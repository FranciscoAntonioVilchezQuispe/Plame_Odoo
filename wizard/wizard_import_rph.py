# -*- coding: utf-8 -*-

import base64
import logging
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class WizardImportRph(models.TransientModel):
    _name = "wizard.import.rph"
    _description = "Wizard de Carga Masiva de RPH"

    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario de Compras/Honorarios',
        required=True,
        domain="[('type', '=', 'purchase')]",
        help="Diario contable donde se registrarán los Recibos por Honorarios."
    )
    expense_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta de Gasto',
        required=True,
        help="Cuenta contable de gastos (Clase 63) para imputar el servicio profesional."
    )
    tax_id = fields.Many2one(
        comodel_name='account.tax',
        string='Impuesto Retención 4ta (8%)',
        domain="[('type_tax_use', '=', 'purchase')]",
        help="Impuesto de retención de 4ta categoría (-8.00%) que disminuye el neto a pagar."
    )
    payment_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario de Pago',
        required=True,
        domain="[('type', 'in', ('bank', 'cash'))]",
        help="Diario de caja o banco con el que se registrarán los pagos de los RPHs ya liquidados."
    )
    file_rph = fields.Binary(
        string='Archivo de Recibos (.4ta / CSV)',
        required=True,
    )
    file_rph_filename = fields.Char(
        string='Nombre del Archivo de Recibos',
    )
    file_prestadores = fields.Binary(
        string='Archivo de Prestadores (.ps4 / CSV)',
        help="Opcional. Permite registrar o actualizar los nombres de los profesionales antes de procesar los recibos."
    )
    file_prestadores_filename = fields.Char(
        string='Nombre del Archivo de Prestadores',
    )

    def _find_ruc_type(self):
        """Busca el tipo de identificación RUC en la localización peruana."""
        id_type = self.env['l10n_latam.identification.type'].search([
            '|', ('l10n_pe_vat_code', '=', '6'),
            '|', ('code', '=', '6'),
            ('name', '=ilike', 'RUC')
        ], limit=1)
        if not id_type:
            id_type = self.env['l10n_latam.identification.type'].search([
                ('name', 'ilike', 'RUC')
            ], limit=1)
        return id_type

    def _find_dni_type(self):
        """Busca el tipo de identificación DNI en la localización peruana."""
        id_type = self.env['l10n_latam.identification.type'].search([
            '|', ('l10n_pe_vat_code', '=', '1'),
            '|', ('code', '=', '1'),
            ('name', '=ilike', 'DNI')
        ], limit=1)
        if not id_type:
            id_type = self.env['l10n_latam.identification.type'].search([
                ('name', 'ilike', 'DNI')
            ], limit=1)
        return id_type

    def _parse_file_content(self, file_data):
        """Decodifica y divide en líneas el contenido del archivo cargado."""
        try:
            content = base64.b64decode(file_data).decode('utf-8', errors='ignore')
        except Exception as e:
            raise UserError(f"Error al decodificar el archivo. Asegúrese de que sea texto plano codificado en UTF-8 o ANSI: {str(e)}")
        
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        return lines

    def _get_line_delimiter(self, line):
        """Detecta el delimitador de columnas en la línea de texto."""
        if '|' in line:
            return '|'
        elif ';' in line:
            return ';'
        elif ',' in line:
            return ','
        return '|'

    def action_import(self):
        self.ensure_one()
        created_partners_count = 0
        imported_rph_count = 0
        skipped_rph_count = 0

        # 1. Procesar primero los prestadores (Archivo .ps4) si se ha subido
        if self.file_prestadores:
            prestadores_lines = self._parse_file_content(self.file_prestadores)
            ruc_type = self._find_ruc_type()
            dni_type = self._find_dni_type()
            pe_country = self.env.ref('base.pe', raise_if_not_found=False)

            for line in prestadores_lines:
                delim = self._get_line_delimiter(line)
                cols = [c.strip() for c in line.split(delim)]
                if len(cols) < 5:
                    continue
                
                doc_type_code = cols[0]
                doc_number = cols[1]
                paterno = cols[2]
                materno = cols[3]
                nombres = cols[4]

                if not doc_number:
                    continue

                # Formatear el nombre completo
                name_parts = [paterno, materno, nombres]
                name_complete = " ".join([p for p in name_parts if p]).strip().upper()

                # Buscar partner por número de documento
                partner = self.env['res.partner'].search([('vat', '=', doc_number)], limit=1)
                
                # Asignar tipo de documento según el código de SUNAT
                id_type_id = False
                if doc_type_code == '06':
                    id_type_id = ruc_type.id if ruc_type else False
                elif doc_type_code == '01':
                    id_type_id = dni_type.id if dni_type else False

                if not partner:
                    partner_vals = {
                        'name': name_complete,
                        'vat': doc_number,
                        'l10n_latam_identification_type_id': id_type_id,
                        'country_id': pe_country.id if pe_country else False,
                        'supplier_rank': 1,
                    }
                    # Soporte opcional para campos de localización peruana en res.partner
                    if hasattr(self.env['res.partner'], 'last_name'):
                        partner_vals['last_name'] = paterno
                    if hasattr(self.env['res.partner'], 'second_last_name'):
                        partner_vals['second_last_name'] = materno
                    if hasattr(self.env['res.partner'], 'first_name'):
                        partner_vals['first_name'] = nombres

                    self.env['res.partner'].create([partner_vals])
                    created_partners_count += 1
                else:
                    # Si ya existe, podemos actualizar su nombre si está vacío o difiere
                    if name_complete and partner.name != name_complete:
                        partner.write({'name': name_complete})

        # 2. Procesar los recibos por honorarios (Archivo .4ta)
        rph_lines = self._parse_file_content(self.file_rph)
        ruc_type = self._find_ruc_type()
        dni_type = self._find_dni_type()
        pe_country = self.env.ref('base.pe', raise_if_not_found=False)

        # Buscar el tipo de comprobante "02" (Recibo por Honorarios) de SUNAT
        rph_doc_type = self.env['l10n_latam.document.type'].search([('code', '=', '02')], limit=1)
        if not rph_doc_type:
            raise UserError("No se encontró el tipo de documento de SUNAT '02' (Recibo por Honorarios) en Odoo. Por favor verifique la configuración de localización.")

        for line in rph_lines:
            delim = self._get_line_delimiter(line)
            cols = [c.strip() for c in line.split(delim)]
            if len(cols) < 7:
                continue

            doc_type_code = cols[0]
            doc_number = cols[1]
            op_type = cols[2]  # Usualmente 'R' para RPH
            serie = cols[3]
            numero = cols[4]
            monto_str = cols[5]
            fecha_emision_str = cols[6]
            
            # Fecha de pago es opcional
            fecha_pago_str = cols[7] if len(cols) > 7 else ''
            
            # Indicador de retención
            ind_retencion = cols[8] == '1' if len(cols) > 8 else False

            if not doc_number or not serie or not numero:
                continue

            # Convertir montos y fechas
            try:
                monto = float(monto_str)
            except ValueError:
                _logger.warning("Línea omitida por monto inválido: %s", line)
                continue

            try:
                fecha_emision = datetime.strptime(fecha_emision_str, '%d/%m/%Y').date()
            except ValueError:
                _logger.warning("Línea omitida por fecha de emisión inválida: %s", line)
                continue

            fecha_pago = False
            if fecha_pago_str:
                try:
                    fecha_pago = datetime.strptime(fecha_pago_str, '%d/%m/%Y').date()
                except ValueError:
                    _logger.warning("Fecha de pago inválida en línea: %s. Se procesará sin registrar pago automático.", line)

            # Buscar o crear profesional (partner)
            partner = self.env['res.partner'].search([('vat', '=', doc_number)], limit=1)
            if not partner:
                id_type_id = False
                if doc_type_code == '06':
                    id_type_id = ruc_type.id if ruc_type else False
                elif doc_type_code == '01':
                    id_type_id = dni_type.id if dni_type else False

                partner_vals = {
                    'name': f"PROFESIONAL RUC {doc_number}",
                    'vat': doc_number,
                    'l10n_latam_identification_type_id': id_type_id,
                    'country_id': pe_country.id if pe_country else False,
                    'supplier_rank': 1,
                }
                partner = self.env['res.partner'].create([partner_vals])
                created_partners_count += 1

            # Normalizar serie y número para la referencia
            # Formatear el número a 8 caracteres rellenos con ceros a la izquierda
            try:
                num_int = int(numero)
                numero_formatted = f"{num_int:08d}"
            except ValueError:
                numero_formatted = numero

            ref_name = f"{serie}-{numero_formatted}"

            # Verificar si ya existe este RPH para evitar duplicados
            existing_move = self.env['account.move'].search([
                ('partner_id', '=', partner.id),
                ('move_type', '=', 'in_invoice'),
                ('ref', '=', ref_name),
                ('company_id', '=', self.env.company.id),
            ], limit=1)

            if existing_move:
                # Si ya existe, lo saltamos para evitar duplicados o modificar contabilidad histórica
                skipped_rph_count += 1
                _logger.info("RPH ya registrado en Odoo. Omitiendo: %s - Ref: %s", partner.name, ref_name)
                continue

            # Construir impuestos si aplica retención
            tax_ids = []
            if ind_retencion and self.tax_id:
                tax_ids.append(self.tax_id.id)

            # Crear asiento contable (Factura de Proveedor)
            move_vals = {
                'move_type': 'in_invoice',
                'partner_id': partner.id,
                'invoice_date': fecha_emision,
                'l10n_latam_document_type_id': rph_doc_type.id,
                'ref': ref_name,
                'journal_id': self.journal_id.id,
                'invoice_line_ids': [(0, 0, {
                    'name': f"Servicios Profesionales - Recibo por Honorarios {ref_name}",
                    'account_id': self.expense_account_id.id,
                    'price_unit': monto,
                    'quantity': 1.0,
                    'tax_ids': [(6, 0, tax_ids)],
                })],
            }

            try:
                # Crear y publicar factura
                move = self.env['account.move'].create([move_vals])
                move.action_post()
                imported_rph_count += 1

                # 3. Registrar el pago si el archivo indica fecha de pago
                if fecha_pago and self.payment_journal_id:
                    # En Odoo 19, registrar el pago para una factura publicada se realiza mediante account.payment.register
                    register_vals = {
                        'payment_date': fecha_pago,
                        'journal_id': self.payment_journal_id.id,
                    }
                    payment_register = self.env['account.payment.register'].with_context(
                        active_model='account.move',
                        active_ids=move.ids,
                    ).create(register_vals)
                    payment_register.action_create_payments()

            except Exception as e:
                _logger.exception("Error al crear RPH para RUC %s, ref %s: %s", doc_number, ref_name, str(e))
                raise UserError(f"Error procesando la línea con RUC {doc_number} ({ref_name}): {str(e)}")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Carga Masiva de RPH Completada',
                'message': f"Importados: {imported_rph_count} recibos. Creados: {created_partners_count} profesionales. Duplicados omitidos: {skipped_rph_count}.",
                'type': 'success',
                'sticky': False,
            }
        }
