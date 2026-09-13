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

        # 2. Journal — MUST be CASH so action_post goes straight to 'paid'.
        #    Bank journals stay 'in_process' until manual bank reconciliation.
        remote_journal_id = self._get_or_create_remote_cash_journal(config)
        if not remote_journal_id:
            return False

        # 3. Sale order — lookup via mapping
        remote_so_id = None
        if self.sale_order_id:
            remote_so_id = self.env['remote.sync.mapping'].get_remote_id(
                'sale.order', self.sale_order_id.id
            )

        # 4. Build payment vals — let Odoo set destination_account_id normally
        #    (receivable/payable). We will reconcile it via write-off after posting.
        payment_vals = {
            'partner_id': remote_partner_id,
            'amount': self.amount,
            'payment_type': self.payment_type,
            'date': fields.Date.to_string(self.date) if self.date else False,
            'journal_id': remote_journal_id,
        }
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

        # 6. Post the payment → creates journal entry with receivable/payable line
        config._call_kw('account.payment', 'action_post', args=[[remote_id]])

        # 7. Read state + move_id
        remote_data = config._call_kw(
            'account.payment', 'read',
            args=[[remote_id], ['state', 'move_id']],
        )
        remote_state = remote_data[0].get('state') if remote_data else 'unknown'
        move_id = remote_data[0].get('move_id') if remote_data else None
        if isinstance(move_id, (list, tuple)):
            move_id = move_id[0]

        # 8. Force 'paid' — try every available strategy until state changes
        if remote_state != 'paid':
            remote_state = self._force_remote_payment_paid(config, remote_id, move_id, remote_state)

        if remote_state == 'paid':
            _logger.info("Remote Sync: payment %s → remote #%s ✓ state=paid", self.name, remote_id)
        else:
            _logger.error(
                "Remote Sync: payment %s → remote #%s STUCK at state=%s — "
                "ensure the remote has a properly configured Cash journal.",
                self.name, remote_id, remote_state,
            )
        return True

    # ------------------------------------------------------------------
    # Get a non-receivable/payable account from the cash journal
    # so destination_account_id bypasses reconciliation → state = paid
    # ------------------------------------------------------------------

    def _get_remote_non_receivable_account(self, config, remote_journal_id):
        """Return the journal's default account if it's not receivable/payable.
        Using it as destination_account_id means _seek_for_lines finds no
        counterpart → is_reconciled=True → payment goes to 'paid' after post."""
        try:
            journal_data = config._call_kw(
                'account.journal', 'read',
                args=[[remote_journal_id], ['default_account_id', 'name']],
            )
            if not journal_data:
                return None

            _logger.info(
                "Remote Sync: cash journal on remote = '%s' (id=%s)",
                journal_data[0].get('name'), remote_journal_id,
            )

            default = journal_data[0].get('default_account_id')
            account_id = default[0] if isinstance(default, (list, tuple)) else default
            if not account_id:
                return None

            account_data = config._call_kw(
                'account.account', 'read',
                args=[[account_id], ['account_type', 'name']],
            )
            if account_data:
                atype = account_data[0].get('account_type', '')
                _logger.info(
                    "Remote Sync: journal default account '%s' type=%s",
                    account_data[0].get('name'), atype,
                )
                if atype not in ('asset_receivable', 'liability_payable'):
                    return account_id
        except Exception as e:
            _logger.warning("Remote Sync: could not resolve destination account: %s", e)
        return None

    # ------------------------------------------------------------------
    # Get or create a Cash journal on the remote (guaranteed to exist)
    # ------------------------------------------------------------------

    def _get_or_create_remote_cash_journal(self, config):
        """Return an existing Cash journal id on remote, or create one if absent."""
        # 1. Try to match local journal name + cash type
        if self.journal_id:
            found = config._call_kw('account.journal', 'search',
                                    args=[[['name', 'ilike', self.journal_id.name],
                                           ['type', '=', 'cash']], 0, 1])
            if found:
                _logger.info("Remote Sync: found cash journal by name match id=%s", found[0])
                return found[0]

        # 2. Any cash journal on remote
        found = config._call_kw('account.journal', 'search',
                                args=[[['type', '=', 'cash']], 0, 1])
        if found:
            _logger.info("Remote Sync: using existing cash journal id=%s", found[0])
            return found[0]

        # 3. No cash journal exists → create one automatically
        _logger.warning(
            "Remote Sync: no Cash journal on remote — creating 'MS Cash Sync' journal."
        )
        # Try creating; if code 'MSCSH' already exists, try 'MSCSH2'
        for code in ('MSCSH', 'MSCSH2', 'MSCSH3'):
            journal_id = config._call_kw('account.journal', 'create', args=[{
                'name': 'MS Cash Sync',
                'type': 'cash',
                'code': code,
            }])
            if journal_id:
                _logger.info(
                    "Remote Sync: created Cash journal code=%s id=%s on remote.",
                    code, journal_id,
                )
                return journal_id

        _logger.error("Remote Sync: FAILED to create Cash journal on remote.")
        return None

    # ------------------------------------------------------------------
    # Force remote payment to 'paid' via write-off reconciliation
    # ------------------------------------------------------------------

    def _force_remote_payment_paid(self, config, remote_id, move_id, current_state):
        """Create an offsetting journal entry and reconcile it with the payment's
        receivable/payable line → amount_residual=0 → is_reconciled=True → paid."""

        def _read_state():
            data = config._call_kw('account.payment', 'read', args=[[remote_id], ['state']])
            return (data[0].get('state') if data else 'unknown')

        if not move_id:
            return _read_state()

        try:
            # 1. Get ALL unreconciled lines of the payment move (avoid account_type
            #    in domain — it may not work on all remote Odoo versions).
            all_lines = config._call_kw(
                'account.move.line', 'search_read',
                args=[[['move_id', '=', move_id], ['reconciled', '=', False]]],
                kwargs={'fields': ['id', 'debit', 'credit', 'account_id', 'partner_id']},
            ) or []

            # 2. For each line read its account type and keep receivable/payable ones
            lines = []
            for ml in all_lines:
                acc_ref = ml.get('account_id')
                acc_id = acc_ref[0] if isinstance(acc_ref, (list, tuple)) else acc_ref
                if not acc_id:
                    continue
                acc_data = config._call_kw('account.account', 'read',
                                           args=[[acc_id], ['account_type', 'name']])
                if acc_data:
                    atype = acc_data[0].get('account_type', '')
                    _logger.info(
                        "Remote Sync: move line id=%s account='%s' type=%s debit=%s credit=%s",
                        ml['id'], acc_data[0].get('name'), atype,
                        ml.get('debit'), ml.get('credit'),
                    )
                    if atype in ('asset_receivable', 'liability_payable'):
                        lines.append(ml)

            _logger.info(
                "Remote Sync: write-off — found %d receivable/payable lines on move #%s",
                len(lines), move_id,
            )
            if not lines:
                return _read_state()

            line = lines[0]
            pay_line_id = line['id']
            account_id = line['account_id'][0] if isinstance(line['account_id'], list) else line['account_id']
            partner_id = line['partner_id'][0] if line.get('partner_id') else False
            debit = line['debit']
            credit = line['credit']

            # 2. Get the cash journal's default account for the offset side
            journal_data = config._call_kw(
                'account.journal', 'read',
                args=[[self.env['remote.sync.mapping'].get_remote_id(
                    'account.payment', self.id) and move_id],
                    ['default_account_id']],
            ) or []
            # Simpler: search any expense/income account for the offset
            offset_account_ids = config._call_kw(
                'account.account', 'search',
                args=[[['account_type', 'in', ['income_other', 'expense_other',
                                               'income', 'expense']]]],
                kwargs={'limit': 1},
            )
            offset_account_id = offset_account_ids[0] if offset_account_ids else account_id

            date_str = fields.Date.to_string(self.date) if self.date else fields.Date.to_string(fields.Date.today())

            # 3. Find a journal for the write-off entry
            any_journal = config._call_kw(
                'account.journal', 'search',
                args=[[['type', 'in', ['general', 'cash', 'bank']]]],
                kwargs={'limit': 1},
            )
            if not any_journal:
                return _read_state()

            # 4. Create write-off journal entry that offsets the receivable line
            writeoff_vals = {
                'journal_id': any_journal[0],
                'date': date_str,
                'ref': f'Auto-reconcile: {self.name}',
                'line_ids': [
                    (0, 0, {
                        'account_id': account_id,
                        'partner_id': partner_id,
                        'debit': credit,   # offset credit line → debit
                        'credit': debit,   # offset debit line → credit
                        'name': f'Auto-reconcile {self.name}',
                    }),
                    (0, 0, {
                        'account_id': offset_account_id,
                        'partner_id': partner_id,
                        'debit': debit,
                        'credit': credit,
                        'name': f'Auto-reconcile {self.name}',
                    }),
                ],
            }

            writeoff_move_id = config._call_kw('account.move', 'create', args=[writeoff_vals])
            if not writeoff_move_id:
                _logger.error("Remote Sync: failed to create write-off entry for payment #%s", remote_id)
                return _read_state()

            # 5. Post the write-off entry
            config._call_kw('account.move', 'action_post', args=[[writeoff_move_id]])

            # 7. Find the receivable/payable line in the write-off entry
            writeoff_lines = config._call_kw(
                'account.move.line', 'search',
                args=[[['move_id', '=', writeoff_move_id], ['account_id', '=', account_id]]],
            )
            if not writeoff_lines:
                return _read_state()

            # 8. Reconcile payment line + write-off line → amount_residual=0 → paid
            rec_result = config._call_kw(
                'account.move.line', 'reconcile',
                args=[[pay_line_id] + writeoff_lines],
            )
            _logger.info(
                "Remote Sync: reconcile call result=%s for payment #%s",
                rec_result, remote_id,
            )

            # 9. Read is_reconciled directly — state field may be stale/cached
            pay_data = config._call_kw(
                'account.payment', 'read',
                args=[[remote_id], ['state', 'is_reconciled']],
            )
            state = pay_data[0].get('state') if pay_data else 'unknown'
            is_rec = pay_data[0].get('is_reconciled') if pay_data else False
            _logger.info(
                "Remote Sync: payment #%s after reconcile → state=%s is_reconciled=%s",
                remote_id, state, is_rec,
            )
            # Trust is_reconciled even if state hasn't recomputed yet
            if is_rec or state == 'paid':
                return 'paid'
            return state

        except Exception as e:
            _logger.error("Remote Sync: write-off reconcile failed for payment #%s: %s", remote_id, e)
            return _read_state()

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
