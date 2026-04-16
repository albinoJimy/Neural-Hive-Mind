# Release Notes - Architect Agent v0.2.0

**Data:** 2026-04-16
**Versão:** 0.2.0
**Fase:** Fluxo G - Fase 1 Foundation

---

## Novidades

### ✨ Bounded Contexts Identification

Identificação automática de Bounded Contexts baseado em Domain-Driven Design (DDD).

- Módulo `BoundedContextsIdentifier` analisa requisitos e identifica contextos limitrófes
- Detecção de relacionamentos entre contextos
- Extração de Linguagem Onipresente (Ubiquitous Language)
- Suporte a domain hints para orientar a identificação
- API REST: `POST /api/v1/architecture/bounded-contexts/identify`

### ✨ Tech Stack Recommendation

Recomendação inteligente de stack tecnológico baseado em requisitos e restrições.

- Módulo `TechStackRecommender` com knowledge base integrada
- Análise de restrições (linguagem, framework, cloud, budget)
- Scoring de complexidade e custo estimado
- Validação de restrições (satisfied/violated)
- API REST: `POST /api/v1/architecture/tech-stack/recommend`

### ✨ Architecture Diagram Generation

Geração automática de diagramas de arquitetura C4 com renderização Mermaid.

- Diagramas C4: Context, Container, Component
- Diagramas de Sequência
- Geração a partir de descrição em linguagem natural
- Renderização para SVG via Mermaid CLI
- API REST: `POST /api/v1/architecture/diagrams/generate`

### 🚀 Enhanced Architecture Planning

O método `DesignPlanner.plan()` foi estendido para integrar os novos módulos.

- Planos de arquitetura agora incluem `bounded_contexts`, `tech_stack` e `diagrams`
- Inicialização condicional baseada em `OPENAI_API_KEY`
- Graceful degradation se módulos estendidos não estiverem disponíveis
- API REST: `GET /api/v1/architecture/{architecture_id}/bounded-contexts`
- API REST: `GET /api/v1/architecture/{architecture_id}/diagrams`

---

## Breaking Changes

**Nenhuma.** Todas as mudanças são aditivas e backward compatíveis.

---

## Migration Guide

Nenhuma migração necessária. As extensões são opcionais e o serviço continua funcional sem elas.

Para ativar as novas funcionalidades:

1. Configurar `OPENAI_API_KEY` no ambiente
2. Definir `USE_EXTENDED_FEATURES=true` (default: auto-detect)
3. Chamar os novos endpoints REST conforme documentação

---

## Testes

- 3 testes unitários para BoundedContextsIdentifier
- 3 testes unitários para TechStackRecommender
- 5 testes unitários para ArchitectureDiagramGenerator
- 9 testes de integração para o fluxo extendido
- Total: **20 novos testes**

---

## Documentação

- `docs/BOUNDED_CONTEXTS.md` - Guia de identificação de bounded contexts
- `docs/TECH_STACK_RECOMMENDATION.md` - Guia de recomendação de tech stack
- `docs/DIAGRAM_GENERATION.md` - Guia de geração de diagramas

---

## Deploy

### Helm Chart

Os manifests Kubernetes estão disponíveis no formato Helm:

```bash
helm install architect-agent ./helm/architect-agent \
  --namespace neural-hive-staging \
  --set image.tag=v0.2.0 \
  --set env.OPENAI_API_KEY=<your-key>
```

### Variáveis de Ambiente

- `OPENAI_API_KEY` - Chave da OpenAI para funcionalidades estendidas
- `USE_EXTENDED_FEATURES` - Ativa módulos estendidos (default: true)
- `MMDC_PATH` - Caminho para o binário mermaid-cli (default: mmdc)

---

## Próximos Passos

- [ ] Performance testing com bounded contexts complexos
- [ ] Expandir knowledge base do TechStackRecommender
- [ ] Suporte para diagramas C4 com mais detalhes
- [ ] Integração com Service Registry para descoberta de serviços

---

**Full Changelog:** https://github.com/albinoJimy/Neural-Hive-Mind/compare/v0.1.0...v0.2.0
