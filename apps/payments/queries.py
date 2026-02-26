"""
Queries GraphQL para Payments usando Strawberry
Scope: admin ve todos los pagos; cobrador solo de clientes de su cartera.
"""
import strawberry
from typing import Annotated, List, Optional
from datetime import date
from decimal import Decimal
from django.utils import timezone
from django.db.models import Sum
from strawberry.types import Info

from .models import Payment
from .types import PaymentType, PaymentVoucherType, DashboardStatsType
from prestoras.utils_auth import get_current_user_from_info


# Métodos de pago legibles para el voucher
PAYMENT_METHOD_LABELS = {
    'CASH': 'Efectivo',
    'CARD': 'Tarjeta',
    'BCP': 'BCP',
    'YAPE': 'Yape',
    'PLIN': 'Plin',
    'TRANSFER': 'Transferencia',
}


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
        Obtener pagos de un préstamo. Cobrador solo si el préstamo es de su cartera.
        """
        from apps.loans.models import Loan
        user = get_current_user_from_info(info)
        if user and user.role == 'COLLECTOR':
            try:
                loan = Loan.objects.get(id=loan_id)
                if loan.company_id != user.company_id or not user.assigned_clients.filter(id=loan.client_id).exists():
                    return []
            except Loan.DoesNotExist:
                return []
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
        Obtener un pago por ID. Cobrador solo si el cliente está en su cartera.
        """
        try:
            obj = Payment.objects.select_related('loan', 'client', 'collector').prefetch_related('payment_installments').get(id=payment_id)
            user = get_current_user_from_info(info)
            if user and user.role == 'COLLECTOR':
                if obj.company_id != user.company_id or not user.assigned_clients.filter(id=obj.client_id).exists():
                    return None
            return obj
        except Payment.DoesNotExist:
            return None

    @strawberry.field
    def company_payments(
        self,
        info: Info,
        company_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        collector_id: Optional[int] = None
    ) -> List[PaymentType]:
        """
        Obtener pagos de la empresa. Cobrador: solo pagos de clientes de su cartera.
        """
        queryset = Payment.objects.filter(
            company_id=company_id,
            status='COMPLETED'
        ).select_related('loan', 'client', 'collector')
        user = get_current_user_from_info(info)
        if user and user.role == 'COLLECTOR':
            client_ids = list(user.assigned_clients.values_list('id', flat=True))
            if not client_ids:
                return []
            queryset = queryset.filter(client_id__in=client_ids)
        elif collector_id is not None:
            queryset = queryset.filter(collector_id=collector_id)
        if start_date:
            queryset = queryset.filter(payment_date__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(payment_date__date__lte=end_date)
        return list(queryset.order_by('-payment_date'))

    @strawberry.field
    def dashboard_stats(
        self,
        info: Info,
        company_id: int,
        collector_id: Optional[int] = None
    ) -> DashboardStatsType:
        """
        Resumen para dashboard. Si collector_id viene, solo datos del cobrador (sus clientes y sus cobros).
        """
        from apps.loans.models import Loan
        from apps.clients.models import Client
        from apps.users.models import User

        today = timezone.now().date()

        if collector_id is not None:
            # Cobrador: solo su cartera (clientes asignados)
            try:
                collector = User.objects.prefetch_related('assigned_clients').get(id=collector_id, company_id=company_id)
            except User.DoesNotExist:
                return DashboardStatsType(
                    active_loans_count=0,
                    total_clients_count=0,
                    today_payments_sum=Decimal('0.00'),
                    total_pending_sum=Decimal('0.00'),
                )
            client_ids = list(collector.assigned_clients.filter(is_active=True).values_list('id', flat=True))
            if not client_ids:
                return DashboardStatsType(
                    active_loans_count=0,
                    total_clients_count=0,
                    today_payments_sum=Decimal('0.00'),
                    total_pending_sum=Decimal('0.00'),
                )
            total_clients_count = len(client_ids)
            active_loans_count = Loan.objects.filter(
                company_id=company_id,
                client_id__in=client_ids,
                status__in=['ACTIVE', 'DEFAULTING']
            ).count()
            today_result = Payment.objects.filter(
                company_id=company_id,
                collector_id=collector_id,
                status='COMPLETED',
                payment_date__date=today
            ).aggregate(total=Sum('amount'))
            today_payments_sum = today_result['total'] or Decimal('0.00')
            pending_result = Loan.objects.filter(
                company_id=company_id,
                client_id__in=client_ids,
                status__in=['ACTIVE', 'DEFAULTING']
            ).aggregate(total=Sum('pending_amount'))
            total_pending_sum = pending_result['total'] or Decimal('0.00')
        else:
            # Admin: toda la empresa
            active_loans_count = Loan.objects.filter(
                company_id=company_id,
                status__in=['ACTIVE', 'DEFAULTING']
            ).count()
            total_clients_count = Client.objects.filter(
                company_id=company_id,
                is_active=True
            ).count()
            today_result = Payment.objects.filter(
                company_id=company_id,
                status='COMPLETED',
                payment_date__date=today
            ).aggregate(total=Sum('amount'))
            today_payments_sum = today_result['total'] or Decimal('0.00')
            pending_result = Loan.objects.filter(
                company_id=company_id,
                status__in=['ACTIVE', 'DEFAULTING']
            ).aggregate(total=Sum('pending_amount'))
            total_pending_sum = pending_result['total'] or Decimal('0.00')

        return DashboardStatsType(
            active_loans_count=active_loans_count,
            total_clients_count=total_clients_count,
            today_payments_sum=today_payments_sum,
            total_pending_sum=total_pending_sum,
        )
    
    @strawberry.field(name="paymentVoucher")
    def payment_voucher(
        self,
        info: Info,
        payment_id: Annotated[int, strawberry.argument(name="paymentId")],
    ) -> Optional[PaymentVoucherType]:
        """
        Obtener datos del voucher de un pago para mostrar o imprimir
        (ej. en impresora térmica 55mm Bluetooth).
        """
        try:
            payment = Payment.objects.select_related(
                'loan', 'client', 'company'
            ).prefetch_related('payment_installments__installment').get(id=payment_id)
        except Payment.DoesNotExist:
            return None
        
        company = payment.company
        client = payment.client
        
        # Líneas de cuotas: "Cuota 3: S/ 100.00"
        installment_lines = []
        for pi in payment.payment_installments.select_related('installment').all():
            num = pi.installment.installment_number
            amt = pi.amount_applied
            installment_lines.append(f"Cuota {num}: S/ {amt:.2f}")
        
        method_label = PAYMENT_METHOD_LABELS.get(
            payment.payment_method or 'CASH',
            payment.payment_method or 'Efectivo'
        )
        payment_date_str = payment.payment_date.strftime('%d/%m/%Y %H:%M') if payment.payment_date else ''
        
        return PaymentVoucherType(
            payment_id=payment.id,
            company_name=company.commercial_name or company.legal_name or 'Empresa',
            company_ruc=company.ruc,
            company_address=company.fiscal_address,
            client_name=client.full_name if hasattr(client, 'full_name') else f"{getattr(client, 'first_name', '')} {getattr(client, 'last_name', '')}".strip(),
            client_dni=getattr(client, 'dni', None) or getattr(client, 'document_number', None),
            amount=payment.amount,
            payment_date=payment_date_str,
            payment_method=method_label,
            reference_number=payment.reference_number or f"PAG-{payment.id}",
            installment_lines=installment_lines,
            notes=payment.observations,
        )
