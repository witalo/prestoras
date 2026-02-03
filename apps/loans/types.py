"""
Tipos GraphQL para Loans usando Strawberry
Versión moderna compatible con strawberry-django 0.74.0+
"""
import strawberry
from typing import Optional, List
from datetime import date, datetime

from .models import Loan, Installment, Refinancing


@strawberry.django.type(Loan, fields="__all__")
class LoanType:
    """
    Tipo GraphQL para Loan (Préstamo)
    
    Representa un préstamo otorgado a un cliente.
    Los campos del modelo se incluyen automáticamente con fields="__all__"
    """
    
    @strawberry.field
    def installments(self) -> List['InstallmentType']:
        """Retorna las cuotas del préstamo"""
        return list(self.installments.all().order_by('installment_number'))
    
    @strawberry.field
    def company_id(self) -> Optional[int]:
        """Retorna el ID de la empresa (para facilitar el acceso desde el frontend)"""
        return self.company_id
    
    @strawberry.field
    def client_id(self) -> Optional[int]:
        """Retorna el ID del cliente (para facilitar el acceso desde el frontend)"""
        return self.client_id
    
    @strawberry.field
    def loan_type_id(self) -> Optional[int]:
        """Retorna el ID del tipo de préstamo (para facilitar el acceso desde el frontend)"""
        return self.loan_type_id
    
    @strawberry.field
    def original_loan_id(self) -> Optional[int]:
        """Retorna el ID del préstamo original si es refinanciado"""
        return self.original_loan_id


@strawberry.django.type(Installment, fields="__all__")
class InstallmentType:
    """
    Tipo GraphQL para Installment (Cuota)
    """
    
    @strawberry.field
    def loan_id(self) -> Optional[int]:
        """Retorna el ID del préstamo (para facilitar el acceso desde el frontend)"""
        return self.loan_id


@strawberry.django.type(Refinancing, fields="__all__")
class RefinancingType:
    """
    Tipo GraphQL para Refinancing (Refinanciamiento)
    """
    pass
