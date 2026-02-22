# RESUMO: INVESTIGAÇÃO E CORREÇÕES DO FALLBACK_STUB

## Data: 2026-02-22

---

## STATUS ATUAL

✅ **Problema Identificado:** Namespace mismatch entre Workers e Orchestrator
⚠️ **Solução Implementada:** Awaiting new image build
⏳ **Teste de Validação:** Pendente

---

## INVESTIGAÇÃO REALIZADA

### 1. Causa Raiz Confirmada

**Capability Mismatch** (RESOLVIDO após reinício dos workers):
```
Workers antigos:  [optimization, experiment_management, ...]
Workers novos:   [python, terraform, kubernetes, read, write, ...]
Tickets requerem: [analyze, read, ...]
```

### 2. Namespace Mismatch (IDENTIFICADO)

```
Orchestrator filtra:  namespace="neural-hive"      (POD_NAMESPACE)
Workers registrados:   namespace="default"         (env var NAMESPACE)
Service Registry:      namespace filter aplicado

Resultado: Nenhum worker encontrado → fallback_stub
```

### 3. Análise do Commit 98c6f27

**Conclusão:** O commit adicionou apenas observabilidade (logs/métricas), não resolveu o problema de raiz.

---

## CORREÇÕES IMPLEMENTADAS

### Commit 1: b70171f
```python
# Altera namespace padrão de 'neural-hive-execution' para 'neural-hive'
namespace: str = Field(default='neural-hive', ...)

# Adiciona validator para usar POD_NAMESPACE
@model_validator(mode='after')
def validate_namespace_from_env(self):
    pod_namespace = os.environ.get('POD_NAMESPACE')
    if pod_namespace and pod_namespace != 'default':
        self.namespace = pod_namespace
```

### Commit 2: cb9b964
```python
# Renomeia campo interno para namespace_ (evita conflito com env var)
namespace_: str = Field(default='neural-hive', alias='namespace')

# Adiciona property para compatibilidade
@property
def namespace(self) -> str:
    return self.namespace_
```

---

## PRÓXIMO PASSO

### Ação Necessária: Build e Deploy Nova Imagem

```bash
# 1. Build nova imagem worker-agents
docker build -t ghcr.io/albinojimy/neural-hive-mind/worker-agents:latest \
  services/worker-agents/

# 2. Push para registry
docker push ghcr.io/albinojimy/neural-hive-mind/worker-agents:latest

# 3. Atualizar deployment
kubectl set image deployment/worker-agents \
  worker-agents=ghcr.io/albinojimy/neural-hive-mind/worker-agents:latest \
  -n neural-hive
```

### Validação Após Deploy

```bash
# 1. Verificar namespace no Redis
kubectl exec -n redis-cluster redis-* -- redis-cli GET "neural-hive:agents:worker:*" | jq '.namespace'

# Esperado: "neural-hive" (não "default")

# 2. Testar descoberta via Service Registry
kubectl exec -n neural-hive service-registry-* -- python3 -c "
from src.clients.redis_registry_client import RedisRegistryClient
client = RedisRegistryClient(['redis-cluster.redis-cluster.svc.cluster.local:6379'], 'neural-hive:')
agents = await client.list_agents(filters={'namespace': 'neural-hive'})
print(f'Workers encontrados: {len(agents)}')
"

# 3. Enviar nova intenção de teste
kubectl exec -n neural-hive gateway-intencoes-* -- python3 -c "
import requests
requests.post('http://localhost:8000/intentions', json={...})
"

# 4. Verificar tickets criados
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic execution.tickets --from-beginning --max-messages 1

# Esperado: allocation_method != "fallback_stub"
```

---

## WORKAROUND TEMPORÁRIO (Se necessário)

Enquanto a nova imagem não está disponível, é possível forçar o namespace no Redis:

```bash
# Pegar worker ID
WORKER_ID=$(kubectl exec -n redis-cluster redis-* -- redis-cli --scan --pattern "neural-hive:agents:worker:*" | head -1 | cut -d: -f4)

# Ler dados
kubectl exec -n redis-cluster redis-* -- redis-cli GET "neural-hive:agents:worker:$WORKER_ID"

# Atualizar namespace (manual, via jq)
kubectl exec -n redis-cluster redis-* -- redis-cli SET "neural-hive:agents:worker:$WORKER_ID" \
  "$(kubectl exec -n redis-cluster redis-* -- redis-cli GET "neural-hive:agents:worker:$WORKER_ID" | \
  jq '.namespace = \"neural-hive\"' | jq -c .)"
```

---

## ESTRUTURA DO PROBLEMA

```
┌─────────────────────────────────────────────────────────────────────┐
│  FLUXO DE DESCOBERTA DE WORKERS                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Orchestrator                                           │
│    |                                                               │
│    |-- discover_agents(capabilities=['analyze'], │
│    |                         filters={namespace: 'neural-hive'})
│    |                                                               │
│    v                                                               │
│  Service Registry (Redis backend)                                │
│    |                                                               │
│    |-- list_agents()                                             │
│    |    |-- scan('neural-hive:agents:worker:*')                  │
│    |    |-- filter by namespace='neural-hive'  ← PROBLEMA AQUI   │
│    |    |-- filter by capabilities=['analyze']                   │
│    |                                                               │
│  Agents no Redis:                                                 │
│  {                                                               │
│    namespace: 'default',  ← NÃO MATCH 'neural-hive'            │
│    capabilities: ['read', 'analyze', ...]                        │
│  }                                                               │
│                                                                     │
│  Result: [] (vazio) → fallback_stub ativado                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## DOCUMENTAÇÃO RELACIONADA

- `docs/test-raw-data/2026-02-22/ANALISE_COMMIT_98c6f27_FALLBACK_STUB.md`
- `docs/test-raw-data/2026-02-22/TESTE_E2E_PIPELINE_COMPLETO.md`
- `docs/test-raw-data/2026-02-22/DETALHAMENTO_FLUXO_C.md`

---

## COMMITS CRIADOS

| Commit | Descrição |
|--------|-----------|
| `c13441c` | docs(analysis): analisa por que commit 98c6f27 não resolveu |
| `b70171f` | fix(worker-agents): corrige namespace para usar POD_NAMESPACE |
| `cb9b964` | fix(worker-agents): usa namespace_ para evitar conflito |

---

**Status:** Aguardando build de nova imagem worker-agents
