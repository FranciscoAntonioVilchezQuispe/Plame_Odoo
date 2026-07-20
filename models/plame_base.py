# -*- coding: utf-8 -*-

import logging
from datetime import date
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

MESES_ES = {
    1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
    5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
    9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre',
}

BOOKS_CONFIG = [
    {'type': 'RPH', 'model': 'report.plame.rph', 'name': 'Libro de Honorarios (RPH 4ta)', 'icon': 'fa-id-card-o', 'color': '#28a745'},
]


class ReportPlameLineMixin(models.AbstractModel):
    """Mixin que agrega conteo de líneas a los modelos de reporte PLAME."""
    _name = 'report.plame.line.mixin'
    _description = 'Mixin base para reportes PLAME'

    line_count = fields.Integer(
        string='Nro. Líneas',
        compute='_compute_line_count',
    )

    def _compute_line_count(self):
        for record in self:
            record.line_count = len(record.line_ids)

    def action_view_lines(self):
        """Abre la lista de líneas del reporte en ventana actual."""
        self.ensure_one()
        line_field = self._fields.get('line_ids')
        if not line_field:
            return
        return {
            'type': 'ir.actions.act_window',
            'name': 'Líneas generadas',
            'res_model': line_field.comodel_name,
            'view_mode': 'list',
            'domain': [('plame_id', '=', self.id)],
            'target': 'current',
        }

    @api.model
    def create_and_generate(self, date_from, extra_vals=None):
        """Crea (o actualiza) el reporte del período y lanza generar()."""
        try:
            domain = [
                ('date_from', '=', date_from),
                ('company_id', '=', self.env.company.id),
            ]
            existing = self.search(domain, limit=1)
            vals = dict(extra_vals or {})

            if existing:
                if vals:
                    existing.write(vals)
                existing.generar()
                return existing.id
            else:
                vals['date_from'] = date_from
                new_record = self.create([vals])
                new_record.generar()
                return new_record.id
        except Exception as e:
            _logger.exception(
                '[ERROR] [ReportPlameLineMixin] [create_and_generate] → modelo=%s fecha=%s | %s',
                self._name, date_from, str(e)
            )
            raise


class PlameDashboardMixin(models.AbstractModel):
    """Mixin con el método get_dashboard_data para el Dashboard PLAME OWL."""
    _name = 'plame.dashboard.mixin'
    _description = 'Mixin de Dashboard PLAME'

    @api.model
    def get_dashboard_data(self, year, month):
        """Retorna todos los datos necesarios para el Dashboard PLAME OWL."""
        company = self.env.company
        year = int(year)
        month = int(month)

        date_from = date(year, month, 1)

        result_books = []
        for book in BOOKS_CONFIG:
            try:
                record = self.env[book['model']].search([
                    ('date_from', '=', date_from),
                    ('company_id', '=', company.id),
                ], limit=1)

                if record:
                    result_books.append({
                        **book,
                        'generated': True,
                        'line_count': len(record.line_ids),
                        'record_id': record.id,
                        'record_name': record.name or '',
                        'total_honorarios': record.total_honorarios or 0.0,
                        'total_retenciones': record.total_retenciones or 0.0,
                        'total_neto': record.total_neto or 0.0,
                    })
                else:
                    result_books.append({
                        **book,
                        'generated': False,
                        'line_count': 0,
                        'record_id': False,
                        'record_name': '',
                        'total_honorarios': 0.0,
                        'total_retenciones': 0.0,
                        'total_neto': 0.0,
                    })
            except Exception as e:
                _logger.error('[ERROR] [PlameDashboard] [get_dashboard_data] → %s | %s', book['model'], str(e))
                result_books.append({
                    **book,
                    'generated': False,
                    'line_count': 0,
                    'record_id': False,
                    'record_name': '',
                    'total_honorarios': 0.0,
                    'total_retenciones': 0.0,
                    'total_neto': 0.0,
                })

        # Últimos 6 meses para el gráfico de Honorarios (Bruto vs Retención 4ta)
        chart_labels = []
        honorarios_totals = []
        retenciones_totals = []

        for i in range(5, -1, -1):
            d = date_from - relativedelta(months=i)
            d_first = date(d.year, d.month, 1)
            label = f"{MESES_ES.get(d.month, '')} {d.year}"
            chart_labels.append(label)

            rph_records = self.env['report.plame.rph'].search([
                ('date_from', '=', d_first),
                ('company_id', '=', company.id),
            ])
            h_total = sum(r.total_honorarios or 0.0 for r in rph_records)
            ret_total = sum(r.total_retenciones or 0.0 for r in rph_records)

            honorarios_totals.append(round(h_total, 2))
            retenciones_totals.append(round(ret_total, 2))

        generated_count = sum(1 for b in result_books if b['generated'])

        return {
            'period': f'{year:04d}{month:02d}',
            'period_label': f"{MESES_ES.get(month, '')} {year}",
            'company_name': company.name,
            'company_ruc': company.partner_id.vat or '',
            'books': result_books,
            'charts': {
                'labels': chart_labels,
                'honorarios': honorarios_totals,
                'retenciones': retenciones_totals,
            },
            'summary': {
                'total': len(BOOKS_CONFIG),
                'generated': generated_count,
                'pending': len(BOOKS_CONFIG) - generated_count,
            },
        }
