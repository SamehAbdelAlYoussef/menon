# -*- coding: utf-8 -*-
{
    'name': 'Product Stock by Warehouse',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Pivot view: products with available quantities across warehouses',
    'description': """
Product Stock by Warehouse
==========================

Adds a pivot view showing products (rows) × warehouses (cols)
with On Hand / Reserved quantities as measures.

Access: Inventory > Reporting > Product Stock by Warehouse
    """,
    'author': 'Sameh',
    'depends': ['sale', 'stock'],
    'data': [
        'views/stock_quant_views.xml',
        'views/sale_report_pivot.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
