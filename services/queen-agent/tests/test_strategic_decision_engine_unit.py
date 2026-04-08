"""
Testes unitários para StrategicDecisionEngine.

Cobre:
- process_consolidated_decision: Processamento de decisões consolidadas
- process_telemetry_event: Processamento de eventos de telemetria
- process_critical_incident: Processamento de incidentes críticos
- make_strategic_decision: Método principal de decisão
- _aggregate_context: Agregação de contexto
- _perform_analysis: Execução de análise
- _determine_action: Determinação de ação
- _calculate_confidence: Cálculo de confiança
- _assess_risk: Avaliação de risco
- _validate_guardrails: Validação de guardrails
- execute_decision_action: Execução de ações
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

# Configure path
import sys
from pathlib import Path
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from src.services.strategic_decision_engine import StrategicDecisionEngine
from src.models import (
    DecisionType,
    DecisionAction,
    DecisionContext,
    DecisionAnalysis,
    TriggeredBy,
    RiskAssessment,
    StrategicDecision,
)


@pytest.fixture
def mock_clients():
    """Mock de todos os clientes."""
    return {
        "mongodb": AsyncMock(),
        "redis": AsyncMock(),
        "neo4j": AsyncMock(),
        "prometheus": AsyncMock(),
        "pheromone": AsyncMock(),
        "replanning": AsyncMock(),
        "opa": AsyncMock(),
        "orchestrator": AsyncMock(),
    }


@pytest.fixture
def mock_settings():
    """Mock das settings."""
    settings = MagicMock()
    settings.OPA_FAIL_OPEN = False
    return settings


@pytest.fixture
def engine(mock_clients, mock_settings):
    """Instância do engine para testes."""
    engine = StrategicDecisionEngine(
        mongodb_client=mock_clients["mongodb"],
        redis_client=mock_clients["redis"],
        neo4j_client=mock_clients["neo4j"],
        prometheus_client=mock_clients["prometheus"],
        pheromone_client=mock_clients["pheromone"],
        replanning_coordinator=mock_clients["replanning"],
        opa_client=mock_clients["opa"],
        orchestrator_client=mock_clients["orchestrator"],
        settings=mock_settings,
    )
    return engine


class TestProcessConsolidatedDecision:
    """Testes para process_consolidated_decision."""

    @pytest.mark.asyncio
    async def test_no_action_when_low_risk(self, engine):
        """Testa que decisão de baixo risco não requer ação."""
        decision_data = {
            "decision_id": "decision-123",
            "aggregated_risk": 0.3,
            "consensus_metrics": {"divergence_score": 0.01},
            "requires_human_review": False,
            "guardrails_triggered": [],
        }

        result = await engine.process_consolidated_decision(decision_data)

        assert result is None

    @pytest.mark.asyncio
    async def test_action_when_high_risk(self, engine):
        """Testa que decisão de alto risco requer ação."""
        decision_data = {
            "decision_id": "decision-123",
            "aggregated_risk": 0.8,
            "consensus_metrics": {"divergence_score": 0.01},
            "requires_human_review": False,
            "guardrails_triggered": [],
        }

        # Mock para evitar erros
        engine._aggregate_context = AsyncMock(return_value=DecisionContext())
        engine._perform_analysis = AsyncMock(return_value=DecisionAnalysis())
        engine._determine_action = AsyncMock(
            return_value=(DecisionType.PRIORITIZATION, DecisionAction(
                action="adjust_priorities",
                target_entities=[],
                parameters={},
                rationale="test"
            ))
        )
        engine._calculate_confidence = AsyncMock(return_value=0.8)
        engine._assess_risk = AsyncMock(return_value=RiskAssessment(risk_score=0.3, risk_factors=[], mitigations=[]))
        engine._validate_guardrails = AsyncMock(return_value=["guardrail1"])
        engine._update_pheromones = AsyncMock()
        engine.mongodb_client.save_strategic_decision = AsyncMock()
        engine.neo4j_client.record_strategic_decision = AsyncMock()

        result = await engine.process_consolidated_decision(decision_data)

        assert result is not None

    @pytest.mark.asyncio
    async def test_action_when_divergence_high(self, engine):
        """Testa que alta divergência requer ação."""
        decision_data = {
            "decision_id": "decision-123",
            "aggregated_risk": 0.3,
            "consensus_metrics": {"divergence_score": 0.1},
            "requires_human_review": False,
            "guardrails_triggered": [],
        }

        engine._aggregate_context = AsyncMock(return_value=DecisionContext())
        engine._perform_analysis = AsyncMock(return_value=DecisionAnalysis())
        engine._determine_action = AsyncMock(
            return_value=(DecisionType.CONFLICT_RESOLUTION, DecisionAction(
                action="resolve_conflict",
                target_entities=[],
                parameters={},
                rationale="test"
            ))
        )
        engine._calculate_confidence = AsyncMock(return_value=0.7)
        engine._assess_risk = AsyncMock(return_value=RiskAssessment(risk_score=0.3, risk_factors=[], mitigations=[]))
        engine._validate_guardrails = AsyncMock(return_value=["guardrail1"])
        engine._update_pheromones = AsyncMock()
        engine.mongodb_client.save_strategic_decision = AsyncMock()
        engine.neo4j_client.record_strategic_decision = AsyncMock()

        result = await engine.process_consolidated_decision(decision_data)

        assert result is not None


class TestProcessTelemetryEvent:
    """Testes para process_telemetry_event."""

    @pytest.mark.asyncio
    async def test_sla_violation_triggers_action(self, engine):
        """Testa que violação de SLA dispara ação."""
        event = {
            "metric_type": "sla_violation",
            "value": 0.1,
            "source": "service-1",
        }

        engine._aggregate_context = AsyncMock(return_value=DecisionContext())
        engine._perform_analysis = AsyncMock(return_value=DecisionAnalysis())
        engine._determine_action = AsyncMock(
            return_value=(DecisionType.REPLANNING, DecisionAction(
                action="trigger_replanning",
                target_entities=[],
                parameters={},
                rationale="test"
            ))
        )
        engine._calculate_confidence = AsyncMock(return_value=0.7)
        engine._assess_risk = AsyncMock(return_value=RiskAssessment(risk_score=0.3, risk_factors=[], mitigations=[]))
        engine._validate_guardrails = AsyncMock(return_value=["guardrail1"])
        engine._update_pheromones = AsyncMock()
        engine.mongodb_client.save_strategic_decision = AsyncMock()
        engine.neo4j_client.record_strategic_decision = AsyncMock()

        result = await engine.process_telemetry_event(event)

        assert result is not None

    @pytest.mark.asyncio
    async def test_resource_saturation_triggers_action(self, engine):
        """Testa que saturação de recursos dispara ação."""
        event = {
            "metric_type": "resource_saturation",
            "value": 0.9,
            "source": "service-1",
        }

        engine._aggregate_context = AsyncMock(return_value=DecisionContext())
        engine._perform_analysis = AsyncMock(return_value=DecisionAnalysis())
        engine._determine_action = AsyncMock(
            return_value=(DecisionType.RESOURCE_REALLOCATION, DecisionAction(
                action="reallocate_resources",
                target_entities=[],
                parameters={},
                rationale="test"
            ))
        )
        engine._calculate_confidence = AsyncMock(return_value=0.7)
        engine._assess_risk = AsyncMock(return_value=RiskAssessment(risk_score=0.3, risk_factors=[], mitigations=[]))
        engine._validate_guardrails = AsyncMock(return_value=["guardrail1"])
        engine._update_pheromones = AsyncMock()
        engine.mongodb_client.save_strategic_decision = AsyncMock()
        engine.neo4j_client.record_strategic_decision = AsyncMock()

        result = await engine.process_telemetry_event(event)

        assert result is not None

    @pytest.mark.asyncio
    async def test_low_value_no_action(self, engine):
        """Testa que valores baixos não disparam ação."""
        event = {
            "metric_type": "sla_violation",
            "value": 0.01,
            "source": "service-1",
        }

        result = await engine.process_telemetry_event(event)

        assert result is None


class TestProcessCriticalIncident:
    """Testes para process_critical_incident."""

    @pytest.mark.asyncio
    async def test_critical_incident_triggers_action(self, engine):
        """Testa que incidente CRITICAL dispara ação."""
        incident = {
            "incident_id": "incident-123",
            "severity": "CRITICAL",
            "incident_type": "security_threat",
        }

        engine._aggregate_context = AsyncMock(return_value=DecisionContext())
        engine._perform_analysis = AsyncMock(return_value=DecisionAnalysis())
        engine._determine_action = AsyncMock(
            return_value=(DecisionType.QOS_ADJUSTMENT, DecisionAction(
                action="pause_execution",
                target_entities=[],
                parameters={},
                rationale="test"
            ))
        )
        engine._calculate_confidence = AsyncMock(return_value=0.7)
        engine._assess_risk = AsyncMock(return_value=RiskAssessment(risk_score=0.3, risk_factors=[], mitigations=[]))
        engine._validate_guardrails = AsyncMock(return_value=["guardrail1"])
        engine._update_pheromones = AsyncMock()
        engine.mongodb_client.save_strategic_decision = AsyncMock()
        engine.neo4j_client.record_strategic_decision = AsyncMock()

        result = await engine.process_critical_incident(incident)

        assert result is not None

    @pytest.mark.asyncio
    async def test_high_incident_triggers_action(self, engine):
        """Testa que incidente HIGH dispara ação."""
        incident = {
            "incident_id": "incident-123",
            "severity": "HIGH",
        }

        engine._aggregate_context = AsyncMock(return_value=DecisionContext())
        engine._perform_analysis = AsyncMock(return_value=DecisionAnalysis())
        engine._determine_action = AsyncMock(
            return_value=(DecisionType.PRIORITIZATION, DecisionAction(
                action="adjust_priorities",
                target_entities=[],
                parameters={},
                rationale="test"
            ))
        )
        engine._calculate_confidence = AsyncMock(return_value=0.7)
        engine._assess_risk = AsyncMock(return_value=RiskAssessment(risk_score=0.3, risk_factors=[], mitigations=[]))
        engine._validate_guardrails = AsyncMock(return_value=["guardrail1"])
        engine._update_pheromones = AsyncMock()
        engine.mongodb_client.save_strategic_decision = AsyncMock()
        engine.neo4j_client.record_strategic_decision = AsyncMock()

        result = await engine.process_critical_incident(incident)

        assert result is not None

    @pytest.mark.asyncio
    async def test_low_severity_no_action(self, engine):
        """Testa que incidente de baixa severidade não dispara ação."""
        incident = {
            "incident_id": "incident-123",
            "severity": "MEDIUM",
        }

        result = await engine.process_critical_incident(incident)

        assert result is None


class TestDetermineAction:
    """Testes para _determine_action."""

    @pytest.mark.asyncio
    async def test_sla_violation_triggers_replanning(self, engine):
        """Testa que violação de SLA dispara replanejamento."""
        trigger = {"event_type": "sla_violation", "source_id": "plan-123"}
        context = DecisionContext(active_plans=["plan-123"])
        analysis = DecisionAnalysis()

        decision_type, action = await engine._determine_action(trigger, context, analysis)

        assert decision_type == DecisionType.REPLANNING
        assert action.action == "trigger_replanning"
        assert "sla_violation" in action.parameters["reason"]

    @pytest.mark.asyncio
    async def test_resource_saturation_triggers_reallocation(self, engine):
        """Testa que saturação dispara realocação."""
        trigger = {"event_type": "resource_saturation", "source_id": "plan-123"}
        context = DecisionContext(active_plans=["plan-123"])
        analysis = DecisionAnalysis()

        decision_type, action = await engine._determine_action(trigger, context, analysis)

        assert decision_type == DecisionType.RESOURCE_REALLOCATION
        assert action.action == "reallocate_resources"
        assert action.parameters.get("increase_resources") is True

    @pytest.mark.asyncio
    async def test_security_threat_triggers_pause(self, engine):
        """Testa que ameaça de segurança dispara pausa."""
        trigger = {
            "event_type": "critical_incident",
            "source_id": "plan-123",
            "incident_data": {"incident_type": "security_threat"},
        }
        context = DecisionContext(active_plans=["plan-123"])
        analysis = DecisionAnalysis()

        decision_type, action = await engine._determine_action(trigger, context, analysis)

        assert decision_type == DecisionType.QOS_ADJUSTMENT
        assert action.action == "pause_execution"
        assert "security_threat" in action.parameters["reason"]

    @pytest.mark.asyncio
    async def test_divergence_triggers_conflict_resolution(self, engine):
        """Testa que divergência dispara resolução de conflito."""
        trigger = {
            "event_type": "consolidated_decision",
            "source_id": "decision-123",
            "decision_data": {
                "consensus_metrics": {"divergence_score": 0.1}
            },
        }
        context = DecisionContext(active_plans=["plan-123"])
        analysis = DecisionAnalysis()

        decision_type, action = await engine._determine_action(trigger, context, analysis)

        assert decision_type == DecisionType.CONFLICT_RESOLUTION
        assert action.action == "resolve_conflict"
        assert "divergence" in action.parameters["rationale"]

    @pytest.mark.asyncio
    async def test_default_prioritization(self, engine):
        """Testa ação padrão de priorização."""
        trigger = {"event_type": "unknown", "source_id": "plan-123"}
        context = DecisionContext(active_plans=["plan-123"])
        analysis = DecisionAnalysis()

        decision_type, action = await engine._determine_action(trigger, context, analysis)

        assert decision_type == DecisionType.PRIORITIZATION
        assert action.action == "adjust_priorities"


class TestCalculateConfidence:
    """Testes para _calculate_confidence."""

    @pytest.mark.asyncio
    async def test_confidence_with_full_context(self, engine):
        """Testa cálculo com contexto completo."""
        context = DecisionContext(
            active_plans=["plan-1", "plan-2"],
            critical_incidents=["incident-1"],
            resource_saturation=0.5,
        )
        analysis = DecisionAnalysis(pheromone_signals={"plan-1": 0.8, "plan-2": 0.6})

        engine._get_historical_success_rate = AsyncMock(return_value=0.8)

        confidence = await engine._calculate_confidence(context, analysis)

        assert 0.0 <= confidence <= 1.0
        assert confidence > 0.5  # Deve ser alto com sinais positivos

    @pytest.mark.asyncio
    async def test_confidence_with_negative_pheromones(self, engine):
        """Testa cálculo com feromônios negativos."""
        context = DecisionContext(
            active_plans=["plan-1"],
            resource_saturation=0.3,
        )
        analysis = DecisionAnalysis(pheromone_signals={"plan-1": -0.8})

        engine._get_historical_success_rate = AsyncMock(return_value=0.7)

        confidence = await engine._calculate_confidence(context, analysis)

        assert 0.0 <= confidence <= 1.0

    @pytest.mark.asyncio
    async def test_confidence_with_empty_pheromones(self, engine):
        """Testa cálculo sem sinais de feromônio."""
        context = DecisionContext(active_plans=[], resource_saturation=0.0)
        analysis = DecisionAnalysis(pheromone_signals={})

        engine._get_historical_success_rate = AsyncMock(return_value=0.75)

        confidence = await engine._calculate_confidence(context, analysis)

        # Sem feromônios, deve usar 0.5 default
        assert confidence > 0.0


class TestAssessRisk:
    """Testes para _assess_risk."""

    @pytest.mark.asyncio
    async def test_high_resource_saturation_increases_risk(self, engine):
        """Testa que alta saturação aumenta risco."""
        trigger = {}
        context = DecisionContext(resource_saturation=0.9)
        analysis = DecisionAnalysis(pheromone_signals={})

        risk = await engine._assess_risk(trigger, context, analysis)

        assert risk.risk_score >= 0.3
        assert "high_resource_saturation" in risk.risk_factors

    @pytest.mark.asyncio
    async def test_critical_incidents_increase_risk(self, engine):
        """Testa que incidentes críticos aumentam risco."""
        trigger = {}
        context = DecisionContext(
            critical_incidents=["inc-1", "inc-2"],
            resource_saturation=0.3,
        )
        analysis = DecisionAnalysis(pheromone_signals={})

        risk = await engine._assess_risk(trigger, context, analysis)

        assert risk.risk_score >= 0.4
        assert "critical_incidents_active" in risk.risk_factors

    @pytest.mark.asyncio
    async def test_sla_violations_increase_risk(self, engine):
        """Testa que violações de SLA aumentam risco."""
        trigger = {}
        context = DecisionContext(
            sla_violations=["service-1", "service-2"],
            resource_saturation=0.3,
        )
        analysis = DecisionAnalysis(pheromone_signals={})

        risk = await engine._assess_risk(trigger, context, analysis)

        assert "sla_violations" in risk.risk_factors

    @pytest.mark.asyncio
    async def test_negative_pheromones_increase_risk(self, engine):
        """Testa que feromônios negativos aumentam risco."""
        trigger = {}
        context = DecisionContext(resource_saturation=0.3)
        analysis = DecisionAnalysis(pheromone_signals={"plan-1": -0.8})

        risk = await engine._assess_risk(trigger, context, analysis)

        assert "negative_pheromone_trails" in risk.risk_factors

    @pytest.mark.asyncio
    async def test_high_risk_triggers_mitigations(self, engine):
        """Testa que risco alto adiciona mitigações."""
        trigger = {}
        context = DecisionContext(
            critical_incidents=["inc-1", "inc-2", "inc-3"],
            resource_saturation=0.9,
        )
        analysis = DecisionAnalysis(pheromone_signals={"plan-1": -0.9})

        risk = await engine._assess_risk(trigger, context, analysis)

        assert risk.risk_score > 0.5
        assert len(risk.mitigations) > 0
        assert "require_human_approval" in risk.mitigations or "increase_monitoring" in risk.mitigations


class TestValidateGuardrails:
    """Testes para _validate_guardrails."""

    @pytest.mark.asyncio
    async def test_opa_allows_decision(self, engine):
        """Testa validação quando OPA permite."""
        engine.opa_client.is_connected = MagicMock(return_value=True)
        engine.opa_client.evaluate_policy = AsyncMock(return_value={
            "allow": True,
            "guardrails_validated": ["ethical_guardrail_1", "safety_guardrail_1"],
            "violations": [],
            "warnings": [],
        })

        result = await engine._validate_guardrails(
            decision_type=DecisionType.PRIORITIZATION,
            action=DecisionAction(
                action="adjust_priorities",
                target_entities=[],
                parameters={},
                rationale="test"
            ),
            risk_assessment=RiskAssessment(risk_score=0.3, risk_factors=[], mitigations=[]),
            confidence_score=0.8,
            context=DecisionContext(),
            analysis=DecisionAnalysis(),
            reasoning_summary="test",
        )

        assert len(result) > 0
        assert "ethical_guardrail_1" in result

    @pytest.mark.asyncio
    async def test_opa_denies_decision(self, engine):
        """Testa validação quando OPA nega."""
        engine.opa_client.is_connected = MagicMock(return_value=True)
        engine.opa_client.evaluate_policy = AsyncMock(return_value={
            "allow": False,
            "guardrails_validated": [],
            "violations": [{"rule": "safety_violation"}],
            "warnings": [],
        })

        result = await engine._validate_guardrails(
            decision_type=DecisionType.PRIORITIZATION,
            action=DecisionAction(
                action="adjust_priorities",
                target_entities=[],
                parameters={},
                rationale="test"
            ),
            risk_assessment=RiskAssessment(risk_score=0.3, risk_factors=[], mitigations=[]),
            confidence_score=0.8,
            context=DecisionContext(),
            analysis=DecisionAnalysis(),
            reasoning_summary="test",
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_opa_unavailable_fail_closed(self, engine, mock_settings):
        """Testa fail-closed quando OPA indisponível."""
        mock_settings.OPA_FAIL_OPEN = False
        engine.opa_client.is_connected = MagicMock(return_value=False)

        result = await engine._validate_guardrails(
            decision_type=DecisionType.PRIORITIZATION,
            action=DecisionAction(
                action="adjust_priorities",
                target_entities=[],
                parameters={},
                rationale="test"
            ),
            risk_assessment=RiskAssessment(risk_score=0.3, risk_factors=[], mitigations=[]),
            confidence_score=0.8,
            context=DecisionContext(),
            analysis=DecisionAnalysis(),
            reasoning_summary="test",
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_opa_unavailable_fail_open(self, engine, mock_settings):
        """Testa fail-open quando OPA indisponível."""
        mock_settings.OPA_FAIL_OPEN = True
        engine.opa_client.is_connected = MagicMock(return_value=False)

        result = await engine._validate_guardrails(
            decision_type=DecisionType.PRIORITIZATION,
            action=DecisionAction(
                action="adjust_priorities",
                target_entities=[],
                parameters={},
                rationale="test"
            ),
            risk_assessment=RiskAssessment(risk_score=0.3, risk_factors=[], mitigations=[]),
            confidence_score=0.8,
            context=DecisionContext(),
            analysis=DecisionAnalysis(),
            reasoning_summary="test",
        )

        # Fail-open deve retornar validação básica
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_basic_guardrail_validation(self, engine):
        """Testa validação básica de guardrails."""
        result = engine._basic_guardrail_validation(
            decision_type=DecisionType.PRIORITIZATION,
            risk_assessment=RiskAssessment(risk_score=0.5, risk_factors=[], mitigations=[])
        )

        assert "risk_threshold_acceptable" in result
        assert "no_guardrail_violations" in result

    @pytest.mark.asyncio
    async def test_basic_guardrail_validation_high_risk(self, engine):
        """Testa que risco alto falha validação básica."""
        result = engine._basic_guardrail_validation(
            decision_type=DecisionType.PRIORITIZATION,
            risk_assessment=RiskAssessment(risk_score=0.95, risk_factors=[], mitigations=[])
        )

        # Risco alto não deve ter risk_threshold_acceptable
        assert "risk_threshold_acceptable" not in result


class TestExecuteDecisionAction:
    """Testes para execute_decision_action."""

    @pytest.mark.asyncio
    async def test_trigger_replanning_via_grpc(self, engine):
        """Testa replanejamento via gRPC."""
        decision = StrategicDecision(
            decision_type=DecisionType.REPLANNING,
            triggered_by=TriggeredBy(
                event_type="sla_violation",
                source_id="plan-123",
                timestamp=int(datetime.now().timestamp() * 1000),
            ),
            context=DecisionContext(active_plans=["plan-123"]),
            analysis=DecisionAnalysis(),
            decision=DecisionAction(
                action="trigger_replanning",
                target_entities=["plan-123"],
                parameters={"reason": "sla_violation"},
                rationale="test",
            ),
            confidence_score=0.8,
            risk_assessment=RiskAssessment(risk_score=0.3, risk_factors=[], mitigations=[]),
            guardrails_validated=["guardrail1"],
            reasoning_summary="test",
            expires_at=int((datetime.now() + timedelta(hours=24)).timestamp() * 1000),
        )

        engine.orchestrator_client.trigger_replanning = AsyncMock(return_value="replanning-123")

        result = await engine.execute_decision_action(decision)

        assert result is True
        engine.orchestrator_client.trigger_replanning.assert_called_once()

    @pytest.mark.asyncio
    async def test_adjust_priorities_via_grpc(self, engine):
        """Testa ajuste de prioridade via gRPC."""
        decision = StrategicDecision(
            decision_type=DecisionType.PRIORITIZATION,
            triggered_by=TriggeredBy(
                event_type="manual",
                source_id="plan-123",
                timestamp=int(datetime.now().timestamp() * 1000),
            ),
            context=DecisionContext(active_plans=["plan-123"]),
            analysis=DecisionAnalysis(),
            decision=DecisionAction(
                action="adjust_priorities",
                target_entities=["plan-123"],
                parameters={"priority": 9},
                rationale="test",
            ),
            confidence_score=0.8,
            risk_assessment=RiskAssessment(risk_score=0.3, risk_factors=[], mitigations=[]),
            guardrails_validated=["guardrail1"],
            reasoning_summary="test",
            expires_at=int((datetime.now() + timedelta(hours=24)).timestamp() * 1000),
        )

        engine.orchestrator_client.adjust_priorities = AsyncMock(return_value=True)

        result = await engine.execute_decision_action(decision)

        assert result is True

    @pytest.mark.asyncio
    async def test_pause_workflow_via_grpc(self, engine):
        """Testa pausa de workflow via gRPC."""
        decision = StrategicDecision(
            decision_type=DecisionType.QOS_ADJUSTMENT,
            triggered_by=TriggeredBy(
                event_type="security_threat",
                source_id="plan-123",
                timestamp=int(datetime.now().timestamp() * 1000),
            ),
            context=DecisionContext(active_plans=["plan-123"]),
            analysis=DecisionAnalysis(),
            decision=DecisionAction(
                action="pause_execution",
                target_entities=["plan-123"],
                parameters={"reason": "security_threat"},
                rationale="test",
            ),
            confidence_score=0.8,
            risk_assessment=RiskAssessment(risk_score=0.3, risk_factors=[], mitigations=[]),
            guardrails_validated=["guardrail1"],
            reasoning_summary="test",
            expires_at=int((datetime.now() + timedelta(hours=24)).timestamp() * 1000),
        )

        engine.orchestrator_client.pause_workflow = AsyncMock(return_value=True)

        result = await engine.execute_decision_action(decision)

        assert result is True

    @pytest.mark.asyncio
    async def test_resume_workflow_via_grpc(self, engine):
        """Testa retomada de workflow via gRPC."""
        decision = StrategicDecision(
            decision_type=DecisionType.QOS_ADJUSTMENT,
            triggered_by=TriggeredBy(
                event_type="manual",
                source_id="plan-123",
                timestamp=int(datetime.now().timestamp() * 1000),
            ),
            context=DecisionContext(active_plans=["plan-123"]),
            analysis=DecisionAnalysis(),
            decision=DecisionAction(
                action="resume_execution",
                target_entities=["plan-123"],
                parameters={},
                rationale="test",
            ),
            confidence_score=0.8,
            risk_assessment=RiskAssessment(risk_score=0.3, risk_factors=[], mitigations=[]),
            guardrails_validated=["guardrail1"],
            reasoning_summary="test",
            expires_at=int((datetime.now() + timedelta(hours=24)).timestamp() * 1000),
        )

        engine.orchestrator_client.resume_workflow = AsyncMock(return_value=True)

        result = await engine.execute_decision_action(decision)

        assert result is True

    @pytest.mark.asyncio
    async def test_reallocate_resources_via_grpc(self, engine):
        """Testa realocação de recursos via gRPC."""
        decision = StrategicDecision(
            decision_type=DecisionType.RESOURCE_REALLOCATION,
            triggered_by=TriggeredBy(
                event_type="resource_saturation",
                source_id="plan-123",
                timestamp=int(datetime.now().timestamp() * 1000),
            ),
            context=DecisionContext(active_plans=["plan-123"]),
            analysis=DecisionAnalysis(),
            decision=DecisionAction(
                action="reallocate_resources",
                target_entities=["plan-123"],
                parameters={"cpu_millicores": 4000},
                rationale="test",
            ),
            confidence_score=0.8,
            risk_assessment=RiskAssessment(risk_score=0.3, risk_factors=[], mitigations=[]),
            guardrails_validated=["guardrail1"],
            reasoning_summary="test",
            expires_at=int((datetime.now() + timedelta(hours=24)).timestamp() * 1000),
        )

        engine.orchestrator_client.rebalance_resources = AsyncMock(
            return_value={"success": True}
        )

        result = await engine.execute_decision_action(decision)

        assert result is True

    @pytest.mark.asyncio
    async def test_unknown_action_returns_false(self, engine):
        """Testa que ação desconhecida retorna False."""
        decision = StrategicDecision(
            decision_type=DecisionType.PRIORITIZATION,
            triggered_by=TriggeredBy(
                event_type="test",
                source_id="plan-123",
                timestamp=int(datetime.now().timestamp() * 1000),
            ),
            context=DecisionContext(active_plans=["plan-123"]),
            analysis=DecisionAnalysis(),
            decision=DecisionAction(
                action="unknown_action",
                target_entities=[],
                parameters={},
                rationale="test",
            ),
            confidence_score=0.8,
            risk_assessment=RiskAssessment(risk_score=0.3, risk_factors=[], mitigations=[]),
            guardrails_validated=["guardrail1"],
            reasoning_summary="test",
            expires_at=int((datetime.now() + timedelta(hours=24)).timestamp() * 1000),
        )

        result = await engine.execute_decision_action(decision)

        assert result is False

    @pytest.mark.asyncio
    async def test_action_fallback_without_orchestrator(self, engine):
        """Testa fallback para ReplanningCoordinator sem orchestrator."""
        decision = StrategicDecision(
            decision_type=DecisionType.REPLANNING,
            triggered_by=TriggeredBy(
                event_type="test",
                source_id="plan-123",
                timestamp=int(datetime.now().timestamp() * 1000),
            ),
            context=DecisionContext(active_plans=["plan-123"]),
            analysis=DecisionAnalysis(),
            decision=DecisionAction(
                action="trigger_replanning",
                target_entities=["plan-123"],
                parameters={"reason": "test"},
                rationale="test",
            ),
            confidence_score=0.8,
            risk_assessment=RiskAssessment(risk_score=0.3, risk_factors=[], mitigations=[]),
            guardrails_validated=["guardrail1"],
            reasoning_summary="test",
            expires_at=int((datetime.now() + timedelta(hours=24)).timestamp() * 1000),
        )

        engine.orchestrator_client = None
        engine.replanning_coordinator.trigger_replanning = AsyncMock(return_value=True)

        result = await engine.execute_decision_action(decision)

        assert result is True
        engine.replanning_coordinator.trigger_replanning.assert_called()
