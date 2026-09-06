# -*- coding: utf-8 -*-
import logging
from odoo import fields, models, api

_logger = logging.getLogger(__name__)


class SaleReport(models.Model):
    _inherit = "sale.report"

    stock_on_hand = fields.Float(string='Stock On Hand', readonly=True)
    stock_available = fields.Float(string='Stock Available', readonly=True)
    stock_reserved = fields.Float(string='Stock Reserved', readonly=True)
    stock_locations = fields.Char(string='Stock Locations', readonly=True)

    def _select_additional_fields(self):
        res = super()._select_additional_fields()
        res.update({
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
        })
        return res

    def _get_stock_map(self, id_field, ids):
        """
        Returns {id: {stock_on_hand, stock_reserved, stock_available}}
        id_field: 'product_id' (variant) or 'product_tmpl_id' (template)
        """
        stock_map = {}
        if not ids:
            return stock_map

        try:
            if id_field == 'product_id':
                # Group by variant directly
                quant_data = self.env['stock.quant'].read_group(
                    domain=[
                        ('product_id', 'in', ids),
                        ('location_id.usage', '=', 'internal'),
                    ],
                    fields=['product_id', 'quantity:sum', 'reserved_quantity:sum'],
                    groupby=['product_id'],
                )
                for row in quant_data:
                    key = row['product_id'][0]
                    on_hand = row.get('quantity', 0.0)
                    reserved = row.get('reserved_quantity', 0.0)
                    stock_map[key] = {
                        'stock_on_hand': on_hand,
                        'stock_reserved': reserved,
                        'stock_available': on_hand - reserved,
                    }

            elif id_field == 'product_tmpl_id':
                # Map via template: get all variants for each template
                variants = self.env['product.product'].search_read(
                    [('product_tmpl_id', 'in', ids)],
                    ['id', 'product_tmpl_id'],
                )
                variant_to_tmpl = {v['id']: v['product_tmpl_id'][0] for v in variants}
                variant_ids = list(variant_to_tmpl.keys())

                if not variant_ids:
                    return stock_map

                quant_data = self.env['stock.quant'].read_group(
                    domain=[
                        ('product_id', 'in', variant_ids),
                        ('location_id.usage', '=', 'internal'),
                    ],
                    fields=['product_id', 'quantity:sum', 'reserved_quantity:sum'],
                    groupby=['product_id'],
                )

                # Aggregate by template
                for row in quant_data:
                    variant_id = row['product_id'][0]
                    tmpl_id = variant_to_tmpl.get(variant_id)
                    if tmpl_id is None:
                        continue
                    on_hand = row.get('quantity', 0.0)
                    reserved = row.get('reserved_quantity', 0.0)
                    entry = stock_map.setdefault(tmpl_id, {
                        'stock_on_hand': 0.0,
                        'stock_reserved': 0.0,
                        'stock_available': 0.0,
                    })
                    entry['stock_on_hand'] += on_hand
                    entry['stock_reserved'] += reserved
                    entry['stock_available'] += on_hand - reserved

        except Exception as e:
            _logger.warning("sale.report _get_stock_map error: %s", e)

        return stock_map

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        try:
            result = super().read_group(
                domain, fields, groupby,
                offset=offset, limit=limit, orderby=orderby, lazy=lazy
            )
        except Exception as e:
            _logger.warning("sale.report read_group error: %s", e)
            return []

        stock_fields = {'stock_on_hand', 'stock_available', 'stock_reserved'}
        requested = stock_fields & set(f.split(':')[0] for f in (fields or []))
        if not requested:
            return result

        groupby_list = groupby if isinstance(groupby, list) else ([groupby] if groupby else [])
        groupby_fields = [g.split(':')[0] for g in groupby_list]

        # Determine grouping key: prefer product_id (variant), then product_tmpl_id (template)
        if 'product_id' in groupby_fields:
            id_field = 'product_id'
        elif 'product_tmpl_id' in groupby_fields:
            id_field = 'product_tmpl_id'
        else:
            # No product grouping — stock values are meaningless
            for r in result:
                for f in requested:
                    r[f] = 0.0
            return result

        try:
            ids = [
                r[id_field][0]
                for r in result
                if isinstance(r.get(id_field), (list, tuple))
            ]

            stock_map = self._get_stock_map(id_field, ids)

            for r in result:
                key_val = r.get(id_field)
                if not isinstance(key_val, (list, tuple)):
                    continue
                stock = stock_map.get(key_val[0], {})
                for f in requested:
                    r[f] = stock.get(f, 0.0)

        except Exception as e:
            _logger.warning("sale.report stock fix error: %s", e)

        return result
