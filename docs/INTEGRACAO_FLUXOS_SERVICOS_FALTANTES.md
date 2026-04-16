# Integração e Fluxos dos Serviços Faltantes no NHM

> **Data:** 2026-04-15
> **Documento:** Arquitetura de Integração e Fluxos para Serviços Faltantes
> **Versão:** 1.0

---

## 📋 Sumário Executivo

Este documento define a arquitetura de integração e fluxos para os serviços faltantes no Neural-Hive-Mind (NHM), transformando-o de uma plataforma de orquestração de agentes para um sistema completo de criação automática de software do zero.

### Serviços Existentes (75-80% implementados)
- ✅ 8 serviços core com orquestração Kafka/Temporal
- ✅ 8 agentes especializados
- ✅ Code Forge com 4 métodos de geração
- ✅ MCP Tool Catalog com algoritmo genético
- ✅ Sistema de consenso Bayesian
- ✅ CI/CD Pipeline com 7 estágios
- ✅ Observabilidade completa
- ✅ Self-healing engine

### Serviços Faltantes (25-30% a implementar)
1. **Requirements Engineering System** (Fluxo G)
2. **Architectural Planning System**
3. **Agentic Delegation System**
4. **Test Generation System**
5. **Documentation Generation System**
6. **Refactoring & Modernization System**
7. **CI Feedback Loop (Reinforcement Learning)**
8. **Document Analysis & Legacy Migration System** (Fluxo H)
9. **Knowledge Graph Profundo (RAG)**

---

## 🌐 Visão Geral da Arquitetura de Integração

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        NEURAL-HIVE-MIND (ESTADO ATUAL)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   Gateway    │  │     STE      │  │   Consensus  │  │ Orchestrator │    │
│  │  Intenções   │→ │ Translation  │→ │    Engine    │→ │   Dynamic    │    │
│  │    (8000)    │  │    Engine    │  │    (8002)    │  │    (8003)    │    │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
│         ↓                 ↓                 ↓                 ↓              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   Queen      │  │   Workers    │  │   Approval  │  │ Code Forge   │    │
│  │    Agent     │  │    Agents    │  │   Service   │  │   (8005)     │    │
│  │   (8006)     │  │   (8005)     │  │   (8004)     │  │              │    │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                   SERVIÇOS FALTANTES (A IMPLEMENTAR)                         │
│                                                                             │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌───────────────────┐  │
│  │ Requirements Engine  │  │ Architectural Planner│  │ Test Generation   │  │
│  │      System          │  │       System         │  │      System       │  │
│  └──────────────────────┘  └──────────────────────┘  └───────────────────┘  │
│           ↓                         ↓                        ↓                │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌───────────────────┐  │
│  │ Documentation Gen    │  │ Refactoring & Modern │  │ CI Feedback Loop  │  │
│  │      System          │  │         System       │  │      System       │  │
│  └──────────────────────┘  └──────────────────────┘  └───────────────────┘  │
│           ↓                         ↓                        ↓                │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌───────────────────┐  │
│  │  Agentic Delegation  │  │ Knowledge Graph Deep│  │ Doc Analysis &    │  │
│  │      System          │  │       (RAG)          │  │ Legacy Migration   │  │
│  └──────────────────────┘  └──────────────────────┘  └───────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Fluxo G: Ideia → Software Completo

### Descrição Geral

Transforma uma ideia simples em linguagem natural em software completo, testado, documentado e deployado.

### Componentes do Fluxo G

| Componente | Porta | Status | Descrição |
|------------|-------|--------|-----------|
| Gateway de Intenções | 8000 | ✅ Existe | Captura e normaliza ideias |
| Semantic Translation Engine | 8001 | ✅ Existe | Gera planos cognitivos |
| Requirements Engineering System | 8010 | ❌ Faltante | Engenharia de requisitos |
| Architectural Planning System | 8011 | ❌ Faltante | Design arquitetural |
| Agentic Delegation System | 8012 | ❌ Faltante | Delegação de tarefas |
| Code Forge | 8005 | ✅ Existe | Geração de código/IaC |
| Test Generation System | 8013 | ❌ Faltante | Geração de testes |
| Documentation Generation System | 8014 | ❌ Faltante | Geração de documentação |
| Software Engineering Pipeline | Existente | ⚠️ Parcial | CI/CD orquestrado |
| CI Feedback Loop | 8015 | ❌ Faltante | Reinforcement learning |

---

### Passo 1: Usuário Submeter Ideia

**Endpoint:** `POST /api/v1/ideas`

**Payload:**
```json
{
  "idea": "Criar um app de delivery de comida",
  "context": {
    "target_market": "São Paulo",
    "budget": "medium",
    "timeline": "3 months",
    "team_size": 5
  }
}
```

**Response:**
```json
{
  "idea_id": "uuid-v4",
  "status": "received",
  "estimated_duration": "2-3 hours"
}
```

**Fluxo:**
```
Usuário → Gateway de Intenções (8000)
  → Evento Kafka: `intentions.raw`
  → NLU Processing (ASR, NLU Classification, PII Masking, Translation)
  → Evento Kafka: `intentions.high-confidence`
```

---

### Passo 2: Semantic Translation Engine

**Consumir:** `intentions.high-confidence`

**Processar:**
1. **Intent Decomposition** - `/src/services/decomposition_templates.py`
   - Quebrar ideia em subtarefas cognitivas
   - Gerar: `CognitivePlan` com tasks

2. **Enrichment via Neo4j**
   - Query knowledge graph para contexto de domínio
   - Adicionar: `domain_patterns`, `similar_projects`

**Produzir:** `plans.cognitive`

**Payload:**
```json
{
  "id": "uuid-v4",
  "plan": {
    "tasks": [
      {
        "id": "task_1",
        "type": "requirements_engineering",
        "priority": "high",
        "dependencies": []
      },
      {
        "id": "task_2",
        "type": "architectural_design",
        "priority": "high",
        "dependencies": ["task_1"]
      },
      {
        "id": "task_3",
        "type": "data_model_design",
        "priority": "high",
        "dependencies": ["task_1"]
      },
      {
        "id": "task_4",
        "type": "code_generation",
        "priority": "medium",
        "dependencies": ["task_2", "task_3"]
      },
      {
        "id": "task_5",
        "type": "test_generation",
        "priority": "medium",
        "dependencies": ["task_4"]
      },
      {
        "id": "task_6",
        "type": "documentation_generation",
        "priority": "medium",
        "dependencies": ["task_4", "task_5"]
      }
    ]
  }
}
```

---

### Passo 3: Requirements Engineering System (NOVO - 8010)

**Consumir:** `plans.cognitive` (filtro: `task.type == "requirements_engineering"`)

**Portas:**
- API REST: `8010`
- Health Check: `/health`
- Metrics: `/metrics`

**Componentes Internos:**

#### 3.1 Requirements Engineer

**Responsabilidade:** Analisar ideia original + contexto e gerar requisitos funcionais completos.

**Input:**
- Idea original (do Gateway)
- Context (do usuário)
- Cognitive Plan (do STE)

**Processamento:**
```python
# services/requirements-engineering/src/services/requirements_engineer.py

class RequirementsEngineer:
    async def generate_requirements(self, idea: str, context: dict, plan: dict) -> List[Requirement]:
        """
        Gera requisitos funcionais completos a partir de uma ideia.

        Processo:
        1. Analisar ideia com NLP (spaCy, transformers)
        2. Extrair: funcionalidades principais
        3. Extrair: não-funcionais (performance, segurança, escalabilidade)
        4. Extrair: constraints (budget, timeline, team)
        5. Consultar Knowledge Graph (RAG) para similar_projects
        6. Gerar: requisitos estruturados
        7. Prioritizar: MoSCoW (Must, Should, Could, Won't)
        8. Validar: consistency e completeness

        Output: List[Requirement]
        """
        # Análise NLP
        entities = await self._extract_entities(idea)
        functionalities = await self._extract_functionalities(entities)
        non_functionals = await self._extract_non_functionals(context)
        constraints = await self._extract_constraints(context)

        # RAG Query
        similar_projects = await self.knowledge_graph.search_similar_projects(
            domain=entities['domain'],
            functionalities=functionalities
        )

        # Gerar requisitos
        requirements = await self._generate_requirements(
            functionalities=functionalities,
            non_functionals=non_functionals,
            constraints=constraints,
            similar_projects=similar_projects
        )

        # Prioritização MoSCoW
        prioritized = await self._prioritize_moscow(requirements, context)

        # Validação
        validated = await self._validate_requirements(prioritized)

        return validated
```

**Output:**
```json
{
  "requirements": [
    {
      "id": "req_1",
      "title": "Cadastro de usuários",
      "description": "Sistema deve permitir cadastro de usuários com email e senha",
      "type": "functional",
      "priority": "must",
      "acceptance_criteria": [
        "Usuário deve conseguir se cadastrar com email válido",
        "Sistema deve validar formato de email",
        "Senha deve ter mínimo 8 caracteres"
      ],
      "business_rules": [
        "Email deve ser único",
        "Senha deve ser hasheada com bcrypt",
        "Usuário deve confirmar email"
      ],
      "dependencies": [],
      "estimated_complexity": "medium"
    },
    {
      "id": "req_2",
      "title": "Login de usuários",
      "description": "Sistema deve permitir login com email e senha",
      "type": "functional",
      "priority": "must",
      "acceptance_criteria": [
        "Usuário deve conseguir fazer login com credenciais válidas",
        "Sistema deve autenticar corretamente",
        "Sessão deve expirar após inatividade"
      ],
      "business_rules": [
        "Tentativas falhas devem ser limitadas (3 tentativas)",
        "Sessão deve durar 24h",
        "Token JWT deve ser usado"
      ],
      "dependencies": ["req_1"],
      "estimated_complexity": "medium"
    },
    {
      "id": "req_3",
      "title": "Listagem de restaurantes",
      "description": "Sistema deve exibir lista de restaurantes disponíveis",
      "type": "functional",
      "priority": "must",
      "acceptance_criteria": [
        "Usuário deve ver restaurantes na sua região",
        "Lista deve ser paginada (10 por página)",
        "Filtros por tipo de cozinha devem funcionar"
      ],
      "business_rules": [],
      "dependencies": [],
      "estimated_complexity": "low"
    }
  ]
}
```

---

#### 3.2 User Story Generator

**Responsabilidade:** Gerar user stories com acceptance criteria.

**Processamento:**
```python
# services/requirements-engineering/src/services/user_story_generator.py

class UserStoryGenerator:
    async def generate_user_stories(self, requirements: List[Requirement]) -> List[UserStory]:
        """
        Gera user stories a partir de requisitos funcionais.

        Formato padrão:
        "Como um [role], quero [feature], para que [benefit]"

        Para cada user story:
        - Gerar acceptance criteria
        - Gerar Cucumber scenarios (Given-When-Then)
        - Estimar story points
        - Definir priority (Must, Should, Could, Won't)
        """
        user_stories = []

        for req in requirements:
            if req['type'] == 'functional':
                # Identificar role
                role = await self._identify_role(req)

                # Identificar feature
                feature = req['title']

                # Identificar benefit
                benefit = await self._identify_benefit(req)

                # Gerar user story
                user_story = {
                    "id": f"us_{req['id']}",
                    "role": role,
                    "feature": feature,
                    "benefit": benefit,
                    "narrative": f"Como um {role}, quero {feature.lower()}, para que {benefit.lower()}",
                    "acceptance_criteria": req['acceptance_criteria'],
                    "cucumber_scenarios": await self._generate_cucumber_scenarios(req),
                    "story_points": await self._estimate_story_points(req),
                    "priority": req['priority'],
                    "dependencies": req['dependencies']
                }

                user_stories.append(user_story)

        return user_stories
```

**Output:**
```json
{
  "user_stories": [
    {
      "id": "us_req_1",
      "role": "Usuário",
      "feature": "Cadastro de usuários",
      "benefit": "posso criar uma conta no sistema",
      "narrative": "Como um Usuário, quero cadastrar de usuários, para que possa criar uma conta no sistema",
      "acceptance_criteria": [
        "Usuário deve conseguir se cadastrar com email válido",
        "Sistema deve validar formato de email",
        "Senha deve ter mínimo 8 caracteres"
      ],
      "cucumber_scenarios": [
        {
          "name": "Cadastro com sucesso",
          "steps": [
            "Given que estou na página de cadastro",
            "When preencho email válido 'test@example.com'",
            "And preencho senha 'password123'",
            "And clico no botão 'Cadastrar'",
            "Then devo ver mensagem 'Cadastro realizado com sucesso'",
            "And devo ser redirecionado para página de login"
          ]
        },
        {
          "name": "Cadastro com email inválido",
          "steps": [
            "Given que estou na página de cadastro",
            "When preencho email inválido 'invalid'",
            "And preencho senha 'password123'",
            "And clico no botão 'Cadastrar'",
            "Then devo ver erro 'Email inválido'",
            "And não devo ser redirecionado"
          ]
        }
      ],
      "story_points": 3,
      "priority": "must",
      "dependencies": []
    }
  ]
}
```

---

#### 3.3 Acceptance Criteria Generator

**Responsabilidade:** Gerar critérios de aceitação testáveis e success metrics.

**Processamento:**
```python
# services/requirements-engineering/src/services/acceptance_criteria_generator.py

class AcceptanceCriteriaGenerator:
    async def generate_acceptance_criteria(self, user_stories: List[UserStory]) -> List[AcceptanceCriteria]:
        """
        Gera acceptance criteria detalhados e testáveis.

        Para cada user story:
        - Gerar acceptance criteria específicos
        - Definir success metrics (KPIs)
        - Definir test scenarios
        - Definir performance thresholds
        """
        acceptance_criteria = []

        for us in user_stories:
            # Gerar acceptance criteria específicos
            criteria = await self._generate_criteria(us)

            # Definir success metrics
            metrics = await self._define_success_metrics(us)

            # Definir test scenarios
            test_scenarios = await self._define_test_scenarios(us)

            # Definir performance thresholds
            performance_thresholds = await self._define_performance_thresholds(us)

            acceptance_criteria.append({
                "user_story_id": us['id'],
                "criteria": criteria,
                "success_metrics": metrics,
                "test_scenarios": test_scenarios,
                "performance_thresholds": performance_thresholds
            })

        return acceptance_criteria
```

**Output:**
```json
{
  "acceptance_criteria": [
    {
      "user_story_id": "us_req_1",
      "criteria": [
        "CA-1: Sistema deve validar formato de email (regex)",
        "CA-2: Sistema deve validar tamanho mínimo da senha (8 caracteres)",
        "CA-3: Sistema deve hashear senha com bcrypt antes de salvar",
        "CA-4: Sistema deve enviar email de confirmação após cadastro",
        "CA-5: Sistema deve bloquear cadastro com email duplicado"
      ],
      "success_metrics": [
        { "name": "Taxa de conversão de cadastro", "target": "> 70%" },
        { "name": "Tempo de cadastro", "target": "< 5 segundos" },
        { "name": "Taxa de erro de validação", "target": "< 5%" }
      ],
      "test_scenarios": [
        { "name": "Happy path - cadastro com dados válidos" },
        { "name": "Sad path - email inválido" },
        { "name": "Sad path - senha curta" },
        { "name": "Edge case - email duplicado" },
        { "name": "Edge case - email já existe no banco" }
      ],
      "performance_thresholds": {
        "response_time_p95": "< 2s",
        "concurrent_users": "1000 req/s",
        "database_query_time": "< 100ms"
      }
    }
  ]
}
```

---

#### 3.4 Data Model Designer

**Responsabilidade:** Gerar data models, ER diagrams e database schemas.

**Processamento:**
```python
# services/requirements-engineering/src/services/data_model_designer.py

class DataModelDesigner:
    async def design_data_models(self, requirements: List[Requirement]) -> DataModel:
        """
        Gera data models completos.

        Processo:
        1. Extrair entidades de requisitos
        2. Identificar relacionamentos (one-to-one, one-to-many, many-to-many)
        3. Designar attributes (primary keys, foreign keys, indexes)
        4. Aplicar normalização (3NF)
        5. Gerar ER diagrams
        6. Gerar database schemas (SQL/NoSQL)
        7. Designar constraints (unique, not null, foreign key)
        8. Gerar migration scripts
        """
        # Extrair entidades
        entities = await self._extract_entities(requirements)

        # Identificar relacionamentos
        relationships = await self._identify_relationships(requirements, entities)

        # Designar attributes
        attributes = await self._design_attributes(entities, requirements)

        # Normalização
        normalized = await self._normalize_data_model(entities, attributes)

        # Gerar ER diagrams
        er_diagram = await self._generate_er_diagram(normalized, relationships)

        # Gerar database schemas
        sql_schema = await self._generate_sql_schema(normalized)
        nosql_schema = await self._generate_nosql_schema(normalized)

        # Gerar migration scripts
        migration_scripts = await self._generate_migration_scripts(sql_schema)

        return {
            "entities": normalized,
            "relationships": relationships,
            "er_diagram": er_diagram,
            "sql_schema": sql_schema,
            "nosql_schema": nosql_schema,
            "migration_scripts": migration_scripts
        }
```

**Output:**
```json
{
  "entities": [
    {
      "name": "User",
      "attributes": [
        { "name": "id", "type": "UUID", "primary_key": true },
        { "name": "email", "type": "VARCHAR(255)", "unique": true, "not_null": true },
        { "name": "password_hash", "type": "VARCHAR(255)", "not_null": true },
        { "name": "name", "type": "VARCHAR(255)", "not_null": true },
        { "name": "created_at", "type": "TIMESTAMP", "default": "NOW()" },
        { "name": "updated_at", "type": "TIMESTAMP", "default": "NOW()" }
      ],
      "indexes": [
        { "name": "idx_user_email", "columns": ["email"] }
      ],
      "constraints": [
        { "name": "uk_user_email", "type": "UNIQUE", "columns": ["email"] }
      ]
    },
    {
      "name": "Restaurant",
      "attributes": [
        { "name": "id", "type": "UUID", "primary_key": true },
        { "name": "name", "type": "VARCHAR(255)", "not_null": true },
        { "name": "cuisine_type", "type": "VARCHAR(100)" },
        { "name": "address", "type": "TEXT" },
        { "name": "rating", "type": "DECIMAL(3,2)", "min": 0, "max": 5 },
        { "name": "is_active", "type": "BOOLEAN", "default": true }
      ],
      "indexes": [
        { "name": "idx_restaurant_cuisine", "columns": ["cuisine_type"] },
        { "name": "idx_restaurant_active", "columns": ["is_active"] }
      ]
    }
  ],
  "relationships": [
    {
      "from": "User",
      "to": "Order",
      "type": "one-to-many",
      "foreign_key": { "table": "Order", "column": "user_id" }
    },
    {
      "from": "Restaurant",
      "to": "Order",
      "type": "one-to-many",
      "foreign_key": { "table": "Order", "column": "restaurant_id" }
    }
  ],
  "er_diagram": {
    "format": "mermaid",
    "content": "erDiagram\n    User ||--o{ Order : places\n    Restaurant ||--o{ Order : receives\n    User {\n        UUID id PK\n        VARCHAR email UK\n        VARCHAR password_hash\n        VARCHAR name\n        TIMESTAMP created_at\n        TIMESTAMP updated_at\n    }\n    Restaurant {\n        UUID id PK\n        VARCHAR name\n        VARCHAR cuisine_type\n        TEXT address\n        DECIMAL rating\n        BOOLEAN is_active\n    }\n    Order {\n        UUID id PK\n        UUID user_id FK\n        UUID restaurant_id FK\n        DECIMAL total\n        VARCHAR status\n        TIMESTAMP created_at\n    }"
  },
  "sql_schema": {
    "postgresql": "-- Users Table\nCREATE TABLE users (\n    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n    email VARCHAR(255) UNIQUE NOT NULL,\n    password_hash VARCHAR(255) NOT NULL,\n    name VARCHAR(255) NOT NULL,\n    created_at TIMESTAMP DEFAULT NOW(),\n    updated_at TIMESTAMP DEFAULT NOW()\n);\n\n-- Restaurants Table\nCREATE TABLE restaurants (\n    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n    name VARCHAR(255) NOT NULL,\n    cuisine_type VARCHAR(100),\n    address TEXT,\n    rating DECIMAL(3,2) CHECK (rating >= 0 AND rating <= 5),\n    is_active BOOLEAN DEFAULT true\n);\n\n-- Orders Table\nCREATE TABLE orders (\n    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n    user_id UUID REFERENCES users(id) ON DELETE CASCADE,\n    restaurant_id UUID REFERENCES restaurants(id) ON DELETE CASCADE,\n    total DECIMAL(10,2) NOT NULL,\n    status VARCHAR(50) NOT NULL,\n    created_at TIMESTAMP DEFAULT NOW()\n);\n\n-- Indexes\nCREATE INDEX idx_users_email ON users(email);\nCREATE INDEX idx_restaurants_cuisine ON restaurants(cuisine_type);\nCREATE INDEX idx_orders_user_id ON orders(user_id);\nCREATE INDEX idx_orders_restaurant_id ON orders(restaurant_id);"
  },
  "nosql_schema": {
    "mongodb": "{\n  \"collections\": {\n    \"users\": {\n      \"validator\": {\n        \"$jsonSchema\": {\n          \"bsonType\": \"object\",\n          \"required\": [\"email\", \"password_hash\", \"name\"],\n          \"properties\": {\n            \"_id\": { \"bsonType\": \"objectId\" },\n            \"email\": { \"bsonType\": \"string\" },\n            \"password_hash\": { \"bsonType\": \"string\" },\n            \"name\": { \"bsonType\": \"string\" },\n            \"created_at\": { \"bsonType\": \"date\" },\n            \"updated_at\": { \"bsonType\": \"date\" }\n          }\n        }\n      },\n      \"indexes\": [\n        { \"keys\": { \"email\": 1 }, \"unique\": true }\n      ]\n    }\n  }\n}"
  },
  "migration_scripts": [
    {
      "version": "001_initial_schema",
      "up": "-- Migration 001: Initial Schema\nBEGIN;\n\n-- Users Table\nCREATE TABLE users (\n    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n    email VARCHAR(255) UNIQUE NOT NULL,\n    password_hash VARCHAR(255) NOT NULL,\n    name VARCHAR(255) NOT NULL,\n    created_at TIMESTAMP DEFAULT NOW(),\n    updated_at TIMESTAMP DEFAULT NOW()\n);\n\n-- Restaurants Table\nCREATE TABLE restaurants (\n    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n    name VARCHAR(255) NOT NULL,\n    cuisine_type VARCHAR(100),\n    address TEXT,\n    rating DECIMAL(3,2) CHECK (rating >= 0 AND rating <= 5),\n    is_active BOOLEAN DEFAULT true\n);\n\n-- Orders Table\nCREATE TABLE orders (\n    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n    user_id UUID REFERENCES users(id) ON DELETE CASCADE,\n    restaurant_id UUID REFERENCES restaurants(id) ON DELETE CASCADE,\n    total DECIMAL(10,2) NOT NULL,\n    status VARCHAR(50) NOT NULL,\n    created_at TIMESTAMP DEFAULT NOW()\n);\n\n-- Indexes\nCREATE INDEX idx_users_email ON users(email);\nCREATE INDEX idx_restaurants_cuisine ON restaurants(cuisine_type);\nCREATE INDEX idx_orders_user_id ON orders(user_id);\nCREATE INDEX idx_orders_restaurant_id ON orders(restaurant_id);\n\nCOMMIT;",
      "down": "-- Rollback Migration 001\nBEGIN;\n\nDROP INDEX IF EXISTS idx_orders_restaurant_id;\nDROP INDEX IF EXISTS idx_orders_user_id;\nDROP INDEX IF EXISTS idx_restaurants_cuisine;\nDROP INDEX IF EXISTS idx_users_email;\n\nDROP TABLE IF EXISTS orders;\nDROP TABLE IF EXISTS restaurants;\nDROP TABLE IF EXISTS users;\n\nCOMMIT;"
    }
  ]
}
```

---

#### 3.5 API Designer

**Responsabilidade:** Gerar API design, OpenAPI/Swagger specs e API versioning strategy.

**Processamento:**
```python
# services/requirements-engineering/src/services/api_designer.py

class APIDesigner:
    async def design_api(self, requirements: List[Requirement], data_models: DataModel) -> APIDesign:
        """
        Gera API design completo.

        Processo:
        1. Identificar endpoints necessários
        2. Definir HTTP methods (GET, POST, PUT, DELETE, PATCH)
        3. Definir request/response schemas
        4. Gerar OpenAPI/Swagger spec
        5. Definir authentication/authorization strategy
        6. Definir API versioning strategy
        7. Definir rate limiting
        8. Definir error handling
        """
        # Identificar endpoints
        endpoints = await self._identify_endpoints(requirements)

        # Definir HTTP methods
        http_methods = await self._define_http_methods(endpoints)

        # Definir request/response schemas
        schemas = await self._define_schemas(endpoints, data_models)

        # Gerar OpenAPI spec
        openapi_spec = await self._generate_openapi_spec(endpoints, http_methods, schemas)

        # Definir auth strategy
        auth_strategy = await self._define_auth_strategy(requirements)

        # Definir versioning strategy
        versioning_strategy = await self._define_versioning_strategy()

        # Definir rate limiting
        rate_limiting = await self._define_rate_limiting()

        # Definir error handling
        error_handling = await self._define_error_handling()

        return {
            "endpoints": endpoints,
            "openapi_spec": openapi_spec,
            "auth_strategy": auth_strategy,
            "versioning_strategy": versioning_strategy,
            "rate_limiting": rate_limiting,
            "error_handling": error_handling
        }
```

**Output:**
```json
{
  "endpoints": [
    {
      "path": "/api/v1/users",
      "method": "POST",
      "description": "Cria um novo usuário",
      "tags": ["users"],
      "request_body": {
        "schema": {
          "type": "object",
          "properties": {
            "email": { "type": "string", "format": "email" },
            "password": { "type": "string", "minLength": 8 },
            "name": { "type": "string", "minLength": 2 }
          },
          "required": ["email", "password", "name"]
        }
      },
      "response": {
        "201": {
          "description": "Usuário criado com sucesso",
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "id": { "type": "string", "format": "uuid" },
                  "email": { "type": "string", "format": "email" },
                  "name": { "type": "string" },
                  "created_at": { "type": "string", "format": "date-time" }
                }
              }
            }
          }
        },
        "400": {
          "description": "Dados inválidos",
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "error": { "type": "string" },
                  "details": { "type": "object" }
                }
              }
            }
          }
        }
      },
      "security": [{"ApiKeyAuth": []}]
    },
    {
      "path": "/api/v1/users/{user_id}",
      "method": "GET",
      "description": "Busca um usuário por ID",
      "tags": ["users"],
      "parameters": [
        {
          "name": "user_id",
          "in": "path",
          "required": true,
          "schema": { "type": "string", "format": "uuid" }
        }
      ],
      "response": {
        "200": {
          "description": "Usuário encontrado",
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "id": { "type": "string", "format": "uuid" },
                  "email": { "type": "string", "format": "email" },
                  "name": { "type": "string" },
                  "created_at": { "type": "string", "format": "date-time" }
                }
              }
            }
          }
        },
        "404": {
          "description": "Usuário não encontrado"
        }
      },
      "security": [{"ApiKeyAuth": []}]
    }
  ],
  "openapi_spec": {
    "openapi": "3.0.0",
    "info": {
      "title": "Delivery App API",
      "version": "1.0.0",
      "description": "API para aplicativo de delivery de comida"
    },
    "servers": [
      { "url": "https://api.deliveryapp.com/v1", "description": "Production" },
      { "url": "https://staging-api.deliveryapp.com/v1", "description": "Staging" }
    ],
    "paths": {
      "/users": {
        "post": {
          "tags": ["users"],
          "summary": "Cria um novo usuário",
          "requestBody": {
            "required": true,
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/CreateUserRequest"
                }
              }
            }
          },
          "responses": {
            "201": {
              "description": "Usuário criado com sucesso",
              "content": {
                "application/json": {
                  "schema": { "$ref": "#/components/schemas/User" }
                }
              }
            },
            "400": {
              "description": "Dados inválidos",
              "content": {
                "application/json": {
                  "schema": { "$ref": "#/components/schemas/Error" }
                }
              }
            }
          },
          "security": [{"ApiKeyAuth": []}]
        }
      },
      "/users/{user_id}": {
        "get": {
          "tags": ["users"],
          "summary": "Busca um usuário por ID",
          "parameters": [
            {
              "name": "user_id",
              "in": "path",
              "required": true,
              "schema": { "type": "string", "format": "uuid" }
            }
          ],
          "responses": {
            "200": {
              "description": "Usuário encontrado",
              "content": {
                "application/json": {
                  "schema": { "$ref": "#/components/schemas/User" }
                }
              }
            },
            "404": {
              "description": "Usuário não encontrado"
            }
          },
          "security": [{"ApiKeyAuth": []}]
        }
      }
    },
    "components": {
      "securitySchemes": {
        "ApiKeyAuth": {
          "type": "apiKey",
          "in": "header",
          "name": "X-API-Key"
        },
        "BearerAuth": {
          "type": "http",
          "scheme": "bearer",
          "bearerFormat": "JWT"
        }
      },
      "schemas": {
        "CreateUserRequest": {
          "type": "object",
          "required": ["email", "password", "name"],
          "properties": {
            "email": { "type": "string", "format": "email" },
            "password": { "type": "string", "minLength": 8 },
            "name": { "type": "string", "minLength": 2 }
          }
        },
        "User": {
          "type": "object",
          "properties": {
            "id": { "type": "string", "format": "uuid" },
            "email": { "type": "string", "format": "email" },
            "name": { "type": "string" },
            "created_at": { "type": "string", "format": "date-time" }
          }
        },
        "Error": {
          "type": "object",
          "properties": {
            "error": { "type": "string" },
            "details": { "type": "object" }
          }
        }
      }
    }
  },
  "auth_strategy": {
    "type": "JWT",
    "description": "Autenticação via JWT Bearer tokens",
    "token_expiry": "24h",
    "refresh_token_expiry": "7d"
  },
  "versioning_strategy": {
    "type": "URI versioning",
    "description": "Versionamento via URL path (/api/v1/, /api/v2/)",
    "current_version": "v1",
    "supported_versions": ["v1"]
  },
  "rate_limiting": {
    "default_limit": "1000 requests/hour",
    "authenticated_limit": "10000 requests/hour",
    "endpoint_limits": {
      "POST /api/v1/users": "10 requests/minute",
      "POST /api/v1/auth/login": "5 requests/minute"
    }
  },
  "error_handling": {
    "standard_errors": {
      "400": "Bad Request - Dados inválidos",
      "401": "Unauthorized - Autenticação necessária",
      "403": "Forbidden - Permissão insuficiente",
      "404": "Not Found - Recurso não encontrado",
      "409": "Conflict - Recurso já existe",
      "429": "Too Many Requests - Rate limit excedido",
      "500": "Internal Server Error - Erro no servidor",
      "503": "Service Unavailable - Serviço indisponível"
    },
    "error_response_format": {
      "error": "string",
      "message": "string",
      "details": "object",
      "request_id": "string",
      "timestamp": "datetime"
    }
  }
}
```

---

#### 3.6 UI/UX Designer

**Responsabilidade:** Gerar wireframes, mockups, component libraries e user journey maps.

**Processamento:**
```python
# services/requirements-engineering/src/services/ui_ux_designer.py

class UIUXDesigner:
    async def design_ui_ux(self, requirements: List[Requirement], user_stories: List[UserStory]) -> UIUXDesign:
        """
        Gera UI/UX design completo.

        Processo:
        1. Identificar personas de usuário
        2. Gerar user journey maps
        3. Gerar wireframes e mockups
        4. Designar component library
        5. Definir design system
        6. Definir accessibility guidelines
        """
        # Identificar personas
        personas = await self._identify_personas(user_stories)

        # Gerar user journey maps
        user_journeys = await self._generate_user_journeys(personas, user_stories)

        # Gerar wireframes
        wireframes = await self._generate_wireframes(requirements, user_stories)

        # Gerar mockups
        mockups = await self._generate_mockups(wireframes)

        # Designar component library
        component_library = await self._design_component_library()

        # Definir design system
        design_system = await self._define_design_system()

        # Definir accessibility guidelines
        accessibility_guidelines = await self._define_accessibility_guidelines()

        return {
            "personas": personas,
            "user_journeys": user_journeys,
            "wireframes": wireframes,
            "mockups": mockups,
            "component_library": component_library,
            "design_system": design_system,
            "accessibility_guidelines": accessibility_guidelines
        }
```

**Output:**
```json
{
  "personas": [
    {
      "id": "persona_1",
      "name": "Cliente Hungry",
      "description": "Usuário que pede comida delivery",
      "demographics": {
        "age": "25-40",
        "location": "São Paulo",
        "tech_savviness": "high"
      },
      "goals": [
        "Pedir comida rápida e fácil",
        "Encontrar restaurantes na minha região",
        "Ver status do pedido em tempo real"
      ],
      "pain_points": [
        "Apps lentos",
        "Falta de opções",
        "Status do pedido não atualiza"
      ],
      "behaviors": [
        "Usa app no celular",
        "Prefere pagamentos digitais",
        "Lê reviews antes de pedir"
      ]
    }
  ],
  "user_journeys": [
    {
      "persona_id": "persona_1",
      "title": "Primeiro Pedido",
      "steps": [
        {
          "step": 1,
          "action": "Abrir app",
          "screen": "Home Screen",
          "touchpoints": ["Mobile App"],
          "emotions": ["excited"],
          "opportunities": ["Personalização baseada em localização"]
        },
        {
          "step": 2,
          "action": "Buscar restaurantes",
          "screen": "Search/Filter Screen",
          "touchpoints": ["Mobile App", "Backend API"],
          "emotions": ["hopeful"],
          "opportunities": ["Filtros inteligentes por preferências"]
        },
        {
          "step": 3,
          "action": "Selecionar restaurante",
          "screen": "Restaurant Details Screen",
          "touchpoints": ["Mobile App", "Backend API"],
          "emotions": ["curious"],
          "opportunities": ["Recomendações similares"]
        },
        {
          "step": 4,
          "action": "Fazer pedido",
          "screen": "Cart/Checkout Screen",
          "touchpoints": ["Mobile App", "Payment Gateway"],
          "emotions": ["focused"],
          "opportunities": ["Pagamento one-click", "Sugestões de itens populares"]
        },
        {
          "step": 5,
          "action": "Acompanhar pedido",
          "screen": "Order Tracking Screen",
          "touchpoints": ["Mobile App", "WebSocket", "Push Notifications"],
          "emotions": ["anxious", "excited"],
          "opportunities": ["Atualizações em tempo real", "Tempo estimado preciso"]
        },
        {
          "step": 6,
          "action": "Receber pedido",
          "screen": "Order Completed Screen",
          "touchpoints": ["Mobile App", "Delivery Person"],
          "emotions": ["satisfied"],
          "opportunities": ["Solicitação de review", "Recomendações futuras"]
        }
      ]
    }
  ],
  "wireframes": [
    {
      "id": "wf_1",
      "name": "Login Screen",
      "description": "Tela de login do app",
      "format": "image/png",
      "url": "/wireframes/login_screen.png",
      "components": [
        { "type": "logo", "x": 50, "y": 50, "width": 100, "height": 100 },
        { "type": "input", "x": 50, "y": 200, "width": 300, "height": 40, "placeholder": "Email" },
        { "type": "input", "x": 50, "y": 260, "width": 300, "height": 40, "placeholder": "Senha", "is_password": true },
        { "type": "button", "x": 50, "y": 320, "width": 300, "height": 50, "text": "Entrar" },
        { "type": "link", "x": 200, "y": 380, "text": "Esqueci minha senha" },
        { "type": "link", "x": 50, "y": 380, "text": "Criar conta" }
      ]
    },
    {
      "id": "wf_2",
      "name": "Home Screen",
      "description": "Tela inicial do app",
      "format": "image/png",
      "url": "/wireframes/home_screen.png",
      "components": [
        { "type": "search_bar", "x": 20, "y": 20, "width": 360, "height": 40, "placeholder": "Buscar restaurantes..." },
        { "type": "category_list", "x": 20, "y": 80, "width": 360, "height": 100, "categories": ["Italiana", "Brasileira", "Japonesa", "Chinesa", "Hamburgueria", "Pizza"] },
        { "type": "restaurant_list", "x": 20, "y": 200, "width": 360, "height": 400, "restaurants": [...] }
      ]
    },
    {
      "id": "wf_3",
      "name": "Restaurant Details Screen",
      "description": "Tela de detalhes do restaurante",
      "format": "image/png",
      "url": "/wireframes/restaurant_details_screen.png",
      "components": [
        { "type": "image", "x": 0, "y": 0, "width": 400, "height": 200 },
        { "type": "text", "x": 20, "y": 220, "text": "Restaurante Exemplo", "font_size": 24, "font_weight": "bold" },
        { "type": "rating", "x": 20, "y": 260, "value": 4.5 },
        { "type": "button", "x": 300, "y": 250, "width": 80, "height": 30, "text": "Favoritar" },
        { "type": "menu_list", "x": 20, "y": 300, "width": 360, "height": 300, "items": [...] },
        { "type": "floating_button", "x": 320, "y": 580, "width": 60, "height": 60, "icon": "cart" }
      ]
    }
  ],
  "mockups": [
    {
      "id": "mockup_1",
      "wireframe_id": "wf_1",
      "name": "Login Screen Mockup",
      "description": "Mockup high-fidelity da tela de login",
      "format": "image/png",
      "url": "/mockups/login_screen_mockup.png",
      "colors": {
        "primary": "#FF6B6B",
        "secondary": "#4ECDC4",
        "background": "#FFFFFF",
        "text": "#333333"
      },
      "fonts": {
        "header": "Roboto Bold",
        "body": "Roboto Regular"
      }
    }
  ],
  "component_library": [
    {
      "id": "btn_primary",
      "name": "Primary Button",
      "description": "Botão primário com cor de destaque",
      "props": {
        "text": "string",
        "onPress": "function",
        "disabled": "boolean"
      },
      "variants": {
        "default": { "background_color": "#FF6B6B", "text_color": "#FFFFFF" },
        "disabled": { "background_color": "#CCCCCC", "text_color": "#666666" }
      }
    },
    {
      "id": "input_text",
      "name": "Text Input",
      "description": "Campo de entrada de texto",
      "props": {
        "placeholder": "string",
        "value": "string",
        "onChange": "function",
        "isPassword": "boolean"
      },
      "variants": {
        "default": { "border_color": "#E0E0E0", "text_color": "#333333" },
        "error": { "border_color": "#FF0000", "text_color": "#333333" }
      }
    },
    {
      "id": "card_restaurant",
      "name": "Restaurant Card",
      "description": "Card de restaurante",
      "props": {
        "restaurant": "object",
        "onPress": "function"
      }
    }
  ],
  "design_system": {
    "colors": {
      "primary": {
        "50": "#FFF5F5",
        "100": "#FFE0E0",
        "200": "#FFB3B3",
        "300": "#FF8080",
        "400": "#FF4D4D",
        "500": "#FF1A1A",
        "600": "#FF0000",
        "700": "#CC0000",
        "800": "#990000",
        "900": "#660000"
      },
      "secondary": {
        "50": "#F0FDFA",
        "100": "#CCFBF1",
        "200": "#99F6E4",
        "300": "#5EEAD4",
        "400": "#2DD4BF",
        "500": "#14B8A6",
        "600": "#0D9488",
        "700": "#0F766E",
        "800": "#115E59",
        "900": "#134E4A"
      },
      "neutral": {
        "50": "#FAFAFA",
        "100": "#F5F5F5",
        "200": "#E5E5E5",
        "300": "#D4D4D4",
        "400": "#A3A3A3",
        "500": "#737373",
        "600": "#525252",
        "700": "#404040",
        "800": "#262626",
        "900": "#171717"
      }
    },
    "typography": {
      "font_family": "Roboto, sans-serif",
      "font_sizes": {
        "xs": "0.75rem",    // 12px
        "sm": "0.875rem",   // 14px
        "base": "1rem",     // 16px
        "lg": "1.125rem",   // 18px
        "xl": "1.25rem",    // 20px
        "2xl": "1.5rem",    // 24px
        "3xl": "1.875rem",  // 30px
        "4xl": "2.25rem",   // 36px
        "5xl": "3rem"       // 48px
      },
      "font_weights": {
        "light": 300,
        "regular": 400,
        "medium": 500,
        "semibold": 600,
        "bold": 700,
        "extrabold": 800
      }
    },
    "spacing": {
      "0": "0",
      "1": "0.25rem",   // 4px
      "2": "0.5rem",    // 8px
      "3": "0.75rem",   // 12px
      "4": "1rem",      // 16px
      "5": "1.25rem",   // 20px
      "6": "1.5rem",    // 24px
      "8": "2rem",      // 32px
      "10": "2.5rem",   // 40px
      "12": "3rem",     // 48px
      "16": "4rem",     // 64px
      "20": "5rem"      // 80px
    },
    "border_radius": {
      "none": "0",
      "sm": "0.125rem",  // 2px
      "md": "0.375rem",  // 6px
      "lg": "0.5rem",    // 8px
      "xl": "0.75rem",   // 12px
      "2xl": "1rem",     // 16px
      "3xl": "1.5rem",   // 24px
      "full": "9999px"
    },
    "shadows": {
      "sm": "0 1px 2px 0 rgba(0, 0, 0, 0.05)",
      "md": "0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)",
      "lg": "0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)",
      "xl": "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
      "2xl": "0 25px 50px -12px rgba(0, 0, 0, 0.25)"
    }
  },
  "accessibility_guidelines": {
    "wcag_level": "AA",
    "color_contrast": {
      "minimum_ratio": 4.5,
      "large_text_ratio": 3.0
    },
    "focus_indicators": {
      "enabled": true,
      "style": "outline: 2px solid #4ECDC4; outline-offset: 2px;"
    },
    "keyboard_navigation": {
      "tab_index": "logical",
      "shortcuts": []
    },
    "screen_reader_support": {
      "aria_labels": "required_for_interactive_elements",
      "aria_descriptions": "provided_for_complex_components"
    },
    "text_sizing": {
      "minimum_size": "16px",
      "scalable": true
    },
    "alternative_text": {
      "images": "required",
      "icons": "required_if_informational"
    }
  }
}
```

---

### Eventos Kafka Produzidos pelo Requirements Engineering System

```yaml
requirements.generated:
  - Producer: Requirements Engineering System
  - Consumer: Architectural Planning System
  - Payload: { id, requirements: [...] }

user_stories.generated:
  - Producer: User Story Generator
  - Consumer: Architectural Planning System, Test Generation System
  - Payload: { id, user_stories: [...] }

acceptance_criteria.generated:
  - Producer: Acceptance Criteria Generator
  - Consumer: Architectural Planning System, Test Generation System
  - Payload: { id, acceptance_criteria: [...] }

data_models.generated:
  - Producer: Data Model Designer
  - Consumer: Architectural Planning System, Code Forge
  - Payload: { id, entities: [...], relationships: [...], er_diagram: {...}, sql_schema: {...}, nosql_schema: {...}, migration_scripts: [...] }

api_designs.generated:
  - Producer: API Designer
  - Consumer: Architectural Planning System, Code Forge, Test Generation System
  - Payload: { id, endpoints: [...], openapi_spec: {...}, auth_strategy: {...}, versioning_strategy: {...} }

ui_ux_designs.generated:
  - Producer: UI/UX Designer
  - Consumer: Code Forge, Documentation Generation System
  - Payload: { id, personas: [...], user_journeys: [...], wireframes: [...], mockups: [...], component_library: [...], design_system: {...}, accessibility_guidelines: {...} }
```

---

## Conclusão da Parte 1

O Requirements Engineering System é o primeiro componente crítico do Fluxo G, transformando ideias simples em artefatos estruturados de engenharia de requisitos (requisitos funcionais, user stories, acceptance criteria, data models, API designs e UI/UX designs).

Este sistema produz 6 tipos principais de eventos Kafka que alimentam os sistemas downstream:
1. `requirements.generated` → Architectural Planning System
2. `user_stories.generated` → Architectural Planning System, Test Generation System
3. `acceptance_criteria.generated` → Architectural Planning System, Test Generation System
4. `data_models.generated` → Architectural Planning System, Code Forge
5. `api_designs.generated` → Architectural Planning System, Code Forge, Test Generation System
6. `ui_ux_designs.generated` → Code Forge, Documentation Generation System

---

## 🔧 Passo 4: Architectural Planning System (NOVO - 8011)

### Descrição Geral

Consome os artefatos gerados pelo Requirements Engineering System e gera a arquitetura completa do sistema, incluindo design arquitetural, system design, seleção de tech stack e diagramas.

### Componentes do Architectural Planning System

| Componente | Descrição |
|------------|-----------|
| **Architect Designer** | Gera arquiteturas do zero (monolith vs microservices vs serverless) |
| **System Designer** | Designa sistema completo (frontend, backend, DB, cache, MQ) |
| **Tech Stack Recommender** | Recomenda tech stack baseado em requisitos e constraints |
| **Diagram Generator** | Gera C4 models, UML diagrams, deployment diagrams |

### Portas e Endpoints

- **Porta API REST:** 8011
- **Health Check:** `/health`
- **Metrics:** `/metrics`
- **Endpoints:**
  - `POST /api/v1/architecture/design` - Gerar arquitetura
  - `POST /api/v1/architecture/system-design` - Gerar system design
  - `POST /api/v1/architecture/tech-stack` - Recomendar tech stack
  - `POST /api/v1/architecture/diagrams` - Gerar diagramas
  - `GET /api/v1/architecture/{id}` - Obter arquitetura completa

---

### 4.1 Knowledge Graph Profundo (RAG) - Pré-requisito

**Consumir:** `requirements.generated`, `data_models.generated`

**Responsabilidade:** Fornecer contexto rico via RAG (Retrieval Augmented Generation) para o Architectural Planning System.

#### RAG Engine

```python
# services/knowledge-base/src/services/rag_engine.py

class RAGEngine:
    async def search_context(self, query: str, domain: str, constraints: dict) -> dict:
        """
        Busca contexto relevante via RAG.

        Processo:
        1. Gerar embedding da query (sentence-transformers/all-MiniLM-L6-v2)
        2. Buscar documentos similares via ANN (Approximate Nearest Neighbor)
        3. Rerank resultados com cross-encoder
        4. Retornar contexto estruturado
        """
        # Gerar embedding da query
        query_embedding = await self.embedding_service.generate_embedding(query)

        # Buscar documentos similares
        similar_docs = await self.vector_store.search_similar(
            embedding=query_embedding,
            top_k=10,
            threshold=0.85
        )

        # Rerank resultados
        reranked = await self.reranker.rerank(query, similar_docs)

        # Retornar contexto estruturado
        context = {
            "design_patterns": self._extract_design_patterns(reranked),
            "best_practices": self._extract_best_practices(reranked),
            "similar_projects": self._extract_similar_projects(reranked),
            "anti_patterns": self._extract_anti_patterns(reranked),
            "tech_stack_knowledge": self._extract_tech_stack_knowledge(reranked)
        }

        return context
```

**Output:**
```json
{
  "design_patterns": [
    {
      "name": "Microservices Pattern",
      "description": "Divide a aplicação em serviços pequenos e independentes",
      "when_to_use": ["Aplicações complexas", "Escalabilidade horizontal", "Multi-teams"],
      "tradeoffs": {
        "pros": ["Escalabilidade independente", "Deployment independente", "Fault isolation"],
        "cons": ["Complexidade de comunicação", "Distributed transactions", "Latência de rede"]
      },
      "examples": ["Netflix", "Amazon", "Uber"],
      "confidence_score": 0.92
    },
    {
      "name": "CQRS (Command Query Responsibility Segregation)",
      "description": "Separa operações de leitura e escrita em modelos diferentes",
      "when_to_use": ["Alta carga de leitura", "Consultas complexas", "Real-time requirements"],
      "tradeoffs": {
        "pros": ["Performance de leitura otimizada", "Escalabilidade separada", "Flexibilidade de schemas"],
        "cons": ["Complexidade de sincronização", "Eventual consistency", "Duplicate data"]
      },
      "examples": ["EventStore", "Axon Framework", "Lagom"],
      "confidence_score": 0.87
    }
  ],
  "best_practices": [
    {
      "category": "API Design",
      "practice": "RESTful API Design",
      "description": "Seguir princípios REST para APIs",
      "guidelines": [
        "Usar nouns para resources (users, orders)",
        "Usar HTTP methods corretamente (GET, POST, PUT, DELETE)",
        "Versionar APIs via URL (/api/v1/)",
        "Usar status codes HTTP corretamente",
        "Implementar HATEOAS (Hypermedia as the Engine of Application State)"
      ]
    },
    {
      "category": "Database Design",
      "practice": "Database Normalization",
      "description": "Aplicar normalização para reduzir redundância",
      "guidelines": [
        "1NF: Eliminar repeating groups",
        "2NF: Eliminar partial dependencies",
        "3NF: Eliminar transitive dependencies",
        "Considerar denormalização para performance (caching, read-heavy workloads)"
      ]
    }
  ],
  "similar_projects": [
    {
      "name": "iFood Delivery Platform",
      "domain": "Food Delivery",
      "architecture": "Microservices",
      "tech_stack": {
        "frontend": "React Native",
        "backend": "Java, Spring Boot",
        "database": "PostgreSQL, MongoDB, Redis",
        "message_queue": "Kafka",
        "deployment": "Kubernetes"
      },
      "lessons_learned": [
        "Microservices aumentaram complexidade mas permitiram escalar independentemente",
        "Caching foi crucial para performance de listagens",
        "Event-driven architecture reduziu acoplamento entre serviços"
      ]
    },
    {
      "name": "Uber Eats",
      "domain": "Food Delivery",
      "architecture": "Microservices + Event-Driven",
      "tech_stack": {
        "frontend": "React, React Native",
        "backend": "Go, Java, Python",
        "database": "PostgreSQL, MySQL, Redis, Cassandra",
        "message_queue": "Kafka",
        "deployment": "Kubernetes"
      },
      "lessons_learned": [
        "Domain-driven design (DDD) foi essencial para definir bounded contexts",
        "Saga pattern resolveu distributed transactions",
        "Circuit breakers previniram cascading failures"
      ]
    }
  ],
  "anti_patterns": [
    {
      "name": "Distributed Monolith",
      "description": "Arquitetura microservices onde serviços são fortemente acoplados",
      "symptoms": [
        "Deployment de um serviço requer deployment de outros",
        "Chamadas síncronas entre serviços",
        "Shared database entre serviços"
      ],
      "consequences": [
        "Perda de benefícios de microservices",
        "Aumento de complexidade sem ganhos",
        "Dificuldade de manutenção e escalabilidade"
      ],
      "solutions": [
        "Aplicar Domain-Driven Design (DDD) para definir bounded contexts",
        "Usar communication assíncrona (event-driven)",
        "Separar databases por bounded context",
        "Implementar API Gateway para roteamento"
      ]
    }
  ],
  "tech_stack_knowledge": [
    {
      "category": "Frontend Frameworks",
      "options": [
        {
          "name": "React",
          "description": "Biblioteca JavaScript para construção de interfaces de usuário",
          "pros": ["Component-based", "Large ecosystem", "Performance", "Easy to learn"],
          "cons": ["JSX learning curve", "State management complexity"],
          "best_for": ["SPAs", "Complex UIs", "Large teams"],
          "popularity_score": 0.95,
          "maturity_score": 0.90
        },
        {
          "name": "Vue.js",
          "description": "Framework JavaScript progressivo para construção de UIs",
          "pros": ["Easy to learn", "Good documentation", "Flexible", "Performance"],
          "cons": ["Smaller ecosystem", "Less enterprise adoption"],
          "best_for": ["SPAs", "Startups", "Medium projects"],
          "popularity_score": 0.75,
          "maturity_score": 0.85
        },
        {
          "name": "Angular",
          "description": "Framework JavaScript para construção de aplicações web",
          "pros": ["Enterprise-ready", "Opinionated", "TypeScript support", "Large ecosystem"],
          "cons": ["Steep learning curve", "Complex", "Overkill for small projects"],
          "best_for": ["Enterprise apps", "Large teams", "Complex applications"],
          "popularity_score": 0.70,
          "maturity_score": 0.95
        }
      ]
    },
    {
      "category": "Backend Frameworks",
      "options": [
        {
          "name": "FastAPI",
          "description": "Framework Python moderno e rápido para criar APIs",
          "pros": ["Fast", "Async support", "Automatic docs", "Type hints"],
          "cons": ["Newer than Django/Flask", "Smaller ecosystem"],
          "best_for": ["APIs", "Microservices", "AI/ML applications"],
          "popularity_score": 0.85,
          "maturity_score": 0.75
        },
        {
          "name": "Django",
          "description": "Framework Python de alto nível para desenvolvimento web",
          "pros": ["Batteries included", "Admin interface", "ORM", "Security"],
          "cons": ["Monolithic", "Slow compared to FastAPI", "Opinionated"],
          "best_for": ["Full-stack apps", "CRUD apps", "Enterprise apps"],
          "popularity_score": 0.80,
          "maturity_score": 0.95
        },
        {
          "name": "Spring Boot",
          "description": "Framework Java para criar aplicações production-ready",
          "pros": ["Enterprise-ready", "Large ecosystem", "Microservices support", "Security"],
          "cons": ["Verbose", "Complex", "Heavy"],
          "best_for": ["Enterprise apps", "Microservices", "Large teams"],
          "popularity_score": 0.90,
          "maturity_score": 0.95
        }
      ]
    },
    {
      "category": "Databases",
      "options": [
        {
          "name": "PostgreSQL",
          "description": "Banco de dados relacional open-source avançado",
          "pros": ["ACID compliant", "Extensível", "JSON support", "Full-text search"],
          "cons": ["Scaling vertical", "Complex queries slow"],
          "best_for": ["Relational data", "Transactions", "ACID requirements"],
          "popularity_score": 0.90,
          "maturity_score": 0.95
        },
        {
          "name": "MongoDB",
          "description": "Banco de dados NoSQL orientado a documentos",
          "pros": ["Flexible schema", "Horizontal scaling", "Fast queries", "JSON native"],
          "cons": ["No ACID (before 4.0)", "Limited joins", "Memory heavy"],
          "best_for": ["Document data", "Rapid prototyping", "Horizontal scaling"],
          "popularity_score": 0.85,
          "maturity_score": 0.90
        },
        {
          "name": "Redis",
          "description": "Banco de dados in-memory, key-value store",
          "pros": ["Fast", "Versatile", "Pub/Sub", "Caching"],
          "cons": ["Limited data types", "Memory intensive"],
          "best_for": ["Caching", "Sessions", "Pub/Sub", "Rate limiting"],
          "popularity_score": 0.80,
          "maturity_score": 0.90
        }
      ]
    }
  ]
}
```

---

### 4.2 Architect Designer

**Responsabilidade:** Gerar arquiteturas do zero baseado em requisitos e contexto RAG.

**Consumir:**
- `requirements.generated`
- `data_models.generated`
- Contexto do Knowledge Graph (RAG)

**Processamento:**
```python
# services/architectural-planning/src/services/architect_designer.py

class ArchitectDesigner:
    async def design_architecture(self, requirements: List[Requirement], data_models: DataModel, rag_context: dict) -> Architecture:
        """
        Gera arquitetura completa do zero.

        Processo:
        1. Analisar requisitos funcionais e não-funcionais
        2. Analisar constraints (budget, timeline, team_size)
        3. Consultar RAG para patterns e similar_projects
        4. Decidir: monolith vs microservices vs serverless
        5. Designar arquitetura (layers, hexagonal, clean arch)
        6. Definir bounded contexts (DDD)
        7. Gerar architectural decision records (ADRs)
        """
        # Análise de requisitos não-funcionais
        nfr_analysis = await self._analyze_non_functional_requirements(requirements)

        # Análise de constraints
        constraints_analysis = await self._analyze_constraints(data_models)

        # Decisão de arquitetura
        architecture_type = await self._decide_architecture_type(
            nfr_analysis=nfr_analysis,
            constraints_analysis=constraints_analysis,
            rag_context=rag_context
        )

        # Design arquitetura baseada no tipo
        if architecture_type == "microservices":
            architecture = await self._design_microservices_architecture(requirements, data_models, rag_context)
        elif architecture_type == "monolith":
            architecture = await self._design_monolith_architecture(requirements, data_models, rag_context)
        elif architecture_type == "serverless":
            architecture = await self._design_serverless_architecture(requirements, data_models, rag_context)
        else:
            raise ValueError(f"Unknown architecture type: {architecture_type}")

        # Definir bounded contexts (DDD)
        bounded_contexts = await self._define_bounded_contexts(requirements, architecture)

        # Gerar ADRs
        adrs = await self._generate_architectural_decision_records(architecture, bounded_contexts)

        return {
            "architecture_type": architecture_type,
            "architecture": architecture,
            "bounded_contexts": bounded_contexts,
            "architectural_decision_records": adrs,
            "rationale": {
                "why": self._explain_why(architecture_type, nfr_analysis, constraints_analysis),
                "tradeoffs": self._explain_tradeoffs(architecture, rag_context),
                "alternatives_considered": self._explain_alternatives(architecture_type)
            }
        }

    async def _decide_architecture_type(self, nfr_analysis: dict, constraints_analysis: dict, rag_context: dict) -> str:
        """
        Decide o tipo de arquitetura baseado em análise.

        Critérios:
        - Escalabilidade requerida
        - Complexidade do domínio
        - Tamanho da equipe
        - Budget e timeline
        - Similar_projects do RAG
        """
        score_microservices = 0.0
        score_monolith = 0.0
        score_serverless = 0.0

        # Critério: Escalabilidade
        if nfr_analysis['scalability'] == 'high':
            score_microservices += 2.0
            score_serverless += 1.5
        elif nfr_analysis['scalability'] == 'medium':
            score_microservices += 1.0
            score_serverless += 1.0
        else:
            score_monolith += 1.0

        # Critério: Complexidade do domínio
        if nfr_analysis['domain_complexity'] == 'high':
            score_microservices += 2.0
        elif nfr_analysis['domain_complexity'] == 'medium':
            score_microservices += 1.0
            score_monolith += 1.0
        else:
            score_monolith += 1.0

        # Critério: Tamanho da equipe
        team_size = constraints_analysis['team_size']
        if team_size > 10:
            score_microservices += 2.0
        elif team_size > 5:
            score_microservices += 1.0
        else:
            score_monolith += 1.0

        # Critério: Budget e timeline
        if constraints_analysis['budget'] == 'low' or constraints_analysis['timeline'] == 'short':
            score_monolith += 2.0
            score_serverless += 1.0

        # Critério: Similar_projects do RAG
        similar_projects = rag_context.get('similar_projects', [])
        microservices_count = sum(1 for p in similar_projects if p['architecture'] == 'Microservices')
        if microservices_count > len(similar_projects) / 2:
            score_microservices += 1.0

        # Decisão
        scores = {
            'microservices': score_microservices,
            'monolith': score_monolith,
            'serverless': score_serverless
        }

        return max(scores, key=scores.get)
```

**Output:**
```json
{
  "architecture_type": "microservices",
  "architecture": {
    "pattern": "Microservices + Event-Driven",
    "description": "Arquitetura de microservices com comunicação assíncrona via eventos",
    "bounded_contexts": [
      {
        "name": "User Management",
        "description": "Gestão de usuários, autenticação e autorização",
        "services": ["user-service", "auth-service"],
        "domain_model": ["User", "Role", "Permission"],
        "responsibilities": [
          "Cadastro de usuários",
          "Login e autenticação",
          "Gestão de permissões",
          "Perfil de usuário"
        ]
      },
      {
        "name": "Restaurant Catalog",
        "description": "Catálogo de restaurantes e gestão de menus",
        "services": ["restaurant-service"],
        "domain_model": ["Restaurant", "Menu", "MenuItem"],
        "responsibilities": [
          "CRUD de restaurantes",
          "Gestão de menus",
          "Busca e filtros",
          "Avaliações"
        ]
      },
      {
        "name": "Order Management",
        "description": "Gestão de pedidos e fluxo de order",
        "services": ["order-service", "payment-service"],
        "domain_model": ["Order", "OrderItem", "Payment"],
        "responsibilities": [
          "Criação de pedidos",
          "Processamento de pagamentos",
          "Atualização de status",
          "Histórico de pedidos"
        ]
      },
      {
        "name": "Delivery Management",
        "description": "Gestão de entregadores e entregas",
        "services": ["delivery-service"],
        "domain_model": ["DeliveryPerson", "Delivery", "DeliveryRoute"],
        "responsibilities": [
          "Gestão de entregadores",
          "Roteamento de entregas",
          "Rastreamento em tempo real",
          "Confirmação de entrega"
        ]
      },
      {
        "name": "Notification",
        "description": "Envio de notificações (push, email, SMS)",
        "services": ["notification-service"],
        "domain_model": ["Notification", "NotificationTemplate"],
        "responsibilities": [
          "Envio de notificações",
          "Gestão de templates",
          "Histórico de notificações"
        ]
      }
    ],
    "communication_patterns": [
      {
        "pattern": "Event-Driven",
        "description": "Comunicação assíncrona via eventos Kafka",
        "use_cases": [
          "OrderCreated → PaymentProcess",
          "PaymentCompleted → RestaurantNotify",
          "PaymentCompleted → DeliveryAssign",
          "OrderStatusChanged → NotificationSend"
        ],
        "kafka_topics": [
          "orders.created",
          "orders.status.changed",
          "payments.completed",
          "payments.failed",
          "deliveries.assigned",
          "deliveries.status.changed"
        ]
      },
      {
        "pattern": "REST API",
        "description": "APIs síncronas para operações CRUD",
        "use_cases": [
          "GET /restaurants (listagem)",
          "POST /restaurants (criação)",
          "GET /users/{id} (busca)"
        ]
      }
    ],
    "data_strategy": [
      {
        "bounded_context": "User Management",
        "database": "PostgreSQL",
        "rationale": "Dados relacionais, ACID requirements"
      },
      {
        "bounded_context": "Restaurant Catalog",
        "database": "PostgreSQL",
        "rationale": "Dados relacionais, queries complexas"
      },
      {
        "bounded_context": "Order Management",
        "database": "PostgreSQL",
        "rationale": "Transações ACID, consistency crítica"
      },
      {
        "bounded_context": "Delivery Management",
        "database": "PostgreSQL",
        "rationale": "Dados relacionais, geoespatial queries"
      },
      {
        "bounded_context": "Notification",
        "database": "MongoDB",
        "rationale": "Documentos flexíveis, alta write throughput"
      }
    ],
    "caching_strategy": [
      {
        "use_case": "Listagem de restaurantes",
        "cache": "Redis",
        "ttl": "300s",
        "invalidation": "Update/Delete de restaurante"
      },
      {
        "use_case": "Detalhes de menu",
        "cache": "Redis",
        "ttl": "600s",
        "invalidation": "Update/Delete de menu"
      },
      {
        "use_case": "Sessões de usuário",
        "cache": "Redis",
        "ttl": "86400s",
        "invalidation": "Logout"
      }
    ],
    "message_queue": "Kafka",
    "api_gateway": "Kong / AWS API Gateway / Traefik",
    "service_discovery": "Consul / Eureka / K8s Service Discovery",
    "observability": {
      "logging": "ELK Stack (Elasticsearch, Logstash, Kibana)",
      "metrics": "Prometheus + Grafana",
      "tracing": "OpenTelemetry + Jaeger",
      "alerts": "Prometheus AlertManager"
    }
  },
  "architectural_decision_records": [
    {
      "adr_id": "ADR-001",
      "title": "Escolha de Arquitetura Microservices",
      "status": "Accepted",
      "date": "2026-04-15",
      "context": "O sistema precisa escalar independentemente para diferentes bounded contexts (users, restaurants, orders, deliveries). A equipe tem 5+ desenvolvedores e o budget permite a complexidade.",
      "decision": "Adotar arquitetura de microservices com comunicação event-driven via Kafka.",
      "consequences": [
        "Positivo: Escalabilidade independente por bounded context",
        "Positivo: Deployment independente reduz downtime",
        "Positivo: Fault isolation entre serviços",
        "Negativo: Complexidade aumentada de comunicação",
        "Negativo: Distributed transactions via Saga pattern",
        "Negativo: Latência de rede entre serviços"
      ]
    },
    {
      "adr_id": "ADR-002",
      "title": "Comunicação Event-Driven via Kafka",
      "status": "Accepted",
      "date": "2026-04-15",
      "context": "Microservices precisam se comunicar de forma assíncrona e desacoplada. Alta throughput de eventos (orders, payments, deliveries).",
      "decision": "Usar Kafka como message broker para comunicação event-driven entre serviços.",
      "consequences": [
        "Positivo: Desacoplamento entre serviços",
        "Positivo: Alta throughput e baixa latência",
        "Positivo: Durabilidade e replay de eventos",
        "Positivo: Suporte a consumer groups para escalabilidade",
        "Negativo: Complexidade de monitoramento",
        "Negativo: Eventual consistency"
      ]
    },
    {
      "adr_id": "ADR-003",
      "title": "Escolha de Banco de Dados Polyglot",
      "status": "Accepted",
      "date": "2026-04-15",
      "context": "Diferentes bounded contexts têm requisitos de dados diferentes (relacionais vs documental).",
      "decision": "Adotar estratégia polyglot persistence: PostgreSQL para dados relacionais, MongoDB para documentos.",
      "consequences": [
        "Positivo: Banco de dados otimizado para cada bounded context",
        "Positivo: Flexibilidade de schema no MongoDB",
        "Positivo: ACID no PostgreSQL para transações críticas",
        "Negativo: Complexidade de operar múltiplos bancos",
        "Negativo: Queries cross-database complexas"
      ]
    }
  ],
  "rationale": {
    "why": "Arquitetura microservices foi escolhida devido à alta escalabilidade requerida, complexidade do domínio (5 bounded contexts distintos) e tamanho da equipe (> 5 desenvolvedores). Comunicação event-drive via Kafka desacopla serviços e permite alta throughput.",
    "tradeoffs": {
      "monolith_vs_microservices": {
        "chose": "microservices",
        "pros": ["Escalabilidade independente", "Deployment independente", "Fault isolation"],
        "cons": ["Complexidade aumentada", "Distributed transactions", "Latência de rede"]
      },
      "sync_vs_async": {
        "chose": "async (event-driven)",
        "pros": ["Desacoplamento", "Alta throughput", "Durabilidade"],
        "cons": ["Eventual consistency", "Complexidade de debug"]
      },
      "relational_vs_nosql": {
        "chose": "polyglot (ambos)",
        "pros": ["Otimizado para cada bounded context", "Flexibilidade"],
        "cons": ["Complexidade operacional", "Queries cross-database"]
      }
    },
    "alternatives_considered": [
      {
        "alternative": "Monolith Modular",
        "reason_rejected": "Não atende requisitos de escalabilidade independentes por bounded context"
      },
      {
        "alternative": "Serverless (FaaS)",
        "reason_rejected": "Cold start latency afetaria UX, complexidade de state management"
      }
    ]
  }
}
```

---

### 4.3 System Designer

**Responsabilidade:** Designar sistema completo (frontend, backend, database, cache, message queue, deployment).

**Consumir:**
- `architecture.plan` (do Architect Designer)
- `requirements.generated`
- `data_models.generated`
- `ui_ux_designs.generated`

**Processamento:**
```python
# services/architectural-planning/src/services/system_designer.py

class SystemDesigner:
    async def design_system(self, architecture: Architecture, requirements: List[Requirement], data_models: DataModel, ui_ux_designs: UIUXDesign) -> SystemDesign:
        """
        Gera system design completo.

        Processo:
        1. Designar frontend components (mobile, web, admin)
        2. Designar backend services (APIs, workers, schedulers)
        3. Designar data layer (databases, cache, message queue)
        4. Gerar data flow diagrams
        5. Gerar sequence diagrams
        6. Capacity planning (estimativa de recursos)
        7. Gerar scalability strategies
        """
        # Designar frontend
        frontend_design = await self._design_frontend(ui_ux_designs, architecture)

        # Designar backend
        backend_design = await self._design_backend(architecture, requirements)

        # Designar data layer
        data_layer_design = await self._design_data_layer(architecture, data_models)

        # Gerar data flow diagram
        data_flow_diagram = await self._generate_data_flow_diagram(frontend_design, backend_design, data_layer_design)

        # Gerar sequence diagrams
        sequence_diagrams = await self._generate_sequence_diagrams(requirements, architecture)

        # Capacity planning
        capacity_plan = await self._capacity_planning(requirements, architecture)

        # Scalability strategies
        scalability_strategies = await self._generate_scalability_strategies(architecture, capacity_plan)

        return {
            "frontend_design": frontend_design,
            "backend_design": backend_design,
            "data_layer_design": data_layer_design,
            "data_flow_diagram": data_flow_diagram,
            "sequence_diagrams": sequence_diagrams,
            "capacity_plan": capacity_plan,
            "scalability_strategies": scalability_strategies
        }
```

**Output:**
```json
{
  "frontend_design": {
    "components": [
      {
        "name": "Mobile App (Customer)",
        "type": "mobile",
        "technology": "React Native",
        "platforms": ["iOS", "Android"],
        "features": [
          "Cadastro e login de usuários",
          "Listagem e busca de restaurantes",
          "Detalhes de restaurante e menu",
          "Criação e gerenciamento de pedidos",
          "Rastreamento de pedidos em tempo real",
          "Histórico de pedidos",
          "Perfil e configurações"
        ],
        "integrations": [
          { "api": "User Service", "endpoints": ["/api/v1/users"] },
          { "api": "Restaurant Service", "endpoints": ["/api/v1/restaurants"] },
          { "api": "Order Service", "endpoints": ["/api/v1/orders"] },
          { "api": "Notification Service", "endpoints": ["/api/v1/notifications"] },
          { "websocket": "Delivery Service", "topic": "deliveries.updates" }
        ],
        "offline_support": true,
        "push_notifications": true,
        "biometrics": true
      },
      {
        "name": "Web App (Restaurant Admin)",
        "type": "web",
        "technology": "React + TypeScript",
        "features": [
          "Cadastro e gestão de restaurante",
          "Gestão de menu e itens",
          "Gestão de pedidos (aceitar/rejeitar)",
          "Relatórios e analytics",
          "Gestão de horários de funcionamento",
          "Gestão de entregadores"
        ],
        "integrations": [
          { "api": "Restaurant Service", "endpoints": ["/api/v1/restaurants", "/api/v1/menus"] },
          { "api": "Order Service", "endpoints": ["/api/v1/orders"] },
          { "api": "Delivery Service", "endpoints": ["/api/v1/delivery-persons"] }
        ]
      },
      {
        "name": "Admin Dashboard (Platform)",
        "type": "web",
        "technology": "React + TypeScript",
        "features": [
          "Gestão de usuários (admin)",
          "Monitoramento de platform (metrics, alerts)",
          "Gestão de conteúdo (banners, promoções)",
          "Relatórios de negócio",
          "Configuração de sistema"
        ],
        "integrations": [
          { "api": "All Services", "endpoints": ["/api/v1/..."] },
          { "monitoring": "Prometheus/Grafana" }
        ]
      }
    ],
    "shared_libraries": [
      {
        "name": "Design System",
        "description": "Component library compartilhada (React Native + React Web)",
        "technologies": ["Storybook", "React Native Web"]
      },
      {
        "name": "API Client",
        "description": "Client HTTP com autenticação e retry logic",
        "technologies": ["Axios", "Redux Toolkit Query (RTK Query)"]
      },
      {
        "name": "State Management",
        "description": "Gerenciamento de estado compartilhado",
        "technologies": ["Redux Toolkit", "RTK Query"]
      }
    ],
    "authentication": {
      "strategy": "JWT Bearer Tokens",
      "token_expiry": "24h",
      "refresh_token_expiry": "7d",
      "social_login": ["Google", "Facebook", "Apple"],
      "biometrics": ["FaceID", "TouchID"]
    },
    "authorization": {
      "strategy": "Role-Based Access Control (RBAC)",
      "roles": [
        { "name": "customer", "permissions": ["read:own_data", "create:orders"] },
        { "name": "restaurant_owner", "permissions": ["manage:restaurant", "manage:orders"] },
        { "name": "delivery_person", "permissions": ["manage:deliveries"] },
        { "name": "admin", "permissions": ["*:*"] }
      ]
    }
  },
  "backend_design": {
    "services": [
      {
        "name": "user-service",
        "port": 8010,
        "language": "Python",
        "framework": "FastAPI",
        "responsibilities": [
          "Cadastro e gestão de usuários",
          "Autenticação (login, logout, refresh token)",
          "Gestão de perfis e preferências"
        ],
        "api_endpoints": [
          { "method": "POST", "path": "/api/v1/users", "description": "Criar usuário" },
          { "method": "GET", "path": "/api/v1/users/{id}", "description": "Buscar usuário" },
          { "method": "PUT", "path": "/api/v1/users/{id}", "description": "Atualizar usuário" },
          { "method": "POST", "path": "/api/v1/auth/login", "description": "Login" },
          { "method": "POST", "path": "/api/v1/auth/logout", "description": "Logout" },
          { "method": "POST", "path": "/api/v1/auth/refresh", "description": "Refresh token" }
        ],
        "kafka_topics": [
          { "topic": "users.created", "role": "producer" },
          { "topic": "users.updated", "role": "producer" }
        ],
        "database": "PostgreSQL",
        "cache": "Redis (user sessions)"
      },
      {
        "name": "restaurant-service",
        "port": 8011,
        "language": "Python",
        "framework": "FastAPI",
        "responsibilities": [
          "CRUD de restaurantes",
          "Gestão de menus e itens",
          "Busca e filtros de restaurantes",
          "Avaliações e reviews"
        ],
        "api_endpoints": [
          { "method": "POST", "path": "/api/v1/restaurants", "description": "Criar restaurante" },
          { "method": "GET", "path": "/api/v1/restaurants", "description": "Listar restaurantes" },
          { "method": "GET", "path": "/api/v1/restaurants/{id}", "description": "Buscar restaurante" },
          { "method": "PUT", "path": "/api/v1/restaurants/{id}", "description": "Atualizar restaurante" },
          { "method": "DELETE", "path": "/api/v1/restaurants/{id}", "description": "Deletar restaurante" },
          { "method": "POST", "path": "/api/v1/restaurants/{id}/menus", "description": "Criar menu" },
          { "method": "GET", "path": "/api/v1/restaurants/{id}/menus", "description": "Listar menus" }
        ],
        "kafka_topics": [
          { "topic": "restaurants.created", "role": "producer" },
          { "topic": "restaurants.updated", "role": "producer" }
        ],
        "database": "PostgreSQL",
        "cache": "Redis (restaurant listings, menus)"
      },
      {
        "name": "order-service",
        "port": 8012,
        "language": "Python",
        "framework": "FastAPI",
        "responsibilities": [
          "Criação e gestão de pedidos",
          "Atualização de status de pedidos",
          "Cálculo de totais e taxas",
          "Histórico de pedidos"
        ],
        "api_endpoints": [
          { "method": "POST", "path": "/api/v1/orders", "description": "Criar pedido" },
          { "method": "GET", "path": "/api/v1/orders", "description": "Listar pedidos" },
          { "method": "GET", "path": "/api/v1/orders/{id}", "description": "Buscar pedido" },
          { "method": "PUT", "path": "/api/v1/orders/{id}/status", "description": "Atualizar status" }
        ],
        "kafka_topics": [
          { "topic": "orders.created", "role": "producer" },
          { "topic": "orders.status.changed", "role": "producer" },
          { "topic": "payments.completed", "role": "consumer" },
          { "topic": "payments.failed", "role": "consumer" }
        ],
        "database": "PostgreSQL",
        "cache": "Redis (order status)"
      },
      {
        "name": "payment-service",
        "port": 8013,
        "language": "Python",
        "framework": "FastAPI",
        "responsibilities": [
          "Processamento de pagamentos",
          "Integração com gateways (Stripe, Mercado Pago)",
          "Gestão de métodos de pagamento",
          "Reembolsos"
        ],
        "api_endpoints": [
          { "method": "POST", "path": "/api/v1/payments", "description": "Criar pagamento" },
          { "method": "GET", "path": "/api/v1/payments/{id}", "description": "Buscar pagamento" },
          { "method": "POST", "path": "/api/v1/payments/{id}/refund", "description": "Reembolsar" }
        ],
        "kafka_topics": [
          { "topic": "orders.created", "role": "consumer" },
          { "topic": "payments.completed", "role": "producer" },
          { "topic": "payments.failed", "role": "producer" }
        ],
        "database": "PostgreSQL",
        "external_integrations": ["Stripe", "Mercado Pago"]
      },
      {
        "name": "delivery-service",
        "port": 8014,
        "language": "Python",
        "framework": "FastAPI",
        "responsibilities": [
          "Gestão de entregadores",
          "Atribuição de entregas",
          "Roteamento de entregas",
          "Rastreamento em tempo real"
        ],
        "api_endpoints": [
          { "method": "POST", "path": "/api/v1/delivery-persons", "description": "Criar entregador" },
          { "method": "GET", "path": "/api/v1/delivery-persons", "description": "Listar entregadores" },
          { "method": "GET", "path": "/api/v1/deliveries", "description": "Listar entregas" },
          { "method": "PUT", "path": "/api/v1/deliveries/{id}/status", "description": "Atualizar status" },
          { "method": "GET", "path": "/api/v1/deliveries/{id}/location", "description": "Rastrear localização" }
        ],
        "kafka_topics": [
          { "topic": "payments.completed", "role": "consumer" },
          { "topic": "deliveries.assigned", "role": "producer" },
          { "topic": "deliveries.status.changed", "role": "producer" }
        ],
        "websocket": {
          "topic": "deliveries.updates",
          "description": "Real-time updates de entregas"
        },
        "database": "PostgreSQL (com PostGIS para queries geoespaciais)",
        "external_integrations": ["Google Maps API", "OpenStreetMap"]
      },
      {
        "name": "notification-service",
        "port": 8015,
        "language": "Python",
        "framework": "FastAPI",
        "responsibilities": [
          "Envio de notificações (push, email, SMS)",
          "Gestão de templates de notificação",
          "Histórico de notificações",
          "Preferências de notificação"
        ],
        "api_endpoints": [
          { "method": "POST", "path": "/api/v1/notifications", "description": "Criar notificação" },
          { "method": "GET", "path": "/api/v1/notifications", "description": "Listar notificações" }
        ],
        "kafka_topics": [
          { "topic": "orders.status.changed", "role": "consumer" },
          { "topic": "deliveries.status.changed", "role": "consumer" }
        ],
        "database": "MongoDB",
        "external_integrations": [
          "Firebase Cloud Messaging (FCM)",
          "AWS SES (email)",
          "Twilio (SMS)"
        ]
      }
    ],
    "api_gateway": {
      "technology": "Kong / AWS API Gateway",
      "features": [
        "Rate limiting",
        "Authentication/Authorization",
        "SSL termination",
        "Request/response transformation",
        "Caching",
        "Analytics"
      ],
      "routes": [
        { "path": "/api/v1/users", "service": "user-service" },
        { "path": "/api/v1/auth", "service": "user-service" },
        { "path": "/api/v1/restaurants", "service": "restaurant-service" },
        { "path": "/api/v1/orders", "service": "order-service" },
        { "path": "/api/v1/payments", "service": "payment-service" },
        { "path": "/api/v1/deliveries", "service": "delivery-service" },
        { "path": "/api/v1/notifications", "service": "notification-service" }
      ]
    },
    "observability": {
      "logging": {
        "technology": "ELK Stack",
        "components": ["Elasticsearch", "Logstash", "Kibana"],
        "log_level": "INFO",
        "structured_logging": true
      },
      "metrics": {
        "technology": "Prometheus + Grafana",
        "metrics": [
          "requests_total",
          "request_duration_seconds",
          "error_rate",
          "queue_depth",
          "database_connections"
        ],
        "dashboards": [
          "Service Overview",
          "API Performance",
          "Error Rates",
          "Kafka Consumer Lag"
        ]
      },
      "tracing": {
        "technology": "OpenTelemetry + Jaeger",
        "sampling_rate": 0.1
      },
      "alerts": {
        "technology": "Prometheus AlertManager",
        "rules": [
          { "name": "HighErrorRate", "condition": "error_rate > 0.05", "severity": "warning" },
          { "name": "HighLatency", "condition": "p95_latency > 1s", "severity": "warning" },
          { "name": "ServiceDown", "condition": "up == 0", "severity": "critical" }
        ]
      }
    }
  },
  "data_layer_design": {
    "databases": [
      {
        "name": "user_db",
        "type": "PostgreSQL",
        "version": "15",
        "purpose": "Armazenamento de dados de usuários",
        "tables": ["users", "roles", "permissions", "user_roles"],
        "connection_pool": {
          "min_connections": 5,
          "max_connections": 20
        },
        "replication": {
          "enabled": true,
          "replicas": 2
        },
        "backup": {
          "enabled": true,
          "retention": "7d",
          "schedule": "daily"
        }
      },
      {
        "name": "restaurant_db",
        "type": "PostgreSQL",
        "version": "15",
        "purpose": "Armazenamento de restaurantes e menus",
        "tables": ["restaurants", "menus", "menu_items", "reviews"],
        "connection_pool": {
          "min_connections": 5,
          "max_connections": 20
        },
        "replication": {
          "enabled": true,
          "replicas": 2
        },
        "backup": {
          "enabled": true,
          "retention": "7d",
          "schedule": "daily"
        }
      },
      {
        "name": "order_db",
        "type": "PostgreSQL",
        "version": "15",
        "purpose": "Armazenamento de pedidos",
        "tables": ["orders", "order_items"],
        "connection_pool": {
          "min_connections": 10,
          "max_connections": 50
        },
        "replication": {
          "enabled": true,
          "replicas": 2
        },
        "backup": {
          "enabled": true,
          "retention": "30d",
          "schedule": "daily"
        }
      },
      {
        "name": "delivery_db",
        "type": "PostgreSQL",
        "version": "15",
        "extensions": ["PostGIS"],
        "purpose": "Armazenamento de entregas e entregadores",
        "tables": ["delivery_persons", "deliveries", "delivery_routes"],
        "connection_pool": {
          "min_connections": 5,
          "max_connections": 20
        },
        "replication": {
          "enabled": true,
          "replicas": 2
        },
        "backup": {
          "enabled": true,
          "retention": "30d",
          "schedule": "daily"
        }
      },
      {
        "name": "notification_db",
        "type": "MongoDB",
        "version": "6.0",
        "purpose": "Armazenamento de notificações",
        "collections": ["notifications", "notification_templates", "user_preferences"],
        "connection_pool": {
          "min_connections": 5,
          "max_connections": 50
        },
        "replication": {
          "enabled": true,
          "replica_sets": 3
        },
        "backup": {
          "enabled": true,
          "retention": "7d",
          "schedule": "daily"
        }
      }
    ],
    "cache": {
      "name": "Redis Cluster",
      "version": "7.0",
      "purpose": "Caching e session storage",
      "use_cases": [
        "Restaurant listings (TTL: 300s)",
        "Menu items (TTL: 600s)",
        "User sessions (TTL: 86400s)",
        "Order status (TTL: 3600s)",
        "Rate limiting (TTL: 60s)"
      ],
      "configuration": {
        "memory_limit": "2GB",
        "eviction_policy": "allkeys-lru",
        "persistence": "RDB + AOF"
      },
      "replication": {
        "enabled": true,
        "replicas": 2
      }
    },
    "message_queue": {
      "name": "Kafka Cluster",
      "version": "3.5",
      "purpose": "Event-driven communication",
      "topics": [
        { "name": "users.created", "partitions": 3, "replication_factor": 2 },
        { "name": "users.updated", "partitions": 3, "replication_factor": 2 },
        { "name": "restaurants.created", "partitions": 3, "replication_factor": 2 },
        { "name": "restaurants.updated", "partitions": 3, "replication_factor": 2 },
        { "name": "orders.created", "partitions": 10, "replication_factor": 2 },
        { "name": "orders.status.changed", "partitions": 10, "replication_factor": 2 },
        { "name": "payments.completed", "partitions": 10, "replication_factor": 2 },
        { "name": "payments.failed", "partitions": 10, "replication_factor": 2 },
        { "name": "deliveries.assigned", "partitions": 5, "replication_factor": 2 },
        { "name": "deliveries.status.changed", "partitions": 5, "replication_factor": 2 }
      ],
      "configuration": {
        "retention": "7d",
        "compression": "snappy",
        "auto_create_topics": false
      }
    }
  },
  "data_flow_diagram": {
    "format": "mermaid",
    "content": "graph TD\n    A[Mobile App] -->|HTTP REST| B[API Gateway]\n    B -->|HTTP REST| C[User Service]\n    B -->|HTTP REST| D[Restaurant Service]\n    B -->|HTTP REST| E[Order Service]\n    B -->|HTTP REST| F[Payment Service]\n    B -->|HTTP REST| G[Delivery Service]\n    C -->|Write| H[(User DB - PostgreSQL)]\n    C -->|Cache| I[(Redis - User Sessions)]\n    C -->|Produce| J[Kafka - users.created]\n    D -->|Write| K[(Restaurant DB - PostgreSQL)]\n    D -->|Cache| I[(Redis - Restaurant Listings)]\n    D -->|Produce| L[Kafka - restaurants.created]\n    E -->|Write| M[(Order DB - PostgreSQL)]\n    E -->|Cache| I[(Redis - Order Status)]\n    E -->|Produce| N[Kafka - orders.created]\n    F -->|Consume| N[Kafka - orders.created]\n    F -->|Write| O[(Payment DB - PostgreSQL)]\n    F -->|External| P[(Stripe, Mercado Pago)]\n    F -->|Produce| Q[Kafka - payments.completed]\n    F -->|Produce| R[Kafka - payments.failed]\n    G -->|Consume| Q[Kafka - payments.completed]\n    G -->|Write| S[(Delivery DB - PostgreSQL + PostGIS)]\n    G -->|External| T[(Google Maps API)]\n    G -->|WebSocket| A[Mobile App - Real-time]\n    G -->|Produce| U[Kafka - deliveries.assigned]\n    G -->|Produce| V[Kafka - deliveries.status.changed]\n    W[Notification Service] -->|Consume| N[Kafka - orders.created]\n    W -->|Consume| V[Kafka - deliveries.status.changed]\n    W -->|Write| X[(Notification DB - MongoDB)]\n    W -->|External| Y[(Firebase, AWS SES, Twilio)]"
  },
  "sequence_diagrams": [
    {
      "title": "Fluxo de Criação de Pedido",
      "format": "mermaid",
      "content": "sequenceDiagram\n    participant User as Usuário\n    participant Mobile as Mobile App\n    participant APIGateway as API Gateway\n    participant OrderSvc as Order Service\n    participant RestaurantSvc as Restaurant Service\n    participant PaymentSvc as Payment Service\n    participant DeliverySvc as Delivery Service\n    participant Kafka as Kafka\n    participant NotificationSvc as Notification Service\n\n    User->>Mobile: Selecione restaurante e itens\n    Mobile->>APIGateway: POST /api/v1/orders\n    APIGateway->>OrderSvc: POST /api/v1/orders\n    OrderSvc->>RestaurantSvc: Validar disponibilidade\n    RestaurantSvc-->>OrderSvc: Disponível\n    OrderSvc->>OrderSvc: Calcular total\n    OrderSvc->>Kafka: orders.created\n    OrderSvc-->>Mobile: 201 Order Created\n\n    Kafka->>PaymentSvc: orders.created\n    PaymentSvc->>PaymentSvc: Processar pagamento\n    PaymentSvc->>PaymentSvc: Gateway (Stripe, Mercado Pago)\n    PaymentSvc-->>PaymentSvc: Pagamento aprovado\n    PaymentSvc->>Kafka: payments.completed\n\n    Kafka->>OrderSvc: payments.completed\n    OrderSvc->>OrderSvc: Atualizar status: Aguardando Restaurante\n    OrderSvc->>Kafka: orders.status.changed\n\n    Kafka->>NotificationSvc: orders.status.changed\n    NotificationSvc->>NotificationSvc: Enviar push\n    NotificationSvc-->>User: Push: Pedido confirmado\n\n    Kafka->>DeliverySvc: payments.completed\n    DeliverySvc->>DeliverySvc: Atribuir entregador\n    DeliverySvc->>Kafka: deliveries.assigned\n    DeliverySvc->>Mobile: WebSocket: Entregador atribuído\n\n    Mobile->>DeliverySvc: WebSocket: Conectar\n    DeliverySvc-->>Mobile: Real-time updates"
    }
  ],
  "capacity_plan": {
    "traffic_estimates": {
      "daily_active_users": 10000,
      "orders_per_day": 5000,
      "peak_concurrent_users": 1000,
      "peak_orders_per_hour": 500
    },
    "resource_requirements": {
      "frontend": {
        "mobile_app": "No server-side resources (client-side)",
        "web_app": "CDN hosting (AWS CloudFront / Cloudflare)"
      },
      "backend": {
        "api_gateway": "t3.medium (2 vCPU, 4GB RAM) x 3 instances",
        "user_service": "t3.medium (2 vCPU, 4GB RAM) x 3 instances",
        "restaurant_service": "t3.medium (2 vCPU, 4GB RAM) x 3 instances",
        "order_service": "t3.large (2 vCPU, 8GB RAM) x 5 instances",
        "payment_service": "t3.medium (2 vCPU, 4GB RAM) x 3 instances",
        "delivery_service": "t3.medium (2 vCPU, 4GB RAM) x 3 instances",
        "notification_service": "t3.small (1 vCPU, 2GB RAM) x 2 instances"
      },
      "databases": {
        "postgresql_clusters": "t3.large (2 vCPU, 8GB RAM) x 5 instances (1 primary + 2 replicas)",
        "mongodb_cluster": "t3.medium (2 vCPU, 4GB RAM) x 3 instances (replica set)"
      },
      "cache": {
        "redis_cluster": "cache.t3.medium (2 vCPU, 4GB RAM) x 3 instances (1 primary + 2 replicas)"
      },
      "message_queue": {
        "kafka_cluster": "kafka.m5.large (2 vCPU, 8GB RAM) x 3 instances"
      },
      "cdn": {
        "cloudfront": "AWS CloudFront (edge locations globais)"
      }
    },
    "scaling_strategy": {
      "horizontal_scaling": {
        "backend_services": "Auto Scaling Groups (ASG) com target tracking",
        "databases": "Read replicas para PostgreSQL, Replica Sets para MongoDB",
        "kafka": "Broker scale-out baseado em throughput"
      },
      "vertical_scaling": {
        "databases": "Instance types baseados em workload (CPU/Memory/Disk)",
        "redis": "Memory scaling baseado em cache hit rate"
      },
      "autoscaling_policies": [
        {
          "service": "order-service",
          "metric": "CPU utilization",
          "target": "70%",
          "min_instances": 3,
          "max_instances": 10
        },
        {
          "service": "order-service",
          "metric": "Request rate",
          "target": "100 requests/second",
          "min_instances": 3,
          "max_instances": 10
        }
      ]
    }
  },
  "scalability_strategies": [
    {
      "aspect": "Database Scaling",
      "strategies": [
        {
          "name": "Read Replicas",
          "description": "Adicionar read replicas para PostgreSQL",
          "use_case": "Workloads de leitura pesada (listagens de restaurantes, menus)",
          "implementation": "AWS RDS Read Replicas / PostgreSQL Streaming Replication"
        },
        {
          "name": "Connection Pooling",
          "description": "Usar connection pooling para reduzir overhead de conexões",
          "use_case": "Alta concorrência de database connections",
          "implementation": "PgBouncer / PgPool-II"
        },
        {
          "name": "Caching",
          "description": "Caching layer (Redis) para queries frequentes",
          "use_case": "Listagens de restaurantes, menus, user sessions",
          "implementation": "Redis Cluster com cache-aside pattern"
        }
      ]
    },
    {
      "aspect": "Application Scaling",
      "strategies": [
        {
          "name": "Horizontal Pod Autoscaler (HPA)",
          "description": "Escalamento automático de pods baseado em metrics",
          "use_case": "Backend services (order-service, restaurant-service)",
          "implementation": "Kubernetes HPA com metrics de CPU, memory, custom metrics"
        },
        {
          "name": "Load Balancing",
          "description": "Distribuir tráfego entre múltiplas instâncias",
          "use_case": "API Gateway, Backend services",
          "implementation": "AWS ALB / Nginx / HAProxy"
        }
      ]
    },
    {
      "aspect": "Message Queue Scaling",
      "strategies": [
        {
          "name": "Kafka Partitioning",
          "description": "Aumentar número de partições para throughput",
          "use_case": "High throughput topics (orders.created, payments.completed)",
          "implementation": "Kafka partition reassignment (kafka-reassign-partitions.sh)"
        },
        {
          "name": "Consumer Group Scaling",
          "description": "Aumentar número de consumers para processamento paralelo",
          "use_case": "Order service, Payment service",
          "implementation": "Kubernetes HPA para consumer pods"
        }
      ]
    },
    {
      "aspect": "CDN Scaling",
      "strategies": [
        {
          "name": "Global Edge Locations",
          "description": "Distribuir conteúdo globalmente via CDN",
          "use_case": "Static assets (imagens, CSS, JS)",
          "implementation": "AWS CloudFront / Cloudflare"
        },
        {
          "name": "Image Optimization",
          "description": "Otimizar imagens para diferentes dispositivos",
          "use_case": "Restaurant images, food images",
          "implementation": "AWS CloudFront + Lambda@Edge / Cloudflare Image Resizing"
        }
      ]
    }
  ]
}
```

---

### Eventos Kafka Produzidos pelo Architectural Planning System

```yaml
architectural.plan:
  - Producer: Architect Designer
  - Consumer: Agentic Delegation System, Code Forge
  - Payload: { id, architecture_type, architecture: {...}, bounded_contexts: [...], architectural_decision_records: [...] }

system_design.generated:
  - Producer: System Designer
  - Consumer: Code Forge, Documentation Generation System
  - Payload: { id, frontend_design: {...}, backend_design: {...}, data_layer_design: {...}, data_flow_diagram: {...}, sequence_diagrams: [...] }

tech_stack.selected:
  - Producer: Tech Stack Recommender
  - Consumer: Code Forge, Software Engineering Pipeline
  - Payload: { id, tech_stack: {...}, justification: {...} }

diagrams.generated:
  - Producer: Diagram Generator
  - Consumer: Documentation Generation System
  - Payload: { id, diagrams: [{ name, type, format, content }] }
```

---

## Conclusão da Parte 2

O Architectural Planning System é o segundo componente crítico do Fluxo G, consumindo os artefatos do Requirements Engineering System e gerando a arquitetura completa do sistema.

Este sistema produz 4 tipos principais de eventos Kafka que alimentam os sistemas downstream:
1. `architectural.plan` → Agentic Delegation System, Code Forge
2. `system_design.generated` → Code Forge, Documentation Generation System
3. `tech_stack.selected` → Code Forge, Software Engineering Pipeline
4. `diagrams.generated` → Documentation Generation System

---

## 🤖 Passo 5: Agentic Delegation System (NOVO - 8012)

### Descrição Geral

Consume os artefatos gerados pelo Architectural Planning System e gerencia a delegação de tarefas para múltiplos agentes especializados, coordenando o desenvolvimento iterativo do projeto.

### Componentes do Agentic Delegation System

| Componente | Descrição |
|------------|-----------|
| **Decomposer** | Decompõe plano arquitetural em subtarefas delegáveis |
| **Task Dispatcher** | Atribui tarefas aos agentes mais apropriados |
| **Agent Coordinator** | Orquestra múltiplos agentes trabalhando no mesmo projeto |
| **Progress Tracker** | Rastreia progresso consolidado de todos os agentes |
| **Conflict Resolver** | Resolve conflitos entre agentes |

### Portas e Endpoints

- **Porta API REST:** 8012
- **Health Check:** `/health`
- **Metrics:** `/metrics`
- **Endpoints:**
  - `POST /api/v1/delegation/decompose` - Decompor plano em subtarefas
  - `POST /api/v1/delegation/dispatch` - Atribuir tarefas a agentes
  - `POST /api/v1/delegation/coordinate` - Iniciar coordenação de agentes
  - `GET /api/v1/delegation/{id}/progress` - Obter progresso consolidado
  - `POST /api/v1/delegation/resolve-conflict` - Resolver conflitos

---

### 5.1 Decomposer

**Responsabilidade:** Decompor plano arquitetural completo em subtarefas delegáveis e gerar ExecutionPlan com dependências.

**Consumir:**
- `architectural.plan`
- `system_design.generated`
- `requirements.generated`
- `user_stories.generated`

**Processamento:**
```python
# services/agentic-delegation/src/services/decomposer.py

class Decomposer:
    async def decompose_plan(self, architectural_plan: Architecture, system_design: SystemDesign, requirements: List[Requirement], user_stories: List[UserStory]) -> ExecutionPlan:
        """
        Decompõe plano arquitetural em subtarefas delegáveis.

        Processo:
        1. Analisar bounded contexts do architectural plan
        2. Identificar componentes de cada bounded context
        3. Decompor em subtarefas por componente (frontend, backend, database, tests, docs)
        4. Definir dependências entre subtarefas
        5. Estimar complexidade e esforço de cada subtarefa
        6. Gerar ExecutionPlan com DAG (Directed Acyclic Graph)
        7. Definir milestones e checkpoints
        """
        # Análise de bounded contexts
        bounded_contexts = architectural_plan.get('architecture', {}).get('bounded_contexts', [])

        # Decomposição de subtarefas
        tasks = await self._generate_tasks(bounded_contexts, system_design, requirements, user_stories)

        # Definir dependências
        dependencies = await self._define_dependencies(tasks, system_design)

        # Estimar complexidade
        tasks_with_complexity = await self._estimate_complexity(tasks, user_stories)

        # Gerar DAG
        dag = await self._generate_dag(tasks_with_complexity, dependencies)

        # Definir milestones
        milestones = await self._define_milestones(tasks_with_complexity, dag)

        # Definir checkpoints
        checkpoints = await self._define_checkpoints(tasks_with_complexity, dag)

        return {
            "id": str(uuid.uuid4()),
            "project_id": architectural_plan.get('id'),
            "tasks": tasks_with_complexity,
            "dependencies": dependencies,
            "dag": dag,
            "milestones": milestones,
            "checkpoints": checkpoints,
            "estimated_duration": await self._estimate_duration(tasks_with_complexity),
            "critical_path": await self._find_critical_path(tasks_with_complexity, dependencies)
        }

    async def _generate_tasks(self, bounded_contexts: List[dict], system_design: SystemDesign, requirements: List[Requirement], user_stories: List[UserStory]) -> List[Task]:
        """
        Gera subtarefas para cada bounded context.
        """
        tasks = []

        for bc in bounded_contexts:
            bc_name = bc['name']
            services = bc.get('services', [])

            for service in services:
                # Frontend tasks
                if await self._has_frontend_component(service, system_design):
                    tasks.extend(await self._generate_frontend_tasks(bc_name, service, user_stories))

                # Backend tasks
                tasks.extend(await self._generate_backend_tasks(bc_name, service, system_design, requirements))

                # Database tasks
                tasks.extend(await self._generate_database_tasks(bc_name, service, system_design))

                # Test tasks
                tasks.extend(await self._generate_test_tasks(bc_name, service, system_design, user_stories))

                # Documentation tasks
                tasks.extend(await self._generate_documentation_tasks(bc_name, service, system_design))

        return tasks

    async def _generate_backend_tasks(self, bc_name: str, service: str, system_design: SystemDesign, requirements: List[Requirement]) -> List[Task]:
        """
        Gera subtarefas de backend para um serviço.
        """
        tasks = []

        # Task 1: Setup de projeto
        tasks.append({
            "id": f"task_{bc_name}_{service}_setup",
            "name": f"Setup {service}",
            "description": f"Inicializar projeto {service} com estrutura base",
            "bounded_context": bc_name,
            "service": service,
            "type": "backend_setup",
            "skill_requirements": ["Python", "FastAPI", "Docker"],
            "complexity": "low",
            "estimated_hours": 2,
            "priority": "high",
            "dependencies": [],
            "deliverables": [
                "Project structure",
                "requirements.txt",
                "Dockerfile",
                ".gitignore",
                "README.md"
            ]
        })

        # Task 2: Implementar modelos de domínio
        tasks.append({
            "id": f"task_{bc_name}_{service}_models",
            "name": f"Implementar modelos de domínio - {service}",
            "description": f"Criar modelos de domínio (Pydantic) para {service}",
            "bounded_context": bc_name,
            "service": service,
            "type": "backend_models",
            "skill_requirements": ["Python", "Pydantic", "Domain Modeling"],
            "complexity": "medium",
            "estimated_hours": 4,
            "priority": "high",
            "dependencies": [f"task_{bc_name}_{service}_setup"],
            "deliverables": [
                "domain/models.py",
                "unit tests para modelos"
            ]
        })

        # Task 3: Implementar repository layer
        tasks.append({
            "id": f"task_{bc_name}_{service}_repositories",
            "name": f"Implementar repository layer - {service}",
            "description": f"Criar repository layer para acesso a dados",
            "bounded_context": bc_name,
            "service": service,
            "type": "backend_repositories",
            "skill_requirements": ["Python", "SQLAlchemy", "MongoDB"],
            "complexity": "medium",
            "estimated_hours": 6,
            "priority": "high",
            "dependencies": [f"task_{bc_name}_{service}_models"],
            "deliverables": [
                "infrastructure/repositories.py",
                "database migrations",
                "unit tests para repositories"
            ]
        })

        # Task 4: Implementar service layer
        tasks.append({
            "id": f"task_{bc_name}_{service}_services",
            "name": f"Implementar service layer - {service}",
            "description": f"Criar service layer com lógica de negócio",
            "bounded_context": bc_name,
            "service": service,
            "type": "backend_services",
            "skill_requirements": ["Python", "Business Logic", "Domain-Driven Design"],
            "complexity": "high",
            "estimated_hours": 8,
            "priority": "high",
            "dependencies": [f"task_{bc_name}_{service}_repositories"],
            "deliverables": [
                "domain/services.py",
                "unit tests para services"
            ]
        })

        # Task 5: Implementar API endpoints
        tasks.append({
            "id": f"task_{bc_name}_{service}_api",
            "name": f"Implementar API endpoints - {service}",
            "description": f"Criar API REST endpoints",
            "bounded_context": bc_name,
            "service": service,
            "type": "backend_api",
            "skill_requirements": ["Python", "FastAPI", "REST API"],
            "complexity": "medium",
            "estimated_hours": 6,
            "priority": "high",
            "dependencies": [f"task_{bc_name}_{service}_services"],
            "deliverables": [
                "api/v1/endpoints.py",
                "API documentation (OpenAPI)",
                "integration tests para endpoints"
            ]
        })

        # Task 6: Implementar Kafka producer/consumer
        tasks.append({
            "id": f"task_{bc_name}_{service}_kafka",
            "name": f"Implementar Kafka producer/consumer - {service}",
            "description": f"Implementar comunicação event-driven via Kafka",
            "bounded_context": bc_name,
            "service": service,
            "type": "backend_kafka",
            "skill_requirements": ["Python", "Kafka", "Event-Driven Architecture"],
            "complexity": "medium",
            "estimated_hours": 4,
            "priority": "medium",
            "dependencies": [f"task_{bc_name}_{service}_services"],
            "deliverables": [
                "infrastructure/kafka/producer.py",
                "infrastructure/kafka/consumer.py",
                "unit tests para Kafka producer/consumer"
            ]
        })

        # Task 7: Implementar caching
        tasks.append({
            "id": f"task_{bc_name}_{service}_cache",
            "name": f"Implementar caching - {service}",
            "description": f"Implementar caching com Redis",
            "bounded_context": bc_name,
            "service": service,
            "type": "backend_cache",
            "skill_requirements": ["Python", "Redis", "Caching Strategies"],
            "complexity": "low",
            "estimated_hours": 3,
            "priority": "medium",
            "dependencies": [f"task_{bc_name}_{service}_repositories"],
            "deliverables": [
                "infrastructure/cache/redis_client.py",
                "cache decorators",
                "unit tests para cache"
            ]
        })

        # Task 8: Implementar autenticação/autorização
        tasks.append({
            "id": f"task_{bc_name}_{service}_auth",
            "name": f"Implementar autenticação/autorização - {service}",
            "description": f"Implementar JWT e RBAC",
            "bounded_context": bc_name,
            "service": service,
            "type": "backend_auth",
            "skill_requirements": ["Python", "JWT", "OAuth2"],
            "complexity": "medium",
            "estimated_hours": 4,
            "priority": "high",
            "dependencies": [f"task_{bc_name}_{service}_api"],
            "deliverables": [
                "api/dependencies/auth.py",
                "JWT middleware",
                "RBAC decorators",
                "integration tests para autenticação"
            ]
        })

        return tasks
```

**Output:**
```json
{
  "id": "exec_plan_uuid",
  "project_id": "arch_plan_uuid",
  "tasks": [
    {
      "id": "task_user_management_user_service_setup",
      "name": "Setup user-service",
      "description": "Inicializar projeto user-service com estrutura base",
      "bounded_context": "User Management",
      "service": "user-service",
      "type": "backend_setup",
      "skill_requirements": ["Python", "FastAPI", "Docker"],
      "complexity": "low",
      "estimated_hours": 2,
      "priority": "high",
      "dependencies": [],
      "deliverables": [
        "Project structure",
        "requirements.txt",
        "Dockerfile",
        ".gitignore",
        "README.md"
      ],
      "status": "pending",
      "assigned_to": null,
      "started_at": null,
      "completed_at": null
    },
    {
      "id": "task_user_management_user_service_models",
      "name": "Implementar modelos de domínio - user-service",
      "description": "Criar modelos de domínio (Pydantic) para user-service",
      "bounded_context": "User Management",
      "service": "user-service",
      "type": "backend_models",
      "skill_requirements": ["Python", "Pydantic", "Domain Modeling"],
      "complexity": "medium",
      "estimated_hours": 4,
      "priority": "high",
      "dependencies": ["task_user_management_user_service_setup"],
      "deliverables": [
        "domain/models.py",
        "unit tests para modelos"
      ],
      "status": "pending",
      "assigned_to": null,
      "started_at": null,
      "completed_at": null
    },
    {
      "id": "task_user_management_user_service_repositories",
      "name": "Implementar repository layer - user-service",
      "description": "Criar repository layer para acesso a dados",
      "bounded_context": "User Management",
      "service": "user-service",
      "type": "backend_repositories",
      "skill_requirements": ["Python", "SQLAlchemy", "MongoDB"],
      "complexity": "medium",
      "estimated_hours": 6,
      "priority": "high",
      "dependencies": ["task_user_management_user_service_models"],
      "deliverables": [
        "infrastructure/repositories.py",
        "database migrations",
        "unit tests para repositories"
      ],
      "status": "pending",
      "assigned_to": null,
      "started_at": null,
      "completed_at": null
    },
    {
      "id": "task_user_management_user_service_api",
      "name": "Implementar API endpoints - user-service",
      "description": "Criar API REST endpoints",
      "bounded_context": "User Management",
      "service": "user-service",
      "type": "backend_api",
      "skill_requirements": ["Python", "FastAPI", "REST API"],
      "complexity": "medium",
      "estimated_hours": 6,
      "priority": "high",
      "dependencies": ["task_user_management_user_service_services"],
      "deliverables": [
        "api/v1/endpoints.py",
        "API documentation (OpenAPI)",
        "integration tests para endpoints"
      ],
      "status": "pending",
      "assigned_to": null,
      "started_at": null,
      "completed_at": null
    },
    {
      "id": "task_user_management_mobile_app_customer_screens",
      "name": "Implementar Customer Screens - Mobile App",
      "description": "Criar telas de cadastro, login, perfil",
      "bounded_context": "User Management",
      "service": "mobile-app",
      "type": "frontend_screens",
      "skill_requirements": ["React Native", "UI/UX", "Navigation"],
      "complexity": "medium",
      "estimated_hours": 8,
      "priority": "high",
      "dependencies": [],
      "deliverables": [
        "screens/Signup.tsx",
        "screens/Login.tsx",
        "screens/Profile.tsx",
        "navigation/UserStack.tsx",
        "components/UserForm.tsx"
      ],
      "status": "pending",
      "assigned_to": null,
      "started_at": null,
      "completed_at": null
    }
  ],
  "dependencies": [
    {
      "from": "task_user_management_user_service_models",
      "to": "task_user_management_user_service_repositories",
      "type": "finish_to_start"
    },
    {
      "from": "task_user_management_user_service_repositories",
      "to": "task_user_management_user_service_services",
      "type": "finish_to_start"
    },
    {
      "from": "task_user_management_user_service_services",
      "to": "task_user_management_user_service_api",
      "type": "finish_to_start"
    }
  ],
  "dag": {
    "nodes": [
      "task_user_management_user_service_setup",
      "task_user_management_user_service_models",
      "task_user_management_user_service_repositories",
      "task_user_management_user_service_services",
      "task_user_management_user_service_api",
      "task_user_management_mobile_app_customer_screens"
    ],
    "edges": [
      ["task_user_management_user_service_setup", "task_user_management_user_service_models"],
      ["task_user_management_user_service_models", "task_user_management_user_service_repositories"],
      ["task_user_management_user_service_repositories", "task_user_management_user_service_services"],
      ["task_user_management_user_service_services", "task_user_management_user_service_api"]
    ],
    "format": "mermaid",
    "content": "graph TD\n    A[Setup user-service] --> B[Models]\n    B --> C[Repositories]\n    C --> D[Services]\n    D --> E[API Endpoints]\n    F[Mobile App Screens]"
  },
  "milestones": [
    {
      "id": "milestone_1",
      "name": "Backend Core - User Management",
      "description": "Core backend services for user management completed",
      "tasks": [
        "task_user_management_user_service_setup",
        "task_user_management_user_service_models",
        "task_user_management_user_service_repositories",
        "task_user_management_user_service_services"
      ],
      "due_date": "2026-05-01",
      "status": "pending"
    },
    {
      "id": "milestone_2",
      "name": "API Layer - User Management",
      "description": "API endpoints for user management completed",
      "tasks": [
        "task_user_management_user_service_api"
      ],
      "due_date": "2026-05-03",
      "status": "pending"
    },
    {
      "id": "milestone_3",
      "name": "Mobile App - User Flow",
      "description": "User flow in mobile app completed",
      "tasks": [
        "task_user_management_mobile_app_customer_screens"
      ],
      "due_date": "2026-05-05",
      "status": "pending"
    }
  ],
  "checkpoints": [
    {
      "id": "checkpoint_1",
      "name": "User Service Models Validation",
      "description": "Validate Pydantic models against requirements",
      "task_id": "task_user_management_user_service_models",
      "validation_rules": [
        "All fields from requirements are present",
        "Field types match data model specification",
        "Validation rules are defined"
      ],
      "status": "pending"
    },
    {
      "id": "checkpoint_2",
      "name": "User Service API Integration",
      "description": "Test API integration with mobile app",
      "task_ids": [
        "task_user_management_user_service_api",
        "task_user_management_mobile_app_customer_screens"
      ],
      "validation_rules": [
        "Mobile app can call API endpoints",
        "Authentication works correctly",
        "Data serialization/deserialization works"
      ],
      "status": "pending"
    }
  ],
  "estimated_duration": {
    "total_hours": 60,
    "total_days": 8,
    "total_weeks": 2
  },
  "critical_path": [
    "task_user_management_user_service_setup",
    "task_user_management_user_service_models",
    "task_user_management_user_service_repositories",
    "task_user_management_user_service_services",
    "task_user_management_user_service_api"
  ],
  "parallel_tasks": [
    [
      "task_user_management_user_service_setup",
      "task_user_management_mobile_app_customer_screens"
    ],
    [
      "task_user_management_user_service_models",
      "task_user_management_mobile_app_profile_screen"
    ]
  ]
}
```

---

### 5.2 Task Dispatcher

**Responsabilidade:** Atribuir tarefas aos agentes mais apropriados baseado em skills, capacidade e especialização.

**Consumir:**
- `decomposition.generated` (ExecutionPlan do Decomposer)
- Agent registry (service-registry)

**Processamento:**
```python
# services/agentic-delegation/src/services/task_dispatcher.py

class TaskDispatcher:
    async def dispatch_tasks(self, execution_plan: ExecutionPlan) -> List[Assignment]:
        """
        Atribui tarefas aos agentes mais apropriados.

        Processo:
        1. Obter lista de agentes disponíveis do service-registry
        2. Analisar skill requirements de cada tarefa
        3. Calcular fitness score para cada agente-tarefa
        4. Atribuir tarefa ao agente com maior fitness
        5. Considerar carga atual de agentes (load balancing)
        6. Considerar especialização de agentes
        7. Gerar assignments
        """
        # Obter agentes disponíveis
        available_agents = await self._get_available_agents()

        # Calcular fitness scores
        assignments = []

        for task in execution_plan['tasks']:
            # Filtrar agentes com skills requeridas
            eligible_agents = await self._filter_eligible_agents(available_agents, task)

            # Calcular fitness scores
            fitness_scores = await self._calculate_fitness_scores(eligible_agents, task)

            # Selecionar agente ótimo
            selected_agent = await self._select_optimal_agent(fitness_scores, task)

            # Criar assignment
            assignment = {
                "id": str(uuid.uuid4()),
                "task_id": task['id'],
                "agent_id": selected_agent['id'],
                "agent_type": selected_agent['type'],
                "priority": task['priority'],
                "estimated_hours": task['estimated_hours'],
                "assigned_at": datetime.utcnow().isoformat(),
                "status": "assigned",
                "fitness_score": selected_agent['fitness_score']
            }

            assignments.append(assignment)

        # Ordenar assignments por prioridade e dependências
        assignments = await self._sort_assignments(assignments, execution_plan)

        return assignments

    async def _calculate_fitness_scores(self, agents: List[dict], task: dict) -> List[dict]:
        """
        Calcula fitness score para cada agente.

        Fitness = skill_match * 0.5 + availability * 0.3 + specialization * 0.2
        """
        fitness_scores = []

        for agent in agents:
            # Skill match
            skill_match = await self._calculate_skill_match(agent, task)

            # Availability (carga atual)
            availability = await self._calculate_availability(agent)

            # Specialization (se agente é especialista neste bounded context)
            specialization = await self._calculate_specialization(agent, task)

            # Fitness score
            fitness = (skill_match * 0.5) + (availability * 0.3) + (specialization * 0.2)

            fitness_scores.append({
                "agent": agent,
                "skill_match": skill_match,
                "availability": availability,
                "specialization": specialization,
                "fitness": fitness
            })

        return fitness_scores

    async def _calculate_skill_match(self, agent: dict, task: dict) -> float:
        """
        Calcula quanto as skills do agente correspondem aos requisitos da tarefa.
        """
        required_skills = set(task.get('skill_requirements', []))
        agent_skills = set(agent.get('skills', []))

        if not required_skills:
            return 1.0

        # Skills correspondidas
        matched_skills = required_skills.intersection(agent_skills)

        # Score = matched / required
        skill_match_score = len(matched_skills) / len(required_skills)

        # Bonus se agente tem skills extras relevantes
        extra_skills = agent_skills - required_skills
        if extra_skills:
            skill_match_score += 0.1

        return min(skill_match_score, 1.0)

    async def _calculate_availability(self, agent: dict) -> float:
        """
        Calcula disponibilidade do agente baseado na carga atual.
        """
        current_load = agent.get('current_load', 0)
        max_capacity = agent.get('max_capacity', 10)

        # Availability = 1 - (current_load / max_capacity)
        availability = 1.0 - (current_load / max_capacity)

        return max(availability, 0.0)
```

**Output:**
```json
{
  "assignments": [
    {
      "id": "assign_uuid_1",
      "task_id": "task_user_management_user_service_setup",
      "agent_id": "agent_code_forge_1",
      "agent_type": "code-forge",
      "priority": "high",
      "estimated_hours": 2,
      "assigned_at": "2026-04-15T10:00:00Z",
      "status": "assigned",
      "fitness_score": {
        "skill_match": 0.95,
        "availability": 0.8,
        "specialization": 0.9,
        "fitness": 0.895
      }
    },
    {
      "id": "assign_uuid_2",
      "task_id": "task_user_management_user_service_models",
      "agent_id": "agent_code_forge_2",
      "agent_type": "code-forge",
      "priority": "high",
      "estimated_hours": 4,
      "assigned_at": "2026-04-15T10:00:00Z",
      "status": "assigned",
      "fitness_score": {
        "skill_match": 0.9,
        "availability": 0.7,
        "specialization": 0.85,
        "fitness": 0.83
      }
    },
    {
      "id": "assign_uuid_3",
      "task_id": "task_user_management_mobile_app_customer_screens",
      "agent_id": "agent_code_forge_3",
      "agent_type": "code-forge",
      "priority": "high",
      "estimated_hours": 8,
      "assigned_at": "2026-04-15T10:00:00Z",
      "status": "assigned",
      "fitness_score": {
        "skill_match": 0.92,
        "availability": 0.9,
        "specialization": 0.8,
        "fitness": 0.88
      }
    }
  ],
  "assignment_summary": {
    "total_tasks": 150,
    "assigned_tasks": 150,
    "pending_tasks": 0,
    "agents_used": 15,
    "total_estimated_hours": 600,
    "parallelization_factor": 8,
    "estimated_completion": "2026-05-15"
  }
}
```

---

### 5.3 Agent Coordinator

**Responsabilidade:** Orquestrar múltiplos agentes trabalhando no mesmo projeto, sincronizando agentes que dependem uns dos outros e resolvendo conflitos.

**Consumir:**
- `tasks.assigned` (do Task Dispatcher)
- `agent.progress` (dos agentes)
- `agent.errors` (dos agentes)

**Processamento:**
```python
# services/agentic-delegation/src/services/agent_coordinator.py

class AgentCoordinator:
    async def coordinate_agents(self, assignments: List[Assignment]) -> CoordinationResult:
        """
        Orquestra múltiplos agentes.

        Processo:
        1. Identificar tarefas que podem ser executadas em paralelo
        2. Identificar tarefas com dependências (sequenciais)
        3. Disparar execução de agentes
        4. Monitorar progresso dos agentes
        5. Sincronizar agentes que dependem uns dos outros
        6. Detectar e resolver conflitos
        7. Gerar checkpoints quando tarefas são completadas
        """
        # Identificar tarefas paralelas vs sequenciais
        parallel_tasks = await self._identify_parallel_tasks(assignments)
        sequential_tasks = await self._identify_sequential_tasks(assignments)

        # Criar execution plan para coordenação
        coordination_plan = await self._create_coordination_plan(parallel_tasks, sequential_tasks)

        # Executar coordenação
        result = await self._execute_coordination(coordination_plan)

        return result

    async def _identify_parallel_tasks(self, assignments: List[Assignment]) -> List[List[Assignment]]:
        """
        Identifica tarefas que podem ser executadas em paralelo.
        """
        # Tarefas sem dependências podem ser executadas em paralelo
        tasks_without_deps = [a for a in assignments if len(a.get('dependencies', [])) == 0]

        # Agrupar por bounded context e tipo
        parallel_groups = {}
        for task in tasks_without_deps:
            key = f"{task['bounded_context']}_{task['type']}"
            if key not in parallel_groups:
                parallel_groups[key] = []
            parallel_groups[key].append(task)

        return list(parallel_groups.values())

    async def _resolve_conflict(self, conflict: dict) -> Resolution:
        """
        Resolve conflitos entre agentes.

        Tipos de conflitos:
        1. Schema mismatch (API models diferentes)
        2. Dependency version conflict
        3. Resource conflict (porta, endpoint path)
        4. Logic conflict (regras de negócio contraditórias)
        """
        conflict_type = conflict['type']

        if conflict_type == 'schema_mismatch':
            resolution = await self._resolve_schema_mismatch(conflict)
        elif conflict_type == 'dependency_version_conflict':
            resolution = await self._resolve_dependency_version_conflict(conflict)
        elif conflict_type == 'resource_conflict':
            resolution = await self._resolve_resource_conflict(conflict)
        elif conflict_type == 'logic_conflict':
            resolution = await self._resolve_logic_conflict(conflict)
        else:
            resolution = {
                "status": "escalated",
                "message": f"Conflict type {conflict_type} requires human intervention",
                "escalated_to": "Orchestrator Dynamic",
                "escalated_at": datetime.utcnow().isoformat()
            }

        return resolution
```

**Output:**
```json
{
  "coordination_id": "coord_uuid",
  "status": "in_progress",
  "parallel_groups": [
    {
      "group_id": "group_1",
      "tasks": [
        "task_user_management_user_service_setup",
        "task_restaurant_catalog_restaurant_service_setup",
        "task_order_management_order_service_setup"
      ],
      "agents": [
        "agent_code_forge_1",
        "agent_code_forge_2",
        "agent_code_forge_3"
      ],
      "status": "executing",
      "started_at": "2026-04-15T10:00:00Z"
    }
  ],
  "sequential_groups": [
    {
      "group_id": "group_seq_1",
      "sequence": [
        {
          "task": "task_user_management_user_service_setup",
          "depends_on": []
        },
        {
          "task": "task_user_management_user_service_models",
          "depends_on": ["task_user_management_user_service_setup"]
        },
        {
          "task": "task_user_management_user_service_repositories",
          "depends_on": ["task_user_management_user_service_models"]
        }
      ],
      "status": "pending"
    }
  ],
  "conflicts": [
    {
      "id": "conflict_1",
      "type": "schema_mismatch",
      "severity": "high",
      "description": "User model in user-service differs from Order model in order-service",
      "affected_agents": [
        "agent_code_forge_1",
        "agent_code_forge_2"
      ],
      "affected_tasks": [
        "task_user_management_user_service_models",
        "task_order_management_order_service_models"
      ],
      "detected_at": "2026-04-15T11:30:00Z",
      "resolution": {
        "status": "resolved",
        "resolution_type": "schema_unification",
        "resolution": "Unified User model via shared library (neural_hive_domain)",
        "resolved_at": "2026-04-15T11:45:00Z"
      }
    }
  ],
  "checkpoints": [
    {
      "id": "checkpoint_1",
      "name": "Backend Core - User Management",
      "status": "passed",
      "validated_at": "2026-04-15T12:00:00Z",
      "validation_results": {
        "models_valid": true,
        "repositories_valid": true,
        "services_valid": true
      }
    }
  ]
}
```

---

### 5.4 Progress Tracker

**Responsabilidade:** Rastrear progresso consolidado de todos os agentes, fornecer visibilidade para stakeholders e detectar bottlenecks.

**Consumir:**
- `agent.progress` (de todos os agentes)
- `agent.completed` (tarefas completadas)
- `agent.errors` (erros dos agentes)

**Processamento:**
```python
# services/agentic-delegation/src/services/progress_tracker.py

class ProgressTracker:
    async def track_progress(self, execution_plan_id: str) -> ProgressReport:
        """
        Rastreia progresso consolidado de todos os agentes.

        Processo:
        1. Agregar progresso de todos os agentes
        2. Calcular progresso global (% completo)
        3. Detectar bottlenecks e bloqueios
        4. Identificar milestones completados
        5. Identificar checkpoints validados
        6. Gerar visibilidade para stakeholders
        """
        # Agregar progresso de agentes
        agent_progress = await self._aggregate_agent_progress(execution_plan_id)

        # Calcular progresso global
        global_progress = await self._calculate_global_progress(agent_progress)

        # Detectar bottlenecks
        bottlenecks = await self._detect_bottlenecks(agent_progress)

        # Identificar milestones completados
        completed_milestones = await self._get_completed_milestones(execution_plan_id)

        # Identificar checkpoints validados
        validated_checkpoints = await self._get_validated_checkpoints(execution_plan_id)

        # Gerar visibilidade
        visibility = await self._generate_visibility(global_progress, bottlenecks, completed_milestones)

        return {
            "execution_plan_id": execution_plan_id,
            "global_progress": global_progress,
            "agent_progress": agent_progress,
            "bottlenecks": bottlenecks,
            "completed_milestones": completed_milestones,
            "validated_checkpoints": validated_checkpoints,
            "visibility": visibility,
            "updated_at": datetime.utcnow().isoformat()
        }
```

**Output:**
```json
{
  "execution_plan_id": "exec_plan_uuid",
  "global_progress": {
    "total_tasks": 150,
    "completed_tasks": 75,
    "in_progress_tasks": 50,
    "pending_tasks": 25,
    "failed_tasks": 0,
    "progress_percentage": 50.0,
    "estimated_completion": "2026-05-15",
    "estimated_remaining_hours": 300
  },
  "agent_progress": [
    {
      "agent_id": "agent_code_forge_1",
      "agent_type": "code-forge",
      "assigned_tasks": 10,
      "completed_tasks": 8,
      "in_progress_tasks": 2,
      "progress_percentage": 80.0,
      "current_task": "task_user_management_user_service_cache",
      "last_updated": "2026-04-15T14:00:00Z"
    },
    {
      "agent_id": "agent_code_forge_2",
      "agent_type": "code-forge",
      "assigned_tasks": 12,
      "completed_tasks": 6,
      "in_progress_tasks": 6,
      "progress_percentage": 50.0,
      "current_task": "task_order_management_order_service_api",
      "last_updated": "2026-04-15T14:00:00Z"
    }
  ],
  "bottlenecks": [
    {
      "id": "bottleneck_1",
      "type": "agent_unavailable",
      "severity": "medium",
      "description": "agent_code_forge_5 is currently overloaded",
      "affected_tasks": [
        "task_delivery_management_delivery_service_api"
      ],
      "estimated_delay": "2 hours",
      "resolution": "Task reassigned to agent_code_forge_6"
    },
    {
      "id": "bottleneck_2",
      "type": "dependency_delay",
      "severity": "high",
      "description": "task_order_management_order_service_api blocked by payment-service API completion",
      "affected_tasks": [
        "task_order_management_order_service_tests"
      ],
      "estimated_delay": "4 hours",
      "resolution": "Waiting for payment-service API completion"
    }
  ],
  "completed_milestones": [
    {
      "id": "milestone_1",
      "name": "Backend Core - User Management",
      "completed_at": "2026-04-15T12:00:00Z",
      "actual_duration": "24 hours",
      "estimated_duration": "32 hours",
      "status": "on_track"
    }
  ],
  "validated_checkpoints": [
    {
      "id": "checkpoint_1",
      "name": "User Service Models Validation",
      "validated_at": "2026-04-15T11:30:00Z",
      "validation_results": {
        "all_fields_present": true,
        "field_types_match": true,
        "validation_rules_defined": true
      },
      "status": "passed"
    }
  ],
  "visibility": {
    "stakeholder_view": {
      "summary": "Project is 50% complete, on track for estimated completion on 2026-05-15",
      "health": "green",
      "risk_level": "low",
      "next_milestone": "API Layer - User Management (2026-05-03)"
    },
    "team_view": {
      "current_blockers": 2,
      "urgent_tasks": 5,
      "next_actions": [
        "Complete payment-service API (task_payment_management_payment_service_api)",
        "Reassign task_delivery_management_delivery_service_api to agent_code_forge_6",
        "Test integration between user-service and mobile-app"
      ]
    }
  }
}
```

---

### 5.5 Conflict Resolver

**Responsabilidade:** Resolver conflitos entre agentes automaticamente quando possível, ou escalar para intervenção humana.

**Consumir:**
- `agent.conflicts` (detecção de conflitos)

**Processamento:**
```python
# services/agentic-delegation/src/services/conflict_resolver.py

class ConflictResolver:
    async def resolve_conflicts(self, conflicts: List[dict]) -> List[Resolution]:
        """
        Resolve conflitos entre agentes.

        Tipos de conflitos:
        1. Schema mismatch
        2. Dependency version conflict
        3. Resource conflict
        4. Logic conflict
        5. Implementation divergence
        """
        resolutions = []

        for conflict in conflicts:
            resolution = await self._resolve_single_conflict(conflict)
            resolutions.append(resolution)

        return resolutions

    async def _resolve_schema_mismatch(self, conflict: dict) -> dict:
        """
        Resolve schema mismatch entre serviços.

        Estratégias:
        1. Unificar schema via shared library
        2. Criar adapter layer
        3. Renegociar schema entre agentes
        """
        # Analisar mismatch
        mismatch_details = conflict.get('details', {})

        # Estratégia 1: Unificar schema
        if mismatch_details['difference_type'] == 'field_name':
            resolution = {
                "status": "resolved",
                "resolution_type": "schema_unification",
                "resolution": "Unified schema via shared library (neural_hive_domain)",
                "action_required": "Both agents must import unified User model",
                "assigned_to": ["agent_1", "agent_2"],
                "due_date": "2026-04-15T16:00:00Z"
            }
        # Estratégia 2: Adapter layer
        elif mismatch_details['difference_type'] == 'structural':
            resolution = {
                "status": "resolved",
                "resolution_type": "adapter_layer",
                "resolution": "Create adapter layer to translate between schemas",
                "action_required": "Create UserAdapter in order-service",
                "assigned_to": "agent_2",
                "due_date": "2026-04-15T18:00:00Z"
            }

        return resolution
```

---

### Eventos Kafka Produzidos pelo Agentic Delegation System

```yaml
decomposition.generated:
  - Producer: Decomposer
  - Consumer: Task Dispatcher, Orchestrator Dynamic
  - Payload: { id, project_id, tasks: [...], dependencies: [...], dag: {...}, milestones: [...], checkpoints: [...] }

tasks.assigned:
  - Producer: Task Dispatcher
  - Consumer: Agent Coordinator, Progress Tracker
  - Payload: { id, task_id, agent_id, agent_type, priority, estimated_hours, fitness_score }

agent.progress:
  - Producer: Agent Coordinator
  - Consumer: Progress Tracker, Orchestrator Dynamic
  - Payload: { id, agent_id, task_id, status, progress_percentage, current_step, eta }

agent.completed:
  - Producer: Agent Coordinator
  - Consumer: Task Dispatcher, Progress Tracker
  - Payload: { id, agent_id, task_id, status, completed_at, deliverables }

agent.errors:
  - Producer: Agent Coordinator
  - Consumer: Conflict Resolver, Progress Tracker
  - Payload: { id, agent_id, task_id, error_type, error_message, stack_trace }

conflicts.detected:
  - Producer: Agent Coordinator
  - Consumer: Conflict Resolver
  - Payload: { id, type, severity, description, affected_agents, affected_tasks }

conflicts.resolved:
  - Producer: Conflict Resolver
  - Consumer: Agent Coordinator, Orchestrator Dynamic
  - Payload: { id, conflict_id, status, resolution_type, resolution, assigned_to, due_date }

delegation.progress:
  - Producer: Progress Tracker
  - Consumer: Orchestrator Dynamic, Monitoring
  - Payload: { id, execution_plan_id, global_progress: {...}, bottlenecks: [...], visibility: {...} }

delegation.completed:
  - Producer: Progress Tracker
  - Consumer: Orchestrator Dynamic, Code Forge
  - Payload: { id, execution_plan_id, status, completed_at, summary }
```

---

## Conclusão da Parte 3

O Agentic Delegation System é o terceiro componente crítico do Fluxo G, consumindo os artefatos do Architectural Planning System e gerenciando a delegação de tarefas para múltiplos agentes especializados.

Este sistema produz 8 tipos principais de eventos Kafka que alimentam os sistemas downstream e stakeholders:
1. `decomposition.generated` → Task Dispatcher, Orchestrator Dynamic
2. `tasks.assigned` → Agent Coordinator, Progress Tracker
3. `agent.progress` → Progress Tracker, Orchestrator Dynamic
4. `agent.completed` → Task Dispatcher, Progress Tracker
5. `agent.errors` → Conflict Resolver, Progress Tracker
6. `conflicts.detected` → Conflict Resolver
7. `conflicts.resolved` → Agent Coordinator, Orchestrator Dynamic
8. `delegation.progress` → Orchestrator Dynamic, Monitoring
9. `delegation.completed` → Orchestrator Dynamic, Code Forge

O Agentic Delegation System permite:
- **Decomposição inteligente** de planos arquiteturais em subtarefas delegáveis
- **Task assignment otimizado** baseado em skills, capacidade e especialização
- **Coordenação multi-agente** com sincronização de dependências
- **Resolução de conflitos** automática entre agentes
- **Progress tracking consolidado** com visibilidade para stakeholders

---

## 💻 Passo 6: Code Forge (EXISTENTE - 8005 - MELHORADO)

### Descrição Geral

Consome os assignments do Agentic Delegation System e gera código e IaC para todos os componentes do sistema (frontend, backend, databases, etc.).

### Estado Atual do Code Forge

O Code Forge já existe no NHM e é 100% funcional. Ele foi desenhado para gerar código e IaC com múltiplos métodos de geração.

### Capacidades Atuais Implementadas

| Capacidade | Status | Descrição |
|------------|--------|-----------|
| **Template Selector** | ✅ 100% | Seleção inteligente de templates com cache Redis e algoritmo genético |
| **Code Composer** | ✅ 100% | 4 métodos de geração: LLM, HYBRID, HEURISTIC, TEMPLATE |
| **IaC Generator** | ✅ 100% | Terraform, Helm, Kubernetes, CloudFormation, AWS CDK, Azure Bicep |
| **Dockerfile Generator** | ✅ 100% | Geração de Dockerfiles para 6 linguagens |
| **LLM Client** | ✅ 100% | Suporte a 3 providers: OpenAI, Anthropic, Ollama |
| **MCP Integration** | ✅ 100% | Algoritmo genético para seleção de ferramentas |
| **RAG Context** | ✅ 100% | Contexto rico via Analyst Agents + embeddings |
| **Template Cache** | ✅ 100% | Cache em Redis para templates usados frequentemente |
| **Template Versionamento** | ✅ 100% | Versionamento via Git tags |
| **Code Review Integration** | ✅ 100% | Integração com GitHub/GitLab PRs/MRs |
| **Test Runner** | ✅ 100% | Execução de testes existentes |
| **Validation Service** | ✅ 100% | Validação de código gerado |
| **Pipeline Engine** | ✅ 100% | Orquestração de pipeline completo |
| **Build Metrics** | ✅ 100% | Métricas de build e performance |
| **Approval Gate** | ✅ 100% | Gate de aprovação manual/automático |
| **Container Builder** | ✅ 100% | Build de containers via Kaniko/BuildKit |
| **Packager** | ✅ 100% | Empacotamento de artefatos |
| **SBOM Generator** | ✅ 100% | Software Bill of Materials (Trivy) |
| **License Validator** | ✅ 100% | Validação de licenças de dependências |

### Portas e Endpoints

- **Porta API REST:** 8005
- **Health Check:** `/health`
- **Metrics:** `/metrics`
- **Endpoints:**
  - `POST /api/v1/pipeline/execute` - Executar pipeline de geração
  - `POST /api/v1/code/compose` - Compor código
  - `POST /api/v1/iac/generate` - Gerar IaC
  - `POST /api/v1/dockerfile/generate` - Gerar Dockerfile
  - `GET /api/v1/templates` - Listar templates disponíveis
  - `GET /api/v1/templates/{id}` - Obter template específico
  - `GET /api/v1/artifacts/{id}` - Obter artefato gerado

---

### 6.1 Integração com Agentic Delegation System

**Consumir:**
- `tasks.assigned` (do Agentic Delegation System)
- `architectural.plan` (do Architectural Planning System)
- `system_design.generated` (do Architectural Planning System)
- `tech_stack.selected` (do Architectural Planning System)
- `data_models.generated` (do Requirements Engineering System)
- `api_designs.generated` (do Requirements Engineering System)
- `ui_ux_designs.generated` (do Requirements Engineering System)

**Fluxo de Integração:**
```python
# services/code-forge/src/services/delegation_integrator.py

class DelegationIntegrator:
    """
    Integra o Code Forge com o Agentic Delegation System.
    """

    def __init__(
        self,
        code_composer: CodeComposer,
        template_selector: TemplateSelector,
        iac_generator: IaCGenerator,
        dockerfile_generator: DockerfileGenerator,
    ):
        self.code_composer = code_composer
        self.template_selector = template_selector
        self.iac_generator = iac_generator
        self.dockerfile_generator = dockerfile_generator

    async def process_task_assignment(self, assignment: dict) -> dict:
        """
        Processa um task assignment do Agentic Delegation System.

        Processo:
        1. Analisar o tipo de tarefa (backend, frontend, database, iac, etc.)
        2. Buscar artefatos relevantes dos sistemas upstream
        3. Selecionar método de geração apropriado
        4. Gerar código/IaC
        5. Validar código gerado
        6. Publicar evento de task completion
        """
        task_type = assignment.get('type')
        task_id = assignment.get('task_id')
        service = assignment.get('service')
        bounded_context = assignment.get('bounded_context')

        logger.info("processing_task_assignment", task_id=task_id, task_type=task_type)

        # Buscar artefatos relevantes
        artifacts = await self._fetch_relevant_artifacts(assignment)

        # Criar contexto de pipeline
        context = await self._create_pipeline_context(assignment, artifacts)

        # Selecionar método de geração
        generation_method = await self._select_generation_method(task_type, context)

        # Gerar código/IaC
        if task_type == 'backend_code':
            result = await self._generate_backend_code(context, generation_method)
        elif task_type == 'frontend_code':
            result = await self._generate_frontend_code(context, generation_method)
        elif task_type == 'database_schema':
            result = await self._generate_database_schema(context)
        elif task_type == 'iac':
            result = await self._generate_iac(context)
        elif task_type == 'dockerfile':
            result = await self._generate_dockerfile(context)
        else:
            raise ValueError(f"Unknown task type: {task_type}")

        # Validar código gerado
        validation_result = await self._validate_generated_code(result)

        # Publicar evento de task completion
        await self._publish_task_completion(assignment, result, validation_result)

        return {
            "task_id": task_id,
            "status": "completed",
            "result": result,
            "validation": validation_result,
            "generated_at": datetime.utcnow().isoformat()
        }

    async def _fetch_relevant_artifacts(self, assignment: dict) -> dict:
        """
        Busca artefatos relevantes dos sistemas upstream.
        """
        artifacts = {}

        # Buscar arquitetura
        artifacts['architecture'] = await self._fetch_artifact(
            'architectural.plan',
            assignment.get('project_id')
        )

        # Buscar system design
        artifacts['system_design'] = await self._fetch_artifact(
            'system_design.generated',
            assignment.get('project_id')
        )

        # Buscar tech stack
        artifacts['tech_stack'] = await self._fetch_artifact(
            'tech_stack.selected',
            assignment.get('project_id')
        )

        # Buscar data models (se backend ou database)
        if assignment.get('type') in ['backend_code', 'database_schema']:
            artifacts['data_models'] = await self._fetch_artifact(
                'data_models.generated',
                assignment.get('project_id')
            )

        # Buscar API design (se backend ou frontend)
        if assignment.get('type') in ['backend_code', 'frontend_code']:
            artifacts['api_design'] = await self._fetch_artifact(
                'api_designs.generated',
                assignment.get('project_id')
            )

        # Buscar UI/UX design (se frontend)
        if assignment.get('type') == 'frontend_code':
            artifacts['ui_ux_design'] = await self._fetch_artifact(
                'ui_ux_designs.generated',
                assignment.get('project_id')
            )

        return artifacts
```

---

### 6.2 Template Selector com RAG Context

**Responsabilidade:** Selecionar template ótimo baseado em critérios do assignment e contexto RAG.

**Processamento Aprimorado:**
```python
# services/code-forge/src/services/template_selector.py

class TemplateSelector:
    async def select_with_delegation_context(self, assignment: dict, artifacts: dict) -> Template:
        """
        Seleciona template com contexto do Agentic Delegation System.

        Processo:
        1. Analisar tipo de tarefa e skill requirements
        2. Buscar templates similares via RAG (embeddings)
        3. Calcular fitness score de cada template
        4. Selecionar template ótimo
        5. Considerar histórico de sucesso por bounded context
        """
        # Extrair critérios do assignment
        task_type = assignment.get('type')
        bounded_context = assignment.get('bounded_context')
        service = assignment.get('service')
        skill_requirements = assignment.get('skill_requirements', [])

        # Buscar tech stack
        tech_stack = artifacts.get('tech_stack', {})
        language = await self._determine_language(task_type, bounded_context, tech_stack)

        # Critérios de seleção
        criteria = {
            'type': task_type,
            'language': language,
            'bounded_context': bounded_context,
            'service': service,
            'skill_requirements': skill_requirements
        }

        # Buscar em cache
        cache_key = self._generate_cache_key(criteria)
        cached_template = await self.redis_client.get_cached_template(cache_key)

        if cached_template:
            logger.info("template_cache_hit", template_id=cached_template.template_id)
            return cached_template

        # Buscar templates similares via RAG (embeddings)
        similar_templates = await self._search_similar_templates(criteria)

        # Calcular fitness scores
        template_scores = await self._calculate_template_scores(
            similar_templates,
            criteria,
            artifacts
        )

        # Selecionar template ótimo
        selected_template = max(template_scores, key=lambda x: x['fitness_score'])

        # Cache template
        await self.redis_client.cache_template(cache_key, selected_template)

        logger.info(
            "template_selected",
            template_id=selected_template['template'].template_id,
            fitness_score=selected_template['fitness_score']
        )

        return selected_template['template']

    async def _search_similar_templates(self, criteria: dict) -> List[Template]:
        """
        Busca templates similares via RAG (embeddings).
        """
        # Gerar embedding dos critérios
        criteria_text = self._criteria_to_text(criteria)
        embedding = await self.analyst_client.get_embedding(criteria_text)

        # Buscar templates similares
        similar_templates = await self.analyst_client.search_similar_code(
            query_embedding=embedding,
            language=criteria.get('language'),
            top_k=10,
            threshold=0.75
        )

        return similar_templates

    async def _calculate_template_scores(self, templates: List[Template], criteria: dict, artifacts: dict) -> List[dict]:
        """
        Calcula fitness score para cada template.

        Fitness = match_score * 0.4 + quality_score * 0.3 + usage_score * 0.2 + context_score * 0.1
        """
        template_scores = []

        for template in templates:
            # Match score (matching de critérios)
            match_score = await self._calculate_match_score(template, criteria)

            # Quality score (qualidade do template baseado em métricas)
            quality_score = await self._calculate_quality_score(template)

            # Usage score (frequência de uso e taxa de sucesso)
            usage_score = await self._calculate_usage_score(template)

            # Context score (alinhamento com bounded context e requirements)
            context_score = await self._calculate_context_score(template, artifacts)

            # Fitness score
            fitness = (
                match_score * 0.4 +
                quality_score * 0.3 +
                usage_score * 0.2 +
                context_score * 0.1
            )

            template_scores.append({
                'template': template,
                'match_score': match_score,
                'quality_score': quality_score,
                'usage_score': usage_score,
                'context_score': context_score,
                'fitness_score': fitness
            })

        return template_scores
```

---

### 6.3 Code Composer com RAG Context

**Responsabilidade:** Compor código com contexto RAG rico dos sistemas upstream.

**Processamento Aprimorado:**
```python
# services/code-forge/src/services/code_composer.py

class CodeComposer:
    async def compose_with_rag_context(self, context: dict, generation_method: str) -> dict:
        """
        Compoem código com contexto RAG rico.

        Processo:
        1. Construir prompt com contexto RAG
        2. Adicionar contexto de similar_projects do Knowledge Graph
        3. Adicionar contexto de design patterns e best practices
        4. Gerar código via LLM/HYBRID/HEURISTIC/TEMPLATE
        5. Validar código gerado
        6. Gerar artefatos adicionais (tests, docs, etc.)
        """
        # Construir contexto RAG
        rag_context = await self._build_rag_context(context)

        # Adicionar contexto de similar_projects
        similar_projects = await self._get_similar_projects(context)
        rag_context['similar_projects'] = similar_projects

        # Adicionar contexto de design patterns
        design_patterns = await self._get_design_patterns(context)
        rag_context['design_patterns'] = design_patterns

        # Adicionar contexto de best practices
        best_practices = await self._get_best_practices(context)
        rag_context['best_practices'] = best_practices

        # Gerar código
        if generation_method == 'LLM':
            code_content = await self._generate_via_llm(context, rag_context)
        elif generation_method == 'HYBRID':
            code_content = await self._generate_hybrid(context, rag_context)
        elif generation_method == 'HEURISTIC':
            code_content = await self._generate_heuristic(context)
        else:
            code_content = await self._generate_template(context)

        # Validar código gerado
        validation_result = await self._validate_code(code_content, context)

        # Gerar artefatos adicionais
        additional_artifacts = await self._generate_additional_artifacts(
            code_content,
            context,
            validation_result
        )

        return {
            "code": code_content,
            "validation": validation_result,
            "additional_artifacts": additional_artifacts,
            "rag_context_used": rag_context,
            "generation_method": generation_method,
            "generated_at": datetime.utcnow().isoformat()
        }

    async def _build_rag_context(self, context: dict) -> dict:
        """
        Constrói contexto RAG a partir dos artefatos upstream.
        """
        rag_context = {}

        # Contexto de data models
        data_models = context.get('artifacts', {}).get('data_models', {})
        if data_models:
            rag_context['data_models'] = await self._extract_data_model_context(data_models)

        # Contexto de API design
        api_design = context.get('artifacts', {}).get('api_design', {})
        if api_design:
            rag_context['api_design'] = await self._extract_api_design_context(api_design)

        # Contexto de arquitetura
        architecture = context.get('artifacts', {}).get('architecture', {})
        if architecture:
            rag_context['architecture'] = await self._extract_architecture_context(architecture)

        # Contexto de system design
        system_design = context.get('artifacts', {}).get('system_design', {})
        if system_design:
            rag_context['system_design'] = await self._extract_system_design_context(system_design)

        # Contexto de tech stack
        tech_stack = context.get('artifacts', {}).get('tech_stack', {})
        if tech_stack:
            rag_context['tech_stack'] = await self._extract_tech_stack_context(tech_stack)

        # Contexto de UI/UX design (se frontend)
        ui_ux_design = context.get('artifacts', {}).get('ui_ux_design', {})
        if ui_ux_design:
            rag_context['ui_ux_design'] = await self._extract_ui_ux_design_context(ui_ux_design)

        return rag_context

    async def _get_similar_projects(self, context: dict) -> List[dict]:
        """
        Busca projetos similares do Knowledge Graph.
        """
        # Buscar do Knowledge Graph (via RAG)
        similar_projects = await self.analyst_client.search_similar_projects(
            query=context.get('assignment', {}).get('service', ''),
            bounded_context=context.get('assignment', {}).get('bounded_context', ''),
            top_k=3
        )

        return similar_projects

    async def _get_design_patterns(self, context: dict) -> List[dict]:
        """
        Busca design patterns relevantes do Knowledge Graph.
        """
        # Buscar do Knowledge Graph
        design_patterns = await self.analyst_client.search_design_patterns(
            bounded_context=context.get('assignment', {}).get('bounded_context', ''),
            task_type=context.get('assignment', {}).get('type', ''),
            top_k=5
        )

        return design_patterns

    async def _get_best_practices(self, context: dict) -> List[dict]:
        """
        Busca best practices relevantes do Knowledge Graph.
        """
        # Buscar do Knowledge Graph
        best_practices = await self.analyst_client.search_best_practices(
            tech_stack=context.get('artifacts', {}).get('tech_stack', {}),
            bounded_context=context.get('assignment', {}).get('bounded_context', ''),
            top_k=5
        )

        return best_practices
```

---

### 6.4 IaC Generator com System Design

**Responsabilidade:** Gerar IaC com base no System Design detalhado.

**Processamento Aprimorado:**
```python
# services/code-forge/src/services/iac_generator.py

class IaCGenerator:
    async def generate_with_system_design(self, system_design: dict) -> dict:
        """
        Gera IaC com base no System Design detalhado.

        Processo:
        1. Analisar system design (frontend, backend, databases, cache, message queue)
        2. Gerar IaC para backend services (Kubernetes deployments, services, configmaps)
        3. Gerar IaC para databases (PostgreSQL, MongoDB)
        4. Gerar IaC para cache (Redis)
        5. Gerar IaC para message queue (Kafka)
        6. Gerar IaC para API Gateway
        7. Gerar IaC para observability (Prometheus, Grafana, Jaeger)
        8. Gerar Helm Charts
        """
        iac_artifacts = {}

        # Gerar IaC para backend services
        backend_design = system_design.get('backend_design', {})
        iac_artifacts['backend'] = await self._generate_backend_iac(backend_design)

        # Gerar IaC para databases
        data_layer_design = system_design.get('data_layer_design', {})
        iac_artifacts['databases'] = await self._generate_databases_iac(data_layer_design)

        # Gerar IaC para cache
        cache_design = data_layer_design.get('cache', {})
        iac_artifacts['cache'] = await self._generate_cache_iac(cache_design)

        # Gerar IaC para message queue
        message_queue = data_layer_design.get('message_queue', {})
        iac_artifacts['message_queue'] = await self._generate_message_queue_iac(message_queue)

        # Gerar IaC para API Gateway
        api_gateway = backend_design.get('api_gateway', {})
        iac_artifacts['api_gateway'] = await self._generate_api_gateway_iac(api_gateway)

        # Gerar IaC para observability
        observability = backend_design.get('observability', {})
        iac_artifacts['observability'] = await self._generate_observability_iac(observability)

        # Gerar Helm Charts
        iac_artifacts['helm_charts'] = await self._generate_helm_charts(system_design)

        # Gerar Terraform modules
        iac_artifacts['terraform'] = await self._generate_terraform_modules(system_design)

        return {
            "iac_artifacts": iac_artifacts,
            "generated_at": datetime.utcnow().isoformat()
        }

    async def _generate_backend_iac(self, backend_design: dict) -> dict:
        """
        Gera IaC para backend services.
        """
        services = backend_design.get('services', [])

        k8s_artifacts = []

        for service in services:
            service_name = service.get('name')
            port = service.get('port')
            language = service.get('language')
            framework = service.get('framework')

            # Gerar Kubernetes Deployment
            deployment = await self._generate_kubernetes_deployment(service)

            # Gerar Kubernetes Service
            k8s_service = await self._generate_kubernetes_service(service)

            # Gerar Kubernetes ConfigMap
            configmap = await self._generate_kubernetes_configmap(service)

            # Gerar Kubernetes Secret
            secret = await self._generate_kubernetes_secret(service)

            k8s_artifacts.append({
                "service_name": service_name,
                "deployment": deployment,
                "service": k8s_service,
                "configmap": configmap,
                "secret": secret
            })

        return {
            "kubernetes": k8s_artifacts,
            "type": "kubernetes"
        }

    async def _generate_kubernetes_deployment(self, service: dict) -> str:
        """
        Gera Kubernetes Deployment para um serviço.
        """
        service_name = service.get('name')
        port = service.get('port')
        replicas = 3  # Padrão para alta disponibilidade

        deployment_yaml = f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {service_name}
  labels:
    app: {service_name}
spec:
  replicas: {replicas}
  selector:
    matchLabels:
      app: {service_name}
  template:
    metadata:
      labels:
        app: {service_name}
    spec:
      containers:
      - name: {service_name}
        image: ghcr.io/neural-hive-mind/{service_name}:latest
        ports:
        - containerPort: {port}
        env:
        - name: PORT
          value: "{port}"
        - name: ENVIRONMENT
          valueFrom:
            configMapKeyRef:
              name: {service_name}-config
              key: ENVIRONMENT
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: {service_name}-secret
              key: DATABASE_URL
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: {port}
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: {port}
          initialDelaySeconds: 5
          periodSeconds: 5
"""

        return deployment_yaml
```

---

### 6.5 Exemplo de Execução Completa

**Input:**
```json
{
  "assignment": {
    "id": "assign_uuid_1",
    "task_id": "task_user_management_user_service_models",
    "agent_id": "agent_code_forge_1",
    "agent_type": "code-forge",
    "priority": "high",
    "estimated_hours": 4,
    "bounded_context": "User Management",
    "service": "user-service",
    "type": "backend_code",
    "skill_requirements": ["Python", "Pydantic", "Domain Modeling"],
    "dependencies": ["task_user_management_user_service_setup"]
  },
  "artifacts": {
    "architecture": {
      "architecture_type": "microservices",
      "bounded_contexts": [...]
    },
    "system_design": {
      "backend_design": {
        "services": [...]
      }
    },
    "tech_stack": {
      "backend": {
        "language": "Python",
        "framework": "FastAPI"
      }
    },
    "data_models": {
      "entities": [
        {
          "name": "User",
          "attributes": [...]
        }
      ]
    }
  }
}
```

**Output:**
```json
{
  "task_id": "task_user_management_user_service_models",
  "status": "completed",
  "result": {
    "code": "# domain/models.py\nfrom pydantic import BaseModel, EmailStr, Field\nfrom datetime import datetime\nfrom typing import Optional\nimport uuid\n\nclass UserBase(BaseModel):\n    \"\"\"Base model for User\"\"\"\n    email: EmailStr\n    name: str = Field(..., min_length=2, max_length=255)\n\nclass UserCreate(UserBase):\n    \"\"\"Model for creating a user\"\"\"\n    password: str = Field(..., min_length=8)\n\nclass User(UserBase):\n    \"\"\"User model\"\"\"\n    id: UUID = Field(default_factory=uuid.uuid4)\n    created_at: datetime = Field(default_factory=datetime.utcnow)\n    updated_at: datetime = Field(default_factory=datetime.utcnow)\n    is_active: bool = True\n\nclass UserInDB(User):\n    \"\"\"User model as stored in database\"\"\"\n    password_hash: str\n",
    "validation": {
      "is_valid": true,
      "errors": [],
      "warnings": [],
      "lint_score": 9.5,
      "type_check_passed": true
    },
    "additional_artifacts": {
      "unit_tests": "# tests/test_models.py\nimport pytest\nfrom domain.models import User, UserCreate\n\ndef test_user_create():\n    user_data = {\n        \"email\": \"test@example.com\",\n        \"name\": \"Test User\",\n        \"password\": \"password123\"\n    }\n    user = UserCreate(**user_data)\n    assert user.email == \"test@example.com\"\n    assert user.name == \"Test User\"\n    assert len(user.password) >= 8\n",
      "docstrings": "Docstrings adicionadas a todos os modelos com Google style",
      "type_hints": "Type hints adicionados a todos os campos e métodos"
    },
    "rag_context_used": {
      "data_models": ["User entity from data_models.generated"],
      "architecture": ["Microservices architecture"],
      "tech_stack": ["Python", "FastAPI", "Pydantic"],
      "similar_projects": ["iFood user-service", "Uber user-profile-service"],
      "design_patterns": ["Repository Pattern", "Domain-Driven Design"],
      "best_practices": ["Pydantic for validation", "UUID for primary keys"]
    },
    "generation_method": "HYBRID",
    "generated_at": "2026-04-15T14:30:00Z"
  }
}
```

---

### Eventos Kafka Produzidos pelo Code Forge

```yaml
code.generated:
  - Producer: Code Forge
  - Consumer: Test Generation System, Documentation Generation System, Software Engineering Pipeline
  - Payload: { id, task_id, code, validation, additional_artifacts, rag_context_used, generation_method, generated_at }

iac.generated:
  - Producer: Code Forge
  - Consumer: Software Engineering Pipeline
  - Payload: { id, task_id, iac_artifacts, type, generated_at }

tests.required:
  - Producer: Code Forge
  - Consumer: Test Generation System
  - Payload: { id, task_id, code, test_requirements, coverage_threshold }

artifacts.created:
  - Producer: Code Forge
  - Consumer: Software Engineering Pipeline, Monitoring
  - Payload: { id, task_id, artifacts: [...], generated_at }

template.used:
  - Producer: Template Selector
  - Consumer: Monitoring, Analytics
  - Payload: { id, template_id, fitness_score, generation_method, rag_context_used }
```

---

## Conclusão da Parte 4

O Code Forge é um componente maduro e funcional que já existe no NHM. A integração com os novos sistemas do Fluxo G (Agentic Delegation System, Architectural Planning System, Requirements Engineering System) permite que o Code Forge gere código e IaC com contexto rico e inteligente.

Principais melhorias de integração:
1. **Delegation Integrator** - Processa task assignments do Agentic Delegation System
2. **Template Selector com RAG** - Seleciona templates com contexto de similar_projects, design patterns e best practices
3. **Code Composer com RAG** - Gera código com contexto rico de data_models, api_design, architecture, system_design, tech_stack, ui_ux_design
4. **IaC Generator com System Design** - Gera IaC baseado no System Design detalhado (Kubernetes, Helm, Terraform)
5. **Validação Aprimorada** - Valida código gerado com base nos requisitos e specs upstream

O Code Forge produz 5 tipos principais de eventos Kafka que alimentam os sistemas downstream:
1. `code.generated` → Test Generation System, Documentation Generation System, Software Engineering Pipeline
2. `iac.generated` → Software Engineering Pipeline
3. `tests.required` → Test Generation System
4. `artifacts.created` → Software Engineering Pipeline, Monitoring
5. `template.used` → Monitoring, Analytics

---

## 🧪 Passo 7: Test Generation System (NOVO - 8013)

### Descrição Geral

Consome o código gerado pelo Code Forge e gera testes automáticos (unitários, integração, E2E, mocks, mutation testing).

### Componentes do Test Generation System

| Componente | Descrição |
|------------|-----------|
| **Unit Test Generator** | Gera testes unitários para cada função/classe |
| **Integration Test Generator** | Gera testes de integração para APIs e bancos de dados |
| **E2E Test Generator** | Gera testes E2E para user journeys |
| **Mock Generator** | Gera mocks e fixtures para dependências externas |
| **Mutation Tester** | Realiza mutation testing para validar qualidade de testes |
| **Test Quality Analyzer** | Analisa qualidade de testes (coverage, complexity, maintainability) |

### Portas e Endpoints

- **Porta API REST:** 8013
- **Health Check:** `/health`
- **Metrics:** `/metrics`
- **Endpoints:**
  - `POST /api/v1/tests/unit/generate` - Gerar testes unitários
  - `POST /api/v1/tests/integration/generate` - Gerar testes de integração
  - `POST /api/v1/tests/e2e/generate` - Gerar testes E2E
  - `POST /api/v1/tests/mocks/generate` - Gerar mocks e fixtures
  - `POST /api/v1/tests/mutation/run` - Executar mutation testing
  - `POST /api/v1/tests/quality/analyze` - Analisar qualidade de testes
  - `GET /api/v1/tests/{id}` - Obter testes gerados
  - `GET /api/v1/tests/{id}/report` - Obter relatório de testes

---

### 7.1 Unit Test Generator

**Responsabilidade:** Gera testes unitários para cada função/classe do código gerado.

**Consumir:**
- `code.generated` (do Code Forge)
- `data_models.generated` (do Requirements Engineering System)
- `api_designs.generated` (do Requirements Engineering System)

**Processamento:**
```python
# services/test-generation/src/services/unit_test_generator.py

class UnitTestGenerator:
    async def generate_unit_tests(self, code: dict, data_models: dict, api_design: dict) -> dict:
        """
        Gera testes unitários para código gerado.

        Processo:
        1. Analisar código com AST para identificar funções/classes
        2. Extrair tipos de retorno e parâmetros
        3. Gerar testes para cada função/classe
        4. Gerar edge case tests
        5. Gerar boundary value tests
        6. Gerar mocks para dependências
        7. Validação de resultados
        """
        # Analisar código com AST
        code_analysis = await self._analyze_code_ast(code['code'])

        # Gerar testes para cada função
        unit_tests = []

        for function in code_analysis['functions']:
            # Gerar testes normais
            normal_tests = await self._generate_normal_tests(function, data_models)

            # Gerar edge case tests
            edge_case_tests = await self._generate_edge_case_tests(function)

            # Gerar boundary value tests
            boundary_tests = await self._generate_boundary_value_tests(function)

            # Gerar mocks para dependências
            mocks = await self._generate_mocks(function)

            unit_tests.append({
                "function_name": function['name'],
                "normal_tests": normal_tests,
                "edge_case_tests": edge_case_tests,
                "boundary_tests": boundary_tests,
                "mocks": mocks
            })

        # Gerar testes para classes
        for class_def in code_analysis['classes']:
            # Gerar testes para cada método
            class_tests = await self._generate_class_tests(class_def, data_models)

            unit_tests.append({
                "class_name": class_def['name'],
                "class_tests": class_tests
            })

        # Gerar arquivo de testes
        test_file = await self._generate_test_file(unit_tests, code['language'])

        # Gerar fixtures
        fixtures = await self._generate_fixtures(data_models, code['language'])

        # Validar testes gerados
        validation_result = await self._validate_unit_tests(test_file, code['code'])

        return {
            "test_file": test_file,
            "fixtures": fixtures,
            "validation": validation_result,
            "test_count": await self._count_tests(unit_tests),
            "coverage_estimate": await self._estimate_coverage(code_analysis, unit_tests),
            "generated_at": datetime.utcnow().isoformat()
        }

    async def _generate_normal_tests(self, function: dict, data_models: dict) -> List[dict]:
        """
        Gera testes normais para uma função.

        Estratégia:
        1. Identificar casos de teste baseados em tipo de retorno e parâmetros
        2. Gerar dados de teste válidos
        3. Gerar asserts apropriados
        4. Adicionar docstrings descritivas
        """
        tests = []

        # Identificar tipos de parâmetros
        params = function.get('parameters', [])
        return_type = function.get('return_type')

        # Caso de teste 1: Valores normais
        normal_input = await self._generate_normal_input(params, data_models)
        expected_output = await self._generate_expected_output(return_type, normal_input)

        test = {
            "name": f"test_{function['name']}_with_normal_input",
            "description": f"Test {function['name']} with normal input values",
            "input": normal_input,
            "expected_output": expected_output,
            "asserts": await self._generate_asserts(return_type, expected_output),
            "setup": await self._generate_setup(params, data_models),
            "teardown": await self._generate_teardown(params)
        }

        tests.append(test)

        return tests

    async def _generate_edge_case_tests(self, function: dict) -> List[dict]:
        """
        Gera edge case tests para uma função.

        Edge cases:
        1. Valores nulos
        2. Valores vazios
        3. Valores extremos (min/max)
        4. Tipos incorretos
        5. Valores inválidos
        """
        tests = []

        params = function.get('parameters', [])

        # Edge case 1: Valores nulos
        null_input = await self._generate_null_input(params)
        test_null = {
            "name": f"test_{function['name']}_with_null_input",
            "description": f"Test {function['name']} with null input values",
            "input": null_input,
            "expected_behavior": "should raise ValueError or return None",
            "asserts": [
                "with pytest.raises(ValueError):"
            ]
        }
        tests.append(test_null)

        # Edge case 2: Valores vazios
        empty_input = await self._generate_empty_input(params)
        test_empty = {
            "name": f"test_{function['name']}_with_empty_input",
            "description": f"Test {function['name']} with empty input values",
            "input": empty_input,
            "expected_behavior": "should handle empty input gracefully",
            "asserts": [
                "assert result is not None",
                "assert len(result) == 0"
            ]
        }
        tests.append(test_empty)

        return tests

    async def _generate_boundary_value_tests(self, function: dict) -> List[dict]:
        """
        Gera boundary value tests para uma função.

        Boundary values:
        1. Valor mínimo
        2. Valor máximo
        3. Valores logo abaixo do mínimo
        4. Valores logo acima do máximo
        """
        tests = []

        params = function.get('parameters', [])

        # Identificar parâmetros numéricos
        numeric_params = [p for p in params if p['type'] in ['int', 'float']]

        for param in numeric_params:
            min_value = param.get('constraints', {}).get('min', 0)
            max_value = param.get('constraints', {}).get('max', 100)

            # Boundary 1: Valor mínimo
            test_min = {
                "name": f"test_{function['name']}_with_{param['name']}_at_min_value",
                "description": f"Test {function['name']} with {param['name']} at minimum value ({min_value})",
                "input": {param['name']: min_value},
                "expected_behavior": "should work correctly with minimum value"
            }
            tests.append(test_min)

            # Boundary 2: Valor máximo
            test_max = {
                "name": f"test_{function['name']}_with_{param['name']}_at_max_value",
                "description": f"Test {function['name']} with {param['name']} at maximum value ({max_value})",
                "input": {param['name']: max_value},
                "expected_behavior": "should work correctly with maximum value"
            }
            tests.append(test_max)

            # Boundary 3: Valor logo abaixo do mínimo
            test_below_min = {
                "name": f"test_{function['name']}_with_{param['name']}_below_min_value",
                "description": f"Test {function['name']} with {param['name']} below minimum value ({min_value - 1})",
                "input": {param['name']: min_value - 1},
                "expected_behavior": "should raise ValueError"
            }
            tests.append(test_below_min)

            # Boundary 4: Valor logo acima do máximo
            test_above_max = {
                "name": f"test_{function['name']}_with_{param['name']}_above_max_value",
                "description": f"Test {function['name']} with {param['name']} above maximum value ({max_value + 1})",
                "input": {param['name']: max_value + 1},
                "expected_behavior": "should raise ValueError"
            }
            tests.append(test_above_max)

        return tests

    async def _generate_test_file(self, unit_tests: List[dict], language: str) -> str:
        """
        Gera arquivo de testes baseado na linguagem.
        """
        if language == 'python':
            return await self._generate_python_test_file(unit_tests)
        elif language == 'typescript':
            return await self._generate_typescript_test_file(unit_tests)
        else:
            raise ValueError(f"Unsupported language: {language}")

    async def _generate_python_test_file(self, unit_tests: List[dict]) -> str:
        """
        Gera arquivo de testes Python com pytest.
        """
        test_file = """# Auto-generated unit tests
# Generated by Neural-Hive-Mind Test Generation System

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import uuid
from typing import List

# Import functions and classes to test
from src.models.user import User, UserCreate, UserInDB
from src.services.user_service import UserService
from src.repositories.user_repository import UserRepository

# Fixtures
@pytest.fixture
def mock_user_repository():
    """Mock UserRepository for testing."""
    repo = MagicMock(spec=UserRepository)
    return repo

@pytest.fixture
def user_service(mock_user_repository):
    """UserService with mocked repository."""
    return UserService(repository=mock_user_repository)

@pytest.fixture
def sample_user_data():
    """Sample user data for testing."""
    return {
        "email": "test@example.com",
        "name": "Test User",
        "password": "password123"
    }

# User Model Tests
class TestUserModel:
    \"\"\"Tests for User model.\"\"\"

    def test_user_create_with_valid_data(self, sample_user_data):
        \"\"\"Test UserCreate with valid input data.\"\"\"
        user = UserCreate(**sample_user_data)
        assert user.email == "test@example.com"
        assert user.name == "Test User"
        assert user.password == "password123"
        assert len(user.password) >= 8

    def test_user_create_with_invalid_email(self, sample_user_data):
        \"\"\"Test UserCreate with invalid email.\"\"\"
        sample_user_data['email'] = "invalid"
        with pytest.raises(ValueError):
            UserCreate(**sample_user_data)

    def test_user_create_with_short_password(self, sample_user_data):
        \"\"\"Test UserCreate with short password.\"\"\"
        sample_user_data['password'] = "short"
        with pytest.raises(ValueError):
            UserCreate(**sample_user_data)

    def test_user_create_with_empty_name(self, sample_user_data):
        \"\"\"Test UserCreate with empty name.\"\"\"
        sample_user_data['name'] = ""
        with pytest.raises(ValueError):
            UserCreate(**sample_user_data)

    def test_user_model_with_uuid(self):
        \"\"\"Test User model with auto-generated UUID.\"\"\"
        user = User(
            id=uuid.uuid4(),
            email="test@example.com",
            name="Test User",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        assert isinstance(user.id, uuid.UUID)
        assert user.email == "test@example.com"
        assert user.name == "Test User"
        assert isinstance(user.created_at, datetime)
        assert isinstance(user.updated_at, datetime)

# UserService Tests
class TestUserService:
    \"\"\"Tests for UserService.\"\"\"

    def test_create_user_with_valid_data(self, user_service, sample_user_data, mock_user_repository):
        \"\"\"Test create_user with valid data.\"\"\"
        mock_user_repository.create.return_value = User(
            id=uuid.uuid4(),
            email=sample_user_data['email'],
            name=sample_user_data['name'],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        result = user_service.create_user(sample_user_data)

        assert result.email == sample_user_data['email']
        assert result.name == sample_user_data['name']
        mock_user_repository.create.assert_called_once()

    def test_create_user_with_duplicate_email(self, user_service, sample_user_data, mock_user_repository):
        \"\"\"Test create_user with duplicate email.\"\"\"
        mock_user_repository.create.side_effect = ValueError("Email already exists")

        with pytest.raises(ValueError, match="Email already exists"):
            user_service.create_user(sample_user_data)

    def test_get_user_by_id(self, user_service, mock_user_repository):
        \"\"\"Test get_user_by_id with valid ID.\"\"\"
        user_id = uuid.uuid4()
        expected_user = User(
            id=user_id,
            email="test@example.com",
            name="Test User",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        mock_user_repository.get_by_id.return_value = expected_user

        result = user_service.get_user_by_id(user_id)

        assert result.id == user_id
        assert result.email == "test@example.com"
        mock_user_repository.get_by_id.assert_called_once_with(user_id)

    def test_get_user_by_id_not_found(self, user_service, mock_user_repository):
        \"\"\"Test get_user_by_id with non-existent ID.\"\"\"
        user_id = uuid.uuid4()
        mock_user_repository.get_by_id.return_value = None

        with pytest.raises(ValueError, match="User not found"):
            user_service.get_user_by_id(user_id)

    def test_update_user_with_valid_data(self, user_service, sample_user_data, mock_user_repository):
        \"\"\"Test update_user with valid data.\"\"\"
        user_id = uuid.uuid4()
        existing_user = User(
            id=user_id,
            email=sample_user_data['email'],
            name="Old Name",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        mock_user_repository.get_by_id.return_value = existing_user

        update_data = {"name": "New Name"}
        mock_user_repository.update.return_value = User(
            id=user_id,
            email=sample_user_data['email'],
            name="New Name",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        result = user_service.update_user(user_id, update_data)

        assert result.name == "New Name"
        mock_user_repository.update.assert_called_once()

    def test_delete_user(self, user_service, mock_user_repository):
        \"\"\"Test delete_user.\"\"\"
        user_id = uuid.uuid4()
        mock_user_repository.delete.return_value = True

        result = user_service.delete_user(user_id)

        assert result is True
        mock_user_repository.delete.assert_called_once_with(user_id)
"""

        return test_file
```

**Output:**
```json
{
  "test_file": {
    "language": "python",
    "framework": "pytest",
    "filename": "tests/unit/test_user_service.py",
    "content": "# Auto-generated unit tests\n# Generated by Neural-Hive-Mind Test Generation System\n\nimport pytest\nfrom unittest.mock import Mock, patch, MagicMock\nfrom datetime import datetime\nimport uuid\nfrom typing import List\n\n# Import functions and classes to test\nfrom src.models.user import User, UserCreate, UserInDB\nfrom src.services.user_service import UserService\nfrom src.repositories.user_repository import UserRepository\n\n# Fixtures\n@pytest.fixture\ndef mock_user_repository():\n    \"\"\"Mock UserRepository for testing.\"\"\"\n    repo = MagicMock(spec=UserRepository)\n    return repo\n\n@pytest.fixture\ndef user_service(mock_user_repository):\n    \"\"\"UserService with mocked repository.\"\"\"\n    return UserService(repository=mock_user_repository)\n\n@pytest.fixture\ndef sample_user_data():\n    \"\"\"Sample user data for testing.\"\"\"\n    return {\n        \"email\": \"test@example.com\",\n        \"name\": \"Test User\",\n        \"password\": \"password123\"\n    }\n\n# User Model Tests\nclass TestUserModel:\n    \"\"\"Tests for User model.\"\"\"\n\n    def test_user_create_with_valid_data(self, sample_user_data):\n        \"\"\"Test UserCreate with valid input data.\"\"\"\n        user = UserCreate(**sample_user_data)\n        assert user.email == \"test@example.com\"\n        assert user.name == \"Test User\"\n        assert user.password == \"password123\"\n        assert len(user.password) >= 8\n\n    def test_user_create_with_invalid_email(self, sample_user_data):\n        \"\"\"Test UserCreate with invalid email.\"\"\"\n        sample_user_data['email'] = \"invalid\"\n        with pytest.raises(ValueError):\n            UserCreate(**sample_user_data)\n\n    # ... mais testes"
  },
  "fixtures": [
    {
      "name": "sample_user_data",
      "description": "Sample user data for testing",
      "data": {
        "email": "test@example.com",
        "name": "Test User",
        "password": "password123"
      }
    },
    {
      "name": "mock_user_repository",
      "description": "Mock UserRepository for testing",
      "mock_type": "MagicMock",
      "spec": "UserRepository"
    }
  ],
  "validation": {
    "is_valid": true,
    "errors": [],
    "warnings": [],
    "lint_score": 9.2
  },
  "test_count": {
    "total": 15,
    "unit_tests": 10,
    "edge_case_tests": 3,
    "boundary_tests": 2
  },
  "coverage_estimate": {
    "statement_coverage": 85.0,
    "branch_coverage": 75.0,
    "function_coverage": 90.0
  },
  "generated_at": "2026-04-15T15:00:00Z"
}
```

---

### 7.2 Integration Test Generator

**Responsabilidade:** Gera testes de integração para APIs e bancos de dados.

**Consumir:**
- `code.generated` (do Code Forge)
- `api_designs.generated` (do Requirements Engineering System)
- `data_models.generated` (do Requirements Engineering System)

**Processamento:**
```python
# services/test-generation/src/services/integration_test_generator.py

class IntegrationTestGenerator:
    async def generate_integration_tests(self, code: dict, api_design: dict, data_models: dict) -> dict:
        """
        Gera testes de integração para APIs e bancos de dados.

        Processo:
        1. Analisar API endpoints (GET, POST, PUT, DELETE)
        2. Gerar testes para cada endpoint
        3. Gerar testes de autenticação/autorização
        4. Gerar testes de validação de schema
        5. Gerar testes de integração com banco de dados
        6. Gerar testes de integração com message queue (Kafka)
        """
        # Analisar API endpoints
        endpoints = api_design.get('endpoints', [])

        # Gerar testes para cada endpoint
        integration_tests = []

        for endpoint in endpoints:
            # Gerar testes para este endpoint
            endpoint_tests = await self._generate_endpoint_tests(endpoint, data_models)

            integration_tests.append({
                "endpoint": endpoint,
                "tests": endpoint_tests
            })

        # Gerar testes de autenticação
        auth_tests = await self._generate_auth_tests(api_design)

        # Gerar testes de validação de schema
        schema_tests = await self._generate_schema_tests(api_design, data_models)

        # Gerar testes de integração com banco de dados
        db_tests = await self._generate_db_integration_tests(data_models)

        # Gerar testes de integração com Kafka
        kafka_tests = await self._generate_kafka_integration_tests(api_design)

        # Gerar arquivo de testes
        test_file = await self._generate_integration_test_file(
            integration_tests,
            auth_tests,
            schema_tests,
            db_tests,
            kafka_tests
        )

        # Validar testes gerados
        validation_result = await self._validate_integration_tests(test_file)

        return {
            "test_file": test_file,
            "validation": validation_result,
            "test_count": {
                "endpoint_tests": len(integration_tests) * 3,
                "auth_tests": len(auth_tests),
                "schema_tests": len(schema_tests),
                "db_tests": len(db_tests),
                "kafka_tests": len(kafka_tests)
            },
            "generated_at": datetime.utcnow().isoformat()
        }

    async def _generate_endpoint_tests(self, endpoint: dict, data_models: dict) -> List[dict]:
        """
        Gera testes de integração para um endpoint específico.

        Tipos de testes:
        1. Happy path (cenário normal)
        2. Sad path (cenário de erro)
        3. Edge case (casos extremos)
        """
        tests = []

        method = endpoint.get('method')
        path = endpoint.get('path')
        request_body = endpoint.get('request_body')
        response = endpoint.get('response')

        # Teste 1: Happy path
        happy_test = {
            "name": f"test_{method.lower()}_{path.replace('/', '_')}_success",
            "description": f"Test {method} {path} - Happy path",
            "setup": await self._generate_happy_setup(endpoint),
            "request": await self._generate_happy_request(endpoint, data_models),
            "expected_status": 200,
            "expected_response": response.get('200', {}).get('content', {}),
            "cleanup": await self._generate_cleanup(endpoint)
        }
        tests.append(happy_test)

        # Teste 2: Sad path (erro de validação)
        sad_test = {
            "name": f"test_{method.lower()}_{path.replace('/', '_')}_validation_error",
            "description": f"Test {method} {path} - Validation error",
            "setup": await self._generate_sad_setup(endpoint),
            "request": await self._generate_sad_request(endpoint, data_models),
            "expected_status": 400,
            "expected_response": {
                "error": "Validation error",
                "details": {}
            },
            "cleanup": await self._generate_cleanup(endpoint)
        }
        tests.append(sad_test)

        # Teste 3: Edge case (recurso não encontrado)
        edge_test = {
            "name": f"test_{method.lower()}_{path.replace('/', '_')}_not_found",
            "description": f"Test {method} {path} - Resource not found",
            "setup": await self._generate_edge_setup(endpoint),
            "request": await self._generate_edge_request(endpoint, data_models),
            "expected_status": 404,
            "expected_response": {
                "error": "Resource not found"
            },
            "cleanup": await self._generate_cleanup(endpoint)
        }
        tests.append(edge_test)

        return tests

    async def _generate_auth_tests(self, api_design: dict) -> List[dict]:
        """
        Gera testes de autenticação/autorização.
        """
        auth_tests = []

        # Teste 1: Login com credenciais válidas
        auth_tests.append({
            "name": "test_login_with_valid_credentials",
            "description": "Test login with valid email and password",
            "request": {
                "method": "POST",
                "path": "/api/v1/auth/login",
                "body": {
                    "email": "test@example.com",
                    "password": "password123"
                }
            },
            "expected_status": 200,
            "expected_response": {
                "access_token": "jwt_token",
                "refresh_token": "jwt_refresh_token",
                "token_type": "Bearer",
                "expires_in": 86400
            }
        })

        # Teste 2: Login com credenciais inválidas
        auth_tests.append({
            "name": "test_login_with_invalid_credentials",
            "description": "Test login with invalid email or password",
            "request": {
                "method": "POST",
                "path": "/api/v1/auth/login",
                "body": {
                    "email": "test@example.com",
                    "password": "wrongpassword"
                }
            },
            "expected_status": 401,
            "expected_response": {
                "error": "Invalid credentials"
            }
        })

        # Teste 3: Acesso sem autenticação
        auth_tests.append({
            "name": "test_access_without_authentication",
            "description": "Test accessing protected endpoint without authentication",
            "request": {
                "method": "GET",
                "path": "/api/v1/users/{id}",
                "headers": {}
            },
            "expected_status": 401,
            "expected_response": {
                "error": "Authentication required"
            }
        })

        return auth_tests

    async def _generate_db_integration_tests(self, data_models: dict) -> List[dict]:
        """
        Gera testes de integração com banco de dados.
        """
        db_tests = []

        entities = data_models.get('entities', [])

        for entity in entities:
            entity_name = entity.get('name')

            # Teste 1: Criar registro no banco
            db_tests.append({
                "name": f"test_create_{entity_name.lower()}_in_database",
                "description": f"Test creating {entity_name} in database",
                "setup": await self._generate_db_setup(entity),
                "operation": "CREATE",
                "data": await self._generate_sample_data(entity),
                "expected_result": "Record created successfully"
            })

            # Teste 2: Ler registro do banco
            db_tests.append({
                "name": f"test_read_{entity_name.lower()}_from_database",
                "description": f"Test reading {entity_name} from database",
                "setup": await self._generate_db_setup(entity),
                "operation": "READ",
                "query": f"SELECT * FROM {entity_name.lower()} WHERE id = ?",
                "expected_result": "Record retrieved successfully"
            })

            # Teste 3: Atualizar registro no banco
            db_tests.append({
                "name": f"test_update_{entity_name.lower()}_in_database",
                "description": f"Test updating {entity_name} in database",
                "setup": await self._generate_db_setup(entity),
                "operation": "UPDATE",
                "query": f"UPDATE {entity_name.lower()} SET name = ? WHERE id = ?",
                "data": {"name": "Updated Name"},
                "expected_result": "Record updated successfully"
            })

            # Teste 4: Deletar registro do banco
            db_tests.append({
                "name": f"test_delete_{entity_name.lower()}_from_database",
                "description": f"Test deleting {entity_name} from database",
                "setup": await self._generate_db_setup(entity),
                "operation": "DELETE",
                "query": f"DELETE FROM {entity_name.lower()} WHERE id = ?",
                "expected_result": "Record deleted successfully"
            })

        return db_tests

    async def _generate_kafka_integration_tests(self, api_design: dict) -> List[dict]:
        """
        Gera testes de integração com Kafka.
        """
        kafka_tests = []

        # Teste 1: Producer envia evento para tópico
        kafka_tests.append({
            "name": "test_kafka_producer_sends_event",
            "description": "Test Kafka producer sends event to topic",
            "setup": await self._generate_kafka_producer_setup(),
            "operation": "PRODUCE",
            "topic": "orders.created",
            "event": await self._generate_sample_kafka_event("orders.created"),
            "expected_result": "Event sent successfully"
        })

        # Teste 2: Consumer recebe evento do tópico
        kafka_tests.append({
            "name": "test_kafka_consumer_receives_event",
            "description": "Test Kafka consumer receives event from topic",
            "setup": await self._generate_kafka_consumer_setup(),
            "operation": "CONSUME",
            "topic": "orders.created",
            "expected_result": "Event consumed successfully"
        })

        return kafka_tests

    async def _generate_integration_test_file(self, integration_tests: List[dict], auth_tests: List[dict], schema_tests: List[dict], db_tests: List[dict], kafka_tests: List[dict]) -> str:
        """
        Gera arquivo de testes de integração.
        """
        test_file = """# Auto-generated integration tests
# Generated by Neural-Hive-Mind Test Generation System

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import Mock, patch
import json
from kafka import KafkaProducer, KafkaConsumer
import time

# Import FastAPI app
from src.main import app

# Database setup
DATABASE_URL = "postgresql://test_user:test_pass@localhost:5432/test_db"
engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Kafka setup
KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
KAFKA_TOPIC_ORDERS = "orders.created"

@pytest.fixture
def db_session():
    \"\"\"Create a new database session for a test.\"\"\"
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def client():
    \"\"\"Create a test client for FastAPI app.\"\"\"
    return TestClient(app)

# API Integration Tests
class TestAPIIntegration:
    \"\"\"Tests for API integration.\"\"\"

    def test_post_users_with_valid_data(self, client):
        \"\"\"Test POST /api/v1/users with valid data.\"\"\"
        response = client.post(
            "/api/v1/users",
            json={
                "email": "test@example.com",
                "password": "password123",
                "name": "Test User"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["email"] == "test@example.com"
        assert data["name"] == "Test User"

    def test_post_users_with_invalid_email(self, client):
        \"\"\"Test POST /api/v1/users with invalid email.\"\"\"
        response = client.post(
            "/api/v1/users",
            json={
                "email": "invalid",
                "password": "password123",
                "name": "Test User"
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    def test_get_users_with_authentication(self, client):
        \"\"\"Test GET /api/v1/users with authentication.\"\"\"
        # First, login to get token
        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "password123"
            }
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        # Then, get users with token
        response = client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_users_without_authentication(self, client):
        \"\"\"Test GET /api/v1/users without authentication.\"\"\"
        response = client.get("/api/v1/users")
        assert response.status_code == 401
        data = response.json()
        assert "error" in data

# Database Integration Tests
class TestDatabaseIntegration:
    \"\"\"Tests for database integration.\"\"\"

    def test_create_user_in_database(self, db_session):
        \"\"\"Test creating user in database.\"\"\"
        from src.models.user import User, UserInDB

        user_data = {
            "email": "test@example.com",
            "name": "Test User",
            "password_hash": "hashed_password"
        }

        user = User(**user_data)
        db_session.add(user)
        db_session.commit()

        assert user.id is not None
        assert user.email == "test@example.com"

    def test_read_user_from_database(self, db_session):
        \"\"\"Test reading user from database.\"\"\"
        from src.models.user import User

        user = db_session.query(User).filter(User.email == "test@example.com").first()
        assert user is not None
        assert user.name == "Test User"

# Kafka Integration Tests
class TestKafkaIntegration:
    \"\"\"Tests for Kafka integration.\"\"\"

    @pytest.mark.integration
    def test_kafka_producer_sends_event(self):
        \"\"\"Test Kafka producer sends event to topic.\"\"\"
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )

        event = {
            "order_id": "test-order-1",
            "user_id": "test-user-1",
            "restaurant_id": "test-restaurant-1",
            "total": 50.0,
            "items": [{"item_id": "item-1", "quantity": 2}]
        }

        future = producer.send(KAFKA_TOPIC_ORDERS, value=event)
        record_metadata = future.get(timeout=10)

        assert record_metadata.topic == KAFKA_TOPIC_ORDERS

    @pytest.mark.integration
    def test_kafka_consumer_receives_event(self):
        \"\"\"Test Kafka consumer receives event from topic.\"\"\"
        consumer = KafkaConsumer(
            KAFKA_TOPIC_ORDERS,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='earliest',
            consumer_timeout_ms=1000
        )

        events = []
        for message in consumer:
            events.append(message.value)
            if len(events) >= 1:
                break

        assert len(events) >= 1
        assert "order_id" in events[0]
"""

        return test_file
```

**Output:**
```json
{
  "test_file": {
    "language": "python",
    "framework": "pytest",
    "filename": "tests/integration/test_api_integration.py",
    "content": "# Auto-generated integration tests\n# Generated by Neural-Hive-Mind Test Generation System\n\nimport pytest\nfrom fastapi.testclient import TestClient\nfrom sqlalchemy import create_engine\nfrom sqlalchemy.orm import sessionmaker\nfrom unittest.mock import Mock, patch\nimport json\nfrom kafka import KafkaProducer, KafkaConsumer\nimport time\n\n# Import FastAPI app\nfrom src.main import app\n\n# Database setup\nDATABASE_URL = \"postgresql://test_user:test_pass@localhost:5432/test_db\"\nengine = create_engine(DATABASE_URL)\nTestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)\n\n# Kafka setup\nKAFKA_BOOTSTRAP_SERVERS = \"localhost:9092\"\nKAFKA_TOPIC_ORDERS = \"orders.created\"\n\n@pytest.fixture\ndef db_session():\n    \"\"\"Create a new database session for a test.\"\"\"\n    session = TestingSessionLocal()\n    try:\n        yield session\n    finally:\n        session.close()\n\n@pytest.fixture\ndef client():\n    \"\"\"Create a test client for FastAPI app.\"\"\"\n    return TestClient(app)\n\n# API Integration Tests\nclass TestAPIIntegration:\n    \"\"\"Tests for API integration.\"\"\"\n\n    def test_post_users_with_valid_data(self, client):\n        \"\"\"Test POST /api/v1/users with valid data.\"\"\"\n        response = client.post(\n            \"/api/v1/users\",\n            json={\n                \"email\": \"test@example.com\",\n                \"password\": \"password123\",\n                \"name\": \"Test User\"\n            }\n        )\n        assert response.status_code == 201\n        data = response.json()\n        assert \"id\" in data\n        assert data[\"email\"] == \"test@example.com\"\n        assert data[\"name\"] == \"Test User\"\n\n    # ... mais testes"
  },
  "validation": {
    "is_valid": true,
    "errors": [],
    "warnings": [
      "Kafka integration tests require running Kafka instance"
    ],
    "lint_score": 9.0
  },
  "test_count": {
    "total": 25,
    "endpoint_tests": 18,
    "auth_tests": 3,
    "schema_tests": 2,
    "db_tests": 2,
    "kafka_tests": 2
  },
  "generated_at": "2026-04-15T15:30:00Z"
}
```

---

### 7.3 E2E Test Generator

**Responsabilidade:** Gera testes E2E para user journeys completos.

**Consumir:**
- `user_stories.generated` (do Requirements Engineering System)
- `api_designs.generated` (do Requirements Engineering System)
- `ui_ux_designs.generated` (do Requirements Engineering System)

**Processamento:**
```python
# services/test-generation/src/services/e2e_test_generator.py

class E2ETestGenerator:
    async def generate_e2e_tests(self, user_stories: List[dict], api_design: dict, ui_ux_design: dict) -> dict:
        """
        Gera testes E2E para user journeys.

        Processo:
        1. Analisar user stories e acceptance criteria
        2. Mapear user journeys a partir de Cucumber scenarios
        3. Gerar testes E2E para cada user journey
        4. Gerar test data complexos
        5. Gerar visual regression tests
        """
        # Analisar user stories
        e2e_tests = []

        for user_story in user_stories:
            # Obter Cucumber scenarios
            cucumber_scenarios = user_story.get('cucumber_scenarios', [])

            for scenario in cucumber_scenarios:
                # Gerar teste E2E para este cenário
                e2e_test = await self._generate_e2e_test(scenario, api_design, ui_ux_design)

                e2e_tests.append(e2e_test)

        # Gerar test data complexos
        test_data = await self._generate_test_data(user_stories)

        # Gerar visual regression tests
        visual_tests = await self._generate_visual_regression_tests(ui_ux_design)

        # Gerar arquivo de testes
        test_file = await self._generate_e2e_test_file(e2e_tests, test_data)

        # Validar testes gerados
        validation_result = await self._validate_e2e_tests(test_file)

        return {
            "test_file": test_file,
            "test_data": test_data,
            "visual_tests": visual_tests,
            "validation": validation_result,
            "test_count": len(e2e_tests),
            "generated_at": datetime.utcnow().isoformat()
        }

    async def _generate_e2e_test(self, scenario: dict, api_design: dict, ui_ux_design: dict) -> dict:
        """
        Gera teste E2E para um Cucumber scenario.
        """
        scenario_name = scenario.get('name', 'Unknown')
        steps = scenario.get('steps', [])

        # Mapear steps para ações E2E
        e2e_steps = await self._map_steps_to_e2e_actions(steps, api_design, ui_ux_design)

        # Gerar teste E2E
        e2e_test = {
            "name": f"test_e2e_{scenario_name.lower().replace(' ', '_')}",
            "description": scenario_name,
            "user_story": scenario.get('user_story'),
            "steps": e2e_steps,
            "setup": await self._generate_e2e_setup(scenario, ui_ux_design),
            "cleanup": await self._generate_e2e_cleanup(scenario),
            "asserts": await self._generate_e2e_asserts(scenario)
        }

        return e2e_test

    async def _map_steps_to_e2e_actions(self, steps: List[dict], api_design: dict, ui_ux_design: dict) -> List[dict]:
        """
        Mapeia Cucumber steps para ações E2E.

        Tipos de ações:
        1. Navigate to page
        2. Fill input field
        3. Click button
        4. Wait for element
        5. Assert element visible
        6. Assert text equals
        """
        e2e_actions = []

        for step in steps:
            step_text = step.get('step', '')

            # Mapear step para ação
            if "Given que estou na página" in step_text:
                e2e_actions.append({
                    "action": "navigate",
                    "target": await self._extract_page_from_step(step_text),
                    "wait_until": "page_loaded"
                })
            elif "When preencho" in step_text:
                e2e_actions.append({
                    "action": "fill_input",
                    "selector": await self._extract_input_selector(step_text, ui_ux_design),
                    "value": await self._extract_input_value(step_text),
                    "wait_until": "element_visible"
                })
            elif "And clico no botão" in step_text:
                e2e_actions.append({
                    "action": "click",
                    "selector": await self._extract_button_selector(step_text, ui_ux_design),
                    "wait_until": "element_visible"
                })
            elif "Then devo ver mensagem" in step_text:
                e2e_actions.append({
                    "action": "assert_text_visible",
                    "selector": await self._extract_message_selector(step_text, ui_ux_design),
                    "text": await self._extract_expected_text(step_text),
                    "timeout": 5000
                })
            elif "Then devo ser redirecionado" in step_text:
                e2e_actions.append({
                    "action": "assert_url",
                    "expected_url": await self._extract_expected_url(step_text),
                    "timeout": 5000
                })

        return e2e_actions

    async def _generate_e2e_test_file(self, e2e_tests: List[dict], test_data: dict) -> str:
        """
        Gera arquivo de testes E2E usando Playwright/Cypress.
        """
        test_file = """# Auto-generated E2E tests
# Generated by Neural-Hive-Mind Test Generation System
# Framework: Playwright with Python

from playwright.sync_api import Page, expect
import pytest

# Test Data
TEST_USER_DATA = {
    "email": "test@example.com",
    "password": "password123",
    "name": "Test User"
}

TEST_RESTAURANT_DATA = {
    "name": "Test Restaurant",
    "cuisine_type": "Italian",
    "address": "123 Test St",
    "rating": 4.5
}

# E2E Tests
class TestUserRegistrationE2E:
    \"\"\"E2E tests for user registration flow.\"\"\"

    def test_user_registration_happy_path(self, page: Page):
        \"\"\"Test complete user registration flow - Happy path.\"\"\"

        # Step 1: Navigate to signup page
        page.goto("http://localhost:3000/signup")
        page.wait_for_load_state("networkidle")

        # Step 2: Fill registration form
        page.fill("input[name='email']", TEST_USER_DATA['email'])
        page.fill("input[name='name']", TEST_USER_DATA['name'])
        page.fill("input[name='password']", TEST_USER_DATA['password'])
        page.fill("input[name='password_confirmation']", TEST_USER_DATA['password'])

        # Step 3: Click signup button
        page.click("button[type='submit']")

        # Step 4: Wait for success message
        expect(page.locator("text=Registration successful")).to_be_visible(timeout=5000)

        # Step 5: Verify redirect to login page
        expect(page).to_have_url("http://localhost:3000/login")

    def test_user_registration_with_invalid_email(self, page: Page):
        \"\"\"Test user registration with invalid email - Sad path.\"\"\"

        # Step 1: Navigate to signup page
        page.goto("http://localhost:3000/signup")
        page.wait_for_load_state("networkidle")

        # Step 2: Fill registration form with invalid email
        page.fill("input[name='email']", "invalid")
        page.fill("input[name='name']", TEST_USER_DATA['name'])
        page.fill("input[name='password']", TEST_USER_DATA['password'])
        page.fill("input[name='password_confirmation']", TEST_USER_DATA['password'])

        # Step 3: Click signup button
        page.click("button[type='submit']")

        # Step 4: Wait for error message
        expect(page.locator("text=Invalid email")).to_be_visible(timeout=5000)

        # Step 5: Verify still on signup page
        expect(page).to_have_url("http://localhost:3000/signup")

class TestOrderCreationE2E:
    \"\"\"E2E tests for order creation flow.\"\"\"

    @pytest.mark.dependency(depends=["TestUserRegistrationE2E::test_user_registration_happy_path"])
    def test_order_creation_happy_path(self, page: Page):
        \"\"\"Test complete order creation flow - Happy path.\"\"\"

        # Step 1: Login
        page.goto("http://localhost:3000/login")
        page.fill("input[name='email']", TEST_USER_DATA['email'])
        page.fill("input[name='password']", TEST_USER_DATA['password'])
        page.click("button[type='submit']")
        expect(page).to_have_url("http://localhost:3000/home")

        # Step 2: Browse restaurants
        page.wait_for_load_state("networkidle")
        restaurant_card = page.locator(f"text={TEST_RESTAURANT_DATA['name']}").first
        restaurant_card.click()

        # Step 3: View restaurant menu
        expect(page).to_have_url(re.compile(r"/restaurants/.*"))
        expect(page.locator("h1")).to_contain_text(TEST_RESTAURANT_DATA['name'])

        # Step 4: Add items to cart
        menu_items = page.locator(".menu-item").all()
        first_item = menu_items[0]
        first_item.locator("button").click()

        # Step 5: View cart
        page.click("button:has-text('Cart')")

        # Step 6: Create order
        expect(page.locator(".cart-item")).to_have_count(1)
        page.click("button:has-text('Checkout')")

        # Step 7: Confirm order
        expect(page).to_have_url(re.compile(r"/checkout"))
        page.fill("input[name='address']", "123 Delivery St")
        page.fill("input[name='notes']", "Deliver at door")
        page.click("button:has-text('Place Order')")

        # Step 8: Verify order confirmation
        expect(page.locator("text=Order created successfully")).to_be_visible(timeout=5000)
        expect(page).to_have_url(re.compile(r"/orders/.*"))

class TestOrderTrackingE2E:
    \"\"\"E2E tests for order tracking flow.\"\"\"

    @pytest.mark.dependency(depends=["TestOrderCreationE2E::test_order_creation_happy_path"])
    def test_order_tracking_real_time(self, page: Page):
        \"\"\"Test real-time order tracking.\"\"\"

        # Step 1: Navigate to orders page
        page.goto("http://localhost:3000/orders")
        page.wait_for_load_state("networkidle")

        # Step 2: Select latest order
        latest_order = page.locator(".order-card").first
        latest_order.click()

        # Step 3: Wait for order details
        expect(page.locator(".order-details")).to_be_visible()

        # Step 4: Verify tracking section
        expect(page.locator(".order-tracking")).to_be_visible()

        # Step 5: Verify status updates (simulated via WebSocket)
        status_badge = page.locator(".order-status")
        expect(status_badge).to_be_visible()

        # Wait for status to change from "pending" to "confirmed"
        expect(status_badge).to_contain_text("confirmed", timeout=10000)
"""

        return test_file
```

**Output:**
```json
{
  "test_file": {
    "framework": "playwright",
    "language": "python",
    "filename": "tests/e2e/test_user_flows.py",
    "content": "# Auto-generated E2E tests\n# Generated by Neural-Hive-Mind Test Generation System\n# Framework: Playwright with Python\n\nfrom playwright.sync_api import Page, expect\nimport pytest\n\n# Test Data\nTEST_USER_DATA = {\n    \"email\": \"test@example.com\",\n    \"password\": \"password123\",\n    \"name\": \"Test User\"\n}\n\nTEST_RESTAURANT_DATA = {\n    \"name\": \"Test Restaurant\",\n    \"cuisine_type\": \"Italian\",\n    \"address\": \"123 Test St\",\n    \"rating\": 4.5\n}\n\n# E2E Tests\nclass TestUserRegistrationE2E:\n    \"\"\"E2E tests for user registration flow.\"\"\"\n\n    def test_user_registration_happy_path(self, page: Page):\n        \"\"\"Test complete user registration flow - Happy path.\"\"\"\n        # Step 1: Navigate to signup page\n        page.goto(\"http://localhost:3000/signup\")\n        page.wait_for_load_state(\"networkidle\")\n        # Step 2: Fill registration form\n        page.fill(\"input[name='email']\", TEST_USER_DATA['email'])\n        # ... mais testes"
  },
  "test_data": {
    "users": [
      {
        "email": "test@example.com",
        "password": "password123",
        "name": "Test User"
      }
    ],
    "restaurants": [
      {
        "name": "Test Restaurant",
        "cuisine_type": "Italian",
        "address": "123 Test St",
        "rating": 4.5
      }
    ]
  },
  "visual_tests": [
    {
      "name": "test_signup_page_visual_regression",
      "description": "Visual regression test for signup page",
      "screenshot_path": "tests/e2e/screenshots/signup_page.png",
      "baseline_path": "tests/e2e/baselines/signup_page.png"
    }
  ],
  "validation": {
    "is_valid": true,
    "errors": [],
    "warnings": [],
    "lint_score": 9.5
  },
  "test_count": 5,
  "generated_at": "2026-04-15T16:00:00Z"
}
```

---

### 7.4 Mock Generator

**Responsabilidade:** Gera mocks e fixtures para dependências externas.

**Consumir:**
- `code.generated` (do Code Forge)
- `api_designs.generated` (do Requirements Engineering System)
- `system_design.generated` (do Architectural Planning System)

**Processamento:**
```python
# services/test-generation/src/services/mock_generator.py

class MockGenerator:
    async def generate_mocks(self, code: dict, api_design: dict, system_design: dict) -> dict:
        """
        Gera mocks e fixtures para dependências externas.

        Tipos de mocks:
        1. Database mocks (SQLAlchemy, MongoDB)
        2. API client mocks (HTTP, gRPC)
        3. Message queue mocks (Kafka, RabbitMQ)
        4. Cache mocks (Redis)
        5. External service mocks (Stripe, Mercado Pago, Google Maps)
        """
        mocks = []

        # Analisar dependências do código
        dependencies = await self._analyze_dependencies(code)

        # Gerar mocks para cada dependência
        for dependency in dependencies:
            if dependency['type'] == 'database':
                mock = await self._generate_database_mock(dependency)
                mocks.append(mock)
            elif dependency['type'] == 'api_client':
                mock = await self._generate_api_client_mock(dependency, api_design)
                mocks.append(mock)
            elif dependency['type'] == 'message_queue':
                mock = await self._generate_message_queue_mock(dependency, system_design)
                mocks.append(mock)
            elif dependency['type'] == 'cache':
                mock = await self._generate_cache_mock(dependency, system_design)
                mocks.append(mock)
            elif dependency['type'] == 'external_service':
                mock = await self._generate_external_service_mock(dependency, system_design)
                mocks.append(mock)

        # Gerar arquivo de mocks
        mock_file = await self._generate_mock_file(mocks)

        # Gerar fixtures
        fixtures = await self._generate_fixtures(mocks)

        return {
            "mock_file": mock_file,
            "fixtures": fixtures,
            "mock_count": len(mocks),
            "generated_at": datetime.utcnow().isoformat()
        }

    async def _generate_database_mock(self, dependency: dict) -> dict:
        """
        Gera mock para dependência de banco de dados.
        """
        db_type = dependency.get('db_type')
        models = dependency.get('models', [])

        if db_type == 'postgresql':
            return await self._generate_postgresql_mock(models)
        elif db_type == 'mongodb':
            return await self._generate_mongodb_mock(models)
        else:
            raise ValueError(f"Unsupported database type: {db_type}")

    async def _generate_postgresql_mock(self, models: List[dict]) -> dict:
        """
        Gera mock para PostgreSQL com SQLAlchemy.
        """
        mock = {
            "type": "database",
            "db_type": "postgresql",
            "framework": "sqlalchemy",
            "name": "mock_db_session",
            "code": """
# Auto-generated database mocks for PostgreSQL/SQLAlchemy
# Generated by Neural-Hive-Mind Test Generation System

from unittest.mock import MagicMock, Mock, patch
from sqlalchemy.orm import Session

# Mock database session
@pytest.fixture
def mock_db_session():
    \"\"\"Mock SQLAlchemy database session.\"\"\"
    session = MagicMock(spec=Session)
    yield session

# Mock User repository
@pytest.fixture
def mock_user_repository():
    \"\"\"Mock UserRepository for testing.\"\"\"
    from src.repositories.user_repository import UserRepository

    with patch.object(UserRepository, '__init__', return_value=None):
        repo = UserRepository()
        repo.create = MagicMock()
        repo.get_by_id = MagicMock()
        repo.get_by_email = MagicMock()
        repo.update = MagicMock()
        repo.delete = MagicMock()
        repo.list = MagicMock()

        yield repo

# Mock Restaurant repository
@pytest.fixture
def mock_restaurant_repository():
    \"\"\"Mock RestaurantRepository for testing.\"\"\"
    from src.repositories.restaurant_repository import RestaurantRepository

    with patch.object(RestaurantRepository, '__init__', return_value=None):
        repo = RestaurantRepository()
        repo.create = MagicMock()
        repo.get_by_id = MagicMock()
        repo.list = MagicMock()
        repo.search = MagicMock()

        yield repo
"""
        }
        return mock

    async def _generate_api_client_mock(self, dependency: dict, api_design: dict) -> dict:
        """
        Gera mock para cliente de API externa.
        """
        api_name = dependency.get('api_name')
        base_url = dependency.get('base_url')
        endpoints = api_design.get('endpoints', [])

        return {
            "type": "api_client",
            "api_name": api_name,
            "base_url": base_url,
            "name": f"mock_{api_name}_client",
            "code": await self._generate_http_client_mock(api_name, base_url, endpoints)
        }

    async def _generate_message_queue_mock(self, dependency: dict, system_design: dict) -> dict:
        """
        Gera mock para message queue (Kafka).
        """
        mq_type = dependency.get('mq_type')

        if mq_type == 'kafka':
            return await self._generate_kafka_mock(dependency, system_design)
        else:
            raise ValueError(f"Unsupported message queue type: {mq_type}")

    async def _generate_external_service_mock(self, dependency: dict, system_design: dict) -> dict:
        """
        Gera mock para serviço externo (Stripe, Google Maps, etc.).
        """
        service_name = dependency.get('service_name')
        operations = dependency.get('operations', [])

        if service_name == 'stripe':
            return await self._generate_stripe_mock(operations)
        elif service_name == 'google_maps':
            return await self._generate_google_maps_mock(operations)
        else:
            raise ValueError(f"Unsupported external service: {service_name}")

    async def _generate_mock_file(self, mocks: List[dict]) -> str:
        """
        Gera arquivo consolidado de mocks.
        """
        mock_file = """# Auto-generated mocks and fixtures
# Generated by Neural-Hive-Mind Test Generation System

import pytest
from unittest.mock import MagicMock, Mock, patch, AsyncMock
from sqlalchemy.orm import Session

# Database Mocks
@pytest.fixture
def mock_db_session():
    \"\"\"Mock SQLAlchemy database session.\"\"\"
    session = MagicMock(spec=Session)
    session.add = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    session.query = MagicMock()
    yield session

@pytest.fixture
def mock_user_repository():
    \"\"\"Mock UserRepository.\"\"\"
    from src.repositories.user_repository import UserRepository

    repo = MagicMock(spec=UserRepository)
    repo.create = AsyncMock()
    repo.get_by_id = AsyncMock()
    repo.get_by_email = AsyncMock()
    repo.update = AsyncMock()
    repo.delete = AsyncMock()
    repo.list = AsyncMock()

    yield repo

# API Client Mocks
@pytest.fixture
def mock_stripe_client():
    \"\"\"Mock Stripe client.\"\"\"
    import stripe

    with patch('stripe.Client') as mock_stripe:
        client = mock_stripe.return_value
        client.customers.create = Mock(return_value={'id': 'cus_test', 'email': 'test@example.com'})
        client.charges.create = Mock(return_value={'id': 'ch_test', 'amount': 5000, 'status': 'succeeded'})
        client.payment_intents.create = Mock(return_value={'id': 'pi_test', 'status': 'succeeded'})

        yield client

@pytest.fixture
def mock_google_maps_client():
    \"\"\"Mock Google Maps client.\"\"\"
    from googlemaps import Client

    with patch.object(Client, '__init__', return_value=None):
        client = Client()
        client.geocode = Mock(return_value=[{'formatted_address': '123 Test St', 'lat': 40.7128, 'lng': -74.0060}])
        client.directions = Mock(return_value=[{'legs': [{'duration': {'value': 1800}}]}])

        yield client

# Message Queue Mocks
@pytest.fixture
def mock_kafka_producer():
    \"\"\"Mock Kafka producer.\"\"\"
    producer = MagicMock()
    producer.send = Mock(return_value=MagicMock(get=Mock(return_value={'topic': 'test', 'partition': 0})))
    producer.flush = Mock()

    yield producer

@pytest.fixture
def mock_kafka_consumer():
    \"\"\"Mock Kafka consumer.\"\"\"
    consumer = MagicMock()
    consumer.__iter__ = Mock(return_value=iter([
        {'value': {'order_id': '1', 'status': 'pending'}},
        {'value': {'order_id': '2', 'status': 'pending'}}
    ]))

    yield consumer

# Cache Mocks
@pytest.fixture
def mock_redis_client():
    \"\"\"Mock Redis client.\"\"\"
    redis = MagicMock()
    redis.get = Mock(return_value=b'cached_value')
    redis.set = Mock(return_value=True)
    redis.delete = Mock(return_value=True)
    redis.setex = Mock(return_value=True)
    redis.exists = Mock(return_value=True)

    yield redis
"""
        return mock_file

    async def _generate_fixtures(self, mocks: List[dict]) -> List[dict]:
        """
        Gera fixtures para testes.
        """
        fixtures = []

        for mock in mocks:
            fixture = {
                "name": mock.get('name'),
                "type": mock.get('type'),
                "description": f"Mock fixture for {mock.get('type')} {mock.get('db_type', mock.get('api_name', mock.get('service_name'))}"
            }
            fixtures.append(fixture)

        # Adicionar fixtures de dados de teste
        fixtures.append({
            "name": "sample_user_data",
            "type": "test_data",
            "description": "Sample user data for testing",
            "data": {
                "email": "test@example.com",
                "name": "Test User",
                "password": "password123"
            }
        })

        fixtures.append({
            "name": "sample_order_data",
            "type": "test_data",
            "description": "Sample order data for testing",
            "data": {
                "user_id": "test-user-1",
                "restaurant_id": "test-restaurant-1",
                "total": 50.0,
                "items": [
                    {
                        "item_id": "item-1",
                        "quantity": 2,
                        "price": 25.0
                    }
                ]
            }
        })

        return fixtures
```

**Output:**
```json
{
  "mock_file": {
    "filename": "tests/mocks.py",
    "content": "# Auto-generated mocks and fixtures\n# Generated by Neural-Hive-Mind Test Generation System\n\nimport pytest\nfrom unittest.mock import MagicMock, Mock, patch, AsyncMock\nfrom sqlalchemy.orm import Session\n\n# Database Mocks\n@pytest.fixture\ndef mock_db_session():\n    \"\"\"Mock SQLAlchemy database session.\"\"\"\n    session = MagicMock(spec=Session)\n    session.add = MagicMock()\n    session.commit = MagicMock()\n    session.rollback = MagicMock()\n    session.query = MagicMock()\n    yield session\n\n# ... mais mocks"
  },
  "fixtures": [
    {
      "name": "mock_db_session",
      "type": "database",
      "description": "Mock SQLAlchemy database session"
    },
    {
      "name": "mock_stripe_client",
      "type": "external_service",
      "description": "Mock Stripe client"
    },
    {
      "name": "sample_user_data",
      "type": "test_data",
      "description": "Sample user data for testing",
      "data": {
        "email": "test@example.com",
        "name": "Test User",
        "password": "password123"
      }
    }
  ],
  "mock_count": 15,
  "generated_at": "2026-04-15T16:30:00Z"
}
```

---

### Eventos Kafka Produzidos pelo Test Generation System

```yaml
unit_tests.generated:
  - Producer: Unit Test Generator
  - Consumer: Software Engineering Pipeline
  - Payload: { id, task_id, test_file, fixtures, validation, test_count, coverage_estimate, generated_at }

integration_tests.generated:
  - Producer: Integration Test Generator
  - Consumer: Software Engineering Pipeline
  - Payload: { id, task_id, test_file, validation, test_count, generated_at }

e2e_tests.generated:
  - Producer: E2E Test Generator
  - Consumer: Software Engineering Pipeline
  - Payload: { id, task_id, test_file, test_data, visual_tests, validation, test_count, generated_at }

mocks.generated:
  - Producer: Mock Generator
  - Consumer: Unit Test Generator, Integration Test Generator
  - Payload: { id, task_id, mock_file, fixtures, mock_count, generated_at }

mutation_tests.completed:
  - Producer: Mutation Tester
  - Consumer: Software Engineering Pipeline, Monitoring
  - Payload: { id, task_id, mutation_score, mutants_killed, mutants_lived, mutation_report, generated_at }
```

---

## Conclusão da Parte 5

O Test Generation System é o quinto componente crítico do Fluxo G, consumindo o código gerado pelo Code Forge e gerando testes automáticos (unitários, integração, E2E, mocks, mutation testing).

Este sistema produz 5 tipos principais de eventos Kafka que alimentam os sistemas downstream:
1. `unit_tests.generated` → Software Engineering Pipeline
2. `integration_tests.generated` → Software Engineering Pipeline
3. `e2e_tests.generated` → Software Engineering Pipeline
4. `mocks.generated` → Unit Test Generator, Integration Test Generator
5. `mutation_tests.completed` → Software Engineering Pipeline, Monitoring

O Test Generation System permite:
- **Geração automática de testes unitários** com análise AST, edge cases e boundary values
- **Geração automática de testes de integração** para APIs e bancos de dados
- **Geração automática de testes E2E** baseados em user stories e Cucumber scenarios
- **Geração automática de mocks** para dependências externas (databases, APIs, message queues, serviços externos)
- **Mutation testing** para validar qualidade de testes
- **Análise de qualidade de testes** (coverage, complexity, maintainability)

---

## 📚 Passo 8: Documentation Generation System (NOVO - 8014)

### Descrição Geral

Consome o código e testes gerados pelo Code Forge e Test Generation System, e gera documentação automaticamente (README, API docs, architecture docs, diagrams, inline comments).

### Componentes do Documentation Generation System

| Componente | Descrição |
|------------|-----------|
| **README Generator** | Gera README completo com instruções de instalação e uso |
| **API Docs Generator** | Gera documentação de API (OpenAPI/Swagger, API reference) |
| **Architecture Docs Generator** | Gera documentação de arquitetura (C4 diagrams, sequence diagrams, data flow) |
| **Diagram Generator** | Gera diagramas (Mermaid, PlantUML, C4, UML) |
| **Code Commenter** | Gera inline comments/docstrings para código complexo |
| **Docs Validator** | Valida documentação gerada |

### Portas e Endpoints

- **Porta API REST:** 8014
- **Health Check:** `/health`
- **Metrics:** `/metrics`
- **Endpoints:**
  - `POST /api/v1/docs/readme/generate` - Gerar README
  - `POST /api/v1/docs/api/generate` - Gerar API docs
  - `POST /api/v1/docs/architecture/generate` - Gerar architecture docs
  - `POST /api/v1/docs/diagrams/generate` - Gerar diagramas
  - `POST /api/v1/docs/comments/generate` - Gerar inline comments/docstrings
  - `POST /api/v1/docs/validate` - Validar documentação
  - `GET /api/v1/docs/{id}` - Obter documentação gerada

---

### 8.1 README Generator

**Responsabilidade:** Gerar README completo com instruções de instalação, uso, configuração e exemplos.

**Consumir:**
- `code.generated` (do Code Forge)
- `system_design.generated` (do Architectural Planning System)
- `tech_stack.selected` (do Architectural Planning System)
- `architectural.plan` (do Architectural Planning System)

**Processamento:**
```python
# services/documentation-generation/src/services/readme_generator.py

class READMEGenerator:
    async def generate_readme(self, code: dict, system_design: dict, tech_stack: dict, architecture: dict) -> dict:
        """
        Gera README completo.

        Processo:
        1. Analisar código gerado (estrutura, dependências)
        2. Analisar system design (frontends, backends, databases)
        3. Analisar tech stack (linguagens, frameworks, tools)
        4. Analisar arquitetura (bounded contexts, patterns)
        5. Gerar seções do README:
           - Title e descrição
           - Features
           - Tech stack
           - Arquitetura
           - Pré-requisitos
           - Instalação
           - Configuração
           - Uso
           - API Reference
           - Desenvolvimento
           - Testes
           - Deploy
           - Contribuição
           - Licença
        6. Gerar badges (build status, coverage, version)
        7. Adicionar exemplos de uso
        """
        # Analisar código
        code_analysis = await self._analyze_code_structure(code)

        # Analisar system design
        frontend_design = system_design.get('frontend_design', {})
        backend_design = system_design.get('backend_design', {})
        data_layer_design = system_design.get('data_layer_design', {})

        # Analisar tech stack
        backend_stack = tech_stack.get('backend', {})
        frontend_stack = tech_stack.get('frontend', {})
        database_stack = tech_stack.get('databases', {})

        # Analisar arquitetura
        bounded_contexts = architecture.get('architecture', {}).get('bounded_contexts', [])
        communication_patterns = architecture.get('architecture', {}).get('communication_patterns', [])

        # Gerar README
        readme_content = await self._generate_readme_content(
            code_analysis,
            frontend_design,
            backend_design,
            data_layer_design,
            backend_stack,
            frontend_stack,
            database_stack,
            bounded_contexts,
            communication_patterns
        )

        # Gerar badges
        badges = await self._generate_badges(tech_stack, architecture)

        # Validar README
        validation_result = await self._validate_readme(readme_content)

        return {
            "readme": readme_content,
            "badges": badges,
            "validation": validation_result,
            "generated_at": datetime.utcnow().isoformat()
        }

    async def _generate_readme_content(self, code_analysis: dict, frontend_design: dict, backend_design: dict, data_layer_design: dict, backend_stack: dict, frontend_stack: dict, database_stack: dict, bounded_contexts: List[dict], communication_patterns: List[dict]) -> str:
        """
        Gera conteúdo do README.
        """
        project_name = code_analysis.get('project_name', 'My Project')
        project_description = code_analysis.get('description', 'Description')

        readme = f"""# {project_name}

{badges}

## Description

{project_description}

## Features

{await self._generate_features_section(backend_design, frontend_design)}

## Tech Stack

### Backend

{await self._generate_tech_stack_section(backend_stack)}

### Frontend

{await self._generate_tech_stack_section(frontend_stack)}

### Databases

{await self._generate_database_section(database_stack)}

### Infrastructure

{await self._generate_infrastructure_section(data_layer_design)}

## Architecture

{await self._generate_architecture_section(bounded_contexts, communication_patterns)}

## Prerequisites

{await self._generate_prerequisites_section(backend_stack, frontend_stack, database_stack)}

## Installation

{await self._generate_installation_section(code_analysis, backend_stack)}

## Configuration

{await self._generate_configuration_section(code_analysis, backend_stack)}

## Usage

{await self._generate_usage_section(backend_design, frontend_design)}

## API Reference

{await self._generate_api_reference_section(backend_design)}

## Development

{await self._generate_development_section(code_analysis, backend_stack)}

## Testing

{await self._generate_testing_section(code_analysis)}

## Deployment

{await self._generate_deployment_section(data_layer_design)}

## Contributing

{await self._generate_contributing_section()}

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
"""

        return readme

    async def _generate_features_section(self, backend_design: dict, frontend_design: dict) -> str:
        """
        Gera seção de features.
        """
        features = []

        # Backend features
        backend_services = backend_design.get('services', [])
        for service in backend_services:
            responsibilities = service.get('responsibilities', [])
            for resp in responsibilities:
                features.append(f"- {resp}")

        # Frontend features
        frontend_components = frontend_design.get('components', [])
        for component in frontend_components:
            feature_desc = f"- {component.get('name', 'Component')}: {component.get('description', 'Description')}"
            features.append(feature_desc)

        features_text = "\n".join(features)

        return f"""### Backend

- Multi-service architecture with {len(backend_services)} microservices
- Event-driven communication via Kafka
- RESTful API with OpenAPI/Swagger documentation
- JWT-based authentication and authorization
- Redis caching for performance optimization
- PostgreSQL/MongoDB polyglot persistence

### Frontend

- React Native mobile application (iOS and Android)
- React web application for restaurant admins
- Real-time updates via WebSockets
- Push notifications support
- Biometric authentication (FaceID, TouchID)
- Offline-first architecture with cache

### Core Features

{features_text}
"""

    async def _generate_tech_stack_section(self, tech_stack: dict) -> str:
        """
        Gera seção de tech stack.
        """
        language = tech_stack.get('language', 'Unknown')
        framework = tech_stack.get('framework', 'Unknown')
        tools = tech_stack.get('tools', [])

        tech_stack_text = "- **Language:** {language}\n"
        tech_stack_text += f"- **Framework:** {framework}\n"

        if tools:
            tech_stack_text += "\n**Tools:**\n"
            for tool in tools:
                tech_stack_text += f"- {tool.get('name', 'Tool')} - {tool.get('description', 'Description')}\n"

        return tech_stack_text

    async def _generate_installation_section(self, code_analysis: dict, backend_stack: dict) -> str:
        """
        Gera seção de instalação.
        """
        language = backend_stack.get('language', 'python')

        installation_section = "## Installation\n\n"

        if language == 'python':
            installation_section += """### Prerequisites

- Python 3.12 or higher
- pip (Python package manager)
- Docker and Docker Compose (for local development)
- PostgreSQL 15+ (for local development)
- Redis 7.0+ (for local development)
- Kafka 3.5+ (for local development)

### Clone the repository

```bash
git clone https://github.com/neural-hive-mind/my-project.git
cd my-project
```

### Install dependencies

```bash
pip install -r requirements.txt
```

### Setup environment variables

```bash
cp .env.example .env
# Edit .env with your configuration
```

### Run database migrations

```bash
alembic upgrade head
```

### Start services locally

```bash
docker-compose up -d
```

### Verify installation

```bash
# Check health of API Gateway
curl http://localhost:8000/health

# Check health of User Service
curl http://localhost:8010/health
```
"""
        elif language == 'javascript':
            installation_section += """### Prerequisites

- Node.js 18 or higher
- npm or yarn package manager
- Docker and Docker Compose (for local development)

### Clone the repository

```bash
git clone https://github.com/neural-hive-mind/my-project.git
cd my-project
```

### Install dependencies

```bash
npm install
# or
yarn install
```

### Setup environment variables

```bash
cp .env.example .env
# Edit .env with your configuration
```

### Run database migrations

```bash
npm run migrate
# or
yarn migrate
```

### Start services locally

```bash
docker-compose up -d
```

### Verify installation

```bash
npm run dev
# or
yarn dev
```
"""
        else:
            installation_section += "### Prerequisites\n\nSee project-specific requirements in documentation.\n\n"

        return installation_section

    async def _generate_badges(self, tech_stack: dict, architecture: dict) -> str:
        """
        Gera badges para README.
        """
        language = tech_stack.get('backend', {}).get('language', 'python')
        framework = tech_stack.get('backend', {}).get('framework', 'Unknown')
        architecture_type = architecture.get('architecture', {}).get('architecture_type', 'microservices')

        badges = []
        badges.append(f"[![Language](https://img.shields.io/badge/language-{language}-blue.svg)]")
        badges.append(f"[![Framework](https://img.shields.io/badge/framework-{framework}-green.svg)]")
        badges.append(f"[![License](https://img.shields.io/badge/license-MIT-yellow.svg)]")
        badges.append("[![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)]")
        badges.append("[![Coverage](https://img.shields.io/badge/coverage-80%25-important.svg)]")
        badges.append(f"[![Architecture](https://img.shields.io/badge/architecture-{architecture_type}-orange.svg)]")

        badges_html = "\n".join(badges)

        return f"""{badges_html}
"""
```

**Output:**
```json
{
  "readme": {
    "filename": "README.md",
    "content": "# My Delivery App\n\n[![Language](https://img.shields.io/badge/language-python-blue.svg)]\n[![Framework](https://img.shields.io/badge/framework-FastAPI-green.svg)]\n[![License](https://img.shields.io/badge/license-MIT-yellow.svg)]\n[![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)]\n[![Coverage](https://img.shields.io/badge/coverage-80%25-important.svg)]\n[![Architecture](https://img.shields.io/badge/architecture-microservices-orange.svg)]\n\n## Description\n\nFood delivery platform with real-time tracking, multiple restaurant support, and payment integration.\n\n## Features\n\n### Backend\n\n- Multi-service architecture with 6 microservices\n- Event-driven communication via Kafka\n- RESTful API with OpenAPI/Swagger documentation\n- JWT-based authentication and authorization\n- Redis caching for performance optimization\n- PostgreSQL/MongoDB polyglot persistence\n\n### Frontend\n\n- React Native mobile application (iOS and Android)\n- React web application for restaurant admins\n- Real-time updates via WebSockets\n- Push notifications support\n- Biometric authentication (FaceID, TouchID)\n- Offline-first architecture with cache\n\n### Core Features\n\n- User registration and authentication\n- Restaurant browsing and search\n- Menu management for restaurants\n- Order creation and real-time tracking\n- Payment processing (Stripe, Mercado Pago)\n- Delivery person management and routing\n- Push notifications and alerts\n\n## Tech Stack\n\n### Backend\n\n- **Language:** Python\n- **Framework:** FastAPI\n\n**Tools:**\n- SQLAlchemy - ORM for PostgreSQL\n- Motor - Async MongoDB driver\n- aiokafka - Async Kafka client\n- Redis-py - Redis client\n- Pydantic - Data validation\n- JWT - Authentication\n\n### Frontend\n\n- **Language:** TypeScript\n- **Framework:** React\n\n**Tools:**\n- React Native - Mobile framework\n- Redux Toolkit - State management\n- Axios - HTTP client\n- Socket.IO - WebSocket client\n- Expo - Mobile development platform\n\n### Databases\n\n- **Primary:** PostgreSQL - Relational data\n- **Document:** MongoDB - Notifications\n- **Cache:** Redis - Caching layer\n\n### Infrastructure\n\n- **Message Queue:** Kafka - Event streaming\n- **API Gateway:** Kong - API management\n- **Observability:** ELK Stack + Prometheus + Grafana + Jaeger\n\n## Architecture\n\nThe application follows a microservices architecture with event-driven communication.\n\n### Bounded Contexts\n\n1. **User Management** - User registration, authentication, profiles\n2. **Restaurant Catalog** - Restaurant listings, menus, reviews\n3. **Order Management** - Order creation, status updates, history\n4. **Payment Processing** - Payment integration, refunds\n5. **Delivery Management** - Delivery person management, routing\n6. **Notification** - Push notifications, email, SMS\n\n### Communication Patterns\n\n- **Event-Driven:** Asynchronous communication via Kafka\n- **REST API:** Synchronous HTTP APIs for frontend\n\n## Prerequisites\n\n### Backend\n\n- Python 3.12 or higher\n- pip (Python package manager)\n- Docker and Docker Compose (for local development)\n- PostgreSQL 15+ (for local development)\n- Redis 7.0+ (for local development)\n- Kafka 3.5+ (for local development)\n\n### Frontend\n\n- Node.js 18 or higher\n- npm or yarn package manager\n- Docker and Docker Compose (for local development)\n\n## Installation\n\n### Clone the repository\n\n```bash\ngit clone https://github.com/neural-hive-mind/my-delivery-app.git\ncd my-delivery-app\n```\n\n### Install backend dependencies\n\n```bash\ncd services/user-service\npip install -r requirements.txt\n```\n\n### Install frontend dependencies\n\n```bash\ncd frontend/mobile-app\nnpm install\n```\n\n### Setup environment variables\n\n```bash\ncp .env.example .env\n# Edit .env with your configuration\n```\n\n### Run database migrations\n\n```bash\nalembic upgrade head\n```\n\n### Start services locally\n\n```bash\ndocker-compose up -d\n```\n\n### Verify installation\n\n```bash\n# Check health of API Gateway\ncurl http://localhost:8000/health\n\n# Check health of User Service\ncurl http://localhost:8010/health\n```\n\n## Usage\n\n### Running the application\n\n```bash\n# Start backend services\ndocker-compose up -d\n\n# Start mobile app\ncd frontend/mobile-app\nnpm run ios  # for iOS\nnpm run android  # for Android\n\n# Start admin web app\ncd frontend/admin-app\nnpm run dev\n```\n\n### API Endpoints\n\nSee [API Documentation](./docs/api.md) for full API reference.\n\n## Development\n\n### Running tests\n\n```bash\n# Backend tests\ncd services/user-service\npytest\n\n# Frontend tests\ncd frontend/mobile-app\nnpm test\n```\n\n## License\n\nThis project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.\n",
    "badges": [
      "[![Language](https://img.shields.io/badge/language-python-blue.svg)]",
      "[![Framework](https://img.shields.io/badge/framework-FastAPI-green.svg)]",
      "[![License](https://img.shields.io/badge/license-MIT-yellow.svg)]",
      "[![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)]",
      "[![Coverage](https://img.shields.io/badge/coverage-80%25-important.svg)]",
      "[![Architecture](https://img.shields.io/badge/architecture-microservices-orange.svg)]"
    ]
  },
  "validation": {
    "is_valid": true,
    "errors": [],
    "warnings": [],
    "lint_score": 9.8
  },
  "generated_at": "2026-04-15T17:00:00Z"
}
```

---

### 8.2 API Docs Generator

**Responsabilidade:** Gera documentação de API (OpenAPI/Swagger specs, API reference docs).

**Consumir:**
- `api_designs.generated` (do Requirements Engineering System)
- `code.generated` (do Code Forge)
- `architectural.plan` (do Architectural Planning System)

**Processamento:**
```python
# services/documentation-generation/src/services/api_docs_generator.py

class APIDocsGenerator:
    async def generate_api_docs(self, api_design: dict, code: dict, architecture: dict) -> dict:
        """
        Gera documentação de API.

        Processo:
        1. Analisar API design (endpoints, schemas, auth)
        2. Analisar código gerado para validar implementação
        3. Gerar OpenAPI/Swagger spec completo
        4. Gerar documentação de referência (endpoints detalhados)
        5. Gerar exemplos de request/response
        6. Gerar guias de autenticação/autorização
        7. Gerar códigos de erro
        """
        # Analisar API design
        endpoints = api_design.get('endpoints', [])
        openapi_spec = api_design.get('openapi_spec', {})

        # Analisar código
        code_analysis = await self._analyze_code_endpoints(code, endpoints)

        # Gerar OpenAPI spec atualizado
        updated_openapi_spec = await self._generate_openapi_spec(api_design, code_analysis)

        # Gerar documentação de referência
        api_reference = await self._generate_api_reference(api_design, code_analysis)

        # Gerar exemplos
        examples = await self._generate_examples(api_design, architecture)

        # Gerar guias de auth
        auth_guides = await self._generate_auth_guides(api_design)

        # Gerar códigos de erro
        error_codes = await self._generate_error_codes(api_design)

        return {
            "openapi_spec": updated_openapi_spec,
            "api_reference": api_reference,
            "examples": examples,
            "auth_guides": auth_guides,
            "error_codes": error_codes,
            "generated_at": datetime.utcnow().isoformat()
        }

    async def _generate_openapi_spec(self, api_design: dict, code_analysis: dict) -> dict:
        """
        Gera OpenAPI/Swagger spec completo.
        """
        endpoints = api_design.get('endpoints', [])
        auth_strategy = api_design.get('auth_strategy', {})
        base_url = api_design.get('base_url', 'http://localhost:8000')

        openapi_spec = {
            "openapi": "3.0.0",
            "info": {
                "title": api_design.get('title', 'API'),
                "version": api_design.get('version', '1.0.0'),
                "description": api_design.get('description', 'API Description'),
                "contact": {
                    "name": "API Support",
                    "email": "support@example.com"
                },
                "license": {
                    "name": "MIT"
                }
            },
            "servers": [
                {
                    "url": base_url,
                    "description": "Development server"
                },
                {
                    "url": "https://api.example.com/v1",
                    "description": "Production server"
                }
            ],
            "security": await self._generate_security_schemes(auth_strategy),
            "paths": await self._generate_paths(endpoints, code_analysis),
            "components": await self._generate_components(api_design, code_analysis)
        }

        return openapi_spec

    async def _generate_paths(self, endpoints: List[dict], code_analysis: dict) -> dict:
        """
        Gera seção paths do OpenAPI spec.
        """
        paths = {}

        for endpoint in endpoints:
            path = endpoint.get('path')
            method = endpoint.get('method').lower()
            description = endpoint.get('description', '')
            tags = endpoint.get('tags', [])
            request_body = endpoint.get('request_body')
            responses = endpoint.get('response', {})

            if path not in paths:
                paths[path] = {}

            paths[path][method] = {
                "summary": description,
                "description": description,
                "tags": tags,
                "operationId": await self._generate_operation_id(path, method),
                "requestBody": await self._generate_request_body(request_body),
                "responses": await self._generate_responses(responses),
                "security": await self._generate_security(tags)
            }

        return paths

    async def _generate_components(self, api_design: dict, code_analysis: dict) -> dict:
        """
        Gera seção components do OpenAPI spec.
        """
        components = {
            "schemas": await self._generate_schemas(api_design, code_analysis),
            "securitySchemes": await self._generate_security_schemes(api_design.get('auth_strategy', {}))
        }

        return components

    async def _generate_schemas(self, api_design: dict, code_analysis: dict) -> dict:
        """
        Gera schemas do OpenAPI spec.
        """
        schemas = {}

        # Obter schemas de request/response
        for endpoint in api_design.get('endpoints', []):
            request_body = endpoint.get('request_body', {})
            responses = endpoint.get('response', {})

            # Obter schema de request body
            if 'schema' in request_body:
                schema = request_body['schema']
                schema_name = await self._extract_schema_name(request_body.get('description', ''))
                schemas[schema_name] = schema

            # Obter schemas de response
            for status_code, response_data in responses.items():
                if 'content' in response_data:
                    content = response_data['content']
                    if 'application/json' in content:
                        if 'schema' in content['application/json']:
                            schema = content['application/json']['schema']
                            schema_name = await self._extract_schema_name(response_data.get('description', ''))
                            schemas[schema_name] = schema

        # Obter schemas do código
        code_schemas = await self._extract_schemas_from_code(code_analysis)
        schemas.update(code_schemas)

        return schemas

    async def _generate_api_reference(self, api_design: dict, code_analysis: dict) -> str:
        """
        Gera documentação de referência de API.
        """
        endpoints = api_design.get('endpoints', [])

        api_ref = """# API Reference

## Authentication

All API endpoints require authentication using JWT Bearer tokens.

```bash
# Include JWT token in request header
Authorization: Bearer <your-jwt-token>
```

## Endpoints

"""

        for endpoint in endpoints:
            path = endpoint.get('path')
            method = endpoint.get('method')
            description = endpoint.get('description', '')
            tags = endpoint.get('tags', [])
            request_body = endpoint.get('request_body', {})
            responses = endpoint.get('response', {})

            api_ref += f"""### {method.upper()} {path}

**Tags:** {', '.join(tags)}

**Description:** {description}

#### Request

**Method:** {method.upper()}
**Endpoint:** {path}
**Content-Type:** application/json

**Request Body:**

```json
{json.dumps(request_body.get('schema', {}), indent=2)}
```

#### Response

{await self._generate_response_documentation(responses)}

---

"""

        return api_ref
```

**Output:**
```json
{
  "openapi_spec": {
    "openapi": "3.0.0",
    "info": {
      "title": "Delivery App API",
      "version": "1.0.0",
      "description": "Food delivery platform API",
      "contact": {
        "name": "API Support",
        "email": "support@example.com"
      },
      "license": {
        "name": "MIT"
      }
    },
    "servers": [
      {
        "url": "http://localhost:8000/v1",
        "description": "Development server"
      },
      {
        "url": "https://api.deliveryapp.com/v1",
        "description": "Production server"
      }
    ],
    "security": [
      {
        "ApiKeyAuth": []
      },
      {
        "BearerAuth": []
      }
    ],
    "paths": {
      "/users": {
        "post": {
          "summary": "Criar usuário",
          "description": "Cria um novo usuário no sistema",
          "tags": ["users"],
          "operationId": "createUser",
          "requestBody": {
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/CreateUserRequest"
                }
              }
            },
            "required": true
          },
          "responses": {
            "201": {
              "description": "Usuário criado com sucesso",
              "content": {
                "application/json": {
                  "schema": {
                    "$ref": "#/components/schemas/User"
                  }
                }
              }
            },
            "400": {
              "description": "Dados inválidos",
              "content": {
                "application/json": {
                  "schema": {
                    "$ref": "#/components/schemas/Error"
                  }
                }
              }
            }
          }
        }
      },
      "/users/{user_id}": {
        "get": {
          "summary": "Buscar usuário",
          "description": "Busca um usuário por ID",
          "tags": ["users"],
          "operationId": "getUser",
          "parameters": [
            {
              "name": "user_id",
              "in": "path",
              "required": true,
              "schema": {
                "type": "string",
                "format": "uuid"
              }
            }
          ],
          "responses": {
            "200": {
              "description": "Usuário encontrado",
              "content": {
                "application/json": {
                  "schema": {
                    "$ref": "#/components/schemas/User"
                  }
                }
              }
            },
            "404": {
              "description": "Usuário não encontrado"
            }
          }
        }
      }
    },
    "components": {
      "schemas": {
        "CreateUserRequest": {
          "type": "object",
          "required": ["email", "password", "name"],
          "properties": {
            "email": {
              "type": "string",
              "format": "email"
            },
            "password": {
              "type": "string",
              "minLength": 8
            },
            "name": {
              "type": "string",
              "minLength": 2
            }
          }
        },
        "User": {
          "type": "object",
          "properties": {
            "id": {
              "type": "string",
              "format": "uuid"
            },
            "email": {
              "type": "string",
              "format": "email"
            },
            "name": {
              "type": "string"
            },
            "created_at": {
              "type": "string",
              "format": "date-time"
            }
          }
        },
        "Error": {
          "type": "object",
          "properties": {
            "error": {
              "type": "string"
            },
            "message": {
              "type": "string"
            }
          }
        }
      },
      "securitySchemes": {
        "ApiKeyAuth": {
          "type": "apiKey",
          "in": "header",
          "name": "X-API-Key"
        },
        "BearerAuth": {
          "type": "http",
          "scheme": "bearer",
          "bearerFormat": "JWT"
        }
      }
    }
  },
  "api_reference": {
    "filename": "docs/api.md",
    "content": "# API Reference\n\n## Authentication\n\nAll API endpoints require authentication using JWT Bearer tokens.\n\n```bash\n# Include JWT token in request header\nAuthorization: Bearer <your-jwt-token>\n```\n\n## Endpoints\n\n### POST /users\n\n**Tags:** users\n\n**Description:** Cria um novo usuário no sistema\n\n#### Request\n\n**Method:** POST\n**Endpoint:** /users\n**Content-Type:** application/json\n\n**Request Body:**\n\n```json\n{\n  \"email\": \"test@example.com\",\n  \"password\": \"password123\",\n  \"name\": \"Test User\"\n}\n```\n\n#### Response\n\n**201 Created**\n\nUsuário criado com sucesso\n\n```json\n{\n  \"id\": \"uuid-v4\",\n  \"email\": \"test@example.com\",\n  \"name\": \"Test User\",\n  \"created_at\": \"2026-04-15T17:00:00Z\"\n}\n```\n\n**400 Bad Request**\n\nDados inválidos\n\n```json\n{\n  \"error\": \"Validation error\",\n  \"message\": \"Email is invalid\"\n}\n```\n\n---\n\n### GET /users/{user_id}\n\n**Tags:** users\n\n**Description:** Busca um usuário por ID\n\n#### Request\n\n**Method:** GET\n**Endpoint:** /users/{user_id}\n\n**Path Parameters:**\n\n| Name | Type | Required | Description |\n|------|------|----------|-------------|\n| user_id | string (UUID) | Yes | ID do usuário |\n\n#### Response\n\n**200 OK**\n\nUsuário encontrado\n\n```json\n{\n  \"id\": \"uuid-v4\",\n  \"email\": \"test@example.com\",\n  \"name\": \"Test User\",\n  \"created_at\": \"2026-04-15T17:00:00Z\"\n}\n```\n\n**404 Not Found**\n\nUsuário não encontrado\n\n```json\n{\n  \"error\": \"Not Found\",\n  \"message\": \"User not found\"\n}\n```\n\n---"
  },
  "examples": {
    "user_registration": {
      "description": "Exemplo de registro de usuário",
      "request": {
        "method": "POST",
        "url": "/api/v1/users",
        "headers": {
          "Content-Type": "application/json"
        },
        "body": {
          "email": "test@example.com",
          "password": "password123",
          "name": "Test User"
        }
      },
      "response": {
        "status": 201,
        "headers": {
          "Content-Type": "application/json"
        },
        "body": {
          "id": "uuid-v4",
          "email": "test@example.com",
          "name": "Test User",
          "created_at": "2026-04-15T17:00:00Z"
        }
      }
    }
  },
  "auth_guides": {
    "jwt_authentication": {
      "description": "Guia de autenticação JWT",
      "steps": [
        "1. Fazer login na API POST /api/v1/auth/login",
        "2. Receber access_token e refresh_token na resposta",
        "3. Incluir access_token no header Authorization: Bearer <token>",
        "4. Usar refresh_token para renovar o token antes de expirar"
      ],
      "code_example": "```bash\n# Login e obter token\ncurl -X POST http://localhost:8000/api/v1/auth/login \\\n  -H 'Content-Type: application/json' \\\n  -d '{\n    \"email\": \"test@example.com\",\n    \"password\": \"password123\"\n  }'\n\n# Usar token em requests subsequentes\ncurl -X GET http://localhost:8000/api/v1/users/me \\\n  -H 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...'\n```"
    }
  },
  "error_codes": {
    "400": {
      "code": "VALIDATION_ERROR",
      "message": "Dados de entrada inválidos",
      "description": "Os dados fornecidos não passaram na validação"
    },
    "401": {
      "code": "UNAUTHORIZED",
      "message": "Autenticação necessária",
      "description": "É necessário fornecer credenciais válidas"
    },
    "403": {
      "code": "FORBIDDEN",
      "message": "Permissão insuficiente",
      "description": "O usuário não tem permissão para acessar este recurso"
    },
    "404": {
      "code": "NOT_FOUND",
      "message": "Recurso não encontrado",
      "description": "O recurso solicitado não existe"
    },
    "409": {
      "code": "CONFLICT",
      "message": "Conflito de dados",
      "description": "Já existe um recurso com estes dados"
    },
    "500": {
      "code": "INTERNAL_SERVER_ERROR",
      "message": "Erro interno do servidor",
      "description": "Ocorreu um erro inesperado no servidor"
    }
  },
  "generated_at": "2026-04-15T17:00:00Z"
}
```

---

### 8.3 Architecture Docs Generator

**Responsabilidade:** Gera documentação de arquitetura (C4 diagrams, sequence diagrams, data flow).

**Consumir:**
- `architectural.plan` (do Architectural Planning System)
- `system_design.generated` (do Architectural Planning System)
- `diagrams.generated` (do Architectural Planning System)

**Processamento:**
```python
# services/documentation-generation/src/services/architecture_docs_generator.py

class ArchitectureDocsGenerator:
    async def generate_architecture_docs(self, architecture: dict, system_design: dict, diagrams: dict) -> dict:
        """
        Gera documentação de arquitetura.

        Processo:
        1. Analisar arquitetura (bounded contexts, communication patterns)
        2. Analisar system design (frontend, backend, databases)
        3. Gerar C4 diagrams
        4. Gerar sequence diagrams
        5. Gerar data flow documentation
        6. Gerar arquitetural decision records (ADRs)
        """
        # Analisar arquitetura
        bounded_contexts = architecture.get('architecture', {}).get('bounded_contexts', [])
        communication_patterns = architecture.get('architecture', {}).get('communication_patterns', [])

        # Analisar system design
        frontend_design = system_design.get('frontend_design', {})
        backend_design = system_design.get('backend_design', {})
        data_layer_design = system_design.get('data_layer_design', {})

        # Gerar C4 diagrams
        c4_diagrams = await self._generate_c4_diagrams(
            bounded_contexts,
            frontend_design,
            backend_design,
            data_layer_design
        )

        # Gerar sequence diagrams
        sequence_diagrams = await self._generate_sequence_diagrams(
            system_design,
            communication_patterns
        )

        # Gerar data flow documentation
        data_flow_docs = await self._generate_data_flow_docs(
            system_design,
            communication_patterns
        )

        # Gerar ADRs
        adrs = architecture.get('architectural_decision_records', [])

        # Gerar documentação consolidada
        architecture_docs = await self._generate_architecture_docs_content(
            architecture,
            system_design,
            c4_diagrams,
            sequence_diagrams,
            data_flow_docs,
            adrs
        )

        return {
            "architecture_docs": architecture_docs,
            "c4_diagrams": c4_diagrams,
            "sequence_diagrams": sequence_diagrams,
            "data_flow_docs": data_flow_docs,
            "generated_at": datetime.utcnow().isoformat()
        }

    async def _generate_c4_diagrams(self, bounded_contexts: List[dict], frontend_design: dict, backend_design: dict, data_layer_design: dict) -> dict:
        """
        Gera C4 diagrams (Context, Container, Component, Code).
        """
        c4_diagrams = {}

        # C4 Level 1: Context Diagram
        c4_diagrams['context'] = await self._generate_context_diagram(
            bounded_contexts,
            frontend_design,
            backend_design
        )

        # C4 Level 2: Container Diagram
        c4_diagrams['container'] = await self._generate_container_diagram(
            bounded_contexts,
            frontend_design,
            backend_design,
            data_layer_design
        )

        # C4 Level 3: Component Diagram
        c4_diagrams['component'] = await self._generate_component_diagram(
            bounded_contexts,
            backend_design,
            data_layer_design
        )

        # C4 Level 4: Code Diagram
        c4_diagrams['code'] = await self._generate_code_diagram(
            bounded_contexts,
            backend_design
        )

        return c4_diagrams

    async def _generate_context_diagram(self, bounded_contexts: List[dict], frontend_design: dict, backend_design: dict) -> str:
        """
        Gera C4 Context Diagram.
        """
        # Identificar usuários externos
        users = []
        for component in frontend_design.get('components', []):
            if 'Mobile App' in component.get('name', ''):
                users.append('Customer (Mobile)')
            elif 'Web App' in component.get('name', ''):
                users.append('Restaurant Owner (Web)')
            elif 'Admin Dashboard' in component.get('name', ''):
                users.append('Platform Admin (Web)')

        # Criar diagrama
        context_diagram = """# C4 Model: Context Diagram

## System Context

```mermaid
C4Context
    title "Delivery App System Context"
    
    Person(customer, "Customer", "A user who wants to order food")
    Person(restaurant_owner, "Restaurant Owner", "A restaurant owner who wants to manage their business")
    Person(platform_admin, "Platform Admin", "An admin who wants to manage the platform")

    System_Boundary(c1, "Delivery App", "") {
        System(user_service, "User Service", "User management and authentication")
        System(restaurant_service, "Restaurant Service", "Restaurant and menu management")
        System(order_service, "Order Service", "Order creation and management")
        System(payment_service, "Payment Service", "Payment processing")
        System(delivery_service, "Delivery Service", "Delivery management and routing")
        System(notification_service, "Notification Service", "Notifications and alerts")
    }
    
    Rel(customer, user_service, "Uses", "Register, login, manage profile")
    Rel(customer, restaurant_service, "Uses", "Browse restaurants, view menus")
    Rel(customer, order_service, "Uses", "Create orders, track delivery")
    Rel(customer, payment_service, "Uses", "Pay for orders")
    Rel(customer, delivery_service, "Uses", "Track delivery in real-time")
    Rel(restaurant_owner, user_service, "Uses", "Manage restaurant account")
    Rel(restaurant_owner, restaurant_service, "Uses", "Manage restaurant, menu, orders")
    Rel(platform_admin, user_service, "Uses", "Manage users")
    Rel(platform_admin, restaurant_service, "Uses", "Moderate restaurants")
    Rel(platform_admin, order_service, "Uses", "Monitor orders")
    Rel(platform_admin, delivery_service, "Uses", "Manage delivery persons")
```

## Description

The **Delivery App** is a food delivery platform that allows customers to order food from restaurants, restaurant owners to manage their business, and platform admins to manage the overall system.

### External Users

- **Customer**: Uses mobile app to browse restaurants, place orders, and track deliveries
- **Restaurant Owner**: Uses web app to manage restaurant information, menu, and orders
- **Platform Admin**: Uses admin dashboard to manage users, restaurants, and platform configuration

### Core Systems

- **User Service**: Manages user accounts, authentication, and profiles
- **Restaurant Service**: Manages restaurant listings, menus, and reviews
- **Order Service**: Manages order creation, status updates, and history
- **Payment Service**: Processes payments via Stripe and Mercado Pago
- **Delivery Service**: Manages delivery persons, routing, and real-time tracking
- **Notification Service**: Sends push notifications, emails, and SMS alerts
"""

        return context_diagram

    async def _generate_architecture_docs_content(self, architecture: dict, system_design: dict, c4_diagrams: dict, sequence_diagrams: dict, data_flow_docs: dict, adrs: List[dict]) -> str:
        """
        Gera documentação de arquitetura consolidada.
        """
        architecture_type = architecture.get('architecture', {}).get('architecture_type', 'microservices')

        docs = f"""# Architecture Documentation

## Architecture Overview

The Delivery App follows a **{architecture_type} architecture** with event-driven communication via Kafka.

## High-Level Architecture

### Bounded Contexts

{await self._generate_bounded_contexts_section(architecture)}

### Communication Patterns

{await self._generate_communication_patterns_section(architecture)}

## C4 Diagrams

### Context Diagram

{c4_diagrams.get('context', '')}

### Container Diagram

{c4_diagrams.get('container', '')}

### Component Diagram

{c4_diagrams.get('component', '')}

## Sequence Diagrams

{await self._generate_sequence_diagrams_section(sequence_diagrams)}

## Data Flow

{data_flow_docs.get('overview', '')}

## Architectural Decision Records (ADRs)

{await self._generate_adrs_section(adrs)}

## Technology Stack

### Frontend

{await self._generate_frontend_tech_stack(system_design)}

### Backend

{await self._generate_backend_tech_stack(system_design)}

### Databases

{await self._generate_database_tech_stack(system_design)}

### Infrastructure

{await self._generate_infrastructure_tech_stack(system_design)}

## Deployment Architecture

{await self._generate_deployment_architecture_section(system_design)}

## Scalability and Performance

{await self._generate_scalability_section(system_design)}

## Security

{await self._generate_security_section(system_design)}

## Observability

{await self._generate_observability_section(system_design)}
"""

        return docs
```

**Output:**
```json
{
  "architecture_docs": {
    "filename": "docs/architecture.md",
    "content": "# Architecture Documentation\n\n## Architecture Overview\n\nThe Delivery App follows a **microservices architecture** with event-driven communication via Kafka.\n\n## High-Level Architecture\n\n### Bounded Contexts\n\nThe system is organized into the following bounded contexts:\n\n#### 1. User Management\n\n**Responsibility:** User accounts, authentication, and profiles\n\n**Services:**\n- `user-service` (Python FastAPI, port 8010)\n\n**Database:** PostgreSQL (user_db)\n\n**Kafka Topics:**\n- `users.created` (producer)\n- `users.updated` (producer)\n\n#### 2. Restaurant Catalog\n\n**Responsibility:** Restaurant listings, menus, and reviews\n\n**Services:**\n- `restaurant-service` (Python FastAPI, port 8011)\n\n**Database:** PostgreSQL (restaurant_db)\n\n**Kafka Topics:**\n- `restaurants.created` (producer)\n- `restaurants.updated` (producer)\n\n#### 3. Order Management\n\n**Responsibility:** Order creation, status updates, and history\n\n**Services:**\n- `order-service` (Python FastAPI, port 8012)\n\n**Database:** PostgreSQL (order_db)\n\n**Kafka Topics:**\n- `orders.created` (producer/consumer)\n- `orders.status.changed` (producer)\n- `payments.completed` (consumer)\n- `payments.failed` (consumer)\n\n---\n\n## C4 Diagrams\n\n### Context Diagram\n\n```mermaid\nC4Context\n    title \"Delivery App System Context\"\n    \n    Person(customer, \"Customer\", \"A user who wants to order food\")\n    Person(restaurant_owner, \"Restaurant Owner\", \"A restaurant owner who wants to manage their business\")\n    Person(platform_admin, \"Platform Admin\", \"An admin who wants to manage the platform\")\n\n    System_Boundary(c1, \"Delivery App\", \"\") {\n        System(user_service, \"User Service\", \"User management and authentication\")\n        System(restaurant_service, \"Restaurant Service\", \"Restaurant and menu management\")\n        System(order_service, \"Order Service\", \"Order creation and management\")\n        System(payment_service, \"Payment Service\", \"Payment processing\")\n        System(delivery_service, \"Delivery Service\", \"Delivery management and routing\")\n        System(notification_service, \"Notification Service\", \"Notifications and alerts\")\n    }\n    \n    Rel(customer, user_service, \"Uses\", \"Register, login, manage profile\")\n    Rel(customer, restaurant_service, \"Uses\", \"Browse restaurants, view menus\")\n    Rel(customer, order_service, \"Uses\", \"Create orders, track delivery\")\n    Rel(customer, payment_service, \"Uses\", \"Pay for orders\")\n    Rel(customer, delivery_service, \"Uses\", \"Track delivery in real-time\")\n    Rel(restaurant_owner, user_service, \"Uses\", \"Manage restaurant account\")\n    Rel(restaurant_owner, restaurant_service, \"Uses\", \"Manage restaurant, menu, orders\")\n    Rel(platform_admin, user_service, \"Uses\", \"Manage users\")\n    Rel(platform_admin, restaurant_service, \"Uses\", \"Moderate restaurants\")\n    Rel(platform_admin, order_service, \"Uses\", \"Monitor orders\")\n    Rel(platform_admin, delivery_service, \"Uses\", \"Manage delivery persons\")\n```\n\n## Sequence Diagrams\n\n### Order Creation Flow\n\n```mermaid\nsequenceDiagram\n    participant Customer as Customer\n    participant MobileApp as Mobile App\n    participant APIGateway as API Gateway\n    participant UserService as User Service\n    participant RestaurantService as Restaurant Service\n    participant OrderService as Order Service\n    participant PaymentService as Payment Service\n    participant DeliveryService as Delivery Service\n    participant NotificationService as Notification Service\n\n    Customer->>MobileApp: Select restaurant and items\n    MobileApp->>APIGateway: POST /api/v1/orders\n    APIGateway->>OrderService: Forward order request\n    OrderService->>RestaurantService: Validate availability\n    RestaurantService-->>OrderService: Available\n    OrderService->>OrderService: Calculate total\n    OrderService->>APIGateway: Return order\n    APIGateway-->>MobileApp: 201 Order Created\n\n    APIGateway->>PaymentService: Process payment\n    PaymentService->>PaymentService: Charge card\n    PaymentService-->>APIGateway: Payment completed\n    \n    APIGateway->>OrderService: Update order status\n    OrderService->>NotificationService: Send notification\n    NotificationService-->>Customer: Push: Order confirmed\n    \n    APIGateway->>DeliveryService: Assign delivery person\n    DeliveryService->>MobileApp: WebSocket: Delivery assigned\n```\n\n---\n\n## Architectural Decision Records (ADRs)\n\n### ADR-001: Choice of Microservices Architecture\n\n**Status:** Accepted\n\n**Date:** 2026-04-15\n\n**Context:** The system needs to scale independently for different bounded contexts (users, restaurants, orders, deliveries). The team has 5+ developers and the budget allows the complexity.\n\n**Decision:** Adopt microservices architecture with event-driven communication via Kafka.\n\n**Consequences:**\n- **Positive:** Independent scaling, independent deployment, fault isolation\n- **Negative:** Increased complexity, distributed transactions, network latency\n\n### ADR-002: Event-Driven Communication via Kafka\n\n**Status:** Accepted\n\n**Date:** 2026-04-15\n\n**Context:** Microservices need to communicate asynchronously and decoupled. High throughput of events (orders, payments, deliveries).\n\n**Decision:** Use Kafka as message broker for event-driven communication between services.\n\n**Consequences:**\n- **Positive:** Decoupling, high throughput, durability, replay\n- **Negative:** Complexity of monitoring, eventual consistency\n\n---"
  },
  "c4_diagrams": {
    "context": {
      "filename": "docs/diagrams/c4-context.md",
      "format": "mermaid",
      "content": "# C4 Model: Context Diagram\n\n## System Context\n\n```mermaid\nC4Context\n    title \"Delivery App System Context\"\n    \n    Person(customer, \"Customer\", \"A user who wants to order food\")\n    Person(restaurant_owner, \"Restaurant Owner\", \"A restaurant owner who wants to manage their business\")\n    Person(platform_admin, \"Platform Admin\", \"An admin who wants to manage the platform\")\n\n    System_Boundary(c1, \"Delivery App\", \"\") {\n        System(user_service, \"User Service\", \"User management and authentication\")\n        System(restaurant_service, \"Restaurant Service\", \"Restaurant and menu management\")\n        System(order_service, \"Order Service\", \"Order creation and management\")\n        System(payment_service, \"Payment Service\", \"Payment processing\")\n        System(delivery_service, \"Delivery Service\", \"Delivery management and routing\")\n        System(notification_service, \"Notification Service\", \"Notifications and alerts\")\n    }\n    \n    Rel(customer, user_service, \"Uses\", \"Register, login, manage profile\")\n    Rel(customer, restaurant_service, \"Uses\", \"Browse restaurants, view menus\")\n    Rel(customer, order_service, \"Uses\", \"Create orders, track delivery\")\n    Rel(customer, payment_service, \"Uses\", \"Pay for orders\")\n    Rel(customer, delivery_service, \"Uses\", \"Track delivery in real-time\")\n    Rel(restaurant_owner, user_service, \"Uses\", \"Manage restaurant account\")\n    Rel(restaurant_owner, restaurant_service, \"Uses\", \"Manage restaurant, menu, orders\")\n    Rel(platform_admin, user_service, \"Uses\", \"Manage users\")\n    Rel(platform_admin, restaurant_service, \"Uses\", \"Moderate restaurants\")\n    Rel(platform_admin, order_service, \"Uses\", \"Monitor orders\")\n    Rel(platform_admin, delivery_service, \"Uses\", \"Manage delivery persons\")\n```\n\n## Description\n\nThe **Delivery App** is a food delivery platform that allows customers to order food from restaurants, restaurant owners to manage their business, and platform admins to manage the overall system.\n\n### External Users\n\n- **Customer**: Uses mobile app to browse restaurants, place orders, and track deliveries\n- **Restaurant Owner**: Uses web app to manage restaurant information, menu, and orders\n- **Platform Admin**: Uses admin dashboard to manage users, restaurants, and platform configuration\n\n### Core Systems\n\n- **User Service**: Manages user accounts, authentication, and profiles\n- **Restaurant Service**: Manages restaurant listings, menus, and reviews\n- **Order Service**: Manages order creation, status updates, and history\n- **Payment Service**: Processes payments via Stripe and Mercado Pago\n- **Delivery Service**: Manages delivery persons, routing, and real-time tracking\n- **Notification Service**: Sends push notifications, emails, and SMS alerts"
    },
    "container": {
      "filename": "docs/diagrams/c4-container.md",
      "format": "mermaid",
      "content": "# C4 Model: Container Diagram\n\n## System Container Diagram\n\n```mermaid\nC4Container\n    title \"Delivery App System Container Diagram\"\n    \n    Person(customer, \"Customer\", \"A user who wants to order food\")\n    \n    Container_Boundary(app, \"Delivery App\", \"Food Delivery Platform\") {\n        Container(mobile_app, \"Mobile App\", \"React Native\", \"Allows customers to order food\")\n        Container(web_app, \"Web App\", \"React\", \"Allows restaurant owners to manage their business\")\n        Container(admin_dashboard, \"Admin Dashboard\", \"React\", \"Allows platform admins to manage the platform\")\n        \n        ContainerDb(user_db, \"User Database\", \"PostgreSQL\", \"Stores user data\")\n        ContainerDb(restaurant_db, \"Restaurant Database\", \"PostgreSQL\", \"Stores restaurant and menu data\")\n        ContainerDb(order_db, \"Order Database\", \"PostgreSQL\", \"Stores order data\")\n        ContainerDb(notification_db, \"Notification Database\", \"MongoDB\", \"Stores notification data\")\n        ContainerDb(cache, \"Redis Cache\", \"Redis\", \"Caches frequently accessed data\")\n        ContainerQueue(kafka, \"Message Queue\", \"Kafka\", \"Event streaming platform\")\n    }\n    \n    Rel(customer, mobile_app, \"Uses\", \"Place orders, track delivery\")\n    Rel(mobile_app, user_db, \"Reads from\", \"User profiles\")\n    Rel(mobile_app, restaurant_db, \"Reads from\", \"Restaurant listings\")\n    Rel(mobile_app, order_db, \"Writes to\", \"Order data\")\n    Rel(mobile_app, cache, \"Reads from\", \"Cached data\")\n    Rel(mobile_app, kafka, \"Publishes events to\", \"User actions\")\n    Rel(mobile_app, kafka, \"Subscribes to events from\", \"Delivery updates\")\n    \n    Rel(restaurant_owner, web_app, \"Uses\", \"Manage restaurant, menu, orders\")\n    Rel(web_app, user_db, \"Reads from\", \"Restaurant account\")\n    Rel(web_app, restaurant_db, \"Writes to\", \"Restaurant, menu data\")\n    Rel(web_app, order_db, \"Reads from\", \"Orders for restaurant\")\n    Rel(web_app, kafka, \"Publishes events to\", \"Restaurant actions\")\n    Rel(web_app, kafka, \"Subscribes to events from\", \"New orders\")\n```\n\n## Description\n\nThe Delivery App consists of the following containers:\n\n### Frontend Containers\n\n- **Mobile App**: React Native application for customers (iOS and Android)\n- **Web App**: React web application for restaurant owners\n- **Admin Dashboard**: React web application for platform admins\n\n### Backend Services\n\n- **User Service**: Python FastAPI service (port 8010)\n- **Restaurant Service**: Python FastAPI service (port 8011)\n- **Order Service**: Python FastAPI service (port 8012)\n- **Payment Service**: Python FastAPI service (port 8013)\n- **Delivery Service**: Python FastAPI service (port 8014)\n- **Notification Service**: Python FastAPI service (port 8015)\n\n### Databases\n\n- **User Database**: PostgreSQL for user data\n- **Restaurant Database**: PostgreSQL for restaurant data\n- **Order Database**: PostgreSQL for order data\n- **Notification Database**: MongoDB for notification data\n\n### Infrastructure\n\n- **Redis Cache**: Caches frequently accessed data\n- **Kafka**: Event streaming platform for inter-service communication"
    },
    "component": {
      "filename": "docs/diagrams/c4-component.md",
      "format": "mermaid",
      "content": "# C4 Model: Component Diagram\n\n## System Component Diagram\n\n```mermaid\nC4Component\n    title \"Delivery App System Component Diagram - Order Service\"\n    \n    ContainerDb(order_db, \"Order Database\", \"PostgreSQL\", \"Stores order data\")\n    \n    Component_Boundary(order_service, \"Order Service\", \"\") {\n        Component(api, \"API Layer\", \"FastAPI endpoints\")\n        Component(services, \"Service Layer\", \"Business logic\")\n        Component(repositories, \"Repository Layer\", \"Data access\")\n    }\n    \n    Rel(api, services, \"Calls\")\n    Rel(services, repositories, \"Uses\")\n    Rel(repositories, order_db, \"Reads from & Writes to\")\n```\n\n## Description\n\nThe Order Service is composed of the following components:\n\n### API Layer\n\n- **FastAPI Endpoints**: RESTful API endpoints for order management\n- **Authentication Middleware**: JWT-based authentication\n- **Rate Limiting**: API rate limiting\n\n### Service Layer\n\n- **Order Service**: Order creation, status updates, history\n- **Order Validation Service**: Validates order data\n- **Order Pricing Service**: Calculates order totals\n\n### Repository Layer\n\n- **Order Repository**: CRUD operations for orders\n- **Order Item Repository**: CRUD operations for order items"
    },
    "code": {
      "filename": "docs/diagrams/c4-code.md",
      "format": "mermaid",
      "content": "# C4 Model: Code Diagram\n\n## System Code Diagram\n\n```mermaid\nC4Component\n    title \"Delivery App System Code Diagram - User Service Models\"\n    \n    Component_Boundary(user_service, \"User Service\", \"\") {\n        Component(models, \"Domain Models\", \"Pydantic models\")\n        Component(repositories, \"Repositories\", \"SQLAlchemy repositories\")\n    }\n    \n    Rel(models, repositories, \"Uses\")\n```\n\n## Description\n\nThe User Service domain models include:\n\n### User Model\n\n- **Fields**: id, email, name, password_hash, created_at, updated_at\n- **Validation**: Email format, password length, name requirements\n\n### Role Model\n\n- **Fields**: id, name, permissions\n- **Validation**: Role name uniqueness, permissions format"
    }
  },
  "sequence_diagrams": {
    "order_creation_flow": {
      "filename": "docs/diagrams/sequence-order-creation.md",
      "format": "mermaid",
      "content": "# Sequence Diagram: Order Creation Flow\n\n```mermaid\nsequenceDiagram\n    participant Customer as Customer\n    participant MobileApp as Mobile App\n    participant APIGateway as API Gateway\n    participant UserService as User Service\n    participant RestaurantService as Restaurant Service\n    participant OrderService as Order Service\n    participant PaymentService as Payment Service\n    participant DeliveryService as Delivery Service\n    participant NotificationService as Notification Service\n    \n    Customer->>MobileApp: Select restaurant and items\n    MobileApp->>APIGateway: POST /api/v1/orders\n    APIGateway->>OrderService: Forward order request\n    OrderService->>RestaurantService: Validate availability\n    RestaurantService-->>OrderService: Available\n    OrderService->>OrderService: Calculate total\n    OrderService->>APIGateway: Return order\n    APIGateway-->>MobileApp: 201 Order Created\n    \n    APIGateway->>PaymentService: Process payment\n    PaymentService->>PaymentService: Charge card\n    PaymentService-->>APIGateway: Payment completed\n    \n    APIGateway->>OrderService: Update order status\n    OrderService->>NotificationService: Send notification\n    NotificationService-->>Customer: Push: Order confirmed\n    \n    APIGateway->>DeliveryService: Assign delivery person\n    DeliveryService->>MobileApp: WebSocket: Delivery assigned\n```\n\n## Description\n\nThis sequence diagram shows the flow of order creation in the Delivery App system:\n\n1. **Customer Action:** Customer selects restaurant and items on mobile app\n2. **Order Creation:** Mobile app sends order to API Gateway\n3. **Validation:** Order Service validates order with Restaurant Service\n4. **Calculation:** Order Service calculates total\n5. **Return:** API Gateway returns created order to mobile app\n6. **Payment:** Payment Service processes payment\n7. **Notification:** Notification Service sends confirmation to customer\n8. **Delivery:** Delivery Service assigns delivery person and sends real-time update"
    }
  },
  "data_flow_docs": {
    "overview": {
      "filename": "docs/data-flow.md",
      "content": "# Data Flow Documentation\n\n## Overview\n\nThe Delivery App system follows an event-driven architecture with Kafka as the central message broker.\n\n## Data Flow Diagram\n\n```mermaid\ngraph TD\n    A[Mobile App] -->|HTTP REST| B[API Gateway]\n    B -->|HTTP REST| C[User Service]\n    B -->|HTTP REST| D[Restaurant Service]\n    B -->|HTTP REST| E[Order Service]\n    B -->|HTTP REST| F[Payment Service]\n    B -->|HTTP REST| G[Delivery Service]\n    C -->|Write| H[(User DB - PostgreSQL)]\n    C -->|Cache| I[(Redis - User Sessions)]\n    C -->|Produce| J[Kafka - users.created]\n    D -->|Write| K[(Restaurant DB - PostgreSQL)]\n    D -->|Cache| I[(Redis - Restaurant Listings)]\n    D -->|Produce| L[Kafka - restaurants.created]\n    E -->|Write| M[(Order DB - PostgreSQL)]\n    E -->|Cache| I[(Redis - Order Status)]\n    E -->|Produce| N[Kafka - orders.created]\n    F -->|Consume| N[Kafka - orders.created]\n    F -->|Write| O[(Payment DB - PostgreSQL)]\n    F -->|External| P[(Stripe, Mercado Pago)]\n    F -->|Produce| Q[Kafka - payments.completed]\n    G -->|Consume| N[Kafka - orders.created]\n    G -->|Write| S[(Delivery DB - PostgreSQL)]\n    G -->|External| T[(Google Maps API)]\n    G -->|WebSocket| A[Mobile App - Real-time]\n    G -->|Produce| U[Kafka - deliveries.assigned]\n    W[Notification Service] -->|Consume| N[Kafka - orders.status.changed]\n    W -->|Consume| U[Kafka - deliveries.status.changed]\n    W -->|Write| X[(Notification DB - MongoDB)]\n    W -->|External| Y[(Firebase, AWS SES, Twilio)]\n```\n\n## Data Flow Description\n\n### 1. Order Creation Flow\n\n1. **Customer** browses restaurants and selects items on **Mobile App**\n2. **Mobile App** sends POST request to **API Gateway**\n3. **API Gateway** forwards to **Order Service**\n4. **Order Service** validates with **Restaurant Service** (availability)\n5. **Order Service** saves order to **Order DB**\n6. **Order Service** publishes `orders.created` event to **Kafka**\n7. **Payment Service** consumes `orders.created`, processes payment, publishes `payments.completed`\n8. **Order Service** consumes `payments.completed`, updates order status, publishes `orders.status.changed`\n9. **Delivery Service** consumes `payments.completed`, assigns delivery person, publishes `deliveries.assigned`\n10. **Notification Service** consumes `orders.status.changed`, sends push notification to customer\n11. **Mobile App** receives real-time delivery updates via **WebSocket**\n\n### 2. Caching Strategy\n\n- **Restaurant Listings:** Cached in Redis with 5-minute TTL\n- **Order Status:** Cached in Redis with 1-hour TTL\n- **User Sessions:** Cached in Redis with 24-hour TTL\n- **API Response Time:** Cached responses return in < 100ms\n\n### 3. Event-Driven Communication\n\n- **Async Processing:** All inter-service communication is asynchronous via Kafka\n- **Eventual Consistency:** Data consistency is eventually consistent\n- **Event Replay:** Kafka allows replaying events for re-processing\n- **Decoupling:** Services are decoupled from each other\n\n### 4. Database Strategy\n\n- **Read Replicas:** PostgreSQL databases have read replicas for high-read workloads\n- **Connection Pooling:** All services use connection pooling (PgBouncer)\n- **Indexing:** Appropriate indexes on frequently queried fields\n- **Backup:** Daily backups with 7-day retention"
    }
  },
  "generated_at": "2026-04-15T17:00:00Z"
}
```

---

### 8.4 Diagram Generator

**Responsabilidade:** Gera diagramas (Mermaid, PlantUML, C4, UML) para documentação.

**Consumir:**
- `architectural.plan` (do Architectural Planning System)
- `system_design.generated` (do Architectural Planning System)
- `diagrams.generated` (do Architectural Planning System)

**Processamento:**
```python
# services/documentation-generation/src/services/diagram_generator.py

class DiagramGenerator:
    async def generate_diagrams(self, architecture: dict, system_design: dict, diagrams: dict) -> dict:
        """
        Gera diagramas para documentação.

        Tipos de diagramas:
        1. C4 diagrams (Context, Container, Component, Code)
        2. Sequence diagrams
        3. Data flow diagrams
        4. State machine diagrams
        5. UML class diagrams
        """
        generated_diagrams = {}

        # Gerar C4 diagrams
        c4_diagrams = await self._generate_c4_diagrams(architecture, system_design)
        generated_diagrams['c4'] = c4_diagrams

        # Gerar sequence diagrams
        sequence_diagrams = await self._generate_sequence_diagrams(architecture, system_design)
        generated_diagrams['sequence'] = sequence_diagrams

        # Gerar data flow diagrams
        data_flow_diagrams = await self._generate_data_flow_diagrams(architecture, system_design)
        generated_diagrams['data_flow'] = data_flow_diagrams

        # Gerar state machine diagrams
        state_machine_diagrams = await self._generate_state_machine_diagrams(architecture, system_design)
        generated_diagrams['state_machine'] = state_machine_diagrams

        # Gerar UML class diagrams
        uml_class_diagrams = await self._generate_uml_class_diagrams(architecture, system_design)
        generated_diagrams['uml_class'] = uml_class_diagrams

        # Gerar PlantUML diagrams
        plantuml_diagrams = await self._generate_plantuml_diagrams(c4_diagrams, sequence_diagrams, data_flow_diagrams)
        generated_diagrams['plantuml'] = plantuml_diagrams

        return {
            "diagrams": generated_diagrams,
            "diagram_files": await self._generate_diagram_files(generated_diagrams),
            "generated_at": datetime.utcnow().isoformat()
        }

    async def _generate_diagram_files(self, diagrams: dict) -> List[dict]:
        """
        Gera arquivos de diagramas.
        """
        diagram_files = []

        for diagram_type, diagram in diagrams.items():
            for diagram_name, diagram_content in diagram.items():
                file_name = f"docs/diagrams/{diagram_type}/{diagram_name}.md"
                diagram_files.append({
                    "name": diagram_name,
                    "type": diagram_type,
                    "filename": file_name,
                    "format": "mermaid",
                    "content": diagram_content.get('content', diagram_content)
                })

        return diagram_files
```

**Output:**
```json
{
  "diagrams": {
    "c4": {
      "context": {
        "name": "C4 Context Diagram",
        "format": "mermaid",
        "content": "```mermaid\nC4Context\n    title \"Delivery App System Context\"\n    ...\n```"
      },
      "container": {
        "name": "C4 Container Diagram",
        "format": "mermaid",
        "content": "```mermaid\nC4Container\n    title \"Delivery App System Container Diagram\"\n    ...\n```"
      }
    },
    "sequence": {
      "order_creation_flow": {
        "name": "Order Creation Flow Sequence Diagram",
        "format": "mermaid",
        "content": "```mermaid\nsequenceDiagram\n    participant Customer as Customer\n    participant MobileApp as Mobile App\n    ...\n```"
      }
    },
    "data_flow": {
      "overview": {
        "name": "Data Flow Overview",
        "format": "mermaid",
        "content": "```mermaid\ngraph TD\n    A[Mobile App] -->|HTTP REST| B[API Gateway]\n    ...\n```"
      }
    },
    "state_machine": {
      "order_status": {
        "name": "Order Status State Machine",
        "format": "mermaid",
        "content": "```mermaid\nstateDiagram-v2\n    [*] --> Pending\n    Pending --> Confirmed: Payment completed\n    Confirmed --> Preparing: Restaurant accepted\n    Preparing --> Ready: Restaurant ready\n    Ready --> Pickup: Delivery person picked up\n    Pickup --> OnTheWay: Delivery person en route\n    OnTheWay --> Delivered: Delivered to customer\n    Delivered --> [*]\n```"
      }
    },
    "uml_class": {
      "user_models": {
        "name": "User Models UML Class Diagram",
        "format": "mermaid",
        "content": "```mermaid\nclassDiagram\n    class User {\n        +UUID id\n        +String email\n        +String name\n        +DateTime created_at\n        +DateTime updated_at\n        +Boolean is_active\n        +validateEmail()\n        +hashPassword()\n    }\n\n    class UserCreate {\n        +String email\n        +String password\n        +String name\n        +validatePassword()\n    }\n\n    UserCreate --|inherits|> User\n```"
      }
    }
  },
  "diagram_files": [
    {
      "name": "C4 Context Diagram",
      "type": "c4",
      "filename": "docs/diagrams/c4/c4-context.md",
      "format": "mermaid",
      "content": "```mermaid\nC4Context\n    title \"Delivery App System Context\"\n    ...\n```"
    },
    {
      "name": "C4 Container Diagram",
      "type": "c4",
      "filename": "docs/diagrams/c4/c4-container.md",
      "format": "mermaid",
      "content": "```mermaid\nC4Container\n    title \"Delivery App System Container Diagram\"\n    ...\n```"
    },
    {
      "name": "Order Creation Flow Sequence Diagram",
      "type": "sequence",
      "filename": "docs/diagrams/sequence/sequence-order-creation.md",
      "format": "mermaid",
      "content": "```mermaid\nsequenceDiagram\n    participant Customer as Customer\n    ...\n```"
    },
    {
      "name": "Data Flow Overview",
      "type": "data_flow",
      "filename": "docs/diagrams/data-flow/data-flow-overview.md",
      "format": "mermaid",
      "content": "```mermaid\ngraph TD\n    A[Mobile App] -->|HTTP REST| B[API Gateway]\n    ...\n```"
    }
  ],
  "generated_at": "2026-04-15T17:30:00Z"
}
```

---

### Eventos Kafka Produzidos pelo Documentation Generation System

```yaml
readme.generated:
  - Producer: README Generator
  - Consumer: Software Engineering Pipeline
  - Payload: { id, readme, badges, validation, generated_at }

api_docs.generated:
  - Producer: API Docs Generator
  - Consumer: Software Engineering Pipeline
  - Payload: { id, openapi_spec, api_reference, examples, auth_guides, error_codes, generated_at }

architecture_docs.generated:
  - Producer: Architecture Docs Generator
  - Consumer: Software Engineering Pipeline
  - Payload: { id, architecture_docs, c4_diagrams, sequence_diagrams, data_flow_docs, generated_at }

diagrams.generated:
  - Producer: Diagram Generator
  - Consumer: Software Engineering Pipeline
  - Payload: { id, diagrams, diagram_files, generated_at }

inline_comments.generated:
  - Producer: Code Commenter
  - Consumer: Code Forge, Software Engineering Pipeline
  - Payload: { id, file_path, comments, generated_at }
```

---

## Conclusão da Parte 6

O Documentation Generation System é o sexto componente crítico do Fluxo G, consumindo o código e testes gerados pelo Code Forge e Test Generation System e gerando documentação automaticamente.

Este sistema produz 5 tipos principais de eventos Kafka que alimentam os sistemas downstream:
1. `readme.generated` → Software Engineering Pipeline
2. `api_docs.generated` → Software Engineering Pipeline
3. `architecture_docs.generated` → Software Engineering Pipeline
4. `diagrams.generated` → Software Engineering Pipeline
5. `inline_comments.generated` → Code Forge, Software Engineering Pipeline

O Documentation Generation System permite:
- **Geração automática de README** com instruções detalhadas de instalação, uso, configuração e exemplos
- **Geração automática de API docs** com OpenAPI/Swagger specs, referência de endpoints, exemplos, guias de auth, códigos de erro
- **Geração automática de architecture docs** com C4 diagrams, sequence diagrams, data flow documentation, ADRs
- **Geração automática de diagramas** em múltiplos formatos (Mermaid, PlantUML, C4, UML)
- **Geração automática de inline comments/docstrings** para código complexo

---

## 🔄 Passo 9: CI Feedback Loop (NOVO - 8015)

### Descrição Geral

Consome resultados de builds/testes e implementa reinforcement learning para otimizar geração de código e testes automaticamente.

### Componentes do CI Feedback Loop

| Componente | Descrição |
|------------|-----------|
| **Feedback Collector** | Coleta feedback de builds, testes e deployments |
| **Reinforcement Learner** | Aprende com feedback e atualiza políticas de geração |
| **Auto-Corrector** | Corrige código automaticamente quando testes falham |
| **Failure Analyzer** | Analisa falhas e identifica padrões de erro |
| **Optimization Suggester** | Sugere otimizações baseadas em métricas |

### Portas e Endpoints

- **Porta API REST:** 8015
- **Health Check:** `/health`
- **Metrics:** `/metrics`
- **Endpoints:**
  - `POST /api/v1/feedback/collect` - Coletar feedback de build
  - `POST /api/v1/feedback/reinforce` - Executar ciclo de reinforcement learning
  - `POST /api/v1/autocorrect/fix` - Corrigir código automaticamente
  - `POST /api/v1/failure/analyze` - Analisar falha de build
  - `POST /api/v1/optimization/suggest` - Sugerir otimizações
  - `GET /api/v1/policies/{id}` - Obter política atual
  - `GET /api/v1/metrics/quality` - Obter métricas de qualidade
  - `GET /api/v1/reports/summary` - Obter resumo de qualidade

---

### 9.1 Feedback Collector

**Responsabilidade:** Coletar feedback de builds, testes e deployments para análise e aprendizado.

**Consumir:**
- `build.completed` (do Software Engineering Pipeline)
- `tests.completed` (do Software Engineering Pipeline)
- `deployment.completed` (do Software Engineering Pipeline)
- `agent.errors` (do Agentic Delegation System)

**Processamento:**
```python
# services/ci-feedback-loop/src/services/feedback_collector.py

class FeedbackCollector:
    async def collect_feedback(self, build_data: dict, test_data: dict, deployment_data: dict, agent_errors: List[dict]) -> dict:
        """
        Coleta feedback completo de build/test/deployment.

        Processo:
        1. Extrair métricas de build (duração, custo, status)
        2. Extrair métricas de testes (coverage, mutation score, falhas)
        3. Extrair métricas de deployment (uptime, performance)
        4. Analisar erros de agentes (tipos, mensagens, stack traces)
        5. Calcular scores de qualidade
        6. Identificar anomalias e padrões
        7. Gerar feedback consolidado
        """
        # Extrair métricas de build
        build_metrics = await self._extract_build_metrics(build_data)

        # Extrair métricas de testes
        test_metrics = await self._extract_test_metrics(test_data)

        # Extrair métricas de deployment
        deployment_metrics = await self._extract_deployment_metrics(deployment_data)

        # Analisar erros de agentes
        error_metrics = await self._analyze_agent_errors(agent_errors)

        # Calcular scores de qualidade
        quality_scores = await self._calculate_quality_scores(
            build_metrics,
            test_metrics,
            deployment_metrics
        )

        # Identificar anomalias
        anomalies = await self._identify_anomalies(
            build_metrics,
            test_metrics,
            deployment_metrics,
            error_metrics
        )

        # Gerar feedback consolidado
        consolidated_feedback = {
            "build_id": build_data.get('id'),
            "build_metrics": build_metrics,
            "test_metrics": test_metrics,
            "deployment_metrics": deployment_metrics,
            "error_metrics": error_metrics,
            "quality_scores": quality_scores,
            "anomalies": anomalies,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Armazenar feedback no banco de dados
        await self._store_feedback(consolidated_feedback)

        return consolidated_feedback

    async def _extract_build_metrics(self, build_data: dict) -> dict:
        """
        Extrai métricas de build.
        """
        return {
            "duration_seconds": build_data.get('duration', 0),
            "cost_usd": build_data.get('cost', 0.0),
            "status": build_data.get('status', 'unknown'),
            "stages": build_data.get('stages', []),
            "stage_metrics": await self._extract_stage_metrics(build_data.get('stages', [])),
            "worker_type": build_data.get('worker_type'),
            "environment": build_data.get('environment')
        }

    async def _extract_test_metrics(self, test_data: dict) -> dict:
        """
        Extrai métricas de testes.
        """
        return {
            "total_tests": test_data.get('total', 0),
            "passed": test_data.get('passed', 0),
            "failed": test_data.get('failed', 0),
            "skipped": test_data.get('skipped', 0),
            "coverage_percentage": test_data.get('coverage', 0.0),
            "mutation_score": test_data.get('mutation_score', 0.0),
            "flaky_tests": test_data.get('flaky', []),
            "slow_tests": test_data.get('slow', []),
            "test_types": {
                "unit": test_data.get('unit', {}),
                "integration": test_data.get('integration', {}),
                "e2e": test_data.get('e2e', {})
            }
        }

    async def _extract_deployment_metrics(self, deployment_data: dict) -> dict:
        """
        Extrai métricas de deployment.
        """
        return {
            "status": deployment_data.get('status', 'unknown'),
            "uptime_seconds": deployment_data.get('uptime', 0),
            "performance_metrics": deployment_data.get('performance', {}),
            "scaling_events": deployment_data.get('scaling', []),
            "error_count": deployment_data.get('errors', 0)
        }

    async def _analyze_agent_errors(self, agent_errors: List[dict]) -> dict:
        """
        Analisa erros de agentes.
        """
        error_summary = {
            "total_errors": len(agent_errors),
            "errors_by_type": {},
            "errors_by_agent": {},
            "common_errors": [],
            "critical_errors": []
        }

        for error in agent_errors:
            error_type = error.get('type', 'unknown')
            agent_id = error.get('agent_id')

            # Contagem por tipo
            if error_type not in error_summary['errors_by_type']:
                error_summary['errors_by_type'][error_type] = 0
            error_summary['errors_by_type'][error_type] += 1

            # Contagem por agente
            if agent_id not in error_summary['errors_by_agent']:
                error_summary['errors_by_agent'][agent_id] = 0
            error_summary['errors_by_agent'][agent_id] += 1

            # Identificar erros críticos
            if error.get('severity') == 'critical':
                error_summary['critical_errors'].append(error)

            # Identificar erros comuns (mesma mensagem)
            error_message = error.get('message', '')
            existing = next((e for e in error_summary['common_errors'] if e.get('message') == error_message), None)
            if existing:
                existing['count'] += 1
            else:
                error_summary['common_errors'].append({
                    "message": error_message,
                    "count": 1,
                    "type": error_type,
                    "agent_id": agent_id
                })

        return error_summary

    async def _calculate_quality_scores(self, build_metrics: dict, test_metrics: dict, deployment_metrics: dict) -> dict:
        """
        Calcula scores de qualidade.
        """
        scores = {}

        # Score de testes
        test_score = (
            test_metrics.get('coverage_percentage', 0) * 0.4 +
            (test_metrics.get('passed', 0) / max(test_metrics.get('total', 1)) * 0.3 +
            (1 - len(test_metrics.get('flaky_tests', [])) / max(test_metrics.get('total', 1)) * 0.2 +
            test_metrics.get('mutation_score', 0) * 0.1
        )
        scores['test'] = test_score

        # Score de build
        build_score = (
            1.0 if build_metrics.get('status') == 'success' else 0.0
        ) * 0.5 + (
            1.0 if build_metrics.get('duration_seconds', 0) < 300 else 0.5
        ) * 0.3 + (
            1.0 if build_metrics.get('cost_usd', 0) < 10 else 0.5
        ) * 0.2
        scores['build'] = build_score

        # Score de deployment
        deployment_score = (
            1.0 if deployment_metrics.get('status') == 'success' else 0.0
        ) * 0.6 + (
            1.0 if deployment_metrics.get('uptime_seconds', 0) > 3600 else 0.0
        ) * 0.4
        scores['deployment'] = deployment_score

        # Score geral
        scores['overall'] = (
            scores['test'] * 0.5 +
            scores['build'] * 0.3 +
            scores['deployment'] * 0.2
        )

        return scores

    async def _identify_anomalies(self, build_metrics: dict, test_metrics: dict, deployment_metrics: dict, error_metrics: dict) -> dict:
        """
        Identifica anomalias nos resultados.
        """
        anomalies = []

        # Anomalia 1: Build muito lenta
        if build_metrics.get('duration_seconds', 0) > 600:
            anomalies.append({
                "type": "slow_build",
                "severity": "warning",
                "description": f"Build levou {build_metrics['duration_seconds']} segundos (threshold: 300s)",
                "suggestion": "Otimizar pipeline ou reduzir complexidade do código"
            })

        # Anomalia 2: Test coverage baixa
        if test_metrics.get('coverage_percentage', 0) < 70:
            anomalies.append({
                "type": "low_coverage",
                "severity": "warning",
                "description": f"Coverage de {test_metrics['coverage_percentage']}% (threshold: 80%)",
                "suggestion": "Aumentar número de testes ou testar código não coberto"
            })

        # Muitos testes flaky
        if len(test_metrics.get('flaky_tests', [])) > 5:
            anomalies.append({
                "type": "many_flaky_tests",
                "severity": "warning",
                "description": f"{len(test_metrics['flaky_tests'])} testes flaky identificados",
                "suggestion": "Investigar e estabilizar testes instáveis"
            })

        # Muitos erros do mesmo tipo
        common_errors = [e for e in error_metrics.get('common_errors', []) if e['count'] > 3]
        for common_error in common_errors:
            anomalies.append({
                "type": "repeated_error",
                "severity": "warning",
                "description": f"Erro repetido {common_error['count']} vezes: {common_error['message']}",
                "suggestion": "Investigar causa raiz e implementar fix permanente"
            })

        # Erros críticos
        for critical_error in error_metrics.get('critical_errors', []):
            anomalies.append({
                "type": "critical_error",
                "severity": "critical",
                "description": f"Erro crítico no agente {critical_error.get('agent_id')}: {critical_error.get('message')}",
                "suggestion": "Investigar e corrigir imediatamente"
            })

        return anomalies
```

**Output:**
```json
{
  "build_id": "build_uuid",
  "build_metrics": {
    "duration_seconds": 245,
    "cost_usd": 8.50,
    "status": "success",
    "stages": ["Pre-Flight", "Build", "Test", "Security", "Staging", "Approval", "Production"],
    "stage_metrics": {
      "Pre-Flight": {"duration_seconds": 10, "cost_usd": 0.05},
      "Build": {"duration_seconds": 120, "cost_usd": 5.00},
      "Test": {"duration_seconds": 80, "cost_usd": 2.50},
      "Security": {"duration_seconds": 15, "cost_usd": 0.50},
      "Staging": {"duration_seconds": 5, "cost_usd": 0.30},
      "Approval": {"duration_seconds": 10, "cost_usd": 0.05},
      "Production": {"duration_seconds": 5, "cost_usd": 0.10}
    },
    "worker_type": "kubernetes-runner",
    "environment": "production"
  },
  "test_metrics": {
    "total_tests": 150,
    "passed": 142,
    "failed": 8,
    "skipped": 0,
    "coverage_percentage": 85.5,
    "mutation_score": 82.0,
    "flaky_tests": [
      {"name": "test_order_creation_flaky", "failure_rate": 0.3},
      {"name": "test_integration_api_timeout", "failure_rate": 0.25}
    ],
    "slow_tests": [
      {"name": "test_e2e_complete_flow", "duration_seconds": 120}
    ],
    "test_types": {
      "unit": {"total": 100, "passed": 95, "failed": 5, "coverage": 90.0},
      "integration": {"total": 30, "passed": 28, "failed": 2, "coverage": 85.0},
      "e2e": {"total": 20, "passed": 19, "failed": 1, "coverage": 75.0}
    }
  },
  "deployment_metrics": {
    "status": "success",
    "uptime_seconds": 43200,
    "performance_metrics": {
      "response_time_p50": 50,
      "response_time_p95": 120,
      "throughput_rps": 1000,
      "error_rate": 0.001
    },
    "scaling_events": [
      {"time": "2026-04-15T18:00:00Z", "action": "scale_up", "from": 3, "to": 5},
      {"time": "2026-04-15T22:00:00Z", "action": "scale_down", "from": 5, "to": 3}
    ],
    "error_count": 5
  },
  "error_metrics": {
    "total_errors": 12,
    "errors_by_type": {
      "validation_error": 4,
      "timeout_error": 3,
      "dependency_error": 2,
      "network_error": 2,
      "unknown_error": 1
    },
    "errors_by_agent": {
      "agent_code_forge_1": 5,
      "agent_code_forge_2": 4,
      "agent_test_generator": 2,
      "agent_docs_generator": 1
    },
    "common_errors": [
      {"message": "ImportError: cannot import name 'User'", "count": 3, "type": "dependency_error", "agent_id": "agent_code_forge_1"},
      {"message": "Timeout: Database query took too long", "count": 2, "type": "timeout_error", "agent_id": "agent_code_forge_2"}
    ],
    "critical_errors": [
      {"message": "Database connection failed during migration", "agent_id": "agent_code_forge_1", "type": "critical", "stack_trace": "..."}
    ]
  },
  "quality_scores": {
    "test": 0.82,
    "build": 0.85,
    "deployment": 0.94,
    "overall": 0.85
  },
  "anomalies": [
    {
      "type": "slow_build",
      "severity": "warning",
      "description": "Build levou 245 segundos (threshold: 300s)",
      "suggestion": "Otimizar pipeline ou reduzir complexidade do código"
    },
    {
      "type": "low_coverage",
      "severity": "warning",
      "description": "Coverage de 85.5% (threshold: 80%)",
      "suggestion": "Aumentar número de testes ou testar código não coberto"
    },
    {
      "type": "many_flaky_tests",
      "severity": "warning",
      "description": "2 testes flaky identificados",
      "suggestion": "Investigar e estabilizar testes instáveis"
    },
    {
      "type": "repeated_error",
      "severity": "warning",
      "description": "Erro repetido 3 vezes: ImportError: cannot import name 'User'",
      "suggestion": "Investigar causa raiz e implementar fix permanente"
    }
  ],
  "timestamp": "2026-04-15T18:30:00Z"
}
```

---

### 9.2 Reinforcement Learner

**Responsabilidade:** Aprende com feedback e atualiza políticas de geração de código e testes.

**Consumir:**
- `feedback.collected` (do Feedback Collector)
- `code.generated` (do Code Forge)
- `tests.generated` (do Test Generation System)
- `architectural.plan` (do Architectural Planning System)
- `system_design.generated` (do Architectural Planning System)

**Processamento:**
```python
# services/ci-feedback-loop/src/services/reinforcement_learner.py

class ReinforcementLearner:
    async def learn_and_update_policies(self, feedback_data: dict, code_data: dict, test_data: dict, architecture: dict) -> dict:
        """
        Aprende com feedback e atualiza políticas.

        Processo:
        1. Analisar feedback (sucesso/falha, métricas, anomalias)
        2. Identificar padrões de sucesso/falha
        3. Calcular rewards e penalties
        4. Atualizar políticas de geração de código (Code Forge)
        5. Atualizar políticas de geração de testes (Test Generation)
        6. Atualizar pesos de templates e ferramentas
        7. Gerar recomendações de ajuste
        8. Validar impacto das atualizações
        """
        # Analisar feedback
        feedback_analysis = await self._analyze_feedback(feedback_data)

        # Identificar padrões
        patterns = await self._identify_patterns(feedback_data, code_data, test_data, architecture)

        # Calcular rewards
        rewards = await self._calculate_rewards(feedback_data, patterns)

        # Atualizar políticas
        policy_updates = await self._update_policies(rewards, patterns)

        # Aplicar atualizações
        applied_updates = await self._apply_policy_updates(policy_updates)

        # Validar impacto
        validation = await self._validate_impact(feedback_data, applied_updates)

        return {
            "feedback_analysis": feedback_analysis,
            "identified_patterns": patterns,
            "rewards": rewards,
            "policy_updates": policy_updates,
            "applied_updates": applied_updates,
            "impact_validation": validation,
            "generated_at": datetime.utcnow().isoformat()
        }

    async def _analyze_feedback(self, feedback_data: dict) -> dict:
        """
        Analisa feedback para identificar tendências.
        """
        analysis = {
            "build_success_rate": 0.0,
            "test_success_rate": 0.0,
            "average_coverage": 0.0,
            "common_failure_reasons": [],
            "high_risk_components": []
        }

        # Calcular taxas de sucesso
        total_builds = await self._count_recent_builds(100)
        successful_builds = await self._count_successful_builds(100)
        analysis['build_success_rate'] = successful_builds / max(total_builds, 1)

        total_tests = await self._count_recent_tests(100)
        successful_tests = await self._count_successful_tests(100)
        analysis['test_success_rate'] = successful_tests / max(total_tests, 1)

        # Calcular média de coverage
        coverages = await self._get_recent_coverages(100)
        analysis['average_coverage'] = sum(coverages) / max(len(coverages), 1)

        # Identificar razões de falha comuns
        failure_reasons = await self._analyze_common_failure_reasons(100)
        analysis['common_failure_reasons'] = failure_reasons[:5]

        # Identificar componentes de alto risco
        high_risk = await self._identify_high_risk_components(100)
        analysis['high_risk_components'] = high_risk_components[:5]

        return analysis

    async def _identify_patterns(self, feedback_data: dict, code_data: dict, test_data: dict, architecture: dict) -> dict:
        """
        Identifica padrões de sucesso/falha.
        """
        patterns = {
            "successful_patterns": [],
            "failure_patterns": [],
            "code_patterns": [],
            "test_patterns": [],
            "template_patterns": [],
            "tool_patterns": []
        }

        # Identificar padrões de sucesso
        successful_patterns = await self._identify_successful_patterns(feedback_data, code_data, test_data)
        patterns['successful_patterns'] = successful_patterns

        # Identificar padrões de falha
        failure_patterns = await self._identify_failure_patterns(feedback_data, code_data, test_data)
        patterns['failure_patterns'] = failure_patterns

        # Identificar padrões de código
        code_patterns = await self._identify_code_patterns(feedback_data, code_data)
        patterns['code_patterns'] = code_patterns

        # Identificar padrões de testes
        test_patterns = await self._identify_test_patterns(feedback_data, test_data)
        patterns['test_patterns'] = test_patterns

        # Identificar padrões de templates
        template_patterns = await self._identify_template_patterns(feedback_data, code_data)
        patterns['template_patterns'] = template_patterns

        # Identificar padrões de ferramentas
        tool_patterns = await self._identify_tool_patterns(feedback_data, architecture)
        patterns['tool_patterns'] = tool_patterns

        return patterns

    async def _calculate_rewards(self, feedback_data: dict, patterns: dict) -> dict:
        """
        Calcula rewards e penalties.
        """
        rewards = {}

        # Reward para build de sucesso
        if feedback_data.get('build_metrics', {}).get('status') == 'success':
            rewards['build_success'] = 1.0
        else:
            rewards['build_success'] = -1.0

        # Reward para alta coverage
        coverage = feedback_data.get('test_metrics', {}).get('coverage_percentage', 0)
        if coverage > 0.8:
            rewards['high_coverage'] = 0.5
        elif coverage > 0.6:
            rewards['medium_coverage'] = 0.3
        else:
            rewards['low_coverage'] = -0.3

        # Reward para sem testes flaky
        flaky_tests = len(feedback_data.get('test_metrics', {}).get('flaky_tests', []))
        if flaky_tests == 0:
            rewards['no_flaky_tests'] = 0.3
        else:
            rewards['has_flaky_tests'] = -0.1 * flaky_tests

        # Reward para build rápido
        build_duration = feedback_data.get('build_metrics', {}).get('duration_seconds', 0)
        if build_duration < 300:
            rewards['fast_build'] = 0.2
        else:
            rewards['slow_build'] = -0.2

        # Reward por seguir padrões de sucesso
        successful_patterns = patterns.get('successful_patterns', [])
        for pattern in successful_patterns:
            rewards[f"successful_pattern_{pattern['id']}"] = 0.5

        # Penalty por seguir padrões de falha
        failure_patterns = patterns.get('failure_patterns', [])
        for pattern in failure_patterns:
            rewards[f"failure_pattern_{pattern['id']}"] = -0.5

        return rewards

    async def _update_policies(self, rewards: dict, patterns: dict) -> dict:
        """
        Atualiza políticas de geração baseado em rewards.
        """
        policy_updates = {
            "code_generation_policies": {},
            "test_generation_policies": {},
            "template_selection_policies": {},
            "tool_selection_policies": {}
        }

        # Atualizar políticas de geração de código
        code_policies = await self._update_code_generation_policies(rewards, patterns)
        policy_updates['code_generation_policies'] = code_policies

        # Atualizar políticas de geração de testes
        test_policies = await self._update_test_generation_policies(rewards, patterns)
        policy_updates['test_generation_policies'] = test_policies

        # Atualizar políticas de seleção de templates
        template_policies = await self._update_template_selection_policies(rewards, patterns)
        policy_updates['template_selection_policies'] = template_policies

        # Atualizar políticas de seleção de ferramentas
        tool_policies = await self._update_tool_selection_policies(rewards, patterns)
        policy_updates['tool_selection_policies'] = tool_policies

        return policy_updates

    async def _update_code_generation_policies(self, rewards: dict, patterns: dict) -> dict:
        """
        Atualiza políticas de geração de código.
        """
        policies = {}

        # Aumentar peso para templates que geram código de alta qualidade
        code_patterns = patterns.get('code_patterns', [])
        for pattern in code_patterns:
            if pattern.get('success_rate', 0) > 0.8:
                policies[f"template_{pattern['template_id']}_weight"] = patterns.get('weight', 1.0) + 0.2

        # Penalizar templates que geram bugs
        failure_patterns = patterns.get('failure_patterns', [])
        for pattern in failure_patterns:
            if pattern.get('failure_rate', 0) > 0.5:
                policies[f"template_{pattern['template_id']}_weight"] = patterns.get('weight', 1.0) - 0.3

        # Ajustar parâmetros de LLM baseado em qualidade
        if rewards.get('build_success', 0) > 0.8:
            policies['llm_temperature'] = max(0.1, policies.get('llm_temperature', 0.7) - 0.1)
        else:
            policies['llm_temperature'] = min(1.0, policies.get('llm_temperature', 0.7) + 0.1)

        return policies

    async def _update_test_generation_policies(self, rewards: dict, patterns: dict) -> dict:
        """
        Atualiza políticas de geração de testes.
        """
        policies = {}

        # Aumentar prioridade para testes que pegam bugs
        test_patterns = patterns.get('test_patterns', [])
        for pattern in test_patterns:
            if pattern.get('bug_detection_rate', 0) > 0.7:
                policies[f"test_type_{pattern['test_type']}_priority"] = "high"
            elif pattern.get('bug_detection_rate', 0) > 0.5:
                policies[f"test_type_{pattern['test_type']}_priority"] = "medium"
            else:
                policies[f"test_type_{pattern['test_type']}_priority'] = "low"

        # Aumentar prioridade para edge cases que pegam bugs
        if rewards.get('high_coverage', 0) > 0:
            policies['include_edge_cases'] = True
        else:
            policies['include_edge_cases'] = False

        return policies

    async def _update_template_selection_policies(self, rewards: dict, patterns: dict) -> dict:
        """
        Atualiza políticas de seleção de templates.
        """
        policies = {}

        # Aumentar peso para templates que geram código de alta qualidade
        template_patterns = patterns.get('template_patterns', [])
        for pattern in template_patterns:
            if pattern.get('success_rate', 0) > 0.8:
                policies[f"template_{pattern['template_id']}_fitness_boost"] = 0.2
            elif pattern.get('success_rate', 0) > 0.6:
                policies[f"template_{pattern['template_id']}_fitness_boost"] = 0.1

        # Penalizar templates que geram código lento
        if rewards.get('slow_build', 0) < -0.1:
            policies[f"template_{pattern['template_id']_penalty"] = 0.1

        return policies

    async def _update_tool_selection_policies(self, rewards: dict, patterns: dict) -> dict):
        """
        Atualiza políticas de seleção de ferramentas.
        """
        policies = {}

        # Aumentar prioridade para ferramentas que melhoram sucesso
        tool_patterns = patterns.get('tool_patterns', [])
        for pattern in tool_patterns:
            if pattern.get('improves_quality', 0) > 0.3:
                policies[f"tool_{pattern['tool_id']_preference_boost"] = 0.15

        return policies

    async def _apply_policy_updates(self, policy_updates: dict) -> dict:
        """
        Aplica atualizações de políticas.
        """
        applied_updates = []

        # Aplicar atualizações de políticas de geração de código
        code_policies = policy_updates.get('code_generation_policies', {})
        for policy_name, policy_value in code_policies.items():
            result = await self._apply_code_generation_policy(policy_name, policy_value)
            applied_updates.append(result)

        # Aplicar atualizações de políticas de geração de testes
        test_policies = policy_updates.get('test_generation_policies', {})
        for policy_name, policy_value in test_policies.items():
            result = await self._apply_test_generation_policy(policy_name, policy_value)
            applied_updates.append(result)

        # Aplicar atualizações de seleção de templates
        template_policies = policy_updates.get('template_selection_policies', {})
        for policy_name, policy_value in template_policies.items():
            result = await self._apply_template_selection_policy(policy_name, policy_value)
            applied_updates.append(result)

        # Aplicar atualizações de seleção de ferramentas
        tool_policies = policy_updates.get('tool_selection_policies', {})
        for policy_name, policy_value in tool_policies.items():
            result = await self._apply_tool_selection_policy(policy_name, policy_value)
            applied_updates.append(result)

        return {
            "total_updates": len(applied_updates),
            "successful_updates": len([u for u in applied_updates if u.get('success', False)]),
            "failed_updates": len([u for u in applied_updates if not u.get('success', True)]),
            "updates": applied_updates
        }

    async def _validate_impact(self, feedback_data: dict, applied_updates: dict) -> dict:
        """
        Valida impacto das atualizações.
        """
        # Simular impacto esperado
        expected_impact = await self._simulate_impact(applied_updates)

        # Comparar com feedback histórico
        historical_comparison = await self._compare_with_historical(feedback_data, expected_impact)

        validation = {
            "expected_impact_score": expected_impact.get('score', 0),
            "confidence": historical_comparison.get('confidence', 0.5),
            "recommendation": historical_comparison.get('recommendation', 'monitor')
        }

        if validation.get('confidence') > 0.8 and validation.get('expected_impact_score') > 0.1:
            validation['status'] = 'approved'
        elif validation.get('expected_impact_score') < 0:
            validation['status'] = 'rejected'
        else:
            validation['status'] = 'monitor'

        return validation
```

**Output:**
```json
{
  "feedback_analysis": {
    "build_success_rate": 0.92,
    "test_success_rate": 0.89,
    "average_coverage": 83.5,
    "common_failure_reasons": [
      {"reason": "ImportError: cannot import name 'User'", "count": 15, "percentage": 25},
      {"reason": "Timeout: Database query took too long", "count": 10, "percentage": 17},
      {"reason": "Validation error: Invalid email format", "count": 8, "percentage": 13}
    ],
    "high_risk_components": [
      {"component": "user-service", "failure_rate": 0.15, "risk_score": 0.85},
      {"component": "order-service", "failure_rate": 0.12, "risk_score": 0.72},
      {"component": "payment-service", "failure_rate": 0.10, "risk_score": 0.65}
    ]
  },
  "identified_patterns": {
    "successful_patterns": [
      {"id": "pattern_1", "type": "code", "description": "Using Pydantic for validation", "success_rate": 0.95},
      {"id": "pattern_2", "type": "test", "description": "Including edge cases", "success_rate": 0.92"},
      {"id": "pattern_3", "template": "description": "Template: FastAPI + Pydantic", "success_rate": 0.94}
    ],
    "failure_patterns": [
      {"id": "pattern_4", "type": "code", "description": "Missing error handling", "failure_rate": 0.30},
      {"id": "pattern_5", "type": "test", "description": "No async tests", "failure_rate": 0.25},
      {"id": "pattern_6", "template": "description": "Template: Flask + no validation", "failure_rate": 0.28}
    ],
    "code_patterns": [
      {"template_id": "fastapi_pydantic", "weight": 1.2, "success_rate": 0.95},
      {"template_id": "flask_basic", "weight": 0.7, "success_rate": 0.70},
      {"template_id": "django_basic", "weight": 0.8, "success_rate": 0.75}
    ],
    "test_patterns": [
      {"test_type": "unit", "priority": "high", "bug_detection_rate": 0.85},
      {"test_type": "integration", "priority": "medium", "bug_detection_rate": 0.72},
      {"test_type": "e2e", "priority": "medium", "bug_detection_rate": 0.68}
    ],
    "template_patterns": [
      {"template_id": "fastapi_pydantic", "fitness_boost": 0.2},
      {"template_id": "flask_basic", "fitness_boost": 0.0},
      {"template_id": "django_basic", "fitness_boost": 0.1}
    ],
    "tool_patterns": [
      {"tool_id": "pytest", "preference_boost": 0.15},
      {"tool_id": "black", "preference_boost": 0.1},
      {"tool_id": "ruff", "preference_boost": 0.1}
    ]
  },
  "rewards": {
    "build_success": 0.92,
    "high_coverage": 0.35,
    "no_flaky_tests": 0.3,
    "fast_build": 0.1,
    "successful_pattern_pattern_1": 0.5,
    "successful_pattern_pattern_2": 0.5,
    "successful_pattern_pattern_3": 0.5,
    "failure_pattern_pattern_4": -0.5,
    "failure_pattern_pattern_5": -0.5,
    "failure_pattern_pattern_6": -0.5
  },
  "policy_updates": {
    "code_generation_policies": {
      "template_fastapi_pydantic_weight": 1.2,
      "template_flask_basic_weight": 0.7,
      "django_basic_weight": 0.8,
      "llm_temperature": 0.6,
      "include_error_handling": true,
      "include_async_tests": true
    },
    "test_generation_policies": {
      "unit_priority": "high",
      "integration_priority": "medium",
      "e2e_priority": "medium",
      "include_edge_cases": true,
      "minimum_coverage_target": 0.8
    },
    "template_selection_policies": {
      "template_fastapi_pydantic_fitness_boost": 0.2,
      "template_flask_basic_fitness_boost": 0.0,
      "template_django_basic_fitness_boost": 0.1,
      "template_fastapi_pydantic_penalty": 0.0,
      "template_flask_basic_penalty": 0.1,
      "template_django_basic_penalty": 0.0
    },
    "tool_selection_policies": {
      "pytest_preference_boost": 0.15,
      "black_preference_boost": 0.1,
      "ruff_preference_boost": 0.1
    }
  },
  "applied_updates": {
    "total_updates": 12,
    "successful_updates": 11,
    "failed_updates": 1,
    "updates": [
      {"policy_name": "template_fastapi_pydantic_weight", "old_value": 1.0, "new_value": 1.2, "success": true},
      {"policy_name": "llm_temperature", "old_value": 0.7, "new_value": 0.6, "success": true},
      {"policy_name": "include_error_handling", "old_value": false, "new_value": true, "success": true},
      {"policy_name": "unit_priority", "old_value": "medium", "new_value": "high", "success": true},
      {"policy_name": "template_fastapi_pydantic_fitness_boost", "old_value": 0.0, "new_value": 0.2, "success": true}
    ]
  },
  "impact_validation": {
    "expected_impact_score": 0.12,
    "confidence": 0.85,
    "recommendation": "approved",
    "status": "approved"
  },
  "generated_at": "2026-04-15T19:00:00Z"
}
```

---

### 9.3 Auto-Corrector

**Responsabilidade:** Corrige código automaticamente quando testes falham.

**Consumir:**
- `tests.completed` (do Software Engineering Pipeline)
- `build.failed` (do Software Engineering Pipeline)
- `agent.errors` (do Agentic Delegation System)
- `code.generated` (do Code Forge)

**Processamento:**
```python
# services/ci-feedback-loop/src/services/auto_corrector.py

class AutoCorrector:
    async def auto_correct(self, test_results: dict, build_errors: dict, agent_errors: List[dict], code: dict) -> dict:
        """
        Corrige código automaticamente.

        Processo:
        1. Analisar falhas de testes (testes que falharam)
        2. Analisar erros de build (compilação, linting, etc.)
        3. Analisar erros de agentes (syntax, runtime, etc.)
        4. Identificar tipos de correção necessárias
        5. Gerar fixes para cada erro
        6. Priorizar correções (crítico, alto, médio, baixo)
        7. Aplicar fixes (com rollback automático se falhar)
        8. Validar correções
        9. Gerar PR com correções
        """
        # Analisar falhas de testes
        test_fixes = await self._analyze_test_failures(test_results)

        # Analisar erros de build
        build_fixes = await self._analyze_build_errors(build_errors)

        # Analisar erros de agentes
        agent_fixes = await self._analyze_agent_errors(agent_errors)

        # Consolidar todas as correções necessárias
        all_corrections = test_fixes + build_fixes + agent_fixes

        # Priorizar correções
        prioritized_corrections = await self._prioritize_corrections(all_corrections)

        # Aplicar correções
        applied_fixes = await self._apply_fixes(prioritized_corrections, code)

        # Validar correções
        validation_results = await self._validate_fixes(applied_fixes)

        # Gerar PR com correções
        pr = await self._generate_pull_request(applied_fixes, validation_results)

        return {
            "test_fixes": test_fixes,
            "build_fixes": build_fixes,
            "agent_fixes": agent_fixes,
            "prioritized_corrections": prioritized_corrections,
            "applied_fixes": applied_fixes,
            "validation_results": validation_results,
            "pull_request": pr,
            "generated_at": datetime.utcnow().isoformat()
        }

    async def _analyze_test_failures(self, test_results: dict) -> List[dict]:
        """
        Analisa falhas de testes.
        """
        test_fixes = []

        for test in test_results.get('failed_tests', []):
            test_name = test.get('name', '')
            error_message = test.get('error', '')
            stack_trace = test.get('stack_trace', '')

            # Identificar tipo de correção
            correction_type = await self._identify_correction_type(test, error_message, stack_trace)

            # Gerar correção
            correction = {
                "test_name": test_name,
                "error": error_message,
                "type": correction_type,
                "severity": test.get('severity', 'medium'),
                "file": test.get('file'),
                "line": test.get('line'),
                "code_snippet": test.get('code_snippet', ''),
                "suggested_fix": await self._generate_fix(correction_type, test),
                "confidence": await self._estimate_fix_confidence(correction_type, error_message, stack_trace)
            }

            test_fixes.append(correction)

        return test_fixes

    async def _identify_correction_type(self, test: dict, error_message: str, stack_trace: str) -> str:
        """
        Identifica tipo de correção necessária.
        """
        error_lower = error_message.lower()

        if 'assertionerror' in error_lower:
            if 'assert' in error_lower and 'equal' in error_lower:
                return 'fix_assertion'
            elif 'assert' in error_lower and 'true' in error_lower:
                return 'fix_boolean_assertion'
            elif 'assert' in error_lower and 'false' in error_lower:
                return 'fix_boolean_assertion'
            elif 'raises' in error_lower and 'valueerror' in error_lower:
                return 'fix_exception_type_error'
        elif 'raises' in error_lower and 'timeout' in error_lower:
                return 'fix_timeout'
        elif 'keyerror' in error_lower:
                return 'fix_missing_key'
            elif 'attributeerror' in error_lower:
                return 'fix_missing_attribute'
            elif 'typeerror' in error_lower:
                return 'fix_type_error'
        elif 'importerror' in error_lower:
            return 'fix_import_error'
        elif 'namerror' in error_lower:
            return 'fix_name_error'
        elif 'unboundlocalerror' in error_lower:
            return 'fix_unbound_local'
        else:
            return 'unknown_assertion_error'

        elif 'timeout' in error_lower:
            return 'increase_timeout'

        else:
            return 'unknown_error'

    async def _generate_fix(self, correction_type: str, test: dict) -> dict:
        """
        Gera correção para um erro de teste.
        """
        fix = {
            "type": correction_type,
            "file": test.get('file'),
            "line": test.get('line'),
            "original_code": test.get('code_snippet', ''),
            "suggested_code": "",
            "confidence": test.get('confidence', 0.0),
            "applied": False
        }

        # Gerar correção baseado no tipo
        if correction_type == 'fix_assertion':
            fix['suggested_code'] = await self._generate_assertion_fix(test)
        elif correction_type == 'fix_import_error':
            fix['suggested_code'] = await self._generate_import_fix(test)
        elif correction_type == 'fix_missing_key':
            fix['suggested_code'] = await self._generate_missing_key_fix(test)
        elif correction_type == 'fix_timeout':
            fix['suggested_code'] = await self._generate_timeout_fix(test)
        else:
            fix['suggested_code'] = await self._generate_generic_fix(test)

        return fix

    async def _generate_assertion_fix(self, test: dict) -> str:
        """
        Gera correção para erro de assertion.
        """
        code_snippet = test.get('code_snippet', '')

        # Analisar assertion
        if '==' in code_snippet and 'expected' in code_snippet:
            # Fix: Verificar lógica de comparação
            if 'not' in code_snippet and 'is None' in code_snippet:
                # Fix: Adicionar is not None check
                return code_snippet.replace('is None', 'is not None')
            elif '>' in code_snippet and '>=' in code_snippet:
                # Fix: Verificar lógica de comparação
                return code_snippet.replace('>=', '>=', 1)  # Ajustar delta se necessário
        elif 'in' in code_snippet and 'not in' in code_snippet:
                # Fix: Verificar se item está na coleção
                pass  # Precisaria de contexto
        elif 'len(' in code_snippet:
            # Fix: Verificar tamanho da coleção
            match = re.search(r'len\(([^)]+)\)\s*[<>!=]+\s*(\d+)', code_snippet)
            if match:
                operator, expected_length = match.groups()
                return code_snippet.replace(operator, f"{operator} {expected_length}")

        return code_snippet

    async def _generate_import_fix(self, test: dict) -> str:
        """
        Gera correção para erro de import.
        """
        code_snippet = test.get('code_snippet', '')

        # Analisar import
        match = re.search(r'import\s+(\w+)', code_snippet)
        if not match:
            return code_snippet

        module_name = match.group(1)

        # Fix: Verificar se módulo existe
        if module_name in ['numpy', 'pandas', 'requests', 'sqlalchemy']:
            return code_snippet  # Import correto
        else:
            # Fix: Comentar import ou remover
            return f"# TODO: Fix import for {module_name}\n{code_snippet}"

    async def _apply_fixes(self, prioritized_corrections: List[dict], code: dict) -> dict:
        """
        Aplica correções ao código.
        """
        applied_fixes = []
        skipped_fixes = []

        for correction in prioritized_corrections:
            try:
                # Ler arquivo
                file_content = code.get('files', {}).get(correction['file'], '')
                lines = file_content.split('\n')

                # Aplicar correção na linha específica
                line_number = correction.get('line', 1) - 1  # 0-indexed
                if 0 <= line_number < len(lines):
                    lines[line_number] = correction.get('suggested_code', lines[line_number])
                    corrected_file_content = '\n'.join(lines)

                    # Validar correção
                    validation = await self._validate_fix(correction, corrected_file_content)

                    if validation.get('valid', True):
                        applied_fixes.append({
                            **correction,
                            "validation": validation
                        })
                    else:
                        skipped_fixes.append({
                            **correction,
                            "validation": validation,
                            "skip_reason": "Validation failed"
                        })
                else:
                    skipped_fixes.append({
                        **correction,
                        "validation": {"valid": False, "skip_reason": "Line number out of range"}
                    })

            except Exception as e:
                skipped_fixes.append({
                    **correction,
                    "validation": {"valid": False, "skip_reason": f"Exception: {str(e)}"}
                })

        return {
            "total_corrections": len(prioritized_corrections),
            "applied_fixes": len(applied_fixes),
            "skipped_fixes": len(skipped_fixes),
            "applied_fixes": applied_fixes,
            "skipped_fixes": skipped_fixes,
            "generated_at": datetime.utcnow().isoformat()
        }

    async def _validate_fix(self, correction: dict, corrected_code: str) -> dict:
        """
        Valida se a correção é válida.
        """
        validation = {
            "valid": False,
            "warnings": [],
            "lint_score": 0.0
        }

        try:
            # Parse syntax com ast (Python)
            if correction.get('file', '').endswith('.py'):
                import ast
                ast.parse(corrected_code)
                validation['valid'] = True
                validation['lint_score'] = 1.0

                # Checar por warnings comuns
                if 'TODO:' in corrected_code:
                    validation['warnings'].append('Fix marked as TODO - review necessário')
                elif 'FIXME:' in corrected_code:
                    validation['warnings'].append('Fix marked as FIXME - review necessário')

        except SyntaxError as e:
            validation['valid'] = False
            validation['error'] = f"SyntaxError: {str(e)}"
        except Exception as e:
            validation['valid'] = False
            validation['error'] = f"Unexpected error: {str(e)}"

        return validation

    async def _generate_pull_request(self, applied_fixes: List[dict], validation_results: dict) -> dict:
        """
        Gera PR com correções.
        """
        pr = {
            "title": "Auto-correction fixes",
            "description": f"Automatically generated fixes for {len(applied_fixes)} failed tests and errors",
            "branch": f"fix/auto-correction-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}",
            "target": "main",
            "labels": ["auto-generated", "fix", "ci-feedback"],
            "body": await self._generate_pr_body(applied_fixes, validation_results),
            "generated_at": datetime.utcnow().isoformat()
        }

        return pr
```

---

### 9.4 Failure Analyzer

**Responsabilidade:** Analisa falhas de build/test e identifica padrões de erro.

**Consumir:**
- `feedback.collected` (do Feedback Collector)
- `build.failed` (do Software Engineering Pipeline)
- `tests.completed` (do Software Engineering Pipeline)

**Processamento:**
```python
# services/ci-feedback-loop/src/services/failure_analyzer.py

class FailureAnalyzer:
    async def analyze_failures(self, failure_data: dict, historical_data: List[dict]) -> dict:
        """
        Analisa falhas e identifica padrões.

        Processo:
        1. Analisar falha atual (tipo, mensagem, stack trace)
        2. Comparar com falhas históricas
        3. Identificar padrões de falha
        4. Classificar severidade e impacto
        5. Identificar causa raiz
        6. Gerar recomendações de prevenção
        7. Gerar relatório detalhado
        """
        # Analisar falha atual
        current_failure = await self._analyze_current_failure(failure_data)

        # Buscar falhas similares históricas
        similar_failures = await self._search_similar_failures(current_failure, historical_data)

        # Identificar padrões
        patterns = await self._identify_failure_patterns(failure_data, similar_failures)

        # Classificar severidade
        severity = await self._classify_severity(current_failure, patterns)

        # Identificar causa raiz
        root_cause = await self._identify_root_cause(current_failure, similar_failures)

        # Gerar recomendações de prevenção
        recommendations = await self._generate_prevention_recommendations(patterns, root_cause)

        # Gerar relatório
        report = {
            "failure_id": failure_data.get('id'),
            "current_failure": current_failure,
            "similar_failures": similar_failures,
            "patterns": patterns,
            "severity": severity,
            "root_cause": root_cause,
            "recommendations": recommendations,
            "generated_at": datetime.utcnow().isoformat()
        }

        return report

    async def _analyze_current_failure(self, failure_data: dict) -> dict:
        """
        Analisa falha atual.
        """
        failure_type = failure_data.get('type', 'unknown')
        error_message = failure_data.get('error_message', '')
        stack_trace = failure_data.get('stack_trace', '')
        context = failure_data.get('context', {})

        return {
            "type": failure_type,
            "message": error_message,
            "stack_trace": stack_trace,
            "context": context,
            "occurred_at": failure_data.get('timestamp', datetime.utcnow().isoformat()),
            "stage": failure_data.get('stage', 'unknown'),
            "component": failure_data.get('component', 'unknown'),
            "service": failure_data.get('service', 'unknown')
        }

    async def _search_similar_failures(self, current_failure: dict, historical_data: List[dict]) -> List[dict]:
        """
        Busca falhas similares históricas.
        """
        similar_failures = []

        for historical_failure in historical_data:
            similarity_score = await self._calculate_failure_similarity(
                current_failure,
                historical_failure
            )

            if similarity_score > 0.7:  # Threshold de similaridade
                similar_failures.append({
                    "failure_id": historical_failure.get('id'),
                    "similarity_score": similarity_score,
                    "occurred_at": historical_failure.get('timestamp', ''),
                    "resolution": historical_failure.get('resolution', {}),
                    "reoccurrence_count": historical_failure.get('reoccurrence_count', 0) + 1
                })

        # Ordenar por similaridade
        similar_failures.sort(key=lambda x: x['similarity_score'], reverse=True)

        return similar_failures[:10]  # Top 10 mais similares

    async def _calculate_failure_similarity(self, failure1: dict, failure2: dict) -> float:
        """
        Calcula similaridade entre duas falhas.
        """
        similarity = 0.0

        # Comparar tipos de erro
        if failure1.get('type') == failure2.get('type'):
            similarity += 0.4

        # Comparar mensagens de erro
        message1 = failure1.get('error_message', '')
        message2 = failure2.get('error_message', '')
        message_similarity = await self._calculate_text_similarity(message1, message2)
        similarity += message_similarity * 0.3

        # Comparar stack traces
        stack1 = failure1.get('stack_trace', '')
        stack2 = failure2.get('stack_trace', '')
        stack_similarity = await self._calculate_text_similarity(stack1, stack2)
        similarity += stack_similarity * 0.3

        return similarity

    async def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """
        Calcula similaridade entre dois textos.
        """
        # Usar simple Jaccard similarity para simplicidade
        set1 = set(text1.lower().split())
        set2 = set(text2.lower().split())

        intersection = set1.intersection(set2)
        union = set1.union(set2)

        if len(union) == 0:
            return 0.0

        jaccard = len(intersection) / len(union)
        return jaccard

    async def _identify_failure_patterns(self, failure_data: dict, similar_failures: List[dict]) -> List[dict]:
        """
        Identifica padrões de falha.
        """
        patterns = []

        # Padrão 1: Falhas de importação
        if 'import error' in failure_data.get('error_message', '').lower():
            patterns.append({
                "pattern_type": "import_error",
                "frequency": len([f for f in similar_failures if 'import error' in f.get('error_message', '').lower()]) + 1,
                "most_common_modules": await self._extract_common_modules(similar_failures)
            })

        # Padrão 2: Timeouts
        if 'timeout' in failure_data.get('error_message', '').lower():
            patterns.append({
                "pattern_type": "timeout",
                "frequency": len([f for f in similar_failures if 'timeout' in f.get('error_message', '').lower()]) + 1,
                "timeout_duration": await self._extract_common_timeout_duration(similar_failures)
            })

        # Padrão 3: Erros de validação
        if 'validation error' in failure_data.get('error_message', '').lower():
            patterns.append({
                "pattern_type": "validation_error",
                "frequency": len([f for f in similar_failures if 'validation error' in f.get('error_message', '').lower()]) + 1,
                "validation_errors": await self._extract_common_validation_errors(similar_failures)
            })

        return patterns

    async def _extract_common_modules(self, similar_failures: List[dict]) -> List[str]:
        """
        Extrai módulos comuns que causam erros de importação.
        """
        module_counts = {}

        for failure in similar_failures:
            error_message = failure.get('error_message', '')
            match = re.search(r"import\s+(\w+)", error_message)
            if match:
                module_name = match.group(1)
                if module_name not in module_counts:
                    module_counts[module_name] = 0
                module_counts[module_name] += 1

        # Ordenar por frequência
        sorted_modules = sorted(module_counts.items(), key=lambda x: x[1], reverse=True)

        return [module[0] for module, count in sorted_modules[:10]]

    async def _classify_severity(self, failure: dict, patterns: List[dict]) -> dict:
        """
        Classifica severidade da falha.
        """
        severity = {
            "level": "medium",
            "impact": "low",
            "affected_components": [],
            "estimated_fix_time_minutes": 5
        }

        # Severidade baseado em tipo de erro
        error_type = failure.get('type', 'unknown')

        if error_type == 'database_connection_error':
            severity['level'] = 'critical'
            severity['impact'] = 'high'
            severity['affected_components'] = ['database', 'all']
            severity['estimated_fix_time_minutes'] = 15
        elif error_type == 'security_error':
            severity['level'] = 'critical'
            severity['impact'] = 'high'
            severity['affected_components'] = ['security', 'all']
            severity['estimated_fix_time_minutes'] = 10
        elif error_type == 'timeout_error':
            severity['level'] = 'high'
            severity['impact'] = 'medium'
            severity['affected_components'] = ['all']
            severity['estimated_fix_time_minutes'] = 3
        elif error_type == 'validation_error':
            severity['level'] = 'medium'
            severity['impact'] = 'low'
            severity['affected_components'] = ['specific component']
            severity['estimated_fix_time_minutes'] = 2

        # Ajustar severidade baseado em frequência
        for pattern in patterns:
            if pattern.get('pattern_type') == error_type:
                frequency = pattern.get('frequency', 0)
                if frequency > 10:
                    severity['level'] = 'critical'
                    severity['estimated_fix_time_minutes'] = 2

        return severity

    async def _identify_root_cause(self, failure: dict, similar_failures: List[dict]) -> dict:
        """
        Identifica causa raiz da falha.
        """
        root_cause = {
            "type": "unknown",
            "description": "Causa raiz não identificada",
            "suggested_fixes": [],
            "prevention_measures": []
        }

        error_type = failure.get('type', 'unknown')
        error_message = failure.get('error_message', '')

        # Mapeamento de causas raiz conhecidas
        known_root_causes = {
            "importerror": {
                "type": "missing_dependency",
                "description": "Módulo não instalado ou não importado corretamente",
                "suggested_fixes": ["Instalar módulo ou corrigir import"],
                "prevention_measures": ["Verificar requirements.txt", "Usar virtual environments"]
            },
            "keyerror": {
                "type": "missing_key",
                "description": "Chave não encontrada em dicionário ou lista",
                "suggested_fixes": ["Adicionar chave a dicionário antes de acessar", "Usar dict.get() com valor padrão"],
                "prevention_measures": ["Validar chaves antes de acessar"]
            },
            "timeouterror": {
                "type": "operation_timeout",
                "description": "Operação demorou mais do que o timeout configurado",
                "suggested_fixes": ["Aumentar timeout", "Otimizar operação", "Usar async/await corretamente"],
                "prevention_measures": ["Ajustar timeout baseado em testes de performance"]
            },
            "databaseerror": {
                "type": "database_issue",
                "description": "Erro de conexão ou query",
                "suggested_fixes": ["Verificar string de conexão", "Verificar query SQL", "Verificar disponibilidade do banco"],
                "prevention measures": ["Implementar connection pooling", "Adicionar retry logic", "Usar transações corretamente"]
            }
        }

        # Identificar tipo de erro
        if error_type == 'importerror' or 'module not found':
            root_cause = known_root_causes['importerror']
        elif 'keyerror' in error_type or 'key not found' in error_message.lower():
            root_cause = known_root_causes['keyerror']
        elif 'timeout' in error_type or 'timeout' in error_message.lower():
            root_cause = known_root_causes['timeouterror']
        elif 'database' in error_type or 'database' in error_type.lower():
            root_cause = known_root_causes['databaseerror']
        elif 'connection' in error_type or 'connection' in error_message.lower():
            root_cause = known_root_causes['databaseerror']

        # Analisar stack trace para mais detalhes
        stack_trace = failure.get('stack_trace', '')
        if 'connection' in stack_trace.lower():
            root_cause['type'] = 'database_connection_issue'
            root_cause['description'] = f"Falha de conexão detectada no stack trace: {stack_trace[:100]}..."

        return root_cause

    async def _generate_prevention_recommendations(self, patterns: List[dict], root_cause: dict) -> List[str]:
        """
        Gera recomendações de prevenção.
        """
        recommendations = []

        # Recomendações baseadas em padrões
        for pattern in patterns:
            if pattern.get('pattern_type') == 'import_error':
                recommendations.append("Adicionar verificação de dependências no CI pipeline")
                recommendations.append("Usar ferramentas como pip-audit ou safety para detectar dependências desatualizadas")
            elif pattern.get('pattern_type') == 'timeout':
                recommendations.append("Aumentar timeout de testes lentos identificados")
                recommendations.append("Otimizar operações lentas com profiling")
            elif pattern.get('pattern_type') == 'validation_error':
                recommendations.append("Adicionar mais testes edge cases para cenários não cobertos")
                recommendations.append("Refatorar código para simplificar lógica complexa")

        # Recomendações baseadas em causa raiz
        if root_cause['type'] == 'missing_dependency':
            recommendations.append("Verificar se todas as dependências estão em requirements.txt")
            recommendations.append("Documentar dependências externas obrigatórias")
            recommendations.append("Usar ferramenta de dependências para garantir consistência")
        elif root_cause['type'] == 'operation_timeout':
            recommendations.append("Fazer profiling de código para identificar operações lentas")
            recommendations.append("Otimizar queries de banco de dados se timeout for em queries")
            recommendations.append("Aumentar recursos computacionais se timeout for por CPU/memory")
        elif root_cause['type'] == 'database_connection_issue':
            recommendations.append("Implementar retry com exponential backoff para conexões")
            recommendations.append("Usar connection pooling para melhorar performance")
            recommendations.append("Monitorar métricas de latência do banco")

        return recommendations
```

**Output:**
```json
{
  "failure_id": "failure_uuid",
  "current_failure": {
    "type": "database_error",
    "message": "OperationalError: could not connect to server: Connection refused",
    "stack_trace": "Traceback (most recent call last):\n  File \"src/repositories/order_repository.py\", line 45, in get_by_id\n    db.connect()\n    OperationalError: could not connect to server: Connection refused",
    "context": {
      "operation": "query_order_by_id",
      "service": "order-service",
      "stage": "test",
      "component": "order-service",
      "environment": "staging"
    },
    "occurred_at": "2026-04-15T19:15:00Z"
  },
  "similar_failures": [
    {
      "failure_id": "failure_1",
      "similarity_score": 0.92,
      "occurred_at": "2026-04-10T14:30:00Z",
      "resolution": {
        "fix": "Aumentar timeout de conexão no database",
        "resolution_type": "configuration_change",
        "resolved_by": "admin"
      },
      "reoccurrence_count": 15
    },
    {
      "failure_id": "failure_2",
      "similarity_score": 0.88,
      "occurred_at": "2026-04-12T16:45:00Z",
      "resolution": {
        "fix": "Adicionar retry com exponential backoff",
        "resolution_type": "code_change",
        "resolved_by": "developer"
      },
      "reoccurrence_count": 8
    }
  ],
  "patterns": [
    {
      "pattern_type": "database_connection_error",
      "frequency": 23,
      "common_modules": ["psycopg2", "asyncpg", "sqlalchemy"],
      "timeout_duration": "5-10s"
    },
    {
      "pattern_type": "retry_exhausted",
      "frequency": 12,
      "common_timeout_values": ["30s", "60s", "120s"]
    }
  ],
  "severity": {
    "level": "critical",
    "impact": "high",
    "affected_components": ["order-service", "all"],
    "estimated_fix_time_minutes": 15
  },
  "root_cause": {
    "type": "database_connection_issue",
    "description": "Falha de conexão detectada no stack trace. Ocorre frequentemente em testes de integração. A conexão ao banco de dados falha provavelmente devido a: 1) Banco indisponível, 2) Network issue, 3) Timeout muito agressivo (5s)",
    "suggested_fixes": [
      "Verificar disponibilidade do banco de dados",
      "Aumentar timeout de conexão para testes de integração",
      "Adicionar retry com exponential backoff para conexões",
      "Monitorar métricas de latência de conexões"
    ],
    "prevention_measures": [
      "Implementar retry com exponential backoff para todas as conexões de banco",
      "Usar connection pooling para melhorar performance",
      "Monitorar métricas de latência e estabilidade de conexões",
      "Configurar health checks para banco de dados"
    ]
  },
  "recommendations": [
    "Adicionar verificação de dependências no CI pipeline",
    "Usar ferramentas como pip-audit ou safety para detectar dependências desatualizadas",
    "Fazer profiling de código para identificar operações lentas",
    "Otimizar queries de banco de dados se timeout for em queries",
    "Aumentar recursos computacionais se timeout for por CPU/memory",
    "Implementar retry com exponential backoff para todas as conexões de banco",
    "Usar connection pooling para melhorar performance",
    "Monitorar métricas de latência de conexões",
    "Configurar health checks para banco de dados"
  ],
  "generated_at": "2026-04-15T19:30:00Z"
}
```

---

### 9.5 Optimization Suggester

**Responsabilidade:** Sugere otimizações baseadas em métricas de qualidade.

**Consumir:**
- `feedback.collected` (do Feedback Collector)
- `policy_updates.applied` (do Reinforcement Learner)
- `quality_scores` (do Feedback Collector)
- `anomalies` (do Feedback Collector)

**Processamento:**
```python
# services/ci-feedback-loop/src/services/optimization_suggester.py

class OptimizationSuggester:
    async def suggest_optimizations(self, feedback_data: dict, policy_updates: dict, quality_scores: dict, anomalies: List[dict]) -> dict:
        """
        Sugere otimizações baseado em métricas.

        Processo:
        1. Analisar métricas de qualidade (testes, build, deployment)
        2. Identificar áreas de baixa qualidade
        3. Analisar anomalias recorrentes
        4. Comparar com benchmarks históricos
        5. Gerar sugestões de otimização
        6. Priorizar sugestões por impacto e esforço
        7. Estimar benefícios esperadas
        """
        suggestions = []

        # Sugestões de otimização de testes
        test_optimizations = await self._suggest_test_optimizations(feedback_data, quality_scores, anomalies)
        suggestions.extend(test_optimizations)

        # Sugestões de otimização de build
        build_optimizations = await self._suggest_build_optimizations(feedback_data, quality_scores, anomalies)
        suggestions.extend(build_optimizations)

        # Sugestões de otimização de deploy
        deploy_optimizations = await self._suggest_deploy_optimizations(feedback_data, quality_scores, anomalies)
        suggestions.extend(deploy_optimizations)

        # Ordenar sugestões por impacto
        sorted_suggestions = sorted(
            suggestions,
            key=lambda x: x.get('estimated_benefit_score', 0),
            reverse=True
        )

        return {
            "suggestions": sorted_suggestions,
            "total_suggestions": len(sorted_suggestions),
            "high_priority": len([s for s in sorted_suggestions if s.get('priority') == 'high']),
            "medium_priority": len([s for s in sorted_suggestions if s.get('priority') == 'medium']),
            "low_priority": [s for s in sorted_suggestions if s.get('priority') == 'low']),
            "generated_at": datetime.utcnow().isoformat()
        }

    async def _suggest_test_optimizations(self, feedback_data: dict, quality_scores: dict, anomalies: List[dict]) -> List[dict]:
        """
        Sugere otimizações de testes.
        """
        suggestions = []

        test_metrics = feedback_data.get('test_metrics', {})

        # Sugestão 1: Aumentar coverage se baixa
        if quality_scores.get('test', 0) < 0.75:
            suggestions.append({
                "priority": "high",
                "area": "test_coverage",
                "current_state": f"Coverage: {quality_scores['test']*100:.1f}%",
                "target_state": "Coverage: 80%",
                "impact": "medium",
                "estimated_effort_hours": 4,
                "description": "Aumentar número de testes para atingir target de 80% de coverage",
                "actions": [
                    "Gerar testes para código não coberto",
                    "Gerar testes edge cases para cenários não cobertos"
                ],
                "estimated_benefit_score": 0.15
            })

        # Sugestão 2: Reduzir testes flaky se houver muitos
        flaky_tests = test_metrics.get('flaky_tests', [])
        if len(flaky_tests) > 5:
            suggestions.append({
                "priority": "high",
                "area": "flaky_tests",
                "current_state": f"Flaky tests: {len(flaky_tests)}",
                "target_state": "Flaky tests: 0",
                "impact": "high",
                "estimated_effort_hours": 6,
                "description": f"Estabilizar {len(flaky_tests)} testes instáveis que estão falhando",
                "actions": [
                    "Investigar causas de instabilidade",
                    "Usar fixtures consistentes",
                    "Adicionar waits explícitos",
                    "Isolar testes paralelos",
                    "Usar mocks para dependências externas"
                ],
                "estimated_benefit_score": 0.25
            })

        # Sugestão 3: Aumentar mutation score se baixo
        mutation_score = test_metrics.get('mutation_score', 0)
        if mutation_score < 0.8:
            suggestions.append({
                "priority": "medium",
                "area": "mutation_testing",
                "current_state": f"Mutation score: {mutation_score*100:.1f}%",
                "target_state": "Mutation score: 85%",
                "impact": "medium",
                "estimated_effort_hours": 2,
                "description": "Aumentar覆盖率 de mutants e aumentar mutation score para 85%",
                "actions": [
                    "Adicionar testes para cobrir casos não testados",
                    "Melhorar asserts para pegar mais bugs",
                    "Aumentar complexidade de testes existentes"
                ],
                "estimated_benefit_score": 0.1
            })

        # Sugestão 4: Reduzir testes lentos se houver muitos
        slow_tests = test_metrics.get('slow_tests', [])
        if len(slow_tests) > 5:
            suggestions.append({
                "priority": "medium",
                "area": "slow_tests",
                "current_state": f"Slow tests: {len(slow_tests)}",
                "target_state": "Slow tests: 0",
                "impact": "medium",
                "estimated_effort_hours": 3,
                "description": f"Otimizar {len(slow_tests)} testes lentos que estão atrasando o pipeline",
                "actions": [
                    "Investigar gargalos de performance",
                    "Mock dependências externas em testes de unidade",
                    "Usar fixtures e factories para dados complexos",
                    "Paralelizar testes quando possível"
                ],
                "estimated_benefit_score": 0.2
            })

        return suggestions

    async def _suggest_build_optimizations(self, feedback_data: dict, quality_scores: dict, anomalies: List[dict]) -> List[dict]:
        """
        Sugere otimizações de build.
        """
        suggestions = []

        build_metrics = feedback_data.get('build_metrics', {})

        # Sugestão 1: Reduzir tempo de build se muito lento
        build_duration = build_metrics.get('duration_seconds', 0)
        if build_duration > 300:
            suggestions.append({
                "priority": "high",
                "area": "build_duration",
                "current_state": f"Build duration: {build_duration}s (threshold: 300s)",
                "target_state": "Build duration: < 200s",
                "impact": "high",
                "estimated_effort_hours": 8,
                "description": "Reducir tempo de build em 100 segundos (30%) para melhorar CI/CD",
                "actions": [
                    "Paralelizar estágios quando possível",
                    "Cachear dependências (pip cache, Docker layers)",
                    "Otimizar Docker builds (BuildKit, Kaniko cache)",
                    "Usar recursos de build mais potentes"
                ],
                "estimated_benefit_score": 0.2
            })

        # Sugestão 2: Reduzir custo de build se muito alto
        build_cost = build_metrics.get('cost_usd', 0)
        if build_cost > 20:
            suggestions.append({
                "priority": "high",
                "area": "build_cost",
                "current_state": f"Build cost: ${build_cost:.2f}",
                "target_state": "Build cost: < $10",
                "impact": "medium",
                "estimated_effort_hours": 6,
                "description": "Reduzir custo de build em 50% para reduzir custos de CI/CD",
                "actions": [
                    "Revisar uso de recursos (escalar horizontal para jobs curtos)",
                    "Otimizar caching de dependências",
                    "Reduzir tamanho de imagens Docker"
                ],
                "estimated_benefit_score": 0.25
            })

        # Sugestão 3: Aumentar sucesso de build se baixo
        build_success_rate = 0.92
        if build_success_rate < 0.9:
            suggestions.append({
                "priority": "high",
                "area": "build_success_rate",
                "current_state": f"Build success rate: {build_success_rate*100:.1f}%",
                "target_state": "Build success rate: > 95%",
                "impact": "high",
                "estimated_effort_hours": 4,
                "description": "Aumentar taxa de sucesso de build em >5% para reduzir custos de rebuild",
                "actions": [
                    "Identificar causas de falhas comuns (pattern analysis)",
                    "Adicionar mais testes de integração",
                    "Melhorar validação de código (linter, type checking)",
                    "Adicionar checks de sanity no pré-commit"
                ],
                "estimated_benefit_score": 0.3
            })

        return suggestions

    async def _suggest_deploy_optimizations(self, feedback_data: dict, quality_scores: dict, anomalies: List[dict]) -> List[dict]:
        """
        Sugere otimizações de deploy.
        """
        suggestions = []

        deployment_metrics = feedback_data.get('deployment_metrics', {})

        # Sugestão 1: Aumentar uptime se baixo
        uptime = deployment_metrics.get('uptime_seconds', 0)
        uptime_hours = uptime / 3600
        if uptime_hours < 1:
            suggestions.append({
                "priority": "high",
                "area": "deployment_uptime",
                "current_state": f"Uptime: {uptime_hours:.2f}h",
                "target_state": "Uptime: > 99.9%",
                "impact": "high",
                "estimated_effort_hours": 6,
                "description": "Aumentar uptime para > 99.9% para reduzir downtime",
                "actions": [
                    "Implementar auto-scaling proativo",
                    "Implementar health checks mais abrangentes",
                    "Implementar auto-rollback mais rápido",
                    "Implementar blue/green deployment canary checks"
                ],
                "estimated_benefit_score": 0.3
            })

        # Sugestão 2: Reduzir error rate se alto
        error_rate = deployment_metrics.get('error_rate', 0)
        if error_rate > 0.01:  # > 1%
            suggestions.append({
                "priority": "high",
                "area": "deployment_error_rate",
                "current_state": f"Error rate: {error_rate*100:.3f}%",
                "target_state": "Error rate: < 0.5%",
                "impact": "medium",
                "estimated_effort_hours": 4,
                "description": "Reduzir taxa de erro em 50% para melhorar experiência do usuário",
                "actions": [
                    "Implementar circuit breakers mais agressivos",
                    "Implementar retries mais robustos",
                    "Implementar rate limiting mais granular",
                    "Implementar shadow deployments"
                ],
                "estimated_benefit_score": 0.2
            })

        # Sugestão 3: Aumentar throughput se baixo
        throughput = deployment_metrics.get('performance_metrics', {}).get('throughput_rps', 0)
        if throughput < 500:
            suggestions.append({
                "priority": "medium",
                "area": "deployment_throughput",
                "current_state": f"Throughput: {throughput} req/s (threshold: 500 req/s)",
                "target_state": "Throughput: > 1000 req/s",
                "impact": "medium",
                "estimated_effort_hours": 3,
                "description": "Aumentar throughput para 1000 req/s para melhorar experiência do usuário",
                "actions": [
                    "Implementar auto-scaling baseado em CPU/memory",
                    "Otimizar queries de banco de dados (índices, materialized views)",
                    "Aumentar número de workers/pods"
                ],
                "estimated_benefit_score": 0.15
            })

        return suggestions

    async def _generate_optimization_report(self, suggestions: List[dict]) -> str:
        """
        Gera relatório de otimizações.
        """
        report = """# Otimization Report

**Generated:** 2026-04-15T20:00:00Z

## High Priority Optimizations

{await self._generate_optimization_section(suggestions, "high", "High")}

## Medium Priority Optimizations

{await self._generate_optimization_section(suggestions, "medium", "Medium")}

## Low Priority Optimizations

{await self._generate_optimization_section(suggestions, "low", "Low")}

## Estimated Benefits

- **Quality Score Improvement:** +0.15
- **Build Time Reduction:** -30%
- **Cost Reduction:** -40%
- **User Experience Improvement:** +25%

## Implementation Plan

### Phase 1: Test Optimizations (1-2 weeks)
{await self._generate_implementation_plan(s, "test", "High", 1)}

### Phase 2: Build Optimizations (2-3 weeks)
{await self._generate_implementation_plan(s, "build", "High", 1)}

### Phase 3: Deploy Optimizations (1-2 weeks)
{await self._generate_implementation_plan(s, "deploy", "Medium", 2)}

## Risk Assessment

**Low Risk:** Optimizations are non-breaking and reversible
**Mitigation:** A/B test each optimization before rolling out to 100%
"""

        return report

    async def _generate_optimization_section(self, suggestions: List[dict], priority: str, impact_level: str) -> str:
        """
        Gera seção de otimização por prioridade.
        """
        priority_suggestions = [s for s in suggestions if s.get('priority') == priority]

        section = f"## {impact_level} Priority Optimizations\n\n"

        for i, suggestion in enumerate(priority_suggestions, 1):
            section += f"\n### {i}. {suggestion.get('area', 'unknown')}\n\n"
            section += f"**Current State:** {suggestion.get('current_state', 'unknown')}\n\n"
            section += f"**Target State:** {suggestion.get('target_state', 'unknown')}\n\n"
            section += f"**Impact:** {suggestion.get('impact', 'unknown')}\n\n"
            section += f"**Estimated Effort:** {suggestion.get('estimated_effort_hours', 0)} hours\n\n"
            section += f"**Actions:**\n"
            for action in suggestion.get('actions', []):
                section += f"- {action}\n"
            section += f"**Estimated Benefit:** {suggestion.get('estimated_benefit_score', 0)*100:.1f}%\n"

        return section
```

---

### Eventos Kafka Produzidos pelo CI Feedback Loop

```yaml
feedback.collected:
  - Producer: Feedback Collector
  - Consumer: Reinforcement Learner, Failure Analyzer
  - Payload: { id, build_metrics, test_metrics, deployment_metrics, error_metrics, quality_scores, anomalies, timestamp }

policy_updates.applied:
  - Producer: Reinforcement Learner
  - Consumer: Code Forge, Test Generation System
  - Payload: { id, feedback_analysis, identified_patterns, rewards, policy_updates, applied_updates, impact_validation, generated_at }

autocorrections.applied:
  - Producer: Auto-Corrector
  - Consumer: Code Forge, Test Generation System
  - Payload: { id, test_fixes, build_fixes, agent_fixes, prioritized_corrections, applied_fixes, validation_results, pull_request, generated_at }

failures.analyzed:
  - Producer: Failure Analyzer
  - Consumer: Orchestrator Dynamic, Monitoring
  - Payload: { id, current_failure, similar_failures, patterns, severity, root_cause, recommendations, generated_at }

optimizations.suggested:
  - Producer: Optimization Suggester
  - Consumer: Orchestrator Dynamic, Development Team
  - Payload: { id, suggestions, total_suggestions, priority_breakdown, estimated_benefits, implementation_plan, generated_at }
```

---

## Conclusão da Parte 7

O CI Feedback Loop é o sétimo componente crítico do Fluxo G, consumindo resultados de builds/testes e implementando reinforcement learning para otimizar automaticamente.

Este sistema produz 4 tipos principais de eventos Kafka que alimentam os sistemas downstream:
1. `feedback.collected` → Reinforcement Learner, Failure Analyzer
2. `policy_updates.applied` → Code Forge, Test Generation System
3. `autocorrections.applied` → Code Forge, Test Generation System
4. `failures.analyzed` → Orchestrator Dynamic, Monitoring
5. `optimizations.suggested` → Orchestrator Dynamic, Development Team

O CI Feedback Loop permite:
- **Coleta automatizada de feedback** de builds, testes e deployments
- **Análise de padrões de sucesso/falha** com comparação com dados históricos
- **Reinforcement learning** para otimizar políticas de geração de código e testes
- **Auto-correção automática** de bugs e erros com validação
- **Análise de falhas profundas** com identificação de causa raiz e recomendações
- **Sugestões de otimização** baseadas em métricas de qualidade (testes, builds, deployments)

O CI Feedback Loop é fundamental para o aprendizado contínuo do sistema, permitindo que o NHM se torne cada vez mais inteligente na geração de software.

Na próxima parte, documentaremos os **fluxos G e H completos** com exemplos práticos de execução do sistema completo.

---

## 🚀 Fluxo G Completo: Ideia → Software (Exemplo Prático)

### Descrição Geral

O Fluxo G demonstra a jornada completa de uma ideia inicial até software deployado, passando por todos os 7 sistemas documentados nas partes anteriores.

### Exemplo Prático: Delivery App (Uber Eats Clone)

**Ideia Inicial:** "Quero um app de delivery de comida similar ao Uber Eats para o mercado brasileiro"

### Diagrama de Sequência Completo

```mermaid
sequenceDiagram
    autonumber
    participant User as Usuário
    participant Gateway as Gateway Intenções
    participant STE as Semantic Translation
    participant Consensus as Consensus Engine
    participant Orchestrator as Orchestrator Dynamic
    participant ReqEng as Requirements Engineering
    participant ArchPlan as Architectural Planning
    participant AgentDel as Agentic Delegation
    participant CodeForge as Code Forge
    participant TestGen as Test Generation
    participant DocsGen as Documentation Generation
    participant CILoop as CI Feedback Loop
    participant CI as Software Engineering Pipeline
    participant Kafka as Kafka
    participant GitHub as GitHub

    User->>Gateway: POST /api/v1/intentions
    Note over User,Gateway: Payload: Intenção do usuário
    
    Gateway->>STE: intention.submitted
    Note over Gateway,STE: Evento Kafka
    
    STE->>Kafka: intention.translated
    Note over STE,Kafka: Payload: Intenção formatada
    
    Kafka->>Consensus: intention.translated
    
    Consensus->>Kafka: consensus.reached
    Note over Consensus,Kafka: Payload: Plano consensual
    
    Kafka->>Orchestrator: consensus.reached
    
    Orchestrator->>ReqEng: requirements.needed
    Note over Orchestrator,ReqEng: Payload: Intenção + Contexto
    
    ReqEng->>Kafka: requirements.generated
    Note over ReqEng,Kafka: Payload: User stories, Aceite criteria, API design
    
    Kafka->>ArchPlan: requirements.generated
    
    ArchPlan->>Kafka: architectural.plan
    Note over ArchPlan,Kafka: Payload: Bounded contexts, System design, Tech stack
    
    Kafka->>AgentDel: architectural.plan
    
    AgentDel->>Kafka: plan.decomposed
    Note over AgentDel,Kafka: Payload: Tarefas decompostas
    
    AgentDel->>Kafka: agents.assigned
    Note over AgentDel,Kafka: Payload: Agentes atribuídos
    
    Kafka->>CodeForge: plan.decomposed
    Kafka->>CodeForge: agents.assigned
    
    CodeForge->>Kafka: code.generated
    Note over CodeForge,Kafka: Payload: Código fonte completo
    
    Kafka->>TestGen: code.generated
    
    TestGen->>Kafka: tests.generated
    Note over TestGen,Kafka: Payload: Testes unitários, integração, E2E
    
    Kafka->>DocsGen: code.generated
    Kafka->>DocsGen: tests.generated
    
    DocsGen->>Kafka: readme.generated
    DocsGen->>Kafka: api_docs.generated
    DocsGen->>Kafka: architecture_docs.generated
    
    Kafka->>CI: code.generated
    Kafka->>CI: tests.generated
    Kafka->>CI: readme.generated
    
    CI->>GitHub: Push branch + PR
    Note over CI,GitHub: Commit: feat/delivery-app-v1
    
    CI->>CI: Build Docker images
    CI->>CI: Run tests
    CI->>CI: Security scan
    CI->>CI: Deploy to Staging
    CI->>Kafka: build.completed
    Note over CI,Kafka: Payload: Build status, metrics
    
    Kafka->>CILoop: build.completed
    
    CILoop->>Kafka: feedback.collected
    CILoop->>Kafka: policy_updates.applied
    
    CI->>Kafka: deployment.completed
    Note over CI,Kafka: Payload: Deploy status, uptime
    
    Kafka->>CILoop: deployment.completed
    
    CI->>GitHub: Merge to main
    CI->>CI: Deploy to Production
    CI->>User: 🎉 Software Deployado!
    Note over CI,User: URL: https://delivery-app.com
```

---

### Passo 1: Submissão da Intenção

**Endpoint:** `POST /api/v1/intentions`

**Request Payload:**
```json
{
  "id": "int_001",
  "user_id": "user_123",
  "intention": "Quero um app de delivery de comida similar ao Uber Eats para o mercado brasileiro",
  "context": {
    "target_market": "Brazil",
    "budget": "medium",
    "timeline": "3 months",
    "team_size": "small"
  },
  "preferences": {
    "tech_stack_preference": "modern",
    "deployment_target": "cloud",
    "language": "portuguese"
  },
  "submitted_at": "2026-04-15T10:00:00Z"
}
```

**Response (Gateway Intenções):**
```json
{
  "id": "int_001",
  "status": "submitted",
  "message": "Intenção submetida com sucesso",
  "estimated_completion_time": "PT2H",
  "tracking_id": "track_001",
  "next_steps": [
    "Semantic Translation Engine analisará a intenção",
    "Consensus Engine definirá o plano consensual",
    "Orchestrator coordenará a execução"
  ],
  "created_at": "2026-04-15T10:00:05Z"
}
```

---

### Passo 2: Tradução da Intenção (STE)

**Evento Kafka:** `intention.submitted`

**Payload Recebido:**
```json
{
  "id": "int_001",
  "user_id": "user_123",
  "intention": "Quero um app de delivery de comida similar ao Uber Eats para o mercado brasileiro",
  "context": {
    "target_market": "Brazil",
    "budget": "medium",
    "timeline": "3 months",
    "team_size": "small"
  },
  "preferences": {
    "tech_stack_preference": "modern",
    "deployment_target": "cloud",
    "language": "portuguese"
  },
  "submitted_at": "2026-04-15T10:00:00Z"
}
```

**Processamento STE:**
```python
# services/semantic-translation-engine/src/translator.py

class IntentionTranslator:
    async def translate_intention(self, intention_data: dict) -> dict:
        """
        Traduz intenção do usuário para formato estruturado.
        """
        intention_text = intention_data.get('intention', '')
        context = intention_data.get('context', {})
        
        # Análise NLU
        entities = await self._extract_entities(intention_text)
        intents = await self._classify_intent(intention_text)
        
        # Gerar estrutura formatada
        formatted_intention = {
            "id": f"fmt_{intention_data['id']}",
            "original_id": intention_data['id'],
            "primary_intent": intents.get('primary', 'unknown'),
            "secondary_intents": intents.get('secondary', []),
            "domain": "food_delivery",
            "entities": entities,
            "requirements": {
                "functional": self._derive_functional_requirements(intention_text, entities),
                "non_functional": self._derive_non_functional_requirements(context)
            },
            "market_context": {
                "target_market": context.get('target_market', 'Brazil'),
                "language": context.get('language', 'portuguese'),
                "currency": "BRL",
                "payment_methods": ["pix", "credit_card", "cash"]
            },
            "technical_constraints": {
                "budget": context.get('budget', 'medium'),
                "timeline": context.get('timeline', '3 months'),
                "team_size": context.get('team_size', 'small'),
                "tech_preference": intention_data.get('preferences', {}).get('tech_stack_preference', 'modern')
            }
        }
        
        return formatted_intention
```

**Output STE:**
```json
{
  "id": "fmt_int_001",
  "original_id": "int_001",
  "primary_intent": "build_food_delivery_app",
  "secondary_intents": [
    "mobile_app_development",
    "web_admin_panel",
    "payment_integration",
    "real_time_tracking"
  ],
  "domain": "food_delivery",
  "entities": {
    "platform": ["mobile_app", "web_app"],
    "users": ["customers", "restaurant_owners", "delivery_persons", "admins"],
    "features": ["restaurant_catalog", "menu_management", "order_tracking", "payment_processing", "delivery_routing"],
    "integrations": ["payment_gateway", "maps", "notifications"]
  },
  "requirements": {
    "functional": [
      "User registration and authentication",
      "Restaurant browsing and search",
      "Menu viewing and item selection",
      "Order placement and payment",
      "Real-time order tracking",
      "Restaurant owner management interface",
      "Delivery person interface",
      "Admin dashboard"
    ],
    "non_functional": [
      "Scalability: Support 10,000+ concurrent users",
      "Availability: 99.9% uptime",
      "Performance: <200ms response time for APIs",
      "Security: PCI-DSS compliance for payments",
      "Mobile responsiveness"
    ]
  },
  "market_context": {
    "target_market": "Brazil",
    "language": "portuguese",
    "currency": "BRL",
    "payment_methods": ["pix", "credit_card", "cash"]
  },
  "technical_constraints": {
    "budget": "medium",
    "timeline": "3 months",
    "team_size": "small",
    "tech_preference": "modern"
  },
  "translated_at": "2026-04-15T10:00:10Z"
}
```

**Evento Kafka Produzido:** `intention.translated`

---

### Passo 3: Consenso entre Especialistas

**Evento Kafka:** `intention.translated`

**Payload Recebido:** (Output do STE acima)

**Processamento Consensus Engine:**
```python
# services/consensus-engine/src/consensus.py

class ConsensusEngine:
    async def reach_consensus(self, intention: dict) -> dict:
        """
        Coordena consenso entre especialistas.
        """
        specialists = [
            "text_analysis_specialist",
            "code_analysis_specialist",
            "data_analysis_specialist",
            "security_specialist"
        ]
        
        # Obter opiniões de cada especialista
        specialist_opinions = []
        for specialist in specialists:
            opinion = await self._get_specialist_opinion(specialist, intention)
            specialist_opinions.append(opinion)
        
        # Analisar convergências e divergências
        convergence_analysis = await self._analyze_convergence(specialist_opinions)
        
        # Gerar plano consensual
        consensus_plan = {
            "consensus_id": f"cons_{intention['id']}",
            "intention_id": intention['id'],
            "specialists_involved": specialists,
            "convergence_score": convergence_analysis.get('score', 0.0),
            "agreed_upon_aspects": convergence_analysis.get('converged', []),
            "divergent_aspects": convergence_analysis.get('diverged', []),
            "resolution_strategy": await self._resolve_divergences(convergence_analysis),
            "proposed_plan": await self._generate_proposed_plan(intention, convergence_analysis),
            "confidence_level": convergence_analysis.get('confidence', 0.5),
            "consensus_reached_at": datetime.utcnow().isoformat()
        }
        
        return consensus_plan
```

**Output Consensus Engine:**
```json
{
  "consensus_id": "cons_fmt_int_001",
  "intention_id": "fmt_int_001",
  "specialists_involved": [
    "text_analysis_specialist",
    "code_analysis_specialist",
    "data_analysis_specialist",
    "security_specialist"
  ],
  "convergence_score": 0.92,
  "agreed_upon_aspects": [
    {
      "aspect": "architecture_type",
      "value": "microservices",
      "agreement_level": 1.0,
      "specialists": ["text_analysis_specialist", "code_analysis_specialist", "security_specialist"]
    },
    {
      "aspect": "primary_database",
      "value": "PostgreSQL",
      "agreement_level": 0.9,
      "specialists": ["data_analysis_specialist", "code_analysis_specialist"]
    },
    {
      "aspect": "frontend_framework",
      "value": "React/React Native",
      "agreement_level": 0.85,
      "specialists": ["text_analysis_specialist", "code_analysis_specialist"]
    },
    {
      "aspect": "backend_framework",
      "value": "FastAPI",
      "agreement_level": 0.95,
      "specialists": ["code_analysis_specialist", "security_specialist"]
    }
  ],
  "divergent_aspects": [
    {
      "aspect": "caching_strategy",
      "alternatives": [
        {"value": "Redis", "proponents": ["code_analysis_specialist", "data_analysis_specialist"]},
        {"value": "Memcached", "proponents": ["text_analysis_specialist"]}
      ],
      "resolution": "Redis (chosen for feature set and community support)"
    },
    {
      "aspect": "message_queue",
      "alternatives": [
        {"value": "Kafka", "proponents": ["code_analysis_specialist", "security_specialist"]},
        {"value": "RabbitMQ", "proponents": ["data_analysis_specialist"]}
      ],
      "resolution": "Kafka (chosen for scalability and event-driven architecture)"
    }
  ],
  "resolution_strategy": {
    "strategy": "weighted_voting",
    "weights": {
      "code_analysis_specialist": 0.35,
      "security_specialist": 0.25,
      "data_analysis_specialist": 0.25,
      "text_analysis_specialist": 0.15
    }
  },
  "proposed_plan": {
    "architecture": {
      "type": "microservices",
      "services": [
        "user-service",
        "restaurant-service",
        "order-service",
        "payment-service",
        "delivery-service",
        "notification-service"
      ],
      "communication": "event-driven via Kafka"
    },
    "tech_stack": {
      "backend": {
        "framework": "FastAPI",
        "language": "Python 3.12+",
        "database": "PostgreSQL",
        "cache": "Redis",
        "message_queue": "Kafka"
      },
      "frontend": {
        "mobile": "React Native",
        "web": "React",
        "admin_panel": "React"
      },
      "infrastructure": {
        "containerization": "Docker",
        "orchestration": "Kubernetes",
        "ci_cd": "GitHub Actions",
        "cloud": "AWS/GCP"
      }
    },
    "data_layer": {
      "relational": "PostgreSQL (users, restaurants, orders)",
      "document": "MongoDB (notifications, logs)",
      "graph": "Neo4j (recommendations, social features)",
      "cache": "Redis (sessions, rate limiting)"
    },
    "security": {
      "authentication": "JWT with refresh tokens",
      "authorization": "RBAC",
      "payment_compliance": "PCI-DSS",
      "data_encryption": "TLS 1.3, AES-256"
    }
  },
  "confidence_level": 0.89,
  "consensus_reached_at": "2026-04-15T10:01:30Z"
}
```

**Evento Kafka Produzido:** `consensus.reached`

---

### Passo 4: Orquestração - Requirements Engineering

**Evento Kafka:** `consensus.reached`

**Payload Recebido:** (Output do Consensus Engine acima)

**Orchestrator Dynamic coordena:** Requirements Engineering System

**Evento Kafka Produzido:** `requirements.needed`

**Payload:**
```json
{
  "request_id": "req_req_fmt_int_001",
  "intention_id": "fmt_int_001",
  "consensus_id": "cons_fmt_int_001",
  "consensus_plan": {
    "architecture": {
      "type": "microservices",
      "services": [
        "user-service",
        "restaurant-service",
        "order-service",
        "payment-service",
        "delivery-service",
        "notification-service"
      ],
      "communication": "event-driven via Kafka"
    },
    "tech_stack": {
      "backend": {
        "framework": "FastAPI",
        "language": "Python 3.12+",
        "database": "PostgreSQL",
        "cache": "Redis",
        "message_queue": "Kafka"
      },
      "frontend": {
        "mobile": "React Native",
        "web": "React",
        "admin_panel": "React"
      }
    }
  },
  "context": {
    "target_market": "Brazil",
    "budget": "medium",
    "timeline": "3 months",
    "team_size": "small"
  },
  "requested_at": "2026-04-15T10:02:00Z"
}
```

**Requirements Engineering System processa:**

**Componente 1: Requirements Engineer**
```python
# services/requirements-engine/src/requirements_engineer.py

class RequirementsEngineer:
    async def engineer_requirements(self, request: dict) -> dict:
        """
        Engenharia de requisitos completa.
        """
        intention_id = request.get('intention_id')
        consensus_plan = request.get('consensus_plan')
        context = request.get('context')
        
        # Extrair requisitos funcionais
        functional_reqs = await self._extract_functional_requirements(
            consensus_plan, context
        )
        
        # Extrair requisitos não funcionais
        non_functional_reqs = await self._extract_non_functional_requirements(
            consensus_plan, context
        )
        
        # Definir user stories
        user_stories = await self._generate_user_stories(
            functional_reqs, context
        )
        
        # Definir acceptance criteria
        acceptance_criteria = await self._generate_acceptance_criteria(
            user_stories
        )
        
        # Definir data models
        data_models = await self._design_data_models(
            consensus_plan, functional_reqs
        )
        
        # Definir API design
        api_design = await self._design_api(
            functional_reqs, consensus_plan
        )
        
        # Definir UI/UX wireframes
        ui_ux_design = await self._design_ui_ux(
            user_stories, context
        )
        
        return {
            "requirements_id": f"req_{intention_id}",
            "intention_id": intention_id,
            "functional_requirements": functional_reqs,
            "non_functional_requirements": non_functional_reqs,
            "user_stories": user_stories,
            "acceptance_criteria": acceptance_criteria,
            "data_models": data_models,
            "api_design": api_design,
            "ui_ux_design": ui_ux_design,
            "engineered_at": datetime.utcnow().isoformat()
        }
```

**Output Requirements Engineering System:**
```json
{
  "requirements_id": "req_fmt_int_001",
  "intention_id": "fmt_int_001",
  "functional_requirements": [
    {
      "id": "FR_001",
      "title": "User Registration and Authentication",
      "description": "Customers must be able to register, login, and manage their profiles",
      "priority": "high",
      "user_stories": ["US_001", "US_002"],
      "acceptance_criteria": ["AC_001", "AC_002"]
    },
    {
      "id": "FR_002",
      "title": "Restaurant Browsing and Search",
      "description": "Customers must be able to browse restaurants, filter by cuisine, location, rating",
      "priority": "high",
      "user_stories": ["US_003", "US_004"],
      "acceptance_criteria": ["AC_003", "AC_004"]
    },
    {
      "id": "FR_003",
      "title": "Menu Viewing and Item Selection",
      "description": "Customers must be able to view restaurant menus and select items",
      "priority": "high",
      "user_stories": ["US_005", "US_006"],
      "acceptance_criteria": ["AC_005", "AC_006"]
    },
    {
      "id": "FR_004",
      "title": "Order Placement and Payment",
      "description": "Customers must be able to place orders and pay via multiple methods",
      "priority": "critical",
      "user_stories": ["US_007", "US_008"],
      "acceptance_criteria": ["AC_007", "AC_008"]
    },
    {
      "id": "FR_005",
      "title": "Real-time Order Tracking",
      "description": "Customers must be able to track their orders in real-time",
      "priority": "high",
      "user_stories": ["US_009"],
      "acceptance_criteria": ["AC_009"]
    },
    {
      "id": "FR_006",
      "title": "Restaurant Management Interface",
      "description": "Restaurant owners must be able to manage their restaurants and menus",
      "priority": "high",
      "user_stories": ["US_010", "US_011"],
      "acceptance_criteria": ["AC_010", "AC_011"]
    },
    {
      "id": "FR_007",
      "title": "Delivery Person Interface",
      "description": "Delivery persons must be able to accept and deliver orders",
      "priority": "high",
      "user_stories": ["US_012", "US_013"],
      "acceptance_criteria": ["AC_012", "AC_013"]
    },
    {
      "id": "FR_008",
      "title": "Admin Dashboard",
      "description": "Admins must be able to monitor and manage the platform",
      "priority": "medium",
      "user_stories": ["US_014", "US_015"],
      "acceptance_criteria": ["AC_014", "AC_015"]
    }
  ],
  "non_functional_requirements": [
    {
      "id": "NFR_001",
      "category": "performance",
      "requirement": "API response time <200ms for 95th percentile",
      "priority": "high",
      "metrics": ["p95_response_time", "p99_response_time"]
    },
    {
      "id": "NFR_002",
      "category": "scalability",
      "requirement": "Support 10,000+ concurrent users",
      "priority": "critical",
      "metrics": ["concurrent_users", "throughput_rps"]
    },
    {
      "id": "NFR_003",
      "category": "availability",
      "requirement": "99.9% uptime SLA",
      "priority": "critical",
      "metrics": ["uptime_percentage", "downtime_per_month"]
    },
    {
      "id": "NFR_004",
      "category": "security",
      "requirement": "PCI-DSS compliance for payment processing",
      "priority": "critical",
      "metrics": ["security_scan_results", "penetration_test_results"]
    },
    {
      "id": "NFR_005",
      "category": "usability",
      "requirement": "Mobile-first responsive design",
      "priority": "high",
      "metrics": ["mobile_screen_coverage", "user_satisfaction_score"]
    }
  ],
  "user_stories": [
    {
      "id": "US_001",
      "title": "User Registration",
      "as_a": "customer",
      "i_want_to": "register with email and password",
      "so_that": "I can start ordering food",
      "acceptance_criteria": ["AC_001"],
      "priority": "high"
    },
    {
      "id": "US_002",
      "title": "User Login",
      "as_a": "customer",
      "i_want_to": "login with my credentials",
      "so_that": "I can access my account",
      "acceptance_criteria": ["AC_002"],
      "priority": "high"
    },
    {
      "id": "US_003",
      "title": "Browse Restaurants",
      "as_a": "customer",
      "i_want_to": "browse restaurants near me",
      "so_that": "I can find places to order from",
      "acceptance_criteria": ["AC_003"],
      "priority": "high"
    },
    {
      "id": "US_004",
      "title": "Filter Restaurants",
      "as_a": "customer",
      "i_want_to": "filter restaurants by cuisine and rating",
      "so_that": "I can find restaurants that match my preferences",
      "acceptance_criteria": ["AC_004"],
      "priority": "medium"
    },
    {
      "id": "US_005",
      "title": "View Menu",
      "as_a": "customer",
      "i_want_to": "view a restaurant's menu",
      "so_that": "I can see what items are available",
      "acceptance_criteria": ["AC_005"],
      "priority": "high"
    },
    {
      "id": "US_006",
      "title": "Add to Cart",
      "as_a": "customer",
      "i_want_to": "add items to my cart",
      "so_that": "I can build my order",
      "acceptance_criteria": ["AC_006"],
      "priority": "high"
    },
    {
      "id": "US_007",
      "title": "Place Order",
      "as_a": "customer",
      "i_want_to": "place my order and pay",
      "so_that": "I can receive my food",
      "acceptance_criteria": ["AC_007"],
      "priority": "critical"
    },
    {
      "id": "US_008",
      "title": "Track Order",
      "as_a": "customer",
      "i_want_to": "track my order in real-time",
      "so_that": "I know when my food will arrive",
      "acceptance_criteria": ["AC_009"],
      "priority": "high"
    }
  ],
  "acceptance_criteria": [
    {
      "id": "AC_001",
      "user_story_id": "US_001",
      "criteria": [
        "User can register with valid email and password",
        "Password must be at least 8 characters",
        "Email validation is performed",
        "User receives confirmation email"
      ],
      "given_when_then": [
        "Given I am on the registration page",
        "When I enter a valid email and password",
        "Then I should be registered and redirected to login"
      ]
    },
    {
      "id": "AC_002",
      "user_story_id": "US_002",
      "criteria": [
        "User can login with valid credentials",
        "Invalid credentials show error message",
        "Successful login redirects to home page",
        "JWT token is issued and stored"
      ],
      "given_when_then": [
        "Given I am registered",
        "When I enter my email and password",
        "Then I should be logged in and see the home page"
      ]
    }
  ],
  "data_models": [
    {
      "name": "User",
      "fields": [
        {"name": "id", "type": "UUID", "primary_key": true},
        {"name": "email", "type": "VARCHAR(255)", "unique": true},
        {"name": "password_hash", "type": "VARCHAR(255)"},
        {"name": "name", "type": "VARCHAR(100)"},
        {"name": "phone", "type": "VARCHAR(20)"},
        {"name": "role", "type": "ENUM('customer', 'restaurant_owner', 'delivery_person', 'admin')"},
        {"name": "created_at", "type": "TIMESTAMP"},
        {"name": "updated_at", "type": "TIMESTAMP"}
      ],
      "indexes": [
        {"fields": ["email"], "unique": true},
        {"fields": ["phone"]}
      ]
    },
    {
      "name": "Restaurant",
      "fields": [
        {"name": "id", "type": "UUID", "primary_key": true},
        {"name": "owner_id", "type": "UUID", "foreign_key": "User.id"},
        {"name": "name", "type": "VARCHAR(100)"},
        {"name": "cuisine_type", "type": "VARCHAR(50)"},
        {"name": "address", "type": "TEXT"},
        {"name": "latitude", "type": "DECIMAL(10, 8)"},
        {"name": "longitude", "type": "DECIMAL(11, 8)"},
        {"name": "rating", "type": "DECIMAL(3, 2)"},
        {"name": "delivery_time_minutes", "type": "INTEGER"},
        {"name": "is_active", "type": "BOOLEAN"},
        {"name": "created_at", "type": "TIMESTAMP"},
        {"name": "updated_at", "type": "TIMESTAMP"}
      ],
      "indexes": [
        {"fields": ["owner_id"]},
        {"fields": ["cuisine_type"]},
        {"fields": ["latitude", "longitude"], "type": "spatial"}
      ]
    },
    {
      "name": "Order",
      "fields": [
        {"name": "id", "type": "UUID", "primary_key": true},
        {"name": "customer_id", "type": "UUID", "foreign_key": "User.id"},
        {"name": "restaurant_id", "type": "UUID", "foreign_key": "Restaurant.id"},
        {"name": "delivery_person_id", "type": "UUID", "foreign_key": "User.id", "nullable": true},
        {"name": "status", "type": "ENUM('pending', 'confirmed', 'preparing', 'ready', 'pickup', 'on_the_way', 'delivered', 'cancelled')"},
        {"name": "total_amount_brl", "type": "DECIMAL(10, 2)"},
        {"name": "delivery_fee_brl", "type": "DECIMAL(10, 2)"},
        {"name": "delivery_address", "type": "TEXT"},
        {"name": "delivery_latitude", "type": "DECIMAL(10, 8)"},
        {"name": "delivery_longitude", "type": "DECIMAL(11, 8)"},
        {"name": "estimated_delivery_time", "type": "TIMESTAMP"},
        {"name": "created_at", "type": "TIMESTAMP"},
        {"name": "updated_at", "type": "TIMESTAMP"}
      ],
      "indexes": [
        {"fields": ["customer_id"]},
        {"fields": ["restaurant_id"]},
        {"fields": ["delivery_person_id"]},
        {"fields": ["status"]},
        {"fields": ["created_at"]}
      ]
    }
  ],
  "api_design": {
    "base_url": "https://api.delivery-app.com/v1",
    "version": "1.0.0",
    "authentication": "JWT Bearer token",
    "endpoints": [
      {
        "path": "/auth/register",
        "method": "POST",
        "description": "Register new user",
        "request_body": {
          "email": "string",
          "password": "string",
          "name": "string",
          "phone": "string",
          "role": "customer|restaurant_owner|delivery_person"
        },
        "response": {
          "id": "uuid",
          "email": "string",
          "name": "string",
          "created_at": "timestamp"
        },
        "status_codes": [201, 400, 409]
      },
      {
        "path": "/auth/login",
        "method": "POST",
        "description": "Login user",
        "request_body": {
          "email": "string",
          "password": "string"
        },
        "response": {
          "access_token": "string",
          "refresh_token": "string",
          "token_type": "Bearer",
          "expires_in": 3600
        },
        "status_codes": [200, 401]
      },
      {
        "path": "/restaurants",
        "method": "GET",
        "description": "List restaurants",
        "query_params": {
          "cuisine_type": "string",
          "min_rating": "decimal",
          "latitude": "decimal",
          "longitude": "decimal",
          "radius_km": "integer"
        },
        "response": {
          "restaurants": [
            {
              "id": "uuid",
              "name": "string",
              "cuisine_type": "string",
              "rating": "decimal",
              "delivery_time_minutes": "integer"
            }
          ]
        },
        "status_codes": [200]
      },
      {
        "path": "/orders",
        "method": "POST",
        "description": "Create order",
        "request_body": {
          "restaurant_id": "uuid",
          "items": [
            {
              "menu_item_id": "uuid",
              "quantity": "integer"
            }
          ],
          "delivery_address": "string",
          "delivery_latitude": "decimal",
          "delivery_longitude": "decimal",
          "payment_method": "pix|credit_card|cash"
        },
        "response": {
          "id": "uuid",
          "status": "pending",
          "total_amount_brl": "decimal",
          "estimated_delivery_time": "timestamp"
        },
        "status_codes": [201, 400, 402]
      },
      {
        "path": "/orders/{order_id}",
        "method": "GET",
        "description": "Get order details",
        "response": {
          "id": "uuid",
          "customer_id": "uuid",
          "restaurant_id": "uuid",
          "status": "string",
          "total_amount_brl": "decimal",
          "delivery_address": "string",
          "estimated_delivery_time": "timestamp",
          "delivery_person": {
            "id": "uuid",
            "name": "string",
            "phone": "string"
          }
        },
        "status_codes": [200, 404]
      }
    ]
  },
  "ui_ux_design": {
    "mobile_app": {
      "screens": [
        {
          "name": "Login",
          "components": [
            {"type": "input", "label": "Email", "input_type": "email"},
            {"type": "input", "label": "Password", "input_type": "password"},
            {"type": "button", "label": "Login"},
            {"type": "link", "label": "Forgot password?", "action": "navigate_to_reset_password"},
            {"type": "link", "label": "Create account", "action": "navigate_to_register"}
          ]
        },
        {
          "name": "Home",
          "components": [
            {"type": "search_bar", "placeholder": "Search restaurants"},
            {"type": "filter_button", "label": "Filter"},
            {"type": "restaurant_list", "items": "restaurants_from_api"}
          ]
        },
        {
          "name": "Restaurant Details",
          "components": [
            {"type": "image", "source": "restaurant_image"},
            {"type": "text", "content": "restaurant_name"},
            {"type": "rating", "value": "restaurant_rating"},
            {"type": "menu_list", "items": "menu_items"},
            {"type": "button", "label": "View Cart"}
          ]
        },
        {
          "name": "Cart",
          "components": [
            {"type": "cart_items", "items": "cart_items"},
            {"type": "total_amount", "value": "total"},
            {"type": "delivery_fee", "value": "fee"},
            {"type": "button", "label": "Checkout"}
          ]
        },
        {
          "name": "Order Tracking",
          "components": [
            {"type": "order_status", "value": "current_status"},
            {"type": "map", "markers": ["restaurant", "customer", "delivery_person"]},
            {"type": "progress_bar", "steps": ["confirmed", "preparing", "on_the_way", "delivered"]},
            {"type": "delivery_person_info", "name": "driver_name", "phone": "driver_phone"}
          ]
        }
      ]
    },
    "web_admin_panel": {
      "screens": [
        {
          "name": "Dashboard",
          "components": [
            {"type": "stats_card", "title": "Total Orders", "value": "order_count"},
            {"type": "stats_card", "title": "Active Users", "value": "user_count"},
            {"type": "stats_card", "title": "Revenue", "value": "revenue_brl"},
            {"type": "chart", "type": "line", "data": "orders_over_time"}
          ]
        },
        {
          "name": "Restaurant Management",
          "components": [
            {"type": "table", "columns": ["name", "cuisine", "rating", "status"], "data": "restaurants"},
            {"type": "button", "label": "Add Restaurant"},
            {"type": "button", "label": "Edit Restaurant"}
          ]
        }
      ]
    }
  },
  "engineered_at": "2026-04-15T10:05:00Z"
}
```

**Evento Kafka Produzido:** `requirements.generated`

---

### Passo 5: Orquestração - Architectural Planning

**Evento Kafka:** `requirements.generated`

**Payload Recebido:** (Output do Requirements Engineering System acima)

**Architectural Planning System processa:**

**Componente 1: RAG Engine (Knowledge Graph Integration)**
```python
# services/architectural-planning/src/rag_engine.py

class RAGEngine:
    async def search_architectural_knowledge(self, requirements: dict) -> dict:
        """
        Busca conhecimento arquitetural no Knowledge Graph.
        """
        # Extrair contexto dos requisitos
        domain = requirements.get('domain', 'unknown')
        tech_stack = requirements.get('api_design', {}).get('version', '1.0')
        scale_requirements = [
            nfr for nfr in requirements.get('non_functional_requirements', [])
            if nfr['category'] == 'scalability'
        ]
        
        # Buscar bounded contexts similares no Neo4j
        similar_contexts = await self._query_similar_contexts(domain, scale_requirements)
        
        # Buscar patterns de comunicação
        communication_patterns = await self._query_communication_patterns(domain)
        
        # Buscar best practices de arquitetura
        best_practices = await self._query_best_practices(domain, tech_stack)
        
        # Buscar patterns de error handling
        error_patterns = await self._query_error_patterns(domain)
        
        return {
            "search_results": {
                "similar_contexts": similar_contexts,
                "communication_patterns": communication_patterns,
                "best_practices": best_practices,
                "error_patterns": error_patterns
            },
            "knowledge_graph_queries": await self._get_queries_executed(),
            "confidence_scores": await self._calculate_confidence_scores(search_results)
        }
```

**Output RAG Engine:**
```json
{
  "search_results": {
    "similar_contexts": [
      {
        "context_id": "ctx_food_delivery_001",
        "domain": "food_delivery",
        "bounded_contexts": [
          {
            "name": "User Management",
            "services": ["user-service"],
            "responsibilities": ["authentication", "user_profiles", "permissions"],
            "success_rate": 0.92
          },
          {
            "name": "Restaurant Catalog",
            "services": ["restaurant-service"],
            "responsibilities": ["restaurant_listings", "menu_management", "reviews"],
            "success_rate": 0.89
          },
          {
            "name": "Order Management",
            "services": ["order-service", "payment-service"],
            "responsibilities": ["order_creation", "payment_processing", "order_status"],
            "success_rate": 0.94
          },
          {
            "name": "Delivery Management",
            "services": ["delivery-service"],
            "responsibilities": ["delivery_routing", "delivery_tracking", "delivery_person_management"],
            "success_rate": 0.87
          },
          {
            "name": "Notification System",
            "services": ["notification-service"],
            "responsibilities": ["push_notifications", "email_notifications", "sms_notifications"],
            "success_rate": 0.91
          }
        ],
        "communication_patterns": [
          {
            "pattern": "event_driven",
            "message": "Orders create events that trigger notifications and deliveries",
            "confidence": 0.95
          },
          {
            "pattern": "circuit_breaker",
            "message": "Payment service uses circuit breaker to handle failures",
            "confidence": 0.88
          }
        ],
        "lessons_learned": [
          "Kafka is critical for event-driven architecture in food delivery",
          "Real-time tracking requires WebSocket connections",
          "Payment failures must be handled gracefully with retries",
          "GPS tracking needs exponential backoff for API rate limits"
        ]
      }
    ],
    "communication_patterns": [
      {
        "pattern_id": "pub_sub",
        "name": "Publish-Subscribe",
        "description": "Services publish events to topics, subscribers consume asynchronously",
        "use_case": "Order status updates sent to multiple subscribers",
        "implementation": "Kafka topics",
        "confidence": 0.94
      },
      {
        "pattern_id": "request_response",
        "name": "Request-Response",
        "description": "Synchronous HTTP calls between services",
        "use_case": "User service queries restaurant service for availability",
        "implementation": "HTTP REST with timeouts",
        "confidence": 0.89
      },
      {
        "pattern_id": "circuit_breaker",
        "name": "Circuit Breaker",
        "description": "Prevents cascading failures by failing fast",
        "use_case": "Payment service calls external payment gateway",
        "implementation": "Hystrix or resilience4j",
        "confidence": 0.91
      }
    ],
    "best_practices": [
      {
        "practice": "Bounded Contexts",
        "description": "Separate business domains into independent contexts",
        "application": "User, Restaurant, Order, Delivery, Notification contexts",
        "benefits": ["Decoupling", "Scalability", "Team autonomy"]
      },
      {
        "practice": "Event Sourcing",
        "description": "Store all state changes as events",
        "application": "Order events: created, confirmed, preparing, ready, on_the_way, delivered",
        "benefits": ["Audit trail", "Replayability", "Debugging"]
      },
      {
        "practice": "CQRS",
        "description": "Command Query Responsibility Segregation",
        "application": "Separate read/write models for orders and restaurants",
        "benefits": ["Performance", "Scalability", "Flexibility"]
      }
    ],
    "error_patterns": [
      {
        "pattern": "payment_failure",
        "frequency": 0.05,
        "handling_strategy": "Retry with exponential backoff, fallback to cash payment",
        "recovery_time_seconds": 30
      },
      {
        "pattern": "delivery_timeout",
        "frequency": 0.03,
        "handling_strategy": "Auto-assign new delivery person, notify customer",
        "recovery_time_seconds": 120
      },
      {
        "pattern": "gps_api_rate_limit",
        "frequency": 0.08,
        "handling_strategy": "Cache locations, use exponential backoff",
        "recovery_time_seconds": 60
      }
    ]
  },
  "knowledge_graph_queries": [
    "MATCH (ctx:BoundedContext) WHERE ctx.domain = 'food_delivery' RETURN ctx",
    "MATCH (p:CommunicationPattern) WHERE p.domain = 'food_delivery' RETURN p",
    "MATCH (bp:BestPractice) WHERE bp.applicable_to = 'food_delivery' RETURN bp",
    "MATCH (ep:ErrorPattern) WHERE ep.domain = 'food_delivery' RETURN ep"
  ],
  "confidence_scores": {
    "similar_contexts": 0.92,
    "communication_patterns": 0.89,
    "best_practices": 0.91,
    "error_patterns": 0.85,
    "overall": 0.89
  }
}
```

**Componente 2: Architect Designer**
```python
# services/architectural-planning/src/architect_designer.py

class ArchitectDesigner:
    async def design_architecture(self, requirements: dict, rag_results: dict) -> dict:
        """
        Desenha arquitetura baseada em requisitos e conhecimento.
        """
        # Analisar requisitos de escala
        scale_reqs = [
            nfr for nfr in requirements.get('non_functional_requirements', [])
            if nfr['category'] == 'scalability'
        ]
        
        # Selecionar bounded contexts
        bounded_contexts = await self._design_bounded_contexts(
            requirements, rag_results
        )
        
        # Definir comunicação entre contexts
        communication_patterns = await self._design_communication_patterns(
            bounded_contexts, rag_results
        )
        
        # Definir arquitetural decision records
        adrs = await self._generate_architectural_decision_records(
            bounded_contexts, communication_patterns
        )
        
        return {
            "architecture_id": f"arch_{requirements['requirements_id']}",
            "architecture_type": "microservices_event_driven",
            "bounded_contexts": bounded_contexts,
            "communication_patterns": communication_patterns,
            "architectural_decision_records": adrs,
            "designed_at": datetime.utcnow().isoformat()
        }
```

**Output Architect Designer:**
```json
{
  "architecture_id": "arch_req_fmt_int_001",
  "architecture_type": "microservices_event_driven",
  "bounded_contexts": [
    {
      "id": "bc_user_management",
      "name": "User Management",
      "responsibilities": [
        "User authentication",
        "User profiles",
        "Role-based access control",
        "User preferences"
      ],
      "services": [
        {
          "name": "user-service",
          "port": 8010,
          "language": "Python",
          "framework": "FastAPI",
          "database": "PostgreSQL (user_db)",
          "cache": "Redis (user_sessions)",
          "endpoints": [
            "/auth/register",
            "/auth/login",
            "/auth/refresh",
            "/users/me",
            "/users/{id}"
          ]
        }
      ],
      "kafka_topics_produced": ["users.created", "users.updated", "users.deleted"],
      "kafka_topics_consumed": [],
      "api_dependencies": [],
      "data_models": ["User", "Role", "Permission"]
    },
    {
      "id": "bc_restaurant_catalog",
      "name": "Restaurant Catalog",
      "responsibilities": [
        "Restaurant listings",
        "Menu management",
        "Reviews and ratings",
        "Search and filtering"
      ],
      "services": [
        {
          "name": "restaurant-service",
          "port": 8011,
          "language": "Python",
          "framework": "FastAPI",
          "database": "PostgreSQL (restaurant_db)",
          "cache": "Redis (restaurant_listings)",
          "endpoints": [
            "/restaurants",
            "/restaurants/{id}",
            "/restaurants/{id}/menu",
            "/restaurants/{id}/reviews"
          ]
        }
      ],
      "kafka_topics_produced": ["restaurants.created", "restaurants.updated", "restaurants.deleted"],
      "kafka_topics_consumed": ["users.created"],
      "api_dependencies": ["user-service"],
      "data_models": ["Restaurant", "MenuItem", "Review", "Cuisine"]
    },
    {
      "id": "bc_order_management",
      "name": "Order Management",
      "responsibilities": [
        "Order creation",
        "Order status updates",
        "Order history",
        "Cart management"
      ],
      "services": [
        {
          "name": "order-service",
          "port": 8012,
          "language": "Python",
          "framework": "FastAPI",
          "database": "PostgreSQL (order_db)",
          "cache": "Redis (order_status)",
          "endpoints": [
            "/orders",
            "/orders/{id}",
            "/orders/{id}/items",
            "/carts"
          ]
        }
      ],
      "kafka_topics_produced": ["orders.created", "orders.updated", "orders.status.changed"],
      "kafka_topics_consumed": ["payments.completed", "payments.failed", "restaurants.updated"],
      "api_dependencies": ["user-service", "restaurant-service"],
      "data_models": ["Order", "OrderItem", "Cart"]
    },
    {
      "id": "bc_payment_processing",
      "name": "Payment Processing",
      "responsibilities": [
        "Payment processing",
        "Payment methods",
        "Transaction history",
        "Refunds"
      ],
      "services": [
        {
          "name": "payment-service",
          "port": 8013,
          "language": "Python",
          "framework": "FastAPI",
          "database": "PostgreSQL (payment_db)",
          "cache": "Redis (payment_status)",
          "endpoints": [
            "/payments",
            "/payments/{id}",
            "/payments/methods",
            "/payments/refunds"
          ]
        }
      ],
      "kafka_topics_produced": ["payments.completed", "payments.failed", "payments.refunded"],
      "kafka_topics_consumed": ["orders.created"],
      "api_dependencies": ["user-service"],
      "data_models": ["Payment", "PaymentMethod", "Transaction"]
    },
    {
      "id": "bc_delivery_management",
      "name": "Delivery Management",
      "responsibilities": [
        "Delivery person management",
        "Delivery routing",
        "Real-time tracking",
        "Delivery status updates"
      ],
      "services": [
        {
          "name": "delivery-service",
          "port": 8014,
          "language": "Python",
          "framework": "FastAPI",
          "database": "PostgreSQL (delivery_db)",
          "cache": "Redis (delivery_locations)",
          "external_apis": ["Google Maps API"],
          "endpoints": [
            "/deliveries",
            "/deliveries/{id}",
            "/deliveries/{id}/track",
            "/delivery-persons",
            "/delivery-persons/{id}/status"
          ]
        }
      ],
      "kafka_topics_produced": ["deliveries.assigned", "deliveries.status.changed", "deliveries.location.updated"],
      "kafka_topics_consumed": ["orders.status.changed", "orders.created"],
      "api_dependencies": ["user-service", "order-service"],
      "data_models": ["Delivery", "DeliveryPerson", "DeliveryRoute"]
    },
    {
      "id": "bc_notification_system",
      "name": "Notification System",
      "responsibilities": [
        "Push notifications",
        "Email notifications",
        "SMS notifications",
        "Notification templates"
      ],
      "services": [
        {
          "name": "notification-service",
          "port": 8015,
          "language": "Python",
          "framework": "FastAPI",
          "database": "MongoDB (notifications)",
          "cache": "Redis (notification_queue)",
          "external_services": ["Firebase", "AWS SES", "Twilio"],
          "endpoints": [
            "/notifications",
            "/notifications/templates",
            "/notifications/send"
          ]
        }
      ],
      "kafka_topics_produced": ["notifications.sent"],
      "kafka_topics_consumed": ["orders.status.changed", "deliveries.status.changed", "users.created"],
      "api_dependencies": [],
      "data_models": ["Notification", "NotificationTemplate", "NotificationLog"]
    }
  ],
  "communication_patterns": [
    {
      "pattern_id": "cp_001",
      "pattern_type": "event_driven",
      "name": "Order Status Events",
      "description": "Order service publishes status change events, multiple services subscribe",
      "publisher": "order-service",
      "subscribers": ["delivery-service", "notification-service"],
      "kafka_topic": "orders.status.changed",
      "event_schema": {
        "order_id": "uuid",
        "status": "enum(pending|confirmed|preparing|ready|pickup|on_the_way|delivered|cancelled)",
        "timestamp": "timestamp",
        "metadata": "object"
      },
      "reliability": "at_least_once",
      "retry_policy": "exponential_backoff_5_retries",
      "dead_letter_queue": true
    },
    {
      "pattern_id": "cp_002",
      "pattern_type": "synchronous",
      "name": "User Authentication Validation",
      "description": "Services validate JWT tokens with user-service",
      "consumer": "all_services",
      "provider": "user-service",
      "endpoint": "/auth/validate",
      "method": "POST",
      "timeout_ms": 500,
      "circuit_breaker": true,
      "fallback": "cache_validation"
    },
    {
      "pattern_id": "cp_003",
      "pattern_type": "event_driven",
      "name": "Payment Completion Events",
      "description": "Payment service publishes completion events",
      "publisher": "payment-service",
      "subscribers": ["order-service", "notification-service"],
      "kafka_topic": "payments.completed",
      "event_schema": {
        "payment_id": "uuid",
        "order_id": "uuid",
        "amount_brl": "decimal",
        "status": "enum(success|failed)",
        "timestamp": "timestamp"
      },
      "reliability": "exactly_once",
      "retry_policy": "exponential_backoff_3_retries"
    }
  ],
  "architectural_decision_records": [
    {
      "adr_id": "ADR_001",
      "title": "Use Microservices Architecture",
      "status": "Accepted",
      "date": "2026-04-15",
      "context": "System requires high scalability, independent deployment, and team autonomy",
      "decision": "Adopt microservices architecture with bounded contexts",
      "consequences": [
        "Positive: Independent scaling of services",
        "Positive: Faster deployment cycles",
        "Negative: Increased operational complexity",
        "Negative: Network latency between services"
      ]
    },
    {
      "adr_id": "ADR_002",
      "title": "Use Kafka for Event-Driven Communication",
      "status": "Accepted",
      "date": "2026-04-15",
      "context": "Order processing requires asynchronous communication and event sourcing",
      "decision": "Use Apache Kafka as the central message broker",
      "consequences": [
        "Positive: Loose coupling between services",
        "Positive: Event replay capability",
        "Positive: Fault tolerance with replication",
        "Negative: Complexity of event ordering"
      ]
    },
    {
      "adr_id": "ADR_003",
      "title": "Use PostgreSQL for Relational Data",
      "status": "Accepted",
      "date": "2026-04-15",
      "context": "ACID transactions required for orders and payments",
      "decision": "Use PostgreSQL as primary relational database",
      "consequences": [
        "Positive: Strong consistency",
        "Positive: ACID transactions",
        "Positive: Mature ecosystem",
        "Negative: Vertical scaling limit"
      ]
    },
    {
      "adr_id": "ADR_004",
      "title": "Use Redis for Caching",
      "status": "Accepted",
      "date": "2026-04-15",
      "context": "High read latency required for restaurant listings and user sessions",
      "decision": "Use Redis for caching frequently accessed data",
      "consequences": [
        "Positive: Sub-millisecond read latency",
        "Positive: Session management",
        "Negative: Limited memory size",
        "Negative: Data persistence requires configuration"
      ]
    },
    {
      "adr_id": "ADR_005",
      "title": "Use MongoDB for Notifications",
      "status": "Accepted",
      "date": "2026-04-15",
      "context": "Notifications are document-based with variable schema",
      "decision": "Use MongoDB for notification storage",
      "consequences": [
        "Positive: Flexible schema",
        "Positive: Horizontal scaling",
        "Negative: No ACID guarantees",
        "Negative: Query complexity for joins"
      ]
    }
  ],
  "designed_at": "2026-04-15T10:10:00Z"
}
```

**Evento Kafka Produzido:** `architectural.plan`

---

### Passo 6: Orquestração - Agentic Delegation (Planejamento e Atribuição)

**Evento Kafka:** `architectural.plan`

**Payload Recebido:** (Output do Architect Designer acima)

**Agentic Delegation System processa:**

**Componente 1: Decomposer**
```python
# services/agentic-delegation/src/decomposer.py

class Decomposer:
    async def decompose_plan(self, architecture: dict, requirements: dict) -> dict:
        """
        Decompõe plano arquitetural em tarefas executáveis.
        """
        decomposition = {
            "decomposition_id": f"decomp_{architecture['architecture_id']}",
            "architecture_id": architecture['architecture_id'],
            "total_tasks": 0,
            "tasks": []
        }
        
        # Para cada bounded context, decompor em tarefas
        for bounded_context in architecture.get('bounded_contexts', []):
            tasks = await self._decompose_bounded_context(bounded_context, requirements)
            decomposition['tasks'].extend(tasks)
        
        # Adicionar tarefas de infraestrutura
        infrastructure_tasks = await self._decompose_infrastructure(architecture)
        decomposition['tasks'].extend(infrastructure_tasks)
        
        # Adicionar tarefas de deployment
        deployment_tasks = await self._decompose_deployment(architecture)
        decomposition['tasks'].extend(deployment_tasks)
        
        decomposition['total_tasks'] = len(decomposition['tasks'])
        decomposition['decomposed_at'] = datetime.utcnow().isoformat()
        
        return decomposition
    
    async def _decompose_bounded_context(self, context: dict, requirements: dict) -> List[dict]:
        """
        Decompõe um bounded context em tarefas.
        """
        tasks = []
        context_name = context['name']
        context_id = context['id']
        
        for service in context.get('services', []):
            service_name = service['name']
            
            # Tarefa 1: Setup do projeto
            tasks.append({
                "task_id": f"task_{context_id}_{service_name}_setup",
                "context_id": context_id,
                "service": service_name,
                "type": "setup",
                "title": f"Setup {service_name} project",
                "description": f"Initialize {service_name} project structure with {service['framework']}",
                "dependencies": [],
                "estimated_time_minutes": 15,
                "priority": "high",
                "skills_required": ["fastapi", "python", "project_structure"],
                "output_artifacts": [
                    f"{service_name}/",
                    f"{service_name}/pyproject.toml",
                    f"{service_name}/Dockerfile"
                ]
            })
            
            # Tarefa 2: Data Models
            tasks.append({
                "task_id": f"task_{context_id}_{service_name}_models",
                "context_id": context_id,
                "service": service_name,
                "type": "data_modeling",
                "title": f"Define data models for {service_name}",
                "description": f"Define Pydantic models and SQLAlchemy schemas for {service_name}",
                "dependencies": [f"task_{context_id}_{service_name}_setup"],
                "estimated_time_minutes": 30,
                "priority": "high",
                "skills_required": ["pydantic", "sqlalchemy", "data_modeling"],
                "output_artifacts": [
                    f"{service_name}/src/models/",
                    f"{service_name}/src/schemas/"
                ]
            })
            
            # Tarefa 3: API Endpoints
            tasks.append({
                "task_id": f"task_{context_id}_{service_name}_api",
                "context_id": context_id,
                "service": service_name,
                "type": "api_development",
                "title": f"Implement API endpoints for {service_name}",
                "description": f"Implement all REST API endpoints defined in requirements",
                "dependencies": [f"task_{context_id}_{service_name}_models"],
                "estimated_time_minutes": 60,
                "priority": "high",
                "skills_required": ["fastapi", "rest_api", "async_python"],
                "output_artifacts": [
                    f"{service_name}/src/api/",
                    f"{service_name}/src/routes/"
                ]
            })
            
            # Tarefa 4: Kafka Integration
            tasks.append({
                "task_id": f"task_{context_id}_{service_name}_kafka",
                "context_id": context_id,
                "service": service_name,
                "type": "kafka_integration",
                "title": f"Integrate Kafka with {service_name}",
                "description": f"Implement Kafka producers and consumers for {service_name}",
                "dependencies": [f"task_{context_id}_{service_name}_api"],
                "estimated_time_minutes": 45,
                "priority": "high",
                "skills_required": ["kafka", "aiokafka", "async_python"],
                "output_artifacts": [
                    f"{service_name}/src/kafka/"
                ]
            })
            
            # Tarefa 5: Database Migrations
            tasks.append({
                "task_id": f"task_{context_id}_{service_name}_migrations",
                "context_id": context_id,
                "service": service_name,
                "type": "database",
                "title": f"Create database migrations for {service_name}",
                "description": f"Create Alembic migrations for {service['database']}",
                "dependencies": [f"task_{context_id}_{service_name}_models"],
                "estimated_time_minutes": 20,
                "priority": "high",
                "skills_required": ["alembic", "postgresql", "sql"],
                "output_artifacts": [
                    f"{service_name}/alembic/"
                ]
            })
            
            # Tarefa 6: Docker Configuration
            tasks.append({
                "task_id": f"task_{context_id}_{service_name}_docker",
                "context_id": context_id,
                "service": service_name,
                "type": "devops",
                "title": f"Create Docker configuration for {service_name}",
                "description": f"Create Dockerfile and docker-compose configuration for {service_name}",
                "dependencies": [f"task_{context_id}_{service_name}_setup"],
                "estimated_time_minutes": 15,
                "priority": "medium",
                "skills_required": ["docker", "docker_compose"],
                "output_artifacts": [
                    f"{service_name}/Dockerfile",
                    "docker-compose.yml"
                ]
            })
        
        return tasks
```

**Output Decomposer (Resumido):**
```json
{
  "decomposition_id": "decomp_arch_req_fmt_int_001",
  "architecture_id": "arch_req_fmt_int_001",
  "total_tasks": 42,
  "tasks": [
    {
      "task_id": "task_bc_user_management_user-service_setup",
      "context_id": "bc_user_management",
      "service": "user-service",
      "type": "setup",
      "title": "Setup user-service project",
      "description": "Initialize user-service project structure with FastAPI",
      "dependencies": [],
      "estimated_time_minutes": 15,
      "priority": "high",
      "skills_required": ["fastapi", "python", "project_structure"],
      "output_artifacts": [
        "user-service/",
        "user-service/pyproject.toml",
        "user-service/Dockerfile"
      ]
    },
    {
      "task_id": "task_bc_user_management_user-service_models",
      "context_id": "bc_user_management",
      "service": "user-service",
      "type": "data_modeling",
      "title": "Define data models for user-service",
      "description": "Define Pydantic models and SQLAlchemy schemas for user-service",
      "dependencies": ["task_bc_user_management_user-service_setup"],
      "estimated_time_minutes": 30,
      "priority": "high",
      "skills_required": ["pydantic", "sqlalchemy", "data_modeling"],
      "output_artifacts": [
        "user-service/src/models/",
        "user-service/src/schemas/"
      ]
    },
    {
      "task_id": "task_bc_user_management_user-service_api",
      "context_id": "bc_user_management",
      "service": "user-service",
      "type": "api_development",
      "title": "Implement API endpoints for user-service",
      "description": "Implement all REST API endpoints defined in requirements",
      "dependencies": ["task_bc_user_management_user-service_models"],
      "estimated_time_minutes": 60,
      "priority": "high",
      "skills_required": ["fastapi", "rest_api", "async_python"],
      "output_artifacts": [
        "user-service/src/api/",
        "user-service/src/routes/"
      ]
    },
    {
      "task_id": "task_bc_user_management_user-service_kafka",
      "context_id": "bc_user_management",
      "service": "user-service",
      "type": "kafka_integration",
      "title": "Integrate Kafka with user-service",
      "description": "Implement Kafka producers and consumers for user-service",
      "dependencies": ["task_bc_user_management_user-service_api"],
      "estimated_time_minutes": 45,
      "priority": "high",
      "skills_required": ["kafka", "aiokafka", "async_python"],
      "output_artifacts": [
        "user-service/src/kafka/"
      ]
    },
    {
      "task_id": "task_bc_restaurant_catalog_restaurant-service_setup",
      "context_id": "bc_restaurant_catalog",
      "service": "restaurant-service",
      "type": "setup",
      "title": "Setup restaurant-service project",
      "description": "Initialize restaurant-service project structure with FastAPI",
      "dependencies": [],
      "estimated_time_minutes": 15,
      "priority": "high",
      "skills_required": ["fastapi", "python", "project_structure"],
      "output_artifacts": [
        "restaurant-service/",
        "restaurant-service/pyproject.toml",
        "restaurant-service/Dockerfile"
      ]
    },
    {
      "task_id": "task_bc_order_management_order-service_setup",
      "context_id": "bc_order_management",
      "service": "order-service",
      "type": "setup",
      "title": "Setup order-service project",
      "description": "Initialize order-service project structure with FastAPI",
      "dependencies": [],
      "estimated_time_minutes": 15,
      "priority": "high",
      "skills_required": ["fastapi", "python", "project_structure"],
      "output_artifacts": [
        "order-service/",
        "order-service/pyproject.toml",
        "order-service/Dockerfile"
      ]
    },
    {
      "task_id": "task_bc_payment_processing_payment-service_setup",
      "context_id": "bc_payment_processing",
      "service": "payment-service",
      "type": "setup",
      "title": "Setup payment-service project",
      "description": "Initialize payment-service project structure with FastAPI",
      "dependencies": [],
      "estimated_time_minutes": 15,
      "priority": "high",
      "skills_required": ["fastapi", "python", "project_structure"],
      "output_artifacts": [
        "payment-service/",
        "payment-service/pyproject.toml",
        "payment-service/Dockerfile"
      ]
    },
    {
      "task_id": "task_bc_delivery_management_delivery-service_setup",
      "context_id": "bc_delivery_management",
      "service": "delivery-service",
      "type": "setup",
      "title": "Setup delivery-service project",
      "description": "Initialize delivery-service project structure with FastAPI",
      "dependencies": [],
      "estimated_time_minutes": 15,
      "priority": "high",
      "skills_required": ["fastapi", "python", "project_structure"],
      "output_artifacts": [
        "delivery-service/",
        "delivery-service/pyproject.toml",
        "delivery-service/Dockerfile"
      ]
    },
    {
      "task_id": "task_bc_notification_system_notification-service_setup",
      "context_id": "bc_notification_system",
      "service": "notification-service",
      "type": "setup",
      "title": "Setup notification-service project",
      "description": "Initialize notification-service project structure with FastAPI",
      "dependencies": [],
      "estimated_time_minutes": 15,
      "priority": "high",
      "skills_required": ["fastapi", "python", "project_structure"],
      "output_artifacts": [
        "notification-service/",
        "notification-service/pyproject.toml",
        "notification-service/Dockerfile"
      ]
    },
    {
      "task_id": "task_infrastructure_kubernetes_setup",
      "context_id": "infrastructure",
      "service": "kubernetes",
      "type": "infrastructure",
      "title": "Setup Kubernetes cluster",
      "description": "Create Kubernetes manifests for all services",
      "dependencies": [],
      "estimated_time_minutes": 60,
      "priority": "high",
      "skills_required": ["kubernetes", "helm", "yaml"],
      "output_artifacts": [
        "k8s/",
        "k8s/deployments/",
        "k8s/services/",
        "k8s/ingress/"
      ]
    },
    {
      "task_id": "task_infrastructure_ci_cd_pipeline",
      "context_id": "infrastructure",
      "service": "github_actions",
      "type": "ci_cd",
      "title": "Setup CI/CD pipeline",
      "description": "Create GitHub Actions workflow for CI/CD",
      "dependencies": [],
      "estimated_time_minutes": 45,
      "priority": "high",
      "skills_required": ["github_actions", "docker", "kubernetes"],
      "output_artifacts": [
        ".github/workflows/ci-cd.yml"
      ]
    }
  ],
  "decomposed_at": "2026-04-15T10:15:00Z"
}
```

**Evento Kafka Produzido:** `plan.decomposed`

**Componente 2: Task Dispatcher**
```python
# services/agentic-delegation/src/task_dispatcher.py

class TaskDispatcher:
    async def dispatch_tasks(self, decomposition: dict, available_agents: List[dict]) -> dict:
        """
        Atribui tarefas a agentes baseado em fitness.
        """
        assignments = {
            "dispatch_id": f"dispatch_{decomposition['decomposition_id']}",
            "decomposition_id": decomposition['decomposition_id'],
            "total_tasks": len(decomposition['tasks']),
            "assigned_tasks": 0,
            "unassigned_tasks": 0,
            "assignments": []
        }
        
        # Para cada tarefa, encontrar melhor agente
        for task in decomposition['tasks']:
            best_agent = await self._find_best_agent(task, available_agents)
            
            assignment = {
                "task_id": task['task_id'],
                "task": task,
                "agent_id": best_agent.get('id') if best_agent else None,
                "agent_name": best_agent.get('name') if best_agent else None,
                "fitness_score": best_agent.get('fitness', 0.0) if best_agent else 0.0,
                "assigned_at": datetime.utcnow().isoformat()
            }
            
            assignments['assignments'].append(assignment)
            
            if best_agent:
                assignments['assigned_tasks'] += 1
            else:
                assignments['unassigned_tasks'] += 1
        
        assignments['dispatched_at'] = datetime.utcnow().isoformat()
        
        return assignments
```

**Output Task Dispatcher:**
```json
{
  "dispatch_id": "dispatch_decomp_arch_req_fmt_int_001",
  "decomposition_id": "decomp_arch_req_fmt_int_001",
  "total_tasks": 42,
  "assigned_tasks": 42,
  "unassigned_tasks": 0,
  "assignments": [
    {
      "task_id": "task_bc_user_management_user-service_setup",
      "task": {
        "task_id": "task_bc_user_management_user-service_setup",
        "context_id": "bc_user_management",
        "service": "user-service",
        "type": "setup",
        "title": "Setup user-service project",
        "description": "Initialize user-service project structure with FastAPI",
        "dependencies": [],
        "estimated_time_minutes": 15,
        "priority": "high",
        "skills_required": ["fastapi", "python", "project_structure"],
        "output_artifacts": [
          "user-service/",
          "user-service/pyproject.toml",
          "user-service/Dockerfile"
        ]
      },
      "agent_id": "agent_code_forge_fastapi_001",
      "agent_name": "Code Forge FastAPI Specialist",
      "fitness_score": 0.95,
      "assigned_at": "2026-04-15T10:16:00Z"
    },
    {
      "task_id": "task_bc_user_management_user-service_models",
      "task": {
        "task_id": "task_bc_user_management_user-service_models",
        "context_id": "bc_user_management",
        "service": "user-service",
        "type": "data_modeling",
        "title": "Define data models for user-service",
        "description": "Define Pydantic models and SQLAlchemy schemas for user-service",
        "dependencies": ["task_bc_user_management_user-service_setup"],
        "estimated_time_minutes": 30,
        "priority": "high",
        "skills_required": ["pydantic", "sqlalchemy", "data_modeling"],
        "output_artifacts": [
          "user-service/src/models/",
          "user-service/src/schemas/"
        ]
      },
      "agent_id": "agent_code_forge_models_002",
      "agent_name": "Code Forge Data Model Specialist",
      "fitness_score": 0.92,
      "assigned_at": "2026-04-15T10:16:00Z"
    },
    {
      "task_id": "task_bc_user_management_user-service_api",
      "task": {
        "task_id": "task_bc_user_management_user-service_api",
        "context_id": "bc_user_management",
        "service": "user-service",
        "type": "api_development",
        "title": "Implement API endpoints for user-service",
        "description": "Implement all REST API endpoints defined in requirements",
        "dependencies": ["task_bc_user_management_user-service_models"],
        "estimated_time_minutes": 60,
        "priority": "high",
        "skills_required": ["fastapi", "rest_api", "async_python"],
        "output_artifacts": [
          "user-service/src/api/",
          "user-service/src/routes/"
        ]
      },
      "agent_id": "agent_code_forge_fastapi_001",
      "agent_name": "Code Forge FastAPI Specialist",
      "fitness_score": 0.93,
      "assigned_at": "2026-04-15T10:16:00Z"
    },
    {
      "task_id": "task_bc_restaurant_catalog_restaurant-service_setup",
      "task": {
        "task_id": "task_bc_restaurant_catalog_restaurant-service_setup",
        "context_id": "bc_restaurant_catalog",
        "service": "restaurant-service",
        "type": "setup",
        "title": "Setup restaurant-service project",
        "description": "Initialize restaurant-service project structure with FastAPI",
        "dependencies": [],
        "estimated_time_minutes": 15,
        "priority": "high",
        "skills_required": ["fastapi", "python", "project_structure"],
        "output_artifacts": [
          "restaurant-service/",
          "restaurant-service/pyproject.toml",
          "restaurant-service/Dockerfile"
        ]
      },
      "agent_id": "agent_code_forge_fastapi_001",
      "agent_name": "Code Forge FastAPI Specialist",
      "fitness_score": 0.95,
      "assigned_at": "2026-04-15T10:16:00Z"
    },
    {
      "task_id": "task_infrastructure_kubernetes_setup",
      "task": {
        "task_id": "task_infrastructure_kubernetes_setup",
        "context_id": "infrastructure",
        "service": "kubernetes",
        "type": "infrastructure",
        "title": "Setup Kubernetes cluster",
        "description": "Create Kubernetes manifests for all services",
        "dependencies": [],
        "estimated_time_minutes": 60,
        "priority": "high",
        "skills_required": ["kubernetes", "helm", "yaml"],
        "output_artifacts": [
          "k8s/",
          "k8s/deployments/",
          "k8s/services/",
          "k8s/ingress/"
        ]
      },
      "agent_id": "agent_iac_specialist_k8s_003",
      "agent_name": "IaC Kubernetes Specialist",
      "fitness_score": 0.94,
      "assigned_at": "2026-04-15T10:16:00Z"
    }
  ],
  "dispatched_at": "2026-04-15T10:16:00Z"
}
```

**Evento Kafka Produzido:** `agents.assigned`

---

### Passo 7: Orquestração - Code Forge (Geração de Código)

**Eventos Kafka Recebidos:** `plan.decomposed`, `agents.assigned`

**Code Forge System processa:**

**Componente 1: Template Selector (com RAG)**
```python
# services/code-forge/src/template_selector.py

class TemplateSelector:
    async def select_template(self, task: dict, task_assignments: dict) -> dict:
        """
        Seleciona melhor template baseado na tarefa e contexto RAG.
        """
        task_type = task.get('type')
        service = task.get('service')
        skills = task.get('skills_required', [])
        
        # Buscar templates similares no Knowledge Graph
        similar_templates = await self._query_similar_templates(
            task_type, service, skills
        )
        
        # Calcular fitness de cada template
        template_fitness = []
        for template in similar_templates:
            fitness = await self._calculate_fitness(
                template, task, task_assignments
            )
            template_fitness.append({
                "template": template,
                "fitness_score": fitness
            })
        
        # Ordenar por fitness e selecionar melhor
        template_fitness.sort(key=lambda x: x['fitness_score'], reverse=True)
        best_template = template_fitness[0] if template_fitness else None
        
        return {
            "task_id": task['task_id'],
            "selected_template": best_template.get('template') if best_template else None,
            "template_id": best_template.get('template', {}).get('id') if best_template else None,
            "fitness_score": best_template.get('fitness_score', 0.0) if best_template else 0.0,
            "alternatives": template_fitness[1:4],  # Top 3 alternativas
            "selected_at": datetime.utcnow().isoformat()
        }
```

**Output Template Selector:**
```json
{
  "task_id": "task_bc_user_management_user-service_setup",
  "selected_template": {
    "id": "tpl_fastapi_microservice_v2",
    "name": "FastAPI Microservice Starter",
    "description": "Complete FastAPI microservice template with best practices",
    "version": "2.0.0",
    "language": "python",
    "framework": "fastapi",
    "features": [
      "Pydantic for validation",
      "SQLAlchemy ORM",
      "Alembic migrations",
      "JWT authentication",
      "Kafka integration",
      "Redis caching",
      "OpenAPI documentation",
      "Docker support"
    ],
    "structure": {
      "directories": [
        "src/",
        "src/api/",
        "src/models/",
        "src/schemas/",
        "src/services/",
        "src/repositories/",
        "tests/",
        "alembic/"
      ],
      "files": [
        "pyproject.toml",
        "Dockerfile",
        "docker-compose.yml",
        ".env.example",
        "README.md"
      ]
    },
    "success_rate": 0.94,
    "usage_count": 150
  },
  "template_id": "tpl_fastapi_microservice_v2",
  "fitness_score": 0.95,
  "alternatives": [
    {
      "template": {
        "id": "tpl_fastapi_basic_v1",
        "name": "FastAPI Basic",
        "success_rate": 0.82
      },
      "fitness_score": 0.78
    }
  ],
  "selected_at": "2026-04-15T10:20:00Z"
}
```

**Componente 2: Code Composer (com RAG)**
```python
# services/code-forge/src/code_composer.py

class CodeComposer:
    async def compose_code(self, task: dict, template: dict, context: dict) -> dict:
        """
        Componha código usando template e RAG.
        """
        service_name = task.get('service')
        task_type = task.get('type')
        
        # Buscar código similar no Knowledge Graph
        similar_code = await self._query_similar_code(
            service_name, task_type, template
        )
        
        # Compor código
        generated_code = await self._generate_code(
            task, template, similar_code, context
        )
        
        # Validar código
        validation = await self._validate_code(generated_code)
        
        return {
            "task_id": task['task_id'],
            "service": service_name,
            "code": generated_code,
            "files": generated_code.get('files', {}),
            "validation": validation,
            "rag_context": similar_code,
            "composed_at": datetime.utcnow().isoformat()
        }
```

**Output Code Composer (Exemplo para user-service setup):**
```json
{
  "task_id": "task_bc_user_management_user-service_setup",
  "service": "user-service",
  "code": {
    "files": {
      "user-service/pyproject.toml": {
        "content": "[tool.poetry]\nname = \"user-service\"\nversion = \"0.1.0\"\ndescription = \"User Service for Delivery App\"\nauthors = [\"NHM Team\"]\n\n[tool.poetry.dependencies]\npython = \"^3.12\"\nfastapi = \"^0.109.0\"\npydantic = \"^2.5.0\"\nsqlalchemy = \"^2.0.0\"\nalembic = \"^1.13.0\"\naiokafka = \"^0.9.0\"\nredis = \"^5.0.0\"\npython-jose = \"^3.3.0\"\npasslib = \"^1.7.4\"\npython-multipart = \"^0.0.6\"\n\n[tool.poetry.dev-dependencies]\npytest = \"^7.4.0\"\npytest-asyncio = \"^0.23.0\"\nblack = \"^24.1.0\"\nruff = \"^0.1.0\"\n\n[build-system]\nrequires = [\"poetry-core\"]\nbuild-backend = \"poetry.core.masonry.api\""
      },
      "user-service/Dockerfile": {
        "content": "FROM python:3.12-slim\n\nWORKDIR /app\n\nCOPY pyproject.toml poetry.lock ./\nRUN pip install poetry && poetry install --no-dev\n\nCOPY . .\n\nCMD [\"poetry\", \"run\", \"uvicorn\", \"src.main:app\", \"--host\", \"0.0.0.0\", \"--port\", \"8010\"]"
      },
      "user-service/.env.example": {
        "content": "DATABASE_URL=postgresql://user:password@localhost:5432/user_db\nREDIS_URL=redis://localhost:6379/0\nKAFKA_BOOTSTRAP_SERVERS=localhost:9092\nSECRET_KEY=your-secret-key-here\nALGORITHM=HS256\nACCESS_TOKEN_EXPIRE_MINUTES=30"
      },
      "user-service/README.md": {
        "content": "# User Service\n\n## Description\nUser management service for Delivery App.\n\n## Features\n- User registration and authentication\n- JWT-based authentication\n- Role-based access control\n- Kafka integration for user events\n\n## Installation\n\n```bash\npoetry install\n```\n\n## Running\n\n```bash\npoetry run uvicorn src.main:app --reload\n```\n\n## API Documentation\nOpenAPI docs available at http://localhost:8010/docs"
      }
    }
  },
  "validation": {
    "syntax_valid": true,
    "lint_score": 1.0,
    "security_scan": {
      "score": 1.0,
      "issues": []
    }
  },
  "rag_context": {
    "similar_projects": [
      {
        "project": "auth-service-v3",
        "similarity": 0.89,
        "snippets": [
          "user-service/src/models/user.py",
          "user-service/src/schemas/user_schema.py"
        ]
      }
    ]
  },
  "composed_at": "2026-04-15T10:25:00Z"
}
```

**Evento Kafka Produzido:** `code.generated`

---

### Passo 8: Orquestração - Test Generation

**Evento Kafka Recebido:** `code.generated`

**Test Generation System processa:**

**Componente 1: Unit Test Generator**
```python
# services/test-generation/src/unit_test_generator.py

class UnitTestGenerator:
    async def generate_unit_tests(self, code: dict) -> dict:
        """
        Gera testes unitários para código gerado.
        """
        tests = {}
        
        for file_path, file_data in code.get('files', {}).items():
            if file_path.endswith('.py'):
                test_file = await self._generate_tests_for_file(file_path, file_data)
                tests[test_file['path']] = test_file['content']
        
        return {
            "code_id": code.get('task_id'),
            "tests": tests,
            "test_count": len(tests),
            "coverage_target": 0.8,
            "generated_at": datetime.utcnow().isoformat()
        }
```

**Output Unit Test Generator:**
```json
{
  "code_id": "task_bc_user_management_user-service_setup",
  "tests": {
    "user-service/tests/test_models.py": {
      "content": "import pytest\nfrom datetime import datetime\nfrom src.models.user import User, Role\n\n@pytest.fixture\ndef user_data():\n    return {\n        \"id\": \"test-uuid\",\n        \"email\": \"test@example.com\",\n        \"password_hash\": \"hashed_password\",\n        \"name\": \"Test User\",\n        \"phone\": \"+5511999999999\",\n        \"role\": Role.CUSTOMER,\n        \"created_at\": datetime.utcnow(),\n        \"updated_at\": datetime.utcnow()\n    }\n\ndef test_user_creation(user_data):\n    user = User(**user_data)\n    assert user.email == \"test@example.com\"\n    assert user.role == Role.CUSTOMER\n    assert user.is_active is True\n\ndef test_user_password_validation():\n    user = User(\n        email=\"test@example.com\",\n        password_hash=\"hashed_password\",\n        name=\"Test User\",\n        phone=\"+5511999999999\",\n        role=Role.CUSTOMER\n    )\n    assert user.verify_password(\"wrong_password\") is False\n    assert user.verify_password(\"correct_password\") is True"
    }
  },
  "test_count": 42,
  "coverage_target": 0.8,
  "generated_at": "2026-04-15T10:30:00Z"
}
```

**Componente 2: Integration Test Generator**
```python
# services/test-generation/src/integration_test_generator.py

class IntegrationTestGenerator:
    async def generate_integration_tests(self, code: dict, api_design: dict) -> dict:
        """
        Gera testes de integração para APIs.
        """
        tests = {}
        
    for endpoint in api_design.get('endpoints', []):
        test_file = await self._generate_tests_for_endpoint(endpoint)
        tests[test_file['path']] = test_file['content']
    
    return {
        "code_id": code.get('task_id'),
        "tests": tests,
        "test_count": len(tests),
        "generated_at": datetime.utcnow().isoformat()
    }
```

**Output Integration Test Generator:**
```json
{
  "code_id": "task_bc_user_management_user-service_setup",
  "tests": {
    "user-service/tests/integration/test_api.py": {
      "content": "import pytest\nfrom httpx import AsyncClient\nfrom src.main import app\n\n@pytest.mark.asyncio\nasync def test_register_user():\n    async with AsyncClient(app=app, base_url=\"http://test\") as client:\n        response = await client.post(\n            \"/api/v1/auth/register\",\n            json={\n                \"email\": \"test@example.com\",\n                \"password\": \"password123\",\n                \"name\": \"Test User\",\n                \"phone\": \"+5511999999999\",\n                \"role\": \"customer\"\n            }\n        )\n        assert response.status_code == 201\n        data = response.json()\n        assert data[\"email\"] == \"test@example.com\"\n        assert \"id\" in data\n\n@pytest.mark.asyncio\nasync def test_login_user():\n    async with AsyncClient(app=app, base_url=\"http://test\") as client:\n        response = await client.post(\n            \"/api/v1/auth/login\",\n            json={\n                \"email\": \"test@example.com\",\n                \"password\": \"password123\"\n            }\n        )\n        assert response.status_code == 200\n        data = response.json()\n        assert \"access_token\" in data\n        assert \"refresh_token\" in data"
    }
  },
  "test_count": 15,
  "generated_at": "2026-04-15T10:35:00Z"
}
```

**Componente 3: E2E Test Generator**
```python
# services/test-generation/src/e2e_test_generator.py

class E2ETestGenerator:
    async def generate_e2e_tests(self, requirements: dict) -> dict:
        """
        Gera testes end-to-end baseados em user stories.
        """
        tests = {}
        
        user_stories = requirements.get('user_stories', [])
        
        for user_story in user_stories:
            test_file = await self._generate_e2e_test_for_user_story(user_story)
            tests[test_file['path']] = test_file['content']
        
        return {
            "tests": tests,
            "test_count": len(tests),
            "generated_at": datetime.utcnow().isoformat()
        }
```

**Output E2E Test Generator:**
```json
{
  "tests": {
    "tests/e2e/test_order_flow.py": {
      "content": "import pytest\nfrom playwright.sync_api import Page, expect\n\ndef test_complete_order_flow(page: Page):\n    \"\"\"Test US_007: Customer can place order and pay\"\"\"\n    \n    # Step 1: Login\n    page.goto(\"https://delivery-app.com\")\n    page.fill(\"input[name='email']\", \"customer@example.com\")\n    page.fill(\"input[name='password']\", \"password123\")\n    page.click(\"button[type='submit']\")\n    expect(page).to_have_url(\"https://delivery-app.com/home\")\n    \n    # Step 2: Browse restaurants\n    page.fill(\"input[placeholder='Search restaurants']\", \"Pizza\")\n    page.click(\"button:has-text('Search')\")\n    \n    # Step 3: Select restaurant\n    page.click(\".restaurant-item:first-child\")\n    \n    # Step 4: Add items to cart\n    page.click(\".menu-item:first-child .add-to-cart\")\n    expect(page.locator(\".cart-count\")).to_have_text(\"1\")\n    \n    # Step 5: Checkout\n    page.click(\"button:has-text('View Cart')\")\n    page.click(\"button:has-text('Checkout')\")\n    \n    # Step 6: Payment\n    page.select_option(\"select[name='payment_method']\", \"pix\")\n    page.click(\"button:has-text('Place Order')\")\n    \n    # Step 7: Verify order confirmation\n    expect(page.locator(\".order-confirmation\")).to_be_visible()\n    expect(page.locator(\".order-status\")).to_have_text(\"pending\")"
    }
  },
  "test_count": 8,
  "generated_at": "2026-04-15T10:40:00Z"
}
```

**Evento Kafka Produzido:** `tests.generated`

---

### Passo 9: Orquestração - Documentation Generation

**Eventos Kafka Recebidos:** `code.generated`, `tests.generated`

**Documentation Generation System processa:**

**Componente 1: README Generator**
```python
# services/documentation-generation/src/readme_generator.py

class READMEGenerator:
    async def generate_readme(self, code: dict, requirements: dict) -> dict:
        """
        Gera README completo.
        """
        readme = await self._generate_readme_content(code, requirements)
        
        return {
            "filename": "README.md",
            "content": readme,
            "sections": [
                "Project Description",
                "Features",
                "Tech Stack",
                "Installation",
                "Configuration",
                "Running",
                "API Documentation",
                "Testing",
                "Deployment",
                "Contributing"
            ],
            "generated_at": datetime.utcnow().isoformat()
        }
```

**Output README Generator:**
```json
{
  "filename": "README.md",
  "content": "# Delivery App\n\n![Python](https://img.shields.io/badge/Python-3.12-blue.svg)\n![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green.svg)\n![License](https://img.shields.io/badge/License-MIT-yellow.svg)\n\n## 📋 Project Description\n\nDelivery App is a food delivery platform similar to Uber Eats for the Brazilian market. It allows customers to browse restaurants, place orders, track deliveries in real-time, and pay via multiple methods including PIX.\n\n## ✨ Features\n\n### Customer Features\n- 📱 User registration and authentication\n- 🍕 Restaurant browsing and search\n- 📜 Menu viewing and item selection\n- 🛒 Cart management\n- 💳 Multiple payment methods (PIX, Credit Card, Cash)\n- 📍 Real-time order tracking\n- 📝 Order history\n\n### Restaurant Owner Features\n- 🏪 Restaurant registration and management\n- 📋 Menu management\n- 📊 Order management\n- 💰 Revenue tracking\n\n### Admin Features\n- 📈 Platform analytics dashboard\n- 👥 User management\n- 🏢 Restaurant moderation\n- 🚚 Delivery person management\n\n## 🛠 Tech Stack\n\n### Backend\n- **Language:** Python 3.12+\n- **Framework:** FastAPI\n- **Database:** PostgreSQL\n- **Cache:** Redis\n- **Message Queue:** Apache Kafka\n- **Authentication:** JWT\n\n### Frontend\n- **Mobile App:** React Native\n- **Web App:** React\n- **Admin Panel:** React\n\n### Infrastructure\n- **Containerization:** Docker\n- **Orchestration:** Kubernetes\n- **CI/CD:** GitHub Actions\n- **Cloud:** AWS/GCP\n\n## 🚀 Installation\n\n### Prerequisites\n- Docker and Docker Compose\n- Python 3.12+\n- Node.js 18+\n\n### Backend Setup\n\n```bash\n# Clone repository\ngit clone https://github.com/your-org/delivery-app.git\ncd delivery-app\n\n# Start infrastructure (PostgreSQL, Redis, Kafka)\ndocker-compose up -d\n\n# Install dependencies for each service\nfor service in user-service restaurant-service order-service payment-service delivery-service notification-service; do\n    cd $service\n    poetry install\n    cd ..\ndone\n\n# Run migrations\nfor service in user-service restaurant-service order-service payment-service delivery-service; do\n    cd $service\n    poetry run alembic upgrade head\n    cd ..\ndone\n```\n\n### Frontend Setup\n\n```bash\n# Install dependencies for mobile app\ncd mobile-app\nnpm install\n\n# Install dependencies for web app\ncd web-app\nnpm install\n\n# Install dependencies for admin panel\ncd admin-panel\nnpm install\n```\n\n## ⚙️ Configuration\n\n### Environment Variables\n\nCreate a `.env` file in each service directory:\n\n```env\nDATABASE_URL=postgresql://user:password@localhost:5432/service_db\nREDIS_URL=redis://localhost:6379/0\nKAFKA_BOOTSTRAP_SERVERS=localhost:9092\nSECRET_KEY=your-secret-key-here\nALGORITHM=HS256\nACCESS_TOKEN_EXPIRE_MINUTES=30\n```\n\n## 🏃 Running\n\n### Backend Services\n\n```bash\n# Run all services (in separate terminals)\nfor service in user-service restaurant-service order-service payment-service delivery-service notification-service; do\n    cd $service\n    poetry run uvicorn src.main:app --host 0.0.0.0 --port $(cat PORT)\n    cd ..\ndone\n```\n\n### Frontend Applications\n\n```bash\n# Run mobile app\ncd mobile-app\nnpm run ios  # or npm run android\n\n# Run web app\ncd web-app\nnpm run dev\n\n# Run admin panel\ncd admin-panel\nnpm run dev\n```\n\n## 📚 API Documentation\n\nAPI documentation is available via Swagger UI:\n\n- **User Service:** http://localhost:8010/docs\n- **Restaurant Service:** http://localhost:8011/docs\n- **Order Service:** http://localhost:8012/docs\n- **Payment Service:** http://localhost:8013/docs\n- **Delivery Service:** http://localhost:8014/docs\n- **Notification Service:** http://localhost:8015/docs\n\n## 🧪 Testing\n\n```bash\n# Run unit tests\npytest tests/unit/\n\n# Run integration tests\npytest tests/integration/\n\n# Run E2E tests\npytest tests/e2e/\n\n# Run all tests with coverage\npytest --cov=src tests/\n```\n\n## 🚢 Deployment\n\n### Docker Compose (Local)\n\n```bash\ndocker-compose up -d\n```\n\n### Kubernetes (Production)\n\n```bash\n# Apply Kubernetes manifests\nkubectl apply -f k8s/\n\n# Verify deployment\nkubectl get pods\nkubectl get services\n```\n\n## 📝 Contributing\n\n1. Fork the repository\n2. Create a feature branch (`git checkout -b feat/amazing-feature`)\n3. Commit your changes (`git commit -m 'feat: add amazing feature'`)\n4. Push to the branch (`git push origin feat/amazing-feature`)\n5. Open a Pull Request\n\n## 📄 License\n\nThis project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.\n\n## 👥 Team\n\n- **Developed by:** NHM Team\n- **Architecture:** Microservices Event-Driven\n- **Version:** 1.0.0\n\n## 📞 Contact\n\n- **Email:** contact@delivery-app.com\n- **Website:** https://delivery-app.com\n\n---\n\nBuilt with ❤️ by NHM (Neural-Hive-Mind)",
  "sections": [
    "Project Description",
    "Features",
    "Tech Stack",
    "Installation",
    "Configuration",
    "Running",
    "API Documentation",
    "Testing",
    "Deployment",
    "Contributing"
  ],
  "generated_at": "2026-04-15T10:45:00Z"
}
```

**Evento Kafka Produzido:** `readme.generated`

---

### Passo 10: CI/CD Pipeline e Deploy

**Eventos Kafka Recebidos:** `code.generated`, `tests.generated`, `readme.generated`

**Software Engineering Pipeline processa:**

**Criação de branch e commit:**
```bash
# Criar branch
git checkout -b feat/delivery-app-v1

# Adicionar todos os arquivos gerados
git add .

# Commit
git commit -m "feat: implement delivery app v1 with microservices architecture

- User service with authentication
- Restaurant service with menu management
- Order service with real-time tracking
- Payment service with multiple methods
- Delivery service with routing
- Notification service with multi-channel
- Kubernetes manifests
- CI/CD pipeline
- Complete documentation
- Unit, integration and E2E tests

Co-authored-by: Neural-Hive-Mind <nhm@ai>"
```

**Push para GitHub:**
```bash
git push origin feat/delivery-app-v1
```

**Pull Request criado automaticamente:**
```json
{
  "title": "feat: implement delivery app v1",
  "body": "## 🎉 Feature: Delivery App v1\n\nAutomatically generated by NHM (Neural-Hive-Mind)\n\n### Changes\n- **6 microservices:** user, restaurant, order, payment, delivery, notification\n- **Tech stack:** FastAPI, PostgreSQL, Redis, Kafka, React, React Native\n- **Infrastructure:** Docker, Kubernetes, GitHub Actions\n- **Documentation:** README, API docs, architecture docs, C4 diagrams\n- **Tests:** 42 unit tests, 15 integration tests, 8 E2E tests\n\n### Verification\n- [x] Code generated\n- [x] Tests generated\n- [x] Documentation generated\n- [x] Security scan passed\n- [x] All tests passing\n\n### Deployment\n- [ ] Merge to main\n- [ ] Deploy to staging\n- [ ] Deploy to production",
  "labels": ["auto-generated", "feat", "ci-cd"],
  "base": "main",
  "head": "feat/delivery-app-v1"
}
```

**CI Pipeline Execução:**

**Stage 1: Build**
```yaml
- name: Build Docker images
  run: |
    docker build -t delivery-app/user-service:latest user-service/
    docker build -t delivery-app/restaurant-service:latest restaurant-service/
    docker build -t delivery-app/order-service:latest order-service/
    docker build -t delivery-app/payment-service:latest payment-service/
    docker build -t delivery-app/delivery-service:latest delivery-service/
    docker build -t delivery-app/notification-service:latest notification-service/
```

**Stage 2: Test**
```yaml
- name: Run tests
  run: |
    pytest tests/unit/ --cov=src --cov-report=xml
    pytest tests/integration/\n    pytest tests/e2e/\n```

**Stage 3: Security Scan**
```yaml
- name: Security scan
  run: |
    pip-audit
    bandit -r src/
    trivy image delivery-app/user-service:latest
```

**Stage 4: Deploy to Staging**
```yaml
- name: Deploy to staging
  run: |
    kubectl apply -f k8s/staging/
    kubectl rollout status deployment/user-service -n staging
```

**Stage 5: Approval**
```yaml
- name: Request approval
  run: |
    gh pr create --title "Deploy to Production" --body "Ready for production deployment?"
```

**Stage 6: Deploy to Production**
```yaml
- name: Deploy to production
  run: |
    kubectl apply -f k8s/production/\n    kubectl rollout status deployment/user-service -n production
```

**Evento Kafka Produzido:** `build.completed`

**Payload:**
```json
{
  "build_id": "build_001",
  "status": "success",
  "stages": [
    {
      "name": "Build",
      "status": "success",
      "duration_seconds": 300,
      "cost_usd": 5.0
    },
    {
      "name": "Test",
      "status": "success",
      "duration_seconds": 180,
      "cost_usd": 2.5
    },
    {
      "name": "Security Scan",
      "status": "success",
      "duration_seconds": 60,
      "cost_usd": 1.0
    },
    {
      "name": "Staging",
      "status": "success",
      "duration_seconds": 120,
      "cost_usd": 1.5
    },
    {
      "name": "Approval",
      "status": "success",
      "duration_seconds": 300,
      "cost_usd": 0.5
    },
    {
      "name": "Production",
      "status": "success",
      "duration_seconds": 90,
      "cost_usd": 2.0
    }
  ],
  "test_results": {
    "total": 65,
    "passed": 65,
    "failed": 0,
    "coverage": 85.5
  },
  "security_results": {
    "vulnerabilities": 0,
    "severity": "none"
  },
  "deployment_results": {
    "staging": {
      "status": "success",
      "url": "https://staging.delivery-app.com",
      "uptime": 100
    },
    "production": {
      "status": "success",
      "url": "https://delivery-app.com",
      "uptime": 100
    }
  },
  "duration_seconds": 1050,
  "cost_usd": 12.5,
  "completed_at": "2026-04-15T12:00:00Z"
}
```

---

### Passo 11: CI Feedback Loop

**Evento Kafka Recebido:** `build.completed`

**CI Feedback Loop processa:**

**Componente 1: Feedback Collector**
```python
# services/ci-feedback-loop/src/feedback_collector.py

class FeedbackCollector:
    async def collect_feedback(self, build_data: dict) -> dict:
        """
        Coleta feedback de build.
        """
        feedback = {
            "build_id": build_data.get('build_id'),
            "build_metrics": self._extract_build_metrics(build_data),
            "test_metrics": self._extract_test_metrics(build_data),
            "deployment_metrics": self._extract_deployment_metrics(build_data),
            "quality_scores": self._calculate_quality_scores(build_data),
            "anomalies": self._identify_anomalies(build_data),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return feedback
```

**Output Feedback Collector:**
```json
{
  "build_id": "build_001",
  "build_metrics": {
    "duration_seconds": 1050,
    "cost_usd": 12.5,
    "status": "success",
    "stages_completed": 6,
    "stages_failed": 0
  },
  "test_metrics": {
    "total_tests": 65,
    "passed": 65,
    "failed": 0,
    "coverage_percentage": 85.5,
    "mutation_score": 82.0,
    "flaky_tests": []
  },
  "deployment_metrics": {
    "staging_status": "success",
    "production_status": "success",
    "uptime_percentage": 100,
    "response_time_p95_ms": 150,
    "error_rate": 0.001
  },
  "quality_scores": {
    "test": 0.85,
    "build": 1.0,
    "deployment": 0.98,
    "overall": 0.92
  },
  "anomalies": [],
  "timestamp": "2026-04-15T12:05:00Z"
}
```

**Evento Kafka Produzido:** `feedback.collected`

**Componente 2: Reinforcement Learner**
```python
# services/ci-feedback-loop/src/reinforcement_learner.py

class ReinforcementLearner:
    async def learn_and_update_policies(self, feedback: dict) -> dict:
        """
        Aprende com feedback e atualiza políticas.
        """
        rewards = self._calculate_rewards(feedback)
        policy_updates = self._update_policies(rewards)
        
        return {
            "feedback_analysis": feedback,
            "rewards": rewards,
            "policy_updates": policy_updates,
            "generated_at": datetime.utcnow().isoformat()
        }
```

**Output Reinforcement Learner:**
```json
{
  "feedback_analysis": {
    "build_success_rate": 1.0,
    "test_success_rate": 1.0,
    "coverage_percentage": 85.5,
    "deployment_success_rate": 1.0
  },
  "rewards": {
    "build_success": 1.0,
    "test_success": 1.0,
    "high_coverage": 0.5,
    "no_flaky_tests": 0.3,
    "fast_deployment": 0.2,
    "overall_reward": 2.0
  },
  "policy_updates": {
    "code_generation_policies": {
      "template_fastapi_microservice_v2_weight": 1.2,
      "llm_temperature": 0.6
    },
    "test_generation_policies": {
      "unit_test_priority": "high",
      "integration_test_priority": "high",
      "e2e_test_priority": "medium"
    }
  },
  "generated_at": "2026-04-15T12:10:00Z"
}
```

**Evento Kafka Produzido:** `policy_updates.applied`

---

### Passo 12: Software Deployado 🎉

**Resultado Final:**

```
✨ Delivery App v1 Deployed com Sucesso! ✨

📊 Estatísticas:
- 6 microservices deployados
- 65 testes passando (85.5% coverage)
- 0 vulnerabilidades de segurança
- 99.9% uptime

🔗 URLs:
- Mobile App: https://delivery-app.com/mobile
- Web App: https://delivery-app.com
- Admin Panel: https://admin.delivery-app.com
- API Docs: https://api.delivery-app.com/docs

⏱️ Tempo Total: 2 horas
💰 Custo Total: $12.50
👥 Usuários Podem: 10,000+ concorrentes

🚀 Pronto para uso! 🚀
```

---

## 📊 Sumário do Fluxo G

| Etapa | Sistema | Tempo | Eventos Kafka Produzidos |
|-------|---------|-------|---------------------------|
| 1 | Gateway Intenções | 5s | `intention.submitted` |
| 2 | Semantic Translation Engine | 5s | `intention.translated` |
| 3 | Consensus Engine | 80s | `consensus.reached` |
| 4 | Requirements Engineering | 180s | `requirements.generated` |
| 5 | Architectural Planning | 300s | `architectural.plan` |
| 6 | Agentic Delegation | 60s | `plan.decomposed`, `agents.assigned` |
| 7 | Code Forge | 1800s | `code.generated` |
| 8 | Test Generation | 600s | `tests.generated` |
| 9 | Documentation Generation | 300s | `readme.generated`, `api_docs.generated`, `architecture_docs.generated` |
| 10 | CI/CD Pipeline | 1050s | `build.completed` |
| 11 | CI Feedback Loop | 300s | `feedback.collected`, `policy_updates.applied` |
| **Total** | | **~2 horas** | **14 eventos Kafka** |

---

## 🎯 Pontos Chave do Fluxo G

1. **Orquestração Completa:** Cada sistema é ativado na ordem correta pelo Orchestrator Dynamic
2. **Comunicação Assíncrona:** Kafka permite desacoplamento entre sistemas
3. **Inteligência Distribuída:** Consensus Engine, RAG Engine e Reinforcement Learner contribuem com inteligência
4. **Auto-Correção:** CI Feedback Loop permite aprendizado contínuo
5. **Rastreamento Total:** Cada etapa produz eventos Kafka que podem ser rastreados
6. **Validação Contínua:** Cada etapa valida outputs antes de prosseguir
7. **Escalabilidade:** Arquitetura microservices permite escala independente

---

Na próxima parte, documentaremos o **Fluxo H: Documentação → Software** com exemplo prático de migração de software existente.


---

## 🔄 Fluxo H Completo: Documentação → Software (Exemplo Prático)

### Descrição Geral

O Fluxo H demonstra a migração de software existente baseada em documentação (legado) usando os 7 sistemas documentados.

### Exemplo Prático: Migração de Sistema de E-commerce Legado

**Cenário:** Sistema de e-commerce em PHP 5.6 (legado) precisa ser migrado para arquitetura moderna

**Documentação Disponível:**
- Manual de usuário (PDF)
- Especificação técnica (Word)
- Diagramas de banco de dados (Visio)
- API docs (Postman collection)
- README parcial (Markdown)

### Diagrama de Sequência Completo

```mermaid
sequenceDiagram
    autonumber
    participant User as Usuário
    participant DocIngest as Doc Ingestion Service
    participant Gateway as Gateway Intenções
    participant STE as Semantic Translation
    participant Consensus as Consensus Engine
    participant Orchestrator as Orchestrator Dynamic
    participant ReqEng as Requirements Engineering
    participant ArchPlan as Architectural Planning
    participant AgentDel as Agentic Delegation
    participant CodeForge as Code Forge
    participant TestGen as Test Generation
    participant DocsGen as Documentation Generation
    participant CILoop as CI Feedback Loop
    participant CI as Software Engineering Pipeline
    participant Kafka as Kafka

    User->>DocIngest: Upload documentação legada
    Note over User,DocIngest: PDF, Word, Visio, Postman
    
    DocIngest->>DocIngest: Parse documentos
    DocIngest->>DocIngest: Extrair entidades
    DocIngest->>DocIngest: Gerar intenções
    
    DocIngest->>Gateway: POST /api/v1/intentions
    Note over DocIngest,Gateway: Payload: Intenção de migração
    
    Gateway->>STE: intention.submitted
    
    STE->>Kafka: intention.translated
    Note over STE,Kafka: Payload: Intenção formatada
    
    Kafka->>Consensus: intention.translated
    
    Consensus->>Kafka: consensus.reached
    Note over Consensus,Kafka: Payload: Plano consensual
    
    Kafka->>Orchestrator: consensus.reached
    
    Orchestrator->>ReqEng: requirements.needed
    Note over Orchestrator,ReqEng: Payload: Doc legada + Contexto
    
    ReqEng->>Kafka: requirements.generated
    Note over ReqEng,Kafka: Payload: User stories, API design extraído
    
    Kafka->>ArchPlan: requirements.generated
    
    ArchPlan->>Kafka: architectural.plan
    Note over ArchPlan,Kafka: Payload: Arquitetura moderna
    
    Kafka->>AgentDel: architectural.plan
    
    AgentDel->>Kafka: plan.decomposed
    AgentDel->>Kafka: agents.assigned
    
    Kafka->>CodeForge: plan.decomposed
    Kafka->>CodeForge: agents.assigned
    
    CodeForge->>Kafka: code.generated
    Note over CodeForge,Kafka: Payload: Código moderno
    
    Kafka->>TestGen: code.generated
    
    TestGen->>Kafka: tests.generated
    Note over TestGen,Kafka: Payload: Testes de migração
    
    Kafka->>CI: code.generated
    Kafka->>CI: tests.generated
    
    CI->>CI: Build Docker images
    CI->>CI: Run tests
    CI->>CI: Deploy to Staging
    CI->>Kafka: build.completed
    
    Kafka->>CILoop: build.completed
    
    CILoop->>Kafka: feedback.collected
    CILoop->>Kafka: policy_updates.applied
    
    CI->>CI: Migrate data
    CI->>CI: Deploy to Production
    CI->>User: 🎉 Migração Completa!
```

---

### Passo 1: Ingestão de Documentação Legada

**Endpoint:** `POST /api/v1/documents/ingest`

**Request Payload:**
```json
{
  "ingestion_id": "ingest_001",
  "documents": [
    {
      "type": "user_manual",
      "format": "pdf",
      "filename": "user_manual.pdf",
      "url": "https://legacy-system.com/docs/user_manual.pdf",
      "description": "Manual do usuário completo do sistema legado"
    },
    {
      "type": "technical_spec",
      "format": "word",
      "filename": "technical_spec.docx",
      "url": "https://legacy-system.com/docs/technical_spec.docx",
      "description": "Especificação técnica do sistema"
    },
    {
      "type": "database_schema",
      "format": "visio",
      "filename": "database_schema.vsd",
      "url": "https://legacy-system.com/docs/database_schema.vsd",
      "description": "Diagrama ER do banco de dados MySQL"
    },
    {
      "type": "api_documentation",
      "format": "postman",
      "filename": "api_collection.json",
      "url": "https://legacy-system.com/docs/api_collection.json",
      "description": "Coleção Postman com todas as APIs"
    }
  ],
  "legacy_system_info": {
    "name": "Legacy E-commerce",
    "technology": "PHP 5.6",
    "database": "MySQL 5.5",
    "web_server": "Apache 2.2",
    "deployed_at": "2010-01-01"
  },
  "migration_targets": {
    "target_language": "Python",
    "target_framework": "FastAPI",
    "target_database": "PostgreSQL",
    "target_architecture": "microservices"
  },
  "submitted_at": "2026-04-15T14:00:00Z"
}
```

**Response (Doc Ingestion Service):**
```json
{
  "ingestion_id": "ingest_001",
  "status": "processing",
  "message": "Documentação recebida para processamento",
  "estimated_processing_time": "PT10M",
  "steps": [
    "Parsear documentos",
    "Extrair entidades",
    "Gerar intenções",
    "Validar qualidade"
  ],
  "created_at": "2026-04-15T14:00:05Z"
}
```

---

### Passo 2: Parseamento e Extração de Entidades

**Processamento Doc Ingestion Service:**

**Parseamento de User Manual (PDF):**
```python
# services/doc-ingestion/src/parsers/pdf_parser.py

class PDFParser:
    async def parse_user_manual(self, pdf_path: str) -> dict:
        """
        Parse manual do usuário em PDF.
        """
        # Extrair texto do PDF
        text_content = await self._extract_text(pdf_path)
        
        # Identificar seções
        sections = await self._identify_sections(text_content)
        
        # Extrair funcionalidades
        functionalities = await self._extract_functionalities(text_content, sections)
        
        # Extrair user stories implícitas
        user_stories = await self._derive_user_stories(text_content, functionalities)
        
        return {
            "source": "user_manual.pdf",
            "sections": sections,
            "functionalities": functionalities,
            "user_stories": user_stories,
            "parsed_at": datetime.utcnow().isoformat()
        }
```

**Output Parseamento PDF:**
```json
{
  "source": "user_manual.pdf",
  "sections": [
    {
      "title": "Introdução",
      "page_range": [1, 3],
      "content": "Sistema de e-commerce para venda de produtos online..."
    },
    {
      "title": "Cadastro de Produtos",
      "page_range": [10, 25],
      "content": "Como cadastrar produtos no sistema..."
    },
    {
      "title": "Gestão de Pedidos",
      "page_range": [30, 50],
      "content": "Como gerenciar pedidos de clientes..."
    },
    {
      "title": "Gestão de Clientes",
      "page_range": [55, 70],
      "content": "Como gerenciar clientes do sistema..."
    },
    {
      "title": "Relatórios",
      "page_range": [75, 90],
      "content": "Como gerar relatórios de vendas..."
    }
  ],
  "functionalities": [
    {
      "id": "func_001",
      "name": "Cadastro de Produtos",
      "description": "Permite administradores cadastrarem produtos com informações de nome, descrição, preço, estoque e categoria",
      "features": [
        "Criar produto",
        "Editar produto",
        "Excluir produto",
        "Listar produtos",
        "Buscar produto"
      ],
      "user_roles": ["admin"],
      "screens_mentioned": ["Cadastro de Produto", "Lista de Produtos"]
    },
    {
      "id": "func_002",
      "name": "Gestão de Pedidos",
      "description": "Permite administradores e vendedores gerenciarem pedidos de clientes",
      "features": [
        "Criar pedido manual",
        "Editar pedido",
        "Cancelar pedido",
        "Acompanhar status",
        "Atualizar status (pendente, aprovado, enviado, entregue, cancelado)"
      ],
      "user_roles": ["admin", "seller"],
      "screens_mentioned": ["Lista de Pedidos", "Detalhes do Pedido"]
    },
    {
      "id": "func_003",
      "name": "Gestão de Clientes",
      "description": "Permite administradores gerenciarem cadastros de clientes",
      "features": [
        "Cadastrar cliente",
        "Editar cliente",
        "Excluir cliente",
        "Visualizar histórico de pedidos",
        "Gerenciar endereços"
      ],
      "user_roles": ["admin"],
      "screens_mentioned": ["Lista de Clientes", "Detalhes do Cliente"]
    },
    {
      "id": "func_004",
      "name": "Relatórios de Vendas",
      "description": "Permite administradores gerarem relatórios de vendas",
      "features": [
        "Relatório por período",
        "Relatório por produto",
        "Relatório por cliente",
        "Relatório por vendedor",
        "Exportar para Excel"
      ],
      "user_roles": ["admin"],
      "screens_mentioned": ["Dashboard de Relatórios"]
    },
    {
      "id": "func_005",
      "name": "Carrinho de Compras",
      "description": "Permite clientes adicionarem produtos ao carrinho",
      "features": [
        "Adicionar item ao carrinho",
        "Remover item do carrinho",
        "Alterar quantidade",
        "Calcular total",
        "Aplicar cupom de desconto"
      ],
      "user_roles": ["customer"],
      "screens_mentioned": ["Carrinho", "Checkout"]
    }
  ],
  "user_stories": [
    {
      "id": "us_001",
      "as_a": "admin",
      "i_want_to": "cadastrar um novo produto",
      "so_that": "ele possa ser vendido no sistema",
      "derived_from": "Cadastro de Produtos",
      "priority": "high"
    },
    {
      "id": "us_002",
      "as_a": "admin",
      "i_want_to": "visualizar todos os pedidos",
      "so_that": "eu possa gerenciar as vendas",
      "derived_from": "Gestão de Pedidos",
      "priority": "high"
    },
    {
      "id": "us_003",
      "as_a": "customer",
      "i_want_to": "adicionar produtos ao carrinho",
      "so_that": "eu possa fazer uma compra",
      "derived_from": "Carrinho de Compras",
      "priority": "high"
    }
  ],
  "parsed_at": "2026-04-15T14:05:00Z"
}
```

**Parseamento de Especificação Técnica (Word):**
```python
# services/doc-ingestion/src/parsers/word_parser.py

class WordParser:
    async def parse_technical_spec(self, word_path: str) -> dict:
        """
        Parse especificação técnica em Word.
        """
        # Extrair conteúdo do Word
        content = await self._extract_content(word_path)
        
        # Identificar requisitos funcionais
        functional_reqs = await self._extract_functional_requirements(content)
        
        # Identificar requisitos não funcionais
        non_functional_reqs = await self._extract_non_functional_requirements(content)
        
        # Extrair arquitetura
        architecture = await self._extract_architecture(content)
        
        # Extrair integrações
        integrations = await self._extract_integrations(content)
        
        return {
            "source": "technical_spec.docx",
            "functional_requirements": functional_reqs,
            "non_functional_requirements": non_functional_reqs,
            "architecture": architecture,
            "integations": integrations,
            "parsed_at": datetime.utcnow().isoformat()
        }
```

**Output Parseamento Word:**
```json
{
  "source": "technical_spec.docx",
  "functional_requirements": [
    {
      "id": "fr_001",
      "title": "Autenticação de Usuários",
      "description": "Sistema deve permitir login de usuários via email e senha",
      "priority": "critical",
      "acceptance_criteria": [
        "Usuário pode fazer login com credenciais válidas",
        "Sessão expira após 30 minutos de inatividade",
        "Senha deve ter mínimo 6 caracteres"
      ]
    },
    {
      "id": "fr_002",
      "title": "Catálogo de Produtos",
      "description": "Sistema deve exibir catálogo de produtos com busca e filtros",
      "priority": "high",
      "acceptance_criteria": [
        "Produtos listados com imagem, nome, preço",
        "Busca por nome de produto",
        "Filtro por categoria",
        "Filtro por faixa de preço"
      ]
    },
    {
      "id": "fr_003",
      "title": "Carrinho de Compras",
      "description": "Sistema deve permitir gerenciamento de carrinho de compras",
      "priority": "critical",
      "acceptance_criteria": [
        "Adicionar produtos ao carrinho",
        "Remover produtos do carrinho",
        "Alterar quantidade de itens",
        "Calcular total automaticamente",
        "Persistir carrinho na sessão"
      ]
    },
    {
      "id": "fr_004",
      "title": "Checkout e Pagamento",
      "description": "Sistema deve permitir finalização de compra com pagamento",
      "priority": "critical",
      "acceptance_criteria": [
        "Formulário de endereço de entrega",
        "Seleção de método de pagamento (cartão, boleto)",
        "Integração com gateway de pagamento",
        "Confirmação de pedido por email"
      ]
    },
    {
      "id": "fr_005",
      "title": "Gestão de Pedidos",
      "description": "Sistema deve permitir gerenciamento de pedidos por administradores",
      "priority": "high",
      "acceptance_criteria": [
        "Listar todos os pedidos",
        "Visualizar detalhes do pedido",
        "Atualizar status do pedido",
        "Cancelar pedido",
        "Gerar nota fiscal"
      ]
    }
  ],
  "non_functional_requirements": [
    {
      "id": "nfr_001",
      "category": "performance",
      "requirement": "Páginas devem carregar em menos de 3 segundos",
      "priority": "high"
    },
    {
      "id": "nfr_002",
      "category": "availability",
      "requirement": "Sistema deve ter 99% de disponibilidade",
      "priority": "high"
    },
    {
      "id": "nfr_003",
      "category": "security",
      "requirement": "Senhas devem ser armazenadas com hash (bcrypt)",
      "priority": "critical"
    },
    {
      "id": "nfr_004",
      "category": "scalability",
      "requirement": "Sistema deve suportar 1000 usuários simultâneos",
      "priority": "medium"
    }
  ],
  "architecture": {
    "type": "monolithic",
    "description": "Aplicação monolítica em PHP com Apache",
    "layers": [
      "Presentation (PHP/HTML)",
      "Business Logic (PHP)",
      "Data Access (PHP/MySQL)"
    ],
    "components": [
      "User Management",
      "Product Catalog",
      "Shopping Cart",
      "Order Management",
      "Payment Integration",
      "Reporting"
    ]
  },
  "integrations": [
    {
      "name": "Gateway de Pagamento",
      "type": "REST API",
      "provider": "PagSeguro",
      "description": "Processamento de pagamentos online"
    },
    {
      "name": "Envio de Emails",
      "type": "SMTP",
      "provider": "SendGrid",
      "description": "Envio de emails de confirmação"
    },
    {
      "name": "Geração de NF-e",
      "type": "SOAP API",
      "provider": "SEFAZ",
      "description": "Emissão de notas fiscais eletrônicas"
    }
  ],
  "parsed_at": "2026-04-15T14:07:00Z"
}
```

**Parseamento de Schema do Banco (Visio):**
```python
# services/doc-ingestion/src/parsers/visio_parser.py

class VisioParser:
    async def parse_database_schema(self, visio_path: str) -> dict:
        """
        Parse diagrama ER em Visio.
        """
        # Extrair entidades do Visio
        entities = await self._extract_entities(visio_path)
        
        # Extrair relacionamentos
        relationships = await self._extract_relationships(visio_path)
        
        # Gerar modelos de dados
        data_models = await self._generate_data_models(entities, relationships)
        
        return {
            "source": "database_schema.vsd",
            "database_type": "MySQL",
            "entities": entities,
            "relationships": relationships,
            "data_models": data_models,
            "parsed_at": datetime.utcnow().isoformat()
        }
```

**Output Parseamento Visio:**
```json
{
  "source": "database_schema.vsd",
  "database_type": "MySQL",
  "entities": [
    {
      "name": "users",
      "primary_key": "id",
      "fields": [
        {"name": "id", "type": "INT", "primary_key": true, "auto_increment": true},
        {"name": "name", "type": "VARCHAR(100)", "nullable": false},
        {"name": "email", "type": "VARCHAR(255)", "unique": true, "nullable": false},
        {"name": "password", "type": "VARCHAR(255)", "nullable": false},
        {"name": "phone", "type": "VARCHAR(20)", "nullable": true},
        {"name": "address", "type": "TEXT", "nullable": true},
        {"name": "role", "type": "ENUM('admin', 'seller', 'customer')", "default": "customer"},
        {"name": "created_at", "type": "TIMESTAMP", "default": "CURRENT_TIMESTAMP"}
      ],
      "indexes": [
        {"fields": ["email"], "unique": true},
        {"fields": ["role"]}
      ]
    },
    {
      "name": "products",
      "primary_key": "id",
      "fields": [
        {"name": "id", "type": "INT", "primary_key": true, "auto_increment": true},
        {"name": "name", "type": "VARCHAR(255)", "nullable": false},
        {"name": "description", "type": "TEXT", "nullable": true},
        {"name": "price", "type": "DECIMAL(10, 2)", "nullable": false},
        {"name": "stock", "type": "INT", "default": 0},
        {"name": "category_id", "type": "INT", "nullable": false},
        {"name": "image_url", "type": "VARCHAR(500)", "nullable": true},
        {"name": "created_at", "type": "TIMESTAMP", "default": "CURRENT_TIMESTAMP"},
        {"name": "updated_at", "type": "TIMESTAMP", "default": "CURRENT_TIMESTAMP", "on_update": "CURRENT_TIMESTAMP"}
      ],
      "indexes": [
        {"fields": ["category_id"]},
        {"fields": ["name"]},
        {"fields": ["price"]}
      ]
    },
    {
      "name": "categories",
      "primary_key": "id",
      "fields": [
        {"name": "id", "type": "INT", "primary_key": true, "auto_increment": true},
        {"name": "name", "type": "VARCHAR(100)", "nullable": false},
        {"name": "description", "type": "TEXT", "nullable": true},
        {"name": "parent_id", "type": "INT", "nullable": true}
      ],
      "indexes": [
        {"fields": ["parent_id"]}
      ]
    },
    {
      "name": "orders",
      "primary_key": "id",
      "fields": [
        {"name": "id", "type": "INT", "primary_key": true, "auto_increment": true},
        {"name": "user_id", "type": "INT", "nullable": false},
        {"name": "status", "type": "ENUM('pending', 'approved', 'sent', 'delivered', 'cancelled')", "default": "pending"},
        {"name": "total_amount", "type": "DECIMAL(10, 2)", "nullable": false},
        {"name": "shipping_address", "type": "TEXT", "nullable": false},
        {"name": "payment_method", "type": "ENUM('credit_card', 'boleto', 'pix')", "nullable": false},
        {"name": "payment_status", "type": "ENUM('pending', 'approved', 'rejected', 'refunded')", "default": "pending"},
        {"name": "created_at", "type": "TIMESTAMP", "default": "CURRENT_TIMESTAMP"},
        {"name": "updated_at", "type": "TIMESTAMP", "default": "CURRENT_TIMESTAMP", "on_update": "CURRENT_TIMESTAMP"}
      ],
      "indexes": [
        {"fields": ["user_id"]},
        {"fields": ["status"]},
        {"fields": ["created_at"]}
      ]
    },
    {
      "name": "order_items",
      "primary_key": "id",
      "fields": [
        {"name": "id", "type": "INT", "primary_key": true, "auto_increment": true},
        {"name": "order_id", "type": "INT", "nullable": false},
        {"name": "product_id", "type": "INT", "nullable": false},
        {"name": "quantity", "type": "INT", "nullable": false},
        {"name": "unit_price", "type": "DECIMAL(10, 2)", "nullable": false},
        {"name": "subtotal", "type": "DECIMAL(10, 2)", "nullable": false}
      ],
      "indexes": [
        {"fields": ["order_id"]},
        {"fields": ["product_id"]}
      ]
    },
    {
      "name": "payments",
      "primary_key": "id",
      "fields": [
        {"name": "id", "type": "INT", "primary_key": true, "auto_increment": true},
        {"name": "order_id", "type": "INT", "nullable": false},
        {"name": "amount", "type": "DECIMAL(10, 2)", "nullable": false},
        {"name": "method", "type": "ENUM('credit_card', 'boleto', 'pix')", "nullable": false},
        {"name": "status", "type": "ENUM('pending', 'approved', 'rejected', 'refunded')", "default": "pending"},
        {"name": "transaction_id", "type": "VARCHAR(100)", "nullable": true},
        {"name": "payment_date", "type": "TIMESTAMP", "nullable": true},
        {"name": "created_at", "type": "TIMESTAMP", "default": "CURRENT_TIMESTAMP"}
      ],
      "indexes": [
        {"fields": ["order_id"]},
        {"fields": ["transaction_id"]},
        {"fields": ["status"]}
      ]
    }
  ],
  "relationships": [
    {
      "from_table": "products",
      "to_table": "categories",
      "type": "many_to_one",
      "foreign_key": "category_id",
      "description": "Produto pertence a uma categoria"
    },
    {
      "from_table": "orders",
      "to_table": "users",
      "type": "many_to_one",
      "foreign_key": "user_id",
      "description": "Pedido pertence a um usuário"
    },
    {
      "from_table": "order_items",
      "to_table": "orders",
      "type": "many_to_one",
      "foreign_key": "order_id",
      "description": "Item de pedido pertence a um pedido"
    },
    {
      "from_table": "order_items",
      "to_table": "products",
      "type": "many_to_one",
      "foreign_key": "product_id",
      "description": "Item de pedido referencia um produto"
    },
    {
      "from_table": "payments",
      "to_table": "orders",
      "type": "many_to_one",
      "foreign_key": "order_id",
      "description": "Pagamento pertence a um pedido"
    }
  ],
  "data_models": [
    {
      "name": "User",
      "source_table": "users",
      "fields": [
        {"name": "id", "type": "int", "primary_key": true},
        {"name": "name", "type": "str"},
        {"name": "email", "type": "str", "unique": true},
        {"name": "phone", "type": "str"},
        {"name": "address", "type": "str"},
        {"name": "role", "type": "enum"}
      ]
    },
    {
      "name": "Product",
      "source_table": "products",
      "fields": [
        {"name": "id", "type": "int", "primary_key": true},
        {"name": "name", "type": "str"},
        {"name": "description", "type": "str"},
        {"name": "price", "type": "decimal"},
        {"name": "stock", "type": "int"},
        {"name": "category_id", "type": "int"},
        {"name": "image_url", "type": "str"}
      ]
    },
    {
      "name": "Order",
      "source_table": "orders",
      "fields": [
        {"name": "id", "type": "int", "primary_key": true},
        {"name": "user_id", "type": "int"},
        {"name": "status", "type": "enum"},
        {"name": "total_amount", "type": "decimal"},
        {"name": "shipping_address", "type": "str"},
        {"name": "payment_method", "type": "enum"}
      ]
    }
  ],
  "parsed_at": "2026-04-15T14:09:00Z"
}
```

**Parseamento de Documentação de API (Postman):**
```python
# services/doc-ingestion/src/parsers/postman_parser.py

class PostmanParser:
    async def parse_api_collection(self, postman_path: str) -> dict:
        """
        Parse coleção Postman.
        """
        # Carregar coleção JSON
        collection = await self._load_collection(postman_path)
        
        # Extrair endpoints
        endpoints = await self._extract_endpoints(collection)
        
        # Agrupar por recurso
        grouped_endpoints = await self._group_by_resource(endpoints)
        
        # Extrair exemplos de requests/responses
        examples = await self._extract_examples(collection)
        
        return {
            "source": "api_collection.json",
            "base_url": collection.get('variable', [{}])[0].get('value', 'http://api.legacy-system.com'),
            "endpoints": grouped_endpoints,
            "examples": examples,
            "total_endpoints": len(endpoints),
            "parsed_at": datetime.utcnow().isoformat()
        }
```

**Output Parseamento Postman:**
```json
{
  "source": "api_collection.json",
  "base_url": "http://api.legacy-system.com/v1",
  "endpoints": [
    {
      "resource": "auth",
      "path": "/auth/login",
      "method": "POST",
      "description": "Realiza login do usuário",
      "request_body": {
        "email": "string",
        "password": "string"
      },
      "response": {
        "status": 200,
        "body": {
          "token": "string",
          "user": {
            "id": "int",
            "name": "string",
            "email": "string",
            "role": "string"
          }
        }
      }
    },
    {
      "resource": "auth",
      "path": "/auth/logout",
      "method": "POST",
      "description": "Realiza logout do usuário",
      "headers": {
        "Authorization": "Bearer {token}"
      },
      "response": {
        "status": 200,
        "body": {
          "message": "Logout realizado com sucesso"
        }
      }
    },
    {
      "resource": "products",
      "path": "/products",
      "method": "GET",
      "description": "Lista todos os produtos",
      "query_params": {
        "page": "int",
        "limit": "int",
        "category_id": "int",
        "search": "string"
      },
      "response": {
        "status": 200,
        "body": {
          "products": [
            {
              "id": "int",
              "name": "string",
              "description": "string",
              "price": "decimal",
              "stock": "int",
              "image_url": "string",
              "category": {
                "id": "int",
                "name": "string"
              }
            }
          ],
          "pagination": {
            "total": "int",
            "page": "int",
            "limit": "int"
          }
        }
      }
    },
    {
      "resource": "products",
      "path": "/products/{id}",
      "method": "GET",
      "description": "Obtém detalhes de um produto",
      "response": {
        "status": 200,
        "body": {
          "id": "int",
          "name": "string",
          "description": "string",
          "price": "decimal",
          "stock": "int",
          "image_url": "string",
          "category": {
            "id": "int",
            "name": "string"
          }
        }
      }
    },
    {
      "resource": "products",
      "path": "/products",
      "method": "POST",
      "description": "Cria um novo produto",
      "headers": {
        "Authorization": "Bearer {token}"
      },
      "request_body": {
        "name": "string",
        "description": "string",
        "price": "decimal",
        "stock": "int",
        "category_id": "int",
        "image_url": "string"
      },
      "response": {
        "status": 201,
        "body": {
          "id": "int",
          "name": "string",
          "description": "string",
          "price": "decimal",
          "stock": "int",
          "image_url": "string",
          "category_id": "int"
        }
      }
    },
    {
      "resource": "orders",
      "path": "/orders",
      "method": "POST",
      "description": "Cria um novo pedido",
      "headers": {
        "Authorization": "Bearer {token}"
      },
      "request_body": {
        "items": [
          {
            "product_id": "int",
            "quantity": "int"
          }
        ],
        "shipping_address": "string",
        "payment_method": "credit_card|boleto|pix"
      },
      "response": {
        "status": 201,
        "body": {
          "id": "int",
          "user_id": "int",
          "status": "pending",
          "total_amount": "decimal",
          "payment_status": "pending",
          "items": [
            {
              "id": "int",
              "product_id": "int",
              "quantity": "int",
              "unit_price": "decimal",
              "subtotal": "decimal"
            }
          ]
        }
      }
    },
    {
      "resource": "orders",
      "path": "/orders/{id}",
      "method": "GET",
      "description": "Obtém detalhes de um pedido",
      "headers": {
        "Authorization": "Bearer {token}"
      },
      "response": {
        "status": 200,
        "body": {
          "id": "int",
          "user_id": "int",
          "status": "string",
          "total_amount": "decimal",
          "payment_status": "string",
          "shipping_address": "string",
          "created_at": "timestamp",
          "items": []
        }
      }
    },
    {
      "resource": "orders",
      "path": "/orders/{id}/status",
      "method": "PUT",
      "description": "Atualiza status de um pedido",
      "headers": {
        "Authorization": "Bearer {token}"
      },
      "request_body": {
        "status": "approved|sent|delivered|cancelled"
      },
      "response": {
        "status": 200,
        "body": {
          "id": "int",
          "status": "string",
          "updated_at": "timestamp"
        }
      }
    }
  ],
  "examples": [
    {
      "endpoint": "/auth/login",
      "method": "POST",
      "request": {
        "body": {
          "email": "admin@company.com",
          "password": "password123"
        }
      },
      "response": {
        "status": 200,
        "body": {
          "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
          "user": {
            "id": 1,
            "name": "Admin User",
            "email": "admin@company.com",
            "role": "admin"
          }
        }
      }
    }
  ],
  "total_endpoints": 8,
  "parsed_at": "2026-04-15T14:10:00Z"
}
```

---

### Passo 3: Geração de Intenção de Migração

**Consolidação de toda documentação:**
```python
# services/doc-ingestion/src/intention_generator.py

class IntentionGenerator:
    async def generate_migration_intention(self, parsed_docs: List[dict], legacy_info: dict, migration_targets: dict) -> dict:
        """
        Gera intenção de migração baseada em documentação parseada.
        """
        # Consolidar funcionalidades de todos os docs
        all_functionalities = []
        for doc in parsed_docs:
            functionalities = doc.get('functionalities', [])
            all_functionalities.extend(functionalities)
        
        # Consolidar requisitos
        all_requirements = []
        for doc in parsed_docs:
            frs = doc.get('functional_requirements', [])
            all_requirements.extend(frs)
        
        # Consolidar modelos de dados
        all_data_models = []
        for doc in parsed_docs:
            models = doc.get('data_models', [])
            all_data_models.extend(models)
        
        # Consolidar APIs
        all_endpoints = []
        for doc in parsed_docs:
            endpoints = doc.get('endpoints', [])
            all_endpoints.extend(endpoints)
        
        # Gerar intenção formatada
        intention = {
            "id": f"mig_int_{uuid.uuid4().hex[:8]}",
            "type": "migration",
            "legacy_system": legacy_info,
            "migration_targets": migration_targets,
            "functional_coverage": {
                "total_functionalities": len(all_functionalities),
                "covered": len(all_functionalities),
                "percentage": 100.0
            },
            "requirements": {
                "functional": all_requirements,
                "non_functional": parsed_docs[2].get('non_functional_requirements', [])
            },
            "data_models": all_data_models,
            "api_endpoints": all_endpoints,
            "integrations": parsed_docs[2].get('integrations', []),
            "estimated_complexity": await self._estimate_complexity(all_functionalities, all_data_models),
            "generated_at": datetime.utcnow().isoformat()
        }
        
        return intention
```

**Output Intenção de Migração:**
```json
{
  "id": "mig_int_a1b2c3d4",
  "type": "migration",
  "legacy_system": {
    "name": "Legacy E-commerce",
    "technology": "PHP 5.6",
    "database": "MySQL 5.5",
    "web_server": "Apache 2.2",
    "deployed_at": "2010-01-01",
    "architecture_type": "monolithic"
  },
  "migration_targets": {
    "target_language": "Python",
    "target_framework": "FastAPI",
    "target_database": "PostgreSQL",
    "target_architecture": "microservices"
  },
  "functional_coverage": {
    "total_functionalities": 15,
    "covered": 15,
    "percentage": 100.0
  },
  "requirements": {
    "functional": [
      {
        "id": "fr_001",
        "title": "Autenticação de Usuários",
        "description": "Sistema deve permitir login de usuários via email e senha",
        "priority": "critical",
        "acceptance_criteria": [
          "Usuário pode fazer login com credenciais válidas",
          "Sessão expira após 30 minutos de inatividade",
          "Senha deve ter mínimo 6 caracteres"
        ]
      },
      {
        "id": "fr_002",
        "title": "Catálogo de Produtos",
        "description": "Sistema deve exibir catálogo de produtos com busca e filtros",
        "priority": "high",
        "acceptance_criteria": [
          "Produtos listados com imagem, nome, preço",
          "Busca por nome de produto",
          "Filtro por categoria",
          "Filtro por faixa de preço"
        ]
      },
      {
        "id": "fr_003",
        "title": "Carrinho de Compras",
        "description": "Sistema deve permitir gerenciamento de carrinho de compras",
        "priority": "critical",
        "acceptance_criteria": [
          "Adicionar produtos ao carrinho",
          "Remover produtos do carrinho",
          "Alterar quantidade de itens",
          "Calcular total automaticamente",
          "Persistir carrinho na sessão"
        ]
      },
      {
        "id": "fr_004",
        "title": "Checkout e Pagamento",
        "description": "Sistema deve permitir finalização de compra com pagamento",
        "priority": "critical",
        "acceptance_criteria": [
          "Formulário de endereço de entrega",
          "Seleção de método de pagamento (cartão, boleto)",
          "Integração com gateway de pagamento",
          "Confirmação de pedido por email"
        ]
      },
      {
        "id": "fr_005",
        "title": "Gestão de Pedidos",
        "description": "Sistema deve permitir gerenciamento de pedidos por administradores",
        "priority": "high",
        "acceptance_criteria": [
          "Listar todos os pedidos",
          "Visualizar detalhes do pedido",
          "Atualizar status do pedido",
          "Cancelar pedido",
          "Gerar nota fiscal"
        ]
      }
    ],
    "non_functional": [
      {
        "id": "nfr_001",
        "category": "performance",
        "requirement": "Páginas devem carregar em menos de 3 segundos",
        "priority": "high"
      },
      {
        "id": "nfr_002",
        "category": "availability",
        "requirement": "Sistema deve ter 99% de disponibilidade",
        "priority": "high"
      },
      {
        "id": "nfr_003",
        "category": "security",
        "requirement": "Senhas devem ser armazenadas com hash (bcrypt)",
        "priority": "critical"
      },
      {
        "id": "nfr_004",
        "category": "scalability",
        "requirement": "Sistema deve suportar 1000 usuários simultâneos",
        "priority": "medium"
      }
    ]
  },
  "data_models": [
    {
      "name": "User",
      "source_table": "users",
      "fields": [
        {"name": "id", "type": "int", "primary_key": true},
        {"name": "name", "type": "str"},
        {"name": "email", "type": "str", "unique": true},
        {"name": "phone", "type": "str"},
        {"name": "address", "type": "str"},
        {"name": "role", "type": "enum"}
      ]
    },
    {
      "name": "Product",
      "source_table": "products",
      "fields": [
        {"name": "id", "type": "int", "primary_key": true},
        {"name": "name", "type": "str"},
        {"name": "description", "type": "str"},
        {"name": "price", "type": "decimal"},
        {"name": "stock", "type": "int"},
        {"name": "category_id", "type": "int"},
        {"name": "image_url", "type": "str"}
      ]
    },
    {
      "name": "Order",
      "source_table": "orders",
      "fields": [
        {"name": "id", "type": "int", "primary_key": true},
        {"name": "user_id", "type": "int"},
        {"name": "status", "type": "enum"},
        {"name": "total_amount", "type": "decimal"},
        {"name": "shipping_address", "type": "str"},
        {"name": "payment_method", "type": "enum"}
      ]
    },
    {
      "name": "OrderItem",
      "source_table": "order_items",
      "fields": [
        {"name": "id", "type": "int", "primary_key": true},
        {"name": "order_id", "type": "int"},
        {"name": "product_id", "type": "int"},
        {"name": "quantity", "type": "int"},
        {"name": "unit_price", "type": "decimal"},
        {"name": "subtotal", "type": "decimal"}
      ]
    },
    {
      "name": "Payment",
      "source_table": "payments",
      "fields": [
        {"name": "id", "type": "int", "primary_key": true},
        {"name": "order_id", "type": "int"},
        {"name": "amount", "type": "decimal"},
        {"name": "method", "type": "enum"},
        {"name": "status", "type": "enum"},
        {"name": "transaction_id", "type": "str"}
      ]
    }
  ],
  "api_endpoints": [
    {
      "resource": "auth",
      "path": "/auth/login",
      "method": "POST",
      "description": "Realiza login do usuário"
    },
    {
      "resource": "auth",
      "path": "/auth/logout",
      "method": "POST",
      "description": "Realiza logout do usuário"
    },
    {
      "resource": "products",
      "path": "/products",
      "method": "GET",
      "description": "Lista todos os produtos"
    },
    {
      "resource": "products",
      "path": "/products/{id}",
      "method": "GET",
      "description": "Obtém detalhes de um produto"
    },
    {
      "resource": "products",
      "path": "/products",
      "method": "POST",
      "description": "Cria um novo produto"
    },
    {
      "resource": "orders",
      "path": "/orders",
      "method": "POST",
      "description": "Cria um novo pedido"
    },
    {
      "resource": "orders",
      "path": "/orders/{id}",
      "method": "GET",
      "description": "Obtém detalhes de um pedido"
    },
    {
      "resource": "orders",
      "path": "/orders/{id}/status",
      "method": "PUT",
      "description": "Atualiza status de um pedido"
    }
  ],
  "integrations": [
    {
      "name": "Gateway de Pagamento",
      "type": "REST API",
      "provider": "PagSeguro",
      "description": "Processamento de pagamentos online"
    },
    {
      "name": "Envio de Emails",
      "type": "SMTP",
      "provider": "SendGrid",
      "description": "Envio de emails de confirmação"
    },
    {
      "name": "Geração de NF-e",
      "type": "SOAP API",
      "provider": "SEFAZ",
      "description": "Emissão de notas fiscais eletrônicas"
    }
  ],
  "estimated_complexity": {
    "level": "medium",
    "score": 0.65,
    "factors": [
      {"name": "number_of_entities", "value": 5, "impact": "medium"},
      {"name": "number_of_endpoints", "value": 8, "impact": "low"},
      {"name": "number_of_integrations", "value": 3, "impact": "medium"},
      {"name": "data_complexity", "value": "medium", "impact": "medium"}
    ]
  },
  "generated_at": "2026-04-15T14:12:00Z"
}
```

**Submissão ao Gateway Intenções:**
```bash
curl -X POST http://gateway-intencoes:8000/api/v1/intentions \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "mig_int_a1b2c3d4",
    "type": "migration",
    "intention": "Migrar sistema de e-commerce legado (PHP 5.6 + MySQL) para arquitetura moderna (Python + FastAPI + PostgreSQL + Microservices)",
    "context": {
      "legacy_system": "Legacy E-commerce",
      "migration_type": "modernization",
      "migration_targets": {
        "language": "Python",
        "framework": "FastAPI",
        "database": "PostgreSQL",
        "architecture": "microservices"
      }
    },
    "documentation_sources": [
      "user_manual.pdf",
      "technical_spec.docx",
      "database_schema.vsd",
      "api_collection.json"
    ],
    "derived_intention": {...}
  }'
```

---

### Passo 4: Tradução da Intenção (STE)

**Evento Kafka:** `intention.submitted`

**Payload Recebido:** (Intenção de migração acima)

**Processamento STE (Específico para Migração):**
```python
# services/semantic-translation-engine/src/translator.py

class MigrationIntentionTranslator:
    async def translate_migration_intention(self, intention_data: dict) -> dict:
        """
        Traduz intenção de migração para formato estruturado.
        """
        derived_intention = intention_data.get('derived_intention', {})
        legacy_system = derived_intention.get('legacy_system', {})
        migration_targets = intention_data.get('context', {}).get('migration_targets', {})
        
        # Análise NLU específica para migração
        entities = {
            "legacy_technology": legacy_system.get('technology'),
            "legacy_database": legacy_system.get('database'),
            "target_language": migration_targets.get('target_language'),
            "target_framework": migration_targets.get('target_framework'),
            "target_database": migration_targets.get('target_database'),
            "target_architecture": migration_targets.get('target_architecture')
        }
        
        # Classificar tipo de migração
        migration_type = await self._classify_migration_type(
            legacy_system, migration_targets
        )
        
        # Gerar estrutura formatada
        formatted_intention = {
            "id": f"fmt_{intention_data['id']}",
            "original_id": intention_data['id'],
            "primary_intent": "migrate_legacy_system",
            "secondary_intents": [
                "modernize_architecture",
                "migrate_data",
                "preserve_functionality",
                "improve_performance"
            ],
            "domain": "e-commerce",
            "migration_analysis": {
                "type": migration_type,
                "complexity": derived_intention.get('estimated_complexity', {}),
                "legacy_entities": len(derived_intention.get('data_models', [])),
                "legacy_endpoints": len(derived_intention.get('api_endpoints', [])),
                "integrations_to_migrate": len(derived_intention.get('integrations', []))
            },
            "entities": entities,
            "requirements": derived_intention.get('requirements', {}),
            "data_models": derived_intention.get('data_models', []),
            "api_design": derived_intention.get('api_endpoints', []),
            "integrations": derived_intention.get('integrations', []),
            "migration_strategy": await self._define_migration_strategy(
                legacy_system, migration_targets, derived_intention
            ),
            "data_migration_plan": await self._create_data_migration_plan(
                derived_intention.get('data_models', [])
            )
        }
        
        return formatted_intention
```

**Output STE (Migração):**
```json
{
  "id": "fmt_mig_int_a1b2c3d4",
  "original_id": "mig_int_a1b2c3d4",
  "primary_intent": "migrate_legacy_system",
  "secondary_intents": [
    "modernize_architecture",
    "migrate_data",
    "preserve_functionality",
    "improve_performance"
  ],
  "domain": "e-commerce",
  "migration_analysis": {
    "type": "technology_migration",
    "complexity": {
      "level": "medium",
      "score": 0.65
    },
    "legacy_entities": 5,
    "legacy_endpoints": 8,
    "integrations_to_migrate": 3
  },
  "entities": {
    "legacy_technology": "PHP 5.6",
    "legacy_database": "MySQL 5.5",
    "target_language": "Python",
    "target_framework": "FastAPI",
    "target_database": "PostgreSQL",
    "target_architecture": "microservices"
  },
  "requirements": {
    "functional": [
      {
        "id": "fr_001",
        "title": "Autenticação de Usuários",
        "description": "Sistema deve permitir login de usuários via email e senha",
        "priority": "critical"
      }
    ],
    "non_functional": [
      {
        "id": "nfr_001",
        "category": "performance",
        "requirement": "Páginas devem carregar em menos de 3 segundos",
        "priority": "high"
      }
    ]
  },
  "data_models": [
    {
      "name": "User",
      "source_table": "users",
      "fields": [
        {"name": "id", "type": "int", "primary_key": true},
        {"name": "name", "type": "str"},
        {"name": "email", "type": "str", "unique": true},
        {"name": "phone", "type": "str"},
        {"name": "address", "type": "str"},
        {"name": "role", "type": "enum"}
      ]
    }
  ],
  "api_design": [
    {
      "resource": "auth",
      "path": "/auth/login",
      "method": "POST",
      "description": "Realiza login do usuário"
    }
  ],
  "integrations": [
    {
      "name": "Gateway de Pagamento",
      "type": "REST API",
      "provider": "PagSeguro"
    }
  ],
  "migration_strategy": {
    "approach": "strangler_fig_pattern",
    "phases": [
      {
        "phase": 1,
        "name": "Preparação",
        "duration_weeks": 2,
        "activities": [
          "Configurar ambiente de desenvolvimento",
          "Criar estrutura de projetos microservices",
          "Configurar PostgreSQL e Kafka",
          "Criar scripts de data migration"
        ]
      },
      {
        "phase": 2,
        "name": "Migração de Autenticação",
        "duration_weeks": 3,
        "activities": [
          "Implementar user-service",
          "Migrar tabela users para PostgreSQL",
          "Implementar JWT authentication",
          "Criar API de auth"
        ]
      },
      {
        "phase": 3,
        "name": "Migração de Catálogo",
        "duration_weeks": 4,
        "activities": [
          "Implementar product-service",
          "Migrar tabelas products e categories",
          "Implementar API de produtos",
          "Migrar imagens para cloud storage"
        ]
      },
      {
        "phase": 4,
        "name": "Migração de Pedidos",
        "duration_weeks": 5,
        "activities": [
          "Implementar order-service",
          "Migrar tabelas orders e order_items",
          "Implementar API de pedidos",
          "Implementar carrinho com Redis"
        ]
      },
      {
        "phase": 5,
        "name": "Migração de Pagamentos",
        "duration_weeks": 3,
        "activities": [
          "Implementar payment-service",
          "Migrar tabela payments",
          "Integrar com PagSeguro",
          "Implementar webhooks de pagamento"
        ]
      },
      {
        "phase": 6,
        "name": "Cutover",
        "duration_weeks": 2,
        "activities": [
          "Validar dados migrados",
          "Performance testing",
          "Switch DNS para novo sistema",
          "Monitorar pós-migração"
        ]
      }
    ],
    "total_duration_weeks": 19
  },
  "data_migration_plan": {
    "source_database": "MySQL 5.5",
    "target_database": "PostgreSQL",
    "strategy": "incremental_migration",
    "tables": [
      {
        "source_table": "users",
        "target_table": "users",
        "mapping": {
          "id": "id",
          "name": "name",
          "email": "email",
          "password": "password_hash",
          "phone": "phone",
          "address": "address",
          "role": "role",
          "created_at": "created_at"
        },
        "transformations": [
          "Convert password hash to bcrypt",
          "Convert VARCHAR to UUID for id"
        ],
        "estimated_rows": 50000,
        "estimated_time_minutes": 30
      },
      {
        "source_table": "products",
        "target_table": "products",
        "mapping": {
          "id": "id",
          "name": "name",
          "description": "description",
          "price": "price",
          "stock": "stock",
          "category_id": "category_id",
          "image_url": "image_url",
          "created_at": "created_at",
          "updated_at": "updated_at"
        },
        "transformations": [
          "Convert VARCHAR URLs to cloud storage paths",
          "Convert DECIMAL to NUMERIC"
        ],
        "estimated_rows": 10000,
        "estimated_time_minutes": 20
      },
      {
        "source_table": "orders",
        "target_table": "orders",
        "mapping": {
          "id": "id",
          "user_id": "user_id",
          "status": "status",
          "total_amount": "total_amount",
          "shipping_address": "shipping_address",
          "payment_method": "payment_method",
          "payment_status": "payment_status",
          "created_at": "created_at",
          "updated_at": "updated_at"
        },
        "transformations": [
          "Convert ENUM to VARCHAR for compatibility"
        ],
        "estimated_rows": 500000,
        "estimated_time_minutes": 120
      }
    ],
    "total_estimated_rows": 560000,
    "total_estimated_time_hours": 3
  },
  "translated_at": "2026-04-15T14:15:00Z"
}
```

**Evento Kafka Produzido:** `intention.translated`

---

### Passo 5: Consenso entre Especialistas (Migração)

**Evento Kafka:** `intention.translated`

**Payload Recebido:** (Output do STE acima)

**Processamento Consensus Engine (Específico para Migração):**
```python
# services/consensus-engine/src/consensus_migration.py

class MigrationConsensusEngine:
    async def reach_migration_consensus(self, intention: dict) -> dict:
        """
        Coordena consenso entre especialistas para migração.
        """
        specialists = [
            "legacy_system_specialist",
            "migration_architect_specialist",
            "data_engineering_specialist",
            "security_specialist"
        ]
        
        # Obter opiniões de cada especialista
        specialist_opinions = []
        for specialist in specialists:
            opinion = await self._get_specialist_migration_opinion(
                specialist, intention
            )
            specialist_opinions.append(opinion)
        
        # Analisar convergências e divergências
        convergence_analysis = await self._analyze_migration_convergence(
            specialist_opinions
        )
        
        # Gerar plano consensual de migração
        consensus_plan = {
            "consensus_id": f"cons_{intention['id']}",
            "intention_id": intention['id'],
            "specialists_involved": specialists,
            "migration_approach": convergence_analysis.get('approach', 'unknown'),
            "convergence_score": convergence_analysis.get('score', 0.0),
            "agreed_upon_aspects": convergence_analysis.get('converged', []),
            "divergent_aspects": convergence_analysis.get('diverged', []),
            "resolution_strategy": await self._resolve_migration_divergences(
                convergence_analysis
            ),
            "proposed_migration_plan": await self._generate_migration_plan(
                intention, convergence_analysis
            ),
            "confidence_level": convergence_analysis.get('confidence', 0.5),
            "consensus_reached_at": datetime.utcnow().isoformat()
        }
        
        return consensus_plan
```

**Output Consensus Engine (Migração):**
```json
{
  "consensus_id": "cons_fmt_mig_int_a1b2c3d4",
  "intention_id": "fmt_mig_int_a1b2c3d4",
  "specialists_involved": [
    "legacy_system_specialist",
    "migration_architect_specialist",
    "data_engineering_specialist",
    "security_specialist"
  ],
  "migration_approach": "strangler_fig_pattern",
  "convergence_score": 0.91,
  "agreed_upon_aspects": [
    {
      "aspect": "migration_pattern",
      "value": "strangler_fig_pattern",
      "agreement_level": 1.0,
      "specialists": [
        "legacy_system_specialist",
        "migration_architect_specialist"
      ]
    },
    {
      "aspect": "target_architecture",
      "value": "microservices",
      "agreement_level": 0.95,
      "specialists": [
        "migration_architect_specialist",
        "data_engineering_specialist"
      ]
    },
    {
      "aspect": "data_migration_strategy",
      "value": "incremental_with_dual_write",
      "agreement_level": 0.93,
      "specialists": [
        "data_engineering_specialist",
        "security_specialist"
      ]
    },
    {
      "aspect": "authentication_migration",
      "value": "jwt_with_bcrypt_migration",
      "agreement_level": 1.0,
      "specialists": [
        "security_specialist",
        "migration_architect_specialist"
      ]
    }
  ],
  "divergent_aspects": [
    {
      "aspect": "payment_integration_strategy",
      "alternatives": [
        {
          "value": "direct_integration",
          "proponents": ["migration_architect_specialist"],
          "rationale": "Integração direta com PagSeguro API"
        },
        {
          "value": "wrapper_service",
          "proponents": ["legacy_system_specialist"],
          "rationale": "Wrapper service para gradual migration"
        }
      ],
      "resolution": "direct_integration (chosen for modern architecture and better performance)"
    }
  ],
  "resolution_strategy": {
    "strategy": "weighted_voting_with_expert_input",
    "weights": {
      "migration_architect_specialist": 0.35,
      "data_engineering_specialist": 0.25,
      "legacy_system_specialist": 0.25,
      "security_specialist": 0.15
    }
  },
  "proposed_migration_plan": {
    "architecture": {
      "pattern": "strangler_fig",
      "description": "Gradualmente substituir funcionalidades do sistema legado por novos microservices",
      "phases": [
        {
          "phase": 1,
          "name": "Foundation",
          "services": ["user-service", "gateway-service"],
          "duration_weeks": 2,
          "data_migration": ["users"]
        },
        {
          "phase": 2,
          "name": "Catalog Migration",
          "services": ["product-service", "category-service"],
          "duration_weeks": 4,
          "data_migration": ["products", "categories"]
        },
        {
          "phase": 3,
          "name": "Order Migration",
          "services": ["order-service", "cart-service"],
          "duration_weeks": 5,
          "data_migration": ["orders", "order_items"]
        },
        {
          "phase": 4,
          "name": "Payment Integration",
          "services": ["payment-service"],
          "duration_weeks": 3,
          "data_migration": ["payments"]
        }
      ]
    },
    "tech_stack": {
      "backend": {
        "framework": "FastAPI",
        "language": "Python 3.12+",
        "database": "PostgreSQL",
        "cache": "Redis",
        "message_queue": "Kafka"
      },
      "frontend": {
        "framework": "React",
        "language": "TypeScript",
        "state_management": "Redux Toolkit"
      },
      "infrastructure": {
        "containerization": "Docker",
        "orchestration": "Kubernetes",
        "ci_cd": "GitHub Actions",
        "cloud": "AWS"
      }
    },
    "data_layer": {
      "source_database": "MySQL 5.5",
      "target_database": "PostgreSQL",
      "migration_strategy": "incremental_with_dual_write",
      "sync_mechanism": "Change Data Capture (CDC)",
      "consistency_checks": "row_count_and_checksum_comparison"
    },
    "security": {
      "authentication": "JWT with refresh tokens",
      "authorization": "RBAC",
      "password_migration": "bcrypt rehash on next login",
      "session_management": "Redis with TTL"
    },
    "integrations": {
      "payment_gateway": {
        "provider": "PagSeguro",
        "integration_type": "REST API",
        "strategy": "direct_integration"
      },
      "email_service": {
        "provider": "SendGrid",
        "integration_type": "SMTP/API",
        "strategy": "keep_existing"
      },
      "invoice_generation": {
        "provider": "SEFAZ",
        "integration_type": "SOAP API",
        "strategy": "keep_existing"
      }
    },
    "rollback_plan": {
      "enabled": true,
      "strategy": "feature_flag_based_rollback",
      "rollback_points": [
        "end_of_each_phase",
        "after_data_migration",
        "after_cutover"
      ]
    }
  },
  "confidence_level": 0.89,
  "consensus_reached_at": "2026-04-15T14:20:00Z"
}
```

**Evento Kafka Produzido:** `consensus.reached`

---

### Passo 6 em diante - Mesmo Fluxo G

A partir daqui, o fluxo segue o mesmo padrão do Fluxo G:

1. **Requirements Engineering** → Gera requisitos baseados em documentação legada
2. **Architectural Planning** → Desenha arquitetura microservices com bounded contexts
3. **Agentic Delegation** → Decompõe plano em tarefas e atribui a agentes
4. **Code Forge** → Gera código Python/FastAPI baseado em templates de migração
5. **Test Generation** → Gera testes de migração (data integrity, backward compatibility)
6. **Documentation Generation** → Gera docs do novo sistema
7. **CI/CD Pipeline** → Build, test, deploy
8. **CI Feedback Loop** → Aprende com feedback

---

### Diferenças Chave entre Fluxo G e Fluxo H

| Aspecto | Fluxo G (Ideia → Software) | Fluxo H (Doc → Software) |
|---------|----------------------------|---------------------------|
| **Entrada** | Intenção de usuário | Documentação legada parseada |
| **Análise** | NLU de intenção | Extração de entidades de docs |
| **Estratégia** | De novo (greenfield) | Migração (brownfield) |
| **Código Legado** | Nenhum | PHP 5.6 + MySQL 5.5 |
| **Arquitetura Alvo** | Qualquer arquitetura | Modernização específica |
| **Dados** | Novos dados | Migração de dados existentes |
| **Integrações** | Novas integrações | Migração de integrações existentes |
| **Testes** | Funcionais | Funcionais + Data Integrity + Backward Compatibility |
| **Deploy** | Deploy direto | Cutover gradual com rollback |

---

## 📊 Sumário do Fluxo H

| Etapa | Sistema | Tempo | Eventos Kafka Produzidos |
|-------|---------|-------|---------------------------|
| 1 | Doc Ingestion | 300s | `intention.submitted` (via Gateway) |
| 2 | Semantic Translation Engine | 180s | `intention.translated` |
| 3 | Consensus Engine | 300s | `consensus.reached` |
| 4-10 | Mesmo Fluxo G | ~90 min | `requirements.generated` até `build.completed` |
| 11 | Data Migration | 180s | `data.migration.completed` |
| 12 | Cutover | 60s | `cutover.completed` |
| **Total** | | ~2.5 horas | **+ eventos Kafka** |

---

## 🎯 Pontos Chave do Fluxo H

1. **Ingestão Inteligente:** Parsea múltiplos formatos (PDF, Word, Visio, Postman)
2. **Extração de Entidades:** Identifica funcionalidades, requisitos, modelos de dados, APIs
3. **Estratégia de Migração:** Strangler Fig Pattern para migração gradual
4. **Preservação de Dados:** Plano detalhado de data migration com CDC
5. **Backward Compatibility:** Testes específicos para garantir compatibilidade
6. **Rollback Planejado:** Feature flags para rollback em caso de problemas
7. **Cutover Gradual:** Migração faseada com validação em cada fase

---

## Conclusão dos Fluxos G e H

Os fluxos G e H demonstram como o Neural-Hive-Mind pode automatizar completamente a criação de software:

- **Fluxo G:** De uma ideia simples até software deployado
- **Fluxo H:** Da documentação legada até sistema moderno migrado

Ambos os fluxos seguem a mesma arquitetura de sistemas, mas com estratégias diferentes adaptadas ao contexto:
- Fluxo G é ideal para **novos projetos** (greenfield)
- Fluxo H é ideal para **migrações** (brownfield)

A orquestração via Kafka permite:
- Desacoplamento entre sistemas
- Processamento paralelo onde possível
- Rastreamento completo de cada etapa
- Escalabilidade horizontal

O CI Feedback Loop permite aprendizado contínuo, melhorando a qualidade do software gerado ao longo do tempo.

---

## Documentação Completa

Este documento `INTEGRACAO_FLUXOS_SERVICOS_FALTANTES.md` agora contém:

1. **Parte 1:** Visão Geral dos Serviços Faltantes
2. **Parte 2:** Requirements Engineering System
3. **Parte 3:** Architectural Planning System
4. **Parte 4:** Agentic Delegation System
5. **Parte 5:** Code Forge (Melhorado)
6. **Parte 6:** Test Generation System
7. **Parte 7:** Documentation Generation System
8. **Parte 8:** CI Feedback Loop
9. **Parte 9:** Fluxo G Completo (Ideia → Software)
10. **Parte 10:** Fluxo H Completo (Documentação → Software)

**Total:** 10 partes, ~15.000 linhas, documentação completa de integração e fluxos.

---

*Documento criado em 2026-04-15*
*Versão: 1.0.0*
*Status: Completo*


---

## 📊 Comparação Detalhada de Todos os Fluxos

### Tabela Comparativa Geral

| Aspecto | Fluxo A | Fluxo B | Fluxo C | Fluxo D | Fluxo E | Fluxo F | Fluxo G | Fluxo H |
|---------|---------|---------|---------|---------|---------|---------|---------|---------|
| **Nome** | User Intent → NLU → Consensus | Requirements → Architecture | Architecture → Code | Code → Tests → Docs | Code → Deploy | Deploy → Feedback | Ideia → Software | Doc → Software |
| **Entrada** | Intenção de usuário (texto) | Plano consensual | Arquitetura desenhada | Código fonte gerado | Código + Testes | Sistema deployado | Ideia simples | Documentação legada |
| **Saída** | Plano consensual | Arquitetura definida | Tarefas atribuídas | Software completo | Software deployado | Insights de aprendizado | Software deployado | Software migrado |
| **Tipo** | NLU + Orquestração | Engenharia de requisitos | Agentic delegation | Engenharia de software | CI/CD | MLOps | End-to-End | Migração |
| **Caso de Uso** | Inicialização de projeto | Planejamento técnico | Decomposição de tarefas | Geração de artefatos | Deploy automático | Aprendizado contínuo | Criação de novo software | Modernização de sistema legado |
| **Complexidade** | Baixa | Média | Alta | Alta | Média | Alta | Muito Alta | Muito Alta |
| **Tempo** | 1-2 min | 5-10 min | 10-15 min | 30-45 min | 15-20 min | Contínuo | ~2 horas | ~2.5 horas |
| **Eventos Kafka** | 2 | 2 | 2 | 3 | 1 | 4 | 14 | 16 |
| **Determinístico** | Parcialmente | Sim | Sim | Sim | Sim | Não | Não | Não |
| **Requer Humano** | Não | Não | Não | Não | Não | Não | Não | Não |
| **Reversible** | Sim | Sim | Sim | Sim | Sim | Não | Não | Parcialmente |

---

### Comparação por Dimensão

#### 1. Fonte de Entrada

| Fluxo | Fonte de Entrada | Formato | Origem |
|-------|------------------|---------|---------|
| **Fluxo A** | Intenção de usuário | Texto natural | Humano via API |
| **Fluxo B** | Plano consensual | JSON | Fluxo A |
| **Fluxo C** | Arquitetura desenhada | JSON | Fluxo B |
| **Fluxo D** | Código fonte gerado | Arquivos de código | Fluxo C |
| **Fluxo E** | Código + Testes | Arquivos + JSON | Fluxo D |
| **Fluxo F** | Sistema deployado | Métricas/logs | Fluxo E |
| **Fluxo G** | Ideia simples | Texto natural | Humano via API |
| **Fluxo H** | Documentação legada | PDF, Word, Visio, Postman | Humano via API |

**Principais Diferenças:**
- **Fluxos A e G:** Entrada por texto natural (intenção/ideia)
- **Fluxo H:** Entrada por documentação estruturada (arquivos múltiplos)
- **Fluxos B-F:** Entrada por JSON/Arquivos (fluxo interno)
- **Fluxo H:** Único que aceita múltiplos formatos de documento

#### 2. Sistemas Envolvidos

| Fluxo | Sistemas Envolvidos | Quantidade | Novos vs Existentes |
|-------|-------------------|-----------|---------------------|
| **Fluxo A** | Gateway Intenções, STE, Consensus Engine | 3 | Todos existentes |
| **Fluxo B** | Requirements Engineering, Architectural Planning | 2 | Ambos NOVOS |
| **Fluxo C** | Architectural Planning, Agentic Delegation | 2 | Ambos NOVOS |
| **Fluxo D** | Code Forge, Test Generation, Documentation Generation | 3 | Code Forge existente, outros NOVOS |
| **Fluxo E** | Software Engineering Pipeline | 1 | Existente |
| **Fluxo F** | CI Feedback Loop | 1 | NOVO |
| **Fluxo G** | Todos os 7 sistemas | 7 | Combinação de todos |
| **Fluxo H** | Todos os 7 sistemas + Doc Ingestion | 8 | Combinação + Doc Ingestion NOVO |

**Principais Diferenças:**
- **Fluxos A, E:** Usam apenas sistemas existentes
- **Fluxos B-F:** Introduzem novos sistemas
- **Fluxos G, H:** Usam TODOS os sistemas
- **Fluxo H:** Único que adiciona Doc Ingestion Service

#### 3. Output por Fluxo

| Fluxo | Output Principal | Formato | Artefatos Gerados |
|-------|-----------------|---------|------------------|
| **Fluxo A** | Plano consensual | JSON | Plano técnico, prioridades |
| **Fluxo B** | Arquitetura definida | JSON + Diagramas | Bounded contexts, tech stack |
| **Fluxo C** | Tarefas atribuídas | JSON | Tarefas decompostas, agentes |
| **Fluxo D** | Software completo | Arquivos de código | Código, testes, documentação |
| **Fluxo E** | Software deployado | Docker images + K8s | Imagens, manifests, URL |
| **Fluxo F** | Insights de aprendizado | JSON | Políticas atualizadas, recomendações |
| **Fluxo G** | Software deployado | Sistema completo | Tudo do Fluxo E + monitoring |
| **Fluxo H** | Software migrado | Sistema completo | Tudo do Fluxo G + dados migrados |

**Principais Diferenças:**
- **Fluxos A-C:** Output são planos/desenhos (JSON)
- **Fluxo D:** Output são artefatos de software (código, testes, docs)
- **Fluxo E:** Output é software deployado (Docker, K8s)
- **Fluxo F:** Output são metadados de aprendizado (políticas, insights)
- **Fluxo G:** Output é sistema completo end-to-end
- **Fluxo H:** Output é sistema completo + dados migrados

#### 4. Tempo e Complexidade

| Fluxo | Tempo Estimado | Complexidade | Fatores de Complexidade |
|-------|---------------|--------------|------------------------|
| **Fluxo A** | 1-2 min | Baixa | NLU, consenso simples |
| **Fluxo B** | 5-10 min | Média | Engenharia de requisitos, arquitetura |
| **Fluxo C** | 10-15 min | Alta | Decomposição, atribuição de agentes |
| **Fluxo D** | 30-45 min | Alta | Geração de código, testes, docs |
| **Fluxo E** | 15-20 min | Média | Build, test, deploy |
| **Fluxo F** | Contínuo | Alta | Análise de feedback, ML |
| **Fluxo G** | ~2 horas | Muito Alta | Combina todos os fluxos |
| **Fluxo H** | ~2.5 horas | Muito Alta | Fluxo G + ingestão de docs + data migration |

**Principais Diferenças:**
- **Fluxos A-B:** Tempo em minutos (planejamento)
- **Fluxos C-D:** Tempo em dezenas de minutos (execução)
- **Fluxos E-F:** Tempo em minutos (CI/CD e aprendizado)
- **Fluxos G-H:** Tempo em horas (execução completa)
- **Fluxo H:** Mais lento devido a ingestão de docs + data migration

#### 5. Eventos Kafka por Fluxo

| Fluxo | Eventos Produzidos | Eventos Consumidos | Total | Bidirecional |
|-------|-------------------|-------------------|-------|--------------|
| **Fluxo A** | `intention.translated`, `consensus.reached` | `intention.submitted` | 3 | Sim |
| **Fluxo B** | `requirements.generated`, `architectural.plan` | `requirements.needed` | 3 | Sim |
| **Fluxo C** | `plan.decomposed`, `agents.assigned` | `architectural.plan` | 3 | Sim |
| **Fluxo D** | `code.generated`, `tests.generated`, `readme.generated`, `api_docs.generated`, `architecture_docs.generated`, `diagrams.generated` | `plan.decomposed`, `agents.assigned` | 8 | Sim |
| **Fluxo E** | `build.completed` | `code.generated`, `tests.generated`, `readme.generated` | 4 | Sim |
| **Fluxo F** | `feedback.collected`, `policy_updates.applied`, `autocorrections.applied`, `failures.analyzed`, `optimizations.suggested` | `build.completed` | 6 | Sim |
| **Fluxo G** | 14 eventos únicos | 14 eventos únicos | 28 | Sim |
| **Fluxo H** | 16 eventos únicos | 16 eventos únicos | 32 | Sim |

**Principais Diferenças:**
- **Fluxos A-C:** Poucos eventos (2-3)
- **Fluxo D:** Muitos eventos (6+)
- **Fluxos E-F:** Eventos específicos (1-5)
- **Fluxos G-H:** Muitos eventos (14-16)
- **Fluxo H:** +2 eventos (`data.migration.completed`, `cutover.completed`)

#### 6. Casos de Uso Específicos

| Fluxo | Caso de Uso Ideal | Quando Usar | Exemplo |
|-------|-------------------|-------------|---------|
| **Fluxo A** | Inicialização rápida | Nova ideia, conceito inicial | "Quero um app de delivery" |
| **Fluxo B** | Planejamento técnico | Definir arquitetura e requisitos | Projeto em fase de design |
| **Fluxo C** | Decomposição de tarefas | Dividir trabalho entre agentes | Projeto complexo com múltiplas partes |
| **Fluxo D** | Geração de artefatos | Criar código, testes, docs automaticamente | Bootstrapping de projeto |
| **Fluxo E** | Deploy automatizado | Deployar para produção | PR merge → deploy |
| **Fluxo F** | Aprendizado contínuo | Melhorar qualidade ao longo do tempo | Ciclos de CI/CD |
| **Fluxo G** | Criação completa de software | Ideia → software deployado | Startup criando MVP |
| **Fluxo H** | Modernização de legado | Migração de sistemas antigos | PHP → Python, monolito → microservices |

**Principais Diferenças:**
- **Fluxos A-C:** Casos de uso iniciais (planejamento)
- **Fluxos D-E:** Casos de uso de execução (geração, deploy)
- **Fluxo F:** Caso de uso de otimização (aprendizado)
- **Fluxo G:** Caso de uso completo (greenfield)
- **Fluxo H:** Caso de uso de migração (brownfield)

#### 7. Dependências entre Fluxos

```mermaid
graph TD
    A[Fluxo A: User Intent] --> B[Fluxo B: Requirements]
    B --> C[Fluxo C: Agentic Delegation]
    C --> D[Fluxo D: Code + Tests + Docs]
    D --> E[Fluxo E: CI/CD Deploy]
    E --> F[Fluxo F: CI Feedback Loop]
    F -.->|políticas atualizadas| C
    F -.->|insights| D
    
    G[Fluxo G: Ideia → Software] --> A
    G --> B
    G --> C
    G --> D
    G --> E
    G --> F
    
    H[Fluxo H: Doc → Software] --> A
    H --> B
    H --> C
    H --> D
    H --> E
    H --> F
    H -->|data migration| M[Data Migration]
    
    style A fill:#e1f5ff
    style G fill:#fff4e1
    style H fill:#ffe1f5
    style M fill:#e1ffe1
```

**Principais Diferenças:**
- **Fluxos A-F:** Dependência linear (A→B→C→D→E→F)
- **Fluxo G:** Combina todos os fluxos (A+B+C+D+E+F)
- **Fluxo H:** Combina todos + Data Migration
- **Fluxo F:** Loop de feedback que afeta Fluxos C e D

#### 8. Reversibilidade e Rollback

| Fluxo | Reversível | Estratégia de Rollback | Custo de Rollback |
|-------|------------|----------------------|-------------------|
| **Fluxo A** | Sim | Re-submeter intenção | Baixo |
| **Fluxo B** | Sim | Re-gerar requisitos | Baixo |
| **Fluxo C** | Sim | Re-decompor tarefas | Médio |
| **Fluxo D** | Sim | Re-gerar código | Médio |
| **Fluxo E** | Sim | Deploy versão anterior | Médio-Alto |
| **Fluxo F** | Não | Aprendizado é acumulativo | N/A |
| **Fluxo G** | Não | Múltiplas etapas | Alto |
| **Fluxo H** | Parcialmente | Cutover com rollback | Muito Alto |

**Principais Diferenças:**
- **Fluxos A-E:** Reversível (re-execução possível)
- **Fluxo F:** Não reversível (aprendizado acumulativo)
- **Fluxos G-H:** Difícil de reverter (múltiplas etapas)
- **Fluxo H:** Mais complexo rollback (data migration)

#### 9. Envio Humano Necessário

| Fluxo | Requer Humano | Em Qual Etapa | Tipo de Intervenção |
|-------|---------------|---------------|-------------------|
| **Fluxo A** | Não | Nenhuma | N/A |
| **Fluxo B** | Não | Nenhuma | N/A |
| **Fluxo C** | Não | Nenhuma | N/A |
| **Fluxo D** | Não | Nenhuma | N/A |
| **Fluxo E** | Opcional | Approval | Aprovação de PR |
| **Fluxo F** | Não | Nenhuma | N/A |
| **Fluxo G** | Não | Nenhuma | N/A |
| **Fluxo H** | Opcional | Cutover | Validação de migração |

**Principais Diferenças:**
- **Fluxos A-D, F, G:** Totalmente automáticos
- **Fluxo E:** Opcional (approval)
- **Fluxo H:** Opcional (validação de cutover)
- **Todos os fluxos:** Podem ser 100% automáticos se configurados

#### 10. Determinismo vs Probabilístico

| Fluxo | Determinístico | Probabilístico | Fatores de Incerteza |
|-------|---------------|----------------|---------------------|
| **Fluxo A** | Parcialmente | Sim | NLU do STE, consenso |
| **Fluxo B** | Sim | Não | Requisitos bem definidos |
| **Fluxo C** | Sim | Não | Tarefas baseadas em regras |
| **Fluxo D** | Parcialmente | Sim | Geração de código por LLM |
| **Fluxo E** | Sim | Não | Pipeline determinístico |
| **Fluxo F** | Não | Sim | Aprendizado por RL |
| **Fluxo G** | Não | Sim | Combinação de fluxos incertos |
| **Fluxo H** | Não | Sim | Parseamento de docs + fluxo G |

**Principais Diferenças:**
- **Fluxos B, C, E:** Determinísticos (outputs previsíveis)
- **Fluxos A, D:** Parcialmente determinísticos (LLM envolvido)
- **Fluxos F, G, H:** Probabilísticos (ML/LLM intensivo)

---

### Comparação de Uso de Recursos

#### 1. Uso de LLM/ML

| Fluxo | Uso de LLM | Uso de ML | Sistemas |
|-------|-----------|-----------|-----------|
| **Fluxo A** | Alto | Baixo | STE, Consensus Engine |
| **Fluxo B** | Médio | Baixo | Requirements Engineering, Architectural Planning |
| **Fluxo C** | Baixo | Médio | Agentic Delegation (fitness scoring) |
| **Fluxo D** | Muito Alto | Baixo | Code Forge (RAG + LLM), Test Gen, Docs Gen |
| **Fluxo E** | Nenhum | Nenhum | Software Engineering Pipeline |
| **Fluxo F** | Baixo | Muito Alto | CI Feedback Loop (Reinforcement Learning) |
| **Fluxo G** | Muito Alto | Alto | Todos os sistemas |
| **Fluxo H** | Muito Alto | Alto | Todos + Doc Ingestion (NLP) |

**Principais Diferenças:**
- **Fluxo D:** Mais uso de LLM (geração de código)
- **Fluxo F:** Mais uso de ML (reinforcement learning)
- **Fluxo H:** Adiciona NLP para parseamento de docs
- **Fluxo E:** Sem uso de LLM/ML (CI/CD puro)

#### 2. Uso de Knowledge Graph/RAG

| Fluxo | Usa Knowledge Graph | Usa RAG | Casos de Uso |
|-------|-------------------|----------|--------------|
| **Fluxo A** | Não | Não | N/A |
| **Fluxo B** | Sim | Sim | Buscar bounded contexts similares |
| **Fluxo C** | Não | Não | N/A |
| **Fluxo D** | Sim | Sim | Buscar templates e código similar |
| **Fluxo E** | Não | Não | N/A |
| **Fluxo F** | Não | Não | N/A |
| **Fluxo G** | Sim | Sim | Combina B e D |
| **Fluxo H** | Sim | Sim | Combina B, D + RAG em docs |

**Principais Diferenças:**
- **Fluxos B, D, G, H:** Usam Knowledge Graph e RAG
- **Fluxos A, C, E, F:** Não usam Knowledge Graph
- **Fluxo H:** RAG mais complexo (docs legados + código + templates)

#### 3. Uso de Kafka

| Fluxo | Tópicos Produzidos | Tópicos Consumidos | Padrão de Comunicação |
|-------|-------------------|-------------------|----------------------|
| **Fluxo A** | 2 | 1 | Request-Response |
| **Fluxo B** | 2 | 1 | Request-Response |
| **Fluxo C** | 2 | 1 | Request-Response |
| **Fluxo D** | 6 | 2 | Broadcast |
| **Fluxo E** | 1 | 3 | Agregação |
| **Fluxo F** | 5 | 1 | Broadcast |
| **Fluxo G** | 14 | 14 | Event Sourcing |
| **Fluxo H** | 16 | 16 | Event Sourcing + CDC |

**Principais Diferenças:**
- **Fluxos A-C:** Comunicação simples (1:1)
- **Fluxo D:** Broadcast (múltiplos consumidores)
- **Fluxo E:** Agregação (múltiplos produtores → 1 consumidor)
- **Fluxo F:** Broadcast (feedback para múltiplos sistemas)
- **Fluxos G-H:** Event Sourcing (eventos de domínio)
- **Fluxo H:** + CDC (Change Data Capture)

#### 4. Uso de Banco de Dados

| Fluxo | Escreve BD | Lê BD | Tipo de BD |
|-------|-----------|--------|------------|
| **Fluxo A** | Não | Não | N/A |
| **Fluxo B** | Sim | Sim | MongoDB (specs), Neo4j (KG) |
| **Fluxo C** | Sim | Sim | MongoDB (tarefas) |
| **Fluxo D** | Não | Sim | Neo4j (templates/código) |
| **Fluxo E** | Não | Não | N/A |
| **Fluxo F** | Sim | Sim | MongoDB (feedback), Redis (políticas) |
| **Fluxo G** | Sim | Sim | Todos acima |
| **Fluxo H** | Sim | Sim | Todos + PostgreSQL (dados migrados) |

**Principais Diferenças:**
- **Fluxos B, C, F:** Escrevem metadados (specs, tarefas, feedback)
- **Fluxo D:** Apenas lê Knowledge Graph
- **Fluxo E:** Não usa banco (apenas Docker/K8s)
- **Fluxos G, H:** Leem e escrevem todos os bancos
- **Fluxo H:** +Escreve dados de produção (PostgreSQL)

---

### Comparação de Qualidade e Métricas

#### 1. Métricas de Sucesso

| Fluxo | Métricas de Sucesso | Como Medir | Thresholds |
|-------|---------------------|-------------|-----------|
| **Fluxo A** | Tempo de consenso, convergência | Logs, eventos | <2 min, >0.8 convergência |
| **Fluxo B** | Cobertura de requisitos, aderência | Análise de specs | >90% cobertura |
| **Fluxo C** | Taxa de atribuição, fitness | Status de tarefas | 100% atribuídas, >0.7 fitness |
| **Fluxo D** | Qualidade do código, coverage | Lint, testes | Lint 100%, coverage >80% |
| **Fluxo E** | Status do build, tempo | Pipeline status | Success, <20 min |
| **Fluxo F** | Melhoria de qualidade ao longo do tempo | Histórico de scores | Tendência positiva |
| **Fluxo G** | Software funcional, deployado | E2E tests, uptime | Testes passando, 99%+ uptime |
| **Fluxo H** | Migração completa, dados consistentes | Data validation | 100% dados migrados, 0 corrupção |

#### 2. Pontos de Falha Potenciais

| Fluxo | Pontos de Falha | Probabilidade | Impacto |
|-------|------------------|---------------|----------|
| **Fluxo A** | NLU mal interpreta intenção | Média | Plano incorreto |
| **Fluxo B** | Requisitos incompletos | Baixa | Arquitetura insuficiente |
| **Fluxo C** | Agentes não disponíveis | Baixa-Média | Tarefas não executadas |
| **Fluxo D** | LLM gera código com bugs | Alta | Software não funcional |
| **Fluxo E** | Build falha | Média | Deploy não acontece |
| **Fluxo F** | Feedback negativo deteriora políticas | Baixa | Qualidade cai |
| **Fluxo G** | Múltiplas falhas em cascata | Média-Alta | Sistema não entregue |
| **Fluxo H** | Data migration corrompe dados | Média-Alta | Perda de dados |

#### 3. Estratégias de Mitigação

| Fluxo | Estratégia de Mitigação | Implementação |
|-------|-----------------------|----------------|
| **Fluxo A** | Validação de intenção antes do consenso | Gateway Intenções |
| **Fluxo B** | Revisão de requisitos por especialistas | Consensus Engine |
| **Fluxo C** | Pool de agentes com backup | Agentic Delegation |
| **Fluxo D** | Validação de código + testes automáticos | Test Generation + Lint |
| **Fluxo E** | Canaries e rollbacks | Software Engineering Pipeline |
| **Fluxo F** | Thresholds mínimos de qualidade | CI Feedback Loop |
| **Fluxo G** | Checkpoints em cada etapa | Orchestrator Dynamic |
| **Fluxo H** | Data validation + rollback capability | Data Migration + Cutover |

---

### Comparação de Custos

#### 1. Custos Computacionais

| Fluxo | Custo de LLM | Custo de ML | Custo de BD | Custo de Infra | Custo Total |
|-------|--------------|-------------|-------------|---------------|-------------|
| **Fluxo A** | $0.05 | $0.01 | $0.00 | $0.01 | $0.07 |
| **Fluxo B** | $0.20 | $0.02 | $0.05 | $0.02 | $0.29 |
| **Fluxo C** | $0.10 | $0.10 | $0.05 | $0.02 | $0.27 |
| **Fluxo D** | $5.00 | $0.05 | $0.10 | $0.10 | $5.25 |
| **Fluxo E** | $0.00 | $0.00 | $0.00 | $2.00 | $2.00 |
| **Fluxo F** | $0.50 | $1.00 | $0.10 | $0.50 | $2.10 |
| **Fluxo G** | $6.00 | $1.20 | $0.30 | $2.70 | $10.20 |
| **Fluxo H** | $6.50 | $1.30 | $0.50 | $3.50 | $11.80 |

**Principais Diferenças:**
- **Fluxo D:** Maior custo de LLM (geração de código extensiva)
- **Fluxo E:** Maior custo de infra (Docker, K8s)
- **Fluxo F:** Maior custo de ML (reinforcement learning)
- **Fluxos G, H:** Custos acumulados de todos os fluxos
- **Fluxo H:** +$1.60 devido a ingestão de docs + data migration

#### 2. Custos de Tempo

| Fluxo | Tempo de Desenvolvimento | Tempo de Execução | Tempo Total |
|-------|------------------------|------------------|-------------|
| **Fluxo A** | 0 min (automático) | 1-2 min | 1-2 min |
| **Fluxo B** | 0 min (automático) | 5-10 min | 5-10 min |
| **Fluxo C** | 0 min (automático) | 10-15 min | 10-15 min |
| **Fluxo D** | 0 min (automático) | 30-45 min | 30-45 min |
| **Fluxo E** | 0 min (automático) | 15-20 min | 15-20 min |
| **Fluxo F** | 0 min (automático) | Contínuo | N/A |
| **Fluxo G** | 0 min (automático) | ~2 horas | ~2 horas |
| **Fluxo H** | 0 min (automático) | ~2.5 horas | ~2.5 horas |

**Principais Diferenças:**
- **Fluxos A-E:** Tempo em minutos (únicos)
- **Fluxo F:** Tempo contínuo (aprendizado)
- **Fluxos G, H:** Tempo em horas (end-to-end)
- **Fluxo H:** +30 min devido a ingestão de docs + data migration

---

### Conclusão da Comparação

**Fluxos por Categoria:**

1. **Fluxos Iniciais (A-B):** Planejamento e desenho
   - Baixa complexidade
   - Tempo em minutos
   - Custo baixo
   - Outputs são planos

2. **Fluxos de Execução (C-D):** Decomposição e geração
   - Alta complexidade
   - Tempo em dezenas de minutos
   - Custo médio
   - Outputs são tarefas/código

3. **Fluxos de Deploy (E-F):** CI/CD e aprendizado
   - Média-Alta complexidade
   - Tempo em minutos (contínuo para F)
   - Custo médio-alto
   - Outputs são deploy/insights

4. **Fluxos End-to-End (G-H):** Completo
   - Muito alta complexidade
   - Tempo em horas
   - Custo alto
   - Outputs são sistemas completos

**Fluxo G vs Fluxo H:**

- **Semelhantes:** Ambos usam todos os sistemas, são end-to-end, automáticos
- **Diferença principal:** Entrada (ideia vs documentação)
- **Fluxo G:** Ideal para greenfield (novo software)
- **Fluxo H:** Ideal para brownfield (modernização de legado)
- **Fluxo H:** +Doc Ingestion + Data Migration + Cutover

**Recomendações de Uso:**

- Use **Fluxo G** para criar novos produtos do zero
- Use **Fluxo H** para modernizar sistemas legados
- Use **Fluxos A-F individualmente** para casos específicos
- Use **Fluxo F** continuamente para melhorar qualidade ao longo do tempo

Todos os fluxos são 100% automatizados, não requerem intervenção humana, e podem ser executados em paralelo para múltiplos projetos.

---


---

## 📊 Comparação Detalhada de Todos os Fluxos

### Tabela Comparativa Geral

| Aspecto | Fluxo A | Fluxo B | Fluxo C | Fluxo D | Fluxo E | Fluxo F | Fluxo G | Fluxo H |
|---------|---------|---------|---------|---------|---------|---------|---------|---------|
| **Nome** | User Intent → NLU → Consensus | Requirements → Architecture | Architecture → Code | Code → Tests → Docs | Code → Deploy | Deploy → Feedback | Ideia → Software | Doc → Software |
| **Entrada** | Intenção de usuário (texto) | Plano consensual | Arquitetura desenhada | Código fonte gerado | Código + Testes | Sistema deployado | Ideia simples | Documentação legada |
| **Saída** | Plano consensual | Arquitetura definida | Tarefas atribuídas | Software completo | Software deployado | Insights de aprendizado | Software deployado | Software migrado |
| **Tipo** | NLU + Orquestração | Engenharia de requisitos | Agentic delegation | Engenharia de software | CI/CD | MLOps | End-to-End | Migração |
| **Caso de Uso** | Inicialização de projeto | Planejamento técnico | Decomposição de tarefas | Geração de artefatos | Deploy automático | Aprendizado contínuo | Criação de novo software | Modernização de sistema legado |
| **Complexidade** | Baixa | Média | Alta | Alta | Média | Alta | Muito Alta | Muito Alta |
| **Tempo** | 1-2 min | 5-10 min | 10-15 min | 30-45 min | 15-20 min | Contínuo | ~2 horas | ~2.5 horas |
| **Eventos Kafka** | 2 | 2 | 2 | 3 | 1 | 4 | 14 | 16 |
| **Determinístico** | Parcialmente | Sim | Sim | Sim | Sim | Não | Não | Não |
| **Requer Humano** | Não | Não | Não | Não | Não | Não | Não | Não |
| **Reversible** | Sim | Sim | Sim | Sim | Sim | Não | Não | Parcialmente |

---

### Comparação por Dimensão

#### 1. Fonte de Entrada

| Fluxo | Fonte de Entrada | Formato | Origem |
|-------|------------------|---------|---------|
| **Fluxo A** | Intenção de usuário | Texto natural | Humano via API |
| **Fluxo B** | Plano consensual | JSON | Fluxo A |
| **Fluxo C** | Arquitetura desenhada | JSON | Fluxo B |
| **Fluxo D** | Código fonte gerado | Arquivos de código | Fluxo C |
| **Fluxo E** | Código + Testes | Arquivos + JSON | Fluxo D |
| **Fluxo F** | Sistema deployado | Métricas/logs | Fluxo E |
| **Fluxo G** | Ideia simples | Texto natural | Humano via API |
| **Fluxo H** | Documentação legada | PDF, Word, Visio, Postman | Humano via API |

#### 2. Sistemas Envolvidos

| Fluxo | Sistemas Envolvidos | Quantidade | Novos vs Existentes |
|-------|-------------------|-----------|---------------------|
| **Fluxo A** | Gateway Intenções, STE, Consensus Engine | 3 | Todos existentes |
| **Fluxo B** | Requirements Engineering, Architectural Planning | 2 | Ambos NOVOS |
| **Fluxo C** | Architectural Planning, Agentic Delegation | 2 | Ambos NOVOS |
| **Fluxo D** | Code Forge, Test Generation, Documentation Generation | 3 | Code Forge existente, outros NOVOS |
| **Fluxo E** | Software Engineering Pipeline | 1 | Existente |
| **Fluxo F** | CI Feedback Loop | 1 | NOVO |
| **Fluxo G** | Todos os 7 sistemas | 7 | Combinação de todos |
| **Fluxo H** | Todos os 7 sistemas + Doc Ingestion | 8 | Combinação + Doc Ingestion NOVO |

#### 3. Output por Fluxo

| Fluxo | Output Principal | Formato | Artefatos Gerados |
|-------|-----------------|---------|------------------|
| **Fluxo A** | Plano consensual | JSON | Plano técnico, prioridades |
| **Fluxo B** | Arquitetura definida | JSON + Diagramas | Bounded contexts, tech stack |
| **Fluxo C** | Tarefas atribuídas | JSON | Tarefas decompostas, agentes |
| **Fluxo D** | Software completo | Arquivos de código | Código, testes, documentação |
| **Fluxo E** | Software deployado | Docker images + K8s | Imagens, manifests, URL |
| **Fluxo F** | Insights de aprendizado | JSON | Políticas atualizadas, recomendações |
| **Fluxo G** | Software deployado | Sistema completo | Tudo do Fluxo E + monitoring |
| **Fluxo H** | Software migrado | Sistema completo | Tudo do Fluxo G + dados migrados |

#### 4. Tempo e Complexidade

| Fluxo | Tempo Estimado | Complexidade | Fatores de Complexidade |
|-------|---------------|--------------|------------------------|
| **Fluxo A** | 1-2 min | Baixa | NLU, consenso simples |
| **Fluxo B** | 5-10 min | Média | Engenharia de requisitos, arquitetura |
| **Fluxo C** | 10-15 min | Alta | Decomposição, atribuição de agentes |
| **Fluxo D** | 30-45 min | Alta | Geração de código, testes, docs |
| **Fluxo E** | 15-20 min | Média | Build, test, deploy |
| **Fluxo F** | Contínuo | Alta | Análise de feedback, ML |
| **Fluxo G** | ~2 horas | Muito Alta | Combina todos os fluxos |
| **Fluxo H** | ~2.5 horas | Muito Alta | Fluxo G + ingestão de docs + data migration |

#### 5. Eventos Kafka por Fluxo

| Fluxo | Eventos Produzidos | Eventos Consumidos | Total | Bidirecional |
|-------|-------------------|-------------------|-------|--------------|
| **Fluxo A** | `intention.translated`, `consensus.reached` | `intention.submitted` | 3 | Sim |
| **Fluxo B** | `requirements.generated`, `architectural.plan` | `requirements.needed` | 3 | Sim |
| **Fluxo C** | `plan.decomposed`, `agents.assigned` | `architectural.plan` | 3 | Sim |
| **Fluxo D** | `code.generated`, `tests.generated`, `readme.generated`, `api_docs.generated`, `architecture_docs.generated`, `diagrams.generated` | `plan.decomposed`, `agents.assigned` | 8 | Sim |
| **Fluxo E** | `build.completed` | `code.generated`, `tests.generated`, `readme.generated` | 4 | Sim |
| **Fluxo F** | `feedback.collected`, `policy_updates.applied`, `autocorrections.applied`, `failures.analyzed`, `optimizations.suggested` | `build.completed` | 6 | Sim |
| **Fluxo G** | 14 eventos únicos | 14 eventos únicos | 28 | Sim |
| **Fluxo H** | 16 eventos únicos | 16 eventos únicos | 32 | Sim |

#### 6. Casos de Uso Específicos

| Fluxo | Caso de Uso Ideal | Quando Usar | Exemplo |
|-------|-------------------|-------------|---------|
| **Fluxo A** | Inicialização rápida | Nova ideia, conceito inicial | "Quero um app de delivery" |
| **Fluxo B** | Planejamento técnico | Definir arquitetura e requisitos | Projeto em fase de design |
| **Fluxo C** | Decomposição de tarefas | Dividir trabalho entre agentes | Projeto complexo com múltiplas partes |
| **Fluxo D** | Geração de artefatos | Criar código, testes, docs automaticamente | Bootstrapping de projeto |
| **Fluxo E** | Deploy automatizado | Deployar para produção | PR merge → deploy |
| **Fluxo F** | Aprendizado contínuo | Melhorar qualidade ao longo do tempo | Ciclos de CI/CD |
| **Fluxo G** | Criação completa de software | Ideia → software deployado | Startup criando MVP |
| **Fluxo H** | Modernização de legado | Migração de sistemas antigos | PHP → Python, monolito → microservices |

---

### Fluxo G vs Fluxo H: Diferenças Principais

| Aspecto | Fluxo G | Fluxo H |
|---------|---------|---------|
| **Entrada** | Ideia simples (texto) | Documentação legada (PDF, Word, Visio, Postman) |
| **Estratégia** | De novo (greenfield) | Migração (brownfield) |
| **Código Legado** | Nenhum | PHP 5.6 + MySQL 5.5 |
| **Arquitetura Alvo** | Qualquer arquitetura | Modernização específica |
| **Dados** | Novos dados | Migração de dados existentes |
| **Integrações** | Novas integrações | Migração de integrações existentes |
| **Testes** | Funcionais | Funcionais + Data Integrity + Backward Compatibility |
| **Deploy** | Deploy direto | Cutover gradual com rollback |
| **Sistemas Extras** | Nenhum | Doc Ingestion Service (NOVO) |
| **Tempo** | ~2 horas | ~2.5 horas |
| **Eventos Kafka** | 14 | 16 (+ data.migration.completed, cutover.completed) |
| **Complexidade** | Muito Alta | Muito Alta + ingestão de docs |
| **Custo** | ~$10.20 | ~$11.80 (+ Doc Ingestion + Data Migration) |
| **Padrão** | Criar do zero | Strangler Fig Pattern |

---

### Conclusão da Comparação

**Fluxos por Categoria:**

1. **Fluxos Iniciais (A-B):** Planejamento e desenho
   - Baixa complexidade
   - Tempo em minutos
   - Custo baixo
   - Outputs são planos

2. **Fluxos de Execução (C-D):** Decomposição e geração
   - Alta complexidade
   - Tempo em dezenas de minutos
   - Custo médio
   - Outputs são tarefas/código

3. **Fluxos de Deploy (E-F):** CI/CD e aprendizado
   - Média-Alta complexidade
   - Tempo em minutos (contínuo para F)
   - Custo médio-alto
   - Outputs são deploy/insights

4. **Fluxos End-to-End (G-H):** Completo
   - Muito alta complexidade
   - Tempo em horas
   - Custo alto
   - Outputs são sistemas completos

**Fluxo G vs Fluxo H:**

- **Semelhantes:** Ambos usam todos os sistemas, são end-to-end, automáticos
- **Diferença principal:** Entrada (ideia vs documentação)
- **Fluxo G:** Ideal para greenfield (novo software)
- **Fluxo H:** Ideal para brownfield (modernização de legado)
- **Fluxo H:** +Doc Ingestion + Data Migration + Cutover

**Recomendações de Uso:**

- Use **Fluxo G** para criar novos produtos do zero
- Use **Fluxo H** para modernizar sistemas legados
- Use **Fluxos A-F individualmente** para casos específicos
- Use **Fluxo F** continuamente para melhorar qualidade ao longo do tempo

Todos os fluxos são 100% automatizados, não requerem intervenção humana, e podem ser executados em paralelo para múltiplos projetos.

---



---


---

## 📊 Nota Importante

A **análise comparativa detalhada de todos os fluxos** (A-H) foi separada em um documento independente para facilitar a consulta e manter o foco deste documento na integração e fluxos dos serviços faltantes.

### Documento de Análise de Fluxos

📄 **Arquivo:** `docs/ANALISE_FLUXOS.md`
📊 **Conteúdo:** Análise comparativa completa dos 8 fluxos do Neural-Hive-Mind

**Conteúdo do Documento:**

1. **Tabela Comparativa Geral**
   - Comparação lado a lado de todos os fluxos
   - 12 dimensões comparadas

2. **Comparação por Dimensão**
   - Fonte de entrada (texto vs docs)
   - Sistemas envolvidos (existentes vs novos)
   - Outputs (planos vs código vs deploy)
   - Tempo e complexidade (minutos vs horas)
   - Eventos Kafka (2-16 eventos)
   - Casos de uso (iniciais vs completos)
   - Dependências (lineares vs combinados)
   - Reversibilidade e rollback
   - Intervenção humana (totalmente automático)
   - Determinismo vs probabilismo

3. **Comparação de Uso de Recursos**
   - Uso de LLM/ML por fluxo
   - Uso de Knowledge Graph/RAG
   - Uso de Kafka (padrões de comunicação)
   - Uso de banco de dados (MongoDB, Neo4j, PostgreSQL, Redis)

4. **Comparação de Qualidade e Métricas**
   - Métricas de sucesso por fluxo
   - Pontos de falha potenciais
   - Estratégias de mitigação

5. **Comparação de Custos**
   - Custos computacionais (LLM, ML, BD, infra)
   - Custos de tempo (desenvolvimento vs execução)

6. **Fluxo G vs Fluxo H: Diferenças Principais**
   - Tabela comparativa detalhada
   - Entrada (ideia vs documentação)
   - Estratégia (greenfield vs brownfield)
   - Dados (novos vs migrados)
   - Testes (funcionais vs data integrity)
   - Deploy (direto vs cutover)

7. **Recomendações de Uso**
   - Qual fluxo usar em cada situação
   - Casos de uso ideais por fluxo

### Por que Separar?

✅ **Foco:** Este documento mantém foco na integração e fluxos dos serviços faltantes
✅ **Organização:** Análise comparativa fica em documento dedicado
✅ **Manutenibilidade:** Mais fácil atualizar e consultar
✅ **Clareza:** Cada documento tem propósito único

---

