"""Configuração de testes"""

import os
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from src.config import Settings, get_settings
from src.models import DocumentFormat, DocumentStatus, DocumentType, ExperimentRun, Insight, InsightConfidence, LearningDocument


@pytest.fixture
def test_settings() -> Settings:
    """Configurações para teste"""
    return Settings(
        environment="test",
        debug=True,
        mongodb_uri="mongodb://localhost:27017",
        mongodb_database="test_neural_hive",
        mongodb_collection="test_learning_documents",
        mlflow_tracking_uri="http://localhost:5000",
        kafka_bootstrap_servers="localhost:9092",
        docs_output_dir="/tmp/test_learning_docs",
    )


@pytest.fixture(autouse=True)
def set_env_vars(monkeypatch, tmp_path):
    """Define variáveis de ambiente para testes"""
    output_dir = tmp_path / "output"
    template_dir = tmp_path / "templates"
    output_dir.mkdir(exist_ok=True)
    template_dir.mkdir(exist_ok=True)

    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("MONGODB_DATABASE", "test_neural_hive")
    monkeypatch.setenv("MONGODB_COLLECTION", "test_learning_documents")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    monkeypatch.setenv("DOCS_OUTPUT_DIR", str(output_dir))
    monkeypatch.setenv("DOCS_TEMPLATE_DIR", str(template_dir))


@pytest.fixture
def mock_experiment_runs() -> list[ExperimentRun]:
    """Runs de experimento mockados"""
    return [
        ExperimentRun(
            run_id="exp_001",
            experiment_id=1,
            name="experiment_baseline",
            status="FINISHED",
            start_time=datetime(2026, 1, 1, 10, 0, 0),
            end_time=datetime(2026, 1, 1, 10, 30, 0),
            metrics={
                "accuracy": 0.85,
                "val_accuracy": 0.82,
                "loss": 0.45,
                "val_loss": 0.52,
            },
            params={"learning_rate": 0.001, "epochs": 10},
            tags={"version": "baseline"},
            artifact_uri="s3://mlflow/exp_001/artifacts",
        ),
        ExperimentRun(
            run_id="exp_002",
            experiment_id=1,
            name="experiment_v2",
            status="FINISHED",
            start_time=datetime(2026, 1, 2, 10, 0, 0),
            end_time=datetime(2026, 1, 2, 10, 25, 0),
            metrics={
                "accuracy": 0.88,
                "val_accuracy": 0.86,
                "loss": 0.38,
                "val_loss": 0.42,
            },
            params={"learning_rate": 0.0005, "epochs": 15},
            tags={"version": "v2"},
            artifact_uri="s3://mlflow/exp_002/artifacts",
        ),
        ExperimentRun(
            run_id="exp_003",
            experiment_id=1,
            name="experiment_failed",
            status="FAILED",
            start_time=datetime(2026, 1, 3, 10, 0, 0),
            end_time=datetime(2026, 1, 3, 10, 10, 0),
            metrics={
                "accuracy": 0.70,
                "val_accuracy": 0.65,
            },
            params={"learning_rate": 0.01, "epochs": 5},
            tags={"version": "experimental"},
            artifact_uri="s3://mlflow/exp_003/artifacts",
        ),
    ]


@pytest.fixture
def mock_insights() -> list[Insight]:
    """Insights mockados"""
    return [
        Insight(
            title="Melhoria de performance",
            description="O experimento v2 obteve 4.9% de melhoria em val_accuracy",
            evidence={"current": 0.86, "baseline": 0.82, "improvement_percent": 4.9},
            confidence=InsightConfidence.HIGH,
            experiment_ids=["exp_002"],
            category="improvement",
        ),
        Insight(
            title="Tempo de treinamento reduzido",
            description="O tempo de treinamento foi reduzido em 5 minutos",
            evidence={"baseline_duration": 1800, "current_duration": 1500},
            confidence=InsightConfidence.MEDIUM,
            experiment_ids=["exp_002"],
            category="performance",
        ),
    ]


@pytest.fixture
def mock_document() -> LearningDocument:
    """Documento mockado"""
    return LearningDocument(
        id="doc_001",
        title="Relatório de Experimentos Semanal",
        type=DocumentType.WEEKLY_SUMMARY,
        status=DocumentStatus.COMPLETED,
        format=DocumentFormat.MARKDOWN,
        created_at=datetime(2026, 1, 7, 10, 0, 0),
        generated_at=datetime(2026, 1, 7, 11, 0, 0),
        period_start=datetime(2026, 1, 1, 0, 0, 0),
        period_end=datetime(2026, 1, 7, 23, 59, 59),
        summary="Analisados 3 experimentos, 2 concluídos com sucesso e 1 falhou.",
        insights=[],
        recommendations=["Continuar com learning rate de 0.0005"],
        markdown_content="# Relatório de Experimentos Semanal\n...",
    )


@pytest.fixture
async def mock_mongodb_client():
    """Cliente MongoDB mockado"""
    client = AsyncMock(spec=AsyncIOMotorClient)
    return client


@pytest.fixture
def mock_mlflow_client():
    """Cliente MLflow mockado"""
    client = MagicMock()
    return client


@pytest.fixture
def mock_mlflow_runs(mock_experiment_runs):
    """Runs MLflow mockados"""
    runs = []
    for run in mock_experiment_runs:
        run_dict = {
            "info": {
                "run_id": run.run_id,
                "experiment_id": run.experiment_id,
                "run_name": run.name,
                "status": run.status,
                "start_time": int(run.start_time.timestamp() * 1000) if run.start_time else None,
                "end_time": int(run.end_time.timestamp() * 1000) if run.end_time else None,
                "artifact_uri": run.artifact_uri,
            },
            "data": {
                "metrics": [{"key": k, "value": v} for k, v in run.metrics.items()],
                "params": [{"key": k, "value": str(v)} for k, v in run.params.items()],
                "tags": [{"key": k, "value": v} for k, v in run.tags.items()],
            },
        }
        runs.append(MagicMock(to_dictionary=lambda: run_dict))
    return runs


@pytest.fixture(autouse=True)
def reset_settings():
    """Reseta settings para cada teste"""
    # Reset singleton
    import src.config.settings
    src.config.settings._settings_instance = None

    # Reset API state
    import src.api.v1.docs
    src.api.v1.docs._state = None


@pytest.fixture
def output_dir(tmp_path):
    """Diretório de saída para testes"""
    output = tmp_path / "output"
    output.mkdir(exist_ok=True)
    return str(output)
