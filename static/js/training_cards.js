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
            cancel: '/api/training-runs/{id}/cancel/',
            delete: '/api/training-runs/{id}/delete/',
            submit: '/api/training-runs/{id}/submit/',
            retry: '/api/training-runs/{id}/retry/',
            deploy: '/api/training-runs/{id}/deploy/',
            push: '/api/training-runs/{id}/push/'
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
        isLoading: false
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
            icon: 'fa-upload',
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
            actions: ['view', 'deploy', 'delete']
        },
        failed: {
            icon: 'fa-times-circle',
            label: 'Failed',
            spin: false,
            actions: ['view', 'retry', 'delete']
        },
        cancelled: {
            icon: 'fa-ban',
            label: 'Cancelled',
            spin: false,
            actions: ['view', 'delete']
        },
        not_blessed: {
            icon: 'fa-exclamation-triangle',
            label: 'Not Blessed',
            spin: false,
            actions: ['view', 'push', 'delete']
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
        const now = new Date();
        const diff = now - date;

        // If less than 24 hours, show relative time
        if (diff < 86400000) {
            if (diff < 60000) return 'Just now';
            if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
            return `${Math.floor(diff / 3600000)}h ago`;
        }

        // Otherwise show date
        return date.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    function showToast(message, type = 'success') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 8px;
            color: white;
            font-size: 14px;
            z-index: 10000;
            animation: slideIn 0.3s ease;
            background-color: ${type === 'success' ? '#16a34a' : '#dc2626'};
        `;
        toast.textContent = message;
        document.body.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
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

        showLoading();

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
            // Start polling
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

    function search(query) {
        state.filters.search = query;
        state.pagination.page = 1;
        loadTrainingRuns();
    }

    function clearFilters() {
        state.filters = { status: null, modelType: null, search: '' };
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

                <input type="text" id="trainingSearchInput" class="training-search-input"
                       placeholder="Search training runs..." oninput="TrainingCards.handleSearchInput(this.value)">
            </div>
        `;
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
        const iconClass = statusConfig.spin ? 'fa-spin' : '';

        // Model type badge
        const modelTypeBadge = renderModelTypeBadge(run.model_type);

        // Metrics section
        const metricsHtml = renderMetrics(run);

        // Config info
        const configHtml = renderConfigInfo(run);

        // Actions
        const actionsHtml = renderActions(run, statusConfig.actions);

        // Progress section (for running/submitting)
        const progressHtml = renderProgress(run);

        // Error section (for failed)
        const errorHtml = run.status === 'failed' ? renderError(run) : '';

        // Badges (deployed, blessed)
        const badgesHtml = renderBadges(run);

        return `
            <div class="training-card status-${run.status}" data-run-id="${run.id}" onclick="TrainingCards.viewRun(${run.id})">
                <div class="training-card-header">
                    <div class="training-card-status-icon ${run.status}">
                        <i class="fas ${statusConfig.icon} ${iconClass}"></i>
                    </div>
                    <div class="training-card-info">
                        <div class="training-card-name">
                            ${escapeHtml(run.name)}
                            <span class="training-card-run-number">#${run.run_number}</span>
                            ${modelTypeBadge}
                            ${badgesHtml}
                        </div>
                        ${run.description ? `<div class="training-card-description">${escapeHtml(run.description)}</div>` : ''}
                        <div class="training-card-meta">
                            <span><i class="fas fa-calendar"></i> ${formatDate(run.created_at)}</span>
                            ${run.elapsed_seconds ? `<span><i class="fas fa-clock"></i> ${formatDuration(run.elapsed_seconds)}</span>` : ''}
                            ${run.created_by ? `<span><i class="fas fa-user"></i> ${escapeHtml(run.created_by)}</span>` : ''}
                        </div>
                    </div>
                    <div class="training-card-badge ${run.status}">
                        <i class="fas ${statusConfig.icon} ${iconClass}"></i>
                        ${statusConfig.label}
                    </div>
                </div>

                <div class="training-card-body">
                    ${configHtml}
                    ${metricsHtml}
                    ${actionsHtml}
                </div>

                ${progressHtml}
                ${errorHtml}
            </div>
        `;
    }

    function renderModelTypeBadge(modelType) {
        const icons = {
            retrieval: 'fa-search',
            ranking: 'fa-sort-amount-down',
            multitask: 'fa-layer-group'
        };
        const icon = icons[modelType] || icons.retrieval;
        return `
            <span class="training-card-type-badge ${modelType}">
                <i class="fas ${icon}"></i>
                ${modelType}
            </span>
        `;
    }

    function renderBadges(run) {
        let badges = '';

        if (run.is_deployed) {
            badges += `
                <span class="training-card-deployed-badge">
                    <i class="fas fa-rocket"></i> Deployed
                </span>
            `;
        }

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
            return '<div class="training-card-metrics"><span class="training-card-metric-value empty">Metrics available after completion</span></div>';
        }

        if (run.model_type === 'multitask') {
            return `
                <div class="training-card-metrics-multitask">
                    <div class="training-card-metrics-section">
                        <div class="training-card-metrics-section-label">
                            <i class="fas fa-search"></i> Retrieval
                        </div>
                        <div class="training-card-metrics">
                            <div class="training-card-metric">
                                <div class="training-card-metric-label">R@50</div>
                                <div class="training-card-metric-value ${run.recall_at_50 == null ? 'empty' : ''}">${formatNumber(run.recall_at_50)}</div>
                            </div>
                            <div class="training-card-metric">
                                <div class="training-card-metric-label">R@100</div>
                                <div class="training-card-metric-value ${run.recall_at_100 == null ? 'empty' : ''}">${formatNumber(run.recall_at_100)}</div>
                            </div>
                        </div>
                    </div>
                    <div class="training-card-metrics-section">
                        <div class="training-card-metrics-section-label">
                            <i class="fas fa-sort-amount-down"></i> Ranking
                        </div>
                        <div class="training-card-metrics">
                            <div class="training-card-metric">
                                <div class="training-card-metric-label">RMSE</div>
                                <div class="training-card-metric-value ${run.rmse == null ? 'empty' : ''}">${formatNumber(run.rmse, 4)}</div>
                            </div>
                            <div class="training-card-metric">
                                <div class="training-card-metric-label">MAE</div>
                                <div class="training-card-metric-value ${run.mae == null ? 'empty' : ''}">${formatNumber(run.mae, 4)}</div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        } else if (run.model_type === 'ranking') {
            return `
                <div class="training-card-metrics">
                    <div class="training-card-metric">
                        <div class="training-card-metric-label">RMSE</div>
                        <div class="training-card-metric-value ${run.rmse == null ? 'empty' : ''}">${formatNumber(run.rmse, 4)}</div>
                    </div>
                    <div class="training-card-metric">
                        <div class="training-card-metric-label">Test RMSE</div>
                        <div class="training-card-metric-value ${run.test_rmse == null ? 'empty' : ''}">${formatNumber(run.test_rmse, 4)}</div>
                    </div>
                    <div class="training-card-metric">
                        <div class="training-card-metric-label">MAE</div>
                        <div class="training-card-metric-value ${run.mae == null ? 'empty' : ''}">${formatNumber(run.mae, 4)}</div>
                    </div>
                </div>
            `;
        } else {
            // Retrieval
            return `
                <div class="training-card-metrics">
                    <div class="training-card-metric">
                        <div class="training-card-metric-label">R@5</div>
                        <div class="training-card-metric-value ${run.recall_at_5 == null ? 'empty' : ''}">${formatNumber(run.recall_at_5)}</div>
                    </div>
                    <div class="training-card-metric">
                        <div class="training-card-metric-label">R@10</div>
                        <div class="training-card-metric-value ${run.recall_at_10 == null ? 'empty' : ''}">${formatNumber(run.recall_at_10)}</div>
                    </div>
                    <div class="training-card-metric">
                        <div class="training-card-metric-label">R@50</div>
                        <div class="training-card-metric-value ${run.recall_at_50 == null ? 'empty' : ''}">${formatNumber(run.recall_at_50)}</div>
                    </div>
                    <div class="training-card-metric">
                        <div class="training-card-metric-label">R@100</div>
                        <div class="training-card-metric-value ${run.recall_at_100 == null ? 'empty' : ''}">${formatNumber(run.recall_at_100)}</div>
                    </div>
                </div>
            `;
        }
    }

    function renderConfigInfo(run) {
        return `
            <div class="training-card-config">
                <div class="training-card-config-item">
                    <span class="training-card-config-label">Dataset:</span> ${escapeHtml(run.dataset_name || '-')}
                </div>
                <div class="training-card-config-item">
                    <span class="training-card-config-label">Features:</span> ${escapeHtml(run.feature_config_name || '-')}
                </div>
                <div class="training-card-config-item">
                    <span class="training-card-config-label">Model:</span> ${escapeHtml(run.model_config_name || '-')}
                </div>
            </div>
        `;
    }

    function renderActions(run, allowedActions) {
        const buttons = [];

        // View button - always available
        buttons.push(`
            <button class="training-card-btn" onclick="event.stopPropagation(); TrainingCards.viewRun(${run.id})" title="View Details">
                <i class="fas fa-eye"></i> View
            </button>
        `);

        // Submit button (for pending/scheduled)
        if (allowedActions.includes('submit') && (run.status === 'pending' || run.status === 'scheduled')) {
            buttons.push(`
                <button class="training-card-btn btn-primary" onclick="event.stopPropagation(); TrainingCards.submitRun(${run.id})" title="Submit to Vertex AI">
                    <i class="fas fa-play"></i> Run Now
                </button>
            `);
        }

        // Cancel button (for pending/scheduled/submitting/running)
        if (allowedActions.includes('cancel')) {
            buttons.push(`
                <button class="training-card-btn btn-danger" onclick="event.stopPropagation(); TrainingCards.cancelRun(${run.id})" title="Cancel Training">
                    <i class="fas fa-stop"></i> Cancel
                </button>
            `);
        }

        // Deploy button (for completed)
        if (allowedActions.includes('deploy') && run.status === 'completed' && run.is_blessed && !run.is_deployed) {
            buttons.push(`
                <button class="training-card-btn btn-success" onclick="event.stopPropagation(); TrainingCards.deployRun(${run.id})" title="Deploy to Endpoint">
                    <i class="fas fa-rocket"></i> Deploy
                </button>
            `);
        }

        // Push button (for not_blessed)
        if (allowedActions.includes('push') && run.status === 'not_blessed') {
            buttons.push(`
                <button class="training-card-btn btn-warning" onclick="event.stopPropagation(); TrainingCards.pushAnyway(${run.id})" title="Push to Registry Anyway">
                    <i class="fas fa-upload"></i> Push Anyway
                </button>
            `);
        }

        // Retry button (for failed)
        if (allowedActions.includes('retry') && run.status === 'failed') {
            buttons.push(`
                <button class="training-card-btn btn-warning" onclick="event.stopPropagation(); TrainingCards.retryRun(${run.id})" title="Retry Training">
                    <i class="fas fa-redo"></i> Retry
                </button>
            `);
        }

        // Delete button (for terminal states)
        if (allowedActions.includes('delete')) {
            buttons.push(`
                <button class="training-card-btn btn-danger" onclick="event.stopPropagation(); TrainingCards.deleteRun(${run.id})" title="Delete Training Run">
                    <i class="fas fa-trash"></i>
                </button>
            `);
        }

        return `
            <div class="training-card-actions">
                <div class="training-card-actions-row">
                    ${buttons.join('')}
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
        const segments = stageDetails.map(stage => {
            const statusClass = stage.status || 'pending';
            return `<div class="training-stage-segment ${statusClass}">${stage.name || ''}</div>`;
        }).join('');

        return `
            <div class="training-card-stages">
                <div class="training-stages-bar">
                    ${segments}
                </div>
            </div>
        `;
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

        // Show skeleton cards if the container is empty
        const container = document.getElementById(config.containers.cardsList);
        if (container && container.children.length === 0) {
            renderSkeletonCards(3);
        }

        // Add loading class to refresh button
        const refreshBtn = document.querySelector('.training-refresh-btn');
        if (refreshBtn) {
            refreshBtn.classList.add('loading');
        }
    }

    function hideLoading() {
        const loadingEl = document.getElementById(config.containers.loading);
        if (loadingEl) {
            loadingEl.classList.add('hidden');
        }

        // Remove loading class from refresh button
        const refreshBtn = document.querySelector('.training-refresh-btn');
        if (refreshBtn) {
            refreshBtn.classList.remove('loading');
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

    async function cancelRun(runId) {
        if (!confirm('Are you sure you want to cancel this training run?')) {
            return;
        }

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
                showToast('Training run cancelled', 'success');
                loadTrainingRuns();
            } else {
                showToast(data.error || 'Failed to cancel training run', 'error');
            }
        } catch (error) {
            console.error('Error cancelling training run:', error);
            showToast('Failed to cancel training run', 'error');
        }
    }

    async function deleteRun(runId) {
        if (!confirm('Are you sure you want to delete this training run? This action cannot be undone.')) {
            return;
        }

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
                showToast('Training run deleted', 'success');
                loadTrainingRuns();
            } else {
                showToast(data.error || 'Failed to delete training run', 'error');
            }
        } catch (error) {
            console.error('Error deleting training run:', error);
            showToast('Failed to delete training run', 'error');
        }
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
                showToast('Training run submitted to Vertex AI', 'success');
                loadTrainingRuns();
            } else {
                showToast(data.error || 'Failed to submit training run', 'error');
            }
        } catch (error) {
            console.error('Error submitting training run:', error);
            showToast('Failed to submit training run', 'error');
        }
    }

    async function retryRun(runId) {
        if (!confirm('Are you sure you want to retry this failed training run? This will create a new training run with the same configuration.')) {
            return;
        }

        try {
            const url = buildUrl(config.endpoints.retry, { id: runId });
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });

            const data = await response.json();

            if (data.success) {
                showToast(data.message || 'Retry created and submitted', 'success');
                loadTrainingRuns();
            } else {
                showToast(data.error || 'Failed to retry training run', 'error');
            }
        } catch (error) {
            console.error('Error retrying training run:', error);
            showToast('Failed to retry training run', 'error');
        }
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
        retryRun: retryRun,
        deployRun: deployRun,
        pushAnyway: pushAnyway,
        stopPolling: stopPolling,
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
        daily: 'Daily',
        weekly: 'Weekly'
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

    function showToast(message, type = 'success') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 8px;
            color: white;
            font-size: 14px;
            z-index: 10000;
            animation: slideIn 0.3s ease;
            background-color: ${type === 'success' ? '#16a34a' : type === 'error' ? '#dc2626' : '#3b82f6'};
        `;
        toast.textContent = message;
        document.body.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
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
                        <div class="schedule-card-badge ${schedule.schedule_type}">
                            ${typeLabel}
                        </div>
                    </div>
                    <div class="schedule-card-stats">
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
                        ${schedule.status === 'active' ? `
                            <button class="schedule-action-btn" onclick="TrainingSchedules.triggerNow(${schedule.id})" title="Run Now">
                                <i class="fas fa-play"></i>
                            </button>
                            <button class="schedule-action-btn" onclick="TrainingSchedules.pauseSchedule(${schedule.id})" title="Pause">
                                <i class="fas fa-pause"></i>
                            </button>
                        ` : ''}
                        ${schedule.status === 'paused' ? `
                            <button class="schedule-action-btn" onclick="TrainingSchedules.resumeSchedule(${schedule.id})" title="Resume">
                                <i class="fas fa-play"></i>
                            </button>
                        ` : ''}
                        <button class="schedule-action-btn danger" onclick="TrainingSchedules.cancelSchedule(${schedule.id})" title="Cancel">
                            <i class="fas fa-times"></i>
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

    async function cancelSchedule(scheduleId) {
        if (!confirm('Are you sure you want to cancel this schedule? This will delete the Cloud Scheduler job.')) {
            return;
        }

        try {
            const url = buildUrl(config.endpoints.cancel, { id: scheduleId });
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
                showToast('Failed to cancel schedule: ' + (data.error || 'Unknown error'), 'error');
            }
        } catch (error) {
            console.error('Failed to cancel schedule:', error);
            showToast('Failed to cancel schedule', 'error');
        }
    }

    async function triggerNow(scheduleId) {
        if (!confirm('Are you sure you want to trigger this schedule now?')) {
            return;
        }

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
        cancelSchedule: cancelSchedule,
        triggerNow: triggerNow,
        toggleSection: toggleSection
    };
})();
