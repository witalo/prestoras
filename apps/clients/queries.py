"""
Queries GraphQL para Clients usando Strawberry
Scope: admin ve todos los clientes de la empresa; cobrador solo su cartera.
"""
import logging
import re
from datetime import date as date_type, datetime
import strawberry

logger = logging.getLogger(__name__)
from typing import List, Optional
from strawberry.types import Info
from django.db.models import Q, F, Case, When, Value, IntegerField
from django.db.models.functions import Length

from .models import Client, ClientDocument
from .types import ClientType, ClientDocumentType, CollectionRouteItemType
from prestoras.utils_auth import get_current_user_from_info
from django.utils import timezone


def _scope_clients_queryset(queryset, info: Info, company_id: int):
    """Si el usuario es cobrador, restringe a su cartera y empresa."""
    user = get_current_user_from_info(info)
    if user and user.role == 'COLLECTOR':
        if user.company_id != company_id:
            return queryset.none()
        client_ids = list(user.assigned_clients.values_list('id', flat=True))
        if not client_ids:
            return queryset.none()
        return queryset.filter(id__in=client_ids)
    return queryset


@strawberry.type
class ClientQuery:
    """
    Queries relacionadas con clientes
    """
    
    @strawberry.field
    def clients(
        self,
        info: Info,
        company_id: int,
        zone_id: Optional[int] = None,
        classification: Optional[str] = None,
        is_active: Optional[bool] = True
    ) -> List[ClientType]:
        """
        Obtener lista de clientes.
        Admin: todos los de la empresa. Cobrador: solo los de su cartera.
        """
        queryset = Client.objects.filter(company_id=company_id)
        queryset = _scope_clients_queryset(queryset, info, company_id)
        
        if zone_id:
            queryset = queryset.filter(zone_id=zone_id)
        
        if classification:
            queryset = queryset.filter(classification=classification)
        
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        
        return list(queryset.select_related('company', 'zone').prefetch_related('documents'))

    @strawberry.field(name="clientsForAssignCartera")
    def clients_for_assign_cartera(
        self,
        info: Info,
        company_id: int,
        zone_id: Optional[int] = None,
        search: Optional[str] = None,
        limit: Optional[int] = 100
    ) -> List[ClientType]:
        """
        Clientes que tienen al menos un préstamo ACTIVO o DEFAULTING, para asignar cartera.
        Solo administrador. Opcional: filtrar por zona y/o búsqueda por nombre/DNI.
        """
        user = get_current_user_from_info(info)
        if not user or user.role != 'ADMIN' or user.company_id != company_id:
            return []
        from apps.loans.models import Loan
        # IDs de clientes con al menos un préstamo activo o en mora
        loan_qs = Loan.objects.filter(
            company_id=company_id,
            status__in=['ACTIVE', 'DEFAULTING']
        ).values_list('client_id', flat=True).distinct()
        client_ids = list(loan_qs)
        if not client_ids:
            return []
        queryset = Client.objects.filter(
            company_id=company_id,
            id__in=client_ids,
            is_active=True
        ).select_related('company', 'zone')
        if zone_id is not None:
            queryset = queryset.filter(zone_id=zone_id)
        search_clean = (search or '').strip()
        if len(search_clean) >= 2:
            q = (
                Q(first_name__icontains=search_clean) |
                Q(last_name__icontains=search_clean) |
                Q(dni__icontains=search_clean)
            )
            queryset = queryset.filter(q)
        return list(queryset.order_by('first_name', 'last_name')[: limit or 100])
    
    @strawberry.field
    def client(self, info: Info, client_id: int) -> Optional[ClientType]:
        """
        Obtener un cliente por ID. Cobrador solo si el cliente está en su cartera.
        """
        try:
            obj = Client.objects.select_related('company', 'zone').prefetch_related('documents').get(id=client_id)
            user = get_current_user_from_info(info)
            if user and user.role == 'COLLECTOR':
                if user.company_id != obj.company_id or not user.assigned_clients.filter(id=client_id).exists():
                    return None
            return obj
        except Client.DoesNotExist:
            return None
    
    @strawberry.field
    def client_by_dni(self, info: Info, dni: str, company_id: int) -> Optional[ClientType]:
        """
        Obtener un cliente por DNI y empresa. Cobrador solo si está en su cartera.
        """
        try:
            obj = Client.objects.select_related('company', 'zone').prefetch_related('documents').get(
                dni=dni,
                company_id=company_id
            )
            user = get_current_user_from_info(info)
            if user and user.role == 'COLLECTOR':
                if user.company_id != company_id or not user.assigned_clients.filter(id=obj.id).exists():
                    return None
            return obj
        except Client.DoesNotExist:
            return None
    
    @strawberry.field
    def clients_by_collector(
        self,
        info: Info,
        collector_id: int,
        company_id: int
    ) -> List[ClientType]:
        """
        Obtener clientes en la cartera de un cobrador (solo admin o el mismo cobrador).
        """
        from apps.users.models import User
        user = get_current_user_from_info(info)
        if user and user.role == 'COLLECTOR' and user.id != collector_id:
            return []
        try:
            collector = User.objects.get(id=collector_id, company_id=company_id)
            client_ids = list(collector.assigned_clients.values_list('id', flat=True))
            if not client_ids:
                return []
            queryset = Client.objects.filter(
                company_id=company_id,
                id__in=client_ids,
                is_active=True
            )
            return list(queryset.select_related('company', 'zone').prefetch_related('documents'))
        except User.DoesNotExist:
            return []
    
    @strawberry.field
    def client_documents(
        self,
        info: Info,
        client_id: int,
        document_type: Optional[str] = None
    ) -> List[ClientDocumentType]:
        """
        Obtener documentos de un cliente
        
        Filtros:
        - client_id: ID del cliente (requerido)
        - document_type: Tipo de documento (DNI, RECEIPT, etc.) - opcional
        """
        queryset = ClientDocument.objects.filter(client_id=client_id)
        
        if document_type:
            queryset = queryset.filter(document_type=document_type)
        
        return list(queryset.order_by('-created_at'))
    
    @strawberry.field
    def client_document(self, info: Info, document_id: int) -> Optional[ClientDocumentType]:
        """
        Obtener un documento específico por ID
        """
        try:
            return ClientDocument.objects.get(id=document_id)
        except ClientDocument.DoesNotExist:
            return None

    @strawberry.field(name="collectionRouteToday")
    def collection_route_today(
        self,
        info: Info,
        company_id: int
    ) -> List[CollectionRouteItemType]:
        """
        Cobros del día (hoy). Alias de collectionRouteByDate(companyId, hoy).
        """
        return self._collection_route_by_date_impl(info, company_id, timezone.now().date())

    @strawberry.field(name="collectionRouteByDate")
    def collection_route_by_date(
        self,
        info: Info,
        company_id: int,
        date: date_type
    ) -> List[CollectionRouteItemType]:
        """Deserializa date y delega. Para uso desde cliente que envía Date scalar."""
        return self._collection_route_by_date_impl(info, company_id, date)

    @strawberry.field(name="collectionRouteByDateStr")
    def collection_route_by_date_str(
        self,
        info: Info,
        company_id: int,
        date_str: str
    ) -> List[CollectionRouteItemType]:
        """
        Misma lógica que collectionRouteByDate pero recibe la fecha como string yyyy-MM-dd.
        Evita problemas de zona horaria o serialización del scalar Date.
        """
        logger.info("collectionRouteByDateStr llamada: company_id=%s date_str=%s", company_id, date_str)
        try:
            target_date = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            logger.warning("collectionRouteByDateStr fecha inválida: %s", date_str)
            return []
        return self._collection_route_by_date_impl(info, company_id, target_date)

    def _collection_route_by_date_impl(
        self,
        info: Info,
        company_id: int,
        target_date: date_type
    ) -> List[CollectionRouteItemType]:
        """
        Ruta de cobro por fecha: clientes con cuotas a cobrar en esa fecha,
        con monto a cobrar y estado pagado/no pagado (para lista y mapa rojo/verde).
        - Cobrador: solo sus clientes asignados (cartera).
        - Admin: todos los clientes de la empresa con cuotas pendientes esa fecha.
        Filtro: cuotas con due_date <= target_date que aún tienen saldo.
        """
        from apps.loans.models import Loan, Installment
        from apps.payments.models import Payment
        from decimal import Decimal

        user = get_current_user_from_info(info)
        if not user or user.company_id != company_id:
            logger.info("collection_route_by_date: sin usuario o empresa distinta, company_id=%s", company_id)
            return []

        if user.role == 'COLLECTOR':
            client_ids = list(user.assigned_clients.filter(is_active=True).values_list('id', flat=True))
            if not client_ids:
                return []
            loan_ids = list(Loan.objects.filter(
                company_id=company_id,
                client_id__in=client_ids,
                status__in=['ACTIVE', 'DEFAULTING']
            ).values_list('id', flat=True))
        else:
            # ADMIN: todos los préstamos activos/morosos de la empresa
            loan_ids = list(Loan.objects.filter(
                company_id=company_id,
                status__in=['ACTIVE', 'DEFAULTING']
            ).values_list('id', flat=True))
        if not loan_ids:
            logger.info("collection_route_by_date: sin préstamos activos/morosos company_id=%s date=%s", company_id, target_date)
            return []

        # Diagnóstico: cuántas cuotas hay en total para estos préstamos (sin filtrar por fecha/estado)
        total_installments = Installment.objects.filter(loan_id__in=loan_ids).count()
        # Cuotas vencidas o con vencimiento en target_date que aún tienen saldo
        installments = Installment.objects.filter(
            loan_id__in=loan_ids,
            due_date__lte=target_date,
            status__in=['PENDING', 'OVERDUE', 'PARTIALLY_PAID']
        ).select_related('loan__client')
        installments_count = installments.count()
        if installments_count == 0 and total_installments > 0:
            # Hay cuotas pero ninguna pasa el filtro: mostrar por qué
            from django.db.models import Count
            by_status = dict(Installment.objects.filter(loan_id__in=loan_ids).values('status').annotate(n=Count('id')).values_list('status', 'n'))
            max_due = Installment.objects.filter(loan_id__in=loan_ids).order_by('-due_date').values_list('due_date', flat=True).first()
            min_due = Installment.objects.filter(loan_id__in=loan_ids).order_by('due_date').values_list('due_date', flat=True).first()
            # Cuántas tienen due_date <= target (cualquier estado)
            with_due_by = Installment.objects.filter(loan_id__in=loan_ids, due_date__lte=target_date).count()
            # De esas, cuántas por estado
            by_status_on_or_before = dict(Installment.objects.filter(loan_id__in=loan_ids, due_date__lte=target_date).values('status').annotate(n=Count('id')).values_list('status', 'n'))
            logger.info("collection_route_by_date: 0 cuotas con saldo; total=%s por_status=%s min_due=%s max_due=%s con due_date<=%s: %s (por_status %s)",
                        total_installments, by_status, min_due, max_due, target_date, with_due_by, by_status_on_or_before)

        # Por cliente: monto pendiente y si pagó ese día
        per_client = {}
        for inst in installments:
            cid = inst.loan.client_id
            pending = (inst.total_amount or Decimal('0')) - (inst.paid_amount or Decimal('0'))
            if pending <= 0:
                continue
            if cid not in per_client:
                per_client[cid] = {'amount': Decimal('0'), 'client': inst.loan.client}
            per_client[cid]['amount'] += pending

        if not per_client:
            logger.info("collection_route_by_date: sin cuotas con saldo company_id=%s date=%s loans=%s installments=%s",
                        company_id, target_date, len(loan_ids), installments_count)
            return []

        # ¿Pagó ese día? (algún pago completado del cliente en target_date)
        paid_client_ids = set(
            Payment.objects.filter(
                client_id__in=per_client.keys(),
                status='COMPLETED',
                payment_date__date=target_date
            ).values_list('client_id', flat=True).distinct()
        )

        clients_qs = Client.objects.filter(
            id__in=per_client.keys(),
            company_id=company_id,
            is_active=True
        ).select_related('company', 'zone').prefetch_related('documents')
        clients_by_id = {c.id: c for c in clients_qs}

        result = []
        for cid, data in per_client.items():
            client = clients_by_id.get(cid) or data['client']
            result.append(CollectionRouteItemType(
                client=client,
                amount_to_collect=data['amount'],
                paid=(cid in paid_client_ids)
            ))
        logger.info("collection_route_by_date: OK company_id=%s date=%s clients=%s (loans=%s installments=%s)",
                    company_id, target_date, len(result), len(loan_ids), installments_count)
        return result

    @strawberry.field
    def search_clients(
        self,
        info: Info,
        search: str,
        company_id: int,
        limit: Optional[int] = 20
    ) -> List[ClientType]:
        """
        Búsqueda avanzada de clientes por DNI, nombres o apellidos
        Similar a search_products, con tolerancia a errores y optimizada para velocidad
        
        Parámetros:
        - search: Texto de búsqueda (mínimo 3 caracteres)
        - company_id: ID de la empresa
        - limit: Límite de resultados (default: 20)
        """
        # Validación mínima de 3 caracteres
        search = search.strip()
        if not search or len(search) < 3:
            return []
        
        # Limpiar búsqueda pero mantener números y espacios
        search_lower = search.lower()
        search_clean = re.sub(r'[^\w\s]', '', search_lower)
        words = search_clean.split()
        
        if not words:
            return []
        
        # Base queryset con select_related para evitar N+1 (scope: admin/cobrador)
        base_qs = Client.objects.filter(
            company_id=company_id,
            is_active=True
        ).select_related('company', 'zone')
        base_qs = _scope_clients_queryset(base_qs, info, company_id)
        
        # ESTRATEGIA POSTGRESQL CON TRIGRAM (LA MÁS POTENTE)
        # Requiere: CREATE EXTENSION pg_trgm; en PostgreSQL
        try:
            from django.contrib.postgres.search import TrigramSimilarity
            from django.db.models.functions import Concat
            
            # Búsqueda con similitud de trigramas (tolerante a errores)
            clients = base_qs.annotate(
                # Similitud en DNI
                dni_similarity=TrigramSimilarity('dni', search_lower),
                # Similitud en nombres
                first_name_similarity=TrigramSimilarity('first_name', search_lower),
                # Similitud en apellidos
                last_name_similarity=TrigramSimilarity('last_name', search_lower),
                # Similitud en nombre completo (usar Concat para concatenar correctamente)
                full_name_similarity=TrigramSimilarity(
                    Concat('first_name', Value(' '), 'last_name'),
                    search_lower
                ),
                # Score combinado (DNI tiene más peso)
                total_score=(
                    F('dni_similarity') * 4 +
                    F('first_name_similarity') * 2 +
                    F('last_name_similarity') * 2 +
                    F('full_name_similarity') * 3
                )
            ).filter(
                # Al menos 0.1 de similitud en algún campo
                Q(dni_similarity__gt=0.1) |
                Q(first_name_similarity__gt=0.1) |
                Q(last_name_similarity__gt=0.1) |
                Q(full_name_similarity__gt=0.1)
            ).order_by('-total_score')[:limit or 20]
            
            # Evaluar el queryset para verificar si hay resultados
            clients_list = list(clients)
            if clients_list:
                return clients_list
        
        except (ImportError, Exception):
            # Fallback a búsqueda sin trigrams si hay cualquier error
            pass
        
        # ESTRATEGIA FALLBACK (Sin PostgreSQL o sin extensión pg_trgm)
        
        # 1. EXACTO: Coincidencia exacta del DNI o nombre completo
        exact_q = (
            Q(dni__iexact=search) |
            Q(first_name__iexact=search) |
            Q(last_name__iexact=search)
        )
        # Si hay 2 o más palabras, también buscar coincidencia exacta de nombre completo
        if len(words) >= 2:
            exact_q |= (Q(first_name__iexact=words[0]) & Q(last_name__iexact=words[-1]))
        
        # 2. CONTIENE: La búsqueda completa está contenida
        contains_q = (
            Q(dni__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(phone__icontains=search)
        )
        
        # 3. TODAS LAS PALABRAS: Todas las palabras deben estar presentes
        all_words_q = Q()
        for word in words:
            if len(word) >= 2:  # Ignorar palabras de 1 carácter
                word_q = (
                    Q(dni__icontains=word) |
                    Q(first_name__icontains=word) |
                    Q(last_name__icontains=word) |
                    Q(phone__icontains=word)
                )
                all_words_q &= word_q
        
        # 4. ALGUNA PALABRA: Al menos una palabra coincide
        any_word_q = Q()
        for word in words:
            if len(word) >= 2:
                any_word_q |= (
                    Q(dni__icontains=word) |
                    Q(first_name__icontains=word) |
                    Q(last_name__icontains=word) |
                    Q(phone__icontains=word)
                )
        
        # 5. PREFIJO: Empieza con la primera palabra
        prefix_q = Q()
        if words:
            first = words[0]
            if len(first) >= 2:
                prefix_q = (
                    Q(dni__istartswith=first) |
                    Q(first_name__istartswith=first) |
                    Q(last_name__istartswith=first)
                )
        
        # 6. FUZZY MANUAL: Para errores de tipeo simples
        fuzzy_q = Q()
        for word in words:
            if len(word) >= 4:  # Solo palabras de 4+ caracteres
                # Quitar 1 carácter del final (error común)
                fuzzy_q |= (
                    Q(dni__icontains=word[:-1]) |
                    Q(first_name__icontains=word[:-1]) |
                    Q(last_name__icontains=word[:-1])
                )
                # Quitar 1 carácter del inicio
                fuzzy_q |= (
                    Q(dni__icontains=word[1:]) |
                    Q(first_name__icontains=word[1:]) |
                    Q(last_name__icontains=word[1:])
                )
        
        # Aplicar scoring basado en coincidencias
        clients = base_qs.annotate(
            relevance=Case(
                # Coincidencia exacta = 1000 puntos
                When(exact_q, then=Value(1000)),
                # Contiene búsqueda completa = 800 puntos
                When(contains_q, then=Value(800)),
                # Todas las palabras = 600 puntos
                When(all_words_q, then=Value(600)),
                # Empieza con primera palabra = 400 puntos
                When(prefix_q, then=Value(400)),
                # Fuzzy match = 300 puntos
                When(fuzzy_q, then=Value(300)),
                # Al menos una palabra = 200 puntos
                When(any_word_q, then=Value(200)),
                default=Value(0),
                output_field=IntegerField()
            ),
            # Bonus por longitud de coincidencia (clientes con nombres más cortos primero)
            length_bonus=Case(
                When(first_name__isnull=False, then=100 - Length('first_name') - Length('last_name')),
                default=Value(0),
                output_field=IntegerField()
            )
        ).filter(
            relevance__gt=0  # Solo resultados relevantes
        ).annotate(
            # Score final
            final_score=F('relevance') + F('length_bonus')
        ).order_by('-final_score', 'first_name', 'last_name')[:limit or 20]
        
        return list(clients)