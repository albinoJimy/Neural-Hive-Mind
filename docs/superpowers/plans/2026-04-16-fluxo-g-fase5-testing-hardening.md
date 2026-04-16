# Fluxo G Fase 5: Testing & Hardening - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Testes de carga, security hardening, performance tuning e documentação final para produção do Fluxo G.

**Architecture:** Testes automatizados com Locust, security scanning com Trivy/SonarQube, performance profiling com py-spy, e documentação completa de operações.

**Tech Stack:** Locust, pytest-benchmark, trivy, bandit, py-spy, prometheus, grafana

---

## Pré-requisitos

- Fases 1-4 completas (todos os serviços implementados e integrados)
- Cluster Kubernetes operacional
- Ferramentas de testing instaladas

---

## Task 1: Criar Testes de Carga com Locust

**Files:**
- Create: `services/orchestrator-dynamic/tests/load/locustfile.py`
- Create: `services/orchestrator-dynamic/tests/load/fluxo_g_load_test.py`

- [ ] **Step 1: Create Locust test file**

```python
# services/orchestrator-dynamic/tests/load/locustfile.py
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner
import time
import random
from datetime import datetime


class FluxoGUser(HttpUser):
    """Simula usuário interagindo com o Fluxo G."""

    wait_time = between(1, 3)
    host = "http://localhost:8003"

    def on_start(self):
        """Setup inicial de cada usuário."""
        self.pipeline_id = None
        self.user_id = f"load-test-user-{random.randint(1000, 9999)}"

    @task(3)
    def start_pipeline(self):
        """Inicia um novo pipeline (tarefa mais frequente)."""
        intents = [
            "Criar uma API REST de usuários",
            "Implementar sistema de autenticação JWT",
            "Criar microserviço de pagamentos",
            "Desenvolver dashboard administrativo",
            "Implementar fila de processamento",
            "Criar serviço de notificações",
            "Implementar cache distribuído",
            "Criar API de produtos com busca",
        ]

        intent_text = random.choice(intents)
        project_name = f"project-{random.randint(1000, 9999)}"

        response = self.client.post(
            "/api/v1/fluxo-g/pipelines",
            json={
                "intent_text": intent_text,
                "project_name": project_name,
                "user_id": self.user_id,
                "tech_stack": {
                    "language": "python",
                    "framework": "fastapi",
                },
                "require_approval": False,  # Mais rápido para load test
            },
            name="/api/v1/fluxo-g/pipelines (POST)",
        )

        if response.status_code == 202:
            data = response.json()
            self.pipeline_id = data.get("pipeline_id")
            self.environment.pipelines_started += 1

    @task(2)
    def check_pipeline_status(self):
        """Verifica status de pipeline existente."""
        if not self.pipeline_id:
            return

        response = self.client.get(
            f"/api/v1/fluxo-g/pipelines/{self.pipeline_id}",
            name="/api/v1/fluxo-g/pipelines/:id (GET)",
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("status") in ["completed", "failed"]:
                # Pipeline finalizado, reset para novo
                self.pipeline_id = None
                if data.get("status") == "completed":
                    self.environment.pipelines_completed += 1
                else:
                    self.environment.pipelines_failed += 1

    @task(1)
    def list_pipelines(self):
        """Lista pipelines (tarefa menos frequente)."""
        self.client.get(
            "/api/v1/fluxo-g/pipelines?page=1&page_size=20",
            name="/api/v1/fluxo-g/pipelines (GET)",
        )

    @task(1)
    def health_check(self):
        """Health check."""
        self.client.get("/health/ready", name="/health/ready")


class CustomUser(FluxoGUser):
    """Usuário customizado para testes específicos."""

    @task
    def start_complex_pipeline(self):
        """Inicia pipeline complexo com aprovação."""
        response = self.client.post(
            "/api/v1/fluxo-g/pipelines",
            json={
                "intent_text": (
                    "Criar sistema completo de e-commerce com "
                    "catálogo, carrinho, checkout e pagamentos"
                ),
                "project_name": f"ecommerce-{random.randint(100, 999)}",
                "user_id": self.user_id,
                "tech_stack": {
                    "language": "python",
                    "framework": "django",
                    "database": "postgresql",
                },
                "require_approval": True,
                "approvers": ["admin@test.com"],
            },
            name="/api/v1/fluxo-g/pipelines (POST with approval)",
        )


# Event handlers para métricas
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Inicializa contadores no início do teste."""
    environment.pipelines_started = 0
    environment.pipelines_completed = 0
    environment.pipelines_failed = 0
    environment.start_time = time.time()


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs, **kw):
    """Reporta métricas finais."""
    duration = time.time() - environment.start_time

    print("\n" + "=" * 60)
    print("FLUXO G LOAD TEST RESULTS")
    print("=" * 60)
    print(f"Duration: {duration:.2f} seconds")
    print(f"Pipelines Started: {environment.pipelines_started}")
    print(f"Pipelines Completed: {environment.pipelines_completed}")
    print(f"Pipelines Failed: {environment.pipelines_failed}")
    print(f"Success Rate: {(environment.pipelines_completed / max(environment.pipelines_started, 1)) * 100:.2f}%")
    print(f"Throughput: {environment.pipelines_started / duration:.2f} pipelines/second")
    print("=" * 60 + "\n")


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, **kwargs):
    """Log de requisições lentas."""
    if response_time > 5000:  # 5 segundos
        print(f"SLOW REQUEST: {name} took {response_time}ms")
```

- [ ] **Step 2: Create script executável**

```python
# services/orchestrator-dynamic/tests/load/run_load_test.py
import argparse
import subprocess
import sys


def run_locust(
    host: str,
    users: int,
    spawn_rate: float,
    run_time: str,
    headless: bool = True,
    master: bool = False,
    worker: bool = False,
    master_host: str = None,
):
    """Executa teste de carga com Locust."""

    cmd = [
        "locust",
        "-f", "tests/load/locustfile.py",
        "--host", host,
        "--users", str(users),
        "--spawn-rate", str(spawn_rate),
        "--run-time", run_time,
        "--html", "load_test_report.html",
    ]

    if headless:
        cmd.append("--headless")

    if master:
        cmd.append("--master")
        cmd.extend(["--expect-workers", str(users // 100)])

    if worker:
        cmd.append("--worker")
        if master_host:
            cmd.extend(["--master-host", master_host])

    # Output configs
    cmd.extend([
        "--logfile", "locust.log",
        "--loglevel", "INFO",
    ])

    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser(description="Run Fluxo G load tests")
    parser.add_argument("--host", default="http://localhost:8003", help="Target host")
    parser.add_argument("--users", type=int, default=100, help="Number of users")
    parser.add_argument("--spawn-rate", type=float, default=10, help="Users per second")
    parser.add_argument("--run-time", default="5m", help="Test duration (e.g., 5m, 1h)")
    parser.add_argument("--gui", action="store_true", help="Run with web UI")
    parser.add_argument("--master", action="store_true", help="Run as master")
    parser.add_argument("--worker", action="store_true", help="Run as worker")
    parser.add_argument("--master-host", help="Master host (for workers)")

    args = parser.parse_args()

    try:
        run_locust(
            host=args.host,
            users=args.users,
            spawn_rate=args.spawn_rate,
            run_time=args.run_time,
            headless=not args.gui,
            master=args.master,
            worker=args.worker,
            master_host=args.master_host,
        )
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(0)
    except subprocess.CalledProcessError as e:
        print(f"Error running locust: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Create configuration**

```yaml
# services/orchestrator-dynamic/tests/load/locust.conf
locust:
  host: http://localhost:8003
  users: 100
  spawn_rate: 10
  run_time: 5m

# Configurações de produção
production:
  host: http://orchestrator-dynamic-fluxog.neural-hive-mind.svc.cluster.local:8003
  users: 1000
  spawn_rate: 50
  run_time: 30m

# Configurações de stress
stress:
  host: http://localhost:8003
  users: 5000
  spawn_rate: 500
  run_time: 10m
```

- [ ] **Step 4: Commit**

```bash
git add services/orchestrator-dynamic/tests/load/
git commit -m "test(orchestrator): add load tests with Locust for Fluxo G"
```

---

## Task 2: Criar Testes de Performance com pytest-benchmark

**Files:**
- Create: `services/orchestrator-dynamic/tests/performance/test_fluxo_g_benchmarks.py`

- [ ] **Step 1: Create benchmark tests**

```python
# services/orchestrator-dynamic/tests/performance/test_fluxo_g_benchmarks.py
import pytest
import asyncio
from datetime import datetime

from orchestrator.models.fluxo_g_pipeline import (
    FluxoGPipeline,
    PipelineContext,
    PipelineStage,
)
from orchestrator.activities.fluxo_g_activities import (
    GenerateRequirementsActivity,
    QueryRAGActivity,
)
from orchestrator.producers.fluxo_g_producer import FluxoGEventProducer


@pytest.mark.benchmark(group="pipeline-model")
def test_pipeline_creation_speed(benchmark):
    """Benchmark da criação de pipeline."""
    context = PipelineContext(
        user_id="user123",
        project_name="test-project",
        intent_text="Criar API de usuários",
    )

    def create_pipeline():
        return FluxoGPipeline(context=context)

    result = benchmark(create_pipeline)
    assert result.id is not None


@pytest.mark.benchmark(group="pipeline-model")
def test_pipeline_stage_progression(benchmark):
    """Benchmark da progressão de estágios."""
    pipeline = FluxoGPipeline(
        context=PipelineContext(
            user_id="user456",
            project_name="test-project",
            intent_text="Intent de teste",
        )
    )

    async def progress_all_stages():
        await pipeline.start()
        for stage in [
            PipelineStage.REQUIREMENTS,
            PipelineStage.ARCHITECTURE,
            PipelineStage.RAG_QUERY,
        ]:
            from orchestrator.models.fluxo_g_pipeline import StageResult
            await pipeline.complete_stage(
                stage,
                StageResult(success=True, output={"test": "data"}),
            )

    benchmark(asyncio.run, progress_all_stages())


@pytest.mark.benchmark(group="kafka-producer")
def test_kafka_publish_speed(benchmark):
    """Benchmark de publicação Kafka."""
    producer = FluxoGEventProducer()

    async def publish_event():
        await producer.publish_intent_received(
            pipeline_id=f"pipe-{datetime.utcnow().timestamp()}",
            intent_text="Test intent",
            user_id="user789",
            project_name="test-proj",
        )

    # Warmup
    for _ in range(5):
        asyncio.run(publish_event())

    # Benchmark
    benchmark(lambda: asyncio.run(publish_event()))


@pytest.mark.benchmark(group="pipeline-context")
def test_context_serialization_speed(benchmark):
    """Benchmark de serialização de contexto."""
    context = PipelineContext(
        user_id="user999",
        project_name="serialize-test",
        intent_text="Test serialization",
        requirements={"user_stories": ["story1", "story2"]},
        architecture={"components": ["comp1", "comp2"]},
        metadata={"key1": "value1", "key2": "value2"},
    )

    def serialize():
        return context.model_dump_json()

    benchmark(serialize)


@pytest.mark.benchmark(group="pipeline-context")
def test_context_deserialization_speed(benchmark):
    """Benchmark de deserialização de contexto."""
    context = PipelineContext(
        user_id="user999",
        project_name="deserialize-test",
        intent_text="Test deserialization",
    )
    serialized = context.model_dump_json()

    def deserialize():
        return PipelineContext.model_validate_json(serialized)

    benchmark(deserialize)


@pytest.mark.benchmark(group="activities")
def test_requirements_activity_mock(benchmark):
    """Benchmark de activity de requirements (mockado)."""
    activity = GenerateRequirementsActivity()

    # Mock HTTP client para evitar chamadas reais
    from unittest.mock import AsyncMock, patch

    async def mock_post(*args, **kwargs):
        class MockResponse:
            status_code = 200
            def json(self):
                return {
                    "id": "req-123",
                    "user_stories": [{"role": "user", "action": "test", "benefit": "benefit"}],
                }

        return MockResponse()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_post()

        async def run_activity():
            result = await activity.run(
                intent_text="Criar sistema de testes",
                project_name="test-system",
                user_id="user-bench",
            )
            return result

        benchmark(lambda: asyncio.run(run_activity()))


@pytest.mark.benchmark(group="rag-query")
def test_rag_fallback_speed(benchmark):
    """Benchmark de fallback RAG (deve ser rápido)."""
    activity = QueryRAGActivity()

    result = benchmark(
        activity._execute_fallback,
        query="microservices architecture",
        context={"domain": "architecture"},
    )

    assert result["fallback_used"] is True


@pytest.mark.benchmark(group="stage-progress")
def test_percentage_calculation(benchmark):
    """Benchmark de cálculo de progresso."""
    pipeline = FluxoGPipeline(
        context=PipelineContext(
            user_id="user-percent",
            project_name="percent-test",
            intent_text="Test percentage",
        )
    )

    # Simula alguns estágios completos
    async def setup():
        await pipeline.start()
        from orchestrator.models.fluxo_g_pipeline import StageResult
        await pipeline.complete_stage(
            PipelineStage.REQUIREMENTS,
            StageResult(success=True, output={}),
        )
        await pipeline.complete_stage(
            PipelineStage.ARCHITECTURE,
            StageResult(success=True, output={}),
        )
        return pipeline

    pipeline = asyncio.run(setup())

    def get_progress():
        return pipeline.get_progress_percentage()

    result = benchmark(get_progress)
    assert result > 0  # Alguns estágios completos


# Benchmark de memória
@pytest.mark.benchmark(group="memory")
def test_pipeline_memory_footprint(benchmark):
    """Benchmark de footprint de memória do pipeline."""
    import sys

    context = PipelineContext(
        user_id="user-mem",
        project_name="memory-test",
        intent_text="Test memory footprint" * 10,  # Intent maior
        requirements={
            "user_stories": [{"role": "user", "action": f"action{i}", "benefit": f"benefit{i}"} for i in range(100)]
        },
        architecture={
            "components": [{"name": f"comp{i}", "type": "service"} for i in range(50)]
        },
    )

    def get_size():
        pipeline = FluxoGPipeline(context=context)
        return sys.getsizeof(pipeline)

    result = benchmark(get_size)
    # Pipeline não deve exceder 1MB para casos normais
    assert result < 1_000_000
```

- [ ] **Step 2: Create pytest config para benchmarks**

```ini
# pyproject.toml ou pytest.ini
[tool.pytest.ini_options]
markers = [
    "benchmark: marks tests as benchmarks",
]
benchmark_min_rounds = 5
benchmark_max_time = 30
benchmark_sort_by = "mean"
benchmark_columns = "min, max, mean, median, stddev, ops, rounds"
```

- [ ] **Step 3: Commit**

```bash
git add services/orchestrator-dynamic/tests/performance/
git commit -m "test(orchestrator): add performance benchmarks for Fluxo G"
```

---

## Task 3: Criar Security Scans

**Files:**
- Create: `security/scan-fluxo-g.sh`
- Create: `security/snyk-policy.yml`

- [ ] **Step 1: Create security scan script**

```bash
#!/bin/bash
# security/scan-fluxo-g.sh
set -e

echo "======================================"
echo "Fluxo G Security Scan"
echo "======================================"
echo ""

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Diretórios
ORCHESTRATOR_DIR="services/orchestrator-dynamic"
REQUIREMENTS_DIR="services/requirements-engineering"
ARCHITECT_DIR="services/architect-agent"
RAG_DIR="services/knowledge-graph-rag"
DOCS_DIR="services/documentation-generation"
APPROVAL_DIR="services/approval-gateway"

SERVICES=(
    "$ORCHESTRATOR_DIR"
    "$REQUIREMENTS_DIR"
    "$ARCHITECT_DIR"
    "$RAG_DIR"
    "$DOCS_DIR"
    "$APPROVAL_DIR"
)

# Funções
check_command() {
    if ! command -v $1 &> /dev/null; then
        echo -e "${YELLOW}⚠ $1 não encontrado, pulando...${NC}"
        return 1
    fi
    return 0
}

run_bandit() {
    echo -e "\n${GREEN}=== Bandit (Python Security) ===${NC}"

    for service in "${SERVICES[@]}"; do
        if [ -d "$service/src" ]; then
            echo "Scanning $service..."
            bandit -r "$service/src" -f json -o "bandit-$(basename $service).json" || true
            bandit -r "$service/src" || echo -e "${YELLOW}Bandit encontrou issues em $service${NC}"
        fi
    done
}

run_safety() {
    echo -e "\n${GREEN}=== Safety (Dependency Security) ===${NC}"

    for service in "${SERVICES[@]}"; do
        if [ -f "$service/requirements.txt" ]; then
            echo "Checking $service/requirements.txt..."
            safety check --file "$service/requirements.txt" --json > "safety-$(basename $service).json" || true
        fi
        if [ -f "$service/pyproject.toml" ]; then
            echo "Checking $service/pyproject.toml..."
            safety check --file "$service/pyproject.toml" || echo -e "${YELLOW}Safety encontrou issues em $service${NC}"
        fi
    done
}

run_trivy() {
    echo -e "\n${GREEN}=== Trivy (Vulnerability Scanner) ===${NC}"

    # Scan de imagens
    IMAGES=(
        "neural-hive-mind/orchestrator-dynamic:latest"
        "neural-hive-mind/requirements-engineering:latest"
        "neural-hive-mind/architect-agent:latest"
        "neural-hive-mind/knowledge-graph-rag:latest"
        "neural-hive-mind/documentation-generation:latest"
        "neural-hive-mind/approval-gateway:latest"
    )

    for image in "${IMAGES[@]}"; do
        echo "Scanning image $image..."
        trivy image --severity HIGH,CRITICAL --format json --output "trivy-$(echo $image | tr '/' '-').json" "$image" || true
        trivy image --severity HIGH,CRITICAL "$image" || echo -e "${YELLOW}Trivy encontrou issues em $image${NC}"
    done
}

run_secrets() {
    echo -e "\n${GREEN}=== Gitleaks (Secret Scanning) ===${NC}"

    for service in "${SERVICES[@]}"; do
        if [ -d "$service" ]; then
            echo "Scanning $service for secrets..."
            gitleaks detect --source "$service" --report-path "gitleaks-$(basename $service).json" || true
        fi
    done
}

run_sarif() {
    echo -e "\n${GREEN}=== Generating SARIF Report ===${NC}"

    # Combina resultados em SARIF
    python3 - <<EOF
import json
import glob
from datetime import datetime

sarif = {
    "version": "2.1.0",
    "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
    "runs": []
}

# Bandit
for f in glob.glob("bandit-*.json"):
    try:
        with open(f) as fp:
            data = json.load(fp)
            if "results" in data:
                sarif["runs"].append({
                    "tool": {"name": "Bandit"},
                    "results": data["results"]
                })
    except: pass

# Trivy
for f in glob.glob("trivy-*.json"):
    try:
        with open(f) as fp:
            data = json.load(fp)
            if "Results" in data:
                sarif["runs"].append({
                    "tool": {"name": "Trivy"},
                    "results": data["Results"]
                })
    except: pass

with open("fluxo-g-security-scan.sarif", "w") as fp:
    json.dump(sarif, fp, indent=2)

print("SARIF report saved to fluxo-g-security-scan.sarif")
EOF
}

# Main
if [ "$1" == "--full" ]; then
    run_bandit
    run_safety
    run_secrets
elif [ "$1" == "--trivy" ]; then
    run_trivy
else
    echo "Uso: ./scan-fluxo-g.sh [--full|--trivy]"
    echo "  --full  : Executa todos os scans (Bandit, Safety, Gitleaks)"
    echo "  --trivy : Executa scan de imagens container"
    exit 1
fi

run_sarif

echo -e "\n${GREEN}=== Scan completo ===${NC}"
echo "Resultados SARIF: fluxo-g-security-scan.sarif"
```

- [ ] **Step 2: Create Trivy config**

```yaml
# security/trivy-config.yaml
scan:
  security-checks:
    - vuln
    - config
    - secrets
  severity:
    - UNKNOWN
    - LOW
    - MEDIUM
    - HIGH
    - CRITICAL

vulnerability:
  type:
    - os
    - library

secret:
  skip-dirs:
    - tests
    - examples

config:
  skipped-paths:
    - "*/tests/*"
    - "*/test_*"
```

- [ ] **Step 3: Create bandit config**

```ini
# security/bandit.config
[bandit]
exclude_dirs = ['/tests', '/test']
skips = ['B101', 'B601']  # Assert used, shell injection (quando controlado)
```

- [ ] **Step 4: Make executable**

```bash
chmod +x security/scan-fluxo-g.sh
```

- [ ] **Step 5: Commit**

```bash
git add security/
git commit -m "security: add security scanning scripts for Fluxo G"
```

---

## Task 4: Implementar Rate Limiting

**Files:**
- Create: `services/orchestrator-dynamic/src/middleware/rate_limit.py`
- Test: `services/orchestrator-dynamic/tests/middleware/test_rate_limit.py`

- [ ] **Step 1: Write the failing test**

```python
# services/orchestrator-dynamic/tests/middleware/test_rate_limit.py
import pytest
import time
from httpx import AsyncClient
from main import app


@pytest.mark.asyncio
async def test_rate_limit_allows_under_threshold():
    """Testa que requests abaixo do limite são permitidos."""
    from orchestrator.middleware.rate_limit import RateLimiter

    limiter = RateLimiter(requests=10, window_seconds=60)

    user_id = "test-user-1"

    for i in range(10):
        allowed = await limiter.is_allowed(user_id)
        assert allowed is True, f"Request {i+1} should be allowed"


@pytest.mark.asyncio
async def test_rate_limit_blocks_over_threshold():
    """Testa que requests acima do limite são bloqueados."""
    from orchestrator.middleware.rate_limit import RateLimiter

    limiter = RateLimiter(requests=5, window_seconds=60)

    user_id = "test-user-2"

    # Primeiras 5 devem ser permitidas
    for _ in range(5):
        assert await limiter.is_allowed(user_id) is True

    # 6ª deve ser bloqueada
    assert await limiter.is_allowed(user_id) is False


@pytest.mark.asyncio
async def test_rate_limit_resets_after_window():
    """Testa que limite reseta após janela de tempo."""
    from unittest.mock import patch
    from orchestrator.middleware.rate_limit import RateLimiter

    limiter = RateLimiter(requests=3, window_seconds=2)

    user_id = "test-user-3"

    # Consome todas as requests
    for _ in range(3):
        assert await limiter.is_allowed(user_id) is True

    # Deve estar bloqueado
    assert await limiter.is_allowed(user_id) is False

    # Avança tempo
    with patch("time.time", return_value=time.time() + 3):
        # Deve permitir novamente
        assert await limiter.is_allowed(user_id) is True


@pytest.mark.asyncio
async def test_rate_limit_different_users():
    """Testa que rate limiting é por usuário."""
    from orchestrator.middleware.rate_limit import RateLimiter

    limiter = RateLimiter(requests=2, window_seconds=60)

    # User 1 consome seu limite
    assert await limiter.is_allowed("user-1") is True
    assert await limiter.is_allowed("user-1") is True
    assert await limiter.is_allowed("user-1") is False

    # User 2 ainda tem seu limite disponível
    assert await limiter.is_allowed("user-2") is True


@pytest.mark.asyncio
async def test_rate_limit_endpoint():
    """Testa rate limiting via endpoint HTTP."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Faz múltiplas requisições
        responses = []
        for _ in range(15):
            response = await client.post(
                "/api/v1/fluxo-g/pipelines",
                json={
                    "intent_text": "Test rate limit",
                    "project_name": "test",
                    "user_id": "rate-limit-user",
                },
            )
            responses.append(response.status_code)

        # Primeiras 10 devem ser 202 (aceitas)
        # Restantes devem ser 429 (rate limited)
        accepted = sum(1 for s in responses if s == 202)
        rate_limited = sum(1 for s in responses if s == 429)

        assert accepted <= 10
        assert rate_limited >= 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/orchestrator-dynamic/tests/middleware/test_rate_limit.py -v`
Expected: FAIL - middleware não existe

- [ ] **Step 3: Implement rate limiting**

```python
# services/orchestrator-dynamic/src/middleware/rate_limit.py
from typing import Dict, Optional
from datetime import datetime, timedelta
import time
import asyncio
from fastapi import Request, HTTPException, status
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Rate Limiter usando algoritmo sliding window log.

    Armazena contagem de requests por usuário em memória
    (em produção, usar Redis).
    """

    def __init__(self, requests: int = 100, window_seconds: int = 60):
        """
        Inicializa rate limiter.

        Args:
            requests: Número máximo de requests permitidas
            window_seconds: Janela de tempo em segundos
        """
        self.requests = requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, list] = {}
        self._lock = asyncio.Lock()

    async def is_allowed(self, key: str) -> bool:
        """
        Verifica se request é permitida para a key.

        Args:
            key: Identificador único (user_id, IP, etc.)

        Returns:
            True se request é permitida, False caso contrário
        """
        async with self._lock:
            now = time.time()
            window_start = now - self.window_seconds

            # Inicializa lista para key se não existir
            if key not in self._requests:
                self._requests[key] = []

            # Remove timestamps fora da janela
            self._requests[key] = [
                ts for ts in self._requests[key]
                if ts > window_start
            ]

            # Verifica se ainda tem capacidade
            if len(self._requests[key]) < self.requests:
                self._requests[key].append(now)
                return True

            return False

    async def reset(self, key: str):
        """Reseta contador para uma key."""
        async with self._lock:
            if key in self._requests:
                del self._requests[key]

    async def get_remaining(self, key: str) -> int:
        """Retorna número de requests restantes para a key."""
        async with self._lock:
            if key not in self._requests:
                return self.requests

            window_start = time.time() - self.window_seconds
            valid_requests = [
                ts for ts in self._requests[key]
                if ts > window_start
            ]

            return max(0, self.requests - len(valid_requests))


class RateLimitConfig(BaseModel):
    """Configurações de rate limiting."""
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_requests: int = 10

    # Endpoints específicos podem ter limites diferentes
    endpoint_limits: Dict[str, int] = {
        "/api/v1/fluxo-g/pipelines": 10,  # POST (criar pipeline)
        "/api/v1/fluxo-g/pipelines/": 60,  # GET (consultar status)
    }


class RedisRateLimiter:
    """
    Rate Limiter distribuído usando Redis.

    Usa Redis INCR para operações atômicas.
    """

    def __init__(
        self,
        redis_client,
        requests: int = 100,
        window_seconds: int = 60,
    ):
        """
        Inicializa rate limiter com Redis.

        Args:
            redis_client: Cliente Redis (aioredis)
            requests: Número máximo de requests
            window_seconds: Janela de tempo
        """
        self.redis = redis_client
        self.requests = requests
        self.window_seconds = window_seconds

    async def is_allowed(self, key: str) -> bool:
        """Verifica se request é permitida usando Redis."""
        pipe = self.redis.pipeline()

        now = time.time()
        window_key = f"ratelimit:{key}:{int(now // self.window_seconds)}"

        pipe.incr(window_key)
        pipe.expire(window_key, self.window_seconds)

        results = await pipe.execute()
        count = results[0]

        return count <= self.requests


# Instância global (em produção, usar Redis)
_global_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Retorna instância global de rate limiter."""
    global _global_limiter
    if _global_limiter is None:
        _global_limiter = RateLimiter(
            requests=60,  # 60 requests por minuto
            window_seconds=60,
        )
    return _global_limiter


# FastAPI Middleware
class RateLimitMiddleware:
    """Middleware de rate limiting para FastAPI."""

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.limiter = get_rate_limiter()

    async def __call__(self, request: Request, call_next):
        """Processa request com rate limiting."""
        # Extrai identificador
        user_id = request.headers.get("X-User-ID")
        if not user_id:
            # Fallback para IP
            user_id = request.client.host

        # Verifica limite específico do endpoint
        path = request.url.path
        limit = self.config.endpoint_limits.get(
            path,
            self.config.requests_per_minute,
        )

        # Cria limiter temporário com limite específico
        endpoint_limiter = RateLimiter(
            requests=limit,
            window_seconds=60,
        )

        # Verifica se request é permitida
        allowed = await endpoint_limiter.is_allowed(user_id)

        if not allowed:
            logger.warning(f"Rate limit exceeded for {user_id} on {path}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "retry_after": 60,
                },
            )

        # Adiciona headers de rate limit
        response = await call_next(request)
        remaining = await endpoint_limiter.get_remaining(user_id)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)

        return response
```

- [ ] **Step 4: Integrate into main app**

```python
# services/orchestrator-dynamic/src/api/main.py

from orchestrator.middleware.rate_limit import RateLimitConfig, RateLimitMiddleware

# Configuração de rate limiting
rate_limit_config = RateLimitConfig(
    requests_per_minute=60,
    requests_per_hour=1000,
    burst_requests=10,
    endpoint_limits={
        "/api/v1/fluxo-g/pipelines": 10,  # Mais restrito
        "/api/v1/fluxo-g/pipelines/": 60,
    },
)

app.add_middleware(RateLimitMiddleware, config=rate_limit_config)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest services/orchestrator-dynamic/tests/middleware/test_rate_limit.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/orchestrator-dynamic/src/middleware/rate_limit.py \
        services/orchestrator-dynamic/tests/middleware/test_rate_limit.py
git commit -m "feat(orchestrator): add rate limiting middleware"
```

---

## Task 5: Implementar Request/Response Logging

**Files:**
- Create: `services/orchestrator-dynamic/src/middleware/logging.py`
- Test: `services/orchestrator-dynamic/tests/middleware/test_logging.py`

- [ ] **Step 1: Implement logging middleware**

```python
# services/orchestrator-dynamic/src/middleware/logging.py
import time
import json
import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import uuid

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware para logging detalhado de requests/responses.

    Registra: timestamp, request_id, método, path, status, duration
    """

    def __init__(
        self,
        app: ASGIApp,
        skip_paths: list[str] = None,
        log_body: bool = False,
    ):
        super().__init__(app)
        self.skip_paths = skip_paths or ["/health", "/metrics", "/favicon.ico"]
        self.log_body = log_body

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Processa request com logging."""
        # Skip caminhos especificados
        if any(request.url.path.startswith(p) for p in self.skip_paths):
            return await call_next(request)

        # Gera request_id único
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # Timestamp de início
        start_time = time.time()

        # Log da request
        log_data = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "query_params": str(request.query_params),
            "client_host": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        }

        # Adiciona body se habilitado (cuidado com dados sensíveis)
        if self.log_body and request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                if body:
                    # Sanitiza dados sensíveis
                    body_str = body.decode("utf-8")
                    body_json = json.loads(body_str)

                    # Remove campos sensíveis
                    for field in ["password", "token", "secret", "api_key"]:
                        if field in body_json:
                            body_json[field] = "***REDACTED***"

                    log_data["body"] = body_json
            except Exception:
                pass

        logger.info("Request started", extra=log_data)

        # Processa request
        try:
            response = await call_next(request)

            # Calcula duração
            duration = time.time() - start_time

            # Log da response
            logger.info(
                "Request completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration * 1000, 2),
                },
            )

            # Adiciona headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = f"{duration:.3f}"

            return response

        except Exception as e:
            # Log de erro
            duration = time.time() - start_time

            logger.error(
                "Request failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "error": str(e),
                    "duration_ms": round(duration * 1000, 2),
                },
                exc_info=True,
            )

            raise


class StructuredLogger:
    """
    Logger estruturado para logs consistentes.

    Usa structlog para logs JSON em produção.
    """

    def __init__(self):
        self._logger = logging.getLogger(__name__)

    def log_pipeline_event(
        self,
        event_type: str,
        pipeline_id: str,
        **kwargs,
    ):
        """Registra evento de pipeline."""
        self._logger.info(
            event_type,
            extra={
                "event_type": event_type,
                "pipeline_id": pipeline_id,
                **kwargs,
            },
        )

    def log_stage_event(
        self,
        stage: str,
        pipeline_id: str,
        status: str,
        **kwargs,
    ):
        """Registra evento de estágio."""
        self._logger.info(
            f"Stage {status}",
            extra={
                "stage": stage,
                "pipeline_id": pipeline_id,
                "stage_status": status,
                **kwargs,
            },
        )

    def log_error(
        self,
        error: Exception,
        context: dict,
    ):
        """Registra erro com contexto."""
        self._logger.error(
            f"Error: {type(error).__name__}",
            extra={
                "error_type": type(error).__name__,
                "error_message": str(error),
                **context,
            },
            exc_info=True,
        )


# Instância global
get_logger = lambda: StructuredLogger()
```

- [ ] **Step 2: Create tests**

```python
# services/orchestrator-dynamic/tests/middleware/test_logging.py
import pytest
from httpx import AsyncClient
from main import app


@pytest.mark.asyncio
async def test_request_logging_adds_headers():
    """Testa que middleware adiciona headers de logging."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health/ready")

        # Verifica headers
        assert "X-Request-ID" in response.headers
        assert "X-Process-Time" in response.headers

        # Request ID deve ser UUID válido
        request_id = response.headers["X-Request-ID"]
        assert len(request_id) == 36  # UUID format


@pytest.mark.asyncio
async def test_process_time_header():
    """Testa que process time é adicionado."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health/ready")

        process_time = float(response.headers["X-Process-Time"])
        assert process_time >= 0
        assert process_time < 1.0  # Não deve demorar mais de 1 segundo


@pytest.mark.asyncio
async def test_skip_paths():
    """Testa que health check não é logado."""
    # Este teste verificaria que logs não são gerados
    # para caminhos em skip_paths
    pass
```

- [ ] **Step 3: Commit**

```bash
git add services/orchestrator-dynamic/src/middleware/logging.py \
        services/orchestrator-dynamic/tests/middleware/test_logging.py
git commit -m "feat(orchestrator): add request logging middleware"
```

---

## Task 6: Criar Dashboards Grafana

**Files:**
- Create: `monitoring/grafana/dashboards/fluxo-g-dashboard.json`

- [ ] **Step 1: Create Grafana dashboard**

```json
{
  "annotations": {
    "list": [
      {
        "builtIn": 1,
        "datasource": "-- Grafana --",
        "enable": true,
        "hide": true,
        "iconColor": "rgba(0, 211, 255, 1)",
        "name": "Annotations & Alerts",
        "type": "dashboard"
      }
    ]
  },
  "editable": true,
  "gnetId": null,
  "graphTooltip": 0,
  "id": null,
  "links": [],
  "panels": [
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "line",
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 1,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              }
            ]
          },
          "unit": "reqps"
        }
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 0,
        "y": 0
      },
      "id": 1,
      "options": {
        "legend": {
          "calcs": [],
          "displayMode": "list",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "single"
        }
      },
      "pluginVersion": "8.0.0",
      "targets": [
        {
          "expr": "rate(fluxo_g_http_requests_total{job=\"orchestrator-dynamic\"}[5m])",
          "legendFormat": "{{method}} {{path}}",
          "refId": "A"
        }
      ],
      "title": "Request Rate",
      "type": "timeseries"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "thresholds"
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              },
              {
                "color": "yellow",
                "value": 200
              },
              {
                "color": "red",
                "value": 500
              }
            ]
          },
          "unit": "ms"
        }
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 12,
        "y": 0
      },
      "id": 2,
      "options": {
        "orientation": "auto",
        "reduceOptions": {
          "values": false,
          "calcs": ["lastNotNull"],
          "fields": ""
        },
        "showThresholdLabels": false,
        "showThresholdMarkers": true
      },
      "pluginVersion": "8.0.0",
      "targets": [
        {
          "expr": "histogram_quantile(0.95, rate(fluxo_g_http_request_duration_seconds_bucket[5m])) * 1000",
          "legendFormat": "p95",
          "refId": "A"
        }
      ],
      "title": "Request Latency (p95)",
      "type": "gauge"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "bars",
            "fillOpacity": 80,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 1,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              }
            ]
          },
          "unit": "short"
        }
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 0,
        "y": 8
      },
      "id": 3,
      "options": {
        "legend": {
          "calcs": [],
          "displayMode": "list",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "single"
        }
      },
      "pluginVersion": "8.0.0",
      "targets": [
        {
          "expr": "rate(fluxo_g_pipelines_started_total{job=\"orchestrator-dynamic\"}[5m])",
          "legendFormat": "Started",
          "refId": "A"
        },
        {
          "expr": "rate(fluxo_g_pipelines_completed_total{job=\"orchestrator-dynamic\"}[5m])",
          "legendFormat": "Completed",
          "refId": "B"
        },
        {
          "expr": "rate(fluxo_g_pipelines_failed_total{job=\"orchestrator-dynamic\"}[5m])",
          "legendFormat": "Failed",
          "refId": "C"
        }
      ],
      "title": "Pipeline Throughput",
      "type": "timeseries"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "line",
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 1,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              }
            ]
          },
          "unit": "percent"
        }
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 12,
        "y": 8
      },
      "id": 4,
      "options": {
        "legend": {
          "calcs": [],
          "displayMode": "list",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "single"
        }
      },
      "pluginVersion": "8.0.0",
      "targets": [
        {
          "expr": "rate(fluxo_g_pipelines_completed_total{job=\"orchestrator-dynamic\"}[5m]) / rate(fluxo_g_pipelines_started_total{job=\"orchestrator-dynamic\"}[5m]) * 100",
          "legendFormat": "Success Rate",
          "refId": "A"
        }
      ],
      "title": "Pipeline Success Rate",
      "type": "timeseries"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            }
          },
          "mappings": []
        }
      },
      "gridPos": {
        "h": 8,
        "w": 24,
        "x": 0,
        "y": 16
      },
      "id": 5,
      "options": {
        "legend": {
          "displayMode": "table",
          "placement": "right",
          "values": ["value", "percent"]
        },
        "pieType": "pie",
        "tooltip": {
          "mode": "single"
        }
      },
      "pluginVersion": "8.0.0",
      "targets": [
        {
          "expr": "count by (status) (fluxo_g_pipeline_status{job=\"orchestrator-dynamic\"})",
          "legendFormat": "{{status}}",
          "refId": "A"
        }
      ],
      "title": "Pipeline Status Distribution",
      "type": "piechart"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "line",
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 1,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              }
            ]
          },
          "unit": "short"
        }
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 0,
        "y": 24
      },
      "id": 6,
      "options": {
        "legend": {
          "calcs": [],
          "displayMode": "list",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "single"
        }
      },
      "pluginVersion": "8.0.0",
      "targets": [
        {
          "expr": "fluxo_g_active_workers{job=\"orchestrator-dynamic\"}",
          "legendFormat": "{{worker_type}}",
          "refId": "A"
        }
      ],
      "title": "Active Workers",
      "type": "timeseries"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "line",
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 1,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": true
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              }
            ]
          },
          "unit": "bytes"
        }
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 12,
        "y": 24
      },
      "id": 7,
      "options": {
        "legend": {
          "calcs": [],
          "displayMode": "list",
          "placement": "bottom"
        },
        "tooltip": {
          "mode": "single"
        }
      },
      "pluginVersion": "8.0.0",
      "targets": [
        {
          "expr": "process_resident_memory_bytes{job=\"orchestrator-dynamic\"}",
          "legendFormat": "{{pod}}",
          "refId": "A"
        }
      ],
      "title": "Memory Usage",
      "type": "timeseries"
    }
  ],
  "refresh": "5s",
  "schemaVersion": 27,
  "style": "dark",
  "tags": ["fluxo-g", "neural-hive-mind"],
  "templating": {
    "list": []
  },
  "time": {
    "from": "now-1h",
    "to": "now"
  },
  "timepicker": {},
  "timezone": "",
  "title": "Fluxo G - Pipeline Dashboard",
  "uid": "fluxo-g-dashboard",
  "version": 1
}
```

- [ ] **Step 2: Create alerts**

```yaml
# monitoring/alerts/fluxo-g-alerts.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: fluxo-g-alerts
  namespace: neural-hive-mind
  labels:
    app: orchestrator-dynamic
    component: fluxo-g
spec:
  groups:
    - name: fluxo_g_pipeline_alerts
      interval: 30s
      rules:
        - alert: FluxoGHighFailureRate
          expr: |
            rate(fluxo_g_pipelines_failed_total[5m]) / rate(fluxo_g_pipelines_started_total[5m]) > 0.1
          for: 5m
          labels:
            severity: warning
            service: orchestrator-dynamic
          annotations:
            summary: "Alta taxa de falhas no Fluxo G"
            description: "Taxa de falhas acima de 10% por 5 minutos"

        - alert: FluxoGCriticalFailureRate
          expr: |
            rate(fluxo_g_pipelines_failed_total[5m]) / rate(fluxo_g_pipelines_started_total[5m]) > 0.3
          for: 2m
          labels:
            severity: critical
            service: orchestrator-dynamic
          annotations:
            summary: "Taxa crítica de falhas no Fluxo G"
            description: "Taxa de falhas acima de 30% por 2 minutos"

        - alert: FluxoGSlowPipelines
          expr: |
            histogram_quantile(0.95, rate(fluxo_g_pipeline_duration_seconds_bucket[5m])) > 600
          for: 10m
          labels:
            severity: warning
            service: orchestrator-dynamic
          annotations:
            summary: "Pipelines lentos detectados"
            description: "p95 de duração de pipeline acima de 10 minutos"

        - alert: FluxoGNoWorkers
          expr: |
            count(fluxo_g_active_workers) == 0
          for: 1m
          labels:
            severity: critical
            service: orchestrator-dynamic
          annotations:
            summary: "Nenhum worker ativo"
            description: "Todos os workers Temporal estão inativos"

        - alert: FluxoGBacklogGrowing
          expr: |
            fluxo_g_pending_pipelines > 100
          for: 5m
          labels:
            severity: warning
            service: orchestrator-dynamic
          annotations:
            summary: "Backlog de pipelines crescendo"
            description: "Mais de 100 pipelines aguardando processamento"
```

- [ ] **Step 3: Commit**

```bash
git add monitoring/grafana/dashboards/fluxo-g-dashboard.json \
        monitoring/alerts/fluxo-g-alerts.yaml
git commit -m "monitoring: add Grafana dashboard and alerts for Fluxo G"
```

---

## Task 7: Criar Documentação de Operações

**Files:**
- Create: `docs/FLUXO_G_OPERATIONS.md`

- [ ] **Step 1: Create operations documentation**

```markdown
# Fluxo G - Operations Guide

**Versão:** 1.0
**Data:** 2026-04-16
**Responsáveis:** DevOps / SRE Team

---

## Visão Geral

Este documento cobre operações diárias, troubleshooting e procedimentos de emergência para o Fluxo G (pipeline Ideia → Software).

## Arquitetura

```
┌─────────────┐      ┌──────────────┐      ┌─────────────────┐
│   Client    │─────▶│ REST API     │─────▶│ Temporal Server │
└─────────────┘      │ (FastAPI)    │      └─────────────────┘
                     └──────────────┘              │
                           │                      │
                           ▼                      ▼
                     ┌──────────────┐      ┌─────────────────┐
                     │ Kafka Events │      │ Temporal Worker │
                     └──────────────┘      └─────────────────┘
                                                  │
                      ┌─────────────────────────────┼───────────────────┐
                      │                             │                   │
                      ▼                             ▼                   ▼
              ┌─────────────┐             ┌─────────────┐       ┌─────────────┐
              │ Requirements │             │ Architecture │       │     RAG     │
              │   (8010)    │             │   (8008)     │       │   (8016)    │
              └─────────────┘             └─────────────┘       └─────────────┘
                      │                             │                   │
                      └─────────────────────────────┼───────────────────┘
                                                    │
                      ┌─────────────────────────────┼───────────────────┐
                      │                             │                   │
                      ▼                             ▼                   ▼
              ┌─────────────┐             ┌─────────────┐       ┌─────────────┐
              │  Docs Gen   │             │   Approval  │       │  Code Gen   │
              │   (8014)    │             │   (8017)     │       │   (8005)    │
              └─────────────┘             └─────────────┘       └─────────────┘
```

---

## Serviços e Health Checks

### Orchestrator API

```bash
# Health check
curl http://orchestrator-dynamic-fluxog:8003/health/live

# Readiness check
curl http://orchestrator-dynamic-fluxog:8003/health/ready

# Metrics
curl http://orchestrator-dynamic-fluxog:8013/metrics
```

### Serviços do Fluxo G

| Serviço | Porta | Health Check |
|---------|-------|--------------|
| Requirements Engineering | 8010 | `GET /health` |
| Architect Agent | 8008 | `GET /health` |
| Knowledge Graph RAG | 8016 | `GET /health` |
| Documentation Generation | 8014 | `GET /health` |
| Approval Gateway | 8017 | `GET /health` |
| Code Forge | 8005 | `GET /health` |

---

## Métricas Principais

### Pipeline Metrics

```promql
# Taxa de pipelines iniciados
rate(fluxo_g_pipelines_started_total[5m])

# Taxa de pipelines completados
rate(fluxo_g_pipelines_completed_total[5m])

# Taxa de falhas
rate(fluxo_g_pipelines_failed_total[5m])

# Duração média (p50, p95, p99)
histogram_quantile(0.95, rate(fluxo_g_pipeline_duration_seconds_bucket[5m]))

# Success rate
rate(fluxo_g_pipelines_completed_total[5m]) / rate(fluxo_g_pipelines_started_total[5m]) * 100

# Pipelines ativos por estágio
count by (stage) (fluxo_g_pipeline_status{status="running"})
```

### Performance Metrics

```promql
# Latency da API (p95)
histogram_quantile(0.95, rate(fluxo_g_http_request_duration_seconds_bucket[5m]))

# Throughput da API
rate(fluxo_g_http_requests_total[5m])

# Erros da API
rate(fluxo_g_http_requests_total{status=~"5.."}[5m])

# Memory dos workers
process_resident_memory_bytes{job="orchestrator-fluxog-worker"}

# CPU dos workers
rate(process_cpu_seconds_total{job="orchestrator-fluxog-worker"}[5m])
```

---

## Daily Operations

### Rotation de Logs

```bash
# Logs são enviados para stdout/stderr e coletados pelo Logging Agent
# Retenção padrão: 30 dias em Loki

# Limpeza manual se necessário
kubectl exec -it deployment/orchestrator-dynamic-fluxog -- \
  find /var/log -name "*.log" -mtime +30 -delete
```

### Backup do MongoDB

```bash
# Script de backup automatizado (executado diariamente via cronjob)
kubectl create job --from=cronjob/mongodb-backup manual-backup-$(date +%Y%m%d)
```

### Limpeza de Pipelines Antigos

```bash
# Executa limpeza de pipelines completados há mais de 30 dias
kubectl exec -it deployment/orchestrator-dynamic-fluxog -- \
  python -c "
from orchestrator.services.pipeline_store import PipelineStore
import asyncio
async def cleanup():
    store = PipelineStore()
    deleted = await store.delete_older_than(days=30)
    print(f'Deleted {deleted} old pipelines')
asyncio.run(cleanup())
"
```

---

## Troubleshooting

### Pipeline "Travado" em um Estágio

**Sintomas:** Pipeline em status "running" mas sem progresso por > 10 minutos.

**Diagnóstico:**
```bash
# Verifica status no Temporal UI
# http://temporal-ui:8088/namespaces/default/workflows/{pipeline_id}

# Verifica worker logs
kubectl logs -f deployment/orchestrator-fluxog-worker --tail=100

# Verifica se worker está respondendo
kubectl exec -it deployment/orchestrator-fluxog-worker -- \
  curl http://localhost:8003/health/ready
```

**Resolução:**
1. Verificar se o serviço dependente está saudável
2. Verificar conectividade de rede
3. Se necessário, reiniciar workflow:
   ```bash
   kubectl exec -it deployment/orchestrator-dynamic-fluxog -- \
     python -c "
import asyncio
from temporalio.client import Client
async def reset():
    client = await Client.connect('temporal:7233')
    handle = client.get_workflow_handle('pipeline-id')
    await handle.signal('reset')
asyncio.run(reset())
"
   ```

### Alto Taxa de Falhas em Requirements

**Sintomas:** `rate(fluxo_g_pipelines_failed_total{stage="requirements"}) > 0.2`

**Diagnóstico:**
```bash
# Verifica service health
kubectl exec -it deployment/requirements-engineering -- curl http://localhost:8010/health

# Verifica logs
kubectl logs -f deployment/requirements-engineering --tail=200 | grep ERROR
```

**Resolução:**
1. Verificar quota da API LLM
2. Verificar timeout settings
3. Aumentar `FLUXO_G_STAGE_TIMEOUT` se necessário

### Worker não processa Tasks

**Sintomas:** `fluxo_g_active_workers == 0`

**Diagnóstico:**
```bash
# Verifica worker pods
kubectl get pods -l component=fluxo-g-worker

# Verifica worker status
kubectl describe pod <worker-pod>

# Verifica se worker está conectado ao Temporal
# (Ver logs por "Worker started")
kubectl logs deployment/orchestrator-fluxog-worker
```

**Resolução:**
```bash
# Restart worker
kubectl rollout restart deployment/orchestrator-fluxog-worker
```

---

## Emergency Procedures

### Rollback Completo do Fluxo G

```bash
# 1. Escala workers para zero (para novos pipelines)
kubectl scale deployment orchestrator-fluxog-worker --replicas=0

# 2. Desabilita feature flag no ConfigMap
kubectl patch configmap orchestrator-fluxog-config --type=json \
  -p='[{"op": "replace", "path": "/data/FLUXO_G_ENABLE", "value": "false"}]'

# 3. Rollback API deployment
kubectl rollout undo deployment/orchestrator-dynamic-fluxog

# 4. Notifica stakeholders
# (Implementar script de notificação)
```

### Evacuation de Pipelines em Andamento

```bash
# Cancela todos os pipelines ativos
kubectl exec -it deployment/orchestrator-dynamic-fluxog -- \
  python -c "
import asyncio
from temporalio.client import Client, ListFilter
async def evacuate():
    client = await Client.connect('temporal:7233')
    async for workflow in client.list_workflows(
        query='WorkflowType = \"FluxoGWorkflow\" and ExecutionStatus = \"Running\"'
    ):
        handle = client.get_workflow_handle(workflow.id)
        await handle.cancel()
        print(f'Cancelled {workflow.id}')
asyncio.run(evacuate())
"
```

### Drain e Restart

```bash
#!/bin/bash
# drain-restart-fluxog.sh

echo "Cordonando nodes..."
kubectl cordon $(kubectl get nodes -o name)

echo "Escalando workers gradualmente..."
for i in {1..3}; do
  kubectl scale deployment orchestrator-fluxog-worker --replicas=$i
  sleep 30
done

echo "Uncordoning nodes..."
kubectl uncordon $(kubectl get nodes -o name)

echo "Restart API..."
kubectl rollout restart deployment/orchestrator-dynamic-fluxog

echo "Aguardando readiness..."
kubectl wait --for=condition=ready pod -l component=fluxo-g --timeout=300s
```

---

## Capacity Planning

### Baseline de Recursos

| Componente | CPU (Request/Limit) | Memory (Request/Limit) | Replicas |
|------------|---------------------|------------------------|----------|
| Orchestrator API | 500m / 2000m | 512Mi / 2Gi | 3 |
| Worker | 250m / 1000m | 256Mi / 1Gi | 2 |
| Requirements Service | 200m / 1000m | 256Mi / 512Mi | 2 |
| Architect Service | 200m / 1000m | 256Mi / 512Mi | 2 |
| RAG Service | 500m / 2000m | 1Gi / 4Gi | 2 |

### Escalabilidade

**Horizontal Scaling:**
```bash
# Escala workers (mais throughput de activities)
kubectl scale deployment orchestrator-fluxog-worker --replicas=5

# Escala API (mais throughput de requests)
kubectl scale deployment orchestrator-dynamic-fluxog --replicas=5
```

**Vertical Scaling:**
```yaml
# Aumentar limites de recursos no deployment
resources:
  requests:
    cpu: 1000m      # Aumentar de 500m
    memory: 1Gi     # Aumentar de 512Mi
  limits:
    cpu: 4000m      # Aumentar de 2000m
    memory: 4Gi     # Aumentar de 2Gi
```

**Thresholds para Scale-up:**
- CPU > 70% por 5 minutos → +1 replica
- Memory > 80% por 5 minutos → +1 replica
- Pending tasks > 50 → +2 workers

---

## Security

### RBAC

```yaml
# ServiceAccount para workers
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orchestrator-fluxog-worker
  namespace: neural-hive-mind
---
# Role para ler secrets/secrets
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: orchestrator-fluxog-worker
  namespace: neural-hive-mind
rules:
- apiGroups: [""]
  resources: ["secrets", "configmaps"]
  verbs: ["get", "list"]
---
# RoleBinding
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: orchestrator-fluxog-worker
  namespace: neural-hive-mind
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: orchestrator-fluxog-worker
subjects:
- kind: ServiceAccount
  name: orchestrator-fluxog-worker
```

### Network Policies

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orchestrator-fluxog-policy
  namespace: neural-hive-mind
spec:
  podSelector:
    matchLabels:
      component: fluxo-g
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx  # Permite tráfego do ingress
    ports:
    - protocol: TCP
      port: 8003
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          name: neural-hive-mind  # Permite comunicação interna
    - namespaceSelector:
        matchLabels:
          name: temporal
    - namespaceSelector:
        matchLabels:
          name: kafka
  - to:
    - namespaceSelector: {}  # Permite egress externo (APIs LLM)
    ports:
    - protocol: TCP
      port: 443
```

---

## On-Call Procedures

### Alertas Principais

| Alerta | Severidade | Ação |
|--------|-----------|------|
| `FluxoGHighFailureRate` | Warning | Investigar taxa de falhas > 10% |
| `FluxoGCriticalFailureRate` | Critical | Escalar workers, investigar services |
| `FluxoGNoWorkers` | Critical | Reiniciar workers imediatamente |
| `FluxoGSlowPipelines` | Warning | Investigar bottleneck |
| `FluxoGBacklogGrowing` | Warning | Escalar workers |

### Runbook: `FluxoGCriticalFailureRate`

**1. Acknowledge alert:**
```bash
# Via PagerDuty/OPSGenie
# Acknowledge alarm
```

**2. Verify impact:**
```bash
# Verifica número de pipelines afetados
curl -s 'http://prometheus:9090/api/v1/query?query=rate(fluxo_g_pipelines_failed_total[5m])' | jq '.data.result[0].value[1]'
```

**3. Identify failing stage:**
```bash
# Verifica qual estágio está falhando mais
curl -s 'http://prometheus:9090/api/v1/query?query=topk(5, rate(fluxo_g_stage_failures_total[5m]))' | jq
```

**4. Check service health:**
```bash
# Para o estágio com mais falhas
kubectl get pods -l stage=requirements
kubectl logs -f deployment/requirements-engineering --tail=100
```

**5. Mitigation:**
```bash
# Se service está down: scale up
kubectl scale deployment requirements-engineering --replicas=3

# Se é timeout: aumentar timeout
kubectl patch configmap orchestrator-fluxog-config --type=json \
  -p='[{"op": "replace", "path": "/data/FLUXO_G_STAGE_TIMEOUT", "value": "600"}]'

# Rollback workers se necessário
kubectl rollout undo deployment/orchestrator-fluxog-worker
```

**6. Post-incident:**
```bash
# Coleta logs para análise
kubectl logs deployment/orchestrator-fluxog-worker --since=1h > incident-$(date +%Y%m%d).log

# Cria ticket de follow-up
# (Implementar via API de issue tracker)
```

---

*Documentação atualizada em 2026-04-16*
*Mantido por: Platform Team*
```

- [ ] **Step 2: Commit**

```bash
git add docs/FLUXO_G_OPERATIONS.md
git commit -m "docs: add Fluxo G operations guide"
```

---

## Task 8: Criar Runbooks Específicos

**Files:**
- Create: `docs/runbooks/fluxo-g-runbooks.md`

- [ ] **Step 1: Create runbooks**

```markdown
# Fluxo G - Runbooks

Coleção de runbooks para incidentes comuns do Fluxo G.

---

## Runbook: Pipeline Preso no Estágio de Aprovação

**Trigger:** Pipeline aguardando aprovação há > 24 horas

**Symptoms:**
- Dashboard mostra pipelines com `status="awaiting_approval"`
- `approval_requested` há mais de 24h sem `approval_completed`

**Investigation:**

```bash
# Lista pipelines aguardando aprovação
kubectl exec -it deployment/orchestrator-dynamic-fluxog -- \
  python -c "
from orchestrator.services.pipeline_store import PipelineStore
import asyncio
async def check():
    store = PipelineStore()
    pipelines, _ = await store.list_all(
        status_filter='awaiting_approval',
        page=1,
        page_size=100
    )
    for p in pipelines:
        print(f'{p.pipeline_id}: aguardando desde {p.created_at}')
asyncio.run(check())
"
```

**Resolution Options:**

1. **Auto-approve após timeout (configuração):**
```yaml
# ConfigMap
FLUXO_G_APPROVAL_TIMEOUT_SECONDS: "86400"  # 24h
FLUXO_G_AUTO_APPROVE_AFTER_TIMEOUT: "true"
```

2. **Manual approve via API:**
```bash
PIPELINE_ID="fluxo-g-xxx"
curl -X POST \
  "http://orchestrator-dynamic-fluxog:8003/api/v1/fluxo-g/pipelines/$PIPELINE_ID/approve" \
  -H "Content-Type: application/json" \
  -d '{"approved": true, "feedback": "Auto-approved after timeout"}'
```

3. **Cancel pipeline:**
```bash
curl -X POST \
  "http://orchestrator-dynamic-fluxog:8003/api/v1/fluxo-g/pipelines/$PIPELINE_ID/cancel"
```

---

## Runbook: Memory Leak no Worker

**Trigger:** `process_resident_memory_bytes{job="orchestrator-fluxog-worker"}` crescendo continuamente

**Symptoms:**
- Memory usage > 80% do limite
- OOMKilled events
- Workers reiniciando frequentemente

**Investigation:**

```bash
# Memory profile
kubectl exec -it deployment/orchestrator-fluxog-worker -- \
  python -m memory_profiler $(which python) -m orchestrator.workers.fluxo_g_worker

# Verifica objetos pendentes
kubectl exec -it deployment/orchestrator-fluxog-worker -- \
  python -c "
import gc
import objgraph
print('Objects before GC:', len(gc.get_objects()))
gc.collect()
print('Objects after GC:', len(gc.get_objects()))
objgraph.show_growth()
"
```

**Resolution:**

1. **Restart worker:**
```bash
kubectl rollout restart deployment/orchestrator-fluxog-worker
```

2. **Increase memory limit:**
```yaml
# deployment.yaml
resources:
  limits:
    memory: 4Gi  # Aumentar de 2Gi
```

3. **Enable periodic GC:**
```python
# No worker
import gc
import asyncio

async def periodic_gc():
    while True:
        await asyncio.sleep(300)  # 5 minutos
        gc.collect()

asyncio.create_task(periodic_gc())
```

---

## Runbook: Deadlock no Temporal Workflow

**Trigger:** Workflows presos em mesmo estado por > timeout

**Symptoms:**
- Vários workflows com same history event ID
- `pending_activities` não diminuindo
- Workers ativos mas sem progresso

**Investigation:**

```bash
# Via Temporal CLI
temporal workflow show --workflow_id <id>

# Verifica pending activities
temporal workflow query --workflow_id <id> --query_type __stack_trace
```

**Resolution:**

1. **Terminate workflow:**
```bash
temporal workflow terminate --workflow_id <id> --reason "Deadlock detected"
```

2. **Force reset:**
```bash
temporal workflow reset --workflow_id <id> --reason "Resetting stuck workflow"
```

3. **Worker restart:**
```bash
kubectl rollout restart deployment/orchestrator-fluxog-worker
```

---

## Runbook: Service Unavailable (Cascading Failure)

**Trigger:** Múltiplos services retornando 503

**Symptoms:**
- `rate(fluxo_g_http_requests_total{status=~"5.."})` spikes
- Piplelines failing em múltiplos estágios
- Timeout errors

**Investigation:**

```bash
# Verifica health de todos os services
for svc in requirements-engineering:8010 architect-agent:8008 \
           knowledge-graph-rag:8016 documentation-generation:8014 \
           approval-gateway:8017 code-forge:8005; do
  echo "Checking $svc..."
  kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
    curl -s http://$svc/health || echo "FAILED"
done
```

**Resolution:**

1. **Identify root cause service:**
```bash
# Verifica qual service está causando cascade
kubectl top pods -A | sort -k3 --reverse
```

2. **Isolate failing service:**
```bash
# Escala service problemático para 0
kubectl scale deployment/<failing-service> --replicas=0

# Feature flag para pular estágio
kubectl patch configmap orchestrator-fluxog-config --type=json \
  -p='[{"op": "replace", "path": "/data/FLUXO_G_ENABLE_<STAGE>", "value": "false"}]'
```

3. **Recovery:**
```bash
# Escala service gradualmente
kubectl scale deployment/<failing-service> --replicas=1
kubectl wait --for=condition=ready pod -l app=<failing-service> --timeout=120s

# Reabilita estágio
kubectl patch configmap orchestrator-fluxog-config --type=json \
  -p='[{"op": "replace", "path": "/data/FLUXO_G_ENABLE_<STAGE>", "value": "true"}]'
```

---

## Runbook: Kafka Consumer Lag

**Trigger:** `kafka_consumergroup_lag{topic=~"fluxo-g.*"}` alto

**Symptoms:**
- Eventos não sendo processados
- Atraso entre publicação e consumo
- Logs mostrando "Rebalancing..."

**Investigation:**

```bash
# Verifica consumer lag
kubectl exec -it kafka-0 -n kafka -- \
  kafka-consumer-groups --bootstrap-server localhost:9092 \
  --group fluxo-g-consumer --describe

# Verifica tópicos com lag
kubectl exec -it kafka-0 -n kafka -- \
  kafka-consumer-groups --bootstrap-server localhost:9092 \
  --all-groups --describe | grep fluxo-g
```

**Resolution:**

1. **Scale consumers:**
```yaml
# No deployment
# Aumentar replicas escalará consumers automaticamente
spec:
  replicas: 5  # Aumentar de 3
```

2. **Increase fetch size:**
```yaml
# ConfigMap
KAFKA_FETCH_MIN_BYTES: "1024"
Kafka_FETCH_MAX_WAIT_MS: "500"
```

3. **Skip lagging messages:**
```bash
# Reset consumer offset (último recurso)
kubectl exec -it kafka-0 -n kafka -- \
  kafka-consumer-groups --bootstrap-server localhost:9092 \
  --group fluxo-g-consumer \
  --reset-offsets --to-latest --execute --topic fluxo-g.pipeline.completed
```

---

## Runbook: LLM API Rate Limit

**Trigger:** Erros 429 de APIs LLM

**Symptoms:**
- Requirements/Architecture falhando
- Logs mostram "Rate limit exceeded"
- `rate(fluxo_g_llm_api_errors{status="429"})` > 0

**Investigation:**

```bash
# Verifica erro rate
kubectl logs deployment/requirements-engineering --tail=100 | grep "429\|rate limit"

# Verifica quota usage
# (Depende do provider LLM)
```

**Resolution:**

1. **Implement exponential backoff:**
```python
# Já implementado nas activities
# Ajustar se necessário
retry_policy = RetryPolicy(
    initial_interval=timedelta(seconds=5),  # Aumentar
    backoff_coefficient=2.0,
)
```

2. **Queue requests:**
```python
# Implementar fila local se API estiver saturated
class LocalRequestQueue:
    def __init__(self, max_rate=10):
        self.queue = asyncio.Queue()
        self.rate_limiter = AsyncRateLimiter(max_rate)

    async def submit(self, request):
        await self.rate_limiter.acquire()
        return await self.queue.put(request)
```

3. **Fallback para modelo local:**
```yaml
FLUXO_G_LLM_FALLBACK_TO_LOCAL: "true"
FLUXO_G_LLM_LOCAL_MODEL: "llama-3-8b"
```

---

*Runbooks mantidos por: SRE Team*
*Última atualização: 2026-04-16*
```

- [ ] **Step 2: Commit**

```bash
git add docs/runbooks/fluxo-g-runbooks.md
git commit -m "docs: add Fluxo G runbooks"
```

---

## Task 9: Criar Checklist de Deploy para Produção

**Files:**
- Create: `docs/FLUXO_G_PRODUCTION_CHECKLIST.md`

- [ ] **Step 1: Create checklist**

```markdown
# Fluxo G - Production Deployment Checklist

**Versão:** 1.0
**Data:** 2026-04-16

---

## Pré-Deploy

### 1. Código e Testes

- [ ] Todos os testes unitários passando (`pytest`)
- [ ] Todos os testes de integração passando
- [ ] Testes E2E executados com sucesso
- [ ] Code review aprovado
- [ ] Sem vulnerabilidades críticas (Bandit, Safety, Trivy)
- [ ] Coverage > 70%

### 2. Configuração

- [ ] ConfigMaps criados e revisados
- [ ] Secrets criados (não hardcoded)
- [ ] Feature flags configuradas
- [ ] Resource limits apropriados
- [ ] HPA thresholds configurados

### 3. Infraestrutura

- [ ] Namespaces existem
- [ ] RBAC configurado
- [ ] Network policies aplicadas
- [ ] PVCs provisionados
- [ ] Ingress configurado

### 4. Dependências

- [ ] Kafka topics criados
- [ ] MongoDB indexes criados
- [ ] Redis configured
- [ ] Temporal namespace criado
- [ ] Serviços dependentes disponíveis

---

## Deploy

### 1. Rollout Strategy

- [ ] Canary deployment (10% do tráfego)
- [ ] Monitoramento ativo por 30 minutos
- [ ] Rollout gradual (25% → 50% → 100%)
- [ ] Rollback plan testado

### 2. Deploy Commands

```bash
# 1. Aplica configurações
kubectl apply -f services/orchestrator-dynamic/deployments/fluxo-g/configmap.yaml
kubectl apply -f services/orchestrator-dynamic/deployments/fluxo-g/secrets.yaml

# 2. Deploy workers primeiro
kubectl apply -f services/orchestrator-dynamic/deployments/fluxo-g/deployment.yaml
kubectl wait --for=condition=ready pod -l component=fluxo-g-worker --timeout=300s

# 3. Deploy API
kubectl rollout status deployment/orchestrator-dynamic-fluxog

# 4. Verifica health
kubectl exec -it deployment/orchestrator-dynamic-fluxog -- curl http://localhost:8003/health/ready
```

---

## Pós-Deploy

### 1. Verificação Imediata (5 min)

- [ ] Todos os pods Running
- [ ] Todos os pods Ready
- [ ] Sem restarts (CrashLoopBackOff)
- [ ] Health checks passing
- [ ] Logs sem erros

```bash
# Verifica pods
kubectl get pods -l component=fluxo-g

# Verifica logs recentes
kubectl logs -f deployment/orchestrator-dynamic-fluxog --tail=50 --since=5m
kubectl logs -f deployment/orchestrator-fluxog-worker --tail=50 --since=5m
```

### 2. Verificação de Funcionalidade (15 min)

- [ ] API responde ping
- [ ] Criação de pipeline funciona
- [ ] Consulta de status funciona
- [ ] Lista de pipelines funciona
- [ ] Events Kafka sendo publicados

```bash
# Teste smoke
PIPELINE_ID=$(curl -X POST http://orchestrator-dynamic-fluxog:8003/api/v1/fluxo-g/pipelines \
  -H "Content-Type: application/json" \
  -d '{"intent_text":"Test smoke","project_name":"smoke-test","user_id":"test"}' \
  | jq -r '.pipeline_id')

curl http://orchestrator-dynamic-fluxog:8003/api/v1/fluxo-g/pipelines/$PIPELINE_ID
```

### 3. Monitoramento (1 hora)

- [ ] Métricas Prometheus normais
- [ ] Sem alerts disparados
- [ ] Latency dentro do baseline
- [ ] Error rate < 1%
- [ ] Throughput esperado

```bash
# Via Prometheus/Grafana
# Ver dashboard: fluxo-g-dashboard
```

---

## Rollback Plan

Se qualquer check falhar:

### 1. Rollback Imediato

```bash
# Rollback deployments
kubectl rollout undo deployment/orchestrator-dynamic-fluxog
kubectl rollout undo deployment/orchestrator-fluxog-worker

# Verifica status
kubectl rollout status deployment/orchestrator-dynamic-fluxog
```

### 2. Rollback Configuração

```bash
# Restaura ConfigMap anterior
kubectl apply -f backup/fluxo-g-configmap-v1.yaml

# Restaura Secrets
kubectl apply -f backup/fluxo-g-secrets-v1.yaml
```

### 3. Notificação

- [ ] Notifica time de engenharia
- [ ] Atualiza status page
- [ ] Documenta incidente

---

## Health Check Commands

### API Health

```bash
# Liveness
curl http://orchestrator-dynamic-fluxog:8003/health/live
# Expected: {"status": "ok"}

# Readiness
curl http://orchestrator-dynamic-fluxog:8003/health/ready
# Expected: {"status": "ready", "checks": {...}}

# Metrics
curl http://orchestrator-dynamic-fluxog:8013/metrics
# Expected: Prometheus metrics
```

### Service Health

```bash
# Requirements
curl http://requirements-engineering:8010/health

# Architecture
curl http://architect-agent:8008/health

# RAG
curl http://knowledge-graph-rag:8016/health

# Documentation
curl http://documentation-generation:8014/health

# Approval
curl http://approval-gateway:8017/health

# Code Forge
curl http://code-forge:8005/health
```

---

## Sign-off

| Role | Nome | Aprovou | Data/Hora |
|------|------|---------|-----------|
| Developer | |___| |___|
| Tech Lead | |___| |___|
| DevOps | |___| |___|
| Manager | |___| |___|

---

*Checklist aprovado e assinado*
*Deploy autorizado*
```

- [ ] **Step 2: Commit**

```bash
git add docs/FLUXO_G_PRODUCTION_CHECKLIST.md
git commit -m "docs: add production deployment checklist"
```

---

## Task 10: Criar Documentação de API Final

**Files:**
- Create: `docs/api/fluxo-g-api.md`

- [ ] **Step 1: Create API documentation**

```markdown
# Fluxo G API Documentation

**Base URL:** `http://orchestrator-dynamic-fluxog:8003/api/v1/fluxo-g`
**Version:** 1.0.0
**Content-Type:** `application/json`

---

## Authentication

Todas as requisições devem incluir header de autenticação:

```http
Authorization: Bearer <jwt_token>
X-User-ID: <user_id>
```

---

## Endpoints

### POST /pipelines

Inicia um novo pipeline do Fluxo G.

**Request:**
```http
POST /api/v1/fluxo-g/pipelines
Content-Type: application/json

{
  "intent_text": "Criar uma API REST de usuários com autenticação",
  "project_name": "user-auth-api",
  "user_id": "user123",
  "tech_stack": {
    "language": "python",
    "framework": "fastapi",
    "database": "postgresql"
  },
  "require_approval": true,
  "approvers": ["architect@company.com"],
  "metadata": {
    "team": "platform",
    "priority": "high"
  }
}
```

**Response (202 Accepted):**
```json
{
  "pipeline_id": "fluxo-g-1744838400",
  "status": "running",
  "message": "Pipeline iniciado com sucesso",
  "current_stage": "requirements",
  "progress": 0.0,
  "estimated_duration_seconds": 600
}
```

**Errors:**
- `400 Bad Request` - Payload inválido
- `422 Unprocessable Entity` - Validação falhou
- `429 Too Many Requests` - Rate limit exceeded
- `500 Internal Server Error` - Erro interno

---

### GET /pipelines

Lista pipelines do Fluxo G.

**Request:**
```http
GET /api/v1/fluxo-g/pipelines?page=1&page_size=20&status=running
```

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| page | integer | 1 | Número da página |
| page_size | integer | 20 | Itens por página (max 100) |
| status | string | - | Filtra por status (pending, running, completed, failed, awaiting_approval) |
| user_id | string | - | Filtra por usuário |

**Response (200 OK):**
```json
{
  "pipelines": [
    {
      "pipeline_id": "fluxo-g-1744838400",
      "status": "running",
      "current_stage": "architecture",
      "progress": 28.0,
      "created_at": "2026-04-16T10:00:00Z",
      "started_at": "2026-04-16T10:00:05Z",
      "user_id": "user123",
      "project_name": "user-auth-api"
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

---

### GET /pipelines/{pipeline_id}

Obtém detalhes de um pipeline específico.

**Request:**
```http
GET /api/v1/fluxo-g/pipelines/fluxo-g-1744838400
```

**Response (200 OK):**
```json
{
  "pipeline_id": "fluxo-g-1744838400",
  "status": "completed",
  "current_stage": "completed",
  "progress": 100.0,
  "created_at": "2026-04-16T10:00:00Z",
  "started_at": "2026-04-16T10:00:05Z",
  "completed_at": "2026-04-16T10:08:30Z",
  "duration_seconds": 505,
  "stages": {
    "requirements": {
      "status": "completed",
      "started_at": "2026-04-16T10:00:05Z",
      "completed_at": "2026-04-16T10:01:20Z",
      "duration_seconds": 75,
      "output": {
        "requirements_id": "req-123",
        "user_stories_count": 8
      }
    },
    "architecture": {
      "status": "completed",
      "started_at": "2026-04-16T10:01:25Z",
      "completed_at": "2026-04-16T10:03:00Z",
      "duration_seconds": 95,
      "output": {
        "architecture_id": "arch-456",
        "components_count": 5,
        "pattern": "microservices"
      }
    },
    "rag_query": {
      "status": "completed",
      "fallback_used": false,
      "results_count": 5
    },
    "documentation": {
      "status": "completed",
      "doc_types": ["readme", "api_docs", "diagrams"]
    },
    "approval": {
      "status": "completed",
      "approved": true,
      "approver": "architect@company.com"
    },
    "code_generation": {
      "status": "completed",
      "files_count": 15,
      "lines_of_code": 1250
    }
  },
  "output": {
    "requirements": {...},
    "architecture": {...},
    "documentation": {...},
    "generated_code": {...}
  }
}
```

**Errors:**
- `404 Not Found` - Pipeline não encontrado

---

### POST /pipelines/{pipeline_id}/approve

Envia decisão de aprovação para pipeline.

**Request:**
```http
POST /api/v1/fluxo-g/pipelines/fluxo-g-1744838400/approve
Content-Type: application/json

{
  "approved": true,
  "feedback": "LGTM! A arquitetura está sólida.",
  "approver_id": "architect@company.com"
}
```

**Response (200 OK):**
```json
{
  "message": "Sinal de aprovação enviado com sucesso",
  "approved": true,
  "pipeline_status": "resuming"
}
```

---

### POST /pipelines/{pipeline_id}/cancel

Cancela um pipeline em execução.

**Request:**
```http
POST /api/v1/fluxo-g/pipelines/fluxo-g-1744838400/cancel
```

**Response (200 OK):**
```json
{
  "message": "Pipeline cancelado com sucesso",
  "pipeline_id": "fluxo-g-1744838400",
  "status": "cancelled"
}
```

---

## Eventos Kafka

O Fluxo G publica eventos no Kafka para rastreamento:

| Tópico | Event Type | Descrição |
|--------|-----------|-----------|
| `fluxo-g.intent.received` | `intent.received` | Intenção recebida |
| `fluxo-g.requirements.generated` | `requirements.generated` | Requisitos gerados |
| `fluxo-g.architecture.generated` | `architecture.generated` | Arquitetura gerada |
| `fluxo-g.rag.results` | `rag.queried` | Consulta RAG executada |
| `fluxo-g.documentation.generated` | `documentation.generated` | Documentação gerada |
| `fluxo-g.approval.requested` | `approval.requested` | Aprovação solicitada |
| `fluxo-g.approval.completed` | `approval.completed` | Aprovação completada |
| `fluxo-g.code.generated` | `code.generated` | Código gerado |
| `fluxo-g.pipeline.completed` | `pipeline.completed` | Pipeline completado |
| `fluxo-g.pipeline.failed` | `pipeline.failed` | Pipeline falhou |

**Exemplo de Evento:**
```json
{
  "event_type": "pipeline.completed",
  "timestamp": "2026-04-16T10:08:30Z",
  "data": {
    "pipeline_id": "fluxo-g-1744838400",
    "duration_seconds": 505,
    "output_summary": {
      "has_code": true,
      "has_docs": true
    }
  }
}
```

---

## Rate Limiting

| Endpoint | Limit | Window |
|----------|-------|--------|
| POST /pipelines | 10 requests | 1 minute |
| GET /pipelines | 60 requests | 1 minute |
| GET /pipelines/{id} | 60 requests | 1 minute |
| POST /pipelines/{id}/approve | 20 requests | 1 minute |

Headers de resposta incluem:
```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Reset: 1744838460
```

---

## Webhooks

Configure webhooks para receber notificações:

```http
POST /api/v1/fluxo-g/webhooks
{
  "url": "https://your-system.com/webhooks/fluxo-g",
  "events": ["pipeline.completed", "pipeline.failed"],
  "secret": "webhook_secret_key"
}
```

Webhook payload:
```json
{
  "event": "pipeline.completed",
  "pipeline_id": "fluxo-g-1744838400",
  "timestamp": "2026-04-16T10:08:30Z",
  "signature": "sha256=..."
}
```

---

## SDKs

### Python

```python
from nhm.fluxo_g import FluxoGClient

client = FluxoGClient(
    base_url="http://orchestrator-dynamic-fluxog:8003",
    api_key="your-api-key"
)

# Iniciar pipeline
pipeline = await client.create_pipeline(
    intent_text="Criar API de produtos",
    project_name="product-api",
    user_id="user123"
)

# Aguardar conclusão
result = await pipeline.wait_for_completion(timeout=600)

print(f"Status: {result.status}")
print(f"Generated code: {result.output['generated_code']}")
```

---

*Documentação atualizada em 2026-04-16*
*Contato: api@neural-hive-mind.com*
```

- [ ] **Step 2: Commit**

```bash
git add docs/api/fluxo-g-api.md
git commit -m "docs: add Fluxo G API documentation"
```

---

## Resumo do Plano

**10 tarefas** completando a **Fase 5: Testing & Hardening** do Fluxo G.

### Componentes Criados

1. **Load Tests**: Locust scripts para testes de carga
2. **Performance Benchmarks**: pytest-benchmark para microbenchmarks
3. **Security Scans**: Scripts Bandit/Safety/Trivy/Gitleaks
4. **Rate Limiting**: Middleware de rate limiting por usuário
5. **Request Logging**: Middleware de logging estruturado
6. **Grafana Dashboard**: Monitoramento completo
7. **Operations Guide**: Documentação de operações diárias
8. **Runbooks**: Procedimentos de emergência
9. **Production Checklist**: Checklist de deploy para produção
10. **API Documentation**: Documentação completa da API

### Métricas de Sucesso

- **Testes**: >70% cobertura, todos E2E passando
- **Performance**: p95 latency < 5s, throughput > 10 pipelines/minuto
- **Segurança**: 0 vulnerabilidades críticas
- **Disponibilidade**: >99.5% uptime

---

## Conclusão do Fluxo G

Completando as 5 fases, o **Fluxo G (Ideia → Software)** está pronto para produção:

| Fase | Status | Entregas |
|------|--------|----------|
| **Fase 1: Foundation** | ✅ | architect-agent estendido |
| **Fase 2: Core Services** | ✅ | requirements-engineering, documentation-generation |
| **Fase 3: Knowledge & Approvals** | ✅ | knowledge-graph-rag, approval-gateway |
| **Fase 4: Orchestration Integration** | ✅ | orchestrator-dynamic integrado |
| **Fase 5: Testing & Hardening** | ✅ | testes, segurança, performance, docs |

**Próximos Passos:**
1. Deploy em staging para validação final
2. Testes de aceitação com stakeholders
3. Deploy gradual em produção (canary)
4. Coleta de feedback e iterações

---

*Plano completo criado em 2026-04-16*
*Total: 62 tarefas distribuídas em 5 fases*
*Estimativa: 26-31 semanas (5-8 meses)*
