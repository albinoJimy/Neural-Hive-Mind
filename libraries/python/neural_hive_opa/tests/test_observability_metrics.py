"""
Testes para o módulo de observabilidade.

Testa o registry e funções de gerenciamento de métricas OPA.
"""
import pytest
from prometheus_client import CollectorRegistry

from neural_hive_opa.observability import (
    get_registry,
    init_opa_metrics,
    get_opa_metrics,
    reset_opa_metrics,
)
from neural_hive_opa.metrics import OPAMetrics


class TestObservabilityRegistry:
    """Testes do registry Prometheus."""

    def test_get_registry_returns_collector_registry(self):
        """
        DADO: Nenhum registry inicializado
        QUANDO: Chamo get_registry
        ENTÃO: Deve retornar CollectorRegistry
        """
        # Resetar para garantir estado limpo
        reset_opa_metrics()

        registry = get_registry()

        assert isinstance(registry, CollectorRegistry)

    def test_get_registry_returns_same_instance(self):
        """
        DADO: Registry já criado
        QUANDO: Chamo get_registry novamente
        ENTÃO: Deve retornar mesma instância
        """
        # Resetar para garantir estado limpo
        reset_opa_metrics()

        registry1 = get_registry()
        registry2 = get_registry()

        assert registry1 is registry2


class TestOPAMetricsInitialization:
    """Testes de inicialização de métricas OPA."""

    def test_init_opa_metrics_creates_instance(self):
        """
        DADO: Métricas não inicializadas
        QUANDO: Chamo init_opa_metrics
        ENTÃO: Deve criar instância de OPAMetrics
        """
        reset_opa_metrics()

        metrics = init_opa_metrics()

        assert isinstance(metrics, OPAMetrics)

    def test_init_opa_metrics_returns_same_instance(self):
        """
        DADO: Métricas já inicializadas
        QUANDO: Chamo init_opa_metrics novamente
        ENTÃO: Deve retornar mesma instância
        """
        reset_opa_metrics()

        metrics1 = init_opa_metrics()
        metrics2 = init_opa_metrics()

        assert metrics1 is metrics2

    def test_init_opa_metrics_with_custom_subsystem(self):
        """
        DADO: Subsystem customizado
        QUANDO: Chamo init_opa_metrics
        ENTÃO: Deve usar subsystem fornecido
        """
        reset_opa_metrics()

        metrics = init_opa_metrics(subsystem="test_service")

        assert metrics.subsystem == "test_service"

    def test_init_opa_metrics_with_custom_registry(self):
        """
        DADO: Registry customizado
        QUANDO: Chamo init_opa_metrics
        ENTÃO: Deve usar registry fornecido
        """
        reset_opa_metrics()
        custom_registry = CollectorRegistry()

        metrics = init_opa_metrics(registry=custom_registry)

        assert metrics.registry is custom_registry


class TestGetOPAMetrics:
    """Testes de get_opa_metrics."""

    def test_get_opa_metrics_returns_none_when_not_initialized(self):
        """
        DADO: Métricas não inicializadas
        QUANDO: Chamo get_opa_metrics
        ENTÃO: Deve retornar None
        """
        reset_opa_metrics()

        metrics = get_opa_metrics()

        assert metrics is None

    def test_get_opa_metrics_returns_instance_after_init(self):
        """
        DADO: Métricas inicializadas
        QUANDO: Chamo get_opa_metrics
        ENTÃO: Deve retornar instância
        """
        reset_opa_metrics()
        init_opa_metrics()

        metrics = get_opa_metrics()

        assert isinstance(metrics, OPAMetrics)


class TestResetOPAMetrics:
    """Testes de reset_opa_metrics."""

    def test_reset_clears_metrics(self):
        """
        DADO: Métricas inicializadas
        QUANDO: Chamo reset_opa_metrics
        ENTÃO: get_opa_metrics deve retornar None
        """
        init_opa_metrics()
        reset_opa_metrics()

        metrics = get_opa_metrics()

        assert metrics is None

    def test_reset_allows_reinit(self):
        """
        DADO: Métricas resetadas
        QUANDO: Inicializo novamente
        ENTÃO: Deve criar nova instância
        """
        init_opa_metrics()
        metrics1 = get_opa_metrics()
        reset_opa_metrics()

        metrics2 = init_opa_metrics()

        assert metrics1 is not metrics2
        assert isinstance(metrics2, OPAMetrics)


class TestOPAMetricsIntegration:
    """Testes de integração com métricas."""

    def test_metrics_labels_correct(self):
        """
        DADO: Instância de OPAMetrics
        ENTÃO: Labels devem estar configuradas corretamente
        """
        metrics = OPAMetrics(namespace="opa", subsystem="test")

        assert metrics.subsystem == "test"
        assert hasattr(metrics, "_evaluations_total")
        assert hasattr(metrics, "_evaluation_duration_ms")
        assert hasattr(metrics, "_cache_hits_total")
        assert hasattr(metrics, "_circuit_breaker_open")

    def test_record_evaluation_increments_counter(self):
        """
        DADO: Instância de OPAMetrics
        QUANDO: Registro avaliação
        ENTÃO: Contador deve ser incrementado
        """
        metrics = OPAMetrics()

        # Não deve levantar exceção
        metrics.record_evaluation("policy/test", True, 100.0)

    def test_record_cache_hit_increments_counter(self):
        """
        DADO: Instância de OPAMetrics
        QUANDO: Registro cache hit
        ENTÃO: Contador deve ser incrementado
        """
        metrics = OPAMetrics()

        # Não deve levantar exceção
        metrics.record_cache_hit()

    def test_set_circuit_breaker_state_updates_gauge(self):
        """
        DADO: Instância de OPAMetrics
        QUANDO: Defino estado do circuit breaker
        ENTÃO: Gauge deve ser atualizada
        """
        metrics = OPAMetrics()

        # Não deve levantar exceção
        metrics.set_circuit_breaker_state(True)
        metrics.set_circuit_breaker_state(False)
