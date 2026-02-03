"""
Modelos de Clientes
Incluye datos personales, documentos, clasificación y geolocalización
"""
from django.db import models

# Opciones para clasificación de clientes
CLIENT_CLASSIFICATION_CHOICES = [
    ('PUNCTUAL', 'Puntual'),
    ('REGULAR', 'Regular'),
    ('DEFAULTING', 'Moroso'),
    ('SEVERELY_DEFAULTING', 'Muy Moroso'),
]

# Tipos de documentos del cliente
DOCUMENT_TYPE_CHOICES = [
    ('DNI', 'Foto de DNI'),
    ('RECEIPT', 'Recibo (Agua/Luz)'),
    ('ADDITIONAL', 'Foto Adicional'),
    ('CONTRACT', 'Contrato'),
    ('OTHER', 'Otro'),
]


class Client(models.Model):
    """
    Modelo de Cliente
    
    Un cliente puede tener múltiples créditos activos simultáneamente.
    Se clasifica automáticamente según su historial de pagos.
    """
    id = models.AutoField(primary_key=True)
    
    # Relación con empresa
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='clients',
        help_text='Empresa a la que pertenece este cliente'
    )
    
    # Relación con zona
    zone = models.ForeignKey(
        'zones.Zone',
        on_delete=models.SET_NULL,
        related_name='clients',
        null=True,
        blank=True,
        help_text='Zona asignada al cliente'
    )
    
    # Datos personales
    dni = models.CharField(
        'DNI',
        max_length=8,
        unique=True,
        null=False,
        blank=False,
        help_text='DNI del cliente (8 dígitos)'
    )
    first_name = models.CharField(
        'Nombres',
        max_length=100,
        null=False,
        blank=False
    )
    last_name = models.CharField(
        'Apellidos',
        max_length=100,
        null=False,
        blank=False
    )
    
    # Contacto
    phone = models.CharField(
        'Teléfono',
        max_length=15,
        null=True,
        blank=True
    )
    email = models.EmailField(
        'Correo',
        max_length=100,
        null=True,
        blank=True
    )
    
    # Direcciones
    home_address = models.TextField(
        'Dirección Domicilio',
        null=True,
        blank=True
    )
    business_address = models.TextField(
        'Dirección Negocio',
        null=True,
        blank=True
    )
    
    # Ubicación GPS (del negocio o domicilio)
    latitude = models.DecimalField(
        'Latitud',
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        help_text='Coordenada GPS del negocio o domicilio'
    )
    longitude = models.DecimalField(
        'Longitud',
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        help_text='Coordenada GPS del negocio o domicilio'
    )
    
    # Clasificación del cliente
    classification = models.CharField(
        'Clasificación',
        max_length=30,
        choices=CLIENT_CLASSIFICATION_CHOICES,
        default='REGULAR',
        help_text='Clasificación según historial de pagos'
    )
    
    # Observaciones adicionales
    notes = models.TextField(
        'Observaciones',
        blank=True,
        null=True,
        help_text='Notas adicionales sobre el cliente'
    )
    
    # Estado
    is_active = models.BooleanField('Activo', default=True)
    
    # Auditoría
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    @property
    def full_name(self):
        """Retorna el nombre completo del cliente"""
        return f"{self.first_name} {self.last_name}".strip()
    
    def update_classification(self):
        """
        Actualiza la clasificación del cliente según su historial de pagos.
        Se ejecuta automáticamente cuando hay cambios en los préstamos.
        """
        from apps.loans.models import Loan
        
        # Obtener todos los préstamos del cliente
        loans = Loan.objects.filter(client=self)
        
        if not loans.exists():
            self.classification = 'REGULAR'
            self.save(update_fields=['classification'])
            return
        
        # Contar préstamos morosos y puntuales
        defaulting_count = loans.filter(status__in=['DEFAULTING', 'REFINANCED']).count()
        completed_count = loans.filter(status='COMPLETED').count()
        total_count = loans.count()
        
        # Calcular clasificación
        if defaulting_count == 0 and completed_count > 0:
            self.classification = 'PUNCTUAL'
        elif defaulting_count >= total_count * 0.5:  # Más del 50% morosos
            self.classification = 'SEVERELY_DEFAULTING'
        elif defaulting_count > 0:
            self.classification = 'DEFAULTING'
        else:
            self.classification = 'REGULAR'
        
        self.save(update_fields=['classification'])
    
    def __str__(self):
        return f"{self.dni} - {self.full_name}"
    
    class Meta:
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
        ordering = ['first_name', 'last_name']
        indexes = [
            models.Index(fields=['dni']),
            models.Index(fields=['company', 'zone']),
            models.Index(fields=['classification']),
            models.Index(fields=['is_active']),
        ]


class ClientDocument(models.Model):
    """
    Documentos del Cliente
    
    Almacena fotos de DNI, recibos, contratos y otros documentos del cliente.
    """
    id = models.AutoField(primary_key=True)
    
    # Relación con cliente
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='documents',
        help_text='Cliente al que pertenece este documento'
    )
    
    # Tipo de documento
    document_type = models.CharField(
        'Tipo de Documento',
        max_length=20,
        choices=DOCUMENT_TYPE_CHOICES,
        default='DNI',
        help_text='Tipo de documento (DNI, Recibo, etc.)'
    )
    
    # Archivo (imagen o PDF)
    # Estructura: media/clients/documents/{company_id}/{client_dni}/{tipo_documento}/{nombre_archivo}
    file = models.FileField(
        'Archivo',
        upload_to='clients/documents/',
        help_text='Archivo del documento (DNI, recibo agua/luz, etc.)'
    )
    
    # Descripción
    description = models.TextField(
        'Descripción',
        blank=True,
        null=True,
        help_text='Descripción o notas del documento'
    )
    
    # Auditoría
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.client.full_name} - {self.get_document_type_display()}"
    
    class Meta:
        verbose_name = 'Documento de Cliente'
        verbose_name_plural = 'Documentos de Clientes'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['client', 'document_type']),
        ]
