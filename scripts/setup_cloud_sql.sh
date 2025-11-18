#!/bin/bash
# Setup Cloud SQL for b2b-recs project

set -e

PROJECT_ID="b2b-recs"
INSTANCE_NAME="b2b-recs-db"
DB_NAME="b2b_recs_dev"
DB_USER="django_user"

# Get password from Secret Manager (already created earlier)
echo "Retrieving database password from Secret Manager..."
DB_PASSWORD=$(gcloud secrets versions access latest \
    --secret=django-db-password \
    --project=$PROJECT_ID)

echo "Setting up Cloud SQL database and user..."
echo ""

# Wait for instance to be ready
echo "Waiting for Cloud SQL instance to be ready..."
while true; do
    STATE=$(gcloud sql instances describe $INSTANCE_NAME \
        --project=$PROJECT_ID \
        --format="value(state)" 2>/dev/null || echo "NOT_FOUND")

    if [ "$STATE" = "RUNNABLE" ]; then
        echo "✅ Instance is ready!"
        break
    elif [ "$STATE" = "NOT_FOUND" ]; then
        echo "❌ Instance not found"
        exit 1
    else
        echo "   Status: $STATE (waiting...)"
        sleep 10
    fi
done

# Create database
echo ""
echo "Creating database '$DB_NAME'..."
gcloud sql databases create $DB_NAME \
    --instance=$INSTANCE_NAME \
    --project=$PROJECT_ID \
    --charset=UTF8 || echo "Database may already exist"

# Create user
echo ""
echo "Creating user '$DB_USER'..."
gcloud sql users create $DB_USER \
    --instance=$INSTANCE_NAME \
    --project=$PROJECT_ID \
    --password=$DB_PASSWORD || echo "User may already exist"

# Get connection name
echo ""
CONNECTION_NAME=$(gcloud sql instances describe $INSTANCE_NAME \
    --project=$PROJECT_ID \
    --format="value(connectionName)")

echo ""
echo "✅ Cloud SQL setup complete!"
echo ""
echo "Connection details:"
echo "  Instance: $INSTANCE_NAME"
echo "  Database: $DB_NAME"
echo "  User: $DB_USER"
echo "  Connection name: $CONNECTION_NAME"
echo ""
