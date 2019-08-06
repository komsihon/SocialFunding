
from django.conf.urls import patterns, url
from django.contrib.auth.decorators import login_required, permission_required

from zovizo.views import Profile, PreviousDraws, WalletList

urlpatterns = patterns(
    '',
    url(r'^previousDraws/$', PreviousDraws.as_view(), name='previous_draws'),
    url(r'^profile/$', login_required(Profile.as_view()), name='profile'),
    url(r'^walletList/$', permission_required('accesscontrol.sudo')(WalletList.as_view()), name='wallet_list'),
)
