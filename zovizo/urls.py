
from django.conf.urls import patterns, url
from django.contrib.auth.decorators import login_required, permission_required

from zovizo.views import Profile, PreviousDraws, WalletList, BundleList, ChangeBundle

urlpatterns = patterns(
    '',
    url(r'^previousDraws/$', PreviousDraws.as_view(), name='previous_draws'),
    url(r'^profile/$', login_required(Profile.as_view()), name='profile'),
    url(r'^wallets/$', permission_required('accesscontrol.sudo')(WalletList.as_view()), name='wallet_list'),
    url(r'^bundles/$', permission_required('accesscontrol.sudo')(BundleList.as_view()), name='bundle_list'),
    url(r'^bundle/(?P<object_id>[-\w]+)$', permission_required('accesscontrol.sudo')(ChangeBundle.as_view()), name='change_bundle'),
)
