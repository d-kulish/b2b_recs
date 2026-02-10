/**
 * Model Dashboard Models Module
 *
 * Manages the Models chapter on the Model Dashboard page.
 * Displays models from Vertex AI Model Registry with KPIs, calendar, and table.
 * Uses the same real API endpoints as Models Registry - no demo data.
 *
 * Usage:
 *     ModelDashboardModels.init({
 *         containerId: '#modelsChapter'
 *     });
 *     ModelDashboardModels.load();
 */

const ModelDashboardModels = (function() {
    'use strict';

    // =============================================================================
    // CONFIGURATION & STATE
    // =============================================================================

    const config = {
        containerId: '#modelsChapter',
        kpiContainerId: '#modelsChapterKpiRow',
        calendarContainerId: '#modelsChapterCalendar',
        filterBarId: '#modelsChapterFilterBar',
        tableContainerId: '#modelsChapterTable',
        emptyStateId: '#modelsChapterEmptyState',
        endpoints: {
            list: '/api/models/'
        }
    };

    let state = {
        models: [],
        kpi: { total: 0, deployed: 0, outdated: 0, idle: 0, scheduled: 0 },
        pagination: { page: 1, pageSize: 5, totalCount: 0, totalPages: 1 },
        filters: {
            modelType: 'all',
            status: 'all',
            sort: 'latest',
            search: ''
        },
        loading: false,
        searchDebounceTimer: null,
        initialized: false
    };

    // Deployment status badge configurations
    const STATUS_CONFIG = {
        deployed: { icon: 'fa-rocket', label: 'Deployed', class: 'deployed' },
        outdated: { icon: 'fa-exclamation-triangle', label: 'Outdated', class: 'outdated' },
        idle: { icon: 'fa-pause-circle', label: 'Idle', class: 'idle' },
        unknown: { icon: 'fa-question-circle', label: 'Unknown', class: 'unknown' }
    };

    // Model type configurations
    const TYPE_CONFIG = {
        retrieval: { icon: 'fa-search', label: 'Retrieval' },
        ranking: { icon: 'fa-sort-amount-up', label: 'Ranking' },
        multitask: { icon: 'fa-layer-group', label: 'Multitask' }
    };

    // =============================================================================
    // UTILITY FUNCTIONS
    // =============================================================================

    function formatAge(isoStr) {
        if (!isoStr) return { text: '-', class: '' };
        const registered = new Date(isoStr);
        const now = new Date();

        const registeredDate = new Date(registered.getFullYear(), registered.getMonth(), registered.getDate());
        const todayDate = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const diffMs = todayDate - registeredDate;
        const days = Math.round(diffMs / (1000 * 60 * 60 * 24));

        let ageClass = '';
        if (days > 14) {
            ageClass = 'age-old';
        } else if (days > 7) {
            ageClass = 'age-warning';
        }

        let text;
        if (days === 0) {
            text = 'Today';
        } else if (days === 1) {
            text = '1 day';
        } else {
            text = `${days} days`;
        }

        return { text, class: ageClass };
    }

    function formatMetric(value, decimals = 4) {
        if (value === null || value === undefined) return '-';
        return value.toFixed(decimals);
    }

    function formatMetricAsPercent(value) {
        if (value === null || value === undefined) return '-';
        return Math.round(value * 100) + '%';
    }

    // =============================================================================
    // API CALLS
    // =============================================================================

    async function fetchModels() {
        state.loading = true;
        renderLoading();

        try {
            const params = new URLSearchParams();
            params.append('page', state.pagination.page);
            params.append('page_size', state.pagination.pageSize);

            if (state.filters.modelType !== 'all') {
                params.append('model_type', state.filters.modelType);
            }
            if (state.filters.status !== 'all') {
                params.append('status', state.filters.status);
            }
            if (state.filters.sort) {
                params.append('sort', state.filters.sort);
            }
            if (state.filters.search) {
                params.append('search', state.filters.search);
            }

            const response = await fetch(`${config.endpoints.list}?${params.toString()}`);
            const data = await response.json();

            if (data.success) {
                state.models = data.models || [];
                state.kpi = data.kpi || state.kpi;
                state.pagination = {
                    page: data.pagination?.page || 1,
                    pageSize: data.pagination?.page_size || 5,
                    totalCount: data.pagination?.total_count || 0,
                    totalPages: data.pagination?.total_pages || 1,
                    hasNext: data.pagination?.has_next || false,
                    hasPrev: data.pagination?.has_prev || false
                };
                render({ includeFilterBar: false });
            } else {
                console.error('Failed to fetch models:', data.error);
                renderError(data.error);
            }
        } catch (error) {
            console.error('Error fetching models:', error);
            renderError(error.message);
        } finally {
            state.loading = false;
        }
    }

    // =============================================================================
    // RENDERING
    // =============================================================================

    function render(options = {}) {
        renderKPI();
        if (options.includeFilterBar !== false) {
            renderFilterBar();
        }
        renderTable();
    }

    function renderKPI() {
        const container = document.querySelector(config.kpiContainerId);
        if (!container) return;

        const kpiData = [
            {
                id: 'total',
                icon: 'fa-cube',
                iconClass: 'total',
                label: 'Total Models',
                value: state.kpi.total
            },
            {
                id: 'deployed',
                icon: 'fa-rocket',
                iconClass: 'deployed',
                label: 'Deployed',
                value: state.kpi.deployed
            },
            {
                id: 'outdated',
                icon: 'fa-exclamation-triangle',
                iconClass: 'outdated',
                label: 'Outdated',
                value: state.kpi.outdated
            },
            {
                id: 'idle',
                icon: 'fa-pause-circle',
                iconClass: 'idle',
                label: 'Idle',
                value: state.kpi.idle
            },
            {
                id: 'scheduled',
                icon: 'fa-clock',
                iconClass: 'scheduled',
                label: 'Scheduled',
                value: state.kpi.scheduled
            }
        ];

        container.innerHTML = kpiData.map(item => `
            <div class="model-dashboard-models-kpi-card" data-kpi="${item.id}">
                <div class="model-dashboard-models-kpi-icon ${item.iconClass}">
                    <i class="fas ${item.icon}"></i>
                </div>
                <div class="model-dashboard-models-kpi-content">
                    <div class="model-dashboard-models-kpi-value">${item.value}</div>
                    <div class="model-dashboard-models-kpi-label">${item.label}</div>
                </div>
            </div>
        `).join('');
    }

    function renderFilterBar() {
        const container = document.querySelector(config.filterBarId);
        if (!container) return;

        container.innerHTML = `
            <div class="model-dashboard-models-filter-group">
                <label class="model-dashboard-models-filter-label">Model Type</label>
                <select class="model-dashboard-models-filter-select" id="modelsDashboardFilterType" onchange="ModelDashboardModels.setFilter('modelType', this.value)">
                    <option value="all" ${state.filters.modelType === 'all' ? 'selected' : ''}>All Types</option>
                    <option value="retrieval" ${state.filters.modelType === 'retrieval' ? 'selected' : ''}>Retrieval</option>
                    <option value="ranking" ${state.filters.modelType === 'ranking' ? 'selected' : ''}>Ranking</option>
                    <option value="multitask" ${state.filters.modelType === 'multitask' ? 'selected' : ''}>Multitask</option>
                </select>
            </div>
            <div class="model-dashboard-models-filter-group">
                <label class="model-dashboard-models-filter-label">Deployment</label>
                <select class="model-dashboard-models-filter-select" id="modelsDashboardFilterStatus" onchange="ModelDashboardModels.setFilter('status', this.value)">
                    <option value="all" ${state.filters.status === 'all' ? 'selected' : ''}>All</option>
                    <option value="deployed" ${state.filters.status === 'deployed' ? 'selected' : ''}>Deployed</option>
                    <option value="outdated" ${state.filters.status === 'outdated' ? 'selected' : ''}>Outdated</option>
                    <option value="idle" ${state.filters.status === 'idle' ? 'selected' : ''}>Idle</option>
                </select>
            </div>
            <div class="model-dashboard-models-filter-group">
                <label class="model-dashboard-models-filter-label">Sort By</label>
                <select class="model-dashboard-models-filter-select" id="modelsDashboardFilterSort" onchange="ModelDashboardModels.setFilter('sort', this.value)">
                    <option value="latest" ${state.filters.sort === 'latest' ? 'selected' : ''}>Latest</option>
                    <option value="oldest" ${state.filters.sort === 'oldest' ? 'selected' : ''}>Oldest</option>
                    <option value="best_metrics" ${state.filters.sort === 'best_metrics' ? 'selected' : ''}>Best Metrics</option>
                    <option value="name" ${state.filters.sort === 'name' ? 'selected' : ''}>Name A-Z</option>
                </select>
            </div>
            <div class="model-dashboard-models-filter-group model-dashboard-models-search-group">
                <label class="model-dashboard-models-filter-label">Search</label>
                <input type="text"
                       class="model-dashboard-models-search-input"
                       id="modelsDashboardSearchInput"
                       placeholder="Search models..."
                       value="${state.filters.search}"
                       oninput="ModelDashboardModels.handleSearch(this.value)">
            </div>
        `;
    }

    function renderTable() {
        const container = document.querySelector(config.tableContainerId);
        const emptyState = document.querySelector(config.emptyStateId);

        if (!container) return;

        if (state.models.length === 0) {
            container.style.display = 'none';
            if (emptyState) {
                emptyState.style.display = 'flex';
                emptyState.innerHTML = `
                    <div class="model-dashboard-models-empty-icon"><i class="fas fa-cube"></i></div>
                    <h3>No Registered Models</h3>
                    <p>Complete training runs with the Register component to register models in Vertex AI Model Registry.</p>
                `;
            }
            return;
        }

        container.style.display = 'block';
        if (emptyState) emptyState.style.display = 'none';

        container.innerHTML = `
            <div class="model-dashboard-models-table-container">
                <table class="model-dashboard-models-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Model Name</th>
                            <th>Type</th>
                            <th>Deployment</th>
                            <th>Version</th>
                            <th>Metrics</th>
                            <th>Age</th>
                            <th class="model-dashboard-models-actions-header">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${state.models.map((model, idx) => renderTableRow(model, idx)).join('')}
                    </tbody>
                </table>
            </div>
            ${renderPagination()}
        `;
    }

    function renderTableRow(model, idx) {
        const statusConfig = STATUS_CONFIG[model.model_status] || STATUS_CONFIG.idle;
        const typeConfig = TYPE_CONFIG[model.model_type] || TYPE_CONFIG.retrieval;
        const rowNum = (state.pagination.page - 1) * state.pagination.pageSize + idx + 1;
        const age = formatAge(model.registered_at);

        let metricsHtml = '';
        if (model.metrics) {
            if (model.model_type === 'ranking') {
                metricsHtml = `
                    <div class="model-dashboard-models-metric-item">
                        <span class="model-dashboard-models-metric-label">RMSE</span>
                        <span class="model-dashboard-models-metric-value">${formatMetric(model.metrics.rmse, 2)}</span>
                    </div>
                    <div class="model-dashboard-models-metric-item">
                        <span class="model-dashboard-models-metric-label">Test RMSE</span>
                        <span class="model-dashboard-models-metric-value">${formatMetric(model.metrics.test_rmse, 2)}</span>
                    </div>
                    <div class="model-dashboard-models-metric-item">
                        <span class="model-dashboard-models-metric-label">MAE</span>
                        <span class="model-dashboard-models-metric-value">${formatMetric(model.metrics.mae, 2)}</span>
                    </div>
                    <div class="model-dashboard-models-metric-item">
                        <span class="model-dashboard-models-metric-label">Test MAE</span>
                        <span class="model-dashboard-models-metric-value">${formatMetric(model.metrics.test_mae, 2)}</span>
                    </div>
                `;
            } else if (model.model_type === 'multitask') {
                metricsHtml = `
                    <div class="model-dashboard-models-metric-item">
                        <span class="model-dashboard-models-metric-label">R@50</span>
                        <span class="model-dashboard-models-metric-value">${formatMetricAsPercent(model.metrics.recall_at_50)}</span>
                    </div>
                    <div class="model-dashboard-models-metric-item">
                        <span class="model-dashboard-models-metric-label">R@100</span>
                        <span class="model-dashboard-models-metric-value">${formatMetricAsPercent(model.metrics.recall_at_100)}</span>
                    </div>
                    <div class="model-dashboard-models-metric-item">
                        <span class="model-dashboard-models-metric-label">RMSE</span>
                        <span class="model-dashboard-models-metric-value">${formatMetric(model.metrics.rmse, 2)}</span>
                    </div>
                    <div class="model-dashboard-models-metric-item">
                        <span class="model-dashboard-models-metric-label">Test RMSE</span>
                        <span class="model-dashboard-models-metric-value">${formatMetric(model.metrics.test_rmse, 2)}</span>
                    </div>
                `;
            } else {
                metricsHtml = `
                    <div class="model-dashboard-models-metric-item">
                        <span class="model-dashboard-models-metric-label">R@5</span>
                        <span class="model-dashboard-models-metric-value">${formatMetricAsPercent(model.metrics.recall_at_5)}</span>
                    </div>
                    <div class="model-dashboard-models-metric-item">
                        <span class="model-dashboard-models-metric-label">R@10</span>
                        <span class="model-dashboard-models-metric-value">${formatMetricAsPercent(model.metrics.recall_at_10)}</span>
                    </div>
                    <div class="model-dashboard-models-metric-item">
                        <span class="model-dashboard-models-metric-label">R@50</span>
                        <span class="model-dashboard-models-metric-value">${formatMetricAsPercent(model.metrics.recall_at_50)}</span>
                    </div>
                    <div class="model-dashboard-models-metric-item">
                        <span class="model-dashboard-models-metric-label">R@100</span>
                        <span class="model-dashboard-models-metric-value">${formatMetricAsPercent(model.metrics.recall_at_100)}</span>
                    </div>
                `;
            }
        }

        return `
            <tr data-model-id="${model.id}" onclick="ModelDashboardModels.viewDetails(${model.id})">
                <td>${rowNum}</td>
                <td>
                    <div class="model-dashboard-models-table-name">
                        <span class="model-dashboard-models-table-name-main">${model.vertex_model_name || 'Unnamed'}</span>
                        <span class="model-dashboard-models-table-name-sub">Run #${model.run_number}</span>
                    </div>
                </td>
                <td>
                    <span class="model-dashboard-models-type-badge ${model.model_type}">
                        <i class="fas ${typeConfig.icon}"></i>
                        ${typeConfig.label}
                    </span>
                </td>
                <td>
                    <span class="model-dashboard-models-status-badge ${statusConfig.class}">
                        <i class="fas ${statusConfig.icon}"></i>
                        ${statusConfig.label}
                    </span>
                </td>
                <td>
                    <span class="model-dashboard-models-version-badge">
                        <i class="fas fa-code-branch"></i>
                        v${model.vertex_model_version || '1'}
                    </span>
                </td>
                <td>
                    <div class="model-dashboard-models-metrics-cell">
                        ${metricsHtml || '<span style="color:#9ca3af;">-</span>'}
                    </div>
                </td>
                <td>
                    <span class="model-dashboard-models-age-badge ${age.class}">${age.text}</span>
                </td>
                <td class="model-dashboard-models-actions-cell" onclick="event.stopPropagation();">
                    ${renderActionButtons(model)}
                </td>
            </tr>
        `;
    }

    function renderActionButtons(model) {
        return `
            <div class="model-dashboard-models-actions">
                <button class="model-dashboard-models-action-btn view" onclick="ModelDashboardModels.viewDetails(${model.id})">
                    View
                </button>
            </div>
        `;
    }

    function generateShowingText(currentPage, totalItems, itemsPerPage) {
        if (totalItems === 0) return 'Showing 0';
        const start = (currentPage - 1) * itemsPerPage + 1;
        const end = Math.min(currentPage * itemsPerPage, totalItems);
        return `Showing ${start}-${end} of ${totalItems}`;
    }

    function generatePageButton(pageNum, currentPage) {
        if (pageNum === currentPage) {
            return `<button class="btn btn-primary btn-xs" style="background-color: #6b7280; color: #fff; border-color: #6b7280;">${pageNum}</button>`;
        }
        return `<button onclick="ModelDashboardModels.goToPage(${pageNum})" class="btn btn-secondary btn-xs">${pageNum}</button>`;
    }

    function generatePaginationControls(currentPage, totalPages) {
        const buttons = [];
        if (totalPages <= 4) {
            for (let i = 1; i <= totalPages; i++) {
                buttons.push(generatePageButton(i, currentPage));
            }
        } else {
            buttons.push(generatePageButton(1, currentPage));
            if (currentPage > 3) {
                buttons.push('<span class="px-1 text-gray-400">...</span>');
            }
            const start = Math.max(2, currentPage - 1);
            const end = Math.min(totalPages - 1, currentPage + 1);
            for (let i = start; i <= end; i++) {
                buttons.push(generatePageButton(i, currentPage));
            }
            if (currentPage < totalPages - 2) {
                buttons.push('<span class="px-1 text-gray-400">...</span>');
            }
            buttons.push(generatePageButton(totalPages, currentPage));
        }
        return buttons.join('');
    }

    function renderPagination() {
        if (state.pagination.totalPages <= 1) return '';

        const { page, totalPages, totalCount, pageSize, hasPrev, hasNext } = state.pagination;
        const showingText = generateShowingText(page, totalCount, pageSize);
        const pageButtons = generatePaginationControls(page, totalPages);

        return `
            <div class="flex items-center justify-between mt-4 pt-4 border-t border-gray-200">
                <div class="text-sm text-gray-600">${showingText}</div>
                <div class="flex items-center gap-2">
                    ${hasPrev ? `<button onclick="ModelDashboardModels.prevPage()" class="btn btn-secondary btn-xs">Previous</button>` : ''}
                    ${pageButtons}
                    ${hasNext ? `<button onclick="ModelDashboardModels.nextPage()" class="btn btn-secondary btn-xs">Next</button>` : ''}
                </div>
            </div>
        `;
    }

    function renderLoading() {
        const container = document.querySelector(config.tableContainerId);
        const emptyState = document.querySelector(config.emptyStateId);

        if (emptyState) emptyState.style.display = 'none';

        if (container) {
            container.style.display = 'block';
            container.innerHTML = `
                <div class="model-dashboard-models-loading">
                    <i class="fas fa-spinner fa-spin"></i>
                    <span>Loading models...</span>
                </div>
            `;
        }
    }

    function renderError(message) {
        const container = document.querySelector(config.tableContainerId);
        if (container) {
            container.innerHTML = `
                <div class="model-dashboard-models-empty-state">
                    <div class="model-dashboard-models-empty-icon"><i class="fas fa-exclamation-triangle" style="color: #ef4444;"></i></div>
                    <h3>Error Loading Models</h3>
                    <p>${message || 'An error occurred while loading models.'}</p>
                    <button class="model-dashboard-models-retry-btn" onclick="ModelDashboardModels.refresh()">
                        <i class="fas fa-sync-alt"></i> Retry
                    </button>
                </div>
            `;
        }
    }

    // =============================================================================
    // EVENT HANDLERS
    // =============================================================================

    function handleSearch(value) {
        if (state.searchDebounceTimer) {
            clearTimeout(state.searchDebounceTimer);
        }
        state.searchDebounceTimer = setTimeout(() => {
            state.filters.search = value;
            state.pagination.page = 1;
            fetchModels();
        }, 300);
    }

    // =============================================================================
    // ACTIONS
    // =============================================================================

    function viewDetails(modelId) {
        if (typeof ExpViewModal !== 'undefined') {
            ExpViewModal.openForModel(modelId);
        }
    }

    // =============================================================================
    // FILTER & PAGINATION
    // =============================================================================

    function setFilter(key, value) {
        state.filters[key] = value;
        state.pagination.page = 1;
        fetchModels();
    }

    function nextPage() {
        if (state.pagination.hasNext) {
            state.pagination.page++;
            fetchModels();
        }
    }

    function prevPage() {
        if (state.pagination.hasPrev) {
            state.pagination.page--;
            fetchModels();
        }
    }

    function goToPage(page) {
        if (page >= 1 && page <= state.pagination.totalPages) {
            state.pagination.page = page;
            fetchModels();
        }
    }

    // =============================================================================
    // CALENDAR
    // =============================================================================

    function initCalendar() {
        if (typeof ScheduleCalendar !== 'undefined' && document.querySelector(config.calendarContainerId)) {
            ScheduleCalendar.init(config.calendarContainerId, {
                onRunClick: (runId) => {
                    if (typeof ExpViewModal !== 'undefined') {
                        ExpViewModal.openForTrainingRun(runId);
                    }
                }
            });
            ScheduleCalendar.load();
        }
    }

    // =============================================================================
    // PUBLIC API
    // =============================================================================

    function init(options = {}) {
        if (options.containerId) config.containerId = options.containerId;
        if (options.kpiContainerId) config.kpiContainerId = options.kpiContainerId;
        if (options.calendarContainerId) config.calendarContainerId = options.calendarContainerId;
        if (options.filterBarId) config.filterBarId = options.filterBarId;
        if (options.tableContainerId) config.tableContainerId = options.tableContainerId;
        if (options.emptyStateId) config.emptyStateId = options.emptyStateId;

        state.initialized = true;
        return ModelDashboardModels;
    }

    function load() {
        if (!state.initialized) {
            init();
        }

        renderFilterBar();
        fetchModels();
        initCalendar();
    }

    function refresh() {
        fetchModels();
    }

    // Expose public API
    return {
        init,
        load,
        refresh,
        setFilter,
        handleSearch,
        viewDetails,
        nextPage,
        prevPage,
        goToPage
    };

})();
