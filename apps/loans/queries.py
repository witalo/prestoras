"""
Queries GraphQL para Loans usando Strawberry
"""
import strawberry
from typing import List, Optional
from datetime import date
from strawberry.types import Info

from .models import Loan, Installment, Refinancing
from .types import LoanType, InstallmentType, RefinancingType


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
        Obtener lista de préstamos
        
        Filtros:
        - company_id: Empresa (requerido)
        - client_id: Filtrar por cliente (opcional)
        - status: Filtrar por estado (ACTIVE, COMPLETED, DEFAULTING, REFINANCED, CANCELLED)
        - is_refinanced: Filtrar préstamos refinanciados (opcional)
        """
        queryset = Loan.objects.filter(company_id=company_id)
        
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
        Obtener un préstamo por ID
        """
        try:
            return Loan.objects.select_related('company', 'client', 'loan_type', 'created_by', 'original_loan').prefetch_related('installments').get(id=loan_id)
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
        Obtener préstamos activos de un cliente
        """
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
        Obtener préstamos vencidos (morosos)
        """
        from django.utils import timezone
        
        today = timezone.now().date()
        queryset = Loan.objects.filter(
            company_id=company_id,
            status__in=['ACTIVE', 'DEFAULTING'],
            end_date__lt=today
        )
        
        return list(queryset.select_related('company', 'client').prefetch_related('installments'))
    
    @strawberry.field
    def client_loan_history(
        self,
        info: Info,
        client_id: int,
        company_id: int
    ) -> List[LoanType]:
        """
        Obtener historial completo de préstamos de un cliente
        
        Incluye todos los préstamos (activos, completados, refinanciados, etc.)
        para evaluar si el cliente es apto para un nuevo crédito.
        """
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