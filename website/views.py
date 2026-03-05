from django.shortcuts import render, redirect


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
