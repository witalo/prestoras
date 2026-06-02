import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'prestoras.settings')
django.setup()

from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from apps.payments.models import Payment, PaymentInstallment
from apps.loans.models import Installment

DRY_RUN = False  # cambia a False para aplicar los cambios reales

# ─── Correcciones exactas (calculadas desde el diagnóstico) ───────────────────
#
# Pago #221 (39.99 → 40.00):
#   La cuota #3 recibió todo el pago original.
#   El re-save creó un PI falso en cuota #4.
#   PIs correctos: {cuota3 (id=2026): 40.00}
#   PIs a eliminar: cuota4 (id=2027)
#
# Pago #240 (29.99 → 30.00):
#   El pago original se dividió: 8.99 a cuota #13 y 21.00 a cuota #14.
#   El re-save cambió cuota #14 de 21.00 a 21.23 y creó cuota #15 con 8.77.
#   PIs correctos: {cuota13 (id=3237): 8.99, cuota14 (id=3238): 21.01}
#   PIs a eliminar: cuota15 (id=3239)
#
CORRECCIONES = {
    221: {
        "original":     Decimal("39.99"),
        "correcto":     Decimal("40.00"),
        "loan_id":      67,
        "pis_correctos": {
            2026: Decimal("40.00"),   # cuota #3
        },
        "pis_eliminar": [2027],       # cuota #4
    },
    240: {
        "original":     Decimal("29.99"),
        "correcto":     Decimal("30.00"),
        "loan_id":      98,
        "pis_correctos": {
            3237: Decimal("8.99"),    # cuota #13 — sin cambio (ya era correcto)
            3238: Decimal("21.01"),   # cuota #14 — corregido (30.00 - 8.99)
        },
        "pis_eliminar": [3239],       # cuota #15
    },
}

# ─────────────────────────────────────────────────────────────────────────────
def sep(): print("=" * 70)
prefix = "[DRY RUN] " if DRY_RUN else ""

for pid, cfg in CORRECCIONES.items():
    sep()
    print(f"{prefix}PAGO #{pid}  ({cfg['original']} → {cfg['correcto']})\n")

    try:
        pago = Payment.objects.get(id=pid)
    except Payment.DoesNotExist:
        print(f"  ERROR: Pago #{pid} no encontrado.")
        continue

    if pago.amount != cfg["correcto"]:
        print(f"  ERROR: amount en BD = {pago.amount}, esperado {cfg['correcto']}.")
        continue

    from apps.loans.models import Loan
    loan = Loan.objects.get(id=cfg["loan_id"])

    # ── Mostrar plan ──────────────────────────────────────────────────────────
    print("  PaymentInstallments — cambios:")
    for inst_id, nuevo_applied in cfg["pis_correctos"].items():
        pi = PaymentInstallment.objects.filter(payment_id=pid, installment_id=inst_id).first()
        actual = pi.amount_applied if pi else "NO EXISTE"
        marca  = "(sin cambio)" if pi and pi.amount_applied == nuevo_applied else f"→ {nuevo_applied}"
        print(f"    Cuota id={inst_id}: applied={actual}  {marca}")
    for inst_id in cfg["pis_eliminar"]:
        pi = PaymentInstallment.objects.filter(payment_id=pid, installment_id=inst_id).first()
        actual = pi.amount_applied if pi else "ya no existe"
        print(f"    Cuota id={inst_id}: applied={actual}  → ELIMINAR")

    print("\n  Recálculo de cuotas afectadas:")
    todos_inst_ids = list(cfg["pis_correctos"].keys()) + cfg["pis_eliminar"]
    for inst_id in todos_inst_ids:
        inst = Installment.objects.get(id=inst_id)
        otros = PaymentInstallment.objects.filter(
            installment_id=inst_id
        ).exclude(payment_id=pid).aggregate(t=Sum("amount_applied"))["t"] or Decimal("0.00")
        nuevo_applied = cfg["pis_correctos"].get(inst_id, Decimal("0.00"))
        nuevo_paid = otros + nuevo_applied
        print(f"    Cuota id={inst_id} #{inst.installment_number}: "
              f"paid {inst.paid_amount}/{inst.total_amount} → {nuevo_paid}/{inst.total_amount}")

    nuevo_paid_loan    = loan.paid_amount - cfg["original"]
    nuevo_pending_loan = loan.total_amount - nuevo_paid_loan
    print(f"\n  Préstamo #{loan.id}:")
    print(f"    paid_amount:    {loan.paid_amount} → {nuevo_paid_loan}")
    print(f"    pending_amount: {loan.pending_amount} → {nuevo_pending_loan}")

    # ── Aplicar ───────────────────────────────────────────────────────────────
    if not DRY_RUN:
        with transaction.atomic():

            # 1. Eliminar PIs contaminados
            for inst_id in cfg["pis_eliminar"]:
                PaymentInstallment.objects.filter(
                    payment_id=pid, installment_id=inst_id
                ).delete()

            # 2. Actualizar/crear los PIs correctos
            for inst_id, nuevo_applied in cfg["pis_correctos"].items():
                pi, _ = PaymentInstallment.objects.get_or_create(
                    payment_id=pid, installment_id=inst_id
                )
                pi.amount_applied = nuevo_applied
                pi.save(update_fields=["amount_applied"])

            # 3. Recalcular paid_amount de cada cuota afectada desde SUM real
            for inst_id in todos_inst_ids:
                total = PaymentInstallment.objects.filter(
                    installment_id=inst_id
                ).aggregate(t=Sum("amount_applied"))["t"] or Decimal("0.00")
                inst = Installment.objects.get(id=inst_id)
                inst.paid_amount = total
                inst.save(update_fields=["paid_amount"])
                inst.update_status()
                inst.refresh_from_db()
                print(f"  ✓ Cuota id={inst_id} #{inst.installment_number}: "
                      f"paid={inst.paid_amount} | status={inst.status}")

            # 4. Corregir doble conteo en el préstamo
            loan.refresh_from_db()
            loan.paid_amount    = loan.paid_amount - cfg["original"]
            loan.pending_amount = loan.total_amount - loan.paid_amount
            if loan.pending_amount <= Decimal("0.00"):
                loan.status = "COMPLETED"
            elif loan.end_date and loan.end_date < timezone.now().date():
                loan.status = "DEFAULTING"
            else:
                loan.status = "ACTIVE"
            loan.save(update_fields=["paid_amount", "pending_amount", "status"])
            print(f"  ✓ Préstamo #{loan.id}: paid={loan.paid_amount} | "
                  f"pending={loan.pending_amount} | status={loan.status}")

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
    print("Corrección completada.")
sep()
