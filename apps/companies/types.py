"""
Tipos GraphQL para Companies usando Strawberry
Versión moderna compatible con strawberry-django 0.74.0+
Bien comentado para entender cada tipo y campo
"""
import strawberry
import base64
from typing import Optional
from datetime import datetime

# Importar los modelos
from .models import Company, LoanType


@strawberry.django.type(Company, fields="__all__")
class CompanyType:
    """
    Tipo GraphQL para Company (Empresa)
    
    Representa una empresa en el sistema multiempresa.
    Los campos del modelo se incluyen automáticamente con fields="__all__"
    """
    
    @strawberry.field
    def responsible_full_name(self) -> str:
        """Retorna el nombre completo del responsable"""
        return f"{self.responsible_names or ''} {self.responsible_last_names or ''}".strip()
    
    @strawberry.field
    def logo_url(self) -> Optional[str]:
        """Retorna la URL completa del logo si existe (para acceso directo)"""
        if self.logo:
            return self.logo.url
        return None
    
    @strawberry.field
    def logo_base64(self) -> Optional[str]:
        """
        Retorna el logo en formato base64 para enviarlo en el login de empresa
        
        Formato: "data:image/jpeg;base64,/9j/4AAQSkZJRg..." o None si no hay logo
        """
        if not self.logo:
            return None
        
        try:
            # Leer el archivo de imagen
            with open(self.logo.path, 'rb') as image_file:
                image_data = image_file.read()
                
            # Convertir a base64
            base64_data = base64.b64encode(image_data).decode('utf-8')
            
            # Detectar el tipo MIME de la imagen
            file_extension = self.logo.name.split('.')[-1].lower()
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


@strawberry.django.type(LoanType, fields="__all__")
class LoanTypeType:
    """
    Tipo GraphQL para LoanType (Tipo de Préstamo)
    
    Representa un tipo de préstamo definido por una empresa.
    """
    
    @strawberry.field
    def company_id(self) -> Optional[int]:
        """Retorna el ID de la empresa (para facilitar el acceso desde el frontend)"""
        return self.company_id
