# -*- coding: utf-8 -*-
from odoo import models, api, fields


class SaleOrder(models.Model):
    _inherit = "sale.order"

    how_did_you_know = fields.Char(string='How did you hear about us?')

    amount_paid = fields.Monetary(
        string='إجمالي المدفوع',
        currency_field='currency_id',
        compute='_compute_amount_paid',
        store=False,
    )

    amount_remaining = fields.Monetary(
        string='المبلغ المتبقي',
        currency_field='currency_id',
        compute='_compute_amount_paid',
        store=False,
    )

    @api.depends(
        'invoice_ids',
        'invoice_ids.state',
        'invoice_ids.payment_state',
        'invoice_ids.line_ids.amount_residual',
        'amount_total',
    )
    def _compute_amount_paid(self):
        for order in self:
            paid = 0.0

            payments = self.env['account.payment'].search([
                ('sale_order_id', '=', order.id),
                # ('payment_type', '=', 'inbound'),
                ('state', 'in', ['posted', 'paid']),
            ])
            for pay in payments:
                paid += pay.amount

            if not paid:
                invoices = order.invoice_ids.filtered(
                    lambda i: i.state == 'posted' and i.move_type == 'out_invoice'
                )
                for inv in invoices:
                    try:
                        for payment in inv._get_reconciled_payments():
                            paid += payment.amount
                    except Exception:
                        paid += inv.amount_total - inv.amount_residual

            order.amount_paid = paid
            order.amount_remaining = order.amount_total - paid