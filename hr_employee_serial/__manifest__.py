# -*- coding: utf-8 -*-
{
    'name': 'HR Employee Serial Number',
    'version': '18.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Add a unique serial number field to employee records',
    'description': """
HR Employee Serial Number
=========================
Adds a unique employee serial/reference number field to the employee form.

Features:
- New field "Employee Serial" (unique) added after Job Position in the employee form.
- SQL constraint ensures no two employees can share the same serial number.
- Auto-computed default serial number from a dedicated sequence.
    """,
    'author': '',
    'depends': ['hr'],
    'data': [
        'data/ir_sequence.xml',
        'views/hr_employee_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
