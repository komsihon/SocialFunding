from django.conf.urls import patterns, include, url
from django.contrib.auth.decorators import permission_required

from django.contrib import admin
admin.autodiscover()

from ikwen.flatpages.views import FlatPageView
from zovizo.views import Dashboard, Home, About, DrawView

urlpatterns = patterns(
    '',
    url(r'^laakam/', include(admin.site.urls)),

    url(r'^billing/', include('ikwen.billing.urls', namespace='billing')),
    url(r'^rewarding/', include('ikwen.rewarding.urls', namespace='rewarding')),
    url(r'^revival/', include('ikwen.revival.urls', namespace='revival')),
    url(r'^page/(?P<url>[-\w]+)/$', FlatPageView.as_view(), name='flatpage'),

    url(r'^echo/', include('echo.urls', namespace='echo')),
    url(r'^daraja/', include('daraja.urls', namespace='daraja')),

    url(r'^i18n/', include('django.conf.urls.i18n')),
    url(r'^cci/', include('ikwen_kakocase.cci.urls', namespace='cci')),
    url(r'^currencies/', include('currencies.urls')),

    url(r'^ikwen/dashboard/$', permission_required('zovizo.ik_view_dashboard')(Dashboard.as_view()), name='dashboard'),
    url(r'^ikwen/theming/', include('ikwen.theming.urls', namespace='theming')),
    url(r'^ikwen/cashout/', include('ikwen.cashout.urls', namespace='cashout')),
    url(r'^ikwen/', include('ikwen.core.urls', namespace='ikwen')),

    url(r'^about/$', About.as_view(), name='about'),
    url(r'^draw/$', DrawView.as_view(), name='draw'),
    url(r'^', include('zovizo.urls', namespace='zovizo')),
    url(r'^$', Home.as_view(), name='home'),

    # url(r'^$', ProviderDashboard.as_view(), name='admin_home'),
    # url(r'^page/(?P<url>[-\w]+)/$', FlatPageView.as_view(), name='flatpage'),
)
