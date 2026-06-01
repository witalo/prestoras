"""
Correccion puntual: pago de ROSARIO RUTH RIVERA DE TICONA
Cambia el pago incorrecto de 432 a 296.

Ejecutar:
    python fix_pago_rosario.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'prestoras.settings')
django.setup()

from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from datetime import datetime

from apps.clients.models import Client
from apps.loans.models import Loan, Installment
from apps.payments.models import Payment, PaymentInstallment


DNI      = '29301535'
MONTO_CORRECTO = Decimal('296.00')

with transaction.atomic():
    # Buscar cliente
    try:
        client = Client.objects.get(dni=DNI)
    except Client.DoesNotExist:
        print(f'ERROR: No se encontro cliente con DNI {DNI}')
        exit(1)
    print(f'Cliente : {client.full_name} (DNI {client.dni})')

    # Buscar el prestamo cargado (el mas reciente)
    loan = Loan.objects.filter(client=client).order_by('-created_at').first()
    if not loan:
        print('ERROR: No se encontro prestamo para este cliente')
        exit(1)
    print(f'Prestamo: #{loan.id} | total={loan.total_amount} | paid={loan.paid_amount} | pending={loan.pending_amount} | status={loan.status}')

    # Buscar el pago incorrecto
    pago = Payment.objects.filter(loan=loan).order_by('-created_at').first()
    if not pago:
        print('ERROR: No se encontro pago para este prestamo')
        exit(1)
    print(f'Pago    : #{pago.id} | amount={pago.amount} | fecha={pago.payment_date}')

    # Confirmar que es el pago incorrecto
    if pago.amount != Decimal('432.00'):
        print(f'AVISO: El pago tiene monto {pago.amount}, no 432.00 — revisar manualmente')
        exit(1)

    # 1. Eliminar registros PaymentInstallment
    PaymentInstallment.objects.filter(payment=pago).delete()

    # 2. Resetear cuotas a PENDING con paid_amount=0
    Installment.objects.filter(loan=loan).update(paid_amount=Decimal('0.00'), status='PENDING')
    print(f'Cuotas  : {loan.number_of_installments} cuotas reseteadas a PENDING')

    # 3. Eliminar el pago incorrecto
    pago.delete()
    print(f'Pago #{pago.id} eliminado')

    # 4. Resetear el prestamo
    loan.paid_amount    = Decimal('0.00')
    loan.pending_amount = loan.total_amount
    loan.status         = 'ACTIVE'
    loan.save(update_fields=['paid_amount', 'pending_amount', 'status'])
    print(f'Prestamo reseteado: paid=0 | pending={loan.total_amount} | status=ACTIVE')

    # 5. Crear nuevo pago con monto correcto
    fecha_pago = datetime(2026, 5, 31, 0, 0, 0)
    from django.utils import timezone as tz
    paid_dt = tz.make_aware(fecha_pago)

    from apps.users.models import User
    collector = User.objects.filter(company_id=loan.company_id, role='ADMIN').first()

    nuevo_pago = Payment(
        company_id      = loan.company_id,
        loan            = loan,
        client          = client,
        amount          = MONTO_CORRECTO,
        payment_date    = paid_dt,
        payment_method  = 'CASH',
        collector       = collector,
        status          = 'COMPLETED',
        observations    = 'Carga historica desde sistema anterior',
    )
    nuevo_pago.save()  # distribuye en cuotas automaticamente
    print(f'Nuevo pago #{nuevo_pago.id} de S/ {MONTO_CORRECTO} registrado correctamente')

    loan.refresh_from_db()
    print(f'\nEstado final del prestamo:')
    print(f'  paid_amount    = {loan.paid_amount}')
    print(f'  pending_amount = {loan.pending_amount}')
    print(f'  status         = {loan.status}')

print('\nCorreccion completada con exito.')
