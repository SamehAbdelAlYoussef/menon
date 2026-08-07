{
    'name': 'Restricted CRM Stages',
    'version': '18.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': 'Restrict CRM stage visibility for a specific group',
    'author': 'yasser mohamed abd alwadood',
    'website': 'https://www.yasserodoo.com',
    'email': 'yasserodoodev@gmail.com',
    'depends': ['crm'],
    'data': [
        'security/y_crm_stage_security.xml',
        'views/y_crm_stage_views.xml',
        'views/y_res_users_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
