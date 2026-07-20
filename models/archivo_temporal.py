from odoo import models, fields

class ArchivoTemporal(models.Model):
    _name = 'archivo.temporal'
    _description = 'Archivo Temporal'

    filecontent = fields.Binary(string="Contenido del Archivo", required=True)
