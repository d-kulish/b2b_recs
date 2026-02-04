/**
 * Model Dashboard - ETL Chapter
 *
 * Displays ETL Dashboard data: KPIs, Scheduled Jobs table, and Bubble Chart.
 * Uses the same data source as the ETL page for automatic synchronization.
 *
 * @module ModelDashboardEtl
 */
const ModelDashboardEtl = (function() {
    'use strict';

    // =========================================================================
    // CONFIGURATION
    // =========================================================================
    const config = {
        containerId: '#etlChapter',
        loadingId: '#etlChapterLoading',
        emptyId: '#etlChapterEmpty',
        contentId: '#etlChapterContent',
        kpiRowId: '#etlChapterKpiRow',
        row2Id: '#etlChapterRow2',
        scheduledSectionId: '#etlScheduledSection',
        chartSectionId: '#etlChartSection',
        bubbleChartId: '#etlBubbleChart',
        tooltipId: '#etlBubbleTooltip'
    };

    // =========================================================================
    // STATE
    // =========================================================================
    let state = {
        initialized: false,
        loading: false,
        data: null,
        modelId: null,
        scheduledJobsPage: 1,
        scheduledJobsPerPage: 5
    };

    // Bubble chart color palette (from model_etl.html)
    const statusColors = {
        completed: { light: '#86EFAC', dark: '#166534' },  // green-300 -> green-800
        partial:   { light: '#FED7AA', dark: '#9A3412' },  // orange-200 -> orange-800
        failed:    { light: '#FCA5A5', dark: '#991B1B' },  // red-300 -> red-800
    };

    // =========================================================================
    // PRIVATE METHODS
    // =========================================================================

    /**
     * Extract model ID from the current page URL.
     * Expects URL pattern: /models/{id}/dashboard/
     */
    function getModelIdFromUrl() {
        const match = window.location.pathname.match(/\/models\/(\d+)\//);
        return match ? match[1] : null;
    }

    /**
     * Show loading state.
     */
    function showLoading() {
        document.querySelector(config.loadingId).classList.remove('hidden');
        document.querySelector(config.emptyId).classList.add('hidden');
        document.querySelector(config.contentId).classList.add('hidden');
    }

    /**
     * Show empty state.
     */
    function showEmpty() {
        document.querySelector(config.loadingId).classList.add('hidden');
        document.querySelector(config.emptyId).classList.remove('hidden');
        document.querySelector(config.contentId).classList.add('hidden');
    }

    /**
     * Show content.
     */
    function showContent() {
        document.querySelector(config.loadingId).classList.add('hidden');
        document.querySelector(config.emptyId).classList.add('hidden');
        document.querySelector(config.contentId).classList.remove('hidden');
    }

    /**
     * Fetch dashboard stats from API.
     */
    function fetchData() {
        if (!state.modelId) {
            console.error('ModelDashboardEtl: No model ID found');
            showEmpty();
            return;
        }

        state.loading = true;
        showLoading();

        fetch(`/api/models/${state.modelId}/etl/dashboard-stats/`)
            .then(response => response.json())
            .then(data => {
                state.loading = false;

                if (data.success) {
                    state.data = data.data;

                    // Check if there's any data (runs or scheduled jobs)
                    const hasData = data.data.kpi.total_runs > 0 ||
                                   data.data.scheduled_jobs_total > 0;

                    if (!hasData) {
                        showEmpty();
                    } else {
                        renderKpiRow(data.data.kpi);
                        renderScheduledJobs(data.data.scheduled_jobs, 1);
                        renderBubbleChart(data.data.bubble_chart);
                        showContent();
                    }
                } else {
                    console.error('ModelDashboardEtl: API error:', data.error);
                    showEmpty();
                }
            })
            .catch(error => {
                state.loading = false;
                console.error('ModelDashboardEtl: Fetch error:', error);
                showEmpty();
            });
    }

    /**
     * Render KPI row with 6 cards.
     *
     * @param {Object} kpi - KPI data from API
     */
    function renderKpiRow(kpi) {
        const container = document.querySelector(config.kpiRowId);

        // Determine success rate color
        let successRateColorClass = 'green';
        if (kpi.success_rate < 70) {
            successRateColorClass = 'red';
        } else if (kpi.success_rate < 90) {
            successRateColorClass = 'yellow';
        }

        // Determine failed runs color
        const failedColorClass = kpi.failed_runs > 0 ? 'red' : 'green';

        container.innerHTML = `
            <div class="model-dashboard-etl-kpi-card">
                <div class="model-dashboard-etl-kpi-icon blue">
                    <i class="fas fa-play-circle"></i>
                </div>
                <div class="model-dashboard-etl-kpi-info">
                    <div class="model-dashboard-etl-kpi-value">${kpi.total_runs}</div>
                    <div class="model-dashboard-etl-kpi-label">Total Runs</div>
                </div>
            </div>

            <div class="model-dashboard-etl-kpi-card">
                <div class="model-dashboard-etl-kpi-icon ${successRateColorClass}">
                    <i class="fas fa-check-circle"></i>
                </div>
                <div class="model-dashboard-etl-kpi-info">
                    <div class="model-dashboard-etl-kpi-value">${kpi.success_rate}%</div>
                    <div class="model-dashboard-etl-kpi-label">Success Rate</div>
                </div>
            </div>

            <div class="model-dashboard-etl-kpi-card">
                <div class="model-dashboard-etl-kpi-icon green">
                    <i class="fas fa-check-double"></i>
                </div>
                <div class="model-dashboard-etl-kpi-info">
                    <div class="model-dashboard-etl-kpi-value">${kpi.successful_runs}</div>
                    <div class="model-dashboard-etl-kpi-label">Successful Runs</div>
                </div>
            </div>

            <div class="model-dashboard-etl-kpi-card">
                <div class="model-dashboard-etl-kpi-icon ${failedColorClass}">
                    <i class="fas fa-times-circle"></i>
                </div>
                <div class="model-dashboard-etl-kpi-info">
                    <div class="model-dashboard-etl-kpi-value">${kpi.failed_runs}</div>
                    <div class="model-dashboard-etl-kpi-label">Failed Runs</div>
                </div>
            </div>

            <div class="model-dashboard-etl-kpi-card">
                <div class="model-dashboard-etl-kpi-icon purple">
                    <i class="fas fa-database"></i>
                </div>
                <div class="model-dashboard-etl-kpi-info">
                    <div class="model-dashboard-etl-kpi-value">${formatNumber(kpi.total_rows_extracted)}</div>
                    <div class="model-dashboard-etl-kpi-label">Rows Migrated</div>
                </div>
            </div>

            <div class="model-dashboard-etl-kpi-card">
                <div class="model-dashboard-etl-kpi-icon blue">
                    <i class="fas fa-clock"></i>
                </div>
                <div class="model-dashboard-etl-kpi-info">
                    <div class="model-dashboard-etl-kpi-value">${formatDuration(kpi.avg_duration_seconds)}</div>
                    <div class="model-dashboard-etl-kpi-label">Avg Duration</div>
                </div>
            </div>
        `;
    }

    /**
     * Render scheduled jobs table with client-side pagination.
     *
     * @param {Array} jobs - Scheduled jobs array
     * @param {number} page - Current page number (1-based)
     */
    function renderScheduledJobs(jobs, page) {
        const container = document.querySelector(config.scheduledSectionId);
        state.scheduledJobsPage = page;

        if (!jobs || jobs.length === 0) {
            container.innerHTML = `
                <h3 class="model-dashboard-etl-scheduled-title">
                    <i class="fas fa-calendar-alt"></i>
                    Scheduled Jobs
                </h3>
                <div class="model-dashboard-etl-scheduled-empty">
                    <i class="fas fa-calendar-times"></i>
                    <p>No scheduled jobs</p>
                    <p class="text-xs mt-1">Create ETL jobs with schedules to see them here</p>
                </div>
            `;
            return;
        }

        // Calculate pagination
        const totalJobs = jobs.length;
        const totalPages = Math.ceil(totalJobs / state.scheduledJobsPerPage);
        const startIndex = (page - 1) * state.scheduledJobsPerPage;
        const endIndex = Math.min(startIndex + state.scheduledJobsPerPage, totalJobs);
        const pageJobs = jobs.slice(startIndex, endIndex);

        // Build table rows
        const rowsHtml = pageJobs.map(job => {
            const nextRunDisplay = job.is_paused
                ? '<span class="text-gray-400">\u2014</span>'
                : (job.next_run_time ? formatNextRun(job.next_run_time) : '<span class="text-gray-400">\u2014</span>');

            const stateBadge = job.is_paused
                ? '<span class="model-dashboard-etl-badge-paused"><i class="fas fa-pause"></i> Paused</span>'
                : '<span class="model-dashboard-etl-badge-enabled"><i class="fas fa-check"></i> Enabled</span>';

            return `
                <tr>
                    <td class="job-name" title="${job.name}">${truncate(job.name, 18)}</td>
                    <td class="job-schedule">${job.schedule_display}</td>
                    <td class="job-next-run">${nextRunDisplay}</td>
                    <td>${stateBadge}</td>
                </tr>
            `;
        }).join('');

        // Build pagination if needed
        let paginationHtml = '';
        if (totalPages > 1) {
            const prevDisabled = page === 1 ? 'disabled' : '';
            const nextDisabled = page === totalPages ? 'disabled' : '';

            paginationHtml = `
                <div class="model-dashboard-etl-pagination">
                    <span class="page-info">${startIndex + 1}-${endIndex} of ${totalJobs}</span>
                    <div class="page-controls">
                        <button class="page-btn ${prevDisabled}" onclick="ModelDashboardEtl.goToScheduledJobsPage(${page - 1})" ${prevDisabled ? 'disabled' : ''}>Previous</button>
                        <button class="page-btn ${nextDisabled}" onclick="ModelDashboardEtl.goToScheduledJobsPage(${page + 1})" ${nextDisabled ? 'disabled' : ''}>Next</button>
                    </div>
                </div>
            `;
        }

        container.innerHTML = `
            <h3 class="model-dashboard-etl-scheduled-title">
                <i class="fas fa-calendar-alt"></i>
                Scheduled Jobs
            </h3>
            <div class="model-dashboard-etl-scheduled-table-wrapper">
                <table class="model-dashboard-etl-scheduled-table">
                    <thead>
                        <tr>
                            <th>Job Name</th>
                            <th>Schedule</th>
                            <th>Next Run</th>
                            <th>State</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rowsHtml}
                    </tbody>
                </table>
            </div>
            ${paginationHtml}
        `;
    }

    /**
     * Render bubble chart using D3.js.
     *
     * @param {Object} chartData - Bubble chart data from API
     */
    function renderBubbleChart(chartData) {
        const container = document.querySelector(config.chartSectionId);
        const svgElement = d3.select(config.bubbleChartId);

        // Clear previous content
        svgElement.selectAll('*').remove();

        const chartContainer = document.querySelector('#etlBubbleChartContainer');
        if (!chartContainer) return;

        const containerWidth = chartContainer.clientWidth;

        // Chart dimensions
        const margin = { top: 15, right: 30, bottom: 40, left: 130 };
        const width = containerWidth - margin.left - margin.right;
        const height = 260;

        // Bubble size constraints
        const minRadius = 3;
        const maxRadius = 16;

        const jobNames = chartData.job_names;
        const runs = chartData.runs;
        const durationStats = chartData.duration_stats;

        // Check if we have data
        if (jobNames.length === 0 || runs.length === 0) {
            // Show empty state
            container.innerHTML = `
                <div class="model-dashboard-etl-chart-header">
                    <span class="model-dashboard-etl-chart-title">ETL Job Runs (Last 5 Days)</span>
                    <div class="model-dashboard-etl-chart-legend">
                        <span><span class="legend-dot completed"></span> Completed</span>
                        <span><span class="legend-dot partial"></span> Partial</span>
                        <span><span class="legend-dot failed"></span> Failed</span>
                    </div>
                </div>
                <div id="etlBubbleChartContainer" class="relative">
                    <div class="model-dashboard-etl-chart-empty">
                        <i class="fas fa-chart-scatter"></i>
                        <p>No job runs in last 5 days</p>
                    </div>
                    <div id="etlBubbleTooltip" class="model-dashboard-etl-tooltip hidden"></div>
                </div>
            `;
            return;
        }

        // Re-render header with chart
        container.innerHTML = `
            <div class="model-dashboard-etl-chart-header">
                <span class="model-dashboard-etl-chart-title">ETL Job Runs (Last 5 Days)</span>
                <div class="model-dashboard-etl-chart-legend">
                    <span><span class="legend-dot completed"></span> Completed</span>
                    <span><span class="legend-dot partial"></span> Partial</span>
                    <span><span class="legend-dot failed"></span> Failed</span>
                </div>
            </div>
            <div id="etlBubbleChartContainer" class="relative">
                <svg id="etlBubbleChart" class="w-full"></svg>
                <div id="etlBubbleTooltip" class="model-dashboard-etl-tooltip hidden"></div>
            </div>
        `;

        // Re-select SVG after re-render
        const svg = d3.select('#etlBubbleChart');
        const chartContainerNew = document.querySelector('#etlBubbleChartContainer');
        const newContainerWidth = chartContainerNew.clientWidth;
        const newWidth = newContainerWidth - margin.left - margin.right;

        svg
            .attr('width', newContainerWidth)
            .attr('height', height + margin.top + margin.bottom);

        const g = svg.append('g')
            .attr('transform', `translate(${margin.left},${margin.top})`);

        // Add clip path
        const clipId = 'etl-bubble-chart-clip';
        svg.append('defs')
            .append('clipPath')
            .attr('id', clipId)
            .append('rect')
            .attr('x', 0)
            .attr('y', -maxRadius)
            .attr('width', newWidth)
            .attr('height', height + maxRadius * 2);

        // Parse date range
        const startDate = new Date(chartData.date_range.start);
        const endDate = new Date(chartData.date_range.end);

        // X scale - time (5 days)
        const xScale = d3.scaleTime()
            .domain([startDate, endDate])
            .range([0, newWidth]);

        // Y scale - job names (categorical with padding)
        const yScale = d3.scaleBand()
            .domain(jobNames)
            .range([0, height])
            .padding(0.3);

        // Size scale - log scale for duration to radius
        const maxDuration = Math.max(durationStats.max, 1);
        const sizeScale = d3.scaleLog()
            .domain([1, maxDuration + 1])
            .range([minRadius, maxRadius])
            .clamp(true);

        const getRadius = (duration) => sizeScale(Math.max(1, duration + 1));

        // Normalized size for color gradient (0-1)
        const getNormalizedSize = (duration) => {
            if (maxDuration <= 1) return 0.5;
            const logMin = Math.log(1);
            const logMax = Math.log(maxDuration + 1);
            const logVal = Math.log(Math.max(1, duration + 1));
            return (logVal - logMin) / (logMax - logMin);
        };

        // Get bubble color based on status and normalized size
        const getBubbleColor = (status, normalizedSize) => {
            const palette = statusColors[status] || statusColors.completed;
            return d3.interpolateRgb(palette.light, palette.dark)(normalizedSize);
        };

        // Draw horizontal baselines for each job
        jobNames.forEach((jobName) => {
            const y = yScale(jobName) + yScale.bandwidth() / 2;
            g.append('line')
                .attr('x1', 0)
                .attr('x2', newWidth)
                .attr('y1', y)
                .attr('y2', y)
                .attr('stroke', '#E5E7EB')
                .attr('stroke-width', 1);
        });

        // Draw job name labels on the left
        jobNames.forEach((jobName) => {
            const y = yScale(jobName) + yScale.bandwidth() / 2;
            g.append('text')
                .attr('x', -10)
                .attr('y', y)
                .attr('text-anchor', 'end')
                .attr('dominant-baseline', 'middle')
                .attr('fill', '#4B5563')
                .attr('font-size', '11px')
                .text(jobName.length > 18 ? jobName.substring(0, 16) + '...' : jobName);
        });

        // Create clipped group for bubbles
        const bubblesGroup = g.append('g')
            .attr('clip-path', `url(#${clipId})`);

        // Draw bubbles for each run
        runs.forEach((run) => {
            const runDate = new Date(run.started_at);
            const x = xScale(runDate);
            const y = yScale(run.job_name) + yScale.bandwidth() / 2;
            const radius = getRadius(run.duration);
            const normalizedSize = getNormalizedSize(run.duration);
            const color = getBubbleColor(run.status, normalizedSize);
            const hasData = run.rows_loaded > 0;

            const bubble = bubblesGroup.append('circle')
                .attr('cx', x)
                .attr('cy', y)
                .attr('r', radius)
                .attr('fill', hasData ? color : 'white')
                .attr('stroke', color)
                .attr('stroke-width', hasData ? 1 : 2)
                .attr('opacity', 0.9)
                .style('cursor', 'pointer');

            // Add hover events
            bubble.on('mouseenter', function(event) {
                d3.select(this)
                    .attr('opacity', 1)
                    .attr('stroke-width', hasData ? 2 : 3);

                const formattedTime = runDate.toLocaleString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    hour: 'numeric',
                    minute: '2-digit'
                });

                const statusLabel = run.status.charAt(0).toUpperCase() + run.status.slice(1);
                const statusColorClass = run.status === 'completed' ? 'text-green-400' :
                                        run.status === 'partial' ? 'text-orange-400' : 'text-red-400';

                showBubbleTooltip(event, `
                    <div class="font-semibold">${run.job_name}</div>
                    <div class="text-gray-300">${formattedTime}</div>
                    <div class="mt-1">Duration: ${formatDuration(run.duration)}</div>
                    <div>Rows: ${run.rows_loaded.toLocaleString()}</div>
                    <div class="${statusColorClass}">Status: ${statusLabel}</div>
                `);
            })
            .on('mouseleave', function() {
                d3.select(this)
                    .attr('opacity', 0.9)
                    .attr('stroke-width', hasData ? 1 : 2);
                hideBubbleTooltip();
            });
        });

        // X axis at the bottom
        const xAxis = d3.axisBottom(xScale)
            .ticks(d3.timeDay.every(1))
            .tickFormat(d3.timeFormat('%b %d'));

        g.append('g')
            .attr('transform', `translate(0,${height})`)
            .call(xAxis)
            .selectAll('text')
            .style('text-anchor', 'middle')
            .style('font-size', '10px')
            .attr('fill', '#6B7280');

        // Add hour markers (every 6 hours) as minor ticks
        const hourTicks = d3.timeHour.range(startDate, endDate, 6);

        g.append('g')
            .attr('transform', `translate(0,${height})`)
            .selectAll('.hour-tick')
            .data(hourTicks.filter(d => d.getHours() !== 0))
            .enter()
            .append('text')
            .attr('x', d => xScale(d))
            .attr('y', 28)
            .attr('text-anchor', 'middle')
            .attr('fill', '#9CA3AF')
            .attr('font-size', '8px')
            .text(d => d3.timeFormat('%H:00')(d));
    }

    /**
     * Show bubble chart tooltip.
     */
    function showBubbleTooltip(event, html) {
        const tooltip = document.getElementById('etlBubbleTooltip');
        if (!tooltip) return;

        tooltip.innerHTML = html;
        tooltip.classList.remove('hidden');

        const container = document.getElementById('etlBubbleChartContainer');
        if (!container) return;

        const containerRect = container.getBoundingClientRect();
        const tooltipRect = tooltip.getBoundingClientRect();

        let x = event.clientX - containerRect.left + 15;
        let y = event.clientY - containerRect.top - 10;

        // Keep tooltip within container bounds
        if (x + tooltipRect.width > containerRect.width) {
            x = event.clientX - containerRect.left - tooltipRect.width - 15;
        }
        if (y < 0) {
            y = event.clientY - containerRect.top + 20;
        }

        tooltip.style.left = `${x}px`;
        tooltip.style.top = `${y}px`;
    }

    /**
     * Hide bubble chart tooltip.
     */
    function hideBubbleTooltip() {
        const tooltip = document.getElementById('etlBubbleTooltip');
        if (tooltip) {
            tooltip.classList.add('hidden');
        }
    }

    /**
     * Format duration in seconds to human-readable string.
     */
    function formatDuration(seconds) {
        if (seconds === null || seconds === undefined || isNaN(seconds)) return '\u2014';
        if (seconds === 0) return '\u2014';
        if (seconds < 60) return `${Math.round(seconds)}s`;
        if (seconds < 3600) {
            const mins = Math.floor(seconds / 60);
            const secs = Math.round(seconds % 60);
            return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
        }
        const hours = Math.floor(seconds / 3600);
        const mins = Math.round((seconds % 3600) / 60);
        return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
    }

    /**
     * Format number with commas.
     */
    function formatNumber(num) {
        if (num === null || num === undefined) return '0';
        return num.toLocaleString();
    }

    /**
     * Format next run time.
     */
    function formatNextRun(isoString) {
        if (!isoString) return '\u2014';
        const date = new Date(isoString);
        return date.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: 'numeric',
            minute: '2-digit'
        });
    }

    /**
     * Truncate string with ellipsis.
     */
    function truncate(str, maxLength) {
        if (!str) return '';
        return str.length > maxLength ? str.substring(0, maxLength - 2) + '...' : str;
    }

    // =========================================================================
    // PUBLIC API
    // =========================================================================
    return {
        /**
         * Initialize the ETL chapter.
         *
         * @param {Object} options - Optional configuration overrides
         */
        init: function(options) {
            if (options) {
                Object.assign(config, options);
            }

            state.modelId = getModelIdFromUrl();
            state.initialized = true;

            // Bind resize handler
            let resizeTimeout;
            window.addEventListener('resize', function() {
                clearTimeout(resizeTimeout);
                resizeTimeout = setTimeout(function() {
                    if (state.data && state.data.bubble_chart) {
                        renderBubbleChart(state.data.bubble_chart);
                    }
                }, 250);
            });
        },

        /**
         * Load data and render the chapter.
         */
        load: function() {
            if (!state.initialized) {
                this.init();
            }
            fetchData();
        },

        /**
         * Refresh the chapter data.
         */
        refresh: function() {
            state.data = null;
            fetchData();
        },

        /**
         * Go to scheduled jobs page.
         *
         * @param {number} page - Page number (1-based)
         */
        goToScheduledJobsPage: function(page) {
            if (!state.data || !state.data.scheduled_jobs) return;
            const totalPages = Math.ceil(state.data.scheduled_jobs.length / state.scheduledJobsPerPage);
            if (page < 1 || page > totalPages) return;
            renderScheduledJobs(state.data.scheduled_jobs, page);
        },

        /**
         * Get current state (for debugging).
         */
        getState: function() {
            return { ...state };
        }
    };
})();
