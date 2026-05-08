# This file is part of purchase_kit module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from decimal import Decimal

from trytond.i18n import gettext
from trytond.model import fields
from trytond.model.exceptions import ValidationError
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Bool, Eval
from trytond.transaction import Transaction

STATES = {
    'invisible': Bool(~Eval('kit')),
}


class Product(metaclass=PoolMeta):
    __name__ = 'product.product'

    explode_kit_in_purchases = fields.Boolean(
        'Explode in Purchases', states=STATES)

    @staticmethod
    def default_explode_kit_in_purchases():
        return True

    @staticmethod
    def default_kit_fixed_list_price():
        return True

    @classmethod
    def validate(cls, products):
        super().validate(products)
        for product in products:
            product.check_required_purchasable_products_in_kits()

    def check_required_purchasable_products_in_kits(self):
        KitLine = Pool().get('product.kit.line')

        if not self.kit:
            return

        n_not_purchasable_lines = KitLine.search_count([
                ('parent', '=', self.id),
                ('product.purchasable', '=', False),
                ('parent.explode_kit_in_purchases', '=', True),
                ])
        if n_not_purchasable_lines:
            raise ValidationError(gettext(
                    'purchase_kit.purchasable_product_required_in_kit',
                    product=self.rec_name))

    @classmethod
    def get_purchase_price(cls, products, quantity=0):
        pool = Pool()
        Uom = pool.get('product.uom')
        Company = pool.get('company.company')
        Currency = pool.get('currency.currency')
        Date = pool.get('ir.date')

        context = Transaction().context
        prices = {}

        uom = None
        if context.get('uom'):
            uom = Uom(context['uom'])

        currency = None
        if context.get('currency'):
            currency = Currency(context['currency'])
        elif context.get('company'):
            currency = Company(context['company']).currency
        date = context.get('purchase_date') or Date.today()

        todo_products = set()
        for product in products:
            if not product.kit or product.kit_fixed_list_price:
                todo_products.add(product)
                continue
            if product.explode_kit_in_purchases:
                prices[product.id] = Decimal(0)
                continue

            product_price = Decimal(0)
            for kit_line in product.kit_lines:
                with Transaction().set_context(uom=kit_line.unit.id):
                    price = cls.get_purchase_price(
                        [kit_line.product], quantity=kit_line.quantity)
                    price = price[kit_line.product.id]
                    if price:
                        price *= Decimal(str(kit_line.quantity))
                        product_price += price
            prices[product.id] = product_price

            if uom:
                prices[product.id] = Uom.compute_price(
                    product.default_uom, prices[product.id], uom)
            if currency:
                company = None
                if context.get('company'):
                    company = Company(context['company'])
                if company and company.currency != currency:
                    with Transaction().set_context(date=date):
                        prices[product.id] = Currency.compute(
                            company.currency, prices[product.id], currency,
                            round=False)

        if todo_products:
            prices.update(super().get_purchase_price(todo_products, quantity))
        return prices


class ProductKitLine(metaclass=PoolMeta):
    __name__ = 'product.kit.line'

    def get_purchase_price(self):
        parent = self.parent
        if parent.kit_fixed_list_price:
            return False
        parent_kit_lines = self.search([
                ('product', '=', parent.id),
                ])
        for line in parent_kit_lines:
            if line in [x for x in line.product.kit_lines]:
                return line.get_purchase_price()
        return True

    @classmethod
    def validate(cls, lines):
        super().validate(lines)
        for line in lines:
            line.check_required_purchasable_lines()

    def check_required_purchasable_lines(self):
        if self.parent.explode_kit_in_purchases and not self.product.purchasable:
            raise ValidationError(
                gettext('purchase_kit.purchasable_lines_required'))
