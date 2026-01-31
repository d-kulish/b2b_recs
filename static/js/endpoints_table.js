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
            deploy: '/api/deployed-endpoints/{id}/deploy/',
            config: '/api/deployed-endpoints/{id}/config/',
            delete: '/api/deployed-endpoints/{id}/delete/',
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
        searchDebounceTimer: null,
        autoCloseTimer: null
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

    async function deployEndpoint(endpointId) {
        try {
            // Show loading spinner
            showLoadingModal('Deploying', 'Deploying endpoint...');

            const response = await fetch(buildUrl(config.endpoints.deploy, { id: endpointId }), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });
            const data = await response.json();

            if (data.success) {
                // Show success with auto-close after 3 seconds
                showConfirmModal({
                    title: 'Success',
                    message: 'Endpoint deployed successfully',
                    type: 'success',
                    confirmText: 'Ok',
                    confirmButtonClass: 'btn-neu-save',
                    hideCancel: true,
                    autoClose: 3000,
                    onConfirm: () => {}
                });
                fetchEndpoints();
            } else {
                showConfirmModal({
                    title: 'Error',
                    message: data.error || 'Failed to deploy endpoint',
                    type: 'danger',
                    confirmText: 'Close',
                    confirmButtonClass: 'btn-neu-cancel',
                    hideCancel: true,
                    onConfirm: () => {}
                });
            }
        } catch (error) {
            console.error('Error deploying endpoint:', error);
            showConfirmModal({
                title: 'Error',
                message: 'Failed to deploy endpoint',
                type: 'danger',
                confirmText: 'Close',
                confirmButtonClass: 'btn-neu-cancel',
                hideCancel: true,
                onConfirm: () => {}
            });
        }
    }

    async function updateEndpointConfig(endpointId, newConfig) {
        try {
            showToast('Updating endpoint configuration...', 'info');
            const response = await fetch(buildUrl(config.endpoints.config, { id: endpointId }), {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify(newConfig)
            });
            const data = await response.json();

            if (data.success) {
                showToast('Endpoint configuration updated successfully', 'success');
                closeEditModal();
                fetchEndpoints();
            } else {
                showToast(data.error || 'Failed to update endpoint config', 'error');
            }
        } catch (error) {
            console.error('Error updating endpoint config:', error);
            showToast('Failed to update endpoint config', 'error');
        }
    }

    async function deleteEndpoint(endpointId) {
        try {
            const response = await fetch(buildUrl(config.endpoints.delete, { id: endpointId }), {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });
            const data = await response.json();

            if (data.success) {
                showToast('Endpoint deleted successfully', 'success');
                fetchEndpoints();
            } else {
                showToast(data.error || 'Failed to delete endpoint', 'error');
            }
        } catch (error) {
            console.error('Error deleting endpoint:', error);
            showToast('Failed to delete endpoint', 'error');
        }
    }

    // =============================================================================
    // DROPDOWN & MODAL
    // =============================================================================

    function toggleViewDropdown(endpointId, event) {
        event.stopPropagation();
        closeAllDropdowns();

        const dropdown = document.getElementById(`viewDropdown-${endpointId}`);
        if (dropdown) {
            dropdown.classList.toggle('visible');
        }
    }

    function closeAllDropdowns() {
        document.querySelectorAll('.endpoints-dropdown-menu.visible').forEach(menu => {
            menu.classList.remove('visible');
        });
    }

    // Close dropdowns when clicking outside
    document.addEventListener('click', function(event) {
        if (!event.target.closest('.endpoints-dropdown')) {
            closeAllDropdowns();
        }
    });

    // Edit modal state
    let editModalState = {
        endpointId: null,
        endpoint: null,
        selectedPreset: 'production',
        showAdvanced: false
    };

    // Preset configurations
    const PRESETS = {
        development: {
            name: 'Development',
            description: 'Low cost, scale to zero',
            icon: 'fa-laptop-code',
            config: { memory: '2Gi', cpu: '1', min_instances: 0, max_instances: 2, timeout: '300' }
        },
        production: {
            name: 'Production',
            description: 'Balanced performance',
            icon: 'fa-server',
            config: { memory: '4Gi', cpu: '2', min_instances: 1, max_instances: 10, timeout: '300' }
        },
        high_traffic: {
            name: 'High Traffic',
            description: 'Maximum performance',
            icon: 'fa-rocket',
            config: { memory: '8Gi', cpu: '4', min_instances: 2, max_instances: 20, timeout: '600' }
        }
    };

    function openEditModal(endpointId) {
        const endpoint = state.endpoints.find(e => e.id === endpointId);
        if (!endpoint) return;

        editModalState.endpointId = endpointId;
        editModalState.endpoint = endpoint;
        editModalState.showAdvanced = false;

        // Detect current preset based on config
        const currentConfig = endpoint.deployment_config || {};
        editModalState.selectedPreset = detectPreset(currentConfig);

        renderEditModal();
    }

    function detectPreset(config) {
        // Try to match current config to a preset
        for (const [key, preset] of Object.entries(PRESETS)) {
            if (preset.config.memory === config.memory &&
                preset.config.cpu === config.cpu &&
                preset.config.min_instances === config.min_instances &&
                preset.config.max_instances === config.max_instances) {
                return key;
            }
        }
        return 'custom';
    }

    function renderEditModal() {
        // Remove existing modal if any
        const existingModal = document.getElementById('endpointEditModal');
        if (existingModal) {
            existingModal.remove();
        }

        const endpoint = editModalState.endpoint;
        const currentConfig = endpoint.deployment_config || {};

        const modalHtml = `
            <div id="endpointEditModal" class="endpoint-edit-modal-overlay">
                <div class="endpoint-edit-modal">
                    <div class="endpoint-edit-modal-header">
                        <h3><i class="fas fa-cog"></i> Edit Endpoint Configuration</h3>
                        <button class="endpoint-edit-modal-close" onclick="EndpointsTable.closeEditModal()">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>

                    <div class="endpoint-edit-modal-body">
                        <!-- Endpoint Info -->
                        <div class="edit-endpoint-info">
                            <span class="edit-endpoint-name">${endpoint.service_name}</span>
                            <span class="edit-endpoint-version">Version ${endpoint.deployed_version || 'v1'}</span>
                        </div>

                        <!-- Deployment Presets -->
                        <div class="edit-section-label">Configuration Preset</div>
                        <div class="deploy-preset-cards">
                            ${Object.entries(PRESETS).map(([key, preset]) => `
                                <div class="deploy-preset-card ${editModalState.selectedPreset === key ? 'selected' : ''}"
                                     data-preset="${key}"
                                     onclick="EndpointsTable.selectPreset('${key}')">
                                    <div class="deploy-preset-icon"><i class="fas ${preset.icon}"></i></div>
                                    <div class="deploy-preset-name">${preset.name}</div>
                                    <div class="deploy-preset-desc">${preset.description}</div>
                                    <div class="deploy-preset-specs">
                                        ${preset.config.cpu} vCPU, ${preset.config.memory}
                                    </div>
                                </div>
                            `).join('')}
                        </div>

                        <!-- Advanced Options Toggle -->
                        <div class="edit-advanced-header" onclick="EndpointsTable.toggleAdvancedOptions()">
                            <i class="fas fa-sliders-h"></i>
                            <span>Advanced Options</span>
                            <i class="fas fa-chevron-${editModalState.showAdvanced ? 'up' : 'down'}" id="advancedChevron"></i>
                        </div>

                        <!-- Advanced Options Panel -->
                        <div class="edit-advanced-options ${editModalState.showAdvanced ? 'visible' : ''}" id="editAdvancedOptions">
                            <div class="edit-option-row">
                                <div class="edit-option-group">
                                    <label>Memory</label>
                                    <select id="editMemory">
                                        ${['1Gi', '2Gi', '4Gi', '8Gi', '16Gi', '32Gi'].map(m =>
                                            `<option value="${m}" ${currentConfig.memory === m ? 'selected' : ''}>${m}</option>`
                                        ).join('')}
                                    </select>
                                </div>
                                <div class="edit-option-group">
                                    <label>CPU</label>
                                    <select id="editCpu">
                                        ${['1', '2', '4', '8'].map(c =>
                                            `<option value="${c}" ${currentConfig.cpu === c ? 'selected' : ''}>${c} vCPU</option>`
                                        ).join('')}
                                    </select>
                                </div>
                            </div>
                            <div class="edit-option-row">
                                <div class="edit-option-group">
                                    <label>Min Instances</label>
                                    <input type="number" id="editMinInstances" min="0" max="100"
                                           value="${currentConfig.min_instances || 0}">
                                </div>
                                <div class="edit-option-group">
                                    <label>Max Instances</label>
                                    <input type="number" id="editMaxInstances" min="1" max="1000"
                                           value="${currentConfig.max_instances || 10}">
                                </div>
                            </div>
                            <div class="edit-option-row">
                                <div class="edit-option-group" style="flex: 1;">
                                    <label>Timeout (seconds)</label>
                                    <input type="number" id="editTimeout" min="1" max="3600"
                                           value="${currentConfig.timeout || 300}">
                                </div>
                            </div>
                        </div>

                        <!-- Warning -->
                        <div class="edit-warning">
                            <i class="fas fa-exclamation-triangle"></i>
                            <span>This will undeploy and redeploy the endpoint with the new configuration. There may be brief downtime.</span>
                        </div>
                    </div>

                    <div class="endpoint-edit-modal-footer">
                        <button class="btn-cancel" onclick="EndpointsTable.closeEditModal()">Cancel</button>
                        <button class="btn-save" onclick="EndpointsTable.saveEndpointConfig()">
                            <i class="fas fa-check"></i> Apply Changes
                        </button>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHtml);
    }

    function closeEditModal() {
        const modal = document.getElementById('endpointEditModal');
        if (modal) {
            modal.remove();
        }
        editModalState = {
            endpointId: null,
            endpoint: null,
            selectedPreset: 'production',
            showAdvanced: false
        };
    }

    function selectPreset(presetName) {
        editModalState.selectedPreset = presetName;
        const preset = PRESETS[presetName];

        if (preset) {
            // Update advanced options with preset values
            const memorySelect = document.getElementById('editMemory');
            const cpuSelect = document.getElementById('editCpu');
            const minInput = document.getElementById('editMinInstances');
            const maxInput = document.getElementById('editMaxInstances');
            const timeoutInput = document.getElementById('editTimeout');

            if (memorySelect) memorySelect.value = preset.config.memory;
            if (cpuSelect) cpuSelect.value = preset.config.cpu;
            if (minInput) minInput.value = preset.config.min_instances;
            if (maxInput) maxInput.value = preset.config.max_instances;
            if (timeoutInput) timeoutInput.value = preset.config.timeout;
        }

        // Update selected state on preset cards
        document.querySelectorAll('.deploy-preset-card').forEach(card => {
            card.classList.remove('selected');
            if (card.dataset.preset === presetName) {
                card.classList.add('selected');
            }
        });
    }

    function toggleAdvancedOptions() {
        editModalState.showAdvanced = !editModalState.showAdvanced;
        const panel = document.getElementById('editAdvancedOptions');
        const chevron = document.getElementById('advancedChevron');

        if (panel) {
            panel.classList.toggle('visible', editModalState.showAdvanced);
        }
        if (chevron) {
            chevron.className = `fas fa-chevron-${editModalState.showAdvanced ? 'up' : 'down'}`;
        }
    }

    function saveEndpointConfig() {
        const newConfig = {
            memory: document.getElementById('editMemory')?.value,
            cpu: document.getElementById('editCpu')?.value,
            min_instances: parseInt(document.getElementById('editMinInstances')?.value || '0', 10),
            max_instances: parseInt(document.getElementById('editMaxInstances')?.value || '10', 10),
            timeout: document.getElementById('editTimeout')?.value
        };

        // Validate
        if (newConfig.min_instances > newConfig.max_instances) {
            showToast('Min instances cannot exceed max instances', 'error');
            return;
        }

        updateEndpointConfig(editModalState.endpointId, newConfig);
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

        // 2x2 Grid Layout matching Models Registry on Training page:
        // Row 1: [Deploy/Undeploy] [View]
        // Row 2: [empty spacer]    [Edit][Delete] grouped
        return `
            <div class="ml-card-col-actions">
                <div class="ml-card-actions-grid">
                    <!-- Row 1: Deploy/Undeploy | View -->
                    <button class="card-action-btn deploy"
                            onclick="${isActive
                                ? `EndpointsTable.confirmUndeploy(${endpoint.id})`
                                : `EndpointsTable.confirmDeploy(${endpoint.id})`}">
                        ${isActive ? 'Undeploy' : 'Deploy'}
                    </button>
                    <button class="card-action-btn view"
                            onclick="EndpointsTable.viewDetails(${endpoint.id})">
                        View
                    </button>

                    <!-- Row 2: Spacer | Edit+Delete group -->
                    <div></div>
                    <div class="card-action-btn-group">
                        <button class="card-action-btn icon-only edit"
                                onclick="EndpointsTable.openEditModal(${endpoint.id})"
                                title="Edit Config"
                                ${!isActive ? 'disabled' : ''}>
                            <i class="fas fa-external-link-alt"></i>
                        </button>
                        <button class="card-action-btn icon-only delete"
                                onclick="EndpointsTable.confirmDelete(${endpoint.id})"
                                title="Delete"
                                ${isActive ? 'disabled' : ''}>
                            <i class="fas fa-trash-alt"></i>
                        </button>
                    </div>
                </div>
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
        showConfirmModal({
            title: 'Undeploy Endpoint',
            message: `Are you sure you want to undeploy <strong>${serviceName}</strong>?<br><br>This will delete the Cloud Run service.<br>The endpoint record will remain and can be re-deployed.`,
            confirmText: 'Undeploy',
            cancelText: 'Cancel',
            type: 'warning',
            confirmButtonClass: 'btn-neu-save',      // Green button
            cancelButtonClass: 'btn-neu-cancel',     // Red button
            onConfirm: () => {
                undeployEndpoint(endpointId);
            }
        });
    }

    function confirmDeploy(endpointId) {
        const endpoint = state.endpoints.find(e => e.id === endpointId);
        if (!endpoint) return;

        if (endpoint.is_active) {
            showToast('Endpoint is already active', 'error');
            return;
        }

        const serviceName = endpoint.service_name || 'this endpoint';
        const deployConfig = endpoint.deployment_config || {};
        const configStr = `${deployConfig.cpu || '2'} vCPU, ${deployConfig.memory || '4Gi'}`;

        showConfirmModal({
            title: 'Deploy Endpoint',
            message: `Deploy <strong>${serviceName}</strong>?<br><br>This will create the Cloud Run service with:<br>• Version: ${endpoint.deployed_version || 'v1'}<br>• Config: ${configStr}`,
            confirmText: 'Deploy',
            cancelText: 'Cancel',
            type: 'info',
            confirmButtonClass: 'btn-neu-save',      // Green button
            cancelButtonClass: 'btn-neu-cancel',     // Red button
            onConfirm: () => {
                deployEndpoint(endpointId);
            }
        });
    }

    function confirmDelete(endpointId) {
        const endpoint = state.endpoints.find(e => e.id === endpointId);
        if (!endpoint) return;

        if (endpoint.is_active) {
            showToast('Cannot delete active endpoint. Undeploy it first.', 'error');
            return;
        }

        showConfirmModal({
            title: 'Delete Endpoint',
            message: 'Are you sure you want to delete this endpoint?<br><br><strong>This action cannot be undone.</strong>',
            confirmText: 'Confirm',
            cancelText: 'Cancel',
            type: 'danger',
            confirmButtonClass: 'btn-neu-save',      // Green button
            cancelButtonClass: 'btn-neu-cancel',     // Red button
            onConfirm: () => {
                deleteEndpoint(endpointId);
            }
        });
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
    // CONFIRMATION MODAL (styled modal matching Training page)
    // =============================================================================

    function showConfirmModal(options) {
        const modal = document.getElementById('confirmModal');
        const icon = document.getElementById('confirmModalIcon');
        const title = document.getElementById('confirmModalTitle');
        const message = document.getElementById('confirmModalMessage');
        const confirmBtn = document.getElementById('confirmModalConfirmBtn');
        const cancelBtn = document.getElementById('confirmModalCancelBtn');

        // Set content
        title.textContent = options.title || 'Confirm Action';
        message.innerHTML = options.message || 'Are you sure you want to proceed?';

        // Update inner span text for neumorphic buttons
        const confirmInner = confirmBtn.querySelector('.btn-neu-inner');
        const cancelInner = cancelBtn.querySelector('.btn-neu-inner');
        if (confirmInner) confirmInner.textContent = options.confirmText || 'Confirm';
        if (cancelInner) cancelInner.textContent = options.cancelText || 'Cancel';

        // Set icon and button type
        const type = options.type || 'warning';
        icon.className = `modal-header-icon ${type}`;

        // Update icon based on type
        const iconElement = icon.querySelector('i');
        const baseClasses = 'btn-neu btn-neu-action';

        // Determine confirm button class (custom class takes precedence)
        let confirmButtonClass = options.confirmButtonClass;
        if (!confirmButtonClass) {
            if (type === 'danger') {
                iconElement.className = 'fas fa-trash-alt text-xl';
                confirmButtonClass = 'btn-neu-cancel';  // RED button for destructive actions
            } else if (type === 'warning') {
                iconElement.className = 'fas fa-exclamation-circle text-xl';
                confirmButtonClass = 'btn-neu-warning';
            } else if (type === 'info') {
                iconElement.className = 'fas fa-info-circle text-xl';
                confirmButtonClass = 'btn-neu-nav-wide';
            } else if (type === 'success') {
                iconElement.className = 'fas fa-check-circle text-xl';
                confirmButtonClass = 'btn-neu-save';
            }
        } else {
            // Set icon based on type even when custom button class is provided
            if (type === 'danger') {
                iconElement.className = 'fas fa-trash-alt text-xl';
            } else if (type === 'warning') {
                iconElement.className = 'fas fa-exclamation-circle text-xl';
            } else if (type === 'info') {
                iconElement.className = 'fas fa-info-circle text-xl';
            } else if (type === 'success') {
                iconElement.className = 'fas fa-check-circle text-xl';
            }
        }
        confirmBtn.className = `${baseClasses} ${confirmButtonClass}`;

        // Set cancel button class (default: btn-neu-secondary for grey neutral button)
        cancelBtn.className = `${baseClasses} ${options.cancelButtonClass || 'btn-neu-secondary'}`;

        // Hide cancel button if requested (for notification modals)
        if (options.hideCancel) {
            cancelBtn.style.display = 'none';
        } else {
            cancelBtn.style.display = '';
        }

        // Hide confirm button if requested (for loading modals)
        if (options.hideConfirm) {
            confirmBtn.style.display = 'none';
        } else {
            confirmBtn.style.display = '';  // Always restore visibility
        }

        // Remove old event listeners by cloning
        const newConfirmBtn = confirmBtn.cloneNode(true);
        const newCancelBtn = cancelBtn.cloneNode(true);
        confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
        cancelBtn.parentNode.replaceChild(newCancelBtn, cancelBtn);

        // Add new event listeners
        newConfirmBtn.addEventListener('click', () => {
            hideConfirmModal();
            if (options.onConfirm) options.onConfirm();
        });

        newCancelBtn.addEventListener('click', () => {
            hideConfirmModal();
            if (options.onCancel) options.onCancel();
        });

        // Show modal
        modal.classList.remove('hidden');

        // Close on overlay click
        modal.addEventListener('click', function overlayClick(e) {
            if (e.target === modal) {
                hideConfirmModal();
                if (options.onCancel) options.onCancel();
                modal.removeEventListener('click', overlayClick);
            }
        });

        // Close on ESC key
        function escapeHandler(e) {
            if (e.key === 'Escape') {
                hideConfirmModal();
                if (options.onCancel) options.onCancel();
                document.removeEventListener('keydown', escapeHandler);
            }
        }
        document.addEventListener('keydown', escapeHandler);

        // Auto-close after specified time if requested
        if (options.autoClose && options.autoClose > 0) {
            // Clear any existing timer
            if (state.autoCloseTimer) {
                clearTimeout(state.autoCloseTimer);
            }
            state.autoCloseTimer = setTimeout(() => {
                hideConfirmModal();
                if (options.onConfirm) options.onConfirm();
            }, options.autoClose);
        }
    }

    function hideConfirmModal() {
        const modal = document.getElementById('confirmModal');
        modal.classList.add('hidden');
        // Clear auto-close timer if any
        if (state.autoCloseTimer) {
            clearTimeout(state.autoCloseTimer);
            state.autoCloseTimer = null;
        }
    }

    function showLoadingModal(title, message) {
        showConfirmModal({
            title: title,
            message: `<div style="display: flex; align-items: center; gap: 12px;"><i class="fas fa-spinner fa-spin" style="font-size: 24px; color: #6366f1;"></i><span>${message}</span></div>`,
            type: 'info',
            hideCancel: true,
            hideConfirm: true
        });
    }

    // =============================================================================
    // NOTIFICATIONS
    // =============================================================================

    function showToast(message, type = 'info') {
        showConfirmModal({
            title: type === 'success' ? 'Success' : type === 'error' ? 'Error' : 'Info',
            message: message,
            type: type === 'success' ? 'success' : type === 'error' ? 'danger' : 'info',
            confirmText: 'Close',
            hideCancel: true,
            onConfirm: () => {}
        });
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
        confirmDeploy,
        confirmDelete,
        toggleViewDropdown,
        openEditModal,
        closeEditModal,
        selectPreset,
        toggleAdvancedOptions,
        saveEndpointConfig,
        nextPage,
        prevPage
    };

})();
