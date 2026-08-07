# -*- coding: utf-8 -*-
from odoo import fields, models


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    pivot_warehouse_id = fields.Many2one(
        'stock.warehouse', string='Warehouse',
        related='location_id.warehouse_id', store=True)
