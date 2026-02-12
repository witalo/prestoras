from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['dni', 'email', 'full_name', 'role', 'company', 'phone', 'is_active']
    list_filter = ['role', 'is_active', 'company', 'is_staff', 'is_superuser']
    search_fields = ['dni', 'email', 'first_name', 'last_name', 'phone']
    ordering = ['dni']  # Ordenar por DNI en lugar de username
    
    fieldsets = (
        (None, {'fields': ('dni', 'password')}),
        ('Información Personal', {'fields': ('first_name', 'last_name', 'email', 'phone', 'photo')}),
        ('Permisos y Roles', {'fields': ('role', 'company', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Fechas importantes', {'fields': ('last_login', 'date_joined')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('dni', 'email', 'first_name', 'last_name', 'password1', 'password2', 'role', 'company'),
        }),
    )
    
    readonly_fields = ['last_login', 'date_joined']
