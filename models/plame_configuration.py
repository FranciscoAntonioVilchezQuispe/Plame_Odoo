# -*- coding: utf-8 -*-

from odoo import fields, models, api


class PlameConfiguration(models.Model):
    _name = "plame.configuration"
    _description = "Configuración PLAME Base"
    _inherit = ['plame.dashboard.mixin']

    name = fields.Char(string='Nombre', default='Configuración PLAME')
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        default=lambda self: self.env.company,
    )
    report_type = fields.Selection(selection=[
        ('RPH', 'Recibos por Honorarios - 4ta Categoría (Archivos .4ta y .ps4)'),
    ], string='Formato PLAME', default='RPH')
    
    accounts_ids = fields.Many2many(
        comodel_name='account.account',
        string='Cuentas de Gastos / Honorarios',
    )
    journal_ids = fields.Many2many(
        comodel_name='account.journal',
        string='Diarios de Honorarios / Comprobantes',
    )

    def action_create_plame_config(self, value='RPH'):
        for line in self.env['res.company'].search([]):
            self.create({'company_id': line.id, 'report_type': value})
