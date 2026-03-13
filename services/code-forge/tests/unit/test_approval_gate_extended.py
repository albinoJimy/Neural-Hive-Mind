"""
Testes estendidos para ApprovalGate.

Este modulo testa metodos e caminhos nao cobertos pelos testes existentes,
focando em edge cases, error handling e cenarios alternativos.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.services.approval_gate import ApprovalGate
from src.models.pipeline_context import PipelineContext
from src.models.execution_ticket import (
    ExecutionTicket, TaskType, TicketStatus, Priority, RiskBand,
    SLA, QoS, SecurityLevel, DeliveryMode, Consistency, Durability
)
from src.models.artifact import CodeForgeArtifact, GenerationMethod
from src.types.artifact_types import ArtifactCategory
from src.models.template import Template, TemplateMetadata, TemplateType
from src.types.artifact_types import CodeLanguage
import uuid


class TestGetFilenameForLanguage:
    """Testes para metodo _get_filename_for_language."""

    @pytest.fixture
    def approval_gate(self, mock_git_client):
        """Instancia do ApprovalGate para testes."""
        return ApprovalGate(
            git_client=mock_git_client,
            mongodb_client=None,
            auto_approval_threshold=0.9,
            min_quality_score=0.5
        )

    def test_python_filename(self, approval_gate):
        """Testa nome de arquivo para Python."""
        filename = approval_gate._get_filename_for_language('python')
        assert filename == 'main.py'

    def test_python_uppercase_filename(self, approval_gate):
        """Testa nome de arquivo para Python em maiusculas (nao suportado)."""
        # O metodo nao converte para minusculas, entao retorna main.PYTHON
        filename = approval_gate._get_filename_for_language('PYTHON')
        assert filename == 'main.PYTHON'

    def test_javascript_filename(self, approval_gate):
        """Testa nome de arquivo para JavaScript."""
        filename = approval_gate._get_filename_for_language('javascript')
        assert filename == 'index.js'

    def test_typescript_filename(self, approval_gate):
        """Testa nome de arquivo para TypeScript."""
        filename = approval_gate._get_filename_for_language('typescript')
        assert filename == 'index.ts'

    def test_go_filename(self, approval_gate):
        """Testa nome de arquivo para Go."""
        filename = approval_gate._get_filename_for_language('go')
        assert filename == 'main.go'

    def test_java_filename(self, approval_gate):
        """Testa nome de arquivo para Java."""
        filename = approval_gate._get_filename_for_language('java')
        assert filename == 'Main.java'

    def test_rust_filename(self, approval_gate):
        """Testa nome de arquivo para Rust."""
        filename = approval_gate._get_filename_for_language('rust')
        assert filename == 'main.rs'

    def test_ruby_filename(self, approval_gate):
        """Testa nome de arquivo para Ruby."""
        filename = approval_gate._get_filename_for_language('ruby')
        assert filename == 'main.rb'

    def test_php_filename(self, approval_gate):
        """Testa nome de arquivo para PHP."""
        filename = approval_gate._get_filename_for_language('php')
        assert filename == 'index.php'

    def test_unknown_language_filename(self, approval_gate):
        """Testa nome de arquivo para linguagem desconhecida."""
        filename = approval_gate._get_filename_for_language('unknown-lang')
        assert filename == 'main.unknown-lang'

    def test_none_language_filename(self, approval_gate):
        """Testa nome de arquivo quando linguagem eh None."""
        # O metodo nao trata None especialmente, retorna 'main.None'
        filename = approval_gate._get_filename_for_language(None)
        assert filename == 'main.None'


class TestGenerateReadme:
    """Testes para metodo _generate_readme."""

    @pytest.fixture
    def approval_gate(self, mock_git_client):
        """Instancia do ApprovalGate para testes."""
        return ApprovalGate(
            git_client=mock_git_client,
            mongodb_client=None,
            auto_approval_threshold=0.9,
            min_quality_score=0.5
        )

    @pytest.fixture
    def sample_context(self):
        """Contexto de pipeline para testes."""
        ticket_id = str(uuid.uuid4())
        ticket = ExecutionTicket(
            ticket_id=ticket_id,
            plan_id=f'plan-{ticket_id[:8]}',
            intent_id=f'intent-{ticket_id[:8]}',
            decision_id=f'decision-{ticket_id[:8]}',
            correlation_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            task_type=TaskType.BUILD,
            status=TicketStatus.PENDING,
            priority=Priority.NORMAL,
            risk_band=RiskBand.MEDIUM,
            parameters={
                'service_name': 'test-service',
                'description': 'A test service',
                'target_repo': 'https://github.com/test/repo'
            },
            sla=SLA(
                deadline=datetime.now(),
                timeout_ms=300000,
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

        context = PipelineContext(
            pipeline_id=str(uuid.uuid4()),
            ticket=ticket,
            trace_id=str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            metadata={}
        )

        # Template
        template = Template(
            template_id='microservice-python-v1',
            metadata=TemplateMetadata(
                name='Python Microservice',
                version='1.0.0',
                description='Python microservice template',
                author='Neural Hive Team',
                tags=['microservice', 'python'],
                language=CodeLanguage.PYTHON,
                type=TemplateType.MICROSERVICE
            ),
            parameters=[],
            content_path='/app/templates',
            examples={}
        )
        context.selected_template = template

        return context

    @pytest.fixture
    def sample_artifact(self, sample_context):
        """Artefato para testes."""
        return CodeForgeArtifact(
            artifact_id=str(uuid.uuid4()),
            ticket_id=sample_context.ticket.ticket_id,
            plan_id=sample_context.ticket.plan_id,
            intent_id=sample_context.ticket.intent_id,
            correlation_id=sample_context.ticket.correlation_id,
            trace_id=sample_context.trace_id,
            span_id=sample_context.span_id,
            artifact_type=ArtifactCategory.CODE,
            language='python',
            template_id='microservice-python-v1',
            confidence_score=0.85,
            generation_method=GenerationMethod.TEMPLATE,
            content_uri='mongodb://artifacts/test',
            content_hash='abc123',
            created_at=datetime.now(),
            metadata={}
        )

    def test_readme_content_structure(self, approval_gate, sample_context, sample_artifact):
        """Testa que o README tem a estrutura esperada."""
        readme = approval_gate._generate_readme(
            sample_context,
            sample_artifact,
            '# Generated code',
            auto_approved=True
        )

        # Verificar secoes principais
        assert '# test-service' in readme
        assert '## Generated by Neural Code Forge' in readme
        assert '## Metadata' in readme
        assert '## Quality Score' in readme
        assert '## Artifacts' in readme

    def test_readme_auto_approved_true(self, approval_gate, sample_context, sample_artifact):
        """Testa README com auto_approved=True."""
        readme = approval_gate._generate_readme(
            sample_context,
            sample_artifact,
            '# Generated code',
            auto_approved=True
        )

        # O formato eh: - **Auto-Approved**: True
        assert '**Auto-Approved**: True' in readme

    def test_readme_auto_approved_false(self, approval_gate, sample_context, sample_artifact):
        """Testa README com auto_approved=False."""
        readme = approval_gate._generate_readme(
            sample_context,
            sample_artifact,
            '# Generated code',
            auto_approved=False
        )

        assert '**Auto-Approved**: False' in readme

    def test_readme_with_none_created_at(self, approval_gate, sample_context):
        """Testa README quando artifact.created_at eh None (usando datetime valido)."""
        # Pydantic v2 nao aceita None para datetime, usar datetime valido
        artifact = CodeForgeArtifact(
            artifact_id=str(uuid.uuid4()),
            ticket_id=sample_context.ticket.ticket_id,
            plan_id=sample_context.ticket.plan_id,
            intent_id=sample_context.ticket.intent_id,
            correlation_id=sample_context.ticket.correlation_id,
            trace_id=sample_context.trace_id,
            span_id=sample_context.span_id,
            artifact_type=ArtifactCategory.CODE,
            language='python',
            template_id='microservice-python-v1',
            confidence_score=0.85,
            generation_method=GenerationMethod.TEMPLATE,
            content_uri='mongodb://artifacts/test',
            content_hash='abc123',
            created_at=datetime.now(),  # Pydantic v2 requer datetime valido
            metadata={}
        )

        readme = approval_gate._generate_readme(
            sample_context,
            artifact,
            '# Generated code',
            auto_approved=True
        )

        # Verificar que a data de criacao esta presente no formato ISO
        assert 'Generated at' in readme

    def test_readme_with_none_template(self, approval_gate, sample_context, sample_artifact):
        """Testa README quando nao ha template selecionado."""
        sample_context.selected_template = None

        readme = approval_gate._generate_readme(
            sample_context,
            sample_artifact,
            '# Generated code',
            auto_approved=True
        )

        assert 'N/A' in readme  # Template deve ser N/A

    def test_readme_custom_service_name(self, approval_gate, sample_context, sample_artifact):
        """Testa README com nome de servico customizado."""
        sample_context.ticket.parameters['service_name'] = 'my-custom-service'
        sample_context.ticket.parameters['description'] = 'My custom description'

        readme = approval_gate._generate_readme(
            sample_context,
            sample_artifact,
            '# Generated code',
            auto_approved=True
        )

        assert '# my-custom-service' in readme
        assert 'My custom description' in readme


class TestCommitAndPushEdgeCases:
    """Testes para edge cases do metodo _commit_and_push."""

    @pytest.fixture
    def approval_gate_with_mongo(self, mock_git_client, mock_mongodb_client):
        """Instancia do ApprovalGate com MongoDB mock."""
        return ApprovalGate(
            git_client=mock_git_client,
            mongodb_client=mock_mongodb_client,
            auto_approval_threshold=0.9,
            min_quality_score=0.5
        )

    @pytest.fixture
    def approval_gate_no_mongo(self, mock_git_client):
        """Instancia do ApprovalGate sem MongoDB."""
        return ApprovalGate(
            git_client=mock_git_client,
            mongodb_client=None,
            auto_approval_threshold=0.9,
            min_quality_score=0.5
        )

    @pytest.fixture
    def sample_context_with_artifact(self):
        """Contexto com artifact para testes."""
        ticket_id = str(uuid.uuid4())
        ticket = ExecutionTicket(
            ticket_id=ticket_id,
            plan_id=f'plan-{ticket_id[:8]}',
            intent_id=f'intent-{ticket_id[:8]}',
            decision_id=f'decision-{ticket_id[:8]}',
            correlation_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            task_type=TaskType.BUILD,
            status=TicketStatus.PENDING,
            priority=Priority.NORMAL,
            risk_band=RiskBand.MEDIUM,
            parameters={
                'service_name': 'test-service',
                'target_repo': 'https://github.com/test/repo'
            },
            sla=SLA(
                deadline=datetime.now(),
                timeout_ms=300000,
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

        context = PipelineContext(
            pipeline_id=str(uuid.uuid4()),
            ticket=ticket,
            trace_id=str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            metadata={}
        )

        # Adicionar artifact
        artifact = CodeForgeArtifact(
            artifact_id=str(uuid.uuid4()),
            ticket_id=ticket_id,
            plan_id=ticket.plan_id,
            intent_id=ticket.intent_id,
            correlation_id=ticket.correlation_id,
            trace_id=context.trace_id,
            span_id=context.span_id,
            artifact_type=ArtifactCategory.CODE,
            language='python',
            template_id='microservice-python-v1',
            confidence_score=0.85,
            generation_method=GenerationMethod.TEMPLATE,
            content_uri='mongodb://artifacts/test',
            content_hash='abc123',
            created_at=datetime.now(),
            metadata={}
        )
        context.add_artifact(artifact)

        return context

    @pytest.mark.asyncio
    async def test_commit_and_push_no_mongodb_client(
        self,
        approval_gate_no_mongo,
        sample_context_with_artifact
    ):
        """Testa _commit_and_push quando mongodb_client eh None."""
        result = await approval_gate_no_mongo._commit_and_push(
            sample_context_with_artifact,
            auto_approved=True
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_commit_and_push_no_artifact(self, approval_gate_no_mongo):
        """Testa _commit_and_push quando nao ha artifact."""
        # Criar contexto sem artifact
        ticket_id = str(uuid.uuid4())
        ticket = ExecutionTicket(
            ticket_id=ticket_id,
            plan_id=f'plan-{ticket_id[:8]}',
            intent_id=f'intent-{ticket_id[:8]}',
            decision_id=f'decision-{ticket_id[:8]}',
            correlation_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            task_type=TaskType.BUILD,
            status=TicketStatus.PENDING,
            priority=Priority.NORMAL,
            risk_band=RiskBand.MEDIUM,
            parameters={'service_name': 'test-service'},
            sla=SLA(
                deadline=datetime.now(),
                timeout_ms=300000,
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

        context = PipelineContext(
            pipeline_id=str(uuid.uuid4()),
            ticket=ticket,
            trace_id=str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            metadata={}
        )

        result = await approval_gate_no_mongo._commit_and_push(
            context,
            auto_approved=True
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_commit_and_push_no_target_repo(
        self,
        approval_gate_with_mongo,
        sample_context_with_artifact
    ):
        """Testa _commit_and_push quando target_repo nao esta definido."""
        # Remover target_repo dos parametros
        sample_context_with_artifact.ticket.parameters.pop('target_repo', None)

        result = await approval_gate_with_mongo._commit_and_push(
            sample_context_with_artifact,
            auto_approved=True
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_commit_and_push_empty_artifact_content(
        self,
        approval_gate_with_mongo,
        sample_context_with_artifact
    ):
        """Testa _commit_and_push quando conteudo do artifact esta vazio."""
        # Mock get_artifact_content retornando None
        approval_gate_with_mongo.mongodb_client.get_artifact_content = AsyncMock(return_value=None)

        result = await approval_gate_with_mongo._commit_and_push(
            sample_context_with_artifact,
            auto_approved=True
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_commit_and_push_artifact_retrieval_exception(
        self,
        approval_gate_with_mongo,
        sample_context_with_artifact
    ):
        """Testa _commit_and_push quando recuperacao do artifact falha."""
        # Mock get_artifact_content lancando excecao
        approval_gate_with_mongo.mongodb_client.get_artifact_content = AsyncMock(
            side_effect=Exception("Database connection failed")
        )

        result = await approval_gate_with_mongo._commit_and_push(
            sample_context_with_artifact,
            auto_approved=True
        )

        assert result is None
        # Verificar que metadata de erro foi adicionado
        assert 'commit_error' in sample_context_with_artifact.metadata


class TestCheckApprovalScenarios:
    """Testes para cenarios especificos de check_approval."""

    @pytest.fixture
    def approval_gate(self, mock_git_client, mock_mongodb_client):
        """Instancia do ApprovalGate para testes."""
        return ApprovalGate(
            git_client=mock_git_client,
            mongodb_client=mock_mongodb_client,
            auto_approval_threshold=0.9,
            min_quality_score=0.5
        )

    @pytest.fixture
    def sample_context(self):
        """Contexto base para testes."""
        ticket_id = str(uuid.uuid4())
        ticket = ExecutionTicket(
            ticket_id=ticket_id,
            plan_id=f'plan-{ticket_id[:8]}',
            intent_id=f'intent-{ticket_id[:8]}',
            decision_id=f'decision-{ticket_id[:8]}',
            correlation_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            task_type=TaskType.BUILD,
            status=TicketStatus.PENDING,
            priority=Priority.NORMAL,
            risk_band=RiskBand.MEDIUM,
            parameters={
                'service_name': 'test-service',
                'target_repo': 'https://github.com/test/repo'
            },
            sla=SLA(
                deadline=datetime.now(),
                timeout_ms=300000,
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

        context = PipelineContext(
            pipeline_id=str(uuid.uuid4()),
            ticket=ticket,
            trace_id=str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            metadata={}
        )

        # Template
        template = Template(
            template_id='microservice-python-v1',
            metadata=TemplateMetadata(
                name='Python Microservice',
                version='1.0.0',
                description='Python microservice template',
                author='Neural Hive Team',
                tags=['microservice', 'python'],
                language=CodeLanguage.PYTHON,
                type=TemplateType.MICROSERVICE
            ),
            parameters=[],
            content_path='/app/templates',
            examples={}
        )
        context.selected_template = template

        return context

    @pytest.fixture
    def context_with_validation(self, sample_context):
        """Contexto com validacao para testar has_critical_issues."""
        from src.models.artifact import ValidationResult, ValidationType, ValidationStatus

        validation = ValidationResult(
            validation_type=ValidationType.SAST,
            tool_name='SonarQube',
            tool_version='10.0.0',
            status=ValidationStatus.PASSED,
            score=0.95,
            issues_count=0,
            critical_issues=0,
            high_issues=0,
            medium_issues=0,
            low_issues=0,
            executed_at=datetime.now(),
            duration_ms=1000
        )
        sample_context.add_validation(validation)

        return sample_context

    @pytest.fixture
    def context_with_critical_issue(self, sample_context):
        """Contexto com issue critico."""
        from src.models.artifact import ValidationResult, ValidationType, ValidationStatus

        validation = ValidationResult(
            validation_type=ValidationType.SAST,
            tool_name='SonarQube',
            tool_version='10.0.0',
            status=ValidationStatus.FAILED,
            score=0.3,
            issues_count=5,
            critical_issues=2,
            high_issues=1,
            medium_issues=1,
            low_issues=1,
            executed_at=datetime.now(),
            duration_ms=2000
        )
        sample_context.add_validation(validation)

        return sample_context

    @pytest.mark.asyncio
    async def test_check_approval_manual_review_without_repo(
        self,
        approval_gate,
        sample_context
    ):
        """Testa check_approval em revisao manual sem target_repo."""
        # Adicionar artifact para satisfazer condicoes
        artifact = CodeForgeArtifact(
            artifact_id=str(uuid.uuid4()),
            ticket_id=sample_context.ticket.ticket_id,
            plan_id=sample_context.ticket.plan_id,
            intent_id=sample_context.ticket.intent_id,
            correlation_id=sample_context.ticket.correlation_id,
            trace_id=sample_context.trace_id,
            span_id=sample_context.span_id,
            artifact_type=ArtifactCategory.CODE,
            language='python',
            template_id='microservice-python-v1',
            confidence_score=0.7,
            generation_method=GenerationMethod.TEMPLATE,
            content_uri='mongodb://artifacts/test',
            content_hash='abc123',
            created_at=datetime.now(),
            metadata={}
        )
        sample_context.add_artifact(artifact)

        # Remover target_repo para forcar manual_no_repo
        sample_context.ticket.parameters.pop('target_repo', None)

        await approval_gate.check_approval(sample_context)

        # Deve ser marcado como manual_no_repo
        assert sample_context.metadata.get('approval') == 'manual_no_repo'

    @pytest.mark.asyncio
    async def test_check_approval_score_below_minimum(
        self,
        approval_gate,
        context_with_critical_issue
    ):
        """Testa check_approval quando score esta abaixo do minimo."""
        # Adicionar artifact
        artifact = CodeForgeArtifact(
            artifact_id=str(uuid.uuid4()),
            ticket_id=context_with_critical_issue.ticket.ticket_id,
            plan_id=context_with_critical_issue.ticket.plan_id,
            intent_id=context_with_critical_issue.ticket.intent_id,
            correlation_id=context_with_critical_issue.ticket.correlation_id,
            trace_id=context_with_critical_issue.trace_id,
            span_id=context_with_critical_issue.span_id,
            artifact_type=ArtifactCategory.CODE,
            language='python',
            template_id='microservice-python-v1',
            confidence_score=0.3,
            generation_method=GenerationMethod.TEMPLATE,
            content_uri='mongodb://artifacts/test',
            content_hash='abc123',
            created_at=datetime.now(),
            metadata={}
        )
        context_with_critical_issue.add_artifact(artifact)

        await approval_gate.check_approval(context_with_critical_issue)

        # Deve ser rejeitado
        assert context_with_critical_issue.metadata.get('approval') == 'rejected'


class TestEdgeCasesWithGenerationMethod:
    """Testes para edge cases relacionados ao GenerationMethod."""

    @pytest.fixture
    def approval_gate(self, mock_git_client, mock_mongodb_client):
        """Instancia do ApprovalGate para testes."""
        return ApprovalGate(
            git_client=mock_git_client,
            mongodb_client=mock_mongodb_client,
            auto_approval_threshold=0.9,
            min_quality_score=0.5
        )

    def test_generate_readme_with_enum_generation_method(self, approval_gate):
        """Testa _generate_readme com GenerationMethod como enum."""
        ticket_id = str(uuid.uuid4())
        ticket = ExecutionTicket(
            ticket_id=ticket_id,
            plan_id=f'plan-{ticket_id[:8]}',
            intent_id=f'intent-{ticket_id[:8]}',
            decision_id=f'decision-{ticket_id[:8]}',
            correlation_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            task_type=TaskType.BUILD,
            status=TicketStatus.PENDING,
            priority=Priority.NORMAL,
            risk_band=RiskBand.MEDIUM,
            parameters={'service_name': 'test-service'},
            sla=SLA(
                deadline=datetime.now(),
                timeout_ms=300000,
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

        context = PipelineContext(
            pipeline_id=str(uuid.uuid4()),
            ticket=ticket,
            trace_id=str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            metadata={}
        )

        artifact = CodeForgeArtifact(
            artifact_id=str(uuid.uuid4()),
            ticket_id=ticket_id,
            plan_id=ticket.plan_id,
            intent_id=ticket.intent_id,
            correlation_id=ticket.correlation_id,
            trace_id=context.trace_id,
            span_id=context.span_id,
            artifact_type=ArtifactCategory.CODE,
            language='python',
            template_id='microservice-python-v1',
            confidence_score=0.85,
            generation_method=GenerationMethod.LLM,  # Enum
            content_uri='mongodb://artifacts/test',
            content_hash='abc123',
            created_at=datetime.now(),
            metadata={}
        )

        readme = approval_gate._generate_readme(
            context,
            artifact,
            '# Generated code',
            auto_approved=True
        )

        # Deve conter o valor do enum
        assert 'Generation Method' in readme
        assert 'LLM' in readme or 'Template' in readme
