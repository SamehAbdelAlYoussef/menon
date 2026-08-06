# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class RemoteSyncMapping(models.Model):
    _name = 'remote.sync.mapping'
    _description = 'Local ↔ Remote ID Mapping'

    model = fields.Char('Model', required=True, index=True)
    local_id = fields.Integer('Local ID', required=True, index=True)
    remote_id = fields.Integer('Remote ID', required=True, index=True)

    _sql_constraints = [
        ('model_local_uniq', 'unique(model, local_id)',
         'Each local record can only be mapped once per model.'),
    ]

    @api.model
    def get_remote_id(self, model, local_id):
        """Return the remote id for a local record, or None."""
        mapping = self.search(
            [('model', '=', model), ('local_id', '=', local_id)], limit=1
        )
        return mapping.remote_id if mapping else None

    @api.model
    def set_mapping(self, model, local_id, remote_id):
        """Create a mapping, silently ignoring duplicates."""
        existing = self.search(
            [('model', '=', model), ('local_id', '=', local_id)], limit=1
        )
        if existing:
            existing.write({'remote_id': remote_id})
        else:
            self.create({
                'model': model,
                'local_id': local_id,
                'remote_id': remote_id,
            })
