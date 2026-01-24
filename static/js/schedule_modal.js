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
            createFromModel: '/api/training/schedules/'
        },
        onSuccess: null,
        onError: null
    };

    let state = {
        mode: null,         // 'training_run' or 'model'
        sourceId: null,
        sourceData: null,   // Preview data from API
        scheduleConfig: {
            name: '',
            description: '',
            scheduleType: 'daily',
            scheduledDatetime: null,
            scheduleTime: '09:00',
            scheduleDayOfWeek: 0,
            scheduleTimezone: 'UTC'
        },
        isLoading: false,
        flatpickrDatetime: null,
        flatpickrTime: null
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

        // For model mode, we need to get the model's source training run
        // For now, show a placeholder
        document.getElementById('scheduleSourceName').textContent = `Model ID: ${modelId}`;
        document.getElementById('scheduleSourceDataset').textContent = '-';
        document.getElementById('scheduleSourceFeatures').textContent = '-';
        document.getElementById('scheduleSourceModel').textContent = '-';
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
        state.scheduleConfig = {
            name: '',
            description: '',
            scheduleType: 'daily',
            scheduledDatetime: null,
            scheduleTime: '09:00',
            scheduleDayOfWeek: 0,
            scheduleTimezone: 'UTC'
        };
        state.isLoading = false;

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

        // Show recurring options, hide once options
        document.getElementById('scheduleOptionsOnce').style.display = 'none';
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

            // Populate source card
            document.getElementById('scheduleSourceName').textContent =
                data.preview.source_run_display_name || `Run #${data.preview.source_run_number}`;
            document.getElementById('scheduleSourceDataset').textContent =
                data.preview.dataset_name || '-';
            document.getElementById('scheduleSourceFeatures').textContent =
                data.preview.feature_config_name || '-';
            document.getElementById('scheduleSourceModel').textContent =
                data.preview.model_config_name || '-';

            // Auto-generate schedule name suggestion
            const suggestedName = `${data.preview.model_config_name || 'Model'} - Retraining`;
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
        const recurringOptions = document.getElementById('scheduleOptionsRecurring');
        const dayOfWeekGroup = document.getElementById('scheduleDayOfWeekGroup');

        if (type === 'once') {
            onceOptions.style.display = 'block';
            recurringOptions.style.display = 'none';
        } else {
            onceOptions.style.display = 'none';
            recurringOptions.style.display = 'block';
            dayOfWeekGroup.style.display = type === 'weekly' ? 'block' : 'none';
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
        } else if (type === 'daily') {
            const time = state.scheduleConfig.scheduleTime || '09:00';
            previewText = `Daily at ${time} (${timezone})`;
        } else if (type === 'weekly') {
            const time = state.scheduleConfig.scheduleTime || '09:00';
            const day = DAY_NAMES[state.scheduleConfig.scheduleDayOfWeek];
            previewText = `Every ${day} at ${time} (${timezone})`;
        }

        previewEl.textContent = previewText;
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
        // Validate
        const name = document.getElementById('scheduleNameInput').value.trim();
        if (!name) {
            showToast('Please enter a schedule name', 'error');
            document.getElementById('scheduleNameInput').focus();
            return;
        }

        const type = state.scheduleConfig.scheduleType;
        const timezone = document.getElementById('scheduleTimezoneSelect').value;
        const description = document.getElementById('scheduleDescriptionInput').value.trim();

        // Validate type-specific fields
        if (type === 'once') {
            if (!state.scheduleConfig.scheduledDatetime) {
                showToast('Please select a date and time', 'error');
                return;
            }
        }

        // Build request data
        const requestData = {
            source_training_run_id: state.sourceId,
            name: name,
            description: description,
            schedule_type: type,
            schedule_timezone: timezone
        };

        if (type === 'once') {
            // Convert local datetime to ISO format
            const dt = new Date(state.scheduleConfig.scheduledDatetime);
            requestData.scheduled_datetime = dt.toISOString();
        } else {
            requestData.schedule_time = state.scheduleConfig.scheduleTime || '09:00';
            if (type === 'weekly') {
                requestData.schedule_day_of_week = state.scheduleConfig.scheduleDayOfWeek;
            }
        }

        // Show loading
        state.isLoading = true;
        document.getElementById('scheduleModalLoading').classList.remove('hidden');
        document.getElementById('scheduleCreateBtn').disabled = true;

        try {
            const response = await fetch(config.endpoints.createFromRun, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify(requestData)
            });

            const data = await response.json();

            if (data.success) {
                showToast(data.message || `Schedule "${name}" created successfully`, 'success');
                close();

                // Call success callback
                if (config.onSuccess) {
                    config.onSuccess(data.schedule);
                }
            } else {
                showToast(data.error || 'Failed to create schedule', 'error');
                if (config.onError) {
                    config.onError(data.error);
                }
            }
        } catch (error) {
            console.error('Error creating schedule:', error);
            showToast('Failed to create schedule', 'error');
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
        close: close,
        handleOverlayClick: handleOverlayClick,
        onScheduleTypeChange: onScheduleTypeChange,
        selectDay: selectDay,
        create: create,
        // Expose state for debugging
        getState: function() { return state; }
    };
})();
