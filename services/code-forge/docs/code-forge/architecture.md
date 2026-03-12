# CodeForge: Arquitetura de Builds de Container

## Visão Geral

O CodeForge é um serviço de geração de código que implementa builds de container reais como parte do pipeline de execução. Esta arquitetura descreve como os componentes de build de container se integram ao pipeline existente.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CodeForge Pipeline                              │
│                                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Template   │  │    Code      │  │  Dockerfile  │  │   Container  │     │
│  │   Selector   │─▶│   Composer   │─▶│  Generator  │─▶│    Builder    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Validator   │  │  TestRunner  │  │   Packager   │  │  Approval    │     │
│  └──────────────┘─▶└──────────────┘─▶└──────────────┘─▶└──────────────┘     │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │                        Persistence Layer                              │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐             │  │
│  │  │  S3 SBOM │  │ MongoDB  │  │PostgreSQL │  │ Registry  │             │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘             │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Componentes Principais

### 1. DockerfileGenerator

**Arquivo:** `src/services/dockerfile_generator.py`

**Responsabilidade:** Gerar Dockerfiles otimizados baseado em linguagem e framework.

**Características:**
- Multi-stage builds para minimizar tamanho final
- Suporte a 6 linguagens: Python, Node.js, Go, Java, TypeScript, C#
- Usuário não-root em todas as imagens
- HEALTHCHECK configurável
- Suporte a diferentes tipos de artefato (Microservice, Lambda Function, CLI Tool, Library)

**Templates Disponíveis:**
| Linguagem | Versão Base | Frameworks Suportados |
|-----------|-------------|----------------------|
| Python | 3.11-slim | FastAPI, Flask |
| Node.js | 20-alpine | Express, NestJS |
| Go | 1.21-alpine | Gin, Echo |
| Java | 21-slim | Spring Boot |
| TypeScript | 20-alpine | NestJS, Express |
| C# | 8.0 | ASP.NET Core |

### 2. ContainerBuilder

**Arquivo:** `src/services/container_builder.py`

**Responsabilidade:** Executar builds de container usando Docker CLI ou Kaniko.

**Características:**
- Suporte a Docker CLI (builds locais)
- Interface preparada para Kaniko (builds em Kubernetes)
- Captura de digest SHA256
- Métricas de duração do build
- Tratamento de erros detalhado

**Builders Suportados:**
```python
class BuilderType(str, Enum):
    DOCKER = "docker"      # Docker CLI (local)
    KANIKO = "kaniko"    # Kaniko (Kubernetes)
    BUILDKIT = "buildkit"  # BuildKit (futuro)
```

### 3. PipelineEngine Modificado

**Arquivo:** `src/services/pipeline_engine.py`

**Novos Stages:**
```
1. template_selection    # EXISTE
2. code_composition       # EXISTE
3. dockerfile_generation  # NOVO
4. container_build        # NOVO
5. validation            # EXISTE
6. testing               # EXISTE
7. packaging             # EXISTE
8. approval_gate         # EXISTE
```

**Fluxo dos Novos Stages:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Stage 3: dockerfile_generation                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │ 1. Detectar linguagem a partir dos parâmetros do ticket          │ │
│  │ 2. Identificar framework (se aplicável)                           │ │
│  │ 3. Mapear tipo de artefato (microservice, lambda, cli, library)   │ │
│  │ 4. Gerar Dockerfile usando template apropriado                    │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                       ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  Stage 4: container_build                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │ 1. Salvar Dockerfile em disco (workspace do pipeline)            │ │
│  │ 2. Definir tag da imagem (nome:versão)                           │ │
│  │ 3. Executar build usando ContainerBuilder                         │
│  │ 4. Capturar digest SHA256                                        │ │
│  │ 5. Salvar metadados no contexto                                  │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Integrações com Serviços Externos

### 1. Artifact Registry

**Arquivo:** `src/clients/artifact_registry_client.py`

**Operações:**
- `register_container()`: Registra metadados de container construído
- `get_container_metadata()`: Recupera metadados registrados
- `list_containers()`: Lista containers por critérios

### 2. Trivy (Security Scanning)

**Arquivo:** `src/clients/trivy_client.py`

**Operações:**
- `scan_filesystem()`: Scan de vulnerabilidades no filesystem
- `scan_container_image()`: Scan de imagem de container
- Retorno: `ValidationResult` com contagem de issues por severidade

### 3. Sigstore (SBOM e Signing)

**Arquivo:** `src/clients/sigstore_client.py`

**Operações:**
- `generate_sbom()`: Gera SBOM usando Syft
- `sign_artifact()**: Assina artefato com Sigstore

### 4. S3 Artifact Storage

**Arquivo:** `src/clients/s3_artifact_client.py`

**Operações:**
- `upload_sbom()`: Faz upload de SBOM
- `verify_sbom_integrity()`: Verifica integridade de SBOM armazenado

## Camadas de Persistência

### MongoDB
- **Conteúdo:** Código fonte gerado
- **Operação:** `mongodb_client.save_artifact_content()`
- **Recuperação:** Via `content_uri` nos artefatos

### PostgreSQL
- **Metadados:** Metadados de artefatos e resultados de pipeline
- **Operações:**
  - `postgres_client.save_artifact_metadata()`
  - `postgres_client.save_pipeline()`
- **Schema:** Tabelas `artifacts` e `pipelines`

### S3
- **SBOMs:** Software Bill of Materials
- **Operação:** Upload via Sigstore client
- **Formato:** SPDX-JSON ou CycloneDX-JSON

## Padrões de Design

### 1. Fault Tolerance

**Retry Pattern:**
```python
# Validator usa return_exceptions=True
results = await asyncio.gather(
    *validation_tasks,
    return_exceptions=True  # Não falha pipeline inteiro
)
```

**Fallback em Templates:**
- Se MCP tool selection falhar → usa template padrão
- Se template específico não encontrado → usa template genérico

### 2. Multi-Stage Builds

**Padrão:**
```dockerfile
# Builder stage - compilações e dependências
FROM base-image as builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user -r requirements.txt

# Final stage - mínimo necessário
FROM base-image
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .
RUN useradd -m appuser
USER appuser
```

### 3. Separação de Concerns

**DockerfileGenerator:** Apenas gera string do Dockerfile
**ContainerBuilder:** Apenas executa build (não gera Dockerfile)
**PipelineEngine:** Orquestra os dois, mas não conhece detalhes

## Configuração

### Variáveis de Ambiente

```bash
# Build Configuration
ENABLE_CONTAINER_BUILD=true   # Habilita/desabilita builds
BUILD_TIMEOUT=3600              # Timeout em segundos
DEFAULT_BUILDER=docker          # docker|kaniko

# Registry
REGISTRY_URL=docker.io         # Registry para push
REGISTRY_USERNAME=              # Credenciais
REGISTRY_PASSWORD=              # Credenciais

# Cache
BUILDKIT_CACHE_TYPE=registry    # registry|local|s3
BUILDKIT_CACHE_ADDR=            # Endereço do cache
```

### Parâmetros do Ticket

```python
ticket.parameters = {
    "language": "python",           # python|nodejs|golang|java|typescript|csharp
    "framework": "fastapi",          # fastapi|flask|express|nestjs|spring-boot|etc
    "artifact_type": "microservice",  # microservice|lambda_function|cli_tool|library
    "service_name": "my-service",    # Nome do serviço
    "version": "1.0.0"               # Versão do artefato
}
```

## Métricas e Observabilidade

### Métricas Emitidas

**Pipeline:**
- `codeforge_pipeline_duration_seconds` (labels: status)
- `codeforge_pipeline_stages_total` (labels: stage)
- `codeforge_pipeline_builds_total` (labels: success)

**Container Build:**
- `codeforge_container_build_duration_seconds` (labels: builder_type, language)
- `codeforge_container_build_size_bytes` (labels: language)
- `codeforge_container_build_success_total` (labels: builder_type, language)

**Validação:**
- `codeforge_validation_issues_found` (labels: severity, tool)
- `codeforge_validation_duration_seconds` (labels: validation_type, tool)

### Logging

**Structured Logging com Structlog:**
```python
logger.info(
    "container_build_completed",
    pipeline_id=pipeline_id,
    image_tag=image_tag,
    digest=result.image_digest,
    size_bytes=result.size_bytes,
    duration_ms=result.duration_ms
)
```

## Segurança

### Práticas Implementadas

1. **Usuário Não-Root:** Todas as imagens rodam como usuário não privilegiado
2. **Imagens Base Oficiais:** Uso de imagens verificadas (python:3.11-slim, node:20-alpine, etc)
3. **Scan de Vulnerabilidades:** Trivy integrado em todos os builds
4. **SBOM:** Rastreabilidade de todas as dependências
5. **Signing:** Assinatura digital com Sigstore

### Variáveis Sensíveis

- Nunca logar credenciais
- Usar secrets do Kubernetes para registry privado
- Variáveis de ambiente via ConfigMaps/Secrets

## Limitações e Decisões de Design

### Limitações Atuais

1. **Kaniko Não Implementado:** Apenas Docker CLI está funcionando
2. **Multi-Arch:** Suporte apenas para arquitetura do host
3. **Cache Distribuído:** Builds sem cache entre execuções

### Decisões de Design

1. **Templates em Código:** Dockerfiles gerados via Python, não YAML externo
2. **Validação Resiliente:** Falhas na validação não interrompem o pipeline
3. **Geração Template-Based:** CodeComposer usa templates quando disponível
4. **Persistência Dual:** Código no MongoDB, metadados no PostgreSQL

## Evolução Futura

### FASE 3 (Planejada)

- [ ] Implementar Kaniko para builds em Kubernetes
- [ ] BuildKit cache distribuído
- [ ] Multi-arch builds (amd64, arm64)
- [ ] Otimizações de performance

### FASE 4 (Em Progresso)

- [ ] Test Runner real com execução de testes
- [ ] Testes E2E completos ✅ (concluído)
- [ ] Documentação completa (em progresso)
- [ ] Code review e refactoring
- [ ] Release preparation

## Referências

- [Dockerfile Best Practices](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/)
- [Kaniko Documentation](https://github.com/GoogleContainerTools/kaniko)
- [Trivy Scanner](https://aquasecurity.github.io/trivy/)
- [Sigstore](https://www.sigstore.dev/)
- [SPDX Specification](https://spdx.dev/)
