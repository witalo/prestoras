from django.contrib import admin
from .models import Zone


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display  = ['nombre', 'empresa', 'activa', 'clientes_activos', 'descripcion_corta', 'created_at']
    list_filter   = ['status', 'company', 'created_at']
    search_fields = ['name', 'description', 'company__commercial_name', 'company__legal_name']
    readonly_fields = ['created_at', 'updated_at']
    list_per_page = 30
    actions = ['activar_zonas', 'desactivar_zonas']

    fieldsets = (
        ('Datos de la Zona', {
            'fields': ('company', 'name', 'description', 'status')
        }),
        ('Ubicacion GPS', {
            'fields': ('latitude', 'longitude'),
            'classes': ('collapse',)
        }),
        ('Auditoria', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='Nombre')
    def nombre(self, obj):
        return obj.name

    @admin.display(description='Empresa')
    def empresa(self, obj):
        return obj.company.commercial_name or obj.company.legal_name

    @admin.display(boolean=True, description='Activa')
    def activa(self, obj):
        return obj.status == 'ACTIVE'

    @admin.display(description='Clientes activos')
    def clientes_activos(self, obj):
        return obj.clients.filter(is_active=True).count()

    @admin.display(description='Descripcion')
    def descripcion_corta(self, obj):
        if obj.description:
            return obj.description[:60] + '...' if len(obj.description) > 60 else obj.description
        return '-'

    @admin.action(description='Marcar zonas seleccionadas como Activas')
    def activar_zonas(self, request, queryset):
        n = queryset.update(status='ACTIVE')
        self.message_user(request, f'{n} zona(s) activada(s) correctamente.')

    @admin.action(description='Marcar zonas seleccionadas como Inactivas')
    def desactivar_zonas(self, request, queryset):
        n = queryset.update(status='INACTIVE')
        self.message_user(request, f'{n} zona(s) desactivada(s) correctamente.')
