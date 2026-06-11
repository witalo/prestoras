"""
Utilidades de autenticación compartidas (reportes PDF/Excel, etc.).
Usado por apps/zones/reports.py, apps/clients/reports.py, etc.
"""
import logging
import jwt
from django.conf import settings

logger = logging.getLogger(__name__)


def get_user_from_jwt(request):
    """
    Extrae y valida JWT del header Authorization o del query param ?token=.
    Retorna el payload del token o None si no es válido.
    """
    auth = request.META.get('HTTP_AUTHORIZATION') or ''
    if auth.startswith('Bearer '):
        token = auth[7:].strip()
    else:
        # Fallback: query param ?token= (usado por iframes para evitar IDM/extensiones)
        token = request.GET.get('token', '').strip()
    if not token:
        logger.warning("Reportes auth: token ausente en header y query param")
        return None
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[getattr(settings, 'JWT_ALGORITHM', 'HS256')]
        )
        return payload
    except Exception as e:
        logger.warning("Reportes auth: JWT inválido o expirado: %s", type(e).__name__)
        return None


def get_current_user_from_info(info):
    """
    Obtiene el usuario actual desde el contexto GraphQL (JWT).
    Usado para scope: admin ve todo, cobrador solo su cartera.
    """
    if not info.context:
        return None
    return info.context.get('user') if hasattr(info.context, 'get') else getattr(info.context, 'user', None)


def get_session_error_message(info):
    """
    Retorna un mensaje de error de sesión distinguiendo token inválido/expirado vs sin token.
    Usar cuando user is None para dar el mensaje correcto al cliente.
    """
    ctx = info.context if hasattr(info.context, 'get') else None
    if ctx and ctx.get('token_provided'):
        return "Sesión inválida o expirada."
    return "No autenticado."
