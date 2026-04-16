# Bounded Contexts - Documentação de Uso

## Visão Geral

O módulo **BoundedContextsIdentifier** identifica bounded contexts baseados em Domain-Driven Design (DDD) a partir de requisitos de sistema em linguagem natural.

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
