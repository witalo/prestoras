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

    @strawberry.field(name="clientName")
    def client_name(self) -> str:
        """Nombre del cliente que realizó el pago (company_payments usa select_related('client'))."""
        if getattr(self, 'client', None):
            return self.client.full_name
        return ""
    
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


@strawberry.type
class DashboardStatsType:
    """
    Resumen para dashboard (multiempresa). Campos en camelCase para el frontend.
    """
    active_loans_count: int = strawberry.field(name="activeLoansCount")
    total_clients_count: int = strawberry.field(name="totalClientsCount")
    today_payments_sum: Decimal = strawberry.field(name="todayPaymentsSum")
    total_pending_sum: Decimal = strawberry.field(name="totalPendingSum")


@strawberry.type
class PaymentVoucherType:
    """
    Datos del voucher de pago para imprimir (ej. en impresora 55mm Bluetooth).
    Expuesto en camelCase para el frontend (paymentVoucher, paymentId, companyName, etc.).
    """
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
