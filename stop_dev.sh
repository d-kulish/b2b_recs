#!/bin/bash

# B2B Recs Development Environment Stop Script
# Usage: ./stop_dev.sh

echo "🛑 Stopping B2B Recs Development Environment..."
echo ""

# Stop Cloud SQL Proxy
if pgrep -f "cloud-sql-proxy.*memo2-456215" > /dev/null; then
    echo "   Stopping Cloud SQL Proxy..."
    pkill -f "cloud-sql-proxy.*memo2-456215"
    echo "   ✅ Cloud SQL Proxy stopped"
else
    echo "   ⚠️  Cloud SQL Proxy not running"
fi

# Stop Django server
if pgrep -f "manage.py runserver" > /dev/null; then
    echo "   Stopping Django development server..."
    pkill -f "manage.py runserver"
    echo "   ✅ Django server stopped"
else
    echo "   ⚠️  Django server not running"
fi

echo ""
echo "✅ All services stopped"
echo ""
