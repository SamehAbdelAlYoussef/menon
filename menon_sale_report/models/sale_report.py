# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleReport(models.Model):
    _inherit = 'sale.report'

    partner_name_display = fields.Char(
        string="العميل (الاسم / التليفون / الموبايل)",
        readonly=True,
        group_operator='max',
    )

    def _select_sale(self):
        return (
            super()._select_sale()
            + """,
            MAX(partner.name
                || '  -  تليفون: ' || COALESCE(partner.phone, '--')
                || '  -  موبايل: ' || COALESCE(partner.mobile, '--')
            ) AS partner_name_display"""
        )
