"""
Mutations GraphQL para Users usando Strawberry
Incluye login de usuario con tokens JWT de 24 horas
"""
import strawberry
from typing import Optional
from datetime import datetime, timedelta
import jwt
from django.conf import settings
from django.contrib.auth import authenticate

from .models import User
from .types import UserType


@strawberry.type
class UserLoginResult:
    """
    Resultado del login de usuario
    
    Retorna el token de usuario y la información del usuario.
    """
    success: bool
    message: str
    token: Optional[str] = None
    user: Optional[UserType] = None
    expires_at: Optional[datetime] = None


def generate_jwt_token(payload: dict, expires_in_hours: int = 24) -> tuple[str, datetime]:
    """
    Genera un token JWT con expiración
    
    Args:
        payload: Datos a incluir en el token
        expires_in_hours: Horas de expiración (por defecto 24 horas)
    
    Returns:
        Tupla con (token, expires_at)
    """
    expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)
    payload['exp'] = expires_at
    payload['iat'] = datetime.utcnow()
    
    token = jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    
    return token, expires_at


@strawberry.mutation
def user_login(
    dni: str,
    password: str,
    company_id: Optional[int] = None
) -> UserLoginResult:
    """
    Mutation para login de usuario
    
    El login de usuario requiere:
    - DNI del usuario (usado como username)
    - Contraseña del usuario
    - company_id (opcional, para validar que el usuario pertenece a la empresa)
    
    Retorna un token JWT válido por 24 horas.
    """
    try:
        # Buscar usuario por DNI
        try:
            user = User.objects.get(dni=dni, is_active=True)
        except User.DoesNotExist:
            return UserLoginResult(
                success=False,
                message="Usuario no encontrado o inactivo. Verifique el DNI.",
                token=None,
                user=None,
                expires_at=None
            )
        
        # Validar que el usuario pertenece a la empresa si se proporciona company_id
        if company_id and user.company_id != company_id:
            return UserLoginResult(
                success=False,
                message="El usuario no pertenece a esta empresa.",
                token=None,
                user=None,
                expires_at=None
            )
        
        # Autenticar usuario con Django
        authenticated_user = authenticate(
            username=dni,
            password=password
        )
        
        if not authenticated_user or authenticated_user != user:
            return UserLoginResult(
                success=False,
                message="Contraseña incorrecta.",
                token=None,
                user=None,
                expires_at=None
            )
        
        # Generar token JWT (válido por 24 horas)
        payload = {
            'type': 'user',
            'user_id': user.id,
            'dni': user.dni,
            'company_id': user.company_id if user.company else None,
            'role': user.role,
        }
        
        token, expires_at = generate_jwt_token(payload, expires_in_hours=24)
        
        return UserLoginResult(
            success=True,
            message="Login exitoso",
            token=token,
            user=user,
            expires_at=expires_at
        )
    
    except Exception as e:
        return UserLoginResult(
            success=False,
            message=f"Error en el login: {str(e)}",
            token=None,
            user=None,
            expires_at=None
        )
