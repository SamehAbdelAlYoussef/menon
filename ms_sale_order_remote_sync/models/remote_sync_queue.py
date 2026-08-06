# -*- coding: utf-8 -*-
import json
import logging

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

# Map model name → remote model name (usually same, but can differ)
MODEL_MAP = {
    'sale.order': 'sale.order',
    'account.payment': 'account.payment',
}


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
        items = items.filtered(lambda r: r.retry_count < r.max_retries)
        if not items:
            return True

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

        # Clean up successful (done) records — keep failed for debugging
        self._cleanup_done()
        return True

    def _cleanup_done(self):
        """Delete all successfully processed (done) queue records."""
        done = self.search([('state', '=', 'done')])
        if done:
            count = len(done)
            done.unlink()
            _logger.info("Remote Sync Queue: cleaned up %s done record(s)", count)

    # ------------------------------------------------------------------
    # Dispatch — generic, routes by item.model
    # ------------------------------------------------------------------

    def _process_item(self, item, config):
        """Route a queue item to its model's sync handler."""
        if item.operation == 'unlink':
            success = self._process_unlink(item, config)
        else:
            model_name = item.model
            record = self.env[model_name].with_context(skip_remote_sync=True).browse(item.local_id)

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
    # Unlink handler — generic (record is already gone, use mapping table)
    # ------------------------------------------------------------------

    def _process_unlink(self, item, config):
        """Delete the remote record using the mapping table to find remote_id."""
        remote_model = MODEL_MAP.get(item.model, item.model)
        remote_id = self.env['remote.sync.mapping'].get_remote_id(item.model, item.local_id)
        if not remote_id:
            return True  # Not on remote, nothing to do

        result = config._call_kw(remote_model, 'unlink', args=[[remote_id]])
        if result:
            # Clean up mapping
            mapping = self.env['remote.sync.mapping'].search([
                ('model', '=', item.model), ('local_id', '=', item.local_id),
            ])
            mapping.unlink()
            _logger.info("Remote Sync Queue: DELETED remote %s #%s", remote_model, remote_id)
            return True
        _logger.error("Remote Sync Queue: FAILED to delete remote %s #%s", remote_model, remote_id)
        return False

    # ------------------------------------------------------------------
    # Enqueue helpers
    # ------------------------------------------------------------------

    @api.model
    def enqueue(self, model, local_id, operation, vals=None):
        """Generic enqueue: schedule any model's sync operation."""
        values_json = None
        if vals:
            # Convert recordset values to ids for JSON serialization
            clean = {}
            for k, v in vals.items():
                if hasattr(v, 'id'):
                    clean[k] = v.id
                elif isinstance(v, list) and v and hasattr(v[0], 'id'):
                    clean[k] = [x.id for x in v]
                else:
                    clean[k] = v
            values_json = json.dumps(clean)
        self.create({
            'model': model,
            'local_id': local_id,
            'operation': operation,
            'values': values_json,
        })

    @api.model
    def enqueue_create(self, order_id):
        """Fast DB insert: schedule a sale.order create sync."""
        self.create({
            'model': 'sale.order',
            'local_id': order_id,
            'operation': 'create',
        })

    @api.model
    def enqueue_write(self, order_id, vals):
        """Fast DB insert: schedule a sale.order write sync."""
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
        """Fast DB insert: schedule a sale.order delete sync."""
        self.create({
            'model': 'sale.order',
            'local_id': order_id,
            'operation': 'unlink',
        })

    # ------------------------------------------------------------------
    # Payment-specific enqueue helpers
    # ------------------------------------------------------------------

    @api.model
    def enqueue_payment_create(self, payment_id):
        self.create({
            'model': 'account.payment',
            'local_id': payment_id,
            'operation': 'create',
        })

    @api.model
    def enqueue_payment_write(self, payment_id, vals):
        sync_fields = {'amount', 'payment_type', 'date', 'sale_order_id',
                       'journal_id', 'partner_id', 'payment_reference', 'memo'}
        slim = {k: v for k, v in vals.items() if k in sync_fields}
        self.create({
            'model': 'account.payment',
            'local_id': payment_id,
            'operation': 'write',
            'values': json.dumps(slim),
        })

    @api.model
    def enqueue_payment_unlink(self, payment_id):
        self.create({
            'model': 'account.payment',
            'local_id': payment_id,
            'operation': 'unlink',
        })
