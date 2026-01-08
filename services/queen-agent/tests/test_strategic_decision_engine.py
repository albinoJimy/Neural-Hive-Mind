"""
Testes para StrategicDecisionEngine - foco em execute_decision_action
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.services.strategic_decision_engine import StrategicDecisionEngine
from src.models import (
    StrategicDecision, DecisionType, DecisionContext, DecisionAnalysis,
    DecisionAction, RiskAssessment, TriggeredBy
)


@pytest.fixture
def mock_clients():
    """Mock de todos os clientes necessários"""
    return {
        'mongodb': AsyncMock(),
        'redis': AsyncMock(),
        'neo4j': AsyncMock(),
        'prometheus': AsyncMock(),
        'pheromone': AsyncMock(),
        'replanning_coordinator': AsyncMock(),
        'opa': AsyncMock()
    }


@pytest.fixture
def mock_settings():
    """Mock de configurações"""
    settings = MagicMock()
    settings.REPLANNING_COOLDOWN_SECONDS = 300
    settings.OPA_FAIL_OPEN = False
    return settings


@pytest.fixture
def decision_engine(mock_clients, mock_settings):
    """Instância do StrategicDecisionEngine com mocks"""
    return StrategicDecisionEngine(
        mongodb_client=mock_clients['mongodb'],
        redis_client=mock_clients['redis'],
        neo4j_client=mock_clients['neo4j'],
        prometheus_client=mock_clients['prometheus'],
        pheromone_client=mock_clients['pheromone'],
        replanning_coordinator=mock_clients['replanning_coordinator'],
        opa_client=mock_clients['opa'],
        settings=mock_settings
    )


@pytest.fixture
def sample_decision():
    """Decisão estratégica de exemplo"""
    return StrategicDecision(
        decision_type=DecisionType.REPLANNING,
        triggered_by=TriggeredBy(
            event_type='sla_violation',
            source_id='test-source',
            timestamp=int(datetime.now().timestamp() * 1000)
        ),
        context=DecisionContext(
            active_plans=['plan-1', 'plan-2'],
            critical_incidents=[],
            sla_violations=[],
            resource_saturation=0.5
        ),
        analysis=DecisionAnalysis(),
        decision=DecisionAction(
            action='trigger_replanning',
            target_entities=['plan-1', 'plan-2'],
            parameters={'reason': 'sla_violation'},
            rationale='Replanning necessário devido a violação de SLA'
        ),
        confidence_score=0.85,
        risk_assessment=RiskAssessment(
            risk_score=0.3,
            risk_factors=['sla_violation'],
            mitigations=['increase_monitoring']
        ),
        guardrails_validated=['risk_threshold_acceptable'],
        reasoning_summary='Decisão de replanning baseada em violação de SLA',
        expires_at=int(datetime.now().timestamp() * 1000) + 86400000
    )


@pytest.mark.asyncio
async def test_execute_decision_action_trigger_replanning(decision_engine, mock_clients, sample_decision):
    """Testa execução de ação trigger_replanning"""
    # Configurar mock para retornar sucesso
    mock_clients['replanning_coordinator'].trigger_replanning.return_value = True

    # Executar ação
    result = await decision_engine.execute_decision_action(sample_decision)

    # Verificar resultado
    assert result is True

    # Verificar que trigger_replanning foi chamado para cada entidade
    assert mock_clients['replanning_coordinator'].trigger_replanning.call_count == 2

    # Verificar parâmetros da primeira chamada
    first_call = mock_clients['replanning_coordinator'].trigger_replanning.call_args_list[0]
    assert first_call.kwargs['plan_id'] == 'plan-1'
    assert first_call.kwargs['reason'] == 'sla_violation'
    assert first_call.kwargs['decision_id'] == sample_decision.decision_id


@pytest.mark.asyncio
async def test_execute_decision_action_adjust_qos(decision_engine, mock_clients):
    """Testa execução de ação adjust_qos"""
    decision = StrategicDecision(
        decision_type=DecisionType.QOS_ADJUSTMENT,
        triggered_by=TriggeredBy(
            event_type='resource_saturation',
            source_id='test',
            timestamp=int(datetime.now().timestamp() * 1000)
        ),
        context=DecisionContext(),
        analysis=DecisionAnalysis(),
        decision=DecisionAction(
            action='adjust_qos',
            target_entities=['workflow-1'],
            parameters={'priority': 'high'},
            rationale='Ajustar QoS'
        ),
        confidence_score=0.8,
        risk_assessment=RiskAssessment(risk_score=0.2, risk_factors=[], mitigations=[]),
        guardrails_validated=[],
        reasoning_summary='',
        expires_at=int(datetime.now().timestamp() * 1000) + 86400000
    )

    mock_clients['replanning_coordinator'].adjust_qos.return_value = True

    result = await decision_engine.execute_decision_action(decision)

    assert result is True
    assert mock_clients['replanning_coordinator'].adjust_qos.call_count == 1


@pytest.mark.asyncio
async def test_execute_decision_action_pause_execution(decision_engine, mock_clients):
    """Testa execução de ação pause_execution"""
    decision = StrategicDecision(
        decision_type=DecisionType.QOS_ADJUSTMENT,
        triggered_by=TriggeredBy(
            event_type='security_threat',
            source_id='test',
            timestamp=int(datetime.now().timestamp() * 1000)
        ),
        context=DecisionContext(),
        analysis=DecisionAnalysis(),
        decision=DecisionAction(
            action='pause_execution',
            target_entities=['workflow-1', 'workflow-2'],
            parameters={'reason': 'security_threat'},
            rationale='Pausar por ameaça de segurança'
        ),
        confidence_score=0.9,
        risk_assessment=RiskAssessment(risk_score=0.8, risk_factors=[], mitigations=[]),
        guardrails_validated=[],
        reasoning_summary='',
        expires_at=int(datetime.now().timestamp() * 1000) + 86400000
    )

    mock_clients['replanning_coordinator'].pause_execution.return_value = True

    result = await decision_engine.execute_decision_action(decision)

    assert result is True
    assert mock_clients['replanning_coordinator'].pause_execution.call_count == 2


@pytest.mark.asyncio
async def test_execute_decision_action_unknown_action(decision_engine, mock_clients):
    """Testa execução de ação desconhecida"""
    decision = StrategicDecision(
        decision_type=DecisionType.PRIORITIZATION,
        triggered_by=TriggeredBy(
            event_type='test',
            source_id='test',
            timestamp=int(datetime.now().timestamp() * 1000)
        ),
        context=DecisionContext(),
        analysis=DecisionAnalysis(),
        decision=DecisionAction(
            action='unknown_action',
            target_entities=['entity-1'],
            parameters={},
            rationale='Teste'
        ),
        confidence_score=0.5,
        risk_assessment=RiskAssessment(risk_score=0.1, risk_factors=[], mitigations=[]),
        guardrails_validated=[],
        reasoning_summary='',
        expires_at=int(datetime.now().timestamp() * 1000) + 86400000
    )

    result = await decision_engine.execute_decision_action(decision)

    assert result is False


@pytest.mark.asyncio
async def test_execute_decision_action_delegated_actions(decision_engine, mock_clients):
    """Testa ações que são delegadas downstream (adjust_priorities, resolve_conflict)"""
    decision = StrategicDecision(
        decision_type=DecisionType.PRIORITIZATION,
        triggered_by=TriggeredBy(
            event_type='test',
            source_id='test',
            timestamp=int(datetime.now().timestamp() * 1000)
        ),
        context=DecisionContext(),
        analysis=DecisionAnalysis(),
        decision=DecisionAction(
            action='adjust_priorities',
            target_entities=['plan-1'],
            parameters={},
            rationale='Ajustar prioridades'
        ),
        confidence_score=0.7,
        risk_assessment=RiskAssessment(risk_score=0.1, risk_factors=[], mitigations=[]),
        guardrails_validated=[],
        reasoning_summary='',
        expires_at=int(datetime.now().timestamp() * 1000) + 86400000
    )

    result = await decision_engine.execute_decision_action(decision)

    # Ações delegadas retornam True sem chamar coordinator
    assert result is True


@pytest.mark.asyncio
async def test_execute_decision_action_handles_exceptions(decision_engine, mock_clients):
    """Testa tratamento de exceções durante execução"""
    decision = StrategicDecision(
        decision_type=DecisionType.REPLANNING,
        triggered_by=TriggeredBy(
            event_type='test',
            source_id='test',
            timestamp=int(datetime.now().timestamp() * 1000)
        ),
        context=DecisionContext(),
        analysis=DecisionAnalysis(),
        decision=DecisionAction(
            action='trigger_replanning',
            target_entities=['plan-1'],
            parameters={},
            rationale='Teste'
        ),
        confidence_score=0.5,
        risk_assessment=RiskAssessment(risk_score=0.1, risk_factors=[], mitigations=[]),
        guardrails_validated=[],
        reasoning_summary='',
        expires_at=int(datetime.now().timestamp() * 1000) + 86400000
    )

    # Simular exceção no coordinator
    mock_clients['replanning_coordinator'].trigger_replanning.side_effect = Exception("Test error")

    result = await decision_engine.execute_decision_action(decision)

    assert result is False


# ============================================================================
# Testes de integração OPA
# ============================================================================


@pytest.mark.asyncio
async def test_validate_guardrails_opa_allows(mock_clients, mock_settings):
    """Testa validação de guardrails quando OPA permite"""
    # Configurar mock OPA
    mock_clients['opa'].is_connected.return_value = True
    mock_clients['opa'].evaluate_policy.return_value = {
        "allow": True,
        "violations": [],
        "warnings": [],
        "guardrails_validated": ["risk_threshold_acceptable", "no_bias_risk"]
    }

    engine = StrategicDecisionEngine(
        mongodb_client=mock_clients['mongodb'],
        redis_client=mock_clients['redis'],
        neo4j_client=mock_clients['neo4j'],
        prometheus_client=mock_clients['prometheus'],
        pheromone_client=mock_clients['pheromone'],
        replanning_coordinator=mock_clients['replanning_coordinator'],
        opa_client=mock_clients['opa'],
        settings=mock_settings
    )

    result = await engine._validate_guardrails(
        decision_type=DecisionType.PRIORITIZATION,
        action=DecisionAction(action="adjust_priorities", rationale="test"),
        risk_assessment=RiskAssessment(risk_score=0.5, risk_factors=[], mitigations=[]),
        confidence_score=0.85,
        context=DecisionContext(resource_saturation=0.5),
        analysis=DecisionAnalysis(),
        reasoning_summary="Test reasoning"
    )

    assert len(result) == 2
    assert "risk_threshold_acceptable" in result
    assert "no_bias_risk" in result
    mock_clients['opa'].evaluate_policy.assert_called_once()


@pytest.mark.asyncio
async def test_validate_guardrails_opa_denies(mock_clients, mock_settings):
    """Testa validação de guardrails quando OPA nega"""
    mock_clients['opa'].is_connected.return_value = True
    mock_clients['opa'].evaluate_policy.return_value = {
        "allow": False,
        "violations": [
            {
                "policy": "ethical_guardrails",
                "rule": "excessive_risk",
                "severity": "critical",
                "msg": "Risk score muito alto"
            }
        ],
        "warnings": [],
        "guardrails_validated": []
    }

    engine = StrategicDecisionEngine(
        mongodb_client=mock_clients['mongodb'],
        redis_client=mock_clients['redis'],
        neo4j_client=mock_clients['neo4j'],
        prometheus_client=mock_clients['prometheus'],
        pheromone_client=mock_clients['pheromone'],
        replanning_coordinator=mock_clients['replanning_coordinator'],
        opa_client=mock_clients['opa'],
        settings=mock_settings
    )

    result = await engine._validate_guardrails(
        decision_type=DecisionType.REPLANNING,
        action=DecisionAction(action="trigger_replanning", rationale="test"),
        risk_assessment=RiskAssessment(risk_score=0.95, risk_factors=[], mitigations=[]),
        confidence_score=0.8,
        context=DecisionContext(resource_saturation=0.5),
        analysis=DecisionAnalysis(),
        reasoning_summary="Test"
    )

    # Lista vazia = validação falhou
    assert len(result) == 0
    mock_clients['opa'].evaluate_policy.assert_called_once()


@pytest.mark.asyncio
async def test_validate_guardrails_opa_unavailable_fail_open(mock_clients, mock_settings):
    """Testa fallback para validação básica quando OPA indisponível (fail open)"""
    mock_clients['opa'].is_connected.return_value = False
    mock_settings.OPA_FAIL_OPEN = True

    engine = StrategicDecisionEngine(
        mongodb_client=mock_clients['mongodb'],
        redis_client=mock_clients['redis'],
        neo4j_client=mock_clients['neo4j'],
        prometheus_client=mock_clients['prometheus'],
        pheromone_client=mock_clients['pheromone'],
        replanning_coordinator=mock_clients['replanning_coordinator'],
        opa_client=mock_clients['opa'],
        settings=mock_settings
    )

    result = await engine._validate_guardrails(
        decision_type=DecisionType.PRIORITIZATION,
        action=DecisionAction(action="adjust_priorities", rationale="test"),
        risk_assessment=RiskAssessment(risk_score=0.5, risk_factors=[], mitigations=[]),
        confidence_score=0.85,
        context=DecisionContext(resource_saturation=0.5),
        analysis=DecisionAnalysis(),
        reasoning_summary="Test"
    )

    # Validação básica deve passar
    assert len(result) > 0
    assert "risk_threshold_acceptable" in result
    mock_clients['opa'].evaluate_policy.assert_not_called()


@pytest.mark.asyncio
async def test_validate_guardrails_opa_with_warnings(mock_clients, mock_settings):
    """Testa validação de guardrails com warnings"""
    mock_clients['opa'].is_connected.return_value = True
    mock_clients['opa'].evaluate_policy.return_value = {
        "allow": True,
        "violations": [],
        "warnings": [
            {
                "policy": "ethical_guardrails",
                "rule": "high_risk_warning",
                "msg": "Risk score alto: 0.75"
            }
        ],
        "guardrails_validated": ["risk_threshold_acceptable"]
    }

    engine = StrategicDecisionEngine(
        mongodb_client=mock_clients['mongodb'],
        redis_client=mock_clients['redis'],
        neo4j_client=mock_clients['neo4j'],
        prometheus_client=mock_clients['prometheus'],
        pheromone_client=mock_clients['pheromone'],
        replanning_coordinator=mock_clients['replanning_coordinator'],
        opa_client=mock_clients['opa'],
        settings=mock_settings
    )

    result = await engine._validate_guardrails(
        decision_type=DecisionType.PRIORITIZATION,
        action=DecisionAction(action="adjust_priorities", rationale="test"),
        risk_assessment=RiskAssessment(risk_score=0.75, risk_factors=[], mitigations=[]),
        confidence_score=0.85,
        context=DecisionContext(resource_saturation=0.5),
        analysis=DecisionAnalysis(),
        reasoning_summary="Test"
    )

    # Deve permitir mesmo com warning
    assert len(result) > 0
    mock_clients['opa'].evaluate_policy.assert_called_once()


@pytest.mark.asyncio
async def test_validate_guardrails_no_opa_client(mock_clients, mock_settings):
    """Testa validação quando não há cliente OPA"""
    engine = StrategicDecisionEngine(
        mongodb_client=mock_clients['mongodb'],
        redis_client=mock_clients['redis'],
        neo4j_client=mock_clients['neo4j'],
        prometheus_client=mock_clients['prometheus'],
        pheromone_client=mock_clients['pheromone'],
        replanning_coordinator=mock_clients['replanning_coordinator'],
        opa_client=None,  # Sem cliente OPA
        settings=mock_settings
    )

    result = await engine._validate_guardrails(
        decision_type=DecisionType.PRIORITIZATION,
        action=DecisionAction(action="adjust_priorities", rationale="test"),
        risk_assessment=RiskAssessment(risk_score=0.5, risk_factors=[], mitigations=[]),
        confidence_score=0.85,
        context=DecisionContext(resource_saturation=0.5),
        analysis=DecisionAnalysis(),
        reasoning_summary="Test"
    )

    # Deve usar validação básica
    assert len(result) > 0
    assert "risk_threshold_acceptable" in result


@pytest.mark.asyncio
async def test_basic_guardrail_validation_high_risk(mock_clients, mock_settings):
    """Testa validação básica com risco alto"""
    engine = StrategicDecisionEngine(
        mongodb_client=mock_clients['mongodb'],
        redis_client=mock_clients['redis'],
        neo4j_client=mock_clients['neo4j'],
        prometheus_client=mock_clients['prometheus'],
        pheromone_client=mock_clients['pheromone'],
        replanning_coordinator=mock_clients['replanning_coordinator'],
        opa_client=None,
        settings=mock_settings
    )

    result = engine._basic_guardrail_validation(
        decision_type=DecisionType.PRIORITIZATION,
        risk_assessment=RiskAssessment(risk_score=0.95, risk_factors=[], mitigations=[])
    )

    # Risk > 0.9 não passa
    assert "risk_threshold_acceptable" not in result


@pytest.mark.asyncio
async def test_basic_guardrail_validation_exception_approval(mock_clients, mock_settings):
    """Testa validação básica com exception approval"""
    engine = StrategicDecisionEngine(
        mongodb_client=mock_clients['mongodb'],
        redis_client=mock_clients['redis'],
        neo4j_client=mock_clients['neo4j'],
        prometheus_client=mock_clients['prometheus'],
        pheromone_client=mock_clients['pheromone'],
        replanning_coordinator=mock_clients['replanning_coordinator'],
        opa_client=None,
        settings=mock_settings
    )

    result = engine._basic_guardrail_validation(
        decision_type=DecisionType.EXCEPTION_APPROVAL,
        risk_assessment=RiskAssessment(risk_score=0.5, risk_factors=[], mitigations=[])
    )

    # Exception approval não tem no_guardrail_violations
    assert "no_guardrail_violations" not in result
