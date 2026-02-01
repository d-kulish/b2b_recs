/**
 * Endpoints Dashboard Module
 *
 * Manages the Endpoints Dashboard chapter on the Deployment page.
 * Displays skeleton/placeholder UI for observability charts, tables, and KPIs.
 * No API integration - purely UI scaffolding for future features.
 *
 * Usage:
 *     EndpointsDashboard.init({
 *         containerId: '#endpointsDashboardChapter'
 *     });
 *     EndpointsDashboard.load();
 */

const EndpointsDashboard = (function() {
    'use strict';

    // =============================================================================
    // CONFIGURATION & STATE
    // =============================================================================

    const config = {
        containerId: '#endpointsDashboardChapter',
        kpiContainerId: '#dashboardKpiSummary',
        chartsContainerId: '#dashboardChartsGrid',
        tablesContainerId: '#dashboardTablesSection',
        prometheusContainerId: '#dashboardPrometheusSection',
        chartHeight: 220
    };

    let state = {
        initialized: false,
        charts: {}  // Store Chart.js instances for cleanup
    };

    // =============================================================================
    // CONSTANTS
    // =============================================================================

    const KPI_CONFIGS = [
        {
            id: 'totalRequests',
            icon: 'fa-chart-bar',
            iconClass: 'requests',
            label: 'Total Requests',
            skeletonValue: '--'
        },
        {
            id: 'avgLatency',
            icon: 'fa-clock',
            iconClass: 'latency',
            label: 'Avg Latency (P95)',
            skeletonValue: '--'
        },
        {
            id: 'errorRate',
            icon: 'fa-exclamation-circle',
            iconClass: 'errors',
            label: 'Error Rate',
            skeletonValue: '--'
        },
        {
            id: 'peakInstances',
            icon: 'fa-server',
            iconClass: 'instances',
            label: 'Peak Instances',
            skeletonValue: '--'
        }
    ];

    const CHART_CONFIGS = [
        {
            id: 'requestVolume',
            title: 'Request Volume Over Time',
            type: 'line',
            badge: '24h',
            options: {
                fill: true,
                stacked: true
            }
        },
        {
            id: 'latencyDistribution',
            title: 'Latency Distribution P50/P95/P99',
            type: 'line',
            badge: '24h',
            options: {
                datasets: 3
            }
        },
        {
            id: 'containerInstances',
            title: 'Container Instances Over Time',
            type: 'line',
            badge: '24h',
            options: {
                fill: true
            }
        },
        {
            id: 'errorRate',
            title: 'Error Rate Over Time',
            type: 'line',
            badge: '24h',
            options: {}
        },
        {
            id: 'coldStartLatency',
            title: 'Cold Start Latency',
            type: 'bar',
            badge: '7d',
            options: {
                indexAxis: 'y'
            }
        },
        {
            id: 'resourceUtilization',
            title: 'Resource Utilization CPU/Memory',
            type: 'line',
            badge: '24h',
            options: {
                dualYAxis: true
            }
        }
    ];

    const TABLE_CONFIGS = [
        {
            id: 'endpointPerformance',
            title: 'Endpoint Performance',
            columns: ['Endpoint', 'Requests', 'Avg', 'P95', 'Errors', 'Trend'],
            skeletonRows: 5
        },
        {
            id: 'peakUsagePeriods',
            title: 'Peak Usage Periods',
            columns: ['Time Period', 'Endpoint', 'Requests', 'Max Instances'],
            skeletonRows: 5
        }
    ];

    // =============================================================================
    // KPI RENDERING
    // =============================================================================

    function renderKPIs() {
        const container = document.querySelector(config.kpiContainerId);
        if (!container) return;

        container.innerHTML = KPI_CONFIGS.map(kpi => `
            <div class="dashboard-kpi-card" data-kpi="${kpi.id}">
                <div class="dashboard-kpi-icon ${kpi.iconClass}">
                    <i class="fas ${kpi.icon}"></i>
                </div>
                <div class="dashboard-kpi-content">
                    <div class="dashboard-kpi-value skeleton">${kpi.skeletonValue}</div>
                    <div class="dashboard-kpi-label">${kpi.label}</div>
                </div>
            </div>
        `).join('');
    }

    // =============================================================================
    // CHARTS RENDERING
    // =============================================================================

    function renderChartsGrid() {
        const container = document.querySelector(config.chartsContainerId);
        if (!container) return;

        container.innerHTML = CHART_CONFIGS.map(chart => `
            <div class="dashboard-chart-card" data-chart="${chart.id}">
                <div class="dashboard-chart-header">
                    <span class="dashboard-chart-title">${chart.title}</span>
                    <span class="dashboard-chart-badge">${chart.badge}</span>
                </div>
                <div class="dashboard-chart-container">
                    <canvas id="chart-${chart.id}"></canvas>
                </div>
            </div>
        `).join('');

        // Initialize skeleton charts after DOM is ready
        setTimeout(() => {
            CHART_CONFIGS.forEach(chartConfig => {
                createSkeletonChart(chartConfig);
            });
        }, 0);
    }

    function createSkeletonChart(chartConfig) {
        const canvas = document.getElementById(`chart-${chartConfig.id}`);
        if (!canvas) return;

        const ctx = canvas.getContext('2d');

        // Destroy existing chart if any
        if (state.charts[chartConfig.id]) {
            state.charts[chartConfig.id].destroy();
        }

        // Common options for skeleton appearance
        const skeletonColor = '#e5e7eb';
        const gridColor = '#f3f4f6';

        let chartOptions = {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    enabled: false
                }
            },
            scales: {
                x: {
                    display: true,
                    grid: {
                        color: gridColor,
                        drawBorder: false
                    },
                    ticks: {
                        display: false
                    }
                },
                y: {
                    display: true,
                    grid: {
                        color: gridColor,
                        drawBorder: false
                    },
                    ticks: {
                        display: false
                    },
                    beginAtZero: true
                }
            }
        };

        let datasets = [];
        const emptyData = Array(12).fill(null);

        // Configure based on chart type
        if (chartConfig.type === 'bar' && chartConfig.options.indexAxis === 'y') {
            // Horizontal bar chart
            chartOptions.indexAxis = 'y';
            chartOptions.scales.x.display = true;
            chartOptions.scales.y.display = true;
            datasets = [{
                data: Array(5).fill(null),
                backgroundColor: skeletonColor,
                borderWidth: 0,
                barThickness: 20
            }];
        } else if (chartConfig.options.datasets === 3) {
            // Multiple line series (P50/P95/P99)
            datasets = [
                { data: emptyData, borderColor: '#d1d5db', borderWidth: 1, pointRadius: 0, tension: 0.3 },
                { data: emptyData, borderColor: '#e5e7eb', borderWidth: 1, pointRadius: 0, tension: 0.3 },
                { data: emptyData, borderColor: '#f3f4f6', borderWidth: 1, pointRadius: 0, tension: 0.3 }
            ];
        } else if (chartConfig.options.dualYAxis) {
            // Dual Y-axis chart
            chartOptions.scales.y1 = {
                display: true,
                position: 'right',
                grid: {
                    display: false
                },
                ticks: {
                    display: false
                }
            };
            datasets = [
                { data: emptyData, borderColor: '#d1d5db', borderWidth: 1, pointRadius: 0, tension: 0.3, yAxisID: 'y' },
                { data: emptyData, borderColor: '#e5e7eb', borderWidth: 1, pointRadius: 0, tension: 0.3, yAxisID: 'y1' }
            ];
        } else if (chartConfig.options.fill || chartConfig.options.stacked) {
            // Filled/stacked area chart
            datasets = [{
                data: emptyData,
                borderColor: skeletonColor,
                backgroundColor: 'rgba(229, 231, 235, 0.3)',
                borderWidth: 1,
                fill: true,
                pointRadius: 0,
                tension: 0.3
            }];
        } else {
            // Default line chart
            datasets = [{
                data: emptyData,
                borderColor: skeletonColor,
                borderWidth: 1,
                pointRadius: 0,
                tension: 0.3
            }];
        }

        // Create the chart
        state.charts[chartConfig.id] = new Chart(ctx, {
            type: chartConfig.type,
            data: {
                labels: chartConfig.type === 'bar' ? ['', '', '', '', ''] : Array(12).fill(''),
                datasets: datasets
            },
            options: chartOptions
        });
    }

    function destroyCharts() {
        Object.values(state.charts).forEach(chart => {
            if (chart && typeof chart.destroy === 'function') {
                chart.destroy();
            }
        });
        state.charts = {};
    }

    // =============================================================================
    // TABLES RENDERING
    // =============================================================================

    function renderTables() {
        const container = document.querySelector(config.tablesContainerId);
        if (!container) return;

        container.innerHTML = TABLE_CONFIGS.map(table => `
            <div class="dashboard-table-card" data-table="${table.id}">
                <div class="dashboard-table-header">
                    <span class="dashboard-table-title">${table.title}</span>
                </div>
                <table class="dashboard-table">
                    <thead>
                        <tr>
                            ${table.columns.map(col => `<th>${col}</th>`).join('')}
                        </tr>
                    </thead>
                    <tbody>
                        ${renderSkeletonRows(table)}
                    </tbody>
                </table>
            </div>
        `).join('');
    }

    function renderSkeletonRows(tableConfig) {
        const rows = [];
        for (let i = 0; i < tableConfig.skeletonRows; i++) {
            const cells = tableConfig.columns.map((col, idx) => {
                // Vary skeleton widths for visual interest
                let widthClass = '';
                if (col === 'Trend') {
                    return '<td><div class="dashboard-trend-placeholder"></div></td>';
                } else if (idx === 0) {
                    widthClass = 'long';
                } else if (col === 'Avg' || col === 'P95' || col === 'Errors') {
                    widthClass = 'short';
                }
                return `<td><div class="dashboard-skeleton dashboard-skeleton-text ${widthClass}"></div></td>`;
            });
            rows.push(`<tr>${cells.join('')}</tr>`);
        }
        return rows.join('');
    }

    // =============================================================================
    // PROMETHEUS SECTION
    // =============================================================================

    function renderPrometheusSection() {
        const container = document.querySelector(config.prometheusContainerId);
        if (!container) return;

        container.innerHTML = `
            <div class="dashboard-prometheus-card">
                <div class="dashboard-prometheus-content">
                    <div class="dashboard-prometheus-icon">
                        <i class="fas fa-fire"></i>
                    </div>
                    <div class="dashboard-prometheus-info">
                        <div class="dashboard-prometheus-title">
                            <h4>Prometheus Integration</h4>
                            <span class="dashboard-coming-soon-badge">Coming Soon</span>
                        </div>
                        <p class="dashboard-prometheus-desc">
                            Connect to Prometheus for advanced metrics, alerting, and custom dashboards.
                        </p>
                    </div>
                </div>
                <button class="dashboard-prometheus-btn" disabled>
                    <i class="fas fa-cog"></i>
                    Configure
                </button>
            </div>
        `;
    }

    // =============================================================================
    // PUBLIC API
    // =============================================================================

    function init(options = {}) {
        // Merge options with defaults
        if (options.containerId) config.containerId = options.containerId;
        if (options.kpiContainerId) config.kpiContainerId = options.kpiContainerId;
        if (options.chartsContainerId) config.chartsContainerId = options.chartsContainerId;
        if (options.tablesContainerId) config.tablesContainerId = options.tablesContainerId;
        if (options.prometheusContainerId) config.prometheusContainerId = options.prometheusContainerId;
        if (options.chartHeight) config.chartHeight = options.chartHeight;

        state.initialized = true;
        return EndpointsDashboard;
    }

    function load() {
        if (!state.initialized) {
            init();
        }

        // Render all sections
        renderKPIs();
        renderChartsGrid();
        renderTables();
        renderPrometheusSection();
    }

    function refresh() {
        // Placeholder for future API integration
        // For now, just re-render the skeleton UI
        destroyCharts();
        load();
    }

    // Expose public API
    return {
        init,
        load,
        refresh
    };

})();
