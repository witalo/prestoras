"""
Reportes de la app Clients (PDF y Excel).
Cada vista requiere JWT en header: Authorization: Bearer <token>.
"""
import io

from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER

from prestoras.utils_auth import get_user_from_jwt
from apps.clients.models import Client
from apps.companies.models import Company


@csrf_exempt
@require_GET
def clientes_puntuales_pdf(request):
    """
    GET /api/clients/reports/puntuales-pdf/?company_id=<id>
    PDF: Listado de clientes puntuales con todos sus datos (DNI, nombres, teléfono, etc.).
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

    try:
        company = Company.objects.get(pk=company_id)
    except Company.DoesNotExist:
        return JsonResponse({'error': 'Empresa no encontrada'}, status=404)

    company_name = (company.commercial_name or company.legal_name or 'Empresa').strip()
    company_ruc = company.ruc or ''
    now_local = timezone.localtime(timezone.now())
    report_date = now_local.strftime('%d/%m/%Y %H:%M')

    clients = (
        Client.objects
        .filter(company_id=company_id, is_active=True, classification='PUNCTUAL')
        .select_related('zone')
        .order_by('last_name', 'first_name')
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm
    )
    elements = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Heading1'],
        fontSize=11,
        alignment=TA_CENTER,
        spaceAfter=2,
    )
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=8,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#444444'),
        spaceAfter=1,
    )

    elements.append(Paragraph(company_name.upper(), title_style))
    if company_ruc:
        elements.append(Paragraph(f'RUC: {company_ruc}', subtitle_style))
    elements.append(Paragraph('Clientes puntuales', title_style))
    elements.append(Paragraph(f'{report_date}', subtitle_style))
    elements.append(Spacer(1, 4))

    headers = [
        '#', 'DNI', 'Nombres', 'Apellidos', 'Teléfono', 'Correo',
        'Zona', 'Dirección', 'Estado'
    ]
    col_widths = [18, 28, 45, 45, 32, 50, 35, 70, 22]
    data_rows = [[Paragraph('<b>%s</b>' % h, styles['Normal']) for h in headers]]

    for i, client in enumerate(clients, 1):
        zone_name = (client.zone.name if client.zone else '-')[:20]
        address = (client.home_address or client.business_address or '-')
        address = (address[:40] + '...') if len(address) > 40 else address
        email = (client.email or '-')[:25]
        row = [
            str(i),
            client.dni or '-',
            (client.first_name or '')[:25],
            (client.last_name or '')[:25],
            (client.phone or '-')[:14],
            email,
            zone_name,
            address,
            'Activo' if client.is_active else 'Inactivo',
        ]
        data_rows.append(row)

    if len(data_rows) == 1:
        elements.append(Paragraph('No hay clientes puntuales registrados.', styles['Normal']))
    else:
        t = Table(data_rows, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2e7d32')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (1, 0), (-1, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#b0bec5')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f1f8e9')]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 6))
        elements.append(Paragraph(f'<b>Total clientes puntuales:</b> {len(clients)}', styles['Normal']))

    def add_footer(canvas, doc):
        canvas.saveState()
        # Marca de agua centrada: trasladar al centro, rotar y dibujar en (0,0)
        canvas.setFillColor(colors.HexColor('#e0e0e0'))
        canvas.setFont('Helvetica', 32)
        center_x = A4[0] / 2
        center_y = A4[1] / 2
        canvas.translate(center_x, center_y)
        canvas.rotate(45)
        canvas.drawCentredString(0, 0, 'PUNTUALES')
        canvas.restoreState()
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.HexColor('#9e9e9e'))
        canvas.drawCentredString(center_x, 10 * mm, f'{company_name} - Puntuales - {report_date}')
        canvas.restoreState()

    doc.build(elements, onFirstPage=add_footer, onLaterPages=add_footer)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    filename = f'clientes_puntuales_{now_local.strftime("%Y%m%d_%H%M")}.pdf'
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


# Aquí irán más reportes de clientes (PDF/Excel), por ejemplo:
# def clientes_morosos_pdf(request): ...
# def clientes_puntuales_excel(request): ...
# def clientes_completo_excel(request): ...
