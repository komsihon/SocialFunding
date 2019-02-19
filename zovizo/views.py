import json
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.views.generic import TemplateView
from django.utils.translation import gettext as _

from ikwen.core.constants import CONFIRMED, PENDING
from ikwen.core.views import DashboardBase
from ikwen.core.utils import get_mail_content, get_service_instance, set_counters, increment_history_field, \
    slice_watch_objects, rank_watch_objects
from ikwen.revival.models import MemberProfile
from ikwen.billing.mtnmomo.views import MTN_MOMO

from zovizo.models import MEMBERSHIP, Project, Bundle, Subscription, Wallet, Draw, DrawSubscription, Subscriber
from zovizo.utils import pick_up_winner, register_members_for_next_draw

SUBSCRIPTION_FEES = getattr(settings, 'SUBSCRIPTION_FEES', 100)
COMPANY_SHARE = getattr(settings, 'SUBSCRIPTION_FEES', 15)


class Home(TemplateView):
    template_name = 'zovizo/home.html'


class About(TemplateView):
    template_name = 'zovizo/about.html'


def start_draw():
    register_members_for_next_draw(debug=True)
    pick_up_winner(debug=True)


class DrawView(TemplateView):
    template_name = 'zovizo/draw.html'

    def get_context_data(self, **kwargs):
        context = super(DrawView, self).get_context_data(**kwargs)
        draw = Draw.get_current()
        DrawSubscription.objects.filter(draw=draw).delete()
        register_members_for_next_draw(debug=True)
        context['draw'] = draw
        return context

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'start_draw':
            pick_up_winner(debug=True)
            response = {'success': True}
            return HttpResponse(json.dumps(response))
        if action == 'get_winning_number':
            draw = Draw.get_current()
            if draw.winner:
                sub = DrawSubscription.objects.get(draw=draw, member=draw.winner)
                response = {'winner': '%06d' % sub.number}
                draw.winner = None  # Cancel everything.
                draw.save()
            else:
                response = {'winner': None}
            return HttpResponse(json.dumps(response))
        return super(DrawView, self).get(request, *args, **kwargs)


class Profile(TemplateView):
    template_name = 'zovizo/profile.html'

    def get_context_data(self, **kwargs):
        context = super(Profile, self).get_context_data(**kwargs)

        draw = Draw.get_current()
        if datetime.now().hour < getattr(settings, 'DRAW_HOUR', 19):
            draw.participant_count = Wallet.objects.using('zovizo_wallets')\
                .filter(balance__gte=SUBSCRIPTION_FEES).count()
            draw.jackpot = draw.participant_count * SUBSCRIPTION_FEES
        draw.winner_jackpot = draw.jackpot * (1 - COMPANY_SHARE/100)
        context['bundle_list'] = Bundle.objects.filter(is_active=True).order_by('amount')
        wallet, update = Wallet.objects.using('zovizo_wallets').get_or_create(member_id=self.request.user.id)
        context['wallet'] = wallet
        context['draw'] = draw
        return context

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'save_project':
            return self.save_project(request)
        return super(Profile, self).get(request, *args, **kwargs)

    def save_project(self, request):
        project_title = request.POST['project_title']
        project_summary = request.POST['project_summary']
        project_description = request.POST['project_description']

        member = request.user
        project, update = Project.objects.get_or_create(member=member)
        project.title = project_title
        project.summary = project_summary
        project.description = project_description
        project.save()
        if update:
            notice = _("Project successfully updated")
        else:
            notice = _("Project successfully created")
        messages.success(request, notice)
        return HttpResponseRedirect(reverse("zovizo:profile"))


def add_member_to_revival(request, *args, **kwargs):
    member = request.user
    member_profile, update = MemberProfile.objects.get_or_create(member=member)
    if MEMBERSHIP not in member_profile.tag_list:
        member_profile.tag_list.append(MEMBERSHIP)
        member_profile.save()


def render_default_revival(target, obj, revival, **kwargs):
    subject = _("Give a chance to your projects")
    template_name = 'zovizo/mails/default_revival.html'
    html_content = get_mail_content(subject, template_name=template_name,
                                    extra_context={'member_name': target.member.first_name})
    return subject, html_content


def set_bundle_payment_checkout(request, *args, **kwargs):
    """
    This function has no URL associated with it.
    It serves as ikwen setting "MOMO_BEFORE_CHECKOUT"
    """
    member = request.user
    service = get_service_instance()
    bundle_id = request.POST['product_id']
    bundle = Bundle.objects.get(pk=bundle_id)
    amount = bundle.amount
    obj = Subscription.objects.create(member=member, bundle=bundle, amount=amount)
    request.session['amount'] = amount
    request.session['model_name'] = 'zovizo.Subscription'
    request.session['object_id'] = obj.id

    mean = request.GET.get('mean', MTN_MOMO)
    request.session['mean'] = mean
    request.session['notif_url'] = service.url  # Orange Money only
    request.session['cancel_url'] = service.url + reverse('zovizo:profile') # Orange Money only
    request.session['return_url'] = service.url + reverse('zovizo:profile')


def confirm_bundle_payment(request, *args, **kwargs):
    """
    This function has no URL associated with it.
    It serves as ikwen setting "MOMO_AFTER_CHECKOUT"
    """
    member = request.user
    service = get_service_instance(check_cache=False)
    service.raise_balance(request.session['amount'], provider=request.session['mean'])
    object_id = request.session['object_id']
    obj = Subscription.objects.get(pk=object_id, status=PENDING)
    obj.status = CONFIRMED
    obj.save()
    set_counters(service)
    increment_history_field(service, 'turnover_history', obj.amount)
    increment_history_field(service, 'earnings_history', obj.amount)
    increment_history_field(service, 'transaction_earnings_history', obj.amount)
    increment_history_field(service, 'transaction_count_history')
    wallet, update = Wallet.objects.using('zovizo_wallets').get_or_create(member_id=member.id)
    wallet.balance += obj.amount
    wallet.save()
    now = datetime.now()
    draw = Draw.get_current()
    if now.hour < getattr(settings, 'DRAW_HOUR', 19):
        if wallet.balance == obj.amount:  # Means Member is refilling a previously empty balance
            draw.participant_count += 1
            draw.jackpot = draw.participant_count * SUBSCRIPTION_FEES
            draw.save()

    subscriber, update = Subscriber.objects.get_or_create(member=member)
    set_counters(subscriber)
    subscriber.last_payment_on = now
    increment_history_field(subscriber, 'subscriptions_count_history')
    increment_history_field(subscriber, 'turnover_history', obj.amount)
    increment_history_field(subscriber, 'earnings_history', obj.amount)

    # member = request.user
    # add_event(service, PAYMENT_CONFIRMATION, member=member, object_id=object_id)
    # partner = s.retailer
    # if partner:
    #     add_database_to_settings(partner.database)
    #     sudo_group = Group.objects.using(partner.database).get(name=SUDO)
    # else:
    #     sudo_group = Group.objects.using(UMBRELLA).get(name=SUDO)
    # add_event(service, PAYMENT_CONFIRMATION, group_id=sudo_group.id, object_id=invoice.id)
    # if member.email:
    #     invoice_url = 'http://ikwen.com' + reverse('billing:invoice_detail', args=(invoice.id,))
    #     subject, message, sms_text = get_payment_confirmation_message(payment, member)
    #     html_content = get_mail_content(subject, message, template_name='billing/mails/notice.html',
    #                                     extra_context={'member_name': member.first_name, 'invoice': invoice,
    #                                                    'cta': _("View invoice"), 'invoice_url': invoice_url})
    #     sender = '%s <no-reply@%s>' % (config.company_name, service.domain)
    #     msg = EmailMessage(subject, html_content, sender, [member.email])
    #     msg.content_subtype = "html"
    #     Thread(target=lambda m: m.send(), args=(msg,)).start()
    notice = _("Your subscription was successful.")
    messages.success(request, notice)
    return HttpResponseRedirect(request.session['return_url'])


class Dashboard(DashboardBase):
    template_name = 'zovizo/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super(Dashboard, self).get_context_data(**kwargs)
        subscribers_today = slice_watch_objects(Subscriber)
        subscribers_yesterday = slice_watch_objects(Subscriber, 1)
        subscribers_last_week = slice_watch_objects(Subscriber, 7)
        subscribers_last_28_days = slice_watch_objects(Subscriber, 28)
        subscribers_report = {
            'today': rank_watch_objects(subscribers_today, 'turnover_history'),
            'yesterday': rank_watch_objects(subscribers_yesterday, 'turnover_history', 1),
            'last_week': rank_watch_objects(subscribers_last_week, 'turnover_history', 7),
            'last_28_days': rank_watch_objects(subscribers_last_28_days, 'turnover_history', 28)
        }
        context['subscribers_report'] = subscribers_report
        return context

