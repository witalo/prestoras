"""
Modelo de Zonas para organizar clientes y cobradores
Las zonas permiten agrupar clientes geográficamente para rutas de cobranza
"""
from django.db import models

# Opciones para estado de zona
ZONE_STATUS_CHOICES = [
    ('ACTIVE', 'Activa'),
    ('INACTIVE', 'Inactiva'),
]


class Zone(models.Model):
    """
    Modelo de Zona
    
    Las empresas definen zonas para organizar:
    - Clientes por ubicación geográfica
    - Cobradores asignados a zonas específicas
    - Rutas de cobranza optimizadas
    """
    id = models.AutoField(primary_key=True)
    
    # Relación con empresa
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='zones',
        help_text='Empresa a la que pertenece esta zona'
    )
    
    # Nombre de la zona
    name = models.CharField(
        'Nombre',
        max_length=100,
        help_text='Nombre de la zona (ej: Zona Norte, Centro, Sur)'
    )
    
    # Descripción
    description = models.TextField(
        'Descripción',
        blank=True,
        null=True,
        help_text='Descripción de la zona y sus características'
    )
    
    # Ubicación GPS (punto central de la zona)
    latitude = models.DecimalField(
        'Latitud',
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        help_text='Coordenada GPS central de la zona'
    )
    longitude = models.DecimalField(
        'Longitud',
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        help_text='Coordenada GPS central de la zona'
    )
    
    # Nota: Para áreas más complejas, se podría usar PostGIS con PolygonField
    # Por ahora usamos punto GPS central
    
    # Estado
    status = models.CharField(
        'Estado',
        max_length=20,
        choices=ZONE_STATUS_CHOICES,
        default='ACTIVE',
        help_text='Estado de la zona (Activa/Inactiva)'
    )
    
    # Auditoría
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.company.commercial_name} - {self.name}"
    
    class Meta:
        verbose_name = 'Zona'
        verbose_name_plural = 'Zonas'
        ordering = ['company', 'name']
        unique_together = ['company', 'name']
        indexes = [
            models.Index(fields=['company', 'status']),
        ]
