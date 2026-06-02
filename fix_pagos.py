import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'prestoras.settings')
django.setup()

from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from apps.payments.models import Payment, PaymentInstallment
from apps.loans.models import Installment

# ─── Pagos a corregir ─────────────────────────────────────────────────────────
PAGOS = [
    {"id": 221, "original": Decimal("39.99"), "correcto": Decimal("40.00")},
    {"id": 240, "original": Decimal("29.99"), "correcto": Decimal("30.00")},
]

DRY_RUN = True  # cambia a False para aplicar los cambios reales

# ─────────────────────────────────────────────────────────────────────────────
def sep(): print("=" * 70)

def recalcular_cuota(inst_id, dry_run):
    """Recalcula paid_amount de una cuota sumando todos sus PaymentInstallments."""
    total = PaymentInstallment.objects.filter(
        installment_id=inst_id
    ).aggregate(t=Sum("amount_applied"))["t"] or Decimal("0.00")
    inst = Installment.objects.get(id=inst_id)
    antes = inst.paid_amount
    if not dry_run:
        inst.paid_amount = total
        inst.save(update_fields=["paid_amount"])
        inst.update_status()
        inst.refresh_from_db()
    return inst, antes, total

# ─────────────────────────────────────────────────────────────────────────────
prefix = "[DRY RUN] " if DRY_RUN else ""

for cfg in PAGOS:
    sep()
    pid      = cfg["id"]
    original = cfg["original"]
    correcto = cfg["correcto"]

    print(f"{prefix}PAGO #{pid}  ({original} → {correcto})\n")

    try:
        pago = Payment.objects.get(id=pid)
    except Payment.DoesNotExist:
        print(f"  ERROR: Pago #{pid} no encontrado. Se omite.")
        continue

    if pago.amount != correcto:
        print(f"  ERROR: amount en BD es {pago.amount}, se esperaba {correcto}.")
        print(f"  Asegúrate de haber editado el monto en el admin primero.")
        continue

    loan = pago.loan

    pis = list(
        PaymentInstallment.objects
        .filter(payment=pago)
        .order_by("installment__installment_number")
        .select_related("installment")
    )

    if not pis:
        print(f"  ERROR: No hay PaymentInstallments para el pago #{pid}.")
        continue

    original_pi = pis[0]    # la cuota que recibió el pago original
    extra_pis   = pis[1:]   # cuotas contaminadas por el re-save

    # ── Mostrar qué se va a hacer ─────────────────────────────────────────────
    print(f"  PaymentInstallment principal — cuota #{original_pi.installment.installment_number} (id={original_pi.installment_id}):")
    print(f"    amount_applied: {original_pi.amount_applied}  →  {correcto}")

    if extra_pis:
        print(f"  PaymentInstallments contaminados a eliminar ({len(extra_pis)}):")
        for pi in extra_pis:
            print(f"    Cuota #{pi.installment.installment_number} (id={pi.installment_id}): applied={pi.amount_applied}")

    print(f"\n  Recálculo de cuotas (paid_amount = suma real de sus PaymentInstallments):")

    # Cuota principal: mostrar qué pasaría DESPUÉS de setear amount_applied=correcto
    inst_principal = original_pi.installment
    otros_pi_principal = PaymentInstallment.objects.filter(
        installment_id=inst_principal.id
    ).exclude(payment_id=pid).aggregate(t=Sum("amount_applied"))["t"] or Decimal("0.00")
    nuevo_paid_principal = otros_pi_principal + correcto
    print(f"    Cuota #{inst_principal.installment_number}: {inst_principal.paid_amount} → {nuevo_paid_principal}"
          f"  (otros pagos: {otros_pi_principal} + este: {correcto})")

    # Cuotas contaminadas: mostrar qué quedaría después de eliminar su PI
    for pi in extra_pis:
        inst = pi.installment
        otros = PaymentInstallment.objects.filter(
            installment_id=inst.id
        ).exclude(payment_id=pid).aggregate(t=Sum("amount_applied"))["t"] or Decimal("0.00")
        print(f"    Cuota #{inst.installment_number}: {inst.paid_amount} → {otros}"
              f"  (otros pagos: {otros}, se elimina el de este pago: {pi.amount_applied})")

    nuevo_paid_loan    = loan.paid_amount - original
    nuevo_pending_loan = loan.total_amount - nuevo_paid_loan
    print(f"\n  Préstamo #{loan.id}: paid {loan.paid_amount} → {nuevo_paid_loan}"
          f" | pending {loan.pending_amount} → {nuevo_pending_loan}")

    # ── Aplicar cambios ───────────────────────────────────────────────────────
    if not DRY_RUN:
        with transaction.atomic():

            # 1. Eliminar PaymentInstallments contaminados
            for pi in extra_pis:
                pi.delete()

            # 2. Corregir amount_applied del PI principal
            original_pi.amount_applied = correcto
            original_pi.save(update_fields=["amount_applied"])

            # 3. Recalcular paid_amount de TODAS las cuotas afectadas desde SUM real
            todas_inst_ids = [pi.installment_id for pi in pis]
            for inst_id in todas_inst_ids:
                inst, antes, nuevo = recalcular_cuota(inst_id, dry_run=False)
                print(f"  ✓ Cuota id={inst_id}: paid_amount {antes} → {inst.paid_amount} | status={inst.status}")

            # 4. Corregir doble conteo en el préstamo
            loan.refresh_from_db()
            loan.paid_amount    = loan.paid_amount - original
            loan.pending_amount = loan.total_amount - loan.paid_amount
            if loan.pending_amount <= Decimal("0.00"):
                loan.status = "COMPLETED"
            elif loan.end_date and loan.end_date < timezone.now().date():
                loan.status = "DEFAULTING"
            else:
                loan.status = "ACTIVE"
            loan.save(update_fields=["paid_amount", "pending_amount", "status"])
            print(f"  ✓ Préstamo #{loan.id}: paid={loan.paid_amount} | pending={loan.pending_amount} | status={loan.status}")

            # 5. Recalcular clasificación del cliente
            pago.client.update_classification()
            print(f"  ✓ Clasificación del cliente recalculada.")

        print(f"\n  ✅ Pago #{pid} corregido.")
    else:
        print(f"\n  {prefix}Sin cambios aplicados.")

sep()
if DRY_RUN:
    print("DRY RUN completado — revisa los valores arriba.")
    print("Si todo se ve correcto, pon  DRY_RUN = False  y vuelve a ejecutar.")
else:
    print("Corrección completada para todos los pagos.")
sep()
