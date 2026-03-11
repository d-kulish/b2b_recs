import json
import logging
import os

import resend
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .models import DemoRequest

logger = logging.getLogger(__name__)


@ensure_csrf_cookie
def landing(request):
    """Public landing page. Authenticated users get redirected to dashboard."""
    if request.user.is_authenticated:
        return redirect('system_dashboard')
    return render(request, 'website/landing.html')


def terms(request):
    """Terms of Service page."""
    return render(request, 'website/terms.html')


def privacy(request):
    """Privacy Policy page."""
    return render(request, 'website/privacy.html')


@require_POST
def request_demo(request):
    """Handle demo request submissions."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request.'}, status=400)

    email = (data.get('email') or '').strip()
    description = (data.get('description') or '').strip()
    honeypot = (data.get('company') or '').strip()

    if not email:
        return JsonResponse({'error': 'Email is required.'}, status=400)

    # Honeypot check — bots that fill hidden fields get a silent success
    if honeypot:
        return JsonResponse({'success': True})

    ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')

    DemoRequest.objects.create(
        email=email,
        description=description,
        ip_address=ip,
    )

    # Send notification email via Resend
    try:
        api_key = os.environ.get('RESEND_API_KEY')
        if api_key:
            resend.api_key = api_key
            body_lines = [f"Email: {email}"]
            if description:
                body_lines.append(f"\nDescription:\n{description}")
            resend.Emails.send({
                "from": "Recs Studio <noreply@recs.studio>",
                "to": ["dkulish@recs.studio"],
                "subject": f"New Demo Request from {email}",
                "text": "\n".join(body_lines),
            })
    except Exception:
        logger.exception("Failed to send demo request notification email")

    return JsonResponse({'success': True})
