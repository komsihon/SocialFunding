# -*- coding: utf-8 -*-
import random
import string
import logging

import requests
import json

from currencies.models import Currency
from django.conf import settings
from django.core.urlresolvers import reverse
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.utils.http import urlunquote
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.generic import TemplateView

from ikwen.billing.models import PaymentMean
from ikwen.core.utils import get_service_instance, parse_paypal_response, EC_ENDPOINT

from zovizo.models import Bundle, Subscription
from zovizo.views import confirm_bundle_payment

logger = logging.getLogger('ikwen')


class SetExpressCheckout(TemplateView):
    template_name = 'zovizo/paypal/cancel.html'

    @method_decorator(sensitive_post_parameters())
    @method_decorator(csrf_protect)
    @method_decorator(never_cache)
    def post(self, request, *args, **kwargs):
        service = get_service_instance()
        payment_mean = PaymentMean.objects.get(slug='paypal')
        if getattr(settings, 'DEBUG', False):
            paypal = json.loads(payment_mean.credentials)
        else:
            try:
                paypal = json.loads(payment_mean.credentials)
            except:
                return HttpResponse("Error, Could not parse PayPal parameters.")

        cancel_url = request.META.get('HTTP_REFERER')
        if not cancel_url:
            cancel_url = service.url + reverse('home')

        member = request.user
        try:
            bundle_id = request.POST['product_id']
            bundle = Bundle.objects.get(pk=bundle_id)
            qty = 1
            if bundle.is_investor_pack:
                if bundle.currency.code != 'EUR':
                    currency = Currency.objects.get(code='EUR')
                    bundle = Bundle.objects.filter(currency=currency, is_investor_pack=True)[0]
                qty = int(request.POST.get('quantity', 1))
            amount = bundle.amount * qty
            number = Subscription.objects.all().count() + 1
            xaf_amount = amount / bundle.currency.factor
            sub = Subscription.objects.create(member=member, bundle=bundle, amount=xaf_amount,
                                              number=number, quantity=qty)
        except:
            return HttpResponseRedirect(cancel_url)

        if getattr(settings, 'UNIT_TESTING', False):
            signature = 'dumb_signature'
        else:
            signature = ''.join([random.SystemRandom().choice(string.ascii_letters + string.digits) for n in range(16)])
        request.session['signature'] = signature
        request.session['return_url'] = service.url + reverse('zovizo:profile')

        if getattr(settings, 'UNIT_TESTING', False):
            return HttpResponse(json.dumps({"subscription_id": sub.id}))

        ec_data = {
            "USER": paypal['username'],
            "PWD": paypal['password'],
            "SIGNATURE": paypal['signature'],
            "METHOD": "SetExpressCheckout",
            "VERSION": 124.0,
            "RETURNURL": service.url + reverse('zovizo:paypal_get_details') + '?subscription_id=' + sub.id,
            "CANCELURL": cancel_url,
            "PAYMENTREQUEST_0_PAYMENTACTION": "Sale",
            "PAYMENTREQUEST_0_AMT": amount,
            "PAYMENTREQUEST_0_ITEMAMT": amount,
            "PAYMENTREQUEST_0_SHIPPINGAMT": 0,
            "PAYMENTREQUEST_0_TAXAMT": 0,
            "PAYMENTREQUEST_0_CURRENCYCODE": bundle.currency.code,
            "PAYMENTREQUEST_0_DESC": "Purchase on " + service.project_name,

            # Items
            "L_PAYMENTREQUEST_0_NAME0": "Pack %d day(s)" % bundle.duration,
            "L_PAYMENTREQUEST_0_DESC0": '<' + _("No description") + '>',
            "L_PAYMENTREQUEST_0_AMT0": bundle.amount,
            "L_PAYMENTREQUEST_0_QTY0": qty,
            "L_PAYMENTREQUEST_0_TAXAMT0": 0,
            "L_PAYMENTREQUEST_0_NUMBER0": 1,
            "L_PAYMENTREQUEST_0_ITEMURL0": service.url,
            "L_PAYMENTREQUEST_0_ITEMCATEGORY0": 'Physical'
        }

        try:
            response = requests.post(EC_ENDPOINT, data=ec_data)
            result = parse_paypal_response(response.content.decode('utf-8'))
            ACK = result['ACK']
            if ACK == 'Success' or ACK == 'SuccessWithWarning':
                if getattr(settings, 'DEBUG', False):
                    redirect_url = 'https://www.sandbox.paypal.com/checkoutnow?token=' + result['TOKEN']
                else:
                    redirect_url = 'https://www.paypal.com/checkoutnow?token=' + result['TOKEN']
                return HttpResponseRedirect(redirect_url)
            else:
                sub.delete()
                context = self.get_context_data(**kwargs)
                if getattr(settings, 'DEBUG', False):
                    context['paypal_error'] = urlunquote(response.content.decode('utf-8'))
                else:
                    context['paypal_error'] = urlunquote(result['L_LONGMESSAGE0'])
                return render(request, 'zovizo/paypal/cancel.html', context)
        except Exception as e:
            logger.error("%s - PayPal error." % service.project_name, exc_info=True)
            if getattr(settings, 'DEBUG', False):
                raise e
            context = self.get_context_data(**kwargs)
            context['server_error'] = 'Could not initiate transaction due to server error. Contact administrator.'
            return render(request, 'zovizo/paypal/cancel.html', context)


class GetExpressCheckoutDetails(TemplateView):
    template_name = 'zovizo/paypal/confirmation.html'

    def get(self, request, *args, **kwargs):
        service = get_service_instance()
        paypal = json.loads(PaymentMean.objects.get(slug='paypal').credentials)
        paypal_token = request.GET['token']
        ec_data = {
            "USER": paypal['username'],
            "PWD": paypal['password'],
            "SIGNATURE": paypal['signature'],
            "METHOD": "GetExpressCheckoutDetails",
            "VERSION": 124.0,
            "TOKEN": paypal_token
        }
        try:
            response = requests.post(EC_ENDPOINT, data=ec_data)
            result = parse_paypal_response(response.content.decode('utf-8'))
            ACK = result['ACK']
            if ACK == 'Success' or ACK == 'SuccessWithWarning':
                request.session['token'] = paypal_token
                request.session['payer_id'] = request.GET['PayerID']
                context = self.get_context_data(**kwargs)
                return render(request, self.template_name, context)
            else:
                try:
                    Subscription.objects.get(pk=request.GET['subscription_id']).delete()
                except Subscription.DoesNotExist:
                    pass
                context = self.get_context_data(**kwargs)
                if getattr(settings, 'DEBUG', False):
                    context['paypal_error'] = urlunquote(response.content.decode('utf-8'))
                else:
                    context['paypal_error'] = urlunquote(result['L_LONGMESSAGE0'])
                return render(request, 'zovizo/paypal/cancel.html', context)
        except Exception as e:
            logger.error("%s - PayPal error." % service.project_name, exc_info=True)
            if getattr(settings, 'DEBUG', False):
                raise e
            context = self.get_context_data(**kwargs)
            context['server_error'] = 'Could not proceed transaction due to server error. Contact administrator.'
            return render(request, 'zovizo/paypal/cancel.html', context)


class DoExpressCheckout(TemplateView):
    template_name = 'zovizo/paypal/cancel.html'

    @method_decorator(sensitive_post_parameters())
    @method_decorator(csrf_protect)
    @method_decorator(never_cache)
    def post(self, request, *args, **kwargs):
        if getattr(settings, 'UNIT_TESTING', False):
            return confirm_bundle_payment(request, signature=request.session['signature'], *args, **kwargs)

        service = get_service_instance()
        paypal = json.loads(PaymentMean.objects.get(slug='paypal').credentials)

        subscription_id = request.POST['subscription_id']
        sub = Subscription.objects.select_related('member').get(pk=subscription_id)
        bundle = sub.bundle
        amount = bundle.amount * sub.quantity

        ec_data = {
            "USER": paypal['username'],
            "PWD": paypal['password'],
            "SIGNATURE": paypal['signature'],
            "METHOD": "DoExpressCheckoutPayment",
            "VERSION": 124.0,
            "TOKEN": request.session['token'],
            "PAYERID": request.session['payer_id'],
            "PAYMENTREQUEST_0_PAYMENTACTION": "Sale",
            "PAYMENTREQUEST_0_AMT": amount,
            "PAYMENTREQUEST_0_ITEMAMT": amount,
            "PAYMENTREQUEST_0_SHIPPINGAMT": 0,
            "PAYMENTREQUEST_0_TAXAMT": 0,
            "PAYMENTREQUEST_0_CURRENCYCODE": bundle.currency.code,
            "PAYMENTREQUEST_0_DESC": "Purchase on " + service.project_name,

            # Items
            "L_PAYMENTREQUEST_0_NAME0": "Pack %d day(s)" % bundle.duration,
            "L_PAYMENTREQUEST_0_DESC0": '<' + _("No description") + '>',
            "L_PAYMENTREQUEST_0_AMT0": bundle.amount,
            "L_PAYMENTREQUEST_0_QTY0": sub.quantity,
            "L_PAYMENTREQUEST_0_TAXAMT0": 0,
            "L_PAYMENTREQUEST_0_NUMBER0": 1,
            "L_PAYMENTREQUEST_0_ITEMURL0": service.url,
            "L_PAYMENTREQUEST_0_ITEMCATEGORY0": 'Physical'
        }
        if getattr(settings, 'DEBUG', False):
            response = requests.post(EC_ENDPOINT, data=ec_data)
            result = parse_paypal_response(response.content.decode('utf-8'))
            ACK = result['ACK']
            if ACK == 'Success' or ACK == 'SuccessWithWarning':
                return confirm_bundle_payment(request, subscription=sub, signature=request.session['signature'],
                                              next_url=reverse('zovizo:profile'), *args, **kwargs)
            else:
                try:
                    Subscription.objects.get(pk=request.POST['subscription_id']).delete()
                except Subscription.DoesNotExist:
                    pass
                context = self.get_context_data(**kwargs)
                if getattr(settings, 'DEBUG', False):
                    context['paypal_error'] = urlunquote(response.content.decode('utf-8'))
                else:
                    context['paypal_error'] = urlunquote(result['L_LONGMESSAGE0'])
                return render(request, 'zovizo/paypal/cancel.html', context)
        else:
            try:
                response = requests.post(EC_ENDPOINT, data=ec_data)
                result = parse_paypal_response(response.content.decode('utf-8'))
                ACK = result['ACK']
                if ACK == 'Success' or ACK == 'SuccessWithWarning':
                    return confirm_bundle_payment(request, subscription=sub, signature=request.session['signature'],
                                                  next_url=reverse('zovizo:profile'), *args, **kwargs)
                else:
                    try:
                        Subscription.objects.get(pk=request.POST['subscription_id']).delete()
                    except Subscription.DoesNotExist:
                        pass
                    context = self.get_context_data(**kwargs)
                    if getattr(settings, 'DEBUG', False):
                        context['paypal_error'] = urlunquote(response.content.decode('utf-8'))
                    else:
                        context['paypal_error'] = urlunquote(result['L_LONGMESSAGE0'])
                    return render(request, 'zovizo/paypal/cancel.html', context)
            except Exception as e:
                logger.error("%s - PayPal error. S10N ID: %s" % (service.project_name, sub.id), exc_info=True)
                context = self.get_context_data(**kwargs)
                context['server_error'] = 'Could not proceed transaction due to server error. Contact administrator.'
                return render(request, 'zovizo/paypal/cancel.html', context)


class PayPalCancel(TemplateView):
    template_name = 'zovizo/paypal/cancel.html'
