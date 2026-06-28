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
from .types import (
    PaymentType, PaymentVoucherType, DashboardStatsType, CollectorStatType,
    DailyPaymentType, SaldosReportRowType,
)
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
        return list(Payment.objects.filter(loan_id=loan_id).prefetch_related('payment_installments').order_by('-payment_date'))
    
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
        Pagos de un cobrador. Admin puede ver cualquiera; cobrador solo los suyos.
        """
        user = get_current_user_from_info(info)
        if not user:
            return []
        if user.role == 'COLLECTOR' and user.id != collector_id:
            return []
        if user.company_id != company_id:
            return []
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
        ).select_related('loan', 'client', 'collector').prefetch_related('payment_installments')
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
        """Resumen completo para el dashboard. Admin ve toda la empresa; cobrador solo su cartera."""
        from apps.loans.models import Loan
        from apps.clients.models import Client
        from apps.users.models import User
        from django.db.models import Count, Q

        today = timezone.now().date()
        ZERO = Decimal('0.00')

        def _empty():
            return DashboardStatsType(
                total_clients=0, active_loans=0, completed_loans=0, defaulting_loans=0,
                total_disbursed=ZERO, total_collected=ZERO, total_pending=ZERO, total_penalty=ZERO,
                collections_today=0, amount_today=ZERO, collector_stats=[],
            )

        current_user = get_current_user_from_info(info)

        # Cobrador: forzar sus propias stats
        if current_user and current_user.role == 'COLLECTOR':
            if current_user.company_id != company_id:
                return _empty()
            if collector_id is not None and collector_id != current_user.id:
                return _empty()
            collector_id = current_user.id

        if collector_id is not None:
            # ── Vista del cobrador: solo su cartera ──
            try:
                collector = User.objects.prefetch_related('assigned_clients').get(
                    id=collector_id, company_id=company_id
                )
            except User.DoesNotExist:
                return _empty()

            client_ids = list(collector.assigned_clients.filter(is_active=True).values_list('id', flat=True))
            if not client_ids:
                return _empty()

            loans_qs = Loan.objects.filter(company_id=company_id, client_id__in=client_ids)
            active_qs = loans_qs.filter(status__in=['ACTIVE', 'DEFAULTING'])

            # Solo préstamos en circulación (ACTIVE + DEFAULTING) para todos los montos
            agg = active_qs.aggregate(
                disbursed=Sum('initial_amount'),
                collected=Sum('paid_amount'),
                pending=Sum('pending_amount'),
                penalty=Sum('penalty_applied'),
            )
            today_agg = Payment.objects.filter(
                company_id=company_id, collector_id=collector_id,
                status='COMPLETED', payment_date__date=today
            ).aggregate(total=Sum('amount'), cnt=Count('id'))

            return DashboardStatsType(
                total_clients=len(client_ids),
                active_loans=active_qs.count(),
                completed_loans=loans_qs.filter(status='COMPLETED').count(),
                defaulting_loans=loans_qs.filter(status='DEFAULTING').count(),
                total_disbursed=agg['disbursed'] or ZERO,
                total_collected=agg['collected'] or ZERO,
                total_pending=agg['pending'] or ZERO,
                total_penalty=agg['penalty'] or ZERO,
                collections_today=today_agg['cnt'] or 0,
                amount_today=today_agg['total'] or ZERO,
                collector_stats=[],
            )

        # ── Vista del admin: toda la empresa ──
        loans_qs = Loan.objects.filter(company_id=company_id)
        active_qs = loans_qs.filter(status__in=['ACTIVE', 'DEFAULTING'])

        # Solo préstamos en circulación (ACTIVE + DEFAULTING) para todos los montos
        agg = active_qs.aggregate(
            disbursed=Sum('initial_amount'),
            collected=Sum('paid_amount'),
            pending=Sum('pending_amount'),
            penalty=Sum('penalty_applied'),
        )
        today_agg = Payment.objects.filter(
            company_id=company_id, status='COMPLETED', payment_date__date=today
        ).aggregate(total=Sum('amount'), cnt=Count('id'))

        total_clients = Client.objects.filter(company_id=company_id, is_active=True).count()

        # Stats por usuario: todos los usuarios activos de la empresa (admin + cobradores)
        collector_stats = []
        users = User.objects.filter(
            company_id=company_id, is_active=True
        ).prefetch_related('assigned_clients').order_by('role', 'first_name', 'last_name')

        for col in users:
            col_client_ids = list(col.assigned_clients.filter(is_active=True).values_list('id', flat=True))
            col_active = Loan.objects.filter(
                company_id=company_id, client_id__in=col_client_ids,
                status__in=['ACTIVE', 'DEFAULTING']
            ).count() if col_client_ids else 0
            col_today = Payment.objects.filter(
                company_id=company_id, collector_id=col.id,
                status='COMPLETED', payment_date__date=today
            ).aggregate(total=Sum('amount'))['total'] or ZERO

            collector_stats.append(CollectorStatType(
                collector_id=col.id,
                collector_name=col.full_name,
                total_clients=len(col_client_ids),
                active_loans=col_active,
                amount_collected_today=col_today,
                role=col.role,
            ))

        return DashboardStatsType(
            total_clients=total_clients,
            active_loans=active_qs.count(),
            completed_loans=loans_qs.filter(status='COMPLETED').count(),
            defaulting_loans=loans_qs.filter(status='DEFAULTING').count(),
            total_disbursed=agg['disbursed'] or ZERO,
            total_collected=agg['collected'] or ZERO,
            total_pending=agg['pending'] or ZERO,
            total_penalty=agg['penalty'] or ZERO,
            collections_today=today_agg['cnt'] or 0,
            amount_today=today_agg['total'] or ZERO,
            collector_stats=collector_stats,
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

    @strawberry.field(name="saldosReport")
    def saldos_report(
        self,
        info: Info,
        company_id: int,
        start_date: date,
        end_date: date,
        zone_id: Optional[int] = None,
        periodicity: Optional[str] = None,
        loan_type_id: Optional[int] = None,
    ) -> List[SaldosReportRowType]:
        """
        Reporte de saldos: préstamos activos/morosos con pagos diarios
        en el rango de fechas. Soporta filtros por zona, periodicidad y tipo.
        """
        from apps.loans.models import Loan
        from django.db.models import Sum
        from django.db.models.functions import TruncDate
        from collections import defaultdict
        from datetime import timedelta, datetime, time as dt_time
        from zoneinfo import ZoneInfo

        user = get_current_user_from_info(info)
        if not user:
            return []

        loans_qs = Loan.objects.filter(
            company_id=company_id,
            status__in=['ACTIVE', 'DEFAULTING'],
        ).select_related('client', 'client__zone', 'loan_type')

        if user.role == 'COLLECTOR':
            client_ids = list(user.assigned_clients.values_list('id', flat=True))
            if not client_ids:
                return []
            loans_qs = loans_qs.filter(client_id__in=client_ids)

        if zone_id:
            loans_qs = loans_qs.filter(client__zone_id=zone_id)
        if periodicity:
            loans_qs = loans_qs.filter(periodicity=periodicity)
        if loan_type_id:
            loans_qs = loans_qs.filter(loan_type_id=loan_type_id)

        loans_list = list(
            loans_qs.order_by('client__zone__name', 'client__last_name', 'client__first_name')
        )
        if not loans_list:
            return []

        loan_ids = [l.id for l in loans_list]

        # TruncDate con timezone Lima para que el día sea correcto (UTC-5)
        lima_tz = ZoneInfo('America/Lima')

        # Filtro por rango completo del día en hora Lima
        start_dt = datetime.combine(start_date, dt_time.min, tzinfo=lima_tz)
        end_dt   = datetime.combine(end_date,   dt_time.max, tzinfo=lima_tz)

        payments_agg = (
            Payment.objects
            .filter(
                company_id=company_id,
                loan_id__in=loan_ids,
                status='COMPLETED',
                payment_date__gte=start_dt,
                payment_date__lte=end_dt,
            )
            .annotate(pay_date=TruncDate('payment_date', tzinfo=lima_tz))
            .values('loan_id', 'pay_date')
            .annotate(day_total=Sum('amount'))
        )

        payment_map: dict = defaultdict(dict)
        for row in payments_agg:
            if row['pay_date']:
                dstr = row['pay_date'].isoformat()
                payment_map[row['loan_id']][dstr] = row['day_total']

        # Generar todas las fechas del rango
        all_dates = []
        cur = start_date
        while cur <= end_date:
            all_dates.append(cur.isoformat())
            cur += timedelta(days=1)

        result = []
        for loan in loans_list:
            client = loan.client
            zone = getattr(client, 'zone', None)

            daily = [
                DailyPaymentType(
                    date=d,
                    amount=payment_map[loan.id].get(d, Decimal('0.00')),
                )
                for d in all_dates
            ]

            result.append(SaldosReportRowType(
                loan_id=loan.id,
                client_dni=client.dni or '',
                client_full_name=(
                    client.full_name
                    if hasattr(client, 'full_name') and client.full_name
                    else f"{client.first_name} {client.last_name}".strip()
                ),
                zone_name=zone.name if zone else None,
                zone_id=zone.id if zone else None,
                loan_start_date=(loan.loan_date or loan.start_date).isoformat() if (loan.loan_date or loan.start_date) else '',
                loan_actual_start_date=loan.start_date.isoformat() if loan.start_date else '',
                loan_end_date=loan.end_date.isoformat() if loan.end_date else '',
                initial_amount=loan.initial_amount,
                interest_rate=loan.interest_rate,
                total_amount=loan.total_amount,
                paid_amount=loan.paid_amount,
                pending_amount=loan.pending_amount,
                loan_status=loan.status,
                loan_type_name=loan.loan_type.name if loan.loan_type else None,
                periodicity=loan.periodicity,
                classification=client.classification or 'NORMAL',
                daily_payments=daily,
            ))

        return result
