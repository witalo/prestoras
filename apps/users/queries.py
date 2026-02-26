"""
Queries GraphQL para Users usando Strawberry
"""
import strawberry
from typing import List, Optional
from strawberry.types import Info

from .models import User
from .types import UserType


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
        """
        Obtener lista de usuarios
        
        Filtros opcionales:
        - company_id: Filtrar por empresa
        - role: Filtrar por rol (ADMIN, COLLECTOR)
        - is_active: Filtrar por estado activo/inactivo
        """
        queryset = User.objects.all()
        
        if company_id:
            queryset = queryset.filter(company_id=company_id)
        
        if role:
            queryset = queryset.filter(role=role)
        
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        
        return list(queryset.select_related('company').prefetch_related('assigned_clients'))
    
    @strawberry.field
    def user(self, info: Info, user_id: int) -> Optional[UserType]:
        """
        Obtener un usuario por ID
        """
        try:
            return User.objects.select_related('company').prefetch_related('assigned_clients').get(id=user_id)
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
        """
        Obtener cobradores de la empresa (para asignar cartera).
        """
        queryset = User.objects.filter(
            role='COLLECTOR',
            company_id=company_id
        )
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return list(queryset.select_related('company').prefetch_related('assigned_clients'))
