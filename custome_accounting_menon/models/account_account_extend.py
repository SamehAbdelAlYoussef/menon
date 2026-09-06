# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AccountAccount(models.Model):
    _inherit = 'account.account'

    is_taqseet_company = fields.Boolean(string='Installment Company')

    taqseet_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Installment Company Account',
        domain="[('company_ids', 'in', company_ids), ('id', '!=', id)]",
    )

    taqseet_account_balance = fields.Monetary(
        string='Administrative Expenses',
        compute='_compute_taqseet_account_balance',
        currency_field='company_currency_id',
    )

    @api.depends('taqseet_account_id')
    def _compute_taqseet_account_balance(self):
        for rec in self:
            if rec.taqseet_account_id:
                data = self.env['account.move.line'].read_group(
                    domain=[
                        ('account_id', '=', rec.taqseet_account_id.id),
                        ('parent_state', '=', 'posted'),
                    ],
                    fields=['balance:sum'],
                    groupby=[],
                )
                rec.taqseet_account_balance = data[0]['balance'] if data else 0.0
            else:
                rec.taqseet_account_balance = 0.0
