"""
Schema para Companies app
Exporta queries y mutations relacionadas con empresas
"""
import strawberry

from .queries import CompanyQuery
from .mutations import company_login


@strawberry.type
class CompanyMutation:
    """
    Mutations relacionadas con empresas
    """
    company_login = company_login


__all__ = ['CompanyQuery', 'CompanyMutation']
