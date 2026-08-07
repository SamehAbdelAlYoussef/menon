from markupsafe import Markup
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class CrmMeetingActionWizard(models.TransientModel):
    _name = 'crm.meeting.action.wizard'
    _description = 'CRM Meeting Action Wizard'

    lead_id = fields.Many2one(
        comodel_name='crm.lead',
        string='Lead / Opportunity',
        required=True,
        ondelete='cascade',
    )
    is_meeting_access = fields.Boolean(
        string='Meeting Access',
        default=False,
    )
    action_type = fields.Selection(
        selection=[
            ('contract', 'Contract — Create Sales Order'),
            ('followup', 'Follow-up — Schedule Meeting'),
            ('cancel', 'Cancel Opportunity'),
        ],
        string='Action',
    )
    next_followup_date = fields.Datetime(
        string='Next Follow-up Date',
    )
    followup_notes = fields.Text(
        string='Follow-up Notes',
        help='Add notes before scheduling the follow-up meeting.',
    )
    lost_reason_id = fields.Many2one(
        comodel_name='crm.lost.reason',
        string='Lost Reason',
    )

    # ------------------------------------------------------------------ #
    #  Main action                                                         #
    # ------------------------------------------------------------------ #

    def action_apply(self):
        self.ensure_one()

        if not self.is_meeting_access:
            raise UserError(_('Meeting actions are not available for this stage.'))
        if not self.action_type:
            raise UserError(_('Please select an action type.'))

        lead = self.lead_id

        # ── CONTRACT ────────────────────────────────────────────────── #
        if self.action_type == 'contract':
            if not lead.partner_id:
                raise UserError(_(
                    'The lead must have a customer set before creating a Sales Order.'
                ))

            # Open Sale Order form directly.
            # The SO form has the is_place_equipped / is_place_not_equipped
            # fields that handle the inspection flow.
            ctx = {
                'default_partner_id': lead.partner_id.id,
                'default_origin': lead.name,
                'default_crm_lead_id': lead.id,
            }
            if 'opportunity_id' in self.env['sale.order']._fields:
                ctx['default_opportunity_id'] = lead.id

            return {
                'type': 'ir.actions.act_window',
                'name': _('New Sales Order'),
                'res_model': 'sale.order',
                'view_mode': 'form',
                'views': [(False, 'form')],
                'target': 'new',
                'context': ctx,
            }

        # ── FOLLOW-UP ───────────────────────────────────────────────── #
        elif self.action_type == 'followup':
            if not self.next_followup_date:
                raise UserError(_('Please set the next follow-up date.'))
            if not self.followup_notes:
                raise UserError(_(
                    'Please add follow-up notes before scheduling the meeting.'
                ))

            # Find a stage with is_followup == True (team-specific, then global)
            CrmStage = self.env['crm.stage']
            followup_stage = False
            if lead.team_id:
                followup_stage = CrmStage.search([
                    ('is_followup', '=', True),
                    ('team_id', '=', lead.team_id.id),
                ], limit=1)
            if not followup_stage:
                followup_stage = CrmStage.search([
                    ('is_followup', '=', True),
                    ('team_id', '=', False),
                ], limit=1)
            if not followup_stage:
                raise UserError(_(
                    'No Follow-up stage found. Please configure a stage '
                    'with the "Follow-up" checkbox enabled first.'
                ))
            # Post the note FIRST so the validation _check_stage_requires_note passes
            notes_content = self.followup_notes or ""

            followup_title = _('Follow-up')
            sys_note = _('System Notification')
            message_body = Markup(
                '<div style="display:block;max-width:85%%;font-family:'
                '-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,'
                'Helvetica,Arial,sans-serif;margin:8px 0;text-align:left;">'
                '<div class="bg-success" style="display:inline-block;'
                'color:#0b4f83;font-size:14px;padding:10px 14px;'
                'border-radius:14px 14px 14px 0;box-shadow:0 1px 1px '
                'rgba(0,0,0,0.06);line-height:1.5;text-align:left;">'
                '<div style="margin-bottom:6px;white-space:nowrap;">'
                '<i class="fa fa-commenting-o" style="color:#00629b;'
                'font-size:14px;margin-right:6px;display:inline-block;'
                'vertical-align:middle;"/>'
                '<strong style="color:#00629b;font-size:13px;display:'
                'inline-block;vertical-align:middle;">%s</strong>'
                '</div>'
                '<p style="margin:0;white-space:pre-wrap;color:#1f2937;'
                'text-align:left;">%s</p>'
                '</div>'
                '<div style="font-size:11px;color:#707881;margin-top:4px;'
                'margin-left:4px;opacity:0.8;">%s</div>'
                '</div>'
            ) % (followup_title, notes_content, sys_note)

            lead.message_post(
                body=message_body,
                message_type='comment',
                subtype_xmlid='mail.mt_note',
            )
            # Move to Follow-up + unassign salesperson.
            # Unassigning is required so the "Personal Leads" rule (172)
            # allows other users to see the lead after transition.
            lead.with_context(_skip_meeting_transition=True).write({
                'stage_id': followup_stage.id,
                'user_id': False,
            })

            activity_type = (
                self.env.ref('mail.mail_activity_data_meeting', raise_if_not_found=False)
                or self.env['mail.activity.type'].search([('category', '=', 'meeting')], limit=1)
                or self.env['mail.activity.type'].search([], limit=1)
            )

            self.env['mail.activity'].create({
                'res_model_id': self.env['ir.model']._get_id('crm.lead'),
                'res_id': lead.id,
                'activity_type_id': activity_type.id,
                'date_deadline': self.next_followup_date.date(),
                'summary': _('Follow-up with client'),
                'user_id': self.env.uid,
            })

            return {'type': 'ir.actions.act_window_close'}

        # ── CANCEL / LOST ───────────────────────────────────────────── #
        elif self.action_type == 'cancel':
            if not self.lost_reason_id:
                raise UserError(_('Please select a lost reason before cancelling.'))

            lead.write({'lost_reason_id': self.lost_reason_id.id})
            lead.action_archive()

            return {'type': 'ir.actions.act_window_close'}
