"""
Schema para Payments app
Exporta queries y mutations relacionadas con pagos
"""
import strawberry

from .queries import PaymentQuery
from .mutations import create_payment, update_payment


@strawberry.type
class PaymentMutation:
    """
    Mutations relacionadas con pagos
    """
    create_payment = create_payment
    update_payment = update_payment


__all__ = ['PaymentQuery', 'PaymentMutation']
