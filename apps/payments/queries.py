"""
Queries GraphQL para Payments usando Strawberry
"""
import strawberry
from typing import List, Optional
from datetime import date
from strawberry.types import Info

from .models import Payment
from .types import PaymentType


@strawberry.type
class PaymentQuery:
    """
    Queries relacionadas con pagos
    """
    
    @strawberry.field
    def loan_payments(
        self,
        info: Info,
        loan_id: int
    ) -> List[PaymentType]:
        """
        Obtener pagos de un préstamo
        """
        return list(Payment.objects.filter(loan_id=loan_id).order_by('-payment_date'))
    
    @strawberry.field
    def collector_payments(
        self,
        info: Info,
        collector_id: int,
        company_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[PaymentType]:
        """
        Obtener pagos de un cobrador en un rango de fechas
        
        Útil para estadísticas y reportes de cobradores.
        """
        queryset = Payment.objects.filter(
            collector_id=collector_id,
            company_id=company_id,
            status='COMPLETED'
        )
        
        if start_date:
            queryset = queryset.filter(payment_date__date__gte=start_date)
        
        if end_date:
            queryset = queryset.filter(payment_date__date__lte=end_date)
        
        return list(queryset.order_by('-payment_date'))
    
    @strawberry.field
    def payment(self, info: Info, payment_id: int) -> Optional[PaymentType]:
        """
        Obtener un pago específico por ID
        """
        try:
            return Payment.objects.select_related('loan', 'client', 'collector').prefetch_related('payment_installments').get(id=payment_id)
        except Payment.DoesNotExist:
            return None
