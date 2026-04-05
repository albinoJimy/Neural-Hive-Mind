# Especificação Técnica - CI/CD Pipelines

> **Spec Parent:** `.agent-os/specs/2026-04-04-ci-cd-pipelines/spec.md`
> **Criado:** 2026-04-04
> **Status:** Planning

## Arquitetura de Workflows

### Estrutura de Diretórios

```
.github/
├── workflows/
│   ├── _templates/              # Templates reutilizáveis
│   │   ├── ci-template.yml      # Template principal de CI
│   │   ├── test-template.yml    # Template de testes
│   │   └── deploy-template.yml  # Template de deploy
│   ├── ci-core-services.yml     # CI para serviços core
│   ├── ci-agents.yml            # CI para agentes
│   ├── ci-mcp-servers.yml       # CI para servidores MCP
│   ├── ci-specialists.yml       # CI para especialistas
│   ├── ci-python-libraries.yml  # CI para bibliotecas
│   ├── deploy-staging.yml       # Deploy para staging
│   ├── deploy-production.yml    # Deploy para production
│   ├── rollback.yml             # Rollback de emergência
│   ├── security-scan.yml        # Scan de segurança
│   ├── python-linting.yml       # Linting Python
│   └── e2e-ci-cd.yml            # Testes E2E dos pipelines
├── scripts/
│   ├── deploy-staging.sh        # Script de deploy staging
│   ├── rollback.sh              # Script de rollback
│   ├── smoke-tests.sh           # Smoke tests pós-deploy
│   ├── timing-report.sh         # Relatório de timing
│   └── coverage-report.sh       # Relatório de coverage
└── _archive/                    # Workflows obsoletos arquivados
```

## Especificação dos Templates

### 1. CI Template (`_templates/ci-template.yml`)

**Inputs:**
```yaml
inputs:
  service_name:
    description: 'Nome do serviço'
    required: true
    type: string
  dockerfile_path:
    description: 'Caminho para Dockerfile'
    required: false
    type: string
    default: 'services/${{ inputs.service_name }}/Dockerfile'
  python_version:
    description: 'Versão Python'
    required: false
    type: string
    default: '3.12'
  run_tests:
    description: 'Executar testes'
    required: false
    type: boolean
    default: true
  run_security_scan:
    description: 'Executar scan de segurança'
    required: false
    type: boolean
    default: true
```

**Outputs:**
```yaml
outputs:
  image_tag:
    description: 'Tag da imagem buildada'
    value: ${{ jobs.build.outputs.image_tag }}
  tests_passed:
    description: 'Status dos testes'
    value: ${{ jobs.test.outputs.result }}
```

**Jobs:**

#### Job: detect-changes
```yaml
detect-changes:
  runs-on: ubuntu-latest
  outputs:
    should_build: ${{ steps.check.outputs.should_build }}
  steps:
    - name: Checkout
      uses: actions/checkout@v4
      with:
        fetch-depth: 0

    - name: Detect changes
      id: check
      run: |
        # Detecta se o serviço foi modificado
        CHANGED_FILES=$(git diff --name-only HEAD~1 HEAD)
        if echo "$CHANGED_FILES" | grep -q "services/${{ inputs.service_name }}/"; then
          echo "should_build=true" >> $GITHUB_OUTPUT
        else
          echo "should_build=false" >> $GITHUB_OUTPUT
        fi
```

#### Job: build
```yaml
build:
  needs: detect-changes
  if: needs.detect-changes.outputs.should_build == 'true'
  runs-on: ubuntu-latest
  permissions:
    contents: read
    packages: write
  outputs:
    image_tag: ${{ steps.meta.outputs.version }}
  steps:
    - name: Checkout
      uses: actions/checkout@v4

    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3

    - name: Login to GHCR
      uses: docker/login-action@v3
      with:
        registry: ghcr.io
        username: ${{ github.repository_owner }}
        password: ${{ secrets.GITHUB_TOKEN }}

    - name: Extract metadata
      id: meta
      uses: docker/metadata-action@v5
      with:
        images: ghcr.io/${{ github.repository_owner }}/neural-hive-mind/${{ inputs.service_name }}
        tags: |
          type=raw,value=latest
          type=sha,prefix=
          type=semver,pattern={{version}}

    - name: Build and push
      uses: docker/build-push-action@v5
      with:
        context: .
        file: ${{ inputs.dockerfile_path }}
        push: ${{ github.event_name != 'pull_request' }}
        tags: ${{ steps.meta.outputs.tags }}
        labels: ${{ steps.meta.outputs.labels }}
        cache-from: type=registry,ref=ghcr.io/${{ github.repository_owner }}/neural-hive-mind/${{ inputs.service_name }}:buildcache
        cache-to: type=registry,ref=ghcr.io/${{ github.repository_owner }}/neural-hive-mind/${{ inputs.service_name }}:buildcache,mode=max
```

#### Job: test
```yaml
test:
  needs: build
  if: inputs.run_tests == true
  runs-on: ubuntu-latest
  steps:
    - name: Checkout
      uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: ${{ inputs.python_version }}
        cache: 'pip'

    - name: Install dependencies
      run: |
        pip install pytest pytest-asyncio pytest-cov

    - name: Run tests
      run: |
        cd services/${{ inputs.service_name }}
        pytest tests/ --cov=src --cov-report=xml --cov-report=term

    - name: Upload coverage
      uses: codecov/codecov-action@v4
      with:
        files: ./coverage.xml
        flags: ${{ inputs.service_name }}
```

### 2. Test Template (`_templates/test-template.yml`)

**Inputs:**
```yaml
inputs:
  test_type:
    description: 'Tipo de teste (unit, integration, e2e)'
    required: true
    type: string
  python_versions:
    description: 'Versões Python para testar'
    required: false
    type: string
    default: '[ "3.11", "3.12" ]'
  coverage_threshold:
    description: 'Threshold mínimo de coverage'
    required: false
    type: number
    default: 70
```

### 3. Deploy Template (`_templates/deploy-template.yml`)

**Inputs:**
```yaml
inputs:
  environment:
    description: 'Ambiente de deploy'
    required: true
    type: choice
    options:
      - staging
      - production
  services:
    description: 'Lista de serviços para deploy'
    required: true
    type: string
  image_tag:
    description: 'Tag da imagem'
    required: false
    type: string
    default: 'latest'
  dry_run:
    description: 'Simular deploy'
    required: false
    type: boolean
    default: false
```

## Configuração de Ambientes

### Staging (develop branch)
```yaml
environment:
  name: staging
  url: https://staging.neural-hive-mind.com
  variables:
    NAMESPACE: neural-hive-staging
    CLUSTER: staging-cluster
    REGISTRY: ghcr.io/albinojimy/neural-hive-mind
```

### Production (main branch)
```yaml
environment:
  name: production
  url: https://neural-hive-mind.com
  variables:
    NAMESPACE: neural-hive-prod
    CLUSTER: prod-cluster
    REGISTRY: ghcr.io/albinojimy/neural-hive-mind
```

## Estratégia de Deploy

### Blue-Green Deployment
```yaml
# Para serviços críticos
strategy:
  type: blue-green
  steps:
    1. Deploy new version (green)
    2. Run smoke tests on green
    3. Switch traffic to green
    4. Keep blue for rollback
    5. Delete blue after success
```

### Canary Deployment (opcional)
```yaml
# Para baixo risco
strategy:
  type: canary
  steps:
    1. Deploy to 10% of pods
    2. Monitor metrics
    3. Gradually increase to 100%
```

## Smoke Tests

```bash
#!/bin/bash
# .github/scripts/smoke-tests.sh

set -e

SERVICE=${1}
NAMESPACE=${2}
BASE_URL="https://${NAMESPACE}.neural-hive-mind.com"

echo "Running smoke tests for ${SERVICE}..."

# Health check
echo "1. Health check..."
curl -f "${BASE_URL}/${SERVICE}/health" || exit 1

# Metrics endpoint
echo "2. Metrics endpoint..."
curl -f "${BASE_URL}/${SERVICE}/metrics" || exit 1

# Readiness probe
echo "3. Readiness probe..."
kubectl get pod -n ${NAMESPACE} -l app=${SERVICE} -o json | \
  jq '.items[].status.conditions[] | select(.type=="Ready") | .status' | \
  grep -q "True"

echo "✅ Smoke tests passed!"
```

## Variáveis de Ambiente Necessárias

### GitHub Secrets
```yaml
# Registry
CR_PAT: "Personal Access Token para GHCR"

# Kubernetes
KUBECONFIG_STAGING: "Base64 encoded kubeconfig for staging"
KUBECONFIG_PROD: "Base64 encoded kubeconfig for production"

# Notificações
SLACK_WEBHOOK_URL: "Webhook URL para Slack"
TEAMS_WEBHOOK_URL: "Webhook URL para Teams"

# Codecov
CODECOV_TOKEN: "Token para Codecov"

# Segurança
SNYK_TOKEN: "Token para Snyk (opcional)"
SONAR_TOKEN: "Token para SonarQube (opcional)"
```

## Matriz de Serviços

### Serviços Core (8)
| Serviço | Porta | Helm Chart | Criticalidade |
|---------|-------|------------|---------------|
| gateway-intencoes | 8000 | ✓ | Alta |
| semantic-translation-engine | 8001 | ✓ | Alta |
| consensus-engine | 8002 | ✓ | Alta |
| orchestrator-dynamic | 8003 | ✓ | Alta |
| approval-service | 8004 | ✓ | Alta |
| worker-agents | 8005 | ✓ | Alta |
| queen-agent | 8006 | ✓ | Alta |
| service-registry | 8007 | ✓ | Alta |

### Agentes (8)
| Serviço | Porta | Helm Chart |
|---------|-------|------------|
| analyst-agents | 8010 | ✓ |
| scout-agents | 8011 | ✓ |
| guard-agents | 8012 | ✓ |
| optimizer-agents | 8013 | ✓ |
| self-healing-engine | 8014 | ✓ |
| code-forge | 8015 | ✓ |
| architect-agent | 8016 | ✓ |
| mcp-tool-catalog | 8017 | ✓ |

### Servidores MCP (13)
| Servidor | Descrição |
|---------|-----------|
| ai-codegen-mcp-server | Geração de código |
| sonarqube-mcp-server | Análise estática |
| trivy-mcp-server | Segurança |
| scout-mcp-server | Exploração |
| optimizer-mcp-server | Otimização |
| + 8 outros | ... |

## Métricas e SLAs

### Build Time SLAs
| Tipo | Target | Max |
|------|--------|-----|
| Build unitário | < 5 min | 10 min |
| Build incremental (1-5 serviços) | < 10 min | 15 min |
| Build completo (todos serviços) | < 30 min | 45 min |

### Deploy Time SLAs
| Ambiente | Target | Max |
|----------|--------|-----|
| Staging | < 5 min | 10 min |
| Production | < 15 min | 30 min |
| Rollback | < 2 min | 5 min |

### Quality Gates
| Métrica | Threshold | Action |
|---------|-----------|--------|
| Coverage | < 70% | Falhar |
| Critical vulnerabilities | > 0 | Falhar |
| High vulnerabilities | > 5 | Aviso |
| Linting errors | > 0 | Falhar |

---

*Especificação Técnica criada por Claude Code - 2026-04-04*
