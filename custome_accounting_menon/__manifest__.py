# -*- coding: utf-8 -*-
{
    'name': 'Menon - Accounting Customization',
    'version': '18.0.1.0.0',
    'category': 'Accounting',
    'summary': 'General Ledger account filter + Installment company fields',
    'author': 'Custom',
    'license': 'LGPL-3',
    'depends': ['account_reports'],
    'data': [
        'security/ir.model.access.csv',
        'data/general_ledger_patch.xml',
        'reports/taqseet_report_template.xml',
        'reports/taqseet_report_actions.xml',
        'wizard/taqseet_excel_wizard_views.xml',
        'views/account_account_views.xml',
        'views/taqseet_report_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'custome_accounting_menon/static/src/components/filter_account/filter_account.xml',
            'custome_accounting_menon/static/src/components/filter_account/filter_account.js',
        ],
    },
    'installable': True,
    'auto_install': False,
}
