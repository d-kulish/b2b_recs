# Starting Page (System Dashboard)

## Overview

The starting page (`system_dashboard.html`) is the landing page users see when accessing the Recs Studio platform. It provides an overview of the system and quick access to models.

**URL:** `/` (root)
**View:** `ml_platform.views.system_dashboard`
**Template:** `templates/ml_platform/system_dashboard.html`

---

## Design Principles

The starting page is intentionally **different** from model pages to provide clear visual distinction:

| Aspect | Starting Page | Model Pages |
|--------|---------------|-------------|
| Background | Pure white (`#ffffff`) | Dotted pattern |
| Header | No header bar | Full header with KPIs |
| Navigation | None | Horizontal pill tabs |
| Layout | Collapsible chapters | Content containers |

---

## Page Structure

### Header Section

```
┌─────────────────────────────────────────────────────────────────┐
│  [Logo]          b2b-recs                        [User Icon]    │
│  Recs Studio     (project ID)                                   │
└─────────────────────────────────────────────────────────────────┘
```

**Components:**
- **Logo** - Positioned identically to model pages (70px height, "Recs Studio" text below)
- **Project ID** - Displayed next to logo, styled like model name (`text-5xl font-bold text-blue-900`)
- **User Profile Icon** - Far right, 44x44px circular icon

**Layout Classes:**
- Outer wrapper: `p-6 pb-0`
- Container: `max-w-[88rem] mx-auto`
- Header row: `px-6 py-3 flex items-center gap-6`

### Main Content

Three collapsible chapters displayed vertically:

1. **System Details** - Project configuration and infrastructure overview
2. **Your Models** - Manage ML models and endpoints
3. **Billing** - Usage tracking and subscription details

---

## Chapter Components

### Chapter Container Structure

```html
<div class="chapter-container open" data-chapter="[name]">
    <div class="chapter-header">
        <div class="chapter-title-wrapper">
            <div class="chapter-icon [type]">
                <i class="fas fa-[icon]"></i>
            </div>
            <div class="chapter-title-text">
                <span class="chapter-title">[Title]</span>
                <span class="chapter-subtitle">[Description]</span>
            </div>
        </div>
        <div class="chapter-toggle">
            <i class="fas fa-chevron-right"></i>
        </div>
    </div>
    <div class="chapter-content">
        <div class="chapter-content-inner">
            <!-- Chapter content here -->
        </div>
    </div>
</div>
```

### Chapter Styling

| Property | Value |
|----------|-------|
| Border | 2px solid #1f2937 |
| Border radius | 16px |
| Header padding | 24px 28px |
| Icon size | 48x48px |
| Icon border-radius | 12px |
| Title font-size | 24px |
| Title font-weight | 700 |
| Subtitle font-size | 14px |
| Subtitle color | #6b7280 |

### Chapter Icons

| Chapter | Icon | Background Gradient |
|---------|------|---------------------|
| System Details | `fa-server` | Blue (#3b82f6 → #60a5fa) |
| Your Models | `fa-cube` | Purple (#8b5cf6 → #a78bfa) |
| Billing | `fa-credit-card` | Orange (#f59e0b → #fbbf24) |

---

## Chapter 1: System Details

Displays project configuration information in a 2-column grid.

**Fields (static/hardcoded):**
- Project ID: `b2b-recs`
- Region: `europe-central2 (Warsaw)`

**Fields (dynamic from context):**
- Total Models: `{{ total_models }}`
- Active Endpoints: `{{ active_models }}`

---

## Chapter 2: Your Models

Lists all models with cards linking to their dashboards.

### Model Card Structure

Each model displays:
- Model name
- Description (truncated to 15 words)
- Status badge (active/draft/inactive/failed)
- Created date
- Last trained date (if applicable)
- Arrow indicator on hover

### Status Badge Colors

| Status | Background | Text Color |
|--------|------------|------------|
| Active | #d1fae5 | #065f46 |
| Draft | #f3f4f6 | #4b5563 |
| Inactive | #fef3c7 | #92400e |
| Failed | #fee2e2 | #991b1b |

### Empty State

When no models exist, displays:
- Large cube icon
- "No models created yet" text
- "Create Your First Model" button

---

## Chapter 3: Billing

Displays subscription and usage information.

**Fields (all hardcoded/demo data):**
- Current Plan: Pro (with gradient badge)
- Billing Period: Feb 1 - Feb 28, 2026
- Training Hours Used: 12.5 / 100 hrs
- API Requests: 47,250 / Unlimited
- Current Charges: $0.00 (green)

---

## JavaScript

Single function for chapter toggle:

```javascript
function toggleChapter(header) {
    const container = header.closest('.chapter-container');
    container.classList.toggle('open');
}
```

**Behavior:**
- Clicking chapter header toggles `open` class
- Chevron rotates 90° when open
- Content expands/collapses with CSS transition

---

## Context Variables

The view provides these context variables:

| Variable | Type | Description |
|----------|------|-------------|
| `models` | QuerySet | All ModelEndpoint objects |
| `total_models` | int | Count of all models |
| `active_models` | int | Count of models with status='active' |

---

## Dependencies

- **Tailwind CSS** 3.4.10 (CDN)
- **Font Awesome** 6.4.0 (CDN)

---

## Future Enhancements

- [ ] Dynamic project ID from settings/database
- [ ] Real billing data from subscription service
- [ ] User profile dropdown menu
- [ ] Quick actions in header
- [ ] Recent activity feed
