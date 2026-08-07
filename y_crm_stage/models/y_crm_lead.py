from odoo import models, api
from odoo.osv import expression

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        if self.env.user.y_allowed_stage_ids and not self.env.su:
            domain = expression.AND([domain or [], [('stage_id', 'in', self.env.user.y_allowed_stage_ids.ids)]])
        return super()._search(domain, offset=offset, limit=limit, order=order)
