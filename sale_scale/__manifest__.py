# -*- coding: utf-8 -*-
{
    'name': 'Sale Scale (الميزان)',
    'version': '18.0.4.4.0',
    'category': 'Sales',
    'summary': 'Scale (الميزان) with discount on sale & purchase order lines',
    'description': """
Sale Scale
==========
- Scale (الميزان) model with a discount value
- Scale + Scale Discount % + Qty After Discount fields on sale & purchase order lines
- Scale discount auto-filled when a scale is selected
- Scale menu under Sales and Purchase
    """,
    'author': 'Touch Sales',
    'depends': ['sale_management', 'purchase','stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/scale_views.xml',
        'views/sale_order_views.xml',
        'views/purchase_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
