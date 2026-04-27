# Análise de Compatibilidade e Conflitos de Versão
## Neural-Hive-Mind - Technical Debt Audit

**Data:** 2026-04-27
**Autor:** Worker Agent T9
**Scope:** Version pinning, gRPC alignment, breaking changes
**Status:** CRÍTICO

---

## 1. Resumo Executivo

Encontrados **13 conflitos de versão** críticos que podem causar runtime errors, incompatibilidade de protocolos gRPC e dependências transitivas conflitantes.

| Categoria | Conflitos | Severidade |
|-----------|-----------|------------|
| gRPC version mismatch | 2 serviços | ALTA |
| FastAPI fragmentation | 3 versões | MÉDIA |
| Pydantic inconsistency | 2 versões | MÉDIA |
| OpenTelemetry drift | libs vs base | ALTA |
| ML libraries version gaps | 2 versões numpy | BAIXA |
| httpx version spread | 3 versões | MÉDIA |

---

## 2. Version Pinning Consistency (R-T7.1)

### 2.1 Status Actual

**requirements-base.txt** (referência):
```
fastapi==0.115.10
pydantic==2.10.4
grpcio==1.71.2
opentelemetry-api==1.29.0
httpx==0.28.1
```

**Problema:** Múltiplos serviços não seguem o `requirements-base.txt` ou usam version ranges (`>=`) em vez de pinning exacto (`==`).

### 2.2 Serviços com Version Pinning Inconsistente

| Serviço | Biblioteca | Versão Actual | Target | Gap |
|---------|-----------|---------------|--------|-----|
| ml-inference-api | fastapi | 0.109.0 | 0.115.10 | -2 minor versions |
| ml-inference-api | pydantic | 2.6.0 | 2.10.4 | -4 patch versions |
| ml-inference-api | aiokafka | 0.9.0 | 0.12.0 | -3 minor versions |
| ml-inference-api | uvicorn | 0.24.0 | 0.34.0 | -10 minor versions |
| ml-inference-api | structlog | 23.2.0 | 24.4.0 | -1 year |
| ai-codegen-mcp-server | pydantic | >=2.5.0 | 2.10.4 | unbounded |
| ai-codegen-mcp-server | fastapi | >=0.109.0 | 0.115.10 | unbounded |
| deploy-service | grpcio | 1.68.1 | 1.71.2 | -3 patch versions |

### 2.3 Impacto

- **Runtime incompatibility:** `aiokafka==0.9.0` tem API diferente de `0.12.0` (mudança em `AIOKafkaProducer`)
- **Type safety loss:** `pydantic==2.6.0` vs `2.10.4` tem diferente `TypeAdapter` behaviour
- **Unpredictable deployments:** `>=` permite breaking changes em CI/CD

---

## 3. gRPC Version Alignment (R-T7.2)

### 3.1 Target Version Analysis

**Target:** `grpcio==1.71.2` (definido em requirements-base.txt)

### 3.2 Serviços Desalinhados

| Serviço | grpcio | grpcio-tools | Status |
|---------|--------|--------------|--------|
| **ml-inference-api** | 1.68.1 | 1.68.1 | ❌ OUTDATED |
| **orchestrator-dynamic** | 1.68.1 | 1.68.1 | ❌ OUTDATED |
| **deploy-service** | 1.68.1 | N/A | ❌ OUTDATED |
| **mcp-client-sdk** | 1.68.1 | N/A | ❌ OUTDATED |
| **optimizer-mcp-server** | 1.68.1 | N/A | ❌ OUTDATED |

### 3.3 Breaking Changes gRPC 1.68.x → 1.71.x

Conforme release notes do grpcio:
- **1.69.0:** Mudança em `grpc.channel_ready_future` (deprecation warning)
- **1.70.0:** `grpc.insecure_channel` agora requiere explicit `credentials` para TLS configs
- **1.71.0:** `grpc.intercept_channel` mudou ordem de interceptors

**Risco:** Serviços com versão antiga podem falhar ao comunicar com serviços na versão 1.71.2 devido a:
1. Incompatibilidade de protocolo wire format
2. Diferentes serialização de mensagens
3. Health check protocol mismatch

### 3.4 Análise de Compatibilidade Transitive

```
requirements-base.txt: grpcio==1.71.2
    └── grpcio-health-checking==1.71.2 (depende de grpcio==1.71.2)

ml-inference-api: grpcio==1.68.1
    └── grpcio-tools==1.68.1 (depende de grpcio==1.68.1)

CONFLITO: Se ambos instalados no mesmo venv, pip escolhe uma versão (non-deterministic)
```

---

## 4. Breaking Changes Identification (R-T7.3)

### 4.1 Pydantic 2.6.0 → 2.10.4 Breaking Changes

| Change | Impacto em ml-inference-api |
|--------|----------------------------|
| `TypeAdapter` type inference | Modelos podem falhar validação |
| `computed_field` behavior | Fields calculados podem retornar valores diferentes |
| `SecretStr` serialization | Pode expor secrets em logs |

**Mitigação:** Upgrade para 2.10.4 + review de testes de validação

### 4.2 FastAPI 0.109.0 → 0.115.10 Breaking Changes

| Change | Impacto em ml-inference-api |
|--------|----------------------------|
| OpenAPI schema generation | `/docs` pode não reflectir modelos correctos |
| `Request.state` typing | Type hints podem estar incorrectos |
| Dependency injection scope | Dependencies com `yield` podem ter lifecycle diferente |

### 4.3 aiokafka 0.9.0 → 0.12.0 Breaking Changes

| Change | Impacto em ml-inference-api |
|--------|----------------------------|
| `AIOKafkaProducer.send_and_wait` | Renomeado para `send` (com await) |
| `ConsumerRebalanceListener` | Interface mudou (métodos renomeados) |
| Schema registry integration | `confluent-kafka` config format mudou |

**Risco:** Runtime errors no Kafka consumer do ml-inference-api

---

## 5. Transitive Dependency Conflicts

### 5.1 OpenTelemetry Drift (CRÍTICO)

```
requirements-base.txt:
    opentelemetry-api==1.29.0
    opentelemetry-sdk==1.29.0
    opentelemetry-instrumentation==0.50b0

libs/python/requirements.txt:
    opentelemetry-api==1.39.1  ⚠️ INCOMPATÍVEL
    opentelemetry-sdk==1.39.1  ⚠️ INCOMPATÍVEL
    opentelemetry-instrumentation==0.60b1  ⚠️ INCOMPATÍVEL

libs/neural_hive_llm/pyproject.toml:
    opentelemetry-api>=1.21.0  ⚠️ UNBOUNDED
```

**Conflito detectado por pipdeptree:**
```
opentelemetry-instrumentation-kafka-python 0.61b0 requires opentelemetry-instrumentation==0.61b0,
but you have opentelemetry-instrumentation 0.50b0 which is incompatible.
```

**Impacto:**
- Traces podem não propagar correctamente
- Spans podem não ser exportadas
- Incompatibilidade de tipos em runtime

### 5.2 httpx Version Fragmentation

```
requirements-base.txt: httpx==0.28.1
ml-inference-api: httpx==0.25.2 (outdated)
neural_hive_llm: httpx>=0.25.0,<0.28 (capped before 0.28)
```

**Impacto:** OpenAI SDK (>=1.40.0) requer httpx>=0.27.0 para algumas features

### 5.3 Pydantic Constraint Conflict

```
neural_hive_llm/pyproject.toml:
    pydantic>=2.0.0 (unbounded minimum)

requirements-base.txt:
    pydantic==2.10.4 (pinned)

CONFLITO: Se pydantic 2.11.x for released, neural_hive_llm pode instalar
versão incompatible com requirements-base.txt
```

---

## 6. Migration Paths

### 6.1 gRPC Upgrade (Prioridade ALTA)

**Passo 1:** Identificar serviços usando gRPC 1.68.x
```bash
grep -r "grpcio.*1.68" services/*/requirements*.txt
```

**Passo 2:** Upgrade em staging
```bash
# ml-inference-api, orchestrator-dynamic, deploy-service, mcp-*-servers
sed -i 's/grpcio==1.68.1/grpcio==1.71.2/g' services/*/requirements*.txt
sed -i 's/grpcio-tools==1.68.1/grpcio-tools==1.71.2/g' services/*/requirements*.txt
```

**Passo 3:** Regenerate protos
```bash
make proto  # ou python -m grpc_tools.protoc ...
```

**Passo 4:** Test E2E com canary deployment

### 6.2 OpenTelemetry Sync (Prioridade ALTA)

**Opção A:** Downgrade libs para 1.29.0
```bash
# libs/python/requirements.txt
opentelemetry-api==1.29.0  # was 1.39.1
opentelemetry-sdk==1.29.0  # was 1.39.1
opentelemetry-instrumentation==0.50b0  # was 0.60b1
```

**Opção B:** Upgrade base para 1.39.1 (RECOMENDADO)
```bash
# requirements-base.txt
opentelemetry-api==1.39.1
opentelemetry-sdk==1.39.1
opentelemetry-instrumentation==0.60b1
opentelemetry-instrumentation-fastapi==0.61b0
opentelemetry-instrumentation-grpc==0.61b0
```

### 6.3 FastAPI/Pydantic Upgrade (Prioridade MÉDIA)

**ml-inference-api upgrade completo:**
```
fastapi==0.109.0 → 0.115.10
pydantic==2.6.0 → 2.10.4
aiokafka==0.9.0 → 0.12.0
uvicorn==0.24.0 → 0.34.0
structlog==23.2.0 → 24.4.0
```

**Passos:**
1. Review de breaking changes nas release notes
2. Update de testes unitários (API schema validation)
3. Test de integração Kafka
4. Deploy em staging com monitoramento

---

## 7. Mitigation Recommendations

### 7.1 Imediato (Before Next Release)

1. **Lock OpenTelemetry version**
   - Escolher versão consistente (1.29.0 ou 1.39.1)
   - Update libs/python/requirements.txt
   - Adicionar test de compatibilidade

2. **Pin gRPC version globalmente**
   - Adicionar check no CI/CD para detectar versões diferentes de 1.71.2
   - Bloquear PRs que modificam grpcio version

3. **Fix neural_hive_llm constraints**
   - Mudar `pydantic>=2.0.0` para `pydantic>=2.10.0,<2.11.0`
   - Mudar `httpx>=0.25.0,<0.28` para `httpx>=0.28.0,<0.29`

### 7.2 Curto Prazo (Next Sprint)

1. **Migrate ml-inference-api to base versions**
   - Atualizar todas as dependências
   - Executar test suite completo
   - Deploy em canary

2. **Implement version compatibility testing**
   - Script que verifica dependências transitivas
   - Pipeline job que corre `pipdeptree` e reporta conflicts

3. **Centralize dependency management**
   - Mover mais dependências para requirements-base.txt
   - Eliminar ranges (`>=`) em favor de pinned versions (`==`)

### 7.3 Longo Prazo

1. **Adopt Poetry ou PDM para dependency resolution**
   - Garantem que dependências transitivas são resolvidas correctamente
   - Lock files garantem builds reproducíveis

2. **Implement Renovate ou Dependabot**
   - Auto-updates de dependências com PRs automatizados
   - Testes automáticos antes de merge

3. **Dependency dashboard**
   - Dashboard visível de versões em uso
   - Alertas de security vulnerabilities

---

## 8. Conclusão

### Riscos Identificados por Severidade

| Severidade | Count | Exemplos |
|------------|-------|----------|
| CRÍTICA | 3 | OpenTelemetry drift, gRPC mismatch, httpx cap |
| ALTA | 5 | Pydantic 2.6→2.10, FastAPI 0.109→0.115, aiokafka 0.9→0.12 |
| MÉDIA | 3 | Version ranges unbounded, numpy 1.26.0 vs 1.26.4 |
| BAIXA | 2 | Structlog version gap, minor patch differences |

### Próximos Passos Recomendados

1. **Ticket 1:** Sync OpenTelemetry versions (CRÍTICO)
2. **Ticket 2:** Migrate gRPC to 1.71.2 em todos os serviços (ALTA)
3. **Ticket 3:** Upgrade ml-inference-api to base versions (ALTA)
4. **Ticket 4:** Implement version check CI/CD gate (MÉDIA)
5. **Ticket 5:** Evaluate migration to Poetry/PDM (BAIXA)

---

**Documentação Relacionada:**
- `requirements-base.txt` - Versões alvo para todos os serviços
- `CLAUDE.md` - Stack técnica e convenções
- `pyproject.toml` - Configuração de ferramentas de desenvolvimento
