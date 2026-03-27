# Quick Start - Correções Bloqueadores Críticos
## Neural Hive-Mind - Fase 1

---

## ⚡ TL;DR

**Status Atual**: ⚠️ Infraestrutura deployada mas fluxo E2E bloqueado

**3 Comandos Críticos** (5 minutos):

```bash
# 1. Criar tópicos Kafka faltantes
kubectl apply -f - <<EOF
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: plans-ready
  namespace: kafka
  labels:
    strimzi.io/cluster: neural-hive-kafka
spec:
  partitions: 3
  replicas: 1
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: plans-consensus
  namespace: kafka
  labels:
    strimzi.io/cluster: neural-hive-kafka
spec:
  partitions: 3
  replicas: 1
EOF

# 2. Validar tópicos criados
kubectl get kafkatopic -n kafka | grep plans

# 3. Re-executar teste E2E
./tests/phase1-end-to-end-test.sh --continue-on-error --debug
```

**Se ainda falhar**: Consultar `COMANDOS_CORRECAO_BLOQUEADORES.md`

---

## 📊 Status dos Componentes

```
✅ Kafka (1/1 broker)
✅ MongoDB (1/1 pod)
✅ Redis (1/1 pod)
✅ Neo4j (1/1 pod)
✅ Gateway (1/1 pod)
✅ STE (1/1 pod)
⚠️ Consensus Engine (1/1 - com erros TypeError)
⚠️ 5 Specialists (3 OK, 2 com problemas)
❌ Tópicos Kafka (5/7 - faltam 2)
❌ Observabilidade (0/3 - não deployada)
```

---

## 🔴 Bloqueadores Identificados

1. **Tópicos Kafka**: `plans.ready` e `plans.consensus` não existem
2. **Publicação Kafka**: Script de teste falha ao publicar
3. **Serialização**: TypeError ao deserializar protobuf

---

## 📚 Documentação Gerada

```
tests/results/
├── PHASE1_E2E_TEST_REPORT.md      (15KB - relatório completo)
├── phase1-e2e-output-*.log        (4KB - log de execução)
└── README.md                      (índice)

/
├── SUMARIO_TESTE_E2E_FASE1.md              (3KB - sumário executivo)
├── COMANDOS_CORRECAO_BLOQUEADORES.md       (8KB - guia de correção)
└── QUICK_START_CORRECOES.md                (este arquivo)
```

---

## 🚀 Workflow Recomendado

### Opção 1: Correção Rápida (5-10 min)

```bash
# 1. Criar tópicos Kafka
kubectl apply -f - <<EOF
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: plans-ready
  namespace: kafka
  labels:
    strimzi.io/cluster: neural-hive-kafka
spec:
  partitions: 3
  replicas: 1
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: plans-consensus
  namespace: kafka
  labels:
    strimzi.io/cluster: neural-hive-kafka
spec:
  partitions: 3
  replicas: 1
EOF

# 2. Aguardar tópicos ficarem Ready
kubectl wait --for=condition=Ready kafkatopic/plans-ready -n kafka --timeout=2m
kubectl wait --for=condition=Ready kafkatopic/plans-consensus -n kafka --timeout=2m

# 3. Re-executar teste
./tests/phase1-end-to-end-test.sh --continue-on-error --debug
```

### Opção 2: Correção Completa (2-4 horas)

```bash
# Seguir guia completo
less COMANDOS_CORRECAO_BLOQUEADORES.md

# Executar seções em ordem:
# - Seção 1: Tópicos Kafka (5 min)
# - Seção 2: Publicação Kafka (15 min)
# - Seção 3: Serialização Protobuf (30-60 min)
# - Validação Final (10 min)
```

---

## 🎯 Critério de Sucesso

O teste E2E será considerado **PASSED** quando:

- ✅ Todos os 7 tópicos Kafka estão Ready
- ✅ Intent Envelope publicado com sucesso
- ✅ STE gera Cognitive Plan
- ✅ 5/5 (ou 3/5) Specialists avaliam
- ✅ Consensus Engine gera decisão
- ✅ Registros no MongoDB
- ✅ Sem erros TypeError nos logs

---

## 📞 Ajuda Adicional

- **Relatório Completo**: `tests/results/PHASE1_E2E_TEST_REPORT.md`
- **Comandos Detalhados**: `COMANDOS_CORRECAO_BLOQUEADORES.md`
- **Guia de Testes**: `docs/PHASE1_TESTING_GUIDE.md`

---

## ⚠️ Avisos Importantes

1. **Consensus Engine** estava com 0 réplicas → **JÁ CORRIGIDO**
2. **Specialist Business** com 567 restarts → Deletar pod problemático
3. **Specialist Technical** com pod Pending → Escalar para 1 réplica
4. **Observabilidade** não deployada → Não bloqueia mas impede métricas

---

**Tempo Total Estimado**: 2-4 horas
**Prioridade**: P0 (Crítico)
**Última Atualização**: 2025-11-12 11:45 UTC
