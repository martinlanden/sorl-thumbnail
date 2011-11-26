from django.conf import settings as django_settings
from django.core.urlresolvers import reverse

from apparel.utils import get_gender_from_cookie

def exposed_settings(request):
    return {
        'CACHE_TIMEOUT': django_settings.CACHE_TEMPLATE_TIMEOUT,
        'DEFAULT_AVATAR': django_settings.APPAREL_DEFAULT_AVATAR,
        'DEFAULT_AVATAR_LARGE': django_settings.APPAREL_DEFAULT_AVATAR_LARGE,
        'GOOGLE_ANALYTICS_ACCOUNT': django_settings.GOOGLE_ANALYTICS_ACCOUNT,
        'GOOGLE_ANALYTICS_DOMAIN': django_settings.GOOGLE_ANALYTICS_DOMAIN,
        'SHORT_LANGUAGES': django_settings.SHORT_LANGUAGES,
    }

def next_redirects(request):
    if reverse('django.contrib.auth.views.logout') == request.path:
        return {
            'next' : '/'
        }
    else:
        return {
            'next' : request.path
        }

def gender(request):
    return {'apparel_gender': get_gender_from_cookie(request)}
