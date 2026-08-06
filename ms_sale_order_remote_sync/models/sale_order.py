# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    remote_synced = fields.Boolean(
        'Synced to Remote', default=False, copy=False,
        help='This order has been pushed to the remote server',
    )

    # ------------------------------------------------------------------
    # CRUD hooks — ASYNC: just enqueue, don't block
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        if not self.env.context.get('skip_remote_sync'):
            queue = self.env['remote.sync.queue']
            for order in orders:
                queue.enqueue_create(order.id)
        return orders

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('skip_remote_sync'):
            queue = self.env['remote.sync.queue']
            for order in self:
                if order.remote_synced and order._should_sync_remote(vals):
                    queue.enqueue_write(order.id, vals)
        return res

    def unlink(self):
        if not self.env.context.get('skip_remote_sync'):
            queue = self.env['remote.sync.queue']
            for order in self:
                if order.remote_synced:
                    queue.enqueue_unlink(order.id)
        return super().unlink()

    # ------------------------------------------------------------------
    # Sync decision helpers
    # ------------------------------------------------------------------

    def _should_sync_remote(self, vals):
        """Only trigger a sync when meaningful fields change."""
        sync_fields = {
            'partner_id', 'client_order_ref', 'date_order', 'order_line',
            'state', 'pricelist_id', 'note', 'payment_term_id', 'user_id',
        }
        return bool(set(vals.keys()) & sync_fields)

    def _get_remote_config(self):
        return self.env['remote.sync.config'].search(
            [('active', '=', True)], limit=1
        )

    # ------------------------------------------------------------------
    # Public sync methods (called from queue processor with config passed)
    # ------------------------------------------------------------------

    def _remote_sync_create_with_config(self, config):
        self.ensure_one()
        if not config:
            return False
        return self._do_remote_create(config)

    def _remote_sync_write_with_config(self, config, vals):
        self.ensure_one()
        if not config:
            return False
        return self._do_remote_write(config, vals)

    def _remote_sync_unlink_with_config(self, config):
        self.ensure_one()
        if not config:
            return False
        return self._do_remote_unlink(config)

    # ------------------------------------------------------------------
    # CREATE on remote
    # ------------------------------------------------------------------

    def _do_remote_create(self, config):
        self.ensure_one()

        # 1. Partner
        remote_partner_id = self._remote_find_or_create_partner(config)
        if not remote_partner_id:
            if config.default_partner_remote_id:
                remote_partner_id = config.default_partner_remote_id
            else:
                _logger.warning("Remote Sync: partner not found and no fallback, skip order %s", self.name)
                return False

        # 2. Pricelist (optional)
        remote_pricelist_id = None
        if self.pricelist_id:
            remote_pricelist_id = self._remote_search_id_by_name(
                config, 'product.pricelist', self.pricelist_id.name
            )

        # 3. Payment term (optional)
        remote_term_id = None
        if self.payment_term_id:
            remote_term_id = self._remote_search_id_by_name(
                config, 'account.payment.term', self.payment_term_id.name
            )

        # 4. Order lines
        order_lines_cmd = self._build_lines_for_create(config)
        if not order_lines_cmd:
            _logger.warning("Remote Sync: no valid lines for order %s", self.name)
            return False

        # 5. Build order vals
        order_vals = {
            'partner_id': remote_partner_id,
            'client_order_ref': self.name,
            'date_order': fields.Datetime.to_string(self.date_order) if self.date_order else False,
            'order_line': order_lines_cmd,
        }
        if remote_pricelist_id:
            order_vals['pricelist_id'] = remote_pricelist_id
        if remote_term_id:
            order_vals['payment_term_id'] = remote_term_id
        if self.note:
            order_vals['note'] = self.note
        if self.user_id:
            remote_user = self._remote_search_id_by_name(config, 'res.users', self.user_id.name)
            if remote_user:
                order_vals['user_id'] = remote_user

        # 6. Create remotely
        remote_id = config._call_kw('sale.order', 'create', args=[order_vals])
        if remote_id:
            self.env['remote.sync.mapping'].set_mapping('sale.order', self.id, remote_id)
            self.with_context(skip_remote_sync=True).write({'remote_synced': True})
            _logger.info("Remote Sync: CREATED order %s → remote #%s", self.name, remote_id)
            return True

        _logger.error("Remote Sync: FAILED to create order %s", self.name)
        return False

    # ------------------------------------------------------------------
    # WRITE (update) on remote
    # ------------------------------------------------------------------

    def _do_remote_write(self, config, vals):
        self.ensure_one()

        remote_id = self.env['remote.sync.mapping'].get_remote_id('sale.order', self.id)
        if not remote_id:
            return self._do_remote_create(config)

        update_vals = {}

        # Partner
        if 'partner_id' in vals and self.partner_id:
            rid = self._remote_find_or_create_partner(config)
            if rid:
                update_vals['partner_id'] = rid

        # Pricelist
        if 'pricelist_id' in vals and self.pricelist_id:
            rid = self._remote_search_id_by_name(config, 'product.pricelist', self.pricelist_id.name)
            if rid:
                update_vals['pricelist_id'] = rid

        # Payment term
        if 'payment_term_id' in vals and self.payment_term_id:
            rid = self._remote_search_id_by_name(config, 'account.payment.term', self.payment_term_id.name)
            if rid:
                update_vals['payment_term_id'] = rid

        # Simple fields
        for fld in ('client_order_ref', 'date_order', 'note', 'state'):
            if fld in vals:
                val = self[fld]
                if isinstance(val, models.BaseModel):
                    update_vals[fld] = val.id if val else False
                elif hasattr(val, 'isoformat'):
                    update_vals[fld] = fields.Datetime.to_string(val) if val else False
                else:
                    update_vals[fld] = val or False

        # Order lines — full replacement
        if 'order_line' in vals:
            lines_cmd = self._build_lines_cmd_for_write(config)
            if lines_cmd is not None:
                update_vals['order_line'] = lines_cmd

        if not update_vals:
            return True  # nothing to sync

        result = config._call_kw('sale.order', 'write', args=[[remote_id], update_vals])
        if result:
            _logger.info("Remote Sync: UPDATED order %s (remote #%s)", self.name, remote_id)
            return True
        _logger.error("Remote Sync: FAILED to update %s", self.name)
        return False

    # ------------------------------------------------------------------
    # UNLINK (delete) from remote
    # ------------------------------------------------------------------

    def _do_remote_unlink(self, config):
        self.ensure_one()
        remote_id = self.env['remote.sync.mapping'].get_remote_id('sale.order', self.id)
        if not remote_id:
            return True  # not on remote, nothing to do

        result = config._call_kw('sale.order', 'unlink', args=[[remote_id]])
        if result:
            _logger.info("Remote Sync: DELETED order %s (remote #%s)", self.name, remote_id)
        else:
            _logger.error("Remote Sync: FAILED to delete remote #%s", remote_id)
        return result

    # ------------------------------------------------------------------
    # Build lines commands
    # ------------------------------------------------------------------

    def _build_lines_for_create(self, config):
        """Build x2many commands for creating order lines from scratch."""
        commands = []
        for line in self.order_line:
            if line.display_type:
                continue
            line_vals = self._build_single_line_vals(config, line)
            if line_vals:
                commands.append([0, 0, line_vals])
        return commands

    def _build_lines_cmd_for_write(self, config):
        """Full replacement: delete all remote lines, then recreate from local."""
        commands = []
        remote_id = self.env['remote.sync.mapping'].get_remote_id('sale.order', self.id)
        if remote_id:
            remote_lines = config._call_kw('sale.order.line', 'search',
                                           args=[[['order_id', '=', remote_id]]])
            if remote_lines:
                for rlid in remote_lines:
                    commands.append([2, rlid, 0])

        for line in self.order_line:
            if line.display_type:
                continue
            line_vals = self._build_single_line_vals(config, line)
            if line_vals:
                commands.append([0, 0, line_vals])
        return commands

    def _build_single_line_vals(self, config, line):
        """Build vals dict for a single order line."""
        remote_product_id = self._remote_find_or_create_product(config, line.product_id)
        if not remote_product_id:
            _logger.warning("Remote Sync: cannot sync product %s, skip line",
                            line.product_id.name)
            return None

        line_vals = {
            'product_id': remote_product_id,
            'product_uom_qty': line.product_uom_qty,
            'price_unit': line.price_unit,
            'name': line.name or line.product_id.name,
        }
        if line.product_uom:
            ruom = self._remote_search_id_by_name(config, 'uom.uom', line.product_uom.name)
            if ruom:
                line_vals['product_uom'] = ruom
        if line.tax_id:
            remote_tax_ids = [
                self._remote_search_id_by_name(config, 'account.tax', tax.name)
                for tax in line.tax_id
            ]
            remote_tax_ids = [t for t in remote_tax_ids if t]
            if remote_tax_ids:
                line_vals['tax_id'] = [[6, 0, remote_tax_ids]]
        return line_vals

    # ------------------------------------------------------------------
    # Partner helpers
    # ------------------------------------------------------------------

    def _remote_find_or_create_partner(self, config):
        partner = self.partner_id.commercial_partner_id
        if not partner:
            return None
        # Check mapping first
        rid = self.env['remote.sync.mapping'].get_remote_id('res.partner', partner.id)
        if rid:
            return rid
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
        # Create
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
            remote_country = self._remote_search_id_by_name(
                config, 'res.country', partner.country_id.name
            )
            if remote_country:
                partner_vals['country_id'] = remote_country

        rid = config._call_kw('res.partner', 'create', args=[partner_vals])
        if rid:
            self.env['remote.sync.mapping'].set_mapping('res.partner', partner.id, rid)
            _logger.info("Remote Sync: CREATED partner %s → remote #%s", partner.name, rid)
        return rid

    # ------------------------------------------------------------------
    # Product helpers
    # ------------------------------------------------------------------

    def _remote_find_or_create_product(self, config, product):
        if not product:
            return None
        # Mapping
        rid = self.env['remote.sync.mapping'].get_remote_id('product.product', product.id)
        if rid:
            return rid
        # Search by default_code
        if product.default_code:
            found = config._call_kw('product.product', 'search',
                                    args=[[['default_code', '=', product.default_code]]])
            if found:
                rid = found[0]
                self.env['remote.sync.mapping'].set_mapping('product.product', product.id, rid)
                return rid
        # Search by name
        found = config._call_kw('product.product', 'search',
                                args=[[['name', 'ilike', product.name]]])
        if found:
            rid = found[0]
            self.env['remote.sync.mapping'].set_mapping('product.product', product.id, rid)
            return rid
        # Create
        product_vals = {
            'name': product.name,
            'type': product.type or 'consu',
            'default_code': product.default_code or False,
        }
        if product.lst_price:
            product_vals['lst_price'] = product.lst_price
        if product.uom_id:
            ruom = self._remote_search_id_by_name(config, 'uom.uom', product.uom_id.name)
            if ruom:
                product_vals['uom_id'] = ruom
                product_vals['uom_po_id'] = ruom
        if product.categ_id:
            rcat = self._remote_search_id_by_name(
                config, 'product.category', product.categ_id.complete_name
            )
            if rcat:
                product_vals['categ_id'] = rcat

        rid = config._call_kw('product.product', 'create', args=[product_vals])
        if rid:
            self.env['remote.sync.mapping'].set_mapping('product.product', product.id, rid)
            _logger.info("Remote Sync: CREATED product %s → remote #%s", product.name, rid)
        return rid

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------

    def _remote_search_id_by_name(self, config, model, name):
        """Search a remote model by name, return the first id or None."""
        rid = config._call_kw(model, 'search', args=[[['name', 'ilike', name]], 0, 1])
        return rid[0] if rid else None
