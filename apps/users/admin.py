from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User
from apps.clients.models import ClientCollector


class ClientesAsignadosInline(admin.TabularInline):
    """Muestra los clientes asignados a un cobrador directamente desde el usuario."""
    model = ClientCollector
    fk_name = 'collector'
    extra = 0
    can_delete = False
    readonly_fields = ['client', 'assigned_at', 'assigned_by']
    fields = ['client', 'assigned_at', 'assigned_by']
    verbose_name = 'Cliente asignado'
    verbose_name_plural = 'Clientes asignados (cartera)'

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display  = ['dni', 'nombre_completo', 'email', 'role', 'company', 'phone', 'is_active', 'num_clientes']
    list_filter   = ['role', 'is_active', 'company', 'is_staff', 'is_superuser']
    search_fields = ['dni', 'email', 'first_name', 'last_name', 'phone']
    ordering      = ['company', 'role', 'first_name']
    list_per_page = 40
    list_select_related = ['company']
    actions = ['activar_usuarios', 'desactivar_usuarios']

    fieldsets = (
        ('Credenciales', {
            'fields': ('dni', 'password')
        }),
        ('Datos Personales', {
            'fields': ('first_name', 'last_name', 'email', 'phone', 'photo')
        }),
        ('Rol y Empresa', {
            'fields': ('role', 'company', 'is_active')
        }),
        ('Permisos de sistema (Django)', {
            'fields': ('is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'classes': ('collapse',)
        }),
        ('Actividad', {
            'fields': ('last_login', 'date_joined'),
            'classes': ('collapse',)
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('dni', 'email', 'first_name', 'last_name', 'password1', 'password2', 'role', 'company'),
        }),
    )

    readonly_fields = ['last_login', 'date_joined']

    def get_inlines(self, request, obj):
        # Solo mostrar inline de clientes asignados si el usuario es COLLECTOR
        if obj and obj.role == 'COLLECTOR':
            return [ClientesAsignadosInline]
        return []

    @admin.display(description='Nombre')
    def nombre_completo(self, obj):
        return obj.full_name

    @admin.display(description='Clientes asignados')
    def num_clientes(self, obj):
        if obj.role == 'COLLECTOR':
            return obj.assigned_clients.filter(is_active=True).count()
        return '-'

    @admin.action(description='Activar usuarios seleccionados')
    def activar_usuarios(self, request, queryset):
        n = queryset.update(is_active=True)
        self.message_user(request, f'{n} usuario(s) activado(s).')

    @admin.action(description='Desactivar usuarios seleccionados')
    def desactivar_usuarios(self, request, queryset):
        n = queryset.update(is_active=False)
        self.message_user(request, f'{n} usuario(s) desactivado(s).')
