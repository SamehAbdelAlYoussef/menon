# -*- coding: utf-8 -*-
import io
import base64
import xlsxwriter
from odoo import models, fields, _


class TaqseetExcelWizard(models.TransientModel):
    _name = 'taqseet.excel.wizard'
    _description = 'Installment Companies Excel Export'

    excel_file = fields.Binary(string='Excel File', readonly=True)
    file_name = fields.Char(default='Installment_Companies_Report.xlsx')

    def _get_labels(self):
        lang = self.env.user.lang or 'en_US'
        if lang.startswith('ar'):
            return {
                'title': 'تقرير حسابات شركات التقسيط',
                'num': '#',
                'company': 'الشركة',
                'balance': 'الرصيد',
                'admin': 'مصروفات إدارية',
                'total': 'الإجمالي',
                'file': 'تقرير_شركات_التقسيط.xlsx',
                'sheet': 'شركات التقسيط',
                'rtl': True,
            }
        return {
            'title': 'Installment Companies Report',
            'num': '#',
            'company': 'Company',
            'balance': 'Balance',
            'admin': 'Administrative Expenses',
            'total': 'Total',
            'file': 'Installment_Companies_Report.xlsx',
            'sheet': 'Installment Companies',
            'rtl': False,
        }

    def action_export_excel(self):
        accounts = self.env['account.account'].search([('is_taqseet_company', '=', True)])
        lbl = self._get_labels()

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet(lbl['sheet'])

        # Styles
        header_fmt = workbook.add_format({
            'bold': True, 'bg_color': '#2c3e50', 'font_color': 'white',
            'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 11,
        })
        cell_fmt = workbook.add_format({
            'border': 1, 'valign': 'vcenter', 'font_size': 10,
        })
        num_fmt = workbook.add_format({
            'border': 1, 'valign': 'vcenter', 'font_size': 10,
            'num_format': '#,##0.00', 'align': 'right',
        })
        total_fmt = workbook.add_format({
            'bold': True, 'bg_color': '#bdc3c7', 'border': 1,
            'num_format': '#,##0.00', 'align': 'right', 'font_size': 10,
        })
        title_fmt = workbook.add_format({
            'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter',
        })

        # RTL support
        if lbl['rtl']:
            sheet.right_to_left()

        # Column widths
        sheet.set_column(0, 0, 6)
        sheet.set_column(1, 1, 35)
        sheet.set_column(2, 2, 20)
        sheet.set_column(3, 3, 25)

        # Title
        sheet.merge_range(0, 0, 0, 3, lbl['title'], title_fmt)
        sheet.set_row(0, 30)

        # Headers
        for col, h in enumerate([lbl['num'], lbl['company'], lbl['balance'], lbl['admin']]):
            sheet.write(1, col, h, header_fmt)
        sheet.set_row(1, 20)

        # Data
        total_balance = 0.0
        total_admin = 0.0
        for idx, acc in enumerate(accounts):
            row = idx + 2
            sheet.write(row, 0, idx + 1, cell_fmt)
            sheet.write(row, 1, acc.name, cell_fmt)
            sheet.write(row, 2, acc.current_balance, num_fmt)
            sheet.write(row, 3, acc.taqseet_account_balance, num_fmt)
            total_balance += acc.current_balance
            total_admin += acc.taqseet_account_balance

        # Total row
        total_row = len(accounts) + 2
        sheet.merge_range(total_row, 0, total_row, 1, lbl['total'], total_fmt)
        sheet.write(total_row, 2, total_balance, total_fmt)
        sheet.write(total_row, 3, total_admin, total_fmt)

        workbook.close()
        output.seek(0)

        self.excel_file = base64.b64encode(output.read())
        self.file_name = lbl['file']

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'taqseet.excel.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': {'form_view_initial_mode': 'edit'},
        }
