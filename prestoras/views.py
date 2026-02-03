"""
Views para el endpoint GraphQL usando Strawberry
"""
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from strawberry.django.views import GraphQLView

from .schema import schema

# Vista para GraphQL con GraphiQL habilitado en modo DEBUG
# csrf_exempt para permitir solicitudes desde Apollo/introspection
graphql_view = csrf_exempt(GraphQLView.as_view(
    schema=schema,
    graphiql=settings.DEBUG,  # Habilita GraphiQL solo en desarrollo
))
