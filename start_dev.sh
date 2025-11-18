#!/bin/bash

# B2B Recs Development Environment Startup Script
# Usage: ./start_dev.sh
# Stop: Press Ctrl+C (will stop both Django and Cloud SQL Proxy)

set -e  # Exit on error

PROJECT_DIR="/Users/dkulish/Projects/b2b_recs"
VENV_PATH="$PROJECT_DIR/venv"
GCP_CREDS="$PROJECT_DIR/.gcp/django-service-account.json"

# Cleanup function - kills Cloud SQL Proxy when script exits
cleanup() {
    echo ""
    echo "🛑 Stopping services..."
    if [ ! -z "$PROXY_PID" ] && kill -0 $PROXY_PID 2>/dev/null; then
        kill $PROXY_PID
        echo "   ✅ Cloud SQL Proxy stopped"
    fi
    echo "   ✅ Django server stopped"
    echo ""
    exit 0
}

# Set up trap to catch Ctrl+C and call cleanup
trap cleanup SIGINT SIGTERM

echo "🚀 Starting B2B Recs Development Environment..."
echo ""

# Change to project directory if needed
if [ "$PWD" != "$PROJECT_DIR" ]; then
    cd "$PROJECT_DIR"
fi

# Check virtual environment
if [ ! -d "$VENV_PATH" ]; then
    echo "❌ Virtual environment not found at $VENV_PATH"
    exit 1
fi

# Check GCP credentials
if [ ! -f "$GCP_CREDS" ]; then
    echo "❌ GCP credentials not found at $GCP_CREDS"
    exit 1
fi

# Stop any existing Cloud SQL Proxy
if pgrep -f "cloud-sql-proxy.*b2b-recs" > /dev/null; then
    echo "🧹 Stopping existing Cloud SQL Proxy..."
    pkill -f "cloud-sql-proxy.*b2b-recs"
    sleep 1
fi

# Start Cloud SQL Proxy in background (output hidden)
echo "🔌 Starting Cloud SQL Proxy..."
export GOOGLE_APPLICATION_CREDENTIALS="$GCP_CREDS"
./cloud-sql-proxy b2b-recs:europe-central2:b2b-recs-db --port 5433 > /dev/null 2>&1 &
PROXY_PID=$!
sleep 2

# Check if proxy started successfully
if ! kill -0 $PROXY_PID 2>/dev/null; then
    echo "❌ Failed to start Cloud SQL Proxy"
    exit 1
fi

echo "   ✅ Cloud SQL Proxy started (PID: $PROXY_PID)"
echo ""

# Start Django server in foreground (logs visible in terminal)
echo "🌐 Starting Django development server..."
echo "   📍 Web App: http://127.0.0.1:8000/"
echo "   📍 Database: 127.0.0.1:5433 (via Cloud SQL Proxy)"
echo ""
echo "   💡 Press Ctrl+C to stop all services"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

source "$VENV_PATH/bin/activate"

# Load environment variables from .env file
if [ -f "$PROJECT_DIR/.env" ]; then
    export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
    echo "   ✅ Loaded environment variables from .env"
fi

# Set database environment variables for b2b-recs PostgreSQL
export DB_ENGINE=postgresql
export DB_NAME=b2b_recs_dev
export DB_USER=django_user
export DB_HOST=127.0.0.1
export DB_PORT=5433

echo "   📊 Database: b2b_recs_dev @ b2b-recs-db"
echo ""

python manage.py runserver

# If Django exits normally (not Ctrl+C), cleanup
cleanup
