"""
Core Metrics Classes for Neural Hive-Mind

Implementa classes de métricas específicas para cada camada/componente do Neural Hive-Mind
com suporte a exemplars, correlação distribuída e SLOs.
"""

import time
import logging
from typing import Dict, List, Optional, Any, Union, Callable
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import wraps
from contextlib import contextmanager
from threading import Lock

from .config import get_config
from .correlation import get_correlation_context, CorrelationContext
from .exemplars import get_exemplar_collector, create_exemplar_from_current_context


logger = logging.getLogger(__name__)


@dataclass
class MetricSample:
    """Representa uma amostra de métrica com timestamp e labels."""

    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: Optional[float] = None
    help_text: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class BaseMetrics(ABC):
    """Classe base para métricas Neural Hive-Mind."""

    def __init__(self, component_name: str, labels: Optional[Dict[str, str]] = None):
        """
        Inicializa métricas base.

        Args:
            component_name: Nome do componente
            labels: Labels padrão para todas as métricas
        """
        self.component_name = component_name
        self.config = get_config()
        self.exemplar_collector = get_exemplar_collector()
        self._lock = Lock()

        # Labels padrão
        self.default_labels = {
            "component": component_name,
            **self.config.default_labels,
            **(labels or {}),
        }

        # Contadores internos
        self._counters: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = {}
        self._gauges: Dict[str, float] = {}

        logger.info(f"Métricas inicializadas para componente: {component_name}")

    def _merge_labels(self, additional_labels: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Merge labels padrão com labels adicionais."""
        if additional_labels is None:
            return self.default_labels.copy()

        return {**self.default_labels, **additional_labels}

    def _create_metric_name(self, metric_type: str, operation: str = "") -> str:
        """Cria nome padronizado para métrica."""
        base_name = f"neural_hive_{self.component_name.lower()}"

        if operation:
            return f"{base_name}_{operation}_{metric_type}"
        else:
            return f"{base_name}_{metric_type}"

    def record_counter(
        self,
        name: str,
        value: float = 1.0,
        labels: Optional[Dict[str, str]] = None,
        help_text: Optional[str] = None,
        create_exemplar: bool = True,
    ):
        """
        Registra contador.

        Args:
            name: Nome da métrica
            value: Valor a incrementar
            labels: Labels adicionais
            help_text: Texto de ajuda
            create_exemplar: Se deve criar exemplar
        """
        metric_name = self._create_metric_name("total", name)
        final_labels = self._merge_labels(labels)

        # Atualizar contador interno
        label_key = str(sorted(final_labels.items()))
        with self._lock:
            self._counters[f"{metric_name}_{label_key}"] = (
                self._counters.get(f"{metric_name}_{label_key}", 0) + value
            )

        # Criar exemplar se habilitado
        if create_exemplar and self.config.is_exemplar_enabled():
            create_exemplar_from_current_context(
                metric_name=metric_name,
                value=self._counters[f"{metric_name}_{label_key}"],
                labels=final_labels,
            )

        logger.debug(f"Counter registrado: {metric_name} = {value} {final_labels}")

    def record_histogram(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
        buckets: Optional[List[float]] = None,
        help_text: Optional[str] = None,
        create_exemplar: bool = True,
    ):
        """
        Registra histograma.

        Args:
            name: Nome da métrica
            value: Valor observado
            labels: Labels adicionais
            buckets: Buckets do histograma
            help_text: Texto de ajuda
            create_exemplar: Se deve criar exemplar
        """
        metric_name = self._create_metric_name("duration_seconds", name)
        final_labels = self._merge_labels(labels)

        # Adicionar ao histograma interno
        label_key = str(sorted(final_labels.items()))
        hist_key = f"{metric_name}_{label_key}"

        with self._lock:
            if hist_key not in self._histograms:
                self._histograms[hist_key] = []
            self._histograms[hist_key].append(value)

        # Criar exemplar se habilitado
        if create_exemplar and self.config.is_exemplar_enabled():
            create_exemplar_from_current_context(
                metric_name=metric_name,
                value=value,
                labels=final_labels,
            )

        logger.debug(f"Histogram registrado: {metric_name} = {value} {final_labels}")

    def record_gauge(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
        help_text: Optional[str] = None,
        create_exemplar: bool = False,  # Gauges raramente precisam de exemplars
    ):
        """
        Registra gauge.

        Args:
            name: Nome da métrica
            value: Valor atual
            labels: Labels adicionais
            help_text: Texto de ajuda
            create_exemplar: Se deve criar exemplar
        """
        metric_name = self._create_metric_name("current", name)
        final_labels = self._merge_labels(labels)

        # Atualizar gauge interno
        label_key = str(sorted(final_labels.items()))
        with self._lock:
            self._gauges[f"{metric_name}_{label_key}"] = value

        # Criar exemplar se habilitado
        if create_exemplar and self.config.is_exemplar_enabled():
            create_exemplar_from_current_context(
                metric_name=metric_name,
                value=value,
                labels=final_labels,
            )

        logger.debug(f"Gauge registrado: {metric_name} = {value} {final_labels}")

    @contextmanager
    def time_operation(
        self,
        operation_name: str,
        labels: Optional[Dict[str, str]] = None,
        record_success: bool = True,
        success_label_key: str = "status",
    ):
        """
        Context manager para medir tempo de operação.

        Args:
            operation_name: Nome da operação
            labels: Labels adicionais
            record_success: Se deve registrar status de sucesso
            success_label_key: Nome do label para status

        Example:
            ```python
            with metrics.time_operation("process_request"):
                process_request()
            ```
        """
        start_time = time.time()
        final_labels = self._merge_labels(labels)
        error = None

        try:
            yield
        except Exception as e:
            error = e
            if record_success:
                final_labels[success_label_key] = "error"
            raise
        else:
            if record_success:
                final_labels[success_label_key] = "success"
        finally:
            duration = time.time() - start_time

            # Registrar duração
            self.record_histogram(
                name=operation_name,
                value=duration,
                labels=final_labels,
            )

            # Registrar contador de operações
            self.record_counter(
                name=f"{operation_name}_operations",
                labels=final_labels,
            )

    def time_function(
        self,
        operation_name: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None,
        record_success: bool = True,
    ):
        """
        Decorator para medir tempo de função.

        Args:
            operation_name: Nome da operação (usa nome da função se None)
            labels: Labels adicionais
            record_success: Se deve registrar status de sucesso

        Example:
            ```python
            @metrics.time_function()
            def process_data():
                pass
            ```
        """

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                op_name = operation_name or func.__name__
                with self.time_operation(op_name, labels, record_success):
                    return func(*args, **kwargs)

            return wrapper

        return decorator

    def get_current_values(self) -> Dict[str, Any]:
        """Obtém valores atuais de todas as métricas."""
        with self._lock:
            return {
                "counters": self._counters.copy(),
                "histograms": {k: list(v) for k, v in self._histograms.items()},
                "gauges": self._gauges.copy(),
            }


class NeuralHiveMetrics(BaseMetrics):
    """Métricas gerais do sistema Neural Hive-Mind."""

    def __init__(self, labels: Optional[Dict[str, str]] = None):
        super().__init__("system", labels)

    def record_request(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        duration: float,
        labels: Optional[Dict[str, str]] = None,
    ):
        """Registra métrica de request HTTP."""
        request_labels = {
            "method": method,
            "endpoint": endpoint,
            "status": str(status_code),
            **(labels or {}),
        }

        # Contador de requests
        self.record_counter("requests", labels=request_labels)

        # Duração do request
        self.record_histogram("request_duration", duration, labels=request_labels)

    def record_error(
        self,
        error_type: str,
        component: str,
        severity: str = "error",
        labels: Optional[Dict[str, str]] = None,
    ):
        """Registra erro do sistema."""
        error_labels = {
            "error_type": error_type,
            "component": component,
            "severity": severity,
            **(labels or {}),
        }

        self.record_counter("errors", labels=error_labels)

    def record_system_health(self, component: str, healthy: bool, labels: Optional[Dict[str, str]] = None):
        """Registra saúde do sistema."""
        health_labels = {
            "component": component,
            "status": "healthy" if healthy else "unhealthy",
            **(labels or {}),
        }

        self.record_gauge("health", 1.0 if healthy else 0.0, labels=health_labels)


class BarramentoMetrics(BaseMetrics):
    """Métricas específicas do Barramento Neural."""

    def __init__(self, labels: Optional[Dict[str, str]] = None):
        super().__init__("barramento", labels)

    def record_message_routing(
        self,
        source_component: str,
        target_component: str,
        message_type: str,
        success: bool,
        duration: float,
        labels: Optional[Dict[str, str]] = None,
    ):
        """Registra roteamento de mensagem."""
        routing_labels = {
            "source": source_component,
            "target": target_component,
            "message_type": message_type,
            "status": "success" if success else "error",
            **(labels or {}),
        }

        # Contador de roteamentos
        self.record_counter("routing", labels=routing_labels)

        # Duração do roteamento (SLO: ≤150ms)
        self.record_histogram("routing_duration", duration, labels=routing_labels)

    def record_throughput(self, messages_per_second: float, labels: Optional[Dict[str, str]] = None):
        """Registra throughput do barramento."""
        self.record_gauge("throughput_messages_per_second", messages_per_second, labels=labels)

    def record_queue_depth(self, queue_name: str, depth: int, labels: Optional[Dict[str, str]] = None):
        """Registra profundidade da fila."""
        queue_labels = {"queue": queue_name, **(labels or {})}
        self.record_gauge("queue_depth", float(depth), labels=queue_labels)


class CognicaoMetrics(BaseMetrics):
    """Métricas específicas da camada de Cognição."""

    def __init__(self, labels: Optional[Dict[str, str]] = None):
        super().__init__("cognicao", labels)

    def record_plan_generation(
        self,
        intent_id: str,
        plan_complexity: str,
        success: bool,
        duration: float,
        labels: Optional[Dict[str, str]] = None,
    ):
        """Registra geração de plano."""
        plan_labels = {
            "complexity": plan_complexity,
            "status": "success" if success else "error",
            **(labels or {}),
        }

        # Adicionar correlação se disponível
        context = get_correlation_context()
        if context and context.intent_id:
            plan_labels["intent_id"] = context.intent_id

        # Contador de gerações
        self.record_counter("plan_generation", labels=plan_labels)

        # Duração da geração (SLO: ≤120ms)
        self.record_histogram("plan_generation_duration", duration, labels=plan_labels)

    def record_knowledge_access(
        self,
        knowledge_type: str,
        cache_hit: bool,
        duration: float,
        labels: Optional[Dict[str, str]] = None,
    ):
        """Registra acesso ao conhecimento."""
        knowledge_labels = {
            "type": knowledge_type,
            "cache": "hit" if cache_hit else "miss",
            **(labels or {}),
        }

        self.record_counter("knowledge_access", labels=knowledge_labels)
        self.record_histogram("knowledge_access_duration", duration, labels=knowledge_labels)

    def record_reasoning_quality(self, quality_score: float, reasoning_type: str, labels: Optional[Dict[str, str]] = None):
        """Registra qualidade do raciocínio."""
        reasoning_labels = {"type": reasoning_type, **(labels or {})}
        self.record_gauge("reasoning_quality_score", quality_score, labels=reasoning_labels)


class ExperienciaMetrics(BaseMetrics):
    """Métricas específicas da camada de Experiência."""

    def __init__(self, labels: Optional[Dict[str, str]] = None):
        super().__init__("experiencia", labels)

    def record_intent_capture(
        self,
        channel: str,
        intent_type: str,
        success: bool,
        duration: float,
        confidence_score: float,
        labels: Optional[Dict[str, str]] = None,
    ):
        """Registra captura de intenção."""
        intent_labels = {
            "channel": channel,
            "intent_type": intent_type,
            "status": "success" if success else "error",
            **(labels or {}),
        }

        # Contador de capturas
        self.record_counter("intent_capture", labels=intent_labels)

        # Duração da captura (SLO: ≤200ms)
        self.record_histogram("intent_capture_duration", duration, labels=intent_labels)

        # Score de confiança
        self.record_gauge("intent_confidence_score", confidence_score, labels=intent_labels)

    def record_user_interaction(
        self,
        interaction_type: str,
        user_satisfaction: float,
        duration: float,
        labels: Optional[Dict[str, str]] = None,
    ):
        """Registra interação com usuário."""
        interaction_labels = {"type": interaction_type, **(labels or {})}

        self.record_counter("user_interactions", labels=interaction_labels)
        self.record_histogram("interaction_duration", duration, labels=interaction_labels)
        self.record_gauge("user_satisfaction_score", user_satisfaction, labels=interaction_labels)

    def record_channel_health(self, channel: str, healthy: bool, response_time: float, labels: Optional[Dict[str, str]] = None):
        """Registra saúde do canal."""
        channel_labels = {"channel": channel, **(labels or {})}

        self.record_gauge("channel_health", 1.0 if healthy else 0.0, labels=channel_labels)
        self.record_gauge("channel_response_time", response_time, labels=channel_labels)


class OrquestracaoMetrics(BaseMetrics):
    """Métricas específicas da camada de Orquestração."""

    def __init__(self, labels: Optional[Dict[str, str]] = None):
        super().__init__("orquestracao", labels)

    def record_workflow_execution(
        self,
        workflow_id: str,
        workflow_type: str,
        success: bool,
        duration: float,
        steps_count: int,
        labels: Optional[Dict[str, str]] = None,
    ):
        """Registra execução de workflow."""
        workflow_labels = {
            "workflow_type": workflow_type,
            "status": "success" if success else "error",
            **(labels or {}),
        }

        self.record_counter("workflow_executions", labels=workflow_labels)
        self.record_histogram("workflow_duration", duration, labels=workflow_labels)
        self.record_gauge("workflow_steps_count", float(steps_count), labels=workflow_labels)

    def record_resource_allocation(
        self,
        resource_type: str,
        allocated_amount: float,
        requested_amount: float,
        labels: Optional[Dict[str, str]] = None,
    ):
        """Registra alocação de recursos."""
        resource_labels = {"type": resource_type, **(labels or {})}

        self.record_gauge("resource_allocated", allocated_amount, labels=resource_labels)
        self.record_gauge("resource_requested", requested_amount, labels=resource_labels)

        # Calcular utilização
        utilization = (allocated_amount / requested_amount) * 100 if requested_amount > 0 else 0
        self.record_gauge("resource_utilization_percent", utilization, labels=resource_labels)

    def record_coordination_event(
        self,
        event_type: str,
        components_involved: int,
        success: bool,
        labels: Optional[Dict[str, str]] = None,
    ):
        """Registra evento de coordenação."""
        coord_labels = {
            "event_type": event_type,
            "status": "success" if success else "error",
            **(labels or {}),
        }

        self.record_counter("coordination_events", labels=coord_labels)
        self.record_gauge("coordination_components_count", float(components_involved), labels=coord_labels)


class ExecucaoMetrics(BaseMetrics):
    """Métricas específicas da camada de Execução."""

    def __init__(self, labels: Optional[Dict[str, str]] = None):
        super().__init__("execucao", labels)

    def record_task_execution(
        self,
        task_type: str,
        priority: str,
        success: bool,
        duration: float,
        labels: Optional[Dict[str, str]] = None,
    ):
        """Registra execução de tarefa."""
        task_labels = {
            "task_type": task_type,
            "priority": priority,
            "status": "success" if success else "error",
            **(labels or {}),
        }

        self.record_counter("task_executions", labels=task_labels)
        self.record_histogram("task_duration", duration, labels=task_labels)

    def record_action_completion(
        self,
        action_type: str,
        success: bool,
        retries: int,
        labels: Optional[Dict[str, str]] = None,
    ):
        """Registra conclusão de ação."""
        action_labels = {
            "action_type": action_type,
            "status": "success" if success else "error",
            **(labels or {}),
        }

        self.record_counter("action_completions", labels=action_labels)
        self.record_gauge("action_retries_count", float(retries), labels=action_labels)

    def record_performance_metrics(
        self,
        cpu_usage: float,
        memory_usage: float,
        disk_io: float,
        labels: Optional[Dict[str, str]] = None,
    ):
        """Registra métricas de performance."""
        self.record_gauge("cpu_usage_percent", cpu_usage, labels=labels)
        self.record_gauge("memory_usage_percent", memory_usage, labels=labels)
        self.record_gauge("disk_io_bytes_per_second", disk_io, labels=labels)


class ResilienciaMetrics(BaseMetrics):
    """Métricas específicas da camada de Resiliência."""

    def __init__(self, labels: Optional[Dict[str, str]] = None):
        super().__init__("resiliencia", labels)

    def record_failure_detection(
        self,
        failure_type: str,
        component: str,
        severity: str,
        detection_time: float,
        labels: Optional[Dict[str, str]] = None,
    ):
        """Registra detecção de falha."""
        failure_labels = {
            "failure_type": failure_type,
            "component": component,
            "severity": severity,
            **(labels or {}),
        }

        self.record_counter("failure_detections", labels=failure_labels)
        self.record_histogram("failure_detection_time", detection_time, labels=failure_labels)

    def record_recovery_action(
        self,
        recovery_type: str,
        success: bool,
        duration: float,
        attempts: int,
        labels: Optional[Dict[str, str]] = None,
    ):
        """Registra ação de recuperação."""
        recovery_labels = {
            "recovery_type": recovery_type,
            "status": "success" if success else "error",
            **(labels or {}),
        }

        self.record_counter("recovery_actions", labels=recovery_labels)
        self.record_histogram("recovery_duration", duration, labels=recovery_labels)
        self.record_gauge("recovery_attempts_count", float(attempts), labels=recovery_labels)

    def record_system_availability(
        self,
        component: str,
        availability_percent: float,
        labels: Optional[Dict[str, str]] = None,
    ):
        """Registra disponibilidade do sistema."""
        availability_labels = {"component": component, **(labels or {})}
        self.record_gauge("availability_percent", availability_percent, labels=availability_labels)

    def record_circuit_breaker_state(
        self,
        circuit_name: str,
        state: str,  # "closed", "open", "half-open"
        failure_count: int,
        labels: Optional[Dict[str, str]] = None,
    ):
        """Registra estado do circuit breaker."""
        circuit_labels = {
            "circuit": circuit_name,
            "state": state,
            **(labels or {}),
        }

        # Converter estado para valor numérico
        state_value = {"closed": 0, "half-open": 1, "open": 2}.get(state, -1)

        self.record_gauge("circuit_breaker_state", float(state_value), labels=circuit_labels)
        self.record_gauge("circuit_breaker_failures", float(failure_count), labels=circuit_labels)