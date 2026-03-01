"""
Schema para Users app
Exporta queries y mutations relacionadas SOLO con usuarios
"""
import strawberry

from .queries import UserQuery
from .mutations import user_login, create_user, update_user, admin_set_password


@strawberry.type
class UserMutation:
    """
    Mutations relacionadas con usuarios
    """
    user_login = user_login
    create_user = create_user
    update_user = update_user
    admin_set_password = admin_set_password


__all__ = ['UserQuery', 'UserMutation']
