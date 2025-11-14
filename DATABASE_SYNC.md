# Database Synchronization Guide

**Problem**: Working on the same Django project across multiple machines (laptop + desktop) with `db.sqlite3` not synced via Git.

**Solution**: This guide helps you synchronize database schema and optionally data between machines.

---

## Why Database Files Aren't in Git

`db.sqlite3` is in `.gitignore` because:
- ❌ Binary files don't merge well in Git
- ❌ Database contains sensitive local data (credentials, user passwords)
- ❌ Each developer should have their own local database
- ✅ Migrations ARE synced via Git (they define the schema)

---

## Quick Sync Process (Desktop Machine)

### Step 1: Pull Latest Code

```bash
cd /path/to/b2b_recs
git pull origin main
```

### Step 2: Activate Virtual Environment

```bash
source venv/bin/activate
```

### Step 3: Check Migration Status

```bash
python manage.py showmigrations ml_platform
```

**You should see:**
```
ml_platform
 [X] 0001_initial
 [X] 0002_remove_etlconfiguration_source_credentials_secret_and_more
 [X] 0003_datasource_connection_params_and_more
 [X] 0004_alter_datasource_credentials_secret_name_and_more
 [X] 0005_alter_connection_unique_together_and_more
 [X] 0006_alter_datasource_unique_together
 [X] 0007_datasource_wizard_completed_steps_and_more
```

**If you see `[ ]` (unchecked) migrations**, proceed to Step 4.

### Step 4: Apply Pending Migrations

```bash
python manage.py migrate
```

This will apply all unapplied migrations to bring your desktop database schema up-to-date with the laptop.

### Step 5: Verify Database is Ready

```bash
python manage.py check
```

Should output: `System check identified no issues (0 silenced).`

---

## Current Migration State (As of November 14, 2025)

**Latest Migration**: `0007_datasource_wizard_completed_steps_and_more`

**What this migration does:**
- Adds `wizard_last_step` field to DataSource model
- Adds `wizard_completed_steps` field to DataSource model
- Enables ETL job edit/resume functionality

**All Migrations:**

1. **0001_initial** - Initial database schema (all models)
2. **0002_remove_etlconfiguration_source_credentials_secret_and_more** - ETL config cleanup
3. **0003_datasource_connection_params_and_more** - Add connection parameters
4. **0004_alter_datasource_credentials_secret_name_and_more** - Secret name changes
5. **0005_alter_connection_unique_together_and_more** - Connection model with unique constraints
6. **0006_alter_datasource_unique_together** - DataSource unique constraint (etl_config, name)
7. **0007_datasource_wizard_completed_steps_and_more** - Wizard step tracking fields

---

## Starting Fresh (Nuclear Option)

If you want to completely reset the desktop database to match a clean state:

### Option A: Delete and Recreate Database

```bash
# DANGER: This deletes all data!
rm db.sqlite3

# Recreate database with all migrations
python manage.py migrate

# Create a superuser
python create_user.py
```

### Option B: Delete and Restore from Backup (if you have one)

```bash
# Backup desktop database (just in case)
cp db.sqlite3 db.sqlite3.backup

# Replace with laptop database (copy file manually)
# Then run migrations to ensure it's up-to-date
python manage.py migrate
```

---

## Syncing Data (Optional)

If you need to sync actual DATA (users, models, ETL jobs) between machines:

### Export Data from Laptop

```bash
# Export all data
python manage.py dumpdata > data_backup.json

# Or export specific app
python manage.py dumpdata ml_platform > ml_platform_data.json

# Or export specific models
python manage.py dumpdata ml_platform.ModelEndpoint ml_platform.Connection > connections.json
```

### Import Data on Desktop

```bash
# First: Apply all migrations
python manage.py migrate

# Then: Load data
python manage.py loaddata data_backup.json
```

**⚠️ Warning**: This will CREATE new records, not update existing ones. If you have conflicting data, you may get errors.

---

## Recommended Workflow

### On Laptop (Development Machine)

1. Make changes to code
2. Create migrations: `python manage.py makemigrations`
3. Apply migrations: `python manage.py migrate`
4. Test changes
5. Commit and push:
   ```bash
   git add .
   git commit -m "Your changes"
   git push origin main
   ```

### On Desktop (Sync Machine)

1. Pull latest code: `git pull origin main`
2. Activate venv: `source venv/bin/activate`
3. Apply migrations: `python manage.py migrate`
4. Start server: `python manage.py runserver`

**That's it!** The desktop database schema will match the laptop automatically.

---

## Common Issues & Solutions

### Issue 1: Migration Conflicts

**Error**: `Conflicting migrations detected`

**Solution**:
```bash
# Reset migrations (DANGER: only on fresh database)
python manage.py migrate --fake-initial
```

### Issue 2: Missing Migration Files

**Error**: `No such migration: 0007_datasource_wizard_completed_steps_and_more`

**Solution**: You forgot to pull the code first!
```bash
git pull origin main
python manage.py migrate
```

### Issue 3: Database is Locked

**Error**: `database is locked`

**Solution**:
```bash
# Stop Django server
# Check for running processes
ps aux | grep "manage.py runserver"
kill <process_id>

# Try migration again
python manage.py migrate
```

### Issue 4: IntegrityError When Loading Data

**Error**: `UNIQUE constraint failed`

**Solution**: You're trying to load data that already exists.
```bash
# Clear all data first
python manage.py flush  # DANGER: Deletes all data

# Then load fixture
python manage.py loaddata data_backup.json
```

---

## GCP Setup for Desktop

If you're testing ETL connections on desktop, you'll need GCP credentials:

### 1. Copy Service Account Key

From laptop, copy:
```bash
scp .gcp/django-service-account.json desktop:/path/to/b2b_recs/.gcp/
```

Or download again from GCP Console.

### 2. Set Environment Variable

Add to `~/.zshrc` or `~/.bash_profile`:
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/b2b_recs/.gcp/django-service-account.json"
```

Reload:
```bash
source ~/.zshrc
```

### 3. Verify GCP Connection

```bash
gcloud auth application-default print-access-token
```

Should print an access token.

---

## Quick Reference Commands

```bash
# CHECK migration status
python manage.py showmigrations

# APPLY pending migrations
python manage.py migrate

# VERIFY database
python manage.py check

# RUN development server
python manage.py runserver

# CREATE superuser
python create_user.py

# EXPORT data (for backup)
python manage.py dumpdata > backup.json

# IMPORT data (from backup)
python manage.py loaddata backup.json

# RESET database (DANGER!)
rm db.sqlite3 && python manage.py migrate
```

---

## Best Practices

1. **Always pull before coding**: `git pull origin main`
2. **Always migrate after pulling**: `python manage.py migrate`
3. **Never commit db.sqlite3**: It's already in `.gitignore`
4. **Keep migrations in Git**: They define the schema
5. **Test migrations**: Run `python manage.py migrate` locally before pushing
6. **Use fixtures for test data**: Create JSON files for reusable data

---

## When to Use Each Approach

| Scenario | Solution |
|----------|----------|
| Just pulled new code | Run `python manage.py migrate` |
| Need same schema, fresh data | Delete `db.sqlite3`, run `migrate`, run `create_user.py` |
| Need same data across machines | Export with `dumpdata`, import with `loaddata` |
| Database is corrupted | Delete `db.sqlite3`, run `migrate` |
| Testing migration changes | Create test database, apply migrations |

---

## Current Database Models

**ml_platform app:**
- ModelEndpoint
- Connection (reusable database connections)
- DataSource (ETL jobs)
- DataSourceTable (table mappings)
- Pipeline
- PipelineRun
- ETLConfiguration
- Experiments

**Django built-in:**
- User (authentication)
- Session
- ContentType
- Permission
- Group

---

## Summary

**Recommended Desktop Sync Steps:**

```bash
# 1. Pull latest code
git pull origin main

# 2. Activate virtual environment
source venv/bin/activate

# 3. Apply migrations
python manage.py migrate

# 4. Start development server
python manage.py runserver
```

**That's it!** Your desktop database schema will match your laptop automatically through Django migrations.

---

**Last Updated**: November 14, 2025
**Current Migration**: 0007_datasource_wizard_completed_steps_and_more
**Database Version**: SQLite 3
