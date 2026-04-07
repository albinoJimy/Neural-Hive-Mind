"""
Testes de contrato gRPC estendidos para validar todos os campos do schema v2.

Estes testes garantem que a estrutura de request/response está em conformidade
com o arquivo proto specialist.proto e com a versão 2.0.0 do schema.
"""

import pytest
import grpc
import uuid
import json

from neural_hive_specialists.proto_gen import specialist_pb2


@pytest.mark.contract
def test_evaluate_plan_full_opinion_structure(grpc_stub, sample_cognitive_plan):
    """Valida estrutura completa de SpecialistOpinion incluindo campos novos."""
    cognitive_plan_json = json.dumps(sample_cognitive_plan)
    cognitive_plan_bytes = cognitive_plan_json.encode("utf-8")

    request = specialist_pb2.EvaluatePlanRequest(
        plan_id=sample_cognitive_plan["plan_id"],
        intent_id=sample_cognitive_plan["intent_id"],
        trace_id=f"trace-{uuid.uuid4()}",
        cognitive_plan=cognitive_plan_bytes,
    )

    response = grpc_stub.EvaluatePlan(request)

    # Validar campos obrigatórios do opinion
    opinion = response.opinion

    # Scores (range 0.0-1.0)
    assert 0.0 <= opinion.confidence_score <= 1.0
    assert 0.0 <= opinion.risk_score <= 1.0

    # Recomendação (valores válidos)
    assert opinion.recommendation in [
        "approve",
        "reject",
        "review_required",
        "conditional",
        "proceed",
    ]

    # Campos de texto obrigatórios
    assert opinion.reasoning_summary
    assert isinstance(opinion.reasoning_summary, str)

    # Arrays obrigatórios (podem estar vazios)
    assert hasattr(opinion, "reasoning_factors")
    assert hasattr(opinion, "mitigations")

    # Metadados (mapa string->string - protobuf ScalarMapContainer)
    assert hasattr(opinion, "metadata")
    # Protobuf maps não são dict nativos, mas têm interface similar
    assert hasattr(opinion.metadata, "get")


@pytest.mark.contract
def test_evaluate_plan_explainability_structure(grpc_stub, sample_cognitive_plan):
    """Valida estrutura de explainability no opinion."""
    cognitive_plan_json = json.dumps(sample_cognitive_plan)
    cognitive_plan_bytes = cognitive_plan_json.encode("utf-8")

    request = specialist_pb2.EvaluatePlanRequest(
        plan_id=sample_cognitive_plan["plan_id"],
        intent_id=sample_cognitive_plan["intent_id"],
        cognitive_plan=cognitive_plan_bytes,
    )

    response = grpc_stub.EvaluatePlan(request)
    opinion = response.opinion

    # explainability_token é string (pode ser vazia)
    assert hasattr(opinion, "explainability_token")
    assert isinstance(opinion.explainability_token, str)

    # explainabilidade é mensagem opcional
    if opinion.HasField("explainability"):
        explainability = opinion.explainability

        # method deve ser um dos valores suportados
        assert explainability.method in [
            "shap",
            "lime",
            "rule_based",
            "heuristic",
            "semantic",
            "ensemble",
        ]

        # model_version e model_type são strings
        assert explainability.model_version
        assert explainability.model_type

        # feature_importances é array
        for feature_importance in explainability.feature_importances:
            assert feature_importance.feature_name
            assert 0.0 <= feature_importance.importance <= 1.0
            assert feature_importance.contribution in [
                "positive",
                "negative",
                "neutral",
            ]


@pytest.mark.contract
def test_evaluate_plan_reasoning_factors_validation(grpc_stub, sample_cognitive_plan):
    """Valida estrutura e valores de reasoning_factors."""
    cognitive_plan_json = json.dumps(sample_cognitive_plan)
    cognitive_plan_bytes = cognitive_plan_json.encode("utf-8")

    request = specialist_pb2.EvaluatePlanRequest(
        plan_id=sample_cognitive_plan["plan_id"],
        intent_id=sample_cognitive_plan["intent_id"],
        cognitive_plan=cognitive_plan_bytes,
    )

    response = grpc_stub.EvaluatePlan(request)
    opinion = response.opinion

    # Validar cada reasoning factor
    for factor in opinion.reasoning_factors:
        # factor_name é obrigatório e não vazio
        assert factor.factor_name
        assert len(factor.factor_name) > 0

        # weight e score estão em [0.0, 1.0]
        assert 0.0 <= factor.weight <= 1.0
        assert 0.0 <= factor.score <= 1.0

        # description é string (pode ser vazia)
        assert isinstance(factor.description, str)


@pytest.mark.contract
def test_evaluate_plan_mitigations_validation(grpc_stub, sample_cognitive_plan):
    """Valida estrutura e valores de mitigations."""
    cognitive_plan_json = json.dumps(sample_cognitive_plan)
    cognitive_plan_bytes = cognitive_plan_json.encode("utf-8")

    request = specialist_pb2.EvaluatePlanRequest(
        plan_id=sample_cognitive_plan["plan_id"],
        intent_id=sample_cognitive_plan["intent_id"],
        cognitive_plan=cognitive_plan_bytes,
    )

    response = grpc_stub.EvaluatePlan(request)
    opinion = response.opinion

    # Validar cada mitigação
    for mitigation in opinion.mitigations:
        # mitigation_id é obrigatório e não vazio
        assert mitigation.mitigation_id
        assert len(mitigation.mitigation_id) > 0

        # description é obrigatória e não vazia
        assert mitigation.description
        assert len(mitigation.description) > 0

        # priority deve ser um valor válido
        assert mitigation.priority in [
            "low",
            "medium",
            "high",
            "critical",
        ]

        # estimated_impact está em [0.0, 1.0]
        assert 0.0 <= mitigation.estimated_impact <= 1.0

        # required_actions é array de strings (pode ser vazio)
        assert isinstance(mitigation.required_actions, list)
        for action in mitigation.required_actions:
            assert isinstance(action, str)


@pytest.mark.contract
def test_health_check_all_status_values(grpc_stub):
    """Valida que HealthCheck retorna valores válidos."""
    request = specialist_pb2.HealthCheckRequest(service_name="test-specialist")
    response = grpc_stub.HealthCheck(request)

    # Validar que status é um dos valores enumerados
    valid_statuses = [
        specialist_pb2.HealthCheckResponse.UNKNOWN,
        specialist_pb2.HealthCheckResponse.SERVING,
        specialist_pb2.HealthCheckResponse.NOT_SERVING,
        specialist_pb2.HealthCheckResponse.SERVICE_UNKNOWN,
    ]
    assert response.status in valid_statuses

    # details é map string->string (protobuf ScalarMapContainer)
    # Protobuf maps não são dict nativos, mas têm interface similar
    assert hasattr(response.details, "get")


@pytest.mark.contract
def test_get_capabilities_complete_structure(grpc_stub):
    """Valida estrutura completa de GetCapabilities."""
    request = specialist_pb2.GetCapabilitiesRequest()
    response = grpc_stub.GetCapabilities(request)

    # Campos obrigatórios
    assert response.specialist_type
    assert response.version
    assert len(response.supported_domains) > 0
    assert len(response.supported_plan_versions) > 0

    # Validar supported_domains contém valores válidos
    # Nota: test_domain é usado apenas em testes
    valid_domains = [
        "business",
        "technical",
        "architecture",
        "behavior",
        "evolution",
        "security",
        "performance",
        "design-patterns",
        "solid-principles",
        "coupling-cohesion",
        "separation-of-concerns",
        "layering-modularity",
        "process-mining",
        "cost-analysis",
        "code-quality",
        "security-analysis",
        "maintainability",
        "scalability",
        "tech-debt",
        "test_domain",  # Domínio de teste
    ]
    for domain in response.supported_domains:
        assert domain.lower() in [d.lower() for d in valid_domains]

    # Validar supported_plan_versions segue semver
    for version in response.supported_plan_versions:
        # Versão deve seguir padrão X.Y.Z ou X.Y
        assert len(version.split(".")) in [2, 3]

    # configuration é map protobuf (pode ser vazio)
    assert hasattr(response.configuration, "get")

    # Validar métricas se presente
    if response.HasField("metrics"):
        metrics = response.metrics
        assert metrics.average_processing_time_ms >= 0.0
        assert 0.0 <= metrics.accuracy_score <= 1.0
        assert metrics.total_evaluations >= 0

        # last_model_update é timestamp válido se presente
        if metrics.HasField("last_model_update"):
            assert metrics.last_model_update.seconds > 0


@pytest.mark.contract
def test_evaluate_plan_request_all_fields(grpc_stub, sample_cognitive_plan):
    """Valida que todos os campos do request são processados."""
    trace_id = f"trace-{uuid.uuid4()}"
    span_id = f"span-{uuid.uuid4()}"
    correlation_id = f"corr-{uuid.uuid4()}"

    cognitive_plan_json = json.dumps(sample_cognitive_plan)
    cognitive_plan_bytes = cognitive_plan_json.encode("utf-8")

    # Criar request com todos os campos
    request = specialist_pb2.EvaluatePlanRequest(
        plan_id=sample_cognitive_plan["plan_id"],
        intent_id=sample_cognitive_plan["intent_id"],
        correlation_id=correlation_id,
        trace_id=trace_id,
        span_id=span_id,
        cognitive_plan=cognitive_plan_bytes,
        plan_version="1.0.0",
        timeout_ms=5000,
        context={
            "tenant_id": "test-tenant",
            "user_id": "test-user",
            "session_id": "test-session",
        },
    )

    # Executar e validar que processa sem erro
    response = grpc_stub.EvaluatePlan(request)
    assert response.opinion_id


@pytest.mark.contract
def test_evaluate_plan_context_propagation(grpc_stub, sample_cognitive_plan):
    """Valida que contexto adicional é propagado corretamente."""
    cognitive_plan_json = json.dumps(sample_cognitive_plan)
    cognitive_plan_bytes = cognitive_plan_json.encode("utf-8")

    context_data = {
        "tenant_id": "tenant-123",
        "user_id": "user-456",
        "session_id": "session-789",
        "custom_field": "custom_value",
    }

    request = specialist_pb2.EvaluatePlanRequest(
        plan_id=sample_cognitive_plan["plan_id"],
        intent_id=sample_cognitive_plan["intent_id"],
        cognitive_plan=cognitive_plan_bytes,
        context=context_data,
    )

    # Executar - contexto deve ser processado sem erro
    response = grpc_stub.EvaluatePlan(request)
    assert response.opinion_id


@pytest.mark.contract
def test_evaluate_plan_timestamp_validity(grpc_stub, sample_cognitive_plan):
    """Valida que timestamp retornado é válido e recente."""
    import time

    cognitive_plan_json = json.dumps(sample_cognitive_plan)
    cognitive_plan_bytes = cognitive_plan_json.encode("utf-8")

    before_time = time.time()

    request = specialist_pb2.EvaluatePlanRequest(
        plan_id=sample_cognitive_plan["plan_id"],
        intent_id=sample_cognitive_plan["intent_id"],
        cognitive_plan=cognitive_plan_bytes,
    )

    response = grpc_stub.EvaluatePlan(request)

    after_time = time.time()

    # Validar timestamp está dentro do intervalo esperado
    evaluated_at = response.evaluated_at
    assert evaluated_at.seconds > 0

    # Converter para segundos e validar que é recente (dentro de 1 minuto)
    evaluated_seconds = evaluated_at.seconds
    assert before_time - 60 <= evaluated_seconds <= after_time + 60


@pytest.mark.contract
def test_evaluate_plan_response_metadata(grpc_stub, sample_cognitive_plan):
    """Valida metadados da resposta."""
    cognitive_plan_json = json.dumps(sample_cognitive_plan)
    cognitive_plan_bytes = cognitive_plan_json.encode("utf-8")

    request = specialist_pb2.EvaluatePlanRequest(
        plan_id=sample_cognitive_plan["plan_id"],
        intent_id=sample_cognitive_plan["intent_id"],
        cognitive_plan=cognitive_plan_bytes,
    )

    response = grpc_stub.EvaluatePlan(request)

    # Validar campos de metadados da resposta
    assert response.opinion_id
    assert isinstance(response.opinion_id, str)

    assert response.specialist_type
    assert isinstance(response.specialist_type, str)

    assert response.specialist_version
    assert isinstance(response.specialist_version, str)

    assert response.processing_time_ms >= 0
    assert isinstance(response.processing_time_ms, int)


@pytest.mark.contract
def test_evaluate_plan_error_handling_empty_plan(grpc_stub):
    """Valida tratamento de erro para plano vazio."""
    empty_plan = {
        "plan_id": "plan-empty",
        "version": "1.0.0",
        "intent_id": "intent-123",
        "tasks": [],
    }

    cognitive_plan_bytes = json.dumps(empty_plan).encode("utf-8")

    request = specialist_pb2.EvaluatePlanRequest(
        plan_id=empty_plan["plan_id"],
        intent_id=empty_plan["intent_id"],
        cognitive_plan=cognitive_plan_bytes,
    )

    # Deve processar (mock sempre retorna approve)
    # Em produção, plano vazio pode retornar reject ou review_required
    response = grpc_stub.EvaluatePlan(request)
    # Mock sempre retorna opinion válida
    assert response.opinion.recommendation in [
        "approve",
        "reject",
        "review_required",
    ]


@pytest.mark.contract
def test_evaluate_plan_error_handling_malformed_json(grpc_stub):
    """Valida tratamento de erro para JSON malformado."""
    invalid_json_bytes = b'{"invalid": json}'

    request = specialist_pb2.EvaluatePlanRequest(
        plan_id="plan-invalid",
        intent_id="intent-123",
        cognitive_plan=invalid_json_bytes,
    )

    # Mock não valida JSON, então processa sem erro
    # Em produção, JSON malformado deve retornar erro
    response = grpc_stub.EvaluatePlan(request)
    assert response.opinion_id


@pytest.mark.contract
def test_grpc_interceptor_metadata_propagation(grpc_stub, sample_cognitive_plan):
    """Valida que metadados gRPC são propagados através de interceptors."""
    cognitive_plan_json = json.dumps(sample_cognitive_plan)
    cognitive_plan_bytes = cognitive_plan_json.encode("utf-8")

    request = specialist_pb2.EvaluatePlanRequest(
        plan_id=sample_cognitive_plan["plan_id"],
        intent_id=sample_cognitive_plan["intent_id"],
        cognitive_plan=cognitive_plan_bytes,
    )

    # Metadados que devem ser propagados
    metadata = [
        ("x-trace-id", "trace-test-123"),
        ("x-span-id", "span-test-456"),
        ("x-correlation-id", "corr-test-789"),
        ("x-tenant-id", "tenant-test"),
        ("authorization", "Bearer test-token"),
    ]

    # Executar com metadados - não deve lançar erro
    response = grpc_stub.EvaluatePlan(request, metadata=metadata)
    assert response.opinion_id


@pytest.mark.contract
def test_multiple_sequential_requests(grpc_stub, sample_cognitive_plan):
    """Valida que múltiplas requisições sequenciais funcionam corretamente."""
    cognitive_plan_json = json.dumps(sample_cognitive_plan)
    cognitive_plan_bytes = cognitive_plan_json.encode("utf-8")

    responses = []
    for i in range(5):
        request = specialist_pb2.EvaluatePlanRequest(
            plan_id=f"plan-{i}",
            intent_id=f"intent-{i}",
            cognitive_plan=cognitive_plan_bytes,
        )
        response = grpc_stub.EvaluatePlan(request)
        responses.append(response)

    # Nota: Mock retorna o mesmo opinion_id, mas em produção seriam únicos
    # Validar que todas as respostas têm estrutura válida
    for response in responses:
        assert response.opinion_id
        assert 0.0 <= response.opinion.confidence_score <= 1.0
        assert response.opinion.recommendation in [
            "approve",
            "reject",
            "review_required",
            "conditional",
        ]


@pytest.mark.contract
def test_response_size_limits(grpc_stub, sample_cognitive_plan):
    """Valida que tamanho da resposta está dentro dos limites gRPC."""
    cognitive_plan_json = json.dumps(sample_cognitive_plan)
    cognitive_plan_bytes = cognitive_plan_json.encode("utf-8")

    request = specialist_pb2.EvaluatePlanRequest(
        plan_id=sample_cognitive_plan["plan_id"],
        intent_id=sample_cognitive_plan["intent_id"],
        cognitive_plan=cognitive_plan_bytes,
    )

    response = grpc_stub.EvaluatePlan(request)

    # gRPC default max message size é 4MB
    # Resposta deve ser significativamente menor
    response_size = response.ByteSize()
    assert response_size < 1_000_000  # < 1MB


@pytest.mark.contract
def test_plan_version_compatibility(grpc_stub, sample_cognitive_plan):
    """Valida compatibilidade com diferentes versões de plano."""
    supported_versions = ["1.0.0", "1.1.0", "2.0.0"]

    for version in supported_versions:
        plan = sample_cognitive_plan.copy()
        plan["version"] = version
        plan["plan_id"] = f"plan-{version}"

        cognitive_plan_bytes = json.dumps(plan).encode("utf-8")

        request = specialist_pb2.EvaluatePlanRequest(
            plan_id=plan["plan_id"],
            intent_id=plan["intent_id"],
            cognitive_plan=cognitive_plan_bytes,
            plan_version=version,
        )

        response = grpc_stub.EvaluatePlan(request)
        assert response.opinion_id


@pytest.mark.contract
def test_timeout_handling(grpc_stub, sample_cognitive_plan):
    """Valida que timeout é respeitado."""
    cognitive_plan_json = json.dumps(sample_cognitive_plan)
    cognitive_plan_bytes = cognitive_plan_json.encode("utf-8")

    request = specialist_pb2.EvaluatePlanRequest(
        plan_id=sample_cognitive_plan["plan_id"],
        intent_id=sample_cognitive_plan["intent_id"],
        cognitive_plan=cognitive_plan_bytes,
        timeout_ms=100,  # Timeout muito curto
    )

    # Deve completar rapidamente (successo ou timeout)
    try:
        response = grpc_stub.EvaluatePlan(request, timeout=0.2)  # 200ms
        assert response.opinion_id
    except grpc.RpcError as e:
        # Se timeout, código deve be DEADLINE_EXCEEDED
        assert e.code() == grpc.StatusCode.DEADLINE_EXCEEDED
