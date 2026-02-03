"""
Tipos GraphQL para Payments usando Strawberry
Versión moderna compatible con strawberry-django 0.74.0+
"""
import strawberry
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

from .models import Payment, PaymentInstallment, PenaltyAdjustment


@strawberry.type
class PaymentMethodType:
    """
    Tipo GraphQL para PaymentMethod (Método de Pago)
    Representa un método de pago con su monto
    """
    method: str
    amount: Decimal


@strawberry.django.type(Payment, fields="__all__")
class PaymentType:
    """
    Tipo GraphQL para Payment (Pago)
    
    Representa un pago realizado por un cliente.
    Los campos del modelo se incluyen automáticamente con fields="__all__"
    """
    
    @strawberry.field
    def loan_id(self) -> Optional[int]:
        """Retorna el ID del préstamo (para facilitar el acceso desde el frontend)"""
        return self.loan_id
    
    @strawberry.field
    def collector_id(self) -> Optional[int]:
        """Retorna el ID del cobrador (para facilitar el acceso desde el frontend)"""
        return self.collector_id if self.collector else None
    
    @strawberry.field
    def payment_methods(self) -> List[PaymentMethodType]:
        """
        Retorna la lista de métodos de pago.
        
        Nota: El modelo actualmente solo soporta un método principal (payment_method),
        pero este campo retorna una lista para ser compatible con el frontend
        que espera múltiples métodos de pago.
        """
        if self.payment_method:
            return [PaymentMethodType(
                method=self.payment_method,
                amount=self.amount
            )]
        return []
    
    @strawberry.field
    def notes(self) -> Optional[str]:
        """Retorna las observaciones del pago (alias de observations)"""
        return self.observations
    
    @strawberry.field
    def payment_installments(self) -> List['PaymentInstallmentType']:
        """Retorna las cuotas cubiertas por este pago"""
        return list(self.payment_installments.all())


@strawberry.django.type(PaymentInstallment, fields="__all__")
class PaymentInstallmentType:
    """
    Tipo GraphQL para PaymentInstallment (Pago-Cuota)
    """
    pass


@strawberry.django.type(PenaltyAdjustment, fields="__all__")
class PenaltyAdjustmentType:
    """
    Tipo GraphQL para PenaltyAdjustment (Ajuste de Mora)
    """
    pass
