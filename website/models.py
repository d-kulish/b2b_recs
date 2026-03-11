from django.db import models


class DemoRequest(models.Model):
    email = models.EmailField()
    description = models.TextField(blank=True, default='')
    honeypot = models.CharField(max_length=255, blank=True, default='')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.email} — {self.created_at:%Y-%m-%d %H:%M}"
