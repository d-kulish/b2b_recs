/**
 * Training Cards Module
 *
 * Handles displaying and managing training run cards with filtering,
 * pagination, and auto-refresh for running/submitting states.
 *
 * Usage:
 *     // Configure the module
 *     TrainingCards.configure({
 *         modelId: 123,
 *         onViewRun: function(runId) { TrainingViewModal.open(runId); }
 *     });
 *
 *     // Load and display training runs
 *     TrainingCards.init();
 */

const TrainingCards = (function() {
    'use strict';

    // =============================================================================
    // CONFIGURATION & STATE
    // =============================================================================

    let config = {
        endpoints: {
            list: '/api/training-runs/',
            modelNames: '/api/models/names/',
            cancel: '/api/training-runs/{id}/cancel/',
            delete: '/api/training-runs/{id}/delete/',
            submit: '/api/training-runs/{id}/submit/',
            deploy: '/api/training-runs/{id}/deploy/',
            deployCloudRun: '/api/training-runs/{id}/deploy-cloud-run/',
            push: '/api/training-runs/{id}/push/',
            rerun: '/api/training-runs/{id}/rerun/'
        },
        pollIntervalMs: 30000,  // 30 seconds
        modelId: null,
        onViewRun: null,
        containers: {
            filterBar: 'trainingFilterBar',
            cardsList: 'trainingCardsList',
            pagination: 'trainingPagination',
            emptyState: 'trainingEmptyState',
            loading: 'trainingLoading',
            main: 'trainingRunsContainer'
        }
    };

    let state = {
        trainingRuns: [],
        filters: {
            status: null,        // null = all, or specific status
            modelType: null,     // null = all, or 'retrieval', 'ranking', 'multitask'
            vertexModelName: null,  // null = all, or specific registered model name
            search: ''
        },
        pagination: {
            page: 1,
            pageSize: 10,
            totalCount: 0,
            totalPages: 1,
            hasNext: false,
            hasPrev: false
        },
        pollInterval: null,
        isLoading: false,
        autoCloseTimer: null
    };

    // Status configuration
    const STATUS_CONFIG = {
        pending: {
            icon: 'fa-hourglass-start',
            label: 'Pending',
            spin: false,
            actions: ['view', 'submit', 'cancel']
        },
        scheduled: {
            icon: 'fa-clock',
            label: 'Scheduled',
            spin: false,
            actions: ['view', 'submit', 'cancel']
        },
        submitting: {
            icon: 'fa-sync',
            label: 'Submitting',
            spin: true,
            actions: ['view', 'cancel']
        },
        running: {
            icon: 'fa-sync',
            label: 'Running',
            spin: true,
            actions: ['view', 'cancel']
        },
        completed: {
            icon: 'fa-check-circle',
            label: 'Completed',
            spin: false,
            actions: ['view', 'rerun', 'deploy', 'deployCloudRun', 'delete']
        },
        failed: {
            icon: 'fa-times-circle',
            label: 'Failed',
            spin: false,
            actions: ['view', 'rerun', 'delete']
        },
        cancelled: {
            icon: 'fa-ban',
            label: 'Cancelled',
            spin: false,
            actions: ['view', 'rerun', 'delete']
        },
        not_blessed: {
            icon: 'fa-exclamation-triangle',
            label: 'Not Blessed',
            spin: false,
            actions: ['view', 'rerun', 'push', 'delete']
        }
    };

    // Pipeline stages for progress display
    const PIPELINE_STAGES = [
        'compile', 'examples', 'stats', 'schema', 'transform', 'train', 'evaluate', 'push'
    ];

    // =============================================================================
    // UTILITY FUNCTIONS
    // =============================================================================

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

    function buildUrl(template, params) {
        let url = template;
        for (const [key, value] of Object.entries(params)) {
            url = url.replace(`{${key}}`, value);
        }
        return url;
    }

    function formatNumber(val, decimals = 3) {
        if (val === null || val === undefined) return '-';
        if (typeof val !== 'number') return val;
        return val.toFixed(decimals);
    }

    function formatDuration(seconds) {
        if (!seconds && seconds !== 0) return '-';
        if (seconds < 60) return `${seconds}s`;
        if (seconds < 3600) {
            const mins = Math.floor(seconds / 60);
            const secs = seconds % 60;
            return `${mins}m ${secs}s`;
        }
        const hours = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        return `${hours}h ${mins}m`;
    }

    function formatDate(dateString) {
        if (!dateString) return '-';
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric'
        }) + ' ' + date.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    /**
     * Show a success notification modal that auto-closes after 4 seconds.
     */
    function showSuccessModal(message) {
        showConfirmModal({
            title: 'Success',
            message: message,
            type: 'success',
            confirmText: 'Close',
            hideCancel: true,
            autoClose: 4000,
            onConfirm: () => {}
        });
    }

    /**
     * Show an error notification modal.
     */
    function showErrorModal(message) {
        showConfirmModal({
            title: 'Error',
            message: message,
            type: 'danger',
            confirmText: 'Close',
            hideCancel: true,
            onConfirm: () => {}
        });
    }

    // Legacy showToast function - redirects to modal
    function showToast(message, type = 'success') {
        if (type === 'success') {
            showSuccessModal(message);
        } else {
            showErrorModal(message);
        }
    }

    /**
     * Show a styled confirmation modal (matches experiments page)
     * @param {Object} options - Modal options
     * @param {string} options.title - Modal title
     * @param {string} options.message - Modal message (can include HTML)
     * @param {string} options.confirmText - Confirm button text
     * @param {string} options.cancelText - Cancel button text
     * @param {string} options.type - Modal type: 'warning', 'danger', 'info', 'success'
     * @param {string} options.confirmButtonClass - Custom class for confirm button
     * @param {string} options.cancelButtonClass - Custom class for cancel button
     * @param {boolean} options.hideCancel - Hide the cancel button (for notifications)
     * @param {number} options.autoClose - Auto-close modal after N milliseconds
     * @param {Function} options.onConfirm - Callback when confirmed
     * @param {Function} options.onCancel - Callback when cancelled (optional)
     */
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
        // Note: btn-neu-cancel = RED (destructive), btn-neu-secondary = GREY (neutral)
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

    // =============================================================================
    // CONFIGURATION
    // =============================================================================

    function configure(options) {
        if (options.modelId) config.modelId = options.modelId;
        if (options.onViewRun) config.onViewRun = options.onViewRun;
        if (options.endpoints) {
            config.endpoints = { ...config.endpoints, ...options.endpoints };
        }
        if (options.pollIntervalMs) {
            config.pollIntervalMs = options.pollIntervalMs;
        }
    }

    // =============================================================================
    // INITIALIZATION
    // =============================================================================

    function init() {
        renderFilterBar();
        loadTrainingRuns();
    }

    // =============================================================================
    // DATA LOADING
    // =============================================================================

    async function loadTrainingRuns() {
        if (state.isLoading) return;
        state.isLoading = true;

        // Only show loading on initial load (no existing cards)
        const container = document.getElementById(config.containers.cardsList);
        if (!container || container.children.length === 0) {
            showLoading();
        }

        try {
            // Build query params
            const params = new URLSearchParams();
            params.set('page', state.pagination.page);
            params.set('page_size', state.pagination.pageSize);

            if (state.filters.status) {
                params.set('status', state.filters.status);
            }
            if (state.filters.modelType) {
                params.set('model_type', state.filters.modelType);
            }
            if (state.filters.vertexModelName) {
                params.set('vertex_model_name', state.filters.vertexModelName);
            }
            if (state.filters.search) {
                params.set('search', state.filters.search);
            }

            const url = `${config.endpoints.list}?${params.toString()}`;
            const response = await fetch(url);
            const data = await response.json();

            if (data.success) {
                state.trainingRuns = data.training_runs || [];
                state.pagination = {
                    page: data.pagination?.page || 1,
                    pageSize: data.pagination?.page_size || 10,
                    totalCount: data.pagination?.total_count || 0,
                    totalPages: data.pagination?.total_pages || 1,
                    hasNext: data.pagination?.has_next || false,
                    hasPrev: data.pagination?.has_prev || false
                };

                renderCards();
                renderPagination();

                // Start/stop polling based on active runs
                updatePolling();
            } else {
                console.error('Failed to load training runs:', data.error);
                showEmptyState('Failed to load training runs');
            }
        } catch (error) {
            console.error('Error loading training runs:', error);
            showEmptyState('Error loading training runs');
        } finally {
            state.isLoading = false;
            hideLoading();
        }
    }

    function refresh() {
        loadTrainingRuns();
    }

    // =============================================================================
    // POLLING FOR ACTIVE RUNS
    // =============================================================================

    function updatePolling() {
        const hasActiveRuns = state.trainingRuns.some(run =>
            run.status === 'running' || run.status === 'submitting'
        );

        if (hasActiveRuns && !state.pollInterval) {
            state.pollInterval = setInterval(() => {
                loadTrainingRuns();
            }, config.pollIntervalMs);
        } else if (!hasActiveRuns && state.pollInterval) {
            // Stop polling
            clearInterval(state.pollInterval);
            state.pollInterval = null;
        }
    }

    function stopPolling() {
        if (state.pollInterval) {
            clearInterval(state.pollInterval);
            state.pollInterval = null;
        }
    }

    // =============================================================================
    // FILTERING
    // =============================================================================

    function filterByStatus(status) {
        state.filters.status = status;
        state.pagination.page = 1;
        loadTrainingRuns();
        updateFilterUI();
    }

    function filterByModelType(modelType) {
        state.filters.modelType = modelType;
        state.pagination.page = 1;
        loadTrainingRuns();
    }

    function filterByModelName(modelName) {
        state.filters.vertexModelName = modelName;
        state.pagination.page = 1;
        loadTrainingRuns();
        updateFilterUI();
    }

    function search(query) {
        state.filters.search = query;
        state.pagination.page = 1;
        loadTrainingRuns();
    }

    function clearFilters() {
        state.filters = { status: null, modelType: null, vertexModelName: null, search: '' };
        state.pagination.page = 1;
        loadTrainingRuns();
        updateFilterUI();
    }

    function updateFilterUI() {
        // Update status dropdown
        const statusSelect = document.getElementById('trainingStatusFilter');
        if (statusSelect) {
            statusSelect.value = state.filters.status || '';
        }

        // Update model type dropdown
        const modelTypeSelect = document.getElementById('trainingModelTypeFilter');
        if (modelTypeSelect) {
            modelTypeSelect.value = state.filters.modelType || '';
        }

        // Update model name dropdown
        const modelNameSelect = document.getElementById('trainingModelNameFilter');
        if (modelNameSelect) {
            modelNameSelect.value = state.filters.vertexModelName || '';
        }

        // Update search input
        const searchInput = document.getElementById('trainingSearchInput');
        if (searchInput) {
            searchInput.value = state.filters.search || '';
        }
    }

    // =============================================================================
    // PAGINATION
    // =============================================================================

    function nextPage() {
        if (state.pagination.hasNext) {
            state.pagination.page++;
            loadTrainingRuns();
        }
    }

    function prevPage() {
        if (state.pagination.hasPrev) {
            state.pagination.page--;
            loadTrainingRuns();
        }
    }

    function goToPage(page) {
        if (page >= 1 && page <= state.pagination.totalPages) {
            state.pagination.page = page;
            loadTrainingRuns();
        }
    }

    // =============================================================================
    // RENDERING - FILTER BAR
    // =============================================================================

    function renderFilterBar() {
        const container = document.getElementById(config.containers.filterBar);
        if (!container) return;

        container.innerHTML = `
            <div class="training-filter-bar">
                <div class="training-filter-group">
                    <label class="training-filter-label">Status</label>
                    <select id="trainingStatusFilter" class="training-filter-select" onchange="TrainingCards.filterByStatus(this.value || null)">
                        <option value="">All</option>
                        <option value="running">Running</option>
                        <option value="completed">Completed</option>
                        <option value="failed">Failed</option>
                        <option value="cancelled">Cancelled</option>
                    </select>
                </div>

                <div class="training-filter-group">
                    <label class="training-filter-label">Model type</label>
                    <select id="trainingModelTypeFilter" class="training-filter-select" onchange="TrainingCards.filterByModelType(this.value || null)">
                        <option value="">All</option>
                        <option value="retrieval">Retrieval</option>
                        <option value="ranking">Ranking</option>
                        <option value="multitask">Hybrid</option>
                    </select>
                </div>

                <div class="training-filter-group">
                    <label class="training-filter-label">Registered Model</label>
                    <select id="trainingModelNameFilter" class="training-filter-select" onchange="TrainingCards.filterByModelName(this.value || null)">
                        <option value="">All</option>
                        <!-- Options populated dynamically -->
                    </select>
                </div>

                <input type="text" id="trainingSearchInput" class="training-search-input"
                       placeholder="Search by Run #..." oninput="TrainingCards.handleSearchInput(this.value)">
            </div>
        `;

        // Load model names for dropdown
        loadModelNames();
    }

    async function loadModelNames() {
        try {
            const response = await fetch(config.endpoints.modelNames);
            const data = await response.json();

            if (data.success && data.model_names) {
                const select = document.getElementById('trainingModelNameFilter');
                if (select) {
                    // Keep "All" option, add model names
                    data.model_names.forEach(name => {
                        const option = document.createElement('option');
                        option.value = name;
                        option.textContent = name;
                        select.appendChild(option);
                    });
                }
            }
        } catch (error) {
            console.error('Failed to load model names:', error);
        }
    }

    // Debounced search handler
    let searchTimeout = null;
    function handleSearchInput(value) {
        if (searchTimeout) {
            clearTimeout(searchTimeout);
        }
        searchTimeout = setTimeout(() => {
            search(value);
        }, 300);
    }

    // =============================================================================
    // RENDERING - CARDS
    // =============================================================================

    function renderCards() {
        const container = document.getElementById(config.containers.cardsList);
        const emptyState = document.getElementById(config.containers.emptyState);

        if (!container) return;

        if (state.trainingRuns.length === 0) {
            container.innerHTML = '';
            if (emptyState) {
                emptyState.classList.remove('hidden');
            }
            return;
        }

        if (emptyState) {
            emptyState.classList.add('hidden');
        }

        const cardsHtml = state.trainingRuns.map(run => renderCard(run)).join('');
        container.innerHTML = `<div class="training-cards-container">${cardsHtml}</div>`;
    }

    function renderCard(run) {
        const statusConfig = STATUS_CONFIG[run.status] || STATUS_CONFIG.pending;

        // Format times
        const startTime = formatDate(run.created_at);
        const endTime = run.completed_at ? formatDate(run.completed_at) : '-';

        // Metrics section
        const metricsHtml = renderMetrics(run);

        // Config info
        const configHtml = renderConfigInfo(run);

        // Actions
        const actionsHtml = renderActions(run, statusConfig.actions);

        // Error section (for failed)
        const errorHtml = run.status === 'failed' ? renderError(run) : '';

        // Badges row (spans columns 1-2, above stage bar)
        const badgesHtml = renderBadgesRow(run);

        // Stage bar (always shown at bottom)
        const stagesHtml = renderStageBar(run.stage_details || getDefaultStages());

        return `
            <div class="ml-card" data-run-id="${run.id}" onclick="TrainingCards.viewRun(${run.id})">
                <div class="ml-card-columns">
                    <!-- Column 1: Status Icon + Info (30%) -->
                    <div class="ml-card-col-info">
                        <div class="ml-card-status ${run.status}">
                            <i class="fas ${statusConfig.icon}"></i>
                        </div>
                        <div class="ml-card-info-text">
                            <div class="ml-card-name">Run #${run.run_number}</div>
                            <div class="ml-card-secondary-name">${escapeHtml(run.name)}</div>
                            ${run.description ? `<div class="ml-card-description" title="${escapeHtml(run.description)}">${escapeHtml(run.description)}</div>` : ''}
                            <div class="ml-card-times">
                                <div>Start: <span>${startTime}</span></div>
                                <div>End: <span>${endTime}</span></div>
                            </div>
                        </div>
                    </div>
                    <!-- Column 2: Config Info (20%) -->
                    ${configHtml}
                    <!-- Column 3: Metrics (30%) -->
                    <div class="ml-card-col-metrics">
                        ${metricsHtml}
                    </div>
                    <!-- Column 4: Actions (20%) -->
                    ${actionsHtml}
                </div>
                ${badgesHtml}
                ${errorHtml}
                ${stagesHtml}
            </div>
        `;
    }

    function renderModelTypeBadge(modelType) {
        const icons = {
            retrieval: 'fa-search',
            ranking: 'fa-sort-amount-down',
            multitask: 'fa-layer-group'
        };
        const labels = {
            retrieval: 'Retrieval',
            ranking: 'Ranking',
            multitask: 'Retrieval / Ranking'
        };
        const icon = icons[modelType] || icons.retrieval;
        const label = labels[modelType] || labels.retrieval;
        return `
            <span class="ml-card-type-badge ${modelType}">
                <i class="fas ${icon}"></i> ${label}
            </span>
        `;
    }

    function renderBadges(run) {
        let badges = '';

        // Always show deployment status for completed runs
        if (run.status === 'completed' || run.status === 'not_blessed') {
            if (run.is_deployed) {
                badges += `
                    <span class="training-card-deployed-badge">
                        <i class="fas fa-rocket"></i> Deployed
                    </span>
                `;
            } else {
                badges += `
                    <span class="training-card-deployed-badge not-deployed">
                        <i class="fas fa-rocket"></i> Not Deployed
                    </span>
                `;
            }
        }

        // Blessed badge
        if (run.is_blessed === true) {
            badges += `
                <span class="training-card-blessed-badge">
                    <i class="fas fa-star"></i> Blessed
                </span>
            `;
        } else if (run.is_blessed === false) {
            badges += `
                <span class="training-card-blessed-badge not-blessed">
                    <i class="fas fa-exclamation"></i> Not Blessed
                </span>
            `;
        }

        return badges;
    }

    function renderMetrics(run) {
        // Different metrics for different model types
        if (run.status !== 'completed' && run.status !== 'not_blessed') {
            return '<span class="ml-card-metric-value empty">Metrics available after completion</span>';
        }

        if (run.model_type === 'multitask') {
            return `
                <div class="ml-card-metrics-multitask">
                    <div class="ml-card-metrics-section">
                        <div class="ml-card-metrics-section-label">
                            <i class="fas fa-search"></i> Retrieval
                        </div>
                        <div class="ml-card-metrics-row">
                            <div class="ml-card-metric">
                                <div class="ml-card-metric-label">R@5</div>
                                <div class="ml-card-metric-value ${run.recall_at_5 == null ? 'empty' : ''}">${formatNumber(run.recall_at_5)}</div>
                            </div>
                            <div class="ml-card-metric">
                                <div class="ml-card-metric-label">R@10</div>
                                <div class="ml-card-metric-value ${run.recall_at_10 == null ? 'empty' : ''}">${formatNumber(run.recall_at_10)}</div>
                            </div>
                            <div class="ml-card-metric">
                                <div class="ml-card-metric-label">R@50</div>
                                <div class="ml-card-metric-value ${run.recall_at_50 == null ? 'empty' : ''}">${formatNumber(run.recall_at_50)}</div>
                            </div>
                            <div class="ml-card-metric">
                                <div class="ml-card-metric-label">R@100</div>
                                <div class="ml-card-metric-value ${run.recall_at_100 == null ? 'empty' : ''}">${formatNumber(run.recall_at_100)}</div>
                            </div>
                        </div>
                    </div>
                    <div class="ml-card-metrics-section">
                        <div class="ml-card-metrics-section-label">
                            <i class="fas fa-star"></i> Ranking
                        </div>
                        <div class="ml-card-metrics-row">
                            <div class="ml-card-metric">
                                <div class="ml-card-metric-label">RMSE</div>
                                <div class="ml-card-metric-value ${run.rmse == null ? 'empty' : ''}">${formatNumber(run.rmse, 4)}</div>
                            </div>
                            <div class="ml-card-metric">
                                <div class="ml-card-metric-label">TEST RMSE</div>
                                <div class="ml-card-metric-value ${run.test_rmse == null ? 'empty' : ''}">${formatNumber(run.test_rmse, 4)}</div>
                            </div>
                            <div class="ml-card-metric">
                                <div class="ml-card-metric-label">MAE</div>
                                <div class="ml-card-metric-value ${run.mae == null ? 'empty' : ''}">${formatNumber(run.mae, 4)}</div>
                            </div>
                            <div class="ml-card-metric">
                                <div class="ml-card-metric-label">TEST MAE</div>
                                <div class="ml-card-metric-value ${run.test_mae == null ? 'empty' : ''}">${formatNumber(run.test_mae, 4)}</div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        } else if (run.model_type === 'ranking') {
            return `
                <div class="ml-card-metrics-row">
                    <div class="ml-card-metric">
                        <div class="ml-card-metric-label">RMSE</div>
                        <div class="ml-card-metric-value ${run.rmse == null ? 'empty' : ''}">${formatNumber(run.rmse, 4)}</div>
                    </div>
                    <div class="ml-card-metric">
                        <div class="ml-card-metric-label">TEST RMSE</div>
                        <div class="ml-card-metric-value ${run.test_rmse == null ? 'empty' : ''}">${formatNumber(run.test_rmse, 4)}</div>
                    </div>
                    <div class="ml-card-metric">
                        <div class="ml-card-metric-label">MAE</div>
                        <div class="ml-card-metric-value ${run.mae == null ? 'empty' : ''}">${formatNumber(run.mae, 4)}</div>
                    </div>
                    <div class="ml-card-metric">
                        <div class="ml-card-metric-label">TEST MAE</div>
                        <div class="ml-card-metric-value ${run.test_mae == null ? 'empty' : ''}">${formatNumber(run.test_mae, 4)}</div>
                    </div>
                </div>
            `;
        } else {
            // Retrieval
            return `
                <div class="ml-card-metrics-row">
                    <div class="ml-card-metric">
                        <div class="ml-card-metric-label">R@5</div>
                        <div class="ml-card-metric-value ${run.recall_at_5 == null ? 'empty' : ''}">${formatNumber(run.recall_at_5)}</div>
                    </div>
                    <div class="ml-card-metric">
                        <div class="ml-card-metric-label">R@10</div>
                        <div class="ml-card-metric-value ${run.recall_at_10 == null ? 'empty' : ''}">${formatNumber(run.recall_at_10)}</div>
                    </div>
                    <div class="ml-card-metric">
                        <div class="ml-card-metric-label">R@50</div>
                        <div class="ml-card-metric-value ${run.recall_at_50 == null ? 'empty' : ''}">${formatNumber(run.recall_at_50)}</div>
                    </div>
                    <div class="ml-card-metric">
                        <div class="ml-card-metric-label">R@100</div>
                        <div class="ml-card-metric-value ${run.recall_at_100 == null ? 'empty' : ''}">${formatNumber(run.recall_at_100)}</div>
                    </div>
                </div>
            `;
        }
    }

    function renderConfigInfo(run) {
        // Format GPU config
        let gpuChip = '';
        // GPU config keys are gpu_type, gpu_count (not accelerator_*)
        if (run.gpu_config && run.gpu_config.gpu_type) {
            const gpuType = run.gpu_config.gpu_type
                .replace('NVIDIA_TESLA_', '')
                .replace('NVIDIA_', '');
            const gpuCount = run.gpu_config.gpu_count || 1;
            gpuChip = `
                <div class="ml-card-gpu-chip">
                    <i class="fas fa-microchip"></i> ${gpuCount}x ${gpuType}
                </div>
            `;
        }

        // Algorithm line (only for retrieval and multitask models)
        let algorithmLine = '';
        if ((run.model_type === 'retrieval' || run.model_type === 'multitask') && run.retrieval_algorithm) {
            const algorithmDisplay = run.retrieval_algorithm === 'scann' ? 'ScaNN' : 'Brute-Force';
            algorithmLine = `<div class="ml-card-config-item"><span class="ml-card-config-label">Algorithm:</span> ${algorithmDisplay}</div>`;
        }

        // Experiment line
        let experimentLine = '';
        if (run.base_experiment_number) {
            experimentLine = `<div class="ml-card-config-item"><span class="ml-card-config-label">Experiment:</span> Exp #${run.base_experiment_number}</div>`;
        }

        return `
            <div class="ml-card-col-config">
                <div class="ml-card-config-item"><span class="ml-card-config-label">Dataset:</span> ${escapeHtml(run.dataset_name || '-')}</div>
                <div class="ml-card-config-item"><span class="ml-card-config-label">Features:</span> ${escapeHtml(run.feature_config_name || '-')}</div>
                <div class="ml-card-config-item"><span class="ml-card-config-label">Model:</span> ${escapeHtml(run.model_config_name || '-')}</div>
                ${algorithmLine}
                ${experimentLine}
                ${gpuChip}
            </div>
        `;
    }

    function renderBadgesRow(run) {
        // Model type badge
        const modelTypeBadge = renderModelTypeBadge(run.model_type);

        // Blessed status badge (for completed/not_blessed runs)
        let blessedBadge = '';
        if (run.status === 'completed' || run.status === 'not_blessed') {
            if (run.is_blessed === true) {
                blessedBadge = `
                    <span class="blessed-status-badge blessed">
                        <i class="fas fa-check-circle"></i> Blessed
                    </span>
                `;
            } else {
                blessedBadge = `
                    <span class="blessed-status-badge not-blessed">
                        <i class="fas fa-times-circle"></i> Not Blessed
                    </span>
                `;
            }
        }

        // Deployment status badge (for completed runs)
        let deployBadge = '';
        if (run.status === 'completed') {
            const deployIcon = run.is_deployed ? 'fa-check-circle' : 'fa-times-circle';
            const deployText = run.is_deployed ? 'Deployed' : 'Not Deployed';
            deployBadge = `
                <span class="deploy-status-badge ${run.is_deployed ? 'deployed' : 'not-deployed'}">
                    <i class="fas ${deployIcon}"></i> ${deployText}
                </span>
            `;
        }

        // Scheduled status badge
        const scheduledIcon = run.is_scheduled ? 'fa-check-circle' : 'fa-times-circle';
        const scheduledText = run.is_scheduled ? 'Scheduled' : 'Not scheduled';
        const scheduledBadge = `
            <span class="scheduled-status-badge ${run.is_scheduled ? 'scheduled' : 'not-scheduled'}">
                <i class="fas ${scheduledIcon}"></i> ${scheduledText}
            </span>
        `;

        return `
            <div class="ml-card-badges-footer">
                ${modelTypeBadge}${blessedBadge}${deployBadge}${scheduledBadge}
            </div>
        `;
    }

    function renderActions(run, allowedActions) {
        // Determine button states based on run status
        const isCancellable = run.status === 'running' || run.status === 'submitting';
        const isTerminalState = ['completed', 'failed', 'cancelled', 'not_blessed'].includes(run.status);
        const canDeploy = run.status === 'completed';
        const canRerun = allowedActions.includes('rerun');
        const canSchedule = isTerminalState; // Schedule available for completed/failed/cancelled runs
        const canEdit = isTerminalState; // Edit available for terminal states
        const canDelete = allowedActions.includes('delete');

        // Build 2-column grid layout:
        // Column 1: Deploy, Rerun, Schedule
        // Column 2: View, Cancel, Edit+Delete

        // Row 1: Deploy | View
        let deployBtn = '';
        if (canDeploy) {
            deployBtn = `<button class="card-action-btn deploy" onclick="event.stopPropagation(); TrainingCards.deployRun(${run.id})" title="Deploy to Vertex AI Endpoint">Deploy</button>`;
        } else {
            // Placeholder for alignment when deploy not available
            deployBtn = `<button class="card-action-btn deploy" disabled title="Deploy available after completion">Deploy</button>`;
        }

        const viewBtn = `<button class="card-action-btn view" onclick="event.stopPropagation(); TrainingCards.viewRun(${run.id})" title="View Details">View</button>`;

        // Row 2: Rerun | Cancel
        let rerunBtn = '';
        if (canRerun) {
            rerunBtn = `<button class="card-action-btn rerun" onclick="event.stopPropagation(); TrainingCards.rerunRun(${run.id})" title="Re-run with same configuration">Rerun</button>`;
        } else {
            rerunBtn = `<button class="card-action-btn rerun" disabled title="Rerun available after completion">Rerun</button>`;
        }

        const cancelBtn = `<button class="card-action-btn cancel" onclick="event.stopPropagation(); TrainingCards.cancelRun(event, ${run.id})" title="Cancel Training" ${isCancellable ? '' : 'disabled'}>Cancel</button>`;

        // Row 3: Schedule | Edit + Delete
        let scheduleBtn = '';
        if (canSchedule) {
            scheduleBtn = `<button class="card-action-btn schedule" onclick="event.stopPropagation(); TrainingCards.scheduleRun(${run.id})" title="Schedule recurring training">Schedule</button>`;
        } else {
            scheduleBtn = `<button class="card-action-btn schedule" disabled title="Schedule available after completion">Schedule</button>`;
        }

        // Edit + Delete icon buttons
        let editDeleteGroup = '<div class="card-action-btn-group">';
        if (canEdit) {
            editDeleteGroup += `<button class="card-action-btn icon-only edit" onclick="event.stopPropagation(); TrainingCards.editRun(${run.id})" title="Edit Training Run"><i class="fas fa-external-link-alt"></i></button>`;
        } else {
            editDeleteGroup += `<button class="card-action-btn icon-only edit" disabled title="Edit available after completion"><i class="fas fa-external-link-alt"></i></button>`;
        }
        if (canDelete) {
            editDeleteGroup += `<button class="card-action-btn icon-only delete" onclick="event.stopPropagation(); TrainingCards.deleteRun(${run.id})" title="Delete Training Run"><i class="fas fa-trash"></i></button>`;
        } else {
            editDeleteGroup += `<button class="card-action-btn icon-only delete" disabled title="Delete available after completion"><i class="fas fa-trash"></i></button>`;
        }
        editDeleteGroup += '</div>';

        return `
            <div class="ml-card-col-actions">
                <div class="ml-card-actions-grid">
                    ${deployBtn}
                    ${viewBtn}
                    ${rerunBtn}
                    ${cancelBtn}
                    ${scheduleBtn}
                    ${editDeleteGroup}
                </div>
            </div>
        `;
    }

    function renderProgress(run) {
        if (run.status !== 'running' && run.status !== 'submitting') {
            return '';
        }

        const progress = run.progress_percent || 0;
        const stage = run.current_stage || 'Initializing';
        const epoch = run.current_epoch;
        const totalEpochs = run.total_epochs;

        let epochInfo = '';
        if (epoch && totalEpochs) {
            epochInfo = ` (Epoch ${epoch}/${totalEpochs})`;
        }

        // Render stage progress bar if we have stage details
        let stageBarHtml = '';
        if (run.stage_details && run.stage_details.length > 0) {
            stageBarHtml = renderStageBar(run.stage_details);
        }

        return `
            <div class="training-card-progress">
                <div class="training-card-progress-info">
                    <span class="training-card-progress-stage">
                        <i class="fas fa-cog fa-spin"></i> ${escapeHtml(stage)}${epochInfo}
                    </span>
                    <span class="training-card-progress-percent">${progress}%</span>
                </div>
                <div class="training-card-progress-bar">
                    <div class="training-card-progress-fill ${progress === 0 ? 'indeterminate' : ''}" style="width: ${progress}%"></div>
                </div>
                ${stageBarHtml}
            </div>
        `;
    }

    function renderStageBar(stageDetails) {
        // Gradient green colors for 8 stages (matching experiments style)
        const completedColors = ['#059669', '#10b981', '#22c55e', '#34d399', '#4ade80', '#6ee7b7', '#a7f3d0', '#d1fae5'];

        const segments = stageDetails.map((stage, idx) => {
            const statusClass = stage.status || 'pending';
            // Apply gradient color for completed stages
            const style = statusClass === 'completed'
                ? `style="background: ${completedColors[idx % completedColors.length]}"`
                : '';
            return `<div class="ml-stage-segment ${statusClass}" ${style} title="${stage.name}">${stage.name || ''}</div>`;
        }).join('');

        return `
            <div class="ml-card-stages">
                <div class="ml-stages-bar">
                    ${segments}
                </div>
            </div>
        `;
    }

    function getDefaultStages() {
        return [
            { name: 'COMPILE', status: 'pending' },
            { name: 'EXAMPLES', status: 'pending' },
            { name: 'STATS', status: 'pending' },
            { name: 'SCHEMA', status: 'pending' },
            { name: 'TRANSFORM', status: 'pending' },
            { name: 'TRAIN', status: 'pending' },
            { name: 'EVALUATOR', status: 'pending' },
            { name: 'PUSHER', status: 'pending' }
        ];
    }

    function renderError(run) {
        if (!run.error_message) {
            return '';
        }

        return `
            <div class="training-card-error">
                <div class="training-card-error-header">
                    <i class="fas fa-exclamation-circle"></i>
                    ${run.error_stage ? `Failed at: ${escapeHtml(run.error_stage)}` : 'Error'}
                </div>
                <div class="training-card-error-message">${escapeHtml(run.error_message)}</div>
            </div>
        `;
    }

    // =============================================================================
    // RENDERING - PAGINATION
    // =============================================================================

    function renderPagination() {
        const container = document.getElementById(config.containers.pagination);
        if (!container) return;

        if (state.pagination.totalPages <= 1) {
            container.innerHTML = '';
            return;
        }

        const { page, totalPages, totalCount, hasPrev, hasNext } = state.pagination;

        container.innerHTML = `
            <div class="training-pagination">
                <button class="training-pagination-btn" onclick="TrainingCards.prevPage()" ${!hasPrev ? 'disabled' : ''}>
                    <i class="fas fa-chevron-left"></i> Previous
                </button>
                <span class="training-pagination-info">
                    Page ${page} of ${totalPages} (${totalCount} total)
                </span>
                <button class="training-pagination-btn" onclick="TrainingCards.nextPage()" ${!hasNext ? 'disabled' : ''}>
                    Next <i class="fas fa-chevron-right"></i>
                </button>
            </div>
        `;
    }

    // =============================================================================
    // RENDERING - LOADING & EMPTY STATES
    // =============================================================================

    function renderSkeletonCards(count = 3) {
        const container = document.getElementById(config.containers.cardsList);
        if (!container) return;

        let html = '';
        for (let i = 0; i < count; i++) {
            html += `
                <div class="training-skeleton-card">
                    <div class="training-skeleton-header">
                        <div class="skeleton-icon"></div>
                        <div class="skeleton-info">
                            <div class="skeleton-title"></div>
                            <div class="skeleton-subtitle"></div>
                        </div>
                        <div class="skeleton-badge"></div>
                    </div>
                    <div class="training-skeleton-body">
                        <div class="skeleton-metrics">
                            <div class="skeleton-metric"></div>
                            <div class="skeleton-metric"></div>
                            <div class="skeleton-metric"></div>
                        </div>
                        <div class="skeleton-actions">
                            <div class="skeleton-btn"></div>
                            <div class="skeleton-btn"></div>
                        </div>
                    </div>
                </div>
            `;
        }
        container.innerHTML = html;
    }

    function showLoading() {
        const loadingEl = document.getElementById(config.containers.loading);
        if (loadingEl) {
            loadingEl.classList.remove('hidden');
        }

        const container = document.getElementById(config.containers.cardsList);
        if (container && container.children.length === 0) {
            renderSkeletonCards(3);
        }
    }

    function hideLoading() {
        const loadingEl = document.getElementById(config.containers.loading);
        if (loadingEl) {
            loadingEl.classList.add('hidden');
        }
    }

    function showEmptyState(message) {
        const container = document.getElementById(config.containers.cardsList);
        const emptyState = document.getElementById(config.containers.emptyState);

        if (container) {
            container.innerHTML = '';
        }

        if (emptyState) {
            emptyState.classList.remove('hidden');
            if (message) {
                const msgEl = emptyState.querySelector('p');
                if (msgEl) {
                    msgEl.textContent = message;
                }
            }
        }
    }

    // =============================================================================
    // ACTIONS
    // =============================================================================

    function viewRun(runId) {
        if (config.onViewRun) {
            config.onViewRun(runId);
        } else if (typeof TrainingViewModal !== 'undefined') {
            TrainingViewModal.open(runId);
        } else {
            console.log('View training run:', runId);
        }
    }

    function cancelRun(event, runId) {
        const btn = event.target.closest('button');
        const originalHtml = btn.innerHTML;

        showConfirmModal({
            title: 'Cancel Training Run',
            message: 'Are you sure you want to cancel this training run?<br><span class="text-sm text-gray-500 mt-2 block">This will stop the Vertex AI pipeline.</span>',
            confirmText: 'Confirm',
            cancelText: 'Cancel',
            type: 'warning',
            confirmButtonClass: 'btn-neu-save',
            cancelButtonClass: 'btn-neu-cancel',
            onConfirm: async () => {
                btn.disabled = true;
                btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

                try {
                    const url = buildUrl(config.endpoints.cancel, { id: runId });
                    const response = await fetch(url, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken')
                        }
                    });

                    const data = await response.json();

                    if (data.success) {
                        await loadTrainingRuns();
                        showToast('Training run cancelled', 'success');
                    } else {
                        showToast(data.error || 'Failed to cancel training run', 'error');
                        btn.disabled = false;
                        btn.innerHTML = originalHtml;
                    }
                } catch (error) {
                    console.error('Error cancelling training run:', error);
                    showToast('Failed to cancel training run', 'error');
                    btn.disabled = false;
                    btn.innerHTML = originalHtml;
                }
            }
        });
    }

    function deleteRun(runId) {
        showConfirmModal({
            title: 'Delete Training Run',
            message: 'Are you sure you want to delete this training run?<br><br><strong>This action cannot be undone.</strong>',
            confirmText: 'Confirm',
            cancelText: 'Cancel',
            type: 'danger',
            confirmButtonClass: 'btn-neu-save',      // Green button
            cancelButtonClass: 'btn-neu-cancel',     // Red button
            onConfirm: async () => {
                try {
                    const url = buildUrl(config.endpoints.delete, { id: runId });
                    const response = await fetch(url, {
                        method: 'DELETE',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken')
                        }
                    });

                    const data = await response.json();

                    if (data.success) {
                        loadTrainingRuns();
                    } else {
                        showToast(data.error || 'Failed to delete training run', 'error');
                    }
                } catch (error) {
                    console.error('Error deleting training run:', error);
                    showToast('Failed to delete training run', 'error');
                }
            }
        });
    }

    async function submitRun(runId) {
        try {
            const url = buildUrl(config.endpoints.submit, { id: runId });
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });

            const data = await response.json();

            if (data.success) {
                loadTrainingRuns();
            } else {
                showToast(data.error || 'Failed to submit training run', 'error');
            }
        } catch (error) {
            console.error('Error submitting training run:', error);
            showToast('Failed to submit training run', 'error');
        }
    }

    async function rerunRun(runId) {
        showConfirmModal({
            title: 'Re-run Training',
            message: 'Create a new training run with the same configuration?',
            confirmText: 'Rerun',
            cancelText: 'Cancel',
            type: 'info',
            confirmButtonClass: 'btn-neu-save',      // Green button
            cancelButtonClass: 'btn-neu-cancel',     // Red button
            onConfirm: async () => {
                try {
                    const url = buildUrl(config.endpoints.rerun, { id: runId });
                    const response = await fetch(url, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken')
                        }
                    });

                    const data = await response.json();

                    if (data.success) {
                        showToast(data.message || 'New training run created', 'success');
                        loadTrainingRuns();
                    } else {
                        showToast(data.error || 'Failed to create re-run', 'error');
                    }
                } catch (error) {
                    console.error('Error creating re-run:', error);
                    showToast('Failed to create re-run', 'error');
                }
            }
        });
    }

    async function deployRun(runId) {
        if (!confirm('Are you sure you want to deploy this model to a Vertex AI Endpoint? This will make the model available for serving predictions.')) {
            return;
        }

        try {
            const url = buildUrl(config.endpoints.deploy, { id: runId });
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });

            const data = await response.json();

            if (data.success) {
                showToast(data.message || 'Model deployed successfully', 'success');
                loadTrainingRuns();
            } else {
                showToast(data.error || 'Failed to deploy model', 'error');
            }
        } catch (error) {
            console.error('Error deploying training run:', error);
            showToast('Failed to deploy model', 'error');
        }
    }

    async function deployRunCloudRun(runId) {
        if (!confirm('Are you sure you want to deploy this model to Cloud Run? This will create a serverless TF Serving endpoint.')) {
            return;
        }

        try {
            const url = buildUrl(config.endpoints.deployCloudRun, { id: runId });
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });

            const data = await response.json();

            if (data.success) {
                showToast(data.message || 'Model deployed to Cloud Run', 'success');
                loadTrainingRuns();
            } else {
                showToast(data.error || 'Failed to deploy model to Cloud Run', 'error');
            }
        } catch (error) {
            console.error('Error deploying training run to Cloud Run:', error);
            showToast('Failed to deploy model to Cloud Run', 'error');
        }
    }

    async function pushAnyway(runId) {
        if (!confirm('This model did not meet the blessing threshold. Are you sure you want to push it to the Model Registry anyway? This action cannot be undone.')) {
            return;
        }

        try {
            const url = buildUrl(config.endpoints.push, { id: runId });
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });

            const data = await response.json();

            if (data.success) {
                showToast(data.message || 'Model pushed to registry', 'success');
                loadTrainingRuns();
            } else {
                showToast(data.error || 'Failed to push model', 'error');
            }
        } catch (error) {
            console.error('Error pushing model:', error);
            showToast('Failed to push model', 'error');
        }
    }

    function scheduleRun(runId) {
        // Configure the schedule modal with success callback
        if (typeof ScheduleModal !== 'undefined') {
            ScheduleModal.configure({
                onSuccess: function(schedule) {
                    showToast(`Schedule "${schedule.name}" created successfully`, 'success');
                    // Refresh training runs to show updated schedule status
                    loadTrainingRuns();
                    // Also refresh schedules list if available
                    if (typeof TrainingSchedules !== 'undefined') {
                        TrainingSchedules.loadSchedules();
                    }
                }
            });
            ScheduleModal.openForTrainingRun(runId);
        } else {
            // Fallback if ScheduleModal not loaded
            showConfirmModal({
                title: 'Schedule Training Run',
                message: 'Schedule modal is not available. Please refresh the page.',
                confirmText: 'OK',
                cancelText: 'Cancel',
                type: 'info',
                confirmButtonClass: 'btn-neu-nav-wide',
                onConfirm: () => {}
            });
        }
    }

    function editRun(runId) {
        // Open the training wizard in edit mode
        if (typeof TrainingWizard !== 'undefined' && TrainingWizard.openForEdit) {
            TrainingWizard.openForEdit(runId);
        } else {
            showToast('Edit feature not available', 'error');
        }
    }

    // =============================================================================
    // UTILITY - HTML ESCAPING
    // =============================================================================

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // =============================================================================
    // PUBLIC API
    // =============================================================================

    return {
        configure: configure,
        init: init,
        loadTrainingRuns: loadTrainingRuns,
        refresh: refresh,
        filterByStatus: filterByStatus,
        filterByModelType: filterByModelType,
        filterByModelName: filterByModelName,
        search: search,
        clearFilters: clearFilters,
        handleSearchInput: handleSearchInput,
        nextPage: nextPage,
        prevPage: prevPage,
        goToPage: goToPage,
        viewRun: viewRun,
        cancelRun: cancelRun,
        deleteRun: deleteRun,
        submitRun: submitRun,
        rerunRun: rerunRun,
        deployRun: deployRun,
        deployRunCloudRun: deployRunCloudRun,
        pushAnyway: pushAnyway,
        scheduleRun: scheduleRun,
        editRun: editRun,
        stopPolling: stopPolling,
        // Shared UI utilities
        showConfirmModal: showConfirmModal,
        hideConfirmModal: hideConfirmModal,
        showToast: showToast,
        // Expose state for debugging
        getState: function() { return state; }
    };
})();


/**
 * Training Schedules Module
 *
 * Handles displaying and managing training schedules (recurring/one-time).
 */
const TrainingSchedules = (function() {
    'use strict';

    // =============================================================================
    // CONFIGURATION & STATE
    // =============================================================================

    let config = {
        endpoints: {
            list: '/api/training/schedules/',
            detail: '/api/training/schedules/{id}/',
            pause: '/api/training/schedules/{id}/pause/',
            resume: '/api/training/schedules/{id}/resume/',
            cancel: '/api/training/schedules/{id}/cancel/',
            trigger: '/api/training/schedules/{id}/trigger/'
        }
    };

    let state = {
        schedules: [],
        isCollapsed: false,
        isLoading: false
    };

    const STATUS_CONFIG = {
        active: { icon: 'fa-play-circle', label: 'Active', color: '#16a34a' },
        paused: { icon: 'fa-pause-circle', label: 'Paused', color: '#f59e0b' },
        completed: { icon: 'fa-check-circle', label: 'Completed', color: '#6b7280' },
        cancelled: { icon: 'fa-times-circle', label: 'Cancelled', color: '#dc2626' }
    };

    const SCHEDULE_TYPE_LABELS = {
        once: 'One-time',
        hourly: 'Hourly',
        daily: 'Daily',
        weekly: 'Weekly',
        monthly: 'Monthly'
    };

    const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

    // =============================================================================
    // UTILITY FUNCTIONS
    // =============================================================================

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

    function buildUrl(template, params) {
        let url = template;
        for (const [key, value] of Object.entries(params)) {
            url = url.replace(`{${key}}`, value);
        }
        return url;
    }

    function formatDateTime(isoString) {
        if (!isoString) return '-';
        const date = new Date(isoString);
        return date.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    function formatScheduleDescription(schedule) {
        if (schedule.schedule_type === 'once') {
            return `Scheduled for ${formatDateTime(schedule.scheduled_datetime)}`;
        } else if (schedule.schedule_type === 'daily') {
            return `Daily at ${schedule.schedule_time || '09:00'} ${schedule.schedule_timezone}`;
        } else if (schedule.schedule_type === 'weekly') {
            const day = DAY_NAMES[schedule.schedule_day_of_week] || 'Monday';
            return `${day}s at ${schedule.schedule_time || '09:00'} ${schedule.schedule_timezone}`;
        }
        return '';
    }

    // Use the TrainingCards modal for consistent UI
    function showToast(message, type = 'success') {
        if (typeof TrainingCards !== 'undefined' && TrainingCards.showConfirmModal) {
            TrainingCards.showConfirmModal({
                title: type === 'success' ? 'Success' : 'Error',
                message: message,
                type: type === 'success' ? 'success' : 'danger',
                confirmText: 'Close',
                hideCancel: true,
                autoClose: type === 'success' ? 4000 : 0,
                onConfirm: () => {}
            });
        } else {
            alert(message);
        }
    }

    // =============================================================================
    // DATA LOADING
    // =============================================================================

    async function loadSchedules() {
        state.isLoading = true;
        try {
            const response = await fetch(`${config.endpoints.list}?status=active`);
            const data = await response.json();

            if (data.success && data.schedules) {
                state.schedules = data.schedules;
                renderSchedules();
            }
        } catch (error) {
            console.error('Failed to load schedules:', error);
        } finally {
            state.isLoading = false;
        }
    }

    // =============================================================================
    // RENDERING
    // =============================================================================

    function renderSchedules() {
        const section = document.getElementById('trainingSchedulesSection');
        const list = document.getElementById('schedulesList');

        if (!section || !list) return;

        // Also load paused schedules
        loadAllSchedules();
    }

    async function loadAllSchedules() {
        try {
            // Load both active and paused schedules
            const response = await fetch(config.endpoints.list);
            const data = await response.json();

            if (data.success && data.schedules) {
                // Filter to only show active and paused
                state.schedules = data.schedules.filter(
                    s => s.status === 'active' || s.status === 'paused'
                );
                renderSchedulesList();
            }
        } catch (error) {
            console.error('Failed to load schedules:', error);
        }
    }

    function renderSchedulesList() {
        const section = document.getElementById('trainingSchedulesSection');
        const list = document.getElementById('schedulesList');

        if (!section || !list) return;

        if (state.schedules.length === 0) {
            section.classList.add('hidden');
            return;
        }

        section.classList.remove('hidden');

        const html = state.schedules.map(schedule => {
            const statusConfig = STATUS_CONFIG[schedule.status] || STATUS_CONFIG.active;
            const typeLabel = SCHEDULE_TYPE_LABELS[schedule.schedule_type] || schedule.schedule_type;
            const modelName = schedule.registered_model_name || '-';

            return `
                <div class="schedule-card ${schedule.status}">
                    <div class="schedule-card-header">
                        <div class="schedule-card-icon">
                            <i class="fas fa-calendar-alt"></i>
                        </div>
                        <div class="schedule-card-info">
                            <div class="schedule-card-name">${schedule.name}</div>
                            <div class="schedule-card-desc">${formatScheduleDescription(schedule)}</div>
                        </div>
                    </div>
                    <div class="schedule-card-stats">
                        <div class="schedule-stat">
                            <span class="schedule-stat-label">Model</span>
                            <span class="schedule-stat-value schedule-model-name" title="${modelName}">${modelName}</span>
                        </div>
                        <div class="schedule-stat">
                            <span class="schedule-stat-label">Type</span>
                            <span class="schedule-stat-value schedule-type-value">${typeLabel}</span>
                        </div>
                        <div class="schedule-stat">
                            <span class="schedule-stat-label">Last Run</span>
                            <span class="schedule-stat-value">${schedule.last_run_at ? formatDateTime(schedule.last_run_at) : '-'}</span>
                        </div>
                        <div class="schedule-stat">
                            <span class="schedule-stat-label">Next Run</span>
                            <span class="schedule-stat-value">${schedule.next_run_at ? formatDateTime(schedule.next_run_at) : '-'}</span>
                        </div>
                        <div class="schedule-stat">
                            <span class="schedule-stat-label">Total Runs</span>
                            <span class="schedule-stat-value">${schedule.total_runs}</span>
                        </div>
                        <div class="schedule-stat">
                            <span class="schedule-stat-label">Success Rate</span>
                            <span class="schedule-stat-value">${schedule.success_rate != null ? schedule.success_rate + '%' : '-'}</span>
                        </div>
                        <div class="schedule-stat">
                            <span class="schedule-stat-label">Status</span>
                            <span class="schedule-stat-value" style="color: ${statusConfig.color}">
                                <i class="fas ${statusConfig.icon}"></i> ${statusConfig.label}
                            </span>
                        </div>
                    </div>
                    <div class="schedule-card-actions">
                        <button class="card-action-btn run" onclick="TrainingSchedules.triggerNow(${schedule.id})" title="Run Now">
                            <i class="fas fa-play"></i>
                        </button>
                        ${schedule.status === 'active' ? `
                            <button class="card-action-btn pause-large" onclick="TrainingSchedules.pauseSchedule(${schedule.id})" title="Pause Schedule">
                                <i class="fas fa-pause"></i>
                            </button>
                        ` : `
                            <button class="card-action-btn resume-large" onclick="TrainingSchedules.resumeSchedule(${schedule.id})" title="Resume Schedule">
                                <i class="fas fa-play-circle"></i>
                            </button>
                        `}
                        <button class="card-action-btn delete" onclick="TrainingSchedules.deleteSchedule(${schedule.id})" title="Delete Schedule">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            `;
        }).join('');

        list.innerHTML = html;
    }

    // =============================================================================
    // ACTIONS
    // =============================================================================

    async function pauseSchedule(scheduleId) {
        try {
            const url = buildUrl(config.endpoints.pause, { id: scheduleId });
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });
            const data = await response.json();
            if (data.success) {
                loadAllSchedules();
            } else {
                showToast('Failed to pause schedule: ' + (data.error || 'Unknown error'), 'error');
            }
        } catch (error) {
            console.error('Failed to pause schedule:', error);
            showToast('Failed to pause schedule', 'error');
        }
    }

    async function resumeSchedule(scheduleId) {
        try {
            const url = buildUrl(config.endpoints.resume, { id: scheduleId });
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });
            const data = await response.json();
            if (data.success) {
                loadAllSchedules();
            } else {
                showToast('Failed to resume schedule: ' + (data.error || 'Unknown error'), 'error');
            }
        } catch (error) {
            console.error('Failed to resume schedule:', error);
            showToast('Failed to resume schedule', 'error');
        }
    }

    function deleteSchedule(scheduleId) {
        TrainingCards.showConfirmModal({
            title: 'Delete Schedule',
            message: 'Are you sure you want to delete this schedule?<br><br>This will permanently remove the schedule and its Cloud Scheduler job.',
            confirmText: 'Delete',
            cancelText: 'Cancel',
            type: 'danger',
            confirmButtonClass: 'btn-neu-save',      // Green button
            cancelButtonClass: 'btn-neu-cancel',     // Red button
            onConfirm: async () => {
                try {
                    const url = buildUrl(config.endpoints.detail, { id: scheduleId });
                    const response = await fetch(url, {
                        method: 'DELETE',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken')
                        }
                    });
                    const data = await response.json();
                    if (data.success) {
                        showToast('Schedule deleted successfully', 'success');
                        loadAllSchedules();
                    } else {
                        showToast('Failed to delete schedule: ' + (data.error || 'Unknown error'), 'error');
                    }
                } catch (error) {
                    console.error('Failed to delete schedule:', error);
                    showToast('Failed to delete schedule', 'error');
                }
            }
        });
    }

    function triggerNow(scheduleId) {
        TrainingCards.showConfirmModal({
            title: 'Run Training Now',
            message: 'Are you sure you want to run this training immediately?<br><br>A new training run will be started.',
            confirmText: 'Run',
            cancelText: 'Cancel',
            type: 'info',
            confirmButtonClass: 'btn-neu-save',      // Green button
            cancelButtonClass: 'btn-neu-cancel',     // Red button
            onConfirm: async () => {
                try {
                    const url = buildUrl(config.endpoints.trigger, { id: scheduleId });
                    const response = await fetch(url, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken')
                        }
                    });
                    const data = await response.json();
                    if (data.success) {
                        showToast('Training run triggered successfully!', 'success');
                        loadAllSchedules();
                        // Also refresh training runs
                        if (typeof TrainingCards !== 'undefined') {
                            TrainingCards.refresh();
                        }
                    } else {
                        showToast('Failed to trigger schedule: ' + (data.error || 'Unknown error'), 'error');
                    }
                } catch (error) {
                    console.error('Failed to trigger schedule:', error);
                    showToast('Failed to trigger schedule', 'error');
                }
            }
        });
    }

    function toggleSection() {
        state.isCollapsed = !state.isCollapsed;
        const list = document.getElementById('schedulesList');
        const btn = document.querySelector('.schedules-toggle-btn i');

        if (list) {
            list.classList.toggle('collapsed', state.isCollapsed);
        }
        if (btn) {
            btn.className = state.isCollapsed ? 'fas fa-chevron-down' : 'fas fa-chevron-up';
        }
    }

    // =============================================================================
    // INITIALIZATION
    // =============================================================================

    function init() {
        loadAllSchedules();
    }

    // =============================================================================
    // PUBLIC API
    // =============================================================================

    return {
        init: init,
        loadSchedules: loadAllSchedules,
        pauseSchedule: pauseSchedule,
        resumeSchedule: resumeSchedule,
        deleteSchedule: deleteSchedule,
        triggerNow: triggerNow,
        toggleSection: toggleSection
    };
})();
