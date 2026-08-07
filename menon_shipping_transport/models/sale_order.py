# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.tools import format_amount


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

    @api.depends(
        'order_line.price_subtotal', 'currency_id', 'company_id', 'payment_term_id',
        'shipping_transport_total',
    )
    def _compute_amounts(self):
        super()._compute_amounts()
        for order in self:
            order.amount_total += order.shipping_transport_total

    @api.depends(
        'order_line.price_subtotal', 'currency_id', 'company_id', 'payment_term_id',
        'shipping_transport_total',
    )
    def _compute_tax_totals(self):
        super()._compute_tax_totals()
        for order in self:
            if order.shipping_transport_total:
                currency = order.currency_id or order.company_id.currency_id
                # Add to total
                order.tax_totals['total_amount_currency'] += order.shipping_transport_total
                order.tax_totals['formatted_amount_total'] = format_amount(
                    self.env, order.tax_totals['total_amount_currency'], currency
                )
                # Inject "المشال والشحن" line in the first subtotal
                if order.tax_totals.get('subtotals'):
                    subtotal = order.tax_totals['subtotals'][0]
                    shipping_tax_group = {
                        'id': False,
                        'involved_tax_ids': [],
                        'tax_amount_currency': order.shipping_transport_total,
                        'tax_amount': 0.0,
                        'base_amount_currency': 0.0,
                        'base_amount': 0.0,
                        'display_base_amount_currency': False,
                        'display_base_amount': False,
                        'group_name': 'المشال والشحن',
                        'group_label': 'المشال والشحن',
                    }
                    subtotal['tax_groups'].append(shipping_tax_group)
                    subtotal['tax_amount_currency'] += order.shipping_transport_total

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
