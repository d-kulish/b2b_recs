/**
 * Integrate Modal Module
 *
 * Manages the endpoint integration testing modal.
 * Provides Quick Validation, Input Schema, and Code Examples.
 *
 * Usage:
 *     IntegrateModal.open(endpointId);
 *     IntegrateModal.close();
 */

const IntegrateModal = (function() {
    'use strict';

    // =============================================================================
    // CONFIGURATION & STATE
    // =============================================================================

    const config = {
        endpoints: {
            integration: '/api/deployed-endpoints/{id}/integration/',
            sample: '/api/deployed-endpoints/{id}/integration/sample/',
            test: '/api/deployed-endpoints/{id}/integration/test/'
        }
    };

    let state = {
        endpointId: null,
        endpoint: null,
        schema: null,
        sampleData: null,
        codeExamples: null,
        currentCodeTab: 'python',
        loading: false
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
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function formatJson(obj) {
        try {
            return JSON.stringify(obj, null, 2);
        } catch (e) {
            return String(obj);
        }
    }

    // =============================================================================
    // API CALLS
    // =============================================================================

    async function fetchIntegrationData(endpointId) {
        state.loading = true;
        try {
            const url = buildUrl(config.endpoints.integration, { id: endpointId });
            const response = await fetch(url);
            const data = await response.json();

            if (data.success) {
                return data.integration;
            } else {
                throw new Error(data.error || 'Failed to fetch integration data');
            }
        } finally {
            state.loading = false;
        }
    }

    async function fetchSampleData(endpointId) {
        const url = buildUrl(config.endpoints.sample, { id: endpointId });
        const response = await fetch(url);
        const data = await response.json();

        if (data.success) {
            return {
                sampleData: data.sample_data,
                codeExamples: data.code_examples
            };
        } else {
            throw new Error(data.error || 'Failed to fetch sample data');
        }
    }

    async function runTest(endpointId, testType, instance = null) {
        const url = buildUrl(config.endpoints.test, { id: endpointId });
        const body = { test_type: testType };
        if (instance) {
            body.instance = instance;
        }

        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify(body)
        });

        const data = await response.json();

        if (data.success) {
            return data.result;
        } else {
            throw new Error(data.error || 'Failed to run test');
        }
    }

    // =============================================================================
    // RENDERING
    // =============================================================================

    function renderHeader() {
        const title = document.getElementById('integrateModalTitle');
        const typeBadge = document.getElementById('integrateModalTypeBadge');

        if (state.endpoint) {
            // Title shows the service name
            title.textContent = state.endpoint.service_name;

            // Type badge with icon
            const modelType = state.endpoint.model_type || 'retrieval';
            const typeIcons = {
                'retrieval': 'fa-search',
                'ranking': 'fa-sort-amount-down',
                'multitask': 'fa-layer-group'
            };
            const icon = typeIcons[modelType] || 'fa-cube';
            typeBadge.className = `integrate-modal-type-badge ${modelType}`;
            typeBadge.innerHTML = `<i class="fas ${icon}"></i> ${modelType.toUpperCase()}`;
        }
    }

    function renderSchema() {
        const tbody = document.getElementById('integrateSchemaBody');
        if (!state.schema || !state.schema.fields || state.schema.fields.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="3" class="integrate-loading">No schema available</td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = state.schema.fields.map(field => `
            <tr>
                <td><span class="integrate-schema-field">${escapeHtml(field.name)}</span></td>
                <td><span class="integrate-schema-type">${escapeHtml(field.type)}</span></td>
                <td><span class="integrate-schema-notes">${escapeHtml(field.notes || '')}</span></td>
            </tr>
        `).join('');
    }

    function renderSampleData() {
        const sampleEl = document.getElementById('integrateSampleData');
        if (state.sampleData && state.sampleData.instance) {
            sampleEl.textContent = formatJson(state.sampleData.instance);
        } else if (state.sampleData && state.sampleData.error) {
            sampleEl.textContent = `Error: ${state.sampleData.error}`;
        } else {
            sampleEl.textContent = '{}';
        }
    }

    function renderCodeExamples() {
        const codeEl = document.getElementById('integrateCodeDisplay');
        if (state.codeExamples && state.codeExamples[state.currentCodeTab]) {
            codeEl.textContent = state.codeExamples[state.currentCodeTab];
        } else {
            codeEl.textContent = '// No code example available';
        }

        // Update active tab
        document.querySelectorAll('.integrate-code-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.lang === state.currentCodeTab);
        });
    }

    function renderPredictResult(result) {
        const resultRow = document.getElementById('integratePredictResultRow');
        const statusEl = document.getElementById('integratePredictStatus');
        const resultEl = document.getElementById('integratePredictResult');

        resultRow.style.display = '';

        if (result.success) {
            statusEl.innerHTML = `
                <span class="integrate-result-status success">
                    <i class="fas fa-check-circle"></i>
                    ${result.status_code} OK
                </span>
                <span class="integrate-result-latency">(${result.latency_ms}ms)</span>
            `;
        } else {
            const errorMsg = result.error || `Status ${result.status_code}`;
            statusEl.innerHTML = `
                <span class="integrate-result-status error">
                    <i class="fas fa-times-circle"></i>
                    ${escapeHtml(errorMsg)}
                </span>
                ${result.latency_ms > 0 ? `<span class="integrate-result-latency">(${result.latency_ms}ms)</span>` : ''}
            `;
        }

        resultEl.textContent = formatJson(result.response || result.error);
    }

    function renderLoading() {
        document.getElementById('integrateSchemaBody').innerHTML = `
            <tr>
                <td colspan="3" class="integrate-loading">
                    <i class="fas fa-spinner fa-spin"></i> Loading...
                </td>
            </tr>
        `;
        document.getElementById('integrateSampleData').textContent = '{"loading": "..."}';
        document.getElementById('integrateCodeDisplay').textContent = '// Loading...';
    }

    // =============================================================================
    // EVENT HANDLERS
    // =============================================================================

    function handleOverlayClick(event) {
        if (event.target.classList.contains('modal-overlay')) {
            close();
        }
    }

    function handleKeyDown(event) {
        if (event.key === 'Escape') {
            close();
        }
    }

    // =============================================================================
    // PUBLIC API
    // =============================================================================

    async function open(endpointId) {
        state.endpointId = endpointId;
        state.endpoint = null;
        state.schema = null;
        state.sampleData = null;
        state.codeExamples = null;
        state.currentCodeTab = 'python';

        // Show modal with loading state
        const modal = document.getElementById('integrateModal');
        modal.classList.remove('hidden');

        // Add keyboard listener
        document.addEventListener('keydown', handleKeyDown);

        // Render loading state
        renderLoading();

        try {
            // Fetch integration data
            const data = await fetchIntegrationData(endpointId);

            // Update state
            state.endpoint = data.endpoint;
            state.schema = data.schema;
            state.sampleData = data.sample_data;
            state.codeExamples = data.code_examples;

            // Render all sections
            renderHeader();
            renderSchema();
            renderSampleData();
            renderCodeExamples();

            // Hide prediction result row
            document.getElementById('integratePredictResultRow').style.display = 'none';

        } catch (error) {
            console.error('Error opening integrate modal:', error);
            // Show error in schema section
            document.getElementById('integrateSchemaBody').innerHTML = `
                <tr>
                    <td colspan="3" class="integrate-loading" style="color: #ef4444;">
                        <i class="fas fa-exclamation-triangle"></i> ${escapeHtml(error.message)}
                    </td>
                </tr>
            `;
        }
    }

    function close() {
        const modal = document.getElementById('integrateModal');
        modal.classList.add('hidden');

        // Remove keyboard listener
        document.removeEventListener('keydown', handleKeyDown);

        // Reset state
        state.endpointId = null;
        state.endpoint = null;
        state.schema = null;
        state.sampleData = null;
        state.codeExamples = null;
    }

    async function refreshSample() {
        if (!state.endpointId) return;

        // Show spinner
        const refreshIcon = document.getElementById('integrateSampleRefreshIcon');
        refreshIcon.classList.add('fa-spin');

        try {
            const data = await fetchSampleData(state.endpointId);

            // Update state
            state.sampleData = data.sampleData;
            state.codeExamples = data.codeExamples;

            // Re-render
            renderSampleData();
            renderCodeExamples();

            // Hide prediction result (sample changed)
            document.getElementById('integratePredictResultRow').style.display = 'none';

        } catch (error) {
            console.error('Error refreshing sample:', error);
            document.getElementById('integrateSampleData').textContent =
                `Error: ${error.message}`;
        } finally {
            refreshIcon.classList.remove('fa-spin');
        }
    }

    async function runPredictionTest() {
        if (!state.endpointId || !state.sampleData || !state.sampleData.instance) {
            return;
        }

        const btn = document.getElementById('integratePredictBtn');
        const originalHtml = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Running...';
        btn.disabled = true;

        try {
            const result = await runTest(
                state.endpointId,
                'predict',
                state.sampleData.instance
            );
            renderPredictResult(result);
        } catch (error) {
            console.error('Error running prediction test:', error);
            renderPredictResult({
                success: false,
                error: error.message,
                latency_ms: 0
            });
        } finally {
            btn.innerHTML = originalHtml;
            btn.disabled = false;
        }
    }

    function switchCodeTab(lang) {
        state.currentCodeTab = lang;
        renderCodeExamples();
    }

    async function copyCode() {
        const codeEl = document.getElementById('integrateCodeDisplay');
        const copyBtn = document.querySelector('.integrate-copy-btn');
        const copyIcon = document.getElementById('integrateCopyIcon');
        const copyText = document.getElementById('integrateCopyText');

        try {
            await navigator.clipboard.writeText(codeEl.textContent);

            // Show success state
            copyBtn.classList.add('copied');
            copyIcon.className = 'fas fa-check';
            copyText.textContent = 'Copied!';

            // Reset after 2 seconds
            setTimeout(() => {
                copyBtn.classList.remove('copied');
                copyIcon.className = 'fas fa-copy';
                copyText.textContent = 'Copy';
            }, 2000);

        } catch (error) {
            console.error('Failed to copy code:', error);
            copyText.textContent = 'Failed';
            setTimeout(() => {
                copyText.textContent = 'Copy';
            }, 2000);
        }
    }


    // =============================================================================
    // EXPOSE PUBLIC API
    // =============================================================================

    return {
        open,
        close,
        refreshSample,
        runPredictionTest,
        switchCodeTab,
        copyCode,
        handleOverlayClick
    };

})();
