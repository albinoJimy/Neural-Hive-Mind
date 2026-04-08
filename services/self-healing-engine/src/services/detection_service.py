"""
Detection Service para Self-Healing Engine.

Detecta problemas que requerem remediação automática:
- Deadlocks em workflows
- Memory leaks em pods
- Outros incidentes que necessitam intervenção
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

from neural_hive_observability import get_tracer

logger = structlog.get_logger()
_tracer = get_tracer()

# Helper para spans que funcionam mesmo sem tracer configurado
def _start_span(name):
    """Inicia um span OTEL, ou noop context se tracer indisponível."""
    if _tracer is None:
        from contextlib import nullcontext
        return nullcontext()
    return _tracer.start_as_current_span(name)

# Helper para set_attribute seguro
def _set_span_attr(span, key, value):
    """Define atributo no span apenas se span não é noop."""
    if span is not None and hasattr(span, 'set_attribute'):
        span.set_attribute(key, value)


class IncidentType(Enum):
    """Tipos de incidentes detectados."""

    DEADLOCK = "deadlock"
    MEMORY_LEAK = "memory_leak"
    KAFKA_LAG = "kafka_lag"
    DATABASE_CONNECTION = "database_connection"
    POD_CRASH_LOOP = "pod_crash_loop"


class Severity(Enum):
    """Níveis de severidade."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class DeadlockStatus:
    """Resultado de detecção de deadlock."""

    workflow_id: str
    has_deadlock: bool
    stuck_duration_seconds: int = 0
    suspected_tickets: List[str] = field(default_factory=list)
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "workflow_id": self.workflow_id,
            "has_deadlock": self.has_deadlock,
            "stuck_duration_seconds": self.stuck_duration_seconds,
            "suspected_tickets": self.suspected_tickets,
            "detected_at": self.detected_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class MemoryStatus:
    """Resultado de detecção de memory leak."""

    pod_name: str
    namespace: str
    has_leak: bool
    usage_bytes: int
    usage_percent: float
    limit_bytes: int
    duration_above_threshold_seconds: int = 0
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    container_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "pod_name": self.pod_name,
            "namespace": self.namespace,
            "has_leak": self.has_leak,
            "usage_bytes": self.usage_bytes,
            "usage_percent": self.usage_percent,
            "limit_bytes": self.limit_bytes,
            "duration_above_threshold_seconds": self.duration_above_threshold_seconds,
            "detected_at": self.detected_at.isoformat(),
            "container_name": self.container_name,
            "metadata": self.metadata,
        }


@dataclass
class RemediationTrigger:
    """Trigger para execução de remediação."""

    incident_type: str
    severity: str
    detected_at: datetime
    workflow_id: Optional[str] = None
    pod_name: Optional[str] = None
    namespace: Optional[str] = None
    service_name: Optional[str] = None
    consumer_group: Optional[str] = None
    topic: Optional[str] = None
    connection_string: Optional[str] = None
    playbook_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "incident_type": self.incident_type,
            "severity": self.severity,
            "detected_at": self.detected_at.isoformat(),
            "workflow_id": self.workflow_id,
            "pod_name": self.pod_name,
            "namespace": self.namespace,
            "service_name": self.service_name,
            "consumer_group": self.consumer_group,
            "topic": self.topic,
            "connection_string": self.connection_string,
            "playbook_name": self.playbook_name,
            "metadata": self.metadata,
        }


class DetectionService:
    """
    Serviço de detecção de incidentes para Self-Healing.

    Detecta problemas automaticamente e dispara remediação.
    """

    def __init__(
        self,
        orchestrator_client=None,
        k8s_core_v1=None,
        k8s_custom_api=None,
        redis_client=None,
        health_monitor=None,
        memory_threshold_percent: float = 90.0,
        memory_duration_seconds: int = 300,
        workflow_timeout_seconds: int = 1800,
        lag_threshold: int = 10000,
        memory_history_ttl_seconds: int = 86400,  # 24 horas
    ):
        """
        Inicializa o DetectionService.

        Args:
            orchestrator_client: Cliente gRPC do Orchestrator
            k8s_core_v1: Cliente Kubernetes CoreV1Api
            k8s_custom_api: Cliente Kubernetes CustomObjectsApi (para metrics)
            redis_client: Cliente Redis para historico de memoria (opcional)
            health_monitor: HealthMonitor para verificações de saúde
            memory_threshold_percent: Percentual de memória para alerta
            memory_duration_seconds: Tempo acima do threshold para considerar leak
            workflow_timeout_seconds: Tempo sem progresso para considerar deadlock
            lag_threshold: Lag de Kafka para alerta
            memory_history_ttl_seconds: TTL de historico no Redis
        """
        self.orchestrator_client = orchestrator_client
        self.k8s_core_v1 = k8s_core_v1
        self.k8s_custom_api = k8s_custom_api
        self.redis_client = redis_client
        self.health_monitor = health_monitor
        self.memory_threshold_percent = memory_threshold_percent
        self.memory_duration_seconds = memory_duration_seconds
        self.workflow_timeout_seconds = workflow_timeout_seconds
        self.lag_threshold = lag_threshold
        self.memory_history_ttl_seconds = memory_history_ttl_seconds

        # Histórico em memória (fallback se Redis indisponível)
        self._memory_history: Dict[str, List[datetime]] = {}

        # Chave Redis para historico de memoria
        self._redis_memory_key_prefix = "self_healing:memory_history"

    async def _store_memory_reading(
        self, key: str, timestamp: datetime, usage_bytes: int, usage_percent: float
    ) -> bool:
        """
        Armazena leitura de memoria no Redis.

        Args:
            key: Chave unica do pod (namespace/pod/container)
            timestamp: Timestamp da leitura
            usage_bytes: Uso de memoria em bytes
            usage_percent: Percentual de uso

        Returns:
            True se armazenado com sucesso
        """
        if not self.redis_client:
            return False

        try:
            redis_key = f"{self._redis_memory_key_prefix}:{key}"
            timestamp_str = timestamp.isoformat()

            # Formato: timestamp|usage_bytes|usage_percent
            value = f"{timestamp_str}|{usage_bytes}|{usage_percent}"

            # Adicionar ao sorted set com score = timestamp unix
            score = timestamp.timestamp()
            await self.redis_client.zadd(redis_key, {value: score})

            # Definir TTL
            await self.redis_client.expire(redis_key, self.memory_history_ttl_seconds)

            # Limpar entradas muito antigas
            cutoff = timestamp.timestamp() - (self.memory_duration_seconds * 2)
            await self.redis_client.zremrangebyscore(redis_key, 0, cutoff)

            return True
        except Exception as e:
            logger.warning("detection_service.redis_store_failed", key=key, error=str(e))
            return False

    async def _get_memory_history(
        self, key: str, since_seconds: int = 3600
    ) -> List[Dict[str, Any]]:
        """
        Obtem historico de memoria do Redis.

        Args:
            key: Chave unica do pod
            since_seconds: Buscar historico desde este tempo atras

        Returns:
            Lista de leituras com timestamp, usage_bytes, usage_percent
        """
        if not self.redis_client:
            return []

        try:
            redis_key = f"{self._redis_memory_key_prefix}:{key}"
            now = datetime.now(timezone.utc)
            min_score = (now - timedelta(seconds=since_seconds)).timestamp()
            max_score = now.timestamp()

            # Obter entradas do sorted set
            results = await self.redis_client.zrangebyscore(
                redis_key, min_score, max_score, withscores=False
            )

            history = []
            for result in results:
                if isinstance(result, bytes):
                    result = result.decode()
                parts = result.split("|")
                if len(parts) == 3:
                    history.append({
                        "timestamp": parts[0],
                        "usage_bytes": int(parts[1]),
                        "usage_percent": float(parts[2]),
                    })

            return history
        except Exception as e:
            logger.warning("detection_service.redis_get_failed", key=key, error=str(e))
            return []

    async def _get_memory_history_stats(
        self, key: str
    ) -> Dict[str, Any]:
        """
        Obtem estatisticas do historico de memoria.

        Args:
            key: Chave unica do pod

        Returns:
            Dict com count, avg_bytes, avg_percent, max_bytes, max_percent
        """
        if not self.redis_client:
            return {}

        try:
            redis_key = f"{self._redis_memory_key_prefix}:{key}"
            results = await self.redis_client.zrange(redis_key, 0, -1, withscores=False)

            if not results:
                return {}

            total_bytes = 0
            max_bytes = 0
            total_percent = 0.0
            max_percent = 0.0
            count = len(results)

            for result in results:
                if isinstance(result, bytes):
                    result = result.decode()
                parts = result.split("|")
                if len(parts) == 3:
                    bytes_val = int(parts[1])
                    percent_val = float(parts[2])
                    total_bytes += bytes_val
                    max_bytes = max(max_bytes, bytes_val)
                    total_percent += percent_val
                    max_percent = max(max_percent, percent_val)

            return {
                "count": count,
                "avg_bytes": total_bytes // count if count > 0 else 0,
                "avg_percent": round(total_percent / count, 2) if count > 0 else 0,
                "max_bytes": max_bytes,
                "max_percent": round(max_percent, 2),
            }
        except Exception as e:
            logger.warning("detection_service.redis_stats_failed", key=key, error=str(e))
            return {}

    async def detect_deadlocks(self, workflow_id: str) -> DeadlockStatus:
        """
        Detecta se um workflow está em deadlock.

        Considera deadlock se:
        - Status é RUNNING mas não há progresso por > workflow_timeout_seconds
        - Tickets estão IN_PROGRESS por muito tempo

        Args:
            workflow_id: ID do workflow a verificar

        Returns:
            DeadlockStatus com resultado da detecção
        """
        with _start_span("detection.deadlock_check") as span:
            _set_span_attr(span,"neural.hive.workflow_id", workflow_id)
            _set_span_attr(span,"neural.hive.detection_type", "deadlock")

            try:
                if not self.orchestrator_client:
                    logger.warning("detection_service.no_orchestrator_client")
                    return DeadlockStatus(
                        workflow_id=workflow_id,
                        has_deadlock=False,
                        metadata={"error": "Orchestrator client not available"},
                    )

                response = await self.orchestrator_client.get_workflow_status(
                    workflow_id=workflow_id, include_tickets=True
                )

                # Se veio como mock, pode vir various formatos
                if isinstance(response, dict):
                    status = response.get("status", "")
                    last_progress = response.get("last_progress_at")
                    tickets = response.get("tickets", [])
                else:
                    # gRPC response object
                    status = getattr(response, "status", "")
                    last_progress = getattr(response, "last_progress_at", None)
                    tickets = getattr(response, "tickets", [])

                # Verificar se há progresso recente
                now = datetime.now(timezone.utc)
                stuck_duration = 0
                suspected_tickets = []

                if last_progress:
                    try:
                        if isinstance(last_progress, str):
                            progress_time = datetime.fromisoformat(last_progress.replace("Z", "+00:00"))
                        else:
                            progress_time = last_progress

                        stuck_duration = int((now - progress_time).total_seconds())
                    except Exception:
                        stuck_duration = 0

                # Verificar tickets presos
                for ticket in tickets:
                    if isinstance(ticket, dict):
                        ticket_status = ticket.get("status")
                        ticket_id = ticket.get("ticket_id")
                        updated_at = ticket.get("updated_at")
                    else:
                        ticket_status = getattr(ticket, "status", None)
                        ticket_id = getattr(ticket, "ticket_id", None)
                        updated_at = getattr(ticket, "updated_at", None)

                    if ticket_status == "IN_PROGRESS" and updated_at:
                        try:
                            if isinstance(updated_at, str):
                                ticket_time = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                            else:
                                ticket_time = updated_at

                            ticket_stuck = (now - ticket_time).total_seconds()
                            if ticket_stuck > 1800:  # 30 minutos
                                suspected_tickets.append(ticket_id)
                        except Exception:
                            pass

                has_deadlock = status == "RUNNING" and stuck_duration >= self.workflow_timeout_seconds

                # Adicionar atributos ao span
                _set_span_attr(span,"neural.hive.has_deadlock", str(has_deadlock))
                _set_span_attr(span,"neural.hive.stuck_duration_seconds", stuck_duration)
                _set_span_attr(span,"neural.hive.suspected_ticket_count", len(suspected_tickets))

                return DeadlockStatus(
                    workflow_id=workflow_id,
                    has_deadlock=has_deadlock,
                    stuck_duration_seconds=stuck_duration,
                    suspected_tickets=suspected_tickets,
                    metadata={"workflow_status": status, "ticket_count": len(tickets)},
                )

            except Exception as e:
                logger.error(
                    "detection_service.deadlock_check_failed", workflow_id=workflow_id, error=str(e)
                )
                return DeadlockStatus(
                    workflow_id=workflow_id, has_deadlock=False, metadata={"error": str(e)}
                )

    async def detect_memory_leak(
        self,
        pod_name: str,
        namespace: str,
        memory_limit_bytes: int,
        container_name: Optional[str] = None,
        check_duration_seconds: int = 0,
    ) -> MemoryStatus:
        """
        Detecta se um pod tem memory leak.

        Considera leak se:
        - Uso de memória > threshold por > memory_duration_seconds

        Args:
            pod_name: Nome do pod
            namespace: Namespace Kubernetes
            memory_limit_bytes: Limite de memória em bytes
            container_name: Nome do container (opcional)
            check_duration_seconds: Duração acima do threshold

        Returns:
            MemoryStatus com resultado da detecção
        """
        with _start_span("detection.memory_leak_check") as span:
            _set_span_attr(span,"neural.hive.pod_name", pod_name)
            _set_span_attr(span,"neural.hive.namespace", namespace)
            _set_span_attr(span,"neural.hive.detection_type", "memory_leak")

            try:
                # Obter métricas do pod via Kubernetes Metrics API
                if self.k8s_custom_api:
                    metrics = await self._get_pod_metrics(pod_name, namespace)
                else:
                    logger.warning("detection_service.no_k8s_metrics_api")
                    return MemoryStatus(
                        pod_name=pod_name,
                        namespace=namespace,
                        has_leak=False,
                        usage_bytes=0,
                        usage_percent=0.0,
                        limit_bytes=memory_limit_bytes,
                        metadata={"error": "Metrics API not available"},
                    )

                usage_bytes = 0
                target_container = container_name

                for container in metrics.get("containers", []):
                    c_name = container.get("name")
                    if container_name is None or c_name == container_name:
                        mem_str = container.get("usage", {}).get("memory", "0")
                        usage_bytes = self._parse_memory_bytes(mem_str)
                    target_container = c_name
                    break

                usage_percent = (
                    (usage_bytes / memory_limit_bytes) * 100 if memory_limit_bytes > 0 else 0
                )

                # Verificar se está acima do threshold
                above_threshold = usage_percent >= self.memory_threshold_percent

                has_leak = False
                duration_above = 0
                now = datetime.now(timezone.utc)

                if above_threshold:
                    key = f"{namespace}/{pod_name}/{target_container or 'main'}"

                    # Armazenar leitura no Redis (se disponível)
                    if self.redis_client:
                        await self._store_memory_reading(
                            key=key,
                            timestamp=now,
                            usage_bytes=usage_bytes,
                            usage_percent=usage_percent,
                        )

                        # Obter historico do Redis
                        history = await self._get_memory_history(
                            key, since_seconds=self.memory_duration_seconds * 2
                        )

                        if history:
                            first_timestamp = history[0]["timestamp"]
                            try:
                                if isinstance(first_timestamp, str):
                                    first_time = datetime.fromisoformat(
                                        first_timestamp.replace("Z", "+00:00")
                                    )
                                else:
                                    first_time = first_timestamp
                                duration_above = int((now - first_time).total_seconds())
                            except Exception:
                                duration_above = 0

                            if duration_above >= self.memory_duration_seconds:
                                has_leak = True
                        else:
                            # Fallback para historico em memoria
                            if key not in self._memory_history:
                                self._memory_history[key] = []
                            self._memory_history[key].append(now)
                            cutoff = now - timedelta(seconds=self.memory_duration_seconds * 2)
                            self._memory_history[key] = [
                                t for t in self._memory_history[key] if t > cutoff
                            ]
                            if self._memory_history[key]:
                                first_above = self._memory_history[key][0]
                                duration_above = int((now - first_above).total_seconds())
                                if duration_above >= self.memory_duration_seconds:
                                    has_leak = True
                    else:
                        # Sem Redis - usar historico em memoria
                        if key not in self._memory_history:
                            self._memory_history[key] = []

                        self._memory_history[key].append(now)

                        cutoff = now - timedelta(seconds=self.memory_duration_seconds * 2)
                        self._memory_history[key] = [t for t in self._memory_history[key] if t > cutoff]

                        if self._memory_history[key]:
                            first_above = self._memory_history[key][0]
                            duration_above = int((now - first_above).total_seconds())

                            if duration_above >= self.memory_duration_seconds:
                                has_leak = True

                # Obter estatisticas do historico (se Redis disponivel)
                history_stats = {}
                if self.redis_client:
                    history_stats = await self._get_memory_history_stats(
                        f"{namespace}/{pod_name}/{target_container or 'main'}"
                    )

                # Adicionar atributos ao span
                _set_span_attr(span,"neural.hive.has_leak", str(has_leak))
                _set_span_attr(span,"neural.hive.usage_percent", round(usage_percent, 2))
                _set_span_attr(span,"neural.hive.duration_above_threshold", duration_above)

                return MemoryStatus(
                pod_name=pod_name,
                namespace=namespace,
                has_leak=has_leak,
                usage_bytes=usage_bytes,
                usage_percent=round(usage_percent, 2),
                limit_bytes=memory_limit_bytes,
                duration_above_threshold_seconds=duration_above,
                container_name=target_container,
                metadata={
                    "history_samples": history_stats.get("count", 0),
                    "avg_usage_bytes": history_stats.get("avg_bytes", 0),
                    "avg_usage_percent": history_stats.get("avg_percent", 0),
                    "max_usage_bytes": history_stats.get("max_bytes", 0),
                    "max_usage_percent": history_stats.get("max_percent", 0),
                } if history_stats else {},
            )

            except Exception as e:
                logger.error(
                    "detection_service.memory_leak_check_failed",
                    pod_name=pod_name,
                    namespace=namespace,
                    error=str(e),
                )
                return MemoryStatus(
                    pod_name=pod_name,
                    namespace=namespace,
                    has_leak=False,
                    usage_bytes=0,
                    usage_percent=0.0,
                    limit_bytes=memory_limit_bytes,
                    metadata={"error": str(e)},
                )

    async def _get_pod_metrics(self, pod_name: str, namespace: str) -> Dict[str, Any]:
        """Obtém métricas de um pod via Kubernetes Metrics API."""
        try:
            # Usar Metrics API v1beta1
            metrics = await self.k8s_custom_api.get_namespaced_custom_object(
                name=pod_name,
                namespace=namespace,
                group="metrics.k8s.io",
                version="v1beta1",
                plural="pods",
            )
            return metrics
        except Exception as e:
            logger.warning("detection_service.metrics_api_failed", error=str(e))
            # Retornar estrutura vazia
            return {"containers": []}

    def _parse_memory_bytes(self, mem_str: str) -> int:
        """Converte string de memória Kubernetes para bytes."""
        mem_str = mem_str.strip().upper()

        units = {
            "KI": 1024,
            "MI": 1024**2,
            "GI": 1024**3,
            "TI": 1024**4,
            "K": 1000,
            "M": 1000**2,
            "G": 1000**3,
            "T": 1000**4,
        }

        for suffix, multiplier in units.items():
            if mem_str.endswith(suffix):
                number = float(mem_str[: -len(suffix)])
                return int(number * multiplier)

        # Sem sufixo = bytes
        return int(mem_str)

    async def trigger_remediation(
        self, trigger: RemediationTrigger, playbook_executor=None
    ) -> Dict[str, Any]:
        """
        Dispara remediação baseado em um trigger detectado.

        Args:
            trigger: Trigger de remediação
            playbook_executor: Executor de playbooks

        Returns:
            Resultado da execução da remediação
        """
        with _start_span("remediation.trigger") as span:
            _set_span_attr(span,"neural.hive.incident_type", trigger.incident_type)
            _set_span_attr(span,"neural.hive.severity", trigger.severity.value if isinstance(trigger.severity, Severity) else trigger.severity)

            logger.info(
                "detection_service.triggering_remediation",
                incident_type=trigger.incident_type,
                severity=trigger.severity,
            )

            try:
                # Selecionar playbook baseado no tipo de incidente
                playbook_name = trigger.playbook_name or self._get_playbook_for_incident(
                    trigger.incident_type
                )

                if not playbook_executor:
                    logger.warning("detection_service.no_playbook_executor")
                    return {"success": False, "error": "Playbook executor not available"}

                # Validar estrutura do playbook antes da execução
                if hasattr(playbook_executor, "validate_playbook_structure"):
                    validation = playbook_executor.validate_playbook_structure(playbook_name)
                    if not validation.get("valid"):
                        logger.error(
                            "detection_service.playbook_validation_failed",
                            playbook=playbook_name,
                            errors=validation.get("errors"),
                        )
                        return {
                            "success": False,
                            "error": "Playbook structure validation failed",
                            "playbook": playbook_name,
                            "validation_errors": validation.get("errors"),
                        }

                    logger.debug(
                        "detection_service.playbook_validation_passed",
                        playbook=playbook_name,
                        action_count=validation.get("action_count"),
                    )

                # Preparar contexto
                context = {
                    "incident_type": trigger.incident_type,
                    "severity": trigger.severity,
                    "detected_at": trigger.detected_at.isoformat(),
                }

                if trigger.workflow_id:
                    context["workflow_id"] = trigger.workflow_id
                if trigger.pod_name:
                    context["pod_name"] = trigger.pod_name
                    context["namespace"] = trigger.namespace
                if trigger.service_name:
                    context["service_name"] = trigger.service_name
                if trigger.consumer_group:
                    context["consumer_group"] = trigger.consumer_group
                    context["topic"] = trigger.topic

                # Executar playbook
                result = await playbook_executor.execute_playbook(
                    playbook_name=playbook_name, context=context
                )

                logger.info(
                    "detection_service.remediation_completed",
                    playbook=playbook_name,
                    success=result.get("success"),
                )

                # Adicionar resultado ao span
                _set_span_attr(span,"neural.hive.remediation_success", str(result.get("success", False)))
                _set_span_attr(span,"neural.hive.playbook_name", playbook_name)

                return result

            except Exception as e:
                logger.error(
                    "detection_service.remediation_failed",
                    incident_type=trigger.incident_type,
                    error=str(e),
                )
                _set_span_attr(span,"neural.hive.remediation_error", str(e))
                return {"success": False, "error": str(e)}

    def _get_playbook_for_incident(self, incident_type: str) -> str:
        """Retorna o playbook apropriado para o tipo de incidente."""
        playbooks = {
            "deadlock": "deadlock_recovery",
            "memory_leak": "memory_leak_recovery",
            "kafka_lag": "kafka_lag_recovery",
            "database_connection": "database_connection_recovery",
            "pod_crash_loop": "restart_pod",
        }
        return playbooks.get(incident_type, "generic_recovery")

    async def detect_kafka_lag(
        self,
        consumer_group: str,
        topic: str,
        threshold: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Detecta lag excessivo em consumidor Kafka.

        Args:
            consumer_group: Grupo de consumidores
            topic: Tópico Kafka
            threshold: Limite de lag (usa default se não especificado)

        Returns:
            Dict com resultado da detecção
        """
        with _start_span("detection.kafka_lag_check") as span:
            _set_span_attr(span, "neural.hive.consumer_group", consumer_group)
            _set_span_attr(span, "neural.hive.detection_type", "kafka_lag")

            if not self.health_monitor:
                return {
                    "has_lag": False,
                    "lag": 0,
                    "threshold": threshold or 10000,
                    "consumer_group": consumer_group,
                    "topic": topic,
                    "error": "HealthMonitor not available",
                }

            try:
                lag_status = await self.health_monitor.check_kafka_consumer_lag(
                    consumer_group=consumer_group,
                    topic=topic,
                    threshold=threshold,
                )

                has_lag = not lag_status.within_threshold and lag_status.lag > 0

                _set_span_attr(span, "neural.hive.has_lag", str(has_lag))
                _set_span_attr(span, "neural.hive.lag", lag_status.lag)

                return {
                    "has_lag": has_lag,
                    "lag": lag_status.lag,
                    "threshold": lag_status.threshold,
                    "consumer_group": consumer_group,
                    "topic": topic,
                    "partitions": lag_status.partitions,
                }

            except Exception as e:
                logger.error(
                    "detection_service.kafka_lag_check_failed",
                    consumer_group=consumer_group,
                    topic=topic,
                    error=str(e),
                )
                return {
                    "has_lag": False,
                    "lag": 0,
                    "threshold": threshold or 10000,
                    "consumer_group": consumer_group,
                    "topic": topic,
                    "error": str(e),
                }

    async def detect_database_connection(
        self,
        service_name: str,
        host: str,
        port: int,
        database: str,
    ) -> Dict[str, Any]:
        """
        Detecta problemas de conexão com banco de dados.

        Args:
            service_name: Nome do serviço de banco
            host: Host do banco
            port: Porta do banco
            database: Nome do banco

        Returns:
            Dict com resultado da detecção
        """
        with _start_span("detection.database_connection_check") as span:
            _set_span_attr(span, "neural.hive.service_name", service_name)
            _set_span_attr(span, "neural.hive.detection_type", "database_connection")

            if not self.health_monitor:
                return {
                    "has_connection_issue": False,
                    "service_name": service_name,
                    "connected": True,
                    "latency_ms": 0,
                    "error": "HealthMonitor not available",
                }

            try:
                conn_status = await self.health_monitor.check_database_connection(
                    service_name=service_name,
                    host=host,
                    port=port,
                    database=database,
                )

                has_issue = not conn_status.connected

                _set_span_attr(span, "neural.hive.has_issue", str(has_issue))

                return {
                    "has_connection_issue": has_issue,
                    "service_name": service_name,
                    "connected": conn_status.connected,
                    "latency_ms": conn_status.latency_ms,
                    "error": conn_status.error,
                }

            except Exception as e:
                logger.error(
                    "detection_service.database_check_failed",
                    service_name=service_name,
                    error=str(e),
                )
                return {
                    "has_connection_issue": False,
                    "service_name": service_name,
                    "connected": True,
                    "latency_ms": 0,
                    "error": str(e),
                }

    async def detect_pod_crash_loop(
        self,
        pod_name: str,
        namespace: str,
        restart_threshold: int = 3,
        time_window_minutes: int = 10,
    ) -> Dict[str, Any]:
        """
        Detecta pods em crash loop (múltiplos restarts em curto período).

        Args:
            pod_name: Nome do pod
            namespace: Namespace Kubernetes
            restart_threshold: Número de restarts para considerar crash loop
            time_window_minutes: Janela de tempo para contar restarts

        Returns:
            Dict com resultado da detecção
        """
        with _start_span("detection.crash_loop_check") as span:
            _set_span_attr(span, "neural.hive.pod_name", pod_name)
            _set_span_attr(span, "neural.hive.namespace", namespace)
            _set_span_attr(span, "neural.hive.detection_type", "pod_crash_loop")

            if not self.k8s_core_v1:
                return {
                    "has_crash_loop": False,
                    "pod_name": pod_name,
                    "namespace": namespace,
                    "restart_count": 0,
                    "error": "Kubernetes API not available",
                }

            try:
                # Obter status do pod
                pod = await self.k8s_core_v1.read_namespaced_pod(
                    name=pod_name,
                    namespace=namespace,
                )

                restart_count = pod.status.container_statuses[0].restart_count if pod.status.container_statuses else 0

                has_crash_loop = restart_count >= restart_threshold

                _set_span_attr(span, "neural.hive.has_crash_loop", str(has_crash_loop))
                _set_span_attr(span, "neural.hive.restart_count", restart_count)

                return {
                    "has_crash_loop": has_crash_loop,
                    "pod_name": pod_name,
                    "namespace": namespace,
                    "restart_count": restart_count,
                    "restart_threshold": restart_threshold,
                    "phase": pod.status.phase,
                }

            except Exception as e:
                logger.error(
                    "detection_service.crash_loop_check_failed",
                    pod_name=pod_name,
                    namespace=namespace,
                    error=str(e),
                )
                return {
                    "has_crash_loop": False,
                    "pod_name": pod_name,
                    "namespace": namespace,
                    "restart_count": 0,
                    "error": str(e),
                }

    async def run_detection_loop(
        self,
        workflows: List[str],
        pods: List[tuple[str, str]],  # (pod_name, namespace)
        interval_seconds: int = 60,
        kafka_consumer_groups: Optional[List[tuple[str, str]]] = None,  # (group, topic)
        database_checks: Optional[List[dict]] = None,  # [{"service_name", "host", "port", "database"}]
        check_crash_loops: bool = True,
    ):
        """
        Executa loop de detecção contínua.

        Args:
            workflows: Lista de workflow IDs para monitorar
            pods: Lista de tuplas (pod_name, namespace) para monitorar
            interval_seconds: Intervalo entre verificações
            kafka_consumer_groups: Lista de tuplas (consumer_group, topic) para verificar lag
            database_checks: Lista de configs para verificar conexões DB
            check_crash_loops: Se deve verificar crash loops em pods
        """
        kafka_consumer_groups = kafka_consumer_groups or []
        database_checks = database_checks or []

        logger.info(
            "detection_service.starting_loop",
            workflow_count=len(workflows),
            pod_count=len(pods),
            kafka_count=len(kafka_consumer_groups),
            db_count=len(database_checks),
        )

        while True:
            with _start_span("detection.loop_iteration") as span:
                _set_span_attr(span, "neural.hive.workflow_count", len(workflows))
                _set_span_attr(span, "neural.hive.pod_count", len(pods))
                detection_count = 0
                remediation_count = 0

                try:
                    # Verificar workflows (deadlock)
                    for workflow_id in workflows:
                        status = await self.detect_deadlocks(workflow_id)
                        detection_count += 1
                        if status.has_deadlock:
                            trigger = RemediationTrigger(
                                incident_type="deadlock",
                                severity="high",
                                detected_at=datetime.now(timezone.utc),
                                workflow_id=workflow_id,
                                metadata={"stuck_duration_seconds": status.stuck_duration_seconds},
                            )
                            await self.trigger_remediation(trigger)
                            remediation_count += 1

                    # Verificar pods (memory leak + crash loop)
                    for pod_name, namespace in pods:
                        # Memory leak check
                        limit_bytes = 1073741824  # 1GB default
                        mem_status = await self.detect_memory_leak(
                            pod_name=pod_name, namespace=namespace, memory_limit_bytes=limit_bytes
                        )
                        detection_count += 1
                        if mem_status.has_leak:
                            trigger = RemediationTrigger(
                                incident_type="memory_leak",
                                severity="medium",
                                detected_at=datetime.now(timezone.utc),
                                pod_name=pod_name,
                                namespace=namespace,
                            )
                            await self.trigger_remediation(trigger)
                            remediation_count += 1

                        # Crash loop check
                        if check_crash_loops:
                            crash_status = await self.detect_pod_crash_loop(
                                pod_name=pod_name, namespace=namespace
                            )
                            detection_count += 1
                            if crash_status["has_crash_loop"]:
                                trigger = RemediationTrigger(
                                    incident_type="pod_crash_loop",
                                    severity="high",
                                    detected_at=datetime.now(timezone.utc),
                                    pod_name=pod_name,
                                    namespace=namespace,
                                    metadata={
                                        "restart_count": crash_status["restart_count"],
                                        "restart_threshold": crash_status["restart_threshold"],
                                    },
                                )
                                await self.trigger_remediation(trigger)
                                remediation_count += 1

                    # Verificar Kafka lag
                    for consumer_group, topic in kafka_consumer_groups:
                        lag_status = await self.detect_kafka_lag(
                            consumer_group=consumer_group, topic=topic
                        )
                        detection_count += 1
                        if lag_status["has_lag"]:
                            trigger = RemediationTrigger(
                                incident_type="kafka_lag",
                                severity="warning",
                                detected_at=datetime.now(timezone.utc),
                                consumer_group=consumer_group,
                                metadata={
                                    "lag": lag_status["lag"],
                                    "topic": topic,
                                    "threshold": lag_status["threshold"],
                                },
                            )
                            await self.trigger_remediation(trigger)
                            remediation_count += 1

                    # Verificar conexões DB
                    for db_config in database_checks:
                        db_status = await self.detect_database_connection(**db_config)
                        detection_count += 1
                        if db_status["has_connection_issue"]:
                            trigger = RemediationTrigger(
                                incident_type="database_connection",
                                severity="error",
                                detected_at=datetime.now(timezone.utc),
                                service_name=db_config["service_name"],
                                metadata=db_config,
                            )
                            await self.trigger_remediation(trigger)
                            remediation_count += 1

                    _set_span_attr(span, "neural.hive.detection_count", detection_count)
                    _set_span_attr(span, "neural.hive.remediation_count", remediation_count)

                    # Sleep antes da próxima iteração, mas verificando cancelamento
                    try:
                        await asyncio.sleep(interval_seconds)
                    except asyncio.CancelledError:
                        raise

                except asyncio.CancelledError:
                    logger.info("detection_service.loop_cancelled")
                    _set_span_attr(span, "neural.hive.loop_cancelled", "true")
                    break
                except Exception as e:
                    logger.error("detection_service.loop_error", error=str(e))
                    _set_span_attr(span, "neural.hive.loop_error", str(e))
                    await asyncio.sleep(interval_seconds)
