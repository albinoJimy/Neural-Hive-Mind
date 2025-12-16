# Relatório de Análise Profunda - Problemas Bloqueadores

## Neural Hive Mind - E2E Test Blockers Analysis
**Data:** 2025-12-04 09:10 UTC
**Versão:** 1.0.8
**Analista:** Claude Code

---

## Resumo Executivo

O teste E2E foi bloqueado por uma **cadeia de dependências não satisfeitas** que impede o funcionamento dos specialists. A análise identificou **5 problemas principais**, todos interconectados:

| # | Problema | Severidade | Impacto |
|---|----------|------------|---------|
| 1 | Imagens de containers ausentes | CRÍTICO | 3/5 specialists não iniciam |
| 2 | MongoDB sem autenticação configurada | CRÍTICO | Circuit breaker aberto |
| 3 | Modelos ML não registrados no MLflow | CRÍTICO | Specialists em NOT_SERVING |
| 4 | Pods órfãos saturando o cluster | ALTO | 2175 pods em ContainerStatusUnknown |
| 5 | Configuração de secrets incorreta | MÉDIO | Falha de conexão MongoDB |

---

## Problema 1: Imagens de Containers Ausentes

### Descrição
Três dos cinco specialists não possuem suas imagens Docker disponíveis nos worker nodes, impedindo o início dos pods.

### Evidência
```
specialist-architecture-5f5b498c6b-6vtqv   0/1   ErrImageNeverPull
specialist-business-[hash]                  0/1   ErrImageNeverPull
specialist-technical-[hash]                 0/1   ErrImageNeverPull
```

### Inventário de Imagens nos Workers

| Imagem | Worker 1 (vmi2911681) | Worker 2 (vmi2911680) |
|--------|----------------------|----------------------|
| specialist-behavior:1.0.8 | ✅ | ✅ |
| specialist-evolution:1.0.8 | ✅ | ✅ |
| specialist-architecture:1.0.8 | ❌ | ❌ |
| specialist-business:1.0.8 | ❌ | ❌ |
| specialist-technical:1.0.8 | ❌ | ❌ |

### Causa Raiz
- `imagePullPolicy: Never` configurado nos deployments
- Build das imagens faltantes não foi executado
- Não há registry privado configurado para pull automático

### Solução Proposta
```bash
# Opção 1: Build e export direto para workers
cd /jimy/Neural-Hive-Mind
./scripts/build-and-push-images.sh specialist-architecture specialist-business specialist-technical

# Opção 2: Export via pipe SSH
for svc in specialist-architecture specialist-business specialist-technical; do
  docker save neural-hive-mind/${svc}:1.0.8 | \
    ssh root@84.247.138.35 "ctr -n k8s.io images import -"
  docker save neural-hive-mind/${svc}:1.0.8 | \
    ssh root@158.220.101.216 "ctr -n k8s.io images import -"
done
```

---

## Problema 2: MongoDB Sem Autenticação Configurada

### Descrição
Os specialists estão tentando conectar ao MongoDB sem credenciais, mas o MongoDB requer autenticação.

### Evidência (Logs do Specialist)
```
[error] Falha ao inicializar AuditLogger - audit logging desabilitado
error="Command createIndexes requires authentication, full error:
{'ok': 0.0, 'errmsg': 'Command createIndexes requires authentication',
'code': 13, 'codeName': 'Unauthorized'}"
```

### Configuração Atual vs Esperada

| Aspecto | Atual | Esperado |
|---------|-------|----------|
| MONGODB_URI | `mongodb://mongodb...:27017/neural_hive` | `mongodb://root:PASSWORD@mongodb...:27017/neural_hive?authSource=admin` |
| Autenticação | Não incluída | Root password: `local_dev_password` |

### Causa Raiz
- A variável `MONGODB_URI` no deployment não inclui credenciais
- O secret `mongodb` no namespace `mongodb-cluster` contém a senha (`local_dev_password`)
- Os specialists não referenciam este secret corretamente

### Solução Proposta
```yaml
# Atualizar ConfigMap/Deployment dos specialists:
env:
  - name: MONGODB_URI
    value: "mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive?authSource=admin"
```

Ou usar secretKeyRef:
```yaml
env:
  - name: MONGODB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: mongodb
        key: mongodb-root-password
  - name: MONGODB_URI
    value: "mongodb://root:$(MONGODB_PASSWORD)@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive?authSource=admin"
```

---

## Problema 3: Modelos ML Não Registrados no MLflow

### Descrição
Os specialists tentam carregar modelos do MLflow Model Registry, mas os modelos não existem.

### Evidência
```
[info] Loading model from MLflow model_name=behavior stage=Staging
[error] Failed to load model from MLflow
error='RESOURCE_DOES_NOT_EXIST: Registered Model with name=behavior not found'
[warning] ML model not available, using heuristics
```

### Estado Atual do MLflow
- MLflow está rodando: `mlflow-849cb94ddf-qgmcj` (1/1 Running)
- API respondendo em: `http://mlflow.mlflow.svc.cluster.local:5000`
- Experiments existem mas modelos não estão registrados

### Modelos Esperados vs Registrados

| Specialist | Modelo Esperado | Stage | Registrado |
|------------|-----------------|-------|------------|
| behavior | `behavior` | Staging | ❌ |
| evolution | `evolution` | Staging | ❌ |
| architecture | `architecture` | Staging | ❌ |
| business | `business` | Staging | ❌ |
| technical | `technical` | Staging | ❌ |

### Causa Raiz
- Pipeline de treinamento de modelos nunca foi executado
- Modelos não foram registrados no MLflow Model Registry
- Specialists caem para modo "heurístico" que ainda requer outras dependências

### Solução Proposta
```bash
# 1. Executar pipeline de treinamento
cd /jimy/Neural-Hive-Mind/ml_pipelines/training
./train_all_specialists.sh

# 2. Ou registrar modelos manualmente via MLflow API
mlflow models create --name behavior
mlflow models transition-stage --name behavior --version 1 --stage Staging
```

### Impacto nos Specialists
O specialist ainda pode funcionar em "modo heurístico" sem o modelo ML, porém:
- Requer MongoDB funcionando (para ledger)
- Circuit breaker abre após falhas de modelo
- Status: `NOT_SERVING` mesmo com pod `Running`

---

## Problema 4: Pods Órfãos Saturando o Cluster

### Descrição
Há **2175 pods** em estado `ContainerStatusUnknown` no namespace `neural-hive`, consumindo recursos do API Server.

### Evidência
```bash
$ kubectl get pods -n neural-hive | grep -c "ContainerStatusUnknown"
2175
```

### Padrão Observado
- Maioria são do `specialist-architecture` com múltiplos ReplicaSets
- Pods criados há 10-12h atrás
- Status indicativo de node que ficou indisponível

### Causa Raiz
- Provável reinício ou falha de node worker
- Kubelet não conseguiu reportar status final dos pods
- Garbage collector não limpou automaticamente

### Solução Proposta
```bash
# Limpar pods órfãos
kubectl delete pods -n neural-hive --field-selector=status.phase=Unknown --force --grace-period=0

# Ou via status específico
kubectl get pods -n neural-hive | grep ContainerStatusUnknown | awk '{print $1}' | \
  xargs kubectl delete pod -n neural-hive --force --grace-period=0

# Verificar ReplicaSets órfãos
kubectl get rs -n neural-hive | awk '$2==0 && $3==0 {print $1}' | \
  xargs kubectl delete rs -n neural-hive
```

---

## Problema 5: Configuração de Secrets Incorreta

### Descrição
Os specialists usam URI do MongoDB sem autenticação, embora o values.yaml defina o padrão correto.

### Comparação de Configurações

**values.yaml (esperado):**
```yaml
secrets:
  mongodbUri: "mongodb://root:CHANGEME_PRODUCTION_PASSWORD@mongodb...:27017/neural_hive?authSource=admin"
```

**Environment no Pod (atual):**
```
MONGODB_URI=mongodb://mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive
```

### Causa Raiz
- O Helm chart usa `values-local.yaml` que pode sobrescrever
- A senha `CHANGEME_PRODUCTION_PASSWORD` nunca foi substituída
- Deploy local não usou a configuração de autenticação

### Arquivos Envolvidos
- `helm-charts/specialist-*/values.yaml` - Configuração base
- `helm-charts/specialist-*/values-local.yaml` - Override local
- `helm-charts/specialist-*/templates/deployment.yaml` - Template

### Solução Proposta
Verificar e atualizar `values-local.yaml`:
```yaml
secrets:
  mongodbUri: "mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive?authSource=admin"
```

Ou aplicar patch direto:
```bash
for spec in behavior evolution architecture business technical; do
  kubectl set env deployment/specialist-${spec} -n neural-hive \
    MONGODB_URI="mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive?authSource=admin"
done
```

---

## Diagrama de Dependências e Falhas

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CADEIA DE FALHAS                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┐                                                        │
│  │ IMAGENS AUSENTES │──────► 3 Specialists não iniciam                       │
│  │ (architecture,   │        (ErrImageNeverPull)                             │
│  │  business,       │                                                        │
│  │  technical)      │                                                        │
│  └──────────────────┘                                                        │
│                                                                              │
│  ┌──────────────────┐     ┌─────────────────┐     ┌───────────────────────┐ │
│  │ MONGODB AUTH     │────►│ Circuit Breaker │────►│ Ledger Unavailable    │ │
│  │ (Unauthorized)   │     │ OPEN            │     │ status=NOT_SERVING    │ │
│  └──────────────────┘     └─────────────────┘     └───────────────────────┘ │
│                                                              │               │
│  ┌──────────────────┐                                        ▼               │
│  │ MLFLOW MODELS    │────►  Modelo não carregado ───► specialist_type=X     │
│  │ (não existem)    │       model_loaded=False        status=NOT_SERVING    │
│  └──────────────────┘                                        │               │
│                                                              ▼               │
│                                                   ┌─────────────────────────┐│
│                                                   │  Consensus Engine       ││
│                                                   │  "Pareceres             ││
│                                                   │   insuficientes: 0/5"   ││
│                                                   └─────────────────────────┘│
│                                                              │               │
│                                                              ▼               │
│                                                   ┌─────────────────────────┐│
│                                                   │  FLUXO C BLOQUEADO      ││
│                                                   └─────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Plano de Ação Prioritizado

### FASE 1: Infraestrutura Imediata (Estimativa: depende do build)

| # | Ação | Comando | Responsável |
|---|------|---------|-------------|
| 1 | Limpar pods órfãos | `kubectl delete pods -n neural-hive --field-selector=status.phase=Unknown --force` | DevOps |
| 2 | Build imagens faltantes | `./scripts/build-and-push-images.sh specialist-architecture specialist-business specialist-technical` | DevOps |
| 3 | Export para workers | `./scripts/export-images-to-workers.sh` | DevOps |

### FASE 2: Configuração de Autenticação

| # | Ação | Detalhes |
|---|------|----------|
| 4 | Atualizar MongoDB URI | Adicionar credenciais nos deployments |
| 5 | Restart specialists | `kubectl rollout restart deployment -n neural-hive -l app.kubernetes.io/part-of=neural-hive-mind` |
| 6 | Verificar conexão | Checar logs para "MongoDB connection established" |

### FASE 3: Modelos ML

| # | Ação | Detalhes |
|---|------|----------|
| 7 | Executar training | `./ml_pipelines/training/train_all_specialists.sh` |
| 8 | Registrar modelos | Promote para Staging no MLflow |
| 9 | Restart specialists | Forçar reload dos modelos |

### FASE 4: Validação

| # | Ação | Critério de Sucesso |
|---|------|---------------------|
| 10 | Health check | Todos specialists `status=SERVING` |
| 11 | Retest E2E | Fluxo C completo com decisão consolidada |

---

## Métricas de Saúde Atual

| Componente | Status | Métrica |
|------------|--------|---------|
| Gateway Intenções | ✅ HEALTHY | `/health` HTTP 200 |
| STE | ✅ HEALTHY | Processando plans |
| Kafka | ✅ RUNNING | Mensagens fluindo |
| MongoDB | ⚠️ AUTH_REQUIRED | Conexões rejeitadas |
| MLflow | ✅ RUNNING | API respondendo |
| Specialists Running | ⚠️ 2/5 | behavior, evolution |
| Specialists SERVING | ❌ 0/5 | Todos NOT_SERVING |

---

## Conclusão

O sistema Neural Hive Mind está operacional até o **Fluxo B parcial** (STE gera plans), porém o **Fluxo C está completamente bloqueado** devido a:

1. **Imagens ausentes** - Resolve-se com build/export
2. **MongoDB auth** - Resolve-se com configuração de secrets
3. **Modelos ML** - Resolve-se com pipeline de treinamento

A solução mais rápida para validação E2E seria:
1. Configurar MongoDB auth nos 2 specialists existentes (behavior, evolution)
2. Testar se Consensus Engine aceita 2/5 pareceres (quórum mínimo)
3. Se não aceitar, fazer build das 3 imagens faltantes

**Tempo estimado para resolução completa:** Depende da disponibilidade para build de imagens e execução do pipeline de ML.

---

*Relatório gerado em 2025-12-04 09:10 UTC*
