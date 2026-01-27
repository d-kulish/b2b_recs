/**
 * Schedule Modal Module
 *
 * A reusable modal component for creating training schedules from existing
 * training runs or registered models.
 *
 * Usage:
 *     // Configure the module (optional)
 *     ScheduleModal.configure({
 *         onSuccess: function(schedule) {
 *             showToast('Schedule created!', 'success');
 *             loadTrainingRuns();
 *         }
 *     });
 *
 *     // Open modal for a training run
 *     ScheduleModal.openForTrainingRun(runId);
 *
 *     // Open modal for a registered model (future use)
 *     ScheduleModal.openForModel(modelId);
 */

const ScheduleModal = (function() {
    'use strict';

    // =============================================================================
    // CONFIGURATION & STATE
    // =============================================================================

    let config = {
        endpoints: {
            preview: '/api/training/schedules/preview/',
            createFromRun: '/api/training/schedules/from-run/',
            createFromModel: '/api/training/schedules/',
            detail: '/api/training/schedules/{id}/',
            update: '/api/training/schedules/{id}/'
        },
        onSuccess: null,
        onError: null
    };

    let state = {
        mode: null,         // 'training_run', 'model', 'registered_model', 'wizard', or 'edit'
        sourceId: null,
        sourceData: null,   // Preview data from API
        wizardConfig: null, // Config from TrainingWizard (for mode='wizard')
        editScheduleId: null, // Track schedule being edited (for mode='edit')
        scheduleConfig: {
            name: '',
            description: '',
            scheduleType: 'daily',
            scheduledDatetime: null,
            scheduleTime: '09:00',
            scheduleMinute: 0,           // For hourly (0, 15, 30, 45)
            scheduleDayOfWeek: 0,
            scheduleDayOfMonth: 1,       // For monthly (1-28)
            scheduleTimezone: 'UTC'
        },
        isLoading: false,
        flatpickrDatetime: null,
        flatpickrTime: null,
        flatpickrMonthlyTime: null
    };

    // Day names for display
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

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
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

    async function openForTrainingRun(runId) {
        state.mode = 'training_run';
        state.sourceId = runId;

        // Reset state
        resetState();

        // Show modal
        const modal = document.getElementById('scheduleModal');
        modal.classList.remove('hidden');

        // Update subtitle
        document.getElementById('scheduleModalSubtitle').textContent =
            `Creating schedule from Training Run #${runId}`;

        // Initialize pickers
        initializePickers();

        // Load preview data
        await loadPreviewData(runId);
    }

    async function openForModel(modelId) {
        state.mode = 'model';
        state.sourceId = modelId;

        // Reset state
        resetState();

        // Show modal
        const modal = document.getElementById('scheduleModal');
        modal.classList.remove('hidden');

        // Update subtitle
        document.getElementById('scheduleModalSubtitle').textContent =
            `Creating retraining schedule for model`;

        // Initialize pickers
        initializePickers();

        // Load the registered model details and its latest training run
        await loadRegisteredModelData(modelId);
    }

    /**
     * Open modal for a RegisteredModel entity.
     * This is the new way to create schedules for models that already exist.
     */
    async function openForRegisteredModel(registeredModelId) {
        state.mode = 'registered_model';
        state.sourceId = registeredModelId;

        // Reset state
        resetState();

        // Show modal
        const modal = document.getElementById('scheduleModal');
        modal.classList.remove('hidden');

        // Update subtitle
        document.getElementById('scheduleModalSubtitle').textContent =
            `Creating retraining schedule`;

        // Initialize pickers
        initializePickers();

        // Load registered model details
        await loadRegisteredModelDetails(registeredModelId);
    }

    /**
     * Open modal for creating a schedule from Training Wizard configuration.
     * This is used when the user clicks "Schedule" in the training wizard (step 3).
     *
     * @param {Object} wizardConfig - Configuration built from wizard state
     * @param {string} wizardConfig.model_name - Model name from Step 1
     * @param {string} wizardConfig.description - Model description
     * @param {number} wizardConfig.dataset_id - Dataset ID
     * @param {number} wizardConfig.feature_config_id - Feature config ID
     * @param {number} wizardConfig.model_config_id - Model config ID
     * @param {number} wizardConfig.base_experiment_id - Base experiment ID
     * @param {Object} wizardConfig.training_params - Training parameters
     * @param {Object} wizardConfig.gpu_config - GPU configuration
     * @param {Object} wizardConfig.evaluator_config - Evaluator configuration
     */
    function openForWizardConfig(wizardConfig) {
        state.mode = 'wizard';
        state.sourceId = null;
        state.wizardConfig = wizardConfig;

        // Reset schedule config but keep wizardConfig
        state.scheduleConfig = {
            name: '',
            description: '',
            scheduleType: 'daily',
            scheduledDatetime: null,
            scheduleTime: '09:00',
            scheduleMinute: 0,
            scheduleDayOfWeek: 0,
            scheduleDayOfMonth: 1,
            scheduleTimezone: 'UTC'
        };

        // Show modal
        const modal = document.getElementById('scheduleModal');
        modal.classList.remove('hidden');

        // Update subtitle for wizard context
        document.getElementById('scheduleModalSubtitle').textContent =
            'Creating schedule for new model';

        // Initialize pickers
        initializePickers();

        // Display model name from wizard
        const modelName = wizardConfig.model_name || '-';
        document.getElementById('scheduleModelName').textContent = modelName;

        // Pre-fill schedule name based on model name
        const suggestedName = `${wizardConfig.model_name || 'Model'} - Retraining`;
        document.getElementById('scheduleNameInput').value = suggestedName;
        state.scheduleConfig.name = suggestedName;

        // Update next run preview
        updateNextRunPreview();
    }

    /**
     * Open modal for editing an existing schedule.
     * Only schedule timing fields can be modified.
     *
     * @param {number} scheduleId - ID of the schedule to edit
     */
    async function openForEdit(scheduleId) {
        state.mode = 'edit';
        state.editScheduleId = scheduleId;
        state.sourceId = null;

        // Reset schedule config
        state.scheduleConfig = {
            name: '',
            description: '',
            scheduleType: 'daily',
            scheduledDatetime: null,
            scheduleTime: '09:00',
            scheduleMinute: 0,
            scheduleDayOfWeek: 0,
            scheduleDayOfMonth: 1,
            scheduleTimezone: 'UTC'
        };

        // Show modal
        const modal = document.getElementById('scheduleModal');
        modal.classList.remove('hidden');

        // Update title and button for edit mode
        const titleEl = document.getElementById('scheduleModalTitle');
        const subtitleEl = document.getElementById('scheduleModalSubtitle');
        const btnTextEl = document.getElementById('scheduleCreateBtnText');

        if (titleEl) titleEl.textContent = 'Edit Training Schedule';
        if (subtitleEl) subtitleEl.textContent = 'Modifying schedule timing';
        if (btnTextEl) btnTextEl.textContent = 'Save';

        // Initialize pickers
        initializePickers();

        // Load schedule data
        await loadScheduleForEdit(scheduleId);
    }

    /**
     * Load schedule details and populate form for editing.
     */
    async function loadScheduleForEdit(scheduleId) {
        try {
            const url = config.endpoints.detail.replace('{id}', scheduleId);
            const response = await fetch(url);
            const data = await response.json();

            if (!data.success) {
                console.error('Failed to load schedule:', data.error);
                showToast(data.error || 'Failed to load schedule', 'error');
                close();
                return;
            }

            const schedule = data.schedule;

            // Check if schedule can be edited
            if (schedule.status !== 'active' && schedule.status !== 'paused') {
                showToast(`Cannot edit schedule in ${schedule.status} status`, 'error');
                close();
                return;
            }

            // Update subtitle with schedule name
            const subtitleEl = document.getElementById('scheduleModalSubtitle');
            if (subtitleEl) subtitleEl.textContent = `Editing schedule: ${schedule.name}`;

            // Display model name
            const modelName = schedule.registered_model_name || '-';
            document.getElementById('scheduleModelName').textContent = modelName;

            // Populate form with existing values
            populateFormForEdit(schedule);

            // Update next run preview
            updateNextRunPreview();

        } catch (error) {
            console.error('Error loading schedule:', error);
            showToast('Failed to load schedule', 'error');
            close();
        }
    }

    /**
     * Populate the form fields with existing schedule data for editing.
     */
    function populateFormForEdit(schedule) {
        // Set name and description
        document.getElementById('scheduleNameInput').value = schedule.name || '';
        document.getElementById('scheduleDescriptionInput').value = schedule.description || '';
        state.scheduleConfig.name = schedule.name || '';
        state.scheduleConfig.description = schedule.description || '';

        // Set schedule type and show appropriate options
        const scheduleType = schedule.schedule_type || 'daily';
        state.scheduleConfig.scheduleType = scheduleType;
        onScheduleTypeChange(scheduleType);

        // Set timezone
        const timezone = schedule.schedule_timezone || 'UTC';
        document.getElementById('scheduleTimezoneSelect').value = timezone;
        state.scheduleConfig.scheduleTimezone = timezone;

        // Set type-specific values
        if (scheduleType === 'once') {
            // Set datetime
            if (schedule.scheduled_datetime && state.flatpickrDatetime) {
                state.flatpickrDatetime.setDate(new Date(schedule.scheduled_datetime), true);
                state.scheduleConfig.scheduledDatetime = schedule.scheduled_datetime;
            }
        } else if (scheduleType === 'hourly') {
            // Set minute (extract from schedule_time which is "HH:MM")
            const timeStr = schedule.schedule_time || '00:00';
            const minute = parseInt(timeStr.split(':')[1]) || 0;
            // Round to nearest 15 for the buttons (0, 15, 30, 45)
            const roundedMinute = Math.round(minute / 15) * 15;
            state.scheduleConfig.scheduleMinute = roundedMinute >= 60 ? 45 : roundedMinute;
            selectMinute(state.scheduleConfig.scheduleMinute);
        } else if (scheduleType === 'daily' || scheduleType === 'weekly') {
            // Set time
            const timeStr = schedule.schedule_time || '09:00';
            if (state.flatpickrTime) {
                state.flatpickrTime.setDate(timeStr, true);
            }
            state.scheduleConfig.scheduleTime = timeStr;

            // For weekly, set day of week
            if (scheduleType === 'weekly') {
                const dayOfWeek = schedule.schedule_day_of_week ?? 0;
                state.scheduleConfig.scheduleDayOfWeek = dayOfWeek;
                selectDay(dayOfWeek);
            }
        } else if (scheduleType === 'monthly') {
            // Set time
            const timeStr = schedule.schedule_time || '09:00';
            if (state.flatpickrMonthlyTime) {
                state.flatpickrMonthlyTime.setDate(timeStr, true);
            }
            state.scheduleConfig.scheduleTime = timeStr;

            // Set day of month
            const dayOfMonth = schedule.schedule_day_of_month || 1;
            state.scheduleConfig.scheduleDayOfMonth = dayOfMonth;
            selectDayOfMonth(dayOfMonth);
        }
    }

    async function loadRegisteredModelData(trainingRunId) {
        // This is called when openForModel is used with a training run ID
        // (for backward compatibility with ModelsRegistry)
        try {
            const response = await fetch(`${config.endpoints.preview}?source_run_id=${trainingRunId}`);
            const data = await response.json();

            if (!data.success) {
                console.error('Failed to load preview:', data.error);
                showToast(data.error || 'Failed to load configuration', 'error');
                return;
            }

            state.sourceData = data.preview;
            state.sourceId = trainingRunId;  // Use training run ID

            // Populate model name
            const modelName = data.preview.vertex_model_name || '-';
            document.getElementById('scheduleModelName').textContent = modelName;

            // Auto-generate schedule name suggestion
            const suggestedName = `${data.preview.vertex_model_name || 'Model'} - Retraining`;
            document.getElementById('scheduleNameInput').placeholder = suggestedName;

            // Update preview
            updateNextRunPreview();
        } catch (error) {
            console.error('Error loading model data:', error);
            showToast('Failed to load model data', 'error');
        }
    }

    async function loadRegisteredModelDetails(registeredModelId) {
        try {
            // Get registered model details
            const response = await fetch(`/api/registered-models/${registeredModelId}/`);
            const data = await response.json();

            if (!data.success) {
                console.error('Failed to load registered model:', data.error);
                showToast(data.error || 'Failed to load model details', 'error');
                return;
            }

            const regModel = data.registered_model;

            // Check if model already has a schedule
            if (regModel.has_schedule) {
                showToast('This model already has a schedule', 'error');
                close();
                return;
            }

            // If there's a latest version, use it as the source for preview
            if (regModel.latest_version_id) {
                // Update sourceId to the TrainingRun ID - this is required for creating the schedule
                // The schedule API expects source_training_run_id, not registered_model_id
                state.sourceId = regModel.latest_version_id;
                await loadPreviewData(regModel.latest_version_id);
            } else {
                // Model has no versions yet - cannot create schedule without configuration
                showToast('This model has no training runs to base a schedule on', 'error');
                close();
                return;
            }

            // Store registered model info for reference
            state.registeredModelId = registeredModelId;
            state.registeredModelName = regModel.model_name;

        } catch (error) {
            console.error('Error loading registered model:', error);
            showToast('Failed to load model details', 'error');
        }
    }

    function close() {
        const modal = document.getElementById('scheduleModal');
        modal.classList.add('hidden');

        // Destroy pickers
        destroyPickers();

        // Reset state
        resetState();
    }

    function resetState() {
        state.sourceData = null;
        state.editScheduleId = null;
        state.scheduleConfig = {
            name: '',
            description: '',
            scheduleType: 'daily',
            scheduledDatetime: null,
            scheduleTime: '09:00',
            scheduleMinute: 0,
            scheduleDayOfWeek: 0,
            scheduleDayOfMonth: 1,
            scheduleTimezone: 'UTC'
        };
        state.isLoading = false;

        // Reset title and button text to defaults
        const titleEl = document.getElementById('scheduleModalTitle');
        const btnTextEl = document.getElementById('scheduleCreateBtnText');
        if (titleEl) titleEl.textContent = 'Create Training Schedule';
        if (btnTextEl) btnTextEl.textContent = 'Create';

        // Reset form
        document.getElementById('scheduleNameInput').value = '';
        document.getElementById('scheduleDescriptionInput').value = '';
        document.getElementById('scheduleTimezoneSelect').value = 'UTC';

        // Reset type tabs
        document.querySelectorAll('.schedule-type-tab').forEach(tab => {
            tab.classList.remove('active');
            if (tab.dataset.type === 'daily') {
                tab.classList.add('active');
            }
        });

        // Reset day selector
        document.querySelectorAll('.schedule-day-btn').forEach(btn => {
            btn.classList.remove('active');
            if (btn.dataset.day === '0') {
                btn.classList.add('active');
            }
        });

        // Reset minute selector
        document.querySelectorAll('.schedule-minute-btn').forEach(btn => {
            btn.classList.remove('active');
            if (btn.dataset.minute === '0') {
                btn.classList.add('active');
            }
        });

        // Reset day of month selector (grid buttons)
        document.querySelectorAll('.schedule-dom-btn').forEach(btn => {
            btn.classList.remove('active');
            if (btn.dataset.day === '1') {
                btn.classList.add('active');
            }
        });

        // Show recurring options, hide other options
        document.getElementById('scheduleOptionsOnce').style.display = 'none';
        document.getElementById('scheduleOptionsHourly').style.display = 'none';
        document.getElementById('scheduleOptionsMonthly').style.display = 'none';
        document.getElementById('scheduleOptionsRecurring').style.display = 'block';
        document.getElementById('scheduleDayOfWeekGroup').style.display = 'none';

        // Reset preview
        document.getElementById('scheduleNextRunPreview').textContent = '-';

        // Hide loading
        document.getElementById('scheduleModalLoading').classList.add('hidden');
    }

    function handleOverlayClick(event) {
        if (event.target === event.currentTarget) {
            close();
        }
    }

    // =============================================================================
    // DATA LOADING
    // =============================================================================

    async function loadPreviewData(runId) {
        try {
            const response = await fetch(`${config.endpoints.preview}?source_run_id=${runId}`);
            const data = await response.json();

            if (!data.success) {
                console.error('Failed to load preview:', data.error);
                showToast(data.error || 'Failed to load configuration', 'error');
                return;
            }

            state.sourceData = data.preview;

            // Populate model name
            const modelName = data.preview.vertex_model_name || '-';
            document.getElementById('scheduleModelName').textContent = modelName;

            // Auto-generate schedule name suggestion
            const suggestedName = `${data.preview.vertex_model_name || 'Model'} - Retraining`;
            document.getElementById('scheduleNameInput').placeholder = suggestedName;

            // Update preview
            updateNextRunPreview();

        } catch (error) {
            console.error('Error loading preview:', error);
            showToast('Failed to load configuration', 'error');
        }
    }

    // =============================================================================
    // PICKERS INITIALIZATION
    // =============================================================================

    function initializePickers() {
        // Check if flatpickr is available
        if (typeof flatpickr === 'undefined') {
            console.warn('Flatpickr not loaded, using native inputs');
            return;
        }

        // Datetime picker for one-time schedules
        state.flatpickrDatetime = flatpickr('#scheduleDatetimeInput', {
            enableTime: true,
            dateFormat: 'Y-m-d H:i',
            minDate: 'today',
            time_24hr: true,
            onChange: function(selectedDates, dateStr) {
                state.scheduleConfig.scheduledDatetime = dateStr;
                updateNextRunPreview();
            }
        });

        // Time picker for recurring schedules
        state.flatpickrTime = flatpickr('#scheduleTimeInput', {
            enableTime: true,
            noCalendar: true,
            dateFormat: 'H:i',
            time_24hr: true,
            defaultDate: '09:00',
            onChange: function(selectedDates, dateStr) {
                state.scheduleConfig.scheduleTime = dateStr;
                updateNextRunPreview();
            }
        });

        // Time picker for monthly schedules
        state.flatpickrMonthlyTime = flatpickr('#scheduleMonthlyTimeInput', {
            enableTime: true,
            noCalendar: true,
            dateFormat: 'H:i',
            time_24hr: true,
            defaultDate: '09:00',
            onChange: function(selectedDates, dateStr) {
                state.scheduleConfig.scheduleTime = dateStr;
                updateNextRunPreview();
            }
        });
    }

    function destroyPickers() {
        if (state.flatpickrDatetime) {
            state.flatpickrDatetime.destroy();
            state.flatpickrDatetime = null;
        }
        if (state.flatpickrTime) {
            state.flatpickrTime.destroy();
            state.flatpickrTime = null;
        }
        if (state.flatpickrMonthlyTime) {
            state.flatpickrMonthlyTime.destroy();
            state.flatpickrMonthlyTime = null;
        }
    }

    // =============================================================================
    // SCHEDULE TYPE & OPTIONS
    // =============================================================================

    function onScheduleTypeChange(type) {
        state.scheduleConfig.scheduleType = type;

        // Update tabs
        document.querySelectorAll('.schedule-type-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.type === type);
        });

        // Show/hide appropriate options
        const onceOptions = document.getElementById('scheduleOptionsOnce');
        const hourlyOptions = document.getElementById('scheduleOptionsHourly');
        const recurringOptions = document.getElementById('scheduleOptionsRecurring');
        const monthlyOptions = document.getElementById('scheduleOptionsMonthly');
        const dayOfWeekGroup = document.getElementById('scheduleDayOfWeekGroup');

        // Hide all first
        onceOptions.style.display = 'none';
        hourlyOptions.style.display = 'none';
        recurringOptions.style.display = 'none';
        monthlyOptions.style.display = 'none';

        if (type === 'once') {
            onceOptions.style.display = 'block';
        } else if (type === 'hourly') {
            hourlyOptions.style.display = 'block';
        } else if (type === 'daily') {
            recurringOptions.style.display = 'block';
            dayOfWeekGroup.style.display = 'none';
        } else if (type === 'weekly') {
            recurringOptions.style.display = 'block';
            dayOfWeekGroup.style.display = 'block';
        } else if (type === 'monthly') {
            monthlyOptions.style.display = 'block';
        }

        updateNextRunPreview();
    }

    function selectDay(day) {
        state.scheduleConfig.scheduleDayOfWeek = day;

        // Update day buttons
        document.querySelectorAll('.schedule-day-btn').forEach(btn => {
            btn.classList.toggle('active', parseInt(btn.dataset.day) === day);
        });

        updateNextRunPreview();
    }

    function selectMinute(minute) {
        state.scheduleConfig.scheduleMinute = minute;

        // Update minute buttons
        document.querySelectorAll('.schedule-minute-btn').forEach(btn => {
            btn.classList.toggle('active', parseInt(btn.dataset.minute) === minute);
        });

        updateNextRunPreview();
    }

    function selectDayOfMonth(day) {
        state.scheduleConfig.scheduleDayOfMonth = parseInt(day);

        // Update day of month buttons
        document.querySelectorAll('.schedule-dom-btn').forEach(btn => {
            btn.classList.toggle('active', parseInt(btn.dataset.day) === parseInt(day));
        });

        updateNextRunPreview();
    }

    // =============================================================================
    // NEXT RUN PREVIEW
    // =============================================================================

    function updateNextRunPreview() {
        const previewEl = document.getElementById('scheduleNextRunPreview');
        const type = state.scheduleConfig.scheduleType;
        const timezone = document.getElementById('scheduleTimezoneSelect').value;

        let previewText = '';

        if (type === 'once') {
            const datetime = state.scheduleConfig.scheduledDatetime;
            if (datetime) {
                const date = new Date(datetime);
                previewText = formatDateTime(date) + ` (${timezone})`;
            } else {
                previewText = 'Select date and time';
            }
        } else if (type === 'hourly') {
            const minute = state.scheduleConfig.scheduleMinute || 0;
            previewText = `Every hour at :${String(minute).padStart(2, '0')} (${timezone})`;
        } else if (type === 'daily') {
            const time = state.scheduleConfig.scheduleTime || '09:00';
            previewText = `Daily at ${time} (${timezone})`;
        } else if (type === 'weekly') {
            const time = state.scheduleConfig.scheduleTime || '09:00';
            const day = DAY_NAMES[state.scheduleConfig.scheduleDayOfWeek];
            previewText = `Every ${day} at ${time} (${timezone})`;
        } else if (type === 'monthly') {
            const time = state.scheduleConfig.scheduleTime || '09:00';
            const day = state.scheduleConfig.scheduleDayOfMonth || 1;
            const suffix = getDaySuffix(day);
            previewText = `Monthly on the ${day}${suffix} at ${time} (${timezone})`;
        }

        previewEl.textContent = previewText;
    }

    function getDaySuffix(day) {
        if (day >= 11 && day <= 13) return 'th';
        switch (day % 10) {
            case 1: return 'st';
            case 2: return 'nd';
            case 3: return 'rd';
            default: return 'th';
        }
    }

    function formatDateTime(date) {
        if (!date) return '-';
        return date.toLocaleDateString('en-US', {
            weekday: 'short',
            month: 'short',
            day: 'numeric',
            year: 'numeric'
        }) + ' at ' + date.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
        });
    }

    // =============================================================================
    // CREATE SCHEDULE
    // =============================================================================

    async function create() {
        // Validate schedule name
        const scheduleName = document.getElementById('scheduleNameInput').value.trim();
        if (!scheduleName) {
            showToast('Please enter a schedule name', 'error');
            document.getElementById('scheduleNameInput').focus();
            return;
        }

        const type = state.scheduleConfig.scheduleType;
        const timezone = document.getElementById('scheduleTimezoneSelect').value;
        const scheduleDescription = document.getElementById('scheduleDescriptionInput').value.trim();

        // Validate type-specific fields
        if (type === 'once') {
            if (!state.scheduleConfig.scheduledDatetime) {
                showToast('Please select a date and time', 'error');
                return;
            }
        }

        // Determine endpoint, method, and build request data based on mode
        let endpoint;
        let method = 'POST';
        let requestData;

        if (state.mode === 'edit') {
            // Editing existing schedule - use PUT
            endpoint = config.endpoints.update.replace('{id}', state.editScheduleId);
            method = 'PUT';

            // Only send schedule timing fields (not training config)
            requestData = {
                name: scheduleName,
                description: scheduleDescription,
                schedule_type: type,
                schedule_timezone: timezone
            };

            // Add type-specific schedule fields
            if (type === 'once') {
                const dt = new Date(state.scheduleConfig.scheduledDatetime);
                requestData.scheduled_datetime = dt.toISOString();
            } else if (type === 'hourly') {
                requestData.schedule_time = `00:${String(state.scheduleConfig.scheduleMinute).padStart(2, '0')}`;
            } else if (type === 'monthly') {
                requestData.schedule_time = state.scheduleConfig.scheduleTime || '09:00';
                requestData.schedule_day_of_month = state.scheduleConfig.scheduleDayOfMonth;
            } else {
                requestData.schedule_time = state.scheduleConfig.scheduleTime || '09:00';
                if (type === 'weekly') {
                    requestData.schedule_day_of_week = state.scheduleConfig.scheduleDayOfWeek;
                }
            }
        } else if (state.mode === 'wizard') {
            // Creating from wizard - use full config endpoint
            endpoint = config.endpoints.createFromModel;  // /api/training/schedules/
            const wc = state.wizardConfig;

            requestData = {
                // Model identity - use model_name from wizard
                name: wc.model_name,
                description: wc.description || '',

                // Data configuration from wizard
                dataset_id: wc.dataset_id,
                feature_config_id: wc.feature_config_id,
                model_config_id: wc.model_config_id,
                base_experiment_id: wc.base_experiment_id,

                // Training configuration from wizard
                training_params: wc.training_params,
                gpu_config: wc.gpu_config,
                evaluator_config: wc.evaluator_config,

                // Schedule-specific fields
                schedule_name: scheduleName,
                schedule_description: scheduleDescription,
                schedule_type: type,
                schedule_timezone: timezone
            };

            // Add type-specific schedule fields
            if (type === 'once') {
                const dt = new Date(state.scheduleConfig.scheduledDatetime);
                requestData.scheduled_datetime = dt.toISOString();
            } else if (type === 'hourly') {
                requestData.schedule_time = `00:${String(state.scheduleConfig.scheduleMinute).padStart(2, '0')}`;
            } else if (type === 'monthly') {
                requestData.schedule_time = state.scheduleConfig.scheduleTime || '09:00';
                requestData.schedule_day_of_month = state.scheduleConfig.scheduleDayOfMonth;
            } else {
                requestData.schedule_time = state.scheduleConfig.scheduleTime || '09:00';
                if (type === 'weekly') {
                    requestData.schedule_day_of_week = state.scheduleConfig.scheduleDayOfWeek;
                }
            }
        } else {
            // Creating from existing training run
            endpoint = config.endpoints.createFromRun;  // /api/training/schedules/from-run/
            requestData = {
                source_training_run_id: state.sourceId,
                name: scheduleName,
                description: scheduleDescription,
                schedule_type: type,
                schedule_timezone: timezone
            };

            // Add type-specific schedule fields
            if (type === 'once') {
                const dt = new Date(state.scheduleConfig.scheduledDatetime);
                requestData.scheduled_datetime = dt.toISOString();
            } else if (type === 'hourly') {
                requestData.schedule_time = `00:${String(state.scheduleConfig.scheduleMinute).padStart(2, '0')}`;
            } else if (type === 'monthly') {
                requestData.schedule_time = state.scheduleConfig.scheduleTime || '09:00';
                requestData.schedule_day_of_month = state.scheduleConfig.scheduleDayOfMonth;
            } else {
                requestData.schedule_time = state.scheduleConfig.scheduleTime || '09:00';
                if (type === 'weekly') {
                    requestData.schedule_day_of_week = state.scheduleConfig.scheduleDayOfWeek;
                }
            }
        }

        // Determine success message based on mode
        const isEdit = state.mode === 'edit';
        const successMessage = isEdit
            ? `Schedule "${scheduleName}" updated successfully`
            : `Schedule "${scheduleName}" created successfully`;
        const errorMessage = isEdit
            ? 'Failed to update schedule'
            : 'Failed to create schedule';

        // Show loading
        state.isLoading = true;
        document.getElementById('scheduleModalLoading').classList.remove('hidden');
        document.getElementById('scheduleCreateBtn').disabled = true;

        try {
            const response = await fetch(endpoint, {
                method: method,
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify(requestData)
            });

            const data = await response.json();

            if (data.success) {
                showToast(data.message || successMessage, 'success');
                close();

                // Call success callback
                if (config.onSuccess) {
                    config.onSuccess(data.schedule);
                }
            } else {
                showToast(data.error || errorMessage, 'error');
                if (config.onError) {
                    config.onError(data.error);
                }
            }
        } catch (error) {
            console.error('Error with schedule:', error);
            showToast(errorMessage, 'error');
            if (config.onError) {
                config.onError(error.message);
            }
        } finally {
            state.isLoading = false;
            document.getElementById('scheduleModalLoading').classList.add('hidden');
            document.getElementById('scheduleCreateBtn').disabled = false;
        }
    }

    // =============================================================================
    // EVENT LISTENERS
    // =============================================================================

    // Listen for timezone changes
    document.addEventListener('DOMContentLoaded', function() {
        const timezoneSelect = document.getElementById('scheduleTimezoneSelect');
        if (timezoneSelect) {
            timezoneSelect.addEventListener('change', function() {
                state.scheduleConfig.scheduleTimezone = this.value;
                updateNextRunPreview();
            });
        }
    });

    // =============================================================================
    // PUBLIC API
    // =============================================================================

    return {
        configure: configure,
        openForTrainingRun: openForTrainingRun,
        openForModel: openForModel,
        openForRegisteredModel: openForRegisteredModel,
        openForWizardConfig: openForWizardConfig,  // For Training Wizard integration
        openForEdit: openForEdit,  // For editing existing schedules
        close: close,
        handleOverlayClick: handleOverlayClick,
        onScheduleTypeChange: onScheduleTypeChange,
        selectDay: selectDay,
        selectMinute: selectMinute,
        selectDayOfMonth: selectDayOfMonth,
        create: create,
        // Expose state for debugging
        getState: function() { return state; }
    };
})();
