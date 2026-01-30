/**
 * Endpoints Table Module
 *
 * Manages the Serving Endpoints chapter on the Deployment page.
 * Displays deployed ML serving endpoints (Cloud Run services ending with '-serving')
 * with filtering, search, and actions (test, copy URL, view logs, undeploy).
 *
 * Usage:
 *     EndpointsTable.init({
 *         containerId: '#endpointsChapter',
 *         onEndpointClick: function(endpointId) { ... }
 *     });
 *     EndpointsTable.load();
 */

const EndpointsTable = (function() {
    'use strict';

    // =============================================================================
    // CONFIGURATION & STATE
    // =============================================================================

    const config = {
        containerId: null,
        kpiContainerId: null,
        filterBarId: null,
        tableContainerId: null,
        emptyStateId: null,
        endpoints: {
            list: '/api/deployed-endpoints/',
            detail: '/api/deployed-endpoints/{id}/',
            undeploy: '/api/deployed-endpoints/{id}/undeploy/',
        },
        // Cloud Run logs URL pattern
        logsUrlPattern: 'https://console.cloud.google.com/run/detail/{region}/{service}/logs?project={project}',
        region: 'europe-central2',
        project: 'b2b-recs',
        onEndpointClick: null,
        onViewDetails: null
    };

    let state = {
        endpoints: [],
        modelNames: [],
        kpi: { total: 0, active: 0, inactive: 0, last_updated: null },
        pagination: { page: 1, pageSize: 10, totalCount: 0, totalPages: 1 },
        filters: {
            modelType: 'all',
            status: 'active',  // Default to showing active endpoints
            modelName: 'all',
            search: ''
        },
        kpiFilter: 'active',  // Track which KPI card is selected ('all', 'active', 'inactive')
        loading: false,
        searchDebounceTimer: null
    };

    // Status badge configurations
    const STATUS_CONFIG = {
        active: { icon: 'fa-check-circle', label: 'Active', class: 'active' },
        inactive: { icon: 'fa-times-circle', label: 'Inactive', class: 'inactive' }
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

    function formatDateTime(isoStr) {
        if (!isoStr) return '-';
        const d = new Date(isoStr);
        return d.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    function formatRelativeTime(isoStr) {
        if (!isoStr) return '-';
        const d = new Date(isoStr);
        const now = new Date();
        const diffMs = now - d;
        const diffMins = Math.floor(diffMs / (1000 * 60));
        const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays === 1) return 'Yesterday';
        if (diffDays < 7) return `${diffDays}d ago`;
        return formatDate(isoStr);
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

    function truncateUrl(url, maxLength = 40) {
        if (!url) return '-';
        if (url.length <= maxLength) return url;
        // Remove https:// prefix for display
        let display = url.replace(/^https?:\/\//, '');
        if (display.length <= maxLength) return display;
        return display.substring(0, maxLength - 3) + '...';
    }

    function formatConfig(config) {
        if (!config) return '-';
        const parts = [];
        if (config.cpu) parts.push(`${config.cpu} CPU`);
        if (config.memory) parts.push(config.memory);
        return parts.join(', ') || '-';
    }

    // =============================================================================
    // API CALLS
    // =============================================================================

    async function fetchEndpoints() {
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
            if (state.filters.modelName !== 'all') {
                params.append('model_name', state.filters.modelName);
            }
            if (state.filters.search) {
                params.append('search', state.filters.search);
            }

            const response = await fetch(`${config.endpoints.list}?${params.toString()}`);
            const data = await response.json();

            if (data.success) {
                state.endpoints = data.endpoints || [];
                state.kpi = data.kpi || state.kpi;
                state.modelNames = data.model_names || [];
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
                console.error('Failed to fetch endpoints:', data.error);
                renderError(data.error);
            }
        } catch (error) {
            console.error('Error fetching endpoints:', error);
            renderError(error.message);
        } finally {
            state.loading = false;
        }
    }

    async function undeployEndpoint(endpointId) {
        try {
            const response = await fetch(buildUrl(config.endpoints.undeploy, { id: endpointId }), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });
            const data = await response.json();

            if (data.success) {
                showToast('Endpoint undeployed successfully', 'success');
                fetchEndpoints();
            } else {
                showToast(data.error || 'Failed to undeploy endpoint', 'error');
            }
        } catch (error) {
            console.error('Error undeploying endpoint:', error);
            showToast('Failed to undeploy endpoint', 'error');
        }
    }

    // =============================================================================
    // RENDERING
    // =============================================================================

    function render(options = {}) {
        renderKPI();
        // Only render filter bar on initial load, not on every refresh
        if (options.includeFilterBar !== false) {
            renderFilterBar();
        }
        renderTable();
    }

    function renderKPI() {
        const container = document.querySelector(config.kpiContainerId);
        if (!container) return;

        container.innerHTML = `
            <div class="endpoints-kpi-card clickable ${state.kpiFilter === 'all' ? 'selected' : ''}" onclick="EndpointsTable.setKpiFilter('all')">
                <div class="endpoints-kpi-value">${state.kpi.total}</div>
                <div class="endpoints-kpi-label">Total Endpoints</div>
            </div>
            <div class="endpoints-kpi-card clickable ${state.kpiFilter === 'active' ? 'selected' : ''}" onclick="EndpointsTable.setKpiFilter('active')">
                <div class="endpoints-kpi-value highlight-green">${state.kpi.active}</div>
                <div class="endpoints-kpi-label">Active</div>
            </div>
            <div class="endpoints-kpi-card clickable ${state.kpiFilter === 'inactive' ? 'selected' : ''}" onclick="EndpointsTable.setKpiFilter('inactive')">
                <div class="endpoints-kpi-value highlight-red">${state.kpi.inactive}</div>
                <div class="endpoints-kpi-label">Inactive</div>
            </div>
            <div class="endpoints-kpi-card">
                <div class="endpoints-kpi-value highlight-blue" style="font-size: 14px;">${formatRelativeTime(state.kpi.last_updated)}</div>
                <div class="endpoints-kpi-label">Last Updated</div>
            </div>
        `;
    }

    function renderFilterBar() {
        const container = document.querySelector(config.filterBarId);
        if (!container) return;

        // Build model names options
        const modelNameOptions = state.modelNames.map(name =>
            `<option value="${name}" ${state.filters.modelName === name ? 'selected' : ''}>${name}</option>`
        ).join('');

        container.innerHTML = `
            <div class="endpoints-filter-group">
                <label class="endpoints-filter-label">Model Type</label>
                <select class="endpoints-filter-select" id="endpointsFilterType" onchange="EndpointsTable.setFilter('modelType', this.value)">
                    <option value="all" ${state.filters.modelType === 'all' ? 'selected' : ''}>All Types</option>
                    <option value="retrieval" ${state.filters.modelType === 'retrieval' ? 'selected' : ''}>Retrieval</option>
                    <option value="ranking" ${state.filters.modelType === 'ranking' ? 'selected' : ''}>Ranking</option>
                    <option value="multitask" ${state.filters.modelType === 'multitask' ? 'selected' : ''}>Multitask</option>
                </select>
            </div>
            <div class="endpoints-filter-group">
                <label class="endpoints-filter-label">Status</label>
                <select class="endpoints-filter-select" id="endpointsFilterStatus" onchange="EndpointsTable.setFilter('status', this.value)">
                    <option value="all" ${state.filters.status === 'all' ? 'selected' : ''}>All</option>
                    <option value="active" ${state.filters.status === 'active' ? 'selected' : ''}>Active</option>
                    <option value="inactive" ${state.filters.status === 'inactive' ? 'selected' : ''}>Inactive</option>
                </select>
            </div>
            <div class="endpoints-filter-group">
                <label class="endpoints-filter-label">Model Name</label>
                <select class="endpoints-filter-select" id="endpointsFilterModelName" onchange="EndpointsTable.setFilter('modelName', this.value)">
                    <option value="all" ${state.filters.modelName === 'all' ? 'selected' : ''}>All Models</option>
                    ${modelNameOptions}
                </select>
            </div>
            <div class="endpoints-filter-group" style="flex: 1;">
                <label class="endpoints-filter-label">Search</label>
                <input type="text"
                       class="endpoints-search-input"
                       id="endpointsSearchInput"
                       placeholder="Search endpoints..."
                       value="${state.filters.search}"
                       oninput="EndpointsTable.handleSearch(this.value)">
            </div>
            <button class="endpoints-refresh-btn" onclick="EndpointsTable.refresh()" title="Refresh">
                <i class="fas fa-sync-alt"></i>
            </button>
        `;
    }

    function renderTable() {
        const container = document.querySelector(config.tableContainerId);
        const emptyState = document.querySelector(config.emptyStateId);

        if (!container) return;

        if (state.endpoints.length === 0) {
            container.style.display = 'none';
            if (emptyState) {
                emptyState.style.display = 'flex';
                emptyState.innerHTML = `
                    <div class="empty-icon"><i class="fas fa-server"></i></div>
                    <h3>No Deployed Endpoints</h3>
                    <p>Deploy models from the Training page to create serving endpoints.</p>
                `;
            }
            return;
        }

        container.style.display = 'block';
        if (emptyState) emptyState.style.display = 'none';

        container.innerHTML = `
            <div class="endpoints-table-container">
                <table class="endpoints-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Endpoint Name</th>
                            <th>Model</th>
                            <th>Version</th>
                            <th>URL</th>
                            <th>Config</th>
                            <th>Status</th>
                            <th>Last Updated</th>
                            <th class="endpoints-actions-header">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${state.endpoints.map((endpoint, idx) => renderTableRow(endpoint, idx)).join('')}
                    </tbody>
                </table>
            </div>
            ${renderPagination()}
        `;
    }

    function renderTableRow(endpoint, idx) {
        const statusConfig = endpoint.is_active ? STATUS_CONFIG.active : STATUS_CONFIG.inactive;
        const typeConfig = TYPE_CONFIG[endpoint.model_type] || TYPE_CONFIG.retrieval;
        const rowNum = (state.pagination.page - 1) * state.pagination.pageSize + idx + 1;

        return `
            <tr data-endpoint-id="${endpoint.id}">
                <td>${rowNum}</td>
                <td>
                    <div class="endpoints-table-name">
                        <span class="endpoints-table-name-main">${endpoint.service_name || 'Unnamed'}</span>
                        ${endpoint.run_number ? `<span class="endpoints-table-name-sub">Run #${endpoint.run_number}</span>` : ''}
                    </div>
                </td>
                <td>
                    <span class="endpoints-type-badge ${endpoint.model_type || 'retrieval'}">
                        <i class="fas ${typeConfig.icon}"></i>
                        ${endpoint.model_name || '-'}
                    </span>
                </td>
                <td>
                    <span class="endpoints-version-badge">
                        <i class="fas fa-code-branch"></i>
                        ${endpoint.deployed_version || 'v1'}
                    </span>
                </td>
                <td>
                    <div class="endpoints-url-cell">
                        <span class="endpoints-url-text" title="${endpoint.service_url || ''}">${truncateUrl(endpoint.service_url)}</span>
                        <button class="endpoints-url-copy-btn" onclick="EndpointsTable.copyUrl(${endpoint.id})" title="Copy URL">
                            <i class="fas fa-copy"></i>
                        </button>
                    </div>
                </td>
                <td>
                    <span class="endpoints-config-badge">${formatConfig(endpoint.deployment_config)}</span>
                </td>
                <td>
                    <span class="endpoints-status-badge ${statusConfig.class}">
                        <i class="fas ${statusConfig.icon}"></i>
                        ${statusConfig.label}
                    </span>
                </td>
                <td>${formatRelativeTime(endpoint.updated_at)}</td>
                <td class="endpoints-actions-cell">
                    ${renderActionButtons(endpoint)}
                </td>
            </tr>
        `;
    }

    function renderActionButtons(endpoint) {
        const isActive = endpoint.is_active;

        return `
            <div class="endpoints-action-buttons">
                <button class="endpoints-action-btn test" onclick="EndpointsTable.testEndpoint(${endpoint.id})" title="Test Endpoint" ${!isActive ? 'disabled' : ''}>
                    <i class="fas fa-play"></i>
                </button>
                <button class="endpoints-action-btn copy" onclick="EndpointsTable.copyUrl(${endpoint.id})" title="Copy URL">
                    <i class="fas fa-link"></i>
                </button>
                <button class="endpoints-action-btn logs" onclick="EndpointsTable.viewLogs(${endpoint.id})" title="View Logs">
                    <i class="fas fa-file-alt"></i>
                </button>
                <button class="endpoints-action-btn details" onclick="EndpointsTable.viewDetails(${endpoint.id})" title="View Details">
                    <i class="fas fa-info-circle"></i>
                </button>
                <button class="endpoints-action-btn undeploy" onclick="EndpointsTable.confirmUndeploy(${endpoint.id})" title="Undeploy" ${!isActive ? 'disabled' : ''}>
                    <i class="fas fa-trash-alt"></i>
                </button>
            </div>
        `;
    }

    function renderPagination() {
        if (state.pagination.totalPages <= 1) return '';

        return `
            <div class="endpoints-pagination">
                <button class="endpoints-pagination-btn" onclick="EndpointsTable.prevPage()" ${!state.pagination.hasPrev ? 'disabled' : ''}>
                    <i class="fas fa-chevron-left"></i>
                    Previous
                </button>
                <span class="endpoints-pagination-info">
                    Page ${state.pagination.page} of ${state.pagination.totalPages}
                    (${state.pagination.totalCount} endpoints)
                </span>
                <button class="endpoints-pagination-btn" onclick="EndpointsTable.nextPage()" ${!state.pagination.hasNext ? 'disabled' : ''}>
                    Next
                    <i class="fas fa-chevron-right"></i>
                </button>
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
                <div class="endpoints-loading">
                    <i class="fas fa-spinner fa-spin"></i>
                    <span class="endpoints-loading-text">Loading endpoints...</span>
                </div>
            `;
        }
    }

    function renderError(message) {
        const container = document.querySelector(config.tableContainerId);
        if (container) {
            container.innerHTML = `
                <div class="endpoints-empty-state">
                    <div class="empty-icon"><i class="fas fa-exclamation-triangle" style="color: #ef4444;"></i></div>
                    <h3>Error Loading Endpoints</h3>
                    <p>${message || 'An error occurred while loading endpoints.'}</p>
                    <button class="btn btn-primary" onclick="EndpointsTable.refresh()">
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
            fetchEndpoints();
        }, 300);
    }

    // =============================================================================
    // ACTIONS
    // =============================================================================

    function copyUrl(endpointId) {
        const endpoint = state.endpoints.find(e => e.id === endpointId);
        if (endpoint && endpoint.service_url) {
            navigator.clipboard.writeText(endpoint.service_url).then(() => {
                showToast('URL copied to clipboard', 'success');
                // Visual feedback on button
                const btn = document.querySelector(`[data-endpoint-id="${endpointId}"] .endpoints-url-copy-btn`);
                if (btn) {
                    btn.classList.add('copied');
                    setTimeout(() => btn.classList.remove('copied'), 2000);
                }
            }).catch(() => {
                showToast('Failed to copy URL', 'error');
            });
        }
    }

    function viewLogs(endpointId) {
        const endpoint = state.endpoints.find(e => e.id === endpointId);
        if (endpoint && endpoint.service_name) {
            const logsUrl = buildUrl(config.logsUrlPattern, {
                region: config.region,
                service: endpoint.service_name,
                project: config.project
            });
            window.open(logsUrl, '_blank');
        }
    }

    function viewDetails(endpointId) {
        const endpoint = state.endpoints.find(e => e.id === endpointId);
        if (!endpoint) return;

        // If ExpViewModal is available, use it for the linked training run
        if (endpoint.training_run_id && typeof ExpViewModal !== 'undefined') {
            ExpViewModal.open(endpoint.training_run_id, { mode: 'training_run' });
        } else if (config.onViewDetails) {
            config.onViewDetails(endpointId);
        } else {
            // Fallback: show alert with details
            const details = [
                `Service Name: ${endpoint.service_name}`,
                `URL: ${endpoint.service_url}`,
                `Model: ${endpoint.model_name}`,
                `Version: ${endpoint.deployed_version}`,
                `Status: ${endpoint.is_active ? 'Active' : 'Inactive'}`,
                `Config: ${formatConfig(endpoint.deployment_config)}`,
                `Last Updated: ${formatDateTime(endpoint.updated_at)}`
            ].join('\n');
            alert(details);
        }
    }

    function testEndpoint(endpointId) {
        const endpoint = state.endpoints.find(e => e.id === endpointId);
        if (!endpoint || !endpoint.is_active) {
            showToast('Cannot test inactive endpoint', 'error');
            return;
        }

        // Placeholder for future testing feature
        // See phase_deployment.md for full testing specification
        showToast('Endpoint testing feature coming soon!', 'info');

        // Future implementation could open a testing modal
        // if (typeof EndpointTester !== 'undefined') {
        //     EndpointTester.open(endpointId, endpoint.service_url);
        // }
    }

    function confirmUndeploy(endpointId) {
        const endpoint = state.endpoints.find(e => e.id === endpointId);
        if (!endpoint) return;

        if (!endpoint.is_active) {
            showToast('Endpoint is already inactive', 'error');
            return;
        }

        const serviceName = endpoint.service_name || 'this endpoint';
        if (confirm(`Are you sure you want to undeploy "${serviceName}"?\n\nThis will delete the Cloud Run service. This action cannot be undone.`)) {
            undeployEndpoint(endpointId);
        }
    }

    // =============================================================================
    // FILTER & PAGINATION
    // =============================================================================

    function setFilter(key, value) {
        state.filters[key] = value;
        state.pagination.page = 1;
        // Sync KPI filter when status dropdown changes
        if (key === 'status') {
            state.kpiFilter = value;
            renderKPI();
        }
        fetchEndpoints();
    }

    function setKpiFilter(filterValue) {
        state.kpiFilter = filterValue;
        state.filters.status = filterValue;
        state.pagination.page = 1;
        // Update the status dropdown to match
        const statusDropdown = document.getElementById('endpointsFilterStatus');
        if (statusDropdown) {
            statusDropdown.value = filterValue;
        }
        renderKPI();
        fetchEndpoints();
    }

    function nextPage() {
        if (state.pagination.hasNext) {
            state.pagination.page++;
            fetchEndpoints();
        }
    }

    function prevPage() {
        if (state.pagination.hasPrev) {
            state.pagination.page--;
            fetchEndpoints();
        }
    }

    function refresh() {
        fetchEndpoints();
    }

    // =============================================================================
    // NOTIFICATIONS
    // =============================================================================

    function showToast(message, type = 'info') {
        // Use TrainingCards modal if available for consistent UI
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
        config.containerId = options.containerId || '#endpointsChapter';
        config.kpiContainerId = options.kpiContainerId || '#endpointsKpiSummary';
        config.filterBarId = options.filterBarId || '#endpointsFilterBar';
        config.tableContainerId = options.tableContainerId || '#endpointsTable';
        config.emptyStateId = options.emptyStateId || '#endpointsEmptyState';

        if (options.onEndpointClick) config.onEndpointClick = options.onEndpointClick;
        if (options.onViewDetails) config.onViewDetails = options.onViewDetails;
        if (options.region) config.region = options.region;
        if (options.project) config.project = options.project;
        if (options.endpoints) {
            Object.assign(config.endpoints, options.endpoints);
        }

        return EndpointsTable;
    }

    function load() {
        // Render filter bar once on initial load
        renderFilterBar();
        fetchEndpoints();
    }

    // Expose public API
    return {
        init,
        load,
        refresh,
        setFilter,
        setKpiFilter,
        handleSearch,
        copyUrl,
        viewLogs,
        viewDetails,
        testEndpoint,
        confirmUndeploy,
        nextPage,
        prevPage
    };

})();
