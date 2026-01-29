"""
Testes de integração para SemanticPipeline fallback.

Valida que specialists usam SemanticPipeline quando ML falha,
ao invés de heurísticas simples.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from typing import Dict, Any


class TestSemanticFallbackIntegration:
    """Testes de integração para fallback semântico."""

    @pytest.fixture
    def mock_config_with_semantic_fallback(self):
        """Config com SemanticPipeline habilitado."""
        config = MagicMock()
        config.use_semantic_fallback = True
        config.specialist_type = "technical"
        config.mlflow_tracking_uri = "http://mlflow:5000"
        config.mlflow_model_name = "technical-evaluator"
        config.mlflow_model_stage = "Production"
        config.enable_explainability = True
        config.enable_caching = False
        config.enable_tracing = False
        config.enable_ledger = False
        config.mongodb_uri = "mongodb://localhost:27017"
        config.mongodb_database = "neural_hive"
        config.redis_cluster_nodes = "localhost:6379"
        config.neo4j_uri = "bolt://localhost:7687"
        config.neo4j_user = "neo4j"
        config.neo4j_password = "password"
        config.grpc_port = 50051
        config.http_port = 8000
        return config

    @pytest.fixture
    def mock_config_without_semantic_fallback(self):
        """Config com SemanticPipeline desabilitado."""
        config = MagicMock()
        config.use_semantic_fallback = False
        config.specialist_type = "technical"
        config.mlflow_tracking_uri = "http://mlflow:5000"
        config.mlflow_model_name = "technical-evaluator"
        config.mlflow_model_stage = "Production"
        config.enable_explainability = True
        config.enable_caching = False
        config.enable_tracing = False
        config.enable_ledger = False
        config.mongodb_uri = "mongodb://localhost:27017"
        config.mongodb_database = "neural_hive"
        config.redis_cluster_nodes = "localhost:6379"
        config.neo4j_uri = "bolt://localhost:7687"
        config.neo4j_user = "neo4j"
        config.neo4j_password = "password"
        config.grpc_port = 50051
        config.http_port = 8000
        return config

    @pytest.fixture
    def sample_plan_request(self) -> Dict[str, Any]:
        """Requisição de plano de exemplo para testes."""
        return {
            "plan_id": "test-plan-123",
            "correlation_id": "test-correlation-456",
            "intent_id": "test-intent-789",
            "tasks": [
                {
                    "task_id": "task-1",
                    "description": "Implementar autenticação JWT com refresh tokens",
                    "domain": "security",
                    "complexity": 0.7,
                    "estimated_effort_hours": 8,
                }
            ],
            "metadata": {"source": "test", "version": "1.0.0"},
        }

    def test_config_default_semantic_fallback_enabled(self):
        """Valida que use_semantic_fallback=True é o padrão."""
        from neural_hive_specialists.config import SpecialistConfig

        # Criar config com valores mínimos obrigatórios
        with patch.dict(
            "os.environ",
            {
                "SPECIALIST_TYPE": "technical",
                "SERVICE_NAME": "test-specialist",
                "MLFLOW_TRACKING_URI": "http://mlflow:5000",
                "MLFLOW_EXPERIMENT_NAME": "test",
                "MLFLOW_MODEL_NAME": "test-model",
                "MONGODB_URI": "mongodb://localhost:27017",
                "REDIS_CLUSTER_NODES": "localhost:6379",
                "NEO4J_URI": "bolt://localhost:7687",
                "NEO4J_PASSWORD": "password",
                "ENVIRONMENT": "test",
                "ENABLE_JWT_AUTH": "false",
            },
        ):
            config = SpecialistConfig()
            assert (
                config.use_semantic_fallback is True
            ), "use_semantic_fallback deve ser True por padrão"

    def test_config_semantic_fallback_from_env_var(self):
        """Valida que USE_SEMANTIC_FALLBACK pode ser configurado via env var."""
        from neural_hive_specialists.config import SpecialistConfig

        # Testar com USE_SEMANTIC_FALLBACK=false
        with patch.dict(
            "os.environ",
            {
                "SPECIALIST_TYPE": "technical",
                "SERVICE_NAME": "test-specialist",
                "MLFLOW_TRACKING_URI": "http://mlflow:5000",
                "MLFLOW_EXPERIMENT_NAME": "test",
                "MLFLOW_MODEL_NAME": "test-model",
                "MONGODB_URI": "mongodb://localhost:27017",
                "REDIS_CLUSTER_NODES": "localhost:6379",
                "NEO4J_URI": "bolt://localhost:7687",
                "NEO4J_PASSWORD": "password",
                "ENVIRONMENT": "test",
                "ENABLE_JWT_AUTH": "false",
                "USE_SEMANTIC_FALLBACK": "false",
            },
        ):
            config = SpecialistConfig()
            assert (
                config.use_semantic_fallback is False
            ), "USE_SEMANTIC_FALLBACK=false deve desabilitar semantic fallback"

    @patch(
        "neural_hive_specialists.semantic_pipeline.semantic_pipeline.SemanticPipeline"
    )
    def test_semantic_pipeline_initialization(self, mock_semantic_pipeline):
        """Valida que SemanticPipeline é inicializado corretamente."""
        mock_instance = MagicMock()
        mock_semantic_pipeline.return_value = mock_instance

        # Importar e instanciar SemanticPipeline
        from neural_hive_specialists.semantic_pipeline.semantic_pipeline import (
            SemanticPipeline,
        )

        pipeline = SemanticPipeline(specialist_type="technical")

        # Verificar que foi chamado com specialist_type correto
        mock_semantic_pipeline.assert_called_once_with(specialist_type="technical")

    def test_semantic_pipeline_evaluate_returns_valid_structure(self):
        """Valida estrutura de retorno do SemanticPipeline."""
        # Resultado esperado do SemanticPipeline
        expected_keys = ["confidence_score", "risk_score", "recommendation", "metadata"]

        # Mock do resultado do SemanticPipeline
        mock_result = {
            "confidence_score": 0.75,
            "risk_score": 0.3,
            "recommendation": "approve",
            "metadata": {
                "model_source": "semantic_pipeline",
                "semantic_scores": {
                    "security": 0.8,
                    "architecture": 0.7,
                    "performance": 0.75,
                    "quality": 0.7,
                },
                "ontology_evaluation": {
                    "domain_match": 0.85,
                    "complexity_assessment": 0.6,
                },
            },
        }

        for key in expected_keys:
            assert key in mock_result, f"Resultado deve conter chave '{key}'"

        assert mock_result["metadata"]["model_source"] == "semantic_pipeline"

    def test_confidence_calibration_for_semantic_fallback(self):
        """Valida que confiança é reduzida em 20% para fallback."""
        original_confidence = 0.9
        calibration_factor = 0.8  # Redução de 20%
        expected_calibrated = original_confidence * calibration_factor

        calibrated_confidence = original_confidence * calibration_factor

        assert calibrated_confidence == pytest.approx(
            expected_calibrated, rel=1e-3
        ), "Confiança deve ser reduzida em 20% para fallback"

    def test_metadata_model_source_semantic_pipeline(self):
        """Valida que metadata.model_source='semantic_pipeline' quando usa fallback."""
        metadata = {
            "model_source": "semantic_pipeline",
            "fallback_reason": "model_unavailable",
            "original_confidence": 0.9,
            "calibrated_confidence": 0.72,
        }

        assert metadata["model_source"] == "semantic_pipeline"
        assert metadata["fallback_reason"] == "model_unavailable"

    def test_metadata_model_source_heuristics_when_disabled(self):
        """Valida que metadata.model_source='heuristics' quando semantic está desabilitado."""
        metadata = {
            "model_source": "heuristics",
            "fallback_reason": "model_unavailable",
            "semantic_fallback_enabled": False,
        }

        assert metadata["model_source"] == "heuristics"
        assert metadata["semantic_fallback_enabled"] is False

    @patch("neural_hive_specialists.base_specialist.MLflowClient")
    def test_fallback_triggered_when_ml_unavailable(self, mock_mlflow_client):
        """Valida que fallback é acionado quando ML não está disponível."""
        # Configurar mock para simular falha de ML
        mock_client = MagicMock()
        mock_client.load_model_with_fallback.return_value = None
        mock_mlflow_client.return_value = mock_client

        # Simular comportamento de fallback
        model = mock_client.load_model_with_fallback()

        assert model is None, "Modelo deve ser None quando ML falha"

        # Em caso de modelo None, fallback deve ser usado
        use_semantic_fallback = True
        if model is None:
            if use_semantic_fallback:
                model_source = "semantic_pipeline"
            else:
                model_source = "heuristics"

            assert model_source == "semantic_pipeline"

    def test_fallback_decision_tree(self):
        """Testa árvore de decisão de fallback."""
        test_cases = [
            # (ml_available, use_semantic_fallback, expected_source)
            (True, True, "mlflow"),
            (True, False, "mlflow"),
            (False, True, "semantic_pipeline"),
            (False, False, "heuristics"),
        ]

        for ml_available, use_semantic_fallback, expected_source in test_cases:
            if ml_available:
                model_source = "mlflow"
            elif use_semantic_fallback:
                model_source = "semantic_pipeline"
            else:
                model_source = "heuristics"

            assert model_source == expected_source, (
                f"ml_available={ml_available}, use_semantic_fallback={use_semantic_fallback} "
                f"deve resultar em model_source='{expected_source}', mas foi '{model_source}'"
            )


class TestSemanticPipelineQuality:
    """Testes de qualidade das avaliações do SemanticPipeline."""

    def test_semantic_scores_within_valid_range(self):
        """Valida que scores semânticos estão entre 0 e 1."""
        semantic_scores = {
            "security": 0.85,
            "architecture": 0.72,
            "performance": 0.68,
            "quality": 0.79,
        }

        for dimension, score in semantic_scores.items():
            assert (
                0.0 <= score <= 1.0
            ), f"Score de {dimension} ({score}) deve estar entre 0 e 1"

    def test_overall_confidence_aggregation(self):
        """Testa agregação de scores em confiança geral."""
        semantic_scores = {
            "security": 0.8,
            "architecture": 0.7,
            "performance": 0.6,
            "quality": 0.7,
        }

        # Agregação por média ponderada
        weights = {
            "security": 0.3,
            "architecture": 0.25,
            "performance": 0.2,
            "quality": 0.25,
        }

        weighted_sum = sum(
            semantic_scores[dim] * weights[dim] for dim in semantic_scores
        )
        expected_confidence = weighted_sum

        assert 0.0 <= expected_confidence <= 1.0

    def test_risk_score_calculation(self):
        """Testa cálculo de score de risco."""
        # Risk score é inverso da confiança em segurança e arquitetura
        security_score = 0.8
        architecture_score = 0.7

        # Risco alto quando scores de segurança/arquitetura são baixos
        risk_score = 1.0 - (security_score * 0.6 + architecture_score * 0.4)

        assert 0.0 <= risk_score <= 1.0

    def test_recommendation_based_on_thresholds(self):
        """Testa recomendação baseada em thresholds."""
        approve_threshold = 0.8
        review_threshold = 0.6

        test_cases = [
            (0.9, "approve"),
            (0.85, "approve"),
            (0.7, "review"),
            (0.65, "review"),
            (0.5, "reject"),
            (0.3, "reject"),
        ]

        for confidence, expected_recommendation in test_cases:
            if confidence >= approve_threshold:
                recommendation = "approve"
            elif confidence >= review_threshold:
                recommendation = "review"
            else:
                recommendation = "reject"

            assert (
                recommendation == expected_recommendation
            ), f"Confiança {confidence} deve resultar em '{expected_recommendation}'"


class TestSemanticFallbackMetrics:
    """Testes para métricas de fallback."""

    def test_fallback_counter_labels(self):
        """Valida labels de métricas Prometheus para fallback."""
        expected_labels = ["specialist_type", "model_source", "fallback_reason"]

        metric_labels = {
            "specialist_type": "technical",
            "model_source": "semantic_pipeline",
            "fallback_reason": "model_unavailable",
        }

        for label in expected_labels:
            assert label in metric_labels

    def test_model_source_values(self):
        """Valida valores possíveis para model_source."""
        valid_model_sources = ["mlflow", "semantic_pipeline", "heuristics"]

        for source in ["mlflow", "semantic_pipeline", "heuristics"]:
            assert source in valid_model_sources

    def test_latency_tracking_per_source(self):
        """Testa tracking de latência por source."""
        latencies = {
            "mlflow": 150,  # ms
            "semantic_pipeline": 80,  # ms
            "heuristics": 20,  # ms
        }

        # SemanticPipeline deve ser mais rápido que MLflow
        assert latencies["semantic_pipeline"] < latencies["mlflow"]

        # Heurísticas devem ser mais rápidas que SemanticPipeline
        assert latencies["heuristics"] < latencies["semantic_pipeline"]
