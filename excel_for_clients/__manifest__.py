# -*- coding: utf-8 -*-
{
    'name': 'CRM XLSX Report',
    'version': '18.0.1.0.0',
    'category': 'CRM',
    'summary': 'Export CRM Leads/Opportunities to Excel (Campaign Daily Sheet)',
    'depends': ['base', 'crm', 'mail', 'bus'],
    'data': [
        # 'security/ir.model.access.csv',
        'views/crm_lead_view.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}