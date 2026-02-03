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

from .models import Payment, PaymentInstallment
from .types import PaymentType
from apps.loans.models import Loan, Installment
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
    installment_ids: List[int],
    payment_methods: List[PaymentMethodInput],
    notes: Optional[str] = None
) -> CreatePaymentResult:
    """
    Mutation para registrar un pago (CRÍTICO)
    
    El cliente puede pagar con múltiples métodos de pago.
    Ejemplo: S/ 50 en efectivo + S/ 30 por Yape = S/ 80 total
    
    IMPORTANTE: 
    - Actualiza automáticamente el estado de las cuotas
    - Actualiza el monto pagado del préstamo
    - Actualiza la clasificación del cliente
    
    Args:
        loan_id: ID del préstamo
        amount: Monto total del pago
        payment_date: Fecha del pago
        collector_id: ID del cobrador que registra el pago
        installment_ids: Lista de IDs de cuotas que se están pagando
        payment_methods: Lista de métodos de pago (puede ser múltiples)
        notes: Notas adicionales (opcional)
    
    Retorna el pago registrado.
    """
    try:
        with transaction.atomic():
            # Validar préstamo
            try:
                loan = Loan.objects.get(id=loan_id)
            except Loan.DoesNotExist:
                return CreatePaymentResult(
                    success=False,
                    message="Préstamo no encontrado",
                    payment=None
                )
            
            # Validar cobrador
            try:
                collector = User.objects.get(id=collector_id, company_id=loan.company_id)
            except User.DoesNotExist:
                return CreatePaymentResult(
                    success=False,
                    message="Cobrador no encontrado",
                    payment=None
                )
            
            # Validar que el cobrador sea cobrador
            # if not collector.is_collector:
            #     return CreatePaymentResult(
            #         success=False,
            #         message="El usuario especificado no es un cobrador",
            #         payment=None
            #     )
            
            # Validar cuotas
            installments = Installment.objects.filter(
                loan_id=loan_id,
                id__in=installment_ids
            )
            
            if installments.count() != len(installment_ids):
                return CreatePaymentResult(
                    success=False,
                    message="Alguna cuota especificada no existe o no pertenece a este préstamo",
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
            
            # Validar que la suma de métodos coincida con el monto total
            if abs(total_methods_amount - amount) > Decimal('0.01'):  # Permitir diferencia mínima por redondeo
                return CreatePaymentResult(
                    success=False,
                    message=f"La suma de métodos de pago ({total_methods_amount}) no coincide con el monto total ({amount})",
                    payment=None
                )
            
            # Validar que el monto no exceda lo pendiente
            if amount > (loan.pending_amount + loan.penalty_applied):
                return CreatePaymentResult(
                    success=False,
                    message=f"El monto del pago ({amount}) excede el saldo pendiente más mora ({loan.pending_amount + loan.penalty_applied})",
                    payment=None
                )
            
            # Crear el pago (por ahora usamos el primer método de pago como método principal)
            # TODO: Implementar soporte completo para múltiples métodos de pago en el modelo
            main_method = payment_methods[0].method if payment_methods else 'CASH'
            
            payment = Payment(
                company_id=loan.company_id,
                loan=loan,
                client=loan.client,
                amount=amount,
                payment_date=datetime.combine(payment_date, timezone.now().time()),
                payment_method=main_method,
                collector=collector,
                observations=notes,
                status='COMPLETED'
            )
            payment.save()
            
            # Crear relaciones PaymentInstallment
            remaining_amount = amount
            installments_list = list(installments.order_by('installment_number'))
            
            for installment in installments_list:
                if remaining_amount <= 0:
                    break
                
                # Calcular cuánto se aplica a esta cuota
                amount_needed = installment.total_amount - installment.paid_amount
                amount_to_apply = min(remaining_amount, amount_needed)
                
                # Crear relación pago-cuota
                PaymentInstallment.objects.create(
                    payment=payment,
                    installment=installment,
                    amount_applied=amount_to_apply
                )
                
                # Actualizar cuota
                installment.paid_amount += amount_to_apply
                installment.update_status()
                
                remaining_amount -= amount_to_apply
            
            # El save() del Payment ya actualiza el préstamo y cliente
            # Pero necesitamos recalcular la mora después del pago
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
            payment.payment_date = datetime.combine(payment_date, timezone.now().time())
        
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
