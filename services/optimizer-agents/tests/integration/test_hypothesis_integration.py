"""
Testes de integração para Hypothesis Library.

Este módulo testa a integração entre optimizer-agents e hypothesis-library,
incluindo:
- Conversão de OptimizationHypothesis para HypothesisCreate
- Criação de hipóteses no hypothesis-library
- Início de testes
- Sincronização de resultados
"""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from src.clients.hypothesis_library_client import HypothesisLibraryClient
from src.models.optimization_hypothesis import (
    OptimizationHypothesis,
    OptimizationType,
)
from src.services.experiment_manager import ExperimentManager
from src.services.hypothesis_converter import HypothesisConverter

# ============================================================================
# Testes do HypothesisConverter
# ============================================================================


class TestHypothesisConverter:
    """Testes para o conversor de hipóteses."""

    def test_converter_initialization(self):
        """Testa inicialização do conversor."""
        converter = HypothesisConverter()
        assert converter.default_author == "optimizer-agents"

    def test_converter_custom_author(self):
        """Testa inicialização com autor customizado."""
        converter = HypothesisConverter(default_author="test-author")
        assert converter.default_author == "test-author"

    def test_to_hypothesis_create_success(self, sample_optimization_hypothesis):
        """Testa conversão bem-sucedida de hipótese."""
        converter = HypothesisConverter()
        result = converter.to_hypothesis_create(sample_optimization_hypothesis)

        # Verificar campos obrigatórios
        assert "title" in result
        assert "description" in result
        assert "background" in result
        assert "expected_outcome" in result
        assert "metrics" in result
        assert "baseline_metrics" in result
        assert "target_metrics" in result
        assert "priority" in result
        assert "author" in result
        assert "tags" in result
        assert "metadata" in result

        # Verificar valores
        assert result["author"] == "optimizer-agents"
        assert result["requires_experiment"] is True
        assert result["auto_approve"] is False
        assert "component:consensus-engine" in result["tags"]
        assert "weight_recalibration" in result["tags"]
        assert "auto-generated" in result["tags"]

        # Verificar metadata
        assert (
            result["metadata"]["optimizer_hypothesis_id"]
            == sample_optimization_hypothesis.hypothesis_id
        )
        assert result["metadata"]["optimizer_source"] == "optimizer-agents"
        assert result["metadata"]["optimization_type"] == "WEIGHT_RECALIBRATION"

    def test_priority_mapping(self):
        """Testa mapeamento de prioridade."""
        converter = HypothesisConverter()

        # Priority 1 -> CRITICAL
        assert converter._map_priority(1) == "CRITICAL"

        # Priority 2 -> HIGH
        assert converter._map_priority(2) == "HIGH"

        # Priority 3 -> MEDIUM
        assert converter._map_priority(3) == "MEDIUM"

        # Priority 4 -> LOW
        assert converter._map_priority(4) == "LOW"

        # Priority 5 -> LOW
        assert converter._map_priority(5) == "LOW"

    def test_title_generation(self, sample_optimization_hypothesis):
        """Testa geração de título."""
        converter = HypothesisConverter()
        title = converter._generate_title(sample_optimization_hypothesis)

        assert "[Weight Recalibration]" in title
        assert "consensus-engine" in title
        assert len(title) <= converter.MAX_TITLE_LENGTH

    def test_title_truncation(self):
        """Testa truncamento de título longo."""
        converter = HypothesisConverter()

        # Criar hipótese com texto muito longo
        hypothesis = OptimizationHypothesis(
            hypothesis_id=str(uuid4()),
            hypothesis_text="x" * 300,  # Texto muito longo
            optimization_type=OptimizationType.WEIGHT_RECALIBRATION,
            target_component="test-component",
            baseline_metrics={"metric1": 100.0},
            target_metrics={"metric1": 150.0},
            proposed_adjustments=[],
            expected_improvement=0.1,
            confidence_score=0.8,
            risk_score=0.2,
            priority=3,
        )

        title = converter._generate_title(hypothesis)
        assert len(title) <= converter.MAX_TITLE_LENGTH
        assert title.endswith("...")

    def test_description_generation(self, sample_optimization_hypothesis):
        """Testa geração de descrição."""
        converter = HypothesisConverter()
        description = converter._generate_description(sample_optimization_hypothesis)

        assert "Tipo de Otimizacao:" in description
        assert "Componente Alvo:" in description
        assert "Ajustes Propostos:" in description
        assert "Melhoria Esperada:" in description
        assert "Confianca:" in description
        assert "Risco:" in description

    def test_tags_generation(self, sample_optimization_hypothesis):
        """Testa geração de tags."""
        converter = HypothesisConverter()
        tags = converter._generate_tags(sample_optimization_hypothesis)

        assert "weight_recalibration" in tags
        assert "component:consensus-engine" in tags
        assert "auto-generated" in tags

    def test_tags_critical_priority(self):
        """Testa tag de prioridade crítica."""
        hypothesis = OptimizationHypothesis(
            hypothesis_id=str(uuid4()),
            hypothesis_text="Critical hypothesis",
            optimization_type=OptimizationType.WEIGHT_RECALIBRATION,
            target_component="test-component",
            baseline_metrics={"metric1": 100.0},
            target_metrics={"metric1": 150.0},
            proposed_adjustments=[],
            expected_improvement=0.1,
            confidence_score=0.8,
            risk_score=0.2,
            priority=1,  # Critical
        )

        converter = HypothesisConverter()
        tags = converter._generate_tags(hypothesis)

        assert "critical" in tags

    def test_tags_high_risk(self):
        """Testa tag de alto risco."""
        hypothesis = OptimizationHypothesis(
            hypothesis_id=str(uuid4()),
            hypothesis_text="High risk hypothesis",
            optimization_type=OptimizationType.WEIGHT_RECALIBRATION,
            target_component="test-component",
            baseline_metrics={"metric1": 100.0},
            target_metrics={"metric1": 150.0},
            proposed_adjustments=[],
            expected_improvement=0.1,
            confidence_score=0.8,
            risk_score=0.8,  # High risk
            priority=3,
        )

        converter = HypothesisConverter()
        tags = converter._generate_tags(hypothesis)

        assert "high-risk" in tags

    def test_metadata_enrichment(self, sample_optimization_hypothesis):
        """Testa enriquecimento de metadata."""
        converter = HypothesisConverter()
        metadata = converter._enrich_metadata(sample_optimization_hypothesis)

        assert metadata["optimizer_hypothesis_id"] == sample_optimization_hypothesis.hypothesis_id
        assert metadata["optimizer_source"] == "optimizer-agents"
        assert metadata["optimization_type"] == "WEIGHT_RECALIBRATION"
        assert metadata["confidence_score"] == sample_optimization_hypothesis.confidence_score
        assert metadata["risk_score"] == sample_optimization_hypothesis.risk_score
        assert (
            metadata["expected_improvement"] == sample_optimization_hypothesis.expected_improvement
        )

    def test_validation_missing_hypothesis_text(self):
        """Testa validação com hypothesis_text vazio."""
        converter = HypothesisConverter()

        hypothesis = OptimizationHypothesis(
            hypothesis_id=str(uuid4()),
            hypothesis_text="",  # Vazio
            optimization_type=OptimizationType.WEIGHT_RECALIBRATION,
            target_component="test-component",
            baseline_metrics={"metric1": 100.0},
            target_metrics={"metric1": 150.0},
            proposed_adjustments=[],
            expected_improvement=0.1,
            confidence_score=0.8,
            risk_score=0.2,
            priority=3,
        )

        with pytest.raises(ValueError, match="hypothesis_text is required"):
            converter.to_hypothesis_create(hypothesis)

    def test_validation_invalid_priority(self):
        """Testa validação com prioridade inválida."""
        converter = HypothesisConverter()

        # Criar hipótese válida e depois modificar o priority diretamente
        # para bypassar validação do Pydantic
        hypothesis_dict = {
            "hypothesis_id": str(uuid4()),
            "hypothesis_text": "Test hypothesis",
            "optimization_type": OptimizationType.WEIGHT_RECALIBRATION,
            "target_component": "test-component",
            "baseline_metrics": {"metric1": 100.0},
            "target_metrics": {"metric1": 150.0},
            "proposed_adjustments": [],
            "expected_improvement": 0.1,
            "confidence_score": 0.8,
            "risk_score": 0.2,
            "priority": 3,  # Válido para criação
        }

        hypothesis = OptimizationHypothesis(**hypothesis_dict)
        hypothesis.priority = 10  # Modificar para inválido após criação

        with pytest.raises(ValueError, match="priority must be between 1 and 5"):
            converter.to_hypothesis_create(hypothesis)


# ============================================================================
# Testes do HypothesisLibraryClient
# ============================================================================


class TestHypothesisLibraryClient:
    """Testes para o cliente do Hypothesis Library."""

    @pytest.fixture
    def mock_client(self):
        """Cliente para testes."""
        return HypothesisLibraryClient(base_url="http://test:8001")

    @pytest.mark.asyncio
    async def test_create_hypothesis_success(self, mock_client):
        """Testa criação de hipótese com sucesso."""
        hypothesis_data = {
            "title": "Test Hypothesis",
            "description": "Test description",
            "expected_outcome": "Improved metrics",
            "metrics": ["latency_p95"],
            "baseline_metrics": {"latency_p95": 200.0},
            "target_metrics": {"latency_p95": 150.0},
            "priority": "MEDIUM",
            "tags": ["test"],
            "requires_experiment": True,
            "auto_approve": False,
            "metadata": {},
        }

        # Mock da resposta HTTP
        with patch.object(mock_client.client, "post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                "hypothesis_id": "hyp-001",
                "title": "Test Hypothesis",
                "status": "DRAFT",
            }
            mock_post.return_value = mock_response

            result = await mock_client.create_hypothesis(hypothesis_data)

            assert result is not None
            assert result["hypothesis_id"] == "hyp-001"

    @pytest.mark.asyncio
    async def test_start_testing_success(self, mock_client):
        """Testa início de teste com sucesso."""
        with patch.object(mock_client.client, "post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "hypothesis": {"hypothesis_id": "hyp-001", "status": "IN_TESTING"},
                "transition": {"from_status": "APPROVED", "to_status": "IN_TESTING"},
            }
            mock_post.return_value = mock_response

            result = await mock_client.start_testing(
                hypothesis_id="hyp-001", experiment_id="exp-001"
            )

            assert result is not None
            assert result["hypothesis"]["status"] == "IN_TESTING"

    @pytest.mark.asyncio
    async def test_complete_testing_success(self, mock_client):
        """Testa conclusão de teste com sucesso."""
        results = {
            "experiment_id": "exp-001",
            "status": "COMPLETED",
            "outcome": "validated",
            "confidence_level": 0.95,
            "improvement_percentage": 25.0,
            "statistical_significance": True,
            "actual_baseline_metrics": {"latency_p95": 200.0},
            "actual_target_metrics": {"latency_p95": 150.0},
            "lessons_learned": ["Test validated successfully"],
        }

        with patch.object(mock_client.client, "post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "hypothesis": {"hypothesis_id": "hyp-001", "status": "COMPLETED"},
                "transition": {"from_status": "IN_TESTING", "to_status": "COMPLETED"},
            }
            mock_post.return_value = mock_response

            result = await mock_client.complete_testing(hypothesis_id="hyp-001", results=results)

            assert result is not None
            assert result["hypothesis"]["status"] == "COMPLETED"

    @pytest.mark.asyncio
    async def test_health_check_success(self, mock_client):
        """Testa health check com sucesso."""
        with patch.object(mock_client.client, "get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            is_healthy = await mock_client.health_check()

            assert is_healthy is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, mock_client):
        """Testa health check com falha."""
        with patch.object(mock_client.client, "get") as mock_get:
            mock_get.side_effect = Exception("Connection error")

            is_healthy = await mock_client.health_check()

            assert is_healthy is False


# ============================================================================
# Testes de Integração do ExperimentManager
# ============================================================================


class TestExperimentManagerHypothesisIntegration:
    """Testes de integração do ExperimentManager com Hypothesis Library."""

    @pytest.fixture
    def manager(self, mock_settings, mock_hypothesis_client):
        """ExperimentManager com integração de hipóteses."""
        converter = HypothesisConverter()
        return ExperimentManager(
            settings=mock_settings,
            hypothesis_converter=converter,
            hypothesis_client=mock_hypothesis_client,
        )

    @pytest.fixture
    def mock_hypothesis_client(self):
        """Mock do HypothesisLibraryClient."""
        client = AsyncMock()
        client.create_hypothesis = AsyncMock(
            return_value={
                "hypothesis_id": "lib-hyp-001",
                "title": "Test Hypothesis",
                "status": "DRAFT",
            }
        )
        client.start_testing = AsyncMock(
            return_value={
                "hypothesis": {"hypothesis_id": "lib-hyp-001", "status": "IN_TESTING"},
                "transition": {"from_status": "APPROVED", "to_status": "IN_TESTING"},
            }
        )
        client.complete_testing = AsyncMock(
            return_value={
                "hypothesis": {"hypothesis_id": "lib-hyp-001", "status": "COMPLETED"},
                "transition": {"from_status": "IN_TESTING", "to_status": "COMPLETED"},
            }
        )
        client.get_hypothesis = AsyncMock(
            return_value={
                "hypothesis": {"hypothesis_id": "lib-hyp-001", "status": "IN_TESTING"},
            }
        )
        client.health_check = AsyncMock(return_value=True)
        return client

    @pytest.mark.asyncio
    async def test_submit_experiment_with_hypothesis_success(
        self, manager, mock_hypothesis_client, sample_optimization_hypothesis
    ):
        """Testa submissão de experimento com criação de hipótese."""
        # Mock do submit_experiment (que é chamado internamente)
        manager.submit_experiment = AsyncMock(return_value="exp-001")

        result = await manager.submit_experiment_with_hypothesis(sample_optimization_hypothesis)

        assert result is not None
        assert result["experiment_id"] == "exp-001"
        assert result["hypothesis_id"] == "lib-hyp-001"
        assert result["hypothesis_created"] is True
        assert result["testing_started"] is True

        # Verificar chamadas
        mock_hypothesis_client.create_hypothesis.assert_called_once()
        mock_hypothesis_client.start_testing.assert_called_once_with(
            hypothesis_id="lib-hyp-001", experiment_id="exp-001", started_by="optimizer-agents"
        )

    @pytest.mark.asyncio
    async def test_submit_experiment_with_hypothesis_fallback(
        self, mock_settings, sample_optimization_hypothesis
    ):
        """Testa fallback quando integração não está disponível."""
        # Manager sem integração
        manager = ExperimentManager(
            settings=mock_settings,
            hypothesis_converter=None,
            hypothesis_client=None,
        )

        manager.submit_experiment = AsyncMock(return_value="exp-001")

        result = await manager.submit_experiment_with_hypothesis(sample_optimization_hypothesis)

        assert result is not None
        assert result["experiment_id"] == "exp-001"
        assert result["hypothesis_id"] is None
        assert result["hypothesis_created"] is False
        assert result["fallback_mode"] is True

    @pytest.mark.asyncio
    async def test_complete_experiment_with_hypothesis_validated(
        self, manager, mock_hypothesis_client
    ):
        """Testa conclusão de experimento com hipótese validada."""
        analysis = {
            "recommendation": "APPLY",
            "success": True,
            "confidence": 0.95,
            "improvement_percentage": 25.0,
            "baseline_metrics": {"latency_p95": 200.0},
            "experimental_metrics": {"latency_p95": 150.0},
            "control_size": 500,
            "treatment_size": 500,
        }

        result = await manager.complete_experiment_with_hypothesis(
            experiment_id="exp-001", hypothesis_id="lib-hyp-001", analysis=analysis
        )

        assert result is not None
        assert result["hypothesis_updated"] is True
        assert result["outcome"] == "validated"

        # Verificar chamada
        mock_hypothesis_client.complete_testing.assert_called_once()
        call_args = mock_hypothesis_client.complete_testing.call_args
        assert call_args[1]["hypothesis_id"] == "lib-hyp-001"
        assert call_args[1]["results"]["outcome"] == "validated"

    @pytest.mark.asyncio
    async def test_complete_experiment_with_hypothesis_refuted(
        self, manager, mock_hypothesis_client
    ):
        """Testa conclusão de experimento com hipótese refutada."""
        analysis = {
            "recommendation": "REJECT",
            "success": False,
            "confidence": 0.95,
            "improvement_percentage": -10.0,
            "baseline_metrics": {"latency_p95": 200.0},
            "experimental_metrics": {"latency_p95": 220.0},
        }

        result = await manager.complete_experiment_with_hypothesis(
            experiment_id="exp-001", hypothesis_id="lib-hyp-001", analysis=analysis
        )

        assert result is not None
        assert result["hypothesis_updated"] is True
        assert result["outcome"] == "refuted"

    @pytest.mark.asyncio
    async def test_complete_experiment_with_hypothesis_inconclusive(
        self, manager, mock_hypothesis_client
    ):
        """Testa conclusão de experimento com resultado inconclusivo."""
        analysis = {
            "recommendation": "INCONCLUSIVE",
            "success": True,
            "confidence": 0.5,
            "improvement_percentage": 2.0,
            "baseline_metrics": {"latency_p95": 200.0},
            "experimental_metrics": {"latency_p95": 196.0},
        }

        result = await manager.complete_experiment_with_hypothesis(
            experiment_id="exp-001", hypothesis_id="lib-hyp-001", analysis=analysis
        )

        assert result is not None
        assert result["hypothesis_updated"] is True
        assert result["outcome"] == "inconclusive"

    @pytest.mark.asyncio
    async def test_complete_experiment_without_client(self, mock_settings):
        """Testa conclusão quando cliente não está disponível."""
        manager = ExperimentManager(
            settings=mock_settings,
            hypothesis_client=None,
        )

        analysis = {"recommendation": "APPLY", "success": True}

        result = await manager.complete_experiment_with_hypothesis(
            experiment_id="exp-001", hypothesis_id="lib-hyp-001", analysis=analysis
        )

        assert result is not None
        assert result["hypothesis_updated"] is False
        assert "error" in result

    def test_generate_lessons_learned_validated(self, mock_settings):
        """Testa geração de aprendizados para hipótese validada."""
        manager = ExperimentManager(settings=mock_settings)

        analysis = {
            "recommendation": "APPLY",
            "success": True,
            "improvement_percentage": 25.0,
            "confidence": 0.95,
            "primary_metrics_analysis": [
                {
                    "metric_name": "latency_p95",
                    "control_mean": 200.0,
                    "treatment_mean": 150.0,
                }
            ],
        }

        lessons = manager._generate_lessons_learned(analysis, None)

        assert "validada" in lessons.lower()
        assert "25.0%" in lessons
        assert "95.0%" in lessons

    def test_generate_lessons_learned_refuted(self, mock_settings):
        """Testa geração de aprendizados para hipótese refutada."""
        manager = ExperimentManager(settings=mock_settings)

        analysis = {
            "recommendation": "REJECT",
            "success": False,
            "improvement_percentage": -10.0,
            "confidence": 0.95,
        }

        lessons = manager._generate_lessons_learned(analysis, None)

        assert "refutada" in lessons.lower()
        assert "-10.0%" in lessons
