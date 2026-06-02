import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'prestoras.settings')
django.setup()

from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from apps.payments.models import Payment, PaymentInstallment

# ─── Pagos a corregir ─────────────────────────────────────────────────────────
PAGOS = [
    {"id": 221, "original": Decimal("39.99"), "correcto": Decimal("40.00")},
    {"id": 240, "original": Decimal("29.99"), "correcto": Decimal("30.00")},
]

DRY_RUN = True  # cambia a False para aplicar los cambios reales

# ─────────────────────────────────────────────────────────────────────────────
def sep(): print("=" * 70)

for cfg in PAGOS:
    sep()
    pid      = cfg["id"]
    original = cfg["original"]
    correcto = cfg["correcto"]
    prefix   = "[DRY RUN] " if DRY_RUN else ""

    print(f"{prefix}CORRIGIENDO PAGO #{pid}  ({original} → {correcto})\n")

    try:
        pago = Payment.objects.get(id=pid)
    except Payment.DoesNotExist:
        print(f"  ERROR: Pago #{pid} no encontrado. Se omite.")
        continue

    if pago.amount != correcto:
        print(f"  ERROR: amount en BD es {pago.amount}, se esperaba {correcto}.")
        print(f"  Verifica que ya editaste este pago en el admin.")
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

    original_pi = pis[0]
    extra_pis   = pis[1:]

    print(f"  Préstamo #{loan.id}: paid={loan.paid_amount} | pending={loan.pending_amount} | total={loan.total_amount}")
    print(f"  PaymentInstallments ({len(pis)}):")
    for i, pi in enumerate(pis):
        inst = pi.installment
        nota = "← principal" if i == 0 else "← CONTAMINADO"
        print(f"    Cuota #{inst.installment_number:>3} (id={inst.id}): applied={pi.amount_applied}  {nota}")

    nuevo_paid    = loan.paid_amount - original
    nuevo_pending = loan.total_amount - nuevo_paid
    print(f"\n  Cambios a aplicar:")
    print(f"    PaymentInstallment cuota principal: {original_pi.amount_applied} → {correcto}")
    for pi in extra_pis:
        print(f"    Eliminar PaymentInstallment cuota #{pi.installment.installment_number} (applied={pi.amount_applied}) y revertir cuota")
    print(f"    loan.paid_amount:    {loan.paid_amount} → {nuevo_paid}")
    print(f"    loan.pending_amount: {loan.pending_amount} → {nuevo_pending}")

    if not DRY_RUN:
        with transaction.atomic():
            # 1. Revertir cuotas contaminadas
            for pi in extra_pis:
                inst = pi.installment
                revertido = max(Decimal("0.00"), inst.paid_amount - pi.amount_applied)
                inst.paid_amount = revertido
                inst.save(update_fields=["paid_amount"])
                inst.update_status()
                pi.delete()

            # 2. Corregir amount_applied de la cuota principal
            original_pi.amount_applied = correcto
            original_pi.save(update_fields=["amount_applied"])
            original_pi.installment.refresh_from_db()
            original_pi.installment.update_status()

            # 3. Corregir el doble conteo en el préstamo
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

            # 4. Recalcular clasificación del cliente
            pago.client.update_classification()

        print(f"\n  ✅ Pago #{pid} corregido.")
    else:
        print(f"\n  [DRY RUN] Sin cambios aplicados.")

sep()
if DRY_RUN:
    print("DRY RUN completado. Pon DRY_RUN = False y vuelve a ejecutar para corregir.")
else:
    print("Corrección completada para todos los pagos.")
sep()
