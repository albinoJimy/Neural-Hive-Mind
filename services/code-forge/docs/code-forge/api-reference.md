# API Reference - CodeForge

## Visão Geral

Este documento fornece a referência completa da API do CodeForge, incluindo todas as classes, métodos e parâmetros disponíveis.

## Índice

1. [PipelineEngine](#pipelineengine)
2. [DockerfileGenerator](#dockerfilegenerator)
3. [ContainerBuilder](#containerbuilder)
4. [CodeForgeTicket](#codeforgeticket)
5. [Models e Enums](#models-e-enums)
6. [Clientes Externos](#clientes-externos)
7. [Validadores](#validadores)

---

## PipelineEngine

### Classe Principal

```python
from src.services.pipeline_engine import PipelineEngine
```

### Construtor

```python
def __init__(
    self,
    template_selector: TemplateSelector | None = None,
    code_composer: CodeComposer | None = None,
    dockerfile_generator: DockerfileGenerator | None = None,
    container_builder: ContainerBuilder | None = None,
    validator: Validator | None = None,
    test_runner: TestRunner | None = None,
    packager: Packager | None = None,
    approval_client: ApprovalClient | None = None,
    enable_container_build: bool = True,
    auto_approval_threshold: float = 0.9,
    pipeline_timeout: int = 3600
)
```

**Parâmetros:**

| Nome | Tipo | Default | Descrição |
|------|------|---------|-----------|
| `template_selector` | `TemplateSelector \| None` | `None` | Seletor de templates MCP |
| `code_composer` | `CodeComposer \| None` | `None` | Compositor de código |
| `dockerfile_generator` | `DockerfileGenerator \| None` | `None` | Gerador de Dockerfiles |
| `container_builder` | `ContainerBuilder \| None` | `None` | Builder de containers |
| `validator` | `Validator \| None` | `None` | Validador de código e segurança |
| `test_runner` | `TestRunner \| None` | `None` | Executor de testes |
| `packager` | `Packager \| None` | `None` | Empacotador de artefatos |
| `approval_client` | `ApprovalClient \| None` | `None` | Cliente de aprovação |
| `enable_container_build` | `bool` | `True` | Habilita builds de container |
| `auto_approval_threshold` | `float` | `0.9` | Threshold para auto-aprovação |
| `pipeline_timeout` | `int` | `3600` | Timeout do pipeline em segundos |

### Métodos

#### execute_pipeline

```python
async def execute_pipeline(
    self,
    ticket: CodeForgeTicket
) -> PipelineResult
```

Executa o pipeline completo para um ticket.

**Retorna:** `PipelineResult` com status e metadados da execução.

**Exceções:**
- `ValidationError`: Se os parâmetros do ticket forem inválidos
- `PipelineTimeoutError`: Se o timeout for excedido

**Exemplo:**
```python
result = await engine.execute_pipeline(ticket)
print(result.status)  # "COMPLETED", "FAILED", "REQUIRES_REVIEW"
```

#### execute_stage

```python
async def execute_stage(
    self,
    stage_name: str,
    ticket: CodeForgeTicket,
    context: dict
) -> StageResult
```

Executa um stage específico do pipeline.

**Stages Disponíveis:**
- `template_selection`
- `code_composition`
- `dockerfile_generation`
- `container_build`
- `validation`
- `testing`
- `packaging`
- `approval_gate`

---

## DockerfileGenerator

### Classe Principal

```python
from src.services.dockerfile_generator import (
    DockerfileGenerator,
    SupportedLanguage,
    ArtifactType
)
```

### Construtor

```python
def __init__(self):
    pass
```

### Métodos

#### generate_dockerfile

```python
def generate_dockerfile(
    self,
    language: SupportedLanguage,
    framework: str | None = None,
    artifact_type: ArtifactType = ArtifactType.MICROSERVICE,
    custom_template: str | None = None
) -> str
```

Gera um Dockerfile otimizado para a linguagem e framework especificados.

**Parâmetros:**

| Nome | Tipo | Default | Descrição |
|------|------|---------|-----------|
| `language` | `SupportedLanguage` | *obrigatório* | Linguagem alvo |
| `framework` | `str \| None` | `None` | Framework específico |
| `artifact_type` | `ArtifactType` | `MICROSERVICE` | Tipo de artefato |
| `custom_template` | `str \| None` | `None` | Template customizado |

**Retorna:** `str` - Conteúdo do Dockerfile

**Exceções:**
- `ValueError`: Se linguagem não for suportada

**Exemplo:**
```python
dockerfile = generator.generate_dockerfile(
    language=SupportedLanguage.PYTHON,
    framework="fastapi",
    artifact_type=ArtifactType.MICROSERVICE
)
```

### Linguagens Suportadas

```python
class SupportedLanguage(str, Enum):
    PYTHON = "python"
    NODEJS = "nodejs"
    GOLANG = "golang"
    JAVA = "java"
    TYPESCRIPT = "typescript"
    CSHARP = "csharp"
```

### Tipos de Artefato

```python
class ArtifactType(str, Enum):
    MICROSERVICE = "microservice"
    LAMBDA_FUNCTION = "lambda_function"
    CLI_TOOL = "cli_tool"
    LIBRARY = "library"
```

---

## ContainerBuilder

### Classe Principal

```python
from src.services.container_builder import (
    ContainerBuilder,
    BuilderType,
    ContainerBuildResult
)
```

### Construtor

```python
def __init__(
    self,
    builder_type: BuilderType = BuilderType.DOCKER,
    timeout_seconds: int = 3600
)
```

**Parâmetros:**

| Nome | Tipo | Default | Descrição |
|------|------|---------|-----------|
| `builder_type` | `BuilderType` | `DOCKER` | Tipo de builder |
| `timeout_seconds` | `int` | `3600` | Timeout em segundos |

### Métodos

#### build_container

```python
async def build_container(
    self,
    dockerfile_path: str,
    build_context: str,
    image_tag: str,
    build_args: list[str] | None = None
) -> ContainerBuildResult
```

Executa o build de uma imagem de container.

**Parâmetros:**

| Nome | Tipo | Default | Descrição |
|------|------|---------|-----------|
| `dockerfile_path` | `str` | *obrigatório* | Caminho do Dockerfile |
| `build_context` | `str` | *obrigatório* | Diretório do build context |
| `image_tag` | `str` | *obrigatório* | Tag da imagem |
| `build_args` | `list[str] \| None` | `None` | Argumentos de build |

**Retorna:** `ContainerBuildResult`

**Exemplo:**
```python
result = await builder.build_container(
    dockerfile_path="/path/to/Dockerfile",
    build_context="/path/to/context",
    image_tag="myapp:1.0.0",
    build_args=["ENV=production", "VERSION=1.0.0"]
)
```

### Tipos de Builder

```python
class BuilderType(str, Enum):
    DOCKER = "docker"      # Docker CLI (local)
    KANIKO = "kaniko"     # Kaniko (Kubernetes) - não implementado
    BUILDKIT = "buildkit" # BuildKit - não implementado
```

### ContainerBuildResult

```python
@dataclass
class ContainerBuildResult:
    success: bool              # Build completou com sucesso?
    image_digest: str | None   # SHA256 digest
    size_bytes: int | None     # Tamanho da imagem em bytes
    error_message: str | None  # Mensagem de erro se falhou
    duration_ms: int           # Duração do build em ms
    image_tag: str             # Tag da imagem
```

---

## CodeForgeTicket

### Dataclass

```python
from src.models.codeforge_ticket import CodeForgeTicket, ArtifactType
```

### Definição

```python
@dataclass
class CodeForgeTicket:
    ticket_id: str                          # ID único do ticket
    intent_description: str                 # Descrição da intenção
    parameters: dict[str, Any]              # Parâmetros do artefato
    artifact_type: ArtifactType             # Tipo de artefato
    priority: int = 5                       # Prioridade (1-10)
    created_at: str | None = None           # Timestamp de criação
    requested_by: str | None = None         # Solicitante
    metadata: dict[str, Any] = field(default_factory=dict)  # Metadados adicionais
```

### Parâmetros Esperados em `parameters`

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `language` | `str` | Linguagem: python, nodejs, golang, java, typescript, csharp |
| `framework` | `str \| None` | Framework: fastapi, flask, express, nestjs, etc |
| `artifact_type` | `str` | microservice, lambda_function, cli_tool, library |
| `service_name` | `str` | Nome do serviço |
| `version` | `str` | Versão do artefato |
| `port` | `int \| None` | Porta para microserviços |

### Exemplo

```python
ticket = CodeForgeTicket(
    ticket_id="my-ticket-001",
    intent_description="Create a FastAPI microservice",
    parameters={
        "language": "python",
        "framework": "fastapi",
        "artifact_type": "microservice",
        "service_name": "user-api",
        "version": "1.0.0",
        "port": 8000
    },
    artifact_type=ArtifactType.MICROSERVICE,
    priority=7
)
```

---

## Models e Enums

### PipelineResult

```python
@dataclass
class PipelineResult:
    status: str                           # COMPLETED, FAILED, REQUIRES_REVIEW
    artifacts: list[CodeForgeArtifact]     # Artefatos gerados
    stage_results: dict[str, StageResult]  # Resultados por stage
    metadata: dict[str, Any]               # Metadados da execução
    error_message: str | None              # Mensagem de erro se falhou
    execution_time_ms: int                 # Tempo total de execução
```

### StageResult

```python
@dataclass
class StageResult:
    stage_name: str          # Nome do stage
    status: str              # COMPLETED, FAILED, SKIPPED
    success: bool            # Sucesso da execução
    error_message: str | None # Mensagem de erro se falhou
    metadata: dict[str, Any]  # Metadados do stage
```

### CodeForgeArtifact

```python
@dataclass
class CodeForgeArtifact:
    artifact_id: str              # ID único
    artifact_type: str            # Tipo do artefato
    content_uri: str | None       # URI do conteúdo
    metadata: dict[str, Any]      # Metadados do artefato
    created_at: str               # Timestamp de criação
```

### ArtifactType

```python
class ArtifactType(str, Enum):
    MICROSERVICE = "microservice"
    LAMBDA_FUNCTION = "lambda_function"
    CLI_TOOL = "cli_tool"
    LIBRARY = "library"
    BATCH_JOB = "batch_job"
    WEB_APP = "web_app"
```

---

## Clientes Externos

### TrivyClient

```python
from src.clients.trivy_client import TrivyClient, VulnerabilitySeverity
```

#### Métodos

```python
async def scan_filesystem(
    self,
    path: str,
    severity: list[VulnerabilitySeverity] | None = None
) -> ValidationResult

async def scan_container_image(
    self,
    image_reference: str,
    severity: list[VulnerabilitySeverity] | None = None
) -> ValidationResult
```

#### ValidationResult

```python
@dataclass
class ValidationResult:
    success: bool                       # Validação passou?
    issues_found: int                   # Total de issues
    critical_count: int                 # Issues críticos
    high_count: int                     # Issues altos
    medium_count: int                   # Issues médios
    low_count: int                      # Issues baixos
    details: list[dict[str, Any]]       # Detalhes dos issues
    tool: str                           # Ferramenta usada
```

### ArtifactRegistryClient

```python
from src.clients.artifact_registry_client import ArtifactRegistryClient
```

#### Métodos

```python
async def register_container(
    self,
    artifact_id: str,
    image_tag: str,
    digest: str,
    size_bytes: int,
    metadata: dict[str, Any]
) -> bool

async def get_container_metadata(
    self,
    artifact_id: str
) -> dict[str, Any] | None
```

### SigstoreClient

```python
from src.clients.sigstore_client import SigstoreClient
```

#### Métodos

```python
async def generate_sbom(
    self,
    artifact_path: str,
    format: str = "spdx-json"
) -> str

async def sign_artifact(
    self,
    artifact_path: str
) -> bool
```

---

## Validadores

### Validator

```python
from src.services.validator import Validator
```

#### Construtor

```python
def __init__(
    self,
    trivy_client: TrivyClient | None = None,
    sonarqube_client: SonarQubeClient | None = None,
    snyk_client: Any | None = None,
    enabled_validations: list[str] | None = None
)
```

#### Métodos

```python
async def validate_all(
    self,
    artifact_path: str
) -> dict[str, ValidationResult]

async def validate_vulnerabilities(
    self,
    artifact_path: str
) -> ValidationResult

async def validate_code_quality(
    self,
    artifact_path: str
) -> ValidationResult
```

---

## Packager

```python
from src.services.packager import Packager
```

### Métodos

```python
async def package_artifact(
    self,
    artifact: CodeForgeArtifact,
    source_path: str
) -> str

async def generate_sbom(
    self,
    artifact_path: str
) -> str
```

---

## Exemplos de Uso Rápido

### Pipeline Simples

```python
from src.services.pipeline_engine import PipelineEngine
from src.models.codeforge_ticket import CodeForgeTicket, ArtifactType

# Criar engine
engine = PipelineEngine(
    enable_container_build=False  # Para ambientes sem Docker
)

# Criar ticket
ticket = CodeForgeTicket(
    ticket_id="ticket-001",
    intent_description="Create API service",
    parameters={
        "language": "python",
        "framework": "fastapi"
    },
    artifact_type=ArtifactType.MICROSERVICE
)

# Executar
result = await engine.execute_pipeline(ticket)
```

### Build com Docker

```python
from src.services.container_builder import ContainerBuilder
from src.services.dockerfile_generator import DockerfileGenerator, SupportedLanguage

# Gerar Dockerfile
generator = DockerfileGenerator()
dockerfile = generator.generate_dockerfile(
    language=SupportedLanguage.PYTHON
)

# Salvar e buildar
with open("Dockerfile", "w") as f:
    f.write(dockerfile)

builder = ContainerBuilder()
result = await builder.build_container(
    dockerfile_path="Dockerfile",
    build_context=".",
    image_tag="myapp:1.0.0"
)

if result.success:
    print(f"Build OK: {result.image_digest}")
```

### Validação de Segurança

```python
from src.clients.trivy_client import TrivyClient

client = TrivyClient()
result = await client.scan_filesystem(
    path="/app",
    severity=["CRITICAL", "HIGH"]
)

if result.critical_count > 0:
    print(f"⚠️ {result.critical_count} critical issues found!")
```

---

## Convenções de Nomenclatura

### IDs e Tags

- **Ticket ID**: `{service}-{feature}-{seq}` (ex: `api-users-001`)
- **Image Tag**: `{name}:{version}` (ex: `myapp:1.0.0`)
- **Artifact ID**: UUID v4

### Status

| Status | Descrição |
|--------|-----------|
| `COMPLETED` | Pipeline concluído com sucesso |
| `FAILED` | Pipeline falhou |
| `REQUIRES_REVIEW` | Requer aprovação manual |
| `PENDING` | Aguardando execução |
| `IN_PROGRESS` | Em execução |

### Prioridade

| Valor | Nível |
|-------|-------|
| 1-3 | Baixa |
| 4-6 | Normal |
| 7-8 | Alta |
| 9-10 | Crítica |

---

## Tratamento de Erros

### Exceções Comuns

```python
# Validação
class ValidationError(Exception):
    """Erro de validação de parâmetros"""

# Timeout
class PipelineTimeoutError(Exception):
    """Timeout do pipeline"""

# Build
class BuildError(Exception):
    """Erro no build de container"""

# Comunicação
class ServiceUnavailableError(Exception):
    """Serviço externo indisponível"""
```

### Tratamento Recomendado

```python
from src.services.pipeline_engine import PipelineEngine, PipelineTimeoutError

try:
    result = await engine.execute_pipeline(ticket)
except ValidationError as e:
    logger.error(f"Invalid parameters: {e}")
except PipelineTimeoutError as e:
    logger.error(f"Pipeline timeout: {e}")
except Exception as e:
    logger.error(f"Unexpected error: {e}")
```

---

## Referências Relacionadas

- [Examples](examples.md)
- [Architecture](architecture.md)
- [Troubleshooting](troubleshooting.md)
- [Dockerfile Generator Guide](dockerfile-generator-guide.md)
- [Container Builder Guide](container-builder-guide.md)
