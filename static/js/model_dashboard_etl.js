/**
 * Model Dashboard - ETL Chapter
 *
 * Displays ETL Dashboard data: KPIs, Scheduled Jobs table, and Diverging Chart.
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
        contentIds: ['#etlChapterKpiRow', '#etlChapterRow2'],
        kpiRowId: '#etlChapterKpiRow',
        row2Id: '#etlChapterRow2',
        scheduledSectionId: '#etlScheduledSection',
        chartSectionId: '#etlChartSection',
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

    // =========================================================================
    // DIVERGING CHART COLOR PALETTES
    // =========================================================================
    const FAILED_PALETTE = [
        '#FDD835',  // job_index 0 (closest to 0) - yellow
        '#FB8C00',  // job_index 1 - orange
        '#E65100',  // job_index 2 - deep orange
        '#BF360C',  // job_index 3 - dark red
        '#B71C1C',  // job_index 4
        '#D84315',  // job_index 5
        '#F57C00',  // job_index 6
        '#FBC02D',  // job_index 7
    ];
    const SUCCEEDED_PALETTE = [
        '#A5D6A7',  // job_index 0 (closest to 0) - light green
        '#4CAF50',  // job_index 1 - green
        '#2E7D32',  // job_index 2 - dark green
        '#1565C0',  // job_index 3 - blue
        '#00796B',  // job_index 4
        '#00897B',  // job_index 5
        '#1B5E20',  // job_index 6
        '#43A047',  // job_index 7
    ];

    const RUN_GAP = 0.4;

    function getJobColor(palette, jobIndex) {
        return palette[Math.min(jobIndex, palette.length - 1)];
    }

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
        config.contentIds.forEach(id => document.querySelector(id).classList.add('hidden'));
    }

    /**
     * Show empty state.
     */
    function showEmpty() {
        document.querySelector(config.loadingId).classList.add('hidden');
        document.querySelector(config.emptyId).classList.remove('hidden');
        config.contentIds.forEach(id => document.querySelector(id).classList.add('hidden'));
    }

    /**
     * Show content.
     */
    function showContent() {
        document.querySelector(config.loadingId).classList.add('hidden');
        document.querySelector(config.emptyId).classList.add('hidden');
        config.contentIds.forEach(id => document.querySelector(id).classList.remove('hidden'));
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
                        showContent();  // Show content first so chart container has dimensions
                        renderDivergingChart(data.data.diverging_chart);
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
        let successRateColorClass = 'kpi-icon-green';
        if (kpi.success_rate < 70) {
            successRateColorClass = 'kpi-icon-red';
        } else if (kpi.success_rate < 90) {
            successRateColorClass = 'kpi-icon-yellow';
        }

        // Determine failed runs color
        const failedColorClass = kpi.failed_runs > 0 ? 'kpi-icon-red' : 'kpi-icon-green';

        container.innerHTML = `
            <div class="kpi-card">
                <div class="kpi-icon-wrapper kpi-icon-blue">
                    <i class="fas fa-play-circle"></i>
                </div>
                <div class="kpi-content">
                    <span class="kpi-value">${kpi.total_runs}</span>
                    <span class="kpi-label">Total Runs</span>
                </div>
            </div>

            <div class="kpi-card">
                <div class="kpi-icon-wrapper ${successRateColorClass}">
                    <i class="fas fa-check-circle"></i>
                </div>
                <div class="kpi-content">
                    <span class="kpi-value">${kpi.success_rate}%</span>
                    <span class="kpi-label">Success Rate</span>
                </div>
            </div>

            <div class="kpi-card">
                <div class="kpi-icon-wrapper kpi-icon-green">
                    <i class="fas fa-check-double"></i>
                </div>
                <div class="kpi-content">
                    <span class="kpi-value">${kpi.successful_runs}</span>
                    <span class="kpi-label">Successful Runs</span>
                </div>
            </div>

            <div class="kpi-card">
                <div class="kpi-icon-wrapper ${failedColorClass}">
                    <i class="fas fa-times-circle"></i>
                </div>
                <div class="kpi-content">
                    <span class="kpi-value">${kpi.failed_runs}</span>
                    <span class="kpi-label">Failed Runs</span>
                </div>
            </div>

            <div class="kpi-card">
                <div class="kpi-icon-wrapper kpi-icon-purple">
                    <i class="fas fa-database"></i>
                </div>
                <div class="kpi-content">
                    <span class="kpi-value">${formatNumber(kpi.total_rows_extracted)}</span>
                    <span class="kpi-label">Rows Migrated</span>
                </div>
            </div>

            <div class="kpi-card">
                <div class="kpi-icon-wrapper kpi-icon-blue">
                    <i class="fas fa-clock"></i>
                </div>
                <div class="kpi-content">
                    <span class="kpi-value">${formatDuration(kpi.avg_duration_seconds)}</span>
                    <span class="kpi-label">Avg Duration</span>
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
                <h3><i class="fas fa-calendar-alt mr-2 text-gray-400"></i>Scheduled Jobs</h3>
                <div class="scheduled-empty-state">
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
                ? '<span class="badge-paused"><i class="fas fa-pause"></i> Paused</span>'
                : '<span class="badge-enabled"><i class="fas fa-check"></i> Enabled</span>';

            return `
                <tr>
                    <td class="job-name" title="${job.name}">${truncate(job.name, 18)}</td>
                    <td class="job-schedule">${job.schedule_display}</td>
                    <td class="job-next-run">${nextRunDisplay}</td>
                    <td>${stateBadge}</td>
                </tr>
            `;
        }).join('');

        // Build pagination with page numbers if needed
        let paginationHtml = '';
        if (totalPages > 1) {
            let pageNumbersHtml = '';
            for (let i = 1; i <= totalPages; i++) {
                if (i === page) {
                    pageNumbersHtml += `<button class="btn btn-primary btn-xs" style="background-color: #6b7280; color: #fff; border-color: #6b7280;">${i}</button>`;
                } else {
                    pageNumbersHtml += `<button class="btn btn-secondary btn-xs" onclick="ModelDashboardEtl.goToScheduledJobsPage(${i})">${i}</button>`;
                }
            }

            paginationHtml = `
                <div class="flex items-center justify-between mt-4 pt-4 border-t border-gray-200">
                    <div class="text-sm text-gray-600">Showing ${startIndex + 1}-${endIndex} of ${totalJobs}</div>
                    <div class="flex items-center gap-2">
                        ${page > 1 ? `<button class="btn btn-secondary btn-xs" onclick="ModelDashboardEtl.goToScheduledJobsPage(${page - 1})">Previous</button>` : ''}
                        ${pageNumbersHtml}
                        ${page < totalPages ? `<button class="btn btn-secondary btn-xs" onclick="ModelDashboardEtl.goToScheduledJobsPage(${page + 1})">Next</button>` : ''}
                    </div>
                </div>
            `;
        }

        container.innerHTML = `
            <h3><i class="fas fa-calendar-alt mr-2 text-gray-400"></i>Scheduled Jobs</h3>
            <div class="scheduled-jobs-table-wrapper">
                <table class="scheduled-jobs-table">
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
     * Build JOB_ORDER map from runs' data_source_created_at (oldest first = index 0).
     */
    function buildJobOrder(runs) {
        const jobCreatedMap = {};
        runs.forEach(run => {
            if (!jobCreatedMap[run.job_name] || run.data_source_created_at < jobCreatedMap[run.job_name]) {
                jobCreatedMap[run.job_name] = run.data_source_created_at;
            }
        });
        const sorted = Object.entries(jobCreatedMap).sort((a, b) => a[1].localeCompare(b[1]));
        const order = {};
        sorted.forEach(([name], i) => { order[name] = i; });
        return order;
    }

    /**
     * Process runs into daily stacked bar data.
     */
    function processChartData(chartData) {
        const runs = chartData.runs;
        const JOB_ORDER = buildJobOrder(runs);

        const processed = runs.map(run => ({
            ...run,
            status_mapped: (run.status === 'completed' || run.status === 'partial') ? 'succeeded' : 'failed',
            job_index: JOB_ORDER[run.job_name] ?? 99,
            date: run.started_at.split('T')[0],
            duration_minutes: Math.max(1, Math.ceil(run.duration / 60)),
        }));

        // Generate full 30-day date range from API
        const startDate = new Date(chartData.date_range.start);
        const endDate = new Date(chartData.date_range.end);
        const dates = [];
        const d = new Date(startDate);
        while (d <= endDate) {
            dates.push(d.toISOString().split('T')[0]);
            d.setDate(d.getDate() + 1);
        }

        // Group runs by date
        const byDate = {};
        dates.forEach(dt => { byDate[dt] = []; });
        processed.forEach(run => {
            if (byDate[run.date]) byDate[run.date].push(run);
        });

        // Build stacked bars per day
        const dailyStacks = {};
        let maxPositive = 0;
        let maxNegative = 0;

        dates.forEach(date => {
            const dayRuns = byDate[date];
            const succeeded = dayRuns.filter(r => r.status_mapped === 'succeeded');
            const failed = dayRuns.filter(r => r.status_mapped === 'failed');

            succeeded.sort((a, b) => a.job_index - b.job_index || new Date(a.started_at) - new Date(b.started_at));
            failed.sort((a, b) => a.job_index - b.job_index || new Date(a.started_at) - new Date(b.started_at));

            const positiveBars = [];
            let posY = 0;
            succeeded.forEach((run, i) => {
                if (i > 0) posY += RUN_GAP;
                positiveBars.push({ y_start: posY, y_end: posY + run.duration_minutes, height: run.duration_minutes, ...run });
                posY += run.duration_minutes;
            });

            const negativeBars = [];
            let negY = 0;
            failed.forEach((run, i) => {
                if (i > 0) negY += RUN_GAP;
                negativeBars.push({ y_start: negY, y_end: negY + run.duration_minutes, height: run.duration_minutes, ...run });
                negY += run.duration_minutes;
            });

            maxPositive = Math.max(maxPositive, posY);
            maxNegative = Math.max(maxNegative, negY);

            dailyStacks[date] = { positiveBars, negativeBars, totalPositive: posY, totalNegative: negY };
        });

        return { dailyStacks, maxPositive, maxNegative, dates, JOB_ORDER };
    }

    /**
     * Render diverging stacked bar chart using D3.js.
     *
     * @param {Object} chartData - Diverging chart data from API
     */
    function renderDivergingChart(chartData) {
        const container = document.querySelector(config.chartSectionId);
        if (!container) return;

        const runs = chartData.runs;

        // Chart header
        const chartHeaderHtml = `
            <div class="flex items-center justify-between mb-3">
                <h3 class="text-sm font-semibold text-gray-700">ETL Job Runs (Last 30 Days)</h3>
            </div>
        `;

        // Empty state
        if (!runs || runs.length === 0) {
            container.innerHTML = `
                ${chartHeaderHtml}
                <div id="etlDivergingChartContainer" class="relative">
                    <div class="text-center py-12 bg-gray-50 rounded-lg">
                        <i class="fas fa-chart-bar text-gray-400 text-2xl mb-2"></i>
                        <p class="text-gray-600 text-sm font-medium">No job runs</p>
                        <p class="text-gray-400 text-xs mt-1">Run ETL jobs to see visualization</p>
                    </div>
                </div>
            `;
            return;
        }

        // Process data
        const { dailyStacks, maxPositive, maxNegative, dates, JOB_ORDER } = processChartData(chartData);

        // Render chart container
        container.innerHTML = `
            ${chartHeaderHtml}
            <div id="etlDivergingChartContainer" class="relative flex-1">
                <svg id="etlDivergingChart" class="w-full"></svg>
                <div id="etlDivergingTooltip" class="etl-bubble-tooltip hidden"></div>
            </div>
            <div id="etlJobLegend" style="display:flex;flex-wrap:wrap;justify-content:center;gap:12px;margin-top:8px;padding-top:8px;border-top:1px solid #f3f4f6;"></div>
        `;

        // Get container dimensions
        const chartContainer = document.querySelector('#etlDivergingChartContainer');
        const containerWidth = chartContainer.clientWidth;

        if (containerWidth < 50) {
            console.warn('ModelDashboardEtl: Chart container too narrow, skipping render');
            return;
        }

        // Chart dimensions — auto-scale unitSize to fit within the 370px container
        // Container: 370px total, minus 32px padding, ~30px header, ~35px legend = ~273px for SVG
        const margin = { top: 20, right: 10, bottom: 45, left: 40 };
        const svgAvailableHeight = 260;
        const totalUnits = maxPositive + maxNegative + 2;
        const innerHeight = svgAvailableHeight - margin.top - margin.bottom;
        const unitSize = Math.min(16, Math.max(2, innerHeight / Math.max(totalUnits, 1)));
        const height = Math.max(totalUnits * unitSize + 20, 100);
        const width = containerWidth - margin.left - margin.right;

        const svgEl = d3.select('#etlDivergingChart');
        svgEl.attr('width', containerWidth).attr('height', height + margin.top + margin.bottom);

        const svg = svgEl.append('g')
            .attr('transform', `translate(${margin.left},${margin.top})`);

        const xScale = d3.scaleBand()
            .domain(dates)
            .range([0, width])
            .padding(0.12);

        const zeroY = (maxPositive + 1) * unitSize;

        const dateParse = d3.timeParse('%Y-%m-%d');
        const dateFormat = d3.timeFormat('%b %d');
        const parsedDates = dates.map(d => dateParse(d));

        // Weekend backgrounds
        dates.forEach((date, i) => {
            const dow = parsedDates[i].getDay();
            if (dow === 0 || dow === 6) {
                svg.append('rect')
                    .attr('x', xScale(date) - xScale.step() * xScale.padding() / 2)
                    .attr('y', 0)
                    .attr('width', xScale.step())
                    .attr('height', height)
                    .attr('fill', '#f7fef9');
            }
        });

        // Month separator lines
        dates.forEach((date, i) => {
            if (i > 0 && parsedDates[i].getMonth() !== parsedDates[i - 1].getMonth()) {
                const lineX = xScale(date) - xScale.step() * xScale.padding() / 2;
                svg.append('line')
                    .attr('x1', lineX).attr('x2', lineX)
                    .attr('y1', 0).attr('y2', height)
                    .attr('stroke', '#111827')
                    .attr('stroke-width', 1.5);
            }
        });

        // Zero line
        svg.append('line')
            .attr('x1', 0).attr('x2', width)
            .attr('y1', zeroY).attr('y2', zeroY)
            .attr('stroke', '#9ca3af').attr('stroke-width', 1.5);

        svg.append('text')
            .attr('x', -6).attr('y', zeroY)
            .attr('text-anchor', 'end')
            .attr('dominant-baseline', 'middle')
            .attr('font-size', '10px')
            .attr('fill', '#6b7280')
            .attr('font-weight', '600')
            .text('0');

        // Y-axis ticks
        for (let i = 5; i <= maxPositive; i += 5) {
            const y = zeroY - i * unitSize;
            if (y > 5) {
                svg.append('text').attr('x', -6).attr('y', y).attr('text-anchor', 'end')
                    .attr('dominant-baseline', 'middle').attr('font-size', '9px').attr('fill', '#6b7280').text(i);
                svg.append('line').attr('x1', 0).attr('x2', width).attr('y1', y).attr('y2', y)
                    .attr('stroke', '#e5e7eb').attr('stroke-width', 0.5).attr('stroke-dasharray', '2,3');
            }
        }
        for (let i = -5; i >= -maxNegative; i -= 5) {
            const y = zeroY - i * unitSize;
            if (y < height - 5) {
                svg.append('text').attr('x', -6).attr('y', y).attr('text-anchor', 'end')
                    .attr('dominant-baseline', 'middle').attr('font-size', '9px').attr('fill', '#6b7280').text(i);
                svg.append('line').attr('x1', 0).attr('x2', width).attr('y1', y).attr('y2', y)
                    .attr('stroke', '#e5e7eb').attr('stroke-width', 0.5).attr('stroke-dasharray', '2,3');
            }
        }

        // Y axis label
        svg.append('text')
            .attr('transform', 'rotate(-90)')
            .attr('x', -(height / 2))
            .attr('y', -30)
            .attr('text-anchor', 'middle')
            .attr('font-size', '10px')
            .attr('fill', '#6b7280')
            .text('Duration');

        // X-axis labels (every 3rd day + last)
        dates.forEach((date, i) => {
            const x = xScale(date) + xScale.bandwidth() / 2;
            const parsed = parsedDates[i];
            const hasData = dailyStacks[date].positiveBars.length > 0 || dailyStacks[date].negativeBars.length > 0;

            if (i % 3 === 0 || i === dates.length - 1) {
                svg.append('text')
                    .attr('x', x).attr('y', height + 12)
                    .attr('text-anchor', 'middle')
                    .attr('font-size', '8px')
                    .attr('fill', hasData ? '#374151' : '#d1d5db')
                    .text(dateFormat(parsed));

                const dow = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][parsed.getDay()];
                svg.append('text')
                    .attr('x', x).attr('y', height + 23)
                    .attr('text-anchor', 'middle')
                    .attr('font-size', '7px')
                    .attr('fill', hasData ? '#9ca3af' : '#e5e7eb')
                    .text(dow);
            }
        });

        const tooltip = d3.select('#etlDivergingTooltip');

        function barStroke(color) {
            return d3.color(color).darker(0.4);
        }

        // Draw bars
        dates.forEach(date => {
            const stack = dailyStacks[date];
            const colX = xScale(date);
            const bw = xScale.bandwidth();

            // Succeeded bars (upward)
            stack.positiveBars.forEach(bar => {
                const color = getJobColor(SUCCEEDED_PALETTE, bar.job_index);
                const barTopY = zeroY - bar.y_end * unitSize;
                const barH = bar.height * unitSize;

                svg.append('rect')
                    .attr('x', colX).attr('y', barTopY)
                    .attr('width', bw).attr('height', Math.max(barH - 1, 2))
                    .attr('rx', 2)
                    .attr('fill', color)
                    .attr('stroke', barStroke(color))
                    .attr('stroke-width', 0.5)
                    .style('cursor', 'pointer')
                    .on('mouseover', function(event) {
                        d3.select(this).attr('stroke-width', 2.5).attr('stroke', '#111827');
                        showDivergingTooltip(event, bar, 'Succeeded', date);
                    })
                    .on('mousemove', function(event) {
                        positionTooltip(event);
                    })
                    .on('mouseout', function() {
                        d3.select(this).attr('stroke-width', 0.5).attr('stroke', barStroke(color));
                        hideDivergingTooltip();
                    });
            });

            // Failed bars (downward)
            stack.negativeBars.forEach(bar => {
                const color = getJobColor(FAILED_PALETTE, bar.job_index);
                const barTopY = zeroY + bar.y_start * unitSize + 1;
                const barH = bar.height * unitSize;

                svg.append('rect')
                    .attr('x', colX).attr('y', barTopY)
                    .attr('width', bw).attr('height', Math.max(barH - 1, 2))
                    .attr('rx', 2)
                    .attr('fill', color)
                    .attr('stroke', barStroke(color))
                    .attr('stroke-width', 0.5)
                    .style('cursor', 'pointer')
                    .on('mouseover', function(event) {
                        d3.select(this).attr('stroke-width', 2.5).attr('stroke', '#111827');
                        showDivergingTooltip(event, bar, 'Failed', date);
                    })
                    .on('mousemove', function(event) {
                        positionTooltip(event);
                    })
                    .on('mouseout', function() {
                        d3.select(this).attr('stroke-width', 0.5).attr('stroke', barStroke(color));
                        hideDivergingTooltip();
                    });
            });

            // Empty day indicator
            if (stack.positiveBars.length === 0 && stack.negativeBars.length === 0) {
                const x = colX + bw / 2;
                svg.append('line')
                    .attr('x1', x).attr('x2', x)
                    .attr('y1', zeroY - 3).attr('y2', zeroY + 3)
                    .attr('stroke', '#e5e7eb').attr('stroke-width', 1);
            }
        });

        // Render job legend below chart
        renderJobLegend(JOB_ORDER);
    }

    /**
     * Show diverging chart tooltip.
     */
    function showDivergingTooltip(event, bar, statusLabel, date) {
        const tooltip = document.getElementById('etlDivergingTooltip');
        if (!tooltip) return;

        const durationStr = bar.duration < 60
            ? `${bar.duration.toFixed(1)}s`
            : `${Math.floor(bar.duration / 60)}m ${Math.round(bar.duration % 60)}s`;

        const statusClass = statusLabel === 'Succeeded' ? 'text-green-400' : 'text-red-400';
        let errorHtml = '';
        if (bar.error_message) {
            const shortError = bar.error_message.length > 120 ? bar.error_message.substring(0, 118) + '...' : bar.error_message;
            errorHtml = `<div class="text-red-300 mt-1 text-xs" style="border-top:1px solid rgba(255,255,255,0.15);padding-top:4px;">Error: ${shortError}</div>`;
        }

        tooltip.innerHTML = `
            <div class="font-semibold">${bar.job_name}</div>
            <div class="${statusClass}" style="font-size:10px;font-weight:600;text-transform:uppercase;">${statusLabel}</div>
            <div class="text-gray-300 mt-1">Duration: ${durationStr} (${bar.duration_minutes} min bar)</div>
            <div class="text-gray-300">Rows: ${(bar.rows_loaded || 0).toLocaleString()}</div>
            <div class="text-gray-300">Started: ${new Date(bar.started_at).toLocaleTimeString()}</div>
            <div class="text-gray-300">Date: ${date}</div>
            ${errorHtml}
        `;
        tooltip.classList.remove('hidden');
        positionTooltip(event);
    }

    /**
     * Position tooltip near mouse.
     */
    function positionTooltip(event) {
        const tooltip = document.getElementById('etlDivergingTooltip');
        const container = document.getElementById('etlDivergingChartContainer');
        if (!tooltip || !container) return;

        const containerRect = container.getBoundingClientRect();
        const tooltipRect = tooltip.getBoundingClientRect();

        let x = event.clientX - containerRect.left + 15;
        let y = event.clientY - containerRect.top - 10;

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
     * Hide diverging chart tooltip.
     */
    function hideDivergingTooltip() {
        const tooltip = document.getElementById('etlDivergingTooltip');
        if (tooltip) {
            tooltip.classList.add('hidden');
        }
    }

    /**
     * Render job legend below the chart.
     */
    function renderJobLegend(JOB_ORDER) {
        const container = document.getElementById('etlJobLegend');
        if (!container) return;
        container.innerHTML = '';

        const jobs = Object.entries(JOB_ORDER).sort((a, b) => a[1] - b[1]);
        jobs.forEach(([name, idx]) => {
            const succColor = getJobColor(SUCCEEDED_PALETTE, idx);
            const failColor = getJobColor(FAILED_PALETTE, idx);
            const shortName = name.length > 20 ? name.substring(0, 18) + '...' : name;
            const item = document.createElement('div');
            item.style.cssText = 'display:flex;align-items:center;gap:4px;';
            item.innerHTML = `
                <div style="display:flex;gap:2px;">
                    <div style="width:8px;height:12px;background:${succColor};border-radius:2px;" title="Succeeded"></div>
                    <div style="width:8px;height:12px;background:${failColor};border-radius:2px;" title="Failed"></div>
                </div>
                <span style="font-size:10px;color:#4b5563;" title="${name}">${shortName}</span>
            `;
            container.appendChild(item);
        });
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
                    if (state.data && state.data.diverging_chart) {
                        renderDivergingChart(state.data.diverging_chart);
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
