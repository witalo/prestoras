"""
Views para el endpoint GraphQL usando Strawberry
"""
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from strawberry.django.views import GraphQLView

from .schema import schema, Query
from .utils_auth import get_user_from_jwt


def get_context(request, response):
    """Contexto GraphQL: request + usuario actual desde JWT (para scope admin/cobrador)."""
    from apps.users.models import User
    from apps.users.mutations import _is_within_schedule
    auth = request.META.get('HTTP_AUTHORIZATION') or ''
    token_provided = auth.startswith('Bearer ')
    ctx = {'request': request, 'response': response, 'user': None, 'token_provided': token_provided, 'schedule_blocked': False}
    payload = get_user_from_jwt(request)
    if payload and payload.get('type') == 'user':
        try:
            user = User.objects.get(id=payload['user_id'])
            if _is_within_schedule(user):
                ctx['user'] = user
            else:
                # Cobrador fuera de su horario permitido: se trata como sesión expirada
                # en cualquier request, aunque su JWT siga vigente.
                ctx['schedule_blocked'] = True
        except (User.DoesNotExist, KeyError, TypeError):
            pass
    return ctx


class PrestorasGraphQLView(GraphQLView):
    """Root value para que los resolvers de Query reciban self (instancia)."""
    def get_root_value(self, request):
        return Query()


# Vista para GraphQL con GraphiQL habilitado en modo DEBUG
# csrf_exempt para permitir solicitudes desde Apollo/introspection
graphql_view = csrf_exempt(PrestorasGraphQLView.as_view(
    schema=schema,
    graphiql=settings.DEBUG,
    get_context=get_context,
))
