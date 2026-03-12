# Guia de Uso do DockerfileGenerator

## Visão Geral

O `DockerfileGenerator` gera Dockerfiles otimizados para diferentes linguagens e frameworks, seguindo as melhores práticas de segurança e performance.

## Importação e Instanciação

```python
from src.services.dockerfile_generator import (
    DockerfileGenerator,
    SupportedLanguage,
    ArtifactType
)

# Instanciar gerador
generator = DockerfileGenerator()
```

## Uso Básico

### Gerar Dockerfile Padrão

```python
dockerfile = generator.generate_dockerfile(
    language=SupportedLanguage.PYTHON
)

print(dockerfile)
# Saída: Dockerfile Python multi-stage com usuário não-root
```

### Gerar com Framework Específico

```python
# Python com FastAPI
dockerfile = generator.generate_dockerfile(
    language=SupportedLanguage.PYYON,
    framework="fastapi"
)

# Node.js com Express
dockerfile = generator.generate_dockerfile(
    language=SupportedLanguage.NODEJS,
    framework="express"
)
```

### Gerar para Tipo de Artefato

```python
# Microservice padrão (com EXPOSE e HEALTHCHECK)
dockerfile = generator.generate_dockerfile(
    language=SupportedLanguage.PYTHON,
    artifact_type=ArtifactType.MICROSERVICE
)

# Lambda Function (sem EXPOSE tradicional)
dockerfile = generator.generate_dockerfile(
    language=SupportedLanguage.PYTHON,
    artifact_type=ArtifactType.LAMBDA_FUNCTION
)
```

## Linguagens Suportadas

### Python

**Framework:** FastAPI (padrão), Flask
**Versão Base:** 3.11-slim
**Porta Padrão:** 8000

```python
dockerfile = generator.generate_dockerfile(
    language=SupportedLanguage.PYTHON,
    framework="fastapi",
    artifact_type=ArtifactType.MICROSERVICE
)
```

**Estrutura Gerada:**
- Multi-stage: builder (com dependências) + final (runtime)
- Usuário: `appuser` (UID 1000)
- HEALTHCHECK via curl
- Porta 8000 exposta

### Node.js

**Framework:** Express (padrão), NestJS
**Versão Base:** 20-alpine
**Porta Padrão:** 3000

```python
dockerfile = generator.generate_dockerfile(
    language=SupportedLanguage.NODEJS,
    framework="express"
)
```

**Estrutura Gerada:**
- Multi-stage: builder (npm ci) + final (apenas production)
- Usuário: `nodejs` (UID 1000)
- HEALTHCHECK via curl
- npm install com `--only=production`

### TypeScript

**Framework:** NestJS (padrão), Express
**Versão Base:** 20-alpine
**Porta Padrão:** 3000

```python
dockerfile = generator.generate_dockerfile(
    language=SupportedLanguage.TYPESCRIPT,
    framework="nestjs"
)
```

**Estrutura Gerada:**
- Multi-stage com compilação (tsc)
- ENTRYPOINT com tini para signal handling
- Duas fases: todas as dependências + apenas produção
- Usuário: `nodejs` (UID 1000)

### Go

**Framework:** Gin, Echo (ou genérico)
**Versão Base:** 1.21-alpine → scratch
**Porta Padrão:** 8080

```python
dockerfile = generator.generate_dockerfile(
    language=SupportedLanguage.GOLANG,
    framework="gin"
)
```

**Estrutura Gerada:**
- Single stage (build estático)
- Imagem final: scratch (mínimo possível)
- Binário compilado com CGO_ENABLED=0

### Java

**Framework:** Spring Boot (padrão)
**Versão Base:** 21-slim (build) → 21-jre (runtime)
**Porta Padrão:** 8080

```python
dockerfile = generator.generate_dockerfile(
    language=SupportedLanguage.JAVA,
    framework="spring-boot"
)
```

**Estrutura Gerada:**
- Multi-stage com Maven
- JAR extraído para /app/app.jar
- HEALTHCHECK em /actuator/health

### C#

**Framework:** ASP.NET Core
**Versão Base:** 8.0 SDK (build) → 8.0 runtime
**Porta Padrão:** 8080

```python
dockerfile = generator.generate_dockerfile(
    language=SupportedLanguage.CSHARP,
    framework="aspnet"
)
```

## Tipos de Artefato

### MICROSERVICE

Padrão para APIs e serviços web. Inclui:
- Porta exposta (EXPOSE)
- HEALTHCHECK configurado
- Framework web otimizado

### LAMBDA_FUNCTION

Para AWS Lambda. Características:
- **SEM** EXPOSE tradicional
- CMD usa awslambdaric
- Runtime Python otimizado para Lambda

```python
dockerfile = generator.generate_dockerfile(
    language=SupportedLanguage.PYTHON,
    artifact_type=ArtifactType.LAMBDA_FUNCTION
)
```

### CLI_TOOL

Ferramentas de linha de comando. Características:
- ENTRYPOINT em vez de CMD
- Sem porta exposta
- Build focado em binário estático

### LIBRARY

Bibliotecas e pacotes. Características:
- Sem ENTRYPOINT/CMD (apenas código)
- Usuário para instalação via pip/npm

## Template Customizado

Você pode fornecer seu próprio Dockerfile:

```python
custom_dockerfile = """FROM python:3.11-slim
RUN pip install my-package
CMD ["python", "-m", "mypackage"]
"""

dockerfile = generator.generate_dockerfile(
    language=SupportedLanguage.PYTHON,
    custom_template=custom_dockerfile
)
```

## Padrões dos Templates Gerados

### Multi-Stage Build

Todos os templates usam multi-stage build para minimizar tamanho:

```dockerfile
# Builder stage
FROM base-image as builder
WORKDIR /app
# ... instalação de dependências ...

# Final stage
FROM base-image
WORKDIR /app
COPY --from=builder /path /path
# ... configuração runtime ...
```

### Segurança

1. **Usuário Não-Root:** Todos os templates criam usuário não-root
2. **Imagens Base Oficiais:** Imagens verificadas de Docker Hub
3. **Sem Segredos:** Nenhuma credencial nos templates

### Health Checks

Microservices incluem HEALTHCHECK:

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:PORT/health || exit 1
```

## Exemplos Completos

### Exemplo 1: API FastAPI

```python
from src.services.dockerfile_generator import DockerfileGenerator, SupportedLanguage

generator = DockerfileGenerator()

dockerfile = generator.generate_dockerfile(
    language=SupportedLanguage.PYTHON,
    framework="fastapi",
    artifact_type=ArtifactType.MICROSERVICE
)

# Salvar em arquivo
with open("Dockerfile", "w") as f:
    f.write(dockerfile)
```

### Exemplo 2: WebApp NestJS

```python
dockerfile = generator.generate_dockerfile(
    language=SupportedLanguage.TYPESCRIPT,
    framework="nestjs",
    artifact_type=ArtifactType.MICROSERVICE
)

# Resultado inclui transpilação TypeScript
```

### Exemplo 3: CLI Go

```python
dockerfile = generator.generate_dockerfile(
    language=SupportedLanguage.GOLANG,
    artifact_type=ArtifactType.CLI_TOOL
)

# Resultado: binário estático em scratch
```

## Troubleshooting

### Erro: Linguagem não suportada

```python
# ❌ Isso vai gerar ValueError
dockerfile = generator.generate_dockerfile(language="ruby")

# ✅ Use a enum SupportedLanguage
dockerfile = generator.generate_dockerfile(
    language=SupportedLanguage.PYTHON
)
```

### Template Vazio

Se o template gerado estiver vazio, verifique:
1. Se a linguagem está implementada em `_templates`
2. Se a função do template retorna string

### Build Falha

Se o build falhar com o Dockerfile gerado:
1. Verifique se o framework existe para a linguagem
2. Confirme se os arquivos necessários existem (requirements.txt, package.json, etc.)
3. Para TypeScript, verifique se tsconfig.json existe

## Boas Práticas

1. **Sempre versionar imagens:** Use tags específicos (python:3.11-slim, não python:latest)
2. **Minimize camadas:** Cada RUN cria uma layer, combine comandos
3. ** aproveite cache:** Copie arquivos que mudam com frequência depois de dependências que mudam pouco
4. **Use .dockerignore:** Exclua arquivos desnecessários do build

## Referências

- [Dockerfile Reference](https://docs.docker.com/engine/reference/builder/)
- [Multi-stage builds](https://docs.docker.com/build/building/multi-stage/)
- [Python Docker Hub](https://hub.docker.com/_/python/)
- [Node Docker Hub](https://hub.docker.com/_/node/)
