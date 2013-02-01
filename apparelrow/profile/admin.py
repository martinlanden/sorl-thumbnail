from django.contrib import admin

from profile.models import ApparelProfile
from profile.models import Follow
from profile.models import NotificationCache
from profile.models import PaymentDetail


class ApparelProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'brand', 'slug', 'is_brand', 'language', 'followers_count', 'popularity')
    list_filter = ('is_brand', 'is_partner')
    search_fields = ('name',)
    raw_id_fields = ('user', 'brand')

admin.site.register(ApparelProfile, ApparelProfileAdmin)


admin.site.register(NotificationCache)


class FollowAdmin(admin.ModelAdmin):
    readonly_fields = ('created', 'modified')
    raw_id_fields = ['user', 'user_follow']
    list_display = ('user', 'user_follow', 'created', 'modified', 'active')
    list_filter = ('active',)

admin.site.register(Follow, FollowAdmin)


class PaymentDetailAdmin(admin.ModelAdmin):
    list_display = ('custom_user', 'name', 'company', 'orgnr', 'clearingnr', 'banknr')
    raw_id_fields = ('user',)

    def custom_user(self, obj):
        return u'%s' % (obj.user.get_profile().display_name,)

admin.site.register(PaymentDetail, PaymentDetailAdmin)
