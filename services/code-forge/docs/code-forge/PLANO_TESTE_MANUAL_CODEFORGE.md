# Plano de Teste Manual - CodeForge Builds Reais

**Versão:** 1.5.0
**Data:** 2026-03-12
**Status:** Pronto para Execução

---

## 1. Visão Geral

Este plano de teste manual valida todas as funcionalidades do CodeForge Builds Reais, incluindo os 4 itens opcionais implementados.

### Objetivo

Validar manualmente que o CodeForge Builds Reais está funcionando corretamente em um ambiente real, cobrindo todos os fluxos de build para diferentes linguagens, builders e plataformas.

### Escopo

- ✅ DockerfileGenerator (6 linguagens)
- ✅ ContainerBuilder (Docker CLI + Kaniko)
- ✅ Multi-arch builds (6 plataformas)
- ✅ BuildKit Cache
- ✅ Kaniko Real Builds (cluster Kubernetes)
- ✅ QEMU Multi-arch (emulação)
- ✅ Performance Metrics

### Critérios de Sucesso

- [ ] Todos os testes básicos passam
- [ ] Pelo menos 1 build bem-sucedido por linguagem
- [ ] Multi-arch build funciona para amd64 + arm64
- [ ] Kaniko build funciona no cluster Kubernetes
- [ ] Métricas são coletadas e persistidas

---

## 2. Pré-requisitos

### 2.1 Ambiente de Teste

| Componente | Versão Mínima | Como Verificar |
|------------|---------------|----------------|
| Python | 3.10+ | `python3 --version` |
| Docker | 24.0+ | `docker --version` |
| kubectl | 1.28+ | `kubectl version --client` |
| Cluster K8s | 1.24+ | `kubectl cluster-info` |

### 2.2 Configuração do Cluster

```bash
# Verificar conexão com cluster
kubectl cluster-info

# Verificar namespace docker-build
kubectl get namespace docker-build

# Criar se não existir
kubectl create namespace docker-build
```

### 2.3 Variáveis de Ambiente

```bash
# Opcional: Registry para imagens
export REGISTRY_URL=localhost:5000
export REGISTRY_USERNAME=user
export REGISTRY_PASSWORD=pass

# Opcional: Kubernetes config
export KUBECONFIG=/path/to/kubeconfig
```

### 2.4 Preparação do Diretório de Teste

```bash
mkdir -p /tmp/codeforge-test
cd /tmp/codeforge-test
```

---

## 3. Casos de Teste

### 3.1 TC-001: DockerfileGenerator - Python Microservice

**Objetivo:** Validar geração de Dockerfile para Python FastAPI

**Pré-condições:**
- Python 3.10+ instalado
- Código fonte disponível

**Passos:**

1. Criar projeto de teste:
```bash
mkdir -p /tmp/codeforge-test/python-fastapi
cd /tmp/codeforge-test/python-fastapi

cat > main.py << 'EOF'
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello World"}

@app.get("/health")
def health():
    return {"status": "healthy"}
EOF
```

2. Criar requirements.txt:
```bash
cat > requirements.txt << 'EOF'
fastapi==0.104.1
uvicorn==0.24.0
EOF
```

3. Executar teste Python:
```python
from src.services.dockerfile_generator import DockerfileGenerator
from src.services.dockerfile_generator import ArtifactType, PythonVersion

generator = DockerfileGenerator()

# Gerar Dockerfile
dockerfile_content = generator.generate_python_dockerfile(
    python_version=PythonVersion.PYTHON_3_11_SLIM,
    artifact_type=ArtifactType.MICROSERVICE,
    framework="fastapi",
    port=8000,
    healthcheck_path="/health"
)

# Salvar e verificar
with open("Dockerfile", "w") as f:
    f.write(dockerfile_content)

print("✅ Dockerfile gerado com sucesso!")
print(dockerfile_content[:200])  # Primeiras 200 linhas
```

**Resultado Esperado:**
- [ ] Dockerfile criado com sucesso
- [ ] Contém FROM python:3.11-slim
- [ ] Contém HEALTHCHECK
- [ ] Contém EXPOSE 8000
- [ ] Contém CMD para uvicorn

---

### 3.2 TC-002: DockerfileGenerator - Node.js Express

**Objetivo:** Validar geração de Dockerfile para Node.js

**Passos:**

1. Criar projeto:
```bash
mkdir -p /tmp/codeforge-test/nodejs-express
cd /tmp/codeforge-test/nodejs-express

cat > package.json << 'EOF'
{
  "name": "test-express",
  "version": "1.0.0",
  "main": "index.js",
  "dependencies": {
    "express": "^4.18.2"
  }
}
EOF

cat > index.js << 'EOF'
const express = require('express');
const app = express();
app.get('/', (req, res) => res.json({message: 'Hello World'}));
app.get('/health', (req, res) => res.json({status: 'healthy'}));
app.listen(3000);
EOF
```

2. Gerar Dockerfile:
```python
from src.services.dockerfile_generator import DockerfileGenerator, NodeVersion, ArtifactType

generator = DockerfileGenerator()
dockerfile = generator.generate_nodejs_dockerfile(
    node_version=NodeVersion.NODE_20_ALPINE,
    artifact_type=ArtifactType.MICROSERVICE,
    framework="express",
    port=3000
)

with open("Dockerfile", "w") as f:
    f.write(dockerfile)
```

**Resultado Esperado:**
- [ ] Dockerfile criado
- [ ] FROM node:20-alpine
- [ ] Multi-stage build presente
- [ ] EXPOSE 3000

---

### 3.3 TC-003: DockerfileGenerator - Outras Linguagens

**Objetivo:** Validar geração para Go, Java, C#, TypeScript

| Linguagem | Framework | Porta | Arquivo Teste |
|-----------|-----------|-------|---------------|
| Go | Gin | 8080 | main.go |
| Java | Spring Boot | 8080 | Application.java |
| C# | ASP.NET | 5000 | Program.cs |
| TypeScript | NestJS | 3000 | main.ts |

**Resultado Esperado:**
- [ ] Todos os Dockerfiles gerados sem erros
- [ ] Cada Dockerfile usa a imagem base correta
- [ ] Healthcheck presente quando aplicável

---

### 3.4 TC-004: ContainerBuilder - Docker CLI (Build Local)

**Objetivo:** Validar build com Docker CLI

**Passos:**

1. Criar contexto de build:
```bash
cd /tmp/codeforge-test/python-fastapi
```

2. Executar build:
```python
import asyncio
from src.services.container_builder import ContainerBuilder, BuilderType

async def test_docker_build():
    builder = ContainerBuilder(
        builder_type=BuilderType.DOCKER,
        enable_metrics=True
    )

    result = await builder.build_container(
        dockerfile_path="Dockerfile",
        build_context=".",
        image_tag="test-python:latest",
        platforms=["linux/amd64"]
    )

    print(f"Success: {result.success}")
    print(f"Image: {result.image_tag}")
    print(f"Digest: {result.image_digest}")
    print(f"Size: {result.size_bytes} bytes")
    print(f"Duration: {result.duration_seconds}s")

    return result

result = asyncio.run(test_docker_build())
```

**Resultado Esperado:**
- [ ] Build completa com sucesso
- [ ] result.success == True
- [ ] image_digest não é None (SHA256)
- [ ] size_bytes > 0
- [ ] duration_seconds registrado
- [ ] Imagem visível em `docker images`

---

### 3.5 TC-005: ContainerBuilder - BuildKit Cache

**Objetivo:** Validar cache do BuildKit

**Passos:**

```python
from src.services.container_builder import ContainerBuilder

async def test_cache():
    builder = ContainerBuilder(
        enable_cache=True,
        cache_repo="localhost:5000/test-cache"
    )

    # Primeiro build (sem cache)
    result1 = await builder.build_container(
        dockerfile_path="Dockerfile",
        build_context=".",
        image_tag="test-cache:1"
    )

    # Build incremental (com cache)
    result2 = await builder.build_container(
        dockerfile_path="Dockerfile",
        build_context=".",
        image_tag="test-cache:2"
    )

    # Segundo build deve ser mais rápido
    print(f"Build 1: {result1.duration_seconds}s")
    print(f"Build 2: {result2.duration_seconds}s")
    print(f"Speedup: {result1.duration_seconds / result2.duration_seconds:.2f}x")

asyncio.run(test_cache())
```

**Resultado Esperado:**
- [ ] Ambos builds completam com sucesso
- [ ] Segundo build é mais rápido (cache hit)
- [ ] Logs mostram "CACHED" para layers

---

### 3.6 TC-006: Multi-arch Build - Docker Local

**Objetivo:** Validar build multi-arch local

**Passos:**

```python
from src.services.container_builder import ContainerBuilder, Platform

async def test_multiarch():
    builder = ContainerBuilder()

    result = await builder.build_container(
        dockerfile_path="Dockerfile",
        build_context=".",
        image_tag="test-multiarch:latest",
        platforms=[
            Platform.LINUX_AMD64,
            Platform.LINUX_ARM64
        ]
    )

    print(f"Success: {result.success}")
    print(f"Platforms: {result.platforms}")

asyncio.run(test_multiarch())
```

**Resultado Esperado:**
- [ ] Build completa para ambas plataformas
- [ ] result.platforms contém ["linux/amd64", "linux/arm64"]
- [ ] `docker buildx imagetools inspect` mostra ambas arquiteturas

---

### 3.7 TC-007: Kaniko Builder - Kubernetes Cluster

**Objetivo:** Validar build com Kaniko no cluster

**Pré-condições:**
- Cluster Kubernetes acessível
- Namespace docker-build existe

**Passos:**

```python
import asyncio
from src.services.container_builder import ContainerBuilder, BuilderType

async def test_kaniko_build():
    builder = ContainerBuilder(
        builder_type=BuilderType.KANIKO,
        kubernetes_namespace="docker-build",
        enable_metrics=True
    )

    result = await builder.build_container(
        dockerfile_path="Dockerfile",
        build_context="/tmp/codeforge-test/python-fastapi",
        image_tag="localhost:5000/test-kaniko:latest",
        no_push=True,  # Para teste local
        platforms=["linux/amd64"]
    )

    print(f"Success: {result.success}")
    print(f"Image: {result.image_tag}")
    print(f"Digest: {result.image_digest}")
    print(f"Logs ({len(result.build_logs)} linhas):")

    # Últimas 10 linhas do log
    for log in result.build_logs[-10:]:
        print(f"  {log}")

    return result

result = asyncio.run(test_kaniko_build())
```

**Resultado Esperado:**
- [ ] Pod Kaniko criado no cluster
- [ ] Build completa com sucesso
- [ ] Pod é deletado após build
- [ ] result.image_digest contém SHA256

**Verificação no Kubernetes:**
```bash
# Verificar se pod foi criado e depois deletado
kubectl get pods -n docker-build

# Deve mostrar vazio ou pods recentes
```

---

### 3.8 TC-008: Kaniko - QEMU Multi-arch

**Objetivo:** Validar build multi-arch com QEMU no cluster

**Passos:**

```python
from src.services.container_builder import ContainerBuilder, BuilderType

async def test_kaniko_qemu():
    builder = ContainerBuilder(
        builder_type=BuilderType.KANIKO,
        kubernetes_namespace="docker-build"
    )

    result = await builder.build_container(
        dockerfile_path="Dockerfile",
        build_context="/tmp/codeforge-test/python-fastapi",
        image_tag="localhost:5000/test-qemu:latest",
        platforms=["linux/amd64", "linux/arm64"],
        no_push=True
    )

    print(f"Success: {result.success}")
    print(f"Platforms: {result.platforms}")
    print(f"Duration: {result.duration_seconds}s")

asyncio.run(test_kaniko_qemu())
```

**Resultado Esperado:**
- [ ] Init container qemu-setup é criado
- [ ] Binários QEMU copiados para volume
- [ ] Build completa para ambas plataformas
- [ ] result.platforms == ["linux/amd64", "linux/arm64"]

**Verificação:**
```bash
# Descrever pod durante build
kubectl describe pod -n docker-build -l job-name=kaniko-

# Deve mostrar:
# - init container qemu-setup
# - volume qemu
# - volumeMounts para /usr/local/bin
```

---

### 3.9 TC-009: Performance Metrics - Coleta

**Objetivo:** Validar coleta de métricas

**Passos:**

```python
from src.services.build_metrics import get_metrics_collector, MetricType

# Executar alguns builds com métricas habilitadas
# ... (usar TC-004 ou TC-007)

# Consultar coletor
collector = get_metrics_collector()

# Relatório completo
report = collector.get_performance_report()

print("=== RELATÓRIO DE PERFORMANCE ===")
print(f"Total de builds: {report['summary']['total_builds']}")
print(f"Taxa de sucesso: {report['summary']['success_rate']:.1%}")
print(f"\nDuração por linguagem:")
for lang, stats in report['duration_by_language'].items():
    print(f"  {lang}: média {stats['mean']:.2f}s")

print(f"\nCache hit rate por linguagem:")
for lang, rate in report['cache_hit_rate_by_language'].items():
    print(f"  {lang}: {rate:.1f}%")

print(f"\nImpacto multi-arch:")
ma = report['multi_arch_impact']
print(f"  Single-arch: {ma['single_arch_avg_duration']:.2f}s")
print(f"  Multi-arch: {ma['multi_arch_avg_duration']:.2f}s")
print(f"  Overhead: {ma['multi_arch_overhead_percent']:.1f}%")
```

**Resultado Esperado:**
- [ ] Métricas persistidas em `metrics/build_metrics.jsonl`
- [ ] Relatório mostra estatísticas corretas
- [ ] Builds agrupados por linguagem

---

### 3.10 TC-010: Performance Metrics - Exportação

**Objetivo:** Validar exportação de métricas

**Passos:**

```python
from src.services.build_metrics import get_metrics_collector

collector = get_metrics_collector()

# Exportar para JSON
collector.export_metrics("/tmp/metrics.json", format="json")

# Exportar para CSV
collector.export_metrics("/tmp/metrics.csv", format="csv")

# Builds mais lentos
slowest = collector.get_slowest_builds(n=5)
print("=== 5 BUILDS MAIS LENTOS ===")
for i, build in enumerate(slowest, 1):
    print(f"{i}. {build['language']} - {build['duration_seconds']:.1f}s")

# Resumo de erros
errors = collector.get_error_summary()
print(f"\nTotal de erros: {errors['total_errors']}")
print(f"Tipos de erro: {errors['error_types']}")
```

**Resultado Esperado:**
- [ ] Arquivo JSON criado com todas métricas
- [ ] Arquivo CSV criado
- [ ] Lista de builds lentos ordenada corretamente
- [ ] Resumo de erros mostra tipos e contagens

---

### 3.11 TC-011: Integracao - Pipeline Completo

**Objetivo:** Validar fluxo completo do PipelineEngine

**Passos:**

```python
import asyncio
from src.services.pipeline_engine import PipelineEngine
from src.models.pipeline_context import PipelineContext

async def test_full_pipeline():
    engine = PipelineEngine()

    context = PipelineContext(
        project_name="test-project",
        repository_url="https://github.com/test/repo.git",
        branch="main",
        commit_sha="abc123",
        source_path="/tmp/codeforge-test/python-fastapi"
    )

    result = await engine.execute_pipeline(context)

    print(f"Success: {result.success}")
    print(f"Artifacts: {len(result.artifacts)}")
    print(f"SBOMs: {len(result.sboms)}")
    print(f"Security scans: {len(result.security_scans)}")

    for artifact in result.artifacts:
        print(f"  - {artifact.image_tag}: {artifact.image_digest}")

asyncio.run(test_full_pipeline())
```

**Resultado Esperado:**
- [ ] Pipeline executa completamente
- [ ] Artefatos criados
- [ ] SBOMs gerados
- [ ] Scans de segurança executados
- [ ] Métricas coletadas

---

## 4. Relatório de Testes

### Template de Resultados

| TC ID | Descrição | Status | Observações |
|-------|-----------|--------|------------|
| TC-001 | Python FastAPI | [ ] PASS / FAIL | |
| TC-002 | Node.js Express | [ ] PASS / FAIL | |
| TC-003 | Outras Linguagens | [ ] PASS / FAIL | |
| TC-004 | Docker CLI Build | [ ] PASS / FAIL | |
| TC-005 | BuildKit Cache | [ ] PASS / FAIL | |
| TC-006 | Multi-arch Local | [ ] PASS / FAIL | |
| TC-007 | Kaniko K8s Build | [ ] PASS / FAIL | |
| TC-008 | Kaniko QEMU | [ ] PASS / FAIL | |
| TC-009 | Metrics Coleta | [ ] PASS / FAIL | |
| TC-010 | Metrics Export | [ ] PASS / FAIL | |
| TC-011 | Pipeline Completo | [ ] PASS / FAIL | |

### Resumo Executivo

```
Data: ____/____/______
Tester: ___________________
Ambiente: [ ] Local [ ] Cluster K8s [ ] Ambos

Total de Testes: ___/11
Passou: ___
Falhou: ___
Não executado: ___

Builds por Linguagem:
- Python: [ ] PASS [ ] FAIL
- Node.js: [ ] PASS [ ] FAIL
- Go: [ ] PASS [ ] FAIL
- Java: [ ] PASS [ ] FAIL
- C#: [ ] PASS [ ] FAIL
- TypeScript: [ ] PASS [ ] FAIL

Builders:
- Docker CLI: [ ] PASS [ ] FAIL
- Kaniko: [ ] PASS [ ] FAIL

Multi-arch:
- AMD64: [ ] PASS [ ] FAIL
- ARM64: [ ] PASS [ ] FAIL
- Outros: [ ] PASS [ ] FAIL

Métricas:
- Coleta: [ ] PASS [ ] FAIL
- Exportação: [ ] PASS [ ] FAIL

Observações Gerais:
_____________________________________________________________
_____________________________________________________________
_____________________________________________________________
```

---

## 5. Troubleshooting

### 5.1 Problemas Comuns

| Problema | Solução |
|----------|---------|
| `docker: command not found` | Instalar Docker Desktop ou Docker Engine |
| `kubectl: command not found` | Instalar kubectl |
| `Cannot connect to cluster` | Verificar KUBECONFIG |
| `permission denied` | Usar sudo ou adicionar usuário ao grupo docker |
| `image not found` | Build não foi executado ou falhou |
| `pod not found` | Verificar namespace docker-build |

### 5.2 Logs Úteis

```bash
# Logs do Pod Kaniko
kubectl logs -n docker-build -l job-name=kaniko- --tail=100

# Descrever pod
kubectl describe pod -n docker-build

# Eventos do namespace
kubectl get events -n docker-build --sort-by='.lastTimestamp'

# Métricas persistidas
cat metrics/build_metrics.jsonl
```

---

## 6. Checklist Final

Antes de considerar os testes completos:

- [ ] Todos os TCs básicos (001-006) executados
- [ ] Pelo menos 1 build Kaniko executado (TC-007)
- [ ] Métricas verificadas (TC-009, TC-010)
- [ ] Relatório de testes preenchido
- [ ] Logs salvos para casos de falha
- [ ] Imagens de teste limpas (`docker rmi ...`)
- [ ] Pods de teste removidos do cluster

---

**Assinatura do Tester:** _________________ **Data:** ____/____/______
