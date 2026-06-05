"""
Tipos GraphQL para Loans usando Strawberry
"""
import strawberry
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal

from .models import Loan, Installment, Refinancing
from apps.clients.types import ClientType
from apps.companies.types import LoanTypeType


# Campos escalares del modelo Loan — excluimos todos los FK para evitar
# que fields= intente auto-resolver tipos (causaría typing.Any en self-ref y created_by)
_LOAN_SCALAR_FIELDS = [
    'id',
    'initial_amount',
    'interest_rate',
    'number_of_installments',
    'periodicity',
    'loan_date',
    'start_date',
    'end_date',
    'total_amount',
    'paid_amount',
    'pending_amount',
    'penalty_type',
    'penalty_amount',
    'penalty_percentage',
    'status',
    'observations',
    'is_refinanced',
    'created_at',
]


@strawberry.django.type(Loan, fields=_LOAN_SCALAR_FIELDS)
class LoanType:
    """Tipo GraphQL para Loan (Préstamo)"""

    # FK como objetos — explícitos para que Strawberry conozca el tipo exacto
    @strawberry.field
    def client(self) -> Optional[ClientType]:
        return self.client

    @strawberry.field
    def loan_type(self) -> Optional[LoanTypeType]:
        return self.loan_type

    # Cuotas (reverse FK)
    @strawberry.field
    def installments(self) -> List['InstallmentType']:
        return list(self.installments.all().order_by('installment_number'))

    @strawberry.field
    def refinanced_to_id(self) -> Optional[int]:
        # original_loan → related_name='refinancings' (FK, puede haber varios en teoría)
        try:
            r = self.refinancings.first()
            return r.new_loan_id if r else None
        except Exception:
            return None

    @strawberry.field
    def penalty_total_paid(self) -> Decimal:
        if hasattr(self, '_pmt_total'):
            pmt = self._pmt_total or Decimal('0.00')
            inst = self._inst_total or Decimal('0.00')
            return max(Decimal('0.00'), pmt - inst)
        from django.db.models import Sum as DSum
        from apps.payments.models import PaymentInstallment
        total_pmts = self.payments.filter(status='COMPLETED').aggregate(t=DSum('amount'))['t'] or Decimal('0.00')
        total_inst = PaymentInstallment.objects.filter(
            payment__loan=self, payment__status='COMPLETED'
        ).aggregate(t=DSum('amount_applied'))['t'] or Decimal('0.00')
        return max(Decimal('0.00'), total_pmts - total_inst)

    @strawberry.field
    def penalty_applied(self) -> Decimal:
        if self.status in ('COMPLETED', 'CANCELLED', 'REFINANCED'):
            return Decimal('0.00')
        # Si el admin ajustó manualmente la mora, devolver el valor guardado.
        if self.penalty_override:
            return self.penalty_applied
        # Caso normal: calcular fresco desde la fórmula.
        return self.calculate_penalty(save=False)

    # IDs de FK — útiles para el frontend sin tener que cargar el objeto completo
    @strawberry.field
    def company_id(self) -> Optional[int]:
        return self.company_id

    @strawberry.field
    def client_id(self) -> Optional[int]:
        return self.client_id

    @strawberry.field
    def loan_type_id(self) -> Optional[int]:
        return self.loan_type_id

    @strawberry.field
    def original_loan_id(self) -> Optional[int]:
        return self.original_loan_id


@strawberry.django.type(Installment, fields="__all__")
class InstallmentType:
    """Tipo GraphQL para Installment (Cuota)"""

    @strawberry.field
    def loan_id(self) -> Optional[int]:
        return self.loan_id

    @strawberry.field(name="capitalAmount")
    def capital_amount_field(self) -> Optional[float]:
        return float(self.capital_amount) if self.capital_amount is not None else None

    @strawberry.field(name="interestAmount")
    def interest_amount_field(self) -> Optional[float]:
        return float(self.interest_amount) if self.interest_amount is not None else None


@strawberry.django.type(Refinancing, fields="__all__")
class RefinancingType:
    """Tipo GraphQL para Refinancing (Refinanciamiento)"""
    pass
