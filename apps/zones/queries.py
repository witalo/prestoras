"""
Queries GraphQL para Zones usando Strawberry
"""
import strawberry
from typing import List, Optional
from strawberry.types import Info

from .models import Zone
from .types import ZoneType


@strawberry.type
class ZoneQuery:
    """
    Queries relacionadas con zonas
    """
    
    @strawberry.field
    def zones(
        self,
        info: Info,
        company_id: int,
        is_active: Optional[bool] = True
    ) -> List[ZoneType]:
        """
        Obtener lista de zonas de una empresa
        
        Filtros:
        - company_id: Empresa (requerido)
        - is_active: Filtrar por estado activo/inactivo (default: True)
        """
        queryset = Zone.objects.filter(company_id=company_id)
        
        if is_active is not None:
            # El modelo Zone usa 'status' en lugar de 'is_active'
            status_filter = 'ACTIVE' if is_active else 'INACTIVE'
            queryset = queryset.filter(status=status_filter)
        
        return list(queryset.order_by('name'))
    
    @strawberry.field
    def zone(self, info: Info, zone_id: int) -> Optional[ZoneType]:
        """
        Obtener una zona por ID
        """
        try:
            return Zone.objects.get(id=zone_id)
        except Zone.DoesNotExist:
            return None
