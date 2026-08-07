from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'


    def print_labels(self):
        return self.env.ref('report_label_custom.action_report_product_template_label_custom').report_action(self)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('barcode'):
                try:
                    vals['barcode'] = self.env['ir.sequence'].next_by_code('product.template.barcode')
                except Exception as e:
                    # Log the error but don't block creation
                    self.env.cr.rollback()  # rollback the failed sequence to avoid gaps
                    self.env.cr.commit()  # commit again to keep prior operations
                    _logger.error("Failed to generate barcode sequence: %s", str(e))

        return super(ProductTemplate, self).create(vals_list)