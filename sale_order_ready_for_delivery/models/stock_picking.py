# -*- coding: utf-8 -*-
import logging
from odoo import api, models

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    """Extend stock.picking to trigger order readiness recalculation
    when incoming stock is received."""

    _inherit = "stock.picking"

    def _action_done(self):
        """Override to recalculate affected sale orders after stock receipt."""
        res = super()._action_done()

        incoming_pickings = self.filtered(
            lambda p: p.picking_type_id.code == 'incoming'
        )
        if incoming_pickings:
            product_ids = incoming_pickings.move_ids.mapped('product_id').ids
            if product_ids:
                _logger.info(
                    "Stock receipt: products %s → recalculating orders", product_ids
                )
                self.env['sale.order']._recalculate_affected_orders(product_ids)

        return res


class StockQuant(models.Model):
    """Extend stock.quant: ANY write triggers recalculation.

    We do NOT filter by specific fields because Odoo 18's product
    quantity update may write fields we don't know about. The
    performance cost is negligible — recalculation only runs on
    draft/sent orders containing the affected products.
    """

    _inherit = "stock.quant"

    def write(self, vals):
        res = super().write(vals)
        self._trigger_recalculation()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        quants = super().create(vals_list)
        quants._trigger_recalculation()
        return quants

    def _apply_inventory(self):
        """Called when inventory adjustments are applied."""
        res = super()._apply_inventory()
        self._trigger_recalculation()
        return res

    def _update_available_quantity(self, product_id, location_id, quantity=False,
                                     reserved_quantity=False, lot_id=None,
                                     package_id=None, owner_id=None, in_date=None):
        """Called on every stock change — the single source of truth."""
        res = super()._update_available_quantity(
            product_id, location_id, quantity=quantity,
            reserved_quantity=reserved_quantity, lot_id=lot_id,
            package_id=package_id, owner_id=owner_id, in_date=in_date,
        )
        # Trigger recalculation for the affected product
        if product_id:
            self.env['sale.order']._recalculate_affected_orders([product_id.id])
        return res

    def _trigger_recalculation(self):
        """Called by write/create/_apply_inventory. Deduplicates per request."""
        if self.env.context.get('_stock_recalc_done'):
            return
        product_ids = self.mapped('product_id').ids
        if product_ids:
            _logger.info(
                "Stock change: products %s → recalculating orders",
                product_ids,
            )
            self.env['sale.order'].with_context(
                _stock_recalc_done=True
            )._recalculate_affected_orders(product_ids)
