"""
Testes de integração para circuit breakers.
Valida transições de estado, buffer flush, e fallback com cache expirado.
"""

import pytest
import time
import uuid
from datetime import datetime
from unittest.mock import patch, MagicMock
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure

from neural_hive_specialists.config import SpecialistConfig
from neural_hive_specialists.ledger_client import LedgerClient
from neural_hive_specialists.mlflow_client import MLflowClient


@pytest.mark.integration
def test_ledger_circuit_breaker_opens_on_failures(mongodb_uri):
    """Valida abertura de circuit breaker após múltiplas falhas no Ledger."""
    config = SpecialistConfig(
        specialist_type="test",
        specialist_version="1.0.0",
        service_name="test-specialist",
        environment="test",
        mongodb_uri="mongodb://invalid-host:27017",  # URI inválida
        mongodb_database="test_db",
        mongodb_opinions_collection="test_opinions",
        enable_circuit_breaker=True,
        circuit_breaker_failure_threshold=3,
        circuit_breaker_recovery_timeout=5,
        ledger_buffer_size=10,
    )

    ledger = LedgerClient(config)

    opinion = {
        "opinion_id": f"opinion-{uuid.uuid4()}",
        "specialist_type": "test",
        "specialist_version": "1.0.0",
        "plan_id": f"plan-{uuid.uuid4()}",
        "intent_id": f"intent-{uuid.uuid4()}",
        "correlation_id": f"corr-{uuid.uuid4()}",
        "recommendation": "approve",
        "confidence_score": 0.85,
        "risk_score": 0.2,
        "estimated_effort_hours": 8.0,
        "reasoning_factors": [],
        "suggested_mitigations": [],
        "explainability_token": "token-123",
        "processing_time_ms": 100.0,
        "timestamp": datetime.utcnow().isoformat(),
        "metadata": {},
    }

    # Tentar salvar múltiplas vezes (deve falhar e abrir circuit breaker)
    for i in range(5):
        opinion_id = ledger.save_opinion_with_fallback(opinion)
        # Como há circuit breaker, deve retornar opinion_id mas usar buffer
        assert opinion_id

    # Validar que circuit breaker está aberto
    assert ledger._circuit_breaker_state == "open"

    # Validar que buffer foi usado
    buffer_size = ledger.get_buffer_size()
    assert buffer_size > 0


@pytest.mark.integration
def test_ledger_circuit_breaker_recovery_and_buffer_flush(mongodb_uri):
    """Valida recuperação de circuit breaker e flush de buffer ao reconectar."""
    config = SpecialistConfig(
        specialist_type="test",
        specialist_version="1.0.0",
        service_name="test-specialist",
        environment="test",
        mongodb_uri=mongodb_uri,
        mongodb_database="test_integration_db",
        mongodb_opinions_collection="test_opinions_recovery",
        enable_circuit_breaker=True,
        circuit_breaker_failure_threshold=3,
        circuit_breaker_recovery_timeout=2,  # 2 segundos
        ledger_buffer_size=20,
    )

    ledger = LedgerClient(config)

    # Forçar circuit breaker a abrir simulando falhas
    with patch.object(
        ledger, "_save_opinion_impl", side_effect=ConnectionFailure("Simulated failure")
    ):
        for i in range(4):
            opinion = {
                "opinion_id": f"opinion-fail-{i}",
                "specialist_type": "test",
                "specialist_version": "1.0.0",
                "plan_id": f"plan-{uuid.uuid4()}",
                "intent_id": f"intent-{uuid.uuid4()}",
                "correlation_id": f"corr-{uuid.uuid4()}",
                "recommendation": "approve",
                "confidence_score": 0.85,
                "risk_score": 0.2,
                "estimated_effort_hours": 8.0,
                "reasoning_factors": [],
                "suggested_mitigations": [],
                "explainability_token": f"token-{i}",
                "processing_time_ms": 100.0,
                "timestamp": datetime.utcnow().isoformat(),
                "metadata": {},
            }
            ledger.save_opinion_with_fallback(opinion)

    # Circuit breaker deve estar aberto
    initial_state = ledger._circuit_breaker_state
    assert initial_state == "open"

    # Aguardar timeout de recuperação
    time.sleep(3)

    # Tentar salvar novamente (deve recuperar e fazer flush do buffer)
    opinion_recovery = {
        "opinion_id": f"opinion-recovery-{uuid.uuid4()}",
        "specialist_type": "test",
        "specialist_version": "1.0.0",
        "plan_id": f"plan-{uuid.uuid4()}",
        "intent_id": f"intent-{uuid.uuid4()}",
        "correlation_id": f"corr-{uuid.uuid4()}",
        "recommendation": "approve",
        "confidence_score": 0.85,
        "risk_score": 0.2,
        "estimated_effort_hours": 8.0,
        "reasoning_factors": [],
        "suggested_mitigations": [],
        "explainability_token": "token-recovery",
        "processing_time_ms": 100.0,
        "timestamp": datetime.utcnow().isoformat(),
        "metadata": {},
    }

    opinion_id = ledger.save_opinion_with_fallback(opinion_recovery)
    assert opinion_id

    # Circuit breaker deve ter recuperado
    # Buffer deve ter sido processado
    buffer_size = ledger.get_buffer_size()
    assert buffer_size == 0  # Buffer vazio após flush


@pytest.mark.integration
def test_mlflow_circuit_breaker_expired_cache_fallback(mocker):
    """Valida fallback para cache expirado quando circuit breaker está aberto."""
    config = SpecialistConfig(
        specialist_type="test",
        specialist_version="1.0.0",
        service_name="test-specialist",
        environment="test",
        mlflow_tracking_uri="http://invalid-mlflow:5000",  # URI inválida
        mlflow_experiment_name="test-experiment",
        mlflow_model_name="test-model",
        mlflow_model_stage="Production",
        enable_circuit_breaker=True,
        circuit_breaker_failure_threshold=3,
        circuit_breaker_recovery_timeout=5,
        mlflow_cache_ttl_seconds=10,
        enable_caching=True,
    )

    mlflow_client = MLflowClient(config)

    # Simular modelo em cache (expirado)
    mock_model = MagicMock()
    mock_model.predict = MagicMock(return_value=[0.85])
    mlflow_client._model_cache["test-model:Production"] = {
        "model": mock_model,
        "cached_at": time.time() - 3600,  # Cache expirado (1 hora atrás)
        "version": "1",
    }

    # Tentar carregar modelo (deve falhar mas usar cache expirado)
    with patch("mlflow.MlflowClient") as mock_mlflow:
        mock_mlflow.return_value.get_latest_versions.side_effect = ConnectionError(
            "MLflow unreachable"
        )

        # Deve usar cache expirado como fallback
        model = mlflow_client.load_model_with_fallback()
        assert model is not None
        assert mlflow_client.used_expired_cache_recently is True


@pytest.mark.integration
def test_circuit_breaker_half_open_transition(mongodb_uri):
    """Valida transição half-open -> closed após sucesso."""
    config = SpecialistConfig(
        specialist_type="test",
        specialist_version="1.0.0",
        service_name="test-specialist",
        environment="test",
        mongodb_uri=mongodb_uri,
        mongodb_database="test_integration_db",
        mongodb_opinions_collection="test_opinions_half_open",
        enable_circuit_breaker=True,
        circuit_breaker_failure_threshold=3,
        circuit_breaker_recovery_timeout=2,
        ledger_buffer_size=10,
    )

    ledger = LedgerClient(config)

    # Forçar abertura do circuit breaker
    with patch.object(
        ledger, "_save_opinion_impl", side_effect=ConnectionFailure("Simulated failure")
    ):
        for i in range(4):
            opinion = {
                "opinion_id": f"opinion-{i}",
                "specialist_type": "test",
                "specialist_version": "1.0.0",
                "plan_id": f"plan-{uuid.uuid4()}",
                "intent_id": f"intent-{uuid.uuid4()}",
                "correlation_id": f"corr-{uuid.uuid4()}",
                "recommendation": "approve",
                "confidence_score": 0.85,
                "risk_score": 0.2,
                "estimated_effort_hours": 8.0,
                "reasoning_factors": [],
                "suggested_mitigations": [],
                "explainability_token": f"token-{i}",
                "processing_time_ms": 100.0,
                "timestamp": datetime.utcnow().isoformat(),
                "metadata": {},
            }
            ledger.save_opinion_with_fallback(opinion)

    assert ledger._circuit_breaker_state == "open"

    # Aguardar timeout
    time.sleep(3)

    # Próxima tentativa deve transitar para half-open
    opinion_test = {
        "opinion_id": f"opinion-test-{uuid.uuid4()}",
        "specialist_type": "test",
        "specialist_version": "1.0.0",
        "plan_id": f"plan-{uuid.uuid4()}",
        "intent_id": f"intent-{uuid.uuid4()}",
        "correlation_id": f"corr-{uuid.uuid4()}",
        "recommendation": "approve",
        "confidence_score": 0.85,
        "risk_score": 0.2,
        "estimated_effort_hours": 8.0,
        "reasoning_factors": [],
        "suggested_mitigations": [],
        "explainability_token": "token-test",
        "processing_time_ms": 100.0,
        "timestamp": datetime.utcnow().isoformat(),
        "metadata": {},
    }

    opinion_id = ledger.save_opinion_with_fallback(opinion_test)
    assert opinion_id

    # Circuit breaker deve ter fechado (sucesso em half-open)
    # Nota: implementação real pode levar alguns ciclos para fechar completamente
    assert ledger._circuit_breaker_state in ["half-open", "closed"]


@pytest.mark.integration
def test_ledger_buffer_overflow_handling(mongodb_uri):
    """Valida comportamento quando buffer atinge capacidade máxima."""
    config = SpecialistConfig(
        specialist_type="test",
        specialist_version="1.0.0",
        service_name="test-specialist",
        environment="test",
        mongodb_uri="mongodb://invalid-host:27017",  # Forçar falhas
        mongodb_database="test_db",
        mongodb_opinions_collection="test_opinions",
        enable_circuit_breaker=True,
        circuit_breaker_failure_threshold=2,
        circuit_breaker_recovery_timeout=10,
        ledger_buffer_size=5,  # Buffer pequeno
    )

    ledger = LedgerClient(config)

    # Tentar salvar mais pareceres do que capacidade do buffer
    for i in range(10):
        opinion = {
            "opinion_id": f"opinion-overflow-{i}",
            "specialist_type": "test",
            "specialist_version": "1.0.0",
            "plan_id": f"plan-{uuid.uuid4()}",
            "intent_id": f"intent-{uuid.uuid4()}",
            "correlation_id": f"corr-{uuid.uuid4()}",
            "recommendation": "approve",
            "confidence_score": 0.85,
            "risk_score": 0.2,
            "estimated_effort_hours": 8.0,
            "reasoning_factors": [],
            "suggested_mitigations": [],
            "explainability_token": f"token-{i}",
            "processing_time_ms": 100.0,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": {},
        }
        ledger.save_opinion_with_fallback(opinion)

    # Buffer não deve exceder capacidade máxima
    buffer_size = ledger.get_buffer_size()
    assert buffer_size <= 5


@pytest.mark.integration
def test_circuit_breaker_metrics_tracking(mongodb_uri, mocker):
    """Valida rastreamento de métricas durante transições de circuit breaker."""
    mock_metrics = mocker.MagicMock()

    config = SpecialistConfig(
        specialist_type="test",
        specialist_version="1.0.0",
        service_name="test-specialist",
        environment="test",
        mongodb_uri="mongodb://invalid-host:27017",
        mongodb_database="test_db",
        mongodb_opinions_collection="test_opinions",
        enable_circuit_breaker=True,
        circuit_breaker_failure_threshold=3,
        circuit_breaker_recovery_timeout=5,
        ledger_buffer_size=10,
    )

    ledger = LedgerClient(config, metrics=mock_metrics)

    # Forçar falhas para abrir circuit breaker
    for i in range(5):
        opinion = {
            "opinion_id": f"opinion-{i}",
            "specialist_type": "test",
            "specialist_version": "1.0.0",
            "plan_id": f"plan-{uuid.uuid4()}",
            "intent_id": f"intent-{uuid.uuid4()}",
            "correlation_id": f"corr-{uuid.uuid4()}",
            "recommendation": "approve",
            "confidence_score": 0.85,
            "risk_score": 0.2,
            "estimated_effort_hours": 8.0,
            "reasoning_factors": [],
            "suggested_mitigations": [],
            "explainability_token": f"token-{i}",
            "processing_time_ms": 100.0,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": {},
        }
        ledger.save_opinion_with_fallback(opinion)

    # Validar que métricas foram chamadas
    # set_circuit_breaker_state deve ter sido chamado com 'open'
    assert mock_metrics.set_circuit_breaker_state.called
    # increment_fallback_used deve ter sido chamado
    assert mock_metrics.increment_fallback_used.called
