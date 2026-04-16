# Test Generation Service (8013)

Serviço de geração automática de testes usando LLMs.

## Descrição

O Test Generation Service é responsável por gerar testes automatizados a partir de:
- Requisitos funcionais
- User Stories
- Critérios de Aceite (Given-When-Then)
- Código fonte existente

## Funcionalidades

- **Geração Multi-tipo**: Unitários, Integração, E2E, Performance, Segurança
- **Multi-framework**: pytest, jest, junit, go_test, robot
- **Multi-linguagem**: Python, JavaScript/TypeScript, Java, Go
- **Rastreabilidade**: Links diretos para requisitos e user stories
- **Métricas**: Cálculo automático de cobertura de testes

## Stack Tecnológica

- Python 3.12+
- FastAPI
- OpenAI GPT-4
- MongoDB
- Kafka
- Qdrant (Knowledge Graph)

## API Endpoints

### Geração de Testes

```bash
# Geração completa
POST /api/v1/tests/generate
{
  "requirements": [...],
  "user_stories": [...],
  "test_type": "unit",
  "framework": "pytest",
  "language": "python"
}

# A partir de requisitos
POST /api/v1/tests/generate/from-requirements
{
  "requirements": [
    {
      "id": "REQ-001",
      "title": "Autenticação",
      "description": "Sistema deve permitir login",
      "acceptance_criteria": ["Login válido funciona", "Login inválido falha"]
    }
  ],
  "test_type": "integration",
  "framework": "pytest"
}

# A partir de User Stories
POST /api/v1/tests/generate/from-user-stories
{
  "user_stories": [
    {
      "id": "US-001",
      "title": "Login do Usuário",
      "description": "Como usuário, quero fazer login",
      "acceptance_criteria": [
        {
          "id": "AC-001",
          "given": "na página de login",
          "when": "insiro credenciais válidas",
          "then": "sou redirecionado ao dashboard"
        }
      ]
    }
  ],
  "test_type": "e2e",
  "framework": "robot"
}
```

### Consulta e Métricas

```bash
# Listar suítes de testes
GET /api/v1/tests/suites

# Métricas de cobertura
GET /api/v1/tests/coverage

# Health check
GET /health
```

## Desenvolvimento

### Instalar Dependências

```bash
pip install -r requirements.txt
```

### Rodar Testes

```bash
pytest
```

### Rodar Serviço Localmente

```bash
cp .env.test .env
python -m uvicorn src.main:app --reload --port 8013
```

## Variáveis de Ambiente

| Variável | Descrição | Default |
|----------|-----------|---------|
| `TEST_GEN_OPENAI_API_KEY` | Chave API OpenAI | - |
| `TEST_GEN_LLM_MODEL` | Modelo LLM | gpt-4-turbo-preview |
| `TEST_GEN_MONGODB_URL` | URL MongoDB | mongodb://localhost:27017 |
| `TEST_GEN_KAFKA_BOOTSTRAP_SERVERS` | Kafka brokers | localhost:9092 |
| `TEST_GEN_KNOWLEDGE_GRAPH_URL` | Knowledge Graph | http://localhost:8016 |
| `TEST_GEN_COVERAGE_TARGET` | Meta de cobertura | 0.8 |

## Deploy

### Docker

```bash
docker build -t nhm/test-generation:v0.1.0 .
docker run -p 8013:8013 --env-file .env nhm/test-generation:v0.1.0
```

### Kubernetes

```bash
kubectl apply -f deployment/k8s-deployment.yaml
```

## Integração

### Kafka Topics

- **Produz**: `test.generated.v1`
- **Consome**: `requirement.created.v1`, `user.story.created.v1`

### Knowledge Graph

Consulta requisitos e código fonte para contexto de geração.

## Estrutura de Diretórios

```
test-generation/
├── src/
│   ├── api/
│   │   └── routers/
│   │       └── tests.py          # API REST
│   ├── config/
│   │   └── settings.py           # Configurações
│   ├── models/
│   │   └── tests.py              # Modelos Pydantic
│   ├── services/
│   │   └── test_generator.py     # Lógica de geração
│   └── main.py                   # Aplicação FastAPI
├── tests/
│   ├── conftest.py
│   └── src/
│       ├── models/
│       ├── services/
│       └── api/
├── deployment/
│   └── k8s-deployment.yaml
├── Dockerfile
└── requirements.txt
```
