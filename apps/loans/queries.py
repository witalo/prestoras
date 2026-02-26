"""
Queries GraphQL para Loans usando Strawberry
Scope: admin ve todos los préstamos; cobrador solo de su cartera.
"""
import strawberry
from typing import List, Optional
from datetime import date
from strawberry.types import Info

from .models import Loan, Installment, Refinancing
from .types import LoanType, InstallmentType, RefinancingType
from prestoras.utils_auth import get_current_user_from_info


def _scope_loans_queryset(queryset, info: Info, company_id: int):
    """Si el usuario es cobrador, restringe a préstamos de su cartera."""
    user = get_current_user_from_info(info)
    if user and user.role == 'COLLECTOR':
        if user.company_id != company_id:
            return queryset.none()
        client_ids = list(user.assigned_clients.values_list('id', flat=True))
        if not client_ids:
            return queryset.none()
        return queryset.filter(client_id__in=client_ids)
    return queryset


@strawberry.type
class LoanQuery:
    """
    Queries relacionadas con préstamos
    """
    
    @strawberry.field
    def loans(
        self,
        info: Info,
        company_id: int,
        client_id: Optional[int] = None,
        status: Optional[str] = None,
        is_refinanced: Optional[bool] = None
    ) -> List[LoanType]:
        """
        Obtener lista de préstamos. Admin: todos. Cobrador: solo de su cartera.
        """
        queryset = Loan.objects.filter(company_id=company_id)
        queryset = _scope_loans_queryset(queryset, info, company_id)
        
        if client_id:
            queryset = queryset.filter(client_id=client_id)
        
        if status:
            queryset = queryset.filter(status=status)
        
        if is_refinanced is not None:
            queryset = queryset.filter(is_refinanced=is_refinanced)
        
        return list(queryset.select_related('company', 'client', 'loan_type', 'created_by', 'original_loan').prefetch_related('installments'))
    
    @strawberry.field
    def loan(self, info: Info, loan_id: int) -> Optional[LoanType]:
        """
        Obtener un préstamo por ID. Cobrador solo si el cliente está en su cartera.
        """
        try:
            obj = Loan.objects.select_related('company', 'client', 'loan_type', 'created_by', 'original_loan').prefetch_related('installments').get(id=loan_id)
            user = get_current_user_from_info(info)
            if user and user.role == 'COLLECTOR':
                if user.company_id != obj.company_id or not user.assigned_clients.filter(id=obj.client_id).exists():
                    return None
            return obj
        except Loan.DoesNotExist:
            return None
    
    @strawberry.field
    def active_loans_by_client(
        self,
        info: Info,
        client_id: int,
        company_id: int
    ) -> List[LoanType]:
        """
        Obtener préstamos activos de un cliente. Cobrador solo si el cliente está en su cartera.
        """
        user = get_current_user_from_info(info)
        if user and user.role == 'COLLECTOR':
            if user.company_id != company_id or not user.assigned_clients.filter(id=client_id).exists():
                return []
        queryset = Loan.objects.filter(
            client_id=client_id,
            company_id=company_id,
            status='ACTIVE'
        )
        return list(queryset.select_related('company', 'client', 'loan_type').prefetch_related('installments'))
    
    @strawberry.field
    def overdue_loans(
        self,
        info: Info,
        company_id: int
    ) -> List[LoanType]:
        """
        Obtener préstamos vencidos (morosos). Cobrador: solo de su cartera.
        """
        from django.utils import timezone
        today = timezone.now().date()
        queryset = Loan.objects.filter(
            company_id=company_id,
            status__in=['ACTIVE', 'DEFAULTING'],
            end_date__lt=today
        )
        queryset = _scope_loans_queryset(queryset, info, company_id)
        return list(queryset.select_related('company', 'client').prefetch_related('installments'))
    
    @strawberry.field
    def client_loan_history(
        self,
        info: Info,
        client_id: int,
        company_id: int
    ) -> List[LoanType]:
        """
        Obtener historial completo de préstamos de un cliente. Cobrador solo si cliente en su cartera.
        """
        user = get_current_user_from_info(info)
        if user and user.role == 'COLLECTOR':
            if user.company_id != company_id or not user.assigned_clients.filter(id=client_id).exists():
                return []
        queryset = Loan.objects.filter(
            client_id=client_id,
            company_id=company_id
        ).order_by('-created_at')
        return list(queryset.select_related('company', 'client', 'loan_type').prefetch_related('installments'))
    
    @strawberry.field
    def loan_installments(
        self,
        info: Info,
        loan_id: int
    ) -> List[InstallmentType]:
        """
        Obtener cuotas de un préstamo
        """
        return list(Installment.objects.filter(loan_id=loan_id).order_by('installment_number'))
    
    @strawberry.field
    def installment(self, info: Info, installment_id: int) -> Optional[InstallmentType]:
        """
        Obtener una cuota específica por ID
        """
        try:
            return Installment.objects.get(id=installment_id)
        except Installment.DoesNotExist:
            return None