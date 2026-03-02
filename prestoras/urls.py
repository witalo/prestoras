"""
URL configuration for prestoras project.
"""
from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from prestoras.views import graphql_view
from apps.zones.reports import zone_loans_pdf, zone_client_pdf
from apps.clients.reports import clientes_puntuales_pdf, clientes_activos_pdf

urlpatterns = [
    path('admin/', admin.site.urls),
    path('graphql/', graphql_view, name='graphql'),
    path('graphql', graphql_view, name='graphql_raw'),
    # Reportes por app: Zones
    path('api/zones/reports/<int:zone_id>/prestamos-pdf/', zone_loans_pdf, name='zone_loans_pdf'),
    path('api/zones/reports/<int:zone_id>/clientes-pdf/', zone_client_pdf, name='zone_client_pdf'),
    # Reportes por app: Clients (igual que zonas: dos PDF con mismo estilo)
    path('api/clients/reports/puntuales-pdf/', clientes_puntuales_pdf, name='clientes_puntuales_pdf'),
    path('api/clients/reports/clientes-activos-pdf/', clientes_activos_pdf, name='clientes_activos_pdf'),
]

# Servir archivos estáticos y media en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
