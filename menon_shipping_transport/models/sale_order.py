# -*- coding: utf-8 -*-
from odoo import api, fields, models

SHIPPING_TRANSPORT_PRODUCT_XMLID = 'menon_shipping_transport.product_shipping_transport_service'


class SaleOrder(models.Model):
    _inherit = "sale.order"

    customer_phone = fields.Char(
        string="Customer Phone",
        related='partner_id.phone',
    )
    salesperson_phone = fields.Char(
        string="Salesperson Phone",
        related='user_id.phone',
    )

    shipping_transport_total = fields.Monetary(
        string="إجمالي المشال والشحن",
        currency_field='currency_id',
        compute='_compute_shipping_transport_total',
        store=True,
        tracking=True,
        help="Total shipping and transport cost added to the order",
    )
    shipping_transport_line_ids = fields.One2many(
        'sale.order.shipping.transport.line',
        'order_id',
        string="سجلات المشال والشحن",
    )

    @api.depends('shipping_transport_line_ids.amount')
    def _compute_shipping_transport_total(self):
        for order in self:
            order.shipping_transport_total = sum(line.amount for line in order.shipping_transport_line_ids)

    def _sync_shipping_transport_order_line(self):
        """Keep a single order line in sync with shipping_transport_total, using the
        dedicated service product so it flows through the normal totals/tax computation."""
        product_tmpl = self.env.ref(SHIPPING_TRANSPORT_PRODUCT_XMLID, raise_if_not_found=False)
        product = product_tmpl.product_variant_id if product_tmpl else False
        if not product:
            return
        for order in self:
            line = order.order_line.filtered(lambda l: l.product_id.id == product.id)
            if not order.shipping_transport_total:
                line.unlink()
                continue
            if line:
                line.price_unit = order.shipping_transport_total
            else:
                self.env['sale.order.line'].create({
                    'order_id': order.id,
                    'product_id': product.id,
                    'product_uom_qty': 1,
                    'price_unit': order.shipping_transport_total,
                })

    def action_open_shipping_transport_wizard(self):
        self.ensure_one()
        return {
            'name': 'المشال والشحن',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.shipping.transport',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
            },
        }


class SaleOrderShippingTransportLine(models.Model):
    _name = 'sale.order.shipping.transport.line'
    _description = "Shipping & Transport Line"
    _order = 'id desc'

    order_id = fields.Many2one(
        'sale.order',
        string="Sales Order",
        required=True,
        ondelete='cascade',
    )
    currency_id = fields.Many2one(
        related='order_id.currency_id',
    )
    amount = fields.Monetary(
        string="القيمة",
        required=True,
        currency_field='currency_id',
    )
    company_id = fields.Many2one(
        related='order_id.company_id',
    )

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.order_id._sync_shipping_transport_order_line()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if 'amount' in vals:
            self.order_id._sync_shipping_transport_order_line()
        return res

    def unlink(self):
        orders = self.order_id
        res = super().unlink()
        orders._sync_shipping_transport_order_line()
        return res


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    is_shipping_transport_line = fields.Boolean(
        compute='_compute_is_shipping_transport_line',
    )

    @api.depends('product_id')
    def _compute_is_shipping_transport_line(self):
        product_tmpl = self.env.ref(SHIPPING_TRANSPORT_PRODUCT_XMLID, raise_if_not_found=False)
        product = product_tmpl.product_variant_id if product_tmpl else False
        for line in self:
            line.is_shipping_transport_line = bool(product) and line.product_id.id == product.id
