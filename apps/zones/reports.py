"""
Reportes de la app Zones (PDF y Excel).
Cada vista requiere JWT en header: Authorization: Bearer <token>.
"""
import io
import os
from decimal import Decimal
from html import escape

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

from prestoras.utils_auth import get_user_from_jwt
from apps.zones.models import Zone
from apps.loans.models import Loan


def _get_logo_path(company):
    """Ruta del logo de la empresa si existe en disco."""
    if not company or not company.logo:
        return None
    try:
        path = getattr(company.logo, 'path', None)
        if path and os.path.isfile(path):
            return path
        name = getattr(company.logo, 'name', None)
        if name:
            full = os.path.join(settings.MEDIA_ROOT, name)
            if os.path.isfile(full):
                return full
    except (ValueError, OSError):
        pass
    return None


@csrf_exempt
@require_GET
def zone_loans_pdf(request, zone_id: int):
    """
    GET /api/zones/reports/<zone_id>/prestamos-pdf/
    PDF: Ficha de préstamos por zona (solo clientes con deuda activa).
    """
    if not get_user_from_jwt(request):
        return JsonResponse({'error': 'No autorizado'}, status=401)

    try:
        zone = Zone.objects.select_related('company').get(pk=zone_id)
    except Zone.DoesNotExist:
        return JsonResponse({'error': 'Zona no encontrada'}, status=404)

    company = zone.company
    company_name = (company.commercial_name or company.legal_name or 'Empresa').strip()
    company_ruc = company.ruc or ''
    logo_path = _get_logo_path(company)
    now_local = timezone.localtime(timezone.now())
    report_date = now_local.strftime('%d/%m/%Y %H:%M')

    loans = (
        Loan.objects
        .filter(
            client__zone_id=zone_id,
            client__is_active=True,
            status__in=['ACTIVE', 'DEFAULTING'],
            pending_amount__gt=0
        )
        .select_related('client', 'loan_type')
        .order_by('client__last_name', 'client__first_name', 'start_date')
    )

    # Márgenes reducidos (top/bottom) para que el contenido no quede bajo y haya menos blanco
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=8 * mm,
        bottomMargin=10 * mm
    )
    usable_width_pt = 538
    elements = []
    styles = getSampleStyleSheet()
    small_normal = ParagraphStyle('SmallNormal', parent=styles['Normal'], fontSize=5, leading=6)
    table_header_style = ParagraphStyle(
        'TableHeader', parent=styles['Normal'], fontSize=5, leading=6,
        textColor=colors.white, alignment=TA_CENTER,
    )
    table_header_right_style = ParagraphStyle(
        'TableHeaderRight', parent=styles['Normal'], fontSize=5, leading=6,
        textColor=colors.white, alignment=TA_RIGHT, spaceAfter=0,
    )
    left_style = ParagraphStyle(
        'Left', parent=styles['Normal'], fontSize=6, leading=7,
        alignment=TA_LEFT, textColor=colors.HexColor('#1565C0'), spaceAfter=0,
    )
    left_small = ParagraphStyle(
        'LeftSmall', parent=styles['Normal'], fontSize=5, leading=6,
        alignment=TA_LEFT, textColor=colors.HexColor('#555555'), spaceAfter=0,
    )
    center_style = ParagraphStyle(
        'Center', parent=styles['Normal'], fontSize=6, leading=7,
        alignment=TA_CENTER, textColor=colors.HexColor('#1a1a1a'), spaceAfter=0,
    )
    center_small = ParagraphStyle(
        'CenterSmall', parent=styles['Normal'], fontSize=5, leading=6,
        alignment=TA_CENTER, textColor=colors.HexColor('#555555'), spaceAfter=0,
    )
    # Estilos detalle: leading = fontSize para bajar altura de fila; alineación en el Paragraph
    cell_body = ParagraphStyle(
        'CellBody', parent=styles['Normal'], fontSize=4, leading=4,
        spaceAfter=0, spaceBefore=0, textColor=colors.HexColor('#1a1a1a'), alignment=TA_LEFT,
    )
    cell_body_center = ParagraphStyle(
        'CellBodyCenter', parent=styles['Normal'], fontSize=4, leading=4,
        spaceAfter=0, spaceBefore=0, textColor=colors.HexColor('#1a1a1a'), alignment=TA_CENTER,
    )
    cell_body_right = ParagraphStyle(
        'CellBodyRight', parent=styles['Normal'], fontSize=4, leading=4,
        spaceAfter=0, spaceBefore=0, textColor=colors.HexColor('#1a1a1a'), alignment=TA_RIGHT,
    )

    # Encabezado 3 columnas: (1) nombre empresa + RUC | (2) ficha + zona + fecha | (3) logo
    col1 = [Paragraph(f'<b>%s</b>' % company_name.upper(), left_style)]
    if company_ruc:
        col1.append(Paragraph(f'RUC: {company_ruc}', left_small))
    col2 = [
        Paragraph('<b>Ficha de préstamos por zona</b>', center_style),
        Paragraph(zone.name, center_small),
        Paragraph(report_date, center_small),
    ]
    col3 = []
    if logo_path:
        try:
            col3 = [RLImage(logo_path, width=32, height=32)]
        except Exception:
            col3 = [Spacer(1, 1)]
    if not col3:
        col3 = [Spacer(1, 1)]
    # 3 columnas en partes iguales (538/3) y tabla mismo ancho: todo alineado a la misma recta
    header_table = Table(
        [[col1, col2, col3]],
        colWidths=[170, 198, 170]  # partes iguales, suma = 538
    )
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0))

    # Cabeceras: #, DNI, Cliente, Telefono, Fecha, Solicitado, Total, Pago, Saldo, Tipo, Estado
    headers = ['#', 'DNI', 'Cliente', 'Telefono', 'Fecha', 'Solicitado', 'Total', 'Pago', 'Saldo', 'Tipo', 'Estado']
    col_widths = [18, 40, 175, 35, 35, 42, 42, 42, 42, 35, 32]  # suma = 538
    data_rows = [[Paragraph('<b>%s</b>' % h, table_header_style) for h in headers]]
    total_solicitado = Decimal('0.00')
    total_monto_mas_int = Decimal('0.00')
    total_pagado = Decimal('0.00')
    total_saldo = Decimal('0.00')
    n = 0

    for loan in loans:
        n += 1
        client = loan.client
        full_name = f"{client.first_name} {client.last_name}".strip()[:20]
        phone = (client.phone or '-')[:8]
        f_prestamo = loan.start_date.strftime('%d/%m/%y')
        tipo = loan.get_periodicity_display() if hasattr(loan, 'get_periodicity_display') else (
            {'DAILY': 'D', 'WEEKLY': 'S', 'BIWEEKLY': 'Q', 'MONTHLY': 'M',
             'QUARTERLY': 'T', 'CUSTOM': '-'}.get(loan.periodicity, '-')
        )
        estado = client.get_classification_display() if hasattr(client, 'get_classification_display') else (
            {'PUNCTUAL': 'B', 'REGULAR': 'R', 'DEFAULTING': 'M',
             'SEVERELY_DEFAULTING': 'M-'}.get(client.classification, 'R')
        )
        total_solicitado += loan.initial_amount
        total_monto_mas_int += loan.total_amount
        total_pagado += loan.paid_amount
        total_saldo += loan.pending_amount
        # # y Fecha centro; montos (Solicitado, Total, Pago, Saldo) derecha; resto izquierda/centro
        row = [
            Paragraph(escape(str(n)), cell_body_center),
            Paragraph(escape(client.dni or '-'), cell_body),
            Paragraph(escape(full_name), cell_body),
            Paragraph(escape(phone), cell_body),
            Paragraph(escape(f_prestamo), cell_body_center),
            Paragraph(escape('%.2f' % loan.initial_amount), cell_body_right),
            Paragraph(escape('%.2f' % loan.total_amount), cell_body_right),
            Paragraph(escape('%.2f' % loan.paid_amount), cell_body_right),
            Paragraph(escape('%.2f' % loan.pending_amount), cell_body_right),
            Paragraph(escape(tipo[:10] if isinstance(tipo, str) else str(tipo)[:10]), cell_body_center),
            Paragraph(escape(estado[:10] if isinstance(estado, str) else str(estado)[:10]), cell_body_center),
        ]
        data_rows.append(row)

    if not data_rows[1:]:
        elements.append(Paragraph('No hay clientes con deuda activa en esta zona.', small_normal))
    else:
        t = Table(data_rows, colWidths=col_widths, repeatRows=1)
        # Cabecera (fila 0): azul; detalle (fila 1+): padding 0 para bajar altura de fila
        table_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1565C0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 5),
            ('TOPPADDING', (0, 0), (-1, 0), 3),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (1, 0), (4, -1), 'LEFT'),
            ('ALIGN', (5, 0), (8, -1), 'RIGHT'),
            ('ALIGN', (9, 0), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, 0), 5),
            ('GRID', (0, 0), (-1, -1), 0.2, colors.HexColor('#B0BEC5')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 1), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 2),
        ]
        for i, loan in enumerate(loans, start=1):
            if loan.paid_amount <= 0:
                table_style.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#FFEBEE')))
                table_style.append(('TEXTCOLOR', (0, i), (-1, i), colors.HexColor('#C62828')))
            elif loan.client.classification in ('DEFAULTING', 'SEVERELY_DEFAULTING'):
                table_style.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#FFF8E1')))
                table_style.append(('TEXTCOLOR', (0, i), (-1, i), colors.HexColor('#E65100')))
            else:
                table_style.append(
                    ('BACKGROUND', (0, i), (-1, i), colors.HexColor('#FAFAFA') if i % 2 == 0 else colors.white))
        t.setStyle(TableStyle(table_style))
        elements.append(t)
        elements.append(Spacer(1, 2))
        # Montos con alineación derecha para quedar en la misma recta que las columnas numéricas
        total_row = [
            Paragraph('', table_header_style),
            Paragraph('', table_header_style),
            Paragraph('TOTALES', table_header_style),
            Paragraph('', table_header_style),
            Paragraph('', table_header_style),
            Paragraph('%.2f' % total_solicitado, table_header_right_style),
            Paragraph('%.2f' % total_monto_mas_int, table_header_right_style),
            Paragraph('%.2f' % total_pagado, table_header_right_style),
            Paragraph('%.2f' % total_saldo, table_header_right_style),
            Paragraph('', table_header_style),
            Paragraph('', table_header_style),
        ]
        t_total = Table([total_row], colWidths=col_widths)
        t_total.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#1565C0')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('ALIGN', (5, 0), (8, -1), 'RIGHT'),
            ('ALIGN', (0, 0), (4, -1), 'LEFT'),
            ('ALIGN', (9, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.2, colors.HexColor('#1565C0')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(t_total)
        foot_style = ParagraphStyle('Foot', parent=styles['Normal'], fontSize=5, leading=6, alignment=TA_LEFT,
                                    spaceAfter=0, leftIndent=0, rightIndent=0)
        elements.append(
            Paragraph(f'<b>Total deuda:</b> S/ %.2f  |  <b>Préstamos:</b> %d' % (total_saldo, n), foot_style))

    def add_footer(canvas, doc):
        center_x = A4[0] / 2
        center_y = A4[1] / 2
        canvas.saveState()
        # Marca de agua: logo si existe, sino texto
        if logo_path:
            try:
                canvas.translate(center_x, center_y)
                canvas.rotate(45)
                w, h = 180, 180  # tamaño marca de agua (más grande para que se vea mejor)
                canvas.setFillAlpha(0.18)
                canvas.drawImage(logo_path, -w / 2, -h / 2, width=w, height=h)
            except Exception:
                canvas.rotate(-45)
                canvas.translate(-center_x, -center_y)
                canvas.setFillAlpha(1)
                canvas.setFillColor(colors.HexColor('#e8e8e8'))
                canvas.setFont('Helvetica', 24)
                canvas.translate(center_x, center_y)
                canvas.rotate(45)
                canvas.drawCentredString(0, 0, company_name[:20])
        else:
            canvas.setFillColor(colors.HexColor('#e8e8e8'))
            canvas.setFont('Helvetica', 24)
            canvas.translate(center_x, center_y)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, company_name[:20])
        canvas.restoreState()
        # Pie de página: centrado abajo, visible (dentro del margen inferior)
        canvas.saveState()
        footer_y = 12 * mm
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.HexColor('#555555'))
        canvas.drawCentredString(center_x, footer_y, f'{company_name} — Ficha zona — {report_date}')
        canvas.restoreState()

    doc.build(elements, onFirstPage=add_footer, onLaterPages=add_footer)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    filename = f'ficha_prestamos_zona_{zone.name.replace(" ", "_")}_{now_local.strftime("%Y%m%d_%H%M")}.pdf'
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


@csrf_exempt
@require_GET
def zone_client_pdf(request, zone_id: int):
    """
    GET /api/zones/reports/<zone_id>/clientes-pdf/
    PDF: Ficha de préstamos por zona con columnas DNI, Cliente, Fecha préstamo, Interés %, Monto+Interés,
    y 14 columnas para dos semanas (Lun, Mar, ... Dom x2). Encabezado: título + fecha/hora + empresa y logo.
    """
    if not get_user_from_jwt(request):
        return JsonResponse({'error': 'No autorizado'}, status=401)

    try:
        zone = Zone.objects.select_related('company').get(pk=zone_id)
    except Zone.DoesNotExist:
        return JsonResponse({'error': 'Zona no encontrada'}, status=404)

    company = zone.company
    company_name = (company.commercial_name or company.legal_name or 'Empresa').strip()
    company_ruc = company.ruc or ''
    logo_path = _get_logo_path(company)
    now_local = timezone.localtime(timezone.now())
    report_date = now_local.strftime('%d/%m/%Y %H:%M')

    loans = (
        Loan.objects
        .filter(
            client__zone_id=zone_id,
            client__is_active=True,
            status__in=['ACTIVE', 'DEFAULTING'],
            pending_amount__gt=0
        )
        .select_related('client', 'loan_type')
        .order_by('client__last_name', 'client__first_name', 'start_date')
    )

    buffer = io.BytesIO()
    # Márgenes reducidos (sobre todo top) para que el contenido no quede bajo en la hoja
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=8 * mm,
        bottomMargin=10 * mm
    )
    usable_width_pt = 538
    elements = []
    styles = getSampleStyleSheet()
    small_normal = ParagraphStyle('SmallNormal', parent=styles['Normal'], fontSize=5, leading=6)
    table_header_style = ParagraphStyle(
        'TableHeader', parent=styles['Normal'], fontSize=5, leading=6,
        textColor=colors.white, alignment=TA_CENTER,
    )
    table_header_right_style = ParagraphStyle(
        'TableHeaderRight', parent=styles['Normal'], fontSize=5, leading=6,
        textColor=colors.white, alignment=TA_RIGHT, spaceAfter=0,
    )
    left_style = ParagraphStyle(
        'Left', parent=styles['Normal'], fontSize=6, leading=7,
        alignment=TA_LEFT, textColor=colors.HexColor('#1565C0'), spaceAfter=0,
    )
    left_small = ParagraphStyle(
        'LeftSmall', parent=styles['Normal'], fontSize=5, leading=6,
        alignment=TA_LEFT, textColor=colors.HexColor('#555555'), spaceAfter=0,
    )
    center_style = ParagraphStyle(
        'Center', parent=styles['Normal'], fontSize=6, leading=7,
        alignment=TA_CENTER, textColor=colors.HexColor('#1a1a1a'), spaceAfter=0,
    )
    center_small = ParagraphStyle(
        'CenterSmall', parent=styles['Normal'], fontSize=5, leading=6,
        alignment=TA_CENTER, textColor=colors.HexColor('#555555'), spaceAfter=0,
    )
    # Estilos para celdas del detalle: leading = fontSize para reducir altura de fila.
    # La alineación va en el Paragraph (TableStyle ALIGN no alinea el texto dentro del Paragraph).
    cell_body = ParagraphStyle(
        'CellBody', parent=styles['Normal'], fontSize=4, leading=4,
        spaceAfter=0, spaceBefore=0, textColor=colors.HexColor('#1a1a1a'), alignment=TA_LEFT,
    )
    cell_body_center = ParagraphStyle(
        'CellBodyCenter', parent=styles['Normal'], fontSize=4, leading=4,
        spaceAfter=0, spaceBefore=0, textColor=colors.HexColor('#1a1a1a'), alignment=TA_CENTER,
    )
    cell_body_right = ParagraphStyle(
        'CellBodyRight', parent=styles['Normal'], fontSize=4, leading=4,
        spaceAfter=0, spaceBefore=0, textColor=colors.HexColor('#1a1a1a'), alignment=TA_RIGHT,
    )

    # Encabezado: (1) empresa + RUC | (2) Ficha de préstamos + zona + fecha/hora | (3) logo
    col1 = [Paragraph(f'<b>%s</b>' % company_name.upper(), left_style)]
    if company_ruc:
        col1.append(Paragraph(f'RUC: {company_ruc}', left_small))
    col2 = [
        Paragraph('<b>FICHA DE PRÉSTAMOS</b>', center_style),
        Paragraph(zone.name, center_small),
        Paragraph(report_date, center_small),
    ]
    col3 = []
    if logo_path:
        try:
            col3 = [RLImage(logo_path, width=32, height=32)]
        except Exception:
            col3 = [Spacer(1, 1)]
    if not col3:
        col3 = [Spacer(1, 1)]
    header_table = Table(
        [[col1, col2, col3]],
        colWidths=[170, 198, 170]
    )
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0))

    # Columnas: N° (correlativo), DNI, Cliente, F. Préstamo, Int. %, Monto+Int., 12 días (Lun-Sáb x2, sin domingos)
    day_headers = [
        'Lun1', 'Mar1', 'Mié1', 'Jue1', 'Vie1', 'Sáb1',
        'Lun2', 'Mar2', 'Mié2', 'Jue2', 'Vie2', 'Sáb2',
    ]
    headers = ['N°', 'DNI', 'Cliente', 'F. Préstamo', 'Int. %', 'Monto+Int.'] + day_headers
    col_widths = [15, 34, 105, 38, 32, 38] + [23] * 12  # suma = 538
    data_rows = [[Paragraph('<b>%s</b>' % h, table_header_style) for h in headers]]

    for n, loan in enumerate(loans, start=1):
        client = loan.client
        full_name = f"{client.first_name} {client.last_name}".strip()[:18]
        f_prestamo = loan.start_date.strftime('%d/%m/%y')
        interest_pct = float(loan.interest_rate) if loan.interest_rate is not None else 0
        # N° y Fecha al centro; montos (Int. %, Monto+Int.) a la derecha; resto a la izquierda
        row = [
            Paragraph(escape(str(n)), cell_body_center),
            Paragraph(escape(client.dni or '-'), cell_body),
            Paragraph(escape(full_name), cell_body),
            Paragraph(escape(f_prestamo), cell_body_center),
            Paragraph(escape('%.1f' % interest_pct), cell_body_right),
            Paragraph(escape('%.2f' % (loan.total_amount or 0)), cell_body_right),
        ]
        for _ in range(12):
            row.append(Paragraph('', cell_body_center))
        data_rows.append(row)

    if not data_rows[1:]:
        elements.append(Paragraph('No hay clientes con deuda activa en esta zona.', small_normal))
    else:
        t = Table(data_rows, colWidths=col_widths, repeatRows=1)
        # TableStyle: (comando, (col_ini, fila_ini), (col_fin, fila_fin), valor)
        # (-1 = última columna/fila). Fila 0 = cabecera, fila 1+ = detalle.
        table_style = [
            # --- Cabecera (fila 0): fondo azul, texto blanco, negrita ---
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1565C0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 5),
            ('TOPPADDING', (0, 0), (-1, 0), 3),      # espacio arriba de la cabecera
            ('BOTTOMPADDING', (0, 0), (-1, 0), 2),   # espacio abajo de la cabecera
            # --- Todas las celdas: márgenes laterales ---
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            # --- Alineación por columna (todas las filas) ---
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),   # N°
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),   # DNI
            ('ALIGN', (2, 0), (2, -1), 'LEFT'),     # Cliente (nombres)
            ('ALIGN', (3, 0), (3, -1), 'CENTER'),   # F. Préstamo (fecha)
            ('ALIGN', (4, 0), (5, -1), 'RIGHT'),    # Int. % y Monto+Int.
            ('ALIGN', (6, 0), (-1, -1), 'CENTER'),  # columnas de días
            # --- Tamaño de fuente: cabecera 5pt, detalle 4pt (reduce altura de línea = menos alto arriba y abajo) ---
            ('FONTSIZE', (0, 0), (-1, 0), 5),
            ('FONTSIZE', (0, 1), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.2, colors.HexColor('#B0BEC5')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            # --- Solo detalle (fila 1 en adelante): sin espacio arriba ni abajo para bajar altura de fila ---
            ('TOPPADDING', (0, 1), (-1, -1), 2),    # quita espacio superior en cada fila de datos
            ('BOTTOMPADDING', (0, 1), (-1, -1), 2), # quita espacio inferior en cada fila de datos
        ]
        for i, loan in enumerate(loans, start=1):
            if loan.paid_amount <= 0:
                table_style.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#FFEBEE')))
                table_style.append(('TEXTCOLOR', (0, i), (-1, i), colors.HexColor('#C62828')))
            elif loan.client.classification in ('DEFAULTING', 'SEVERELY_DEFAULTING'):
                table_style.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#FFF8E1')))
                table_style.append(('TEXTCOLOR', (0, i), (-1, i), colors.HexColor('#E65100')))
            else:
                table_style.append(
                    ('BACKGROUND', (0, i), (-1, i), colors.HexColor('#FAFAFA') if i % 2 == 0 else colors.white))
        t.setStyle(TableStyle(table_style))
        elements.append(t)
        foot_style = ParagraphStyle(
            'Foot', parent=styles['Normal'], fontSize=5, leading=6,
            alignment=TA_LEFT, spaceAfter=0, leftIndent=0, rightIndent=0
        )
        elements.append(Paragraph(
            f'<b>Préstamos:</b> {len(loans)}  |  <b>Zona:</b> {zone.name}  |  {report_date}',
            foot_style
        ))

    def add_footer(canvas, doc):
        center_x = A4[0] / 2
        center_y = A4[1] / 2
        canvas.saveState()
        if logo_path:
            try:
                canvas.translate(center_x, center_y)
                canvas.rotate(45)
                canvas.setFillAlpha(0.18)
                canvas.drawImage(logo_path, -90, -90, width=180, height=180)
            except Exception:
                pass
        else:
            canvas.setFillColor(colors.HexColor('#e8e8e8'))
            canvas.setFont('Helvetica', 24)
            canvas.translate(center_x, center_y)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, company_name[:20])
        canvas.restoreState()
        canvas.saveState()
        footer_y = 12 * mm
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.HexColor('#555555'))
        canvas.drawCentredString(center_x, footer_y, f'{company_name} — Ficha de préstamos — {report_date}')
        # Número de página (pag 1, pag 2, ...)
        page_num = canvas.getPageNumber()
        canvas.drawRightString(A4[0] - 15 * mm, footer_y, f'pag {page_num}')
        canvas.restoreState()

    doc.build(elements, onFirstPage=add_footer, onLaterPages=add_footer)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    filename = f'ficha_clientes_zona_{zone.name.replace(" ", "_")}_{now_local.strftime("%Y%m%d_%H%M")}.pdf'
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response

# Aquí irán reportes Excel de zonas cuando los agregues, por ejemplo:
# def zone_loans_excel(request, zone_id): ...
# def zone_summary_excel(request): ...
