from django.contrib import admin
from .models import Client, ClientCollector, ClientDocument


class ClientCollectorInline(admin.TabularInline):
    model = ClientCollector
    fk_name = 'client'
    extra = 0
    readonly_fields = ['assigned_at', 'assigned_by']
    fields = ['collector', 'assigned_by', 'assigned_at']
    verbose_name = 'Cobrador asignado'
    verbose_name_plural = 'Cobradores asignados (cartera)'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('collector', 'assigned_by')


class ClientDocumentInline(admin.TabularInline):
    model = ClientDocument
    extra = 0
    readonly_fields = ['created_at', 'updated_at']
    fields = ['document_type', 'file', 'description', 'created_at']
    verbose_name = 'Documento'
    verbose_name_plural = 'Documentos del cliente'


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display  = ['dni', 'nombre_completo', 'company', 'zone', 'classification', 'phone', 'is_active', 'num_prestamos']
    list_filter   = ['classification', 'is_active', 'company', 'zone', 'created_at']
    search_fields = ['dni', 'first_name', 'last_name', 'phone', 'email']
    readonly_fields = ['created_at', 'updated_at']
    list_per_page = 40
    list_select_related = ['company', 'zone']
    inlines = [ClientCollectorInline, ClientDocumentInline]
    actions = ['activar_clientes', 'desactivar_clientes']

    fieldsets = (
        ('Datos Personales', {
            'fields': ('company', 'zone', 'dni', 'first_name', 'last_name', 'phone', 'email')
        }),
        ('Direcciones', {
            'fields': ('home_address', 'business_address')
        }),
        ('Ubicacion GPS', {
            'fields': ('latitude', 'longitude'),
            'classes': ('collapse',)
        }),
        ('Clasificacion y Estado', {
            'fields': ('classification', 'is_active', 'notes')
        }),
        ('Auditoria', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='Nombre completo')
    def nombre_completo(self, obj):
        return obj.full_name

    @admin.display(description='Prestamos')
    def num_prestamos(self, obj):
        return obj.loans.filter(status__in=['ACTIVE', 'DEFAULTING']).count()

    @admin.action(description='Activar clientes seleccionados')
    def activar_clientes(self, request, queryset):
        n = queryset.update(is_active=True)
        self.message_user(request, f'{n} cliente(s) activado(s).')

    @admin.action(description='Desactivar clientes seleccionados')
    def desactivar_clientes(self, request, queryset):
        n = queryset.update(is_active=False)
        self.message_user(request, f'{n} cliente(s) desactivado(s).')


@admin.register(ClientCollector)
class ClientCollectorAdmin(admin.ModelAdmin):
    list_display  = ['cliente', 'cobrador', 'empresa', 'assigned_by', 'assigned_at']
    list_filter   = ['assigned_at', 'collector__company']
    search_fields = [
        'client__dni', 'client__first_name', 'client__last_name',
        'collector__dni', 'collector__first_name', 'collector__last_name',
    ]
    readonly_fields = ['assigned_at']
    list_select_related = ['client', 'collector', 'assigned_by']
    list_per_page = 40

    @admin.display(description='Cliente')
    def cliente(self, obj):
        return f"{obj.client.full_name} ({obj.client.dni})"

    @admin.display(description='Cobrador')
    def cobrador(self, obj):
        return f"{obj.collector.full_name} ({obj.collector.dni})"

    @admin.display(description='Empresa')
    def empresa(self, obj):
        return obj.collector.company


@admin.register(ClientDocument)
class ClientDocumentAdmin(admin.ModelAdmin):
    list_display  = ['cliente', 'document_type', 'created_at']
    list_filter   = ['document_type', 'created_at', 'client__company']
    search_fields = ['client__dni', 'client__first_name', 'client__last_name']
    readonly_fields = ['created_at', 'updated_at']

    @admin.display(description='Cliente')
    def cliente(self, obj):
        return f"{obj.client.full_name} ({obj.client.dni})"
