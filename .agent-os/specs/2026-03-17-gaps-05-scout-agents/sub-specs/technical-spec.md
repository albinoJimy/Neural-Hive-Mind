# Technical Specification

This is the technical specification for the spec detailed in @.agent-os/specs/2026-03-17-gaps-05-scout-agents/spec.md

## Technical Requirements

### ScoutOrchestrator Service
- gRPC server para comunicação com Queen Agent
- Coordenação de múltiplos scouts em paralelo (asyncio)
- Timeout configurável por exploração (default: 30s)
- Agregação de resultados com deduplicação
- Publicação de eventos em Kafka (scout.exploration.completed)

### CodebaseExplorer Module
- Análise estática usando AST (Abstract Syntax Tree)
- Indexação de arquivos por tipo (Python, TypeScript, YAML)
- Extração de imports, classes, funções e decorators
- Construção de grafo de dependências
- Suporte a repositórios Git (diff analysis)

### PatternDiscovery Engine
- Detecção de padrões usando AST matching
- Categorias: error_handling, logging, validation, caching, async
- Scoring de relevância por frequência e contexto
- Identificação de anti-padrões (ex: bare except)
- Sugestão de refatorações baseadas em best practices

### SolutionSynthesizer
- Combina múltiplas descobertas em recomendações
- Geração de exemplos de código
- Cálculo de complexidade (cyclomatic complexity, LOC)
- Identificação de dependências externas
- Formato de saída: JSON (API), texto (narrativa), Markdown (documentos)

### ScoutLedger (MongoDB)
- Coleção: `scout_explorations`
- Índices: plan_id, created_at, exploration_type, status
- TTL de 7 dias para explorações antigas
- Cache hit rate tracking

## External Dependencies

- **astroid** - Análise estática de Python (alternativa ao AST builtin)
- **networkx** - Manipulação de grafos de dependências
- **pygments** - Syntax highlighting para snippets de código
- **gitpython** - Interação com repositórios Git

**Justification:** Essas bibliotecas são especializadas em análise estática de código e manipulação de grafos, permitindo implementação robusta sem reinventar a roda.

## Integration Requirements

### Queen Agent Integration
- gRPC client para registrar Scout Agent
- Heartbeat a cada 5s
- Recebe comandos de exploração via streaming

### Orchestrator Dynamic Integration
- Enriquece tickets com descobertas dos scouts
- Adiciona campo `scout_insights` ao CognitivePlan
- Triggers exploração automática para intenções complexas

### Kafka Events
- Producer: `scout.exploration.started`, `scout.exploration.completed`
- Consumer: `plan.created` → trigger exploração automática

## Performance Criteria

- Análise de codebase médio (~1000 arquivos): <10s
- Descoberta de padrões: <5s
- Parallelização: até 5 scouts simultâneos
- Cache hit rate target: >70%
