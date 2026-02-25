# RELATÓRIO - ANÁLISE DE CAUSA RAIZ (FALHAS DE NÓS)
**Data:** 2026-02-23
**Período analisado:** 14:00 - 15:00 UTC
**Nodes afetados:** vmi2911681, vmi3002938, vmi3075398

---

## Resumo Executivo

**Status:** ✅ INVESTIGAÇÃO CONCLUÍDA

Três nodes do cluster Kubernetes tornaram-se unreachable simultaneamente por volta das 14:15 UTC, causando falha generalizada nos pods. A recuperação ocorreu naturalmente após ~30 minutos. A causa raiz principal está relacionada a problemas de conectividade do kubelet, possivelmente desencadeados por pressão de disco em um dos nodes.

---

## Linha do Tempo

| Hora (UTC) | Evento | Node(s) Afetado(s) |
|------------|--------|-------------------|
| ~14:15 | Nodes começam a reportar "NodeStatusUnknown" | Todos os 3 |
| 14:30 | 3 de 5 nodes em estado NotReady | vmi2911681, vmi3002938, vmi3075398 |
| 14:32 | vmi3002938: DiskPressure + EvictionThresholdMet | vmi3002938 |
| 14:35 | vmi2911681: DiskPressure + EvictionThresholdMet | vmi2911681 |
| 14:36-14:37 | Nodes começam a recuperar (kubelet responde) | Todos os 3 |
| 14:46-14:54 | Todos os nodes Ready novamente | Todos |

---

## Causas Raiz Identificadas

### 1. EvictionThresholdMet - vmi2911681

**Evidências:**
```
Warning  EvictionThresholdMet   13m (x3 over 16d)    kubelet
Message: Attempting to reclaim ephemeral-storage
```

**Análise:**
- O kubelet acionou o eviction threshold 3 vezes em 16 dias
- Este node apresenta um padrão recorrente de pressão de armazenamento efêmero
- 21 pods rodando neste node, incluindo pods de observability com alto volume de logs

**Impacto:**
- Durante o eviction, o kubelet pode ter ficado não responsivo
- Pods foram being evicted ou não conseguiam ser agendados

### 2. "NodeStatusUnknown" - Todos os Nodes

**Evidências:**
```
Kubelet stopped posting node status
LastHeartbeatTime parou de atualizar
```

**Análise:**
- O kubelet parou de enviar heartbeats para o API server
- Mensagem: "NodeStatusUnknown"
- Causa provável:
  1. **Resource exhaustion** (memória, CPU, ou I/O)
  2. **Network connectivity issue** entre node e API server
  3. **Kubelet crash** ou deadlock

### 3. Longhorn Instance-Managers Recriados

**Evidências:**
```
instance-manager-bcc6e6950ea173ae29641668c160e4f3   Age: 33m (vmi2911681)
instance-manager-f2206d1c236ec31c66885bf05231058d   Age: 32m (vmi3075398)
instance-manager-cbf6e6950ea173ae29641668c160e4f3   Age: 33m (vmi3002938)
```

**Análise:**
- Instance-managers do Longhorn foram recriados ~33 minutos atrás
- Coincide com o período de falha dos nodes
- Possível correlação: problemas de I/O no sistema de arquivos afetaram tanto o kubelet quanto o Longhorn

---

## Estado Atual dos Nodes

| Node | Status | CPU | Memória | Pods Running | Problemas |
|------|--------|-----|---------|--------------|-----------|
| vmi2092350 | Ready | 78% (6310m) | 35% | ~35 | Control-plane |
| vmi2911680 | Ready | 18% (1120m) | 55% | ~25 | ✅ Sem problemas |
| vmi2911681 | Ready | 7% (448m) | 50% | 21 | ⚠️ Histórico de DiskPressure |
| vmi3002938 | Ready | 30% (1813m) | 69% | 32 | Sem problemas |
| vmi3075398 | Ready | 5% (309m) | 17% | 13 | Sem problemas |

---

## Pods nos Nodes Afetados

### vmi2911681 (21 pods)
- ingress-nginx-controller (alto volume de logs)
- loki + loki-promtail (coletores de logs)
- prometheus-node-exporter
- mlflow
- optimizer-agents (2 pods)
- semantic-translation-engine
- specialists (behavior, business, technical)

### vmi3002938 (32 pods)
- Maior número de pods
- 71% de memória utilizada

### vmi3075398 (13 pods)
- Menor número de pods
- Apenas 17% de memória utilizada
- Recuperação mais rápida

---

## Análise Detalhada

### Fator 1: Ephemeral Storage Pressure

O kubelet do Kubernetes tem um **eviction threshold** configurado (padrão: 100MB livre ou 95% de uso). Quando atingido:
1. Pods começam a ser evicted
2. O kubelet tenta reclaim space
3. Durante este processo, o kubelet pode se tornar não responsivo
4. Heartbeats param de ser enviados
5. Node é marcado como "NodeStatusUnknown"

### Fator 2: Resource Contention

**vmi2911681** tinha 21 pods incluindo:
- Ingress controller com alto I/O
- Loki (armazenamento de logs) com alto uso de disco
- Instance-managers do Longhorn com I/O intensivo

A combinação de múltiplos pods com I/O intensivo pode ter causado:
- Contenção de disco (I/O wait)
- Kubelet unable to write heartbeats
- Degradation geral do sistema

### Fator 3: Network Connectivity

Os eventos mostram uma Timeline consistente:
1. Nodes pararam de reportar status quase simultaneamente
2. Longhorn managers foram recriados em todos os 3 nodes
3. Recuperação ocorreu naturalmente após ~30 minutos

Isso sugere um **problema de rede transitório** ou um **event storm** que afetou:
- Comunicação kubelet ↔ API server
- Longhorn manager ↔ API server

---

## Recomendações

### Imediatas

1. **Aumentar threshold de eviction** para ephemeral-storage:
   ```yaml
   kubeletExtraArgs:
     eviction-soft: "nodefs.available<15%,nodefs.inodesFree<10%"
     eviction-hard: "nodefs.available<10%,imagefs.available<15%,nodefs.inodesFree<5%"
   ```

2. **Monitoramento específico**:
   - Adicionar alerts para "NodeStatusUnknown"
   - Monitorar kubelet uptime
   - Alertar em eviction threshold

3. **Distribuir carga** melhor:
   - Mover pods de observability do vmi2911681
   - Balancear pods mais uniformemente

### Longo Prazo

1. **Investigar infraestrutura de rede**:
   - Verificar switch/roteador entre nodes e control-plane
   - Configurar timeout e keepalive apropriados

2. **Aumentar capacidade de disco**:
   - Adicionar storage dedicado para logs
   - Implementar log rotation mais agressiva

3. **Node auto-repair**:
   - Configurar mecanismo automático de recovery
   - Considerar restart de kubelet em caso de "NodeStatusUnknown"

4. **Separar workloads**:
   - Isolar pods de I/O intensivo (Longhorn, Loki, Prometheus)
   - Usar node selectors para segregação

---

## Conclusão

A causa raiz mais provável foi uma combinação de:

1. **Primário**: EvictionThresholdMet em vmi2911681 desencadeando pressão de recurso
2. **Contribuidor**: I/O contention afetando kubelet responsividade
3. **Possível**: Problema de rede transitório exacerbando a situação

O sistema se recuperou naturalmente após o kubelet reclaim espaço e os nodes voltarem a reportar status. No entanto, sem intervenção preventiva, este problema pode recorrer.

**Próximos passos recomendados:**
- Implementar alertas proativos
- Ajustar thresholds de eviction
- Distribuir carga de I/O entre nodes
- Investigar conectividade de rede

---

**Assinado:** Análise de Causa Raiz
**Data:** 2026-02-23 15:30 UTC
