# Runbook: Troubleshooting Unified Gateway

**Tipo:** Troubleshooting transversal
**Componente:** Unified Gateway (`services/unified-gateway/`) + NLU service + PII service
**Spec:** `.agent-os/specs/2026-05-01-unified-gateway-architecture/`
**Última atualização:** 2026-05-09

---

## Descrição

Este runbook cobre **diagnóstico e resolução de incidentes** no Unified Gateway e respectivas dependências (NLU service, PII service, Redis, Kafka, MongoDB, gateways downstream). Está organizado por **sintoma observável** — encontra o sintoma mais próximo do que estás a ver, segue o diagnóstico e aplica a mitigação sugerida.

Para o procedimento de **deploy** (não troubleshooting), consulta `docs/runbooks/DEPLOY_UNIFIED_GATEWAY.md`.

## Mapa de Namespaces

| Componente | Namespace | Selector | Porta |
|-----------|-----------|----------|-------|
| Unified Gateway | `gateway` | `app=unified-gateway` | 7999 (HTTP) |
| NLU Service | `nlu` | `app=nlu-service` | 8020 (HTTP) / 8021 (gRPC) |
| PII Service | `pii` | `app=pii-service` | 8021 (HTTP) / 9021 (gRPC) |
| Redis (rate limiting) | `redis-cluster` | — | 6379 |
| Kafka (eventos) | `kafka` | — | 9092 |
| MongoDB | `mongodb-cluster` | — | 27017 |

---

## Sintomas Comuns e Diagnósticos

### 1. Pod em CrashLoopBackOff

**Sintomas:**
- `kubectl get pods -n gateway` mostra STATUS=CrashLoopBackOff.
- Pod reinicia continuamente.

**Diagnóstico:**

```bash
# 1. Ver pods e RESTARTS
kubectl get pods -n gateway -l app=unified-gateway

# 2. Eventos recentes
kubectl describe pod -n gateway <pod-name> | grep -A 20 Events:

# 3. Logs do crash actual
kubectl logs -n gateway <pod-name> --tail=200

# 4. Logs do crash anterior (após restart)
kubectl logs -n gateway <pod-name> --previous --tail=200
```

**Causas comuns:**
- ConfigMap/Secret em falta ou com chaves inválidas (ex.: `JWT_SECRET` indefinido).
- Dependência externa indisponível na startup (Kafka, Redis).
- OOMKilled (ver `kubectl describe` → `Last State: Terminated, Reason: OOMKilled`).

**Resolução:**
1. Verificar ConfigMap/Secret:
   ```bash
   kubectl get configmap unified-gateway-config -n gateway -o yaml
   kubectl get secret unified-gateway-secrets -n gateway -o yaml
   ```
2. Se OOMKilled, aumentar `resources.limits.memory` no deployment.
3. Se dependência externa, ver secção respectiva mais abaixo.

---

### 2. Liveness Probe Falha

**Sintomas:**
- `kubectl describe pod` mostra `Liveness probe failed: HTTP probe failed`.
- Pods reiniciam por falha de liveness.

**Diagnóstico:**

```bash
# 1. Testar /health diretamente do pod
kubectl exec -n gateway <pod-name> -- curl -fsS localhost:7999/health

# 2. Verificar dependências críticas: NLU e PII gRPC
kubectl exec -n gateway <pod-name> -- nc -zv nlu-service.nlu.svc.cluster.local 8021
kubectl exec -n gateway <pod-name> -- nc -zv pii-service.pii.svc.cluster.local 9021

# 3. Verificar Redis (rate limiting)
kubectl exec -n gateway <pod-name> -- nc -zv redis.redis-cluster.svc.cluster.local 6379

# 4. Inspecionar logs por timeouts ou bloqueios
kubectl logs -n gateway <pod-name> --tail=200 | grep -iE "timeout|connection.*refused|unavailable"
```

**Causas comuns:**
- Redis indisponível (não bloqueia /health diretamente, mas se rate limiter blocking startup, pode prender).
- NLU/PII gRPC down → falhas em endpoints de classificação.
- Aplicação trancada em loop síncrono (raro em FastAPI async, mas possível em I/O bloqueante).

**Resolução:**
1. Se dependência down, restaurá-la primeiro (ver secções 3 e 4).
2. Aumentar `livenessProbe.timeoutSeconds` temporariamente se houver lentidão sistémica.
3. Restart pod: `kubectl delete pod -n gateway <pod-name>`.

---

### 3. 5xx em `POST /api/v1/nhm/request`

**Sintomas:**
- Clientes a receber HTTP 500 / 502 / 503.
- Logs mostram `request_failed` ou `unhandled_exception`.

**Diagnóstico:**

```bash
# 1. Logs do gateway com detalhes do erro
kubectl logs -n gateway -l app=unified-gateway --tail=200 | grep -E "request_failed|unhandled_exception|gateway_response"

# 2. Verificar saúde dos gateways downstream (Flow A-F, G, H)
kubectl exec -n gateway -l app=unified-gateway -- curl -fsS http://gateway-intencoes.neural-hive.svc.cluster.local:8000/health
kubectl exec -n gateway -l app=unified-gateway -- curl -fsS http://requirements-engineering.neural-hive.svc.cluster.local:8010/health
kubectl exec -n gateway -l app=unified-gateway -- curl -fsS http://doc-ingestion.neural-hive.svc.cluster.local:8018/health

# 3. Verificar circuit breaker (configurado em CIRCUIT_BREAKER_THRESHOLD=5)
kubectl logs -n gateway -l app=unified-gateway --tail=500 | grep -iE "circuit.*open|circuit.*breaker"

# 4. Testar request E2E para reproduzir
kubectl port-forward -n gateway svc/unified-gateway 7999:7999 &
curl -X POST http://localhost:7999/api/v1/nhm/request \
  -H "Content-Type: application/json" \
  -d '{"input": "test", "language": "pt"}' -i
```

**Causas comuns:**
- Gateway downstream (gateway-intencoes / requirements-engineering / doc-ingestion) down.
- Circuit breaker aberto (após 5 falhas consecutivas).
- NLU service down → fallback ativo mas classificação degradada.

**Resolução:**
1. Restaurar gateway downstream afetado.
2. Aguardar circuit breaker fechar (timeout: 60s, half-open attempts: 3).
3. Se necessário, restart do gateway para forçar reset:
   ```bash
   kubectl rollout restart deployment/unified-gateway -n gateway
   ```

---

### 4. HTTP 429 (Rate Limit) Indevidos

**Sintomas:**
- Clientes recebem 429 em volumes que deveriam ser permitidos.
- Header `X-RateLimit-Remaining` chega rapidamente a 0.

**Diagnóstico:**

```bash
# 1. Logs de rate limiting
kubectl logs -n gateway -l app=unified-gateway --tail=200 | grep "rate_limit_exceeded"

# 2. Verificar tier do tenant (campo "roles" no JWT)
# Tiers configurados em src/middleware/rate_limit.py:
#   trial: 10 req/min
#   default: 100 req/min
#   enterprise: 1000 req/min

# 3. Inspecionar Redis (chaves de rate limit)
kubectl exec -n redis-cluster redis-cluster-0 -- redis-cli
# Dentro do CLI:
#   KEYS unified_gateway:rate_limit:*
#   GET unified_gateway:rate_limit:<tenant_id>:...:rate_limit:<window>
#   TTL unified_gateway:rate_limit:<tenant_id>:...:rate_limit:<window>

# 4. Verificar split-brain do Redis cluster
kubectl exec -n redis-cluster redis-cluster-0 -- redis-cli cluster info
kubectl exec -n redis-cluster redis-cluster-0 -- redis-cli cluster nodes
```

**Causas comuns:**
- Tenant classificado como `trial` quando deveria ser `default` ou `enterprise` (verificar claim `roles` no JWT).
- Tenant_id `anonymous` (JWT ausente ou middleware exclui auth) → todos partilham o mesmo bucket.
- Redis cluster com split-brain → contadores inconsistentes.

**Resolução:**
1. Confirmar conteúdo do JWT (tenant_id e roles correctos).
2. Se split-brain Redis: ver `docs/runbooks/redis-troubleshooting.md`.
3. Em emergência, desligar rate limiting:
   ```bash
   # ⚠️ Apenas emergência
   kubectl set env deployment/unified-gateway -n gateway RATE_LIMIT_ENABLED=false
   ```

---

### 5. Latência Alta (p95 > 20ms no gateway)

**Sintomas:**
- Latência p95 do gateway > baseline (objetivo: classificação < 20ms; pipeline E2E aceitável depende do downstream).
- `processing_time_ms` em logs muito alto.

**Diagnóstico:**

```bash
# 1. Logs com tempos de processamento
kubectl logs -n gateway -l app=unified-gateway --tail=500 | grep "processing_time_ms"

# 2. Métricas de utilização CPU/Mem
kubectl top pods -n gateway -l app=unified-gateway

# 3. HPA — está a escalar?
kubectl get hpa -n gateway unified-gateway-hpa
kubectl describe hpa -n gateway unified-gateway-hpa

# 4. Verificar latência do NLU (classificação é o passo crítico)
kubectl exec -n gateway -l app=unified-gateway -- \
  curl -w "@-" -o /dev/null -s http://nlu-service.nlu.svc.cluster.local:8020/health <<'EOF'
time_total: %{time_total}\n
EOF

# 5. Cache hit/miss do NLU client (cache local em ResilienceNLUService)
kubectl logs -n gateway -l app=unified-gateway --tail=500 | grep -iE "cache.*hit|cache.*miss"
```

**Causas comuns:**
- NLU service sob carga ou sem replicas suficientes.
- Cache miss elevado (cache local em memória, não partilhado entre pods).
- Gateway downstream lento → propaga para latência E2E.
- HPA não escalou ou atingiu `maxReplicas=10`.

**Resolução:**
1. Escalar manualmente se HPA bloqueado:
   ```bash
   kubectl scale deployment/unified-gateway -n gateway --replicas=5
   kubectl scale deployment/nlu-service -n nlu --replicas=5
   ```
2. Aumentar `maxReplicas` do HPA (editar `k8s/unified-gateway-deployment.yaml`).
3. Investigar gateway downstream (logs em `neural-hive` namespace).

---

### 6. JWT 401 Espalhado

**Sintomas:**
- Maioria dos requests devolve 401 Unauthorized de uma só vez.
- Logs mostram `jwt_invalid` ou `jwt_expired` em massa.

**Diagnóstico:**

```bash
# 1. Logs de JWT
kubectl logs -n gateway -l app=unified-gateway --tail=200 | grep -iE "jwt|unauthorized|401"

# 2. Verificar JWT_SECRET / JWKS_URL
kubectl get secret unified-gateway-secrets -n gateway -o yaml
kubectl get configmap unified-gateway-config -n gateway -o yaml | grep -i jwt

# 3. Se JWKS_URL estiver definido, testar acesso
kubectl exec -n gateway -l app=unified-gateway -- curl -fsS <JWKS_URL>

# 4. Verificar JWT_AUTH_REQUIRED
kubectl exec -n gateway -l app=unified-gateway -- env | grep JWT
```

**Causas comuns:**
- Secret rotacionado mas pods ainda têm valor antigo (não fizeram restart).
- JWKS endpoint indisponível.
- Algoritmo errado (`JWT_ALGORITHM` por defeito: `RS256` → exige chave pública).
- Token cliente expirado.

**Resolução:**
1. Se secret foi rotacionado, fazer rolling restart:
   ```bash
   kubectl rollout restart deployment/unified-gateway -n gateway
   ```
2. Confirmar JWKS endpoint acessível.
3. Em ambiente não-produção, é possível desligar temporariamente:
   ```bash
   kubectl set env deployment/unified-gateway -n gateway JWT_AUTH_REQUIRED=false
   # ⚠️ NUNCA em produção
   ```

---

### 7. Tracing Não Aparece no Backend

**Sintomas:**
- Spans não aparecem no backend de tracing (Jaeger / Tempo / etc.).
- `X-Trace-Parent` em respostas (em `development`) mostra trace_id válido, mas backend vazio.

**Diagnóstico:**

```bash
# 1. Verificar inicialização da observabilidade
kubectl logs -n gateway -l app=unified-gateway --tail=500 | grep -iE "observability_initialized|observability_init_failed|neural_hive_observability"

# Esperado em produção:
#   "observability_initialized"
# Se aparecer:
#   "neural_hive_observability not available - tracing disabled"
# significa que o pacote não foi instalado no container.

# 2. Verificar OTLP exporter (variável de ambiente)
kubectl exec -n gateway -l app=unified-gateway -- env | grep OTEL

# Variáveis típicas:
#   OTEL_EXPORTER_OTLP_ENDPOINT
#   OTEL_TRACES_SAMPLER
#   OTEL_TRACES_SAMPLER_ARG

# 3. Verificar conectividade ao collector
kubectl exec -n gateway -l app=unified-gateway -- nc -zv <otel-collector-host> 4317
```

**Causas comuns:**
- `neural_hive_observability` não disponível na imagem (gateway funciona sem tracing).
- OTLP endpoint mal configurado.
- Sampling rate a 0 (todos os spans descartados).

**Resolução:**
1. Confirmar pacote `neural_hive_observability` instalado no `requirements.txt` do unified-gateway.
2. Definir `OTEL_EXPORTER_OTLP_ENDPOINT` correto via ConfigMap.
3. Ajustar sampling: `OTEL_TRACES_SAMPLER=parentbased_traceidratio`, `OTEL_TRACES_SAMPLER_ARG=0.1`.

---

### 8. NLU Classifica Errado / Confiança Baixa

**Sintomas:**
- Requests roteados para o gateway downstream errado.
- Logs mostram `confidence` baixa em `classified_intent`.
- Fallback keyword-based ativo de forma persistente.

**Diagnóstico:**

```bash
# 1. Logs de classificação
kubectl logs -n gateway -l app=unified-gateway --tail=500 | grep -E "classified_intent|fallback"

# 2. Verificar saúde do NLU service
kubectl get pods -n nlu -l app=nlu-service
kubectl logs -n nlu -l app=nlu-service --tail=100

# 3. Testar NLU directamente (REST)
kubectl exec -n gateway -l app=unified-gateway -- \
  curl -fsS http://nlu-service.nlu.svc.cluster.local:8020/health

# 4. Testar gRPC (se houver tooling grpcurl no pod, caso contrário usar python)
kubectl exec -n gateway -l app=unified-gateway -- python -c "
import grpc
channel = grpc.insecure_channel('nlu-service.nlu.svc.cluster.local:8021')
print('gRPC channel:', channel)
"

# 5. Endpoint detalhado mostra resultado NLU completo
curl -X POST http://localhost:7999/api/v1/nhm/request/detailed \
  -H "Content-Type: application/json" \
  -d '{"input": "<input que classifica mal>", "language": "pt"}' | jq
```

**Causas comuns:**
- NLU service down → fallback `_fallback_nlu_result` ativo (retorna `DOMAIN_UNKNOWN` confidence 0.3).
- Idioma do input diferente de `DEFAULT_LANGUAGE` (pt) e modelo não suporta.
- Confidence threshold `0.5` no NLU mas modelo está abaixo desse valor.

**Resolução:**
1. Restaurar NLU service:
   ```bash
   kubectl rollout restart deployment/nlu-service -n nlu
   ```
2. Ajustar `CONFIDENCE_THRESHOLD` no ConfigMap do NLU se modelo estiver consistentemente abaixo.
3. Em último caso, passar `flow_type` explícito no request (debug):
   ```json
   {"input": "...", "flow_type": "FLOW_AF"}
   ```

---

## Comandos de Diagnóstico (Toolkit)

### Logs

```bash
# Tail dos últimos N logs (todos os pods do deployment)
kubectl logs -n gateway -l app=unified-gateway --tail=100

# Follow em tempo real
kubectl logs -n gateway -l app=unified-gateway -f --tail=50

# Logs de um pod específico (incluindo restart anterior)
kubectl logs -n gateway <pod-name> --previous --tail=200

# Filtrar erros
kubectl logs -n gateway -l app=unified-gateway --tail=500 | grep -iE "error|exception|traceback|critical"
```

### Estado dos Pods

```bash
# Lista com IPs e nodes
kubectl get pods -n gateway -l app=unified-gateway -o wide

# Describe (eventos, probes, recursos)
kubectl describe pod -n gateway <pod-name>

# Recursos consumidos
kubectl top pods -n gateway -l app=unified-gateway
kubectl top pods -n nlu -l app=nlu-service
kubectl top pods -n pii -l app=pii-service
```

### Health Checks

```bash
# Via exec (sem port-forward)
kubectl exec -n gateway <pod-name> -- curl -fsS localhost:7999/health
kubectl exec -n gateway <pod-name> -- curl -fsS localhost:7999/health/live
kubectl exec -n gateway <pod-name> -- curl -fsS localhost:7999/health/ready

# Via port-forward (acesso local)
kubectl port-forward -n gateway svc/unified-gateway 7999:7999
curl http://localhost:7999/health
curl http://localhost:7999/api/v1/nhm/capabilities
```

### Redis (Rate Limiting)

```bash
# Conectar ao Redis
kubectl exec -it -n redis-cluster redis-cluster-0 -- redis-cli

# Inspecionar chaves de rate limit do gateway
# (dentro do redis-cli)
KEYS unified_gateway:rate_limit:*
GET unified_gateway:rate_limit:<tenant_id>:rate_limit:<minute_window>
TTL unified_gateway:rate_limit:<tenant_id>:rate_limit:<minute_window>

# Estado do cluster
kubectl exec -n redis-cluster redis-cluster-0 -- redis-cli cluster info
kubectl exec -n redis-cluster redis-cluster-0 -- redis-cli cluster nodes
```

### Kafka (Eventos)

```bash
# Listar tópicos
kubectl exec -n kafka neural-hive-kafka-kafka-0 -- \
  kafka-topics.sh --bootstrap-server localhost:9092 --list | grep -iE "gateway"

# Tópicos esperados:
#   unifiedgateway_events  (produzido pelo unified-gateway)
#   gateway_events         (legado, do gateway-intencoes)

# Consumir mensagens recentes
kubectl exec -n kafka neural-hive-kafka-kafka-0 -- \
  kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic unifiedgateway_events \
  --from-beginning --max-messages 10

# Consumer groups (lag)
kubectl exec -n kafka neural-hive-kafka-kafka-0 -- \
  kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --list
```

### gRPC Downstream (NLU + PII)

```bash
# NLU gRPC (porta 8021)
kubectl exec -n gateway -l app=unified-gateway -- \
  nc -zv nlu-service.nlu.svc.cluster.local 8021

# PII gRPC (porta 9021)
kubectl exec -n gateway -l app=unified-gateway -- \
  nc -zv pii-service.pii.svc.cluster.local 9021

# Logs dos serviços
kubectl logs -n nlu -l app=nlu-service --tail=100
kubectl logs -n pii -l app=pii-service --tail=100
```

### Eventos do Cluster

```bash
# Eventos recentes do namespace gateway
kubectl get events -n gateway --sort-by='.lastTimestamp' | tail -30

# Eventos com warning ou error
kubectl get events -n gateway --field-selector type!=Normal
```

---

## Métricas-Chave a Observar

> **Nota importante:** O endpoint `/metrics` do Unified Gateway (porta 7999) actualmente expõe apenas as **métricas default** do `prometheus_client` (Python runtime / process metrics) montadas via `prometheus_client.make_asgi_app()`, mais qualquer auto-instrumentação fornecida por `neural_hive_observability` (OpenTelemetry).
>
> **Métricas customizadas** específicas do unified-gateway (request count por flow_type, latência de classificação, contador de rate limit excedido, etc.) **ainda não estão definidas no código** em `services/unified-gateway/src/`. As métricas listadas abaixo como `unified_gateway_*` são **propostas/expectativas** e **TODO confirmar** quando custom instrumentation for adicionada (ver issues abertos).

### Métricas Default (já expostas)

| Métrica | Descrição |
|---------|-----------|
| `process_cpu_seconds_total` | CPU consumido pelo processo. |
| `process_resident_memory_bytes` | Memória RSS. |
| `python_gc_collections_total` | Contagem de GC do Python. |
| `python_info` | Versão do Python. |

### Métricas Propostas (TODO confirmar — ainda não implementadas)

| Métrica | Descrição | Estado |
|---------|-----------|--------|
| `unified_gateway_requests_total{status_code, flow_type}` | Total de requests por status e flow. | **TODO confirmar** |
| `unified_gateway_latency_seconds_bucket` | Histograma de latência E2E. | **TODO confirmar** |
| `unified_gateway_rate_limit_exceeded_total{tenant_id, tier}` | Contador de 429s. | **TODO confirmar** |
| `unified_gateway_classification_confidence` | Histograma de confidence da classificação. | **TODO confirmar** |
| `unified_gateway_circuit_breaker_state{gateway}` | Estado do circuit breaker (0=closed, 1=open, 2=half-open). | **TODO confirmar** |
| `unified_gateway_nlu_fallback_total` | Contador de uso do fallback keyword-based. | **TODO confirmar** |

Enquanto estas métricas não existirem como Prometheus instruments no código, **o sinal observável vem dos logs estruturados** (`structlog`):
- `processing_nhm_request`, `classified_intent`, `gateway_response`, `request_completed`, `request_failed`, `rate_limit_exceeded`.

### Sinais por Logs (alternativa a métricas)

```bash
# Taxa de erros nos últimos 200 requests
kubectl logs -n gateway -l app=unified-gateway --tail=2000 | \
  grep -E "request_completed|request_failed" | \
  awk '/request_failed/{f++} /request_completed/{c++} END {print "failed:", f, "completed:", c}'

# Latência média
kubectl logs -n gateway -l app=unified-gateway --tail=1000 | \
  grep "processing_time_ms" | \
  grep -oE "processing_time_ms=[0-9]+" | \
  awk -F= '{sum+=$2; n++} END {if (n>0) print "avg ms:", sum/n}'

# Distribuição de flow_types
kubectl logs -n gateway -l app=unified-gateway --tail=1000 | \
  grep -oE "flow_type=[A-Z_]+" | sort | uniq -c | sort -rn
```

---

## Escalation

| Tempo | Ação | Responsável |
|-------|------|-------------|
| 0-5 min | Diagnóstico inicial seguindo este runbook | Oncall (DevOps) |
| 5-15 min | Restart pods, verificar dependências | Oncall |
| 15-30 min | Rollback (ver `DEPLOY_UNIFIED_GATEWAY.md`) se sintomas surgiram pós-deploy | Oncall + tech lead |
| > 30 min | Escalar para equipa Platform e abrir incident report | Tech lead |
| Crítico (P0) | Notificar equipa de produto e stakeholders | Engineering Manager |

### Quando Contactar Outras Equipas

- **NLU service não recupera:** equipa ML/NLU.
- **Redis cluster split-brain:** equipa Platform / DBA.
- **Kafka indisponível:** equipa Platform / Streaming.
- **Gateway downstream (gateway-intencoes / requirements-engineering / doc-ingestion) down:** consultar runbook respectivo na pasta `docs/runbooks/`.

---

## Pós-Incidente

Após resolução de qualquer incidente:

1. **Documentar timeline** no canal de incident response.
2. **Criar post-mortem** se severidade ≥ P1.
3. **Atualizar este runbook** se foi descoberto um novo sintoma/diagnóstico.
4. **Abrir tickets** para:
   - Métricas Prometheus customizadas (caso ausentes — ver secção Métricas).
   - Alertas em falta no Prometheus rules.
   - Hardening (timeouts, retries, circuit breakers) se houver ponto fraco.

---

## Referências

- **Spec:** `.agent-os/specs/2026-05-01-unified-gateway-architecture/spec.md`
- **Deploy runbook:** `docs/runbooks/DEPLOY_UNIFIED_GATEWAY.md`
- **Código:** `services/unified-gateway/src/`
- **Manifests:**
  - `k8s/unified-gateway-deployment.yaml`
  - `k8s/nlu-service-deployment.yaml`
  - `k8s/pii-service-deployment.yaml`
- **Middlewares:**
  - `services/unified-gateway/src/middleware/jwt_auth.py`
  - `services/unified-gateway/src/middleware/rate_limit.py`
  - `services/unified-gateway/src/middleware/tracing.py`
- **Runbooks relacionados:**
  - `docs/runbooks/redis-troubleshooting.md`
  - `docs/runbooks/kafka-hot-partition.md`
  - `docs/runbooks/initialization-errors.md`
