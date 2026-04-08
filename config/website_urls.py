"""Website-only URL configuration."""

from django.contrib.sitemaps.views import sitemap
from django.http import HttpResponse
from django.urls import include, path

from website.sitemaps import StaticViewSitemap

sitemaps = {
    'static': StaticViewSitemap,
}


def robots_txt(request):
    lines = [
        'User-agent: *',
        'Allow: /',
        '',
        'Sitemap: https://recs.studio/sitemap.xml',
    ]
    return HttpResponse('\n'.join(lines), content_type='text/plain')


urlpatterns = [
    path('robots.txt', robots_txt, name='robots_txt'),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path('', include('website.urls')),
]
