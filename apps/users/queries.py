"""
Queries GraphQL para Users usando Strawberry
"""
import strawberry
from typing import List, Optional
from strawberry.types import Info

from .models import User
from .types import UserType
from prestoras.utils_auth import get_current_user_from_info


@strawberry.type
class UserQuery:
    """
    Queries relacionadas con usuarios
    """
    
    @strawberry.field
    def users(
        self,
        info: Info,
        company_id: Optional[int] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = True
    ) -> List[UserType]:
        """Lista de usuarios. Solo administrador puede consultarla."""
        current_user = get_current_user_from_info(info)
        if not current_user or current_user.role != 'ADMIN':
            return []
        queryset = User.objects.filter(company_id=current_user.company_id)
        if company_id and company_id != current_user.company_id:
            return []
        if role:
            queryset = queryset.filter(role=role)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return list(queryset.select_related('company').prefetch_related('assigned_clients'))
    
    @strawberry.field
    def user(self, info: Info, user_id: int) -> Optional[UserType]:
        """Admin ve cualquier usuario de su empresa; cobrador solo se ve a sí mismo."""
        current_user = get_current_user_from_info(info)
        if not current_user:
            return None
        try:
            obj = User.objects.select_related('company').prefetch_related('assigned_clients').get(id=user_id)
            if current_user.role == 'COLLECTOR' and current_user.id != user_id:
                return None
            if obj.company_id != current_user.company_id:
                return None
            return obj
        except User.DoesNotExist:
            return None
    
    @strawberry.field
    def user_by_dni(self, info: Info, dni: str, company_id: Optional[int] = None) -> Optional[UserType]:
        """
        Obtener un usuario por DNI
        
        Si se proporciona company_id, valida que el usuario pertenezca a esa empresa.
        """
        try:
            user = User.objects.select_related('company').prefetch_related('assigned_clients').get(dni=dni)
            
            if company_id and user.company_id != company_id:
                return None
            
            return user
        except User.DoesNotExist:
            return None
    
    @strawberry.field
    def collectors(
        self,
        info: Info,
        company_id: int,
        is_active: Optional[bool] = True
    ) -> List[UserType]:
        """Lista de cobradores de la empresa. Solo administrador."""
        current_user = get_current_user_from_info(info)
        if not current_user or current_user.role != 'ADMIN':
            return []
        if current_user.company_id != company_id:
            return []
        queryset = User.objects.filter(role='COLLECTOR', company_id=company_id)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return list(queryset.select_related('company').prefetch_related('assigned_clients'))

    @strawberry.field(name="companyUsers")
    def company_users(
        self,
        info: Info,
        company_id: int,
        is_active: Optional[bool] = True
    ) -> List[UserType]:
        """Todos los usuarios de la empresa (admin + cobradores) — para registrar pagos."""
        from django.db.models import Q
        current_user = get_current_user_from_info(info)
        if not current_user:
            return []
        # Incluir: usuarios del company_id dado + el usuario actual (por si su company_id es NULL)
        q = Q(company_id=company_id) | Q(pk=current_user.pk)
        queryset = User.objects.filter(q).distinct()
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return list(queryset.order_by('role', 'first_name', 'last_name'))
