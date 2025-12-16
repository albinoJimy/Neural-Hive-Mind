# Práticas Recomendadas para Builds Docker - Neural Hive-Mind

## 1. Introdução

Este guia documenta as práticas recomendadas para builds Docker no projeto Neural Hive-Mind. Seguir estas práticas garante:

- **Builds mais rápidos**: Melhor uso de cache e paralelização
- **Imagens menores**: Redução do tamanho final das imagens
- **Cache otimizado**: Estratégias que maximizam o reuso de camadas
- **Consistência**: Padrões uniformes em todos os serviços

## 2. Arquivos .dockerignore

### Importância

Arquivos `.dockerignore` são essenciais para reduzir o tamanho do contexto de build Docker. Um contexto menor significa:
- Menos dados transferidos para o Docker daemon
- Builds mais rápidos
- Menor consumo de memória durante o build

### Template Padrão

Todos os serviços e imagens base no projeto utilizam o mesmo template `.dockerignore` (baseado em `/jimy/Neural-Hive-Mind/services/semantic-translation-engine/.dockerignore`):

```
# Python cache
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
*.so

# Virtual environments
venv/
env/
ENV/
.venv

# IDE and editors
.git/
.gitignore
.vscode/
.idea/
*.swp
*.swo
*~

# Documentation
*.md
docs/

# Tests
tests/
.pytest_cache/
.coverage
htmlcov/
.tox/

# Build artifacts
dist/
build/
*.egg-info/
*.egg

# Environment files
.env
.env.local
.env.*.local

# Docker
docker-compose*.yml
Dockerfile.*

# CI/CD
.github/
.gitlab-ci.yml

# OS files
.DS_Store
Thumbs.db
```

### O Que Excluir

- **Cache Python**: `__pycache__/`, `*.pyc`, `*.pyo`, `*.pyd`, `.Python`, `*.so`
- **Ambientes virtuais**: `venv/`, `env/`, `ENV/`, `.venv`
- **Arquivos de IDE**: `.git/`, `.gitignore`, `.vscode/`, `.idea/`, `*.swp`, `*.swo`, `*~`
- **Documentação**: `*.md`, `docs/`
- **Testes**: `tests/`, `.pytest_cache/`, `.coverage`, `htmlcov/`, `.tox/`
- **Artefatos de build**: `dist/`, `build/`, `*.egg-info/`, `*.egg`
- **Arquivos de ambiente**: `.env`, `.env.local`, `.env.*.local`
- **Arquivos Docker**: `docker-compose*.yml`, `Dockerfile.*`
- **CI/CD**: `.github/`, `.gitlab-ci.yml`
- **Arquivos do sistema operacional**: `.DS_Store`, `Thumbs.db`

### Verificação

Para verificar o tamanho do contexto de build:

```bash
docker build --no-cache .
```

A primeira linha mostrará o tamanho do contexto: `Sending build context to Docker daemon  X.XXkB`

## 3. Otimização de Dockerfile

### 3.1 Builds Multi-Estágio

Use um estágio para construção/instalação e outro para execução:

**Exemplo** (baseado em `/jimy/Neural-Hive-Mind/services/specialist-business/Dockerfile`):

```dockerfile
# Estágio 1 - Builder
FROM neural-hive-mind/python-grpc-base:1.0.0 AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Estágio 2 - Runtime
FROM neural-hive-mind/python-grpc-base:1.0.0

WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY src/ ./src/
```

**Benefícios**:
- Imagens finais menores (sem dependências de build)
- Separação clara entre dependências de build e runtime
- Melhor segurança (ferramentas de build não ficam na imagem final)

### 3.2 Estratégia de Cache de Camadas

**Ordem importa**: COPY requirements.txt antes de COPY src/

**Racional**: Código fonte muda com frequência, dependências raramente mudam.

**Exemplo** (linhas 11-12 em `/jimy/Neural-Hive-Mind/services/specialist-business/Dockerfile`):

```dockerfile
# ✅ CORRETO: requirements primeiro
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
COPY src/ ./src/

# ❌ ERRADO: src primeiro invalida cache do pip
COPY src/ ./src/
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
```

### 3.3 Consolidação de Comandos RUN

Combine múltiplos comandos RUN com `&&` para reduzir camadas.

**Exemplo** (baseado em `/jimy/Neural-Hive-Mind/base-images/python-ml-base/Dockerfile` linhas 11-15):

```dockerfile
# ✅ CORRETO: Tudo em uma camada
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libblas-dev \
    liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

# ❌ ERRADO: Múltiplas camadas
RUN apt-get update
RUN apt-get install -y gcc g++
RUN apt-get install -y libblas-dev liblapack-dev
RUN rm -rf /var/lib/apt/lists/*
```

**Otimização do gateway-intencoes** (antes: 3 camadas, depois: 1 camada):

```dockerfile
# ✅ OTIMIZADO
RUN pip install --no-cache-dir --upgrade pip==24.0 && \
    pip install --no-cache-dir torch==2.1.0 torchaudio==2.1.0 && \
    pip install --no-cache-dir --no-deps openai-whisper && \
    pip install --no-cache-dir -r requirements.txt
```

Use `\` para continuação de linha e melhor legibilidade.

### 3.4 Instalação de Dependências

**Para pip**:
- Sempre use `--no-cache-dir` para evitar cache na imagem
- Use `--no-deps` quando apropriado (ex: openai-whisper em `/jimy/Neural-Hive-Mind/services/gateway-intencoes/Dockerfile` linha 49)

```dockerfile
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt
```

**Para apt-get**:
- Use `--no-install-recommends` para minimizar pacotes
- Sempre limpe listas de apt: `rm -rf /var/lib/apt/lists/*`

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*
```

### 3.5 Imagens Base

O projeto utiliza hierarquia de imagens base para reduzir duplicação:

```
python:3.11-slim
    ↓
python-ml-base:1.0.0
    ↓
python-grpc-base:1.0.0
    ↓
python-nlp-base:1.0.0
```

**Localização**: `/jimy/Neural-Hive-Mind/base-images/`

**Benefícios**:
- Reduz duplicação de camadas
- Builds mais rápidos (base images cacheadas)
- Consistência entre serviços

**Uso**:
```dockerfile
FROM neural-hive-mind/python-grpc-base:1.0.0
```

**Importante**: Use versões específicas (`:1.0.0`), não `:latest`, para reprodutibilidade.

## 4. BuildKit

### Ativação

BuildKit está habilitado em ambos os scripts de build:
- `/jimy/Neural-Hive-Mind/scripts/build-local-parallel.sh`
- `/jimy/Neural-Hive-Mind/scripts/build-and-push-images.sh`

```bash
export DOCKER_BUILDKIT=1
```

### Benefícios

- **Paralelização**: Estágios de build independentes executam em paralelo
- **Cache melhorado**: Cache mais inteligente e eficiente
- **Output melhorado**: Logs de build mais claros e concisos
- **Garbage collection automático**: Limpeza automática de artefatos temporários

### Verificação

```bash
docker build --progress=plain .
```

Se BuildKit estiver ativo, você verá output diferente do tradicional.

## 5. Práticas de Segurança

### Usuário Não-Root

Sempre crie e use um usuário não-root:

```dockerfile
# Criar usuário
RUN groupadd -r specialist && useradd -r -g specialist specialist

# Definir permissões
RUN chown -R specialist:specialist /app

# Trocar para usuário não-root
USER specialist
```

### Permissões de Arquivo

```dockerfile
RUN find /app -type d -exec chmod 755 {} \; && \
    find /app -type f -exec chmod 644 {} \; && \
    chmod +x /app/src/main.py
```

- Diretórios: `755` (rwxr-xr-x)
- Arquivos: `644` (rw-r--r--)
- Executáveis: `755` ou `+x`

### Versões Específicas

```dockerfile
# ✅ CORRETO
FROM python:3.11-slim
RUN pip install --no-cache-dir torch==2.1.0

# ❌ EVITAR
FROM python:latest
RUN pip install torch
```

## 6. Scripts de Build

### Build Paralelo Local

**Script**: `/jimy/Neural-Hive-Mind/scripts/build-local-parallel.sh`

**Características**:
- Controla paralelismo com `MAX_PARALLEL_JOBS` (padrão: 4)
- Constrói imagens base primeiro
- Executa builds de serviços em paralelo
- Logging detalhado de progresso

**Uso**:
```bash
# Build com 4 jobs paralelos (padrão)
./scripts/build-local-parallel.sh

# Build com 8 jobs paralelos
MAX_PARALLEL_JOBS=8 ./scripts/build-local-parallel.sh

# Build com cache limpo
./scripts/build-local-parallel.sh --no-cache
```

**Padrão de implementação**:
1. Verifica pré-requisitos
2. Constrói imagens base (`build-base-images.sh`)
3. Coleta lista de serviços
4. Executa builds em paralelo (controlado por `MAX_PARALLEL_JOBS`)
5. Rastreia progresso e erros
6. Logging para `/tmp/build-*.log`

### Build e Push para ECR

**Script**: `/jimy/Neural-Hive-Mind/scripts/build-and-push-images.sh`

**Características**:
- Carrega variáveis de ambiente
- Login no ECR
- Constrói e empurra imagens base
- Constrói e empurra serviços principais
- Constrói e empurra especialistas
- Tratamento de erros e logging

**Uso**:
```bash
./scripts/build-and-push-images.sh
```

## 7. Verificação e Testes

### Verificar Tamanho de Imagens

```bash
docker images | grep neural-hive-mind
```

Procure por tamanhos excessivamente grandes.

### Verificar Contagem de Camadas

```bash
docker history <imagem>
```

Menos camadas geralmente é melhor (resultado de consolidação de RUN).

### Testar Cache de Build

1. Build inicial:
```bash
docker build -t test-service .
```

2. Modificar código fonte (não requirements.txt)

3. Rebuild:
```bash
docker build -t test-service .
```

4. Verificar: O passo `pip install` deve mostrar "Using cache"

### Scan de Vulnerabilidades

```bash
# Docker scan nativo
docker scan <imagem>

# Ou Trivy
trivy image <imagem>
```

## 8. Anti-Padrões Comuns a Evitar

### ❌ Copiar src no Estágio Builder Desnecessariamente

**Problema**: Invalida cache do pip quando código muda.

**Antes** (ver problema em `/jimy/Neural-Hive-Mind/services/worker-agents/Dockerfile` - corrigido):
```dockerfile
# Builder stage
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY src/ ./src/  # ❌ Desnecessário no builder
```

**Depois**:
```dockerfile
# Builder stage
COPY requirements.txt .
RUN pip install -r requirements.txt
# src copiado apenas no runtime stage
```

### ❌ Múltiplos RUN para Operações Relacionadas

```dockerfile
# ❌ ERRADO
RUN pip install torch
RUN pip install torchaudio
RUN pip install -r requirements.txt

# ✅ CORRETO
RUN pip install --no-cache-dir torch torchaudio && \
    pip install --no-cache-dir -r requirements.txt
```

### ❌ Não Usar .dockerignore

**Resultado**: Contexto de build gigante, builds lentos.

### ❌ Usar Tags :latest em Produção

```dockerfile
# ❌ EVITAR
FROM python:latest

# ✅ PREFERIR
FROM python:3.11-slim
```

### ❌ Executar Como Root

```dockerfile
# ❌ EVITAR
USER root
CMD ["python", "app.py"]

# ✅ PREFERIR
USER appuser
CMD ["python", "app.py"]
```

### ❌ Não Limpar Caches de Gerenciadores de Pacotes

```dockerfile
# ❌ ERRADO
RUN apt-get update && apt-get install -y gcc

# ✅ CORRETO
RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*
```

## 9. Referência Rápida

### Tabela de Serviços

| Serviço | Dockerfile | Multi-stage | Base Image |
|---------|-----------|-------------|------------|
| analyst-agents | ✅ | ✅ | python-grpc-base:1.0.0 |
| code-forge | ✅ | ✅ | python:3.11-slim |
| consensus-engine | ✅ | ✅ | python-grpc-base:1.0.0 |
| execution-ticket-service | ✅ | ❌ | python:3.11-slim |
| explainability-api | ✅ | ❌ | python:3.11-slim |
| gateway-intencoes | ✅ | ❌ | python:3.11-slim |
| guard-agents | ✅ | ✅ | python-grpc-base:1.0.0 |
| mcp-tool-catalog | ✅ | ❌ | python:3.11-slim |
| memory-layer-api | ✅ | ❌ | python:3.11-slim |
| optimizer-agents | ✅ | ✅ | python-grpc-base:1.0.0 |
| orchestrator-dynamic | ✅ | ❌ | python:3.11-slim |
| queen-agent | ✅ | ✅ | python-grpc-base:1.0.0 |
| scout-agents | ✅ | ✅ | python-grpc-base:1.0.0 |
| self-healing-engine | ✅ | ❌ | python:3.11-slim |
| semantic-translation-engine | ✅ | ✅ | python-nlp-base:1.0.0 |
| service-registry | ✅ | ❌ | python:3.11-slim |
| sla-management-system | ✅ | ❌ | python:3.11-slim |
| specialist-architecture | ✅ | ✅ | python-grpc-base:1.0.0 |
| specialist-behavior | ✅ | ✅ | python-grpc-base:1.0.0 |
| specialist-business | ✅ | ✅ | python-grpc-base:1.0.0 |
| specialist-evolution | ✅ | ✅ | python-grpc-base:1.0.0 |
| specialist-technical | ✅ | ✅ | python-grpc-base:1.0.0 |
| worker-agents | ✅ | ✅ | python:3.11-slim |

### Comandos de Build

```bash
# Build local de um serviço específico
docker build -t neural-hive-mind/<serviço>:1.0.0 \
    -f services/<serviço>/Dockerfile \
    --build-arg VERSION=1.0.0 \
    .

# Build local paralelo de todos os serviços
./scripts/build-local-parallel.sh

# Build e push para ECR
./scripts/build-and-push-images.sh

# Build sem cache
docker build --no-cache -t <imagem> .

# Build com BuildKit e output detalhado
DOCKER_BUILDKIT=1 docker build --progress=plain -t <imagem> .
```

### Troubleshooting

**Problema**: Build lento
- ✅ Verificar .dockerignore existe e está completo
- ✅ Verificar ordem de COPY (requirements antes de src)
- ✅ Verificar BuildKit está habilitado
- ✅ Verificar consolidação de comandos RUN

**Problema**: Cache não funciona
- ✅ Verificar ordem de instruções Dockerfile
- ✅ Não copiar arquivos desnecessários antes de RUN
- ✅ Verificar se .dockerignore exclui arquivos voláteis

**Problema**: Imagem muito grande
- ✅ Usar multi-stage builds
- ✅ Limpar caches de gerenciadores de pacotes
- ✅ Usar --no-install-recommends com apt-get
- ✅ Verificar .dockerignore

**Problema**: Build falha com erro de permissão
- ✅ Verificar se diretórios foram criados antes de uso
- ✅ Verificar permissões corretas (chown)
- ✅ Executar comandos que precisam root antes de USER

## 10. Documentação Relacionada

- 📚 [README Principal](/jimy/Neural-Hive-Mind/README.md)
- 🐳 [Base Images](/jimy/Neural-Hive-Mind/base-images/)
- 🔧 [Scripts de Build](/jimy/Neural-Hive-Mind/scripts/)
- 📋 [Template .dockerignore](/jimy/Neural-Hive-Mind/services/semantic-translation-engine/.dockerignore)

---

**Última atualização**: 2025-11-18
**Versão do Projeto**: 1.0.7
