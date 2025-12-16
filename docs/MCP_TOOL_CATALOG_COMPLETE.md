# MCP Tool Catalog - Catálogo Completo de Ferramentas

## Visão Geral

Catálogo de **87 ferramentas** distribuídas em **6 categorias** para seleção inteligente via algoritmo genético.

## Categorias

### 1. ANALYSIS (15 ferramentas)

Ferramentas de análise estática, segurança e qualidade de código.

| Tool ID | Nome | Integration Type | Capabilities | Reputation | Cost | Avg Time |
|---------|------|------------------|--------------|------------|------|----------|
| sonarqube-001 | SonarQube | REST_API | code_quality, security_scan, bugs | 0.92 | 0.7 | 45s |
| trivy-001 | Trivy | CLI | vulnerability_scan, container_scan | 0.92 | 0.1 | 15s |
| snyk-001 | Snyk | REST_API | vulnerability_scan, license_check | 0.90 | 0.8 | 30s |
| semgrep-001 | Semgrep | CLI | sast, pattern_matching | 0.88 | 0.1 | 20s |
| eslint-001 | ESLint | CLI | javascript_lint, code_quality | 0.87 | 0.1 | 8s |
| pylint-001 | Pylint | CLI | python_lint, code_quality | 0.86 | 0.1 | 10s |
| bandit-001 | Bandit | CLI | python_security, sast | 0.85 | 0.1 | 12s |
| codeql-001 | CodeQL | CLI | sast, semantic_analysis | 0.91 | 0.5 | 60s |
| owasp-dep-check-001 | OWASP Dependency-Check | CLI | dependency_scan, vulnerabilities | 0.84 | 0.1 | 40s |
| checkmarx-001 | Checkmarx | REST_API | sast, compliance | 0.88 | 0.9 | 60s |
| veracode-001 | Veracode | REST_API | sast, dast, compliance | 0.87 | 0.95 | 90s |
| fortify-001 | Fortify | REST_API | sast, security_scan | 0.86 | 0.9 | 75s |
| pmd-001 | PMD | CLI | static_analysis, java | 0.82 | 0.1 | 15s |
| spotbugs-001 | SpotBugs | CLI | bug_detection, java | 0.81 | 0.1 | 20s |
| clang-analyzer-001 | Clang Static Analyzer | CLI | static_analysis, c, cpp | 0.85 | 0.1 | 25s |

**Uso Recomendado**: Selecionar 1-2 ferramentas ANALYSIS por pipeline (ex: Trivy + SonarQube).

### 2. GENERATION (20 ferramentas)

Ferramentas de geração de código, scaffolding e IaC.

| Tool ID | Nome | Integration Type | Capabilities | Reputation | Cost | Avg Time |
|---------|------|------------------|--------------|------------|------|----------|
| github-copilot-001 | GitHub Copilot | LIBRARY | ai_code_generation, autocomplete | 0.95 | 0.8 | 2s |
| openapi-generator-001 | OpenAPI Generator | CLI | api_client_generation, server_stubs | 0.89 | 0.1 | 15s |
| terraform-cdk-001 | Terraform CDK | CLI | iac, terraform | 0.87 | 0.1 | 20s |
| cookiecutter-001 | Cookiecutter | CLI | project_templates, scaffolding | 0.83 | 0.1 | 10s |
| tabnine-001 | Tabnine | LIBRARY | code_completion, ai_assisted | 0.88 | 0.6 | 0.5s |
| swagger-codegen-001 | Swagger Codegen | CLI | api_client_generation, openapi | 0.85 | 0.1 | 10s |
| yeoman-001 | Yeoman | CLI | scaffolding, project_generator | 0.79 | 0.1 | 15s |
| jhipster-001 | JHipster | CLI | full_stack_generator, spring_boot | 0.86 | 0.1 | 60s |
| spring-initializr-001 | Spring Initializr | REST_API | spring_boot_generator | 0.91 | 0.1 | 5s |
| create-react-app-001 | Create React App | CLI | react_scaffolding | 0.89 | 0.1 | 30s |
| vue-cli-001 | Vue CLI | CLI | vue_scaffolding | 0.87 | 0.1 | 25s |
| angular-cli-001 | Angular CLI | CLI | angular_scaffolding | 0.88 | 0.1 | 35s |
| pulumi-001 | Pulumi | CLI | iac, multi_cloud | 0.84 | 0.2 | 20s |
| aws-cdk-001 | AWS CDK | CLI | iac, aws | 0.86 | 0.1 | 30s |
| serverless-001 | Serverless Framework | CLI | serverless, lambda | 0.85 | 0.1 | 25s |
| helm-generator-001 | Helm Chart Generator | CLI | helm_chart_generation, kubernetes | 0.81 | 0.1 | 5s |
| dockerfile-gen-001 | Dockerfile Generator | LIBRARY | dockerfile_generation | 0.76 | 0.1 | 2s |
| pytest-gen-001 | Pytest Test Generator | LIBRARY | test_generation, python | 0.74 | 0.1 | 3s |
| jest-gen-001 | Jest Test Generator | LIBRARY | test_generation, javascript | 0.75 | 0.1 | 3s |
| openai-codex-001 | OpenAI Codex | REST_API | ai_code_generation | 0.94 | 0.9 | 5s |

**Uso Recomendado**: Combinar AI tools (Copilot/Codex) com scaffolding tools (Cookiecutter/Yeoman).

### 3. TRANSFORMATION (18 ferramentas)

Ferramentas de formatação, transpiling, bundling e migração.

| Tool ID | Nome | Integration Type | Capabilities | Reputation | Cost | Avg Time |
|---------|------|------------------|--------------|------------|------|----------|
| prettier-001 | Prettier | CLI | code_formatting, javascript | 0.91 | 0.1 | 3s |
| black-001 | Black | CLI | code_formatting, python | 0.90 | 0.1 | 4s |
| terraform-fmt-001 | Terraform fmt | CLI | terraform_formatting | 0.88 | 0.1 | 2s |
| babel-001 | Babel | CLI | transpiling, javascript | 0.91 | 0.1 | 8s |
| tsc-001 | TypeScript Compiler | CLI | transpiling, typescript | 0.93 | 0.1 | 12s |
| webpack-001 | Webpack | CLI | bundling, javascript | 0.89 | 0.1 | 20s |
| rollup-001 | Rollup | CLI | bundling, tree_shaking | 0.86 | 0.1 | 15s |
| parcel-001 | Parcel | CLI | bundling, zero_config | 0.84 | 0.1 | 10s |
| ansible-lint-001 | Ansible Lint | CLI | ansible_validation | 0.82 | 0.1 | 5s |
| kustomize-001 | Kustomize | CLI | kubernetes_manifest_transformation | 0.85 | 0.1 | 3s |
| openapi-transformer-001 | OpenAPI Transformer | LIBRARY | openapi_transformation | 0.77 | 0.1 | 2s |
| graphql-stitching-001 | GraphQL Schema Stitching | LIBRARY | graphql_schema_merge | 0.79 | 0.1 | 4s |
| flyway-001 | Flyway | CLI | database_migration, sql | 0.88 | 0.3 | 10s |
| liquibase-001 | Liquibase | CLI | database_migration, xml | 0.87 | 0.3 | 12s |
| uglifyjs-001 | UglifyJS | CLI | minification, javascript | 0.83 | 0.1 | 6s |
| terser-001 | Terser | CLI | minification, es6 | 0.85 | 0.1 | 7s |
| docker-compose-converter-001 | Docker Compose Converter | LIBRARY | docker_compose_transformation | 0.78 | 0.1 | 3s |
| refactoring-tools-001 | Refactoring Tools | LIBRARY | code_refactoring | 0.80 | 0.1 | 8s |

**Uso Recomendado**: Aplicar formatação (Prettier/Black) antes de validação.

### 4. VALIDATION (12 ferramentas)

Ferramentas de testes, validação de políticas e segurança.

| Tool ID | Nome | Integration Type | Capabilities | Reputation | Cost | Avg Time |
|---------|------|------------------|--------------|------------|------|----------|
| pytest-001 | Pytest | CLI | unit_testing, python | 0.92 | 0.1 | 5s |
| jest-001 | Jest | CLI | unit_testing, javascript | 0.91 | 0.1 | 6s |
| checkov-001 | Checkov | CLI | iac_validation, policy_as_code | 0.89 | 0.1 | 10s |
| junit-001 | JUnit | LIBRARY | unit_testing, java | 0.92 | 0.1 | 8s |
| selenium-001 | Selenium | LIBRARY | e2e_testing, browser_automation | 0.89 | 0.1 | 30s |
| cypress-001 | Cypress | CLI | e2e_testing, javascript | 0.91 | 0.1 | 25s |
| newman-001 | Postman Newman | CLI | api_testing | 0.86 | 0.1 | 10s |
| k6-001 | K6 | CLI | load_testing, performance | 0.87 | 0.1 | 60s |
| locust-001 | Locust | CLI | load_testing, python | 0.84 | 0.1 | 45s |
| owasp-zap-001 | OWASP ZAP | CONTAINER | penetration_testing, security | 0.88 | 0.1 | 90s |
| burp-001 | Burp Suite | REST_API | penetration_testing, security | 0.90 | 0.95 | 120s |
| conftest-001 | Conftest | CLI | policy_validation, opa | 0.85 | 0.1 | 3s |

**Uso Recomendado**: Combinar unit tests (Pytest/Jest) com security validation (Checkov/OWASP ZAP).

### 5. AUTOMATION (12 ferramentas)

Ferramentas de CI/CD, GitOps e automação de infraestrutura.

| Tool ID | Nome | Integration Type | Capabilities | Reputation | Cost | Avg Time |
|---------|------|------------------|--------------|------------|------|----------|
| github-actions-001 | GitHub Actions | REST_API | ci_cd, github | 0.93 | 0.2 | 180s |
| argocd-001 | ArgoCD | REST_API | gitops, kubernetes | 0.91 | 0.1 | 30s |
| gitlab-ci-001 | GitLab CI | REST_API | ci_cd, gitlab | 0.88 | 0.1 | 180s |
| jenkins-001 | Jenkins | REST_API | ci_cd, automation | 0.85 | 0.1 | 120s |
| circleci-001 | CircleCI | REST_API | ci_cd | 0.87 | 0.5 | 150s |
| travis-001 | Travis CI | REST_API | ci_cd | 0.82 | 0.4 | 140s |
| flux-001 | Flux | CLI | gitops, kubernetes | 0.86 | 0.1 | 15s |
| tekton-001 | Tekton | LIBRARY | kubernetes_native_ci_cd | 0.83 | 0.1 | 90s |
| ansible-001 | Ansible | CLI | configuration_management | 0.89 | 0.1 | 60s |
| terraform-001 | Terraform | CLI | iac, multi_cloud | 0.92 | 0.1 | 45s |
| k8s-operators-001 | Kubernetes Operators | LIBRARY | automation, kubernetes | 0.84 | 0.1 | 30s |
| helm-001 | Helm | CLI | kubernetes_package_manager | 0.90 | 0.1 | 10s |

**Uso Recomendado**: Usar ArgoCD/Flux para deployments, GitHub Actions para CI.

### 6. INTEGRATION (10 ferramentas)

Ferramentas de integração de dados, workflows e APIs.

| Tool ID | Nome | Integration Type | Capabilities | Reputation | Cost | Avg Time |
|---------|------|------------------|--------------|------------|------|----------|
| kafka-connect-001 | Kafka Connect | REST_API | data_streaming, integration | 0.90 | 0.2 | 20s |
| airflow-001 | Airflow | REST_API | workflow_orchestration, etl | 0.89 | 0.3 | 60s |
| apache-camel-001 | Apache Camel | LIBRARY | integration_patterns, eip | 0.87 | 0.1 | 15s |
| mulesoft-001 | MuleSoft | REST_API | api_integration, esb | 0.86 | 0.95 | 45s |
| zapier-001 | Zapier | REST_API | workflow_automation, saas | 0.84 | 0.7 | 10s |
| ifttt-001 | IFTTT | REST_API | automation, triggers | 0.81 | 0.5 | 8s |
| aws-eventbridge-001 | AWS EventBridge | REST_API | event_routing, aws | 0.88 | 0.3 | 5s |
| azure-logic-apps-001 | Azure Logic Apps | REST_API | workflow_automation, azure | 0.85 | 0.6 | 30s |
| google-workflows-001 | Google Cloud Workflows | REST_API | workflow_orchestration, gcp | 0.83 | 0.4 | 25s |
| prefect-001 | Prefect | REST_API | workflow_orchestration, python | 0.86 | 0.2 | 40s |

**Uso Recomendado**: Usar Kafka Connect para streaming, Airflow para ETL.

## Algoritmo Genético

### Fitness Function

```
fitness = (reputation × 0.4) + ((1 - cost) × 0.3) + (diversity × 0.2) + ((1 - time) × 0.1)
```

### Parâmetros

- **Population Size**: 50
- **Max Generations**: 100
- **Crossover Probability**: 0.7
- **Mutation Probability**: 0.2
- **Tournament Size**: 3
- **Convergence Threshold**: 0.01
- **Timeout**: 30s

### Exemplo de Seleção

**Request**:

```json
{
  "required_categories": ["GENERATION", "VALIDATION"],
  "constraints": {
    "max_cost_score": 0.5,
    "min_reputation_score": 0.8
  }
}
```

**Response** (após 15 gerações, fitness=0.89):
- GitHub Copilot (GENERATION) - fitness: 0.92
- Pytest (VALIDATION) - fitness: 0.86

## Guias de Uso

### Seleção via REST API

```bash
curl -X POST http://mcp-tool-catalog:8080/api/v1/selections \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "req-001",
    "artifact_type": "CODE",
    "language": "python",
    "required_categories": ["ANALYSIS", "VALIDATION"],
    "constraints": {"max_cost_score": 0.3}
  }'
```

### Seleção via Kafka

Publicar em `mcp.tool.selection.requests`, consumir de `mcp.tool.selection.responses`.

### Feedback Loop

```bash
curl -X POST http://mcp-tool-catalog:8080/api/v1/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "tool_id": "trivy-001",
    "success": true,
    "execution_time_ms": 12000
  }'
```

## Métricas e Observabilidade

- **Dashboard Grafana**: `observability/grafana/dashboards/mcp-tool-catalog.json`
- **Alertas Prometheus**: `observability/prometheus/alerts/mcp-tool-catalog-alerts.yaml`
- **Métricas Endpoint**: `http://mcp-tool-catalog:9091/metrics`

## Referências

- [Tool Adapters Guide](../services/mcp-tool-catalog/TOOL_ADAPTERS_GUIDE.md)
- [Code Forge Integration](../services/code-forge/INTEGRATION_MCP.md)
- [Phase 2 Implementation Status](../PHASE2_IMPLEMENTATION_STATUS.md)
