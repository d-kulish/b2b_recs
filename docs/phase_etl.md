# Phase: ETL Domain

## Document Purpose
This document provides detailed specifications for the **ETL (Extract, Transform, Load)** domain in the ML Platform. The ETL domain manages data ingestion from external sources into BigQuery for model training.

**Last Updated**: 2025-12-27 (v8 - Added Issue #6: CSV column mapping and TIMESTAMP parsing fixes)

---

## Overview

### Purpose
The ETL domain allows users to:
1. Create and manage **Connections** to external data sources (databases, cloud storage, NoSQL)
2. Configure **ETL Jobs** that extract data from those connections into BigQuery
3. Schedule automated data extraction pipelines via Cloud Scheduler
4. Monitor ETL run history and troubleshoot failures

### Key Principles

1. **Connections are Reusable.** A single connection (e.g., "Production PostgreSQL") can be used by multiple ETL jobs. This prevents credential duplication and simplifies maintenance.

2. **Credentials are Secure.** Database passwords and API keys are stored in Google Secret Manager, not in the Django database. Only secret references are stored.

3. **ETL Jobs are Atomic.** Each ETL job extracts data from one connection to one BigQuery table. Complex pipelines are composed of multiple jobs.

4. **Scheduling is Optional.** Jobs can be manual-only or scheduled (hourly, daily, weekly, monthly) via Cloud Scheduler.

5. **Incremental Loads Supported.** Jobs can be configured for full replacement or incremental extraction based on a timestamp column.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ETL Domain                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┐         ┌──────────────────┐         ┌──────────────┐ │
│  │   Connections    │ ──uses──│    ETL Jobs      │──runs───│  Cloud Run   │ │
│  │   (Credentials)  │         │  (DataSource)    │         │  ETL Runner  │ │
│  └────────┬─────────┘         └────────┬─────────┘         └──────┬───────┘ │
│           │                            │                          │         │
│           │                            │                          │         │
│  ┌────────▼─────────┐         ┌────────▼─────────┐         ┌──────▼───────┐ │
│  │  Secret Manager  │         │ Cloud Scheduler  │         │   BigQuery   │ │
│  │  (Credentials)   │         │  (Automation)    │         │   (Target)   │ │
│  └──────────────────┘         └──────────────────┘         └──────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### What Gets Stored

```
Connection (Django Model)
├── Identification: name, description, source_type
├── Database: host, port, database, schema, username
├── Cloud Storage: bucket_path, service_account_json
├── AWS: aws_access_key_id, aws_region
├── Azure: azure_storage_account
├── NoSQL: connection_string
├── Security: credentials_secret_name (Secret Manager reference)
├── Status: connection_tested, last_test_at, last_test_status
└── Tracking: last_used_at, created_at, updated_at

DataSource (ETL Job - Django Model)
├── Reference: connection (FK), etl_config (FK)
├── Identification: name, source_type (denormalized)
├── Schedule: schedule_type, cloud_scheduler_job_name
├── Extraction: use_incremental, incremental_column, last_sync_value
├── Status: is_enabled, last_run_at, last_run_status
└── Tables: DataSourceTable[] (one-to-many)
```

---

## Chapter: ETL Setup

The ETL Setup chapter contains two sub-chapters:
1. **Connections** - Manage database and storage connections
2. **ETL Jobs** - Configure data extraction pipelines

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ETL Setup                                                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────┐    ┌─────────────────────────────────────┐ │
│  │ Connections                 │    │ ETL Jobs                            │ │
│  │ [+ New] [Test Connections]  │    │ [+ New ETL Job]                     │ │
│  │ ┌─────────────────────────┐ │    │ ┌─────────────────────────────────┐ │ │
│  │ │ ● Production PostgreSQL │ │    │ │ ▶ Daily Transactions Extract   │ │ │
│  │ │   Database: analytics   │ │    │ │   Connection: Prod PostgreSQL  │ │ │
│  │ │   Used by: 3 jobs       │ │    │ │   Schedule: Daily 09:00        │ │ │
│  │ └─────────────────────────┘ │    │ └─────────────────────────────────┘ │ │
│  │ ┌─────────────────────────┐ │    │ ┌─────────────────────────────────┐ │ │
│  │ │ ● GCS Data Lake         │ │    │ │ ⏸ Weekly Products Sync         │ │ │
│  │ │   Bucket: gs://data-lake│ │    │ │   Connection: GCS Data Lake    │ │ │
│  │ │   Used by: 1 job        │ │    │ │   Schedule: Weekly Mon 08:00   │ │ │
│  │ └─────────────────────────┘ │    │ └─────────────────────────────────┘ │ │
│  │                             │    │                                     │ │
│  │ Showing 1-2 of 5           │    │ Showing 1-2 of 8                    │ │
│  │ [< Prev] [1] [2] [3] [>]   │    │ [< Prev] [1] [2] [3] [4] [>]       │ │
│  └─────────────────────────────┘    └─────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Sub-Chapter: Connections

### Purpose
Connections represent reusable database/storage credentials. They are created once and can be referenced by multiple ETL jobs.

### Supported Connection Types

#### Relational Databases
| Type | Key | Display Name | Authentication |
|------|-----|--------------|----------------|
| PostgreSQL | `postgresql` | PostgreSQL | Host, Port, Database, Username, Password |
| MySQL | `mysql` | MySQL | Host, Port, Database, Username, Password |
| MariaDB | `mariadb` | MariaDB | Host, Port, Database, Username, Password |
| Oracle | `oracle` | Oracle Database | Host, Port, Database, Username, Password |
| SQL Server | `sqlserver` | Microsoft SQL Server | Host, Port, Database, Username, Password |
| IBM DB2 | `db2` | IBM DB2 | Host, Port, Database, Username, Password |
| Amazon Redshift | `redshift` | Amazon Redshift | Host, Port, Database, Username, Password |
| Google BigQuery | `bigquery` | Google BigQuery | Project ID, Dataset, Service Account JSON |
| Snowflake | `snowflake` | Snowflake | Host, Port, Database, Username, Password |
| Azure Synapse | `synapse` | Azure Synapse | Host, Port, Database, Username, Password |
| Teradata | `teradata` | Teradata | Host, Port, Database, Username, Password |

#### Cloud Storage
| Type | Key | Display Name | Authentication |
|------|-----|--------------|----------------|
| Google Cloud Storage | `gcs` | Google Cloud Storage | Bucket Path (gs://), Service Account JSON |
| AWS S3 | `s3` | AWS S3 | Bucket Path (s3://), Access Key ID, Secret Access Key, Region |
| Azure Blob | `azure_blob` | Azure Blob Storage | Bucket Path, Storage Account, Account Key or SAS Token |

#### NoSQL Databases
| Type | Key | Display Name | Authentication |
|------|-----|--------------|----------------|
| MongoDB | `mongodb` | MongoDB | Connection String |
| Firestore | `firestore` | Google Firestore | Project ID, Service Account JSON |
| Cassandra | `cassandra` | Apache Cassandra | Connection String |
| DynamoDB | `dynamodb` | Amazon DynamoDB | AWS Credentials |
| Redis | `redis` | Redis | Connection String |

---

### User Interface

#### Connections List View

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Connections                                    [+ New] [Test Connections]   │
├─────────────────────────────────────────────────────────────────────────────┤
│ 🔍 [Search connections...                                              ]   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ● Production PostgreSQL                          Used by: 3 jobs       │ │
│ │   Relational DB: analytics                       Tested: 2 min ago     │ │
│ │                                                           [Edit] [Del] │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ○ GCS Data Lake                                  Used by: 1 job        │ │
│ │   Cloud Storage: data-lake-bucket                Tested: Never         │ │
│ │                                                           [Edit] [Del] │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ● BigQuery Analytics                             Used by: 2 jobs       │ │
│ │   Relational DB: project.dataset                 Tested: 5 min ago     │ │
│ │                                                           [Edit] [Del] │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Showing 1-3 of 7 connections                                                │
│                                      [< Previous] [1] [2] [Next >]          │
└─────────────────────────────────────────────────────────────────────────────┘

Status Indicators:
● Green  = Connection tested successfully (within last hour)
○ Gray   = Connection never tested or test status unknown
● Red    = Connection test failed
```

#### Connection Card Structure

Each connection card displays:
1. **Status Dot**: Visual indicator of connection health (green/gray/red)
2. **Connection Name**: User-defined friendly name
3. **Type Category**: "Relational DB", "Cloud Storage", or "NoSQL"
4. **Source Info**: Database name, bucket path, or connection string
5. **Usage Count**: Number of ETL jobs using this connection
6. **Last Tested**: Time since last connection test
7. **Actions**: Edit and Delete buttons

#### Create Connection Modal (2-Step Wizard)

**Step 1: Select Connection Type**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 🔌 Create Connection                                           Step 1 of 2 │
│    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│    [Type]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[Configure]                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Select Connection Type                                                       │
│                                                                              │
│ [Relational DB] [Cloud Storage] [NoSQL DB]                                  │
│                                                                              │
│ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐                │
│ │ ○ PostgreSQL    │ │ ○ MySQL         │ │ ○ MariaDB       │                │
│ └─────────────────┘ └─────────────────┘ └─────────────────┘                │
│ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐                │
│ │ ○ Oracle        │ │ ○ SQL Server    │ │ ○ IBM DB2       │                │
│ └─────────────────┘ └─────────────────┘ └─────────────────┘                │
│ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐                │
│ │ ○ Redshift      │ │ ● BigQuery      │ │ ○ Snowflake     │                │
│ └─────────────────┘ └─────────────────┘ └─────────────────┘                │
│ ┌─────────────────┐ ┌─────────────────┐                                    │
│ │ ○ Azure Synapse │ │ ○ Teradata      │                                    │
│ └─────────────────┘ └─────────────────┘                                    │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                    [Next →]      [Cancel]   │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Step 2: Configure Connection (varies by type)**

*Example: PostgreSQL Configuration*
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 🔌 Create Connection                                           Step 2 of 2 │
│    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│    [Type]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[Configure]                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Configure PostgreSQL Connection                                              │
│                                                                              │
│ Connection Name *                                                            │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Production PostgreSQL                                                   │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌────────────────────────────────┐  ┌──────────────────────────────────────┐│
│ │ Host *                         │  │ Port *                               ││
│ │ ┌────────────────────────────┐ │  │ ┌──────────────────────────────────┐ ││
│ │ │ db.example.com             │ │  │ │ 5432                             │ ││
│ │ └────────────────────────────┘ │  │ └──────────────────────────────────┘ ││
│ └────────────────────────────────┘  └──────────────────────────────────────┘│
│                                                                              │
│ Database *                                                                   │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ analytics                                                               │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌────────────────────────────────┐  ┌──────────────────────────────────────┐│
│ │ Username *                     │  │ Password *                           ││
│ │ ┌────────────────────────────┐ │  │ ┌──────────────────────────────────┐ ││
│ │ │ etl_user                   │ │  │ │ ••••••••••••                     │ ││
│ │ └────────────────────────────┘ │  │ └──────────────────────────────────┘ ││
│ └────────────────────────────────┘  └──────────────────────────────────────┘│
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ✓ Connection tested successfully                                        │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                               [← Back]  [Test Connection]  [Save] [Cancel]  │
└─────────────────────────────────────────────────────────────────────────────┘
```

*Example: BigQuery Configuration*
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Configure BigQuery Connection                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Connection Name *                                                            │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ BigQuery Analytics                                                      │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Project ID *                                                                 │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ my-gcp-project                                                          │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Dataset *                                                                    │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ raw_data                                                                │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Service Account JSON *                                                       │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ {                                                                       │ │
│ │   "type": "service_account",                                            │ │
│ │   "project_id": "my-gcp-project",                                       │ │
│ │   ...                                                                   │ │
│ │ }                                                                       │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

*Example: GCS Configuration*
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Configure Google Cloud Storage Connection                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ℹ️ Connection = access to bucket. File type selected during ETL job creation │
│                                                                              │
│ Connection Name *                                                            │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ GCS Data Lake                                                           │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Bucket Path *                                                                │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ gs://my-data-lake-bucket                                                │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Service Account JSON *                                                       │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ { ... }                                                                 │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Data Model

#### Connection Model (`ml_platform/models.py`)

```python
class Connection(models.Model):
    # Foreign Keys
    model_endpoint = ForeignKey(ModelEndpoint)  # Parent model

    # Identification
    name = CharField(max_length=255)            # "Production PostgreSQL"
    source_type = CharField(max_length=50)      # "postgresql", "bigquery", etc.
    description = TextField(blank=True)

    # Database Connections
    source_host = CharField(max_length=255)     # "db.example.com"
    source_port = IntegerField(null=True)       # 5432
    source_database = CharField(max_length=255) # "analytics"
    source_schema = CharField(max_length=255)   # "public"
    source_username = CharField(max_length=255) # "etl_user"
    credentials_secret_name = CharField()       # Secret Manager reference

    # Cloud Storage
    bucket_path = CharField(max_length=512)     # "gs://bucket-name"

    # BigQuery/Firestore
    bigquery_project = CharField(max_length=255)
    bigquery_dataset = CharField(max_length=255)
    service_account_json = TextField()          # JSON key (encrypted in transit)

    # AWS S3
    aws_access_key_id = CharField(max_length=255)
    aws_secret_access_key_secret = CharField()  # Secret Manager reference
    aws_region = CharField(max_length=50)

    # Azure Blob
    azure_storage_account = CharField(max_length=255)
    azure_account_key_secret = CharField()      # Secret Manager reference
    azure_sas_token_secret = CharField()        # Alternative to account key

    # NoSQL
    connection_string = TextField()             # MongoDB, Redis, etc.
    connection_params = JSONField()             # Flexible additional params

    # Status
    is_enabled = BooleanField(default=True)
    connection_tested = BooleanField(default=False)
    last_test_at = DateTimeField(null=True)
    last_test_status = CharField(max_length=20) # "success" or "failed"
    last_test_message = TextField()

    # Usage
    last_used_at = DateTimeField(null=True)

    # Timestamps
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)

    class Meta:
        unique_together = [
            ['model_endpoint', 'name'],
            ['model_endpoint', 'source_type', 'source_host', 'source_port',
             'source_database', 'source_username']
        ]
```

---

### API Endpoints

#### Connection Management APIs

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/models/{id}/connections/test-wizard/` | Test connection and check for duplicates |
| `POST` | `/api/models/{id}/connections/create/` | Create new connection |
| `GET` | `/api/models/{id}/connections/` | List all connections for a model |
| `GET` | `/api/connections/{id}/` | Get connection details |
| `GET` | `/api/connections/{id}/credentials/` | Get decrypted credentials |
| `POST` | `/api/connections/{id}/test/` | Test existing connection |
| `POST` | `/api/connections/{id}/update/` | Update connection |
| `GET` | `/api/connections/{id}/usage/` | Get ETL jobs using this connection |
| `POST` | `/api/connections/{id}/delete/` | Delete connection |

#### Schema and Table Fetching APIs

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/connections/{id}/fetch-schemas/` | List available schemas/datasets |
| `POST` | `/api/connections/{id}/fetch-tables-for-schema/` | List tables in a schema |
| `POST` | `/api/connections/{id}/fetch-table-preview/` | Preview table data (10 rows) |

#### File Operations APIs (Cloud Storage)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/connections/{id}/list-files/` | List files in bucket/container |
| `POST` | `/api/connections/{id}/detect-file-schema/` | Auto-detect file schema (CSV, Parquet, JSON) |

---

### API Response Examples

#### List Connections Response
```json
{
  "status": "success",
  "connections": [
    {
      "id": 1,
      "name": "Production PostgreSQL",
      "source_type": "postgresql",
      "source_host": "db.example.com",
      "source_port": 5432,
      "source_database": "analytics",
      "connection_tested": true,
      "last_test_status": "success",
      "last_test_at": "2025-12-26T14:30:00Z",
      "jobs_count": 3
    },
    {
      "id": 2,
      "name": "GCS Data Lake",
      "source_type": "gcs",
      "bucket_path": "gs://data-lake-bucket",
      "connection_tested": false,
      "jobs_count": 1
    }
  ]
}
```

#### Test Connection Response (Success)
```json
{
  "status": "success",
  "message": "Connection successful. Found 15 tables.",
  "tables": [
    {"name": "customers", "row_count": 50000},
    {"name": "orders", "row_count": 1200000},
    {"name": "products", "row_count": 5000}
  ]
}
```

#### Test Connection Response (Duplicate Found)
```json
{
  "status": "success",
  "duplicate": true,
  "connection_id": 5,
  "connection_name": "Existing PostgreSQL Connection",
  "message": "Connection successful. This connection already exists."
}
```

#### Test Connection Response (Failure)
```json
{
  "status": "error",
  "message": "Connection failed: could not connect to server: Connection refused"
}
```

---

### JavaScript Functions

#### State Management
```javascript
// Global state
let allConnections = [];           // All connections from API
let connectionsCurrentPage = 1;     // Current pagination page
let connectionsSearchTerm = '';     // Current search filter

const ITEMS_PER_PAGE = 5;           // Items per page (configurable)
```

#### Core Functions

| Function | Purpose |
|----------|---------|
| `loadConnections()` | Fetch connections from API and populate `allConnections` |
| `renderConnectionsList()` | Render connection cards with pagination |
| `filterConnections(connections, term)` | Filter connections by search term |
| `handleConnectionsSearch()` | Handle search input with debounce |
| `goToConnectionsPage(page)` | Navigate to pagination page |
| `clearConnectionsSearch()` | Clear search and reset pagination |

#### Connection Testing

| Function | Purpose |
|----------|---------|
| `autoTestConnections(connections)` | Test all visible connections in background |
| `refreshConnections()` | Reload and re-test all connections |

#### CRUD Operations

| Function | Purpose |
|----------|---------|
| `openCreateConnectionModal()` | Open the create connection wizard |
| `closeCreateConnectionModal()` | Close the wizard modal |
| `openEditConnectionModal(id)` | Open edit modal for existing connection |
| `deleteConnection(id)` | Delete connection (with usage check) |
| `saveConnectionStandalone()` | Save new connection |

#### Wizard Navigation

| Function | Purpose |
|----------|---------|
| `goToConnStep(step)` | Navigate to wizard step (1 or 2) |
| `switchConnTab(tab)` | Switch between Relational/Storage/NoSQL tabs |
| `testAndProceed()` | Test connection and proceed to save |

---

### Connection Testing Logic

#### Test Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  User Clicks    │ --> │  API Call       │ --> │  Backend Test   │
│  "Test"         │     │  /test/         │     │  (socket + SQL) │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                        ┌─────────────────┐              │
                        │  Update UI      │ <────────────┘
                        │  (status dot)   │
                        └─────────────────┘
```

#### Backend Test Functions (`connection_manager.py`)

| Function | Source Type | What It Tests |
|----------|-------------|---------------|
| `test_postgresql()` | PostgreSQL | TCP connect + `SELECT 1` + list tables |
| `test_mysql()` | MySQL/MariaDB | TCP connect + `SELECT 1` + list tables |
| `test_bigquery()` | BigQuery | API auth + list tables in dataset |
| `test_firestore()` | Firestore | API auth + list collections |
| `test_gcs()` | GCS | List objects in bucket path |
| `test_s3()` | S3 | List objects in bucket path |
| `test_azure_blob()` | Azure Blob | List blobs in container |

#### Status Update Sequence

1. **On Page Load**: `autoTestConnections()` called for visible connections
2. **On Test Complete**: Status dot updated via DOM manipulation
3. **On Refresh Click**: All connections reloaded and retested

---

### Security Considerations

#### Credential Storage

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Credential Flow                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. User enters credentials in form                                         │
│     ↓                                                                        │
│  2. Frontend sends to Django API (HTTPS)                                    │
│     ↓                                                                        │
│  3. Django stores in Google Secret Manager                                  │
│     Secret name: "etl-conn-{model_id}-{connection_id}"                      │
│     ↓                                                                        │
│  4. Django stores secret reference in Connection model                      │
│     credentials_secret_name = "etl-conn-5-12"                               │
│                                                                              │
│  ⚠️ Raw passwords NEVER stored in Django database                           │
│  ⚠️ Service account JSON stored only in Secret Manager                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Duplicate Detection

When testing a new connection, the system checks for existing connections with:
- Same `source_type`
- Same `source_host`
- Same `source_port`
- Same `source_database`
- Same `source_username`

If found, user is prompted to use the existing connection instead.

---

### Error Handling

#### Connection Test Errors

| Error | Cause | User Message |
|-------|-------|--------------|
| Connection refused | Server down or firewall | "Connection refused. Check host/port." |
| Authentication failed | Wrong credentials | "Authentication failed. Check username/password." |
| Database not found | Wrong database name | "Database 'X' does not exist." |
| SSL required | Server requires SSL | "SSL connection required." |
| Timeout | Network issues | "Connection timed out. Check network." |
| Permission denied | Insufficient privileges | "Access denied. Check user permissions." |

#### Delete Protection

Connections cannot be deleted if:
- They are used by one or more ETL jobs

User sees: "Cannot delete connection: used by X ETL job(s). Delete or reassign those jobs first."

---

### Known Issues and Limitations

1. **No Connection Sharing Across Models**: Connections are scoped to a single ModelEndpoint. Cross-model sharing not yet implemented.

2. **No Connection Folders/Groups**: All connections displayed in flat list. For models with many connections, search and pagination help.

3. **Service Account JSON Stored in DB**: For BigQuery/GCS/Firestore, the service account JSON is currently stored in the model (encrypted). Migration to Secret Manager planned.

4. **No Connection Cloning**: Users cannot duplicate an existing connection. Must recreate manually.

---

### Future Enhancements

1. **Connection Templates**: Pre-configured connection templates for common setups
2. **Connection Health Dashboard**: Aggregate view of all connection statuses
3. **Scheduled Health Checks**: Automatic periodic testing of all connections
4. **Connection Import/Export**: Backup and restore connection configurations
5. **Role-Based Access**: Restrict connection management to admin users

---

## Sub-Chapter: ETL Jobs

### Purpose

ETL Jobs (also called DataSources) define data extraction pipelines that:
1. Extract data from a Connection (database, cloud storage, or NoSQL)
2. Load data into BigQuery tables
3. Run on-demand or on a schedule via Cloud Scheduler
4. Support both full replacement (Catalog) and incremental (Transactional) loads

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              ETL Job Execution Flow                                  │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐      ┌──────────────┐ │
│  │    User      │      │   Cloud      │      │   Django     │      │  Cloud Run   │ │
│  │  (Manual)    │      │  Scheduler   │      │   Webhook    │      │    Job       │ │
│  └──────┬───────┘      └──────┬───────┘      └──────┬───────┘      └──────┬───────┘ │
│         │                     │                     │                     │         │
│         │  Click "Run"        │  Cron trigger       │                     │         │
│         │─────────────────────│─────────────────────│───────────────────▶ │         │
│         │                     │                     │                     │         │
│         │                     │  POST /webhook      │  run_v2.run_job()   │         │
│         │                     │────────────────────▶│────────────────────▶│         │
│         │                     │                     │                     │         │
│         │                     │                     │   Create ETLRun     │         │
│         │                     │                     │   record (pending)  │         │
│         │                     │                     │                     │         │
│  ┌──────┴───────┐      ┌──────┴───────┐      ┌──────┴───────┐      ┌──────┴───────┐ │
│  │              │      │              │      │              │      │              │ │
│  │              │      │              │      │              │      │  ETL Runner  │ │
│  │              │      │              │      │              │      │  (main.py)   │ │
│  │              │      │              │      │              │      │              │ │
│  └──────────────┘      └──────────────┘      └──────────────┘      └──────┬───────┘ │
│                                                                           │         │
│                                                                           ▼         │
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │                         Processing Mode Decision                              │  │
│  │                                                                               │  │
│  │    ┌─────────────────────┐              ┌─────────────────────┐              │  │
│  │    │  Estimated Rows     │              │  Processing Mode    │              │  │
│  │    │  < 1,000,000        │─────────────▶│  STANDARD           │              │  │
│  │    │                     │              │  (Pandas + Cloud    │              │  │
│  │    │                     │              │   Run Job)          │              │  │
│  │    └─────────────────────┘              └─────────────────────┘              │  │
│  │                                                                               │  │
│  │    ┌─────────────────────┐              ┌─────────────────────┐              │  │
│  │    │  Estimated Rows     │              │  Processing Mode    │              │  │
│  │    │  >= 1,000,000       │─────────────▶│  DATAFLOW           │              │  │
│  │    │                     │              │  (Apache Beam +     │              │  │
│  │    │                     │              │   Dataflow)         │              │  │
│  │    └─────────────────────┘              └─────────────────────┘              │  │
│  │                                                                               │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Processing Modes

#### Standard Processing (Cloud Run Job)

For datasets **< 1 million rows**, uses:
- **Pandas** for data extraction and transformation
- **Cloud Run Job** (`etl-runner`) for execution
- **Batch loading** to BigQuery (10,000 rows per batch)

**Advantages:**
- Faster startup (no Dataflow worker spin-up)
- Lower cost for small datasets
- Simpler debugging

**Flow:**
```
Source DB/Storage ──▶ Pandas DataFrame ──▶ BigQuery Load Job ──▶ BigQuery Table
                     (in Cloud Run)        (batch upload)
```

#### Dataflow Processing (Apache Beam)

For datasets **>= 1 million rows**, uses:
- **Apache Beam** pipeline for distributed processing
- **Dataflow** workers for parallel execution
- **Native BigQuery I/O** for efficient loading

**Advantages:**
- Horizontal scaling for large datasets
- Parallel processing across multiple workers
- Handles datasets of any size

**Flow:**
```
Source DB/Storage ──▶ Apache Beam ──▶ Dataflow Workers ──▶ BigQuery (streaming)
                     (pipeline)      (auto-scaled)
```

#### Processing Mode Selection

| Mode | Setting | Behavior |
|------|---------|----------|
| Auto (default) | `processing_mode='auto'` | Estimate rows, use Dataflow if >= threshold |
| Standard | `processing_mode='standard'` | Always use Pandas + Cloud Run |
| Dataflow | `processing_mode='dataflow'` | Always use Apache Beam + Dataflow |

**Threshold:** Default 1,000,000 rows (configurable per table via `row_count_threshold`)

---

### Load Types

#### Catalog (Full Snapshot)

- **Replaces** all data in destination table
- Used for dimension/reference data that changes infrequently
- Example: Product catalog, customer master data

```
Source Table                    BigQuery Table
┌────────────────┐              ┌────────────────┐
│ products       │    REPLACE   │ products       │
│ - id           │ ──────────▶  │ - id           │
│ - name         │    ALL       │ - name         │
│ - price        │              │ - price        │
└────────────────┘              └────────────────┘
```

#### Transactional (Incremental/Append)

- **Appends** only new/changed records since last sync
- Uses timestamp column to track changes
- Tracks `last_sync_value` for next run

```
Source Table                    BigQuery Table
┌────────────────┐              ┌────────────────┐
│ orders         │    APPEND    │ orders         │
│ - id           │ ──────────▶  │ - id           │
│ - created_at   │    WHERE     │ - created_at   │
│ - amount       │ created_at > │ - amount       │
└────────────────┘ last_sync    └────────────────┘
```

---

### Data Model

#### DataSource (ETL Job)

```python
class DataSource(models.Model):
    # Parent references
    etl_config = ForeignKey(ETLConfiguration)
    connection = ForeignKey(Connection)       # Reusable connection

    # Identification
    name = CharField(max_length=255)          # "Daily Transactions Extract"
    source_type = CharField(max_length=50)    # Denormalized from connection

    # Status
    is_enabled = BooleanField(default=True)

    # Schedule
    schedule_type = CharField()               # 'manual', 'hourly', 'daily', 'weekly', 'monthly'
    cloud_scheduler_job_name = CharField()    # Full path to Cloud Scheduler job

    # Extraction settings
    use_incremental = BooleanField()
    incremental_column = CharField()
    last_sync_value = CharField()
    historical_start_date = DateField()

    # Last run tracking
    last_run_at = DateTimeField()
    last_run_status = CharField()             # 'completed', 'failed', 'running'
    last_run_message = TextField()

    # Timestamps
    created_at = DateTimeField()
    updated_at = DateTimeField()
```

#### DataSourceTable (Table Configuration)

```python
class DataSourceTable(models.Model):
    data_source = ForeignKey(DataSource)

    # Source configuration
    schema_name = CharField()                 # "public"
    source_table_name = CharField()           # "transactions"
    source_query = TextField()                # Custom SQL (optional)

    # Destination configuration
    dest_table_name = CharField()             # "transactions"
    dest_dataset = CharField()                # "raw_data"

    # Load strategy
    load_type = CharField()                   # 'transactional' or 'catalog'
    timestamp_column = CharField()            # For incremental loads
    historical_start_date = DateField()

    # Column selection
    selected_columns = JSONField()            # [] = all columns

    # File source configuration (GCS/S3/Azure)
    is_file_based = BooleanField()
    file_path_prefix = CharField()            # "data/transactions/"
    file_pattern = CharField()                # "*.csv"
    file_format = CharField()                 # 'csv', 'parquet', 'json'
    file_format_options = JSONField()         # delimiter, encoding, etc.
    column_mapping = JSONField()              # Original -> sanitized names

    # Processing configuration
    processing_mode = CharField()             # 'auto', 'standard', 'dataflow'
    row_count_threshold = IntegerField()      # Default: 1,000,000
    estimated_row_count = BigIntegerField()   # From last run

    # Schedule (per-table)
    schedule_type = CharField()
    schedule_time = TimeField()
    schedule_minute = IntegerField()          # For hourly
    schedule_day_of_week = IntegerField()     # 0-6 for weekly
    schedule_day_of_month = IntegerField()    # 1-31 for monthly
    schedule_timezone = CharField()           # Default: 'UTC'

    # Statistics
    last_row_count = IntegerField()
    last_synced_at = DateTimeField()
```

#### ETLRun (Execution History)

```python
class ETLRun(models.Model):
    # References
    etl_config = ForeignKey(ETLConfiguration)
    model_endpoint = ForeignKey(ModelEndpoint)
    data_source = ForeignKey(DataSource)

    # Status
    status = CharField()                      # 'pending', 'running', 'completed', 'failed'
    started_at = DateTimeField()
    completed_at = DateTimeField()

    # Cloud Run execution
    cloud_run_execution_id = CharField()

    # Progress tracking
    extraction_started_at = DateTimeField()
    extraction_completed_at = DateTimeField()
    loading_started_at = DateTimeField()
    loading_completed_at = DateTimeField()

    # Results
    total_sources = IntegerField()
    successful_sources = IntegerField()
    total_tables = IntegerField()
    successful_tables = IntegerField()
    total_rows_extracted = BigIntegerField()
    rows_loaded = BigIntegerField()
    bytes_processed = BigIntegerField()
    duration_seconds = IntegerField()

    # Details
    results_detail = JSONField()              # Per-table results
    error_message = TextField()
    logs_url = URLField()                     # Cloud Run logs

    triggered_by = ForeignKey(User)           # Null for scheduled runs
    created_at = DateTimeField()
```

#### ProcessedFile (File Tracking)

```python
class ProcessedFile(models.Model):
    """Tracks processed files for incremental file-based ETL"""
    data_source_table = ForeignKey(DataSourceTable)

    file_path = CharField()                   # Full path in storage
    file_size_bytes = BigIntegerField()
    file_last_modified = DateTimeField()
    rows_loaded = IntegerField()
    processed_at = DateTimeField()
    etl_run = ForeignKey(ETLRun)
```

---

### Cloud Services Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              GCP Services                                            │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │ Cloud Scheduler                                                              │    │
│  │ ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐              │    │
│  │ │ etl-job-5       │  │ etl-job-7       │  │ etl-job-14      │              │    │
│  │ │ Daily 09:00 UTC │  │ Weekly Mon 08:00│  │ Hourly :30      │              │    │
│  │ └────────┬────────┘  └────────┬────────┘  └────────┬────────┘              │    │
│  └──────────┼────────────────────┼────────────────────┼────────────────────────┘    │
│             │                    │                    │                              │
│             │  HTTP POST with OIDC token              │                              │
│             ▼                    ▼                    ▼                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │ Cloud Run Service (Django App)                                               │    │
│  │ ┌───────────────────────────────────────────────────────────────────────┐   │    │
│  │ │ Webhook Endpoint: /api/etl/sources/{id}/scheduler-webhook/            │   │    │
│  │ │                                                                        │   │    │
│  │ │ 1. Validate OIDC token                                                │   │    │
│  │ │ 2. Create ETLRun record (status='pending')                            │   │    │
│  │ │ 3. Trigger Cloud Run Job via run_v2.run_job()                         │   │    │
│  │ └───────────────────────────────────────────────────────────────────────┘   │    │
│  └──────────────────────────────────────┬──────────────────────────────────────┘    │
│                                         │                                            │
│                                         │ run_v2.run_job()                           │
│                                         ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │ Cloud Run Job: etl-runner                                                    │    │
│  │ ┌───────────────────────────────────────────────────────────────────────┐   │    │
│  │ │ Entry Point: python main.py --data_source_id=X --etl_run_id=Y         │   │    │
│  │ │                                                                        │   │    │
│  │ │ 1. Fetch job config from Django API                                   │   │    │
│  │ │ 2. Determine processing mode (standard vs dataflow)                   │   │    │
│  │ │ 3. Execute extraction + loading                                       │   │    │
│  │ │ 4. Update ETLRun status via Django API                                │   │    │
│  │ └───────────────────────────────────────────────────────────────────────┘   │    │
│  └──────────────────────────────────────┬──────────────────────────────────────┘    │
│                                         │                                            │
│             ┌───────────────────────────┼───────────────────────────┐                │
│             │                           │                           │                │
│             ▼                           ▼                           ▼                │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐          │
│  │ Source Database     │  │ Cloud Storage       │  │ BigQuery            │          │
│  │ (PostgreSQL, MySQL, │  │ (GCS, S3, Azure)    │  │ (Destination)       │          │
│  │  BigQuery, etc.)    │  │                     │  │                     │          │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘          │
│                                                                                      │
│                              FOR LARGE DATASETS (>= 1M rows):                        │
│                                         │                                            │
│                                         ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │ Dataflow                                                                     │    │
│  │ ┌───────────────────────────────────────────────────────────────────────┐   │    │
│  │ │ Apache Beam Pipeline                                                   │   │    │
│  │ │                                                                        │   │    │
│  │ │ Source ──▶ Transform ──▶ Partition ──▶ Load ──▶ BigQuery              │   │    │
│  │ │                                                                        │   │    │
│  │ │ Auto-scaled workers (n1-standard-2)                                   │   │    │
│  │ └───────────────────────────────────────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Cloud Scheduler Integration

#### Job Naming Convention

```
projects/{project_id}/locations/{region}/jobs/etl-job-{data_source_id}

Example:
projects/b2b-recs/locations/europe-central2/jobs/etl-job-14
```

#### Schedule Types and Cron Expressions

| Schedule Type | Example Config | Cron Expression |
|---------------|----------------|-----------------|
| Hourly | minute=30 | `30 * * * *` |
| Daily | time=09:00 | `0 9 * * *` |
| Weekly | day=1 (Mon), time=08:00 | `0 8 * * 1` |
| Monthly | day=15, time=06:00 | `0 6 15 * *` |

#### Webhook Payload

Cloud Scheduler sends:
```json
{
  "data_source_id": 14,
  "trigger": "scheduled"
}
```

#### OIDC Authentication

- Cloud Scheduler uses **OIDC token** for authentication
- Service account: `{project-number}-compute@developer.gserviceaccount.com`
- Audience: Django Cloud Run service URL

---

### ETL Runner Microservice

#### Directory Structure

```
etl_runner/
├── main.py                    # Entry point, ETLRunner class
├── config.py                  # Configuration management, Django API client
├── extractors/
│   ├── base.py               # Base extractor interface
│   ├── postgresql.py         # PostgreSQL extraction
│   ├── mysql.py              # MySQL extraction
│   ├── bigquery.py           # BigQuery extraction
│   ├── firestore.py          # Firestore extraction
│   └── file_extractor.py     # GCS/S3/Azure file extraction
├── loaders/
│   └── bigquery_loader.py    # BigQuery loading (batch + streaming)
├── dataflow_pipelines/
│   ├── etl_pipeline.py       # Apache Beam pipeline definitions
│   └── partitioning.py       # Work unit calculation for parallel processing
└── utils/
    ├── logging_config.py     # Structured JSON logging for Cloud Run
    └── error_handling.py     # Error handling and status updates
```

#### Entry Point Arguments

```bash
python main.py \
  --data_source_id=14 \
  --etl_run_id=567 \
  --log_level=INFO \
  --json_logs
```

#### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DJANGO_API_URL` | Django Cloud Run URL | `https://django-app-xxx.run.app` |
| `ETL_API_TOKEN` | API authentication token | `secret-token` |
| `GCP_PROJECT_ID` | GCP project | `b2b-recs` |
| `BIGQUERY_DATASET` | Default destination dataset | `raw_data` |
| `DATAFLOW_BUCKET` | GCS bucket for Dataflow temp files | `b2b-recs-dataflow` |
| `DATAFLOW_REGION` | Dataflow region | `europe-central2` |
| `ETL_BATCH_SIZE` | Rows per batch | `10000` |

---

### API Endpoints

#### ETL Job Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/models/{id}/etl/create-job/` | Create new ETL job |
| `GET` | `/api/etl/sources/{id}/` | Get ETL job details |
| `POST` | `/api/etl/sources/{id}/edit/` | Update ETL job |
| `POST` | `/api/etl/sources/{id}/delete/` | Delete ETL job |
| `POST` | `/api/etl/sources/{id}/toggle-pause/` | Pause/resume scheduler |

#### ETL Execution

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/etl/sources/{id}/run/` | Trigger manual run |
| `POST` | `/api/etl/sources/{id}/trigger/` | Trigger via API (internal) |
| `POST` | `/api/etl/sources/{id}/scheduler-webhook/` | Cloud Scheduler webhook |

#### ETL Runner APIs (Internal)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/etl/job-config/{id}/` | Get job configuration for runner |
| `PATCH` | `/api/etl/runs/{id}/update/` | Update run status/progress |
| `GET` | `/api/etl/sources/{id}/processed-files/` | Get processed files list |
| `POST` | `/api/etl/sources/{id}/record-processed-file/` | Record file as processed |

#### ETL Run Status

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/etl/runs/{id}/status/` | Get run status |

---

### User Interface

#### ETL Jobs List View

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ETL Jobs                                                [+ New ETL Job]    │
├─────────────────────────────────────────────────────────────────────────────┤
│ 🔍 [Search ETL jobs...                                                  ]  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ● Daily Transactions                                                    │ │
│ │   From: public.transactions                                             │ │
│ │   To: transactions                                                      │ │
│ │                                                                         │ │
│ │   Schedule: Daily at 09:00        Last run: 2 hours ago                │ │
│ │   Connection: Prod PostgreSQL     Status: Success                       │ │
│ │                                                                         │ │
│ │   [▶ Run] [⏸ Pause]              [Edit] [Delete]                        │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ○ Weekly Products Sync (PAUSED)                                         │ │
│ │   From: inventory.products                                              │ │
│ │   To: products                                                          │ │
│ │                                                                         │ │
│ │   Schedule: Weekly Mon 08:00      Last run: 5 days ago                 │ │
│ │   Connection: GCS Data Lake       Status: Success                       │ │
│ │                                                                         │ │
│ │   [▶ Run] [▶ Resume]             [Edit] [Delete]                        │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Showing 1-2 of 8 jobs                                                       │
│                                      [< Previous] [1] [2] [Next >]          │
└─────────────────────────────────────────────────────────────────────────────┘

Status Indicators:
● Green  = Enabled and running on schedule
○ Gray   = Paused or manual-only
● Red    = Last run failed
```

#### ETL Job Card Structure

Each job card displays 5 columns:
1. **Job Info**: Name, source → destination table mapping
2. **Schedule + Connection**: Schedule type/time, connection name
3. **Last Run Info**: When last ran, status
4. **Run Actions**: Run Now button, Pause/Resume button (if scheduled)
5. **Actions**: Edit and Delete buttons

---

### File Change Detection

For file-based sources (GCS, S3, Azure Blob), the ETL runner detects changes:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         File Change Detection Flow                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. Fetch previously processed files from ProcessedFile table               │
│     ┌──────────────────────────────────────────────────────────────────┐    │
│     │ ProcessedFile                                                     │    │
│     │ - file_path: gs://bucket/data/file1.csv                          │    │
│     │ - file_size_bytes: 1024000                                       │    │
│     │ - file_last_modified: 2025-12-25T10:00:00Z                       │    │
│     └──────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  2. List current files in cloud storage                                     │
│     ┌──────────────────────────────────────────────────────────────────┐    │
│     │ gs://bucket/data/                                                 │    │
│     │ - file1.csv (unchanged)                                          │    │
│     │ - file2.csv (NEW)                                                │    │
│     │ - file3.csv (MODIFIED - size changed)                            │    │
│     └──────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  3. Compare and determine action:                                           │
│                                                                              │
│     CATALOG mode: Any change detected → process ALL files                   │
│     TRANSACTIONAL mode: Process only NEW/MODIFIED files                     │
│                                                                              │
│  4. After processing, record files in ProcessedFile table                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Error Handling

#### Error Types

| Error Class | When Raised | Handling |
|-------------|-------------|----------|
| `ConfigurationError` | Invalid job config | Fail immediately, update status |
| `ExtractionError` | Source connection/query fails | Fail, log error details |
| `LoadError` | BigQuery loading fails | Fail, partial data may be loaded |

#### Status Updates

The ETL runner updates Django via API at:
1. **Start**: `status='running'`
2. **Progress**: Every 5 batches (rows extracted/loaded)
3. **Complete**: `status='completed'`, final row counts, duration
4. **Failure**: `status='failed'`, error message

#### Retry Logic

- Default: 3 retries with 5-second delay
- Applies to: Database connections, API calls
- Does NOT retry: Configuration errors, authentication failures

---

### Known Issues and Limitations

1. **No Job Dependencies**: Jobs run independently, cannot be chained
2. **Single Table per Run**: Each job processes one source → one destination
3. **No Data Validation**: Schema compatibility checked at creation, not runtime
4. **Dataflow Cold Start**: First Dataflow job in a session takes 2-3 minutes to start workers

---

### Future Enhancements

1. **Job Templates**: Pre-configured job templates for common patterns
2. **Job Chaining**: Run jobs in sequence (DAG-style)
3. **Data Quality Checks**: Row count validation, schema drift detection
4. **Alerting**: Email/Slack notifications on failure
5. **Cost Estimation**: Estimate Dataflow cost before running

---

## Chapter: ETL Jobs Dashboard

The ETL Jobs Dashboard provides operational visibility into ETL pipeline performance through summary KPIs and execution history.

### KPI Cards

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                         ETL Jobs Dashboard                                               │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │
│  │ ▶ 102        │  │ ✓ 89.2%     │  │ ✓ 91         │  │ ✗ 8          │  │ ≡ 164,101    │  │ ⏱ 37s    │ │
│  │   TOTAL RUNS │  │   SUCCESS   │  │   SUCCESSFUL │  │   FAILED     │  │   ROWS       │  │   AVG    │ │
│  │              │  │   RATE      │  │   RUNS       │  │   RUNS       │  │   MIGRATED   │  │   DURATION│ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘  └──────────┘ │
│       (blue)          (green)           (green)           (red)           (purple)         (blue)       │
│                                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

#### KPI Definitions

| KPI | Icon | Color | Description | Data Source |
|-----|------|-------|-------------|-------------|
| **Total Runs** | ▶ Play | Blue | Total number of ETL runs executed across all jobs | `COUNT(ETLRun)` |
| **Success Rate** | ✓ Check | Green | Percentage of runs that completed successfully | `(successful / total) × 100` |
| **Successful Runs** | ✓ Check | Green | Count of runs with `status='completed'` | `COUNT(ETLRun WHERE status='completed')` |
| **Failed Runs** | ✗ Cross | Red | Count of runs with `status='failed'` | `COUNT(ETLRun WHERE status='failed')` |
| **Rows Migrated** | ≡ Database | Purple | Total rows loaded across all successful runs | `SUM(ETLRun.rows_loaded)` |
| **Avg Duration** | ⏱ Clock | Blue | Average execution time of completed runs | `AVG(ETLRun.duration_seconds)` |

#### KPI Details

##### Total Runs
- **Purpose**: Provides overall volume indicator for ETL activity
- **Calculation**: Simple count of all `ETLRun` records for the current model/ETL configuration
- **Includes**: All runs regardless of status (pending, running, completed, failed)
- **Use Case**: Monitor ETL activity levels, detect unusual patterns (sudden drop or spike)

##### Success Rate
- **Purpose**: Primary health indicator for ETL pipelines
- **Calculation**: `(Successful Runs / Total Runs) × 100`
- **Format**: Displayed as percentage with one decimal place (e.g., "89.2%")
- **Thresholds**:
  - `>= 95%`: Healthy (green)
  - `80-95%`: Warning (yellow)
  - `< 80%`: Critical (red)
- **Use Case**: Quick assessment of pipeline reliability, SLA monitoring

##### Successful Runs
- **Purpose**: Absolute count of successful ETL executions
- **Criteria**: `ETLRun.status = 'completed'`
- **Use Case**: Paired with Total Runs to understand raw success volume

##### Failed Runs
- **Purpose**: Track failures requiring attention
- **Criteria**: `ETLRun.status = 'failed'`
- **Action**: Click to filter run history to failed runs only
- **Use Case**: Identify jobs needing investigation, track failure trends

##### Rows Migrated
- **Purpose**: Measure data throughput volume
- **Calculation**: `SUM(rows_loaded)` from all completed runs
- **Format**: Formatted with thousands separator (e.g., "164,101")
- **Use Case**: Capacity planning, verify data completeness, billing estimates

##### Avg Duration
- **Purpose**: Performance baseline for ETL jobs
- **Calculation**: `AVG(duration_seconds)` from completed runs
- **Format**: Displayed in seconds (e.g., "37s") or minutes for longer durations
- **Use Case**: Performance monitoring, detect degradation over time

---

### Data Aggregation

#### Time Scope

KPIs are calculated across **all historical runs** for the current ETL configuration. Future enhancement may add time-based filtering (last 7 days, last 30 days, etc.).

#### Query Logic

```python
# Backend calculation (ml_platform/etl/api.py)
def get_dashboard_stats(etl_config_id):
    runs = ETLRun.objects.filter(etl_config_id=etl_config_id)

    total_runs = runs.count()
    successful_runs = runs.filter(status='completed').count()
    failed_runs = runs.filter(status='failed').count()

    success_rate = (successful_runs / total_runs * 100) if total_runs > 0 else 0

    completed_runs = runs.filter(status='completed')
    rows_migrated = completed_runs.aggregate(Sum('rows_loaded'))['rows_loaded__sum'] or 0
    avg_duration = completed_runs.aggregate(Avg('duration_seconds'))['duration_seconds__avg'] or 0

    return {
        'total_runs': total_runs,
        'success_rate': round(success_rate, 1),
        'successful_runs': successful_runs,
        'failed_runs': failed_runs,
        'rows_migrated': rows_migrated,
        'avg_duration': int(avg_duration)
    }
```

---

### UI Implementation

#### Card Structure

Each KPI card follows a consistent structure:

```html
<div class="kpi-card">
    <div class="kpi-icon kpi-icon--{color}">
        <i class="fas fa-{icon}"></i>
    </div>
    <div class="kpi-content">
        <div class="kpi-value">{value}</div>
        <div class="kpi-label">{label}</div>
    </div>
</div>
```

#### Icon Mapping

| KPI | Font Awesome Icon | CSS Class |
|-----|-------------------|-----------|
| Total Runs | `fa-play` | `kpi-icon--blue` |
| Success Rate | `fa-check-circle` | `kpi-icon--green` |
| Successful Runs | `fa-check` | `kpi-icon--green` |
| Failed Runs | `fa-times-circle` | `kpi-icon--red` |
| Rows Migrated | `fa-database` | `kpi-icon--purple` |
| Avg Duration | `fa-clock` | `kpi-icon--blue` |

#### Responsive Behavior

- **Desktop (>1200px)**: 6 cards in single row
- **Tablet (768-1200px)**: 3 cards per row (2 rows)
- **Mobile (<768px)**: 2 cards per row (3 rows)

---

### Scheduled Jobs Table

The Scheduled Jobs table displays all ETL jobs configured with automated schedules, showing their next run time and current state.

#### Layout

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                         Dashboard Row 2                                                   │
├───────────────────────────────────────────────┬─────────────────────────────────────────────────────────┤
│                                               │                                                           │
│  📅 Scheduled Jobs                            │  ETL Job Runs (Last 5 Days)                             │
│  ┌───────────────────────────────────────┐   │                                                           │
│  │ Job Name    │ Schedule  │ Next Run    │   │              [Bubble Chart]                              │
│  │             │           │             │   │                                                           │
│  ├─────────────┼───────────┼─────────────┤   │                                                           │
│  │ Daily Trans │ Daily 09:00│ Dec 27, 09:00│  │                                                           │
│  │ Weekly Prod │ Mon 08:00 │ Dec 30, 08:00│  │                                                           │
│  │ Hourly Inv  │ Hourly :30│ Dec 26, 15:30│  │                                                           │
│  │ Monthly Rep │ 1st 06:00 │ Jan 1, 06:00 │  │                                                           │
│  │ Old Job     │ Daily 02:00│ — (Paused) │   │                                                           │
│  └───────────────────────────────────────┘   │                                                           │
│                                               │                                                           │
│  1-5 of 8    [Prev] [1] [2] [Next]           │                                                           │
│                                               │                                                           │
└───────────────────────────────────────────────┴─────────────────────────────────────────────────────────┘
```

#### Table Columns

| Column | Description | Data Source |
|--------|-------------|-------------|
| **Job Name** | ETL job name (truncated to 18 chars with tooltip) | `DataSource.name` |
| **Schedule** | Human-readable schedule (e.g., "Daily 09:00", "Mon 08:00") | Derived from schedule fields |
| **Next Run** | Next scheduled execution time in job's timezone | Cloud Scheduler API |
| **State** | Current scheduler state badge | Cloud Scheduler API |

#### State Badges

| State | Badge | Description |
|-------|-------|-------------|
| `ENABLED` | `✓ Enabled` (green) | Job is active and will run on schedule |
| `PAUSED` | `⏸ Paused` (gray) | Job is paused, next run shows "—" |
| `UNKNOWN` | Based on `is_enabled` | Could not fetch status from Cloud Scheduler |

#### Filtering and Sorting

Jobs are displayed in the following order:
1. **Enabled jobs first**: Sorted by `next_run_time` (soonest first)
2. **Paused jobs last**: Sorted alphabetically by name

#### Data Aggregation

```python
# Backend: ml_platform/etl/views.py

# 1. Get all scheduled data sources (non-manual with scheduler job)
scheduled_sources = data_sources.filter(
    schedule_type__in=['hourly', 'daily', 'weekly', 'monthly'],
    cloud_scheduler_job_name__isnull=False
).exclude(cloud_scheduler_job_name='')

# 2. For each source, fetch status from Cloud Scheduler API
for source in scheduled_sources:
    status = scheduler_manager.get_schedule_status(source.cloud_scheduler_job_name)
    next_run_time = status.get('next_run_time')
    state = status.get('state')  # 'ENABLED', 'PAUSED', etc.
    is_paused = (state == 'PAUSED')

# 3. Sort: enabled by next_run_time, paused alphabetically
enabled_jobs.sort(key=lambda x: x['next_run_time'])
paused_jobs.sort(key=lambda x: x['name'].lower())
scheduled_jobs_list = enabled_jobs + paused_jobs
```

#### Schedule Display Format

| Schedule Type | Display Format | Example |
|---------------|----------------|---------|
| Hourly | `Hourly :MM` | "Hourly :30" |
| Daily | `Daily HH:MM` | "Daily 09:00" |
| Weekly | `DAY HH:MM` | "Mon 08:00" |
| Monthly | `Nth HH:MM` | "15th 06:00" |

#### Pagination

- **Items per page**: 5
- **URL parameter**: `sched_page`
- **Shows**: "1-5 of 8" format with Previous/Next navigation

#### Empty State

When no scheduled jobs exist:
```
┌─────────────────────────────────────┐
│      📅                              │
│      No scheduled jobs              │
│      Create ETL jobs with           │
│      schedules to see them here     │
└─────────────────────────────────────┘
```

---

### ETL Job Runs Bubble Chart

The bubble chart provides a visual timeline of ETL job executions over the last 5 days, with bubble attributes encoding run metadata.

#### Chart Layout

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ETL Job Runs (Last 5 Days)                    ● Success  ● Partial  ● Failed  │ ● Data  ○ No data      │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                          │
│                       Dec 22        Dec 23        Dec 24        Dec 25        Dec 26                    │
│                          │             │             │             │             │                       │
│  Daily Transactions ─────●─────────────●─────────────●─────────────●─────────────●────                  │
│                         (lg)          (lg)          (lg)          (lg)          (md)                    │
│                                                                                                          │
│  Weekly Products ────────────────────────────────────────────────────●─────────────────                  │
│                                                                     (sm)                                 │
│                                                                                                          │
│  Hourly Inventory ───────○───○───○───○───○───○───○───○───○───●───●───●───●───●───●───●                  │
│                         (xs) ...                              (xs) ...                                   │
│                                                                                                          │
│  Monthly Report ─────────────────────────────────────────────────────────────────────────                │
│                                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘

Legend:
  ● Filled bubble = Rows were loaded (data transferred)
  ○ Hollow bubble = No data loaded (0 rows)
  Bubble size = Duration (larger = longer running)
  Color: Green = Success, Orange = Partial, Red = Failed
```

#### Visual Encoding

| Attribute | Encoding | Description |
|-----------|----------|-------------|
| **X Position** | Time | When the run started (5-day range) |
| **Y Position** | Job Name | Which ETL job was executed |
| **Bubble Size** | Duration | Execution time in seconds (scaled min→max to 4px→14px radius) |
| **Bubble Color** | Status | `completed`=green, `partial`=orange, `failed`=red |
| **Bubble Fill** | Data Loaded | Filled=rows loaded, Hollow=no data (0 rows) |

#### Status Color Mapping

| Status | Color | Hex | Condition |
|--------|-------|-----|-----------|
| Success | Green | `#22C55E` | `status='completed'` |
| Partial | Orange | `#FB923C` | `status='completed'` but partial success |
| Failed | Red | `#EF4444` | `status='failed'` |

#### Bubble Size Scale

```javascript
// Size is scaled based on duration relative to all runs in the 5-day window
const minRadius = 4;   // Minimum bubble radius (px)
const maxRadius = 14;  // Maximum bubble radius (px)

// Linear scale from min to max duration
const sizeScale = d3.scaleLinear()
    .domain([durationStats.min, durationStats.max])
    .range([minRadius, maxRadius])
    .clamp(true);
```

#### Data Structure

```javascript
// bubble_chart_data passed from Django to JavaScript
{
    "runs": [
        {
            "job_name": "Daily Transactions",
            "started_at": "2025-12-26T09:00:00+00:00",
            "duration": 37,        // seconds
            "status": "completed", // or "failed", "partial"
            "rows_loaded": 15420
        },
        // ... more runs
    ],
    "job_names": ["Daily Transactions", "Hourly Inventory", "Weekly Products"],
    "date_range": {
        "start": "2025-12-22T00:00:00+00:00",
        "end": "2025-12-26T23:59:59+00:00"
    },
    "duration_stats": {
        "min": 12,   // shortest run in seconds
        "max": 145   // longest run in seconds
    }
}
```

#### Tooltip

On hover, each bubble displays a tooltip with:
```
┌────────────────────────────────┐
│ Daily Transactions             │
│ Dec 26, 09:00                  │
│ Duration: 37s                  │
│ Rows: 15,420                   │
│ Status: ✓ Completed            │
└────────────────────────────────┘
```

#### Chart Dimensions

| Property | Value | Notes |
|----------|-------|-------|
| Container width | 100% | Responsive to parent |
| Chart height | 260px | Fixed for consistent layout |
| Margins | `{ top: 15, right: 30, bottom: 40, left: 130 }` | Left margin for job names |
| Y-axis | Categorical (job names) | Uses `d3.scaleBand()` |
| X-axis | Time scale (5 days) | Uses `d3.scaleTime()` |

#### Rendering Library

Uses **D3.js** for SVG rendering with the following components:
- `d3.scaleTime()` for X-axis
- `d3.scaleBand()` for Y-axis (job names)
- `d3.scaleLinear()` for bubble size
- Custom tooltip positioning

#### Empty State

When no runs exist in the last 5 days:
```
┌─────────────────────────────────────┐
│           📊                         │
│      No job runs                    │
│      Run ETL jobs to see            │
│      visualization                   │
└─────────────────────────────────────┘
```

#### Loading State

During data fetch:
```
┌─────────────────────────────────────┐
│      ⟳ Loading chart...             │
└─────────────────────────────────────┘
```

#### Responsive Behavior

- Chart width adjusts to container width on window resize
- Debounced re-render (250ms delay) to prevent excessive redraws
- Job name labels truncated on smaller screens

---

### Recent Runs Table

The Recent Runs table provides a detailed history of ETL job executions with client-side filtering, search, and pagination.

#### Layout

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Recent Runs                                                                                              │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                          │
│  🔍 [Search by job name...        ]  [✕ Clear Filters]         Status: [Completed] [Failed] [Cancelled] │
│                                                                                                          │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  Run ID │ ETL Job           │ Connection         │ Status    │ Started         │ Duration │ Rows  │ Act │
├─────────┼───────────────────┼────────────────────┼───────────┼─────────────────┼──────────┼───────┼─────┤
│  #567   │ Daily Transactions│ 🐘 Prod PostgreSQL │ ✓ Completed│ Dec 26, 9:00 AM│ 37s      │ 15,420│ View│
│  #566   │ Weekly Products   │ ☁️ GCS Data Lake   │ ✓ Completed│ Dec 25, 8:00 AM│ 145s     │ 5,230 │ View│
│  #565   │ Hourly Inventory  │ 🐘 Prod PostgreSQL │ ✗ Failed   │ Dec 26, 2:30 PM│ 12s      │ 0     │ View│
│  #564   │ Monthly Report    │ ☁️ BigQuery        │ ⊘ Cancelled│ Dec 24, 6:00 AM│ —        │ 0     │ View│
│  #563   │ Daily Transactions│ 🐘 Prod PostgreSQL │ ✓ Completed│ Dec 25, 9:00 AM│ 42s      │ 14,892│ View│
│  #562   │ Hourly Inventory  │ 🐘 Prod PostgreSQL │ ⚠ Partial  │ Dec 24, 3:30 PM│ 28s      │ 3,100 │ View│
├─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  Showing 1-6 of 102 runs                                    [Previous] [1] [2] ... [17] [Next]          │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

#### Table Columns

| Column | Width | Description | Data Source |
|--------|-------|-------------|-------------|
| **Run ID** | 8% | Unique run identifier prefixed with # | `ETLRun.id` |
| **ETL Job** | 15% | Job name (truncated with tooltip) | `ETLRun.data_source.name` |
| **Connection** | 18% | Source type icon + connection name | `DataSource.connection.name` |
| **Status** | 12% | Status badge with icon | `ETLRun.status` |
| **Started** | 17% | Start timestamp (e.g., "Dec 26, 9:00 AM") | `ETLRun.started_at` |
| **Duration** | 10% | Execution time in seconds (or "—") | `ETLRun.duration_seconds` |
| **Rows** | 8% | Rows extracted with thousands separator | `ETLRun.total_rows_extracted` |
| **Actions** | 12% | "View Details" link | Opens run details modal |

#### Status Badges and Row Colors

| Status | Badge | Icon | Text Color | Row Background |
|--------|-------|------|------------|----------------|
| `completed` | `✓ Completed` | `fa-check-circle` | Green (`text-green-700`) | `bg-green-50` |
| `failed` | `✗ Failed` | `fa-times-circle` | Red (`text-red-700`) | `bg-red-50` |
| `cancelled` | `⊘ Cancelled` | `fa-ban` | Gray (`text-gray-600`) | `bg-gray-50` |
| `running` | `↻ Running` | `fa-spinner fa-spin` | Blue (`text-blue-700`) | `bg-blue-50` |
| `partial` | `⚠ Partial` | `fa-exclamation-triangle` | Yellow (`text-yellow-700`) | `bg-yellow-50` |
| `pending` | `⏱ Pending` | `fa-clock` | Gray (`text-gray-600`) | `bg-gray-50` |

#### Connection Type Icons

| Source Type | Icon | Color |
|-------------|------|-------|
| `postgresql` | 🐘 Elephant | Blue (`text-blue-600`) |
| `mysql` | Database | Orange (`text-orange-500`) |
| `bigquery` | Cloud | Blue (`text-blue-500`) |
| `gcs` | Cloud Upload | Yellow (`text-yellow-500`) |
| `s3` | AWS Logo | Orange (`text-orange-600`) |
| `firestore` | Fire | Yellow (`text-yellow-600`) |

---

#### Filter Controls

##### Search Input

- **Placeholder**: "Search by job name..."
- **Behavior**: Debounced search (200ms delay), immediate on Enter
- **Filter logic**: Case-insensitive substring match on `job_name`

##### Status Filter Buttons

Three toggle buttons for filtering by run status:

| Button | Default Style | Selected Style |
|--------|--------------|----------------|
| **Completed** | `bg-green-100 text-green-700` | `bg-green-500 text-white` |
| **Failed** | `bg-red-100 text-red-700` | `bg-red-500 text-white` |
| **Cancelled** | `bg-gray-200 text-gray-700` | `bg-gray-500 text-white` |

- **Multi-select**: Multiple statuses can be selected (OR logic)
- **Toggle behavior**: Click to select/deselect

##### Clear Filters Button

- **Visibility**: Hidden by default, shown when any filter is active
- **Action**: Clears search input and all status filters

---

#### Client-Side Filtering

The Recent Runs table uses **client-side filtering** for fast, responsive interaction.

```javascript
// Global state
let allRunsData = [];          // All runs from last 30 days (from embedded JSON)
let filteredRunsData = [];     // Runs matching current filters
let runsCurrentPage = 1;
const runsPerPage = 6;
let runsActiveStatuses = [];   // ['completed', 'failed', etc.]
let runsSearchQuery = '';

// Filter logic
filteredRunsData = allRunsData.filter(run => {
    // Search filter (case-insensitive)
    if (runsSearchQuery) {
        if (!run.job_name.toLowerCase().includes(runsSearchQuery.toLowerCase())) {
            return false;
        }
    }

    // Status filter (OR logic - match any selected status)
    if (runsActiveStatuses.length > 0) {
        if (!runsActiveStatuses.includes(run.status)) {
            return false;
        }
    }

    return true;
});
```

#### Data Structure

```javascript
// all_runs_json embedded in page (last 30 days)
[
    {
        "id": 567,
        "job_name": "Daily Transactions",
        "source_type": "postgresql",
        "connection_name": "Prod PostgreSQL",
        "status": "completed",
        "started_at": "2025-12-26T09:00:00+00:00",
        "duration_seconds": 37,
        "rows_extracted": 15420
    },
    // ... more runs
]
```

---

#### Data Scope

- **Time window**: Last 30 days (configurable in backend)
- **Query filter**: `started_at >= (now - 30 days) OR started_at IS NULL` (includes pending runs)
- **Status sync**: Running/pending runs are synchronized with Cloud Run status on page load

---

#### Pagination

- **Items per page**: 6
- **Page navigation**: Previous/Next buttons + page number links
- **Smart pagination**: Shows ellipsis for large page counts (e.g., [1] ... [5] [6] [7] ... [17])
- **Shows**: "Showing 1-6 of 102 runs" with "(filtered)" indicator when filters active

---

#### Empty States

Three distinct empty states based on context:

| Condition | Icon | Title | Subtitle |
|-----------|------|-------|----------|
| No runs ever | `fa-inbox` | "No ETL runs yet" | (empty) |
| Filters active, no matches | `fa-filter` | "No runs match your filters" | "Try adjusting your search or status filters" |
| Runs exist but none in 30 days | `fa-calendar-times` | "No runs in last 30 days" | "All recent ETL runs are older than 30 days" |

---

#### View Details Action

Clicking "View Details" opens a modal with comprehensive run information:

```
┌─────────────────────────────────────────────────────────────────┐
│ ETL Run #567 Details                                        [X] │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Job: Daily Transactions                                        │
│  Connection: Prod PostgreSQL (postgresql)                       │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Status      │ ✓ Completed                                │   │
│  │ Started     │ Dec 26, 2025 9:00:00 AM                   │   │
│  │ Completed   │ Dec 26, 2025 9:00:37 AM                   │   │
│  │ Duration    │ 37 seconds                                 │   │
│  │ Rows        │ 15,420                                     │   │
│  │ Bytes       │ 2.4 MB                                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Error Message: (none)                                          │
│                                                                  │
│  [View Cloud Run Logs]                              [Close]     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Known Issues and Fixes

This section documents bugs discovered during ETL system usage and their fixes.

### Issue #1: Dataflow Jobs Reporting 0 Rows (Fixed 2025-12-26)

**Symptoms:**
- ETL jobs using Dataflow completed successfully (data was loaded to BigQuery)
- But the UI showed "Rows Extracted: 0, Rows Loaded: 0"
- Logs showed: `Failed to wait for Dataflow completion: cannot import name 'dataflow_v1beta3' from 'google.cloud'`

**Root Cause:**
1. Missing `google-cloud-dataflow-client` package in `etl_runner/requirements.txt`
2. No fallback logic when Dataflow API calls failed

**Fix Applied:**
1. Added `google-cloud-dataflow-client>=0.8.6` to ETL runner requirements
2. Added fallback logic in `main.py` to use estimated row counts when API fails:
   ```python
   # Use estimated rows as fallback if Dataflow API failed or returned 0
   effective_rows = final_rows_loaded
   if final_rows_loaded == 0 and estimated_rows > 0:
       effective_rows = estimated_rows
   ```
3. Added retry logic (3 attempts) for Dataflow client initialization and job listing

**Files Modified:**
- `etl_runner/requirements.txt` - Added dependency
- `etl_runner/main.py` - Added fallback logic and retry handling in `run_with_dataflow()` and `_wait_for_dataflow_completion()`

---

### Issue #2: Incorrect ETL Run Status for Dataflow Jobs (Fixed 2025-12-26)

**Symptoms:**
- UI showed "Dataflow failed with errors" when Dataflow was still running
- Status was incorrectly updated based on Cloud Run execution status, not Dataflow job status

**Root Cause:**
- `sync_running_etl_runs_with_cloud_run()` in `views.py` synced with Cloud Run execution status
- Cloud Run completes quickly after submitting a Dataflow job
- If Cloud Run showed any error, the ETL run was marked as failed even though Dataflow was still running successfully

**Fix Applied:**
1. Added `dataflow_job_id` field to `ETLRun` model to track Dataflow jobs separately
2. Created new `sync_running_etl_runs_with_dataflow()` function that queries Dataflow API directly
3. Updated `model_etl` view to prioritize Dataflow status sync over Cloud Run sync

**Files Modified:**
- `ml_platform/models.py` - Added `dataflow_job_id` field to `ETLRun`
- `ml_platform/migrations/0040_add_dataflow_job_id_to_etlrun.py` - Migration for new field
- `ml_platform/etl/views.py` - Added `sync_running_etl_runs_with_dataflow()` function
- `ml_platform/etl/api.py` - Updated `run_update()` and `run_status()` to handle `dataflow_job_id`
- `etl_runner/main.py` - Pass `dataflow_job_id` in result and status updates
- `etl_runner/config.py` - Updated docstring for `dataflow_job_id` parameter

**New Field Schema:**
```python
class ETLRun(models.Model):
    # ... existing fields ...
    dataflow_job_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Dataflow job ID for large-scale ETL runs (used for accurate status tracking)"
    )
```

---

### Issue #3: Scheduler Job Not Appearing in UI (Analyzed 2025-12-26)

**Symptoms:**
- When creating a job with "run immediately" checked, the scheduler didn't appear in "Scheduled Jobs" table
- Scheduler appeared only after page refresh post job completion

**Analysis:**
- Investigation confirmed the scheduler **was** created at job creation time (verified in logs)
- The issue was timing - the page may have been loaded before `cloud_scheduler_job_name` was saved
- **This is not a code bug** - it's a normal page refresh timing issue

**Recommendation:**
- Consider adding real-time updates to the scheduled jobs table (WebSocket or polling)
- No code fix required

---

### Issue #4: Schema Detection 1GB File Size Limit (Fixed 2025-12-26)

**Symptoms:**
- ETL wizard refused to detect schema for CSV files larger than 1GB
- Error message: "File size (3.74 GB) exceeds 1GB limit"
- Files were visible in the wizard but "Detect Schema" button failed

**Root Cause:**
- Hardcoded 1GB limit in `detect_file_schema()` function in `ml_platform/connections/api.py`
- The limit was unnecessary because schema detection only downloads first 5MB of the file
- This was defensive code added before Dataflow support was implemented

**Fix Applied:**
Removed the arbitrary 1GB file size check. The 5MB sample download was already safe for files of any size:

```python
# REMOVED:
if file_size > 1024 * 1024 * 1024:  # 1GB
    return JsonResponse({'status': 'error', 'message': f'File size exceeds 1GB limit'})

# KEPT (already safe):
max_bytes_to_download = min(file_size, 5 * 1024 * 1024)  # 5MB max
file_content = blob.download_as_bytes(end=max_bytes_to_download)
```

**Files Modified:**
- `ml_platform/connections/api.py` - Removed 1GB limit in `detect_file_schema()` (lines 1330-1334)

---

### Issue #5: Dataflow Worker OOM with Large CSV Files (Fixed 2025-12-26)

**Symptoms:**
- Dataflow jobs failed when processing large CSV files (4GB+)
- Error: "Timed out waiting for an update from the worker"
- Error: "The worker has been reported dead"
- Jobs failed after 4 retry attempts

**Root Cause:**
The Dataflow pipeline used **pandas inside workers** to process files, which loaded entire files into memory:

```python
# OLD (broken) - in UnifiedExtractor._process_file():
df = extractor.extract_file(file_path)  # Downloads entire 4GB file
for _, row in df.iterrows():            # Requires 12-15GB RAM
    yield row
```

For a 4GB CSV file:
- Pandas needs ~12-15GB RAM to load and parse
- Workers were configured with `n1-standard-2` (7.5GB RAM)
- Workers ran out of memory and were killed

**Fix Applied:**
Implemented **native Beam I/O** for file sources, replacing pandas with streaming:

1. **New `ParseCSVLine` DoFn** - Parses CSV lines using Python's `csv` module (handles quotes, escapes)
2. **New `ParseJSONLine` DoFn** - Parses JSON lines using `json.loads()`
3. **New `run_file_pipeline()` function** - Uses `beam.io.ReadFromText` for streaming

```python
# NEW (fixed) - Native Beam I/O:
pipeline
| 'ReadCSV' >> beam.io.ReadFromText(
    file_pattern='gs://bucket/file.csv',
    skip_header_lines=1
)
# Beam automatically splits into ~64MB bundles
# Each worker processes bundles in parallel
# Memory usage: ~100-200MB per worker (not 12GB!)

| 'ParseCSVLines' >> beam.ParDo(ParseCSVLine(column_names=schema_columns))
| 'SerializeValues' >> beam.Map(...)
| 'WriteToBigQuery' >> WriteToBigQuery(...)
```

**Key Benefits:**
| Aspect | Before | After |
|--------|--------|-------|
| Memory per worker | 12-15GB | ~100-200MB |
| File size limit | ~2GB | Unlimited |
| Processing model | Load entire file | Stream line-by-line |
| File splitting | Manual | Automatic (~64MB bundles) |

**Pipeline Selection Logic:**
```python
# In main.py run_with_dataflow():
if source_type == 'bigquery':
    run_bigquery_native_pipeline(...)  # Native BigQuery I/O
elif is_file_source:
    run_file_pipeline(...)             # NEW - Native Beam I/O
else:
    run_scalable_pipeline(...)         # Database sources
```

**Error Handling:**
- Bad CSV records (parsing errors, field count mismatch) are skipped and logged
- Skipped records are counted in Dataflow metrics (visible in GCP Console)
- Pipeline continues processing valid records

**Files Modified:**
- `etl_runner/dataflow_pipelines/etl_pipeline.py`:
  - Added `ParseCSVLine` DoFn (lines 297-381)
  - Added `ParseJSONLine` DoFn (lines 384-443)
  - Added `run_file_pipeline()` function (lines 1343-1575)
  - Added imports for `csv` and `io` modules
- `etl_runner/main.py`:
  - Updated `run_with_dataflow()` to use `run_file_pipeline()` for file sources
  - Added full GCS path construction from bucket name and file paths

---

### Issue #6: CSV Column Mapping and TIMESTAMP Parsing Failures (Fixed 2025-12-27)

**Symptoms:**
- Dataflow job fails with: "JSON table encountered too many errors, giving up. Rows: 1; errors: 1"
- Error occurs at BigQuery FILE_LOADS stage (not during CSV parsing)
- All rows fail with the same error

**Root Causes:**

1. **Empty `column_mapping` for legacy ETL jobs:**
   - The `column_mapping` field was added to `DataSourceTable` model after some ETL jobs were created
   - Legacy jobs have `column_mapping = NULL`
   - When empty, the code fell back to BigQuery schema column order (wrong order for CSV positional parsing)

2. **Time-only values in TIMESTAMP columns:**
   - CSV had `invoice_time` column with values like `"18:53:06"` (time only, no date)
   - BigQuery TIMESTAMP requires full datetime format
   - The `SchemaAwareConverter` only handled date-only strings (`"YYYY-MM-DD"`), not time-only

3. **Extra CSV columns not in BigQuery schema:**
   - CSV may have more columns than BigQuery table (user selected subset in wizard)
   - All CSV columns were included in JSON output, causing BigQuery load failures

**Solution:**

1. **Read CSV header at runtime (`read_csv_header_from_gcs`):**
   ```python
   # Read first 64KB from GCS file to get header
   # Parse with csv.reader for proper handling of quoted fields
   # Returns column names in correct file order
   ```

2. **Smart column matching (`apply_column_mapping`):**
   ```python
   # If column_mapping exists: use it
   # If empty: match CSV columns to BigQuery schema by sanitized name
   # Fuzzy matching handles "CHANNEL_DESC" -> "channel_desc"
   ```

3. **Filter to BigQuery schema columns:**
   ```python
   # After parsing, remove any columns not in BigQuery schema
   | 'FilterToSchemaColumns' >> beam.Map(
       lambda row, keep_cols=columns_to_keep: {k: v for k, v in row.items() if k in keep_cols}
   )
   ```

4. **Handle time-only TIMESTAMP values:**
   ```python
   # In SchemaAwareConverter:
   # "18:53:06" (time-only) -> "1970-01-01T18:53:06"
   # "2024-02-22" (date-only) -> "2024-02-22T00:00:00"
   ```

**Files Modified:**
- `etl_runner/dataflow_pipelines/etl_pipeline.py`:
  - Added `read_csv_header_from_gcs()` function (lines 384-478)
  - Added `apply_column_mapping()` function with BQ schema fallback (lines 481-547)
  - Updated `run_file_pipeline()` to read header and filter columns (lines 1591-1617)
  - Added `FilterToSchemaColumns` pipeline step (lines 1757-1761)
  - Enhanced `SchemaAwareConverter` for time-only timestamps (lines 268-285)

**Verification:**
```bash
# Check CSV header
gsutil cat -r 0-500 gs://bucket/file.csv | head -1

# Check BigQuery schema
bq show --schema --format=prettyjson project:dataset.table

# Check ETL job config
python manage.py shell -c "
from ml_platform.models import DataSourceTable
t = DataSourceTable.objects.get(dest_table_name='table_name')
print(f'column_mapping: {t.column_mapping}')
print(f'selected_columns: {t.selected_columns}')
"
```

**Prevention:**
- New ETL jobs created after fix will have `column_mapping` populated
- Consider backfilling `column_mapping` for existing jobs
- Add validation in wizard for ambiguous timestamp formats

---

## Files Reference

### Backend Files

| File | Purpose |
|------|---------|
| `ml_platform/models.py` | Connection, DataSource, DataSourceTable, ETLRun, ProcessedFile models |
| `ml_platform/connections/urls.py` | Connection API URL routes |
| `ml_platform/connections/api.py` | Connection API endpoint handlers |
| `ml_platform/etl/urls.py` | ETL API URL routes |
| `ml_platform/etl/api.py` | ETL job API endpoint handlers |
| `ml_platform/etl/views.py` | ETL page view |
| `ml_platform/etl/webhooks.py` | Cloud Scheduler webhook handler |
| `ml_platform/utils/connection_manager.py` | Connection testing and metadata fetching |
| `ml_platform/utils/cloud_scheduler.py` | Cloud Scheduler management |

### ETL Runner Microservice

| File | Purpose |
|------|---------|
| `etl_runner/main.py` | Entry point, ETLRunner orchestrator class |
| `etl_runner/config.py` | Configuration management, Django API client |
| `etl_runner/extractors/postgresql.py` | PostgreSQL data extraction |
| `etl_runner/extractors/mysql.py` | MySQL data extraction |
| `etl_runner/extractors/bigquery.py` | BigQuery data extraction |
| `etl_runner/extractors/firestore.py` | Firestore data extraction |
| `etl_runner/extractors/file_extractor.py` | GCS/S3/Azure file extraction |
| `etl_runner/loaders/bigquery_loader.py` | BigQuery loading (batch + streaming) |
| `etl_runner/dataflow_pipelines/etl_pipeline.py` | Apache Beam pipeline definitions |
| `etl_runner/dataflow_pipelines/partitioning.py` | Work unit calculation for parallel processing |
| `etl_runner/utils/logging_config.py` | Structured JSON logging |
| `etl_runner/utils/error_handling.py` | Error handling and status updates |

### Frontend Files

| File | Purpose |
|------|---------|
| `templates/ml_platform/model_etl.html` | Main ETL page template |
| `static/css/cards.css` | Card styling for connections/jobs |
| `static/css/modals.css` | Modal styling for wizards |

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| v8 | 2025-12-27 | Added Issue #6 (CSV column mapping and TIMESTAMP parsing fixes for Dataflow) |
| v7 | 2025-12-26 | Added Issue #4 (1GB schema limit) and Issue #5 (Dataflow OOM fix with native Beam I/O) |
| v6 | 2025-12-26 | Added Known Issues and Fixes section (Dataflow row count, status tracking) |
| v5 | 2025-12-26 | Added Recent Runs table documentation |
| v4 | 2025-12-26 | Added Scheduled Jobs table and Bubble Chart documentation |
| v3 | 2025-12-26 | Added ETL Jobs Dashboard chapter with KPI documentation |
| v2 | 2025-12-26 | Added ETL Jobs sub-chapter with full documentation |
| v1 | 2025-12-26 | Initial documentation for Connections sub-chapter |
