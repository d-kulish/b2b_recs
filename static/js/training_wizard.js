/**
 * Training Wizard Module
 *
 * A 3-step wizard modal for creating training runs.
 * Allows users to select a base experiment, configure training parameters,
 * and set GPU/deployment options before submitting to the Training API.
 *
 * Usage:
 *     // Configure the wizard
 *     TrainingWizard.configure({
 *         modelId: 123,
 *         onComplete: function() { loadTrainingRuns(); }
 *     });
 *
 *     // Open wizard
 *     TrainingWizard.open();
 *
 *     // Open from a specific experiment
 *     TrainingWizard.openFromExperiment(experimentId);
 */

const TrainingWizard = (function() {
    'use strict';

    // =============================================================================
    // CONFIGURATION & STATE
    // =============================================================================

    let config = {
        endpoints: {
            topConfigs: '/api/experiments/top-configurations/',
            quickTests: '/api/quick-tests/',
            datasets: '/api/modeling/datasets/{model_id}/',
            featureConfigs: '/api/modeling/{model_id}/feature-configs/',
            modelConfigs: '/api/modeling/model-configs/',
            createTrainingRun: '/api/training-runs/'
        },
        modelId: null,
        onComplete: null
    };

    let state = {
        currentStep: 1,
        formData: {
            name: '',
            description: '',
            modelType: 'retrieval',
            selectedExperiment: null,
            datasetId: null,
            featureConfigId: null,
            modelConfigId: null,
            trainingParams: {
                epochs: 150,
                batchSize: 8192,
                learningRate: 0.1,
                earlyStoppingEnabled: false,
                earlyStoppingPatience: 10,
                // Store original experiment values for reference
                expBatchSize: null,
                expLearningRate: null
            },
            // Inherited experiment settings (read-only display)
            experimentSettings: {
                splitStrategy: '',
                holdoutDays: null,
                dateColumn: '',
                optimizer: '',
                algorithm: '',
                topK: null,
                retrievalAlgorithm: ''
            },
            gpuConfig: {
                acceleratorType: 'NVIDIA_T4',
                acceleratorCount: 2,
                usePreemptible: false
            },
            evaluatorConfig: {
                enabled: false,
                blessingThreshold: 0.40
            },
            deploymentOption: 'register_only',
            scheduleConfig: {
                type: 'now',              // 'now', 'once', 'daily', 'weekly'
                date: null,               // YYYY-MM-DD for 'once'
                time: '09:00',            // HH:MM for all schedule types
                dayOfWeek: 0,             // 0=Monday for weekly
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
            }
        },
        experiments: [],
        datasets: [],
        featureConfigs: [],
        modelConfigs: [],
        validation: {
            step1: false,
            step2: true,  // Has defaults, starts valid
            step3: true   // Has defaults, starts valid
        },
        isLoading: false,
        searchQuery: '',
        searchTimeout: null,
        bestExperimentId: null,  // Track the actual best experiment ID for the current model type
        nameCheckTimeout: null,  // Debounce timeout for name uniqueness check
        nameAvailable: null      // null = not checked, true = available, false = taken
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

    function formatNumber(val) {
        if (val === null || val === undefined) return '-';
        if (Math.abs(val) >= 1000000) return (val / 1000000).toFixed(2) + 'M';
        if (Math.abs(val) >= 1000) return (val / 1000).toFixed(1) + 'K';
        if (Number.isInteger(val)) return val.toLocaleString();
        return val.toFixed(3);
    }

    function showToast(message, type = 'success') {
        // Simple toast implementation - can be enhanced later
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
            z-index: 1000;
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

    /**
     * Check if a training run name is available (unique).
     * Shows visual feedback on the input field.
     */
    async function checkNameAvailability(name) {
        const nameInput = document.getElementById('wizardRunName');
        const nameError = document.getElementById('wizardRunNameError');

        // Reset state
        state.nameAvailable = null;

        // Clear previous timeout
        if (state.nameCheckTimeout) {
            clearTimeout(state.nameCheckTimeout);
        }

        // Basic validation first
        if (!name || name.length < 3) {
            return;
        }

        // Debounce API call
        state.nameCheckTimeout = setTimeout(async () => {
            try {
                const response = await fetch(`/api/training-runs/check-name/?name=${encodeURIComponent(name)}`);
                const data = await response.json();

                if (data.success) {
                    state.nameAvailable = data.available;

                    if (!data.available) {
                        showFieldError(nameInput, nameError, 'This name already exists. Please choose a unique name.');
                    } else {
                        // Only hide error if it was showing the "already exists" message
                        if (nameError && nameError.textContent.includes('already exists')) {
                            hideFieldError(nameInput, nameError);
                        }
                    }
                }
            } catch (error) {
                console.error('Error checking name availability:', error);
            }
        }, 400);  // 400ms debounce
    }

    // =============================================================================
    // CONFIGURATION
    // =============================================================================

    function configure(options) {
        if (options.modelId) config.modelId = options.modelId;
        if (options.onComplete) config.onComplete = options.onComplete;
        if (options.endpoints) {
            config.endpoints = { ...config.endpoints, ...options.endpoints };
        }
    }

    // =============================================================================
    // MODAL OPEN/CLOSE
    // =============================================================================

    function open() {
        // Reset state
        resetState();

        // Show modal
        const modal = document.getElementById('trainingWizardModal');
        if (modal) {
            modal.classList.remove('hidden');
        }

        // Reset to step 1
        goToStep(1);

        // Load top experiments
        loadTopExperiments();
    }

    function openFromExperiment(experimentId) {
        // Reset state
        resetState();

        // Show modal
        const modal = document.getElementById('trainingWizardModal');
        if (modal) {
            modal.classList.remove('hidden');
        }

        // Load the experiment and pre-select it
        loadExperimentAndSelect(experimentId);
    }

    function close() {
        const modal = document.getElementById('trainingWizardModal');
        if (modal) {
            modal.classList.add('hidden');
        }
        resetState();
    }

    function resetState() {
        state.currentStep = 1;
        state.formData = {
            name: '',
            description: '',
            modelType: 'retrieval',
            selectedExperiment: null,
            datasetId: null,
            featureConfigId: null,
            modelConfigId: null,
            trainingParams: {
                epochs: 150,
                batchSize: 8192,
                learningRate: 0.1,
                earlyStoppingEnabled: false,
                earlyStoppingPatience: 10,
                expBatchSize: null,
                expLearningRate: null
            },
            experimentSettings: {
                splitStrategy: '',
                holdoutDays: null,
                dateColumn: '',
                optimizer: '',
                algorithm: '',
                topK: null,
                retrievalAlgorithm: ''
            },
            gpuConfig: {
                acceleratorType: 'NVIDIA_T4',
                acceleratorCount: 2,
                usePreemptible: false
            },
            evaluatorConfig: {
                enabled: false,
                blessingThreshold: 0.40
            },
            deploymentOption: 'register_only',
            scheduleConfig: {
                type: 'now',
                datetime: null,
                time: '09:00',
                dayOfWeek: 0,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
            }
        };
        state.experiments = [];
        state.validation = { step1: false, step2: true, step3: true };
        state.isLoading = false;
        state.searchQuery = '';
        state.bestExperimentId = null;
        state.nameCheckTimeout = null;
        state.nameAvailable = null;
    }

    // =============================================================================
    // STEP NAVIGATION
    // =============================================================================

    function goToStep(stepNum) {
        state.currentStep = stepNum;

        // Update step visibility
        for (let i = 1; i <= 3; i++) {
            const stepEl = document.getElementById(`wizardStep${i}`);
            if (stepEl) {
                stepEl.classList.toggle('active', i === stepNum);
            }
        }

        // Update progress pills
        const pills = document.querySelectorAll('.progress-step-pill');
        pills.forEach((pill, index) => {
            pill.classList.remove('current', 'completed', 'future');
            if (index + 1 < stepNum) {
                pill.classList.add('completed');
            } else if (index + 1 === stepNum) {
                pill.classList.add('current');
            } else {
                pill.classList.add('future');
            }
        });

        // Update step counter
        const counter = document.querySelector('.modal-step-counter');
        if (counter) {
            counter.textContent = `Step ${stepNum} of 3`;
        }

        // Update navigation buttons
        updateNavigationButtons();

        // Load step-specific data
        if (stepNum === 2) {
            renderStep2();
        } else if (stepNum === 3) {
            renderStep3();
        }
    }

    function nextStep() {
        if (state.currentStep >= 3) return;

        // Validate current step
        if (!validateStep(state.currentStep)) {
            return;
        }

        goToStep(state.currentStep + 1);
    }

    function prevStep() {
        if (state.currentStep <= 1) return;
        goToStep(state.currentStep - 1);
    }

    function updateNavigationButtons() {
        const prevBtn = document.getElementById('wizardPrevBtn');
        const nextBtn = document.getElementById('wizardNextBtn');
        const submitBtn = document.getElementById('wizardSubmitBtn');

        if (prevBtn) {
            prevBtn.classList.toggle('hidden', state.currentStep === 1);
            prevBtn.disabled = state.currentStep === 1;
        }

        if (nextBtn) {
            nextBtn.classList.toggle('hidden', state.currentStep === 3);
        }

        if (submitBtn) {
            submitBtn.classList.toggle('hidden', state.currentStep !== 3);
        }
    }

    // =============================================================================
    // VALIDATION
    // =============================================================================

    function validateStep(stepNum) {
        if (stepNum === 1) {
            return validateStep1();
        } else if (stepNum === 2) {
            return validateStep2();
        } else if (stepNum === 3) {
            return validateStep3();
        }
        return true;
    }

    function validateStep1() {
        let isValid = true;

        // Validate name
        const nameInput = document.getElementById('wizardRunName');
        const nameError = document.getElementById('wizardRunNameError');
        const name = nameInput?.value?.trim() || '';

        if (!name) {
            showFieldError(nameInput, nameError, 'Name is required');
            isValid = false;
        } else if (name.length < 3 || name.length > 63) {
            showFieldError(nameInput, nameError, 'Name must be 3-63 characters');
            isValid = false;
        } else if (!/^[a-z0-9_-]+$/.test(name)) {
            showFieldError(nameInput, nameError, 'Only lowercase letters, numbers, hyphens, and underscores allowed');
            isValid = false;
        } else if (state.nameAvailable === false) {
            // Name exists - show error
            showFieldError(nameInput, nameError, 'This name already exists. Please choose a unique name.');
            isValid = false;
        } else {
            hideFieldError(nameInput, nameError);
            state.formData.name = name;
        }

        // Validate experiment selection
        if (!state.formData.selectedExperiment) {
            isValid = false;
            const expList = document.getElementById('wizardExperimentList');
            if (expList) {
                expList.style.borderColor = '#dc2626';
            }
        }

        state.validation.step1 = isValid;
        return isValid;
    }

    function validateStep2() {
        // Step 2 has sensible defaults, always valid
        state.validation.step2 = true;
        return true;
    }

    function validateStep3() {
        // Step 3 has sensible defaults, always valid
        state.validation.step3 = true;
        return true;
    }

    function showFieldError(input, errorEl, message) {
        if (input) input.classList.add('error');
        if (errorEl) {
            errorEl.textContent = message;
            errorEl.classList.add('show');
        }
    }

    function hideFieldError(input, errorEl) {
        if (input) input.classList.remove('error');
        if (errorEl) errorEl.classList.remove('show');
    }

    // =============================================================================
    // STEP 1: SELECT BASE EXPERIMENT
    // =============================================================================

    async function loadTopExperiments() {
        const listEl = document.getElementById('wizardExperimentList');
        if (!listEl) return;

        listEl.innerHTML = '<div class="wizard-loading"><i class="fas fa-spinner fa-spin"></i> Loading experiments...</div>';

        try {
            const url = `${config.endpoints.topConfigs}?limit=5&model_type=${state.formData.modelType}`;
            const response = await fetch(url);
            const data = await response.json();

            if (data.success && data.configurations && data.configurations.length > 0) {
                state.experiments = data.configurations;
                // Store the best experiment ID (first one, since API returns sorted by best metrics)
                state.bestExperimentId = data.configurations[0].experiment_id;
                renderExperimentList();
            } else {
                listEl.innerHTML = `
                    <div class="wizard-experiments-empty">
                        <i class="fas fa-flask"></i>
                        <div>No completed ${state.formData.modelType} experiments found</div>
                        <div style="font-size: 11px; margin-top: 4px;">Run some experiments first to select as base</div>
                    </div>
                `;
            }
        } catch (error) {
            console.error('Failed to load experiments:', error);
            listEl.innerHTML = '<div class="wizard-experiments-empty"><i class="fas fa-exclamation-triangle"></i> Failed to load experiments</div>';
        }
    }

    function renderExperimentList() {
        const listEl = document.getElementById('wizardExperimentList');
        if (!listEl || !state.experiments.length) return;

        const html = state.experiments.map((exp, index) => {
            const isSelected = state.formData.selectedExperiment?.experiment_id === exp.experiment_id;
            const isBest = exp.experiment_id === state.bestExperimentId;
            const metricLabel = state.formData.modelType === 'ranking' ? 'RMSE' : 'R@100';
            const metricValue = state.formData.modelType === 'ranking'
                ? (exp.test_rmse != null ? exp.test_rmse.toFixed(4) : '-')
                : (exp.recall_at_100 != null ? exp.recall_at_100.toFixed(3) : '-');

            return `
                <div class="wizard-experiment-item ${isSelected ? 'selected' : ''}"
                     onclick="TrainingWizard.selectExperiment(${index})">
                    <input type="radio" name="wizardExp" ${isSelected ? 'checked' : ''}>
                    <div class="wizard-experiment-info">
                        <div class="wizard-experiment-name">
                            ${exp.display_name || 'Exp #' + exp.experiment_number}
                            ${isBest ? '<span class="badge-recommended"><i class="fas fa-star"></i> Best</span>' : ''}
                        </div>
                        <div class="wizard-experiment-details">
                            <span><i class="fas fa-database"></i> ${exp.dataset || 'Dataset'}</span>
                            <span><i class="fas fa-layer-group"></i> ${exp.feature_config || 'Features'}</span>
                            <span><i class="fas fa-project-diagram"></i> ${exp.model_config || 'Model'}</span>
                        </div>
                    </div>
                    <div class="wizard-experiment-metric">
                        <span class="metric-value">${metricValue}</span>
                        <span class="metric-label">${metricLabel}</span>
                    </div>
                    <div class="wizard-experiment-actions">
                        <button class="btn-view" onclick="event.stopPropagation(); TrainingWizard.openExpViewModal(${exp.experiment_id})">View</button>
                    </div>
                </div>
            `;
        }).join('');

        listEl.innerHTML = html;
    }

    function selectExperiment(index) {
        const exp = state.experiments[index];
        if (!exp) return;

        state.formData.selectedExperiment = exp;
        state.formData.datasetId = exp.dataset_id;
        state.formData.featureConfigId = exp.feature_config_id;
        state.formData.modelConfigId = exp.model_config_id;

        // Copy training parameters from experiment
        // Learning rate: copy one-to-one from experiment
        if (exp.learning_rate != null) {
            state.formData.trainingParams.learningRate = exp.learning_rate;
            state.formData.trainingParams.expLearningRate = exp.learning_rate;
        }

        // Batch size: store original for reference, keep scaled default for GPUs
        if (exp.batch_size != null) {
            state.formData.trainingParams.expBatchSize = exp.batch_size;
            // Keep default 8192 for GPU training, but store original for reference
        }

        // Store experiment settings (read-only display)
        state.formData.experimentSettings.splitStrategy = exp.split_strategy || 'time_holdout';
        state.formData.experimentSettings.holdoutDays = exp.holdout_days || null;
        state.formData.experimentSettings.dateColumn = exp.date_column || '';
        state.formData.experimentSettings.optimizer = exp.optimizer || 'adagrad';
        state.formData.experimentSettings.topK = exp.top_k || 100;
        state.formData.experimentSettings.retrievalAlgorithm = exp.retrieval_algorithm || 'scann';

        // Determine algorithm display based on retrieval_algorithm and model type
        const algoMap = {
            'scann': 'ScaNN',
            'brute_force': 'Brute Force',
            'annoy': 'Annoy'
        };
        if (state.formData.modelType === 'ranking') {
            state.formData.experimentSettings.algorithm = 'DCN Ranking';
        } else if (state.formData.modelType === 'hybrid') {
            state.formData.experimentSettings.algorithm = 'Multitask (Retrieval + Ranking)';
        } else {
            // Retrieval - use actual algorithm
            state.formData.experimentSettings.algorithm = algoMap[exp.retrieval_algorithm] || 'Two-Tower';
        }

        // Update blessing threshold based on model type
        if (state.formData.modelType === 'ranking') {
            state.formData.evaluatorConfig.blessingThreshold = 1.0;  // Lower RMSE is better
        } else {
            state.formData.evaluatorConfig.blessingThreshold = 0.40;  // Higher recall is better
        }

        // Re-render list to show selection
        renderExperimentList();

        // Show selected summary
        renderSelectedExperimentSummary();

        // Reset experiment list border if it was red
        const listEl = document.getElementById('wizardExperimentList');
        if (listEl) {
            listEl.style.borderColor = '';
        }
    }

    function renderSelectedExperimentSummary() {
        const summaryEl = document.getElementById('wizardSelectedExpSummary');
        if (!summaryEl) return;

        const exp = state.formData.selectedExperiment;
        if (!exp) {
            summaryEl.classList.remove('show');
            return;
        }

        summaryEl.innerHTML = `
            <div class="selected-experiment-summary-header">
                <i class="fas fa-check-circle"></i>
                Selected: ${exp.display_name || 'Exp #' + exp.experiment_number}
            </div>
            <div class="selected-experiment-summary-content">
                <span><strong>Dataset:</strong> ${exp.dataset || 'N/A'}</span>
                <span><strong>Features:</strong> ${exp.feature_config || 'N/A'}</span>
                <span><strong>Model:</strong> ${exp.model_config || 'N/A'}</span>
            </div>
        `;
        summaryEl.classList.add('show');
    }

    function selectModelType(modelType) {
        if (state.formData.modelType === modelType) return;

        state.formData.modelType = modelType;
        state.formData.selectedExperiment = null;

        // Update model type card visual selection
        document.querySelectorAll('.model-type-card').forEach(card => {
            card.classList.remove('selected');
            if (card.dataset.type === modelType) {
                card.classList.add('selected');
            }
        });

        // Hide selected summary
        const summaryEl = document.getElementById('wizardSelectedExpSummary');
        if (summaryEl) summaryEl.classList.remove('show');

        // Reload experiments for new model type
        loadTopExperiments();
    }

    async function searchExperiments(query) {
        state.searchQuery = query;

        // Debounce
        if (state.searchTimeout) {
            clearTimeout(state.searchTimeout);
        }

        if (!query.trim()) {
            loadTopExperiments();
            return;
        }

        state.searchTimeout = setTimeout(async () => {
            const listEl = document.getElementById('wizardExperimentList');
            if (!listEl) return;

            listEl.innerHTML = '<div class="wizard-loading"><i class="fas fa-spinner fa-spin"></i> Searching...</div>';

            try {
                const url = `${config.endpoints.quickTests}?model_type=${state.formData.modelType}&status=completed&search=${encodeURIComponent(query)}`;
                const response = await fetch(url);
                const data = await response.json();

                if (data.success && data.quick_tests && data.quick_tests.length > 0) {
                    // Map to same format as top configs
                    state.experiments = data.quick_tests.slice(0, 10).map(exp => ({
                        experiment_id: exp.id,
                        experiment_number: exp.experiment_number || exp.id,
                        display_name: exp.display_name || `Exp #${exp.experiment_number || exp.id}`,
                        dataset: exp.dataset_name,
                        dataset_id: exp.dataset_id,
                        feature_config: exp.feature_config_name,
                        feature_config_id: exp.feature_config_id,
                        model_config: exp.model_config_name,
                        model_config_id: exp.model_config_id,
                        recall_at_100: exp.recall_at_100,
                        test_rmse: exp.test_rmse,
                        // Training parameters
                        learning_rate: exp.learning_rate,
                        batch_size: exp.batch_size,
                        // Experiment settings (read-only)
                        split_strategy: exp.split_strategy,
                        holdout_days: exp.holdout_days,
                        date_column: exp.date_column,
                        optimizer: exp.optimizer,
                        top_k: exp.top_k,
                        retrieval_algorithm: exp.retrieval_algorithm
                    }));
                    renderExperimentList();
                } else {
                    listEl.innerHTML = `
                        <div class="wizard-experiments-empty">
                            <i class="fas fa-search"></i>
                            <div>No experiments found matching "${query}"</div>
                        </div>
                    `;
                }
            } catch (error) {
                console.error('Search failed:', error);
            }
        }, 300);
    }

    async function loadExperimentAndSelect(experimentId) {
        const listEl = document.getElementById('wizardExperimentList');
        if (listEl) {
            listEl.innerHTML = '<div class="wizard-loading"><i class="fas fa-spinner fa-spin"></i> Loading experiment...</div>';
        }

        try {
            const response = await fetch(`/api/quick-tests/${experimentId}/`);
            const data = await response.json();

            if (data.success && data.quick_test) {
                const exp = data.quick_test;
                state.experiments = [{
                    experiment_id: exp.id,
                    experiment_number: exp.experiment_number || exp.id,
                    display_name: exp.display_name || `Exp #${exp.experiment_number || exp.id}`,
                    dataset: exp.dataset_name,
                    dataset_id: exp.dataset_id,
                    feature_config: exp.feature_config_name,
                    feature_config_id: exp.feature_config_id,
                    model_config: exp.model_config_name,
                    model_config_id: exp.model_config_id,
                    recall_at_100: exp.metrics?.recall_at_100 || exp.recall_at_100,
                    test_rmse: exp.metrics?.test_rmse || exp.test_rmse,
                    // Training parameters
                    learning_rate: exp.learning_rate,
                    batch_size: exp.batch_size,
                    // Experiment settings (read-only)
                    split_strategy: exp.split_strategy,
                    holdout_days: exp.holdout_days,
                    date_column: exp.date_column,
                    optimizer: exp.optimizer,
                    top_k: exp.top_k,
                    retrieval_algorithm: exp.retrieval_algorithm
                }];

                // Set model type from experiment
                const modelType = exp.feature_config_type || exp.model_type || 'retrieval';
                state.formData.modelType = modelType.toLowerCase();

                // Update model type cards
                document.querySelectorAll('.model-type-card').forEach(card => {
                    card.classList.remove('selected');
                    if (card.dataset.type === state.formData.modelType) {
                        card.classList.add('selected');
                    }
                });

                renderExperimentList();
                selectExperiment(0);
            } else {
                loadTopExperiments();
            }
        } catch (error) {
            console.error('Failed to load experiment:', error);
            loadTopExperiments();
        }
    }

    function openExpViewModal(expId) {
        // Use the ExpViewModal if available
        if (typeof ExpViewModal !== 'undefined' && ExpViewModal.open) {
            ExpViewModal.open(expId);
        }
    }

    // =============================================================================
    // STEP 2: CONFIGURATION & PARAMETERS
    // =============================================================================

    function renderStep2() {
        // Render inherited config cards
        renderConfigCards();

        // Populate training params with current values
        populateTrainingParams();
    }

    function renderConfigCards() {
        const exp = state.formData.selectedExperiment;
        if (!exp) return;

        // Dataset card
        const datasetCard = document.getElementById('wizardDatasetCard');
        if (datasetCard) {
            datasetCard.querySelector('.config-card-name').textContent = exp.dataset || 'Dataset';
            // Could load row count asynchronously
        }

        // Feature config card
        const featureCard = document.getElementById('wizardFeatureCard');
        if (featureCard) {
            featureCard.querySelector('.config-card-name').textContent = exp.feature_config || 'Feature Config';
        }

        // Model config card
        const modelCard = document.getElementById('wizardModelCard');
        if (modelCard) {
            modelCard.querySelector('.config-card-name').textContent = exp.model_config || 'Model Config';
        }
    }

    function populateTrainingParams() {
        const params = state.formData.trainingParams;

        // Set select values
        setInputValue('wizardEpochs', params.epochs);
        setInputValue('wizardBatchSize', params.batchSize);
        setInputValue('wizardLearningRate', params.learningRate);

        // Set early stopping toggle (default is off)
        const earlyStopToggle = document.getElementById('wizardEarlyStopping');
        if (earlyStopToggle) {
            earlyStopToggle.checked = params.earlyStoppingEnabled;
        }

        // Set patience
        setInputValue('wizardPatience', params.earlyStoppingPatience);

        // Show experiment reference values (Exp used: X)
        const batchSizeRef = document.getElementById('wizardBatchSizeRef');
        if (batchSizeRef) {
            if (params.expBatchSize != null) {
                batchSizeRef.textContent = `(Exp used: ${params.expBatchSize.toLocaleString()})`;
                batchSizeRef.style.display = 'inline';
            } else {
                batchSizeRef.style.display = 'none';
            }
        }

        // Populate experiment settings chips (read-only)
        populateExperimentSettings();
    }

    function populateExperimentSettings() {
        const settings = state.formData.experimentSettings;

        // Format split strategy display
        let splitStrategyText = '-';
        if (settings.splitStrategy === 'time_holdout') {
            splitStrategyText = settings.holdoutDays
                ? `Time Holdout (${settings.holdoutDays}d)`
                : 'Time Holdout';
        } else if (settings.splitStrategy === 'strict_time') {
            splitStrategyText = 'Strict Temporal';
        } else if (settings.splitStrategy === 'random') {
            splitStrategyText = 'Random (80/15/5)';
        }

        // Format optimizer display (capitalize)
        const optimizerMap = {
            'adam': 'Adam',
            'adagrad': 'AdaGrad',
            'sgd': 'SGD',
            'rmsprop': 'RMSprop',
            'ftrl': 'FTRL'
        };
        const optimizerText = optimizerMap[settings.optimizer?.toLowerCase()] || settings.optimizer || 'AdaGrad';

        // Update chip values
        const splitStrategyDisplay = document.getElementById('wizardSplitStrategyDisplay');
        if (splitStrategyDisplay) splitStrategyDisplay.textContent = splitStrategyText;

        const optimizerDisplay = document.getElementById('wizardOptimizerDisplay');
        if (optimizerDisplay) optimizerDisplay.textContent = optimizerText;

        const algorithmDisplay = document.getElementById('wizardAlgorithmDisplay');
        if (algorithmDisplay) algorithmDisplay.textContent = settings.algorithm || '-';

        const topKDisplay = document.getElementById('wizardTopKDisplay');
        if (topKDisplay) topKDisplay.textContent = settings.topK || '100';
    }

    function setInputValue(elementId, value) {
        const el = document.getElementById(elementId);
        if (el && value != null) el.value = String(value);
    }

    function updateTrainingParam(param, value) {
        if (param === 'epochs') {
            state.formData.trainingParams.epochs = parseInt(value);
        } else if (param === 'batchSize') {
            state.formData.trainingParams.batchSize = parseInt(value);
        } else if (param === 'learningRate') {
            state.formData.trainingParams.learningRate = parseFloat(value);
        } else if (param === 'earlyStoppingEnabled') {
            state.formData.trainingParams.earlyStoppingEnabled = value;
        } else if (param === 'earlyStoppingPatience') {
            state.formData.trainingParams.earlyStoppingPatience = parseInt(value);
        }
    }

    function toggleAdvanced() {
        const chevron = document.getElementById('wizardAdvancedChevron');
        const content = document.getElementById('wizardAdvancedContent');

        if (chevron && content) {
            const isExpanded = chevron.classList.toggle('expanded');
            content.classList.toggle('hidden', !isExpanded);
        }
    }

    function toggleStep3Advanced() {
        const chevron = document.getElementById('wizardStep3AdvancedChevron');
        const content = document.getElementById('wizardStep3AdvancedContent');

        if (chevron && content) {
            const isExpanded = chevron.classList.toggle('expanded');
            content.classList.toggle('hidden', !isExpanded);
        }
    }

    function toggleDeploy() {
        const chevron = document.getElementById('wizardDeployChevron');
        const content = document.getElementById('wizardDeployContent');

        if (chevron && content) {
            const isExpanded = chevron.classList.toggle('expanded');
            content.classList.toggle('hidden', !isExpanded);
        }
    }

    // =============================================================================
    // STEP 3: GPU & DEPLOYMENT
    // =============================================================================

    function renderStep3() {
        // Render GPU selection
        renderGPUSelection();

        // Render summary panel
        renderSummaryPanel();

        // Set evaluator toggle
        const evalToggle = document.getElementById('wizardEvaluatorEnabled');
        if (evalToggle) {
            evalToggle.checked = state.formData.evaluatorConfig.enabled;
        }

        // Set threshold
        const thresholdInput = document.getElementById('wizardBlessingThreshold');
        if (thresholdInput) {
            thresholdInput.value = state.formData.evaluatorConfig.blessingThreshold;
        }

        // Set preemptible toggle
        const preemptToggle = document.getElementById('wizardPreemptible');
        if (preemptToggle) {
            preemptToggle.checked = state.formData.gpuConfig.usePreemptible;
        }

        // Initialize schedule type selection
        selectScheduleType(state.formData.scheduleConfig.type);

        // Set schedule timezone
        const timezoneSelect = document.getElementById('wizardScheduleTimezone');
        if (timezoneSelect) {
            timezoneSelect.value = state.formData.scheduleConfig.timezone;
        }

        // Set day of week for weekly
        const daySelect = document.getElementById('wizardScheduleDayOfWeek');
        if (daySelect) {
            daySelect.value = state.formData.scheduleConfig.dayOfWeek;
        }

        // Initialize datetime pickers
        initializeDatetimePickers();
    }

    function renderGPUSelection() {
        const gpuCards = document.querySelectorAll('.gpu-card');
        gpuCards.forEach(card => {
            const gpuType = card.dataset.gpu;
            card.classList.toggle('selected', gpuType === state.formData.gpuConfig.acceleratorType);
        });

        // Set GPU count
        setInputValue('wizardGpuCount', state.formData.gpuConfig.acceleratorCount);
    }

    function selectGPU(gpuType) {
        // Only T4 is currently available (quota approved)
        // Other GPUs are disabled in the UI
        if (gpuType !== 'NVIDIA_T4') {
            return;
        }
        state.formData.gpuConfig.acceleratorType = gpuType;
        renderGPUSelection();
    }

    function updateGPUCount(count) {
        state.formData.gpuConfig.acceleratorCount = parseInt(count);
    }

    function updatePreemptible(enabled) {
        state.formData.gpuConfig.usePreemptible = enabled;
    }

    function updateEvaluator(param, value) {
        if (param === 'enabled') {
            state.formData.evaluatorConfig.enabled = value;
        } else if (param === 'threshold') {
            state.formData.evaluatorConfig.blessingThreshold = parseFloat(value);
        }
    }

    function selectDeploymentOption(option) {
        state.formData.deploymentOption = option;
        document.querySelectorAll('.deployment-option').forEach(opt => {
            opt.classList.toggle('selected', opt.dataset.option === option);
        });
    }

    function toggleSchedule() {
        const chevron = document.getElementById('wizardScheduleChevron');
        const content = document.getElementById('wizardScheduleContent');

        if (chevron && content) {
            const isExpanded = !chevron.classList.contains('expanded');
            chevron.classList.toggle('expanded', isExpanded);
            content.classList.toggle('hidden', !isExpanded);
        }
    }

    function onScheduleTypeChange() {
        // Get selected radio button value
        const selectedRadio = document.querySelector('input[name="wizardScheduleType"]:checked');
        const scheduleType = selectedRadio ? selectedRadio.value : 'now';

        state.formData.scheduleConfig.type = scheduleType;

        // Get all option containers
        const onceOptions = document.getElementById('wizardScheduleOnceOptions');
        const dailyOptions = document.getElementById('wizardScheduleDailyOptions');
        const weeklyOptions = document.getElementById('wizardScheduleWeeklyOptions');

        // Hide all by default
        if (onceOptions) onceOptions.classList.add('hidden');
        if (dailyOptions) dailyOptions.classList.add('hidden');
        if (weeklyOptions) weeklyOptions.classList.add('hidden');

        // Show relevant options
        if (scheduleType === 'once') {
            if (onceOptions) onceOptions.classList.remove('hidden');
        } else if (scheduleType === 'daily') {
            if (dailyOptions) dailyOptions.classList.remove('hidden');
        } else if (scheduleType === 'weekly') {
            if (weeklyOptions) weeklyOptions.classList.remove('hidden');
        }

        // Update submit button text
        const submitBtn = document.getElementById('wizardSubmitBtn');
        if (submitBtn) {
            const btnInner = submitBtn.querySelector('.btn-neu-inner');
            if (btnInner) {
                btnInner.innerHTML = scheduleType === 'now' ? 'Run' : 'Schedule';
            }
        }
    }

    // Keep old function name for backwards compatibility
    function selectScheduleType(type) {
        // Find and check the corresponding radio button
        const radio = document.querySelector(`input[name="wizardScheduleType"][value="${type}"]`);
        if (radio) {
            radio.checked = true;
            onScheduleTypeChange();
        }
    }

    function updateScheduleConfig(param, value) {
        if (param === 'date') {
            state.formData.scheduleConfig.date = value;
        } else if (param === 'time') {
            state.formData.scheduleConfig.time = value;
        } else if (param === 'dayOfWeek') {
            state.formData.scheduleConfig.dayOfWeek = parseInt(value);
        } else if (param === 'timezone') {
            state.formData.scheduleConfig.timezone = value;
        }
    }

    function initializeDatetimePickers() {
        // No longer using flatpickr - using native HTML5 date/time inputs
        // This function is kept for backwards compatibility but does nothing
    }

    function renderSummaryPanel() {
        const summaryEl = document.getElementById('wizardSummaryGrid');
        if (!summaryEl) return;

        const exp = state.formData.selectedExperiment;
        const params = state.formData.trainingParams;
        const gpu = state.formData.gpuConfig;

        summaryEl.innerHTML = `
            <div class="wizard-summary-item">
                <span class="summary-label">Run Name</span>
                <span class="summary-value">${state.formData.name || '-'}</span>
            </div>
            <div class="wizard-summary-item">
                <span class="summary-label">Base Experiment</span>
                <span class="summary-value">${exp?.display_name || '-'}</span>
            </div>
            <div class="wizard-summary-item">
                <span class="summary-label">Epochs</span>
                <span class="summary-value">${params.epochs}</span>
            </div>
            <div class="wizard-summary-item">
                <span class="summary-label">Batch Size</span>
                <span class="summary-value">${formatNumber(params.batchSize)}</span>
            </div>
            <div class="wizard-summary-item">
                <span class="summary-label">Learning Rate</span>
                <span class="summary-value">${params.learningRate}</span>
            </div>
            <div class="wizard-summary-item">
                <span class="summary-label">GPU</span>
                <span class="summary-value">${gpu.acceleratorCount}x ${gpu.acceleratorType.replace('NVIDIA_', '')}</span>
            </div>
            <div class="wizard-summary-item">
                <span class="summary-label">Preemptible</span>
                <span class="summary-value">${gpu.usePreemptible ? 'Yes' : 'No'}</span>
            </div>
            <div class="wizard-summary-item">
                <span class="summary-label">Evaluator</span>
                <span class="summary-value">${state.formData.evaluatorConfig.enabled ? 'Enabled' : 'Disabled'}</span>
            </div>
        `;
    }

    // =============================================================================
    // SUBMIT
    // =============================================================================

    async function submit() {
        if (!validateStep(3)) return;

        const submitBtn = document.getElementById('wizardSubmitBtn');
        const scheduleType = state.formData.scheduleConfig.type;
        const isScheduled = scheduleType !== 'now';

        if (submitBtn) {
            submitBtn.disabled = true;
            const btnInner = submitBtn.querySelector('.btn-neu-inner');
            if (btnInner) {
                btnInner.innerHTML = '<i class="fas fa-spinner fa-spin"></i> ' + (isScheduled ? 'Scheduling...' : 'Submitting...');
            }
        }

        try {
            const payload = buildPayload();

            // Use the schedule API endpoint which handles both immediate and scheduled runs
            const endpoint = '/api/training/schedules/';

            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify(payload)
            });

            const data = await response.json();

            if (data.success) {
                // Success
                close();

                if (isScheduled) {
                    showToast('Training scheduled successfully!', 'success');
                } else {
                    showToast('Training run created successfully!', 'success');
                }

                // Call completion callback
                if (config.onComplete) {
                    config.onComplete();
                }

                // Switch to training chapter
                if (typeof switchChapter === 'function') {
                    switchChapter('training');
                }
            } else {
                // Error
                showToast(data.error || 'Failed to create training', 'error');
            }
        } catch (error) {
            console.error('Submit failed:', error);
            showToast('Failed to create training', 'error');
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                const btnInner = submitBtn.querySelector('.btn-neu-inner');
                if (btnInner) {
                    if (isScheduled) {
                        btnInner.innerHTML = 'Schedule';
                    } else {
                        btnInner.innerHTML = 'Run';
                    }
                }
            }
        }
    }

    function buildPayload() {
        const exp = state.formData.selectedExperiment;
        const params = state.formData.trainingParams;
        const expSettings = state.formData.experimentSettings;
        const gpu = state.formData.gpuConfig;
        const evaluator = state.formData.evaluatorConfig;
        const schedule = state.formData.scheduleConfig;

        const payload = {
            name: state.formData.name,
            description: state.formData.description || '',
            dataset_id: exp.dataset_id || state.formData.datasetId,
            feature_config_id: exp.feature_config_id || state.formData.featureConfigId,
            model_config_id: exp.model_config_id || state.formData.modelConfigId,
            base_experiment_id: exp.experiment_id,
            training_params: {
                epochs: params.epochs,
                batch_size: params.batchSize,
                learning_rate: params.learningRate,
                // Split strategy inherited from experiment (read-only)
                split_strategy: expSettings.splitStrategy,
                holdout_days: expSettings.holdoutDays,
                date_column: expSettings.dateColumn,
                early_stopping: {
                    enabled: params.earlyStoppingEnabled,
                    patience: params.earlyStoppingPatience
                }
            },
            gpu_config: {
                gpu_type: gpu.acceleratorType.replace('NVIDIA_', 'NVIDIA_TESLA_'),
                gpu_count: gpu.acceleratorCount,
                preemptible: gpu.usePreemptible
            },
            evaluator_config: {
                enabled: evaluator.enabled,
                blessing_threshold: {
                    metric: 'recall_at_100',
                    min_value: parseFloat(evaluator.blessingThreshold)
                }
            }
        };

        // Add schedule configuration
        if (schedule.type === 'now') {
            payload.schedule_type = 'now';
        } else {
            payload.schedule_type = schedule.type;
            payload.schedule_timezone = schedule.timezone;
            if (schedule.type === 'once') {
                payload.scheduled_datetime = schedule.datetime;
            } else {
                payload.schedule_time = schedule.time;
                if (schedule.type === 'weekly') {
                    payload.schedule_day_of_week = schedule.dayOfWeek;
                }
            }
        }

        return payload;
    }

    // =============================================================================
    // PUBLIC API
    // =============================================================================

    return {
        configure: configure,
        open: open,
        close: close,
        nextStep: nextStep,
        prevStep: prevStep,
        submit: submit,
        openFromExperiment: openFromExperiment,
        selectExperiment: selectExperiment,
        selectModelType: selectModelType,
        searchExperiments: searchExperiments,
        openExpViewModal: openExpViewModal,
        toggleAdvanced: toggleAdvanced,
        toggleStep3Advanced: toggleStep3Advanced,
        updateTrainingParam: updateTrainingParam,
        selectGPU: selectGPU,
        updateGPUCount: updateGPUCount,
        updatePreemptible: updatePreemptible,
        updateEvaluator: updateEvaluator,
        selectDeploymentOption: selectDeploymentOption,
        selectScheduleType: selectScheduleType,
        updateScheduleConfig: updateScheduleConfig,
        checkNameAvailability: checkNameAvailability,
        toggleDeploy: toggleDeploy,
        toggleSchedule: toggleSchedule,
        onScheduleTypeChange: onScheduleTypeChange
    };
})();
