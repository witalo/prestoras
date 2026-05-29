"""
Schema para Companies app
Exporta queries y mutations relacionadas con empresas
"""
import strawberry

from .queries import CompanyQuery
from .mutations import company_login, create_loan_type, update_loan_type, delete_loan_type


@strawberry.type
class CompanyMutation:
    """
    Mutations relacionadas con empresas
    """
    company_login = company_login
    create_loan_type = create_loan_type
    update_loan_type = update_loan_type
    delete_loan_type = delete_loan_type


__all__ = ['CompanyQuery', 'CompanyMutation']
