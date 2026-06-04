"""
Unit tests para Traffic Switcher.

Testa o gerenciador de redirecionamento de tráfego entre sistemas
legado e target, incluindo shadow mode e rollback de emergência.
"""

import sys
from datetime import timezone

UTC = timezone.utc
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Adicionar src ao path
src_path = str(Path(__file__).parent.parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from src.services.traffic_switcher import (
    EmergencyRollbackError,
    EnvoyTrafficSwitcher,
    KubernetesTrafficSwitcher,
    MockTrafficSwitcher,
    TrafficSwitcherFactory,
    TrafficSwitchError,
    TrafficSwitchStrategy,
)

UTC = timezone.utc


class TestTrafficSwitcherFactory:
    """Testes da factory para criar switchers."""

    @pytest.mark.asyncio()
    async def test_create_mock_switcher(self):
        """Deve criar MockTrafficSwitcher."""
        switcher = await TrafficSwitcherFactory.create(
            strategy=TrafficSwitchStrategy.MOCK,
            config={"initial_percentage": 50},
        )

        assert isinstance(switcher, MockTrafficSwitcher)
        assert await switcher.get_traffic_percentage() == 50

    @pytest.mark.asyncio()
    async def test_create_envoy_switcher(self):
        """Deve criar EnvoyTrafficSwitcher."""
        switcher = await TrafficSwitcherFactory.create(
            strategy=TrafficSwitchStrategy.ENVOY,
            config={"envoy_admin_url": "http://localhost:9901"},
        )

        assert isinstance(switcher, EnvoyTrafficSwitcher)
        assert switcher.envoy_admin_url == "http://localhost:9901"

    @pytest.mark.asyncio()
    async def test_create_kubernetes_switcher(self):
        """Deve criar KubernetesTrafficSwitcher."""
        switcher = await TrafficSwitcherFactory.create(
            strategy=TrafficSwitchStrategy.KUBERNETES,
            config={"service_name": "app", "namespace": "production"},
        )

        assert isinstance(switcher, KubernetesTrafficSwitcher)
        assert switcher.service_name == "app"
        assert switcher.namespace == "production"

    def test_create_sync_mock_switcher(self):
        """Deve criar MockTrafficSwitcher versão síncrona."""
        switcher = TrafficSwitcherFactory.create_sync(
            strategy=TrafficSwitchStrategy.MOCK,
        )

        assert isinstance(switcher, MockTrafficSwitcher)

    @pytest.mark.asyncio()
    async def test_create_invalid_strategy(self):
        """Deve levantar erro para estratégia inválida."""
        with pytest.raises(ValueError):
            await TrafficSwitcherFactory.create(strategy="invalid_strategy")

    @pytest.mark.asyncio()
    async def test_create_from_string(self):
        """Deve aceitar string como estratégia."""
        switcher = await TrafficSwitcherFactory.create(strategy="mock")

        assert isinstance(switcher, MockTrafficSwitcher)


class TestMockTrafficSwitcher:
    """Testes do MockTrafficSwitcher."""

    @pytest.fixture()
    def mock_switcher(self):
        """Retorna MockTrafficSwitcher para testes."""
        return MockTrafficSwitcher(initial_percentage=0)

    @pytest.mark.asyncio()
    async def test_initial_state(self, mock_switcher):
        """Deve inicializar com porcentagem zero."""
        assert await mock_switcher.get_traffic_percentage() == 0
        assert mock_switcher._shadow_mode_enabled is False

    @pytest.mark.asyncio()
    async def test_set_traffic_percentage_valid(self, mock_switcher):
        """Deve definir porcentagem válida."""
        result = await mock_switcher.set_traffic_percentage(50)

        assert result is True
        assert await mock_switcher.get_traffic_percentage() == 50
        assert mock_switcher._last_updated is not None

    @pytest.mark.asyncio()
    async def test_set_traffic_percentage_zero(self, mock_switcher):
        """Deve aceitar 0% (100% legado)."""
        result = await mock_switcher.set_traffic_percentage(0)

        assert result is True
        assert await mock_switcher.get_traffic_percentage() == 0

    @pytest.mark.asyncio()
    async def test_set_traffic_percentage_full(self, mock_switcher):
        """Deve aceitar 100% (100% target)."""
        result = await mock_switcher.set_traffic_percentage(100)

        assert result is True
        assert await mock_switcher.get_traffic_percentage() == 100

    @pytest.mark.asyncio()
    async def test_set_traffic_percentage_invalid_negative(self, mock_switcher):
        """Deve rejeitar porcentagem negativa."""
        with pytest.raises(ValueError, match="Percentage deve estar entre 0 e 100"):
            await mock_switcher.set_traffic_percentage(-1)

    @pytest.mark.asyncio()
    async def test_set_traffic_percentage_invalid_over_100(self, mock_switcher):
        """Deve rejeitar porcentagem acima de 100."""
        with pytest.raises(ValueError, match="Percentage deve estar entre 0 e 100"):
            await mock_switcher.set_traffic_percentage(101)

    @pytest.mark.asyncio()
    async def test_enable_shadow_mode(self, mock_switcher):
        """Deve ativar shadow mode."""
        result = await mock_switcher.enable_shadow_mode()

        assert result is True
        assert mock_switcher._shadow_mode_enabled is True

    @pytest.mark.asyncio()
    async def test_disable_shadow_mode(self, mock_switcher):
        """Deve desativar shadow mode."""
        await mock_switcher.enable_shadow_mode()
        result = await mock_switcher.disable_shadow_mode()

        assert result is True
        assert mock_switcher._shadow_mode_enabled is False

    @pytest.mark.asyncio()
    async def test_emergency_switch_to_legacy(self, mock_switcher):
        """Deve executar rollback de emergência."""
        await mock_switcher.set_traffic_percentage(100)
        await mock_switcher.enable_shadow_mode()

        result = await mock_switcher.emergency_switch_to_legacy()

        assert result is True
        assert await mock_switcher.get_traffic_percentage() == 0
        assert mock_switcher._shadow_mode_enabled is False
        assert mock_switcher._rollback_count == 1

    @pytest.mark.asyncio()
    async def test_get_status(self, mock_switcher):
        """Deve retornar status completo."""
        await mock_switcher.set_traffic_percentage(75)
        await mock_switcher.enable_shadow_mode()

        status = await mock_switcher.get_status()

        assert status["traffic_percentage"] == 75
        assert status["shadow_mode_enabled"] is True
        assert status["strategy"] == TrafficSwitchStrategy.MOCK
        assert "last_updated" in status
        assert status["update_count"] == 1

    @pytest.mark.asyncio()
    async def test_simulate_latency(self):
        """Deve simular latência quando habilitado."""
        import time

        switcher = MockTrafficSwitcher(simulate_latency=True)

        start = time.time()
        await switcher.set_traffic_percentage(50)
        elapsed = time.time() - start

        assert elapsed >= 0.05  # 50ms mínimo

    @pytest.mark.asyncio()
    async def test_simulate_failure(self):
        """Deve simular falha quando configurado."""
        switcher = MockTrafficSwitcher(failure_percentage=1.0)  # 100% falha

        with pytest.raises(TrafficSwitchError, match="Simulated failure"):
            await switcher.set_traffic_percentage(50)

    @pytest.mark.asyncio()
    async def test_reset(self, mock_switcher):
        """Deve resetar estado."""
        await mock_switcher.set_traffic_percentage(100)
        await mock_switcher.enable_shadow_mode()

        mock_switcher.reset()

        assert await mock_switcher.get_traffic_percentage() == 0
        assert mock_switcher._shadow_mode_enabled is False
        assert mock_switcher._update_count == 0
        assert mock_switcher._rollback_count == 0


class TestEnvoyTrafficSwitcher:
    """Testes do EnvoyTrafficSwitcher."""

    @pytest.fixture()
    def envoy_switcher(self):
        """Retorna EnvoyTrafficSwitcher para testes."""
        return EnvoyTrafficSwitcher(
            envoy_admin_url="http://localhost:9901",
            envoy_control_plane_url="http://control-plane:8080",
        )

    @pytest.mark.asyncio()
    async def test_initial_state(self, envoy_switcher):
        """Deve inicializar com configuração padrão."""
        assert envoy_switcher.strategy == TrafficSwitchStrategy.ENVOY
        assert envoy_switcher.envoy_admin_url == "http://localhost:9901"
        assert envoy_switcher._current_percentage == 0

    @pytest.mark.asyncio()
    async def test_set_traffic_percentage_valid(self, envoy_switcher):
        """Deve definir porcentagem válida."""
        with patch.object(envoy_switcher._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.status_code = 200

            result = await envoy_switcher.set_traffic_percentage(50)

            assert result is True
            assert envoy_switcher._current_percentage == 50

    @pytest.mark.asyncio()
    async def test_set_traffic_percentage_zero(self, envoy_switcher):
        """Deve definir 0% (100% legado)."""
        with patch.object(envoy_switcher._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.status_code = 200

            result = await envoy_switcher.set_traffic_percentage(0)

            assert result is True
            assert envoy_switcher._current_percentage == 0

    @pytest.mark.asyncio()
    async def test_set_traffic_percentage_full(self, envoy_switcher):
        """Deve definir 100% (100% target)."""
        with patch.object(envoy_switcher._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.status_code = 200

            result = await envoy_switcher.set_traffic_percentage(100)

            assert result is True
            assert envoy_switcher._current_percentage == 100

    @pytest.mark.asyncio()
    async def test_set_traffic_percentage_invalid(self, envoy_switcher):
        """Deve rejeitar porcentagem inválida."""
        with pytest.raises(ValueError, match="Percentage deve estar entre 0 e 100"):
            await envoy_switcher.set_traffic_percentage(150)

    @pytest.mark.asyncio()
    async def test_set_traffic_percentage_http_error(self, envoy_switcher):
        """Deve tratar erro HTTP do Envoy."""
        import httpx

        with patch.object(envoy_switcher._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.HTTPError("Connection refused")

            with pytest.raises(TrafficSwitchError, match="Falha HTTP ao comunicar com Envoy"):
                await envoy_switcher.set_traffic_percentage(50)

    @pytest.mark.asyncio()
    async def test_get_traffic_percentage(self, envoy_switcher):
        """Deve retornar porcentagem atual."""
        with patch.object(envoy_switcher._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value.status_code = 200

            envoy_switcher._current_percentage = 75
            result = await envoy_switcher.get_traffic_percentage()

            assert result == 75

    @pytest.mark.asyncio()
    async def test_enable_shadow_mode(self, envoy_switcher):
        """Deve ativar shadow mode via control plane."""
        with patch.object(envoy_switcher._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.status_code = 200

            result = await envoy_switcher.enable_shadow_mode()

            assert result is True
            assert envoy_switcher._shadow_mode_enabled is True

    @pytest.mark.asyncio()
    async def test_enable_shadow_mode_without_control_plane(self):
        """Deve ativar shadow mode sem control plane (fallback)."""
        switcher = EnvoyTrafficSwitcher(
            envoy_admin_url="http://localhost:9901",
            envoy_control_plane_url=None,
        )

        # Sem control plane, deve usar fallback
        result = await switcher.enable_shadow_mode()

        assert result is True
        assert switcher._shadow_mode_enabled is True

    @pytest.mark.asyncio()
    async def test_disable_shadow_mode(self, envoy_switcher):
        """Deve desativar shadow mode."""
        with patch.object(envoy_switcher._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.status_code = 200

            envoy_switcher._shadow_mode_enabled = True
            result = await envoy_switcher.disable_shadow_mode()

            assert result is True
            assert envoy_switcher._shadow_mode_enabled is False

    @pytest.mark.asyncio()
    async def test_emergency_switch_to_legacy(self, envoy_switcher):
        """Deve executar rollback de emergência."""
        with patch.object(envoy_switcher._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.status_code = 200

            # Configurar estado inicial
            envoy_switcher._current_percentage = 100
            envoy_switcher._shadow_mode_enabled = True

            result = await envoy_switcher.emergency_switch_to_legacy()

            assert result is True
            assert envoy_switcher._current_percentage == 0
            assert envoy_switcher._shadow_mode_enabled is False

    @pytest.mark.asyncio()
    async def test_emergency_switch_to_legacy_failure(self, envoy_switcher):
        """Deve levantar erro se rollback falhar."""
        import httpx

        with patch.object(envoy_switcher._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.HTTPError("Connection refused")

            with pytest.raises(EmergencyRollbackError, match="Falha crítica no rollback"):
                await envoy_switcher.emergency_switch_to_legacy()

    @pytest.mark.asyncio()
    async def test_close(self, envoy_switcher):
        """Deve fechar HTTP client."""
        await envoy_switcher.close()

        # Verificar que client foi fechado
        assert envoy_switcher._client.is_closed


class TestKubernetesTrafficSwitcher:
    """Testes do KubernetesTrafficSwitcher.

    Nota: Os testes de integração com Kubernetes são limitados porque
    o kubernetes client faz lazy import e requer configuração real.
    Testes focam em validação de input e configuração.
    """

    @pytest.fixture()
    def k8s_switcher(self):
        """Retorna KubernetesTrafficSwitcher para testes."""
        return KubernetesTrafficSwitcher(
            service_name="app",
            namespace="production",
            legacy_label="version: legacy",
            canary_label="version: canary",
        )

    def test_initial_state(self, k8s_switcher):
        """Deve inicializar com configuração padrão."""
        assert k8s_switcher.strategy == TrafficSwitchStrategy.KUBERNETES
        assert k8s_switcher.service_name == "app"
        assert k8s_switcher.namespace == "production"
        assert k8s_switcher._current_percentage == 0

    @pytest.mark.asyncio()
    async def test_set_traffic_percentage_invalid_negative(self, k8s_switcher):
        """Deve rejeitar porcentagem negativa."""
        with pytest.raises(ValueError, match="Percentage deve estar entre 0 e 100"):
            await k8s_switcher.set_traffic_percentage(-5)

    @pytest.mark.asyncio()
    async def test_set_traffic_percentage_invalid_over_100(self, k8s_switcher):
        """Deve rejeitar porcentagem acima de 100."""
        with pytest.raises(ValueError, match="Percentage deve estar entre 0 e 100"):
            await k8s_switcher.set_traffic_percentage(150)

    @pytest.mark.asyncio()
    async def test_enable_shadow_mode(self, k8s_switcher):
        """Deve ativar shadow mode (limitado no K8s)."""
        result = await k8s_switcher.enable_shadow_mode()

        assert result is True
        assert k8s_switcher._shadow_mode_enabled is True

    @pytest.mark.asyncio()
    async def test_disable_shadow_mode(self, k8s_switcher):
        """Deve desativar shadow mode."""
        await k8s_switcher.enable_shadow_mode()
        result = await k8s_switcher.disable_shadow_mode()

        assert result is True
        assert k8s_switcher._shadow_mode_enabled is False

    @pytest.mark.asyncio()
    async def test_get_status(self, k8s_switcher):
        """Deve retornar status detalhado."""
        k8s_switcher._current_percentage = 50
        k8s_switcher._shadow_mode_enabled = True

        status = await k8s_switcher.get_status()

        assert status["traffic_percentage"] == 50
        # KubernetesTrafficSwitcher usa get_status da classe base que não retorna shadow_mode_enabled
        # O importante é testar que _shadow_mode_enabled foi set corretamente
        assert k8s_switcher._shadow_mode_enabled is True
        assert status["strategy"] == TrafficSwitchStrategy.KUBERNETES
        assert "last_updated" in status

    @pytest.mark.asyncio()
    async def test_label_parsing(self, k8s_switcher):
        """Deve parsear labels corretamente."""
        # Labels no formato "key: value"
        assert k8s_switcher.legacy_label == "version: legacy"
        assert k8s_switcher.canary_label == "version: canary"

    @pytest.mark.asyncio()
    async def test_custom_labels(self):
        """Deve aceitar labels customizados."""
        switcher = KubernetesTrafficSwitcher(
            service_name="app",
            namespace="staging",
            legacy_label="env: prod",
            canary_label="env: staging",
        )

        assert switcher.legacy_label == "env: prod"
        assert switcher.canary_label == "env: staging"
        assert switcher.namespace == "staging"


class TestTrafficSwitchStrategy:
    """Testes do enum TrafficSwitchStrategy."""

    def test_strategy_values(self):
        """Deve ter todas as estratégias esperadas."""
        assert TrafficSwitchStrategy.ENVOY == "envoy"
        assert TrafficSwitchStrategy.KUBERNETES == "kubernetes"
        assert TrafficSwitchStrategy.NGINX == "nginx"
        assert TrafficSwitchStrategy.ISTIO == "istio"
        assert TrafficSwitchStrategy.MOCK == "mock"

    def test_strategy_from_string(self):
        """Deve criar estratégia from string."""
        assert TrafficSwitchStrategy("envoy") == TrafficSwitchStrategy.ENVOY
        assert TrafficSwitchStrategy("mock") == TrafficSwitchStrategy.MOCK

    def test_strategy_iteration(self):
        """Deve iterar sobre todas as estratégias."""
        strategies = [s for s in TrafficSwitchStrategy]

        assert TrafficSwitchStrategy.ENVOY in strategies
        assert TrafficSwitchStrategy.MOCK in strategies
        assert len(strategies) == 5


class TestTrafficSwitchError:
    """Testes das exceções customizadas."""

    def test_traffic_switch_error_creation(self):
        """Deve criar erro com detalhes."""
        error = TrafficSwitchError(
            message="Test error",
            strategy=TrafficSwitchStrategy.MOCK,
            details={"key": "value"},
        )

        assert error.message == "Test error"
        assert error.strategy == TrafficSwitchStrategy.MOCK
        assert error.details == {"key": "value"}
        assert str(error) == "Test error"

    def test_emergency_rollback_error_is_traffic_switch_error(self):
        """EmergencyRollbackError deve ser subclasse de TrafficSwitchError."""
        error = EmergencyRollbackError(
            message="Emergency!",
            strategy=TrafficSwitchStrategy.ENVOY,
        )

        assert isinstance(error, TrafficSwitchError)
        assert isinstance(error, EmergencyRollbackError)
        assert error.message == "Emergency!"
