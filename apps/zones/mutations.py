"""
Mutations GraphQL para Zones usando Strawberry
"""
import strawberry
from typing import Optional
from django.db import transaction
from strawberry.types import Info

from .models import Zone
from .types import ZoneType
from apps.companies.models import Company
from prestoras.utils_auth import get_current_user_from_info


@strawberry.type
class CreateZoneResult:
    """Resultado de crear una zona"""
    success: bool
    message: str
    zone: Optional[ZoneType] = None


@strawberry.type
class UpdateZoneResult:
    """Resultado de actualizar una zona"""
    success: bool
    message: str
    zone: Optional[ZoneType] = None


@strawberry.mutation
def create_zone(
    info: Info,
    company_id: int,
    name: str,
    description: Optional[str] = None
) -> CreateZoneResult:
    """Crea una nueva zona. Solo administrador."""
    user = get_current_user_from_info(info)
    if not user or user.role != 'ADMIN':
        return CreateZoneResult(success=False, message="Solo el administrador puede crear zonas.", zone=None)
    if user.company_id != company_id:
        return CreateZoneResult(success=False, message="No puede crear zonas de otra empresa.", zone=None)
    try:
        # Validar empresa
        try:
            company = Company.objects.get(id=company_id)
        except Company.DoesNotExist:
            return CreateZoneResult(
                success=False,
                message="Empresa no encontrada",
                zone=None
            )
        
        # Validar que no exista una zona con el mismo nombre en la empresa
        if Zone.objects.filter(company_id=company_id, name=name).exists():
            return CreateZoneResult(
                success=False,
                message=f"Ya existe una zona con el nombre '{name}' en esta empresa",
                zone=None
            )
        
        # Crear la zona
        zone = Zone(
            company=company,
            name=name,
            description=description,
            status='ACTIVE'
        )
        zone.save()
        
        return CreateZoneResult(
            success=True,
            message=f"Zona '{name}' creada exitosamente",
            zone=zone
        )
    
    except Exception as e:
        return CreateZoneResult(
            success=False,
            message=f"Error al crear zona: {str(e)}",
            zone=None
        )


@strawberry.mutation
def update_zone(
    info: Info,
    zone_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    is_active: Optional[bool] = None
) -> UpdateZoneResult:
    """Actualiza una zona. Solo administrador."""
    user = get_current_user_from_info(info)
    if not user or user.role != 'ADMIN':
        return UpdateZoneResult(success=False, message="Solo el administrador puede editar zonas.", zone=None)
    try:
        # Obtener la zona
        try:
            zone = Zone.objects.get(id=zone_id)
        except Zone.DoesNotExist:
            return UpdateZoneResult(
                success=False,
                message="Zona no encontrada",
                zone=None
            )
        if zone.company_id != user.company_id:
            return UpdateZoneResult(success=False, message="No puede editar zonas de otra empresa.", zone=None)
        
        # Actualizar campos si se proporcionan
        if name is not None:
            # Validar que no exista otra zona con el mismo nombre en la misma empresa
            if Zone.objects.filter(company_id=zone.company_id, name=name).exclude(id=zone_id).exists():
                return UpdateZoneResult(
                    success=False,
                    message=f"Ya existe otra zona con el nombre '{name}' en esta empresa",
                    zone=None
                )
            zone.name = name
        
        if description is not None:
            zone.description = description
        
        if is_active is not None:
            # El modelo Zone usa 'status' en lugar de 'is_active'
            zone.status = 'ACTIVE' if is_active else 'INACTIVE'
        
        zone.save()
        
        return UpdateZoneResult(
            success=True,
            message="Zona actualizada exitosamente",
            zone=zone
        )
    
    except Exception as e:
        return UpdateZoneResult(
            success=False,
            message=f"Error al actualizar zona: {str(e)}",
            zone=None
        )
