"""
Serviço para enforcement de políticas de congelamento.
"""

from datetime import datetime
from typing import List, Optional
import structlog
from kubernetes import client as k8s_client

from ..config.settings import PolicySettings
from ..clients.postgresql_client import PostgreSQLClient
from ..clients.redis_client import RedisClient
from ..clients.kafka_producer import KafkaProducerClient
from ..models.error_budget import ErrorBudget
from ..models.freeze_policy import FreezePolicy, FreezeEvent, FreezeAction


class PolicyEnforcer:
    """Enforcer de políticas de congelamento."""

    def __init__(
        self,
        postgresql_client: PostgreSQLClient,
        redis_client: RedisClient,
        kafka_producer: KafkaProducerClient,
        settings: PolicySettings
    ):
        self.postgresql_client = postgresql_client
        self.redis_client = redis_client
        self.kafka_producer = kafka_producer
        self.settings = settings
        self.logger = structlog.get_logger(__name__)

        # Kubernetes clients
        self.k8s_core_v1 = k8s_client.CoreV1Api()
        self.k8s_apps_v1 = k8s_client.AppsV1Api()

    async def evaluate_policies(self, budget: ErrorBudget) -> List[FreezeEvent]:
        """Avalia políticas para um budget."""
        events_created = []

        # Buscar políticas ativas para o serviço
        policies = await self.postgresql_client.list_policies(enabled_only=True)

        for policy in policies:
            # Verificar se política aplica a este serviço
            if not self._policy_applies_to_service(policy, budget.service_name):
                continue

            # Verificar freezes ativos para esta política
            active_freezes = await self.postgresql_client.get_active_freezes(
                service_name=budget.service_name
            )
            policy_freeze_active = any(
                f.policy_id == policy.policy_id for f in active_freezes
            )

            # Avaliar se deve acionar freeze
            if policy.should_trigger(budget) and not policy_freeze_active:
                event = await self.trigger_freeze(policy, budget)
                events_created.append(event)
                self.logger.info(
                    "freeze_triggered",
                    policy_id=policy.policy_id,
                    service=budget.service_name,
                    budget_remaining=budget.error_budget_remaining
                )

            # Avaliar se deve descongelar
            elif policy.should_unfreeze(budget) and policy_freeze_active:
                for freeze in active_freezes:
                    if freeze.policy_id == policy.policy_id:
                        await self.resolve_freeze(freeze, budget)
                        self.logger.info(
                            "freeze_resolved",
                            event_id=freeze.event_id,
                            service=budget.service_name,
                            budget_remaining=budget.error_budget_remaining
                        )

        return events_created

    async def trigger_freeze(
        self,
        policy: FreezePolicy,
        budget: ErrorBudget
    ) -> FreezeEvent:
        """Aciona freeze."""
        # Passo 1: Criar FreezeEvent
        event = FreezeEvent(
            policy_id=policy.policy_id,
            slo_id=budget.slo_id,
            service_name=budget.service_name,
            action=policy.actions[0],  # Primeira ação
            trigger_reason=f"Error budget below {policy.trigger_threshold_percent}%",
            budget_remaining_percent=budget.error_budget_remaining,
            burn_rate=budget.burn_rates[0].rate if budget.burn_rates else 0,
            active=True
        )

        # Passo 2: Persistir evento
        await self.postgresql_client.create_freeze_event(event)

        # Passo 3: Aplicar freeze no Kubernetes
        await self._apply_kubernetes_freeze(policy, event)

        # Passo 4: Cachear status
        await self.redis_client.cache_freeze_status(budget.service_name, True)

        # Passo 5: Publicar evento Kafka
        await self.kafka_producer.publish_freeze_event(event, "activated")

        return event

    async def resolve_freeze(
        self,
        event: FreezeEvent,
        budget: ErrorBudget
    ) -> bool:
        """Resolve freeze."""
        # Passo 1: Atualizar evento no PostgreSQL
        success = await self.postgresql_client.resolve_freeze_event(event.event_id)
        if not success:
            return False

        # Passo 2: Remover freeze do Kubernetes
        await self._remove_kubernetes_freeze(event)

        # Passo 3: Atualizar cache Redis
        await self.redis_client.cache_freeze_status(event.service_name, False)

        # Passo 4: Publicar evento Kafka
        event.resolved_at = datetime.utcnow()
        event.active = False
        await self.kafka_producer.publish_freeze_event(event, "resolved")

        return True

    async def get_active_freezes(
        self,
        service_name: Optional[str] = None
    ) -> List[FreezeEvent]:
        """Busca freezes ativos."""
        return await self.postgresql_client.get_active_freezes(service_name)

    async def is_frozen(self, service_name: str) -> bool:
        """Verifica se serviço está congelado."""
        # Tentar cache Redis
        cached_status = await self.redis_client.get_freeze_status(service_name)
        if cached_status is not None:
            return cached_status

        # Fallback para PostgreSQL
        active_freezes = await self.postgresql_client.get_active_freezes(service_name)
        is_frozen = len(active_freezes) > 0

        # Cachear para próximas consultas
        await self.redis_client.cache_freeze_status(service_name, is_frozen)

        return is_frozen

    async def _apply_kubernetes_freeze(
        self,
        policy: FreezePolicy,
        event: FreezeEvent
    ) -> None:
        """Aplica freeze no Kubernetes."""
        annotations = policy.to_kubernetes_annotation()
        annotations["neural-hive.io/freeze-event-id"] = event.event_id

        try:
            if policy.scope.value == "NAMESPACE":
                # Anotar namespace
                await self._annotate_namespace(policy.target, annotations)

            elif policy.scope.value == "SERVICE":
                # Anotar deployments/statefulsets do serviço
                await self._annotate_service_resources(
                    event.service_name,
                    annotations
                )

            elif policy.scope.value == "GLOBAL":
                # Anotar todos os namespaces neural-hive-*
                await self._annotate_global(annotations)

            self.logger.info(
                "kubernetes_freeze_applied",
                scope=policy.scope.value,
                target=policy.target,
                event_id=event.event_id
            )

        except Exception as e:
            self.logger.error(
                "kubernetes_freeze_apply_failed",
                error=str(e),
                event_id=event.event_id
            )
            raise

    async def _remove_kubernetes_freeze(self, event: FreezeEvent) -> None:
        """Remove freeze do Kubernetes."""
        try:
            # Buscar recursos com annotation freeze-event-id
            # Simplificado: buscar por service_name
            await self._remove_annotations_from_service(event.service_name)

            self.logger.info(
                "kubernetes_freeze_removed",
                service=event.service_name,
                event_id=event.event_id
            )

        except Exception as e:
            self.logger.error(
                "kubernetes_freeze_remove_failed",
                error=str(e),
                event_id=event.event_id
            )

    async def _annotate_namespace(
        self,
        namespace: str,
        annotations: dict
    ) -> None:
        """Adiciona annotations a um namespace."""
        try:
            ns = self.k8s_core_v1.read_namespace(namespace)
            if not ns.metadata.annotations:
                ns.metadata.annotations = {}
            ns.metadata.annotations.update(annotations)
            self.k8s_core_v1.patch_namespace(namespace, ns)

            self.logger.debug("namespace_annotated", namespace=namespace)

        except Exception as e:
            self.logger.warning(
                "namespace_annotation_failed",
                namespace=namespace,
                error=str(e)
            )

    async def _annotate_service_resources(
        self,
        service_name: str,
        annotations: dict
    ) -> None:
        """Adiciona annotations aos recursos de um serviço."""
        try:
            # Buscar deployments com label app=service_name
            deployments = self.k8s_apps_v1.list_deployment_for_all_namespaces(
                label_selector=f"app={service_name}"
            )

            for deploy in deployments.items:
                if not deploy.metadata.annotations:
                    deploy.metadata.annotations = {}
                deploy.metadata.annotations.update(annotations)

                self.k8s_apps_v1.patch_namespaced_deployment(
                    deploy.metadata.name,
                    deploy.metadata.namespace,
                    deploy
                )

                self.logger.debug(
                    "deployment_annotated",
                    deployment=deploy.metadata.name,
                    namespace=deploy.metadata.namespace
                )

        except Exception as e:
            self.logger.warning(
                "service_resources_annotation_failed",
                service=service_name,
                error=str(e)
            )

    async def _annotate_global(self, annotations: dict) -> None:
        """Adiciona annotations a todos os namespaces neural-hive-*."""
        try:
            namespaces = self.k8s_core_v1.list_namespace()

            for ns in namespaces.items:
                if ns.metadata.name.startswith("neural-hive-"):
                    await self._annotate_namespace(ns.metadata.name, annotations)

        except Exception as e:
            self.logger.warning("global_annotation_failed", error=str(e))

    async def _remove_annotations_from_service(self, service_name: str) -> None:
        """Remove annotations de freeze de um serviço."""
        try:
            deployments = self.k8s_apps_v1.list_deployment_for_all_namespaces(
                label_selector=f"app={service_name}"
            )

            for deploy in deployments.items:
                if deploy.metadata.annotations:
                    # Remover annotations neural-hive.io/sla-freeze*
                    annotations_to_remove = [
                        k for k in deploy.metadata.annotations.keys()
                        if k.startswith("neural-hive.io/sla-freeze") or
                           k.startswith("neural-hive.io/freeze-")
                    ]

                    for key in annotations_to_remove:
                        del deploy.metadata.annotations[key]

                    if annotations_to_remove:
                        self.k8s_apps_v1.patch_namespaced_deployment(
                            deploy.metadata.name,
                            deploy.metadata.namespace,
                            deploy
                        )

                        self.logger.debug(
                            "deployment_annotations_removed",
                            deployment=deploy.metadata.name,
                            namespace=deploy.metadata.namespace
                        )

        except Exception as e:
            self.logger.warning(
                "service_annotations_removal_failed",
                service=service_name,
                error=str(e)
            )

    def _policy_applies_to_service(
        self,
        policy: FreezePolicy,
        service_name: str
    ) -> bool:
        """Verifica se política aplica a um serviço."""
        if policy.scope.value == "GLOBAL":
            return True

        if policy.scope.value == "SERVICE":
            return policy.target == service_name or policy.target == "*"

        # NAMESPACE: verificar se serviço pertence ao namespace
        # Simplificado: assumir que service_name contém namespace
        return policy.target in service_name
