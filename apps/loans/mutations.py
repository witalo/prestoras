"""
Mutations GraphQL para Loans usando Strawberry
Incluye creación, actualización, ajuste de mora y refinanciamiento de préstamos
"""
import strawberry
from typing import Optional, List
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils import timezone

from strawberry.types import Info
from .models import Loan, Installment
from .types import LoanType
from apps.companies.models import Company
from apps.clients.models import Client
from apps.companies.models import LoanType as CompanyLoanType
from apps.payments.models import Payment
from prestoras.utils_auth import get_current_user_from_info


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


def _add_business_days_daily(start: date, n: int) -> date:
    """Suma n días hábiles (lun–sáb) a start. Domingos se saltan.
    Para n=0 devuelve start sin modificar."""
    if n <= 0:
        return start
    d = start
    added = 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() != 6:   # 6 = domingo
            added += 1
    return d


def _due_date(start: date, periodicity: str, index: int, custom_interval: int = 1) -> date:
    """Fecha de vencimiento para la cuota en posición `index` (0-based desde start).
    DAILY: los domingos no se cuentan (préstamos sin cobro los domingos).
    """
    if periodicity == 'MONTHLY':
        return start + relativedelta(months=index)
    if periodicity == 'QUARTERLY':
        return start + relativedelta(months=index * 3)
    if periodicity == 'WEEKLY':
        return start + timedelta(days=7 * index)
    if periodicity == 'BIWEEKLY':
        # Quincenal = cada 15 días (no 14)
        return start + timedelta(days=15 * index)
    if periodicity == 'CUSTOM':
        return start + timedelta(days=custom_interval * index)
    # DAILY: skip domingos
    return _add_business_days_daily(start, index)


def _start_date_from_loan_date(loan_date: date, periodicity: str) -> date:
    """Calcula la fecha de primera cuota a partir de la fecha de otorgamiento del préstamo.
    DAILY: si el día siguiente cae domingo, avanza al lunes.
    """
    if periodicity == 'DAILY':
        d = loan_date + timedelta(days=1)
        if d.weekday() == 6:   # domingo → lunes
            d += timedelta(days=1)
        return d
    if periodicity == 'WEEKLY':
        return loan_date + timedelta(days=7)
    if periodicity == 'BIWEEKLY':
        return loan_date + timedelta(days=15)
    if periodicity == 'MONTHLY':
        return loan_date + relativedelta(months=1)
    if periodicity == 'QUARTERLY':
        return loan_date + relativedelta(months=3)
    # CUSTOM / default: siguiente día
    return loan_date + timedelta(days=1)


def _end_date_from_start(start: date, periodicity: str, n: int) -> date:
    """Calcula la fecha de la última cuota dado start, periodicidad y nro de cuotas."""
    return _due_date(start, periodicity, n - 1)


def _guard_daily_sunday(periodicity: str, d: date) -> date:
    """Para préstamos DAILY: si la fecha cae domingo, avanza al lunes.
    Para cualquier otro tipo devuelve la fecha sin modificar."""
    if periodicity == 'DAILY' and d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def generate_installments(loan: Loan):
    """
    Genera cuotas con redondeo financiero correcto (ROUND_HALF_UP a 2 decimales).
    La última cuota absorbe el centavo de diferencia por redondeo, garantizando
    que la suma de todas las cuotas sea exactamente igual al total del préstamo.
    """
    n = loan.number_of_installments
    unit = Decimal('0.01')

    # Interés total redondeado a 2 dp
    total_interest = (loan.initial_amount * loan.interest_rate / Decimal('100')).quantize(unit, rounding=ROUND_HALF_UP)

    # Monto por cuota (capital e interés redondeados)
    capital_unit = (loan.initial_amount / Decimal(str(n))).quantize(unit, rounding=ROUND_HALF_UP)
    interest_unit = (total_interest / Decimal(str(n))).quantize(unit, rounding=ROUND_HALF_UP)
    total_unit = capital_unit + interest_unit  # ya son 2dp

    custom_interval = 1
    if loan.periodicity == 'CUSTOM' and n > 0:
        custom_interval = max(1, int((loan.end_date - loan.start_date).days / n))

    installments = []
    for i in range(1, n + 1):
        is_last = (i == n)
        if is_last:
            # Última cuota = residuo exacto → suma perfecta con loan.total_amount
            due = loan.end_date
            cap = loan.initial_amount - capital_unit * (n - 1)
            itr = total_interest - interest_unit * (n - 1)
            total = loan.total_amount - total_unit * (n - 1)
        else:
            due = _due_date(loan.start_date, loan.periodicity, i - 1, custom_interval)
            cap = capital_unit
            itr = interest_unit
            total = total_unit

        installments.append(Installment(
            loan=loan,
            installment_number=i,
            due_date=due,
            capital_amount=cap,
            interest_amount=itr,
            total_amount=total,
            status='PENDING',
        ))

    Installment.objects.bulk_create(installments)
    return installments


@strawberry.mutation
def create_loan(
    info: Info,
    company_id: int,
    client_id: int,
    initial_amount: Decimal,
    interest_rate: Decimal,
    number_of_installments: int,
    periodicity: str,
    start_date: date,
    end_date: date,
    loan_date: date,
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
    user = get_current_user_from_info(info)
    if not user or user.role != 'ADMIN':
        return CreateLoanResult(success=False, message="Solo el administrador puede crear préstamos.", loan=None)
    if user.company_id != company_id:
        return CreateLoanResult(success=False, message="No puede crear préstamos de otra empresa.", loan=None)
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
            
            # DAILY: corregir domingo → lunes antes de cualquier validación
            start_date = _guard_daily_sunday(periodicity, start_date)
            end_date   = _guard_daily_sunday(periodicity, end_date)

            # Validar fechas (1 cuota: inicio == fin es válido)
            if number_of_installments == 1:
                if start_date > end_date:
                    return CreateLoanResult(
                        success=False,
                        message="La fecha de inicio no puede ser posterior a la fecha de vencimiento",
                        loan=None
                    )
            else:
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
                loan_date=loan_date,
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
    info: Info,
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
    user = get_current_user_from_info(info)
    if not user or user.role != 'ADMIN':
        return UpdateLoanResult(success=False, message="Solo el administrador puede modificar préstamos.", loan=None)
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
            if loan.company_id != user.company_id:
                return UpdateLoanResult(success=False, message="No puede modificar préstamos de otra empresa.", loan=None)
            
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
                effective_installments = number_of_installments if number_of_installments is not None else loan.number_of_installments
                if effective_installments == 1:
                    if loan.start_date > end_date:
                        return UpdateLoanResult(
                            success=False,
                            message="La fecha de inicio no puede ser posterior a la fecha de vencimiento",
                            loan=None
                        )
                else:
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

                if status == 'CANCELLED':
                    # Limpiar mora — un préstamo cancelado no acumula mora
                    loan.penalty_applied = Decimal('0.00')
                    loan.penalty_override = False
                    # Marcar cuotas pendientes como canceladas
                    loan.installments.filter(
                        status__in=['PENDING', 'OVERDUE', 'PARTIALLY_PAID']
                    ).update(status='CANCELLED')

            loan.save()

            # Actualizar clasificación del cliente si cambió el estado
            if status in ('CANCELLED', 'COMPLETED', 'ACTIVE', 'DEFAULTING'):
                loan.client.update_classification()

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
    info: Info,
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
    user = get_current_user_from_info(info)
    if not user or user.role != 'ADMIN':
        return UpdateLoanPenaltyResult(success=False, message="Solo el administrador puede ajustar la mora.", loan=None)
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
            if loan.company_id != user.company_id:
                return UpdateLoanPenaltyResult(success=False, message="No puede ajustar mora de otra empresa.", loan=None)
            
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
            
            # Actualizar mora del préstamo y marcar como ajuste manual
            loan.penalty_applied = penalty_applied
            loan.penalty_override = True  # el resolver usará este valor en lugar de recalcular

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
    info: Info,
    original_loan_id: int,
    company_id: int,
    client_id: int,
    capital_amount: Decimal,
    interest_rate: Decimal,
    number_of_installments: int,
    periodicity: str,
    start_date: date,
    end_date: date,
    loan_date: date,
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
    user = get_current_user_from_info(info)
    if not user or user.role != 'ADMIN':
        return RefinanceLoanResult(success=False, message="Solo el administrador puede refinanciar préstamos.", loan=None)
    if user.company_id != company_id:
        return RefinanceLoanResult(success=False, message="No puede refinanciar préstamos de otra empresa.", loan=None)
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

            # Calcular mora actual (respetando override si existe)
            current_penalty = original_loan.calculate_penalty(save=False)
            max_capital = original_loan.pending_amount + current_penalty

            # El capital puede incluir la mora (si el admin decide incorporarla al nuevo préstamo)
            if capital_amount > max_capital:
                return RefinanceLoanResult(
                    success=False,
                    message=f"El capital refinanciado ({capital_amount}) no puede exceder saldo + mora ({max_capital})",
                    loan=None
                )
            
            # DAILY: corregir domingo → lunes
            start_date = _guard_daily_sunday(periodicity, start_date)
            end_date   = _guard_daily_sunday(periodicity, end_date)

            # Crear nuevo préstamo refinanciado
            new_loan = Loan(
                company_id=company_id,
                client_id=client_id,
                initial_amount=capital_amount,
                interest_rate=interest_rate,
                number_of_installments=number_of_installments,
                periodicity=periodicity,
                loan_date=loan_date,
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
            
            # Marcar préstamo original como refinanciado y limpiar mora
            original_loan.status = 'REFINANCED'
            original_loan.penalty_applied = Decimal('0.00')
            original_loan.penalty_override = False
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


@strawberry.type
class AdminAdjustLoanResult:
    """Resultado de ajuste administrativo de préstamo"""
    success: bool
    message: str
    loan: Optional[LoanType] = None


@strawberry.mutation
def admin_adjust_loan(
    info: Info,
    loan_id: int,
    loan_date: Optional[date] = None,
    periodicity: Optional[str] = None,
    reajustar_fechas: bool = False,
    reajustar_montos: bool = False,
    new_amount: Optional[Decimal] = None,
) -> AdminAdjustLoanResult:
    """
    Ajuste administrativo de un préstamo (solo ADMIN).

    Actualiza en-lugar las cuotas sin borrarlas, preservando el historial de pagos.

    - reajustar_fechas: recalcula due_date de cada cuota desde loan_date + periodicidad.
    - reajustar_montos: recalcula montos de cuotas; la última absorbe el centavo de diferencia.
    Ambos pueden activarse de forma independiente en una misma llamada.
    """
    user = get_current_user_from_info(info)
    if not user or user.role != 'ADMIN':
        return AdminAdjustLoanResult(success=False, message="Solo el administrador puede ajustar préstamos.", loan=None)
    try:
        with transaction.atomic():
            try:
                loan = Loan.objects.select_related('client').prefetch_related('installments').get(id=loan_id)
            except Loan.DoesNotExist:
                return AdminAdjustLoanResult(success=False, message="Préstamo no encontrado.", loan=None)
            if loan.company_id != user.company_id:
                return AdminAdjustLoanResult(success=False, message="No puede ajustar préstamos de otra empresa.", loan=None)

            # ── Actualizar loan_date y/o periodicidad ────────────────────────
            if loan_date is not None:
                loan.loan_date = loan_date
            if periodicity is not None:
                valid = ['DAILY', 'WEEKLY', 'BIWEEKLY', 'MONTHLY', 'QUARTERLY', 'CUSTOM']
                if periodicity not in valid:
                    return AdminAdjustLoanResult(success=False, message=f"Periodicidad inválida. Debe ser una de: {', '.join(valid)}", loan=None)
                loan.periodicity = periodicity

            today = timezone.now().date()
            installments = list(loan.installments.order_by('installment_number'))
            n = loan.number_of_installments

            if len(installments) != n:
                return AdminAdjustLoanResult(
                    success=False,
                    message=f"El préstamo tiene {len(installments)} cuotas registradas pero se esperaban {n}. Verifique la integridad de datos.",
                    loan=None
                )

            # ── REAJUSTE DE FECHAS ───────────────────────────────────────────
            if reajustar_fechas:
                if not loan.loan_date:
                    return AdminAdjustLoanResult(
                        success=False,
                        message="Debe proporcionar la fecha del préstamo (loan_date) para reajustar fechas.",
                        loan=None
                    )
                new_start = _start_date_from_loan_date(loan.loan_date, loan.periodicity)

                # CUSTOM: mantener end_date existente (el intervalo lo define start↔end)
                # Los demás: recalcular end_date desde new_start + (n-1) periodos
                if loan.periodicity == 'CUSTOM':
                    new_end = loan.end_date  # respetar el vencimiento original
                    custom_iv = max(1, int((new_end - new_start).days / n)) if n > 0 else 1
                else:
                    new_end = _end_date_from_start(new_start, loan.periodicity, n)
                    custom_iv = 1

                loan.start_date = new_start
                loan.end_date = new_end

                date_updates = []
                for i, inst in enumerate(installments, 1):
                    if i == n:
                        inst.due_date = new_end
                    else:
                        inst.due_date = _due_date(new_start, loan.periodicity, i - 1, custom_iv)
                    # Re-evaluar estado según nueva fecha (sin tocar pagos)
                    if inst.paid_amount >= inst.total_amount:
                        inst.status = 'PAID'
                    elif inst.paid_amount > 0:
                        inst.status = 'PARTIALLY_PAID'
                    elif today > inst.due_date:
                        inst.status = 'OVERDUE'
                    else:
                        inst.status = 'PENDING'
                    date_updates.append(inst)

                Installment.objects.bulk_update(date_updates, ['due_date', 'status'])

            # ── REAJUSTE DE MONTOS ───────────────────────────────────────────
            if reajustar_montos:
                if new_amount is not None and new_amount > 0:
                    loan.initial_amount = new_amount
                # Recalcular total (capital + intereses)
                loan.calculate_total_amount()

                unit = Decimal('0.01')
                total_interest = (loan.initial_amount * loan.interest_rate / Decimal('100')).quantize(unit, rounding=ROUND_HALF_UP)
                capital_unit = (loan.initial_amount / Decimal(str(n))).quantize(unit, rounding=ROUND_HALF_UP)
                interest_unit = (total_interest / Decimal(str(n))).quantize(unit, rounding=ROUND_HALF_UP)
                total_unit = capital_unit + interest_unit

                amount_updates = []
                for i, inst in enumerate(installments, 1):
                    if i == n:
                        inst.capital_amount  = loan.initial_amount - capital_unit * (n - 1)
                        inst.interest_amount = total_interest - interest_unit * (n - 1)
                        inst.total_amount    = loan.total_amount - total_unit * (n - 1)
                    else:
                        inst.capital_amount  = capital_unit
                        inst.interest_amount = interest_unit
                        inst.total_amount    = total_unit
                    amount_updates.append(inst)

                Installment.objects.bulk_update(amount_updates, ['capital_amount', 'interest_amount', 'total_amount'])

                # Recalcular paid_amount y pending_amount del préstamo
                loan.paid_amount = sum(i.paid_amount for i in installments)
                loan.pending_amount = loan.total_amount - loan.paid_amount

            # Si se cambiaron fechas o montos, la mora debe recalcularse desde
            # la fórmula con los nuevos valores — el override manual ya no aplica.
            if reajustar_fechas or reajustar_montos:
                loan.penalty_override = False

            loan.save()

            return AdminAdjustLoanResult(
                success=True,
                message="Préstamo ajustado correctamente.",
                loan=loan
            )

    except Exception as e:
        return AdminAdjustLoanResult(
            success=False,
            message=f"Error al ajustar préstamo: {str(e)}",
            loan=None
        )


@strawberry.mutation
def delete_loan(info: Info, loan_id: int) -> DeleteLoanResult:
    """Elimina un préstamo sin pagos. Solo administrador."""
    user = get_current_user_from_info(info)
    if not user or user.role != 'ADMIN':
        return DeleteLoanResult(success=False, message="Solo el administrador puede eliminar préstamos.")
    try:
        loan = Loan.objects.get(id=loan_id)
    except Loan.DoesNotExist:
        return DeleteLoanResult(
            success=False,
            message="Préstamo no encontrado"
        )

    if loan.company_id != user.company_id:
        return DeleteLoanResult(success=False, message="No puede eliminar préstamos de otra empresa.")

    if Payment.objects.filter(loan_id=loan_id).exists():
        return DeleteLoanResult(
            success=False,
            message="No se puede eliminar el préstamo porque ya tiene pagos registrados."
        )

    loan.delete()
    return DeleteLoanResult(
        success=True,
        message="Préstamo eliminado correctamente"
    )
