# Diagramas de Sequência - CodeForge

## Visão Geral

Este documento contém diagramas de sequência Mermaid que ilustram os principais fluxos do CodeForge.

## Índice

1. [Fluxo Principal do Pipeline](#fluxo-principal-do-pipeline)
2. [Geração de Dockerfile](#geração-de-dockerfile)
3. [Build de Container](#build-de-container)
4. [Validação de Segurança](#validação-de-segurança)
5. [Fluxo de Aprovação](#fluxo-de-aprovação)
6. [Tratamento de Erros](#tratamento-de-erros)
7. [Build com Kaniko](#build-com-kaniko)
8. [Persistência de Artefatos](#persistência-de-artefatos)

---

## Fluxo Principal do Pipeline

```mermaid
sequenceDiagram
    actor User as Usuário
    participant PE as PipelineEngine
    participant TS as TemplateSelector
    participant CC as CodeComposer
    participant DG as DockerfileGenerator
    participant CB as ContainerBuilder
    participant V as Validator
    participant P as Packager
    participant AC as ApprovalClient

    User->>PE: execute_pipeline(ticket)

    Note over PE: Stage 1: Template Selection
    PE->>TS: select_template(ticket.parameters)
    TS-->>PE: template_id

    Note over PE: Stage 2: Code Composition
    PE->>CC: compose_code(ticket, template)
    CC-->>PE: generated_code

    Note over PE: Stage 3: Dockerfile Generation
    PE->>DG: generate_dockerfile(language, framework)
    DG-->>PE: dockerfile_content

    Note over PE: Stage 4: Container Build
    alt enable_container_build=True
        PE->>CB: build_container(dockerfile, context)
        CB->>CB: docker build ...
        CB-->>PE: ContainerBuildResult
    else enable_container_build=False
        PE->>PE: Skip build (mock)
    end

    Note over PE: Stage 5: Validation
    PE->>V: validate_all(artifact_path)
    V->>V: Trivy scan
    V->>V: SonarQube analysis
    V-->>PE: ValidationResult

    Note over PE: Stage 6: Testing
    PE->>PE: Run tests (if configured)
    PE-->>PE: TestResult

    Note over PE: Stage 7: Packaging
    PE->>P: package_artifact(artifact)
    P->>P: Generate SBOM
    P->>P: Sign artifact
    P-->>PE: packaged_artifact

    Note over PE: Stage 8: Approval Gate
    alt confidence >= threshold
        PE->>PE: Auto-approve
    else confidence < threshold
        PE->>AC: request_approval(pipeline_id)
        AC-->>PE: REQUIRES_REVIEW
    end

    PE-->>User: PipelineResult
```

---

## Geração de Dockerfile

```mermaid
sequenceDiagram
    participant Client as Cliente
    participant DG as DockerfileGenerator
    participant Template as Template Engine

    Client->>DG: generate_dockerfile(language, framework, artifact_type)

    alt custom_template provided
        DG->>DG: Use custom template
    else language supported
        DG->>Template: _get_{language}_template()

        alt framework specified
            Template->>Template: Apply framework-specific optimizations
        end

        alt artifact_type = LAMBDA_FUNCTION
            Template->>Template: Use Lambda runtime base
            Template->>Template: Remove EXPOSE, use CMD with Lambda handler
        else artifact_type = CLI_TOOL
            Template->>Template: Use ENTRYPOINT, minimal base
        else artifact_type = MICROSERVICE
            Template->>Template: Add HEALTHCHECK, EXPOSE port
        end

        Template-->>DG: dockerfile_content
    else language not supported
        DG-->>Client: ValueError("Linguagem não suportada")
    end

    DG-->>Client: str (Dockerfile content)
```

---

## Build de Container

```mermaid
sequenceDiagram
    participant Client as Cliente
    participant CB as ContainerBuilder
    participant Docker as Docker CLI
    participant Registry as Docker Registry

    Client->>CB: build_container(dockerfile_path, context, tag)

    CB->>CB: Validate inputs
    CB->>CB: Check dockerfile exists
    CB->>CB: Check context directory exists

    alt builder_type = DOCKER
        CB->>Docker: docker build command
        Note over Docker: Build image with<br/>multi-stage optimization

        Docker-->>CB: Build output stream

        alt build successful
            Docker-->>CB: Image ID + SHA256 digest
            CB->>CB: Extract image size
            CB->>CB: Calculate duration
        else build timeout
            CB-->>CB: TimeoutError
            CB-->>Client: ContainerBuildResult(success=False)
        else build failed
            Docker-->>CB: Error message
            CB-->>Client: ContainerBuildResult(success=False, error)
        end
    else builder_type = KANIKO
        CB->>CB: NotImplementedError
        CB-->>Client: Error("Kaniko not implemented yet")
    end

    CB-->>Client: ContainerBuildResult(success, digest, size, duration)
```

---

## Validação de Segurança

```mermaid
sequenceDiagram
    participant PE as PipelineEngine
    participant V as Validator
    participant Trivy as TrivyClient
    participant Sonar as SonarQubeClient
    participant Snyk as SnykClient (opcional)

    PE->>V: validate_all(artifact_path)

    par Vulnerability Scan
        PE->>Trivy: scan_filesystem(path)
        Trivy->>Trivy: Execute trivy fs
        Trivy-->>PE: ValidationResult(critical_count, high_count, ...)
    and Code Quality
        PE->>Sonar: scan_code(path)
        Sonar->>Sonar: Execute sonar-scanner
        Sonar-->>PE: ValidationResult(bugs, coverage, ...)
    and Snyk Scan (opcional)
        PE->>Snyk: scan_dependencies(path)
        Snyk->>Snyk: Execute snyk test
        Snyk-->>PE: ValidationResult(vulnerabilities, ...)
    end

    alt critical_count > 0
        PE->>PE: Mark as FAILED
    else critical_count = 0 and high_count < threshold
        PE->>PE: Mark as COMPLETED
    else high_count >= threshold
        PE->>PE: Mark as REQUIRES_REVIEW
    end

    V-->>PE: dict[str, ValidationResult]
```

---

## Fluxo de Aprovação

```mermaid
sequenceDiagram
    participant PE as PipelineEngine
    participant AC as ApprovalClient
    participant DB as PostgreSQL
    participant User as Approver

    PE->>PE: Calculate confidence score

    alt confidence >= auto_approval_threshold
        PE->>PE: Auto-approve
        PE->>DB: save_pipeline(status=COMPLETED)
        PE-->>PE: PipelineResult(status=COMPLETED)
    else confidence < auto_approval_threshold
        PE->>AC: create_approval_request(pipeline_id, artifacts)
        AC->>DB: insert approval_request
        DB-->>AC: approval_id

        PE->>DB: save_pipeline(status=REQUIRES_REVIEW)
        PE-->>PE: PipelineResult(status=REQUIRES_REVIEW)

        Note over User: Waiting for manual approval
        User->>AC: review_approval(approval_id, approved=True)
        AC->>DB: update_approval_request(status=APPROVED)
        DB-->>AC: OK

        AC->>PE: approval_response(approval_id, approved=True)
        PE->>PE: Resume pipeline
        PE->>DB: save_pipeline(status=COMPLETED)
    end
```

---

## Tratamento de Erros

```mermaid
sequenceDiagram
    participant PE as PipelineEngine
    participant Stage as Stage Executor
    participant Logger as Structlog
    participant DB as PostgreSQL

    PE->>Stage: execute_stage(stage_name, ticket)

    alt Stage success
        Stage-->>PE: StageResult(success=True)
        PE->>Logger: info("stage_completed", stage_name)
    else Stage fails with retryable error
        Stage-->>PE: StageResult(success=False, error=retryable)
        PE->>PE: Increment retry counter
        alt retry_count < max_retries
            PE->>Stage: execute_stage (retry)
            Note over PE: Exponential backoff
        else retry_count >= max_retries
            PE->>Logger: error("stage_failed_retries_exhausted")
            PE->>DB: save_pipeline(status=FAILED)
            PE-->>PE: PipelineResult(status=FAILED)
        end
    else Stage fails with non-retryable error
        Stage-->>PE: StageResult(success=False, error=critical)
        PE->>Logger: error("stage_failed_critical", error_message)
        PE->>DB: save_pipeline(status=FAILED)
        PE-->>PE: PipelineResult(status=FAILED, error_message)
    end

    alt fault_tolerance_enabled
        PE->>PE: Continue to next stage (if non-blocking)
    else fault_tolerance_disabled
        PE->>PE: Stop pipeline
    end
```

---

## Build com Kaniko (Futuro)

```mermaid
sequenceDiagram
    participant Client as Cliente
    participant CB as ContainerBuilder
    participant K8s as Kubernetes
    participant Kaniko as Kaniko Pod
    participant Registry as Container Registry

    Note over CB,Registry: FUTURE IMPLEMENTATION

    Client->>CB: build_container(dockerfile, context, tag, builder_type=KANIKO)

    CB->>K8s: Create Kaniko pod
    CB->>Kaniko: Wait for pod ready

    Kaniko->>Registry: Pull base image
    Kaniko->>Kaniko: Execute build steps
    Kaniko->>Registry: Push built image

    Registry-->>Kaniko: SHA256 digest

    Kaniko-->>CB: Build result
    CB->>K8s: Delete Kaniko pod

    CB-->>Client: ContainerBuildResult(success, digest)
```

---

## Persistência de Artefatos

```mermaid
sequenceDiagram
    participant PE as PipelineEngine
    participant Mongo as MongoDB
    participant PG as PostgreSQL
    participant S3 as S3 Storage
    participant AR as Artifact Registry

    PE->>PE: Generate artifact_id

    par Save code content
        PE->>Mongo: save_artifact_content(artifact_id, code)
        Mongo-->>PE: content_uri
    and Save metadata
        PE->>PG: save_artifact_metadata(artifact_id, metadata)
        PG-->>PE: artifact_record
    end

    alt Container build successful
        PE->>AR: register_container(artifact_id, image_tag, digest)
        AR-->>PE: registered=True
    end

    PE->>S3: upload_sbom(artifact_id, sbom_content)
    S3-->>PE: sbom_uri

    PE->>PG: update_artifact(artifact_id, sbom_uri, container_info)
    PG-->>PE: updated_record

    PE-->>PE: CodeForgeArtifact(artifact_id, content_uri, metadata)
```

---

## Fluxo de Recuperação (Fault Tolerance)

```mermaid
sequenceDiagram
    participant Client as Cliente
    participant PE as PipelineEngine
    participant Cache as Redis Cache
    participant DB as PostgreSQL
    participant CB as ContainerBuilder

    Client->>PE: execute_pipeline(ticket)

    PE->>Cache: check_cached_result(ticket_id)

    alt Cache hit
        Cache-->>PE: Cached PipelineResult
        PE-->>Client: Cached result (fast path)
    else Cache miss
        PE->>DB: get_pipeline(ticket_id)

        alt Pipeline exists and incomplete
            DB-->>PE: Partial PipelineResult
            PE->>PE: Determine last completed stage
            PE->>PE: Resume from next stage
            Note over PE: Recovery mode
        else Pipeline doesn't exist or completed
            PE->>PE: Start fresh execution
        end

        Note over PE: Execute stages...

        alt Stage fails
            PE->>DB: save_pipeline(status=FAILED, failed_stage)
            PE->>Cache: cache_error(ticket_id, error)
            PE-->>Client: PipelineResult(status=FAILED)
        else All stages complete
            PE->>DB: save_pipeline(status=COMPLETED)
            PE->>Cache: cache_result(ticket_id, result)
            PE-->>Client: PipelineResult(status=COMPLETED)
        end
    end
```

---

## Fluxo de Testes E2E

```mermaid
sequenceDiagram
    participant Test as Test Suite
    participant PE as PipelineEngine
    participant MockTC as MockTicketClient
    participant MockAC as MockApprovalClient
    participant MockBC as MockBuildClient

    Test->>PE: __init__(enable_container_build=False)

    Test->>MockTC: configure_mock_responses()
    MockTC-->>Test: configured

    Test->>PE: execute_pipeline(ticket)

    PE->>MockTC: get_template()
    MockTC-->>PE: template

    PE->>MockTC: generate_code()
    MockTC-->>PE: generated_code

    PE->>PE: generate_dockerfile()
    PE->>MockBC: build_container()
    MockBC-->>PE: mock_result(success=True)

    PE->>MockAC: request_approval()
    MockAC-->>PE: approved(auto=True)

    PE-->>Test: PipelineResult(status=COMPLETED)

    Test->>Test: assert result.status == "COMPLETED"
    Test->>Test: assert len(result.artifacts) > 0
```

---

## Legenda de Componentes

| Abreviação | Componente |
|------------|------------|
| `PE` | PipelineEngine |
| `DG` | DockerfileGenerator |
| `CB` | ContainerBuilder |
| `V` | Validator |
| `P` | Packager |
| `AC` | ApprovalClient |
| `TS` | TemplateSelector |
| `CC` | CodeComposer |
| `DB` | PostgreSQL (metadados) |
| `Mongo` | MongoDB (código) |
| `S3` | S3 Storage (SBOMs) |
| `AR` | Artifact Registry |

## Convenções Visuais

- **Seta sólida (`->`)**: Chamada síncrona
- **Seta tracejada (`-->`)**: Retorno de valor
- **Retângulo tracejado**: Atividade assíncrona/processamento
- **Nota (`Note over`)**: Comentário ou contexto adicional
- **Alt/Opt**: Branch condicional

---

## Referências

- [Architecture](architecture.md)
- [API Reference](api-reference.md)
- [Examples](examples.md)
- [Troubleshooting](troubleshooting.md)
