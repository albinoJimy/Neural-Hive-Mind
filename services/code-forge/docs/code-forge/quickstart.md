# Quickstart - CodeForge Container Builds

## Instalação Rápida

```bash
cd services/code-forge
pip install -e .
```

## Uso Básico

### 1. Gerar um Dockerfile

```python
from src.services.dockerfile_generator import (
    DockerfileGenerator,
    SupportedLanguage
)

generator = DockerfileGenerator()

# Gerar Dockerfile para FastAPI
dockerfile = generator.generate_dockerfile(
    language=SupportedLanguage.PYTHON,
    framework="fastapi"
)

# Salvar
with open("Dockerfile", "w") as f:
    f.write(dockerfile)
```

### 2. Build de Container

```python
from src.services.container_builder import ContainerBuilder

builder = ContainerBuilder(timeout_seconds=3600)

result = await builder.build_container(
    dockerfile_path="Dockerfile",
    build_context=".",
    image_tag="myapp:1.0.0"
)

if result.success:
    print(f"✅ Build OK: {result.image_digest}")
    print(f"   Size: {result.size_bytes / 1024 / 1024:.1f} MB")
else:
    print(f"❌ Erro: {result.error_message}")
```

### 3. Pipeline Completo

```python
from src.services.pipeline_engine import PipelineEngine
from src.services.dockerfile_generator import DockerfileGenerator
from src.services.container_builder import ContainerBuilder
from src.models.execution_ticket import ExecutionTicket

# Configurar pipeline com builds habilitados
engine = PipelineEngine(
    enable_container_build=True,
    dockerfile_generator=DockerfileGenerator(),
    container_builder=ContainerBuilder()
)

# Criar ticket
ticket = ExecutionTicket(
    ticket_id="my-service-001",
    task_type="BUILD",
    parameters={
        "language": "python",
        "framework": "fastapi",
        "service_name": "my-api",
        "version": "1.0.0"
    }
)

# Executar
result = await engine.execute_pipeline(ticket)
print(f"Status: {result.status}")
```

## Linguagens Disponíveis

| Linguagem | Parâmetro | Frameworks |
|-----------|-----------|------------|
| Python | `"python"` | fastapi, flask |
| Node.js | `"nodejs"` | express, nest |
| TypeScript | `"typescript"` | nestjs, express |
| Go | `"golang"` | gin, echo |
| Java | `"java"` | spring-boot |
| C# | `"csharp"` | aspnet |

## Tipos de Artefato

| Tipo | Uso |
|------|-----|
| `"microservice"` | APIs web com porta e healthcheck |
| `"lambda_function"` | AWS Lambda (sem EXPOSE) |
| `"cli_tool"` | Ferramentas CLI (ENTRYPOINT) |
| `"library"` | Bibliotecas para instalar |

## Dockerfile Gerado (Exemplo Python)

```dockerfile
# Builder stage
FROM python:3.11-slim as builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl
COPY --from=builder /root/.local /root/.local
COPY . .
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser
ENV PATH=/root/.local/bin:$PATH
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Próximos Passos

- [Guia Completo do DockerfileGenerator](dockerfile-generator-guide.md)
- [Guia Completo do ContainerBuilder](container-builder-guide.md)
- [Exemplos de Uso](examples.md)
- [Troubleshooting](troubleshooting.md)
- [FAQ](faq.md)
