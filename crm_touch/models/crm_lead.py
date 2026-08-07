import logging
from collections import defaultdict
from datetime import timedelta
from markupsafe import Markup

# Per-request flag to prevent duplicate bus notifications
_notified_users = defaultdict(bool)
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    # ── Fields ─────────────────────────────────────────────────────── #
    assigned_stage_sequence = fields.Integer(
        string='Assignment Stage Sequence',
        default=0,
        copy=False,
        help='Sequence of the stage at the moment the salesperson was '
             'assigned.  0 = never assigned or assignment cleared. '
             'Used by _search to hide the lead when it moves backward.',
    )
    current_stage_sequence = fields.Integer(
        string='Current Stage Sequence',
        related='stage_id.sequence',
        store=True,
    )

    is_meeting_access = fields.Boolean(
        related='stage_id.is_meeting_access',
        string='Meeting Access',
    )
    is_synthetic_inspection = fields.Boolean(
        related='stage_id.is_synthetic_inspection',
        string='Synthetic Inspection',
    )
    is_won_stage = fields.Boolean(
        related='stage_id.is_won',
        string='Won Stage',
    )
    is_preview_uploaded = fields.Boolean(
        related='stage_id.is_preview_uploaded',
        string='Preview Uploaded Stage',
    )
    no_response = fields.Boolean(
        string='No Response',
        default=False,
        tracking=True,
    )
    preview_attachment = fields.Many2many(
        'ir.attachment',
        string='Preview Uploaded',
        relation='crm_lead_preview_attachment_rel',
    )

    inspection_file = fields.Binary(
        string='Contracts',
        attachment=True,
        help='Upload Contracts files.',
    )
    inspection_file_name = fields.Char(
        string='Contracts',
        tracking=True,
    )
    inspection_upload_date = fields.Date(
        string='Last Upload Date',
        tracking=True,
    )
    # Pending follow-up data set by the Place Inspection wizard
    # from the Sale Order form.  Processed and cleared by SaleOrder.create().
    pending_followup_date = fields.Datetime(string='Pending Follow-up Date')
    pending_followup_notes = fields.Text(string='Pending Follow-up Notes')

    # ── Validations ────────────────────────────────────────────────── #
    @api.constrains('stage_id')
    def _check_stage_requires_attachment(self):
        for lead in self:
            stage = lead.stage_id
            if not (stage.is_design_phase or stage.is_meeting_access):
                continue
            if self.env.context.get('_skip_attachment_check'):
                continue
            if not lead.preview_attachment:
                raise ValidationError(_(
                    'A preview attachment must be uploaded before '
                    'moving the lead to stage "%s".'
                ) % stage.name)

    @api.constrains('stage_id')
    def _check_stage_requires_quotation(self):
        for lead in self:
            if not lead.stage_id.is_synthetic_inspection:
                continue
            has_quotation = self.env['sale.order'].sudo().search_count([
                ('crm_lead_id', '=', lead.id),
            ])
            if not has_quotation:
                raise ValidationError(_(
                    'The lead must have at least one Sales Order / Quotation '
                    'before moving to the "%s" stage.'
                ) % lead.stage_id.name)

    @api.constrains('stage_id')
    def _check_won_requires_inspection_file(self):
        for lead in self:
            if not lead.stage_id.is_won:
                continue
            # Skip inspection file check if Reading Two Files is confirmed
            if lead.reading_two_files:
                continue
            if not lead.inspection_file:
                raise ValidationError(_(
                    'An inspection file must be uploaded in the '
                    '"Upload Inspection Files" field before '
                    'marking the lead as Won.'
                ))

    @api.constrains('stage_id')
    def _check_stage_requires_salesperson(self):
        """Salesperson must be assigned when lead is past New stage."""
        for lead in self:
            if not lead.user_id and lead.stage_id.is_request_inspection:
                raise ValidationError(_(
                    'A salesperson must be assigned before this stage.'
                ))

    @api.constrains('stage_id')
    def _check_stage_requires_note(self):
        for lead in self:
            if not lead.stage_id.is_followup:
                continue
            has_note = self.env['mail.message'].search_count([
                ('model', '=', 'crm.lead'),
                ('res_id', '=', lead.id),
                ('message_type', '=', 'comment'),
            ])
            if not has_note:
                raise ValidationError(_(
                    'A log note must be added before '
                    'moving the lead to the "%s" stage.'
                ) % lead.stage_id.name)

    # ── Helpers ────────────────────────────────────────────────────── #
    def _get_design_stage_sequence(self):
        """Get the minimum sequence for Design Manager access."""
        if self.env.user.has_group('crm_touch.group_crm_design_manager'):
            self.env.cr.execute(
                """SELECT 1 FROM res_groups_users_rel gur
                   JOIN ir_model_data imd ON imd.res_id = gur.gid
                      AND imd.model = 'res.groups'
                      AND imd.module = 'crm_touch'
                      AND imd.name = 'group_crm_design_manager'
                   WHERE gur.uid = %s LIMIT 1""",
                [self.env.uid],
            )
            if self.env.cr.fetchone():
                design_stage = self.env['crm.stage'].search(
                    [('is_design_stage', '=', True)],
                    order='sequence', limit=1,
                )
                return design_stage.sequence if design_stage else None
        return None

    def _get_allowed_lead_ids(self):
        """Return IDs this user is allowed to see.

        - Leads assigned to the user  AND  current >= assignment stage.
        - Leads the user created (regardless of assignment or stage).
        """
        self.env.cr.execute(
            """SELECT id, assigned_stage_sequence, current_stage_sequence,
                      user_id, create_uid
               FROM crm_lead
               WHERE active = true
                 AND (user_id = %s OR create_uid = %s)""",
            [self.env.uid, self.env.uid],
        )
        return [
            row[0] for row in self.env.cr.fetchall()
            if (
                row[4] == self.env.uid  # I created it → always visible
                or row[2] >= row[1]     # Assigned to me → check stage
            )
        ]

    # ── CRUD: track assignment stage ───────────────────────────────── #
    def _send_design_phase_email(self, lead, stage):
        """Send email to stage.design_phase_user_id when lead enters Design Phase."""
        design_user = stage.design_phase_user_id
        if not design_user or not design_user.email:
            return
        # Temporarily set user_id so template renders for the correct person
        old_user = lead.user_id
        lead.with_context(
            _skip_meeting_transition=True,
            _skip_attachment_check=True,
        ).write({'user_id': design_user.id})
        # Send via template (appears in chatter with full format)
        template = self.env.ref(
            'crm_touch.mail_template_crm_lead_assigned',
            raise_if_not_found=False,
        )
        if template:
            template.send_mail(lead.id, force_send=True)
            lead.message_post(
                body='📧 Email sent to <strong>%s</strong> (%s)'
                     % (design_user.name, design_user.email),
                message_type='notification',
            )
        # Restore original user_id
        lead.with_context(
            _skip_meeting_transition=True,
            _skip_attachment_check=True,
        ).write({'user_id': old_user.id if old_user else False})

    def _create_probability_activity(self, probability_client=None, no_response=None):
        """Auto-create follow-up activity based on probability_client / no_response."""
        self.ensure_one()
        Activity = self.env['mail.activity']
        model_id = self.env['ir.model'].sudo().search(
            [('model', '=', 'crm.lead')], limit=1,
        ).id
        activity_type = self.env.ref('mail.mail_activity_data_call', raise_if_not_found=False)
        today = fields.Date.today()
        prob_client = probability_client if probability_client is not None else self.probability_client
        no_resp = no_response if no_response is not None else self.no_response

        summary = None
        deadline = None

        # Case 1: no_response = True → follow-up after 3 days
        if no_resp:
            summary = 'متابعة بعد ثلاث أيام'
            deadline = today + timedelta(days=3)
        # Case 2: probability_client = 90% → follow-up after 3 days
        elif prob_client == '90':
            summary = 'متابعة بعد ثلاث أيام'
            deadline = today + timedelta(days=3)
        # Case 3: probability_client = 40% → follow-up after 7 days (once only)
        elif prob_client == '40':
            existing = Activity.search_count([
                ('res_model_id', '=', model_id),
                ('res_id', '=', self.id),
                ('summary', '=', 'متابعة بعد 7 ايام'),
                ('date_deadline', '>=', today),
            ])
            if existing:
                return
            summary = 'متابعة بعد 7 ايام'
            deadline = today + timedelta(days=7)

        if summary and deadline:
            Activity.create({
                'res_model_id': model_id,
                'res_id': self.id,
                'activity_type_id': activity_type.id if activity_type else False,
                'summary': summary,
                'date_deadline': deadline,
                'user_id': self.user_id.id or self.env.uid,
            })
            self.message_post(
                body='تم إنشاء نشاط: %s (الموعد: %s)' % (
                    summary, deadline.strftime('%Y-%m-%d')),
                message_type='notification',
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('user_id') and not vals.get('assigned_stage_sequence'):
                if vals.get('stage_id'):
                    stage = self.env['crm.stage'].browse(vals['stage_id'])
                    vals['assigned_stage_sequence'] = stage.sequence
        records = super().create(vals_list)
        # Send Design Phase email on create
        for rec in records:
            stage = rec.stage_id
            if stage.is_design_phase and stage.design_phase_user_id:
                rec._send_design_phase_email(rec, stage)
        # Auto-create activity on create
        for rec in records:
            prob_client = rec.probability_client
            no_resp = rec.no_response
            if prob_client or no_resp:
                rec._create_probability_activity(
                    probability_client=prob_client, no_response=no_resp)
        return records

    def write(self, vals):
        # ── Track assignment stage ──────────────────────────────────── #
        if 'user_id' in vals:
            for lead in self:
                new_user = vals['user_id']
                if new_user:
                    stage_id = vals.get('stage_id', lead.stage_id.id)
                    stage = (
                        self.env['crm.stage'].browse(stage_id)
                        if stage_id else None
                    )
                    self.env.cr.execute(
                        'UPDATE crm_lead SET assigned_stage_sequence = %s '
                        'WHERE id = %s',
                        [stage.sequence if stage else 0, lead.id],
                    )
                else:
                    self.env.cr.execute(
                        'UPDATE crm_lead SET assigned_stage_sequence = 0 '
                        'WHERE id = %s',
                        [lead.id],
                    )
            self.invalidate_recordset(['assigned_stage_sequence'])

        # Design Manager: block write on leads outside Design Stage+
        design_seq = self._get_design_stage_sequence()
        if design_seq is not None:
            for lead in self:
                if lead.stage_id and lead.stage_id.sequence < design_seq:
                    raise ValidationError(_(
                        'You do not have permission to modify leads '
                        'in stages before the Design Stage.'
                    ))

        # Installation Engineer: block write outside Meeting Stage+
        if self.env.user.has_group('crm_touch.group_crm_installation_engineer'):
            meeting_stage = self.env['crm.stage'].search(
                [('is_meeting_access', '=', True)], order='sequence', limit=1,
            )
            if meeting_stage:
                for lead in self:
                    if (lead.stage_id
                            and lead.stage_id.sequence < meeting_stage.sequence):
                        raise ValidationError(_(
                            'You do not have permission to modify leads '
                            'in stages before the Meeting with Client stage.'
                        ))

        res = super().write(vals)

        # Auto-create follow-up activities based on probability_client
        if 'probability_client' in vals or 'no_response' in vals:
            for lead in self:
                prob_client = vals.get('probability_client', lead.probability_client)
                no_resp = vals.get('no_response', lead.no_response)
                if prob_client or no_resp:
                    lead._create_probability_activity(
                        probability_client=prob_client,
                        no_response=bool(no_resp),
                    )

        # Inspection file uploaded → set date + update Sale Order dates
        if 'inspection_file' in vals and vals.get('inspection_file'):
            for lead in self:
                today = fields.Date.today()
                lead.inspection_upload_date = today
                factory_date = today + timedelta(days=2)
                installation_date = factory_date + timedelta(days=18)
                sale_orders = self.env['sale.order'].search([
                    ('crm_lead_id', '=', lead.id),
                ])
                if sale_orders:
                    self.env.cr.execute(
                        """UPDATE sale_order
                           SET factory_sending_date = %s,
                               installation_date = %s
                           WHERE id IN %s""",
                        [factory_date, installation_date,
                         tuple(sale_orders.ids)],
                    )
                    _logger.info(
                        'CRM Touch: Factory=%s / Install=%s for %s SO(s) '
                        'of lead "%s".',
                        factory_date, installation_date,
                        len(sale_orders), lead.name,
                    )

        # Preview Uploaded → Design Phase auto-transition
        if 'preview_attachment' in vals:
            for lead in self:
                if lead.stage_id.is_preview_uploaded and lead.preview_attachment:
                    design_stage = self.env['crm.stage'].sudo().search(
                        [('is_design_phase', '=', True)], order='sequence', limit=1,
                    )
                    if design_stage and lead.stage_id.id != design_stage.id:
                        lead.with_context(
                            _skip_meeting_transition=True,
                            _skip_attachment_check=True,
                        ).write({'stage_id': design_stage.id})

        # Design Phase email — send whenever entering Design Phase stage
        if 'stage_id' in vals:
            for lead in self:
                new_stage = self.env['crm.stage'].browse(vals['stage_id'])
                if new_stage.is_design_phase and new_stage.design_phase_user_id:
                    self._send_design_phase_email(lead, new_stage)

        # Auto-transitions
        if not self.env.context.get('_skip_meeting_transition'):
            for lead in self:
                if lead.stage_id.is_design_phase:
                    # Auto-transition Design Phase → Meeting with Client
                    if 'user_id' in vals and vals['user_id']:
                        meeting_stage = self.env['crm.stage'].sudo().search(
                            [('is_meeting_access', '=', True)],
                            order='sequence', limit=1,
                        )
                        if meeting_stage and lead.stage_id.id != meeting_stage.id:
                            lead.with_context(_skip_meeting_transition=True).write({
                                'stage_id': meeting_stage.id,
                            })
                if 'user_id' in vals and vals['user_id'] \
                        and lead.stage_id.is_request_inspection:
                    lead._transition_request_inspection_to_preview()
                # Check if inspection_file has been uploaded
                if lead.stage_id.is_synthetic_inspection:
                    self.env.cr.execute(
                        "SELECT 1 FROM ir_attachment WHERE res_model='crm.lead' "
                        "AND res_id=%s AND res_field='inspection_file' LIMIT 1",
                        [lead.id],
                    )
                    if self.env.cr.fetchone():
                        lead._transition_synthetic_to_work_order()
                # Technical Office: Reading Two Files checked → Won
                if lead.stage_id.is_work_order_trigger:
                    if lead.reading_two_files:
                        lead._transition_work_order_trigger_to_won()
            # If lead moved to a stage the user can no longer access → redirect
            if not _notified_users[self.env.uid]:
                for lead in self:
                    stage = lead.stage_id
                    lost_access = False
                    if self.env.user.has_group('crm_touch.group_crm_design_manager') \
                            and not stage.is_design_stage:
                        lost_access = True
                    elif self.env.user.has_group('crm_touch.group_inspection_department') \
                            and not stage.is_inspection_stage:
                        lost_access = True
                    elif self.env.user.has_group('crm_touch.group_operations_department') \
                            and not stage.is_operations_stage:
                        lost_access = True
                    elif self.env.user.has_group('crm_touch.group_sales_person') \
                            and not stage.is_sales_person_stage:
                        lost_access = True
                    elif self.env.user.has_group('crm_touch.group_sales') \
                            and not stage.is_sales_stage:
                        lost_access = True
                    elif self.env.user.has_group('crm_touch.group_work_order') \
                            and not stage.is_work_order_stage:
                        lost_access = True

                    if lost_access:
                        _notified_users[self.env.uid] = True
                        self.env['bus.bus']._sendone(
                            self.env.user.partner_id, 'crm_touch/reload', {},
                        )
                        break
        return res

    # ── _search: access control ────────────────────────────────────── #
    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        """Access control.

        Superuser → bypass everything.

        Design Manager → Design Stage + Follow-up + Won, regardless of
          assignment.  Sudo bypasses ir.rules (including Personal Leads).

        Installation Engineer → Meeting Stage + Won, regardless of
          assignment.  Sudo bypasses ir.rules.

        Regular user → pass-through.  Visibility is controlled by
          ir.rule ``rule_crm_lead_own_records``.
        """
        domain = list(domain or [])

        if self.env.su:
            return super()._search(domain, offset=offset, limit=limit, order=order)

        from odoo.osv import expression

        # ── Design Manager ────────────────────────────────────────── #
        self.env.cr.execute(
            """SELECT 1 FROM res_groups_users_rel gur
               JOIN ir_model_data imd ON imd.res_id = gur.gid
                  AND imd.model = 'res.groups'
                  AND imd.module = 'crm_touch'
                  AND imd.name = 'group_crm_design_manager'
               WHERE gur.uid = %s LIMIT 1""",
            [self.env.uid],
        )
        if self.env.cr.fetchone():
            design_stage = self.env['crm.stage'].search(
                [('is_design_stage', '=', True)], order='sequence', limit=1,
            )
            if design_stage:
                domain = expression.AND([domain, [
                    '|', '|', '|',
                    ('stage_id', '=', False),
                    ('stage_id.is_design_stage', '=', True),
                    ('stage_id.is_followup', '=', True),
                    ('stage_id.sequence', '>=', design_stage.sequence),
                ]])
            return self.sudo()._search(
                domain, offset=offset, limit=limit, order=order,
            )

        # ── Installation Engineer ─────────────────────────────────── #
        self.env.cr.execute(
            """SELECT 1 FROM res_groups_users_rel gur
               JOIN ir_model_data imd ON imd.res_id = gur.gid
                  AND imd.model = 'res.groups'
                  AND imd.module = 'crm_touch'
                  AND imd.name = 'group_crm_installation_engineer'
               WHERE gur.uid = %s LIMIT 1""",
            [self.env.uid],
        )
        if self.env.cr.fetchone():
            meeting_stage = self.env['crm.stage'].search(
                [('is_meeting_access', '=', True)], order='sequence', limit=1,
            )
            if meeting_stage:
                domain = expression.AND([domain, [
                    '|', '|',
                    ('stage_id.is_meeting_access', '=', True),
                    ('stage_id.is_won', '=', True),
                    ('stage_id.sequence', '>=', meeting_stage.sequence),
                ]])
            return self.sudo()._search(
                domain, offset=offset, limit=limit, order=order,
            )

        # ── Regular user → pass-through (ir.rule handles visibility)  #
        return super()._search(
            domain, offset=offset, limit=limit, order=order,
        )

    # ── Stage transitions ──────────────────────────────────────────── #
    def _transition_to_meeting_stage(self):
        self.ensure_one()
        CrmStage = self.env['crm.stage'].sudo()
        meeting_stage = False
        if self.team_id:
            meeting_stage = CrmStage.search([
                ('is_meeting_access', '=', True),
                ('team_id', '=', self.team_id.id),
            ], limit=1)
        if not meeting_stage:
            meeting_stage = CrmStage.search([
                ('is_meeting_access', '=', True),
                ('team_id', '=', False),
            ], limit=1)
        if not meeting_stage:
            _logger.info(
                'CRM Touch: No Meeting stage — lead "%s" stays in "%s".',
                self.name, self.stage_id.name,
            )
            return

        old_stage = self.stage_id.name
        self.with_context(_skip_meeting_transition=True).write({
            'stage_id': meeting_stage.id,
        })
        new_stage = meeting_stage.name

        msg = _(
            'Lead automatically moved from <strong>%s</strong> to '
            '<strong>%s</strong> because the Design Phase was completed.'
        ) % (old_stage, new_stage)
        body = Markup(
            '<div style="display:flex;flex-direction:column;align-items:flex-start;'
            'max-width:85%%;font-family:-apple-system,BlinkMacSystemFont,'
            '\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;margin:4px 0;">'
            '<div style="background-color:#f0e6ff;color:#5a2d82;font-size:14px;'
            'padding:12px 16px;border-radius:14px 14px 14px 0;'
            'box-shadow:0 1px 1px rgba(0,0,0,0.05);line-height:1.5;'
            'direction:ltr;text-align:left;">%s</div>'
            '<span style="font-size:11px;color:#707881;margin-top:4px;'
            'margin-left:2px;opacity:0.8;">%s</span>'
            '</div>'
        ) % (msg, _('System Notification'))
        self.message_post(
            body=body, message_type='comment', subtype_xmlid='mail.mt_note',
        )

    def _transition_request_inspection_to_preview(self):
        self.ensure_one()
        CrmStage = self.env['crm.stage'].sudo()
        preview_stage = CrmStage.search(
            [('is_preview_uploaded', '=', True)], limit=1,
        )
        if not preview_stage:
            _logger.info(
                'CRM Touch: No Preview Uploaded stage — '
                'lead "%s" stays in "%s".',
                self.name, self.stage_id.name,
            )
            return

        self.with_context(_skip_meeting_transition=True).write({
            'stage_id': preview_stage.id,
        })
        msg = _(
            'Lead moved to <strong>%s</strong> automatically after '
            'a salesperson was assigned.'
        ) % preview_stage.name
        body = Markup(
            '<div style="display:flex;flex-direction:column;align-items:flex-start;'
            'max-width:85%%;font-family:-apple-system,BlinkMacSystemFont,'
            '\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;margin:4px 0;">'
            '<div style="background-color:#e1f0fa;color:#0b4f83;font-size:14px;'
            'padding:12px 16px;border-radius:14px 14px 14px 0;'
            'box-shadow:0 1px 1px rgba(0,0,0,0.05);line-height:1.5;'
            'direction:ltr;text-align:left;">%s</div>'
            '<span style="font-size:11px;color:#707881;margin-top:4px;'
            'margin-left:2px;opacity:0.8;">%s</span>'
            '</div>'
        ) % (msg, _('System Notification'))
        self.message_post(
            body=body, message_type='comment', subtype_xmlid='mail.mt_note',
        )

    def _transition_synthetic_to_work_order(self):
        self.ensure_one()
        CrmStage = self.env['crm.stage'].sudo()
        work_order_stage = CrmStage.search([
            '|', ('is_work_order_stage', '=', True),
            ('is_work_order_trigger', '=', True),
            ('sequence', '>', self.stage_id.sequence),
        ], order='sequence', limit=1)
        if not work_order_stage:
            _logger.info(
                'CRM Touch: No Contracts stage — lead "%s" stays in "%s".',
                self.name, self.stage_id.name,
            )
            return

        self.with_context(_skip_meeting_transition=True).write({
            'stage_id': work_order_stage.id,
        })
        new_stage = work_order_stage.name

        msg = _(
            'Lead moved to <strong>%s</strong> automatically after '
            'inspection file was uploaded and saved.'
        ) % new_stage
        body = Markup(
            '<div style="display:flex;flex-direction:column;align-items:flex-start;'
            'max-width:85%%;font-family:-apple-system,BlinkMacSystemFont,'
            '\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;margin:4px 0;">'
            '<div style="background-color:#e1f0fa;color:#0b4f83;font-size:14px;'
            'padding:12px 16px;border-radius:14px 14px 14px 0;'
            'box-shadow:0 1px 1px rgba(0,0,0,0.05);line-height:1.5;'
            'direction:ltr;text-align:left;">%s</div>'
            '<span style="font-size:11px;color:#707881;margin-top:4px;'
            'margin-left:2px;opacity:0.8;">%s</span>'
            '</div>'
        ) % (msg, _('System Notification'))
        self.message_post(
            body=body, message_type='comment', subtype_xmlid='mail.mt_note',
        )

    def _transition_work_order_trigger_to_work_order(self):
        self.ensure_one()
        CrmStage = self.env['crm.stage'].sudo()
        work_order_stage = CrmStage.search(
            [('is_work_order_stage', '=', True),
             ('is_work_order_trigger', '=', False)], limit=1,
        )
        if not work_order_stage:
            _logger.info(
                'CRM Touch: No Contracts stage — lead "%s" stays in "%s".',
                self.name, self.stage_id.name,
            )
            return

        self.with_context(_skip_meeting_transition=True).write({
            'stage_id': work_order_stage.id,
        })
        msg = _(
            'Lead moved to <strong>%s</strong> automatically after '
            'Contracts attachment was uploaded.'
        ) % work_order_stage.name
        body = Markup(
            '<div style="display:flex;flex-direction:column;align-items:flex-start;'
            'max-width:85%%;font-family:-apple-system,BlinkMacSystemFont,'
            '\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;margin:4px 0;">'
            '<div style="background-color:#e1f0fa;color:#0b4f83;font-size:14px;'
            'padding:12px 16px;border-radius:14px 14px 14px 0;'
            'box-shadow:0 1px 1px rgba(0,0,0,0.05);line-height:1.5;'
            'direction:ltr;text-align:left;">%s</div>'
            '<span style="font-size:11px;color:#707881;margin-top:4px;'
            'margin-left:2px;opacity:0.8;">%s</span>'
            '</div>'
        ) % (msg, _('System Notification'))
        self.message_post(
            body=body, message_type='comment', subtype_xmlid='mail.mt_note',
        )

    def _transition_work_order_to_won(self):
        self.ensure_one()
        CrmStage = self.env['crm.stage'].sudo()
        won_stage = CrmStage.search([('is_won', '=', True)], limit=1)
        if not won_stage:
            _logger.info(
                'CRM Touch: No Won stage — lead "%s" stays in "%s".',
                self.name, self.stage_id.name,
            )
            return

        self.with_context(_skip_meeting_transition=True).write({
            'stage_id': won_stage.id, 'probability': 100,
        })
        msg = _(
            'Lead marked as <strong>Won</strong> automatically after '
            'Contracts files were confirmed.'
        )
        body = Markup(
            '<div style="display:flex;flex-direction:column;align-items:flex-start;'
            'max-width:85%%;font-family:-apple-system,BlinkMacSystemFont,'
            '\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;margin:4px 0;">'
            '<div style="background-color:#d4edda;color:#155724;font-size:14px;'
            'padding:12px 16px;border-radius:14px 14px 14px 0;'
            'box-shadow:0 1px 1px rgba(0,0,0,0.05);line-height:1.5;'
            'direction:ltr;text-align:left;">%s</div>'
            '<span style="font-size:11px;color:#707881;margin-top:4px;'
            'margin-left:2px;opacity:0.8;">%s</span>'
            '</div>'
        ) % (msg, _('System Notification'))
        self.message_post(
            body=body, message_type='comment', subtype_xmlid='mail.mt_note',
        )

    def _transition_work_order_trigger_to_won(self):
        self.ensure_one()
        CrmStage = self.env['crm.stage'].sudo()
        won_stage = CrmStage.search([('is_won', '=', True)], limit=1)
        if not won_stage:
            _logger.info(
                'CRM Touch: No Won stage — lead "%s" stays in "%s".',
                self.name, self.stage_id.name,
            )
            return

        self.with_context(_skip_meeting_transition=True).write({
            'stage_id': won_stage.id, 'probability': 100,
        })
        msg = _(
            'Lead marked as <strong>Won</strong> automatically after '
            'Reading Two Files was confirmed.'
        )
        body = Markup(
            '<div style="display:flex;flex-direction:column;align-items:flex-start;'
            'max-width:85%%;font-family:-apple-system,BlinkMacSystemFont,'
            '\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;margin:4px 0;">'
            '<div style="background-color:#d4edda;color:#155724;font-size:14px;'
            'padding:12px 16px;border-radius:14px 14px 14px 0;'
            'box-shadow:0 1px 1px rgba(0,0,0,0.05);line-height:1.5;'
            'direction:ltr;text-align:left;">%s</div>'
            '<span style="font-size:11px;color:#707881;margin-top:4px;'
            'margin-left:2px;opacity:0.8;">%s</span>'
            '</div>'
        ) % (msg, _('System Notification'))
        self.message_post(
            body=body, message_type='comment', subtype_xmlid='mail.mt_note',
        )

    def _transition_synthetic_to_won(self):
        self.ensure_one()
        CrmStage = self.env['crm.stage'].sudo()
        won_stage = CrmStage.search([('is_won', '=', True)], limit=1)
        if not won_stage:
            _logger.info(
                'CRM Touch: No Won stage — lead "%s" stays in "%s".',
                self.name, self.stage_id.name,
            )
            return

        old_stage = self.stage_id.name
        self.write({'stage_id': won_stage.id, 'probability': 100})
        new_stage = won_stage.name

        msg = _(
            'Lead marked as <strong>Won</strong> automatically after '
            'inspection file was uploaded and saved.'
        )
        body = Markup(
            '<div style="display:flex;flex-direction:column;align-items:flex-start;'
            'max-width:85%%;font-family:-apple-system,BlinkMacSystemFont,'
            '\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;margin:4px 0;">'
            '<div style="background-color:#d4edda;color:#155724;font-size:14px;'
            'padding:12px 16px;border-radius:14px 14px 14px 0;'
            'box-shadow:0 1px 1px rgba(0,0,0,0.05);line-height:1.5;'
            'direction:ltr;text-align:left;">%s</div>'
            '<span style="font-size:11px;color:#707881;margin-top:4px;'
            'margin-left:2px;opacity:0.8;">%s</span>'
            '</div>'
        ) % (msg, _('System Notification'))
        self.message_post(
            body=body, message_type='comment', subtype_xmlid='mail.mt_note',
        )

    def action_open_meeting_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Meeting Actions'),
            'res_model': 'crm.meeting.action.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref(
                'crm_touch.crm_meeting_action_wizard_form_view'
            ).id,
            'target': 'new',
            'context': {
                'default_lead_id': self.id,
                'default_is_meeting_access': self.stage_id.is_meeting_access,
            },
        }
