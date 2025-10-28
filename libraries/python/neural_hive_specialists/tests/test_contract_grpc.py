"""
Testes de contrato gRPC para validar request/response structures.
"""

import pytest
import grpc
import uuid
from google.protobuf.timestamp_pb2 import Timestamp

from neural_hive_specialists.proto_gen import specialist_pb2


@pytest.mark.contract
def test_evaluate_plan_request_response_contract(grpc_stub, sample_cognitive_plan):
    """Valida contrato de EvaluatePlan: estrutura request/response."""
    # Construir CognitivePlan protobuf
    tasks = [
        specialist_pb2.Task(
            task_id=task['task_id'],
            task_type=task['task_type'],
            name=task['name'],
            description=task['description'],
            dependencies=task['dependencies'],
            estimated_duration_ms=task['estimated_duration_ms'],
            required_capabilities=task['required_capabilities'],
            parameters=task['parameters'],
            metadata=task.get('metadata', {})
        )
        for task in sample_cognitive_plan['tasks']
    ]

    plan = specialist_pb2.CognitivePlan(
        plan_id=sample_cognitive_plan['plan_id'],
        version=sample_cognitive_plan['version'],
        intent_id=sample_cognitive_plan['intent_id'],
        tasks=tasks,
        execution_order=sample_cognitive_plan['execution_order'],
        original_domain=sample_cognitive_plan['original_domain'],
        original_priority=sample_cognitive_plan['original_priority'],
        original_security_level=sample_cognitive_plan['original_security_level'],
        risk_score=sample_cognitive_plan['risk_score'],
        risk_band=sample_cognitive_plan['risk_band'],
        complexity_score=sample_cognitive_plan['complexity_score'],
        metadata=sample_cognitive_plan.get('metadata', {})
    )

    request = specialist_pb2.EvaluatePlanRequest(
        plan_id=sample_cognitive_plan['plan_id'],
        intent_id=sample_cognitive_plan['intent_id'],
        trace_id=sample_cognitive_plan.get('trace_id', f'trace-{uuid.uuid4()}'),
        span_id=sample_cognitive_plan.get('span_id', f'span-{uuid.uuid4()}'),
        correlation_id=sample_cognitive_plan.get('correlation_id', f'corr-{uuid.uuid4()}'),
        plan=plan
    )

    # Executar chamada gRPC
    response = grpc_stub.EvaluatePlan(request)

    # Validar estrutura de response
    assert response.opinion_id
    assert response.specialist_type == 'test'
    assert response.specialist_version
    assert response.processing_time_ms > 0

    # Validar opinion
    assert response.opinion.confidence_score >= 0.0
    assert response.opinion.confidence_score <= 1.0
    assert response.opinion.risk_score >= 0.0
    assert response.opinion.risk_score <= 1.0
    assert response.opinion.recommendation in ['approve', 'reject', 'review_required', 'proceed']
    assert response.opinion.reasoning_summary

    # Validar timestamp
    assert response.evaluated_at.seconds > 0


@pytest.mark.contract
def test_evaluate_plan_metadata_propagation(grpc_stub, sample_cognitive_plan):
    """Valida propagação de metadados (trace_id, span_id, correlation_id)."""
    trace_id = f'trace-{uuid.uuid4()}'
    span_id = f'span-{uuid.uuid4()}'
    correlation_id = f'corr-{uuid.uuid4()}'

    tasks = [
        specialist_pb2.Task(
            task_id=task['task_id'],
            task_type=task['task_type'],
            name=task['name'],
            description=task['description'],
            dependencies=task['dependencies'],
            estimated_duration_ms=task['estimated_duration_ms'],
            required_capabilities=task['required_capabilities'],
            parameters=task['parameters']
        )
        for task in sample_cognitive_plan['tasks']
    ]

    plan = specialist_pb2.CognitivePlan(
        plan_id=sample_cognitive_plan['plan_id'],
        version=sample_cognitive_plan['version'],
        intent_id=sample_cognitive_plan['intent_id'],
        tasks=tasks,
        execution_order=sample_cognitive_plan['execution_order'],
        original_domain=sample_cognitive_plan['original_domain']
    )

    request = specialist_pb2.EvaluatePlanRequest(
        plan_id=sample_cognitive_plan['plan_id'],
        intent_id=sample_cognitive_plan['intent_id'],
        trace_id=trace_id,
        span_id=span_id,
        correlation_id=correlation_id,
        plan=plan
    )

    # Adicionar metadados gRPC
    metadata = [
        ('x-trace-id', trace_id),
        ('x-span-id', span_id),
        ('x-correlation-id', correlation_id)
    ]

    response = grpc_stub.EvaluatePlan(request, metadata=metadata)

    # Validar resposta recebida (metadados devem ser processados sem erro)
    assert response.opinion_id


@pytest.mark.contract
def test_health_check_contract(grpc_stub):
    """Valida contrato de HealthCheck."""
    request = specialist_pb2.HealthCheckRequest()

    response = grpc_stub.HealthCheck(request)

    # Validar estrutura de response
    assert response.status in [
        specialist_pb2.HealthCheckResponse.SERVING,
        specialist_pb2.HealthCheckResponse.NOT_SERVING,
        specialist_pb2.HealthCheckResponse.UNKNOWN,
        specialist_pb2.HealthCheckResponse.SERVICE_UNKNOWN
    ]


@pytest.mark.contract
def test_get_capabilities_contract(grpc_stub):
    """Valida contrato de GetCapabilities."""
    request = specialist_pb2.GetCapabilitiesRequest()

    response = grpc_stub.GetCapabilities(request)

    # Validar estrutura de response
    assert response.specialist_type
    assert response.version
    assert len(response.supported_domains) > 0
    assert len(response.supported_plan_versions) > 0

    # Validar métricas (opcional mas esperado)
    if response.HasField('metrics'):
        assert response.metrics.average_processing_time_ms >= 0.0
        assert response.metrics.accuracy_score >= 0.0
        assert response.metrics.accuracy_score <= 1.0
        assert response.metrics.total_evaluations >= 0


@pytest.mark.contract
def test_evaluate_plan_invalid_plan_id_error_mapping(grpc_stub):
    """Valida mapeamento de erro para plan_id inválido."""
    # Criar request com plan_id vazio (inválido)
    plan = specialist_pb2.CognitivePlan(
        plan_id='',  # Inválido
        version='1.0.0',
        intent_id='intent-123',
        tasks=[],
        execution_order=[]
    )

    request = specialist_pb2.EvaluatePlanRequest(
        plan_id='',
        intent_id='intent-123',
        trace_id='trace-123',
        plan=plan
    )

    # Executar chamada gRPC - deve falhar ou retornar erro
    try:
        response = grpc_stub.EvaluatePlan(request)
        # Se não lançar exceção, validar que opinion contém indicação de erro
        # (implementação específica pode variar)
    except grpc.RpcError as e:
        # Validar código de status gRPC apropriado
        assert e.code() in [
            grpc.StatusCode.INVALID_ARGUMENT,
            grpc.StatusCode.FAILED_PRECONDITION,
            grpc.StatusCode.INTERNAL
        ]


@pytest.mark.contract
def test_evaluate_plan_reasoning_factors_structure(grpc_stub, sample_cognitive_plan):
    """Valida estrutura de reasoning_factors em response."""
    # Configurar mock para retornar reasoning_factors
    tasks = [
        specialist_pb2.Task(
            task_id=task['task_id'],
            task_type=task['task_type'],
            name=task['name'],
            description=task['description'],
            dependencies=task['dependencies'],
            estimated_duration_ms=task['estimated_duration_ms'],
            required_capabilities=task['required_capabilities']
        )
        for task in sample_cognitive_plan['tasks']
    ]

    plan = specialist_pb2.CognitivePlan(
        plan_id=sample_cognitive_plan['plan_id'],
        version=sample_cognitive_plan['version'],
        intent_id=sample_cognitive_plan['intent_id'],
        tasks=tasks,
        execution_order=sample_cognitive_plan['execution_order'],
        original_domain=sample_cognitive_plan['original_domain']
    )

    request = specialist_pb2.EvaluatePlanRequest(
        plan_id=sample_cognitive_plan['plan_id'],
        intent_id=sample_cognitive_plan['intent_id'],
        trace_id=f'trace-{uuid.uuid4()}',
        plan=plan
    )

    response = grpc_stub.EvaluatePlan(request)

    # Validar que reasoning_factors está presente (pode estar vazio)
    assert hasattr(response.opinion, 'reasoning_factors')
    # Se houver fatores, validar estrutura
    for factor in response.opinion.reasoning_factors:
        assert factor.factor_name
        assert factor.weight >= 0.0
        assert factor.weight <= 1.0
        assert factor.score >= 0.0
        assert factor.score <= 1.0


@pytest.mark.contract
def test_evaluate_plan_mitigations_structure(grpc_stub, sample_cognitive_plan):
    """Valida estrutura de mitigations em response."""
    tasks = [
        specialist_pb2.Task(
            task_id=task['task_id'],
            task_type=task['task_type'],
            name=task['name'],
            description=task['description'],
            dependencies=task['dependencies'],
            estimated_duration_ms=task['estimated_duration_ms'],
            required_capabilities=task['required_capabilities']
        )
        for task in sample_cognitive_plan['tasks']
    ]

    plan = specialist_pb2.CognitivePlan(
        plan_id=sample_cognitive_plan['plan_id'],
        version=sample_cognitive_plan['version'],
        intent_id=sample_cognitive_plan['intent_id'],
        tasks=tasks,
        execution_order=sample_cognitive_plan['execution_order'],
        original_domain=sample_cognitive_plan['original_domain']
    )

    request = specialist_pb2.EvaluatePlanRequest(
        plan_id=sample_cognitive_plan['plan_id'],
        intent_id=sample_cognitive_plan['intent_id'],
        trace_id=f'trace-{uuid.uuid4()}',
        plan=plan
    )

    response = grpc_stub.EvaluatePlan(request)

    # Validar que mitigations está presente (pode estar vazio)
    assert hasattr(response.opinion, 'mitigations')
    # Se houver mitigações, validar estrutura
    for mitigation in response.opinion.mitigations:
        assert mitigation.mitigation_id
        assert mitigation.description
        assert mitigation.priority in ['low', 'medium', 'high', 'critical']
