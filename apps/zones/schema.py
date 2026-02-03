"""
Schema para Zones app
Exporta queries y mutations relacionadas con zonas
"""
import strawberry

from .queries import ZoneQuery
from .mutations import create_zone, update_zone


@strawberry.type
class ZoneMutation:
    """
    Mutations relacionadas con zonas
    """
    create_zone = create_zone
    update_zone = update_zone


__all__ = ['ZoneQuery', 'ZoneMutation']
