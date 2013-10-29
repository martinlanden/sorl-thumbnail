# -*- coding: utf-8 -*-
import logging
import datetime
import csv
import StringIO
import os
import os.path
import shutil

from django.conf import settings
from django.shortcuts import render_to_response
from django.http import HttpResponse, HttpResponseNotFound
from django.db.models import Q, Count
from django.db.models.signals import pre_save, pre_delete
from django.db.models.loading import get_model
from django.dispatch import receiver
from django.template import RequestContext, loader
from django.utils.translation import activate
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.views.decorators.csrf import csrf_exempt
from django.contrib.staticfiles.storage import staticfiles_storage
from sorl.thumbnail import get_thumbnail
from mailsnake import MailSnake
from mailsnake.exceptions import MailSnakeException

from apparelrow.apparel.tasks import mailchimp_subscribe, mailchimp_unsubscribe

logger = logging.getLogger('apparel.email')


def get_newsletter_users():
    """
    Get an iterator of all users eligible for our (weekly) newsletter.
    """
    return get_user_model().objects.filter(newsletter=True) \
                                   .exclude(Q(email__isnull=True) | Q(email__exact='')) \
                                   .exclude(Q(first_name__isnull=True) | Q(first_name__exact='')) \
                                   .exclude(Q(last_name__isnull=True) | Q(last_name__exact='')) \
                                   .iterator()


def update_subscribers(mailchimp):
    batch = []
    for user in get_newsletter_users():
        batch.append({'EMAIL': user.email,
                      'FNAME': user.first_name,
                      'LNAME': user.last_name,
                      'GENDER': user.gender,
                      'PUBLISHER': int(user.is_partner)})

    mailchimp.listBatchSubscribe(id=settings.MAILCHIMP_NEWSLETTER_LIST, double_optin=False, update_existing=True, batch=batch)


@receiver(pre_save, sender=get_user_model(), dispatch_uid='pre_save_profile_newsletter')
def pre_save_profile_newsletter(sender, instance, **kwargs):
    """
    Update mailchimp list on profile update.
    """
    if not instance.pk:
        return

    old_data = get_user_model().objects.get(pk=instance.pk)
    if old_data.newsletter == instance.newsletter:
        return

    if instance.newsletter:
        mailchimp_subscribe.delay(instance)
    else:
        mailchimp_unsubscribe.delay(instance)

@receiver(pre_delete, sender=get_user_model(), dispatch_uid='pre_delete_profile_newsletter')
def pre_delete_profile_newsletter(sender, instance, **kwargs):
    """
    Update mailchimp list on profile delete.
    """
    mailchimp_unsubscribe.delay(instance, delete=True)

@csrf_exempt
def mailchimp_webhook(request):
    if request.method == 'POST':
        webhook_type = request.POST.get('type', None)
        webhook_email = request.POST.get('data[email]', '')
        if webhook_type == 'subscribe':
            get_user_model().objects.filter(email=webhook_email).update(newsletter=True)
            logger.info('Mailchimp webhook: subscribe %s' % (webhook_email,))
        elif webhook_type == 'unsubscribe':
            get_user_model().objects.filter(email=webhook_email).update(newsletter=False)
            logger.info('Mailchimp webhook: unsubscribe %s' % (webhook_email,))

    return HttpResponse('')

@login_required
def admin_user_list_csv(request):
    if not request.user.is_superuser:
        return HttpResponseNotFound()

    csv_string = StringIO.StringIO()

    writer = csv.writer(csv_string)
    for user in get_newsletter_users():
        writer.writerow([user.email.encode('utf-8'), user.first_name.encode('utf-8'), user.last_name.encode('utf-8')])

    response = HttpResponse(csv_string.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename=apprl-users.csv'

    csv_string.close()

    return response

def get_weekly_mail_content(gender, timeframe):
    """
    Generates the weekly mail content based on gender and timeframe.
    """
    # Make sure that the email image root is created
    directory = os.path.join(settings.MEDIA_ROOT, settings.APPAREL_EMAIL_IMAGE_ROOT)
    if not os.path.exists(directory):
        os.makedirs(directory)

    # Products
    product_names = []
    products = []
    excludes = get_model('apparel', 'ProductUsedWeekly').objects.values_list('product_id', flat=True)
    base_products = list(get_model('apparel', 'Product').valid_objects.filter(gender__in=[gender, 'U'])
                                                                      .exclude(pk__in=excludes)
                                                                      .order_by('-popularity')[:9])
    week_products = list(get_model('apparel', 'Product').valid_objects.filter(gender__in=[gender, 'U'])
                                                                      .filter(likes__active=True, likes__modified__gt=timeframe)
                                                                      .exclude(pk__in=excludes)
                                                                      .annotate(num_likes=Count('likes'))
                                                                      .order_by('-num_likes')[:9])

    used_products = []
    count_products = 0
    for product in week_products + base_products:
        if product.pk not in used_products:
            if product.manufacturer.name not in product_names:
                product_names.append(product.manufacturer.name)
            product_image = get_thumbnail(product.product_image, '176', crop='noop').url
            product_price = u'%.0f %s' % (product.default_vendor.locale_price, product.default_vendor.locale_currency)
            if product.default_vendor.locale_discount_price:
                product_price = u'<span class="discount">%.0f %s</span> <span class="original">%.0f %s</span>' % (product.default_vendor.locale_discount_price, product.default_vendor.locale_currency, product.default_vendor.locale_price, product.default_vendor.locale_currency)

            products.append({
                'pk': product.pk,
                'url': ''.join(['http://', Site.objects.get_current().domain, product.get_absolute_url()]),
                'image': product_image,
                'name': product.manufacturer.name,
                'text': product_price
            })

            count_products = count_products + 1
            used_products.append(product.pk)

        if count_products >= 9:
            break

    product_names = product_names[:5]
    subject = u'%s and more trending this week!' % (', '.join(product_names),)

    # Looks
    looks = []
    base_looks = list(get_model('apparel', 'Look').published_objects.filter(gender__in=[gender, 'U'], likes__active=True).annotate(num_likes=Count('likes')).order_by('-num_likes', '-modified')[:4])
    week_looks = list(get_model('apparel', 'Look').published_objects.filter(gender__in=[gender, 'U'], likes__active=True, likes__modified__gt=timeframe).annotate(num_likes=Count('likes')).order_by('-num_likes', '-modified')[:4])

    used_looks = []
    count_looks = 0
    for look in week_looks + base_looks:
        if look.pk not in used_looks:
            look_class = 'photo' if look.display_with_component == 'P' else 'collage'
            looks.append({
                'class': look_class,
                'url': ''.join(['http://', Site.objects.get_current().domain, look.get_absolute_url()]),
                'image': get_thumbnail(look.static_image, '576', crop='noop').url,
                'name': look.title,
                'user_url': ''.join(['http://', Site.objects.get_current().domain, look.user.get_absolute_url()]),
                'user_name': look.user.display_name,
            })

            count_looks = count_looks + 1
            used_looks.append(look.pk)

        if count_looks >= 4:
            break

    # Members
    members = []
    base_members = list(get_user_model().objects.filter(gender=gender).order_by('-followers_count').values_list('id', flat=True)[:4])
    temp_week_members = list(get_model('profile', 'Follow').objects.filter(modified__gt=timeframe)
                                                                   .values_list('user_follow', flat=True)
                                                                   .annotate(count=Count('user_follow'))
                                                                   .order_by('-count'))

    week_members = []
    count_week_members = 0
    for user_id in temp_week_members:
        profile = get_user_model().objects.get(pk=user_id)
        if profile.gender == gender:
            week_members.append(user_id)
            count_week_members = count_week_members + 1

        if count_week_members >= 4:
            break

    used_members = []
    count_members = 0
    for member_id in week_members + base_members:
        if member_id not in used_members:
            profile = get_user_model().objects.get(pk=member_id)

            avatar = profile.avatar_medium
            if not avatar.startswith('http://') and not avatar.startswith('https://'):
                avatar = ''.join(['http://', Site.objects.get_current().domain, avatar])

            members.append({
                'url': ''.join(['http://', Site.objects.get_current().domain, profile.get_absolute_url()]),
                'image': avatar,
                'name': profile.display_name,
                'text': u'Följs av %s' % (profile.followers_count,)
            })

            count_members = count_members + 1
            used_members.append(member_id)

        if count_members >= 4:
            break

    return (subject, products, looks, members)


@login_required
def generate_weekly_mail(request):
    if not request.user.is_superuser:
        return HttpResponseNotFound()

    if request.GET.get('create') == 'yes':
        mailchimp = MailSnake(settings.MAILCHIMP_API_KEY)

        try:
            update_subscribers(mailchimp)
        except MailSnakeException, e:
            return HttpResponse('Error: could not update subscribers list: %s' % (str(e),))

        message = []
        for gender in ['M', 'W']:
            one_week_ago = datetime.datetime.now() - datetime.timedelta(weeks=1)
            subject, products, looks, members = get_weekly_mail_content(gender, one_week_ago)

            template = loader.render_to_string('email/weekly.html', {
                'products': products,
                'products_1': products[0:3],
                'products_2': products[3:6],
                'products_3': products[6:9],
                'looks': looks,
                'members': members,
                'email_weekly_top': request.build_absolute_uri(staticfiles_storage.url('images/weekly-top-en.gif')),
            })

            text_template = loader.render_to_string('email/weekly.txt')

            options = {
                    'list_id': settings.MAILCHIMP_NEWSLETTER_LIST,
                    'subject': subject,
                    'from_email': 'postman@apprl.com',
                    'from_name': 'Apprl',
                    'to_name': '*|FNAME|*',
                    'inline_css': True,
                    'generate_text': True,
                    'title': '%s - %s' % (datetime.date.today(), gender)
                }

            segment_options = {'match': 'all',
                               'conditions': [{'field': 'GENDER',
                                               'op': 'eq',
                                               'value': gender}]}

            try:
                result = mailchimp.campaignCreate(type='regular', options=options, content={'html': template, 'text': text_template}, segment_opts=segment_options)
            except MailSnakeException, e:
                return HttpResponse('Error [%s]: could not create campaign: %s' % (gender, e))

            message.append(result)

            # Mail campaign was created set products as used
            for product in products:
                get_model('apparel', 'ProductUsedWeekly').objects.create(product_id=product['pk'])


        return HttpResponse('Created two campaigns: %s' % (', '.join(message),))

    # Bad solution to force templatetag 'now' to use english date
    activate('en')

    one_week_ago = datetime.datetime.now() - datetime.timedelta(weeks=1)
    subject, products, looks, members = get_weekly_mail_content(request.GET.get('gender', 'M'), one_week_ago)

    return render_to_response('email/weekly.html', {
            'products': products,
            'products_1': products[0:3],
            'products_2': products[3:6],
            'products_3': products[6:9],
            'looks': looks,
            'members': members,
            'email_weekly_top': request.build_absolute_uri(staticfiles_storage.url('images/weekly-top-en.gif')),
        }, context_instance=RequestContext(request))
