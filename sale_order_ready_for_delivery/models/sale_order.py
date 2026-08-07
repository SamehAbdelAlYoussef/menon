# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    """Extend sale.order to add ready-for-delivery status tracking."""

    _inherit = "sale.order"

    ready_for_delivery = fields.Selection(
        selection=[
            ('ready', _('Ready for Delivery')),
            ('not_ready', _('Not Ready for Delivery')),
        ],
        string=_("Delivery Status"),
        default=False,
        copy=False,
        help=_("Delivery readiness based on product stock availability."),
    )

    # ------------------------------------------------------------------
    # Core availability logic
    # ------------------------------------------------------------------

    def _check_ready_for_delivery(self):
        """Check whether all product lines in this order have sufficient stock."""
        self.ensure_one()

        if self.state not in ('draft', 'sent'):
            return False

        # Force flush all pending writes to DB, then search directly.
        self.env.flush_all()

        # Debug: count ALL lines first (before product filter)
        all_lines = self.env['sale.order.line'].search([
            ('order_id', '=', self.id),
        ])
        lines = all_lines.filtered(
            lambda l: l.product_id and l.product_id.type != 'service'
        )

        _logger.info(
            "Order %s (id=%s) — total lines=%d, non-service lines=%d",
            self.name, self.id, len(all_lines), len(lines),
        )

        if not lines:
            return False

        warehouse = self.warehouse_id

        for line in lines:
            product = line.product_id
            if not product:
                continue

            # Service products are always skipped (not a physical product)
            if product.type == 'service':
                continue

            # Storable and consumable: check virtual_available
            product.invalidate_recordset(['virtual_available'])

            if warehouse:
                product_ctx = product.with_context(warehouse=warehouse.id)
            else:
                product_ctx = product

            available = product_ctx.virtual_available
            ordered = line.product_uom_qty

            if available < ordered:
                _logger.info(
                    "Order %s — NOT READY: %s available=%s < ordered=%s (wh=%s)",
                    self.name, product.display_name, available, ordered,
                    warehouse.name if warehouse else 'All',
                )
                return 'not_ready'
            else:
                _logger.info(
                    "Order %s — OK: %s available=%s >= ordered=%s",
                    self.name, product.display_name, available, ordered,
                )

        _logger.info("Order %s — READY! All products available", self.name)
        return 'ready'

    def _recompute_ready_for_delivery(self):
        """Recompute ready_for_delivery for all records in self."""
        for order in self:
            old_value = order.ready_for_delivery
            new_value = order._check_ready_for_delivery()

            _logger.info(
                "Order %s (state=%s): old=%s new=%s",
                order.name, order.state, old_value, new_value,
            )

            if old_value == new_value:
                continue

            order.write({'ready_for_delivery': new_value or False})

            if new_value == 'ready' and old_value != 'ready':
                order._notify_users_ready()
            elif new_value == 'not_ready' and old_value == 'ready':
                order._notify_no_longer_ready()

    # ------------------------------------------------------------------
    # Chatter messages
    # ------------------------------------------------------------------

    def _notify_users_ready(self):
        """Send notification to all users when order is ready for delivery.

        Safely subscribes all active users as followers, then posts a
        comment. Uses message_type='comment' (not 'notification') to
        avoid the Odoo core notification pipeline that triggers duplicate
        follower INSERTs via add_followers=True in _bus_send_store.
        """
        self.ensure_one()

        users = self.env['res.users'].search([('active', '=', True)])
        if not users:
            _logger.warning("Order %s: No active users to notify", self.name)
            return

        # Subscribe any users not already following (SQL handles duplicates)
        self._followers_insert_on_conflict(users.mapped('partner_id').ids)

        # Post as comment — inbox notifications reach all followers
        # via standard chatter, without triggering the duplicate-follower bug
        self.message_post(
            body=_(
                "✅ Sales Order %s is Ready for Delivery!\n"
                "All products are now available in stock. "
                "You can confirm and deliver this order."
            ) % self.name,
            subject=_("Ready for Delivery: %s") % self.name,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )
        _logger.info("Order %s: Ready notification sent to %d users", self.name, len(users))

    def _followers_insert_on_conflict(self, partner_ids):
        """Subscribe partners using INSERT ... WHERE NOT EXISTS.
        Completely avoids the duplicate follower IntegrityError."""
        if not partner_ids:
            return
        self.env.cr.execute("""
            INSERT INTO mail_followers (res_model, res_id, partner_id)
            SELECT %(model)s, %(res_id)s, p.id
            FROM unnest(%(pids)s::int[]) AS p(id)
            WHERE NOT EXISTS (
                SELECT 1 FROM mail_followers mf
                WHERE mf.res_model = %(model)s
                  AND mf.res_id = %(res_id)s
                  AND mf.partner_id = p.id
            )
        """, {
            'model': self._name,
            'res_id': self.id,
            'pids': list(partner_ids),
        })
        self.env.registry.clear_cache()

    def _notify_no_longer_ready(self):
        """Post a note when a ready order loses stock."""
        self.ensure_one()
        self.message_post(
            body=_(
                "⚠️ Sales Order %s is no longer Ready for Delivery.\n"
                "Some products are now out of stock. "
                "You will be notified when they become available again."
            ) % self.name,
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )

    def _post_waiting_for_stock(self):
        """Post a note: order is waiting for stock (called once after save)."""
        self.ensure_one()
        self.message_post(
            body=_(
                "📦 Sales Order %s — Waiting for Stock\n"
                "Some products are not yet available. "
                "You will be notified as soon as all products become ready."
            ) % self.name,
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )

    # ------------------------------------------------------------------
    # ORM overrides
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """Override to fix Odoo core bug: duplicate follower when
        create_uid's partner == user_id's partner.

        mail.thread.create() does:
          1. _insert_followers(creator, check_existing=False) — INSERT
          2. _message_auto_subscribe for tracked partners (user_id)
        If both reference the same partner, step 2's unflushed query
        misses step 1's INSERT → duplicate key error.

        Fix: use mail_create_nosubscribe to skip step 1, then let
        step 2 handle subscription correctly.
        """
        orders = super(
            SaleOrder, self.with_context(mail_create_nosubscribe=True)
        ).create(vals_list)
        # Manually subscribe creators (what step 1 would have done)
        for order in orders:
            if self.env.user.active:
                order._message_subscribe(
                    partner_ids=self.env.user.partner_id.ids,
                    subtype_ids=None,
                    customer_ids=[],
                )
        for order in orders:
            if order.state in ('draft', 'sent'):
                order._recompute_ready_for_delivery()
                if order.ready_for_delivery == 'not_ready':
                    order._post_waiting_for_stock()
        return orders

    def write(self, vals):
        res = super().write(vals)

        if set(vals.keys()) == {'ready_for_delivery'}:
            return res

        trigger_fields = {'order_line', 'state', 'warehouse_id'}
        if any(f in vals for f in trigger_fields):
            if 'state' in vals:
                self._recompute_ready_for_delivery()
            else:
                pending = self.filtered(lambda o: o.state in ('draft', 'sent'))
                if pending:
                    pending._recompute_ready_for_delivery()

        return res

    # ------------------------------------------------------------------
    # Recalculate after stock changes
    # ------------------------------------------------------------------

    @api.model
    def _recalculate_affected_orders(self, product_ids):
        """Find and recalculate orders affected by stock changes."""
        if not product_ids:
            return
        order_lines = self.env['sale.order.line'].search([
            ('product_id', 'in', product_ids),
            ('product_id.type', '!=', 'service'),
            ('order_id.state', 'in', ('draft', 'sent')),
        ])
        orders = order_lines.mapped('order_id')
        if orders:
            orders._recompute_ready_for_delivery()
            _logger.info("Stock change → %d orders recalculated", len(orders))

    @api.model
    def cron_recalculate_ready_for_delivery(self):
        """Scheduled action: recalculate all pending orders."""
        orders = self.search([
            ('state', 'in', ('draft', 'sent')),
        ], limit=100, order='write_date asc')
        if orders:
            orders._recompute_ready_for_delivery()
            _logger.info("Cron: recalculated %d orders", len(orders))


class SaleOrderLine(models.Model):
    """Trigger recalculation when order lines are created or modified.
    This catches the flow where lines are saved after the order itself."""

    _inherit = "sale.order.line"

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        # Force all writes to DB before we try to find the parent order
        self.env.flush_all()
        orders = lines.mapped('order_id').filtered(
            lambda o: o.state in ('draft', 'sent')
        )
        if orders:
            _logger.info(
                "Order line created (ids=%s) → recalculating %d orders (ids=%s)",
                lines.ids, len(orders), orders.ids,
            )
            orders._recompute_ready_for_delivery()
            for order in orders:
                if order.ready_for_delivery == 'not_ready':
                    order._post_waiting_for_stock()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if any(f in vals for f in ('product_id', 'product_uom_qty', 'product_uom')):
            orders = self.mapped('order_id').filtered(
                lambda o: o.state in ('draft', 'sent')
            )
            if orders:
                _logger.info("Order line updated → recalculating %d orders", len(orders))
                orders._recompute_ready_for_delivery()
        return res

    def unlink(self):
        orders = self.mapped('order_id').filtered(
            lambda o: o.state in ('draft', 'sent')
        )
        res = super().unlink()
        if orders:
            _logger.info("Order line deleted → recalculating %d orders", len(orders))
            orders._recompute_ready_for_delivery()
        return res
