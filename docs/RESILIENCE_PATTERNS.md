# Padrões de Resiliência - Circuit Breakers

## Visão Geral

O Orchestrator Dynamic implementa circuit breakers para proteger contra cascading failures em integrações externas:

- **Kafka Producer**: Protege publicação de execution tickets
- **Temporal Client**: Protege início e queries de workflows
- **Redis Client**: Protege operações de cache
- **MongoDB Client**: Protege persistência (já implementado)

## Biblioteca Utilizada

Todos os circuit breakers usam `MonitoredCircuitBreaker` de `neural_hive_resilience.circuit_breaker`, que:

- Usa `pybreaker` internamente
- Registra métricas Prometheus automaticamente
- Suporta operações síncronas e assíncronas
- Logging estruturado com `structlog`

## Estados do Circuit Breaker

```
CLOSED ──[fail_max failures]──> OPEN ──[recovery_timeout]──> HALF_OPEN
   ^                                                              |
   └──────────────────[success]────────────────────────────────┘
```

- **CLOSED**: Operação normal, todas as requisições passam
- **OPEN**: Circuit breaker aberto, requisições são bloqueadas imediatamente
- **HALF_OPEN**: Permite uma requisição de teste para verificar recuperação

## Configuração

### Kafka Producer

```yaml
circuitBreaker:
  kafka:
    enabled: true
    failMax: 5          # Abrir após 5 falhas consecutivas
    timeoutSeconds: 60  # Duração do estado OPEN
    recoveryTimeoutSeconds: 30  # Tempo para tentar HALF_OPEN
```

**Comportamento:**
- Falhas de publicação incrementam contador
- Após `failMax` falhas, circuit breaker abre
- Requisições são bloqueadas por `timeoutSeconds`
- Após `recoveryTimeoutSeconds`, permite uma tentativa (HALF_OPEN)
- Sucesso fecha circuit breaker, falha reabre

### Temporal Client

```yaml
circuitBreaker:
  temporal:
    enabled: true
    failMax: 5
    timeoutSeconds: 60
    recoveryTimeoutSeconds: 30
```

**Operações Protegidas:**
- `start_workflow()`: Início de workflows
- `get_workflow_handle()`: Obtenção de handles
- `query_workflow()`: Queries em workflows

**Comportamento:**
- Falhas de conexão ou timeout incrementam contador
- Circuit breaker abre após `failMax` falhas
- Workflows não podem ser iniciados quando aberto
- Fail-fast: retorna `CircuitBreakerError` imediatamente

### Redis Client

```yaml
circuitBreaker:
  redis:
    enabled: true
    failMax: 5
    timeoutSeconds: 60
    recoveryTimeoutSeconds: 60  # Maior para cache
```

**Operações Protegidas:**
- `redis_get_safe()`: Leitura de cache
- `redis_setex_safe()`: Escrita de cache
- `redis_ping_safe()`: Health check

**Comportamento:**
- Fail-open: retorna `None` quando circuit breaker aberto
- Sistema continua operando sem cache
- Performance degradada mas funcional

## Métricas Prometheus

### circuit_breaker_state

Gauge indicando estado do circuit breaker:
- `0`: CLOSED
- `1`: OPEN
- `2`: HALF_OPEN

Labels: `service`, `circuit`

```promql
circuit_breaker_state{service="orchestrator-dynamic", circuit="kafka_producer"}
```

### circuit_breaker_failures_total

Counter de falhas registradas.

```promql
rate(circuit_breaker_failures_total{circuit="kafka_producer"}[5m])
```

### circuit_breaker_trips_total

Counter de vezes que circuit breaker abriu.

```promql
circuit_breaker_trips_total{circuit="temporal_client"}
```

## Alertas

### CircuitBreakerOpen

Alerta quando circuit breaker está aberto por mais de 2 minutos.

**Severidade:** Warning (Redis), Critical (Kafka/Temporal)

**Ação:**
1. Verificar logs do serviço dependente
2. Verificar conectividade de rede
3. Verificar health do serviço dependente
4. Considerar restart se persistir

### MultipleCircuitBreakersOpen

Alerta quando 2+ circuit breakers estão abertos simultaneamente.

**Severidade:** Critical

**Ação:**
1. Verificar infraestrutura (rede, DNS, cluster)
2. Verificar se há incident em andamento
3. Escalar para SRE se necessário

## Troubleshooting

### Circuit Breaker Não Fecha

**Sintomas:**
- Circuit breaker permanece OPEN por tempo prolongado
- Métricas mostram `circuit_breaker_state == 1`

**Diagnóstico:**
```bash
# Verificar logs
kubectl logs -n neural-hive orchestrator-dynamic-xxx | grep circuit_breaker

# Verificar estado via API
curl http://orchestrator-dynamic:8000/health

# Verificar serviço dependente
kubectl get pods -n neural-hive | grep kafka
kubectl get pods -n neural-hive | grep temporal
kubectl get pods -n neural-hive | grep redis
```

**Resolução:**
1. Verificar se serviço dependente está healthy
2. Verificar conectividade de rede
3. Aguardar recovery timeout (30-60s)
4. Se persistir, restart do orchestrator-dynamic

### Falsos Positivos

**Sintomas:**
- Circuit breaker abre frequentemente
- Serviço dependente está healthy

**Diagnóstico:**
- Verificar `failMax` (pode estar muito baixo)
- Verificar timeouts (podem estar muito agressivos)

**Resolução:**
```yaml
# Aumentar threshold
circuitBreaker:
  kafka:
    failMax: 10  # Era 5
    timeoutSeconds: 120  # Era 60
```

## Testes

### Teste Manual de Circuit Breaker

```bash
# 1. Simular falha do Kafka
kubectl scale deployment kafka --replicas=0 -n neural-hive

# 2. Observar circuit breaker abrindo
kubectl logs -f orchestrator-dynamic-xxx | grep circuit_breaker_open

# 3. Verificar métricas
curl http://orchestrator-dynamic:8000/metrics | grep circuit_breaker_state

# 4. Restaurar Kafka
kubectl scale deployment kafka --replicas=3 -n neural-hive

# 5. Observar circuit breaker fechando
kubectl logs -f orchestrator-dynamic-xxx | grep circuit_breaker_reset
```

### Testes Automatizados

```bash
# Testes unitários
pytest tests/unit/test_circuit_breakers.py -v

# Testes de integração
pytest tests/integration/test_circuit_breakers_integration.py -v -m integration
```

## Referências

- [pybreaker Documentation](https://github.com/danielfm/pybreaker)
- [Circuit Breaker Pattern - Martin Fowler](https://martinfowler.com/bliki/CircuitBreaker.html)
- [Release It! - Michael Nygard](https://pragprog.com/titles/mnee2/release-it-second-edition/)
