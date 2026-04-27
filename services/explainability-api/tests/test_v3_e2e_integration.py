"""
Testes de Integração E2E para Explainability API v3.

Testa o fluxo completo v3:
1. Decisão com votos hierárquicos (expert, senior, trainee)
2. Geração de hierarchical breakdown
3. Geração de individual contributions
4. Cálculo de consensus strength
5. Geração de counterfactuals
6. Análise temporal
7. Validação de integração de todos os componentes

TDD: Testes escritos antes da implementação (Explainability API v3 Task 8).
"""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# Multiplicadores de senioridade (mesmos valores do consensus-engine)
SENIORITY_MULTIPLIERS = {
    "trainee": 0.5,
    "junior": 0.75,
    "mid_level": 1.0,
    "senior": 1.5,
    "expert": 2.0,
}


# Helper function para criar votos de teste
def create_vote(
    level: str, vote: str, confidence: float, specialist_id: str = "test"
) -> dict[str, Any]:
    """
    Cria um voto de especialista para testes.

    Args:
        level: Nível de senioridade (trainee, junior, mid_level, senior, expert)
        vote: Voto (approve, reject)
        confidence: Confiança (0.0 a 1.0)
        specialist_id: ID do especialista

    Returns:
        Dicionário representando um voto
    """
    return {
        "specialist_id": f"{specialist_id}_{level}",
        "specialist_name": f"Test {level.title()}",
        "domain": "TECHNICAL",
        "seniority_level": level,
        "seniority_multiplier": SENIORITY_MULTIPLIERS.get(level, 1.0),
        "vote": vote,
        "confidence": confidence,
        "risk": 1.0 - confidence,
    }


class TestV3E2EFullFlow:
    """Testes E2E do fluxo completo v3."""

    @pytest.fixture()
    def hierarchical_votes(self) -> list[dict[str, Any]]:
        """Votos hierárquicos completos para testes E2E."""
        return [
            create_vote("expert", "approve", 0.9, "business"),
            create_vote("senior", "approve", 0.8, "technical"),
            create_vote("mid_level", "reject", 0.7, "architecture"),
            create_vote("junior", "approve", 0.6, "security"),
            create_vote("trainee", "reject", 0.5, "behavior"),
        ]

    @pytest.fixture()
    def explainer_services(self):
        """Instancia todos os serviços v3."""
        from services.counterfactual_analyzer import CounterfactualAnalyzer
        from services.hierarchical_explainer import HierarchicalExplainer

        return {
            "hierarchical": HierarchicalExplainer(),
            "counterfactual": CounterfactualAnalyzer(),
        }

    def test_full_v3_explanation_flow_hierarchical_breakdown(
        self, hierarchical_votes, explainer_services
    ):
        """Testa geração de breakdown hierárquico no fluxo completo."""
        explainer = explainer_services["hierarchical"]

        result = explainer.explain(hierarchical_votes)

        # Validar breakdown hierárquico
        assert "hierarchical_breakdown" in result
        breakdown = result["hierarchical_breakdown"]

        # Verificar por nível
        assert "by_level" in breakdown
        by_level = breakdown["by_level"]

        # Todos os 5 níveis devem estar presentes
        assert "expert" in by_level
        assert "senior" in by_level
        assert "mid_level" in by_level
        assert "junior" in by_level
        assert "trainee" in by_level

        # Verificar contagens
        assert by_level["expert"]["count"] == 1
        assert by_level["senior"]["count"] == 1
        assert by_level["mid_level"]["count"] == 1
        assert by_level["junior"]["count"] == 1
        assert by_level["trainee"]["count"] == 1

        # Verificar multiplicadores
        assert by_level["expert"]["weight_multiplier"] == 2.0
        assert by_level["senior"]["weight_multiplier"] == 1.5
        assert by_level["mid_level"]["weight_multiplier"] == 1.0
        assert by_level["junior"]["weight_multiplier"] == 0.75
        assert by_level["trainee"]["weight_multiplier"] == 0.5

    def test_full_v3_explanation_flow_individual_contributions(
        self, hierarchical_votes, explainer_services
    ):
        """Testa geração de contribuições individuais no fluxo completo."""
        explainer = explainer_services["hierarchical"]

        result = explainer.explain(hierarchical_votes)

        # Validar contribuições individuais
        assert "individual_contributions" in result
        contributions = result["individual_contributions"]

        # Todas as 5 contribuições devem estar presentes
        assert len(contributions) == 5

        # Verificar ranking (expert deve ter rank 1 por maior multiplier + confiança)
        assert contributions[0]["rank"] == 1
        assert contributions[0]["seniority_level"] == "expert"
        assert contributions[0]["vote"] == "approve"

        # Verificar campos de cada contribuição
        for contrib in contributions:
            assert "specialist_id" in contrib
            assert "seniority_level" in contrib
            assert "multiplier" in contrib
            assert "vote" in contrib
            assert "confidence" in contrib
            assert "contribution_score" in contrib
            assert "rank" in contrib

    def test_full_v3_explanation_flow_consensus_strength(
        self, hierarchical_votes, explainer_services
    ):
        """Testa cálculo de força de consenso no fluxo completo."""
        explainer = explainer_services["hierarchical"]

        result = explainer.explain(hierarchical_votes)

        # Validar força de consenso
        assert "hierarchical_breakdown" in result
        breakdown = result["hierarchical_breakdown"]

        assert "consensus_strength" in breakdown
        consensus_strength = breakdown["consensus_strength"]

        # Consenso deve estar entre 0 e 1
        assert 0.0 <= consensus_strength <= 1.0

        # Com 3 approve e 2 reject (em diferentes níveis),
        # expectativa é consenso parcial (~0.6)
        assert 0.5 <= consensus_strength <= 0.7

    def test_full_v3_explanation_flow_counterfactuals(self, hierarchical_votes, explainer_services):
        """Testa geração de counterfactuals no fluxo completo."""
        analyzer = explainer_services["counterfactual"]

        result = analyzer.generate_all_counterfactuals(hierarchical_votes)

        # Validar estrutura dos counterfactuals
        assert "scenarios" in result
        assert "sensitivity_analysis" in result

        scenarios = result["scenarios"]

        # Verificar todos os cenários
        assert "original" in scenarios
        assert "equal_weights" in scenarios
        assert "no_trainee" in scenarios
        assert "seniority_inversion" in scenarios

        # Validar campos de cada cenário
        for scenario_name, scenario_data in scenarios.items():
            assert "decision" in scenario_data
            assert "score" in scenario_data or "weighted_score" in scenario_data

    def test_full_v3_explanation_flow_counterfactual_sensitivity(
        self, hierarchical_votes, explainer_services
    ):
        """Testa análise de sensibilidade nos counterfactuals."""
        analyzer = explainer_services["counterfactual"]

        result = analyzer.generate_all_counterfactuals(hierarchical_votes)

        # Validar análise de sensibilidade
        assert "sensitivity_analysis" in result
        sensitivity = result["sensitivity_analysis"]

        assert "is_robust" in sensitivity
        assert "decision_flips" in sensitivity
        assert "flip_count" in sensitivity

        # flip_count deve ser inteiro não-negativo
        assert isinstance(sensitivity["flip_count"], int)
        assert sensitivity["flip_count"] >= 0

        # decision_flips deve ser lista
        assert isinstance(sensitivity["decision_flips"], list)

    @pytest.mark.asyncio()
    async def test_full_v3_explanation_flow_temporal_analysis(self, hierarchical_votes):
        """Testa análise temporal no fluxo completo."""
        from services.temporal_tracker import TemporalTracker

        # Criar mock MongoDB
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()

        # Mock de decisões para análise de sessão
        mock_decisions = [
            {
                "decision_id": "decision-1",
                "plan_id": "plan-123",
                "generated_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
                "final_decision": {"decision": "approve"},
            },
            {
                "decision_id": "decision-2",
                "plan_id": "plan-123",
                "generated_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                "final_decision": {"decision": "approve"},
            },
            {
                "decision_id": "decision-3",
                "plan_id": "plan-123",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "final_decision": {"decision": "reject"},
            },
        ]

        # Configurar mocks
        mock_collection.find_one = AsyncMock(return_value=mock_decisions[0])
        mock_collection.find = Mock(return_value=mock_cursor(mock_decisions))
        mock_db.explainability_ledger = mock_collection
        mock_db.seniority_history = mock_collection
        mock_client.__getitem__ = Mock(return_value=mock_db)

        # Criar tracker
        tracker = TemporalTracker(mock_client)

        # Testar análise de sessão
        session = await tracker.get_current_session("decision-3")

        # Validar resultado da sessão
        assert "session_id" in session
        assert session["session_id"] == "plan-123"
        assert "decision_count" in session
        assert session["decision_count"] == 3
        assert "timeline" in session
        assert len(session["timeline"]) == 3
        assert "duration_hours" in session
        assert session["duration_hours"] > 0

    @pytest.mark.asyncio()
    async def test_full_v3_explanation_flow_temporal_window_analysis(self, hierarchical_votes):
        """Testa análise de janela temporal."""
        from services.temporal_tracker import TemporalTracker

        # Criar mock MongoDB
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()

        # Mock de decisões para janela de 7 dias
        base_time = datetime.now(timezone.utc)
        mock_decisions = [
            {
                "decision_id": f"decision-{i}",
                "plan_id": f"plan-{i}",
                "generated_at": (base_time - timedelta(days=i)).isoformat(),
                "final_decision": {"decision": "approve" if i % 2 == 0 else "reject"},
            }
            for i in range(1, 8)  # 7 decisões em 7 dias
        ]

        # Configurar mocks
        mock_collection.find = Mock(return_value=mock_cursor(mock_decisions))
        mock_db.explainability_ledger = mock_collection
        mock_db.seniority_history = mock_collection
        mock_client.__getitem__ = Mock(return_value=mock_db)

        # Criar tracker
        tracker = TemporalTracker(mock_client)

        # Testar análise de janela
        window = await tracker.get_window_analysis(days=7)

        # Validar resultado da janela
        assert "window_days" in window
        assert window["window_days"] == 7
        assert "decision_count" in window
        assert window["decision_count"] == 7
        assert "approve_count" in window
        assert "reject_count" in window
        assert "approve_rate" in window
        assert 0.0 <= window["approve_rate"] <= 1.0
        assert "daily_breakdown" in window

    def test_full_v3_explanation_flow_integration_all_components(
        self, hierarchical_votes, explainer_services
    ):
        """Testa integração de todos os componentes v3."""
        # 1. Hierarchical Breakdown
        explainer = explainer_services["hierarchical"]
        hierarchical_result = explainer.explain(hierarchical_votes)

        assert "hierarchical_breakdown" in hierarchical_result
        assert "individual_contributions" in hierarchical_result

        # 2. Counterfactuals
        analyzer = explainer_services["counterfactual"]
        counterfactual_result = analyzer.generate_all_counterfactuals(hierarchical_votes)

        assert "scenarios" in counterfactual_result
        assert "sensitivity_analysis" in counterfactual_result

        # 3. Validar consistência entre componentes

        # Consensus strength deve ser calculável
        consensus_strength = hierarchical_result["hierarchical_breakdown"]["consensus_strength"]
        assert 0.0 <= consensus_strength <= 1.0

        # Nível dominante deve estar presente
        dominant_level = hierarchical_result["hierarchical_breakdown"]["dominant_level"]
        assert dominant_level in ["expert", "senior", "mid_level", "junior", "trainee"]

        # Decision flips devem ser detectáveis
        flip_count = counterfactual_result["sensitivity_analysis"]["flip_count"]
        assert flip_count >= 0

        # 4. Integrar todos os resultados
        integrated_result = {
            "decision_id": "test-v3-decision",
            "hierarchical_analysis": hierarchical_result,
            "counterfactual_analysis": counterfactual_result,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Validar estrutura integrada
        assert "hierarchical_analysis" in integrated_result
        assert "counterfactual_analysis" in integrated_result
        assert integrated_result["decision_id"] == "test-v3-decision"

    def test_full_v3_explanation_flow_unanimous_consensus(self, explainer_services):
        """Testa fluxo com consenso unânime."""
        unanimous_votes = [
            create_vote("expert", "approve", 0.9, "business"),
            create_vote("senior", "approve", 0.85, "technical"),
            create_vote("mid_level", "approve", 0.8, "architecture"),
        ]

        explainer = explainer_services["hierarchical"]
        result = explainer.explain(unanimous_votes)

        # Consenso unânime deve ter força 1.0
        consensus_strength = result["hierarchical_breakdown"]["consensus_strength"]
        assert consensus_strength == 1.0

        # Nível dominante deve ser expert (maior multiplicador)
        dominant_level = result["hierarchical_breakdown"]["dominant_level"]
        assert dominant_level == "expert"

    def test_full_v3_explanation_flow_divided_consensus(self, explainer_services):
        """Testa fluxo com consenso dividido."""
        divided_votes = [
            create_vote("expert", "approve", 0.9, "business"),
            create_vote("senior", "reject", 0.8, "technical"),
            create_vote("mid_level", "neutral", 0.5, "architecture"),
        ]

        explainer = explainer_services["hierarchical"]
        result = explainer.explain(divided_votes)

        # Consenso dividido deve ter força baixa
        consensus_strength = result["hierarchical_breakdown"]["consensus_strength"]
        assert 0.3 <= consensus_strength <= 0.4  # ~1/3


class TestV3E2ECounterfactualScenarios:
    """Testes E2E de cenários contrafactuais específicos."""

    @pytest.fixture()
    def explainer_services(self):
        """Instancia todos os serviços v3."""
        from services.counterfactual_analyzer import CounterfactualAnalyzer

        return {
            "counterfactual": CounterfactualAnalyzer(),
        }

    def test_counterfactual_equal_weights_scenario(self, explainer_services):
        """Testa cenário de pesos iguais."""
        votes = [
            create_vote("expert", "approve", 0.9, "business"),
            create_vote("trainee", "approve", 0.8, "technical"),
        ]

        analyzer = explainer_services["counterfactual"]
        result = analyzer.analyze_equal_weights(votes)

        assert result.scenario_name == "equal_weights"
        assert "decision" in result.to_dict()
        assert "weighted_score" in result.to_dict()

        # Sem multiplicadores, ambos devem ter mesmo peso
        breakdown = result.to_dict()["breakdown"]
        for specialist_id, data in breakdown.items():
            assert data["multiplier"] == 1.0

    def test_counterfactual_no_trainee_scenario(self, explainer_services):
        """Testa cenário sem trainees."""
        votes = [
            create_vote("expert", "approve", 0.9, "business"),
            create_vote("senior", "approve", 0.8, "technical"),
            create_vote("trainee", "reject", 0.7, "architecture"),
        ]

        analyzer = explainer_services["counterfactual"]
        result = analyzer.analyze_no_trainee(votes)

        assert result.scenario_name == "no_trainee"
        assert "decision" in result.to_dict()

        # Trainee não deve aparecer no breakdown
        breakdown = result.to_dict()["breakdown"]
        for specialist_id in breakdown.keys():
            assert "trainee" not in specialist_id

    def test_counterfactual_seniority_inversion_scenario(self, explainer_services):
        """Testa cenário de inversão de senioridade."""
        votes = [
            create_vote("expert", "approve", 0.9, "business"),
            create_vote("trainee", "approve", 0.8, "technical"),
        ]

        analyzer = explainer_services["counterfactual"]
        result = analyzer.analyze_seniority_inversion(votes)

        assert result.scenario_name == "seniority_inversion"
        assert "decision" in result.to_dict()

        # Multiplicadores devem estar invertidos
        breakdown = result.to_dict()["breakdown"]
        for specialist_id, data in breakdown.items():
            if "expert" in specialist_id:
                assert data["inverted_multiplier"] == 0.5
            elif "trainee" in specialist_id:
                assert data["inverted_multiplier"] == 2.0

    def test_counterfactual_robust_decision(self, explainer_services):
        """Testa que decisão robusta não muda com cenários."""
        # Votos com forte aprovação em todos os níveis
        robust_votes = [
            create_vote("expert", "approve", 0.95, "business"),
            create_vote("senior", "approve", 0.90, "technical"),
            create_vote("mid_level", "approve", 0.85, "architecture"),
        ]

        analyzer = explainer_services["counterfactual"]
        result = analyzer.generate_all_counterfactuals(robust_votes)

        # Decisão original deve ser approve
        original_decision = result["scenarios"]["original"]["decision"]
        assert original_decision == "approve"

        # Sensibilidade deve indicar decisão robusta
        sensitivity = result["sensitivity_analysis"]
        # Com votos tão fortes, deve ser robusto (nenhum flip)
        assert sensitivity["is_robust"] is True
        assert sensitivity["flip_count"] == 0


# Helper class para mock de cursor MongoDB


class mock_cursor:
    """Mock de cursor MongoDB para testes assíncronos."""

    def __init__(self, documents: list[dict[str, Any]]):
        self.documents = documents
        self.current_index = 0

    def sort(self, key, direction):
        """Mock de sort."""
        return self

    def __aiter__(self):
        """Retorna self para iteração assíncrona."""
        return self

    async def __anext__(self):
        """Avança para o próximo documento."""
        if self.current_index >= len(self.documents):
            raise StopAsyncIteration
        doc = self.documents[self.current_index]
        self.current_index += 1
        return doc
