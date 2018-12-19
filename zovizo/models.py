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
    member_id = models.CharField(max_length=24)
    balance = models.IntegerField(default=0)


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
    winner = models.ForeignKey(Member)
    participant_count = models.IntegerField(default=0)


class DrawSubscription(Model):
    member = models.ForeignKey(Member)
    amount = models.IntegerField()