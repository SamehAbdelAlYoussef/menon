# -*- coding: utf-8 -*-
{
    'name': 'Restrict Journal Entries Menu',
    'version': '18.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Restrict Journal Entries & Dashboard menus to specific groups only',
    'description': """
        This module creates security groups to restrict access to:
        1. "Journal Entries" menu under Accounting → only visible to users with "Journal Entries views" group
        2. "Dashboards" application → only visible to users with "Dashboard Viewer" group or Dashboard Admin

        Without these groups, the menus are completely hidden from ALL users.
    """,
    'author': 'Custom',
    'license': 'LGPL-3',
    'depends': ['account', 'spreadsheet_dashboard'],
    'data': [
        'views/menuitem_override.xml',
        'views/dashboard_menuitem_override.xml',
    ],
    'installable': True,
    'auto_install': False,
}
