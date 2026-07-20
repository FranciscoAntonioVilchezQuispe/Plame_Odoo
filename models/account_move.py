# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    fch_detraccion = fields.Date(
        string='Fecha detracción'
    )
    constancia_detraccion = fields.Char(
        string='Constancia detracción',
    )