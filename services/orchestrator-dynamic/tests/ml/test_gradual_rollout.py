"""
Testes unitários para Gradual Rollout no ModelPromotionManager.

Valida:
- Rollout gradual bem-sucedido
- Rollback automático em degradação
- Verificação de degradação de MAE
- Verificação de error rate
- Checkpoints de validação
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.ml.model_promotion import (
    ModelPromotionManager,
    PromotionRequest,
    PromotionConfig,
    PromotionStage,
    PromotionResult
)


class TestGradualRollout:
    """Testes para gradual rollout."""

    @pytest.fixture
    def mock_config(self):
        """Mock de configuração."""
        config = MagicMock()
        config.ml_gradual_rollout_enabled = True
        config.ml_rollout_stages = [0.25, 0.50, 0.75, 1.0]
        config.ml_checkpoint_duration_minutes = 0.01  # 0.6 segundos para testes rápidos
        config.ml_checkpoint_mae_threshold_pct = 20.0
        config.ml_checkpoint_error_rate_threshold = 0.001
        config.ml_shadow_mode_enabled = True
        config.ml_shadow_mode_duration_minutes = 1
        config.ml_shadow_mode_min_predictions = 10
        config.ml_shadow_mode_agreement_threshold = 0.90
        config.ml_canary_enabled = True
        config.ml_canary_traffic_percentage = 10.0
        config.ml_canary_duration_minutes = 1
        config.ml_validation_mae_threshold = 0.15
        config.ml_validation_precision_threshold = 0.75
        config.ml_auto_rollback_enabled = True
        config.ml_rollback_mae_increase_pct = 20.0
        return config

    @pytest.fixture
    def mock_model_registry(self):
        """Model registry mock."""
        registry = AsyncMock()
        registry.load_model = AsyncMock(return_value=MagicMock())
        registry.get_model_metadata = AsyncMock(return_value={'metrics': {'mae_percentage': 10.0}})
        registry.promote_model = AsyncMock()
        registry.enrich_model_metadata = AsyncMock()
        registry.rollback_model = AsyncMock(return_value={'success': True})
        return registry

    @pytest.fixture
    def mock_continuous_validator(self):
        """Continuous validator mock."""
        validator = MagicMock()
        validator.get_current_metrics = MagicMock(return_value={
            '24h': {
                'mae': 500,
                'mae_pct': 10.0,
                'sample_count': 100
            }
        })
        return validator

    @pytest.fixture
    def mock_mongodb(self):
        """Cliente MongoDB mock."""
        mongodb = MagicMock()
        mongodb.db = MagicMock()
        collection = AsyncMock()
        collection.insert_one = AsyncMock()
        mongodb.db.__getitem__ = MagicMock(return_value=collection)
        return mongodb

    @pytest.fixture
    def mock_metrics(self):
        """Métricas mock."""
        metrics = MagicMock()
        metrics.set_rollout_stage = MagicMock()
        metrics.set_rollout_traffic_pct = MagicMock()
        metrics.record_rollout_checkpoint = MagicMock()
        metrics.record_rollout_degradation = MagicMock()
        metrics.record_promotion = MagicMock()
        return metrics

    @pytest.fixture
    def promotion_manager(self, mock_config, mock_model_registry, mock_continuous_validator, mock_mongodb, mock_metrics):
        """Cria ModelPromotionManager para testes."""
        manager = ModelPromotionManager(
            config=mock_config,
            model_registry=mock_model_registry,
            continuous_validator=mock_continuous_validator,
            mongodb_client=mock_mongodb,
            metrics=mock_metrics
        )
        return manager

    @pytest.mark.asyncio
    async def test_gradual_rollout_success(self, promotion_manager, mock_metrics):
        """Testa rollout gradual bem-sucedido."""
        # Arrange
        request = PromotionRequest(
            request_id="test_promo_1",
            model_name="duration_predictor",
            source_version="v2.0",
            config=PromotionConfig(
                gradual_rollout_enabled=True,
                rollout_stages=[0.25, 0.50, 1.0],
                checkpoint_duration_minutes=0.001,  # 0.06 segundos
                checkpoint_mae_threshold_pct=20.0,
                auto_rollback_enabled=True
            )
        )

        # Mock métricas estáveis
        promotion_manager._collect_current_metrics = AsyncMock(return_value={
            'mae_pct': 10.0,
            'sample_count': 100
        })

        promotion_manager._execute_full_rollout = AsyncMock()

        # Act
        result = await promotion_manager._run_gradual_rollout(request)

        # Assert
        assert result is True
        assert promotion_manager._execute_full_rollout.called
        assert 'rollout_baseline' in request.metrics
        mock_metrics.set_rollout_stage.assert_called()
        mock_metrics.set_rollout_traffic_pct.assert_called()

    @pytest.mark.asyncio
    async def test_gradual_rollout_degradation_rollback(self, promotion_manager, mock_metrics):
        """Testa rollback automático em degradação."""
        # Arrange
        request = PromotionRequest(
            request_id="test_promo_2",
            model_name="duration_predictor",
            source_version="v2.0",
            config=PromotionConfig(
                gradual_rollout_enabled=True,
                rollout_stages=[0.25, 0.50, 1.0],
                checkpoint_duration_minutes=0.001,
                auto_rollback_enabled=True,
                checkpoint_mae_threshold_pct=20.0
            )
        )

        # Mock métricas: baseline OK, checkpoint degradado (50% increase > 20% threshold)
        baseline_metrics = {'mae_pct': 10.0, 'sample_count': 100}
        degraded_metrics = {'mae_pct': 15.0, 'sample_count': 100}  # 50% increase

        promotion_manager._collect_current_metrics = AsyncMock(
            side_effect=[baseline_metrics, degraded_metrics]
        )

        promotion_manager._execute_rollback = AsyncMock()

        # Act
        result = await promotion_manager._run_gradual_rollout(request)

        # Assert
        assert result is False
        assert promotion_manager._execute_rollback.called
        assert request.error_message is not None
        mock_metrics.record_rollout_degradation.assert_called()

    @pytest.mark.asyncio
    async def test_check_rollout_degradation_mae_increase(self, promotion_manager):
        """Testa detecção de degradação por aumento de MAE."""
        # Arrange
        request = PromotionRequest(
            request_id="test_promo_3",
            model_name="duration_predictor",
            source_version="v2.0",
            config=PromotionConfig(checkpoint_mae_threshold_pct=20.0)
        )

        baseline_metrics = {'mae_pct': 10.0, 'sample_count': 100}
        checkpoint_metrics = {'mae_pct': 13.0, 'sample_count': 100}  # 30% increase

        # Act
        degradation = await promotion_manager._check_rollout_degradation(
            request=request,
            baseline_metrics=baseline_metrics,
            checkpoint_metrics=checkpoint_metrics,
            stage_name="stage_1"
        )

        # Assert
        assert degradation is True

    @pytest.mark.asyncio
    async def test_check_rollout_degradation_no_degradation(self, promotion_manager):
        """Testa validação sem degradação."""
        # Arrange
        request = PromotionRequest(
            request_id="test_promo_4",
            model_name="duration_predictor",
            source_version="v2.0",
            config=PromotionConfig(checkpoint_mae_threshold_pct=20.0)
        )

        baseline_metrics = {'mae_pct': 10.0, 'sample_count': 100}
        checkpoint_metrics = {'mae_pct': 10.5, 'sample_count': 100}  # 5% increase

        # Act
        degradation = await promotion_manager._check_rollout_degradation(
            request=request,
            baseline_metrics=baseline_metrics,
            checkpoint_metrics=checkpoint_metrics,
            stage_name="stage_1"
        )

        # Assert
        assert degradation is False

    @pytest.mark.asyncio
    async def test_check_rollout_degradation_error_rate(self, promotion_manager):
        """Testa detecção de degradação por error rate."""
        # Arrange
        request = PromotionRequest(
            request_id="test_promo_5",
            model_name="duration_predictor",
            source_version="v2.0",
            config=PromotionConfig(
                checkpoint_mae_threshold_pct=20.0,
                checkpoint_error_rate_threshold=0.001  # 0.1%
            )
        )

        baseline_metrics = {'mae_pct': 10.0, 'sample_count': 100}
        checkpoint_metrics = {'mae_pct': 10.0, 'sample_count': 100, 'error_rate': 0.01}  # 1% error rate

        # Act
        degradation = await promotion_manager._check_rollout_degradation(
            request=request,
            baseline_metrics=baseline_metrics,
            checkpoint_metrics=checkpoint_metrics,
            stage_name="stage_1"
        )

        # Assert
        assert degradation is True

    @pytest.mark.asyncio
    async def test_check_rollout_degradation_insufficient_samples(self, promotion_manager):
        """Testa que amostras insuficientes não geram degradação."""
        # Arrange
        request = PromotionRequest(
            request_id="test_promo_6",
            model_name="duration_predictor",
            source_version="v2.0",
            config=PromotionConfig(checkpoint_mae_threshold_pct=20.0)
        )

        baseline_metrics = {'mae_pct': 10.0, 'sample_count': 100}
        checkpoint_metrics = {'mae_pct': 50.0, 'sample_count': 5}  # Muita degradação mas poucas amostras

        # Act
        degradation = await promotion_manager._check_rollout_degradation(
            request=request,
            baseline_metrics=baseline_metrics,
            checkpoint_metrics=checkpoint_metrics,
            stage_name="stage_1"
        )

        # Assert
        assert degradation is False  # Não detecta degradação com amostras insuficientes

    @pytest.mark.asyncio
    async def test_check_rollout_degradation_no_metrics(self, promotion_manager):
        """Testa que ausência de métricas não gera degradação."""
        # Arrange
        request = PromotionRequest(
            request_id="test_promo_7",
            model_name="duration_predictor",
            source_version="v2.0",
            config=PromotionConfig(checkpoint_mae_threshold_pct=20.0)
        )

        # Act
        degradation = await promotion_manager._check_rollout_degradation(
            request=request,
            baseline_metrics={},
            checkpoint_metrics={},
            stage_name="stage_1"
        )

        # Assert
        assert degradation is False

    @pytest.mark.asyncio
    async def test_gradual_rollout_disabled(self, promotion_manager):
        """Testa que rollout direto é usado quando gradual está desabilitado."""
        # Arrange
        request = PromotionRequest(
            request_id="test_promo_8",
            model_name="duration_predictor",
            source_version="v2.0",
            config=PromotionConfig(
                gradual_rollout_enabled=False,
                shadow_mode_enabled=False,
                canary_enabled=False
            )
        )

        # Mock validation to pass
        promotion_manager._run_pre_promotion_validation = AsyncMock(return_value=True)
        promotion_manager._execute_full_rollout = AsyncMock()
        promotion_manager._finalize_promotion = AsyncMock()

        # Act
        await promotion_manager._execute_promotion(request)

        # Assert
        assert promotion_manager._execute_full_rollout.called
        assert request.stage == PromotionStage.COMPLETED

    @pytest.mark.asyncio
    async def test_gradual_rollout_stages_progression(self, promotion_manager, mock_metrics):
        """Testa progressão correta pelos estágios de rollout."""
        # Arrange
        request = PromotionRequest(
            request_id="test_promo_9",
            model_name="duration_predictor",
            source_version="v2.0",
            config=PromotionConfig(
                gradual_rollout_enabled=True,
                rollout_stages=[0.25, 0.50, 0.75, 1.0],
                checkpoint_duration_minutes=0.001,
                checkpoint_mae_threshold_pct=50.0  # Alto threshold para garantir sucesso
            )
        )

        # Mock métricas estáveis
        promotion_manager._collect_current_metrics = AsyncMock(return_value={
            'mae_pct': 10.0,
            'sample_count': 100
        })

        promotion_manager._execute_full_rollout = AsyncMock()

        # Act
        result = await promotion_manager._run_gradual_rollout(request)

        # Assert
        assert result is True

        # Verificar que todos os estágios foram registrados
        stage_calls = [call for call in mock_metrics.set_rollout_stage.call_args_list]
        assert len(stage_calls) == 4  # 4 estágios

        # Verificar progressão de tráfego
        traffic_calls = [call for call in mock_metrics.set_rollout_traffic_pct.call_args_list]
        assert len(traffic_calls) == 4

    @pytest.mark.asyncio
    async def test_gradual_rollout_cleanup_on_success(self, promotion_manager):
        """Testa que estado é limpo após rollout bem-sucedido."""
        # Arrange
        request = PromotionRequest(
            request_id="test_promo_10",
            model_name="duration_predictor",
            source_version="v2.0",
            config=PromotionConfig(
                gradual_rollout_enabled=True,
                rollout_stages=[0.50, 1.0],
                checkpoint_duration_minutes=0.001
            )
        )

        promotion_manager._collect_current_metrics = AsyncMock(return_value={
            'mae_pct': 10.0,
            'sample_count': 100
        })

        promotion_manager._execute_full_rollout = AsyncMock()

        # Act
        await promotion_manager._run_gradual_rollout(request)

        # Assert - estado deve estar limpo
        assert request.model_name not in promotion_manager._rollout_current_stage
        assert request.model_name not in promotion_manager._rollout_baseline_metrics
        assert request.model_name not in promotion_manager._canary_traffic_split

    @pytest.mark.asyncio
    async def test_gradual_rollout_cleanup_on_failure(self, promotion_manager):
        """Testa que estado é limpo após rollback."""
        # Arrange
        request = PromotionRequest(
            request_id="test_promo_11",
            model_name="duration_predictor",
            source_version="v2.0",
            config=PromotionConfig(
                gradual_rollout_enabled=True,
                rollout_stages=[0.25, 0.50, 1.0],
                checkpoint_duration_minutes=0.001,
                auto_rollback_enabled=True,
                checkpoint_mae_threshold_pct=10.0  # Baixo threshold
            )
        )

        # Mock métricas que causam rollback
        baseline_metrics = {'mae_pct': 10.0, 'sample_count': 100}
        degraded_metrics = {'mae_pct': 15.0, 'sample_count': 100}

        promotion_manager._collect_current_metrics = AsyncMock(
            side_effect=[baseline_metrics, degraded_metrics]
        )

        promotion_manager._execute_rollback = AsyncMock()

        # Act
        await promotion_manager._run_gradual_rollout(request)

        # Assert - estado deve estar limpo
        assert request.model_name not in promotion_manager._rollout_current_stage
        assert request.model_name not in promotion_manager._rollout_baseline_metrics
        assert request.model_name not in promotion_manager._canary_traffic_split

    @pytest.mark.asyncio
    async def test_gradual_rollout_error_rate_rollback(self, promotion_manager, mock_metrics):
        """Testa rollback automático por error rate elevado via _collect_current_metrics."""
        # Arrange
        request = PromotionRequest(
            request_id="test_promo_12",
            model_name="duration_predictor",
            source_version="v2.0",
            config=PromotionConfig(
                gradual_rollout_enabled=True,
                rollout_stages=[0.25, 0.50, 1.0],
                checkpoint_duration_minutes=0.001,
                auto_rollback_enabled=True,
                checkpoint_mae_threshold_pct=50.0,  # Alto threshold MAE para não triggar
                checkpoint_error_rate_threshold=0.001  # 0.1% threshold
            )
        )

        # Mock métricas: baseline OK, checkpoint com error_rate elevado
        baseline_metrics = {'mae_pct': 10.0, 'sample_count': 100, 'error_rate': 0.0}
        high_error_rate_metrics = {'mae_pct': 10.0, 'sample_count': 100, 'error_rate': 0.01}  # 1% > 0.1%

        promotion_manager._collect_current_metrics = AsyncMock(
            side_effect=[baseline_metrics, high_error_rate_metrics]
        )

        promotion_manager._execute_rollback = AsyncMock()

        # Act
        result = await promotion_manager._run_gradual_rollout(request)

        # Assert
        assert result is False
        assert promotion_manager._execute_rollback.called
        assert request.error_message is not None
        mock_metrics.record_rollout_degradation.assert_called()

    @pytest.mark.asyncio
    async def test_collect_current_metrics_returns_error_rate(self, mock_config, mock_model_registry, mock_mongodb, mock_metrics):
        """Testa que _collect_current_metrics retorna error_rate do continuous_validator."""
        # Arrange - criar validator que retorna error_rate
        validator_with_error_rate = MagicMock()
        validator_with_error_rate.get_current_metrics = MagicMock(return_value={
            '24h': {
                'mae': 500,
                'mae_pct': 10.0,
                'sample_count': 100,
                'error_rate': 0.005  # 0.5% error rate
            }
        })

        manager = ModelPromotionManager(
            config=mock_config,
            model_registry=mock_model_registry,
            continuous_validator=validator_with_error_rate,
            mongodb_client=mock_mongodb,
            metrics=mock_metrics
        )

        # Act
        metrics = await manager._collect_current_metrics("duration_predictor")

        # Assert
        assert 'error_rate' in metrics
        assert metrics['error_rate'] == 0.005
        assert metrics['mae_pct'] == 10.0
        assert metrics['sample_count'] == 100


class TestPromotionConfigGradualRollout:
    """Testes para configuração de gradual rollout."""

    def test_default_config_values(self):
        """Testa valores padrão da configuração."""
        config = PromotionConfig()

        assert config.gradual_rollout_enabled is True
        assert config.rollout_stages == [0.25, 0.50, 0.75, 1.0]
        assert config.checkpoint_duration_minutes == 30
        assert config.checkpoint_mae_threshold_pct == 20.0
        assert config.checkpoint_error_rate_threshold == 0.001

    def test_custom_config_values(self):
        """Testa valores customizados da configuração."""
        config = PromotionConfig(
            gradual_rollout_enabled=False,
            rollout_stages=[0.10, 0.25, 0.50, 0.75, 1.0],
            checkpoint_duration_minutes=60,
            checkpoint_mae_threshold_pct=30.0,
            checkpoint_error_rate_threshold=0.005
        )

        assert config.gradual_rollout_enabled is False
        assert config.rollout_stages == [0.10, 0.25, 0.50, 0.75, 1.0]
        assert config.checkpoint_duration_minutes == 60
        assert config.checkpoint_mae_threshold_pct == 30.0
        assert config.checkpoint_error_rate_threshold == 0.005
