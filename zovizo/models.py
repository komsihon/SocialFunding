from datetime import datetime
from random import random

from currencies.models import Currency
from django.contrib.humanize.templatetags.humanize import intcomma
from django.db import models
from djangotoolbox.fields import EmbeddedModelField, ListField

from ikwen.core.constants import PENDING
from ikwen.core.models import Model, AbstractWatchModel
from ikwen.core.fields import MultiImageField
from ikwen.accesscontrol.models import Member


MEMBERSHIP = '__Membership'


class Project(Model):
    member = models.ForeignKey(Member)
    name = models.CharField(max_length=60)
    summary = models.CharField(max_length=60)
    description = models.CharField(max_length=60)


class Wallet(Model):
    member_id = models.CharField(max_length=24, db_index=True)
    balance = models.FloatField(default=0, db_index=True)
    xaf_balance = models.FloatField(default=0, db_index=True)  # Balance in XAF
    currency_code = models.CharField(max_length=24, db_index=True, blank=True, null=True)  # Currency of the wallet

    def _get_currency(self):
        try:
            currency = Currency.objects.using('default').get(code=self.currency_code)
        except:
            self.balance = self.xaf_balance
            currency = Currency.active.base()
            self.currency_code = currency.code
            self.save(using='zovizo_wallets')
        return currency
    currency = property(_get_currency)


class EarningsWallet(Model):
    member_id = models.CharField(max_length=24, db_index=True)
    balance = models.FloatField(default=0, db_index=True)
    xaf_balance = models.IntegerField(default=0, db_index=True)  # Balance in XAF

    def __unicode__(self):
        member = self.member
        return member.username + ' - ' + member.phone

    def _get_member(self):
        return Member.objects.get(pk=self.member_id)
    member = property(_get_member)

    def get_obj_details(self):
        return intcomma(self.balance)


class CashOut(Model):
    member_id = models.CharField(max_length=24, db_index=True)
    amount = models.IntegerField(default=0, db_index=True)


class Bundle(Model):
    UPLOAD_TO = 'bundles/'
    amount = models.IntegerField()
    duration = models.IntegerField()
    is_active = models.BooleanField(default=True)
    show_on_home = models.BooleanField(default=False)
    cover = MultiImageField(upload_to=UPLOAD_TO, blank=True, null=True)
    currency = models.ForeignKey(Currency, blank=True, null=True)  # Currency of the bundle
    is_investor_pack = models.BooleanField(default=False)

    def __unicode__(self):
        return str(self.amount)


class Subscription(Model):
    member = models.ForeignKey(Member)
    bundle = EmbeddedModelField(Bundle)
    amount = models.IntegerField()
    number = models.IntegerField(unique=True, blank=True, null=True)
    status = models.CharField(max_length=15, default=PENDING)
    quantity = models.IntegerField(default=1)


class Draw(Model):
    winner = models.ForeignKey(Member, blank=True, null=True)
    participant_count = models.IntegerField(default=0)
    jackpot = models.FloatField(default=0)
    run_on = models.DateField(unique=True, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    @staticmethod
    def get_current():
        today = datetime.now().date()
        draw, update = Draw.objects.get_or_create(run_on=today)
        return draw


class DrawSubscription(Model):
    draw = models.ForeignKey(Draw)
    member = models.ForeignKey(Member)
    amount = models.IntegerField()
    is_winner = models.BooleanField(default=False, db_index=True)
    rand = models.FloatField(default=random)


class Subscriber(AbstractWatchModel):
    """
    Profile information for a Subscriber on the website
    """
    member = models.OneToOneField(Member)
    last_payment_on = models.DateTimeField(blank=True, null=True, db_index=True)

    subscriptions_count_history = ListField()
    turnover_history = ListField()
    earnings_history = ListField()

    total_subscriptions_count = models.IntegerField(default=0)
    total_turnover = models.IntegerField(default=0)
    total_earnings = models.IntegerField(default=0)
