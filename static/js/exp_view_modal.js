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
        showVersionDeployButtons: false,  // Show Deploy/Undeploy buttons in Versions tab
        onClose: null,
        onUpdate: null,
        modelId: null
    };

    let state = {
        mode: 'experiment',  // 'experiment', 'training_run', 'model', or 'endpoint'
        expId: null,
        currentExp: null,
        runId: null,
        currentRun: null,
        modelId: null,
        currentModel: null,
        endpointId: null,
        currentEndpoint: null,
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
        }
    };

    // Training chart instances
    let charts = {
        lossChart: null,
        metricsChart: null,
        gradientChart: null,
        weightStatsChart: null,
        versionsChart: null
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
        not_blessed: { icon: 'fa-exclamation', color: '#f97316', label: 'Not Blessed' },
        deploying: { icon: 'fa-sync', color: '#3b82f6', label: 'Deploying' },
        deployed: { icon: 'fa-check', color: '#10b981', label: 'Deployed' },
        deploy_failed: { icon: 'fa-exclamation', color: '#ef4444', label: 'Deploy Failed' },
        registered: { icon: 'fa-check', color: '#10b981', label: 'Registered' }
    };

    // Pipeline stages for training runs (9 stages including Deploy)
    // NOTE: 'name' must match TFX_PIPELINE.components 'id' in pipeline_dag.js for status mapping
    const TRAINING_PIPELINE_STAGES = [
        { id: 'compile', name: 'Compile', icon: 'fa-cog' },
        { id: 'examples', name: 'Examples', icon: 'fa-database' },
        { id: 'stats', name: 'Stats', icon: 'fa-chart-bar' },
        { id: 'schema', name: 'Schema', icon: 'fa-sitemap' },
        { id: 'transform', name: 'Transform', icon: 'fa-exchange-alt' },
        { id: 'train', name: 'Train', icon: 'fa-graduation-cap' },
        { id: 'evaluator', name: 'Evaluator', icon: 'fa-check-double' },
        { id: 'register', name: 'Register', icon: 'fa-box-archive' },
        { id: 'deploy', name: 'Deploy', icon: 'fa-rocket' }
    ];

    function appendModelEndpointId(url) {
        if (!config.modelId) return url;
        const sep = url.includes('?') ? '&' : '?';
        return `${url}${sep}model_endpoint_id=${config.modelId}`;
    }

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
        if (options.modelId) config.modelId = options.modelId;
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

            const response = await fetch(appendModelEndpointId(url));
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
        document.querySelectorAll('.exp-view-pill').forEach(t => t.classList.remove('current'));
        const overviewTab = document.querySelector('.exp-view-pill[data-tab="overview"]');
        if (overviewTab) overviewTab.classList.add('current');

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
        document.querySelectorAll('.exp-view-pill').forEach(t => t.classList.remove('current'));
        const overviewTab = document.querySelector('.exp-view-pill[data-tab="overview"]');
        if (overviewTab) overviewTab.classList.add('current');

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

        // Show new header, hide legacy
        showNewHeader();

        // Show dataset section for training run mode (experiment mode hides it)
        const dsAccordion = document.getElementById('expViewDatasetAccordion');
        if (dsAccordion) dsAccordion.style.display = 'flex';

        // Determine effective status — use "registered" (green) if model is registered
        const isRegistered = run.vertex_model_resource_name || run.registered_at;
        const effectiveStatus = isRegistered ? 'registered' : run.status;

        // New header: status gradient
        const header = document.getElementById('expViewHeader');
        header.className = `modal-header-soft soft-run-${effectiveStatus}`;

        // Icon badge — cogs for training runs
        const iconBadge = header.querySelector('.modal-header-icon-badge');
        if (iconBadge) iconBadge.innerHTML = '<i class="fas fa-cogs"></i>';

        // Title: "Run #N · name" or just "Run #N"
        const runName = run.name || '';
        const titleText = runName ? `Run #${run.run_number} \u00b7 ${runName}` : `Run #${run.run_number}`;
        document.getElementById('expViewTitle').textContent = titleText;

        // Subtitle
        document.getElementById('expViewSubtitle').textContent = 'Training run overview';

        // Status badge (circle)
        const statusBadge = document.getElementById('expViewStatusBadge');
        const statusCfg = TRAINING_STATUS_CONFIG[effectiveStatus] || TRAINING_STATUS_CONFIG.pending;
        const isSpinning = run.status === 'running' || run.status === 'submitting' || run.status === 'deploying';
        statusBadge.className = `modal-header-status-circle ${effectiveStatus}`;
        statusBadge.innerHTML = `<i class="fas ${statusCfg.icon}${isSpinning ? ' fa-spin' : ''}"></i>`;

        // Nav bar status color
        const navBar = document.getElementById('expViewNavBar');
        if (navBar) {
            const statusMap = {
                completed: 'completed', failed: 'failed', running: 'running',
                submitting: 'running', pending: 'pending', cancelled: 'cancelled',
                registered: 'completed', deployed: 'completed', deploying: 'running',
                deploy_failed: 'failed', not_blessed: 'failed', scheduled: 'pending'
            };
            const navStatus = statusMap[effectiveStatus] || 'pending';
            navBar.className = `exp-view-nav-bar exp-nav-${navStatus}`;
        }

        // Show card sections, hide legacy results summary
        const cardSections = document.getElementById('expViewCardSections');
        if (cardSections) cardSections.style.display = '';
        const resultsSummary = document.getElementById('expViewResultsSummary');
        if (resultsSummary) resultsSummary.classList.add('hidden');

        // Card 1: Run Information
        const modelType = (run.model_type || 'retrieval').toLowerCase();
        const badgeContents = {
            'retrieval': '<i class="fas fa-search"></i> Retrieval',
            'ranking': '<i class="fas fa-sort-amount-down"></i> Ranking',
            'multitask': '<i class="fas fa-layer-group"></i> Retrieval / Ranking'
        };

        const nameCard = document.getElementById('expCardName');
        if (nameCard) nameCard.querySelector('.stat-value').textContent = runName || '\u2014';

        const typeCard = document.getElementById('expCardModelType');
        if (typeCard) {
            typeCard.querySelector('.stat-value').innerHTML =
                `<span class="exp-detail-type-badge ${modelType}">${badgeContents[modelType] || badgeContents['retrieval']}</span>`;
        }

        const descCard = document.getElementById('expCardDescription');
        if (descCard) {
            descCard.querySelector('.stat-value').textContent = run.notes || '\u2014';
        }

        // Card 2: Timeline
        const startCard = document.getElementById('expCardStart');
        if (startCard) startCard.querySelector('.stat-value').textContent = formatDateTime(run.started_at || run.created_at);

        const endCard = document.getElementById('expCardEnd');
        if (endCard) endCard.querySelector('.stat-value').textContent = run.completed_at ? formatDateTime(run.completed_at) : '\u2014';

        const durationCard = document.getElementById('expCardDuration');
        if (durationCard) {
            const durationSec = computeDuration(run.started_at || run.created_at, run.completed_at);
            durationCard.querySelector('.stat-value').textContent = durationSec != null ? formatDuration(durationSec) : '\u2014';
        }

        // Card 3: Results (for terminal statuses with metrics)
        const resultsCard = document.getElementById('expCardResults');
        if (resultsCard) {
            const terminalStatuses = ['completed', 'not_blessed', 'deployed', 'deploying', 'deploy_failed', 'registered'];
            if (terminalStatuses.includes(run.status) || isRegistered) {
                const metrics = {
                    recall_at_5: run.recall_at_5, recall_at_10: run.recall_at_10,
                    recall_at_50: run.recall_at_50, recall_at_100: run.recall_at_100,
                    rmse: run.rmse, mae: run.mae, test_rmse: run.test_rmse,
                    test_mae: run.test_mae, loss: run.loss
                };
                const hasMetrics = Object.values(metrics).some(v => v != null);
                if (hasMetrics) {
                    resultsCard.style.display = '';
                    renderResultsCard(metrics, modelType);
                } else {
                    resultsCard.style.display = 'none';
                }
            } else {
                resultsCard.style.display = 'none';
            }
        }

        // Overview Tab - render training run specific content
        renderTrainingRunOverview(run);

        // Pipeline Tab - render 8-stage pipeline
        renderTrainingRunPipeline(run);
    }

    function renderTrainingRunOverview(run) {
        // Reset accordion states when populating new data
        resetAccordionStates();

        // Dataset section
        state.datasetName = run.dataset_name || '';
        // Dataset details - load full details using existing function
        if (run.dataset_id) {
            loadDatasetDetails(run.dataset_id);
        } else {
            document.getElementById('expViewDatasetDetails').innerHTML =
                '<div class="exp-view-no-filters">No dataset configured</div>';
        }

        // Features config - load full details
        if (run.feature_config_id) {
            loadFeaturesConfig(run.feature_config_id);
        } else {
            document.getElementById('expViewFeaturesConfigContent').innerHTML =
                '<div class="exp-view-no-filters">No features config</div>';
        }

        // Model config - load full details
        if (run.model_config_id) {
            loadModelConfig(run.model_config_id);
        } else {
            document.getElementById('expViewModelConfigContent').innerHTML =
                '<div class="exp-view-no-filters">No model config</div>';
        }

        // Sampling & Training Parameters (card format)
        const trainingSetupCards = document.getElementById('expViewTrainingSetupCards');
        if (trainingSetupCards) {
            trainingSetupCards.innerHTML = renderTrainingRunSamplingCard(run) + renderTrainingRunParamsCard(run);
        }

        // Results Summary — skip legacy metrics section (now using card-based results)
        // renderTrainingRunMetrics(run);

        // Registry and Deployment sections (for training_run mode)
        renderRegistrySection(run);
        renderDeploymentSection(run);
    }

    function renderTrainingRunMetrics(run) {
        const resultsSummary = document.getElementById('expViewResultsSummary');

        // Show for all terminal states where training has completed
        const terminalStatuses = ['completed', 'not_blessed', 'deployed', 'deploying', 'deploy_failed'];
        if (!terminalStatuses.includes(run.status)) {
            resultsSummary.classList.add('hidden');
            return;
        }

        resultsSummary.classList.remove('hidden');

        // Build metrics object from training run properties
        const metrics = {
            recall_at_5: run.recall_at_5,
            recall_at_10: run.recall_at_10,
            recall_at_50: run.recall_at_50,
            recall_at_100: run.recall_at_100,
            rmse: run.rmse,
            mae: run.mae,
            test_rmse: run.test_rmse,
            test_mae: run.test_mae,
            loss: run.loss
        };

        // Delegate to renderMetricsSummary for consistent rendering
        renderMetricsSummary(metrics, false, run.model_type || 'retrieval');
    }

    function renderTrainingRunSamplingCard(run) {
        const params = run.training_params || {};
        const stats = [];

        if (params.split_strategy) {
            stats.push({ label: 'Split Strategy', value: params.split_strategy });
        }
        if (params.train_fraction) {
            stats.push({ label: 'Train', value: `${(params.train_fraction * 100).toFixed(0)}%` });
        }
        if (params.val_fraction) {
            stats.push({ label: 'Val', value: `${(params.val_fraction * 100).toFixed(0)}%` });
        }
        if (params.test_fraction) {
            stats.push({ label: 'Test', value: `${(params.test_fraction * 100).toFixed(0)}%` });
        }

        if (stats.length === 0) return '';

        return `
            <div class="exp-detail-section">
                <div class="exp-detail-section-title">Sampling</div>
                <div class="exp-detail-section-body">
                    <div class="exp-detail-section-icon sampling"><i class="fas fa-percentage"></i></div>
                    <div class="exp-detail-stats">
                        ${stats.map(s => `
                            <div class="exp-detail-stat-info">
                                <div class="stat-label">${s.label}</div>
                                <div class="stat-value">${s.value}</div>
                            </div>`).join('')}
                    </div>
                </div>
            </div>`;
    }

    function renderTrainingRunParamsCard(run) {
        const params = run.training_params || {};
        const gpuConfig = run.gpu_config || {};
        const stats = [];

        if (params.epochs) stats.push({ label: 'Epochs', value: params.epochs });
        if (params.batch_size) stats.push({ label: 'Batch Size', value: formatNumber(params.batch_size) });
        if (params.learning_rate) stats.push({ label: 'Learning Rate', value: params.learning_rate });

        // GPU config (keys are gpu_type, gpu_count, preemptible - not accelerator_*)
        if (gpuConfig.gpu_type) {
            stats.push({ label: 'GPU', value: gpuConfig.gpu_type.replace('NVIDIA_TESLA_', '').replace('NVIDIA_', '') });
        }
        if (gpuConfig.gpu_count) {
            stats.push({ label: 'GPU Count', value: gpuConfig.gpu_count });
        }
        if (gpuConfig.preemptible !== undefined) {
            stats.push({ label: 'Preemptible', value: gpuConfig.preemptible ? 'Yes' : 'No' });
        }

        if (stats.length === 0) return '';

        return `
            <div class="exp-detail-section">
                <div class="exp-detail-section-title">Training Parameters</div>
                <div class="exp-detail-section-body">
                    <div class="exp-detail-section-icon training"><i class="fas fa-cogs"></i></div>
                    <div class="exp-detail-stats">
                        ${stats.map(s => `
                            <div class="exp-detail-stat-info">
                                <div class="stat-label">${s.label}</div>
                                <div class="stat-value">${s.value}</div>
                            </div>`).join('')}
                    </div>
                </div>
            </div>`;
    }

    // =============================================================================
    // REGISTRY & DEPLOYMENT SECTIONS (Training Run Mode) - Consolidated Accordion
    // =============================================================================

    function renderRegistryDeploymentSection(data) {
        const section = document.getElementById('expViewRegistryDeploymentSection');
        const container = document.getElementById('expViewRegistryDeploymentContent');

        // Only show for training_run mode with terminal status
        if (state.mode !== 'training_run' || !data ||
            !['completed', 'not_blessed', 'failed'].includes(data.status)) {
            section.style.display = 'none';
            return;
        }

        section.style.display = '';

        // --- Registry stat ---
        let registryValue = '';
        if (data.is_blessed === false && data.status === 'not_blessed') {
            registryValue = '<span style="color: #dc2626;"><i class="fas fa-times-circle"></i> Evaluation Failed</span>';
        } else if (data.vertex_model_name) {
            registryValue = `<span style="color: #16a34a;"><i class="fas fa-check-circle"></i> ${escapeHtml(data.vertex_model_name)} (${data.vertex_model_version || 'v1'})</span>`;
        } else {
            registryValue = '<span style="color: #9ca3af;"><i class="fas fa-clock"></i> Not Registered</span>';
        }

        // --- Blessing stat ---
        let blessingValue = '\u2014';
        if (data.is_blessed === true) {
            blessingValue = '<span style="color: #16a34a;"><i class="fas fa-check"></i> Passed</span>';
        } else if (data.is_blessed === false) {
            blessingValue = '<span style="color: #dc2626;"><i class="fas fa-times"></i> Failed</span>';
        }

        // --- Registered at ---
        const registeredAt = data.vertex_model_name ? formatDateTime(data.registered_at) : '\u2014';

        // --- Deployment stat ---
        let deployValue = '\u2014';
        if (data.vertex_model_name) {
            if (data.is_deployed) {
                deployValue = `<span style="color: #16a34a;"><i class="fas fa-rocket"></i> Live</span>`;
            } else {
                deployValue = `<span style="color: #9ca3af;"><i class="fas fa-pause-circle"></i> Ready to Deploy</span>`;
            }
        }

        // Build stats row
        let html = '<div class="exp-detail-stats" style="flex-wrap: wrap;">';
        html += `<div class="exp-detail-stat-info"><div class="stat-label">Registry</div><div class="stat-value">${registryValue}</div></div>`;
        html += `<div class="exp-detail-stat-info"><div class="stat-label">Blessing</div><div class="stat-value">${blessingValue}</div></div>`;
        html += `<div class="exp-detail-stat-info"><div class="stat-label">Registered</div><div class="stat-value">${registeredAt}</div></div>`;
        html += `<div class="exp-detail-stat-info"><div class="stat-label">Deployment</div><div class="stat-value">${deployValue}</div></div>`;
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
            const response = await fetch(appendModelEndpointId(`/api/training-runs/${runId}/push/`), {
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
            const response = await fetch(appendModelEndpointId(`/api/training-runs/${runId}/register/`), {
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
        // Use the DeployWizard modal instead of confirm dialog
        if (typeof DeployWizard !== 'undefined') {
            DeployWizard.open(runId);
            return;
        }

        // Fallback to simple confirm if DeployWizard is not available
        if (!confirm('Are you sure you want to deploy this model to a Vertex AI Endpoint?')) return;

        try {
            const response = await fetch(appendModelEndpointId(`/api/training-runs/${runId}/deploy/`), {
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
        // Use the DeployWizard modal instead of confirm dialog
        if (typeof DeployWizard !== 'undefined') {
            DeployWizard.open(runId);
            return;
        }

        // Fallback to simple confirm if DeployWizard is not available
        if (!confirm('Are you sure you want to deploy this model to Cloud Run? This will create a serverless TF Serving endpoint.')) return;

        try {
            const response = await fetch(appendModelEndpointId(`/api/training-runs/${runId}/deploy-cloud-run/`), {
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

            const response = await fetch(appendModelEndpointId(`/api/models/${run.model_id}/undeploy/`), {
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

    /**
     * Deploy a specific version from the Versions tab.
     * Opens the DeployWizard with a success callback to refresh versions.
     */
    async function deployVersion(trainingRunId) {
        // Configure DeployWizard with success callback to refresh versions
        if (typeof DeployWizard !== 'undefined') {
            DeployWizard.configure({
                onSuccess: function(result) {
                    // Refresh the versions tab to show updated deployment status
                    if (state.currentModel && state.currentModel.id) {
                        // Clear cache to force refresh
                        state.dataCache.versions = null;
                        loadModelVersions(state.currentModel.id);
                    }
                }
            });
            DeployWizard.open(trainingRunId);
        } else {
            alert('Deploy wizard is not available. Please refresh the page.');
        }
    }

    /**
     * Undeploy a specific version from the Versions tab.
     * Shows confirmation dialog and calls the endpoint undeploy API.
     */
    async function undeployVersion(endpointId, trainingRunId) {
        if (!confirm('Are you sure you want to undeploy this version? This will delete the Cloud Run service.')) {
            return;
        }

        // Find and disable the undeploy button
        const buttons = document.querySelectorAll('.version-undeploy-btn');
        buttons.forEach(btn => {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Undeploying...';
        });

        try {
            const response = await fetch(appendModelEndpointId(`/api/deployed-endpoints/${endpointId}/undeploy/`), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });
            const data = await response.json();

            if (data.success) {
                // Refresh the versions tab to show updated deployment status
                if (state.currentModel && state.currentModel.id) {
                    // Clear cache to force refresh
                    state.dataCache.versions = null;
                    loadModelVersions(state.currentModel.id);
                }
            } else {
                alert('Failed to undeploy: ' + (data.error || 'Unknown error'));
                // Re-enable buttons
                buttons.forEach(btn => {
                    btn.disabled = false;
                    btn.innerHTML = 'Undeploy';
                });
            }
        } catch (error) {
            console.error('Error undeploying version:', error);
            alert('Error undeploying version');
            // Re-enable buttons
            buttons.forEach(btn => {
                btn.disabled = false;
                btn.innerHTML = 'Undeploy';
            });
        }
    }

    function scheduleRetraining(runId) {
        // Close the view modal to show the schedule modal
        close();

        // Open schedule modal for this training run
        if (typeof ScheduleModal !== 'undefined') {
            ScheduleModal.configure({
                modelId: config.modelId,
                onSuccess: function(schedule) {
                    // Show success modal
                    if (typeof TrainingCards !== 'undefined' && TrainingCards.showConfirmModal) {
                        TrainingCards.showConfirmModal({
                            title: 'Success',
                            message: `Schedule "${schedule.name}" created successfully`,
                            type: 'success',
                            confirmText: 'Close',
                            hideCancel: true,
                            autoClose: 4000,
                            onConfirm: () => {}
                        });
                    }

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
                const response = await fetch(appendModelEndpointId(url));
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
            const response = await fetch(appendModelEndpointId(url));
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
        document.querySelectorAll('.exp-view-pill').forEach(t => t.classList.remove('current'));
        const targetTab = document.querySelector(`.exp-view-pill[data-tab="${initialTab}"]`);
        if (targetTab) targetTab.classList.add('current');

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

        // Switch to legacy header, hide card sections
        showLegacyHeader();
        const cardSections = document.getElementById('expViewCardSections');
        if (cardSections) cardSections.style.display = 'none';

        // Model mode header: use "registered" status for green gradient + model-mode class
        const header = document.getElementById('expViewHeaderLegacy');
        header.className = `modal-header exp-view-header registered model-mode`;

        // Status panel - registered status
        const statusPanel = document.getElementById('expViewStatusPanel');
        statusPanel.className = `exp-view-status-panel registered`;

        // Status icon - green checkmark for registered models
        const statusIcon = document.getElementById('expViewStatusIcon');
        statusIcon.className = `exp-view-status-icon registered`;
        statusIcon.innerHTML = `<i class="fas fa-check"></i>`;

        // Title (Model name) - shown prominently with type badge below
        const titleEl = document.getElementById('expViewTitleLegacy');
        const modelType = (model.model_type || 'retrieval').toLowerCase();
        const badgeContents = {
            'retrieval': '<i class="fas fa-search"></i> Retrieval',
            'ranking': '<i class="fas fa-sort-amount-down"></i> Ranking',
            'multitask': '<i class="fas fa-layer-group"></i> Multitask'
        };
        // Set model name and add type badge inline below it
        titleEl.innerHTML = `
            <span class="exp-view-model-name-text">${model.vertex_model_name || 'Model'}</span>
            <span class="exp-view-model-type-inline ${modelType}">${badgeContents[modelType] || badgeContents['retrieval']}</span>
        `;

        // Hide version/run info for model mode (simplified header)
        const expNameEl = document.getElementById('expViewExpName');
        expNameEl.textContent = '';
        expNameEl.style.display = 'none';

        // Hide the separate type badge in header-info (we show it inline now)
        const typeBadgeEl = document.getElementById('expViewTypeBadge');
        typeBadgeEl.style.display = 'none';

        // Description - hidden
        const descEl = document.getElementById('expViewDescription');
        descEl.textContent = '';
        descEl.style.display = 'none';

        // Hide times for model mode (simplified header)
        const timesEl = document.querySelector('.exp-view-times');
        if (timesEl) timesEl.style.display = 'none';

        // Overview Tab - render model overview
        renderModelOverview(model);
    }

    function renderModelOverview(model) {
        // Reset accordion states when populating new data
        resetAccordionStates();

        // Dataset section - load full details like training runs
        // Load full dataset details using dataset_id
        if (model.dataset_id) {
            loadDatasetDetails(model.dataset_id);
        } else {
            document.getElementById('expViewDatasetDetails').innerHTML =
                '<div class="exp-view-no-filters">No dataset configured</div>';
        }

        // Features config - load full details like training runs
        // Load full features config details using feature_config_id
        if (model.feature_config_id) {
            loadFeaturesConfig(model.feature_config_id);
        } else {
            document.getElementById('expViewFeaturesConfigContent').innerHTML =
                '<div class="exp-view-no-filters">No features config</div>';
        }

        // Model config - load full details
        // Load full model config details using model_config_id
        if (model.model_config_id) {
            loadModelConfig(model.model_config_id);
        } else {
            document.getElementById('expViewModelConfigContent').innerHTML =
                '<div class="exp-view-no-filters">No model config</div>';
        }

        // Sampling & Training Parameters (card format)
        const trainingSetupCards = document.getElementById('expViewTrainingSetupCards');
        if (trainingSetupCards) {
            trainingSetupCards.innerHTML = renderModelSamplingCard(model) + renderModelTrainingParamsCard(model);
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
        const formatMetric = v => v != null ? v.toFixed(2) : 'N/A';
        const formatRecall = v => v != null ? (v * 100).toFixed(1) + '%' : 'N/A';

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
        } else if (model.model_type === 'multitask') {
            // Hybrid/Multitask models: R@50, R@100, Test RMSE, Test MAE
            metricsHtml = `
                <div class="exp-view-metric-card">
                    <div class="exp-view-metric-card-label">R@50</div>
                    <div class="exp-view-metric-card-value">${formatRecall(model.metrics.recall_at_50)}</div>
                </div>
                <div class="exp-view-metric-card">
                    <div class="exp-view-metric-card-label">R@100</div>
                    <div class="exp-view-metric-card-value">${formatRecall(model.metrics.recall_at_100)}</div>
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
            // Retrieval models: R@5, R@10, R@50, R@100
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

    function renderModelSamplingCard(model) {
        const params = model.training_params || {};
        const sampling = model.sampling_config || {};
        const stats = [];

        if (params.split_strategy) {
            stats.push({ label: 'Split Strategy', value: params.split_strategy });
        }

        if (params.train_fraction) {
            stats.push({ label: 'Train', value: `${(params.train_fraction * 100).toFixed(0)}%` });
        } else if (sampling.train_percent) {
            stats.push({ label: 'Train', value: `${sampling.train_percent}%` });
        }
        if (params.val_fraction) {
            stats.push({ label: 'Val', value: `${(params.val_fraction * 100).toFixed(0)}%` });
        } else if (sampling.val_percent) {
            stats.push({ label: 'Val', value: `${sampling.val_percent}%` });
        }
        if (params.test_fraction) {
            stats.push({ label: 'Test', value: `${(params.test_fraction * 100).toFixed(0)}%` });
        } else if (sampling.test_percent) {
            stats.push({ label: 'Test', value: `${sampling.test_percent}%` });
        }

        if (stats.length === 0) return '';

        return `
            <div class="exp-detail-section">
                <div class="exp-detail-section-title">Sampling</div>
                <div class="exp-detail-section-body">
                    <div class="exp-detail-section-icon sampling"><i class="fas fa-percentage"></i></div>
                    <div class="exp-detail-stats">
                        ${stats.map(s => `
                            <div class="exp-detail-stat-info">
                                <div class="stat-label">${s.label}</div>
                                <div class="stat-value">${s.value}</div>
                            </div>`).join('')}
                    </div>
                </div>
            </div>`;
    }

    function renderModelTrainingParamsCard(model) {
        const params = model.training_params || {};
        const gpuConfig = model.gpu_config || {};
        const stats = [];

        if (params.epochs) stats.push({ label: 'Epochs', value: params.epochs });
        if (params.batch_size) stats.push({ label: 'Batch Size', value: formatNumber(params.batch_size) });
        if (params.learning_rate) stats.push({ label: 'Learning Rate', value: params.learning_rate });

        // GPU config - support both naming conventions (gpu_type from training runs, accelerator_type from models)
        const gpuType = gpuConfig.gpu_type || gpuConfig.accelerator_type;
        if (gpuType) {
            stats.push({ label: 'GPU', value: gpuType.replace('NVIDIA_TESLA_', '').replace('NVIDIA_', '') });
        }
        if (gpuConfig.gpu_count) {
            stats.push({ label: 'GPU Count', value: gpuConfig.gpu_count });
        }
        if (gpuConfig.preemptible !== undefined) {
            stats.push({ label: 'Preemptible', value: gpuConfig.preemptible ? 'Yes' : 'No' });
        }

        if (stats.length === 0) return '';

        return `
            <div class="exp-detail-section">
                <div class="exp-detail-section-title">Training Parameters</div>
                <div class="exp-detail-section-body">
                    <div class="exp-detail-section-icon training"><i class="fas fa-cogs"></i></div>
                    <div class="exp-detail-stats">
                        ${stats.map(s => `
                            <div class="exp-detail-stat-info">
                                <div class="stat-label">${s.label}</div>
                                <div class="stat-value">${s.value}</div>
                            </div>`).join('')}
                    </div>
                </div>
            </div>`;
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
            const response = await fetch(appendModelEndpointId(`/api/models/${modelId}/versions/`));
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

    /**
     * Get KPI configuration based on model type
     */
    function getKpiConfigForModelType(modelType) {
        if (modelType === 'ranking') {
            return [
                { key: 'rmse', label: 'RMSE' },
                { key: 'mae', label: 'MAE' },
                { key: 'test_rmse', label: 'Test RMSE' },
                { key: 'test_mae', label: 'Test MAE' }
            ];
        } else if (modelType === 'multitask') {
            // Hybrid/Multitask: R@50, R@100, Test RMSE, Test MAE
            return [
                { key: 'recall_at_50', label: 'R@50' },
                { key: 'recall_at_100', label: 'R@100' },
                { key: 'test_rmse', label: 'Test RMSE' },
                { key: 'test_mae', label: 'Test MAE' }
            ];
        } else { // retrieval (default)
            return [
                { key: 'recall_at_5', label: 'R@5' },
                { key: 'recall_at_10', label: 'R@10' },
                { key: 'recall_at_50', label: 'R@50' },
                { key: 'recall_at_100', label: 'R@100' }
            ];
        }
    }

    /**
     * Render versions tab with visual KPI design
     */
    function renderVersionsTab(modelName, versions) {
        const container = document.getElementById('expViewTabVersions');
        if (!container) return;

        // Limit to 10 most recent versions
        const limitedVersions = versions.slice(0, 10);

        // Get model type from first version or current model
        const modelType = limitedVersions[0]?.model_type || state.currentModel?.model_type || 'retrieval';
        const kpiConfig = getKpiConfigForModelType(modelType);

        const formatDate = (isoStr) => {
            if (!isoStr) return '-';
            return new Date(isoStr).toLocaleDateString('en-US', {
                month: 'short', day: 'numeric', year: 'numeric'
            });
        };

        const formatMetric = (value) => {
            if (value === null || value === undefined) return '-';
            return parseFloat(value).toFixed(3);
        };

        // Build version cards HTML
        let versionCardsHtml = limitedVersions.map((v, idx) => {
            const versionNum = v.vertex_model_version || (versions.length - idx);
            const metrics = v.metrics || {};

            const kpiBoxesHtml = kpiConfig.map(kpi => `
                <div class="version-kpi-box">
                    <div class="version-kpi-label">${kpi.label}</div>
                    <div class="version-kpi-value">${formatMetric(metrics[kpi.key])}</div>
                </div>
            `).join('');

            // Build deployment status and button for header
            const isDeployed = v.model_status === 'deployed' && v.deployed_endpoint_info;
            const endpointInfo = v.deployed_endpoint_info;
            let deploymentStatusHtml;
            let deployButtonHtml = '';

            if (isDeployed) {
                deploymentStatusHtml = `
                    <div class="version-deployment-status deployed">
                        <i class="fas fa-check-circle"></i>
                        <span>Deployed to <span class="endpoint-name">${endpointInfo.service_name}</span></span>
                    </div>
                `;
                // Show Undeploy button only if configured
                if (config.showVersionDeployButtons) {
                    deployButtonHtml = `
                        <button class="version-undeploy-btn" onclick="event.stopPropagation(); ExpViewModal.undeployVersion(${endpointInfo.id}, ${v.id})">
                            Undeploy
                        </button>
                    `;
                }
            } else {
                deploymentStatusHtml = `
                    <div class="version-deployment-status not-deployed">
                        <i class="fas fa-circle"></i>
                        <span>Not deployed</span>
                    </div>
                `;
                // Show Deploy button only if configured
                if (config.showVersionDeployButtons) {
                    deployButtonHtml = `
                        <button class="version-deploy-btn" onclick="event.stopPropagation(); ExpViewModal.deployVersion(${v.id})">
                            Deploy
                        </button>
                    `;
                }
            }

            return `
                <div class="version-card ${isDeployed ? 'deployed' : ''}" onclick="ExpViewModal.selectModelVersion(${v.id})" style="cursor: pointer;">
                    <div class="version-card-header ${isDeployed ? 'deployed' : ''}">
                        <div class="version-card-info">
                            <span class="version-badge">
                                <i class="fas fa-code-branch"></i>
                                v${versionNum}
                            </span>
                            <span class="version-run">Run #${v.run_number}</span>
                            <span class="version-date">${formatDate(v.registered_at)}</span>
                            ${deploymentStatusHtml}
                        </div>
                        ${deployButtonHtml}
                    </div>
                    <div class="version-kpis">
                        ${kpiBoxesHtml}
                    </div>
                </div>
            `;
        }).join('');

        container.innerHTML = `
            <div class="versions-tab-content">
                <div class="versions-chart-section">
                    <h4>KPI Trends Across Versions</h4>
                    <div class="versions-chart-container">
                        <canvas id="versionsKpiChart"></canvas>
                    </div>
                </div>
                <div class="versions-list-section">
                    <h4>Version Details</h4>
                    ${versionCardsHtml}
                </div>
            </div>
        `;

        // Render the chart after DOM is ready
        setTimeout(() => {
            renderVersionsChart(limitedVersions, kpiConfig);
        }, 0);
    }

    /**
     * Check if a KPI key represents a recall (accuracy) metric
     */
    function isRecallMetric(kpiKey) {
        return kpiKey.startsWith('recall_at_');
    }

    /**
     * Render grouped bar chart for version KPIs
     */
    function renderVersionsChart(versions, kpiConfig) {
        const canvas = document.getElementById('versionsKpiChart');
        if (!canvas) return;

        // Destroy existing chart
        if (charts.versionsChart) {
            charts.versionsChart.destroy();
            charts.versionsChart = null;
        }

        // Determine chart mode based on metric types
        const hasRecallMetrics = kpiConfig.some(kpi => isRecallMetric(kpi.key));
        const hasErrorMetrics = kpiConfig.some(kpi => !isRecallMetric(kpi.key));
        const chartMode = hasRecallMetrics && hasErrorMetrics ? 'dual' :
                          hasRecallMetrics ? 'recall' : 'error';

        // Take up to 5 versions for chart, reverse to oldest→newest
        const chartVersions = versions.slice(0, 5).reverse();

        // Color schemes
        const blueColors = ['#bfdbfe', '#93c5fd', '#60a5fa', '#3b82f6', '#2563eb'];
        const amberColors = ['#fef3c7', '#fde68a', '#fcd34d', '#f59e0b', '#d97706'];

        // Build datasets
        let datasets;

        if (chartMode === 'dual') {
            // For dual-axis mode, split each version into two datasets:
            // one for recall metrics (left axis) and one for error metrics (right axis)
            datasets = [];
            chartVersions.forEach((v, idx) => {
                const versionNum = v.vertex_model_version || (versions.length - (versions.indexOf(v)));
                const metrics = v.metrics || {};

                // Recall dataset (left Y-axis) - use null for error metric positions
                datasets.push({
                    label: `v${versionNum}`,
                    data: kpiConfig.map(kpi => {
                        if (isRecallMetric(kpi.key)) {
                            return (metrics[kpi.key] || 0) * 100;
                        }
                        return null;
                    }),
                    backgroundColor: blueColors[idx] || blueColors[blueColors.length - 1],
                    borderColor: blueColors[idx] || blueColors[blueColors.length - 1],
                    borderWidth: 1,
                    borderRadius: 3,
                    barPercentage: 0.8,
                    categoryPercentage: 0.7,
                    yAxisID: 'y'
                });

                // Error dataset (right Y-axis) - use null for recall metric positions
                datasets.push({
                    label: `v${versionNum}`,
                    data: kpiConfig.map(kpi => {
                        if (!isRecallMetric(kpi.key)) {
                            return metrics[kpi.key] || 0;
                        }
                        return null;
                    }),
                    backgroundColor: amberColors[idx] || amberColors[amberColors.length - 1],
                    borderColor: amberColors[idx] || amberColors[amberColors.length - 1],
                    borderWidth: 1,
                    borderRadius: 3,
                    barPercentage: 0.8,
                    categoryPercentage: 0.7,
                    yAxisID: 'y2'
                });
            });
        } else {
            // Single-axis modes
            datasets = chartVersions.map((v, idx) => {
                const versionNum = v.vertex_model_version || (versions.length - (versions.indexOf(v)));
                const metrics = v.metrics || {};

                if (chartMode === 'recall') {
                    // Convert recall values to percentages
                    return {
                        label: `v${versionNum}`,
                        data: kpiConfig.map(kpi => (metrics[kpi.key] || 0) * 100),
                        backgroundColor: blueColors[idx] || blueColors[blueColors.length - 1],
                        borderColor: blueColors[idx] || blueColors[blueColors.length - 1],
                        borderWidth: 1,
                        borderRadius: 3,
                        barPercentage: 0.8,
                        categoryPercentage: 0.7
                    };
                } else {
                    // Error-only mode - keep values as-is
                    return {
                        label: `v${versionNum}`,
                        data: kpiConfig.map(kpi => metrics[kpi.key] || 0),
                        backgroundColor: blueColors[idx] || blueColors[blueColors.length - 1],
                        borderColor: blueColors[idx] || blueColors[blueColors.length - 1],
                        borderWidth: 1,
                        borderRadius: 3,
                        barPercentage: 0.8,
                        categoryPercentage: 0.7
                    };
                }
            });
        }

        // Build scales configuration based on chart mode
        let scales;
        if (chartMode === 'dual') {
            scales = {
                x: {
                    grid: { display: false },
                    ticks: { font: chartDefaults.font.axis }
                },
                y: {
                    position: 'left',
                    beginAtZero: true,
                    grace: '5%',
                    grid: { color: '#f3f4f6' },
                    ticks: {
                        font: chartDefaults.font.axis,
                        color: '#3b82f6',
                        callback: function(value) {
                            return value + '%';
                        }
                    },
                    title: {
                        display: true,
                        text: 'Recall',
                        color: '#3b82f6',
                        font: { size: 11, weight: '500' }
                    }
                },
                y2: {
                    position: 'right',
                    beginAtZero: true,
                    grace: '5%',
                    grid: { drawOnChartArea: false },
                    ticks: {
                        font: chartDefaults.font.axis,
                        color: '#f59e0b',
                        callback: function(value) {
                            return value.toFixed(2);
                        }
                    },
                    title: {
                        display: true,
                        text: 'Error',
                        color: '#f59e0b',
                        font: { size: 11, weight: '500' }
                    }
                }
            };
        } else if (chartMode === 'recall') {
            scales = {
                x: {
                    grid: { display: false },
                    ticks: { font: chartDefaults.font.axis }
                },
                y: {
                    beginAtZero: true,
                    grace: '5%',
                    grid: { color: '#f3f4f6' },
                    ticks: {
                        font: chartDefaults.font.axis,
                        callback: function(value) {
                            return value + '%';
                        }
                    }
                }
            };
        } else {
            // Error-only mode
            scales = {
                x: {
                    grid: { display: false },
                    ticks: { font: chartDefaults.font.axis }
                },
                y: {
                    beginAtZero: true,
                    grace: '5%',
                    grid: { color: '#f3f4f6' },
                    ticks: {
                        font: chartDefaults.font.axis,
                        callback: function(value) {
                            return value.toFixed(2);
                        }
                    }
                }
            };
        }

        const ctx = canvas.getContext('2d');

        // For all model types: KPIs on X-axis, versions as separate colored datasets
        charts.versionsChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: kpiConfig.map(kpi => kpi.label),
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                layout: chartDefaults.layout,
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom',
                        labels: {
                            ...chartDefaults.legend.labels,
                            usePointStyle: false,
                            boxWidth: 12,
                            boxHeight: 12,
                            // In dual mode, filter out duplicate version labels (show only recall/blue datasets)
                            filter: chartMode === 'dual'
                                ? (item, data) => item.datasetIndex % 2 === 0
                                : undefined
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const value = context.raw;
                                if (value === null) return null; // Skip null values in dual mode
                                const kpiKey = kpiConfig[context.dataIndex]?.key || '';
                                // Format based on metric type (values already converted for display)
                                if (isRecallMetric(kpiKey)) {
                                    return `${context.dataset.label}: ${value.toFixed(1) + '%'}`;
                                }
                                return `${context.dataset.label}: ${value.toFixed(3)}`;
                            }
                        }
                    }
                },
                scales: scales
            }
        });
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
            const response = await fetch(appendModelEndpointId(`/api/models/${modelId}/lineage/`));
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

    // =============================================================================
    // ENDPOINT MODE FUNCTIONS
    // =============================================================================

    async function openForEndpoint(endpointId) {
        state.mode = 'endpoint';

        try {
            const url = `/api/deployed-endpoints/${endpointId}/`;
            const response = await fetch(appendModelEndpointId(url));
            const data = await response.json();

            if (!data.success) {
                console.error('Failed to load endpoint:', data.error);
                return;
            }

            openWithEndpointData(data.endpoint);
        } catch (error) {
            console.error('Error loading endpoint details:', error);
        }
    }

    function openWithEndpointData(endpoint) {
        state.mode = 'endpoint';
        state.endpointId = endpoint.id;
        state.currentEndpoint = endpoint;

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
        state.currentTab = 'overview';

        // Reset tabs
        document.querySelectorAll('.exp-view-pill').forEach(t => t.classList.remove('current'));
        const targetTab = document.querySelector(`.exp-view-pill[data-tab="overview"]`);
        if (targetTab) targetTab.classList.add('current');

        document.querySelectorAll('.exp-view-tab-content').forEach(c => c.classList.remove('active'));
        const targetContent = document.getElementById('expViewTabOverview');
        if (targetContent) targetContent.classList.add('active');

        // Update visible tabs for endpoint mode
        updateVisibleTabs();

        // Populate modal with endpoint data
        populateEndpointModal(endpoint);
        document.getElementById('expViewModal').classList.remove('hidden');
    }

    function populateEndpointModal(endpoint) {
        // Store current endpoint for tab data loading
        window.currentViewEndpoint = endpoint;

        // Switch to legacy header, hide card sections
        showLegacyHeader();
        const cardSections = document.getElementById('expViewCardSections');
        if (cardSections) cardSections.style.display = 'none';

        // Endpoint mode header: use active/inactive status + endpoint-mode class
        const header = document.getElementById('expViewHeaderLegacy');
        const statusClass = endpoint.is_active ? 'active' : 'inactive';
        header.className = `modal-header exp-view-header endpoint-mode ${statusClass}`;

        // Nav bar color matches header status
        const navBar = document.getElementById('expViewNavBar');
        if (navBar) {
            navBar.className = `exp-view-nav-bar exp-nav-endpoint-${statusClass}`;
        }

        // Status panel
        const statusPanel = document.getElementById('expViewStatusPanel');
        statusPanel.className = `exp-view-status-panel ${statusClass}`;

        // Status icon - checkmark for active, pause for inactive
        const statusIcon = document.getElementById('expViewStatusIcon');
        const iconClass = endpoint.is_active ? 'endpoint-active' : 'endpoint-inactive';
        const iconSymbol = endpoint.is_active ? 'fa-check' : 'fa-pause';
        statusIcon.className = `exp-view-status-icon ${iconClass}`;
        statusIcon.innerHTML = `<i class="fas ${iconSymbol}"></i>`;

        // Title (Endpoint name) - shown prominently with status badge below
        const titleEl = document.getElementById('expViewTitleLegacy');
        const statusText = endpoint.is_active ? 'Active' : 'Inactive';
        const statusBadge = endpoint.is_active
            ? '<i class="fas fa-check-circle"></i> ACTIVE'
            : '<i class="fas fa-pause-circle"></i> INACTIVE';

        titleEl.innerHTML = `
            <span class="exp-view-endpoint-name-text">${endpoint.service_name || 'Endpoint'}</span>
            <span class="exp-view-endpoint-status-inline ${statusClass}">${statusBadge}</span>
        `;

        // Hide version/run info for endpoint mode (simplified header)
        const expNameEl = document.getElementById('expViewExpName');
        expNameEl.textContent = '';
        expNameEl.style.display = 'none';

        // Hide the separate type badge in header-info
        const typeBadgeEl = document.getElementById('expViewTypeBadge');
        typeBadgeEl.style.display = 'none';

        // Description - hidden
        const descEl = document.getElementById('expViewDescription');
        descEl.textContent = '';
        descEl.style.display = 'none';

        // Hide times for endpoint mode (simplified header)
        const timesEl = document.querySelector('.exp-view-times');
        if (timesEl) timesEl.style.display = 'none';

        // Overview Tab - render endpoint overview
        renderEndpointOverview(endpoint);
    }

    function renderEndpointOverview(endpoint) {
        // Hide standard accordions for endpoint mode - use simplified view
        const regDeploySection = document.getElementById('expViewRegistryDeploymentSection');
        if (regDeploySection) regDeploySection.style.display = 'none';

        // Use alternative approach - hide by finding parent accordions
        document.querySelectorAll('.exp-view-accordion').forEach(acc => {
            acc.style.display = 'none';
        });

        // Hide features config section (no longer an accordion)
        const featuresConfigContent = document.getElementById('expViewFeaturesConfigContent');
        if (featuresConfigContent) featuresConfigContent.style.display = 'none';

        // Hide results summary (we'll render our own)
        const resultsSummary = document.getElementById('expViewResultsSummary');
        if (resultsSummary) resultsSummary.classList.add('hidden');

        // Build custom endpoint overview content in the Overview tab
        const overviewTab = document.getElementById('expViewTabOverview');
        if (!overviewTab) return;

        const config = endpoint.deployment_config || {};
        const modelType = endpoint.model_type || 'retrieval';
        const metrics = endpoint.metrics || {};

        // Build Results section HTML based on model type
        let resultsHtml = '';
        if (metrics && Object.keys(metrics).length > 0) {
            const formatRecall = v => v != null ? (v * 100).toFixed(1) + '%' : 'N/A';
            const formatRMSE = v => v != null ? v.toFixed(2) : 'N/A';

            let metricsStats = '';

            if (modelType === 'ranking') {
                metricsStats = `
                    <div class="exp-detail-stat">
                        <div class="exp-detail-stat-value">${formatRMSE(metrics.rmse)}</div>
                        <div class="exp-detail-stat-label">RMSE</div>
                    </div>
                    <div class="exp-detail-stat">
                        <div class="exp-detail-stat-value">${formatRMSE(metrics.mae)}</div>
                        <div class="exp-detail-stat-label">MAE</div>
                    </div>
                    <div class="exp-detail-stat">
                        <div class="exp-detail-stat-value">${formatRMSE(metrics.test_rmse)}</div>
                        <div class="exp-detail-stat-label">Test RMSE</div>
                    </div>
                    <div class="exp-detail-stat">
                        <div class="exp-detail-stat-value">${formatRMSE(metrics.test_mae)}</div>
                        <div class="exp-detail-stat-label">Test MAE</div>
                    </div>`;
            } else if (modelType === 'multitask') {
                metricsStats = `
                    <div class="exp-detail-stat">
                        <div class="exp-detail-stat-value">${formatRecall(metrics.recall_at_50)}</div>
                        <div class="exp-detail-stat-label">R@50</div>
                    </div>
                    <div class="exp-detail-stat">
                        <div class="exp-detail-stat-value">${formatRecall(metrics.recall_at_100)}</div>
                        <div class="exp-detail-stat-label">R@100</div>
                    </div>
                    <div class="exp-detail-stat">
                        <div class="exp-detail-stat-value">${formatRMSE(metrics.test_rmse)}</div>
                        <div class="exp-detail-stat-label">Test RMSE</div>
                    </div>
                    <div class="exp-detail-stat">
                        <div class="exp-detail-stat-value">${formatRMSE(metrics.test_mae)}</div>
                        <div class="exp-detail-stat-label">Test MAE</div>
                    </div>`;
            } else {
                metricsStats = `
                    <div class="exp-detail-stat">
                        <div class="exp-detail-stat-value">${formatRecall(metrics.recall_at_5)}</div>
                        <div class="exp-detail-stat-label">Recall@5</div>
                    </div>
                    <div class="exp-detail-stat">
                        <div class="exp-detail-stat-value">${formatRecall(metrics.recall_at_10)}</div>
                        <div class="exp-detail-stat-label">Recall@10</div>
                    </div>
                    <div class="exp-detail-stat">
                        <div class="exp-detail-stat-value">${formatRecall(metrics.recall_at_50)}</div>
                        <div class="exp-detail-stat-label">Recall@50</div>
                    </div>
                    <div class="exp-detail-stat">
                        <div class="exp-detail-stat-value">${formatRecall(metrics.recall_at_100)}</div>
                        <div class="exp-detail-stat-label">Recall@100</div>
                    </div>`;
            }

            resultsHtml = `
                <div class="exp-detail-section">
                    <div class="exp-detail-section-title">Results</div>
                    <div class="exp-detail-section-body">
                        <div class="exp-detail-section-icon results"><i class="fas fa-chart-bar"></i></div>
                        <div class="exp-detail-stats">
                            ${metricsStats}
                        </div>
                    </div>
                </div>`;
        }

        // Build the overview HTML
        let overviewHtml = `
            <div style="display: flex; flex-direction: column; gap: 16px;">
            ${resultsHtml}

            <!-- Service URL Section -->
            <div class="exp-detail-section">
                <div class="exp-detail-section-title">Service URL</div>
                <div class="exp-detail-section-body">
                    <div class="exp-detail-section-icon url"><i class="fas fa-link"></i></div>
                    <div class="exp-detail-stats">
                        <div class="exp-detail-stat-info" style="flex: 1;">
                            <div class="stat-label">Endpoint</div>
                            <div class="stat-value">
                                <div class="exp-detail-url-row">
                                    <code>${endpoint.service_url || 'N/A'}</code>
                                    <button class="exp-view-copy-btn" onclick="ExpViewModal.copyToClipboard('${endpoint.service_url || ''}')">
                                        <i class="fas fa-copy"></i>
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Model Information Card -->
            <div class="exp-detail-section">
                <div class="exp-detail-section-title">Model Information</div>
                <div class="exp-detail-section-body">
                    <div class="exp-detail-section-icon info"><i class="fas fa-info-circle"></i></div>
                    <div class="exp-detail-stats">
                        <div class="exp-detail-stat-info">
                            <div class="stat-label">Model</div>
                            <div class="stat-value">${endpoint.model_name || '-'}</div>
                        </div>
                        <div class="exp-detail-stat-info">
                            <div class="stat-label">Type</div>
                            <div class="stat-value">${modelType.charAt(0).toUpperCase() + modelType.slice(1)}</div>
                        </div>
                        <div class="exp-detail-stat-info">
                            <div class="stat-label">Version</div>
                            <div class="stat-value">v${endpoint.deployed_version || '-'}</div>
                        </div>
                        <div class="exp-detail-stat-info">
                            <div class="stat-label">Run #</div>
                            <div class="stat-value">${endpoint.run_number || '-'}</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Hardware Configuration Card -->
            <div class="exp-detail-section">
                <div class="exp-detail-section-title">Hardware Configuration</div>
                <div class="exp-detail-section-body">
                    <div class="exp-detail-section-icon hardware"><i class="fas fa-server"></i></div>
                    <div class="exp-detail-stats">
                        <div class="exp-detail-stat-info">
                            <div class="stat-label">Memory</div>
                            <div class="stat-value">${config.memory || '4Gi'}</div>
                        </div>
                        <div class="exp-detail-stat-info">
                            <div class="stat-label">CPU</div>
                            <div class="stat-value">${config.cpu || '2'}</div>
                        </div>
                        <div class="exp-detail-stat-info">
                            <div class="stat-label">Min Instances</div>
                            <div class="stat-value">${config.min_instances !== undefined ? config.min_instances : '0'}</div>
                        </div>
                        <div class="exp-detail-stat-info">
                            <div class="stat-label">Max Instances</div>
                            <div class="stat-value">${config.max_instances || '10'}</div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Add advanced deployment params if present
        if (config.timeout_seconds || config.concurrency || config.gpu_type) {
            overviewHtml += `
            <div class="exp-detail-section">
                <div class="exp-detail-section-title">Advanced Parameters</div>
                <div class="exp-detail-section-body">
                    <div class="exp-detail-section-icon params"><i class="fas fa-sliders-h"></i></div>
                    <div class="exp-detail-stats">
                        ${config.timeout_seconds ? `
                        <div class="exp-detail-stat-info">
                            <div class="stat-label">Timeout</div>
                            <div class="stat-value">${config.timeout_seconds}s</div>
                        </div>` : ''}
                        ${config.concurrency ? `
                        <div class="exp-detail-stat-info">
                            <div class="stat-label">Concurrency</div>
                            <div class="stat-value">${config.concurrency}</div>
                        </div>` : ''}
                        ${config.gpu_type ? `
                        <div class="exp-detail-stat-info">
                            <div class="stat-label">GPU</div>
                            <div class="stat-value">${config.gpu_type}</div>
                        </div>` : ''}
                    </div>
                </div>
            </div>`;
        }

        overviewHtml += `</div>`; // close flex container

        overviewTab.innerHTML = overviewHtml;
    }

    function renderEndpointLogsTab(endpoint) {
        const container = document.getElementById('expViewTabLogs');
        if (!container) return;

        const serviceName = endpoint.service_name || endpoint.name || 'Unknown';

        container.innerHTML = `
            <div style="padding: 16px 0;">
                <div class="component-logs-card" id="endpointLogsCard">
                    <div class="component-logs-card-header" onclick="ExpViewModal.toggleEndpointLogs()">
                        <div class="component-logs-card-header-left">
                            <div class="component-logs-card-icon"><i class="fas fa-stream"></i></div>
                            <div class="component-logs-card-title">Logs ${serviceName}</div>
                        </div>
                        <div class="component-logs-card-actions">
                            <button class="btn btn-primary" id="endpointLoadLogsBtn"
                                    onclick="event.stopPropagation(); ExpViewModal.loadEndpointLogs()"
                                    style="white-space: nowrap; min-width: auto; padding: 8px 18px; font-size: 13px;">
                                <i class="fas fa-sync-alt"></i> Load Logs
                            </button>
                            <div class="component-logs-card-toggle">
                                <i class="fas fa-chevron-right"></i>
                            </div>
                        </div>
                    </div>
                    <div class="component-logs-card-content">
                        <div class="component-logs-card-divider"></div>
                        <div class="exp-view-logs-container" id="endpointLogsContainer">
                            <div class="logs-empty-state">
                                <div class="logs-empty-icon">
                                    <i class="fas fa-terminal"></i>
                                </div>
                                <p class="logs-empty-title">No logs loaded</p>
                                <p class="logs-empty-subtitle">Click "Load Logs" to fetch recent entries from Cloud Run</p>
                            </div>
                        </div>
                        <div class="component-logs-card-footer">
                            <div class="logs-legend">
                                <span class="logs-legend-item"><span class="logs-severity-dot INFO"></span> Info</span>
                                <span class="logs-legend-item"><span class="logs-severity-dot WARNING"></span> Warning</span>
                                <span class="logs-legend-item"><span class="logs-severity-dot ERROR"></span> Error</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    function toggleEndpointLogs() {
        const card = document.getElementById('endpointLogsCard');
        if (card) {
            card.classList.toggle('logs-open');
        }
    }

    async function loadEndpointLogs() {
        const endpoint = state.currentEndpoint;
        if (!endpoint) return;

        const container = document.getElementById('endpointLogsContainer');
        const btn = document.getElementById('endpointLoadLogsBtn');
        if (!container || !btn) return;

        // Show loading state
        container.innerHTML = `
            <div class="logs-loading-state">
                <i class="fas fa-circle-notch fa-spin"></i>
                <span>Fetching logs from Cloud Run...</span>
            </div>
        `;
        btn.disabled = true;
        btn.querySelector('i').classList.add('fa-spin');

        try {
            const response = await fetch(appendModelEndpointId(`/api/deployed-endpoints/${endpoint.id}/logs/?limit=100`));
            const data = await response.json();

            if (data.success && data.logs.available) {
                const logCount = data.logs.logs.length;
                // Render log entries with count header
                container.innerHTML = `
                    <div class="logs-count-header">
                        <span class="logs-count-badge">${logCount}</span>
                        <span>log entries</span>
                    </div>
                    <div class="logs-entries-list">
                        ${data.logs.logs.map(log => {
                            const severityClass = log.severity === 'DEFAULT' ? 'INFO' : log.severity.toUpperCase();
                            return `
                                <div class="log-entry ${severityClass.toLowerCase()}">
                                    <span class="log-severity-indicator ${severityClass}"></span>
                                    <span class="log-timestamp">${log.timestamp}</span>
                                    <span class="log-message">${escapeHtml(log.message)}</span>
                                </div>
                            `;
                        }).join('')}
                    </div>
                `;
                // Auto-expand the logs card
                const card = document.getElementById('endpointLogsCard');
                if (card) card.classList.add('logs-open');
            } else {
                // Show message
                const message = data.logs?.message || data.error || 'No logs available';
                container.innerHTML = `
                    <div class="logs-empty-state">
                        <div class="logs-empty-icon">
                            <i class="fas fa-inbox"></i>
                        </div>
                        <p class="logs-empty-title">No logs available</p>
                        <p class="logs-empty-subtitle">${escapeHtml(message)}</p>
                    </div>
                `;
            }
        } catch (error) {
            console.error('Error loading endpoint logs:', error);
            container.innerHTML = `
                <div class="logs-error-state">
                    <div class="logs-error-icon">
                        <i class="fas fa-exclamation-triangle"></i>
                    </div>
                    <p class="logs-error-title">Failed to load logs</p>
                    <p class="logs-error-subtitle">Please try again or check your connection</p>
                </div>
            `;
        } finally {
            btn.disabled = false;
            const btnIcon = btn.querySelector('i');
            if (btnIcon) {
                btnIcon.classList.remove('fa-spin');
            }
        }
    }

    async function loadEndpointVersions(endpointId) {
        const container = document.getElementById('expViewTabVersions');
        if (!container) return;

        container.innerHTML = `
            <div class="exp-view-loading">
                <i class="fas fa-spinner fa-spin"></i>
                <span>Loading versions...</span>
            </div>
        `;

        try {
            const response = await fetch(appendModelEndpointId(`/api/deployed-endpoints/${endpointId}/versions/`));
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
            console.error('Error loading endpoint versions:', error);
            container.innerHTML = `
                <div class="exp-view-data-message">
                    <i class="fas fa-exclamation-circle"></i>
                    <span>Error loading versions</span>
                </div>
            `;
        }
    }

    async function deployModel(modelId) {
        // Use the DeployWizard modal instead of confirm dialog
        if (typeof DeployWizard !== 'undefined') {
            DeployWizard.open(modelId);
            return;
        }

        // Fallback to simple confirm if DeployWizard is not available
        if (!confirm('Are you sure you want to deploy this model?')) return;

        try {
            const response = await fetch(appendModelEndpointId(`/api/models/${modelId}/deploy/`), {
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
            const response = await fetch(appendModelEndpointId(`/api/models/${modelId}/undeploy/`), {
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

        // Reset endpoint state
        state.endpointId = null;
        state.currentEndpoint = null;

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
            visibleTabs = ['overview', 'versions', 'artifacts', 'deployment'];
        } else if (state.mode === 'endpoint') {
            visibleTabs = ['overview', 'versions', 'logs'];
        } else if (state.mode === 'experiment') {
            visibleTabs = ['overview', 'pipeline', 'data', 'training'];
        } else {
            // Fallback to config for unknown modes
            visibleTabs = config.showTabs;
        }

        const allTabs = tabContainer.querySelectorAll('.exp-view-pill');
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

    function showNewHeader() {
        document.getElementById('expViewHeader').style.display = '';
        document.getElementById('expViewHeaderLegacy').style.display = 'none';
    }

    function showLegacyHeader() {
        document.getElementById('expViewHeader').style.display = 'none';
        document.getElementById('expViewHeaderLegacy').style.display = '';
        // Show dataset section for legacy modes
        const dsAccordion = document.getElementById('expViewDatasetAccordion');
        if (dsAccordion) dsAccordion.style.display = 'flex';
    }

    function computeDuration(startedAt, completedAt) {
        if (!startedAt || !completedAt) return null;
        const start = new Date(startedAt);
        const end = new Date(completedAt);
        const diffMs = end - start;
        if (diffMs < 0) return null;
        return Math.floor(diffMs / 1000);
    }

    function renderResultsCard(metrics, configType) {
        const container = document.getElementById('expCardMetricsContainer');
        if (!container) return;

        const formatRecall = v => v != null ? (v * 100).toFixed(1) + '%' : 'N/A';
        const formatRMSE = v => v != null ? v.toFixed(2) : 'N/A';

        function renderMetricGrid(items) {
            return `<div class="exp-metrics-grid">${items.map(item => `
                <div class="exp-metric-card">
                    <div class="exp-metric-card-label">${item.label}</div>
                    <div class="exp-metric-card-value">${item.format(item.value)}</div>
                </div>
            `).join('')}</div>`;
        }

        if (configType === 'multitask') {
            const retrievalItems = [
                { label: 'Recall@5', value: metrics['recall_at_5'], format: formatRecall },
                { label: 'Recall@10', value: metrics['recall_at_10'], format: formatRecall },
                { label: 'Recall@50', value: metrics['recall_at_50'], format: formatRecall },
                { label: 'Recall@100', value: metrics['recall_at_100'], format: formatRecall }
            ];
            const rmse = metrics['rmse'] ?? metrics['final_val_rmse'] ?? metrics['final_rmse'];
            const mae = metrics['mae'] ?? metrics['final_val_mae'] ?? metrics['final_mae'];
            const testRmse = metrics['test_rmse'];
            const testMae = metrics['test_mae'];
            const rankingItems = [
                { label: 'RMSE', value: rmse, format: formatRMSE },
                { label: 'Test RMSE', value: testRmse, format: formatRMSE },
                { label: 'MAE', value: mae, format: formatRMSE },
                { label: 'Test MAE', value: testMae, format: formatRMSE }
            ];
            container.innerHTML = `
                <div class="exp-metrics-group-title"><i class="fas fa-search"></i> Retrieval Metrics</div>
                ${renderMetricGrid(retrievalItems)}
                <div class="exp-metrics-divider"></div>
                <div class="exp-metrics-group-title"><i class="fas fa-star"></i> Ranking Metrics</div>
                ${renderMetricGrid(rankingItems)}
            `;
        } else if (configType === 'ranking') {
            const rmse = metrics['rmse'] ?? metrics['final_val_rmse'] ?? metrics['final_rmse'];
            const mae = metrics['mae'] ?? metrics['final_val_mae'] ?? metrics['final_mae'];
            const testRmse = metrics['test_rmse'];
            const testMae = metrics['test_mae'];
            const items = [
                { label: 'RMSE', value: rmse, format: formatRMSE },
                { label: 'Test RMSE', value: testRmse, format: formatRMSE },
                { label: 'MAE', value: mae, format: formatRMSE },
                { label: 'Test MAE', value: testMae, format: formatRMSE }
            ];
            container.innerHTML = renderMetricGrid(items);
        } else {
            const items = [
                { label: 'Recall@5', value: metrics['recall_at_5'], format: formatRecall },
                { label: 'Recall@10', value: metrics['recall_at_10'], format: formatRecall },
                { label: 'Recall@50', value: metrics['recall_at_50'], format: formatRecall },
                { label: 'Recall@100', value: metrics['recall_at_100'], format: formatRecall }
            ];
            container.innerHTML = renderMetricGrid(items);
        }
    }

    function populateModal(exp) {
        // Store current exp for tab data loading
        window.currentViewExp = exp;

        // Show new header, hide legacy
        showNewHeader();

        // New header: status gradient
        const header = document.getElementById('expViewHeader');
        header.className = `modal-header-soft soft-exp-${exp.status}`;

        // Icon badge — flask for experiments
        const iconBadge = header.querySelector('.modal-header-icon-badge');
        if (iconBadge) iconBadge.innerHTML = '<i class="fas fa-flask"></i>';

        // Nav bar status color
        const navBar = document.getElementById('expViewNavBar');
        if (navBar) {
            const statusMap = { completed: 'completed', failed: 'failed', running: 'running',
                submitting: 'running', pending: 'pending', cancelled: 'cancelled', registered: 'completed' };
            const navStatus = statusMap[exp.status] || 'pending';
            navBar.className = `exp-view-nav-bar exp-nav-${navStatus}`;
        }

        // Status badge (circle)
        const statusBadge = document.getElementById('expViewStatusBadge');
        const statusIcons = {
            'submitting': 'fa-sync fa-spin',
            'running': 'fa-sync fa-spin',
            'completed': 'fa-check',
            'failed': 'fa-times',
            'cancelled': 'fa-ban',
            'pending': 'fa-clock'
        };
        statusBadge.className = `modal-header-status-circle ${exp.status}`;
        statusBadge.innerHTML = `<i class="fas ${statusIcons[exp.status] || 'fa-circle'}"></i>`;

        // Title: "Exp #N · name" or just "Exp #N"
        const expName = exp.experiment_name || '';
        const titleText = expName ? `Exp #${exp.id} \u00b7 ${expName}` : (exp.display_name || `Exp #${exp.id}`);
        document.getElementById('expViewTitle').textContent = titleText;

        // Subtitle
        document.getElementById('expViewSubtitle').textContent = 'Experiment overview';

        // Show card sections, hide legacy results summary
        const cardSections = document.getElementById('expViewCardSections');
        if (cardSections) cardSections.style.display = '';
        const resultsSummary = document.getElementById('expViewResultsSummary');
        if (resultsSummary) resultsSummary.classList.add('hidden');

        // Card 1: Experiment Information
        const modelType = (exp.model_type || exp.feature_config_type || 'retrieval').toLowerCase();
        const badgeContents = {
            'retrieval': '<i class="fas fa-search"></i> Retrieval',
            'ranking': '<i class="fas fa-sort-amount-down"></i> Ranking',
            'multitask': '<i class="fas fa-layer-group"></i> Retrieval / Ranking'
        };

        const nameCard = document.getElementById('expCardName');
        if (nameCard) nameCard.querySelector('.stat-value').textContent = expName || '\u2014';

        const typeCard = document.getElementById('expCardModelType');
        if (typeCard) {
            typeCard.querySelector('.stat-value').innerHTML =
                `<span class="exp-detail-type-badge ${modelType}">${badgeContents[modelType] || badgeContents['retrieval']}</span>`;
        }

        const descCard = document.getElementById('expCardDescription');
        if (descCard) {
            const desc = exp.experiment_description || '\u2014';
            descCard.querySelector('.stat-value').textContent = desc;
        }

        // Card 2: Timeline
        const startCard = document.getElementById('expCardStart');
        if (startCard) startCard.querySelector('.stat-value').textContent = formatDateTime(exp.started_at || exp.created_at);

        const endCard = document.getElementById('expCardEnd');
        if (endCard) endCard.querySelector('.stat-value').textContent = exp.completed_at ? formatDateTime(exp.completed_at) : '\u2014';

        const durationCard = document.getElementById('expCardDuration');
        if (durationCard) {
            const durationSec = computeDuration(exp.started_at || exp.created_at, exp.completed_at);
            durationCard.querySelector('.stat-value').textContent = durationSec != null ? formatDuration(durationSec) : '\u2014';
        }

        // Card 3: Results (only for completed experiments with metrics)
        const resultsCard = document.getElementById('expCardResults');
        if (resultsCard) {
            if (exp.status === 'completed' && exp.metrics) {
                resultsCard.style.display = '';
                const configType = exp.feature_config_type || exp.model_type || 'retrieval';
                renderResultsCard(exp.metrics, configType);
            } else {
                resultsCard.style.display = 'none';
            }
        }

        // Reset accordion states for overview tab
        resetAccordionStates();

        // Hide Registry & Deployment section for experiment mode
        const regDeploySection = document.getElementById('expViewRegistryDeploymentSection');
        if (regDeploySection) regDeploySection.style.display = 'none';

        // Hide the dataset accordion in experiment mode (cards shown directly instead)
        const datasetAccordion = document.getElementById('expViewDatasetAccordion');
        if (datasetAccordion) datasetAccordion.style.display = 'none';

        // Store dataset name for use in card rendering
        state.datasetName = exp.dataset_name || exp.dataset?.name || '';

        // Overview Tab - Dataset section: load into card container
        const datasetId = exp.dataset_id || exp.dataset?.id;
        if (datasetId) {
            loadDatasetDetails(datasetId, 'expCardDatasetContainer');
        } else {
            document.getElementById('expCardDatasetContainer').innerHTML = '<div class="exp-view-no-filters">No dataset configured</div>';
        }

        // Load features config details
        const featureConfigId = exp.feature_config_id || exp.feature_config?.id;
        if (featureConfigId) {
            loadFeaturesConfig(featureConfigId);
        } else {
            document.getElementById('expViewFeaturesConfigContent').innerHTML = '<div class="exp-view-no-filters">No features config</div>';
        }

        // Load model config details
        const modelConfigId = exp.model_config_id || exp.model_config?.id;
        if (modelConfigId) {
            loadModelConfig(modelConfigId);
        } else {
            document.getElementById('expViewModelConfigContent').innerHTML = '<div class="exp-view-no-filters">No model config</div>';
        }

        // Sampling & Training Parameters (card format)
        const trainingSetupContainer = document.getElementById('expViewTrainingSetupCards');
        if (trainingSetupContainer) {
            trainingSetupContainer.innerHTML = renderSamplingCard(exp) + renderTrainingParamsCard(exp);
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
            { name: 'Train', status: 'pending', duration_seconds: null },
            { name: 'Evaluator', status: 'pending', duration_seconds: null },
            { name: 'Register', status: 'pending', duration_seconds: null },
            { name: 'Deploy', status: 'skipped', duration_seconds: null }
        ];
    }

    // =============================================================================
    // TAB SWITCHING
    // =============================================================================

    function switchTab(tabName) {
        state.currentTab = tabName;

        // Update tab buttons
        document.querySelectorAll('.exp-view-pill').forEach(t => t.classList.remove('current'));
        const activeTab = document.querySelector(`.exp-view-pill[data-tab="${tabName}"]`);
        if (activeTab) activeTab.classList.add('current');

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
        } else if (state.mode === 'endpoint') {
            // Endpoint mode tabs
            const endpoint = state.currentEndpoint;
            if (tabName === 'logs' && endpoint) {
                renderEndpointLogsTab(endpoint);
            }
            if (tabName === 'versions' && endpoint) {
                if (!state.dataCache.versions) {
                    loadEndpointVersions(endpoint.id);
                } else {
                    const modelName = endpoint.model_name || state.dataCache.versions[0]?.vertex_model_name;
                    renderVersionsTab(modelName, state.dataCache.versions);
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

    function loadDatasetDetails(datasetId, targetContainerId) {
        const containerId = targetContainerId || 'expViewDatasetDetails';
        const container = document.getElementById(containerId);
        container.innerHTML = '<div class="exp-view-loading"><i class="fas fa-spinner fa-spin"></i> Loading...</div>';

        const url = buildUrl(config.endpoints.datasetSummary, { id: datasetId });

        fetch(appendModelEndpointId(url), {
            headers: { 'X-CSRFToken': getCookie('csrftoken') }
        })
        .then(response => response.json())
        .then(data => {
            if (data.status !== 'success') {
                container.innerHTML = '<div class="exp-view-no-filters">Failed to load dataset details</div>';
                return;
            }
            renderDatasetDetails(data.summary, containerId);
        })
        .catch(error => {
            console.error('Error loading dataset details:', error);
            container.innerHTML = '<div class="exp-view-no-filters">Failed to load dataset details</div>';
        });
    }

    function renderDatasetDetails(summary, containerId) {
        const container = document.getElementById(containerId || 'expViewDatasetDetails');
        const snapshot = summary.summary_snapshot || {};
        const filtersApplied = snapshot.filters_applied || {};
        const joinConfig = summary.join_config || {};

        // Tables info
        const primaryTable = summary.tables?.primary?.replace('raw_data.', '') || '-';
        const secondaryTables = summary.tables?.secondary || [];
        const tableCount = 1 + secondaryTables.length;

        // Build join rows
        const joinRows = Object.entries(joinConfig).map(([table, cfg]) => {
            const tableName = table.replace('raw_data.', '');
            return `
                <div style="display: flex; align-items: center; font-size: 13px; padding: 4px 0;">
                    <span style="color: #111827; font-weight: 500;">${primaryTable}.${cfg.join_key}</span>
                    <i class="fas fa-arrows-alt-h" style="margin: 0 8px; color: #9ca3af; font-size: 10px;"></i>
                    <span style="color: #111827; font-weight: 500;">${tableName}.${cfg.secondary_column}</span>
                    <span style="margin-left: 8px; padding: 1px 8px; border-radius: 4px; font-size: 11px; background: #f3f4f6; color: #6b7280;">${cfg.join_type || 'LEFT'}</span>
                </div>
            `;
        }).join('');

        // Build filter detail rows
        const filterDetails = [];

        if (filtersApplied.dates?.type === 'rolling') {
            filterDetails.push(`
                <div class="exp-filter-row">
                    <div class="exp-filter-label">
                        <div class="exp-filter-label-icon blue"><i class="fas fa-calendar-alt"></i></div>
                        Date Filter
                    </div>
                    <div class="exp-filter-values">
                        <span class="exp-filter-chip">Last ${filtersApplied.dates.days} days</span>
                        <span class="exp-filter-connector">on</span>
                        <span class="exp-filter-chip">${filtersApplied.dates.column || 'N/A'}</span>
                    </div>
                </div>
            `);
        } else if (filtersApplied.dates?.type === 'fixed') {
            filterDetails.push(`
                <div class="exp-filter-row">
                    <div class="exp-filter-label">
                        <div class="exp-filter-label-icon blue"><i class="fas fa-calendar-alt"></i></div>
                        Date Filter
                    </div>
                    <div class="exp-filter-values">
                        <span class="exp-filter-chip">From ${filtersApplied.dates.start_date}</span>
                        <span class="exp-filter-connector">on</span>
                        <span class="exp-filter-chip">${filtersApplied.dates.column || 'N/A'}</span>
                    </div>
                </div>
            `);
        }

        if (filtersApplied.customers?.type === 'multiple' && filtersApplied.customers.filters?.length > 0) {
            const customerChips = filtersApplied.customers.filters.map(f => {
                if (f.type === 'top_revenue') return `<span class="exp-filter-chip">Top ${f.percent}% by revenue</span>`;
                if (f.type === 'transaction_count') {
                    const desc = f.filter_type === 'greater_than' ? `> ${f.value}` :
                                 f.filter_type === 'less_than' ? `< ${f.value}` :
                                 `${f.min} – ${f.max}`;
                    return `<span class="exp-filter-chip">Transaction count ${desc}</span>`;
                }
                if (f.type === 'spending') {
                    const desc = f.filter_type === 'greater_than' ? `> $${f.value}` :
                                 f.filter_type === 'less_than' ? `< $${f.value}` :
                                 `$${f.min} – $${f.max}`;
                    return `<span class="exp-filter-chip">Total spending ${desc}</span>`;
                }
                if (f.type === 'category') {
                    const vals = f.values?.slice(0, 3).join(', ') + (f.values?.length > 3 ? '\u2026' : '');
                    return `<span class="exp-filter-chip">${f.column}: ${vals}</span>`;
                }
                return `<span class="exp-filter-chip">${f.type}</span>`;
            }).join('');
            filterDetails.push(`
                <div class="exp-filter-row">
                    <div class="exp-filter-label">
                        <div class="exp-filter-label-icon green"><i class="fas fa-users"></i></div>
                        Customer (${filtersApplied.customers.count || filtersApplied.customers.filters.length})
                    </div>
                    <div class="exp-filter-values">${customerChips}</div>
                </div>
            `);
        }

        if (filtersApplied.products?.type === 'multiple' && filtersApplied.products.filters?.length > 0) {
            const productChips = filtersApplied.products.filters.map(f => {
                if (f.type === 'top_revenue') return `<span class="exp-filter-chip">Top ${f.percent}% by revenue</span>`;
                if (f.type === 'category') {
                    const vals = f.values?.slice(0, 3).join(', ') + (f.values?.length > 3 ? '\u2026' : '');
                    return `<span class="exp-filter-chip">${f.column}: ${f.mode || ''} ${vals}</span>`;
                }
                if (f.type === 'numeric') {
                    const desc = f.filter_type === 'range' ? `${f.min} – ${f.max}` :
                                 f.filter_type === 'greater_than' ? `> ${f.value}` :
                                 f.filter_type === 'less_than' ? `< ${f.value}` : `= ${f.value}`;
                    return `<span class="exp-filter-chip">${f.column}: ${desc}</span>`;
                }
                return `<span class="exp-filter-chip">${f.type}</span>`;
            }).join('');
            filterDetails.push(`
                <div class="exp-filter-row">
                    <div class="exp-filter-label">
                        <div class="exp-filter-label-icon purple"><i class="fas fa-box"></i></div>
                        Product (${filtersApplied.products.count || filtersApplied.products.filters.length})
                    </div>
                    <div class="exp-filter-values">${productChips}</div>
                </div>
            `);
        }

        // Count filters for stat tablets
        const dateFilterCount = filtersApplied.dates?.type ? 1 : 0;
        const customerFilterCount = filtersApplied.customers?.count || 0;
        const productFilterCount = filtersApplied.products?.count || 0;
        const totalFilterCount = dateFilterCount + customerFilterCount + productFilterCount;

        const html = `
            <div style="display: flex; flex-direction: column; gap: 16px;">

                <!-- 1. Dataset Information -->
                <div class="exp-detail-section">
                    <div class="exp-detail-section-title">Dataset Information</div>
                    <div class="exp-detail-section-body">
                        <div class="exp-detail-section-icon info"><i class="fas fa-info-circle"></i></div>
                        <div class="exp-detail-stats">
                            <div class="exp-detail-stat-info" style="flex: 2;">
                                <div class="stat-label">Name</div>
                                <div class="stat-value">${state.datasetName || summary.name || '\u2014'}</div>
                            </div>
                            <div class="exp-detail-stat-info">
                                <div class="stat-label">Created</div>
                                <div class="stat-value">${summary.timestamps?.created_at ? new Date(summary.timestamps.created_at).toLocaleDateString() : 'Unknown'}</div>
                            </div>
                            <div class="exp-detail-stat">
                                <div class="exp-detail-stat-value">${snapshot.has_snapshot ? formatNumber(snapshot.total_rows) : '\u2014'}</div>
                                <div class="exp-detail-stat-label">Rows</div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 2. Tables & Joins -->
                <div class="exp-detail-section">
                    <div class="exp-detail-section-title">Tables & Joins</div>
                    <div class="exp-detail-section-body">
                        <div class="exp-detail-section-icon tables"><i class="fas fa-table"></i></div>
                        <div class="exp-detail-stats">
                            <div class="exp-detail-stat">
                                <div class="exp-detail-stat-value">${tableCount}</div>
                                <div class="exp-detail-stat-label">${tableCount === 1 ? 'Table' : 'Tables'}</div>
                            </div>
                            <div class="exp-detail-stat-info" style="flex: 2;">
                                <div class="stat-label">Primary Table</div>
                                <div class="stat-value">${primaryTable}</div>
                            </div>
                            ${secondaryTables.length > 0 ? `
                            <div class="exp-detail-stat-info" style="flex: 2;">
                                <div class="stat-label">Secondary</div>
                                <div class="stat-value">${secondaryTables.map(t => t.replace('raw_data.', '')).join(', ')}</div>
                            </div>
                            ` : ''}
                        </div>
                    </div>
                    ${Object.keys(joinConfig).length > 0 ? `
                    <div class="exp-detail-filter-details">
                        <div style="font-size: 12px; font-weight: 700; color: #374151; margin-bottom: 4px;">Join Keys</div>
                        ${joinRows}
                    </div>
                    ` : ''}
                </div>

                <!-- 3. Filters Applied (collapsible) -->
                <div class="exp-detail-section" id="expViewFiltersCard">
                    <div class="exp-detail-filters-header" onclick="ExpViewModal.toggleDatasetFilters()">
                        <div class="exp-detail-filters-title-row">
                            <div class="exp-detail-section-title" style="margin-bottom: 0;">Filters Applied</div>
                            ${filterDetails.length > 0 ? `
                            <div class="exp-detail-filters-toggle">
                                <i class="fas fa-chevron-right"></i>
                            </div>
                            ` : ''}
                        </div>
                        <div class="exp-detail-section-body">
                            <div class="exp-detail-section-icon filters"><i class="fas fa-filter"></i></div>
                            <div class="exp-detail-stats">
                                <div class="exp-detail-stat">
                                    <div class="exp-detail-stat-value">${totalFilterCount}</div>
                                    <div class="exp-detail-stat-label">Total Filters</div>
                                </div>
                                <div class="exp-detail-stat">
                                    <div class="exp-detail-stat-value">${dateFilterCount}</div>
                                    <div class="exp-detail-stat-label">Date</div>
                                </div>
                                <div class="exp-detail-stat">
                                    <div class="exp-detail-stat-value">${customerFilterCount}</div>
                                    <div class="exp-detail-stat-label">Customer</div>
                                </div>
                                <div class="exp-detail-stat">
                                    <div class="exp-detail-stat-value">${productFilterCount}</div>
                                    <div class="exp-detail-stat-label">Product</div>
                                </div>
                            </div>
                        </div>
                    </div>
                    ${filterDetails.length > 0 ? `
                    <div class="exp-detail-filters-content">
                        <div class="exp-detail-filter-details">
                            ${filterDetails.join('')}
                        </div>
                    </div>
                    ` : `
                    <div style="margin-top: 10px; font-size: 13px; color: #6b7280;">No filters applied \u2014 using all data</div>
                    `}
                </div>
            </div>
        `;

        container.innerHTML = html;
    }

    function toggleDatasetFilters() {
        const card = document.getElementById('expViewFiltersCard');
        if (card) card.classList.toggle('filters-open');
    }

    // =============================================================================
    // FEATURES CONFIG VISUALIZATION
    // =============================================================================

    function loadFeaturesConfig(featureConfigId) {
        const container = document.getElementById('expViewFeaturesConfigContent');
        container.innerHTML = '<div class="exp-view-loading"><i class="fas fa-spinner fa-spin"></i> Loading...</div>';

        const url = buildUrl(config.endpoints.featureConfig, { id: featureConfigId });

        fetch(appendModelEndpointId(url), {
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
        const totalFeatures = buyerResult.breakdown.length + productResult.breakdown.length;
        const totalDim = buyerResult.total + productResult.total;

        // Build target column card (for ranking models)
        let targetColumnHtml = '';
        if (configData.target_column && configData.config_type === 'ranking') {
            const tc = configData.target_column;
            const tcName = tc.display_name || tc.column || '-';
            const tcType = tc.bq_type || 'FLOAT';
            const transforms = tc.transforms || {};

            let transformsHtml = '';
            if (transforms.normalize && transforms.normalize.enabled) {
                transformsHtml += '<span class="target-transform-tag"><i class="fas fa-compress-arrows-alt"></i> Normalize 0-1</span>';
            }
            if (transforms.log_transform && transforms.log_transform.enabled) {
                transformsHtml += '<span class="target-transform-tag"><i class="fas fa-chart-line"></i> Log transform</span>';
            }
            if (transforms.clip_outliers && transforms.clip_outliers.enabled) {
                const lower = transforms.clip_outliers.lower?.enabled ? transforms.clip_outliers.lower.percentile : null;
                const upper = transforms.clip_outliers.upper?.enabled ? transforms.clip_outliers.upper.percentile : null;
                let clipText = 'Clip';
                if (lower && upper) clipText = `Clip ${lower}%-${upper}%`;
                else if (lower) clipText = `Clip lower ${lower}%`;
                else if (upper) clipText = `Clip upper ${upper}%`;
                transformsHtml += `<span class="target-transform-tag"><i class="fas fa-cut"></i> ${clipText}</span>`;
            }

            targetColumnHtml = `
                <div class="exp-detail-section">
                    <div class="exp-detail-section-title">Target Column</div>
                    <div class="exp-detail-section-body">
                        <div class="exp-detail-section-icon target"><i class="fas fa-bullseye"></i></div>
                        <div class="exp-detail-stats">
                            <div class="exp-detail-stat-info">
                                <div class="stat-label">Column</div>
                                <div class="stat-value">${tcName}</div>
                            </div>
                            <div class="exp-detail-stat-info">
                                <div class="stat-label">Type</div>
                                <div class="stat-value">${tcType}</div>
                            </div>
                        </div>
                    </div>
                    ${transformsHtml ? `
                    <div class="exp-detail-filter-details">
                        <div class="exp-filter-row" style="grid-template-columns: 100px 1fr;">
                            <div style="font-size: 13px; color: #6b7280; font-weight: 500;">Transforms:</div>
                            <div style="display: flex; flex-wrap: wrap; gap: 6px;">${transformsHtml}</div>
                        </div>
                    </div>` : ''}
                </div>
            `;
        }

        // Build Model Tensors card
        const tensorsHtml = `
            <div class="exp-detail-section">
                <div class="exp-detail-section-title">Model Tensors</div>
                <div class="exp-detail-section-body">
                    <div class="exp-detail-section-icon tensors"><i class="fas fa-cubes"></i></div>
                    <div class="exp-detail-stats">
                        <div class="exp-detail-stat">
                            <div class="exp-detail-stat-value">${buyerResult.total || 0}D</div>
                            <div class="exp-detail-stat-label">Buyer</div>
                        </div>
                        <div class="exp-detail-stat">
                            <div class="exp-detail-stat-value">${productResult.total || 0}D</div>
                            <div class="exp-detail-stat-label">Product</div>
                        </div>
                        <div class="exp-detail-stat">
                            <div class="exp-detail-stat-value">${totalFeatures}</div>
                            <div class="exp-detail-stat-label">Features</div>
                        </div>
                        <div class="exp-detail-stat">
                            <div class="exp-detail-stat-value">${totalDim}D</div>
                            <div class="exp-detail-stat-label">Total</div>
                        </div>
                    </div>
                </div>
                <div style="margin-top: 14px; padding-top: 14px; border-top: 1px solid #f3f4f6; display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                    <div class="p-4 bg-blue-50 rounded-lg">
                        <div class="flex items-center justify-between mb-3">
                            <h4 class="font-semibold text-blue-800">Buyer Tensor</h4>
                            <span class="font-semibold text-blue-600">${buyerResult.total}D</span>
                        </div>
                        <div id="expViewBuyerBar" class="exp-view-tensor-bar mb-3"></div>
                        <div class="space-y-1">
                            ${buyerResult.breakdown.map(item => `
                                <div class="flex items-center justify-between text-sm">
                                    <span class="${item.is_cross ? 'text-blue-600 italic' : 'text-blue-700'}">${item.name}</span>
                                    <span class="text-blue-500 font-medium">${item.dim}D</span>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                    <div class="p-4 bg-green-50 rounded-lg">
                        <div class="flex items-center justify-between mb-3">
                            <h4 class="font-semibold text-green-800">Product Tensor</h4>
                            <span class="font-semibold text-green-600">${productResult.total}D</span>
                        </div>
                        <div id="expViewProductBar" class="exp-view-tensor-bar mb-3"></div>
                        <div class="space-y-1">
                            ${productResult.breakdown.map(item => `
                                <div class="flex items-center justify-between text-sm">
                                    <span class="${item.is_cross ? 'text-green-600 italic' : 'text-green-700'}">${item.name}</span>
                                    <span class="text-green-500 font-medium">${item.dim}D</span>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            </div>
        `;

        container.innerHTML = targetColumnHtml + tensorsHtml;

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

        fetch(appendModelEndpointId(url), {
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

        const buyerLayers = mc.buyer_tower_layers || [];
        const productLayers = mc.product_tower_layers || [];
        const buyerParams = calculateTowerParams(buyerLayers);
        const productParams = calculateTowerParams(productLayers);
        const totalParams = buyerParams + productParams;
        const totalParamsDisplay = totalParams >= 1000
            ? Math.round(totalParams / 1000) + 'K'
            : totalParams.toLocaleString();
        const towerHtml = renderCardTowerLayersForView(buyerLayers, productLayers);

        // Retrieval algorithm section (for retrieval and multitask)
        let retrievalHtml = '';
        if (['retrieval', 'multitask'].includes(mc.model_type)) {
            let retrievalStats = `
                <div class="exp-detail-stat-info">
                    <div class="stat-label">Algorithm</div>
                    <div class="stat-value">${mc.retrieval_algorithm_display || 'Brute Force'}</div>
                </div>
                <div class="exp-detail-stat">
                    <div class="exp-detail-stat-value">${mc.top_k || 100}</div>
                    <div class="exp-detail-stat-label">Top-K</div>
                </div>
            `;
            if (mc.retrieval_algorithm === 'scann') {
                retrievalStats += `
                    <div class="exp-detail-stat">
                        <div class="exp-detail-stat-value">${mc.scann_num_leaves || 100}</div>
                        <div class="exp-detail-stat-label">Num Leaves</div>
                    </div>
                    <div class="exp-detail-stat">
                        <div class="exp-detail-stat-value">${mc.scann_leaves_to_search || 10}</div>
                        <div class="exp-detail-stat-label">Leaves to Search</div>
                    </div>
                `;
            }
            retrievalHtml = `
                <div class="exp-detail-section">
                    <div class="exp-detail-section-title">Retrieval Algorithm</div>
                    <div class="exp-detail-section-body">
                        <div class="exp-detail-section-icon algo"><i class="fas fa-search"></i></div>
                        <div class="exp-detail-stats">${retrievalStats}</div>
                    </div>
                </div>
            `;
        }

        // Rating Head section (for ranking and multitask)
        let ratingHeadHtml = '';
        if (['ranking', 'multitask'].includes(mc.model_type) && mc.rating_head_layers) {
            const ratingHeadLayers = mc.rating_head_layers || [];
            const ratingHeadParams = calculateTowerParams(ratingHeadLayers, (mc.output_embedding_dim || 32) * 2);
            const ratingLayersHtml = renderRatingHeadLayersForView(ratingHeadLayers);
            ratingHeadHtml = `
                <div class="exp-detail-section">
                    <div class="exp-detail-section-title">Rating Head</div>
                    <div class="exp-detail-section-body">
                        <div class="exp-detail-section-icon rating"><i class="fas fa-bullseye"></i></div>
                        <div class="exp-detail-stats">
                            <div class="exp-detail-stat-info">
                                <div class="stat-label">Loss Function</div>
                                <div class="stat-value">${mc.loss_function_display || 'MSE'}</div>
                            </div>
                            <div class="exp-detail-stat">
                                <div class="exp-detail-stat-value">${ratingHeadLayers.length}</div>
                                <div class="exp-detail-stat-label">Layers</div>
                            </div>
                            <div class="exp-detail-stat">
                                <div class="exp-detail-stat-value">${ratingHeadParams.toLocaleString()}</div>
                                <div class="exp-detail-stat-label">Params</div>
                            </div>
                        </div>
                    </div>
                    <div style="margin-top: 14px; padding-top: 14px; border-top: 1px solid #f3f4f6;">
                        <div class="rating-head-content">
                            <div class="rating-head-layers-col">
                                <div class="tower-stack ranking">
                                    ${ratingLayersHtml}
                                </div>
                            </div>
                            <div class="rating-head-params-col">
                                <div class="tower-params-summary view-modal" style="margin: 0; background: linear-gradient(135deg, #f5f3ff 0%, #ede9fe 100%); border-color: #8b5cf6;">
                                    <div class="params-row"><span>Total params:</span><span>${ratingHeadParams.toLocaleString()}</span></div>
                                    <div class="params-row"><span>Trainable params:</span><span>${ratingHeadParams.toLocaleString()}</span></div>
                                    <div class="params-row"><span>Non-trainable params:</span><span>0</span></div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }

        // Multitask weights section (for multitask only)
        let multitaskHtml = '';
        if (mc.model_type === 'multitask') {
            multitaskHtml = `
                <div class="exp-detail-section">
                    <div class="exp-detail-section-title">Multitask Weights</div>
                    <div class="exp-detail-section-body">
                        <div class="exp-detail-section-icon weights"><i class="fas fa-balance-scale"></i></div>
                        <div class="exp-detail-stats">
                            <div class="exp-detail-stat">
                                <div class="exp-detail-stat-value">${Math.round((mc.retrieval_weight !== undefined ? mc.retrieval_weight : 1) * 100)}%</div>
                                <div class="exp-detail-stat-label">Retrieval</div>
                            </div>
                            <div class="exp-detail-stat">
                                <div class="exp-detail-stat-value">${Math.round((mc.ranking_weight !== undefined ? mc.ranking_weight : 1) * 100)}%</div>
                                <div class="exp-detail-stat-label">Ranking</div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }

        container.innerHTML = `
            <!-- Config Information -->
            <div class="exp-detail-section">
                <div class="exp-detail-section-title">Config Information</div>
                <div class="exp-detail-section-body">
                    <div class="exp-detail-section-icon info"><i class="fas fa-info-circle"></i></div>
                    <div class="exp-detail-stats">
                        <div class="exp-detail-stat-info">
                            <div class="stat-label">Name</div>
                            <div class="stat-value">${mc.name || '—'}</div>
                        </div>
                        <div class="exp-detail-stat-info">
                            <div class="stat-label">Type</div>
                            <div class="stat-value">${mc.model_type_display || mc.model_type || '—'}</div>
                        </div>
                        <div class="exp-detail-stat">
                            <div class="exp-detail-stat-value">${mc.output_embedding_dim || 32}D</div>
                            <div class="exp-detail-stat-label">Output Dim</div>
                        </div>
                        <div class="exp-detail-stat-info" style="flex: 2;">
                            <div class="stat-label">Description</div>
                            <div class="stat-value">${mc.description || '—'}</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Tower Architecture -->
            <div class="exp-detail-section">
                <div class="exp-detail-section-title">Tower Architecture</div>
                <div class="exp-detail-section-body">
                    <div class="exp-detail-section-icon tower"><i class="fas fa-server"></i></div>
                    <div class="exp-detail-stats">
                        <div class="exp-detail-stat">
                            <div class="exp-detail-stat-value">${buyerLayers.length}</div>
                            <div class="exp-detail-stat-label">Buyer Layers</div>
                        </div>
                        <div class="exp-detail-stat">
                            <div class="exp-detail-stat-value">${productLayers.length}</div>
                            <div class="exp-detail-stat-label">Product Layers</div>
                        </div>
                        <div class="exp-detail-stat">
                            <div class="exp-detail-stat-value">${totalParamsDisplay}</div>
                            <div class="exp-detail-stat-label">Total Params</div>
                        </div>
                    </div>
                </div>
                <div style="margin-top: 14px; padding-top: 14px; border-top: 1px solid #f3f4f6;">
                    <div class="tower-visual tower-visual-aligned">
                        <div class="tower-column">
                            <div class="tower-header"><span class="tower-label">Buyer Tower</span></div>
                            <div class="tower-stack buyer">${towerHtml.buyer}</div>
                            <div class="tower-params-summary view-modal">
                                <div class="params-row"><span>Total params:</span><span>${buyerParams.toLocaleString()}</span></div>
                                <div class="params-row"><span>Trainable params:</span><span>${buyerParams.toLocaleString()}</span></div>
                                <div class="params-row"><span>Non-trainable params:</span><span>0</span></div>
                            </div>
                        </div>
                        <div class="tower-column">
                            <div class="tower-header"><span class="tower-label">Product Tower</span></div>
                            <div class="tower-stack product">${towerHtml.product}</div>
                            <div class="tower-params-summary view-modal">
                                <div class="params-row"><span>Total params:</span><span>${productParams.toLocaleString()}</span></div>
                                <div class="params-row"><span>Trainable params:</span><span>${productParams.toLocaleString()}</span></div>
                                <div class="params-row"><span>Non-trainable params:</span><span>0</span></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            ${ratingHeadHtml}

            <!-- Training Parameters -->
            <div class="exp-detail-section">
                <div class="exp-detail-section-title">Training Parameters</div>
                <div class="exp-detail-section-body">
                    <div class="exp-detail-section-icon params"><i class="fas fa-sliders-h"></i></div>
                    <div class="exp-detail-stats">
                        <div class="exp-detail-stat-info">
                            <div class="stat-label">Optimizer</div>
                            <div class="stat-value">${mc.optimizer_display || mc.optimizer || '—'}</div>
                        </div>
                        <div class="exp-detail-stat-info">
                            <div class="stat-label">Learning Rate</div>
                            <div class="stat-value">${mc.learning_rate || '—'}</div>
                        </div>
                        <div class="exp-detail-stat-info">
                            <div class="stat-label">Batch Size</div>
                            <div class="stat-value">${mc.batch_size ? mc.batch_size.toLocaleString() : '—'}</div>
                        </div>
                    </div>
                </div>
            </div>

            ${retrievalHtml}
            ${multitaskHtml}
        `;

        // Update Optimizer in Training Parameters card
        const optimizerEl = document.getElementById('expViewOptimizerValue');
        if (optimizerEl) {
            optimizerEl.textContent = mc.optimizer_display || mc.optimizer || 'Adagrad';
        }
    }

    function renderCardTowerLayersForView(buyerLayers, productLayers) {
        const maxLen = Math.max(buyerLayers.length, productLayers.length);
        if (maxLen === 0) {
            return {
                buyer: '<div class="text-xs text-gray-400 italic p-2">No layers</div>',
                product: '<div class="text-xs text-gray-400 italic p-2">No layers</div>'
            };
        }

        const renderLayer = (layer, isOutput) => {
            let badge = '';
            let params = '';

            if (layer.type === 'dense') {
                badge = '<span class="card-layer-badge dense">Dense</span>';
                params = `${layer.units} units`;
                if (layer.activation) params += `, ${layer.activation}`;
                if (layer.l2_regularization) params += `, L2=${layer.l2_regularization}`;
                else if (layer.l2_reg) params += `, L2=${layer.l2_reg}`;
            } else if (layer.type === 'dropout') {
                badge = '<span class="card-layer-badge dropout">Dropout</span>';
                params = `rate: ${layer.rate}`;
            } else if (layer.type === 'batch_norm') {
                badge = '<span class="card-layer-badge batch_norm">BatchNorm</span>';
                params = '';
            } else if (layer.type === 'layer_norm') {
                badge = '<span class="card-layer-badge layer_norm">LayerNorm</span>';
                params = layer.epsilon ? `ε: ${layer.epsilon}` : '';
            }

            return `
                <div class="card-layer-item${isOutput ? ' output-layer' : ''}">
                    <span class="card-drag-handle"><i class="fas fa-grip-vertical"></i></span>
                    ${badge}
                    <span class="card-layer-params">${params}</span>
                </div>
            `;
        };

        const renderPlaceholder = () => '<div class="card-layer-item empty-placeholder">&nbsp;</div>';

        const buildTowerHtml = (layers, placeholderCount) => {
            if (layers.length === 0) return '';
            const result = [];
            for (let i = 0; i < layers.length - 1; i++) {
                result.push(renderLayer(layers[i], false));
            }
            for (let i = 0; i < placeholderCount; i++) {
                result.push(renderPlaceholder());
            }
            result.push(renderLayer(layers[layers.length - 1], true));
            return result.join('');
        };

        const buyerPlaceholders = maxLen - buyerLayers.length;
        const productPlaceholders = maxLen - productLayers.length;

        return {
            buyer: buildTowerHtml(buyerLayers, buyerPlaceholders),
            product: buildTowerHtml(productLayers, productPlaceholders)
        };
    }

    function renderRatingHeadLayersForView(layers) {
        if (!layers || layers.length === 0) {
            return '<div class="text-xs text-gray-400 italic p-2">No layers defined</div>';
        }

        return layers.map((layer, idx) => {
            const isOutput = idx === layers.length - 1 && layer.type === 'dense' && layer.units === 1;
            let badge = '';
            let params = '';

            if (layer.type === 'dense') {
                badge = '<span class="card-layer-badge dense">Dense</span>';
                params = `${layer.units} units`;
                if (layer.activation) params += `, ${layer.activation}`;
                if (layer.l2_reg) params += `, L2=${layer.l2_reg}`;
            } else if (layer.type === 'dropout') {
                badge = '<span class="card-layer-badge dropout">Dropout</span>';
                params = `rate: ${layer.rate}`;
            } else if (layer.type === 'batch_norm') {
                badge = '<span class="card-layer-badge batch_norm">BatchNorm</span>';
                params = '';
            } else if (layer.type === 'layer_norm') {
                badge = '<span class="card-layer-badge layer_norm">LayerNorm</span>';
                params = layer.epsilon ? `ε: ${layer.epsilon}` : '';
            }

            return `
                <div class="card-layer-item${isOutput ? ' output-layer' : ''}">
                    <span class="card-drag-handle"><i class="fas fa-grip-vertical"></i></span>
                    ${badge}
                    <span class="card-layer-params">${params}</span>
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

    function renderSamplingCard(exp) {
        const splitLabels = {
            'random': 'Random 80/15/5',
            'time_holdout': 'Time Holdout',
            'strict_time': 'Strict Temporal'
        };

        let conditionalStats = '';
        if (exp.split_strategy !== 'random' && exp.date_column) {
            conditionalStats += `
                <div class="exp-detail-stat-info">
                    <div class="stat-label">Date Column</div>
                    <div class="stat-value">${exp.date_column}</div>
                </div>`;
        }
        if (exp.split_strategy === 'time_holdout') {
            conditionalStats += `
                <div class="exp-detail-stat-info">
                    <div class="stat-label">Holdout Days</div>
                    <div class="stat-value">${exp.holdout_days || 1} days</div>
                </div>`;
        }

        return `
            <div class="exp-detail-section">
                <div class="exp-detail-section-title">Sampling</div>
                <div class="exp-detail-section-body">
                    <div class="exp-detail-section-icon sampling"><i class="fas fa-percentage"></i></div>
                    <div class="exp-detail-stats">
                        <div class="exp-detail-stat-info">
                            <div class="stat-label">Sample %</div>
                            <div class="stat-value">${exp.data_sample_percent || 100}%</div>
                        </div>
                        <div class="exp-detail-stat-info">
                            <div class="stat-label">Split Strategy</div>
                            <div class="stat-value">${splitLabels[exp.split_strategy] || exp.split_strategy}</div>
                        </div>
                        ${conditionalStats}
                    </div>
                </div>
            </div>`;
    }

    function renderTrainingParamsCard(exp) {
        const hardwareSpecs = {
            'e2-standard-4': { name: 'Small', cpu: '4 vCPUs', memory: '16 GB' },
            'e2-standard-8': { name: 'Medium', cpu: '8 vCPUs', memory: '32 GB' },
            'e2-standard-16': { name: 'Large', cpu: '16 vCPUs', memory: '64 GB' },
            // Legacy n1-series (for older experiments)
            'n1-standard-4': { name: 'Small', cpu: '4 vCPUs', memory: '15 GB' },
            'n1-standard-8': { name: 'Medium', cpu: '8 vCPUs', memory: '30 GB' },
            'n1-standard-16': { name: 'Large', cpu: '16 vCPUs', memory: '60 GB' },
        };

        const machineType = exp.machine_type || 'e2-standard-4';
        const hwSpec = hardwareSpecs[machineType] || { name: 'Custom', cpu: '-', memory: '-' };
        const hardwareDisplay = `${hwSpec.cpu}, ${hwSpec.memory}`;

        return `
            <div class="exp-detail-section">
                <div class="exp-detail-section-title">Training Parameters</div>
                <div class="exp-detail-section-body">
                    <div class="exp-detail-section-icon training"><i class="fas fa-cogs"></i></div>
                    <div class="exp-detail-stats">
                        <div class="exp-detail-stat-info">
                            <div class="stat-label">Optimizer</div>
                            <div class="stat-value" id="expViewOptimizerValue">\u2014</div>
                        </div>
                        <div class="exp-detail-stat-info">
                            <div class="stat-label">Epochs</div>
                            <div class="stat-value">${exp.epochs || '\u2014'}</div>
                        </div>
                        <div class="exp-detail-stat-info">
                            <div class="stat-label">Batch Size</div>
                            <div class="stat-value">${exp.batch_size?.toLocaleString() || '\u2014'}</div>
                        </div>
                        <div class="exp-detail-stat-info">
                            <div class="stat-label">Learning Rate</div>
                            <div class="stat-value">${exp.learning_rate || '\u2014'}</div>
                        </div>
                        <div class="exp-detail-stat-info">
                            <div class="stat-label">Hardware</div>
                            <div class="stat-value">${hardwareDisplay}</div>
                        </div>
                    </div>
                </div>
            </div>`;
    }

    // =============================================================================
    // METRICS SUMMARY
    // =============================================================================

    function renderMetricsSummary(metrics, useTestPrefix = false, configType = 'retrieval') {
        const container = document.getElementById('expViewMetricsSummary');
        if (!container) return;

        const formatRecall = v => v != null ? (v * 100).toFixed(1) + '%' : 'N/A';
        const formatRMSE = v => v != null ? v.toFixed(2) : 'N/A';

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
                fetch(appendModelEndpointId(statsUrl)),
                fetch(appendModelEndpointId(schemaUrl))
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
                fetch(appendModelEndpointId(statsUrl)),
                fetch(appendModelEndpointId(schemaUrl))
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
            const response = await fetch(appendModelEndpointId(url));
            const data = await response.json();

            if (data.success && data.training_history?.available) {
                state.dataCache.trainingHistory = data.training_history;

                if (data.training_history.final_metrics) {
                    const configType = window.currentViewRun?.model_type || window.currentViewExp?.feature_config_type || 'retrieval';
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
            const response = await fetch(appendModelEndpointId(url));
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
                const configType = window.currentViewRun?.model_type || window.currentViewExp?.feature_config_type || 'retrieval';
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
        if (charts.versionsChart) { charts.versionsChart.destroy(); charts.versionsChart = null; }
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
        const configType = window.currentViewRun?.model_type || window.currentViewExp?.feature_config_type || 'retrieval';

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

        // Calculate Y-axis max with padding for data labels
        let yAxisMax;
        if (isRanking) {
            const maxValue = Math.max(...metricValues);
            yAxisMax = maxValue * 1.2; // Add 20% padding for labels
        } else {
            yAxisMax = 1;
        }

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
                        max: yAxisMax,
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
            const response = await fetch(appendModelEndpointId(url));
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
                const response = await fetch(appendModelEndpointId(url));
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
        // Reset accordion states
        state.accordionExpanded = {};

        // Reset features config container (not an accordion, but may be hidden by endpoint mode)
        const featuresConfig = document.getElementById('expViewFeaturesConfigContent');
        if (featuresConfig) {
            featuresConfig.style.display = 'flex';
            featuresConfig.innerHTML = '<div class="exp-view-loading"><i class="fas fa-spinner fa-spin"></i> Loading...</div>';
        }
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

        // Endpoint mode operations
        openForEndpoint: openForEndpoint,
        openWithEndpointData: openWithEndpointData,
        loadEndpointLogs: loadEndpointLogs,
        toggleEndpointLogs: toggleEndpointLogs,

        // Training run actions (Registry & Deployment)
        pushToRegistry: pushToRegistry,
        registerModel: registerModel,
        deployTrainingRun: deployTrainingRun,
        deployToCloudRun: deployToCloudRun,
        undeployTrainingRun: undeployTrainingRun,
        scheduleRetraining: scheduleRetraining,

        // Version deployment actions (Versions tab)
        deployVersion: deployVersion,
        undeployVersion: undeployVersion,

        // Tab switching
        switchTab: switchTab,

        // Overview accordion
        toggleAccordion: toggleAccordion,
        toggleDatasetFilters: toggleDatasetFilters,

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
        getCurrentEndpoint: () => state.currentEndpoint,
        getMode: () => state.mode
    };
})();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ExpViewModal;
}
