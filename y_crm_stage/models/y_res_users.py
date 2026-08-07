from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'

    y_allowed_stage_ids = fields.Many2many(
        'crm.stage',
        'y_res_users_crm_stage_rel',
        'user_id',
        'stage_id',
        string='Allowed CRM Stages',
        help='If specified, this user will ONLY see these stages and the leads within them.'
    )
