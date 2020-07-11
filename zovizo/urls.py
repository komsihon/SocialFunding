
from django.conf.urls import patterns, url
from django.contrib.auth.decorators import login_required, permission_required

from zovizo.paypal.views import SetExpressCheckout, GetExpressCheckoutDetails, DoExpressCheckout
from zovizo.views import Profile, PreviousDraws, WalletList, BundleList, ChangeBundle, confirm_bundle_payment

urlpatterns = patterns(
    '',
    url(r'^previousDraws/$', PreviousDraws.as_view(), name='previous_draws'),
    url(r'^profile/$', login_required(Profile.as_view()), name='profile'),
    url(r'^wallets/$', permission_required('accesscontrol.sudo')(WalletList.as_view()), name='wallet_list'),
    url(r'^bundles/$', permission_required('accesscontrol.sudo')(BundleList.as_view()), name='bundle_list'),
    url(r'^bundle$', permission_required('accesscontrol.sudo')(ChangeBundle.as_view()), name='change_bundle'),
    url(r'^bundle/(?P<object_id>[-\w]+)$', permission_required('accesscontrol.sudo')(ChangeBundle.as_view()), name='change_bundle'),
    url(r'^confirm_bundle_payment/(?P<tx_id>[-\w]+)/(?P<signature>[-\w]+)$', confirm_bundle_payment, name='confirm_bundle_payment'),

    url(r'^paypal/setCheckout/', SetExpressCheckout.as_view(), name='paypal_set_checkout'),
    url(r'^paypal/getDetails/$', GetExpressCheckoutDetails.as_view(), name='paypal_get_details'),
    url(r'^paypal/doCheckout/$', DoExpressCheckout.as_view(), name='paypal_do_checkout'),
)
