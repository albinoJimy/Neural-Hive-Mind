"""Tests para roteamento por Journey no Decision Consumer (Fase 3 / Task 4.3).

O consumer passa a rotear por ``cognitive_plan.journey`` (decidida no STE) em
vez de re-derivar o ``workflow_type``:

    - J3_BUILD       -> FluxoGWorkflow (geração / fluxo G)
    - J2_ORCHESTRATE -> OrchestrationWorkflow
    - J4_MIGRATE     -> OrchestrationWorkflow (cutover é sub-fluxo da orquestração)
    - J1_PLAN_ONLY   -> sem execução (plan-only)

COMPATIBILIDADE: planos sem journey ou journey=UNKNOWN (planos antigos) fazem
fallback ao comportamento atual (workflow_type).
"""

from unittest.mock import patch

from src.consumers.decision_consumer import (
    _get_journey_from_plan,
    _is_plan_only,
    _select_workflow_class_by_journey,
)


class TestJourneyExtraction:
    """Extração da journey do plano (defensiva, case-insensitive)."""

    def test_get_journey_present(self):
        plan = {"plan_id": "p1", "journey": "J3_BUILD"}
        assert _get_journey_from_plan(plan) == "J3_BUILD"

    def test_get_journey_absent_returns_unknown(self):
        """Plano antigo sem journey -> UNKNOWN (aciona fallback)."""
        plan = {"plan_id": "p1"}
        assert _get_journey_from_plan(plan) == "UNKNOWN"

    def test_get_journey_empty_returns_unknown(self):
        """journey vazia (default do modelo) -> UNKNOWN."""
        plan = {"plan_id": "p1", "journey": ""}
        assert _get_journey_from_plan(plan) == "UNKNOWN"

    def test_get_journey_case_insensitive(self):
        plan = {"plan_id": "p1", "journey": "j3_build"}
        assert _get_journey_from_plan(plan) == "J3_BUILD"


class TestPlanOnlyDetection:
    """J1_PLAN_ONLY significa sem execução a jusante."""

    def test_j1_is_plan_only(self):
        assert _is_plan_only("J1_PLAN_ONLY") is True

    def test_others_are_not_plan_only(self):
        for j in ("J2_ORCHESTRATE", "J3_BUILD", "J4_MIGRATE", "UNKNOWN"):
            assert _is_plan_only(j) is False


class TestWorkflowSelectionByJourney:
    """Seleção da classe de workflow por journey."""

    @patch("src.consumers.decision_consumer.OrchestrationWorkflow")
    @patch("src.consumers.decision_consumer.FluxoGWorkflow")
    def test_j3_build_routes_to_fluxo_g(self, mock_fluxo_g, mock_orchestration):
        assert _select_workflow_class_by_journey("J3_BUILD") == mock_fluxo_g
        mock_orchestration.assert_not_called()

    @patch("src.consumers.decision_consumer.OrchestrationWorkflow")
    @patch("src.consumers.decision_consumer.FluxoGWorkflow")
    def test_j2_orchestrate_routes_to_orchestration(self, mock_fluxo_g, mock_orchestration):
        assert _select_workflow_class_by_journey("J2_ORCHESTRATE") == mock_orchestration
        mock_fluxo_g.assert_not_called()

    @patch("src.consumers.decision_consumer.OrchestrationWorkflow")
    @patch("src.consumers.decision_consumer.FluxoGWorkflow")
    def test_j4_migrate_routes_to_orchestration(self, mock_fluxo_g, mock_orchestration):
        assert _select_workflow_class_by_journey("J4_MIGRATE") == mock_orchestration
        mock_fluxo_g.assert_not_called()

    def test_unknown_journey_returns_none(self):
        """UNKNOWN -> None: sinaliza ao chamador para fazer fallback workflow_type."""
        assert _select_workflow_class_by_journey("UNKNOWN") is None

    def test_plan_only_returns_none(self):
        """J1 não tem classe de workflow de execução (plan-only)."""
        assert _select_workflow_class_by_journey("J1_PLAN_ONLY") is None


class TestRoutingFallbackCompat:
    """Planos antigos (sem journey) continuam a rotear por workflow_type."""

    @patch("src.consumers.decision_consumer.OrchestrationWorkflow")
    @patch("src.consumers.decision_consumer.FluxoGWorkflow")
    def test_journey_takes_precedence_over_workflow_type(self, mock_fluxo_g, mock_orchestration):
        """journey=J3_BUILD roteia para fluxo_g mesmo com workflow_type=orchestration."""
        plan = {"journey": "J3_BUILD", "workflow_type": "orchestration"}
        journey = _get_journey_from_plan(plan)
        wf = _select_workflow_class_by_journey(journey)
        assert wf == mock_fluxo_g

    @patch("src.consumers.decision_consumer.OrchestrationWorkflow")
    @patch("src.consumers.decision_consumer.FluxoGWorkflow")
    def test_unknown_journey_falls_back_to_workflow_type(self, mock_fluxo_g, mock_orchestration):
        """journey ausente -> None -> chamador usa workflow_type (generation->fluxo_g)."""
        from src.consumers.decision_consumer import _select_workflow_class

        plan = {"workflow_type": "generation"}  # sem journey
        journey = _get_journey_from_plan(plan)
        wf = _select_workflow_class_by_journey(journey)
        assert wf is None  # aciona fallback
        # Fallback ao comportamento legado:
        assert _select_workflow_class("generation") == mock_fluxo_g
