import json
from datetime import datetime
from threading import Thread

from django.conf import settings
from django.contrib import messages
from django.core.mail import EmailMessage
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.views.generic import TemplateView
from django.utils.translation import gettext as _

from ikwen.core.constants import CONFIRMED, PENDING
from ikwen.accesscontrol.models import Member
from ikwen.core.utils import get_mail_content, get_service_instance, set_counters, increment_history_field
from ikwen.revival.models import MemberProfile
from ikwen.billing.mtnmomo.views import MTN_MOMO

from zovizo.models import MEMBERSHIP, Project, Bundle, Subscription, Wallet, Draw, DrawSubscription, EarningsWallet

SUBSCRIPTION_FEES = getattr(settings, 'SUBSCRIPTION_FEES', 100)
WINNER_SHARE = getattr(settings, 'SUBSCRIPTION_FEES', 75)
INCUBATOR_SHARE = getattr(settings, 'SUBSCRIPTION_FEES', 10)
COMPANY_SHARE = getattr(settings, 'SUBSCRIPTION_FEES', 15)


def register_members_for_next_draw():
    draw = Draw.get_current()
    wallet_queryset = Wallet.objects.using('zovizo_wallets').filter(balance__gt=0)
    total = wallet_queryset.count()
    chunks = total / 500 + 1
    for i in range(chunks):
        start = i * 500
        finish = (i + 1) * 500
        for wallet in wallet_queryset[start:finish]:
            wallet.balance -= SUBSCRIPTION_FEES
            wallet.save()
            draw.participant_count += 1
            draw.jackpot = draw.participant_count * SUBSCRIPTION_FEES
            try:
                member = Member.objects.get(pk=wallet.member_id)
                DrawSubscription.objects.create(draw=draw, member=member, amount=SUBSCRIPTION_FEES)
            except:
                continue
    draw.save()


def pick_up_winner():
    pass


def share_jackpot():
    draw = Draw.get_current()
    if not draw.is_active:
        return
    winner_earnings = draw.jackpot * WINNER_SHARE / 100
    earnings_wallet = EarningsWallet.objects.get_or_create(member_id=draw.winner.id)
    earnings_wallet.balance = winner_earnings