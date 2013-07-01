from django.test import TestCase
from django.db.models.loading import get_model

from theimp.parser.modules.build_buy_url import BuildBuyURL


class BuildBuyURLTest(TestCase):
    fixtures = ['initial.json', 'vendors.json']

    def setUp(self):
        self.vendor = get_model('theimp', 'Vendor').objects.create(name='TestVendor')
        self.vendor_aan = get_model('theimp', 'Vendor').objects.create(name='TestAANVendor', affiliate_identifier='test_aan1234')
        self.vendor_zanox = get_model('theimp', 'Vendor').objects.get(name='asos')
        self.vendor_tradedoubler = get_model('theimp', 'Vendor').objects.get(name='nelly')
        self.vendor_linkshare = get_model('theimp', 'Vendor').objects.get(name='net-a-porter')
        self.vendor_cj = get_model('theimp', 'Vendor').objects.get(name='sneakersnstuff')
        self.vendor_aw = get_model('theimp', 'Vendor').objects.get(name='oki_ni')

        self.module = BuildBuyURL(None)

    def test_build_buy_url(self):
        parsed_item = self.module({}, {}, 0)
        self.assertEqual(parsed_item, {})

        parsed_item = self.module({'buy_url': 'http://domain.com/buy_url/'}, {}, 0)
        self.assertEqual(parsed_item.get('buy_url'), 'http://domain.com/buy_url/')

    def test_only_url_parameter(self):
        parsed_item = self.module({'url': 'http://domain.com/normal_url/'}, {}, 0)
        self.assertEqual(parsed_item, {})

    def test_vendor_no_affiliate_identifier(self):
        parsed_item = self.module({'affiliate': None, 'vendor': 'no_affiliate', 'url': 'http://domain.com/normal_url/'}, {}, self.vendor.pk)
        self.assertEqual(parsed_item, {})

    def test_affiliate_aan(self):
        parsed_item = self.module({'affiliate': 'aan', 'vendor': 'TestAANVendor', 'url': 'http://domain.com/normal_url/'}, {}, self.vendor_aan.pk)
        self.assertEqual(parsed_item.get('buy_url'), 'http://apprl.com/a/link/?store_id=test_aan1234&url=http%3A%2F%2Fdomain.com%2Fnormal_url%2F')

    def test_affiliate_zanox(self):
        parsed_item = self.module({'affiliate': 'zanox', 'vendor': 'asos', 'url': 'http://domain.com/normal_url/'}, {}, self.vendor_zanox.pk)
        self.assertEqual(parsed_item.get('buy_url'), 'http://ad.zanox.com/ppc/?25086946C30669136&ulp=[[http%3A%2F%2Fdomain.com%2Fnormal_url%2F]]')

    def test_affiliate_tradedoubler(self):
        parsed_item = self.module({'affiliate': 'tradedoubler', 'vendor': 'nelly', 'url': 'http://domain.com/normal_url/'}, {}, self.vendor_tradedoubler.pk)
        self.assertEqual(parsed_item.get('buy_url'), 'http://clk.tradedoubler.com/click?p=17833&a=1853028&g=17114610&url=http%3A%2F%2Fdomain.com%2Fnormal_url%2F')

    def test_affiliate_linkshare(self):
        parsed_item = self.module({'affiliate': 'linkshare', 'vendor': 'net-a-porter', 'url': 'http://domain.com/normal_url/'}, {}, self.vendor_linkshare.pk)
        self.assertEqual(parsed_item.get('buy_url'), 'http://click.linksynergy.com/deeplink?id=oaQeNCJweO0&mid=24448&murl=http%3A%2F%2Fdomain.com%2Fnormal_url%2F')

    def test_affiliate_cj(self):
        parsed_item = self.module({'affiliate': 'cj', 'vendor': 'sneakersnstuff', 'url': 'http://domain.com/normal_url/'}, {}, self.vendor_cj.pk)
        self.assertEqual(parsed_item.get('buy_url'), 'http://www.anrdoezrs.net/click-4125005-11069203?URL=http%3A%2F%2Fdomain.com%2Fnormal_url%2F')

    def test_affiliate_affiliatewindow(self):
        parsed_item = self.module({'affiliate': 'affiliatewindow', 'vendor': 'oki_ni', 'url': 'http://domain.com/normal_url/'}, {}, self.vendor_aw.pk)
        self.assertEqual(parsed_item.get('buy_url'), 'http://www.awin1.com/pclick.php?p=http%3A%2F%2Fdomain.com%2Fnormal_url%2F&a=115076&m=2083')
