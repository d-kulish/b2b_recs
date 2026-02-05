/**
 * Model Dashboard Endpoints Module
 *
 * Manages the Endpoints chapter on the Model Dashboard page.
 * Displays grouped summary card, KPIs, charts, and tables for endpoint observability.
 *
 * Data Sources:
 * - Serving Endpoints KPIs (Total/Active/Inactive): Real data from /api/deployed-endpoints/
 * - Performance KPIs, Charts, Tables: Demo data for sales demonstrations (APIs not yet implemented)
 *
 * Usage:
 *     ModelDashboardEndpoints.init({
 *         containerId: '#endpointsChapter'
 *     });
 *     ModelDashboardEndpoints.load();
 */

const ModelDashboardEndpoints = (function() {
    'use strict';

    // =============================================================================
    // CONFIGURATION & STATE
    // =============================================================================

    // Demo mode only affects charts and tables (no APIs exist yet)
    // KPIs always use real data from the deployed-endpoints API
    const DEMO_MODE_CHARTS = true;
    const DEMO_DATA_URL = '/static/data/demo/model_dashboard_endpoints.json';

    const config = {
        containerId: '#endpointsChapter',
        kpiContainerId: '#endpointsKpiRow',
        chartsContainerId: '#endpointsChartsGrid',
        tablesContainerId: '#endpointsTablesSection',
        chartHeight: 220,
        // API endpoint for real KPI data (same as EndpointsTable uses)
        endpointsApiUrl: '/api/deployed-endpoints/'
    };

    let state = {
        initialized: false,
        charts: {},
        demoData: null
    };

    // Endpoint colors matching the demo data
    const ENDPOINT_COLORS = [
        { primary: '#3b82f6', light: 'rgba(59, 130, 246, 0.2)', name: 'blue' },
        { primary: '#10b981', light: 'rgba(16, 185, 129, 0.2)', name: 'green' },
        { primary: '#8b5cf6', light: 'rgba(139, 92, 246, 0.2)', name: 'purple' }
    ];

    // =============================================================================
    // CONSTANTS
    // =============================================================================

    const KPI_CONFIGS = [
        {
            id: 'totalRequests',
            icon: 'fa-chart-bar',
            iconClass: 'requests',
            label: 'Requests (7D)',
            skeletonValue: '--'
        },
        {
            id: 'avgLatency',
            icon: 'fa-clock',
            iconClass: 'latency',
            label: 'Latency (P95)',
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
            label: 'Instances',
            skeletonValue: '--'
        }
    ];

    const CHART_CONFIGS = [
        {
            id: 'requestVolume',
            title: 'Request Volume Over Time',
            type: 'line',
            badge: '7d',
            options: {
                fill: true,
                stacked: true
            }
        },
        {
            id: 'latencyDistribution',
            title: 'Latency Distribution P50/P95/P99',
            type: 'line',
            badge: '7d',
            options: {
                datasets: 3
            }
        },
        {
            id: 'containerInstances',
            title: 'Container Instances Over Time',
            type: 'line',
            badge: '7d',
            options: {
                fill: true
            }
        },
        {
            id: 'errorRate',
            title: 'Error Rate Over Time',
            type: 'line',
            badge: '7d',
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
            badge: '7d',
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
    // DATA LOADING
    // =============================================================================

    /**
     * Fetch real KPI data from the deployed-endpoints API.
     * Returns endpoints_summary with total, active, inactive counts.
     */
    async function fetchEndpointsKpi() {
        try {
            const response = await fetch(config.endpointsApiUrl);
            if (!response.ok) throw new Error('Failed to fetch endpoints data');
            const data = await response.json();

            if (data.success && data.kpi) {
                // Map API response to expected endpoints_summary structure
                return {
                    total: data.kpi.total || 0,
                    active: data.kpi.active || 0,
                    inactive: data.kpi.inactive || 0
                };
            }
            return null;
        } catch (error) {
            console.error('Failed to fetch endpoints KPI:', error);
            return null;
        }
    }

    /**
     * Load demo data for charts and tables (no real APIs exist yet).
     */
    async function loadDemoData() {
        if (state.demoData) return state.demoData;

        try {
            const response = await fetch(DEMO_DATA_URL);
            if (!response.ok) throw new Error('Failed to load demo data');
            state.demoData = await response.json();
            return state.demoData;
        } catch (error) {
            console.error('Demo data load failed:', error);
            return null;
        }
    }

    // =============================================================================
    // UTILITY FUNCTIONS
    // =============================================================================

    function formatNumber(num) {
        if (num >= 1000000) {
            return (num / 1000000).toFixed(1) + 'M';
        } else if (num >= 1000) {
            return (num / 1000).toFixed(1) + 'K';
        }
        return num.toLocaleString();
    }

    // =============================================================================
    // KPI RENDERING (Grouped Summary + 4 Performance Cards)
    // =============================================================================

    function renderKPIsWithData(data) {
        const container = document.querySelector(config.kpiContainerId);
        if (!container) return;

        const summary = data.endpoints_summary;
        const kpi = data.kpi_summary;

        // Build the grouped summary card HTML with title on top, icon + stats in a row
        const summaryCardHtml = `
            <div class="model-dashboard-summary-card">
                <div class="model-dashboard-summary-title">Serving Endpoints</div>
                <div class="model-dashboard-summary-row">
                    <div class="model-dashboard-summary-icon">
                        <i class="fas fa-rocket"></i>
                    </div>
                    <div class="model-dashboard-summary-stats">
                        <div class="model-dashboard-summary-stat">
                            <div class="model-dashboard-summary-value">${summary.total}</div>
                            <div class="model-dashboard-summary-label">Total</div>
                        </div>
                        <div class="model-dashboard-summary-stat">
                            <div class="model-dashboard-summary-value active">${summary.active}</div>
                            <div class="model-dashboard-summary-label">Active</div>
                        </div>
                        <div class="model-dashboard-summary-stat">
                            <div class="model-dashboard-summary-value inactive">${summary.inactive}</div>
                            <div class="model-dashboard-summary-label">Inactive</div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Build the 4 performance KPI cards in a 2x2 grid
        const kpiData = [
            {
                id: 'totalRequests',
                icon: 'fa-chart-bar',
                iconClass: 'requests',
                label: 'Requests (7D)',
                value: formatNumber(kpi.total_requests),
                change: `${kpi.total_requests_change_pct > 0 ? '+' : ''}${kpi.total_requests_change_pct}%`,
                changeClass: kpi.total_requests_change_pct >= 0 ? 'positive' : 'negative'
            },
            {
                id: 'avgLatency',
                icon: 'fa-clock',
                iconClass: 'latency',
                label: 'Latency (P95)',
                value: `${kpi.avg_latency_p95_ms}ms`,
                change: `${kpi.avg_latency_change_ms > 0 ? '+' : ''}${kpi.avg_latency_change_ms}ms`,
                changeClass: kpi.avg_latency_change_ms <= 0 ? 'positive' : 'negative'
            },
            {
                id: 'errorRate',
                icon: 'fa-exclamation-circle',
                iconClass: 'errors',
                label: 'Error Rate',
                value: `${kpi.error_rate_pct}%`,
                change: kpi.error_rate_trend,
                changeClass: 'neutral'
            },
            {
                id: 'peakInstances',
                icon: 'fa-server',
                iconClass: 'instances',
                label: 'Peak / Avg',
                value: `${kpi.peak_instances}`,
                change: `avg ${kpi.avg_instances}`,
                changeClass: 'neutral'
            }
        ];

        const kpiCardsHtml = kpiData.map(item => `
            <div class="model-dashboard-kpi-card" data-kpi="${item.id}">
                <div class="model-dashboard-kpi-icon ${item.iconClass}">
                    <i class="fas ${item.icon}"></i>
                </div>
                <div class="model-dashboard-kpi-content">
                    <div class="model-dashboard-kpi-value">${item.value}</div>
                    <div class="model-dashboard-kpi-label">${item.label}</div>
                    <div class="model-dashboard-kpi-change ${item.changeClass}">${item.change}</div>
                </div>
            </div>
        `).join('');

        // Wrap performance KPIs in a 2x2 grid container
        container.innerHTML = summaryCardHtml + `<div class="model-dashboard-performance-grid">${kpiCardsHtml}</div>`;
    }

    function renderSkeletonKPIs() {
        const container = document.querySelector(config.kpiContainerId);
        if (!container) return;

        // Skeleton summary card with title on top, icon + stats in a row
        const summaryCardHtml = `
            <div class="model-dashboard-summary-card">
                <div class="model-dashboard-summary-title">Serving Endpoints</div>
                <div class="model-dashboard-summary-row">
                    <div class="model-dashboard-summary-icon">
                        <i class="fas fa-rocket"></i>
                    </div>
                    <div class="model-dashboard-summary-stats">
                        <div class="model-dashboard-summary-stat">
                            <div class="model-dashboard-summary-value">--</div>
                            <div class="model-dashboard-summary-label">Total</div>
                        </div>
                        <div class="model-dashboard-summary-stat">
                            <div class="model-dashboard-summary-value active">--</div>
                            <div class="model-dashboard-summary-label">Active</div>
                        </div>
                        <div class="model-dashboard-summary-stat">
                            <div class="model-dashboard-summary-value inactive">--</div>
                            <div class="model-dashboard-summary-label">Inactive</div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        const kpiCardsHtml = KPI_CONFIGS.map(kpi => `
            <div class="model-dashboard-kpi-card" data-kpi="${kpi.id}">
                <div class="model-dashboard-kpi-icon ${kpi.iconClass}">
                    <i class="fas ${kpi.icon}"></i>
                </div>
                <div class="model-dashboard-kpi-content">
                    <div class="model-dashboard-kpi-value skeleton">${kpi.skeletonValue}</div>
                    <div class="model-dashboard-kpi-label">${kpi.label}</div>
                </div>
            </div>
        `).join('');

        // Wrap performance KPIs in a 2x2 grid container
        container.innerHTML = summaryCardHtml + `<div class="model-dashboard-performance-grid">${kpiCardsHtml}</div>`;
    }

    // =============================================================================
    // CHARTS RENDERING
    // =============================================================================

    function renderChartsWithData(data) {
        const container = document.querySelector(config.chartsContainerId);
        if (!container) return;

        container.innerHTML = CHART_CONFIGS.map(chart => `
            <div class="model-dashboard-chart-card" data-chart="${chart.id}">
                <div class="model-dashboard-chart-header">
                    <span class="model-dashboard-chart-title">${chart.title}</span>
                    <span class="model-dashboard-chart-badge">${chart.badge}</span>
                </div>
                <div class="model-dashboard-chart-container">
                    <canvas id="md-chart-${chart.id}"></canvas>
                </div>
            </div>
        `).join('');

        // Initialize charts with demo data after DOM is ready
        setTimeout(() => {
            createRequestVolumeChart(data);
            createLatencyDistributionChart(data);
            createContainerInstancesChart(data);
            createErrorRateChart(data);
            createColdStartLatencyChart(data);
            createResourceUtilizationChart(data);
        }, 0);
    }

    function renderSkeletonCharts() {
        const container = document.querySelector(config.chartsContainerId);
        if (!container) return;

        container.innerHTML = CHART_CONFIGS.map(chart => `
            <div class="model-dashboard-chart-card" data-chart="${chart.id}">
                <div class="model-dashboard-chart-header">
                    <span class="model-dashboard-chart-title">${chart.title}</span>
                    <span class="model-dashboard-chart-badge">${chart.badge}</span>
                </div>
                <div class="model-dashboard-chart-container">
                    <canvas id="md-chart-${chart.id}"></canvas>
                </div>
            </div>
        `).join('');

        // Initialize skeleton charts
        setTimeout(() => {
            CHART_CONFIGS.forEach(chartConfig => {
                createSkeletonChart(chartConfig);
            });
        }, 0);
    }

    function createSkeletonChart(chartConfig) {
        const canvas = document.getElementById(`md-chart-${chartConfig.id}`);
        if (!canvas) return;

        const ctx = canvas.getContext('2d');

        if (state.charts[chartConfig.id]) {
            state.charts[chartConfig.id].destroy();
        }

        const skeletonColor = '#e5e7eb';
        const gridColor = '#f3f4f6';

        let chartOptions = {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: {
                legend: { display: false },
                tooltip: { enabled: false }
            },
            scales: {
                x: {
                    display: true,
                    grid: { color: gridColor, drawBorder: false },
                    ticks: { display: false }
                },
                y: {
                    display: true,
                    grid: { color: gridColor, drawBorder: false },
                    ticks: { display: false },
                    beginAtZero: true
                }
            }
        };

        let datasets = [];
        const emptyData = Array(12).fill(null);

        if (chartConfig.type === 'bar' && chartConfig.options.indexAxis === 'y') {
            chartOptions.indexAxis = 'y';
            datasets = [{
                data: Array(5).fill(null),
                backgroundColor: skeletonColor,
                borderWidth: 0,
                barThickness: 20
            }];
        } else {
            datasets = [{
                data: emptyData,
                borderColor: skeletonColor,
                backgroundColor: 'rgba(229, 231, 235, 0.3)',
                borderWidth: 1,
                fill: true,
                pointRadius: 0,
                tension: 0.3
            }];
        }

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
    // CHART CREATION WITH DATA
    // =============================================================================

    function getCommonChartOptions(showLegend = false) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 400 },
            plugins: {
                legend: {
                    display: showLegend,
                    position: 'top',
                    labels: {
                        boxWidth: 12,
                        padding: 15,
                        font: { size: 11 }
                    }
                },
                tooltip: {
                    enabled: true,
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleFont: { size: 12 },
                    bodyFont: { size: 11 },
                    padding: 10,
                    cornerRadius: 4
                }
            },
            scales: {
                x: {
                    display: true,
                    grid: { color: '#f3f4f6', drawBorder: false },
                    ticks: {
                        font: { size: 10 },
                        color: '#6b7280',
                        maxRotation: 45,
                        minRotation: 0,
                        autoSkip: true,
                        maxTicksLimit: 8
                    }
                },
                y: {
                    display: true,
                    grid: { color: '#f3f4f6', drawBorder: false },
                    ticks: {
                        font: { size: 10 },
                        color: '#6b7280'
                    },
                    beginAtZero: true
                }
            }
        };
    }

    function createRequestVolumeChart(data) {
        const canvas = document.getElementById('md-chart-requestVolume');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const chartData = data.request_volume;

        if (state.charts.requestVolume) {
            state.charts.requestVolume.destroy();
        }

        const datasets = chartData.endpoints.map((endpoint, idx) => ({
            label: endpoint.name,
            data: endpoint.values,
            backgroundColor: ENDPOINT_COLORS[idx].light,
            borderColor: ENDPOINT_COLORS[idx].primary,
            borderWidth: 1.5,
            fill: true,
            tension: 0.3,
            pointRadius: 0,
            pointHoverRadius: 4
        }));

        const options = getCommonChartOptions(true);
        options.scales.y.stacked = true;
        options.scales.x.stacked = true;
        options.scales.y.ticks.callback = (value) => formatNumber(value);

        state.charts.requestVolume = new Chart(ctx, {
            type: 'line',
            data: {
                labels: chartData.labels,
                datasets: datasets
            },
            options: options
        });
    }

    function createLatencyDistributionChart(data) {
        const canvas = document.getElementById('md-chart-latencyDistribution');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const chartData = data.latency_distribution;

        if (state.charts.latencyDistribution) {
            state.charts.latencyDistribution.destroy();
        }

        const options = getCommonChartOptions(true);
        options.scales.y.ticks.callback = (value) => `${value}ms`;

        state.charts.latencyDistribution = new Chart(ctx, {
            type: 'line',
            data: {
                labels: chartData.labels,
                datasets: [
                    {
                        label: 'P50',
                        data: chartData.p50,
                        borderColor: '#10b981',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        tension: 0.3,
                        pointRadius: 0,
                        pointHoverRadius: 4
                    },
                    {
                        label: 'P95',
                        data: chartData.p95,
                        borderColor: '#f59e0b',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        borderDash: [5, 5],
                        tension: 0.3,
                        pointRadius: 0,
                        pointHoverRadius: 4
                    },
                    {
                        label: 'P99',
                        data: chartData.p99,
                        borderColor: '#ef4444',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        borderDash: [2, 2],
                        tension: 0.3,
                        pointRadius: 0,
                        pointHoverRadius: 4
                    }
                ]
            },
            options: options
        });
    }

    function createContainerInstancesChart(data) {
        const canvas = document.getElementById('md-chart-containerInstances');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const chartData = data.container_instances;

        if (state.charts.containerInstances) {
            state.charts.containerInstances.destroy();
        }

        const datasets = chartData.endpoints.map((endpoint, idx) => ({
            label: endpoint.name,
            data: endpoint.values,
            backgroundColor: ENDPOINT_COLORS[idx].light,
            borderColor: ENDPOINT_COLORS[idx].primary,
            borderWidth: 1.5,
            fill: true,
            tension: 0.3,
            pointRadius: 0,
            pointHoverRadius: 4
        }));

        const options = getCommonChartOptions(true);
        options.scales.y.stacked = true;
        options.scales.x.stacked = true;

        state.charts.containerInstances = new Chart(ctx, {
            type: 'line',
            data: {
                labels: chartData.labels,
                datasets: datasets
            },
            options: options
        });
    }

    function createErrorRateChart(data) {
        const canvas = document.getElementById('md-chart-errorRate');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const chartData = data.error_rate;

        if (state.charts.errorRate) {
            state.charts.errorRate.destroy();
        }

        const options = getCommonChartOptions(false);
        options.scales.y.ticks.callback = (value) => `${value}%`;

        state.charts.errorRate = new Chart(ctx, {
            type: 'line',
            data: {
                labels: chartData.labels,
                datasets: [{
                    label: 'Error Rate',
                    data: chartData.values,
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.3,
                    pointRadius: chartData.values.map(v => v > 1 ? 6 : 0),
                    pointBackgroundColor: chartData.values.map(v => v > 1 ? '#ef4444' : 'transparent'),
                    pointBorderColor: chartData.values.map(v => v > 1 ? '#fff' : 'transparent'),
                    pointBorderWidth: 2,
                    pointHoverRadius: 6
                }]
            },
            options: options
        });
    }

    function createColdStartLatencyChart(data) {
        const canvas = document.getElementById('md-chart-coldStartLatency');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const chartData = data.cold_start_latency;

        if (state.charts.coldStartLatency) {
            state.charts.coldStartLatency.destroy();
        }

        const labels = chartData.endpoints.map(ep => ep.name);
        const p50Data = chartData.endpoints.map(ep => ep.p50);
        const p95Data = chartData.endpoints.map(ep => ep.p95);

        const options = getCommonChartOptions(true);
        options.indexAxis = 'y';
        options.scales.x.ticks.callback = (value) => `${(value / 1000).toFixed(1)}s`;
        options.scales.y.ticks.font = { size: 11 };

        state.charts.coldStartLatency = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'P50',
                        data: p50Data,
                        backgroundColor: 'rgba(59, 130, 246, 0.7)',
                        borderColor: '#3b82f6',
                        borderWidth: 1,
                        barThickness: 16
                    },
                    {
                        label: 'P95',
                        data: p95Data,
                        backgroundColor: 'rgba(249, 115, 22, 0.7)',
                        borderColor: '#f97316',
                        borderWidth: 1,
                        barThickness: 16
                    }
                ]
            },
            options: options
        });
    }

    function createResourceUtilizationChart(data) {
        const canvas = document.getElementById('md-chart-resourceUtilization');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const chartData = data.resource_utilization;

        if (state.charts.resourceUtilization) {
            state.charts.resourceUtilization.destroy();
        }

        const options = getCommonChartOptions(true);
        options.scales.y.max = 100;
        options.scales.y.ticks.callback = (value) => `${value}%`;
        options.scales.y1 = {
            display: true,
            position: 'right',
            max: 100,
            grid: { display: false },
            ticks: {
                font: { size: 10 },
                color: '#6b7280',
                callback: (value) => `${value}%`
            }
        };

        state.charts.resourceUtilization = new Chart(ctx, {
            type: 'line',
            data: {
                labels: chartData.labels,
                datasets: [
                    {
                        label: 'CPU',
                        data: chartData.cpu_percent,
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.15)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Memory',
                        data: chartData.memory_percent,
                        borderColor: '#8b5cf6',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        tension: 0.3,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        yAxisID: 'y1'
                    }
                ]
            },
            options: options
        });
    }

    // =============================================================================
    // TABLES RENDERING
    // =============================================================================

    function renderTablesWithData(data) {
        const container = document.querySelector(config.tablesContainerId);
        if (!container) return;

        container.innerHTML = `
            <div class="model-dashboard-table-card" data-table="endpointPerformance">
                <div class="model-dashboard-table-header">
                    <span class="model-dashboard-table-title">Endpoint Performance</span>
                </div>
                <table class="model-dashboard-table">
                    <thead>
                        <tr>
                            <th>Endpoint</th>
                            <th>Requests</th>
                            <th>Avg</th>
                            <th>P95</th>
                            <th>Errors</th>
                            <th>Trend</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${renderEndpointPerformanceRows(data)}
                    </tbody>
                </table>
            </div>
            <div class="model-dashboard-table-card" data-table="peakUsagePeriods">
                <div class="model-dashboard-table-header">
                    <span class="model-dashboard-table-title">Peak Usage Periods</span>
                </div>
                <table class="model-dashboard-table">
                    <thead>
                        <tr>
                            <th>Time Period</th>
                            <th>Endpoint</th>
                            <th>Requests</th>
                            <th>Max Instances</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${renderPeakPeriodsRows(data)}
                    </tbody>
                </table>
            </div>
        `;
    }

    function renderSkeletonTables() {
        const container = document.querySelector(config.tablesContainerId);
        if (!container) return;

        container.innerHTML = TABLE_CONFIGS.map(table => `
            <div class="model-dashboard-table-card" data-table="${table.id}">
                <div class="model-dashboard-table-header">
                    <span class="model-dashboard-table-title">${table.title}</span>
                </div>
                <table class="model-dashboard-table">
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
                let widthClass = '';
                if (col === 'Trend') {
                    return '<td><div class="model-dashboard-trend-placeholder"></div></td>';
                } else if (idx === 0) {
                    widthClass = 'long';
                } else if (col === 'Avg' || col === 'P95' || col === 'Errors') {
                    widthClass = 'short';
                }
                return `<td><div class="model-dashboard-skeleton model-dashboard-skeleton-text ${widthClass}"></div></td>`;
            });
            rows.push(`<tr>${cells.join('')}</tr>`);
        }
        return rows.join('');
    }

    function renderEndpointPerformanceRows(data) {
        return data.endpoint_performance.map((ep, idx) => {
            const trendClass = ep.trend > 0 ? 'positive' : ep.trend < 0 ? 'negative' : 'neutral';
            const trendIcon = ep.trend > 0 ? 'fa-arrow-up' : ep.trend < 0 ? 'fa-arrow-down' : 'fa-minus';
            const errorClass = ep.error_rate > 0.5 ? 'error-high' : '';
            const color = ENDPOINT_COLORS[idx] ? ENDPOINT_COLORS[idx].primary : '#6b7280';

            return `
                <tr>
                    <td>
                        <span class="endpoint-indicator" style="background-color: ${color};"></span>
                        <span class="endpoint-name">${ep.name}</span>
                    </td>
                    <td>${formatNumber(ep.requests)}</td>
                    <td>${ep.avg_latency}ms</td>
                    <td>${ep.p95_latency}ms</td>
                    <td class="${errorClass}">${ep.errors} (${ep.error_rate}%)</td>
                    <td class="trend ${trendClass}">
                        <i class="fas ${trendIcon}"></i>
                        ${ep.trend > 0 ? '+' : ''}${ep.trend}%
                    </td>
                </tr>
            `;
        }).join('');
    }

    function renderPeakPeriodsRows(data) {
        return data.peak_periods.map(period => {
            const endpointIdx = data.endpoints.findIndex(ep => ep.name === period.endpoint);
            const color = ENDPOINT_COLORS[endpointIdx] ? ENDPOINT_COLORS[endpointIdx].primary : '#6b7280';

            return `
                <tr>
                    <td><strong>${period.time_period}</strong></td>
                    <td>
                        <span class="endpoint-indicator" style="background-color: ${color};"></span>
                        ${period.endpoint}
                    </td>
                    <td>${formatNumber(period.requests)}</td>
                    <td>${period.max_instances}</td>
                </tr>
            `;
        }).join('');
    }

    // =============================================================================
    // PUBLIC API
    // =============================================================================

    function init(options = {}) {
        if (options.containerId) config.containerId = options.containerId;
        if (options.kpiContainerId) config.kpiContainerId = options.kpiContainerId;
        if (options.chartsContainerId) config.chartsContainerId = options.chartsContainerId;
        if (options.tablesContainerId) config.tablesContainerId = options.tablesContainerId;
        if (options.chartHeight) config.chartHeight = options.chartHeight;

        state.initialized = true;
        return ModelDashboardEndpoints;
    }

    async function load() {
        if (!state.initialized) {
            init();
        }

        // Always fetch real KPI data from the API
        const realKpi = await fetchEndpointsKpi();

        // Load demo data for charts and tables (no real APIs exist yet)
        let demoData = null;
        if (DEMO_MODE_CHARTS) {
            demoData = await loadDemoData();
        }

        // Build merged data object with real KPIs + demo charts/tables
        if (realKpi || demoData) {
            const mergedData = {
                // Use real KPI data, fallback to demo if API fails
                endpoints_summary: realKpi || (demoData ? demoData.endpoints_summary : { total: 0, active: 0, inactive: 0 }),
                // Use demo data for performance KPIs (no real API)
                kpi_summary: demoData ? demoData.kpi_summary : {
                    total_requests: 0,
                    total_requests_change_pct: 0,
                    avg_latency_p95_ms: 0,
                    avg_latency_change_ms: 0,
                    error_rate_pct: 0,
                    error_rate_trend: '-',
                    peak_instances: 0,
                    avg_instances: 0
                },
                // Charts and tables use demo data
                endpoints: demoData ? demoData.endpoints : [],
                request_volume: demoData ? demoData.request_volume : null,
                latency_distribution: demoData ? demoData.latency_distribution : null,
                container_instances: demoData ? demoData.container_instances : null,
                error_rate: demoData ? demoData.error_rate : null,
                cold_start_latency: demoData ? demoData.cold_start_latency : null,
                resource_utilization: demoData ? demoData.resource_utilization : null,
                endpoint_performance: demoData ? demoData.endpoint_performance : [],
                peak_periods: demoData ? demoData.peak_periods : []
            };

            renderKPIsWithData(mergedData);

            // Only render charts and tables if we have demo data
            if (demoData) {
                renderChartsWithData(mergedData);
                renderTablesWithData(mergedData);
            } else {
                renderSkeletonCharts();
                renderSkeletonTables();
            }
            return;
        }

        // Fallback to skeleton UI if both fail
        renderSkeletonKPIs();
        renderSkeletonCharts();
        renderSkeletonTables();
    }

    function refresh() {
        destroyCharts();
        state.demoData = null;  // Clear demo data cache to force reload
        load();  // Will fetch fresh KPI data from API
    }

    // Expose public API
    return {
        init,
        load,
        refresh
    };

})();
