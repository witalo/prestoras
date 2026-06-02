import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'prestoras.settings')
django.setup()

from decimal import Decimal
from django.db.models import Sum
from apps.payments.models import Payment, PaymentInstallment
from apps.loans.models import Loan, Installment

# ─── Pagos a revisar ──────────────────────────────────────────────────────────
PAGOS = [
    {"id": 221, "original": Decimal("39.99"), "correcto": Decimal("40.00")},
    {"id": 240, "original": Decimal("29.99"), "correcto": Decimal("30.00")},
]

def separador():
    print("=" * 70)

for cfg in PAGOS:
    separador()
    pid        = cfg["id"]
    original   = cfg["original"]
    correcto   = cfg["correcto"]

    try:
        pago = Payment.objects.get(id=pid)
    except Payment.DoesNotExist:
        print(f"ERROR: Pago #{pid} no encontrado.")
        continue

    loan   = pago.loan
    client = pago.client

    print(f"PAGO #{pid}  —  {client.full_name}")
    print(f"  amount en BD : {pago.amount}  (original={original}, correcto={correcto})")
    print(f"  método       : {pago.payment_method}")
    print(f"  fecha        : {pago.payment_date.date()}")
    print()

    # ── PaymentInstallments del pago ──────────────────────────────────────────
    pis = list(
        PaymentInstallment.objects
        .filter(payment=pago)
        .order_by("installment__installment_number")
        .select_related("installment")
    )
    print(f"  PaymentInstallments ({len(pis)} registros):")
    total_aplicado = Decimal("0.00")
    for i, pi in enumerate(pis):
        inst = pi.installment
        marca = ""
        if i == 0:
            if pi.amount_applied != correcto:
                marca = "  ← DEBERÍA SER " + str(correcto)
            else:
                marca = "  ✓"
        else:
            marca = "  ← CONTAMINADO (creado por re-save del admin)"
        print(f"    Cuota #{inst.installment_number:>3} (id={inst.id:>5}): "
              f"amount_applied={pi.amount_applied}{marca}")
        total_aplicado += pi.amount_applied

    print(f"  SUMA de amount_applied: {total_aplicado}  "
          f"({'✓ correcto' if total_aplicado == correcto else '✗ INCORRECTO, debería ser ' + str(correcto)})")
    print()

    # ── Estado de las cuotas afectadas ────────────────────────────────────────
    inst_ids = [pi.installment_id for pi in pis]
    print(f"  Cuotas afectadas ({len(inst_ids)}):")
    for pi in pis:
        inst = pi.installment
        # paid_amount esperado solo por este pago (si es la cuota principal)
        esperado_en_cuota = inst.total_amount  # si quedó pagada al 100%
        ok = ""
        if inst.paid_amount > inst.total_amount:
            ok = "  ✗ OVERPAID"
        elif inst.status == "PAID" and inst.paid_amount == inst.total_amount:
            ok = "  ✓"
        print(f"    Cuota #{inst.installment_number:>3} (id={inst.id:>5}): "
              f"paid={inst.paid_amount}/{inst.total_amount}  status={inst.status}{ok}")
    print()

    # ── Estado del préstamo ───────────────────────────────────────────────────
    # Calcular cuánto debería ser paid_amount sumando todos los pagos COMPLETED
    pagos_completados = Payment.objects.filter(
        loan=loan, status="COMPLETED"
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    print(f"  PRÉSTAMO #{loan.id}:")
    print(f"    total_amount   = {loan.total_amount}")
    print(f"    paid_amount BD = {loan.paid_amount}")
    print(f"    paid_amount Q  = {pagos_completados}  (suma real de todos los pagos COMPLETED)")
    diferencia = loan.paid_amount - pagos_completados
    if diferencia != 0:
        print(f"    DIFERENCIA     = {diferencia}  ✗ HAY DOBLE CONTEO")
    else:
        print(f"    DIFERENCIA     = 0  ✓ consistente")
    print(f"    pending_amount = {loan.pending_amount}")
    print(f"    status         = {loan.status}")
    print()

separador()
print("DIAGNÓSTICO COMPLETO — ningún dato fue modificado.")
separador()
