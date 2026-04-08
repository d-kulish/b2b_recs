"""
Website-specific Django settings.

This deployment serves only the public marketing website.
"""

from .settings import *  # noqa: F401,F403


INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sitemaps',
    'website',
]

ROOT_URLCONF = 'config.website_urls'
WSGI_APPLICATION = 'config.wsgi_website.application'

# The public website does not expose a local dashboard.
LOGIN_REDIRECT_URL = PLATFORM_DASHBOARD_URL
LOGOUT_REDIRECT_URL = '/'
