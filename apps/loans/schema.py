"""
Schema para Loans app (exportar queries y mutations)
"""
import strawberry
from .queries import LoanQuery
from .mutations import (
    create_loan,
    update_loan,
    update_loan_penalty,
    activate_loan_penalty,
    refinance_loan,
    admin_adjust_loan,
    delete_loan
)


@strawberry.type
class LoanMutation:
    """
    Mutations relacionadas con préstamos
    """
    create_loan = create_loan
    update_loan = update_loan
    update_loan_penalty = update_loan_penalty
    activate_loan_penalty = activate_loan_penalty
    refinance_loan = refinance_loan
    admin_adjust_loan = admin_adjust_loan
    delete_loan = delete_loan


__all__ = ['LoanQuery', 'LoanMutation']
