# Technical Specification

Esta é a especificação técnica para o spec detalhado em @.agent-os/specs/2026-03-18-scout-agents-expansion/spec.md

## Technical Requirements

### AST Parsing Multi-Linguagem

**Python** (já implementado, verificar):
- `ast` module para parsing
- Extração de classes, funções, imports, decoradores
- Cálculo de complexidade ciclomática

**TypeScript/JavaScript** (NOVO):
- Usar `@typescript-eslint/parser` ou `esprima`
- Suporte para TypeScript interfaces, types, generics
- Extração de classes, funções, decorators, imports
- Detecção de arrow functions e async/await

**YAML/JSON** (NOVO):
- Parsing com `PyYAML` para YAML
- Parsing com `json` para JSON
- Extração de estrutura (chaves, valores aninhados)
- Detecção de configurações Kubernetes, Docker Compose

**Java** (NOVO):
- Usar `javaparser` (Java library) ou `tree-sitter-java`
- Extração de classes, interfaces, métodos, campos
- Suporte para annotations, generics, enums
- Detecção de packages e imports

**C#** (NOVO):
- Usar `tree-sitter-c-sharp` ou `roslyn` via subprocess
- Extração de classes, interfaces, métodos, propriedades
- Suporte para attributes, generics, enums
- Detecção de namespaces e using directives

**Go** (NOVO):
- Usar `go/parser` via subprocess ou `tree-sitter-go`
- Extração de structs, interfaces, funções, métodos
- Suporte para goroutines, channels, defer
- Detecção de packages e imports

**C/C++** (NOVO):
- Usar `tree-sitter-c` e `tree-sitter-cpp`
- Extração de classes, structs, funções, templates
- Suporte para macros, includes, preprocessor directives
- Detecção de headers e dependencies

**Rust** (NOVO):
- Usar `tree-sitter-rust`
- Extração de structs, enums, traits, impl blocks, funções
- Suporte para macros (macro_rules!, decl, proc)
- Suporte para lifetime annotations e generics
- Detecção de crates (use, extern crate) e module declarations (mod)

### Pattern Detection Expandido

**Padrões já implementados** (verificar):
- Repository, Service, Factory, Singleton, Decorator

**Novos padrões a implementar** (20+ no total):
- **Strategy**: Classes com mesma interface, seleção em runtime
- **Observer**: Event handlers, pub/sub, emit/on patterns
- **Adapter**: Wrapper classes, tradução de interfaces
- **Bridge**: Abstração separada de implementação
- **Composite**: Tree structures, parent-child relationships
- **Proxy**: Lazy loading, access control, logging wrappers
- **Command**: Command objects, undo/redo, queueing
- **Chain of Responsibility**: Middleware chains, pass-through
- **Template Method**: Base classes com hooks, override patterns
- **Facade**: Simplified interfaces over complex subsystems
- **Builder**: Fluent interfaces, step-by-step construction
- **Prototype**: Clone methods, object copying
- **Mediator**: Central coordination between components
- **Memento**: State snapshots, rollback capability
- **State**: State machines, context-dependent behavior
- **Flyweight**: Object pooling, shared intrinsic state
- **Abstract Factory**: Families of related objects
- **Iterator**: Sequential access to collections
- **Visitor**: Operations on object structures without modifying classes

### Signal Detection & Curiosity

**Curiosity Scoring**:
- Entropia de código (novidade vs. padrões conhecidos)
- Coverage de testes (arquivos sem testes)
- Complexidade (código complexo merece atenção)
- Dependências (módulos com muitas dependências)
- Recência (arquivos modificados recentemente)

**Signal Types**:
- `high_complexity`: Complexidade >15
- `low_coverage`: Arquivos sem testes correspondentes
- `pattern_anomaly`: Desvio de padrões conhecidos
- `dependency_spike**: Muitas dependências recentes

### Multi-Scout Coordination

**Coordenador**:
- Distribuir tarefas entre scouts
- Agregar resultados (synthesis)
- Tratar conflitos e duplicações
- Timeout por scout

**Sincronização**:
- Redis para state sharing
- Lock distribuído para regiões críticas
- Pub/Sub para eventos de progresso

### API Endpoints

**Já implementados** (verificar):
- `GET /health` - Health check
- `POST /explorations` - Criar exploração
- `GET /explorations/{id}` - Obter resultado

**Novos endpoints**:
- `GET /explorations` - Listar explorações (paginado)
- `DELETE /explorations/{id}` - Cancelar exploração
- `POST /explorations/{id}/scouts` - Adicionar scout
- `GET /patterns` - Listar padrões detectados
- `POST /signal-detect` - Detectar sinais
- `GET /metrics` - Métricas Prometheus

## External Dependencies

**Novas dependências**:

- **`esprima`** ou **`@typescript-eslint/typescript-estree`** - Parsing JavaScript/TypeScript
  - Justificativa: necessário para suporte AST de JS/TS

- **`PyYAML`** - Parsing YAML (já usado, validar versão)
  - Justificativa: análise de configs Kubernetes, Docker Compose

- **`tree-sitter`** + **`tree-sitter-languages`** - Parsing multi-linguagem
  - Justificativa: suporte unificado para Java, C#, Go, C/C++, Rust

- **`redis`** (python-redis) - Coordenação multi-scout
  - Justificativa: state sharing entre instâncias de scout

- **`prometheus-client`** - Métricas de exportação
  - Justificativa: integração com stack de observabilidade

## Performance Requirements

- Exploração de 1000 arquivos Python em <30s
- Parsing de um arquivo médio (200 LOC) em <50ms
- Detecção de padrões em <100ms por arquivo
- Multi-scout: 4 scouts em paralelo, speedup 3x+

## Test Coverage Goals

- Unit tests: ≥80% coverage
- Integration tests: todos os endpoints REST
- E2E tests: fluxo completo com Docker Compose
- Performance tests: load test com 100 req/s
- **Meta**: 150+ testes no total (41 existentes + ~110 novos)

## Deployment Configuration

**Helm Chart Structure**:
```
helm/scout-agents/
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── serviceaccount.yaml
│   ├── configmap.yaml
│   ├── hpa.yaml
│   └── metrics-service.yaml
```

**Configuráveis via values.yaml**:
- image.repository, image.tag
- resources.limits, resources.requests
- replicas (para HPA)
- env variables (KAFKA_BROKERS, REDIS_URL, etc.)
- annotations para ServiceMesh
- tolerations/nodeSelector

## Grafana Dashboard Panels

1. **Explorations Rate** - explorations/second (rate)
2. **Exploration Duration** - P50/P95/P99 latency
3. **Patterns Detected** - by pattern type (pie chart)
4. **Scout Utilization** - active scouts vs. capacity
5. **Error Rate** - failed explorations (percentage)
6. **Language Distribution** - files by language (Python, TS, JS, YAML, JSON, Java, C#, Go, C/C++, Rust)
7. **Cache Hit Rate** - AST cache effectiveness
8. **Queue Depth** - pending explorations
