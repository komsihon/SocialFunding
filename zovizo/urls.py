
from django.conf.urls import patterns, url
from django.contrib.auth.decorators import login_required

from zovizo.views import Profile, PreviousDraws

urlpatterns = patterns(
    '',
    url(r'^previousDraws/$', PreviousDraws.as_view(), name='previous_draws'),
    url(r'^profile/$', login_required(Profile.as_view()), name='profile'),
)
