# -*- coding: utf-8 -*-
"""
Testes de integração para ModelAuditLogger.

Valida o registro e consulta de eventos do ciclo de vida de modelos ML:
1. TestAuditLoggerBasicOperations - Operações básicas de logging
2. TestAuditLoggerQueries - Consultas de histórico e resumo
3. TestAuditLoggerIntegration - Integração com componentes ML
"""

import asyncio
import datetime
import uuid
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import sys
import os

# Adiciona path do projeto
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'services', 'orchestrator-dynamic', 'src'))

try:
    from ml.model_audit_logger import (
        ModelAuditLogger,
        AuditEventContext,
        ModelLifecycleEvent
    )
except ImportError:
    ModelAuditLogger = None
    AuditEventContext = None
    ModelLifecycleEvent = None


def skip_if_audit_logger_unavailable():
    """Skipa teste se ModelAuditLogger não está disponível."""
    if ModelAuditLogger is None:
        pytest.skip("ModelAuditLogger não disponível")


# =============================================================================
# Fixture específica para Audit Logger
# =============================================================================

class MockAuditLoggerConfig:
    """Configuração mock para ModelAuditLogger em testes."""
    ml_audit_log_collection = 'model_audit_log'
    ml_audit_retention_days = 365
    ml_audit_enabled = True
    environment = 'test'


@pytest.fixture
async def audit_logger(mongodb_ml_client, clean_ml_collections):
    """
    ModelAuditLogger configurado para testes.
    """
    skip_if_audit_logger_unavailable()

    mock_metrics = MagicMock()
    mock_metrics.increment_model_audit_event = MagicMock()

    config = MockAuditLoggerConfig()

    logger = ModelAuditLogger(
        mongodb_client=mongodb_ml_client,
        config=config,
        metrics=mock_metrics
    )

    yield logger


class MockAuditLoggerConfigDisabled:
    """Configuração mock para ModelAuditLogger desabilitado."""
    ml_audit_log_collection = 'model_audit_log'
    ml_audit_retention_days = 365
    ml_audit_enabled = False
    environment = 'test'


@pytest.fixture
async def audit_logger_disabled(mongodb_ml_client):
    """
    ModelAuditLogger desabilitado para testes de fail-open.
    """
    skip_if_audit_logger_unavailable()

    config = MockAuditLoggerConfigDisabled()

    logger = ModelAuditLogger(
        mongodb_client=mongodb_ml_client,
        config=config,
        metrics=None
    )

    yield logger


# =============================================================================
# Classe 1: Operações Básicas de Logging
# =============================================================================

@pytest.mark.integration
@pytest.mark.ml
@pytest.mark.ml_integration
@pytest.mark.asyncio
class TestAuditLoggerBasicOperations:
    """Testes para operações básicas de audit logging."""

    async def test_log_training_started(
        self,
        audit_logger,
        mongodb_ml_client,
        event_loop
    ):
        """
        Testa registro de evento training_started.

        Verifica:
        - Evento salvo no MongoDB
        - Campos obrigatórios presentes
        - Métricas incrementadas
        """
        skip_if_audit_logger_unavailable()

        # Arrange
        model_name = "duration_predictor"
        model_version = "v2.0"
        context = AuditEventContext(
            user_id="test_user",
            reason="Retreinamento programado",
            environment="staging",
            triggered_by="scheduler",
            metadata={"run_id": "run_123", "dataset_version": "v1.5"}
        )
        training_config = {
            "model_type": "random_forest",
            "hyperparameters": {"n_estimators": 100},
            "dataset_info": {"size": 10000}
        }

        # Act
        audit_id = await audit_logger.log_training_started(
            model_name=model_name,
            model_version=model_version,
            context=context,
            training_config=training_config
        )

        # Assert
        assert audit_id is not None
        assert isinstance(audit_id, str)

        # Verifica no MongoDB
        event = await mongodb_ml_client.db['model_audit_log'].find_one(
            {'audit_id': audit_id}
        )
        assert event is not None
        assert event['model_name'] == model_name
        assert event['model_version'] == model_version
        assert event['event_type'] == 'training_started'
        assert event['user_id'] == 'test_user'
        assert event['environment'] == 'staging'
        assert event['triggered_by'] == 'scheduler'
        assert 'timestamp' in event

        # Verifica métricas
        audit_logger.metrics.increment_model_audit_event.assert_called_with(
            model_name=model_name,
            event_type='training_started'
        )

    async def test_log_training_completed(
        self,
        audit_logger,
        mongodb_ml_client
    ):
        """
        Testa registro de evento training_completed com métricas.
        """
        skip_if_audit_logger_unavailable()

        # Arrange
        model_name = "duration_predictor"
        model_version = "v2.0"
        training_metrics = {
            'mae_percentage': 8.5,
            'precision': 0.85,
            'training_samples': 10000
        }
        context = AuditEventContext(
            duration_seconds=3600.0,
            metadata={'mlflow_run_id': 'run_456'}
        )

        # Act
        audit_id = await audit_logger.log_training_completed(
            model_name=model_name,
            model_version=model_version,
            metrics=training_metrics,
            context=context
        )

        # Assert
        assert audit_id is not None

        event = await mongodb_ml_client.db['model_audit_log'].find_one(
            {'audit_id': audit_id}
        )
        assert event is not None
        assert event['event_type'] == 'training_completed'
        assert event['duration_seconds'] == 3600.0
        assert event['event_data']['metrics'] == training_metrics

    async def test_log_promotion_initiated(
        self,
        audit_logger,
        mongodb_ml_client
    ):
        """
        Testa registro de evento promotion_initiated.
        """
        skip_if_audit_logger_unavailable()

        # Arrange
        model_name = "duration_predictor"
        model_version = "v2.0"
        request_id = f"promo_{uuid.uuid4().hex[:8]}"
        context = AuditEventContext(
            user_id="ml_engineer",
            triggered_by="manual"
        )
        promotion_config = {
            "target_stage": "Production",
            "request_id": request_id,
            "current_version": "v1.0"
        }

        # Act
        audit_id = await audit_logger.log_promotion_initiated(
            model_name=model_name,
            model_version=model_version,
            context=context,
            promotion_config=promotion_config
        )

        # Assert
        assert audit_id is not None

        event = await mongodb_ml_client.db['model_audit_log'].find_one(
            {'audit_id': audit_id}
        )
        assert event is not None
        assert event['event_type'] == 'promotion_initiated'
        assert event['event_data']['promotion_config']['target_stage'] == "Production"
        assert event['event_data']['current_production_version'] == "v1.0"

    async def test_log_shadow_mode_started(
        self,
        audit_logger,
        mongodb_ml_client
    ):
        """
        Testa registro de evento shadow_mode_started.
        """
        skip_if_audit_logger_unavailable()

        # Arrange
        model_name = "duration_predictor"
        shadow_version = "v2.0"
        context = AuditEventContext(
            user_id="system",
            reason="Shadow mode iniciado",
            environment="production",
            triggered_by="automatic",
            metadata={"production_version": "v1.0"}
        )
        shadow_config = {
            'duration_minutes': 60,
            'min_predictions': 100,
            'agreement_threshold': 0.90,
            'sample_rate': 1.0
        }

        # Act
        audit_id = await audit_logger.log_shadow_mode_started(
            model_name=model_name,
            model_version=shadow_version,
            context=context,
            shadow_config=shadow_config
        )

        # Assert
        assert audit_id is not None

        event = await mongodb_ml_client.db['model_audit_log'].find_one(
            {'audit_id': audit_id}
        )
        assert event is not None
        assert event['event_type'] == 'shadow_mode_started'
        assert event['model_version'] == shadow_version
        assert event['event_data']['duration_minutes'] == 60

    async def test_log_shadow_mode_completed(
        self,
        audit_logger,
        mongodb_ml_client
    ):
        """
        Testa registro de evento shadow_mode_completed com estatísticas.
        """
        skip_if_audit_logger_unavailable()

        # Arrange
        model_name = "duration_predictor"
        shadow_version = "v2.0"
        shadow_results = {
            'prediction_count': 150,
            'agreement_rate': 0.947,
            'avg_latency_ms': 5.2
        }
        context = AuditEventContext(
            duration_seconds=3660.0
        )

        # Act
        audit_id = await audit_logger.log_shadow_mode_completed(
            model_name=model_name,
            model_version=shadow_version,
            context=context,
            shadow_results=shadow_results
        )

        # Assert
        assert audit_id is not None

        event = await mongodb_ml_client.db['model_audit_log'].find_one(
            {'audit_id': audit_id}
        )
        assert event is not None
        assert event['event_type'] == 'shadow_mode_completed'
        assert event['event_data']['agreement_rate'] == 0.947
        assert event['duration_seconds'] == 3660.0

    async def test_log_rollback_executed(
        self,
        audit_logger,
        mongodb_ml_client
    ):
        """
        Testa registro de evento rollback_executed.
        """
        skip_if_audit_logger_unavailable()

        # Arrange
        model_name = "duration_predictor"
        model_version = "v2.0"  # Versão atual sendo revertida
        previous_version = "v1.0"  # Versão para a qual está sendo revertido
        context = AuditEventContext(
            reason="MAE increase > 20%",
            triggered_by="auto_rollback",
            metadata={'mae_increase_pct': 25.3, 'error_rate': 0.005}
        )

        # Act
        audit_id = await audit_logger.log_rollback_executed(
            model_name=model_name,
            model_version=model_version,
            context=context,
            rollback_reason="MAE increase > 20%",
            previous_version=previous_version
        )

        # Assert
        assert audit_id is not None

        event = await mongodb_ml_client.db['model_audit_log'].find_one(
            {'audit_id': audit_id}
        )
        assert event is not None
        assert event['event_type'] == 'rollback_executed'
        assert event['event_data']['rollback_reason'] == "MAE increase > 20%"
        assert event['event_data']['previous_version'] == previous_version
        assert event['reason'] == "MAE increase > 20%"
        assert event['triggered_by'] == 'auto_rollback'

    async def test_log_model_promoted(
        self,
        audit_logger,
        mongodb_ml_client
    ):
        """
        Testa registro de evento model_promoted.
        """
        skip_if_audit_logger_unavailable()

        # Arrange
        model_name = "duration_predictor"
        model_version = "v2.0"
        context = AuditEventContext(
            user_id="ml_engineer",
            duration_seconds=7200.0,
            metadata={'promotion_request_id': 'promo_abc123'}
        )
        promotion_summary = {
            "target_stage": "Production",
            "previous_version": "v1.0",
            "shadow_mode_passed": True,
            "canary_passed": True
        }

        # Act
        audit_id = await audit_logger.log_model_promoted(
            model_name=model_name,
            model_version=model_version,
            context=context,
            promotion_summary=promotion_summary
        )

        # Assert
        assert audit_id is not None

        event = await mongodb_ml_client.db['model_audit_log'].find_one(
            {'audit_id': audit_id}
        )
        assert event is not None
        assert event['event_type'] == 'model_promoted'
        assert event['event_data']['target_stage'] == "Production"
        assert event['duration_seconds'] == 7200.0

    async def test_audit_logger_disabled_returns_empty(
        self,
        audit_logger_disabled
    ):
        """
        Testa que audit logger desabilitado retorna string vazia (fail-open).
        """
        skip_if_audit_logger_unavailable()

        # Act
        audit_id = await audit_logger_disabled.log_training_started(
            model_name="test_model",
            model_version="v1.0",
            context=AuditEventContext(),
            training_config={"model_type": "test"}
        )

        # Assert
        assert audit_id == ''


# =============================================================================
# Classe 2: Consultas de Histórico e Resumo
# =============================================================================

@pytest.mark.integration
@pytest.mark.ml
@pytest.mark.ml_integration
@pytest.mark.asyncio
class TestAuditLoggerQueries:
    """Testes para consultas de audit log."""

    async def test_get_model_history(
        self,
        audit_logger,
        mongodb_ml_client
    ):
        """
        Testa recuperação de histórico de um modelo.
        """
        skip_if_audit_logger_unavailable()

        # Arrange - registra múltiplos eventos
        model_name = "duration_predictor"

        await audit_logger.log_training_started(
            model_name=model_name,
            model_version="v2.0",
            context=AuditEventContext()
        )

        await audit_logger.log_training_completed(
            model_name=model_name,
            model_version="v2.0",
            metrics={'mae_percentage': 8.5},
            context=AuditEventContext(duration_seconds=3600.0)
        )

        await audit_logger.log_model_promoted(
            model_name=model_name,
            model_version="v2.0",
            target_stage="Production",
            context=AuditEventContext()
        )

        # Act
        events = await audit_logger.get_model_history(
            model_name=model_name,
            limit=10
        )

        # Assert
        assert len(events) == 3

        # Verifica ordem (mais recente primeiro)
        event_types = [e['event_type'] for e in events]
        assert event_types[0] == 'model_promoted'
        assert event_types[1] == 'training_completed'
        assert event_types[2] == 'training_started'

    async def test_get_model_history_with_event_type_filter(
        self,
        audit_logger,
        mongodb_ml_client
    ):
        """
        Testa filtro por tipo de evento no histórico.
        """
        skip_if_audit_logger_unavailable()

        # Arrange
        model_name = "duration_predictor"

        await audit_logger.log_training_started(
            model_name=model_name,
            model_version="v2.0",
            context=AuditEventContext()
        )

        await audit_logger.log_training_completed(
            model_name=model_name,
            model_version="v2.0",
            metrics={},
            context=AuditEventContext()
        )

        await audit_logger.log_model_promoted(
            model_name=model_name,
            model_version="v2.0",
            target_stage="Production",
            context=AuditEventContext()
        )

        # Act - filtra apenas eventos de training
        events = await audit_logger.get_model_history(
            model_name=model_name,
            event_types=['training_started', 'training_completed'],
            limit=10
        )

        # Assert
        assert len(events) == 2
        for event in events:
            assert event['event_type'] in ['training_started', 'training_completed']

    async def test_get_events_by_type(
        self,
        audit_logger,
        mongodb_ml_client
    ):
        """
        Testa recuperação de eventos por tipo.
        """
        skip_if_audit_logger_unavailable()

        # Arrange - registra eventos de modelos diferentes
        await audit_logger.log_rollback_executed(
            model_name="model_a",
            from_version="v2.0",
            to_version="v1.0",
            context=AuditEventContext(reason="High error rate")
        )

        await audit_logger.log_rollback_executed(
            model_name="model_b",
            from_version="v3.0",
            to_version="v2.0",
            context=AuditEventContext(reason="Performance degradation")
        )

        await audit_logger.log_training_started(
            model_name="model_a",
            model_version="v3.0",
            context=AuditEventContext()
        )

        # Act
        rollback_events = await audit_logger.get_events_by_type(
            event_type='rollback_executed',
            limit=10
        )

        # Assert
        assert len(rollback_events) == 2
        for event in rollback_events:
            assert event['event_type'] == 'rollback_executed'

    async def test_get_events_by_type_with_date_range(
        self,
        audit_logger,
        mongodb_ml_client
    ):
        """
        Testa filtro por período de data.
        """
        skip_if_audit_logger_unavailable()

        # Arrange
        now = datetime.datetime.utcnow()

        await audit_logger.log_training_started(
            model_name="model_a",
            model_version="v1.0",
            context=AuditEventContext()
        )

        # Act
        events = await audit_logger.get_events_by_type(
            event_type='training_started',
            start_date=now - datetime.timedelta(hours=1),
            end_date=now + datetime.timedelta(hours=1),
            limit=10
        )

        # Assert
        assert len(events) >= 1

    async def test_get_audit_summary(
        self,
        audit_logger,
        mongodb_ml_client
    ):
        """
        Testa geração de resumo de auditoria.
        """
        skip_if_audit_logger_unavailable()

        # Arrange - registra eventos variados
        model_name = "duration_predictor"

        await audit_logger.log_training_started(
            model_name=model_name,
            model_version="v2.0",
            context=AuditEventContext()
        )

        await audit_logger.log_training_completed(
            model_name=model_name,
            model_version="v2.0",
            metrics={},
            context=AuditEventContext()
        )

        await audit_logger.log_promotion_initiated(
            model_name=model_name,
            model_version="v2.0",
            target_stage="Production",
            request_id="req_123",
            context=AuditEventContext()
        )

        await audit_logger.log_model_promoted(
            model_name=model_name,
            model_version="v2.0",
            target_stage="Production",
            context=AuditEventContext()
        )

        # Act
        summary = await audit_logger.get_audit_summary(
            model_name=model_name,
            days=30
        )

        # Assert
        assert summary is not None
        assert summary['model_name'] == model_name
        assert summary['period_days'] == 30
        assert summary['total_events'] == 4
        assert 'events_by_type' in summary
        assert summary['events_by_type'].get('training_started', 0) >= 1
        assert summary['events_by_type'].get('model_promoted', 0) >= 1

    async def test_get_event_by_id(
        self,
        audit_logger,
        mongodb_ml_client
    ):
        """
        Testa recuperação de evento por ID.
        """
        skip_if_audit_logger_unavailable()

        # Arrange
        audit_id = await audit_logger.log_training_started(
            model_name="test_model",
            model_version="v1.0",
            context=AuditEventContext(user_id="test_user")
        )

        # Act
        event = await audit_logger.get_event_by_id(audit_id)

        # Assert
        assert event is not None
        assert event['audit_id'] == audit_id
        assert event['model_name'] == "test_model"
        assert event['user_id'] == "test_user"

    async def test_get_event_by_id_not_found(
        self,
        audit_logger
    ):
        """
        Testa retorno None para ID não encontrado.
        """
        skip_if_audit_logger_unavailable()

        # Act
        event = await audit_logger.get_event_by_id("nonexistent_id_12345")

        # Assert
        assert event is None

    async def test_get_model_timeline(
        self,
        audit_logger,
        mongodb_ml_client
    ):
        """
        Testa geração de timeline de eventos por versão.
        """
        skip_if_audit_logger_unavailable()

        # Arrange
        model_name = "duration_predictor"

        # Eventos para v1.0
        await audit_logger.log_training_started(
            model_name=model_name,
            model_version="v1.0",
            context=AuditEventContext()
        )

        await audit_logger.log_model_promoted(
            model_name=model_name,
            model_version="v1.0",
            target_stage="Production",
            context=AuditEventContext()
        )

        # Eventos para v2.0
        await audit_logger.log_training_started(
            model_name=model_name,
            model_version="v2.0",
            context=AuditEventContext()
        )

        await audit_logger.log_training_completed(
            model_name=model_name,
            model_version="v2.0",
            metrics={'mae_percentage': 8.5},
            context=AuditEventContext()
        )

        # Act
        timeline = await audit_logger.get_model_timeline(
            model_name=model_name,
            days=90
        )

        # Assert
        assert timeline is not None
        assert timeline['model_name'] == model_name
        assert 'versions' in timeline
        assert timeline['total_events'] == 4


# =============================================================================
# Classe 3: Integração com Componentes ML
# =============================================================================

@pytest.mark.integration
@pytest.mark.ml
@pytest.mark.ml_integration
@pytest.mark.asyncio
class TestAuditLoggerIntegration:
    """Testes de integração do audit logger com outros componentes."""

    async def test_audit_logger_handles_mongodb_errors_gracefully(
        self,
        mongodb_ml_client
    ):
        """
        Testa que erros de MongoDB são tratados (fail-open).
        """
        skip_if_audit_logger_unavailable()

        # Arrange - cria logger com client quebrado
        broken_client = MagicMock()
        broken_client.db = MagicMock()
        broken_collection = MagicMock()
        broken_collection.insert_one = AsyncMock(side_effect=Exception("Connection lost"))
        broken_collection.create_index = AsyncMock()
        broken_client.db.__getitem__ = MagicMock(return_value=broken_collection)

        config = MockAuditLoggerConfig()

        logger = ModelAuditLogger(
            mongodb_client=broken_client,
            config=config,
            metrics=None
        )

        # Act - não deve lançar exceção
        audit_id = await logger.log_training_started(
            model_name="test_model",
            model_version="v1.0",
            context=AuditEventContext(),
            training_config={"model_type": "test"}
        )

        # Assert - retorna vazio mas não falha
        assert audit_id == ''

    async def test_multiple_concurrent_audit_events(
        self,
        audit_logger,
        mongodb_ml_client
    ):
        """
        Testa registro de múltiplos eventos concorrentes.
        """
        skip_if_audit_logger_unavailable()

        # Arrange
        model_name = "duration_predictor"
        num_events = 10

        # Act - registra eventos concorrentemente
        tasks = []
        for i in range(num_events):
            tasks.append(
                audit_logger.log_training_started(
                    model_name=model_name,
                    model_version=f"v{i}.0",
                    context=AuditEventContext(
                        metadata={'batch_index': i}
                    )
                )
            )

        audit_ids = await asyncio.gather(*tasks)

        # Assert
        assert len(audit_ids) == num_events
        assert all(aid is not None for aid in audit_ids)

        # Verifica no MongoDB
        count = await mongodb_ml_client.db['model_audit_log'].count_documents(
            {'model_name': model_name}
        )
        assert count == num_events

    async def test_audit_event_context_serialization(
        self,
        audit_logger,
        mongodb_ml_client
    ):
        """
        Testa serialização correta do contexto de auditoria.
        """
        skip_if_audit_logger_unavailable()

        # Arrange
        context = AuditEventContext(
            user_id="user_123",
            reason="Manual deployment",
            duration_seconds=1234.56,
            environment="production",
            triggered_by="api_call",
            metadata={
                'nested': {'key': 'value'},
                'array': [1, 2, 3],
                'float': 3.14
            }
        )

        # Act
        audit_id = await audit_logger.log_training_started(
            model_name="test_model",
            model_version="v1.0",
            context=context
        )

        # Assert
        event = await mongodb_ml_client.db['model_audit_log'].find_one(
            {'audit_id': audit_id}
        )

        assert event['user_id'] == "user_123"
        assert event['reason'] == "Manual deployment"
        assert event['duration_seconds'] == 1234.56
        assert event['environment'] == "production"
        assert event['triggered_by'] == "api_call"
        assert event['metadata']['nested']['key'] == 'value'
        assert event['metadata']['array'] == [1, 2, 3]
        assert event['metadata']['float'] == 3.14
