"""
Schema para Users app
Exporta queries y mutations relacionadas SOLO con usuarios
"""
import strawberry

from .queries import UserQuery
from .mutations import user_login


@strawberry.type
class UserMutation:
    """
    Mutations relacionadas con usuarios
    """
    user_login = user_login


__all__ = ['UserQuery', 'UserMutation']
