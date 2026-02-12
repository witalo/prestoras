"""
URL configuration for prestoras project.
"""
from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from prestoras.views import graphql_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('graphql/', graphql_view, name='graphql'),   # Con barra (recomendado)
    path('graphql', graphql_view, name='graphql_raw'), # Sin barra: evita error APPEND_SLASH en POST (Apollo, etc.)
]

# Servir archivos estáticos y media en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
