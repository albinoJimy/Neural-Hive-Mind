# Mapeamento de Endpoints de Ferramentas MCP

Este documento descreve a arquitetura de configuração em 3 camadas para os 87 ferramentas do MCP Tool Catalog.

## Arquitetura de Configuração

### Camada 1: Configuração Estática (Bootstrap)
Metadados imutáveis definidos em `tool_catalog_bootstrap.py`:
- `cli_command`: Comando CLI para ferramentas de linha de comando
- `docker_image`: Imagem Docker para ferramentas containerizáveis
- `integration_type`: CLI, REST_API, LIBRARY, CONTAINER

### Camada 2: Configuração Dinâmica (ConfigMap)
Endpoints configuráveis via variáveis de ambiente:
- URLs de APIs REST
- Portas de serviço
- Configurações de timeout

### Camada 3: Credenciais Seguras (Secret)
Credenciais sensíveis separadas:
- API Keys
- Tokens de autenticação
- Credenciais OAuth2

## Mapeamento de Ferramentas por Categoria

### ANALYSIS Tools (12 ferramentas)

| Tool ID | Nome | Tipo | CLI Command | Docker Image | Endpoint Var | Credential Var |
|---------|------|------|-------------|--------------|--------------|----------------|
| sonarqube-001 | SonarQube | REST_API | - | - | SONARQUBE_URL | SONARQUBE_TOKEN |
| eslint-001 | ESLint | CLI | `eslint` | - | - | - |
| pylint-001 | Pylint | CLI | `pylint` | - | - | - |
| checkmarx-001 | Checkmarx | REST_API | - | - | CHECKMARX_URL | CHECKMARX_API_KEY |
| snyk-001 | Snyk | CLI | `snyk test` | - | - | SNYK_TOKEN |
| semgrep-001 | Semgrep | CLI | `semgrep` | - | - | - |
| trivy-001 | Trivy | CLI | `trivy` | aquasec/trivy:latest | - | - |
| veracode-001 | Veracode | REST_API | - | - | VERACODE_URL | VERACODE_API_ID, VERACODE_API_KEY |
| spotbugs-001 | SpotBugs | CLI | `spotbugs` | - | - | - |
| fortify-001 | Fortify | REST_API | - | - | FORTIFY_URL | FORTIFY_TOKEN |
| black-001 | Black | CLI | `black` | - | - | - |
| prettier-001 | Prettier | CLI | `prettier` | - | - | - |

### GENERATION Tools (15 ferramentas)

| Tool ID | Nome | Tipo | CLI Command | Docker Image | Endpoint Var | Credential Var |
|---------|------|------|-------------|--------------|--------------|----------------|
| github-copilot-001 | GitHub Copilot | REST_API | - | - | GITHUB_COPILOT_URL | GITHUB_TOKEN |
| codegen-001 | CodeGen | LIBRARY | - | - | - | - |
| swagger-codegen-001 | Swagger Codegen | CLI | `swagger-codegen` | - | - | - |
| openapi-generator-001 | OpenAPI Generator | CLI | `openapi-generator` | - | - | - |
| jooq-001 | jOOQ | LIBRARY | - | - | - | - |
| graphql-codegen-001 | GraphQL Code Generator | CLI | `graphql-codegen` | - | - | - |
| protobuf-001 | Protocol Buffers | CLI | `protoc` | - | - | - |
| thrift-001 | Apache Thrift | CLI | `thrift` | - | - | - |
| avro-001 | Apache Avro | CLI | `avro-tools` | - | - | - |
| spring-initializr-001 | Spring Initializr | REST_API | - | - | SPRING_INITIALIZR_URL | - |
| yeoman-001 | Yeoman | CLI | `yo` | - | - | - |
| cookiecutter-001 | Cookiecutter | CLI | `cookiecutter` | - | - | - |
| plop-001 | Plop | CLI | `plop` | - | - | - |
| nx-001 | Nx | CLI | `nx` | - | - | - |
| codex-001 | OpenAI Codex | REST_API | - | - | OPENAI_CODEX_URL | OPENAI_API_KEY |

### TRANSFORMATION Tools (15 ferramentas)

| Tool ID | Nome | Tipo | CLI Command | Docker Image | Endpoint Var | Credential Var |
|---------|------|------|-------------|--------------|--------------|----------------|
| babel-001 | Babel | CLI | `babel` | - | - | - |
| typescript-001 | TypeScript | CLI | `tsc` | - | - | - |
| webpack-001 | Webpack | CLI | `webpack` | - | - | - |
| rollup-001 | Rollup | CLI | `rollup` | - | - | - |
| esbuild-001 | esbuild | CLI | `esbuild` | - | - | - |
| vite-001 | Vite | CLI | `vite` | - | - | - |
| sass-001 | Sass | CLI | `sass` | - | - | - |
| less-001 | Less | CLI | `lessc` | - | - | - |
| postcss-001 | PostCSS | CLI | `postcss` | - | - | - |
| imagemin-001 | Imagemin | CLI | `imagemin` | - | - | - |
| sharp-001 | Sharp | LIBRARY | - | - | - | - |
| ffmpeg-001 | FFmpeg | CLI | `ffmpeg` | jrottenberg/ffmpeg:latest | - | - |
| handlebars-001 | Handlebars | CLI | `handlebars` | - | - | - |
| pug-001 | Pug | CLI | `pug` | - | - | - |
| markdown-001 | Markdown | LIBRARY | - | - | - | - |

### VALIDATION Tools (15 ferramentas)

| Tool ID | Nome | Tipo | CLI Command | Docker Image | Endpoint Var | Credential Var |
|---------|------|------|-------------|--------------|--------------|----------------|
| jest-001 | Jest | CLI | `jest` | - | - | - |
| mocha-001 | Mocha | CLI | `mocha` | - | - | - |
| pytest-001 | Pytest | CLI | `pytest` | - | - | - |
| junit-001 | JUnit | CLI | `mvn test` | - | - | - |
| cypress-001 | Cypress | CLI | `cypress` | cypress/included:latest | - | - |
| playwright-001 | Playwright | CLI | `playwright` | mcr.microsoft.com/playwright:latest | - | - |
| selenium-001 | Selenium | CONTAINER | - | selenium/standalone-chrome:latest | - | - |
| puppeteer-001 | Puppeteer | CLI | `puppeteer` | - | - | - |
| k6-001 | k6 | CLI | `k6` | grafana/k6:latest | - | - |
| jmeter-001 | JMeter | CLI | `jmeter` | justb4/jmeter:latest | - | - |
| locust-001 | Locust | CLI | `locust` | - | - | - |
| gatling-001 | Gatling | CLI | `gatling` | - | - | - |
| owasp-zap-001 | OWASP ZAP | CONTAINER | `zap-cli` | owasp/zap2docker-stable:latest | - | - |
| burp-suite-001 | Burp Suite | REST_API | - | - | BURP_SUITE_URL | BURP_SUITE_API_KEY |
| nuclei-001 | Nuclei | CLI | `nuclei` | - | - | - |

### AUTOMATION Tools (15 ferramentas)

| Tool ID | Nome | Tipo | CLI Command | Docker Image | Endpoint Var | Credential Var |
|---------|------|------|-------------|--------------|--------------|----------------|
| github-actions-001 | GitHub Actions | REST_API | `gh` | - | GITHUB_ACTIONS_URL | GITHUB_TOKEN |
| gitlab-ci-001 | GitLab CI | REST_API | `gitlab-runner` | - | GITLAB_CI_URL | GITLAB_TOKEN |
| jenkins-001 | Jenkins | REST_API | `jenkins-cli` | - | JENKINS_URL | JENKINS_TOKEN |
| circleci-001 | CircleCI | REST_API | `circleci` | - | CIRCLECI_URL | CIRCLECI_TOKEN |
| travis-001 | Travis CI | REST_API | `travis` | - | TRAVIS_CI_URL | TRAVIS_TOKEN |
| argocd-001 | ArgoCD | REST_API | `argocd` | - | ARGOCD_URL | ARGOCD_TOKEN |
| pulumi-001 | Pulumi | CLI | `pulumi` | - | - | PULUMI_ACCESS_TOKEN |
| flux-001 | Flux | CLI | `flux` | - | - | - |
| spinnaker-001 | Spinnaker | REST_API | - | - | - | - |
| tekton-001 | Tekton | CLI | `tkn` | - | - | - |
| ansible-001 | Ansible | CLI | `ansible` | - | - | - |
| terraform-001 | Terraform | CLI | `terraform` | hashicorp/terraform:latest | - | - |
| pulumi-001 | Pulumi | CLI | `pulumi` | - | - | - |
| chef-001 | Chef | CLI | `chef` | - | - | - |
| puppet-001 | Puppet | CLI | `puppet` | - | - | - |
| saltstack-001 | SaltStack | CLI | `salt` | - | - | - |

### INTEGRATION Tools (15 ferramentas)

| Tool ID | Nome | Tipo | CLI Command | Docker Image | Endpoint Var | Credential Var |
|---------|------|------|-------------|--------------|--------------|----------------|
| kafka-connect-001 | Kafka Connect | REST_API | - | - | KAFKA_CONNECT_URL | - |
| debezium-001 | Debezium | REST_API | - | - | - | - |
| nifi-001 | Apache NiFi | REST_API | - | - | - | - |
| airflow-001 | Apache Airflow | REST_API | `airflow` | - | AIRFLOW_URL | - |
| prefect-001 | Prefect | CLI | `prefect` | - | - | - |
| dagster-001 | Dagster | CLI | `dagster` | - | - | - |
| mulesoft-001 | MuleSoft | REST_API | - | - | MULESOFT_URL | MULESOFT_CLIENT_ID, MULESOFT_CLIENT_SECRET |
| talend-001 | Talend | REST_API | - | - | - | - |
| informatica-001 | Informatica | REST_API | - | - | - | - |
| aws-eventbridge-001 | AWS EventBridge | REST_API | `aws events` | - | AWS_EVENTBRIDGE_URL | AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY |
| azure-logic-apps-001 | Azure Logic Apps | REST_API | `az logic` | - | AZURE_LOGIC_APPS_URL | AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID |
| google-workflows-001 | Google Workflows | REST_API | `gcloud workflows` | - | GOOGLE_WORKFLOWS_URL | GOOGLE_CREDENTIALS_JSON |
| zapier-001 | Zapier | REST_API | - | - | - | - |
| ifttt-001 | IFTTT | REST_API | - | - | - | - |
| n8n-001 | n8n | REST_API | - | - | - | - |

## Configuração via Helm Values

### Endpoints (values.yaml)

```yaml
toolEndpoints:
  sonarqube:
    url: "http://sonarqube.neural-hive-tools.svc.cluster.local:9000/api"
    enabled: true
  checkmarx:
    url: "https://checkmarx.example.com/api"
    enabled: false
  # ... demais endpoints
```

### Credenciais (values.yaml)

```yaml
toolCredentials:
  sonarqubeToken: ""
  checkmarxApiKey: ""
  githubToken: ""
  # ... demais credenciais
```

## Variáveis de Ambiente

### ConfigMap (Endpoints)

| Variável | Descrição | Default |
|----------|-----------|---------|
| SONARQUBE_URL | SonarQube API endpoint | http://sonarqube:9000/api |
| CHECKMARX_URL | Checkmarx API endpoint | https://checkmarx.example.com/api |
| VERACODE_URL | Veracode API endpoint | https://analysiscenter.veracode.com/api |
| FORTIFY_URL | Fortify API endpoint | https://fortify.example.com/api |
| GITHUB_COPILOT_URL | GitHub Copilot API endpoint | https://api.github.com/copilot |
| SPRING_INITIALIZR_URL | Spring Initializr endpoint | https://start.spring.io |
| OPENAI_CODEX_URL | OpenAI Codex API endpoint | https://api.openai.com/v1 |
| BURP_SUITE_URL | Burp Suite API endpoint | http://burpsuite:8080 |
| GITHUB_ACTIONS_URL | GitHub Actions API endpoint | https://api.github.com |
| ARGOCD_URL | ArgoCD API endpoint | http://argocd-server:80/api |
| GITLAB_CI_URL | GitLab CI API endpoint | https://gitlab.com/api/v4 |
| JENKINS_URL | Jenkins API endpoint | http://jenkins:8080 |
| CIRCLECI_URL | CircleCI API endpoint | https://circleci.com/api/v2 |
| TRAVIS_CI_URL | Travis CI API endpoint | https://api.travis-ci.com |
| KAFKA_CONNECT_URL | Kafka Connect API endpoint | http://kafka-connect:8083 |
| AIRFLOW_URL | Apache Airflow API endpoint | http://airflow-webserver:8080/api/v1 |
| MULESOFT_URL | MuleSoft API endpoint | https://anypoint.mulesoft.com/api |
| AWS_EVENTBRIDGE_URL | AWS EventBridge endpoint | https://events.amazonaws.com |
| AZURE_LOGIC_APPS_URL | Azure Logic Apps endpoint | https://management.azure.com |
| GOOGLE_WORKFLOWS_URL | Google Workflows endpoint | https://workflowexecutions.googleapis.com |

### Secret (Credenciais)

| Variável | Descrição | Ferramentas |
|----------|-----------|-------------|
| SONARQUBE_TOKEN | Token de acesso SonarQube | sonarqube-001 |
| SNYK_TOKEN | Token de acesso Snyk | snyk-001 |
| CHECKMARX_API_KEY | API Key Checkmarx | checkmarx-001 |
| VERACODE_API_ID | Veracode API ID | veracode-001 |
| VERACODE_API_KEY | Veracode API Key | veracode-001 |
| FORTIFY_TOKEN | Token Fortify | fortify-001 |
| GITHUB_TOKEN | GitHub Personal Access Token | github-copilot-001, github-actions-001 |
| OPENAI_API_KEY | OpenAI API Key | openai-codex-001 |
| PULUMI_ACCESS_TOKEN | Pulumi Access Token | pulumi-001 |
| BURP_SUITE_API_KEY | Burp Suite API Key | burp-001 |
| GITLAB_TOKEN | GitLab Access Token | gitlab-ci-001 |
| JENKINS_TOKEN | Jenkins API Token | jenkins-001 |
| CIRCLECI_TOKEN | CircleCI API Token | circleci-001 |
| TRAVIS_TOKEN | Travis CI Token | travis-001 |
| ARGOCD_TOKEN | ArgoCD Token | argocd-001 |
| MULESOFT_CLIENT_ID | MuleSoft Client ID | mulesoft-001 |
| MULESOFT_CLIENT_SECRET | MuleSoft Client Secret | mulesoft-001 |
| AWS_ACCESS_KEY_ID | AWS Access Key | aws-eventbridge-001 |
| AWS_SECRET_ACCESS_KEY | AWS Secret Key | aws-eventbridge-001 |
| AZURE_CLIENT_ID | Azure Client ID | azure-logic-apps-001 |
| AZURE_CLIENT_SECRET | Azure Client Secret | azure-logic-apps-001 |
| AZURE_TENANT_ID | Azure Tenant ID | azure-logic-apps-001 |
| GOOGLE_CREDENTIALS_JSON | Google Service Account JSON | google-workflows-001 |

## Resumo de Estatísticas

| Categoria | Total | CLI | REST_API | LIBRARY | CONTAINER |
|-----------|-------|-----|----------|---------|-----------|
| ANALYSIS | 12 | 8 | 4 | 0 | 0 |
| GENERATION | 15 | 10 | 3 | 2 | 0 |
| TRANSFORMATION | 15 | 13 | 0 | 2 | 0 |
| VALIDATION | 15 | 10 | 1 | 0 | 4 |
| AUTOMATION | 15 | 8 | 7 | 0 | 0 |
| INTEGRATION | 15 | 3 | 12 | 0 | 0 |
| **TOTAL** | **87** | **52** | **27** | **4** | **4** |

### Docker Images Disponíveis

| Ferramenta | Imagem Docker |
|------------|---------------|
| Trivy | aquasec/trivy:latest |
| FFmpeg | jrottenberg/ffmpeg:latest |
| Cypress | cypress/included:latest |
| Playwright | mcr.microsoft.com/playwright:latest |
| Selenium | selenium/standalone-chrome:latest |
| k6 | grafana/k6:latest |
| JMeter | justb4/jmeter:latest |
| OWASP ZAP | owasp/zap2docker-stable:latest |
| Terraform | hashicorp/terraform:latest |
