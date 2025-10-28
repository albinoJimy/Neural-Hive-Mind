"""
Exemplar Support for Neural Hive-Mind Metrics

Implementa suporte a exemplars para correlação entre métricas e traces,
seguindo especificação OpenMetrics e integração com OpenTelemetry.
"""

import time
import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from threading import Lock
from collections import defaultdict, deque

from .config import get_config
from .correlation import get_current_correlation_context


logger = logging.getLogger(__name__)


@dataclass
class Exemplar:
    """Representa um exemplar de métrica com correlação de trace."""

    # Valores requeridos
    value: float
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)

    # Identificadores de trace
    trace_id: Optional[str] = None
    span_id: Optional[str] = None

    # Correlação Neural Hive-Mind
    intent_id: Optional[str] = None
    plan_id: Optional[str] = None
    domain: Optional[str] = None
    user_id: Optional[str] = None

    # Metadados adicionais
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validação pós-inicialização."""
        if self.timestamp <= 0:
            self.timestamp = time.time()

        # Validar trace_id e span_id se fornecidos
        if self.trace_id and len(self.trace_id) not in [16, 32]:
            logger.warning(f"trace_id com comprimento inválido: {len(self.trace_id)}")

        if self.span_id and len(self.span_id) not in [8, 16]:
            logger.warning(f"span_id com comprimento inválido: {len(self.span_id)}")

    def to_openmetrics(self) -> str:
        """Converte exemplar para formato OpenMetrics."""
        # Construir labels do exemplar
        exemplar_labels = []

        if self.trace_id:
            exemplar_labels.append(f'trace_id="{self.trace_id}"')

        if self.span_id:
            exemplar_labels.append(f'span_id="{self.span_id}"')

        # Adicionar correlação Neural Hive-Mind
        if self.intent_id:
            exemplar_labels.append(f'neural_hive_intent_id="{self.intent_id}"')

        if self.plan_id:
            exemplar_labels.append(f'neural_hive_plan_id="{self.plan_id}"')

        if self.domain:
            exemplar_labels.append(f'neural_hive_domain="{self.domain}"')

        if self.user_id:
            exemplar_labels.append(f'neural_hive_user_id="{self.user_id}"')

        # Adicionar labels customizados
        for key, value in self.labels.items():
            exemplar_labels.append(f'{key}="{value}"')

        labels_str = "{" + ",".join(exemplar_labels) + "}" if exemplar_labels else ""

        return f"# {labels_str} {self.value} {self.timestamp}"

    def to_dict(self) -> Dict[str, Any]:
        """Converte exemplar para dicionário."""
        return {
            "value": self.value,
            "timestamp": self.timestamp,
            "labels": self.labels,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "intent_id": self.intent_id,
            "plan_id": self.plan_id,
            "domain": self.domain,
            "user_id": self.user_id,
            "metadata": self.metadata,
        }


class ExemplarCollector:
    """Coletor de exemplars com armazenamento em memória e gestão de ciclo de vida."""

    def __init__(self, max_exemplars_per_metric: int = 10, max_age_seconds: int = 300):
        """
        Inicializa coletor de exemplars.

        Args:
            max_exemplars_per_metric: Número máximo de exemplars por métrica
            max_age_seconds: Idade máxima dos exemplars em segundos
        """
        self.max_exemplars_per_metric = max_exemplars_per_metric
        self.max_age_seconds = max_age_seconds
        self._exemplars: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_exemplars_per_metric))
        self._lock = Lock()

        logger.info(f"ExemplarCollector iniciado: max_exemplars={max_exemplars_per_metric}, max_age={max_age_seconds}s")

    def add_exemplar(
        self,
        metric_name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        correlation_context: Optional[Dict[str, str]] = None,
        timestamp: Optional[float] = None,
        **metadata
    ) -> Exemplar:
        """
        Adiciona exemplar para uma métrica.

        Args:
            metric_name: Nome da métrica
            value: Valor do exemplar
            labels: Labels do exemplar
            trace_id: ID do trace (se disponível)
            span_id: ID do span (se disponível)
            correlation_context: Contexto de correlação Neural Hive-Mind
            timestamp: Timestamp do exemplar (padrão: agora)
            **metadata: Metadados adicionais

        Returns:
            Exemplar criado
        """
        config = get_config()

        # Verificar se exemplars estão habilitados
        if not config.is_exemplar_enabled():
            logger.debug("Exemplars desabilitados na configuração")
            return None

        # Verificar sampling
        if not config.should_sample_exemplar():
            logger.debug("Exemplar não selecionado para amostragem")
            return None

        # Obter contexto de correlação se não fornecido
        if correlation_context is None:
            correlation_context = get_current_correlation_context()

        # Criar exemplar
        exemplar = Exemplar(
            value=value,
            timestamp=timestamp or time.time(),
            labels=labels or {},
            trace_id=trace_id,
            span_id=span_id,
            intent_id=correlation_context.get("intent_id"),
            plan_id=correlation_context.get("plan_id"),
            domain=correlation_context.get("domain"),
            user_id=correlation_context.get("user_id"),
            metadata=metadata,
        )

        # Adicionar ao coletor
        with self._lock:
            self._exemplars[metric_name].append(exemplar)

        logger.debug(f"Exemplar adicionado para métrica {metric_name}: {exemplar.to_dict()}")
        return exemplar

    def get_exemplars(self, metric_name: str) -> List[Exemplar]:
        """
        Obtém exemplars para uma métrica.

        Args:
            metric_name: Nome da métrica

        Returns:
            Lista de exemplars válidos
        """
        with self._lock:
            exemplars = list(self._exemplars.get(metric_name, []))

        # Filtrar exemplars expirados
        current_time = time.time()
        valid_exemplars = [
            ex for ex in exemplars
            if current_time - ex.timestamp <= self.max_age_seconds
        ]

        # Atualizar cache se necessário
        if len(valid_exemplars) != len(exemplars):
            with self._lock:
                self._exemplars[metric_name] = deque(valid_exemplars, maxlen=self.max_exemplars_per_metric)

        return valid_exemplars

    def get_all_exemplars(self) -> Dict[str, List[Exemplar]]:
        """Obtém todos os exemplars válidos."""
        result = {}
        for metric_name in list(self._exemplars.keys()):
            exemplars = self.get_exemplars(metric_name)
            if exemplars:
                result[metric_name] = exemplars
        return result

    def clear_exemplars(self, metric_name: Optional[str] = None):
        """
        Limpa exemplars.

        Args:
            metric_name: Nome da métrica (None para limpar todos)
        """
        with self._lock:
            if metric_name is None:
                self._exemplars.clear()
                logger.info("Todos os exemplars foram limpos")
            else:
                if metric_name in self._exemplars:
                    del self._exemplars[metric_name]
                    logger.info(f"Exemplars da métrica {metric_name} foram limpos")

    def cleanup_expired(self):
        """Remove exemplars expirados de todas as métricas."""
        current_time = time.time()
        removed_count = 0

        with self._lock:
            for metric_name in list(self._exemplars.keys()):
                exemplars = self._exemplars[metric_name]
                original_length = len(exemplars)

                # Filtrar exemplars válidos
                valid_exemplars = [
                    ex for ex in exemplars
                    if current_time - ex.timestamp <= self.max_age_seconds
                ]

                if len(valid_exemplars) != original_length:
                    self._exemplars[metric_name] = deque(valid_exemplars, maxlen=self.max_exemplars_per_metric)
                    removed_count += original_length - len(valid_exemplars)

                # Remover métricas sem exemplars
                if not valid_exemplars:
                    del self._exemplars[metric_name]

        if removed_count > 0:
            logger.debug(f"Limpeza automática removeu {removed_count} exemplar(s) expirado(s)")

    def get_stats(self) -> Dict[str, Any]:
        """Obtém estatísticas do coletor."""
        with self._lock:
            total_exemplars = sum(len(exemplars) for exemplars in self._exemplars.values())
            metrics_with_exemplars = len(self._exemplars)

        return {
            "total_exemplars": total_exemplars,
            "metrics_with_exemplars": metrics_with_exemplars,
            "max_exemplars_per_metric": self.max_exemplars_per_metric,
            "max_age_seconds": self.max_age_seconds,
        }


# Instância global do coletor
_global_collector: Optional[ExemplarCollector] = None


def get_exemplar_collector() -> ExemplarCollector:
    """Obtém instância global do coletor de exemplars."""
    global _global_collector

    if _global_collector is None:
        _global_collector = ExemplarCollector()

    return _global_collector


def create_exemplar(
    metric_name: str,
    value: float,
    labels: Optional[Dict[str, str]] = None,
    trace_id: Optional[str] = None,
    span_id: Optional[str] = None,
    **metadata
) -> Optional[Exemplar]:
    """
    Função utilitária para criar exemplar.

    Args:
        metric_name: Nome da métrica
        value: Valor do exemplar
        labels: Labels do exemplar
        trace_id: ID do trace
        span_id: ID do span
        **metadata: Metadados adicionais

    Returns:
        Exemplar criado ou None se desabilitado
    """
    collector = get_exemplar_collector()
    return collector.add_exemplar(
        metric_name=metric_name,
        value=value,
        labels=labels,
        trace_id=trace_id,
        span_id=span_id,
        **metadata
    )


def get_trace_context_from_otel():
    """
    Obtém contexto de trace do OpenTelemetry se disponível.

    Returns:
        Tupla (trace_id, span_id) ou (None, None)
    """
    try:
        from opentelemetry import trace
        from opentelemetry.trace import format_trace_id, format_span_id

        span = trace.get_current_span()
        if span is None or not span.is_recording():
            return None, None

        span_context = span.get_span_context()
        if not span_context.is_valid():
            return None, None

        trace_id = format_trace_id(span_context.trace_id)
        span_id = format_span_id(span_context.span_id)

        return trace_id, span_id

    except ImportError:
        logger.debug("OpenTelemetry não disponível para extração de contexto")
        return None, None
    except Exception as e:
        logger.warning(f"Erro ao obter contexto OpenTelemetry: {e}")
        return None, None


def create_exemplar_from_current_context(
    metric_name: str,
    value: float,
    labels: Optional[Dict[str, str]] = None,
    **metadata
) -> Optional[Exemplar]:
    """
    Cria exemplar usando contexto atual de trace e correlação.

    Args:
        metric_name: Nome da métrica
        value: Valor do exemplar
        labels: Labels do exemplar
        **metadata: Metadados adicionais

    Returns:
        Exemplar criado ou None
    """
    # Obter contexto de trace do OpenTelemetry
    trace_id, span_id = get_trace_context_from_otel()

    # Criar exemplar com contexto
    return create_exemplar(
        metric_name=metric_name,
        value=value,
        labels=labels,
        trace_id=trace_id,
        span_id=span_id,
        **metadata
    )