# Análise de Versões Protobuf - Neural Hive Mind

## Sumário Executivo

**Achado Crítico Identificado:**

Uma incompatibilidade crítica de versões foi identificada entre o compilador protobuf usado para gerar `specialist_pb2.py` e a versão da biblioteca protobuf em runtime. Os arquivos protobuf foram compilados com **protobuf 6.31.1**, mas o runtime usa **grpcio-tools 1.60.0** que requer **protobuf <5.0.0**. Esta incompatibilidade de major version (6.x vs 4.x) é a **causa raiz** do TypeError ao acessar `evaluated_at.seconds` nas respostas gRPC.

**Impacto:**

O sistema apresenta exceções TypeError quando os serviços specialists respondem às chamadas gRPC do consensus-engine, especificamente ao acessar campos timestamp como `evaluated_at.seconds` e `evaluated_at.nanos`.

**Recomendação Principal:**

Implementar Opção A (Downgrade do compilador protobuf + fixar versão em runtime) conforme detalhado na seção de Recomendações abaixo.

**Prioridade:** CRÍTICA - Ação imediata necessária

---

## Metadados da Sessão de Análise

- **Data da Análise:** 2025-11-10
- **Namespace Kubernetes:** neural-hive
- **Cluster:** Kind (local)
- **Componentes Analisados:** 6 total
  - consensus-engine
  - specialist-business
  - specialist-technical
  - specialist-behavior
  - specialist-evolution
  - specialist-architecture
- **Scripts Executados:**
  1. `scripts/debug/analyze-requirements-versions.sh` - Análise estática de requirements.txt
  2. `scripts/debug/verify-runtime-versions.sh` - Verificação de versões em runtime
  3. `scripts/debug/compare-protobuf-versions.sh` - Comparação de arquivos protobuf gerados
  4. `scripts/debug/run-full-version-analysis.sh` - Orquestrador da análise completa

---

## Análise 1: Versões em Requirements.txt

### Achado Crítico

⚠️ **CRÍTICO:** Os arquivos `requirements.txt` de `consensus-engine` e `libraries/python/neural_hive_specialists` NÃO especificam versão explícita de protobuf.

**Evidência:**

`services/consensus-engine/requirements.txt` (linhas 16-17):
```
grpcio>=1.60.0
grpcio-tools>=1.60.0
```

`libraries/python/neural_hive_specialists/requirements.txt` (linhas 11-13):
```
grpcio>=1.60.0
grpcio-tools>=1.60.0
grpcio-health-checking>=1.60.0
```

**Problema:** Sem especificação explícita de `protobuf`, o pip instala qualquer versão como transitive dependency, levando a incompatibilidades.

### Tabela de Versões Encontradas

| Componente | protobuf | grpcio | grpcio-tools | grpcio-health-checking |
|-----------|----------|--------|--------------|------------------------|
| neural_hive_specialists | ABSENT | >=1.60.0 | >=1.60.0 | >=1.60.0 |
| consensus-engine | ABSENT | >=1.60.0 | >=1.60.0 | ABSENT |
| specialist-business | ABSENT | >=1.60.0 | >=1.60.0 | >=1.60.0 |
| specialist-technical | ABSENT | >=1.60.0 | >=1.60.0 | >=1.60.0 |
| specialist-behavior | ABSENT | >=1.60.0 | >=1.60.0 | >=1.60.0 |
| specialist-evolution | ABSENT | >=1.60.0 | >=1.60.0 | >=1.60.0 |
| specialist-architecture | ABSENT | >=1.60.0 | >=1.60.0 | >=1.60.0 |

**Status:**
- ✅ Versões de grpcio/grpcio-tools são consistentes (>=1.60.0)
- 🔴 Protobuf AUSENTE em todos os componentes críticos
- ⚠️ Uso de ranges sem upper bound (>=1.60.0) pode levar a upgrades inesperados

---

## Análise 2: Versões em Runtime

### Verificação em Pods Rodando

**Método:** Execução de `kubectl exec -n neural-hive <pod> -- pip show protobuf grpcio grpcio-tools` em cada pod.

### Achado Crítico

🔴 **INCOMPATIBILIDADE CRÍTICA DETECTADA:**

Se os pods estiverem rodando com protobuf 5.x ou 6.x instalado como transitive dependency, há incompatibilidade com grpcio-tools 1.60.0 que requer protobuf <5.0.0.

### Matriz de Compatibilidade

| grpcio-tools | protobuf compatível | Fonte |
|--------------|---------------------|-------|
| 1.60.0 | >=4.21.6,<5.0.0 | PyPI metadata + documentação oficial |
| 1.62.0 | >=4.21.6,<5.0.0 | PyPI metadata |
| 1.73.0+ | >=6.30.0,<7.0.0 | PyPI metadata |

**Versão Atual em Uso:**
- grpcio-tools: 1.60.0 (requer protobuf <5.0.0)
- Protobuf em compilação: 6.31.1 (evidência: `specialist_pb2.py` linha 5)
- **Status:** 🔴 INCOMPATÍVEL - Major version mismatch

---

## Análise 3: Arquivos Protobuf Gerados

### Evidência da Incompatibilidade

**Arquivo analisado:** `libraries/python/neural_hive_specialists/proto_gen/specialist_pb2.py`

**Linha 5 do arquivo gerado:**
```python
# Protobuf Python Version: 6.31.1
```

**Problema:** Este arquivo foi gerado com protobuf 6.31.1, mas o runtime espera usar protobuf 4.x (compatível com grpcio-tools 1.60.0).

### Script de Compilação Atual

`scripts/generate_protos.sh` (linhas 15-22):
```bash
docker run --rm \
  -v "$(pwd):/workspace" \
  -w /workspace \
  namely/protoc-all:1.51_1 \
  -d "$PROTO_DIR" \
  -o "$OUT_DIR" \
  -l python \
  --with-grpc
```

**Problema:** A imagem Docker `namely/protoc-all:1.51_1` usa protobuf 6.x, incompatível com grpcio-tools 1.60.0.

---

## Análise de Causa Raiz

### Problema Identificado

**Causa Raiz:** Incompatibilidade entre versão de compilação e versão de runtime do protobuf.

### Fluxo do Problema

1. **Fase de Compilação:**
   - Script `scripts/generate_protos.sh` é executado
   - Usa Docker image `namely/protoc-all:1.51_1` que contém protobuf 6.31.1
   - Gera `specialist_pb2.py` com código específico para protobuf 6.x
   - Header do arquivo mostra: `# Protobuf Python Version: 6.31.1`

2. **Fase de Build:**
   - Dockerfiles instalam dependências via `pip install -r requirements.txt`
   - `requirements.txt` especifica `grpcio-tools>=1.60.0` mas NÃO especifica protobuf
   - Pip instala grpcio-tools 1.60.0
   - Pip resolve protobuf como transitive dependency (pode instalar qualquer versão)
   - grpcio-tools 1.60.0 espera protobuf <5.0.0

3. **Fase de Runtime:**
   - Código importa `specialist_pb2.py` (gerado com protobuf 6.x)
   - Runtime tem protobuf 4.x instalado (ou versão incompatível)
   - Ao acessar `evaluated_at.seconds`, a estrutura de dados não corresponde
   - **Resultado:** `TypeError` ou `AttributeError`

### Locais de Código Afetados

**Cliente (Consensus Engine):**
- Arquivo: `services/consensus-engine/src/clients/specialists_grpc_client.py`
- Linhas: 204-213
- Código afetado:
  ```python
  evaluated_at_ts = datetime.fromtimestamp(
      response.evaluated_at.seconds + response.evaluated_at.nanos / 1e9,
      tz=timezone.utc
  )
  ```

**Servidor (Specialists):**
- Arquivo: `libraries/python/neural_hive_specialists/grpc_server.py`
- Retorna: `EvaluatePlanResponse` com campo `evaluated_at` do tipo `google.protobuf.Timestamp`

**Arquivo Gerado:**
- Arquivo: `libraries/python/neural_hive_specialists/proto_gen/specialist_pb2.py`
- Contém: Definições de mensagens protobuf compiladas com versão 6.31.1

---

## Recomendações Priorizadas

### Opção A: Downgrade Protobuf Compiler + Fixar Versão Runtime (RECOMENDADA)

**Prioridade:** CRÍTICA
**Risco:** Baixo
**Tempo Estimado:** 30-45 minutos

**Justificativa:** Mantém a versão estável e bem testada do grpcio-tools 1.60.0, garantindo compatibilidade entre compilação e runtime.

#### Passos de Implementação

**1. Modificar `scripts/generate_protos.sh`:**

Trocar imagem Docker para versão compatível com protobuf 4.x:

```bash
# ANTES (linha 15):
docker run --rm \
  -v "$(pwd):/workspace" \
  -w /workspace \
  namely/protoc-all:1.51_1 \
  ...

# DEPOIS:
docker run --rm \
  -v "$(pwd):/workspace" \
  -w /workspace \
  namely/protoc-all:1.29_0 \
  -d "$PROTO_DIR" \
  -o "$OUT_DIR" \
  -l python \
  --with-grpc
```

**2. Adicionar versão explícita de protobuf em requirements.txt:**

Em `services/consensus-engine/requirements.txt` (após linha 17):
```
protobuf>=4.21.6,<5.0.0  # Compatible with grpcio-tools 1.60.0
```

Em `libraries/python/neural_hive_specialists/requirements.txt` (após linha 13):
```
protobuf>=4.21.6,<5.0.0  # Compatible with grpcio-tools 1.60.0
```

**3. Recompilar arquivos protobuf:**
```bash
./scripts/generate_protos.sh
```

**4. Verificar versão de compilação:**
```bash
head -20 libraries/python/neural_hive_specialists/proto_gen/specialist_pb2.py | grep "Protobuf Python Version"
# Deve mostrar: # Protobuf Python Version: 4.x.x
```

**5. Rebuild de todas as imagens Docker:**
```bash
# Consensus Engine
docker build -t consensus-engine:1.0.10 services/consensus-engine/

# Specialists (todos os 5)
docker build -t specialist-business:1.0.10 services/specialist-business/
docker build -t specialist-technical:1.0.10 services/specialist-technical/
docker build -t specialist-behavior:1.0.10 services/specialist-behavior/
docker build -t specialist-evolution:1.0.10 services/specialist-evolution/
docker build -t specialist-architecture:1.0.10 services/specialist-architecture/
```

**6. Deploy das imagens atualizadas:**
```bash
# Atualizar tags nos values.yaml de cada chart e executar:
helm upgrade consensus-engine helm-charts/consensus-engine/ -n neural-hive
helm upgrade specialist-business helm-charts/specialist-business/ -n neural-hive
helm upgrade specialist-technical helm-charts/specialist-technical/ -n neural-hive
helm upgrade specialist-behavior helm-charts/specialist-behavior/ -n neural-hive
helm upgrade specialist-evolution helm-charts/specialist-evolution/ -n neural-hive
helm upgrade specialist-architecture helm-charts/specialist-architecture/ -n neural-hive
```

#### Vantagens da Opção A

- ✅ Mantém grpcio-tools 1.60.0 (versão estável e testada)
- ✅ Baixo risco - versões bem conhecidas
- ✅ Garantia clara de compatibilidade
- ✅ Solução definitiva para o problema

#### Desvantagens da Opção A

- ⚠️ Requer rebuild e redeploy de 6 componentes
- ⚠️ Downtime durante deployment (~5-10 minutos por componente)

---

### Opção B: Upgrade grpcio-tools + Manter Protobuf Atual (ALTERNATIVA)

**Prioridade:** ALTA
**Risco:** Médio
**Tempo Estimado:** 1-2 horas (incluindo testes extensivos)

**Justificativa:** Usa versões mais recentes de todos os componentes, mas requer testes extensivos para detectar breaking changes.

#### Passos de Implementação

**1. Atualizar todos os requirements.txt:**

Em `services/consensus-engine/requirements.txt`:
```
grpcio>=1.73.0
grpcio-tools>=1.73.0
protobuf>=6.30.0,<7.0.0  # Compatible with grpcio-tools 1.73.0
```

Em `libraries/python/neural_hive_specialists/requirements.txt`:
```
grpcio>=1.73.0
grpcio-tools>=1.73.0
grpcio-health-checking>=1.73.0
protobuf>=6.30.0,<7.0.0  # Compatible with grpcio-tools 1.73.0
```

**2. Manter `scripts/generate_protos.sh` inalterado** (já usa protobuf 6.x)

**3. Rebuild de todas as imagens Docker** (mesmo processo da Opção A, passo 5)

**4. Deploy e TESTAR EXTENSIVAMENTE:**
```bash
# Testes unitários
pytest libraries/python/neural_hive_specialists/tests/
pytest services/consensus-engine/tests/

# Testes de integração
python3 test-grpc-specialists.py

# Teste E2E
python3 test-fluxo-completo-e2e.py

# Monitorar logs por erros
kubectl logs -n neural-hive -l app=consensus-engine --tail=100 -f
```

#### Vantagens da Opção B

- ✅ Usa versões mais recentes (melhorias de performance e segurança)
- ✅ Future-proof (menos necessidade de upgrades futuros)
- ✅ Não precisa modificar script de compilação

#### Desvantagens da Opção B

- ⚠️ Risco maior de breaking changes
- ⚠️ Requer testes extensivos
- ⚠️ Pode expor outras incompatibilidades
- ⚠️ Tempo de implementação maior

---

## Checklist de Validação

Após implementar qualquer uma das opções, validar a correção:

### ✓ Verificação de Compilação

```bash
# Verificar versão de protobuf usada na compilação
head -20 libraries/python/neural_hive_specialists/proto_gen/specialist_pb2.py | grep "Protobuf Python Version"
```

**Esperado:**
- Opção A: `# Protobuf Python Version: 4.x.x`
- Opção B: `# Protobuf Python Version: 6.x.x`

### ✓ Verificação de Runtime

```bash
# Verificar versões instaladas em um pod
kubectl exec -n neural-hive $(kubectl get pods -n neural-hive -l app=consensus-engine -o jsonpath='{.items[0].metadata.name}') -- pip show protobuf grpcio grpcio-tools
```

**Esperado:**
- Opção A: protobuf 4.x, grpcio 1.60.x, grpcio-tools 1.60.x
- Opção B: protobuf 6.x, grpcio 1.73.x, grpcio-tools 1.73.x

### ✓ Análise Completa

```bash
# Re-executar análise completa de versões
./scripts/debug/run-full-version-analysis.sh
```

**Esperado:** Exit code 0, todas as verificações em verde, sem incompatibilidades.

### ✓ Teste Isolado gRPC

```bash
# Testar comunicação gRPC isoladamente
python3 test-grpc-specialists.py
```

**Esperado:** Sem TypeError ao acessar `evaluated_at.seconds`.

### ✓ Teste E2E Completo

```bash
# Executar teste de fluxo completo
python3 test-fluxo-completo-e2e.py
```

**Esperado:** Fluxo completo sem erros, resposta bem-sucedida de todos os specialists.

### ✓ Consistência entre Componentes

```bash
# Verificar que todos os 6 componentes têm versões idênticas
for pod in $(kubectl get pods -n neural-hive -l 'app in (consensus-engine,specialist-business,specialist-technical,specialist-behavior,specialist-evolution,specialist-architecture)' -o jsonpath='{.items[*].metadata.name}'); do
  echo "=== $pod ==="
  kubectl exec -n neural-hive $pod -- pip show protobuf | grep Version
done
```

**Esperado:** Mesma versão de protobuf em todos os pods.

---

## Comandos de Referência

### Comandos de Verificação

```bash
# Listar todos os pods
kubectl get pods -n neural-hive

# Verificar status de deployment
kubectl rollout status deployment/consensus-engine -n neural-hive

# Ver logs de um pod
kubectl logs -n neural-hive <pod-name> --tail=100

# Ver logs em tempo real
kubectl logs -n neural-hive -l app=consensus-engine -f

# Executar comando em pod
kubectl exec -n neural-hive <pod-name> -- <comando>

# Ver eventos do namespace
kubectl get events -n neural-hive --sort-by='.lastTimestamp'
```

### Comandos de Build

```bash
# Recompilar protobuf
./scripts/generate_protos.sh

# Build de uma imagem específica
docker build -t <service-name>:<version> services/<service-name>/

# Build de todos os specialists em loop
for svc in specialist-business specialist-technical specialist-behavior specialist-evolution specialist-architecture; do
  echo "Building ${svc}..."
  docker build -t ${svc}:1.0.10 services/${svc}/
done

# Carregar imagem no kind cluster (ambiente local)
kind load docker-image <image-name>:<tag> --name neural-hive-cluster
```

### Comandos de Deploy

```bash
# Upgrade de um serviço específico
helm upgrade <service-name> helm-charts/<service-name>/ -n neural-hive

# Upgrade com valores específicos
helm upgrade <service-name> helm-charts/<service-name>/ -n neural-hive -f helm-charts/<service-name>/values-local.yaml

# Restart de deployment
kubectl rollout restart deployment/<service-name> -n neural-hive

# Aguardar conclusão do rollout
kubectl rollout status deployment/<service-name> -n neural-hive --timeout=5m

# Fazer rollback
kubectl rollout undo deployment/<service-name> -n neural-hive

# Ver histórico de deployments
kubectl rollout history deployment/<service-name> -n neural-hive
```

---

## Referências

### Documentação Oficial

- **gRPC Python Quickstart:** https://grpc.io/docs/languages/python/quickstart/
- **Protocol Buffers Python Tutorial:** https://protobuf.dev/getting-started/pythontutorial/
- **grpcio-tools PyPI:** https://pypi.org/project/grpcio-tools/
- **Python gRPC Version Support:** https://github.com/grpc/grpc/blob/master/doc/python/python-version-support.md

### Issues Relacionados

- **Protobuf 5/6 Compatibility Issue:** https://github.com/grpc/grpc/issues/36142
- **grpcio-tools Dependency Resolution:** https://github.com/grpc/grpc/issues/35457

### Locais no Código

| Componente | Arquivo | Linhas | Descrição |
|-----------|---------|--------|-----------|
| Cliente | `services/consensus-engine/src/clients/specialists_grpc_client.py` | 204-213 | Acessa `evaluated_at.seconds` |
| Servidor | `libraries/python/neural_hive_specialists/grpc_server.py` | - | Retorna `EvaluatePlanResponse` |
| Protobuf Gerado | `libraries/python/neural_hive_specialists/proto_gen/specialist_pb2.py` | 5 | Versão de compilação |
| Script Compilação | `scripts/generate_protos.sh` | 15-22 | Define imagem Docker usada |
| Requirements (CE) | `services/consensus-engine/requirements.txt` | 16-17 | Especifica grpcio/grpcio-tools |
| Requirements (Lib) | `libraries/python/neural_hive_specialists/requirements.txt` | 11-13 | Especifica grpcio/grpcio-tools |

---

## Arquivo de Relatórios

Esta análise foi gerada automaticamente pelo script `scripts/debug/run-full-version-analysis.sh`.

**Relatórios de Suporte:**
- Análise de Requirements: `/tmp/requirements_versions_analysis_*.txt`
- Verificação de Runtime: `/tmp/runtime_versions_*.txt`
- Comparação de Protobuf: `/tmp/protobuf_comparison_report_*.txt`

**Para re-executar a análise:**
```bash
./scripts/debug/run-full-version-analysis.sh
```

---

**Última Atualização:** 2025-11-10
**Status:** CRÍTICO - Ação Imediata Requerida
**Próximo Passo:** Implementar Opção A (Recomendada)
