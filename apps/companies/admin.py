from django.contrib import admin
from django import forms
from django.contrib.auth.hashers import make_password
from .models import Company, LoanType


class CompanyAdminForm(forms.ModelForm):
    """Formulario personalizado para encriptar contraseñas"""
    
    class Meta:
        model = Company
        fields = '__all__'
        widgets = {
            'password': forms.PasswordInput(render_value=True),
        }
    
    def save(self, commit=True):
        # Guardar sin commit para permitir que save_model maneje la encriptación
        company = super().save(commit=False)
        if commit:
            company.save()
        return company


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    form = CompanyAdminForm
    list_display = ['ruc', 'legal_name', 'commercial_name', 'email', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['ruc', 'legal_name', 'commercial_name', 'email']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Datos de Acceso', {
            'fields': ('ruc', 'email', 'password'),
            'description': 'RUC, correo y contraseña para login de empresa'
        }),
        ('Datos del Responsable', {
            'fields': ('responsible_document', 'responsible_names', 'responsible_last_names')
        }),
        ('Datos de la Empresa', {
            'fields': ('legal_name', 'commercial_name', 'fiscal_address', 'phone')
        }),
        ('Ubicación', {
            'fields': ('latitude', 'longitude'),
            'classes': ('collapse',)
        }),
        ('Logo', {
            'fields': ('logo',)
        }),
        ('Estado', {
            'fields': ('is_active',)
        }),
        ('Fechas', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        """
        Encripta la contraseña automáticamente si se proporciona texto plano.
        Detecta si la contraseña ya está encriptada para evitar doble encriptación.
        """
        # Si hay password en el formulario
        if 'password' in form.cleaned_data and form.cleaned_data['password']:
            raw_password = form.cleaned_data['password']
            
            # Verificar si la contraseña ya está encriptada
            # Las contraseñas encriptadas de Django empiezan con 'pbkdf2_', 'bcrypt$', 'argon2$', o '$'
            # o tienen más de 60 caracteres (los hashes son largos)
            is_encrypted = (
                raw_password.startswith('pbkdf2_') or
                raw_password.startswith('bcrypt$') or
                raw_password.startswith('argon2$') or
                raw_password.startswith('$') or
                len(raw_password) > 60
            )
            
            # Solo encriptar si es texto plano
            if not is_encrypted:
                obj.set_password(raw_password)
            else:
                # Si ya está encriptado, asignarlo directamente sin re-encriptar
                obj.password = raw_password
        
        super().save_model(request, obj, form, change)

@admin.register(LoanType)
class LoanTypeAdmin(admin.ModelAdmin):
    list_display = ['company', 'name', 'periodicity', 'default_interest_rate', 'suggested_installments', 'is_active']
    list_filter = ['periodicity', 'is_active']
    search_fields = ['name', 'company__legal_name']
