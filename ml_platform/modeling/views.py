"""
Modeling Domain Page Views

Handles rendering of the Modeling (Feature Engineering) page.
"""

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required

from ml_platform.models import ModelEndpoint


@login_required
def model_modeling(request, model_id):
    """
    Render the Modeling (Feature Engineering) page.

    This page allows users to:
    - View list of feature configs for datasets in this model
    - Create new feature configs with wizard
    - Edit existing feature configs
    - View tensor dimension previews
    """
    model = get_object_or_404(ModelEndpoint, id=model_id)

    context = {
        'model': model,
    }

    return render(request, 'ml_platform/model_modeling.html', context)
