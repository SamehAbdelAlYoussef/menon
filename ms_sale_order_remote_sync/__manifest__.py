{
    'name': 'MS Sale Order Remote Sync',
    'version': '18.0.1.0.0',
    'category': 'Sales',
    'summary': 'Sync Sale Orders to remote Odoo server via JSON-RPC',
    'description': """
        Real-time sync of Sale Orders (create/write/delete) to a remote Odoo server.
        Uses JSON-RPC API. Auto-searches partners & products on remote, creates if missing.
    """,
    'author': 'MS',
    'depends': ['sale_management'],
    'data': [
        'security/ir.model.access.csv',
        'views/remote_sync_config_views.xml',
        'views/remote_sync_queue_views.xml',
        'views/menu.xml',
        'data/cron.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
