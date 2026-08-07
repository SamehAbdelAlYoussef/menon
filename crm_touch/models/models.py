import logging
from markupsafe import Markup
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class CrmStage(models.Model):
    _inherit = 'crm.stage'

    is_design_phase = fields.Boolean(
        string='Design Phase', default=False,
        help='Check this if this stage represents the Design Phase.',
    )
    design_phase_user_id = fields.Many2one(
        'res.users', string='Design Phase Salesperson',
        help='Leads entering this Design Phase stage will automatically '
             'send an email notification to this user.',
    )
    is_preview_uploaded = fields.Boolean(
        string='Preview Uploaded', default=False,
        help='Check this if uploading an attachment in this stage should '
             'automatically move the lead to the Design Phase stage.',
    )
    is_meeting_access = fields.Boolean(
        string='Meeting with Client', default=False,
        help='Check this if this stage requires a meeting with the client '
             'before proceeding.',
    )
    is_followup = fields.Boolean(
        string='Follow-up', default=False,
        help='Check this if this stage represents the Follow-up phase.',
    )
    is_synthetic_inspection = fields.Boolean(
        string='Contracts', default=False,
        help='Check this if this stage represents the Synthetic '
             'Inspection phase.',
    )
    is_installation_stage = fields.Boolean(
        string='Installation Stage', default=False,
        help='Installation Engineers can only see leads from this stage '
             'onwards.',
    )
    is_inspection_stage = fields.Boolean(
        string='Inspection Department Stage', default=False,
        help='Check this if this stage belongs to the Inspection '
             'Department. Users in the Inspection Department group '
             'will only see stages and leads marked with this flag.',
    )
    is_operations_stage = fields.Boolean(
        string='Operations Department Stage', default=False,
        help='Check this if this stage belongs to the Operations '
             'Department. Users in the Operations Department group '
             'will only see stages and leads marked with this flag.',
    )
    is_request_inspection = fields.Boolean(
        string='Request for Inspection', default=False,
        help='Check this if this stage is the "Request for Inspection" '
             'stage. When a salesperson is assigned to a lead in this '
             'stage, the lead auto-transitions to the "Preview Uploaded" '
             'stage.',
    )
    is_sales_person_stage = fields.Boolean(
        string='Sales Person Stage', default=False,
        help='Check this if this stage belongs to the Sales Person '
             'group. Users in the Sales Person group will only see '
             'stages and leads marked with this flag.',
    )
    is_sales_stage = fields.Boolean(
        string='Sales Stage', default=False,
        help='Check this if this stage belongs to the Sales group. '
             'Users in the Sales group will only see stages and leads '
             'marked with this flag.',
    )
    is_work_order_stage = fields.Boolean(
        string='Technical Office Stage', default=False,
        help='Check this if this stage belongs to the Technical Office '
             'group. Users in the Technical Office group will only see '
             'stages and leads marked with this flag.',
    )
    is_work_order_trigger = fields.Boolean(
        string='Technical Office', default=False,
        help='Check this if confirming Reading Two Files '
             'in this stage should auto-transition the lead to Won.',
    )


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _check_work_order_block(self):
        if self.env.user.has_group('crm_touch.group_work_order'):
            from odoo.exceptions import AccessError
            raise AccessError(
                'You do not have permission to access Sale Orders. '
                'Please contact your administrator.'
            )

    is_place_equipped = fields.Boolean(
        string='The Place is Equipped', default=False,
        tracking=True,
    )
    is_place_not_equipped = fields.Boolean(
        string='The Place is Not Equipped', default=False,
        tracking=True,
    )
    crm_lead_id = fields.Many2one(
        comodel_name='crm.lead', string='CRM Lead', ondelete='set null',
    )

    _sql_constraints = [
        ('check_place_equipment',
         'CHECK(NOT (is_place_equipped AND is_place_not_equipped))',
         'A place cannot be both equipped and unequipped at the same time!')
    ]

    def open_followup_wizard(self):
        self.ensure_one()
        from odoo.exceptions import UserError
        if not self.crm_lead_id:
            raise UserError(_('Please link a CRM lead first.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Follow-up Details'),
            'res_model': 'crm.place.inspection.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref(
                'crm_touch.crm_place_inspection_wizard_form_view'
            ).id,
            'target': 'new',
            'context': {'default_lead_id': self.crm_lead_id.id},
        }

    @api.constrains('is_place_equipped', 'is_place_not_equipped')
    def _check_place_inspection(self):
        for order in self:
            if (order.crm_lead_id
                    and not order.is_place_equipped
                    and not order.is_place_not_equipped):
                from odoo.exceptions import ValidationError
                raise ValidationError(_(
                    'Please select either "The Place is Equipped" or '
                    '"The Place is Not Equipped" before saving.'
                ))

    @api.model_create_multi
    def create(self, vals_list):
        self._check_work_order_block()
        for vals in vals_list:
            if vals.get('crm_lead_id') and not vals.get('order_line'):
                from odoo.exceptions import ValidationError
                raise ValidationError(_(
                    'You must add at least one Product, Section, '
                    'or Note to the Sales Order before saving.'
                ))

        records = super().create(vals_list)
        won_stage = None
        synthetic_stage = None
        for order in records:
            lead = order.crm_lead_id
            if not lead:
                continue

            if lead.stage_id.is_meeting_access:
                CrmStage = self.env['crm.stage'].sudo()
                order_name = order.name

                # ── Place NOT Equipped → Follow-up ────────────── #
                if order.is_place_not_equipped:
                    followup_stage = None
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
                    if followup_stage:
                        followup_notes = lead.pending_followup_notes or ''
                        stage_name = followup_stage.name

                        lead.with_context(
                            _skip_inspection_check=True
                        ).write({
                            'stage_id': followup_stage.id,
                            'user_id': False,
                            'pending_followup_date': False,
                            'pending_followup_notes': False,
                        })

                        # Post notes on SO
                        if followup_notes.strip():
                            order.message_post(
                                body=followup_notes,
                                message_type='comment',
                                subtype_xmlid='mail.mt_note',
                            )

                        # Post transition note on lead
                        msg = _(
                            'Place not equipped — lead moved to '
                            '<strong>%s</strong> after SO '
                            '<strong>#%s</strong>.'
                        ) % (stage_name, order_name)
                        sys_note = _('System Notification')
                        note_body = Markup(
                            '<div style="display:flex;flex-direction:column;'
                            'align-items:flex-start;max-width:85%%;'
                            'font-family:-apple-system,BlinkMacSystemFont,'
                            "'Segoe UI',Roboto,Helvetica,Arial,sans-serif;"
                            'margin:4px 0;">'
                            '<div style="display:inline-block;color:#0b4f83;'
                            'font-size:14px;padding:10px 14px;'
                            'border-radius:14px 14px 14px 0;'
                            'box-shadow:0 1px 1px rgba(0,0,0,0.06);'
                            'line-height:1.5;text-align:left;">%s</div>'
                            '<span style="font-size:11px;color:#707881;'
                            'margin-top:4px;margin-left:4px;'
                            'opacity:0.8;">%s</span>'
                            '</div>'
                        ) % (msg, sys_note)
                        lead.message_post(
                            body=note_body, message_type='comment',
                            subtype_xmlid='mail.mt_note',
                        )
                    else:
                        _logger.info(
                            'CRM Touch: No Follow-up stage — '
                            'lead "%s" stays in "%s".',
                            lead.name, lead.stage_id.name,
                        )
                    continue

                # ── Place Equipped → Synthetic Inspection ─────── #
                if synthetic_stage is None:
                    if lead.team_id:
                        synthetic_stage = CrmStage.search([
                            ('is_synthetic_inspection', '=', True),
                            ('team_id', '=', lead.team_id.id),
                        ], limit=1)
                    if not synthetic_stage:
                        synthetic_stage = CrmStage.search([
                            ('is_synthetic_inspection', '=', True),
                            ('team_id', '=', False),
                        ], limit=1)
                if synthetic_stage:
                    lead.with_context(
                        _skip_inspection_check=True
                    ).write({'stage_id': synthetic_stage.id})
                    stage_name = synthetic_stage.name
                    msg = _(
                        'Lead automatically moved to stage '
                        '<strong>%s</strong> after Sales Order '
                        '<strong>#%s</strong> was created.'
                    ) % (stage_name, order_name)
                    sys_note = _('System Notification')
                    message_body = Markup(
                        '<div style="display:flex;flex-direction:column;'
                        'align-items:flex-start;max-width:85%%;'
                        'font-family:-apple-system,BlinkMacSystemFont,'
                        "'Segoe UI',Roboto,Helvetica,Arial,sans-serif;"
                        'margin:4px 0;">'
                        '<div style="background-color:#e1f0fa;'
                        'color:#0b4f83;font-size:14px;padding:12px 16px;'
                        'border-radius:14px 14px 14px 0;'
                        'box-shadow:0 1px 1px rgba(0,0,0,0.05);'
                        'line-height:1.5;direction:ltr;'
                        'text-align:left;">%s</div>'
                        '<span style="font-size:11px;color:#707881;'
                        'margin-top:4px;margin-left:2px;'
                        'opacity:0.8;">%s</span>'
                        '</div>'
                    ) % (msg, sys_note)
                    lead.message_post(
                        body=message_body, message_type='comment',
                        subtype_xmlid='mail.mt_note',
                    )
                else:
                    _logger.info(
                        'CRM Touch: No Synthetic Inspection stage — '
                        'lead "%s" stays in "%s".',
                        lead.name, lead.stage_id.name,
                    )
                continue

            # ── Default: mark as Won ───────────────────────────── #
            if won_stage is None:
                won_stage = self.env['crm.stage'].sudo().search(
                    [('is_won', '=', True)], limit=1,
                )
            if not won_stage:
                continue
            if not lead.inspection_file:
                lead.message_post(
                    body=_(
                        'Sales Order <strong>%s</strong> was created '
                        'but the lead could not be marked as Won '
                        'because no inspection file has been '
                        'uploaded yet.'
                    ) % order.name,
                    message_type='comment',
                    subtype_xmlid='mail.mt_note',
                )
                continue
            lead.write({'stage_id': won_stage.id, 'probability': 100})
            stage_name = won_stage.name
            order_name = order.name
            msg = _(
                'Lead marked as <strong>Won</strong> automatically '
                'after Sales Order <strong>#%s</strong> was created.'
            ) % order_name
            sys_note = _('System Notification')
            message_body = Markup(
                '<div style="display:flex;flex-direction:column;'
                'align-items:flex-start;max-width:85%%;'
                'font-family:-apple-system,BlinkMacSystemFont,'
                "'Segoe UI',Roboto,Helvetica,Arial,sans-serif;"
                'margin:4px 0;">'
                '<div style="background-color:#d4edda;color:#155724;'
                'font-size:14px;padding:12px 16px;'
                'border-radius:14px 14px 14px 0;'
                'box-shadow:0 1px 1px rgba(0,0,0,0.05);'
                'line-height:1.5;direction:ltr;text-align:left;">%s</div>'
                '<span style="font-size:11px;color:#707881;'
                'margin-top:4px;margin-left:2px;'
                'opacity:0.8;">%s</span>'
                '</div>'
            ) % (msg, sys_note)
            lead.message_post(
                body=message_body, message_type='comment',
                subtype_xmlid='mail.mt_note',
            )
        return records

    def write(self, vals):
        self._check_work_order_block()
        res = super().write(vals)
        if self.env.context.get('_skip_so_line_check'):
            return res
        for order in self:
            if order.crm_lead_id and not order.order_line:
                from odoo.exceptions import ValidationError
                raise ValidationError(_(
                    'You must add at least one Product, Section, '
                    'or Note to the Sales Order before saving.'
                ))
        return res

    def unlink(self):
        self._check_work_order_block()
        return super().unlink()


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    @api.model_create_multi
    def create(self, vals_list):
        attachments = super().create(vals_list)
        for attachment in attachments:
            if attachment.res_model == 'crm.lead' and attachment.res_id:
                lead = self.env['crm.lead'].browse(attachment.res_id)
                if not lead.exists():
                    continue
                # Auto-set Upload Date on any file upload
                if not lead.inspection_upload_date:
                    lead.inspection_upload_date = fields.Date.today()
                if lead.stage_id.is_preview_uploaded:
                    self._handle_design_phase_transition(lead)
                # Any file uploaded in Request Inspection → Synthetic Inspection
                if lead.stage_id.is_request_inspection:
                    synthetic_stage = self.env['crm.stage'].sudo().search(
                        [('is_synthetic_inspection', '=', True)], limit=1,
                    )
                    if synthetic_stage and lead.stage_id.id != synthetic_stage.id:
                        lead.with_context(
                            _skip_meeting_transition=True,
                            _skip_request_inspection=True,
                        ).write({
                            'stage_id': synthetic_stage.id,
                        })
                # Any file uploaded in Synthetic Inspection → Work Order
                elif lead.stage_id.is_synthetic_inspection:
                    lead._transition_synthetic_to_work_order()
                # Work Order attachment uploaded in trigger → Work Order
                if lead.stage_id.is_work_order_trigger \
                        and attachment.res_field == 'work_order_attachment':
                    lead._transition_work_order_trigger_to_work_order()
                # Work Order attachment uploaded in Work Order stage → Won
                if lead.stage_id.is_work_order_stage \
                        and not lead.stage_id.is_work_order_trigger \
                        and attachment.res_field == 'work_order_attachment':
                    lead._transition_work_order_to_won()
        return attachments

    def _handle_design_phase_transition(self, lead):
        CrmStage = self.env['crm.stage'].sudo()
        design_stage = False
        if lead.team_id:
            design_stage = CrmStage.search([
                ('is_design_phase', '=', True),
                ('team_id', '=', lead.team_id.id),
            ], limit=1)
        if not design_stage:
            design_stage = CrmStage.search([
                ('is_design_phase', '=', True),
                ('team_id', '=', False),
            ], limit=1)
        if not design_stage:
            return
        lead.with_context(
            _skip_meeting_transition=True,
            _skip_attachment_check=True,
        ).write({
            'stage_id': design_stage.id, 'user_id': False,
        })
        self.env['bus.bus']._sendone(
            self.env.user.partner_id, 'crm_touch/reload', {})


