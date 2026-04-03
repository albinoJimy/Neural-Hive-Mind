"""
Métricas Prometheus para OPA Client.

Monitoramento de operações OPA.
"""
from time import time
from typing import Any, Optional

try:
    from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

    PROMETHEUS_AVAILABLE = True
except ImportError:
    # Fallback se prometheus_client não estiver instalado
    PROMETHEUS_AVAILABLE = False

    class Counter:  # type: ignore[no-redef]
        """Mock Counter para quando Prometheus não está disponível."""

        def __init__(self, *args: Any, **kwargs: Any):
            self._value = 0

        def inc(self, amount: float = 1) -> None:
            """Incrementa contador (mock)."""
            self._value += amount

        def labels(self, *args: Any, **kwargs: Any) -> "Counter":
            """Retorna self (mock)."""
            return self

    class Gauge:  # type: ignore[no-redef]
        """Mock Gauge para quando Prometheus não está disponível."""

        def __init__(self, *args: Any, **kwargs: Any):
            self._value = 0

        def set(self, value: float) -> None:
            """Define valor (mock)."""
            self._value = value

        def labels(self, *args: Any, **kwargs: Any) -> "Gauge":
            """Retorna self (mock)."""
            return self

    class Histogram:  # type: ignore[no-redef]
        """Mock Histogram para quando Prometheus não está disponível."""

        def __init__(self, *args: Any, **kwargs: Any):
            pass

        def observe(self, amount: float) -> None:
            """Observa valor (mock)."""
            pass

        def labels(self, *args: Any, **kwargs: Any) -> "Histogram":
            """Retorna self (mock)."""
            return self

        def time(self) -> Any:
            """Retorna context manager (mock)."""
            return self


class OPAMetrics:
    """
    Métricas Prometheus para operações OPA.

    Acompanha avaliações, cache, circuit breaker e performance.

    Segue especificação INFRA-002:
    - opa_evaluations_total (counter)
    - opa_evaluation_duration_ms (histogram)
    - opa_cache_hits_total (counter)
    - opa_circuit_breaker_open (gauge)
    """

    def __init__(
        self,
        namespace: str = "opa",
        subsystem: str = "client",
        registry: Optional["CollectorRegistry"] = None,
    ):
        """
        Inicializa métricas.

        Args:
            namespace: Namespace Prometheus
            subsystem: Subsistema para labels
            registry: Registry Prometheus (opcional, cria dedicado se não fornecido)
        """
        # Criar registry dedicado se não fornecido para evitar conflitos
        if PROMETHEUS_AVAILABLE and registry is None:
            self._registry = CollectorRegistry()
        else:
            self._registry = registry

        # Preparar kwargs para métricas
        metric_kwargs = {}
        if self._registry is not None:
            metric_kwargs["registry"] = self._registry

        self._evaluations_total = Counter(
            f"{namespace}_evaluations_total",
            "Total de avaliações OPA",
            ["subsystem", "policy", "result"],
            **metric_kwargs,
        )

        self._evaluation_duration_ms = Histogram(
            f"{namespace}_evaluation_duration_milliseconds",
            "Duração da avaliação OPA em milissegundos",
            ["subsystem", "policy"],
            buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000, 5000],
            **metric_kwargs,
        )

        self._cache_hits_total = Counter(
            f"{namespace}_cache_hits_total",
            "Total de cache hits",
            ["subsystem"],
            **metric_kwargs,
        )

        self._cache_misses_total = Counter(
            f"{namespace}_cache_misses_total",
            "Total de cache misses",
            ["subsystem"],
            **metric_kwargs,
        )

        self._circuit_breaker_open = Gauge(
            f"{namespace}_circuit_breaker_open",
            "Estado do circuit breaker (1=open, 0=closed)",
            ["subsystem"],
            **metric_kwargs,
        )

        self._circuit_breaker_failures_total = Counter(
            f"{namespace}_circuit_breaker_failures_total",
            "Total de falhas que abriram circuit breaker",
            ["subsystem"],
            **metric_kwargs,
        )

        self._batch_evaluations_total = Counter(
            f"{namespace}_batch_evaluations_total",
            "Total de avaliações em lote",
            ["subsystem"],
            **metric_kwargs,
        )

        self._connection_errors_total = Counter(
            f"{namespace}_connection_errors_total",
            "Total de erros de conexão",
            ["subsystem"],
            **metric_kwargs,
        )

        self.subsystem = subsystem

    @property
    def registry(self) -> Optional["CollectorRegistry"]:
        """Retorna o registry Prometheus usado."""
        return self._registry

    def record_evaluation(self, policy: str, success: bool, duration_ms: float) -> None:
        """
        Registra avaliação OPA.

        Args:
            policy: Caminho da política
            success: Se a avaliação foi bem-sucedida
            duration_ms: Duração em milissegundos
        """
        result = "success" if success else "failure"
        self._evaluations_total.labels(subsystem=self.subsystem, policy=policy, result=result).inc()
        self._evaluation_duration_ms.labels(subsystem=self.subsystem, policy=policy).observe(
            duration_ms
        )

    def record_cache_hit(self) -> None:
        """Registra cache hit."""
        self._cache_hits_total.labels(subsystem=self.subsystem).inc()

    def record_cache_miss(self) -> None:
        """Registra cache miss."""
        self._cache_misses_total.labels(subsystem=self.subsystem).inc()

    def set_circuit_breaker_state(self, is_open: bool) -> None:
        """
        Define estado do circuit breaker.

        Args:
            is_open: True se circuit breaker está aberto
        """
        value = 1.0 if is_open else 0.0
        self._circuit_breaker_open.labels(subsystem=self.subsystem).set(value)

    def record_circuit_breaker_failure(self) -> None:
        """Registra falha que abriu circuit breaker."""
        self._circuit_breaker_failures_total.labels(subsystem=self.subsystem).inc()

    def record_batch_evaluation(self, count: int) -> None:
        """
        Registra avaliação em lote.

        Args:
            count: Número de requisições no lote
        """
        self._batch_evaluations_total.labels(subsystem=self.subsystem).inc(count)

    def record_connection_error(self) -> None:
        """Registra erro de conexão."""
        self._connection_errors_total.labels(subsystem=self.subsystem).inc()


class MetricTimer:
    """
    Context manager para medir tempo de operação.

    Uso:
        with MetricTimer(metrics, "policy/path", start_time):
            # ... operação ...
            pass
    """

    def __init__(self, metrics: OPAMetrics, policy: str):
        """
        Inicializa timer.

        Args:
            metrics: Instância de métricas
            policy: Caminho da política
        """
        self.metrics = metrics
        self.policy = policy
        self.start_time: float | None = None
        self.success: bool = True

    def __enter__(self) -> "MetricTimer":
        """Inicia timer."""
        self.start_time = time()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Finaliza timer e registra métrica."""
        if self.start_time is None:
            return

        duration_ms = (time() - self.start_time) * 1000
        success = exc_type is None
        self.metrics.record_evaluation(self.policy, success, duration_ms)
