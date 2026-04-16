# Tech Stack Recommendation - Documentação de Uso

## Visão Geral

O módulo **TechStackRecommender** recomenda stacks tecnológicas baseado em requisitos e restrições.

## Uso via Python

```python
from src.recommenders.tech_stack import TechStackRecommender
from src.llm.openai_client import AsyncOpenAI
from src.models.tech_stack import Constraint

# Inicializar com cliente LLM
llm_client = AsyncOpenAI(api_key="your-api-key")
recommender = TechStackRecommender(llm_client)

# Definir restrições
constraints = [
    Constraint(type="language", value="python"),
    Constraint(type="budget", value="low"),
    Constraint(type="scalability", value="high")
]

# Recomendar stack
recommendation = await recommender.recommend(
    requirements="API REST de alta performance para marketplace",
    constraints=constraints
)

# Acessar recomendações
for choice in recommendation.choices:
    print(f"{choice.category}: {choice.name} {choice.version}")
    print(f"  Rationale: {choice.rationale}")

print(f"Confidence: {recommendation.confidence_score}")
print(f"Complexity: {recommendation.estimated_complexity}")
print(f"Cost: {recommendation.estimated_cost}")
```

## API REST

### Recomendar Stack Tecnológico

```bash
POST /api/v1/architecture/tech-stack/recommend
Content-Type: application/json

{
  "requirements": "API REST de alta performance...",
  "constraints": {
    "budget": "low",
    "team_expertise": ["python"],
    "scalability": "high"
  }
}
```

## Categorias Disponíveis

- **Languages:** Python, Node.js, Go, Java, Ruby
- **Web Frameworks:** FastAPI, Express, Gin, Spring Boot
- **Databases:** PostgreSQL, MongoDB, Redis
- **Messaging:** Kafka, RabbitMQ, Redis Streams
- **Frontend:** React, Vue, Svelte

## Restrições Suportadas

- `budget`: low, medium, high
- `scalability`: low, medium, high
- `team_expertise`: lista de tecnologias
- `compliance`: gdpr, hipaa, pci-dss

## Exemplo de Resposta JSON Completo

```json
{
  "choices": [
    {
      "category": "language",
      "name": "Python",
      "version": "3.12+",
      "rationale": "Equipe tem experiência, ecossistema rico para APIs"
    },
    {
      "category": "web_framework",
      "name": "FastAPI",
      "version": "0.104+",
      "rationale": "Alta performance, suporte async nativo, validação automática"
    },
    {
      "category": "database",
      "name": "PostgreSQL",
      "version": "16",
      "rationale": "ACID compliant, JSON support, escalabilidade horizontal"
    },
    {
      "category": "cache",
      "name": "Redis",
      "version": "7.2",
      "rationale": "Cache distribuído, rate limiting, pub/sub"
    },
    {
      "category": "messaging",
      "name": "Kafka",
      "version": "3.6",
      "rationale": "Event streaming, alta throughput, durability"
    }
  ],
  "constraints_satisfied": [
    {"type": "language", "value": "python"},
    {"type": "scalability", "value": "high"}
  ],
  "constraints_violated": [
    {"type": "budget", "value": "low", "reason": "Kafka requer infraestrutura dedicada"}
  ],
  "confidence_score": 0.88,
  "estimated_complexity": "medium",
  "estimated_cost": "medium"
}
```
```
