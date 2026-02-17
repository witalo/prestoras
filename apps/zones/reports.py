"""
Reportes de la app Zones (PDF y Excel).
Cada vista requiere JWT en header: Authorization: Bearer <token>.
"""
import io
import os
from decimal import Decimal

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

    # A4: 210mm width. Márgenes reducidos para usar todo el ancho útil (~190mm)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm
    )
    # Ancho útil A4: 595pt - (10+10)mm ≈ 538 pt
    usable_width_pt = 538
    elements = []
    styles = getSampleStyleSheet()
    small_normal = ParagraphStyle('SmallNormal', parent=styles['Normal'], fontSize=5, leading=6)
    table_header_style = ParagraphStyle(
        'TableHeader', parent=styles['Normal'], fontSize=5, leading=6,
        textColor=colors.white, alignment=TA_CENTER,
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
        colWidths=[179, 180, 179]  # partes iguales, suma = 538
    )
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 4))

    # Cabeceras cortas para que encajen; columnas repartidas en todo el ancho útil
    headers = ['#', 'DNI', 'Cliente', 'Tel', 'F.prést', 'Solic', 'Total', 'Pag', 'Saldo', 'Tipo', 'Est.']
    col_widths = [18, 38, 158, 30, 32, 42, 42, 42, 42, 30, 22]  # suma = 538
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
        row = [
            str(n), client.dni or '-', full_name, phone, f_prestamo,
            '%.2f' % loan.initial_amount, '%.2f' % loan.total_amount,
            '%.2f' % loan.paid_amount, '%.2f' % loan.pending_amount,
            tipo[:6] if isinstance(tipo, str) else str(tipo)[:6],
            estado[:4] if isinstance(estado, str) else str(estado)[:4]
        ]
        data_rows.append(row)

    if not data_rows[1:]:
        elements.append(Paragraph('No hay clientes con deuda activa en esta zona.', small_normal))
    else:
        t = Table(data_rows, colWidths=col_widths, repeatRows=1)
        # Cabecera azul, texto blanco; cuerpo 5pt para que todo encaje
        table_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1565C0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 5),
            ('TOPPADDING', (0, 0), (-1, 0), 2),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (1, 0), (4, -1), 'LEFT'),
            ('ALIGN', (5, 0), (8, -1), 'RIGHT'),
            ('ALIGN', (9, 0), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, -1), 5),
            ('GRID', (0, 0), (-1, -1), 0.2, colors.HexColor('#B0BEC5')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ]
        for i, loan in enumerate(loans, start=1):
            if loan.paid_amount <= 0:
                table_style.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#FFEBEE')))
                table_style.append(('TEXTCOLOR', (0, i), (-1, i), colors.HexColor('#C62828')))
            elif loan.client.classification in ('DEFAULTING', 'SEVERELY_DEFAULTING'):
                table_style.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#FFF8E1')))
                table_style.append(('TEXTCOLOR', (0, i), (-1, i), colors.HexColor('#E65100')))
            else:
                table_style.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#FAFAFA') if i % 2 == 0 else colors.white))
        t.setStyle(TableStyle(table_style))
        elements.append(t)
        elements.append(Spacer(1, 6))
        total_row = [
            '', '', 'TOTALES', '', '',
            '%.2f' % total_solicitado, '%.2f' % total_monto_mas_int,
            '%.2f' % total_pagado, '%.2f' % total_saldo, '', ''
        ]
        t_total = Table([total_row], colWidths=col_widths)
        t_total.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#1565C0')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('ALIGN', (5, 0), (8, -1), 'RIGHT'),
            ('ALIGN', (0, 0), (4, -1), 'LEFT'),
            ('ALIGN', (9, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.2, colors.HexColor('#1565C0')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ]))
        elements.append(t_total)
        foot_style = ParagraphStyle('Foot', parent=styles['Normal'], fontSize=5, leading=6, alignment=TA_LEFT, spaceAfter=0, leftIndent=0, rightIndent=0)
        elements.append(Paragraph(f'<b>Total deuda:</b> S/ %.2f  |  <b>Préstamos:</b> %d' % (total_saldo, n), foot_style))

    def add_footer(canvas, doc):
        center_x = A4[0] / 2
        canvas.saveState()
        # Marca de agua centrada
        canvas.setFillColor(colors.HexColor('#e8e8e8'))
        canvas.setFont('Helvetica', 24)
        center_y = A4[1] / 2
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


# Aquí irán reportes Excel de zonas cuando los agregues, por ejemplo:
# def zone_loans_excel(request, zone_id): ...
# def zone_summary_excel(request): ...
