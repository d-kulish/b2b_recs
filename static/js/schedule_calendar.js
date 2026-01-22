/**
 * Schedule Calendar Module
 *
 * GitHub-style contribution calendar for visualizing training schedule activity.
 * Shows historical training runs (past) and projected schedules (future).
 *
 * Usage:
 *     ScheduleCalendar.init('#calendarContainer');
 *     ScheduleCalendar.load();
 */

const ScheduleCalendar = (function() {
    'use strict';

    // =============================================================================
    // CONFIGURATION
    // =============================================================================

    const config = {
        containerId: null,
        endpoint: '/api/training-schedules/calendar/',
        weeksToShow: 40,  // 10 past + 30 future
        onDayClick: null,
        onRunClick: null,
        onScheduleClick: null
    };

    let state = {
        calendarData: {},
        today: null,
        range: { start: null, end: null },
        tooltip: null,
        popover: null
    };

    // Day of week labels (0 = Sunday in JS, but we want Monday-first)
    const DAY_LABELS = ['Mon', '', 'Wed', '', 'Fri', '', ''];
    const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    // =============================================================================
    // UTILITY FUNCTIONS
    // =============================================================================

    function parseDate(dateStr) {
        const [year, month, day] = dateStr.split('-').map(Number);
        return new Date(year, month - 1, day);
    }

    function formatDate(date) {
        return date.toISOString().split('T')[0];
    }

    function formatDisplayDate(dateStr) {
        const date = parseDate(dateStr);
        return date.toLocaleDateString('en-US', {
            weekday: 'short',
            month: 'short',
            day: 'numeric',
            year: 'numeric'
        });
    }

    function getActivityLevel(count) {
        if (count === 0) return 0;
        if (count === 1) return 1;
        if (count <= 2) return 2;
        if (count <= 4) return 3;
        return 4;
    }

    function getWeekStart(date) {
        // Get Monday of the week containing date
        const d = new Date(date);
        const day = d.getDay();
        const diff = d.getDate() - day + (day === 0 ? -6 : 1);
        return new Date(d.setDate(diff));
    }

    // =============================================================================
    // API
    // =============================================================================

    async function fetchCalendarData() {
        try {
            const response = await fetch(config.endpoint);
            const data = await response.json();

            if (data.success) {
                state.calendarData = data.calendar || {};
                state.today = data.today;
                state.range = data.range;
                return true;
            } else {
                console.error('Failed to fetch calendar data:', data.error);
                return false;
            }
        } catch (error) {
            console.error('Error fetching calendar data:', error);
            return false;
        }
    }

    // =============================================================================
    // RENDERING
    // =============================================================================

    function render() {
        const container = document.querySelector(config.containerId);
        if (!container) return;

        if (!state.today || !state.range.start) {
            container.innerHTML = `
                <div class="schedule-calendar-empty">
                    <div class="schedule-calendar-empty-icon"><i class="fas fa-calendar-alt"></i></div>
                    <div class="schedule-calendar-empty-text">No schedule data available</div>
                </div>
            `;
            return;
        }

        const today = parseDate(state.today);
        const startDate = parseDate(state.range.start);
        const endDate = parseDate(state.range.end);

        // Get first Monday on or before startDate
        const firstMonday = getWeekStart(startDate);

        // Build weeks array
        const weeks = [];
        let currentDate = new Date(firstMonday);

        while (currentDate <= endDate) {
            const week = [];
            for (let d = 0; d < 7; d++) {
                const dateStr = formatDate(currentDate);
                const dayData = state.calendarData[dateStr];
                const isToday = dateStr === state.today;
                const isFuture = currentDate > today;
                const isInRange = currentDate >= startDate && currentDate <= endDate;

                week.push({
                    date: dateStr,
                    count: dayData?.count || 0,
                    type: dayData?.type || (isFuture ? 'scheduled' : 'historical'),
                    runs: dayData?.runs || [],
                    schedules: dayData?.schedules || [],
                    isToday,
                    isFuture,
                    isInRange
                });

                currentDate.setDate(currentDate.getDate() + 1);
            }
            weeks.push(week);
        }

        // Build month headers
        const monthHeaders = buildMonthHeaders(weeks);

        // Render HTML
        container.innerHTML = `
            <div class="schedule-calendar">
                <div class="schedule-calendar-inner">
                    ${monthHeaders}
                    <div class="schedule-calendar-grid">
                        <div class="schedule-calendar-labels">
                            ${DAY_LABELS.map(label => `
                                <div class="schedule-calendar-day-label">${label}</div>
                            `).join('')}
                        </div>
                        <div class="schedule-calendar-weeks">
                            ${weeks.map((week, weekIdx) => `
                                <div class="schedule-calendar-week" data-week="${weekIdx}">
                                    ${week.map(day => renderDay(day)).join('')}
                                </div>
                            `).join('')}
                        </div>
                    </div>
                    <div class="schedule-calendar-legend">
                        <span class="schedule-calendar-legend-label">Less</span>
                        <div class="schedule-calendar-legend-scale">
                            <div class="schedule-calendar-legend-cell level-0"></div>
                            <div class="schedule-calendar-legend-cell level-1"></div>
                            <div class="schedule-calendar-legend-cell level-2"></div>
                            <div class="schedule-calendar-legend-cell level-3"></div>
                            <div class="schedule-calendar-legend-cell level-4"></div>
                        </div>
                        <span class="schedule-calendar-legend-label">More</span>
                    </div>
                </div>
            </div>
        `;

        // Attach event listeners
        attachEventListeners(container);
    }

    function buildMonthHeaders(weeks) {
        if (weeks.length === 0) return '';

        const months = [];
        let currentMonth = null;
        let weekCount = 0;

        weeks.forEach((week, idx) => {
            // Use the first day's date to determine month
            const firstDay = week[0];
            if (!firstDay.isInRange) return;

            const date = parseDate(firstDay.date);
            const monthKey = `${date.getFullYear()}-${date.getMonth()}`;

            if (monthKey !== currentMonth) {
                if (currentMonth !== null && weekCount > 0) {
                    months.push({ width: weekCount * 14 });
                }
                currentMonth = monthKey;
                months.push({
                    label: MONTH_NAMES[date.getMonth()],
                    width: 0
                });
                weekCount = 0;
            }
            weekCount++;
        });

        // Add last month
        if (weekCount > 0) {
            months.push({ width: weekCount * 14 });
        }

        return `
            <div class="schedule-calendar-header">
                ${months.map(m => m.label ?
                    `<span class="schedule-calendar-month" style="min-width: 14px;">${m.label}</span>` :
                    `<span style="width: ${m.width}px;"></span>`
                ).join('')}
            </div>
        `;
    }

    function renderDay(day) {
        if (!day.isInRange) {
            return '<div class="schedule-calendar-day empty"></div>';
        }

        const level = getActivityLevel(day.count);
        const classes = [
            'schedule-calendar-day',
            `level-${level}`,
            day.isToday ? 'today' : '',
            day.isFuture && day.count > 0 ? 'scheduled' : ''
        ].filter(Boolean).join(' ');

        return `
            <div class="${classes}"
                 data-date="${day.date}"
                 data-count="${day.count}"
                 data-type="${day.type}">
            </div>
        `;
    }

    // =============================================================================
    // EVENT HANDLERS
    // =============================================================================

    function attachEventListeners(container) {
        const days = container.querySelectorAll('.schedule-calendar-day:not(.empty)');

        days.forEach(day => {
            day.addEventListener('mouseenter', handleDayHover);
            day.addEventListener('mouseleave', handleDayLeave);
            day.addEventListener('click', handleDayClick);
        });

        // Close popover on outside click
        document.addEventListener('click', handleDocumentClick);
    }

    function handleDayHover(e) {
        const day = e.target;
        const date = day.dataset.date;
        const count = parseInt(day.dataset.count) || 0;
        const dayData = state.calendarData[date];

        showTooltip(day, date, count, dayData);
    }

    function handleDayLeave() {
        hideTooltip();
    }

    function handleDayClick(e) {
        e.stopPropagation();
        const day = e.target;
        const date = day.dataset.date;
        const count = parseInt(day.dataset.count) || 0;

        if (count === 0) return;

        const dayData = state.calendarData[date];
        showPopover(day, date, dayData);

        if (config.onDayClick) {
            config.onDayClick(date, dayData);
        }
    }

    function handleDocumentClick(e) {
        if (state.popover && !state.popover.contains(e.target)) {
            hidePopover();
        }
    }

    // =============================================================================
    // TOOLTIP
    // =============================================================================

    function showTooltip(element, date, count, dayData) {
        hideTooltip();

        const tooltip = document.createElement('div');
        tooltip.className = 'schedule-calendar-tooltip';

        let itemsHtml = '';
        if (dayData?.runs?.length > 0) {
            const runItems = dayData.runs.slice(0, 3).map(run =>
                `<div class="schedule-calendar-tooltip-item">
                    Run #${run.run_number}: ${run.name || 'Unnamed'}
                </div>`
            ).join('');
            itemsHtml += runItems;
        }
        if (dayData?.schedules?.length > 0) {
            const scheduleItems = dayData.schedules.slice(0, 3).map(schedule =>
                `<div class="schedule-calendar-tooltip-item">
                    <i class="fas fa-clock" style="font-size: 9px; margin-right: 4px;"></i>
                    ${schedule.name}
                </div>`
            ).join('');
            itemsHtml += scheduleItems;
        }

        tooltip.innerHTML = `
            <div class="schedule-calendar-tooltip-date">${formatDisplayDate(date)}</div>
            <div class="schedule-calendar-tooltip-count">
                ${count} ${count === 1 ? 'activity' : 'activities'}
            </div>
            ${itemsHtml ? `<div class="schedule-calendar-tooltip-items">${itemsHtml}</div>` : ''}
        `;

        document.body.appendChild(tooltip);
        state.tooltip = tooltip;

        // Position tooltip
        const rect = element.getBoundingClientRect();
        const tooltipRect = tooltip.getBoundingClientRect();

        tooltip.style.left = `${rect.left + rect.width / 2 - tooltipRect.width / 2}px`;
        tooltip.style.top = `${rect.top - tooltipRect.height - 8}px`;
    }

    function hideTooltip() {
        if (state.tooltip) {
            state.tooltip.remove();
            state.tooltip = null;
        }
    }

    // =============================================================================
    // POPOVER
    // =============================================================================

    function showPopover(element, date, dayData) {
        hidePopover();

        const popover = document.createElement('div');
        popover.className = 'schedule-calendar-popover';

        const runs = dayData?.runs || [];
        const schedules = dayData?.schedules || [];
        const total = runs.length + schedules.length;

        let itemsHtml = '';

        runs.forEach(run => {
            itemsHtml += `
                <div class="schedule-calendar-popover-item" data-run-id="${run.id}">
                    <div class="schedule-calendar-popover-item-name">
                        <i class="fas fa-check-circle" style="color: #10b981; margin-right: 6px;"></i>
                        Run #${run.run_number}
                    </div>
                    <div class="schedule-calendar-popover-item-meta">
                        ${run.name || 'Unnamed'} - ${run.status}
                    </div>
                </div>
            `;
        });

        schedules.forEach(schedule => {
            itemsHtml += `
                <div class="schedule-calendar-popover-item" data-schedule-id="${schedule.id}">
                    <div class="schedule-calendar-popover-item-name">
                        <i class="fas fa-clock" style="color: #3b82f6; margin-right: 6px;"></i>
                        ${schedule.name}
                    </div>
                    <div class="schedule-calendar-popover-item-meta">
                        ${schedule.schedule_type} schedule
                    </div>
                </div>
            `;
        });

        popover.innerHTML = `
            <button class="schedule-calendar-popover-close" onclick="ScheduleCalendar.hidePopover()">
                <i class="fas fa-times"></i>
            </button>
            <div class="schedule-calendar-popover-header">
                <div class="schedule-calendar-popover-date">${formatDisplayDate(date)}</div>
                <div class="schedule-calendar-popover-count">
                    ${total} ${total === 1 ? 'activity' : 'activities'}
                </div>
            </div>
            <div class="schedule-calendar-popover-content">
                ${itemsHtml || '<div style="padding: 16px; color: #6b7280;">No activities</div>'}
            </div>
        `;

        document.body.appendChild(popover);
        state.popover = popover;

        // Position popover
        const rect = element.getBoundingClientRect();
        const popoverRect = popover.getBoundingClientRect();

        let left = rect.left + rect.width / 2 - popoverRect.width / 2;
        let top = rect.bottom + 8;

        // Keep within viewport
        if (left < 8) left = 8;
        if (left + popoverRect.width > window.innerWidth - 8) {
            left = window.innerWidth - popoverRect.width - 8;
        }
        if (top + popoverRect.height > window.innerHeight - 8) {
            top = rect.top - popoverRect.height - 8;
        }

        popover.style.left = `${left}px`;
        popover.style.top = `${top}px`;

        // Attach click handlers for items
        popover.querySelectorAll('[data-run-id]').forEach(item => {
            item.addEventListener('click', () => {
                const runId = item.dataset.runId;
                if (config.onRunClick) {
                    config.onRunClick(runId);
                }
                hidePopover();
            });
        });

        popover.querySelectorAll('[data-schedule-id]').forEach(item => {
            item.addEventListener('click', () => {
                const scheduleId = item.dataset.scheduleId;
                if (config.onScheduleClick) {
                    config.onScheduleClick(scheduleId);
                }
                hidePopover();
            });
        });
    }

    function hidePopover() {
        if (state.popover) {
            state.popover.remove();
            state.popover = null;
        }
    }

    // =============================================================================
    // PUBLIC API
    // =============================================================================

    function init(containerId, options = {}) {
        config.containerId = containerId;

        if (options.endpoint) config.endpoint = options.endpoint;
        if (options.onDayClick) config.onDayClick = options.onDayClick;
        if (options.onRunClick) config.onRunClick = options.onRunClick;
        if (options.onScheduleClick) config.onScheduleClick = options.onScheduleClick;

        return ScheduleCalendar;
    }

    async function load() {
        const container = document.querySelector(config.containerId);
        if (container) {
            container.innerHTML = `
                <div class="schedule-calendar-empty">
                    <div class="schedule-calendar-empty-icon"><i class="fas fa-spinner fa-spin"></i></div>
                    <div class="schedule-calendar-empty-text">Loading schedule data...</div>
                </div>
            `;
        }

        const success = await fetchCalendarData();
        if (success) {
            render();
        }
    }

    function refresh() {
        return load();
    }

    function destroy() {
        hideTooltip();
        hidePopover();
        document.removeEventListener('click', handleDocumentClick);

        const container = document.querySelector(config.containerId);
        if (container) {
            container.innerHTML = '';
        }
    }

    // Expose public API
    return {
        init,
        load,
        refresh,
        destroy,
        hidePopover
    };

})();
