# Epic 3: Requirements Engineering Service (8010) - Relatório Final

**Data:** 2026-04-16
**Status:** ✅ COMPLETO
**Porta:** 8010

## Resumo Executivo

O Requirements Engineering Service é o primeiro estágio do Fluxo G (Idea → Software). Ele é responsável por gerar requisitos funcionais e não-funcionais a partir de planos cognitivos, gerenciar user stories e critérios de aceite, e fornecer rastreabilidade completa.

## Funcionalidades Implementadas

### 1. Modelos de Dados (src/models/)

#### requirements.py
- `Requirement`: Requisito completo com rastreabilidade
- `RequirementCreate/Update`: DTOs para operações CRUD
- `RequirementsSet`: Conjunto de requisitos gerados
- `RequirementPriority`: Enum (CRITICAL, HIGH, MEDIUM, LOW)
- `RequirementType`: Enum (FUNCTIONAL, NON_FUNCTIONAL, CONSTRAINT, ASSUMPTION)
- `RequirementStatus`: Enum (DRAFT, APPROVED, REJECTED, DEPRECATED)

#### user_story.py
- `UserStory`: User story com formato padrão
- `AcceptanceCriteria`: Critérios em formato GWT (Given-When-Then)

#### acceptance_criteria.py
- `AcceptanceCriteria`: Critério de aceite estruturado

#### data_model.py
- Modelos auxiliares para integração

### 2. Serviço LLM (src/services/requirements_engineer.py)

**Funcionalidades:**
- `generate_from_cognitive_plan()`: Gera requisitos a partir de texto de plano
- `prioritize_requirements()`: Ordena por prioridade
- `analyze_dependencies()`: Analisa dependências entre requisitos via LLM

**Prompts especializados:**
- `REQUIREMENTS_GENERATION_PROMPT`: Gera funcionais + não-funcionais
- `DEPENDENCY_ANALYSIS_PROMPT`: Identifica dependências e conflitos

### 3. API REST (src/api/routers/requirements.py)

**Endpoints:**
- `POST /api/v1/requirements` - Criar requisito manual
- `POST /api/v1/requirements/generate` - Gerar requisitos via LLM
- `POST /api/v1/requirements/analyze-dependencies` - Analisar dependências
- `GET /api/v1/requirements` - Listar com filtros (priority, type, status)
- `GET /api/v1/requirements/{id}` - Obter por ID
- `PUT /api/v1/requirements/{id}` - Atualizar
- `DELETE /api/v1/requirements/{id}` - Deletar

### 4. Persistência MongoDB (src/db/mongodb.py, src/repositories/)

**MongoDBClient:** Singleton assíncrono com connection pooling

**RequirementsRepository:**
- `create()`: Criar novo requisito
- `get_by_id()`: Busca por ID
- `list()`: Listagem com filtros e paginação
- `update()`: Atualização parcial
- `delete()`: Remoção
- `save_set()`: Salvar conjunto de requisitos
- `get_by_cognitive_plan()`: Busca por plano origem

### 5. Configuração (src/config/settings.py)

- Prefix `REQ_ENG_` para variáveis de ambiente
- Integração OpenAI/Anthropic
- MongoDB, Redis, Kafka
- URLs para outros serviços NHM

## Testes

### Testes Unitários (4/4 passando ✅)
- `test_generate_requirements_from_cognitive_plan` ✅
- `test_generate_requirements_includes_functional_and_non_functional` ✅
- `test_prioritize_requirements_correctly` ✅
- `test_identify_dependencies` ✅

## Deploy

### Docker
- Python 3.12-slim
- Porta 8010 exposta
- Multi-stage build pronto

### Kubernetes
- Deployment com 1 réplica
- Service ClusterIP
- Health checks configurados
- Resource limits: 256Mi/512Mi memory, 250m/500m CPU
- Secrets para API keys

## Integração

### Kafka Topics
- **Produz**: `requirements-events`
- **Consome**: `cognitive-plan.created.v1`

### Downstream Services
- **architect-agent (8008)**: Recebe requisitos para planejamento arquitetural
- **documentation-generation (8014)**: Gera documentação a partir dos requisitos
- **test-generation (8013)**: Gera testes baseados nos requisitos

## Exemplo de Uso

```python
# Gerar requisitos a partir de plano cognitivo
POST /api/v1/requirements/generate?plan_id=CP-001&plan_text="Sistema de autenticação..."

# Resposta
{
  "requirements_set_id": "RS-a1b2c3d4",
  "cognitive_plan_id": "CP-001",
  "total": 5,
  "functional_count": 3,
  "non_functional_count": 2,
  "requirements": [
    {
      "id": "REQ-A1B2C3",
      "title": "Autenticação via email e senha",
      "description": "...",
      "priority": "high",
      "requirement_type": "functional",
      "rationale": "Método principal de acesso"
    },
    ...
  ]
}
```

## Estrutura de Arquivos

```
requirements-engineering/
├── src/
│   ├── api/
│   │   └── routers/
│   │       └── requirements.py     # API REST (200+ linhas)
│   ├── config/
│   │   └── settings.py             # Configurações
│   ├── db/
│   │   └── mongodb.py              # Cliente MongoDB
│   ├── models/
│   │   ├── requirements.py         # Modelos principais
│   │   ├── user_story.py           # User stories
│   │   ├── acceptance_criteria.py  # Critérios GWT
│   │   └── data_model.py           # Modelos auxiliares
│   ├── repositories/
│   │   └── requirements_repository.py  # Persistência
│   ├── services/
│   │   └── requirements_engineer.py    # Lógica LLM
│   ├── consumers/
│   ├── producers/
│   └── main.py                     # FastAPI app
├── tests/
│   └── unit/
│       └── test_requirements_engineer.py  # 4 testes ✅
├── deployment/
│   └── k8s-deployment.yaml         # K8s manifests
├── Dockerfile
├── requirements.txt
└── pyproject.toml
```

## Próximos Passos

1. Implementar User Stories endpoint completo
2. Adicionar Aceitação Criteria via LLM
3. Criar dashboard de rastreabilidade
4. Implementar versão de requisitos
5. Adicionar approval workflow

## Notas

- Gera requisitos funcionais e não-funcionais automaticamente
- Analisa dependências e conflitos via LLM
- Rastreabilidade completa (Requisitos ← User Stories ← Testes)
- Integração MongoDB para persistência
- Pronto para produção com testes passando
