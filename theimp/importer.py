import datetime
from django.core.cache import get_cache
import logging
import os.path
import re

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models.loading import get_model
from django.template.defaultfilters import slugify
from django.utils import timezone

from theimp.models import Vendor, Product
from theimp.utils import ProductItem, get_site_product_hash


logger = logging.getLogger(__name__)

cache = get_cache("importer")

class SiteImportError(Exception):
    pass


class Importer(object):
    imported_cache_key = "imported_{id}"

    def __init__(self, site_queue=None):
        self.site_product_model = get_model('apparel', 'Product')
        self.site_vendor_product_model = get_model('apparel', 'VendorProduct')
        self.site_option_model = get_model('apparel', 'Option')
        self.site_brand_model = get_model('apparel', 'Brand')
        self.site_category_model = get_model('apparel', 'Category')

        self.option_types = dict([(re.sub(r'\W', '', v.name.lower()), v) for v in get_model('apparel', 'OptionType').objects.iterator()])

    def run(self, dry=False, vendor=None,force=None):
        vendors = Vendor.objects.filter(vendor__isnull=False)
        request_links = []
        if vendor is not None:
            vendors = vendors.filter(name=vendor)

        for vendor in vendors.iterator():
            imported_date = None
            product_queryset = Product.objects.filter(vendor=vendor)
            if vendor.last_imported_date and not force:
                # Fetch all products that has been updated since the last vendor.imported date.
                product_queryset = product_queryset.filter(parsed_date__gte=vendor.last_imported_date)
            logger.info(u'Import {count} products for vendor {vendor}'.format(count=product_queryset.count(), vendor=vendor))
            for product_id in product_queryset.values_list('pk', flat=True):
                try:
                    product = Product.objects.get(pk=product_id)
                except Product.DoesNotExist as e:
                    logger.exception(u'Could not load product with id {id}'.format(id=product_id,))
                    continue

                if not dry:
                    logger.debug(u'Import product {key} [valid = {valid}]'.format(key=product.key, valid=product.is_validated))
                    try:
                        with transaction.atomic():
                            imported_date = self.site_import(product, product.is_validated)
                    except (SiteImportError, IntegrityError) as e:
                        logger.exception(u'Could not import product with id {id}'.format(id=product_id,))
                        continue

            # Run through all products and set new values. Reason I suspect we iterate through every product is to trigger save signals in django
            # which in turn trigger other things. Todo: Look at making this more effective
            yesterday = timezone.now() - datetime.timedelta(hours=48)
            for product_id in self.site_product_model.objects.filter(vendors=vendor.vendor_id, availability=True, modified__lte=yesterday).values_list('id', flat=True):
                logger.debug(u'Setting availability to false for product with id {id} due to the item has not been imported since {yday} or later [{vendor}]'.
                             format(id=product_id, yday=yesterday, vendor=vendor))
                if not dry:
                    product = self.site_product_model.objects.get(pk=product_id)
                    product.availability=False
                    product.vendorproduct.update(availability=0)
                    product.save()

            if imported_date and not dry:
                vendor.last_imported_date = imported_date
                vendor.save()

    def site_import(self, product, is_valid):
        import datetime

        # Convert into ProductItem = bundle of dicts
        item = ProductItem(product)

        # Get corresponding apparel.Product object
        site_product = self._find_site_product(item)
        if is_valid:
            if site_product:
                updated = self.update_product(product, item, site_product)
                logger.info("Product {name} {id} update was written to disk: {update_completed}".
                                                                                format(name=site_product.product_name,
                                                                                    id=site_product.id,
                                                                                    update_completed=updated))
                if not updated:
                    site_product.modified = datetime.datetime.now()
                    site_product.save(update_fields=["modified"])
            else:
                site_product = self.add_product(product, item)
        else:
            if site_product:
                logger.info('Hiding product %s' % site_product)
                self.hide_product(site_product)

        # This is always done now, not necessary unless something changes.
        # Added check if there is a site key already set
        if is_valid and site_product and item.get_site_product() is None :
            item.set_site_product(site_product.pk)
            item.save()

        product.imported_date = timezone.now()
        product.save()

        return product.imported_date

    # TODO: might be a problem when adding new products that the solr update
    # code wont be able to handle it and the product will actually be picked up
    # in solr on update_product call the next day
    def add_product(self, product, item):
        brand = product.brand_mapping
        if not brand:
            raise SiteImportError('invalid brand mapping')

        category = product.category_mapping
        if not category:
            raise SiteImportError('invalid category mapping')

        site_product = self.site_product_model.objects.create(
            product_key = item.get_scraped('key'),
            product_name = item.get_final('name'),
            description = item.get_final('description'),
            category_id = category.mapped_category_id,
            manufacturer_id = brand.mapped_brand_id,
            sku = item.get_final('sku'),
            static_brand = item.get_final('brand'),
            gender = item.get_final('gender'),
            availability = bool(item.get_final('in_stock', False)),
            product_image = self._product_image(item)
        )

        self._update_vendor_product(item, site_product)
        self._update_product_options(item, site_product)

        return site_product

    def update_product(self, product, item, site_product):
        brand = product.brand_mapping
        if not brand:
            raise SiteImportError('invalid brand mapping')

        category = product.category_mapping
        if not category:
            raise SiteImportError('invalid category mapping')

        site_product.product_name = item.get_final('name')
        site_product.product_key = item.get_scraped('key')
        site_product.description = item.get_final('description')
        site_product.category_id = category.mapped_category_id
        site_product.manufacturer_id = brand.mapped_brand_id
        site_product.sku = item.get_final('sku')
        site_product.static_brand = item.get_final('brand')
        site_product.gender = item.get_final('gender')
        site_product.availability = bool(item.get_final('in_stock', False))
        site_product.product_image = self._product_image(item)

        imported_hash = get_site_product_hash(site_product, **item.data[ProductItem.KEY_FINAL])
        previous_hash = cache.get(self.imported_cache_key.format(id=site_product.id))
        if not imported_hash == previous_hash:
            cache.set(self.imported_cache_key.format(id=site_product.id), imported_hash, 3600*24*90)
            site_product.save()
            self._update_vendor_product(item, site_product)
            self._update_product_options(item, site_product)
            return True
        else:
            #logger.info("{} - {}".format(imported_hash, previous_hash))
            logger.info("Not updating product {id}, since product is the same.".format(id=site_product.id))
        return False

    def hide_product(self, site_product):
        site_product.availability = False
        for vendor_product in site_product.vendorproduct.all():
            vendor_product.availability = 0
            vendor_product.save()
        site_product.save()


    #
    # HELPERS
    #

    def _product_image(self, item):
        return os.path.join(settings.APPAREL_PRODUCT_IMAGE_ROOT, item.get_final('images')[0]['path'])

    def _update_product_options(self, item, site_product):
        for product_option in ['colors', 'patterns']:
            product_option_values = item.get_final(product_option)
            if product_option_values:
                for product_option_value in product_option_values:
                    # Option type name is singular
                    option_type = self.option_types.get(product_option[:-1])
                    if option_type:
                        option, created = self.site_option_model.objects.get_or_create(option_type=option_type, value=product_option_value)
                        if not site_product.options.filter(pk=option.pk).exists():
                            site_product.options.add(option)

    def _update_vendor_product(self, item, site_product):
        vendor = Vendor.objects.get(name=item.get_final('vendor'))
        vendor_product, _ = self.site_vendor_product_model.objects.get_or_create(product=site_product,
                                                                                 vendor_id=vendor.vendor_id)

        vendor_product.buy_url = item.get_final('url')
        vendor_product.original_price = item.get_final('regular_price') or '0.0'
        vendor_product.original_currency = item.get_final('currency')
        vendor_product.original_discount_price = item.get_final('discount_price')
        vendor_product.original_discount_currency = item.get_final('currency')
        stock = item.get_final('stock')
        if not stock:
            stock = -1
        vendor_product.availability = 0 if not bool(item.get_final('in_stock', False)) else stock
        # XXX: price, currency and discount_price should not be used, WHY???
        #vendor_product.price = item.get_final('regular_price') or '0.0'
        #vendor_product.currency = item.get_final('currency')
        #vendor_product.discount_price = item.get_final('discount_price')
        vendor_product.save()

    def _find_site_product(self, item):
        """
        Find a product on the live site by slug or explicit mapping.
        """
        site_product_pk = item.get_site_product()
        if site_product_pk:
            try:
                return self.site_product_model.objects.get(pk=site_product_pk)
            except self.site_product_model.DoesNotExist:
                item.set_site_product(None)

        static_brand = item.get_final('brand')
        sku = item.get_final('sku')
        try:
            return self.site_product_model.objects.get(static_brand=static_brand, sku=sku)
        except self.site_product_model.DoesNotExist:
            pass

        return None
