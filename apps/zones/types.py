"""
Tipos GraphQL para Zones usando Strawberry
Versión moderna compatible con strawberry-django 0.74.0+
"""
import strawberry
from typing import Optional

from .models import Zone


@strawberry.django.type(Zone, fields="__all__")
class ZoneType:
    """
    Tipo GraphQL para Zone (Zona)
    
    Representa una zona para organizar clientes y cobradores.
    Los campos del modelo se incluyen automáticamente con fields="__all__"
    """
    
    @strawberry.field
    def company_id(self) -> Optional[int]:
        """Retorna el ID de la empresa (para facilitar el acceso desde el frontend)"""
        return self.company_id
    
    @strawberry.field
    def is_active(self) -> bool:
        """
        Retorna si la zona está activa (mapeado desde status)
        
        El modelo usa 'status' (ACTIVE/INACTIVE) pero el frontend espera 'isActive' (boolean)
        """
        return self.status == 'ACTIVE'