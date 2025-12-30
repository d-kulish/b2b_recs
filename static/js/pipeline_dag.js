/**
 * Pipeline DAG Visualization
 * Reusable component for TFX pipeline visualization (Vertex AI style)
 *
 * Usage:
 *   1. Include CSS: {% static 'css/pipeline_dag.css' %}
 *   2. Include HTML: {% include 'includes/_pipeline_dag.html' %}
 *   3. Include this JS: {% static 'js/pipeline_dag.js' %}
 *   4. Call: renderPipelineStages(stages)
 *
 * Functions available:
 *   - renderPipelineStages(stages) - Render the pipeline with stage status
 *   - selectDagComponent(componentId) - Select a component node
 *   - loadComponentLogs(componentId, experimentId) - Load logs for a component
 *   - refreshComponentLogs(experimentId) - Refresh logs for selected component
 *   - resetDagState() - Reset DAG state when modal closes
 *   - formatDuration(seconds) - Format seconds as MM:SS
 */

// =============================================================================
// CONSTANTS
// =============================================================================

// Layout constants for 2D DAG positioning
// nodeHeight = icon(36px) + padding(24px) + border(2px) = 62px
const DAG_LAYOUT = {
    nodeWidth: 264,
    nodeHeight: 62,
    artifactSize: 40
};

// TFX Pipeline Structure with 2D Positions
const TFX_PIPELINE = {
    // Components with absolute positions (x is left edge of node)
    components: [
        { id: 'Compile', name: 'Pipeline Compile', icon: 'fa-cogs', x: 150, y: 15 },
        { id: 'Examples', name: 'Examples Gen', icon: 'fa-database', x: 150, y: 189 },
        { id: 'Stats', name: 'Stats Gen', icon: 'fa-chart-bar', x: 20, y: 363 },
        { id: 'Schema', name: 'Schema Gen', icon: 'fa-sitemap', x: 20, y: 537 },
        { id: 'Transform', name: 'Transform', icon: 'fa-exchange-alt', x: 335, y: 711 },
        { id: 'Train', name: 'Trainer', icon: 'fa-microchip', x: 20, y: 885 },
        { id: 'Evaluator', name: 'Evaluator', icon: 'fa-check-double', x: 290, y: 1059 },
        { id: 'Pusher', name: 'Pusher', icon: 'fa-cloud-upload-alt', x: 150, y: 1233 }
    ],

    // Artifacts with absolute positions (centered between source component and next component)
    // Calculated as: x = component.x + (nodeWidth - artifactSize) / 2 = component.x + 112
    //                y = component_bottom + (gap - artifactSize) / 2 = component_bottom + 36
    // Types: examples (purple grid), statistics (teal bars), schema (amber shapes), document (purple doc)
    artifacts: [
        { id: 'config', name: 'Config', icon: 'fa-file-alt', type: 'document', componentId: 'Compile', x: 262, y: 113 },
        { id: 'examples', name: 'Examples', icon: 'fa-th', type: 'examples', componentId: 'Examples', x: 262, y: 287 },
        { id: 'statistics', name: 'Statistics', icon: 'fa-chart-bar', type: 'statistics', componentId: 'Stats', x: 132, y: 461 },
        { id: 'schema', name: 'Schema', icon: 'fa-shapes', type: 'schema', componentId: 'Schema', x: 132, y: 635 },
        { id: 'transform_graph', name: 'Transform Graph', icon: 'fa-file-alt', type: 'document', componentId: 'Transform', x: 290, y: 809 },
        { id: 'transformed_examples', name: 'Transformed Examples', icon: 'fa-th', type: 'examples', componentId: 'Transform', x: 335, y: 809 },
        { id: 'pre_transform_schema', name: 'Pre-Transform Schema', icon: 'fa-shapes', type: 'schema', componentId: 'Transform', x: 380, y: 809 },
        { id: 'pre_transform_stats', name: 'Pre-Transform Stats', icon: 'fa-chart-bar', type: 'statistics', componentId: 'Transform', x: 425, y: 809 },
        { id: 'post_transform_schema', name: 'Post-Transform Schema', icon: 'fa-shapes', type: 'schema', componentId: 'Transform', x: 470, y: 809 },
        { id: 'post_transform_stats', name: 'Post-Transform Stats', icon: 'fa-chart-bar', type: 'statistics', componentId: 'Transform', x: 515, y: 809 },
        { id: 'post_transform_anomalies', name: 'Anomalies', icon: 'fa-file-alt', type: 'document', componentId: 'Transform', x: 560, y: 809 },
        { id: 'updated_analyzer_cache', name: 'Analyzer Cache', icon: 'fa-database', type: 'statistics', componentId: 'Transform', x: 605, y: 809 },
        { id: 'model', name: 'Model', icon: 'fa-lightbulb', type: 'model', componentId: 'Train', x: 110, y: 983 },
        { id: 'model_run', name: 'Model Run', icon: 'fa-file-alt', type: 'document', componentId: 'Train', x: 155, y: 983 },
        { id: 'model_blessing', name: 'Model Blessing', icon: 'fa-certificate', type: 'blessing', componentId: 'Evaluator', x: 380, y: 1157 },
        { id: 'evaluation', name: 'Evaluation', icon: 'fa-chart-bar', type: 'statistics', componentId: 'Evaluator', x: 425, y: 1157 },
        { id: 'pushed_model', name: 'Model Endpoint', icon: 'fa-cloud', type: 'model', componentId: 'Pusher', x: 262, y: 1331 }
    ],

    // Edges: connections between nodes (components and artifacts)
    edges: [
        { from: 'Compile', to: 'config', fromType: 'component', toType: 'artifact' },
        { from: 'config', to: 'Examples', fromType: 'artifact', toType: 'component' },
        { from: 'Examples', to: 'examples', fromType: 'component', toType: 'artifact' },
        { from: 'examples', to: 'Stats', fromType: 'artifact', toType: 'component', curve: 'left' },
        { from: 'examples', to: 'Transform', fromType: 'artifact', toType: 'component', curve: 'down-right' },
        { from: 'Stats', to: 'statistics', fromType: 'component', toType: 'artifact' },
        { from: 'statistics', to: 'Schema', fromType: 'component', toType: 'component' },
        { from: 'Schema', to: 'schema', fromType: 'component', toType: 'artifact' },
        { from: 'schema', to: 'Transform', fromType: 'artifact', toType: 'component', curve: 'right' },
        { from: 'schema', to: 'Train', fromType: 'artifact', toType: 'component', curve: 'down-right' },
        { from: 'Transform', to: 'transform_graph', fromType: 'component', toType: 'artifact' },
        { from: 'Transform', to: 'transformed_examples', fromType: 'component', toType: 'artifact' },
        { from: 'Transform', to: 'pre_transform_schema', fromType: 'component', toType: 'artifact' },
        { from: 'Transform', to: 'pre_transform_stats', fromType: 'component', toType: 'artifact' },
        { from: 'Transform', to: 'post_transform_schema', fromType: 'component', toType: 'artifact' },
        { from: 'Transform', to: 'post_transform_stats', fromType: 'component', toType: 'artifact' },
        { from: 'Transform', to: 'post_transform_anomalies', fromType: 'component', toType: 'artifact' },
        { from: 'Transform', to: 'updated_analyzer_cache', fromType: 'component', toType: 'artifact' },
        { from: 'transformed_examples', to: 'Train', fromType: 'artifact', toType: 'component', curve: 'down-left' },
        { from: 'transform_graph', to: 'Train', fromType: 'artifact', toType: 'component', curve: 'down-left' },
        { from: 'Train', to: 'model', fromType: 'component', toType: 'artifact' },
        { from: 'Train', to: 'model_run', fromType: 'component', toType: 'artifact' },
        { from: 'model', to: 'Evaluator', fromType: 'artifact', toType: 'component', curve: 'right' },
        { from: 'model', to: 'Pusher', fromType: 'artifact', toType: 'component', curve: 'down-right' },
        { from: 'Evaluator', to: 'model_blessing', fromType: 'component', toType: 'artifact' },
        { from: 'Evaluator', to: 'evaluation', fromType: 'component', toType: 'artifact' },
        { from: 'model_blessing', to: 'Pusher', fromType: 'artifact', toType: 'component', curve: 'down-left' },
        { from: 'Pusher', to: 'pushed_model', fromType: 'component', toType: 'artifact' }
    ]
};

// Status badge icons mapping
const STATUS_BADGE_ICONS = {
    'completed': 'fa-check',
    'running': 'fa-sync fa-spin',
    'failed': 'fa-exclamation',
    'pending': 'fa-minus',
    'skipped': 'fa-ban'
};

// =============================================================================
// STATE
// =============================================================================

let selectedComponentId = null;
let currentStageDetails = [];
let stageMap = {};

// =============================================================================
// UTILITIES
// =============================================================================

/**
 * Format seconds as MM:SS
 * @param {number} seconds - Duration in seconds
 * @returns {string} Formatted duration string
 */
function formatDuration(seconds) {
    if (!seconds && seconds !== 0) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Escape HTML to prevent XSS
 * @param {string} text - Text to escape
 * @returns {string} Escaped text
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// =============================================================================
// CORE FUNCTIONS
// =============================================================================

/**
 * Get node position and dimensions for connection drawing
 * @param {string} nodeId - Component or artifact ID
 * @returns {Object|null} Node info with x, y, width, height, type
 */
function getNodeInfo(nodeId) {
    const component = TFX_PIPELINE.components.find(c => c.id === nodeId);
    if (component) {
        return {
            x: component.x,
            y: component.y,
            width: DAG_LAYOUT.nodeWidth,
            height: DAG_LAYOUT.nodeHeight,
            type: 'component'
        };
    }
    const artifact = TFX_PIPELINE.artifacts.find(a => a.id === nodeId);
    if (artifact) {
        return {
            x: artifact.x,
            y: artifact.y,
            width: DAG_LAYOUT.artifactSize,
            height: DAG_LAYOUT.artifactSize,
            type: 'artifact'
        };
    }
    return null;
}

/**
 * Get the status for a connection based on source node
 * @param {string} fromId - Source node ID
 * @param {string} fromType - Source node type ('component' or 'artifact')
 * @returns {string} Status ('completed', 'failed', or 'pending')
 */
function getEdgeStatus(fromId, fromType) {
    if (fromType === 'component') {
        const stage = stageMap[fromId];
        if (stage) {
            if (stage.status === 'completed') return 'completed';
            if (stage.status === 'failed') return 'failed';
        }
    } else {
        const artifact = TFX_PIPELINE.artifacts.find(a => a.id === fromId);
        if (artifact) {
            const stage = stageMap[artifact.componentId];
            if (stage) {
                if (stage.status === 'completed') return 'completed';
                if (stage.status === 'failed') return 'failed';
            }
        }
    }
    return 'pending';
}

/**
 * Draw bezier curve between two nodes
 */
function drawBezierConnection(svg, fromNode, toNode, curveType, status) {
    const fromCenterX = fromNode.x + fromNode.width / 2;
    const fromBottomY = fromNode.y + fromNode.height;
    const toCenterX = toNode.x + toNode.width / 2;
    const toTopY = toNode.y;

    let path;
    const dx = toCenterX - fromCenterX;
    const dy = toTopY - fromBottomY;

    if (curveType === 'left') {
        const ctrl1X = fromCenterX;
        const ctrl1Y = fromBottomY + dy * 0.5;
        const ctrl2X = toCenterX;
        const ctrl2Y = toTopY - dy * 0.3;
        path = `M ${fromCenterX} ${fromBottomY} C ${ctrl1X} ${ctrl1Y}, ${ctrl2X} ${ctrl2Y}, ${toCenterX} ${toTopY}`;
    } else if (curveType === 'right') {
        const ctrl1X = fromCenterX;
        const ctrl1Y = fromBottomY + dy * 0.5;
        const ctrl2X = toCenterX;
        const ctrl2Y = toTopY - dy * 0.3;
        path = `M ${fromCenterX} ${fromBottomY} C ${ctrl1X} ${ctrl1Y}, ${ctrl2X} ${ctrl2Y}, ${toCenterX} ${toTopY}`;
    } else if (curveType === 'down-right') {
        const midY = fromBottomY + dy * 0.6;
        const ctrl1X = fromCenterX;
        const ctrl1Y = midY;
        const ctrl2X = toCenterX;
        const ctrl2Y = midY;
        path = `M ${fromCenterX} ${fromBottomY} C ${ctrl1X} ${ctrl1Y}, ${ctrl2X} ${ctrl2Y}, ${toCenterX} ${toTopY}`;
    } else if (curveType === 'down-left') {
        const midY = fromBottomY + dy * 0.6;
        const ctrl1X = fromCenterX;
        const ctrl1Y = midY;
        const ctrl2X = toCenterX;
        const ctrl2Y = midY;
        path = `M ${fromCenterX} ${fromBottomY} C ${ctrl1X} ${ctrl1Y}, ${ctrl2X} ${ctrl2Y}, ${toCenterX} ${toTopY}`;
    } else {
        if (Math.abs(dx) < 50) {
            path = `M ${fromCenterX} ${fromBottomY} L ${toCenterX} ${toTopY}`;
        } else {
            const ctrl1X = fromCenterX;
            const ctrl1Y = fromBottomY + dy * 0.4;
            const ctrl2X = toCenterX;
            const ctrl2Y = toTopY - dy * 0.4;
            path = `M ${fromCenterX} ${fromBottomY} C ${ctrl1X} ${ctrl1Y}, ${ctrl2X} ${ctrl2Y}, ${toCenterX} ${toTopY}`;
        }
    }

    const pathEl = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    pathEl.setAttribute('d', path);
    pathEl.setAttribute('class', status);
    svg.appendChild(pathEl);
}

/**
 * Debug: Draw a small circle at a position
 */
function drawDebugMarker(svg, x, y, color = 'red') {
    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('cx', x);
    circle.setAttribute('cy', y);
    circle.setAttribute('r', 4);
    circle.setAttribute('fill', color);
    circle.setAttribute('stroke', 'white');
    circle.setAttribute('stroke-width', 1);
    svg.appendChild(circle);
}

/**
 * Draw all SVG connections
 */
function drawDagConnections() {
    const svg = document.getElementById('expViewDagSvg');
    if (!svg) return;

    svg.innerHTML = '';

    // Debug mode: set to true to enable port markers
    const DEBUG_PORTS = false;

    if (DEBUG_PORTS) {
        TFX_PIPELINE.components.forEach(comp => {
            const node = getNodeInfo(comp.id);
            const topPortX = node.x + node.width / 2;
            const topPortY = node.y;
            const bottomPortX = node.x + node.width / 2;
            const bottomPortY = node.y + node.height;

            drawDebugMarker(svg, topPortX, topPortY, 'lime');
            drawDebugMarker(svg, bottomPortX, bottomPortY, 'red');
        });

        TFX_PIPELINE.artifacts.forEach(art => {
            const node = getNodeInfo(art.id);
            const topPortX = node.x + node.width / 2;
            const topPortY = node.y;
            const bottomPortX = node.x + node.width / 2;
            const bottomPortY = node.y + node.height;

            drawDebugMarker(svg, topPortX, topPortY, 'cyan');
            drawDebugMarker(svg, bottomPortX, bottomPortY, 'orange');
        });
    }

    TFX_PIPELINE.edges.forEach(edge => {
        const fromNode = getNodeInfo(edge.from);
        const toNode = getNodeInfo(edge.to);

        if (fromNode && toNode) {
            const status = getEdgeStatus(edge.from, edge.fromType);
            drawBezierConnection(svg, fromNode, toNode, edge.curve, status);
        }
    });
}

// =============================================================================
// RENDERING
// =============================================================================

/**
 * Render pipeline stages in the DAG visualization
 * @param {Array} stages - Array of stage objects with name, status, duration_seconds
 */
function renderPipelineStages(stages) {
    currentStageDetails = stages;

    stageMap = {};
    stages.forEach(s => { stageMap[s.name] = s; });

    const container = document.getElementById('expViewDagNodes');
    if (!container) return;

    let html = '';

    // Render all components
    TFX_PIPELINE.components.forEach((component, index) => {
        const stage = stageMap[component.id] || { status: 'pending', duration_seconds: null };
        let statusClass = stage.status || 'pending';

        // If a previous component failed, mark subsequent as skipped
        if (statusClass === 'pending') {
            const prevFailed = TFX_PIPELINE.components.slice(0, index).some(c => {
                const s = stageMap[c.id];
                return s && s.status === 'failed';
            });
            if (prevFailed) statusClass = 'skipped';
        }

        const statusBadgeIcon = STATUS_BADGE_ICONS[statusClass] || 'fa-minus';
        const duration = stage.duration_seconds ? formatDuration(stage.duration_seconds) : '';
        const selected = selectedComponentId === component.id ? 'selected' : '';

        html += `
            <div class="exp-view-dag-node ${statusClass} ${selected}"
                 style="left: ${component.x}px; top: ${component.y}px;"
                 data-component="${component.id}"
                 onclick="selectDagComponent('${component.id}')">
                <span class="exp-view-dag-node-port top"></span>
                <div class="exp-view-dag-node-icon">
                    <i class="fas ${component.icon}"></i>
                </div>
                <div class="exp-view-dag-node-info">
                    <div class="exp-view-dag-node-name">${component.name}</div>
                    ${duration ? `<div class="exp-view-dag-node-time">${duration}</div>` : ''}
                </div>
                <div class="exp-view-dag-node-status-badge">
                    <i class="fas ${statusBadgeIcon}"></i>
                </div>
                <span class="exp-view-dag-node-port bottom"></span>
            </div>
        `;
    });

    // Render all artifacts
    TFX_PIPELINE.artifacts.forEach(artifact => {
        const stage = stageMap[artifact.componentId] || { status: 'pending' };
        const artifactStatus = stage.status === 'completed' ? 'completed' : 'pending';

        html += `
            <div class="exp-view-dag-artifact ${artifactStatus} artifact-${artifact.type}"
                 style="left: ${artifact.x}px; top: ${artifact.y}px;"
                 data-artifact="${artifact.id}">
                <i class="fas ${artifact.icon}"></i>
                <span class="exp-view-dag-artifact-tooltip">${artifact.name}</span>
            </div>
        `;
    });

    container.innerHTML = html;

    // Draw SVG connections after DOM update
    requestAnimationFrame(() => {
        drawDagConnections();
    });
}

// =============================================================================
// INTERACTION
// =============================================================================

/**
 * Select a DAG component and show its details
 * @param {string} componentId - Component ID to select
 */
function selectDagComponent(componentId) {
    // Don't show logs panel for Compile stage (it's Cloud Build, not Vertex AI)
    if (componentId === 'Compile') {
        const nodes = document.querySelectorAll('.exp-view-dag-node');
        nodes.forEach(node => {
            node.classList.remove('selected');
            if (node.dataset.component === componentId) {
                node.classList.add('selected');
            }
        });
        selectedComponentId = componentId;
        document.getElementById('expViewComponentDetail')?.classList.add('hidden');
        return;
    }

    // Update selection visually
    const nodes = document.querySelectorAll('.exp-view-dag-node');
    nodes.forEach(node => {
        node.classList.remove('selected');
        if (node.dataset.component === componentId) {
            node.classList.add('selected');
        }
    });

    selectedComponentId = componentId;

    // Show detail panel
    const detailPanel = document.getElementById('expViewComponentDetail');
    if (detailPanel) {
        detailPanel.classList.remove('hidden');
    }

    // Get stage info
    const stage = currentStageDetails.find(s => s.name === componentId) || { status: 'pending' };

    // Update header
    const component = TFX_PIPELINE.components.find(c => c.id === componentId);
    const nameEl = document.getElementById('expViewComponentName');
    if (nameEl) {
        nameEl.textContent = component ? component.name : componentId;
    }

    const statusEl = document.getElementById('expViewComponentStatus');
    if (statusEl) {
        statusEl.textContent = stage.status || 'pending';
        statusEl.className = 'exp-view-component-status ' + (stage.status || 'pending');
    }

    const durationEl = document.getElementById('expViewComponentDurationText');
    if (durationEl) {
        durationEl.textContent = stage.duration_seconds ? formatDuration(stage.duration_seconds) : '-';
    }

    // Load logs - requires experimentId from the page context
    if (typeof viewModalExpId !== 'undefined' && viewModalExpId) {
        loadComponentLogs(componentId, viewModalExpId);
    }
}

/**
 * Load component logs from API
 * @param {string} componentId - Component ID
 * @param {number} experimentId - Experiment/Quick Test ID
 */
async function loadComponentLogs(componentId, experimentId) {
    if (!experimentId || !componentId) return;

    const logsContainer = document.getElementById('expViewLogsContainer');
    if (!logsContainer) return;

    logsContainer.innerHTML = '<div class="exp-view-logs-empty"><i class="fas fa-spinner fa-spin"></i> Loading logs...</div>';

    try {
        const response = await fetch(`/api/quick-tests/${experimentId}/logs/${componentId}/`);
        const data = await response.json();

        if (data.success && data.logs?.available) {
            if (data.logs.logs && data.logs.logs.length > 0) {
                logsContainer.innerHTML = data.logs.logs.map(log => `
                    <div class="exp-view-log-entry">
                        <span class="exp-view-log-time">${log.timestamp}</span>
                        <span class="exp-view-log-severity ${log.severity}">${log.severity}</span>
                        <span class="exp-view-log-message">${escapeHtml(log.message)}</span>
                    </div>
                `).join('');
            } else {
                logsContainer.innerHTML = '<div class="exp-view-logs-empty">No logs available yet</div>';
            }
        } else {
            const msg = data.logs?.message || 'Logs not available';
            logsContainer.innerHTML = `<div class="exp-view-logs-empty">${escapeHtml(msg)}</div>`;
        }
    } catch (error) {
        console.error('Error loading logs:', error);
        logsContainer.innerHTML = '<div class="exp-view-logs-error">Failed to load logs</div>';
    }
}

/**
 * Refresh logs for the currently selected component
 * @param {number} experimentId - Experiment/Quick Test ID (optional, uses viewModalExpId if available)
 */
function refreshComponentLogs(experimentId) {
    if (!selectedComponentId) return;

    const expId = experimentId || (typeof viewModalExpId !== 'undefined' ? viewModalExpId : null);
    if (!expId) return;

    const btn = document.getElementById('expViewRefreshLogsBtn');
    if (btn) {
        btn.classList.add('loading');
    }

    loadComponentLogs(selectedComponentId, expId).finally(() => {
        if (btn) {
            btn.classList.remove('loading');
        }
    });
}

/**
 * Reset DAG state when modal closes
 */
function resetDagState() {
    selectedComponentId = null;
    currentStageDetails = [];
    stageMap = {};
    const detailPanel = document.getElementById('expViewComponentDetail');
    if (detailPanel) {
        detailPanel.classList.add('hidden');
    }
}
