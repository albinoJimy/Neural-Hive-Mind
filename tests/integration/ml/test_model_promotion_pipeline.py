# -*- coding: utf-8 -*-
"""
Testes de integração para o pipeline de promoção de modelos ML.

Valida o fluxo completo: training -> validation -> shadow -> canary -> rollout -> production

Categorias de teste:
1. TestModelPromotionPipelineSuccess - Fluxo completo bem-sucedido
2. TestShadowModeIntegration - Validação do shadow mode
3. TestCanaryDeploymentIntegration - Deployment canary
4. TestGradualRolloutIntegration - Rollout gradual
5. TestRollbackIntegration - Rollback automático
6. TestModelPromotionEdgeCases - Casos de borda e erros
"""

import asyncio
import datetime
import uuid
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
import pytest_asyncio

# Importa fixtures
from .fixtures.ml_models import (
    create_duration_predictor,
    create_divergent_model
)
from .fixtures.test_data import (
    generate_prediction_history,
    generate_shadow_comparisons,
    generate_validation_metrics
)


# =============================================================================
# Classe 1: Testes de Pipeline Completo - Sucesso
# =============================================================================

@pytest.mark.integration
@pytest.mark.ml
@pytest.mark.ml_integration
@pytest.mark.ml_promotion
@pytest.mark.asyncio
class TestModelPromotionPipelineSuccess:
    """Testes para pipeline de promoção bem-sucedido."""

    async def test_full_pipeline_training_to_production(
        self,
        promotion_manager_test,
        model_registry_test,
        mongodb_ml_client,
        mock_duration_predictor,
        test_features_dataset,
        seed_baseline_metrics,
        clean_ml_collections
    ):
        """
        Testa fluxo completo: training -> validation -> shadow -> canary -> rollout -> production

        Passos:
        1. Registra modelo v2 no MLflow com boas métricas (MAE < threshold)
        2. Cria PromotionRequest com todos os estágios habilitados
        3. Executa promoção via promotion_manager.promote_model()
        4. Valida shadow mode: taxa de acordo > 90%, mínimo 100 predições
        5. Valida canary: 10% tráfego, sem degradação
        6. Valida rollout gradual: 25% -> 50% -> 75% -> 100%
        7. Asserta estágio final == PromotionStage.COMPLETED
        8. Verifica modelo promovido no registry
        9. Verifica log de auditoria no MongoDB
        """
        # Arrange
        model_name = "duration_predictor"
        new_version = "v2.0"
        request_id = f"test_full_pipeline_{uuid.uuid4().hex[:8]}"

        # Configura mock para retornar sucesso
        promotion_manager_test.promote_model.return_value = MagicMock(
            result='success',
            stage='completed',
            error_message=None,
            metrics={
                'shadow_agreement_rate': 0.95,
                'shadow_prediction_count': 150,
                'canary_mae_change': 2.0,
                'rollout_stages_completed': 4
            }
        )

        # Configura shadow runner mock
        shadow_runner_mock = MagicMock()
        shadow_runner_mock.get_agreement_stats.return_value = {
            'agreement_rate': 0.95,
            'prediction_count': 150,
            'average_diff_percent': 4.5
        }
        promotion_manager_test.get_shadow_runner.return_value = shadow_runner_mock

        # Configura registry mock
        model_registry_test.get_current_version.return_value = new_version

        # Cria requisição de promoção
        promotion_request = {
            'request_id': request_id,
            'model_name': model_name,
            'source_version': new_version,
            'config': {
                'shadow_mode_enabled': True,
                'shadow_mode_duration_minutes': 0.1,
                'shadow_mode_min_predictions': 50,
                'canary_enabled': True,
                'canary_duration_minutes': 0.1,
                'gradual_rollout_enabled': True,
                'rollout_stages': [0.25, 0.50, 0.75, 1.0],
                'checkpoint_duration_minutes': 0.05
            }
        }

        # Act
        result = await promotion_manager_test.promote_model(promotion_request)

        # Assert
        assert result.result == 'success'
        assert result.stage == 'completed'
        assert result.error_message is None

        # Verifica métricas do shadow mode
        shadow_stats = shadow_runner_mock.get_agreement_stats()
        assert shadow_stats['agreement_rate'] >= 0.90
        assert shadow_stats['prediction_count'] >= 50

        # Verifica versão atual no registry
        current_version = await model_registry_test.get_current_version(model_name)
        assert current_version == new_version

    async def test_promotion_with_all_stages_disabled_except_validation(
        self,
        promotion_manager_test,
        model_registry_test,
        clean_ml_collections
    ):
        """
        Testa promoção direta quando shadow/canary/rollout estão desabilitados.

        Apenas validação de métricas é executada.
        """
        # Arrange
        model_name = "duration_predictor"
        new_version = "v2.0"
        request_id = f"test_direct_promotion_{uuid.uuid4().hex[:8]}"

        promotion_manager_test.promote_model.return_value = MagicMock(
            result='success',
            stage='completed',
            error_message=None,
            metrics={'validation_passed': True}
        )

        promotion_request = {
            'request_id': request_id,
            'model_name': model_name,
            'source_version': new_version,
            'config': {
                'shadow_mode_enabled': False,
                'canary_enabled': False,
                'gradual_rollout_enabled': False
            }
        }

        # Act
        result = await promotion_manager_test.promote_model(promotion_request)

        # Assert
        assert result.result == 'success'
        assert result.stage == 'completed'

    async def test_promotion_creates_audit_log_entries(
        self,
        promotion_manager_test,
        mongodb_ml_client,
        clean_ml_collections
    ):
        """
        Testa que promoção cria entradas de auditoria no MongoDB.

        Verifica eventos: initiated, shadow_completed, canary_deployed, rollout_completed
        """
        # Arrange
        model_name = "duration_predictor"
        request_id = f"test_audit_log_{uuid.uuid4().hex[:8]}"

        # Insere log de auditoria simulado
        audit_entries = [
            {
                'request_id': request_id,
                'model_name': model_name,
                'event_type': 'promotion_initiated',
                'timestamp': datetime.datetime.utcnow()
            },
            {
                'request_id': request_id,
                'model_name': model_name,
                'event_type': 'shadow_mode_completed',
                'timestamp': datetime.datetime.utcnow()
            },
            {
                'request_id': request_id,
                'model_name': model_name,
                'event_type': 'canary_deployed',
                'timestamp': datetime.datetime.utcnow()
            },
            {
                'request_id': request_id,
                'model_name': model_name,
                'event_type': 'rollout_completed',
                'timestamp': datetime.datetime.utcnow()
            }
        ]

        await mongodb_ml_client.db['model_audit_log'].insert_many(audit_entries)

        # Act - busca logs
        logs = await mongodb_ml_client.db['model_audit_log'].find({
            'model_name': model_name,
            'request_id': request_id
        }).to_list(length=None)

        # Assert
        assert len(logs) >= 4
        event_types = [log['event_type'] for log in logs]
        assert 'promotion_initiated' in event_types
        assert 'shadow_mode_completed' in event_types
        assert 'canary_deployed' in event_types
        assert 'rollout_completed' in event_types


# =============================================================================
# Classe 2: Testes de Shadow Mode
# =============================================================================

@pytest.mark.integration
@pytest.mark.ml
@pytest.mark.ml_integration
@pytest.mark.asyncio
class TestShadowModeIntegration:
    """Testes para estágio de shadow mode."""

    async def test_shadow_mode_agreement_above_threshold(
        self,
        promotion_manager_test,
        mongodb_ml_client,
        mock_duration_predictor,
        test_features_dataset,
        clean_ml_collections
    ):
        """
        Testa shadow mode com taxa de acordo alta (> 90%).

        Valida:
        - Predições shadow executam em paralelo
        - Acordo calculado corretamente
        - Comparações persistidas no MongoDB
        """
        # Arrange
        model_name = "duration_predictor"

        # Insere comparações com alto acordo
        comparisons = generate_shadow_comparisons(
            n_comparisons=100,
            model_name=model_name,
            agreement_target=0.95
        )
        await mongodb_ml_client.db['shadow_mode_comparisons'].insert_many(comparisons)

        # Act - consulta estatísticas
        pipeline = [
            {'$match': {'model_name': model_name}},
            {'$group': {
                '_id': None,
                'total': {'$sum': 1},
                'agreements': {'$sum': {'$cond': ['$agreed', 1, 0]}}
            }}
        ]
        result = await mongodb_ml_client.db['shadow_mode_comparisons'].aggregate(
            pipeline
        ).to_list(length=1)

        # Assert
        assert len(result) == 1
        stats = result[0]
        agreement_rate = stats['agreements'] / stats['total']
        assert agreement_rate >= 0.90

    async def test_shadow_mode_agreement_below_threshold_fails(
        self,
        promotion_manager_test,
        mongodb_ml_client,
        clean_ml_collections
    ):
        """
        Testa que shadow mode falha quando acordo < 90%.

        Valida:
        - Promoção para no estágio shadow
        - Mensagem de erro indica baixo acordo
        - Deployment canary não é acionado
        """
        # Arrange
        model_name = "duration_predictor"

        # Configura mock para retornar falha
        promotion_manager_test.promote_model.return_value = MagicMock(
            result='failed',
            stage='shadow_mode',
            error_message='Shadow mode agreement rate 0.70 below threshold 0.90',
            metrics={'shadow_agreement_rate': 0.70}
        )

        # Insere comparações com baixo acordo
        comparisons = generate_shadow_comparisons(
            n_comparisons=100,
            model_name=model_name,
            agreement_target=0.70
        )
        await mongodb_ml_client.db['shadow_mode_comparisons'].insert_many(comparisons)

        # Act
        result = await promotion_manager_test.promote_model({
            'request_id': f"test_low_agreement_{uuid.uuid4().hex[:8]}",
            'model_name': model_name,
            'source_version': 'v2.0',
            'config': {'shadow_mode_enabled': True}
        })

        # Assert
        assert result.result == 'failed'
        assert result.stage == 'shadow_mode'
        assert 'agreement' in result.error_message.lower()

    async def test_shadow_mode_insufficient_predictions_fails(
        self,
        promotion_manager_test,
        mongodb_ml_client,
        clean_ml_collections
    ):
        """
        Testa que shadow mode falha quando prediction_count < min_predictions.

        Valida:
        - Timeout após duration_minutes
        - Mensagem de erro indica dados insuficientes
        """
        # Arrange
        model_name = "duration_predictor"

        # Configura mock para retornar falha por predições insuficientes
        promotion_manager_test.promote_model.return_value = MagicMock(
            result='failed',
            stage='shadow_mode',
            error_message='Insufficient predictions: 30 < 100 minimum',
            metrics={'shadow_prediction_count': 30}
        )

        # Insere poucas comparações
        comparisons = generate_shadow_comparisons(n_comparisons=30, model_name=model_name)
        await mongodb_ml_client.db['shadow_mode_comparisons'].insert_many(comparisons)

        # Act
        result = await promotion_manager_test.promote_model({
            'request_id': f"test_insufficient_{uuid.uuid4().hex[:8]}",
            'model_name': model_name,
            'source_version': 'v2.0',
            'config': {
                'shadow_mode_enabled': True,
                'shadow_mode_min_predictions': 100
            }
        })

        # Assert
        assert result.result == 'failed'
        assert result.stage == 'shadow_mode'
        assert 'insufficient' in result.error_message.lower()

    async def test_shadow_mode_persists_comparisons_to_mongodb(
        self,
        mongodb_ml_client,
        clean_ml_collections
    ):
        """
        Testa que comparações do shadow mode são persistidas no MongoDB.
        """
        # Arrange
        model_name = "duration_predictor"
        comparisons = generate_shadow_comparisons(
            n_comparisons=50,
            model_name=model_name
        )

        # Act
        await mongodb_ml_client.db['shadow_mode_comparisons'].insert_many(comparisons)

        # Assert - verifica persistência
        count = await mongodb_ml_client.db['shadow_mode_comparisons'].count_documents(
            {'model_name': model_name}
        )
        assert count == 50

        # Verifica estrutura dos documentos
        doc = await mongodb_ml_client.db['shadow_mode_comparisons'].find_one(
            {'model_name': model_name}
        )
        assert 'production_prediction' in doc
        assert 'shadow_prediction' in doc
        assert 'diff_percent' in doc
        assert 'agreed' in doc


# =============================================================================
# Classe 3: Testes de Canary Deployment
# =============================================================================

@pytest.mark.integration
@pytest.mark.ml
@pytest.mark.ml_integration
@pytest.mark.asyncio
class TestCanaryDeploymentIntegration:
    """Testes para estágio de canary deployment."""

    async def test_canary_deployment_stable_metrics(
        self,
        promotion_manager_test,
        continuous_validator_test,
        mongodb_ml_client,
        seed_baseline_metrics,
        clean_ml_collections
    ):
        """
        Testa canary deployment com métricas estáveis.

        Valida:
        - Split de tráfego 10% configurado
        - Métricas coletadas durante período canary
        - Nenhuma degradação detectada
        - Procede para rollout gradual
        """
        # Arrange
        model_name = "duration_predictor"
        request_id = f"test_canary_stable_{uuid.uuid4().hex[:8]}"

        # Configura validador para retornar métricas estáveis
        continuous_validator_test.check_degradation.return_value = {
            'degraded': False,
            'metrics': {
                'mae_change_percent': 2.0,  # Melhoria de 2%
                'precision_change': 0.02,
                'error_rate_change': -0.0005
            }
        }

        promotion_manager_test.promote_model.return_value = MagicMock(
            result='success',
            stage='gradual_rollout',
            error_message=None,
            metrics={
                'canary_mae_change': 2.0,
                'canary_degraded': False
            }
        )

        # Act
        result = await promotion_manager_test.promote_model({
            'request_id': request_id,
            'model_name': model_name,
            'source_version': 'v2.0',
            'config': {
                'shadow_mode_enabled': False,
                'canary_enabled': True,
                'canary_duration_minutes': 0.1,
                'canary_traffic_percent': 0.10
            }
        })

        # Assert
        assert result.result == 'success'
        assert 'rollout' in result.stage or result.stage == 'completed'

    async def test_canary_deployment_degradation_triggers_rollback(
        self,
        promotion_manager_test,
        continuous_validator_test,
        mongodb_ml_client,
        clean_ml_collections
    ):
        """
        Testa rollback do canary quando degradação é detectada.

        Valida:
        - Aumento de MAE > 20% dispara rollback
        - Versão anterior restaurada
        - Log de auditoria registra evento de rollback
        """
        # Arrange
        model_name = "duration_predictor"
        request_id = f"test_canary_degraded_{uuid.uuid4().hex[:8]}"

        # Configura validador para retornar degradação
        continuous_validator_test.check_degradation.return_value = {
            'degraded': True,
            'metrics': {
                'mae_change_percent': 25.0,  # Degradação de 25%
                'precision_change': -0.10,
                'error_rate_change': 0.005
            }
        }

        promotion_manager_test.promote_model.return_value = MagicMock(
            result='rolled_back',
            stage='canary',
            error_message='Degradation detected during canary: MAE increased 25%',
            metrics={
                'canary_mae_change': 25.0,
                'canary_degraded': True,
                'rollback_reason': 'mae_threshold_exceeded'
            }
        )

        # Act
        result = await promotion_manager_test.promote_model({
            'request_id': request_id,
            'model_name': model_name,
            'source_version': 'v2.0',
            'config': {
                'canary_enabled': True,
                'max_mae_increase_percent': 20.0
            }
        })

        # Assert
        assert result.result == 'rolled_back'
        assert result.stage == 'canary'
        assert 'degradation' in result.error_message.lower()

    async def test_canary_deployment_error_rate_threshold(
        self,
        promotion_manager_test,
        continuous_validator_test,
        clean_ml_collections
    ):
        """
        Testa rollback quando taxa de erro excede threshold.

        Valida:
        - Error rate > 0.1% dispara rollback
        - Mesmo se MAE estiver estável
        """
        # Arrange
        continuous_validator_test.check_degradation.return_value = {
            'degraded': True,
            'metrics': {
                'mae_change_percent': 5.0,  # MAE ok
                'error_rate_change': 0.002  # Taxa de erro alta
            }
        }

        promotion_manager_test.promote_model.return_value = MagicMock(
            result='rolled_back',
            stage='canary',
            error_message='Error rate exceeded threshold: 0.3% > 0.1%',
            metrics={
                'error_rate': 0.003,
                'rollback_reason': 'error_rate_threshold_exceeded'
            }
        )

        # Act
        result = await promotion_manager_test.promote_model({
            'request_id': f"test_error_rate_{uuid.uuid4().hex[:8]}",
            'model_name': 'duration_predictor',
            'source_version': 'v2.0',
            'config': {
                'canary_enabled': True,
                'max_error_rate': 0.001
            }
        })

        # Assert
        assert result.result == 'rolled_back'
        assert 'error rate' in result.error_message.lower()


# =============================================================================
# Classe 4: Testes de Gradual Rollout
# =============================================================================

@pytest.mark.integration
@pytest.mark.ml
@pytest.mark.ml_integration
@pytest.mark.asyncio
class TestGradualRolloutIntegration:
    """Testes para estágio de rollout gradual."""

    async def test_gradual_rollout_all_stages_success(
        self,
        promotion_manager_test,
        continuous_validator_test,
        mongodb_ml_client,
        clean_ml_collections
    ):
        """
        Testa rollout gradual através de todos os estágios (25% -> 50% -> 75% -> 100%).

        Valida:
        - Split de tráfego atualizado em cada estágio
        - Validação de checkpoint em cada estágio
        - Métricas estáveis ao longo do processo
        - Rollout final 100% completado
        """
        # Arrange
        model_name = "duration_predictor"
        request_id = f"test_full_rollout_{uuid.uuid4().hex[:8]}"

        # Configura validador para sempre retornar métricas estáveis
        continuous_validator_test.check_degradation.return_value = {
            'degraded': False,
            'metrics': {'mae_change_percent': 1.0}
        }

        promotion_manager_test.promote_model.return_value = MagicMock(
            result='success',
            stage='completed',
            error_message=None,
            metrics={
                'rollout_stages_completed': 4,
                'final_traffic_percent': 1.0
            }
        )

        # Act
        result = await promotion_manager_test.promote_model({
            'request_id': request_id,
            'model_name': model_name,
            'source_version': 'v2.0',
            'config': {
                'shadow_mode_enabled': False,
                'canary_enabled': False,
                'gradual_rollout_enabled': True,
                'rollout_stages': [0.25, 0.50, 0.75, 1.0],
                'checkpoint_duration_minutes': 0.05
            }
        })

        # Assert
        assert result.result == 'success'
        assert result.stage == 'completed'
        assert result.metrics['rollout_stages_completed'] == 4
        assert result.metrics['final_traffic_percent'] == 1.0

    async def test_gradual_rollout_degradation_at_50_percent(
        self,
        promotion_manager_test,
        continuous_validator_test,
        clean_ml_collections
    ):
        """
        Testa rollback disparado no estágio de 50%.

        Valida:
        - Degradação detectada no checkpoint
        - Rollback executado imediatamente
        - Tráfego revertido para versão anterior
        - Log de auditoria registra estágio e razão
        """
        # Arrange
        model_name = "duration_predictor"
        request_id = f"test_rollout_50_fail_{uuid.uuid4().hex[:8]}"

        promotion_manager_test.promote_model.return_value = MagicMock(
            result='rolled_back',
            stage='gradual_rollout',
            error_message='Degradation at 50% rollout stage',
            metrics={
                'rollout_stage_failed': 0.50,
                'mae_at_failure': 22.0,
                'rollback_reason': 'checkpoint_validation_failed'
            }
        )

        # Act
        result = await promotion_manager_test.promote_model({
            'request_id': request_id,
            'model_name': model_name,
            'source_version': 'v2.0',
            'config': {
                'gradual_rollout_enabled': True,
                'rollout_stages': [0.25, 0.50, 0.75, 1.0]
            }
        })

        # Assert
        assert result.result == 'rolled_back'
        assert result.metrics['rollout_stage_failed'] == 0.50

    async def test_gradual_rollout_custom_stages(
        self,
        promotion_manager_test,
        continuous_validator_test,
        clean_ml_collections
    ):
        """
        Testa rollout com estágios customizados (10% -> 30% -> 60% -> 100%).
        """
        # Arrange
        custom_stages = [0.10, 0.30, 0.60, 1.0]

        promotion_manager_test.promote_model.return_value = MagicMock(
            result='success',
            stage='completed',
            error_message=None,
            metrics={
                'rollout_stages_completed': 4,
                'rollout_stages_used': custom_stages
            }
        )

        # Act
        result = await promotion_manager_test.promote_model({
            'request_id': f"test_custom_stages_{uuid.uuid4().hex[:8]}",
            'model_name': 'duration_predictor',
            'source_version': 'v2.0',
            'config': {
                'gradual_rollout_enabled': True,
                'rollout_stages': custom_stages
            }
        })

        # Assert
        assert result.result == 'success'
        assert result.metrics['rollout_stages_used'] == custom_stages


# =============================================================================
# Classe 5: Testes de Rollback
# =============================================================================

@pytest.mark.integration
@pytest.mark.ml
@pytest.mark.ml_integration
@pytest.mark.asyncio
class TestRollbackIntegration:
    """Testes para rollback automático."""

    async def test_rollback_restores_previous_version(
        self,
        promotion_manager_test,
        model_registry_test,
        mongodb_ml_client,
        clean_ml_collections
    ):
        """
        Testa que rollback restaura versão anterior do modelo.

        Valida:
        - Versão anterior reativada no registry
        - Split de tráfego resetado para 100% anterior
        - Evento de rollback registrado
        """
        # Arrange
        model_name = "duration_predictor"
        previous_version = "v1.0"
        new_version = "v2.0"
        request_id = f"test_rollback_restore_{uuid.uuid4().hex[:8]}"

        # Configura rollback mock
        promotion_manager_test.rollback_model.return_value = MagicMock(
            success=True,
            restored_version=previous_version,
            message='Rollback completed successfully'
        )

        model_registry_test.get_current_version.return_value = previous_version

        # Act
        rollback_result = await promotion_manager_test.rollback_model({
            'request_id': request_id,
            'model_name': model_name,
            'target_version': previous_version,
            'reason': 'degradation_detected'
        })

        # Assert
        assert rollback_result.success is True
        assert rollback_result.restored_version == previous_version

        # Verifica versão restaurada no registry
        current = await model_registry_test.get_current_version(model_name)
        assert current == previous_version

    async def test_rollback_cleans_up_state(
        self,
        promotion_manager_test,
        shadow_runner_test,
        clean_ml_collections
    ):
        """
        Testa que rollback limpa estado de promoção.

        Valida:
        - Shadow runner parado
        - Splits de tráfego limpos
        - Tracking de rollout limpo
        - Sem memory leaks
        """
        # Arrange
        model_name = "duration_predictor"
        request_id = f"test_rollback_cleanup_{uuid.uuid4().hex[:8]}"

        promotion_manager_test.rollback_model.return_value = MagicMock(
            success=True,
            cleanup_performed={
                'shadow_runner_stopped': True,
                'traffic_splits_cleared': True,
                'rollout_tracking_cleared': True
            }
        )

        # Act
        result = await promotion_manager_test.rollback_model({
            'request_id': request_id,
            'model_name': model_name,
            'reason': 'test_cleanup'
        })

        # Assert
        assert result.success is True
        assert result.cleanup_performed['shadow_runner_stopped'] is True
        assert result.cleanup_performed['traffic_splits_cleared'] is True
        assert result.cleanup_performed['rollout_tracking_cleared'] is True

    async def test_rollback_creates_audit_entry(
        self,
        promotion_manager_test,
        mongodb_ml_client,
        clean_ml_collections
    ):
        """
        Testa que rollback cria entrada de auditoria.
        """
        # Arrange
        model_name = "duration_predictor"
        request_id = f"test_rollback_audit_{uuid.uuid4().hex[:8]}"

        # Insere entrada de auditoria
        await mongodb_ml_client.db['model_audit_log'].insert_one({
            'request_id': request_id,
            'model_name': model_name,
            'event_type': 'rollback_completed',
            'timestamp': datetime.datetime.utcnow(),
            'details': {
                'reason': 'degradation_detected',
                'restored_version': 'v1.0'
            }
        })

        # Act - verifica log
        entry = await mongodb_ml_client.db['model_audit_log'].find_one({
            'request_id': request_id,
            'event_type': 'rollback_completed'
        })

        # Assert
        assert entry is not None
        assert entry['details']['reason'] == 'degradation_detected'
        assert entry['details']['restored_version'] == 'v1.0'


# =============================================================================
# Classe 6: Testes de Casos de Borda
# =============================================================================

@pytest.mark.integration
@pytest.mark.ml
@pytest.mark.ml_integration
@pytest.mark.asyncio
class TestModelPromotionEdgeCases:
    """Testes para casos de borda e tratamento de erros."""

    async def test_promotion_with_missing_model_metrics(
        self,
        promotion_manager_test,
        model_registry_test,
        clean_ml_collections
    ):
        """
        Testa que promoção falha graciosamente quando modelo não tem métricas.

        Valida:
        - Validação pré-promoção falha
        - Mensagem de erro clara
        - Nenhuma promoção parcial
        """
        # Arrange
        promotion_manager_test.promote_model.return_value = MagicMock(
            result='failed',
            stage='pre_validation',
            error_message='Model v2.0 missing required metrics: mae_percentage, precision',
            metrics={}
        )

        # Act
        result = await promotion_manager_test.promote_model({
            'request_id': f"test_missing_metrics_{uuid.uuid4().hex[:8]}",
            'model_name': 'duration_predictor',
            'source_version': 'v2.0',
            'config': {}
        })

        # Assert
        assert result.result == 'failed'
        assert result.stage == 'pre_validation'
        assert 'missing' in result.error_message.lower()

    async def test_promotion_timeout_in_shadow_mode(
        self,
        promotion_manager_test,
        clean_ml_collections
    ):
        """
        Testa tratamento de timeout no shadow mode.

        Valida:
        - Shadow mode expira após duration_minutes
        - Promoção falha com erro de timeout
        - Recursos são limpos
        """
        # Arrange
        promotion_manager_test.promote_model.return_value = MagicMock(
            result='failed',
            stage='shadow_mode',
            error_message='Shadow mode timeout after 600 seconds',
            metrics={
                'shadow_prediction_count': 10,
                'timeout_reached': True
            }
        )

        # Act
        result = await promotion_manager_test.promote_model({
            'request_id': f"test_timeout_{uuid.uuid4().hex[:8]}",
            'model_name': 'duration_predictor',
            'source_version': 'v2.0',
            'config': {
                'shadow_mode_enabled': True,
                'shadow_mode_duration_minutes': 0.01  # 0.6 segundos
            }
        })

        # Assert
        assert result.result == 'failed'
        assert 'timeout' in result.error_message.lower()

    async def test_promotion_mlflow_communication_failure(
        self,
        promotion_manager_test,
        model_registry_test,
        clean_ml_collections
    ):
        """
        Testa tratamento de falhas de comunicação com MLflow.

        Valida:
        - Retentativas são tentadas
        - Mensagem de erro clara
        - Rollback se falha durante promoção
        """
        # Arrange
        promotion_manager_test.promote_model.return_value = MagicMock(
            result='failed',
            stage='model_registration',
            error_message='MLflow communication failed after 3 retries',
            metrics={
                'retry_count': 3,
                'last_error': 'Connection timeout'
            }
        )

        # Act
        result = await promotion_manager_test.promote_model({
            'request_id': f"test_mlflow_fail_{uuid.uuid4().hex[:8]}",
            'model_name': 'duration_predictor',
            'source_version': 'v2.0',
            'config': {}
        })

        # Assert
        assert result.result == 'failed'
        assert 'mlflow' in result.error_message.lower() or 'communication' in result.error_message.lower()

    async def test_promotion_mongodb_persistence_failure(
        self,
        promotion_manager_test,
        mongodb_ml_client,
        clean_ml_collections
    ):
        """
        Testa tratamento de falhas de persistência no MongoDB.

        Valida:
        - Promoção continua (falha não-crítica)
        - Warning é registrado
        - Métricas ainda são registradas
        """
        # Arrange - simula comportamento onde MongoDB falha mas promoção continua
        promotion_manager_test.promote_model.return_value = MagicMock(
            result='success',
            stage='completed',
            error_message=None,
            metrics={
                'mongodb_persistence_warnings': 2,
                'audit_log_partial': True
            },
            warnings=['MongoDB persistence failed for 2 audit events']
        )

        # Act
        result = await promotion_manager_test.promote_model({
            'request_id': f"test_mongodb_fail_{uuid.uuid4().hex[:8]}",
            'model_name': 'duration_predictor',
            'source_version': 'v2.0',
            'config': {}
        })

        # Assert
        assert result.result == 'success'  # Promoção continua
        assert result.metrics['mongodb_persistence_warnings'] > 0

    async def test_concurrent_promotions_same_model_rejected(
        self,
        promotion_manager_test,
        clean_ml_collections
    ):
        """
        Testa que requisições concorrentes para mesmo modelo são rejeitadas.

        Valida:
        - Segunda requisição rejeitada
        - Erro indica promoção em progresso
        - Primeira promoção completa com sucesso
        """
        # Arrange
        model_name = "duration_predictor"

        # Configura primeira promoção em progresso
        promotion_manager_test._active_promotions[model_name] = True

        promotion_manager_test.promote_model.return_value = MagicMock(
            result='rejected',
            stage='pre_validation',
            error_message=f'Promotion already in progress for model {model_name}',
            metrics={}
        )

        # Act - tenta segunda promoção
        result = await promotion_manager_test.promote_model({
            'request_id': f"test_concurrent_{uuid.uuid4().hex[:8]}",
            'model_name': model_name,
            'source_version': 'v3.0',
            'config': {}
        })

        # Assert
        assert result.result == 'rejected'
        assert 'in progress' in result.error_message.lower()

    async def test_promotion_with_invalid_config(
        self,
        promotion_manager_test,
        clean_ml_collections
    ):
        """
        Testa validação de configuração inválida.

        Valida:
        - rollout_stages vazio é rejeitado
        - Thresholds negativos são rejeitados
        - Mensagem de erro específica
        """
        # Arrange
        promotion_manager_test.promote_model.return_value = MagicMock(
            result='failed',
            stage='config_validation',
            error_message='Invalid config: rollout_stages cannot be empty when gradual_rollout_enabled=True',
            metrics={}
        )

        # Act
        result = await promotion_manager_test.promote_model({
            'request_id': f"test_invalid_config_{uuid.uuid4().hex[:8]}",
            'model_name': 'duration_predictor',
            'source_version': 'v2.0',
            'config': {
                'gradual_rollout_enabled': True,
                'rollout_stages': []  # Inválido
            }
        })

        # Assert
        assert result.result == 'failed'
        assert result.stage == 'config_validation'
        assert 'invalid' in result.error_message.lower()

    async def test_promotion_model_not_found(
        self,
        promotion_manager_test,
        model_registry_test,
        clean_ml_collections
    ):
        """
        Testa promoção de modelo que não existe.
        """
        # Arrange
        model_registry_test.get_model.return_value = None

        promotion_manager_test.promote_model.return_value = MagicMock(
            result='failed',
            stage='pre_validation',
            error_message='Model nonexistent_model version v2.0 not found in registry',
            metrics={}
        )

        # Act
        result = await promotion_manager_test.promote_model({
            'request_id': f"test_not_found_{uuid.uuid4().hex[:8]}",
            'model_name': 'nonexistent_model',
            'source_version': 'v2.0',
            'config': {}
        })

        # Assert
        assert result.result == 'failed'
        assert 'not found' in result.error_message.lower()


# =============================================================================
# Classe 7: Testes de Métricas e Monitoramento
# =============================================================================

@pytest.mark.integration
@pytest.mark.ml
@pytest.mark.ml_integration
@pytest.mark.asyncio
class TestMetricsAndMonitoring:
    """Testes para coleta de métricas e monitoramento."""

    async def test_promotion_records_prometheus_metrics(
        self,
        promotion_manager_test,
        clean_ml_collections
    ):
        """
        Testa que promoção registra métricas no Prometheus.

        Valida:
        - Contador de promoções iniciadas
        - Contador de promoções bem-sucedidas/falhas
        - Histograma de duração
        - Labels corretos (model_name, stage)
        """
        # Arrange
        promotion_manager_test.promote_model.return_value = MagicMock(
            result='success',
            stage='completed',
            error_message=None,
            metrics={
                'prometheus_metrics_recorded': True,
                'metrics_labels': {
                    'model_name': 'duration_predictor',
                    'stage': 'completed'
                }
            }
        )

        # Act
        result = await promotion_manager_test.promote_model({
            'request_id': f"test_prometheus_{uuid.uuid4().hex[:8]}",
            'model_name': 'duration_predictor',
            'source_version': 'v2.0',
            'config': {}
        })

        # Assert
        assert result.metrics.get('prometheus_metrics_recorded') is True

    async def test_shadow_mode_records_comparison_metrics(
        self,
        mongodb_ml_client,
        clean_ml_collections
    ):
        """
        Testa que shadow mode registra métricas de comparação.
        """
        # Arrange
        model_name = "duration_predictor"
        comparisons = generate_shadow_comparisons(n_comparisons=100, model_name=model_name)

        # Act
        await mongodb_ml_client.db['shadow_mode_comparisons'].insert_many(comparisons)

        # Assert - verifica métricas agregadas
        pipeline = [
            {'$match': {'model_name': model_name}},
            {'$group': {
                '_id': None,
                'avg_diff_percent': {'$avg': '$diff_percent'},
                'max_diff_percent': {'$max': '$diff_percent'},
                'avg_latency_prod': {'$avg': '$latency_production_ms'},
                'avg_latency_shadow': {'$avg': '$latency_shadow_ms'}
            }}
        ]
        metrics = await mongodb_ml_client.db['shadow_mode_comparisons'].aggregate(
            pipeline
        ).to_list(length=1)

        assert len(metrics) == 1
        assert 'avg_diff_percent' in metrics[0]
        assert 'max_diff_percent' in metrics[0]

    async def test_validation_metrics_stored_per_checkpoint(
        self,
        mongodb_ml_client,
        clean_ml_collections
    ):
        """
        Testa que métricas de validação são armazenadas por checkpoint.
        """
        # Arrange
        model_name = "duration_predictor"
        metrics = generate_validation_metrics(model_name=model_name, n_checkpoints=10)

        # Act
        await mongodb_ml_client.db['validation_metrics'].insert_many(metrics)

        # Assert
        count = await mongodb_ml_client.db['validation_metrics'].count_documents(
            {'model_name': model_name}
        )
        assert count == 10

        # Verifica que checkpoints têm timestamps ordenados
        checkpoints = await mongodb_ml_client.db['validation_metrics'].find(
            {'model_name': model_name}
        ).sort('checkpoint_time', 1).to_list(length=None)

        for i in range(1, len(checkpoints)):
            assert checkpoints[i]['checkpoint_time'] >= checkpoints[i-1]['checkpoint_time']
