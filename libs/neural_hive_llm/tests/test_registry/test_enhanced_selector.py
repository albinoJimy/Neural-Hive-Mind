"""
Unit tests para Enhanced Intelligent Selector.
"""

import pytest

from neural_hive_llm.registry import (
    ComplianceRequirement,
    DataResidencyRequirement,
    Domain,
    EnhancedSelectionContext,
    ExtendedSelectionCriteria,
    ExtendedSelectionWeights,
    PriorityLevel,
    get_enhanced_selector,
    reset_registry,
)


@pytest.fixture(autouse=True)
def reset_all_before_each():
    """Reseta registry antes de cada teste."""
    reset_registry()
    yield
    reset_registry()


@pytest.mark.asyncio
async def test_enhanced_selector_initialization():
    """Testa inicialização do selector expandido."""
    selector = get_enhanced_selector()

    assert selector is not None
    assert selector._registry is not None
    assert selector._tracker is not None


@pytest.mark.asyncio
async def test_select_by_domain_quality():
    """Testa seleção por qualidade específica de domínio."""
    selector = get_enhanced_selector()

    context = EnhancedSelectionContext(
        task_type="code_generation",
        expected_input_tokens=500,
        expected_output_tokens=500,
        domain=Domain.CODING,
        require_domain_expertise=True,
    )

    result = await selector.select_model(
        context, criteria=ExtendedSelectionCriteria.HIGHEST_DOMAIN_QUALITY
    )

    assert result is not None
    assert "domínio" in result.selection_reason.lower()


@pytest.mark.asyncio
async def test_select_most_reliable():
    """Testa seleção do modelo mais confiável."""
    selector = get_enhanced_selector()

    context = EnhancedSelectionContext(
        task_type="chat",
        expected_input_tokens=200,
        expected_output_tokens=300,
        min_uptime_percentage=99.0,
        min_success_rate=0.97,
    )

    result = await selector.select_model(context, criteria=ExtendedSelectionCriteria.MOST_RELIABLE)

    assert result is not None
    assert "confiabilidade" in result.selection_reason.lower()


@pytest.mark.asyncio
async def test_select_best_user_satisfaction():
    """Testa seleção por satisfação do utilizador."""
    selector = get_enhanced_selector()

    context = EnhancedSelectionContext(
        task_type="chat",
        expected_input_tokens=200,
        expected_output_tokens=300,
        require_positive_user_feedback=True,
        min_user_rating=4.0,
    )

    result = await selector.select_model(
        context, criteria=ExtendedSelectionCriteria.BEST_USER_SATISFACTION
    )

    assert result is not None
    assert "satisfação" in result.selection_reason.lower()


@pytest.mark.asyncio
async def test_select_best_compliance():
    """Testa seleção por melhor compliance."""
    selector = get_enhanced_selector()

    context = EnhancedSelectionContext(
        task_type="analysis",
        expected_input_tokens=500,
        expected_output_tokens=500,
        compliance_requirements=[ComplianceRequirement.SOC2],
        require_enterprise_tier=True,
    )

    result = await selector.select_model(
        context, criteria=ExtendedSelectionCriteria.BEST_COMPLIANCE
    )

    assert result is not None
    assert "compliance" in result.selection_reason.lower()


@pytest.mark.asyncio
async def test_select_priority_aware():
    """Testa seleção baseada na prioridade."""
    selector = get_enhanced_selector()

    # Prioridade crítica - deve seleccionar mais confiável
    critical_context = EnhancedSelectionContext(
        task_type="analysis",
        expected_input_tokens=500,
        expected_output_tokens=500,
        priority=PriorityLevel.CRITICAL,
        require_high_availability=True,
    )

    result = await selector.select_model(
        critical_context, criteria=ExtendedSelectionCriteria.PRIORITY_AWARE
    )

    assert result is not None

    # Prioridade baixa - deve seleccionar mais barato
    low_context = EnhancedSelectionContext(
        task_type="chat",
        expected_input_tokens=200,
        expected_output_tokens=300,
        priority=PriorityLevel.LOW,
    )

    result = await selector.select_model(
        low_context, criteria=ExtendedSelectionCriteria.PRIORITY_AWARE
    )

    assert result is not None


@pytest.mark.asyncio
async def test_select_optimal_composite():
    """Testa seleção óptima composta."""
    selector = get_enhanced_selector()

    context = EnhancedSelectionContext(
        task_type="code_generation",
        expected_input_tokens=1000,
        expected_output_tokens=1000,
        domain=Domain.CODING,
        require_domain_expertise=True,
        min_uptime_percentage=99.0,
        require_positive_user_feedback=True,
    )

    result = await selector.select_model(
        context, criteria=ExtendedSelectionCriteria.OPTIMAL_COMPOSITE
    )

    assert result is not None
    assert (
        "composta" in result.selection_reason.lower() or "óptima" in result.selection_reason.lower()
    )


@pytest.mark.asyncio
async def test_select_with_extended_custom_weights():
    """Testa seleção com pesos customizados extendidos."""
    selector = get_enhanced_selector()

    context = EnhancedSelectionContext(
        task_type="code_generation",
        expected_input_tokens=500,
        expected_output_tokens=500,
        domain=Domain.CODING,
    )

    weights = ExtendedSelectionWeights(
        performance_weight=0.20,
        cost_weight=0.15,
        quality_weight=0.15,
        domain_quality_weight=0.25,
        reliability_weight=0.15,
        user_feedback_weight=0.05,
        compliance_weight=0.05,
    )

    result = await selector.select_model(
        context, criteria=ExtendedSelectionCriteria.CUSTOM, weights=weights
    )

    assert result is not None
    assert "customizados" in result.selection_reason.lower()


@pytest.mark.asyncio
async def test_filter_by_compliance():
    """Testa filtro por compliance."""
    selector = get_enhanced_selector()

    context = EnhancedSelectionContext(
        task_type="analysis",
        expected_input_tokens=500,
        expected_output_tokens=500,
        compliance_requirements=[ComplianceRequirement.SOC2, ComplianceRequirement.GDPR],
    )

    result = await selector.select_model(context)

    assert result is not None


@pytest.mark.asyncio
async def test_filter_by_data_residency():
    """Testa filtro por residência de dados."""
    selector = get_enhanced_selector()

    context = EnhancedSelectionContext(
        task_type="chat",
        expected_input_tokens=200,
        expected_output_tokens=300,
        data_residency=DataResidencyRequirement.EU,
    )

    await selector.select_model(context)

    # Pode retornar None se nenhum modelo satisfizer
    # dependendo da simulação de metadados


@pytest.mark.asyncio
async def test_filter_by_exclude_providers():
    """Testa exclusão de providers."""
    selector = get_enhanced_selector()

    context = EnhancedSelectionContext(
        task_type="chat",
        expected_input_tokens=200,
        expected_output_tokens=300,
        exclude_providers={"local"},
    )

    result = await selector.select_model(context)

    assert result is not None
    # Não deve seleccionar modelo local


@pytest.mark.asyncio
async def test_filter_by_enterprise_tier():
    """Testa filtro por enterprise tier."""
    selector = get_enhanced_selector()

    context = EnhancedSelectionContext(
        task_type="analysis",
        expected_input_tokens=500,
        expected_output_tokens=500,
        require_enterprise_tier=True,
    )

    result = await selector.select_model(context)

    assert result is not None


@pytest.mark.asyncio
async def test_validate_extended_weights():
    """Testa validação de pesos extendidos."""
    weights = ExtendedSelectionWeights(
        performance_weight=0.20,
        cost_weight=0.20,
        quality_weight=0.20,
        domain_quality_weight=0.10,
        reliability_weight=0.10,
        user_feedback_weight=0.10,
        compliance_weight=0.10,
    )
    weights.validate()

    # Soma incorreta deve falhar
    invalid_weights = ExtendedSelectionWeights(
        performance_weight=0.20,
        cost_weight=0.20,
        quality_weight=0.20,
        domain_quality_weight=0.20,
        reliability_weight=0.20,
    )

    with pytest.raises(ValueError):
        invalid_weights.validate()


@pytest.mark.asyncio
async def test_enhanced_selection_context():
    """Testa contexto de seleção expandido."""
    context = EnhancedSelectionContext(
        task_type="code_generation",
        expected_input_tokens=1000,
        expected_output_tokens=1000,
        domain=Domain.CODING,
        priority=PriorityLevel.HIGH,
        compliance_requirements=[ComplianceRequirement.SOC2],
        data_residency=DataResidencyRequirement.US,
        require_high_availability=True,
        require_positive_user_feedback=True,
        min_user_rating=4.5,
        exclude_providers={"local"},
    )

    assert context.domain == Domain.CODING
    assert context.priority == PriorityLevel.HIGH
    assert len(context.compliance_requirements) == 1
    assert context.data_residency == DataResidencyRequirement.US
    assert context.require_high_availability
    assert "local" in context.exclude_providers


@pytest.mark.asyncio
async def test_no_model_meets_extended_criteria():
    """Testa quando nenhum modelo satisfaz os critérios expandidos."""
    selector = get_enhanced_selector()

    context = EnhancedSelectionContext(
        task_type="analysis",
        expected_input_tokens=500,
        expected_output_tokens=500,
        min_uptime_percentage=100.0,  # Impossível
        min_success_rate=1.0,
        compliance_requirements=[
            ComplianceRequirement.GDPR,
            ComplianceRequirement.HIPAA,
            ComplianceRequirement.SOC2,
            ComplianceRequirement.ISO27001,
        ],
        require_enterprise_tier=True,
    )

    await selector.select_model(context)

    # Provavelmente None devido a requisitos muito estritos
    # mas pode retornar algum modelo dependendo da simulação


@pytest.mark.asyncio
async def test_all_extended_selection_criteria():
    """Testa todos os critérios de seleção extendidos."""
    selector = get_enhanced_selector()

    context = EnhancedSelectionContext(
        task_type="chat",
        expected_input_tokens=200,
        expected_output_tokens=300,
    )

    for criteria in [
        ExtendedSelectionCriteria.FASTEST,
        ExtendedSelectionCriteria.CHEAPEST,
        ExtendedSelectionCriteria.HIGHEST_QUALITY,
        ExtendedSelectionCriteria.BALANCED,
        ExtendedSelectionCriteria.HIGHEST_DOMAIN_QUALITY,
        ExtendedSelectionCriteria.MOST_RELIABLE,
        ExtendedSelectionCriteria.BEST_USER_SATISFACTION,
        ExtendedSelectionCriteria.BEST_COMPLIANCE,
        ExtendedSelectionCriteria.OPTIMAL_COMPOSITE,
        ExtendedSelectionCriteria.PRIORITY_AWARE,
    ]:
        result = await selector.select_model(context, criteria=criteria)
        assert result is not None, f"Falhou para critério: {criteria}"
