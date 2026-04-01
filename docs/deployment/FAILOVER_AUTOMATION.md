# Failover Automation - Neural Hive-Mind (EPIC-404)

## Visão Geral

Sistema de failover automatizado para garantir alta disponibilidade do Neural Hive-Mind com RTO (Recovery Time Objective) < 5 minutos.

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Região Primária                                  │
│                     (us-east-1 / AWS EKS)                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Gateway  │  │Consensus │  │Orchestr. │  │ Workers  │              │
│  │  (3x)    │  │  (3x)    │  │  (2x)    │  │  (4x)    │              │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Health Check (1min)
                                    │
                    ┌───────────────▼──────────────┐
                    │   Failover Watchdog         │
                    │   - Detect: < 1min          │
                    │   - Decide: < 1min          │
                    │   - Failover: < 3min        │
                    └───────────────┬──────────────┘
                                    │
                    ┌───────────────▼──────────────┐
                    │  Route53 / DNS Failover      │
                    │  TTL: 60s                    │
                    └───────────────┬──────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Região Secundária                                │
│                    (us-west-2 / AWS EKS)                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Gateway  │  │Consensus │  │Orchestr. │  │ Workers  │              │
│  │  (3x)    │  │  (3x)    │  │  (2x)    │  │  (4x)    │              │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘              │
└─────────────────────────────────────────────────────────────────────────┘
```

## Componentes

### 1. Health Check Script

**Arquivo:** `scripts/automation/health-check.sh`

**Função:** Verificar saúde de todos os serviços críticos

**Checks:**
- Status do Deployment (ready/total replicas)
- Status dos Pods (running/pending/failed)
- Endpoint HTTP (/health) quando disponível
- Conectividade com serviços dependentes

**Saídas:**
- `0`: Todos os serviços saudáveis
- `1`: Cluster parcialmente degradado (> 30% falhando)
- `2`: Cluster severamente degradado (> 70% falhando)

**Exemplo:**
```bash
./health-check.sh --namespace neural-hive --timeout 30
```

### 2. Failover Watchdog

**Arquivo:** `scripts/automation/failover-watchdog.sh`

**Função:** Monitorar contínuamente e executar failover automático

**Estados:**
- `NORMAL`: Todos os serviços saudáveis
- `DEGRADED`: Alguns serviços falhando (< 70%)
- `FAILING_OVER`: Failover em andamento
- `FAILOVER_COMPLETE`: Failover executado

**Parâmetros:**
- `CHECK_INTERVAL`: 60 segundos (padrão)
- `FAILURE_THRESHOLD`: 3 checks consecutivos (padrão)
- `PRIMARY_REGION`: us-east-1
- `SECONDARY_REGION`: us-west-2

**Exemplo:**
```bash
# Executar em background
nohup ./failover-watchdog.sh > /var/log/failover.log 2>&1 &

# Ou como serviço systemd
sudo systemctl start neural-hive-failover
```

### 3. DNS Failover

**Mecanismo:** Atualização de registro DNS via Route53 API

**TTL:** 60 segundos (balance entre propagação rápida e carga DNS)

**Registro:**
```
api.neural-hive-mind.io
  Type: A
  TTL: 60
  Values:
    - primary.us-east-1.elb.amazonaws.com (weight: 100)
    - secondary.us-west-2.elb.amazonaws.com (weight: 0)
```

**Failover:**
```python
def promote_secondary():
    client = boto3.client('route53')
    client.change_resource_record_sets(
        HostedZoneId='Z1234567890ABC',
        ChangeBatch={
            'Changes': [{
                'Action': 'UPSERT',
                'ResourceRecordSet': {
                    'Name': 'api.neural-hive-mind.io',
                    'Type': 'A',
                    'SetIdentifier': 'secondary',
                    'Weight': 100,  # Promover
                    'AliasTarget': {
                        'DNSName': 'secondary.us-west-2.elb.amazonaws.com',
                        'EvaluateTargetHealth': True
                    }
                }
            }, {
                'Action': 'UPSERT',
                'ResourceRecordSet': {
                    'Name': 'api.neural-hive-mind.io',
                    'Type': 'A',
                    'SetIdentifier': 'primary',
                    'Weight': 0,  # Despromover
                    'AliasTarget': {
                        'DNSName': 'primary.us-east-1.elb.amazonaws.com',
                        'EvaluateTargetHealth': True
                    }
                }
            }]
        }
    )
```

## RTO Breakdown

| Fase | Duração | Descrição |
|------|---------|-----------|
| Detecção | < 1min | Watchdog detecta falha |
| Decisão | < 1min | Threshold de 3 checks consecutivos |
| Failover | < 3min | Promover secundária + DNS propagate |
| **Total** | **< 5min** | **RTO garantido** |

## Configuração

### Variáveis de Ambiente

```bash
# Health Check
export NAMESPACE="neural-hive"
export TIMEOUT=30

# Watchdog
export CHECK_INTERVAL=60
export FAILURE_THRESHOLD=3
export PRIMARY_REGION="us-east-1"
export SECONDARY_REGION="us-west-2"

# Alertas
export SLACK_WEBHOOK_URL="https://hooks.slack.com/..."
export PAGERDUTY_API_KEY="..."
```

### Systemd Service

**Arquivo:** `/etc/systemd/system/neural-hive-failover.service`

```ini
[Unit]
Description=Neural Hive-Mind Failover Watchdog
After=network.target

[Service]
Type=simple
User=root
Environment="NAMESPACE=neural-hive"
Environment="CHECK_INTERVAL=60"
Environment="FAILURE_THRESHOLD=3"
ExecStart=/opt/neural-hive/scripts/failover-watchdog.sh
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Habilitar serviço:**
```bash
sudo systemctl enable neural-hive-failover
sudo systemctl start neural-hive-failover
sudo systemctl status neural-hive-failover
```

## Testes

### Teste Manual de Health Check

```bash
# Verificar saúde atual
./scripts/automation/health-check.sh

# Simular falha (escalar replicas para 0)
kubectl scale deployment gateway-intencoes --replicas=0 -n neural-hive

# Verificar que health check detecta
./scripts/automation/health-check.sh  # Deve retornar exit code 2

# Recuperar
kubectl scale deployment gateway-intencoes --replicas=3 -n neural-hive
```

### Teste de Failover (Chaos Engineering)

**Usando Chaos Mesh ou Litmus:**

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: failover-test
  namespace: neural-hive
spec:
  action: pod-kill
  mode: fixed-percent
  value: "80"
  selector:
    namespaces:
      - neural-hive
  scheduler:
    cron: "@every 5m"
```

**Resultado Esperado:**
1. Chaos mata 80% dos pods
2. Watchdog detecta falha em < 1min
3. Após 3 checks, failover é iniciado
4. DNS atualizado em < 3min
5. Tráfego redirecionado para secundária

## Monitoramento

### Métricas Prometheus

```yaml
# Failover events
failover_events_total{region="us-east-1", status="initiated"} 0
failover_events_total{region="us-east-1", status="completed"} 0
failover_events_total{region="us-east-1", status="failed"} 0

# Health check status
health_check_status{service="gateway-intencoes", region="us-east-1"} 1
health_check_status{service="consensus-engine", region="us-east-1"} 1

# Service health percentage
service_health_percentage{region="us-east-1"} 100
```

### Alertas Grafana

```yaml
groups:
  - name: failover
    rules:
      - alert: ServiceDegraded
        expr: service_health_percentage < 70
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Cluster parcialmente degradado"
          description: "{{ $value }}% dos serviços estão saudáveis"

      - alert: FailoverInitiated
        expr: increase(failover_events_total{status="initiated"}[1m]) > 0
        labels:
          severity: critical
        annotations:
          summary: "FAILOVER INICIADO"
          description: "Failover iniciado para região secundária"

      - alert: FailoverCompleted
        expr: increase(failover_events_total{status="completed"}[1m]) > 0
        labels:
          severity: info
        annotations:
          summary: "FAILOVER COMPLETO"
          description: "Tráfego redirecionado para região secundária"
```

## Recuperação

### Após Failover Bem-Sucedido

1. **Investigar causa da falha** na primária
2. **Corrigir problema** identificado
3. **Aguardar recuperação** completa
4. **Failback** manual (se desejado)

### Failback Manual

```bash
# 1. Verificar primária está saudável
./health-check.sh --namespace neural-hive --region us-east-1

# 2. Promover primária novamente
./scripts/promote-primary.sh --region us-east-1

# 3. Verificar tráfego voltou
kubectl logs -n neural-hive deployment/gateway-intencoes --tail=100
```

## Limitações

1. **Data Consistency**: Durante failover, dados recentes podem não ter replicado
2. **Split-Brain**: Risco se ambas regiões se acham primária
3. **DNS TTL**: 60s de propagação significa alguns clientes ainda tentam primária
4. **Manual Verification**: Failback requer intervenção manual

## Próximos Passos

1. [ ] Implementar notificação PagerDuty
2. [ ] Adicionar métricas detalhadas Prometheus
3. [ ] Automatizar failback com verificação de consistência
4. [ ] Implementar failover multi-region (3+ regiões)
5. [ ] Adicionar testes de chaos automáticos

## Referências

- [AWS Route53 Health Checks](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/health-checks.html)
- [Kubernetes Disaster Recovery](https://kubernetes.io/docs/tasks/administer-cluster/configure-upgrade-etcd/)
- [Chaos Engineering Best Practices](https://principlesofchaos.org/)
