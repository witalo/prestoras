"""
Reportes de la app Clients (PDF y Excel).
Mismo estilo que Zones: encabezado 3 columnas (empresa | título | logo), tabla con cabecera azul, pie con fecha y página.
Cada vista requiere JWT en header: Authorization: Bearer <token>.
Parámetro opcional collector_id: si el usuario es cobrador, se filtra por sus clientes asignados.
"""
import io
import os
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
from apps.clients.models import Client
from apps.companies.models import Company


def _get_logo_path(company):
    """Ruta del logo de la empresa si existe en disco (igual que en zones)."""
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


def _get_clients_queryset(company_id, is_active=True, classification=None, collector_id=None):
    """Clientes de la empresa. Si collector_id se pasa, solo los asignados a ese cobrador."""
    qs = Client.objects.filter(company_id=company_id, is_active=is_active).select_related('zone')
    if classification:
        qs = qs.filter(classification=classification)
    if collector_id:
        qs = qs.filter(collectors__id=collector_id)
    return qs.order_by('last_name', 'first_name')


def _build_client_report_header(elements, company, title_text, subtitle_text, report_date, styles):
    """Encabezado igual que zonas: 3 columnas (empresa+ruc | título+subtítulo+fecha | logo)."""
    company_name = (company.commercial_name or company.legal_name or 'Empresa').strip()
    company_ruc = company.ruc or ''
    logo_path = _get_logo_path(company)

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

    col1 = [Paragraph(f'<b>%s</b>' % company_name.upper(), left_style)]
    if company_ruc:
        col1.append(Paragraph(f'RUC: {company_ruc}', left_small))
    col2 = [
        Paragraph(f'<b>%s</b>' % title_text, center_style),
        Paragraph(subtitle_text, center_small),
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

    header_table = Table([[col1, col2, col3]], colWidths=[170, 198, 170])
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


def _add_footer_client(canvas, doc, company_name, report_date, title_label, logo_path):
    """Pie de página igual que zonas: marca de agua (logo o texto) + texto centrado abajo."""
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
            canvas.restoreState()
            canvas.saveState()
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
    canvas.saveState()
    footer_y = 12 * mm
    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(colors.HexColor('#555555'))
    canvas.drawCentredString(center_x, footer_y, f'{company_name} — {title_label} — {report_date}')
    page_num = canvas.getPageNumber()
    canvas.drawRightString(A4[0] - 15 * mm, footer_y, f'pag {page_num}')
    canvas.restoreState()


@csrf_exempt
@require_GET
def clientes_puntuales_pdf(request):
    """
    GET /api/clients/reports/puntuales-pdf/?company_id=<id>&collector_id=<opcional>
    PDF: Listado de clientes puntuales. Mismo diseño que zonas (encabezado 3 cols, tabla azul, pie).
    Si collector_id viene en GET (y el usuario es ese cobrador o admin), solo clientes asignados a ese cobrador.
    """
    payload = get_user_from_jwt(request)
    if not payload:
        return JsonResponse({'error': 'No autorizado'}, status=401)

    company_id = request.GET.get('company_id') or payload.get('company_id')
    if not company_id:
        return JsonResponse({'error': 'Falta company_id'}, status=400)
    try:
        company_id = int(company_id)
    except (TypeError, ValueError):
        return JsonResponse({'error': 'company_id inválido'}, status=400)

    collector_id = request.GET.get('collector_id')
    if collector_id is not None:
        try:
            collector_id = int(collector_id)
        except (TypeError, ValueError):
            collector_id = None

    try:
        company = Company.objects.get(pk=company_id)
    except Company.DoesNotExist:
        return JsonResponse({'error': 'Empresa no encontrada'}, status=404)

    company_name = (company.commercial_name or company.legal_name or 'Empresa').strip()
    logo_path = _get_logo_path(company)
    now_local = timezone.localtime(timezone.now())
    report_date = now_local.strftime('%d/%m/%Y %H:%M')

    clients = list(_get_clients_queryset(
        company_id, is_active=True, classification='PUNCTUAL', collector_id=collector_id
    ))
    subtitle = f'Cobrador: {collector_id}' if collector_id else 'Todos los clientes puntuales'
    # Si el JWT tiene user_id y es cobrador, podrías poner el nombre; por ahora solo el id o "Todos"

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=8 * mm,
        bottomMargin=10 * mm,
    )
    elements = []
    styles = getSampleStyleSheet()
    table_header_style = ParagraphStyle(
        'TableHeader', parent=styles['Normal'], fontSize=5, leading=6,
        textColor=colors.white, alignment=TA_CENTER,
    )
    cell_body = ParagraphStyle(
        'CellBody', parent=styles['Normal'], fontSize=4, leading=4,
        spaceAfter=0, spaceBefore=0, textColor=colors.HexColor('#1a1a1a'), alignment=TA_LEFT,
    )
    cell_body_center = ParagraphStyle(
        'CellBodyCenter', parent=styles['Normal'], fontSize=4, leading=4,
        spaceAfter=0, spaceBefore=0, textColor=colors.HexColor('#1a1a1a'), alignment=TA_CENTER,
    )
    small_normal = ParagraphStyle('SmallNormal', parent=styles['Normal'], fontSize=5, leading=6)

    _build_client_report_header(
        elements, company,
        title_text='CLIENTES PUNTUALES',
        subtitle_text=subtitle,
        report_date=report_date,
        styles=styles,
    )

    headers = ['#', 'DNI', 'Cliente', 'Teléfono', 'Zona', 'Clasificación']
    col_widths = [22, 50, 180, 55, 120, 50]  # suma ~477, ajustado a 538 si hace falta
    col_widths = [20, 48, 200, 52, 140, 78]
    data_rows = [[Paragraph('<b>%s</b>' % h, table_header_style) for h in headers]]

    for i, client in enumerate(clients, 1):
        zone_name = (client.zone.name if client.zone else '-')[:18]
        clasif = (client.get_classification_display() if hasattr(client, 'get_classification_display') else (client.classification or '-'))[:12]
        row = [
            Paragraph(escape(str(i)), cell_body_center),
            Paragraph(escape(client.dni or '-'), cell_body),
            Paragraph(escape(f"{client.first_name} {client.last_name}".strip()[:30]), cell_body),
            Paragraph(escape((client.phone or '-')[:14]), cell_body),
            Paragraph(escape(zone_name), cell_body),
            Paragraph(escape(clasif), cell_body_center),
        ]
        data_rows.append(row)

    if len(data_rows) == 1:
        elements.append(Paragraph('No hay clientes puntuales registrados.', small_normal))
    else:
        t = Table(data_rows, colWidths=col_widths, repeatRows=1)
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
            ('ALIGN', (5, 0), (5, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.2, colors.HexColor('#B0BEC5')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 1), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 2),
        ]
        for i in range(1, len(data_rows)):
            table_style.append(
                ('BACKGROUND', (0, i), (-1, i),
                 colors.HexColor('#FAFAFA') if i % 2 == 0 else colors.white))
        t.setStyle(TableStyle(table_style))
        elements.append(t)
        elements.append(Spacer(1, 2))
        foot_style = ParagraphStyle(
            'Foot', parent=styles['Normal'], fontSize=5, leading=6,
            alignment=TA_LEFT, spaceAfter=0,
        )
        elements.append(Paragraph(f'<b>Total clientes puntuales:</b> {len(clients)}', foot_style))

    def add_footer(canvas, doc):
        _add_footer_client(canvas, doc, company_name, report_date, 'Clientes puntuales', logo_path)

    doc.build(elements, onFirstPage=add_footer, onLaterPages=add_footer)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    filename = f'clientes_puntuales_{now_local.strftime("%Y%m%d_%H%M")}.pdf'
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


@csrf_exempt
@require_GET
def clientes_activos_pdf(request):
    """
    GET /api/clients/reports/clientes-activos-pdf/?company_id=<id>&collector_id=<opcional>
    PDF: Ficha de clientes activos (todos los activos o solo del cobrador). Mismo diseño que zonas.
    """
    payload = get_user_from_jwt(request)
    if not payload:
        return JsonResponse({'error': 'No autorizado'}, status=401)

    company_id = request.GET.get('company_id') or payload.get('company_id')
    if not company_id:
        return JsonResponse({'error': 'Falta company_id'}, status=400)
    try:
        company_id = int(company_id)
    except (TypeError, ValueError):
        return JsonResponse({'error': 'company_id inválido'}, status=400)

    collector_id = request.GET.get('collector_id')
    if collector_id is not None:
        try:
            collector_id = int(collector_id)
        except (TypeError, ValueError):
            collector_id = None

    try:
        company = Company.objects.get(pk=company_id)
    except Company.DoesNotExist:
        return JsonResponse({'error': 'Empresa no encontrada'}, status=404)

    company_name = (company.commercial_name or company.legal_name or 'Empresa').strip()
    logo_path = _get_logo_path(company)
    now_local = timezone.localtime(timezone.now())
    report_date = now_local.strftime('%d/%m/%Y %H:%M')

    clients = list(_get_clients_queryset(
        company_id, is_active=True, classification=None, collector_id=collector_id
    ))
    subtitle = f'Cobrador ID: {collector_id}' if collector_id else 'Todos los clientes activos'

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=8 * mm,
        bottomMargin=10 * mm,
    )
    elements = []
    styles = getSampleStyleSheet()
    table_header_style = ParagraphStyle(
        'TableHeader', parent=styles['Normal'], fontSize=5, leading=6,
        textColor=colors.white, alignment=TA_CENTER,
    )
    cell_body = ParagraphStyle(
        'CellBody', parent=styles['Normal'], fontSize=4, leading=4,
        spaceAfter=0, spaceBefore=0, textColor=colors.HexColor('#1a1a1a'), alignment=TA_LEFT,
    )
    cell_body_center = ParagraphStyle(
        'CellBodyCenter', parent=styles['Normal'], fontSize=4, leading=4,
        spaceAfter=0, spaceBefore=0, textColor=colors.HexColor('#1a1a1a'), alignment=TA_CENTER,
    )
    small_normal = ParagraphStyle('SmallNormal', parent=styles['Normal'], fontSize=5, leading=6)

    _build_client_report_header(
        elements, company,
        title_text='FICHA DE CLIENTES ACTIVOS',
        subtitle_text=subtitle,
        report_date=report_date,
        styles=styles,
    )

    headers = ['#', 'DNI', 'Cliente', 'Teléfono', 'Zona', 'Clasificación']
    col_widths = [20, 48, 200, 52, 140, 78]
    data_rows = [[Paragraph('<b>%s</b>' % h, table_header_style) for h in headers]]

    for i, client in enumerate(clients, 1):
        zone_name = (client.zone.name if client.zone else '-')[:18]
        clasif = (client.get_classification_display() if hasattr(client, 'get_classification_display') else (client.classification or '-'))[:12]
        row = [
            Paragraph(escape(str(i)), cell_body_center),
            Paragraph(escape(client.dni or '-'), cell_body),
            Paragraph(escape(f"{client.first_name} {client.last_name}".strip()[:30]), cell_body),
            Paragraph(escape((client.phone or '-')[:14]), cell_body),
            Paragraph(escape(zone_name), cell_body),
            Paragraph(escape(clasif), cell_body_center),
        ]
        data_rows.append(row)

    if len(data_rows) == 1:
        elements.append(Paragraph('No hay clientes activos.', small_normal))
    else:
        t = Table(data_rows, colWidths=col_widths, repeatRows=1)
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
            ('ALIGN', (5, 0), (5, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.2, colors.HexColor('#B0BEC5')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 1), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 2),
        ]
        for i in range(1, len(data_rows)):
            table_style.append(
                ('BACKGROUND', (0, i), (-1, i),
                 colors.HexColor('#FAFAFA') if i % 2 == 0 else colors.white))
        t.setStyle(TableStyle(table_style))
        elements.append(t)
        elements.append(Spacer(1, 2))
        foot_style = ParagraphStyle(
            'Foot', parent=styles['Normal'], fontSize=5, leading=6,
            alignment=TA_LEFT, spaceAfter=0,
        )
        elements.append(Paragraph(f'<b>Total clientes:</b> {len(clients)}', foot_style))

    def add_footer(canvas, doc):
        _add_footer_client(canvas, doc, company_name, report_date, 'Ficha clientes activos', logo_path)

    doc.build(elements, onFirstPage=add_footer, onLaterPages=add_footer)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    filename = f'ficha_clientes_activos_{now_local.strftime("%Y%m%d_%H%M")}.pdf'
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response
