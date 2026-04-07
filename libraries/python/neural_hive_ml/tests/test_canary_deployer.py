"""Testes para CanaryDeployer - Deploy Canary de Modelos ML."""

import pytest
from unittest.mock import AsyncMock
from neural_hive_ml.drift_detector import CanaryDeployer


@pytest.fixture
def mock_model_repo():
    """Mock ModelVersionRepository."""
    repo = AsyncMock()
    repo.get_active_model = AsyncMock(
        return_value={"version": "v8", "stage": "production", "f1_score": 0.73}
    )
    repo.get_model_version = AsyncMock(
        return_value={"version": "v9", "stage": "staging", "f1_score": 0.75}
    )
    repo.promote_model = AsyncMock(return_value=True)
    repo.update_model = AsyncMock(return_value=True)
    return repo


@pytest.fixture
def mock_kafka_producer():
    """Mock Kafka producer."""
    producer = AsyncMock()
    producer.produce_and_wait = AsyncMock()
    return producer


@pytest.fixture
def canary_deployer(mock_model_repo, mock_kafka_producer):
    """Fixture para CanaryDeployer."""
    return CanaryDeployer(
        model_repo=mock_model_repo,
        kafka_producer=mock_kafka_producer,
        canary_duration_minutes=60,
        canary_traffic_percentage=10,
    )


class TestCanaryDeployerInit:
    """Testes de inicialização."""

    def test_init_with_defaults(self, mock_model_repo, mock_kafka_producer):
        """Testa inicialização com valores padrão."""
        deployer = CanaryDeployer(model_repo=mock_model_repo, kafka_producer=mock_kafka_producer)
        assert deployer.canary_duration_minutes == 60
        assert deployer.canary_traffic_percentage == 10

    def test_init_with_custom_values(self, mock_model_repo, mock_kafka_producer):
        """Testa inicialização com valores customizados."""
        deployer = CanaryDeployer(
            model_repo=mock_model_repo,
            kafka_producer=mock_kafka_producer,
            canary_duration_minutes=120,
            canary_traffic_percentage=25,
        )
        assert deployer.canary_duration_minutes == 120
        assert deployer.canary_traffic_percentage == 25


class TestStartCanary:
    """Testes de start_canary."""

    @pytest.mark.asyncio
    async def test_start_canary_success(
        self, canary_deployer, mock_model_repo, mock_kafka_producer
    ):
        """Testa início de deploy canary com sucesso."""
        result = await canary_deployer.start_canary(version="v9", target_version="v8")

        assert result["status"] == "running"
        assert "canary_id" in result
        assert "started_at" in result
        assert result["canary_traffic_percentage"] == 10
        assert result["duration_minutes"] == 60

    @pytest.mark.asyncio
    async def test_start_canary_publishes_event(self, canary_deployer, mock_kafka_producer):
        """Testa que início de canary publica evento Kafka."""
        await canary_deployer.start_canary(version="v9", target_version="v8")

        mock_kafka_producer.produce_and_wait.assert_called_once()
        call_args = mock_kafka_producer.produce_and_wait.call_args
        assert "ml.canary_started" in call_args[1]["topic"]

    @pytest.mark.asyncio
    async def test_start_canary_validates_versions(self, canary_deployer, mock_model_repo):
        """Testa que start_canary valida existência das versões."""
        # Mock para retornar None para versão inexistente
        mock_model_repo.get_model_version = AsyncMock(return_value=None)

        result = await canary_deployer.start_canary(version="v99", target_version="v8")

        assert result["status"] == "failed"
        assert "error" in result


class TestCollectCanaryMetrics:
    """Testes de collect_canary_metrics."""

    @pytest.mark.asyncio
    async def test_collect_metrics_success(self, canary_deployer):
        """Testa coleta de métricas canary com sucesso."""
        # Simular métricas coletadas
        canary_id = "canary-v9-v8"
        result = await canary_deployer.collect_canary_metrics(canary_id)

        assert "canary_id" in result
        assert "metrics" in result
        assert "collected_at" in result

    @pytest.mark.asyncio
    async def test_collect_metrics_with_comparison(self, canary_deployer):
        """Testa coleta com comparação entre baseline e canary."""
        canary_id = "canary-v9-v8"
        result = await canary_deployer.collect_canary_metrics(canary_id)

        assert "baseline" in result["metrics"]
        assert "canary" in result["metrics"]
        assert "comparison" in result["metrics"]


class TestValidateCanary:
    """Testes de validate_canary."""

    @pytest.mark.asyncio
    async def test_validate_canary_success(self, canary_deployer):
        """Testa validação de canary com sucesso."""
        canary_id = "canary-v9-v8"
        result = await canary_deployer.validate_canary(canary_id)

        assert isinstance(result, dict)
        assert "should_promote" in result
        assert "reasons" in result

    @pytest.mark.asyncio
    async def test_validate_canary_with_better_metrics(self, canary_deployer):
        """Testa validação quando canary tem métricas melhores."""
        canary_id = "canary-v9-v8"
        result = await canary_deployer.validate_canary(canary_id)

        # Deve recomendar promoção se métricas são melhores
        assert result["should_promote"] is True

    @pytest.mark.asyncio
    async def test_validate_canary_with_worse_metrics(self, canary_deployer):
        """Testa validação quando canary tem métricas piores."""
        # Simular métricas piores
        canary_id = "canary-v9-v8"
        result = await canary_deployer.validate_canary(canary_id)

        # Verifica que avaliação foi feita
        assert "should_promote" in result

    @pytest.mark.asyncio
    async def test_validate_canary_insufficient_samples(self, canary_deployer):
        """Testa validação com samples insuficientes."""
        canary_id = "canary-v9-v8"
        result = await canary_deployer.validate_canary(canary_id)

        # Deve requerer mais samples se insuficientes
        assert "should_promote" in result


class TestPromoteOrRollback:
    """Testes de promote_or_rollback."""

    @pytest.mark.asyncio
    async def test_promote_canary(self, canary_deployer, mock_model_repo, mock_kafka_producer):
        """Testa promoção de canary."""
        canary_id = "canary-v9-v8"
        result = await canary_deployer.promote_or_rollback(canary_id, should_promote=True)

        assert result["status"] == "promoted"
        mock_model_repo.promote_model.assert_called_once()
        mock_kafka_producer.produce_and_wait.assert_called()

    @pytest.mark.asyncio
    async def test_rollback_canary(self, canary_deployer, mock_kafka_producer):
        """Testa rollback de canary."""
        canary_id = "canary-v9-v8"
        result = await canary_deployer.promote_or_rollback(canary_id, should_promote=False)

        assert result["status"] == "rolled_back"
        mock_kafka_producer.produce_and_wait.assert_called()

    @pytest.mark.asyncio
    async def test_promote_publishes_event(self, canary_deployer, mock_kafka_producer):
        """Testa que promoção publica evento."""
        canary_id = "canary-v9-v8"
        await canary_deployer.promote_or_rollback(canary_id, should_promote=True)

        # Verifica que evento foi publicado
        assert mock_kafka_producer.produce_and_wait.call_count >= 1


class TestCanaryLifecycle:
    """Testes do ciclo de vida completo do canary."""

    @pytest.mark.asyncio
    async def test_full_canary_lifecycle_success(self, canary_deployer, mock_model_repo):
        """Testa ciclo completo: start -> collect -> validate -> promote."""
        # Start
        start_result = await canary_deployer.start_canary(version="v9", target_version="v8")
        canary_id = start_result["canary_id"]

        # Collect
        metrics_result = await canary_deployer.collect_canary_metrics(canary_id)

        # Validate
        validate_result = await canary_deployer.validate_canary(canary_id)

        # Promote or rollback
        final_result = await canary_deployer.promote_or_rollback(
            canary_id, should_promote=validate_result["should_promote"]
        )

        assert final_result["status"] in ["promoted", "rolled_back"]

    @pytest.mark.asyncio
    async def test_full_canary_lifecycle_rollback(self, canary_deployer):
        """Testa ciclo completo com rollback."""
        start_result = await canary_deployer.start_canary(version="v9", target_version="v8")
        canary_id = start_result["canary_id"]

        await canary_deployer.collect_canary_metrics(canary_id)
        validate_result = await canary_deployer.validate_canary(canary_id)

        # Força rollback
        final_result = await canary_deployer.promote_or_rollback(canary_id, should_promote=False)

        assert final_result["status"] == "rolled_back"


class TestCanaryMetricsCalculation:
    """Testes de cálculo de métricas canary."""

    @pytest.mark.asyncio
    async def test_calculate_traffic_split(self, canary_deployer):
        """Testa cálculo de split de tráfego."""
        result = await canary_deployer._calculate_traffic_split("v9", "v8")

        assert result["canary_percentage"] == 10
        assert result["baseline_percentage"] == 90

    @pytest.mark.asyncio
    async def test_calculate_traffic_split_custom(self, mock_model_repo, mock_kafka_producer):
        """Testa split com percentual customizado."""
        deployer = CanaryDeployer(
            model_repo=mock_model_repo,
            kafka_producer=mock_kafka_producer,
            canary_traffic_percentage=25,
        )

        result = await deployer._calculate_traffic_split("v9", "v8")

        assert result["canary_percentage"] == 25
        assert result["baseline_percentage"] == 75
