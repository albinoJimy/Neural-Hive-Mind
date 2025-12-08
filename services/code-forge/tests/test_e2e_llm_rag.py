"""Teste E2E para geração de código com LLM + RAG"""
import pytest
from unittest.mock import AsyncMock, MagicMock
import sys
import os
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.clients.llm_client import LLMProvider
from src.services.code_composer import CodeComposer
from src.models.artifact import ArtifactType, GenerationMethod


@pytest.fixture
def mock_all_clients():
    """Mock de todos os clientes necessários"""
    llm_mock = AsyncMock()
    llm_mock.provider = LLMProvider.OPENAI  # Adicionar provider
    llm_mock.generate_code = AsyncMock(return_value={
        'code': 'print("Hello")',
        'confidence_score': 0.8,
        'prompt_tokens': 50,
        'completion_tokens': 20
    })

    return {
        'mongodb_client': AsyncMock(),
        'llm_client': llm_mock,
        'analyst_client': AsyncMock(),
        'mcp_client': AsyncMock()
    }


@pytest.fixture
def sample_execution_ticket():
    """Criar execution ticket de exemplo"""
    ticket = MagicMock()
    ticket.ticket_id = str(uuid.uuid4())
    ticket.plan_id = str(uuid.uuid4())
    ticket.intent_id = str(uuid.uuid4())
    ticket.correlation_id = str(uuid.uuid4())
    ticket.parameters = {
        'description': 'Create a Python FastAPI microservice for user management',
        'language': 'python',
        'artifact_type': 'MICROSERVICE',
        'domain': 'TECHNICAL',
        'service_name': 'user-service',
        'requirements': [
            'REST API with CRUD operations',
            'PostgreSQL database',
            'JWT authentication'
        ]
    }
    return ticket


@pytest.fixture
def sample_context(sample_execution_ticket):
    """Criar contexto de pipeline"""
    context = MagicMock()
    context.pipeline_id = 'test-pipeline-123'
    context.ticket = sample_execution_ticket
    context.trace_id = 'trace-123'
    context.span_id = 'span-123'
    context.generation_method = 'LLM'
    context.selected_template = MagicMock()
    context.selected_template.template_id = 'template-123'
    context.selected_template.metadata = MagicMock()
    context.selected_template.metadata.name = 'FastAPI Template'
    context.artifacts = []
    context.add_artifact = lambda artifact: context.artifacts.append(artifact)
    return context


@pytest.mark.asyncio
async def test_e2e_llm_rag_generation(mock_all_clients, sample_context):
    """Testar fluxo E2E completo: ticket → RAG → LLM → artifact"""

    # Configurar mocks
    clients = mock_all_clients

    # Mock Analyst Agents responses
    clients['analyst_client'].get_embedding = AsyncMock(return_value=[0.1] * 768)
    clients['analyst_client'].find_similar_templates = AsyncMock(return_value=[
        {'text': 'FastAPI microservice with PostgreSQL', 'similarity': 0.92},
        {'text': 'Python REST API with JWT auth', 'similarity': 0.88}
    ])
    clients['analyst_client'].get_architectural_patterns = AsyncMock(return_value=[
        'microservices',
        'REST API',
        'layered architecture'
    ])

    # Mock LLM response
    generated_code = '''from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="User Service")

class User(BaseModel):
    id: int
    name: str
    email: str

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/users")
async def list_users():
    return []
'''

    clients['llm_client'].generate_code = AsyncMock(return_value={
        'code': generated_code,
        'confidence_score': 0.88,
        'explanation': 'Generated FastAPI microservice',
        'prompt_tokens': 500,
        'completion_tokens': 300
    })

    # Mock MongoDB save
    clients['mongodb_client'].save_artifact_content = AsyncMock()

    # Criar CodeComposer
    code_composer = CodeComposer(
        clients['mongodb_client'],
        clients['llm_client'],
        clients['analyst_client'],
        clients['mcp_client']
    )

    # Executar composição
    await code_composer.compose(sample_context)

    # Validações
    assert len(sample_context.artifacts) > 0
    artifact = sample_context.artifacts[0]

    # Verificar que Analyst Agents foi chamado
    clients['analyst_client'].find_similar_templates.assert_called_once()
    clients['analyst_client'].get_architectural_patterns.assert_called_once()

    # Verificar que LLM foi chamado
    clients['llm_client'].generate_code.assert_called_once()

    # Verificar que código foi salvo
    clients['mongodb_client'].save_artifact_content.assert_called_once()

    # Verificar artefato gerado
    assert artifact.artifact_type == ArtifactType.CODE
    assert artifact.generation_method == GenerationMethod.LLM
    assert artifact.confidence_score >= 0.8

    print(f"✅ E2E Test Passed: Artifact generated with confidence {artifact.confidence_score}")


@pytest.mark.asyncio
async def test_e2e_fallback_to_heuristic(mock_all_clients, sample_context):
    """Testar fallback para heurística quando LLM falha"""

    clients = mock_all_clients

    # Mock LLM failure
    clients['llm_client'].generate_code = AsyncMock(return_value=None)

    # Mock Analyst Agents
    clients['analyst_client'].get_embedding = AsyncMock(return_value=[0.1] * 768)
    clients['analyst_client'].find_similar_templates = AsyncMock(return_value=[])
    clients['analyst_client'].get_architectural_patterns = AsyncMock(return_value=[])

    # Mock MongoDB
    clients['mongodb_client'].save_artifact_content = AsyncMock()

    # Criar CodeComposer
    code_composer = CodeComposer(
        clients['mongodb_client'],
        clients['llm_client'],
        clients['analyst_client'],
        clients['mcp_client']
    )

    # Executar composição
    await code_composer.compose(sample_context)

    # Validações
    assert len(sample_context.artifacts) > 0
    artifact = sample_context.artifacts[0]

    # Verificar que fallback foi usado - método efetivo deve ser HEURISTIC
    assert artifact.generation_method == GenerationMethod.HEURISTIC
    assert artifact.confidence_score == 0.75  # Confidence de fallback

    print(f"✅ Fallback Test Passed: Used HEURISTIC generation")


@pytest.mark.asyncio
async def test_e2e_no_analyst_client(mock_all_clients, sample_context):
    """Testar geração sem Analyst Client (RAG desabilitado)"""

    clients = mock_all_clients

    # Mock LLM response
    clients['llm_client'].generate_code = AsyncMock(return_value={
        'code': 'print("Hello")',
        'confidence_score': 0.8
    })

    # Mock MongoDB
    clients['mongodb_client'].save_artifact_content = AsyncMock()

    # Criar CodeComposer SEM analyst_client
    code_composer = CodeComposer(
        clients['mongodb_client'],
        clients['llm_client'],
        analyst_client=None,  # RAG desabilitado
        mcp_client=clients['mcp_client']
    )

    # Executar composição
    await code_composer.compose(sample_context)

    # Validações
    assert len(sample_context.artifacts) > 0

    # Verificar que LLM foi chamado mesmo sem RAG
    clients['llm_client'].generate_code.assert_called_once()

    print(f"✅ No RAG Test Passed: Generated code without RAG context")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_e2e_pipeline_engine_complete_flow(mock_all_clients, sample_execution_ticket):
    """Testar fluxo E2E completo usando PipelineEngine: ticket → pipeline → result"""
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

    from src.services.pipeline_engine import PipelineEngine
    from src.services.template_selector import TemplateSelector
    from src.services.code_composer import CodeComposer
    from src.services.validator import Validator
    from src.services.test_runner import TestRunner
    from src.services.packager import Packager
    from src.services.approval_gate import ApprovalGate
    from src.models.artifact import GenerationMethod

    clients = mock_all_clients

    # Mock clientes adicionais necessários
    kafka_producer = AsyncMock()
    ticket_client = AsyncMock()
    postgres_client = AsyncMock()
    git_client = AsyncMock()
    redis_client = AsyncMock()
    sonarqube_client = AsyncMock()
    snyk_client = AsyncMock()
    trivy_client = AsyncMock()
    sigstore_client = AsyncMock()

    # Configurar mocks de Analyst Agents
    clients['analyst_client'].get_embedding = AsyncMock(return_value=[0.1] * 768)
    clients['analyst_client'].find_similar_templates = AsyncMock(return_value=[
        {'text': 'FastAPI microservice with PostgreSQL', 'similarity': 0.92}
    ])
    clients['analyst_client'].get_architectural_patterns = AsyncMock(return_value=[
        'microservices', 'REST API'
    ])

    # Mock LLM response
    generated_code = '''from fastapi import FastAPI

app = FastAPI(title="User Service")

@app.get("/health")
async def health():
    return {"status": "healthy"}
'''

    clients['llm_client'].generate_code = AsyncMock(return_value={
        'code': generated_code,
        'confidence_score': 0.88,
        'explanation': 'Generated FastAPI microservice'
    })

    # Mock MongoDB save
    clients['mongodb_client'].save_artifact_content = AsyncMock()

    # Mock Kafka producer
    kafka_producer.publish_result = AsyncMock()

    # Mock ticket client
    ticket_client.update_status = AsyncMock()

    # Mock postgres
    postgres_client.save_pipeline = AsyncMock()

    # Mock git client para template selector
    from src.models.template import Template, TemplateMetadata
    mock_template = Template(
        template_id='template-123',
        name='FastAPI Microservice Template',
        version='1.0.0',
        category='MICROSERVICE',
        language='python',
        framework='fastapi',
        metadata=TemplateMetadata(
            description='FastAPI microservice template',
            author='Neural Hive Mind',
            tags=['python', 'fastapi', 'microservice']
        ),
        base_path='/templates/fastapi',
        files=[]
    )
    git_client.list_templates = AsyncMock(return_value=[mock_template])
    redis_client.get = AsyncMock(return_value=None)
    redis_client.set = AsyncMock()

    # Mock validation clients
    from src.models.artifact import ValidationResult, ValidationType, ValidationStatus
    from datetime import datetime

    mock_validation_result = ValidationResult(
        validation_type=ValidationType.SAST,
        tool_name='sonarqube',
        tool_version='9.0',
        status=ValidationStatus.PASSED,
        score=0.9,
        issues_count=0,
        critical_issues=0,
        high_issues=0,
        medium_issues=0,
        low_issues=0,
        executed_at=datetime.now(),
        duration_ms=1000
    )

    sonarqube_client.analyze_code = AsyncMock(return_value=mock_validation_result)
    snyk_client.scan_dependencies = AsyncMock(return_value=mock_validation_result)
    trivy_client.scan_filesystem = AsyncMock(return_value=mock_validation_result)

    # Mock test runner
    from src.models.test_result import TestResult, TestStatus
    mock_test_result = TestResult(
        test_suite='unit_tests',
        status=TestStatus.PASSED,
        total_tests=10,
        passed=10,
        failed=0,
        skipped=0,
        coverage=0.85,
        duration_ms=2000,
        executed_at=datetime.now()
    )

    # Mock packager
    sigstore_client.sign_artifact = AsyncMock(return_value='mock-signature')

    # Criar subpipelines
    template_selector = TemplateSelector(git_client, redis_client, clients['mcp_client'])
    code_composer = CodeComposer(
        clients['mongodb_client'],
        clients['llm_client'],
        clients['analyst_client'],
        clients['mcp_client']
    )
    validator = Validator(sonarqube_client, snyk_client, trivy_client, clients['mcp_client'])
    test_runner = TestRunner(min_coverage=0.7)
    packager = Packager(sigstore_client)
    approval_gate = ApprovalGate(git_client, auto_approval_threshold=0.9, min_quality_score=0.5)

    # Mock test runner methods
    test_runner.run_tests = AsyncMock()
    test_runner.run_tests.return_value = None  # Adiciona resultado ao contexto internamente

    # Mock packager methods
    packager.package = AsyncMock()

    # Mock approval gate methods
    approval_gate.check_approval = AsyncMock()

    # Criar PipelineEngine
    pipeline_engine = PipelineEngine(
        template_selector,
        code_composer,
        validator,
        test_runner,
        packager,
        approval_gate,
        kafka_producer,
        ticket_client,
        postgres_client,
        clients['mongodb_client'],
        max_concurrent=3,
        pipeline_timeout=3600,
        auto_approval_threshold=0.9,
        min_quality_score=0.5
    )

    # Preparar ticket com generation_method = LLM
    sample_execution_ticket.parameters['generation_method'] = 'LLM'

    # Executar pipeline completo
    result = await pipeline_engine.execute_pipeline(sample_execution_ticket)

    # Validações
    assert result is not None
    assert result.pipeline_id is not None
    assert result.ticket_id == sample_execution_ticket.ticket_id

    # Verificar que template foi selecionado
    git_client.list_templates.assert_called_once()

    # Verificar que Analyst Agents foi chamado
    clients['analyst_client'].get_embedding.assert_called_once()
    clients['analyst_client'].find_similar_templates.assert_called_once()
    clients['analyst_client'].get_architectural_patterns.assert_called_once()

    # Verificar que LLM foi chamado
    clients['llm_client'].generate_code.assert_called_once()

    # Verificar que código foi salvo
    clients['mongodb_client'].save_artifact_content.assert_called_once()

    # Verificar que validações foram executadas
    sonarqube_client.analyze_code.assert_called_once()
    snyk_client.scan_dependencies.assert_called_once()
    trivy_client.scan_filesystem.assert_called_once()

    # Verificar que pipeline result foi salvo
    postgres_client.save_pipeline.assert_called_once()

    # Verificar que resultado foi publicado
    kafka_producer.publish_result.assert_called_once()

    # Verificar que ticket foi atualizado
    assert ticket_client.update_status.call_count >= 1

    # Verificar artefatos gerados
    assert len(result.artifacts) > 0
    artifact = result.artifacts[0]
    assert artifact.generation_method == GenerationMethod.LLM
    assert artifact.confidence_score >= 0.8

    # Verificar stages do pipeline
    assert len(result.pipeline_stages) == 6
    stage_names = [s.stage_name for s in result.pipeline_stages]
    assert 'template_selection' in stage_names
    assert 'code_composition' in stage_names
    assert 'validation' in stage_names
    assert 'testing' in stage_names
    assert 'packaging' in stage_names
    assert 'approval_gate' in stage_names

    print(f"✅ Pipeline E2E Test Passed: Full flow executed successfully")
    print(f"   Pipeline ID: {result.pipeline_id}")
    print(f"   Status: {result.status}")
    print(f"   Artifacts: {len(result.artifacts)}")
    print(f"   Duration: {result.total_duration_ms}ms")
