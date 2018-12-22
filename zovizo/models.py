from datetime import datetime
from random import random

from django.db import models
from djangotoolbox.fields import EmbeddedModelField

from ikwen.core.constants import PENDING
from ikwen.core.models import Model
from ikwen.accesscontrol.models import Member


MEMBERSHIP = '__Membership'


class Project(Model):
    member = models.ForeignKey(Member)
    name = models.CharField(max_length=60)
    summary = models.CharField(max_length=60)
    description = models.CharField(max_length=60)


class Wallet(Model):
    member_id = models.CharField(max_length=24, db_index=True)
    balance = models.IntegerField(default=0, db_index=True)


class EarningsWallet(Model):
    member_id = models.CharField(max_length=24, db_index=True)
    balance = models.IntegerField(default=0, db_index=True)


class Bundle(Model):
    amount = models.IntegerField()
    duration = models.IntegerField()
    is_active = models.BooleanField(default=True)


class Subscription(Model):
    member = models.ForeignKey(Member)
    bundle = EmbeddedModelField(Bundle)
    amount = models.IntegerField()
    status = models.CharField(max_length=15, default=PENDING)


class Draw(Model):
    winner = models.ForeignKey(Member, blank=True, null=True)
    participant_count = models.IntegerField(default=0)
    jackpot = models.IntegerField(default=0)
    run_on = models.DateField(blank=True, null=True)
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
    rand = models.FloatField(default=random)