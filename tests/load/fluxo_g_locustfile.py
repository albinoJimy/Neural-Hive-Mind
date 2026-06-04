"""
Locust load test file for Fluxo G Engineering Services.

Tests load on:
- requirements-engineering (8010)
- documentation-generation (8014)
- knowledge-graph-rag (8016)
- approval-gateway (8017)
"""

import time
from locust import HttpUser, task, between, events


class RequirementsEngineeringUser(HttpUser):
    """Simula usuário interagindo com requirements-engineering."""

    wait_time = between(1, 3)
    host = "http://localhost:8010"

    def on_start(self):
        """Setup inicial."""
        self.requirement_id = None

    @task(3)
    def health_check(self):
        """Health check - endpoint mais leve."""
        self.client.get("/health", name="/health")

    @task(2)
    def list_requirements(self):
        """Lista requisitos existentes."""
        self.client.get(
            "/api/v1/requirements?page=1&page_size=20", name="/api/v1/requirements (GET)"
        )


class DocumentationGenerationUser(HttpUser):
    """Simula usuário interagindo com documentation-generation."""

    wait_time = between(2, 5)
    host = "http://localhost:8014"

    @task(3)
    def health_check(self):
        """Health check."""
        self.client.get("/health", name="/health")

    @task(1)
    def list_docs(self):
        """Lista documentação gerada."""
        self.client.get(
            "/api/v1/documentation?page=1&page_size=20", name="/api/v1/documentation (GET)"
        )


class KnowledgeGraphRAGUser(HttpUser):
    """Simula usuário interagindo com knowledge-graph-rag."""

    wait_time = between(1, 4)
    host = "http://localhost:8016"

    @task(3)
    def health_check(self):
        """Health check."""
        self.client.get("/health", name="/health")

    @task(2)
    def rag_query(self):
        """Executa query RAG."""
        self.client.post(
            "/api/v1/rag/query",
            json={
                "query": "Como implementar autenticação JWT em FastAPI?",
                "top_k": 5,
                "include_sources": True,
            },
            name="/api/v1/rag/query (POST)",
        )


class ApprovalGatewayUser(HttpUser):
    """Simula usuário interagindo com approval-gateway."""

    wait_time = between(1, 3)
    host = "http://localhost:8017"

    @task(3)
    def health_check(self):
        """Health check."""
        self.client.get("/health", name="/health")

    @task(1)
    def list_approvals(self):
        """Lista aprovações."""
        self.client.get("/api/v1/approvals?page=1&page_size=20", name="/api/v1/approvals (GET)")


class FluxoGMixUser(HttpUser):
    """Usuário misto que testa todos os serviços."""

    wait_time = between(1, 2)

    @task(1)
    def test_requirements_service(self):
        """Testa requirements-engineering."""
        if not hasattr(self, "client"):
            return

        # Usar HTTP client direto para diferentes hosts
        import requests

        try:
            response = requests.get("http://localhost:8010/health", timeout=2)
            if response.status_code == 200:
                self.environment.reqs_health_ok += 1
        except Exception:
            self.environment.reqs_health_failed += 1

    @task(1)
    def test_documentation_service(self):
        """Testa documentation-generation."""
        import requests

        try:
            response = requests.get("http://localhost:8014/health", timeout=2)
            if response.status_code == 200:
                self.environment.docs_health_ok += 1
        except Exception:
            self.environment.docs_health_failed += 1

    @task(1)
    def test_kg_rag_service(self):
        """Testa knowledge-graph-rag."""
        import requests

        try:
            response = requests.get("http://localhost:8016/health", timeout=2)
            if response.status_code == 200:
                self.environment.kg_health_ok += 1
        except Exception:
            self.environment.kg_health_failed += 1

    @task(1)
    def test_approval_service(self):
        """Testa approval-gateway."""
        import requests

        try:
            response = requests.get("http://localhost:8017/health", timeout=2)
            if response.status_code == 200:
                self.environment.approval_health_ok += 1
        except Exception:
            self.environment.approval_health_failed += 1


# Event handlers para métricas
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Inicializa contadores."""
    environment.reqs_health_ok = 0
    environment.reqs_health_failed = 0
    environment.docs_health_ok = 0
    environment.docs_health_failed = 0
    environment.kg_health_ok = 0
    environment.kg_health_failed = 0
    environment.approval_health_ok = 0
    environment.approval_health_failed = 0
    environment.start_time = time.time()


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Reporta métricas finais."""
    duration = time.time() - environment.start_time

    print("\n" + "=" * 70)
    print("FLUXO G LOAD TEST RESULTS")
    print("=" * 70)
    print(f"Duration: {duration:.2f} seconds")
    print()
    print("Requirements Engineering (8010):")
    print(f"  Health OK: {environment.reqs_health_ok}")
    print(f"  Health Failed: {environment.reqs_health_failed}")
    print()
    print("Documentation Generation (8014):")
    print(f"  Health OK: {environment.docs_health_ok}")
    print(f"  Health Failed: {environment.docs_health_failed}")
    print()
    print("Knowledge Graph RAG (8016):")
    print(f"  Health OK: {environment.kg_health_ok}")
    print(f"  Health Failed: {environment.kg_health_failed}")
    print()
    print("Approval Gateway (8017):")
    print(f"  Health OK: {environment.approval_health_ok}")
    print(f"  Health Failed: {environment.approval_health_failed}")
    print()

    total_ok = (
        environment.reqs_health_ok
        + environment.docs_health_ok
        + environment.kg_health_ok
        + environment.approval_health_ok
    )
    total_failed = (
        environment.reqs_health_failed
        + environment.docs_health_failed
        + environment.kg_health_failed
        + environment.approval_health_failed
    )
    total = total_ok + total_failed

    if total > 0:
        print(f"Total Health Checks: {total}")
        print(f"Success Rate: {(total_ok / total) * 100:.2f}%")
        print(f"Throughput: {total / duration:.2f} checks/second")
    print("=" * 70 + "\n")


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, **kwargs):
    """Log de requisições lentas."""
    if response_time > 5000:  # 5 segundos
        print(f"SLOW REQUEST: {name} took {response_time}ms")
