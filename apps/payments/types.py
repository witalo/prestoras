"""
Tipos GraphQL para Payments usando Strawberry
"""
import strawberry
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

from .models import Payment, PaymentInstallment, PenaltyAdjustment
from apps.users.types import UserType


@strawberry.type
class PaymentMethodType:
    """Método de pago con su monto"""
    method: str
    amount: Decimal


# Campos escalares del modelo Payment — FK excluidos para evitar typing.Any
_PAYMENT_SCALAR_FIELDS = [
    'id',
    'amount',
    'payment_date',
    'payment_method',
    'status',
    'reference_number',
    'observations',
    'created_at',
    'updated_at',
]


@strawberry.django.type(Payment, fields=_PAYMENT_SCALAR_FIELDS)
class PaymentType:
    """Tipo GraphQL para Payment (Pago)"""

    # FK como objeto — explícito para que Strawberry conozca el tipo exacto
    @strawberry.field
    def collector(self) -> Optional[UserType]:
        return self.collector if self.collector_id else None

    # IDs de FK útiles para el frontend
    @strawberry.field
    def loan_id(self) -> Optional[int]:
        return self.loan_id

    @strawberry.field
    def loan_initial_amount(self) -> Optional[Decimal]:
        try:
            return self.loan.initial_amount if self.loan_id else None
        except Exception:
            return None

    @strawberry.field
    def loan_total_amount(self) -> Optional[Decimal]:
        try:
            return self.loan.total_amount if self.loan_id else None
        except Exception:
            return None

    @strawberry.field
    def loan_status(self) -> Optional[str]:
        try:
            return self.loan.status if self.loan_id else None
        except Exception:
            return None

    @strawberry.field
    def loan_pending_amount(self) -> Optional[Decimal]:
        try:
            return self.loan.pending_amount if self.loan_id else None
        except Exception:
            return None

    @strawberry.field
    def loan_date(self) -> Optional[str]:
        try:
            d = self.loan.loan_date if self.loan_id else None
            return str(d) if d else None
        except Exception:
            return None

    @strawberry.field
    def penalty_paid(self) -> Decimal:
        from django.db.models import Sum
        total = self.payment_installments.aggregate(t=Sum('amount_applied'))['t'] or Decimal('0.00')
        return max(Decimal('0.00'), self.amount - total)

    @strawberry.field
    def collector_id(self) -> Optional[int]:
        return self.collector_id if self.collector_id else None

    # Campos calculados / alias
    @strawberry.field
    def notes(self) -> Optional[str]:
        return self.observations

    @strawberry.field(name="clientName")
    def client_name(self) -> str:
        try:
            return self.client.full_name if self.client else ""
        except Exception:
            return ""

    @strawberry.field
    def payment_methods(self) -> List[PaymentMethodType]:
        if self.payment_method:
            return [PaymentMethodType(method=self.payment_method, amount=self.amount)]
        return []

    @strawberry.field
    def payment_installments(self) -> List['PaymentInstallmentType']:
        return list(self.payment_installments.all())


# Campos escalares del modelo PaymentInstallment
_PAYMENT_INSTALLMENT_SCALAR_FIELDS = [
    'id',
    'amount_applied',
    'created_at',
]


@strawberry.django.type(PaymentInstallment, fields=_PAYMENT_INSTALLMENT_SCALAR_FIELDS)
class PaymentInstallmentType:
    """Tipo GraphQL para PaymentInstallment (Pago-Cuota)"""

    @strawberry.field
    def payment_id(self) -> Optional[int]:
        return self.payment_id

    @strawberry.field
    def installment_id(self) -> Optional[int]:
        return self.installment_id


# Campos escalares del modelo PenaltyAdjustment
_PENALTY_ADJUSTMENT_SCALAR_FIELDS = [
    'id',
    'adjustment_type',
    'previous_penalty',
    'new_penalty',
    'reason',
    'created_at',
]


@strawberry.django.type(PenaltyAdjustment, fields=_PENALTY_ADJUSTMENT_SCALAR_FIELDS)
class PenaltyAdjustmentType:
    """Tipo GraphQL para PenaltyAdjustment (Ajuste de Mora)"""

    @strawberry.field
    def loan_id(self) -> Optional[int]:
        return self.loan_id

    @strawberry.field
    def adjusted_by_id(self) -> Optional[int]:
        return self.adjusted_by_id


@strawberry.type
class CollectorStatType:
    """Estadísticas por usuario para el dashboard."""
    collector_id: int = strawberry.field(name="collectorId")
    collector_name: str = strawberry.field(name="collectorName")
    total_clients: int = strawberry.field(name="totalClients")
    active_loans: int = strawberry.field(name="activeLoans")
    amount_collected_today: Decimal = strawberry.field(name="amountCollectedToday")
    role: str = strawberry.field(name="role", default="COLLECTOR")


@strawberry.type
class DashboardStatsType:
    """Resumen completo para el dashboard."""
    total_clients: int = strawberry.field(name="totalClients")
    active_loans: int = strawberry.field(name="activeLoans")
    completed_loans: int = strawberry.field(name="completedLoans")
    defaulting_loans: int = strawberry.field(name="defaultingLoans")
    total_disbursed: Decimal = strawberry.field(name="totalDisbursed")
    total_collected: Decimal = strawberry.field(name="totalCollected")
    total_pending: Decimal = strawberry.field(name="totalPending")
    total_penalty: Decimal = strawberry.field(name="totalPenalty")
    collections_today: int = strawberry.field(name="collectionsToday")
    amount_today: Decimal = strawberry.field(name="amountToday")
    collector_stats: List[CollectorStatType] = strawberry.field(name="collectorStats")


@strawberry.type
class PaymentVoucherType:
    """Datos del voucher de pago para imprimir."""
    payment_id: int = strawberry.field(name="paymentId")
    company_name: str = strawberry.field(name="companyName")
    company_ruc: Optional[str] = strawberry.field(name="companyRuc", default=None)
    company_address: Optional[str] = strawberry.field(name="companyAddress", default=None)
    client_name: str = strawberry.field(name="clientName")
    client_dni: Optional[str] = strawberry.field(name="clientDni", default=None)
    amount: Decimal = strawberry.field(name="amount")
    payment_date: str = strawberry.field(name="paymentDate")
    payment_method: str = strawberry.field(name="paymentMethod")
    reference_number: Optional[str] = strawberry.field(name="referenceNumber", default=None)
    installment_lines: List[str] = strawberry.field(name="installmentLines")
    notes: Optional[str] = strawberry.field(name="notes", default=None)


# ─── Reporte de Saldos ───────────────────────────────────────────────────────

@strawberry.type
class DailyPaymentType:
    """Pago agregado por día para el reporte de saldos."""
    date: str   # "YYYY-MM-DD"
    amount: Decimal


@strawberry.type
class SaldosReportRowType:
    """Fila del reporte de saldos: préstamo activo/moroso con pagos diarios."""
    loan_id: int = strawberry.field(name="loanId")
    client_dni: str = strawberry.field(name="clientDni")
    client_full_name: str = strawberry.field(name="clientFullName")
    zone_name: Optional[str] = strawberry.field(name="zoneName", default=None)
    zone_id: Optional[int] = strawberry.field(name="zoneId", default=None)
    loan_start_date: str = strawberry.field(name="loanStartDate")           # fecha real del préstamo (loan_date || start_date)
    loan_actual_start_date: str = strawberry.field(name="loanActualStartDate")  # fecha primera cuota
    loan_end_date: str = strawberry.field(name="loanEndDate")                   # fecha última cuota
    initial_amount: Decimal = strawberry.field(name="initialAmount")
    interest_rate: Decimal = strawberry.field(name="interestRate")
    total_amount: Decimal = strawberry.field(name="totalAmount")
    paid_amount: Decimal = strawberry.field(name="paidAmount")
    pending_amount: Decimal = strawberry.field(name="pendingAmount")
    loan_status: str = strawberry.field(name="loanStatus")
    loan_type_name: Optional[str] = strawberry.field(name="loanTypeName", default=None)
    periodicity: str
    classification: str
    daily_payments: List[DailyPaymentType] = strawberry.field(name="dailyPayments")


# ─── Reporte de Ganancia por Intereses ───────────────────────────────────────

@strawberry.type
class InterestEarnedReportRowType:
    """Fila del reporte de ganancia: préstamo con interés cobrado en el período."""
    loan_id: int = strawberry.field(name="loanId")
    client_dni: str = strawberry.field(name="clientDni")
    client_full_name: str = strawberry.field(name="clientFullName")
    zone_name: Optional[str] = strawberry.field(name="zoneName", default=None)
    loan_status: str = strawberry.field(name="loanStatus")
    initial_amount: Decimal = strawberry.field(name="initialAmount")
    total_amount: Decimal = strawberry.field(name="totalAmount")
    interest_earned: Decimal = strawberry.field(name="interestEarned")
    payments_count: int = strawberry.field(name="paymentsCount")
    total_collected: Decimal = strawberry.field(name="totalCollected")
