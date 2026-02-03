from django.contrib import admin
from .models import Client, ClientDocument

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['dni', 'full_name', 'company', 'zone', 'classification', 'phone', 'is_active']
    list_filter = ['classification', 'is_active', 'company', 'zone', 'created_at']
    search_fields = ['dni', 'first_name', 'last_name', 'phone', 'email']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Información Personal', {
            'fields': ('company', 'zone', 'dni', 'first_name', 'last_name', 'phone', 'email')
        }),
        ('Ubicación', {
            'fields': ('home_address', 'business_address', 'latitude', 'longitude')
        }),
        ('Clasificación', {
            'fields': ('classification', 'notes', 'is_active')
        }),
        ('Auditoría', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(ClientDocument)
class ClientDocumentAdmin(admin.ModelAdmin):
    list_display = ['client', 'document_type', 'created_at']
    list_filter = ['document_type', 'created_at']
    search_fields = ['client__dni', 'client__first_name', 'client__last_name']
    readonly_fields = ['created_at', 'updated_at']
