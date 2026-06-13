from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    protocol = 'https'
    changefreq = 'monthly'

    def items(self):
        return [
            ('landing', 1.0),
            ('pricing', 0.8),
            ('about', 0.6),
            ('customers', 0.6),
            ('support', 0.6),
            ('security', 0.6),
            ('terms', 0.3),
            ('privacy', 0.3),
        ]

    def location(self, item):
        return reverse(item[0])

    def priority(self, item):
        return item[1]
