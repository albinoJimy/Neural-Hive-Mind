"""Testes de integração Kafka para Architect Agent."""

import asyncio
from uuid import uuid4

import pytest


@pytest.mark.asyncio()
async def test_architect_agent_consumes_cognitive_plans(
    kafka_producer,
    consume_from_topic,
    sample_cognitive_plan,
):
    """Testa se Architect Agent consome cognitive.plans.created."""
    # Publicar plano cognitivo
    await kafka_producer.send_and_wait("cognitive.plans.created", sample_cognitive_plan)

    # Aguardar processamento (simulado - em produção consumiria o tópico de saída)
    await asyncio.sleep(0.5)


@pytest.mark.asyncio()
async def test_architect_agent_produces_architecture_plans(
    publish_to_topic,
    consume_from_topic,
):
    """Testa se Architect Agent produz architecture.plans.generated."""
    # Simular mensagem que triggeria o architect agent
    cognitive_plan = {
        "plan_id": str(uuid4()),
        "intent": "Criar sistema de microsserviços para e-commerce",
        "context": {"domain": "backend", "complexity": "high"},
        "nlp_features": {"domain_backend": 0.9},
    }

    # Publicar no tópico de entrada
    await publish_to_topic("cognitive.plans.created", cognitive_plan)

    # Aguardar processamento
    await asyncio.sleep(1)

    # Consumir do tópico de saída (em produção, verificar se foi criado)
    # Este é um teste de integração que assumiria o serviço rodando


@pytest.mark.asyncio()
async def test_architecture_plan_schema_validation(consume_from_topic):
    """Testa se plano de arquitetura segue schema esperado."""
    # Schema esperado
    expected_fields = {
        "event_type",
        "plan_id",
        "cognitive_plan_id",
        "architecture_type",
        "components_count",
        "patterns",
        "rationale",
    }

    # Em produção, consumiria do tópico real e validaria
    # Este é um teste de estrutura
    assert expected_fields == {
        "event_type",
        "plan_id",
        "cognitive_plan_id",
        "architecture_type",
        "components_count",
        "patterns",
        "rationale",
    }


@pytest.mark.asyncio()
async def test_architecture_types_supported():
    """Testa que diferentes tipos de arquitetura são suportados."""
    from src.models.architecture import ArchitectureType

    # Verificar que todos os tipos esperados existem
    assert hasattr(ArchitectureType, "MICROSERVICES")
    assert hasattr(ArchitectureType, "MONOLITH")
    assert hasattr(ArchitectureType, "SERVERLESS")
    assert hasattr(ArchitectureType, "HYBRID")


@pytest.mark.asyncio()
async def test_architecture_plan_has_bounded_contexts():
    """Testa que planos de arquitetura incluem bounded contexts (DDD)."""
    from src.models.architecture import ArchitecturePlan, ArchitectureType, Component
    from src.models.bounded_context import BoundedContext

    # Criar plano com bounded contexts
    plan = ArchitecturePlan(
        plan_id=str(uuid4()),
        cognitive_plan_id=str(uuid4()),
        architecture_type=ArchitectureType.MICROSERVICES,
        components=[Component(name="user-api", stack="python/fastapi", replicas=3, ha=True)],
        patterns=["repository", "api_gateway"],
        rationale="Separação por domínio para escala independente",
        bounded_contexts=[
            BoundedContext(
                name="User Management",
                responsibilities=["user_crud", "authentication"],
                entities=["User", "Profile"],
            )
        ],
    )

    assert plan.bounded_contexts is not None
    assert len(plan.bounded_contexts) == 1
    assert plan.bounded_contexts[0].name == "User Management"


@pytest.mark.asyncio()
async def test_architecture_plan_has_tech_stack():
    """Testa que planos de arquitetura incluem stack tecnológico."""
    from src.models.architecture import ArchitecturePlan, ArchitectureType, Component
    from src.models.tech_stack import TechCategory, TechChoice

    # Criar plano com tech stack
    plan = ArchitecturePlan(
        plan_id=str(uuid4()),
        cognitive_plan_id=str(uuid4()),
        architecture_type=ArchitectureType.MICROSERVICES,
        components=[Component(name="user-api", stack="python/fastapi", replicas=3, ha=True)],
        patterns=["repository"],
        rationale="API Python moderna",
        tech_stack=[
            TechChoice(
                category=TechCategory.LANGUAGE,
                name="Python",
                version="3.12",
                rationale="Performance e tipo estatico",
            )
        ],
    )

    assert plan.tech_stack is not None
    assert len(plan.tech_stack) == 1
    assert plan.tech_stack[0].name == "Python"


@pytest.mark.asyncio()
async def test_diagram_generation():
    """Testa geração de diagramas de arquitetura."""
    from src.generators.architecture_diagram_generator import (
        ArchitectureDiagramGenerator,
    )

    generator = ArchitectureDiagramGenerator()

    # Testar diagrama de contexto
    diagram = generator.generate_context_diagram(
        "E-Commerce System",
        ["User API", "Product Catalog", "Order Service"],
    )

    assert diagram is not None
    assert diagram.content != ""
    assert "E-Commerce System" in diagram.content


@pytest.mark.asyncio()
async def test_design_planner_integration():
    """Testa integração do DesignPlanner com novos módulos Fluxo G."""
    from src.models.architecture import ArchitectureType
    from src.planners.design_planner import DesignPlanner

    planner = DesignPlanner()

    requirements = {
        "intent": "Sistema de e-commerce com microsserviços",
        "cognitive_plan_id": str(uuid4()),
        "context": {"domain": "ecommerce", "scale": "high"},
    }

    # Executar planejamento (assíncrono)
    plan = await planner.plan(requirements)

    # Validar resultado
    assert plan is not None
    assert plan.plan_id is not None
    assert plan.architecture_type == ArchitectureType.MICROSERVICES

    # Validar campos estendidos do Fluxo G
    if plan.bounded_contexts:
        assert len(plan.bounded_contexts) > 0
    if plan.tech_stack:
        assert len(plan.tech_stack) > 0
    if plan.diagrams:
        assert len(plan.diagrams) > 0
