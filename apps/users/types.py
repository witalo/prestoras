"""
Tipos GraphQL para Users usando Strawberry
Versión moderna compatible con strawberry-django 0.74.0+
"""
import strawberry
import base64
from typing import Optional, List, TYPE_CHECKING

from .models import User
from apps.zones.types import ZoneType

if TYPE_CHECKING:
    from apps.companies.types import CompanyType


@strawberry.django.type(User, fields="__all__")
class UserType:
    """
    Tipo GraphQL para User (Usuario)
    
    Representa un usuario del sistema (Administrador o Cobrador).
    Los campos del modelo se incluyen automáticamente con fields="__all__"
    """
    # company se incluye automáticamente con __all__, pero podemos definirlo explícitamente si queremos
    
    @strawberry.field
    def full_name(self) -> str:
        """Retorna el nombre completo del usuario"""
        return f"{self.first_name} {self.last_name}".strip()
    
    @strawberry.field
    def photo_url(self) -> Optional[str]:
        """Retorna la URL completa de la foto si existe (para acceso directo)"""
        if self.photo:
            return self.photo.url
        return None
    
    @strawberry.field
    def photo_base64(self) -> Optional[str]:
        """
        Retorna la foto del usuario en formato base64
        
        Formato: "data:image/jpeg;base64,/9j/4AAQSkZJRg..." o None si no hay foto
        """
        if not self.photo:
            return None
        
        try:
            # Leer el archivo de imagen
            with open(self.photo.path, 'rb') as image_file:
                image_data = image_file.read()
                
            # Convertir a base64
            base64_data = base64.b64encode(image_data).decode('utf-8')
            
            # Detectar el tipo MIME de la imagen
            file_extension = self.photo.name.split('.')[-1].lower()
            mime_types = {
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'png': 'image/png',
                'gif': 'image/gif',
                'webp': 'image/webp',
            }
            mime_type = mime_types.get(file_extension, 'image/jpeg')
            
            # Retornar en formato data URL
            return f"data:{mime_type};base64,{base64_data}"
        except Exception:
            # Si hay algún error al leer el archivo, retornar None
            return None
    
    @strawberry.field
    def is_admin(self) -> bool:
        """Retorna True si el usuario es administrador"""
        return self.role == 'ADMIN' or self.is_superuser
    
    @strawberry.field
    def is_collector(self) -> bool:
        """Retorna True si el usuario es cobrador"""
        return self.role == 'COLLECTOR'
    
    @strawberry.field
    def company_id(self) -> Optional[int]:
        """Retorna el ID de la empresa (para facilitar el acceso desde el frontend)"""
        return self.company_id

    @strawberry.field
    def zones(self) -> List[ZoneType]:
        """Zonas asignadas al usuario (cobrador). Para perfil y listados."""
        return list(self.zones.all())
