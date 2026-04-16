# Fluxo G - Fase 1: Foundation (architect-agent extensions)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Estender o serviço architect-agent (8008) com três novos módulos: BoundedContextsIdentifier, TechStackRecommender e ArchitectureDiagramGenerator, permitindo geração de arquitetura mais completa com bounded contexts, recomendação de stack técnico e diagramas C4/Mermaid.

**Architecture:** O architect-agent existente gera planos de arquitetura com componentes e padrões. Vamos adicionar três novos módulos ao serviço existente: (1) BoundedContextsIdentifier usa LLM para identificar bounded contexts baseado em DDD, (2) TechStackRecommender recomenda tecnologias baseado em requisitos e preferências, (3) ArchitectureDiagramGenerator gera diagramas Mermaid/C4 que são renderizados para SVG.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic, OpenAI API (ou Anthropic), Neo4j, mermaid-cli, MongoDB, structlog

---

## Estrutura de Ficheiros

```
services/architect-agent/
├── src/
│   ├── identifiers/
│   │   ├── __init__.py
│   │   ├── bounded_contexts.py          # NOVO - Identificação de BCs
│   │   └── domain_analyzer.py            # NOVO - Análise de domínio
│   ├── recommenders/
│   │   ├── __init__.py
│   │   ├── tech_stack.py                 # NOVO - Recomendação de stack
│   │   └── knowledge_base.py             # NOVO - Base de conhecimento tech
│   ├── generators/
│   │   ├── __init__.py
│   │   ├── diagram_generator.py          # NOVO - Geração de diagramas
│   │   ├── c4_diagram.py                 # NOVO - Diagramas C4
│   │   └── mermaid_renderer.py           # NOVO - Renderer Mermaid→SVG
│   ├── models/
│   │   ├── architecture.py                # EXTENDER - novos modelos
│   │   ├── bounded_context.py             # NOVO - modelo de BC
│   │   └── tech_stack.py                  # NOVO - modelo de tech stack
│   ├── services/
│   │   └── design_planner.py              # MODIFICAR - integrar novos módulos
│   └── api/
│       └── routers/
│           └── architecture.py            # MODIFICAR - novos endpoints
├── tests/
│   ├── unit/
│   │   ├── test_bounded_contexts.py      # NOVO
│   │   ├── test_tech_stack.py             # NOVO
│   │   └── test_diagram_generator.py      # NOVO
│   └── integration/
│       └── test_architecture_extended.py # NOVO
└── pyproject.toml                        # MODIFICAR - novas dependências
```

---

## Task 1: Configurar base para novos módulos

**Files:**
- Create: `services/architect-agent/src/identifiers/__init__.py`
- Create: `services/architect-agent/src/recommenders/__init__.py`
- Create: `services/architect-agent/src/generators/__init__.py`

- [ ] **Step 1: Criar pacote identifiers**

```python
# services/architect-agent/src/identifiers/__init__.py
"""Bounded Context identification module."""

from architect_service.identifiers.bounded_contexts import (
    BoundedContextsIdentifier,
    BoundedContext
)

__all__ = ["BoundedContextsIdentifier", "BoundedContext"]
```

- [ ] **Step 2: Criar pacote recommenders**

```python
# services/architect-agent/src/recommenders/__init__.py
"""Tech stack recommendation module."""

from architect_service.recommenders.tech_stack import (
    TechStackRecommender,
    TechStackRecommendation
)

__all__ = ["TechStackRecommender", "TechStackRecommendation"]
```

- [ ] **Step 3: Criar pacote generators**

```python
# services/architect-agent/src/generators/__init__.py
"""Diagram generation module."""

from architect_service.generators.diagram_generator import (
    ArchitectureDiagramGenerator,
    Diagram
)

__all__ = ["ArchitectureDiagramGenerator", "Diagram"]
```

- [ ] **Step 4: Commit**

```bash
cd services/architect-agent
git add src/identifiers src/recommenders src/generators
git commit -m "feat(architect-agent): add base packages for new modules"
```

---

## Task 2: Adicionar dependências ao projeto

**Files:**
- Modify: `services/architect-agent/pyproject.toml`

- [ ] **Step 1: Ler dependências atuais**

```bash
cat services/architect-agent/pyproject.toml
```

- [ ] **Step 2: Adicionar novas dependências**

Adicionar à secção `[tool.poetry.dependencies]`:

```toml
[tool.poetry.dependencies]
python = "^3.12"
fastapi = "^0.104.0"
pydantic = "^2.0"
motor = "^3.0"
neo4j = "^5.0"
openai = "^1.0"
anthropic = "^0.7"
structlog = "^23.0"
python-multipart = "^0.0.6"

# NOVAS dependências para diagramas
pyyaml = "^6.0"               # para parse Mermaid config
requests = "^2.31"            # para chamar mermaid-cli API
click = "^8.1"                # para CLI commands

[tool.poetry.dev-dependencies]
pytest = "^7.4"
pytest-asyncio = "^0.21"
pytest-cov = "^4.1"
black = "^23.0"
ruff = "^0.1"
mypy = "^1.5"
```

- [ ] **Step 3: Instalar dependências**

```bash
cd services/architect-agent
poetry lock
poetry install
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml poetry.lock
git commit -m "feat(architect-agent): add dependencies for diagram generation"
```

---

## Task 3: Criar modelos de Bounded Context

**Files:**
- Create: `services/architect-agent/src/models/bounded_context.py`

- [ ] **Step 1: Criar modelos Pydantic**

```python
# services/architect-agent/src/models/bounded_context.py
"""Bounded Context data models."""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class UbiquitousLanguageTerm(BaseModel):
    """Termo da linguagem ubíqua do bounded context."""
    
    term: str = Field(..., description="Termo específico do domínio")
    definition: str = Field(..., description="Definição clara do termo")
    examples: List[str] = Field(default_factory=list, description="Exemplos de uso")


class BoundedContextRelationship(BaseModel):
    """Relacionamento entre bounded contexts."""
    
    from_context: str = Field(..., alias="from")
    to_context: str = Field(..., alias="to")
    relationship_type: str = Field(
        ..., 
        description="Tipo de relacionamento: partnership, shared_kernel, etc."
    )
    description: Optional[str] = Field(None, description="Descrição da integração")


class BoundedContext(BaseModel):
    """Bounded Context (DDD)."""
    
    name: str = Field(..., description="Nome do contexto (ex: Identity, Billing)")
    description: str = Field(..., description="Descrição do propósito do contexto")
    responsibilities: List[str] = Field(
        ..., 
        description="Lista de responsabilidades deste contexto"
    )
    domain_models: List[str] = Field(
        ..., 
        description="Lista de modelos de domínio principais"
    )
    relationships: List[BoundedContextRelationship] = Field(
        default_factory=list,
        description="Relacionamentos com outros contextos"
    )
    ubiquitous_language: List[UbiquitousLanguageTerm] = Field(
        default_factory=list,
        description="Termos específicos do domínio"
    )
    
    class Config:
        populate_by_name = True


class BoundedContextsAnalysis(BaseModel):
    """Resultado da análise de bounded contexts."""
    
    contexts: List[BoundedContext]
    total_contexts: int = Field(..., ge=1)
    analysis_timestamp: datetime = Field(default_factory=datetime.utcnow)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
```

- [ ] **Step 2: Commit**

```bash
git add src/models/bounded_context.py
git commit -m "feat(architect-agent): add BoundedContext models"
```

---

## Task 4: Implementar BoundedContextsIdentifier

**Files:**
- Create: `services/architect-agent/src/identifiers/bounded_contexts.py`
- Test: `services/architect-agent/tests/unit/test_bounded_contexts.py`

- [ ] **Step 1: Escrever teste falhando**

```python
# services/architect-agent/tests/unit/test_bounded_contexts.py

import pytest
from architect_service.identifiers.bounded_contexts import BoundedContextsIdentifier
from architect_service.models.bounded_context import BoundedContext, BoundedContextsAnalysis


@pytest.mark.asyncio
async def test_identify_bounded_contexts_simple():
    """Testa identificação de bounded contexts para sistema simples."""
    
    identifier = BoundedContextsIdentifier()
    
    requirements = """
    Sistema de e-commerce com:
    - Gestão de utilizadores e autenticação
    - Catálogo de produtos e categorias
    - Carrinho de compras e checkout
    - Processamento de pagamentos
    - Gestão de encomendas e envio
    """
    
    result = await identifier.identify(requirements)
    
    assert isinstance(result, BoundedContextsAnalysis)
    assert result.total_contexts >= 2
    assert any(ctx.name == "Identity" for ctx in result.contexts)
    assert any(ctx.name == "Catalog" for ctx in result.contexts)


@pytest.mark.asyncio
async def test_identify_bounded_contexts_returns_ubiquitous_language():
    """Testa que termos ubiquituos são identificados."""
    
    identifier = BoundedContextsIdentifier()
    
    requirements = """
    Sistema de gestão de tarefas onde:
    - Utilizadores podem criar tarefas
    - Tarefas podem ser atribuídas a membros da equipa
    - Comentários podem ser adicionados às tarefas
    """
    
    result = await identifier.identify(requirements)
    
    # Verificar que pelo menos um contexto tem termos ubiquituos
    has_terms = any(
        len(ctx.ubiquitous_language) > 0 
        for ctx in result.contexts
    )
    assert has_terms
```

- [ ] **Step 2: Correr teste para verificar falha**

```bash
cd services/architect-agent
pytest tests/unit/test_bounded_contexts.py -v
```

Expected: `ModuleNotFoundError: No module named 'architect_service.identifiers.bounded_contexts'`

- [ ] **Step 3: Implementar BoundedContextsIdentifier**

```python
# services/architect-agent/src/identifiers/bounded_contexts.py

from typing import List, Optional
from openai import AsyncOpenAI
from structlog import get_logger

from architect_service.models.bounded_context import (
    BoundedContext,
    BoundedContextRelationship,
    BoundedContextsAnalysis,
    UbiquitousLanguageTerm
)

logger = get_logger(__name__)


class BoundedContextsIdentifier:
    """Identifica Bounded Contexts baseado em DDD."""
    
    PROMPT_TEMPLATE = """
    Você é um especialista em Domain-Driven Design (DDD).
    
    Analise os seguintes requisitos e identifique os Bounded Contexts.
    
    REQUISITOS:
    {requirements}
    
    Para cada Bounded Context, especifique:
    1. Nome: Nome claro e conciso (ex: Identity, Billing, Catalog)
    2. Descrição: Propósito principal do contexto
    3. Responsabilidades: Lista do que este contexto é responsável
    4. Domain Models: Lista de modelos de domínio principais
    5. Linguagem Ubíqua: 3-5 termos específicos do domínio com definições
    
    Relacionamentos entre contextos:
    - Partnership: Colaboração necessária
    - Shared Kernel: Models partilhados
    - Customer-Supplier: Dependência direta
    - Conformist: Seguindo convenções externas
    
    Responda em formato JSON válido com esta estrutura:
    {{
      "contexts": [
        {{
          "name": "Nome",
          "description": "Descrição",
          "responsibilities": ["resp1", "resp2"],
          "domain_models": ["Model1", "Model2"],
          "ubiquitous_language": [
            {{"term": "Termo", "definition": "Definição"}}
          ],
          "relationships": [
            {{"from": "ContextoA", "to": "ContextoB", "type": "Partnership", "description": "..."}}
          ]
        }}
      ],
      "confidence_score": 0.9
    }}
    """
    
    def __init__(
        self,
        llm_client: Optional[AsyncOpenAI] = None,
        model: str = "gpt-4"
    ):
        self._llm_client = llm_client or AsyncOpenAI()
        self._model = model
        self._logger = logger
    
    async def identify(
        self,
        requirements: str,
        domain_hints: Optional[List[str]] = None
    ) -> BoundedContextsAnalysis:
        """
        Identifica bounded contexts a partir de requisitos.
        
        Args:
            requirements: Texto com requisitos do sistema
            domain_hints: Lista opcional de nomes de contextos sugeridos
            
        Returns:
            BoundedContextsAnalysis com contexts identificados
        """
        self._logger.info("identifying_bounded_contexts", domain_hints=domain_hints)
        
        prompt = self.PROMPT_TEMPLATE.format(requirements=requirements)
        
        if domain_hints:
            prompt += f"\n\nSUGESTÕES DE CONTEXTOS: {', '.join(domain_hints)}"
        
        try:
            response = await self._llm_client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "Você é um especialista em DDD."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3
            )
            
            import json
            result_data = json.loads(response.choices[0].message.content)
            
            contexts = [
                self._parse_context(ctx_data)
                for ctx_data in result_data.get("contexts", [])
            ]
            
            analysis = BoundedContextsAnalysis(
                contexts=contexts,
                total_contexts=len(contexts),
                confidence_score=result_data.get("confidence_score", 0.8)
            )
            
            self._logger.info(
                "bounded_contexts_identified",
                count=len(contexts),
                confidence=analysis.confidence_score
            )
            
            return analysis
            
        except Exception as e:
            self._logger.error("failed_to_identify_contexts", error=str(e))
            raise
    
    def _parse_context(self, ctx_data: dict) -> BoundedContext:
        """Parse dados brutos para BoundedContext."""
        
        relationships = [
            BoundedContextRelationship(
                from_context=rel["from"],
                to_context=rel["to"],
                relationship_type=rel["type"],
                description=rel.get("description")
            )
            for rel in ctx_data.get("relationships", [])
        ]
        
        ubiquitous_language = [
            UbiquitousLanguageTerm(
                term=term["term"],
                definition=term["definition"],
                examples=term.get("examples", [])
            )
            for term in ctx_data.get("ubiquitous_language", [])
        ]
        
        return BoundedContext(
            name=ctx_data["name"],
            description=ctx_data["description"],
            responsibilities=ctx_data.get("responsibilities", []),
            domain_models=ctx_data.get("domain_models", []),
            relationships=relationships,
            ubiquitous_language=ubiquitous_language
        )
```

- [ ] **Step 4: Correr teste para verificar passagem**

```bash
pytest tests/unit/test_bounded_contexts.py::test_identify_bounded_contexts_simple -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/identifiers/bounded_contexts.py tests/unit/test_bounded_contexts.py
git commit -m "feat(architect-agent): implement BoundedContextsIdentifier"
```

---

## Task 5: Criar modelos de Tech Stack

**Files:**
- Create: `services/architect-agent/src/models/tech_stack.py`

- [ ] **Step 1: Criar modelos Pydantic**

```python
# services/architect-agent/src/models/tech_stack.py
"""Tech Stack recommendation models."""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class TechChoice(BaseModel):
    """Escolha tecnológica."""
    
    category: str = Field(..., description="ex: backend, database, frontend")
    name: str = Field(..., description="ex: FastAPI, PostgreSQL, React")
    version: Optional[str] = Field(None, description="Versão recomendada")
    rationale: str = Field(..., description="Por que esta tecnologia")
    alternatives: List[str] = Field(default_factory=list)


class Constraint(BaseModel):
    """Restrição técnica."""
    
    type: str = Field(..., description="ex: language, framework, hosting")
    value: str = Field(..., description="Valor da restrição")
    reason: Optional[str] = Field(None, description="Razão da restrição")


class TechStackRecommendation(BaseModel):
    """Recomendação completa de stack tecnológico."""
    
    choices: List[TechChoice]
    constraints_satisfied: List[str]
    constraints_violated: List[str] = Field(default_factory=list)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    estimated_cost: Optional[str] = Field(None, description="Estimativa de custo mensal")
    estimated_complexity: Optional[str] = Field(None, description="baixa, media, alta")
```

- [ ] **Step 2: Commit**

```bash
git add src/models/tech_stack.py
git commit -m "feat(architect-agent): add TechStack models"
```

---

## Task 6: Implementar TechStackRecommender

**Files:**
- Create: `services/architect-agent/src/recommenders/knowledge_base.py`
- Create: `services/architect-agent/src/recommenders/tech_stack.py`
- Test: `services/architect-agent/tests/unit/test_tech_stack.py`

- [ ] **Step 1: Criar base de conhecimento**

```python
# services/architect-agent/src/recommenders/knowledge_base.py

"""Knowledge base for tech stack recommendations."""

TECH_KNOWLEDGE_BASE = {
    "backend": {
        "python": {
            "frameworks": {
                "fastapi": {
                    "pros": ["async nativo", "type hints", "performance", "API automática"],
                    "cons": ["ecosistema menor que Django/Flask"],
                    "use_cases": ["APIs REST", "microserviços", "high performance"],
                    "complexity": "media",
                    "learning_curve": "media"
                },
                "django": {
                    "pros": ["batteries included", "admin ORM", "ecosistema enorme"],
                    "cons": ["pesado", "sync por padrão", "verboso"],
                    "use_cases": ["monólitos", "CRUD apps", "prototipagem rápida"],
                    "complexity": "baixa",
                    "learning_curve": "baixa"
                }
            }
        },
        "nodejs": {
            "frameworks": {
                "express": {
                    "pros": ["minimal", "flexível", "ecosistema NPM"],
                    "cons": ["pouco opinionado", "requer setup manual"],
                    "use_cases": ["APIs", "microserviços", "serverless"],
                    "complexity": "baixa",
                    "learning_curve": "baixa"
                },
                "nest": {
                    "pros": ["TypeScript nativo", "estruturado", "injeção de dependências"],
                    "cons": ["curva de aprendizado", "verboso"],
                    "use_cases": ["apps empresariais", "microserviços"],
                    "complexity": "media",
                    "learning_curve": "media"
                }
            }
        }
    },
    "database": {
        "relational": {
            "postgresql": {
                "pros": ["ACID", "JSON support", "extensível", "open source"],
                "cons": ["setup mais complexo que SQLite"],
                "use_cases": ["dados estruturados", "transações", "analytics"],
                "complexity": "media",
                "cost": "baixo"
            },
            "mysql": {
                "pros": ["popular", "robusto", "boa performance"],
                "cons": ["licenciamento em alguns casos"],
                "use_cases": ["web apps", "e-commerce"],
                "complexity": "media",
                "cost": "baixo"
            }
        },
        "nosql": {
            "mongodb": {
                "pros": ["flexível", "schemaless", "boa para documentos"],
                "cons": ["sem ACID nativo em algumas operações"],
                "use_cases": ["dados dinâmicos", "prototipagem", "hierarchical data"],
                "complexity": "baixa",
                "cost": "baixo"
            },
            "redis": {
                "pros": ["rápido", "in-memory", "versátil"],
                "cons": ["volátil por padrão", "tamanho limitado"],
                "use_cases": ["cache", "sessions", "rate limiting", "queues"],
                "complexity": "baixa",
                "cost": "baixo"
            }
        }
    },
    "messaging": {
        "kafka": {
            "pros": ["escalável", "durável", "event streaming"],
            "cons": ["complexo", "requer ZooKeeper/KRaft"],
            "use_cases": ["event-driven", "microserviços", "data pipelines"],
            "complexity": "alta",
            "cost": "alto"
        },
        "rabbitmq": {
            "pros": ["flexível", "simples", "work queues"],
            "cons": ["menos escalável que Kafka"],
            "use_cases": ["work queues", "request/response"],
            "complexity": "media",
            "cost": "baixo"
        }
    }
}
```

- [ ] **Step 2: Escrever teste falhando**

```python
# services/architect-agent/tests/unit/test_tech_stack.py

import pytest
from architect_service.recommenders.tech_stack import TechStackRecommender


@pytest.mark.asyncio
async def test_recommend_tech_stack_for_api():
    """Testa recomendação de stack para API REST."""
    
    recommender = TechStackRecommender()
    
    requirements = "API REST para gestão de tarefas com alta concorrência"
    constraints = [{"type": "language", "value": "Python"}]
    
    result = await recommender.recommend(requirements, constraints)
    
    assert len(result.choices) > 0
    assert any(c.category == "backend" for c in result.choices)
    assert result.constraints_satisfied == ["language: Python"]


@pytest.mark.asyncio
async def test_recommend_with_postgresql_preference():
    """Testa recomendação com preferência de PostgreSQL."""
    
    recommender = TechStackRecommender()
    
    requirements = "Sistema transacional com dados relacionais"
    constraints = [{"type": "database", "value": "PostgreSQL"}]
    
    result = await recommender.recommend(requirements, constraints)
    
    db_choice = next((c for c in result.choices if c.category == "database"), None)
    assert db_choice is not None
    assert "PostgreSQL" in db_choice.name
```

- [ ] **Step 3: Correr teste para verificar falha**

```bash
pytest tests/unit/test_tech_stack.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 4: Implementar TechStackRecommender**

```python
# services/architect-agent/src/recommenders/tech_stack.py

from typing import List, Optional
from openai import AsyncOpenAI
from structlog import get_logger

from architect_service.models.tech_stack import (
    TechStackRecommendation,
    TechChoice,
    Constraint
)
from architect_service.recommenders.knowledge_base import TECH_KNOWLEDGE_BASE

logger = get_logger(__name__)


class TechStackRecommender:
    """Recomenda stack tecnológico baseado em requisitos."""
    
    PROMPT_TEMPLATE = """
    Analise os requisitos e recomende um stack tecnológico.
    
    REQUISITOS:
    {requirements}
    
    RESTRIÇÕES:
    {constraints}
    
    Baseado no conhecimento disponível, recomenda tecnologias para:
    1. Backend framework
    2. Database primária
    3. Cache/Messaging (se necessário)
    
    Para cada escolha, justifique com base nos requisitos.
    
    Responda em JSON:
    {{
      "choices": [
        {{"category": "backend", "name": "FastAPI", "version": "0.104", "rationale": "..."}},
        {{"category": "database", "name": "PostgreSQL", "version": "15", "rationale": "..."}}
      ],
      "constraints_satisfied": ["Python", "PostgreSQL"],
      "constraints_violated": [],
      "confidence_score": 0.9,
      "estimated_complexity": "media",
      "estimated_cost": "$$$"
    }}
    """
    
    def __init__(
        self,
        llm_client: Optional[AsyncOpenAI] = None,
        model: str = "gpt-4"
    ):
        self._llm_client = llm_client or AsyncOpenAI()
        self._model = model
        self._logger = logger
        self._knowledge_base = TECH_KNOWLEDGE_BASE
    
    async def recommend(
        self,
        requirements: str,
        constraints: Optional[List[dict]] = None
    ) -> TechStackRecommendation:
        """Recomenda stack tecnológico."""
        
        self._logger.info("recommending_tech_stack", constraints=constraints)
        
        prompt = self.PROMPT_TEMPLATE.format(
            requirements=requirements,
            constraints=self._format_constraints(constraints or [])
        )
        
        try:
            response = await self._llm_client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "Você é um arquiteto de software especialista."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3
            )
            
            import json
            result_data = json.loads(response.choices[0].message.content)
            
            choices = [
                TechChoice(
                    category=choice["category"],
                    name=choice["name"],
                    version=choice.get("version"),
                    rationale=choice["rationale"]
                )
                for choice in result_data.get("choices", [])
            ]
            
            recommendation = TechStackRecommendation(
                choices=choices,
                constraints_satisfied=result_data.get("constraints_satisfied", []),
                constraints_violated=result_data.get("constraints_violated", []),
                confidence_score=result_data.get("confidence_score", 0.8),
                estimated_complexity=result_data.get("estimated_complexity"),
                estimated_cost=result_data.get("estimated_cost")
            )
            
            self._logger.info(
                "tech_stack_recommended",
                choices_count=len(choices),
                complexity=recommendation.estimated_complexity
            )
            
            return recommendation
            
        except Exception as e:
            self._logger.error("failed_to_recommend_tech_stack", error=str(e))
            raise
    
    def _format_constraints(self, constraints: List[dict]) -> str:
        """Formata restrições para o prompt."""
        if not constraints:
            return "Nenhuma"
        
        return "\n".join(
            f"- {c.get('type', 'N/A')}: {c.get('value', 'N/A')}"
            for c in constraints
        )
```

- [ ] **Step 5: Correr testes para verificar passagem**

```bash
pytest tests/unit/test_tech_stack.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/recommenders/knowledge_base.py src/recommenders/tech_stack.py tests/unit/test_tech_stack.py
git commit -m "feat(architect-agent): implement TechStackRecommender"
```

---

## Task 7: Criar modelos de Diagramas

**Files:**
- Create: `services/architect-agent/src/models/diagrams.py`

- [ ] **Step 1: Criar modelos**

```python
# services/architect-agent/src/models/diagrams.py

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class DiagramType(str, Enum):
    """Tipos de diagramas suportados."""
    C4_CONTEXT = "c4_context"
    C4_CONTAINER = "c4_container"
    C4_COMPONENT = "c4_component"
    SEQUENCE = "sequence"
    DEPLOYMENT = "deployment"
    ENTITY_RELATIONSHIP = "er"


class Diagram(BaseModel):
    """Diagrama de arquitetura."""
    
    diagram_id: str
    type: DiagramType
    title: str
    mermaid_code: str
    svg_url: Optional[str] = None
    created_at: str
    
    class Config:
        populate_by_name = True
```

- [ ] **Step 2: Commit**

```bash
git add src/models/diagrams.py
git commit -m "feat(architect-agent): add Diagram models"
```

---

## Task 8: Implementar ArchitectureDiagramGenerator

**Files:**
- Create: `services/architect-agent/src/generators/diagram_generator.py`
- Create: `services/architect-agent/src/generators/c4_diagram.py`
- Create: `services/architect-agent/src/generators/mermaid_renderer.py`
- Test: `services/architect-agent/tests/unit/test_diagram_generator.py`

- [ ] **Step 1: Escrever testes falhando**

```python
# services/architect-agent/tests/unit/test_diagram_generator.py

import pytest
from architect_service.generators.diagram_generator import ArchitectureDiagramGenerator
from architect_service.models.diagrams import DiagramType
from architect_service.models.architecture import ArchitecturePlan


@pytest.mark.asyncio
async def test_generate_c4_context_diagram():
    """Testa geração de diagrama C4 Context."""
    
    generator = ArchitectureDiagramGenerator()
    
    # Criar um plano de arquitetura simples
    plan = ArchitecturePlan(
        architecture_id="test_001",
        requirements_id="req_001",
        architecture_type="MICROSERVICES",
        bounded_contexts=[],
        components=[],
        patterns=[],
        diagrams=[]
    )
    
    result = await generator.generate_c4_context(plan)
    
    assert result.mermaid_code is not None
    assert "C4Context" in result.mermaid_code
    assert result.type == DiagramType.C4_CONTEXT


@pytest.mark.asyncio
async def test_generate_sequence_diagram():
    """Testa geração de diagrama de sequência."""
    
    generator = ArchitectureDiagramGenerator()
    
    result = await generator.generate_sequence(
        title="Login Flow",
        steps=[
            {"from": "User", "to": "API", "action": "POST /login"},
            {"from": "API", "to": "Database", "action": "SELECT user"},
            {"from": "API", "to": "User", "action": "Return token"}
        ]
    )
    
    assert "sequenceDiagram" in result.mermaid_code
    assert "User" in result.mermaid_code
```

- [ ] **Step 2: Correr testes para verificar falha**

```bash
pytest tests/unit/test_diagram_generator.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implementar C4 diagram generator**

```python
# services/architect-agent/src/generators/c4_diagram.py

from typing import List
from architect_service.models.architecture import ArchitecturePlan, Component


class C4DiagramGenerator:
    """Gera diagramas C4."""
    
    @staticmethod
    def generate_context(
        project_name: str,
        system_description: str,
        actors: List[str],
        external_systems: List[str]
    ) -> str:
        """Gera diagrama C4 Context."""
        
        actors_block = "\n".join(
            f'    Person({actor.lower()}, "{actor}", "User")'
            for actor in actors
        )
        
        system_block = f"""
    System(system, "{project_name}", "{system_description}")
"""
        
        external_block = "\n".join(
            f"""    System_Ext({ext.lower()}, "{ext}", "External System")"""
            for ext in external_systems
        )
        
        relationships = "\n".join([
            "    Rel(user, system, \"Usa\")",
            "    Rel(system, external1, \"Integra via API\")"
        ])
        
        return f"""C4Context
    title {project_name} - Context Diagram

{actors_block}
{system_block}
{external_block}

{relationships}
"""
    
    @staticmethod
    def generate_container(
        project_name: str,
        containers: List[Component]
    ) -> str:
        """Gera diagrama C4 Container."""
        
        containers_block = ""
        for container in containers:
            containers_block += f"""
    ContainerDb({container.name}_db, "{container.name} Database", "{container.tech_stack}", "Storage")
    Container({container.name}, "{container.display_name}", "{container.tech_stack}", "{container.description}")
    Rel({container.name}, {container.name}_db, "Lê/Escreve", "JDBC/ORM")
"""
        
        return f"""C4Container
    title {project_name} - Container Diagram

{containers_block}
"""
    
    @staticmethod
    def generate_component(
        component_name: str,
        component_description: str,
        subcomponents: List[str]
    ) -> str:
        """Gera diagrama C4 Component."""
        
        components_block = ""
        for sub in subcomponents:
            components_block += f"""
    Component({sub.lower()}, "{sub}", "Module", "Functionality")
"""
        
        return f"""C4Component
    title {component_name} - Component Diagram

    Component(controller, "Controller", "REST API", "Exposes endpoints")
    Component(service, "Service", "Business Logic", "Processes requests")
    Component(repository, "Repository", "Data Access", "Query database")

{components_block}

    Rel(controller, service, "Chama")
    Rel(service, repository, "Usa")
"""
```

- [ ] **Step 4: Implementar Mermaid renderer**

```python
# services/architect-agent/src/generators/mermaid_renderer.py

import os
import subprocess
import tempfile
from typing import Optional
from structlog import get_logger

logger = get_logger(__name__)


class MermaidRenderer:
    """Renderiza código Mermaid para SVG."""
    
    def __init__(
        self,
        mermaid_cli_path: str = "/usr/local/bin/mmd",
        timeout: int = 30
    ):
        self._mermaid_cli = mermaid_cli_path
        self._timeout = timeout
        self._logger = logger
    
    async def render_to_svg(
        self,
        mermaid_code: str,
        output_dir: Optional[str] = None
    ) -> str:
        """
        Renderiza código Mermaid para SVG.
        
        Returns:
            URL ou caminho do SVG gerado
        """
        self._logger.info("rendering_mermaid_diagram")
        
        # Criar ficheiro temporário com o código
        with tempfile.NamedTemporaryFile(mode='w', suffix='.mmd', delete=False) as f:
            f.write(mermaid_code)
            mmd_file = f.name
        
        try:
            # Chamar mermaid-cli
            svg_file = mmd_file.replace('.mmd', '.svg')
            
            result = subprocess.run(
                [self._mermaid_cli, '-i', mmd_file, '-o', svg_file],
                capture_output=True,
                text=True,
                timeout=self._timeout
            )
            
            if result.returncode != 0:
                self._logger.error(
                    "mermaid_render_failed",
                    stderr=result.stderr
                )
                raise RuntimeError(f"Mermaid render failed: {result.stderr}")
            
            # Ler SVG ou mover para local permanente
            if output_dir:
                import shutil
                os.makedirs(output_dir, exist_ok=True)
                final_path = os.path.join(output_dir, os.path.basename(svg_file))
                shutil.move(svg_file, final_path)
                os.unlink(mmd_file)
                return final_path
            
            # Retornar conteúdo SVG
            with open(svg_file, 'r') as f:
                svg_content = f.read()
            
            # Limpar temporários
            os.unlink(mmd_file)
            os.unlink(svg_file)
            
            # Em produção, fazer upload para S3 e retornar URL
            return svg_content
            
        except subprocess.TimeoutExpired:
            self._logger.error("mermaid_render_timeout")
            raise TimeoutError("Mermaid rendering timed out")
        finally:
            if os.path.exists(mmd_file):
                os.unlink(mmd_file)
```

- [ ] **Step 5: Implementar diagram generator principal**

```python
# services/architect-agent/src/generators/diagram_generator.py

from typing import List, Optional, Dict, Any
from openai import AsyncOpenAI
from structlog import get_logger

from architect_service.models.diagrams import Diagram, DiagramType
from architect_service.models.architecture import ArchitecturePlan, Component
from architect_service.generators.c4_diagram import C4DiagramGenerator
from architect_service.generators.mermaid_renderer import MermaidRenderer

logger = get_logger(__name__)


class ArchitectureDiagramGenerator:
    """Gera diagramas de arquitetura."""
    
    SEQUENCE_PROMPT = """
    Gere um diagrama de sequência Mermaid para o seguinte fluxo:
    
    {flow_description}
    
    O diagrama deve mostrar a interação entre componentes.
    Use formato: sequenceDiagram
    
    Responda apenas com o código Mermaid, sem markdown.
    """
    
    def __init__(
        self,
        llm_client: Optional[AsyncOpenAI] = None,
        mermaid_renderer: Optional[MermaidRenderer] = None
    ):
        self._llm_client = llm_client or AsyncOpenAI()
        self._renderer = mermaid_renderer or MermaidRenderer()
        self._c4_generator = C4DiagramGenerator()
        self._logger = logger
    
    async def generate_c4_context(
        self,
        plan: ArchitecturePlan,
        actors: Optional[List[str]] = None
    ) -> Diagram:
        """Gera diagrama C4 Context."""
        
        self._logger.info("generating_c4_context", architecture_id=plan.architecture_id)
        
        # Extrair atores das user stories se não fornecidos
        if not actors:
            actors = ["User"]  # Default
        
        # Extrair sistemas externos dos relacionamentos
        external_systems = []
        for component in plan.components:
            if "external" in component.name.lower():
                external_systems.append(component.name)
        
        mermaid_code = self._c4_generator.generate_context(
            project_name=plan.architecture_id,
            system_description=f"Architecture for {plan.architecture_id}",
            actors=actors,
            external_systems=external_systems
        )
        
        # Render para SVG
        try:
            svg_content = await self._renderer.render_to_svg(mermaid_code)
            # TODO: Upload para S3 e obter URL
            svg_url = f"/diagrams/{plan.architecture_id}_context.svg"
        except Exception as e:
            self._logger.warning("svg_render_failed", error=str(e))
            svg_url = None
        
        return Diagram(
            diagram_id=f"{plan.architecture_id}_context",
            type=DiagramType.C4_CONTEXT,
            title="C4 Context Diagram",
            mermaid_code=mermaid_code,
            svg_url=svg_url,
            created_at=plan.generated_at if hasattr(plan, 'generated_at') else ""
        )
    
    async def generate_sequence(
        self,
        title: str,
        steps: List[Dict[str, str]],
        artifacts: Optional[List[str]] = None
    ) -> Diagram:
        """Gera diagrama de sequência."""
        
        self._logger.info("generating_sequence_diagram", title=title)
        
        # Gerar código Mermaid
        participants = set()
        for step in steps:
            participants.add(step.get("from"))
            participants.add(step.get("to"))
        
        mermaid_code = "sequenceDiagram\n"
        
        for participant in sorted(participants):
            mermaid_code += f'    Participant("{participant}", {participant})\n'
        
        for step in steps:
            mermaid_code += f'    {step["from"]} ->> {step["to"]}: {step["action"]}\n'
        
        # Render
        try:
            svg_content = await self._renderer.render_to_svg(mermaid_code)
            svg_url = f"/diagrams/{title.replace(' ', '_').lower()}_sequence.svg"
        except Exception as e:
            self._logger.warning("svg_render_failed", error=str(e))
            svg_url = None
        
        return Diagram(
            diagram_id=title.lower().replace(" ", "_"),
            type=DiagramType.SEQUENCE,
            title=title,
            mermaid_code=mermaid_code,
            svg_url=svg_url,
            created_at=""
        )
    
    async def generate_from_description(
        self,
        description: str
    ) -> Diagram:
        """Gera diagrama a partir de descrição em linguagem natural."""
        
        self._logger.info("generating_diagram_from_description")
        
        response = await self._llm_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Você é um especialista em diagramas UML e Mermaid."},
                {"role": "user", "content": self.SEQUENCE_PROMPT.format(flow_description=description)}
            ],
            temperature=0.3
        )
        
        mermaid_code = response.choices[0].message.content.strip()
        
        # Limpar markdown se presente
        if mermaid_code.startswith("```"):
            mermaid_code = mermaid_code.split("\n", 1)[-1].rstrip("\n`")
        
        return await self.generate_sequence(
            title="Generated Diagram",
            steps=[]  # Steps já estão no mermaid_code
        )
```

- [ ] **Step 6: Atualizar testes e correr**

```bash
pytest tests/unit/test_diagram_generator.py -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/generators/ tests/unit/test_diagram_generator.py
git commit -m "feat(architect-agent): implement ArchitectureDiagramGenerator"
```

---

## Task 9: Integrar novos módulos no DesignPlanner

**Files:**
- Modify: `services/architect-agent/src/services/design_planner.py`

- [ ] **Step 1: Ler código existente**

```bash
cat services/architect-agent/src/services/design_planner.py
```

- [ ] **Step 2: Adicionar imports dos novos módulos**

```python
# Adicionar ao topo do ficheiro, após imports existentes

from architect_service.identifiers.bounded_contexts import BoundedContextsIdentifier
from architect_service.recommenders.tech_stack import TechStackRecommender
from architect_service.generators.diagram_generator import ArchitectureDiagramGenerator
from architect_service.models.bounded_context import BoundedContext
from architect_service.models.tech_stack import TechStackRecommendation
from architect_service.models.diagrams import Diagram
```

- [ ] **Step 3: Modificar método __init__ do DesignPlanner**

```python
# Adicionar novos parâmetros ao __init__:

class DesignPlanner:
    def __init__(
        self,
        llm_client: Optional[AsyncOpenAI] = None,
        mongo_client: Optional[AsyncMongoClient] = None,
        neo4j_client: Optional[Neo4jClient] = None,
        kafka_producer: Optional[AIOKafkaProducer] = None,
        # NOVOS módulos
        bounded_contexts_identifier: Optional[BoundedContextsIdentifier] = None,
        tech_stack_recommender: Optional[TechStackRecommender] = None,
        diagram_generator: Optional[ArchitectureDiagramGenerator] = None,
    ):
        # ... código existente ...
        
        # Inicializar novos módulos
        self._bounded_contexts_identifier = bounded_contexts_identifier or BoundedContextsIdentifier(llm_client)
        self._tech_stack_recommender = tech_stack_recommender or TechStackRecommender(llm_client)
        self._diagram_generator = diagram_generator or ArchitectureDiagramGenerator(llm_client)
```

- [ ] **Step 4: Modificar método plan() para usar novos módulos**

```python
# No método plan(), após gerar componentes e padrões, adicionar:

async def plan(self, requirements: str, context: Optional[Dict] = None) -> ArchitecturePlan:
    # ... código existente para gerar componentes e padrões ...
    
    # NOVO: Identificar bounded contexts
    self._logger.info("identifying_bounded_contexts")
    contexts_analysis = await self._bounded_contexts_identifier.identify(requirements)
    bounded_contexts = [
        BoundedContext(
            name=ctx.name,
            description=ctx.description,
            responsibilities=ctx.responsibilities,
            domain_models=ctx.domain_models,
            relationships=[],
            ubiquitous_language=ctx.ubiquitous_language
        )
        for ctx in contexts_analysis.contexts
    ]
    
    # NOVO: Recomendar tech stack
    self._logger.info("recommending_tech_stack")
    tech_recommendation = await self._tech_stack_recommender.recommend(
        requirements=requirements,
        constraints=context.get("constraints") if context else None
    )
    
    # NOVO: Gerar diagramas C4
    self._logger.info("generating_c4_diagrams")
    c4_context_diagram = await self._diagram_generator.generate_c4_context(
        ArchitecturePlan(
            architecture_id="temp",
            requirements_id="temp",
            components=components,
            patterns=patterns,
            bounded_contexts=bounded_contexts
        )
    )
    
    # Criar plano com todos os elementos
    plan = ArchitecturePlan(
        architecture_id=str(uuid4()),
        requirements_id=context.get("requirements_id", "") if context else "",
        architecture_type=self._determine_architecture_type(requirements),
        bounded_contexts=bounded_contexts,
        components=components,
        patterns=patterns,
        diagrams=[c4_context_diagram],
        tech_stack=tech_recommendation.choices,
        rationale=self._generate_rationale(requirements, bounded_contexts, tech_recommendation),
        generated_at=datetime.utcnow()
    )
    
    return plan
```

- [ ] **Step 5: Commit**

```bash
git add src/services/design_planner.py
git commit -m "feat(architect-agent): integrate new modules into DesignPlanner"
```

---

## Task 10: Adicionar novos endpoints REST

**Files:**
- Modify: `services/architect-agent/src/api/routers/architecture.py`

- [ ] **Step 1: Ler código existente**

```bash
cat services/architect-agent/src/api/routers/architecture.py
```

- [ ] **Step 2: Adicionar endpoint para bounded contexts**

```python
# Adicionar novo endpoint após os existentes

@router.get("/architecture/{architecture_id}/bounded-contexts")
async def get_bounded_contexts(
    architecture_id: str,
    planner: DesignPlanner = Depends(get_design_planner)
):
    """Retorna bounded contexts de uma arquitetura."""
    
    plan = await planner.get_architecture_plan(architecture_id)
    
    if not plan:
        raise HTTPException(status_code=404, detail="Architecture not found")
    
    return {
        "architecture_id": architecture_id,
        "bounded_contexts": plan.bounded_contexts,
        "total_contexts": len(plan.bounded_contexts)
    }


@router.post("/architecture/identify-contexts")
async def identify_contexts(
    request: ContextIdentificationRequest,
    planner: DesignPlanner = Depends(get_design_planner)
):
    """Identifica bounded contexts independentemente de criar arquitetura."""
    
    result = await planner._bounded_contexts_identifier.identify(
        requirements=request.requirements,
        domain_hints=request.domain_hints
    )
    
    return result
```

- [ ] **Step 3: Adicionar endpoint para diagramas**

```python
@router.get("/architecture/{architecture_id}/diagrams")
async def get_diagrams(
    architecture_id: str,
    planner: DesignPlanner = Depends(get_design_planner)
):
    """Retorna diagramas de uma arquitetura."""
    
    plan = await planner.get_architecture_plan(architecture_id)
    
    if not plan:
        raise HTTPException(status_code=404, detail="Architecture not found")
    
    return {
        "architecture_id": architecture_id,
        "diagrams": plan.diagrams
    }


@router.post("/diagrams/generate")
async def generate_diagram(
    request: DiagramGenerationRequest,
    planner: DesignPlanner = Depends(get_design_planner)
):
    """Gera diagrama a partir de descrição."""
    
    diagram = await planner._diagram_generator.generate_from_description(
        description=request.description,
        diagram_type=request.diagram_type
    )
    
    return diagram
```

- [ ] **Step 4: Adicionar endpoint para tech stack**

```python
@router.post("/architecture/recommend-stack")
async def recommend_stack(
    request: TechStackRecommendationRequest,
    planner: DesignPlanner = Depends(get_design_planner)
):
    """Recomenda stack tecnológico."""
    
    recommendation = await planner._tech_stack_recommender.recommend(
        requirements=request.requirements,
        constraints=request.constraints
    )
    
    return recommendation
```

- [ ] **Step 5: Commit**

```bash
git add src/api/routers/architecture.py
git commit -m "feat(architect-agent): add new REST endpoints for extended features"
```

---

## Task 11: Criar testes de integração

**Files:**
- Create: `services/architect-agent/tests/integration/test_architecture_extended.py`

- [ ] **Step 1: Escrever teste de integração completo**

```python
# services/architect-agent/tests/integration/test_architecture_extended.py

import pytest
from httpx import AsyncClient
from architect_service.main import app


@pytest.mark.asyncio
async def test_full_architecture_generation_with_extensions():
    """Testa geração completa de arquitetura com novos módulos."""
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Fazer request para gerar arquitetura
        response = await client.post(
            "/api/v1/architecture",
            json={
                "requirements": "Sistema de gestão de tarefas colaborativa",
                "preferences": {
                    "language": "Python",
                    "database": "PostgreSQL"
                }
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verificar que bounded contexts foram gerados
        assert "bounded_contexts" in data
        assert len(data["bounded_contexts"]) >= 1
        
        # Verificar que tech stack foi recomendado
        assert "tech_stack" in data
        assert any(c["category"] == "backend" for c in data["tech_stack"])
        
        # Verificar que diagramas foram gerados
        assert "diagrams" in data
        assert len(data["diagrams"]) >= 1


@pytest.mark.asyncio
async def test_diagram_generation_endpoint():
    """Testa endpoint de geração de diagramas."""
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/diagrams/generate",
            json={
                "description": "Login flow: User -> API -> Database -> Return token",
                "diagram_type": "sequence"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "mermaid_code" in data
        assert "sequenceDiagram" in data["mermaid_code"]
```

- [ ] **Step 2: Commit**

```bash
git add tests/integration/test_architecture_extended.py
git commit -m "test(architect-agent): add integration tests for extended features"
```

---

## Task 12: Documentar novo módulo

**Files:**
- Create: `services/architect-agent/docs/BOUNDED_CONTEXTS.md`
- Create: `services/architect-agent/docs/TECH_STACK_RECOMMENDATION.md`
- Create: `services/architect-agent/docs/DIAGRAM_GENERATION.md`

- [ ] **Step 1: Criar documentação de bounded contexts**

```markdown
# Bounded Contexts Identifier

## Visão Geral

O módulo `BoundedContextsIdentifier` identifica Bounded Contexts baseado em Domain-Driven Design a partir de requisitos em linguagem natural.

## Uso

```python
from architect_service.identifiers.bounded_contexts import BoundedContextsIdentifier

identifier = BoundedContextsIdentifier()
analysis = await identifier.identify(
    requirements="Sistema de e-commerce com catálogo e pagamentos...",
    domain_hints=["Catalog", "Billing", "Identity"]
)

for context in analysis.contexts:
    print(f"{context.name}: {context.description}")
```

## API REST

```bash
curl -X POST "http://localhost:8008/api/v1/architecture/identify-contexts" \
  -H "Content-Type: application/json" \
  -d '{
    "requirements": "...",
    "domain_hints": ["Context1", "Context2"]
  }'
```

## Saída

```json
{
  "contexts": [
    {
      "name": "Catalog",
      "description": "Gestão de catálogo de produtos",
      "responsibilities": ["CRUD produtos", "Categorias", "Search"],
      "domain_models": ["Product", "Category", "SearchIndex"],
      "ubiquitous_language": [
        {"term": "SKU", "definition": "Stock Keeping Unit"}
      ]
    }
  ],
  "confidence_score": 0.9
}
```
```

- [ ] **Step 2: Criar documentação de diagramas**

```markdown
# Diagram Generation

## Visão Geral

O módulo `ArchitectureDiagramGenerator` gera diagramas Mermaid/C4 que são renderizados para SVG.

## Tipos de Diagramas

- **C4 Context**: Visão de alto nível do sistema
- **C4 Container**: Aplicações, databases, serviços
- **Sequence**: Interação entre componentes

## Uso

```python
from architect_service.generators.diagram_generator import ArchitectureDiagramGenerator

generator = ArchitectureDiagramGenerator()
diagram = await generator.generate_c4_context(plan)
```

## Mermaid CLI

O módulo usa `mermaid-cli` para renderizar diagramas:

```bash
mmd -i input.mmd -o output.svg
```

Instalação:
```bash
npm install -g @mermaid-js/mermaid-cli
```
```

- [ ] **Step 3: Commit**

```bash
git add docs/
git commit -m "docs(architect-agent): add documentation for extended features"
```

---

## Task 13: Configurar CI/CD

**Files:**
- Create: `.github/workflows/architect-agent-test.yml`

- [ ] **Step 1: Criar workflow GitHub Actions**

```yaml
name: Test Architect Agent

on:
  push:
    branches: [main, develop]
    paths:
      - 'services/architect-agent/**'
  pull_request:
    branches: [main]
    paths:
      - 'services/architect-agent/**'

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'
        cache: 'poetry'
    
    - name: Install dependencies
      working-directory: ./services/architect-agent
      run: |
        poetry install --no-interaction
    
    - name: Run linter
      working-directory: ./services/architect-agent
      run: poetry run ruff check .
    
    - name: Run type checker
      working-directory: ./services/architect-agent
      run: poetry run mypy src/
    
    - name: Run unit tests
      working-directory: ./services/architect-agent
      run: |
        poetry run pytest tests/unit/ -v --cov=src --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v4
      with:
        files: ./services/architect-agent/coverage.xml
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/architect-agent-test.yml
git commit -m "ci(architect-agent): add GitHub Actions workflow"
```

---

## Task 14: Deploy para staging

**Files:**
- Create: `services/architect-agent/deployment/k8s-deployment.yaml`
- Create: `services/architect-agent/deployment/k8s-service.yaml`

- [ ] **Step 1: Criar Kubernetes deployment**

```yaml
# services/architect-agent/deployment/k8s-deployment.yaml

apiVersion: apps/v1
kind: Deployment
metadata:
  name: architect-agent
  namespace: neural-hive-staging
spec:
  replicas: 2
  selector:
    matchLabels:
      app: architect-agent
  template:
    metadata:
      labels:
        app: architect-agent
        version: v1
    spec:
      containers:
      - name: architect-agent
        image: ghcr.io/neural-hive-mind/architect-agent:latest
        ports:
        - containerPort: 8008
        env:
        - name: DATABASE_URL
          valueFrom:
            configMapKeyRef:
              name: architect-config
              key: database_url
        - name: KAFKA_BOOTSTRAP_SERVERS
          value: "kafka.neural-hive.svc.cluster.local:9092"
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: openai-secret
              key: api-key
        resources:
          requests:
            cpu: 200m
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 512Mi
        livenessProbe:
          httpGet:
            path: /health
            port: 8008
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 8008
          initialDelaySeconds: 5
          periodSeconds: 10
```

- [ ] **Step 2: Criar Kubernetes service**

```yaml
# services/architect-agent/deployment/k8s-service.yaml

apiVersion: v1
kind: Service
metadata:
  name: architect-agent
  namespace: neural-hive-staging
spec:
  selector:
    app: architect-agent
  ports:
  - protocol: TCP
    port: 8008
    targetPort: 8008
  type: ClusterIP
```

- [ ] **Step 3: Deploy**

```bash
kubectl apply -f services/architect-agent/deployment/
```

- [ ] **Step 4: Verificar deploy**

```bash
kubectl rollout status deployment/architect-agent -n neural-hive-staging
```

Expected: `deployment "architect-agent" successfully rolled out`

- [ ] **Step 5: Commit**

```bash
git add services/architect-agent/deployment/
git commit -m "deploy(architect-agent): add Kubernetes manifests for staging"
```

---

## Task 15: Smoke test em staging

**Files:**
- None (manual test)

- [ ] **Step 1: Testar health endpoint**

```bash
curl https://architect-agent.staging.neural-hive.com/health
```

Expected: `{"status": "ok"}`

- [ ] **Step 2: Testar bounded contexts endpoint**

```bash
curl -X POST "https://architect-agent.staging.neural-hive.com/api/v1/architecture/identify-contexts" \
  -H "Content-Type: application/json" \
  -d '{
    "requirements": "Sistema de gestão de tarefas"
  }'
```

Expected: JSON com bounded contexts identificados

- [ ] **Step 3: Testar diagram generation endpoint**

```bash
curl -X POST "https://architect-agent.staging.neural-hive.com/api/v1/diagrams/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "User -> API -> Database",
    "diagram_type": "sequence"
  }'
```

Expected: JSON com mermaid_code

- [ ] **Step 4: Atualizar documento de release**

```markdown
# Release Notes - Architect Agent v0.2.0

## Novidades

✨ **Novo: Bounded Contexts Identification**
- Identificação automática de bounded contexts baseado em DDD
- Linguagem ubíqua extraída do domínio

✨ **Novo: Tech Stack Recommendation**
- Recomendação de stack tecnológico baseada em requisitos
- Base de conhecimento atualizada

✨ **Novo: Diagram Generation**
- Geração de diagramas C4 (Context, Container)
- Geração de diagramas de sequência
- Renderização para SVG via mermaid-cli

## Breaking Changes

Nenhuma

## Migration Guide

Nenhuma migração necessária. Extensões são aditivas.
```

---

## Conclusão da Fase 1

Após completar todos os tasks, o `architect-agent` estará extendido com:

1. ✅ BoundedContextsIdentifier - Identifica contextos DDD
2. ✅ TechStackRecommender - Recomenda stack técnico  
3. ✅ ArchitectureDiagramGenerator - Gera diagramas C4/Mermaid
4. ✅ Integração com DesignPlanner existente
5. ✅ Novos endpoints REST expostos
6. ✅ Testes unitários e integração
7. ✅ Documentação completa
8. ✅ CI/CD configurado
9. ✅ Deploy em staging testado

---

**ESTADO FINAL DA FASE 1:**
```
architect-agent (8008)
├── src/
│   ├── identifiers/
│   │   └── bounded_contexts.py ✅ NOVO
│   ├── recommenders/
│   │   ├── tech_stack.py ✅ NOVO
│   │   └── knowledge_base.py ✅ NOVO
│   ├── generators/
│   │   ├── diagram_generator.py ✅ NOVO
│   │   ├── c4_diagram.py ✅ NOVO
│   │   └── mermaid_renderer.py ✅ NOVO
│   ├── models/
│   │   ├── bounded_context.py ✅ NOVO
│   │   ├── tech_stack.py ✅ NOVO
│   │   └── diagrams.py ✅ NOVO
│   ├── services/
│   │   └── design_planner.py ✅ MODIFICADO
│   └── api/
│       └── routers/
│           └── architecture.py ✅ MODIFICADO
├── tests/
│   ├── unit/
│   │   ├── test_bounded_contexts.py ✅ NOVO
│   │   ├── test_tech_stack.py ✅ NOVO
│   │   └── test_diagram_generator.py ✅ NOVO
│   └── integration/
│       └── test_architecture_extended.py ✅ NOVO
└── docs/
    ├── BOUNDED_CONTEXTS.md ✅ NOVO
    ├── TECH_STACK_RECOMMENDATION.md ✅ NOVO
    └── DIAGRAM_GENERATION.md ✅ NOVO
```

**PRÓXIMA FASE:** Implementação de Requirements Engineering (8010) e Documentation Generation (8014).
