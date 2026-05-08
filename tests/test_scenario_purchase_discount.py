import unittest
from decimal import Decimal

from proteus import Model, Wizard
from trytond.modules.account.tests.tools import (
    create_chart, create_fiscalyear, create_tax, get_accounts)
from trytond.modules.account_invoice.tests.tools import (
    create_payment_term, set_fiscalyear_invoice_sequences)
from trytond.modules.company.tests.tools import create_company, get_company
from trytond.tests.test_tryton import drop_db
from trytond.tests.tools import activate_modules


class Test(unittest.TestCase):

    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):
        activate_modules(['purchase_kit', 'purchase_discount'])

        _ = create_company()
        company = get_company()

        fiscalyear = set_fiscalyear_invoice_sequences(
            create_fiscalyear(company))
        fiscalyear.click('create_period')

        _ = create_chart(company)
        accounts = get_accounts(company)
        revenue = accounts['revenue']
        expense = accounts['expense']

        tax = create_tax(Decimal('.10'))
        tax.save()

        Party = Model.get('party.party')
        supplier = Party(name='Supplier')
        supplier.save()

        ProductCategory = Model.get('product.category')
        account_category = ProductCategory(name='Account Category')
        account_category.accounting = True
        account_category.account_expense = expense
        account_category.account_revenue = revenue
        account_category.supplier_taxes.append(tax)
        account_category.save()

        ProductUom = Model.get('product.uom')
        unit, = ProductUom.find([('name', '=', 'Unit')])
        meter, = ProductUom.find([('name', '=', 'Meter')])
        ProductTemplate = Model.get('product.template')
        ProductKitLine = Model.get('product.kit.line')
        ProductSupplier = Model.get('purchase.product_supplier')
        ProductSupplierPrice = Model.get('purchase.product_supplier.price')

        tkit1 = ProductTemplate()
        tkit1.name = 'product 1'
        tkit1.default_uom = unit
        tkit1.type = 'goods'
        tkit1.purchasable = True
        tkit1.list_price = Decimal('10')
        tkit1.cost_price_method = 'fixed'
        tkit1.account_category = account_category
        pkit1, = tkit1.products
        pkit1.cost_price = Decimal('5')
        tkit1.save()
        pkit1, = tkit1.products

        tkit2 = ProductTemplate()
        tkit2.name = 'product 2'
        tkit2.default_uom = unit
        tkit2.type = 'goods'
        tkit2.purchasable = True
        tkit2.list_price = Decimal('10')
        tkit2.cost_price_method = 'fixed'
        tkit2.account_category = account_category
        pkit2, = tkit2.products
        pkit2.cost_price = Decimal('5')
        tkit2.save()
        pkit2, = tkit2.products

        tkit3 = ProductTemplate()
        tkit3.name = 'product 3'
        tkit3.default_uom = meter
        tkit3.type = 'goods'
        tkit3.purchasable = True
        tkit3.list_price = Decimal('10')
        tkit3.cost_price_method = 'fixed'
        tkit3.account_category = account_category
        pkit3, = tkit3.products
        pkit3.cost_price = Decimal('5')
        tkit3.save()
        pkit3, = tkit3.products

        template = ProductTemplate()
        template.name = 'kit'
        template.default_uom = unit
        template.type = 'goods'
        template.purchasable = True
        template.list_price = Decimal('10')
        template.cost_price_method = 'fixed'
        template.account_category = account_category
        product, = template.products
        product.cost_price = Decimal('5')
        product.kit = True
        product.explode_kit_in_purchases = True
        template.save()
        product, = template.products

        pkit_line1 = ProductKitLine()
        product.kit_lines.append(pkit_line1)
        pkit_line1.product = pkit1
        pkit_line1.quantity = 1
        pkit_line2 = ProductKitLine()
        product.kit_lines.append(pkit_line2)
        pkit_line2.product = pkit2
        pkit_line2.quantity = 1
        pkit_line3 = ProductKitLine()
        product.kit_lines.append(pkit_line3)
        pkit_line3.product = pkit3
        pkit_line3.quantity = 1
        product.save()

        product_supplier = ProductSupplier()
        product_supplier.template = template
        product_supplier.party = supplier
        product_supplier_price = ProductSupplierPrice()
        product_supplier.prices.append(product_supplier_price)
        product_supplier_price.sequence = 1
        product_supplier_price.quantity = Decimal('1.0')
        product_supplier_price.unit_price = Decimal('5')
        product_supplier.save()

        payment_term = create_payment_term()
        payment_term.save()

        Purchase = Model.get('purchase.purchase')
        PurchaseLine = Model.get('purchase.line')
        purchase = Purchase()
        purchase.party = supplier
        purchase.payment_term = payment_term
        purchase.invoice_method = 'order'
        purchase_line = PurchaseLine()
        purchase.lines.append(purchase_line)
        purchase_line.product = product
        purchase_line.quantity = 2.0
        self.assertEqual(purchase_line.base_price, purchase_line.unit_price)
        purchase_line.discount_rate = Decimal('0.1')
        self.assertEqual(purchase_line.base_price, Decimal('5.0000'))
        self.assertEqual(purchase_line.unit_price, Decimal('4.5000'))
        purchase.save()
        purchase.click('quote')
        self.assertEqual(len(purchase.lines), 4)

        line1, line2, line3, line4 = purchase.lines
        self.assertEqual(line1.kit_depth, 0)
        self.assertEqual(line2.kit_depth, 1)
        self.assertEqual(line3.kit_depth, 1)
        self.assertEqual(line4.kit_depth, 1)
        self.assertTrue(line1.product.kit)
        self.assertEqual(line1.base_price, Decimal('5.0000'))
        self.assertEqual(line1.unit_price, Decimal('4.5000'))
        self.assertEqual(line2.base_price, Decimal('0.0'))
        self.assertEqual(line2.unit_price, Decimal('0.0'))
        self.assertEqual(line3.base_price, Decimal('0.0'))
        self.assertEqual(line3.unit_price, Decimal('0.0'))
        self.assertEqual(line4.base_price, Decimal('0.0'))
        self.assertEqual(line4.unit_price, Decimal('0.0'))

        return_purchase = Wizard('purchase.return_purchase', [purchase])
        return_purchase.execute('return_')
        returned_purchase, = Purchase.find([
            ('state', '=', 'draft'),
            ])
        self.assertEqual(len(returned_purchase.lines), 4)

        line1, line2, line3, line4 = returned_purchase.lines
        self.assertTrue(line1.product.kit)
        self.assertEqual(line1.base_price, Decimal('5.0000'))
        self.assertEqual(line1.unit_price, Decimal('4.5000'))
        self.assertEqual(line2.base_price, Decimal('0.0'))
        self.assertEqual(line2.unit_price, Decimal('0.0'))
        self.assertEqual(line3.base_price, Decimal('0.0'))
        self.assertEqual(line3.unit_price, Decimal('0.0'))
        self.assertEqual(line4.base_price, Decimal('0.0'))
        self.assertEqual(line4.unit_price, Decimal('0.0'))
