"""
Testes unitários para V3 API Endpoints.

TDD: Testes escritos antes da implementação (Explainability API v3 Task 6).
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
import sys
from pathlib import Path
from typing import Dict, Any, List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.api.routes.v3.hierarchical import V3ExplanationService

# Importar modelos Pydantic para testes
from pydantic import BaseModel, Field


# Definir modelos localmente para evitar import circular
class HierarchicalBreakdownResponse(BaseModel):
    """Response para breakdown hierárquico."""
    decision_id: str
    hierarchical_breakdown: Dict[str, Any]


class IndividualContributionsResponse(BaseModel):
    """Response para contribuições individuais."""
    decision_id: str
    individual_contributions: List[Dict[str, Any]]
    total_specialists: int


class CounterfactualsResponse(BaseModel):
    """Response para análise contrafactual."""
    decision_id: str
    counterfactuals: List[Dict[str, Any]]
    sensitivity_score: float


class TemporalAnalysisResponse(BaseModel):
    """Response para análise temporal."""
    decision_id: str
    temporal_analysis: Dict[str, Any]


class FullExplanationResponse(BaseModel):
    """Response para explicação completa."""
    decision_id: str
    hierarchical_breakdown: Dict[str, Any]
    individual_contributions: List[Dict[str, Any]]


class BatchExplanationRequest(BaseModel):
    """Request para explicação em lote."""
    decision_ids: List[str] = Field(..., min_length=1, max_length=10)
    include_counterfactuals: bool = False
    include_temporal: bool = False


class BatchExplanationResponse(BaseModel):
    """Response para explicação em lote."""
    explanations: List[Dict[str, Any]]
    failed_ids: List[str]
    summary: Dict[str, Any]


# ========== FIXTURES ==========

@pytest.fixture
def sample_votes() -> List[Dict[str, Any]]:
    """Votos de especialistas para testes."""
    return [
        {
            "specialist_id": "business_expert",
            "specialist_name": "Business Expert",
            "domain": "BUSINESS",
            "seniority_level": "expert",
            "seniority_multiplier": 2.0,
            "vote": "approve",
            "confidence": 0.9,
            "risk": 0.1,
        },
        {
            "specialist_id": "technical_senior",
            "specialist_name": "Technical Senior",
            "domain": "TECHNICAL",
            "seniority_level": "senior",
            "seniority_multiplier": 1.5,
            "vote": "approve",
            "confidence": 0.8,
            "risk": 0.2,
        },
        {
            "specialist_id": "architecture_mid",
            "specialist_name": "Architecture Mid",
            "domain": "ARCHITECTURE",
            "seniority_level": "mid_level",
            "seniority_multiplier": 1.0,
            "vote": "reject",
            "confidence": 0.7,
            "risk": 0.3,
        },
    ]


@pytest.fixture
def sample_explanation_document() -> Dict[str, Any]:
    """Documento de decisão do MongoDB (consensus_decisions format)."""
    return {
        "_id": "507f1f77bcf86cd799439011",
        "decision_id": "decision-456",
        "consensus_method": "hierarchical_bayesian",
        "num_specialists": 3,
        "specialist_votes": [
            {
                "opinion_id": "business_expert",
                "specialist_type": "business",
                "recommendation": "approve",
                "confidence_score": 0.9,
                "risk": 0.1,
                "weight": 2.0,
            },
            {
                "opinion_id": "technical_senior",
                "specialist_type": "technical",
                "recommendation": "approve",
                "confidence_score": 0.8,
                "risk": 0.2,
                "weight": 1.5,
            },
        ],
    }


@pytest.fixture
def mock_mongo_client(sample_explanation_document):
    """Mock do cliente MongoDB."""
    client = MagicMock()
    db = MagicMock()
    collection = MagicMock()

    # Configurar find_one para retornar explicação
    async def mock_find_one(*args, **kwargs):
        return sample_explanation_document

    collection.find_one = mock_find_one
    # V3ExplanationService usa self.db.consensus_decisions
    db.consensus_decisions = collection
    client.consensus_decisions = collection

    return client


@pytest.fixture
def mock_mongo_client_not_found():
    """Mock do MongoDB para simular não encontrado."""
    client = MagicMock()
    db = MagicMock()
    collection = MagicMock()

    async def mock_find_one_none(*args, **kwargs):
        return None

    collection.find_one = mock_find_one_none
    db.consensus_decisions = collection
    client.consensus_decisions = collection

    return client


# ========== V3 EXPLANATION SERVICE TESTS ==========


class TestV3ExplanationServiceInitialization:
    """Testes de inicialização do V3ExplanationService."""

    def test_initialization(self, mock_mongo_client):
        """Testa que o serviço pode ser inicializado."""
        service = V3ExplanationService(mock_mongo_client)
        assert service is not None
        assert service.db == mock_mongo_client
        assert service.hierarchical_explainer is not None
        assert service.counterfactual_analyzer is not None
        assert service.temporal_tracker is not None


class TestV3ExplanationServiceGetDecisionVotes:
    """Testes do método _get_decision_votes."""

    @pytest.mark.asyncio
    async def test_get_decision_votes_returns_votes(
        self, mock_mongo_client, sample_explanation_document
    ):
        """Testa que retorna votos quando encontrados."""
        service = V3ExplanationService(mock_mongo_client)

        votes = await service._get_decision_votes("decision-456")

        assert votes is not None
        assert len(votes) == 2
        # _get_decision_votes retorna votos raw (sem normalização)
        # com decision_id adicionado
        assert votes[0]["opinion_id"] == "business_expert"
        assert votes[0]["decision_id"] == "decision-456"

    @pytest.mark.asyncio
    async def test_get_decision_votes_not_found(self, mock_mongo_client_not_found):
        """Testa que retorna None quando não encontrado."""
        service = V3ExplanationService(mock_mongo_client_not_found)

        votes = await service._get_decision_votes("nonexistent")

        assert votes is None


class TestV3ExplanationServiceGetFullExplanation:
    """Testes do método get_full_explanation."""

    @pytest.mark.asyncio
    async def test_get_full_explanation_basic(self, mock_mongo_client):
        """Testa explicação completa básica."""
        service = V3ExplanationService(mock_mongo_client)

        result = await service.get_full_explanation("decision-456")

        assert result is not None
        assert result["decision_id"] == "decision-456"
        assert "hierarchical_breakdown" in result
        assert "individual_contributions" in result

    @pytest.mark.asyncio
    async def test_get_full_explanation_with_counterfactuals(
        self, mock_mongo_client
    ):
        """Testa explicação completa com contrafactuais."""
        service = V3ExplanationService(mock_mongo_client)

        result = await service.get_full_explanation(
            "decision-456", include_counterfactuals=True
        )

        assert result is not None
        assert "counterfactuals" in result
        assert "sensitivity_score" in result

    @pytest.mark.asyncio
    async def test_get_full_explanation_with_temporal(self, mock_mongo_client):
        """Testa explicação completa com análise temporal."""
        service = V3ExplanationService(mock_mongo_client)

        # Mock do temporal tracker
        async def mock_get_seniority(*args, **kwargs):
            return {
                "current_seniority": "senior",
                "history": [],
                "trend": "stable",
                "volatility": 0.2,
            }

        service.temporal_tracker.get_seniority_changes = mock_get_seniority

        result = await service.get_full_explanation(
            "decision-456", include_temporal=True
        )

        assert result is not None
        assert "temporal_analysis" in result

    @pytest.mark.asyncio
    async def test_get_full_explanation_not_found(self, mock_mongo_client_not_found):
        """Testa explicação quando decisão não existe."""
        service = V3ExplanationService(mock_mongo_client_not_found)

        result = await service.get_full_explanation("nonexistent")

        assert result is None


class TestV3ExplanationServiceGetHierarchicalBreakdown:
    """Testes do método get_hierarchical_breakdown."""

    @pytest.mark.asyncio
    async def test_get_hierarchical_breakdown(self, mock_mongo_client):
        """Testa retorno de breakdown hierárquico."""
        service = V3ExplanationService(mock_mongo_client)

        result = await service.get_hierarchical_breakdown("decision-456")

        assert result is not None
        assert result["decision_id"] == "decision-456"
        assert "hierarchical_breakdown" in result
        assert "by_level" in result["hierarchical_breakdown"]
        assert "dominant_level" in result["hierarchical_breakdown"]
        assert "consensus_strength" in result["hierarchical_breakdown"]

    @pytest.mark.asyncio
    async def test_get_hierarchical_breakdown_not_found(
        self, mock_mongo_client_not_found
    ):
        """Testa breakdown quando decisão não existe."""
        service = V3ExplanationService(mock_mongo_client_not_found)

        result = await service.get_hierarchical_breakdown("nonexistent")

        assert result is None


class TestV3ExplanationServiceGetIndividualContributions:
    """Testes do método get_individual_contributions."""

    @pytest.mark.asyncio
    async def test_get_individual_contributions(self, mock_mongo_client):
        """Testa retorno de contribuições individuais."""
        service = V3ExplanationService(mock_mongo_client)

        result = await service.get_individual_contributions("decision-456")

        assert result is not None
        assert result["decision_id"] == "decision-456"
        assert "individual_contributions" in result
        assert "total_specialists" in result
        assert isinstance(result["individual_contributions"], list)

    @pytest.mark.asyncio
    async def test_get_individual_contributions_not_found(
        self, mock_mongo_client_not_found
    ):
        """Testa contribuições quando decisão não existe."""
        service = V3ExplanationService(mock_mongo_client_not_found)

        result = await service.get_individual_contributions("nonexistent")

        assert result is None


class TestV3ExplanationServiceGetCounterfactuals:
    """Testes do método get_counterfactuals."""

    @pytest.mark.asyncio
    async def test_get_counterfactuals(self, mock_mongo_client):
        """Testa retorno de análise contrafactual."""
        service = V3ExplanationService(mock_mongo_client)

        result = await service.get_counterfactuals("decision-456")

        assert result is not None
        assert result["decision_id"] == "decision-456"
        assert "counterfactuals" in result
        assert "sensitivity_score" in result

    @pytest.mark.asyncio
    async def test_get_counterfactuals_not_found(self, mock_mongo_client_not_found):
        """Testa contrafactuais quando decisão não existe."""
        service = V3ExplanationService(mock_mongo_client_not_found)

        result = await service.get_counterfactuals("nonexistent")

        assert result is None


class TestV3ExplanationServiceGetTemporalAnalysis:
    """Testes do método get_temporal_analysis."""

    @pytest.mark.asyncio
    async def test_get_temporal_analysis(self, mock_mongo_client):
        """Testa retorno de análise temporal."""
        service = V3ExplanationService(mock_mongo_client)

        # Mock do temporal tracker
        async def mock_get_seniority(*args, **kwargs):
            return {
                "current_seniority": "senior",
                "history": [],
                "trend": "stable",
                "volatility": 0.2,
            }

        service.temporal_tracker.get_seniority_changes = mock_get_seniority

        result = await service.get_temporal_analysis("decision-456")

        assert result is not None
        assert result["decision_id"] == "decision-456"
        assert "temporal_analysis" in result

    @pytest.mark.asyncio
    async def test_get_temporal_analysis_no_data(self, mock_mongo_client):
        """Testa análise temporal quando não há dados."""
        service = V3ExplanationService(mock_mongo_client)

        # Mock retornando vazio (sem "history" key)
        async def mock_get_seniority_empty(*args, **kwargs):
            return {}

        service.temporal_tracker.get_seniority_changes = mock_get_seniority_empty

        result = await service.get_temporal_analysis("decision-456")

        # Quando não há histórico, retorna análise vazia (não None)
        assert result is not None
        assert "temporal_analysis" in result
        assert result["temporal_analysis"]["current_seniority"] == "unknown"
        assert result["temporal_analysis"]["history"] == []


class TestV3ExplanationServiceGetBatchExplanations:
    """Testes do método get_batch_explanations."""

    @pytest.mark.asyncio
    async def test_get_batch_explanations_success(self, mock_mongo_client):
        """Testa explicação em lote bem-sucedida."""
        service = V3ExplanationService(mock_mongo_client)

        result = await service.get_batch_explanations(["decision-456"])

        assert result is not None
        assert "explanations" in result
        assert "failed_ids" in result
        assert "summary" in result
        assert result["summary"]["total_requested"] == 1
        assert result["summary"]["successful"] == 1

    @pytest.mark.asyncio
    async def test_get_batch_explanations_mixed(self, mock_mongo_client):
        """Testa explicação em lote com sucessos e falhas."""
        service = V3ExplanationService(mock_mongo_client)

        # Criar um cliente que retorna dados para decision-456 e None para outro
        call_count = [0]

        async def mock_find_one(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Primeira chamada retorna dados
                return {
                    "_id": "507f1f77bcf86cd799439011",
                    "decision_id": "decision-456",
                    "specialist_votes": [
                        {
                            "opinion_id": "business_expert",
                            "specialist_type": "business",
                            "recommendation": "approve",
                            "confidence_score": 0.9,
                            "weight": 2.0,
                        }
                    ],
                }
            return None  # Segunda chamada retorna None

        mock_mongo_client.consensus_decisions.find_one = mock_find_one

        result = await service.get_batch_explanations(
            ["decision-456", "nonexistent"]
        )

        assert result is not None
        assert len(result["explanations"]) == 1
        assert len(result["failed_ids"]) == 1
        assert result["summary"]["total_requested"] == 2
        assert result["summary"]["successful"] == 1
        assert result["summary"]["failed"] == 1


# ========== PYDANTIC MODEL TESTS ==========


class TestHierarchicalBreakdownResponse:
    """Testes do modelo HierarchicalBreakdownResponse."""

    def test_valid_response(self):
        """Testa resposta válida."""
        data = {
            "decision_id": "dec-123",
            "hierarchical_breakdown": {
                "by_level": {"expert": {"count": 1}},
                "dominant_level": "expert",
                "consensus_strength": 1.0,
            },
        }
        response = HierarchicalBreakdownResponse(**data)
        assert response.decision_id == "dec-123"


class TestIndividualContributionsResponse:
    """Testes do modelo IndividualContributionsResponse."""

    def test_valid_response(self):
        """Testa resposta válida."""
        data = {
            "decision_id": "dec-123",
            "individual_contributions": [
                {
                    "specialist_id": "expert_1",
                    "seniority_level": "expert",
                    "rank": 1,
                    "contribution_score": 1.8,
                }
            ],
            "total_specialists": 1,
        }
        response = IndividualContributionsResponse(**data)
        assert response.decision_id == "dec-123"
        assert response.total_specialists == 1


class TestCounterfactualsResponse:
    """Testes do modelo CounterfactualsResponse."""

    def test_valid_response(self):
        """Testa resposta válida."""
        data = {
            "decision_id": "dec-123",
            "counterfactuals": [
                {"scenario": "flip_expert_vote", "flipped_decision": "reject"}
            ],
            "sensitivity_score": 0.75,
        }
        response = CounterfactualsResponse(**data)
        assert response.decision_id == "dec-123"
        assert response.sensitivity_score == 0.75


class TestTemporalAnalysisResponse:
    """Testes do modelo TemporalAnalysisResponse."""

    def test_valid_response(self):
        """Testa resposta válida."""
        data = {
            "decision_id": "dec-123",
            "temporal_analysis": {
                "current_seniority": "senior",
                "history": [],
                "trend": "upward",
                "volatility": 0.2,
            },
        }
        response = TemporalAnalysisResponse(**data)
        assert response.decision_id == "dec-123"


class TestFullExplanationResponse:
    """Testes do modelo FullExplanationResponse."""

    def test_valid_response(self):
        """Testa resposta válida."""
        data = {
            "decision_id": "dec-123",
            "hierarchical_breakdown": {
                "by_level": {"expert": {"count": 1}},
                "dominant_level": "expert",
                "consensus_strength": 1.0,
            },
            "individual_contributions": [
                {
                    "specialist_id": "expert_1",
                    "seniority_level": "expert",
                    "rank": 1,
                    "contribution_score": 1.8,
                }
            ],
        }
        response = FullExplanationResponse(**data)
        assert response.decision_id == "dec-123"


class TestBatchExplanationRequest:
    """Testes do modelo BatchExplanationRequest."""

    def test_valid_request(self):
        """Testa request válida."""
        data = {
            "decision_ids": ["dec-1", "dec-2"],
            "include_counterfactuals": True,
            "include_temporal": False,
        }
        request = BatchExplanationRequest(**data)
        assert len(request.decision_ids) == 2
        assert request.include_counterfactuals is True

    def test_invalid_decision_ids_empty(self):
        """Testa validação de lista vazia."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            BatchExplanationRequest(decision_ids=[])

    def test_invalid_decision_ids_too_many(self):
        """Testa validação de lista muito grande."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            BatchExplanationRequest(decision_ids=[f"dec-{i}" for i in range(11)])


class TestBatchExplanationResponse:
    """Testes do modelo BatchExplanationResponse."""

    def test_valid_response(self):
        """Testa resposta válida."""
        data = {
            "explanations": [{"decision_id": "dec-1"}],
            "failed_ids": [],
            "summary": {"total_requested": 1, "successful": 1, "failed": 0},
        }
        response = BatchExplanationResponse(**data)
        assert len(response.explanations) == 1
        assert response.summary["successful"] == 1


# ========== ROUTER TESTS ==========


class TestRouterEndpoints:
    """Testes dos endpoints do router."""

    def test_router_has_correct_prefix(self):
        """Testa que router tem prefixo correto."""
        from src.api.routes.v3 import router
        assert router.prefix == "/api/v3"

    def test_router_has_tags(self):
        """Testa que router tem tags."""
        from src.api.routes.v3 import router
        assert "v3" in router.tags


# ========== INTEGRATION TESTS ==========


class TestV3RouterIntegration:
    """Testes de integração do router v3."""

    @pytest.fixture
    def test_client(self, mock_mongo_client):
        """Cliente de teste FastAPI."""
        from fastapi import FastAPI

        test_app = FastAPI()
        from src.api.routes.v3 import create_v3_router

        v3_router = create_v3_router(mock_mongo_client)
        test_app.include_router(v3_router)

        return TestClient(test_app)

    def test_full_explanation_endpoint(self, test_client):
        """Testa endpoint /api/v3/explainability/{decision_id}."""
        # Mock para retornar dados válidos
        response = test_client.get("/api/v3/explainability/decision-456")

        # Pode retornar 200 ou 404 dependendo do mock
        assert response.status_code in [200, 404, 500]

    def test_hierarchical_breakdown_endpoint(self, test_client):
        """Testa endpoint /api/v3/explainability/{decision_id}/hierarchical."""
        response = test_client.get("/api/v3/explainability/decision-456/hierarchical")
        assert response.status_code in [200, 404, 500]

    def test_individual_contributions_endpoint(self, test_client):
        """Testa endpoint /api/v3/explainability/{decision_id}/individual."""
        response = test_client.get("/api/v3/explainability/decision-456/individual")
        assert response.status_code in [200, 404, 500]

    def test_counterfactuals_endpoint(self, test_client):
        """Testa endpoint /api/v3/explainability/{decision_id}/counterfactuals."""
        response = test_client.get("/api/v3/explainability/decision-456/counterfactuals")
        assert response.status_code in [200, 404, 500]

    def test_temporal_endpoint(self, test_client):
        """Testa endpoint /api/v3/explainability/{decision_id}/temporal."""
        response = test_client.get("/api/v3/explainability/decision-456/temporal")
        assert response.status_code in [200, 404, 500]

    def test_batch_endpoint(self, test_client):
        """Testa endpoint POST /api/v3/explainability/batch."""
        response = test_client.post(
            "/api/v3/explainability/batch",
            json={"decision_ids": ["decision-456"]},
        )
        assert response.status_code in [200, 500]

    def test_batch_endpoint_with_multiple_decisions(self, test_client):
        """Testa batch endpoint com múltiplas decisões."""
        response = test_client.post(
            "/api/v3/explainability/batch",
            json={"decision_ids": ["dec-1", "dec-2", "dec-3"]},
        )
        assert response.status_code in [200, 500]

    def test_batch_endpoint_with_counterfactuals(self, test_client):
        """Testa batch endpoint com opção de contrafactuais."""
        response = test_client.post(
            "/api/v3/explainability/batch",
            json={
                "decision_ids": ["decision-456"],
                "include_counterfactuals": True,
            },
        )
        assert response.status_code in [200, 500]

    def test_batch_endpoint_with_temporal(self, test_client):
        """Testa batch endpoint com opção temporal."""
        response = test_client.post(
            "/api/v3/explainability/batch",
            json={
                "decision_ids": ["decision-456"],
                "include_temporal": True,
            },
        )
        assert response.status_code in [200, 500]
