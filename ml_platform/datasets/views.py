"""
Datasets Page Views

Handles rendering of dataset-related pages.
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required

from ml_platform.models import ModelEndpoint, Dataset


@login_required
def redirect_to_configs(request, model_id):
    """
    Redirect from old Dataset Manager page to merged Datasets & Configs page.
    The dataset functionality has been integrated into model_configs.
    """
    return redirect(reverse('model_configs', kwargs={'model_id': model_id}))


@login_required
def model_dataset_legacy(request, model_id):
    """
    Dataset Manager Page - Create and manage dataset definitions for ML training.
    """
    model = get_object_or_404(ModelEndpoint, id=model_id)

    # Get all datasets for this model
    datasets = model.datasets.all().order_by('-updated_at')

    # Calculate statistics
    total_datasets = datasets.count()

    context = {
        'model': model,
        'datasets': datasets,
        'total_datasets': total_datasets,
    }

    return render(request, 'ml_platform/model_dataset.html', context)
