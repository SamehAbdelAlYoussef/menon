from markupsafe import Markup
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class CrmPlaceInspectionWizard(models.TransientModel):
    _name = 'crm.place.inspection.wizard'
    _description = 'CRM Place Inspection Wizard'

    lead_id = fields.Many2one(
        'crm.lead', string='Lead', required=True, ondelete='cascade',
    )

    next_followup_date = fields.Datetime(
        string='Next Follow-up Date', required=True,
    )
    followup_notes = fields.Text(
        string='Follow-up Notes', required=True,
    )

    def action_confirm(self):
        self.ensure_one()
        lead = self.lead_id

        if not self.next_followup_date:
            raise UserError(_('Please set the next follow-up date.'))
        if not self.followup_notes:
            raise UserError(_('Please add follow-up notes.'))

        # Store data for SaleOrder.create()
        lead.write({
            'pending_followup_date': self.next_followup_date,
            'pending_followup_notes': self.followup_notes,
        })

        # 1. Create activity on the Lead IMMEDIATELY
        activity_type = (
            self.env.ref('mail.mail_activity_data_meeting',
                         raise_if_not_found=False)
            or self.env['mail.activity.type'].search(
                [('category', '=', 'meeting')], limit=1)
            or self.env['mail.activity.type'].search([], limit=1)
        )
        if activity_type:
            self.env['mail.activity'].create({
                'res_model_id': self.env['ir.model']._get_id('crm.lead'),
                'res_id': lead.id,
                'activity_type_id': activity_type.id,
                'date_deadline': self.next_followup_date.date(),
                'summary': _('Follow-up — Site not equipped'),
                'user_id': self.env.uid,
            })

        # 2. Post follow-up note on the lead chatter IMMEDIATELY
        notes_content = self.followup_notes or ''
        title = _('Follow-up')
        message_body = Markup(
            '<div style="font-family:-apple-system,BlinkMacSystemFont,'
            '\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;margin:8px 0;'
            'padding:12px 16px;background-color:#f0f7fc;'
            'border-left:4px solid #00629b;border-radius:6px;'
            'box-shadow:0 1px 3px rgba(0,0,0,0.05);">'
            '<div style="display:flex;align-items:center;margin-bottom:6px;">'
            '<strong style="color:#00629b;font-size:13px;font-weight:600;">'
            '<i class="fa fa-reply-all" style="margin-right:6px;"/>%s'
            '</strong></div>'
            '<p style="margin:0;white-space:pre-wrap;color:#2d3748;'
            'font-size:13px;line-height:1.5;">%s</p>'
            '</div>'
        ) % (title, notes_content)
        lead.message_post(
            body=message_body,
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )

        return {
            'type': 'ir.actions.act_window_close',
            'infos': _('Activity created! Save the Sales Order to complete.'),
        }
