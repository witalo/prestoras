"""
Schema para Clients app
Exporta queries y mutations relacionadas con clientes y documentos
"""
import strawberry

from .queries import ClientQuery
from .mutations import (
    create_client_document,
    update_client_document,
    create_client,
    update_client,
    assign_clients_to_collector,
)


@strawberry.type
class ClientMutation:
    """
    Mutations relacionadas con clientes y documentos
    """
    create_client = create_client
    update_client = update_client
    create_client_document = create_client_document
    update_client_document = update_client_document
    assign_clients_to_collector = assign_clients_to_collector


__all__ = ['ClientQuery', 'ClientMutation']
