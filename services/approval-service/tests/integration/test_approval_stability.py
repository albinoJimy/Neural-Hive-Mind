"""
TR-4 — Approval Service Istio Sidecar Stability

Contract test: verifica que ambos os charts Helm de approval-service
(o canónico `helm-charts/approval-service/` consumido pelo Flux e o
chart `services/approval-service/helm/approval-service/` usado em
ambientes locais) incluem as mitigações da spec
`2026-05-22-pipeline-flow-recovery` (sidecar Istio estável +
readinessProbe relaxado).

Este teste NÃO requer cluster K8s real. Apenas renderiza os templates
via `helm template` (binary disponível no PATH) e valida campos
estruturais por YAML parsing.

Background:
- Em 2026-05-22, approval-service-5b48bc7b56-pdhck restartou 66x em 28h.
- Causa: sidecar Istio perdia readinessProbe a cada ~3-10 min com
  `context deadline exceeded` durante XDS reconnects (a cada ~30 min).
- Fix aplicado: ver spec sub-specs/technical-spec.md::TR-4.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]

# Lista de charts que devem implementar TR-4. Cada entrada é
# (chart_id, caminho_absoluto). chart_id é usado para parametrização
# e mensagens de erro.
CHARTS = [
    (
        "service-local",
        REPO_ROOT / "services" / "approval-service" / "helm" / "approval-service",
    ),
    (
        "flux-canonical",
        REPO_ROOT / "helm-charts" / "approval-service",
    ),
]


def _render_chart(chart_path: Path) -> list[dict]:
    """Renderiza o chart e retorna todos os documentos YAML."""
    helm = shutil.which("helm")
    if not helm:
        pytest.skip("helm binary not available in PATH")

    if not chart_path.exists():
        pytest.fail(f"Chart não encontrado em {chart_path}")

    result = subprocess.run(
        [helm, "template", "approval-service", str(chart_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"helm template falhou para {chart_path}: {result.stderr}")

    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


@pytest.fixture(scope="module", params=CHARTS, ids=[c[0] for c in CHARTS])
def deployment_manifest(request: pytest.FixtureRequest) -> dict:
    """Retorna o manifesto Deployment do approval-service para cada chart."""
    chart_id, chart_path = request.param
    docs = _render_chart(chart_path)
    deployments = [d for d in docs if d.get("kind") == "Deployment"]
    assert len(deployments) >= 1, f"Chart {chart_id} não produz Deployment"
    manifest = deployments[0]
    manifest["_chart_id"] = chart_id  # passa o identificador para os asserts
    return manifest


def test_chart_renders_without_error(deployment_manifest: dict) -> None:
    """Sanity: chart é YAML válido e contém Deployment."""
    assert deployment_manifest["metadata"]["name"]
    assert deployment_manifest["spec"]["template"]["spec"]["containers"]


def test_tr4_istio_proxy_config_present(deployment_manifest: dict) -> None:
    """TR-4: pod template tem `proxy.istio.io/config` com holdApplicationUntilProxyStarts."""
    chart_id = deployment_manifest["_chart_id"]
    annotations = deployment_manifest["spec"]["template"]["metadata"].get("annotations", {})

    assert "proxy.istio.io/config" in annotations, (
        f"[{chart_id}] Annotation proxy.istio.io/config ausente — "
        "sidecar Istio não configurado segundo TR-4."
    )
    proxy_cfg = yaml.safe_load(annotations["proxy.istio.io/config"])
    assert proxy_cfg.get("holdApplicationUntilProxyStarts") is True, (
        f"[{chart_id}] holdApplicationUntilProxyStarts deve ser True "
        "para evitar race condition app↔sidecar no startup."
    )
    assert proxy_cfg.get("terminationDrainDuration") == "30s", (
        f"[{chart_id}] terminationDrainDuration deve ser '30s' (era "
        f"{proxy_cfg.get('terminationDrainDuration')!r}) para garantir "
        "drenagem ordenada das ligações Kafka/MongoDB em shutdown."
    )


def test_tr4_sidecar_cpu_request_present(deployment_manifest: dict) -> None:
    """TR-4: sidecar tem CPU request explícito para evitar throttling."""
    chart_id = deployment_manifest["_chart_id"]
    annotations = deployment_manifest["spec"]["template"]["metadata"].get("annotations", {})
    assert "sidecar.istio.io/proxyCPU" in annotations, (
        f"[{chart_id}] sidecar.istio.io/proxyCPU ausente — pod sujeito "
        "a CPU throttling em nós Contabo com vCPU partilhado."
    )
    assert "sidecar.istio.io/proxyMemory" in annotations, (
        f"[{chart_id}] sidecar.istio.io/proxyMemory ausente — sidecar "
        "sem garantia de memória mínima."
    )


def test_tr4_readiness_probe_relaxed(deployment_manifest: dict) -> None:
    """TR-4: readinessProbe tem timing relaxado para tolerar XDS reconnects."""
    chart_id = deployment_manifest["_chart_id"]
    container = deployment_manifest["spec"]["template"]["spec"]["containers"][0]
    probe = container["readinessProbe"]

    assert probe["periodSeconds"] >= 30, (
        f"[{chart_id}] readinessProbe.periodSeconds={probe['periodSeconds']} "
        "é demasiado agressivo. Esperado ≥30s para tolerar XDS reconnect "
        "(~30 min)."
    )
    assert probe["timeoutSeconds"] >= 10, (
        f"[{chart_id}] readinessProbe.timeoutSeconds={probe['timeoutSeconds']} "
        "é demasiado curto. Esperado ≥10s para tolerar latência "
        "kubelet→sidecar→app."
    )
    assert probe["failureThreshold"] >= 5, (
        f"[{chart_id}] readinessProbe.failureThreshold={probe['failureThreshold']} "
        "aceita demasiado poucas falhas. Esperado ≥5 para evitar flap."
    )


def test_tr4_termination_grace_envelopes_drain(deployment_manifest: dict) -> None:
    """TR-4: terminationGracePeriodSeconds deve envelopar o drain do sidecar.

    Default kubelet (30s) faz race com o terminationDrainDuration:30s do
    sidecar Istio configurado em proxy.istio.io/config. Sem buffer, o
    SIGKILL acontece exactamente quando o drain ainda corre.
    """
    chart_id = deployment_manifest["_chart_id"]
    pod_spec = deployment_manifest["spec"]["template"]["spec"]
    grace = pod_spec.get("terminationGracePeriodSeconds")

    assert grace is not None, (
        f"[{chart_id}] terminationGracePeriodSeconds ausente — pod fica "
        "no default 30s do kubelet, race com o drain do sidecar."
    )
    assert grace >= 45, (
        f"[{chart_id}] terminationGracePeriodSeconds={grace} é insuficiente "
        "para envelopar terminationDrainDuration:30s + buffer. Esperado ≥45s."
    )


def test_tr4_liveness_probe_unchanged(deployment_manifest: dict) -> None:
    """TR-4 não toca em livenessProbe (apenas readiness — preserva contract)."""
    chart_id = deployment_manifest["_chart_id"]
    container = deployment_manifest["spec"]["template"]["spec"]["containers"][0]
    probe = container["livenessProbe"]

    # Os valores originais (pré-TR-4) que TR-4 NÃO deve alterar.
    assert probe["periodSeconds"] == 10, (
        f"[{chart_id}] livenessProbe.periodSeconds alterado pelo TR-4 " "(deve continuar 10s)."
    )
    assert probe["timeoutSeconds"] == 5, (
        f"[{chart_id}] livenessProbe.timeoutSeconds alterado pelo TR-4 " "(deve continuar 5s)."
    )
    assert probe["failureThreshold"] == 3, (
        f"[{chart_id}] livenessProbe.failureThreshold alterado pelo TR-4 " "(deve continuar 3)."
    )
