"""
Mutations GraphQL para Users usando Strawberry
Incluye login, crear/editar usuario (con foto opcional) y cambiar contraseña (solo admin).
"""
import base64
import uuid
import strawberry
from typing import Optional
from datetime import datetime, timedelta
import jwt
from django.conf import settings
from django.contrib.auth import authenticate
from django.core.files.base import ContentFile

from .models import User
from .types import UserType


def _save_photo_from_base64(user, photo_base64: str) -> bool:
    """Decodifica photo_base64 y guarda en user.photo. Devuelve True si ok."""
    if not photo_base64 or not photo_base64.strip():
        return False
    try:
        if ',' in photo_base64:
            base64_data = photo_base64.split(',')[1]
        else:
            base64_data = photo_base64.strip()
        file_data = base64.b64decode(base64_data)
        ext = 'jpg'
        if ',' in photo_base64:
            mime = photo_base64.split(',')[0]
            if 'png' in mime:
                ext = 'png'
            elif 'jpeg' in mime or 'jpg' in mime:
                ext = 'jpg'
        name = f"{user.dni}_{uuid.uuid4().hex[:8]}.{ext}"
        user.photo.save(name, ContentFile(file_data), save=False)
        return True
    except Exception:
        return False


@strawberry.type
class UserOperationResult:
    success: bool
    message: str
    user: Optional[UserType] = None


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


def _get_current_user(info):
    """Usuario autenticado desde JWT en context (dict con 'user')."""
    if not info.context:
        return None
    return info.context.get("user") if hasattr(info.context, "get") else getattr(info.context, "user", None)


@strawberry.mutation
def create_user(
    info,
    company_id: int,
    dni: str,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    role: str,
    phone: Optional[str] = None,
    photo_base64: Optional[str] = None,
) -> UserOperationResult:
    """Crear usuario (Administrador o Cobrador). Solo ADMIN. Foto opcional."""
    current = _get_current_user(info)
    if not current or not current.is_authenticated or current.role != 'ADMIN':
        return UserOperationResult(success=False, message="Solo administrador puede crear usuarios.", user=None)
    if current.company_id != company_id:
        return UserOperationResult(success=False, message="No puede crear usuarios de otra empresa.", user=None)
    try:
        from apps.companies.models import Company
        dni = dni.strip()
        if len(dni) != 8 or not dni.isdigit():
            return UserOperationResult(success=False, message="El DNI debe tener 8 dígitos.", user=None)
        if User.objects.filter(dni=dni).exists():
            return UserOperationResult(success=False, message="Ya existe un usuario con este DNI.", user=None)
        if User.objects.filter(email__iexact=email.strip()).exists():
            return UserOperationResult(success=False, message="Ya existe un usuario con este correo.", user=None)
        if role not in ('ADMIN', 'COLLECTOR'):
            return UserOperationResult(success=False, message="Rol debe ser ADMIN o COLLECTOR.", user=None)
        company = Company.objects.get(id=company_id)
        user = User(
            dni=dni,
            email=email.strip().lower(),
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            company=company,
            role=role,
            phone=(phone or "").strip() or None,
            is_active=True,
        )
        user.set_password(password)
        user.save()
        if photo_base64 and photo_base64.strip():
            _save_photo_from_base64(user, photo_base64)
            user.save()
        return UserOperationResult(success=True, message="Usuario creado correctamente.", user=user)
    except Company.DoesNotExist:
        return UserOperationResult(success=False, message="Empresa no encontrada.", user=None)
    except Exception as e:
        return UserOperationResult(success=False, message=str(e), user=None)


@strawberry.mutation
def update_user(
    info,
    user_id: int,
    email: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    role: Optional[str] = None,
    phone: Optional[str] = None,
    is_active: Optional[bool] = None,
    new_password: Optional[str] = None,
    photo_base64: Optional[str] = None,
) -> UserOperationResult:
    """Actualizar usuario. Solo ADMIN de la misma empresa. Foto opcional (vacío = quitar foto)."""
    current = _get_current_user(info)
    if not current or not current.is_authenticated or current.role != 'ADMIN':
        return UserOperationResult(success=False, message="Solo administrador puede editar usuarios.", user=None)
    try:
        user = User.objects.get(id=user_id)
        if user.company_id != current.company_id:
            return UserOperationResult(success=False, message="No puede editar usuarios de otra empresa.", user=None)
        if email is not None:
            email = email.strip().lower()
            if User.objects.filter(email__iexact=email).exclude(id=user_id).exists():
                return UserOperationResult(success=False, message="El correo ya está en uso.", user=None)
            user.email = email
        if first_name is not None:
            user.first_name = first_name.strip()
        if last_name is not None:
            user.last_name = last_name.strip()
        if role is not None:
            if role not in ('ADMIN', 'COLLECTOR'):
                return UserOperationResult(success=False, message="Rol debe ser ADMIN o COLLECTOR.", user=None)
            user.role = role
        if phone is not None:
            user.phone = phone.strip() or None
        if is_active is not None:
            user.is_active = is_active
        if new_password is not None and (new_password or "").strip():
            if len(new_password) < 4:
                return UserOperationResult(success=False, message="La contraseña debe tener al menos 4 caracteres.", user=None)
            user.set_password(new_password)
        if photo_base64 is not None:
            if (photo_base64 or "").strip() == "":
                if user.photo:
                    user.photo.delete(save=False)
                    user.photo = None
            else:
                _save_photo_from_base64(user, photo_base64)
        user.save()
        return UserOperationResult(success=True, message="Usuario actualizado.", user=user)
    except User.DoesNotExist:
        return UserOperationResult(success=False, message="Usuario no encontrado.", user=None)
    except Exception as e:
        return UserOperationResult(success=False, message=str(e), user=None)


@strawberry.mutation
def admin_set_password(
    info,
    user_id: int,
    new_password: str,
) -> UserOperationResult:
    """El administrador restablece la contraseña de un usuario (sin contraseña actual)."""
    current = _get_current_user(info)
    if not current or not current.is_authenticated or current.role != 'ADMIN':
        return UserOperationResult(success=False, message="Solo administrador puede restablecer contraseñas.", user=None)
    if len(new_password) < 4:
        return UserOperationResult(success=False, message="La contraseña debe tener al menos 4 caracteres.", user=None)
    try:
        user = User.objects.get(id=user_id)
        if user.company_id != current.company_id:
            return UserOperationResult(success=False, message="No puede cambiar contraseña de otro empresa.", user=None)
        user.set_password(new_password)
        user.save()
        return UserOperationResult(success=True, message="Contraseña actualizada.", user=user)
    except User.DoesNotExist:
        return UserOperationResult(success=False, message="Usuario no encontrado.", user=None)
    except Exception as e:
        return UserOperationResult(success=False, message=str(e), user=None)
