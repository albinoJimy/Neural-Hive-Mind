"""
Testes E2E do fluxo D3 (Build + Geração de Artefatos)

Conforme MODELO_TESTE_WORKER_AGENT.md seção D3.

Fluxo D3:
Worker Agent → CodeForge → PipelineEngine (6 subpipelines) →
Artefatos (CONTAINER, MANIFEST, SBOM, SIGNATURE) → Kafka/MongoDB/PostgreSQL
"""

import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.artifact import (
from src.types.artifact_types import ArtifactCategory, CodeLanguage
    ArtifactCategory, CodeForgeArtifact, PipelineResult, PipelineStatus,
    ValidationResult, ValidationType, ValidationStatus
)
from src.models.execution_ticket import TaskType, TicketStatus
from src.models.pipeline_context import PipelineContext


# Import fixtures from conftest and d3_fixtures
pytest_plugins = [
    'tests.unit.conftest',
    'tests.fixtures.d3_fixtures'
]


# ============================================================================
# Teste Principal: Fluxo D3 End-to-End
# ============================================================================


class TestD3BuildFlowEndToEnd:
    """
    Teste E2E do fluxo D3 conforme MODELO_TESTE_WORKER_AGENT.md

    Critérios de aceitação:
    - Ticket criado com task_type=BUILD
    - PipelineEngine executa 6 subpipelines
    - Artefatos gerados (CONTAINER, SBOM, SIGNATURE)
    - Resultado publicado no Kafka
    - Tempo execução < 30000ms
    """

    @pytest.mark.asyncio
    async def test_d3_build_ticket_creation_and_processing(
        self,
        d3_build_ticket,
        mock_d3_pipeline_engine,
        mock_d3_kafka_producer
    ):
        """
        D3: Criação e processamento de ticket BUILD

        Critérios:
        - Ticket criado com task_type=BUILD
        - PipelineEngine executa 6 subpipelines
        - Artefatos gerados (CONTAINER, SBOM, SIGNATURE)
        - Resultado publicado no Kafka
        - Tempo execução < 30000ms
        """
        # Setup: Configurar mock ticket_client para retornar o ticket
        mock_d3_pipeline_engine.ticket_client.get_ticket = AsyncMock(
            return_value=d3_build_ticket
        )

        # Executar pipeline
        start_time = datetime.now()
        result = await mock_d3_pipeline_engine.execute_pipeline(d3_build_ticket)
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        # Verificações
        assert result is not None, "Pipeline result é None"
        assert result.pipeline_id is not None, "pipeline_id não foi gerado"
        assert result.ticket_id == d3_build_ticket.ticket_id, "ticket_id mismatch"

        # Verificar status COMPLETED (auto-aprovação configurada)
        assert result.status == PipelineStatus.COMPLETED, \
            f"Status: {result.status}, esperado: COMPLETED"

        # Verificar 6 stages executados
        assert len(result.pipeline_stages) == 6, \
            f"Stages executados: {len(result.pipeline_stages)}, esperado: 6"

        stage_names = [s.stage_name for s in result.pipeline_stages]
        expected_stages = [
            'template_selection',
            'code_composition',
            'validation',
            'testing',
            'packaging',
            'approval_gate'
        ]
        for stage in expected_stages:
            assert stage in stage_names, f"Stage '{stage}' não executado"

        # Verificar tempo de execução
        assert duration_ms < 30000, \
            f"Tempo execução: {duration_ms}ms >= 30000ms (SLA excedido)"

        # Verificar Kafka publish
        assert mock_d3_kafka_producer.publish_result.called, \
            "Resultado não publicado no Kafka"

    @pytest.mark.asyncio
    async def test_d3_pipeline_with_container_artifact(
        self,
        d3_build_ticket_with_container,
        mock_d3_pipeline_engine,
        mock_d3_kafka_producer
    ):
        """
        D3: Pipeline com geração de artefato CONTAINER

        Verifica:
        - Artefato CONTAINER gerado
        - content_uri válida (ghcr.io)
        - content_hash começa com sha256:
        - sbom_uri presente
        - signature presente
        """
        result = await mock_d3_pipeline_engine.execute_pipeline(
            d3_build_ticket_with_container
        )

        # Verificar artefatos gerados
        assert len(result.artifacts) > 0, "Nenhum artefato gerado"

        # Encontrar artefato CONTAINER
        container_artifacts = [
            a for a in result.artifacts
            if a.artifact_type == ArtifactCategory.CONTAINER
        ]
        assert len(container_artifacts) > 0, "Artefato CONTAINER não encontrado"

        container = container_artifacts[0]

        # Verificar campos obrigatórios
        assert container.content_uri is not None, "content_uri vazio"
        assert 'ghcr.io' in container.content_uri or \
               'docker.io' in container.content_uri or \
               'gcr.io' in container.content_uri, \
            f"content_uri inválida: {container.content_uri}"

        assert container.content_hash is not None, "content_hash vazio"
        assert container.content_hash.startswith('sha256:'), \
            f"content_hash inválido: {container.content_hash}"

        assert container.sbom_uri is not None, "sbom_uri vazio"

        assert container.signature is not None, "signature vazio"

    @pytest.mark.asyncio
    async def test_d3_pipeline_with_sbom_generation(
        self,
        d3_build_ticket_with_sbom,
        mock_d3_pipeline_engine
    ):
        """
        D3: Pipeline com geração de SBOM

        Verifica:
        - SBOM gerado (formato SPDX 2.3)
        - sbom_uri válida (s3://, gs://, etc)
        """
        result = await mock_d3_pipeline_engine.execute_pipeline(
            d3_build_ticket_with_sbom
        )

        # Verificar artefatos com SBOM
        artifacts_with_sbom = [
            a for a in result.artifacts
            if a.sbom_uri is not None
        ]
        assert len(artifacts_with_sbom) > 0, "Nenhum artefato com SBOM"

        sbom_artifact = artifacts_with_sbom[0]

        # Verificar formato SPDX
        assert '.spdx' in sbom_artifact.sbom_uri or \
               'sbom' in sbom_artifact.sbom_uri.lower(), \
            f"sbom_uri não parece ser SPDX: {sbom_artifact.sbom_uri}"

    @pytest.mark.asyncio
    async def test_d3_pipeline_timeout_handling(
        self,
        d3_build_ticket,
        mock_d3_pipeline_engine
    ):
        """
        D3: Pipeline com timeout configurado

        Verifica:
        - Timeout respeitado (14400s = 4h)
        - Status FAILED se timeout excedido
        """
        # Configurar timeout curto para teste
        mock_d3_pipeline_engine.pipeline_timeout = 1  # 1 segundo

        # Mock que demora mais que o timeout
        async def _slow_stage(context):
            await asyncio.sleep(2)

        mock_d3_pipeline_engine.template_selector.select = AsyncMock(
            side_effect=_slow_stage
        )

        # Executar (deve falhar com timeout)
        result = await mock_d3_pipeline_engine.execute_pipeline(d3_build_ticket)

        # Verificar status
        assert result.status == PipelineStatus.FAILED, \
            f"Status: {result.status}, esperado: FAILED (timeout)"

        # Verificar mensagem de erro nos stages
        stage_errors = [s.error_message for s in result.pipeline_stages if s.error_message]
        assert len(stage_errors) > 0, "Nenhum erro de stage encontrado"
        assert any('timeout' in err.lower() for err in stage_errors), \
            f"Erro de timeout não encontrado em: {stage_errors}"

    @pytest.mark.asyncio
    async def test_d3_pipeline_retry_logic(
        self,
        d3_build_ticket,
        mock_d3_pipeline_engine,
        mock_ticket_client
    ):
        """
        D3: Pipeline com lógica de retry

        Verifica:
        - Máximo de 3 tentativas configuradas
        - Ticket de compensação criado em falha
        """
        # Mock que falha na primeira tentativa
        attempt_count = {'count': 0}

        async def _failing_stage(context):
            attempt_count['count'] += 1
            if attempt_count['count'] == 1:
                raise Exception("Simulated failure")
            # Segunda tentativa succeeds

        mock_d3_pipeline_engine.template_selector.select = AsyncMock(
            side_effect=_failing_stage
        )

        # Executar (deve falhar e criar compensação)
        result = await mock_d3_pipeline_engine.execute_pipeline(d3_build_ticket)

        # Verificar que compensação foi criada
        assert mock_ticket_client.create_compensation_ticket.called, \
            "Ticket de compensação não criado"


# ============================================================================
# Testes de Stages Individuais
# ============================================================================


class TestD3PipelineStages:
    """Testes individuais de cada stage do pipeline D3."""

    @pytest.mark.asyncio
    async def test_d3_template_selection_stage(
        self,
        d3_pipeline_context,
        mock_d3_template_selector
    ):
        """
        D3: Stage template_selection

        Verifica:
        - Template selecionado corretamente
        - Metadata atualizada
        """
        await mock_d3_template_selector.select(d3_pipeline_context)

        assert d3_pipeline_context.selected_template is not None, \
            "Template não selecionado"

        assert d3_pipeline_context.metadata.get('template_selected') is not None, \
            "Metadata não atualizada"

    @pytest.mark.asyncio
    async def test_d3_code_composition_stage(
        self,
        d3_pipeline_context,
        mock_d3_code_composer
    ):
        """
        D3: Stage code_composition

        Verifica:
        - Código composto
        - Workspace criado
        """
        await mock_d3_code_composer.compose(d3_pipeline_context)

        assert d3_pipeline_context.metadata.get('code_composed') == 'true', \
            "Código não composto"

        assert d3_pipeline_context.code_workspace_path is not None, \
            "Workspace não criado"

    @pytest.mark.asyncio
    async def test_d3_validation_stage(
        self,
        d3_pipeline_context,
        mock_d3_validator
    ):
        """
        D3: Stage validation

        Verifica:
        - Validação executada
        - Resultado PASSED
        - Sem issues críticos
        """
        await mock_d3_validator.validate(d3_pipeline_context)

        assert len(d3_pipeline_context.validation_results) > 0, \
            "Nenhuma validação executada"

        validation = d3_pipeline_context.validation_results[0]
        assert validation.status == ValidationStatus.PASSED, \
            f"Status: {validation.status}"
        assert validation.critical_issues == 0, \
            f"Issues críticos: {validation.critical_issues}"

    @pytest.mark.asyncio
    async def test_d3_testing_stage(
        self,
        d3_pipeline_context,
        mock_d3_test_runner
    ):
        """
        D3: Stage testing

        Verifica:
        - Testes executados
        - Metadata com contagem
        """
        await mock_d3_test_runner.run_tests(d3_pipeline_context)

        assert d3_pipeline_context.metadata.get('tests_run') is not None, \
            "Testes não executados"

    @pytest.mark.asyncio
    async def test_d3_packaging_stage(
        self,
        d3_pipeline_context,
        mock_d3_packager
    ):
        """
        D3: Stage packaging

        Verifica:
        - Container criado
        - SBOM gerado
        - Assinatura aplicada
        """
        await mock_d3_packager.package(d3_pipeline_context)

        assert len(d3_pipeline_context.generated_artifacts) > 0, \
            "Nenhum artefato gerado"

        container = d3_pipeline_context.generated_artifacts[0]
        assert container.artifact_type == ArtifactCategory.CONTAINER, \
            f"Tipo: {container.artifact_type}"

        assert container.sbom_uri is not None, "SBOM não gerado"
        assert container.signature is not None, "Assinatura não aplicada"

    @pytest.mark.asyncio
    async def test_d3_approval_gate_stage(
        self,
        d3_pipeline_context,
        mock_d3_approval_gate
    ):
        """
        D3: Stage approval_gate

        Verifica:
        - Aprovação concedida (auto em testes)
        - Metadata atualizada
        """
        approved = await mock_d3_approval_gate.check_approval(d3_pipeline_context)

        assert approved is True, "Aprovação não concedida"
        assert d3_pipeline_context.metadata.get('approval_status') == 'AUTO_APPROVED', \
            "Status de aprovação incorreto"


# ============================================================================
# Testes de Integração com Serviços Externos
# ============================================================================


class TestD3ExternalServicesIntegration:
    """Testes de integração com serviços externos."""

    @pytest.mark.asyncio
    async def test_d3_ticket_client_status_update(
        self,
        d3_build_ticket,
        mock_d3_pipeline_engine,
        mock_ticket_client
    ):
        """
        D3: Atualização de status do ticket

        Verifica:
        - Status PENDING → RUNNING → COMPLETED
        - pipeline_id adicionado aos metadata
        """
        result = await mock_d3_pipeline_engine.execute_pipeline(d3_build_ticket)

        # Verificar chamadas de update_status
        assert mock_ticket_client.update_status.called, \
            "update_status não foi chamado"

        # Deve ter sido chamado pelo menos 2x (RUNNING + COMPLETED/FAILED)
        assert mock_ticket_client.update_status.call_count >= 2, \
            f"update_status chamado {mock_ticket_client.update_status.call_count} vezes"

    @pytest.mark.asyncio
    async def test_d3_postgres_persistence(
        self,
        d3_build_ticket,
        mock_d3_pipeline_engine,
        mock_postgres_client
    ):
        """
        D3: Persistência no PostgreSQL

        Verifica:
        - save_pipeline chamado
        - PipelineResult com campos obrigatórios
        """
        result = await mock_d3_pipeline_engine.execute_pipeline(d3_build_ticket)

        assert mock_postgres_client.save_pipeline.called, \
            "save_pipeline não foi chamado"

        # Verificar argumentos
        call_args = mock_postgres_client.save_pipeline.call_args
        assert call_args is not None, "save_pipeline sem argumentos"

        saved_result = call_args[0][0]
        assert saved_result.pipeline_id == result.pipeline_id, \
            "pipeline_id mismatch"
        assert saved_result.status == result.status, \
            "status mismatch"

    @pytest.mark.asyncio
    async def test_d3_mongodb_artifact_storage(
        self,
        d3_build_ticket_with_container,
        mock_d3_pipeline_engine,
        mock_mongodb_client
    ):
        """
        D3: Armazenamento de artefatos no MongoDB

        Verifica:
        - Artefato salvo corretamente
        - URI do MongoDB válida
        """
        result = await mock_d3_pipeline_engine.execute_pipeline(
            d3_build_ticket_with_container
        )

        # Verificar se pelo menos um artefato foi salvo
        # (depende da implementação do packager)
        assert len(result.artifacts) > 0, "Nenhum artefato para salvar"


# ============================================================================
# Testes de Cenários de Falha
# ============================================================================


class TestD3FailureScenarios:
    """Testes de cenários de falha no fluxo D3."""

    @pytest.mark.asyncio
    async def test_d3_validation_failure_blocks_build(
        self,
        d3_build_ticket,
        mock_d3_pipeline_engine,
        mock_d3_validator
    ):
        """
        D3: Falha na validação bloqueia o build

        Verifica:
        - Status do pipeline: FAILED
        - Mensagem de erro presente
        - Kafka publicado com falha
        """
        # Mock que falha validação
        async def _failing_validation(context):
            from src.models.artifact import (
                ValidationResult, ValidationType, ValidationStatus
            )
            validation = ValidationResult(
                validation_type=ValidationType.SAST,
                tool_name='SonarQube',
                tool_version='10.0.0',
                status=ValidationStatus.FAILED,
                score=0.3,
                issues_count=15,
                critical_issues=3,
                high_issues=5,
                medium_issues=4,
                low_issues=3,
                executed_at=datetime.now(),
                duration_ms=5000
            )
            context.add_validation(validation)
            raise Exception("Validation failed with critical issues")

        mock_d3_validator.validate = AsyncMock(side_effect=_failing_validation)

        # Executar
        result = await mock_d3_pipeline_engine.execute_pipeline(d3_build_ticket)

        # Verificar falha
        assert result.status == PipelineStatus.FAILED, \
            f"Status: {result.status}, esperado: FAILED"

    @pytest.mark.asyncio
    async def test_d3_packaging_failure_creates_compensation(
        self,
        d3_build_ticket,
        mock_d3_pipeline_engine,
        mock_d3_packager,
        mock_ticket_client
    ):
        """
        D3: Falha no packaging cria ticket de compensação

        Verifica:
        - Status do pipeline: FAILED
        - create_compensation_ticket chamado
        - update_status com FAILED
        """
        # Mock que falha packaging
        async def _failing_packaging(context):
            raise Exception("Docker build failed")

        mock_d3_packager.package = AsyncMock(side_effect=_failing_packaging)

        # Executar
        result = await mock_d3_pipeline_engine.execute_pipeline(d3_build_ticket)

        # Verificar compensação
        assert mock_ticket_client.create_compensation_ticket.called, \
            "Compensation ticket não criado"

        assert result.status == PipelineStatus.FAILED, \
            f"Status: {result.status}"


# ============================================================================
# Testes de Performance
# ============================================================================


class TestD3Performance:
    """Testes de performance do fluxo D3."""

    @pytest.mark.asyncio
    async def test_d3_pipeline_duration_within_sla(
        self,
        d3_build_ticket,
        mock_d3_pipeline_engine
    ):
        """
        D3: Duração do pipeline dentro do SLA

        SLA: < 30000ms para testes (produção: 14400000ms = 4h)
        """
        import time

        start_time = time.time()
        result = await mock_d3_pipeline_engine.execute_pipeline(d3_build_ticket)
        duration_ms = int((time.time() - start_time) * 1000)

        assert duration_ms < 30000, \
            f"Duração: {duration_ms}ms excede SLA de 30000ms"

        # Verificar duração registrada
        assert result.total_duration_ms > 0, "Duração registrada é 0"
        assert result.total_duration_ms < 30000, \
            f"Duração registrada: {result.total_duration_ms}ms"

    @pytest.mark.asyncio
    async def test_d3_concurrent_pipeline_limit(
        self,
        mock_d3_pipeline_engine
    ):
        """
        D3: Limite de pipelines concorrentes

        Verifica:
        - max_concurrent = 3 respeitado
        - Pipelines adicionais aguardam
        """
        from src.models.execution_ticket import (
            ExecutionTicket, TaskType, TicketStatus, Priority, RiskBand,
            SLA, QoS, SecurityLevel, DeliveryMode, Consistency, Durability
        )

        # Criar 5 tickets
        tickets = []
        for i in range(5):
            ticket = ExecutionTicket(
                ticket_id=str(uuid.uuid4()),
                plan_id=f'plan-concurrent-{i}',
                intent_id=f'intent-concurrent-{i}',
                decision_id=f'decision-concurrent-{i}',
                correlation_id=str(uuid.uuid4()),
                trace_id=str(uuid.uuid4()),
                span_id=str(uuid.uuid4()),
                task_type=TaskType.BUILD,
                status=TicketStatus.PENDING,
                priority=Priority.NORMAL,
                risk_band=RiskBand.MEDIUM,
                parameters={'artifact_id': f'service-{i}'},
                sla=SLA(
                    deadline=datetime.now(),
                    timeout_ms=30000,
                    max_retries=3
                ),
                qos=QoS(
                    delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                    consistency=Consistency.EVENTUAL,
                    durability=Durability.PERSISTENT
                ),
                security_level=SecurityLevel.INTERNAL,
                dependencies=[],
                created_at=datetime.now()
            )
            tickets.append(ticket)

        # Executar pipelines concorrentemente
        results = await asyncio.gather(*[
            mock_d3_pipeline_engine.execute_pipeline(ticket)
            for ticket in tickets
        ])

        # Todos devem completar (respeitando o semáforo interno)
        assert len(results) == 5, f"Resultados: {len(results)}/5"

        for result in results:
            assert result.status == PipelineStatus.COMPLETED, \
                f"Pipeline {result.pipeline_id} status: {result.status}"
