# -*- coding: utf-8 -*-
from odoo import fields, models


class ScaleScale(models.Model):
    _name = 'scale.scale'
    _description = 'Scale (الميزان)'
    _order = 'name'

    name = fields.Char(string='نوع الميزان', required=True)
    discount = fields.Float(string='خصم الميزان %', digits='Discount')
    active = fields.Boolean(default=True)
