# Guia de Testes - Fase 1

## Visão Geral

Este guia documenta os testes end-to-end (E2E) da Fase 1 do Neural Hive-Mind, cobrindo a validação completa do fluxo de geração e consenso de planos cognitivos.

### Fluxo Testado

```
Intent Envelope → Semantic Translation Engine → Cognitive Plan
       ↓
5 Specialist Evaluations (Business, Technical, Behavior, Evolution, Architecture)
       ↓
Consensus Engine → Consolidated Decision
       ↓
Persistence (MongoDB Ledger, Redis Pheromones, Neo4j Knowledge Graph)
       ↓
Observability (Prometheus Metrics, Jaeger Traces, Grafana Dashboards)
```

### Componentes Validados

- **Camadas de Memória**: Redis, MongoDB, Neo4j (ClickHouse é opcional)
- **Gateway de Intenções**: Captura e roteamento de intents
- **Semantic Translation Engine**: Geração de planos cognitivos
- **5 Especialistas Neurais**: Avaliação multi-perspectiva
- **Consensus Engine**: Consolidação bayesiana de decisões
- **Ledger Cognitivo**: Auditoria e rastreabilidade
- **Feromônios Digitais**: Coordenação emergente
- **Stack de Observabilidade**: Métricas, traces e dashboards

**Nota:** ClickHouse é opcional para a Fase 1. Os testes continuarão mesmo se ClickHouse não estiver deployado.

---

## Pré-requisitos

### Ferramentas Necessárias

- `kubectl` (1.28+)
- `curl`
- `jq` (1.6+)
- `bash` (4.0+)

### Validar Instalação

```bash
kubectl version --client
curl --version
jq --version
```

### Cluster Kubernetes

- Cluster local (minikube, kind, k3s) ou remoto
- Acesso configurado via `~/.kube/config`
- Contexto correto selecionado

```bash
kubectl cluster-info
kubectl get nodes
```

### Autodetecção de Namespace e Tópicos Kafka

Os scripts de teste detectam automaticamente o namespace do Kafka buscando StatefulSets com label `strimzi.io/cluster`. Se não encontrado, usa o namespace padrão `neural-hive-kafka`.

**Nomes de tópicos aceitos:**
- `intentions.business` ou `intentions-business`
- `plans.ready` ou `plans-ready`
- `plans.consensus` ou `plans-consensus`

Os testes tentam publicar/consumir usando ambas as variantes (ponto e hífen) e utilizam a primeira que funcionar. Isso garante compatibilidade com diferentes configurações do Kafka.

### Recursos Mínimos Recomendados

| Componente | CPU | Memória | Armazenamento |
|------------|-----|---------|---------------|
| MongoDB    | 2   | 4 GB    | 20 GB         |
| Redis      | 1   | 2 GB    | 5 GB          |
| Neo4j      | 2   | 4 GB    | 20 GB         |
| ClickHouse | 2   | 4 GB    | 20 GB         |
| Kafka      | 2   | 4 GB    | 10 GB         |
| Specialists | 3   | 6 GB    | -             |
| Total      | 12+ | 24 GB+  | 75 GB+        |

---

## Preparação dos Testes

### 1. Pré-validação (Recomendado)

Execute a validação pré-teste para verificar se todos os componentes necessários estão deployados e prontos:

```bash
./tests/phase1-pre-test-validation.sh
```

**O que é verificado:**
- ✓ Ferramentas CLI necessárias
- ✓ Conectividade com cluster Kubernetes
- ✓ Infraestrutura (Kafka, MongoDB, Redis, Neo4j, ClickHouse)
- ✓ Serviços da Fase 1 (Gateway, STE, Specialists, Consensus Engine)
- ✓ Tópicos Kafka necessários
- ✓ Stack de observabilidade (Prometheus, Jaeger, Grafana)
- ✓ Artefatos de monitoramento (dashboards, alertas)

**Exemplo de saída:**

```
========================================
Neural Hive-Mind - Phase 1 Pre-Test Validation
========================================

Section 1: Tool Validation
ℹ Checking required tools...
✓ kubectl is installed
✓ curl is available
✓ jq is available
✓ kubectl can connect to cluster

Section 2: Infrastructure Validation
ℹ Verifying infrastructure components...
✓ Kafka cluster (3 replicas ready)
✓ Redis cluster (3 pods running)
✓ MongoDB cluster (3 replicas ready)
...

========================================
Validation Summary
========================================

Total Checks:   32
Passed:        32
Failed:        0
Success Rate:  100%

✅ All pre-test validation checks passed!
You are ready to run the Phase 1 end-to-end test.
```

### 2. Corrigir Problemas

Se a pré-validação falhar:

1. **Revisar pods com erro:**
   ```bash
   kubectl get pods --all-namespaces | grep -v Running
   ```

2. **Verificar logs de um pod específico:**
   ```bash
   kubectl logs -n <namespace> <pod-name> --tail=100
   ```

3. **Consultar documentação de deployment:**
   - `DEPLOYMENT_LOCAL.md` - Setup local
   - `TROUBLESHOOTING.md` - Problemas comuns

---

## Executando os Testes

### Teste End-to-End Completo

```bash
./tests/phase1-end-to-end-test.sh
```

### Opções Disponíveis

| Flag | Descrição |
|------|-----------|
| `--skip-pre-validation` | Pular pré-validação automática |
| `--debug` | Ativar saída verbosa de debug |
| `--continue-on-error` | Continuar teste mesmo com falhas |
| `--no-cleanup` | Não limpar recursos de teste ao final |
| `--output-dir DIR` | Diretório para relatórios (padrão: `./tests/results`) |
| `--help` | Exibir ajuda |

### Exemplos de Uso

**Modo padrão (recomendado):**
```bash
./tests/phase1-end-to-end-test.sh
```

**Modo debug para troubleshooting:**
```bash
./tests/phase1-end-to-end-test.sh --debug
```

**Continuar mesmo com falhas (para análise completa):**
```bash
./tests/phase1-end-to-end-test.sh --continue-on-error --debug
```

**Pular pré-validação (se já executada):**
```bash
./tests/phase1-end-to-end-test.sh --skip-pre-validation
```

---

## Interpretando os Resultados

### Estrutura de Saída

O teste produz saída estruturada em 5 fases:

#### FASE 1: Verificar Infraestrutura
- Validação de camadas de memória
- Validação de serviços da Fase 1

#### FASE 2: Testar Fluxo Completo
- Publicação de Intent Envelope no Kafka
- Geração de Cognitive Plan
- Avaliações dos 5 especialistas
- Decisão consolidada do Consensus Engine

#### FASE 3: Validar Persistência e Telemetria
- Registro no ledger cognitivo (MongoDB)
- Publicação de feromônios (Redis)
- Disponibilidade de métricas (Prometheus)
- Traces correlacionados (Jaeger)

#### FASE 4: Validar Governança
- Explicabilidade dos planos
- Integridade do ledger (hashes SHA-256)
- Compliance OPA Gatekeeper

#### FASE 5: Validar Dashboards e Alertas
- Dashboards Grafana existentes
- Alertas Prometheus configurados

### Exemplo de Saída Bem-Sucedida

```
========================================
FASE 2: Testando Fluxo Completo
========================================

ℹ 2.1 Publicando Intent Envelope de teste...
✓ Intent Envelope publicado no Kafka

ℹ 2.2 Aguardando geração de Cognitive Plan (10s)...
✓ Cognitive Plan gerado
   Plan ID: plan-abc123xyz

ℹ 2.3 Aguardando avaliação dos 5 especialistas (15s)...
✓ Specialist business avaliou o plano
✓ Specialist technical avaliou o plano
✓ Specialist behavior avaliou o plano
✓ Specialist evolution avaliou o plano
✓ Specialist architecture avaliou o plano
✓ Mínimo 3 de 5 especialistas avaliaram (5/5)

ℹ 2.4 Aguardando decisão consolidada (10s)...
✓ Decisão consolidada gerada
   Decision ID: decision-xyz789
```

### Relatórios Gerados

Os testes geram 3 tipos de relatórios no diretório `tests/results/`:

**1. Relatório JSON** (`phase1-test-report-YYYYMMDD-HHMMSS.json`)
```json
{
  "test_name": "Phase 1 End-to-End Test",
  "start_time": "2025-01-15T10:30:00Z",
  "end_time": "2025-01-15T10:32:45Z",
  "duration_seconds": 165,
  "results": [
    {
      "section": "Infrastructure",
      "status": "passed",
      "message": "mongodb-cluster deployed",
      "timestamp": "2025-01-15T10:30:15Z"
    },
    ...
  ],
  "summary": {
    "total": 28,
    "passed": 28,
    "failed": 0
  }
}
```

**2. Sumário Markdown** (`phase1-test-summary-YYYYMMDD-HHMMSS.md`)
```markdown
# Phase 1 End-to-End Test Summary

**Test Date:** 2025-01-15T10:30:00Z
**Intent ID:** test-intent-1705315800
**Plan ID:** plan-abc123xyz
**Decision ID:** decision-xyz789

## Test Results

- [PASSED] Infrastructure: mongodb-cluster deployed
- [PASSED] Services: gateway-intencoes deployed
...

## Summary

- **Total Tests:** 28
- **Passed:** 28
- **Failed:** 0
- **Duration:** 165s

✅ **All tests passed!**
```

**3. Relatório Executivo** (`PHASE1_E2E_EXECUTIVE_REPORT.md`)

Este relatório consolida informações dos relatórios JSON, Markdown e métricas de performance do Prometheus em um único documento executivo.

**Geração Automática**: O relatório executivo é gerado automaticamente ao final dos testes E2E.

**Geração Manual**: Para regenerar o relatório com dados atualizados:

```bash
# Executar script de geração de relatório executivo
./scripts/generate_e2e_executive_report.sh \
  tests/results/phase1-test-report-YYYYMMDD-HHMMSS.json \
  tests/results/phase1-test-summary-YYYYMMDD-HHMMSS.md \
  tests/results/performance-metrics-YYYYMMDD-HHMMSS.txt
```

**Conteúdo do Relatório**:
- Status geral da execução dos testes
- Tabela de resumo com testes executados, aprovados e falhados
- Latências observadas (média, mínima, máxima, P95)
- Cenários testados
- Trace IDs (Correlation IDs e Intent IDs)
- Métricas de performance do Prometheus (se disponíveis):
  - Latências P95 dos componentes (Plan Generation, Specialist Evaluation, Consensus, Ledger Write)
  - Throughput do sistema (Plans, Evaluations, Decisions)
  - Taxas de sucesso (Plan Generation, Consensus, Specialist Availability)
- Recomendações e próximos passos baseados nos resultados

**Exemplo de estrutura**:
```markdown
# Relatório Executivo - Teste End-to-End Fase 1
## Neural Hive-Mind - Sistema Cognitivo Distribuído

**Data de Execução**: 2025-01-15 10:30:00 UTC
**Status Geral**: ✅ SUCESSO COMPLETO

## 📊 Resumo Executivo

| Métrica | Valor | Status |
|---------|-------|--------|
| **Testes Executados** | 28 | - |
| **Testes Aprovados** | 28 | ✅ |
| **Testes Falhados** | 0 | ✅ |
| **Taxa de Sucesso** | 100% | ✅ |

...
```

**Extração de Métricas de Performance**:

Para incluir métricas do Prometheus no relatório executivo, execute:

```bash
# Port-forward Prometheus (em uma janela separada)
kubectl port-forward -n monitoring svc/prometheus 9090:9090 &

# Extrair métricas de performance
./scripts/extract-performance-metrics.sh tests/results http://localhost:9090 5m
```

O script `extract-performance-metrics.sh` aceita os seguintes parâmetros:
- `OUTPUT_DIR` (padrão: `tests/results`): Diretório de saída
- `PROMETHEUS_URL` (padrão: `http://localhost:9090`): URL do Prometheus
- `TIME_RANGE` (padrão: `5m`): Intervalo de tempo para as queries (ex: `5m`, `10m`, `1h`)

---

## Troubleshooting

### Problema: Intent Envelope não é processado

**Sintomas:**
```
✗ Cognitive Plan NÃO gerado
```

**Verificações:**

1. **Verificar tópico Kafka:**
   ```bash
   kubectl exec -n neural-hive-kafka neural-hive-kafka-0 -- \
     kafka-topics.sh --bootstrap-server localhost:9092 --list | grep intentions
   ```

2. **Verificar logs do Semantic Translation Engine:**
   ```bash
   kubectl logs -n semantic-translation-engine -l app.kubernetes.io/name=semantic-translation-engine --tail=50
   ```

3. **Verificar conectividade Kafka:**
   ```bash
   kubectl get svc -n neural-hive-kafka
   ```

### Problema: Specialists não avaliam o plano

**Sintomas:**
```
⚠ Mínimo de especialistas não avaliaram (1/5)
```

**Verificações:**

1. **Verificar pods dos specialists:**
   ```bash
   kubectl get pods -n specialist-business
   kubectl get pods -n specialist-technical
   kubectl get pods -n specialist-behavior
   kubectl get pods -n specialist-evolution
   kubectl get pods -n specialist-architecture
   ```

2. **Verificar logs de um specialist específico:**
   ```bash
   kubectl logs -n specialist-business -l app.kubernetes.io/name=specialist-business --tail=100
   ```

3. **Verificar tópico de planos:**
   ```bash
   kubectl exec -n neural-hive-kafka neural-hive-kafka-0 -- \
     kafka-console-consumer.sh --bootstrap-server localhost:9092 \
     --topic plans.ready --from-beginning --max-messages 5
   ```

### Problema: Métricas Prometheus não disponíveis

**Sintomas:**
```
⚠ Métricas Prometheus insuficientes (1/5)
```

**Verificações:**

1. **Verificar port-forward:**
   ```bash
   kubectl port-forward -n neural-hive-observability svc/prometheus 9090:9090
   ```

2. **Acessar Prometheus UI:**
   ```
   http://localhost:9090
   ```

3. **Consultar métricas manualmente:**
   ```bash
   curl -s http://localhost:9090/api/v1/query?query=neural_hive_specialist_evaluations_total | jq
   ```

4. **Extrair métricas de performance (manual):**
   ```bash
   # Se a stack de observabilidade não estiver completamente configurada
   ./scripts/extract-performance-metrics.sh tests/results http://localhost:9090
   ```

   Este script extrai P95 de latências e throughput dos componentes chave. Útil quando o Prometheus está parcialmente funcional.

### Problema: OPA Gatekeeper com violações

**Sintomas:**
```
✗ Políticas OPA Gatekeeper com 3 violações
```

**Verificações:**

1. **Listar todas as constraints:**
   ```bash
   kubectl get constraints -A
   ```

2. **Detalhar violações:**
   ```bash
   kubectl describe <constraint-kind> <constraint-name>
   ```

3. **Corrigir recursos violando políticas:**
   - Consultar `docs/GOVERNANCE.md` para políticas OPA
   - Ajustar manifests dos serviços

---

## Validação Manual

### Acessar Grafana

```bash
kubectl port-forward -n neural-hive-observability svc/grafana 3000:80
```

Abrir navegador: `http://localhost:3000`

**Dashboards Recomendados:**
- `Governance Executive Dashboard` - Visão executiva de governança
- `Specialists Cognitive Layer` - Performance dos specialists
- `Consensus & Governance` - Métricas de consenso
- `Memory Layer Data Quality` - Qualidade dos dados

### Acessar Jaeger

```bash
kubectl port-forward -n neural-hive-observability svc/jaeger-query 16686:16686
```

Abrir navegador: `http://localhost:16686`

**Filtrar por:**
- Service: `semantic-translation-engine`
- Tags: `neural.hive.intent.id:<intent-id>`

### Consultar MongoDB Ledger

```bash
MONGO_POD=$(kubectl get pods -n mongodb-cluster -l app=mongodb -o jsonpath='{.items[0].metadata.name}')

# Buscar por intent_id
kubectl exec -n mongodb-cluster $MONGO_POD -- \
  mongosh --quiet --eval "db.cognitive_ledger.find({intent_id: 'test-intent-1705315800'}).pretty()"

# Buscar por plan_id
kubectl exec -n mongodb-cluster $MONGO_POD -- \
  mongosh --quiet --eval "db.cognitive_ledger.find({plan_id: 'plan-abc123xyz'}).pretty()"

# Verificar explicabilidade
kubectl exec -n mongodb-cluster $MONGO_POD -- \
  mongosh --quiet --eval "db.explainability_ledger.find({plan_id: 'plan-abc123xyz'}).pretty()"
```

### Consultar Redis Pheromones

```bash
REDIS_POD=$(kubectl get pods -n redis-cluster -l app=redis -o jsonpath='{.items[0].metadata.name}')

# Listar todas as chaves de feromônios
kubectl exec -n redis-cluster $REDIS_POD -- redis-cli KEYS 'pheromone:*'

# Ver valor de um feromônio específico
kubectl exec -n redis-cluster $REDIS_POD -- redis-cli GET 'pheromone:specialist:business:confidence'
```

---

## Performance Benchmarks

### Latências Esperadas (P95)

| Etapa | Latência P95 | Timeout |
|-------|-------------|---------|
| Intent → Plan | < 500ms | 5s |
| Specialist Evaluation | < 200ms | 2s |
| Consensus Decision | < 300ms | 3s |
| Ledger Write | < 100ms | 1s |
| End-to-End (Intent → Decision) | < 2s | 10s |

### Throughput Esperado

- **Plans Generated:** 10-50 plans/min
- **Specialist Evaluations:** 50-250 evaluations/min
- **Consensus Decisions:** 10-50 decisions/min

### Métricas de Sucesso

- **Plan Generation Success Rate:** > 99%
- **Specialist Availability:** > 99.9%
- **Consensus Success Rate:** > 95%
- **Ledger Write Success:** > 99.9%

---

## Próximos Passos

Após teste bem-sucedido da Fase 1:

1. **Análise de Performance:**
   - Revisar dashboards Grafana
   - Identificar gargalos
   - Ajustar recursos se necessário

2. **Testes de Carga:**
   - Executar `tests/phase1-load-test.sh` (se disponível)
   - Validar comportamento sob carga

3. **Preparação para Fase 2:**
   - Consultar `docs/PHASE2_ARCHITECTURE.md`
   - Revisar componentes adicionais necessários

4. **Monitoramento Contínuo:**
   - Configurar alertas permanentes
   - Definir SLOs e SLIs
   - Estabelecer runbooks de troubleshooting

---

## Referências

- [Arquitetura da Fase 1](./PHASE1_ARCHITECTURE.md)
- [Deployment Local](./DEPLOYMENT_LOCAL.md)
- [Troubleshooting Guide](./TROUBLESHOOTING.md)
- [Governance Model](./GOVERNANCE.md)
- [Monitoring & Observability](./OBSERVABILITY.md)

---

**Última Atualização:** 2025-01-15
**Versão:** 1.0
**Mantenedor:** Neural Hive-Mind Team
