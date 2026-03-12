# Guia de Uso do ContainerBuilder

## Visão Geral

O `ContainerBuilder` executa builds de container usando Docker CLI ou Kaniko, retornando metadados do build incluindo digest SHA256.

## Importação e Instanciação

```python
from src.services.container_builder import ContainerBuilder, BuilderType

# Instanciar com Docker CLI (padrão)
builder = ContainerBuilder()

# Ou especificar o tipo explicitamente
builder = ContainerBuilder(
    builder_type=BuilderType.DOCKER,
    timeout_seconds=3600  # 1 hora
)
```

## Tipos de Builder

### Docker CLI

**Uso:** Builds locais em ambiente de desenvolvimento

```python
builder = ContainerBuilder(
    builder_type=BuilderType.DOCKER
)
```

**Requisitos:**
- Docker daemon rodando
- Docker CLI instalado
- Permissão para acessar Docker socket

### Kaniko

**Uso:** Builds em Kubernetes sem Docker daemon

```python
builder = ContainerBuilder(
    builder_type=BuilderType.KANIKO
)
```

**Requisitos:**
- Cluster Kubernetes configurado
- Pod com permissões de docker-insecure (não-produção)
- Configmap com credenciais de registry (se privado)

**Nota:** Kaniko ainda não está implementado - em desenvolvimento.

## Uso Básico

### Build Simples

```python
result = await builder.build_container(
    dockerfile_path="/path/to/Dockerfile",
    build_context="/path/to/context",
    image_tag="myapp:latest"
)

if result.success:
    print(f"Build OK! Digest: {result.image_digest}")
else:
    print(f"Build falhou: {result.error_message}")
```

### Build com Argumentos

```python
result = await builder.build_container(
    dockerfile_path="/path/to/Dockerfile",
    build_context="/path/to/context",
    image_tag="myapp:v1.0.0",
    build_args=[
        "ENV=production",
        "VERSION=1.0.0"
    ]
)
```

## Resultado de Build

### ContainerBuildResult

```python
@dataclass
class ContainerBuildResult:
    success: bool              # Build completou com sucesso?
    image_digest: str | None  # SHA256 digest (ex: sha256:abc...)
    size_bytes: int | None     # Tamanho da imagem em bytes
    error_message: str | None  # Mensagem de erro se falhou
    duration_ms: int           # Duração do build em ms
    image_tag: str             # Tag da imagem
```

### Exemplos de Uso

```python
# Sucesso
result = ContainerBuildResult(
    success=True,
    image_digest="sha256:abc123...",
    size_bytes=123456789,
    error_message=None,
    duration_ms=45000,
    image_tag="myapp:latest"
)

# Falha
result = ContainerBuildResult(
    success=False,
    image_digest=None,
    size_bytes=None,
    error_message="Build failed: step 7: exit code 1",
    duration_ms=15000,
    image_tag="myapp:latest"
)
```

## Build Context

### O que é Build Context?

O build context é o diretório que contém todos os arquivos necessários para o build:

```
my-app/
├── Dockerfile          # Definição da imagem
├── requirements.txt     # Dependências Python
├── src/                # Código fonte
│   └── main.py
├── tests/              # Testes
└── README.md
```

### Boas Práticas

1. **Minimize o contexto:** Use `.dockerignore` para excluir arquivos desnecessários
2. **Organize camadas:** Arquivos que mudam pouco depois dos que mudam muito
3. **Evite segredos:** Nunca inclua senhas/tokens no context

## Timeout e Retries

### Configurar Timeout

```python
builder = ContainerBuilder(
    timeout_seconds=7200  # 2 horas
)
```

### Comportamento em Timeout

```python
# Se timeout expirar:
result = ContainerBuildResult(
    success=False,
    error_message="Build timeout after 7200 seconds",
    # ... outros campos
)
```

## Tratamento de Erros

### Tipos de Erro

1. **Dockerfile não encontrado:** Verifique o caminho do arquivo
2. **Context inválido:** Diretório não existe ou não acessível
3. **Build falha:** Erro durante o build (sintaxe, dependências, etc.)
4. **Timeout:** Build demorou mais que o timeout configurado

### Tratamento Robusto

```python
try:
    result = await builder.build_container(
        dockerfile_path=dockerfile_path,
        build_context=context_dir,
        image_tag=image_tag
    )

    if result.success:
        logger.info(f"Build OK: {result.image_digest}")
    else:
        logger.error(f"Build falhou: {result.error_message}")
        # Implementar lógica de retry ou notificação

except FileNotFoundError as e:
    logger.error(f"Dockerfile não encontrado: {e}")

except Exception as e:
    logger.error(f"Erro inesperado: {e}")
```

## Build Args

### Passando Argumentos de Build

```python
result = await builder.build_container(
    dockerfile_path="/path/Dockerfile",
    build_context="/path/to/context",
    image_tag="myapp:latest",
    build_args=[
        "APP_VERSION=1.0.0",
        "ENVIRONMENT=production",
        "DEBUG=false"
    ]
)
```

### Usando no Dockerfile

```dockerfile
# No Dockerfile
ARG APP_VERSION
ARG ENVIRONMENT

ENV APP_VERSION=${APP_VERSION}
ENV ENVIRONMENT=${ENVIRONMENT}
```

## Cache de Build

### Docker Layer Cache

O Docker usa cache de camadas automaticamente. Para otimizar:

1. **Arquivos de dependências primeiro:**
```dockerfile
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
```

2. **Comandos combinados:**
```dockerfile
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl vim && \
    rm -rf /var/lib/apt/lists/*
```

### Limpar Cache Local

```bash
docker system prune -a
```

## Métricas

### Métricas Emitidas

```python
# ContainerBuilder emite métricas Prometheus:
codeforge_container_build_duration_seconds{builder_type="docker",language="python"}
codeforge_container_build_size_bytes{language="python"}
codeforge_container_build_success_total{builder_type="docker",language="python",success="true"}
```

## Integração com PipelineEngine

### Uso Automático

O PipelineEngine usa ContainerBuilder automaticamente quando `enable_container_build=True`:

```python
engine = PipelineEngine(
    # ... outros serviços
    dockerfile_generator=DockerfileGenerator(),
    container_builder=ContainerBuilder(
        builder_type=BuilderType.DOCKER,
        timeout_seconds=3600
    ),
    enable_container_build=True
)
```

### Desabilitar Builds

Para ambientes sem Docker:

```python
engine = PipelineEngine(
    # ... outros serviços
    enable_container_build=False  # Pula stages de build
)
```

## Troubleshooting

### Docker Daemon Não Rodando

**Sintoma:** `error during connect`

**Solução:**
```bash
# Verificar se Docker está rodando
docker --version

# Verificar se daemon está acessível
docker info
```

### Permissão Negada

**Sintoma:** `permission denied while trying to connect`

**Solução:**
```bash
# Adicionar usuário ao grupo docker
sudo usermod -aG docker $USER

# Fazer logout e login novamente
```

### Build Context Muito Grande

**Sintoma:** Build lento ou erro de contexto

**Solução:**
1. Criar `.dockerignore`:
```
.git
node_modules
__pycache__
*.pyc
tests/
docs/
```

2. Mover arquivos grandes para fora do context

### Timeout em Builds Lentos

**Sintoma:** Build timeout em projetos grandes

**Solução:**
```python
builder = ContainerBuilder(
    timeout_seconds=7200  # Aumentar para 2 horas
)
```

## Boas Práticas

### 1. Tags Semanticos

```python
# ❌ Evitar
image_tag="app:latest"

# ✅ Usar
image_tag="myapp:v1.2.3"
```

### 2. Multi-Stage Builds

Use multi-stage para minimizar tamanho final:

```dockerfile
# Builder com ferramentas
FROM golang:1.21-alpine as builder
WORKDIR /app
COPY . .
RUN go build -o main .

# Runtime mínimo
FROM alpine:latest
COPY --from=builder /app/main .
CMD ["./main"]
```

### 3. Non-Root User

Sempre use usuário não-root em produção:

```dockerfile
RUN useradd -m -u 1000 appuser
USER appuser
```

### 4. Saúde e Monitoramento

Inclua HEALTHCHECK para serviços:

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s \
    CMD curl -f http://localhost:8080/health || exit 1
```

## Exemplos Completos

### Exemplo 1: Build Python Simples

```python
from src.services.container_builder import ContainerBuilder

builder = ContainerBuilder()

result = await builder.build_container(
    dockerfile_path="/tmp/myapp/Dockerfile",
    build_context="/tmp/myapp",
    image_tag="myapp:v1.0.0"
)

if result.success:
    print(f"Imagem criada: {result.image_digest}")
    print(f"Tamanho: {result.size_bytes / 1024 / 1024:.1f} MB")
else:
    print(f"Erro: {result.error_message}")
```

### Exemplo 2: Build com Retry

```python
import asyncio
from src.services.container_builder import ContainerBuilder

async def build_with_retry():
    builder = ContainerBuilder(timeout_seconds=1800)

    for attempt in range(3):
        result = await builder.build_container(
            dockerfile_path="Dockerfile",
            build_context=".",
            image_tag=f"app:v1.0.{attempt}"
        )

        if result.success:
            return result

        print(f"Tentativa {attempt + 1} falhou: {result.error_message}")
        await asyncio.sleep(5)

    return None

result = await build_with_retry()
```

### Exemplo 3: Build com Validação

```python
async def build_and_validate():
    builder = ContainerBuilder()

    result = await builder.build_container(
        dockerfile_path="Dockerfile",
        build_context=".",
        image_tag="myapp:latest"
    )

    # Validar resultado
    assert result.success is True, f"Build falhou: {result.error_message}"
    assert result.image_digest is not None, "Digest vazio"
    assert result.size_bytes > 0, "Imagem vazia"
    assert result.size_bytes < 1_000_000_000, "Imagem > 1GB"

    print(f"Build validado: {result.image_digest[:20]}...")
    return result
```

## Referências

- [Docker Build Reference](https://docs.docker.com/engine/reference/commandline/build/)
- [Kaniko Repository](https://github.com/GoogleContainerTools/kaniko)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
