# -*- coding: utf-8 -*-

{
    'name': "PLAME Perú",
    'summary': "Planilla Mensual (PLAME) - SUNAT Perú",
    'description': "Módulo para la generación y gestión de la Planilla Mensual (PLAME) de SUNAT Perú (Recibos por Honorarios 4ta Categoría .4ta y .ps4).",
    'author': "StackPeru / Roberto Guerra",
    'website': 'bizpartner.biz',
    'license': "AGPL-3",
    'category': 'Human Resources/Payroll',
    'version': '19.0.1.0.0',
    'depends': [
        'account',
        'l10n_latam_invoice_document',
    ],


    'data': [
        'data/data.xml',
        'security/ir.model.access.csv',
        'views/plame_configuration.xml',
        'views/plame_dashboard_action.xml',
        'views/plame_reports_client_actions.xml',
        'views/report_plame_rph_views.xml',
        'wizard/wizard_import_rph_views.xml',
        'views/account_move_views.xml',
        'views/account_views.xml',

    ],
    'assets': {
        'web.assets_backend': [
            'l10n_pe_plame/static/src/css/plame_dashboard.css',
            'l10n_pe_plame/static/src/xml/plame_dashboard.xml',
            'l10n_pe_plame/static/src/js/plame_dashboard.js',
            'l10n_pe_plame/static/src/css/plame_report.css',
            'l10n_pe_plame/static/src/xml/plame_report.xml',
            'l10n_pe_plame/static/src/js/plame_report_base.js',
        ],
    },
}
