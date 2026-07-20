# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AccountAccount(models.Model):
    _inherit = 'account.account'

    # Extensión de cuentas contables para PLAME
