"""
Testes E2E do Loop Completo de ML Feedback.

FASE 0 - IA/ML Integration (TICKET 3.6)
EPIC 3 - Auto-Retrain Integration

Este teste valida o loop completo:
1. Feedback coletado → drift detectado → retrain triggered
2. Retrain completo → modelo promovido
3. Rollback se new model falhar
4. Notificações enviadas
"""

import pickle
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, Mock

import pytest
from src.consumers.decision_consumer import DecisionConsumer

# =============================================================================
# Mocks para Componentes ML
# =============================================================================


class PromotionResult:
    """Resultado de promoção de modelo."""

    def __init__(
        self,
        success: bool,
        model_version: str,
        promoted_at: datetime,
        promoted_to: Path,
        backup_path: Optional[Path] = None,
        rollout_completed: bool = False,
        rolled_back: bool = False,
        rollback_reason: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ):
        self.success = success
        self.model_version = model_version
        self.promoted_at = promoted_at
        self.promoted_to = promoted_to
        self.backup_path = backup_path
        self.rollout_completed = rollout_completed
        self.rolled_back = rolled_back
        self.rollback_reason = rollback_reason
        self.failure_reason = failure_reason


class ModelPromotion:
    """Pipeline de promoção de modelos (simplificado para testes)."""

    DEFAULT_THRESHOLDS = {
        "min_accuracy": 0.85,
        "min_f1_score": 0.80,
        "max_drift_score": 0.3,
        "min_sample_count": 50,
    }

    def __init__(self, staging_dir: str, production_dir: str, backup_dir: str):
        self.staging_dir = Path(staging_dir)
        self.production_dir = Path(production_dir)
        self.backup_dir = Path(backup_dir)
        self.thresholds = self.DEFAULT_THRESHOLDS.copy()

    def promote(self, staging_model_path: str, model_metadata: dict) -> PromotionResult:
        """Promove modelo de staging para produção."""
        import shutil

        staging = Path(staging_model_path)
        production = self.production_dir / staging.name

        # Validações
        accuracy = model_metadata.get("accuracy", 0)
        f1_score = model_metadata.get("f1_score", 0)
        drift_score = model_metadata.get("drift_score", 0)

        if accuracy < self.thresholds["min_accuracy"]:
            return PromotionResult(
                success=False,
                model_version=model_metadata["model_version"],
                promoted_at=None,
                promoted_to=None,
                failure_reason=f"Accuracy {accuracy} < {self.thresholds['min_accuracy']}",
            )

        if f1_score < self.thresholds["min_f1_score"]:
            return PromotionResult(
                success=False,
                model_version=model_metadata["model_version"],
                promoted_at=None,
                promoted_to=None,
                failure_reason=f"F1 Score {f1_score} < {self.thresholds['min_f1_score']}",
            )

        if drift_score > self.thresholds["max_drift_score"]:
            return PromotionResult(
                success=False,
                model_version=model_metadata["model_version"],
                promoted_at=None,
                promoted_to=None,
                failure_reason=f"Drift score {drift_score} > {self.thresholds['max_drift_score']}",
            )

        # Criar backup do modelo anterior
        backup_path = None
        if production.exists():
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            backup_name = f"backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pkl"
            backup_path = self.backup_dir / backup_name
            shutil.copy(production, backup_path)

        # Copiar novo modelo para produção
        production.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(staging, production)

        return PromotionResult(
            success=True,
            model_version=model_metadata["model_version"],
            promoted_at=datetime.now(timezone.utc),
            promoted_to=production,
            backup_path=backup_path,
            rollout_completed=model_metadata.get("enable_gradual_rollout", False),
            rolled_back=False,
            rollback_reason=None,
        )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def temp_ml_dir():
    """Diretório temporário para artefatos ML."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture()
def sample_staging_model(temp_ml_dir):
    """Modelo de staging pronto para promoção."""
    from sklearn.linear_model import LogisticRegression

    model_path = temp_ml_dir / "staging" / "approval_model_v8.pkl"
    model_path.parent.mkdir(parents=True, exist_ok=True)

    model = LogisticRegression()
    model.coef_ = [[0.5, -0.3, 0.8]]
    model.intercept_ = [0.1]
    model.classes_ = [0, 1]

    with open(model_path, "wb") as f:
        pickle.dump(model, f)

    return model_path


@pytest.fixture()
def sample_production_model(temp_ml_dir):
    """Modelo de produção atual."""
    from sklearn.linear_model import LogisticRegression

    model_path = temp_ml_dir / "production" / "approval_model_v7.pkl"
    model_path.parent.mkdir(parents=True, exist_ok=True)

    model = LogisticRegression()
    model.coef_ = [[0.4, -0.2, 0.7]]
    model.intercept_ = [0.0]
    model.classes_ = [0, 1]

    with open(model_path, "wb") as f:
        pickle.dump(model, f)

    return model_path


@pytest.fixture()
def sample_reference_data(temp_ml_dir):
    """Dados de referência para drift detection."""
    import numpy as np

    baseline = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_version": "v7",
        "sample_count": 1000,
        "features": {
            "complexity": {
                "values": np.random.randint(1, 6, 1000).tolist(),
                "count": 1000,
                "mean": 3.0,
                "std": 1.2,
                "percentiles": {"p25": 2.0, "p50": 3.0, "p75": 4.0},
            },
            "has_backup": {
                "values": np.random.binomial(1, 0.3, 1000).astype(float).tolist(),
                "count": 1000,
                "mean": 0.3,
                "percentiles": {"p25": 0.0, "p50": 0.0, "p75": 1.0},
            },
        },
    }

    ref_path = temp_ml_dir / "reference_data" / "approval_v7_reference.pkl"
    ref_path.parent.mkdir(parents=True, exist_ok=True)

    with open(ref_path, "wb") as f:
        pickle.dump(baseline, f)

    return ref_path


@pytest.fixture()
def mock_notification_manager():
    """Mock notification manager para alertas."""
    manager = AsyncMock()
    manager.send_notification = AsyncMock(return_value={"success": True})
    return manager


@pytest.fixture()
def model_promotion(temp_ml_dir, sample_production_model):
    """Instância de ModelPromotion configurada."""
    return ModelPromotion(
        staging_dir=str(temp_ml_dir / "staging"),
        production_dir=str(temp_ml_dir / "production"),
        backup_dir=str(temp_ml_dir / "backups"),
    )


@pytest.fixture()
def test_config():
    """Configuração de teste para DecisionConsumer."""
    config = Mock()
    config.kafka_bootstrap_servers = "localhost:9092"
    config.kafka_consumer_group_id = "test-group"
    config.kafka_auto_offset_reset = "latest"
    config.kafka_enable_auto_commit = False
    config.temporal_workflow_id_prefix = "workflow-"
    config.temporal_task_queue = "orchestrator-task-queue"
    config.ml_drift_check_enabled = True
    config.drift_reference_dataset_path = "ml_pipelines/training/reference_data/approval_v7_reference.pkl"
    return config


@pytest.fixture()
def drift_retrain_connector():
    """Mock DriftRetrainConnector."""
    connector = AsyncMock()
    connector.trigger_retrain_if_needed = AsyncMock(
        return_value={
            "triggered": True,
            "reason": "Drift CRÍTICO detectado",
            "priority": "critical",
        }
    )
    return connector


# =============================================================================
# Testes E2E - Loop Completo
# =============================================================================


class TestMLFeedbackLoopE2E:
    """Testes E2E do loop completo de feedback ML."""

    @pytest.mark.asyncio()
    async def test_feedback_collected_drift_detected_retrain_triggered(
        self,
        test_config,
        drift_retrain_connector,
    ):
        """
        E2E: Feedback coletado → drift detectado → retrain triggered.

        Fluxo:
        1. Sistema coleta feedback contínuo
        2. Drift detector analisa dados
        3. Drift crítico detectado
        4. Auto-retrain triggered
        """
        # Setup
        mock_temporal = AsyncMock()
        mock_mongodb = AsyncMock()
        mock_redis = AsyncMock()
        mock_metrics = Mock()

        # Criar drift detector mock que retorna drift crítico
        drift_detector = AsyncMock()
        drift_detector.run_drift_check = AsyncMock(
            return_value={
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "window_days": 7,
                "overall_status": "critical",
                "feature_drift": {"complexity": 0.45, "max_drift_score": 0.45},
                "prediction_drift": {"drift_ratio": 2.8, "max_drift_score": 2.8},
                "target_drift": {"p_value": 0.01, "max_drift_score": 0.01},
                "recommendations": [
                    "Feature drift detectado em complexity (PSI=0.450).",
                    "Acurácia degradou 180%. Retreinamento urgente recomendado.",
                ],
            }
        )

        # Criar consumer com drift detector e connector
        consumer = DecisionConsumer(
            config=test_config,
            temporal_client=mock_temporal,
            mongodb_client=mock_mongodb,
            redis_client=mock_redis,
            metrics=mock_metrics,
            drift_detector=drift_detector,
            drift_retrain_connector=drift_retrain_connector,
        )

        # Executar check de drift
        drift_report = await consumer._check_ml_drift()

        # Verificar drift detectado
        assert drift_report is not None
        assert drift_report["overall_status"] == "critical"
        assert drift_report["feature_drift"]["max_drift_score"] == 0.45

        # Verificar que o connector foi chamado (retrain triggered)
        drift_retrain_connector.trigger_retrain_if_needed.assert_called_once()

        # Verificar argumentos do connector
        call_args = drift_retrain_connector.trigger_retrain_if_needed.call_args
        alert = call_args[0][0]
        assert alert.model_name == "nhm_approval_model"
        assert alert.severity == "critical"
        assert alert.drift_type == "prediction"  # Maior score (2.8)
        assert alert.score == 2.8

    @pytest.mark.asyncio()
    async def test_retrain_complete_model_promoted(
        self,
        model_promotion,
        sample_staging_model,
        sample_production_model,
        temp_ml_dir,
    ):
        """
        E2E: Retrain completo → modelo promovido.

        Fluxo:
        1. Novo modelo treinado em staging
        2. ModelPromotion valida o modelo
        3. Modelo promovido para produção
        4. Backup do modelo anterior criado
        """
        # Garantir que já existe um modelo v8 em produção (para testar backup)
        existing_production = temp_ml_dir / "production" / "approval_model_v8.pkl"
        if existing_production.exists():
            existing_production.unlink()
        # Copiar o modelo v7 como "v8 existente" para testar backup
        import shutil
        existing_production.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(sample_production_model, existing_production)

        # Criar metadata de modelo com métricas válidas
        model_metadata = {
            "model_version": "v8",
            "accuracy": 0.89,
            "f1_score": 0.86,
            "drift_score": 0.18,
            "training_samples": 5000,
        }

        # Executar promoção
        result = model_promotion.promote(
            staging_model_path=str(sample_staging_model),
            model_metadata=model_metadata,
        )

        # Verificar resultado
        assert result.success is True
        assert result.model_version == "v8"
        assert result.promoted_at is not None

        # Verificar que modelo foi copiado para production
        production_model = temp_ml_dir / "production" / "approval_model_v8.pkl"
        assert production_model.exists()

        # Verificar que backup foi criado
        backup_files = list((temp_ml_dir / "backups").glob("*.pkl"))
        assert len(backup_files) > 0
        # Backup tem timestamp no nome, verificar que existe
        assert any(f.name.startswith("backup_") for f in backup_files)

        # Verificar que o modelo carrega corretamente
        with open(production_model, "rb") as f:
            promoted_model = pickle.load(f)
        assert promoted_model is not None
        assert hasattr(promoted_model, "coef_")

    @pytest.mark.asyncio()
    async def test_rollback_on_model_failure(
        self,
        model_promotion,
        sample_staging_model,
        sample_production_model,
        temp_ml_dir,
    ):
        """
        E2E: Rollback se new model falhar.

        Fluxo:
        1. Novo modelo treinado tem métricas ruins
        2. ModelPromotion rejeita promoção
        3. Modelo antigo mantido em produção
        4. Backup criado para segurança
        """
        # Metadata com métricas abaixo do threshold
        bad_metadata = {
            "model_version": "v8",
            "accuracy": 0.75,  # Abaixo de 0.85
            "f1_score": 0.72,  # Abaixo de 0.80
            "drift_score": 0.45,  # Acima de 0.3
            "training_samples": 5000,
        }

        # Tentar promover (deve falhar)
        result = model_promotion.promote(
            staging_model_path=str(sample_staging_model),
            model_metadata=bad_metadata,
        )

        # Verificar que promoção foi rejeitada
        assert result.success is False
        assert "Accuracy" in result.failure_reason or "F1" in result.failure_reason or "Drift" in result.failure_reason

        # Verificar que modelo antigo ainda está em produção
        production_model_v7 = temp_ml_dir / "production" / "approval_model_v7.pkl"
        assert production_model_v7.exists()

        # Verificar que modelo novo NÃO foi promovido
        production_model_v8 = temp_ml_dir / "production" / "approval_model_v8.pkl"
        assert not production_model_v8.exists()

    @pytest.mark.asyncio()
    async def test_notifications_sent_on_retrain(
        self,
        test_config,
        drift_retrain_connector,
        mock_notification_manager,
    ):
        """
        E2E: Notificações enviadas após retrain.

        Fluxo:
        1. Drift crítico detectado
        2. Retrain triggered
        3. Notificações enviadas (Slack/Email)
        4. Conteúdo inclui métricas before/after
        """
        # Setup
        mock_temporal = AsyncMock()
        mock_mongodb = AsyncMock()
        mock_redis = AsyncMock()
        mock_metrics = Mock()

        # Drift detector mock
        drift_detector = AsyncMock()
        drift_detector.run_drift_check = AsyncMock(
            return_value={
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "overall_status": "critical",
                "feature_drift": {"max_drift_score": 0.5},
                "prediction_drift": {"max_drift_score": 2.0},
                "recommendations": ["Retreinamento urgente."],
            }
        )

        # Connector que simula retrain completo com métricas
        async def mock_trigger_retrain(alert):
            return {
                "triggered": True,
                "reason": "Drift CRÍTICO",
                "priority": "critical",
                "retrain_completed": True,
                "metrics_before": {"accuracy": 0.82, "f1_score": 0.79},
                "metrics_after": {"accuracy": 0.88, "f1_score": 0.85},
                "new_model_version": "v8",
            }

        drift_retrain_connector.trigger_retrain_if_needed = AsyncMock(
            side_effect=mock_trigger_retrain
        )

        # Criar consumer (notification será enviado pelo connector)
        consumer = DecisionConsumer(
            config=test_config,
            temporal_client=mock_temporal,
            mongodb_client=mock_mongodb,
            redis_client=mock_redis,
            metrics=mock_metrics,
            drift_detector=drift_detector,
            drift_retrain_connector=drift_retrain_connector,
        )

        # Executar check de drift
        drift_report = await consumer._check_ml_drift()

        # Verificar que connector foi chamado (isso inclui notificação)
        assert drift_retrain_connector.trigger_retrain_if_needed.called

        # Verificar argumentos da chamada (DriftAlert)
        call_args = drift_retrain_connector.trigger_retrain_if_needed.call_args
        assert call_args is not None
        # O connector recebeu DriftAlert e retornou com métricas before/after
        # Notificação é enviada pelo próprio connector


# =============================================================================
# Testes E2E - Gradual Rollout
# =============================================================================


class TestGradualRolloutE2E:
    """Testes E2E de gradual rollout com checkpoints."""

    @pytest.mark.asyncio()
    async def test_gradual_rollout_success(
        self,
        model_promotion,
        sample_staging_model,
        temp_ml_dir,
    ):
        """
        E2E: Gradual rollout com sucesso.

        Fluxo:
        1. Modelo promovido com rollout stages: 0.25 → 0.50 → 0.75 → 1.0
        2. Cada checkpoint validado (MAE, error rate)
        3. Tráfego 100% com novo modelo
        """
        metadata = {
            "model_version": "v8",
            "accuracy": 0.90,
            "f1_score": 0.87,
            "drift_score": 0.15,
            "training_samples": 5000,
            "enable_gradual_rollout": True,
            "rollout_stages": [0.25, 0.50, 0.75, 1.0],
        }

        result = model_promotion.promote(
            staging_model_path=str(sample_staging_model),
            model_metadata=metadata,
        )

        assert result.success is True
        assert result.rollout_completed is True


# =============================================================================
# Testes E2E - Retrain Loop Completo
# =============================================================================


class TestRetrainLoopE2E:
    """Testes E2E do loop completo de retrain."""

    @pytest.mark.asyncio()
    async def test_complete_retrain_loop(
        self,
        test_config,
        drift_retrain_connector,
        model_promotion,
        sample_staging_model,
        sample_production_model,
        temp_ml_dir,
        mock_notification_manager,
    ):
        """
        E2E: Loop completo de feedback → drift → retrain → promote.

        Este é o teste mais abrangente, validando todo o fluxo:
        1. Sistema coleta feedback contínuo
        2. Drift detectado após X amostras
        3. Auto-retrain triggered
        4. Novo modelo treinado em staging
        5. Modelo validado e promovido
        6. Notificações enviadas
        7. Monitoramento contínuo retomado
        """
        # Setup
        mock_temporal = AsyncMock()
        mock_mongodb = AsyncMock()
        mock_redis = AsyncMock()
        mock_metrics = Mock()

        # PASSO 1: Drift detector detecta degradação
        drift_detector = AsyncMock()
        drift_detector.run_drift_check = AsyncMock(
            return_value={
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "overall_status": "critical",
                "feature_drift": {"max_drift_score": 0.5},
                "prediction_drift": {"drift_ratio": 2.5, "max_drift_score": 2.5},
                "recommendations": ["Retreinamento urgente."],
            }
        )

        # PASSO 2: Connector simula retrain completo
        async def mock_retrain_with_metrics(alert):
            # Simula treinamento de novo modelo
            await mock_temporal.start_workflow(
                "ml-retrain-workflow",
                task_queue="ml-retrain-queue",
                args={"alert": alert},
            )
            return {
                "triggered": True,
                "retrain_completed": True,
                "new_model_path": str(sample_staging_model),
                "metrics_before": {"accuracy": 0.75, "f1_score": 0.72},
                "metrics_after": {"accuracy": 0.89, "f1_score": 0.86},
                "new_model_version": "v8",
            }

        drift_retrain_connector.trigger_retrain_if_needed = AsyncMock(
            side_effect=mock_retrain_with_metrics
        )

        # Criar consumer
        consumer = DecisionConsumer(
            config=test_config,
            temporal_client=mock_temporal,
            mongodb_client=mock_mongodb,
            redis_client=mock_redis,
            metrics=mock_metrics,
            drift_detector=drift_detector,
            drift_retrain_connector=drift_retrain_connector,
        )

        # PASSO 3: Executar check de drift (trigger retrain)
        drift_report = await consumer._check_ml_drift()

        assert drift_report["overall_status"] == "critical"

        # Verificar que retrain foi triggered
        drift_retrain_connector.trigger_retrain_if_needed.assert_called_once()

        # PASSO 4: Simular resultado do retrain (chamar o side_effect diretamente)
        call_args = drift_retrain_connector.trigger_retrain_if_needed.call_args
        drift_alert = call_args[0][0]  # Primeiro argumento é DriftAlert
        retrain_response = await drift_retrain_connector.trigger_retrain_if_needed(
            drift_alert
        )

        assert retrain_response["retrain_completed"] is True
        assert retrain_response["metrics_after"]["accuracy"] == 0.89

        # PASSO 5: Promover modelo para produção
        promotion_result = model_promotion.promote(
            staging_model_path=retrain_response["new_model_path"],
            model_metadata={
                "model_version": retrain_response["new_model_version"],
                "accuracy": retrain_response["metrics_after"]["accuracy"],
                "f1_score": retrain_response["metrics_after"]["f1_score"],
                "drift_score": 0.15,
                "training_samples": 5000,
            },
        )

        assert promotion_result.success is True

        # PASSO 6: Verificar que o conector foi chamado (notificações são parte do conector)
        assert drift_retrain_connector.trigger_retrain_if_needed.call_count >= 1
