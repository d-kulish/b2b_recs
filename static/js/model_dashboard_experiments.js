/**
 * Model Dashboard - Experiments Chapter
 *
 * IIFE module for rendering experiments analytics on the dashboard.
 * Includes: Model Type KPI sections, Metrics Trend chart, Top Configurations table.
 */
const ModelDashboardExperiments = (function() {
    'use strict';

    // =============================================================================
    // STATE & CONFIG
    // =============================================================================

    let trendChart = null;
    let selectedModelType = 'retrieval';
    let state = {
        kpis: null,
        loading: false,
        initialized: false
    };

    const config = {
        kpiTrendContainerId: '#experimentsKpiTrendRow',
        topConfigsContainerId: '#experimentsTopConfigsSection',
        modelId: null,
        endpoints: {
            dashboardStats: '/api/experiments/dashboard-stats/',
            metricsTrend: '/api/experiments/metrics-trend/',
            topConfigurations: '/api/experiments/top-configurations/'
        },
        chartHeight: 200,
        topConfigsLimit: 5
    };

    function appendModelEndpointId(url) {
        if (!config.modelId) return url;
        const sep = url.includes('?') ? '&' : '?';
        return `${url}${sep}model_endpoint_id=${config.modelId}`;
    }

    // =============================================================================
    // INITIALIZATION
    // =============================================================================

    function init(options = {}) {
        Object.assign(config, options);
        state.initialized = true;
        renderSkeleton();
    }

    function renderSkeleton() {
        const kpiTrendContainer = document.querySelector(config.kpiTrendContainerId);
        const topConfigsContainer = document.querySelector(config.topConfigsContainerId);

        if (kpiTrendContainer) {
            kpiTrendContainer.innerHTML = `
                <!-- Model Type KPI Sections -->
                <div class="model-dashboard-experiments-model-sections">
                    ${renderModelSectionSkeleton('retrieval', 'Retrieval', 'fa-search')}
                    ${renderModelSectionSkeleton('ranking', 'Ranking', 'fa-sort-amount-down')}
                    ${renderModelSectionSkeleton('hybrid', 'Hybrid', 'fa-layer-group')}
                </div>

                <!-- Metrics Trend Panel -->
                <div class="model-dashboard-experiments-trend-panel">
                    <div class="model-dashboard-experiments-section-header">
                        <span class="model-dashboard-experiments-section-title">Metrics Trend</span>
                        <span class="model-dashboard-experiments-section-subtitle">Best Recall metrics over time</span>
                    </div>
                    <div id="experimentsTrendChartContainer" class="model-dashboard-experiments-chart-container">
                        <canvas id="experimentsTrendCanvas"></canvas>
                        <div id="experimentsTrendEmpty" class="model-dashboard-experiments-empty hidden">
                            <i class="fas fa-chart-line"></i>
                            <p>Not enough data for trend analysis</p>
                        </div>
                    </div>
                </div>
            `;
        }

        if (topConfigsContainer) {
            topConfigsContainer.innerHTML = `
                <div class="model-dashboard-experiments-section-header">
                    <span class="model-dashboard-experiments-section-title" id="experimentsTopConfigsTitle">Top Configurations</span>
                    <span class="model-dashboard-experiments-section-subtitle" id="experimentsTopConfigsSubtitle">Best performing retrieval experiments (by R@100)</span>
                </div>
                <div class="model-dashboard-experiments-table-container">
                    <table class="model-dashboard-experiments-table">
                        <thead id="experimentsTopConfigsHead">
                            <tr>
                                <th style="width: 40px; text-align: center;">#</th>
                                <th style="text-align: center;">Experiment</th>
                                <th>Dataset</th>
                                <th>Feature</th>
                                <th>Model</th>
                                <th style="text-align: center;">LR</th>
                                <th style="text-align: center;">Batch</th>
                                <th style="text-align: center;">Epochs</th>
                                <th style="text-align: center;">R@100</th>
                                <th style="text-align: center;">Loss</th>
                            </tr>
                        </thead>
                        <tbody id="experimentsTopConfigsBody">
                            <tr>
                                <td colspan="10" class="model-dashboard-experiments-table-empty">
                                    <i class="fas fa-spinner fa-spin"></i>
                                    Loading...
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            `;
        }
    }

    function renderModelSectionSkeleton(type, title, icon) {
        const isSelected = type === selectedModelType ? 'selected' : '';
        const kpiLabels = getKpiLabels(type);

        return `
            <div id="experimentsSection_${type}"
                 class="model-dashboard-experiments-model-section ${type} ${isSelected}"
                 onclick="ModelDashboardExperiments.selectModelType('${type}')">
                <div class="model-dashboard-experiments-model-header">
                    <div class="model-dashboard-experiments-model-icon ${type}">
                        <i class="fas ${icon}"></i>
                    </div>
                    <span class="model-dashboard-experiments-model-title">${title}</span>
                </div>
                <div class="model-dashboard-experiments-kpi-stack">
                    <div class="model-dashboard-experiments-kpi-compact">
                        <div class="model-dashboard-experiments-kpi-label">Experiments</div>
                        <div class="model-dashboard-experiments-kpi-value" id="experiments_${type}_count">-</div>
                    </div>
                    ${kpiLabels.map((label, idx) => `
                        <div class="model-dashboard-experiments-kpi-compact">
                            <div class="model-dashboard-experiments-kpi-label">${label}</div>
                            <div class="model-dashboard-experiments-kpi-value highlight" id="experiments_${type}_metric${idx}">-</div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    function getKpiLabels(type) {
        switch (type) {
            case 'ranking':
                return ['RMSE', 'Test RMSE', 'MAE', 'Test MAE'];
            case 'hybrid':
                return ['RMSE', 'Test RMSE', 'R@50', 'R@100'];
            default: // retrieval
                return ['R@5', 'R@10', 'R@50', 'R@100'];
        }
    }

    // =============================================================================
    // DATA LOADING
    // =============================================================================

    async function load() {
        if (state.loading) return;
        state.loading = true;

        try {
            await Promise.all([
                loadKpis(),
                loadMetricsTrend(selectedModelType),
                loadTopConfigurations(selectedModelType)
            ]);
        } catch (error) {
            console.error('Failed to load experiments dashboard:', error);
        } finally {
            state.loading = false;
        }
    }

    async function loadKpis() {
        try {
            const response = await fetch(appendModelEndpointId(config.endpoints.dashboardStats));
            const data = await response.json();

            if (!data.success) {
                console.error('Failed to load KPIs:', data.error);
                return;
            }

            state.kpis = data.stats;

            // Update Retrieval KPIs
            updateKpiValue('experiments_retrieval_count', data.stats?.retrieval?.count || 0);
            updateKpiValue('experiments_retrieval_metric0', formatRecall(data.stats?.retrieval?.best_r5));
            updateKpiValue('experiments_retrieval_metric1', formatRecall(data.stats?.retrieval?.best_r10));
            updateKpiValue('experiments_retrieval_metric2', formatRecall(data.stats?.retrieval?.best_r50));
            updateKpiValue('experiments_retrieval_metric3', formatRecall(data.stats?.retrieval?.best_r100));

            // Update Ranking KPIs
            updateKpiValue('experiments_ranking_count', data.stats?.ranking?.count || 0);
            updateKpiValue('experiments_ranking_metric0', formatAccuracy(data.stats?.ranking?.best_rmse));
            updateKpiValue('experiments_ranking_metric1', formatAccuracy(data.stats?.ranking?.best_test_rmse));
            updateKpiValue('experiments_ranking_metric2', formatAccuracy(data.stats?.ranking?.best_mae));
            updateKpiValue('experiments_ranking_metric3', formatAccuracy(data.stats?.ranking?.best_test_mae));

            // Update Hybrid KPIs
            updateKpiValue('experiments_hybrid_count', data.stats?.hybrid?.count || 0);
            updateKpiValue('experiments_hybrid_metric0', formatAccuracy(data.stats?.hybrid?.best_rmse));
            updateKpiValue('experiments_hybrid_metric1', formatAccuracy(data.stats?.hybrid?.best_test_rmse));
            updateKpiValue('experiments_hybrid_metric2', formatRecall(data.stats?.hybrid?.best_r50));
            updateKpiValue('experiments_hybrid_metric3', formatRecall(data.stats?.hybrid?.best_r100));

        } catch (error) {
            console.error('Error loading KPIs:', error);
        }
    }

    function updateKpiValue(elementId, value) {
        const el = document.getElementById(elementId);
        if (el) {
            el.textContent = value !== null && value !== undefined ? value : '-';
        }
    }

    function formatRecall(value) {
        if (value === null || value === undefined) return '-';
        return (Number(value) * 100).toFixed(1) + '%';
    }

    function formatAccuracy(value) {
        if (value === null || value === undefined) return '-';
        return Number(value).toFixed(2);
    }

    // =============================================================================
    // METRICS TREND CHART
    // =============================================================================

    async function loadMetricsTrend(modelType = null) {
        const canvas = document.getElementById('experimentsTrendCanvas');
        const emptyEl = document.getElementById('experimentsTrendEmpty');
        const headerTitle = document.querySelector('.model-dashboard-experiments-trend-panel .model-dashboard-experiments-section-title');
        const headerSubtitle = document.querySelector('.model-dashboard-experiments-trend-panel .model-dashboard-experiments-section-subtitle');

        const activeModelType = modelType || selectedModelType;

        // Update header based on model type
        const headerConfig = {
            'retrieval': { title: 'Metrics Trend', subtitle: 'Best Recall metrics over time' },
            'ranking': { title: 'Metrics Trend', subtitle: 'Best RMSE/MAE metrics over time (lower is better)' },
            'hybrid': { title: 'Metrics Trend', subtitle: 'Hybrid model metrics over time' }
        };
        const hc = headerConfig[activeModelType] || headerConfig['retrieval'];
        if (headerTitle) headerTitle.textContent = hc.title;
        if (headerSubtitle) headerSubtitle.textContent = hc.subtitle;

        // Destroy existing chart
        if (trendChart) {
            trendChart.destroy();
            trendChart = null;
        }

        try {
            const response = await fetch(appendModelEndpointId(`${config.endpoints.metricsTrend}?model_type=${activeModelType}`));
            const data = await response.json();

            if (!data.success || !data.trend || data.trend.length < 2) {
                canvas.style.display = 'none';
                emptyEl.classList.remove('hidden');
                return;
            }

            canvas.style.display = 'block';
            emptyEl.classList.add('hidden');

            const ctx = canvas.getContext('2d');
            const datasets = buildChartDatasets(data.trend, activeModelType);
            const chartOptions = buildChartOptions(data.trend, activeModelType);

            trendChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.trend.map(d => d.date),
                    datasets: datasets
                },
                options: chartOptions
            });

        } catch (error) {
            console.error('Failed to load metrics trend:', error);
            canvas.style.display = 'none';
            emptyEl.classList.remove('hidden');
        }
    }

    function buildChartDatasets(trend, modelType) {
        if (modelType === 'ranking') {
            return [
                {
                    label: 'Best RMSE',
                    data: trend.map(d => d.best_rmse),
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245, 158, 11, 0.25)',
                    fill: 'origin',
                    tension: 0.3,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    borderWidth: 2
                },
                {
                    label: 'Best Test RMSE',
                    data: trend.map(d => d.best_test_rmse),
                    borderColor: '#d97706',
                    backgroundColor: 'rgba(217, 119, 6, 0.2)',
                    fill: 'origin',
                    tension: 0.3,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    borderWidth: 2
                },
                {
                    label: 'Best MAE',
                    data: trend.map(d => d.best_mae),
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.25)',
                    fill: 'origin',
                    tension: 0.3,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    borderWidth: 2
                },
                {
                    label: 'Best Test MAE',
                    data: trend.map(d => d.best_test_mae),
                    borderColor: '#059669',
                    backgroundColor: 'rgba(5, 150, 105, 0.2)',
                    fill: 'origin',
                    tension: 0.3,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    borderWidth: 2
                }
            ];
        } else if (modelType === 'hybrid') {
            return [
                {
                    label: 'R@100',
                    data: trend.map(d => d.best_r100),
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.35)',
                    fill: '+1',
                    tension: 0.3,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    borderWidth: 2,
                    yAxisID: 'y'
                },
                {
                    label: 'R@50',
                    data: trend.map(d => d.best_r50),
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.35)',
                    fill: '+1',
                    tension: 0.3,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    borderWidth: 2,
                    yAxisID: 'y'
                },
                {
                    label: 'R@10',
                    data: trend.map(d => d.best_r10),
                    borderColor: '#8b5cf6',
                    backgroundColor: 'rgba(139, 92, 246, 0.35)',
                    fill: 'origin',
                    tension: 0.3,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    borderWidth: 2,
                    yAxisID: 'y'
                },
                {
                    label: 'RMSE',
                    data: trend.map(d => d.best_rmse),
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245, 158, 11, 0.2)',
                    fill: 'origin',
                    tension: 0.3,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    borderWidth: 2,
                    borderDash: [5, 5],
                    yAxisID: 'y1'
                },
                {
                    label: 'Test RMSE',
                    data: trend.map(d => d.best_test_rmse),
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.15)',
                    fill: 'origin',
                    tension: 0.3,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    borderWidth: 2,
                    borderDash: [5, 5],
                    yAxisID: 'y1'
                }
            ];
        } else {
            // Retrieval
            return [
                {
                    label: 'Best R@100',
                    data: trend.map(d => d.best_r100),
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.4)',
                    fill: '+1',
                    tension: 0.3,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    borderWidth: 2
                },
                {
                    label: 'Best R@50',
                    data: trend.map(d => d.best_r50),
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.4)',
                    fill: '+1',
                    tension: 0.3,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    borderWidth: 2
                },
                {
                    label: 'Best R@10',
                    data: trend.map(d => d.best_r10),
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245, 158, 11, 0.4)',
                    fill: '+1',
                    tension: 0.3,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    borderWidth: 2
                },
                {
                    label: 'Best R@5',
                    data: trend.map(d => d.best_r5),
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.4)',
                    fill: 'origin',
                    tension: 0.3,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    borderWidth: 2
                }
            ];
        }
    }

    function buildChartOptions(trend, modelType) {
        const baseOptions = {
            responsive: true,
            maintainAspectRatio: false,
            layout: {
                padding: { right: 10 }
            },
            plugins: {
                legend: {
                    position: 'top',
                    align: 'end',
                    labels: { boxWidth: 12, font: { size: 11 } }
                },
                tooltip: {
                    callbacks: {
                        label: (context) => {
                            const label = context.dataset.label || '';
                            const val = context.parsed.y;
                            if (val == null) return label;
                            const isRecall = modelType === 'retrieval' ||
                                (modelType === 'hybrid' && context.dataset.yAxisID !== 'y1');
                            const formatted = isRecall ? (val * 100).toFixed(1) + '%' : val.toFixed(2);
                            return `${label}: ${formatted}`;
                        },
                        afterLabel: (context) => {
                            const idx = context.dataIndex;
                            return `Experiments: ${trend[idx].experiment_count}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { font: { size: 10 }, maxTicksLimit: 10 }
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    beginAtZero: false,
                    grid: { color: 'rgba(0,0,0,0.05)' },
                    ticks: {
                        font: { size: 10 },
                        callback: (value) => modelType === 'ranking'
                            ? value.toFixed(2)
                            : (value * 100).toFixed(0) + '%'
                    },
                    title: modelType === 'hybrid' ? {
                        display: true,
                        text: 'Recall',
                        font: { size: 10 }
                    } : undefined
                }
            }
        };

        // Add right Y-axis for hybrid models
        if (modelType === 'hybrid') {
            baseOptions.scales.y1 = {
                type: 'linear',
                display: true,
                position: 'right',
                beginAtZero: false,
                grid: { drawOnChartArea: false },
                ticks: {
                    font: { size: 10 },
                    callback: (value) => value.toFixed(2)
                },
                title: {
                    display: true,
                    text: 'RMSE',
                    font: { size: 10 }
                }
            };
        }

        return baseOptions;
    }

    // =============================================================================
    // TOP CONFIGURATIONS TABLE
    // =============================================================================

    async function loadTopConfigurations(modelType = null) {
        const thead = document.getElementById('experimentsTopConfigsHead');
        const tbody = document.getElementById('experimentsTopConfigsBody');
        const titleEl = document.getElementById('experimentsTopConfigsTitle');
        const subtitleEl = document.getElementById('experimentsTopConfigsSubtitle');

        const activeModelType = modelType || selectedModelType;

        // Update header based on model type
        const headerConfig = {
            'retrieval': {
                title: 'Top Configurations',
                subtitle: 'Best performing retrieval experiments (by R@100)'
            },
            'ranking': {
                title: 'Top Configurations',
                subtitle: 'Best performing ranking experiments (by Test RMSE, lower is better)'
            },
            'hybrid': {
                title: 'Top Configurations',
                subtitle: 'Best performing hybrid experiments'
            }
        };
        const hc = headerConfig[activeModelType] || headerConfig['retrieval'];
        if (titleEl) titleEl.textContent = hc.title;
        if (subtitleEl) subtitleEl.textContent = hc.subtitle;

        // Update table header based on model type
        if (activeModelType === 'ranking') {
            thead.innerHTML = `
                <tr>
                    <th style="width: 40px; text-align: center;">#</th>
                    <th style="text-align: center;">Experiment</th>
                    <th>Dataset</th>
                    <th>Feature</th>
                    <th>Model</th>
                    <th style="text-align: center;">LR</th>
                    <th style="text-align: center;">Batch</th>
                    <th style="text-align: center;">Epochs</th>
                    <th style="text-align: center;">Test RMSE</th>
                    <th style="text-align: center;">Test MAE</th>
                </tr>
            `;
        } else if (activeModelType === 'hybrid') {
            thead.innerHTML = `
                <tr>
                    <th style="width: 40px; text-align: center;">#</th>
                    <th style="text-align: center;">Experiment</th>
                    <th>Dataset</th>
                    <th>Feature</th>
                    <th>Model</th>
                    <th style="text-align: center;">LR</th>
                    <th style="text-align: center;">R@100</th>
                    <th style="text-align: center;">R@50</th>
                    <th style="text-align: center;">Test RMSE</th>
                    <th style="text-align: center;">Test MAE</th>
                </tr>
            `;
        } else {
            thead.innerHTML = `
                <tr>
                    <th style="width: 40px; text-align: center;">#</th>
                    <th style="text-align: center;">Experiment</th>
                    <th>Dataset</th>
                    <th>Feature</th>
                    <th>Model</th>
                    <th style="text-align: center;">LR</th>
                    <th style="text-align: center;">Batch</th>
                    <th style="text-align: center;">Epochs</th>
                    <th style="text-align: center;">R@100</th>
                    <th style="text-align: center;">Loss</th>
                </tr>
            `;
        }

        try {
            const response = await fetch(appendModelEndpointId(`${config.endpoints.topConfigurations}?limit=${config.topConfigsLimit}&model_type=${activeModelType}`));
            const data = await response.json();

            if (!data.success || !data.configurations || data.configurations.length === 0) {
                const modelLabel = activeModelType === 'hybrid' ? 'hybrid' : (activeModelType === 'ranking' ? 'ranking' : 'retrieval');
                tbody.innerHTML = `
                    <tr>
                        <td colspan="10" class="model-dashboard-experiments-table-empty">
                            <i class="fas fa-flask"></i>
                            No completed ${modelLabel} experiments yet
                        </td>
                    </tr>
                `;
                return;
            }

            tbody.innerHTML = data.configurations.map((cfg, index) => {
                return renderConfigRow(cfg, index, activeModelType, data.configurations[0]);
            }).join('');

        } catch (error) {
            console.error('Failed to load top configurations:', error);
            tbody.innerHTML = `
                <tr>
                    <td colspan="10" class="model-dashboard-experiments-table-empty">
                        <i class="fas fa-exclamation-triangle"></i>
                        Failed to load configurations
                    </td>
                </tr>
            `;
        }
    }

    function renderConfigRow(cfg, index, modelType, bestConfig) {
        const rankClass = index < 3 ? `rank-${index + 1}` : '';

        if (modelType === 'ranking') {
            const isBest = cfg.test_rmse === bestConfig?.test_rmse;
            return `
                <tr onclick="ModelDashboardExperiments.openExpDetails(${cfg.experiment_id})" title="Click to view details">
                    <td class="rank-cell ${rankClass}">${cfg.rank}</td>
                    <td style="text-align: center;">${cfg.display_name || 'Exp #' + cfg.experiment_number}</td>
                    <td>${cfg.dataset || '-'}</td>
                    <td>${cfg.feature_config || '-'}</td>
                    <td>${cfg.model_config || '-'}</td>
                    <td style="text-align: center;">${cfg.learning_rate}</td>
                    <td style="text-align: center;">${cfg.batch_size}</td>
                    <td style="text-align: center;">${cfg.epochs}</td>
                    <td style="text-align: center;" class="${isBest ? 'metric-best' : ''}">
                        ${cfg.test_rmse !== null ? cfg.test_rmse.toFixed(2) : '-'}
                    </td>
                    <td style="text-align: center;">
                        ${cfg.test_mae !== null ? cfg.test_mae.toFixed(2) : '-'}
                    </td>
                </tr>
            `;
        } else if (modelType === 'hybrid') {
            const isBest = cfg.recall_at_100 === bestConfig?.recall_at_100;
            return `
                <tr onclick="ModelDashboardExperiments.openExpDetails(${cfg.experiment_id})" title="Click to view details">
                    <td class="rank-cell ${rankClass}">${cfg.rank}</td>
                    <td style="text-align: center;">${cfg.display_name || 'Exp #' + cfg.experiment_number}</td>
                    <td>${cfg.dataset || '-'}</td>
                    <td>${cfg.feature_config || '-'}</td>
                    <td>${cfg.model_config || '-'}</td>
                    <td style="text-align: center;">${cfg.learning_rate}</td>
                    <td style="text-align: center;" class="${isBest ? 'metric-best' : ''}">
                        ${cfg.recall_at_100 != null ? (cfg.recall_at_100 * 100).toFixed(1) + '%' : '-'}
                    </td>
                    <td style="text-align: center;">
                        ${cfg.recall_at_50 != null ? (cfg.recall_at_50 * 100).toFixed(1) + '%' : '-'}
                    </td>
                    <td style="text-align: center;">
                        ${cfg.test_rmse != null ? cfg.test_rmse.toFixed(2) : '-'}
                    </td>
                    <td style="text-align: center;">
                        ${cfg.test_mae != null ? cfg.test_mae.toFixed(2) : '-'}
                    </td>
                </tr>
            `;
        } else {
            // Retrieval
            const isBest = cfg.recall_at_100 === bestConfig?.recall_at_100;
            return `
                <tr onclick="ModelDashboardExperiments.openExpDetails(${cfg.experiment_id})" title="Click to view details">
                    <td class="rank-cell ${rankClass}">${cfg.rank}</td>
                    <td style="text-align: center;">${cfg.display_name || 'Exp #' + cfg.experiment_number}</td>
                    <td>${cfg.dataset || '-'}</td>
                    <td>${cfg.feature_config || '-'}</td>
                    <td>${cfg.model_config || '-'}</td>
                    <td style="text-align: center;">${cfg.learning_rate}</td>
                    <td style="text-align: center;">${cfg.batch_size}</td>
                    <td style="text-align: center;">${cfg.epochs}</td>
                    <td style="text-align: center;" class="${isBest ? 'metric-best' : ''}">
                        ${cfg.recall_at_100 !== null ? (cfg.recall_at_100 * 100).toFixed(1) + '%' : '-'}
                    </td>
                    <td style="text-align: center;">
                        ${cfg.loss !== null ? cfg.loss.toFixed(1) : '-'}
                    </td>
                </tr>
            `;
        }
    }

    // =============================================================================
    // MODEL TYPE SELECTION
    // =============================================================================

    function selectModelType(type) {
        if (type === selectedModelType) return;

        // Update visual selection
        document.querySelectorAll('.model-dashboard-experiments-model-section').forEach(el => {
            el.classList.remove('selected');
        });
        const selectedEl = document.getElementById(`experimentsSection_${type}`);
        if (selectedEl) {
            selectedEl.classList.add('selected');
        }

        selectedModelType = type;

        // Reload trend and table with new model type
        loadMetricsTrend(type);
        loadTopConfigurations(type);
    }

    // =============================================================================
    // EXPERIMENT DETAILS
    // =============================================================================

    function openExpDetails(expId) {
        // Use ExpViewModal if available
        if (typeof ExpViewModal !== 'undefined' && ExpViewModal.open) {
            ExpViewModal.open(expId);
        } else {
            // Fallback: navigate to experiments page
            console.warn('ExpViewModal not available, cannot open experiment details');
        }
    }

    // =============================================================================
    // PUBLIC API
    // =============================================================================

    return {
        init: init,
        load: load,
        refresh: load,
        selectModelType: selectModelType,
        openExpDetails: openExpDetails
    };

})();
