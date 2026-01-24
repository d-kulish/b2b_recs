/**
 * Experiment View Modal Module
 *
 * A reusable modal component for displaying experiment details,
 * styled like Vertex AI Pipelines console.
 *
 * Usage:
 *     // Include the HTML template in your page
 *     {% include 'includes/_exp_view_modal.html' %}
 *
 *     // Open modal for an experiment
 *     ExpViewModal.open(experimentId);
 *     // or with full experiment data
 *     ExpViewModal.openWithData(experimentData);
 *
 *     // Close modal
 *     ExpViewModal.close();
 *
 * Configuration (set via ExpViewModal.configure()):
 *     {
 *         endpoints: {
 *             experimentDetails: '/api/quick-tests/{id}/',
 *             datasetSummary: '/api/datasets/{id}/summary/',
 *             featureConfig: '/api/feature-configs/{id}/',
 *             modelConfig: '/api/model-configs/{id}/',
 *             statistics: '/api/quick-tests/{id}/statistics/',
 *             schema: '/api/quick-tests/{id}/schema/',
 *             trainingHistory: '/api/quick-tests/{id}/training-history/',
 *             errors: '/api/quick-tests/{id}/errors/',
 *             componentLogs: '/api/quick-tests/{id}/component-logs/{componentId}/'
 *         },
 *         showTabs: ['overview', 'pipeline', 'data', 'training'],
 *         onClose: function() { },
 *         onUpdate: function(exp) { }  // Called when experiment updates during polling
 *     }
 */

const ExpViewModal = (function() {
    'use strict';

    // =============================================================================
    // CONFIGURATION & STATE
    // =============================================================================

    let config = {
        mode: 'experiment',  // 'experiment' or 'training_run'
        endpoints: {
            experimentDetails: '/api/quick-tests/{id}/',
            trainingRunDetails: '/api/training-runs/{id}/',
            datasetSummary: '/api/datasets/{id}/summary/',
            featureConfig: '/api/feature-configs/{id}/',
            modelConfig: '/api/model-configs/{id}/',
            statistics: '/api/quick-tests/{id}/statistics/',
            schema: '/api/quick-tests/{id}/schema/',
            trainingHistory: '/api/quick-tests/{id}/training-history/',
            errors: '/api/quick-tests/{id}/errors/',
            componentLogs: '/api/quick-tests/{id}/component-logs/{componentId}/',
            tfdvReport: '/experiments/quick-tests/{id}/tfdv/',
            // Training run endpoints (used when mode === 'training_run')
            trainingRunStatistics: '/api/training-runs/{id}/statistics/',
            trainingRunSchema: '/api/training-runs/{id}/schema/',
            trainingRunTfdvReport: '/training/runs/{id}/tfdv/',
            trainingRunTrainingHistory: '/api/training-runs/{id}/training-history/',
            trainingRunHistogramData: '/api/training-runs/{id}/histogram-data/'
        },
        showTabs: ['overview', 'pipeline', 'data', 'training'],
        onClose: null,
        onUpdate: null
    };

    let state = {
        mode: 'experiment',  // 'experiment', 'training_run', or 'model'
        expId: null,
        currentExp: null,
        runId: null,
        currentRun: null,
        modelId: null,
        currentModel: null,
        currentTab: 'overview',
        pollInterval: null,
        dataCache: {
            statistics: null,
            schema: null,
            errorDetails: null,
            trainingHistory: null,
            versions: null,
            lineage: null,
            _loadingInsights: false,
            _statsData: null,
            _schemaData: null
        },
        // Accordion expanded states for Overview tab
        accordionExpanded: {
            registryDeployment: false,
            dataset: false,
            features: false,
            model: false,
            trainingSetup: false
        }
    };

    // Training chart instances
    let charts = {
        lossChart: null,
        metricsChart: null,
        gradientChart: null,
        weightStatsChart: null
    };

    // Weight data for tower switching
    let weightData = {
        norms: null,
        stats: null,
        histogram: null
    };

    // Chart.js defaults for consistent styling
    const chartDefaults = {
        layout: {
            padding: { top: 0, right: 0, bottom: 0, left: 0 }
        },
        font: {
            axis: { size: 9 },
            axisTitle: { size: 10 },
            legend: { size: 10 }
        },
        ticks: {
            padding: 2
        },
        scales: {
            y: {
                grace: '2%',
                title: { font: { size: 10 } },
                ticks: { font: { size: 9 }, padding: 2 }
            },
            x: {
                ticks: { font: { size: 9 }, padding: 2, maxRotation: 0 }
            }
        },
        legend: {
            labels: {
                boxWidth: 8,
                boxHeight: 8,
                padding: 6,
                font: { size: 10 },
                usePointStyle: true
            }
        }
    };

    // Training run status configuration (for training_run mode)
    const TRAINING_STATUS_CONFIG = {
        pending: { icon: 'fa-clock', color: '#9ca3af', label: 'Pending' },
        scheduled: { icon: 'fa-clock', color: '#f59e0b', label: 'Scheduled' },
        submitting: { icon: 'fa-sync', color: '#3b82f6', label: 'Submitting' },
        running: { icon: 'fa-sync', color: '#3b82f6', label: 'Running' },
        completed: { icon: 'fa-check', color: '#10b981', label: 'Completed' },
        failed: { icon: 'fa-exclamation', color: '#ef4444', label: 'Failed' },
        cancelled: { icon: 'fa-ban', color: '#6b7280', label: 'Cancelled' },
        not_blessed: { icon: 'fa-exclamation', color: '#f97316', label: 'Not Blessed' }
    };

    // Pipeline stages for training runs (8 stages)
    // NOTE: 'name' must match TFX_PIPELINE.components 'id' in pipeline_dag.js for status mapping
    const TRAINING_PIPELINE_STAGES = [
        { id: 'compile', name: 'Compile', icon: 'fa-cog' },
        { id: 'examples', name: 'Examples', icon: 'fa-database' },
        { id: 'stats', name: 'Stats', icon: 'fa-chart-bar' },
        { id: 'schema', name: 'Schema', icon: 'fa-sitemap' },
        { id: 'transform', name: 'Transform', icon: 'fa-exchange-alt' },
        { id: 'train', name: 'Train', icon: 'fa-graduation-cap' },
        { id: 'evaluator', name: 'Evaluator', icon: 'fa-check-double' },
        { id: 'pusher', name: 'Pusher', icon: 'fa-upload' }
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

    function formatDateTime(isoStr) {
        if (!isoStr) return '-';
        const d = new Date(isoStr);
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' +
               d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    }

    function formatNumber(val) {
        if (val === null || val === undefined) return '-';
        if (Math.abs(val) >= 1000000) return (val / 1000000).toFixed(2) + 'M';
        if (Math.abs(val) >= 1000) return (val / 1000).toFixed(2) + 'K';
        if (Number.isInteger(val)) return val.toLocaleString();
        return val.toFixed(2);
    }

    function formatPercent(val) {
        if (val === null || val === undefined) return '0%';
        return val.toFixed(1) + '%';
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

    async function open(id, options = {}) {
        // Set mode from options (defaults to 'experiment')
        state.mode = options.mode || 'experiment';

        try {
            let url, dataKey;

            if (state.mode === 'training_run') {
                url = buildUrl(config.endpoints.trainingRunDetails, { id: id });
                dataKey = 'training_run';
            } else {
                url = buildUrl(config.endpoints.experimentDetails, { id: id });
                dataKey = 'quick_test';
            }

            const response = await fetch(url);
            const data = await response.json();

            if (!data.success) {
                console.error(`Failed to load ${state.mode}:`, data.error);
                return;
            }

            if (state.mode === 'training_run') {
                openWithTrainingRunData(data[dataKey]);
            } else {
                openWithData(data[dataKey]);
            }
        } catch (error) {
            console.error(`Error loading ${state.mode} details:`, error);
        }
    }

    function openWithData(exp) {
        state.expId = exp.id;
        state.currentExp = exp;

        // Reset state
        state.dataCache = {
            statistics: null,
            schema: null,
            errorDetails: null,
            trainingHistory: null,
            _loadingInsights: false,
            _statsData: null,
            _schemaData: null
        };
        state.currentTab = 'overview';

        // Reset tabs to default
        document.querySelectorAll('.exp-view-tab').forEach(t => t.classList.remove('active'));
        const overviewTab = document.querySelector('.exp-view-tab[data-tab="overview"]');
        if (overviewTab) overviewTab.classList.add('active');

        document.querySelectorAll('.exp-view-tab-content').forEach(c => c.classList.remove('active'));
        const overviewContent = document.getElementById('expViewTabOverview');
        if (overviewContent) overviewContent.classList.add('active');

        // Update visible tabs based on config
        updateVisibleTabs();

        // Populate modal
        populateModal(exp);
        document.getElementById('expViewModal').classList.remove('hidden');

        // Preload Data Insights in background
        preloadDataInsights();

        // Preload training history for completed experiments
        if (exp.status === 'completed') {
            preloadTrainingHistory();
        }

        // Start polling if experiment is running
        if (exp.status === 'running' || exp.status === 'submitting') {
            startPolling(exp.id);
        }
    }

    // =============================================================================
    // TRAINING RUN MODE FUNCTIONS
    // =============================================================================

    function openWithTrainingRunData(run) {
        state.mode = 'training_run';
        state.runId = run.id;
        state.currentRun = run;

        // Reset state
        state.dataCache = {
            statistics: null,
            schema: null,
            errorDetails: null,
            trainingHistory: null,
            _loadingInsights: false,
            _statsData: null,
            _schemaData: null
        };
        state.currentTab = 'overview';

        // Reset tabs to default
        document.querySelectorAll('.exp-view-tab').forEach(t => t.classList.remove('active'));
        const overviewTab = document.querySelector('.exp-view-tab[data-tab="overview"]');
        if (overviewTab) overviewTab.classList.add('active');

        document.querySelectorAll('.exp-view-tab-content').forEach(c => c.classList.remove('active'));
        const overviewContent = document.getElementById('expViewTabOverview');
        if (overviewContent) overviewContent.classList.add('active');

        // Update visible tabs for training run mode
        updateVisibleTabs();

        // Populate modal with training run data
        populateTrainingRunModal(run);
        document.getElementById('expViewModal').classList.remove('hidden');

        // Preload Data Insights in background
        preloadDataInsights();

        // Start polling if running/submitting
        if (run.status === 'running' || run.status === 'submitting') {
            startTrainingRunPolling(run.id);
        }
    }

    function populateTrainingRunModal(run) {
        // Store current run for tab data loading
        window.currentViewRun = run;

        // Status gradient on header
        const header = document.getElementById('expViewHeader');
        header.className = `modal-header exp-view-header ${run.status}`;

        // Status panel
        const statusPanel = document.getElementById('expViewStatusPanel');
        statusPanel.className = `exp-view-status-panel ${run.status}`;

        // Status icon
        const statusIcon = document.getElementById('expViewStatusIcon');
        const statusCfg = TRAINING_STATUS_CONFIG[run.status] || TRAINING_STATUS_CONFIG.pending;
        const isSpinning = run.status === 'running' || run.status === 'submitting';
        statusIcon.className = `exp-view-status-icon ${run.status}`;
        statusIcon.innerHTML = `<i class="fas ${statusCfg.icon}${isSpinning ? ' fa-spin' : ''}"></i>`;

        // Title (Run #N)
        document.getElementById('expViewTitle').textContent = `Run #${run.run_number}`;

        // Run name
        const expNameEl = document.getElementById('expViewExpName');
        expNameEl.textContent = run.name || '';
        expNameEl.style.display = run.name ? '' : 'none';

        // Model type badge in header
        const typeBadgeEl = document.getElementById('expViewTypeBadge');
        const modelType = (run.model_type || 'retrieval').toLowerCase();
        const badgeContents = {
            'retrieval': '<i class="fas fa-search"></i> Retrieval',
            'ranking': '<i class="fas fa-sort-amount-down"></i> Ranking',
            'multitask': '<i class="fas fa-layer-group"></i> Retrieval / Ranking'
        };
        typeBadgeEl.className = `exp-view-header-type-badge ${modelType}`;
        typeBadgeEl.innerHTML = badgeContents[modelType] || badgeContents['retrieval'];

        // Description (empty for training runs or use run notes if available)
        const descEl = document.getElementById('expViewDescription');
        descEl.textContent = run.notes || '';
        descEl.style.display = run.notes ? '' : 'none';

        // Start/End times
        document.getElementById('expViewStartTime').textContent = formatDateTime(run.started_at || run.created_at);
        document.getElementById('expViewEndTime').textContent = run.completed_at ? formatDateTime(run.completed_at) : '-';

        // Overview Tab - render training run specific content
        renderTrainingRunOverview(run);

        // Pipeline Tab - render 8-stage pipeline
        renderTrainingRunPipeline(run);
    }

    function renderTrainingRunOverview(run) {
        // Reset accordion states when populating new data
        resetAccordionStates();

        // Dataset section
        const datasetName = run.dataset_name || '-';
        document.getElementById('expViewDatasetName').textContent = datasetName;

        // Dataset details - load full details using existing function
        if (run.dataset_id) {
            loadDatasetDetails(run.dataset_id);
        } else {
            document.getElementById('expViewDatasetDetails').innerHTML =
                '<div class="exp-view-no-filters">No dataset configured</div>';
        }

        // Features config - load full details
        const featureConfigName = run.feature_config_name || '-';
        document.getElementById('expViewFeaturesConfigName').textContent = featureConfigName;
        if (run.feature_config_id) {
            loadFeaturesConfig(run.feature_config_id);
        } else {
            document.getElementById('expViewFeaturesConfigContent').innerHTML =
                '<div class="exp-view-no-filters">No features config</div>';
        }

        // Model config - load full details
        const modelConfigName = run.model_config_name || '-';
        document.getElementById('expViewModelConfigName').textContent = modelConfigName;

        // Model type badge in accordion header
        const modelType = (run.model_type || 'retrieval').toLowerCase();
        const badgeSmall = document.getElementById('expViewModelTypeBadgeSmall');
        if (badgeSmall) {
            const badgeLabels = {
                'retrieval': 'Retrieval',
                'ranking': 'Ranking',
                'multitask': 'Multitask'
            };
            badgeSmall.textContent = badgeLabels[modelType] || 'Retrieval';
            badgeSmall.className = 'exp-view-accordion-badge badge-' + modelType;
        }

        if (run.model_config_id) {
            loadModelConfig(run.model_config_id);
        } else {
            document.getElementById('expViewModelConfigContent').innerHTML =
                '<div class="exp-view-no-filters">No model config</div>';
        }

        // Sampling chips
        renderTrainingRunSamplingChips(run);

        // Training parameters chips
        renderTrainingRunParamsChips(run);

        // Results Summary (metrics)
        renderTrainingRunMetrics(run);

        // Registry and Deployment sections (for training_run mode)
        renderRegistrySection(run);
        renderDeploymentSection(run);
    }

    function renderTrainingRunMetrics(run) {
        const resultsSummary = document.getElementById('expViewResultsSummary');
        const metricsContainer = document.getElementById('expViewMetricsSummary');

        // Only show for completed or not_blessed runs
        if (run.status !== 'completed' && run.status !== 'not_blessed') {
            resultsSummary.classList.add('hidden');
            return;
        }

        resultsSummary.classList.remove('hidden');

        let metricsHtml = '';
        const formatRecall = v => v != null ? (v * 100).toFixed(0) + '%' : 'N/A';

        // Metrics based on model type
        if (run.model_type === 'multitask') {
            // Retrieval metrics
            metricsHtml += `
                <div class="exp-view-metric-card">
                    <div class="exp-view-metric-card-label">R@5</div>
                    <div class="exp-view-metric-card-value">${formatRecall(run.recall_at_5)}</div>
                </div>
                <div class="exp-view-metric-card">
                    <div class="exp-view-metric-card-label">R@10</div>
                    <div class="exp-view-metric-card-value">${formatRecall(run.recall_at_10)}</div>
                </div>
                <div class="exp-view-metric-card">
                    <div class="exp-view-metric-card-label">RMSE</div>
                    <div class="exp-view-metric-card-value">${formatNumber(run.rmse)}</div>
                </div>
                <div class="exp-view-metric-card">
                    <div class="exp-view-metric-card-label">Loss</div>
                    <div class="exp-view-metric-card-value">${formatNumber(run.loss)}</div>
                </div>
            `;
        } else if (run.model_type === 'ranking') {
            metricsHtml += `
                <div class="exp-view-metric-card">
                    <div class="exp-view-metric-card-label">RMSE</div>
                    <div class="exp-view-metric-card-value">${formatNumber(run.rmse)}</div>
                </div>
                <div class="exp-view-metric-card">
                    <div class="exp-view-metric-card-label">Test RMSE</div>
                    <div class="exp-view-metric-card-value">${formatNumber(run.test_rmse)}</div>
                </div>
                <div class="exp-view-metric-card">
                    <div class="exp-view-metric-card-label">MAE</div>
                    <div class="exp-view-metric-card-value">${formatNumber(run.mae)}</div>
                </div>
                <div class="exp-view-metric-card">
                    <div class="exp-view-metric-card-label">Loss</div>
                    <div class="exp-view-metric-card-value">${formatNumber(run.loss)}</div>
                </div>
            `;
        } else {
            // Retrieval
            metricsHtml += `
                <div class="exp-view-metric-card">
                    <div class="exp-view-metric-card-label">R@5</div>
                    <div class="exp-view-metric-card-value">${formatRecall(run.recall_at_5)}</div>
                </div>
                <div class="exp-view-metric-card">
                    <div class="exp-view-metric-card-label">R@10</div>
                    <div class="exp-view-metric-card-value">${formatRecall(run.recall_at_10)}</div>
                </div>
                <div class="exp-view-metric-card">
                    <div class="exp-view-metric-card-label">R@50</div>
                    <div class="exp-view-metric-card-value">${formatRecall(run.recall_at_50)}</div>
                </div>
                <div class="exp-view-metric-card">
                    <div class="exp-view-metric-card-label">R@100</div>
                    <div class="exp-view-metric-card-value">${formatRecall(run.recall_at_100)}</div>
                </div>
            `;
        }

        metricsContainer.innerHTML = metricsHtml;
    }

    function renderTrainingRunSamplingChips(run) {
        const container = document.getElementById('expViewSamplingChips');
        if (!container) return;

        const params = run.training_params || {};
        const chips = [];

        if (params.split_strategy) {
            chips.push({ label: 'Split Strategy', value: params.split_strategy });
        }
        if (params.train_fraction) {
            chips.push({ label: 'Train', value: `${(params.train_fraction * 100).toFixed(0)}%` });
        }
        if (params.val_fraction) {
            chips.push({ label: 'Val', value: `${(params.val_fraction * 100).toFixed(0)}%` });
        }
        if (params.test_fraction) {
            chips.push({ label: 'Test', value: `${(params.test_fraction * 100).toFixed(0)}%` });
        }

        if (chips.length === 0) {
            container.innerHTML = '<span class="exp-view-no-filters">No sampling parameters</span>';
            return;
        }

        container.innerHTML = chips.map(chip => `
            <div class="exp-view-param-chip">
                <span class="exp-view-param-chip-label">${chip.label}:</span>
                <span class="exp-view-param-chip-value">${chip.value}</span>
            </div>
        `).join('');
    }

    function renderTrainingRunParamsChips(run) {
        const container = document.getElementById('expViewTrainingParamsChips');
        if (!container) return;

        const params = run.training_params || {};
        const gpuConfig = run.gpu_config || {};
        const chips = [];

        if (params.epochs) chips.push({ label: 'Epochs', value: params.epochs });
        if (params.batch_size) chips.push({ label: 'Batch Size', value: formatNumber(params.batch_size) });
        if (params.learning_rate) chips.push({ label: 'Learning Rate', value: params.learning_rate });

        // GPU config (keys are gpu_type, gpu_count, preemptible - not accelerator_*)
        if (gpuConfig.gpu_type) {
            chips.push({ label: 'GPU', value: gpuConfig.gpu_type.replace('NVIDIA_TESLA_', '').replace('NVIDIA_', '') });
        }
        if (gpuConfig.gpu_count) {
            chips.push({ label: 'GPU Count', value: gpuConfig.gpu_count });
        }
        if (gpuConfig.preemptible !== undefined) {
            chips.push({ label: 'Preemptible', value: gpuConfig.preemptible ? 'Yes' : 'No' });
        }

        if (chips.length === 0) {
            container.innerHTML = '<span class="exp-view-no-filters">No training parameters</span>';
            return;
        }

        container.innerHTML = chips.map(chip => `
            <div class="exp-view-param-chip">
                <span class="exp-view-param-chip-label">${chip.label}:</span>
                <span class="exp-view-param-chip-value">${chip.value}</span>
            </div>
        `).join('');
    }

    // =============================================================================
    // REGISTRY & DEPLOYMENT SECTIONS (Training Run Mode) - Consolidated Accordion
    // =============================================================================

    function renderRegistryDeploymentSection(data) {
        const section = document.getElementById('expViewRegistryDeploymentSection');
        const container = document.getElementById('expViewRegistryDeploymentContent');
        const statusBadge = document.getElementById('expViewRegistryDeploymentStatus');

        // Only show for training_run mode with terminal status
        if (state.mode !== 'training_run' || !data ||
            !['completed', 'not_blessed', 'failed'].includes(data.status)) {
            section.style.display = 'none';
            return;
        }

        section.style.display = 'block';

        // Determine overall status for the badge
        let badgeText = '';
        let badgeClass = '';
        if (data.is_deployed) {
            badgeText = 'Live';
            badgeClass = 'status-live';
        } else if (data.vertex_model_name) {
            badgeText = 'Registered';
            badgeClass = 'status-registered';
        } else if (data.is_blessed === false) {
            badgeText = 'Failed';
            badgeClass = 'status-failed';
        } else {
            badgeText = 'Ready';
            badgeClass = 'status-ready';
        }

        // Update status badge
        statusBadge.textContent = badgeText;
        statusBadge.className = 'exp-view-accordion-status ' + badgeClass;

        // Build Registry Card HTML
        let registryHtml = '';
        if (data.is_blessed === false && data.status === 'not_blessed') {
            // Not blessed run - show option to force push anyway
            registryHtml = `
                <div class="exp-view-registry-deployment-card">
                    <div class="exp-view-registry-deployment-card-header">
                        <div class="exp-view-registry-deployment-icon icon-failed">
                            <i class="fas fa-times-circle"></i>
                        </div>
                        <div class="exp-view-registry-deployment-info">
                            <div class="exp-view-registry-deployment-label">Evaluation Failed</div>
                            <div class="exp-view-registry-deployment-detail">Model did not meet blessing thresholds</div>
                        </div>
                    </div>
                    <div class="exp-view-registry-deployment-actions">
                        <button class="btn-outcome-action btn-warning" onclick="ExpViewModal.pushToRegistry(${data.id})">
                            <i class="fas fa-exclamation-triangle"></i> Push Anyway
                        </button>
                    </div>
                </div>
            `;
        } else if (!data.vertex_model_name && data.status === 'completed') {
            // Completed run without registration - show register button
            registryHtml = `
                <div class="exp-view-registry-deployment-card">
                    <div class="exp-view-registry-deployment-card-header">
                        <div class="exp-view-registry-deployment-icon icon-pending">
                            <i class="fas fa-clock"></i>
                        </div>
                        <div class="exp-view-registry-deployment-info">
                            <div class="exp-view-registry-deployment-label">Not Registered</div>
                            <div class="exp-view-registry-deployment-detail">Training completed, registration pending</div>
                        </div>
                    </div>
                    <div class="exp-view-registry-deployment-actions">
                        <button class="btn-outcome-action" onclick="ExpViewModal.registerModel(${data.id})">
                            <i class="fas fa-upload"></i> Register Model
                        </button>
                    </div>
                </div>
            `;
        } else if (!data.vertex_model_name) {
            // Other non-registered states (e.g., still running)
            registryHtml = `
                <div class="exp-view-registry-deployment-card">
                    <div class="exp-view-registry-deployment-card-header">
                        <div class="exp-view-registry-deployment-icon icon-pending">
                            <i class="fas fa-clock"></i>
                        </div>
                        <div class="exp-view-registry-deployment-info">
                            <div class="exp-view-registry-deployment-label">Not Registered</div>
                            <div class="exp-view-registry-deployment-detail">Waiting for training to complete</div>
                        </div>
                    </div>
                </div>
            `;
        } else {
            registryHtml = `
                <div class="exp-view-registry-deployment-card">
                    <div class="exp-view-registry-deployment-card-header">
                        <div class="exp-view-registry-deployment-icon icon-success">
                            <i class="fas fa-check-circle"></i>
                        </div>
                        <div class="exp-view-registry-deployment-info">
                            <div class="exp-view-registry-deployment-label">Registered</div>
                            <div class="exp-view-registry-deployment-detail">${escapeHtml(data.vertex_model_name)} (${data.vertex_model_version || 'v1'})</div>
                        </div>
                    </div>
                    <div class="exp-view-registry-deployment-rows">
                        <div class="exp-view-registry-deployment-row">
                            <span class="exp-view-registry-deployment-key">Registered:</span>
                            <span class="exp-view-registry-deployment-value">${formatDateTime(data.registered_at) || '-'}</span>
                        </div>
                        <div class="exp-view-registry-deployment-row">
                            <span class="exp-view-registry-deployment-key">Blessing:</span>
                            <span class="exp-view-registry-deployment-value value-success">
                                <i class="fas fa-check"></i> Passed
                            </span>
                        </div>
                    </div>
                </div>
            `;
        }

        // Build Deployment Card HTML (only if registered)
        let deploymentHtml = '';
        if (data.vertex_model_name) {
            if (data.is_deployed) {
                deploymentHtml = `
                    <div class="exp-view-registry-deployment-card">
                        <div class="exp-view-registry-deployment-card-header">
                            <div class="exp-view-registry-deployment-icon icon-success">
                                <i class="fas fa-rocket"></i>
                            </div>
                            <div class="exp-view-registry-deployment-info">
                                <div class="exp-view-registry-deployment-label">Deployed</div>
                                <div class="exp-view-registry-deployment-detail">Model is serving predictions</div>
                            </div>
                        </div>
                        <div class="exp-view-registry-deployment-rows">
                            <div class="exp-view-registry-deployment-row">
                                <span class="exp-view-registry-deployment-key">Deployed:</span>
                                <span class="exp-view-registry-deployment-value">${formatDateTime(data.deployed_at) || '-'}</span>
                            </div>
                        </div>
                        <div class="exp-view-registry-deployment-actions">
                            <button class="btn-outcome-action btn-danger" onclick="ExpViewModal.undeployTrainingRun(${data.id})">
                                <i class="fas fa-stop"></i> Undeploy
                            </button>
                        </div>
                    </div>
                `;
            } else {
                deploymentHtml = `
                    <div class="exp-view-registry-deployment-card">
                        <div class="exp-view-registry-deployment-card-header">
                            <div class="exp-view-registry-deployment-icon icon-idle">
                                <i class="fas fa-pause-circle"></i>
                            </div>
                            <div class="exp-view-registry-deployment-info">
                                <div class="exp-view-registry-deployment-label">Ready to Deploy</div>
                                <div class="exp-view-registry-deployment-detail">Model is registered and ready</div>
                            </div>
                        </div>
                        <div class="exp-view-registry-deployment-actions">
                            <button class="btn-outcome-action" onclick="ExpViewModal.deployTrainingRun(${data.id})">
                                <i class="fas fa-rocket"></i> Deploy to Vertex AI
                            </button>
                            <button class="btn-outcome-action btn-secondary" onclick="ExpViewModal.deployToCloudRun(${data.id})">
                                <i class="fas fa-cloud"></i> Deploy to Cloud Run
                            </button>
                            <button class="btn-outcome-action btn-schedule" onclick="ExpViewModal.scheduleRetraining(${data.id})">
                                <i class="fas fa-calendar-alt"></i> Schedule Retraining
                            </button>
                        </div>
                    </div>
                `;
            }
        }

        // Combine into grid layout
        let html = '<div class="exp-view-registry-deployment-grid">';
        html += registryHtml;
        if (deploymentHtml) {
            html += deploymentHtml;
        }
        html += '</div>';

        container.innerHTML = html;
    }

    // Legacy function wrappers for backward compatibility
    function renderRegistrySection(data) {
        renderRegistryDeploymentSection(data);
    }

    function renderDeploymentSection(/* data */) {
        // No-op - handled by renderRegistryDeploymentSection
    }

    // Action handlers for Registry & Deployment
    async function pushToRegistry(runId) {
        if (!confirm('Are you sure you want to push this model to the registry?')) return;

        try {
            const response = await fetch(`/api/training-runs/${runId}/push/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });
            const data = await response.json();

            if (data.success) {
                alert(data.message || 'Model pushed to registry');
                // Refresh the modal
                open(runId, { mode: 'training_run' });
            } else {
                alert('Failed to push: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error pushing to registry:', error);
            alert('Error pushing to registry');
        }
    }

    async function registerModel(runId) {
        // Use styled confirmation modal if available, otherwise fall back to native confirm
        if (typeof TrainingCards !== 'undefined' && TrainingCards.showConfirmModal) {
            TrainingCards.showConfirmModal({
                title: 'Register Model',
                message: 'Are you sure you want to register this model to Vertex AI Model Registry?',
                confirmText: 'Register',
                cancelText: 'Cancel',
                type: 'success',
                confirmButtonClass: 'btn-neu-save',      // Green for positive action
                cancelButtonClass: 'btn-neu-cancel',     // Red for cancel
                onConfirm: () => doRegisterModel(runId)
            });
        } else {
            if (!confirm('Are you sure you want to register this model to Vertex AI Model Registry?')) return;
            doRegisterModel(runId);
        }
    }

    async function doRegisterModel(runId) {
        // Helper to show toast notification
        const showToast = (message, type) => {
            if (typeof TrainingCards !== 'undefined' && TrainingCards.showToast) {
                TrainingCards.showToast(message, type);
            } else {
                alert(message);
            }
        };

        try {
            const response = await fetch(`/api/training-runs/${runId}/register/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });
            const data = await response.json();

            if (data.success) {
                showToast(data.message || 'Model registered to registry', 'success');
                // Refresh the modal
                open(runId, { mode: 'training_run' });
            } else {
                showToast('Failed to register: ' + (data.error || 'Unknown error'), 'error');
            }
        } catch (error) {
            console.error('Error registering model:', error);
            showToast('Error registering model', 'error');
        }
    }

    async function deployTrainingRun(runId) {
        if (!confirm('Are you sure you want to deploy this model to a Vertex AI Endpoint?')) return;

        try {
            const response = await fetch(`/api/training-runs/${runId}/deploy/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });
            const data = await response.json();

            if (data.success) {
                alert(data.message || 'Model deployment started');
                // Refresh the modal
                open(runId, { mode: 'training_run' });
            } else {
                alert('Failed to deploy: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error deploying model:', error);
            alert('Error deploying model');
        }
    }

    async function deployToCloudRun(runId) {
        if (!confirm('Are you sure you want to deploy this model to Cloud Run? This will create a serverless TF Serving endpoint.')) return;

        try {
            const response = await fetch(`/api/training-runs/${runId}/deploy-cloud-run/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });
            const data = await response.json();

            if (data.success) {
                alert(data.message || 'Model deployed to Cloud Run');
                // Refresh the modal
                open(runId, { mode: 'training_run' });
            } else {
                alert('Failed to deploy: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error deploying to Cloud Run:', error);
            alert('Error deploying to Cloud Run');
        }
    }

    async function undeployTrainingRun(runId) {
        if (!confirm('Are you sure you want to undeploy this model? It will no longer serve predictions.')) return;

        try {
            // For training runs, we need to get the model ID first or use a training-run specific endpoint
            // The undeploy endpoint is on the models API, so we'll use the model ID from the run data
            const run = state.currentRun;
            if (!run || !run.model_id) {
                alert('Cannot undeploy: Model ID not found');
                return;
            }

            const response = await fetch(`/api/models/${run.model_id}/undeploy/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });
            const data = await response.json();

            if (data.success) {
                alert('Model undeployed successfully');
                // Refresh the modal
                open(runId, { mode: 'training_run' });
            } else {
                alert('Failed to undeploy: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error undeploying model:', error);
            alert('Error undeploying model');
        }
    }

    function scheduleRetraining(runId) {
        // Close the view modal to show the schedule modal
        close();

        // Open schedule modal for this training run
        if (typeof ScheduleModal !== 'undefined') {
            ScheduleModal.configure({
                onSuccess: function(schedule) {
                    // Show success toast
                    const toast = document.createElement('div');
                    toast.className = 'toast toast-success';
                    toast.style.cssText = `
                        position: fixed;
                        bottom: 20px;
                        right: 20px;
                        padding: 12px 20px;
                        border-radius: 8px;
                        color: white;
                        font-size: 14px;
                        z-index: 10001;
                        animation: slideIn 0.3s ease;
                        background-color: #16a34a;
                    `;
                    toast.textContent = `Schedule "${schedule.name}" created successfully`;
                    document.body.appendChild(toast);
                    setTimeout(() => {
                        toast.style.animation = 'slideOut 0.3s ease';
                        setTimeout(() => toast.remove(), 300);
                    }, 3000);

                    // Refresh training runs if available
                    if (typeof TrainingCards !== 'undefined') {
                        TrainingCards.loadTrainingRuns();
                    }
                    // Also refresh schedules list if available
                    if (typeof TrainingSchedules !== 'undefined') {
                        TrainingSchedules.loadSchedules();
                    }
                }
            });
            ScheduleModal.openForTrainingRun(runId);
        } else {
            alert('Schedule modal is not available. Please refresh the page.');
        }
    }

    function renderTrainingRunPipeline(run) {
        const pipelineContent = document.getElementById('expViewTabPipeline');
        if (!pipelineContent) return;

        const stageDetails = run.stage_details || [];

        // Create stage status map
        const stageStatusMap = {};
        stageDetails.forEach(stage => {
            stageStatusMap[stage.name?.toLowerCase()] = stage.status;
        });

        // Progress section for running runs
        const isRunning = run.status === 'running' || run.status === 'submitting';
        const progressSection = document.getElementById('expViewProgressSection');
        if (progressSection) {
            progressSection.style.display = isRunning ? 'flex' : 'none';
            if (isRunning) {
                const percent = run.progress_percent || 0;
                document.getElementById('expViewProgressBar').style.width = `${percent}%`;
                document.getElementById('expViewProgressText').textContent = `${percent}%`;
            }
        }

        // Render 8-stage DAG using pipeline_dag.js if available
        if (typeof renderPipelineStages === 'function') {
            const stages = TRAINING_PIPELINE_STAGES.map(stage => {
                const status = stageStatusMap[stage.id] || 'pending';
                const stageDetail = stageDetails.find(s => s.name?.toLowerCase() === stage.id);
                return {
                    name: stage.name,
                    status: status,
                    duration_seconds: stageDetail?.duration_seconds || null
                };
            });
            renderPipelineStages(stages);
        }
    }

    function startTrainingRunPolling(runId) {
        stopPolling();

        state.pollInterval = setInterval(async () => {
            try {
                const url = buildUrl(config.endpoints.trainingRunDetails, { id: runId });
                const response = await fetch(url);
                const data = await response.json();

                if (data.success) {
                    const run = data.training_run;
                    populateTrainingRunModal(run);
                    state.currentRun = run;

                    if (config.onUpdate) {
                        config.onUpdate(run);
                    }

                    if (['completed', 'failed', 'cancelled', 'not_blessed'].includes(run.status)) {
                        stopPolling();
                    }
                }
            } catch (error) {
                console.error('Training run polling error:', error);
            }
        }, 10000);
    }

    function renderRepositoryTab() {
        const container = document.getElementById('expViewTabRepository');
        if (!container) return;

        container.innerHTML = `
            <div class="exp-view-section-group">
                <h4 class="exp-view-group-title">Repository Information</h4>
                <div class="exp-view-chart-placeholder">
                    <i class="fas fa-code-branch"></i>
                    <p>Repository information will be available in a future update</p>
                </div>
            </div>
        `;
    }

    function renderDeploymentTab() {
        const container = document.getElementById('expViewTabDeployment');
        if (!container) return;

        // Different rendering for model mode vs training_run mode
        if (state.mode === 'model' && state.currentModel) {
            renderModelDeploymentTab(state.currentModel);
            return;
        }

        container.innerHTML = `
            <div class="exp-view-section-group">
                <h4 class="exp-view-group-title">Deployment Status</h4>
                <div class="exp-view-chart-placeholder">
                    <i class="fas fa-rocket"></i>
                    <p>Deployment information will be available in a future update</p>
                </div>
            </div>
        `;
    }

    // =============================================================================
    // MODEL MODE FUNCTIONS
    // =============================================================================

    async function openForModel(modelId, options = {}) {
        state.mode = 'model';

        try {
            const url = `/api/models/${modelId}/`;
            const response = await fetch(url);
            const data = await response.json();

            if (!data.success) {
                console.error('Failed to load model:', data.error);
                return;
            }

            openWithModelData(data.model, options);
        } catch (error) {
            console.error('Error loading model details:', error);
        }
    }

    function openWithModelData(model, options = {}) {
        state.mode = 'model';
        state.currentModel = model;

        // Reset state
        state.dataCache = {
            statistics: null,
            schema: null,
            errorDetails: null,
            trainingHistory: null,
            versions: null,
            lineage: null,
            _loadingInsights: false,
            _statsData: null,
            _schemaData: null
        };

        // Set initial tab
        const initialTab = options.tab || 'overview';
        state.currentTab = initialTab;

        // Reset tabs
        document.querySelectorAll('.exp-view-tab').forEach(t => t.classList.remove('active'));
        const targetTab = document.querySelector(`.exp-view-tab[data-tab="${initialTab}"]`);
        if (targetTab) targetTab.classList.add('active');

        document.querySelectorAll('.exp-view-tab-content').forEach(c => c.classList.remove('active'));
        const targetContent = document.getElementById(`expViewTab${initialTab.charAt(0).toUpperCase() + initialTab.slice(1)}`);
        if (targetContent) targetContent.classList.add('active');

        // Update visible tabs for model mode
        updateVisibleTabs();

        // Populate modal with model data
        populateModelModal(model);
        document.getElementById('expViewModal').classList.remove('hidden');

        // Load initial tab content
        if (initialTab === 'versions') {
            loadModelVersions(model.id);
        } else if (initialTab === 'lineage') {
            loadModelLineage(model.id);
        }
    }

    function populateModelModal(model) {
        // Store current model for tab data loading
        window.currentViewModel = model;

        // Status gradient on header based on model_status
        const header = document.getElementById('expViewHeader');
        header.className = `modal-header exp-view-header ${model.model_status}`;

        // Status panel
        const statusPanel = document.getElementById('expViewStatusPanel');
        statusPanel.className = `exp-view-status-panel ${model.model_status}`;

        // Status icon
        const statusIcon = document.getElementById('expViewStatusIcon');
        const statusIcons = {
            'deployed': 'fa-rocket',
            'idle': 'fa-pause-circle',
            'not_blessed': 'fa-exclamation-circle',
            'pending': 'fa-clock'
        };
        statusIcon.className = `exp-view-status-icon ${model.model_status}`;
        statusIcon.innerHTML = `<i class="fas ${statusIcons[model.model_status] || 'fa-cube'}"></i>`;

        // Title (Model name)
        document.getElementById('expViewTitle').textContent = model.vertex_model_name || 'Model';

        // Model version as subtitle
        const expNameEl = document.getElementById('expViewExpName');
        expNameEl.textContent = `v${model.vertex_model_version || '1'} - Run #${model.run_number}`;
        expNameEl.style.display = '';

        // Model type badge in header
        const typeBadgeEl = document.getElementById('expViewTypeBadge');
        const modelType = (model.model_type || 'retrieval').toLowerCase();
        const badgeContents = {
            'retrieval': '<i class="fas fa-search"></i> Retrieval',
            'ranking': '<i class="fas fa-sort-amount-down"></i> Ranking',
            'multitask': '<i class="fas fa-layer-group"></i> Multitask'
        };
        typeBadgeEl.className = `exp-view-header-type-badge ${modelType}`;
        typeBadgeEl.innerHTML = badgeContents[modelType] || badgeContents['retrieval'];

        // Description
        const descEl = document.getElementById('expViewDescription');
        descEl.textContent = '';
        descEl.style.display = 'none';

        // Start/End times (registered_at, deployed_at)
        document.getElementById('expViewStartTime').textContent = model.registered_at ?
            formatDateTime(model.registered_at) : '-';
        document.getElementById('expViewEndTime').textContent = model.deployed_at ?
            formatDateTime(model.deployed_at) : '-';

        // Overview Tab - render model overview
        renderModelOverview(model);
    }

    function renderModelOverview(model) {
        // Dataset section
        const datasetName = model.dataset_name || '-';
        document.getElementById('expViewDatasetName').textContent = datasetName;
        document.getElementById('expViewDatasetDetails').innerHTML =
            `<div class="exp-view-config-chip">${datasetName}</div>`;

        // Features config
        const featureConfigName = model.feature_config_name || '-';
        document.getElementById('expViewFeaturesConfigName').textContent = featureConfigName;
        document.getElementById('expViewFeaturesConfigContent').innerHTML =
            `<div class="exp-view-config-chip">${featureConfigName}</div>`;

        // Model config
        const modelConfigName = model.model_config_name || '-';
        document.getElementById('expViewModelConfigName').textContent = modelConfigName;
        document.getElementById('expViewModelConfigContent').innerHTML = `
            <div class="exp-view-config-chips">
                <div class="exp-view-config-chip">${modelConfigName}</div>
                ${model.retrieval_algorithm ? `<div class="exp-view-config-chip">${model.retrieval_algorithm}</div>` : ''}
            </div>
        `;

        // For models, clear sampling chips (since models don't have sampling config)
        const samplingContainer = document.getElementById('expViewSamplingChips');
        if (samplingContainer) samplingContainer.innerHTML = '<span style="color:#9ca3af;">N/A</span>';

        // Training parameters - show GPU config if available
        const paramsContainer = document.getElementById('expViewTrainingParamsChips');
        if (paramsContainer) {
            let paramsHtml = '';
            if (model.training_params) {
                const params = model.training_params;
                if (params.epochs) paramsHtml += `<div class="exp-view-config-chip">Epochs: ${params.epochs}</div>`;
                if (params.batch_size) paramsHtml += `<div class="exp-view-config-chip">Batch: ${params.batch_size}</div>`;
                if (params.learning_rate) paramsHtml += `<div class="exp-view-config-chip">LR: ${params.learning_rate}</div>`;
            }
            if (model.gpu_config) {
                const gpu = model.gpu_config;
                if (gpu.machine_type) paramsHtml += `<div class="exp-view-config-chip">${gpu.machine_type}</div>`;
                if (gpu.accelerator_type) paramsHtml += `<div class="exp-view-config-chip">${gpu.accelerator_type}</div>`;
            }
            paramsContainer.innerHTML = paramsHtml || '<span style="color:#9ca3af;">No parameters</span>';
        }

        // Results Summary (metrics)
        renderModelMetrics(model);
    }

    function renderModelMetrics(model) {
        const resultsSummary = document.getElementById('expViewResultsSummary');
        const metricsContainer = document.getElementById('expViewMetricsSummary');

        if (!model.metrics) {
            resultsSummary.classList.add('hidden');
            return;
        }

        resultsSummary.classList.remove('hidden');

        let metricsHtml = '';
        const formatMetric = v => v != null ? v.toFixed(4) : 'N/A';
        const formatRecall = v => v != null ? (v * 100).toFixed(0) + '%' : 'N/A';

        if (model.model_type === 'ranking') {
            metricsHtml = `
                <div class="exp-view-metric-card">
                    <div class="exp-view-metric-card-label">RMSE</div>
                    <div class="exp-view-metric-card-value">${formatMetric(model.metrics.rmse)}</div>
                </div>
                <div class="exp-view-metric-card">
                    <div class="exp-view-metric-card-label">MAE</div>
                    <div class="exp-view-metric-card-value">${formatMetric(model.metrics.mae)}</div>
                </div>
                <div class="exp-view-metric-card">
                    <div class="exp-view-metric-card-label">Test RMSE</div>
                    <div class="exp-view-metric-card-value">${formatMetric(model.metrics.test_rmse)}</div>
                </div>
                <div class="exp-view-metric-card">
                    <div class="exp-view-metric-card-label">Test MAE</div>
                    <div class="exp-view-metric-card-value">${formatMetric(model.metrics.test_mae)}</div>
                </div>
            `;
        } else {
            metricsHtml = `
                <div class="exp-view-metric-card">
                    <div class="exp-view-metric-card-label">R@5</div>
                    <div class="exp-view-metric-card-value">${formatRecall(model.metrics.recall_at_5)}</div>
                </div>
                <div class="exp-view-metric-card">
                    <div class="exp-view-metric-card-label">R@10</div>
                    <div class="exp-view-metric-card-value">${formatRecall(model.metrics.recall_at_10)}</div>
                </div>
                <div class="exp-view-metric-card">
                    <div class="exp-view-metric-card-label">R@50</div>
                    <div class="exp-view-metric-card-value">${formatRecall(model.metrics.recall_at_50)}</div>
                </div>
                <div class="exp-view-metric-card">
                    <div class="exp-view-metric-card-label">R@100</div>
                    <div class="exp-view-metric-card-value">${formatRecall(model.metrics.recall_at_100)}</div>
                </div>
            `;
        }

        metricsContainer.innerHTML = metricsHtml;
    }

    async function loadModelVersions(modelId) {
        const container = document.getElementById('expViewTabVersions');
        if (!container) return;

        container.innerHTML = `
            <div class="exp-view-loading">
                <i class="fas fa-spinner fa-spin"></i>
                <span>Loading versions...</span>
            </div>
        `;

        try {
            const response = await fetch(`/api/models/${modelId}/versions/`);
            const data = await response.json();

            if (data.success) {
                state.dataCache.versions = data.versions;
                renderVersionsTab(data.model_name, data.versions);
            } else {
                container.innerHTML = `
                    <div class="exp-view-data-message">
                        <i class="fas fa-exclamation-circle"></i>
                        <span>Failed to load versions: ${data.error}</span>
                    </div>
                `;
            }
        } catch (error) {
            console.error('Error loading model versions:', error);
            container.innerHTML = `
                <div class="exp-view-data-message">
                    <i class="fas fa-exclamation-circle"></i>
                    <span>Error loading versions</span>
                </div>
            `;
        }
    }

    function renderVersionsTab(modelName, versions) {
        const container = document.getElementById('expViewTabVersions');
        if (!container) return;

        const formatDate = (isoStr) => {
            if (!isoStr) return '-';
            return new Date(isoStr).toLocaleDateString('en-US', {
                month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit'
            });
        };

        let tableRows = versions.map((v, idx) => `
            <tr class="${v.id === state.currentModel?.id ? 'active' : ''}" onclick="ExpViewModal.selectModelVersion(${v.id})">
                <td>v${v.vertex_model_version || (versions.length - idx)}</td>
                <td>Run #${v.run_number}</td>
                <td>
                    <span class="models-status-badge ${v.model_status}">
                        ${v.model_status === 'deployed' ? '<i class="fas fa-rocket"></i>' :
                          v.model_status === 'idle' ? '<i class="fas fa-pause-circle"></i>' :
                          '<i class="fas fa-exclamation-circle"></i>'}
                        ${v.model_status}
                    </span>
                </td>
                <td>${v.is_blessed ? '<i class="fas fa-check-circle" style="color:#10b981;"></i>' : '<i class="fas fa-times-circle" style="color:#f97316;"></i>'}</td>
                <td>${formatDate(v.registered_at)}</td>
            </tr>
        `).join('');

        container.innerHTML = `
            <div class="exp-view-section-group">
                <h4 class="exp-view-group-title">Version History - ${modelName}</h4>
                <div style="border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden;">
                    <table class="models-table" style="margin: 0;">
                        <thead>
                            <tr>
                                <th>Version</th>
                                <th>Training Run</th>
                                <th>Status</th>
                                <th>Blessed</th>
                                <th>Registered</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${tableRows}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    function selectModelVersion(modelId) {
        // Close and reopen with new model
        close();
        setTimeout(() => openForModel(modelId), 100);
    }

    function renderArtifactsTab(model) {
        const container = document.getElementById('expViewTabArtifacts');
        if (!container) return;

        const artifacts = model.artifacts || {};
        const gcsPath = model.gcs_artifacts_path || '';

        let artifactsHtml = `
            <div class="exp-view-section-group">
                <h4 class="exp-view-group-title">Model Artifacts</h4>
                <div class="exp-view-artifact-list">
        `;

        // GCS Artifacts Path
        if (gcsPath) {
            artifactsHtml += `
                <div class="exp-view-artifact-item">
                    <div class="exp-view-artifact-label">
                        <i class="fas fa-folder"></i> GCS Artifacts Path
                    </div>
                    <div class="exp-view-artifact-value">
                        <code>${gcsPath}</code>
                        <button class="exp-view-copy-btn" onclick="ExpViewModal.copyToClipboard('${gcsPath}')">
                            <i class="fas fa-copy"></i>
                        </button>
                    </div>
                </div>
            `;
        }

        // Model Resource Name
        if (model.vertex_model_resource_name) {
            artifactsHtml += `
                <div class="exp-view-artifact-item">
                    <div class="exp-view-artifact-label">
                        <i class="fas fa-cube"></i> Model Resource Name
                    </div>
                    <div class="exp-view-artifact-value">
                        <code>${model.vertex_model_resource_name}</code>
                        <button class="exp-view-copy-btn" onclick="ExpViewModal.copyToClipboard('${model.vertex_model_resource_name}')">
                            <i class="fas fa-copy"></i>
                        </button>
                    </div>
                </div>
            `;
        }

        // Endpoint Resource Name (if deployed)
        if (model.endpoint_resource_name) {
            artifactsHtml += `
                <div class="exp-view-artifact-item">
                    <div class="exp-view-artifact-label">
                        <i class="fas fa-server"></i> Endpoint Resource Name
                    </div>
                    <div class="exp-view-artifact-value">
                        <code>${model.endpoint_resource_name}</code>
                        <button class="exp-view-copy-btn" onclick="ExpViewModal.copyToClipboard('${model.endpoint_resource_name}')">
                            <i class="fas fa-copy"></i>
                        </button>
                    </div>
                </div>
            `;
        }

        // Additional artifacts from the artifacts JSON
        if (Object.keys(artifacts).length > 0) {
            Object.entries(artifacts).forEach(([key, value]) => {
                if (value) {
                    artifactsHtml += `
                        <div class="exp-view-artifact-item">
                            <div class="exp-view-artifact-label">
                                <i class="fas fa-file"></i> ${key.replace(/_/g, ' ')}
                            </div>
                            <div class="exp-view-artifact-value">
                                <code>${value}</code>
                                <button class="exp-view-copy-btn" onclick="ExpViewModal.copyToClipboard('${value}')">
                                    <i class="fas fa-copy"></i>
                                </button>
                            </div>
                        </div>
                    `;
                }
            });
        }

        artifactsHtml += `
                </div>
            </div>
        `;

        container.innerHTML = artifactsHtml;
    }

    function renderModelDeploymentTab(model) {
        const container = document.getElementById('expViewTabDeployment');
        if (!container) return;

        const isDeployed = model.is_deployed;
        const isBlessed = model.is_blessed;

        let statusHtml;
        if (isDeployed) {
            statusHtml = `
                <div class="exp-view-deployment-status deployed">
                    <div class="exp-view-deployment-status-icon">
                        <i class="fas fa-check-circle"></i>
                    </div>
                    <div class="exp-view-deployment-status-text">
                        <strong>Deployed</strong>
                        <span>Model is currently serving predictions</span>
                    </div>
                </div>
                <div class="exp-view-deployment-info">
                    <div class="exp-view-info-row">
                        <span class="exp-view-info-label">Endpoint</span>
                        <span class="exp-view-info-value">${model.endpoint_resource_name || '-'}</span>
                    </div>
                    <div class="exp-view-info-row">
                        <span class="exp-view-info-label">Deployed At</span>
                        <span class="exp-view-info-value">${model.deployed_at ? formatDateTime(model.deployed_at) : '-'}</span>
                    </div>
                </div>
                <div class="exp-view-deployment-actions">
                    <button class="btn btn-danger" onclick="ExpViewModal.undeployModel(${model.id})">
                        <i class="fas fa-stop-circle"></i> Undeploy Model
                    </button>
                </div>
            `;
        } else if (isBlessed) {
            statusHtml = `
                <div class="exp-view-deployment-status idle">
                    <div class="exp-view-deployment-status-icon">
                        <i class="fas fa-pause-circle"></i>
                    </div>
                    <div class="exp-view-deployment-status-text">
                        <strong>Ready to Deploy</strong>
                        <span>Model is blessed and can be deployed</span>
                    </div>
                </div>
                <div class="exp-view-deployment-actions">
                    <button class="btn btn-primary" onclick="ExpViewModal.deployModel(${model.id})">
                        <i class="fas fa-rocket"></i> Deploy Model
                    </button>
                </div>
            `;
        } else {
            statusHtml = `
                <div class="exp-view-deployment-status not-blessed">
                    <div class="exp-view-deployment-status-icon">
                        <i class="fas fa-exclamation-circle"></i>
                    </div>
                    <div class="exp-view-deployment-status-text">
                        <strong>Not Blessed</strong>
                        <span>Model did not pass evaluation and cannot be deployed</span>
                    </div>
                </div>
            `;
        }

        container.innerHTML = `
            <div class="exp-view-section-group">
                <h4 class="exp-view-group-title">Deployment Status</h4>
                ${statusHtml}
            </div>
        `;
    }

    async function loadModelLineage(modelId) {
        const container = document.getElementById('expViewTabLineage');
        if (!container) return;

        container.innerHTML = `
            <div class="exp-view-loading">
                <i class="fas fa-spinner fa-spin"></i>
                <span>Loading lineage...</span>
            </div>
        `;

        try {
            const response = await fetch(`/api/models/${modelId}/lineage/`);
            const data = await response.json();

            if (data.success) {
                state.dataCache.lineage = data.lineage;
                renderLineageTab(data.lineage);
            } else {
                container.innerHTML = `
                    <div class="exp-view-data-message">
                        <i class="fas fa-exclamation-circle"></i>
                        <span>Failed to load lineage: ${data.error}</span>
                    </div>
                `;
            }
        } catch (error) {
            console.error('Error loading model lineage:', error);
            container.innerHTML = `
                <div class="exp-view-data-message">
                    <i class="fas fa-exclamation-circle"></i>
                    <span>Error loading lineage</span>
                </div>
            `;
        }
    }

    function renderLineageTab(lineage) {
        const container = document.getElementById('expViewTabLineage');
        if (!container) return;

        const nodeIcons = {
            'dataset': 'fa-database',
            'feature_config': 'fa-sliders-h',
            'experiment': 'fa-flask',
            'training_run': 'fa-cogs',
            'model': 'fa-cube',
            'endpoint': 'fa-server'
        };

        const nodeColors = {
            'dataset': '#3b82f6',
            'feature_config': '#8b5cf6',
            'experiment': '#f59e0b',
            'training_run': '#10b981',
            'model': '#ec4899',
            'endpoint': '#14b8a6'
        };

        let nodesHtml = lineage.nodes.map(node => `
            <div class="exp-view-lineage-node" style="border-left: 4px solid ${nodeColors[node.type] || '#6b7280'};">
                <div class="exp-view-lineage-node-icon" style="color: ${nodeColors[node.type] || '#6b7280'};">
                    <i class="fas ${nodeIcons[node.type] || 'fa-circle'}"></i>
                </div>
                <div class="exp-view-lineage-node-info">
                    <div class="exp-view-lineage-node-type">${node.type.replace('_', ' ')}</div>
                    <div class="exp-view-lineage-node-label">${node.label}</div>
                </div>
            </div>
        `).join('<div class="exp-view-lineage-arrow"><i class="fas fa-arrow-down"></i></div>');

        container.innerHTML = `
            <div class="exp-view-section-group">
                <h4 class="exp-view-group-title">Model Lineage</h4>
                <div class="exp-view-lineage-graph">
                    ${nodesHtml}
                </div>
            </div>
        `;
    }

    async function deployModel(modelId) {
        if (!confirm('Are you sure you want to deploy this model?')) return;

        try {
            const response = await fetch(`/api/models/${modelId}/deploy/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });
            const data = await response.json();

            if (data.success) {
                alert('Model deployment started');
                // Refresh the modal
                openForModel(modelId);
            } else {
                alert('Failed to deploy: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error deploying model:', error);
            alert('Error deploying model');
        }
    }

    async function undeployModel(modelId) {
        if (!confirm('Are you sure you want to undeploy this model? It will no longer serve predictions.')) return;

        try {
            const response = await fetch(`/api/models/${modelId}/undeploy/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });
            const data = await response.json();

            if (data.success) {
                alert('Model undeployed successfully');
                // Refresh the modal
                openForModel(modelId);
            } else {
                alert('Failed to undeploy: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error undeploying model:', error);
            alert('Error undeploying model');
        }
    }

    function copyToClipboard(text) {
        navigator.clipboard.writeText(text).then(() => {
            // Show brief visual feedback
            const btn = event.target.closest('.exp-view-copy-btn');
            if (btn) {
                const icon = btn.querySelector('i');
                icon.className = 'fas fa-check';
                setTimeout(() => { icon.className = 'fas fa-copy'; }, 1500);
            }
        }).catch(err => {
            console.error('Failed to copy:', err);
        });
    }

    function close(event) {
        if (event && event.target !== event.currentTarget) return;

        document.getElementById('expViewModal').classList.add('hidden');
        stopPolling();

        // Reset experiment state
        state.expId = null;
        state.currentExp = null;

        // Reset training run state
        state.runId = null;
        state.currentRun = null;

        // Reset model state
        state.modelId = null;
        state.currentModel = null;

        state.mode = 'experiment';

        state.dataCache = {
            statistics: null,
            schema: null,
            errorDetails: null,
            trainingHistory: null,
            versions: null,
            lineage: null,
            _loadingInsights: false,
            _statsData: null,
            _schemaData: null
        };

        // Destroy charts
        destroyCharts();

        // Reset DAG state if pipeline_dag.js is loaded
        if (typeof resetDagState === 'function') {
            resetDagState();
        }

        // Call onClose callback
        if (config.onClose) {
            config.onClose();
        }
    }

    function handleOverlayClick(event) {
        if (event.target === event.currentTarget) {
            close();
        }
    }

    function updateVisibleTabs() {
        const tabContainer = document.getElementById('expViewTabs');
        if (!tabContainer) return;

        // Determine which tabs to show based on mode
        let visibleTabs;
        if (state.mode === 'training_run') {
            visibleTabs = ['overview', 'pipeline', 'data', 'training'];
        } else if (state.mode === 'model') {
            visibleTabs = ['overview', 'versions', 'artifacts', 'deployment', 'lineage'];
        } else {
            visibleTabs = config.showTabs;
        }

        const allTabs = tabContainer.querySelectorAll('.exp-view-tab');
        allTabs.forEach(tab => {
            const tabName = tab.getAttribute('data-tab');
            if (visibleTabs.includes(tabName)) {
                tab.style.display = '';
            } else {
                tab.style.display = 'none';
            }
        });
    }

    // =============================================================================
    // MODAL POPULATION
    // =============================================================================

    function populateModal(exp) {
        // Store current exp for tab data loading
        window.currentViewExp = exp;

        // Status gradient on header
        const header = document.getElementById('expViewHeader');
        header.className = `modal-header exp-view-header ${exp.status}`;

        // Status panel
        const statusPanel = document.getElementById('expViewStatusPanel');
        statusPanel.className = `exp-view-status-panel ${exp.status}`;

        // Status icon
        const statusIcon = document.getElementById('expViewStatusIcon');
        const statusIcons = {
            'submitting': 'fa-sync fa-spin',
            'running': 'fa-sync fa-spin',
            'completed': 'fa-check',
            'failed': 'fa-exclamation',
            'cancelled': 'fa-ban',
            'pending': 'fa-clock'
        };
        statusIcon.className = `exp-view-status-icon ${exp.status}`;
        statusIcon.innerHTML = `<i class="fas ${statusIcons[exp.status] || 'fa-circle'}"></i>`;

        // Title (Exp #N)
        document.getElementById('expViewTitle').textContent = exp.display_name || `Exp #${exp.id}`;

        // Experiment name
        const expNameEl = document.getElementById('expViewExpName');
        expNameEl.textContent = exp.experiment_name || '';
        expNameEl.style.display = exp.experiment_name ? '' : 'none';

        // Model type badge in header
        const typeBadgeEl = document.getElementById('expViewTypeBadge');
        const modelType = (exp.model_type || exp.feature_config_type || 'retrieval').toLowerCase();
        const badgeContents = {
            'retrieval': '<i class="fas fa-search"></i> Retrieval',
            'ranking': '<i class="fas fa-sort-amount-down"></i> Ranking',
            'multitask': '<i class="fas fa-layer-group"></i> Retrieval / Ranking'
        };
        typeBadgeEl.className = `exp-view-header-type-badge ${modelType}`;
        typeBadgeEl.innerHTML = badgeContents[modelType] || badgeContents['retrieval'];

        // Description
        const descEl = document.getElementById('expViewDescription');
        descEl.textContent = exp.experiment_description || '';
        descEl.style.display = exp.experiment_description ? '' : 'none';

        // Start/End times
        document.getElementById('expViewStartTime').textContent = formatDateTime(exp.started_at || exp.created_at);
        document.getElementById('expViewEndTime').textContent = exp.completed_at ? formatDateTime(exp.completed_at) : '-';

        // Reset accordion states for overview tab
        resetAccordionStates();

        // Hide Registry & Deployment section for experiment mode
        const regDeploySection = document.getElementById('expViewRegistryDeploymentSection');
        if (regDeploySection) regDeploySection.style.display = 'none';

        // Overview Tab - Dataset section
        const datasetName = exp.dataset_name || exp.dataset?.name || 'Dataset';
        document.getElementById('expViewDatasetName').textContent = datasetName;

        // Load dataset details
        const datasetId = exp.dataset_id || exp.dataset?.id;
        if (datasetId) {
            loadDatasetDetails(datasetId);
        } else {
            document.getElementById('expViewDatasetDetails').innerHTML = '<div class="exp-view-no-filters">No dataset configured</div>';
        }

        // Load features config details
        const featureConfigName = exp.feature_config_name || exp.feature_config?.name || '-';
        document.getElementById('expViewFeaturesConfigName').textContent = featureConfigName;

        const featureConfigId = exp.feature_config_id || exp.feature_config?.id;
        if (featureConfigId) {
            loadFeaturesConfig(featureConfigId);
        } else {
            document.getElementById('expViewFeaturesConfigContent').innerHTML = '<div class="exp-view-no-filters">No features config</div>';
        }

        // Load model config details
        const modelConfigName = exp.model_config_name || exp.model_config?.name || '-';
        document.getElementById('expViewModelConfigName').textContent = modelConfigName;

        // Model type badge in accordion header
        const expModelType = (exp.model_type || exp.feature_config_type || 'retrieval').toLowerCase();
        const badgeSmall = document.getElementById('expViewModelTypeBadgeSmall');
        if (badgeSmall) {
            const badgeLabels = {
                'retrieval': 'Retrieval',
                'ranking': 'Ranking',
                'multitask': 'Multitask'
            };
            badgeSmall.textContent = badgeLabels[expModelType] || 'Retrieval';
            badgeSmall.className = 'exp-view-accordion-badge badge-' + expModelType;
        }

        const modelConfigId = exp.model_config_id || exp.model_config?.id;
        if (modelConfigId) {
            loadModelConfig(modelConfigId);
        } else {
            document.getElementById('expViewModelConfigContent').innerHTML = '<div class="exp-view-no-filters">No model config</div>';
        }

        // Sampling (chip format)
        renderSamplingChips(exp);

        // Training Parameters (chip format)
        renderTrainingParamsChips(exp);

        // Results Summary (overview tab)
        const resultsSummary = document.getElementById('expViewResultsSummary');
        if (exp.status === 'completed' && exp.metrics) {
            resultsSummary.classList.remove('hidden');
            const configType = exp.feature_config_type || exp.model_type || 'retrieval';
            renderMetricsSummary(exp.metrics, false, configType);
        } else {
            resultsSummary.classList.add('hidden');
        }

        // Pipeline Tab
        const isRunning = exp.status === 'running' || exp.status === 'submitting';
        const progressSection = document.getElementById('expViewProgressSection');
        if (progressSection) {
            progressSection.style.display = isRunning ? 'flex' : 'none';
            if (isRunning) {
                const percent = exp.progress_percent || 0;
                document.getElementById('expViewProgressBar').style.width = `${percent}%`;
                document.getElementById('expViewProgressText').textContent = `${percent}%`;
            }
        }

        // Render pipeline stages if pipeline_dag.js is loaded
        if (typeof renderPipelineStages === 'function') {
            renderPipelineStages(exp.stage_details || getDefaultStages());
        }

        // Training Tab - Final Metrics (hidden until MLflow data loads)
        const finalMetrics = document.getElementById('expViewFinalMetrics');
        if (finalMetrics) finalMetrics.classList.add('hidden');

        // Training Tab - Vocabulary
        const vocabSection = document.getElementById('expViewVocabSection');
        if (vocabSection) {
            if (exp.vocabulary_stats && Object.keys(exp.vocabulary_stats).length > 0) {
                vocabSection.classList.remove('hidden');
                renderVocabRows(exp.vocabulary_stats);
            } else {
                vocabSection.classList.add('hidden');
            }
        }
    }

    function getDefaultStages() {
        return [
            { name: 'Compile', status: 'pending', duration_seconds: null },
            { name: 'Examples', status: 'pending', duration_seconds: null },
            { name: 'Stats', status: 'pending', duration_seconds: null },
            { name: 'Schema', status: 'pending', duration_seconds: null },
            { name: 'Transform', status: 'pending', duration_seconds: null },
            { name: 'Train', status: 'pending', duration_seconds: null }
        ];
    }

    // =============================================================================
    // TAB SWITCHING
    // =============================================================================

    function switchTab(tabName) {
        state.currentTab = tabName;

        // Update tab buttons
        document.querySelectorAll('.exp-view-tab').forEach(t => t.classList.remove('active'));
        const activeTab = document.querySelector(`.exp-view-tab[data-tab="${tabName}"]`);
        if (activeTab) activeTab.classList.add('active');

        // Update tab content
        document.querySelectorAll('.exp-view-tab-content').forEach(c => c.classList.remove('active'));
        const tabContent = document.getElementById(`expViewTab${tabName.charAt(0).toUpperCase() + tabName.slice(1)}`);
        if (tabContent) tabContent.classList.add('active');

        // Handle mode-specific tab loading
        if (state.mode === 'model') {
            // Model mode tabs
            const model = state.currentModel;
            if (tabName === 'versions' && model) {
                if (!state.dataCache.versions) {
                    loadModelVersions(model.id);
                } else {
                    renderVersionsTab(model.vertex_model_name, state.dataCache.versions);
                }
            }
            if (tabName === 'artifacts' && model) {
                renderArtifactsTab(model);
            }
            if (tabName === 'deployment' && model) {
                renderModelDeploymentTab(model);
            }
            if (tabName === 'lineage' && model) {
                if (!state.dataCache.lineage) {
                    loadModelLineage(model.id);
                } else {
                    renderLineageTab(state.dataCache.lineage);
                }
            }
        } else if (state.mode === 'training_run') {
            // Training run mode tabs
            if (tabName === 'data') {
                loadDataInsights();
            }
            if (tabName === 'training') {
                if (state.dataCache.trainingHistory) {
                    renderCachedTrainingHistory();
                } else {
                    loadTrainingHistory();
                }
            }
            if (tabName === 'repository') {
                renderRepositoryTab();
            }
            if (tabName === 'deployment') {
                renderDeploymentTab();
            }
        } else {
            // Experiment mode tabs
            if (tabName === 'data') {
                loadDataInsights();
            }
            if (tabName === 'training') {
                if (state.dataCache.trainingHistory) {
                    renderCachedTrainingHistory();
                } else {
                    loadTrainingHistory();
                }
            }
        }
    }

    // =============================================================================
    // DATASET DETAILS
    // =============================================================================

    function loadDatasetDetails(datasetId) {
        const container = document.getElementById('expViewDatasetDetails');
        container.innerHTML = '<div class="exp-view-loading"><i class="fas fa-spinner fa-spin"></i> Loading...</div>';

        const url = buildUrl(config.endpoints.datasetSummary, { id: datasetId });

        fetch(url, {
            headers: { 'X-CSRFToken': getCookie('csrftoken') }
        })
        .then(response => response.json())
        .then(data => {
            if (data.status !== 'success') {
                container.innerHTML = '<div class="exp-view-no-filters">Failed to load dataset details</div>';
                return;
            }
            renderDatasetDetails(data.summary);
        })
        .catch(error => {
            console.error('Error loading dataset details:', error);
            container.innerHTML = '<div class="exp-view-no-filters">Failed to load dataset details</div>';
        });
    }

    function renderDatasetDetails(summary) {
        const container = document.getElementById('expViewDatasetDetails');
        const snapshot = summary.summary_snapshot || {};
        const filtersApplied = snapshot.filters_applied || {};
        const joinConfig = summary.join_config || {};

        let html = '';

        // Tables & Joins section
        const primaryTable = summary.tables.primary?.replace('raw_data.', '') || '-';
        html += `<div class="exp-view-ds-section">
            <div class="exp-view-ds-title"><i class="fas fa-database"></i>Tables & Joins</div>
            <div class="exp-view-ds-grid">
                <span class="label">Primary:</span>
                <span class="value">${primaryTable}</span>`;

        if (summary.tables.secondary?.length > 0) {
            html += `<span class="label">Secondary:</span>
                <span class="value">${summary.tables.secondary.map(t => t.replace('raw_data.', '')).join(', ')}</span>`;
        }
        html += `</div>`;

        // Join keys
        if (Object.keys(joinConfig).length > 0) {
            html += `<div class="exp-view-ds-join"><span>Join Keys:</span>`;
            for (const [table, configItem] of Object.entries(joinConfig)) {
                const tableName = table.replace('raw_data.', '');
                html += `<div class="exp-view-ds-join-row">
                    <span class="key">${primaryTable}.${configItem.join_key}</span>
                    <i class="fas fa-arrows-alt-h" style="color:#9ca3af;font-size:10px;"></i>
                    <span class="key">${tableName}.${configItem.secondary_column}</span>
                    <span class="badge">${configItem.join_type || 'left'}</span>
                </div>`;
            }
            html += `</div>`;
        }
        html += `</div>`;

        // Filters Applied section
        html += `<div class="exp-view-ds-section">
            <div class="exp-view-ds-title"><i class="fas fa-filter"></i>Filters Applied</div>`;

        let hasFilters = false;

        // Date filter
        if (filtersApplied.dates?.type === 'rolling') {
            hasFilters = true;
            html += `<div class="exp-view-ds-filter date">
                <div class="exp-view-ds-filter-title"><i class="fas fa-calendar-alt"></i>Date Filter</div>
                <div class="exp-view-ds-filter-detail">Column: <strong>${filtersApplied.dates.column || 'N/A'}</strong></div>
                <div class="exp-view-ds-filter-detail">Range: Last ${filtersApplied.dates.days} days (rolling window)</div>
            </div>`;
        } else if (filtersApplied.dates?.type === 'fixed') {
            hasFilters = true;
            html += `<div class="exp-view-ds-filter date">
                <div class="exp-view-ds-filter-title"><i class="fas fa-calendar-alt"></i>Date Filter</div>
                <div class="exp-view-ds-filter-detail">Column: <strong>${filtersApplied.dates.column || 'N/A'}</strong></div>
                <div class="exp-view-ds-filter-detail">Start: ${filtersApplied.dates.start_date}</div>
            </div>`;
        }

        // Customer filters
        if (filtersApplied.customers?.type === 'multiple' && filtersApplied.customers.filters?.length > 0) {
            hasFilters = true;
            const count = filtersApplied.customers.count || filtersApplied.customers.filters.length;
            let items = filtersApplied.customers.filters.map(f => {
                if (f.type === 'top_revenue') {
                    return `<div class="exp-view-ds-filter-detail">• Top <strong>${f.percent}%</strong> customers by revenue</div>
                        <div class="exp-view-ds-filter-detail" style="margin-left:10px;font-size:10px;">Customer: ${f.customer_column || 'N/A'}, Revenue: ${f.revenue_column || 'N/A'}</div>`;
                }
                if (f.type === 'category') return `<div class="exp-view-ds-filter-detail">• ${f.column}: ${f.values?.slice(0,3).join(', ')}${f.values?.length > 3 ? '...' : ''}</div>`;
                return `<div class="exp-view-ds-filter-detail">• ${f.type}</div>`;
            }).join('');
            html += `<div class="exp-view-ds-filter customer">
                <div class="exp-view-ds-filter-title"><i class="fas fa-users"></i>Customer Filters (${count})</div>
                ${items}
            </div>`;
        }

        // Product filters
        if (filtersApplied.products?.type === 'multiple' && filtersApplied.products.filters?.length > 0) {
            hasFilters = true;
            const count = filtersApplied.products.count || filtersApplied.products.filters.length;
            let items = filtersApplied.products.filters.map(f => {
                if (f.type === 'top_revenue') {
                    return `<div class="exp-view-ds-filter-detail">• Top <strong>${f.percent}%</strong> products by revenue</div>
                        <div class="exp-view-ds-filter-detail" style="margin-left:10px;font-size:10px;">Product: ${f.product_column || 'N/A'}, Revenue: ${f.revenue_column || 'N/A'}</div>`;
                }
                if (f.type === 'category') return `<div class="exp-view-ds-filter-detail">• ${f.column}: ${f.values?.slice(0,3).join(', ')}${f.values?.length > 3 ? '...' : ''}</div>`;
                return `<div class="exp-view-ds-filter-detail">• ${f.type}</div>`;
            }).join('');
            html += `<div class="exp-view-ds-filter product">
                <div class="exp-view-ds-filter-title"><i class="fas fa-box"></i>Product Filters (${count})</div>
                ${items}
            </div>`;
        }

        if (!hasFilters) {
            html += `<div class="exp-view-ds-no-filters">No filters applied - using all data</div>`;
        }

        html += `</div>`;

        container.innerHTML = html;
    }

    // =============================================================================
    // FEATURES CONFIG VISUALIZATION
    // =============================================================================

    function loadFeaturesConfig(featureConfigId) {
        const container = document.getElementById('expViewFeaturesConfigContent');
        container.innerHTML = '<div class="exp-view-loading"><i class="fas fa-spinner fa-spin"></i> Loading...</div>';

        const url = buildUrl(config.endpoints.featureConfig, { id: featureConfigId });

        fetch(url, {
            headers: { 'X-CSRFToken': getCookie('csrftoken') }
        })
        .then(response => response.json())
        .then(data => {
            if (!data.success) {
                container.innerHTML = '<div class="exp-view-no-filters">Failed to load features config</div>';
                return;
            }
            renderFeaturesConfig(data.data);
        })
        .catch(error => {
            console.error('Error loading features config:', error);
            container.innerHTML = '<div class="exp-view-no-filters">Failed to load features config</div>';
        });
    }

    function renderFeaturesConfig(configData) {
        const container = document.getElementById('expViewFeaturesConfigContent');

        // Calculate tensor breakdowns
        const buyerResult = calculateTensorBreakdown(
            configData.buyer_model_features || [],
            configData.buyer_model_crosses || []
        );
        const productResult = calculateTensorBreakdown(
            configData.product_model_features || [],
            configData.product_model_crosses || []
        );

        const maxTotal = Math.max(buyerResult.total || 0, productResult.total || 0);

        // Build target column section (for ranking models)
        let targetColumnHtml = '';
        if (configData.target_column && configData.config_type === 'ranking') {
            const tc = configData.target_column;
            const tcName = tc.display_name || tc.column || '-';
            const tcType = tc.bq_type || 'FLOAT';
            const transforms = tc.transforms || {};

            let transformsHtml = '';
            if (transforms.log_transform && transforms.log_transform.enabled) {
                transformsHtml += '<span class="target-transform-tag"><i class="fas fa-chart-line"></i> Log transform</span>';
            }
            if (transforms.clip_outliers && transforms.clip_outliers.enabled) {
                const lower = transforms.clip_outliers.lower?.enabled ? transforms.clip_outliers.lower.percentile : null;
                const upper = transforms.clip_outliers.upper?.enabled ? transforms.clip_outliers.upper.percentile : null;
                let clipText = 'Clip';
                if (lower && upper) {
                    clipText = `Clip ${lower}%-${upper}%`;
                } else if (lower) {
                    clipText = `Clip lower ${lower}%`;
                } else if (upper) {
                    clipText = `Clip upper ${upper}%`;
                }
                transformsHtml += `<span class="target-transform-tag"><i class="fas fa-cut"></i> ${clipText}</span>`;
            }

            targetColumnHtml = `
                <div class="target-column-view-card">
                    <div class="target-column-view-header">
                        <i class="fas fa-bullseye"></i>
                        <span>Target Column</span>
                        <span class="target-column-view-badge">For Ranking</span>
                    </div>
                    <div class="target-column-view-content">
                        <span class="target-column-view-name">${tcName}</span>
                        <span class="target-column-view-type">${tcType}</span>
                    </div>
                    ${transformsHtml ? `<div class="target-column-view-transforms">${transformsHtml}</div>` : ''}
                </div>
            `;
        }

        // Build HTML
        let html = targetColumnHtml + '<div class="exp-view-features-grid">';

        // Buyer Tensor Panel
        html += `
            <div class="exp-view-tensor-panel buyer">
                <div class="exp-view-tensor-header">
                    <span class="exp-view-tensor-title buyer">Buyer Tensor</span>
                    <span class="exp-view-tensor-total buyer">${buyerResult.total}D</span>
                </div>
                <div id="expViewBuyerBar" class="exp-view-tensor-bar"></div>
                <div class="exp-view-tensor-features">
                    ${buyerResult.breakdown.map(item => `
                        <div class="exp-view-tensor-feature-row">
                            <span class="exp-view-tensor-feature-name buyer ${item.is_cross ? 'cross' : ''}">${item.name}</span>
                            <span class="exp-view-tensor-feature-dim buyer">${item.dim}D</span>
                        </div>
                    `).join('')}
                </div>
            </div>`;

        // Product Tensor Panel
        html += `
            <div class="exp-view-tensor-panel product">
                <div class="exp-view-tensor-header">
                    <span class="exp-view-tensor-title product">Product Tensor</span>
                    <span class="exp-view-tensor-total product">${productResult.total}D</span>
                </div>
                <div id="expViewProductBar" class="exp-view-tensor-bar"></div>
                <div class="exp-view-tensor-features">
                    ${productResult.breakdown.map(item => `
                        <div class="exp-view-tensor-feature-row">
                            <span class="exp-view-tensor-feature-name product ${item.is_cross ? 'cross' : ''}">${item.name}</span>
                            <span class="exp-view-tensor-feature-dim product">${item.dim}D</span>
                        </div>
                    `).join('')}
                </div>
            </div>`;

        html += '</div>';
        container.innerHTML = html;

        // Render tensor bars after DOM update
        setTimeout(() => {
            renderTensorBar('buyer', buyerResult.total, buyerResult.breakdown, maxTotal);
            renderTensorBar('product', productResult.total, productResult.breakdown, maxTotal);
        }, 0);
    }

    function calculateTensorBreakdown(features, crosses) {
        const breakdown = [];
        let total = 0;

        // Process features
        (features || []).forEach(feature => {
            const dim = getFeatureDimension(feature);
            if (dim > 0) {
                breakdown.push({ name: feature.display_name || feature.column, dim: dim });
                total += dim;
            }
        });

        // Process cross features
        (crosses || []).forEach(cross => {
            const dim = cross.embedding_dim || 16;
            const featureNames = getCrossFeatureNames(cross);
            const name = featureNames.join(' × ');
            breakdown.push({ name: name, dim: dim, is_cross: true });
            total += dim;
        });

        return { total, breakdown };
    }

    function getFeatureDimension(feature) {
        const dataType = feature.data_type || getDataTypeFromBqType(feature.bq_type);
        const transforms = feature.transforms || {};
        let totalDim = 0;

        if (dataType === 'numeric') {
            if (transforms.normalize?.enabled) totalDim += 1;
            if (transforms.bucketize?.enabled) totalDim += (transforms.bucketize.embedding_dim || 32);
        } else if (dataType === 'text') {
            if (transforms.embedding?.enabled) totalDim += (transforms.embedding.embedding_dim || 32);
        } else if (dataType === 'temporal') {
            if (transforms.normalize?.enabled) totalDim += 1;
            if (transforms.cyclical?.enabled) {
                const c = transforms.cyclical;
                if (c.yearly || c.annual) totalDim += 2;
                if (c.quarterly) totalDim += 2;
                if (c.monthly) totalDim += 2;
                if (c.weekly) totalDim += 2;
                if (c.daily) totalDim += 2;
            }
            if (transforms.bucketize?.enabled) totalDim += (transforms.bucketize.embedding_dim || 32);
        }

        return totalDim;
    }

    function getDataTypeFromBqType(bqType) {
        const type = (bqType || 'STRING').toUpperCase();
        if (['INTEGER', 'INT64', 'FLOAT', 'FLOAT64', 'NUMERIC', 'BIGNUMERIC'].includes(type)) {
            return 'numeric';
        } else if (['TIMESTAMP', 'DATETIME', 'DATE', 'TIME'].includes(type)) {
            return 'temporal';
        }
        return 'text';
    }

    function getCrossFeatureNames(cross) {
        if (!cross.features || cross.features.length === 0) return [];
        if (typeof cross.features[0] === 'string') return cross.features;
        return cross.features.map(f => f.display_name || f.column);
    }

    function renderTensorBar(model, total, breakdown, maxTotal) {
        const barId = model === 'buyer' ? 'expViewBuyerBar' : 'expViewProductBar';
        const bar = document.getElementById(barId);
        if (!bar) return;

        bar.innerHTML = '';
        if (!breakdown || breakdown.length === 0) return;

        if (maxTotal && maxTotal > 0) {
            bar.style.width = `${(total / maxTotal) * 100}%`;
        }

        const colors = model === 'buyer'
            ? ['#3b82f6', '#60a5fa', '#93c5fd', '#bfdbfe', '#dbeafe']
            : ['#10b981', '#34d399', '#6ee7b7', '#a7f3d0', '#d1fae5'];

        breakdown.forEach((item, idx) => {
            const pct = (item.dim / total) * 100;
            const color = colors[idx % colors.length];

            const segment = document.createElement('div');
            segment.className = 'exp-view-tensor-segment';
            segment.style.width = `${pct}%`;
            segment.style.backgroundColor = color;
            segment.title = `${item.name}: ${item.dim}D`;
            if (pct > 10) {
                segment.textContent = item.dim;
            }
            bar.appendChild(segment);
        });
    }

    // =============================================================================
    // MODEL CONFIG VISUALIZATION
    // =============================================================================

    function loadModelConfig(modelConfigId) {
        const container = document.getElementById('expViewModelConfigContent');
        container.innerHTML = '<div class="exp-view-loading"><i class="fas fa-spinner fa-spin"></i> Loading...</div>';

        const url = buildUrl(config.endpoints.modelConfig, { id: modelConfigId });

        fetch(url, {
            headers: { 'X-CSRFToken': getCookie('csrftoken') }
        })
        .then(response => response.json())
        .then(data => {
            if (!data.success) {
                container.innerHTML = '<div class="exp-view-no-filters">Failed to load model config</div>';
                return;
            }
            renderModelConfig(data.data);
        })
        .catch(error => {
            console.error('Error loading model config:', error);
            container.innerHTML = '<div class="exp-view-no-filters">Failed to load model config</div>';
        });
    }

    function renderModelConfig(mc) {
        const container = document.getElementById('expViewModelConfigContent');

        const modelTypeBadges = {
            'retrieval': '<i class="fas fa-search"></i> Retrieval',
            'ranking': '<i class="fas fa-sort-amount-down"></i> Ranking',
            'multitask': '<i class="fas fa-layer-group"></i> Retrieval / Ranking'
        };
        const modelTypeBadgeContent = modelTypeBadges[mc.model_type] || modelTypeBadges['retrieval'];

        const buyerLayers = mc.buyer_tower_layers || [];
        const productLayers = mc.product_tower_layers || [];
        const buyerParams = calculateTowerParams(buyerLayers);
        const productParams = calculateTowerParams(productLayers);

        let html = `
            <span class="exp-view-model-type-badge ${mc.model_type}">${modelTypeBadgeContent}</span>

            <div class="exp-view-tower-section-title">Tower Architecture</div>
            <div class="exp-view-towers-grid">
                <div class="exp-view-tower-column">
                    <div class="exp-view-tower-header">
                        <span class="exp-view-tower-label">BUYER TOWER</span>
                    </div>
                    <div class="exp-view-tower-stack buyer">
                        ${renderTowerLayers(buyerLayers)}
                    </div>
                    <div class="exp-view-tower-params buyer">
                        <div class="exp-view-tower-params-row"><span>Total params:</span><span>${buyerParams.toLocaleString()}</span></div>
                        <div class="exp-view-tower-params-row"><span>Trainable params:</span><span>${buyerParams.toLocaleString()}</span></div>
                        <div class="exp-view-tower-params-row"><span>Non-trainable params:</span><span>0</span></div>
                    </div>
                </div>
                <div class="exp-view-tower-column">
                    <div class="exp-view-tower-header">
                        <span class="exp-view-tower-label">PRODUCT TOWER</span>
                    </div>
                    <div class="exp-view-tower-stack product">
                        ${renderTowerLayers(productLayers)}
                    </div>
                    <div class="exp-view-tower-params product">
                        <div class="exp-view-tower-params-row"><span>Total params:</span><span>${productParams.toLocaleString()}</span></div>
                        <div class="exp-view-tower-params-row"><span>Trainable params:</span><span>${productParams.toLocaleString()}</span></div>
                        <div class="exp-view-tower-params-row"><span>Non-trainable params:</span><span>0</span></div>
                    </div>
                </div>
            </div>`;

        // Rating Head section (for ranking and multitask models)
        if (['ranking', 'multitask'].includes(mc.model_type)) {
            const ratingHeadLayers = mc.rating_head_layers || [];
            const ratingHeadParams = calculateTowerParams(ratingHeadLayers, (mc.output_embedding_dim || 32) * 2);

            html += `
            <div class="exp-view-rating-head-section">
                <div class="exp-view-rating-head-title">Rating Head</div>
                <div class="exp-view-rating-head-label">RANKING TOWER</div>
                <div class="exp-view-rating-tower-wrapper">
                    <div class="exp-view-tower-stack ranking">
                        ${renderTowerLayers(ratingHeadLayers)}
                    </div>
                    <div class="exp-view-tower-params ranking">
                        <div class="exp-view-tower-params-row"><span>Total params:</span><span>${ratingHeadParams.toLocaleString()}</span></div>
                        <div class="exp-view-tower-params-row"><span>Trainable params:</span><span>${ratingHeadParams.toLocaleString()}</span></div>
                        <div class="exp-view-tower-params-row"><span>Non-trainable params:</span><span>0</span></div>
                    </div>
                </div>
            </div>`;
        }

        container.innerHTML = html;

        // Update Optimizer in Training Parameters section
        const optimizerEl = document.getElementById('expViewOptimizerValue');
        if (optimizerEl) {
            optimizerEl.textContent = mc.optimizer_display || mc.optimizer || 'Adagrad';
        }
    }

    function renderTowerLayers(layers) {
        if (!layers || layers.length === 0) {
            return '<div class="text-xs text-gray-400 italic p-2">No layers</div>';
        }

        return layers.map((layer, idx) => {
            const isOutput = idx === layers.length - 1;
            let badge = '';
            let params = '';

            if (layer.type === 'dense') {
                badge = '<span class="exp-view-layer-badge dense">DENSE</span>';
                params = `${layer.units} units`;
                if (layer.activation) params += `, ${layer.activation}`;
                if (layer.l2_regularization) params += `, L2=${layer.l2_regularization}`;
                else if (layer.l2_reg) params += `, L2=${layer.l2_reg}`;
            } else if (layer.type === 'dropout') {
                badge = '<span class="exp-view-layer-badge dropout">DROPOUT</span>';
                params = `rate: ${layer.rate}`;
            } else if (layer.type === 'batch_norm') {
                badge = '<span class="exp-view-layer-badge batch_norm">BATCHNORM</span>';
                params = '';
            } else if (layer.type === 'layer_norm') {
                badge = '<span class="exp-view-layer-badge layer_norm">LAYERNORM</span>';
                params = layer.epsilon ? `ε: ${layer.epsilon}` : '';
            }

            return `
                <div class="exp-view-layer-item${isOutput ? ' output-layer' : ''}">
                    <span class="exp-view-layer-drag"><i class="fas fa-grip-vertical"></i></span>
                    ${badge}
                    <span class="exp-view-layer-params">${params}</span>
                </div>
            `;
        }).join('');
    }

    function calculateTowerParams(layers, inputDim = 128) {
        if (!layers || layers.length === 0) return 0;

        let total = 0;
        let prevDim = inputDim;

        layers.forEach(layer => {
            if (layer.type === 'dense') {
                total += prevDim * layer.units + layer.units;
                prevDim = layer.units;
            }
        });

        return total;
    }

    // =============================================================================
    // SAMPLING & TRAINING PARAMS CHIPS
    // =============================================================================

    function renderSamplingChips(exp) {
        const container = document.getElementById('expViewSamplingChips');
        if (!container) return;

        const splitLabels = {
            'random': 'Random 80/15/5',
            'time_holdout': 'Time Holdout',
            'strict_time': 'Strict Temporal'
        };

        let html = `
            <div class="exp-view-param-chip">
                <span class="exp-view-param-chip-label">Sample:</span>
                <span class="exp-view-param-chip-value">${exp.data_sample_percent || 100}%</span>
            </div>
            <div class="exp-view-param-chip">
                <span class="exp-view-param-chip-label">Split Strategy:</span>
                <span class="exp-view-param-chip-value">${splitLabels[exp.split_strategy] || exp.split_strategy}</span>
            </div>
        `;

        if (exp.split_strategy !== 'random' && exp.date_column) {
            html += `
            <div class="exp-view-param-chip">
                <span class="exp-view-param-chip-label">Date Column:</span>
                <span class="exp-view-param-chip-value">${exp.date_column}</span>
            </div>
            `;
        }

        if (exp.split_strategy === 'time_holdout') {
            html += `
            <div class="exp-view-param-chip">
                <span class="exp-view-param-chip-label">Test (last N days):</span>
                <span class="exp-view-param-chip-value">${exp.holdout_days || 1} days</span>
            </div>
            `;
        }

        container.innerHTML = html;
    }

    function renderTrainingParamsChips(exp) {
        const container = document.getElementById('expViewTrainingParamsChips');
        if (!container) return;

        const hardwareSpecs = {
            'n1-standard-4': { name: 'Small', cpu: '4 vCPUs', memory: '15 GB' },
            'n1-standard-8': { name: 'Medium', cpu: '8 vCPUs', memory: '30 GB' },
            'n1-standard-16': { name: 'Large', cpu: '16 vCPUs', memory: '60 GB' },
            'n1-highmem-4': { name: 'High Memory', cpu: '4 vCPUs', memory: '26 GB' },
            'n1-highmem-8': { name: 'High Memory', cpu: '8 vCPUs', memory: '52 GB' }
        };

        const machineType = exp.machine_type || 'n1-standard-4';
        const hwSpec = hardwareSpecs[machineType] || { name: 'Custom', cpu: '-', memory: '-' };
        const hardwareDisplay = `${hwSpec.cpu}, ${hwSpec.memory}`;

        let html = `
            <div class="exp-view-param-chip" id="expViewOptimizerChip">
                <span class="exp-view-param-chip-label">Optimizer:</span>
                <span class="exp-view-param-chip-value" id="expViewOptimizerValue">-</span>
            </div>
            <div class="exp-view-param-chip">
                <span class="exp-view-param-chip-label">Epochs:</span>
                <span class="exp-view-param-chip-value">${exp.epochs || '-'}</span>
            </div>
            <div class="exp-view-param-chip">
                <span class="exp-view-param-chip-label">Batch Size:</span>
                <span class="exp-view-param-chip-value">${exp.batch_size?.toLocaleString() || '-'}</span>
            </div>
            <div class="exp-view-param-chip">
                <span class="exp-view-param-chip-label">Learning Rate:</span>
                <span class="exp-view-param-chip-value">${exp.learning_rate || '-'}</span>
            </div>
            <div class="exp-view-param-chip">
                <span class="exp-view-param-chip-label">Hardware:</span>
                <span class="exp-view-param-chip-value">${hardwareDisplay}</span>
            </div>
        `;

        container.innerHTML = html;
    }

    // =============================================================================
    // METRICS SUMMARY
    // =============================================================================

    function renderMetricsSummary(metrics, useTestPrefix = false, configType = 'retrieval') {
        const container = document.getElementById('expViewMetricsSummary');
        if (!container) return;

        const formatRecall = v => v != null ? (v * 100).toFixed(2) + '%' : 'N/A';
        const formatRMSE = v => v != null ? v.toFixed(4) : 'N/A';

        let items;
        if (configType === 'multitask') {
            container.classList.remove('exp-view-metrics-row');

            const prefix = useTestPrefix ? 'test_' : '';
            const rmse = metrics['rmse'] ?? metrics['final_val_rmse'] ?? metrics['final_rmse'];
            const mae = metrics['mae'] ?? metrics['final_val_mae'] ?? metrics['final_mae'];
            const testRmse = metrics['test_rmse'];
            const testMae = metrics['test_mae'];

            const retrievalItems = [
                { label: 'Recall@5', value: metrics[prefix + 'recall_at_5'], format: formatRecall },
                { label: 'Recall@10', value: metrics[prefix + 'recall_at_10'], format: formatRecall },
                { label: 'Recall@50', value: metrics[prefix + 'recall_at_50'], format: formatRecall },
                { label: 'Recall@100', value: metrics[prefix + 'recall_at_100'], format: formatRecall }
            ];
            const rankingItems = [
                { label: 'RMSE', value: rmse, format: formatRMSE },
                { label: 'Test RMSE', value: testRmse, format: formatRMSE },
                { label: 'MAE', value: mae, format: formatRMSE },
                { label: 'Test MAE', value: testMae, format: formatRMSE }
            ];

            container.innerHTML = `
                <div class="exp-view-metrics-multitask">
                    <div class="exp-view-metrics-section">
                        <div class="exp-view-metrics-section-header">
                            <i class="fas fa-search"></i> Retrieval Metrics
                        </div>
                        <div class="exp-view-metrics-grid">
                            ${retrievalItems.map(item => `
                                <div class="exp-view-metric-card">
                                    <div class="exp-view-metric-card-label">${item.label}</div>
                                    <div class="exp-view-metric-card-value">${item.format(item.value)}</div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                    <div class="exp-view-metrics-section">
                        <div class="exp-view-metrics-section-header">
                            <i class="fas fa-star"></i> Ranking Metrics
                        </div>
                        <div class="exp-view-metrics-grid">
                            ${rankingItems.map(item => `
                                <div class="exp-view-metric-card">
                                    <div class="exp-view-metric-card-label">${item.label}</div>
                                    <div class="exp-view-metric-card-value">${item.format(item.value)}</div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            `;
            return;
        } else if (configType === 'ranking') {
            container.classList.add('exp-view-metrics-row');

            const rmse = metrics['rmse'] ?? metrics['final_val_rmse'] ?? metrics['final_rmse'];
            const mae = metrics['mae'] ?? metrics['final_val_mae'] ?? metrics['final_mae'];
            const testRmse = metrics['test_rmse'];
            const testMae = metrics['test_mae'];

            items = [
                { label: 'RMSE', value: rmse, format: formatRMSE },
                { label: 'Test RMSE', value: testRmse, format: formatRMSE },
                { label: 'MAE', value: mae, format: formatRMSE },
                { label: 'Test MAE', value: testMae, format: formatRMSE }
            ];
        } else {
            container.classList.add('exp-view-metrics-row');

            const prefix = useTestPrefix ? 'test_' : '';
            items = [
                { label: 'Recall@5', value: metrics[prefix + 'recall_at_5'], format: formatRecall },
                { label: 'Recall@10', value: metrics[prefix + 'recall_at_10'], format: formatRecall },
                { label: 'Recall@50', value: metrics[prefix + 'recall_at_50'], format: formatRecall },
                { label: 'Recall@100', value: metrics[prefix + 'recall_at_100'], format: formatRecall }
            ];
        }

        container.innerHTML = items.map(item => `
            <div class="exp-view-metric-card">
                <div class="exp-view-metric-card-label">${item.label}</div>
                <div class="exp-view-metric-card-value">${item.format(item.value)}</div>
            </div>
        `).join('');
    }

    // =============================================================================
    // VOCABULARY ROWS
    // =============================================================================

    function renderVocabRows(vocabStats) {
        const container = document.getElementById('expViewVocabRows');
        if (!container) return;

        container.innerHTML = Object.entries(vocabStats).map(([name, size]) => `
            <div class="exp-view-row">
                <span class="exp-view-row-label">${name}</span>
                <span class="exp-view-row-value">${typeof size === 'number' ? size.toLocaleString() : size}</span>
            </div>
        `).join('');
    }

    // =============================================================================
    // DATA INSIGHTS (LAZY LOAD)
    // =============================================================================

    async function preloadDataInsights() {
        // Support both experiment and training run modes
        const id = state.mode === 'training_run' ? state.runId : state.expId;
        if (!id) return;
        if (state.dataCache.statistics !== null || state.dataCache._loadingInsights) return;

        state.dataCache._loadingInsights = true;
        const entityType = state.mode === 'training_run' ? 'training run' : 'experiment';
        console.log(`[DataInsights] Preload STARTED for ${entityType}`, id);
        const startTime = performance.now();

        try {
            // Use appropriate endpoints based on mode
            const statsEndpoint = state.mode === 'training_run'
                ? config.endpoints.trainingRunStatistics
                : config.endpoints.statistics;
            const schemaEndpoint = state.mode === 'training_run'
                ? config.endpoints.trainingRunSchema
                : config.endpoints.schema;

            const statsUrl = buildUrl(statsEndpoint, { id });
            const schemaUrl = buildUrl(schemaEndpoint, { id });

            const [statsRes, schemaRes] = await Promise.all([
                fetch(statsUrl),
                fetch(schemaUrl)
            ]);

            const statsData = await statsRes.json();
            const schemaData = await schemaRes.json();

            const elapsed = ((performance.now() - startTime) / 1000).toFixed(1);
            console.log(`[DataInsights] Preload COMPLETED in ${elapsed}s - data cached`);

            // Cache data if the entity is still the same
            const currentId = state.mode === 'training_run' ? state.runId : state.expId;
            if (currentId === id) {
                state.dataCache.statistics = statsData.statistics;
                state.dataCache.schema = schemaData.schema;
                state.dataCache._statsData = statsData;
                state.dataCache._schemaData = schemaData;
            }
        } catch (error) {
            console.log('[DataInsights] Preload FAILED:', error.message);
        } finally {
            state.dataCache._loadingInsights = false;
        }
    }

    async function loadDataInsights() {
        // Support both experiment and training run modes
        const id = state.mode === 'training_run' ? state.runId : state.expId;
        if (!id) return;

        const loadingEl = document.getElementById('expViewDataLoading');
        const contentEl = document.getElementById('expViewDataContent');
        const errorEl = document.getElementById('expViewDataError');

        // Check if data was preloaded
        if (state.dataCache.statistics !== null && state.dataCache._statsData) {
            console.log('[DataInsights] Using CACHED data (instant load)');
            const statsData = state.dataCache._statsData;
            const schemaData = state.dataCache._schemaData;

            const statsAvailable = statsData.success && statsData.statistics?.available;
            const schemaAvailable = schemaData.success && schemaData.schema?.available;

            loadingEl.classList.add('hidden');

            if (!statsAvailable && !schemaAvailable) {
                contentEl.classList.add('hidden');
                errorEl.classList.remove('hidden');
                document.getElementById('expViewDataErrorMessage').textContent =
                    statsData.statistics?.message || schemaData.schema?.message || 'Data insights not available';
                return;
            }

            if (statsAvailable) renderStatistics(statsData.statistics);
            else document.getElementById('expViewStatsContent').innerHTML = '<p class="text-sm text-gray-500">Statistics not available</p>';

            if (schemaAvailable) renderSchema(schemaData.schema);
            else document.getElementById('expViewSchemaContent').innerHTML = '<p class="text-sm text-gray-500">Schema not available</p>';

            errorEl.classList.add('hidden');
            contentEl.classList.remove('hidden');
            return;
        }

        // Wait if preload is in progress
        if (state.dataCache._loadingInsights) {
            console.log('[DataInsights] Waiting for preload to complete...');
            loadingEl.classList.remove('hidden');
            contentEl.classList.add('hidden');
            errorEl.classList.add('hidden');

            let waitTime = 0;
            const maxWait = 90000;
            const checkPreload = setInterval(() => {
                waitTime += 100;
                if (!state.dataCache._loadingInsights) {
                    clearInterval(checkPreload);
                    console.log(`[DataInsights] Preload finished after ${(waitTime/1000).toFixed(1)}s wait`);
                    loadDataInsights();
                } else if (waitTime >= maxWait) {
                    clearInterval(checkPreload);
                    console.log('[DataInsights] Preload timeout - falling back to direct fetch');
                    state.dataCache._loadingInsights = false;
                    loadDataInsights();
                }
            }, 100);
            return;
        }

        loadingEl.classList.remove('hidden');
        contentEl.classList.add('hidden');
        errorEl.classList.add('hidden');

        try {
            // Use appropriate endpoints based on mode
            const statsEndpoint = state.mode === 'training_run'
                ? config.endpoints.trainingRunStatistics
                : config.endpoints.statistics;
            const schemaEndpoint = state.mode === 'training_run'
                ? config.endpoints.trainingRunSchema
                : config.endpoints.schema;

            const statsUrl = buildUrl(statsEndpoint, { id });
            const schemaUrl = buildUrl(schemaEndpoint, { id });

            const [statsRes, schemaRes] = await Promise.all([
                fetch(statsUrl),
                fetch(schemaUrl)
            ]);

            const statsData = await statsRes.json();
            const schemaData = await schemaRes.json();

            state.dataCache.statistics = statsData.statistics;
            state.dataCache.schema = schemaData.schema;
            state.dataCache._statsData = statsData;
            state.dataCache._schemaData = schemaData;

            const statsAvailable = statsData.success && statsData.statistics?.available;
            const schemaAvailable = schemaData.success && schemaData.schema?.available;

            if (!statsAvailable && !schemaAvailable) {
                loadingEl.classList.add('hidden');
                errorEl.classList.remove('hidden');
                document.getElementById('expViewDataErrorMessage').textContent =
                    statsData.statistics?.message || schemaData.schema?.message || 'Data insights not available';
                return;
            }

            if (statsAvailable) {
                renderStatistics(statsData.statistics);
            } else {
                document.getElementById('expViewStatsContent').innerHTML =
                    '<p class="text-sm text-gray-500">Statistics not available</p>';
            }

            if (schemaAvailable) {
                renderSchema(schemaData.schema);
            } else {
                document.getElementById('expViewSchemaContent').innerHTML =
                    '<p class="text-sm text-gray-500">Schema not available</p>';
            }

            loadingEl.classList.add('hidden');
            contentEl.classList.remove('hidden');

        } catch (error) {
            console.error('Error loading data insights:', error);
            loadingEl.classList.add('hidden');
            errorEl.classList.remove('hidden');
            document.getElementById('expViewDataErrorMessage').textContent = 'Failed to load data insights';
        }
    }

    function renderStatistics(stats) {
        const container = document.getElementById('expViewStatsContent');
        const numericSection = document.getElementById('expViewNumericSection');
        const categoricalSection = document.getElementById('expViewCategoricalSection');
        const numericContent = document.getElementById('expViewNumericContent');
        const categoricalContent = document.getElementById('expViewCategoricalContent');
        const tfdvBtn = document.getElementById('expViewTfdvBtn');

        const numNumeric = stats.num_numeric_features || 0;
        const numCategorical = stats.num_categorical_features || 0;
        const avgMissing = stats.avg_missing_pct ?? stats.avg_missing_ratio ?? 0;

        let html = `
            <div class="exp-view-stats-summary">
                <div class="exp-view-stat-box">
                    <div class="exp-view-stat-box-value">${stats.num_examples?.toLocaleString() || '-'}</div>
                    <div class="exp-view-stat-box-label">Examples</div>
                </div>
                <div class="exp-view-stat-box">
                    <div class="exp-view-stat-box-value">${stats.num_features || '-'}</div>
                    <div class="exp-view-stat-box-label">Features</div>
                </div>
                <div class="exp-view-stat-box">
                    <div class="exp-view-stat-box-value">${numNumeric} / ${numCategorical}</div>
                    <div class="exp-view-stat-box-label">Numeric / Categorical</div>
                </div>
                <div class="exp-view-stat-box">
                    <div class="exp-view-stat-box-value">${avgMissing?.toFixed(1) || '0'}%</div>
                    <div class="exp-view-stat-box-label">Avg Missing</div>
                </div>
            </div>
        `;
        container.innerHTML = html;

        if (stats.available && tfdvBtn) {
            // Use appropriate TFDV report URL based on mode
            const tfdvEndpoint = state.mode === 'training_run'
                ? config.endpoints.trainingRunTfdvReport
                : config.endpoints.tfdvReport;
            const tfdvId = state.mode === 'training_run' ? state.runId : state.expId;
            tfdvBtn.href = buildUrl(tfdvEndpoint, { id: tfdvId });
            tfdvBtn.classList.remove('hidden');
        }

        if (stats.numeric_features?.length > 0) {
            numericSection.classList.remove('hidden');
            document.getElementById('expViewNumericCount').textContent = `(${stats.numeric_features.length})`;
            numericContent.innerHTML = renderNumericFeaturesTable(stats.numeric_features);
        } else {
            numericSection.classList.add('hidden');
        }

        if (stats.categorical_features?.length > 0) {
            categoricalSection.classList.remove('hidden');
            document.getElementById('expViewCategoricalCount').textContent = `(${stats.categorical_features.length})`;
            categoricalContent.innerHTML = renderCategoricalFeaturesTable(stats.categorical_features);
        } else {
            categoricalSection.classList.add('hidden');
        }

        if (!stats.numeric_features && !stats.categorical_features && stats.features?.length > 0) {
            numericSection.classList.remove('hidden');
            document.getElementById('expViewNumericCount').textContent = '';
            numericContent.innerHTML = renderLegacyFeaturesTable(stats.features, stats.truncated, stats.total_features);
            categoricalSection.classList.add('hidden');
        }
    }

    function renderNumericFeaturesTable(features) {
        return `
            <div class="tfdv-table-container">
                <table class="tfdv-features-table">
                    <thead>
                        <tr>
                            <th>Feature</th>
                            <th>Count</th>
                            <th>Missing</th>
                            <th>Mean</th>
                            <th>Std Dev</th>
                            <th>Zeros</th>
                            <th>Min</th>
                            <th>Median</th>
                            <th>Max</th>
                            <th>Distribution</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${features.slice(0, 30).map(f => {
                            const ns = f.numeric_stats || {};
                            return `
                            <tr>
                                <td class="feature-name">${f.name}</td>
                                <td>${ns.count?.toLocaleString() || '-'}</td>
                                <td>${formatPercent(ns.missing_pct)}</td>
                                <td>${formatNumber(ns.mean)}</td>
                                <td>${formatNumber(ns.std_dev)}</td>
                                <td>${formatPercent(ns.zeros_pct)}</td>
                                <td>${formatNumber(ns.min_val)}</td>
                                <td>${formatNumber(ns.median)}</td>
                                <td>${formatNumber(ns.max_val)}</td>
                                <td>${renderMiniHistogram(ns.histogram)}</td>
                            </tr>
                        `}).join('')}
                    </tbody>
                </table>
            </div>
            ${features.length > 30 ? `<p class="text-xs text-gray-400 mt-2">Showing first 30 of ${features.length} numeric features</p>` : ''}
        `;
    }

    function renderCategoricalFeaturesTable(features) {
        return `
            <div class="tfdv-table-container">
                <table class="tfdv-features-table">
                    <thead>
                        <tr>
                            <th>Feature</th>
                            <th>Count</th>
                            <th>Missing</th>
                            <th>Unique</th>
                            <th>Top Values</th>
                            <th>Distribution</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${features.slice(0, 30).map(f => {
                            const cs = f.categorical_stats || {};
                            return `
                            <tr>
                                <td class="feature-name">${f.name}</td>
                                <td>${cs.count?.toLocaleString() || '-'}</td>
                                <td>${formatPercent(cs.missing_pct)}</td>
                                <td>${cs.unique?.toLocaleString() || '-'}</td>
                                <td class="top-values-cell">${renderTopValues(cs.top_values)}</td>
                                <td>${renderTopValuesChart(cs.top_values)}</td>
                            </tr>
                        `}).join('')}
                    </tbody>
                </table>
            </div>
            ${features.length > 30 ? `<p class="text-xs text-gray-400 mt-2">Showing first 30 of ${features.length} categorical features</p>` : ''}
        `;
    }

    function renderLegacyFeaturesTable(features, truncated, total) {
        return `
            <div class="tfdv-table-container">
                <table class="tfdv-features-table">
                    <thead>
                        <tr>
                            <th>Feature</th>
                            <th>Type</th>
                            <th>Unique</th>
                            <th>Missing</th>
                            <th>Min</th>
                            <th>Max</th>
                            <th>Mean</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${features.slice(0, 30).map(f => `
                            <tr>
                                <td class="feature-name">${f.name}</td>
                                <td><span class="type-tag ${f.type?.toLowerCase() || 'unknown'}">${f.type || 'UNKNOWN'}</span></td>
                                <td>${f.num_unique?.toLocaleString() || '-'}</td>
                                <td>${formatPercent(f.missing_pct)}</td>
                                <td>${formatNumber(f.min)}</td>
                                <td>${formatNumber(f.max)}</td>
                                <td>${formatNumber(f.mean)}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
            ${truncated ? `<p class="text-xs text-gray-400 mt-2">Showing first 30 of ${total} features</p>` : ''}
        `;
    }

    function renderMiniHistogram(histogram) {
        if (!histogram || histogram.length === 0) return '<span class="no-data">-</span>';

        const maxCount = Math.max(...histogram.map(b => b.count || 0));
        if (maxCount === 0) return '<span class="no-data">-</span>';

        const bars = histogram.slice(0, 10).map(b => {
            const height = Math.max(2, Math.round((b.count / maxCount) * 24));
            return `<div class="mini-bar" style="height: ${height}px;" title="${b.count?.toLocaleString() || 0}"></div>`;
        }).join('');

        return `<div class="mini-histogram">${bars}</div>`;
    }

    function renderTopValues(topValues) {
        if (!topValues || topValues.length === 0) return '<span class="no-data">-</span>';

        const top3 = topValues.slice(0, 3).map(tv => {
            const val = tv.value?.length > 15 ? tv.value.substring(0, 15) + '...' : tv.value;
            return `<span class="top-value" title="${tv.value}: ${tv.frequency_pct?.toFixed(1) || 0}%">${val}</span>`;
        }).join(', ');

        return top3;
    }

    function renderTopValuesChart(topValues) {
        if (!topValues || topValues.length === 0) return '<span class="no-data">-</span>';

        const maxPct = Math.max(...topValues.map(tv => tv.frequency_pct || 0));
        if (maxPct === 0) return '<span class="no-data">-</span>';

        const bars = topValues.slice(0, 5).map(tv => {
            const width = Math.max(2, Math.round((tv.frequency_pct / maxPct) * 60));
            return `<div class="mini-hbar" style="width: ${width}px;" title="${tv.value}: ${tv.frequency_pct?.toFixed(1)}%"></div>`;
        }).join('');

        return `<div class="mini-hbar-chart">${bars}</div>`;
    }

    function renderSchema(schema) {
        const container = document.getElementById('expViewSchemaContent');

        if (!schema.features?.length) {
            container.innerHTML = '<p class="text-sm text-gray-500">No schema information available</p>';
            return;
        }

        container.innerHTML = `
            <table class="exp-view-features-table">
                <thead>
                    <tr>
                        <th>Feature</th>
                        <th>Type</th>
                        <th>Required</th>
                    </tr>
                </thead>
                <tbody>
                    ${schema.features.slice(0, 20).map(f => `
                        <tr>
                            <td>${f.name}</td>
                            <td>${f.feature_type || 'UNKNOWN'}</td>
                            <td>${f.presence === 'required' ? 'Yes' : 'No'}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
            ${schema.truncated ? `<p class="text-xs text-gray-400 mt-2">Showing first 20 of ${schema.total_features} features</p>` : ''}
        `;
    }

    // =============================================================================
    // TRAINING HISTORY (LAZY LOAD)
    // =============================================================================

    async function preloadTrainingHistory() {
        if (!state.expId || state.dataCache.trainingHistory) return;

        try {
            const url = buildUrl(config.endpoints.trainingHistory, { id: state.expId });
            const response = await fetch(url);
            const data = await response.json();

            if (data.success && data.training_history?.available) {
                state.dataCache.trainingHistory = data.training_history;

                if (data.training_history.final_metrics) {
                    const configType = window.currentViewExp?.feature_config_type || 'retrieval';
                    if (configType !== 'multitask') {
                        renderMetricsSummary(data.training_history.final_metrics, true, configType);
                    }
                }
            }
        } catch (error) {
            console.log('[TrainingHistory] Preload failed:', error.message);
        }
    }

    function renderCachedTrainingHistory() {
        const loadingEl = document.getElementById('expViewTrainingLoading');
        const placeholderEl = document.getElementById('expViewTrainingPlaceholder');
        const chartsEl = document.getElementById('expViewTrainingCharts');
        const messageEl = document.getElementById('expViewTrainingMessage');

        const history = state.dataCache.trainingHistory;

        loadingEl.classList.add('hidden');

        if (!history || !history.available) {
            messageEl.textContent = history?.message || 'Training data not available';
            placeholderEl.classList.remove('hidden');
            chartsEl.classList.add('hidden');
            return;
        }

        destroyCharts();
        renderTrainingCharts(history);
        placeholderEl.classList.add('hidden');
        chartsEl.classList.remove('hidden');

        console.log('[TrainingHistory] Rendered from cache (instant)');
    }

    async function loadTrainingHistory() {
        // Get the appropriate ID based on mode
        const id = state.mode === 'training_run' ? state.runId : state.expId;
        if (!id) return;

        const loadingEl = document.getElementById('expViewTrainingLoading');
        const placeholderEl = document.getElementById('expViewTrainingPlaceholder');
        const chartsEl = document.getElementById('expViewTrainingCharts');
        const messageEl = document.getElementById('expViewTrainingMessage');

        loadingEl.classList.remove('hidden');
        placeholderEl.classList.add('hidden');
        chartsEl.classList.add('hidden');

        destroyCharts();

        try {
            // Use appropriate endpoint based on mode
            const endpoint = state.mode === 'training_run'
                ? config.endpoints.trainingRunTrainingHistory
                : config.endpoints.trainingHistory;
            const url = buildUrl(endpoint, { id: id });
            const response = await fetch(url);
            const data = await response.json();

            loadingEl.classList.add('hidden');

            if (!data.success) {
                messageEl.textContent = data.error || 'Error loading training data';
                placeholderEl.classList.remove('hidden');
                return;
            }

            const history = data.training_history;
            state.dataCache.trainingHistory = history;

            if (!history.available) {
                messageEl.textContent = history.message || 'Training data not available';
                placeholderEl.classList.remove('hidden');
                return;
            }

            renderTrainingCharts(history);
            chartsEl.classList.remove('hidden');

            if (history.final_metrics) {
                const configType = window.currentViewExp?.feature_config_type || 'retrieval';
                if (configType !== 'multitask') {
                    renderMetricsSummary(history.final_metrics, true, configType);
                }
            }

        } catch (error) {
            console.error('Error loading training history:', error);
            loadingEl.classList.add('hidden');
            messageEl.textContent = 'Error loading training data';
            placeholderEl.classList.remove('hidden');
        }
    }

    function destroyCharts() {
        if (charts.lossChart) { charts.lossChart.destroy(); charts.lossChart = null; }
        if (charts.metricsChart) { charts.metricsChart.destroy(); charts.metricsChart = null; }
        if (charts.gradientChart) { charts.gradientChart.destroy(); charts.gradientChart = null; }
        if (charts.weightStatsChart) { charts.weightStatsChart.destroy(); charts.weightStatsChart = null; }
        weightData = { norms: null, stats: null, histogram: null };
    }

    function renderTrainingCharts(history) {
        renderLossChart(history);
        renderMetricsChart(history);

        const tower = document.getElementById('weightAnalysisTower')?.value || 'query';
        renderGradientChart(history, tower);
        renderWeightStatsChart(history, tower);

        renderWeightHistogramChart(history);
        renderFinalMetricsTable(history);
    }

    function renderLossChart(history) {
        const ctx = document.getElementById('trainingLossChart');
        if (!ctx) return;

        const loss = history.loss || {};
        const epochs = history.epochs || [];

        const hasData = Object.values(loss).some(arr => arr && arr.length > 0);
        if (!hasData) return;

        const datasets = [];
        const lossConfig = [
            { key: 'train', label: 'Train Loss', color: '#3b82f6', dash: [], fill: true },
            { key: 'val', label: 'Val Loss', color: '#f59e0b', dash: [], fill: true },
            { key: 'regularization', label: 'Reg Loss', color: '#6b7280', dash: [2, 2], fill: false, hidden: true },
            { key: 'val_regularization', label: 'Val Reg Loss', color: '#9ca3af', dash: [2, 2], fill: false, hidden: true },
        ];

        lossConfig.forEach(cfg => {
            const data = loss[cfg.key] || [];
            if (data.length > 0) {
                datasets.push({
                    label: cfg.label,
                    data: data,
                    borderColor: cfg.color,
                    backgroundColor: cfg.fill ? `${cfg.color}1a` : 'transparent',
                    fill: cfg.fill,
                    tension: 0.3,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    borderDash: cfg.dash,
                    hidden: cfg.hidden || false
                });
            }
        });

        charts.lossChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: epochs.map(e => e + 1),
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                layout: chartDefaults.layout,
                plugins: {
                    legend: {
                        position: 'top',
                        labels: chartDefaults.legend.labels,
                        onClick: function(e, legendItem, legend) {
                            const index = legendItem.datasetIndex;
                            const ci = legend.chart;
                            const meta = ci.getDatasetMeta(index);
                            meta.hidden = meta.hidden === null ? !ci.data.datasets[index].hidden : null;
                            ci.update();
                        }
                    },
                    tooltip: { mode: 'index', intersect: false }
                },
                scales: {
                    y: {
                        beginAtZero: false,
                        grace: chartDefaults.scales.y.grace,
                        title: { display: true, text: 'Loss', ...chartDefaults.scales.y.title },
                        ticks: chartDefaults.scales.y.ticks
                    },
                    x: {
                        ticks: { ...chartDefaults.scales.x.ticks, maxRotation: 0 }
                    }
                },
                interaction: { mode: 'nearest', axis: 'x', intersect: false }
            }
        });
    }

    function renderMetricsChart(history) {
        const ctx = document.getElementById('trainingMetricsChart');
        if (!ctx) return;

        const finalMetrics = history.final_metrics || {};
        const configType = window.currentViewExp?.feature_config_type || 'retrieval';

        let metricLabels = [];
        let metricValues = [];
        const colors = ['#06b6d4', '#10b981', '#8b5cf6', '#ec4899'];
        let isRanking = configType === 'ranking';
        let chartTitle, yAxisTitle, formatValue, formatLabel;

        if (isRanking) {
            const rankingMetrics = [
                { label: 'RMSE', value: finalMetrics['rmse'] ?? finalMetrics['final_val_rmse'] ?? finalMetrics['final_rmse'] },
                { label: 'Test RMSE', value: finalMetrics['test_rmse'] },
                { label: 'MAE', value: finalMetrics['mae'] ?? finalMetrics['final_val_mae'] ?? finalMetrics['final_mae'] },
                { label: 'Test MAE', value: finalMetrics['test_mae'] }
            ];

            rankingMetrics.forEach(({ label, value }) => {
                if (value !== undefined && value !== null) {
                    metricLabels.push(label);
                    metricValues.push(value);
                }
            });

            chartTitle = 'Error Metrics';
            yAxisTitle = 'Error Value';
            formatValue = v => v.toFixed(4);
            formatLabel = v => v.toFixed(4);
        } else {
            const recallKeys = [
                { key: 'test_recall_at_5', label: 'Recall@5' },
                { key: 'test_recall_at_10', label: 'Recall@10' },
                { key: 'test_recall_at_50', label: 'Recall@50' },
                { key: 'test_recall_at_100', label: 'Recall@100' }
            ];

            recallKeys.forEach(({ key, label }) => {
                if (finalMetrics[key] !== undefined) {
                    metricLabels.push(label);
                    metricValues.push(finalMetrics[key]);
                }
            });

            chartTitle = 'Recall Metrics';
            yAxisTitle = 'Recall Rate';
            formatValue = v => (v * 100).toFixed(2) + '%';
            formatLabel = v => (v * 100).toFixed(2) + '%';
        }

        const titleElement = document.getElementById('metricsChartTitle');
        if (titleElement) {
            titleElement.textContent = chartTitle;
        }

        if (metricValues.length === 0) {
            const hasAnyFinalMetrics = Object.keys(finalMetrics).length > 0;
            if (hasAnyFinalMetrics) {
                ctx.parentElement.innerHTML = `
                    <h5 class="training-chart-title">${chartTitle}</h5>
                    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 180px; color: #9ca3af; text-align: center;">
                        <i class="fas fa-exclamation-triangle" style="font-size: 24px; margin-bottom: 8px; color: #f59e0b;"></i>
                        <span style="font-size: 13px;">${isRanking ? 'Error' : 'Recall'} evaluation failed</span>
                        <span style="font-size: 11px; margin-top: 4px;">Check logs for details</span>
                    </div>
                `;
            }
            return;
        }

        // Check if ChartDataLabels plugin is available
        const plugins = typeof ChartDataLabels !== 'undefined' ? [ChartDataLabels] : [];

        charts.metricsChart = new Chart(ctx, {
            type: 'bar',
            plugins: plugins,
            data: {
                labels: metricLabels,
                datasets: [{
                    label: isRanking ? 'Error Metrics' : 'Test Recall',
                    data: metricValues,
                    backgroundColor: colors.slice(0, metricValues.length),
                    borderColor: colors.slice(0, metricValues.length).map(c => c),
                    borderWidth: 1,
                    borderRadius: 4,
                    barThickness: 40
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                layout: chartDefaults.layout,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return formatValue(context.parsed.y);
                            }
                        }
                    },
                    datalabels: plugins.length > 0 ? {
                        anchor: 'end',
                        align: 'end',
                        offset: 4,
                        color: '#374151',
                        font: {
                            size: 12,
                            weight: '600'
                        },
                        formatter: function(value) {
                            return formatLabel(value);
                        }
                    } : undefined
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        max: isRanking ? undefined : 1,
                        title: { display: true, text: yAxisTitle, ...chartDefaults.scales.y.title },
                        ticks: {
                            ...chartDefaults.scales.y.ticks,
                            callback: function(value) {
                                return isRanking ? value.toFixed(2) : (value * 100).toFixed(0) + '%';
                            }
                        }
                    },
                    x: {
                        ticks: chartDefaults.scales.x.ticks
                    }
                }
            }
        });
    }

    function renderGradientChart(history, tower = 'query') {
        const ctx = document.getElementById('trainingGradientChart');
        if (!ctx) return;

        // Store data for tower switching
        weightData.norms = history;

        const weightNorms = history.gradient || {};
        const epochs = history.epochs || [];

        // Check if we have data for selected tower
        const towerData = weightNorms[tower];
        const hasData = towerData && towerData.length > 0;

        if (!hasData) return;

        // Destroy existing chart
        if (charts.gradientChart) {
            charts.gradientChart.destroy();
            charts.gradientChart = null;
        }

        // Tower display config
        const towerConfig = {
            query: { label: 'Query Tower', color: '#3b82f6' },
            candidate: { label: 'Candidate Tower', color: '#10b981' }
        };

        const config = towerConfig[tower];

        charts.gradientChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: epochs.map(e => e + 1),
                datasets: [{
                    label: config.label,
                    data: towerData,
                    borderColor: config.color,
                    backgroundColor: `${config.color}1a`,
                    fill: true,
                    tension: 0.3,
                    pointRadius: 3
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                layout: chartDefaults.layout,
                plugins: {
                    legend: { display: false },
                    tooltip: { mode: 'index', intersect: false }
                },
                scales: {
                    y: {
                        grace: chartDefaults.scales.y.grace,
                        title: { display: true, text: 'L1/L2 Norm', ...chartDefaults.scales.y.title },
                        ticks: chartDefaults.scales.y.ticks
                    },
                    x: {
                        ticks: chartDefaults.scales.x.ticks
                    }
                }
            }
        });
    }

    function renderWeightStatsChart(history, tower = 'query') {
        const ctx = document.getElementById('trainingWeightStatsChart');
        if (!ctx) return;

        // Store data for tower switching
        weightData.stats = history;

        const weightStats = history.weight_stats || {};
        const epochs = history.epochs || [];
        const towerStats = weightStats[tower] || {};

        // Check if we have data
        const hasData = towerStats.mean && towerStats.mean.length > 0;

        if (!hasData) {
            // Show placeholder
            ctx.style.display = 'none';
            const placeholder = document.createElement('div');
            placeholder.style.cssText = 'display: flex; flex-direction: column; align-items: center; justify-content: center; height: 160px; color: #9ca3af; text-align: center;';
            placeholder.innerHTML = `
                <i class="fas fa-layer-group" style="font-size: 24px; margin-bottom: 8px; opacity: 0.5;"></i>
                <span style="font-size: 13px;">Weight data not available</span>
                <span style="font-size: 11px; margin-top: 4px;">Run a new experiment to collect weight stats</span>
            `;
            const existingPlaceholder = ctx.parentElement.querySelector('.weight-placeholder');
            if (existingPlaceholder) existingPlaceholder.remove();
            placeholder.className = 'weight-placeholder';
            ctx.parentElement.appendChild(placeholder);
            return;
        }

        // Remove placeholder if exists and show canvas
        const existingPlaceholder = ctx.parentElement.querySelector('.weight-placeholder');
        if (existingPlaceholder) existingPlaceholder.remove();
        ctx.style.display = 'block';

        // Destroy existing chart
        if (charts.weightStatsChart) {
            charts.weightStatsChart.destroy();
            charts.weightStatsChart = null;
        }

        const datasets = [
            {
                label: 'Mean',
                data: towerStats.mean,
                borderColor: '#3b82f6',
                tension: 0.3,
                fill: false,
                pointRadius: 2
            },
            {
                label: 'Std Dev',
                data: towerStats.std,
                borderColor: '#f59e0b',
                tension: 0.3,
                fill: false,
                pointRadius: 2
            }
        ];

        // Add min/max as filled area if available
        if (towerStats.min && towerStats.max) {
            datasets.push({
                label: 'Min',
                data: towerStats.min,
                borderColor: '#10b981',
                borderDash: [2, 2],
                tension: 0.3,
                fill: false,
                pointRadius: 0
            });
            datasets.push({
                label: 'Max',
                data: towerStats.max,
                borderColor: '#ef4444',
                borderDash: [2, 2],
                tension: 0.3,
                fill: false,
                pointRadius: 0
            });
        }

        charts.weightStatsChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: epochs.map(e => e + 1),
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                layout: chartDefaults.layout,
                plugins: {
                    legend: {
                        position: 'top',
                        labels: chartDefaults.legend.labels
                    },
                    tooltip: { mode: 'index', intersect: false }
                },
                scales: {
                    y: {
                        grace: chartDefaults.scales.y.grace,
                        title: { display: true, text: 'Value', ...chartDefaults.scales.y.title },
                        ticks: chartDefaults.scales.y.ticks
                    },
                    x: {
                        ticks: chartDefaults.scales.x.ticks
                    }
                }
            }
        });
    }

    // Fetch histogram data on-demand from GCS (not cached due to size)
    async function fetchHistogramData(history, tower, isGradients) {
        try {
            console.log('[Histogram] Fetching on-demand from GCS...');
            // Use appropriate endpoint and ID based on mode
            const id = state.mode === 'training_run' ? state.runId : state.expId;
            const endpoint = state.mode === 'training_run'
                ? config.endpoints.trainingRunHistogramData
                : (config.endpoints.histogramData || '/api/quick-tests/{id}/histogram-data/');
            const url = buildUrl(endpoint, { id: id });
            const response = await fetch(url);
            const data = await response.json();

            // Mark fetch attempted to prevent infinite loops
            history._histogramFetchAttempted = true;

            if (data.success && data.histogram_data) {
                // Merge histogram data into history
                const histData = data.histogram_data;

                // Merge weight_stats histograms
                if (histData.weight_stats) {
                    for (const t of ['query', 'candidate']) {
                        if (histData.weight_stats[t]?.histogram) {
                            if (!history.weight_stats) history.weight_stats = {};
                            if (!history.weight_stats[t]) history.weight_stats[t] = {};
                            history.weight_stats[t].histogram = histData.weight_stats[t].histogram;
                        }
                    }
                }

                // Merge gradient_stats histograms
                if (histData.gradient_stats) {
                    for (const t of ['query', 'candidate']) {
                        if (histData.gradient_stats[t]?.histogram) {
                            if (!history.gradient_stats) history.gradient_stats = {};
                            if (!history.gradient_stats[t]) history.gradient_stats[t] = {};
                            history.gradient_stats[t].histogram = histData.gradient_stats[t].histogram;
                        }
                    }
                }

                console.log('[Histogram] Data fetched and merged successfully');

                // Update cache
                state.dataCache.trainingHistory = history;
                weightData.histogram = history;

                // Re-render chart with new data
                renderWeightHistogramChart(history, tower);
            } else {
                console.log('[Histogram] No histogram data available from MLflow');
                // Re-render to show "not available" message
                renderWeightHistogramChart(history, tower);
            }
        } catch (error) {
            console.error('[Histogram] Failed to fetch:', error);
            history._histogramFetchAttempted = true;
            renderWeightHistogramChart(history, tower);
        }
    }

    function renderWeightHistogramChart(history, tower = null) {
        const container = document.getElementById('trainingWeightHistogramChart');
        if (!container) return;

        // Store data for tower switching
        weightData.histogram = history;

        // Get tower from dropdown or use provided value
        tower = tower || document.getElementById('weightHistogramTower')?.value || 'query';

        // Get data type (weights or gradients)
        const dataType = document.getElementById('histogramDataType')?.value || 'weights';
        const isGradients = dataType === 'gradients';

        // Select appropriate data source
        const statsSource = isGradients ? (history.gradient_stats || {}) : (history.weight_stats || {});
        const towerStats = statsSource[tower] || {};
        const histogram = towerStats.histogram;

        // Update chart title
        const titleEl = document.getElementById('histogramChartTitle');
        if (titleEl) {
            titleEl.textContent = isGradients ? 'Gradient Distribution Histogram' : 'Weight Distribution Histogram';
        }

        // Check if histogram data is available
        if (!histogram || !histogram.bin_edges || !histogram.counts || histogram.counts.length === 0) {
            // Check if histogram data is available via on-demand fetch
            const currentId = state.mode === 'training_run' ? state.runId : state.expId;
            if (history.histogram_available && currentId && !history._histogramFetchAttempted) {
                // Show loading state
                container.innerHTML = `
                    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: #9ca3af; text-align: center;">
                        <i class="fas fa-spinner fa-spin" style="font-size: 32px; margin-bottom: 12px; opacity: 0.5;"></i>
                        <span style="font-size: 14px;">Loading histogram data from GCS...</span>
                        <span style="font-size: 12px; margin-top: 6px;">This may take a moment</span>
                    </div>
                `;
                // Fetch histogram data on-demand
                fetchHistogramData(history, tower, isGradients);
                return;
            }

            const dataTypeName = isGradients ? 'Gradient' : 'Weight';
            const featureNote = isGradients
                ? 'Run a new experiment to collect gradient distribution histograms.'
                : 'Run a new experiment to collect weight distribution histograms.';
            container.innerHTML = `
                <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: #9ca3af; text-align: center;">
                    <i class="fas fa-chart-area" style="font-size: 32px; margin-bottom: 12px; opacity: 0.5;"></i>
                    <span style="font-size: 14px;">${dataTypeName} histogram data not available</span>
                    <span style="font-size: 12px; margin-top: 6px; max-width: 400px;">
                        ${featureNote}
                    </span>
                </div>
            `;
            return;
        }

        // Check if container is visible (has dimensions)
        const rect = container.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) {
            requestAnimationFrame(() => renderWeightHistogramChart(history, tower));
            return;
        }

        // Clear container
        container.innerHTML = '';

        const { bin_edges, counts } = histogram;
        const epochs = history.epochs || [];
        const numEpochs = counts.length;
        const numBins = bin_edges.length - 1;

        // Dimensions - dynamic top margin to prevent clipping of ridges
        const baseMargin = { top: 10, right: 50, bottom: 40, left: 50 };
        const width = Math.floor(rect.width) - baseMargin.left - baseMargin.right;
        const prelimHeight = Math.floor(rect.height) - baseMargin.top - baseMargin.bottom;

        // Calculate bandwidth from preliminary yEpoch scale
        const prelimYEpoch = d3.scaleBand()
            .domain(d3.range(numEpochs))
            .range([0, prelimHeight])
            .paddingInner(0);
        const bandWidth = prelimYEpoch.bandwidth();

        // Calculate dynamic ridge height
        const baseRidgeHeight = prelimHeight * 0.15;
        const scaledRidgeHeight = bandWidth * 2.5;
        const maxRidgeHeight = Math.min(baseRidgeHeight, scaledRidgeHeight);

        // Calculate dynamic top margin to accommodate ridge overflow
        const dynamicTopMargin = maxRidgeHeight + 15;
        const margin = {
            top: dynamicTopMargin,
            right: baseMargin.right,
            bottom: baseMargin.bottom,
            left: baseMargin.left
        };

        // Recalculate final height with dynamic margin
        const height = Math.floor(rect.height) - margin.top - margin.bottom;

        // Create SVG
        const svg = d3.select(container)
            .append('svg')
            .attr('width', width + margin.left + margin.right)
            .attr('height', height + margin.top + margin.bottom)
            .append('g')
            .attr('transform', `translate(${margin.left},${margin.top})`);

        // Data range
        const maxCount = Math.max(...counts.flat());
        const xMin = bin_edges[0];
        const xMax = bin_edges[bin_edges.length - 1];

        // X scale: weight values
        const xScale = d3.scaleLinear()
            .domain([xMin, xMax])
            .range([0, width]);

        // Y scale for density (height of each ridge)
        const yDensity = d3.scaleLinear()
            .domain([0, maxCount])
            .range([0, maxRidgeHeight]);

        // Y scale for epoch positioning (band scale)
        const yEpoch = d3.scaleBand()
            .domain(d3.range(numEpochs))
            .range([0, height])
            .paddingInner(0);

        // Color scale: light orange (old) to dark orange (new)
        const colorScale = d3.scaleLinear()
            .domain([0, numEpochs - 1])
            .range(['#fdd4b3', '#e25822']);

        // Prepare data for each epoch
        const ridgeData = counts.map((epochCounts, epochIdx) => {
            const points = epochCounts.map((count, binIdx) => ({
                x: (bin_edges[binIdx] + bin_edges[binIdx + 1]) / 2,
                y: count
            }));
            return {
                epochIdx,
                points: [
                    { x: bin_edges[0], y: 0 },
                    ...points,
                    { x: bin_edges[numBins], y: 0 }
                ]
            };
        });

        // Area generator
        const area = d3.area()
            .x(d => xScale(d.x))
            .y0(0)
            .y1(d => -yDensity(d.y))
            .curve(d3.curveBasis);

        // Draw ridges from back to front (oldest first)
        svg.selectAll('.ridge')
            .data(ridgeData)
            .join('path')
            .attr('class', 'ridge')
            .attr('transform', d => `translate(0, ${yEpoch(d.epochIdx) + yEpoch.bandwidth()})`)
            .attr('d', d => area(d.points))
            .attr('fill', d => colorScale(d.epochIdx))
            .attr('fill-opacity', d => 0.7 + (d.epochIdx / Math.max(numEpochs - 1, 1)) * 0.25)
            .attr('stroke', '#fff')
            .attr('stroke-width', 1);

        // X-axis
        const xAxis = d3.axisBottom(xScale)
            .ticks(8)
            .tickFormat(d => (xMax - xMin) > 1 ? d.toFixed(1) : d.toFixed(2));

        svg.append('g')
            .attr('transform', `translate(0, ${height})`)
            .call(xAxis)
            .selectAll('text')
            .style('font-size', '11px')
            .style('fill', '#6b7280');

        // X-axis label (dynamic based on data type)
        const xAxisLabel = isGradients ? 'Gradient Value' : 'Weight Value';
        svg.append('text')
            .attr('x', width / 2)
            .attr('y', height + 35)
            .attr('text-anchor', 'middle')
            .style('font-size', '12px')
            .style('fill', '#374151')
            .text(xAxisLabel);

        // Epoch labels on right side
        // Note: histogram counts may have all epochs (e.g., 150) while history.epochs
        // may only have sampled epochs (e.g., 31). We need to handle both cases.
        const histogramHasAllEpochs = numEpochs !== epochs.length;
        const epochStep = Math.max(1, Math.ceil(numEpochs / 15));
        const epochLabels = d3.range(0, numEpochs, epochStep);
        if ((numEpochs - 1) % epochStep !== 0) epochLabels.push(numEpochs - 1);
        // Sort to ensure proper order
        epochLabels.sort((a, b) => a - b);

        // Horizontal grid lines for major epochs
        svg.selectAll('.epoch-grid-line')
            .data(epochLabels)
            .join('line')
            .attr('class', 'epoch-grid-line')
            .attr('x1', 0)
            .attr('x2', width)
            .attr('y1', d => yEpoch(d) + yEpoch.bandwidth())
            .attr('y2', d => yEpoch(d) + yEpoch.bandwidth())
            .attr('stroke', '#e5e7eb')
            .attr('stroke-width', 1)
            .attr('stroke-opacity', 0.4);

        svg.selectAll('.epoch-label')
            .data(epochLabels)
            .join('text')
            .attr('class', 'epoch-label')
            .attr('x', width + 8)
            .attr('y', d => yEpoch(d) + yEpoch.bandwidth())
            .attr('dy', '0.35em')
            .style('font-size', '10px')
            .style('fill', '#9ca3af')
            .text(d => {
                // If histogram has all epochs (counts.length != epochs.length),
                // use the index directly as the epoch number
                if (histogramHasAllEpochs) {
                    return d + 1;  // 1-indexed epoch number
                }
                // Otherwise use the sampled epochs array
                return epochs[d] !== undefined ? epochs[d] + 1 : d + 1;
            });
    }

    function renderFinalMetricsTable(history) {
        const container = document.getElementById('expViewMetricsRows');
        const section = document.getElementById('expViewFinalMetrics');
        if (!container || !section) return;

        const finalMetrics = history.final_metrics || {};

        if (Object.keys(finalMetrics).length === 0) {
            section.classList.add('hidden');
            return;
        }

        const tableRows = [
            { name: 'Loss', train: finalMetrics['final_loss'], val: finalMetrics['final_val_loss'], test: finalMetrics['test_loss'] },
            { name: 'Reg. Loss', train: finalMetrics['final_regularization_loss'], val: finalMetrics['final_val_regularization_loss'], test: finalMetrics['test_regularization_loss'] },
            { name: 'Total Loss', train: finalMetrics['final_total_loss'], val: finalMetrics['final_val_total_loss'], test: finalMetrics['test_total_loss'] }
        ];

        const formatVal = (value) => value == null ? '—' : value.toFixed(2);

        let html = `
            <table class="final-metrics-table">
                <thead>
                    <tr>
                        <th>Metric</th>
                        <th>Train</th>
                        <th>Val</th>
                        <th>Test</th>
                    </tr>
                </thead>
                <tbody>`;

        tableRows.forEach(row => {
            if (row.train != null || row.val != null || row.test != null) {
                html += `
                    <tr>
                        <td>${row.name}</td>
                        <td class="val-train">${formatVal(row.train)}</td>
                        <td class="val-val">${formatVal(row.val)}</td>
                        <td class="val-test">${formatVal(row.test)}</td>
                    </tr>`;
            }
        });

        html += '</tbody></table>';
        container.innerHTML = html;
        section.classList.remove('hidden');
    }

    function updateWeightAnalysisCharts() {
        const tower = document.getElementById('weightAnalysisTower')?.value || 'query';
        if (weightData.norms) renderGradientChart(weightData.norms, tower);
        if (weightData.stats) renderWeightStatsChart(weightData.stats, tower);
    }

    function updateWeightHistogramChart() {
        if (weightData.histogram) renderWeightHistogramChart(weightData.histogram);
    }

    // =============================================================================
    // POLLING
    // =============================================================================

    function startPolling(expId) {
        stopPolling();

        state.pollInterval = setInterval(async () => {
            try {
                const url = buildUrl(config.endpoints.experimentDetails, { id: expId });
                const response = await fetch(url);
                const data = await response.json();

                if (data.success) {
                    const exp = data.quick_test;
                    populateModal(exp);
                    state.currentExp = exp;

                    if (config.onUpdate) {
                        config.onUpdate(exp);
                    }

                    if (['completed', 'failed', 'cancelled'].includes(exp.status)) {
                        stopPolling();
                    }
                }
            } catch (error) {
                console.error('View modal polling error:', error);
            }
        }, 10000);
    }

    function stopPolling() {
        if (state.pollInterval) {
            clearInterval(state.pollInterval);
            state.pollInterval = null;
        }
    }

    // =============================================================================
    // COMPONENT LOGS (delegated to pipeline_dag.js)
    // =============================================================================

    function refreshComponentLogs() {
        // Use correct ID based on mode (training runs use runId, experiments use expId)
        const id = state.mode === 'training_run' ? state.runId : state.expId;
        if (typeof window.refreshComponentLogs === 'function' && id) {
            window.refreshComponentLogs(id);
        }
    }

    // =============================================================================
    // OVERVIEW TAB ACCORDION
    // =============================================================================

    function toggleAccordion(sectionName) {
        // Toggle the expanded state
        state.accordionExpanded[sectionName] = !state.accordionExpanded[sectionName];
        const isExpanded = state.accordionExpanded[sectionName];

        // Map section names to element IDs
        const sectionMap = {
            registryDeployment: 'expViewRegistryDeployment',
            dataset: 'expViewDataset',
            features: 'expViewFeatures',
            model: 'expViewModel',
            trainingSetup: 'expViewTrainingSetup'
        };

        const prefix = sectionMap[sectionName];
        if (!prefix) return;

        const content = document.getElementById(`${prefix}Content`);
        const chevron = document.getElementById(`${prefix}Chevron`);

        if (content) {
            if (isExpanded) {
                content.classList.remove('hidden');
            } else {
                content.classList.add('hidden');
            }
        }

        if (chevron) {
            if (isExpanded) {
                chevron.classList.add('expanded');
            } else {
                chevron.classList.remove('expanded');
            }
        }
    }

    function resetAccordionStates() {
        // Reset all accordions to collapsed state
        state.accordionExpanded = {
            registryDeployment: false,
            dataset: false,
            features: false,
            model: false,
            trainingSetup: false
        };

        // Collapse all accordion contents
        const prefixes = ['expViewRegistryDeployment', 'expViewDataset', 'expViewFeatures', 'expViewModel', 'expViewTrainingSetup'];

        prefixes.forEach(prefix => {
            const content = document.getElementById(`${prefix}Content`);
            const chevron = document.getElementById(`${prefix}Chevron`);
            if (content) content.classList.add('hidden');
            if (chevron) chevron.classList.remove('expanded');
        });
    }

    // =============================================================================
    // PUBLIC API
    // =============================================================================

    return {
        // Configuration
        configure: configure,

        // Modal operations
        open: open,
        openWithData: openWithData,
        openWithTrainingRunData: openWithTrainingRunData,
        close: close,
        handleOverlayClick: handleOverlayClick,

        // Model mode operations
        openForModel: openForModel,
        openWithModelData: openWithModelData,
        selectModelVersion: selectModelVersion,
        deployModel: deployModel,
        undeployModel: undeployModel,
        copyToClipboard: copyToClipboard,

        // Training run actions (Registry & Deployment)
        pushToRegistry: pushToRegistry,
        registerModel: registerModel,
        deployTrainingRun: deployTrainingRun,
        deployToCloudRun: deployToCloudRun,
        undeployTrainingRun: undeployTrainingRun,
        scheduleRetraining: scheduleRetraining,

        // Tab switching
        switchTab: switchTab,

        // Overview accordion
        toggleAccordion: toggleAccordion,

        // Component logs
        refreshComponentLogs: refreshComponentLogs,

        // Weight analysis chart updates
        updateWeightAnalysisCharts: updateWeightAnalysisCharts,
        updateWeightHistogramChart: updateWeightHistogramChart,

        // State access (for debugging)
        getState: () => state,
        getCurrentExp: () => state.currentExp,
        getCurrentRun: () => state.currentRun,
        getCurrentModel: () => state.currentModel,
        getMode: () => state.mode
    };
})();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ExpViewModal;
}
