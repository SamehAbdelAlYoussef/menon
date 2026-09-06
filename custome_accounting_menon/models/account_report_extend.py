# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AccountReport(models.Model):
    _inherit = 'account.report'

    filter_accounts = fields.Boolean(string='Filter by Accounts', default=False)

    def _init_options_filter_accounts(self, options, previous_options):
        if not self.filter_accounts:
            return
        previous_account_ids = previous_options.get('account_ids', [])
        account_ids = [int(x) for x in previous_account_ids]
        selected_accounts = self.env['account.account'].with_context(active_test=False).search([
            ('id', 'in', account_ids)
        ])
        options['display_filter_accounts'] = True
        options['account_ids'] = selected_accounts.ids
        options['selected_account_names'] = selected_accounts.mapped('display_name')

    def _get_options_accounts_domain(self, options):
        if options.get('account_ids'):
            return [('account_id', 'in', [int(x) for x in options['account_ids']])]
        return []

    def _get_options_domain(self, options, date_scope):
        domain = super()._get_options_domain(options, date_scope)
        domain += self._get_options_accounts_domain(options)
        return domain

    def get_report_information(self, options):
        info = super().get_report_information(options)
        info['filters']['show_filter_accounts'] = options.get('display_filter_accounts', False)
        return info


class GeneralLedgerCustomHandlerExtend(models.AbstractModel):
    _inherit = 'account.general.ledger.report.handler'

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        lines = super()._dynamic_lines_generator(report, options, all_column_groups_expression_totals, warnings)

        if options.get('account_ids') and warnings is not None:
            # Only Total line returned → no account data found
            account_lines = [line for (_, line) in lines if line.get('id') != 'general_ledger_total']
            if not account_lines:
                warnings['custome_accounting_menon.warning_no_account_data'] = {
                    'alert_type': 'warning',
                }

        return lines
