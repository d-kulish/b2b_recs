"""
Configs Domain Page Views

Handles rendering of the Configs (Feature & Model Configuration) page.
"""

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required

from ml_platform.models import ModelEndpoint


@login_required
def model_configs(request, model_id):
    """
    Render the Configs (Feature & Model Configuration) page.

    This page allows users to:
    - View list of feature configs for datasets in this model
    - Create new feature configs with wizard
    - Edit existing feature configs
    - View tensor dimension previews
    - Manage model configs (architecture)
    """
    model = get_object_or_404(ModelEndpoint, id=model_id)

    context = {
        'model': model,
    }

    return render(request, 'ml_platform/model_configs.html', context)
