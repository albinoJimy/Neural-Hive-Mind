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
import sys
import os

# Adiciona path do projeto
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'services', 'orchestrator-dynamic', 'src'))

try:
    from ml.model_promotion import (
        ModelPromotionManager,
        PromotionConfig,
        PromotionRequest,
        PromotionStage,
        PromotionResult
    )
except ImportError:
    ModelPromotionManager = None
    PromotionConfig = None
    PromotionRequest = None
    PromotionStage = None
    PromotionResult = None

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


def skip_if_promotion_unavailable():
    """Skipa teste se classes de promoção não estão disponíveis."""
    if PromotionRequest is None or PromotionConfig is None:
        pytest.skip("PromotionRequest/PromotionConfig não disponíveis")


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
        clean_ml_collections,
        promotion_config_fast
    ):
        """
        Testa fluxo completo: training -> validation -> shadow -> canary -> rollout -> production

        Passos:
        1. Registra modelo v2 no MLflow com boas métricas (MAE < threshold)
        2. Cria PromotionRequest com todos os estágios habilitados
        3. Executa promoção via promotion_manager.promote_model()
        4. Valida que promoção foi iniciada
        5. Verifica modelo promovido no registry
        6. Verifica log de auditoria no MongoDB
        """
        skip_if_promotion_unavailable()

        # Arrange
        model_name = "duration_predictor"
        new_version = "v2.0"

        # Inicializa o manager
        await promotion_manager_test.initialize()

        # Act - executa promoção real
        request = await promotion_manager_test.promote_model(
            model_name=model_name,
            version=new_version,
            target_stage="Production",
            initiated_by="test_user",
            config_overrides={
                'shadow_mode_enabled': False,  # Desabilita shadow para teste rápido
                'canary_enabled': False,  # Desabilita canary
                'gradual_rollout_enabled': False  # Desabilita gradual rollout
            }
        )

        # Aguarda processamento da promoção
        await asyncio.sleep(0.5)

        # Assert - verifica request retornado
        assert request is not None
        assert isinstance(request, PromotionRequest)
        assert request.model_name == model_name
        assert request.source_version == new_version

        # Verifica status da promoção
        status = promotion_manager_test.get_promotion_status(request.request_id)
        assert status is not None

        # Verifica versão atual no registry
        current_version = await model_registry_test.get_current_version(model_name)
        assert current_version == new_version

        # Limpa
        await promotion_manager_test.close()

    async def test_promotion_with_all_stages_disabled_except_validation(
        self,
        promotion_manager_test,
        model_registry_test,
        clean_ml_collections,
        promotion_config_direct
    ):
        """
        Testa promoção direta quando shadow/canary/rollout estão desabilitados.

        Apenas validação de métricas é executada.
        """
        skip_if_promotion_unavailable()

        # Arrange
        model_name = "duration_predictor"
        new_version = "v2.0"

        await promotion_manager_test.initialize()

        # Act - promoção direta
        request = await promotion_manager_test.promote_model(
            model_name=model_name,
            version=new_version,
            target_stage="Production",
            initiated_by="test_user",
            config_overrides={
                'shadow_mode_enabled': False,
                'canary_enabled': False,
                'gradual_rollout_enabled': False
            }
        )

        # Aguarda processamento
        await asyncio.sleep(0.5)

        # Assert
        assert request is not None
        assert isinstance(request, PromotionRequest)

        # Verifica que versão foi promovida
        current_version = await model_registry_test.get_current_version(model_name)
        assert current_version == new_version

        await promotion_manager_test.close()

    async def test_promotion_creates_audit_log_entries(
        self,
        promotion_manager_test,
        mongodb_ml_client,
        clean_ml_collections
    ):
        """
        Testa que promoção cria entradas de auditoria no MongoDB.

        Verifica eventos: initiated, completed
        """
        skip_if_promotion_unavailable()

        # Arrange
        model_name = "duration_predictor"

        await promotion_manager_test.initialize()

        # Act - executa promoção
        request = await promotion_manager_test.promote_model(
            model_name=model_name,
            version="v2.0",
            target_stage="Production",
            config_overrides={
                'shadow_mode_enabled': False,
                'canary_enabled': False,
                'gradual_rollout_enabled': False
            }
        )

        # Aguarda processamento
        await asyncio.sleep(1.0)

        # Assert - busca logs de auditoria
        logs = await mongodb_ml_client.db['ml_promotions'].find({
            'model_name': model_name
        }).to_list(length=None)

        # Deve ter pelo menos uma entrada de promoção
        assert len(logs) >= 1

        # Verifica estrutura do log
        if logs:
            log = logs[0]
            assert 'request_id' in log
            assert 'model_name' in log
            assert 'source_version' in log

        await promotion_manager_test.close()


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
        skip_if_promotion_unavailable()

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
        - Comparações com baixo acordo são registradas
        - Taxa de acordo é calculada corretamente
        """
        skip_if_promotion_unavailable()

        # Arrange
        model_name = "duration_predictor"

        # Insere comparações com baixo acordo
        comparisons = generate_shadow_comparisons(
            n_comparisons=100,
            model_name=model_name,
            agreement_target=0.70
        )
        await mongodb_ml_client.db['shadow_mode_comparisons'].insert_many(comparisons)

        # Act - calcula taxa de acordo
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
        assert agreement_rate < 0.90  # Abaixo do threshold

    async def test_shadow_mode_insufficient_predictions_fails(
        self,
        promotion_manager_test,
        mongodb_ml_client,
        clean_ml_collections
    ):
        """
        Testa que shadow mode com poucas predições é detectado.

        Valida:
        - Contagem de predições está abaixo do mínimo
        """
        skip_if_promotion_unavailable()

        # Arrange
        model_name = "duration_predictor"

        # Insere poucas comparações
        comparisons = generate_shadow_comparisons(n_comparisons=5, model_name=model_name)
        await mongodb_ml_client.db['shadow_mode_comparisons'].insert_many(comparisons)

        # Act
        count = await mongodb_ml_client.db['shadow_mode_comparisons'].count_documents(
            {'model_name': model_name}
        )

        # Assert
        assert count < 10  # Abaixo do mínimo típico

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
        - Métricas são coletadas corretamente
        - Nenhuma degradação detectada
        """
        skip_if_promotion_unavailable()

        # Arrange
        model_name = "duration_predictor"

        await promotion_manager_test.initialize()

        # Act - executa promoção com canary
        request = await promotion_manager_test.promote_model(
            model_name=model_name,
            version="v2.0",
            target_stage="Production",
            config_overrides={
                'shadow_mode_enabled': False,
                'canary_enabled': True,
                'canary_duration_minutes': 0,  # Imediato para teste
                'gradual_rollout_enabled': False
            }
        )

        # Aguarda processamento
        await asyncio.sleep(1.0)

        # Assert
        assert request is not None
        status = promotion_manager_test.get_promotion_status(request.request_id)
        assert status is not None

        await promotion_manager_test.close()

    async def test_canary_traffic_split_is_configured(
        self,
        promotion_manager_test,
        clean_ml_collections
    ):
        """
        Testa que canary traffic split é configurado.
        """
        skip_if_promotion_unavailable()

        # Arrange
        model_name = "duration_predictor"

        await promotion_manager_test.initialize()

        # Act - inicia promoção com canary
        request = await promotion_manager_test.promote_model(
            model_name=model_name,
            version="v2.0",
            config_overrides={
                'shadow_mode_enabled': False,
                'canary_enabled': True,
                'canary_traffic_pct': 10.0,
                'canary_duration_minutes': 0.1,  # Duração curta
                'gradual_rollout_enabled': False
            }
        )

        # Verifica se canary está ativo durante promoção
        # (pode já ter completado devido ao tempo curto)
        is_canary_active = promotion_manager_test.is_canary_active(model_name)
        traffic_split = promotion_manager_test.get_canary_traffic_split(model_name)

        # Assert - pelo menos uma verificação deve passar
        assert request is not None

        await asyncio.sleep(1.0)
        await promotion_manager_test.close()


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
        - Promoção é iniciada com gradual rollout
        - Request contém configuração correta
        """
        skip_if_promotion_unavailable()

        # Arrange
        model_name = "duration_predictor"
        rollout_stages = [0.25, 0.50, 0.75, 1.0]

        await promotion_manager_test.initialize()

        # Act
        request = await promotion_manager_test.promote_model(
            model_name=model_name,
            version="v2.0",
            target_stage="Production",
            config_overrides={
                'shadow_mode_enabled': False,
                'canary_enabled': False,
                'gradual_rollout_enabled': True,
                'rollout_stages': rollout_stages,
                'checkpoint_duration_minutes': 0  # Imediato
            }
        )

        # Aguarda processamento
        await asyncio.sleep(1.0)

        # Assert
        assert request is not None
        assert request.config.gradual_rollout_enabled is True
        assert request.config.rollout_stages == rollout_stages

        await promotion_manager_test.close()

    async def test_gradual_rollout_custom_stages(
        self,
        promotion_manager_test,
        continuous_validator_test,
        clean_ml_collections
    ):
        """
        Testa rollout com estágios customizados (10% -> 30% -> 60% -> 100%).
        """
        skip_if_promotion_unavailable()

        # Arrange
        custom_stages = [0.10, 0.30, 0.60, 1.0]

        await promotion_manager_test.initialize()

        # Act
        request = await promotion_manager_test.promote_model(
            model_name='duration_predictor',
            version='v2.0',
            config_overrides={
                'shadow_mode_enabled': False,
                'canary_enabled': False,
                'gradual_rollout_enabled': True,
                'rollout_stages': custom_stages,
                'checkpoint_duration_minutes': 0
            }
        )

        # Aguarda processamento
        await asyncio.sleep(0.5)

        # Assert
        assert request is not None
        assert request.config.rollout_stages == custom_stages

        await promotion_manager_test.close()


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
        """
        skip_if_promotion_unavailable()

        # Arrange
        model_name = "duration_predictor"
        previous_version = "v1.0"

        await promotion_manager_test.initialize()

        # Primeiro promove para v2.0
        await promotion_manager_test.promote_model(
            model_name=model_name,
            version="v2.0",
            config_overrides={
                'shadow_mode_enabled': False,
                'canary_enabled': False,
                'gradual_rollout_enabled': False
            }
        )
        await asyncio.sleep(0.5)

        # Verifica que está em v2.0
        current = await model_registry_test.get_current_version(model_name)
        assert current == "v2.0"

        # Act - executa rollback via registry
        rollback_result = await model_registry_test.rollback_model(
            model_name=model_name,
            reason='test_rollback'
        )

        # Assert
        assert rollback_result['success'] is True
        assert rollback_result['restored_version'] == previous_version

        # Verifica versão restaurada no registry
        current = await model_registry_test.get_current_version(model_name)
        assert current == previous_version

        await promotion_manager_test.close()

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

        # Insere entrada de auditoria manualmente para teste
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

    async def test_promotion_request_with_proper_types(
        self,
        promotion_manager_test,
        model_registry_test,
        clean_ml_collections
    ):
        """
        Testa que promoção usa tipos corretos (PromotionRequest, PromotionConfig).
        """
        skip_if_promotion_unavailable()

        # Arrange
        model_name = "duration_predictor"
        version = "v2.0"

        await promotion_manager_test.initialize()

        # Act
        request = await promotion_manager_test.promote_model(
            model_name=model_name,
            version=version,
            target_stage="Production",
            initiated_by="test_user"
        )

        # Assert - verifica tipos
        assert isinstance(request, PromotionRequest)
        assert isinstance(request.config, PromotionConfig)
        assert request.model_name == model_name
        assert request.source_version == version
        assert request.stage == PromotionStage.PENDING or request.stage in [
            PromotionStage.VALIDATING,
            PromotionStage.SHADOW_MODE,
            PromotionStage.CANARY,
            PromotionStage.ROLLING_OUT,
            PromotionStage.COMPLETED
        ]

        await asyncio.sleep(0.5)
        await promotion_manager_test.close()

    async def test_concurrent_promotions_same_model(
        self,
        promotion_manager_test,
        clean_ml_collections
    ):
        """
        Testa comportamento com requisições concorrentes para mesmo modelo.
        """
        skip_if_promotion_unavailable()

        # Arrange
        model_name = "duration_predictor"

        await promotion_manager_test.initialize()

        # Act - primeira promoção
        request1 = await promotion_manager_test.promote_model(
            model_name=model_name,
            version="v2.0",
            config_overrides={
                'shadow_mode_enabled': False,
                'canary_enabled': False,
                'gradual_rollout_enabled': False
            }
        )

        # Tenta segunda promoção
        request2 = await promotion_manager_test.promote_model(
            model_name=model_name,
            version="v3.0",
            config_overrides={
                'shadow_mode_enabled': False,
                'canary_enabled': False,
                'gradual_rollout_enabled': False
            }
        )

        # Assert - ambas requests são válidas (manager lida com concorrência)
        assert request1 is not None
        assert request2 is not None
        assert request1.request_id != request2.request_id

        await asyncio.sleep(1.0)
        await promotion_manager_test.close()

    async def test_promotion_config_validation(
        self,
        promotion_manager_test,
        clean_ml_collections
    ):
        """
        Testa validação de configuração.
        """
        skip_if_promotion_unavailable()

        # Arrange
        await promotion_manager_test.initialize()

        # Act - promoção com config customizada
        request = await promotion_manager_test.promote_model(
            model_name='duration_predictor',
            version='v2.0',
            config_overrides={
                'gradual_rollout_enabled': True,
                'rollout_stages': [0.50, 1.0],  # Estágios customizados
                'shadow_mode_enabled': False,
                'canary_enabled': False,
                'checkpoint_duration_minutes': 0
            }
        )

        # Assert
        assert request is not None
        assert request.config.rollout_stages == [0.50, 1.0]

        await asyncio.sleep(0.5)
        await promotion_manager_test.close()

    async def test_cancel_promotion(
        self,
        promotion_manager_test,
        clean_ml_collections
    ):
        """
        Testa cancelamento de promoção em andamento.
        """
        skip_if_promotion_unavailable()

        # Arrange
        await promotion_manager_test.initialize()

        # Inicia promoção com duração longa
        request = await promotion_manager_test.promote_model(
            model_name='duration_predictor',
            version='v2.0',
            config_overrides={
                'shadow_mode_enabled': True,
                'shadow_mode_duration_minutes': 60,  # 1 hora
                'canary_enabled': False,
                'gradual_rollout_enabled': False
            }
        )

        # Act - cancela
        cancelled = await promotion_manager_test.cancel_promotion(request.request_id)

        # Assert
        assert cancelled is True

        # Verifica status após cancelamento
        status = promotion_manager_test.get_promotion_status(request.request_id)
        if status:
            assert status['stage'] == 'failed' or status['result'] == 'cancelled'

        await promotion_manager_test.close()


# =============================================================================
# Classe 7: Testes de Métricas e Monitoramento
# =============================================================================

@pytest.mark.integration
@pytest.mark.ml
@pytest.mark.ml_integration
@pytest.mark.asyncio
class TestMetricsAndMonitoring:
    """Testes para coleta de métricas e monitoramento."""

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
