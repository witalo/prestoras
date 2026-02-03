"""
Modelos para la gestión de empresas multiempresa
Cada empresa es independiente en datos y configuración
"""
from django.db import models
from django.contrib.auth.hashers import make_password, check_password

# Opciones para periodicidad de préstamos
PERIODICITY_CHOICES = [
    ('DAILY', 'Diario'),
    ('WEEKLY', 'Semanal'),
    ('BIWEEKLY', 'Quincenal'),
    ('MONTHLY', 'Mensual'),
    ('QUARTERLY', 'Trimestral'),  # Cada 3 meses
    ('CUSTOM', 'Personalizado'),
]


class Company(models.Model):
    """
    Modelo de Empresa - Sistema Multiempresa
    
    Cada empresa tiene sus propios clientes, préstamos, cobradores y configuración.
    El login de empresa usa RUC, correo y contraseña.
    """
    id = models.AutoField(primary_key=True)
    
    # Datos del responsable
    responsible_document = models.CharField(
        'RUC o DNI del Responsable',
        max_length=11,
        null=True,
        blank=True,
        help_text='RUC (11 dígitos) o DNI (8 dígitos) del responsable'
    )
    responsible_names = models.CharField(
        'Nombres del Responsable',
        max_length=100,
        null=True,
        blank=True
    )
    responsible_last_names = models.CharField(
        'Apellidos del Responsable',
        max_length=100,
        null=True,
        blank=True
    )
    
    # Datos de la empresa
    ruc = models.CharField(
        'RUC',
        max_length=11,
        unique=True,
        null=True,
        blank=True,
        help_text='RUC de la empresa (11 dígitos)'
    )
    legal_name = models.CharField(
        'Razón Social',
        max_length=200,
        null=True,
        blank=True
    )
    commercial_name = models.CharField(
        'Nombre Comercial',
        max_length=200,
        null=True,
        blank=True
    )
    
    # Dirección fiscal
    fiscal_address = models.TextField(
        'Dirección Fiscal',
        null=True,
        blank=True
    )
    
    # Ubicación GPS
    latitude = models.DecimalField(
        'Latitud',
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        help_text='Coordenada GPS de la empresa'
    )
    longitude = models.DecimalField(
        'Longitud',
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        help_text='Coordenada GPS de la empresa'
    )
    
    # Contacto
    email = models.EmailField(
        'Correo Electrónico',
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        help_text='Correo para login de empresa'
    )
    phone = models.CharField(
        'Teléfono',
        max_length=15,
        null=True,
        blank=True
    )
    
    # Logo de la empresa
    logo = models.ImageField(
        'Logo',
        upload_to='companies/logos/',
        blank=True,
        null=True
    )
    
    # Contraseña para login de empresa (hasheada)
    password = models.CharField(
        'Contraseña',
        max_length=128,
        null=True,
        blank=True,
        help_text='Contraseña hasheada para login de empresa'
    )
    
    # Estado
    is_active = models.BooleanField('Activa', default=True)
    
    # Auditoría
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def set_password(self, raw_password):
        """Hashea y guarda la contraseña"""
        self.password = make_password(raw_password)
    
    def check_password(self, raw_password):
        """Verifica si la contraseña es correcta"""
        if not self.password:
            return False
        return check_password(raw_password, self.password)
    
    @property
    def responsible_full_name(self):
        """Retorna el nombre completo del responsable"""
        return f"{self.responsible_names or ''} {self.responsible_last_names or ''}".strip()
    
    def __str__(self):
        return self.commercial_name or self.legal_name or f"Empresa {self.ruc}"
    
    class Meta:
        verbose_name = 'Empresa'
        verbose_name_plural = 'Empresas'
        ordering = ['legal_name']
        indexes = [
            models.Index(fields=['ruc']),
            models.Index(fields=['email']),
            models.Index(fields=['is_active']),
        ]


class LoanType(models.Model):
    """
    Tipo de Préstamo por Empresa
    
    Cada empresa define sus tipos de préstamo (Diario, Semanal, Mensual)
    con sus características por defecto.
    """
    id = models.AutoField(primary_key=True)
    
    # Relación con empresa
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='loan_types',
        help_text='Empresa a la que pertenece este tipo de préstamo'
    )
    
    # Nombre del tipo de préstamo
    name = models.CharField(
        'Nombre',
        max_length=50,
        help_text='Ej: Diario, Semanal, Mensual'
    )
    
    # Periodicidad de pago
    periodicity = models.CharField(
        'Periodicidad',
        max_length=20,
        choices=PERIODICITY_CHOICES,
        default='DAILY',
        help_text='Frecuencia de los pagos (diario, semanal, mensual)'
    )
    
    # Tasa de interés por defecto (%)
    default_interest_rate = models.DecimalField(
        'Tasa de Interés (%)',
        max_digits=5,
        decimal_places=2,
        default=0.00,
        help_text='Tasa de interés por defecto en porcentaje (ej: 8.00 para 8%)'
    )
    
    # Número de cuotas sugeridas
    suggested_installments = models.IntegerField(
        'Cuotas Sugeridas',
        default=1,
        help_text='Número de cuotas sugerido para este tipo de préstamo'
    )
    
    # Descripción
    description = models.TextField(
        'Descripción',
        blank=True,
        null=True,
        help_text='Descripción del tipo de préstamo'
    )
    
    # Estado
    is_active = models.BooleanField('Activo', default=True)
    
    # Auditoría
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.company.commercial_name} - {self.name}"
    
    class Meta:
        verbose_name = 'Tipo de Préstamo'
        verbose_name_plural = 'Tipos de Préstamo'
        ordering = ['company', 'name']
        unique_together = ['company', 'name']
        indexes = [
            models.Index(fields=['company', 'is_active']),
        ]
