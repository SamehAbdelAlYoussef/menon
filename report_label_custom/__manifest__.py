# -*- coding: utf-8 -*-

{
    'name': 'ovn-Barcode',
    'version': '18.0.0.2',
    'summary': '',
    'author': 'Sunil Prajapati',
    'sequence': 2,
    'description': """ """,
    'category': '',
    'website': 'https://sunilprajapati.pythonanywhere.com',
    'images': [],
    'depends': ['stock','product'],
    'data': [
        'views/product_views.xml',
        'views/stock_picking_view.xml',
        'reports/product_label_custom.xml',
        'reports/stock_label.xml',
        'data/server_action.xml',
    ],
    'assets': {
        'web.assets_backend': [
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'application': True,
    'auto_install': False,
}
