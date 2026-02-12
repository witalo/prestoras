"""
Mutations GraphQL para Payments usando Strawberry
Incluye registro de pagos con múltiples métodos de pago
"""
import strawberry
from typing import Optional, List
from decimal import Decimal
from datetime import date, datetime
from django.db import transaction
from django.utils import timezone

from .models import Payment
from .types import PaymentType
from apps.loans.models import Loan
from apps.clients.models import Client
from apps.companies.models import Company
from apps.users.models import User


@strawberry.input
class PaymentMethodInput:
    """Input para método de pago"""
    method: str  # EFECTIVO, TARJETA, BCP, YAPE, PLIN, TRANSFER
    amount: Decimal


@strawberry.type
class CreatePaymentResult:
    """Resultado de crear un pago"""
    success: bool
    message: str
    payment: Optional[PaymentType] = None


@strawberry.type
class UpdatePaymentResult:
    """Resultado de actualizar un pago"""
    success: bool
    message: str
    payment: Optional[PaymentType] = None


@strawberry.mutation
def create_payment(
    loan_id: int,
    amount: Decimal,
    payment_date: date,
    collector_id: int,
    payment_methods: List[PaymentMethodInput],
    installment_ids: Optional[List[int]] = None,
    notes: Optional[str] = None
) -> CreatePaymentResult:
    """
    Mutation para registrar un pago (CRÍTICO)
    
    - El monto se aplica primero a la mora (si existe) y luego a las cuotas
      pendientes en orden. Soporta sobrepago: si el cliente paga más que lo
      debido (ej. debe 200 y paga 300), el excedente se aplica a las siguientes
      cuotas.
    - installment_ids es opcional; si se envía vacío o no se envía, el monto se
      distribuye automáticamente sobre todas las cuotas pendientes en orden.
    
    Args:
        loan_id: ID del préstamo
        amount: Monto total del pago
        payment_date: Fecha del pago
        collector_id: ID del cobrador que registra el pago
        payment_methods: Lista de métodos de pago (ej. efectivo + Yape)
        installment_ids: Opcional. Si se indica, solo se usa como referencia;
          la distribución se hace siempre por orden de cuotas.
        notes: Notas adicionales (opcional)
    """
    try:
        with transaction.atomic():
            try:
                loan = Loan.objects.get(id=loan_id)
            except Loan.DoesNotExist:
                return CreatePaymentResult(
                    success=False,
                    message="Préstamo no encontrado",
                    payment=None
                )
            
            try:
                collector = User.objects.get(id=collector_id, company_id=loan.company_id)
            except User.DoesNotExist:
                return CreatePaymentResult(
                    success=False,
                    message="Cobrador no encontrado",
                    payment=None
                )
            
            # Validar métodos de pago
            valid_methods = ['CASH', 'CARD', 'BCP', 'YAPE', 'PLIN', 'TRANSFER']
            total_methods_amount = Decimal('0.00')
            for method_input in payment_methods:
                if method_input.method not in valid_methods:
                    return CreatePaymentResult(
                        success=False,
                        message=f"Método de pago inválido: {method_input.method}. Debe ser uno de: {', '.join(valid_methods)}",
                        payment=None
                    )
                total_methods_amount += method_input.amount
            
            if abs(total_methods_amount - amount) > Decimal('0.01'):
                return CreatePaymentResult(
                    success=False,
                    message=f"La suma de métodos de pago ({total_methods_amount}) no coincide con el monto total ({amount})",
                    payment=None
                )
            
            if amount <= 0:
                return CreatePaymentResult(
                    success=False,
                    message="El monto del pago debe ser mayor a cero",
                    payment=None
                )
            
            # Monto no puede exceder saldo pendiente + mora
            max_allowed = loan.pending_amount + loan.penalty_applied
            if amount > max_allowed:
                return CreatePaymentResult(
                    success=False,
                    message=f"El monto del pago ({amount}) excede el saldo pendiente más mora ({max_allowed})",
                    payment=None
                )
            
            main_method = payment_methods[0].method if payment_methods else 'CASH'
            
            payment = Payment(
                company_id=loan.company_id,
                loan=loan,
                client=loan.client,
                amount=amount,
                payment_date=timezone.make_aware(datetime.combine(payment_date, timezone.now().time())),
                payment_method=main_method,
                collector=collector,
                observations=notes,
                status='COMPLETED'
            )
            payment.save()
            
            # Recalcular mora después del pago (por si hay nuevos días)
            loan.refresh_from_db()
            loan.calculate_penalty()
            
            return CreatePaymentResult(
                success=True,
                message=f"Pago de S/ {amount} registrado exitosamente",
                payment=payment
            )
    
    except Exception as e:
        return CreatePaymentResult(
            success=False,
            message=f"Error al registrar pago: {str(e)}",
            payment=None
        )


@strawberry.mutation
def update_payment(
    payment_id: int,
    amount: Optional[Decimal] = None,
    payment_date: Optional[date] = None,
    payment_methods: Optional[List[PaymentMethodInput]] = None,
    notes: Optional[str] = None
) -> UpdatePaymentResult:
    """
    Mutation para actualizar un pago
    
    Args:
        payment_id: ID del pago a actualizar
        amount: Nuevo monto (opcional)
        payment_date: Nueva fecha (opcional)
        payment_methods: Nuevos métodos de pago (opcional)
        notes: Nuevas notas (opcional)
    
    Retorna el pago actualizado.
    """
    try:
        try:
            payment = Payment.objects.get(id=payment_id)
        except Payment.DoesNotExist:
            return UpdatePaymentResult(
                success=False,
                message="Pago no encontrado",
                payment=None
            )
        
        # Actualizar campos si se proporcionan
        if amount is not None:
            # Validar nuevo monto
            if amount <= 0:
                return UpdatePaymentResult(
                    success=False,
                    message="El monto debe ser mayor a cero",
                    payment=None
                )
            payment.amount = amount
        
        if payment_date is not None:
            payment.payment_date = timezone.make_aware(datetime.combine(payment_date, timezone.now().time()))
        
        if payment_methods is not None:
            # Validar métodos de pago
            valid_methods = ['CASH', 'CARD', 'BCP', 'YAPE', 'PLIN', 'TRANSFER']
            for method_input in payment_methods:
                if method_input.method not in valid_methods:
                    return UpdatePaymentResult(
                        success=False,
                        message=f"Método de pago inválido: {method_input.method}",
                        payment=None
                    )
            # Por ahora solo actualizamos el método principal
            if payment_methods:
                payment.payment_method = payment_methods[0].method
        
        if notes is not None:
            payment.observations = notes
        
        payment.save()
        
        return UpdatePaymentResult(
            success=True,
            message="Pago actualizado exitosamente",
            payment=payment
        )
    
    except Exception as e:
        return UpdatePaymentResult(
            success=False,
            message=f"Error al actualizar pago: {str(e)}",
            payment=None
        )
