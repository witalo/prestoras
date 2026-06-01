"""
Comando Django para cargar préstamos y pagos históricos desde fixtures_prestamos.json.

Uso:
  python manage.py cargar_prestamos_json --company-id 1
  python manage.py cargar_prestamos_json --company-id 1 --dry-run
  python manage.py cargar_prestamos_json --company-id 1 --json /ruta/prestamos.json
  python manage.py cargar_prestamos_json --company-id 1 --user-id 5
  python manage.py cargar_prestamos_json --company-id 1 --fecha-pago 2026-05-31

IDEMPOTENTE: omite el préstamo si el cliente ya tiene uno con la misma
fecha de inicio y monto inicial, evitando duplicados.

Lógica de fechas:
  La FECHA del Excel es el día en que se dio el crédito.
  Las cuotas empiezan 1 período después:
    DAILY    -> primer vencimiento = FECHA + 1 día
    WEEKLY   -> primer vencimiento = FECHA + 7 días
    BIWEEKLY -> primer vencimiento = FECHA + 14 días
    MONTHLY  -> primer vencimiento = FECHA + 1 mes
    QUARTERLY-> primer vencimiento = FECHA + 3 meses

Matching de clientes:
  1. DNI exacto (8 dígitos, zero-padded)
  2. DNI numérico (sin ceros adelante)
  3. Similitud de nombre (Jaccard sobre tokens) ≥ 50%
"""
import json
import os
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from dateutil.relativedelta import relativedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.clients.models import Client
from apps.companies.models import Company, LoanType
from apps.loans.models import Loan, Installment
from apps.payments.models import Payment
from apps.users.models import User


# ─── Mapas y utilidades ───────────────────────────────────────────────────────

PERIODICITY_STEP = {
    'DAILY':     ('days',   1),
    'WEEKLY':    ('days',   7),
    'BIWEEKLY':  ('days',  14),
    'MONTHLY':   ('months', 1),
    'QUARTERLY': ('months', 3),
}


def add_period(d: date, periodicity: str, n: int = 1) -> date:
    """Avanza n períodos desde la fecha d según la periodicidad."""
    unit, mult = PERIODICITY_STEP[periodicity]
    total = n * mult
    if unit == 'days':
        return d + timedelta(days=total)
    return d + relativedelta(months=total)


def calc_start_end(fecha: date, periodicity: str, n: int):
    """
    Calcula start_date y end_date del préstamo.

    Para n > 1:
      start_date = fecha + 1 período   (fecha del primer vencimiento)
      end_date   = start_date + (n-1) períodos
    Para n = 1:
      start_date = fecha
      end_date   = fecha + 1 período   (único vencimiento)
    """
    if n == 1:
        start = fecha
        end   = add_period(fecha, periodicity, 1)
    else:
        start = add_period(fecha, periodicity, 1)
        end   = add_period(start, periodicity, n - 1)
    return start, end


def norm_str(s: str) -> str:
    """Quita tildes, pasa a mayúsculas y normaliza espacios."""
    if not s:
        return ''
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return ' '.join(s.upper().split())


def jaccard(a: str, b: str) -> float:
    """Similitud de Jaccard sobre tokens de dos cadenas."""
    ta = set(norm_str(a).split())
    tb = set(norm_str(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def dni_int(dni_str: str) -> str:
    """Devuelve el DNI como entero-string (sin ceros adelante)."""
    try:
        return str(int(dni_str))
    except (ValueError, TypeError):
        return dni_str.strip()


# ─── Generación de cuotas (replica exacta de mutations.py) ────────────────────

def _due_date(start: date, periodicity: str, index: int) -> date:
    if periodicity == 'MONTHLY':
        return start + relativedelta(months=index)
    if periodicity == 'QUARTERLY':
        return start + relativedelta(months=index * 3)
    if periodicity == 'WEEKLY':
        return start + timedelta(weeks=index)
    if periodicity == 'BIWEEKLY':
        return start + timedelta(weeks=index * 2)
    return start + timedelta(days=index)  # DAILY


def _generate_installments(loan: Loan):
    """
    Genera las cuotas del préstamo con redondeo financiero ROUND_HALF_UP.
    La última cuota absorbe el centavo de diferencia de redondeo.
    Réplica de generate_installments() en apps/loans/mutations.py.
    """
    n    = loan.number_of_installments
    unit = Decimal('0.01')

    total_interest = (
        loan.initial_amount * loan.interest_rate / Decimal('100')
    ).quantize(unit, rounding=ROUND_HALF_UP)

    capital_unit  = (loan.initial_amount / Decimal(str(n))).quantize(unit, rounding=ROUND_HALF_UP)
    interest_unit = (total_interest      / Decimal(str(n))).quantize(unit, rounding=ROUND_HALF_UP)
    total_unit    = capital_unit + interest_unit

    installments = []
    for i in range(1, n + 1):
        is_last = (i == n)
        if is_last:
            due = loan.end_date
            cap = loan.initial_amount - capital_unit  * (n - 1)
            itr = total_interest      - interest_unit * (n - 1)
            tot = loan.total_amount   - total_unit    * (n - 1)
        else:
            due = _due_date(loan.start_date, loan.periodicity, i - 1)
            cap = capital_unit
            itr = interest_unit
            tot = total_unit

        installments.append(Installment(
            loan=loan,
            installment_number=i,
            due_date=due,
            capital_amount=cap,
            interest_amount=itr,
            total_amount=tot,
            status='PENDING',
        ))

    Installment.objects.bulk_create(installments)


# ─── Comando ──────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Carga préstamos y pagos históricos desde fixtures_prestamos.json'

    def add_arguments(self, parser):
        parser.add_argument(
            '--company-id', type=int, required=True,
            help='ID de la empresa'
        )
        parser.add_argument(
            '--json', default=None,
            help='Ruta al JSON (default: fixtures_prestamos.json en raíz del proyecto)'
        )
        parser.add_argument(
            '--user-id', type=int, default=None,
            help='ID del usuario admin para created_by y collector (default: primer ADMIN de la empresa)'
        )
        parser.add_argument(
            '--fecha-pago', default='2026-05-31',
            help='Fecha del pago histórico en formato YYYY-MM-DD (default: 2026-05-31)'
        )
        parser.add_argument(
            '--dry-run', action='store_true', default=False,
            help='Simular la carga sin guardar nada'
        )

    def handle(self, *args, **options):
        company_id  = options['company_id']
        dry_run     = options['dry_run']
        fecha_pago  = date.fromisoformat(options['fecha_pago'])
        base_dir    = os.path.dirname(os.path.abspath('manage.py'))
        path_json   = options['json'] or os.path.join(base_dir, 'fixtures_prestamos.json')

        if dry_run:
            self.stdout.write(self.style.WARNING('*** DRY-RUN: no se guardará nada ***\n'))

        # ── Empresa ───────────────────────────────────────────────────────────
        try:
            company = Company.objects.get(id=company_id)
        except Company.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'No existe empresa con ID={company_id}'))
            return
        self.stdout.write(f'Empresa : {self.style.SUCCESS(str(company))} (ID={company.id})')

        # ── Usuario admin ─────────────────────────────────────────────────────
        if options['user_id']:
            try:
                admin_user = User.objects.get(id=options['user_id'], company_id=company_id)
            except User.DoesNotExist:
                self.stderr.write(
                    self.style.ERROR(f"No existe usuario {options['user_id']} en la empresa {company_id}")
                )
                return
        else:
            admin_user = User.objects.filter(company_id=company_id, role='ADMIN').first()
            if not admin_user:
                self.stderr.write(
                    self.style.ERROR('No hay usuario ADMIN en esta empresa. Use --user-id <id>')
                )
                return
        self.stdout.write(f'Admin   : {admin_user}')

        # ── JSON ──────────────────────────────────────────────────────────────
        if not os.path.exists(path_json):
            self.stderr.write(self.style.ERROR(f'Archivo no encontrado: {path_json}'))
            return
        with open(path_json, encoding='utf-8') as f:
            datos = json.load(f)
        self.stdout.write(f'JSON    : {path_json}  ({len(datos)} préstamos)')

        # ── Tipos de préstamo disponibles ─────────────────────────────────────
        loan_types_qs = LoanType.objects.filter(company=company, is_active=True)
        loan_type_map = {lt.periodicity: lt for lt in loan_types_qs}
        self.stdout.write(f'LoanTypes disponibles: {list(loan_type_map.keys())}')

        # ── Clientes de la empresa ────────────────────────────────────────────
        all_clients = list(Client.objects.filter(company=company))
        self.stdout.write(f'Clientes en empresa : {len(all_clients)}\n')

        # Fecha-hora del pago histórico (medianoche Lima)
        paid_dt = timezone.make_aware(datetime.combine(fecha_pago, datetime.min.time()))

        # Contadores
        creados     = 0
        pagos_reg   = 0
        ya_existe   = 0
        sin_cliente = 0
        errores     = 0
        warnings    = []

        # ── Procesar cada préstamo ────────────────────────────────────────────
        for item in datos:
            nombre      = item['nombre']
            dni_excel   = item['dni']        # string 8 dígitos
            periodicity = item['periodicity']
            interes     = Decimal(str(item['interes']))
            cuotas      = item['cuotas']
            fecha       = date.fromisoformat(item['fecha'])
            monto       = Decimal(str(item['monto']))
            pago_raw    = item.get('pago')   # float o None

            # ── 1. Buscar cliente ─────────────────────────────────────────────
            client = None

            # Intento 1: DNI exacto (8 dígitos)
            client = next((c for c in all_clients if c.dni == dni_excel), None)

            # Intento 2: DNI sin ceros adelante
            if not client:
                d_int = dni_int(dni_excel)
                client = next(
                    (c for c in all_clients if dni_int(c.dni) == d_int),
                    None
                )

            # Intento 3: similitud de nombre (Jaccard ≥ 50%)
            if not client:
                best_score  = 0.0
                best_client = None
                for c in all_clients:
                    score = jaccard(nombre, c.full_name)
                    if score > best_score:
                        best_score  = score
                        best_client = c
                if best_score >= 0.50:
                    client = best_client
                    warnings.append(
                        f'  FUZZY {nombre} (DNI {dni_excel}) → {client.full_name} '
                        f'(DNI {client.dni}) score={best_score:.2f}'
                    )

            if not client:
                self.stdout.write(
                    self.style.ERROR(f'  SIN CLIENTE : {nombre} | DNI {dni_excel}')
                )
                sin_cliente += 1
                continue

            # ── 2. Calcular fechas ────────────────────────────────────────────
            start_date, end_date = calc_start_end(fecha, periodicity, cuotas)

            # ── 3. Idempotencia ───────────────────────────────────────────────
            existing = Loan.objects.filter(
                client=client,
                company=company,
                start_date=start_date,
                initial_amount=monto,
            ).first()
            if existing:
                self.stdout.write(
                    f'  ~ YA EXISTE préstamo #{existing.id} | {nombre} | omitido'
                )
                ya_existe += 1
                continue

            # ── 4. Tipo de préstamo ───────────────────────────────────────────
            loan_type = loan_type_map.get(periodicity)

            # ── 5. Crear en modo real o dry-run ──────────────────────────────
            if dry_run:
                pago_info = f'+ pago S/ {pago_raw}' if pago_raw else 'sin pago'
                self.stdout.write(
                    f'  [DRY] {nombre} | {periodicity} | S/ {monto} | '
                    f'{cuotas}c | {fecha} | {pago_info}'
                )
                creados += 1
                if pago_raw:
                    pagos_reg += 1
                continue

            try:
                with transaction.atomic():
                    # Crear préstamo
                    loan = Loan(
                        company=company,
                        client=client,
                        loan_type=loan_type,
                        initial_amount=monto,
                        interest_rate=interes,
                        number_of_installments=cuotas,
                        periodicity=periodicity,
                        start_date=start_date,
                        end_date=end_date,
                        status='ACTIVE',
                        created_by=admin_user,
                    )
                    loan.calculate_total_amount()
                    loan.save()

                    # Generar cuotas
                    _generate_installments(loan)

                    # Actualizar clasificación del cliente
                    client.update_classification()

                    self.stdout.write(
                        self.style.SUCCESS(
                            f'  + Préstamo #{loan.id:>4} | {client.full_name:<40} | '
                            f'{periodicity:<10} | S/ {monto:>8} | '
                            f'{cuotas:>3}c | {start_date} → {end_date}'
                        )
                    )
                    creados += 1

                    # Registrar pago si corresponde
                    if pago_raw:
                        pago_decimal = Decimal(str(round(pago_raw, 2)))

                        # Limitar al total del préstamo (evita saldo negativo)
                        pago_final = min(pago_decimal, loan.total_amount)
                        if pago_decimal > loan.total_amount:
                            warnings.append(
                                f'  PAGO AJUSTADO {nombre}: {pago_decimal} > '
                                f'total {loan.total_amount}, registrado {pago_final}'
                            )

                        payment = Payment(
                            company=company,
                            loan=loan,
                            client=client,
                            amount=pago_final,
                            payment_date=paid_dt,
                            payment_method='CASH',
                            collector=admin_user,
                            status='COMPLETED',
                            observations='Carga histórica desde sistema anterior',
                        )
                        payment.save()  # distribuye automáticamente en cuotas

                        self.stdout.write(
                            f'    → Pago #{payment.id} S/ {pago_final} — {fecha_pago}'
                        )
                        pagos_reg += 1

            except Exception as exc:
                self.stdout.write(
                    self.style.ERROR(f'  ERROR {nombre} (DNI {dni_excel}): {exc}')
                )
                errores += 1

        # ── Advertencias acumuladas ────────────────────────────────────────────
        if warnings:
            self.stdout.write('\n' + self.style.WARNING('ADVERTENCIAS:'))
            for w in warnings:
                self.stdout.write(self.style.WARNING(w))

        # ── Resumen ────────────────────────────────────────────────────────────
        sep = '=' * 65
        self.stdout.write(f'\n{sep}')
        self.stdout.write(self.style.SUCCESS(
            f'PRÉSTAMOS : {creados:>3} creados  | '
            f'{ya_existe:>3} ya existían | '
            f'{sin_cliente:>3} sin cliente | '
            f'{errores:>3} errores'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'PAGOS     : {pagos_reg:>3} registrados  (fecha: {fecha_pago})'
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING('\n*** Dry-run: ningún cambio fue guardado ***'))
        self.stdout.write(sep)
