from datetime import datetime
from random import random

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils.translation import gettext as _

from ikwen.accesscontrol.models import Member
from ikwen.core.utils import get_mail_content, get_service_instance

from zovizo.models import Wallet, Draw, DrawSubscription, EarningsWallet

SUBSCRIPTION_FEES = getattr(settings, 'SUBSCRIPTION_FEES', 100)
WINNER_SHARE = getattr(settings, 'SUBSCRIPTION_FEES', 75)
INCUBATOR_SHARE = getattr(settings, 'SUBSCRIPTION_FEES', 10)
COMPANY_SHARE = getattr(settings, 'SUBSCRIPTION_FEES', 15)


def register_members_for_next_draw(debug=False):
    draw = Draw.get_current()
    draw.run_on = datetime.now()
    if not debug:
        if not draw.is_active:
            return
        draw.is_active = False
        draw.save()
    wallet_queryset = Wallet.objects.using('zovizo_wallets').filter(balance__gte=SUBSCRIPTION_FEES)
    total = wallet_queryset.count()
    chunks = total / 500 + 1
    draw.participant_count = 0
    for i in range(chunks):
        start = i * 500
        finish = (i + 1) * 500
        for wallet in wallet_queryset[start:finish]:
            if not debug:
                wallet.balance -= SUBSCRIPTION_FEES
                wallet.save()
            draw.participant_count += 1
            draw.jackpot = draw.participant_count * SUBSCRIPTION_FEES
            try:
                member = Member.objects.get(pk=wallet.member_id)
                DrawSubscription.objects.get_or_create(draw=draw, member=member, amount=SUBSCRIPTION_FEES)
                print("Subscription added")
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
    count = DrawSubscription.objects.exclude(member__in=previous_winners).filter(draw=draw).count()
    if count == 0:
        print("Not enough participants for the draw")
        return
    ref = random()
    try:
        sub = DrawSubscription.objects.exclude(member__in=previous_winners).filter(draw=draw, rand__gte=ref)[0]
        print("Found GTE")
    except:
        try:
            sub = DrawSubscription.objects.exclude(member__in=previous_winners).filter(draw=draw, rand__lt=ref)[0]
            print("Found LT")
        except:
            pass

    if not debug:
        sub.is_winner = True
        sub.save()
    draw.winner = sub.member
    draw.save()
    notify_winner(draw.winner, debug)
    share_jackpot(debug)


def notify_winner(winner, debug=False):
    service = get_service_instance()
    config = service.config
    subject = _("You are the happy winner of the draw today")
    template_name = 'zovizo/mails/winner_notice.html'
    draw = Draw.get_current()
    html_content = get_mail_content(subject, template_name=template_name,
                                    extra_context={'member_name': winner.first_name, 'draw': draw})
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
    earnings_wallet, update = EarningsWallet.objects.using('zovizo_wallets').get_or_create(member_id=winner.id)
    earnings_wallet.balance += winner_earnings
    earnings_wallet.save()
