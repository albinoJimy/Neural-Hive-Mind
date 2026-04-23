# Plano de Correção Definitivo - Dockerfiles Neural Hive Mind

**Data:** 2026-04-23
**Status:** Phase 4 (Implementation) - Pronto para execução

---

## Resumo da Causa Raiz

**Problema Sistémico:** 9 serviços têm Dockerfiles que **não copiam o requirements-base.txt**, causando falha no build quando o requirements.txt local contém `-r ../../requirements-base.txt`.

---

## Serviços Afetados (9)

| Serviço | Status Dockerfile | Erro |
|---------|-------------------|------|
| `data-migration` | ❌ Quebrado | `../../requirements-base.txt` não copiado |
| `doc-ingestion` | ❌ Quebrado | `../../requirements-base.txt` não copiado |
| `documentation-generation` | ❌ Quebrado | `../../requirements-base.txt` não copiado |
| `test-generation` | ❌ Quebrado | `../../requirements-base.txt` não copiado |
| `requirements-engineering` | ❌ Quebrado | `../../requirements-base.txt` não copiado |
| `knowledge-graph-rag` | ❌ Quebrado | `../../requirements-base.txt` não copiado |
| `architect-agent` | ✅ CORRETO | Já segue padrão approval-gateway |
| `approval-gateway` | ✅ CORRETO | Padrão de referência |
| `fluxo-g-dashboard` | ⚠️ Precisa verificar | Possível problema diferente |

---

## Padrão Correto (Working Example)

```dockerfile
# ✓ COPIA requirements-base.txt primeiro
COPY requirements-base.txt ./requirements-base.txt
COPY services/<NOME>/requirements.txt ./requirements-service.txt

# ✓ SUBSTITUI caminho relativo antes do pip install
RUN cat requirements-service.txt | sed 's|-r ../../requirements-base.txt|-r requirements-base.txt|' > requirements.txt && \
    pip install --no-cache-dir -r requirements.txt

# ✓ Copia código fonte
COPY services/<NOME>/src/ ./src/
```

---

## Padrão Quebrado (Todos os 6 serviços)

```dockerfile
# ✗ NÃO copia requirements-base.txt
COPY services/<NOME>/requirements.txt ./

# ✗ Falha com: No such file or directory: '../../requirements-base.txt'
RUN pip install --no-cache-dir -r requirements.txt
```

---

## Correções Necessárias

### 1. data-migration

**Arquivo:** `services/data-migration/Dockerfile`

**ANTES:**
```dockerfile
COPY services/data-migration/requirements.txt services/data-migration/requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt
```

**DEPOIS:**
```dockerfile
COPY requirements-base.txt ./requirements-base.txt
COPY services/data-migration/requirements.txt ./requirements-service.txt
RUN cat requirements-service.txt | sed 's|-r ../../requirements-base.txt|-r requirements-base.txt|' > requirements.txt && \
    pip install --no-cache-dir -r requirements.txt
```

### 2. doc-ingestion

**Arquivo:** `services/doc-ingestion/Dockerfile`

**ANTES:**
```dockerfile
COPY services/doc-ingestion/requirements.txt services/doc-ingestion/requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt
```

**DEPOIS:**
```dockerfile
COPY requirements-base.txt ./requirements-base.txt
COPY services/doc-ingestion/requirements.txt ./requirements-service.txt
RUN cat requirements-service.txt | sed 's|-r ../../requirements-base.txt|-r requirements-base.txt|' > requirements.txt && \
    pip install --no-cache-dir -r requirements.txt
```

### 3. documentation-generation

**Arquivo:** `services/documentation-generation/Dockerfile`

**ANTES:**
```dockerfile
COPY services/documentation-generation/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
```

**DEPOIS:**
```dockerfile
COPY requirements-base.txt ./requirements-base.txt
COPY services/documentation-generation/requirements.txt ./requirements-service.txt
RUN cat requirements-service.txt | sed 's|-r ../../requirements-base.txt|-r requirements-base.txt|' > requirements.txt && \
    pip install --no-cache-dir -r requirements.txt
```

### 4. test-generation

**Arquivo:** `services/test-generation/Dockerfile`

**ANTES:**
```dockerfile
COPY services/test-generation/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```

**DEPOIS:**
```dockerfile
COPY requirements-base.txt ./requirements-base.txt
COPY services/test-generation/requirements.txt ./requirements-service.txt
RUN cat requirements-service.txt | sed 's|-r ../../requirements-base.txt|-r requirements-base.txt|' > requirements.txt && \
    pip install --no-cache-dir -r requirements.txt
```

### 5. requirements-engineering

**Arquivo:** `services/requirements-engineering/Dockerfile`

**ANTES:**
```dockerfile
COPY services/requirements-engineering/requirements.txt services/requirements-engineering/requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r requirements-dev.txt
```

**DEPOIS:**
```dockerfile
COPY requirements-base.txt ./requirements-base.txt
COPY services/requirements-engineering/requirements.txt ./requirements-service.txt
COPY services/requirements-engineering/requirements-dev.txt ./requirements-dev.txt
RUN cat requirements-service.txt | sed 's|-r ../../requirements-base.txt|-r requirements-base.txt|' > requirements.txt && \
    pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r requirements-dev.txt
```

### 6. knowledge-graph-rag

**Arquivo:** `services/knowledge-graph-rag/Dockerfile`

**ANTES:**
```dockerfile
COPY services/knowledge-graph-rag/requirements.txt .
RUN pip install --no-cache-dir torch==2.1.0 --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt
```

**DEPOIS:**
```dockerfile
COPY requirements-base.txt ./requirements-base.txt
COPY services/knowledge-graph-rag/requirements.txt ./requirements-service.txt
RUN cat requirements-service.txt | sed 's|-r ../../requirements-base.txt|-r requirements-base.txt|' > requirements.txt && \
    pip install --no-cache-dir torch==2.1.0 --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt
```

---

## Execução

1. Aplicar correções nos 6 Dockerfiles
2. Commit e push para acionar CI/CD
3. Verificar builds no GitHub Actions
4. Atualizar helm charts para novas tags (ou usar SHA)
5. Deploy no cluster

---

## Verificação

Após correção, o build deve passar sem erro:
```
✓ Successfully built <image-id>
✓ Successfully tagged ghcr.io/albinojimy/neural-hive-mind/<service>:v1.0.1
```
