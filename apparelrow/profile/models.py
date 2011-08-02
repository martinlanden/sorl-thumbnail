import uuid
import os.path

from django.db import models
from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.utils.translation import get_language, ugettext_lazy as _
from django.conf import settings
from django_facebook.models import FacebookProfile

from apparel.models import Look, LookLike, ProductLike

EVENT_CHOICES = (
    ('A', _('All')),
    ('F', _('Those I follow')),
    ('N', _('No one')),
)

def profile_image_path(instance, filename):
    return os.path.join(settings.APPAREL_PROFILE_IMAGE_ROOT, uuid.uuid4().hex)

class ApparelProfile(models.Model):
    user = models.ForeignKey(User, unique=True)
    
    name  = models.CharField(max_length=50, unique=True, blank=True, null=True)
    image = models.ImageField(upload_to=profile_image_path, help_text=_('User profile image'), blank=True, null=True) 
    about = models.TextField(_('About'), null=True, blank=True)

    # notification settings
    comment_product_wardrobe = models.CharField(max_length=1, choices=EVENT_CHOICES, default='F',
            help_text=_('When someone commented on a product that I have in my wardrobe'))
    comment_product_comment = models.CharField(max_length=1, choices=EVENT_CHOICES, default='F',
            help_text=_('When someone commented on a product that I have commented on'))
    comment_look_created = models.CharField(max_length=1, choices=EVENT_CHOICES, default='F',
            help_text=_('When someone commented on a look that I have created'))
    comment_look_comment = models.CharField(max_length=1, choices=EVENT_CHOICES, default='F',
            help_text=_('When someone commented on a look that I have commented on'))
    like_look_created = models.CharField(max_length=1, choices=EVENT_CHOICES, default='F',
            help_text=_('When someone likes a look that I have created'))
    follow_user = models.CharField(max_length=1, choices=EVENT_CHOICES, default='F',
            help_text=_('When someone starts to follow me'))

    @models.permalink
    def get_looks_url(self):
        return ('looks_by_user', [str(self.user.username)])

    # FIXME: Extract number of looks and and likes

    @property
    def looks(self):
        # Number of looks
        return Look.objects.filter(user=self.user).count()
    
    @property
    def likes(self):
        # Number of likes on products and looks combined
        return LookLike.objects.filter(user=self.user).count() + ProductLike.objects.filter(user=self.user).count()

    @property
    def display_name(self):
        if self.name is not None:
            return self.name
        
        if self.user.first_name:
            return u'%s %s' % (self.user.first_name, self.user.last_name)
         
        return u'%s' % self.user

    @property
    def avatar(self):
        if self.image:
            return '/scale/50x50%s?crop=true' % self.image

        if self.facebook_profile:
            return 'http://graph.facebook.com/%s/picture?type=square' % self.facebook_profile.uid

        return settings.APPAREL_DEFAULT_AVATAR

    @property
    def avatar_medium(self):
        if self.image:
            return '/scale/125%s' % self.image

        if self.facebook_profile:
            return 'http://graph.facebook.com/%s/picture?type=small' % self.facebook_profile.uid

        return settings.APPAREL_DEFAULT_AVATAR

    @property
    def avatar_large(self):
        if self.image:
            return '/scale/200%s' % self.image

        if self.facebook_profile:
            return 'http://graph.facebook.com/%s/picture?type=large' % self.facebook_profile.uid

        return settings.APPAREL_DEFAULT_AVATAR_LARGE

    @property
    def facebook_profile(self):
        try:
            return FacebookProfile.objects.get(user=self.user)
        except FacebookProfile.DoesNotExist:
            return None

    @models.permalink
    def get_absolute_url(self):
        return ('profile.views.profile', [str(self.user.username)])
    
    def __unicode__(self):
        return self.display_name

def create_profile(signal, instance, **kwargs):
    if kwargs['created']:
        p, created = ApparelProfile.objects.get_or_create(user=instance)

def create_profile_from_facebook(signal, instance, **kwargs):
    if kwargs['created']:
        fb_properties = {
            'name': instance.name,
            'about': instance.bio,
        }
        p, created = ApparelProfile.objects.get_or_create(user=instance.user, defaults=fb_properties)

        if not created:
            p.name = instance.name
            p.about = instance.bio
            p.save()

post_save.connect(create_profile, sender=User)
post_save.connect(create_profile_from_facebook, sender=FacebookProfile)
