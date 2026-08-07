# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    scale_id = fields.Many2one('scale.scale', string='نوع الميزان')
    scale_discount = fields.Float(string='خصم الميزان %', digits='Discount')
    qty_after_scale_discount = fields.Float(
        string='الكمية بعد الخصم',
        compute='_compute_qty_after_scale_discount',
        store=True,
        digits='Product Unit of Measure')
    # العميل اللي هيتعمله أمر بيع بالمنتج ده بعد تأكيد الشراء
    customer_id = fields.Many2one(
        'res.partner', string='العميل', copy=False)
    # سطر البيع اللي اتعمل من السطر ده (عشان ميتكررش)
    generated_sale_line_id = fields.Many2one(
        'sale.order.line', string='سطر البيع المُنشأ', readonly=True, copy=False)

    @api.depends('product_qty', 'scale_discount')
    def _compute_qty_after_scale_discount(self):
        """الكمية بعد الخصم = الكمية × (1 - خصم الميزان %)"""
        for line in self:
            line.qty_after_scale_discount = line.product_qty * (
                1 - (line.scale_discount or 0.0) / 100.0)

    @api.onchange('scale_id')
    def _onchange_scale_id(self):
        for line in self:
            line.scale_discount = line.scale_id.discount if line.scale_id else 0.0

    # الحقول اللي بتتزامن مع سطر البيع المُنشأ (شراء ← بيع)
    _SALE_SYNC_FIELDS = (
        'product_id', 'product_qty', 'product_uom', 'scale_id', 'scale_discount')
    # الحقول اللي اسمها مختلف في البيع (الباقي بنفس الاسم)
    _SALE_FIELD_RENAMES = {'product_qty': 'product_uom_qty'}

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        # لو في سطر جديد عليه عميل → اعمل/كمّل أمر البيع فوراً (حتى لو Quotation)
        if any(v.get('customer_id') for v in vals_list):
            lines.order_id._create_customer_sale_orders()
        return lines

    def write(self, vals):
        res = super().write(vals)
        # لو اتحط عميل على سطر موجود → اعمل/كمّل أمر البيع فوراً
        if vals.get('customer_id'):
            self.order_id._create_customer_sale_orders()
        # أي تعديل في السطر (نوع الميزان/الخصم/الكمية/المنتج) → عدّله في سطر البيع المرتبط
        sync_keys = set(vals) & set(self._SALE_SYNC_FIELDS)
        if sync_keys:
            for line in self:
                sale_line = line.generated_sale_line_id
                # التزامن طول ما أمر البيع لسه مسودة/معروض
                if not sale_line or sale_line.order_id.state not in ('draft', 'sent'):
                    continue
                sync_vals = {
                    self._SALE_FIELD_RENAMES.get(k, k): vals[k] for k in sync_keys}
                if 'product_id' in sync_keys:
                    sync_vals['name'] = "%s\nالمورد: %s" % (
                        line.product_id.display_name,
                        line.order_id.partner_id.name)
                sale_line.sudo().write(sync_vals)
        return res

    @api.depends('scale_id', 'scale_discount')
    def _compute_price_unit_and_date_planned_and_name(self):
        """لما يكون في ميزان، خصم الميزان بيتطبق كخصم فعلي على السطر
        → الإجمالي = السعر × الكمية بعد الخصم، وبيتنقل لفاتورة المورد"""
        super()._compute_price_unit_and_date_planned_and_name()
        for line in self:
            if line.scale_id:
                line.discount = line.scale_discount
