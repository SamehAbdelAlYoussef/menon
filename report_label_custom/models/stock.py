from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'stock.picking'


    def print_labels(self):
        return self.env.ref('report_label_custom.action_report_stock_label_custom').report_action(self)
