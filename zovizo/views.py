import json
import string
import traceback
import logging
from datetime import datetime, timedelta
import random

import requests
from currencies.models import Currency
from django.conf import settings
from django.contrib import messages
from django.contrib.humanize.templatetags.humanize import intcomma
from django.core.urlresolvers import reverse
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.views.generic import TemplateView
from django.utils.translation import gettext as _

from ikwen.accesscontrol.models import Member
from ikwen.conf.settings import WALLETS_DB_ALIAS
from ikwen.core.constants import CONFIRMED, PENDING
from ikwen.core.models import Service
from ikwen.core.views import DashboardBase, HybridListView, ChangeObjectBase
from ikwen.core.utils import get_mail_content, get_service_instance, set_counters, increment_history_field, \
    slice_watch_objects, rank_watch_objects, send_sms, add_database
from ikwen.revival.models import MemberProfile
from ikwen.billing.models import MoMoTransaction
from ikwen.billing.mtnmomo.views import MTN_MOMO

from echo.utils import count_pages
from echo.models import Balance

from zovizo.admin import BundleAdmin
from zovizo.models import MEMBERSHIP, Project, Bundle, Subscription, Wallet, Draw, DrawSubscription, Subscriber, \
    EarningsWallet, CashOut
from zovizo.utils import pick_up_winner, register_members_for_next_draw, detect_and_set_currency_by_ip

from daraja.models import Dara, Follower
from daraja.utils import send_dara_notification_email

logger = logging.getLogger('ikwen')

SUBSCRIPTION_FEES = getattr(settings, 'SUBSCRIPTION_FEES', 100)
COMPANY_SHARE = getattr(settings, 'COMPANY_SHARE', 25)


class Home(TemplateView):
    template_name = 'zovizo/home.html'

    def get_context_data(self, **kwargs):
        context = super(Home, self).get_context_data(**kwargs)
        currency = detect_and_set_currency_by_ip(self.request)
        now = datetime.now()
        draw = Draw.get_current()
        run_on = draw.run_on
        run_on = datetime.combine(run_on, datetime.min.time())
        diff = now - run_on
        if 86400 < diff.total_seconds() < 86460:
            count_down = '00:00:00'
        else:
            hour = getattr(settings, 'DRAW_HOUR', 19)
            if now.hour >= hour:
                next_draw = datetime(now.year, now.month, now.day, hour) + timedelta(hours=24)
            else:
                next_draw = datetime(now.year, now.month, now.day, hour)

            diff = next_draw - now
            remaining_time = int(diff.total_seconds())
            context['remaining_time'] = remaining_time
            rh = remaining_time / 3600
            rm = (remaining_time % 3600) / 60
            rs = (remaining_time % 3600) % 60
            count_down = '%02d:%02d:%02d' % (rh, rm, rs)
        context['count_down'] = count_down
        context['bundle_list'] = Bundle.objects.filter(currency=currency, is_investor_pack=False,
                                                       show_on_home=True).order_by('amount')
        try:
            context['investor_pack'] = Bundle.objects.filter(currency=currency, is_investor_pack=True)[0]
        except:
            pass
        context['investor_pack_cost_xaf'] = 36500
        context['fundraising_target'] = 300000
        return context

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'check_current_draw':
            now = datetime.now()
            draw = Draw.get_current()
            run_on = draw.run_on
            run_on = datetime.combine(run_on, datetime.min.time())
            diff = now - run_on
            if diff.total_seconds() >= 68580:
                draw.is_closed = True
            else:
                draw.is_closed = False
            response = {'draw': draw.to_dict()}
            return HttpResponse(json.dumps(response))
        elif action == 'get_winning_number':
            draw = Draw.get_current()
            if draw.winner:
                sub = Subscription.objects.filter(member=draw.winner).order_by('-id')[0]
                response = {'winner': '%06d' % sub.number}
            else:
                response = {'winner': None}
            return HttpResponse(json.dumps(response))
        response = super(Home, self).get(self, request, *args, **kwargs)
        return response


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
            register_members_for_next_draw(debug=True)
            pick_up_winner(debug=True)
            response = {'success': True}
            return HttpResponse(json.dumps(response))
        if action == 'get_winning_number':
            draw = Draw.objects.filter(winner__isnull=False).order_by('-id')[0]
            if draw.winner:
                sub = Subscription.objects.filter(member=draw.winner).order_by('-id')[0]
                response = {'winner': '%06d' % sub.number}
            else:
                response = {'winner': None}
            return HttpResponse(json.dumps(response))
        return super(DrawView, self).get(request, *args, **kwargs)


class PreviousDraws(TemplateView):
    template_name = 'zovizo/previous_draws.html'

    def get_context_data(self, **kwargs):
        context = super(PreviousDraws, self).get_context_data(**kwargs)
        context['subscription_list'] = DrawSubscription.objects.select_related('draw').filter(is_winner=True).order_by('-id')[:15]
        return context


class Profile(TemplateView):
    template_name = 'zovizo/profile.html'

    def get_context_data(self, **kwargs):
        context = super(Profile, self).get_context_data(**kwargs)
        member = self.request.user
        currency = detect_and_set_currency_by_ip(self.request)
        draw = Draw.get_current()
        if datetime.now().hour < getattr(settings, 'DRAW_HOUR', 19):
            draw.participant_count = Wallet.objects.using('zovizo_wallets')\
                .filter(balance__gte=SUBSCRIPTION_FEES).count()
            draw.jackpot = draw.participant_count * SUBSCRIPTION_FEES
        draw.winner_jackpot = draw.jackpot * (1 - COMPANY_SHARE/100)
        context['bundle_list'] = Bundle.objects.filter(is_active=True, is_investor_pack=False, currency=currency).order_by('amount')
        context['investor_bundle_list'] = Bundle.objects.filter(is_active=True, is_investor_pack=True, currency=currency).order_by('amount')
        wallet, update = Wallet.objects.using('zovizo_wallets').get_or_create(member_id=member.id)
        context['wallet'] = wallet
        if wallet.currency_code:
            context['currency'] = wallet.currency
        else:
            context['currency'] = currency
        ewallet, update = EarningsWallet.objects.using('zovizo_wallets').get_or_create(member_id=member.id)
        context['earnings_wallet'] = ewallet
        context['draw'] = draw
        if wallet.xaf_balance > SUBSCRIPTION_FEES:
            try:
                sub = Subscription.objects.filter(member=member, status=CONFIRMED).order_by('-id')[0]
            except IndexError:
                number = Subscription.objects.all().count() + 1
                bundle = Bundle.objects.filter(is_active=True)[0]
                sub = Subscription.objects.create(member=member, bundle=bundle, amount=bundle.amount, number=number)
            sub.number = '%06d' % sub.number
            context['sub'] = sub
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
    qty = 1
    if bundle.is_investor_pack:
        qty = int(request.POST.get('quantity', 1))
    amount = bundle.amount * qty
    number = Subscription.objects.all().count() + 1
    obj = Subscription.objects.create(member=member, bundle=bundle, amount=amount, number=number, quantity=qty)
    signature = ''.join([random.SystemRandom().choice(string.ascii_letters + string.digits) for i in range(16)])
    model_name = 'zovizo.Subscription'
    mean = request.GET.get('mean', MTN_MOMO)
    tx = MoMoTransaction.objects.using(WALLETS_DB_ALIAS)\
        .create(service_id=service.id, type=MoMoTransaction.CASH_OUT, amount=amount, phone='N/A', model=model_name,
                object_id=obj.id, task_id=signature, wallet=mean, username=request.user.username, is_running=True)
    notification_url = reverse('zovizo:confirm_bundle_payment', args=(tx.id, signature))
    cancel_url = reverse('zovizo:profile')
    return_url = reverse('zovizo:profile')
    if getattr(settings, 'UNIT_TESTING', False):
        return HttpResponse(json.dumps({'notification_url': notification_url}), content_type='text/json')
    gateway_url = getattr(settings, 'IKWEN_PAYMENT_GATEWAY_URL', 'https://payment.ikwen.com/v1')
    endpoint = gateway_url + '/request_payment'
    params = {
        'username': getattr(settings, 'IKWEN_PAYMENT_GATEWAY_USERNAME', service.project_name_slug),
        'amount': amount,
        'merchant_name': service.config.company_name,
        'notification_url': service.url + notification_url,
        'return_url': service.url + return_url,
        'cancel_url': service.url + cancel_url,
        'user_id': request.user.username
    }
    try:
        r = requests.get(endpoint, params)
        resp = r.json()
        token = resp.get('token')
        if token:
            next_url = gateway_url + '/checkoutnow/' + resp['token'] + '?mean=' + mean
        else:
            logger.error("%s - Init payment flow failed with URL %s and message %s" % (service.project_name, r.url, resp['errors']))
            messages.error(request, resp['errors'])
            next_url = cancel_url
    except:
        logger.error("%s - Init payment flow failed with URL." % service.project_name, exc_info=True)
        next_url = cancel_url
    return HttpResponseRedirect(next_url)


def confirm_bundle_payment(request, *args, **kwargs):
    service = get_service_instance(check_cache=False)
    ikwen_share_rate = getattr(settings, 'IKWEN_SHARE_RATE', 3)
    sub = kwargs.pop('subscription')
    if sub:
        signature = request.session['signature']
        mean = 'paypal'
        tx = MoMoTransaction.objects.using(WALLETS_DB_ALIAS)\
            .create(service_id=service.id, type=MoMoTransaction.CASH_IN, phone=request.user.phone, amount=sub.amount,
                    model='zovizo.Subscription', object_id=sub.id, wallet=mean, username=request.user.username,
                    is_running=False, message='OK', status=MoMoTransaction.SUCCESS)
    else:
        status = request.GET['status']
        message = request.GET['message']
        operator_tx_id = request.GET['operator_tx_id']
        phone = request.GET['phone']
        tx_id = kwargs['tx_id']
        try:
            tx = MoMoTransaction.objects.using(WALLETS_DB_ALIAS).get(pk=tx_id)
            if not getattr(settings, 'DEBUG', False):
                tx_timeout = getattr(settings, 'IKWEN_PAYMENT_GATEWAY_TIMEOUT', 15) * 60
                expiry = tx.created_on + timedelta(seconds=tx_timeout)
                if datetime.now() > expiry:
                    return HttpResponse("Transaction %s timed out." % tx_id)

            tx.status = status
            tx.message = 'OK' if status == MoMoTransaction.SUCCESS else message
            tx.processor_tx_id = operator_tx_id
            tx.phone = phone
            tx.is_running = False
            tx.fees = tx.amount * ikwen_share_rate / 100
            tx.save()
        except:
            raise Http404("Transaction %s not found" % tx_id)
        if status != MoMoTransaction.SUCCESS:
            return HttpResponse("Notification for transaction %s received with status %s" % (tx_id, status))

        object_id = tx.object_id
        signature = tx.task_id
        mean = tx.wallet
        sub = Subscription.objects.select_related('member').get(pk=object_id, status=PENDING)

    callback_signature = kwargs.get('signature')
    no_check_signature = request.GET.get('ncs')
    if getattr(settings, 'DEBUG', False):
        if not no_check_signature:
            if callback_signature != signature:
                return HttpResponse('Invalid transaction signature')
    else:
        if callback_signature != signature:
            return HttpResponse('Invalid transaction signature')

    member = sub.member
    try:
        follower = Follower.objects.get(member=member)
        referrer = follower.referrer
    except Follower.DoesNotExist:
        referrer = None

    platform_earnings = sub.amount
    dara, dara_service_original, provider_mirror = None, None, None
    if referrer:
        referrer_db = referrer.database
        add_database(referrer_db)
        try:
            dara = Dara.objects.get(member=referrer.member)
        except Dara.DoesNotExist:
            logging.error("%s - Dara %s not found" % (service.project_name, member.username))
        try:
            dara_service_original = Service.objects.using(referrer_db).get(pk=referrer.id)
        except Dara.DoesNotExist:
            logging.error("%s - Dara service not found in %s database for %s" % (service.project_name, referrer_db, referrer.project_name))
        try:
            provider_mirror = Service.objects.using(referrer_db).get(pk=service.id)
        except Service.DoesNotExist:
            logging.error("%s - Provider Service not found in %s database for %s" % (service.project_name, referrer_db, referrer.project_name))

        if dara:
            referrer_earnings = sub.amount * dara.share_rate / 100
            platform_earnings = sub.amount - referrer_earnings
            dara_service_original.raise_balance(referrer_earnings, provider=mean)
            tx.dara_fees = referrer_earnings
            tx.save(using=WALLETS_DB_ALIAS)
            send_dara_notification_email(dara_service_original, sub.amount, referrer_earnings, sub.updated_on)

            set_counters(dara)
            dara.last_transaction_on = datetime.now()

            increment_history_field(dara, 'orders_count_history')
            increment_history_field(dara, 'turnover_history', sub.amount)
            increment_history_field(dara, 'earnings_history', platform_earnings)

            if dara_service_original:
                set_counters(dara_service_original)
                increment_history_field(dara_service_original, 'transaction_count_history')
                increment_history_field(dara_service_original, 'turnover_history', sub.amount)
                increment_history_field(dara_service_original, 'earnings_history', referrer_earnings)

            if dara_service_original:
                set_counters(provider_mirror)
                increment_history_field(provider_mirror, 'transaction_count_history')
                increment_history_field(provider_mirror, 'turnover_history', sub.amount)
                increment_history_field(provider_mirror, 'earnings_history', referrer_earnings)

            try:
                member_ref = Member.objects.using(referrer_db).get(pk=member.id)
            except Member.DoesNotExist:
                member.save(using=referrer_db)
                member_ref = Member.objects.using(referrer_db).get(pk=member.id)
            follower_ref, update = Follower.objects.using(referrer_db).get_or_create(member=member_ref)
            set_counters(follower_ref)
            follower_ref.last_payment_on = datetime.now()
            increment_history_field(follower_ref, 'orders_count_history')
            increment_history_field(follower_ref, 'turnover_history', sub.amount)
            increment_history_field(follower_ref, 'earnings_history', referrer_earnings)

    sub.status = CONFIRMED
    sub.save()
    wallet, update = Wallet.objects.using('zovizo_wallets').get_or_create(member_id=member.id)
    bundle = sub.bundle
    currency = bundle.currency
    wallet.currency_code = currency.code
    wallet.xaf_balance += int(bundle.amount / currency.factor)
    wallet.balance = round(int(wallet.xaf_balance) * currency.factor, 2)
    wallet.save()
    now = datetime.now()

    # Dashboards stats
    set_counters(service)
    increment_history_field(service, 'turnover_history', sub.amount)
    increment_history_field(service, 'earnings_history', platform_earnings)
    increment_history_field(service, 'transaction_earnings_history', tx.amount)
    increment_history_field(service, 'transaction_count_history')

    subscriber, update = Subscriber.objects.get_or_create(member=member)
    set_counters(subscriber)
    subscriber.last_payment_on = now
    increment_history_field(subscriber, 'subscriptions_count_history')
    increment_history_field(subscriber, 'turnover_history', sub.amount)
    increment_history_field(subscriber, 'earnings_history', platform_earnings)

    service.raise_balance(platform_earnings, provider=mean)
    if kwargs.get('next_url'):
        messages.success(request, _("Successful payment. You will take part in the next draw."))
        return HttpResponseRedirect(kwargs.get('next_url'))
    return HttpResponse("Notification received")


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


class WalletList(HybridListView):
    queryset = EarningsWallet.objects.using('zovizo_wallets').filter(balance__gt=0)
    template_name = 'zovizo/wallet_list.html'
    html_results_template_name = 'zovizo/snippets/wallet_list_results.html'

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'notify_cashout':
            wallet_id = request.GET['wallet_id']
            return self.notify_cashout(wallet_id)
        return super(WalletList, self).get(request, *args, **kwargs)

    def notify_cashout(self, wallet_id):
        service = get_service_instance()
        wallet = EarningsWallet.objects.using('zovizo_wallets').get(pk=wallet_id)
        member = Member.objects.get(pk=wallet.member_id)
        balance, update = Balance.objects.using(WALLETS_DB_ALIAS).get_or_create(service_id=service.id)
        try:
            with transaction.atomic(using='zovizo_wallets'):
                CashOut.objects.using('zovizo_wallets').create(member_id=wallet.member_id, amount=wallet.balance)
                wallet.balance = 0
                wallet.save()
                amount = intcomma(wallet.balance)
                notice = _("Congratulations! You will receive a XAF %(amount)s money transfer on your phone number "
                           "%(phone)s as payment for your WinJack." % {'amount': amount, 'phone': member.phone})
                page_count = count_pages(notice)
                balance.sms_count -= page_count
                balance.save()
                send_sms(member.phone, notice)
        except:
            response = {'error': traceback.format_exc()}
        else:
            response = {'success': True}
        return HttpResponse(json.dumps(response))


class BundleList(HybridListView):
    model = Bundle


class ChangeBundle(ChangeObjectBase):
    model = Bundle
    model_admin = BundleAdmin
    label_field = 'duration'
