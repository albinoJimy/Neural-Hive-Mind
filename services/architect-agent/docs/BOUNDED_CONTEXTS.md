# Bounded Contexts Identifier

## Visão Geral

O módulo `BoundedContextsIdentifier` identifica Bounded Contexts baseado em Domain-Driven Design (DDD) a partir de requisitos em linguagem natural.

## Propósito

Bounded Contexts são fronteiras conceituais dentro de um domínio onde termos e modelos têm significado específico. Este módulo ajuda a:

1. Identificar contextos limitrófes em um sistema
2. Definir responsabilidades de cada contexto
3. Identificar modelos de domínio principais
4. Documentar linguagem ubíqua (termos específicos do domínio)

## Uso

```python
from src.identifiers.bounded_contexts import BoundedContextsIdentifier

# Inicializar (requer cliente OpenAI configurado)
identifier = BoundedContextsIdentifier()

# Identificar contexts a partir de requisitos
analysis = await identifier.identify(
    requirements="""
    Sistema de e-commerce com:
    - Catálogo de produtos e categorias
    - Carrinho de compras e checkout
    - Processamento de pagamentos
    - Gestão de encomendas e envio
    """,
    domain_hints=["Catalog", "Checkout", "Payments"]  # opcional
)

# Acessar resultados
for context in analysis.contexts:
    print(f"Context: {context.name}")
    print(f"Description: {context.description}")
    print(f"Responsibilities: {context.responsibilities}")
```

## API

### `BoundedContextsIdentifier`

#### Métodos

- `async identify(requirements: str, domain_hints: Optional[List[str]] = None) -> BoundedContextsAnalysis`

  Identifica bounded contexts a partir de requisitos.

  Args:
  - `requirements`: Descrição dos requisitos do sistema
  - `domain_hints`: Sugestões de nomes de contextos (opcional)

  Returns: `BoundedContextsAnalysis` com contexts encontrados

### Modelos

#### `BoundedContext`
- `name`: Nome do contexto
- `description`: Propósito do contexto
- `responsibilities`: Lista de responsabilidades
- `domain_models`: Modelos de domínio principais
- `ubiquitous_language`: Termos específicos do domínio
- `relationships`: Relacionamentos com outros contextos

#### `BoundedContextsAnalysis`
- `contexts`: Lista de bounded contexts identificados
- `total_contexts`: Número total de contexts
- `confidence_score`: Score de confiança da análise (0-1)

## REST API

```bash
POST /api/v1/architecture/bounded-contexts/identify
Content-Type: application/json

{
  "requirements": "Sistema de gestão de tarefas colaborativa",
  "domain_hints": ["Tasks", "Users", "Notifications"]
}
```

## Requisitos

- Cliente OpenAI configurado com API key
- Modelos suportados: gpt-4, gpt-3.5-turbo
