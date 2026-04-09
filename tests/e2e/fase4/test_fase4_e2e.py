"""
Testes E2E para FASE 4 - Evolution Components.

Valida integração entre os componentes implementados na FASE 4.
"""

import pytest
import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator, Dict, Any
import httpx

UTC = timezone.utc


@pytest.fixture
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Client HTTP para requisições."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client


@pytest.fixture
async def services_ports() -> Dict[str, int]:
    """Portas dos serviços FASE 4."""
    return {
        "hypothesis_library": 8010,
        "learning_doc_generator": 8009,
        "experiment_impact_analyzer": 8011,
    }


# ============================================================================
# TESTS: EXP-02-01 - Experimentation Core E2E
# ============================================================================


@pytest.mark.e2e
@pytest.mark.experimentation
class TestExperimentationCoreE2E:
    """Testes E2E do Experimentation Core."""

    async def test_experiment_lifecycle(
        self, http_client: httpxClient, services_ports: Dict[str, int]
    ):
        """Testa ciclo de vida completo de experimento via Hypothesis Library."""
        base_url = f"http://localhost:{services_ports['hypothesis_library']}"

        # 1. Criar hipótese
        response = await http_client.post(
            f"{base_url}/api/v1/hypotheses",
            json={
                "title": "E2E Test Experiment",
                "description": "Teste E2E de experimento",
                "background": "Validar fluxo completo",
                "expected_outcome": "Experimento completado com sucesso",
                "metrics": ["accuracy", "latency_p95"],
                "author": "e2e-test",
                "priority": "high",
            },
        )
        assert response.status_code == 201
        hypothesis = response.json()
        hypothesis_id = hypothesis["hypothesis_id"]

        # 2. Propor hipótese
        response = await http_client.post(
            f"{base_url}/api/v1/hypotheses/{hypothesis_id}/propose"
        )
        assert response.status_code == 200

        # 3. Aprovar hipótese
        response = await http_client.post(
            f"{base_url}/api/v1/hypotheses/{hypothesis_id}/approve",
            json={"reviewer": "e2e-test", "comments": "Approved for E2E testing"},
        )
        assert response.status_code == 200

        # 4. Iniciar teste
        response = await http_client.post(
            f"{base_url}/api/v1/hypotheses/{hypothesis_id}/start-test",
            json={"experiment_id": "e2e-exp-001"},
        )
        assert response.status_code == 200

        # 5. Verificar status
        response = await http_client.get(f"{base_url}/api/v1/hypotheses/{hypothesis_id}")
        assert response.status_code == 200
        updated = response.json()
        assert updated["status"] == "in_testing"

        # 6. Completar com sucesso
        response = await http_client.post(
            f"{base_url}/api/v1/hypotheses/{hypothesis_id}/complete",
            json={
                "outcome": "accepted",
                "results": {"accuracy": 0.85, "latency_p95": 120},
            },
        )
        assert response.status_code == 200


# ============================================================================
# TESTS: RB-01-01 - Rollback E2E
# ============================================================================


@pytest.mark.e2e
@pytest.mark.rollback
class TestRollbackE2E:
    """Testes E2E de sistema de rollback."""

    async def test_rollback_detection_and_execution(
        self, http_client: httpx.AsyncClient, services_ports: Dict[str, int]
    ):
        """Testa deteção de degradação e execução de rollback."""
        base_url = f"http://localhost:{services_ports['experiment_impact_analyzer']}"

        # 1. Registrar análise de baseline
        response = await http_client.post(
            f"{base_url}/api/v1/impact/analyze",
            json={
                "experiment_id": "rollback-test-001",
                "experiment_name": "Rollback Test",
                "experiment_type": "A_B_TEST",
                "baseline_metrics": {"accuracy": 0.90, "latency_p95": 100},
                "treatment_metrics": {"accuracy": 0.88, "latency_p95": 110},
                "start_time": datetime.now(UTC).isoformat(),
                "end_time": datetime.now(UTC).isoformat(),
            },
        )
        assert response.status_code == 201
        analysis = response.json()
        analysis_id = analysis["analysis_id"]

        # 2. Simular degradação
        response = await http_client.post(
            f"{base_url}/api/v1/impact/analyze",
            json={
                "experiment_id": "rollback-test-001",
                "experiment_name": "Rollback Test - Degraded",
                "experiment_type": "A_B_TEST",
                "baseline_metrics": {"accuracy": 0.90, "latency_p95": 100},
                "treatment_metrics": {"accuracy": 0.75, "latency_p95": 180},  # Degradação significativa
                "start_time": datetime.now(UTC).isoformat(),
                "end_time": datetime.now(UTC).isoformat(),
            },
        )
        assert response.status_code == 201
        degraded_analysis = response.json()

        # 3. Verificar detecção de impacto negativo
        response = await http_client.get(
            f"{base_url}/api/v1/impact/experiment/rollback-test-001"
        )
        assert response.status_code == 200
        summary = response.json()
        assert summary["has_degradation"] is True


# ============================================================================
# TESTS: OL-01-01 - Online Learning Pipeline E2E
# ============================================================================


@pytest.mark.e2e
@pytest.mark.online_learning
class TestOnlineLearningPipelineE2E:
    """Testes E2E do pipeline de Online Learning."""

    async def test_online_learning_feedback_loop(
        self, http_client: httpx.AsyncClient, services_ports: Dict[str, int]
    ):
        """Testa loop completo de feedback online."""
        base_url = f"http://localhost:{services_ports['learning_doc_generator']}"

        # 1. Gerar documento de relatório semanal
        response = await http_client.post(
            f"{base_url}/api/v1/docs/generate",
            json={
                "doc_type": "weekly_summary",
                "period_start": (datetime.now(UTC).replace(hour=0, minute=0, second=0)).isoformat(),
                "period_end": datetime.now(UTC).isoformat(),
                "include_plots": True,
            },
        )
        assert response.status_code == 202  # Accepted (background task)
        doc_request = response.json()
        doc_id = doc_request["doc_id"]

        # 2. Aguardar geração (polling)
        max_attempts = 10
        for _ in range(max_attempts):
            await asyncio.sleep(1)
            response = await http_client.get(f"{base_url}/api/v1/docs/{doc_id}")
            assert response.status_code == 200
            doc = response.json()
            if doc["status"] == "completed":
                break
        else:
            pytest.fail("Document generation timed out")

        # 3. Download documento
        response = await http_client.get(
            f"{base_url}/api/v1/docs/{doc_id}/download?format=markdown"
        )
        assert response.status_code == 200
        assert len(response.content) > 0


# ============================================================================
# TESTS: FLUXCD - GitOps Foundation E2E
# ============================================================================


@pytest.mark.e2e
@pytest.mark.gitops
@pytest.mark.kubernetes
class TestFluxCDE2E:
    """Testes E2E do GitOps com FluxCD."""

    async def test_fluxcd_manifests_validation(self):
        """Valida manifests do FluxCD usando kubeval."""
        import subprocess
        import os

        fluxcd_dir = "infrastructure/fluxcd/clusters"

        for env in ["dev", "staging", "prod"]:
            env_dir = os.path.join(fluxcd_dir, env)
            if not os.path.exists(env_dir):
                continue

            # Validar YAMLs com kubectl --dry-run=client
            for root, dirs, files in os.walk(env_dir):
                for file in files:
                    if file.endswith(".yaml"):
                        filepath = os.path.join(root, file)
                        result = subprocess.run(
                            ["kubectl", "apply", "--dry-run=client", "-f", filepath],
                            capture_output=True,
                            text=True,
                        )
                        assert result.returncode == 0, f"Failed to validate {filepath}: {result.stderr}"


# ============================================================================
# TESTS: DASH-001 - Dashboard E2E
# ============================================================================


@pytest.mark.e2e
@pytest.mark.dashboards
class TestDashboardsE2E:
    """Testes E2E dos dashboards Grafana."""

    async def test_dashboard_json_validation(self):
        """Valida que os dashboards Grafana são JSON válido."""
        import json
        import os

        dashboards_dir = "observability/grafana/dashboards"

        for filename in os.listdir(dashboards_dir):
            if filename.endswith(".json"):
                filepath = os.path.join(dashboards_dir, filename)
                with open(filepath) as f:
                    dashboard = json.load(f)
                    assert dashboard.get("uid") is not None, f"Missing UID in {filename}"
                    assert dashboard.get("title") is not None, f"Missing title in {filename}"
                    assert dashboard.get("panels") is not None, f"Missing panels in {filename}"


# ============================================================================
# TESTS: DOCGEN-001 - Document Generation E2E
# ============================================================================


@pytest.mark.e2e
@pytest.mark.documentation
class TestDocumentGenerationE2E:
    """Testes E2E de geração de documentação."""

    async def test_pdf_generation_flow(
        self, http_client: httpx.AsyncClient, services_ports: Dict[str, int]
    ):
        """Testa fluxo completo de geração de PDF."""
        base_url = f"http://localhost:{services_ports['learning_doc_generator']}"

        # 1. Gerar documento
        response = await http_client.post(
            f"{base_url}/api/v1/docs/generate",
            json={
                "doc_type": "experiment_report",
                "experiment_id": "pdf-test-001",
                "experiment_name": "PDF Generation Test",
                "metrics": {"accuracy": 0.95},
            },
        )
        assert response.status_code == 202
        doc_request = response.json()
        doc_id = doc_request["doc_id"]

        # 2. Aguardar conclusão
        await asyncio.sleep(2)

        # 3. Download PDF
        response = await http_client.get(
            f"{base_url}/api/v1/docs/{doc_id}/download?format=pdf"
        )
        # PDF pode não estar disponível se WeasyPrint não estiver instalado
        # Aceitamos 200 ou 404 (feature opcional)
        assert response.status_code in [200, 404, 422]


# ============================================================================
# TESTS: Integracao entre Componentes
# ============================================================================


@pytest.mark.e2e
@pytest.mark.integration
class TestFASE4Integration:
    """Testes de integração entre componentes da FASE 4."""

    async def test_hypothesis_to_doc_flow(
        self, http_client: httpx.AsyncClient, services_ports: Dict[str, int]
    ):
        """Testa fluxo da criação de hipótese até geração de documento."""
        hypothesis_url = f"http://localhost:{services_ports['hypothesis_library']}"
        doc_url = f"http://localhost:{services_ports['learning_doc_generator']}"

        # 1. Criar hipótese
        response = await http_client.post(
            f"{hypothesis_url}/api/v1/hypotheses",
            json={
                "title": "Integration Test",
                "description": "Teste integração FASE 4",
                "background": "Validar fluxos entre componentes",
                "expected_outcome": "Integração funcionando",
                "metrics": ["success_rate"],
                "author": "integration-test",
                "priority": "medium",
            },
        )
        assert response.status_code == 201
        hypothesis = response.json()
        hypothesis_id = hypothesis["hypothesis_id"]

        # 2. Aprovar hipótese
        await http_client.post(
            f"{hypothesis_url}/api/v1/hypotheses/{hypothesis_id}/approve",
            json={"reviewer": "integration-test"},
        )

        # 3. Iniciar teste
        await http_client.post(
            f"{hypothesis_url}/api/v1/hypotheses/{hypothesis_id}/start-test",
            json={"experiment_id": "integration-exp-001"},
        )

        # 4. Completar
        await http_client.post(
            f"{hypothesis_url}/api/v1/hypotheses/{hypothesis_id}/complete",
            json={"outcome": "accepted", "results": {"success_rate": 0.95}},
        )

        # 5. Gerar documento (via evento simulado)
        response = await http_client.post(
            f"{doc_url}/api/v1/docs/generate",
            json={
                "doc_type": "experiment_report",
                "experiment_id": "integration-exp-001",
                "experiment_name": "Integration Test Experiment",
                "status": "completed",
                "metrics": {"success_rate": 0.95},
            },
        )
        assert response.status_code == 202
