# G6-G8: Detalhamento Completo de Code Generation, Build e Deploy

**Data:** 2026-04-23
**Tipo:** Especificação Técnica Detalhada
**Âmbito:** Integração Code-Forge no Fluxo G

---

## Resumo Executivo

O serviço `code-forge` já **existe e é funcional**, com 8 stages de pipeline implementados. Porém, ele **NÃO está integrado** no Fluxo G do orchestrator-dynamic.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ESTADO ATUAL                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  code-forge (SOZINHO)          orchestrator-dynamic (FLUXO G INCOMPLETO)    │
│  ┌─────────────────┐           ┌──────────────────────────────────────┐    │
│  │ PipelineEngine  │  ❌ SEM   │  G1: generate_requirements     ✅     │    │
│  │ - template_sel  │  CONEXÃO  │  G2: generate_documentation    ✅     │    │
│  │ - code_compose  │  ──────── │  G3: update_knowledge_graph    ✅     │    │
│  │ - dockerfile    │           │  G4: request_approval          ✅     │    │
│  │ - container_bld │           │  G5: query_rag                 ✅     │    │
│  │ - validation    │           │  G6: GENERATE_CODE            ❌     │    │
│  │ - testing       │           │  G7: BUILD_PACKAGE            ❌     │    │
│  │ - packaging     │           │  G8: DEPLOY_SOFTWARE          ❌     │    │
│  │ - approval_gate │           └──────────────────────────────────────┘    │
│  └─────────────────┘                                                      │
│                                                                             │
│  API: POST /api/v1/pipelines                                               │
│       POST /api/v1/generation                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Parte 1: G6 - GENERATE_CODE

### 1.1 O Que É G6?

**Definição:** Etapa do Fluxo G que gera código fonte a partir dos requisitos e documentação gerados nas etapas anteriores.

**Entrada:**
- `requirements_set` (saída do G1)
- `documentation` (saída do G2)
- `cognitive_plan` (entrada original)

**Saída:**
- `code_artifact` - Código fonte gerado
- `iac_artifact` - Infrastructure as Code (opcional)
- `metadata` - Linguagem, framework, dependências

### 1.2 O Que Já Existe no Code-Forge

O `code-forge` já possui **toda a funcionalidade necessária** para G6:

#### A. CodeComposer (`services/code_composer.py`)

```python
class CodeComposer:
    """
    Gera código via 4 métodos:
    1. TEMPLATE - Código pré-definido baseado em template
    2. LLM - Geração via LLM (OpenAI/Anthropic)
    3. HYBRID - Combinação de template + LLM
    4. HEURISTIC - Código baseado em regras
    """

    async def compose(self, context: PipelineContext):
        # Suporta 5 linguagens:
        # - Python (FastAPI, Flask)
        # - Node.js (Express)
        # - TypeScript (Express)
        # - Go (Gorilla Mux)
        # - Java (Spring Boot)

        if generation_method == "LLM":
            code_content = await self._generate_via_llm(context)
        elif generation_method == "HYBRID":
            code_content = await self._generate_hybrid(context)
        # ...
```

#### B. IaCGenerator (`services/iac_generator.py`)

```python
class IaCGenerator:
    """
    Gera Infrastructure as Code para:
    - Terraform (AWS, GCP, Azure)
    - Helm Charts
    - Kubernetes manifests
    - CloudFormation
    """

    def generate_terraform_module(self, params, provider, resources):
        # Gera módulo Terraform completo

    def generate_helm_chart(self, params):
        # Gera Helm chart com values.yaml, templates/

    def generate_k8s_manifests(self, params):
        # Gera Deployment, Service, ConfigMap, Secret
```

#### C. LLMClient Integration

```python
# code-forge já tem integração com:
# - OpenAI (GPT-4)
# - Anthropic (Claude)
# - RAG com Analyst Agents
# - MCP Tool Catalog

async def _generate_via_llm(self, context):
    # Constrói RAG context
    rag_context = await self._build_rag_context(ticket)

    # Chama LLM com contexto
    code = await self.llm_client.generate_code(
        prompt=requirements,
        context=rag_context,
        language=language
    )
```

### 1.3 O Que Falta Criar

#### A. Nova Activity no Orchestrator

**Arquivo:** `services/orchestrator-dynamic/src/activities/code_generation_activity.py`

```python
"""
Activity Temporal para integrar com code-forge.
"""

import httpx
from temporalio import activity
from datetime import timedelta

@activity.defn
async def generate_code(
    requirements_set: dict[str, Any],
    documentation: dict[str, Any],
    cognitive_plan: dict[str, Any],
) -> dict[str, Any]:
    """
    G6: Gera código fonte a partir de requisitos e documentação.

    Integra com code-forge via API REST.

    Args:
        requirements_set: Saída do G1 (generate_requirements)
        documentation: Saída do G2 (generate_documentation)
        cognitive_plan: Plano cognitivo original

    Returns:
        Dict com:
            - code_artifact_id: ID do artefato de código gerado
            - iac_artifact_id: ID do artefato IaC (se aplicável)
            - language: Linguagem do código gerado
            - framework: Framework utilizado
            - generation_method: Método de geração (TEMPLATE/LLM/HYBRID)
            - confidence_score: Confiança na qualidade do código
    """
    plan_id = cognitive_plan.get("plan_id", "unknown")

    # Determinar linguagem e framework
    language = cognitive_plan.get("target_language", "python")
    framework = cognitive_plan.get("target_framework", "fastapi")
    artifact_type = cognitive_plan.get("artifact_type", "microservice")

    # Preparar payload para code-forge
    payload = {
        "plan_id": plan_id,
        "intent_id": cognitive_plan.get("intent_id"),
        "decision_id": cognitive_plan.get("decision_id"),
        "artifact_type": artifact_type,
        "parameters": {
            "language": language,
            "framework": framework,
            "service_name": f"service-{plan_id}",
            "generation_method": "LLM",  # ou HYBRID
            "include_tests": True,
            "include_iac": True,
            "iac_provider": "kubernetes",  # ou aws, gcp
        },
        "requirements": requirements_set,
        "documentation": documentation,
    }

    # Chamar code-forge API
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://code-forge:8020/api/v1/generation",
            json=payload,
            timeout=timedelta(seconds=300).total_seconds()  # 5 minutos
        )

        if response.status_code != 202:
            raise RuntimeError(f"Geração falhou: {response.status_code}")

        result = response.json()
        request_id = result.get("request_id")

        # Poll para completude (ou usar webhook)
        return await _wait_for_generation(client, request_id)


async def _wait_for_generation(
    client: httpx.AsyncClient,
    request_id: str,
    max_wait: int = 600,
) -> dict[str, Any]:
    """
    Aguarda a geração de código completar.

    Args:
        client: HTTP client
        request_id: ID da requisição de geração
        max_wait: Tempo máximo de espera em segundos

    Returns:
        Resultado final da geração com artefatos
    """
    import asyncio

    started = asyncio.get_event_loop().time()
    last_status = None

    while True:
        elapsed = asyncio.get_event_loop().time() - started
        if elapsed > max_wait:
            raise TimeoutError(f"Geração timeout após {max_wait}s")

        response = await client.get(
            f"http://code-forge:8020/api/v1/generation/{request_id}"
        )

        if response.status_code == 200:
            status_data = response.json()
            last_status = status_data.get("status")

            if last_status in ("completed", "failed", "requires_review"):
                return status_data

        await asyncio.sleep(5)  # Poll a cada 5 segundos
```

#### B. Atualizar FluxoGWorkflow

**Arquivo:** `services/orchestrator-dynamic/src/workflows/fluxo_g_workflow.py`

```python
# Adicionar import
from neural_hive_observability import get_tracer

with workflow.unsafe.imports_passed_through():
    from src.activities.code_generation_activity import generate_code

@workflow.run
async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
    # ... G1-G5 existentes ...

    # === G6: Code Generation ===
    self._status = "generating_code"
    workflow.logger.info("G6: Gerando código")

    code_result = await workflow.execute_activity(
        generate_code,
        args=[requirements_result, docs_result, cognitive_plan],
        start_to_close_timeout=timedelta(seconds=600),  # 10 minutos
        retry_policy=RetryPolicy(maximum_attempts=1),  # Não retry em falha de LLM
    )

    self._code_artifact = code_result
    span.add_event("code_generated")

    # Armazenar no resultado final
    self._workflow_result["code_generation"] = {
        "artifact_id": code_result.get("code_artifact_id"),
        "language": code_result.get("language"),
        "framework": code_result.get("framework"),
        "confidence": code_result.get("confidence_score"),
    }

    # Continuar com G7-G8...
```

### 1.4 Fluxo de Dados G6

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           G6: GENERATE_CODE                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  INPUT                                                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│  │ requirements_set│  │  documentation  │  │ cognitive_plan  │            │
│  │ (do G1)         │  │   (do G2)       │  │   (original)    │            │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘            │
│           │                    │                    │                      │
│           └────────────────────┴────────────────────┘                      │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │           generate_code ACTIVITY (Temporal)                         │   │
│  │  ┌──────────────────────────────────────────────────────────────┐  │   │
│  │  │  1. Mapear parâmetros:                                       │  │   │
│  │  │     - language (python/nodejs/etc)                           │  │   │
│  │  │     - framework (fastapi/express/etc)                        │  │   │
│  │  │     - artifact_type (microservice/lambda/etc)                │  │   │
│  │  └──────────────────────────────────────────────────────────────┘  │   │
│  │  ┌──────────────────────────────────────────────────────────────┐  │   │
│  │  │  2. Chamar code-forge API:                                   │  │   │
│  │  │     POST /api/v1/generation                                  │  │   │
│  │  │     {                                                         │  │   │
│  │  │       requirements: {...},                                    │  │   │
│  │  │       documentation: {...},                                    │  │   │
│  │  │       parameters: {                                           │  │   │
│  │  │         language: "python",                                    │  │   │
│  │  │         framework: "fastapi",                                  │  │   │
│  │  │         generation_method: "LLM"                               │  │   │
│  │  │       }                                                       │  │   │
│  │  │     }                                                         │  │   │
│  │  └──────────────────────────────────────────────────────────────┘  │   │
│  │  ┌──────────────────────────────────────────────────────────────┐  │   │
│  │  │  3. Poll para completude:                                     │  │   │
│  │  │     GET /api/v1/generation/{request_id}                       │  │   │
│  │  │     status: pending → running → completed                     │  │   │
│  │  └──────────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  CODE-FORGE INTERNAL                                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  PipelineEngine.execute_pipeline()                                  │   │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐    │   │
│  │  │ template_select  │→ │  code_compose    │→ │ dockerfile_gen   │    │   │
│  │  │ (seleciona tmpl) │  │ (gera código)    │  │ (gera Dockerfile)│    │   │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘    │   │
│  │                                                                  │   │   │
│  │  CodeComposer.compose():                                         │   │
│  │  - _generate_via_llm()    ← Chama OpenAI/Claude                │   │   │
│  │  - _generate_hybrid()     ← Template + LLM                      │   │   │
│  │  - _generate_heuristic()  ← Regras predefinidas                 │   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  OUTPUT                                                                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│  │ code_artifact   │  │ iac_artifact    │  │ metadata        │            │
│  │ - Python/NodeJS │  │ - Terraform/Helm│  │ - language      │            │
│  │ - FastAPI/Expr  │  │ - K8s manifests │  │ - framework     │            │
│  │ - 500+ linhas   │  │ - Cloud configs │  │ - dependencies  │            │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Parte 2: G7 - BUILD_PACKAGE

### 2.1 O Que É G7?

**Definição:** Etapa que compila, testa e empacota o código gerado em um artefato distribuível.

**Entrada:**
- `code_artifact` (saída do G6)
- `dockerfile_content` (gerado durante o build)

**Saída:**
- `container_image` - Imagem Docker pronta
- `test_results` - Resultados dos testes
- `sbom` - Software Bill of Materials
- `package_artifact` - Arquivo compactado com tudo

### 2.2 O Que Já Existe no Code-Forge

#### A. ContainerBuilder (`services/container_builder.py`)

```python
class ContainerBuilder:
    """
    Executa build real de containers Docker.
    """

    async def build_container(
        self,
        dockerfile_path: str,
        build_context: str,
        image_tag: str,
    ) -> BuildResult:
        """
        Executa docker build real.
        """
        # Usa Docker CLI ou Kaniko para build
        # Suporta multi-stage builds
        # Retorna digest, size, etc.
```

#### B. TestRunner (`services/test_runner.py`)

```python
class TestRunner:
    """
    Executa testes do código gerado.
    """

    async def run_tests(self, context: PipelineContext):
        # Suporta:
        # - pytest (Python)
        # - jest (Node.js/TS)
        # - go test (Go)
        # - JUnit (Java)

        # Executa em container isolado
        # Coleta métricas de cobertura
```

#### C. Packager (`services/packager.py`)

```python
class Packager:
    """
    Empacota artefatos e gera SBOM.
    """

    async def package(self, context: PipelineContext):
        # Gera:
        # - SBOM (Software Bill of Materials)
        # - Arquivo tar.gz com código
        # - Assinatura do artefato
        # - Metadados de versão
```

#### D. Validator (`services/validator.py`)

```python
class Validator:
    """
    Valida qualidade e segurança do código.
    """

    async def validate(self, context: PipelineContext):
        # Executa:
        # - Linting (ruff, eslint, golangci-lint)
        # - Security scan (bandit, npm audit)
        # - Quality check (complexidade, duplicação)
        # - License validation
```

### 2.3 O Que Falta Criar

#### A. Activity de Build no Orchestrator

**Arquivo:** `services/orchestrator-dynamic/src/activities/build_package_activity.py`

```python
"""
Activity para build e empacotamento do código gerado.
"""

@activity.defn
async def build_package(
    code_artifact_id: str,
    cognitive_plan: dict[str, Any],
) -> dict[str, Any]:
    """
    G7: Compila, testa e empacota o código gerado.

    Args:
        code_artifact_id: ID do artefato de código gerado no G6
        cognitive_plan: Plano cognitivo com parâmetros de build

    Returns:
        Dict com:
            - container_image: Digest da imagem Docker
            - image_tag: Tag da imagem (e.g., service-xyz:1.0.0)
            - test_results: Resultados dos testes
            - sbom: Software Bill of Materials
            - package_uri: URI do artefato empacotado
            - quality_score: Score de qualidade (0-1)
            - security_scan: Resultados do scan de segurança
    """
    plan_id = cognitive_plan.get("plan_id", "unknown")
    service_name = f"service-{plan_id}"
    version = cognitive_plan.get("version", "1.0.0")

    # Preparar payload para code-forge
    payload = {
        "plan_id": plan_id,
        "artifact_id": code_artifact_id,
        "parameters": {
            "service_name": service_name,
            "version": version,
            "enable_tests": True,
            "enable_security_scan": True,
            "generate_sbom": True,
            "push_to_registry": cognitive_plan.get("push_to_registry", False),
        },
    }

    # Chamar code-forge API para build
    async with httpx.AsyncClient() as client:
        # Opção 1: Usar pipeline API do code-forge
        response = await client.post(
            "http://code-forge:8020/api/v1/pipelines",
            json=payload,
            timeout=600.0  # 10 minutos
        )

        if response.status_code != 201:
            raise RuntimeError(f"Build falhou: {response.status_code}")

        result = response.json()
        pipeline_id = result.get("pipeline_id")

        # Poll para completude
        return await _wait_for_build_completion(client, pipeline_id)


async def _wait_for_build_completion(
    client: httpx.AsyncClient,
    pipeline_id: str,
    max_wait: int = 900,
) -> dict[str, Any]:
    """Aguarda o pipeline de build completar."""
    import asyncio

    started = asyncio.get_event_loop().time()

    while True:
        elapsed = asyncio.get_event_loop().time() - started
        if elapsed > max_wait:
            raise TimeoutError(f"Build timeout após {max_wait}s")

        response = await client.get(
            f"http://code-forge:8020/api/v1/pipelines/{pipeline_id}"
        )

        if response.status_code == 200:
            status_data = response.json()
            status = status_data.get("status")

            if status == "completed":
                return {
                    "container_image": status_data.get("image_digest"),
                    "image_tag": status_data.get("image_tag"),
                    "test_results": status_data.get("test_results"),
                    "sbom": status_data.get("sbom"),
                    "quality_score": status_data.get("quality_score", 0.0),
                    "security_scan": status_data.get("security_scan"),
                    "package_uri": status_data.get("package_uri"),
                }
            elif status in ("failed", "requires_review"):
                raise RuntimeError(f"Build falhou: {status_data.get('error')}")

        await asyncio.sleep(5)
```

#### B. Atualizar FluxoGWorkflow

```python
# Após G6 (code_generation):

# === G7: Build & Package ===
self._status = "building_package"
workflow.logger.info("G7: Build e empacotamento")

build_result = await workflow.execute_activity(
    build_package,
    args=[code_result.get("code_artifact_id"), cognitive_plan],
    start_to_close_timeout=timedelta(seconds=900),  # 15 minutos
    retry_policy=RetryPolicy(maximum_attempts=1),
)

self._build_artifact = build_result
span.add_event("package_built")

# Verificar quality gate
if build_result.get("quality_score", 0.0) < 0.5:
    workflow.logger.warning("Baixa qualidade detectada, requer revisão")
    # TODO: Implementar fallback para revisão humana

self._workflow_result["build"] = {
    "image": build_result.get("container_image"),
    "tag": build_result.get("image_tag"),
    "quality": build_result.get("quality_score"),
    "tests_passed": build_result.get("test_results", {}).get("passed", 0),
}
```

### 2.4 Fluxo de Dados G7

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           G7: BUILD_PACKAGE                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  INPUT                              CODE-FORGE PIPELINE                      │
│  ┌─────────────────┐               ┌──────────────────────────────────────┐│
│  │ code_artifact   │───────────────▶│ PipelineEngine.execute_pipeline()   ││
│  │ - artifact_id   │               │                                      ││
│  │ - language      │               │ ┌─────────────────────────────────┐  ││
│  └─────────────────┘               │ │ 1. code_compose                 │  ││
│                                    │ │    (código já existe)           │  ││
│                                    │ └─────────────────────────────────┘  ││
│                                    │ ┌─────────────────────────────────┐  ││
│                                    │ │ 2. dockerfile_generation         │  ││
│                                    │ │    (gera Dockerfile otimizado)   │  ││
│                                    │ └─────────────────────────────────┘  ││
│                                    │ ┌─────────────────────────────────┐  ││
│                                    │ │ 3. container_build              │  ││
│                                    │ │    - docker build               │  ││
│                                    │ │    - ou kaniko build            │  ││
│                                    │ │    - retorna digest + size      │  ││
│                                    │ └─────────────────────────────────┘  ││
│                                    │ ┌─────────────────────────────────┐  ││
│                                    │ │ 4. validation                   │  ││
│                                    │ │    - ruff lint (Python)          │  ││
│                                    │ │    - bandit security            │  ││
│                                    │ │    - npm audit (Node)           │  ││
│                                    │ └─────────────────────────────────┘  ││
│                                    │ ┌─────────────────────────────────┐  ││
│                                    │ │ 5. testing                      │  ││
│                                    │ │    - pytest (Python)            │  ││
│                                    │ │    - jest (Node)                │  ││
│                                    │ │    - go test (Go)               │  ││
│                                    │ │    - Retorna: passed/failed     │  ││
│                                    │ └─────────────────────────────────┘  ││
│                                    │ ┌─────────────────────────────────┐  ││
│                                    │ │ 6. packaging                    │  ││
│                                    │ │    - Gera SBOM (cyclonedx)      │  ││
│                                    │ │    - Cria tar.gz                │  ││
│                                    │ │    - Assina artefato            │  ││
│                                    │ └─────────────────────────────────┘  ││
│                                    │ ┌─────────────────────────────────┐  ││
│                                    │ │ 7. approval_gate                │  ││
│                                    │ │    - Verifica quality_score     │  ││
│                                    │ │    - Auto-aprova se >0.9        │  ││
│                                    │ │    - Senão, requer revisão      │  ││
│                                    │ └─────────────────────────────────┘  ││
│                                    └──────────────────────────────────────┘│
│                                               │                              │
│                                               ▼                              │
│  OUTPUT                                                                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│  │ container_image │  │ test_results    │  │ sbom            │            │
│  │ - digest        │  │ - passed: N     │  │ - components    │            │
│  │ - tag: v1.0.0   │  │ - failed: N     │  │ - licenses      │            │
│  │ - size: 150MB   │  │ - coverage: %   │  │ - vulnerabilities│            │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Parte 3: G8 - DEPLOY_SOFTWARE

### 3.1 O Que É G8?

**Definição:** Etapa que faz deploy do software empacotado no ambiente alvo.

**Entrada:**
- `container_image` (saída do G7)
- `deployment_config` (configuração de deployment)

**Saída:**
- `deployment_status` - Status do deployment
- `service_url` - URL do serviço deployado
- `health_check` - Resultado do health check

### 3.2 O Que Existe no Code-Forge

O code-forge **NÃO tem** funcionalidade de deploy nativa. Ele gera o artefato mas não faz deploy.

### 3.3 O Que Falta Criar

#### A. Serviço de Deploy (NOVO)

**Arquivo:** `services/deploy-service/` (NOVO SERVIÇO)

```python
"""
Serviço especializado em deployment de software.

Capacidades:
- Deploy em Kubernetes (Helm/Kubectl)
- Deploy em AWS (ECS/Lambda)
- Deploy em GCP (Cloud Run)
- Deploy em Azure (Container Instances)
"""

from kubernetes import client, config
from kubernetes.client import AppsV1Api, CoreV1Api

class DeployService:
    """Orquestra deployments em múltiplos ambientes."""

    async def deploy_to_kubernetes(
        self,
        image_tag: str,
        service_name: str,
        namespace: str = "default",
        replicas: int = 1,
        port: int = 8080,
    ) -> dict[str, Any]:
        """
        Faz deploy em Kubernetes.

        Args:
            image_tag: Tag da imagem Docker
            service_name: Nome do serviço
            namespace: Namespace K8s
            replicas: Número de réplicas
            port: Porta do container

        Returns:
            Dict com status do deployment
        """
        # Carregar config K8s
        config.load_incluster_config()  # Dentro do cluster
        # ou config.load_kube_config()  # Fora do cluster

        apps_v1 = AppsV1Api()
        core_v1 = CoreV1Api()

        # Criar Deployment
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": service_name, "namespace": namespace},
            "spec": {
                "replicas": replicas,
                "selector": {"matchLabels": {"app": service_name}},
                "template": {
                    "metadata": {"labels": {"app": service_name}},
                    "spec": {
                        "containers": [{
                            "name": service_name,
                            "image": image_tag,
                            "ports": [{"containerPort": port}],
                            "resources": {
                                "requests": {"cpu": "100m", "memory": "128Mi"},
                                "limits": {"cpu": "500m", "memory": "512Mi"},
                            },
                            "livenessProbe": {
                                "httpGet": {"path": "/health", "port": port},
                                "initialDelaySeconds": 10,
                                "periodSeconds": 5,
                            },
                            "readinessProbe": {
                                "httpGet": {"path": "/health", "port": port},
                                "initialDelaySeconds": 5,
                                "periodSeconds": 3,
                            },
                        }],
                    },
                },
            },
        }

        # Aplicar deployment
        apps_v1.create_namespaced_deployment(
            namespace=namespace,
            body=deployment
        )

        # Criar Service
        service = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": service_name, "namespace": namespace},
            "spec": {
                "selector": {"app": service_name},
                "ports": [{"protocol": "TCP", "port": 80, "targetPort": port}],
                "type": "ClusterIP",
            },
        }

        core_v1.create_namespaced_service(
            namespace=namespace,
            body=service
        )

        # Aguardar rollout
        await self._wait_for_rollout(service_name, namespace)

        return {
            "status": "deployed",
            "service_name": service_name,
            "namespace": namespace,
            "replicas": replicas,
            "url": f"http://{service_name}.{namespace}.svc.cluster.local",
        }

    async def _wait_for_rollout(
        self,
        service_name: str,
        namespace: str,
        timeout: int = 300,
    ):
        """Aguarda o deployment completar."""
        import asyncio

        apps_v1 = AppsV1Api()
        started = asyncio.get_event_loop().time()

        while True:
            elapsed = asyncio.get_event_loop().time() - started
            if elapsed > timeout:
                raise TimeoutError(f"Deploy timeout após {timeout}s")

            deployment = apps_v1.read_namespaced_deployment(
                name=service_name,
                namespace=namespace,
            )

            if deployment.status.ready_replicas == deployment.spec.replicas:
                break

            await asyncio.sleep(5)
```

#### B. Activity de Deploy no Orchestrator

**Arquivo:** `services/orchestrator-dynamic/src/activities/deploy_activity.py`

```python
"""
Activity para deploy do software gerado.
"""

@activity.defn
async def deploy_software(
    container_image: str,
    cognitive_plan: dict[str, Any],
) -> dict[str, Any]:
    """
    G8: Faz deploy do software empacotado.

    Args:
        container_image: Digest/tag da imagem Docker
        cognitive_plan: Plano com configurações de deployment

    Returns:
        Dict com:
            - deployment_status: Status do deployment
            - service_url: URL do serviço
            - health_check: Resultado do health check
            - namespace: Namespace K8s (se aplicável)
    """
    plan_id = cognitive_plan.get("plan_id", "unknown")
    service_name = f"service-{plan_id}"

    # Determinar target de deployment
    deploy_target = cognitive_plan.get("deploy_target", "kubernetes")

    if deploy_target == "kubernetes":
        return await self._deploy_to_kubernetes(
            container_image, service_name, cognitive_plan
        )
    elif deploy_target == "aws_lambda":
        return await self._deploy_to_lambda(
            container_image, service_name, cognitive_plan
        )
    else:
        raise ValueError(f"Target não suportado: {deploy_target}")


async def _deploy_to_kubernetes(
    self,
    image_tag: str,
    service_name: str,
    config: dict,
) -> dict[str, Any]:
    """Deploy em Kubernetes via deploy-service."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://deploy-service:8030/api/v1/deploy/kubernetes",
            json={
                "image_tag": image_tag,
                "service_name": service_name,
                "namespace": config.get("namespace", "neural-hive"),
                "replicas": config.get("replicas", 1),
                "port": config.get("port", 8080),
            },
            timeout=300.0  # 5 minutos
        )

        if response.status_code != 200:
            raise RuntimeError(f"Deploy falhou: {response.status_code}")

        result = response.json()

        # Executar health check
        health = await self._health_check(
            result.get("service_url"),
            timeout=60,
        )

        return {
            "deployment_status": result.get("status"),
            "service_url": result.get("url"),
            "health_check": health,
            "namespace": result.get("namespace"),
        }


async def _health_check(
    self,
    service_url: str,
    timeout: int = 60,
) -> dict[str, Any]:
    """Executa health check no serviço deployado."""
    import asyncio

    started = asyncio.get_event_loop().time()

    while True:
        elapsed = asyncio.get_event_loop().time() - started
        if elapsed > timeout:
            return {"status": "timeout", "error": "Health check timeout"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{service_url}/health",
                    timeout=5.0
                )

                if response.status_code == 200:
                    return {
                        "status": "healthy",
                        "response": response.json(),
                    }
        except Exception:
            pass

        await asyncio.sleep(3)
```

#### C. Atualizar FluxoGWorkflow

```python
# Após G7 (build_package):

# === G8: Deploy Software ===
self._status = "deploying"
workflow.logger.info("G8: Deploy do software")

deploy_config = cognitive_plan.get("deployment", {})
deploy_result = await workflow.execute_activity(
    deploy_software,
    args=[build_result.get("container_image"), cognitive_plan],
    start_to_close_timeout=timedelta(seconds=300),  # 5 minutos
    retry_policy=RetryPolicy(maximum_attempts=2),
)

self._deployment = deploy_result
span.add_event("software_deployed")

# Verificar health check
if deploy_result.get("health_check", {}).get("status") != "healthy":
    workflow.logger.error("Deploy falhou health check")
    # TODO: Disparar self-healing

self._workflow_result["deployment"] = {
    "status": deploy_result.get("deployment_status"),
    "url": deploy_result.get("service_url"),
    "health": deploy_result.get("health_check"),
}
```

### 3.4 Fluxo de Dados G8

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           G8: DEPLOY_SOFTWARE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  INPUT                                                                     │
│  ┌─────────────────┐  ┌─────────────────┐                                  │
│  │ container_image │  │ deployment_cfg  │                                  │
│  │ - digest/tag    │  │ - target: k8s   │                                  │
│  │ - from G7       │  │ - namespace     │                                  │
│  └────────┬────────┘  │ - replicas      │                                  │
│           │            └────────┬────────┘                                  │
│           └─────────────────────┴────────────────────────┐                 │
│                                                             │                 │
│                                                             ▼                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              deploy_software ACTIVITY (Temporal)                    │   │
│  │  ┌──────────────────────────────────────────────────────────────┐  │   │
│  │  │  1. Determinar target de deployment:                        │  │   │
│  │  │     - kubernetes (default)                                   │  │   │
│  │  │     - aws_lambda                                            │  │   │
│  │  │     - gcp_cloud_run                                         │  │   │
│  │  └──────────────────────────────────────────────────────────────┘  │   │
│  │  ┌──────────────────────────────────────────────────────────────┐  │   │
│  │  │  2. Chamar deploy-service API:                               │  │   │
│  │  │     POST /api/v1/deploy/kubernetes                           │  │   │
│  │  │     {                                                        │  │   │
│  │  │       image_tag: "service-xyz:1.0.0",                        │  │   │
│  │  │       service_name: "service-xyz",                           │  │   │
│  │  │       namespace: "neural-hive",                              │  │   │
│  │  │       replicas: 2                                            │  │   │
│  │  │     }                                                        │  │   │
│  │  └──────────────────────────────────────────────────────────────┘  │   │
│  │  ┌──────────────────────────────────────────────────────────────┐  │   │
│  │  │  3. deploy-service executa:                                  │  │   │
│  │  │     - Cria K8s Deployment                                    │  │   │
│  │  │     - Cria K8s Service                                       │  │   │
│  │  │     - Aguarda rollout completar                              │  │   │
│  │  └──────────────────────────────────────────────────────────────┘  │   │
│  │  ┌──────────────────────────────────────────────────────────────┐  │   │
│  │  │  4. Executa health check:                                    │  │   │
│  │  │     GET {service_url}/health                                 │  │   │
│  │  │     - Aguarda responder 200 OK                               │  │   │
│  │  │     - Timeout: 60 segundos                                   │  │   │
│  │  └──────────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  OUTPUT                                                                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│  │ deployment_stat │  │  service_url    │  │  health_check   │            │
│  │ - deployed      │  │ - http://svc..  │  │ - healthy       │            │
│  │ - failed        │  │ - cluster.local │  │ - response data │            │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘            │
│                                                                             │
│  KUBERNETES CLUSTER                                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Namespace: neural-hive                                             │   │
│  │  ┌──────────────────────────────────────────────────────────────┐   │   │
│  │  │ Deployment: service-xyz                                       │   │   │
│  │  │  Replicas: 2/2 READY                                         │   │   │
│  │  │  Image: service-xyz:1.0.0                                    │   │   │
│  │  └──────────────────────────────────────────────────────────────┘   │   │
│  │  ┌──────────────────────────────────────────────────────────────┐   │   │
│  │  │ Service: service-xyz                                          │   │   │
│  │  │  ClusterIP: 10.0.0.50                                        │   │   │
│  │  │  Port: 80/TCP → 8080                                         │   │   │
│  │  └──────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Parte 4: Integração Completa G6-G8

### 4.1 Fluxo G Atualizado

```
FluxoGWorkflow (COMPLETO):
├─ G1: generate_requirements       ✅ IMPLEMENTADO
├─ G2: generate_documentation      ✅ IMPLEMENTADO
├─ G3: update_knowledge_graph      ✅ IMPLEMENTADO
├─ G4: request_approval            ✅ IMPLEMENTADO
├─ G5: query_rag                   ✅ IMPLEMENTADO
├─ G6: GENERATE_CODE               🔧 A IMPLEMENTAR
├─ G7: BUILD_PACKAGE               🔧 A IMPLEMENTAR
└─ G8: DEPLOY_SOFTWARE             🔧 A IMPLEMENTAR
```

### 4.2 Arquivos a Criar

| Arquivo | Propósito | Esforço |
|---------|-----------|---------|
| `code_generation_activity.py` | Activity G6 - integrar com code-forge | 4h |
| `build_package_activity.py` | Activity G7 - build e testes | 4h |
| `deploy_activity.py` | Activity G8 - deployment | 4h |
| `deploy-service/` | Novo serviço para K8s deployment | 16h |
| Atualizar `fluxo_g_workflow.py` | Adicionar G6-G8 | 2h |

**Total Estimado:** 30 horas (~4 dias)

### 4.3 Dependências

```
G6 (generate_code)
  ├─ Depende de: G1, G2 (requirements + documentation)
  ├─ Integra com: code-forge API (/api/v1/generation)
  └─ Produz: code_artifact_id

G7 (build_package)
  ├─ Depende de: G6 (code_artifact_id)
  ├─ Integra com: code-forge API (/api/v1/pipelines)
  └─ Produz: container_image, test_results

G8 (deploy_software)
  ├─ Depende de: G7 (container_image)
  ├─ Integra com: deploy-service API (NOVO SERVIÇO)
  └─ Produz: service_url, health_status
```

---

## Parte 5: Exemplo Completo

### Cenário: Criar Novo Microserviço

**Input do Usuário:**
```
"Crie um microserviço em Python com FastAPI para gerenciar usuários.
Deve ter endpoints para criar, listar, atualizar e deletar usuários.
Use MongoDB como banco de dados."
```

**Fluxo Executado:**

```
E0: Gateway Intenções
    ├─ Intent classificado: "create_microservice"
    └─ confidence: 0.95

E1: STE
    ├─ Semantic parsing
    └─ CognitivePlan criado

E2: Consensus Engine
    ├─ Specialists agregam
    └─ ConsolidatedDecision: "APPROVE"

E3: Context Layer
    ├─ Classificação: TYPE="generation"
    └─ Router → Fluxo G

┌─────────────────────────────────────────────────────────────────────────────┐
│                           FLUXO G (EXECUÇÃO)                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  G1: generate_requirements                                                 │
│  └─ Saída: {                                                              │
│       "requirements_set_id": "REQ-SET-123",                                │
│       "requirements": [                                                    │
│         {                                                                  │
│           "id": "REQ-1",                                                   │
│           "title": "Criar Usuário",                                        │
│           "description": "Endpoint POST /users",                           │
│           "acceptance_criteria": ["Valida input", "Salva no MongoDB"]      │
│         },                                                                 │
│         {                                                                  │
│           "id": "REQ-2",                                                   │
│           "title": "Listar Usuários",                                       │
│           "description": "Endpoint GET /users",                            │
│           "acceptance_criteria": ["Retorna array", "Suporta paginação"]    │
│         }                                                                  │
│       ]                                                                    │
│     }                                                                      │
│                                                                             │
│  G2: generate_documentation                                                │
│  └─ Saída: {                                                              │
│       "documentation_id": "DOC-456",                                       │
│       "readme": "# User Management Service\n...",                          │
│       "api_docs": "OpenAPI spec..."                                        │
│     }                                                                      │
│                                                                             │
│  G3: update_knowledge_graph                                                │
│  └─ Saída: {                                                              │
│       "nodes_created": 3,                                                  │
│       "relations_created": 2                                               │
│     }                                                                      │
│                                                                             │
│  G4: request_approval                                                      │
│  └─ Saída: {                                                              │
│       "status": "approved",                                                │
│       "confidence": 0.92                                                   │
│     }                                                                      │
│                                                                             │
│  G5: query_rag                                                             │
│  └─ Saída: {                                                              │
│       "response": "Encontrei 3 serviços similares..."                       │
│     }                                                                      │
│                                                                             │
│  ─────────────────────────────────────────────────────────────────────────   │
│                                                                             │
│  G6: GENERATE_CODE (NOVO)                                                  │
│  └─ Activity chama code-forge:                                            │
│      POST /api/v1/generation                                              │
│      {                                                                     │
│        "requirements": {...},                                              │
│        "documentation": {...},                                             │
│        "parameters": {                                                     │
│          "language": "python",                                             │
│          "framework": "fastapi",                                           │
│          "generation_method": "LLM"                                        │
│        }                                                                   │
│      }                                                                     │
│      └─ code-forge PipelineEngine:                                        │
│          ├─ template_selector: "python-fastapi-microservice"              │
│          ├─ code_composer:                                                │
│          │   ├─ LLMClient.generate_code() → GPT-4                        │
│          │   └─ Saída: 450 linhas de código Python                       │
│          ├─ dockerfile_generator:                                         │
│          │   └─ Multi-stage Dockerfile (python:3.12-slim)                │
│          └─ Salva no MongoDB                                              │
│                                                                             │
│      └─ Saída: {                                                          │
│           "code_artifact_id": "CODE-789",                                  │
│           "language": "python",                                            │
│           "framework": "fastapi",                                          │
│           "confidence": 0.88,                                              │
│           "lines_of_code": 450                                             │
│         }                                                                  │
│                                                                             │
│  G7: BUILD_PACKAGE (NOVO)                                                  │
│  └─ Activity chama code-forge:                                            │
│      POST /api/v1/pipelines                                               │
│      {                                                                     │
│        "artifact_id": "CODE-789",                                          │
│        "parameters": {                                                     │
│          "enable_tests": true,                                             │
│          "enable_security_scan": true                                      │
│        }                                                                   │
│      }                                                                     │
│      └─ code-forge PipelineEngine:                                        │
│          ├─ container_build:                                              │
│          │   └─ docker build → service-123:1.0.0                         │
│          │   └─ Image digest: sha256:abc123...                            │
│          │   └─ Size: 180MB                                               │
│          ├─ validation:                                                   │
│          │   ├─ ruff check: 0 errors                                     │
│          │   └─ bandit: 0 security issues                                │
│          ├─ testing:                                                      │
│          │   ├─ pytest: 12/12 passed                                      │
│          │   └─ Coverage: 87%                                             │
│          └─ packaging:                                                    │
│              └─ SBOM gerado com 15 dependencies                            │
│                                                                             │
│      └─ Saída: {                                                          │
│           "container_image": "sha256:abc123...",                            │
│           "image_tag": "service-123:1.0.0",                                │
│           "test_results": {"passed": 12, "failed": 0},                      │
│           "quality_score": 0.91,                                           │
│           "sbom": {...}                                                    │
│         }                                                                  │
│                                                                             │
│  G8: DEPLOY_SOFTWARE (NOVO)                                                │
│  └─ Activity chama deploy-service:                                        │
│      POST /api/v1/deploy/kubernetes                                        │
│      {                                                                     │
│        "image_tag": "service-123:1.0.0",                                   │
│        "service_name": "service-123",                                      │
│        "namespace": "neural-hive",                                         │
│        "replicas": 2                                                       │
│      }                                                                     │
│      └─ deploy-service:                                                   │
│          ├─ kubectl apply -f deployment.yaml                               │
│          ├─ kubectl apply -f service.yaml                                  │
│          ├─ Aguarda rollout: 2/2 READY                                     │
│          └─ Health check: GET /health → 200 OK                            │
│                                                                             │
│      └─ Saída: {                                                          │
│           "deployment_status": "deployed",                                  │
│           "service_url": "http://service-123.neural-hive.svc.cluster.local",│
│           "health_check": {"status": "healthy"}                             │
│         }                                                                  │
│                                                                             │
│  RESULTADO FINAL:                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Software gerado e deployado em ~15 minutos                         │   │
│  │                                                                     │   │
│  │  - 450 linhas de código Python (FastAPI)                           │   │
│  │  - 4 endpoints REST implementados                                   │   │
│  │  - Docker multi-stage build (180MB)                                 │   │
│  │  - 12 testes automatizados (87% cobertura)                          │   │
│  │  - Deploy K8s com 2 réplicas                                        │   │
│  │  - Health check passando                                             │   │
│  │  - SBOM com 15 dependencies                                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Conclusão

**O que existe:**
- ✅ `code-forge` completo com 8 stages
- ✅ Geração de código via LLM/Template/Híbrida
- ✅ Build de containers Docker
- ✅ Testes automatizados
- ✅ Validação de segurança
- ✅ Geração de SBOM
- ✅ API REST funcional

**O que falta:**
- ❌ Activities no orchestrator para G6-G8
- ❌ Integração FluxoGWorkflow com code-forge
- ❌ Serviço de deployment (deploy-service)

**Esforço estimado:** 30 horas (~4 dias)

**Após implementação:** NHM será capaz de gerar e deployar software automaticamente a partir de intenção em linguagem natural.
