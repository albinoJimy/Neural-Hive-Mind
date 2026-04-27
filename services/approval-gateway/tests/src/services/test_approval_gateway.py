"""Tests para ApprovalGateway service."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.models.approval import (
    ApprovalPolicy,
    ApprovalRequest,
    ApprovalStatus,
    ApprovalType,
)
from src.services.approval_gateway import ApprovalGateway


@pytest.fixture()
def mock_repository():
    """Mock do repositório de aprovações."""
    repo = MagicMock()
    repo.save_request = AsyncMock()
    repo.get_by_request_id = AsyncMock(return_value=None)
    repo.update_decision = AsyncMock(return_value=True)
    repo.list = AsyncMock(return_value=([], 0))
    repo.count_by_status = AsyncMock(return_value=0)
    repo.expire_old_pending = AsyncMock(return_value=0)
    repo.get_metrics = AsyncMock(
        return_value={"total": 0, "approved": 0, "rejected": 0, "pending": 0, "expired": 0}
    )
    return repo


@pytest.mark.asyncio()
class TestApprovalGateway:
    """Testes para ApprovalGateway."""

    async def test_evaluate_high_confidence(self, mock_openai_client, mock_repository):
        """Testa avaliação com alta confiança -> aprovação automática."""
        mock_openai_client.generate = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message={
                            "content": "AVALIACAO: 90\nRACIOCINIO: Solicitação clara e bem estruturada",
                            "role": "assistant",
                        }
                    )
                ]
            )
        )

        gateway = ApprovalGateway(llm_client=mock_openai_client, repository=mock_repository)

        request = ApprovalRequest(
            id="REQ-001",
            type=ApprovalType.REQUIREMENT,
            title="Simple Login",
            description="Implementação simples de login",
            requested_by="dev@example.com",
            context={"complexity": 2, "is_critical": False},
        )

        decision = await gateway.evaluate_request(request)

        assert decision.status == ApprovalStatus.APPROVED
        assert decision.confidence_score >= 0.8
        assert "ai-" in decision.approved_by

    async def test_evaluate_low_confidence(self, mock_openai_client, mock_repository):
        """Testa avaliação com baixa confiança -> rejeição automática."""
        mock_openai_client.generate = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message={
                            "content": "AVALIACAO: 20\nRACIOCINIO: Requisitos vagos e mal definidos",
                            "role": "assistant",
                        }
                    )
                ]
            )
        )

        gateway = ApprovalGateway(llm_client=mock_openai_client, repository=mock_repository)

        request = ApprovalRequest(
            id="REQ-002",
            type=ApprovalType.REQUIREMENT,
            title="Vague Feature",
            description="Algo qualquer",
            requested_by="dev@example.com",
        )

        decision = await gateway.evaluate_request(request)

        assert decision.status == ApprovalStatus.REJECTED
        assert decision.confidence_score <= 0.3

    async def test_evaluate_medium_confidence(self, mock_openai_client, mock_repository):
        """Testa avaliação com confiança média -> requer humano."""
        mock_openai_client.generate = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message={
                            "content": "AVALIACAO: 50\nRACIOCINIO: Requer análise mais detalhada",
                            "role": "assistant",
                        }
                    )
                ]
            )
        )

        gateway = ApprovalGateway(llm_client=mock_openai_client, repository=mock_repository)

        request = ApprovalRequest(
            id="REQ-003",
            type=ApprovalType.ARCHITECTURE,
            title="Complex Decision",
            description="Decisão complexa",
            requested_by="architect@example.com",
        )

        decision = await gateway.evaluate_request(request)

        assert decision.status == ApprovalStatus.PENDING
        assert decision.approved_by is None

    async def test_critical_requires_human(self, mock_openai_client, mock_repository):
        """Testa que itens críticos sempre requerem humano."""
        gateway = ApprovalGateway(llm_client=mock_openai_client, repository=mock_repository)

        request = ApprovalRequest(
            id="REQ-004",
            type=ApprovalType.ARCHITECTURE,
            title="Critical System",
            description="Mudança crítica",
            requested_by="architect@example.com",
            context={"is_critical": True, "complexity": 3},
        )

        decision = await gateway.evaluate_request(request)

        assert decision.status == ApprovalStatus.PENDING
        assert "human" in decision.reasoning.lower()

    async def test_high_complexity_requires_human(self, mock_openai_client, mock_repository):
        """Testa que alta complexidade requer humano."""
        gateway = ApprovalGateway(llm_client=mock_openai_client, repository=mock_repository)

        request = ApprovalRequest(
            id="REQ-005",
            type=ApprovalType.ARCHITECTURE,
            title="Complex Architecture",
            description="Arquitetura muito complexa",
            requested_by="architect@example.com",
            context={"complexity": 10, "is_critical": False},
        )

        decision = await gateway.evaluate_request(request)

        assert decision.status == ApprovalStatus.PENDING

    async def test_evaluate_with_llm_error(self, mock_openai_client, mock_repository):
        """Testa fallback quando LLM falha."""
        mock_openai_client.generate = AsyncMock(side_effect=Exception("API Error"))

        gateway = ApprovalGateway(llm_client=mock_openai_client, repository=mock_repository)

        request = ApprovalRequest(
            id="REQ-006",
            type=ApprovalType.REQUIREMENT,
            title="Test",
            description="Test",
            requested_by="user@example.com",
        )

        decision = await gateway.evaluate_request(request)

        # Deve retornar média (requer humano) em caso de erro
        assert decision.status == ApprovalStatus.PENDING
        assert "Erro" in decision.reasoning

    async def test_custom_policy(self, mock_openai_client, mock_repository):
        """Testa uso de política customizada."""
        mock_openai_client.generate = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message={
                            "content": "AVALIACAO: 85\nRACIOCINIO: Boa solicitação",
                            "role": "assistant",
                        }
                    )
                ]
            )
        )

        gateway = ApprovalGateway(llm_client=mock_openai_client, repository=mock_repository)

        # Política com threshold mais alto
        strict_policy = ApprovalPolicy(
            id="strict",
            name="Política Rigorosa",
            description="Test",
            auto_approve_threshold=0.95,  # Mais alto
        )

        request = ApprovalRequest(
            id="REQ-007",
            type=ApprovalType.REQUIREMENT,
            title="Test",
            description="Test",
            requested_by="user@example.com",
        )

        # 85% não atinge 95%, então requer humano
        decision = await gateway.evaluate_request(request, policy=strict_policy)

        assert decision.status == ApprovalStatus.PENDING

    async def test_get_metrics(self, mock_openai_client, mock_repository):
        """Testa obtenção de métricas."""
        gateway = ApprovalGateway(llm_client=mock_openai_client, repository=mock_repository)

        metrics = await gateway.get_metrics()

        assert metrics.total_requests == 0
        assert metrics.pending_requests == 0

    async def test_expire_pending(self, mock_openai_client, mock_repository):
        """Testa expiração de pendentes."""
        gateway = ApprovalGateway(llm_client=mock_openai_client, repository=mock_repository)

        expired = await gateway.expire_pending_requests(24)

        assert expired == 0


class TestApprovalGatewaySync:
    """Testes síncronos para ApprovalGateway."""

    def test_extract_confidence(self, mock_openai_client):
        """Testa extração de confiança da resposta."""
        gateway = ApprovalGateway(llm_client=mock_openai_client)

        response = "AVALIACAO: 75\nRACIOCINIO: Análise detalhada..."
        confidence = gateway._extract_confidence(response)

        assert confidence == 0.75

    def test_extract_confidence_malformed(self, mock_openai_client):
        """Testa extração com resposta malformada."""
        gateway = ApprovalGateway(llm_client=mock_openai_client)

        # Sem número
        confidence = gateway._extract_confidence("Resposta sem número")
        assert confidence == 0.5  # Valor padrão

    def test_extract_reasoning(self, mock_openai_client):
        """Testa extração de raciocínio."""
        gateway = ApprovalGateway(llm_client=mock_openai_client)

        response = "AVALIACAO: 80\nRACIOCINIO: Solicitação bem elaborada com objetivos claros."
        reasoning = gateway._extract_reasoning(response)

        assert "Solicitação bem elaborada" in reasoning

    def test_build_evaluation_prompt(self, mock_openai_client):
        """Testa construção de prompt de avaliação."""
        gateway = ApprovalGateway(llm_client=mock_openai_client)

        request = ApprovalRequest(
            id="REQ-001",
            type=ApprovalType.REQUIREMENT,
            title="Login",
            description="Funcionalidade de login",
            requested_by="user@example.com",
            context={"priority": "high"},
        )

        prompt = gateway._build_evaluation_prompt(request)

        assert "requirement" in prompt
        assert "Login" in prompt
        assert "high" in prompt
        assert "AVALIACAO:" in prompt
        assert "RACIOCINIO:" in prompt
