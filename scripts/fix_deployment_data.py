#!/usr/bin/env python
"""
One-time script to fix deployment data for training runs #37 and #38.

This script fixes the deployed_endpoint FK and deployment_status fields
for training runs that had successful deployments but were not properly
linked to their DeployedEndpoint records.

Run this script from the Django shell:
    python manage.py shell < scripts/fix_deployment_data.py

Or execute the code directly in the Django shell.
"""
import django
django.setup()

from ml_platform.training.models import TrainingRun, DeployedEndpoint

def fix_training_run(run_id, service_name):
    """Fix a single training run's deployment data."""
    try:
        training_run = TrainingRun.objects.get(id=run_id)
    except TrainingRun.DoesNotExist:
        print(f"Run #{run_id}: Not found, skipping")
        return False

    try:
        endpoint = DeployedEndpoint.objects.get(service_name=service_name)
    except DeployedEndpoint.DoesNotExist:
        print(f"Run #{run_id}: DeployedEndpoint with service_name={service_name} not found, skipping")
        return False

    # Update the training run
    training_run.deployed_endpoint = endpoint
    training_run.deployment_status = 'deployed'
    training_run.save(update_fields=['deployed_endpoint', 'deployment_status'])

    print(f"Fixed Run #{run_id}: deployed_endpoint={training_run.deployed_endpoint_id}, "
          f"deployment_status={training_run.deployment_status}")
    return True


if __name__ == '__main__':
    print("Fixing deployment data for training runs...\n")

    # Fix Run #38 (auto-deployed, endpoint is active)
    fix_training_run(38, 'chern-rank-v4-serving')

    # Fix Run #37 (deployed but endpoint now inactive)
    fix_training_run(37, 'chern-rank-v3-serving')

    print("\nDone!")
