"""
Modelos de Pagos
Incluye métodos de pago, vouchers y registro de pagos
"""
from django.db import models
from django.utils import timezone
from decimal import Decimal

# Métodos de pago
PAYMENT_METHOD_CHOICES = [
    ('CASH', 'Efectivo'),
    ('YAPE', 'Yape'),
    ('PLIN', 'Plin'),
    ('CARD', 'Tarjeta'),
    ('DAP', 'Depósito'),
    ('TRANSFER', 'Transferencia'),
]

# Estados del pago
PAYMENT_STATUS_CHOICES = [
    ('PENDING', 'Pendiente'),
    ('COMPLETED', 'Completado'),
    ('CANCELLED', 'Cancelado'),
]

# Tipos de ajuste de mora
PENALTY_ADJUSTMENT_TYPE_CHOICES = [
    ('REDUCE', 'Reducir'),
    ('ELIMINATE', 'Eliminar'),
    ('MODIFY', 'Modificar'),
]


class Payment(models.Model):
    """
    Modelo de Pago
    
    Registra cada pago realizado por un cliente.
    Puede cubrir una o más cuotas de un préstamo.
    """
    id = models.AutoField(primary_key=True)
    
    # Relación con empresa
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='payments',
        help_text='Empresa que recibe el pago'
    )
    
    # Relación con préstamo
    loan = models.ForeignKey(
        'loans.Loan',
        on_delete=models.CASCADE,
        related_name='payments',
        help_text='Préstamo al que se aplica el pago'
    )
    
    # Relación con cliente
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.CASCADE,
        related_name='payments',
        help_text='Cliente que realiza el pago'
    )
    
    # Monto del pago
    amount = models.DecimalField(
        'Monto',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Monto pagado en soles (PEN)'
    )
    
    # Fecha de pago
    payment_date = models.DateTimeField(
        'Fecha de Pago',
        default=timezone.now,
        help_text='Fecha y hora del pago'
    )
    
    # Método de pago
    payment_method = models.CharField(
        'Método de Pago',
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default='CASH',
        help_text='Método de pago utilizado'
    )
    
    # Cobrador que registró el pago
    collector = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        related_name='collected_payments',
        null=True,
        blank=True,
        help_text='Cobrador que registró el pago'
    )
    
    # Estado del pago
    status = models.CharField(
        'Estado',
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='COMPLETED',
        help_text='Estado del pago'
    )
    
    # Referencia del pago (número de operación, voucher, etc.)
    reference_number = models.CharField(
        'Número de Referencia',
        max_length=100,
        blank=True,
        null=True,
        help_text='Número de referencia del pago (operación, voucher, etc.)'
    )
    
    # Observaciones
    observations = models.TextField(
        'Observaciones',
        blank=True,
        null=True,
        help_text='Observaciones adicionales sobre el pago'
    )
    
    # Auditoría
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        """
        Guarda el pago y actualiza el estado del préstamo y cuotas.
        El pago se aplica primero a la mora (si existe) y luego a las cuotas
        pendientes en orden. Soporta sobrepago: si el cliente paga más que las
        cuotas seleccionadas, el excedente se aplica a las siguientes cuotas.
        """
        super().save(*args, **kwargs)
        
        # Actualizar préstamo solo si está completado
        if self.status == 'COMPLETED':
            loan = self.loan
            remaining = self.amount
            
            # 1) Aplicar primero a la mora (hasta reducirla a 0)
            if loan.penalty_applied > 0 and remaining > 0:
                amount_to_penalty = min(remaining, loan.penalty_applied)
                loan.penalty_applied -= amount_to_penalty
                loan.save(update_fields=['penalty_applied'])
                remaining -= amount_to_penalty
            
            # 2) Aplicar el resto a cuotas y crear registros PaymentInstallment
            if remaining > 0:
                self._update_installments(remaining)
            
            # 3) Actualizar montos del préstamo
            loan.refresh_from_db()
            loan.paid_amount += self.amount
            loan.pending_amount = loan.total_amount - loan.paid_amount
            
            if loan.pending_amount <= 0:
                loan.status = 'COMPLETED'
            elif loan.end_date < timezone.now().date():
                loan.status = 'DEFAULTING'
            
            loan.save(update_fields=['paid_amount', 'pending_amount', 'status'])
            
            # 4) Clasificación del cliente
            self.client.update_classification()
    
    def _update_installments(self, amount_to_distribute):
        """
        Distribuye el monto entre cuotas pendientes en orden y crea
        PaymentInstallment para auditoría. Soporta sobrepago: si sobra monto,
        se aplica a las siguientes cuotas.
        """
        from apps.loans.models import Installment
        
        installments = Installment.objects.filter(
            loan=self.loan,
            status__in=['PENDING', 'OVERDUE', 'PARTIALLY_PAID']
        ).order_by('installment_number')
        
        remaining_amount = amount_to_distribute
        
        for installment in installments:
            if remaining_amount <= 0:
                break
            
            need = installment.total_amount - installment.paid_amount
            amount_to_apply = min(remaining_amount, need)
            if amount_to_apply <= 0:
                continue
            
            # Crear relación pago-cuota para el voucher y auditoría
            PaymentInstallment.objects.update_or_create(
                defaults={'amount_applied': amount_to_apply},
                payment=self,
                installment=installment
            )
            
            installment.paid_amount += amount_to_apply
            installment.update_status()
            remaining_amount -= amount_to_apply
    
    def __str__(self):
        return f"Pago #{self.id} - {self.client.full_name} - S/ {self.amount}"
    
    class Meta:
        verbose_name = 'Pago'
        verbose_name_plural = 'Pagos'
        ordering = ['-payment_date']
        indexes = [
            models.Index(fields=['company', 'client', 'payment_date']),
            models.Index(fields=['loan', 'status']),
            models.Index(fields=['collector', 'payment_date']),
            models.Index(fields=['payment_method', 'payment_date']),
        ]


class PaymentInstallment(models.Model):
    """
    Modelo intermedio entre Pagos y Cuotas
    
    Relaciona qué cuotas fueron cubiertas por cada pago.
    Un pago puede cubrir múltiples cuotas.
    """
    id = models.AutoField(primary_key=True)
    
    # Relación con pago
    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name='payment_installments',
        help_text='Pago que cubre esta cuota'
    )
    
    # Relación con cuota
    installment = models.ForeignKey(
        'loans.Installment',
        on_delete=models.CASCADE,
        related_name='payment_installments',
        help_text='Cuota cubierta por este pago'
    )
    
    # Monto aplicado a esta cuota específica
    amount_applied = models.DecimalField(
        'Monto Aplicado',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Monto del pago aplicado a esta cuota'
    )
    
    # Auditoría
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Pago #{self.payment.id} - Cuota {self.installment.installment_number}"
    
    class Meta:
        verbose_name = 'Pago-Cuota'
        verbose_name_plural = 'Pagos-Cuotas'
        unique_together = ['payment', 'installment']
        indexes = [
            models.Index(fields=['payment', 'installment']),
        ]


class PenaltyAdjustment(models.Model):
    """
    Modelo de Ajuste de Mora
    
    Registra cuando un administrador ajusta, reduce o elimina la mora.
    Todo ajuste queda registrado para auditoría.
    """
    id = models.AutoField(primary_key=True)
    
    # Relación con préstamo
    loan = models.ForeignKey(
        'loans.Loan',
        on_delete=models.CASCADE,
        related_name='penalty_adjustments',
        help_text='Préstamo al que se aplica el ajuste de mora'
    )
    
    # Tipo de ajuste
    adjustment_type = models.CharField(
        'Tipo de Ajuste',
        max_length=20,
        choices=PENALTY_ADJUSTMENT_TYPE_CHOICES,
        help_text='Tipo de ajuste: Reducir, Eliminar o Modificar'
    )
    
    # Monto anterior de mora
    previous_penalty = models.DecimalField(
        'Mora Anterior',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Monto de mora antes del ajuste'
    )
    
    # Monto nuevo de mora
    new_penalty = models.DecimalField(
        'Mora Nueva',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Monto de mora después del ajuste'
    )
    
    # Motivo del ajuste
    reason = models.TextField(
        'Motivo',
        help_text='Motivo del ajuste de mora'
    )
    
    # Usuario que realizó el ajuste
    adjusted_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        related_name='penalty_adjustments',
        null=True,
        blank=True,
        help_text='Usuario que realizó el ajuste'
    )
    
    # Auditoría
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Ajuste de Mora #{self.id} - Préstamo #{self.loan.id}"
    
    class Meta:
        verbose_name = 'Ajuste de Mora'
        verbose_name_plural = 'Ajustes de Mora'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['loan', 'created_at']),
            models.Index(fields=['adjusted_by', 'created_at']),
        ]
