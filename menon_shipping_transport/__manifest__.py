# -*- coding: utf-8 -*-
{
    'name': 'Menon Shipping Transport',
    'version': '18.0.1.0.0',
    'summary': 'Add Shipping & Transport cost to Sale Order total',
    'author': 'Sayed Mohamed',
    'category': 'Sales',
    'depends': ['sale','sale_management'],

    'data': [
        'security/ir.model.access.csv',
        'data/product_data.xml',
        'views/sale_order_views.xml',
        'wizard/shipping_transport_wizard_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}