# Fluxo G - Fase 2: Core Services (Requirements + Documentation)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar dois novos serviços core para Fluxo G: Requirements Engineering System (8010) para geração de requisitos funcionais e user stories, e Documentation Generation System (8014) para geração automática de documentação técnica (README, API docs, architecture docs, diagramas).

**Architecture:** Dois serviços FastAPI independentes que integram com serviços existentes. Requirements Engineering consome do STE e produz requisitos estruturados que alimentam o architect-agent. Documentation Generation consome artefatos de código e arquitetura para produzir documentação em múltiplos formatos. Ambos publicam eventos Kafka para orquestração do fluxo.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic, OpenAI API/Anthropic, MongoDB, Redis, Kafka, Mermaid CLI, structlog

---

## Estrutura de Ficheiros

```
services/
├── requirements-engineering/          # NOVO SERVIÇO (porta 8010)
│   ├── src/
│   │   ├── __init__.py
│   │   ├── main.py                     # NOVO - FastAPI app
│   │   ├── config/
│   │   │   ├── __init__.py
│   │   │   └── settings.py             # NOVO - Configurações
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── requirements.py         # NOVO - Modelos de requisitos
│   │   │   ├── user_story.py           # NOVO - User stories
│   │   │   ├── acceptance_criteria.py  # NOVO - Critérios de aceitação
│   │   │   └── data_model.py            # NOVO - Modelos de dados
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── requirements_engineer.py    # NOVO - Geração de requisitos
│   │   │   ├── user_story_generator.py     # NOVO - Geração de user stories
│   │   │   ├── acceptance_criteria_generator.py  # NOVO - Critérios
│   │   │   └── data_model_designer.py       # NOVO - Design de modelos
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── routers/
│   │   │       ├── __init__.py
│   │   │       └── requirements.py      # NOVO - Endpoints REST
│   │   ├── consumers/
│   │   │   ├── __init__.py
│   │   │   └── cognitive_plan_consumer.py  # NOVO - Kafka consumer
│   │   └── producers/
│   │       ├── __init__.py
│   │       └── requirements_producer.py     # NOVO - Kafka producer
│   ├── tests/
│   │   ├── unit/
│   │   │   ├── test_requirements_engineer.py
│   │   │   ├── test_user_story_generator.py
│   │   │   └── test_acceptance_criteria_generator.py
│   │   └── integration/
│   │       └── test_requirements_flow.py
│   ├── deployment/
│   │   ├── k8s-deployment.yaml
│   │   ├── k8s-service.yaml
│   │   └── Dockerfile
│   ├── pyproject.toml
│   └── README.md
│
└── documentation-generation/           # NOVO SERVIÇO (porta 8014)
    ├── src/
    │   ├── __init__.py
    │   ├── main.py                     # NOVO - FastAPI app
    │   ├── config/
    │   │   ├── __init__.py
    │   │   └── settings.py             # NOVO - Configurações
    │   ├── models/
    │   │   ├── __init__.py
    │   │   ├── documentation.py         # NOVO - Modelos de docs
    │   │   └── diagram.py               # NOVO - Modelos de diagramas
    │   ├── services/
    │   │   ├── __init__.py
    │   │   ├── readme_generator.py      # NOVO - Geração de README
    │   │   ├── api_docs_generator.py    # NOVO - OpenAPI/Swagger
    │   │   ├── architecture_docs_generator.py  # NOVO - Docs de arquitetura
    │   │   └── diagram_generator.py     # NOVO - Mermaid diagrams
    │   ├── api/
    │   │   ├── __init__.py
    │   │   └── routers/
    │   │       ├── __init__.py
    │   │       └── documentation.py     # NOVO - Endpoints REST
    │   ├── generators/
    │   │   ├── __init__.py
    │   │   ├── markdown_generator.py    # NOVO - Markdown base
    │   │   └── mermaid_renderer.py      # NOVO - Render Mermaid→SVG
    │   └── producers/
    │       ├── __init__.py
    │       └── docs_producer.py         # NOVO - Kafka producer
    ├── tests/
    │   ├── unit/
    │   │   ├── test_readme_generator.py
    │   │   ├── test_api_docs_generator.py
    │   │   └── test_diagram_generator.py
    │   └── integration/
    │       └── test_documentation_flow.py
    ├── deployment/
    │   ├── k8s-deployment.yaml
    │   ├── k8s-service.yaml
    │   └── Dockerfile
    ├── pyproject.toml
    └── README.md
```

---

# PARTE 1: Requirements Engineering System (8010)

## Task 1: Criar estrutura base do serviço requirements-engineering

**Files:**
- Create: `services/requirements-engineering/pyproject.toml`
- Create: `services/requirements-engineering/src/__init__.py`
- Create: `services/requirements-engineering/src/config/__init__.py`
- Create: `services/requirements-engineering/src/config/settings.py`

- [ ] **Step 1: Criar pyproject.toml**

```toml
# services/requirements-engineering/pyproject.toml
[tool.poetry]
name = "requirements-engineering"
version = "0.1.0"
description = "Requirements Engineering System for Neural Hive-Mind"
authors = ["Neural Hive-Mind Team"]
readme = "README.md"
packages = [{include = "requirements_engineering"}]

[tool.poetry.dependencies]
python = "^3.12"
fastapi = "^0.104.0"
uvicorn = {extras = ["standard"], version = "^0.24.0"}
pydantic = "^2.0"
pydantic-settings = "^2.0"
motor = "^3.0"
redis = {extras = ["hiredis"], version = "^5.0"}
aiokafka = "^0.9.0"
structlog = "^23.0"
openai = "^1.0"
anthropic = "^0.7"
python-multipart = "^0.0.6"

[tool.poetry.group.dev.dependencies]
pytest = "^7.4"
pytest-asyncio = "^0.21"
pytest-cov = "^4.1"
black = "^23.0"
ruff = "^0.1"
mypy = "^1.5"
httpx = "^0.25"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.black]
line-length = 100
target-version = ['py312']

[tool.ruff]
line-length = 100
target-version = "py312"
select = ["E", "F", "I", "N", "W", "UP"]
```

- [ ] **Step 2: Criar settings.py**

```python
# services/requirements-engineering/src/config/settings.py
"""Configurações do Requirements Engineering Service."""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações centralizadas."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="REQ_ENG_",
    )

    # API
    api_title: str = "Requirements Engineering API"
    api_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8010
    debug: bool = False

    # OpenAI/Anthropic
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    llm_provider: str = "openai"  # openai or anthropic
    llm_model: str = "gpt-4-turbo-preview"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4000

    # MongoDB
    mongodb_url: str = Field(
        default="mongodb://localhost:27017",
        validation_alias="MONGODB_URL"
    )
    mongodb_database: str = "requirements_engineering"
    mongodb_collection_requirements: str = "requirements"
    mongodb_collection_user_stories: str = "user_stories"

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias="REDIS_URL"
    )
    redis_cache_ttl: int = 3600  # 1 hora

    # Kafka
    kafka_bootstrap_servers: str = Field(
        default="localhost:9092",
        validation_alias="KAFKA_BOOTSTRAP_SERVERS"
    )
    kafka_consumer_group: str = "requirements-engineering-consumers"
    kafka_input_topic: str = "cognitive.plans.created"
    kafka_output_topic: str = "requirements.generated"
    kafka_dlq_topic: str = "requirements.dlq"

    # Service Discovery
    service_registry_url: str = Field(
        default="http://service-registry:8007",
        validation_alias="SERVICE_REGISTRY_URL"
    )

    # Observabilidade
    enable_tracing: bool = True
    otlp_endpoint: str = Field(
        default="http://jaeger:4317",
        validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    log_level: str = "INFO"

    # Funcionalidades
    enable_user_story_generation: bool = True
    enable_acceptance_criteria: bool = True
    enable_data_model_design: bool = True
    max_requirements_per_plan: int = 50
    max_user_stories_per_requirement: int = 10


@lru_cache
def get_settings() -> Settings:
    """Singleton das configurações."""
    return Settings()
```

- [ ] **Step 3: Criar __init__.py packages**

```python
# services/requirements-engineering/src/__init__.py
"""Requirements Engineering Service."""

__version__ = "0.1.0"
```

```python
# services/requirements-engineering/src/config/__init__.py
"""Configurações do serviço."""

from .settings import get_settings, Settings

__all__ = ["get_settings", "Settings"]
```

- [ ] **Step 4: Commit**

```bash
git add services/requirements-engineering/pyproject.toml \
        services/requirements-engineering/src/__init__.py \
        services/requirements-engineering/src/config/
git commit -m "feat(requirements-engineering): add base structure and settings"
```

---

## Task 2: Criar modelos de dados

**Files:**
- Create: `services/requirements-engineering/src/models/__init__.py`
- Create: `services/requirements-engineering/src/models/requirements.py`
- Create: `services/requirements-engineering/src/models/user_story.py`
- Create: `services/requirements-engineering/src/models/acceptance_criteria.py`
- Create: `services/requirements-engineering/src/models/data_model.py`

- [ ] **Step 1: Criar modelos de requisitos**

```python
# services/requirements-engineering/src/models/requirements.py
"""Modelos de dados para requisitos funcionais."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class RequirementPriority(str, Enum):
    """Prioridade de requisito."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RequirementType(str, Enum):
    """Tipo de requisito."""

    FUNCTIONAL = "functional"
    NON_FUNCTIONAL = "non_functional"
    CONSTRAINT = "constraint"
    ASSUMPTION = "assumption"


class RequirementStatus(str, Enum):
    """Status de requisito."""

    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"


class Requirement(BaseModel):
    """Requisito funcional ou não-funcional."""

    id: str = Field(..., description="ID único do requisito")
    requirement_type: RequirementType = Field(
        default=RequirementType.FUNCTIONAL,
        description="Tipo do requisito"
    )
    priority: RequirementPriority = Field(
        default=RequirementPriority.MEDIUM,
        description="Prioridade do requisito"
    )
    status: RequirementStatus = Field(
        default=RequirementStatus.DRAFT,
        description="Status do requisito"
    )
    title: str = Field(..., min_length=5, max_length=200, description="Título do requisito")
    description: str = Field(
        ...,
        min_length=20,
        description="Descrição detalhada do requisito"
    )
    rationale: str = Field(
        default="",
        description="Justificativa do requisito (por que é necessário)"
    )
    acceptance_criteria_ids: List[str] = Field(
        default_factory=list,
        description="IDs dos critérios de aceitação"
    )
    user_story_ids: List[str] = Field(
        default_factory=list,
        description="IDs das user stories relacionadas"
    )
    dependencies: List[str] = Field(
        default_factory=list,
        description="IDs dos requisitos dos quais depende"
    )
    conflicts: List[str] = Field(
        default_factory=list,
        description="IDs dos requisitos com os quais conflita"
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Tags para categorização"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadados adicionais"
    )
    cognitive_plan_id: Optional[str] = Field(
        None,
        description="ID do CognitivePlan de origem"
    )
    architecture_plan_id: Optional[str] = Field(
        None,
        description="ID do ArchitecturePlan relacionado"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Data de criação"
    )
    updated_at: Optional[datetime] = Field(
        None,
        description="Data da última atualização"
    )
    version: int = Field(default=1, description="Versão do requisito")

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Valida formato do ID."""
        if not v.startswith("REQ-"):
            raise ValueError("ID must start with 'REQ-'")
        return v


class RequirementsSet(BaseModel):
    """Conjunto de requisitos para um projeto."""

    id: str = Field(..., description="ID único do conjunto")
    cognitive_plan_id: str = Field(..., description="ID do CognitivePlan")
    requirements: List[Requirement] = Field(
        default_factory=list,
        description="Lista de requisitos"
    )
    functional_count: int = Field(default=0, description="Contagem de requisitos funcionais")
    non_functional_count: int = Field(default=0, description="Contagem de requisitos não-funcionais")
    total_estimated_points: Optional[int] = Field(
        None,
        description="Pontos de story estimados (total)"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadados do conjunto"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Data de criação"
    )
    updated_at: Optional[datetime] = Field(
        None,
        description="Data da última atualização"
    )

    def add_requirement(self, requirement: Requirement) -> None:
        """Adiciona um requisito ao conjunto."""
        self.requirements.append(requirement)
        if requirement.requirement_type == RequirementType.FUNCTIONAL:
            self.functional_count += 1
        else:
            self.non_functional_count += 1
        self.updated_at = datetime.utcnow()

    def get_by_priority(self, priority: RequirementPriority) -> List[Requirement]:
        """Filtra requisitos por prioridade."""
        return [r for r in self.requirements if r.priority == priority]

    def get_by_type(self, req_type: RequirementType) -> List[Requirement]:
        """Filtra requisitos por tipo."""
        return [r for r in self.requirements if r.requirement_type == req_type]
```

- [ ] **Step 2: Criar modelos de user stories**

```python
# services/requirements-engineering/src/models/user_story.py
"""Modelos de dados para User Stories."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class StorySize(str, Enum):
    """Tamanho estimado da user story (story points)."""

    EXTRA_SMALL = "xs"  # 1 ponto
    SMALL = "s"         # 2 pontos
    MEDIUM = "m"        # 3 pontos
    LARGE = "l"         # 5 pontos
    EXTRA_LARGE = "xl"  # 8+ pontos


class StoryStatus(str, Enum):
    """Status da user story."""

    DRAFT = "draft"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"


class UserStory(BaseModel):
    """User Story representando uma funcionalidade do ponto de vista do utilizador."""

    id: str = Field(..., description="ID único da user story")
    requirement_id: str = Field(..., description="ID do requisito relacionado")
    status: StoryStatus = Field(default=StoryStatus.DRAFT, description="Status da story")
    size: StorySize = Field(default=StorySize.MEDIUM, description="Tamanho estimado")

    # Formato padrão: Como [role], eu quero [feature], para que [benefit]
    role: str = Field(..., description="Papel do utilizador (ex: 'admin', 'utilizador final')")
    action: str = Field(
        ...,
        description="Acção que o utilizador quer realizar (feature desejada)"
    )
    benefit: str = Field(
        ...,
        description="Benefício ou valor que o utilizador obtém"
    )

    # Detalhes adicionais
    description: str = Field(
        default="",
        description="Descrição detalhada da história"
    )
    acceptance_criteria_ids: List[str] = Field(
        default_factory=list,
        description="IDs dos critérios de aceitação"
    )
    tasks: List[str] = Field(
        default_factory=list,
        description="Lista de tarefas técnicas para implementação"
    )
    dependencies: List[str] = Field(
        default_factory=list,
        description="IDs das user stories das quais depende"
    )

    # Metadados
    tags: List[str] = Field(default_factory=list, description="Tags para categorização")
    epic: Optional[str] = Field(None, description="Epic relacionado (se aplicável)")
    sprint: Optional[str] = Field(None, description="Sprint planejado")
    assignee: Optional[str] = Field(None, description="Responsável pela implementação")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Timestamps
    cognitive_plan_id: Optional[str] = Field(None, description="ID do CognitivePlan de origem")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(None)
    completed_at: Optional[datetime] = Field(None)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Valida formato do ID."""
        if not v.startswith("US-"):
            raise ValueError("ID must start with 'US-'")
        return v

    def get_user_story_format(self) -> str:
        """Retorna a user story no formato padrão."""
        return f"Como {self.role}, eu quero {self.action}, para que {self.benefit}."


class UserStorySet(BaseModel):
    """Conjunto de user stories para um RequirementsSet."""

    id: str = Field(..., description="ID único do conjunto")
    requirements_set_id: str = Field(..., description="ID do RequirementsSet")
    stories: List[UserStory] = Field(default_factory=list)
    total_story_points: int = Field(default=0, description="Total de story points")
    breakdown: Dict[StorySize, int] = Field(
        default_factory=dict,
        description="Distribuição por tamanho"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(None)

    def add_story(self, story: UserStory) -> None:
        """Adiciona uma user story ao conjunto."""
        self.stories.append(story)
        self.total_story_points += self._size_to_points(story.size)
        self.breakdown[story.size] = self.breakdown.get(story.size, 0) + 1
        self.updated_at = datetime.utcnow()

    @staticmethod
    def _size_to_points(size: StorySize) -> int:
        """Converte tamanho para pontos."""
        mapping = {
            StorySize.EXTRA_SMALL: 1,
            StorySize.SMALL: 2,
            StorySize.MEDIUM: 3,
            StorySize.LARGE: 5,
            StorySize.EXTRA_LARGE: 8,
        }
        return mapping.get(size, 3)
```

- [ ] **Step 3: Criar modelos de acceptance criteria**

```python
# services/requirements-engineering/src/models/acceptance_criteria.py
"""Modelos de dados para Critérios de Aceitação."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CriterionType(str, Enum):
    """Tipo de critério de aceitação."""

    FUNCTIONAL = "functional"
    PERFORMANCE = "performance"
    USABILITY = "usability"
    SECURITY = "security"
    COMPLIANCE = "compliance"


class CriterionStatus(str, Enum):
    """Status do critério."""

    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AcceptanceCriterion(BaseModel):
    """Critério de aceitação individual."""

    id: str = Field(..., description="ID único do critério")
    user_story_id: Optional[str] = Field(None, description="ID da User Story relacionada")
    requirement_id: Optional[str] = Field(None, description="ID do Requisito relacionado")
    criterion_type: CriterionType = Field(
        default=CriterionType.FUNCTIONAL,
        description="Tipo do critério"
    )
    status: CriterionStatus = Field(
        default=CriterionStatus.PENDING,
        description="Status do critério"
    )

    statement: str = Field(
        ...,
        min_length=10,
        description="Declaração do critério no formato Given-When-Then"
    )
    given: Optional[str] = Field(None, description="Contexto inicial (Given)")
    when: Optional[str] = Field(None, description="Acção ou evento (When)")
    then: Optional[str] = Field(None, description="Resultado esperado (Then)")

    test_scenario: Optional[str] = Field(
        None,
        description="Cenário de teste associado"
    )
    automated: bool = Field(
        default=False,
        description="Se possui teste automatizado"
    )
    test_file: Optional[str] = Field(
        None,
        description="Caminho para o teste automatizado"
    )

    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(None)

    def get_gwt_format(self) -> str:
        """Retorna o critério no formato Given-When-Then."""
        parts = []
        if self.given:
            parts.append(f"Given {self.given}")
        if self.when:
            parts.append(f"When {self.when}")
        if self.then:
            parts.append(f"Then {self.then}")
        return "\n".join(parts) if parts else self.statement


class AcceptanceCriteriaSet(BaseModel):
    """Conjunto de critérios de aceitação."""

    id: str = Field(..., description="ID único do conjunto")
    parent_id: str = Field(..., description="ID da User Story ou Requisito")
    parent_type: str = Field(..., description="Tipo do pai (user_story ou requirement)")
    criteria: List[AcceptanceCriterion] = Field(default_factory=list)
    pass_rate: float = Field(default=0.0, description="Taxa de aprovação (0-1)")
    automated_count: int = Field(default=0, description="Critérios automatizados")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(None)

    def calculate_pass_rate(self) -> None:
        """Calcula taxa de aprovação."""
        if not self.criteria:
            self.pass_rate = 0.0
            return
        passed = sum(1 for c in self.criteria if c.status == CriterionStatus.PASSED)
        self.pass_rate = passed / len(self.criteria)

    def add_criterion(self, criterion: AcceptanceCriterion) -> None:
        """Adiciona um critério ao conjunto."""
        self.criteria.append(criterion)
        if criterion.automated:
            self.automated_count += 1
        self.calculate_pass_rate()
        self.updated_at = datetime.utcnow()
```

- [ ] **Step 4: Criar modelos de data model**

```python
# services/requirements-engineering/src/models/data_model.py
"""Modelos de dados para design de modelos de dados."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DataFieldType(str, Enum):
    """Tipo de campo de dados."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    TEXT = "text"
    JSON = "json"
    ENUM = "enum"
    REFERENCE = "reference"  # Chave estrangeira
    ARRAY = "array"


class ConstraintType(str, Enum):
    """Tipo de restrição."""

    PRIMARY_KEY = "primary_key"
    FOREIGN_KEY = "foreign_key"
    UNIQUE = "unique"
    NOT_NULL = "not_null"
    CHECK = "check"
    INDEX = "index"


class DataField(BaseModel):
    """Campo de um modelo de dados."""

    name: str = Field(..., description="Nome do campo")
    field_type: DataFieldType = Field(..., description="Tipo do campo")
    required: bool = Field(default=False, description="Se é obrigatório")
    unique: bool = Field(default=False, description="Se deve ser único")
    default_value: Optional[Any] = Field(None, description="Valor padrão")
    min_length: Optional[int] = Field(None, description="Comprimento mínimo")
    max_length: Optional[int] = Field(None, description="Comprimento máximo")
    min_value: Optional[float] = Field(None, description="Valor mínimo")
    max_value: Optional[float] = Field(None, description="Valor máximo")
    enum_values: Optional[List[str]] = Field(None, description="Valores possíveis (enum)")
    reference_to: Optional[str] = Field(None, description="Tabela/modelo referenciado")
    reference_field: Optional[str] = Field(None, description="Campo referenciado")
    description: Optional[str] = Field(None, description="Descrição do campo")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Index(BaseModel):
    """Índice de um modelo de dados."""

    name: str = Field(..., description="Nome do índice")
    fields: List[str] = Field(..., description="Campos do índice")
    unique: bool = Field(default=False, description="Se é único")
    index_type: str = Field(default="btree", description="Tipo do índice")


class DataModel(BaseModel):
    """Modelo de dados (entidade/tabela)."""

    id: str = Field(..., description="ID único do modelo")
    name: str = Field(..., description="Nome do modelo/tabela")
    description: Optional[str] = Field(None, description="Descrição do modelo")
    fields: List[DataField] = Field(default_factory=list, description="Campos do modelo")
    indexes: List[Index] = Field(default_factory=list, description="Índices do modelo")
    primary_key: List[str] = Field(default_factory=list, description="Chave primária")
    foreign_keys: Dict[str, str] = Field(
        default_factory=dict,
        description="Chaves estrangeiras (campo -> tabela)"
    )

    # Relacionamentos
    many_to_one: List[str] = Field(
        default_factory=list,
        description="Relacionamentos N:1 (nomes dos modelos)"
    )
    one_to_many: List[str] = Field(
        default_factory=list,
        description="Relacionamentos 1:N (nomes dos modelos)"
    )
    many_to_many: List[str] = Field(
        default_factory=list,
        description="Relacionamentos N:M (nomes dos modelos)"
    )

    metadata: Dict[str, Any] = Field(default_factory=dict)
    cognitive_plan_id: Optional[str] = Field(None)
    requirement_id: Optional[str] = Field(None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(None)


class EntityRelationship(BaseModel):
    """Relacionamento entre entidades."""

    from_entity: str = Field(..., alias="from", description="Entidade de origem")
    to_entity: str = Field(..., alias="to", description="Entidade de destino")
    relationship_type: str = Field(
        ...,
        description="Tipo: one_to_one, one_to_many, many_to_many"
    )
    cardinality: str = Field(..., description="Cardinalidade (ex: 1:N, N:M)")
    description: Optional[str] = Field(None, description="Descrição do relacionamento")


class DataModelSchema(BaseModel):
    """Schema completo de modelos de dados de um projeto."""

    id: str = Field(..., description="ID único do schema")
    cognitive_plan_id: str = Field(..., description="ID do CognitivePlan")
    requirements_set_id: Optional[str] = Field(None, description="ID do RequirementsSet")

    models: List[DataModel] = Field(default_factory=list, description="Modelos do schema")
    relationships: List[EntityRelationship] = Field(
        default_factory=list,
        description="Relacionamentos entre modelos"
    )

    # Metadata
    database_type: str = Field(default="postgresql", description="Tipo de banco de dados")
    schema_name: str = Field(default="public", description="Nome do schema")
    description: Optional[str] = Field(None, description="Descrição do schema")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(None)

    def get_model_by_name(self, name: str) -> Optional[DataModel]:
        """Retorna um modelo por nome."""
        return next((m for m in self.models if m.name == name), None)

    def add_model(self, model: DataModel) -> None:
        """Adiciona um modelo ao schema."""
        self.models.append(model)
        self.updated_at = datetime.utcnow()
```

- [ ] **Step 5: Criar __init__.py dos modelos**

```python
# services/requirements-engineering/src/models/__init__.py
"""Modelos de dados do Requirements Engineering Service."""

from .acceptance_criteria import (
    AcceptanceCriterion,
    AcceptanceCriteriaSet,
    CriterionStatus,
    CriterionType,
)
from .data_model import (
    DataField,
    DataFieldType,
    DataModel,
    DataModelSchema,
    EntityRelationship,
    Index,
    ConstraintType,
)
from .requirements import (
    Requirement,
    RequirementPriority,
    RequirementsSet,
    RequirementStatus,
    RequirementType,
)
from .user_story import (
    StorySize,
    StoryStatus,
    UserStory,
    UserStorySet,
)

__all__ = [
    # Requirements
    "Requirement",
    "RequirementsSet",
    "RequirementPriority",
    "RequirementStatus",
    "RequirementType",
    # User Stories
    "UserStory",
    "UserStorySet",
    "StorySize",
    "StoryStatus",
    # Acceptance Criteria
    "AcceptanceCriterion",
    "AcceptanceCriteriaSet",
    "CriterionStatus",
    "CriterionType",
    # Data Models
    "DataField",
    "DataFieldType",
    "DataModel",
    "DataModelSchema",
    "EntityRelationship",
    "Index",
    "ConstraintType",
]
```

- [ ] **Step 6: Commit**

```bash
git add services/requirements-engineering/src/models/
git commit -m "feat(requirements-engineering): add data models for requirements, user stories, acceptance criteria, and data models"
```

---

## Task 3: Implementar RequirementsEngineer

**Files:**
- Create: `services/requirements-engineering/src/services/__init__.py`
- Create: `services/requirements-engineering/src/services/requirements_engineer.py`

- [ ] **Step 1: Escrever teste falhando para RequirementsEngineer**

```python
# services/requirements-engineering/tests/unit/test_requirements_engineer.py
"""Testes unitários para RequirementsEngineer."""

import pytest
from unittest.mock import Mock, patch

from requirements_engineering.services.requirements_engineer import RequirementsEngineer
from requirements_engineering.models.requirements import (
    Requirement,
    RequirementsSet,
    RequirementPriority,
    RequirementType,
)


@pytest.fixture
def mock_llm_client():
    """Fixture para mock LLM client."""
    mock_client = Mock()
    mock_client.chat.completions.create.return_value = Mock(
        choices=[Mock(message=Mock(content='[{"id": "REQ-001", "title": "Autenticação de utilizadores", "description": "O sistema deve permitir autenticação via email e senha", "priority": "high", "type": "functional"}]'))]
    )
    return mock_client


@pytest.fixture
def engineer(mock_llm_client):
    """Fixture para RequirementsEngineer."""
    return RequirementsEngineer(llm_client=mock_llm_client)


@pytest.mark.asyncio
async def test_generate_requirements_from_cognitive_plan(engineer):
    """Testa geração de requisitos a partir de CognitivePlan."""
    # Arrange
    cognitive_plan_text = "Criar um sistema de gestão de utilizadores com autenticação"

    # Act
    requirements_set = await engineer.generate_from_cognitive_plan(
        plan_id="CP-001",
        plan_text=cognitive_plan_text
    )

    # Assert
    assert isinstance(requirements_set, RequirementsSet)
    assert requirements_set.cognitive_plan_id == "CP-001"
    assert len(requirements_set.requirements) > 0
    assert isinstance(requirements_set.requirements[0], Requirement)


@pytest.mark.asyncio
async def test_generate_requirements_includes_functional_and_non_functional(engineer):
    """Testa que gera ambos tipos de requisitos."""
    # Arrange
    cognitive_plan_text = "Sistema de e-commerce com alta disponibilidade"

    # Act
    requirements_set = await engineer.generate_from_cognitive_plan(
        plan_id="CP-002",
        plan_text=cognitive_plan_text
    )

    # Assert
    functional = [r for r in requirements_set.requirements if r.requirement_type == RequirementType.FUNCTIONAL]
    non_functional = [r for r in requirements_set.requirements if r.requirement_type == RequirementType.NON_FUNCTIONAL]

    assert len(functional) > 0, "Deve gerar requisitos funcionais"
    assert len(non_functional) > 0, "Deve gerar requisitos não-funcionais"


@pytest.mark.asyncio
async def test_prioritize_requirements_correctly(engineer):
    """Testa priorização correta de requisitos."""
    # Arrange
    requirements = [
        Requirement(id="REQ-001", title="Login", description="Login de usuário", priority=RequirementPriority.HIGH),
        Requirement(id="REQ-002", title="Logout", description="Logout de usuário", priority=RequirementPriority.MEDIUM),
    ]

    # Act
    prioritized = await engineer.prioritize_requirements(requirements)

    # Assert
    assert prioritized[0].priority == RequirementPriority.HIGH


@pytest.mark.asyncio
async def test_identify_dependencies(engineer):
    """Testa identificação de dependências entre requisitos."""
    # Arrange
    requirements = [
        Requirement(id="REQ-001", title="Criar usuário", description="Criar usuário no sistema"),
        Requirement(id="REQ-002", title="Autenticar usuário", description="Autenticar usuário criado"),
    ]

    # Act
    analyzed = await engineer.analyze_dependencies(requirements)

    # Assert
    assert "REQ-001" in analyzed[1].dependencies, "REQ-002 deve depender de REQ-001"
```

- [ ] **Step 2: Executar teste para verificar falha**

```bash
cd services/requirements-engineering
pytest tests/unit/test_requirements_engineer.py -v
```

Expected: FAIL - "ModuleNotFoundError: No module named 'requirements_engineering.services.requirements_engineer'"

- [ ] **Step 3: Implementar RequirementsEngineer**

```python
# services/requirements-engineering/src/services/requirements_engineer.py
"""Serviço para geração de requisitos funcionais e não-funcionais."""

import json
import uuid
from typing import Any, Dict, List, Optional

import structlog
from openai import AsyncOpenAI
from pydantic import ValidationError

from ..models.requirements import (
    Requirement,
    RequirementsSet,
    RequirementPriority,
    RequirementType,
)
from ..config.settings import get_settings

logger = structlog.get_logger()

# Prompt template para geração de requisitos
REQUIREMENTS_GENERATION_PROMPT = """
Você é um engenheiro de requisitos especialista. Analise o seguinte plano cognitivo e gere uma lista completa de requisitos.

**Plano Cognitivo:**
{plan_text}

**Instruções:**
1. Gere requisitos funcionais (o que o sistema deve fazer)
2. Gere requisitos não-funcionais (performance, segurança, usabilidade, etc.)
3. Para cada requisito, inclua:
   - ID único (formato REQ-XXX)
   - Título claro
   - Descrição detalhada
   - Prioridade (critical, high, medium, low)
   - Tipo (functional, non_functional)
   - Justificativa (por que é necessário)

4. Retorne APENAS JSON válido, sem markdown ou texto adicional.

**Formato JSON:**
[
  {{
    "id": "REQ-001",
    "title": "Título do requisito",
    "description": "Descrição detalhada",
    "priority": "high|medium|low|critical",
    "type": "functional|non_functional",
    "rationale": "Justificativa"
  }}
]
"""


class RequirementsEngineer:
    """Serviço para engenharia de requisitos."""

    def __init__(self, settings: Optional[Any] = None, llm_client: Optional[AsyncOpenAI] = None):
        """Inicializa o RequirementsEngineer.

        Args:
            settings: Configurações do serviço
            llm_client: Cliente LLM (opcional, para testes)
        """
        self.settings = settings or get_settings()
        self.llm_client = llm_client or AsyncOpenAI(api_key=self.settings.openai_api_key)

    async def generate_from_cognitive_plan(
        self,
        plan_id: str,
        plan_text: str,
        domain_hints: Optional[List[str]] = None
    ) -> RequirementsSet:
        """Gera requisitos a partir de um plano cognitivo.

        Args:
            plan_id: ID do CognitivePlan
            plan_text: Texto do plano cognitivo
            domain_hints: Dicas do domínio (opcional)

        Returns:
            RequirementsSet com os requisitos gerados
        """
        logger.info("generating_requirements", plan_id=plan_id)

        # Preparar prompt
        prompt = REQUIREMENTS_GENERATION_PROMPT.format(plan_text=plan_text)
        if domain_hints:
            prompt += f"\n\n**Dicas do Domínio:** {', '.join(domain_hints)}"

        # Chamar LLM
        try:
            response = await self.llm_client.chat.completions.create(
                model=self.settings.llm_model,
                messages=[
                    {"role": "system", "content": "Você é um engenheiro de requisitos especialista."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.settings.llm_temperature,
                max_tokens=self.settings.llm_max_tokens
            )

            response_text = response.choices[0].message.content
            logger.debug("llm_response", response_length=len(response_text))

            # Parse JSON
            requirements_data = self._parse_llm_response(response_text)

            # Criar objetos Requirement
            requirements = []
            for req_data in requirements_data:
                try:
                    requirement = Requirement(
                        id=req_data.get("id", f"REQ-{uuid.uuid4().hex[:6].upper()}"),
                        title=req_data["title"],
                        description=req_data["description"],
                        priority=self._parse_priority(req_data.get("priority", "medium")),
                        requirement_type=self._parse_type(req_data.get("type", "functional")),
                        rationale=req_data.get("rationale", ""),
                        cognitive_plan_id=plan_id
                    )
                    requirements.append(requirement)
                except (ValidationError, KeyError) as e:
                    logger.warning("invalid_requirement_skipped", data=req_data, error=str(e))

            # Criar RequirementsSet
            requirements_set = RequirementsSet(
                id=f"RS-{uuid.uuid4().hex[:8].upper()}",
                cognitive_plan_id=plan_id,
                requirements=requirements[:self.settings.max_requirements_per_plan]
            )

            # Contagens
            requirements_set.functional_count = len([
                r for r in requirements_set.requirements
                if r.requirement_type == RequirementType.FUNCTIONAL
            ])
            requirements_set.non_functional = len([
                r for r in requirements_set.requirements
                if r.requirement_type == RequirementType.NON_FUNCTIONAL
            ])

            logger.info(
                "requirements_generated",
                set_id=requirements_set.id,
                total=len(requirements_set.requirements),
                functional=requirements_set.functional_count,
                non_functional=requirements_set.non_functional_count
            )

            return requirements_set

        except Exception as e:
            logger.error("requirements_generation_failed", plan_id=plan_id, error=str(e))
            raise

    async def prioritize_requirements(
        self,
        requirements: List[Requirement]
    ) -> List[Requirement]:
        """Prioriza requisitos baseado em MoSCoW e impacto.

        Args:
            requirements: Lista de requisitos

        Returns:
            Lista ordenada por prioridade
        """
        priority_order = {
            RequirementPriority.CRITICAL: 0,
            RequirementPriority.HIGH: 1,
            RequirementPriority.MEDIUM: 2,
            RequirementPriority.LOW: 3
        }

        return sorted(
            requirements,
            key=lambda r: (priority_order.get(r.priority, 99), r.id)
        )

    async def analyze_dependencies(
        self,
        requirements: List[Requirement]
    ) -> List[Requirement]:
        """Analisa dependências entre requisitos usando LLM.

        Args:
            requirements: Lista de requisitos

        Returns:
            Lista de requisitos com dependências preenchidas
        """
        if len(requirements) < 2:
            return requirements

        logger.info("analyzing_dependencies", requirement_count=len(requirements))

        # Preparar resumo dos requisitos
        req_summary = "\n".join([
            f"{r.id}: {r.title} - {r.description[:100]}..."
            for r in requirements
        ])

        prompt = f"""
Analise as dependências entre os seguintes requisitos:

{req_summary}

Para cada requisito que depende de outro, retorne no formato:
REQ-XXX -> REQ-YYY

Retorne APENAS pares de dependências, uma por linha.
"""

        try:
            response = await self.llm_client.chat.completions.create(
                model=self.settings.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1000
            )

            dependencies_text = response.choices[0].message.content

            # Parse dependências
            req_map = {r.id: r for r in requirements}

            for line in dependencies_text.strip().split("\n"):
                if "->" in line:
                    parts = line.split("->")
                    if len(parts) == 2:
                        dep_id = parts[0].strip()
                        req_id = parts[1].strip()
                        if req_id in req_map:
                            if dep_id not in req_map[req_id].dependencies:
                                req_map[req_id].dependencies.append(dep_id)

            logger.info("dependencies_analyzed", total=len(requirements))

        except Exception as e:
            logger.warning("dependency_analysis_failed", error=str(e))

        return requirements

    def _parse_llm_response(self, response_text: str) -> List[Dict[str, Any]]:
        """Faz parse da resposta LLM para JSON.

        Args:
            response_text: Texto de resposta do LLM

        Returns:
            Lista de dicionários com dados dos requisitos
        """
        # Remover markdown code blocks se presente
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]

        try:
            return json.loads(response_text.strip())
        except json.JSONDecodeError:
            logger.warning("json_parse_failed", attempting_fix=True)
            # Tentar limpar e parsear novamente
            cleaned = response_text.strip()
            if cleaned.startswith("[") and cleaned.endswith("]"):
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    pass
            return []

    def _parse_priority(self, value: str) -> RequirementPriority:
        """Converte string para RequirementPriority."""
        mapping = {
            "critical": RequirementPriority.CRITICAL,
            "high": RequirementPriority.HIGH,
            "medium": RequirementPriority.MEDIUM,
            "low": RequirementPriority.LOW
        }
        return mapping.get(value.lower(), RequirementPriority.MEDIUM)

    def _parse_type(self, value: str) -> RequirementType:
        """Converte string para RequirementType."""
        mapping = {
            "functional": RequirementType.FUNCTIONAL,
            "non_functional": RequirementType.NON_FUNCTIONAL,
            "constraint": RequirementType.CONSTRAINT,
            "assumption": RequirementType.ASSUMPTION
        }
        return mapping.get(value.lower(), RequirementType.FUNCTIONAL)
```

- [ ] **Step 4: Criar __init__.py do services**

```python
# services/requirements-engineering/src/services/__init__.py
"""Serviços do Requirements Engineering Service."""

from .requirements_engineer import RequirementsEngineer

__all__ = ["RequirementsEngineer"]
```

- [ ] **Step 5: Executar teste para verificar sucesso**

```bash
cd services/requirements-engineering
pytest tests/unit/test_requirements_engineer.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/requirements-engineering/src/services/ \
        services/requirements-engineering/tests/unit/test_requirements_engineer.py
git commit -m "feat(requirements-engineering): implement RequirementsEngineer service"
```

---

## Task 4: Implementar UserStoryGenerator

**Files:**
- Create: `services/requirements-engineering/src/services/user_story_generator.py`
- Create: `services/requirements-engineering/tests/unit/test_user_story_generator.py`

- [ ] **Step 1: Escrever teste falhando**

```python
# services/requirements-engineering/tests/unit/test_user_story_generator.py
"""Testes unitários para UserStoryGenerator."""

import pytest
from unittest.mock import Mock

from requirements_engineering.services.user_story_generator import UserStoryGenerator
from requirements_engineering.models.user_story import UserStory, UserStorySet, StorySize
from requirements_engineering.models.requirements import Requirement


@pytest.fixture
def mock_llm_client():
    """Fixture para mock LLM client."""
    mock_client = Mock()
    mock_client.chat.completions.create.return_value = Mock(
        choices=[Mock(message=Mock(content='[{"id": "US-001", "role": "administrador", "action": "criar utilizadores", "benefit": "gerir equipas", "size": "m"}]'))]
    )
    return mock_client


@pytest.fixture
def generator(mock_llm_client):
    """Fixture para UserStoryGenerator."""
    return UserStoryGenerator(llm_client=mock_llm_client)


@pytest.mark.asyncio
async def test_generate_from_requirement(generator):
    """Testa geração de user stories a partir de requisito."""
    # Arrange
    requirement = Requirement(
        id="REQ-001",
        title="Gestão de Utilizadores",
        description="O sistema deve permitir criar, editar e remover utilizadores"
    )

    # Act
    stories = await generator.generate_from_requirement(requirement)

    # Assert
    assert isinstance(stories, list)
    assert len(stories) > 0
    assert all(isinstance(s, UserStory) for s in stories)


@pytest.mark.asyncio
async def test_user_story_format(generator):
    """Testa formato padrão de user story."""
    # Arrange
    story = UserStory(
        id="US-001",
        requirement_id="REQ-001",
        role="administrador",
        action="criar utilizadores",
        benefit="gerir equipas"
    )

    # Act
    formatted = story.get_user_story_format()

    # Assert
    assert "Como administrador" in formatted
    assert "eu quero criar utilizadores" in formatted
    assert "para que gerir equipas" in formatted
```

- [ ] **Step 2: Executar teste para verificar falha**

```bash
cd services/requirements-engineering
pytest tests/unit/test_user_story_generator.py -v
```

Expected: FAIL

- [ ] **Step 3: Implementar UserStoryGenerator**

```python
# services/requirements-engineering/src/services/user_story_generator.py
"""Serviço para geração de User Stories."""

import json
import uuid
from typing import List, Optional

import structlog
from openai import AsyncOpenAI

from ..models.user_story import UserStory, UserStorySet, StorySize
from ..models.requirements import Requirement
from ..config.settings import get_settings

logger = structlog.get_logger()

USER_STORY_GENERATION_PROMPT = """
Você é um especialista em Product Ownership e User Stories. Analise o seguinte requisito e decomponha em User Stories.

**Requisito:**
{title}
{description}

**Instruções:**
1. Decomponha o requisito em User Stories menores e acionáveis
2. Cada User Story deve seguir o formato: Como [role], eu quero [action], para que [benefit]
3. Atribua um tamanho estimado (xs, s, m, l, xl)
4. Retorne APENAS JSON válido

**Formato JSON:**
[
  {{
    "id": "US-001",
    "role": "papel do utilizador",
    "action": "acção desejada",
    "benefit": "benefício esperado",
    "size": "xs|s|m|l|xl"
  }}
]
"""


class UserStoryGenerator:
    """Gerador de User Stories."""

    def __init__(self, settings: Optional[object] = None, llm_client: Optional[AsyncOpenAI] = None):
        """Inicializa o UserStoryGenerator.

        Args:
            settings: Configurações do serviço
            llm_client: Cliente LLM (opcional)
        """
        self.settings = settings or get_settings()
        self.llm_client = llm_client or AsyncOpenAI(api_key=self.settings.openai_api_key)

    async def generate_from_requirement(
        self,
        requirement: Requirement,
        max_stories: int = 10
    ) -> List[UserStory]:
        """Gera User Stories a partir de um requisito.

        Args:
            requirement: Requisito fonte
            max_stories: Número máximo de stories

        Returns:
            Lista de User Stories
        """
        logger.info("generating_user_stories", requirement_id=requirement.id)

        prompt = USER_STORY_GENERATION_PROMPT.format(
            title=requirement.title,
            description=requirement.description
        )

        try:
            response = await self.llm_client.chat.completions.create(
                model=self.settings.llm_model,
                messages=[
                    {"role": "system", "content": "Você é um especialista em Product Ownership."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.settings.llm_temperature,
                max_tokens=2000
            )

            response_text = response.choices[0].message.content
            stories_data = self._parse_llm_response(response_text)

            stories = []
            for story_data in stories_data[:max_stories]:
                try:
                    story = UserStory(
                        id=story_data.get("id", f"US-{uuid.uuid4().hex[:6].upper()}"),
                        requirement_id=requirement.id,
                        role=story_data["role"],
                        action=story_data["action"],
                        benefit=story_data["benefit"],
                        size=self._parse_size(story_data.get("size", "m")),
                        cognitive_plan_id=requirement.cognitive_plan_id
                    )
                    stories.append(story)
                except Exception as e:
                    logger.warning("invalid_story_skipped", data=story_data, error=str(e))

            logger.info("user_stories_generated", count=len(stories))

            return stories

        except Exception as e:
            logger.error("user_story_generation_failed", requirement_id=requirement.id, error=str(e))
            return []

    def _parse_llm_response(self, response_text: str) -> List[dict]:
        """Faz parse da resposta LLM."""
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]

        try:
            return json.loads(response_text.strip())
        except json.JSONDecodeError:
            return []

    def _parse_size(self, value: str) -> StorySize:
        """Converte string para StorySize."""
        mapping = {
            "xs": StorySize.EXTRA_SMALL,
            "s": StorySize.SMALL,
            "m": StorySize.MEDIUM,
            "l": StorySize.LARGE,
            "xl": StorySize.EXTRA_LARGE
        }
        return mapping.get(value.lower(), StorySize.MEDIUM)
```

- [ ] **Step 4: Atualizar __init__.py**

```python
# services/requirements-engineering/src/services/__init__.py
"""Serviços do Requirements Engineering Service."""

from .requirements_engineer import RequirementsEngineer
from .user_story_generator import UserStoryGenerator

__all__ = ["RequirementsEngineer", "UserStoryGenerator"]
```

- [ ] **Step 5: Executar testes**

```bash
cd services/requirements-engineering
pytest tests/unit/test_user_story_generator.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/requirements-engineering/src/services/user_story_generator.py \
        services/requirements-engineering/tests/unit/test_user_story_generator.py
git commit -m "feat(requirements-engineering): implement UserStoryGenerator service"
```

---

## Task 5: Implementar AcceptanceCriteriaGenerator

**Files:**
- Create: `services/requirements-engineering/src/services/acceptance_criteria_generator.py`
- Create: `services/requirements-engineering/tests/unit/test_acceptance_criteria_generator.py`

- [ ] **Step 1: Escrever teste falhando**

```python
# services/requirements-engineering/tests/unit/test_acceptance_criteria_generator.py
"""Testes para AcceptanceCriteriaGenerator."""

import pytest
from unittest.mock import Mock

from requirements_engineering.services.acceptance_criteria_generator import AcceptanceCriteriaGenerator
from requirements_engineering.models.acceptance_criteria import AcceptanceCriterion, CriterionType
from requirements_engineering.models.user_story import UserStory


@pytest.fixture
def mock_llm_client():
    mock_client = Mock()
    mock_client.chat.completions.create.return_value = Mock(
        choices=[Mock(message=Mock(content='[{"id": "AC-001", "given": "utilizador autenticado", "when": "clica em logout", "then": "sessão terminada"}]'))]
    )
    return mock_client


@pytest.fixture
def generator(mock_llm_client):
    return AcceptanceCriteriaGenerator(llm_client=mock_llm_client)


@pytest.mark.asyncio
async def test_generate_for_user_story(generator):
    """Testa geração de critérios para user story."""
    story = UserStory(
        id="US-001",
        requirement_id="REQ-001",
        role="utilizador",
        action="fazer logout",
        benefit="sair da aplicação"
    )

    criteria = await generator.generate_for_user_story(story)

    assert len(criteria) > 0
    assert all(isinstance(c, AcceptanceCriterion) for c in criteria)


@pytest.mark.asyncio
async def test_criterion_gwt_format(generator):
    """Testa formato Given-When-Then."""
    criterion = AcceptanceCriterion(
        id="AC-001",
        user_story_id="US-001",
        given="utilizador autenticado",
        when="clica em logout",
        then="sessão é terminada"
    )

    gwt = criterion.get_gwt_format()

    assert "Given utilizador autenticado" in gwt
    assert "When clica em logout" in gwt
    assert "Then sessão é terminada" in gwt
```

- [ ] **Step 2: Executar teste**

Expected: FAIL

- [ ] **Step 3: Implementar AcceptanceCriteriaGenerator**

```python
# services/requirements-engineering/src/services/acceptance_criteria_generator.py
"""Serviço para geração de Critérios de Aceitação."""

import json
import uuid
from typing import List

import structlog
from openai import AsyncOpenAI

from ..models.acceptance_criteria import AcceptanceCriterion, CriterionType
from ..models.user_story import UserStory
from ..config.settings import get_settings

logger = structlog.get_logger()

ACCEPTANCE_CRITERIA_PROMPT = """
Você é um especialista em BDD (Behavior Driven Development). Analise a seguinte User Story e gere Critérios de Aceitação no formato Given-When-Then.

**User Story:**
{user_story}

**Instruções:**
1. Gere 3-5 critérios de aceitação
2. Use formato Given-When-Then
3. Seja específico e mensurável
4. Retorne APENAS JSON

**Formato JSON:**
[
  {{
    "id": "AC-001",
    "given": "contexto inicial",
    "when": "acção",
    "then": "resultado esperado",
    "type": "functional|performance|usability|security"
  }}
]
"""


class AcceptanceCriteriaGenerator:
    """Gerador de Critérios de Aceitação."""

    def __init__(self, settings=None, llm_client=None):
        self.settings = settings or get_settings()
        self.llm_client = llm_client or AsyncOpenAI(api_key=self.settings.openai_api_key)

    async def generate_for_user_story(
        self,
        user_story: UserStory,
        max_criteria: int = 5
    ) -> List[AcceptanceCriterion]:
        """Gera critérios de aceitação para uma user story.

        Args:
            user_story: User Story alvo
            max_criteria: Número máximo de critérios

        Returns:
            Lista de AcceptanceCriterion
        """
        logger.info("generating_acceptance_criteria", story_id=user_story.id)

        story_text = user_story.get_user_story_format()
        prompt = ACCEPTANCE_CRITERIA_PROMPT.format(user_story=story_text)

        try:
            response = await self.llm_client.chat.completions.create(
                model=self.settings.llm_model,
                messages=[
                    {"role": "system", "content": "Você é um especialista em BDD."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=1500
            )

            response_text = response.choices[0].message.content
            criteria_data = self._parse_llm_response(response_text)

            criteria = []
            for crit_data in criteria_data[:max_criteria]:
                try:
                    criterion = AcceptanceCriterion(
                        id=crit_data.get("id", f"AC-{uuid.uuid4().hex[:6].upper()}"),
                        user_story_id=user_story.id,
                        criterion_type=self._parse_type(crit_data.get("type", "functional")),
                        given=crit_data.get("given"),
                        when=crit_data.get("when"),
                        then=crit_data.get("then"),
                        statement=f"Given {crit_data.get('given', '')} When {crit_data.get('when', '')} Then {crit_data.get('then', '')}"
                    )
                    criteria.append(criterion)
                except Exception as e:
                    logger.warning("invalid_criterion_skipped", data=crit_data, error=str(e))

            logger.info("acceptance_criteria_generated", count=len(criteria))

            return criteria

        except Exception as e:
            logger.error("acceptance_criteria_generation_failed", story_id=user_story.id, error=str(e))
            return []

    def _parse_llm_response(self, response_text: str) -> List[dict]:
        """Faz parse da resposta LLM."""
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]

        try:
            return json.loads(response_text.strip())
        except json.JSONDecodeError:
            return []

    def _parse_type(self, value: str) -> CriterionType:
        """Converte string para CriterionType."""
        mapping = {
            "functional": CriterionType.FUNCTIONAL,
            "performance": CriterionType.PERFORMANCE,
            "usability": CriterionType.USABILITY,
            "security": CriterionType.SECURITY,
            "compliance": CriterionType.COMPLIANCE
        }
        return mapping.get(value.lower(), CriterionType.FUNCTIONAL)
```

- [ ] **Step 4: Atualizar __init__.py**

```python
# services/requirements-engineering/src/services/__init__.py
"""Serviços do Requirements Engineering Service."""

from .requirements_engineer import RequirementsEngineer
from .acceptance_criteria_generator import AcceptanceCriteriaGenerator
from .user_story_generator import UserStoryGenerator

__all__ = [
    "RequirementsEngineer",
    "AcceptanceCriteriaGenerator",
    "UserStoryGenerator",
]
```

- [ ] **Step 5: Executar testes**

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/requirements-engineering/src/services/acceptance_criteria_generator.py \
        services/requirements-engineering/tests/unit/test_acceptance_criteria_generator.py
git commit -m "feat(requirements-engineering): implement AcceptanceCriteriaGenerator"
```

---

## Task 6: Criar API REST

**Files:**
- Create: `services/requirements-engineering/src/main.py`
- Create: `services/requirements-engineering/src/api/__init__.py`
- Create: `services/requirements-engineering/src/api/routers/__init__.py`
- Create: `services/requirements-engineering/src/api/routers/requirements.py`

- [ ] **Step 1: Criar main.py (FastAPI app)**

```python
# services/requirements-engineering/src/main.py
"""Aplicação FastAPI para Requirements Engineering Service."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers.requirements import router as requirements_router
from config.settings import get_settings
from neural_hive_observability import get_context_manager, get_logger, get_metrics


settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager."""
    logger.info("requirements_engineering_starting", port=settings.port)
    yield
    logger.info("requirements_engineering_stopping")


app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(requirements_router, prefix=settings.api_prefix)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "service": "requirements-engineering",
        "status": "healthy",
        "version": settings.api_version
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )
```

- [ ] **Step 2: Criar router requirements.py**

```python
# services/requirements-engineering/src/api/routers/requirements.py
"""Router REST para requisitos."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ...models.requirements import RequirementsSet, Requirement
from ...services.requirements_engineer import RequirementsEngineer
from ...services.user_story_generator import UserStoryGenerator
from ...services.acceptance_criteria_generator import AcceptanceCriteriaGenerator
from ...config.settings import get_settings


router = APIRouter(prefix="/requirements", tags=["requirements"])
settings = get_settings()


class GenerateRequest(BaseModel):
    """Request para geração de requisitos."""
    plan_id: str
    plan_text: str
    domain_hints: List[str] = []


class GenerateResponse(BaseModel):
    """Response da geração de requisitos."""
    requirements_set_id: str
    requirement_count: int
    functional_count: int
    non_functional_count: int


@router.post("/generate", response_model=GenerateResponse)
async def generate_requirements(request: GenerateRequest):
    """Gera requisitos a partir de um plano cognitivo."""
    engineer = RequirementsEngineer(settings)

    try:
        requirements_set = await engineer.generate_from_cognitive_plan(
            plan_id=request.plan_id,
            plan_text=request.plan_text,
            domain_hints=request.domain_hints or None
        )

        return GenerateResponse(
            requirements_set_id=requirements_set.id,
            requirement_count=len(requirements_set.requirements),
            functional_count=requirements_set.functional_count,
            non_functional_count=requirements_set.non_functional_count
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate requirements: {str(e)}"
        )


@router.get("/health")
async def health():
    """Health check."""
    return {"status": "healthy"}
```

- [ ] **Step 3: Criar packages __init__.py**

```python
# services/requirements-engineering/src/api/__init__.py
"""API REST do Requirements Engineering Service."""
```

```python
# services/requirements-engineering/src/api/routers/__init__.py
"""Routers da API REST."""
```

- [ ] **Step 4: Testar localmente**

```bash
cd services/requirements-engineering
poetry install
poetry run python src/main.py
```

Verificar que o servidor inicia na porta 8010.

- [ ] **Step 5: Commit**

```bash
git add services/requirements-engineering/src/main.py \
        services/requirements-engineering/src/api/
git commit -m "feat(requirements-engineering): add FastAPI REST endpoints"
```

---

## Task 7: Implementar Kafka Consumer e Producer

**Files:**
- Create: `services/requirements-engineering/src/consumers/__init__.py`
- Create: `services/requirements-engineering/src/consumers/cognitive_plan_consumer.py`
- Create: `services/requirements-engineering/src/producers/__init__.py`
- Create: `services/requirements-engineering/src/producers/requirements_producer.py`

- [ ] **Step 1: Criar consumer**

```python
# services/requirements-engineering/src/consumers/cognitive_plan_consumer.py
"""Consumer Kafka para planos cognitivos."""

import json

import structlog
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from ..services.requirements_engineer import RequirementsEngineer
from ..services.user_story_generator import UserStoryGenerator
from ..services.acceptance_criteria_generator import AcceptanceCriteriaGenerator
from ..producers.requirements_producer import RequirementsProducer
from ..config.settings import get_settings

logger = structlog.get_logger()
settings = get_settings()


class CognitivePlanConsumer:
    """Consome tópicos cognitive.plans.created."""

    def __init__(self):
        """Inicializa o consumer."""
        self.consumer = None
        self.settings = settings
        self.engineer = RequirementsEngineer(settings)
        self.story_generator = UserStoryGenerator(settings)
        self.criteria_generator = AcceptanceCriteriaGenerator(settings)
        self.producer = RequirementsProducer()

    async def start(self):
        """Inicia o consumo de mensagens."""
        self.consumer = AIOKafkaConsumer(
            self.settings.kafka_input_topic,
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            group_id=self.settings.kafka_consumer_group,
            auto_offset_reset="earliest",
            enable_auto_commit=False
        )
        await self.consumer.start()
        logger.info("cognitive_plan_consumer_started", topic=self.settings.kafka_input_topic)

        async for msg in self.consumer:
            await self.process_message(msg)

    async def stop(self):
        """Para o consumo de mensagens."""
        if self.consumer:
            await self.consumer.stop()
            logger.info("cognitive_plan_consumer_stopped")

    async def process_message(self, msg):
        """Processa mensagem individual."""
        try:
            data = json.loads(msg.value.decode("utf-8"))
            plan_id = data.get("plan_id")
            plan_text = data.get("plan_text", "")

            logger.info("processing_cognitive_plan", plan_id=plan_id)

            # Gerar requisitos
            requirements_set = await self.engineer.generate_from_cognitive_plan(
                plan_id=plan_id,
                plan_text=plan_text
            )

            # Gerar user stories
            for requirement in requirements_set.requirements:
                stories = await self.story_generator.generate_from_requirement(requirement)

                # Gerar acceptance criteria
                for story in stories:
                    criteria = await self.criteria_generator.generate_for_user_story(story)

            # Publicar resultado
            await self.producer.publish_requirements_generated(
                requirements_set_id=requirements_set.id,
                cognitive_plan_id=plan_id,
                requirement_count=len(requirements_set.requirements)
            )

            # Commit offset
            await self.consumer.commit()

            logger.info(
                "cognitive_plan_processed",
                plan_id=plan_id,
                requirements_count=len(requirements_set.requirements)
            )

        except Exception as e:
            logger.error("message_processing_failed", error=str(e))
            # Enviar para DLQ
            await self.producer.send_to_dlq(msg.value, str(e))
```

- [ ] **Step 2: Criar producer**

```python
# services/requirements-engineering/src/producers/requirements_producer.py
"""Producer Kafka para eventos de requisitos."""

import json

import structlog
from aiokafka import AIOKafkaProducer

from ..config.settings import get_settings

logger = structlog.get_logger()
settings = get_settings()


class RequirementsProducer:
    """Producer para eventos de requisitos."""

    def __init__(self):
        """Inicializa o producer."""
        self.producer = None
        self.settings = settings

    async def start(self):
        """Inicia o producer."""
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.settings.kafka_bootstrap_servers
        )
        await self.producer.start()
        logger.info("requirements_producer_started")

    async def stop(self):
        """Para o producer."""
        if self.producer:
            await self.producer.stop()
            logger.info("requirements_producer_stopped")

    async def publish_requirements_generated(
        self,
        requirements_set_id: str,
        cognitive_plan_id: str,
        requirement_count: int
    ):
        """Publica evento requirements.generated."""
        event = {
            "requirements_set_id": requirements_set_id,
            "cognitive_plan_id": cognitive_plan_id,
            "requirement_count": requirement_count,
            "timestamp": json.dumps({"$date": {"$numberLong": str(int(__import__("time").time() * 1000))}})
        }

        await self.producer.send_and_wait(
            self.settings.kafka_output_topic,
            json.dumps(event).encode("utf-8")
        )
        logger.info("requirements_generated_published", set_id=requirements_set_id)

    async def send_to_dlq(self, original_message: bytes, error: str):
        """Envia mensagem para DLQ."""
        dlq_event = {
            "original_message": original_message.decode("utf-8"),
            "error": error,
            "timestamp": json.dumps({"$date": {"$numberLong": str(int(__import__("time").time() * 1000))}})
        }

        await self.producer.send_and_wait(
            self.settings.kafka_dlq_topic,
            json.dumps(dlq_event).encode("utf-8")
        )
        logger.warning("message_sent_to_dlq", error=error)
```

- [ ] **Step 3: Criar packages**

```python
# services/requirements-engineering/src/consumers/__init__.py
"""Consumers Kafka."""
```

```python
# services/requirements-engineering/src/producers/__init__.py
"""Producers Kafka."""
```

- [ ] **Step 4: Commit**

```bash
git add services/requirements-engineering/src/consumers/ \
        services/requirements-engineering/src/producers/
git commit -m "feat(requirements-engineering): add Kafka consumer and producer"
```

---

## Task 8: Criar deployment manifests

**Files:**
- Create: `services/requirements-engineering/deployment/Dockerfile`
- Create: `services/requirements-engineering/deployment/k8s-deployment.yaml`
- Create: `services/requirements-engineering/deployment/k8s-service.yaml`

- [ ] **Step 1: Criar Dockerfile**

```dockerfile
# services/requirements-engineering/deployment/Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Instalar dependências
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --only=main --no-dev

# Copiar código
COPY src/ ./src/

# Expor porta
EXPOSE 8010

# Executar
CMD ["poetry", "run", "python", "src/main.py"]
```

- [ ] **Step 2: Criar k8s-deployment.yaml**

```yaml
# services/requirements-engineering/deployment/k8s-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: requirements-engineering
  labels:
    app: requirements-engineering
spec:
  replicas: 2
  selector:
    matchLabels:
      app: requirements-engineering
  template:
    metadata:
      labels:
        app: requirements-engineering
    spec:
      containers:
      - name: requirements-engineering
        image: requirements-engineering:latest
        ports:
        - containerPort: 8010
        env:
        - name: REQ_ENG_OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: llm-secrets
              key: openai-api-key
        - name: REQ_ENG_MONGODB_URL
          valueFrom:
            configMapKeyRef:
              name: infrastructure
              key: mongodb-url
        - name: REQ_ENG_KAFKA_BOOTSTRAP_SERVERS
          valueFrom:
            configMapKeyRef:
              name: infrastructure
              key: kafka-bootstrap-servers
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8010
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8010
          initialDelaySeconds: 5
          periodSeconds: 5
```

- [ ] **Step 3: Criar k8s-service.yaml**

```yaml
# services/requirements-engineering/deployment/k8s-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: requirements-engineering
spec:
  selector:
    app: requirements-engineering
  ports:
  - protocol: TCP
    port: 8010
    targetPort: 8010
  type: ClusterIP
```

- [ ] **Step 4: Commit**

```bash
git add services/requirements-engineering/deployment/
git commit -m "feat(requirements-engineering): add Kubernetes deployment manifests"
```

---

# PARTE 2: Documentation Generation System (8014)

## Task 9: Criar estrutura base do documentation-generation

**Files:**
- Create: `services/documentation-generation/pyproject.toml`
- Create: `services/documentation-generation/src/__init__.py`
- Create: `services/documentation-generation/src/config/settings.py`

- [ ] **Step 1: Criar pyproject.toml**

```toml
# services/documentation-generation/pyproject.toml
[tool.poetry]
name = "documentation-generation"
version = "0.1.0"
description = "Documentation Generation System for Neural Hive-Mind"
authors = ["Neural Hive-Mind Team"]

[tool.poetry.dependencies]
python = "^3.12"
fastapi = "^0.104.0"
uvicorn = {extras = ["standard"], version = "^0.24.0"}
pydantic = "^2.0"
pydantic-settings = "^2.0"
motor = "^3.0"
redis = {extras = ["hiredis"], version = "^5.0"}
aiokafka = "^0.9.0"
structlog = "^23.0"
openai = "^1.0"
anthropic = "^0.7"
python-multipart = "^0.0.6"
markdown = "^3.5"
pyyaml = "^6.0"

[tool.poetry.group.dev.dependencies]
pytest = "^7.4"
pytest-asyncio = "^0.21"
pytest-cov = "^4.1"
black = "^23.0"
ruff = "^0.1"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

- [ ] **Step 2: Criar settings.py**

```python
# services/documentation-generation/src/config/settings.py
"""Configurações do Documentation Generation Service."""

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações centralizadas."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="DOC_GEN_",
    )

    # API
    api_title: str = "Documentation Generation API"
    api_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8014

    # LLM
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    llm_provider: str = "openai"
    llm_model: str = "gpt-4-turbo-preview"
    llm_temperature: float = 0.5

    # Storage
    mongodb_url: str = Field(default="mongodb://localhost:27017", validation_alias="MONGODB_URL")
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")

    # Kafka
    kafka_bootstrap_servers: str = Field(default="localhost:9092", validation_alias="KAFKA_BOOTSTRAP_SERVERS")

    # Funcionalidades
    enable_readme_generation: bool = True
    enable_api_docs_generation: bool = True
    enable_architecture_docs: bool = True
    enable_diagram_generation: bool = True


@lru_cache
def get_settings() -> Settings:
    """Singleton das configurações."""
    return Settings()
```

- [ ] **Step 3: Commit**

```bash
git add services/documentation-generation/pyproject.toml \
        services/documentation-generation/src/
git commit -m "feat(documentation-generation): add base structure"
```

---

## Task 10: Criar modelos de documentação

**Files:**
- Create: `services/documentation-generation/src/models/__init__.py`
- Create: `services/documentation-generation/src/models/documentation.py`
- Create: `services/documentation-generation/src/models/diagram.py`

- [ ] **Step 1: Criar modelos**

```python
# services/documentation-generation/src/models/documentation.py
"""Modelos de dados para documentação."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DocType(str, Enum):
    """Tipo de documentação."""

    README = "readme"
    API_DOCS = "api_docs"
    ARCHITECTURE = "architecture"
    SEQUENCE_DIAGRAM = "sequence_diagram"
    FLOW_DIAGRAM = "flow_diagram"
    C4_CONTEXT = "c4_context"
    C4_CONTAINER = "c4_container"


class DocFormat(str, Enum):
    """Formato de saída."""

    MARKDOWN = "markdown"
    HTML = "html"
    PDF = "pdf"
    SVG = "svg"


class Documentation(BaseModel):
    """Documento gerado."""

    id: str = Field(..., description="ID único")
    doc_type: DocType = Field(..., description="Tipo de documento")
    title: str = Field(..., description="Título do documento")
    content: str = Field(..., description="Conteúdo do documento")
    format: DocFormat = Field(default=DocFormat.MARKDOWN, description="Formato")

    # Metadados
    artifact_id: Optional[str] = Field(None, description="ID do artefato relacionado")
    architecture_plan_id: Optional[str] = Field(None, description="ID do plano de arquitetura")
    requirements_set_id: Optional[str] = Field(None, description="ID do conjunto de requisitos")

    # Versão
    version: int = Field(default=1, description="Versão do documento")
    checksum: str = Field(default="", description="Checksum para verificação de mudanças")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(None)

    # Métricas
    word_count: int = Field(default=0, description="Contagem de palavras")
    section_count: int = Field(default=0, description="Contagem de secções")

    metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentationSet(BaseModel):
    """Conjunto de documentos para um projeto."""

    id: str = Field(..., description="ID único")
    project_id: str = Field(..., description="ID do projeto")
    documents: List[Documentation] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(None)

    def get_by_type(self, doc_type: DocType) -> List[Documentation]:
        """Filtra documentos por tipo."""
        return [d for d in self.documents if d.doc_type == doc_type]

    def add_document(self, doc: Documentation) -> None:
        """Adiciona um documento."""
        self.documents.append(doc)
        self.updated_at = datetime.utcnow()
```

```python
# services/documentation-generation/src/models/diagram.py
"""Modelos de dados para diagramas."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DiagramType(str, Enum):
    """Tipo de diagrama."""

    SEQUENCE = "sequence"
    FLOWCHART = "flowchart"
    C4_CONTEXT = "c4_context"
    C4_CONTAINER = "c4_container"
    C4_COMPONENT = "c4_component"
    ENTITY_RELATIONSHIP = "entity_relationship"
    CLASS = "class"
    STATE = "state"


class Diagram(BaseModel):
    """Diagrama gerado."""

    id: str = Field(..., description="ID único")
    diagram_type: DiagramType = Field(..., description="Tipo de diagrama")
    title: str = Field(..., description="Título do diagrama")
    mermaid_code: str = Field(..., description="Código Mermaid")

    # Renderização
    svg_path: Optional[str] = Field(None, description="Caminho para SVG renderizado")
    png_path: Optional[str] = Field(None, description="Caminho para PNG renderizado")

    # Metadados
    artifact_id: Optional[str] = Field(None)
    architecture_plan_id: Optional[str] = Field(None)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Métricas
    node_count: int = Field(default=0, description="Número de nós")
    edge_count: int = Field(default=0, description="Número de arestas")

    metadata: Dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 2: Criar __init__.py**

```python
# services/documentation-generation/src/models/__init__.py
"""Modelos do Documentation Generation Service."""

from .diagram import Diagram, DiagramType
from .documentation import DocFormat, DocType, Documentation, DocumentationSet

__all__ = [
    "Documentation",
    "DocumentationSet",
    "DocType",
    "DocFormat",
    "Diagram",
    "DiagramType",
]
```

- [ ] **Step 3: Commit**

```bash
git add services/documentation-generation/src/models/
git commit -m "feat(documentation-generation): add data models"
```

---

## Task 11: Implementar ReadmeGenerator

**Files:**
- Create: `services/documentation-generation/src/generators/__init__.py`
- Create: `services/documentation-generation/src/generators/readme_generator.py`
- Create: `services/documentation-generation/tests/unit/test_readme_generator.py`

- [ ] **Step 1: Escrever teste**

```python
# services/documentation-generation/tests/unit/test_readme_generator.py
"""Testes para ReadmeGenerator."""

import pytest

from documentation_generation.generators.readme_generator import ReadmeGenerator


@pytest.fixture
def generator():
    return ReadmeGenerator()


def test_generate_readme_minimal(generator):
    """Testa geração de README mínimo."""
    result = generator.generate(
        service_name="test-service",
        description="Test service description"
    )

    assert "# test-service" in result
    assert "Test service description" in result


def test_generate_readme_with_sections(generator):
    """Testa geração de README com secções."""
    result = generator.generate(
        service_name="my-service",
        description="My service",
        sections=["installation", "usage", "api"]
    )

    assert "## Installation" in result
    assert "## Usage" in result
    assert "## API" in result
```

- [ ] **Step 2: Executar teste**

Expected: FAIL

- [ ] **Step 3: Implementar ReadmeGenerator**

```python
# services/documentation-generation/src/generators/readme_generator.py
"""Gerador de README.md."""

from typing import List, Optional, Dict, Any


class ReadmeGenerator:
    """Gerador de arquivos README."""

    def generate(
        self,
        service_name: str,
        description: str,
        sections: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Gera conteúdo README.md.

        Args:
            service_name: Nome do serviço
            description: Descrição do serviço
            sections: Secções a incluir
            metadata: Metadados adicionais

        Returns:
            Conteúdo do README em Markdown
        """
        lines = []

        # Título
        lines.append(f"# {service_name}")
        lines.append("")

        # Descrição
        lines.append(description)
        lines.append("")

        # Badges (se houver metadata)
        if metadata:
            lines.extend(self._generate_badges(metadata))
            lines.append("")

        # Secções
        if sections is None:
            sections = ["installation", "usage", "api", "license"]

        for section in sections:
            lines.extend(self._generate_section(section, metadata))
            lines.append("")

        return "\n".join(lines)

    def _generate_badges(self, metadata: Dict[str, Any]) -> List[str]:
        """Gera badges para o README."""
        lines = []
        if metadata.get("version"):
            lines.append(f"![Version](https://img.shields.io/badge/version-{metadata['version']}-blue)")
        if metadata.get("python_version"):
            lines.append(f"![Python](https://img.shields.io/badge/python-{metadata['python_version']}-green)")
        if metadata.get("license"):
            lines.append(f"![License](https://img.shields.io/badge/license-{metadata['license']}-brightgreen)")
        return lines

    def _generate_section(self, section: str, metadata: Optional[Dict[str, Any]]) -> List[str]:
        """Gera uma secção do README."""
        sections_map = {
            "installation": self._installation_section,
            "usage": self._usage_section,
            "api": self._api_section,
            "license": self._license_section,
            "contributing": self._contributing_section,
            "tests": self._tests_section,
        }

        generator = sections_map.get(section, lambda m: [])
        return generator(metadata)

    def _installation_section(self, metadata: Optional[Dict[str, Any]]) -> List[str]:
        """Secção de instalação."""
        return [
            "## Installation",
            "",
            "```bash",
            "pip install .",
            "```",
            ""
        ]

    def _usage_section(self, metadata: Optional[Dict[str, Any]]) -> List[str]:
        """Secção de uso."""
        return [
            "## Usage",
            "",
            "```python",
            "from service import main",
            "main()",
            "```",
            ""
        ]

    def _api_section(self, metadata: Optional[Dict[str, Any]]) -> List[str]:
        """Secção de API."""
        return [
            "## API",
            "",
            "### Endpoints",
            "",
            "| Method | Path | Description |",
            "|--------|------|-------------|",
            "| GET | /health | Health check |",
            "| POST | /api/v1/process | Process data |",
            ""
        ]

    def _license_section(self, metadata: Optional[Dict[str, Any]]) -> List[str]:
        """Secção de licença."""
        license_name = metadata.get("license", "MIT")
        return [
            "## License",
            "",
            f"This project is licensed under the {license_name} License.",
            ""
        ]

    def _contributing_section(self, metadata: Optional[Dict[str, Any]]) -> List[str]:
        """Secção de contribuição."""
        return [
            "## Contributing",
            "",
            "1. Fork the repository",
            "2. Create your feature branch (`git checkout -b feature/amazing-feature`)",
            "3. Commit your changes (`git commit -m 'Add some amazing feature'`)",
            "4. Push to the branch (`git push origin feature/amazing-feature`)",
            "5. Open a Pull Request",
            ""
        ]

    def _tests_section(self, metadata: Optional[Dict[str, Any]]) -> List[str]:
        """Secção de testes."""
        return [
            "## Tests",
            "",
            "```bash",
            "pytest",
            "```",
            ""
        ]
```

- [ ] **Step 4: Criar package**

```python
# services/documentation-generation/src/generators/__init__.py
"""Geradores de documentação."""

from .readme_generator import ReadmeGenerator

__all__ = ["ReadmeGenerator"]
```

- [ ] **Step 5: Executar testes**

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/documentation-generation/src/generators/ \
        services/documentation-generation/tests/unit/test_readme_generator.py
git commit -m "feat(documentation-generation): implement ReadmeGenerator"
```

---

## Task 12: Implementar APIDocsGenerator

**Files:**
- Create: `services/documentation-generation/src/generators/api_docs_generator.py`
- Create: `services/documentation-generation/tests/unit/test_api_docs_generator.py`

- [ ] **Step 1: Escrever teste**

```python
# services/documentation-generation/tests/unit/test_api_docs_generator.py
"""Testes para APIDocsGenerator."""

import pytest

from documentation_generation.generators.api_docs_generator import APIDocsGenerator


@pytest.fixture
def generator():
    return APIDocsGenerator()


def test_generate_openapi_spec(generator):
    """Testa geração de especificação OpenAPI."""
    endpoints = [
        {
            "path": "/users",
            "method": "GET",
            "summary": "List users",
            "parameters": [{"name": "limit", "in": "query", "type": "integer"}],
            "responses": {"200": {"description": "OK"}}
        }
    ]

    spec = generator.generate_openapi(
        title="Users API",
        version="1.0.0",
        endpoints=endpoints
    )

    assert spec["info"]["title"] == "Users API"
    assert "/users" in spec["paths"]
    assert spec["paths"]["/users"]["get"]["summary"] == "List users"


def test_generate_markdown_docs(generator):
    """Testa geração de documentação Markdown."""
    endpoints = [
        {
            "path": "/users",
            "method": "GET",
            "summary": "List users",
            "description": "Returns a list of users"
        }
    ]

    md = generator.generate_markdown(
        title="Users API",
        endpoints=endpoints
    )

    assert "# Users API" in md
    assert "## GET /users" in md
    assert "List users" in md
```

- [ ] **Step 2: Executar teste**

Expected: FAIL

- [ ] **Step 3: Implementar APIDocsGenerator**

```python
# services/documentation-generation/src/generators/api_docs_generator.py
"""Gerador de documentação de API (OpenAPI/Swagger)."""

from typing import Any, Dict, List
import json


class APIDocsGenerator:
    """Gerador de especificações OpenAPI e documentação de API."""

    def generate_openapi(
        self,
        title: str,
        version: str,
        endpoints: List[Dict[str, Any]],
        base_url: str = "/api/v1"
    ) -> Dict[str, Any]:
        """Gera especificação OpenAPI.

        Args:
            title: Título da API
            version: Versão da API
            endpoints: Lista de endpoints
            base_url: URL base

        Returns:
            Dicionário com especificação OpenAPI
        """
        spec = {
            "openapi": "3.0.0",
            "info": {
                "title": title,
                "version": version
            },
            "servers": [
                {"url": base_url}
            ],
            "paths": {}
        }

        for endpoint in endpoints:
            path = endpoint["path"]
            method = endpoint["method"].lower()

            if path not in spec["paths"]:
                spec["paths"][path] = {}

            spec["paths"][path][method] = self._build_operation(endpoint)

        return spec

    def generate_markdown(
        self,
        title: str,
        endpoints: List[Dict[str, Any]],
        base_url: str = "/api/v1"
    ) -> str:
        """Gera documentação em Markdown.

        Args:
            title: Título da API
            endpoints: Lista de endpoints
            base_url: URL base

        Returns:
            Conteúdo Markdown
        """
        lines = [
            f"# {title}",
            "",
            f"Base URL: `{base_url}`",
            "",
            "## Endpoints",
            ""
        ]

        for endpoint in endpoints:
            lines.extend(self._format_endpoint_markdown(endpoint))
            lines.append("")

        return "\n".join(lines)

    def _build_operation(self, endpoint: Dict[str, Any]) -> Dict[str, Any]:
        """Constrói objeto operation do OpenAPI."""
        operation = {
            "summary": endpoint.get("summary", ""),
            "responses": endpoint.get("responses", {"200": {"description": "OK"}})
        }

        if "description" in endpoint:
            operation["description"] = endpoint["description"]

        if "parameters" in endpoint:
            operation["parameters"] = [
                {
                    "name": p["name"],
                    "in": p.get("in", "query"),
                    "schema": {"type": p.get("type", "string")},
                    "required": p.get("required", False)
                }
                for p in endpoint["parameters"]
            ]

        if "requestBody" in endpoint:
            operation["requestBody"] = endpoint["requestBody"]

        return operation

    def _format_endpoint_markdown(self, endpoint: Dict[str, Any]) -> List[str]:
        """Formata endpoint para Markdown."""
        method = endpoint["method"].upper()
        path = endpoint["path"]
        summary = endpoint.get("summary", "")

        lines = [
            f"### {method} {path}",
            ""
        ]

        if summary:
            lines.append(f"**Summary:** {summary}")
            lines.append("")

        if "description" in endpoint:
            lines.append(endpoint["description"])
            lines.append("")

        if "parameters" in endpoint and endpoint["parameters"]:
            lines.append("**Parameters:**")
            lines.append("")
            lines.append("| Name | In | Type | Required |")
            lines.append("|------|-----|------|----------|")
            for p in endpoint["parameters"]:
                required = "Yes" if p.get("required") else "No"
                lines.append(f"| {p['name']} | {p.get('in', 'query')} | {p.get('type', 'string')} | {required} |")
            lines.append("")

        return lines

    def to_json(self, spec: Dict[str, Any]) -> str:
        """Converte especificação para JSON."""
        return json.dumps(spec, indent=2)

    def to_yaml(self, spec: Dict[str, Any]) -> str:
        """Converte especificação para YAML."""
        try:
            import yaml
            return yaml.dump(spec, default_flow_style=False)
        except ImportError:
            # Fallback para JSON se yaml não disponível
            return self.to_json(spec)
```

- [ ] **Step 4: Atualizar __init__.py**

```python
# services/documentation-generation/src/generators/__init__.py
"""Geradores de documentação."""

from .api_docs_generator import APIDocsGenerator
from .readme_generator import ReadmeGenerator

__all__ = ["ReadmeGenerator", "APIDocsGenerator"]
```

- [ ] **Step 5: Executar testes**

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/documentation-generation/src/generators/api_docs_generator.py \
        services/documentation-generation/tests/unit/test_api_docs_generator.py
git commit -m "feat(documentation-generation): implement APIDocsGenerator"
```

---

## Task 13: Implementar DiagramGenerator com Mermaid

**Files:**
- Create: `services/documentation-generation/src/generators/diagram_generator.py`
- Create: `services/documentation-generation/src/generators/mermaid_renderer.py`
- Create: `services/documentation-generation/tests/unit/test_diagram_generator.py`

- [ ] **Step 1: Escrever testes**

```python
# services/documentation-generation/tests/unit/test_diagram_generator.py
"""Testes para DiagramGenerator."""

import pytest

from documentation_generation.generators.diagram_generator import DiagramGenerator
from documentation_generation.models.diagram import DiagramType


@pytest.fixture
def generator():
    return DiagramGenerator()


def test_generate_sequence_diagram(generator):
    """Testa geração de diagrama de sequência."""
    mermaid = generator.generate_sequence(
        title="User Login Flow",
        actors=["User", "API", "Database"],
        steps=[
            {"from": "User", "to": "API", "message": "POST /login"},
            {"from": "API", "to": "Database", "message": "Query user"},
            {"from": "Database", "to": "API", "message": "Return user"},
            {"from": "API", "to": "User", "message": "Return token"}
        ]
    )

    assert "sequenceDiagram" in mermaid
    assert "User" in mermaid
    assert "API" in mermaid
    assert "Database" in mermaid
    assert "POST /login" in mermaid


def test_generate_flowchart(generator):
    """Testa geração de fluxograma."""
    mermaid = generator.generate_flowchart(
        title="Request Flow",
        nodes=[
            {"id": "start", "label": "Start", "shape": "rounded"},
            {"id": "process", "label": "Process", "shape": "rectangle"},
            {"id": "end", "label": "End", "shape": "rounded"}
        ],
        edges=[
            {"from": "start", "to": "process"},
            {"from": "process", "to": "end"}
        ]
    )

    assert "graph TD" in mermaid
    assert "start" in mermaid
    assert "process" in mermaid


def test_generate_c4_context(generator):
    """Testa geração de diagrama C4 Context."""
    mermaid = generator.generate_c4_context(
        system_name="E-commerce System",
        description="Online sales platform",
        actors=["Customer", "Admin"],
        external_systems=["Payment Gateway", "Inventory System"]
    )

    assert "C4 Context" in mermaid
    assert "E-commerce System" in mermaid
    assert "Customer" in mermaid
```

- [ ] **Step 2: Executar testes**

Expected: FAIL

- [ ] **Step 3: Implementar DiagramGenerator**

```python
# services/documentation-generation/src/generators/diagram_generator.py
"""Gerador de diagramas Mermaid."""

from typing import Any, Dict, List


class DiagramGenerator:
    """Gerador de diagramas usando sintaxe Mermaid."""

    def generate_sequence(
        self,
        title: str,
        actors: List[str],
        steps: List[Dict[str, str]]
    ) -> str:
        """Gera diagrama de sequência.

        Args:
            title: Título do diagrama
            actors: Lista de actores/participantes
            steps: Passos da sequência (from, to, message)

        Returns:
            Código Mermaid
        """
        lines = [
            "sequenceDiagram",
            f"    title {title}",
            ""
        ]

        # Declarar actores
        for i, actor in enumerate(actors, 1):
            lines.append(f"    actor {actor} as {actor}")

        lines.append("")

        # Adicionar passos
        for step in steps:
            from_actor = step.get("from", "Anonymous")
            to_actor = step.get("to", "Anonymous")
            message = step.get("message", "")

            # Verificar se é uma resposta
            if step.get("is_response"):
                lines.append(f"    {to_actor}-->>{from_actor}: {message}")
            else:
                lines.append(f"    {from_actor}->>{to_actor}: {message}")

        return "\n".join(lines)

    def generate_flowchart(
        self,
        title: str,
        nodes: List[Dict[str, str]],
        edges: List[Dict[str, str]],
        direction: str = "TD"
    ) -> str:
        """Gera fluxograma.

        Args:
            title: Título do diagrama
            nodes: Lista de nós (id, label, shape)
            edges: Lista de arestas (from, to, label)
            direction: Direção (TD, LR, BT, RL)

        Returns:
            Código Mermaid
        """
        lines = [
            f"graph {direction}",
            f'    title["{title}"]',
            ""
        ]

        # Mapa de formas
        shape_map = {
            "rounded": "([{}])",
            "rectangle": "[{}]",
            "diamond": "{{{}}}",
            "circle": "(({}))",
            "stadium": "([{}])",
            "subroutine": "[[{}]]",
            "cylinder": "[({})]",
            "circle": "(({}))"
        }

        # Adicionar nós
        for node in nodes:
            node_id = node["id"]
            label = node.get("label", node_id)
            shape = node.get("shape", "rounded")
            shape_template = shape_map.get(shape, "([{}])")

            # Escapar colchetes no label
            label_safe = label.replace("[", "\\[").replace("]", "\\]")

            lines.append(f"    {node_id}{shape_template.format(label_safe)}")

        lines.append("")

        # Adicionar arestas
        for edge in edges:
            from_node = edge["from"]
            to_node = edge["to"]
            label = edge.get("label", "")
            line_style = edge.get("style", "-->")

            if label:
                lines.append(f"    {from_node} {line_style}|{label}| {to_node}")
            else:
                lines.append(f"    {from_node} {line_style} {to_node}")

        return "\n".join(lines)

    def generate_c4_context(
        self,
        system_name: str,
        description: str,
        actors: List[str],
        external_systems: List[str] = None
    ) -> str:
        """Gera diagrama C4 Context.

        Args:
            system_name: Nome do sistema
            description: Descrição do sistema
            actors: Lista de actores
            external_systems: Lista de sistemas externos

        Returns:
            Código Mermaid C4
        """
        lines = [
            "C4Context",
            f"    title {system_name} - Context Diagram",
            "",
            f"    Person(customer, \"Customer\", \"A user of {system_name}\")",
            ""
        ]

        # Adicionar outros actores
        for actor in actors:
            if actor.lower() != "customer":
                actor_id = actor.lower().replace(" ", "_")
                lines.append(f'    Person({actor_id}, "{actor}", "A user of the system")')

        lines.append("")
        lines.append(f'    System(system, "{system_name}", "{description}")')

        lines.append("")

        # Relacionamentos
        lines.append(f'    Rel(customer, system, "Uses")')

        if external_systems:
            for ext_sys in external_systems:
                sys_id = ext_sys.lower().replace(" ", "_").replace("-", "_")
                lines.append(f'    System_Ext({sys_id}, "{ext_sys}", "External system")')
                lines.append(f'    Rel(system, {sys_id}, "Uses")')

        return "\n".join(lines)

    def generate_entity_relationship(
        self,
        entities: List[Dict[str, str]],
        relationships: List[Dict[str, str]]
    ) -> str:
        """Gera diagrama entidade-relacionamento.

        Args:
            entities: Lista de entidades (id, name, columns)
            relationships: Lista de relacionamentos

        Returns:
            Código Mermaid ERD
        """
        lines = ["erDiagram", ""]

        # Adicionar entidades e colunas
        for entity in entities:
            entity_id = entity["id"]
            entity_name = entity.get("name", entity_id)
            columns = entity.get("columns", [])

            col_str = " ".join(columns) if columns else "id field"
            lines.append(f"    {entity_id}{{{entity_name}}} {{")

            for col in columns:
                if isinstance(col, dict):
                    lines.append(f"        {col.get('name')} {col.get('type', 'string')}")
                else:
                    lines.append(f"        {col}")

            lines.append("    }")

        # Adicionar relacionamentos
        for rel in relationships:
            from_ent = rel["from"]
            to_ent = rel["to"]
            rel_type = rel.get("type", "o||--|{")
            label = rel.get("label", "")

            if label:
                lines.append(f"    {from_ent} {rel_type} {to_ent} : \"{label}\"")
            else:
                lines.append(f"    {from_ent} {rel_type} {to_ent}")

        return "\n".join(lines)
```

- [ ] **Step 4: Implementar MermaidRenderer**

```python
# services/documentation-generation/src/generators/mermaid_renderer.py
"""Renderer para diagramas Mermaid (Mermaid → SVG)."""

import subprocess
import tempfile
from pathlib import Path
from typing import Optional


class MermaidRenderer:
    """Renderiza diagramas Mermaid para SVG/PNG."""

    def __init__(self, mmdc_path: str = "mmdc"):
        """Inicializa o renderer.

        Args:
            mmdc_path: Caminho para o executável mmdc (mermaid-cli)
        """
        self.mmdc_path = mmdc_path

    async def render_to_svg(
        self,
        mermaid_code: str,
        output_path: Optional[str] = None
    ) -> str:
        """Renderiza código Mermaid para SVG.

        Args:
            mermaid_code: Código Mermaid
            output_path: Caminho para salvar (opcional)

        Returns:
            Caminho para o arquivo SVG gerado
        """
        if output_path is None:
            # Criar arquivo temporário
            with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
                output_path = f.name

        # Criar arquivo temporário para input Mermaid
        with tempfile.NamedTemporaryFile(mode="w", suffix=".mmd", delete=False) as f:
            f.write(mermaid_code)
            input_path = f.name

        try:
            # Executar mmdc
            subprocess.run(
                [
                    self.mmdc_path,
                    "-i", input_path,
                    "-o", output_path,
                    "-b", "transparent"
                ],
                check=True,
                capture_output=True
            )

            return output_path

        finally:
            # Limpar arquivo temporário de input
            Path(input_path).unlink(missing_ok=True)

    async def render_to_png(
        self,
        mermaid_code: str,
        output_path: Optional[str] = None
    ) -> str:
        """Renderiza código Mermaid para PNG.

        Args:
            mermaid_code: Código Mermaid
            output_path: Caminho para salvar (opcional)

        Returns:
            Caminho para o arquivo PNG gerado
        """
        if output_path is None:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                output_path = f.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".mmd", delete=False) as f:
            f.write(mermaid_code)
            input_path = f.name

        try:
            subprocess.run(
                [
                    self.mmdc_path,
                    "-i", input_path,
                    "-o", output_path,
                    "-b", "transparent"
                ],
                check=True,
                capture_output=True
            )

            return output_path

        finally:
            Path(input_path).unlink(missing_ok=True)

    def is_available(self) -> bool:
        """Verifica se mermaid-cli está disponível."""
        try:
            result = subprocess.run(
                [self.mmdc_path, "--version"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
```

- [ ] **Step 5: Executar testes**

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/documentation-generation/src/generators/diagram_generator.py \
        services/documentation-generation/src/generators/mermaid_renderer.py \
        services/documentation-generation/tests/unit/test_diagram_generator.py
git commit -m "feat(documentation-generation): implement DiagramGenerator with Mermaid support"
```

---

## Task 14: Criar API REST e main.py

**Files:**
- Create: `services/documentation-generation/src/main.py`
- Create: `services/documentation-generation/src/api/routers/documentation.py`

- [ ] **Step 1: Criar main.py**

```python
# services/documentation-generation/src/main.py
"""Aplicação FastAPI para Documentation Generation Service."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers.documentation import router as docs_router
from config.settings import get_settings


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager."""
    print(f"Starting {settings.api_title} on port {settings.port}")
    yield
    print(f"Stopping {settings.api_title}")


app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(docs_router, prefix=settings.api_prefix)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "service": "documentation-generation",
        "status": "healthy",
        "version": settings.api_version
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=False
    )
```

- [ ] **Step 2: Criar router documentation.py**

```python
# services/documentation-generation/src/api/routers/documentation.py
"""Router REST para documentação."""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ...generators.readme_generator import ReadmeGenerator
from ...generators.api_docs_generator import APIDocsGenerator
from ...generators.diagram_generator import DiagramGenerator
from ...models.documentation import DocType


router = APIRouter(prefix="/docs", tags=["documentation"])


class ReadmeRequest(BaseModel):
    """Request para geração de README."""
    service_name: str
    description: str
    sections: Optional[List[str]] = None


class APIDocsRequest(BaseModel):
    """Request para geração de docs de API."""
    title: str
    version: str
    endpoints: List[dict]
    base_url: str = "/api/v1"


class DiagramRequest(BaseModel):
    """Request para geração de diagrama."""
    diagram_type: str
    title: str
    data: dict


@router.post("/readme")
async def generate_readme(request: ReadmeRequest):
    """Gera README.md."""
    generator = ReadmeGenerator()
    content = generator.generate(
        service_name=request.service_name,
        description=request.description,
        sections=request.sections
    )
    return {"content": content, "format": "markdown"}


@router.post("/api")
async def generate_api_docs(request: APIDocsRequest):
    """Gera documentação de API."""
    generator = APIDocsGenerator()

    spec = generator.generate_openapi(
        title=request.title,
        version=request.version,
        endpoints=request.endpoints,
        base_url=request.base_url
    )

    return {"spec": spec, "format": "openapi"}


@router.post("/api/markdown")
async def generate_api_docs_markdown(request: APIDocsRequest):
    """Gera documentação de API em Markdown."""
    generator = APIDocsGenerator()

    content = generator.generate_markdown(
        title=request.title,
        endpoints=request.endpoints,
        base_url=request.base_url
    )

    return {"content": content, "format": "markdown"}


@router.post("/diagram")
async def generate_diagram(request: DiagramRequest):
    """Gera diagrama Mermaid."""
    generator = DiagramGenerator()

    if request.diagram_type == "sequence":
        mermaid = generator.generate_sequence(
            title=request.title,
            actors=request.data.get("actors", []),
            steps=request.data.get("steps", [])
        )
    elif request.diagram_type == "flowchart":
        mermaid = generator.generate_flowchart(
            title=request.title,
            nodes=request.data.get("nodes", []),
            edges=request.data.get("edges", [])
        )
    elif request.diagram_type == "c4_context":
        mermaid = generator.generate_c4_context(
            system_name=request.title,
            description=request.data.get("description", ""),
            actors=request.data.get("actors", []),
            external_systems=request.data.get("external_systems", [])
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported diagram type: {request.diagram_type}"
        )

    return {"mermaid": mermaid, "format": "mermaid"}
```

- [ ] **Step 3: Criar packages**

```python
# services/documentation-generation/src/api/__init__.py
"""API REST do Documentation Generation Service."""
```

```python
# services/documentation-generation/src/api/routers/__init__.py
"""Routers."""
```

- [ ] **Step 4: Commit**

```bash
git add services/documentation-generation/src/main.py \
        services/documentation-generation/src/api/
git commit -m "feat(documentation-generation): add FastAPI REST endpoints"
```

---

## Task 15: Criar deployment manifests e finalização

**Files:**
- Create: `services/documentation-generation/deployment/Dockerfile`
- Create: `services/documentation-generation/deployment/k8s-deployment.yaml`
- Create: `services/documentation-generation/deployment/k8s-service.yaml`

- [ ] **Step 1: Criar Dockerfile**

```dockerfile
# services/documentation-generation/deployment/Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Instalar dependências
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --only=main --no-dev

# Instalar mermaid-cli (opcional, para renderização de diagramas)
RUN npm install -g @mermaid-js/mermaid-cli

# Copiar código
COPY src/ ./src/

# Expor porta
EXPOSE 8014

# Executar
CMD ["poetry", "run", "python", "src/main.py"]
```

- [ ] **Step 2: Criar k8s-deployment.yaml**

```yaml
# services/documentation-generation/deployment/k8s-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: documentation-generation
  labels:
    app: documentation-generation
spec:
  replicas: 2
  selector:
    matchLabels:
      app: documentation-generation
  template:
    metadata:
      labels:
        app: documentation-generation
    spec:
      containers:
      - name: documentation-generation
        image: documentation-generation:latest
        ports:
        - containerPort: 8014
        env:
        - name: DOC_GEN_OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: llm-secrets
              key: openai-api-key
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8014
          initialDelaySeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 8014
          initialDelaySeconds: 5
```

- [ ] **Step 3: Criar k8s-service.yaml**

```yaml
# services/documentation-generation/deployment/k8s-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: documentation-generation
spec:
  selector:
    app: documentation-generation
  ports:
  - protocol: TCP
    port: 8014
    targetPort: 8014
  type: ClusterIP
```

- [ ] **Step 4: Commit final**

```bash
git add services/documentation-generation/deployment/
git commit -m "feat(documentation-generation): add Kubernetes deployment manifests"
```

---

## Resumo dos Serviços Criados

### Requirements Engineering System (8010)

**Componentes implementados:**
- `RequirementsEngineer` - Geração de requisitos funcionais e não-funcionais
- `UserStoryGenerator` - Geração de user stories no formato padrão
- `AcceptanceCriteriaGenerator` - Geração de critérios Gherkin (Given-When-Then)
- REST API `/api/v1/requirements/generate`
- Kafka consumer para `cognitive.plans.created`
- Kafka producer para `requirements.generated`

**Testes:** 4 test suites (requirements_engineer, user_story_generator, acceptance_criteria_generator)

### Documentation Generation System (8014)

**Componentes implementados:**
- `ReadmeGenerator` - Geração de README.md com secções configuráveis
- `APIDocsGenerator` - Geração de OpenAPI/Swagger e docs Markdown
- `DiagramGenerator` - Geração de diagramas Mermaid (sequence, flowchart, C4)
- `MermaidRenderer` - Renderização de Mermaid para SVG/PNG
- REST API endpoints para todos os tipos de documentação

**Testes:** 3 test suites (readme_generator, api_docs_generator, diagram_generator)

---

## Próximos Passos

**Fase 3: Knowledge & Approvals**
- Knowledge Graph RAG (8016)
- Approval Gateway (8017)

**Fase 4: Orchestration Integration**
- Integração de todos os serviços no orchestrator-dynamic
- Fluxo completo Kafka de ponta a ponta

**Fase 5: Testing & Hardening**
- Testes E2E do fluxo completo
- Performance tuning
- Security hardening
