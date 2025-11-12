# Desktop Setup Guide - b2b_recs Project

**Last Updated:** November 12, 2025

This guide helps you set up the b2b_recs project on your desktop computer (or any new machine).

---

## Prerequisites

- Git installed
- Python 3.9+ installed
- Internet connection

---

## Step 1: Clone the Repository

```bash
cd ~/Projects  # or wherever you keep your projects
git clone <your-repo-url>
cd b2b_recs
```

---

## Step 2: Set Up Python Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate  # On Mac/Linux
# OR
venv\Scripts\activate     # On Windows

# Install dependencies
pip install -r requirements.txt
```

---

## Step 3: Install Google Cloud SDK

**On Mac (using Homebrew):**
```bash
brew install --cask google-cloud-sdk
```

**On Windows:**
Download installer from: https://cloud.google.com/sdk/docs/install#windows

**On Linux:**
```bash
curl https://sdk.cloud.google.com | bash
exec -l $SHELL  # Restart shell
```

---

## Step 4: Authenticate with Google Cloud

```bash
# Login with your Google account
gcloud auth login

# Set the project
gcloud config set project b2b-recs
```

**Login credentials:**
- Account: `kulish.dmytro@gmail.com`
- Project: `b2b-recs`

---

## Step 5: Get Service Account Key

**Option A: Copy from MacBook Air (if you have access)**

On MacBook Air:
```bash
# Create a secure copy
scp ~/.gcp/django-service-account.json YOUR_DESKTOP_USER@YOUR_DESKTOP_IP:~/
```

On Desktop:
```bash
# Create directory and move key
mkdir -p ~/Projects/b2b_recs/.gcp
mv ~/django-service-account.json ~/Projects/b2b_recs/.gcp/
chmod 600 ~/Projects/b2b_recs/.gcp/django-service-account.json
```

**Option B: Download new key (if you can't copy)**

```bash
# Download the existing service account key
gcloud iam service-accounts keys create .gcp/django-service-account.json \
    --iam-account=django-app@b2b-recs.iam.gserviceaccount.com

# Set proper permissions
chmod 600 .gcp/django-service-account.json
```

---

## Step 6: Set Environment Variable

**On Mac/Linux (Bash):**
Add to `~/.bashrc`:
```bash
echo '' >> ~/.bashrc
echo '# Google Cloud credentials for b2b-recs' >> ~/.bashrc
echo 'export GOOGLE_APPLICATION_CREDENTIALS="'$(pwd)'/.gcp/django-service-account.json"' >> ~/.bashrc
source ~/.bashrc
```

**On Mac (Zsh - default on newer Macs):**
Add to `~/.zshrc`:
```bash
echo '' >> ~/.zshrc
echo '# Google Cloud credentials for b2b-recs' >> ~/.zshrc
echo 'export GOOGLE_APPLICATION_CREDENTIALS="'$(pwd)'/.gcp/django-service-account.json"' >> ~/.zshrc
source ~/.zshrc
```

**On Windows (PowerShell):**
Add to your PowerShell profile:
```powershell
# Edit profile
notepad $PROFILE

# Add this line:
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\Users\YourUser\Projects\b2b_recs\.gcp\django-service-account.json"

# Reload
. $PROFILE
```

---

## Step 7: Database Setup

```bash
# Create database
python manage.py migrate

# Create superuser
python create_user.py
# OR manually:
# python manage.py createsuperuser
```

**Default credentials (from create_user.py):**
- Username: `dkulish`
- Password: `admin123`

---

## Step 8: Run the Development Server

```bash
python manage.py runserver
```

**Access the app:**
- Web: http://127.0.0.1:8000/
- Admin: http://127.0.0.1:8000/admin/

---

## Verification Checklist

Run these commands to verify everything works:

```bash
# 1. Check Python environment
which python  # Should show venv path
python --version  # Should be 3.9+

# 2. Check gcloud is installed
gcloud --version

# 3. Check authentication
gcloud auth list  # Should show kulish.dmytro@gmail.com as active

# 4. Check project is set
gcloud config get-value project  # Should show: b2b-recs

# 5. Check environment variable
echo $GOOGLE_APPLICATION_CREDENTIALS  # Should show path to .gcp/django-service-account.json

# 6. Verify service account key exists
ls -lh .gcp/django-service-account.json  # Should show ~2.3K file

# 7. Test Secret Manager access
gcloud secrets list --project=b2b-recs  # Should not error (may show empty list)
```

---

## Troubleshooting

### "gcloud: command not found"

**Mac:**
Add to your shell profile:
```bash
export PATH="/opt/homebrew/share/google-cloud-sdk/bin:$PATH"
source ~/.zshrc  # or ~/.bashrc
```

**Windows:**
Restart your terminal after installation.

### "Permission denied" on service account key

```bash
chmod 600 .gcp/django-service-account.json
```

### "Module not found" errors

```bash
# Make sure venv is activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

### Database errors

```bash
# Reset database (WARNING: deletes all data)
rm db.sqlite3
python manage.py migrate
python create_user.py
```

---

## Project Structure Reference

```
b2b_recs/
├── .gcp/                           # GCP credentials (NOT in git)
│   └── django-service-account.json # Service account key
├── config/                         # Django settings
├── ml_platform/                    # Main app
│   ├── models.py                   # Database models
│   ├── views.py                    # API endpoints
│   └── utils/                      # Utilities (connection testing, etc.)
├── templates/                      # HTML templates
├── static/                         # CSS, JS, images
├── venv/                           # Python virtual environment (NOT in git)
├── db.sqlite3                      # SQLite database (NOT in git)
├── manage.py                       # Django management
├── requirements.txt                # Python dependencies
├── next_steps.md                   # Development roadmap
└── DESKTOP_SETUP.md               # This file
```

---

## Security Notes

⚠️ **NEVER commit these files to Git:**
- `.gcp/django-service-account.json` - Service account credentials
- `db.sqlite3` - Local database (contains user data)
- `.env` files - Environment variables

✅ **Already protected by .gitignore:**
- `.gcp/` directory
- `*.json` files (except package.json)
- `db.sqlite3`
- `venv/`

---

## Getting Help

If you run into issues:
1. Check this guide's Troubleshooting section
2. Check `next_steps.md` for current development status
3. Check Django logs: Look at terminal output when running `runserver`
4. Check GCP logs: https://console.cloud.google.com/logs (project: b2b-recs)

---

## Next Steps After Setup

Once everything is running:
1. Login at http://127.0.0.1:8000/
2. Create a test model/endpoint
3. Explore the ETL wizard
4. Check `next_steps.md` for current development tasks
