# -*- coding: utf-8 -*-
from odoo import models, api, fields
from odoo.exceptions import UserError
from datetime import datetime, timedelta


class CrmLead(models.Model):
    _inherit = "crm.lead"

    visit_date = fields.Date(
        string="Date",
        default=fields.Date.context_today
    )

    visit_time = fields.Char(
        string="Time",
        help="وقت الزيارة فقط، على شكل HH:MM",
    )

    inspection_upload_date = fields.Datetime(string="تاريخ رفع المعاينة")
    no_response_since = fields.Datetime(string='تاريخ عدم الرد', readonly=True)
    campaign_date = fields.Date(string="تاريخ الكامبين")
    decor_engineer_id = fields.Many2one('res.users', string="مهندس ديكور")
    location = fields.Char(string="لوكيشن")
    location_map_url = fields.Char(
        string="Map",
        compute="_compute_location_map",
    )

    def _compute_location_map(self):
        for rec in self:
            if rec.location:
                rec.location_map_url = "https://www.google.com/maps/search/%s" % rec.location
            else:
                rec.location_map_url = False

    is_out = fields.Boolean(string="اوت")
    is_preview = fields.Boolean(string="معاينة")
    no_response = fields.Boolean(string="لم يرد")
    # no_response_since = fields.Datetime(string="No Response Since")
    probability_client = fields.Selection(
        selection=[
            ('40', '40%'),
            ('90', '90%'),
        ],
        string="احتمالية العميل (%)",
    )
    num_of_media = fields.Boolean(string="رقم")
    is_late = fields.Boolean()



    def no_response_client(self):
        """
        Cron يومي - يبعت inbox notification لكل يوزر
        بعدد العملاء اللي no_response = True عنده
        """
        late_leads = self.sudo().search([
            ('no_response', '=', True),
        ])

        print(len(late_leads))

        if not late_leads:
            return

        user_leads = {}
        for lead in late_leads:
            uid = lead.create_uid.id
            if uid not in user_leads:
                user_leads[uid] = self.env['crm.lead']
            user_leads[uid] |= lead

        for uid, leads in user_leads.items():
            user = self.env['res.users'].browse(uid)
            if not user.exists() or not user.partner_id:
                continue

            count = len(leads)

            names_html = ''.join(
                '<li>%s</li>' % (lead.partner_name or lead.name or 'عميل بدون اسم')
                for lead in leads
            )

            body = (
                '<div style="direction:rtl;text-align:right;font-family:Arial;">'
                '<p>&#128276; <strong>تنبيه: عملاء لم يتم الرد عليهم</strong></p>'
                '<p>لديك <strong style="color:#e74c3c;">%d</strong>'
                ' عميل لم يتم الرد عليهم:</p>'
                '<ul>%s</ul>'
                '</div>'
            ) % (count, names_html)

            leads[0].sudo().message_notify(
                partner_ids=user.partner_id.ids,
                subject='عملاء بدون رد',
                body=body,
                subtype_xmlid='mail.mt_comment',
            )

    def crm_xlsx_report(self):
        if not self.ids:
            raise UserError("من فضلك اختار records الأول!")
        ids_str = ','.join(str(i) for i in self.ids)
        count = len(self.ids)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'جاري تحميل الريبورت',
                'message': 'عدد الـ records المختارة: %d' % count,
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_url',
                    'url': '/crm/lead/report?ids=%s' % ids_str,
                    'target': 'new',
                },
            },
        }