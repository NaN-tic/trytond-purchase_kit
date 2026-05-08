# This file is part purchase_kit module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.modules.company.tests import CompanyTestMixin
from trytond.tests.test_tryton import ModuleTestCase


class PurchaseKitTestCase(CompanyTestMixin, ModuleTestCase):
    'Test Purchase Kit module'
    module = 'purchase_kit'

del ModuleTestCase
