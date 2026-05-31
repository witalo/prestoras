"""
Comando Django para cargar zonas y clientes desde los JSON generados.

Uso en produccion:
  python manage.py cargar_desde_json --company-id 1
  python manage.py cargar_desde_json --company-id 1 --dry-run
  python manage.py cargar_desde_json --company-id 1 --zonas /ruta/z.json --clientes /ruta/c.json

IDEMPOTENTE: se puede correr varias veces sin duplicar.

Deteccion de zonas duplicadas (3 capas):
  1. Exact match por nombre
  2. Slug match (ignora puntos, espacios, mayus)  ->  "JLBR" == "J.L.B.R."
  3. Normalizar nombre existente + slug            ->  "M. MELGAR" == "MARIANO MELGAR"
"""
import json
import os
import re
import unicodedata
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.companies.models import Company
from apps.zones.models import Zone
from apps.clients.models import Client


# ─── Mapa de abreviaturas / variantes conocidas ───────────────────────────────
# Se aplica TANTO al Excel (generacion de JSON) COMO al cargar en produccion
# para reconocer zonas existentes con nombre abreviado.
ZONA_NORMALIZAR = {
    # Mariano Melgar
    'M. MELGAR':                  'MARIANO MELGAR',
    'M.MELGAR':                   'MARIANO MELGAR',
    # JLBR - Jose Luis Bustamante y Rivero
    'J.L.B.R.':                   'JLBR',
    'J.L.BR':                     'JLBR',
    'J.L.BYR.':                   'JLBR',
    'JLBYR(PARALELO':             'JLBR (PARALELO)',
    'JLBR(SEMANAL)':              'JLBR (SEMANAL)',
    # Cercado variantes
    'CERCAD PARTE 2':             'CERCADO PARTE 2',
    'CERCADO PARTE3':             'CERCADO PARTE 3',
    'CERCADO( SEMANAL)':          'CERCADO (SEMANAL)',
    'CERCADO(SEMANAL)':           'CERCADO (SEMANAL)',
    'CERCADO(PARALELO)':          'CERCADO (PARALELO)',
    # Jacobo Hunter
    'HANTER':                     'JACOBO HUNTER',
    'JACOBO HANTER':              'JACOBO HUNTER',
    # Miraflores
    'MIRAFLORES(PARALELO)':       'MIRAFLORES (PARALELO)',
    # Socabaya (typo comun: Socobaya)
    'SOCOBAYA':                   'SOCABAYA',
    'SOCOBAYA (PARALELO)':        'SOCABAYA (PARALELO)',
    'SOCOBAYA (SEMANAL)':         'SOCABAYA (SEMANAL)',
    'SOCABAYA(SEMANAL)':          'SOCABAYA (SEMANAL)',
    # Paucarpata
    'PAUCARPATA(PARALELO)':       'PAUCARPATA (PARALELO)',
    'PAUCARPATA(SEMANAL)':        'PAUCARPATA (SEMANAL)',
    # Otros
    'CONO NORTE(PARALELO)':       'CONO NORTE (PARALELO)',
    'ASA(PARALELO)':              'ASA (PARALELO)',
    'MARIANO MELGAR (PARALELO)':  'MARIANO MELGAR (PARALELO)',
    'MARIANO MELGAR (SEMANAL)':   'MARIANO MELGAR (SEMANAL)',
    'SABANDIA (SEMANAL)':         'SABANDIA (SEMANAL)',
}


def normalizar_zona(nombre):
    """Aplica el mapa de abreviaturas/variantes para obtener el nombre canonico."""
    if not nombre:
        return nombre
    n = str(nombre).strip()
    return ZONA_NORMALIZAR.get(n, n)


def slug_zona(nombre):
    """
    Convierte un nombre a slug solo-alfanumerico para comparacion fuzzy.
    Elimina tildes, puntos, espacios, parentesis, guiones, etc.

      'J.L.B.R.'          -> 'JLBR'
      'JLBR'              -> 'JLBR'
      'MARIANO MELGAR'    -> 'MARIANOMELGAR'
      'M. MELGAR'         -> 'MMELGAR'
      'CERCADO (SEMANAL)' -> 'CERCADOSEMANAL'
      'CERCADO(SEMANAL)'  -> 'CERCADOSEMANAL'
    """
    if not nombre:
        return ''
    n = unicodedata.normalize('NFD', str(nombre))
    n = ''.join(c for c in n if unicodedata.category(c) != 'Mn')
    n = re.sub(r'[^A-Za-z0-9]', '', n)
    return n.upper()


def construir_zona_map(company):
    """
    Construye el mapa slug -> Zone de todas las zonas existentes en la empresa.

    Para cada zona existente indexa TRES slugs:
      1. slug del nombre original       ('M. MELGAR'       -> 'MMELGAR')
      2. slug del nombre normalizado    ('MARIANO MELGAR'  -> 'MARIANOMELGAR')
      3. slug del nombre original en DB aplicando normalizacion inversa
         (por si en produccion esta guardada con abreviatura)

    Asi 'MARIANO MELGAR' del JSON encontrara la zona guardada como 'M. MELGAR'.
    """
    zona_map = {}
    for z in Zone.objects.filter(company=company):
        # Slug del nombre tal como esta en DB
        slug_original = slug_zona(z.name)
        zona_map[slug_original] = z

        # Slug del nombre normalizado (aplicando mapa de abreviaturas)
        nombre_normalizado = normalizar_zona(z.name)
        slug_norm = slug_zona(nombre_normalizado)
        if slug_norm != slug_original:
            zona_map[slug_norm] = z   # apunta a la misma instancia

    return zona_map


# ─── Comando ─────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Carga zonas y clientes desde fixtures_zonas.json y fixtures_clientes.json'

    def add_arguments(self, parser):
        parser.add_argument(
            '--company-id', type=int, required=True,
            help='ID de la empresa donde se cargaran los datos'
        )
        parser.add_argument(
            '--zonas', default=None,
            help='Ruta al JSON de zonas (por defecto: fixtures_zonas.json)'
        )
        parser.add_argument(
            '--clientes', default=None,
            help='Ruta al JSON de clientes (por defecto: fixtures_clientes.json)'
        )
        parser.add_argument(
            '--dry-run', action='store_true', default=False,
            help='Simular la carga sin guardar nada'
        )

    def handle(self, *args, **options):
        company_id = options['company_id']
        dry_run    = options['dry_run']

        base_dir      = os.path.dirname(os.path.abspath('manage.py'))
        path_zonas    = options['zonas']    or os.path.join(base_dir, 'fixtures_zonas.json')
        path_clientes = options['clientes'] or os.path.join(base_dir, 'fixtures_clientes.json')

        if dry_run:
            self.stdout.write(self.style.WARNING('*** DRY-RUN: no se guardara nada ***\n'))

        # ── Empresa ──────────────────────────────────────────────────────────
        try:
            company = Company.objects.get(id=company_id)
        except Company.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'No existe empresa con ID={company_id}'))
            return

        self.stdout.write(
            f'Empresa: {self.style.SUCCESS(company.commercial_name or company.legal_name)} '
            f'(ID={company.id})\n'
        )

        # ── Leer JSONs ────────────────────────────────────────────────────────
        for path, label in [(path_zonas, 'zonas'), (path_clientes, 'clientes')]:
            if not os.path.exists(path):
                self.stderr.write(self.style.ERROR(f'Archivo no encontrado: {path}'))
                self.stderr.write(f'Indica la ruta con --{label} /ruta/archivo.json')
                return

        with open(path_zonas,    encoding='utf-8') as f:
            datos_zonas = json.load(f)
        with open(path_clientes, encoding='utf-8') as f:
            datos_clientes = json.load(f)

        self.stdout.write(f'Zonas en JSON:    {len(datos_zonas)}')
        self.stdout.write(f'Clientes en JSON: {len(datos_clientes)}\n')

        # ────────────────────────────────────────────────────────────────────
        # PASO 1 — Zonas
        # ────────────────────────────────────────────────────────────────────
        self.stdout.write('Cargando zonas...')

        # Mapa multi-slug de zonas ya existentes en produccion
        zona_map = construir_zona_map(company)
        self.stdout.write(f'  Zonas ya en DB: {Zone.objects.filter(company=company).count()}\n')

        zonas_creadas    = 0
        zonas_existentes = 0
        zona_nombre_map  = {}   # nombre_json -> Zone instance

        with transaction.atomic():
            for dato in datos_zonas:
                nombre = dato['name'].strip()
                status = dato.get('status', 'ACTIVE')

                # Buscar por slug del nombre que viene en el JSON
                slug = slug_zona(nombre)
                zona_existente = zona_map.get(slug)

                if zona_existente:
                    zonas_existentes += 1
                    zona_nombre_map[nombre] = zona_existente
                    if zona_existente.name != nombre:
                        # Encontro con nombre distinto (variante)
                        self.stdout.write(
                            f'  ~ Zona encontrada [{zona_existente.name}] '
                            f'<- JSON [{nombre}]'
                        )
                    else:
                        self.stdout.write(f'  ~ Zona ya existe: {nombre}')
                else:
                    if dry_run:
                        zonas_creadas += 1
                        zona_nombre_map[nombre] = None
                        self.stdout.write(f'  + Zona nueva (dry): {nombre}')
                    else:
                        nueva = Zone.objects.create(
                            company=company,
                            name=nombre,
                            status=status
                        )
                        # Indexar la nueva zona con sus slugs
                        zona_map[slug]                 = nueva
                        zona_map[slug_zona(normalizar_zona(nombre))] = nueva
                        zona_nombre_map[nombre] = nueva
                        zonas_creadas += 1
                        self.stdout.write(
                            f'  {self.style.SUCCESS("+")} Zona creada: {nombre}'
                        )

        # ────────────────────────────────────────────────────────────────────
        # PASO 2 — Clientes
        # ────────────────────────────────────────────────────────────────────
        self.stdout.write('\nCargando clientes...')
        clientes_creados    = 0
        clientes_existentes = 0
        clientes_error      = 0

        with transaction.atomic():
            for dato in datos_clientes:
                dni        = str(dato['dni']).zfill(8)
                first_name = dato.get('first_name') or 'SIN NOMBRE'
                last_name  = dato.get('last_name')  or 'SIN APELLIDO'
                phone      = dato.get('phone')
                email      = dato.get('email')
                address    = dato.get('home_address')
                zona_name  = dato.get('zone_name')
                classif    = dato.get('classification', 'REGULAR')
                is_active  = dato.get('is_active', True)

                # Resolver zona: primero por nombre exacto del JSON,
                # luego por slug (para absorber variantes en produccion)
                zona = None
                if zona_name:
                    zona = zona_nombre_map.get(zona_name)
                    if zona is None:
                        slug = slug_zona(zona_name)
                        zona = zona_map.get(slug)
                        if zona is None:
                            # Ultimo intento: normalizar el nombre y buscar slug
                            slug_norm = slug_zona(normalizar_zona(zona_name))
                            zona = zona_map.get(slug_norm)

                if dry_run:
                    if Client.objects.filter(dni=dni).exists():
                        clientes_existentes += 1
                    else:
                        clientes_creados += 1
                    continue

                try:
                    _, created = Client.objects.get_or_create(
                        dni=dni,
                        defaults={
                            'company':        company,
                            'first_name':     first_name,
                            'last_name':      last_name,
                            'phone':          phone,
                            'email':          email,
                            'home_address':   address,
                            'zone':           zona,
                            'classification': classif,
                            'is_active':      is_active,
                        }
                    )
                    if created:
                        clientes_creados += 1
                    else:
                        clientes_existentes += 1

                except Exception as e:
                    clientes_error += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f'  ERROR DNI {dni} ({first_name} {last_name}): {e}'
                        )
                    )

        # ── Resumen ──────────────────────────────────────────────────────────
        sep = '=' * 55
        self.stdout.write(f'\n{sep}')
        self.stdout.write(self.style.SUCCESS(
            f'ZONAS:    {zonas_creadas:>3} creadas  |  {zonas_existentes:>3} ya existian'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'CLIENTES: {clientes_creados:>3} creados  |  {clientes_existentes:>3} ya existian'
            + (f'  |  {clientes_error} errores' if clientes_error else '')
        ))
        if dry_run:
            self.stdout.write(
                self.style.WARNING('\n*** Dry-run: ningun cambio fue guardado ***')
            )
        self.stdout.write(sep)
