"""
Mutations GraphQL para Clients usando Strawberry
Incluye creación y actualización de clientes y documentos con imágenes
"""
import strawberry
import base64
from typing import List, Optional
from decimal import Decimal
from django.core.files.base import ContentFile
from django.db import transaction
from strawberry.types import Info

from .models import Client, ClientDocument, ClientCollector, DOCUMENT_TYPE_CHOICES, REQUIRED_DOCUMENT_TYPES
from .types import ClientType, ClientDocumentType, DocumentSlotType
from apps.companies.models import Company
from apps.zones.models import Zone
from prestoras.utils_auth import get_current_user_from_info


@strawberry.type
class CreateClientDocumentResult:
    """Resultado de crear un documento de cliente"""
    success: bool
    message: str
    document: Optional[ClientDocumentType] = None


@strawberry.type
class UpdateClientDocumentResult:
    """Resultado de actualizar un documento de cliente"""
    success: bool
    message: str
    document: Optional[ClientDocumentType] = None


@strawberry.mutation
def create_client_document(
    info: Info,
    client_id: int,
    document_type: str,
    file_base64: str,
    description: Optional[str] = None
) -> CreateClientDocumentResult:
    """
    Mutation para crear un documento de cliente (DNI, recibo, etc.)
    
    Args:
        client_id: ID del cliente
        document_type: Tipo de documento (DNI, RECEIPT, ADDITIONAL, CONTRACT, OTHER)
        file_base64: Archivo en formato base64 (data:image/jpeg;base64,... o solo base64)
        description: Descripción opcional del documento
    
    Retorna el documento creado con su URL y base64.
    """
    current_user = get_current_user_from_info(info)
    if not current_user:
        return CreateClientDocumentResult(success=False, message="No autorizado.", document=None)
    try:
        # Validar que el cliente exista
        try:
            client = Client.objects.get(id=client_id)
        except Client.DoesNotExist:
            return CreateClientDocumentResult(
                success=False,
                message="Cliente no encontrado",
                document=None
            )
        if client.company_id != current_user.company_id:
            return CreateClientDocumentResult(success=False, message="Cliente no pertenece a su empresa.", document=None)
        if current_user.role == 'COLLECTOR' and not current_user.assigned_clients.filter(id=client_id).exists():
            return CreateClientDocumentResult(success=False, message="Este cliente no está en su cartera.", document=None)
        
        # Validar tipo de documento
        valid_types = [c[0] for c in DOCUMENT_TYPE_CHOICES]
        if document_type not in valid_types:
            return CreateClientDocumentResult(
                success=False,
                message=f"Tipo de documento inválido. Debe ser uno de: {', '.join(valid_types)}",
                document=None
            )
        
        # Procesar base64
        try:
            # Si viene con prefijo data:image/...;base64, extraer solo el base64
            if ',' in file_base64:
                base64_data = file_base64.split(',')[1]
            else:
                base64_data = file_base64
            
            # Decodificar base64
            file_data = base64.b64decode(base64_data)
            
            # Determinar extensión y nombre del archivo
            # Detectar tipo MIME si está en el data URL
            file_extension = 'jpg'  # Por defecto
            if ',' in file_base64:
                mime_part = file_base64.split(',')[0]
                if 'jpeg' in mime_part or 'jpg' in mime_part:
                    file_extension = 'jpg'
                elif 'png' in mime_part:
                    file_extension = 'png'
                elif 'pdf' in mime_part:
                    file_extension = 'pdf'
            
            # Generar nombre único para el archivo
            import uuid
            file_name = f"{client.dni}_{document_type.lower()}_{uuid.uuid4().hex[:8]}.{file_extension}"
            
            # Crear el documento
            document = ClientDocument(
                client=client,
                document_type=document_type,
                description=description or ''
            )
            
            # Guardar el archivo
            content_file = ContentFile(file_data, name=file_name)
            document.file.save(file_name, content_file, save=False)
            document.save()
            
            return CreateClientDocumentResult(
                success=True,
                message=f"Documento {document.get_document_type_display()} creado exitosamente",
                document=document
            )
            
        except Exception as e:
            return CreateClientDocumentResult(
                success=False,
                message=f"Error al procesar el archivo base64: {str(e)}",
                document=None
            )
    
    except Exception as e:
        return CreateClientDocumentResult(
            success=False,
            message=f"Error al crear documento: {str(e)}",
            document=None
        )


@strawberry.mutation
def update_client_document(
    info: Info,
    document_id: int,
    document_type: Optional[str] = None,
    file_base64: Optional[str] = None,
    description: Optional[str] = None
) -> UpdateClientDocumentResult:
    """
    Mutation para actualizar un documento de cliente
    
    Args:
        document_id: ID del documento a actualizar
        document_type: Tipo de documento (opcional)
        file_base64: Nuevo archivo en base64 (opcional, si se envía se actualiza)
        description: Nueva descripción (opcional)
    
    Si file_base64 es None, no se actualiza el archivo.
    Si file_base64 es string vacío "", se elimina el archivo actual.
    """
    current_user = get_current_user_from_info(info)
    if not current_user:
        return UpdateClientDocumentResult(success=False, message="No autorizado.", document=None)
    try:
        # Obtener el documento
        try:
            document = ClientDocument.objects.select_related('client').get(id=document_id)
        except ClientDocument.DoesNotExist:
            return UpdateClientDocumentResult(
                success=False,
                message="Documento no encontrado",
                document=None
            )
        if document.client.company_id != current_user.company_id:
            return UpdateClientDocumentResult(success=False, message="Documento no pertenece a su empresa.", document=None)
        if current_user.role == 'COLLECTOR' and not current_user.assigned_clients.filter(id=document.client_id).exists():
            return UpdateClientDocumentResult(success=False, message="Este cliente no está en su cartera.", document=None)
        
        # Actualizar tipo de documento si se proporciona
        if document_type is not None:
            valid_types = [c[0] for c in DOCUMENT_TYPE_CHOICES]
            if document_type not in valid_types:
                return UpdateClientDocumentResult(
                    success=False,
                    message=f"Tipo de documento inválido. Debe ser uno de: {', '.join(valid_types)}",
                    document=None
                )
            document.document_type = document_type
        
        # Actualizar descripción si se proporciona
        if description is not None:
            document.description = description
        
        # Procesar archivo si se proporciona
        if file_base64 is not None:
            if file_base64 == "":
                # Eliminar archivo actual
                if document.file:
                    document.file.delete(save=False)
                document.file = None
            else:
                try:
                    # Si viene con prefijo data:image/...;base64, extraer solo el base64
                    if ',' in file_base64:
                        base64_data = file_base64.split(',')[1]
                    else:
                        base64_data = file_base64
                    
                    # Decodificar base64
                    file_data = base64.b64decode(base64_data)
                    
                    # Determinar extensión
                    file_extension = 'jpg'
                    if ',' in file_base64:
                        mime_part = file_base64.split(',')[0]
                        if 'png' in mime_part:
                            file_extension = 'png'
                        elif 'pdf' in mime_part:
                            file_extension = 'pdf'
                    
                    # Generar nombre único
                    import uuid
                    file_name = f"{document.client.dni}_{document.document_type.lower()}_{uuid.uuid4().hex[:8]}.{file_extension}"
                    
                    # Eliminar archivo anterior si existe
                    if document.file:
                        document.file.delete(save=False)
                    
                    # Guardar nuevo archivo
                    content_file = ContentFile(file_data, name=file_name)
                    document.file.save(file_name, content_file, save=False)
                    
                except Exception as e:
                    return UpdateClientDocumentResult(
                        success=False,
                        message=f"Error al procesar el archivo base64: {str(e)}",
                        document=None
                    )
        
        # Guardar cambios
        document.save()
        
        return UpdateClientDocumentResult(
            success=True,
            message="Documento actualizado exitosamente",
            document=document
        )
    
    except Exception as e:
            return UpdateClientDocumentResult(
                success=False,
                message=f"Error al actualizar documento: {str(e)}",
                document=None
            )


# ============ UPLOAD / DELETE DOCUMENTOS (UPSERT) ============

_FILENAME_LABELS = {
    'DNI_FRONT':     'dni_frente',
    'DNI_BACK':      'dni_reverso',
    'RECEIPT_WATER': 'recibo_agua',
    'RECEIPT_LIGHT': 'recibo_luz',
    'CONTRACT':      'contrato',
    'OTHER':         'otro',
}


def _decode_base64_file(file_base64: str):
    """Decodifica un string base64 (con o sin data URL prefix). Retorna (bytes, extension)."""
    ext = 'jpg'
    if ',' in file_base64:
        header, data = file_base64.split(',', 1)
        if 'png' in header:
            ext = 'png'
        elif 'pdf' in header:
            ext = 'pdf'
        elif 'webp' in header:
            ext = 'webp'
    else:
        data = file_base64
    return base64.b64decode(data), ext


def _build_filename(client_dni: str, document_type: str, ext: str, unique: bool = False) -> str:
    """
    Genera el nombre de archivo del documento.
    Tipos requeridos → nombre fijo: 12345678_dni_frente.jpg
    Tipos adicionales → nombre con UUID: 12345678_contrato_a1b2c3d4.jpg
    """
    base = _FILENAME_LABELS.get(document_type, document_type.lower())
    if unique:
        import uuid
        return f"{client_dni}_{base}_{uuid.uuid4().hex[:8]}.{ext}"
    return f"{client_dni}_{base}.{ext}"


@strawberry.type
class UploadClientDocumentResult:
    success: bool
    message: str
    document: Optional[ClientDocumentType] = None


@strawberry.type
class DeleteClientDocumentResult:
    success: bool
    message: str


@strawberry.mutation(name="uploadClientDocument")
def upload_client_document(
    info: Info,
    client_id: int,
    document_type: str,
    file_base64: str,
    description: Optional[str] = None,
) -> UploadClientDocumentResult:
    """
    Sube (o reemplaza) un documento del cliente.

    Para los tipos requeridos (DNI_FRONT, DNI_BACK, RECEIPT_WATER, RECEIPT_LIGHT) solo
    puede existir UN documento por tipo por cliente — si ya existe se sobreescribe.
    Para CONTRACT y OTHER se permite más de uno.
    """
    current_user = get_current_user_from_info(info)
    if not current_user:
        return UploadClientDocumentResult(success=False, message="No autorizado.")

    valid_types = [c[0] for c in DOCUMENT_TYPE_CHOICES]
    if document_type not in valid_types:
        return UploadClientDocumentResult(
            success=False,
            message=f"Tipo inválido. Valores: {', '.join(valid_types)}"
        )

    try:
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        return UploadClientDocumentResult(success=False, message="Cliente no encontrado.")

    if client.company_id != current_user.company_id:
        return UploadClientDocumentResult(success=False, message="Cliente no pertenece a su empresa.")

    if current_user.role == 'COLLECTOR' and not current_user.assigned_clients.filter(id=client_id).exists():
        return UploadClientDocumentResult(success=False, message="Este cliente no está en su cartera.")

    try:
        file_data, ext = _decode_base64_file(file_base64)
    except Exception as e:
        return UploadClientDocumentResult(success=False, message=f"Error al decodificar archivo: {e}")

    with transaction.atomic():
        if document_type in REQUIRED_DOCUMENT_TYPES:
            # Nombre fijo sin UUID → siempre reemplaza el mismo archivo físico
            file_name = _build_filename(client.dni, document_type, ext, unique=False)
            content_file = ContentFile(file_data, name=file_name)
            existing = ClientDocument.objects.filter(client=client, document_type=document_type).first()
            if existing:
                if existing.file:
                    existing.file.delete(save=False)
                existing.description = description or ''
                existing.file.save(file_name, content_file, save=False)
                existing.save()
                document = existing
            else:
                document = ClientDocument(client=client, document_type=document_type, description=description or '')
                document.file.save(file_name, content_file, save=False)
                document.save()
        else:
            # CONTRACT / OTHER → nombre con UUID para no pisar anteriores
            file_name = _build_filename(client.dni, document_type, ext, unique=True)
            content_file = ContentFile(file_data, name=file_name)
            document = ClientDocument(client=client, document_type=document_type, description=description or '')
            document.file.save(file_name, content_file, save=False)
            document.save()

    label_map = dict(DOCUMENT_TYPE_CHOICES)
    return UploadClientDocumentResult(
        success=True,
        message=f"{label_map.get(document_type, document_type)} subido correctamente.",
        document=document,
    )


@strawberry.mutation(name="deleteClientDocument")
def delete_client_document(
    info: Info,
    document_id: int,
) -> DeleteClientDocumentResult:
    """Elimina un documento del cliente y su archivo físico."""
    current_user = get_current_user_from_info(info)
    if not current_user:
        return DeleteClientDocumentResult(success=False, message="No autorizado.")

    try:
        doc = ClientDocument.objects.select_related('client').get(id=document_id)
    except ClientDocument.DoesNotExist:
        return DeleteClientDocumentResult(success=False, message="Documento no encontrado.")

    if doc.client.company_id != current_user.company_id:
        return DeleteClientDocumentResult(success=False, message="No autorizado.")

    if current_user.role == 'COLLECTOR' and not current_user.assigned_clients.filter(id=doc.client_id).exists():
        return DeleteClientDocumentResult(success=False, message="Este cliente no está en su cartera.")

    if doc.file:
        doc.file.delete(save=False)
    doc.delete()
    return DeleteClientDocumentResult(success=True, message="Documento eliminado.")


# ============ MUTACIONES PARA CLIENTES ============

@strawberry.type
class CreateClientResult:
    """Resultado de crear un cliente"""
    success: bool
    message: str
    client: Optional[ClientType] = None


@strawberry.type
class UpdateClientResult:
    """Resultado de actualizar un cliente"""
    success: bool
    message: str
    client: Optional[ClientType] = None


@strawberry.mutation
def create_client(
    info: Info,
    company_id: int,
    dni: str,
    first_name: str,
    last_name: str,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    home_address: Optional[str] = None,
    business_address: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    zone_id: Optional[int] = None,
    classification: str = "REGULAR",
    notes: Optional[str] = None
) -> CreateClientResult:
    """
    Mutation para crear un nuevo cliente
    
    Args:
        company_id: ID de la empresa
        dni: DNI del cliente (8 dígitos)
        first_name: Nombres del cliente
        last_name: Apellidos del cliente
        phone: Teléfono (opcional)
        email: Correo electrónico (opcional)
        home_address: Dirección domicilio (opcional)
        business_address: Dirección negocio (opcional)
        latitude: Latitud GPS (opcional)
        longitude: Longitud GPS (opcional)
        zone_id: ID de la zona (opcional)
        classification: Clasificación del cliente (PUNCTUAL, REGULAR, DEFAULTING, SEVERELY_DEFAULTING)
        notes: Notas adicionales (opcional)
    
    Retorna el cliente creado.
    """
    current_user = get_current_user_from_info(info)
    if not current_user:
        return CreateClientResult(success=False, message="No autorizado.", client=None)
    if current_user.company_id != company_id:
        return CreateClientResult(success=False, message="No puede crear clientes de otra empresa.", client=None)
    try:
        # Validar que la empresa exista
        try:
            company = Company.objects.get(id=company_id)
        except Company.DoesNotExist:
            return CreateClientResult(
                success=False,
                message="Empresa no encontrada",
                client=None
            )
        
        # Validar que el DNI no esté duplicado en la empresa
        if Client.objects.filter(company_id=company_id, dni=dni).exists():
            return CreateClientResult(
                success=False,
                message=f"Ya existe un cliente con DNI {dni} en esta empresa",
                client=None
            )
        
        # Validar zona si se proporciona
        zone = None
        if zone_id:
            try:
                zone = Zone.objects.get(id=zone_id, company_id=company_id)
            except Zone.DoesNotExist:
                return CreateClientResult(
                    success=False,
                    message="Zona no encontrada",
                    client=None
                )
        
        # Validar clasificación
        valid_classifications = ['PUNCTUAL', 'REGULAR', 'DEFAULTING', 'SEVERELY_DEFAULTING']
        if classification not in valid_classifications:
            return CreateClientResult(
                success=False,
                message=f"Clasificación inválida. Debe ser una de: {', '.join(valid_classifications)}",
                client=None
            )
        
        # Crear el cliente
        client = Client(
            company=company,
            zone=zone,
            dni=dni,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
            home_address=home_address,
            business_address=business_address,
            latitude=latitude,
            longitude=longitude,
            classification=classification,
            notes=notes,
            is_active=True
        )
        
        client.save()
        
        return CreateClientResult(
            success=True,
            message=f"Cliente {client.full_name} creado exitosamente",
            client=client
        )
    
    except Exception as e:
        return CreateClientResult(
            success=False,
            message=f"Error al crear cliente: {str(e)}",
            client=None
        )


@strawberry.mutation
def update_client(
    info: Info,
    client_id: int,
    dni: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    home_address: Optional[str] = None,
    business_address: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    zone_id: Optional[int] = None,
    classification: Optional[str] = None,
    notes: Optional[str] = None,
    is_active: Optional[bool] = None
) -> UpdateClientResult:
    """
    Mutation para actualizar un cliente
    
    Args:
        client_id: ID del cliente a actualizar
        dni: DNI del cliente (opcional)
        first_name: Nombres (opcional)
        last_name: Apellidos (opcional)
        phone: Teléfono (opcional)
        email: Correo (opcional)
        home_address: Dirección domicilio (opcional)
        business_address: Dirección negocio (opcional)
        latitude: Latitud GPS (opcional)
        longitude: Longitud GPS (opcional)
        zone_id: ID de la zona (opcional, None para desasignar)
        classification: Clasificación (opcional)
        notes: Notas (opcional)
        is_active: Estado activo/inactivo (opcional)
    
    Retorna el cliente actualizado.
    """
    current_user = get_current_user_from_info(info)
    if not current_user:
        return UpdateClientResult(success=False, message="No autorizado.", client=None)
    try:
        # Obtener el cliente
        try:
            client = Client.objects.get(id=client_id)
        except Client.DoesNotExist:
            return UpdateClientResult(
                success=False,
                message="Cliente no encontrado",
                client=None
            )
        if client.company_id != current_user.company_id:
            return UpdateClientResult(success=False, message="No puede editar clientes de otra empresa.", client=None)
        if current_user.role == 'COLLECTOR' and not current_user.assigned_clients.filter(id=client_id).exists():
            return UpdateClientResult(success=False, message="Este cliente no está en su cartera.", client=None)
        
        # Actualizar campos si se proporcionan
        if dni is not None:
            # Validar que el DNI no esté duplicado (excepto si es el mismo cliente)
            if Client.objects.filter(company_id=client.company_id, dni=dni).exclude(id=client_id).exists():
                return UpdateClientResult(
                    success=False,
                    message=f"Ya existe otro cliente con DNI {dni} en esta empresa",
                    client=None
                )
            client.dni = dni
        
        if first_name is not None:
            client.first_name = first_name
        
        if last_name is not None:
            client.last_name = last_name
        
        if phone is not None:
            client.phone = phone
        
        if email is not None:
            client.email = email
        
        if home_address is not None:
            client.home_address = home_address
        
        if business_address is not None:
            client.business_address = business_address
        
        if latitude is not None:
            client.latitude = latitude
        
        if longitude is not None:
            client.longitude = longitude
        
        if zone_id is not None:
            if zone_id == 0:
                # Desasignar zona (None)
                client.zone = None
            else:
                # Validar y asignar zona
                try:
                    zone = Zone.objects.get(id=zone_id, company_id=client.company_id)
                    client.zone = zone
                except Zone.DoesNotExist:
                    return UpdateClientResult(
                        success=False,
                        message="Zona no encontrada",
                        client=None
                    )
        
        if classification is not None:
            valid_classifications = ['PUNCTUAL', 'REGULAR', 'DEFAULTING', 'SEVERELY_DEFAULTING']
            if classification not in valid_classifications:
                return UpdateClientResult(
                    success=False,
                    message=f"Clasificación inválida. Debe ser una de: {', '.join(valid_classifications)}",
                    client=None
                )
            client.classification = classification
        
        if notes is not None:
            client.notes = notes
        
        if is_active is not None:
            client.is_active = is_active
        
        client.save()
        
        return UpdateClientResult(
            success=True,
            message="Cliente actualizado exitosamente",
            client=client
        )
    
    except Exception as e:
        return UpdateClientResult(
            success=False,
            message=f"Error al actualizar cliente: {str(e)}",
            client=None
        )


@strawberry.type
class AssignClientsToCollectorResult:
    """Resultado de asignar clientes a un cobrador (cartera)."""
    success: bool
    message: str
    assigned_count: int = strawberry.field(name="assignedCount", default=0)


@strawberry.mutation(name="assignClientsToCollector")
def assign_clients_to_collector(
    info: Info,
    client_ids: List[int],
    collector_id: int,
    company_id: int,
    replace_existing: Optional[bool] = False
) -> AssignClientsToCollectorResult:
    """
    Asignar clientes a un cobrador (cartera). Solo administrador.
    - replace_existing: si True, reemplaza la cartera del cobrador por client_ids; si False, agrega.
    """
    user = get_current_user_from_info(info)
    if not user or user.role != 'ADMIN':
        return AssignClientsToCollectorResult(
            success=False,
            message="Solo un administrador puede asignar cartera.",
            assigned_count=0
        )
    if user.company_id != company_id:
        return AssignClientsToCollectorResult(
            success=False,
            message="Empresa no coincide.",
            assigned_count=0
        )
    from apps.users.models import User
    try:
        collector = User.objects.get(id=collector_id, company_id=company_id, role='COLLECTOR')
    except User.DoesNotExist:
        return AssignClientsToCollectorResult(
            success=False,
            message="Cobrador no encontrado.",
            assigned_count=0
        )
    if not client_ids:
        return AssignClientsToCollectorResult(
            success=True,
            message="No hay clientes para asignar.",
            assigned_count=0
        )
    # Validar que todos los clientes sean de la empresa
    clients = list(Client.objects.filter(id__in=client_ids, company_id=company_id, is_active=True))
    if len(clients) != len(client_ids):
        return AssignClientsToCollectorResult(
            success=False,
            message="Algunos clientes no existen o no pertenecen a la empresa.",
            assigned_count=0
        )
    with transaction.atomic():
        if replace_existing:
            ClientCollector.objects.filter(collector=collector).delete()
        assigned = 0
        for client in clients:
            _, created = ClientCollector.objects.get_or_create(
                client=client,
                collector=collector,
                defaults={'assigned_by': user}
            )
            if created:
                assigned += 1
        return AssignClientsToCollectorResult(
            success=True,
            message=f"Se asignaron {assigned} cliente(s) al cobrador.",
            assigned_count=assigned
        )


@strawberry.type
class RemoveClientsFromCollectorResult:
    """Resultado de quitar clientes de la cartera de un cobrador."""
    success: bool
    message: str
    removed_count: int = strawberry.field(name="removedCount", default=0)


@strawberry.mutation(name="removeClientsFromCollector")
def remove_clients_from_collector(
    info: Info,
    client_ids: List[int],
    collector_id: int,
    company_id: int,
) -> RemoveClientsFromCollectorResult:
    """
    Quitar clientes de la cartera de un cobrador. Solo administrador.
    """
    user = get_current_user_from_info(info)
    if not user or user.role != 'ADMIN':
        return RemoveClientsFromCollectorResult(
            success=False,
            message="Solo un administrador puede modificar la cartera.",
            removed_count=0
        )
    if user.company_id != company_id:
        return RemoveClientsFromCollectorResult(
            success=False,
            message="Empresa no coincide.",
            removed_count=0
        )
    from apps.users.models import User
    try:
        collector = User.objects.get(id=collector_id, company_id=company_id, role='COLLECTOR')
    except User.DoesNotExist:
        return RemoveClientsFromCollectorResult(
            success=False,
            message="Cobrador no encontrado.",
            removed_count=0
        )
    removed, _ = ClientCollector.objects.filter(
        collector=collector,
        client_id__in=client_ids
    ).delete()
    return RemoveClientsFromCollectorResult(
        success=True,
        message=f"Se quitaron {removed} cliente(s) de la cartera.",
        removed_count=removed
    )
