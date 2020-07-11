import json
from datetime import datetime
import random as random_module

import requests
from currencies.conf import SESSION_KEY
from currencies.models import Currency
from django.conf import settings
from django.core.mail import EmailMessage
from django.utils.translation import gettext as _

from ikwen.accesscontrol.models import Member
from ikwen.core.utils import get_mail_content, get_service_instance

from zovizo.models import Wallet, Draw, DrawSubscription, EarningsWallet

SUBSCRIPTION_FEES = getattr(settings, 'SUBSCRIPTION_FEES', 100)
WINNER_SHARE = getattr(settings, 'WINNER_SHARE', 60)
COMPANY_SHARE = getattr(settings, 'COMPANY_SHARE', 40)


def register_members_for_next_draw(debug=False):
    draw = Draw.get_current()
    draw.run_on = datetime.now()
    if not debug:
        if not draw.is_active:
            return
        draw.is_active = False
        draw.save()
    wallet_queryset = Wallet.objects.using('zovizo_wallets').filter(xaf_balance__gte=SUBSCRIPTION_FEES)
    total = wallet_queryset.count()
    chunks = total / 500 + 1
    draw.participant_count = 0
    for i in range(chunks):
        start = i * 500
        finish = (i + 1) * 500
        for wallet in wallet_queryset[start:finish]:
            factor = 1
            currency = wallet.currency
            if not debug:
                factor = int(1 / currency.factor / SUBSCRIPTION_FEES)
                fees = SUBSCRIPTION_FEES * factor
                if wallet.xaf_balance < fees:
                    factor = int(wallet.xaf_balance / SUBSCRIPTION_FEES)
                    if factor == 0:
                        continue
                    fees = SUBSCRIPTION_FEES * factor
                wallet.xaf_balance -= fees
                wallet.balance = round(wallet.xaf_balance * currency.factor, 2)
                wallet.save()
            draw.participant_count += factor
            draw.jackpot = draw.participant_count * SUBSCRIPTION_FEES
            member = Member.objects.get(pk=wallet.member_id)
            for i in range(factor):
                try:
                    DrawSubscription.objects.create(draw=draw, member=member, amount=SUBSCRIPTION_FEES)
                except:
                    continue
    draw.save()


def pick_up_winner(debug=False):
    """
    Selects a winner for a draw. A random number is generated
    The winner is a random DrawSubscription which rand field
    is the nearest to the ref random number.
    """
    draw = Draw.get_current()
    if not debug:
        if draw.is_active:
            raise ValueError("Cannot pick-up up winner on an active Draw. Call register_members_for_next_draw() first.")
        if draw.winner:
            raise ValueError("Cannot pick-up a winner more than once. A winner already exists for this draw.")

    previous_winners = [obj.winner for obj in Draw.objects.exclude(pk=draw.id).order_by('-id')[:5] if obj.winner]
    subscription_qs = DrawSubscription.objects.exclude(member__in=previous_winners).filter(draw=draw)
    count = subscription_qs.count()
    if count == 0:
        print("Not enough participants for the draw")
        return
    index_list = list(range(count))
    i = random_module.choice(index_list)
    sub = subscription_qs[i]

    if not debug:
        sub.is_winner = True
        sub.save()
    draw.winner = sub.member
    draw.save()
    notify_winner(draw.winner, debug)
    share_jackpot(debug)
    if debug:
        clean_up(draw)


def notify_winner(winner, debug=False):
    service = get_service_instance()
    config = service.config
    subject = _("You are the happy winner of the draw today")
    template_name = 'zovizo/mails/winner_notice.html'
    draw = Draw.get_current()
    currency = Wallet.objects.get(member=winner).currency
    jackpot = draw.jackpot * currency.factor
    html_content = get_mail_content(subject, template_name=template_name,
                                    extra_context={'member_name': winner.first_name, 'draw': draw,
                                                   'jackpot': jackpot, 'currency_symbol': currency.symbol})
    sender = '%s <no-reply@%s>' % (config.company_name, service.domain)
    recipient = 'rsihon@gmail.com' if debug else winner.email
    msg = EmailMessage(subject, html_content, sender, [recipient])
    if not debug:
        msg.bcc = [sudo.email for sudo in Member.objects.filter(is_superuser=True) if sudo.email]
    msg.content_subtype = "html"
    msg.send()


def share_jackpot(debug=False):
    draw = Draw.get_current()
    if debug:
        if draw.is_active:
            return
    winner_earnings = draw.jackpot * WINNER_SHARE / 100
    winner = Member.objects.filter(is_superuser=True)[0] if debug else draw.winner
    winner_wallet = Wallet.objects.get(member=winner)
    currency = winner_wallet.currency
    earnings_wallet, update = EarningsWallet.objects.using('zovizo_wallets').get_or_create(member_id=winner.id, currency=currency)
    earnings_wallet.xaf_balance += winner_earnings
    earnings_wallet.balance = earnings_wallet.xaf_balance * currency.factor
    earnings_wallet.save()


def clean_up(draw):
    draw.winner = None
    draw.save()
    DrawSubscription.objects.filter(draw=draw).update(is_winner=False)
    print "Test draw cleaned up"


def detect_and_set_currency_by_ip(request):
    if request.session.get(SESSION_KEY):
        return Currency.objects.get(code=request.session.get(SESSION_KEY))
    try:
        if getattr(settings, 'LOCAL_DEV', False):
            ip = '154.72.166.181'  # My Local IP by the time I was writing this code
        else:
            ip = request.META['REMOTE_ADDR']
        from ikwen.conf import settings as ikwen_settings
        r = requests.get('http://api.ipstack.com/%s?access_key=%s' % (ip, ikwen_settings.IP_STACK_API_KEY))
        result = json.loads(r.content.decode('utf-8'))
        country_code = result['country_code']
        r = requests.get('http://country.io/currency.json')
        result = json.loads(r.content)
        currency_code = result[country_code]
        try:
            Currency.active.filter(code=currency_code)
        except:
            currency_code = 'USD'
    except:
        currency_code = 'USD'

    if currency_code and Currency.active.filter(code=currency_code).exists():
        if hasattr(request, 'session'):
            request.session[SESSION_KEY] = currency_code
    return Currency.objects.get(code=currency_code)
