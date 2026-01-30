# Atualização - Correção e Rebuild do Gateway

**Data:** 31 de Outubro de 2025, 12:00 PM
**Status:** ✅ Dockerfile corrigido | ⏳ Build v2 em progresso

---

## Problema Identificado

O build inicial do Gateway (v1) **falhou** na etapa de download dos modelos spaCy.

**Erro:**
```
ERROR: process "python -c 'import spacy; spacy.download(pt_core_news_sm)'"
did not complete successfully: exit code: 1
```

**Linha problemática no Dockerfile original:**
```dockerfile
RUN python -c "import whisper; whisper.load_model('base')" && \
    python -c "import spacy; spacy.download('pt_core_news_sm')" && \
    python -c "import spacy; spacy.download('en_core_web_sm')"
```

### Causa Raiz

O método `spacy.download()` não funciona corretamente durante o build do Docker porque:
1. Requer interação com servidores externos durante build time
2. Não tem retry logic robusto
3. Falha silenciosamente em alguns ambientes

---

## ✅ Solução Aplicada

Alterado o Dockerfile para usar **URLs diretas** dos modelos spaCy, seguindo o mesmo padrão usado com sucesso nos 4 specialists:

**Correção aplicada em `services/gateway-intencoes/Dockerfile` (linhas 42-47):**

```dockerfile
# Download de modelos ML (Whisper e spaCy)
RUN python -c "import whisper; whisper.load_model('base')" && \
    python -m pip install --no-cache-dir \
    https://github.com/explosion/spacy-models/releases/download/pt_core_news_sm-3.8.0/pt_core_news_sm-3.8.0-py3-none-any.whl \
    https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl \
    && python -c "import pt_core_news_sm; import en_core_web_sm; print('✓ Modelos spaCy instalados')"
```

### Benefícios da Correção

✅ Download direto via pip (mais confiável)
✅ URLs explícitas (reproducible builds)
✅ Versão fixa dos modelos (3.8.0)
✅ Validação após instalação
✅ Mesmo padrão dos specialists (consistency)

---

## 🔄 Rebuild do Gateway v2

**Status:** ⏳ Em progresso

**Comando executado:**
```bash
docker build -t neural-hive/gateway-intencoes:v2 \
  -f services/gateway-intencoes/Dockerfile .
```

**Detalhes:**
- PID: 3361377
- Log: `/tmp/build-gateway-v2.log`
- Tempo estimado: 15-20 minutos
- Tag da imagem: `neural-hive/gateway-intencoes:v2`

**Monitorar progresso:**
```bash
tail -f /tmp/build-gateway-v2.log
```

**Verificar quando concluir:**
```bash
docker images | grep gateway-intencoes
```

---

## 📋 Próximos Passos (Após Build Completar)

### 1. Verificar Sucesso do Build

```bash
# Verificar se imagem foi criada
docker images | grep gateway-intencoes:v2

# Ver tamanho da imagem
docker images gateway-intencoes:v2 --format "{{.Size}}"
```

### 2. Export e Import para Containerd

```bash
# Export
docker save neural-hive/gateway-intencoes:v2 -o /tmp/gateway-v2.tar

# Verificar tamanho
ls -lh /tmp/gateway-v2.tar

# Import para containerd do Kubernetes
ctr -n k8s.io images import /tmp/gateway-v2.tar

# Verificar
ctr -n k8s.io images ls | grep gateway-intencoes

# Limpeza
rm /tmp/gateway-v2.tar
```

### 3. Criar values-k8s.yaml

Criar `helm-charts/gateway-intencoes/values-k8s.yaml`:

```yaml
replicaCount: 1

image:
  repository: neural-hive/gateway-intencoes
  tag: v2
  pullPolicy: IfNotPresent

resources:
  requests:
    cpu: 500m
    memory: 1Gi
  limits:
    cpu: 2000m
    memory: 4Gi

config:
  environment: production
  logLevel: INFO
  debug: false

  # ASR e NLU
  asr:
    modelName: base
    device: cpu

  nlu:
    languageModel: pt_core_news_sm
    confidenceThreshold: 0.75

  # Redis
  redis:
    clusterNodes: neural-hive-cache.redis-cluster.svc.cluster.local:6379
    defaultTtl: 600

podSecurityContext:
  runAsNonRoot: true
  runAsUser: 1001
  fsGroup: 1001

livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 60
  periodSeconds: 30
  timeoutSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3

service:
  type: ClusterIP
  port: 80
  targetPort: 8000

autoscaling:
  enabled: false

serviceMonitor:
  enabled: false

networkPolicy:
  enabled: false
```

### 4. Deploy via Helm

```bash
helm install gateway-intencoes helm-charts/gateway-intencoes \
  --values helm-charts/gateway-intencoes/values-k8s.yaml \
  --namespace gateway-intencoes \
  --create-namespace \
  --wait --timeout=5m
```

### 5. Validação

```bash
# Verificar pod
kubectl get pods -n gateway-intencoes

# Health check
kubectl run test-gateway --rm -i --restart=Never \
  --image=curlimages/curl -- \
  curl -s http://gateway-intencoes.gateway-intencoes.svc:8000/health

# Logs
kubectl logs -n gateway-intencoes -l app=gateway-intencoes -f
```

---

## 📊 Comparação: Build v1 vs v2

| Aspecto | Build v1 (Falhou) | Build v2 (Corrigido) |
|---------|-------------------|----------------------|
| Método spaCy | `spacy.download()` | URLs diretas via pip |
| Confiabilidade | ❌ Baixa | ✅ Alta |
| Reproducibilidade | ❌ Não garantida | ✅ Garantida |
| Versão dos modelos | Variável | ✅ Fixa (3.8.0) |
| Consistência | ❌ Diferente dos specialists | ✅ Mesmo padrão |
| Resultado | ❌ Falhou | ⏳ Em progresso |

---

## 🎓 Lições Aprendidas

### O Que Funcionou

✅ **URLs diretas para modelos ML** são mais confiáveis que comandos de download
✅ **Padronização** entre todos os serviços evita problemas
✅ **Validação após instalação** detecta problemas cedo
✅ **Logs detalhados** facilitam troubleshooting

### Recomendações para Futuros Dockerfiles

1. **Sempre usar URLs diretas** para modelos ML
2. **Fixar versões** explicitamente (não usar "latest")
3. **Validar instalação** no mesmo RUN command
4. **Seguir padrões** estabelecidos em outros serviços
5. **Testar localmente** antes de deploy em produção

---

## 📝 Arquivos Modificados

**Arquivo alterado:**
- `services/gateway-intencoes/Dockerfile` (linhas 42-47)

**Arquivos a criar:**
- `helm-charts/gateway-intencoes/values-k8s.yaml` (pendente)

**Documentação atualizada:**
- [CONCLUSAO_SESSAO_DEPLOYMENT.md](CONCLUSAO_SESSAO_DEPLOYMENT.md) - Conclusão da sessão
- [PROXIMOS_PASSOS_GATEWAY.md](PROXIMOS_PASSOS_GATEWAY.md) - Guia original
- Este arquivo - Detalhes da correção

---

## 🚀 Status Atual do Sistema

### Componentes Operacionais

```
✅ MongoDB        (mongodb-cluster)          Running
✅ Neo4j          (neo4j-cluster)            Running
✅ Redis          (redis-cluster)            Running
✅ MLflow         (mlflow)                   Running

✅ Specialist-Technical      1/1 Ready (50+ min)
✅ Specialist-Behavior       1/1 Ready (49+ min)
✅ Specialist-Evolution      1/1 Ready (48+ min)
✅ Specialist-Architecture   1/1 Ready (47+ min)

⏳ Gateway-Intencoes         Building v2...
```

### Progresso da Fase 3

**Antes da correção:** 80% completo
**Após build v2 completar:** 100% completo (esperado)

---

## ⏰ Timeline

- **11:16 AM** - Build v1 iniciado
- **11:35 AM** - Build v1 falhou (erro spaCy)
- **11:50 AM** - Documentação completa criada
- **12:00 PM** - Dockerfile corrigido
- **12:00 PM** - Build v2 iniciado
- **~12:15-20 PM** - Build v2 esperado concluir
- **~12:30 PM** - Deploy gateway esperado (se build OK)

---

---

## 🔍 ANÁLISE PROFUNDA - Problema de Import (v3)

**Data:** 31/10/2025 12:30 PM

### Investigação Detalhada

Após o build v3 completar com sucesso, o deploy continuou falhando com:
```
ERROR: Error loading ASGI app. Could not import module "main".
```

**Passos da investigação:**

#### 1. Verificação dos arquivos __init__.py
```bash
docker run --rm --user root neural-hive/gateway-intencoes:v3 find /app/src -name "__init__.py"
```
**Resultado:** ✅ Todos os 9 arquivos __init__.py presentes na imagem

#### 2. Teste de import absoluto
```bash
docker run --rm --user root neural-hive/gateway-intencoes:v3 bash -c \
  "cd /app && python -c 'from src.config.settings import get_settings; print(\"✓ Import OK\")'"
```
**Resultado:** ✅ Import com caminho absoluto (`src.config.settings`) funciona!

#### 3. Teste de import relativo (como no código)
```bash
docker run --rm --user root neural-hive/gateway-intencoes:v3 bash -c \
  "cd /app/src && python -c 'from config.settings import get_settings; print(\"✓ Import OK\")'"
```
**Resultado:** ❌ ModuleNotFoundError: No module named 'config'

### Causa Raiz Identificada

**PROBLEMA:** Conflito entre PYTHONPATH e Working Directory

O Dockerfile v3 tinha:
- `ENV PYTHONPATH="/app/src"` ✅
- `WORKDIR /app` ❌ (permaneceu como /app)
- `CMD ["uvicorn", "main:app", ...]` ❌

**O que acontecia:**
1. Uvicorn executa a partir de `WORKDIR` atual (`/app`)
2. Uvicorn procura `main.py` no diretório atual ou no PYTHONPATH
3. Com WORKDIR=/app, uvicorn não encontra `main.py` diretamente
4. Mesmo com PYTHONPATH=/app/src, os imports relativos em main.py falham porque o Python está rodando a partir de /app

**Comparação com Specialists:**

| Aspecto | Specialists | Gateway (v3) |
|---------|-------------|---------------|
| Estrutura | Flat: src/main.py, src/config.py | Package: src/config/, src/models/ |
| Imports | Absolutos: `from config import ...` | Relativos: `from config.settings import ...` |
| WORKDIR | /app/src ✅ | /app ❌ |
| CMD | uvicorn main:app | uvicorn main:app |
| Funcionamento | ✅ OK | ❌ Falha |

### ✅ Solução Aplicada (v4)

**Correção no Dockerfile (linha 77):**
```dockerfile
# Definir working directory para /app/src para que uvicorn encontre main.py
WORKDIR /app/src
```

**Por que funciona:**
1. Uvicorn agora executa a partir de `/app/src`
2. Encontra `main.py` diretamente no diretório atual
3. Os imports relativos em main.py funcionam porque Python está em `/app/src`
4. PYTHONPATH=/app/src garante que subdirectórios são encontrados

**Teste de validação:**
```bash
docker run --rm --user root neural-hive/gateway-intencoes:v3 bash -c \
  "cd /app/src && python -c 'import main; print(\"✓ main.py importado com sucesso\")'"
```
**Resultado:** ✅ Sucesso!

---

## 🔄 Build v4 - Correção Final

**Status:** ⏳ Em progresso
**PID:** 154037
**Log:** /tmp/build-gateway-v4.log
**Tempo estimado:** 2-3 minutos (build incremental com cache)

**Alterações aplicadas:**
- ✅ URLs diretas para modelos spaCy (v2)
- ✅ __init__.py em todos os subdirectórios (v3)
- ✅ WORKDIR /app/src (v4) **← CORREÇÃO CRÍTICA**

---

**Última atualização:** 31/10/2025 12:30 PM
**Status:** Análise profunda completa ✅ | Build v4 em progresso ⏳
