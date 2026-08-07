# -*- coding: utf-8 -*-
from odoo import fields, models, api


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    employee_serial = fields.Char(
        string='Employee Serial',
        copy=False,
        readonly=False,
        tracking=True,
        index=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('hr.employee.serial'),
        help="Unique serial number assigned to each employee. Automatically generated from sequence.",
    )

    _sql_constraints = [
        (
            'unique_employee_serial',
            'UNIQUE(employee_serial)',
            'The Employee Serial number must be unique! Another employee already has this serial number.',
        ),
    ]
