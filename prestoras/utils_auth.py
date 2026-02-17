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
    Extrae y valida JWT del header Authorization: Bearer <token>.
    Retorna el payload del token o None si no es válido.
    """
    auth = request.META.get('HTTP_AUTHORIZATION') or ''
    if not auth.startswith('Bearer '):
        logger.warning("Reportes auth: header Authorization ausente o sin 'Bearer '")
        return None
    token = auth[7:].strip()
    if not token:
        logger.warning("Reportes auth: token vacío después de 'Bearer '")
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
