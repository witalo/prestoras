from django.contrib import admin
from .models import Zone

@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ['company', 'name', 'status', 'latitude', 'longitude', 'created_at']
    list_filter = ['status', 'company', 'created_at']
    search_fields = ['name', 'description', 'company__commercial_name']
    readonly_fields = ['created_at', 'updated_at']
