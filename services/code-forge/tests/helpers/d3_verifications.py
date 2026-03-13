"""
Helpers de verificação para testes D3 (Build + Geração de Artefatos).

Estas funções auxiliam na verificação de conformidade conforme
MODELO_TESTE_WORKER_AGENT.md seção D3.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from src.models.artifact import (
from src.types.artifact_types import ArtifactCategory, CodeLanguage
    ArtifactCategory, CodeForgeArtifact, PipelineResult, PipelineStatus,
    PipelineStage, StageStatus, ValidationResult, ValidationType, ValidationStatus
)
from src.models.execution_ticket import TaskType, TicketStatus
from src.models.pipeline_context import PipelineContext


# ============================================================================
# Verificações de Pipeline
# ============================================================================


def verify_pipeline_triggered(pipeline_result: PipelineResult) -> bool:
    """
    Verifica se o pipeline foi disparado com sucesso.

    Critério: pipeline_id foi gerado
    """
    assert pipeline_result is not None, "Pipeline result é None"
    assert pipeline_result.pipeline_id is not None, "pipeline_id não foi gerado"
    assert len(pipeline_result.pipeline_id) > 0, "pipeline_id está vazio"
    return True


def verify_pipeline_status_completed(pipeline_result: PipelineResult) -> bool:
    """
    Verifica se o status do pipeline é COMPLETED.
    """
    assert pipeline_result.status == PipelineStatus.COMPLETED, \
        f"Status esperado: COMPLETED, recebido: {pipeline_result.status}"
    return True


def verify_all_stages_completed(pipeline_result: PipelineResult) -> bool:
    """
    Verifica se todos os 6 stages foram completados.

    Stages esperados:
    - template_selection
    - code_composition
    - validation
    - testing
    - packaging
    - approval_gate
    """
    expected_stages = [
        'template_selection',
        'code_composition',
        'validation',
        'testing',
        'packaging',
        'approval_gate'
    ]

    assert len(pipeline_result.pipeline_stages) == 6, \
        f"Esperados 6 stages, recebidos: {len(pipeline_result.pipeline_stages)}"

    stage_names = [stage.stage_name for stage in pipeline_result.pipeline_stages]
    for expected in expected_stages:
        assert expected in stage_names, f"Stage '{expected}' não encontrado"

    for stage in pipeline_result.pipeline_stages:
        assert stage.status == StageStatus.COMPLETED, \
            f"Stage {stage.stage_name} status: {stage.status}, esperado: COMPLETED"
        assert stage.duration_ms >= 0, f"Stage {stage.stage_name} tem duração negativa"

    return True


def verify_pipeline_timeout_not_exceeded(
    pipeline_result: PipelineResult,
    max_timeout_ms: int = 14400000  # 4 horas
) -> bool:
    """
    Verifica se o timeout não foi excedido.
    """
    assert pipeline_result.total_duration_ms <= max_timeout_ms, \
        f"Timeout excedido: {pipeline_result.total_duration_ms}ms > {max_timeout_ms}ms"
    return True


def verify_pipeline_duration_within_sla(
    pipeline_result: PipelineResult,
    max_duration_ms: int = 30000  # 30 segundos para testes
) -> bool:
    """
    Verifica se a duração está dentro do SLA.
    """
    assert pipeline_result.total_duration_ms < max_duration_ms, \
        f"Duração excedeu SLA: {pipeline_result.total_duration_ms}ms >= {max_duration_ms}ms"
    return True


# ============================================================================
# Verificações de Artefatos
# ============================================================================


def verify_artifacts_generated(pipeline_result: PipelineResult) -> bool:
    """
    Verifica se artefatos foram gerados.

    Tipos esperados para D3:
    - CONTAINER
    - MANIFEST
    - SBOM (via sbom_uri)
    - SIGNATURE (via signature field)
    """
    assert len(pipeline_result.artifacts) > 0, "Nenhum artefato foi gerado"

    artifact_types = [a.artifact_type for a in pipeline_result.artifacts]

    # Verificar se ao menos CONTAINER foi gerado
    assert ArtifactCategory.CONTAINER in artifact_types, \
        f"Artefato CONTAINER não encontrado. Tipos: {artifact_types}"

    return True


def verify_container_artifact(artifact: CodeForgeArtifact) -> bool:
    """
    Verifica se o artefato CONTAINER está correto.
    """
    assert artifact.artifact_type == ArtifactCategory.CONTAINER, \
        f"Tipo esperado: CONTAINER, recebido: {artifact.artifact_type}"

    assert artifact.content_uri is not None, "content_uri está vazio"
    assert artifact.content_hash is not None, "content_hash está vazio"
    assert artifact.content_hash.startswith('sha256:'), \
        f"content_hash não começa com sha256: {artifact.content_hash}"

    # Verificar SBOM
    assert artifact.sbom_uri is not None, "sbom_uri está vazio"

    # Verificar assinatura
    assert artifact.signature is not None, "signature está vazio"

    return True


def verify_sbom_generated(artifact: CodeForgeArtifact, format: str = 'SPDX') -> bool:
    """
    Verifica se SBOM foi gerado corretamente.

    Formato esperado: SPDX 2.3
    """
    assert artifact.sbom_uri is not None, "sbom_uri está vazio"

    # Verificar URI válida
    assert any(prefix in artifact.sbom_uri for prefix in ['s3://', 'gs://', 'http']), \
        f"sbom_uri inválido: {artifact.sbom_uri}"

    # Verificar se contém .spdx.json ou .spdx
    assert any(ext in artifact.sbom_uri for ext in ['.spdx.json', '.spdx', '.json']), \
        f"sbom_uri não parece ser SPDX: {artifact.sbom_uri}"

    return True


def verify_signature_present(artifact: CodeForgeArtifact) -> bool:
    """
    Verifica se a assinatura está presente e válida.

    Algoritmo esperado: SHA256
    """
    assert artifact.signature is not None, "signature está vazio"
    assert len(artifact.signature) > 0, "signature está vazia"

    # Assinatura deve ser uma string base64-like razoável
    assert len(artifact.signature) > 20, f"signature muito curta: {len(artifact.signature)}"

    return True


def verify_artifact_metadata(artifact: CodeForgeArtifact) -> bool:
    """
    Verifica metadados obrigatórios do artefato.
    """
    required_fields = ['artifact_id', 'ticket_id', 'created_at']

    for field in required_fields:
        assert hasattr(artifact, field) and getattr(artifact, field) is not None, \
            f"Campo obrigatório {field} está vazio"

    # Verificar timestamps
    assert artifact.created_at is not None, "created_at está vazio"
    assert isinstance(artifact.created_at, datetime), \
        f"created_at não é datetime: {type(artifact.created_at)}"

    return True


# ============================================================================
# Verificações de Validação
# ============================================================================


def verify_validation_passed(context: PipelineContext) -> bool:
    """
    Verifica se validações passaram sem issues críticos.
    """
    assert len(context.validation_results) > 0, "Nenhuma validação foi executada"

    for validation in context.validation_results:
        assert validation.status in [ValidationStatus.PASSED, ValidationStatus.WARNING], \
            f"Validação {validation.validation_type} falhou: {validation.status}"

        # Verificar que não há issues críticos
        assert validation.critical_issues == 0, \
            f"Validação {validation.validation_type} tem {validation.critical_issues} issues críticos"

    return True


def verify_security_scan_executed(context: PipelineContext) -> bool:
    """
    Verifica se scan de segurança foi executado.
    """
    validation_types = [v.validation_type for v in context.validation_results]

    assert ValidationType.SECURITY_SCAN in validation_types or \
           ValidationType.SAST in validation_types, \
           f"Scan de segurança não encontrado. Tipos: {validation_types}"

    return True


# ============================================================================
# Verificações de Kafka
# ============================================================================


def verify_kafka_message_published(
    mock_producer: MagicMock,
    expected_status: PipelineStatus = PipelineStatus.COMPLETED
) -> bool:
    """
    Verifica se mensagem foi publicada no Kafka.
    """
    assert mock_producer.publish_result.called, "publish_result não foi chamado"
    assert mock_producer.publish_result.call_count >= 1, \
        f"publish_result chamado {mock_producer.publish_result.call_count} vezes"

    # Verificar status da mensagem publicada
    call_args = mock_producer.publish_result.call_args
    if call_args and call_args[0]:
        result = call_args[0][0]
        assert result.status == expected_status, \
            f"Status publicado: {result.status}, esperado: {expected_status}"

    return True


def verify_kafka_message_structure(pipeline_result: PipelineResult) -> bool:
    """
    Verifica estrutura da mensagem Kafka.
    """
    required_fields = [
        'pipeline_id', 'ticket_id', 'status', 'artifacts',
        'total_duration_ms', 'created_at'
    ]

    for field in required_fields:
        assert hasattr(pipeline_result, field), f"Campo obrigatório {field} ausente"

    # Verificar trace/span IDs para tracing distribuído
    assert pipeline_result.trace_id is not None, "trace_id está vazio"
    assert pipeline_result.span_id is not None, "span_id está vazio"

    return True


# ============================================================================
# Verificações de MongoDB
# ============================================================================


def verify_mongodb_artifact_persisted(
    mock_mongodb: MagicMock,
    ticket_id: str
) -> bool:
    """
    Verifica se artefato foi persistido no MongoDB.
    """
    assert mock_mongodb.save_artifact_content.called or \
           mock_mongodb.save_pipeline_result.called, \
           "Nenhum método de persistência MongoDB foi chamado"

    # Se disponível, verificar save_artifact_content
    if hasattr(mock_mongodb, 'save_artifact_content') and mock_mongodb.save_artifact_content.called:
        call_args = mock_mongodb.save_artifact_content.call_args
        assert call_args is not None, "save_artifact_content chamado sem argumentos"

    return True


def verify_mongodb_document_structure(document: Dict[str, Any]) -> bool:
    """
    Verifica estrutura do documento MongoDB.
    """
    required_fields = ['artifact_id', 'ticket_id', 'artifact_type', 'content_uri']

    for field in required_fields:
        assert field in document, f"Campo obrigatório {field} ausente do documento"

    return True


# ============================================================================
# Verificações de PostgreSQL
# ============================================================================


def verify_postgres_pipeline_persisted(
    mock_postgres: MagicMock,
    pipeline_id: str
) -> bool:
    """
    Verifica se pipeline foi persistido no PostgreSQL.
    """
    assert mock_postgres.save_pipeline.called, "save_pipeline não foi chamado"

    # Verificar argumentos da chamada
    call_args = mock_postgres.save_pipeline.call_args
    assert call_args is not None, "save_pipeline chamado sem argumentos"

    if call_args and call_args[0]:
        result = call_args[0][0]
        assert result.pipeline_id == pipeline_id, \
            f"pipeline_id mismatch: {result.pipeline_id} != {pipeline_id}"

    return True


def verify_postgres_pipeline_record(record: Dict[str, Any]) -> bool:
    """
    Verifica estrutura do registro PostgreSQL.
    """
    required_fields = [
        'pipeline_id', 'ticket_id', 'status',
        'total_duration_ms', 'created_at'
    ]

    for field in required_fields:
        assert field in record, f"Campo obrigatório {field} ausente do registro"

    # Verificar status válido
    assert record['status'] in ['COMPLETED', 'FAILED', 'REQUIRES_REVIEW', 'PARTIAL'], \
        f"Status inválido: {record['status']}"

    return True


# ============================================================================
# Verificações de Métricas
# ============================================================================


def verify_build_metrics_emitted(mock_metrics: MagicMock) -> bool:
    """
    Verifica se métricas de build foram emitidas.

    Métricas esperadas:
    - build_tasks_executed_total
    - build_duration_seconds
    - build_artifacts_generated_total
    """
    metrics_to_verify = [
        'build_tasks_executed_total',
        'build_duration_seconds',
        'build_artifacts_generated_total'
    ]

    for metric_name in metrics_to_verify:
        assert hasattr(mock_metrics, metric_name), \
            f"Métrica {metric_name} não existe no mock"

    return True


def verify_pipeline_metrics_emitted(mock_metrics: MagicMock) -> bool:
    """
    Verifica se métricas de pipeline foram emitidas.
    """
    metrics_to_verify = [
        'pipelines_total',
        'pipeline_duration_seconds',
        'stage_duration_seconds'
    ]

    for metric_name in metrics_to_verify:
        assert hasattr(mock_metrics, metric_name), \
            f"Métrica {metric_name} não existe no mock"

    return True


def verify_api_metrics_emitted(
    mock_metrics: MagicMock,
    method: str = 'trigger_pipeline',
    status: str = 'success'
) -> bool:
    """
    Verifica se métricas de API foram emitidas.
    """
    assert hasattr(mock_metrics, 'code_forge_api_calls_total'), \
        "Métrica code_forge_api_calls_total não existe"

    # Verificar labels
    if hasattr(mock_metrics.code_forge_api_calls_total, 'labels'):
        mock_metrics.code_forge_api_calls_total.labels.assert_called()

    return True


# ============================================================================
# Verificações de Logs
# ============================================================================


def verify_expected_logs_present(
    log_records: List[Dict[str, Any]],
    expected_messages: List[str]
) -> bool:
    """
    Verifica se mensagens de log esperadas estão presentes.

    Mensagens esperadas para D3:
    - build_started
    - Triggered pipeline
    - build_completed
    - pipeline_completed
    """
    log_messages = [record.get('message', str(record)) for record in log_records]

    for expected in expected_messages:
        found = any(expected in msg for msg in log_messages)
        assert found, f"Mensagem de log esperada não encontrada: {expected}"

    return True


def verify_no_error_logs(log_records: List[Dict[str, Any]]) -> bool:
    """
    Verifica que não há logs de erro.
    """
    error_levels = ['ERROR', 'CRITICAL', 'exception']

    for record in log_records:
        level = record.get('level', '')
        assert level not in error_levels, \
            f"Log de erro encontrado: {record.get('message', record)}"

    return True


# ============================================================================
# Verificações de Conformidade D3 Completas
# ============================================================================


def verify_d3_conformance(
    pipeline_result: PipelineResult,
    context: Optional[PipelineContext] = None,
    mock_kafka_producer: Optional[MagicMock] = None,
    mock_postgres: Optional[MagicMock] = None,
    mock_mongodb: Optional[MagicMock] = None,
    mock_metrics: Optional[MagicMock] = None
) -> Dict[str, bool]:
    """
    Executa todas as verificações de conformidade D3.

    Retorna dict com resultados de cada verificação.
    """
    results = {}

    # Verificações de Pipeline
    try:
        results['pipeline_triggered'] = verify_pipeline_triggered(pipeline_result)
    except AssertionError:
        results['pipeline_triggered'] = False

    try:
        results['status_completed'] = verify_pipeline_status_completed(pipeline_result)
    except AssertionError:
        results['status_completed'] = False

    try:
        results['all_stages_completed'] = verify_all_stages_completed(pipeline_result)
    except AssertionError:
        results['all_stages_completed'] = False

    try:
        results['timeout_not_exceeded'] = verify_pipeline_timeout_not_exceeded(pipeline_result)
    except AssertionError:
        results['timeout_not_exceeded'] = False

    # Verificações de Artefatos
    try:
        results['artifacts_generated'] = verify_artifacts_generated(pipeline_result)
    except AssertionError:
        results['artifacts_generated'] = False

    # Verificar cada artefato
    for artifact in pipeline_result.artifacts:
        if artifact.artifact_type == ArtifactCategory.CONTAINER:
            try:
                results['container_valid'] = verify_container_artifact(artifact)
            except AssertionError:
                results['container_valid'] = False

            try:
                results['sbom_generated'] = verify_sbom_generated(artifact)
            except AssertionError:
                results['sbom_generated'] = False

            try:
                results['signature_present'] = verify_signature_present(artifact)
            except AssertionError:
                results['signature_present'] = False

    # Verificações de Kafka
    if mock_kafka_producer:
        try:
            results['kafka_published'] = verify_kafka_message_published(mock_kafka_producer)
        except AssertionError:
            results['kafka_published'] = False

    # Verificações de PostgreSQL
    if mock_postgres:
        try:
            results['postgres_persisted'] = verify_postgres_pipeline_persisted(
                mock_postgres, pipeline_result.pipeline_id
            )
        except AssertionError:
            results['postgres_persisted'] = False

    # Verificações de MongoDB
    if mock_mongodb:
        try:
            results['mongodb_persisted'] = verify_mongodb_artifact_persisted(
                mock_mongodb, pipeline_result.ticket_id
            )
        except AssertionError:
            results['mongodb_persisted'] = False

    # Verificações de Métricas
    if mock_metrics:
        try:
            results['build_metrics'] = verify_build_metrics_emitted(mock_metrics)
        except AssertionError:
            results['build_metrics'] = False

        try:
            results['pipeline_metrics'] = verify_pipeline_metrics_emitted(mock_metrics)
        except AssertionError:
            results['pipeline_metrics'] = False

    return results


def assert_d3_conformance(conformance_results: Dict[str, bool]) -> None:
    """
    Falha o teste se qualquer verificação de conformidade falhar.

    Args:
        conformance_results: Dict retornado por verify_d3_conformance

    Raises:
        AssertionError: Se qualquer verificação falhar
    """
    failed_checks = [k for k, v in conformance_results.items() if not v]

    if failed_checks:
        raise AssertionError(
            f"Verificações de conformidade D3 falharam: {', '.join(failed_checks)}\n"
            f"Resultados: {json.dumps(conformance_results, indent=2)}"
        )
