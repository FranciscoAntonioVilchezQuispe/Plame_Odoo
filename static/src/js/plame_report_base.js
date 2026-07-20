/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MONTHS_ES = [
    'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Setiembre', 'Octubre', 'Noviembre', 'Diciembre',
];

function getYearRange() {
    const current = new Date().getFullYear();
    const years = [];
    for (let y = current + 1; y >= current - 4; y--) years.push(y);
    return years;
}

const BOOKS_CONFIG = {
    'RPH': {
        model: 'report.plame.rph',
        lineModel: 'report.plame.rph.line',
        title: 'Libro de Honorarios — Recibos por Honorarios (4ta Categoría)',
        subtitle: 'PLAME 4ta Categoría (.4ta y .ps4)',
        excelTitle: 'FORMATO LIBRO DE HONORARIOS (4TA CATEGORÍA - PLAME SUNAT)',
        icon: 'fa-id-card-o',
        color: '#28a745',
        lineFields: ['id', 'partner_id', 'numero_doc', 'fecha_emision', 'fecha_pago', 'monto_bruto', 'monto_retencion', 'monto_neto'],
        columns: [
            { field: 'partner_id',     label: 'Prestador de Servicios', type: 'many2one' },
            { field: 'numero_doc',     label: 'N° Recibo',             type: 'char',    width: '130px' },
            { field: 'fecha_emision',  label: 'F. Emisión',            type: 'date',    width: '100px' },
            { field: 'fecha_pago',     label: 'F. Pago',               type: 'date',    width: '100px' },
            { field: 'monto_bruto',    label: 'Monto Bruto (S/)',      type: 'float',   width: '120px', align: 'right' },
            { field: 'monto_retencion',label: 'Retención 8% (S/)',     type: 'float',   width: '120px', align: 'right' },
            { field: 'monto_neto',     label: 'Neto a Pagar (S/)',     type: 'float',   width: '120px', align: 'right' },
        ],
    },
};
