# -*- coding: utf-8 -*-
import json
import logging

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class RemoteSyncQueue(models.Model):
    _name = 'remote.sync.queue'
    _description = 'Remote Sync Queue'
    _order = 'create_date asc'

    model = fields.Char('Model', required=True, index=True)
    local_id = fields.Integer('Local Record ID', required=True, index=True)
    operation = fields.Selection(
        [('create', 'Create'), ('write', 'Write'), ('unlink', 'Delete')],
        required=True, index=True,
    )
    state = fields.Selection(
        [('pending', 'Pending'), ('processing', 'Processing'),
         ('done', 'Done'), ('failed', 'Failed')],
        default='pending', index=True,
    )
    values = fields.Text('Values (JSON)', help='Serialized vals dict for write operations')
    error_message = fields.Text('Error Message')
    retry_count = fields.Integer('Retries', default=0)
    max_retries = fields.Integer('Max Retries', default=5)
    create_date = fields.Datetime('Queued At', index=True)
    process_date = fields.Datetime('Processed At')

    # ------------------------------------------------------------------
    # Cron: process the queue
    # ------------------------------------------------------------------

    def _process_queue(self, limit=20):
        """Process pending queue items. Called by cron job."""
        config = self.env['remote.sync.config'].search(
            [('active', '=', True)], limit=1
        )
        if not config:
            _logger.debug("Remote Sync Queue: no active config, skipping")
            return False

        items = self.search(
            [('state', 'in', ('pending', 'failed'))],
            limit=limit, order='create_date asc',
        )
        # Filter in Python: Odoo domains don't support field-vs-field comparison
        items = items.filtered(lambda r: r.retry_count < r.max_retries)
        if not items:
            return True

        # Mark as processing
        items.write({'state': 'processing'})

        for item in items:
            try:
                self._process_item(item, config)
            except Exception as e:
                _logger.exception("Remote Sync Queue: unhandled error for item #%s", item.id)
                item.write({
                    'state': 'failed',
                    'error_message': str(e),
                    'retry_count': item.retry_count + 1,
                })

        return True

    # ------------------------------------------------------------------
    # Dispatch to the correct sync handler
    # ------------------------------------------------------------------

    def _process_item(self, item, config):
        """Route a queue item to its sync method."""
        if item.operation == 'unlink':
            # Record is already deleted locally — use mapping table directly
            success = self._process_unlink(item, config)
        else:
            SaleOrder = self.env['sale.order'].with_context(skip_remote_sync=True)
            record = SaleOrder.browse(item.local_id)

            if not record.exists():
                _logger.warning("Remote Sync Queue: record %s/%s no longer exists",
                                item.model, item.local_id)
                item.write({'state': 'done', 'process_date': fields.Datetime.now()})
                return

            if item.operation == 'create':
                success = record._remote_sync_create_with_config(config)
            elif item.operation == 'write':
                vals = json.loads(item.values) if item.values else {}
                success = record._remote_sync_write_with_config(config, vals)
            else:
                success = False
                item.error_message = f'Unknown operation: {item.operation}'

        if success:
            item.write({'state': 'done', 'process_date': fields.Datetime.now(), 'error_message': False})
        else:
            item.write({
                'state': 'failed',
                'retry_count': item.retry_count + 1,
                'error_message': item.error_message or 'Sync returned False',
            })

    # ------------------------------------------------------------------
    # Unlink handler (record is already gone, use mapping table)
    # ------------------------------------------------------------------

    def _process_unlink(self, item, config):
        """Delete the remote order using the mapping table to find remote_id."""
        remote_id = self.env['remote.sync.mapping'].get_remote_id(item.model, item.local_id)
        if not remote_id:
            # Not on remote, nothing to do — mark done
            return True

        result = config._call_kw('sale.order', 'unlink', args=[[remote_id]])
        if result:
            # Clean up the local→remote mapping for this deleted order
            mapping = self.env['remote.sync.mapping'].search([
                ('model', '=', item.model), ('local_id', '=', item.local_id),
            ])
            mapping.unlink()
            _logger.info("Remote Sync Queue: DELETED remote sale.order #%s", remote_id)
            return True
        _logger.error("Remote Sync Queue: FAILED to delete remote sale.order #%s", remote_id)
        return False

    # ------------------------------------------------------------------
    # Enqueue helpers — called by sale.order hooks
    # ------------------------------------------------------------------

    @api.model
    def enqueue_create(self, order_id):
        """Fast DB insert: schedule a create sync."""
        self.create({
            'model': 'sale.order',
            'local_id': order_id,
            'operation': 'create',
        })

    @api.model
    def enqueue_write(self, order_id, vals):
        """Fast DB insert: schedule a write sync with serialized vals."""
        # Only serialize sync-relevant keys to keep payload small
        sync_fields = {
            'partner_id', 'client_order_ref', 'date_order', 'order_line',
            'state', 'pricelist_id', 'note', 'payment_term_id', 'user_id',
        }
        slim = {k: v for k, v in vals.items() if k in sync_fields}
        self.create({
            'model': 'sale.order',
            'local_id': order_id,
            'operation': 'write',
            'values': json.dumps(slim),
        })

    @api.model
    def enqueue_unlink(self, order_id):
        """Fast DB insert: schedule a delete sync."""
        self.create({
            'model': 'sale.order',
            'local_id': order_id,
            'operation': 'unlink',
        })
