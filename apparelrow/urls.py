from django.conf.urls.defaults import patterns, url, include, handler404, handler500
from django.conf import settings

from django.views.generic.simple import direct_to_template

from django.contrib import admin
admin.autodiscover()

#from account.openid_consumer import PinaxConsumer

#if settings.ACCOUNT_OPEN_SIGNUP:
#    signup_view = "account.views.signup"
#else:
#    signup_view = "signup_codes.views.signup"

urlpatterns = patterns('',
#    url(r'^admin/invite_user/$', 'signup_codes.views.admin_invite_user', name="admin_invite_user"),
#    url(r'^account/signup/$', signup_view, name="acct_signup"),
    
#    (r'^about/', include('about.urls')),
    
    (r'^jsi18n/$', 'django.views.i18n.javascript_catalog', { 'domain': 'djangojs', 'packages': ('apparelrow',),}), 
    # FIXME: Is it possible to include this in some other way? All I want to do
    # is to pass the next_page attribute (and not do it via query)
    (r'^accounts/',         include('registration.backends.default.urls')),
    
    (r'^profile/', include('profile.urls')),
    (r'^watcher/', include('watcher.urls')),
    
    (r'^announcements/', include('announcements.urls')),
    (r'^scale/', include('scale.urls')),
    (r'^comments/', include('django.contrib.comments.urls')),
    (r'^ping/', include('trackback.urls')),
    ('^activity/', include('actstream.urls')),
    (r'^i18n/setlang/$', 'apparel.views.apparel_set_language'), # override builtin set_language
    (r'^i18n/', include('django.conf.urls.i18n')),
    (r'^admin/', include(admin.site.urls)),
    (r'^tinymce/', include('tinymce.urls')),
    (r'^media/(?P<path>.*)$', 'django.views.static.serve', { 'document_root': settings.STATIC_ROOT } ),
    
    (r'', include('apparel.urls')),
    (r'^beta/', include('beta.urls')),

    (r'^search/manufacturer/', 'apparelrow.search.manufacturer_search'),
    (r'^search/(?P<model>\w+)/', 'apparelrow.search.search_view'),
    (r'^s/', include('statistics.urls')),
    # Override facebook
    #(r'^facebook/', include('django_facebook.urls')),
    url(r'^facebook/login', 'apparelrow.profile.views.login', name='facebook_login'),
)


