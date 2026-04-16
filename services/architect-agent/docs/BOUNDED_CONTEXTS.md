# Bounded Contexts - Documentação de Uso

## Visão Geral

O módulo **BoundedContextsIdentifier** identifica bounded contexts baseados em Domain-Driven Design (DDD) a partir de requisitos de sistema em linguagem natural.

## Uso via Python

```python
from src.identifiers.bounded_contexts import BoundedContextsIdentifier
from src.llm.openai_client import AsyncOpenAI

# Inicializar com cliente LLM
llm_client = AsyncOpenAI(api_key="your-api-key")
identifier = BoundedContextsIdentifier(llm_client)

# Identificar bounded contexts
analysis = await identifier.identify(
    requirements="Sistema de e-commerce com gestão de utilizadores, catálogo de produtos e processamento de pagamentos",
    domain_hints=["identity", "catalog", "billing"]
)

# Acessar resultados
for context in analysis.contexts:
    print(f"Context: {context.name}")
    print(f"  Description: {context.description}")
    print(f"  Responsibilities: {context.responsibilities}")

    # Linguagem onipresente
    for term in context.ubiquitous_language:
        print(f"  Term: {term.term} -> {term.definition}")

    # Relacionamentos
    for rel in context.relationships:
        print(f"  Rel: {rel.relationship_type} -> {rel.to_context}")

print(f"Confidence Score: {analysis.confidence_score}")
```

## API REST

### Identificar Bounded Contexts

```bash
POST /api/v1/architecture/bounded-contexts/identify
Content-Type: application/json

{
  "requirements": "Sistema de e-commerce com gestão de utilizadores...",
  "domain_hints": ["identity", "catalog", "billing"]
}
```

## Relacionamentos entre Contextos

| Tipo | Descrição |
|------|-----------|
| partnership | Colaboração necessária |
| shared_kernel | Modelos partilhados |
| customer_supplier | Dependência direta |
| conformist | Convenções upstream |
| acl | Restrições de acesso |

## Contextos Típicos

- **Identity:** Autenticação, autorização, perfis
- **Catalog:** Produtos, categorias, busca
- **Order:** Carrinho, checkout, pagamentos
- **Billing:** Faturação, assinaturas

## Exemplo de Resposta JSON

```json
{
  "total_contexts": 3,
  "confidence_score": 0.92,
  "contexts": [
    {
      "name": "Identity",
      "description": "Gestão de autenticação, autorização e perfis de utilizador",
      "responsibilities": [
        "Login e logout",
        "Gestão de tokens JWT",
        "Perfis e permissões"
      ],
      "domain_models": ["User", "Role", "Permission"],
      "is_external": false,
      "ubiquitous_language": [
        {
          "term": "User",
          "definition": "Entidade que representa um utilizador do sistema"
        },
        {
          "term": "Authentication",
          "definition": "Processo de verificação de credenciais"
        }
      ],
      "relationships": [
        {
          "to_context": "Order",
          "relationship_type": "customer_supplier",
          "direction": "outgoing"
        }
      ]
    },
    {
      "name": "Catalog",
      "description": "Gestão de catálogo de produtos e categorias",
      "responsibilities": [
        "CRUD de produtos",
        "Busca e filtros",
        "Gestão de categorias"
      ],
      "domain_models": ["Product", "Category", "Variant"],
      "is_external": false,
      "ubiquitous_language": [
        {
          "term": "SKU",
          "definition": "Stock Keeping Unit - identificador único do produto"
        }
      ],
      "relationships": []
    },
    {
      "name": "Billing",
      "description": "Processamento de pagamentos e faturação",
      "responsibilities": [
        "Processamento de pagamentos",
        "Geração de faturas",
        "Gestão de subscrições"
      ],
      "domain_models": ["Invoice", "Payment", "Subscription"],
      "is_external": false,
      "ubiquitous_language": [],
      "relationships": [
        {
          "to_context": "Order",
          "relationship_type": "customer_supplier",
          "direction": "incoming"
        }
      ]
    }
  ]
}
```
