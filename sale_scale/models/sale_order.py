# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _action_confirm(self):
        res = super()._action_confirm()
        # Auto-validate delivery pickings after order confirmation
        self._auto_validate_pickings()
        return res

    def _auto_validate_pickings(self):
        """Automatically validate (receive) all delivery orders for the sale order."""
        self.env.flush_all()
        for order in self:
            domain = [
                ('state', 'not in', ('done', 'cancel')),
                '|',
                ('sale_id', '=', order.id),
                ('group_id', '=', order.procurement_group_id.id),
            ]
            if not order.procurement_group_id:
                domain = [
                    ('sale_id', '=', order.id),
                    ('state', 'not in', ('done', 'cancel')),
                ]
            pickings = self.env['stock.picking'].search(domain)
            _logger.info(
                "Auto-validating %s pickings for %s: %s",
                len(pickings), order.name,
                [(p.name, p.state) for p in pickings],
            )
            for picking in pickings:
                if picking.state in ('done', 'cancel'):
                    continue
                # Set all move done quantities = demand quantities
                for move in picking.move_ids.filtered(
                    lambda m: m.state not in ('done', 'cancel')
                ):
                    move.quantity = move.product_uom_qty
                # Use button_validate with skip_backorder to bypass wizards
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
