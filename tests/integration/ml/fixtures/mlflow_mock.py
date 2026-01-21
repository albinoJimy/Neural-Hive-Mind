# -*- coding: utf-8 -*-
"""
Fixtures de teste para MLflow.

Configura ambiente de tracking MLflow isolado para testes de integração.
"""

import os
import shutil
import tempfile
from typing import Dict, Any, Optional
from unittest.mock import MagicMock, AsyncMock

import pytest


class MockMLflowClient:
    """
    Cliente MLflow mock para testes.

    Simula operações de registro e promoção de modelos sem
    dependência de servidor MLflow real.
    """

    def __init__(self, tracking_uri: str = None):
        self.tracking_uri = tracking_uri or "file:///tmp/mlflow_test"
        self._experiments = {"test_model_promotion": "1"}
        self._models = {}
        self._runs = {}
        self._model_versions = {}

    def create_experiment(self, name: str) -> str:
        """Cria experimento de teste."""
        experiment_id = str(len(self._experiments) + 1)
        self._experiments[name] = experiment_id
        return experiment_id

    def get_experiment_by_name(self, name: str) -> Optional[MagicMock]:
        """Retorna experimento por nome."""
        if name in self._experiments:
            exp = MagicMock()
            exp.experiment_id = self._experiments[name]
            return exp
        return None

    def log_param(self, run_id: str, key: str, value: Any):
        """Registra parâmetro em run."""
        if run_id not in self._runs:
            self._runs[run_id] = {"params": {}, "metrics": {}, "artifacts": []}
        self._runs[run_id]["params"][key] = value

    def log_metric(self, run_id: str, key: str, value: float):
        """Registra métrica em run."""
        if run_id not in self._runs:
            self._runs[run_id] = {"params": {}, "metrics": {}, "artifacts": []}
        self._runs[run_id]["metrics"][key] = value

    def create_registered_model(self, name: str) -> MagicMock:
        """Cria modelo registrado."""
        if name not in self._models:
            self._models[name] = {
                "name": name,
                "versions": [],
                "current_stage": "None"
            }
        model = MagicMock()
        model.name = name
        return model

    def create_model_version(
        self,
        name: str,
        source: str,
        run_id: str = None
    ) -> MagicMock:
        """Cria versão de modelo."""
        if name not in self._models:
            self.create_registered_model(name)

        version_num = len(self._models[name]["versions"]) + 1

        version_info = {
            "name": name,
            "version": str(version_num),
            "source": source,
            "run_id": run_id,
            "current_stage": "None"
        }
        self._models[name]["versions"].append(version_info)

        version = MagicMock()
        version.name = name
        version.version = str(version_num)
        version.current_stage = "None"
        return version

    def transition_model_version_stage(
        self,
        name: str,
        version: str,
        stage: str,
        archive_existing_versions: bool = False
    ) -> MagicMock:
        """Transiciona versão de modelo para novo estágio."""
        if name in self._models:
            for v in self._models[name]["versions"]:
                if v["version"] == str(version):
                    v["current_stage"] = stage
                    break

            if archive_existing_versions and stage == "Production":
                for v in self._models[name]["versions"]:
                    if v["version"] != str(version) and v["current_stage"] == "Production":
                        v["current_stage"] = "Archived"

        result = MagicMock()
        result.name = name
        result.version = version
        result.current_stage = stage
        return result

    def get_model_version(self, name: str, version: str) -> Optional[MagicMock]:
        """Retorna versão específica do modelo."""
        if name in self._models:
            for v in self._models[name]["versions"]:
                if v["version"] == str(version):
                    mv = MagicMock()
                    mv.name = name
                    mv.version = v["version"]
                    mv.current_stage = v["current_stage"]
                    mv.run_id = v.get("run_id")
                    return mv
        return None

    def get_latest_versions(self, name: str, stages: list = None) -> list:
        """Retorna versões mais recentes por estágio."""
        if name not in self._models:
            return []

        stages = stages or ["None", "Staging", "Production", "Archived"]
        result = []

        for stage in stages:
            for v in reversed(self._models[name]["versions"]):
                if v["current_stage"] == stage:
                    mv = MagicMock()
                    mv.name = name
                    mv.version = v["version"]
                    mv.current_stage = stage
                    result.append(mv)
                    break

        return result

    def search_model_versions(self, filter_string: str) -> list:
        """Busca versões de modelo."""
        results = []

        # Parse simples do filtro
        if "name=" in filter_string:
            name = filter_string.split("name=")[1].strip("'\"")
            if name in self._models:
                for v in self._models[name]["versions"]:
                    mv = MagicMock()
                    mv.name = name
                    mv.version = v["version"]
                    mv.current_stage = v["current_stage"]
                    results.append(mv)

        return results


class MockMLflowRun:
    """Context manager mock para MLflow run."""

    def __init__(self, client: MockMLflowClient, run_name: str = None):
        self.client = client
        self.run_name = run_name
        self.run_id = f"run_{len(client._runs) + 1}"
        self._info = MagicMock()
        self._info.run_id = self.run_id

    def __enter__(self):
        self.client._runs[self.run_id] = {
            "params": {},
            "metrics": {},
            "artifacts": []
        }
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    @property
    def info(self):
        return self._info


# =============================================================================
# Fixtures Pytest
# =============================================================================

@pytest.fixture(scope="session")
def mlflow_test_tracking_uri() -> str:
    """
    Cria diretório temporário para tracking do MLflow.

    Returns:
        str: URI file:// para tracking de teste
    """
    temp_dir = tempfile.mkdtemp(prefix="mlflow_test_")
    tracking_uri = f"file://{temp_dir}"

    yield tracking_uri

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="session")
def mlflow_test_client(mlflow_test_tracking_uri: str):
    """
    Cliente MLflow configurado para testes.

    Tenta usar MLflow real se disponível, senão usa mock.

    Returns:
        MlflowClient ou MockMLflowClient
    """
    try:
        import mlflow
        from mlflow.tracking import MlflowClient

        mlflow.set_tracking_uri(mlflow_test_tracking_uri)
        client = MlflowClient(tracking_uri=mlflow_test_tracking_uri)

        # Cria experimento de teste
        experiment_name = "test_model_promotion"
        try:
            client.create_experiment(experiment_name)
        except Exception:
            pass

        mlflow.set_experiment(experiment_name)

        yield client

    except ImportError:
        # MLflow não instalado - usa mock
        yield MockMLflowClient(mlflow_test_tracking_uri)


@pytest.fixture
def mock_mlflow_client() -> MockMLflowClient:
    """
    Fixture: Cliente MLflow mock (sempre mock, nunca real).
    """
    return MockMLflowClient()


@pytest.fixture
async def seed_mlflow_models(mlflow_test_client, mock_duration_predictor) -> Dict[str, Any]:
    """
    Popula MLflow com versões de modelo baseline.

    Cria:
    - duration_predictor v1.0 (production)
    - duration_predictor v2.0 (candidate)

    Returns:
        Dict com informações das versões
    """
    model_name = "duration_predictor"

    # Verifica se é mock ou real
    if isinstance(mlflow_test_client, MockMLflowClient):
        # Usa mock
        mlflow_test_client.create_registered_model(model_name)

        v1 = mlflow_test_client.create_model_version(
            name=model_name,
            source="mock://v1",
            run_id="run_v1"
        )
        mlflow_test_client.log_metric("run_v1", "mae_percentage", 10.0)
        mlflow_test_client.log_metric("run_v1", "precision", 0.80)
        mlflow_test_client.transition_model_version_stage(
            name=model_name,
            version="1",
            stage="Production"
        )

        v2 = mlflow_test_client.create_model_version(
            name=model_name,
            source="mock://v2",
            run_id="run_v2"
        )
        mlflow_test_client.log_metric("run_v2", "mae_percentage", 8.0)
        mlflow_test_client.log_metric("run_v2", "precision", 0.85)

        return {
            "v1": {"run_id": "run_v1", "version": "1"},
            "v2": {"run_id": "run_v2", "version": "2"}
        }

    else:
        # Usa MLflow real
        try:
            import mlflow
            import mlflow.sklearn

            # Registra v1.0 (produção atual)
            with mlflow.start_run(run_name="duration_predictor_v1") as run:
                mlflow.log_param("version", "v1.0")
                mlflow.log_metric("mae_percentage", 10.0)
                mlflow.log_metric("precision", 0.80)
                mlflow.sklearn.log_model(mock_duration_predictor, "model")
                run_id_v1 = run.info.run_id

            # Registra modelo
            model_uri = f"runs:/{run_id_v1}/model"
            result = mlflow.register_model(model_uri, model_name)

            # Promove v1.0 para produção
            mlflow_test_client.transition_model_version_stage(
                name=model_name,
                version=result.version,
                stage="Production"
            )

            # Registra v2.0 (candidato)
            with mlflow.start_run(run_name="duration_predictor_v2") as run:
                mlflow.log_param("version", "v2.0")
                mlflow.log_metric("mae_percentage", 8.0)
                mlflow.log_metric("precision", 0.85)
                mlflow.sklearn.log_model(mock_duration_predictor, "model")
                run_id_v2 = run.info.run_id

            model_uri_v2 = f"runs:/{run_id_v2}/model"
            result_v2 = mlflow.register_model(model_uri_v2, model_name)

            return {
                "v1": {"run_id": run_id_v1, "version": result.version},
                "v2": {"run_id": run_id_v2, "version": result_v2.version}
            }

        except Exception as e:
            # Fallback para mock em caso de erro
            return {
                "v1": {"run_id": "run_v1_fallback", "version": "1"},
                "v2": {"run_id": "run_v2_fallback", "version": "2"}
            }
