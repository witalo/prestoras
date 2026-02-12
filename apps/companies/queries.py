"""
Queries GraphQL para Companies usando Strawberry
"""
import strawberry
from typing import List, Optional

from .models import Company, LoanType
from .types import CompanyType, LoanTypeType


@strawberry.type
class CompanyQuery:
    """
    Queries relacionadas con empresas
    """
    
    @strawberry.field
    def companies(self, is_active: Optional[bool] = True) -> List[CompanyType]:
        """
        Obtener lista de empresas
        
        Filtros:
        - is_active: Filtrar por estado activo/inactivo (por defecto solo activas)
        """
        queryset = Company.objects.all()
        
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        
        return list(queryset)
    
    @strawberry.field
    def company(self, company_id: int) -> Optional[CompanyType]:
        """
        Obtener una empresa por ID
        """
        try:
            return Company.objects.get(id=company_id)
        except Company.DoesNotExist:
            return None
    
    @strawberry.field
    def company_by_ruc(self, ruc: str) -> Optional[CompanyType]:
        """
        Obtener una empresa por RUC
        """
        try:
            return Company.objects.get(ruc=ruc)
        except Company.DoesNotExist:
            return None
    
    @strawberry.field
    def company_by_email(self, email: str) -> Optional[CompanyType]:
        """
        Obtener una empresa por email
        """
        try:
            return Company.objects.get(email=email)
        except Company.DoesNotExist:
            return None
    
    @strawberry.field
    def loan_types_by_company(
        self,
        company_id: int,
        is_active: Optional[bool] = True
    ) -> List[LoanTypeType]:
        """
        Obtener tipos de préstamo de una empresa
        """
        queryset = LoanType.objects.filter(company_id=company_id)
        
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        
        return list(queryset)
