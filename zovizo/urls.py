
from django.conf.urls import patterns, url
from django.contrib.auth.decorators import login_required

from zovizo.views import Profile

urlpatterns = patterns(
    '',
    url(r'^profile/$', login_required(Profile.as_view()), name='profile'),
)
