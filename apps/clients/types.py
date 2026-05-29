"""
Tipos GraphQL para Clients usando Strawberry
Versión moderna compatible con strawberry-django 0.74.0+
"""
import strawberry
import base64
from decimal import Decimal
from typing import Optional, List

from .models import Client, ClientDocument, DOCUMENT_TYPE_CHOICES, REQUIRED_DOCUMENT_TYPES


@strawberry.django.type(Client, fields="__all__")
class ClientType:
    """
    Tipo GraphQL para Client (Cliente)

    Representa un cliente del sistema.
    Los campos del modelo se incluyen automáticamente con fields="__all__"
    """

    @strawberry.field
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @strawberry.field
    def zone_id(self) -> Optional[int]:
        return self.zone_id

    @strawberry.field
    def address(self) -> Optional[str]:
        """
        Retorna la dirección principal del cliente (home_address)
        Campo de compatibilidad para el frontend que usa 'address'
        """
        return self.home_address
    
    @strawberry.field
    def client_id(self) -> int:
        """
        Retorna el ID del cliente (alias de 'id' para consistencia con otros tipos)
        """
        return self.id
    
    # Nota: Los campos del modelo se exponen automáticamente en camelCase:
    # - first_name → firstName
    # - last_name → lastName
    # - home_address → homeAddress
    # - business_address → businessAddress
    # - is_active → isActive
    # - created_at → createdAt
    # - updated_at → updatedAt


@strawberry.type
class CollectionRouteItemType:
    """
    Item de ruta de cobro: un préstamo con cuotas pendientes en esa fecha.
    Un cliente con N préstamos activos genera N items.
    """
    client: ClientType
    amount_to_collect: Decimal = strawberry.field(name="amountToCollect")
    paid: bool
    loan_id: int = strawberry.field(name="loanId", default=0)
    loan_status: str = strawberry.field(name="loanStatus", default="ACTIVE")


@strawberry.django.type(ClientDocument, fields="__all__")
class ClientDocumentType:
    """
    Tipo GraphQL para ClientDocument (Documento de Cliente)
    
    Almacena fotos de DNI, recibos (agua/luz), contratos y otros documentos del cliente.
    """
    
    @strawberry.field
    def client_id(self) -> int:
        """Retorna el ID del cliente (para facilitar el acceso desde el frontend)"""
        return self.client_id
    
    @strawberry.field
    def file_url(self) -> str:
        """Retorna la URL completa del archivo (para acceso directo)"""
        return self.file.url if self.file else ""
    
    @strawberry.field
    def file_base64(self) -> Optional[str]:
        """
        Retorna el documento en formato base64
        
        Útil para enviar fotos de DNI, recibos, etc. al frontend.
        Formato: "data:image/jpeg;base64,/9j/4AAQSkZJRg..." o None si no hay archivo
        """
        if not self.file:
            return None
        
        try:
            # Leer el archivo
            with open(self.file.path, 'rb') as file_handle:
                file_data = file_handle.read()
                
            # Convertir a base64
            base64_data = base64.b64encode(file_data).decode('utf-8')
            
            # Detectar el tipo MIME del archivo
            file_extension = self.file.name.split('.')[-1].lower()
            mime_types = {
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'png': 'image/png',
                'gif': 'image/gif',
                'webp': 'image/webp',
                'pdf': 'application/pdf',
            }
            mime_type = mime_types.get(file_extension, 'application/octet-stream')
            
            # Retornar en formato data URL
            return f"data:{mime_type};base64,{base64_data}"
        except Exception:
            return None


@strawberry.type
class DocumentSlotType:
    """
    Estado de un slot de documento requerido del cliente.
    Permite al frontend saber cuáles están subidos y cuáles faltan.
    """
    document_type: str = strawberry.field(name="documentType")
    label: str
    has_file: bool = strawberry.field(name="hasFile")
    document_id: Optional[int] = strawberry.field(name="documentId", default=None)
    file_url: Optional[str] = strawberry.field(name="fileUrl", default=None)
    file_base64: Optional[str] = strawberry.field(name="fileBase64", default=None)
    uploaded_at: Optional[str] = strawberry.field(name="uploadedAt", default=None)