# -*- coding: utf-8 -*-
{
    'name': 'Menon Furniture - Sale Report Arabic',
    'version': '18.0.2.1.0',
    'summary': 'Arabic Sale Order Reports with Terms & Conditions',
    'author': 'Sayed Mohamed',
    'category': 'Sales',
    'depends': ['sale', 'account'],

    'data': [
        'reports/sales_order_report_ar.xml',
        'views/sales_order_view.xml',
        'views/sale_report_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'LGPL-3',
}