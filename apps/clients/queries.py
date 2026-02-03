"""
Queries GraphQL para Clients usando Strawberry
"""
import re
import strawberry
from typing import List, Optional
from strawberry.types import Info
from django.db.models import Q, F, Case, When, Value, IntegerField
from django.db.models.functions import Length

from .models import Client, ClientDocument
from .types import ClientType, ClientDocumentType


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
        Obtener lista de clientes
        
        Filtros:
        - company_id: Empresa (requerido)
        - zone_id: Filtrar por zona (opcional)
        - classification: Filtrar por clasificación (PUNCTUAL, REGULAR, DEFAULTING, SEVERELY_DEFAULTING)
        - is_active: Filtrar por estado activo/inactivo
        """
        queryset = Client.objects.filter(company_id=company_id)
        
        if zone_id:
            queryset = queryset.filter(zone_id=zone_id)
        
        if classification:
            queryset = queryset.filter(classification=classification)
        
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        
        return list(queryset.select_related('company', 'zone').prefetch_related('documents'))
    
    @strawberry.field
    def client(self, info: Info, client_id: int) -> Optional[ClientType]:
        """
        Obtener un cliente por ID
        """
        try:
            return Client.objects.select_related('company', 'zone').prefetch_related('documents').get(id=client_id)
        except Client.DoesNotExist:
            return None
    
    @strawberry.field
    def client_by_dni(self, info: Info, dni: str, company_id: int) -> Optional[ClientType]:
        """
        Obtener un cliente por DNI y empresa
        """
        try:
            return Client.objects.select_related('company', 'zone').prefetch_related('documents').get(
                dni=dni,
                company_id=company_id
            )
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
        Obtener clientes asignados a las zonas de un cobrador
        
        Retorna los clientes que están en las zonas asignadas al cobrador.
        """
        from apps.users.models import User
        
        try:
            collector = User.objects.get(id=collector_id, company_id=company_id)
            zone_ids = collector.zones.values_list('id', flat=True)
            
            queryset = Client.objects.filter(
                company_id=company_id,
                zone_id__in=zone_ids,
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
        
        # Base queryset con select_related para evitar N+1
        base_qs = Client.objects.filter(
            company_id=company_id,
            is_active=True
        ).select_related('company', 'zone')
        
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