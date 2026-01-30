/**
 * Models Registry Module
 *
 * Manages the Models Registry chapter on the Training page.
 * Displays registered models from Vertex AI Model Registry with
 * filtering, search, and actions (deploy/undeploy).
 *
 * Usage:
 *     ModelsRegistry.init({
 *         containerId: '#modelsRegistryContainer',
 *         onModelClick: function(modelId) { ... }
 *     });
 *     ModelsRegistry.load();
 */

const ModelsRegistry = (function() {
    'use strict';

    // =============================================================================
    // CONFIGURATION & STATE
    // =============================================================================

    const config = {
        containerId: null,
        kpiContainerId: null,
        calendarContainerId: null,
        filterBarId: null,
        tableContainerId: null,
        emptyStateId: null,
        endpoints: {
            list: '/api/models/',
            detail: '/api/models/{id}/',
            deploy: '/api/models/{id}/deploy/',
            undeploy: '/api/models/{id}/undeploy/',
            delete: '/api/models/{id}/delete/',
        },
        onModelClick: null,
        onViewDetails: null
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
        searchDebounceTimer: null
    };

    // Deployment status badge configurations
    // Three states: deployed (latest on endpoint), outdated (older version deployed), idle (none deployed)
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

    function buildUrl(template, params) {
        let url = template;
        for (const [key, value] of Object.entries(params)) {
            url = url.replace(`{${key}}`, value);
        }
        return url;
    }

    function formatDate(isoStr) {
        if (!isoStr) return '-';
        const d = new Date(isoStr);
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    }

    function formatAge(isoStr) {
        if (!isoStr) return { text: '-', class: '' };
        const registered = new Date(isoStr);
        const now = new Date();

        // Compare calendar dates (normalized to local midnight), not elapsed time
        // This ensures Jan 26 -> Jan 27 = 1 day, regardless of time of day
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

    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
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
                    pageSize: data.pagination?.page_size || 10,
                    totalCount: data.pagination?.total_count || 0,
                    totalPages: data.pagination?.total_pages || 1,
                    hasNext: data.pagination?.has_next || false,
                    hasPrev: data.pagination?.has_prev || false
                };
                // Don't re-render filter bar on refresh to preserve search input focus
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

    async function deployModel(modelId) {
        try {
            const response = await fetch(buildUrl(config.endpoints.deploy, { id: modelId }), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });
            const data = await response.json();

            if (data.success) {
                showToast('Model deployment started', 'success');
                fetchModels();
            } else {
                showToast(data.error || 'Failed to deploy model', 'error');
            }
        } catch (error) {
            console.error('Error deploying model:', error);
            showToast('Failed to deploy model', 'error');
        }
    }

    async function undeployModel(modelId) {
        try {
            const response = await fetch(buildUrl(config.endpoints.undeploy, { id: modelId }), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });
            const data = await response.json();

            if (data.success) {
                showToast('Model undeployed successfully', 'success');
                fetchModels();
            } else {
                showToast(data.error || 'Failed to undeploy model', 'error');
            }
        } catch (error) {
            console.error('Error undeploying model:', error);
            showToast('Failed to undeploy model', 'error');
        }
    }

    // =============================================================================
    // RENDERING
    // =============================================================================

    function render(options = {}) {
        renderKPI();
        // Only render filter bar on initial load, not on every refresh
        // This prevents the search input from losing focus while typing
        if (options.includeFilterBar !== false) {
            renderFilterBar();
        }
        renderTable();
    }

    function renderKPI() {
        const container = document.querySelector(config.kpiContainerId);
        if (!container) return;

        container.innerHTML = `
            <div class="models-kpi-card">
                <div class="models-kpi-value">${state.kpi.total}</div>
                <div class="models-kpi-label">Total Models</div>
            </div>
            <div class="models-kpi-card">
                <div class="models-kpi-value highlight-green">${state.kpi.deployed}</div>
                <div class="models-kpi-label">Deployed</div>
            </div>
            <div class="models-kpi-card">
                <div class="models-kpi-value highlight-orange">${state.kpi.outdated}</div>
                <div class="models-kpi-label">Outdated</div>
            </div>
            <div class="models-kpi-card">
                <div class="models-kpi-value highlight-blue">${state.kpi.idle}</div>
                <div class="models-kpi-label">Idle</div>
            </div>
            <div class="models-kpi-card">
                <div class="models-kpi-value highlight-orange">${state.kpi.scheduled}</div>
                <div class="models-kpi-label">Scheduled</div>
            </div>
        `;
    }

    function renderFilterBar() {
        const container = document.querySelector(config.filterBarId);
        if (!container) return;

        container.innerHTML = `
            <div class="models-filter-group">
                <label class="models-filter-label">Model Type</label>
                <select class="models-filter-select" id="modelsFilterType" onchange="ModelsRegistry.setFilter('modelType', this.value)">
                    <option value="all" ${state.filters.modelType === 'all' ? 'selected' : ''}>All Types</option>
                    <option value="retrieval" ${state.filters.modelType === 'retrieval' ? 'selected' : ''}>Retrieval</option>
                    <option value="ranking" ${state.filters.modelType === 'ranking' ? 'selected' : ''}>Ranking</option>
                    <option value="multitask" ${state.filters.modelType === 'multitask' ? 'selected' : ''}>Multitask</option>
                </select>
            </div>
            <div class="models-filter-group">
                <label class="models-filter-label">Deployment</label>
                <select class="models-filter-select" id="modelsFilterStatus" onchange="ModelsRegistry.setFilter('status', this.value)">
                    <option value="all" ${state.filters.status === 'all' ? 'selected' : ''}>All</option>
                    <option value="deployed" ${state.filters.status === 'deployed' ? 'selected' : ''}>Deployed</option>
                    <option value="outdated" ${state.filters.status === 'outdated' ? 'selected' : ''}>Outdated</option>
                    <option value="idle" ${state.filters.status === 'idle' ? 'selected' : ''}>Idle</option>
                </select>
            </div>
            <div class="models-filter-group">
                <label class="models-filter-label">Sort By</label>
                <select class="models-filter-select" id="modelsFilterSort" onchange="ModelsRegistry.setFilter('sort', this.value)">
                    <option value="latest" ${state.filters.sort === 'latest' ? 'selected' : ''}>Latest</option>
                    <option value="oldest" ${state.filters.sort === 'oldest' ? 'selected' : ''}>Oldest</option>
                    <option value="best_metrics" ${state.filters.sort === 'best_metrics' ? 'selected' : ''}>Best Metrics</option>
                    <option value="name" ${state.filters.sort === 'name' ? 'selected' : ''}>Name A-Z</option>
                </select>
            </div>
            <div class="models-filter-group" style="flex: 1;">
                <label class="models-filter-label">Search</label>
                <input type="text"
                       class="models-search-input"
                       id="modelsSearchInput"
                       placeholder="Search models..."
                       value="${state.filters.search}"
                       oninput="ModelsRegistry.handleSearch(this.value)">
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
                    <div class="empty-icon"><i class="fas fa-cube"></i></div>
                    <h3>No Registered Models</h3>
                    <p>Complete training runs with the Register component to register models in Vertex AI Model Registry.</p>
                `;
            }
            return;
        }

        container.style.display = 'block';
        if (emptyState) emptyState.style.display = 'none';

        container.innerHTML = `
            <div class="models-table-container">
                <table class="models-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Model Name</th>
                            <th>Type</th>
                            <th>Deployment</th>
                            <th>Schedule</th>
                            <th>Version</th>
                            <th>Metrics</th>
                            <th>Age</th>
                            <th class="models-actions-header">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${state.models.map((model, idx) => renderTableRow(model, idx)).join('')}
                    </tbody>
                </table>
            </div>
            ${renderPagination()}
        `;

        // Attach event listeners
        attachTableEventListeners();
    }

    function renderTableRow(model, idx) {
        const statusConfig = STATUS_CONFIG[model.model_status] || STATUS_CONFIG.idle;
        const typeConfig = TYPE_CONFIG[model.model_type] || TYPE_CONFIG.retrieval;
        const rowNum = (state.pagination.page - 1) * state.pagination.pageSize + idx + 1;
        const age = formatAge(model.registered_at);

        // Get metrics for display based on model type
        // - Retrieval: R@5, R@10, R@50, R@100
        // - Ranking: RMSE, Test RMSE, MAE, Test MAE
        // - Multitask/Hybrid: R@50, R@100, RMSE, Test RMSE
        let metricsHtml = '';
        if (model.metrics) {
            if (model.model_type === 'ranking') {
                metricsHtml = `
                    <div class="models-metric-item">
                        <span class="models-metric-label">RMSE</span>
                        <span class="models-metric-value">${formatMetric(model.metrics.rmse, 2)}</span>
                    </div>
                    <div class="models-metric-item">
                        <span class="models-metric-label">Test RMSE</span>
                        <span class="models-metric-value">${formatMetric(model.metrics.test_rmse, 2)}</span>
                    </div>
                    <div class="models-metric-item">
                        <span class="models-metric-label">MAE</span>
                        <span class="models-metric-value">${formatMetric(model.metrics.mae, 2)}</span>
                    </div>
                    <div class="models-metric-item">
                        <span class="models-metric-label">Test MAE</span>
                        <span class="models-metric-value">${formatMetric(model.metrics.test_mae, 2)}</span>
                    </div>
                `;
            } else if (model.model_type === 'multitask') {
                // Hybrid/Multitask: R@50, R@100, RMSE, Test RMSE
                metricsHtml = `
                    <div class="models-metric-item">
                        <span class="models-metric-label">R@50</span>
                        <span class="models-metric-value">${formatMetricAsPercent(model.metrics.recall_at_50)}</span>
                    </div>
                    <div class="models-metric-item">
                        <span class="models-metric-label">R@100</span>
                        <span class="models-metric-value">${formatMetricAsPercent(model.metrics.recall_at_100)}</span>
                    </div>
                    <div class="models-metric-item">
                        <span class="models-metric-label">RMSE</span>
                        <span class="models-metric-value">${formatMetric(model.metrics.rmse, 2)}</span>
                    </div>
                    <div class="models-metric-item">
                        <span class="models-metric-label">Test RMSE</span>
                        <span class="models-metric-value">${formatMetric(model.metrics.test_rmse, 2)}</span>
                    </div>
                `;
            } else {
                // Retrieval: R@5, R@10, R@50, R@100
                metricsHtml = `
                    <div class="models-metric-item">
                        <span class="models-metric-label">R@5</span>
                        <span class="models-metric-value">${formatMetricAsPercent(model.metrics.recall_at_5)}</span>
                    </div>
                    <div class="models-metric-item">
                        <span class="models-metric-label">R@10</span>
                        <span class="models-metric-value">${formatMetricAsPercent(model.metrics.recall_at_10)}</span>
                    </div>
                    <div class="models-metric-item">
                        <span class="models-metric-label">R@50</span>
                        <span class="models-metric-value">${formatMetricAsPercent(model.metrics.recall_at_50)}</span>
                    </div>
                    <div class="models-metric-item">
                        <span class="models-metric-label">R@100</span>
                        <span class="models-metric-value">${formatMetricAsPercent(model.metrics.recall_at_100)}</span>
                    </div>
                `;
            }
        }

        return `
            <tr data-model-id="${model.id}" onclick="ModelsRegistry.handleRowClick(event, ${model.id})">
                <td>${rowNum}</td>
                <td>
                    <div class="models-table-name">
                        <span class="models-table-name-main">${model.vertex_model_name || 'Unnamed'}</span>
                        <span class="models-table-name-sub">Run #${model.run_number}</span>
                    </div>
                </td>
                <td>
                    <span class="models-type-badge ${model.model_type}">
                        <i class="fas ${typeConfig.icon}"></i>
                        ${typeConfig.label}
                    </span>
                </td>
                <td>
                    <span class="models-status-badge ${statusConfig.class}">
                        <i class="fas ${statusConfig.icon}"></i>
                        ${statusConfig.label}
                    </span>
                </td>
                <td>
                    ${model.has_schedule ? `
                        <span class="models-schedule-badge ${model.schedule_status === 'active' ? 'active' : 'paused'}">
                            <i class="fas ${model.schedule_status === 'active' ? 'fa-clock' : 'fa-pause'}"></i>
                            ${model.schedule_status === 'active' ? 'Scheduled' : 'Paused'}
                        </span>
                    ` : `
                        <span class="models-schedule-badge none">
                            <i class="fas fa-minus"></i>
                            None
                        </span>
                    `}
                </td>
                <td>
                    <span class="models-version-badge">
                        <i class="fas fa-code-branch"></i>
                        v${model.vertex_model_version || '1'}
                    </span>
                </td>
                <td>
                    <div class="models-metrics-cell">
                        ${metricsHtml || '<span style="color:#9ca3af;">-</span>'}
                    </div>
                </td>
                <td>
                    <span class="models-age-badge ${age.class}">${age.text}</span>
                </td>
                <td class="models-actions-cell" onclick="event.stopPropagation();">
                    ${renderActionButtons(model)}
                </td>
            </tr>
        `;
    }

    function renderActionButtons(model) {
        const isDeployed = model.model_status === 'deployed';
        const hasSchedule = model.has_schedule;

        return `
            <div class="ml-card-col-actions">
                <div class="ml-card-actions-grid">
                    <!-- Row 1: Deploy | View -->
                    <button class="card-action-btn deploy"
                            onclick="${isDeployed ? `ModelsRegistry.undeploy(${model.id})` : `ModelsRegistry.deploy(${model.id})`}">
                        ${isDeployed ? 'Undeploy' : 'Deploy'}
                    </button>
                    <button class="card-action-btn view" onclick="ModelsRegistry.viewDetails(${model.id})">
                        View
                    </button>

                    <!-- Row 2: Schedule | Delete -->
                    <button class="card-action-btn schedule"
                            onclick="${hasSchedule ? `ModelsRegistry.viewSchedule(${model.schedule_id})` : `ModelsRegistry.createSchedule(${model.id})`}">
                        Schedule
                    </button>
                    <button class="card-action-btn icon-only delete" onclick="ModelsRegistry.confirmDelete(${model.id})" title="Delete">
                        <i class="fas fa-trash-alt"></i>
                    </button>
                </div>
            </div>
        `;
    }

    function generateShowingText(currentPage, totalItems, itemsPerPage) {
        if (totalItems === 0) return 'Showing 0 models';
        const start = (currentPage - 1) * itemsPerPage + 1;
        const end = Math.min(currentPage * itemsPerPage, totalItems);
        return `Showing ${start}-${end} of ${totalItems} models`;
    }

    function generatePageButton(pageNum, currentPage) {
        const isActive = pageNum === currentPage;
        if (isActive) {
            return `<button class="w-8 h-8 flex items-center justify-center rounded-md text-sm font-medium bg-blue-600 text-white">${pageNum}</button>`;
        }
        return `<button onclick="ModelsRegistry.goToPage(${pageNum})" class="w-8 h-8 flex items-center justify-center rounded-md text-sm font-medium border border-gray-300 hover:bg-blue-50 text-gray-700">${pageNum}</button>`;
    }

    function generatePaginationControls(currentPage, totalPages) {
        const buttons = [];
        if (totalPages <= 7) {
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
            <div class="flex flex-col sm:flex-row items-center justify-between mt-4 pt-4 border-t border-gray-200 gap-2">
                <div class="text-sm text-gray-600">${showingText}</div>
                <div class="flex items-center gap-1">
                    <button onclick="ModelsRegistry.prevPage()" ${!hasPrev ? 'disabled' : ''} class="px-3 py-1.5 border rounded-md text-sm font-medium ${hasPrev ? 'border-gray-300 hover:bg-blue-50 text-gray-700' : 'border-gray-200 text-gray-400 cursor-not-allowed'}">
                        Previous
                    </button>
                    <div class="flex items-center gap-1 mx-2">
                        ${pageButtons}
                    </div>
                    <button onclick="ModelsRegistry.nextPage()" ${!hasNext ? 'disabled' : ''} class="px-3 py-1.5 border rounded-md text-sm font-medium ${hasNext ? 'border-gray-300 hover:bg-blue-50 text-gray-700' : 'border-gray-200 text-gray-400 cursor-not-allowed'}">
                        Next
                    </button>
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
                <div class="models-loading">
                    <i class="fas fa-spinner fa-spin"></i>
                    <span class="models-loading-text">Loading models...</span>
                </div>
            `;
        }
    }

    function renderError(message) {
        const container = document.querySelector(config.tableContainerId);
        if (container) {
            container.innerHTML = `
                <div class="models-empty-state">
                    <div class="empty-icon"><i class="fas fa-exclamation-triangle" style="color: #ef4444;"></i></div>
                    <h3>Error Loading Models</h3>
                    <p>${message || 'An error occurred while loading models.'}</p>
                    <button class="btn btn-primary" onclick="ModelsRegistry.refresh()">
                        <i class="fas fa-sync-alt"></i> Retry
                    </button>
                </div>
            `;
        }
    }

    // =============================================================================
    // EVENT HANDLERS
    // =============================================================================

    function attachTableEventListeners() {
        // No additional event listeners needed for inline buttons
    }

    function handleRowClick(e, modelId) {
        // Don't trigger row click if clicking on action buttons
        if (e.target.closest('.models-action-buttons')) return;

        if (config.onModelClick) {
            config.onModelClick(modelId);
        } else {
            viewDetails(modelId);
        }
    }

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
        if (config.onViewDetails) {
            config.onViewDetails(modelId);
        } else if (typeof ExpViewModal !== 'undefined') {
            ExpViewModal.openForModel(modelId);
        }
    }

    function viewVersions(modelId) {
        if (config.onViewDetails) {
            config.onViewDetails(modelId, 'versions');
        } else if (typeof ExpViewModal !== 'undefined') {
            ExpViewModal.openForModel(modelId, { tab: 'versions' });
        }
    }

    function deploy(modelId) {
        // Use the DeployWizard modal instead of confirm dialog
        if (typeof DeployWizard !== 'undefined') {
            DeployWizard.open(modelId);
        } else {
            // Fallback to simple confirm if DeployWizard is not available
            if (confirm('Are you sure you want to deploy this model?')) {
                deployModel(modelId);
            }
        }
    }

    function undeploy(modelId) {
        if (confirm('Are you sure you want to undeploy this model? It will no longer serve predictions.')) {
            undeployModel(modelId);
        }
    }

    function copyArtifactUrl(modelId) {
        const model = state.models.find(m => m.id === modelId);
        if (model && model.vertex_model_resource_name) {
            navigator.clipboard.writeText(model.vertex_model_resource_name).then(() => {
                showToast('Artifact URL copied to clipboard', 'success');
            }).catch(() => {
                showToast('Failed to copy URL', 'error');
            });
        }
    }

    function createSchedule(modelId) {
        // Use ScheduleModal to create a schedule for this model's training run
        if (typeof ScheduleModal !== 'undefined') {
            ScheduleModal.configure({
                onSuccess: function(schedule) {
                    showToast(`Schedule "${schedule.name}" created successfully`, 'success');
                    fetchModels();
                }
            });
            ScheduleModal.openForTrainingRun(modelId);
        } else {
            showToast('Schedule modal not available', 'error');
        }
    }

    function viewSchedule(scheduleId) {
        // Navigate to training schedules chapter or open schedule detail modal
        if (typeof TrainingSchedules !== 'undefined' && TrainingSchedules.viewSchedule) {
            TrainingSchedules.viewSchedule(scheduleId);
        } else {
            // Fallback: scroll to schedules section
            const schedulesSection = document.querySelector('#trainingSchedulesChapter');
            if (schedulesSection) {
                schedulesSection.scrollIntoView({ behavior: 'smooth' });
            }
        }
    }

    function openInVertexAI(modelId) {
        const model = state.models.find(m => m.id === modelId);
        if (model && model.vertex_model_resource_name) {
            // Parse resource name: projects/{project}/locations/{location}/models/{model_id}
            const parts = model.vertex_model_resource_name.split('/');
            if (parts.length >= 6) {
                const project = parts[1];
                const location = parts[3];
                const vertexModelId = parts[5];
                const url = `https://console.cloud.google.com/vertex-ai/models/${vertexModelId}?project=${project}`;
                window.open(url, '_blank');
            }
        }
    }

    function confirmDelete(modelId) {
        const model = state.models.find(m => m.id === modelId);
        if (!model) return;

        const modelName = model.vertex_model_name || 'Unnamed Model';

        if (typeof TrainingCards !== 'undefined' && TrainingCards.showConfirmModal) {
            TrainingCards.showConfirmModal({
                title: 'Delete Model',
                message: `Are you sure you want to delete "<strong>${modelName}</strong>"?<br><br>This will remove the model from Vertex AI Model Registry.<br><strong>This action cannot be undone.</strong>`,
                confirmText: 'Confirm',
                cancelText: 'Cancel',
                type: 'danger',
                confirmButtonClass: 'btn-neu-save',
                cancelButtonClass: 'btn-neu-cancel',
                onConfirm: () => {
                    deleteModel(modelId);
                }
            });
        } else {
            // Fallback to native confirm if TrainingCards not available
            if (confirm(`Are you sure you want to delete "${modelName}"?\n\nThis will remove the model from Vertex AI Model Registry. This action cannot be undone.`)) {
                deleteModel(modelId);
            }
        }
    }

    async function deleteModel(modelId) {
        try {
            const response = await fetch(buildUrl(config.endpoints.delete, { id: modelId }), {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });
            const data = await response.json();

            if (data.success) {
                showToast('Model deleted successfully', 'success');
                fetchModels();
            } else {
                showToast(data.error || 'Failed to delete model', 'error');
            }
        } catch (error) {
            console.error('Error deleting model:', error);
            showToast('Failed to delete model', 'error');
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

    function refresh() {
        fetchModels();
    }

    // =============================================================================
    // NOTIFICATIONS
    // =============================================================================

    // Use the TrainingCards modal for consistent UI
    function showToast(message, type = 'info') {
        if (typeof TrainingCards !== 'undefined' && TrainingCards.showConfirmModal) {
            TrainingCards.showConfirmModal({
                title: type === 'success' ? 'Success' : type === 'error' ? 'Error' : 'Info',
                message: message,
                type: type === 'success' ? 'success' : type === 'error' ? 'danger' : 'info',
                confirmText: 'Close',
                hideCancel: true,
                autoClose: type === 'success' || type === 'info' ? 4000 : 0,
                onConfirm: () => {}
            });
        } else {
            alert(message);
        }
    }

    // =============================================================================
    // PUBLIC API
    // =============================================================================

    function init(options = {}) {
        config.containerId = options.containerId || '#modelsRegistry';
        config.kpiContainerId = options.kpiContainerId || '#modelsKpiSummary';
        config.calendarContainerId = options.calendarContainerId || '#modelsScheduleGrid';
        config.filterBarId = options.filterBarId || '#modelsFilterBar';
        config.tableContainerId = options.tableContainerId || '#modelsTable';
        config.emptyStateId = options.emptyStateId || '#modelsEmptyState';

        if (options.onModelClick) config.onModelClick = options.onModelClick;
        if (options.onViewDetails) config.onViewDetails = options.onViewDetails;
        if (options.endpoints) {
            Object.assign(config.endpoints, options.endpoints);
        }

        return ModelsRegistry;
    }

    function load() {
        // Render filter bar once on initial load
        renderFilterBar();
        fetchModels();

        // Initialize calendar if container exists
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

    // Expose public API
    return {
        init,
        load,
        refresh,
        setFilter,
        handleSearch,
        handleRowClick,
        viewDetails,
        viewVersions,
        deploy,
        undeploy,
        confirmDelete,
        copyArtifactUrl,
        openInVertexAI,
        createSchedule,
        viewSchedule,
        nextPage,
        prevPage,
        goToPage
    };

})();
