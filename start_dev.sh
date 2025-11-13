#!/bin/bash

# B2B Recs Development Environment Startup Script
# Usage: ./start_dev.sh

set -e  # Exit on error

PROJECT_DIR="/Users/dkulish/Projects/b2b_recs"
VENV_PATH="$PROJECT_DIR/venv"
GCP_CREDS="$PROJECT_DIR/.gcp/django-service-account.json"
PROXY_LOG="/tmp/cloud-sql-proxy.log"
DJANGO_LOG="/tmp/django-dev-server.log"

echo "🚀 Starting B2B Recs Development Environment..."
echo ""

# Check if already in project directory
if [ "$PWD" != "$PROJECT_DIR" ]; then
    echo "📁 Changing to project directory..."
    cd "$PROJECT_DIR"
fi

# Check if virtual environment exists
if [ ! -d "$VENV_PATH" ]; then
    echo "❌ Virtual environment not found at $VENV_PATH"
    echo "   Please run: python3 -m venv venv"
    exit 1
fi

# Check if GCP credentials exist
if [ ! -f "$GCP_CREDS" ]; then
    echo "❌ GCP credentials not found at $GCP_CREDS"
    exit 1
fi

# Check if Cloud SQL Proxy is already running
if pgrep -f "cloud-sql-proxy.*memo2-456215" > /dev/null; then
    echo "⚠️  Cloud SQL Proxy is already running"
else
    echo "🔌 Starting Cloud SQL Proxy..."
    export GOOGLE_APPLICATION_CREDENTIALS="$GCP_CREDS"
    ./cloud-sql-proxy memo2-456215:europe-central2:memo2-db --port 5433 > "$PROXY_LOG" 2>&1 &
    PROXY_PID=$!
    sleep 2

    # Check if proxy started successfully
    if pgrep -f "cloud-sql-proxy.*memo2-456215" > /dev/null; then
        echo "   ✅ Cloud SQL Proxy started (PID: $PROXY_PID)"
        echo "   📝 Logs: $PROXY_LOG"
    else
        echo "   ❌ Failed to start Cloud SQL Proxy"
        echo "   Check logs: $PROXY_LOG"
        exit 1
    fi
fi

echo ""

# Check if Django server is already running
if pgrep -f "manage.py runserver" > /dev/null; then
    echo "⚠️  Django development server is already running"
else
    echo "🌐 Starting Django development server..."
    source "$VENV_PATH/bin/activate"
    python manage.py runserver > "$DJANGO_LOG" 2>&1 &
    DJANGO_PID=$!
    sleep 2

    # Check if Django started successfully
    if pgrep -f "manage.py runserver" > /dev/null; then
        echo "   ✅ Django server started (PID: $DJANGO_PID)"
        echo "   📝 Logs: $DJANGO_LOG"
    else
        echo "   ❌ Failed to start Django server"
        echo "   Check logs: $DJANGO_LOG"
        exit 1
    fi
fi

echo ""
echo "✨ Development environment is ready!"
echo ""
echo "📍 Access Points:"
echo "   • Web App:      http://127.0.0.1:8000/"
echo "   • Admin Panel:  http://127.0.0.1:8000/admin/"
echo "   • Database:     127.0.0.1:5433 (via Cloud SQL Proxy)"
echo ""
echo "📊 Monitor Logs:"
echo "   • Proxy:  tail -f $PROXY_LOG"
echo "   • Django: tail -f $DJANGO_LOG"
echo ""
echo "🛑 Stop Services:"
echo "   • Run: ./stop_dev.sh"
echo "   • Or:  pkill -f 'cloud-sql-proxy|manage.py runserver'"
echo ""
