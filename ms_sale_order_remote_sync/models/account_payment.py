# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    # Link payment to sale.order (same field as sales_orders_payment_follow)
    sale_order_id = fields.Many2one(
        'sale.order', string='Sale Order',
        domain="[('partner_id', '=?', partner_id)]",
    )

    # ------------------------------------------------------------------
    # CRUD hooks — ASYNC: just enqueue
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        payments = super().create(vals_list)
        if not self.env.context.get('skip_remote_sync'):
            queue = self.env['remote.sync.queue']
            for payment in payments:
                queue.enqueue_payment_create(payment.id)
        return payments

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('skip_remote_sync'):
            queue = self.env['remote.sync.queue']
            for payment in self:
                if self._payment_should_sync(vals):
                    queue.enqueue_payment_write(payment.id, vals)
        return res

    def unlink(self):
        if not self.env.context.get('skip_remote_sync'):
            queue = self.env['remote.sync.queue']
            for payment in self:
                queue.enqueue_payment_unlink(payment.id)
        return super().unlink()

    # ------------------------------------------------------------------
    # Sync helpers
    # ------------------------------------------------------------------

    def _payment_should_sync(self, vals):
        """Only sync when meaningful payment fields change."""
        sync_fields = {
            'amount', 'payment_type', 'date', 'sale_order_id',
            'journal_id', 'partner_id', 'payment_reference', 'memo', 'state',
        }
        return bool(set(vals.keys()) & sync_fields)

    def _get_remote_config(self):
        return self.env['remote.sync.config'].search(
            [('active', '=', True)], limit=1
        )

    # ------------------------------------------------------------------
    # Sync methods called by queue processor
    # ------------------------------------------------------------------

    def _remote_sync_create_with_config(self, config):
        self.ensure_one()
        if not config:
            return False
        return self._do_remote_payment_create(config)

    def _remote_sync_write_with_config(self, config, vals):
        self.ensure_one()
        if not config:
            return False
        return self._do_remote_payment_write(config, vals)

    def _remote_sync_unlink_with_config(self, config):
        self.ensure_one()
        if not config:
            return False
        remote_id = self.env['remote.sync.mapping'].get_remote_id('account.payment', self.id)
        if not remote_id:
            return True
        result = config._call_kw('account.payment', 'unlink', args=[[remote_id]])
        if result:
            self.env['remote.sync.mapping'].search([
                ('model', '=', 'account.payment'), ('local_id', '=', self.id),
            ]).unlink()
            _logger.info("Remote Sync: DELETED payment %s → remote #%s", self.name, remote_id)
            return True
        return False

    # ------------------------------------------------------------------
    # CREATE payment on remote
    # ------------------------------------------------------------------

    def _do_remote_payment_create(self, config):
        self.ensure_one()

        # 1. Partner
        remote_partner_id = self._remote_find_or_create_payment_partner(config)
        if not remote_partner_id:
            _logger.warning("Remote Sync: no partner for payment %s", self.name)
            return False

        # 2. Journal — find a CASH journal on remote (cash goes directly to 'paid',
        #    bank journals only reach 'in_process' until bank reconciliation)
        remote_journal_id = None
        # First try: match by name AND type=cash
        if self.journal_id:
            found = config._call_kw('account.journal', 'search',
                                    args=[[['name', 'ilike', self.journal_id.name],
                                           ['type', '=', 'cash']], 0, 1])
            if found:
                remote_journal_id = found[0]

        # Second try: any cash journal on remote
        if not remote_journal_id:
            found = config._call_kw('account.journal', 'search',
                                    args=[[['type', '=', 'cash']], 0, 1])
            remote_journal_id = found[0] if found else None

        # Last resort: match by name regardless of type
        if not remote_journal_id and self.journal_id:
            found = config._call_kw('account.journal', 'search',
                                    args=[[['name', 'ilike', self.journal_id.name]], 0, 1])
            remote_journal_id = found[0] if found else None

        # 3. Sale order — lookup via mapping
        remote_so_id = None
        if self.sale_order_id:
            remote_so_id = self.env['remote.sync.mapping'].get_remote_id(
                'sale.order', self.sale_order_id.id
            )

        # 4. Build payment vals
        payment_vals = {
            'partner_id': remote_partner_id,
            'amount': self.amount,
            'payment_type': self.payment_type,
            'date': fields.Date.to_string(self.date) if self.date else False,
        }
        if remote_journal_id:
            payment_vals['journal_id'] = remote_journal_id
        if remote_so_id:
            payment_vals['sale_order_id'] = remote_so_id
        if self.payment_reference:
            payment_vals['payment_reference'] = self.payment_reference
        if self.memo:
            payment_vals['memo'] = self.memo

        # 5. Create remotely
        remote_id = config._call_kw('account.payment', 'create', args=[payment_vals])
        if not remote_id:
            _logger.error("Remote Sync: FAILED to create payment %s", self.name)
            return False

        self.env['remote.sync.mapping'].set_mapping('account.payment', self.id, remote_id)
        _logger.info("Remote Sync: CREATED payment %s → remote #%s", self.name, remote_id)

        # 6. Confirm (post) the payment on remote immediately
        # Try action_post first (Odoo 14+), fallback to action_validate (older)
        post_result = config._call_kw('account.payment', 'action_post', args=[[remote_id]])
        if not post_result and post_result != True:
            post_result = config._call_kw('account.payment', 'action_validate', args=[[remote_id]])

        # Verify actual state on remote
        remote_state_data = config._call_kw(
            'account.payment', 'read',
            args=[[remote_id], ['state']],
        )
        remote_state = (remote_state_data[0].get('state') if remote_state_data else 'unknown')

        _logger.info(
            "Remote Sync: payment %s → remote #%s state=%s (post_result=%s)",
            self.name, remote_id, remote_state, post_result
        )
        return True

    # ------------------------------------------------------------------
    # WRITE payment on remote
    # ------------------------------------------------------------------

    def _do_remote_payment_write(self, config, vals):
        self.ensure_one()

        remote_id = self.env['remote.sync.mapping'].get_remote_id('account.payment', self.id)
        if not remote_id:
            return self._do_remote_payment_create(config)

        update_vals = {}

        if 'partner_id' in vals and self.partner_id:
            rid = self._remote_find_or_create_payment_partner(config)
            if rid:
                update_vals['partner_id'] = rid

        for fld in ('amount', 'payment_type', 'payment_reference', 'memo'):
            if fld in vals:
                update_vals[fld] = self[fld] or False

        if 'date' in vals and self.date:
            update_vals['date'] = fields.Date.to_string(self.date)

        if 'journal_id' in vals and self.journal_id:
            found = config._call_kw('account.journal', 'search',
                                    args=[[['name', 'ilike', self.journal_id.name]], 0, 1])
            if found:
                update_vals['journal_id'] = found[0]

        if 'sale_order_id' in vals and self.sale_order_id:
            remote_so_id = self.env['remote.sync.mapping'].get_remote_id(
                'sale.order', self.sale_order_id.id
            )
            if remote_so_id:
                update_vals['sale_order_id'] = remote_so_id

        if not update_vals:
            return True

        result = config._call_kw('account.payment', 'write', args=[[remote_id], update_vals])
        if result:
            _logger.info("Remote Sync: UPDATED payment %s (remote #%s)", self.name, remote_id)
            return True
        _logger.error("Remote Sync: FAILED to update payment %s", self.name)
        return False

    # ------------------------------------------------------------------
    # Partner helper for payments
    # ------------------------------------------------------------------

    def _remote_find_or_create_payment_partner(self, config):
        """Find or create the payment's partner on remote."""
        partner = self.partner_id.commercial_partner_id
        if not partner:
            return None

        # Check mapping first
        rid = self.env['remote.sync.mapping'].get_remote_id('res.partner', partner.id)
        if rid:
            return rid

        # Reuse the sale.order's partner logic via a sale.order stub
        # We use the same search/create pattern as sale_order.py
        SaleOrder = self.env['sale.order']

        # Search by email
        if partner.email:
            found = config._call_kw('res.partner', 'search',
                                    args=[[['email', '=', partner.email]]])
            if found:
                rid = found[0]
                self.env['remote.sync.mapping'].set_mapping('res.partner', partner.id, rid)
                return rid

        # Search by name
        found = config._call_kw('res.partner', 'search',
                                args=[[['name', 'ilike', partner.name]]])
        if found:
            rid = found[0]
            self.env['remote.sync.mapping'].set_mapping('res.partner', partner.id, rid)
            return rid

        # Create partner on remote
        partner_vals = {
            'name': partner.name,
            'email': partner.email or False,
            'phone': partner.phone or False,
            'mobile': partner.mobile or False,
            'is_company': partner.is_company,
            'company_type': 'company' if partner.is_company else 'person',
        }
        if partner.street:
            partner_vals['street'] = partner.street
        if partner.city:
            partner_vals['city'] = partner.city
        if partner.country_id:
            remote_country = config._call_kw('res.country', 'search',
                                             args=[[['name', 'ilike', partner.country_id.name]], 0, 1])
            if remote_country:
                partner_vals['country_id'] = remote_country[0]

        rid = config._call_kw('res.partner', 'create', args=[partner_vals])
        if rid:
            self.env['remote.sync.mapping'].set_mapping('res.partner', partner.id, rid)
            _logger.info("Remote Sync: CREATED partner %s → remote #%s", partner.name, rid)
        return rid
