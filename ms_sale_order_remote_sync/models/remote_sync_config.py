# -*- coding: utf-8 -*-
import json
import logging
import urllib.request
import urllib.error

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class RemoteSyncConfig(models.Model):
    _name = 'remote.sync.config'
    _description = 'Remote Odoo Sync Configuration'

    name = fields.Char('Name', default='Remote Odoo Server')
    active = fields.Boolean('Active', default=True)
    target_url = fields.Char('Target URL', required=True, default='https://menon-furn.com')
    target_db = fields.Char('Target Database', required=True, default='Menon')
    username = fields.Char('Username', required=True,
                           default='menunsale@gmail.com')
    password = fields.Char('Password', required=True,
                           default='4a391d1b8b8e2780ab372620c54b805fcfb95fc9')
    default_partner_remote_id = fields.Integer(
        'Default Remote Partner ID',
        help='Fallback partner ID on remote server when customer is not found'
    )

    # ---- Actions ----
    def test_connection(self):
        """Button action: test authentication and connectivity."""
        self.ensure_one()
        uid = self._authenticate()
        if uid:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection OK'),
                    'message': _('Authenticated successfully (uid=%s).', uid),
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Failed'),
                    'message': _('Could not authenticate. Check credentials and server URL.'),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    # ---- RPC helpers (no external deps) ----
    def _rpc(self, service, method, args=None, kwargs=None, session_id=None):
        """Low‑level JSON‑RPC call to the remote Odoo.
        Returns the 'result' key on success, or None on failure.
        """
        self.ensure_one()
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "call",
            "params": {
                "service": service,
                "method": method,
                "args": args or [],
                "kwargs": kwargs or {},
            },
        }
        data = json.dumps(payload).encode('utf-8')
        url = f"{self.target_url}/jsonrpc"
        req = urllib.request.Request(
            url, data=data,
            headers={'Content-Type': 'application/json'},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode('utf-8'))
        except urllib.error.URLError as e:
            _logger.error("Remote Sync: connection error: %s", e)
            return None
        except Exception as e:
            _logger.error("Remote Sync: RPC error: %s", e)
            return None

        if result.get('error'):
            _logger.error("Remote Sync: RPC fault: %s", result['error'])
            return None
        return result.get('result')

    def _authenticate(self):
        """Return a session_id (uid) string, or None."""
        self.ensure_one()
        result = self._rpc('common', 'authenticate',
                           args=[self.target_db, self.username, self.password, {}])
        if result and isinstance(result, int):
            return result
        _logger.error("Remote Sync: authentication failed")
        return None

    def _call_kw(self, model, method, args=None, kwargs=None):
        """High‑level call through /jsonrpc (model‑scoped)."""
        uid = self._authenticate()
        if uid is None:
            return None
        return self._rpc('object', 'execute_kw',
                         args=[self.target_db, uid, self.password,
                               model, method, args or [], kwargs or {}])
