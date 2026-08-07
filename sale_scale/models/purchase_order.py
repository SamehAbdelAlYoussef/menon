# -*- coding: utf-8 -*-
import logging
from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    related_sale_order_ids = fields.Many2many(
        'sale.order', string='أوامر البيع المرتبطة',
        compute='_compute_related_sale_orders')
    related_sale_order_count = fields.Integer(
        string='عدد أوامر البيع', compute='_compute_related_sale_orders')

    @api.depends('order_line.generated_sale_line_id')
    def _compute_related_sale_orders(self):
        for order in self:
            sale_orders = order.order_line.generated_sale_line_id.order_id
            order.related_sale_order_ids = sale_orders
            order.related_sale_order_count = len(sale_orders)

    def action_view_related_sale_orders(self):
        """زرار الهيدر: اعرض أوامر البيع اللي اتعملت من أمر الشراء ده"""
        self.ensure_one()
        sale_orders = self.related_sale_order_ids
        action = {
            'type': 'ir.actions.act_window',
            'name': 'أوامر البيع',
            'res_model': 'sale.order',
        }
        if len(sale_orders) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': sale_orders.id,
            })
        else:
            action.update({
                'view_mode': 'list,form',
                'domain': [('id', 'in', sale_orders.ids)],
            })
        return action

    def button_approve(self, force=False):
        res = super().button_approve(force=force)
        self._auto_validate_pickings()
        return res

    def _auto_validate_pickings(self):
        """Automatically validate (receive) all incoming pickings for the PO."""
        self.env.flush_all()
        for order in self:
            pickings = self.env['stock.picking'].search([
                ('origin', '=', order.name),
                ('picking_type_id.code', '=', 'incoming'),
                ('state', 'not in', ('done', 'cancel')),
            ])
            _logger.info(
                "Auto-validating %s pickings for PO %s: %s",
                len(pickings), order.name,
                [(p.name, p.state) for p in pickings],
            )
            for picking in pickings:
                if picking.state in ('done', 'cancel'):
                    continue
                for move in picking.move_ids.filtered(
                    lambda m: m.state not in ('done', 'cancel')
                ):
                    move.quantity = move.product_uom_qty
                try:
                    picking.with_context(
                        skip_backorder=True,
                        skip_sanity_check=True,
                    ).button_validate()
                    _logger.info("Picking %s validated", picking.name)
                except Exception as e:
                    _logger.warning(
                        "Auto-validate picking %s failed: %s", picking.name, e
                    )

    def _create_customer_sale_orders(self):
        """لكل سطر شراء عليه عميل: اعمل/كمّل أمر بيع للعميل ده
        - بيشتغل عند الحفظ حتى لو الأمر لسه Quotation (مش لازم تأكيد)
        - لو في أمر بيع (مسودة) اتعمل للعميل خلال آخر 24 ساعة → زوّد عليه السطور
        - لو مفيش → اعمل أمر بيع جديد
        """
        for order in self:
            # السطور اللي عليها عميل ولسه متعملهاش سطر بيع
            pending_lines = order.order_line.filtered(
                lambda l: l.customer_id and l.product_id
                and not l.display_type and not l.generated_sale_line_id)
            if not pending_lines:
                continue

            # جمّع السطور حسب العميل
            by_customer = defaultdict(lambda: self.env['purchase.order.line'])
            for pol in pending_lines:
                by_customer[pol.customer_id] |= pol

            SaleOrder = self.env['sale.order'].sudo()
            limit_date = fields.Datetime.now() - timedelta(hours=24)
            for customer, pols in by_customer.items():
                # دور على أمر بيع للعميل اتعمل خلال آخر 24 ساعة
                sale_order = SaleOrder.search([
                    ('partner_id', '=', customer.id),
                    ('company_id', '=', order.company_id.id),
                    ('state', 'in', ['draft', 'sent']),
                    ('create_date', '>=', limit_date),
                ], order='create_date desc', limit=1)

                if sale_order:
                    # زوّد اسم أمر الشراء في المصدر
                    if order.name not in (sale_order.origin or ''):
                        sale_order.origin = '%s, %s' % (sale_order.origin, order.name) \
                            if sale_order.origin else order.name
                else:
                    sale_order = SaleOrder.create({
                        'partner_id': customer.id,
                        'company_id': order.company_id.id,
                        'origin': order.name,
                    })

                # اعمل سطور البيع دفعة واحدة (batch) بدل واحد واحد
                sale_lines = self.env['sale.order.line'].sudo().create([{
                    'order_id': sale_order.id,
                    'product_id': pol.product_id.id,
                    'product_uom': pol.product_uom.id,
                    'product_uom_qty': pol.product_qty,
                    # كل تفاصيل الميزان بتتنقل زي ما هي
                    'scale_id': pol.scale_id.id,
                    'scale_discount': pol.scale_discount,
                    # من غير سعر - كل حاجة بتتنقل ما عدا السعر
                    'price_unit': 0.0,
                    # المورد اللي اتشرى منه المنتج
                    'source_vendor_id': order.partner_id.id,
                    'name': "%s\nالمورد: %s" % (
                        pol.product_id.display_name, order.partner_id.name),
                } for pol in pols])
                for pol, sale_line in zip(pols, sale_lines):
                    pol.generated_sale_line_id = sale_line
