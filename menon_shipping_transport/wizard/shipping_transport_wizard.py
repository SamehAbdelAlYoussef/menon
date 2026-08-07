# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class SaleOrderShippingTransport(models.TransientModel):
    _name = 'sale.order.shipping.transport'
    _description = "Shipping & Transport Wizard"

    sale_order_id = fields.Many2one(
        'sale.order',
        required=True,
        default=lambda self: self.env.context.get('default_sale_order_id'),
    )
    currency_id = fields.Many2one(
        related='sale_order_id.currency_id',
    )
    amount = fields.Monetary(
        string="القيمة",
        required=True,
        currency_field='currency_id',
        help="أدخل قيمة المشال والشحن",
    )

    def action_add_shipping_transport(self):
        self.ensure_one()
        self.env['sale.order.shipping.transport.line'].create({
            'order_id': self.sale_order_id.id,
            'amount': self.amount,
        })
        return {'type': 'ir.actions.act_window_close'}
