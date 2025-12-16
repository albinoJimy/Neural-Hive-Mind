# Guia de Queries e Filtros Jaeger - Neural Hive

Este guia fornece queries prontas para uso no Jaeger UI e via API para monitoramento e troubleshooting do Neural Hive.

## 1. Queries por Contexto de Negócio

### Tabela de Queries Comuns

| Caso de Uso | Query Jaeger UI | Query API (curl) |
|-------------|-----------------|------------------|
| Buscar por intent_id | `Service: *, Tags: neural.hive.intent.id=<id>` | `curl "http://jaeger-query:16686/api/traces?tag=neural.hive.intent.id:<id>"` |
| Buscar por plan_id | `Service: *, Tags: neural.hive.plan.id=<id>` | `curl "http://jaeger-query:16686/api/traces?tag=neural.hive.plan.id:<id>"` |
| Buscar por user_id | `Service: *, Tags: neural.hive.user.id=<id>` | `curl "http://jaeger-query:16686/api/traces?tag=neural.hive.user.id:<id>"` |
| Buscar por domínio | `Service: *, Tags: neural.hive.domain=<domain>` | `curl "http://jaeger-query:16686/api/traces?tag=neural.hive.domain:<domain>"` |
| Traces com erro | `Service: *, Tags: error=true` | `curl "http://jaeger-query:16686/api/traces?tag=error:true"` |
| Traces lentos (>5s) | `Service: gateway-intencoes, Min Duration: 5s` | `curl "http://jaeger-query:16686/api/traces?service=gateway-intencoes&minDuration=5s"` |
| Por specialist | `Service: specialist-business` | `curl "http://jaeger-query:16686/api/traces?service=specialist-business"` |
| Por checkpoint | `Service: *, Tags: neural.hive.checkpoint=C3` | `curl "http://jaeger-query:16686/api/traces?tag=neural.hive.checkpoint:C3"` |

### Valores de Domínio Disponíveis

- `experiencia` - Camada de experiência do usuário
- `cognicao` - Camada de processamento cognitivo
- `execucao` - Camada de execução
- `business` - Domínio de negócios
- `technical` - Domínio técnico
- `architecture` - Domínio de arquitetura
- `behavior` - Domínio comportamental
- `evolution` - Domínio de evolução

## 2. Queries Compostas (Múltiplos Filtros)

### Buscar traces de um usuário específico com erro em um domínio

```bash
curl "http://jaeger-query:16686/api/traces?\
tag=neural.hive.user.id:<user-id>&\
tag=neural.hive.domain:experiencia&\
tag=error:true&\
limit=50" | jq
```

### Buscar traces de planos rejeitados pelo consensus

```bash
curl "http://jaeger-query:16686/api/traces?\
service=consensus-engine&\
tag=neural.hive.decision:reject&\
lookback=24h" | jq
```

### Buscar traces com alta latência em specialists

```bash
curl "http://jaeger-query:16686/api/traces?\
service=specialist-business&\
operation=Evaluate&\
minDuration=2s&\
limit=100" | jq
```

### Buscar traces de workflows Temporal com falha

```bash
curl "http://jaeger-query:16686/api/traces?\
service=orchestrator-dynamic&\
tag=temporal.workflow.status:failed&\
lookback=6h" | jq
```

### Buscar traces por período específico

```bash
# Últimas 2 horas
START_TIME=$(($(date +%s) - 7200))000000
END_TIME=$(date +%s)000000

curl "http://jaeger-query:16686/api/traces?\
service=gateway-intencoes&\
start=$START_TIME&\
end=$END_TIME&\
limit=100" | jq
```

### Buscar traces com checkpoint específico que falhou

```bash
curl "http://jaeger-query:16686/api/traces?\
tag=neural.hive.checkpoint:C4&\
tag=neural.hive.checkpoint.status:failed&\
limit=50" | jq
```

## 3. Scripts de Análise de Traces

### Script 1: Analisar latência por fase do fluxo

```bash
#!/bin/bash
# scripts/observability/analyze-trace-latency.sh
# Uso: ./analyze-trace-latency.sh <trace-id>

TRACE_ID=$1
JAEGER_URL="${JAEGER_URL:-http://jaeger-query:16686}"

if [ -z "$TRACE_ID" ]; then
    echo "Uso: $0 <trace-id>"
    exit 1
fi

echo "Analisando trace: $TRACE_ID"
echo "================================"

curl -s "$JAEGER_URL/api/traces/$TRACE_ID" | \
  jq -r '.data[0].spans[] | "\(.operationName): \((.duration / 1000) | round)ms"' | \
  sort -t: -k2 -rn

echo ""
echo "Top 5 spans mais lentos:"
curl -s "$JAEGER_URL/api/traces/$TRACE_ID" | \
  jq -r '.data[0].spans | sort_by(-.duration) | .[0:5][] | "  \(.operationName): \((.duration / 1000) | round)ms"'
```

### Script 2: Extrair todos os intent_ids de um período

```bash
#!/bin/bash
# scripts/observability/extract-intent-ids.sh
# Uso: ./extract-intent-ids.sh [horas_atras]

HOURS_AGO=${1:-1}
JAEGER_URL="${JAEGER_URL:-http://jaeger-query:16686}"

START_TIME=$(($(date +%s) - ($HOURS_AGO * 3600)))000000
END_TIME=$(date +%s)000000

echo "Extraindo intent_ids das últimas $HOURS_AGO hora(s)..."

curl -s "$JAEGER_URL/api/traces?\
service=gateway-intencoes&\
start=$START_TIME&\
end=$END_TIME&\
limit=1000" | \
  jq -r '.data[].spans[] |
    select(.tags[] | select(.key=="neural.hive.intent.id")) |
    .tags[] | select(.key=="neural.hive.intent.id") | .value' | \
  sort -u

echo ""
echo "Total de intent_ids únicos: $(curl -s "$JAEGER_URL/api/traces?\
service=gateway-intencoes&\
start=$START_TIME&\
end=$END_TIME&\
limit=1000" | \
  jq -r '.data[].spans[] |
    select(.tags[] | select(.key=="neural.hive.intent.id")) |
    .tags[] | select(.key=="neural.hive.intent.id") | .value' | \
  sort -u | wc -l)"
```

### Script 3: Gerar relatório de erros por serviço

```bash
#!/bin/bash
# scripts/observability/error-report.sh
# Uso: ./error-report.sh [horas_atras]

HOURS_AGO=${1:-24}
JAEGER_URL="${JAEGER_URL:-http://jaeger-query:16686}"

echo "Relatório de Erros - Últimas $HOURS_AGO horas"
echo "=============================================="

# Lista de serviços Neural Hive
SERVICES=(
    "gateway-intencoes"
    "orchestrator-dynamic"
    "consensus-engine"
    "specialist-business"
    "specialist-technical"
    "specialist-architecture"
    "specialist-behavior"
    "specialist-evolution"
    "queen-agent"
    "execution-ticket-service"
    "worker-agents"
)

for SERVICE in "${SERVICES[@]}"; do
    COUNT=$(curl -s "$JAEGER_URL/api/traces?\
service=$SERVICE&\
tag=error:true&\
lookback=${HOURS_AGO}h&\
limit=1000" | jq '.data | length')

    if [ "$COUNT" -gt 0 ]; then
        echo "  $SERVICE: $COUNT traces com erro"
    fi
done

echo ""
echo "Erros mais comuns:"
curl -s "$JAEGER_URL/api/traces?tag=error:true&lookback=${HOURS_AGO}h&limit=100" | \
  jq -r '.data[].spans[] | select(.tags[] | select(.key=="error" and .value==true)) |
    .tags[] | select(.key=="error.message") | .value' | \
  sort | uniq -c | sort -rn | head -10
```

### Script 4: Calcular latência P50/P95/P99 por serviço

```bash
#!/bin/bash
# scripts/observability/latency-percentiles.sh
# Uso: ./latency-percentiles.sh <service> [horas_atras]

SERVICE=$1
HOURS_AGO=${2:-1}
JAEGER_URL="${JAEGER_URL:-http://jaeger-query:16686}"

if [ -z "$SERVICE" ]; then
    echo "Uso: $0 <service> [horas_atras]"
    exit 1
fi

echo "Análise de Latência: $SERVICE"
echo "=============================="

# Extrair durações
DURATIONS=$(curl -s "$JAEGER_URL/api/traces?\
service=$SERVICE&\
lookback=${HOURS_AGO}h&\
limit=500" | \
  jq -r '[.data[].spans[] | select(.operationName | startswith("POST") or startswith("GET") or . == "Evaluate") | .duration / 1000] | sort | @csv' | \
  tr ',' '\n')

if [ -z "$DURATIONS" ]; then
    echo "Nenhum trace encontrado"
    exit 0
fi

# Calcular percentis
TOTAL=$(echo "$DURATIONS" | wc -l)
P50_IDX=$((TOTAL * 50 / 100))
P95_IDX=$((TOTAL * 95 / 100))
P99_IDX=$((TOTAL * 99 / 100))

P50=$(echo "$DURATIONS" | sed -n "${P50_IDX}p")
P95=$(echo "$DURATIONS" | sed -n "${P95_IDX}p")
P99=$(echo "$DURATIONS" | sed -n "${P99_IDX}p")
MIN=$(echo "$DURATIONS" | head -1)
MAX=$(echo "$DURATIONS" | tail -1)

echo "  Traces analisados: $TOTAL"
echo "  Min: ${MIN}ms"
echo "  P50: ${P50}ms"
echo "  P95: ${P95}ms"
echo "  P99: ${P99}ms"
echo "  Max: ${MAX}ms"
```

### Script 5: Rastrear fluxo completo de uma intenção

```bash
#!/bin/bash
# scripts/observability/trace-intent-flow.sh
# Uso: ./trace-intent-flow.sh <intent-id>

INTENT_ID=$1
JAEGER_URL="${JAEGER_URL:-http://jaeger-query:16686}"

if [ -z "$INTENT_ID" ]; then
    echo "Uso: $0 <intent-id>"
    exit 1
fi

echo "Rastreando fluxo da intenção: $INTENT_ID"
echo "=========================================="

# Buscar traces
TRACES=$(curl -s "$JAEGER_URL/api/traces?tag=neural.hive.intent.id:$INTENT_ID&limit=10")

if [ "$(echo $TRACES | jq '.data | length')" -eq 0 ]; then
    echo "Nenhum trace encontrado para intent_id: $INTENT_ID"
    exit 1
fi

# Extrair serviços participantes
echo ""
echo "Serviços participantes:"
echo "$TRACES" | jq -r '.data[].processes | to_entries[] | .value.serviceName' | sort -u | while read SERVICE; do
    echo "  - $SERVICE"
done

# Extrair timeline de operações
echo ""
echo "Timeline de operações:"
echo "$TRACES" | jq -r '.data[0].spans | sort_by(.startTime) | .[] |
    "  \(.startTime / 1000000 | strftime("%H:%M:%S")) | \(.operationName) (\((.duration / 1000) | round)ms)"'

# Verificar erros
ERRORS=$(echo "$TRACES" | jq '[.data[].spans[] | select(.tags[] | select(.key=="error" and .value==true))] | length')
if [ "$ERRORS" -gt 0 ]; then
    echo ""
    echo "⚠️  Erros encontrados: $ERRORS"
    echo "$TRACES" | jq -r '.data[].spans[] |
        select(.tags[] | select(.key=="error" and .value==true)) |
        "  - \(.operationName): \(.tags[] | select(.key=="error.message") | .value)"'
fi

# Verificar propagação de contexto
echo ""
echo "Propagação de contexto:"
echo "$TRACES" | jq -r '.data[0].spans[] |
    select(.tags[] | select(.key=="neural.hive.intent.id")) |
    "\(.operationName): intent_id ✓"' | head -5

PLAN_ID=$(echo "$TRACES" | jq -r '.data[0].spans[].tags[] | select(.key=="neural.hive.plan.id") | .value' | head -1)
if [ -n "$PLAN_ID" ] && [ "$PLAN_ID" != "null" ]; then
    echo "  plan_id gerado: $PLAN_ID"
fi
```

## 4. Dashboards Jaeger Customizados

### Dashboard de Latência por Domínio

**Configuração no Jaeger UI:**

1. Acesse Jaeger UI: `http://jaeger-query:16686`
2. Na aba "Search", configure:
   - Service: `*` (todos)
   - Tags: `neural.hive.domain=<domain>`
   - Lookback: `1h`
3. Clique em "Find Traces"
4. Use "Compare" para comparar traces de diferentes domínios

### Dashboard de Taxa de Erro por Specialist

**Query para cada specialist:**

```bash
# Calcular taxa de erro para cada specialist
for SPECIALIST in business technical architecture behavior evolution; do
    TOTAL=$(curl -s "http://jaeger-query:16686/api/traces?service=specialist-$SPECIALIST&lookback=1h&limit=1000" | jq '.data | length')
    ERRORS=$(curl -s "http://jaeger-query:16686/api/traces?service=specialist-$SPECIALIST&tag=error:true&lookback=1h&limit=1000" | jq '.data | length')

    if [ "$TOTAL" -gt 0 ]; then
        RATE=$(echo "scale=2; $ERRORS * 100 / $TOTAL" | bc)
        echo "specialist-$SPECIALIST: $RATE% de erro ($ERRORS/$TOTAL)"
    else
        echo "specialist-$SPECIALIST: sem traces"
    fi
done
```

### Dashboard de Cobertura de Tracing

**Verificar serviços com traces:**

```bash
#!/bin/bash
# scripts/observability/tracing-coverage.sh

EXPECTED_SERVICES=(
    "gateway-intencoes"
    "orchestrator-dynamic"
    "consensus-engine"
    "semantic-translation-engine"
    "specialist-business"
    "specialist-technical"
    "specialist-architecture"
    "specialist-behavior"
    "specialist-evolution"
    "queen-agent"
    "execution-ticket-service"
    "worker-agents"
    "service-registry"
    "guard-agents"
    "mcp-tool-catalog"
)

echo "Cobertura de Tracing - Neural Hive"
echo "==================================="

# Obter serviços com traces
ACTIVE_SERVICES=$(curl -s "http://jaeger-query:16686/api/services" | jq -r '.data[]')

COVERED=0
MISSING=0

for SERVICE in "${EXPECTED_SERVICES[@]}"; do
    if echo "$ACTIVE_SERVICES" | grep -q "^$SERVICE$"; then
        echo "  ✓ $SERVICE"
        ((COVERED++))
    else
        echo "  ✗ $SERVICE (sem traces)"
        ((MISSING++))
    fi
done

echo ""
echo "Cobertura: $COVERED/${#EXPECTED_SERVICES[@]} serviços"
echo "Percentual: $(echo "scale=1; $COVERED * 100 / ${#EXPECTED_SERVICES[@]}" | bc)%"
```

## 5. Queries para Monitoramento Contínuo

### Health Check de Tracing

```bash
#!/bin/bash
# Verificar se tracing está funcionando

# 1. Verificar Jaeger está acessível
if ! curl -s "http://jaeger-query:16686/api/services" > /dev/null; then
    echo "CRITICAL: Jaeger Query não acessível"
    exit 2
fi

# 2. Verificar se há traces recentes
RECENT_TRACES=$(curl -s "http://jaeger-query:16686/api/traces?service=gateway-intencoes&lookback=5m&limit=1" | jq '.data | length')

if [ "$RECENT_TRACES" -eq 0 ]; then
    echo "WARNING: Sem traces nos últimos 5 minutos"
    exit 1
fi

echo "OK: Tracing funcionando ($RECENT_TRACES traces recentes)"
exit 0
```

### Alertas Baseados em Queries

```bash
# Query para alertar quando taxa de erro > 5%
TOTAL=$(curl -s "http://jaeger-query:16686/api/traces?service=gateway-intencoes&lookback=15m&limit=1000" | jq '.data | length')
ERRORS=$(curl -s "http://jaeger-query:16686/api/traces?service=gateway-intencoes&tag=error:true&lookback=15m&limit=1000" | jq '.data | length')

if [ "$TOTAL" -gt 0 ]; then
    ERROR_RATE=$(echo "scale=2; $ERRORS * 100 / $TOTAL" | bc)
    if (( $(echo "$ERROR_RATE > 5" | bc -l) )); then
        echo "ALERT: Taxa de erro alta: $ERROR_RATE%"
    fi
fi
```

## 6. Integração com Grafana

### Configurar Jaeger como Data Source

```yaml
# grafana-datasources.yaml
apiVersion: 1
datasources:
  - name: Jaeger
    type: jaeger
    access: proxy
    url: http://jaeger-query:16686
    isDefault: false
    jsonData:
      tracesToLogsV2:
        datasourceUid: loki
        spanStartTimeShift: "-1h"
        spanEndTimeShift: "1h"
        tags:
          - key: "neural.hive.intent.id"
            value: "intent_id"
          - key: "neural.hive.plan.id"
            value: "plan_id"
```

### Query Grafana para Traces

```
# No painel Grafana Explore, selecione datasource Jaeger
# Use a query:
{service="gateway-intencoes"} | trace_duration > 1s
```

## 7. Referência Rápida

### Atributos Neural Hive

| Atributo | Descrição | Exemplo |
|----------|-----------|---------|
| `neural.hive.intent.id` | ID único da intenção | `intent-a1b2c3d4-...` |
| `neural.hive.plan.id` | ID do plano cognitivo | `plan-e5f6g7h8-...` |
| `neural.hive.user.id` | ID do usuário | `user-12345` |
| `neural.hive.domain` | Domínio da operação | `business`, `technical` |
| `neural.hive.component` | Componente do serviço | `gateway`, `orchestrator` |
| `neural.hive.layer` | Camada arquitetural | `experiencia`, `cognicao`, `execucao` |
| `neural.hive.checkpoint` | Checkpoint de validação | `C1`, `C2`, ..., `C6` |
| `neural.hive.specialist.type` | Tipo do specialist | `business`, `technical` |

### Operações Comuns por Serviço

| Serviço | Operações |
|---------|-----------|
| gateway-intencoes | `POST /intents/text`, `asr.process`, `nlu.process`, `kafka.produce` |
| orchestrator-dynamic | `kafka.consume`, `orchestration_workflow.run`, `generate_execution_tickets` |
| specialist-* | `Evaluate`, `model.predict`, `model.inference` |
| consensus-engine | `aggregate_opinions`, `generate_decision` |
| queen-agent | `strategic_decision`, `approve_exception` |

### Filtros de Duração

| Filtro | Descrição |
|--------|-----------|
| `minDuration=100ms` | Traces > 100ms |
| `minDuration=1s` | Traces > 1 segundo |
| `minDuration=5s` | Traces > 5 segundos |
| `maxDuration=100ms` | Traces < 100ms |
