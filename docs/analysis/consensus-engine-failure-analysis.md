# Análise Profunda da Falha: Consensus-Engine em Staging

## Resumo Executivo

**Status:** Deployment do `consensus-engine` falhando no namespace `neural-hive-staging`
- Pods ficam em estado `0/1 Running`
- Readiness probe falha consistentemente com timeout (3s)
- Deployment não conclui rollout após ~10 minutos

---

## 1. Diagnóstico Detalhado

### 1.1 Situação Atual dos Pods

```
NAMESPACE: neural-hive-staging

consensus-engine-654bf5545c-jjqgv   0/1   Running   0   96s   IP: 10.244.1.126
consensus-engine-654bf5545c-tzxlv   0/1   Running   0   96s   IP: 10.244.2.133
```

**Observações:**
- Ambos os pods foram recriados há ~2 minutos (deployment recente)
- Nenhum pod alcançou status "Ready"
- Idade indica múltiplas tentativas de recriação

### 1.2 Configuração dos Probes

**Liveness Probe:**
- Endpoint: `http://:8000/health`
- Timeout: 5s
- Period: 10s
- Failure Threshold: 3

**Readiness Probe:**
- Endpoint: `http://:8000/ready` ⚠️ **FALHANDO**
- Timeout: 3s ⚠️ **MUITO CURTO**
- Period: 5s
- Failure Threshold: 3

**Startup Probe:**
- Endpoint: `http://:8000/health`
- Timeout: 5s
- Period: 10s
- Failure Threshold: 15

### 1.3 Mensagens de Erro dos Eventos

```
LAST SEEN   TYPE      REASON      MESSAGE
2m58s       Warning   Unhealthy   Readiness probe failed: Get "http://10.244.2.132:8000/ready": 
                              context deadline exceeded (Client.Timeout exceeded while awaiting headers)
```

**Interpretação:** O readiness probe atinge o timeout de 3s antes de receber resposta do endpoint `/ready`.

---

## 2. Análise do Comportamento da Aplicação

### 2.1 Inicialização Bem-Sucedida

A aplicação inicia corretamente:
```
✅ INFO: Started server process [1]
✅ INFO: Waiting for application startup
✅ INFO: Iniciando Consensus Engine (environment=dev)
✅ INFO: Servidor Prometheus iniciado na porta 8080
✅ INFO: Observabilidade inicializada com sucesso
✅ INFO: Health check 'otel_pipeline' registrado
```

### 2.2 Conectividade MongoDB

```
✅ MongoDB conectado com sucesso
✅ Connection pool created (maxPoolSize: 50)
✅ Server heartbeat succeeding (ismaster: true)
✅ Topology monitoring ativo
✅ Indexes criados/verificados:
   - decision_id_1 (unique)
   - plan_id_1
   - intent_id_1
   - created_at_1
   - hash_1
   - final_decision_1_created_at_-1
   - token_1 (unique) - consensus_explainability
```

### 2.3 Problema Crítico Identificado: OTEL Pipeline

**Logs recorrentes a cada ~5-7 segundos:**
```
🔴 WARNING: otel_pipeline_unhealthy - OTEL Collector not reachable
🔴 DEBUG: neural_hive_observability.health_checks.otel - OTEL collector health check error
```

**Endpoint OTEL configurado:**
```
otel_endpoint=https://opentelemetry-collector.observability.svc.cluster.local:4317
```

### 2.4 Comportamento do Endpoint /ready

**Health Check (/health):**
- ✅ Funciona normalmente
- ✅ Retorna HTTP 200 OK
- ✅ Responde rapidamente

**Readiness Check (/ready):**
- 🔴 Retorna HTTP 503 Service Unavailable
- 🔴 Timeout de 3s é insuficiente
- 🔴 Bloqueado pela verificação do OTEL Collector

---

## 3. Causa Raiz da Falha

### 3.1 Cadeia de Dependências

```
Readiness Probe (K8s)
    ↓ Timeout: 3s
Endpoint /ready (Aplicação)
    ↓ Verifica todos os health checks registrados
Health Check 'otel_pipeline'
    ↓ Tenta conectar ao OTEL Collector
OTEL Collector (observability namespace)
    ↴ INDISPONÍVEL / NÃO RESPONDE
    
Resultado: Timeout da requisição > 3s → Readiness FAIL
```

### 3.2 Por Que /health Funciona Mas /ready Não?

**Endpoint /health:**
- Verifica apenas checks críticos de sobrevivência
- Não inclui dependências externas opcionais
- Retorna rápido

**Endpoint /ready:**
- Verifica TODOS os checks registrados
- Inclui 'otel_pipeline' como dependência obrigatória
- Aguarda timeout da conexão OTEL (muito lento)
- Excede os 3s do readiness probe

### 3.3 Evidence Técnica

**Código fonte implícito:**
```python
# No módulo de health checks
health_checks = [
    'memory',           # ✅ Rápido
    'otel_pipeline',    # ❌ Lento (tentando conectar endpoint inalcançável)
]

@app.get("/ready")
def readiness():
    for check in health_checks:
        if not check.is_healthy():
            return 503  # Falha se QUALQUER check falhar
    return 200
```

---

## 4. Impactos do Problema

### 4.1 Efeito no Deployment

```
Deployment Status:
- Replicas: 2 desired | 2 updated | 2 total | 0 available | 2 unavailable
- Conditions:
  - Available: False (MinimumReplicasUnavailable)
  - Progressing: True (ReplicaSetUpdated)

RollingUpdate Strategy:
- MaxUnavailable: 0 (não permite pods indisponíveis)
- MaxSurge: 1
- Resultado: Deployment travado, pods antigos mantidos
```

### 4.2 Tentativas de Rollout

```
Timeline de Eventos (últimos 60 minutos):
- consensus-engine-75474cb659 (60m atrás)
- consensus-engine-58695b7cf8 (42m atrás)
- consensus-engine-d6857c945 (29m atrás)
- consensus-engine-9b69f4dc4 (24m atrás)
- consensus-engine-6f84575959 (20m atrás)
- consensus-engine-67c9d96744 (8m atrás)
- consensus-engine-654bf5545c (atual, 97s)

Total: 7 tentativas de deployment em 60 minutos
```

---

## 5. Soluções Propostas

### 5.1 Solução Imediata (Hotfix)

**Opção A: Desabilitar health check OTEL no /ready**
```python
# Alterar o check de 'otel_pipeline' para não bloquear readiness
# ou remover do readiness mas manter no health geral
```

**Opção B: Aumentar timeout do readiness probe**
```yaml
# No deployment/kubernetes
readinessProbe:
  timeoutSeconds: 10  # Aumentar de 3s para 10s
  periodSeconds: 10   # Aumentar também
```

**Opção C: Tornar OTEL opcional para readiness**
```python
# Lógica de health check modificada
if check == 'otel_pipeline' and check_fails:
    log_warning()  # Logar mas não falhar readiness
    continue  # Permitir que outros checks passem
```

### 5.2 Solução Definitiva

**Investigar por que OTEL Collector está indisponível:**

```bash
# Comandos para diagnóstico
kubectl get pods -n observability
kubectl logs -n observability deployment/opentelemetry-collector
kubectl get svc -n observability opentelemetry-collector
```

**Possíveis causas:**
1. Namespace `observability` não existe em staging
2. OTEL Collector não está implantado em staging
3. NetworkPolicy bloqueando comunicação
4. DNS não resolvendo `opentelemetry-collector.observability.svc.cluster.local`

### 5.3 Solução de Contorno (Workaround)

**Remover readiness probe temporariamente:**
```yaml
# Isso permitirá o deployment completar
# Mas remove a proteção de não enviar tráfego para pods não-prontos
readinessProbe: null
```

⚠️ **Risco:** Pods podem receber tráfego antes de estarem totalmente inicializados

---

## 6. Recomendações

### Prioridade 1 (Imediata - 5 minutos)
Aumentar timeout do readiness probe de 3s para 10s no Helm chart.

### Prioridade 2 (Curto prazo - 1 hora)
Investigar disponibilidade do OTEL Collector no namespace staging.

### Prioridade 3 (Médio prazo - 1 dia)
Implementar health checks graduais:
- `/health/live` - Liveness (mínimo para sobreviver)
- `/health/ready` - Readiness (para receber tráfego)
- `/health/startup` - Startup (inicialização completa)

### Prioridade 4 (Longo prazo)
Adicionar circuit breaker para dependências externas opcionais.

---

## 7. Métricas para Monitoramento

```
# Kubectl commands para acompanhamento
kubectl rollout status deployment/consensus-engine -n neural-hive-staging
kubectl get pods -n neural-hive-staging -w
kubectl logs -n neural-hive-staging -l app.kubernetes.io/name=consensus-engine -f
```

---

## Conclusão

A falha do deployment é causada por um **health check excessivamente rigoroso** combinado com **timeout inadequado**. O endpoint `/ready` inclui a verificação do OTEL Collector como uma dependência obrigatória, mas o timeout de 3s do readiness probe é insuficiente para a tentativa de conexão falhar graciosamente.

**Ação recomendada imediata:** Aumentar o timeout do readiness probe ou tornar o check do OTEL Collector não-bloqueante para o readiness.

**Arquivos envolvidos:**
- Helm chart: `helm-charts/consensus-engine/templates/deployment.yaml`
- Código: `src/observability/health.py` (provável localização)
- Configuração: `environments/staging/helm-values/consensus-engine-values.yaml`
