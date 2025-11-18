# B2B Recommendation System - SaaS Platform

A multi-tenant B2B SaaS platform for building, training, and deploying production-grade recommendation models.

## 📊 Project Stats

- **13** Database Models (including ETL models)
- **45+** Files Created (including schema_mapper.py, bigquery_manager.py)
- **11** HTML Templates (with responsive UI)
- **22** View Functions (including ETL & BigQuery APIs)
- **19** URL Patterns
- **100%** Authentication Coverage
- **~1,100** Lines of Code Added (Milestone 11.5)
- **Status**: Frontend Skeleton + Advanced 5-Step ETL Wizard + BigQuery Integration ✅

## Project Status

**Current Phase**: BigQuery Table Setup & Schema Management ✅ **COMPLETE**

**Date Completed**: November 18, 2025 (Milestone 11.5)

The client-facing web application is complete with advanced **5-step ETL wizard** featuring BigQuery table schema configuration with intelligent type mapping, load strategy configuration, table preview, column selection, historical backfill, schema selection for multi-schema databases, comprehensive connection management with full CRUD operations, cloud storage integration (GCS, S3, Azure Blob), robust connection testing, modern minimalistic UI design, and professional UX enhancements.

**Next Phase**: ETL Runner & Cloud Scheduler Integration (Milestone 12) - See `BQ_TABLE_SETUP.md` for detailed implementation plan.

### ✅ Completed Components

**Backend:**
- ✅ Django project structure with proper settings
- ✅ 13 database models (ModelEndpoint, ETL, DataSource, DataSourceTable, Pipeline, Experiments, etc.)
- ✅ Complete URL routing structure (system + model-level pages)
- ✅ Functional views with authentication and authorization
- ✅ API endpoints for AJAX operations (training, ETL, deployment, BigQuery)
- ✅ Admin interface for all models (searchable, filterable)
- ✅ Database migrations created and applied
- ✅ **ETL System**: Multi-source configuration, connection testing, manual triggers
- ✅ **Connection Management**: Reusable named connections with credential storage in GCP Secret Manager
- ✅ **Cloud Storage Integration**: GCS, AWS S3, Azure Blob Storage with storage-first architecture
- ✅ **Standalone Connections UI**: Independent connection CRUD with live status indicators
- ✅ **19 Data Source Types**: PostgreSQL, MySQL, Oracle, SQL Server, BigQuery, Snowflake, Firestore, MongoDB, GCS, S3, Azure Blob, and more
- ✅ **BigQuery Integration**: Intelligent type mapping (70+ types), schema validation, table creation with partitioning/clustering
- ✅ **Schema Mapper**: Auto-detection of dates, timestamps, booleans in VARCHAR fields with confidence scoring
- ✅ **BigQuery Manager**: Dataset creation, table creation, schema validation, performance optimization

**Frontend:**
- ✅ Responsive UI using Tailwind CSS
- ✅ Base templates with navigation (system + model-specific)
- ✅ System Dashboard (landing page with stats and models list)
- ✅ Model/Endpoint creation flow
- ✅ Model Dashboard (status cards, recent runs, quick actions)
- ✅ Login/logout functionality
- ✅ **5-Step ETL Wizard**: Connection → Schema/Table → Load Strategy → BigQuery Setup → Schedule
- ✅ **ETL Page**: 2-column layout with Connections section and ETL Jobs section
- ✅ **BigQuery Schema Editor**: Interactive table with editable types/modes, confidence indicators, warnings
- ✅ **Smart Type Detection**: Auto-mapping with 🟢🟡🔴 confidence indicators
- ✅ **Schema Customization**: Edit BigQuery types (13 types), modes (NULLABLE/REQUIRED), table names
- ✅ **Performance Optimization UI**: Partitioning/clustering configuration display
- ✅ **Modern Connection Cards**: Minimalistic 3-column design (60% info + 30% meta + 10% actions)
- ✅ **Reusable Card System**: cards.css for consistent tablet/card design across platform
- ✅ **Live Status Indicators**: Green/red/yellow dots with intelligent error handling
- ✅ **Wizard Modes**: Full ETL job creation wizard + Standalone connection management
- ✅ **Status Timestamps**: "Tested 5m ago" display on connection cards
- ✅ **Manual Refresh**: Refresh button to re-test connections on demand
- ✅ **Standardized Buttons**: Consistent styling using buttons.css system + fixed button sizing
- ✅ **Debug Logging**: Comprehensive console logs with emoji indicators
- ✅ **Dotted Background**: Professional Vertex AI-style dotted pattern background
- ✅ **Custom Modal System**: Reusable confirmation modals (modals.css)
- ✅ **Unified Navigation**: Consistent chevron arrows across all navigation buttons
- ✅ **Modern Empty States**: Professional empty state messages without icons
- ✅ **Optimized Space Usage**: Compact 2-row layout with text truncation

**Developer Experience:**
- ✅ User creation script (`create_user.py`)
- ✅ Comprehensive README documentation
- ✅ `.gitignore` configured for Django projects
- ✅ Requirements file with all dependencies

**Database:**
- ✅ **Migrated to Cloud SQL PostgreSQL** (November 14, 2025)
- ✅ **DEVELOPMENT DATABASE ONLY** - Shared across laptop and desktop for development
- ✅ Cloud SQL Proxy for secure connections
- ✅ Environment-based configuration (.env file)
- ⚠️ **Future Migration Required**: This is a temporary dev database. Production will use a separate control plane database in the `b2b-recs` project (see `implementation.md` for architecture)

### Pages Structure

**System-Level:**
- System Dashboard - View all models/endpoints and summary stats
- Create Model/Endpoint - Initialize new recommendation systems

**Model-Level (per Model/Endpoint):**
- Dashboard - Model health, recent runs, performance
- Training Interface - Launch training jobs, view status
- Experiments Dashboard - View MLflow results, compare models
- Deployment Manager - Deploy models, manage versions
- Pipeline Configuration - Configure ML pipeline parameters
- Dataset Manager - Browse BigQuery data
- ETL - Configure data extraction
- Feature Engineering - Visual designer (placeholder)

## Quick Start

> **⚠️ Development Database Notice**
> This setup uses a **shared Cloud SQL PostgreSQL database for development** (hosted in `memo2-456215` project).
> This is a **temporary solution** - production will use a separate control plane database in the `b2b-recs` project.
> See `implementation.md` for the full production architecture.

### 1. Clone and set up virtual environment

```bash
git clone <your-repo-url>
cd b2b_recs
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Database Connection

This project uses **Cloud SQL PostgreSQL** for the database (shared across all development machines).

Create a `.env` file in the project root:

```bash
# Copy the example file
cp .env.example .env

# Edit .env and add the database password (ask team for credentials)
```

The `.env` file should contain:
```
DB_ENGINE=postgresql
DB_NAME=b2b_recs_dev
DB_USER=django_user
DB_PASSWORD=<ask-for-password>
DB_HOST=127.0.0.1
DB_PORT=5433
```

**Note**: The database is already set up and populated. You don't need to run migrations or create users!

### 3. Start Development Environment

```bash
./start_dev.sh
```

**What happens:**
- Cloud SQL Proxy starts in background (connects to `memo2-db` instance)
- Django development server starts in foreground (all logs visible in terminal)
- You can see and copy all Django logs in real-time

**To stop:** Press **Ctrl+C** (automatically stops both Django and Cloud SQL Proxy)

### 4. Access the application

- **Web App**: http://127.0.0.1:8000/
- **Admin Panel**: http://127.0.0.1:8000/admin/
- **Database**: 127.0.0.1:5433 (via Cloud SQL Proxy)

### 5. Login and start working

Login credentials:
- Username: `dkulish`
- Password: `admin123`

Steps:
1. Log in at http://127.0.0.1:8000/
2. Click "Create Model/Endpoint" on the System Dashboard
3. Fill in the name and description
4. Explore the model-specific pages (Dashboard, Training, ETL, etc.)

## Project Structure

```
b2b_recs/
├── config/                 # Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── ml_platform/           # Main application
│   ├── models.py         # Database models
│   ├── views.py          # View functions
│   ├── urls.py           # URL routing
│   └── admin.py          # Admin configuration
├── templates/            # HTML templates
│   ├── base.html         # Base template with navigation
│   ├── base_model.html   # Model-specific base
│   ├── login.html        # Login page
│   └── ml_platform/      # App-specific templates
├── static/               # Static files (CSS, JS)
├── manage.py             # Django management script
└── requirements.txt      # Python dependencies
```

## Database Models

### ModelEndpoint
Represents a complete ML project/pipeline instance. Each ModelEndpoint is a separate recommendation system.

### ETL Models (Configuration-Driven Architecture)

**ETLConfiguration** - Parent configuration for scheduling and settings
- Schedule type (manual, daily, weekly, monthly)
- Cron expression for Cloud Scheduler
- Last run status and timestamps
- Cloud Run service URL reference

**DataSource** - Individual data source connections (supports multiple per client)
- Supported types: PostgreSQL, MySQL, SQL Server, BigQuery, CSV, Parquet
- Connection details (host, port, database, credentials)
- Connection testing status
- Enable/disable per source

**DataSourceTable** - Table-level extraction configuration
- Source → destination table mapping
- Sync modes: replace (full refresh), append, incremental (date-based)
- Row limits for testing
- Per-table enable/disable

**ETLRun** - Execution history with detailed results
- Tracks all sources and tables in a single run
- Per-source and per-table success/failure
- Total rows extracted
- JSON detailed results structure

### PipelineConfiguration & PipelineRun
ML pipeline parameters and execution tracking (4-stage pipeline: extraction → vocab → training → deployment).

### Experiment
MLflow experiment tracking with metrics and parameters.

### TrainedModel
Individual trained model versions with performance metrics.

### Deployment
Deployment history and active deployments to Cloud Run.

### PredictionLog & SystemMetrics
Aggregated prediction statistics and system-wide metrics.

## 🔄 ETL Implementation

### Architecture: Configuration-Driven Multi-Source ETL

The ETL system uses a **single Docker container template** deployed per client with configuration stored in Django.

```
┌─────────────────────────────────────────┐
│  Django (Client-facing UI)              │
│  - Configure data sources (PostgreSQL,  │
│    MySQL, BigQuery, CSV, Parquet)       │
│  - Set schedules                         │
│  - Test connections                      │
│  - Monitor runs                          │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│  Cloud Scheduler (per client)            │
│  - Triggers on schedule (daily 2am, etc.)│
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│  Cloud Run Job (ETL Container)           │
│  1. Fetch configuration from Django API │
│  2. For each enabled data source:       │
│     - Connect (PostgreSQL/MySQL/etc.)   │
│     - Extract configured tables         │
│     - Load to BigQuery                  │
│  3. Report results back to Django       │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│  BigQuery (Client's GCP Project)         │
│  Dataset: raw_data                       │
│    - transactions (from PostgreSQL)     │
│    - products (from MySQL)              │
│    - customers (from CSV upload)        │
└─────────────────────────────────────────┘
```

### ✅ Implemented Features

**Django Web UI** (`/models/{id}/etl/`):
- **Per-Table ETL Jobs**: Each data source extracts exactly one table with independent scheduling
- **Advanced 4-Step ETL Wizard**: Enhanced with load strategy configuration
  - Step 1: Select existing connection + Enter job name
  - Step 2: Select schema + Select table from schema (auto-fetched)
  - Step 3: Configure load strategy (table preview, column selection, load type, historical backfill)
  - Step 4: Configure schedule + Review summary
- **Schema Selection**: Support for multi-schema databases (PostgreSQL, Oracle, SQL Server)
- **Load Strategy Configuration**:
  - Transactional (append-only with timestamp tracking)
  - Catalog (daily snapshot, full replace)
  - Historical backfill (load last 30/60/90 days on first sync)
- **Table Preview & Column Selection**:
  - View column metadata, types, and sample values
  - Select specific columns to sync (deselect heavy BLOB/TEXT fields)
  - Smart auto-detection of timestamp columns and primary keys
  - Visual indicators (🔑 for primary keys, 🕐 for timestamps)
- **Standalone Connection Management**: 2-step wizard for independent connection creation
  - Step 1: Category tabs (Relational DB/Files/NoSQL) + tile-based database selection
  - Step 2: Connection form with test button → "Save Connection" after successful test
  - Connections managed separately from ETL jobs
  - Test-first pattern: Connection test BEFORE Secret Manager save
- **Connection Management System**: Reusable named database connections
  - Create named connections independently (e.g., "Production PostgreSQL")
  - Auto-suggest connection names based on source type + database name
  - Reuse saved connections across multiple ETL jobs
  - Live status indicators (green=working, red=failed)
  - Connection cards with "Use This Connection" button
  - Duplicate connection name validation
- **Real Database Connection Testing**: Live connection validation with actual database credentials
  - PostgreSQL: Full support with connection pooling and timeout handling
  - MySQL: Full support with connection validation
  - BigQuery: Service account authentication support
  - Auto-test saved connections in background to fetch table list
- **Automatic Table Discovery**: Fetches real table list with metadata after successful connection
  - Table names
  - Row counts
  - Last updated timestamps
- **Secure Credential Storage**: All passwords saved to GCP Secret Manager (never in Django DB)
- **Atomic ETL Job Creation**: ETL jobs created at final step (no drafts, cleaner flow)
  - Links to Connection via ForeignKey
  - Connection.last_used_at updated on job creation
  - Enabled immediately after creation
- **ETL Job Name Validation**: Duplicate job name check at Step 1 (prevents UNIQUE constraint errors)
- **Edit/Restore ETL Jobs**: Resume wizard from last completed step
  - Click "Edit" button on any ETL job
  - Wizard opens at appropriate step with pre-filled data
  - Auto-fetches tables using stored credentials from Secret Manager
  - Proper CREATE vs EDIT flow separation (no duplicate UNIQUE errors)
  - Skip name validation in edit mode
- **Loading State Management**: Visual feedback during async operations
  - Animated spinner with "Loading tables..." message
  - Navigation buttons disabled during table fetch
  - Prevents race conditions and broken state
  - Error messages with "Go back" suggestions
- **Inline Error Messages**: User-friendly error feedback without popup alerts
- **Full CRUD Operations**: Add, edit, delete ETL jobs with complete configuration
- **Multiple Data Source Types**: PostgreSQL, MySQL, SQL Server, BigQuery, Firestore, MongoDB, Google Cloud Storage, AWS S3, Azure Blob Storage
- **Sync Modes**: Full Refresh (replace), Append, Incremental (timestamp-based)
- **Per-Job Run Trigger**: "Run Now" button on each individual job
- **Schedule Configuration**: Manual, hourly, daily, weekly, monthly options
- **ETL Run History**: View past executions with detailed results and row counts

**API Endpoints**:

*ETL Job Management:*
- `POST /api/models/{id}/etl/add-source/` - Create new data source/job
- `POST /api/models/{id}/etl/save-draft/` - Save draft DataSource (at Step 2) with connection link
- `POST /api/models/{id}/etl/check-name/` - Validate ETL job name uniqueness
- `GET /api/etl/sources/{id}/` - Get source details for editing
- `POST /api/etl/sources/{id}/update/` - Update existing data source
- `POST /api/etl/sources/{id}/test/` - Test database connection
- `POST /api/etl/sources/{id}/run/` - Run ETL for single source
- `POST /api/etl/sources/{id}/delete/` - Delete data source
- `POST /api/models/{id}/etl/toggle/` - Enable/disable ETL scheduling
- `POST /api/models/{id}/etl/run/` - Trigger full ETL run (all sources)
- `GET /api/etl/runs/{id}/status/` - Poll ETL run status

*Connection Management:*
- `POST /api/models/{id}/connections/test-wizard/` - Test connection in wizard (real connection, fetches tables)
- `POST /api/models/{id}/connections/create/` - Create new named Connection with credentials
- `GET /api/models/{id}/connections/` - List all saved connections for model
- `GET /api/connections/{id}/` - Get connection details (without credentials)
- `GET /api/connections/{id}/credentials/` - Get decrypted credentials from Secret Manager
- `POST /api/connections/{id}/test/` - Test existing connection
- `POST /api/connections/{id}/test-and-fetch-tables/` - Test connection and fetch tables using stored credentials (for edit mode)
- `POST /api/connections/{id}/delete/` - Delete connection (checks for dependent jobs)

**Database Models**:
- **ETLConfiguration**: Schedule settings and Cloud Run service configuration
- **Connection**: Reusable named database connections (NEW)
  - Name (unique per ModelEndpoint)
  - Source type (postgresql, mysql, bigquery, etc.)
  - Connection parameters (host, port, database, schema)
  - Credentials stored in GCP Secret Manager
  - ForeignKey to ModelEndpoint (one model can have many connections)
- **DataSource**: Individual ETL jobs (one table per source)
  - ForeignKey to Connection (many jobs can share one connection)
  - Job name (unique per ETLConfiguration)
  - Enable/disable per job
  - Connection test status and last test timestamp
  - Draft vs finalized status (is_enabled)
  - Wizard step tracking (wizard_last_step, wizard_completed_steps) for resume functionality
- **DataSourceTable**: Table-level extraction config (sync mode, incremental column, row limits)
- **ETLRun**: Execution history with per-source and per-table success tracking

**Security Architecture**:
- All database passwords stored in **GCP Secret Manager** (never in Django DB)
- Secret naming for connections: `model-{model_id}-connection-{connection_id}-credentials`
- Django only stores the secret name reference in Connection model
- Connection testing validates credentials before saving
- Credentials saved immediately when creating new Connection
- Multiple DataSource jobs can reference the same Connection (share credentials)

### 📚 How to Use: Connection Management & ETL Jobs

**ETL Page Layout:**

The ETL page features a 2-column layout:
- **LEFT**: Connections section - Manage database connections independently
- **RIGHT**: ETL Jobs section - Configure and monitor extraction jobs

**Creating a Standalone Connection:**

1. **Navigate to ETL Page**: Go to `/models/{id}/etl/` for your model
2. **Click "+ Connection"** (in Connections section): Opens 2-step connection wizard modal

**Connection Wizard - Step 1: Select Database Type**
- Choose category: **Relational Databases**, **Flat Files**, or **NoSQL**
- Select specific database type from tile-based grid:
  - Relational: PostgreSQL, MySQL, Amazon Redshift, BigQuery, Snowflake
  - Flat Files: CSV Files, Parquet Files
  - NoSQL: MongoDB, Firestore
- Click "Next" to proceed to configuration

**Connection Wizard - Step 2: Configure & Test**
- Enter connection details:
  - Host (database server address)
  - Port (auto-populated based on type: PostgreSQL=5432, MySQL=3306, etc.)
  - Database name
  - Username & Password
  - **Connection Name** (e.g., "Production PostgreSQL") - required and must be unique
- Click "Test Connection" to validate credentials
  - **Important**: Test does NOT save to Secret Manager yet (test-first pattern)
- On success: "Save Connection" button appears
- Click "Save Connection":
  - Credentials saved to GCP Secret Manager
  - Connection created in database
  - Modal auto-closes, connections list reloads with new connection
- **Status Indicator**: Green dot = working, Red dot = failed (auto-tested on page load)

**Creating Your First ETL Job:**

1. **Navigate to ETL Page**: Go to `/models/{id}/etl/` for your model
2. **Click "+ ETL Job"** (in Jobs section): Opens the 3-step wizard modal

**ETL Wizard - Step 1: Select Connection & Job Name**
- Enter unique job name (e.g., "Daily Transactions Extract")
- Select existing connection from list:
  - Saved connections shown as cards with status indicators (green/red dot)
  - Shows connection name, type, host, database
  - Click "Use This Connection" button
- If no connections exist: Create one first using "+ Connection" button

**ETL Wizard - Step 2: Schema & Table Selection**
- **Schema dropdown** populated automatically from selected connection
  - PostgreSQL/Oracle: Shows all user schemas
  - MySQL: Auto-selects database as schema (single option)
  - BigQuery: Shows all datasets
- Select schema → **Table list** auto-fetches for that schema
- Shows table metadata: name, row count, last updated timestamp
- Select the table to extract
- Click "Next"

**ETL Wizard - Step 3: Configure Load Strategy** ⭐ NEW
- **Table Preview**: View column structure before configuring
  - Column names, data types, nullability
  - Sample values (5 rows per column)
  - Visual indicators (🔑 primary key, 🕐 timestamp columns)
- **Column Selection**: Check/uncheck columns to sync
  - "Select All" / "Deselect All" buttons
  - Useful for excluding heavy BLOB/TEXT fields
- **Load Type**: Choose data loading strategy
  - **Transactional (Append-Only)**: For transactions, logs, events
    - Select timestamp column for incremental tracking
    - Historical backfill: Last 30/60/90 days or custom date
    - First sync loads historical data, subsequent syncs only new records
  - **Catalog (Daily Snapshot)**: For products, customers, inventory
    - Full table replacement on each sync
    - No incremental tracking needed
- Click "Next"

**ETL Wizard - Step 4: Schedule & Review**
- Configure schedule: Manual, Hourly, Daily, Weekly, or Monthly
- Review summary:
  - Job name
  - Connection details
  - Schema and table name (schema.table format)
  - Load type and configuration
  - Selected columns
  - Schedule
- Click "Create ETL Job" to finalize:
  - ETL job created atomically (no drafts)
  - All configuration stored in database
  - Connection.last_used_at updated
  - Job enabled immediately
  - Modal closes, jobs list reloads

**Reusing Connections:**
- Saved connections appear as cards at Step 1
- Shows connection name, type, host, database
- Click "Use This Connection" to skip Step 2 configuration
- Credentials securely retrieved from GCP Secret Manager
- Connection auto-tested in background to fetch table list

**Benefits of Connection Reuse:**
- ✅ No need to re-enter credentials for same database
- ✅ Faster job creation (skip connection configuration)
- ✅ Centralized credential management (update once, affects all jobs)
- ✅ Security: Credentials stored once in Secret Manager

**Editing ETL Jobs:**
- Click "Edit" button on any ETL job (draft or completed)
- Wizard automatically opens at the **next step** after last completed step
  - Draft saved at Step 2 → opens at Step 3 (table selection)
  - Completed job (Step 5) → opens at Step 5 (review/edit)
- Tables auto-fetched using stored credentials (no password re-entry needed)
- Animated loading spinner shows while fetching tables
- Navigation buttons disabled during loading to prevent errors
- All previously entered data pre-populated in form
- Can modify any configuration and save changes
- In edit mode, name validation skipped (you're editing the same job)

**Editing Connections:**
- Click "Edit" button on any connection card in the Connections section
- Form pre-populated with existing connection details
- Modify host, port, database, username, or password as needed
- Click "Test Connection" to validate new credentials
- If test succeeds, connection is updated in database
- Secret Manager credentials updated with new password
- Shows "X jobs affected" message (all ETL jobs using this connection will use new credentials)
- Modal auto-closes after 1.5 seconds
- Connections list reloads with updated status

**Deleting Connections:**
- Click "Delete" button on connection card
- System checks for dependent ETL jobs
- **If jobs exist**: Shows error message with list of dependent job names, blocks deletion
  - Example: "Cannot delete connection: 3 ETL job(s) depend on it. Dependent jobs: • daily_users • products_sync • orders_extract"
- **If no dependencies**: Confirms deletion, removes connection and credentials from Secret Manager
- Protected deletion ensures no orphaned ETL jobs

**Connection Status Indicators:**
- 🟢 **Green dot**: Connection tested successfully, database reachable
- 🔴 **Red dot**: Connection test failed, check credentials or network
- 🟡 **Yellow dot**: Test system error, unclear status (Secret Manager unavailable, network timeout, etc.)
- ⚪ **Gray dot**: Connection not tested yet
- Status auto-updated on page load (background API calls test each connection)
- Real-time health monitoring for all connections
- Intelligent error handling: Network errors don't incorrectly mark connections as "failed"
- Fallback to previous status when test system unavailable
- **Manual refresh button** to re-test all connections on demand
- **Timestamp display** shows "Tested 5m ago" for freshness awareness
- **Comprehensive debug logs** in browser console with emoji indicators

### 🔨 Pending Components (For Production Deployment)

**ETL Container** (Not yet built - needed for actual data extraction):
- `etl_runner.py` - Python script with database connectors
- Database drivers: psycopg2 (PostgreSQL), PyMySQL (MySQL), pyodbc (SQL Server)
- BigQuery loading via `pandas-gbq`
- Reads Django configuration via REST API
- Dockerfile for Cloud Run deployment

**When Needed**:
- First client goes to production
- Actual database connections required
- For now, Django simulates ETL runs for testing

### Key Design Decisions

1. **Per-Table Job Architecture**: One DataSource = One Table = One Independent Schedule
   - Maximum flexibility for different update frequencies per table
   - Granular control over sync modes and incremental logic
   - Independent failure handling (one table failure doesn't block others)
2. **Connection Reuse Architecture**: Separate Connection model with ForeignKey from DataSource
   - One Connection can be shared by many ETL jobs
   - Named connections (e.g., "Production PostgreSQL") for easy identification
   - Credentials stored once per connection (not duplicated per job)
   - Auto-suggest connection names based on source type + database name
   - Connection.last_used_at tracking for usage monitoring
3. **Configuration-Driven**: All extraction logic driven by Django database configuration
4. **Simplified Wizard UX**:
   - **3-step ETL wizard** (down from 5 steps, 40% faster)
   - **2-step connection wizard** with category tabs and tile-based selection
   - Complete separation: Connections managed independently from ETL jobs
   - Job name uniqueness validated at Step 1 (prevents database errors)
   - Connection name uniqueness validated during connection creation
5. **Atomic Creation Pattern**: ETL jobs created at final step (no drafts, cleaner flow)
   - No intermediate saves until user completes wizard
   - Connection.last_used_at updated on job creation
   - Jobs enabled immediately after creation
6. **Test-First Pattern**: Connection test BEFORE Secret Manager save
   - User tests credentials first to validate
   - "Save Connection" button only appears after successful test
   - Prevents premature credential storage in Secret Manager
7. **Security-First**: GCP Secret Manager for credential storage, never plain text in Django DB
8. **Real Connection Testing**: Live database validation before saving (not fake success)
   - Auto-test saved connections in background when reusing
   - Fetches real table list with metadata during test
9. **Connection Manager Utility**: `ml_platform/utils/connection_manager.py`
   - PostgreSQL, MySQL, BigQuery connection testing
   - Table metadata fetching (names, row counts, last updated)
   - Secret Manager integration for credential save/retrieve
10. **No Airflow**: Uses Cloud Run + Cloud Scheduler for simplicity and cost ($10-20/month vs $120/month)
11. **Per-Client Isolation**: Each client gets their own Cloud Scheduler + Cloud Run deployment
12. **Same Container Image**: One Docker image deployed to all clients with different env vars

## 🎯 Next Steps - Chapter-by-Chapter Implementation

ETL implementation is complete! Next features to build:

### Priority 1 - Core ML Pipeline (Weeks 3-5)
1. ✅ **ETL Page** - ✅ COMPLETE (Django UI, APIs, multi-source configuration)
2. **Training Interface** - Celery + Vertex AI integration, real-time status updates
3. **Pipeline Configuration** - Complete form validation, parameter presets
4. **Deployment Manager** - Cloud Run API integration, one-click deployment

### Priority 2 - Monitoring & Analytics (Week 5-6)
5. **MLflow Integration** - Connect to MLflow server, display experiments, model comparison
6. **Model Dashboard** - Real-time metrics, health checks, prediction volume
7. **Dataset Manager** - BigQuery table browser, data preview, quality checks

### Priority 3 - Advanced Features (Week 6+)
8. **Feature Engineering** - Visual designer for feature creation
9. **Control Plane** - Separate app for cross-customer management, billing dashboard
10. **Production Ready** - ETL Container + Dockerfile, CI/CD, monitoring, testing

### Quick Wins (Can be done anytime)
- Add pagination to tables
- Add search/filter to System Dashboard
- Add model status transitions (draft → active)
- Add confirmation modals for destructive actions
- Add loading indicators for AJAX calls

## Architecture Overview

See `implementation.md` for the complete architecture and implementation plan.

### Key Architecture Decisions
- Separate GCP project per client (complete isolation)
- Django for client-facing UI (no-code interface)
- Cloud Run for all services (Django, MLflow, ETL, model serving)
- Vertex AI for GPU training jobs
- BigQuery for data warehouse
- MLflow for experiment tracking

## Development

### Working Across Multiple Machines

This project uses a **shared Cloud SQL PostgreSQL database for DEVELOPMENT**. All development machines (laptop + desktop) connect to the same centralized database, so data is automatically synchronized.

**⚠️ Important**: This is a **temporary development database** hosted in the `memo2-456215` project for cost savings. Production will use a separate control plane database in the `b2b-recs` project (see `implementation.md` architecture).

**Benefits:**
- ✅ Real-time data sync across all development machines
- ✅ No manual data export/import needed
- ✅ All users, models, and ETL configurations shared
- ✅ Production-ready PostgreSQL database type

**On a new machine:**
```bash
git pull
source venv/bin/activate
pip install -r requirements.txt

# Create .env file with database credentials
cp .env.example .env
# Edit .env and add the database password (ask team)

# Start development environment (Cloud SQL Proxy + Django)
./start_dev.sh
```

**That's it!** No migrations or user creation needed - the database is already populated.

**Note**: `db.sqlite3` is kept in `.gitignore` for local fallback. To use SQLite locally, delete or don't create the `.env` file (Django defaults to SQLite).

### Adding a new page

1. Create view in `ml_platform/views.py`
2. Add URL pattern in `ml_platform/urls.py`
3. Create template in `templates/ml_platform/`

### Updating models

```bash
python manage.py makemigrations
python manage.py migrate
```

### Accessing the admin interface

Navigate to http://127.0.0.1:8000/admin/ and log in with your superuser credentials.

### Change your password

```bash
python manage.py changepassword dkulish
# Or just run: python create_user.py (updates existing user)
```

## Technology Stack

**Backend:**
- Django 4.2 LTS (Long Term Support until April 2026)
- PostgreSQL 13 (via Cloud SQL)
- Cloud SQL Proxy for secure database connections
- Python 3.13

**Frontend:**
- Tailwind CSS (via CDN)
- Font Awesome icons
- Vanilla JavaScript (for now)
- Custom CSS Design System:
  - `buttons.css` - Standardized button styles with fixed sizing
  - `backgrounds.css` - Dotted pattern backgrounds (Vertex AI style)
  - `modals.css` - Reusable modal/confirmation dialog system

**Infrastructure (Development):**
- Cloud SQL (PostgreSQL 13) - **DEV DATABASE ONLY** - Shared across development machines
  - Instance: `memo2-db` in project `memo2-456215` (reusing existing instance for cost savings)
  - Database: `b2b_recs_dev`
  - **Note**: Production will use separate control plane database in `b2b-recs` project
- GCP Secret Manager - Credential storage for ETL connections
- Cloud SQL Proxy - Secure database access

**Future:**
- Vue.js for reactive components
- Celery for async tasks
- Redis for caching
- Additional Google Cloud Platform services

## UI Components - Design System

A comprehensive design system has been implemented for consistent, professional UI across all pages.

### 1. Button System
**Location**: `static/css/buttons.css`

All buttons follow a standardized design:
- **White background** with thin black border (1px)
- **Light green hover effect** (`#f0fdf4`)
- Subtle shadow for depth
- Proper icon spacing (10px gap)
- Short and wide proportions for better visibility

### Base Button Classes

**Primary button** (main actions):
```html
<button class="btn btn-primary">
    <i class="fas fa-plus"></i><span>Add Item</span>
</button>
```

**Button variants**:
- `.btn-success` - Light green (create, confirm actions)
- `.btn-danger` - Light red (delete, remove actions)
- `.btn-secondary` - Neutral (less emphasis)
- `.btn-warning` - Light yellow (caution actions)

**Size modifiers**:
- `.btn-sm` - Small buttons
- `.btn-lg` - Large buttons
- `.btn-wide` - Extra wide buttons (200px min-width)
- `.btn-block` - Full width
- `.btn-fixed` - Fixed width for uniform sizing (works with `.btn-sm` for 110px width)
- `.btn-icon` - Icon-only buttons (square with no min-width)

### Usage Guidelines

1. **Always wrap text in `<span>` tags** when using icons for proper spacing
2. **Use consistent color coding**: success (green), danger (red), primary (neutral)
3. **Icons are optional** but provide good visual cues
4. **Disabled state** is handled automatically via CSS `:disabled` pseudo-class

### Examples

**With icon:**
```html
<button class="btn btn-success">
    <i class="fas fa-check"></i><span>Save</span>
</button>
```

**Text only:**
```html
<button class="btn btn-primary">
    <span>Test Connection</span>
</button>
```

**Wide button:**
```html
<button class="btn btn-primary btn-wide">
    <i class="fas fa-plus"></i><span>ETL Job</span>
</button>
```

### Connection Test Containers

Connection test sections use dynamic background colors:
- **White** (default) - Before testing
- **Light green** (`bg-green-50`) - Success
- **Light red** (`bg-red-50`) - Failure

The "Next" navigation button remains disabled until connection test succeeds.

### 2. Background System
**Location**: `static/css/backgrounds.css`

Professional dotted background patterns inspired by Vertex AI Pipelines:

**Available patterns**:
- `.bg-dotted` - Standard dotted pattern (20px spacing, #d1d5db dots)
- `.bg-dotted-subtle` - Lighter dots for less prominent backgrounds
- `.bg-dotted-dense` - Tighter spacing (15px) for more texture

**Usage**: Applied to main content areas where white cards should float elegantly.

### 3. Modal System
**Location**: `static/css/modals.css`

Reusable modal/confirmation dialog system with professional styling:

**Components**:
- `.modal-overlay` - Dark background overlay
- `.modal-container` - White modal box with animation
- `.modal-header` - Header with colored icon
- `.modal-body` - Content area (supports HTML)
- `.modal-footer` - Button area

**Modal types** (colored icons and buttons):
- `danger` - Red (delete, destructive actions)
- `warning` - Yellow (caution messages)
- `info` - Blue (information)
- `success` - Green (confirmations)

**JavaScript function**:
```javascript
showConfirmModal({
    title: 'Delete Connection',
    message: '<p>Are you sure?</p>',
    confirmText: 'Delete',
    cancelText: 'Cancel',
    type: 'danger',
    onConfirm: () => { /* action */ }
});
```

**Features**:
- Smooth slide-in animation
- Auto-hides Cancel button for error/info messages (confirmText === 'OK')
- Keyboard support (ESC to close)
- Click overlay to close
- Customizable buttons and icons

## Contributing

This is an internal project. See `implementation.md` for the complete roadmap and implementation phases.

## License

Proprietary - All rights reserved
