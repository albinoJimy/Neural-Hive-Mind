# Tech Stack Recommendation - Documentação de Uso

## Visão Geral

O módulo **TechStackRecommender** recomenda stacks tecnológicas baseado em requisitos e restrições.

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

## Exemplo de Resposta

```json
{
  "recommendations": [
    {
      "category": "framework",
      "name": "FastAPI",
      "version": "0.104.0",
      "justification": "Alta performance, suporte async nativo",
      "fit_score": 0.95
    }
  ]
}
```
