# Software Engineering Pipeline - Plano de Implementação

> **Para trabalhadores agentes:** SUB-SKILL OBRIGATÓRIO: Use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans para implementar este plano tarefa por tarefa. Etapas usam sintaxe checkbox (`- [ ]`) para rastreamento.

**Objetivo:** Sistema completo de CI/CD com geração automática de pipelines, orquestração de deploys e inteligência para detecção de anomalias

**Arquitetura:** Microserviço FastAPI com 3 componentes principais (Generator, Orchestrator, Intelligence), integração com GitHub/GitLab/Jenkins, GitOps via ArgoCD/Flux CD, e persistência MongoDB

**Tech Stack:** Python 3.12+, FastAPI, Pydantic, Motor (MongoDB async), PyGitHub, python-gitlab, prometheus-client, python-kubernetes, Docker, Helm

---

## Task 1: Estrutura Base do Serviço

**Arquivos:**
- Criar: `services/software-engineering-pipeline/src/main.py`
- Criar: `services/software-engineering-pipeline/src/config/settings.py`
- Criar: `services/software-engineering-pipeline/Dockerfile`
- Criar: `services/software-engineering-pipeline/requirements.txt`

- [ ] **Step 1: Criar requirements.txt**

```txt
fastapi==0.115.0
uvicorn[standard]==0.32.0
pydantic==2.10.0
pydantic-settings==2.6.0
motor==3.6.0
pymongo==4.10.0
aiokafka==0.12.0
structlog==24.4.0
prometheus-client==0.21.0
opentelemetry-api==1.27.0
opentelemetry-sdk==1.27.0
opentelemetry-instrumentation-fastapi==0.48b0
PyGithub==2.4.0
python-gitlab==4.12.0
kubernetes==31.0.0
pyyaml==6.0.2
jinja2==3.1.4
httpx==0.28.0
tenacity==9.0.0
pytest==8.3.0
pytest-asyncio==0.24.0
pytest-cov==6.0.0
ruff==0.8.0
black==24.10.0
```

- [ ] **Step 2: Criar settings.py**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
    )

    # API
    app_name: str = 'software-engineering-pipeline'
    app_version: str = '1.0.0'
    api_host: str = '0.0.0.0'
    api_port: int = 8008
    debug: bool = False

    # MongoDB
    mongodb_url: str = 'mongodb://localhost:27017'
    mongodb_db_name: str = 'pipeline_db'

    # Kafka
    kafka_bootstrap_servers: str = 'localhost:9092'
    kafka_group_id: str = 'pipeline-service'

    # GitHub
    github_token: str = ''
    github_app_id: str | None = None
    github_app_private_key: str | None = None

    # GitLab
    gitlab_token: str = ''
    gitlab_url: str = 'https://gitlab.com'

    # Jenkins
    jenkins_url: str = ''
    jenkins_username: str = ''
    jenkins_password: str = ''

    # ArgoCD
    argocd_url: str = ''
    argocd_token: str = ''
    argocd_namespace: str = 'argocd'

    # Flux CD
    flux_namespace: str = 'flux-system'
    flux_kubeconfig: str = '~/.kube/config'

    # Docker Registry
    docker_registry: str = 'ghcr.io'
    docker_registry_username: str = ''
    docker_registry_password: str = ''

    # Intelligence
    anomaly_detection_enabled: bool = True
    anomaly_threshold: float = 0.7
    flaky_test_threshold: int = 3
    pipeline_insights_retention_days: int = 90

    # Orchestration
    default_timeout_minutes: int = 60
    max_retries: int = 3
    rollback_on_health_check_failure: bool = True
    rollback_on_metrics_degradation: bool = True


settings = Settings()
```

- [ ] **Step 3: Criar main.py**

```python
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from prometheus_client import make_asgi_app

from src.config.settings import settings
from src.api.router import api_router


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt='iso'),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def configure_tracing() -> None:
    provider = TracerProvider()
    processor = BatchSpanProcessor(
        OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
    )
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url='/api/docs',
        redoc_url='/api/redoc',
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    app.include_router(api_router, prefix='/api/v1')

    # Prometheus metrics endpoint
    metrics_app = make_asgi_app()
    app.mount('/metrics', metrics_app)

    return app


configure_logging()
if settings.otel_exporter_otlp_endpoint:
    configure_tracing()

app = create_app()
logger = structlog.get_logger()


@app.on_event('startup')
async def startup_event() -> None:
    logger.info('software_engineering_pipeline_starting', port=settings.api_port)


@app.on_event('shutdown')
async def shutdown_event() -> None:
    logger.info('software_engineering_pipeline_shutting_down')


@app.get('/health')
async def health_check() -> dict[str, str]:
    return {'status': 'healthy', 'service': settings.app_name}
```

- [ ] **Step 4: Criar Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --upgrade pip

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src/ src/

EXPOSE 8008

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8008"]
```

- [ ] **Step 5: Commit inicial**

```bash
git add services/software-engineering-pipeline/
git commit -m "feat(pipeline): cria estrutura base do software-engineering-pipeline"
```

---

## Task 2: Modelos de Dados e Schemas

**Arquivos:**
- Criar: `services/software-engineering-pipeline/src/models/schemas.py`
- Criar: `services/software-engineering-pipeline/src/models/pipeline.py`
- Test: `services/software-engineering-pipeline/tests/unit/test_models.py`

- [ ] **Step 1: Criar schemas.py (enums e modelos base)**

```python
from enum import Enum
from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime


class PipelineProvider(str, Enum):
    GITHUB_ACTIONS = 'github_actions'
    GITLAB_CI = 'gitlab_ci'
    JENKINS = 'jenkins'
    TEKTON = 'tekton'


class GitOpsProvider(str, Enum):
    ARGOCD = 'argocd'
    FLUX_CD = 'flux_cd'
    KUBECTL = 'kubectl'


class PipelineStatus(str, Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    SUCCESS = 'success'
    FAILED = 'failed'
    CANCELLED = 'cancelled'
    ROLLED_BACK = 'rolled_back'


class PipelineStage(str, Enum):
    PRE_FLIGHT = 'pre_flight'
    BUILD = 'build'
    TEST = 'test'
    SECURITY = 'security'
    STAGING = 'staging'
    APPROVAL = 'approval'
    PRODUCTION = 'production'


class Severity(str, Enum):
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    CRITICAL = 'critical'


class ProjectStack(BaseModel):
    language: str
    framework: str | None = None
    package_manager: str
    has_dockerfile: bool = False
    has_docker_compose: bool = False
    has_helm_chart: bool = False
    kubernetes_manifests: bool = False


class Component(BaseModel):
    name: str
    image: str
    replicas: int = 1
    port: int | None = None
    env_vars: dict[str, str] = Field(default_factory=dict)


class AnomalyType(str, Enum):
    FLAKY_TEST = 'flaky_test'
    DEPENDENCY_ISSUE = 'dependency_issue'
    PERFORMANCE_DEGRADATION = 'performance_degradation'
    SECURITY_VULNERABILITY = 'security_vulnerability'
    CONFIGURATION_DRIFT = 'configuration_drift'
```

- [ ] **Step 2: Criar pipeline.py (modelos principais)**

```python
from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime
from .schemas import (
    PipelineProvider,
    PipelineStatus,
    PipelineStage,
    GitOpsProvider,
    Severity,
    AnomalyType,
)


class PipelineManifest(BaseModel):
    manifest_id: str
    repo_url: str
    branch: str
    provider: PipelineProvider
    content: str  # YAML do pipeline gerado
    stack: dict[str, str]
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PipelineRun(BaseModel):
    run_id: str
    manifest_id: str
    repo_url: str
    git_sha: str
    status: PipelineStatus = PipelineStatus.PENDING
    current_stage: PipelineStage | None = None
    stages_completed: list[PipelineStage] = Field(default_factory=list)
    stages_failed: list[PipelineStage] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
    duration_seconds: int | None = None
    logs_url: str | None = None
    rollback_reason: str | None = None
    rollback_run_id: str | None = None


class DeployRequest(BaseModel):
    repo_url: str
    git_sha: str
    branch: str = 'main'
    environment: Literal['staging', 'production']
    provider: PipelineProvider = PipelineProvider.GITHUB_ACTIONS
    gitops_provider: GitOpsProvider | None = None
    timeout_minutes: int = 60


class DeployResponse(BaseModel):
    run_id: str
    status: PipelineStatus
    message: str


class RollbackRequest(BaseModel):
    run_id: str
    reason: str
    force: bool = False


class Anomaly(BaseModel):
    anomaly_id: str
    repo_url: str
    run_id: str | None = None
    type: AnomalyType
    severity: Severity
    description: str
    affected_component: str | None = None
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    resolved: bool = False
    resolved_at: datetime | None = None
    suggested_action: str | None = None


class Insight(BaseModel):
    insight_id: str
    repo_url: str
    insight_type: Literal[
        'flaky_test',
        'slow_test',
        'dependency_issue',
        'cache_opportunity',
        'parallelization_opportunity',
        'security_issue',
    ]
    title: str
    description: str
    impact: Severity
    effort: Literal['S', 'M', 'L']
    created_at: datetime = Field(default_factory=datetime.utcnow)


class InsightsReport(BaseModel):
    repo_url: str
    timeframe_start: datetime
    timeframe_end: datetime
    total_runs: int
    success_rate: float
    average_duration_seconds: float
    flaky_tests: list[Insight]
    slow_tests: list[Insight]
    optimization_opportunities: list[Insight]
    security_issues: list[Insight]
```

- [ ] **Step 3: Escrever testes dos modelos**

```python
import pytest
from datetime import datetime
from src.models.schemas import PipelineProvider, PipelineStatus
from src.models.pipeline import PipelineRun, DeployRequest


def test_pipeline_run_creation():
    run = PipelineRun(
        run_id='run-123',
        manifest_id='manifest-456',
        repo_url='https://github.com/org/repo',
        git_sha='abc123',
    )
    assert run.run_id == 'run-123'
    assert run.status == PipelineStatus.PENDING
    assert run.current_stage is None
    assert run.stages_completed == []


def test_deploy_request_validation():
    request = DeployRequest(
        repo_url='https://github.com/org/repo',
        git_sha='abc123',
        environment='staging',
    )
    assert request.environment == 'staging'
    assert request.branch == 'main'
    assert request.provider == PipelineProvider.GITHUB_ACTIONS


def test_deploy_request_invalid_environment():
    with pytest.raises(ValueError):
        DeployRequest(
            repo_url='https://github.com/org/repo',
            git_sha='abc123',
            environment='invalid',
        )


def test_pipeline_run_stage_progression():
    run = PipelineRun(
        run_id='run-123',
        manifest_id='manifest-456',
        repo_url='https://github.com/org/repo',
        git_sha='abc123',
    )
    run.stages_completed.append(PipelineStage.BUILD)
    run.current_stage = PipelineStage.TEST
    run.status = PipelineStatus.RUNNING

    assert len(run.stages_completed) == 1
    assert run.current_stage == PipelineStage.TEST
    assert run.status == PipelineStatus.RUNNING


def test_rollback_request():
    from src.models.pipeline import RollbackRequest

    request = RollbackRequest(
        run_id='run-123',
        reason='Health check failed',
    )
    assert request.run_id == 'run-123'
    assert request.reason == 'Health check failed'
    assert request.force is False
```

- [ ] **Step 4: Executar testes**

```bash
cd services/software-engineering-pipeline
pytest tests/unit/test_models.py -v
```

- [ ] **Step 5: Commit**

```bash
git add services/software-engineering-pipeline/src/models/ \
        services/software-engineering-pipeline/tests/unit/test_models.py
git commit -m "feat(pipeline): adiciona modelos de dados e schemas"
```

---

## Task 3: Pipeline Generator - Detecção de Stack e Geração

**Arquivos:**
- Criar: `services/software-engineering-pipeline/src/generators/base.py`
- Criar: `services/software-engineering-pipeline/src/generators/stack_detector.py`
- Criar: `services/software-engineering-pipeline/src/generators/github_actions.py`
- Test: `services/software-engineering-pipeline/tests/unit/test_stack_detector.py`

- [ ] **Step 1: Criar base.py (classe abstrata)**

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel


class GeneratedPipeline(BaseModel):
    content: str
    filename: str
    description: str


class BasePipelineGenerator(ABC):
    """Base class for all CI/CD pipeline generators."""

    @abstractmethod
    async def generate(self, config: dict) -> GeneratedPipeline:
        """Generate a pipeline configuration."""
        pass

    @abstractmethod
    def get_filename(self) -> str:
        """Return the standard filename for this pipeline type."""
        pass
```

- [ ] **Step 2: Criar stack_detector.py**

```python
import re
from typing import Literal
from pydantic import BaseModel
from src.models.schemas import ProjectStack


class StackDetectionResult(BaseModel):
    detected: bool
    stack: ProjectStack
    confidence: float  # 0.0 to 1.0


class StackDetector:
    """Detects the technology stack from repository files."""

    PYTHON_INDICATORS = [
        (r'requirements\.txt', 1.0),
        (r'pyproject\.toml', 1.0),
        (r'setup\.py', 0.9),
        (r'Pipfile', 0.8),
        (r'\.py$', 0.5),
    ]

    NODE_INDICATORS = [
        (r'package\.json', 1.0),
        (r'yarn\.lock', 0.9),
        (r'package-lock\.json', 0.9),
        (r'\.js$', 0.3),
        (r'\.ts$', 0.3),
        (r'\.jsx$', 0.3),
        (r'\.tsx$', 0.3),
    ]

    JAVA_INDICATORS = [
        (r'pom\.xml', 1.0),
        (r'build\.gradle', 1.0),
        (r'\.java$', 0.5),
    ]

    GO_INDICATORS = [
        (r'go\.mod', 1.0),
        (r'go\.sum', 0.9),
        (r'\.go$', 0.5),
    ]

    DOCKER_INDICATORS = [
        (r'Dockerfile', 1.0),
        (r'\.dockerignore', 0.5),
    ]

    K8S_INDICATORS = [
        (r'depployment\.yaml', 0.9),
        (r'service\.yaml', 0.9),
        (r'helm/', 1.0),
        (r'k8s/', 0.9),
        (r'kubernetes/', 0.9),
    ]

    PACKAGE_MANAGER_MAP = {
        'python': ['pip', 'poetry', 'pipenv'],
        'node': ['npm', 'yarn', 'pnpm'],
        'java': ['maven', 'gradle'],
        'go': ['go modules'],
    }

    FRAMEWORK_PATTERNS = {
        'python': [
            (r'fastapi', 'fastapi'),
            (r'django', 'django'),
            (r'flask', 'flask'),
            (r'tornado', 'tornado'),
        ],
        'node': [
            (r'react', 'react'),
            (r'next', 'next.js'),
            (r'vue', 'vue'),
            (r'express', 'express'),
            (r'nest', 'nestjs'),
        ],
    }

    def __init__(self, file_list: list[str], file_contents: dict[str, str] | None = None):
        self.file_list = file_list
        self.file_contents = file_contents or {}

    def detect(self) -> StackDetectionResult:
        """Detect the project stack from available files."""
        language, lang_confidence = self._detect_language()
        framework = self._detect_framework(language)

        has_dockerfile = any(re.search(p, f, re.IGNORECASE)
                           for f in self.file_list
                           for p, _ in self.DOCKER_INDICATORS)

        has_docker_compose = any('docker-compose' in f.lower()
                                for f in self.file_list)

        has_helm_chart = any('helm' in f.lower() or 'Chart.yaml' in f
                            for f in self.file_list)

        kubernetes_manifests = any(
            any(re.search(p, f, re.IGNORECASE) for p, _ in self.K8S_INDICATORS)
            for f in self.file_list
        )

        stack = ProjectStack(
            language=language,
            framework=framework,
            package_manager=self._infer_package_manager(language),
            has_dockerfile=has_dockerfile,
            has_docker_compose=has_docker_compose,
            has_helm_chart=has_helm_chart,
            kubernetes_manifests=kubernetes_manifests,
        )

        return StackDetectionResult(
            detected=lang_confidence > 0.5,
            stack=stack,
            confidence=lang_confidence,
        )

    def _detect_language(self) -> tuple[str, float]:
        scores = {
            'python': self._score_indicators(self.PYTHON_INDICATORS),
            'node': self._score_indicators(self.NODE_INDICATORS),
            'java': self._score_indicators(self.JAVA_INDICATORS),
            'go': self._score_indicators(self.GO_INDICATORS),
        }

        top_language = max(scores, key=scores.get)
        return top_language, scores[top_language]

    def _score_indicators(self, indicators: list[tuple[str, float]]) -> float:
        total_score = 0.0
        for pattern, weight in indicators:
            for filename in self.file_list:
                if re.search(pattern, filename, re.IGNORECASE):
                    total_score += weight
        return min(total_score, 1.0)

    def _detect_framework(self, language: str) -> str | None:
        if language not in self.FRAMEWORK_PATTERNS:
            return None

        patterns = self.FRAMEWORK_PATTERNS[language]

        # Check in file names first
        for pattern, framework in patterns:
            for filename in self.file_list:
                if re.search(pattern, filename, re.IGNORECASE):
                    return framework

        # Check in package.json or requirements.txt if available
        if language == 'node' and 'package.json' in self.file_list:
            content = self.file_contents.get('package.json', '')
            for pattern, framework in patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    return framework

        if language == 'python':
            for filename in ['requirements.txt', 'pyproject.toml']:
                if filename in self.file_list:
                    content = self.file_contents.get(filename, '')
                    for pattern, framework in patterns:
                        if re.search(pattern, content, re.IGNORECASE):
                            return framework

        return None

    def _infer_package_manager(self, language: str) -> str:
        managers = {
            'python': 'pip',
            'node': 'npm',
            'java': 'maven',
            'go': 'go',
        }
        return managers.get(language, 'unknown')
```

- [ ] **Step 3: Criar github_actions.py**

```python
from jinja2 import Template
from src.generators.base import BasePipelineGenerator, GeneratedPipeline
from src.models.schemas import ProjectStack, PipelineStage


GITHUB_ACTIONS_TEMPLATE = """
name: {{ pipeline_name }}

on:
  push:
    branches: [main, staging, develop]
  pull_request:
    branches: [main, staging]

env:
  REGISTRY: {{ docker_registry }}
  IMAGE_NAME: {{ image_name }}

jobs:
{% if stages.pre_flight %}
  pre-flight:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Validate configuration
        run: |
          echo "Validating configuration..."
          # Add validation commands here

{% endif %}
{% if stages.build %}
  build:
    runs-on: ubuntu-latest
    {% if stages.test %}needs: pre-flight{% endif %}
    outputs:
      image-tag: ${{ steps.meta.outputs.tags }}
      image-digest: ${{ steps.build.outputs.digest }}
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ secrets.DOCKER_USERNAME }}
          password: ${{ secrets.DOCKER_PASSWORD }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=ref,event=branch
            type=sha,prefix={{ branch }}-
            type=semver,pattern={{version}}

      - name: Build and push
        id: build
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          {% if sbom %}sbom: true{% endif %}

{% endif %}
{% if stages.test %}
  test:
    runs-on: ubuntu-latest
    needs: build
    strategy:
      matrix:
        python-version: {{ python_versions | default(['3.11', '3.12']) }}
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          pip install -e ".[test]"
      - name: Run tests
        run: |
          pytest --cov=src --cov-report=xml --cov-report=term

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage.xml

{% endif %}
{% if stages.security %}
  security:
    runs-on: ubuntu-latest
    needs: build
    steps:
      - uses: actions/checkout@v4

      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: ${{ needs.build.outputs.image-tag }}
          format: 'sarif'
          output: 'trivy-results.sarif'

      - name: Upload Trivy results
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: 'trivy-results.sarif'

{% endif %}
{% if stages.staging %}
  staging:
    runs-on: ubuntu-latest
    needs: [build, test, security]
    if: github.ref == 'refs/heads/staging'
    environment:
      name: staging
      url: ${{ steps.deploy.outputs.url }}
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to staging
        id: deploy
        run: |
          echo "Deploying ${{ needs.build.outputs.image-tag }} to staging..."
          # Add deployment commands here

{% endif %}
{% if stages.production %}
  production:
    runs-on: ubuntu-latest
    needs: [build, test, security]
    if: github.ref == 'refs/heads/main'
    environment:
      name: production
      url: ${{ steps.deploy.outputs.url }}
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to production
        id: deploy
        run: |
          echo "Deploying ${{ needs.build.outputs.image-tag }} to production..."
          # Add deployment commands here

      - name: Health check
        run: |
          # Add health check logic
          echo "Checking deployment health..."

{% endif %}
"""


class GitHubActionsGenerator(BasePipelineGenerator):
    """Generates GitHub Actions workflow files."""

    def __init__(
        self,
        pipeline_name: str = 'CI/CD Pipeline',
        docker_registry: str = 'ghcr.io',
        image_name: str = 'myapp',
        branch: str = 'main',
        sbom: bool = True,
    ):
        self.pipeline_name = pipeline_name
        self.docker_registry = docker_registry
        self.image_name = image_name
        self.branch = branch
        self.sbom = sbom

    async def generate(self, config: dict) -> GeneratedPipeline:
        """Generate GitHub Actions workflow YAML."""
        stack: ProjectStack = config.get('stack')
        stages = config.get('stages', {})

        template = Template(GITHUB_ACTIONS_TEMPLATE, trim_blocks=True, lstrip_blocks=True)

        content = template.render(
            pipeline_name=self.pipeline_name,
            docker_registry=self.docker_registry,
            image_name=self.image_name,
            branch=self.branch,
            sbom=self.sbom,
            stages=self._get_stage_config(stages, stack),
            python_versions=['3.11', '3.12'] if stack.language == 'python' else None,
        )

        return GeneratedPipeline(
            content=content.strip(),
            filename=self.get_filename(),
            description=f'GitHub Actions workflow for {self.pipeline_name}',
        )

    def _get_stage_config(self, stages: dict, stack: ProjectStack) -> dict:
        return {
            'pre_flight': stages.get('pre_flight', True),
            'build': stages.get('build', True),
            'test': stages.get('test', stack.language in ['python', 'node', 'java']),
            'security': stages.get('security', True),
            'staging': stages.get('staging', True),
            'production': stages.get('production', True),
        }

    def get_filename(self) -> str:
        return '.github/workflows/ci-cd.yml'
```

- [ ] **Step 4: Escrever testes do StackDetector**

```python
import pytest
from src.generators.stack_detector import StackDetector, StackDetectionResult
from src.models.schemas import ProjectStack


def test_detect_python_project():
    files = [
        'requirements.txt',
        'src/main.py',
        'tests/test_main.py',
        'Dockerfile',
    ]
    detector = StackDetector(files)
    result = detector.detect()

    assert result.detected
    assert result.stack.language == 'python'
    assert result.confidence > 0.8
    assert result.stack.has_dockerfile


def test_detect_node_project():
    files = [
        'package.json',
        'package-lock.json',
        'src/index.ts',
        'tsconfig.json',
    ]
    detector = StackDetector(files)
    result = detector.detect()

    assert result.detected
    assert result.stack.language == 'node'
    assert result.stack.package_manager == 'npm'


def test_detect_go_project():
    files = [
        'go.mod',
        'go.sum',
        'main.go',
    ]
    detector = StackDetector(files)
    result = detector.detect()

    assert result.detected
    assert result.stack.language == 'go'


def test_detect_kubernetes_manifests():
    files = [
        'requirements.txt',
        'k8s/deployment.yaml',
        'k8s/service.yaml',
    ]
    detector = StackDetector(files)
    result = detector.detect()

    assert result.stack.kubernetes_manifests


def test_detect_helm_chart():
    files = [
        'helm/Chart.yaml',
        'helm/values.yaml',
    ]
    detector = StackDetector(files)
    result = detector.detect()

    assert result.stack.has_helm_chart


def test_low_confidence_detection():
    files = [
        'README.md',
        'LICENSE',
        '.gitignore',
    ]
    detector = StackDetector(files)
    result = detector.detect()

    assert not result.detected
    assert result.confidence < 0.5


def test_detect_framework_with_requirements():
    files = ['requirements.txt']
    contents = {
        'requirements.txt': 'fastapi==0.115.0\nuvicorn[standard]==0.32.0',
    }
    detector = StackDetector(files, file_contents=contents)
    result = detector.detect()

    assert result.stack.framework == 'fastapi'


def test_detect_framework_with_package_json():
    files = ['package.json']
    contents = {
        'package.json': '{"dependencies": {"next": "^14.0.0"}}',
    }
    detector = StackDetector(files, file_contents=contents)
    result = detector.detect()

    assert result.stack.framework == 'next.js'
```

- [ ] **Step 5: Executar testes**

```bash
cd services/software-engineering-pipeline
pytest tests/unit/test_stack_detector.py -v
```

- [ ] **Step 6: Commit**

```bash
git add services/software-engineering-pipeline/src/generators/ \
        services/software-engineering-pipeline/tests/unit/test_stack_detector.py
git commit -m "feat(pipeline): adiciona detector de stack e gerador GitHub Actions"
```

---

## Task 4: Pipeline Orchestrator - Fluxo de Deploy

**Arquivos:**
- Criar: `services/software-engineering-pipeline/src/orchestrators/pipeline_orchestrator.py`
- Criar: `services/software-engineering-pipeline/src/orchestrators/stages.py`
- Test: `services/software-engineering-pipeline/tests/unit/test_orchestrator.py`

- [ ] **Step 1: Criar stages.py (definição dos estágios)**

```python
from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel
from structlog import get_logger

from src.models.pipeline import PipelineRun
from src.models.schemas import PipelineStage


class StageResult(BaseModel):
    stage: PipelineStage
    success: bool
    message: str
    duration_seconds: int
    metadata: dict[str, Any] = {}


class PipelineStage(ABC):
    """Base class for all pipeline stages."""

    def __init__(self, timeout_seconds: int = 3600):
        self.timeout_seconds = timeout_seconds
        self.logger = get_logger()

    @abstractmethod
    async def execute(self, run: PipelineRun, context: dict) -> StageResult:
        """Execute the stage logic."""
        pass

    @abstractmethod
    def get_name(self) -> PipelineStage:
        """Return the stage enum value."""
        pass


class PreFlightStage(PipelineStage):
    """Validates prerequisites before running the pipeline."""

    def get_name(self) -> PipelineStage:
        return PipelineStage.PRE_FLIGHT

    async def execute(self, run: PipelineRun, context: dict) -> StageResult:
        self.logger.info('preflight_stage_starting', run_id=run.run_id)

        checks = context.get('preflight_checks', {})

        # Validate required secrets
        if not checks.get('has_secrets', True):
            return StageResult(
                stage=self.get_name(),
                success=False,
                message='Required secrets not configured',
                duration_seconds=0,
            )

        # Validate version format
        version = checks.get('version', '')
        if not version or not version.replace('.', '').isdigit():
            return StageResult(
                stage=self.get_name(),
                success=False,
                message=f'Invalid version format: {version}',
                duration_seconds=0,
            )

        self.logger.info('preflight_stage_complete', run_id=run.run_id)
        return StageResult(
            stage=self.get_name(),
            success=True,
            message='Pre-flight checks passed',
            duration_seconds=0,
        )


class BuildStage(PipelineStage):
    """Builds container images and generates SBOM."""

    def get_name(self) -> PipelineStage:
        return PipelineStage.BUILD

    async def execute(self, run: PipelineRun, context: dict) -> StageResult:
        self.logger.info('build_stage_starting', run_id=run.run_id)

        # This would delegate to the actual CI platform (GitHub Actions, etc.)
        # For now, we simulate the result
        build_info = context.get('build_info', {})

        self.logger.info('build_stage_complete', run_id=run.run_id)
        return StageResult(
            stage=self.get_name(),
            success=True,
            message=f'Built image {build_info.get("image", "unknown")}',
            duration_seconds=build_info.get('duration', 120),
            metadata={'image': build_info.get('image', ''), 'digest': build_info.get('digest', '')},
        )


class TestStage(PipelineStage):
    """Runs unit and integration tests."""

    def get_name(self) -> PipelineStage:
        return PipelineStage.TEST

    async def execute(self, run: PipelineRun, context: dict) -> StageResult:
        self.logger.info('test_stage_starting', run_id=run.run_id)

        test_results = context.get('test_results', {})

        success = test_results.get('passed', 0) == test_results.get('total', 0)
        message = f'{test_results.get("passed", 0)}/{test_results.get("total", 0)} tests passed'

        self.logger.info('test_stage_complete', run_id=run.run_id, success=success)
        return StageResult(
            stage=self.get_name(),
            success=success,
            message=message,
            duration_seconds=test_results.get('duration', 60),
            metadata=test_results,
        )


class SecurityStage(PipelineStage):
    """Runs security scans (SAST, SCA, container scanning)."""

    def get_name(self) -> PipelineStage:
        return PipelineStage.SECURITY

    async def execute(self, run: PipelineRun, context: dict) -> StageResult:
        self.logger.info('security_stage_starting', run_id=run.run_id)

        scan_results = context.get('security_scan', {})

        critical_vulns = scan_results.get('critical', 0)
        high_vulns = scan_results.get('high', 0)

        success = critical_vulns == 0
        message = f'Found {critical_vulns} critical, {high_vulns} high vulnerabilities'

        self.logger.info('security_stage_complete', run_id=run.run_id, success=success)
        return StageResult(
            stage=self.get_name(),
            success=success,
            message=message,
            duration_seconds=scan_results.get('duration', 30),
            metadata=scan_results,
        )


class StagingStage(PipelineStage):
    """Deploys to staging environment."""

    def get_name(self) -> PipelineStage:
        return PipelineStage.STAGING

    async def execute(self, run: PipelineRun, context: dict) -> StageResult:
        self.logger.info('staging_stage_starting', run_id=run.run_id)

        deploy_info = context.get('staging_deploy', {})

        self.logger.info('staging_stage_complete', run_id=run.run_id)
        return StageResult(
            stage=self.get_name(),
            success=True,
            message=f'Deployed to staging: {deploy_info.get("url", "unknown")}',
            duration_seconds=deploy_info.get('duration', 90),
            metadata={'url': deploy_info.get('url', '')},
        )


class ApprovalStage(PipelineStage):
    """Waits for manual approval."""

    def get_name(self) -> PipelineStage:
        return PipelineStage.APPROVAL

    async def execute(self, run: PipelineRun, context: dict) -> StageResult:
        self.logger.info('approval_stage_waiting', run_id=run.run_id)

        # Check if approval was granted
        approved = context.get('approved', False)

        message = 'Approval granted' if approved else 'Awaiting approval'
        self.logger.info('approval_stage_complete', run_id=run.run_id, approved=approved)

        return StageResult(
            stage=self.get_name(),
            success=approved,
            message=message,
            duration_seconds=0,
        )


class ProductionStage(PipelineStage):
    """Deploys to production environment."""

    def get_name(self) -> PipelineStage:
        return PipelineStage.PRODUCTION

    async def execute(self, run: PipelineRun, context: dict) -> StageResult:
        self.logger.info('production_stage_starting', run_id=run.run_id)

        deploy_info = context.get('production_deploy', {})

        self.logger.info('production_stage_complete', run_id=run.run_id)
        return StageResult(
            stage=self.get_name(),
            success=True,
            message=f'Deployed to production: {deploy_info.get("url", "unknown")}',
            duration_seconds=deploy_info.get('duration', 120),
            metadata={'url': deploy_info.get('url', '')},
        )
```

- [ ] **Step 2: Criar pipeline_orchestrator.py**

```python
import asyncio
from datetime import datetime
from typing import Any
from structlog import get_logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.models.pipeline import PipelineRun, RollbackRequest
from src.models.schemas import PipelineStatus, PipelineStage
from src.orchestrators.stages import (
    PipelineStage as StageExecutor,
    PreFlightStage,
    BuildStage,
    TestStage,
    SecurityStage,
    StagingStage,
    ApprovalStage,
    ProductionStage,
    StageResult,
)


class OrchestratorConfig:
    """Configuration for pipeline orchestration."""

    def __init__(
        self,
        timeout_minutes: int = 60,
        max_retries: int = 3,
        enable_auto_rollback: bool = True,
        rollback_on_health_check: bool = True,
        rollback_on_metrics_degradation: bool = True,
    ):
        self.timeout_minutes = timeout_minutes
        self.max_retries = max_retries
        self.enable_auto_rollback = enable_auto_rollback
        self.rollback_on_health_check = rollback_on_health_check
        self.rollback_on_metrics_degradation = rollback_on_metrics_degradation


class PipelineOrchestrator:
    """Orchestrates the execution of CI/CD pipelines."""

    def __init__(self, config: OrchestratorConfig | None = None):
        self.config = config or OrchestratorConfig()
        self.logger = get_logger()
        self.stages: dict[PipelineStage, StageExecutor] = {
            PipelineStage.PRE_FLIGHT: PreFlightStage(),
            PipelineStage.BUILD: BuildStage(),
            PipelineStage.TEST: TestStage(),
            PipelineStage.SECURITY: SecurityStage(),
            PipelineStage.STAGING: StagingStage(),
            PipelineStage.APPROVAL: ApprovalStage(),
            PipelineStage.PRODUCTION: ProductionStage(),
        }

    async def execute(self, run: PipelineRun, context: dict) -> PipelineRun:
        """Execute the pipeline run through all stages."""
        self.logger.info('pipeline_execution_starting', run_id=run.run_id)

        run.status = PipelineStatus.RUNNING
        run.started_at = datetime.utcnow()

        try:
            # Define stage sequence based on environment
            stage_sequence = self._get_stage_sequence(context.get('environment', 'staging'))

            for stage in stage_sequence:
                if not await self._execute_stage(run, stage, context):
                    # Stage failed - stop execution
                    run.status = PipelineStatus.FAILED
                    run.finished_at = datetime.utcnow()
                    self.logger.error('pipeline_failed', run_id=run.run_id, stage=stage)
                    return run

            # All stages completed successfully
            run.status = PipelineStatus.SUCCESS
            run.finished_at = datetime.utcnow()
            run.duration_seconds = int((run.finished_at - run.started_at).total_seconds())

            self.logger.info('pipeline_completed_successfully', run_id=run.run_id)
            return run

        except Exception as e:
            self.logger.error('pipeline_error', run_id=run.run_id, error=str(e))
            run.status = PipelineStatus.FAILED
            run.finished_at = datetime.utcnow()
            return run

    async def _execute_stage(
        self, run: PipelineRun, stage: PipelineStage, context: dict
    ) -> bool:
        """Execute a single stage with retry logic."""
        run.current_stage = stage

        executor = self.stages.get(stage)
        if not executor:
            self.logger.warning('stage_not_found', stage=stage)
            return True  # Skip unknown stages

        for attempt in range(self.config.max_retries):
            try:
                result = await asyncio.wait_for(
                    executor.execute(run, context),
                    timeout=self.config.timeout_minutes * 60,
                )

                if result.success:
                    run.stages_completed.append(stage)
                    self.logger.info(
                        'stage_completed',
                        run_id=run.run_id,
                        stage=stage,
                        duration=result.duration_seconds,
                    )
                    return True
                else:
                    run.stages_failed.append(stage)
                    self.logger.error(
                        'stage_failed',
                        run_id=run.run_id,
                        stage=stage,
                        message=result.message,
                    )
                    return False  # Don't retry on failure

            except asyncio.TimeoutError:
                self.logger.warning(
                    'stage_timeout',
                    run_id=run.run_id,
                    stage=stage,
                    attempt=attempt + 1,
                )
                if attempt == self.config.max_retries - 1:
                    run.stages_failed.append(stage)
                    return False

            except Exception as e:
                self.logger.error(
                    'stage_error',
                    run_id=run.run_id,
                    stage=stage,
                    error=str(e),
                )
                if attempt == self.config.max_retries - 1:
                    run.stages_failed.append(stage)
                    return False

        return False

    def _get_stage_sequence(self, environment: str) -> list[PipelineStage]:
        """Get the sequence of stages for a given environment."""
        base_stages = [
            PipelineStage.PRE_FLIGHT,
            PipelineStage.BUILD,
            PipelineStage.TEST,
            PipelineStage.SECURITY,
        ]

        if environment == 'staging':
            return base_stages + [PipelineStage.STAGING]

        if environment == 'production':
            return base_stages + [
                PipelineStage.STAGING,
                PipelineStage.APPROVAL,
                PipelineStage.PRODUCTION,
            ]

        return base_stages

    async def rollback(self, request: RollbackRequest, context: dict) -> PipelineRun:
        """Execute a rollback for a failed deployment."""
        self.logger.info('rollback_initiated', run_id=request.run_id, reason=request.reason)

        run = context.get('run')
        if not run:
            raise ValueError(f'Run {request.run_id} not found')

        # Execute rollback logic (this would integrate with GitOps provider)
        run.status = PipelineStatus.ROLLED_BACK
        run.rollback_reason = request.reason
        run.finished_at = datetime.utcnow()

        self.logger.info('rollback_completed', run_id=request.run_id)
        return run

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
    )
    async def check_health(self, run: PipelineRun) -> bool:
        """Check if the deployed application is healthy."""
        self.logger.info('health_check', run_id=run.run_id)

        # This would integrate with actual health check endpoints
        # For now, simulate a successful check
        await asyncio.sleep(2)

        return True

    async def should_rollback(self, run: PipelineRun) -> tuple[bool, str]:
        """Determine if a rollback should be initiated."""
        reasons = []

        if self.config.rollback_on_health_check:
            healthy = await self.check_health(run)
            if not healthy:
                reasons.append('Health check failed')

        if self.config.rollback_on_metrics_degradation:
            degraded = await self._check_metrics_degradation(run)
            if degraded:
                reasons.append('Metrics degraded')

        return len(reasons) > 0, '; '.join(reasons)

    async def _check_metrics_degradation(self, run: PipelineRun) -> bool:
        """Check if metrics have degraded after deployment."""
        # This would query Prometheus for actual metrics
        # For now, return False (no degradation)
        return False
```

- [ ] **Step 3: Escrever testes do orchestrator**

```python
import pytest
from datetime import datetime
from src.models.pipeline import PipelineRun, RollbackRequest
from src.models.schemas import PipelineStatus, PipelineStage
from src.orchestrators.pipeline_orchestrator import (
    PipelineOrchestrator,
    OrchestratorConfig,
)


@pytest.mark.asyncio
async def test_orchestrator_execute_staging_success():
    config = OrchestratorConfig(timeout_minutes=1)
    orchestrator = PipelineOrchestrator(config)

    run = PipelineRun(
        run_id='test-run-1',
        manifest_id='manifest-1',
        repo_url='https://github.com/org/repo',
        git_sha='abc123',
    )

    context = {
        'environment': 'staging',
        'preflight_checks': {'has_secrets': True, 'version': '1.0.0'},
        'build_info': {'image': 'repo:latest', 'digest': 'sha256:123', 'duration': 10},
        'test_results': {'passed': 10, 'total': 10, 'duration': 5},
        'security_scan': {'critical': 0, 'high': 0, 'duration': 3},
        'staging_deploy': {'url': 'https://staging.example.com', 'duration': 8},
    }

    result = await orchestrator.execute(run, context)

    assert result.status == PipelineStatus.SUCCESS
    assert len(result.stages_completed) == 5  # pre_flight, build, test, security, staging
    assert result.finished_at is not None


@pytest.mark.asyncio
async def test_orchestrator_execute_test_failure():
    orchestrator = PipelineOrchestrator()

    run = PipelineRun(
        run_id='test-run-2',
        manifest_id='manifest-1',
        repo_url='https://github.com/org/repo',
        git_sha='abc123',
    )

    context = {
        'preflight_checks': {'has_secrets': True, 'version': '1.0.0'},
        'build_info': {'image': 'repo:latest', 'digest': 'sha256:123', 'duration': 10},
        'test_results': {'passed': 5, 'total': 10, 'duration': 5},  # Failed tests
    }

    result = await orchestrator.execute(run, context)

    assert result.status == PipelineStatus.FAILED
    assert PipelineStage.TEST in result.stages_failed
    assert PipelineStage.SECURITY not in result.stages_completed  # Stopped at test


@pytest.mark.asyncio
async def test_orchestrator_rollback():
    orchestrator = PipelineOrchestrator()

    run = PipelineRun(
        run_id='test-run-3',
        manifest_id='manifest-1',
        repo_url='https://github.com/org/repo',
        git_sha='abc123',
        status=PipelineStatus.RUNNING,
    )

    request = RollbackRequest(
        run_id='test-run-3',
        reason='Health check failed',
    )

    context = {'run': run}

    result = await orchestrator.rollback(request, context)

    assert result.status == PipelineStatus.ROLLED_BACK
    assert result.rollback_reason == 'Health check failed'


@pytest.mark.asyncio
async def test_orchestrator_health_check():
    orchestrator = PipelineOrchestrator()

    run = PipelineRun(
        run_id='test-run-4',
        manifest_id='manifest-1',
        repo_url='https://github.com/org/repo',
        git_sha='abc123',
    )

    healthy = await orchestrator.check_health(run)

    assert healthy is True


@pytest.mark.asyncio
async def test_orchestrator_should_rollback_no_degradation():
    config = OrchestratorConfig(
        rollback_on_health_check=True,
        rollback_on_metrics_degradation=True,
    )
    orchestrator = PipelineOrchestrator(config)

    run = PipelineRun(
        run_id='test-run-5',
        manifest_id='manifest-1',
        repo_url='https://github.com/org/repo',
        git_sha='abc123',
    )

    should_rollback, reason = await orchestrator.should_rollback(run)

    assert should_rollback is False
    assert reason == ''


def test_get_stage_sequence_staging():
    orchestrator = PipelineOrchestrator()
    stages = orchestrator._get_stage_sequence('staging')

    assert PipelineStage.PRODUCTION not in stages
    assert PipelineStage.APPROVAL not in stages
    assert PipelineStage.STAGING in stages


def test_get_stage_sequence_production():
    orchestrator = PipelineOrchestrator()
    stages = orchestrator._get_stage_sequence('production')

    assert PipelineStage.PRODUCTION in stages
    assert PipelineStage.APPROVAL in stages
    assert PipelineStage.STAGING in stages
```

- [ ] **Step 4: Executar testes**

```bash
cd services/software-engineering-pipeline
pytest tests/unit/test_orchestrator.py -v
```

- [ ] **Step 5: Commit**

```bash
git add services/software-engineering-pipeline/src/orchestrators/ \
        services/software-engineering-pipeline/tests/unit/test_orchestrator.py
git commit -m "feat(pipeline): adiciona pipeline orchestrator com estágios"
```

---

## Task 5: Pipeline Intelligence - Detecção de Anomalias

**Arquivos:**
- Criar: `services/software-engineering-pipeline/src/intelligence/anomaly_detector.py`
- Criar: `services/software-engineering-pipeline/src/intelligence/flaky_test_detector.py`
- Criar: `services/software-engineering-pipeline/src/intelligence/insights_generator.py`
- Test: `services/software-engineering-pipeline/tests/unit/test_intelligence.py`

- [ ] **Step 1: Criar anomaly_detector.py**

```python
from datetime import datetime, timedelta
from typing import Any
from pydantic import BaseModel
from structlog import get_logger

from src.models.pipeline import Anomaly, AnomalyType
from src.models.schemas import Severity


class AnomalyDetectionConfig(BaseModel):
    """Configuration for anomaly detection."""

    flaky_test_threshold: int = 3  # Number of consecutive failures
    failure_rate_threshold: float = 0.5  # 50% failure rate
    duration_increase_threshold: float = 2.0  # 2x slower
    enable_performance_detection: bool = True
    enable_security_detection: bool = True


class AnomalyPattern(BaseModel):
    """Represents a detected anomaly pattern."""

    pattern_type: AnomalyType
    severity: Severity
    description: str
    confidence: float
    affected_components: list[str]


class AnomalyDetector:
    """Detects anomalies in pipeline execution."""

    def __init__(self, config: AnomalyDetectionConfig | None = None):
        self.config = config or AnomalyDetectionConfig()
        self.logger = get_logger()

    async def analyze_run(
        self,
        run: dict,
        historical_runs: list[dict],
    ) -> list[Anomaly]:
        """Analyze a pipeline run for anomalies."""
        self.logger.info('analyzing_run', run_id=run.get('run_id'))

        anomalies: list[Anomaly] = []

        # Check for flaky tests
        flaky_anomalies = await self._detect_flaky_tests(run, historical_runs)
        anomalies.extend(flaky_anomalies)

        # Check for performance degradation
        if self.config.enable_performance_detection:
            perf_anomalies = await self._detect_performance_degradation(
                run, historical_runs
            )
            anomalies.extend(perf_anomalies)

        # Check for security issues
        if self.config.enable_security_detection:
            security_anomalies = await self._detect_security_anomalies(run)
            anomalies.extend(security_anomalies)

        self.logger.info('anomaly_analysis_complete', count=len(anomalies))
        return anomalies

    async def _detect_flaky_tests(
        self, run: dict, historical_runs: list[dict]
    ) -> list[Anomaly]:
        """Detect flaky tests (tests that fail intermittently)."""
        anomalies: list[Anomaly] = []

        test_results = run.get('test_results', {})
        failed_tests = test_results.get('failed_tests', [])

        for test_name in failed_tests:
            # Check if this test failed in recent runs
            consecutive_failures = 0
            for historical_run in reversed(historical_runs[:10]):
                hist_test_results = historical_run.get('test_results', {})
                if test_name in hist_test_results.get('failed_tests', []):
                    consecutive_failures += 1
                elif test_name in hist_test_results.get('passed_tests', []):
                    break  # Test passed, break the streak

            if consecutive_failures >= 1 and consecutive_failures < self.config.flaky_test_threshold:
                # Test failed recently but passed before - potentially flaky
                anomalies.append(Anomaly(
                    anomaly_id=f'flaky-{run.get("run_id")}-{test_name}',
                    repo_url=run.get('repo_url', ''),
                    run_id=run.get('run_id'),
                    type=AnomalyType.FLAKY_TEST,
                    severity=Severity.MEDIUM,
                    description=f'Test "{test_name}" failed {consecutive_failures} times recently',
                    affected_component=test_name,
                    suggested_action='Review test for race conditions or external dependencies',
                ))

        return anomalies

    async def _detect_performance_degradation(
        self, run: dict, historical_runs: list[dict]
    ) -> list[Anomaly]:
        """Detect significant performance degradation."""
        anomalies: list[Anomaly] = []

        current_duration = run.get('duration_seconds', 0)
        if current_duration == 0:
            return anomalies

        # Calculate average duration from historical runs
        if not historical_runs:
            return anomalies

        durations = [r.get('duration_seconds', 0) for r in historical_runs if r.get('duration_seconds')]
        if not durations:
            return anomalies

        avg_duration = sum(durations) / len(durations)

        if current_duration > avg_duration * self.config.duration_increase_threshold:
            anomalies.append(Anomaly(
                anomaly_id=f'perf-{run.get("run_id")}',
                repo_url=run.get('repo_url', ''),
                run_id=run.get('run_id'),
                type=AnomalyType.PERFORMANCE_DEGRADATION,
                severity=Severity.HIGH if current_duration > avg_duration * 3 else Severity.MEDIUM,
                description=f'Pipeline duration increased from {avg_duration:.0f}s to {current_duration}s',
                suggested_action='Review recent changes for performance issues',
            ))

        return anomalies

    async def _detect_security_anomalies(self, run: dict) -> list[Anomaly]:
        """Detect security-related anomalies."""
        anomalies: list[Anomaly] = []

        security_results = run.get('security_scan', {})
        critical_vulns = security_results.get('critical', 0)
        high_vulns = security_results.get('high', 0)

        if critical_vulns > 0:
            anomalies.append(Anomaly(
                anomaly_id=f'sec-critical-{run.get("run_id")}',
                repo_url=run.get('repo_url', ''),
                run_id=run.get('run_id'),
                type=AnomalyType.SECURITY_VULNERABILITY,
                severity=Severity.CRITICAL,
                description=f'{critical_vulns} critical vulnerabilities detected',
                suggested_action='Block deployment and address vulnerabilities immediately',
            ))

        if high_vulns > 5:
            anomalies.append(Anomaly(
                anomaly_id=f'sec-high-{run.get("run_id")}',
                repo_url=run.get('repo_url', ''),
                run_id=run.get('run_id'),
                type=AnomalyType.SECURITY_VULNERABILITY,
                severity=Severity.HIGH,
                description=f'{high_vulns} high-severity vulnerabilities detected',
                suggested_action='Review and address high-severity vulnerabilities',
            ))

        return anomalies
```

- [ ] **Step 2: Criar flaky_test_detector.py**

```python
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from pydantic import BaseModel
from structlog import get_logger

from src.models.pipeline import Anomaly
from src.models.schemas import Severity


class TestHistory(BaseModel):
    """Tracks history of a specific test."""

    test_name: str
    total_runs: int = 0
    passed_runs: int = 0
    failed_runs: int = 0
    flaky_score: float = 0.0  # 0.0 = stable, 1.0 = very flaky
    last_failure: datetime | None = None
    last_pass: datetime | None = None


class FlakyTestDetector:
    """Detects and tracks flaky tests."""

    def __init__(self, flaky_threshold: float = 0.3):
        self.flaky_threshold = flaky_threshold
        self.logger = get_logger()
        self.test_histories: dict[str, TestHistory] = {}

    async def analyze_test_results(
        self,
        test_results: dict,
        repo_url: str,
        run_id: str,
    ) -> list[Anomaly]:
        """Analyze test results for flakiness."""
        self.logger.info('analyzing_test_results', run_id=run_id)

        anomalies: list[Anomaly] = []

        # Update test histories
        self._update_histories(test_results, run_id)

        # Check for flaky tests
        for test_name, history in self.test_histories.items():
            if history.flaky_score >= self.flaky_threshold:
                anomalies.append(Anomaly(
                    anomaly_id=f'flaky-{run_id}-{test_name}',
                    repo_url=repo_url,
                    run_id=run_id,
                    type='flaky_test',
                    severity=Severity.MEDIUM,
                    description=f'Test "{test_name}" has flaky score of {history.flaky_score:.2f}',
                    affected_component=test_name,
                    suggested_action='Add retry logic or fix race condition',
                ))

        return anomalies

    def _update_histories(self, test_results: dict, run_id: str) -> None:
        """Update test histories with new results."""
        now = datetime.utcnow()

        passed_tests = test_results.get('passed_tests', [])
        failed_tests = test_results.get('failed_tests', [])

        # Update passed tests
        for test_name in passed_tests:
            if test_name not in self.test_histories:
                self.test_histories[test_name] = TestHistory(test_name=test_name)

            history = self.test_histories[test_name]
            history.total_runs += 1
            history.passed_runs += 1
            history.last_pass = now
            history.flaky_score = self._calculate_flaky_score(history)

        # Update failed tests
        for test_name in failed_tests:
            if test_name not in self.test_histories:
                self.test_histories[test_name] = TestHistory(test_name=test_name)

            history = self.test_histories[test_name]
            history.total_runs += 1
            history.failed_runs += 1
            history.last_failure = now
            history.flaky_score = self._calculate_flaky_score(history)

    def _calculate_flaky_score(self, history: TestHistory) -> float:
        """Calculate flaky score based on pass/fail pattern."""
        if history.total_runs < 3:
            return 0.0

        # Simple metric: failure rate weighted by recency
        base_score = history.failed_runs / history.total_runs

        # Boost score if test has both recent passes and failures (true flakiness)
        if history.last_pass and history.last_failure:
            time_diff = abs((history.last_pass - history.last_failure).total_seconds())
            if time_diff < 3600:  # Within an hour
                base_score *= 1.5

        return min(base_score, 1.0)

    def get_flaky_tests(self) -> list[TestHistory]:
        """Get all tests that are considered flaky."""
        return [
            h for h in self.test_histories.values()
            if h.flaky_score >= self.flaky_threshold
        ]

    def get_test_history(self, test_name: str) -> TestHistory | None:
        """Get history for a specific test."""
        return self.test_histories.get(test_name)
```

- [ ] **Step 3: Criar insights_generator.py**

```python
from datetime import datetime, timedelta
from typing import Any
from pydantic import BaseModel
from structlog import get_logger

from src.models.pipeline import Insight, InsightsReport
from src.models.schemas import Severity


class InsightConfig(BaseModel):
    """Configuration for insights generation."""

    slow_test_threshold_seconds: int = 10
    cache_miss_threshold: int = 5
    parallelization_candidate_time: int = 30


class InsightsGenerator:
    """Generates insights from pipeline execution data."""

    def __init__(self, config: InsightConfig | None = None):
        self.config = config or InsightConfig()
        self.logger = get_logger()

    async def generate_insights(
        self,
        repo_url: str,
        runs: list[dict],
        timeframe_start: datetime,
        timeframe_end: datetime,
    ) -> InsightsReport:
        """Generate comprehensive insights report."""
        self.logger.info('generating_insights', repo_url=repo_url, runs_count=len(runs))

        if not runs:
            return InsightsReport(
                repo_url=repo_url,
                timeframe_start=timeframe_start,
                timeframe_end=timeframe_end,
                total_runs=0,
                success_rate=0.0,
                average_duration_seconds=0.0,
                flaky_tests=[],
                slow_tests=[],
                optimization_opportunities=[],
                security_issues=[],
            )

        # Calculate basic metrics
        successful_runs = [r for r in runs if r.get('status') == 'success']
        success_rate = len(successful_runs) / len(runs) if runs else 0.0

        durations = [r.get('duration_seconds', 0) for r in runs if r.get('duration_seconds')]
        avg_duration = sum(durations) / len(durations) if durations else 0.0

        # Generate insights
        flaky_tests = await self._find_flaky_tests(runs, repo_url)
        slow_tests = await self._find_slow_tests(runs, repo_url)
        optimization_opportunities = await self._find_optimization_opportunities(
            runs, repo_url
        )
        security_issues = await self._find_security_issues(runs, repo_url)

        return InsightsReport(
            repo_url=repo_url,
            timeframe_start=timeframe_start,
            timeframe_end=timeframe_end,
            total_runs=len(runs),
            success_rate=success_rate,
            average_duration_seconds=avg_duration,
            flaky_tests=flaky_tests,
            slow_tests=slow_tests,
            optimization_opportunities=optimization_opportunities,
            security_issues=security_issues,
        )

    async def _find_flaky_tests(self, runs: list[dict], repo_url: str) -> list[Insight]:
        """Find tests that fail intermittently."""
        test_results: dict[str, dict] = {}

        for run in runs:
            run_test_results = run.get('test_results', {})
            failed = run_test_results.get('failed_tests', [])
            passed = run_test_results.get('passed_tests', [])

            for test in failed:
                if test not in test_results:
                    test_results[test] = {'failures': 0, 'passes': 0}
                test_results[test]['failures'] += 1

            for test in passed:
                if test not in test_results:
                    test_results[test] = {'failures': 0, 'passes': 0}
                test_results[test]['passes'] += 1

        # Find tests with both failures and passes
        flaky = []
        for test_name, counts in test_results.items():
            if counts['failures'] > 0 and counts['passes'] > 0:
                flaky_score = counts['failures'] / (counts['failures'] + counts['passes'])
                if flaky_score > 0.1:  # At least 10% failure rate
                    flaky.append(Insight(
                        insight_id=f'flaky-{test_name}',
                        repo_url=repo_url,
                        insight_type='flaky_test',
                        title=f'Flaky test: {test_name}',
                        description=f'Test fails {counts["failures"]} times but passes {counts["passes"]} times',
                        impact=Severity.MEDIUM if flaky_score < 0.3 else Severity.HIGH,
                        effort='M',
                    ))

        return flaky

    async def _find_slow_tests(self, runs: list[dict], repo_url: str) -> list[Insight]:
        """Find tests that take too long to run."""
        test_times: dict[str, list[int]] = {}

        for run in runs:
            run_test_results = run.get('test_results', {})
            test_durations = run_test_results.get('test_durations', {})

            for test_name, duration in test_durations.items():
                if test_name not in test_times:
                    test_times[test_name] = []
                test_times[test_name].append(duration)

        slow_tests = []
        for test_name, durations in test_times.items():
            avg_duration = sum(durations) / len(durations)
            if avg_duration > self.config.slow_test_threshold_seconds:
                slow_tests.append(Insight(
                    insight_id=f'slow-{test_name}',
                    repo_url=repo_url,
                    insight_type='slow_test',
                    title=f'Slow test: {test_name}',
                    description=f'Test takes {avg_duration:.1f}s on average',
                    impact=Severity.MEDIUM,
                    effort='M',
                ))

        return slow_tests

    async def _find_optimization_opportunities(
        self, runs: list[dict], repo_url: str
    ) -> list[Insight]:
        """Find opportunities to optimize pipeline performance."""
        opportunities = []

        # Check for cache opportunities
        cache_misses = 0
        for run in runs:
            if run.get('cache_hit') is False:
                cache_misses += 1

        if cache_misses > self.config.cache_miss_threshold:
            opportunities.append(Insight(
                insight_id='cache-miss',
                repo_url=repo_url,
                insight_type='cache_opportunity',
                title='High cache miss rate',
                description=f'{cache_misses} runs had cache misses',
                impact=Severity.MEDIUM,
                effort='S',
            ))

        # Check for parallelization opportunities
        avg_duration = sum(
            r.get('duration_seconds', 0) for r in runs if r.get('duration_seconds')
        ) / len(runs) if runs else 0

        if avg_duration > self.config.parallelization_candidate_time:
            opportunities.append(Insight(
                insight_id='parallelize',
                repo_url=repo_url,
                insight_type='parallelization_opportunity',
                title='Long pipeline duration',
                description=f'Average pipeline takes {avg_duration:.0f}s - consider parallelizing stages',
                impact=Severity.HIGH,
                effort='M',
            ))

        return opportunities

    async def _find_security_issues(self, runs: list[dict], repo_url: str) -> list[Insight]:
        """Find recurring security issues."""
        security_issues = []

        vuln_count = 0
        critical_count = 0

        for run in runs:
            security_scan = run.get('security_scan', {})
            vuln_count += security_scan.get('total', 0)
            critical_count += security_scan.get('critical', 0)

        if critical_count > 0:
            security_issues.append(Insight(
                insight_id='sec-critical',
                repo_url=repo_url,
                insight_type='security_issue',
                title='Critical vulnerabilities recurring',
                description=f'{critical_count} critical vulnerabilities found across {len(runs)} runs',
                impact=Severity.CRITICAL,
                effort='L',
            ))

        return security_issues
```

- [ ] **Step 4: Escrever testes de inteligência**

```python
import pytest
from datetime import datetime, timedelta
from src.intelligence.anomaly_detector import (
    AnomalyDetector,
    AnomalyDetectionConfig,
)
from src.intelligence.flaky_test_detector import FlakyTestDetector
from src.intelligence.insights_generator import InsightsGenerator, InsightConfig
from src.models.schemas import Severity


@pytest.mark.asyncio
async def test_detect_performance_degradation():
    detector = AnomalyDetector()

    current_run = {
        'run_id': 'current',
        'repo_url': 'https://github.com/org/repo',
        'duration_seconds': 600,  # 10 minutes
    }

    historical_runs = [
        {'run_id': 'hist-1', 'duration_seconds': 180},
        {'run_id': 'hist-2', 'duration_seconds': 200},
        {'run_id': 'hist-3', 'duration_seconds': 190},
    ]

    anomalies = await detector._detect_performance_degradation(current_run, historical_runs)

    assert len(anomalies) == 1
    assert anomalies[0].type == 'performance_degradation'


@pytest.mark.asyncio
async def test_detect_no_flaky_tests():
    detector = AnomalyDetector()

    current_run = {
        'run_id': 'current',
        'repo_url': 'https://github.com/org/repo',
        'test_results': {
            'failed_tests': ['test_login'],
        },
    }

    historical_runs = [
        {
            'run_id': 'hist-1',
            'test_results': {
                'failed_tests': ['test_login'],
                'passed_tests': ['test_logout'],
            },
        },
    ]

    anomalies = await detector._detect_flaky_tests(current_run, historical_runs)

    # test_login failed in both, not flaky
    assert len(anomalies) == 0


@pytest.mark.asyncio
async def test_flaky_test_detector():
    detector = FlakyTestDetector(flaky_threshold=0.3)

    test_results = {
        'passed_tests': ['test_a', 'test_b'],
        'failed_tests': ['test_c'],
    }

    # First run: test_c fails
    anomalies1 = await detector.analyze_test_results(
        test_results, 'https://github.com/org/repo', 'run-1'
    )
    assert len(anomalies1) == 0  # Need more data

    # Second run: test_c passes
    test_results['failed_tests'] = []
    test_results['passed_tests'].append('test_c')

    anomalies2 = await detector.analyze_test_results(
        test_results, 'https://github.com/org/repo', 'run-2'
    )

    # test_c should be flagged as flaky
    flaky_tests = detector.get_flaky_tests()
    assert len(flaky_tests) >= 1


@pytest.mark.asyncio
async def test_insights_generator_basic():
    generator = InsightsGenerator()

    runs = [
        {
            'run_id': 'run-1',
            'status': 'success',
            'duration_seconds': 120,
            'test_results': {
                'failed_tests': [],
                'passed_tests': ['test_a', 'test_b'],
                'test_durations': {'test_a': 2, 'test_b': 3},
            },
            'security_scan': {'total': 0, 'critical': 0},
            'cache_hit': True,
        },
        {
            'run_id': 'run-2',
            'status': 'failed',
            'duration_seconds': 180,
            'test_results': {
                'failed_tests': ['test_a'],
                'passed_tests': ['test_b'],
                'test_durations': {'test_a': 2, 'test_b': 3},
            },
            'security_scan': {'total': 1, 'critical': 0},
            'cache_hit': False,
        },
    ]

    timeframe_end = datetime.utcnow()
    timeframe_start = timeframe_end - timedelta(days=1)

    report = await generator.generate_insights(
        'https://github.com/org/repo',
        runs,
        timeframe_start,
        timeframe_end,
    )

    assert report.total_runs == 2
    assert report.success_rate == 0.5
    assert report.average_duration_seconds == 150.0
    assert len(report.flaky_tests) > 0  # test_a should be flaky


@pytest.mark.asyncio
async def test_insights_generator_empty_runs():
    generator = InsightsGenerator()

    report = await generator.generate_insights(
        'https://github.com/org/repo',
        [],
        datetime.utcnow() - timedelta(days=1),
        datetime.utcnow(),
    )

    assert report.total_runs == 0
    assert report.success_rate == 0.0
```

- [ ] **Step 5: Executar testes**

```bash
cd services/software-engineering-pipeline
pytest tests/unit/test_intelligence.py -v
```

- [ ] **Step 6: Commit**

```bash
git add services/software-engineering-pipeline/src/intelligence/ \
        services/software-engineering-pipeline/tests/unit/test_intelligence.py
git commit -m "feat(pipeline): adiciona detecção de anomalias e insights generator"
```

---

## Task 6: Repositories MongoDB

**Arquivos:**
- Criar: `services/software-engineering-pipeline/src/repositories/base.py`
- Criar: `services/software-engineering-pipeline/src/repositories/pipeline_repository.py`
- Test: `services/software-engineering-pipeline/tests/unit/test_repositories.py`

- [ ] **Step 1: Criar base.py**

```python
from typing import Generic, TypeVar, Any
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from structlog import get_logger

from src.config.settings import settings


T = TypeVar('T', bound=BaseModel)


class BaseRepository(Generic[T]):
    """Base repository for MongoDB operations."""

    def __init__(
        self,
        client: AsyncIOMotorClient | None = None,
        database: str | None = None,
        collection: str | None = None,
    ):
        self.logger = get_logger()
        self._client = client or AsyncIOMotorClient(settings.mongodb_url)
        self._database_name = database or settings.mongodb_db_name
        self._collection_name = collection
        self._collection = self._client[self._database_name][self._collection_name]

    @property
    def collection(self):
        return self._collection

    async def create(self, document: T) -> str:
        """Insert a document and return its ID."""
        self.logger.info('creating_document', collection=self._collection_name)

        doc_dict = document.model_dump(exclude_unset=True)
        result = await self._collection.insert_one(doc_dict)

        self.logger.info('document_created', id=str(result.inserted_id))
        return str(result.inserted_id)

    async def find_by_id(self, id: str) -> T | None:
        """Find a document by ID."""
        doc = await self._collection.find_one({'_id': id})
        return doc if doc else None

    async def find_one(self, filter_dict: dict) -> T | None:
        """Find a single document matching the filter."""
        doc = await self._collection.find_one(filter_dict)
        return doc if doc else None

    async def find_many(
        self,
        filter_dict: dict | None = None,
        skip: int = 0,
        limit: int = 100,
        sort: list[tuple[str, int]] | None = None,
    ) -> list[T]:
        """Find multiple documents matching the filter."""
        cursor = self._collection.find(filter_dict or {})

        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        if sort:
            cursor = cursor.sort(sort)

        docs = await cursor.to_list(length=limit)
        return docs

    async def update(self, id: str, updates: dict) -> bool:
        """Update a document by ID."""
        result = await self._collection.update_one(
            {'_id': id},
            {'$set': updates}
        )
        return result.modified_count > 0

    async def delete(self, id: str) -> bool:
        """Delete a document by ID."""
        result = await self._collection.delete_one({'_id': id})
        return result.deleted_count > 0

    async def count(self, filter_dict: dict | None = None) -> int:
        """Count documents matching the filter."""
        return await self._collection.count_documents(filter_dict or {})

    async def aggregate(self, pipeline: list[dict]) -> list[dict]:
        """Run an aggregation pipeline."""
        cursor = self._collection.aggregate(pipeline)
        return await cursor.to_list(length=None)

    async def create_index(self, keys: list[tuple[str, int]], **kwargs) -> str:
        """Create an index on the collection."""
        return await self._collection.create_index(keys, **kwargs)

    async def close(self) -> None:
        """Close the database connection."""
        self._client.close()
```

- [ ] **Step 2: Criar pipeline_repository.py**

```python
from datetime import datetime, timedelta
from typing import Any
from motor.motor_asyncio import AsyncIOMotorClient

from src.repositories.base import BaseRepository
from src.models.pipeline import (
    PipelineManifest,
    PipelineRun,
    Anomaly,
    InsightsReport,
)
from src.models.schemas import PipelineStatus


class PipelineManifestRepository(BaseRepository[PipelineManifest]):
    """Repository for pipeline manifests."""

    def __init__(self, client: AsyncIOMotorClient | None = None):
        super().__init__(client, collection='pipeline_manifests')

    async def find_by_repo(
        self, repo_url: str, branch: str = 'main'
    ) -> PipelineManifest | None:
        """Find the latest manifest for a repo."""
        return await self.find_one({
            'repo_url': repo_url,
            'branch': branch,
        })

    async def upsert_by_repo(
        self, repo_url: str, branch: str, manifest: PipelineManifest
    ) -> str:
        """Insert or update a manifest for a repo."""
        existing = await self.find_by_repo(repo_url, branch)

        if existing:
            await self.update(existing['_id'], manifest.model_dump(exclude_unset=True))
            return existing['_id']

        return await self.create(manifest)


class PipelineRunRepository(BaseRepository[PipelineRun]):
    """Repository for pipeline runs."""

    def __init__(self, client: AsyncIOMotorClient | None = None):
        super().__init__(client, collection='pipeline_runs')
        self._create_indexes()

    async def _create_indexes(self) -> None:
        """Create indexes for common queries."""
        await self.create_index([('repo_url', 1), ('created_at', -1)])
        await self.create_index([('git_sha', 1)])
        await self.create_index([('status', 1), ('started_at', -1)])
        await self.create_index([('finished_at', 1)], expireAfterSeconds=2592000)  # 30 days TTL

    async def find_recent_by_repo(
        self, repo_url: str, limit: int = 10
    ) -> list[PipelineRun]:
        """Find recent runs for a repo."""
        return await self.find_many(
            filter_dict={'repo_url': repo_url},
            sort=[('started_at', -1)],
            limit=limit,
        )

    async def find_by_status(
        self, status: PipelineStatus, limit: int = 100
    ) -> list[PipelineRun]:
        """Find runs with a specific status."""
        return await self.find_many(
            filter_dict={'status': status.value},
            sort=[('started_at', -1)],
            limit=limit,
        )

    async def find_by_date_range(
        self,
        repo_url: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[PipelineRun]:
        """Find runs within a date range."""
        return await self.find_many(
            filter_dict={
                'repo_url': repo_url,
                'started_at': {'$gte': start_date, '$lte': end_date},
            },
            sort=[('started_at', -1)],
        )

    async def update_status(
        self, run_id: str, status: PipelineStatus, **kwargs
    ) -> bool:
        """Update the status of a run."""
        updates = {'status': status.value, **kwargs}
        return await self.update(run_id, updates)

    async def get_success_rate(
        self, repo_url: str, days: int = 30
    ) -> float:
        """Calculate success rate for a repo over the last N days."""
        start_date = datetime.utcnow() - timedelta(days=days)

        pipeline = [
            {'$match': {
                'repo_url': repo_url,
                'started_at': {'$gte': start_date},
            }},
            {'$group': {
                '_id': '$status',
                'count': {'$sum': 1},
            }},
        ]

        results = await self.aggregate(pipeline)

        total = sum(r['count'] for r in results)
        if total == 0:
            return 0.0

        successful = next(
            (r['count'] for r in results if r['_id'] == PipelineStatus.SUCCESS.value),
            0,
        )

        return successful / total


class AnomalyRepository(BaseRepository[Anomaly]):
    """Repository for anomalies."""

    def __init__(self, client: AsyncIOMotorClient | None = None):
        super().__init__(client, collection='anomalies')
        self._create_indexes()

    async def _create_indexes(self) -> None:
        """Create indexes for common queries."""
        await self.create_index([('repo_url', 1), ('detected_at', -1)])
        await self.create_index([('resolved', 1), ('detected_at', -1)])
        await self.create_index([('type', 1)])

    async def find_unresolved(self, repo_url: str) -> list[Anomaly]:
        """Find unresolved anomalies for a repo."""
        return await self.find_many(
            filter_dict={
                'repo_url': repo_url,
                'resolved': False,
            },
            sort=[('detected_at', -1)],
        )

    async def find_by_type(
        self, repo_url: str, anomaly_type: str
    ) -> list[Anomaly]:
        """Find anomalies of a specific type."""
        return await self.find_many(
            filter_dict={
                'repo_url': repo_url,
                'type': anomaly_type,
            },
            sort=[('detected_at', -1)],
        )

    async def mark_resolved(self, anomaly_id: str) -> bool:
        """Mark an anomaly as resolved."""
        return await self.update(
            anomaly_id,
            {'resolved': True, 'resolved_at': datetime.utcnow()},
        )


class InsightsRepository(BaseRepository[InsightsReport]):
    """Repository for insights reports."""

    def __init__(self, client: AsyncIOMotorClient | None = None):
        super().__init__(client, collection='insights_reports')
        self._create_indexes()

    async def _create_indexes(self) -> None:
        """Create indexes for common queries."""
        await self.create_index(
            [('repo_url', 1), ('timeframe_end', -1)],
            unique=True,
        )

    async def find_latest(
        self, repo_url: str, limit: int = 10
    ) -> list[InsightsReport]:
        """Find the latest insights reports for a repo."""
        return await self.find_many(
            filter_dict={'repo_url': repo_url},
            sort=[('timeframe_end', -1)],
            limit=limit,
        )
```

- [ ] **Step 3: Escrever testes dos repositórios**

```python
import pytest
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient

from src.repositories.pipeline_repository import (
    PipelineRunRepository,
    AnomalyRepository,
)
from src.models.pipeline import PipelineRun, Anomaly
from src.models.schemas import PipelineStatus


@pytest.mark.asyncio
async async def test_create_and_find_run():
    repo = PipelineRunRepository()

    run = PipelineRun(
        run_id='test-run-1',
        manifest_id='manifest-1',
        repo_url='https://github.com/org/repo',
        git_sha='abc123',
        status=PipelineStatus.RUNNING,
    )

    run_id = await repo.create(run)
    assert run_id is not None

    found = await repo.find_by_id(run_id)
    assert found is not None
    assert found['run_id'] == 'test-run-1'


@pytest.mark.asyncio
async async def test_update_run_status():
    repo = PipelineRunRepository()

    run = PipelineRun(
        run_id='test-run-2',
        manifest_id='manifest-1',
        repo_url='https://github.com/org/repo',
        git_sha='abc123',
        status=PipelineStatus.RUNNING,
    )

    run_id = await repo.create(run)

    updated = await repo.update_status(
        run_id,
        PipelineStatus.SUCCESS,
        finished_at=datetime.utcnow(),
        duration_seconds=120,
    )

    assert updated is True

    found = await repo.find_by_id(run_id)
    assert found['status'] == PipelineStatus.SUCCESS.value


@pytest.mark.asyncio
async async def test_find_unresolved_anomalies():
    repo = AnomalyRepository()

    anomaly1 = Anomaly(
        anomaly_id='anom-1',
        repo_url='https://github.com/org/repo',
        type='flaky_test',
        severity='medium',
        description='Test is flaky',
        resolved=False,
    )

    anomaly2 = Anomaly(
        anomaly_id='anom-2',
        repo_url='https://github.com/org/repo',
        type='flaky_test',
        severity='medium',
        description='Another flaky test',
        resolved=True,
    )

    await repo.create(anomaly1)
    await repo.create(anomaly2)

    unresolved = await repo.find_unresolved('https://github.com/org/repo')

    assert len(unresolved) == 1
    assert unresolved[0]['anomaly_id'] == 'anom-1'


@pytest.mark.asyncio
async async def test_mark_anomaly_resolved():
    repo = AnomalyRepository()

    anomaly = Anomaly(
        anomaly_id='anom-3',
        repo_url='https://github.com/org/repo',
        type='flaky_test',
        severity='medium',
        description='Test is flaky',
        resolved=False,
    )

    await repo.create(anomaly)

    resolved = await repo.mark_resolved('anom-3')
    assert resolved is True

    found = await repo.find_by_id('anom-3')
    assert found['resolved'] is True
    assert found['resolved_at'] is not None
```

- [ ] **Step 4: Executar testes**

```bash
cd services/software-engineering-pipeline
pytest tests/unit/test_repositories.py -v
```

- [ ] **Step 5: Commit**

```bash
git add services/software-engineering-pipeline/src/repositories/ \
        services/software-engineering-pipeline/tests/unit/test_repositories.py
git commit -m "feat(pipeline): adiciona repositories MongoDB"
```

---

## Task 7: Clientes GitHub/GitLab/Jenkins/ArgoCD

**Arquivos:**
- Criar: `services/software-engineering-pipeline/src/clients/github_client.py`
- Criar: `services/software-engineering-pipeline/src/clients/gitlab_client.py`
- Criar: `services/software-engineering-pipeline/src/clients/argocd_client.py`
- Test: `services/software-engineering-pipeline/tests/unit/test_clients.py`

- [ ] **Step 1: Criar github_client.py**

```python
from github import Github, GithubException
from github.Repository import Repository
from structlog import get_logger

from src.config.settings import settings


class GitHubClient:
    """Client for interacting with GitHub API."""

    def __init__(
        self,
        token: str | None = None,
        app_id: str | None = None,
        app_private_key: str | None = None,
    ):
        self.token = token or settings.github_token
        self.app_id = app_id or settings.github_app_id
        self.app_private_key = app_private_key or settings.github_app_private_key
        self.logger = get_logger()

        if self.token:
            self.client = Github(self.token)
        elif self.app_id and self.app_private_key:
            # GitHub App authentication would go here
            self.client = Github()
        else:
            raise ValueError('Either token or app credentials are required')

    async def get_repository(self, repo_url: str) -> Repository:
        """Get a repository object from URL."""
        # Parse repo URL to get owner/repo
        parts = repo_url.rstrip('/').split('/')
        if len(parts) < 2:
            raise ValueError(f'Invalid repository URL: {repo_url}')

        owner, repo = parts[-2], parts[-1]
        repo_name = f'{owner}/{repo}'

        try:
            return self.client.get_repo(repo_name)
        except GithubException as e:
            self.logger.error('github_api_error', repo=repo_name, error=str(e))
            raise

    async def create_workflow_dispatch(
        self, repo_url: str, workflow: str, ref: str, inputs: dict
    ) -> bool:
        """Trigger a GitHub Actions workflow."""
        try:
            repo = await self.get_repository(repo_url)
            repo.create_workflow_dispatch(workflow, ref, inputs)
            self.logger.info('workflow_dispatched', repo=repo_url, workflow=workflow)
            return True
        except GithubException as e:
            self.logger.error('workflow_dispatch_failed', error=str(e))
            return False

    async def get_workflow_runs(
        self, repo_url: str, limit: int = 10
    ) -> list[dict]:
        """Get recent workflow runs."""
        try:
            repo = await self.get_repository(repo_url)
            runs = repo.get_workflow_runs()[:limit]

            return [
                {
                    'id': run.id,
                    'name': run.name,
                    'status': run.status,
                    'conclusion': run.conclusion,
                    'created_at': run.created_at.isoformat(),
                    'updated_at': run.updated_at.isoformat(),
                }
                for run in runs
            ]
        except GithubException as e:
            self.logger.error('get_workflows_failed', error=str(e))
            return []

    async def create_or_update_file(
        self,
        repo_url: str,
        file_path: str,
        content: str,
        message: str,
        branch: str = 'main',
    ) -> bool:
        """Create or update a file in the repository."""
        try:
            repo = await self.get_repository(repo_url)

            try:
                # Try to get existing file
                existing_file = repo.get_contents(file_path, ref=branch)
                repo.update_file(
                    file_path,
                    message,
                    content,
                    existing_file.sha,
                    branch=branch,
                )
            except:
                # File doesn't exist, create it
                repo.create_file(file_path, message, content, branch=branch)

            self.logger.info('file_created', path=file_path, repo=repo_url)
            return True

        except GithubException as e:
            self.logger.error('file_operation_failed', error=str(e))
            return False

    async def list_files(self, repo_url: str, branch: str = 'main') -> list[str]:
        """List all files in the repository."""
        try:
            repo = await self.get_repository(repo_url)
            contents = repo.get_contents('', ref=branch)

            files = []
            while contents:
                file_content = contents.pop(0)
                if file_content.type == 'dir':
                    contents.extend(repo.get_contents(file_content.path))
                else:
                    files.append(file_content.path)

            return files

        except GithubException as e:
            self.logger.error('list_files_failed', error=str(e))
            return []
```

- [ ] **Step 2: Criar gitlab_client.py**

```python
import gitlab
from structlog import get_logger

from src.config.settings import settings


class GitLabClient:
    """Client for interacting with GitLab API."""

    def __init__(self, token: str | None = None, url: str | None = None):
        self.token = token or settings.gitlab_token
        self.url = url or settings.gitlab_url
        self.logger = get_logger()

        if not self.token:
            raise ValueError('GitLab token is required')

        self.client = gitlab.Gitlab(self.url, private_token=self.token)

    async def get_project(self, repo_url: str):
        """Get a project object from URL."""
        # Parse repo URL to get project ID or path
        parts = repo_url.rstrip('/').split('/')
        if len(parts) < 2:
            raise ValueError(f'Invalid repository URL: {repo_url}')

        # Try to get by path (owner/project)
        project_path = '/'.join(parts[-2:])
        try:
            return self.client.projects.get(project_path)
        except gitlab.exceptions.GitlabError as e:
            self.logger.error('gitlab_project_not_found', path=project_path, error=str(e))
            raise

    async def trigger_pipeline(
        self, repo_url: str, ref: str, variables: dict
    ) -> dict | None:
        """Trigger a GitLab CI pipeline."""
        try:
            project = await self.get_project(repo_url)
            pipeline = project.pipelines.create({'ref': ref, 'variables': variables})

            self.logger.info('pipeline_triggered', repo=repo_url, pipeline_id=pipeline.id)

            return {
                'id': pipeline.id,
                'status': pipeline.status,
                'created_at': pipeline.created_at,
            }

        except gitlab.exceptions.GitlabError as e:
            self.logger.error('pipeline_trigger_failed', error=str(e))
            return None

    async def get_pipelines(
        self, repo_url: str, limit: int = 10
    ) -> list[dict]:
        """Get recent pipelines."""
        try:
            project = await self.get_project(repo_url)
            pipelines = project.pipelines.list(per_page=limit, order_by='id', sort='desc')

            return [
                {
                    'id': p.id,
                    'status': p.status,
                    'ref': p.ref,
                    'created_at': p.created_at,
                }
                for p in pipelines
            ]

        except gitlab.exceptions.GitlabError as e:
            self.logger.error('get_pipelines_failed', error=str(e))
            return []

    async def create_file(
        self,
        repo_url: str,
        file_path: str,
        content: str,
        message: str,
        branch: str = 'main',
    ) -> bool:
        """Create a file in the repository."""
        try:
            project = await self.get_project(repo_url)
            project.files.create({
                'file_path': file_path,
                'branch': branch,
                'content': content,
                'commit_message': message,
            })

            self.logger.info('file_created', path=file_path, repo=repo_url)
            return True

        except gitlab.exceptions.GitlabError as e:
            self.logger.error('file_creation_failed', error=str(e))
            return False

    async def get_file(
        self, repo_url: str, file_path: str, ref: str = 'main'
    ) -> str | None:
        """Get file content."""
        try:
            project = await self.get_project(repo_url)
            file = project.files.get(file_path=file_path, ref=ref)
            return file.decode()

        except gitlab.exceptions.GitlabError as e:
            self.logger.error('get_file_failed', path=file_path, error=str(e))
            return None
```

- [ ] **Step 3: Criar argocd_client.py**

```python
from typing import Any
from structlog import get_logger
import httpx

from src.config.settings import settings


class ArgoCDClient:
    """Client for interacting with ArgoCD API."""

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        namespace: str | None = None,
    ):
        self.url = (url or settings.argocd_url).rstrip('/')
        self.token = token or settings.argocd_token
        self.namespace = namespace or settings.argocd_namespace
        self.logger = get_logger()

        if not self.token:
            raise ValueError('ArgoCD token is required')

        self.client = httpx.AsyncClient(
            base_url=f'{self.url}/api/v1',
            headers={'Authorization': f'Bearer {self.token}'},
            timeout=30.0,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

    async def create_application(
        self,
        name: str,
        project: str = 'default',
        repo_url: str = '',
        revision: str = 'HEAD',
        path: str = '.',
        destination_namespace: str = 'default',
    ) -> dict | None:
        """Create an ArgoCD Application."""
        manifest = {
            'apiVersion': 'argoproj.io/v1alpha1',
            'kind': 'Application',
            'metadata': {'name': name, 'namespace': self.namespace},
            'spec': {
                'project': project,
                'source': {
                    'repoURL': repo_url,
                    'targetRevision': revision,
                    'path': path,
                },
                'destination': {
                    'server': 'https://kubernetes.default.svc',
                    'namespace': destination_namespace,
                },
                'syncPolicy': {
                    'automated': {
                        'prune': True,
                        'selfHeal': True,
                    },
                },
            },
        }

        try:
            response = await self.client.post('/applications', json=manifest)
            response.raise_for_status()

            self.logger.info('argocd_application_created', name=name)
            return response.json()

        except httpx.HTTPError as e:
            self.logger.error('argocd_create_failed', name=name, error=str(e))
            return None

    async def sync_application(self, name: str) -> bool:
        """Trigger a sync for an application."""
        try:
            response = await self.client.post(
                f'/applications/{name}/sync',
                json={'dryRun': False},
            )
            response.raise_for_status()

            self.logger.info('argocd_sync_triggered', name=name)
            return True

        except httpx.HTTPError as e:
            self.logger.error('argocd_sync_failed', name=name, error=str(e))
            return False

    async def get_application(self, name: str) -> dict | None:
        """Get application details."""
        try:
            response = await self.client.get(f'/applications/{name}')
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            self.logger.error('argocd_get_failed', name=name, error=str(e))
            return None

    async def get_application_health(self, name: str) -> str | None:
        """Get application health status."""
        app = await self.get_application(name)
        if app:
            return app.get('status', {}).get('health', {}).get('status')
        return None

    async def wait_for_health(
        self, name: str, timeout_seconds: int = 300
    ) -> bool:
        """Wait for application to become healthy."""
        import asyncio

        for _ in range(timeout_seconds // 10):
            health = await self.get_application_health(name)
            if health == 'Healthy':
                self.logger.info('argocd_application_healthy', name=name)
                return True

            await asyncio.sleep(10)

        self.logger.warning('argocd_application_timeout', name=name)
        return False

    async def rollback_application(
        self, name: str, revision: str | None = None
    ) -> bool:
        """Rollback an application to a previous revision."""
        try:
            response = await self.client.post(
                f'/applications/{name}/rollback',
                json={'revision': revision} if revision else {},
            )
            response.raise_for_status()

            self.logger.info('argocd_rollback_triggered', name=name)
            return True

        except httpx.HTTPError as e:
            self.logger.error('argocd_rollback_failed', name=name, error=str(e))
            return False
```

- [ ] **Step 4: Escrever testes dos clientes**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.clients.github_client import GitHubClient
from src.clients.gitlab_client import GitLabClient
from src.clients.argocd_client import ArgoCDClient


@pytest.mark.asyncio
async def test_github_create_workflow_dispatch():
    with patch('src.clients.github_client.Github') as mock_github:
        mock_repo = MagicMock()
        mock_repo.create_workflow_dispatch = MagicMock()

        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_client

        client = GitHubClient(token='test-token')

        result = await client.create_workflow_dispatch(
            'https://github.com/org/repo',
            'ci.yml',
            'main',
            {'version': '1.0.0'},
        )

        assert result is True
        mock_repo.create_workflow_dispatch.assert_called_once()


@pytest.mark.asyncio
async def test_gitlab_trigger_pipeline():
    with patch('src.clients.gitlab_client.gitlab') as mock_gitlab:
        mock_project = MagicMock()
        mock_pipeline = MagicMock()
        mock_pipeline.id = '123'
        mock_pipeline.status = 'pending'
        mock_pipeline.created_at = '2026-03-27T00:00:00Z'

        mock_project.pipelines.create.return_value = mock_pipeline

        mock_gl = MagicMock()
        mock_gl.projects.get.return_value = mock_project
        mock_gitlab.Gitlab.return_value = mock_gl

        client = GitLabClient(token='test-token')

        result = await client.trigger_pipeline(
            'https://gitlab.com/org/repo',
            'main',
            {'VERSION': '1.0.0'},
        )

        assert result is not None
        assert result['id'] == '123'


@pytest.mark.asyncio
async async def test_argocd_create_application():
    with patch('httpx.AsyncClient') as mock_httpx:
        mock_response = MagicMock()
        mock_response.json.return_value = {'metadata': {'name': 'test-app'}}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        mock_httpx.return_value = mock_client

        client = ArgoCDClient(url='http://argocd', token='test-token')

        result = await client.create_application(
            name='test-app',
            repo_url='https://github.com/org/repo',
        )

        assert result is not None
        assert result['metadata']['name'] == 'test-app'


@pytest.mark.asyncio
async async def test_argocd_sync_application():
    with patch('httpx.AsyncClient') as mock_httpx:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        mock_httpx.return_value = mock_client

        client = ArgoCDClient(url='http://argocd', token='test-token')

        result = await client.sync_application('test-app')

        assert result is True


@pytest.mark.asyncio
async async def test_argocd_get_application_health():
    with patch('httpx.AsyncClient') as mock_httpx:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': {
                'health': {
                    'status': 'Healthy'
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        mock_httpx.return_value = mock_client

        client = ArgoCDClient(url='http://argocd', token='test-token')

        health = await client.get_application_health('test-app')

        assert health == 'Healthy'
```

- [ ] **Step 5: Executar testes**

```bash
cd services/software-engineering-pipeline
pytest tests/unit/test_clients.py -v
```

- [ ] **Step 6: Commit**

```bash
git add services/software-engineering-pipeline/src/clients/ \
        services/software-engineering-pipeline/tests/unit/test_clients.py
git commit -m "feat(pipeline): adiciona clientes GitHub/GitLab/ArgoCD"
```

---

## Task 8: API REST Router

**Arquivos:**
- Criar: `services/software-engineering-pipeline/src/api/router.py`
- Criar: `services/software-engineering-pipeline/src/api/dependencies.py`
- Test: `services/software-engineering-pipeline/tests/integration/test_api.py`

- [ ] **Step 1: Criar dependencies.py**

```python
from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorClient

from src.config.settings import settings
from src.repositories.pipeline_repository import (
    PipelineManifestRepository,
    PipelineRunRepository,
    AnomalyRepository,
    InsightsRepository,
)
from src.generators.stack_detector import StackDetector
from src.generators.github_actions import GitHubActionsGenerator
from src.orchestrators.pipeline_orchestrator import PipelineOrchestrator
from src.intelligence.anomaly_detector import AnomalyDetector
from src.intelligence.insights_generator import InsightsGenerator
from src.clients.github_client import GitHubClient
from src.clients.gitlab_client import GitLabClient
from src.clients.argocd_client import ArgoCDClient


async def get_mongodb_client() -> AsyncIOMotorClient:
    """Dependency for MongoDB client."""
    return AsyncIOMotorClient(settings.mongodb_url)


async def get_manifest_repository(
    client: AsyncIOMotorClient = Depends(get_mongodb_client),
) -> PipelineManifestRepository:
    """Dependency for manifest repository."""
    return PipelineManifestRepository(client)


async def get_run_repository(
    client: AsyncIOMotorClient = Depends(get_mongodb_client),
) -> PipelineRunRepository:
    """Dependency for run repository."""
    return PipelineRunRepository(client)


async def get_anomaly_repository(
    client: AsyncIOMotorClient = Depends(get_mongodb_client),
) -> AnomalyRepository:
    """Dependency for anomaly repository."""
    return AnomalyRepository(client)


async def get_insights_repository(
    client: AsyncIOMotorClient = Depends(get_mongodb_client),
) -> InsightsRepository:
    """Dependency for insights repository."""
    return InsightsRepository(client)


async def get_stack_detector() -> StackDetector:
    """Dependency for stack detector."""
    return StackDetector(file_list=[], file_contents={})


async def get_github_generator() -> GitHubActionsGenerator:
    """Dependency for GitHub Actions generator."""
    return GitHubActionsGenerator(
        pipeline_name='Neural Hive CI/CD',
        docker_registry=settings.docker_registry,
    )


async def get_orchestrator() -> PipelineOrchestrator:
    """Dependency for pipeline orchestrator."""
    return PipelineOrchestrator()


async def get_anomaly_detector() -> AnomalyDetector:
    """Dependency for anomaly detector."""
    return AnomalyDetector()


async def get_insights_generator() -> InsightsGenerator:
    """Dependency for insights generator."""
    return InsightsGenerator()


async def get_github_client() -> GitHubClient:
    """Dependency for GitHub client."""
    return GitHubClient()


async def get_gitlab_client() -> GitLabClient:
    """Dependency for GitLab client."""
    return GitLabClient()


async def get_argocd_client() -> ArgoCDClient:
    """Dependency for ArgoCD client."""
    return ArgoCDClient()
```

- [ ] **Step 2: Criar router.py**

```python
from datetime import datetime, timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from src.api.dependencies import (
    get_manifest_repository,
    get_run_repository,
    get_anomaly_repository,
    get_insights_repository,
    get_stack_detector,
    get_github_generator,
    get_orchestrator,
    get_anomaly_detector,
    get_insights_generator,
    get_github_client,
    get_gitlab_client,
    get_argocd_client,
)
from src.models.pipeline import (
    PipelineManifest,
    PipelineRun,
    DeployRequest,
    DeployResponse,
    RollbackRequest,
    Anomaly,
    InsightsReport,
)
from src.repositories.pipeline_repository import (
    PipelineManifestRepository,
    PipelineRunRepository,
    AnomalyRepository,
    InsightsRepository,
)
from src.generators.stack_detector import StackDetector
from src.generators.github_actions import GitHubActionsGenerator
from src.orchestrators.pipeline_orchestrator import PipelineOrchestrator
from src.intelligence.insights_generator import InsightsGenerator
from src.clients.github_client import GitHubClient
from src.clients.argocd_client import ArgoCDClient

router = APIRouter()


@router.post('/pipeline/generate', response_model=PipelineManifest)
async def generate_pipeline(
    repo_url: str = Query(..., description='Repository URL'),
    branch: str = Query('main', description='Branch name'),
    provider: str = Query('github_actions', description='CI/CD provider'),
    overrides: dict = {},
    stack_detector: StackDetector = Depends(get_stack_detector),
    generator: GitHubActionsGenerator = Depends(get_github_generator),
    manifest_repo: PipelineManifestRepository = Depends(get_manifest_repository),
):
    """Generate a CI/CD pipeline for a repository."""
    # Detect stack from repository
    detection = await stack_detector.detect()

    if not detection.detected:
        raise HTTPException(
            status_code=400,
            detail=f'Could not detect project stack. Confidence: {detection.confidence}',
        )

    # Generate pipeline
    config = {
        'stack': detection.stack.model_dump(),
        'stages': overrides.get('stages', {}),
    }

    manifest = await generator.generate(config)

    # Save manifest
    manifest_doc = PipelineManifest(
        manifest_id=f'manifest-{datetime.utcnow().timestamp()}',
        repo_url=repo_url,
        branch=branch,
        provider=provider,
        content=manifest.content,
        stack=detection.stack.model_dump(),
    )

    await manifest_repo.upsert_by_repo(repo_url, branch, manifest_doc)

    return manifest_doc


@router.get('/pipeline/templates')
async def list_templates(
    provider: str | None = Query(None, description='Filter by provider'),
):
    """List available pipeline templates."""
    templates = [
        {
            'name': 'github-actions-python',
            'description': 'GitHub Actions for Python projects with Docker',
            'provider': 'github_actions',
            'language': 'python',
            'template': '...',
        },
        {
            'name': 'github-actions-node',
            'description': 'GitHub Actions for Node.js projects',
            'provider': 'github_actions',
            'language': 'node',
            'template': '...',
        },
    ]

    if provider:
        templates = [t for t in templates if t['provider'] == provider]

    return templates


@router.post('/pipeline/deploy', response_model=DeployResponse)
async def trigger_deploy(
    request: DeployRequest,
    orchestrator: PipelineOrchestrator = Depends(get_orchestrator),
    run_repo: PipelineRunRepository = Depends(get_run_repository),
    github_client: GitHubClient = Depends(get_github_client),
):
    """Trigger a deployment pipeline."""
    run_id = f'run-{datetime.utcnow().timestamp()}'

    run = PipelineRun(
        run_id=run_id,
        manifest_id=f'manifest-{request.repo_url}',
        repo_url=request.repo_url,
        git_sha=request.git_sha,
        status='pending',
    )

    await run_repo.create(run)

    # Trigger GitHub Actions workflow if applicable
    if request.provider == 'github_actions':
        await github_client.create_workflow_dispatch(
            request.repo_url,
            'ci-cd.yml',
            request.branch,
            {'git_sha': request.git_sha, 'environment': request.environment},
        )

    return DeployResponse(
        run_id=run_id,
        status='pending',
        message=f'Deployment initiated for {request.repo_url}',
    )


@router.get('/pipeline/status/{run_id}')
async def get_run_status(
    run_id: str,
    run_repo: PipelineRunRepository = Depends(get_run_repository),
):
    """Get the status of a pipeline run."""
    run = await run_repo.find_by_id(run_id)

    if not run:
        raise HTTPException(status_code=404, detail='Run not found')

    return {
        'run_id': run['run_id'],
        'status': run['status'],
        'current_stage': run.get('current_stage'),
        'stages_completed': run.get('stages_completed', []),
        'stages_failed': run.get('stages_failed', []),
        'started_at': run.get('started_at'),
        'finished_at': run.get('finished_at'),
        'duration_seconds': run.get('duration_seconds'),
        'logs_url': run.get('logs_url'),
    }


@router.post('/pipeline/rollback/{run_id}')
async def rollback_deployment(
    run_id: str,
    reason: str = Query(..., description='Reason for rollback'),
    force: bool = Query(False, description='Force rollback'),
    orchestrator: PipelineOrchestrator = Depends(get_orchestrator),
    run_repo: PipelineRunRepository = Depends(get_run_repository),
):
    """Rollback a deployment."""
    run_doc = await run_repo.find_by_id(run_id)
    if not run_doc:
        raise HTTPException(status_code=404, detail='Run not found')

    request = RollbackRequest(run_id=run_id, reason=reason, force=force)

    run = PipelineRun(**run_doc)
    result = await orchestrator.rollback(
        request, {'run': run, 'run_id': run_id}
    )

    await run_repo.update_status(
        run_id,
        result.status,
        rollback_reason=reason,
        rollback_run_id=result.rollback_run_id,
    )

    return {
        'run_id': run_id,
        'status': result.status,
        'message': f'Rollback initiated: {reason}',
    }


@router.get('/pipeline/insights')
async def get_insights(
    repo_url: str = Query(..., description='Repository URL'),
    timeframe_days: int = Query(30, description='Timeframe in days'),
    insights_repo: InsightsRepository = Depends(get_insights_repository),
    insights_generator: InsightsGenerator = Depends(get_insights_generator),
    run_repo: PipelineRunRepository = Depends(get_run_repository),
):
    """Get insights for a repository."""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=timeframe_days)

    # Get runs for the timeframe
    runs = await run_repo.find_by_date_range(repo_url, start_date, end_date)

    # Generate insights
    report = await insights_generator.generate_insights(
        repo_url, runs, start_date, end_date
    )

    # Save report
    await insights_repo.create(report)

    return report


@router.get('/pipeline/anomalies')
async def list_anomalies(
    repo_url: str = Query(..., description='Repository URL'),
    severity: str | None = Query(None, description='Filter by severity'),
    anomaly_repo: AnomalyRepository = Depends(get_anomaly_repository),
):
    """List anomalies for a repository."""
    anomalies = await anomaly_repo.find_unresolved(repo_url)

    if severity:
        anomalies = [a for a in anomalies if a.get('severity') == severity]

    return anomalies


@router.post('/pipeline/anomalies/{anomaly_id}/resolve')
async def resolve_anomaly(
    anomaly_id: str,
    anomaly_repo: AnomalyRepository = Depends(get_anomaly_repository),
):
    """Mark an anomaly as resolved."""
    resolved = await anomaly_repo.mark_resolved(anomaly_id)

    if not resolved:
        raise HTTPException(status_code=404, detail='Anomaly not found')

    return {'anomaly_id': anomaly_id, 'resolved': True}


@router.get('/pipeline/health/{repo_url:path}')
async def get_repo_health(
    repo_url: str,
    run_repo: PipelineRunRepository = Depends(get_run_repository),
):
    """Get health metrics for a repository."""
    success_rate = await run_repo.get_success_rate(repo_url, days=30)

    # Get recent anomalies
    # This would query anomaly repository

    return {
        'repo_url': repo_url,
        'health_score': int(success_rate * 100),
        'trend': 'up' if success_rate > 0.8 else 'down' if success_rate < 0.5 else 'stable',
        'success_rate_30d': success_rate,
        'top_violations': [],
    }
```

- [ ] **Step 3: Escrever testes de integração da API**

```python
import pytest
from httpx import AsyncClient
from fastapi import FastAPI

from src.main import app as main_app
from src.api.router import router


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.mark.asyncio
async async def test_list_templates(app):
    async with AsyncClient(app=app, base_url='http://test') as client:
        response = await client.get('/api/v1/pipeline/templates')

        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        assert 'name' in data[0]
        assert 'provider' in data[0]


@pytest.mark.asyncio
async async def test_list_templates_filtered(app):
    async with AsyncClient(app=app, base_url='http://test') as client:
        response = await client.get(
            '/api/v1/pipeline/templates',
            params={'provider': 'github_actions'},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(t['provider'] == 'github_actions' for t in data)


@pytest.mark.asyncio
async async def test_get_health_invalid_repo(app):
    async with AsyncClient(app=app, base_url='http://test') as client:
        response = await client.get(
            '/api/v1/pipeline/health/https://github.com/org/nonexistent'
        )

        # Should return health with 0% for non-existent repo
        assert response.status_code == 200
        data = response.json()
        assert 'health_score' in data
```

- [ ] **Step 4: Executar testes**

```bash
cd services/software-engineering-pipeline
pytest tests/integration/test_api.py -v
```

- [ ] **Step 5: Commit**

```bash
git add services/software-engineering-pipeline/src/api/ \
        services/software-engineering-pipeline/tests/integration/test_api.py
git commit -m "feat(pipeline): adiciona API REST com endpoints principais"
```

---

## Task 9: Métricas Prometheus e Observabilidade

**Arquivos:**
- Criar: `services/software-engineering-pipeline/src/observability/metrics.py`
- Criar: `services/software-engineering-pipeline/src/observability/tracing.py`
- Test: `services/software-engineering-pipeline/tests/unit/test_metrics.py`

- [ ] **Step 1: Criar metrics.py**

```python
from prometheus_client import Counter, Histogram, Gauge, Summary
from structlog import get_logger


class PipelineMetrics:
    """Prometheus metrics for pipeline operations."""

    def __init__(self):
        self.logger = get_logger()

        # Pipeline runs
        self.pipeline_runs_total = Counter(
            'pipeline_runs_total',
            'Total number of pipeline runs',
            ['repo_url', 'status', 'environment'],
        )

        self.pipeline_duration_seconds = Histogram(
            'pipeline_duration_seconds',
            'Pipeline execution duration in seconds',
            ['repo_url', 'stage'],
            buckets=[10, 30, 60, 120, 300, 600, 1800, 3600],
        )

        self.pipeline_running = Gauge(
            'pipeline_running',
            'Number of currently running pipelines',
            ['repo_url'],
        )

        # Anomalies
        self.anomalies_detected_total = Counter(
            'anomalies_detected_total',
            'Total number of anomalies detected',
            ['repo_url', 'type', 'severity'],
        )

        self.anomalies_resolved_total = Counter(
            'anomalies_resolved_total',
            'Total number of anomalies resolved',
            ['repo_url', 'type'],
        )

        # Deployments
        self.deployments_total = Counter(
            'deployments_total',
            'Total number of deployments',
            ['repo_url', 'environment', 'status'],
        )

        self.rollbacks_total = Counter(
            'rollbacks_total',
            'Total number of rollbacks',
            ['repo_url', 'environment', 'reason'],
        )

        # Insights
        self.insights_generated_total = Counter(
            'insights_generated_total',
            'Total number of insights generated',
            ['repo_url', 'insight_type'],
        )

        # Performance
        self.flaky_tests_total = Gauge(
            'flaky_tests_total',
            'Number of flaky tests',
            ['repo_url'],
        )

        self.slow_tests_total = Gauge(
            'slow_tests_total',
            'Number of slow tests',
            ['repo_url'],
        )

        # Success rate
        self.success_rate = Gauge(
            'pipeline_success_rate',
            'Pipeline success rate',
            ['repo_url', 'environment'],
        )

    def record_pipeline_start(self, repo_url: str, environment: str) -> None:
        """Record the start of a pipeline run."""
        self.pipeline_running.labels(repo_url=repo_url).inc()

    def record_pipeline_complete(
        self, repo_url: str, status: str, environment: str, duration_seconds: float
    ) -> None:
        """Record the completion of a pipeline run."""
        self.pipeline_running.labels(repo_url=repo_url).dec()
        self.pipeline_runs_total.labels(
            repo_url=repo_url,
            status=status,
            environment=environment,
        ).inc()
        self.pipeline_duration_seconds.labels(
            repo_url=repo_url,
            stage='total',
        ).observe(duration_seconds)

    def record_stage_duration(
        self, repo_url: str, stage: str, duration_seconds: float
    ) -> None:
        """Record the duration of a pipeline stage."""
        self.pipeline_duration_seconds.labels(
            repo_url=repo_url,
            stage=stage,
        ).observe(duration_seconds)

    def record_anomaly_detected(
        self, repo_url: str, anomaly_type: str, severity: str
    ) -> None:
        """Record an anomaly detection."""
        self.anomalies_detected_total.labels(
            repo_url=repo_url,
            type=anomaly_type,
            severity=severity,
        ).inc()

    def record_anomaly_resolved(self, repo_url: str, anomaly_type: str) -> None:
        """Record an anomaly resolution."""
        self.anomalies_resolved_total.labels(
            repo_url=repo_url,
            type=anomaly_type,
        ).inc()

    def record_deployment(
        self, repo_url: str, environment: str, status: str
    ) -> None:
        """Record a deployment."""
        self.deployments_total.labels(
            repo_url=repo_url,
            environment=environment,
            status=status,
        ).inc()

    def record_rollback(
        self, repo_url: str, environment: str, reason: str
    ) -> None:
        """Record a rollback."""
        self.rollbacks_total.labels(
            repo_url=repo_url,
            environment=environment,
            reason=reason,
        ).inc()

    def update_flaky_tests(self, repo_url: str, count: int) -> None:
        """Update the flaky tests count."""
        self.flaky_tests_total.labels(repo_url=repo_url).set(count)

    def update_slow_tests(self, repo_url: str, count: int) -> None:
        """Update the slow tests count."""
        self.slow_tests_total.labels(repo_url=repo_url).set(count)

    def update_success_rate(self, repo_url: str, environment: str, rate: float) -> None:
        """Update the success rate gauge."""
        self.success_rate.labels(
            repo_url=repo_url,
            environment=environment,
        ).set(rate)


# Global metrics instance
metrics = PipelineMetrics()
```

- [ ] **Step 2: Atualizar main.py com métricas**

```python
# Adicionar imports
from src.observability.metrics import metrics

# Atualizar health_check endpoint
@app.get('/health')
async def health_check() -> dict[str, str]:
    metrics.pipeline_runs_total.labels(
        repo_url='system',
        status='health_check',
        environment='internal',
    ).inc()
    return {'status': 'healthy', 'service': settings.app_name}
```

- [ ] **Step 3: Escrever testes das métricas**

```python
import pytest
from src.observability.metrics import PipelineMetrics, metrics


def test_metrics_initialization():
    m = PipelineMetrics()

    assert m.pipeline_runs_total is not None
    assert m.pipeline_duration_seconds is not None
    assert m.anomalies_detected_total is not None


def test_record_pipeline_start():
    m = PipelineMetrics()

    m.record_pipeline_start('https://github.com/org/repo', 'staging')

    # Verify metric was incremented
    # Note: In real test, would use prometheus_client registry to get value


def test_record_pipeline_complete():
    m = PipelineMetrics()

    m.record_pipeline_complete(
        repo_url='https://github.com/org/repo',
        status='success',
        environment='staging',
        duration_seconds=120.5,
    )

    # Verify metrics were recorded


def test_record_anomaly_detected():
    m = PipelineMetrics()

    m.record_anomaly_detected(
        repo_url='https://github.com/org/repo',
        anomaly_type='flaky_test',
        severity='medium',
    )

    # Verify counter was incremented


def test_update_flaky_tests():
    m = PipelineMetrics()

    m.update_flaky_tests('https://github.com/org/repo', 5)

    # Verify gauge was set


def test_update_success_rate():
    m = PipelineMetrics()

    m.update_success_rate('https://github.com/org/repo', 'production', 0.85)

    # Verify gauge was set to 0.85
```

- [ ] **Step 4: Executar testes**

```bash
cd services/software-engineering-pipeline
pytest tests/unit/test_metrics.py -v
```

- [ ] **Step 5: Commit**

```bash
git add services/software-engineering-pipeline/src/observability/ \
        services/software-engineering-pipeline/tests/unit/test_metrics.py
git commit -m "feat(pipeline): adiciona métricas Prometheus e observabilidade"
```

---

## Task 10: Helm Chart e Deploy Kubernetes

**Arquivos:**
- Criar: `services/software-engineering-pipeline/helm/software-engineering-pipeline/Chart.yaml`
- Criar: `services/software-engineering-pipeline/helm/software-engineering-pipeline/values.yaml`
- Criar: `services/software-engineering-pipeline/helm/software-engineering-pipeline/templates/deployment.yaml`
- Criar: `services/software-engineering-pipeline/helm/software-engineering-pipeline/templates/service.yaml`
- Criar: `services/software-engineering-pipeline/helm/software-engineering-pipeline/templates/configmap.yaml`
- Criar: `services/software-engineering-pipeline/helm/software-engineering-pipeline/templates/secrets.yaml`

- [ ] **Step 1: Criar Chart.yaml**

```yaml
apiVersion: v2
name: software-engineering-pipeline
description: CI/CD Pipeline Automation Service for Neural Hive Mind
type: application
version: 1.0.0
appVersion: 1.0.0
keywords:
  - ci-cd
  - pipeline
  - automation
maintainers:
  - name: Neural Hive Mind
    email: dev@neuralhive.ai
```

- [ ] **Step 2: Criar values.yaml**

```yaml
replicaCount: 2

image:
  repository: ghcr.io/neural-hive-mind/software-engineering-pipeline
  pullPolicy: IfNotPresent
  tag: 1.0.0

imagePullSecrets: []

service:
  type: ClusterIP
  port: 8008
  annotations: {}

ingress:
  enabled: false
  className: nginx
  annotations: {}
  hosts:
    - host: pipeline.neuralhive.local
      paths:
        - path: /
          pathType: Prefix
  tls: []

resources:
  limits:
    cpu: 1000m
    memory: 512Mi
  requests:
    cpu: 250m
    memory: 256Mi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80

config:
  mongodb:
    url: mongodb://mongodb:27017
    db_name: pipeline_db
  kafka:
    bootstrap_servers: kafka:9092
    group_id: pipeline-service
  docker:
    registry: ghcr.io
  intelligence:
    anomalyDetectionEnabled: true
    flakyTestThreshold: 3
    insightsRetentionDays: 90

secrets:
  githubToken: ''
  gitlabToken: ''
  jenkins:
    url: ''
    username: ''
    password: ''
  argocd:
    url: ''
    token: ''
  docker:
    registryUsername: ''
    registryPassword: ''

nodeSelector: {}

tolerations: []

affinity: {}
```

- [ ] **Step 3: Criar deployment.yaml**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "software-engineering-pipeline.fullname" . }}
  labels:
    {{- include "software-engineering-pipeline.labels" . | nindent 4 }}
spec:
  {{- if not .Values.autoscaling.enabled }}
  replicas: {{ .Values.replicaCount }}
  {{- end }}
  selector:
    matchLabels:
      {{- include "software-engineering-pipeline.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8008"
        prometheus.io/path: "/metrics"
      labels:
        {{- include "software-engineering-pipeline.selectorLabels" . | nindent 8 }}
    spec:
      {{- with .Values.imagePullSecrets }}
      imagePullSecrets:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      containers:
        - name: {{ .Chart.Name }}
          securityContext:
            {{- toYaml .Values.securityContext | nindent 12 }}
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - name: http
              containerPort: {{ .Values.service.port }}
              protocol: TCP
          livenessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 30
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 10
            periodSeconds: 5
            timeoutSeconds: 3
            failureThreshold: 3
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
          env:
            - name: MONGODB_URL
              valueFrom:
                configMapKeyRef:
                  name: {{ include "software-engineering-pipeline.fullname" . }}-config
                  key: mongodb-url
            - name: KAFKA_BOOTSTRAP_SERVERS
              valueFrom:
                configMapKeyRef:
                  name: {{ include "software-engineering-pipeline.fullname" . }}-config
                  key: kafka-bootstrap-servers
            - name: GITHUB_TOKEN
              valueFrom:
                secretKeyRef:
                  name: {{ include "software-engineering-pipeline.fullname" . }}-secrets
                  key: github-token
            - name: GITLAB_TOKEN
              valueFrom:
                secretKeyRef:
                  name: {{ include "software-engineering-pipeline.fullname" . }}-secrets
                  key: gitlab-token
            - name: ARGOCD_URL
              valueFrom:
                secretKeyRef:
                  name: {{ include "software-engineering-pipeline.fullname" . }}-secrets
                  key: argocd-url
            - name: ARGOCD_TOKEN
              valueFrom:
                secretKeyRef:
                  name: {{ include "software-engineering-pipeline.fullname" . }}-secrets
                  key: argocd-token
            - name: DOCKER_REGISTRY
              valueFrom:
                configMapKeyRef:
                  name: {{ include "software-engineering-pipeline.fullname" . }}-config
                  key: docker-registry
            - name: DOCKER_REGISTRY_USERNAME
              valueFrom:
                secretKeyRef:
                  name: {{ include "software-engineering-pipeline.fullname" . }}-secrets
                  key: docker-registry-username
            - name: DOCKER_REGISTRY_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: {{ include "software-engineering-pipeline.fullname" . }}-secrets
                  key: docker-registry-password
      {{- with .Values.nodeSelector }}
      nodeSelector:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.affinity }}
      affinity:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.tolerations }}
      tolerations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
```

- [ ] **Step 4: Criar service.yaml**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "software-engineering-pipeline.fullname" . }}
  labels:
    {{- include "software-engineering-pipeline.labels" . | nindent 4 }}
  {{- with .Values.service.annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
spec:
  type: {{ .Values.service.type }}
  ports:
    - port: {{ .Values.service.port }}
      targetPort: http
      protocol: TCP
      name: http
  selector:
    {{- include "software-engineering-pipeline.selectorLabels" . | nindent 4 }}
```

- [ ] **Step 5: Criar configmap.yaml**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "software-engineering-pipeline.fullname" . }}-config
  labels:
    {{- include "software-engineering-pipeline.labels" . | nindent 4 }}
data:
  mongodb-url: {{ .Values.config.mongodb.url | quote }}
  kafka-bootstrap-servers: {{ .Values.config.kafka.bootstrap_servers | quote }}
  docker-registry: {{ .Values.config.docker.registry | quote }}
  intelligence-anomaly-detection-enabled: {{ .Values.config.intelligence.anomalyDetectionEnabled | quote }}
  intelligence-flaky-test-threshold: {{ .Values.config.intelligence.flakyTestThreshold | quote }}
```

- [ ] **Step 6: Criar secrets.yaml**

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: {{ include "software-engineering-pipeline.fullname" . }}-secrets
  labels:
    {{- include "software-engineering-pipeline.labels" . | nindent 4 }}
type: Opaque
stringData:
  github-token: {{ .Values.secrets.githubToken | quote }}
  gitlab-token: {{ .Values.secrets.gitlabToken | quote }}
  argocd-url: {{ .Values.secrets.argocd.url | quote }}
  argocd-token: {{ .Values.secrets.argocd.token | quote }}
  docker-registry-username: {{ .Values.secrets.docker.registryUsername | quote }}
  docker-registry-password: {{ .Values.secrets.docker.registryPassword | quote }}
```

- [ ] **Step 7: Criar _helpers.tpl**

```yaml
{{/*
Expand the name of the chart.
*/}}
{{- define "software-engineering-pipeline.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "software-engineering-pipeline.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "software-engineering-pipeline.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "software-engineering-pipeline.labels" -}}
helm.sh/chart: {{ include "software-engineering-pipeline.chart" . }}
{{ include "software-engineering-pipeline.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "software-engineering-pipeline.selectorLabels" -}}
app.kubernetes.io/name: {{ include "software-engineering-pipeline.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
```

- [ ] **Step 8: Commit final**

```bash
git add services/software-engineering-pipeline/helm/
git commit -m "feat(pipeline): adiciona Helm chart para deploy Kubernetes"
```

---

## Sumário

Este plano implementa o **Software Engineering Pipeline**, um serviço completo de CI/CD com:

### Componentes Principais
1. **Pipeline Generator** - Detecção automática de stack e geração de pipelines (GitHub, GitLab, Jenkins, Tekton)
2. **Pipeline Orchestrator** - Execução de deploys com 7 estágios (pre-flight, build, test, security, staging, approval, production)
3. **Pipeline Intelligence** - Detecção de anomalias, testes flaky, e insights de performance

### APIs Principais
- `POST /api/v1/pipeline/generate` - Gera pipeline CI/CD
- `POST /api/v1/pipeline/deploy` - Inicia deploy
- `GET /api/v1/pipeline/status/{run_id}` - Status do deploy
- `POST /api/v1/pipeline/rollback/{run_id}` - Rollback
- `GET /api/v1/pipeline/insights` - Insights e otimizações
- `GET /api/v1/pipeline/anomalies` - Lista anomalias

### Métricas Prometheus
- `pipeline_runs_total` - Total de runs
- `pipeline_duration_seconds` - Duração dos estágios
- `anomalies_detected_total` - Anomalias detectadas
- `rollbacks_total` - Rollbacks executados

### Estimativa
- **10 tarefas principais**
- **~50-60 testes** (unit + integration)
- **7-9 dias** de desenvolvimento
- **Meta: 80% cobertura**
