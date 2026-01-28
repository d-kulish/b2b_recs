/**
 * Deploy Wizard Module
 *
 * A configurable modal component for deploying models to Cloud Run
 * with preset configurations and advanced options.
 *
 * Usage:
 *     // Configure the module (optional)
 *     DeployWizard.configure({
 *         onSuccess: function(result) {
 *             showToast('Model deployed!', 'success');
 *             loadTrainingRuns();
 *         }
 *     });
 *
 *     // Open wizard for a training run
 *     DeployWizard.open(runId);
 */

const DeployWizard = (function() {
    'use strict';

    // =============================================================================
    // CONFIGURATION & STATE
    // =============================================================================

    let config = {
        endpoints: {
            runDetails: '/api/training-runs/{id}/',
            deployCloudRun: '/api/training-runs/{id}/deploy-cloud-run/',
            cloudRunServices: '/api/cloud-run/services/'
        },
        onSuccess: null,
        onError: null
    };

    // Preset configurations
    const PRESETS = {
        development: {
            name: 'Development',
            min_instances: 0,
            max_instances: 2,
            memory: '2Gi',
            cpu: '1',
            timeout: '300'
        },
        production: {
            name: 'Production',
            min_instances: 1,
            max_instances: 10,
            memory: '4Gi',
            cpu: '2',
            timeout: '300'
        },
        high_traffic: {
            name: 'High Traffic',
            min_instances: 2,
            max_instances: 50,
            memory: '8Gi',
            cpu: '4',
            timeout: '300'
        }
    };

    let state = {
        trainingRunId: null,
        trainingRunData: null,
        selectedPreset: 'production',
        presetsExpanded: true,
        advancedExpanded: false,
        deploymentConfig: {
            min_instances: 1,
            max_instances: 10,
            memory: '4Gi',
            cpu: '2',
            timeout: '300'
        },
        isLoading: false,
        // Endpoint selection state
        endpointExpanded: true,
        endpointMode: 'new',  // 'new' or 'existing'
        customNameEnabled: false,
        customName: '',
        selectedService: null,
        availableServices: [],
        servicesLoading: false,
        servicesLoaded: false
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
    // CONFIGURATION
    // =============================================================================

    function configure(options) {
        if (options.endpoints) {
            config.endpoints = { ...config.endpoints, ...options.endpoints };
        }
        if (options.onSuccess) {
            config.onSuccess = options.onSuccess;
        }
        if (options.onError) {
            config.onError = options.onError;
        }
    }

    // =============================================================================
    // MODAL OPEN/CLOSE
    // =============================================================================

    async function open(runId) {
        state.trainingRunId = runId;
        state.selectedPreset = 'production';
        state.advancedExpanded = false;

        // Reset endpoint selection state
        state.endpointExpanded = true;
        state.endpointMode = 'new';
        state.customNameEnabled = false;
        state.customName = '';
        state.selectedService = null;
        state.servicesLoaded = false;

        // Reset to production preset
        applyPreset('production');

        // Show modal
        const modal = document.getElementById('deployWizardModal');
        modal.classList.remove('hidden');

        // Reset endpoint selection UI
        const endpointToggle = document.getElementById('deployEndpointToggle');
        const endpointOptions = document.getElementById('deployEndpointOptions');
        endpointToggle.classList.add('expanded');
        endpointOptions.classList.add('visible');

        // Reset endpoint mode selection
        document.querySelectorAll('.deploy-endpoint-option').forEach(opt => {
            opt.classList.toggle('selected', opt.dataset.mode === 'new');
        });

        // Reset custom name
        document.getElementById('deployCustomNameCheck').checked = false;
        document.getElementById('deployCustomNameContainer').classList.add('hidden');
        document.getElementById('deployCustomNameInput').value = '';

        // Reset services dropdown
        document.getElementById('deployServicesSelect').value = '';
        document.getElementById('deployServiceWarning').classList.add('hidden');

        // Collapse advanced options
        const advancedToggle = document.getElementById('deployAdvancedToggle');
        const advancedOptions = document.getElementById('deployAdvancedOptions');
        advancedToggle.classList.remove('expanded');
        advancedOptions.classList.remove('visible');

        // Load training run data
        await loadTrainingRunData(runId);

        // Update summary
        updateConfigSummary();
    }

    function close() {
        const modal = document.getElementById('deployWizardModal');
        modal.classList.add('hidden');

        // Reset state
        state.trainingRunId = null;
        state.trainingRunData = null;
        state.isLoading = false;

        // Hide loading
        document.getElementById('deployWizardLoading').classList.add('hidden');
    }

    function handleOverlayClick(event) {
        if (event.target === event.currentTarget) {
            close();
        }
    }

    // =============================================================================
    // DATA LOADING
    // =============================================================================

    async function loadTrainingRunData(runId) {
        try {
            const url = buildUrl(config.endpoints.runDetails, { id: runId });
            const response = await fetch(url);
            const data = await response.json();

            if (!data.success) {
                console.error('Failed to load training run:', data.error);
                showToast(data.error || 'Failed to load training run', 'error');
                return;
            }

            state.trainingRunData = data.training_run;

            // Update UI with model info
            const modelName = data.training_run.vertex_model_name ||
                              data.training_run.display_name ||
                              '-';
            const modelVersion = data.training_run.vertex_model_version || '-';
            document.getElementById('deployModelName').textContent = modelName;
            document.getElementById('deployModelVersion').textContent = modelVersion;

            // Update auto-generated service name preview
            const autoServiceName = generateServiceName(modelName);
            document.getElementById('deployAutoServiceName').textContent = autoServiceName;

        } catch (error) {
            console.error('Error loading training run:', error);
            showToast('Failed to load training run data', 'error');
        }
    }

    /**
     * Generate a valid Cloud Run service name from model name.
     */
    function generateServiceName(modelName) {
        if (!modelName || modelName === '-') return '-';
        // Convert to lowercase, replace underscores with hyphens, remove invalid chars
        let name = modelName.toLowerCase()
            .replace(/_/g, '-')
            .replace(/[^a-z0-9-]/g, '')
            .replace(/--+/g, '-')
            .replace(/^-|-$/g, '');
        // Add -serving suffix
        name = name + '-serving';
        // Ensure starts with letter
        if (name && !name[0].match(/[a-z]/)) {
            name = 'm-' + name;
        }
        // Truncate to 63 chars
        return name.substring(0, 63);
    }

    /**
     * Sanitize user input for service name.
     */
    function sanitizeServiceName(input) {
        if (!input) return '';
        return input.toLowerCase()
            .replace(/_/g, '-')
            .replace(/[^a-z0-9-]/g, '')
            .replace(/--+/g, '-')
            .substring(0, 63);
    }

    // =============================================================================
    // PRESET SELECTION
    // =============================================================================

    function selectPreset(presetName) {
        if (!PRESETS[presetName]) return;

        state.selectedPreset = presetName;

        // Update visual selection
        document.querySelectorAll('.deploy-preset-card').forEach(card => {
            card.classList.toggle('selected', card.dataset.preset === presetName);
        });

        // Apply preset values
        applyPreset(presetName);

        // Update summary
        updateConfigSummary();
    }

    function applyPreset(presetName) {
        const preset = PRESETS[presetName];
        if (!preset) return;

        state.deploymentConfig = {
            min_instances: preset.min_instances,
            max_instances: preset.max_instances,
            memory: preset.memory,
            cpu: preset.cpu,
            timeout: preset.timeout
        };

        // Update form inputs
        document.getElementById('deployMinInstances').value = preset.min_instances;
        document.getElementById('deployMaxInstances').value = preset.max_instances;
        document.getElementById('deployMemory').value = preset.memory;
        document.getElementById('deployCpu').value = preset.cpu;
        document.getElementById('deployTimeout').value = preset.timeout;
    }

    // =============================================================================
    // ENDPOINT SELECTION
    // =============================================================================

    function toggleEndpoint() {
        state.endpointExpanded = !state.endpointExpanded;

        const toggle = document.getElementById('deployEndpointToggle');
        const options = document.getElementById('deployEndpointOptions');

        toggle.classList.toggle('expanded', state.endpointExpanded);
        options.classList.toggle('visible', state.endpointExpanded);
    }

    function selectEndpointMode(mode) {
        state.endpointMode = mode;

        // Update visual selection
        document.querySelectorAll('.deploy-endpoint-option').forEach(opt => {
            opt.classList.toggle('selected', opt.dataset.mode === mode);
        });

        // If switching to existing mode, load services
        if (mode === 'existing' && !state.servicesLoaded) {
            loadExistingServices();
        }

        // Show/hide warning for existing service
        const warning = document.getElementById('deployServiceWarning');
        if (mode === 'existing' && state.selectedService) {
            warning.classList.remove('hidden');
        } else {
            warning.classList.add('hidden');
        }

        // Update summary
        updateConfigSummary();
    }

    function toggleCustomName() {
        state.customNameEnabled = !state.customNameEnabled;
        document.getElementById('deployCustomNameCheck').checked = state.customNameEnabled;

        const container = document.getElementById('deployCustomNameContainer');
        container.classList.toggle('hidden', !state.customNameEnabled);

        if (!state.customNameEnabled) {
            state.customName = '';
            document.getElementById('deployCustomNameInput').value = '';
        }

        // Update summary
        updateConfigSummary();
    }

    function updateCustomName(value) {
        state.customName = sanitizeServiceName(value);
        // Update input to show sanitized value
        const input = document.getElementById('deployCustomNameInput');
        if (input.value !== state.customName) {
            const cursorPos = input.selectionStart;
            input.value = state.customName;
            // Try to maintain cursor position
            input.setSelectionRange(
                Math.min(cursorPos, state.customName.length),
                Math.min(cursorPos, state.customName.length)
            );
        }
        updateConfigSummary();
    }

    async function loadExistingServices() {
        if (state.servicesLoading) return;

        state.servicesLoading = true;
        const loadingEl = document.getElementById('deployServicesLoading');
        const selectEl = document.getElementById('deployServicesSelect');

        loadingEl.classList.remove('hidden');
        selectEl.disabled = true;

        try {
            const response = await fetch(config.endpoints.cloudRunServices);
            const data = await response.json();

            if (data.success) {
                state.availableServices = data.services || [];
                state.servicesLoaded = true;

                // Populate dropdown
                selectEl.innerHTML = '<option value="">Select a service...</option>';
                state.availableServices.forEach(svc => {
                    const option = document.createElement('option');
                    option.value = svc.name;
                    option.textContent = svc.is_ml_serving
                        ? `${svc.name} (ML Serving)`
                        : svc.name;
                    selectEl.appendChild(option);
                });

                if (state.availableServices.length === 0) {
                    const option = document.createElement('option');
                    option.value = '';
                    option.textContent = 'No services found';
                    option.disabled = true;
                    selectEl.appendChild(option);
                }
            } else {
                console.error('Failed to load services:', data.error);
            }
        } catch (error) {
            console.error('Error loading services:', error);
        } finally {
            state.servicesLoading = false;
            loadingEl.classList.add('hidden');
            selectEl.disabled = false;
        }
    }

    function selectExistingService(serviceName) {
        state.selectedService = serviceName || null;

        // Show/hide warning
        const warning = document.getElementById('deployServiceWarning');
        if (state.endpointMode === 'existing' && state.selectedService) {
            warning.classList.remove('hidden');
        } else {
            warning.classList.add('hidden');
        }

        updateConfigSummary();
    }

    /**
     * Get the effective service name based on current selection.
     * Returns null if using auto-generated name (backend will generate).
     */
    function getEffectiveServiceName() {
        if (state.endpointMode === 'existing') {
            return state.selectedService || null;
        } else if (state.customNameEnabled && state.customName) {
            return state.customName;
        }
        // Return null to let backend generate default name
        return null;
    }

    // =============================================================================
    // PRESETS TOGGLE
    // =============================================================================

    function togglePresets() {
        state.presetsExpanded = !state.presetsExpanded;

        const toggle = document.getElementById('deployPresetToggle');
        const options = document.getElementById('deployPresetOptions');

        toggle.classList.toggle('expanded', state.presetsExpanded);
        options.classList.toggle('visible', state.presetsExpanded);
    }

    // =============================================================================
    // ADVANCED OPTIONS
    // =============================================================================

    function toggleAdvanced() {
        state.advancedExpanded = !state.advancedExpanded;

        const toggle = document.getElementById('deployAdvancedToggle');
        const options = document.getElementById('deployAdvancedOptions');

        toggle.classList.toggle('expanded', state.advancedExpanded);
        options.classList.toggle('visible', state.advancedExpanded);
    }

    function updateConfig(key, value) {
        // Parse numeric values
        if (key === 'min_instances' || key === 'max_instances') {
            value = parseInt(value, 10) || 0;
        }

        state.deploymentConfig[key] = value;

        // Clear preset selection when manually editing
        state.selectedPreset = null;
        document.querySelectorAll('.deploy-preset-card').forEach(card => {
            card.classList.remove('selected');
        });

        // Update summary
        updateConfigSummary();
    }

    // =============================================================================
    // CONFIGURATION SUMMARY
    // =============================================================================

    function updateConfigSummary() {
        const cfg = state.deploymentConfig;

        // Update endpoint info
        let endpointName = '-';
        let isNewEndpoint = true;

        if (state.endpointMode === 'existing' && state.selectedService) {
            endpointName = state.selectedService;
            isNewEndpoint = false;
        } else if (state.customNameEnabled && state.customName) {
            endpointName = state.customName;
        } else if (state.trainingRunData) {
            const modelName = state.trainingRunData.vertex_model_name ||
                              state.trainingRunData.display_name ||
                              '-';
            endpointName = generateServiceName(modelName);
        }

        document.getElementById('deploySummaryEndpoint').textContent = endpointName;
        const badge = document.getElementById('deploySummaryBadge');
        badge.textContent = isNewEndpoint ? 'new' : 'update';
        badge.classList.toggle('new', isNewEndpoint);
        badge.classList.toggle('update', !isNewEndpoint);

        // Update config values
        document.getElementById('deploySummaryInstances').textContent =
            `${cfg.min_instances}-${cfg.max_instances}`;
        document.getElementById('deploySummaryMemory').textContent = cfg.memory;
        document.getElementById('deploySummaryCpu').textContent = `${cfg.cpu} vCPU`;
        document.getElementById('deploySummaryTimeout').textContent = `${cfg.timeout}s`;
    }

    // =============================================================================
    // DEPLOY
    // =============================================================================

    async function deploy() {
        if (!state.trainingRunId) {
            showToast('No training run selected', 'error');
            return;
        }

        // Validate endpoint selection for existing mode
        if (state.endpointMode === 'existing' && !state.selectedService) {
            showToast('Please select an existing service to update', 'error');
            return;
        }

        // Show loading
        state.isLoading = true;
        document.getElementById('deployWizardLoading').classList.remove('hidden');
        document.getElementById('deployWizardDeployBtn').disabled = true;

        try {
            const url = buildUrl(config.endpoints.deployCloudRun, { id: state.trainingRunId });

            // Build request body with optional service_name
            const requestBody = {
                deployment_config: state.deploymentConfig
            };

            const serviceName = getEffectiveServiceName();
            if (serviceName) {
                requestBody.service_name = serviceName;
            }

            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify(requestBody)
            });

            const data = await response.json();

            if (data.success) {
                showToast(data.message || 'Model deployed to Cloud Run successfully', 'success');
                close();

                // Call success callback
                if (config.onSuccess) {
                    config.onSuccess(data);
                }
            } else {
                showToast(data.error || 'Failed to deploy model', 'error');
                if (config.onError) {
                    config.onError(data.error);
                }
            }
        } catch (error) {
            console.error('Error deploying model:', error);
            showToast('Failed to deploy model to Cloud Run', 'error');
            if (config.onError) {
                config.onError(error.message);
            }
        } finally {
            state.isLoading = false;
            document.getElementById('deployWizardLoading').classList.add('hidden');
            document.getElementById('deployWizardDeployBtn').disabled = false;
        }
    }

    // =============================================================================
    // PUBLIC API
    // =============================================================================

    return {
        configure: configure,
        open: open,
        close: close,
        handleOverlayClick: handleOverlayClick,
        selectPreset: selectPreset,
        togglePresets: togglePresets,
        toggleAdvanced: toggleAdvanced,
        updateConfig: updateConfig,
        deploy: deploy,
        // Endpoint selection
        toggleEndpoint: toggleEndpoint,
        selectEndpointMode: selectEndpointMode,
        toggleCustomName: toggleCustomName,
        updateCustomName: updateCustomName,
        selectExistingService: selectExistingService,
        // Expose state for debugging
        getState: function() { return state; },
        getPresets: function() { return PRESETS; }
    };
})();
