"""
Schema principal GraphQL usando Strawberry
Combina todas las queries y mutations de las apps

Cada app tiene su propio schema que exporta sus queries y mutations.
Este schema principal solo los combina.
"""
import strawberry

# Importar schemas de cada app (cada app maneja su propia lógica)
from apps.companies.schema import CompanyQuery, CompanyMutation
from apps.users.schema import UserQuery, UserMutation
from apps.clients.schema import ClientQuery, ClientMutation
from apps.loans.schema import LoanQuery, LoanMutation
from apps.zones.schema import ZoneQuery, ZoneMutation
from apps.payments.schema import PaymentQuery, PaymentMutation


# Combinar todas las queries usando herencia múltiple
@strawberry.type
class Query(CompanyQuery, UserQuery, ClientQuery, LoanQuery, ZoneQuery, PaymentQuery):
    """
    Query principal que combina todas las queries de las apps
    """
    pass


# Combinar todas las mutations usando herencia múltiple
@strawberry.type
class Mutation(CompanyMutation, UserMutation, ClientMutation, LoanMutation, ZoneMutation, PaymentMutation):
    """
    Mutation principal que combina todas las mutations de las apps
    
    Cada app tiene su propia clase Mutation:
    - CompanyMutation: mutations de empresas
    - UserMutation: mutations de usuarios
    - ClientMutation: mutations de clientes
    - LoanMutation: mutations de préstamos
    - ZoneMutation: mutations de zonas
    - PaymentMutation: mutations de pagos
    Se combinan aquí mediante herencia múltiple.
    """
    pass


# Crear el schema completo
schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
)
