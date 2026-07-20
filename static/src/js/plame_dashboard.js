/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";

class PleDashboard extends Component {
    static template = "l10n_pe_plame.PleDashboard";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");

        const hoy = new Date();
        this.state = useState({
            loading: true,
            data: null,
            error: null,
            year: hoy.getFullYear(),
            month: hoy.getMonth() + 1,
        });

        this.chartRef = useRef("honorariosChart");
        this._chart = null;

        onWillStart(async () => {
            await loadJS("/web/static/lib/Chart/Chart.js");
            await this._loadData();
        });

        onMounted(() => {
            if (this.state.data && !this.state.loading) {
                this._renderChart();
            }
        });
    }

    async _loadData() {
        this.state.loading = true;
        this.state.error = null;
        try {
            const result = await this.orm.call(
                "plame.configuration",
                "get_dashboard_data",
                [],
                { year: this.state.year, month: this.state.month }
            );
            this.state.data = result;
        } catch {
            this.state.error = "Error al cargar los datos del Dashboard PLAME.";
            this.notification.add("Error al cargar el Dashboard PLAME", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    _renderChart() {
        const canvas = this.chartRef.el;
        if (!canvas || !this.state.data || globalThis.Chart === undefined) return;

        if (this._chart) {
            this._chart.destroy();
            this._chart = null;
        }

        const { labels, honorarios, retenciones } = this.state.data.charts;
        this._chart = new globalThis.Chart(canvas.getContext("2d"), {
            type: "bar",
            data: {
                labels,
                datasets: [
                    {
                        label: "Total Honorarios Bruto (S/)",
                        data: honorarios,
                        backgroundColor: "rgba(40, 167, 69, 0.75)",
                        borderColor: "rgba(40, 167, 69, 1)",
                        borderWidth: 1,
                        borderRadius: 4,
                    },
                    {
                        label: "Retención 4ta Categoría 8% (S/)",
                        data: retenciones,
                        backgroundColor: "rgba(255, 193, 7, 0.75)",
                        borderColor: "rgba(255, 193, 7, 1)",
                        borderWidth: 1,
                        borderRadius: 4,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: "top" },
                    title: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) =>
                                `${ctx.dataset.label}: S/ ${ctx.parsed.y.toLocaleString("es-PE", { minimumFractionDigits: 2 })}`,
                        },
                    },
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: (v) => "S/ " + v.toLocaleString("es-PE"),
                        },
                        grid: { color: "rgba(0,0,0,0.05)" },
                    },
                    x: {
                        grid: { display: false },
                    },
                },
            },
        });
    }

    get months() {
        return [
            { value: 1, label: "Enero" }, { value: 2, label: "Febrero" },
            { value: 3, label: "Marzo" }, { value: 4, label: "Abril" },
            { value: 5, label: "Mayo" }, { value: 6, label: "Junio" },
            { value: 7, label: "Julio" }, { value: 8, label: "Agosto" },
            { value: 9, label: "Septiembre" }, { value: 10, label: "Octubre" },
            { value: 11, label: "Noviembre" }, { value: 12, label: "Diciembre" },
        ];
    }

    get years() {
        const y = new Date().getFullYear();
        return [y - 2, y - 1, y, y + 1];
    }

    async onChangeYear(ev) {
        this.state.year = Number.parseInt(ev.target.value);
        await this._loadData();
        this._renderChart();
    }

    async onChangeMonth(ev) {
        this.state.month = Number.parseInt(ev.target.value);
        await this._loadData();
        this._renderChart();
    }

    async onRefresh() {
        await this._loadData();
        this._renderChart();
    }

    openRphReport() {
        this.actionService.doAction("l10n_pe_plame.action_report_plame_rph");
    }

    openRphImport() {
        this.actionService.doAction("l10n_pe_plame.action_wizard_import_rph");
    }

    openConfig() {
        this.actionService.doAction("l10n_pe_plame.sunat_plame_configuration_action");
    }
}

registry.category("actions").add("plame_dashboard_action", PleDashboard);
