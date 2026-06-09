#!/usr/bin/env python
"""
Genera fixtures_prestamos.json a partir de prestamos_clientes.xlsx.

Ejecutar desde el directorio raiz del proyecto:
    python generar_prestamos_json.py
"""
import json
import openpyxl
from datetime import date

TIPO_A_PERIODICIDAD = {
    'DIARIO':     'DAILY',
    'SEMANAL':    'WEEKLY',
    'QUINCENAL':  'BIWEEKLY',
    'MENSUAL':    'MONTHLY',
    'TRIMESTRL':  'QUARTERLY',
    'TRIMESTRAL': 'QUARTERLY',
}

def main():
    wb = openpyxl.load_workbook('prestamos_clientes.xlsx')
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    print(f"Cabecera : {rows[0]}")
    print(f"Filas    : {len(rows) - 1}\n")

    prestamos = []
    omitidos  = 0

    for i, row in enumerate(rows[1:], start=2):
        nombre, dni, telefono, direccion, tipo, interes, cuotas, fecha, monto, pago = row

        if not nombre or not monto:
            omitidos += 1
            continue

        # DNI: convertir a entero y zero-pad 8 dígitos
        try:
            dni_str = str(int(float(str(dni)))).zfill(8)
        except (ValueError, TypeError):
            dni_str = str(dni).strip().zfill(8)

        # Fecha como ISO string
        if fecha is None:
            print(f"  OMITIDO fila {i}: {nombre} — sin fecha")
            omitidos += 1
            continue
        fecha_str = fecha.date().isoformat() if hasattr(fecha, 'date') else str(fecha)[:10]

        # Periodicidad
        tipo_upper = str(tipo).strip().upper()
        periodicity = TIPO_A_PERIODICIDAD.get(tipo_upper)
        if periodicity is None:
            print(f"  ADVERTENCIA fila {i}: tipo '{tipo}' desconocido, usando DAILY")
            periodicity = 'DAILY'

        # Pago: None si es None/vacío/0
        pago_val = None
        if pago is not None:
            try:
                pago_f = float(pago)
                if pago_f > 0:
                    pago_val = round(pago_f, 2)
            except (ValueError, TypeError):
                pass

        prestamos.append({
            "nombre":      str(nombre).strip(),
            "dni":         dni_str,
            "tipo":        str(tipo).strip(),
            "periodicity": periodicity,
            "interes":     float(interes) if interes is not None else 0.0,
            "cuotas":      int(cuotas)    if cuotas  is not None else 1,
            "fecha":       fecha_str,
            "monto":       round(float(monto), 2),
            "pago":        pago_val,
        })

    output = 'fixtures_prestamos.json'
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(prestamos, f, ensure_ascii=False, indent=2)

    con_pago  = sum(1 for p in prestamos if p['pago'])
    sin_pago  = sum(1 for p in prestamos if not p['pago'])
    print(f"Archivo  : {output}")
    print(f"Préstamos: {len(prestamos)}")
    print(f"Con pago : {con_pago}")
    print(f"Sin pago : {sin_pago}")
    print(f"Omitidos : {omitidos}")


if __name__ == '__main__':
    main()
