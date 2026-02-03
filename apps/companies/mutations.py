"""
Mutations GraphQL para Companies usando Strawberry
Incluye login de empresa
"""
import strawberry
from typing import Optional
from datetime import datetime, timedelta
import jwt
from django.conf import settings

from .models import Company
from .types import CompanyType


@strawberry.type
class CompanyLoginResult:
    """
    Resultado del login de empresa
    
    Retorna el token de empresa y la información de la empresa.
    """
    success: bool
    message: str
    token: Optional[str] = None
    company: Optional[CompanyType] = None
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
def company_login(
    ruc: str,
    email: str,
    password: str
) -> CompanyLoginResult:
    """
    Mutation para login de empresa
    
    El login de empresa requiere:
    - RUC de la empresa
    - Correo de la empresa
    - Contraseña de la empresa
    
    Retorna un token JWT válido por 24 horas.
    """
    try:
        # Buscar empresa por RUC o email
        try:
            # Intentar buscar por RUC primero
            company = Company.objects.filter(ruc=ruc).first()
            
            # Si no se encuentra por RUC, buscar por email
            if not company:
                company = Company.objects.filter(email=email).first()
            
            if not company:
                raise Company.DoesNotExist
        except Company.DoesNotExist:
            return CompanyLoginResult(
                success=False,
                message="Empresa no encontrada. Verifique el RUC o correo.",
                token=None,
                company=None,
                expires_at=None
            )
        
        # Verificar si la empresa está activa
        if not company.is_active:
            return CompanyLoginResult(
                success=False,
                message="La empresa está inactiva. Contacte al administrador.",
                token=None,
                company=None,
                expires_at=None
            )
        
        # Verificar contraseña
        if not company.check_password(password):
            return CompanyLoginResult(
                success=False,
                message="Contraseña incorrecta.",
                token=None,
                company=None,
                expires_at=None
            )
        
        # Generar token JWT (válido por 24 horas)
        payload = {
            'type': 'company',
            'company_id': company.id,
            'ruc': company.ruc,
        }
        
        token, expires_at = generate_jwt_token(payload, expires_in_hours=24)
        
        return CompanyLoginResult(
            success=True,
            message="Login exitoso",
            token=token,
            company=company,
            expires_at=expires_at
        )
    
    except Exception as e:
        return CompanyLoginResult(
            success=False,
            message=f"Error en el login: {str(e)}",
            token=None,
            company=None,
            expires_at=None
        )
