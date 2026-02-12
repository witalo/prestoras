"""
Modelos de Préstamos, Cuotas y Refinanciamientos
Incluye toda la lógica de negocio para préstamos, intereses, moras y refinanciamientos
"""
from django.db import models
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta

# Estados del préstamo
LOAN_STATUS_CHOICES = [
    ('ACTIVE', 'Activo'),
    ('COMPLETED', 'Completado'),
    ('DEFAULTING', 'Moroso'),
    ('REFINANCED', 'Refinanciado'),
    ('CANCELLED', 'Cancelado'),
]

# Estados de cuota
INSTALLMENT_STATUS_CHOICES = [
    ('PENDING', 'Pendiente'),
    ('PAID', 'Pagada'),
    ('OVERDUE', 'Vencida'),
    ('PARTIALLY_PAID', 'Parcialmente Pagada'),
    ('CANCELLED', 'Cancelada'),
]

# Tipos de mora
PENALTY_TYPE_CHOICES = [
    ('FIXED', 'Fija'),
    ('PERCENTAGE', 'Porcentual'),
]

# Estados de refinanciamiento
REFINANCING_STATUS_CHOICES = [
    ('PENDING', 'Pendiente'),
    ('APPROVED', 'Aprobado'),
    ('REJECTED', 'Rechazado'),
    ('CANCELLED', 'Cancelado'),
]


class Loan(models.Model):
    """
    Modelo de Préstamo/Crédito
    
    Representa un crédito otorgado a un cliente.
    Un cliente puede tener múltiples préstamos activos simultáneamente.
    """
    id = models.AutoField(primary_key=True)
    
    # Relación con empresa
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='loans',
        help_text='Empresa que otorga el préstamo'
    )
    
    # Relación con cliente
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.CASCADE,
        related_name='loans',
        help_text='Cliente que recibe el préstamo'
    )
    
    # Relación con tipo de préstamo (opcional, puede ser personalizado)
    loan_type = models.ForeignKey(
        'companies.LoanType',
        on_delete=models.SET_NULL,
        related_name='loans',
        null=True,
        blank=True,
        help_text='Tipo de préstamo de referencia (puede ser modificado)'
    )
    
    # Monto del préstamo
    initial_amount = models.DecimalField(
        'Monto Inicial',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Monto inicial del préstamo en soles (PEN)'
    )
    
    # Tasa de interés (%)
    interest_rate = models.DecimalField(
        'Tasa de Interés (%)',
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Tasa de interés en porcentaje (ej: 8.00 para 8%)'
    )
    
    # Número de cuotas
    number_of_installments = models.IntegerField(
        'Número de Cuotas',
        default=1,
        help_text='Número total de cuotas del préstamo'
    )
    
    # Periodicidad
    periodicity = models.CharField(
        'Periodicidad',
        max_length=20,
        choices=[
            ('DAILY', 'Diario'),
            ('WEEKLY', 'Semanal'),
            ('BIWEEKLY', 'Quincenal'),
            ('MONTHLY', 'Mensual'),
            ('QUARTERLY', 'Trimestral'),  # Cada 3 meses
            ('CUSTOM', 'Personalizado'),
        ],
        default='DAILY',
        help_text='Frecuencia de pago de las cuotas'
    )
    
    # Fechas
    start_date = models.DateField(
        'Fecha de Inicio',
        help_text='Fecha de inicio del préstamo'
    )
    end_date = models.DateField(
        'Fecha de Vencimiento',
        help_text='Fecha final de vencimiento del préstamo'
    )
    
    # Monto total a pagar (calculado)
    total_amount = models.DecimalField(
        'Monto Total',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Monto total a pagar (capital + intereses)'
    )
    
    # Monto pagado hasta el momento
    paid_amount = models.DecimalField(
        'Monto Pagado',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Monto total pagado hasta el momento'
    )
    
    # Saldo pendiente
    pending_amount = models.DecimalField(
        'Saldo Pendiente',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Saldo pendiente por pagar'
    )
    
    # Configuración de mora
    penalty_type = models.CharField(
        'Tipo de Mora',
        max_length=20,
        choices=PENALTY_TYPE_CHOICES,
        null=True,
        blank=True,
        help_text='Tipo de mora: Fija o Porcentual'
    )
    penalty_amount = models.DecimalField(
        'Monto de Mora Fija',
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        default=Decimal('0.00'),
        help_text='Monto fijo de mora (si aplica)'
    )
    penalty_percentage = models.DecimalField(
        'Porcentaje de Mora',
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        default=Decimal('0.00'),
        help_text='Porcentaje de mora por día (si aplica)'
    )
    
    # Mora aplicada hasta el momento
    penalty_applied = models.DecimalField(
        'Mora Aplicada',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Mora total aplicada hasta el momento'
    )
    
    # Estado del préstamo
    status = models.CharField(
        'Estado',
        max_length=20,
        choices=LOAN_STATUS_CHOICES,
        default='ACTIVE',
        help_text='Estado actual del préstamo'
    )
    
    # Observaciones
    observations = models.TextField(
        'Observaciones',
        blank=True,
        null=True,
        help_text='Observaciones adicionales sobre el préstamo'
    )
    
    # Refinanciamiento
    original_loan = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        related_name='refinanced_loans',
        null=True,
        blank=True,
        help_text='Préstamo original si este es un refinanciamiento'
    )
    is_refinanced = models.BooleanField(
        'Es Refinanciado',
        default=False,
        help_text='Indica si este préstamo es resultado de un refinanciamiento'
    )
    
    # Auditoría
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        related_name='created_loans',
        null=True,
        blank=True,
        help_text='Usuario que creó el préstamo'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def calculate_total_amount(self):
        """
        Calcula el monto total del préstamo (capital + intereses)
        Fórmula: Total = Capital + (Capital * Tasa de Interés / 100)
        """
        interest = (self.initial_amount * self.interest_rate) / Decimal('100')
        self.total_amount = self.initial_amount + interest
        self.pending_amount = self.total_amount - self.paid_amount
        return self.total_amount
    
    def calculate_penalty(self):
        """
        Calcula la mora aplicada si el préstamo está vencido.
        La mora solo se aplica si se supera la fecha final del crédito.
        """
        if self.status in ['COMPLETED', 'CANCELLED']:
            return Decimal('0.00')
        
        today = timezone.now().date()
        
        # Solo aplicar mora si se supera la fecha final
        if today <= self.end_date:
            return Decimal('0.00')
        
        days_overdue = (today - self.end_date).days
        
        if self.penalty_type == 'FIXED' and self.penalty_amount:
            # Mora fija por día
            penalty = self.penalty_amount * days_overdue
        elif self.penalty_type == 'PERCENTAGE' and self.penalty_percentage:
            # Mora porcentual por día sobre el saldo pendiente
            daily_penalty = (self.pending_amount * self.penalty_percentage) / Decimal('100')
            penalty = daily_penalty * days_overdue
        else:
            penalty = Decimal('0.00')
        
        self.penalty_applied = penalty
        self.save(update_fields=['penalty_applied'])
        
        return penalty
    
    def save(self, *args, **kwargs):
        """
        Guarda el préstamo y calcula automáticamente los montos
        """
        # Calcular monto total si no está calculado o si cambió el monto inicial o tasa
        if not self.total_amount or self.pk is None:
            self.calculate_total_amount()
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Préstamo #{self.id} - {self.client.full_name} - S/ {self.initial_amount}"
    
    class Meta:
        verbose_name = 'Préstamo'
        verbose_name_plural = 'Préstamos'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'client', 'status']),
            models.Index(fields=['status', 'end_date']),
            models.Index(fields=['client', 'status']),
            models.Index(fields=['original_loan']),
        ]


class Installment(models.Model):
    """
    Modelo de Cuota
    
    Representa una cuota de pago del préstamo.
    Se generan automáticamente al crear el préstamo.
    """
    id = models.AutoField(primary_key=True)
    
    # Relación con préstamo
    loan = models.ForeignKey(
        Loan,
        on_delete=models.CASCADE,
        related_name='installments',
        help_text='Préstamo al que pertenece esta cuota'
    )
    
    # Número de cuota
    installment_number = models.IntegerField(
        'Número de Cuota',
        help_text='Número de la cuota (1, 2, 3, ...)'
    )
    
    # Fecha de pago
    due_date = models.DateField(
        'Fecha de Vencimiento',
        help_text='Fecha de vencimiento de la cuota'
    )
    
    # Montos
    capital_amount = models.DecimalField(
        'Capital',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Monto de capital de esta cuota'
    )
    interest_amount = models.DecimalField(
        'Interés',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Monto de interés de esta cuota'
    )
    total_amount = models.DecimalField(
        'Total',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Monto total de la cuota (capital + interés)'
    )
    
    # Monto pagado
    paid_amount = models.DecimalField(
        'Monto Pagado',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Monto pagado de esta cuota'
    )
    
    # Estado
    status = models.CharField(
        'Estado',
        max_length=20,
        choices=INSTALLMENT_STATUS_CHOICES,
        default='PENDING',
        help_text='Estado actual de la cuota'
    )
    
    # Auditoría
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def update_status(self):
        """Actualiza el estado de la cuota según pagos y fecha"""
        today = timezone.now().date()
        
        if self.paid_amount >= self.total_amount:
            self.status = 'PAID'
        elif self.paid_amount > 0:
            self.status = 'PARTIALLY_PAID'
        elif today > self.due_date:
            self.status = 'OVERDUE'
        else:
            self.status = 'PENDING'
        
        self.save(update_fields=['status'])
    
    def __str__(self):
        return f"Cuota {self.installment_number} - {self.loan.client.full_name} - {self.due_date}"
    
    class Meta:
        verbose_name = 'Cuota'
        verbose_name_plural = 'Cuotas'
        ordering = ['loan', 'installment_number']
        unique_together = ['loan', 'installment_number']
        indexes = [
            models.Index(fields=['loan', 'status']),
            models.Index(fields=['due_date', 'status']),
        ]


class Refinancing(models.Model):
    """
    Modelo de Refinanciamiento
    
    Registra cuando un préstamo es refinanciado.
    El refinanciamiento crea un nuevo préstamo vinculado al original.
    """
    id = models.AutoField(primary_key=True)
    
    # Relación con préstamo original
    original_loan = models.ForeignKey(
        Loan,
        on_delete=models.CASCADE,
        related_name='refinancings',
        help_text='Préstamo original que se refinancia'
    )
    
    # Relación con nuevo préstamo
    new_loan = models.OneToOneField(
        Loan,
        on_delete=models.CASCADE,
        related_name='refinancing',
        null=True,
        blank=True,
        help_text='Nuevo préstamo creado por el refinanciamiento'
    )
    
    # Saldo pendiente del préstamo original al momento del refinanciamiento
    outstanding_balance = models.DecimalField(
        'Saldo Pendiente',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Saldo pendiente del préstamo original al refinanciar'
    )
    
    # Monto refinanciado (capital del nuevo préstamo)
    refinanced_amount = models.DecimalField(
        'Monto Refinanciado',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Monto del nuevo préstamo refinanciado'
    )
    
    # Tasa de interés aplicada en el refinanciamiento
    interest_rate = models.DecimalField(
        'Tasa de Interés (%)',
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Tasa de interés aplicada en el refinanciamiento'
    )
    
    # Nuevo plazo
    new_period_days = models.IntegerField(
        'Nuevo Plazo (Días)',
        help_text='Nuevo plazo del préstamo refinanciado en días'
    )
    
    # Motivo del refinanciamiento
    reason = models.TextField(
        'Motivo',
        blank=True,
        null=True,
        help_text='Motivo del refinanciamiento'
    )
    
    # Estado
    status = models.CharField(
        'Estado',
        max_length=20,
        choices=REFINANCING_STATUS_CHOICES,
        default='PENDING',
        help_text='Estado del refinanciamiento'
    )
    
    # Auditoría
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        related_name='created_refinancings',
        null=True,
        blank=True,
        help_text='Usuario que creó el refinanciamiento'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Refinanciamiento #{self.id} - Préstamo Original #{self.original_loan.id}"
    
    class Meta:
        verbose_name = 'Refinanciamiento'
        verbose_name_plural = 'Refinanciamientos'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['original_loan', 'status']),
            models.Index(fields=['status']),
        ]
