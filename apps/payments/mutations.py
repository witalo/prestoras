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

from strawberry.types import Info
from .models import Payment
from .types import PaymentType
from apps.loans.models import Loan
from apps.clients.models import Client
from apps.companies.models import Company
from apps.users.models import User
from prestoras.utils_auth import get_current_user_from_info


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
    info: Info,
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
    current_user = get_current_user_from_info(info)
    if not current_user:
        return CreatePaymentResult(success=False, message="No autorizado.", payment=None)
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

            if current_user.company_id != loan.company_id:
                return CreatePaymentResult(success=False, message="No puede registrar pagos de otra empresa.", payment=None)

            if current_user.role == 'COLLECTOR':
                # El cobrador solo puede registrar pagos como sí mismo y sobre sus clientes
                if current_user.id != collector_id:
                    return CreatePaymentResult(success=False, message="Un cobrador solo puede registrar pagos a su nombre.", payment=None)
                if not current_user.assigned_clients.filter(id=loan.client_id).exists():
                    return CreatePaymentResult(success=False, message="Este cliente no está en su cartera.", payment=None)

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
            
            paid_dt = timezone.make_aware(datetime.combine(payment_date, timezone.localtime().time()))
            first_payment = None

            # Crear un Payment por cada método — así los reportes/filtros son exactos
            for method_input in payment_methods:
                p = Payment(
                    company_id=loan.company_id,
                    loan=loan,
                    client=loan.client,
                    amount=method_input.amount,
                    payment_date=paid_dt,
                    payment_method=method_input.method,
                    collector=collector,
                    observations=notes,
                    status='COMPLETED'
                )
                p.save()
                if first_payment is None:
                    first_payment = p

            # Recalcular mora después del pago
            loan.refresh_from_db()
            loan.calculate_penalty()

            return CreatePaymentResult(
                success=True,
                message=f"Pago de S/ {amount} registrado exitosamente",
                payment=first_payment
            )
    
    except Exception as e:
        return CreatePaymentResult(
            success=False,
            message=f"Error al registrar pago: {str(e)}",
            payment=None
        )


@strawberry.type
class CorrectPaymentResult:
    success: bool
    message: str
    payment: Optional[PaymentType] = None


@strawberry.mutation
def correct_payment(
    info: Info,
    payment_id: int,
    new_amount: Decimal,
    new_payment_method: Optional[str] = None,
) -> CorrectPaymentResult:
    """
    Corrige el monto (y opcionalmente el método) de un pago ya registrado.
    Revierte todas las cuotas y el préstamo antes de aplicar el nuevo monto.
    Solo ADMIN puede usar esta acción.
    """
    current_user = get_current_user_from_info(info)
    if not current_user or current_user.role != 'ADMIN':
        return CorrectPaymentResult(success=False, message="Solo el administrador puede corregir pagos.", payment=None)
    try:
        with transaction.atomic():
            try:
                payment = Payment.objects.select_for_update().get(id=payment_id)
            except Payment.DoesNotExist:
                return CorrectPaymentResult(success=False, message="Pago no encontrado.", payment=None)

            if payment.company_id != current_user.company_id:
                return CorrectPaymentResult(success=False, message="Sin permiso sobre este pago.", payment=None)

            if payment.status != 'COMPLETED':
                return CorrectPaymentResult(success=False, message="Solo se pueden corregir pagos completados.", payment=None)

            if new_amount <= 0:
                return CorrectPaymentResult(success=False, message="El monto debe ser mayor a cero.", payment=None)

            if new_payment_method:
                valid_methods = ['CASH', 'CARD', 'BCP', 'YAPE', 'PLIN', 'TRANSFER']
                if new_payment_method not in valid_methods:
                    return CorrectPaymentResult(success=False, message=f"Método inválido: {new_payment_method}.", payment=None)

            from apps.loans.models import Installment
            from django.db.models import Sum as DSum

            loan = payment.loan
            old_amount = payment.amount

            # ── 1. Calcular cuánto fue a mora vs cuotas ────────────────────────
            total_to_installments = payment.payment_installments.aggregate(
                t=DSum('amount_applied')
            )['t'] or Decimal('0.00')
            amount_to_penalty_old = old_amount - total_to_installments

            # ── 2. Revertir cuotas ─────────────────────────────────────────────
            affected_inst_ids = list(
                payment.payment_installments.values_list('installment_id', flat=True)
            )
            payment.payment_installments.all().delete()

            for inst_id in affected_inst_ids:
                total = Payment.objects.filter(
                    payment_installments__installment_id=inst_id
                ).aggregate(t=DSum('payment_installments__amount_applied'))['t'] or Decimal('0.00')
                # Usar SUM de PIs restantes para recalcular
                from apps.payments.models import PaymentInstallment as PI
                total = PI.objects.filter(
                    installment_id=inst_id
                ).aggregate(t=DSum('amount_applied'))['t'] or Decimal('0.00')
                inst = Installment.objects.get(id=inst_id)
                inst.paid_amount = total
                inst.save(update_fields=['paid_amount'])
                inst.update_status()

            # ── 3. Revertir préstamo ───────────────────────────────────────────
            loan.refresh_from_db()
            loan.paid_amount -= old_amount
            loan.penalty_applied += amount_to_penalty_old
            loan.pending_amount = loan.total_amount - loan.paid_amount
            loan.status = 'ACTIVE'
            loan.save(update_fields=['paid_amount', 'pending_amount', 'penalty_applied', 'status'])

            # ── 4. Actualizar el pago sin triggear Payment.save() ──────────────
            update_fields_payment = {'amount': new_amount}
            if new_payment_method:
                update_fields_payment['payment_method'] = new_payment_method
            Payment.objects.filter(id=payment_id).update(**update_fields_payment)
            payment.refresh_from_db()

            # ── 5. Aplicar nuevo monto (misma lógica que Payment.save()) ───────
            remaining = new_amount

            if loan.penalty_applied > 0 and remaining > 0:
                to_penalty = min(remaining, loan.penalty_applied)
                loan.penalty_applied -= to_penalty
                loan.save(update_fields=['penalty_applied'])
                remaining -= to_penalty

            if remaining > 0:
                installments = Installment.objects.filter(
                    loan=loan,
                    status__in=['PENDING', 'OVERDUE', 'PARTIALLY_PAID']
                ).order_by('installment_number')

                from apps.payments.models import PaymentInstallment as PI2
                for inst in installments:
                    if remaining <= 0:
                        break
                    need = inst.total_amount - inst.paid_amount
                    to_apply = min(remaining, need)
                    if to_apply <= 0:
                        continue
                    PI2.objects.create(payment=payment, installment=inst, amount_applied=to_apply)
                    inst.paid_amount += to_apply
                    inst.save(update_fields=['paid_amount'])
                    inst.update_status()
                    remaining -= to_apply

            # ── 6. Actualizar préstamo con nuevo monto ─────────────────────────
            loan.refresh_from_db()
            loan.paid_amount += new_amount
            loan.pending_amount = loan.total_amount - loan.paid_amount
            if loan.pending_amount <= Decimal('0.00'):
                loan.status = 'COMPLETED'
            elif loan.end_date and loan.end_date < timezone.now().date():
                loan.status = 'DEFAULTING'
            else:
                loan.status = 'ACTIVE'
            loan.save(update_fields=['paid_amount', 'pending_amount', 'status'])

            # ── 7. Clasificación del cliente ───────────────────────────────────
            payment.client.update_classification()

            return CorrectPaymentResult(
                success=True,
                message=f"Pago #{payment_id} corregido: S/ {old_amount} → S/ {new_amount}",
                payment=payment
            )
    except Exception as e:
        return CorrectPaymentResult(success=False, message=f"Error al corregir pago: {str(e)}", payment=None)


@strawberry.type
class DeletePaymentResult:
    success: bool
    message: str


@strawberry.mutation
def delete_payment(info: Info, payment_id: int) -> DeletePaymentResult:
    """
    Elimina un pago y revierte todos sus efectos en cuotas y préstamo.
    Borra los PaymentInstallment, restaura paid_amount/status de cada cuota,
    y ajusta paid_amount/pending_amount/status del préstamo.
    Solo ADMIN.
    """
    current_user = get_current_user_from_info(info)
    if not current_user or current_user.role != 'ADMIN':
        return DeletePaymentResult(success=False, message="Solo el administrador puede eliminar pagos.")
    try:
        with transaction.atomic():
            try:
                payment = Payment.objects.select_for_update().select_related('loan', 'client').get(id=payment_id)
            except Payment.DoesNotExist:
                return DeletePaymentResult(success=False, message="Pago no encontrado.")

            if payment.company_id != current_user.company_id:
                return DeletePaymentResult(success=False, message="Sin permiso sobre este pago.")

            if payment.status != 'COMPLETED':
                return DeletePaymentResult(success=False, message="Solo se pueden eliminar pagos completados.")

            from apps.loans.models import Installment
            from django.db.models import Sum as DSum
            from apps.payments.models import PaymentInstallment as PI

            loan  = payment.loan
            client = payment.client
            old_amount = payment.amount

            # ── 1. Calcular cuánto fue a mora vs cuotas ────────────────────────
            total_to_installments = payment.payment_installments.aggregate(
                t=DSum('amount_applied')
            )['t'] or Decimal('0.00')
            amount_to_penalty = old_amount - total_to_installments

            # ── 2. Revertir cuotas afectadas (borra PaymentInstallment) ────────
            affected_inst_ids = list(
                payment.payment_installments.values_list('installment_id', flat=True)
            )
            payment.payment_installments.all().delete()

            for inst_id in affected_inst_ids:
                # Recalcular paid_amount con los PI que quedan (de otros pagos)
                remaining = PI.objects.filter(
                    installment_id=inst_id
                ).aggregate(t=DSum('amount_applied'))['t'] or Decimal('0.00')
                inst = Installment.objects.get(id=inst_id)
                inst.paid_amount = remaining
                inst.save(update_fields=['paid_amount'])
                inst.update_status()

            # ── 3. Revertir préstamo ───────────────────────────────────────────
            loan.refresh_from_db()
            loan.paid_amount    = max(Decimal('0.00'), loan.paid_amount - old_amount)
            loan.penalty_applied += amount_to_penalty
            loan.pending_amount  = loan.total_amount - loan.paid_amount
            if loan.pending_amount <= Decimal('0.00'):
                loan.status = 'COMPLETED'
            elif loan.end_date and loan.end_date < timezone.now().date():
                loan.status = 'DEFAULTING'
            else:
                loan.status = 'ACTIVE'
            loan.save(update_fields=['paid_amount', 'pending_amount', 'penalty_applied', 'status'])

            # ── 4. Reclasificar cliente ────────────────────────────────────────
            client.update_classification()

            # ── 5. Eliminar el pago (limpia el rastro) ─────────────────────────
            payment.delete()

            return DeletePaymentResult(success=True, message=f"Pago #{payment_id} eliminado correctamente.")

    except Exception as e:
        return DeletePaymentResult(success=False, message=f"Error al eliminar pago: {str(e)}")


@strawberry.mutation
def update_payment(
    info: Info,
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
    current_user = get_current_user_from_info(info)
    if not current_user or current_user.role != 'ADMIN':
        return UpdatePaymentResult(success=False, message="Solo el administrador puede modificar pagos.", payment=None)
    try:
        try:
            payment = Payment.objects.get(id=payment_id)
        except Payment.DoesNotExist:
            return UpdatePaymentResult(
                success=False,
                message="Pago no encontrado",
                payment=None
            )
        if payment.company_id != current_user.company_id:
            return UpdatePaymentResult(success=False, message="No puede modificar pagos de otra empresa.", payment=None)
        
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
            payment.payment_date = timezone.make_aware(datetime.combine(payment_date, timezone.localtime().time()))
        
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
