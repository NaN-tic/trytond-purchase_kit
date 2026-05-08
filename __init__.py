# This file is part of purchase_kit module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.pool import Pool

from . import product, purchase


def register():
    Pool.register(
        product.Product,
        product.ProductKitLine,
        purchase.PurchaseLine,
        module='purchase_kit', type_='model')
