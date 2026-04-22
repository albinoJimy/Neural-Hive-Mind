"""Testes para módulo registry."""

from datetime import datetime

import pytest

from neural_hive_resilience.exceptions import (
    PolicyAlreadyExistsError,
    PolicyNotFoundError,
)
from neural_hive_resilience.registry import (
    PolicyMetadata,
    PolicyType,
    ResilienceRegistry,
    get_global_registry,
    init_global_registry,
)
from neural_hive_resilience.retry import BackoffStrategy


class TestResilienceRegistry:
    """Testes para ResilienceRegistry."""

    def test_initialization(self):
        """Testa inicialização do registro."""
        registry = ResilienceRegistry(
            service_name="test-service",
            default_policies=False,
        )

        assert registry.service_name == "test-service"
        assert len(registry._circuit_breakers) == 0
        assert len(registry._retry_policies) == 0

    def test_initialization_with_defaults(self):
        """Testa inicialização com políticas padrão."""
        registry = ResilienceRegistry(
            service_name="test-service",
            default_policies=True,
        )

        # Deve ter políticas padrão
        assert "default" in registry._retry_policies
        assert "default" in registry._circuit_breakers
        assert "default" in registry._rate_limiters
        assert "default" in registry._timeouts

    # ==================== Circuit Breaker ====================

    def test_register_circuit_breaker(self):
        """Testa registro de circuit breaker."""
        registry = ResilienceRegistry(service_name="test-service", default_policies=False)

        cb = registry.register_circuit_breaker(
            name="test-cb",
            failure_threshold=5,
            recovery_timeout=60,
        )

        assert "test-cb" in registry._circuit_breakers
        assert cb.service_name == "test-service"

    def test_register_circuit_breaker_duplicate(self):
        """Testa erro ao registrar circuit breaker duplicado."""
        registry = ResilienceRegistry(service_name="test-service", default_policies=False)

        registry.register_circuit_breaker(name="test-cb")

        with pytest.raises(PolicyAlreadyExistsError):
            registry.register_circuit_breaker(name="test-cb")

    def test_get_circuit_breaker(self):
        """Testa recuperação de circuit breaker."""
        registry = ResilienceRegistry(service_name="test-service", default_policies=False)

        cb_registered = registry.register_circuit_breaker(name="test-cb")
        cb_retrieved = registry.get_circuit_breaker("test-cb")

        assert cb_registered == cb_retrieved

    def test_get_circuit_breaker_not_found(self):
        """Testa erro ao recuperar circuit breaker inexistente."""
        registry = ResilienceRegistry(service_name="test-service", default_policies=False)

        with pytest.raises(PolicyNotFoundError):
            registry.get_circuit_breaker("non-existent")

    # ==================== Retry Policy ====================

    def test_register_retry_policy(self):
        """Testa registro de política de retry."""
        registry = ResilienceRegistry(service_name="test-service", default_policies=False)

        policy = registry.register_retry_policy(
            name="test-retry",
            max_attempts=5,
            base_delay=0.5,
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
        )

        assert "test-retry" in registry._retry_policies
        assert policy.max_attempts == 5

    def test_register_retry_policy_duplicate(self):
        """Testa erro ao registrar política duplicada."""
        registry = ResilienceRegistry(service_name="test-service", default_policies=False)

        registry.register_retry_policy(name="test-retry")

        with pytest.raises(PolicyAlreadyExistsError):
            registry.register_retry_policy(name="test-retry")

    def test_get_retry_policy(self):
        """Testa recuperação de política de retry."""
        registry = ResilienceRegistry(service_name="test-service", default_policies=False)

        policy_registered = registry.register_retry_policy(name="test-retry")
        policy_retrieved = registry.get_retry_policy("test-retry")

        assert policy_registered == policy_retrieved

    # ==================== Rate Limiter ====================

    def test_register_rate_limiter_token_bucket(self):
        """Testa registro de rate limiter token bucket."""
        registry = ResilienceRegistry(service_name="test-service", default_policies=False)

        limiter = registry.register_rate_limiter_token_bucket(
            name="test-limiter",
            capacity=100,
            refill_rate=10,
        )

        assert "test-limiter" in registry._rate_limiters

    def test_register_rate_limiter_sliding_window(self):
        """Testa registro de rate limiter sliding window."""
        registry = ResilienceRegistry(service_name="test-service", default_policies=False)

        limiter = registry.register_rate_limiter_sliding_window(
            name="test-limiter",
            limit=100,
            window_seconds=60,
        )

        assert "test-limiter" in registry._rate_limiters

    # ==================== Timeout ====================

    def test_register_timeout(self):
        """Testa registro de timeout."""
        registry = ResilienceRegistry(service_name="test-service", default_policies=False)

        timeout_value = registry.register_timeout(
            name="test-timeout",
            timeout_seconds=30.0,
        )

        assert "test-timeout" in registry._timeouts
        assert timeout_value == 30.0

    def test_get_timeout(self):
        """Testa recuperação de timeout."""
        registry = ResilienceRegistry(service_name="test-service", default_policies=False)

        registry.register_timeout(name="test-timeout", timeout_seconds=30.0)
        timeout_value = registry.get_timeout("test-timeout")

        assert timeout_value == 30.0

    # ==================== Bulkhead ====================

    def test_register_bulkhead(self):
        """Testa registro de bulkhead."""
        registry = ResilienceRegistry(service_name="test-service", default_policies=False)

        bulkhead = registry.register_bulkhead(
            name="test-bulkhead",
            max_concurrent=5,
            max_queue_size=2,
        )

        assert "test-bulkhead" in registry._bulkheads

    # ==================== Metadata ====================

    def test_get_metadata(self):
        """Testa recuperação de metadados."""
        registry = ResilienceRegistry(service_name="test-service", default_policies=False)

        registry.register_retry_policy(
            name="test-retry",
            description="Test policy",
            tags=["test", "retry"],
        )

        metadata = registry.get_metadata("test-retry")

        assert metadata is not None
        assert metadata.name == "test-retry"
        assert metadata.type == PolicyType.RETRY
        assert metadata.description == "Test policy"
        assert "test" in metadata.tags

    def test_list_policies_all(self):
        """Testa listagem de todas as políticas."""
        registry = ResilienceRegistry(service_name="test-service", default_policies=False)

        registry.register_retry_policy(name="retry1", tags=["tag1"])
        registry.register_timeout(name="timeout1", timeout_seconds=30.0, tags=["tag1"])
        registry.register_bulkhead(name="bulkhead1", tags=["tag2"])

        policies = registry.list_policies()

        assert len(policies) == 3

    def test_list_policies_by_type(self):
        """Testa listagem filtrada por tipo."""
        registry = ResilienceRegistry(service_name="test-service", default_policies=False)

        registry.register_retry_policy(name="retry1")
        registry.register_timeout(name="timeout1", timeout_seconds=30.0)

        retry_policies = registry.list_policies(policy_type=PolicyType.RETRY)

        assert len(retry_policies) == 1
        assert retry_policies[0].name == "retry1"

    def test_list_policies_by_tag(self):
        """Testa listagem filtrada por tag."""
        registry = ResilienceRegistry(service_name="test-service", default_policies=False)

        registry.register_retry_policy(name="retry1", tags=["important"])
        registry.register_retry_policy(name="retry2", tags=["normal"])
        registry.register_timeout(name="timeout1", timeout_seconds=30.0, tags=["important"])

        important_policies = registry.list_policies(tag="important")

        assert len(important_policies) == 2
        assert all("important" in p.tags for p in important_policies)

    def test_get_stats(self):
        """Testa recuperação de estatísticas."""
        registry = ResilienceRegistry(service_name="test-service", default_policies=False)

        registry.register_retry_policy(name="retry1")
        registry.register_timeout(name="timeout1", timeout_seconds=30.0)
        registry.register_bulkhead(name="bulkhead1")

        stats = registry.get_stats()

        assert stats["service_name"] == "test-service"
        assert stats["retry_policies"] == 1
        assert stats["timeouts"] == 1
        assert stats["bulkheads"] == 1
        assert stats["total_policies"] == 3


class TestGlobalRegistry:
    """Testes para registro global."""

    def test_init_global_registry(self):
        """Testa inicialização do registro global."""
        registry = init_global_registry(service_name="global-service")

        assert registry is not None
        assert registry.service_name == "global-service"

    def test_get_global_registry(self):
        """Testa recuperação do registro global."""
        init_global_registry(service_name="global-service")
        registry = get_global_registry()

        assert registry is not None
        assert registry.service_name == "global-service"

    def test_get_global_registry_not_initialized(self):
        """Testa None quando registro global não inicializado."""
        # Limpar registro global se existir
        import neural_hive_resilience.registry as reg_module

        reg_module._global_registry = None

        registry = get_global_registry()
        assert registry is None


class TestPolicyMetadata:
    """Testes para PolicyMetadata."""

    def test_creation(self):
        """Testa criação de metadados."""
        metadata = PolicyMetadata(
            name="test-policy",
            type=PolicyType.RETRY,
            created_at=datetime.now(),
            description="Test policy",
            tags=["test"],
            config={"max_attempts": 3},
        )

        assert metadata.name == "test-policy"
        assert metadata.type == PolicyType.RETRY
        assert metadata.description == "Test policy"
        assert "test" in metadata.tags
        assert metadata.config["max_attempts"] == 3

    def test_defaults(self):
        """Testa valores padrão."""
        metadata = PolicyMetadata(
            name="test",
            type=PolicyType.RETRY,
            created_at=datetime.now(),
        )

        assert metadata.last_used is None
        assert metadata.usage_count == 0
        assert metadata.description == ""
        assert metadata.tags == []
        assert metadata.config == {}
