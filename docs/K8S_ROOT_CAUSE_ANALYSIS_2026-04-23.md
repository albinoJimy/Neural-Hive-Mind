# Análise de Causa Raiz - CrashLoopBackOff K8s Neural Hive Mind

**Data:** 2026-04-23
**Status:** Phase 1 (Root Cause Investigation) - COMPLETO
**Metodologia:** Systematic Debugging

---

## Resumo Executivo

**9 de 16 pods (56%) em CrashLoopBackOff** com 3 tipos distintos de erros que compartilham uma causa raiz comum: **desincronização entre código corrigido e imagens Docker desatualizadas**.

---

## Erro Tipo 1: `ModuleNotFoundError: No module named 'neural_hive_security'`

### Serviços Afetados
- `architect-agent`

### Causa Raiz
**O código importava um módulo que nunca existiu.**

#### Evidências
1. **Código antigo:** `from neural_hive_security.cors import CORSConfig`
2. **Biblioteca existe mas sem módulo `cors`:**
   ```
   /libraries/security/neural_hive_security/
   ├── __init__.py
   ├── config.py
   ├── grpc_channel_factory.py
   ├── jwt/
   ├── security_headers.py
   ├── spiffe_manager.py
   ├── token_cache.py
   ├── vault_client.py
   └── workload_pb2.py
   ```

3. **Correção aplicada:** Commit `640783b4` (2026-04-18 23:08)
   ```diff
   - from neural_hive_security.cors import CORSConfig
   + def _get_cors_origins(environment: str, is_public_api: bool) -> list[str]:
   ```

4. **Imagem rodando:** `ghcr.io/albinojimy/neural-hive-mind/architect-agent:v1.0.0`
   - Construída **ANTES** da correção

### Análise
O módulo `neural_hive_security.cors` **nunca existiu**. Foi uma assunção incorreta durante desenvolvimento que só falhou no runtime do pod.

---

## Erro Tipo 2: `ImportError: cannot import '_QUERY_OPTIONS' from 'pymongo.cursor'`

### Serviços Afetados
- `data-migration`
- `doc-ingestion`
- `documentation-generation`
- `test-generation`
- `requirements-engineering`
- `knowledge-graph-rag`

### Causa Raiz
**Incompatibilidade de versões: pymongo 4.10 removeu `_QUERY_OPTIONS` mas as imagens foram buildadas com versões antigas do motor que ainda importavam do local antigo.**

#### Evidências
1. **requirements-base.txt atual:**
   ```
   motor==3.7.1
   pymongo==4.10.1
   ```

2. **Mudança no pymongo:**
   - pymongo 4.9.x: `_QUERY_OPTIONS` em `pymongo.cursor`
   - pymongo 4.10+: `_QUERY_OPTIONS` movido para `pymongo.cursor_shared`

3. **Motor 3.7.1 já corrigido:**
   ```python
   # motor/core.py linha 30 (versão 3.7.1 e master)
   from pymongo.cursor_shared import _QUERY_OPTIONS  # ✓ CORRETO
   ```

4. **Versão local funciona:**
   ```
   pymongo: 4.9.2
   motor: 3.6.0
   from pymongo.cursor_shared import _QUERY_OPTIONS  # ✓ FUNCIONA
   ```

5. **Imagens v1.0.0 contêm:** versões anteriores a esta correção

### Análise
O código do motor foi corrigido para importar de `pymongo.cursor_shared`, mas as imagens rodando no cluster foram construídas antes dessa atualização do requirements-base.txt.

---

## Erro Tipo 3: `ModuleNotFoundError: No module named 'config'`

### Serviços Afetados
- `fluxo-g-dashboard`

### Causa Raiz
**Possível problema de build com PYTHONPATH ou estrutura de diretórios na imagem v1.0.0.**

#### Evidências
1. **Código local correto:**
   ```python
   # services/fluxo-g-dashboard/src/main.py
   from src.config.settings import get_settings  # ✓
   ```

2. **Estrutura correta:**
   ```
   services/fluxo-g-dashboard/src/
   ├── api/
   ├── config/          # ✓ EXISTE
   │   ├── __init__.py
   │   └── settings.py
   ├── models/
   ├── services/
   └── templates
   ```

3. **Dockerfile define PYTHONPATH:**
   ```dockerfile
   ENV PYTHONPATH=/app
   ```

4. **Última modificação:** 2026-04-22 (ontem)

### Análise
O código-fonte está correto. O erro indica que a imagem v1.0.0 pode ter sido construída com uma versão antiga do código ou com problema de cópia de arquivos.

---

## Causa Raiz Comum

### Problema Sistémico

**O fluxo de deploy está quebrado: correções de código não acionam rebuild automático das imagens Docker.**

#### Fluxo Atual (Quebrado)
```
1. Desenvolvedor faz commit com correção
2. Merge para main
3. [QUEBRA] CI/CD NÃO executa automaticamente
4. Helm chart continua apontando para tag antiga (v1.0.0)
5. Cluster rodando imagem desatualizada
```

#### Evidências do Problema

1. **Último CI/CD bem-sucedido:** 2026-04-22T22:28:10Z (workflow_dispatch)

2. **Push automático FALHOU:** 2026-04-22T22:20:01Z
   ```
   ERROR: Could not open requirements file: [Errno 2]
   No such file or directory: '../../requirements-base.txt'
   ```

3. **Dockerfiles não copiam requirements-base.txt:**
   ```dockerfile
   COPY services/service-registry/requirements.txt .
   # Mas requirements.txt contém: -r ../../requirements-base.txt
   ```

4. **Tags estáticas nos Helm charts:**
   ```yaml
   # helm-charts/architect-agent/values.yaml
   image:
     tag: "1.0.0"  # ← NÃO atualiza automaticamente
   ```

---

## Correções Necessárias (Phase 4: Implementation)

### 1. Corrigir Dockerfiles (IMEDIATO)

**Problema:** Dockerfiles não copiam `requirements-base.txt`

**Solução:** Adicionar cópia do requirements-base antes do pip install

```dockerfile
# ANTES (quebrado)
COPY services/servico/requirements.txt .
RUN pip install -r requirements.txt

# DEPOIS (corrigido)
COPY requirements-base.txt services/servico/requirements.txt ./
RUN pip install -r requirements.txt
```

### 2. Atualizar Tags das Imagens

**Opção A:** Atualizar tags estáticas
- `architect-agent`: v1.0.0 → v1.0.1
- `data-migration`: v1.0.0 → v1.0.1
- etc.

**Opção B:** Usar SHA do Git como tag (recomendado)
- `architect-agent: git-640783b4`
- Atualiza automaticamente a cada commit

### 3. Acionar CI/CD Manualmente

```bash
gh workflow run build-and-push-ghcr.yml \
  -f version_tag=v1.0.1 \
  -f services="architect-agent,data-migration,doc-ingestion,documentation-generation,test-generation,requirements-engineering,knowledge-graph-rag,fluxo-g-dashboard"
```

---

## Serviços Funcionais

| Serviço | Status | Versão | Observações |
|---------|--------|--------|-------------|
| `approval-gateway` | ✅ Running | v1.0.3 | Atualizado e funcional |
| `opa` | ✅ Running | latest | Imagem oficial |

---

## Próximos Passos

1. ✅ **Phase 1 (Root Cause):** COMPLETO
2. ⏳ **Phase 2 (Pattern Analysis):** Verificar working examples (approval-gateway)
3. ⏳ **Phase 3 (Hypothesis):** Testar correção de Dockerfiles
4. ⏳ **Phase 4 (Implementation):** Aplicar fixes e rebuild

---

## Referências

- Commit: `640783b4` - architect-agent fix
- Commit: `1afcfc32` - k8s cluster fixes (22 Abr 2026)
- CI/CD Run: `24805945050` (último sucesso)
- CI/CD Run: `24805651313` (falha por requirements-base.txt)
