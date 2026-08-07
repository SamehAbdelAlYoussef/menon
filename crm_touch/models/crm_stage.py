import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class CrmStage(models.Model):
    _inherit = 'crm.stage'

    is_design_stage = fields.Boolean(
        string='Is Design Stage Start',
        default=False,
        help='Design Managers will only see leads starting from this stage '
             'and any stages after it (based on sequence). '
             'Only Administrators can modify this setting.',
    )

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        """Restrict visible stages per user group.

        ID-based lookups (check_access_rights for direct reads) are never
        filtered ? they are needed to display stage names on records the
        user is already viewing.  General searches (kanban, dropdowns) are
        filtered so early stages stay hidden.
        """
        domain = list(domain or [])
        if self.env.su:
            return super()._search(domain, offset=offset, limit=limit, order=order)
        if self.env.context.get('_bypass_crm_stage_filter'):
            return super()._search(domain, offset=offset, limit=limit, order=order)

        # Allow direct ID reads (used by check_access_rights for browse/read).
        id_leaves = [
            leaf for leaf in domain
            if isinstance(leaf, (list, tuple)) and len(leaf) >= 3
        ]
        if id_leaves and all(
                leaf[0] == 'id' and leaf[1] in ('in', '=')
                for leaf in id_leaves
        ):
            return super()._search(domain, offset=offset, limit=limit, order=order)

        # 1. ?? Design Manager ?????????????????????????????????????????? #
        self.env.cr.execute(
            """SELECT 1
               FROM res_groups_users_rel gur
                        JOIN ir_model_data imd ON imd.res_id = gur.gid
                   AND imd.model = 'res.groups'
                   AND imd.module = 'crm_touch'
                   AND imd.name = 'group_crm_design_manager'
               WHERE gur.uid = %s LIMIT 1""",
            [self.env.uid],
        )
        if self.env.cr.fetchone():
            # Design Manager users see ONLY stages with the checkbox enabled
            domain[:0] = [('is_design_stage', '=', True)]
            return super()._search(
                domain, offset=offset, limit=limit, order=order,
            )

        # 2. ?? Installation Engineer ??????????????????????????????????? #
        self.env.cr.execute(
            """SELECT 1
               FROM res_groups_users_rel gur
                        JOIN ir_model_data imd ON imd.res_id = gur.gid
                   AND imd.model = 'res.groups'
                   AND imd.module = 'crm_touch'
                   AND imd.name = 'group_crm_installation_engineer'
               WHERE gur.uid = %s LIMIT 1""",
            [self.env.uid],
        )
        if self.env.cr.fetchone():
            # Installation Engineer sees ONLY Meeting with Client stages
            domain[:0] = [('is_meeting_access', '=', True)]
            return super()._search(
                domain, offset=offset, limit=limit, order=order,
            )

        # 3. ── Inspection Department ──────────────────────────────── #
        self.env.cr.execute(
            """SELECT 1
               FROM res_groups_users_rel gur
                        JOIN ir_model_data imd ON imd.res_id = gur.gid
                   AND imd.model = 'res.groups'
                   AND imd.module = 'crm_touch'
                   AND imd.name = 'group_inspection_department'
               WHERE gur.uid = %s LIMIT 1""",
            [self.env.uid],
        )
        if self.env.cr.fetchone():
            # Inspection users see ONLY stages with the checkbox enabled
            domain[:0] = [('is_inspection_stage', '=', True)]
            return super()._search(
                domain, offset=offset, limit=limit, order=order,
            )

        # 4. ── Operations Department ──────────────────────────────── #
        self.env.cr.execute(
            """SELECT 1
               FROM res_groups_users_rel gur
                        JOIN ir_model_data imd ON imd.res_id = gur.gid
                   AND imd.model = 'res.groups'
                   AND imd.module = 'crm_touch'
                   AND imd.name = 'group_operations_department'
               WHERE gur.uid = %s LIMIT 1""",
            [self.env.uid],
        )
        if self.env.cr.fetchone():
            # Operations users see ONLY stages with the checkbox enabled
            domain[:0] = [('is_operations_stage', '=', True)]
            return super()._search(
                domain, offset=offset, limit=limit, order=order,
            )

        # 5. ── Sales Person ───────────────────────────────────────── #
        self.env.cr.execute(
            """SELECT 1
               FROM res_groups_users_rel gur
                        JOIN ir_model_data imd ON imd.res_id = gur.gid
                   AND imd.model = 'res.groups'
                   AND imd.module = 'crm_touch'
                   AND imd.name = 'group_sales_person'
               WHERE gur.uid = %s LIMIT 1""",
            [self.env.uid],
        )
        if self.env.cr.fetchone():
            # Sales Person users see ONLY stages with the checkbox enabled
            domain[:0] = [('is_sales_person_stage', '=', True)]
            return super()._search(
                domain, offset=offset, limit=limit, order=order,
            )

        # 6. ── Sales ──────────────────────────────────────────────── #
        self.env.cr.execute(
            """SELECT 1
               FROM res_groups_users_rel gur
                        JOIN ir_model_data imd ON imd.res_id = gur.gid
                   AND imd.model = 'res.groups'
                   AND imd.module = 'crm_touch'
                   AND imd.name = 'group_sales'
               WHERE gur.uid = %s LIMIT 1""",
            [self.env.uid],
        )
        if self.env.cr.fetchone():
            # Sales users see ONLY stages with the checkbox enabled
            domain[:0] = [('is_sales_stage', '=', True)]
            return super()._search(
                domain, offset=offset, limit=limit, order=order,
            )

        # 7. ── Work Order ──────────────────────────────────────────── #
        self.env.cr.execute(
            """SELECT 1
               FROM res_groups_users_rel gur
                        JOIN ir_model_data imd ON imd.res_id = gur.gid
                   AND imd.model = 'res.groups'
                   AND imd.module = 'crm_touch'
                   AND imd.name = 'group_work_order'
               WHERE gur.uid = %s LIMIT 1""",
            [self.env.uid],
        )
        if self.env.cr.fetchone():
            # Work Order users see ONLY stages with the checkbox enabled
            domain[:0] = [('is_work_order_stage', '=', True)]
            return super()._search(
                domain, offset=offset, limit=limit, order=order,
            )

        # 8. ?? Normal Salesman (Own Documents Only) ???????????????????? #
        if self.env.user.has_group('sales_team.group_sale_salesman') and not self.env.user.has_group(
                'sales_team.group_sale_manager'):
            # جلب الـ IDs للمراحل التي تحتوي على كروت تخص المستخدم الحالي
            self.env.cr.execute(
                """SELECT DISTINCT stage_id
                   FROM crm_lead
                   WHERE stage_id IS NOT NULL
                     AND (user_id = %s OR create_uid = %s)""",
                [self.env.uid, self.env.uid]
            )
            allowed_protected_stage_ids = [row[0] for row in self.env.cr.fetchall()]

            # صياغة الـ domain ببايثون صريح وبدون رموز XML تالفة
            domain[:0] = [
                '|',
                '&', '&',
                ('is_design_stage', '=', False),
                ('is_meeting_access', '=', False),
                '&',
                ('is_synthetic_inspection', '=', False),
                ('is_won', '=', False),
                ('id', 'in', allowed_protected_stage_ids)
            ]

        return super()._search(
            domain, offset=offset, limit=limit, order=order,
        )


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    work_order_attachment = fields.Many2many(
        'ir.attachment',
        string='Technical Office',
        tracking=True,
        relation='crm_lead_work_order_attachment_rel',
        help='Upload Technical Office files here.',
    )
    is_work_order_stage = fields.Boolean(
        related='stage_id.is_work_order_stage', readonly=True, store=True,
    )
    is_work_order_trigger = fields.Boolean(
        related='stage_id.is_work_order_trigger', readonly=True, store=True,
    )
    reading_two_files = fields.Boolean(
        string='Reading Two Files', default=False,
        tracking=True,
    )

    @api.model
    def web_read_group(self, domain, fields, groupby, limit=None, offset=0, orderby=None, lazy=True):
        res = super(CrmLead, self).web_read_group(
            domain=domain, fields=fields, groupby=groupby,
            limit=limit, offset=offset, orderby=orderby, lazy=lazy
        )

        if groupby and groupby[0] == 'stage_id':
            if self.env.user.has_group('sales_team.group_sale_salesman') and not self.env.user.has_group(
                    'sales_team.group_sale_manager'):

                filtered_groups = []
                for group in res.get('groups', []):
                    current_stage_id = group.get('stage_id', [False])[0]

                    if current_stage_id:
                        stage = self.env['crm.stage'].browse(current_stage_id)

                        is_protected = stage.is_design_stage or stage.is_meeting_access or stage.is_synthetic_inspection or stage.is_won
                        if is_protected and group.get('stage_id_count', 0) == 0:
                            continue
                    filtered_groups.append(group)
                res['groups'] = filtered_groups

            # ── Design Manager: ONLY is_design_stage=True ──────────── #
            if self.env.user.has_group('crm_touch.group_crm_design_manager'):
                filtered_groups = []
                for group in res.get('groups', []):
                    current_stage_id = group.get('stage_id', [False])[0]
                    if current_stage_id:
                        stage = self.env['crm.stage'].sudo().browse(current_stage_id)
                        if not stage.is_design_stage:
                            continue  # Always remove non-design-manager stages
                    filtered_groups.append(group)
                res['groups'] = filtered_groups

            # ── Installation Engineer: ONLY is_meeting_access=True ── #
            if self.env.user.has_group('crm_touch.group_crm_installation_engineer'):
                filtered_groups = []
                for group in res.get('groups', []):
                    current_stage_id = group.get('stage_id', [False])[0]
                    if current_stage_id:
                        stage = self.env['crm.stage'].sudo().browse(current_stage_id)
                        if not stage.is_meeting_access:
                            continue  # Always remove non-meeting stages
                    filtered_groups.append(group)
                res['groups'] = filtered_groups

            # ── Inspection Department: ONLY is_inspection_stage=True ── #
            if self.env.user.has_group('crm_touch.group_inspection_department'):
                filtered_groups = []
                for group in res.get('groups', []):
                    current_stage_id = group.get('stage_id', [False])[0]
                    if current_stage_id:
                        stage = self.env['crm.stage'].sudo().browse(current_stage_id)
                        if not stage.is_inspection_stage:
                            continue  # Always remove non-inspection stages
                    filtered_groups.append(group)
                res['groups'] = filtered_groups

            # ── Operations Department: ONLY is_operations_stage=True ── #
            if self.env.user.has_group('crm_touch.group_operations_department'):
                filtered_groups = []
                for group in res.get('groups', []):
                    current_stage_id = group.get('stage_id', [False])[0]
                    if current_stage_id:
                        stage = self.env['crm.stage'].sudo().browse(current_stage_id)
                        if not stage.is_operations_stage:
                            continue  # Always remove non-operations stages
                    filtered_groups.append(group)
                res['groups'] = filtered_groups

            # ── Sales Person: ONLY is_sales_person_stage=True ── #
            if self.env.user.has_group('crm_touch.group_sales_person'):
                filtered_groups = []
                for group in res.get('groups', []):
                    current_stage_id = group.get('stage_id', [False])[0]
                    if current_stage_id:
                        stage = self.env['crm.stage'].sudo().browse(current_stage_id)
                        if not stage.is_sales_person_stage:
                            continue  # Always remove non-sales-person stages
                    filtered_groups.append(group)
                res['groups'] = filtered_groups

            # ── Sales: ONLY is_sales_stage=True ────────────────────── #
            if self.env.user.has_group('crm_touch.group_sales'):
                filtered_groups = []
                for group in res.get('groups', []):
                    current_stage_id = group.get('stage_id', [False])[0]
                    if current_stage_id:
                        stage = self.env['crm.stage'].sudo().browse(current_stage_id)
                        if not stage.is_sales_stage:
                            continue  # Always remove non-sales stages
                    filtered_groups.append(group)
                res['groups'] = filtered_groups

            # ── Work Order: ONLY is_work_order_stage=True ──────────── #
            if self.env.user.has_group('crm_touch.group_work_order'):
                filtered_groups = []
                for group in res.get('groups', []):
                    current_stage_id = group.get('stage_id', [False])[0]
                    if current_stage_id:
                        stage = self.env['crm.stage'].sudo().browse(current_stage_id)
                        if not stage.is_work_order_stage:
                            continue  # Always remove non-work-order stages
                    filtered_groups.append(group)
                res['groups'] = filtered_groups

        return res

    # ── Auto-Transition: Request Inspection Stage + Assign Salesperson → Preview Uploaded ──

    def write(self, vals):
        res = super().write(vals)

        # 1) Request Inspection + assign salesperson → Preview Uploaded
        if 'user_id' in vals and vals['user_id'] \
                and not self.env.context.get('_skip_request_inspection'):
            for lead in self:
                if lead.stage_id.is_request_inspection:
                    preview_stage = self.env['crm.stage'].sudo().search(
                        [('is_preview_uploaded', '=', True)], limit=1,
                    )
                    if preview_stage and lead.stage_id.id != preview_stage.id:
                        lead.with_context(_skip_request_inspection=True).write({
                            'stage_id': preview_stage.id,
                        })

        # 2) Technical Office: reading_two_files checked → Won
        if 'reading_two_files' in vals and vals.get('reading_two_files'):
            for lead in self:
                if lead.stage_id.is_work_order_trigger:
                    won_stage = self.env['crm.stage'].sudo().search(
                        [('is_won', '=', True)], limit=1,
                    )
                    if won_stage and lead.stage_id.id != won_stage.id:
                        lead.with_context(
                            _skip_work_order_transition=True,
                            _skip_meeting_transition=True,
                        ).write({'stage_id': won_stage.id})

        # 3) Inspection files uploaded in Synthetic Inspection → Work Order
        if 'inspection_file' in vals and vals.get('inspection_file') \
                and not self.env.context.get('_skip_inspection_transition'):
            for lead in self:
                if lead.stage_id.is_synthetic_inspection:
                    work_order_stage = self.env['crm.stage'].sudo().search(
                        [('is_work_order_stage', '=', True)], limit=1,
                    )
                    if work_order_stage and lead.stage_id.id != work_order_stage.id:
                        lead.with_context(_skip_inspection_transition=True).write({
                            'stage_id': work_order_stage.id,
                        })
        return res

    @api.model
    def _read_group_stage_ids(self, stages, domain, *args, **kwargs):
        """Return only the stage columns the current user should see."""
        stage_ids = super()._read_group_stage_ids(stages, domain, *args, **kwargs)

        # ── Design Manager: ONLY is_design_stage=True ────────────── #
        if self.env.user.has_group('crm_touch.group_crm_design_manager'):
            stage_ids = stage_ids.filtered(lambda s: s.is_design_stage)

        # ── Installation Engineer: ONLY is_meeting_access=True ──────── #
        if self.env.user.has_group('crm_touch.group_crm_installation_engineer'):
            stage_ids = stage_ids.filtered(lambda s: s.is_meeting_access)

        # ── Inspection Department: ONLY is_inspection_stage=True ── #
        if self.env.user.has_group('crm_touch.group_inspection_department'):
            stage_ids = stage_ids.filtered(lambda s: s.is_inspection_stage)

        # ── Operations Department: ONLY is_operations_stage=True ── #
        if self.env.user.has_group('crm_touch.group_operations_department'):
            stage_ids = stage_ids.filtered(lambda s: s.is_operations_stage)

        # ── Sales Person: ONLY is_sales_person_stage=True ────────── #
        if self.env.user.has_group('crm_touch.group_sales_person'):
            stage_ids = stage_ids.filtered(lambda s: s.is_sales_person_stage)

        # ── Sales: ONLY is_sales_stage=True ──────────────────────── #
        if self.env.user.has_group('crm_touch.group_sales'):
            stage_ids = stage_ids.filtered(lambda s: s.is_sales_stage)

        # ── Work Order: ONLY is_work_order_stage=True ────────────── #
        if self.env.user.has_group('crm_touch.group_work_order'):
            stage_ids = stage_ids.filtered(lambda s: s.is_work_order_stage)

        return stage_ids
        return stage_ids


