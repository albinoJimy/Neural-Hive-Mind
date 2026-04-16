# Tech Stack Recommender

## Visão Geral

O módulo `TechStackRecommender` recomenda stacks tecnológicos baseados em requisitos do sistema, utilizando LLM e uma base de conhecimento de tecnologias.

## Propósito

Auxiliar na escolha de tecnologias para um novo projeto ou sistema, considerando:

1. Requisitos funcionais e não-funcionais
2. Restrições técnicas (linguagens, bancos de dados preferidos)
3. Padrões da indústria e melhores práticas
4. Trade-offs entre diferentes opções

## Uso

```python
from src.recommenders.tech_stack import TechStackRecommender

# Inicializar (requer cliente OpenAI configurado)
recommender = TechStackRecommender()

# Recomendar stack
recommendation = await recommender.recommend(
    requirements="API REST para gestão de tarefas com alta concorrência",
    constraints=[
        {"type": "language", "value": "Python"},
        {"type": "database", "value": "PostgreSQL"}
    ]
)

# Acessar recomendações
for choice in recommendation.choices:
    print(f"{choice.category}: {choice.name}")
    print(f"  Rationale: {choice.rationale}")
```

## API

### `TechStackRecommender`

#### Métodos

- `async recommend(requirements: str, constraints: Optional[List[dict]] = None) -> TechStackRecommendation`

  Recomenda stack tecnológico.

  Args:
  - `requirements`: Descrição dos requisitos do sistema
  - `constraints`: Lista de restrições técnicas (opcional)

  Returns: `TechStackRecommendation` com escolhas recomendadas

### Modelos

#### `TechChoice`
- `category`: Categoria (backend, database, cache, messaging)
- `name`: Nome da tecnologia
- `version`: Versão recomendada
- `rationale`: Justificativa da escolha

#### `TechStackRecommendation`
- `choices`: Lista de tecnologias recomendadas
- `constraints_satisfied`: Restrições atendidas
- `constraints_violated`: Restrições não atendidas
- `confidence_score`: Score de confiança (0-1)
- `estimated_complexity`: Complexidade estimada (baixa, media, alta)
- `estimated_cost`: Custo estimado ($, $$, $$$)

## REST API

```bash
POST /api/v1/architecture/tech-stack/recommend
Content-Type: application/json

{
  "requirements": "Sistema transacional com dados relacionais",
  "constraints": [
    {"type": "language", "value": "Python"},
    {"type": "database", "value": "PostgreSQL"}
  ]
}
```

## Base de Conhecimento

O módulo inclui uma base de conhecimento (`TECH_KNOWLEDGE_BASE`) com:

- **Backend Frameworks**: FastAPI, Django, Express, Nest
- **Databases**: PostgreSQL, MySQL, MongoDB, Redis
- **Messaging**: Kafka, RabbitMQ

Cada tecnologia inclui:
- Prós e contras
- Casos de uso recomendados
- Complexidade de implementação
- Custo operacional

## Requisitos

- Cliente OpenAI configurado com API key
- Modelos suportados: gpt-4, gpt-3.5-turbo
