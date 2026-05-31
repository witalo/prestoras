from django.contrib import admin
from django import forms
from .models import Company, LoanType
from apps.zones.models import Zone


class LoanTypeInline(admin.TabularInline):
    model = LoanType
    extra = 0
    fields = ['name', 'periodicity', 'default_interest_rate', 'suggested_installments', 'is_active']
    verbose_name = 'Tipo de prestamo'
    verbose_name_plural = 'Tipos de prestamo'


class ZoneInline(admin.TabularInline):
    model = Zone
    extra = 0
    fields = ['name', 'status', 'description']
    verbose_name = 'Zona'
    verbose_name_plural = 'Zonas'
    show_change_link = True


class CompanyAdminForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = '__all__'
        widgets = {
            'password': forms.PasswordInput(render_value=True),
        }

    def save(self, commit=True):
        company = super().save(commit=False)
        if commit:
            company.save()
        return company


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    form = CompanyAdminForm
    list_display  = ['ruc', 'nombre_comercial', 'email', 'phone', 'is_active', 'num_clientes', 'num_prestamos_activos', 'created_at']
    list_filter   = ['is_active', 'created_at']
    search_fields = ['ruc', 'legal_name', 'commercial_name', 'email']
    readonly_fields = ['created_at', 'updated_at']
    list_per_page = 20
    inlines = [LoanTypeInline, ZoneInline]
    actions = ['activar_empresas', 'desactivar_empresas']

    fieldsets = (
        ('Acceso', {
            'fields': ('ruc', 'email', 'password'),
            'description': 'Credenciales de login de la empresa'
        }),
        ('Responsable Legal', {
            'fields': ('responsible_document', 'responsible_names', 'responsible_last_names')
        }),
        ('Datos de la Empresa', {
            'fields': ('legal_name', 'commercial_name', 'fiscal_address', 'phone')
        }),
        ('Logo', {
            'fields': ('logo',)
        }),
        ('Estado', {
            'fields': ('is_active',)
        }),
        ('Ubicacion', {
            'fields': ('latitude', 'longitude'),
            'classes': ('collapse',)
        }),
        ('Auditoria', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='Nombre comercial')
    def nombre_comercial(self, obj):
        return obj.commercial_name or obj.legal_name

    @admin.display(description='Clientes')
    def num_clientes(self, obj):
        return obj.clients.filter(is_active=True).count()

    @admin.display(description='Prestamos activos')
    def num_prestamos_activos(self, obj):
        return obj.loans.filter(status__in=['ACTIVE', 'DEFAULTING']).count()

    @admin.action(description='Activar empresas seleccionadas')
    def activar_empresas(self, request, queryset):
        n = queryset.update(is_active=True)
        self.message_user(request, f'{n} empresa(s) activada(s).')

    @admin.action(description='Desactivar empresas seleccionadas')
    def desactivar_empresas(self, request, queryset):
        n = queryset.update(is_active=False)
        self.message_user(request, f'{n} empresa(s) desactivada(s).')

    def save_model(self, request, obj, form, change):
        if 'password' in form.cleaned_data and form.cleaned_data['password']:
            raw_password = form.cleaned_data['password']
            is_encrypted = (
                raw_password.startswith('pbkdf2_') or
                raw_password.startswith('bcrypt$') or
                raw_password.startswith('argon2$') or
                raw_password.startswith('$') or
                len(raw_password) > 60
            )
            if not is_encrypted:
                obj.set_password(raw_password)
            else:
                obj.password = raw_password
        super().save_model(request, obj, form, change)


@admin.register(LoanType)
class LoanTypeAdmin(admin.ModelAdmin):
    list_display  = ['name', 'company', 'periodicity', 'default_interest_rate', 'suggested_installments', 'is_active']
    list_filter   = ['periodicity', 'is_active', 'company']
    search_fields = ['name', 'description', 'company__legal_name', 'company__commercial_name']
    readonly_fields = ['created_at', 'updated_at']
    list_per_page = 30
    actions = ['activar', 'desactivar']

    fieldsets = (
        ('Datos', {
            'fields': ('company', 'name', 'description', 'is_active')
        }),
        ('Parametros por defecto', {
            'fields': ('periodicity', 'default_interest_rate', 'suggested_installments'),
            'description': 'Valores sugeridos al crear un prestamo de este tipo'
        }),
        ('Auditoria', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.action(description='Activar tipos seleccionados')
    def activar(self, request, queryset):
        n = queryset.update(is_active=True)
        self.message_user(request, f'{n} tipo(s) activado(s).')

    @admin.action(description='Desactivar tipos seleccionados')
    def desactivar(self, request, queryset):
        n = queryset.update(is_active=False)
        self.message_user(request, f'{n} tipo(s) desactivado(s).')
