# GAP-01: Fluxo STE → Consensus Quebrado

**Status:** 🔴 Planejado
**Prioridade:** P0 - CRÍTICA
**Esforço Estimado:** 1 dia (4-6 horas)
**Responsável:** Backend Team

---

## Problema

O fluxo principal de processamento está **interrompido** devido a mismatch de tópicos Kafka entre Semantic Translation Engine (STE) e Consensus Engine.

```
┌─────────────┐    cognitive-plans     ┌──────────────┐
│     STE     │ ──────────────────────>  ❌ (Ninguém) │
│ (Producer)  │                         │              │
└─────────────┘                         └──────────────┘
     ✗ não consome

┌─────────────┐    plans.ready         ┌──────────────┐
│    (Vazio)   │ <────────────────────── │  Consensus   │
│             │                         │  (Consumer)   │
└─────────────┘                         └──────────────┘
```

### Diagnóstico

| Serviço | Tópico Configurado | Arquivo |
|---------|-------------------|---------|
| STE (Producer) | `cognitive-plans` | `src/config/settings.py:51` |
| Consensus (Consumer) | `plans.ready` | `src/config/settings.py:25` |

---

## Solução

**Opção Escolhida:** Alterar STE para produzir em `plans.ready`

**Justificativa:**
- Helm charts já usam `plans.ready`
- Schema Registry configurado para `plans.ready-value`
- Minimiza impacto no Consensus Engine
- Mantém compatibilidade com documentação existente

---

## Implementação

### Passo 1: Alterar Settings do STE

```python
# Arquivo: services/semantic-translation-engine/src/config/settings.py
# Linha 51

# ANTES:
kafka_plans_topic: str = Field(default='cognitive-plans', description='Plans output topic')

# DEPOIS:
kafka_plans_topic: str = Field(default='plans.ready', description='Plans output topic')
```

### Passo 2: Atualizar Mock Settings nos Testes

```python
# Arquivo: services/semantic-translation-engine/tests/conftest.py
# Linha 127

# ANTES:
settings.kafka_plans_topic = 'cognitive-plans'

# DEPOIS:
settings.kafka_plans_topic = 'plans.ready'
```

### Passo 3: Verificar Testes

```bash
# Buscar referências hardcoded
grep -r "cognitive-plans" services/semantic-translation-engine/tests/

# Atualizar se encontrado
```

---

## Validação

### 1. Pre-Deploy

```bash
# Verificar que tópico plans.ready existe
kubectl exec -n kafka kafka-0 -- kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --list | grep plans.ready

# Verificar schema no Schema Registry
kubectl exec -n kafka schema-registry-0 -- curl \
  http://localhost:8081/subjects/plans.ready-value/versions/latest
```

### 2. Pós-Deploy

```bash
# Verificar logs do STE
kubectl logs -n semantic-translation -l app=semantic-translation-engine \
  --tail=100 | grep "plans.ready\|Plan publicado"

# Verificar mensagens no tópico
kubectl exec -n kafka kafka-0 -- kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic plans.ready \
  --from-beginning \
  --max-messages 5

# Verificar logs do Consensus
kubectl logs -n consensus-orchestration -l app=consensus-engine \
  --tail=100 | grep "plans.ready\|Mensagem recebida"
```

### 3. Métricas de Sucesso

- `kafka_producer_sent_messages{topic="plans.ready"}` incrementando
- `kafka_consumer_lag{topic="plans.ready",consumer="consensus-engine"}` = 0
- `neural_hive_plans_status="success"` incrementando

---

## Deploy Strategy

### Ambiente Desenvolvimento

```bash
# 1. Deploy do STE
helm upgrade semantic-translation-engine ./helm-charts/semantic-translation-engine \
  -n semantic-translation \
  --values environments/dev/helm-values/semantic-translation-engine-values.yaml \
  --reuse-values

# 2. Verificar pods
kubectl get pods -n semantic-translation

# 3. Verificar logs
kubectl logs -n semantic-translation -l app=semantic-translation-engine --tail=50 -f
```

### Ambiente Produção

1. Agendar janela de manutenção
2. Backup da configuração atual
3. Deploy sequencial (rolling update)
4. Monitoramento intensivo (primeira hora)

---

## Rollback Plan

```bash
# Reverter para versão anterior
helm rollback semantic-translation-engine -n semantic-translation

# Ou restaurar valores anteriores
helm upgrade semantic-translation-engine ./helm-charts/semantic-translation-engine \
  -n semantic-translation \
  --values backup-ste-config.yaml \
  --reuse-values

# Verificar recuperação
kubectl logs -n semantic-translation -l app=semantic-translation-engine --tail=50
```

### Critérios de Rollback

- Erro de deserialização > 5%
- Lag do consumidor > 1000 mensagens
- Erro de validação de schema > 1%

---

## Checklist

**Pre-Implementação:**
- [ ] Backup de configurações
- [ ] Validar existência do tópico plans.ready
- [ ] Validar schema no Schema Registry
- [ ] Executar testes unitários
- [ ] Documentar mudanças

**Pos-Implementação:**
- [ ] Deploy do STE
- [ ] Verificar logs do STE
- [ ] Verificar mensagens em plans.ready
- [ ] Verificar logs do Consensus Engine
- [ ] Validar consumo (lag = 0)
- [ ] Executar testes E2E
- [ ] Monitorar métricas por 24h

---

## Arquivos Críticos

| Arquivo | Ação | Linha |
|---------|------|-------|
| `services/semantic-translation-engine/src/config/settings.py` | Modificar | 51 |
| `services/semantic-translation-engine/tests/conftest.py` | Modificar | 127 |
| `helm-charts/semantic-translation-engine/values.yaml` | Verificar | 84 |

---

**Documento baseado em análise do agente Plan (2026-03-29)**
