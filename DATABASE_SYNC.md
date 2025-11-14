# Setting Up Laptop to Use Cloud SQL PostgreSQL

**Last Updated**: November 14, 2025

This guide helps you configure your **laptop** to connect to the same Cloud SQL PostgreSQL database that the desktop is using.

---

## Overview

**What Changed on Desktop (November 14, 2025)**:
- Migrated from SQLite to Cloud SQL PostgreSQL
- Database is now shared across all machines
- Real-time data synchronization
- No more manual exports/imports

**What You Need to Do on Laptop**:
- Pull latest code from GitHub
- Install dependencies
- Configure database connection (.env file)
- Start development environment

---

## Cloud SQL Database Details

**Instance Information**:
- **Project**: `memo2-456215` (not b2b-recs)
- **Instance Name**: `memo2-db`
- **Region**: `europe-central2`
- **Connection Name**: `memo2-456215:europe-central2:memo2-db`
- **PostgreSQL Version**: 13.22

**Database Details**:
- **Database Name**: `b2b_recs_dev`
- **Username**: `django_user`
- **Password**: `B2BRecs2025_Dev_Secure!`
- **Connection**: Via Cloud SQL Proxy on port `5433`

**Why This Database?**:
- Cost savings: Reusing existing Cloud SQL instance
- No additional $10/month charge
- Instance already running for memo2 project

---

## Step-by-Step Setup Instructions

### Step 1: Stop Any Running Django Server

On your laptop:

```bash
# Stop Django if it's running
pkill -f "manage.py runserver"

# Stop cloud-sql-proxy if it's running
pkill -f "cloud-sql-proxy"
```

---

### Step 2: Pull Latest Code from GitHub

```bash
cd /path/to/b2b_recs
git pull origin main
```

**Expected changes**:
- `config/settings.py` - Updated with PostgreSQL support
- `requirements.txt` - New dependencies (psycopg2-binary, python-dotenv)
- `README.md` - Updated documentation
- `.env.example` - Template for environment variables
- `start_dev.sh` - Already includes Cloud SQL Proxy
- `stop_dev.sh` - Already includes Cloud SQL Proxy

---

### Step 3: Activate Virtual Environment and Install Dependencies

```bash
source venv/bin/activate
pip install -r requirements.txt
```

**New dependencies installed**:
- `Django==4.2.26` (downgraded from 5.2 for PostgreSQL 13 compatibility)
- `psycopg2-binary==2.9.11` (PostgreSQL adapter)
- `python-dotenv==1.2.1` (environment variable management)

---

### Step 4: Create .env File with Database Credentials

```bash
# Copy the example file
cp .env.example .env
```

Now edit the `.env` file and add the database password:

```bash
# Open in your editor
nano .env
# or
code .env
# or
vim .env
```

**Content of .env file**:

```bash
# Django Database Configuration
# Cloud SQL PostgreSQL via cloud-sql-proxy

DB_ENGINE=postgresql
DB_NAME=b2b_recs_dev
DB_USER=django_user
DB_PASSWORD=B2BRecs2025_Dev_Secure!
DB_HOST=127.0.0.1
DB_PORT=5433
```

**Important**:
- ✅ Replace `<ask-for-password>` with the actual password above
- ✅ This file is in `.gitignore` and will NOT be committed to Git
- ✅ Keep this file secure - it contains database credentials

---

### Step 5: Verify GCP Credentials Exist

The Cloud SQL Proxy needs GCP credentials to authenticate.

```bash
# Check if service account file exists
ls -la .gcp/django-service-account.json
```

**If the file exists**: You're good to go!

**If the file does NOT exist**:
1. Copy it from your desktop, OR
2. Download from GCP Console:
   - Go to GCP Console → Project `b2b-recs`
   - IAM & Admin → Service Accounts
   - Find the Django service account
   - Create new key (JSON format)
   - Save as `.gcp/django-service-account.json`

---

### Step 6: Verify cloud-sql-proxy is Installed

```bash
# Check if cloud-sql-proxy exists
./cloud-sql-proxy --version
```

**If it exists**: You're good!

**If NOT found**:

```bash
# Download Cloud SQL Proxy
curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.8.0/cloud-sql-proxy.darwin.amd64

# Make executable
chmod +x cloud-sql-proxy

# Verify
./cloud-sql-proxy --version
```

---

### Step 7: Start Development Environment

```bash
./start_dev.sh
```

**What this script does**:
1. Starts Cloud SQL Proxy in background (output hidden)
2. Starts Django development server in foreground (logs visible in terminal)
3. Automatically stops both services when you press Ctrl+C

**Expected output**:

```
🚀 Starting B2B Recs Development Environment...

🔌 Starting Cloud SQL Proxy...
   ✅ Cloud SQL Proxy started (PID: XXXX)

🌐 Starting Django development server...
   📍 Web App: http://127.0.0.1:8000/
   📍 Database: 127.0.0.1:5433 (via Cloud SQL Proxy)

   💡 Press Ctrl+C to stop all services

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Watching for file changes with StatReloader
Performing system checks...
...
Django version 4.2.26, using settings 'config.settings'
Starting development server at http://127.0.0.1:8000/
Quit the server with CONTROL-C.
```

**From this point, all Django logs appear in your terminal in real-time.**

You can:
- ✅ See all Django output directly
- ✅ Copy logs from terminal
- ✅ Press **Ctrl+C** to stop everything cleanly (both Django and Cloud SQL Proxy)

---

### Step 8: Verify Connection to Cloud SQL

Open a browser and go to:

**http://127.0.0.1:8000/admin/**

**Login credentials**:
- Username: `dkulish`
- Password: `admin123`

**You should see**:
- Same user account as desktop
- Same ModelEndpoints
- Same ETL configurations
- Same data everywhere!

**Test data synchronization**:
1. On laptop: Create a new ModelEndpoint
2. On desktop: Refresh the page → see the new ModelEndpoint immediately
3. ✅ This confirms real-time sync!

---

### Step 9: Stop Development Environment

**To stop all services:**

Press **Ctrl+C** in the terminal where `start_dev.sh` is running.

**What happens**:
- Automatically stops Django development server
- Automatically stops Cloud SQL Proxy
- Clean shutdown of both services

---

## Troubleshooting

### Issue 1: Cloud SQL Proxy fails to start

**Error**: `connection refused` or `failed to start proxy`

**Solution**:

```bash
# Check logs
cat /tmp/cloud-sql-proxy.log

# Verify GCP credentials
echo $GOOGLE_APPLICATION_CREDENTIALS
# Should point to: /Users/dkulish/Projects/b2b_recs/.gcp/django-service-account.json

# Test authentication manually
gcloud auth application-default print-access-token
```

---

### Issue 2: Django can't connect to database

**Error**: `connection to server at "127.0.0.1", port 5433 failed`

**Solution**:

```bash
# Check if Cloud SQL Proxy is running
pgrep -f "cloud-sql-proxy"

# If not running, start it
./start_dev.sh

# Verify .env file exists and has correct values
cat .env
```

---

### Issue 3: Wrong Django version (still 5.2)

**Error**: `PostgreSQL 14 or later is required (found 13.22)`

**Solution**:

```bash
# Verify Django version
pip show Django
# Should show: Version: 4.2.26

# If not, reinstall
pip install "Django>=4.2,<4.3"
pip freeze > requirements.txt
```

---

### Issue 4: Missing dependencies

**Error**: `No module named 'psycopg2'` or `No module named 'dotenv'`

**Solution**:

```bash
source venv/bin/activate
pip install -r requirements.txt
```

---

## How It Works

### Architecture

```
┌─────────────────────────────────────────┐
│  Laptop (Django)                        │
│  ↓ reads .env file                      │
│  ↓ connects to 127.0.0.1:5433           │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│  Cloud SQL Proxy (local process)        │
│  ↓ authenticates with service account   │
│  ↓ establishes secure tunnel            │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│  Cloud SQL Instance (GCP)               │
│  Project: memo2-456215                  │
│  Instance: memo2-db                     │
│  Database: b2b_recs_dev                 │
│  Region: europe-central2                │
└─────────────────────────────────────────┘
                  ↑
┌─────────────────────────────────────────┐
│  Desktop (Django)                       │
│  ↑ same database                        │
│  ↑ real-time sync                       │
└─────────────────────────────────────────┘
```

### Security

**Database Password**:
- Stored in `.env` file (NOT in Git)
- File is in `.gitignore`
- Must be copied manually to each machine

**GCP Authentication**:
- Cloud SQL Proxy uses service account JSON key
- File: `.gcp/django-service-account.json`
- Also in `.gitignore`

**ETL Connection Passwords** (customer databases):
- Stored in GCP Secret Manager (not in `.env`)
- Centralized and encrypted by Google
- Accessed via Django API calls

---

## Benefits of Cloud SQL

✅ **Real-time sync**: Changes on laptop appear instantly on desktop
✅ **No manual exports**: No more `dumpdata` / `loaddata`
✅ **Production-ready**: Same database type as production
✅ **No cost increase**: Reusing existing Cloud SQL instance
✅ **Centralized**: Single source of truth for all data
✅ **Migrations simplified**: Run once, applies to all machines

---

## Rollback to SQLite (if needed)

If you need to use SQLite locally (e.g., for offline work):

```bash
# Option 1: Delete .env file
rm .env

# Option 2: Change DB_ENGINE in .env
# Edit .env and change: DB_ENGINE=sqlite

# Django will automatically use SQLite
python manage.py migrate
python create_user.py
python manage.py runserver
```

**Note**: Local SQLite database will be separate from Cloud SQL. Changes won't sync.

---

## Summary Checklist

Before you start:
- [ ] Pull latest code: `git pull origin main`
- [ ] Install dependencies: `pip install -r requirements.txt`
- [ ] Create `.env` file with database password
- [ ] Verify GCP credentials exist: `.gcp/django-service-account.json`
- [ ] Verify `cloud-sql-proxy` is installed

Start working:
- [ ] Run: `./start_dev.sh`
- [ ] Access: http://127.0.0.1:8000/
- [ ] Login with `dkulish` / `admin123`
- [ ] Verify data matches desktop

Stop working:
- [ ] Press **Ctrl+C** to stop all services

---

**Questions?** Check README.md for additional details or contact the team.

**Last Migration**: November 14, 2025 - Desktop migrated from SQLite to Cloud SQL
