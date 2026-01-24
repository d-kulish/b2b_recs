# Chapter: Models Registry

## Document Purpose
This document provides detailed specifications for implementing the **Models Registry** chapter on the Training page. The Models Registry provides visibility into production-ready models registered in Vertex AI Model Registry, their deployment status, and scheduled training activities.

**Last Updated**: 2026-01-24

---

## Overview

### Purpose
The Models Registry chapter allows users to:
1. View all models registered in Vertex AI Model Registry
2. Track model blessing status (passed/failed evaluation)
3. Monitor deployment status across endpoints
4. Visualize scheduled training activity over time
5. Deploy blessed models to serving endpoints
6. Compare model versions and performance metrics

### Key Principle
**Models Registry is the production view of successfully trained models.** Only models that complete the full TFX pipeline (including Pusher component) appear here. Users can track which models are blessed, deployed, and scheduled for retraining.

### Data Sources
- `TrainingRun` model with `vertex_model_resource_name` populated
- `TrainingSchedule` model for scheduled runs
- Vertex AI Model Registry API for live status
- Vertex AI Endpoints API for deployment status

---

## User Interface

### Chapter Layout Structure

The Models Registry chapter is the third chapter on the Training page, positioned below the "Training" chapter.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 📦 Models Registry                                              [+ Deploy]  │
│    Production-ready models in Vertex AI                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ┌─ KPI Summary Row ─────────────────────────────────────────────────────┐   │
│ │ 📦 Total   │ ✅ Blessed  │ 🚀 Deployed │ ⏸️ Idle    │ 📅 Latest       │   │
│ │ Models: 8  │ 7           │ 3           │ 4          │ 21 Jan 2026     │   │
│ └────────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│ ┌─ Training Schedule Grid (GitHub-style) ───────────────────────────────┐   │
│ │  Training Activity: Past 10 weeks │ Next 30 weeks                      │   │
│ │  ┌─────────────────────────────────────────────────────────────────┐  │   │
│ │  │     Nov    Dec    Jan    Feb    Mar    Apr    ...    Oct        │  │   │
│ │  │ M  ░░░░░░░░░░░░██░░░░░░░░░░░░░░██░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │  │   │
│ │  │ T  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │  │   │
│ │  │ W  ░░░░░░██░░░░░░░░░░██░░░░░░██░░░░░░██░░░░░░██░░░░░░██░░░░░░██  │  │   │
│ │  │ T  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │  │   │
│ │  │ F  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │  │   │
│ │  │ S  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │  │   │
│ │  │ S  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │  │   │
│ │  └─────────────────────────────────────────────────────────────────┘  │   │
│ │  Legend: ░ No training  █ 1 model  ██ 2+ models   ← Past │ Future →   │   │
│ └────────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│ ┌─ Filter Bar ──────────────────────────────────────────────────────────┐   │
│ │ [All Types ▼] [All Status ▼] [Sort: Latest ▼]  🔍 Search models...    │   │
│ └────────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│ ┌─ Registered Models Table ─────────────────────────────────────────────┐   │
│ │ # │ Model Name        │ Type      │ Ver │ R@100 │ Status   │ Actions  │   │
│ │ 1 │ recs-prod-v3      │ Retrieval │ 3   │ 0.823 │ DEPLOYED │ [▼]      │   │
│ │ 2 │ recs-prod-v2      │ Retrieval │ 2   │ 0.801 │ IDLE     │ [▼]      │   │
│ │ 3 │ ranking-q4        │ Ranking   │ 1   │ 0.452 │ DEPLOYED │ [▼]      │   │
│ │ 4 │ test_v1-v2        │ Retrieval │ 2   │ —     │ BLESSED  │ [▼]      │   │
│ │ ...                                                                    │   │
│ └────────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Section 1: KPI Summary Row

### Layout
A horizontal row displaying key metrics about registered models, consistent with the Best Experiments KPI row pattern.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  📦 Total    │  ✅ Blessed   │  🚀 Deployed  │  ⏸️ Idle     │  📅 Latest    │
│  Models: 8   │  7            │  3            │  4           │  21 Jan 2026  │
└──────────────────────────────────────────────────────────────────────────────┘
```

### KPI Definitions

| KPI | Icon | Description | Calculation |
|-----|------|-------------|-------------|
| **Total Models** | 📦 | Total registered models | Count of TrainingRuns with `vertex_model_resource_name` |
| **Blessed** | ✅ | Models that passed evaluation | Count where `is_blessed = True` |
| **Deployed** | 🚀 | Currently serving models | Count where `is_deployed = True` |
| **Idle** | ⏸️ | Blessed but not deployed | Count where `is_blessed = True AND is_deployed = False` |
| **Latest** | 📅 | Most recent registration | Max `registered_at` formatted as date |

### Styling
- Background: White card with subtle shadow
- KPI boxes: Same styling as Best Experiments KPI boxes
- Icons: Font Awesome icons with colored backgrounds
- Values: Large bold text (24px)
- Labels: Small muted text below values

---

## Section 2: Training Schedule Grid (GitHub-style Activity Grid)

### Purpose
Visualize scheduled training runs over time using a GitHub contributions-style grid. This provides at-a-glance visibility into:
- Historical training activity (past 10 weeks)
- Planned future training (next 30 weeks)
- Training density (how many models per day)

### Layout Structure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Training Activity                                              [?] Help    │
│  ───────────────────────────────────────────────────────────────────────────│
│                                                                              │
│       │← Past 10 weeks │ Today │ Next 30 weeks →                            │
│       Nov       Dec       Jan       Feb       Mar       Apr    ...    Oct   │
│    ┌─────────────────────────────────────────────────────────────────────┐  │
│  M │ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ █ ░ ░ ░ ░ ░ ░ ░ ░ █ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ... │  │
│  T │ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ... │  │
│  W │ ░ ░ █ ░ ░ ░ █ ░ ░ ░ █ ░ ░ ░ █ ░ ░ ░ █ ░ ░ ░ █ ░ ░ ░ █ ░ ░ ░ █ ... │  │
│  T │ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ... │  │
│  F │ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ... │  │
│  S │ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ... │  │
│  S │ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ░ ... │  │
│    └─────────────────────────────────────────────────────────────────────┘  │
│                                                 │                            │
│  Legend:  ░ No training   █ 1 model   ██ 2 models   ███ 3+ models          │
│           ◄── Historical (completed/failed)  │  Scheduled (future) ──►      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Grid Specifications

| Property | Value |
|----------|-------|
| **Time Range** | Past 10 weeks + Next 30 weeks = 40 weeks total |
| **Rows** | 7 (Monday through Sunday) |
| **Columns** | 40 weeks × 1 column per week = 40 columns |
| **Cell Size** | 12px × 12px with 2px gap |
| **Total Width** | ~520px (scrollable if needed) |

### Cell States & Colors

| State | Color | Meaning |
|-------|-------|---------|
| **Empty** | `#ebedf0` (light gray) | No training scheduled |
| **1 model** | `#9be9a8` (light green) | 1 training run scheduled |
| **2 models** | `#40c463` (medium green) | 2 training runs scheduled |
| **3+ models** | `#30a14e` (dark green) | 3 or more training runs |
| **Today marker** | `#2563eb` blue border | Current day indicator |

### Cell Content

Each cell displays:
- **Number**: Count of models scheduled (1, 2, 3, etc.) - only if > 0
- **Tooltip on hover**: Date and model names

```
┌─────────────────────────────────────┐
│  Wednesday, Jan 29, 2026            │
│  ─────────────────────────────────  │
│  2 training runs scheduled:         │
│  • recs-weekly-refresh              │
│  • ranking-model-v2                 │
└─────────────────────────────────────┘
```

### Cell Click Interaction

Clicking a cell opens a small popover showing:

```
┌─────────────────────────────────────┐
│  Wed, Jan 29, 2026          [×]     │
│  ─────────────────────────────────  │
│                                      │
│  📅 Scheduled Training Runs          │
│                                      │
│  ┌────────────────────────────────┐ │
│  │ 🔁 recs-weekly-refresh         │ │
│  │    Schedule: Weekly (Wed 9AM)  │ │
│  │    Type: Retrieval             │ │
│  │    [View Schedule]             │ │
│  └────────────────────────────────┘ │
│                                      │
│  ┌────────────────────────────────┐ │
│  │ 📆 ranking-model-v2            │ │
│  │    Schedule: Once              │ │
│  │    Type: Ranking               │ │
│  │    [View Schedule]             │ │
│  └────────────────────────────────┘ │
│                                      │
└─────────────────────────────────────┘
```

### Historical vs Future Distinction

| Time Period | Visual Treatment | Data Source |
|-------------|------------------|-------------|
| **Past (completed)** | Solid colors, slightly faded | `TrainingRun` with `completed_at` |
| **Past (failed)** | Red tint or strikethrough | `TrainingRun` with `status='failed'` |
| **Today** | Blue border highlight | Current date |
| **Future** | Solid colors, full opacity | `TrainingSchedule` projected dates |

### Month Labels

- Display abbreviated month names (Nov, Dec, Jan, etc.)
- Position at the start of each month
- Only show months that have at least one visible week

### Data Calculation

For scheduled (recurring) training:

```python
def calculate_scheduled_dates(schedule, start_date, end_date):
    """
    Calculate all dates when a TrainingSchedule will run.

    schedule_type: 'once' | 'daily' | 'weekly'
    """
    dates = []

    if schedule.schedule_type == 'once':
        if start_date <= schedule.scheduled_datetime.date() <= end_date:
            dates.append(schedule.scheduled_datetime.date())

    elif schedule.schedule_type == 'daily':
        current = max(start_date, schedule.created_at.date())
        while current <= end_date:
            dates.append(current)
            current += timedelta(days=1)

    elif schedule.schedule_type == 'weekly':
        # schedule.schedule_day_of_week: 0=Monday, 6=Sunday
        current = max(start_date, schedule.created_at.date())
        while current <= end_date:
            if current.weekday() == schedule.schedule_day_of_week:
                dates.append(current)
            current += timedelta(days=1)

    return dates
```

### CSS Implementation

```css
/* Training Schedule Grid Container */
.training-schedule-grid {
    padding: 16px;
    background: white;
    border-radius: 8px;
    border: 1px solid #e5e7eb;
    margin-bottom: 20px;
}

.training-schedule-grid-title {
    font-size: 14px;
    font-weight: 600;
    color: #374151;
    margin-bottom: 12px;
}

/* Grid Layout */
.schedule-grid-container {
    display: flex;
    gap: 4px;
}

.schedule-grid-days {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding-top: 20px; /* Align with month labels */
}

.schedule-grid-day-label {
    width: 16px;
    height: 12px;
    font-size: 10px;
    color: #9ca3af;
    line-height: 12px;
}

.schedule-grid-weeks {
    display: flex;
    flex-direction: column;
}

.schedule-grid-months {
    display: flex;
    height: 16px;
    font-size: 10px;
    color: #9ca3af;
    margin-bottom: 4px;
}

.schedule-grid-cells {
    display: flex;
    gap: 2px;
}

.schedule-grid-column {
    display: flex;
    flex-direction: column;
    gap: 2px;
}

/* Individual Cells */
.schedule-grid-cell {
    width: 12px;
    height: 12px;
    border-radius: 2px;
    cursor: pointer;
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 8px;
    font-weight: 600;
    color: white;
    transition: transform 0.1s ease;
}

.schedule-grid-cell:hover {
    transform: scale(1.2);
    z-index: 10;
}

/* Cell Colors */
.schedule-grid-cell.empty {
    background-color: #ebedf0;
}

.schedule-grid-cell.level-1 {
    background-color: #9be9a8;
    color: #166534;
}

.schedule-grid-cell.level-2 {
    background-color: #40c463;
    color: white;
}

.schedule-grid-cell.level-3 {
    background-color: #30a14e;
    color: white;
}

.schedule-grid-cell.level-4 {
    background-color: #216e39;
    color: white;
}

/* Today Marker */
.schedule-grid-cell.today {
    outline: 2px solid #2563eb;
    outline-offset: 1px;
}

/* Historical (past) cells - slightly faded */
.schedule-grid-cell.past {
    opacity: 0.7;
}

/* Failed runs - red tint */
.schedule-grid-cell.has-failed {
    background: linear-gradient(135deg, currentColor 50%, #ef4444 50%);
}

/* Legend */
.schedule-grid-legend {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 12px;
    font-size: 11px;
    color: #6b7280;
}

.schedule-grid-legend-item {
    display: flex;
    align-items: center;
    gap: 4px;
}

.schedule-grid-legend-cell {
    width: 12px;
    height: 12px;
    border-radius: 2px;
}
```

### JavaScript Implementation

```javascript
const TrainingScheduleGrid = (function() {
    const WEEKS_PAST = 10;
    const WEEKS_FUTURE = 30;
    const DAYS = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

    let scheduleData = {};  // { 'YYYY-MM-DD': [{ name, type, scheduleId }] }
    let historicalData = {}; // { 'YYYY-MM-DD': [{ runId, name, status }] }

    function init() {
        loadScheduleData();
        renderGrid();
    }

    async function loadScheduleData() {
        const response = await fetch('/api/training-schedules/calendar/');
        const data = await response.json();
        scheduleData = data.scheduled;
        historicalData = data.historical;
        renderGrid();
    }

    function renderGrid() {
        const container = document.getElementById('trainingScheduleGrid');
        if (!container) return;

        const today = new Date();
        const startDate = new Date(today);
        startDate.setDate(startDate.getDate() - (WEEKS_PAST * 7));

        // Align to Monday
        const dayOfWeek = startDate.getDay();
        const daysToMonday = dayOfWeek === 0 ? 6 : dayOfWeek - 1;
        startDate.setDate(startDate.getDate() - daysToMonday);

        let html = `
            <div class="schedule-grid-container">
                <div class="schedule-grid-days">
                    ${DAYS.map(d => `<div class="schedule-grid-day-label">${d}</div>`).join('')}
                </div>
                <div class="schedule-grid-weeks">
                    <div class="schedule-grid-months" id="scheduleGridMonths"></div>
                    <div class="schedule-grid-cells" id="scheduleGridCells"></div>
                </div>
            </div>
            <div class="schedule-grid-legend">
                <span>Less</span>
                <div class="schedule-grid-legend-cell empty"></div>
                <div class="schedule-grid-legend-cell level-1"></div>
                <div class="schedule-grid-legend-cell level-2"></div>
                <div class="schedule-grid-legend-cell level-3"></div>
                <div class="schedule-grid-legend-cell level-4"></div>
                <span>More</span>
            </div>
        `;

        container.innerHTML = html;

        renderCells(startDate, today);
        renderMonthLabels(startDate);
    }

    function renderCells(startDate, today) {
        const cellsContainer = document.getElementById('scheduleGridCells');
        const totalWeeks = WEEKS_PAST + WEEKS_FUTURE;

        let html = '';
        let currentDate = new Date(startDate);

        for (let week = 0; week < totalWeeks; week++) {
            html += '<div class="schedule-grid-column">';

            for (let day = 0; day < 7; day++) {
                const dateStr = formatDate(currentDate);
                const isPast = currentDate < today;
                const isToday = formatDate(currentDate) === formatDate(today);

                const scheduled = scheduleData[dateStr] || [];
                const historical = historicalData[dateStr] || [];
                const count = isPast ? historical.length : scheduled.length;
                const hasFailed = historical.some(r => r.status === 'failed');

                const levelClass = count === 0 ? 'empty' :
                                   count === 1 ? 'level-1' :
                                   count === 2 ? 'level-2' :
                                   count === 3 ? 'level-3' : 'level-4';

                const classes = [
                    'schedule-grid-cell',
                    levelClass,
                    isPast ? 'past' : '',
                    isToday ? 'today' : '',
                    hasFailed ? 'has-failed' : ''
                ].filter(Boolean).join(' ');

                const displayCount = count > 0 ? (count > 9 ? '9+' : count) : '';

                html += `
                    <div class="${classes}"
                         data-date="${dateStr}"
                         onclick="TrainingScheduleGrid.showDayDetails('${dateStr}')"
                         title="${formatDateLong(currentDate)}">
                        ${displayCount}
                    </div>
                `;

                currentDate.setDate(currentDate.getDate() + 1);
            }

            html += '</div>';
        }

        cellsContainer.innerHTML = html;
    }

    function showDayDetails(dateStr) {
        const scheduled = scheduleData[dateStr] || [];
        const historical = historicalData[dateStr] || [];
        const items = [...historical, ...scheduled];

        if (items.length === 0) return;

        // Show popover with training details
        showPopover(dateStr, items);
    }

    function showPopover(dateStr, items) {
        // Implementation for popover display
        // ...
    }

    function formatDate(date) {
        return date.toISOString().split('T')[0];
    }

    function formatDateLong(date) {
        return date.toLocaleDateString('en-US', {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });
    }

    return {
        init,
        refresh: loadScheduleData,
        showDayDetails
    };
})();
```

### API Endpoint

```
GET /api/training-schedules/calendar/
```

**Response:**
```json
{
    "scheduled": {
        "2026-01-29": [
            {
                "scheduleId": 5,
                "name": "recs-weekly-refresh",
                "type": "retrieval",
                "scheduleType": "weekly"
            }
        ],
        "2026-02-05": [
            {
                "scheduleId": 5,
                "name": "recs-weekly-refresh",
                "type": "retrieval",
                "scheduleType": "weekly"
            }
        ]
    },
    "historical": {
        "2026-01-15": [
            {
                "runId": 42,
                "name": "TR-42",
                "status": "completed",
                "type": "retrieval"
            }
        ],
        "2026-01-19": [
            {
                "runId": 47,
                "name": "TR-47",
                "status": "completed",
                "type": "retrieval"
            }
        ]
    }
}
```

---

## Section 3: Filter Bar

### Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  [All Types ▼]   [All Status ▼]   [Sort: Latest ▼]   🔍 Search models...    │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Filter Options

#### Model Type Filter
| Option | Filter Condition |
|--------|-----------------|
| All Types | No filter |
| Retrieval | `model_type = 'retrieval'` |
| Ranking | `model_type = 'ranking'` |
| Hybrid | `model_type = 'hybrid'` |

#### Status Filter
| Option | Filter Condition |
|--------|-----------------|
| All Status | No filter |
| Blessed | `is_blessed = True` |
| Not Blessed | `is_blessed = False` |
| Deployed | `is_deployed = True` |
| Idle | `is_blessed = True AND is_deployed = False` |

#### Sort Options
| Option | Sort Order |
|--------|-----------|
| Latest | `registered_at DESC` |
| Oldest | `registered_at ASC` |
| Best Metrics | `recall_at_100 DESC` (retrieval) or `rmse ASC` (ranking) |
| Name A-Z | `vertex_model_name ASC` |

#### Search
- Search by model name (`vertex_model_name`)
- Debounced input (300ms delay)
- Case-insensitive partial match

---

## Section 4: Registered Models Table

### Table Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ # │ Model Name        │ Type      │ Ver │ Metrics   │ Status   │ Registered │ Actions │
├───┼───────────────────┼───────────┼─────┼───────────┼──────────┼────────────┼─────────┤
│ 1 │ recs-prod-v3      │ Retrieval │ 3   │ R@100: .82│ DEPLOYED │ 21 Jan     │ [▼]     │
│ 2 │ recs-prod-v2      │ Retrieval │ 2   │ R@100: .80│ IDLE     │ 15 Jan     │ [▼]     │
│ 3 │ ranking-q4        │ Ranking   │ 1   │ RMSE: .45 │ DEPLOYED │ 10 Jan     │ [▼]     │
│ 4 │ test_v1-v2        │ Retrieval │ 2   │ —         │ BLESSED  │ 19 Jan     │ [▼]     │
│ 5 │ hybrid-experiment │ Hybrid    │ 1   │ R@100: .78│ NOT BLSD │ 05 Jan     │ [▼]     │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Column Definitions

| Column | Width | Content |
|--------|-------|---------|
| **#** | 40px | Row number |
| **Model Name** | 180px | `vertex_model_name` - clickable to open details |
| **Type** | 90px | Model type badge (Retrieval/Ranking/Hybrid) |
| **Ver** | 50px | `vertex_model_version` |
| **Metrics** | 100px | Primary metric (R@100 for retrieval, RMSE for ranking) |
| **Status** | 90px | Status badge (see below) |
| **Registered** | 90px | `registered_at` formatted as "DD Mon" |
| **Actions** | 60px | Dropdown menu |

### Status Badges

| Status | Badge Color | Condition |
|--------|-------------|-----------|
| **DEPLOYED** | Green (`#22c55e`) | `is_deployed = True` |
| **IDLE** | Blue (`#3b82f6`) | `is_blessed = True AND is_deployed = False` |
| **BLESSED** | Teal (`#14b8a6`) | `is_blessed = True` (synonym for IDLE) |
| **NOT BLESSED** | Orange (`#f97316`) | `is_blessed = False` |
| **PENDING** | Gray (`#9ca3af`) | `is_blessed IS NULL` (evaluation in progress) |

### Actions Dropdown

```
┌─────────────────────┐
│ 👁 View Details     │
│ 📊 Compare          │
│ ─────────────────── │
│ 🚀 Deploy           │  ← Only for blessed, not deployed
│ ⏹ Undeploy         │  ← Only for deployed
│ ─────────────────── │
│ 📋 Copy Artifact URL│
│ 🔗 Open in Vertex   │
└─────────────────────┘
```

### Row Click Behavior

Clicking a row (except actions) opens the Model View Modal.

### Empty State

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                               │
│                           📦                                                  │
│                                                                               │
│                    No models registered yet                                   │
│                                                                               │
│     Complete a training run with the Pusher component enabled               │
│     to register models in Vertex AI Model Registry.                          │
│                                                                               │
│                    [Start Training Run]                                       │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Section 5: Model View Modal

### Overview

Extend the existing `ExpViewModal` to support a "model" mode, or create a dedicated `ModelViewModal` with similar structure.

### Modal Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  📦 recs-prod-v3                                    [DEPLOYED] [×]  │    │
│  │  Version 3 • Registered 21 Jan 2026 • Retrieval                     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  [Overview] [Versions] [Artifacts] [Deployment] [Lineage]                    │
│  ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│  ┌─ Tab Content ────────────────────────────────────────────────────────┐   │
│  │                                                                       │   │
│  │  (Content varies by tab - see below)                                 │   │
│  │                                                                       │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ─────────────────────────────────────────────────────────────────────────   │
│  [Deploy to Endpoint]  [Compare Versions]           [Open in Vertex AI]     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Tab: Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  PERFORMANCE METRICS                                                         │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐               │
│  │ R@5        │ │ R@10       │ │ R@50       │ │ R@100      │               │
│  │ 0.234      │ │ 0.412      │ │ 0.687      │ │ 0.823      │               │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘               │
│                                                                              │
│  EVALUATION RESULTS                                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ ✅ Model Blessed                                                      │   │
│  │ Threshold: R@100 ≥ 0.70  │  Achieved: 0.823  │  Margin: +0.123       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  CONFIGURATION SUMMARY                                                       │
│  ┌────────────────────────┐ ┌────────────────────────┐                      │
│  │ Dataset                │ │ Feature Config         │                      │
│  │ Q4 Transactions 2025   │ │ cfg-042 (v3)          │                      │
│  │ 2.4M rows • 3 tables   │ │ 128 dims • 12 features│                      │
│  └────────────────────────┘ └────────────────────────┘                      │
│  ┌────────────────────────┐ ┌────────────────────────┐                      │
│  │ Model Config           │ │ Training Params        │                      │
│  │ Standard Retrieval     │ │ 20 epochs • LR: 0.1   │                      │
│  │ 3-layer towers         │ │ Batch: 8192 • GPU: T4 │                      │
│  └────────────────────────┘ └────────────────────────┘                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Tab: Versions

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  VERSION HISTORY                                              [Compare]     │
│                                                                              │
│  │ Ver │ Registered     │ R@100  │ Status   │ Training Run │ Actions      │ │
│  ├─────┼────────────────┼────────┼──────────┼──────────────┼──────────────┤ │
│  │ 3   │ 21 Jan 2026    │ 0.823  │ DEPLOYED │ TR-47        │ [View]       │ │
│  │ 2   │ 15 Jan 2026    │ 0.801  │ IDLE     │ TR-42        │ [View] [Del] │ │
│  │ 1   │ 05 Jan 2026    │ 0.756  │ ARCHIVED │ TR-35        │ [View] [Del] │ │
│                                                                              │
│  ─────────────────────────────────────────────────────────────────────────   │
│  Version Comparison (v2 → v3)                                                │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ Metric      │ v2        │ v3        │ Change                          │ │
│  │ R@100       │ 0.801     │ 0.823     │ +0.022 ▲                        │ │
│  │ R@50        │ 0.654     │ 0.687     │ +0.033 ▲                        │ │
│  │ Loss        │ 0.35      │ 0.31      │ -0.04  ▼                        │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Tab: Artifacts

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  MODEL ARTIFACTS                                                             │
│                                                                              │
│  Vertex AI Model Registry                                                    │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ Resource Name:                                                        │   │
│  │ projects/my-project/locations/europe-central2/models/5241525861236.. │   │
│  │                                                    [Copy] [Open]      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  Cloud Storage Artifacts                                                     │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 📁 Model Artifact                                                     │   │
│  │ gs://b2b-recs-training-artifacts/tr-47-20260121/pushed_model/...     │   │
│  │                                                    [Copy] [Browse]    │   │
│  ├──────────────────────────────────────────────────────────────────────┤   │
│  │ 📁 Transform Graph                                                    │   │
│  │ gs://b2b-recs-training-artifacts/tr-47-20260121/transform/...        │   │
│  │                                                    [Copy] [Browse]    │   │
│  ├──────────────────────────────────────────────────────────────────────┤   │
│  │ 📄 Training Metrics                                                   │   │
│  │ gs://b2b-recs-training-artifacts/tr-47-20260121/metrics.json         │   │
│  │                                                    [Copy] [Download]  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  Container Image                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ us-docker.pkg.dev/vertex-ai/prediction/tf2-cpu.2-15:latest           │   │
│  │                                                    [Copy]             │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Tab: Deployment

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  DEPLOYMENT STATUS                                                           │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 🚀 Currently Deployed                                                 │   │
│  │                                                                        │   │
│  │ Endpoint: projects/my-project/locations/europe-central2/endpoints/123│   │
│  │ Deployed: 21 Jan 2026, 15:30                                         │   │
│  │ Machine Type: n1-standard-4                                          │   │
│  │ Min Replicas: 1  │  Max Replicas: 3                                  │   │
│  │                                                                        │   │
│  │ [Undeploy]  [View Endpoint]                                          │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  DEPLOYMENT HISTORY                                                          │
│  │ Date              │ Action    │ Endpoint        │ By          │         │
│  ├───────────────────┼───────────┼─────────────────┼─────────────┤         │
│  │ 21 Jan 2026 15:30 │ Deployed  │ endpoint-prod   │ user@email  │         │
│  │ 15 Jan 2026 10:00 │ Undeployed│ endpoint-prod   │ user@email  │         │
│  │ 15 Jan 2026 09:45 │ Deployed  │ endpoint-prod   │ system      │         │
│                                                                              │
│  ─────────────────────────────────────────────────────────────────────────   │
│  PREDICTION TEST (Coming Soon)                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ Test the model with sample input                                      │   │
│  │ [Feature disabled - endpoint deployment required]                     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Tab: Lineage

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  MODEL LINEAGE                                                               │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                                                                      │    │
│  │   ┌─────────────┐      ┌─────────────┐      ┌─────────────┐        │    │
│  │   │ Quick Test  │ ───► │ Training    │ ───► │ Model       │        │    │
│  │   │ Exp #45     │      │ TR-47       │      │ recs-v3     │        │    │
│  │   │ R@100: 0.81 │      │ R@100: 0.82 │      │ DEPLOYED    │        │    │
│  │   └─────────────┘      └─────────────┘      └─────────────┘        │    │
│  │         │                    │                    │                 │    │
│  │         │                    │                    │                 │    │
│  │         ▼                    ▼                    ▼                 │    │
│  │   ┌─────────────┐      ┌─────────────┐      ┌─────────────┐        │    │
│  │   │ Dataset     │      │ Feature Cfg │      │ Model Cfg   │        │    │
│  │   │ Q4 Trans    │      │ cfg-042     │      │ Standard    │        │    │
│  │   │ 2.4M rows   │      │ 128 dims    │      │ 3-layer     │        │    │
│  │   └─────────────┘      └─────────────┘      └─────────────┘        │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  RELATED TRAINING RUNS                                                       │
│  │ Run    │ Date       │ Status    │ R@100  │ Blessed │                    │
│  ├────────┼────────────┼───────────┼────────┼─────────┤                    │
│  │ TR-47  │ 21 Jan     │ Completed │ 0.823  │ ✅      │  ← This model      │
│  │ TR-42  │ 15 Jan     │ Completed │ 0.801  │ ✅      │                    │
│  │ TR-35  │ 05 Jan     │ Completed │ 0.756  │ ✅      │                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## API Endpoints

### Models Registry Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/models/` | List all registered models |
| `GET` | `/api/models/{id}/` | Get model details |
| `GET` | `/api/models/{id}/versions/` | Get version history |
| `POST` | `/api/models/{id}/deploy/` | Deploy model to endpoint |
| `POST` | `/api/models/{id}/undeploy/` | Remove from endpoint |
| `GET` | `/api/models/{id}/lineage/` | Get model lineage |

### Training Schedule Calendar Endpoint

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/training-schedules/calendar/` | Get scheduled/historical runs for grid |

**Query Parameters:**
- `weeks_past`: Number of past weeks (default: 10)
- `weeks_future`: Number of future weeks (default: 30)

---

## Data Models

### Existing Fields (TrainingRun)

The following fields already exist in `TrainingRun` and will be used:

```python
# Model Registry Fields
vertex_model_name = models.CharField(max_length=500)
vertex_model_version = models.CharField(max_length=100)
vertex_model_resource_name = models.CharField(max_length=500)
registered_at = models.DateTimeField(null=True)

# Evaluation Fields
is_blessed = models.BooleanField(null=True)
evaluation_results = models.JSONField(default=dict)

# Deployment Fields
is_deployed = models.BooleanField(default=False)
deployed_at = models.DateTimeField(null=True)
endpoint_resource_name = models.CharField(max_length=500)
```

### Suggested New Fields

Consider adding these fields for enhanced functionality:

```python
# Model metadata
model_alias = models.CharField(
    max_length=100,
    blank=True,
    help_text="User-defined alias (e.g., 'prod', 'staging', 'latest')"
)

model_description = models.TextField(
    blank=True,
    help_text="User-provided description of this model version"
)

model_tags = models.JSONField(
    default=list,
    help_text="Searchable tags for categorization"
)

# Artifact metadata
artifact_size_bytes = models.BigIntegerField(
    null=True,
    help_text="Size of the model artifact in bytes"
)

serving_container_image = models.CharField(
    max_length=500,
    blank=True,
    help_text="Container image used for serving"
)

# Deployment tracking
deployment_history = models.JSONField(
    default=list,
    help_text="History of deployment/undeployment actions"
)
```

---

## Implementation Phases

### Phase 1: MVP (Week 1-2)
- [ ] KPI Summary Row
- [ ] Basic models table with sorting
- [ ] Filter bar (type, status, search)
- [ ] Row click opens existing ExpViewModal in training_run mode

### Phase 2: Schedule Grid (Week 2-3)
- [ ] Training Schedule Grid component
- [ ] Calendar API endpoint
- [ ] Cell click popover
- [ ] Historical vs scheduled distinction

### Phase 3: Model View Modal (Week 3-4)
- [ ] Overview tab with metrics
- [ ] Versions tab with comparison
- [ ] Artifacts tab with links
- [ ] Lineage tab with DAG

### Phase 4: Deployment Integration (Week 4-5)
- [ ] Deploy button functionality
- [ ] Undeploy functionality
- [ ] Deployment tab in modal
- [ ] Deployment history tracking

### Phase 5: Advanced Features (Future)
- [ ] Version comparison modal
- [ ] Prediction playground
- [ ] Model monitoring dashboard
- [ ] A/B testing support

---

## CSS Files

New styles should be added to:
- `static/css/models_registry.css` - Main component styles
- `static/css/schedule_grid.css` - GitHub-style grid styles

Or integrated into existing:
- `static/css/training_cards.css` - If reusing card patterns

---

## JavaScript Files

New modules to create:
- `static/js/models_registry.js` - Main registry component
- `static/js/training_schedule_grid.js` - GitHub-style grid component

---

## Dependencies

No new external dependencies required. Uses:
- Chart.js (existing) - for metric visualizations
- D3.js (existing) - optional for lineage DAG
- Font Awesome (existing) - for icons

---

## Related Documents

- `docs/phase_training.md` - Training domain specifications
- `ml_platform/training/models.py` - TrainingRun and TrainingSchedule models
- `static/js/exp_view_modal.js` - Reusable view modal component

---

## Automatic Model Registration

### Overview

When a TFX training pipeline completes successfully, the model is automatically registered in Vertex AI Model Registry. This happens in the `_register_to_model_registry()` method in `ml_platform/training/services.py`.

### Registration Flow

1. **Pipeline Completion**: When the pipeline status becomes `COMPLETED`, the `_extract_results()` method is called
2. **Metrics Extraction**: Training metrics and blessing status are extracted from GCS artifacts
3. **Model Registration**: `_register_to_model_registry()` uploads the model to Vertex AI Model Registry using the `aiplatform.Model.upload()` API

### Serving Container Configuration

The model is registered with a Vertex AI pre-built serving container:

```python
serving_container_image_uri="us-docker.pkg.dev/vertex-ai/prediction/tf2-cpu.2-12:latest"
```

This container is used for:
- Automatic registration after pipeline completion
- Force-push operations for not-blessed models
- Deployment to Vertex AI Endpoints

**Note**: All registration methods use the same Vertex AI pre-built container to ensure consistency across the platform.

### Model Artifact Location

The registered model's artifacts are stored at:
```
gs://b2b-recs-training-artifacts/{run_id}/pushed_model
```

Where `{run_id}` follows the format `tr-{training_run_id}-{timestamp}`.

### Error Handling

Registration failures are logged but do not fail the training run. If registration fails:
- The training run status remains `COMPLETED`
- The `vertex_model_resource_name` field remains empty
- Users can manually trigger registration via the "Register Model" button

---

## Bug Fixes: Model Registration Issues (2026-01-24)

### Problem Summary

Training runs #17 and #18 completed successfully but were never registered to Vertex AI Model Registry. Investigation revealed multiple issues in the registration pipeline.

### Bug #1: Invalid Serving Container Image

**Symptom**: Registration failed silently during automatic post-training registration.

**Root Cause**: The original code in `_register_to_model_registry()` used an invalid container image path. The code referenced `self.ml_model.slug` which doesn't exist on the `ModelEndpoint` model (it has `name` instead).

**Error**:
```
AttributeError: 'ModelEndpoint' object has no attribute 'slug'
```

**Fix**: Changed `self.ml_model.slug` to `self.ml_model.name` in two locations:
- Line 746: Model display name construction
- Line 1526: Cloud Run service name construction

**Files Modified**: `ml_platform/training/services.py`

### Bug #2: Invalid GCP Label Values

**Symptom**: Registration failed with `400 INVALID_ARGUMENT` error about labels.

**Root Cause**: GCP labels must only contain lowercase letters, numbers, dashes, and underscores. Values like `model_type` or boolean fields were being passed without sanitization.

**Error**:
```
google.api_core.exceptions.InvalidArgument: 400 List of found errors:
1.Field: model.labels; Message: Label keys and values can only contain
lowercase letters, numbers, dashes and underscores...
```

**Fix**: Added a `sanitize_label()` helper function that:
- Converts values to lowercase
- Replaces invalid characters with underscores
- Ensures values start with a letter/number
- Truncates to 63 characters (GCP limit)

**Files Modified**: `ml_platform/training/services.py`

### Bug #3: Incorrect Model Artifact Path

**Symptom**: Registration failed with `400 FailedPrecondition` error about missing `saved_model.pb`.

**Root Cause**: TFX Pusher creates a versioned subdirectory structure:
```
pushed_model/
  1769254066/          <- version number directory
    saved_model.pb
    variables/
    assets/
```

The code pointed to `pushed_model/` but Vertex AI requires the path to the directory containing `saved_model.pb` directly.

**Error**:
```
google.api_core.exceptions.FailedPrecondition: 400 Model directory
gs://...pushed_model is expected to contain exactly one of:
[saved_model.pb, saved_model.pbtxt]
```

**Fix**: Added logic to detect and use the versioned subdirectory:
```python
# List subdirectories to find versioned model directory
iterator = bucket.list_blobs(prefix=prefix, delimiter='/')
_ = list(iterator)  # Consume iterator to populate prefixes
prefixes = list(iterator.prefixes)

if prefixes:
    version_dir = prefixes[0].rstrip('/')
    artifact_uri = f"gs://{bucket_name}/{version_dir}"
```

**Files Modified**: `ml_platform/training/services.py`

### Bug #4: No Retry Mechanism for Failed Registrations

**Symptom**: Completed training runs with failed registration had no way to retry.

**Root Cause**: The existing "Push to Registry" button only worked for `not_blessed` runs (calling `/push/` endpoint). There was no API endpoint or UI for retrying registration on `completed` runs.

**Fix**: Added new registration retry capability:

1. **New Service Method** (`services.py`):
   ```python
   def register_model(self, training_run: TrainingRun) -> TrainingRun:
       """Register or re-register a completed training run's model."""
   ```

2. **New API Endpoint** (`api.py`):
   ```python
   POST /api/training-runs/<id>/register/
   ```

3. **New URL Pattern** (`urls.py`):
   ```python
   path('api/training-runs/<int:training_run_id>/register/',
        api.training_run_register, name='training_run_register')
   ```

4. **Updated Frontend** (`exp_view_modal.js`):
   - Added "Register Model" button for completed runs without registration
   - Uses styled confirmation modal (not browser native)
   - Shows toast notifications for success/error

**Files Modified**:
- `ml_platform/training/services.py`
- `ml_platform/training/api.py`
- `ml_platform/training/urls.py`
- `static/js/exp_view_modal.js`
- `static/js/training_cards.js` (exported `showConfirmModal`, `showToast`)
- `static/css/modals.css` (z-index fix for confirmation modal)

### Bug #5: Incorrect Model Display Names

**Symptom**: Registered models had names like `test_v1-v11` instead of the training run's name like `chern_rank_v1`.

**Root Cause**: The model name was constructed from `{model_endpoint.name}-v{run_number}` instead of using the training run's `name` field.

**Fix**: Changed model name logic to prioritize training run name:
```python
# Before
model_name = f"{self.ml_model.name}-v{training_run.run_number}"

# After
model_name = training_run.name or f"{self.ml_model.name}-v{training_run.run_number}"
```

Also updated existing registered models in both database and Vertex AI:
- Run #11: `test_v1-v11` → `chern_rank_v1`
- Run #10: `test_v1-v10` → `chern_retriv_v5`
- Run #2: `test_v1-v2` → `chern_retriv_v2`

**Files Modified**: `ml_platform/training/services.py`

### How Registration Works Now

#### Automatic Registration (Post-Training)

1. Training pipeline completes successfully
2. `_extract_results()` extracts metrics and blessing status from GCS
3. `_register_to_model_registry()` is called **regardless of blessing status**
4. Model is uploaded to Vertex AI Model Registry with:
   - Display name: `{training_run.name}` (or fallback to `{endpoint.name}-v{run_number}`)
   - Artifact URI: Versioned model directory from GCS
   - Sanitized labels for tracking
5. Training run record updated with `vertex_model_resource_name` and `vertex_model_name`

#### Manual Registration (Retry)

For completed runs where automatic registration failed:

1. User opens Training Run in View Modal
2. Registry & Deployment section shows "Not Registered" with "Register Model" button
3. User clicks button → styled confirmation modal appears
4. On confirm, `POST /api/training-runs/{id}/register/` is called
5. Service validates run is `COMPLETED` and not already registered
6. `_register_to_model_registry()` performs the upload
7. Success toast notification shown, modal refreshes

#### Key Points

- **All completed models are registered**, regardless of blessing status (`is_blessed` True/False)
- Blessing only affects the `status` field (`completed` vs `not_blessed`) and UI display
- Registration failures are non-fatal and logged as warnings
- The "Register Model" button is specifically for retry scenarios
- Model names come from the Model Name field in the wizard

---

## Implementation Status

**Implemented**: 2026-01-22

### Summary

All MVP features (Phases 1-4) have been implemented. The Models Registry chapter is now fully functional on the Training page.

### Files Created

| File | Lines | Purpose |
|------|-------|---------|
| `static/js/models_registry.js` | ~600 | Main module: table, filters, actions, KPI |
| `static/js/schedule_calendar.js` | ~350 | GitHub-style calendar component |
| `static/css/models_registry.css` | ~400 | KPI, table, filter bar, status badges |
| `static/css/schedule_calendar.css` | ~250 | Calendar grid, tooltip, popover styles |

### Files Modified

| File | Changes |
|------|---------|
| `ml_platform/training/api.py` | Added 7 API endpoint functions for Models Registry |
| `ml_platform/training/urls.py` | Added 7 URL routes |
| `ml_platform/training/services.py` | Added `undeploy_model()` method |
| `static/js/exp_view_modal.js` | Added 'model' mode with new tabs (Versions, Artifacts, Deployment, Lineage) |
| `templates/includes/_exp_view_modal.html` | Added new tab buttons and content areas |
| `static/css/exp_view_modal.css` | Added model-specific styles |
| `templates/ml_platform/model_training.html` | Replaced placeholder with full implementation |

### API Endpoints Implemented

| Method | Endpoint | Status |
|--------|----------|--------|
| `GET` | `/api/models/` | ✅ Implemented |
| `GET` | `/api/models/{id}/` | ✅ Implemented |
| `GET` | `/api/models/{id}/versions/` | ✅ Implemented |
| `POST` | `/api/models/{id}/deploy/` | ✅ Implemented |
| `POST` | `/api/models/{id}/undeploy/` | ✅ Implemented |
| `GET` | `/api/models/{id}/lineage/` | ✅ Implemented |
| `GET` | `/api/training-schedules/calendar/` | ✅ Implemented |

### Features Implemented

#### KPI Summary Row
- ✅ Total Models count
- ✅ Blessed count
- ✅ Deployed count
- ✅ Idle count (blessed but not deployed)
- ✅ Latest registration date

#### Schedule Calendar Grid
- ✅ GitHub-style contribution graph (40 weeks: 10 past + 30 future)
- ✅ Color levels based on activity (0-4)
- ✅ Today marker (blue border)
- ✅ Tooltip on hover with date and model names
- ✅ Click popover with detailed run/schedule info
- ✅ Historical data from TrainingRun completions
- ✅ Future projections from active TrainingSchedule records

#### Filter Bar
- ✅ Model Type filter (All, Retrieval, Ranking, Multitask)
- ✅ Status filter (All, Blessed, Not Blessed, Deployed, Idle)
- ✅ Sort options (Latest, Oldest, Best Metrics, Name A-Z)
- ✅ Debounced search (300ms)
- ✅ Refresh button

#### Models Table
- ✅ Row number, Model Name, Type badge, Version, Metrics, Status badge, Registered date
- ✅ Clickable rows to open Model View Modal
- ✅ Actions dropdown (View Details, Version History, Deploy, Undeploy, Copy Artifact URL, Open in Vertex AI)
- ✅ Pagination

#### Model View Modal (ExpViewModal in 'model' mode)
- ✅ Overview tab with metrics and configuration summary
- ✅ Versions tab with version history table
- ✅ Artifacts tab with GCS paths and copy buttons
- ✅ Deployment tab with status, endpoint info, deploy/undeploy buttons
- ✅ Lineage tab with DAG visualization

### Architecture Decisions Implemented

| Decision | Approach |
|----------|----------|
| **Module Structure** | New `models_registry.js` separate from training cards |
| **Data Source** | Query `TrainingRun` where `vertex_model_resource_name IS NOT NULL` |
| **Modal Strategy** | Extended `ExpViewModal` with `'model'` mode |
| **Schedule Grid** | Standalone `schedule_calendar.js` component |
| **CSS Strategy** | New `models_registry.css` + `schedule_calendar.css` files |

### Verification Steps

1. **Backend Testing**:
   - Start dev server: `python manage.py runserver`
   - Test API endpoints:
     - `GET /api/models/` - returns registered models
     - `GET /api/models/?model_type=retrieval` - filters work
     - `GET /api/training-schedules/calendar/` - returns date mapping

2. **Frontend Testing**:
   - Load Training page (`/models/{id}/training/`)
   - Verify Models Registry chapter renders
   - KPI row shows correct counts
   - Calendar grid displays with correct colors
   - Filter dropdowns work
   - Table rows display models
   - Click row → Modal opens with correct tabs
   - Test Deploy/Undeploy actions

### Future Enhancements (Phase 5)

- [ ] Version comparison modal
- [ ] Prediction playground
- [ ] Model monitoring dashboard
- [ ] A/B testing support
