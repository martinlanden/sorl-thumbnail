from django.core.urlresolvers import reverse
from django.contrib.auth import get_user_model
from django.contrib.sitemaps import Sitemap, FlatPageSitemap, GenericSitemap
from django.db.models import get_model

class LimitGenericSitemap(GenericSitemap):
    limit = 2000

class ViewSitemap(Sitemap):
    changefreq = 'daily'
    priority = 0.8

    def items(self):
        return ['brand-list-men', 'brand-list-women',
                'look-list-men', 'look-list-women',
                'shop-men', 'shop-women',
                'user-list-men', 'user-list-women']

    def location(self, item):
        return reverse(item)

product_info = {'queryset': get_model('apparel', 'Product').published_objects.order_by('-popularity')[:1000], 'date_field': 'modified'}
look_info = {'queryset': get_model('apparel', 'Look').published_objects.order_by('pk'), 'date_field': 'modified'}
profile_info = {'queryset': get_user_model().objects.filter(is_active=True, is_brand=False)}
brand_info = {'queryset': get_user_model().objects.filter(is_active=True, is_brand=True).order_by('-followers_count')[:100]}

sitemaps = {
    'flatpages': FlatPageSitemap,
    'views': ViewSitemap,
    'product': LimitGenericSitemap(product_info, priority=0.6, changefreq='daily'),
    'look': LimitGenericSitemap(look_info, priority=0.9, changefreq='daily'),
    'user': LimitGenericSitemap(profile_info, priority=0.7, changefreq='daily'),
    'brand': LimitGenericSitemap(brand_info, priority=0.7, changefreq='daily'),
}
