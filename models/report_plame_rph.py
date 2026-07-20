# -*- coding: utf-8 -*-

import io
import base64
import xlsxwriter
import dateutil.relativedelta
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError


class ReportPlameRph(models.Model):
    _name = 'report.plame.rph'
    _description = 'Libro de Honorarios y Declaración PLAME RPH'
    _inherit = ['report.plame.line.mixin']

    name = fields.Char(
        string='Nombre',
        default='/',
    )
    date_from = fields.Date(
        string='Fecha Desde',
        required=True,
    )
    date_to = fields.Date(
        string='Fecha Hasta',
        compute="_compute_date",
        store=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda',
        default=lambda self: self.env.company.currency_id,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        default=lambda self: self.env.company,
    )
    line_ids = fields.One2many(
        comodel_name='report.plame.rph.line',
        inverse_name='plame_id',
        string='Detalle del Reporte',
        readonly=True,
    )
    
    total_honorarios = fields.Float(
        string='Total Honorarios (Bruto)',
        compute='_compute_totals',
        store=True,
    )
    total_retenciones = fields.Float(
        string='Total Retenciones (8%)',
        compute='_compute_totals',
        store=True,
    )
    total_neto = fields.Float(
        string='Total Neto',
        compute='_compute_totals',
        store=True,
    )

    @api.depends("date_from")
    def _compute_date(self):
        for record in self:
            if record.date_from:
                fir_date = record.date_from.replace(day=1)
                d2 = fir_date + dateutil.relativedelta.relativedelta(months=1)
                last_day = d2 - dateutil.relativedelta.relativedelta(days=1)
                record.date_to = last_day
            else:
                record.date_to = False

    # Corrección para Odoo 19: dependencias de cálculo
    @api.depends('line_ids.amount_total', 'line_ids.amount_retention', 'line_ids.amount_net')
    def _compute_totals(self):
        for record in self:
            record.total_honorarios = sum(line.amount_total for line in record.line_ids)
            record.total_retenciones = sum(line.amount_retention for line in record.line_ids)
            record.total_neto = sum(line.amount_net for line in record.line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == '/':
                seq_name = self.env['ir.sequence'].next_by_code(self._name)
                if seq_name:
                    vals['name'] = seq_name
                else:
                    date_from_val = fields.Date.from_string(vals.get('date_from'))
                    if date_from_val:
                        vals['name'] = f"RPH-{date_from_val.year}{date_from_val.month:02d}-{self.env.company.id}"
                    else:
                        vals['name'] = f"RPH-NUEVO-{fields.Date.today()}"
        return super(ReportPlameRph, self).create(vals_list)

    def _get_move_payment_info(self, move):
        """Busca el pago asociado y retorna la fecha del pago y si fue liquidado."""
        payments = move._get_reconciled_payments()
        if not payments:
            return False, 'not_paid'
        
        # Tomar el último pago
        last_payment = max(payments, key=lambda p: p.date)
        
        # Estado de pago
        state = 'paid' if move.payment_state in ('paid', 'in_payment') else 'not_paid'
        return last_payment.date, state

    def generar(self):
        self.ensure_one()
        self.line_ids.unlink()

        # 1. Buscar RPHs emitidos en el periodo
        move_domain = [
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('l10n_latam_document_type_id.code', '=', '02'), # 02 = Recibo por Honorarios
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
        ]
        emitted_moves = self.env['account.move'].search(move_domain)

        # 2. Buscar RPHs pagados en el periodo pero emitidos antes
        # Buscamos pagos en el periodo
        payment_domain = [
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
        ]
        payments = self.env['account.payment'].search(payment_domain)
        
        # Obtener facturas conciliadas con estos pagos
        paid_moves_previous = self.env['account.move']
        for payment in payments:
            for move in payment.reconciled_invoice_ids:
                if (move.move_type == 'in_invoice' and 
                        move.l10n_latam_document_type_id.code == '02' and 
                        move.invoice_date < self.date_from):
                    paid_moves_previous |= move

        # Unión de movimientos
        all_moves = emitted_moves | paid_moves_previous

        lines_to_create = []
        for move in all_moves:
            # Obtener datos de pago
            payment_date, state_payment = self._get_move_payment_info(move)
            
            # Si el movimiento es de periodos anteriores pero no tiene pago en este periodo, no lo listamos aquí
            # (ya que paid_moves_previous se filtró por pagos en este periodo)
            if move in paid_moves_previous and not payment_date:
                continue

            # Calcular importes
            # Importe bruto es la suma de las líneas de gasto
            importe_bruto = sum(line.price_subtotal for line in move.invoice_line_ids)
            
            # Retención de 4ta (8%)
            importe_retencion = sum(
                abs(line.balance) for line in move.line_ids 
                if line.tax_line_id and (
                    line.tax_line_id.amount == -8.0 or 
                    '4ta' in line.tax_line_id.name.lower() or 
                    'retencion' in line.tax_line_id.name.lower()
                )
            )
            
            importe_neto = importe_bruto - importe_retencion

            line_vals = {
                'plame_id': self.id,
                'move_id': move.id,
                'ruc': move.partner_id.vat or '',
                'partner_name': move.partner_id.name or '',
                'document_number': move.ref or move.name,
                'date_invoice': move.invoice_date,
                'date_payment': payment_date,
                'amount_total': importe_bruto,
                'amount_retention': importe_retencion,
                'amount_net': importe_neto,
                'state_payment': state_payment,
            }
            lines_to_create.append((0, 0, line_vals))

        if lines_to_create:
            self.write({'line_ids': lines_to_create})
        
        return True

    def descargar_excel(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError('No existen líneas generadas en este reporte para exportar.')

        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = wb.add_worksheet('Libro de Honorarios')

        # Estilos excelwriter
        titulo_style = wb.add_format({
            'font_name': 'Calibri', 'font_size': 14, 'bold': True, 'align': 'center'
        })
        info_style = wb.add_format({
            'font_name': 'Calibri', 'font_size': 10, 'bold': True
        })
        cabecera_style = wb.add_format({
            'font_name': 'Calibri', 'font_color': '#FFFFFF', 'bg_color': '#394746',
            'bold': True, 'font_size': 10, 'align': 'center', 'valign': 'vcenter',
            'border': 1, 'text_wrap': True, 'border_color': '#D3D3D3',
        })
        data_style_left = wb.add_format({'font_name': 'Calibri', 'font_size': 10, 'border': 1, 'align': 'left'})
        data_style_center = wb.add_format({'font_name': 'Calibri', 'font_size': 10, 'border': 1, 'align': 'center'})
        data_style_num = wb.add_format({'font_name': 'Calibri', 'font_size': 10, 'border': 1, 'align': 'right', 'num_format': '#,##0.00'})
        date_style = wb.add_format({'font_name': 'Calibri', 'font_size': 10, 'border': 1, 'align': 'center', 'num_format': 'dd/mm/yyyy'})
        total_style = wb.add_format({
            'font_name': 'Calibri', 'font_size': 10, 'bold': True, 'border': 1, 'align': 'right', 'num_format': '#,##0.00', 'bg_color': '#EFEFEF'
        })
        total_label_style = wb.add_format({
            'font_name': 'Calibri', 'font_size': 10, 'bold': True, 'border': 1, 'align': 'right', 'bg_color': '#EFEFEF'
        })

        # Encabezado del reporte
        ws.merge_range('A1:L1', 'REPORTE LIBRO DE HONORARIOS (RPH)', titulo_style)
        ws.write('A3', 'EMPRESA:', info_style)
        ws.write('B3', self.company_id.name)
        ws.write('A4', 'RUC:', info_style)
        ws.write('B4', self.company_id.partner_id.vat or '')
        ws.write('A5', 'PERÍODO:', info_style)
        ws.write('B5', f"{self.date_from.strftime('%B %Y').upper()}")

        # Cabeceras de la tabla
        headers = [
            'N° Correlativo', 'F. Emisión', 'F. Pago', 'Tipo Doc.', 
            'RUC/DNI', 'Nombres y Apellidos', 'Serie', 'N° Recibo', 
            'Importe Bruto', 'Retención 4ta (8%)', 'Importe Neto', 'Estado'
        ]
        for col_idx, header in enumerate(headers):
            ws.write(6, col_idx, header, cabecera_style)

        # Ancho de columnas
        ws.set_column('A:A', 14) # Correlativo
        ws.set_column('B:C', 12) # Fechas
        ws.set_column('D:D', 10) # Tipo Doc
        ws.set_column('E:E', 15) # RUC
        ws.set_column('F:F', 35) # Nombre completo
        ws.set_column('G:G', 8)  # Serie
        ws.set_column('H:H', 12) # Número
        ws.set_column('I:K', 15) # Importes
        ws.set_column('L:L', 12) # Estado

        # Escribir registros
        row_idx = 7
        correlativo = 1
        for line in self.line_ids:
            ws.write(row_idx, 0, f"RPH-{correlativo:06d}", data_style_center)
            ws.write(row_idx, 1, line.date_invoice, date_style)
            
            if line.date_payment:
                ws.write(row_idx, 2, line.date_payment, date_style)
            else:
                ws.write(row_idx, 2, '-', data_style_center)

            ws.write(row_idx, 3, 'RUC' if len(line.ruc) == 11 else 'DNI', data_style_center)
            ws.write(row_idx, 4, line.ruc, data_style_center)
            ws.write(row_idx, 5, line.partner_name, data_style_left)
            
            # Separar Serie y Número
            ref_parts = line.document_number.split('-')
            serie = ref_parts[0] if len(ref_parts) > 0 else ''
            numero = ref_parts[1] if len(ref_parts) > 1 else line.document_number

            ws.write(row_idx, 6, serie, data_style_center)
            ws.write(row_idx, 7, numero, data_style_center)
            
            ws.write(row_idx, 8, line.amount_total, data_style_num)
            ws.write(row_idx, 9, line.amount_retention, data_style_num)
            ws.write(row_idx, 10, line.amount_net, data_style_num)
            
            state_label = 'PAGADO' if line.state_payment == 'paid' else 'PENDIENTE'
            ws.write(row_idx, 11, state_label, data_style_center)

            row_idx += 1
            correlativo += 1

        # Totales
        ws.merge_range(row_idx, 0, row_idx, 7, 'TOTALES:', total_label_style)
        ws.write(row_idx, 8, f"=SUM(I8:I{row_idx})", total_style)
        ws.write(row_idx, 9, f"=SUM(J8:J{row_idx})", total_style)
        ws.write(row_idx, 10, f"=SUM(K8:K{row_idx})", total_style)
        ws.write(row_idx, 11, '', total_label_style)

        wb.close()
        output.seek(0)
        data = output.read()

        if data:
            temporal_id = self.env['archivo.temporal'].create({
                'filecontent': base64.b64encode(data),
            })
            filename = f"LIBRO_DE_HONORARIOS_{self.date_from.year}_{self.date_from.month:02d}"
            return {
                'res_model': 'ir.actions.act_url',
                'type': 'ir.actions.act_url',
                'target': 'new',
                'url': (
                    'web/content/?model=archivo.temporal'
                    f'&id={temporal_id.id}'
                    f'&filename_field={filename}'
                    '&field=filecontent'
                    '&download=true'
                    f'&filename={filename}.xlsx'
                ),
            }
        else:
            raise UserError('Hubo un error en la generación del archivo Excel.')

    def descargar_txt_4ta(self):
        self.ensure_one()
        # Filtrar solo los recibos pagados en el periodo
        paid_lines = self.line_ids.filtered(
            lambda l: l.state_payment == 'paid' and 
            l.date_payment >= self.date_from and 
            l.date_payment <= self.date_to
        )

        if not paid_lines:
            raise UserError('No existen recibos por honorarios pagados dentro del periodo para declarar.')

        txt_lines = []
        for line in paid_lines:
            # 1. Tipo de documento prestador: 06 (RUC) si tiene 11 caracteres, de lo contrario 01 (DNI)
            doc_type_code = '06' if len(line.ruc) == 11 else '01'
            doc_number = line.ruc
            
            # 2. Tipo comprobante: siempre 'R' para Recibos por Honorarios
            comp_type = 'R'
            
            # 3. Serie y Número
            ref_parts = line.document_number.split('-')
            serie = ref_parts[0] if len(ref_parts) > 0 else 'E001'
            numero = ref_parts[1] if len(ref_parts) > 1 else line.document_number
            # Eliminar caracteres no numéricos del número si fuera necesario, o recortar
            try:
                num_int = int(numero)
                num_str = str(num_int)
            except ValueError:
                num_str = numero

            # 4. Importes
            monto_bruto = f"{line.amount_total:.2f}"
            if monto_bruto.endswith('.00'):
                monto_bruto = str(int(line.amount_total)) # Como en el ejemplo 6000 o 3181.8

            # 5. Fechas
            f_emision = line.date_invoice.strftime('%d/%m/%Y')
            f_pago = line.date_payment.strftime('%d/%m/%Y')

            # 6. Indicador de retención
            ind_ret = '1' if line.amount_retention > 0 else '0'

            # Construir la estructura de Martínez
            # TipoDoc(06)|RUC|TipoDocOperacion(R)|Serie|Numero|MontoBruto|FechaEmision|FechaPago|IndicadorRetencion(0/1)|||
            txt_line = f"{doc_type_code}|{doc_number}|{comp_type}|{serie}|{num_str}|{monto_bruto}|{f_emision}|{f_pago}|{ind_ret}|||"
            txt_lines.append(txt_line)

        # Unir líneas y convertir a bytes
        content_str = "\n".join(txt_lines) + "\n"
        data = content_str.encode('utf-8')

        # Nomenclatura SUNAT: 0601 + YYYYMM + RUC_EMPRESA + .4ta
        ruc_empresa = self.company_id.partner_id.vat or '00000000000'
        filename = f"0601{self.date_from.year}{self.date_from.month:02d}{ruc_empresa}.4ta"

        temporal_id = self.env['archivo.temporal'].create({
            'filecontent': base64.b64encode(data),
        })

        return {
            'res_model': 'ir.actions.act_url',
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': (
                'web/content/?model=archivo.temporal'
                f'&id={temporal_id.id}'
                f'&filename_field={filename}'
                '&field=filecontent'
                '&download=true'
                f'&filename={filename}'
            ),
        }

    def _get_separated_names(self, partner):
        """Separa el nombre completo en Apellido Paterno, Apellido Materno y Nombres."""
        if hasattr(partner, 'last_name') and partner.last_name:
            paterno = partner.last_name or ''
            materno = getattr(partner, 'second_last_name', '') or ''
            nombres = getattr(partner, 'first_name', '') or ''
            return paterno.upper(), materno.upper(), nombres.upper()
        
        # Split inteligente
        name = partner.name or ''
        parts = [p.strip() for p in name.split() if p.strip()]
        paterno = ''
        materno = ''
        nombres = ''
        
        if len(parts) >= 3:
            paterno = parts[0]
            materno = parts[1]
            nombres = ' '.join(parts[2:])
        elif len(parts) == 2:
            paterno = parts[0]
            nombres = parts[1]
        elif len(parts) == 1:
            nombres = parts[0]
            
        return paterno.upper(), materno.upper(), nombres.upper()

    def descargar_txt_ps4(self):
        self.ensure_one()
        # Filtrar los recibos pagados en el periodo
        paid_lines = self.line_ids.filtered(
            lambda l: l.state_payment == 'paid' and 
            l.date_payment >= self.date_from and 
            l.date_payment <= self.date_to
        )

        if not paid_lines:
            raise UserError('No existen recibos por honorarios pagados dentro del periodo para declarar.')

        # Agrupar prestadores únicos para evitar duplicados en el .ps4
        partners = paid_lines.mapped('move_id.partner_id')
        
        txt_lines = []
        for partner in partners:
            doc_type_code = '06' if len(partner.vat or '') == 11 else '01'
            doc_number = partner.vat or ''
            
            # Obtener nombres separados
            paterno, materno, nombres = self._get_separated_names(partner)
            
            # Indicador de domiciliado (1 = Domiciliado, 2 = No domiciliado)
            ind_domiciliado = '1' # RPH de proveedores locales son domiciliados
            
            # Convenio de doble imposición (0 = sin convenio)
            convenio = '0'

            # Estructura: TipoDoc(06)|RUC|ApePaterno|ApeMaterno|Nombres|IndicadorDomiciliado(1)|Convenio(0)|
            txt_line = f"{doc_type_code}|{doc_number}|{paterno}|{materno}|{nombres}|{ind_domiciliado}|{convenio}|"
            txt_lines.append(txt_line)

        # Unir líneas y convertir a bytes
        content_str = "\n".join(txt_lines) + "\n"
        data = content_str.encode('utf-8')

        # Nomenclatura SUNAT: 0601 + YYYYMM + RUC_EMPRESA + .ps4
        ruc_empresa = self.company_id.partner_id.vat or '00000000000'
        filename = f"0601{self.date_from.year}{self.date_from.month:02d}{ruc_empresa}.ps4"

        temporal_id = self.env['archivo.temporal'].create({
            'filecontent': base64.b64encode(data),
        })

        return {
            'res_model': 'ir.actions.act_url',
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': (
                'web/content/?model=archivo.temporal'
                f'&id={temporal_id.id}'
                f'&filename_field={filename}'
                '&field=filecontent'
                '&download=true'
                f'&filename={filename}'
            ),
        }


class ReportPlameRphLine(models.Model):
    _name = 'report.plame.rph.line'
    _description = 'Línea de Libro de Honorarios PLAME'
    _order = 'date_invoice asc, document_number asc'

    plame_id = fields.Many2one(
        comodel_name='report.plame.rph',
        string='Cabecera del reporte',
        required=True,
        ondelete='cascade',
    )
    move_id = fields.Many2one(
        comodel_name='account.move',
        string='Recibo por Honorarios',
        required=True,
        ondelete='cascade',
    )
    ruc = fields.Char(string='RUC/DNI')
    partner_name = fields.Char(string='Profesional')
    document_number = fields.Char(string='Número Comprobante')
    date_invoice = fields.Date(string='Fecha Emisión')
    date_payment = fields.Date(string='Fecha Pago')
    amount_total = fields.Float(string='Importe Bruto')
    amount_retention = fields.Float(string='Retención (8%)')
    amount_net = fields.Float(string='Importe Neto')
    state_payment = fields.Selection(selection=[
        ('paid', 'Pagado'),
        ('not_paid', 'Pendiente'),
    ], string='Estado Pago', default='not_paid')
