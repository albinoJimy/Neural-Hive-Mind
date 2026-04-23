"""
Context Manager Service

Serviço centralizado para gestão de contexto de decisão no Context Layer.
Responsabilidades:
- Criar RichContext a partir de múltiplas fontes
- Cachear contextos para performance
- Gerenciar lifecycle de contextos
- Integrar com serviços externos (SystemState, Security, etc.)
"""

import asyncio
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from neural_hive_context.models import (
    RichContext,
    IntentContext,
    SystemContext,
    TemporalContext,
    SecurityContext,
    ConversationContext,
    WorkflowClassification,
)
from neural_hive_context.interfaces import IContextManager, IWorkflowClassifier


class ContextManagerService(IContextManager):
    """
    Serviço de gerenciamento de contexto.

    Implementa cache LRU, coleta de sinais em paralelo,
    e gerenciamento de lifecycle de contextos.
    """

    def __init__(
        self,
        workflow_classifier: IWorkflowClassifier,
        system_state_client=None,
        security_client=None,
        cache_ttl_seconds: int = 300,
        max_cache_size: int = 1000,
    ):
        """
        Inicializa o Context Manager.

        Args:
            workflow_classifier: Classificador de workflow
            system_state_client: Cliente opcional para estado do sistema
            security_client: Cliente opcional para verificação de segurança
            cache_ttl_seconds: TTL do cache em segundos (default: 5 min)
            max_cache_size: Tamanho máximo do cache LRU
        """
        self.workflow_classifier = workflow_classifier
        self.system_state_client = system_state_client
        self.security_client = security_client
        self.cache_ttl_seconds = cache_ttl_seconds
        self.max_cache_size = max_cache_size

        # Cache LRU simples
        self._cache: Dict[str, tuple[RichContext, datetime]] = {}
        self._cache_lock = asyncio.Lock()

    async def create_context(
        self,
        intent_text: str,
        intent_id: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None,
    ) -> RichContext:
        """
        Cria RichContext completo a partir do intent do usuário.

        Coleta sinais de múltiplas fontes em paralelo para performance.

        Args:
            intent_text: Texto do intent do usuário
            intent_id: ID único do intent
            user_id: ID do usuário (opcional)
            conversation_id: ID da conversa (opcional)
            additional_context: Contexto adicional (opcional)

        Returns:
            RichContext com todas as dimensões preenchidas
        """
        # Verificar cache primeiro
        cache_key = f"{intent_id}:{user_id or 'anon'}"
        cached = await self._get_from_cache(cache_key)
        if cached:
            return cached

        # Coletar sinais em paralelo
        semantic_features = {}
        if additional_context and "semantic_features" in additional_context:
            semantic_features = additional_context["semantic_features"]

        intent_context = IntentContext(
            raw_text=intent_text,
            intent_id=intent_id,
            user_id=user_id,
            semantic_features=semantic_features,
        )

        # Buscar sinais externos em paralelo
        system_task = self._fetch_system_context()
        temporal_task = asyncio.create_task(self._build_temporal_context())
        security_task = asyncio.create_task(self._fetch_security_context(intent_text))
        conversation_task = asyncio.create_task(
            self._build_conversation_context(conversation_id, user_id)
        )

        # Aguardar todas as tarefas
        system, temporal, security, conversation = await asyncio.gather(
            system_task,
            temporal_task,
            security_task,
            conversation_task,
            return_exceptions=True,
        )

        # Tratar exceções individualmente
        if isinstance(system, BaseException):
            system = SystemContext()  # Fallback para contexto vazio
        if isinstance(temporal, BaseException):
            temporal = self._build_temporal_context_sync()
        if isinstance(security, BaseException):
            security = SecurityContext()
        if isinstance(conversation, BaseException):
            conversation = ConversationContext()

        # Criar RichContext
        context_id = additional_context.get("context_id") if additional_context else None
        if not context_id:
            context_id = f"ctx-{intent_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

        rich_context = RichContext(
            intent=intent_context,
            system=system,
            temporal=temporal,
            security=security,
            conversation=conversation,
            context_id=context_id,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # Salvar no cache
        await self._save_to_cache(cache_key, rich_context)

        return rich_context

    async def classify_workflow(self, context: RichContext) -> WorkflowClassification:
        """
        Classifica o workflow baseado no RichContext.

        Args:
            context: RichContext com todas as dimensões

        Returns:
            WorkflowClassification com decisão e justificativa
        """
        return await self.workflow_classifier.classify(context)

    async def create_and_classify(
        self,
        intent_text: str,
        intent_id: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None,
    ) -> tuple[RichContext, WorkflowClassification]:
        """
        Cria contexto e classifica workflow em uma única chamada.

        Args:
            intent_text: Texto do intent do usuário
            intent_id: ID único do intent
            user_id: ID do usuário (opcional)
            conversation_id: ID da conversa (opcional)
            additional_context: Contexto adicional (opcional)

        Returns:
            Tupla (RichContext, WorkflowClassification)
        """
        context = await self.create_context(
            intent_text=intent_text,
            intent_id=intent_id,
            user_id=user_id,
            conversation_id=conversation_id,
            additional_context=additional_context,
        )

        classification = await self.classify_workflow(context)

        return context, classification

    async def enrich_cognitive_plan(
        self,
        cognitive_plan: Dict[str, Any],
        context: RichContext,
        classification: WorkflowClassification,
    ) -> Dict[str, Any]:
        """
        Enriquece CognitivePlan com campos do Context Layer.

        Args:
            cognitive_plan: CognitivePlan base (dict)
            context: RichContext da decisão
            classification: WorkflowClassification resultante

        Returns:
            CognitivePlan enriquecido com campos de workflow
        """
        # WorkflowType é str ou Enum, tratar ambos
        workflow_type_value = (
            classification.workflow_type.value
            if hasattr(classification.workflow_type, "value")
            else classification.workflow_type
        )

        enriched = cognitive_plan.copy()
        enriched.update({
            "workflow_type": workflow_type_value,
            "context_id": context.context_id,
            "workflow_confidence": classification.confidence,
            "workflow_reasoning": classification.reasoning,
        })
        return enriched

    async def _fetch_system_context(self) -> SystemContext:
        """Busca contexto do sistema do cliente externo."""
        if self.system_state_client:
            try:
                state = await self.system_state_client.get_current_state()
                return SystemContext(
                    active_workflows=state.get("active_workflows", 0),
                    affected_services=state.get("affected_services", []),
                    resource_utilization=state.get("resource_utilization", {}),
                    system_load=state.get("system_load", 0.0),
                )
            except Exception as e:
                # Fallback para contexto vazio
                return SystemContext()
        return SystemContext()

    async def _fetch_security_context(self, intent_text: str) -> SecurityContext:
        """Busca contexto de segurança do cliente externo."""
        if self.security_client:
            try:
                sec_data = await self.security_client.analyze_intent(intent_text)
                return SecurityContext(
                    risk_level=sec_data.get("risk_level", "none"),
                    requires_approval=sec_data.get("requires_approval", False),
                    guardrails=sec_data.get("guardrails", []),
                )
            except Exception:
                return SecurityContext()
        return SecurityContext()

    async def _build_temporal_context(self) -> TemporalContext:
        """Constrói contexto temporal."""
        now = datetime.now(timezone.utc)
        hour = now.hour
        weekday = now.weekday()

        # Determinar time of day
        if 6 <= hour < 12:
            time_of_day = "morning"
        elif 12 <= hour < 18:
            time_of_day = "afternoon"
        elif 18 <= hour < 22:
            time_of_day = "evening"
        else:
            time_of_day = "night"

        # Determinar day of week
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_of_week = days[weekday]

        # Business hours: Mon-Fri, 8-18
        is_business_hours = weekday < 5 and 8 <= hour < 18

        return TemporalContext(
            current_time=now.isoformat(),
            time_of_day=time_of_day,
            day_of_week=day_of_week,
            is_business_hours=is_business_hours,
        )

    def _build_temporal_context_sync(self) -> TemporalContext:
        """Versão síncrona para fallback."""
        return asyncio.create_task(self._build_temporal_context()).result()

    async def _build_conversation_context(
        self, conversation_id: Optional[str], user_id: Optional[str]
    ) -> ConversationContext:
        """Constrói contexto de conversação."""
        return ConversationContext(
            conversation_id=conversation_id,
            user_id=user_id,
            turn_count=0,  # TODO: buscar de storage se disponível
            has_escalation=False,
        )

    async def _get_from_cache(self, key: str) -> Optional[RichContext]:
        """Busca contexto do cache."""
        async with self._cache_lock:
            if key in self._cache:
                context, timestamp = self._cache[key]
                age = (datetime.now(timezone.utc) - timestamp).total_seconds()
                if age < self.cache_ttl_seconds:
                    return context
                else:
                    # Expired, remove
                    del self._cache[key]
        return None

    async def _save_to_cache(self, key: str, context: RichContext) -> None:
        """Salva contexto no cache com LRU eviction."""
        async with self._cache_lock:
            # Evict oldest if full
            if len(self._cache) >= self.max_cache_size:
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
                del self._cache[oldest_key]

            self._cache[key] = (context, datetime.now(timezone.utc))

    async def clear_cache(self) -> None:
        """Limpa todo o cache."""
        async with self._cache_lock:
            self._cache.clear()

    async def get_cache_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do cache."""
        async with self._cache_lock:
            return {
                "size": len(self._cache),
                "max_size": self.max_cache_size,
                "ttl_seconds": self.cache_ttl_seconds,
            }
