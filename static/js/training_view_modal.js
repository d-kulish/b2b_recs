/**
 * Training View Modal Module
 *
 * A modal component for displaying training run details,
 * styled similar to the experiment view modal.
 *
 * Usage:
 *     // Open modal for a training run
 *     TrainingViewModal.open(trainingRunId);
 *
 *     // Close modal
 *     TrainingViewModal.close();
 *
 * Tabs:
 *   - Overview: Config summary, final metrics, comparison vs base experiment
 *   - Pipeline: 8-stage DAG (Compile, Examples, Stats, Schema, Transform, Train, Evaluate, Push)
 *   - Training: Loss/metrics charts from training_history_json
 *   - Artifacts: GCS paths, Vertex Model Registry links
 *   - Logs: Pipeline logs (future)
 */

const TrainingViewModal = (function() {
    'use strict';

    // =============================================================================
    // CONFIGURATION & STATE
    // =============================================================================

    let config = {
        endpoints: {
            trainingRunDetails: '/api/training-runs/{id}/'
        },
        showTabs: ['overview', 'pipeline', 'training', 'artifacts'],
        onClose: null,
        onUpdate: null
    };

    let state = {
        runId: null,
        currentRun: null,
        currentTab: 'overview',
        pollInterval: null
    };

    // Chart instances
    let charts = {
        lossChart: null,
        metricsChart: null
    };

    // Pipeline stages
    const PIPELINE_STAGES = [
        { id: 'compile', name: 'Compile', icon: 'fa-cog' },
        { id: 'examples', name: 'Examples', icon: 'fa-database' },
        { id: 'stats', name: 'Stats', icon: 'fa-chart-bar' },
        { id: 'schema', name: 'Schema', icon: 'fa-sitemap' },
        { id: 'transform', name: 'Transform', icon: 'fa-exchange-alt' },
        { id: 'train', name: 'Train', icon: 'fa-graduation-cap' },
        { id: 'evaluate', name: 'Evaluate', icon: 'fa-check-double' },
        { id: 'push', name: 'Push', icon: 'fa-upload' }
    ];

    // Status configuration
    const STATUS_CONFIG = {
        pending: { icon: 'fa-hourglass-start', color: '#9ca3af', label: 'Pending' },
        scheduled: { icon: 'fa-clock', color: '#f59e0b', label: 'Scheduled' },
        submitting: { icon: 'fa-upload', color: '#3b82f6', label: 'Submitting' },
        running: { icon: 'fa-sync', color: '#3b82f6', label: 'Running' },
        completed: { icon: 'fa-check-circle', color: '#10b981', label: 'Completed' },
        failed: { icon: 'fa-times-circle', color: '#ef4444', label: 'Failed' },
        cancelled: { icon: 'fa-ban', color: '#6b7280', label: 'Cancelled' },
        not_blessed: { icon: 'fa-exclamation-triangle', color: '#f97316', label: 'Not Blessed' }
    };

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

    function formatDateTime(isoStr) {
        if (!isoStr) return '-';
        const d = new Date(isoStr);
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) + ' ' +
               d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    }

    function formatNumber(val, decimals = 3) {
        if (val === null || val === undefined) return '-';
        if (typeof val !== 'number') return val;
        if (Math.abs(val) >= 1000000) return (val / 1000000).toFixed(2) + 'M';
        if (Math.abs(val) >= 1000) return (val / 1000).toFixed(2) + 'K';
        if (Number.isInteger(val)) return val.toLocaleString();
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

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // =============================================================================
    // MODAL OPEN/CLOSE
    // =============================================================================

    function configure(options) {
        config = { ...config, ...options };
        if (options.endpoints) {
            config.endpoints = { ...config.endpoints, ...options.endpoints };
        }
    }

    async function open(runId) {
        state.runId = runId;
        state.currentTab = 'overview';

        // Create modal if it doesn't exist
        ensureModalExists();

        // Show modal immediately with loading state
        const modal = document.getElementById('trainingViewModal');
        if (modal) {
            modal.classList.remove('hidden');
            showLoadingState();
        }

        // Load training run data
        try {
            const url = buildUrl(config.endpoints.trainingRunDetails, { id: runId });
            const response = await fetch(url);
            const data = await response.json();

            if (!data.success) {
                console.error('Failed to load training run:', data.error);
                showErrorState(data.error || 'Failed to load training run');
                return;
            }

            state.currentRun = data.training_run;
            renderModal();

            // Start polling if running/submitting
            if (state.currentRun.status === 'running' || state.currentRun.status === 'submitting') {
                startPolling();
            }
        } catch (error) {
            console.error('Error loading training run:', error);
            showErrorState('Error loading training run');
        }
    }

    function close() {
        const modal = document.getElementById('trainingViewModal');
        if (modal) {
            modal.classList.add('hidden');
        }

        // Stop polling
        stopPolling();

        // Destroy charts
        destroyCharts();

        // Call onClose callback
        if (config.onClose) {
            config.onClose();
        }

        // Reset state
        state.runId = null;
        state.currentRun = null;
        state.currentTab = 'overview';
    }

    function startPolling() {
        if (state.pollInterval) return;

        state.pollInterval = setInterval(async () => {
            if (!state.runId) {
                stopPolling();
                return;
            }

            try {
                const url = buildUrl(config.endpoints.trainingRunDetails, { id: state.runId });
                const response = await fetch(url);
                const data = await response.json();

                if (data.success) {
                    const oldStatus = state.currentRun?.status;
                    state.currentRun = data.training_run;
                    updateModalContent();

                    // Stop polling if reached terminal state
                    if (state.currentRun.status !== 'running' && state.currentRun.status !== 'submitting') {
                        stopPolling();
                    }

                    // Notify of update
                    if (config.onUpdate && oldStatus !== state.currentRun.status) {
                        config.onUpdate(state.currentRun);
                    }
                }
            } catch (error) {
                console.error('Error polling training run:', error);
            }
        }, 10000); // Poll every 10 seconds
    }

    function stopPolling() {
        if (state.pollInterval) {
            clearInterval(state.pollInterval);
            state.pollInterval = null;
        }
    }

    function destroyCharts() {
        Object.keys(charts).forEach(key => {
            if (charts[key]) {
                charts[key].destroy();
                charts[key] = null;
            }
        });
    }

    // =============================================================================
    // MODAL CREATION
    // =============================================================================

    function ensureModalExists() {
        if (document.getElementById('trainingViewModal')) return;

        const modalHtml = `
            <div id="trainingViewModal" class="training-view-modal hidden">
                <div class="training-view-modal-overlay" onclick="TrainingViewModal.close()"></div>
                <div class="training-view-modal-container">
                    <div class="training-view-modal-header">
                        <div class="training-view-modal-title">
                            <span id="trainingViewTitle">Training Run</span>
                        </div>
                        <button class="training-view-modal-close" onclick="TrainingViewModal.close()">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    <div class="training-view-modal-tabs" id="trainingViewTabs">
                        <!-- Tabs will be rendered here -->
                    </div>
                    <div class="training-view-modal-body" id="trainingViewBody">
                        <!-- Content will be rendered here -->
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHtml);
    }

    // =============================================================================
    // RENDERING
    // =============================================================================

    function showLoadingState() {
        const body = document.getElementById('trainingViewBody');
        if (body) {
            body.innerHTML = `
                <div class="training-view-loading">
                    <i class="fas fa-spinner fa-spin"></i>
                    <span>Loading training run details...</span>
                </div>
            `;
        }
    }

    function showErrorState(message) {
        const body = document.getElementById('trainingViewBody');
        if (body) {
            body.innerHTML = `
                <div class="training-view-error">
                    <i class="fas fa-exclamation-circle"></i>
                    <span>${escapeHtml(message)}</span>
                </div>
            `;
        }
    }

    function renderModal() {
        const run = state.currentRun;
        if (!run) return;

        // Update title
        const titleEl = document.getElementById('trainingViewTitle');
        if (titleEl) {
            const statusCfg = STATUS_CONFIG[run.status] || STATUS_CONFIG.pending;
            titleEl.innerHTML = `
                <span class="training-view-status-badge" style="background-color: ${statusCfg.color}">
                    <i class="fas ${statusCfg.icon}${(run.status === 'running' || run.status === 'submitting') ? ' fa-spin' : ''}"></i>
                    ${statusCfg.label}
                </span>
                ${escapeHtml(run.name)}
                <span class="training-view-run-number">#${run.run_number}</span>
            `;
        }

        // Render tabs
        renderTabs();

        // Render content for current tab
        renderTabContent();
    }

    function updateModalContent() {
        const run = state.currentRun;
        if (!run) return;

        // Update title/status
        const titleEl = document.getElementById('trainingViewTitle');
        if (titleEl) {
            const statusCfg = STATUS_CONFIG[run.status] || STATUS_CONFIG.pending;
            titleEl.innerHTML = `
                <span class="training-view-status-badge" style="background-color: ${statusCfg.color}">
                    <i class="fas ${statusCfg.icon}${(run.status === 'running' || run.status === 'submitting') ? ' fa-spin' : ''}"></i>
                    ${statusCfg.label}
                </span>
                ${escapeHtml(run.name)}
                <span class="training-view-run-number">#${run.run_number}</span>
            `;
        }

        // Update current tab content
        renderTabContent();
    }

    function renderTabs() {
        const tabsContainer = document.getElementById('trainingViewTabs');
        if (!tabsContainer) return;

        const tabs = [
            { id: 'overview', label: 'Overview', icon: 'fa-info-circle' },
            { id: 'pipeline', label: 'Pipeline', icon: 'fa-project-diagram' },
            { id: 'training', label: 'Training', icon: 'fa-chart-line' },
            { id: 'artifacts', label: 'Artifacts', icon: 'fa-box' }
        ].filter(tab => config.showTabs.includes(tab.id));

        tabsContainer.innerHTML = tabs.map(tab => `
            <button class="training-view-tab ${state.currentTab === tab.id ? 'active' : ''}"
                    onclick="TrainingViewModal.switchTab('${tab.id}')">
                <i class="fas ${tab.icon}"></i>
                ${tab.label}
            </button>
        `).join('');
    }

    function switchTab(tabId) {
        state.currentTab = tabId;

        // Update tab buttons
        document.querySelectorAll('.training-view-tab').forEach(tab => {
            tab.classList.toggle('active', tab.textContent.trim().toLowerCase().includes(tabId));
        });

        renderTabContent();
    }

    function renderTabContent() {
        const body = document.getElementById('trainingViewBody');
        if (!body) return;

        switch (state.currentTab) {
            case 'overview':
                renderOverviewTab(body);
                break;
            case 'pipeline':
                renderPipelineTab(body);
                break;
            case 'training':
                renderTrainingTab(body);
                break;
            case 'artifacts':
                renderArtifactsTab(body);
                break;
            default:
                renderOverviewTab(body);
        }
    }

    // =============================================================================
    // OVERVIEW TAB
    // =============================================================================

    function renderOverviewTab(container) {
        const run = state.currentRun;
        if (!run) return;

        const modelTypeIcons = {
            retrieval: 'fa-search',
            ranking: 'fa-sort-amount-down',
            multitask: 'fa-layer-group'
        };

        container.innerHTML = `
            <div class="training-view-overview">
                <!-- Status & Progress Section -->
                <div class="training-view-section">
                    <h3 class="training-view-section-title">
                        <i class="fas fa-info-circle"></i> Status
                    </h3>
                    <div class="training-view-status-info">
                        ${renderStatusProgress(run)}
                    </div>
                </div>

                <!-- Configuration Section -->
                <div class="training-view-section">
                    <h3 class="training-view-section-title">
                        <i class="fas fa-cog"></i> Configuration
                    </h3>
                    <div class="training-view-grid">
                        <div class="training-view-grid-item">
                            <span class="label">Model Type</span>
                            <span class="value">
                                <i class="fas ${modelTypeIcons[run.model_type] || 'fa-cube'}"></i>
                                ${run.model_type}
                            </span>
                        </div>
                        <div class="training-view-grid-item">
                            <span class="label">Dataset</span>
                            <span class="value">${escapeHtml(run.dataset_name || '-')}</span>
                        </div>
                        <div class="training-view-grid-item">
                            <span class="label">Feature Config</span>
                            <span class="value">${escapeHtml(run.feature_config_name || '-')}</span>
                        </div>
                        <div class="training-view-grid-item">
                            <span class="label">Model Config</span>
                            <span class="value">${escapeHtml(run.model_config_name || '-')}</span>
                        </div>
                    </div>
                </div>

                <!-- Training Parameters Section -->
                ${renderTrainingParams(run)}

                <!-- Metrics Section -->
                ${renderMetricsSection(run)}

                <!-- Timeline Section -->
                <div class="training-view-section">
                    <h3 class="training-view-section-title">
                        <i class="fas fa-clock"></i> Timeline
                    </h3>
                    <div class="training-view-grid">
                        <div class="training-view-grid-item">
                            <span class="label">Created</span>
                            <span class="value">${formatDateTime(run.created_at)}</span>
                        </div>
                        <div class="training-view-grid-item">
                            <span class="label">Started</span>
                            <span class="value">${formatDateTime(run.started_at)}</span>
                        </div>
                        <div class="training-view-grid-item">
                            <span class="label">Completed</span>
                            <span class="value">${formatDateTime(run.completed_at)}</span>
                        </div>
                        <div class="training-view-grid-item">
                            <span class="label">Duration</span>
                            <span class="value">${formatDuration(run.duration_seconds || run.elapsed_seconds)}</span>
                        </div>
                        ${run.created_by ? `
                        <div class="training-view-grid-item">
                            <span class="label">Created By</span>
                            <span class="value">${escapeHtml(run.created_by)}</span>
                        </div>
                        ` : ''}
                    </div>
                </div>

                <!-- Error Section (if failed) -->
                ${renderErrorSection(run)}
            </div>
        `;
    }

    function renderStatusProgress(run) {
        if (run.status !== 'running' && run.status !== 'submitting') {
            return `
                <div class="training-view-status-summary">
                    <div class="status-item">
                        <span class="label">Current Stage</span>
                        <span class="value">${escapeHtml(run.current_stage || '-')}</span>
                    </div>
                    <div class="status-item">
                        <span class="label">Progress</span>
                        <span class="value">${run.progress_percent || 0}%</span>
                    </div>
                </div>
            `;
        }

        const progress = run.progress_percent || 0;
        const stage = run.current_stage || 'Initializing';

        return `
            <div class="training-view-progress-section">
                <div class="training-view-progress-info">
                    <span class="stage"><i class="fas fa-cog fa-spin"></i> ${escapeHtml(stage)}</span>
                    <span class="percent">${progress}%</span>
                </div>
                <div class="training-view-progress-bar">
                    <div class="training-view-progress-fill ${progress === 0 ? 'indeterminate' : ''}" style="width: ${progress}%"></div>
                </div>
                ${run.current_epoch && run.total_epochs ? `
                <div class="training-view-epoch-info">
                    Epoch ${run.current_epoch} of ${run.total_epochs}
                </div>
                ` : ''}
            </div>
        `;
    }

    function renderTrainingParams(run) {
        const params = run.training_params || {};
        const gpuConfig = run.gpu_config || {};
        const evaluatorConfig = run.evaluator_config || {};

        return `
            <div class="training-view-section">
                <h3 class="training-view-section-title">
                    <i class="fas fa-sliders-h"></i> Training Parameters
                </h3>
                <div class="training-view-grid training-view-grid-4">
                    <div class="training-view-grid-item">
                        <span class="label">Epochs</span>
                        <span class="value">${params.epochs || '-'}</span>
                    </div>
                    <div class="training-view-grid-item">
                        <span class="label">Batch Size</span>
                        <span class="value">${formatNumber(params.batch_size)}</span>
                    </div>
                    <div class="training-view-grid-item">
                        <span class="label">Learning Rate</span>
                        <span class="value">${params.learning_rate || '-'}</span>
                    </div>
                    <div class="training-view-grid-item">
                        <span class="label">Split Strategy</span>
                        <span class="value">${params.split_strategy || '-'}</span>
                    </div>
                    <div class="training-view-grid-item">
                        <span class="label">GPU Type</span>
                        <span class="value">${gpuConfig.accelerator_type ? gpuConfig.accelerator_type.replace('NVIDIA_', '') : '-'}</span>
                    </div>
                    <div class="training-view-grid-item">
                        <span class="label">GPU Count</span>
                        <span class="value">${gpuConfig.accelerator_count || '-'}</span>
                    </div>
                    <div class="training-view-grid-item">
                        <span class="label">Preemptible</span>
                        <span class="value">${gpuConfig.use_preemptible ? 'Yes' : 'No'}</span>
                    </div>
                    <div class="training-view-grid-item">
                        <span class="label">Evaluator</span>
                        <span class="value">${evaluatorConfig.enabled ? 'Enabled' : 'Disabled'}</span>
                    </div>
                </div>
            </div>
        `;
    }

    function renderMetricsSection(run) {
        // Only show metrics for completed or not_blessed runs
        if (run.status !== 'completed' && run.status !== 'not_blessed') {
            return '';
        }

        let metricsHtml = '';

        if (run.model_type === 'multitask') {
            metricsHtml = `
                <div class="training-view-metrics-group">
                    <h4><i class="fas fa-search"></i> Retrieval Metrics</h4>
                    <div class="training-view-metrics-row">
                        <div class="training-view-metric">
                            <span class="label">R@5</span>
                            <span class="value">${formatNumber(run.recall_at_5)}</span>
                        </div>
                        <div class="training-view-metric">
                            <span class="label">R@10</span>
                            <span class="value">${formatNumber(run.recall_at_10)}</span>
                        </div>
                        <div class="training-view-metric">
                            <span class="label">R@50</span>
                            <span class="value">${formatNumber(run.recall_at_50)}</span>
                        </div>
                        <div class="training-view-metric">
                            <span class="label">R@100</span>
                            <span class="value">${formatNumber(run.recall_at_100)}</span>
                        </div>
                    </div>
                </div>
                <div class="training-view-metrics-group">
                    <h4><i class="fas fa-sort-amount-down"></i> Ranking Metrics</h4>
                    <div class="training-view-metrics-row">
                        <div class="training-view-metric">
                            <span class="label">RMSE</span>
                            <span class="value">${formatNumber(run.rmse, 4)}</span>
                        </div>
                        <div class="training-view-metric">
                            <span class="label">Test RMSE</span>
                            <span class="value">${formatNumber(run.test_rmse, 4)}</span>
                        </div>
                        <div class="training-view-metric">
                            <span class="label">MAE</span>
                            <span class="value">${formatNumber(run.mae, 4)}</span>
                        </div>
                        <div class="training-view-metric">
                            <span class="label">Test MAE</span>
                            <span class="value">${formatNumber(run.test_mae, 4)}</span>
                        </div>
                    </div>
                </div>
            `;
        } else if (run.model_type === 'ranking') {
            metricsHtml = `
                <div class="training-view-metrics-row">
                    <div class="training-view-metric">
                        <span class="label">RMSE</span>
                        <span class="value">${formatNumber(run.rmse, 4)}</span>
                    </div>
                    <div class="training-view-metric">
                        <span class="label">Test RMSE</span>
                        <span class="value">${formatNumber(run.test_rmse, 4)}</span>
                    </div>
                    <div class="training-view-metric">
                        <span class="label">MAE</span>
                        <span class="value">${formatNumber(run.mae, 4)}</span>
                    </div>
                    <div class="training-view-metric">
                        <span class="label">Test MAE</span>
                        <span class="value">${formatNumber(run.test_mae, 4)}</span>
                    </div>
                    <div class="training-view-metric">
                        <span class="label">Loss</span>
                        <span class="value">${formatNumber(run.loss, 4)}</span>
                    </div>
                </div>
            `;
        } else {
            // Retrieval
            metricsHtml = `
                <div class="training-view-metrics-row">
                    <div class="training-view-metric">
                        <span class="label">R@5</span>
                        <span class="value">${formatNumber(run.recall_at_5)}</span>
                    </div>
                    <div class="training-view-metric">
                        <span class="label">R@10</span>
                        <span class="value">${formatNumber(run.recall_at_10)}</span>
                    </div>
                    <div class="training-view-metric">
                        <span class="label">R@50</span>
                        <span class="value">${formatNumber(run.recall_at_50)}</span>
                    </div>
                    <div class="training-view-metric">
                        <span class="label">R@100</span>
                        <span class="value">${formatNumber(run.recall_at_100)}</span>
                    </div>
                    <div class="training-view-metric">
                        <span class="label">Loss</span>
                        <span class="value">${formatNumber(run.loss, 4)}</span>
                    </div>
                </div>
            `;
        }

        // Add blessing info
        let blessingHtml = '';
        if (run.is_blessed !== null) {
            blessingHtml = `
                <div class="training-view-blessing ${run.is_blessed ? 'blessed' : 'not-blessed'}">
                    <i class="fas ${run.is_blessed ? 'fa-check-circle' : 'fa-exclamation-triangle'}"></i>
                    ${run.is_blessed ? 'Model passed evaluation (blessed)' : 'Model did not pass evaluation threshold'}
                </div>
            `;
        }

        return `
            <div class="training-view-section">
                <h3 class="training-view-section-title">
                    <i class="fas fa-chart-bar"></i> Final Metrics
                </h3>
                ${metricsHtml}
                ${blessingHtml}
            </div>
        `;
    }

    function renderErrorSection(run) {
        if (run.status !== 'failed' || !run.error_message) {
            return '';
        }

        return `
            <div class="training-view-section training-view-error-section">
                <h3 class="training-view-section-title">
                    <i class="fas fa-exclamation-circle"></i> Error Details
                </h3>
                <div class="training-view-error-box">
                    ${run.error_stage ? `<div class="error-stage">Failed at stage: <strong>${escapeHtml(run.error_stage)}</strong></div>` : ''}
                    <div class="error-message">${escapeHtml(run.error_message)}</div>
                    ${run.error_details && Object.keys(run.error_details).length > 0 ? `
                    <details class="error-details">
                        <summary>Technical Details</summary>
                        <pre>${JSON.stringify(run.error_details, null, 2)}</pre>
                    </details>
                    ` : ''}
                </div>
            </div>
        `;
    }

    // =============================================================================
    // PIPELINE TAB
    // =============================================================================

    function renderPipelineTab(container) {
        const run = state.currentRun;
        if (!run) return;

        const stageDetails = run.stage_details || [];

        // Create stage status map
        const stageStatusMap = {};
        stageDetails.forEach(stage => {
            stageStatusMap[stage.name?.toLowerCase()] = stage.status;
        });

        container.innerHTML = `
            <div class="training-view-pipeline">
                <div class="training-view-section">
                    <h3 class="training-view-section-title">
                        <i class="fas fa-project-diagram"></i> Pipeline Stages
                    </h3>
                    <div class="training-view-pipeline-dag">
                        ${PIPELINE_STAGES.map((stage, index) => {
                            const status = stageStatusMap[stage.id] || 'pending';
                            const statusClass = status === 'completed' ? 'completed' :
                                               status === 'running' ? 'running' :
                                               status === 'failed' ? 'failed' : 'pending';

                            return `
                                <div class="training-view-pipeline-stage ${statusClass}">
                                    <div class="stage-icon">
                                        <i class="fas ${stage.icon}${status === 'running' ? ' fa-spin' : ''}"></i>
                                    </div>
                                    <div class="stage-name">${stage.name}</div>
                                    <div class="stage-status">${status}</div>
                                </div>
                                ${index < PIPELINE_STAGES.length - 1 ? '<div class="stage-connector"></div>' : ''}
                            `;
                        }).join('')}
                    </div>
                </div>

                ${run.vertex_pipeline_job_name ? `
                <div class="training-view-section">
                    <h3 class="training-view-section-title">
                        <i class="fas fa-cloud"></i> Vertex AI Pipeline
                    </h3>
                    <div class="training-view-pipeline-info">
                        <div class="info-item">
                            <span class="label">Pipeline Job Name</span>
                            <span class="value mono">${escapeHtml(run.vertex_pipeline_job_name)}</span>
                        </div>
                        <a href="https://console.cloud.google.com/vertex-ai/pipelines" target="_blank" class="training-view-link">
                            <i class="fas fa-external-link-alt"></i> View in Vertex AI Console
                        </a>
                    </div>
                </div>
                ` : ''}
            </div>
        `;
    }

    // =============================================================================
    // TRAINING TAB
    // =============================================================================

    function renderTrainingTab(container) {
        const run = state.currentRun;
        if (!run) return;

        const history = run.training_history_json || {};

        // Check if we have training history data
        if (!history.loss || history.loss.length === 0) {
            container.innerHTML = `
                <div class="training-view-empty-state">
                    <i class="fas fa-chart-line"></i>
                    <p>Training history will be available once training starts</p>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="training-view-training">
                <div class="training-view-section">
                    <h3 class="training-view-section-title">
                        <i class="fas fa-chart-line"></i> Training Loss
                    </h3>
                    <div class="training-view-chart-container">
                        <canvas id="trainingLossChart"></canvas>
                    </div>
                </div>

                <div class="training-view-section">
                    <h3 class="training-view-section-title">
                        <i class="fas fa-chart-bar"></i> Metrics Over Epochs
                    </h3>
                    <div class="training-view-chart-container">
                        <canvas id="trainingMetricsChart"></canvas>
                    </div>
                </div>
            </div>
        `;

        // Render charts after DOM is updated
        setTimeout(() => {
            renderLossChart(history);
            renderMetricsChart(history, run.model_type);
        }, 0);
    }

    function renderLossChart(history) {
        const ctx = document.getElementById('trainingLossChart');
        if (!ctx) return;

        // Destroy existing chart
        if (charts.lossChart) {
            charts.lossChart.destroy();
        }

        const epochs = history.loss.map((_, i) => i + 1);

        charts.lossChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: epochs,
                datasets: [{
                    label: 'Training Loss',
                    data: history.loss,
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: { boxWidth: 12, padding: 10 }
                    }
                },
                scales: {
                    x: {
                        title: { display: true, text: 'Epoch' },
                        ticks: { maxTicksLimit: 10 }
                    },
                    y: {
                        title: { display: true, text: 'Loss' },
                        beginAtZero: false
                    }
                }
            }
        });
    }

    function renderMetricsChart(history, modelType) {
        const ctx = document.getElementById('trainingMetricsChart');
        if (!ctx) return;

        // Destroy existing chart
        if (charts.metricsChart) {
            charts.metricsChart.destroy();
        }

        const datasets = [];
        const colors = ['#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];
        let colorIndex = 0;

        // Add metrics based on model type
        if (modelType === 'retrieval' || modelType === 'multitask') {
            if (history.recall_at_10) {
                datasets.push({
                    label: 'Recall@10',
                    data: history.recall_at_10,
                    borderColor: colors[colorIndex++],
                    tension: 0.3,
                    pointRadius: 2
                });
            }
            if (history.recall_at_100) {
                datasets.push({
                    label: 'Recall@100',
                    data: history.recall_at_100,
                    borderColor: colors[colorIndex++],
                    tension: 0.3,
                    pointRadius: 2
                });
            }
        }

        if (modelType === 'ranking' || modelType === 'multitask') {
            if (history.rmse) {
                datasets.push({
                    label: 'RMSE',
                    data: history.rmse,
                    borderColor: colors[colorIndex++],
                    tension: 0.3,
                    pointRadius: 2
                });
            }
            if (history.mae) {
                datasets.push({
                    label: 'MAE',
                    data: history.mae,
                    borderColor: colors[colorIndex++],
                    tension: 0.3,
                    pointRadius: 2
                });
            }
        }

        if (datasets.length === 0) {
            // No metrics to display
            return;
        }

        const epochs = datasets[0].data.map((_, i) => i + 1);

        charts.metricsChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: epochs,
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: { boxWidth: 12, padding: 10 }
                    }
                },
                scales: {
                    x: {
                        title: { display: true, text: 'Epoch' },
                        ticks: { maxTicksLimit: 10 }
                    },
                    y: {
                        title: { display: true, text: 'Value' },
                        beginAtZero: false
                    }
                }
            }
        });
    }

    // =============================================================================
    // ARTIFACTS TAB
    // =============================================================================

    function renderArtifactsTab(container) {
        const run = state.currentRun;
        if (!run) return;

        const artifacts = run.artifacts || {};

        container.innerHTML = `
            <div class="training-view-artifacts">
                <!-- GCS Artifacts -->
                <div class="training-view-section">
                    <h3 class="training-view-section-title">
                        <i class="fas fa-cloud"></i> GCS Artifacts
                    </h3>
                    ${run.gcs_artifacts_path ? `
                    <div class="training-view-artifact-item">
                        <span class="label">Artifacts Path</span>
                        <span class="value mono">${escapeHtml(run.gcs_artifacts_path)}</span>
                        <a href="https://console.cloud.google.com/storage/browser/${run.gcs_artifacts_path.replace('gs://', '')}" target="_blank" class="artifact-link">
                            <i class="fas fa-external-link-alt"></i>
                        </a>
                    </div>
                    ` : '<p class="empty-text">No GCS artifacts path available</p>'}

                    ${Object.keys(artifacts).length > 0 ? `
                    <div class="training-view-artifact-list">
                        ${Object.entries(artifacts).map(([key, path]) => `
                        <div class="training-view-artifact-item">
                            <span class="label">${escapeHtml(key)}</span>
                            <span class="value mono">${escapeHtml(path)}</span>
                        </div>
                        `).join('')}
                    </div>
                    ` : ''}
                </div>

                <!-- Model Registry -->
                <div class="training-view-section">
                    <h3 class="training-view-section-title">
                        <i class="fas fa-box"></i> Vertex AI Model Registry
                    </h3>
                    ${run.vertex_model_resource_name ? `
                    <div class="training-view-grid">
                        <div class="training-view-grid-item">
                            <span class="label">Model Name</span>
                            <span class="value">${escapeHtml(run.vertex_model_name || '-')}</span>
                        </div>
                        <div class="training-view-grid-item">
                            <span class="label">Version</span>
                            <span class="value">${escapeHtml(run.vertex_model_version || '-')}</span>
                        </div>
                        <div class="training-view-grid-item full-width">
                            <span class="label">Resource Name</span>
                            <span class="value mono">${escapeHtml(run.vertex_model_resource_name)}</span>
                        </div>
                    </div>
                    <a href="https://console.cloud.google.com/vertex-ai/models" target="_blank" class="training-view-link">
                        <i class="fas fa-external-link-alt"></i> View in Model Registry
                    </a>
                    ` : '<p class="empty-text">Model not yet registered</p>'}
                </div>

                <!-- Deployment -->
                <div class="training-view-section">
                    <h3 class="training-view-section-title">
                        <i class="fas fa-rocket"></i> Deployment
                    </h3>
                    ${run.is_deployed ? `
                    <div class="training-view-grid">
                        <div class="training-view-grid-item">
                            <span class="label">Status</span>
                            <span class="value">
                                <span class="deployed-badge"><i class="fas fa-check-circle"></i> Deployed</span>
                            </span>
                        </div>
                        <div class="training-view-grid-item">
                            <span class="label">Deployed At</span>
                            <span class="value">${formatDateTime(run.deployed_at)}</span>
                        </div>
                        ${run.endpoint_resource_name ? `
                        <div class="training-view-grid-item full-width">
                            <span class="label">Endpoint</span>
                            <span class="value mono">${escapeHtml(run.endpoint_resource_name)}</span>
                        </div>
                        ` : ''}
                    </div>
                    ` : '<p class="empty-text">Model not deployed</p>'}
                </div>
            </div>
        `;
    }

    // =============================================================================
    // PUBLIC API
    // =============================================================================

    return {
        configure: configure,
        open: open,
        close: close,
        switchTab: switchTab,
        refresh: function() {
            if (state.runId) {
                open(state.runId);
            }
        }
    };
})();
