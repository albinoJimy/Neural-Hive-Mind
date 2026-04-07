# Runbooks do Serviço de Auto-Recuperação

Este documento documenta todos os playbooks do serviço de auto-recuperação do Neural-Hive-Mind.

## Índice

1. [Visão Geral](#visão-geral)
2. [Playbooks Disponíveis](#playbooks-disponíveis)
3. [Execução Manual de Playbooks](#execução-manual-de-playbooks)
4. [Verificação de Resultados](#verificação-de-resultados)
5. [Troubleshooting](#troubleshooting)
6. [Integração com Monitoramento](#integração-com-monitoramento)

---

## Visão Geral

O serviço de auto-recuperação (Self-Healing Engine) automatiza a detecção e correção de problemas no sistema NHM. Os playbooks são executados automaticamente com base em métricas e eventos, mas também podem ser acionados manualmente.

### Tipos de Playbooks

- **ORCHESTRATION**: Orquestra ações entre serviços do NHM
- **KUBERNETES**: Ações de infraestrutura (Kubernetes)
- **PLATFORM**: Ações de plataforma (bancos de dados, Kafka, etc.)

### Fluxo de Execução

```
Evento/Métrica → HealthMonitor → Self-Healing Engine → Execução do Playbook → Ações → Verificação
```

---

## Playbooks Disponíveis

### 1. `ticket_timeout_recovery` - Recuperação de Timeout de Ticket

**Quando executar:**
- Tickets excedem SLA ou timeout configurado
- Workers ficam unresponsive
- Tickets travados em estados intermediários

**O que faz:**
1. Verifica saúde do worker
2. Reinicia pod do worker se necessário
3. Realoca ticket para outro worker disponível
4. Atualiza status do ticket para "RETRYING"

**Parâmetros obrigatórios:**
- `ticket_id`: ID do ticket problemático
- `workflow_id`: ID do workflow associado
- `worker_id`: ID do worker onde o ticket estava
- `namespace`: Namespace Kubernetes

**Como verificar resultado:**
```bash
# Verificar status do ticket
curl -X GET "http://approval-service:8004/api/v1/tickets/{{ticket_id}}"

# Verificar status do worker
kubectl get pods -n {{namespace}} | grep {{worker_id}}

# Logs do serviço
kubectl logs -n {{namespace}} deployment/worker-agents -f
```

### 2. `enforce_mtls_strict` - Aplicar mTLS STRICT

**Quando executar:**
- Requisito de segurança para namespaces sensíveis
- Auditoria de conformidade com políticas de segurança
- Após incidentes de segurança

**O que faz:**
1. Aplica política Istio PeerAuthentication com mTLS STRICT
2. Aguarda propagação da política (10 segundos)

**Parâmetros obrigatórios:**
- `namespace`: Namespace do Kubernetes para aplicar a política

**Como verificar resultado:**
```bash
# Verificar política aplicada
kubectl get peerauthentication -n {{namespace}}

# Verificar status dos pods (devem estar com mTLS ativo)
kubectl get pods -n {{namespace}} -o wide

# Testar conexão entre serviços
kubectl exec -n {{namespace}} -it <pod-client> -- curl -k https://<pod-server>
```

### 3. `restart_pod` - Reiniciar Pod

**Quando executar:**
- Pod com status CrashLoopBackOff
- Pod travado ou não respondendo
- Consumo excessivo de recursos

**O que faz:**
1. Deleta o pod (Kubernetes cria novo automaticamente)
2. Aguarda novo ficar pronto (máximo 90s)

**Parâmetros obrigatórios:**
- `pod_name`: Nome do pod
- `namespace`: Namespace do pod

**Como verificar resultado:**
```bash
# Verificar status do pod
kubectl get pods -n {{namespace}} | grep {{pod_name}}

# Verificar se o pod está rodando e pronto
kubectl describe pod {{pod_name}} -n {{namespace}}

# Verificar logs do novo pod
kubectl logs -n {{namespace}} pod/{{pod_name}} --since=5m
```

### 4. `sla_violation_mitigation` - Mitigação de Violação de SLA

**Quando executar:**
- Serviço excede atraso configurado (delay_ms)
- Violação do budget de erro do serviço
- Aumento na taxa de erros

**O que faz:**
1. Boost de prioridade para tickets do workflow afetado
2. Escala workers para 2 replicas
3. Habilita modo "fast path" para processamento prioritário
4. Notifica equipe via Slack

**Parâmetros obrigatórios:**
- `workflow_id`: ID do workflow com violação
- `service_name`: Nome do serviço violando SLA

**Parâmetros opcionais:**
- `violation_type`: Tipo de violação (delay, error_rate)
- `delay_ms`: Atraso em ms

**Como verificar resultado:**
```bash
# Verificar SLA restaurado
curl -X GET "http://monitoring-service:8008/api/v1/sla/{{service_name}}"

# Verificar workers escalados
kubectl get deployment worker-agents -n default

# Verificar status do modo fast path
curl -X GET "http://gateway-intencoes:8000/api/v1/policy/fast_path_mode"
```

### 5. `worker_failure_recovery` - Recuperação de Falha de Worker

**Quando executar:**
- Worker falha health checks
- Worker é removido do service registry
- Tickets pendentes em worker falhado

**O que faz:**
1. Desregistra worker unhealthy
2. Realoca tickets pendentes para outros workers
3. Escala workers se necessário
4. Notifica Queen Agent

**Parâmetros obrigatórios:**
- `worker_id`: ID do worker falhado
- `namespace`: Namespace do worker

**Parâmetros opcionais:**
- `affected_tickets`: Lista de tickets afetados

**Como verificar resultado:**
```bash
# Verificar worker desregistrado
curl -X GET "http://service-registry:8007/api/v1/workers"

# Verificar tickets realocados
curl -X GET "http://approval-service:8004/api/v1/tickets?status=PENDING"

# Verificar status da escalação
kubectl get deployment worker-agents -n {{namespace}}
```

### 6. `kafka_consumer_lag_recovery` - Recuperação de Lag do Kafka

**Quando executar:**
- Consumer group excede lag_threshold
- Tópicos com acumulação de mensagens
- Performance de degradada

**O que faz:**
1. Verifica lag do consumer
2. Escala consumers para 3 replicas
3. Pausa producers temporariamente
4. Limpa mensagens "poison pills"

**Parâmetros obrigatórios:**
- `consumer_group`: Nome do consumer group
- `topic`: Tópico afetado
- `lag_threshold`: Limite de lag para acionar recuperação

**Como verificar resultado:**
```bash
# Verificar lag reduzido
kafka-consumer-groups --bootstrap-server=kafka:9092 --describe --group {{consumer_group}}

# Verificar consumers escalados
kubectl get deployment {{consumer_group}} -n default

# Verificar status dos tópicos
kafka-topics --bootstrap-server=kafka:9092 --describe --topic {{topic}}
```

### 7. `scale_up_deployment` - Escala de Deployment

**Quando executar:**
- Aumento na carga de trabalho
- Escala manual para aumento de capacidade
- Recuperação de incidentes

**O que faz:**
1. Escala deployment para target_replicas
2. Aguarda deployment ficar ready

**Parâmetros obrigatórios:**
- `deployment_name`: Nome do deployment
- `namespace`: Namespace
- `target_replicas`: Número alvo de replicas

**Como verificar resultado:**
```bash
# Verificar deployment escalado
kubectl get deployment {{deployment_name}} -n {{namespace}}

# Verificar pods rodando
kubectl get pods -n {{namespace}} | grep {{deployment_name}}

# Verificar deployment ready
kubectl rollout status deployment/{{deployment_name}} -n {{namespace}}
```

### 8. `database_connection_recovery` - Recuperação de Conexão de Banco

**Quando executar:**
- Falha na conexão com MongoDB/PostgreSQL/Redis
- Serviço banco de dados down
- Timeouts de conexão

**O que faz:**
1. Reinicia pod do serviço
2. Aguarda 30 segundos para estabilizar
3. Verifica conexão com o banco
4. Notifica equipe

**Parâmetros obrigatórios:**
- `service_name`: Nome do serviço
- `namespace`: Namespace
- `database_type`: mongodb, postgresql, ou redis

**Parâmetros opcionais:**
- `connection_string`: String de conexão
- `target_pod`: Pod específico para reiniciar

**Como verificar resultado:**
```bash
# Verificar conexão restaurada
curl -X GET "http://{{service_name}}:{{port}}/health"

# Verificar pods reiniciados
kubectl get pods -n {{namespace}} | grep {{service_name}}

# Testar conexão com banco
kubectl exec -n {{namespace}} -it <pod> -- {{db_command}}
```

### 9. `deadlock_recovery` - Recuperação de Deadlock

**Quando executar:**
- Workflow detectado como deadlock
- Tickets presos por >stuck_duration_seconds
- Sistema não progredindo

**O que faz:**
1. Pausa workflow imediatamente
2. Notifica equipe com tickets suspeitos
3. Análise manual necessária

**Parâmetros obrigatórios:**
- `workflow_id`: ID do workflow travado

**Parâmetros opcionais:**
- `stuck_duration_seconds`: Duração para considerar como travado
- `suspected_tickets`: Lista de tickets suspeitos

**Como verificar resultado:**
```bash
# Verificar workflow pausado
curl -X GET "http://orchestrator-dynamic:8003/api/v1/workflows/{{workflow_id}}"

# Verificar status dos tickets
curl -X GET "http://approval-service:8004/api/v1/tickets?workflow_id={{workflow_id}}"

# Logs do orchestrator
kubectl logs -n default deployment/orchestrator-dynamic -f | grep "{{workflow_id}}"
```

### 10. `memory_leak_detection` - Detecção de Memory Leak

**Quando executar:**
- Detecção automática de memory leak
- Uso de memória contínuamente aumentando
- Performance degradada

**O que faz:**
1. Coleta métricas de uso de memória
2. Analisa tendência de crescimento
3. Notifica equipe para análise manual

**Parâmetros obrigatórios:**
- `pod_name`: Nome do pod suspeito
- `namespace`: Namespace do pod

**Parâmetros opcionais:**
- `memory_threshold_mb`: Limite em MB (default: 512)
- `metrics_history`: Histórico de métricas

**Como verificar resultado:**
```bash
# Verificar métricas coletadas
curl -X GET "http://monitoring-service:8008/api/v1/pod-metrics/{{pod_name}}"

# Verificar uso de memória atual
kubectl top pods -n {{namespace}} | grep {{pod_name}}

# Logs do pod (buscar por padrões de memory leak)
kubectl logs -n {{namespace}} pod/{{pod_name}} --tail=100 | grep -i "memory"
```

---

## Execução Manual de Playbooks

### Via API REST

```bash
# Executar ticket_timeout_recovery
curl -X POST "http://self-healing-engine:8006/api/v1/playbooks/ticket_timeout_recovery" \
  -H "Content-Type: application/json" \
  -d '{
    "ticket_id": "ticket-123",
    "workflow_id": "workflow-456",
    "worker_id": "worker-789",
    "namespace": "default"
  }'

# Executar restart_pod
curl -X POST "http://self-healing-engine:8006/api/v1/playbooks/restart_pod" \
  -H "Content-Type: application/json" \
  -d '{
    "pod_name": "worker-agents-123",
    "namespace": "default"
  }'
```

### Via Interface Web

1. Acessar: `http://self-healing-engine:8006/ui`
2. Selecionar playbook na lista
3. Preencher parâmetros
4. Clicar em "Execute Playbook"

### Via Temporal (Orquestração)

```python
from temporalio import workflow

@workflow.defn
class SelfHealingWorkflow:
    @workflow.run
    async def run(self, playbook_name: str, parameters: dict):
        result = await workflow.execute_activity(
            "execute_playbook",
            args=[playbook_name, parameters],
            start_to_close_timeout=timedelta(minutes=10)
        )
        return result
```

---

## Verificação de Resultados

### Verificações Padrão

Todos os playbooks incluem verificações automáticas:

1. **status**: `AVAILABLE` - Playbook pode ser executado
2. **validation_checks**: Lista de verificações pós-execução
3. **timeout_seconds**: Tempo máximo de execução
4. **max_retries**: Tentativas em caso de falha

### Verificação Manual

```bash
# Verificar status do serviço de auto-recuperação
curl -X GET "http://self-healing-engine:8006/api/v1/health"

# Listar playbooks disponíveis
curl -X GET "http://self-healing-engine:8006/api/v1/playbooks"

# Verificar histórico de execuções
curl -X GET "http://self-healing-engine:8006/api/v1/executions"

# Verificar métricas
curl -X GET "http://self-healing-engine:8006/metrics"
```

### Verificação por Integração

Playbooks com integração de sistema:

```bash
# Verificar integridade do sistema após execução
curl -X GET "http://health-monitor:8008/api/v1/system-health"

# Verificar SLA após mitigação
curl -X GET "http://sla-monitor:8009/api/v1/sla-summary"

# Verificar service registry
curl -X GET "http://service-registry:8007/api/v1/health"
```

---

## Troubleshooting

### Problemas Comuns

#### 1. Playbook Falha na Execução

**Sintoma:** Status `FAILED` na API

**Solução:**
```bash
# Verificar logs da execução
curl -X GET "http://self-healing-engine:8006/api/v1/executions/{{execution_id}}"

# Verificar logs do serviço
kubectl logs -n default deployment/self-healing-engine -f

# Checar permissões do pod
kubectl auth can-i delete pods -n default
```

#### 2. Timeout do Playbook

**Sintoma:** Execução excede `timeout_seconds`

**Solução:**
1. Verificar recursos do cluster
```bash
kubectl describe node | grep -i "pressure"
kubectl get events --sort-by='.metadata.creationTimestamp'
```

2. Aumentar timeout no playbook
3. Verificar se há dependências lentas

#### 3. Recuperação Ineficaz

**Sintoma:** Problema recorrente mesmo após recuperação

**Solução:**
```bash
# Analisar padrões de falha
curl -X GET "http://monitoring-service:8008/api/v1/incidents?service={{service}}"

# Verificar root cause
kubectl describe pod {{pod}} --previous

# Ajustar configurações de health check
kubectl get hpa -n default
```

#### 4. Falha de Conexão

**Sintoma:** Erro de conexão entre serviços

**Solução:**
```bash
# Verificar conectividade
kubectl exec -n default -it <pod> -- wget -qO- {{service_url}}

# Verificar service mesh
kubectl get service -n default

# Verificar network policies
kubectl get networkpolicy -n default
```

### Logs e Diagnóstico

```bash
# Logs do Self-Healing Engine
kubectl logs -n default deployment/self-healing-engine -f --tail=100

# Logs do Temporal (orquestração)
kubectl logs -n default deployment/temporal-workflow -f --tail=100

# Logs do Kafka (eventos)
kubectl logs -n default deployment/kafka -f --tail=100 | grep self-healing

# Métricas Prometheus
kubectl port-forward -n monitoring prometheus-server 9090:9090
# Acessar: http://localhost:9090
```

### Escalonamento

Se o problema não for resolvido com os passos acima:

1. **Escalonar para Time SRE:** PagerDuty/Slack alert
2. **Criar incidente:** Documentar em sistema de tickets
3. **Revisar configuração:** Ajustar parâmetros do playbook
4. **Post-mortem:** Documentar aprendizado

---

## Integração com Monitoramento

### Prometheus Metrics

Os playbooks expõem as seguintes métricas:

```bash
# Métricas do Self-Healing Engine
self_healing_playbook_executions_total{playbook="name", status="success|failed"}
self_healing_playbook_duration_seconds{playbook="name"}
self_healing_validation_checks_total{check="name", status="passed|failed"}

# Métricas do sistema
system_slaviolation_count{service="name"}
system_worker_failure_count{namespace="name"}
system_database_error_count{db_type="mongodb|redis"}
```

### Grafana Dashboards

Dashboard padrão: `Self-Healing Dashboard`

- Execuções de playbooks
- Tempo médio de recuperação
- Taxa de sucesso
- Problemas recorrentes

### Alertas

Alertas configurados no Prometheus:

1. **CRITICAL:** Playbook failed consecutively 3 times
2. **WARNING:** High recovery time (>10min)
3. **INFO:** Recovery action executed

---

## Melhores Práticas

1. **Teste Regular:** Executar playbooks em ambiente de staging
2. **Monitoramento:** Acompanhar resultados após execução
3. **Documentar:** Manter runbooks atualizados
4. **Versionar:** Controlar versões dos playbooks
5. **Feedback Loop:** Analisar eficácia e ajustar

---

## Contato de Suporte

- **Time SRE:** `#sre-team` no Slack
- **Engenharia:** `#eng-neuralhive` no Slack
- **On-call:** PagerDuty (exige permissão)

---

*Última atualização: 2026-04-07*