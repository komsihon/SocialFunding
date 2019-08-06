import json
from time import sleep

from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.test.client import Client
from django.test.utils import override_settings
from django.utils import unittest

from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.accesscontrol.models import Member
from ikwen.core.models import OperatorWallet
from ikwen.billing.mtnmomo.views import MTN_MOMO
from ikwen.core.utils import get_service_instance
from ikwen.revival.tests_views import wipe_test_data

from zovizo.models import Subscription, Wallet, Bundle


class ZovizoTestCase(unittest.TestCase):
    """
    This test derives django.utils.unittest.TestCate rather than the default django.test.TestCase.
    Thus, self.client is not automatically created and fixtures not automatically loaded. This
    will be achieved manually by a custom implementation of setUp()
    """
    fixtures = ['ikwen_members.yaml', 'setup_data.yaml', 'member_profiles.yaml', 'revivals.yaml']

    def setUp(self):
        self.client = Client()
        for fixture in self.fixtures:
            call_command('loaddata', fixture)

    def tearDown(self):
        wipe_test_data()
        wipe_test_data(UMBRELLA)
        wipe_test_data('test_ikwen_service_2')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102', UNIT_TESTING=True)
    def test_Home(self):
        """
        Make sure page is reachable
        """
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102', UNIT_TESTING=True)
    def test_Profile(self):
        """
        Make sure page is reachable
        """
        self.client.login(username='member2', password='admin')
        response = self.client.get(reverse('zovizo:profile'))
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102', UNIT_TESTING=True)
    def test_confirm_bundle_payment_with_momo(self):
        """
        Paying for a bundle creates a Subscription object for the Member
        and tops up his zovizo wallet balance
        """
        member = Member.objects.get(username='member2')
        service = get_service_instance()
        member_wallet, update = Wallet.objects.using('zovizo_wallets').get_or_create(member=member)
        member_balance_before = member_wallet.balance
        operator_wallet, update = OperatorWallet.objects.using('wallets').get_or_create(nonrel_id=service.id, provider=MTN_MOMO)
        operator_balance_before = operator_wallet.balance
        bundle_id = '58d1000fa8feb6805199db01'
        self.client.login(username='member2', password='admin')
        self.client.post(reverse('billing:momo_set_checkout'), {'product_id': bundle_id})
        response = self.client.get(reverse('billing:init_momo_transaction'), data={'phone': '677003321'})
        json_resp = json.loads(response.content)
        tx_id = json_resp['tx_id']
        sleep(1)  # Wait for the transaction to complete before querying status
        response = self.client.get(reverse('billing:check_momo_transaction_status'), data={'tx_id': tx_id})
        json_resp = json.loads(response.content)
        self.assertTrue(json_resp['success'])
        sub = Subscription.objects.filter(member=member).order_by('-id')[0]
        self.assertEqual(sub.number, 1)
        member_wallet = Wallet.objects.using('zovizo_wallets').get(member=member)
        operator_wallet = OperatorWallet.objects.using('wallets').get(nonrel_id='56eb6d04b37b3379b531b102', provider=MTN_MOMO)
        bundle = Bundle.objects.get(pk=bundle_id)
        self.assertEqual(member_wallet.balance, member_balance_before + bundle.amount)
        self.assertEqual(operator_wallet.balance,operator_balance_before + bundle.amount)
