from modeltranslation.translator import translator, TranslationOptions
from django.db.models.loading import get_model
from django.contrib.auth import get_user_model


class CategoryTranslationOptions(TranslationOptions):
    fields = ('name', 'name_order', 'singular_name')


class UserTranslationOptions(TranslationOptions):
    fields = ('manual_about',)


translator.register(get_model('apparel', 'Category'), CategoryTranslationOptions)
translator.register(get_user_model(), UserTranslationOptions)
