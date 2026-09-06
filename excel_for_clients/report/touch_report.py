# -*- coding: utf-8 -*-
import io
import re
import xlsxwriter

from odoo import http
from odoo.http import request


class CrmLeadReport(http.Controller):

    @http.route('/crm/lead/report', type='http', auth='user')
    def crm_lead_report(self, ids='', **kwargs):
        """
        Generate an Excel file that looks like the campaign daily sheets
        and return it as a download.
        Records are shown in the exact order they were selected.
        """

        if ids:
            id_list = [int(i) for i in ids.split(',') if i.strip().isdigit()]
            leads = request.env['crm.lead'].browse(id_list).exists()
            lead_map = {lead.id: lead for lead in leads}
            ordered_leads = [lead_map[i] for i in id_list if i in lead_map]
        else:
            ordered_leads = list(request.env['crm.lead'].search(
                [('type', '=', 'opportunity')], order='create_date asc'
            ))

        if not ordered_leads:
            return request.make_response(
                '<h3>لا توجد بيانات</h3>',
                headers=[('Content-Type', 'text/html')]
            )

        date_groups = {}
        date_order = []
        for lead in ordered_leads:
            d = lead.visit_date if lead.visit_date else None
            if d:
                key = '%d-%d-%d' % (d.day, d.month, d.year)
            else:
                key = 'بدون تاريخ'
            if key not in date_groups:
                date_groups[key] = []
                date_order.append(key)
            date_groups[key].append(lead)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        hdr1_fmt = workbook.add_format({
            'bold': True, 'font_name': 'Arial', 'font_size': 11,
            'font_color': '#FFFFFF', 'bg_color': '#1F4E79',
            'align': 'center', 'valign': 'vcenter',
            'border': 1, 'reading_order': 2,
        })
        hdr1_blue_fmt = workbook.add_format({
            'bold': True, 'font_name': 'Arial', 'font_size': 11,
            'font_color': '#FFFFFF', 'bg_color': '#2E75B6',
            'align': 'center', 'valign': 'vcenter',
            'border': 1, 'reading_order': 2,
        })
        hdr1_green_fmt = workbook.add_format({
            'bold': True, 'font_name': 'Arial', 'font_size': 11,
            'font_color': '#FFFFFF', 'bg_color': '#1F7B4E',
            'align': 'center', 'valign': 'vcenter',
            'border': 1, 'reading_order': 2,
        })
        hdr1_grey_fmt = workbook.add_format({
            'bold': True, 'font_name': 'Arial', 'font_size': 11,
            'font_color': '#FFFFFF', 'bg_color': '#5A5A5A',
            'align': 'center', 'valign': 'vcenter',
            'border': 1, 'reading_order': 2,
        })
        hdr2_dark_fmt = workbook.add_format({
            'bold': True, 'font_name': 'Arial', 'font_size': 10,
            'font_color': '#FFFFFF', 'bg_color': '#1F4E79',
            'align': 'center', 'valign': 'vcenter',
            'border': 1, 'text_wrap': True, 'reading_order': 2,
        })
        hdr2_blue_fmt = workbook.add_format({
            'bold': True, 'font_name': 'Arial', 'font_size': 10,
            'font_color': '#FFFFFF', 'bg_color': '#2E75B6',
            'align': 'center', 'valign': 'vcenter',
            'border': 1, 'text_wrap': True, 'reading_order': 2,
        })
        hdr2_green_fmt = workbook.add_format({
            'bold': True, 'font_name': 'Arial', 'font_size': 10,
            'font_color': '#FFFFFF', 'bg_color': '#1F7B4E',
            'align': 'center', 'valign': 'vcenter',
            'border': 1, 'text_wrap': True, 'reading_order': 2,
        })
        hdr2_grey_fmt = workbook.add_format({
            'bold': True, 'font_name': 'Arial', 'font_size': 10,
            'font_color': '#FFFFFF', 'bg_color': '#5A5A5A',
            'align': 'center', 'valign': 'vcenter',
            'border': 1, 'text_wrap': True, 'reading_order': 2,
        })
        data_fmt = workbook.add_format({
            'font_name': 'Arial', 'font_size': 10,
            'align': 'center', 'valign': 'vcenter',
            'border': 1, 'reading_order': 2,
        })
        data_alt_fmt = workbook.add_format({
            'font_name': 'Arial', 'font_size': 10,
            'align': 'center', 'valign': 'vcenter',
            'bg_color': '#D6E4F0',
            'border': 1, 'reading_order': 2,
        })
        comment_fmt = workbook.add_format({
            'font_name': 'Arial', 'font_size': 9,
            'align': 'right', 'valign': 'vcenter',
            'text_wrap': True, 'border': 1, 'reading_order': 2,
        })
        comment_alt_fmt = workbook.add_format({
            'font_name': 'Arial', 'font_size': 9,
            'align': 'right', 'valign': 'vcenter',
            'text_wrap': True, 'border': 1,
            'bg_color': '#D6E4F0', 'reading_order': 2,
        })
        total_fmt = workbook.add_format({
            'bold': True, 'font_name': 'Arial', 'font_size': 10,
            'align': 'center', 'valign': 'vcenter',
            'bg_color': '#FFF2CC', 'border': 1, 'reading_order': 2,
        })
        tick_fmt = workbook.add_format({
            'bold': True, 'font_name': 'Arial', 'font_size': 10,
            'font_color': '#1F4E79',
            'align': 'center', 'valign': 'vcenter',
            'border': 1, 'reading_order': 2,
        })
        tick_alt_fmt = workbook.add_format({
            'bold': True, 'font_name': 'Arial', 'font_size': 10,
            'font_color': '#1F4E79', 'bg_color': '#D6E4F0',
            'align': 'center', 'valign': 'vcenter',
            'border': 1, 'reading_order': 2,
        })

        all_totals = []
        for date_str in date_order:
            day_leads = date_groups[date_str]
            ws = workbook.add_worksheet(date_str)
            ws.right_to_left()

            # column widths
            ws.set_column(0, 0, 5)
            ws.set_column(1, 1, 10)
            ws.set_column(2, 2, 13)
            ws.set_column(3, 3, 14)
            ws.set_column(4, 4, 22)
            ws.set_column(5, 5, 18)
            ws.set_column(6, 6, 18)
            ws.set_column(7, 11, 9)
            ws.set_column(12, 16, 13)
            ws.set_column(17, 17, 45)
            ws.set_row(0, 22)
            ws.set_row(1, 20)
            ws.set_row(2, 16)

            ws.merge_range(0, 0, 0, 6, '', hdr1_fmt)
            ws.merge_range(0, 7, 0, 11, 'تصنيف الرسالة', hdr1_blue_fmt)
            ws.merge_range(0, 12, 0, 16, 'تصنيف العميل', hdr1_green_fmt)
            ws.write(0, 17, 'الكومنت', hdr1_grey_fmt)

            col_names = [
                ('م',                      hdr2_dark_fmt),
                ('الوقت',                  hdr2_dark_fmt),
                ('المسئول',                hdr2_dark_fmt),
                ('التاريخ',                hdr2_dark_fmt),
                ('إسم العميل',             hdr2_dark_fmt),
                ('رقم التليفون',           hdr2_dark_fmt),
                ('نوع الكامبين',           hdr2_dark_fmt),
                ('واتساب',                 hdr2_blue_fmt),
                ('فيسبوك',                 hdr2_blue_fmt),
                ('',                       hdr2_blue_fmt),
                ('إنستجرام',              hdr2_blue_fmt),
                ('',                       hdr2_blue_fmt),
                ('لم يرد',                 hdr2_green_fmt),
                ('احتمالية المتابعة 40 %', hdr2_green_fmt),
                ('اوت',                    hdr2_green_fmt),
                ('احتمالية المتابعة 90 %', hdr2_green_fmt),
                ('معاينة',                 hdr2_green_fmt),
                ('الكومنت',               hdr2_grey_fmt),
            ]
            for col_i, (name, fmt) in enumerate(col_names):
                ws.write(1, col_i, name, fmt)

            row3 = [
                ('', hdr2_dark_fmt),
                ('', hdr2_dark_fmt),
                ('', hdr2_dark_fmt),
                ('', hdr2_dark_fmt),
                ('', hdr2_dark_fmt),
                ('', hdr2_dark_fmt),
                ('', hdr2_dark_fmt),
                ('', hdr2_blue_fmt),
                ('رسالة', hdr2_blue_fmt),
                ('رقم',   hdr2_blue_fmt),
                ('رسالة', hdr2_blue_fmt),
                ('رقم',   hdr2_blue_fmt),
                ('', hdr2_green_fmt),
                ('', hdr2_green_fmt),
                ('', hdr2_green_fmt),
                ('', hdr2_green_fmt),
                ('', hdr2_green_fmt),
                ('', hdr2_grey_fmt),
            ]
            for col_i, (val, fmt) in enumerate(row3):
                ws.write(2, col_i, val, fmt)

            totals = {k: 0 for k in [
                'whatsapp', 'fb_msg', 'fb_num', 'ig_msg', 'ig_num',
                'no_answer', 'follow_40', 'out', 'follow_90', 'inspection',
            ]}

            for idx, lead in enumerate(day_leads):
                row_i = idx + 3
                is_alt = idx % 2 == 1
                df = data_alt_fmt if is_alt else data_fmt
                tf = tick_alt_fmt if is_alt else tick_fmt
                cf = comment_alt_fmt if is_alt else comment_fmt

                ws.set_row(row_i, 22)

                msg  = self._classify_message(lead)
                cust = self._classify_customer(lead)

                for k, v in msg.items():
                    if v:
                        totals[k] += 1
                for k, v in cust.items():
                    if v:
                        totals[k] += 1

                t_str = lead.visit_time or ''

                row_vals = [
                    (idx + 1,                                              df),
                    (t_str,                                                df),
                    (lead.user_id.name or '',                              df),
                    (date_str,                                             df),
                    (lead.partner_name or lead.contact_name or '',         df),
                    (lead.mobile or lead.phone or '',                      df),
                    (self._campaign_type(lead),                            df),
                    (msg['whatsapp'] or '',  tf if msg['whatsapp']  else df),
                    (msg['fb_msg']   or '',  tf if msg['fb_msg']    else df),
                    (msg['fb_num']   or '',  tf if msg['fb_num']    else df),
                    (msg['ig_msg']   or '',  tf if msg['ig_msg']    else df),
                    (msg['ig_num']   or '',  tf if msg['ig_num']    else df),
                    (cust['no_answer']   or '', tf if cust['no_answer']   else df),
                    (cust['follow_40']   or '', tf if cust['follow_40']   else df),
                    (cust['out']         or '', tf if cust['out']         else df),
                    (cust['follow_90']   or '', tf if cust['follow_90']   else df),
                    (cust['inspection']  or '', tf if cust['inspection']  else df),
                    (self._clean_description(lead.description),            cf),
                ]
                for col_i, (val, fmt) in enumerate(row_vals):
                    ws.write(row_i, col_i, val, fmt)

            country_totals = {}
            country_order = []
            for lead in day_leads:
                if lead.country_id and lead.country_id.name:
                    c_name = lead.country_id.name.strip()
                else:
                    c_name = 'بدون دولة'
                if c_name not in country_totals:
                    country_totals[c_name] = {k: 0 for k in totals.keys()}
                    country_order.append(c_name)
                msg = self._classify_message(lead)
                cust = self._classify_customer(lead)
                for k, v in msg.items():
                    if v: country_totals[c_name][k] += 1
                for k, v in cust.items():
                    if v: country_totals[c_name][k] += 1

            # ترتيب تنازلي حسب الإجمالي
            sorted_countries = sorted(
                country_order,
                key=lambda x: sum(country_totals[x].values()),
                reverse=True
            )
            sub_total_start = len(day_leads) + 3

            current_sub_row = sub_total_start
            for c_name in sorted_countries:
                ct = country_totals[c_name]
                ws.set_row(current_sub_row, 20)
                for col_i in range(0, 6):
                    ws.write(current_sub_row, col_i, '', total_fmt)
                ws.write(current_sub_row, 6, c_name, total_fmt)
                sub_vals = [
                    ct['whatsapp'], ct['fb_msg'], ct['fb_num'],
                    ct['ig_msg'], ct['ig_num'],
                    ct['no_answer'], ct['follow_40'], ct['out'],
                    ct['follow_90'], ct['inspection'],
                ]
                for col_i, val in enumerate(sub_vals, start=7):
                    ws.write(current_sub_row, col_i, val or '', total_fmt)
                ws.write(current_sub_row, 17, '', total_fmt)
                current_sub_row += 1

            # ── صف الإجمالي الكلي في الآخر تحتهم ──
            total_row = current_sub_row
            ws.set_row(total_row, 20)
            for col_i in range(0, 6):
                ws.write(total_row, col_i, '', total_fmt)
            ws.write(total_row, 6, 'الإجمالي', total_fmt)
            total_vals = [
                totals['whatsapp'], totals['fb_msg'], totals['fb_num'],
                totals['ig_msg'], totals['ig_num'],
                totals['no_answer'], totals['follow_40'], totals['out'],
                totals['follow_90'], totals['inspection'],
            ]
            for col_i, val in enumerate(total_vals, start=7):
                ws.write(total_row, col_i, val or '', total_fmt)
            ws.write(total_row, 17, '', total_fmt)


            ws.freeze_panes(3, 0)

            all_totals.append((date_str, len(day_leads), totals))

        self._build_totals_sheet(
            workbook, all_totals,
            hdr1_fmt, hdr1_blue_fmt, hdr1_green_fmt,
            data_fmt, data_alt_fmt, total_fmt,
        )
        self._build_campaign_sheet(
            workbook, ordered_leads,
            hdr1_fmt, hdr1_blue_fmt, hdr1_green_fmt, hdr1_grey_fmt,
            hdr2_dark_fmt, hdr2_blue_fmt, hdr2_green_fmt, hdr2_grey_fmt,
            data_fmt, data_alt_fmt, total_fmt, tick_fmt, tick_alt_fmt,
        )
        # ── شيت لم يرد ──
        no_answer_leads = [l for l in ordered_leads if l.no_response]
        self._build_filtered_sheet(
            workbook, 'لم يرد', no_answer_leads,
            hdr1_fmt, hdr1_blue_fmt, hdr1_green_fmt, hdr1_grey_fmt,
            hdr2_dark_fmt, hdr2_blue_fmt, hdr2_green_fmt, hdr2_grey_fmt,
            data_fmt, data_alt_fmt, comment_fmt, comment_alt_fmt,
            total_fmt, tick_fmt, tick_alt_fmt,
        )

        # ── شيت متابعة 40% ──
        follow_40_leads = [l for l in ordered_leads if l.probability_client == '40']
        self._build_filtered_sheet(
            workbook, 'متابعة 40%', follow_40_leads,
            hdr1_fmt, hdr1_blue_fmt, hdr1_green_fmt, hdr1_grey_fmt,
            hdr2_dark_fmt, hdr2_blue_fmt, hdr2_green_fmt, hdr2_grey_fmt,
            data_fmt, data_alt_fmt, comment_fmt, comment_alt_fmt,
            total_fmt, tick_fmt, tick_alt_fmt,
        )

        # ── شيت متابعة 90% ──
        follow_90_leads = [l for l in ordered_leads if l.probability_client == '90']
        self._build_filtered_sheet(
            workbook, 'متابعة 90%', follow_90_leads,
            hdr1_fmt, hdr1_blue_fmt, hdr1_green_fmt, hdr1_grey_fmt,
            hdr2_dark_fmt, hdr2_blue_fmt, hdr2_green_fmt, hdr2_grey_fmt,
            data_fmt, data_alt_fmt, comment_fmt, comment_alt_fmt,
            total_fmt, tick_fmt, tick_alt_fmt,
        )

        # ── شيت معاينة ──
        inspection_leads = [l for l in ordered_leads if l.is_preview]
        self._build_filtered_sheet(
            workbook, 'معاينة', inspection_leads,
            hdr1_fmt, hdr1_blue_fmt, hdr1_green_fmt, hdr1_grey_fmt,
            hdr2_dark_fmt, hdr2_blue_fmt, hdr2_green_fmt, hdr2_grey_fmt,
            data_fmt, data_alt_fmt, comment_fmt, comment_alt_fmt,
            total_fmt, tick_fmt, tick_alt_fmt,
        )
        # ── شيت اوت = الليدز اللي عليها is_out=True ──
        out_leads = [l for l in ordered_leads if l.is_out]
        self._build_out_lost_sheet(
            workbook, out_leads,
            hdr1_fmt, hdr1_blue_fmt, hdr1_green_fmt, hdr1_grey_fmt,
            hdr2_dark_fmt, hdr2_blue_fmt, hdr2_green_fmt, hdr2_grey_fmt,
            data_fmt, data_alt_fmt, comment_fmt, comment_alt_fmt,
            total_fmt, tick_fmt, tick_alt_fmt,
        )
        workbook.close()
        output.seek(0)
        content = output.read()

        headers = [
            ('Content-Type',
             'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Disposition',
             'attachment; filename="campaign_report.xlsx"'),
            ('Content-Length', str(len(content))),
        ]
        return request.make_response(content, headers=headers)



    def _campaign_type(self, lead):
        """
        نوع الكامبين = street + country + state
        Example: Egypt-Al Sharqia (EG)
        لو مفيش قيمة يرجع فراغ
        """
        parts = []
        if lead.street:
            parts.append(lead.street.strip())
        if lead.country_id and lead.country_id.name:
            c_name = lead.country_id.name.strip()
            code = (lead.country_id.code or '').strip()
            if lead.state_id and lead.state_id.name:
                c_name = '%s-%s (%s)' % (c_name, lead.state_id.name.strip(), code)
            else:
                c_name = '%s (%s)' % (c_name, code) if code else c_name
            parts.append(c_name)
        return ' - '.join(parts) if parts else ''

    def _classify_message(self, lead):
        """
        تصنيف الرسالة بناءً على campaign_id فقط.
        لو مفيش campaign كل الحقول تفضل فاضية.
        """
        result = {
            'whatsapp': None,
            'fb_msg':   None,
            'fb_num':   None,
            'ig_msg':   None,
            'ig_num':   None,
        }

        if not lead.campaign_id:
            return result

        campaign_name = (lead.campaign_id.name or '').strip().lower()

        if not campaign_name:
            return result

        # واتساب
        if any(x in campaign_name for x in ['whatsapp', 'واتساب', 'wts', 'wa']):
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        result['whatsapp'] = 1

        # فيسبوك
        elif any(x in campaign_name for x in ['facebook', 'فيسبوك', 'fb']):
            result['fb_msg'] = 1

            if lead.num_of_media:
                result['fb_num'] = 1

        # انستجرام
        elif any(x in campaign_name for x in ['instagram', 'انستجرام', 'insta', 'ig']):
            result['ig_msg'] = 1

            if lead.num_of_media:
                result['ig_num'] = 1

        return result

    def _classify_customer(self, lead):
        """
        تصنيف العميل بناءً على اسم المرحلة أو الاحتمالية.
        """
        stage = (lead.stage_id.name or '').strip().lower()
        prob  = lead.probability or 0
        result = {
            'no_answer':  None,
            'follow_40':  None,
            'out':        None,
            'follow_90':  None,
            'inspection': None,
        }

        if lead.no_response:
            result['no_answer'] = 1

            # احتمال 40%
        if lead.probability_client == '40':
            result['follow_40'] = 1

            # احتمال 90%
        if lead.probability_client == '90':
            result['follow_90'] = 1

            # اوت
        if lead.is_out:
            result['out'] = 1

            # معاينة
        if lead.is_preview:
            result['inspection'] = 1

        return result



    def _clean_description(self, description):
        """
        تنظيف الكومنت:
        - شيل HTML tags
        - شيل السطور الفاضية الزيادة
        - شيل المسافات الزيادة
        """
        if not description:
            return ''
        clean = re.sub(r'<[^>]+>', ' ', description)
        clean = re.sub(r'&[a-zA-Z]+;', ' ', clean)
        clean = re.sub(r'\n{3,}', '\n\n', clean)
        clean = re.sub(r'  +', ' ', clean)
        return clean.strip()

    def _build_totals_sheet(self, workbook, all_totals,
                            hdr1_fmt, hdr1_blue_fmt, hdr1_green_fmt,
                            data_fmt, data_alt_fmt, total_fmt):
        """إنشاء شيت الاجماليات."""
        ws = workbook.add_worksheet('الاجماليات')
        ws.right_to_left()

        ws.set_column(0, 0,  6)
        ws.set_column(1, 1, 14)
        ws.set_column(2, 2, 10)
        ws.set_column(3, 12, 13)
        ws.set_row(0, 22)

        headers = [
            ('م',               hdr1_fmt),
            ('التاريخ',         hdr1_fmt),
            ('الإجمالي',        hdr1_fmt),
            ('واتساب',          hdr1_blue_fmt),
            ('فيسبوك رسالة',   hdr1_blue_fmt),
            ('فيسبوك رقم',     hdr1_blue_fmt),
            ('انستجرام رسالة', hdr1_blue_fmt),
            ('انستجرام رقم',   hdr1_blue_fmt),
            ('لم يرد',          hdr1_green_fmt),
            ('متابعة 40%',      hdr1_green_fmt),
            ('اوت',             hdr1_green_fmt),
            ('متابعة 90%',      hdr1_green_fmt),
            ('معاينة',          hdr1_green_fmt),
        ]
        for col_i, (hdr, fmt) in enumerate(headers):
            ws.write(0, col_i, hdr, fmt)

        for row_i, (date_str, count, totals) in enumerate(all_totals, start=1):
            ws.set_row(row_i, 18)
            is_alt = row_i % 2 == 0
            df = data_alt_fmt if is_alt else data_fmt
            row_data = [
                row_i,
                date_str,
                count,
                totals['whatsapp'],
                totals['fb_msg'],
                totals['fb_num'],
                totals['ig_msg'],
                totals['ig_num'],
                totals['no_answer'],
                totals['follow_40'],
                totals['out'],
                totals['follow_90'],
                totals['inspection'],
            ]
            for col_i, val in enumerate(row_data):
                ws.write(row_i, col_i, val or 0, df)

        # grand total
        total_row = len(all_totals) + 1
        ws.set_row(total_row, 20)
        ws.write(total_row, 0, 'الإجمالي', total_fmt)
        ws.write(total_row, 1, '', total_fmt)
        ws.write(total_row, 2, sum(x[1] for x in all_totals), total_fmt)
        keys = ['whatsapp', 'fb_msg', 'fb_num', 'ig_msg', 'ig_num',
                'no_answer', 'follow_40', 'out', 'follow_90', 'inspection']
        for col_i, k in enumerate(keys, start=3):
            ws.write(total_row, col_i,
                     sum(x[2][k] for x in all_totals), total_fmt)

        ws.freeze_panes(1, 0)

    def _build_campaign_sheet(self, workbook, all_leads,
                              hdr1_fmt, hdr1_blue_fmt, hdr1_green_fmt, hdr1_grey_fmt,
                              hdr2_dark_fmt, hdr2_blue_fmt, hdr2_green_fmt, hdr2_grey_fmt,
                              data_fmt, data_alt_fmt, total_fmt, tick_fmt, tick_alt_fmt):
        """شيت تقرير الكامباين - مجمع حسب نوع الكامباين"""
        ws = workbook.add_worksheet('تقرير الكامباين')
        ws.right_to_left()

        ws.set_column(0, 0, 5)
        ws.set_column(1, 1, 10)
        ws.set_column(2, 2, 13)
        ws.set_column(3, 3, 14)
        ws.set_column(4, 4, 22)
        ws.set_column(5, 5, 18)
        ws.set_column(6, 6, 18)
        ws.set_column(7, 11, 9)
        ws.set_column(12, 16, 13)
        ws.set_column(17, 17, 45)
        ws.set_row(0, 22)
        ws.set_row(1, 20)
        ws.set_row(2, 16)

        ws.merge_range(0, 0, 0, 6, '', hdr1_fmt)
        ws.merge_range(0, 7, 0, 11, 'تصنيف الرسالة', hdr1_blue_fmt)
        ws.merge_range(0, 12, 0, 16, 'تصنيف العميل', hdr1_green_fmt)
        ws.write(0, 17, 'الكومنت', hdr1_grey_fmt)

        col_names = [
            ('م', hdr2_dark_fmt),
            ('الوقت', hdr2_dark_fmt),
            ('المسئول', hdr2_dark_fmt),
            ('التاريخ', hdr2_dark_fmt),
            ('إسم العميل', hdr2_dark_fmt),
            ('رقم التليفون', hdr2_dark_fmt),
            ('نوع الكامبين', hdr2_dark_fmt),
            ('واتساب', hdr2_blue_fmt),
            ('فيسبوك', hdr2_blue_fmt),
            ('', hdr2_blue_fmt),
            ('إنستجرام', hdr2_blue_fmt),
            ('', hdr2_blue_fmt),
            ('لم يرد', hdr2_green_fmt),
            ('احتمالية المتابعة 40 %', hdr2_green_fmt),
            ('اوت', hdr2_green_fmt),
            ('احتمالية المتابعة 90 %', hdr2_green_fmt),
            ('معاينة', hdr2_green_fmt),
            ('الكومنت', hdr2_grey_fmt),
        ]
        for col_i, (name, fmt) in enumerate(col_names):
            ws.write(1, col_i, name, fmt)

        row3 = [
            ('', hdr2_dark_fmt), ('', hdr2_dark_fmt), ('', hdr2_dark_fmt),
            ('', hdr2_dark_fmt), ('', hdr2_dark_fmt), ('', hdr2_dark_fmt),
            ('', hdr2_dark_fmt),
            ('', hdr2_blue_fmt), ('رسالة', hdr2_blue_fmt), ('رقم', hdr2_blue_fmt),
            ('رسالة', hdr2_blue_fmt), ('رقم', hdr2_blue_fmt),
            ('', hdr2_green_fmt), ('', hdr2_green_fmt), ('', hdr2_green_fmt),
            ('', hdr2_green_fmt), ('', hdr2_green_fmt),
            ('', hdr2_grey_fmt),
        ]
        for col_i, (val, fmt) in enumerate(row3):
            ws.write(2, col_i, val, fmt)



        campaign_data = {}
        campaign_order = []

        # ليدز مهندسين الديكور منفصلة
        decor_data = {
            'total': 0, 'whatsapp': 0, 'fb_msg': 0, 'fb_num': 0,
            'ig_msg': 0, 'ig_num': 0,
            'no_answer': 0, 'follow_40': 0, 'out': 0,
            'follow_90': 0, 'inspection': 0,
        }

        for lead in all_leads:
            # فحص لو الليد ده من مهندسين الديكور
            camp_name_raw = (lead.campaign_id.name or '').lower()
            is_decor = 'ديكور' in camp_name_raw or 'decor' in camp_name_raw

            if is_decor:
                decor_data['total'] += 1
                msg = self._classify_message(lead)
                cust = self._classify_customer(lead)
                for k, v in msg.items():
                    if v: decor_data[k] += 1
                for k, v in cust.items():
                    if v: decor_data[k] += 1
                continue

            if lead.country_id and lead.country_id.name:
                c_name = lead.country_id.name.strip()
            else:
                c_name = 'بدون دولة'

            if c_name not in campaign_data:
                campaign_data[c_name] = {
                    'total': 0, 'whatsapp': 0, 'fb_msg': 0, 'fb_num': 0,
                    'ig_msg': 0, 'ig_num': 0,
                    'no_answer': 0, 'follow_40': 0, 'out': 0,
                    'follow_90': 0, 'inspection': 0,
                }
                campaign_order.append(c_name)

            d = campaign_data[c_name]
            d['total'] += 1
            msg = self._classify_message(lead)
            cust = self._classify_customer(lead)
            for k, v in msg.items():
                if v: d[k] += 1
            for k, v in cust.items():
                if v: d[k] += 1

        sorted_campaigns = sorted(campaign_order,
                                  key=lambda x: campaign_data[x]['total'],
                                  reverse=True)

        keys_msg = ['whatsapp', 'fb_msg', 'fb_num', 'ig_msg', 'ig_num']
        keys_cust = ['no_answer', 'follow_40', 'out', 'follow_90', 'inspection']

        def write_data_row(ws, row_i, idx_num, label, d, is_alt):
            df = data_alt_fmt if is_alt else data_fmt
            tf = tick_alt_fmt if is_alt else tick_fmt

            row_vals = [
                (idx_num, df),
                ('', df),
                ('', df),
                ('', df),
                ('', df),
                ('', df),
                (label, df),
                (d['whatsapp'] or '', tf if d['whatsapp'] else df),
                (d['fb_msg'] or '', tf if d['fb_msg'] else df),
                (d['fb_num'] or '', tf if d['fb_num'] else df),
                (d['ig_msg'] or '', tf if d['ig_msg'] else df),
                (d['ig_num'] or '', tf if d['ig_num'] else df),
                (d['no_answer'] or '', tf if d['no_answer'] else df),
                (d['follow_40'] or '', tf if d['follow_40'] else df),
                (d['out'] or '', tf if d['out'] else df),
                (d['follow_90'] or '', tf if d['follow_90'] else df),
                (d['inspection'] or '', tf if d['inspection'] else df),
                ('', df),
            ]
            ws.set_row(row_i, 22)
            for col_i, (val, fmt) in enumerate(row_vals):
                ws.write(row_i, col_i, val, fmt)

        for idx, c_name in enumerate(sorted_campaigns):
            write_data_row(ws, idx + 3, idx + 1, c_name,
                           campaign_data[c_name], idx % 2 == 1)

        current_row = len(sorted_campaigns) + 3

        ws.set_row(current_row, 22)
        for col_i in range(18):
            ws.write(current_row, col_i, '', data_fmt)
        current_row += 1

        write_data_row(ws, current_row, '', 'مهندسين الديكور', decor_data, False)
        current_row += 1

        ws.set_row(current_row, 20)
        grand = {k: sum(campaign_data[c][k] for c in sorted_campaigns)
                 for k in (['total'] + keys_msg + keys_cust)}
        for k in keys_msg + keys_cust:
            grand[k] += decor_data[k]
        grand['total'] += decor_data['total']

        ws.write(current_row, 0, '', total_fmt)
        ws.write(current_row, 1, '', total_fmt)
        ws.write(current_row, 2, '', total_fmt)
        ws.write(current_row, 3, '', total_fmt)
        ws.write(current_row, 4, '', total_fmt)
        ws.write(current_row, 5, '', total_fmt)
        ws.write(current_row, 6, grand['total'], total_fmt)
        total_vals = [
            grand['whatsapp'], grand['fb_msg'], grand['fb_num'],
            grand['ig_msg'], grand['ig_num'],
            grand['no_answer'], grand['follow_40'], grand['out'],
            grand['follow_90'], grand['inspection'],
        ]
        for col_i, val in enumerate(total_vals, start=7):
            ws.write(current_row, col_i, val or '', total_fmt)
        ws.write(current_row, 17, '', total_fmt)

        ws.freeze_panes(3, 0)

    def _build_filtered_sheet(self, workbook, sheet_name, leads,
                              hdr1_fmt, hdr1_blue_fmt, hdr1_green_fmt, hdr1_grey_fmt,
                              hdr2_dark_fmt, hdr2_blue_fmt, hdr2_green_fmt, hdr2_grey_fmt,
                              data_fmt, data_alt_fmt, comment_fmt, comment_alt_fmt,
                              total_fmt, tick_fmt, tick_alt_fmt):
        """شيت مفلتر يعرض الليدز بنفس شكل الشيتات اليومية"""
        ws = workbook.add_worksheet(sheet_name)
        ws.right_to_left()

        ws.set_column(0, 0, 5)
        ws.set_column(1, 1, 10)
        ws.set_column(2, 2, 13)
        ws.set_column(3, 3, 14)
        ws.set_column(4, 4, 22)
        ws.set_column(5, 5, 18)
        ws.set_column(6, 6, 18)
        ws.set_column(7, 11, 9)
        ws.set_column(12, 16, 13)
        ws.set_column(17, 17, 45)
        ws.set_row(0, 22)
        ws.set_row(1, 20)
        ws.set_row(2, 16)

        ws.merge_range(0, 0, 0, 6, '', hdr1_fmt)
        ws.merge_range(0, 7, 0, 11, 'تصنيف الرسالة', hdr1_blue_fmt)
        ws.merge_range(0, 12, 0, 16, 'تصنيف العميل', hdr1_green_fmt)
        ws.write(0, 17, 'الكومنت', hdr1_grey_fmt)

        col_names = [
            ('م', hdr2_dark_fmt),
            ('الوقت', hdr2_dark_fmt),
            ('المسئول', hdr2_dark_fmt),
            ('التاريخ', hdr2_dark_fmt),
            ('إسم العميل', hdr2_dark_fmt),
            ('رقم التليفون', hdr2_dark_fmt),
            ('نوع الكامبين', hdr2_dark_fmt),
            ('واتساب', hdr2_blue_fmt),
            ('فيسبوك', hdr2_blue_fmt),
            ('', hdr2_blue_fmt),
            ('إنستجرام', hdr2_blue_fmt),
            ('', hdr2_blue_fmt),
            ('لم يرد', hdr2_green_fmt),
            ('احتمالية المتابعة 40 %', hdr2_green_fmt),
            ('اوت', hdr2_green_fmt),
            ('احتمالية المتابعة 90 %', hdr2_green_fmt),
            ('معاينة', hdr2_green_fmt),
            ('الكومنت', hdr2_grey_fmt),
        ]
        for col_i, (name, fmt) in enumerate(col_names):
            ws.write(1, col_i, name, fmt)

        row3 = [
            ('', hdr2_dark_fmt), ('', hdr2_dark_fmt), ('', hdr2_dark_fmt),
            ('', hdr2_dark_fmt), ('', hdr2_dark_fmt), ('', hdr2_dark_fmt),
            ('', hdr2_dark_fmt),
            ('', hdr2_blue_fmt), ('رسالة', hdr2_blue_fmt), ('رقم', hdr2_blue_fmt),
            ('رسالة', hdr2_blue_fmt), ('رقم', hdr2_blue_fmt),
            ('', hdr2_green_fmt), ('', hdr2_green_fmt), ('', hdr2_green_fmt),
            ('', hdr2_green_fmt), ('', hdr2_green_fmt),
            ('', hdr2_grey_fmt),
        ]
        for col_i, (val, fmt) in enumerate(row3):
            ws.write(2, col_i, val, fmt)

        totals = {k: 0 for k in [
            'whatsapp', 'fb_msg', 'fb_num', 'ig_msg', 'ig_num',
            'no_answer', 'follow_40', 'out', 'follow_90', 'inspection',
        ]}

        for idx, lead in enumerate(leads):
            row_i = idx + 3
            is_alt = idx % 2 == 1
            df = data_alt_fmt if is_alt else data_fmt
            tf = tick_alt_fmt if is_alt else tick_fmt
            cf = comment_alt_fmt if is_alt else comment_fmt

            ws.set_row(row_i, 22)

            msg = self._classify_message(lead)
            cust = self._classify_customer(lead)

            for k, v in msg.items():
                if v: totals[k] += 1
            for k, v in cust.items():
                if v: totals[k] += 1

            # التاريخ
            d = lead.visit_date
            date_str = '%d-%d-%d' % (d.day, d.month, d.year) if d else ''

            row_vals = [
                (idx + 1, df),
                (lead.visit_time or '', df),
                (lead.user_id.name or '', df),
                (date_str, df),
                (lead.partner_name or lead.contact_name or '', df),
                (lead.mobile or lead.phone or '', df),
                (self._campaign_type(lead), df),
                (msg['whatsapp'] or '', tf if msg['whatsapp'] else df),
                (msg['fb_msg'] or '', tf if msg['fb_msg'] else df),
                (msg['fb_num'] or '', tf if msg['fb_num'] else df),
                (msg['ig_msg'] or '', tf if msg['ig_msg'] else df),
                (msg['ig_num'] or '', tf if msg['ig_num'] else df),
                (cust['no_answer'] or '', tf if cust['no_answer'] else df),
                (cust['follow_40'] or '', tf if cust['follow_40'] else df),
                (cust['out'] or '', tf if cust['out'] else df),
                (cust['follow_90'] or '', tf if cust['follow_90'] else df),
                (cust['inspection'] or '', tf if cust['inspection'] else df),
                (self._clean_description(lead.description), cf),
            ]
            for col_i, (val, fmt) in enumerate(row_vals):
                ws.write(row_i, col_i, val, fmt)

        # ── صف الإجمالي ──
        total_row = len(leads) + 3
        ws.set_row(total_row, 20)
        for col_i in range(0, 6):
            ws.write(total_row, col_i, '', total_fmt)
        ws.write(total_row, 6, 'الإجمالي', total_fmt)
        total_vals = [
            totals['whatsapp'], totals['fb_msg'], totals['fb_num'],
            totals['ig_msg'], totals['ig_num'],
            totals['no_answer'], totals['follow_40'], totals['out'],
            totals['follow_90'], totals['inspection'],
        ]
        for col_i, val in enumerate(total_vals, start=7):
            ws.write(total_row, col_i, val or '', total_fmt)
        ws.write(total_row, 17, '', total_fmt)

        ws.freeze_panes(3, 0)

    def _build_out_lost_sheet(self, workbook, leads,
                              hdr1_fmt, hdr1_blue_fmt, hdr1_green_fmt, hdr1_grey_fmt,
                              hdr2_dark_fmt, hdr2_blue_fmt, hdr2_green_fmt, hdr2_grey_fmt,
                              data_fmt, data_alt_fmt, comment_fmt, comment_alt_fmt,
                              total_fmt, tick_fmt, tick_alt_fmt):
        """شيت اوت - يعرض كل الليدز الخسرانة مع سبب الخسارة بعد نوع الكامبين"""
        ws = workbook.add_worksheet('اوت')
        ws.right_to_left()

        hdr1_red_fmt = workbook.add_format({
            'bold': True, 'font_name': 'Arial', 'font_size': 11,
            'font_color': '#FFFFFF', 'bg_color': '#C00000',
            'align': 'center', 'valign': 'vcenter',
            'border': 1, 'reading_order': 2,
        })
        hdr2_red_fmt = workbook.add_format({
            'bold': True, 'font_name': 'Arial', 'font_size': 10,
            'font_color': '#FFFFFF', 'bg_color': '#C00000',
            'align': 'center', 'valign': 'vcenter',
            'border': 1, 'text_wrap': True, 'reading_order': 2,
        })

        ws.set_column(0, 0, 5)
        ws.set_column(1, 1, 10)
        ws.set_column(2, 2, 13)
        ws.set_column(3, 3, 14)
        ws.set_column(4, 4, 22)
        ws.set_column(5, 5, 18)
        ws.set_column(6, 6, 18)
        ws.set_column(7, 7, 22)   # سبب الخسارة
        ws.set_column(8, 12, 9)
        ws.set_column(13, 17, 13)
        ws.set_column(18, 18, 45)
        ws.set_row(0, 22)
        ws.set_row(1, 20)
        ws.set_row(2, 16)

        ws.merge_range(0, 0, 0, 6, '', hdr1_fmt)
        ws.write(0, 7, 'سبب الخسارة', hdr1_red_fmt)
        ws.merge_range(0, 8, 0, 12, 'تصنيف الرسالة', hdr1_blue_fmt)
        ws.merge_range(0, 13, 0, 17, 'تصنيف العميل', hdr1_green_fmt)
        ws.write(0, 18, 'الكومنت', hdr1_grey_fmt)

        col_names = [
            ('م',                      hdr2_dark_fmt),
            ('الوقت',                  hdr2_dark_fmt),
            ('المسئول',                hdr2_dark_fmt),
            ('التاريخ',                hdr2_dark_fmt),
            ('إسم العميل',             hdr2_dark_fmt),
            ('رقم التليفون',           hdr2_dark_fmt),
            ('نوع الكامبين',           hdr2_dark_fmt),
            ('سبب الخسارة',            hdr2_red_fmt),
            ('واتساب',                 hdr2_blue_fmt),
            ('فيسبوك',                 hdr2_blue_fmt),
            ('',                       hdr2_blue_fmt),
            ('إنستجرام',              hdr2_blue_fmt),
            ('',                       hdr2_blue_fmt),
            ('لم يرد',                 hdr2_green_fmt),
            ('احتمالية المتابعة 40 %', hdr2_green_fmt),
            ('اوت',                    hdr2_green_fmt),
            ('احتمالية المتابعة 90 %', hdr2_green_fmt),
            ('معاينة',                 hdr2_green_fmt),
            ('الكومنت',               hdr2_grey_fmt),
        ]
        for col_i, (name, fmt) in enumerate(col_names):
            ws.write(1, col_i, name, fmt)

        row3 = [
            ('', hdr2_dark_fmt), ('', hdr2_dark_fmt), ('', hdr2_dark_fmt),
            ('', hdr2_dark_fmt), ('', hdr2_dark_fmt), ('', hdr2_dark_fmt),
            ('', hdr2_dark_fmt),
            ('', hdr2_red_fmt),
            ('', hdr2_blue_fmt), ('رسالة', hdr2_blue_fmt), ('رقم', hdr2_blue_fmt),
            ('رسالة', hdr2_blue_fmt), ('رقم', hdr2_blue_fmt),
            ('', hdr2_green_fmt), ('', hdr2_green_fmt), ('', hdr2_green_fmt),
            ('', hdr2_green_fmt), ('', hdr2_green_fmt),
            ('', hdr2_grey_fmt),
        ]
        for col_i, (val, fmt) in enumerate(row3):
            ws.write(2, col_i, val, fmt)

        totals = {k: 0 for k in [
            'whatsapp', 'fb_msg', 'fb_num', 'ig_msg', 'ig_num',
            'no_answer', 'follow_40', 'out', 'follow_90', 'inspection',
        ]}

        for idx, lead in enumerate(leads):
            row_i = idx + 3
            is_alt = idx % 2 == 1
            df = data_alt_fmt if is_alt else data_fmt
            tf = tick_alt_fmt if is_alt else tick_fmt
            cf = comment_alt_fmt if is_alt else comment_fmt

            ws.set_row(row_i, 22)

            msg = self._classify_message(lead)
            cust = self._classify_customer(lead)

            for k, v in msg.items():
                if v: totals[k] += 1
            for k, v in cust.items():
                if v: totals[k] += 1

            d = lead.visit_date
            date_str = '%d-%d-%d' % (d.day, d.month, d.year) if d else ''
            lost_reason = lead.lost_reason_id.name if lead.lost_reason_id else ''

            row_vals = [
                (idx + 1, df),
                (lead.visit_time or '', df),
                (lead.user_id.name or '', df),
                (date_str, df),
                (lead.partner_name or lead.contact_name or '', df),
                (lead.mobile or lead.phone or '', df),
                (self._campaign_type(lead), df),
                (lost_reason, df),
                (msg['whatsapp'] or '', tf if msg['whatsapp'] else df),
                (msg['fb_msg'] or '', tf if msg['fb_msg'] else df),
                (msg['fb_num'] or '', tf if msg['fb_num'] else df),
                (msg['ig_msg'] or '', tf if msg['ig_msg'] else df),
                (msg['ig_num'] or '', tf if msg['ig_num'] else df),
                (cust['no_answer'] or '', tf if cust['no_answer'] else df),
                (cust['follow_40'] or '', tf if cust['follow_40'] else df),
                (cust['out'] or '', tf if cust['out'] else df),
                (cust['follow_90'] or '', tf if cust['follow_90'] else df),
                (cust['inspection'] or '', tf if cust['inspection'] else df),
                (self._clean_description(lead.description), cf),
            ]
            for col_i, (val, fmt) in enumerate(row_vals):
                ws.write(row_i, col_i, val, fmt)

        total_row = len(leads) + 3
        ws.set_row(total_row, 20)
        for col_i in range(0, 6):
            ws.write(total_row, col_i, '', total_fmt)
        ws.write(total_row, 6, 'الإجمالي', total_fmt)
        ws.write(total_row, 7, '', total_fmt)
        total_vals = [
            totals['whatsapp'], totals['fb_msg'], totals['fb_num'],
            totals['ig_msg'], totals['ig_num'],
            totals['no_answer'], totals['follow_40'], totals['out'],
            totals['follow_90'], totals['inspection'],
        ]
        for col_i, val in enumerate(total_vals, start=8):
            ws.write(total_row, col_i, val or '', total_fmt)
        ws.write(total_row, 18, '', total_fmt)

        ws.freeze_panes(3, 0)