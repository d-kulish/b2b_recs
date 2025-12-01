"""
Datasets Page Views

Handles rendering of dataset-related pages.
"""
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required

from ml_platform.models import ModelEndpoint, Dataset


@login_required
def model_dataset(request, model_id):
    """
    Dataset Manager Page - Create and manage dataset definitions for ML training.
    """
    model = get_object_or_404(ModelEndpoint, id=model_id)

    # Get all datasets for this model
    datasets = model.datasets.all().order_by('-updated_at')

    # Calculate statistics
    total_datasets = datasets.count()
    active_datasets = datasets.filter(status='active').count()
    draft_datasets = datasets.filter(status='draft').count()

    context = {
        'model': model,
        'datasets': datasets,
        'total_datasets': total_datasets,
        'active_datasets': active_datasets,
        'draft_datasets': draft_datasets,
    }

    return render(request, 'ml_platform/model_dataset.html', context)
