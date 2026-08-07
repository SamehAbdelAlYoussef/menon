# -*- coding: utf-8 -*-
{
    'name': 'Sale Order Ready for Delivery',
    'version': '18.0.1.0.0',
    'category': 'Sales',
    'summary': 'Auto-check product availability and notify when orders are ready for delivery',
    'description': """
Sale Order Ready for Delivery
=============================
Automatically checks whether all products in a sales order are available in stock
and notifies users when the order becomes ready for delivery.

Key Features:
- Monitors product availability (virtual_available) for each order line
- Marks sales orders as "Ready for Delivery" when all products are in stock
- Sends real-time notifications to all active users
- Adds users as followers of ready orders
- Posts messages in the chatter
- Auto-recalculates on order save, stock receipt, and scheduled cron job
- Service products are excluded from availability checks
- Multi-warehouse aware

Triggers:
1. Sales order creation or modification
2. Stock picking validation (incoming receipts)
3. Scheduled cron job every 30 minutes (safety net)
    """,
    'author': 'Touch Sales',
    'website': '',
    'depends': ['sale_management', 'stock', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_order_view.xml',
        'data/cron_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
