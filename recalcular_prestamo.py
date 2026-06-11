"""
Recalcula paid_amount, pending_amount y estado de un préstamo desde cero,
usando los PaymentInstallment como fuente de verdad.

Uso:
    python recalcular_prestamo.py <loan_id>          # un préstamo específico
    python recalcular_prestamo.py --all              # todos los préstamos activos

Opciones:
    DRY_RUN = True   → solo muestra qué cambiaría, no toca la BD
    DRY_RUN = False  → aplica los cambios
"""
import django, os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'prestoras.settings')
django.setup()

from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from apps.loans.models import Loan, Installment
from apps.payments.models import Payment, PaymentInstallment

# ── Configuración ─────────────────────────────────────────────────────────────
DRY_RUN = True   # Cambia a False para aplicar los cambios reales
# ─────────────────────────────────────────────────────────────────────────────

SEP = "=" * 70
prefix = "[DRY RUN] " if DRY_RUN else ""


def recalcular_prestamo(loan_id: int) -> bool:
    """
    Recalcula un préstamo desde sus PaymentInstallments.
    Retorna True si hubo diferencia (el préstamo estaba mal).
    """
    print(SEP)
    try:
        loan = Loan.objects.select_related('client').get(id=loan_id)
    except Loan.DoesNotExist:
        print(f"❌ Préstamo #{loan_id} no encontrado.")
        return False

    print(f"Préstamo #{loan.id} — {loan.client.full_name}")
    print(f"  Total del préstamo : S/ {loan.total_amount}")
    print(f"  Pagos registrados  : {Payment.objects.filter(loan=loan, status='COMPLETED').count()} pago(s)")

    # ── 1. Calcular paid_amount real de cada cuota ────────────────────────────
    installments = Installment.objects.filter(loan=loan).order_by('installment_number')
    total_correcto = Decimal('0.00')
    cambios_cuotas = []

    for inst in installments:
        paid_real = PaymentInstallment.objects.filter(
            installment=inst
        ).aggregate(t=Sum('amount_applied'))['t'] or Decimal('0.00')

        total_correcto += paid_real

        if inst.paid_amount != paid_real:
            cambios_cuotas.append((inst, paid_real))

    # ── 2. Determinar nuevo estado del préstamo ───────────────────────────────
    pending_correcto = loan.total_amount - total_correcto
    pending_correcto = max(Decimal('0.00'), pending_correcto)

    today = timezone.now().date()
    if pending_correcto <= Decimal('0.00'):
        nuevo_status = 'COMPLETED'
    elif loan.end_date and loan.end_date < today:
        nuevo_status = 'DEFAULTING'
    else:
        nuevo_status = 'ACTIVE'

    # ── 3. Mostrar diagnóstico ────────────────────────────────────────────────
    hay_diferencia = (
        loan.paid_amount != total_correcto
        or loan.pending_amount != pending_correcto
        or loan.status != nuevo_status
        or len(cambios_cuotas) > 0
    )

    print(f"\n  {'─'*40}")
    print(f"  {'Campo':<20} {'BD actual':>14}  {'Correcto':>14}")
    print(f"  {'─'*40}")
    print(f"  {'paid_amount':<20} {loan.paid_amount:>14}  {total_correcto:>14}"
          + (" ← DIFERENTE" if loan.paid_amount != total_correcto else ""))
    print(f"  {'pending_amount':<20} {loan.pending_amount:>14}  {pending_correcto:>14}"
          + (" ← DIFERENTE" if loan.pending_amount != pending_correcto else ""))
    print(f"  {'status':<20} {loan.status:>14}  {nuevo_status:>14}"
          + (" ← DIFERENTE" if loan.status != nuevo_status else ""))

    if cambios_cuotas:
        print(f"\n  Cuotas con paid_amount incorrecto:")
        for inst, correcto in cambios_cuotas:
            print(f"    Cuota #{inst.installment_number} (id={inst.id}): "
                  f"BD={inst.paid_amount} → correcto={correcto}  "
                  f"(total cuota: {inst.total_amount})")
    else:
        print(f"\n  Cuotas: todas correctas ✓")

    if not hay_diferencia:
        print(f"\n  ✅ Préstamo #{loan_id} ya está correcto — sin cambios.")
        return False

    # ── 4. Aplicar corrección ─────────────────────────────────────────────────
    if DRY_RUN:
        print(f"\n  {prefix}No se aplicaron cambios. Pon DRY_RUN = False para corregir.")
        return True

    print(f"\n  Aplicando corrección...")
    with transaction.atomic():
        # 4a. Corregir cada cuota
        for inst, paid_correcto in cambios_cuotas:
            inst.paid_amount = paid_correcto
            inst.save(update_fields=['paid_amount'])

        # 4b. Actualizar status de TODAS las cuotas (no solo las cambiadas)
        for inst in installments:
            inst.refresh_from_db()
            inst.update_status()

        # 4c. Corregir el préstamo usando .update() para no disparar Loan.save()
        Loan.objects.filter(id=loan.id).update(
            paid_amount=total_correcto,
            pending_amount=pending_correcto,
            status=nuevo_status,
        )

        # 4d. Reclasificar cliente
        loan.client.update_classification()

    print(f"  ✅ Préstamo #{loan_id} corregido:")
    print(f"     paid_amount    : {loan.paid_amount} → {total_correcto}")
    print(f"     pending_amount : {loan.pending_amount} → {pending_correcto}")
    print(f"     status         : {loan.status} → {nuevo_status}")
    return True


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Uso: python recalcular_prestamo.py <loan_id>")
        print("     python recalcular_prestamo.py --all")
        sys.exit(1)

    if sys.argv[1] == '--all':
        loans = Loan.objects.exclude(status__in=['CANCELLED']).order_by('id')
        total = loans.count()
        print(f"Revisando {total} préstamos...\n")
        corregidos = 0
        for loan in loans:
            if recalcular_prestamo(loan.id):
                corregidos += 1
        print(SEP)
        print(f"Resumen: {corregidos}/{total} préstamos {'requieren corrección' if DRY_RUN else 'corregidos'}.")
    else:
        try:
            loan_id = int(sys.argv[1])
        except ValueError:
            print(f"Error: '{sys.argv[1]}' no es un ID válido.")
            sys.exit(1)
        recalcular_prestamo(loan_id)

    print(SEP)
    if DRY_RUN:
        print("DRY RUN — sin cambios reales. Pon DRY_RUN = False y vuelve a ejecutar.")
    else:
        print("Corrección completada.")
    print(SEP)
