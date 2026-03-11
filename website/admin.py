from django.contrib import admin
from .models import DemoRequest


@admin.register(DemoRequest)
class DemoRequestAdmin(admin.ModelAdmin):
    list_display = ('email', 'description_preview', 'ip_address', 'created_at')
    readonly_fields = ('email', 'description', 'honeypot', 'ip_address', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('email',)

    def description_preview(self, obj):
        if obj.description:
            return obj.description[:80] + ('...' if len(obj.description) > 80 else '')
        return '-'
    description_preview.short_description = 'Description'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
