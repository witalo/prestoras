"""
Mutations GraphQL para Loans usando Strawberry
Incluye creación, actualización, ajuste de mora y refinanciamiento de préstamos
"""
import strawberry
from typing import Optional, List
from decimal import Decimal
from datetime import date, timedelta
from django.db import transaction
from django.utils import timezone

from .models import Loan, Installment
from .types import LoanType
from apps.companies.models import Company
from apps.clients.models import Client
from apps.companies.models import LoanType as CompanyLoanType
from apps.payments.models import Payment


@strawberry.type
class CreateLoanResult:
    """Resultado de crear un préstamo"""
    success: bool
    message: str
    loan: Optional[LoanType] = None


@strawberry.type
class UpdateLoanResult:
    """Resultado de actualizar un préstamo"""
    success: bool
    message: str
    loan: Optional[LoanType] = None


@strawberry.type
class UpdateLoanPenaltyResult:
    """Resultado de actualizar la mora de un préstamo"""
    success: bool
    message: str
    loan: Optional[LoanType] = None


@strawberry.type
class RefinanceLoanResult:
    """Resultado de refinanciar un préstamo"""
    success: bool
    message: str
    loan: Optional[LoanType] = None


@strawberry.type
class DeleteLoanResult:
    """Resultado de eliminar un préstamo"""
    success: bool
    message: str


def generate_installments(loan: Loan):
    """
    Genera automáticamente las cuotas del préstamo según la periodicidad.
    
    Calcula:
    - Capital por cuota = Monto inicial / Número de cuotas
    - Interés por cuota = (Monto inicial * Tasa de interés / 100) / Número de cuotas
    - Total por cuota = Capital + Interés
    - Fecha de cada cuota según la periodicidad
    """
    installments = []
    capital_per_installment = loan.initial_amount / Decimal(str(loan.number_of_installments))
    total_interest = (loan.initial_amount * loan.interest_rate) / Decimal('100')
    interest_per_installment = total_interest / Decimal(str(loan.number_of_installments))
    total_per_installment = capital_per_installment + interest_per_installment
    
    # Calcular intervalo de días según periodicidad
    days_interval = {
        'DAILY': 1,
        'WEEKLY': 7,
        'BIWEEKLY': 14,
        'MONTHLY': 30,
        'QUARTERLY': 90,
        'CUSTOM': int((loan.end_date - loan.start_date).days / loan.number_of_installments)
    }
    interval = days_interval.get(loan.periodicity, 1)
    
    current_date = loan.start_date
    
    for i in range(1, loan.number_of_installments + 1):
        # La última cuota se ajusta para llegar exactamente a end_date
        if i == loan.number_of_installments:
            current_date = loan.end_date
            # Ajustar montos para la última cuota (ajustar por redondeo)
            remaining_capital = loan.initial_amount - (capital_per_installment * (loan.number_of_installments - 1))
            remaining_interest = total_interest - (interest_per_installment * (loan.number_of_installments - 1))
            total_for_last = remaining_capital + remaining_interest
        else:
            total_for_last = total_per_installment
        
        installment = Installment(
            loan=loan,
            installment_number=i,
            due_date=current_date,
            capital_amount=capital_per_installment if i < loan.number_of_installments else remaining_capital,
            interest_amount=interest_per_installment if i < loan.number_of_installments else remaining_interest,
            total_amount=total_for_last,
            status='PENDING'
        )
        installments.append(installment)
        
        current_date += timedelta(days=interval)
    
    # Crear todas las cuotas en una sola transacción
    Installment.objects.bulk_create(installments)
    return installments


@strawberry.mutation
def create_loan(
    company_id: int,
    client_id: int,
    initial_amount: Decimal,
    interest_rate: Decimal,
    number_of_installments: int,
    periodicity: str,
    start_date: date,
    end_date: date,
    loan_type_id: Optional[int] = None,
    penalty_type: Optional[str] = None,
    penalty_amount: Optional[Decimal] = None,
    penalty_percentage: Optional[Decimal] = None,
    observations: Optional[str] = None
) -> CreateLoanResult:
    """
    Mutation para crear un nuevo préstamo
    
    IMPORTANTE: Genera automáticamente todas las cuotas según la periodicidad.
    
    Args:
        company_id: ID de la empresa
        client_id: ID del cliente
        loan_type_id: ID del tipo de préstamo (opcional, puede ser personalizado)
        initial_amount: Monto inicial del préstamo
        interest_rate: Tasa de interés en porcentaje (ej: 8.00 para 8%)
        number_of_installments: Número de cuotas
        periodicity: Periodicidad (DAILY, WEEKLY, BIWEEKLY, MONTHLY, QUARTERLY, CUSTOM)
        start_date: Fecha de inicio
        end_date: Fecha de vencimiento final
        penalty_type: Tipo de mora (FIXED, PERCENTAGE) - opcional
        penalty_amount: Monto fijo de mora por día - opcional
        penalty_percentage: Porcentaje de mora por día - opcional
        observations: Observaciones - opcional
    
    Retorna el préstamo creado con sus cuotas generadas.
    """
    try:
        with transaction.atomic():
            # Validar empresa
            try:
                company = Company.objects.get(id=company_id)
            except Company.DoesNotExist:
                return CreateLoanResult(
                    success=False,
                    message="Empresa no encontrada",
                    loan=None
                )
            
            # Validar cliente
            try:
                client = Client.objects.get(id=client_id, company_id=company_id)
            except Client.DoesNotExist:
                return CreateLoanResult(
                    success=False,
                    message="Cliente no encontrado",
                    loan=None
                )
            
            # Validar tipo de préstamo si se proporciona
            loan_type = None
            if loan_type_id:
                try:
                    loan_type = CompanyLoanType.objects.get(id=loan_type_id, company_id=company_id)
                except CompanyLoanType.DoesNotExist:
                    return CreateLoanResult(
                        success=False,
                        message="Tipo de préstamo no encontrado",
                        loan=None
                    )
            
            # Validar periodicidad
            valid_periodicities = ['DAILY', 'WEEKLY', 'BIWEEKLY', 'MONTHLY', 'QUARTERLY', 'CUSTOM']
            if periodicity not in valid_periodicities:
                return CreateLoanResult(
                    success=False,
                    message=f"Periodicidad inválida. Debe ser una de: {', '.join(valid_periodicities)}",
                    loan=None
                )
            
            # Validar fechas
            if start_date >= end_date:
                return CreateLoanResult(
                    success=False,
                    message="La fecha de inicio debe ser anterior a la fecha de vencimiento",
                    loan=None
                )
            
            # Validar mora
            if penalty_type:
                valid_penalty_types = ['FIXED', 'PERCENTAGE']
                if penalty_type not in valid_penalty_types:
                    return CreateLoanResult(
                        success=False,
                        message="Tipo de mora inválido. Debe ser FIXED o PERCENTAGE",
                        loan=None
                    )
                
                if penalty_type == 'FIXED' and not penalty_amount:
                    return CreateLoanResult(
                        success=False,
                        message="Debe proporcionar penalty_amount para mora fija",
                        loan=None
                    )
                
                if penalty_type == 'PERCENTAGE' and not penalty_percentage:
                    return CreateLoanResult(
                        success=False,
                        message="Debe proporcionar penalty_percentage para mora porcentual",
                        loan=None
                    )
            
            # Crear el préstamo
            loan = Loan(
                company=company,
                client=client,
                loan_type=loan_type,
                initial_amount=initial_amount,
                interest_rate=interest_rate,
                number_of_installments=number_of_installments,
                periodicity=periodicity,
                start_date=start_date,
                end_date=end_date,
                penalty_type=penalty_type,
                penalty_amount=penalty_amount or Decimal('0.00'),
                penalty_percentage=penalty_percentage or Decimal('0.00'),
                observations=observations,
                status='ACTIVE',
                is_refinanced=False
            )
            
            # Calcular monto total (capital + intereses)
            loan.calculate_total_amount()
            loan.save()
            
            # Generar cuotas automáticamente
            generate_installments(loan)
            
            # Actualizar clasificación del cliente
            client.update_classification()
            
            return CreateLoanResult(
                success=True,
                message=f"Préstamo creado exitosamente con {number_of_installments} cuotas",
                loan=loan
            )
    
    except Exception as e:
        return CreateLoanResult(
            success=False,
            message=f"Error al crear préstamo: {str(e)}",
            loan=None
        )


@strawberry.mutation
def update_loan(
    loan_id: int,
    interest_rate: Optional[Decimal] = None,
    number_of_installments: Optional[int] = None,
    periodicity: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    penalty_type: Optional[str] = None,
    penalty_amount: Optional[Decimal] = None,
    penalty_percentage: Optional[Decimal] = None,
    observations: Optional[str] = None,
    status: Optional[str] = None
) -> UpdateLoanResult:
    """
    Mutation para actualizar un préstamo
    
    Args:
        loan_id: ID del préstamo a actualizar
        interest_rate: Nueva tasa de interés (opcional)
        number_of_installments: Nuevo número de cuotas (opcional, regenerará cuotas)
        periodicity: Nueva periodicidad (opcional)
        start_date: Nueva fecha de inicio (opcional)
        end_date: Nueva fecha de vencimiento (opcional)
        penalty_type: Nuevo tipo de mora (opcional)
        penalty_amount: Nuevo monto de mora fija (opcional)
        penalty_percentage: Nuevo porcentaje de mora (opcional)
        observations: Nuevas observaciones (opcional)
        status: Nuevo estado (opcional)
    
    Retorna el préstamo actualizado.
    """
    try:
        with transaction.atomic():
            try:
                loan = Loan.objects.get(id=loan_id)
            except Loan.DoesNotExist:
                return UpdateLoanResult(
                    success=False,
                    message="Préstamo no encontrado",
                    loan=None
                )
            
            # Actualizar campos si se proporcionan
            if interest_rate is not None:
                loan.interest_rate = interest_rate
                loan.calculate_total_amount()
            
            if periodicity is not None:
                valid_periodicities = ['DAILY', 'WEEKLY', 'BIWEEKLY', 'MONTHLY', 'QUARTERLY', 'CUSTOM']
                if periodicity not in valid_periodicities:
                    return UpdateLoanResult(
                        success=False,
                        message=f"Periodicidad inválida. Debe ser una de: {', '.join(valid_periodicities)}",
                        loan=None
                    )
                loan.periodicity = periodicity
            
            if start_date is not None:
                loan.start_date = start_date
            
            if end_date is not None:
                if loan.start_date >= end_date:
                    return UpdateLoanResult(
                        success=False,
                        message="La fecha de inicio debe ser anterior a la fecha de vencimiento",
                        loan=None
                    )
                loan.end_date = end_date
            
            if number_of_installments is not None:
                # Solo regenerar cuotas si aún no hay pagos
                if loan.paid_amount > 0:
                    return UpdateLoanResult(
                        success=False,
                        message="No se puede modificar el número de cuotas si ya hay pagos registrados",
                        loan=None
                    )
                loan.number_of_installments = number_of_installments
                # Eliminar cuotas anteriores y crear nuevas
                loan.installments.all().delete()
                generate_installments(loan)
            
            if penalty_type is not None:
                valid_penalty_types = ['FIXED', 'PERCENTAGE']
                if penalty_type not in valid_penalty_types:
                    return UpdateLoanResult(
                        success=False,
                        message="Tipo de mora inválido. Debe ser FIXED o PERCENTAGE",
                        loan=None
                    )
                loan.penalty_type = penalty_type
            
            if penalty_amount is not None:
                loan.penalty_amount = penalty_amount
            
            if penalty_percentage is not None:
                loan.penalty_percentage = penalty_percentage
            
            if observations is not None:
                loan.observations = observations
            
            if status is not None:
                valid_statuses = ['ACTIVE', 'COMPLETED', 'DEFAULTING', 'REFINANCED', 'CANCELLED']
                if status not in valid_statuses:
                    return UpdateLoanResult(
                        success=False,
                        message=f"Estado inválido. Debe ser uno de: {', '.join(valid_statuses)}",
                        loan=None
                    )
                loan.status = status
            
            loan.save()
            
            return UpdateLoanResult(
                success=True,
                message="Préstamo actualizado exitosamente",
                loan=loan
            )
    
    except Exception as e:
        return UpdateLoanResult(
            success=False,
            message=f"Error al actualizar préstamo: {str(e)}",
            loan=None
        )


@strawberry.mutation
def update_loan_penalty(
    loan_id: int,
    penalty_applied: Decimal,
    reason: Optional[str] = None,
    penalty_type: Optional[str] = None,
    penalty_amount: Optional[Decimal] = None,
    penalty_percentage: Optional[Decimal] = None
) -> UpdateLoanPenaltyResult:
    """
    Mutation para ajustar manualmente la mora de un préstamo (CRÍTICO)
    
    Permite al administrador ajustar, reducir o eliminar (poner en 0) la mora.
    Todo ajuste queda registrado en PenaltyAdjustment para auditoría.
    
    Args:
        loan_id: ID del préstamo
        penalty_applied: Nuevo monto de mora (puede ser 0 para perdonar)
        reason: Motivo del ajuste (opcional)
        penalty_type: Tipo de mora (opcional)
        penalty_amount: Monto de mora fija (opcional)
        penalty_percentage: Porcentaje de mora (opcional)
    """
    try:
        with transaction.atomic():
            try:
                loan = Loan.objects.get(id=loan_id)
            except Loan.DoesNotExist:
                return UpdateLoanPenaltyResult(
                    success=False,
                    message="Préstamo no encontrado",
                    loan=None
                )
            
            from apps.payments.models import PenaltyAdjustment
            previous_penalty = loan.penalty_applied
            adjustment_type = 'ELIMINATE' if penalty_applied == 0 else 'REDUCE' if penalty_applied < previous_penalty else 'MODIFY'
            reason_text = reason or f"Ajuste manual: de {previous_penalty} a {penalty_applied}"
            
            PenaltyAdjustment.objects.create(
                loan=loan,
                adjustment_type=adjustment_type,
                previous_penalty=previous_penalty,
                new_penalty=penalty_applied,
                reason=reason_text
            )
            
            # Actualizar mora del préstamo
            loan.penalty_applied = penalty_applied
            
            if penalty_type is not None:
                loan.penalty_type = penalty_type
            
            if penalty_amount is not None:
                loan.penalty_amount = penalty_amount
            
            if penalty_percentage is not None:
                loan.penalty_percentage = penalty_percentage
            
            loan.save()
            
            return UpdateLoanPenaltyResult(
                success=True,
                message=f"Mora ajustada exitosamente: {previous_penalty} → {penalty_applied}",
                loan=loan
            )
    
    except Exception as e:
        return UpdateLoanPenaltyResult(
            success=False,
            message=f"Error al ajustar mora: {str(e)}",
            loan=None
        )


@strawberry.mutation
def refinance_loan(
    original_loan_id: int,
    company_id: int,
    client_id: int,
    capital_amount: Decimal,
    interest_rate: Decimal,
    number_of_installments: int,
    periodicity: str,
    start_date: date,
    end_date: date,
    observations: Optional[str] = None
) -> RefinanceLoanResult:
    """
    Mutation para refinanciar un préstamo (CRÍTICO)
    
    Crea un nuevo préstamo refinanciado vinculado al original.
    El préstamo original se marca como REFINANCED.
    
    Args:
        original_loan_id: ID del préstamo original
        company_id: ID de la empresa
        client_id: ID del cliente
        capital_amount: Monto del capital refinanciado (saldo pendiente)
        interest_rate: Nueva tasa de interés
        number_of_installments: Número de cuotas del nuevo préstamo
        periodicity: Periodicidad del nuevo préstamo
        start_date: Fecha de inicio del nuevo préstamo
        end_date: Fecha de vencimiento del nuevo préstamo
        observations: Observaciones sobre el refinanciamiento
    
    Retorna el nuevo préstamo refinanciado.
    """
    try:
        with transaction.atomic():
            # Validar préstamo original
            try:
                original_loan = Loan.objects.get(id=original_loan_id, company_id=company_id, client_id=client_id)
            except Loan.DoesNotExist:
                return RefinanceLoanResult(
                    success=False,
                    message="Préstamo original no encontrado",
                    loan=None
                )
            
            # Validar que el préstamo original tenga saldo pendiente
            if original_loan.pending_amount <= 0:
                return RefinanceLoanResult(
                    success=False,
                    message="El préstamo original ya está pagado completamente",
                    loan=None
                )
            
            # Validar que el capital refinanciado no exceda el saldo pendiente
            if capital_amount > original_loan.pending_amount:
                return RefinanceLoanResult(
                    success=False,
                    message=f"El capital refinanciado ({capital_amount}) no puede exceder el saldo pendiente ({original_loan.pending_amount})",
                    loan=None
                )
            
            # Crear nuevo préstamo refinanciado
            new_loan = Loan(
                company_id=company_id,
                client_id=client_id,
                initial_amount=capital_amount,
                interest_rate=interest_rate,
                number_of_installments=number_of_installments,
                periodicity=periodicity,
                start_date=start_date,
                end_date=end_date,
                original_loan=original_loan,
                is_refinanced=True,
                observations=observations,
                status='ACTIVE'
            )
            
            new_loan.calculate_total_amount()
            new_loan.save()
            
            # Generar cuotas del nuevo préstamo
            generate_installments(new_loan)
            
            # Marcar préstamo original como refinanciado
            original_loan.status = 'REFINANCED'
            original_loan.save()
            
            # Registrar refinanciamiento
            from .models import Refinancing
            Refinancing.objects.create(
                original_loan=original_loan,
                new_loan=new_loan,
                outstanding_balance=original_loan.pending_amount,
                refinanced_amount=capital_amount,
                interest_rate=interest_rate,
                new_period_days=(end_date - start_date).days,
                status='APPROVED'
            )
            
            return RefinanceLoanResult(
                success=True,
                message=f"Préstamo refinanciado exitosamente. Nuevo préstamo ID: {new_loan.id}",
                loan=new_loan
            )
    
    except Exception as e:
        return RefinanceLoanResult(
            success=False,
            message=f"Error al refinanciar préstamo: {str(e)}",
            loan=None
        )


@strawberry.mutation
def delete_loan(loan_id: int) -> DeleteLoanResult:
    """
    Elimina un préstamo. Solo se permite si no tiene ningún pago registrado.
    """
    try:
        loan = Loan.objects.get(id=loan_id)
    except Loan.DoesNotExist:
        return DeleteLoanResult(
            success=False,
            message="Préstamo no encontrado"
        )

    if Payment.objects.filter(loan_id=loan_id).exists():
        return DeleteLoanResult(
            success=False,
            message="No se puede eliminar el préstamo porque ya tiene pagos registrados. Solo se puede eliminar un préstamo sin pagos."
        )

    loan.delete()
    return DeleteLoanResult(
        success=True,
        message="Préstamo eliminado correctamente"
    )
