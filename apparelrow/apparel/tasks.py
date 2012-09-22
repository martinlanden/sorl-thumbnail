import logging
import datetime
import unicodedata
import os
import os.path
import string

from django.core.management import call_command
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.encoding import smart_unicode
from mailsnake import MailSnake
from mailsnake.exceptions import MailSnakeException
from celery.task import task, periodic_task, PeriodicTask
from celery.schedules import crontab
import requests

from apparel.search import ApparelSearch
from apparel.models import Product, VendorBrand, VendorCategory, FacebookAction
from profile.models import ApparelProfile

logger = logging.getLogger('apparel.tasks')

@task(name='apparel.email.mailchimp_subscribe', max_retries=5, ignore_result=True)
def mailchimp_subscribe(user):
    try:
        mailchimp = MailSnake(settings.MAILCHIMP_API_KEY)
        mailchimp.listSubscribe(id=settings.MAILCHIMP_NEWSLETTER_LIST,
                                email_address=user.email,
                                merge_vars={'EMAIL': user.email, 'FNAME': user.first_name, 'LNAME': user.last_name, 'GENDER': user.get_profile().gender},
                                double_optin=False,
                                update_existing=True,
                                send_welcome=False)
        mailchimp.listSubscribe(id=settings.MAILCHIMP_MEMBER_LIST,
                                email_address=user.email,
                                merge_vars={'EMAIL': user.email, 'FNAME': user.first_name, 'LNAME': user.last_name, 'GENDER': user.get_profile().gender},
                                double_optin=False,
                                update_existing=True,
                                send_welcome=False)
    except MailSnakeException, e:
        logger.error('Could not subscribe user to mailchimp: %s' % (e,))

@task(name='apparel.email.mailchimp_unsubscribe', max_retries=5, ignore_result=True)
def mailchimp_unsubscribe(user, delete=False):
    try:
        mailchimp = MailSnake(settings.MAILCHIMP_API_KEY)
        mailchimp.listUnsubscribe(id=settings.MAILCHIMP_NEWSLETTER_LIST,
                                  email_address=user.email,
                                  delete_member=delete,
                                  send_goodbye=False,
                                  send_notify=False)
        if delete:
            mailchimp.listUnsubscribe(id=settings.MAILCHIMP_MEMBER_LIST,
                                      email_address=user.email,
                                      delete_member=delete,
                                      send_goodbye=False,
                                      send_notify=False)
    except MailSnakeException, e:
        logger.error('Could not unsubscribe user from mailchimp: %s' % (e,))


ACTION_TRANSLATION = {'like': 'og.likes', 'follow': 'og.follows', 'create': '%s:create' % (settings.FACEBOOK_OG_TYPE,)}

@task(name='apparel.facebook_push_graph', max_retries=5, ignore_result=True)
def facebook_push_graph(user_id, access_token, action, object_type, object_url):
    url = 'https://graph.facebook.com/me/%s' % (ACTION_TRANSLATION[action],)
    response = requests.post(url, data={object_type: object_url, 'access_token': access_token})
    data = response.json

    logger.info(data)

    if 'id' in data:
        FacebookAction.objects.get_or_create(user_id=user_id, action=action, action_id=data['id'], object_type=object_type, object_url=object_url)
    elif 'error' in data and data['error']['code'] == 2:
        facebook_push_graph.retry(countdown=15)

@task(name='apparel.facebook_pull_graph', max_retries=1, ignore_result=True)
def facebook_pull_graph(user_id, access_token, action, object_type, object_url):
    try:
        facebook_action = FacebookAction.objects.get(user_id=user_id, action=action, object_type=object_type, object_url=object_url)
        facebook_action.delete()
        url = 'https://graph.facebook.com/%s' % (facebook_action.action_id,)
        response = requests.delete(url, data={'access_token': access_token})
        logger.info(response.json)
    except FacebookAction.DoesNotExist:
        logger.warning('No facebook action_id found for uid=%s action=%s type=%s' % (user_id, action, object_type))


# XXX: offline
#@periodic_task(name='apparel.tasks.update_vendor_data', run_every=crontab(minute='0,15,30,45'), max_retries=1, ignore_result=True)
def update_vendor_data():
    """
    Updates vendor data every half hour.
    """
    timestamp = datetime.datetime.now() - datetime.timedelta(minutes=20)
    for vendor_brand in VendorBrand.objects.filter(modified__gt=timestamp).iterator():
        if vendor_brand.brand:
            for product in Product.objects.filter(vendorproduct__vendor_brand_id=vendor_brand.id).iterator():
                if product.manufacturer_id != vendor_brand.brand_id:
                    product.manufacturer_id = vendor_brand.brand_id
                    product.save()
        else:
            queryset = Product.objects.filter(vendorproduct__vendor_brand_id=vendor_brand.id, manufacturer__isnull=False)
            for product in queryset:
                product.manufacturer_id = None
                product.save()

    for vendor_category in VendorCategory.objects.filter(modified__gt=timestamp).iterator():
        if vendor_category.category:
            queryset = Product.objects.filter(vendorproduct__vendor_category=vendor_category)
            for product in queryset:
                product.category = self.category
                product.published = True
                product.save()
        else:
            queryset = Product.objects.filter(vendorproduct__vendor_category=vendor_category, category__isnull=False)
            for product in queryset:
                product.category = None
                product.save()

@periodic_task(name='apparel.tasks.generate_brand_list_template', run_every=crontab(minute='4,19,34,49'), max_retries=1, ignore_result=True)
def generate_brand_list_template():
    for gender in ['M', 'W']:
        alphabet = [u'0-9'] + list(unicode(string.ascii_lowercase))
        brands = []
        brands_mapper = {}
        for index, alpha in enumerate(alphabet):
            brands_mapper[alpha] = index
            brands.append([alpha, []])

        query_arguments = {'fl': 'manufacturer_id',
                           'fq': ['django_ct:apparel.product', 'availability:true', 'published:true', 'gender:(U OR %s)' % (gender,)],
                           'start': 0,
                           'rows': -1,
                           'group': 'true',
                           'group.field': 'manufacturer_id'}
        brand_ids = []
        for brand in ApparelSearch('*:*', **query_arguments).get_docs():
            if hasattr(brand, 'manufacturer_id'):
                brand_ids.append(brand.manufacturer_id)

        for item in ApparelProfile.objects.filter(brand__id__in=brand_ids).values('slug', 'brand__name').order_by('brand__name'):
            normalized_name = unicodedata.normalize('NFKD', smart_unicode(item['brand__name'])).lower()
            for index, char in enumerate(normalized_name):
                if char in alphabet:
                    brands[brands_mapper[char]][1].append(item)
                    break
                elif char.isdigit():
                    brands[brands_mapper[u'0-9']][1].append(item)
                    break

        if gender == 'M':
            template_name = 'brand_list_men.html'
            template_temp_name = 'brand_list_men.html.tmp'
        else:
            template_name = 'brand_list_women.html'
            template_temp_name = 'brand_list_women.html.tmp'

        template_string = render_to_string('apparel/brand_list_generator.html', {'brands': brands})
        temp_filename = os.path.join(settings.PROJECT_ROOT, 'templates', 'apparel', 'generated', template_temp_name)
        filename = os.path.join(settings.PROJECT_ROOT, 'templates', 'apparel', 'generated', template_name)
        open(temp_filename, 'w').write(template_string.encode('utf-8'))
        os.rename(temp_filename, filename)

class ProcessPopularityTask(PeriodicTask):
    run_every = crontab(hour=4, minute=15)
    ignore_result = True

    def run(self, **kwargs):
        logger = self.get_logger(**kwargs)
        logger.info('update popularity for products')
        call_command('popularity')

class ProcessLookPopularity(PeriodicTask):
    run_every = crontab(minute='*/30')
    ignore_result = True

    def run(self, **kwargs):
        logger = self.get_logger(**kwargs)
        logger.info('update popularity for looks')
        call_command('look_popularity')
