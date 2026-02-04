/**
 * Model Dashboard - Configs Chapter
 *
 * Displays configuration inventory KPIs (Datasets, Features, Models)
 * Uses the same data source as the Configs page dashboard.
 *
 * @module ModelDashboardConfigs
 */
const ModelDashboardConfigs = (function() {
    'use strict';

    // =========================================================================
    // CONFIGURATION
    // =========================================================================
    const config = {
        containerId: '#configsChapter',
        loadingId: '#configsChapterLoading',
        emptyId: '#configsChapterEmpty',
        kpiRowId: '#configsChapterKpiRow'
    };

    // =========================================================================
    // STATE
    // =========================================================================
    let state = {
        initialized: false,
        loading: false,
        data: null,
        modelId: null
    };

    // =========================================================================
    // PRIVATE METHODS
    // =========================================================================

    /**
     * Extract model ID from the current page URL.
     * Expects URL pattern: /models/{id}/dashboard/
     */
    function getModelIdFromUrl() {
        const match = window.location.pathname.match(/\/models\/(\d+)\//);
        return match ? match[1] : null;
    }

    /**
     * Show loading state.
     */
    function showLoading() {
        document.querySelector(config.loadingId).classList.remove('hidden');
        document.querySelector(config.emptyId).classList.add('hidden');
        document.querySelector(config.kpiRowId).classList.add('hidden');
    }

    /**
     * Show empty state.
     */
    function showEmpty() {
        document.querySelector(config.loadingId).classList.add('hidden');
        document.querySelector(config.emptyId).classList.remove('hidden');
        document.querySelector(config.kpiRowId).classList.add('hidden');
    }

    /**
     * Show content.
     */
    function showContent() {
        document.querySelector(config.loadingId).classList.add('hidden');
        document.querySelector(config.emptyId).classList.add('hidden');
        document.querySelector(config.kpiRowId).classList.remove('hidden');
    }

    /**
     * Format complexity bar HTML.
     * Uses same thresholds as the Configs page.
     *
     * @param {number} score - Complexity score
     * @param {string} type - Config type: 'dataset', 'feature_config', 'model_config'
     * @returns {string} HTML string
     */
    function formatComplexityBar(score, type) {
        // Thresholds based on type (matching Configs page logic)
        let lowMax, medMax;
        if (type === 'dataset') {
            lowMax = 5;
            medMax = 15;
        } else if (type === 'feature_config') {
            lowMax = 10;
            medMax = 25;
        } else {
            lowMax = 8;
            medMax = 15;
        }

        // Calculate percentages (capped at 100%)
        const total = Math.max(score, medMax * 1.5);
        const lowPct = Math.min((Math.min(score, lowMax) / total) * 100, 100);
        const medPct = score > lowMax ? Math.min(((Math.min(score, medMax) - lowMax) / total) * 100, 100 - lowPct) : 0;
        const highPct = score > medMax ? Math.min(((score - medMax) / total) * 100, 100 - lowPct - medPct) : 0;

        const complexityLabel = score <= lowMax ? 'Low' : score <= medMax ? 'Medium' : 'High';

        return `
            <div class="model-dashboard-configs-complexity-row">
                <div class="model-dashboard-configs-complexity-label">
                    <span>Avg Complexity</span>
                    <span>${score.toFixed(1)} (${complexityLabel})</span>
                </div>
                <div class="model-dashboard-configs-complexity-bar">
                    <div class="model-dashboard-configs-complexity-segment low" style="width: ${lowPct}%"></div>
                    <div class="model-dashboard-configs-complexity-segment medium" style="width: ${medPct}%"></div>
                    <div class="model-dashboard-configs-complexity-segment high" style="width: ${highPct}%"></div>
                </div>
            </div>
        `;
    }

    /**
     * Render KPI cards for Datasets, Features, and Models.
     *
     * @param {Object} stats - Dashboard stats from API
     */
    function renderKpiCards(stats) {
        const container = document.querySelector(config.kpiRowId);
        const ds = stats.datasets;
        const fc = stats.feature_configs;
        const mc = stats.model_configs;

        container.innerHTML = `
            <!-- Datasets KPI Card -->
            <div class="model-dashboard-configs-kpi-card">
                <div class="model-dashboard-configs-kpi-title">Dataset Configs</div>
                <div class="model-dashboard-configs-kpi-content">
                    <div class="model-dashboard-configs-kpi-icon datasets">
                        <i class="fas fa-database"></i>
                    </div>
                    <div class="model-dashboard-configs-kpi-stats">
                        <div class="model-dashboard-configs-kpi-stat">
                            <div class="model-dashboard-configs-kpi-value">${ds.total}</div>
                            <div class="model-dashboard-configs-kpi-label">Total</div>
                        </div>
                        <div class="model-dashboard-configs-kpi-stat">
                            <div class="model-dashboard-configs-kpi-value active">${ds.active}</div>
                            <div class="model-dashboard-configs-kpi-label">Active</div>
                        </div>
                        <div class="model-dashboard-configs-kpi-stat">
                            <div class="model-dashboard-configs-kpi-value unused">${ds.unused}</div>
                            <div class="model-dashboard-configs-kpi-label">Unused</div>
                        </div>
                    </div>
                </div>
                ${formatComplexityBar(ds.avg_complexity, 'dataset')}
            </div>

            <!-- Features KPI Card -->
            <div class="model-dashboard-configs-kpi-card">
                <div class="model-dashboard-configs-kpi-title">Feature Configs</div>
                <div class="model-dashboard-configs-kpi-content">
                    <div class="model-dashboard-configs-kpi-icon features">
                        <i class="fas fa-microchip"></i>
                    </div>
                    <div class="model-dashboard-configs-kpi-stats">
                        <div class="model-dashboard-configs-kpi-stat">
                            <div class="model-dashboard-configs-kpi-value">${fc.total}</div>
                            <div class="model-dashboard-configs-kpi-label">Total</div>
                        </div>
                        <div class="model-dashboard-configs-kpi-stat">
                            <div class="model-dashboard-configs-kpi-value active">${fc.active}</div>
                            <div class="model-dashboard-configs-kpi-label">Active</div>
                        </div>
                        <div class="model-dashboard-configs-kpi-stat">
                            <div class="model-dashboard-configs-kpi-value unused">${fc.unused}</div>
                            <div class="model-dashboard-configs-kpi-label">Unused</div>
                        </div>
                    </div>
                </div>
                ${formatComplexityBar(fc.avg_complexity, 'feature_config')}
            </div>

            <!-- Models KPI Card -->
            <div class="model-dashboard-configs-kpi-card">
                <div class="model-dashboard-configs-kpi-title">Model Configs</div>
                <div class="model-dashboard-configs-kpi-content">
                    <div class="model-dashboard-configs-kpi-icon models">
                        <i class="fas fa-layer-group"></i>
                    </div>
                    <div class="model-dashboard-configs-kpi-stats">
                        <div class="model-dashboard-configs-kpi-stat">
                            <div class="model-dashboard-configs-kpi-value">${mc.total}</div>
                            <div class="model-dashboard-configs-kpi-label">Total</div>
                        </div>
                        <div class="model-dashboard-configs-kpi-stat">
                            <div class="model-dashboard-configs-kpi-value active">${mc.used}</div>
                            <div class="model-dashboard-configs-kpi-label">Used</div>
                        </div>
                        <div class="model-dashboard-configs-kpi-stat">
                            <div class="model-dashboard-configs-kpi-value unused">${mc.unused}</div>
                            <div class="model-dashboard-configs-kpi-label">Unused</div>
                        </div>
                    </div>
                </div>
                ${formatComplexityBar(mc.avg_complexity, 'model_config')}
            </div>
        `;
    }

    /**
     * Fetch dashboard stats from API.
     */
    function fetchData() {
        if (!state.modelId) {
            console.error('ModelDashboardConfigs: No model ID found');
            showEmpty();
            return;
        }

        state.loading = true;
        showLoading();

        fetch(`/api/models/${state.modelId}/configs/dashboard-stats/`)
            .then(response => response.json())
            .then(data => {
                state.loading = false;

                if (data.success) {
                    state.data = data.data;

                    // Check if there's any data
                    const hasData = data.data.datasets.total > 0 ||
                                   data.data.feature_configs.total > 0 ||
                                   data.data.model_configs.total > 0;

                    if (!hasData) {
                        showEmpty();
                    } else {
                        renderKpiCards(data.data);
                        showContent();
                    }
                } else {
                    console.error('ModelDashboardConfigs: API error:', data.error);
                    showEmpty();
                }
            })
            .catch(error => {
                state.loading = false;
                console.error('ModelDashboardConfigs: Fetch error:', error);
                showEmpty();
            });
    }

    // =========================================================================
    // PUBLIC API
    // =========================================================================
    return {
        /**
         * Initialize the Configs chapter.
         *
         * @param {Object} options - Optional configuration overrides
         */
        init: function(options) {
            if (options) {
                Object.assign(config, options);
            }

            state.modelId = getModelIdFromUrl();
            state.initialized = true;
        },

        /**
         * Load data and render the chapter.
         */
        load: function() {
            if (!state.initialized) {
                this.init();
            }
            fetchData();
        },

        /**
         * Refresh the chapter data.
         */
        refresh: function() {
            state.data = null;
            fetchData();
        },

        /**
         * Get current state (for debugging).
         */
        getState: function() {
            return { ...state };
        }
    };
})();
