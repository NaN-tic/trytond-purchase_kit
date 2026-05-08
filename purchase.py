# This file is part of purchase_kit module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from decimal import Decimal

from trytond.model import fields
from trytond.modules.product import round_price
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Equal, Eval
from trytond.transaction import Transaction


class PurchaseLine(metaclass=PoolMeta):
    __name__ = 'purchase.line'

    kit_depth = fields.Integer(
        'Depth', required=True,
        help='Depth of the line if it is part of a kit.')
    kit_parent_line = fields.Many2One(
        'purchase.line', 'Parent Kit Line',
        help='The kit that contains this product.')
    kit_child_lines = fields.One2Many(
        'purchase.line', 'kit_parent_line', 'Lines in the kit',
        help='Subcomponents of the kit.')

    @classmethod
    def __setup__(cls):
        super().__setup__()
        required = (~Eval('kit_parent_line', False)
            and Equal(Eval('type'), 'line'))
        cls.unit_price.states['required'] = required

    @classmethod
    def default_kit_depth(cls):
        return 0

    def _fill_line_from_kit_line(self, kit_line, line):
        pool = Pool()
        Product = pool.get('product.product')
        ProductUom = pool.get('product.uom')

        self.type = 'line'
        self.product = Product(kit_line.product)
        self.on_change_product()
        if kit_line.unit.category.id != line.unit.category.id:
            quantity = kit_line.quantity * line.quantity
        else:
            quantity = ProductUom.compute_qty(
                kit_line.unit, kit_line.quantity, line.unit) * line.quantity
        self.unit = kit_line.unit
        self.quantity = quantity
        self.on_change_quantity()
        self.kit_parent_line = line

    @classmethod
    def explode_kit(cls, lines):
        Product = Pool().get('product.product')

        has_purchase_discount = hasattr(cls, 'base_price')
        sequence = lines[0].sequence if lines and lines[0].sequence else 1
        to_write, to_create = [], []
        for line in lines:
            if line.sequence != sequence and to_create:
                line.sequence = sequence
            sequence += 1
            depth = line.kit_depth + 1
            if (line.product and line.product.kit and line.product.kit_lines
                    and line.product.explode_kit_in_purchases):
                kit_lines = list(zip(
                    line.product.kit_lines,
                    [depth] * len(list(line.product.kit_lines))))
                while kit_lines:
                    kit_line, depth = kit_lines.pop(0)
                    product = Product(kit_line.product)

                    default_values = cls.default_get(
                        cls._fields.keys(), with_rec_name=False)
                    purchase_line = cls(**default_values)
                    purchase_line.purchase = line.purchase
                    purchase_line._fill_line_from_kit_line(kit_line, line)
                    purchase_line.sequence = sequence
                    purchase_line.on_change_product()
                    purchase_line.kit_depth = depth

                    if kit_line.get_purchase_price():
                        with Transaction().set_context(
                                purchase_line._get_context_purchase_price()):
                            prices = Product.get_purchase_price(
                                [product], abs(line.quantity))
                            unit_price = prices.get(product.id) or Decimal(0)
                            unit_price = round_price(unit_price)
                    else:
                        unit_price = Decimal(0)

                    if has_purchase_discount:
                        purchase_line.base_price = unit_price
                        purchase_line.unit_price = unit_price
                        if line.discount_rate is not None:
                            purchase_line.discount_rate = line.discount_rate
                            purchase_line.on_change_discount_rate()
                        elif line.discount_amount is not None:
                            purchase_line.discount_amount = (
                                line.discount_amount)
                            purchase_line.on_change_discount_amount()
                    else:
                        purchase_line.unit_price = unit_price

                    to_create.append(purchase_line._save_values())
                    if product.kit and product.kit_lines:
                        product_kit_lines = list(zip(
                            product.kit_lines,
                            [depth + 1] * len(list(product.kit_lines))))
                        kit_lines = product_kit_lines + kit_lines
                    sequence += 1
                if not line.product.kit_fixed_list_price and line.unit_price:
                    if has_purchase_discount:
                        line.base_price = Decimal(0)
                    line.unit_price = Decimal(0)
            elif (line.product and line.product.kit_lines
                    and not line.product.kit_fixed_list_price):
                with Transaction().set_context(
                        line._get_context_purchase_price()):
                    prices = Product.get_purchase_price(
                        [line.product], abs(line.quantity))
                    unit_price = prices[line.product.id]
                if has_purchase_discount:
                    line.base_price = unit_price
                    line.unit_price = unit_price
                elif line.unit_price != unit_price:
                    line.unit_price = unit_price
            to_write.extend(([line], line._save_values()))
        if to_write:
            cls.write(*to_write)
        return super().create(to_create)

    @classmethod
    def create(cls, values):
        lines = super().create(values)
        if Transaction().context.get('explode_kit', True):
            lines.extend(cls.explode_kit(lines))
        return lines

    def get_kit_lines(self, kit_line=None):
        res = []
        childs = kit_line.kit_child_lines if kit_line else self.kit_child_lines
        for child in childs:
            res.append(child)
            res += self.get_kit_lines(child)
        return res

    @classmethod
    def write(cls, *args):
        actions = iter(args)
        to_write, to_reset, to_delete = [], [], []
        if Transaction().context.get('explode_kit', True):
            for lines, values in zip(actions, actions):
                reset_kit = False
                if ('product' in values or 'quantity' in values
                        or 'unit' in values):
                    reset_kit = True
                lines = lines[:]
                if reset_kit:
                    for line in lines:
                        to_delete += line.get_kit_lines()
                    lines = list(set(lines) - set(to_delete))
                    to_reset.extend(lines)
                to_write.extend((lines, values))
        else:
            to_write = args
        if to_write:
            super().write(*to_write)
        super().write(*args)
        if to_delete:
            cls.delete(to_delete)
        to_reset = list(set(to_reset) - set(to_delete))
        if to_reset:
            cls.explode_kit(to_reset)

    @classmethod
    def copy(cls, lines, default=None):
        if default is None:
            default = {}
        else:
            default = default.copy()
        default['kit_child_lines'] = []
        if Transaction().context.get('check_kit_parent_line', True):
            lines = [x for x in lines if not x.kit_parent_line]
        return super().copy(lines, default=default)
