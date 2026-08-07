# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleReport(models.Model):
    _inherit = "sale.report"

    stock_on_hand = fields.Float(string='Stock On Hand', readonly=True)
    stock_available = fields.Float(string='Stock Available', readonly=True)
    stock_reserved = fields.Float(string='Stock Reserved', readonly=True)
    stock_locations = fields.Char(string='Stock Locations', readonly=True)

    def _select_additional_fields(self):
        # Correlated subqueries: one value per sale line, no row multiplication
        return {
            'stock_on_hand': """
                COALESCE((
                    SELECT SUM(sq.quantity)
                    FROM stock_quant sq
                    JOIN stock_location sl ON sl.id = sq.location_id
                    WHERE sq.product_id = l.product_id
                      AND sl.usage = 'internal'
                      AND sq.quantity > 0
                ), 0.0)
            """,
            'stock_available': """
                COALESCE((
                    SELECT SUM(sq.quantity - sq.reserved_quantity)
                    FROM stock_quant sq
                    JOIN stock_location sl ON sl.id = sq.location_id
                    WHERE sq.product_id = l.product_id
                      AND sl.usage = 'internal'
                      AND sq.quantity > 0
                ), 0.0)
            """,
            'stock_reserved': """
                COALESCE((
                    SELECT SUM(sq.reserved_quantity)
                    FROM stock_quant sq
                    JOIN stock_location sl ON sl.id = sq.location_id
                    WHERE sq.product_id = l.product_id
                      AND sl.usage = 'internal'
                      AND sq.quantity > 0
                ), 0.0)
            """,
            'stock_locations': """
                COALESCE((
                    SELECT STRING_AGG(wh_name || ': ' || qty::text, ', ' ORDER BY wh_name)
                    FROM (
                        SELECT wh.name AS wh_name, SUM(sq2.quantity) AS qty
                        FROM stock_quant sq2
                        JOIN stock_location sl2 ON sl2.id = sq2.location_id
                        LEFT JOIN stock_warehouse wh ON wh.id = sl2.warehouse_id
                        WHERE sq2.product_id = l.product_id
                          AND sl2.usage = 'internal'
                          AND sq2.quantity > 0
                        GROUP BY wh.name
                    ) stock_summary
                ), '')
            """,
        }
