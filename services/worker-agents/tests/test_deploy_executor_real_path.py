"""Testes do caminho real (imperativo) do DeployExecutor (Task 8).

Contrato (spec caminho-real-first-class):
- Deploy via caminho imperativo devolve EVIDÊNCIA DE RECONCILIAÇÃO num namespace
  efémero (dev): `output.resource`/`output.status="reconciled"`/`output.healthy`,
  `metadata.simulated=False`. Satisfaz `ExecutionEngine._evidence_deploy` (Task 1).
- SEM provider real (argocd/flux client ausentes E kubernetes_asyncio indisponível)
  → FAILED (`success=False`, `simulated=False`, `real_path_unavailable=True`),
  incrementa `real_path_unavailable_total`. NUNCA `success=True`+`simulated=True`.
- Timeout sem reconciliar → `success=False` (não verde).
- Namespace efémero criado com labels Gatekeeper-compliant + labels TTL + ResourceQuota.
- `_execute_simulation` REMOVIDO (nunca devolve simulação silenciosa verde).
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

# Import do gate de evidência da Task 1 para validação ponta-a-ponta do contrato.
from engine.execution_engine import ExecutionEngine
from executors.deploy_executor import DeployExecutor

# --------------------------------------------------------------------------- #
# Helpers / mocks de kubernetes_asyncio                                        #
# --------------------------------------------------------------------------- #


class _CounterSpy:
    """Counter Prometheus-like minimalista para asserts."""

    def __init__(self):
        self.incremented = 0
        self._last_labels = None

    def labels(self, *args, **kwargs):
        self._last_labels = (args, kwargs)
        return self

    def inc(self, amount: int = 1):
        self.incremented += amount


class _FakeStatus:
    def __init__(self, available, ready):
        self.available_replicas = available
        self.ready_replicas = ready


class _FakeDeployment:
    def __init__(self, available, ready):
        self.status = _FakeStatus(available, ready)


class _FakeCoreV1Api:
    """Simula CoreV1Api: regista namespaces e resource quotas criados."""

    def __init__(self):
        self.created_namespaces = []
        self.created_quotas = []
        self.deleted_namespaces = []

    async def create_namespace(self, body):
        self.created_namespaces.append(body)
        return body

    async def read_namespace(self, name):
        return SimpleNamespace(metadata=SimpleNamespace(name=name))

    async def create_namespaced_resource_quota(self, namespace, body):
        self.created_quotas.append((namespace, body))
        return body

    async def delete_namespace(self, name):
        self.deleted_namespaces.append(name)
        return SimpleNamespace()


class _FakeAppsV1Api:
    """Simula AppsV1Api: regista deployments e devolve status reconciliado."""

    def __init__(self, available, ready, replicas):
        self.created_deployments = []
        self._available = available
        self._ready = ready
        self._replicas = replicas

    async def create_namespaced_deployment(self, namespace, body):
        self.created_deployments.append((namespace, body))
        return body

    async def read_namespaced_deployment_status(self, name, namespace):  # noqa: ARG002
        return _FakeDeployment(self._available, self._ready)


def _install_fake_k8s(executor, core_api, apps_api):
    """Substitui o inicializador lazy de clientes k8s por mocks."""

    async def _fake_init():
        executor._core_api = core_api
        executor._apps_api = apps_api
        executor._k8s_client = SimpleNamespace(close=_noop_close)

    async def _noop_close():
        return None

    executor._init_k8s_clients = _fake_init


def _ticket(ticket_id="d-real-1", **params):
    base = {
        "deployment_name": "svc-deploy",
        "image": "ghcr.io/x/svc:1.0.0",
        "replicas": 2,
        "provider": "imperative",
        "timeout_seconds": 5,
        "poll_interval": 0,
    }
    base.update(params)
    return {
        "ticket_id": ticket_id,
        "task_id": "task",
        "task_type": "DEPLOY",
        "parameters": base,
    }


# --------------------------------------------------------------------------- #
# 1. Caminho real: reconciliação + evidência                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio()
async def test_imperative_real_path_returns_reconciliation_evidence():
    """Deployment reconciliado (available_replicas == replicas) → evidência real."""
    executor = DeployExecutor(SimpleNamespace())
    core = _FakeCoreV1Api()
    apps = _FakeAppsV1Api(available=2, ready=2, replicas=2)
    _install_fake_k8s(executor, core, apps)

    result = await executor.execute(_ticket())

    assert result["success"] is True
    assert result["metadata"]["simulated"] is False
    out = result["output"]
    assert out.get("resource")  # "{ns}/{name}"
    assert out.get("healthy") is True
    assert out.get("status") == "reconciled"
    assert out.get("available_replicas") == 2


@pytest.mark.asyncio()
async def test_imperative_output_satisfies_evidence_gate():
    """O output real satisfaz o gate de evidência da Task 1."""
    executor = DeployExecutor(SimpleNamespace())
    _install_fake_k8s(executor, _FakeCoreV1Api(), _FakeAppsV1Api(available=2, ready=2, replicas=2))

    result = await executor.execute(_ticket())

    ok, reason = ExecutionEngine._evidence_deploy(result["output"])
    assert ok is True, f"gate rejeitou output real: {reason}"
    assert reason is None


class _ApiConflict(Exception):
    """Simula kubernetes_asyncio ApiException com status 409 (AlreadyExists)."""

    status = 409


@pytest.mark.asyncio()
async def test_imperative_idempotent_on_409_already_exists():
    """Re-execução do mesmo ticket (namespace já existe) → 409 tolerado, não FAILED."""

    class _ConflictCoreV1Api(_FakeCoreV1Api):
        async def create_namespace(self, body):
            raise _ApiConflict()  # já existe (retry Temporal)

        async def create_namespaced_resource_quota(self, namespace, body):
            raise _ApiConflict()

    executor = DeployExecutor(SimpleNamespace())
    apps = _FakeAppsV1Api(available=2, ready=2, replicas=2)
    _install_fake_k8s(executor, _ConflictCoreV1Api(), apps)

    result = await executor.execute(_ticket())

    # 409 não deve falhar o deploy — o recurso já existe e a reconciliação prossegue.
    assert result["success"] is True
    assert result["metadata"]["simulated"] is False
    assert result["output"].get("healthy") is True


@pytest.mark.asyncio()
async def test_imperative_creates_ephemeral_namespace_with_ttl_and_quota():
    """Namespace efémero com labels Gatekeeper + TTL e ResourceQuota."""
    executor = DeployExecutor(SimpleNamespace())
    core = _FakeCoreV1Api()
    apps = _FakeAppsV1Api(available=1, ready=1, replicas=1)
    _install_fake_k8s(executor, core, apps)

    await executor.execute(_ticket("d-ns-1", replicas=1, ttl_seconds=1800))

    assert len(core.created_namespaces) == 1
    ns_body = core.created_namespaces[0]
    labels = ns_body["metadata"]["labels"]
    # Gatekeeper-compliant
    assert "app" in labels
    assert "app.kubernetes.io/name" in labels
    # TTL para reaper externo
    assert labels.get("neural-hive.io/ephemeral") == "true"
    assert labels.get("neural-hive.io/ttl-seconds") == "1800"
    assert "neural-hive.io/created-at" in labels

    # ResourceQuota criada no namespace
    assert len(core.created_quotas) == 1
    quota_ns, quota_body = core.created_quotas[0]
    hard = quota_body["spec"]["hard"]
    assert "limits.cpu" in hard
    assert "limits.memory" in hard


@pytest.mark.asyncio()
async def test_imperative_deployment_is_gatekeeper_compliant():
    """Deployment com labels app/app.kubernetes.io/name no pod template + resources."""
    executor = DeployExecutor(SimpleNamespace())
    core = _FakeCoreV1Api()
    apps = _FakeAppsV1Api(available=2, ready=2, replicas=2)
    _install_fake_k8s(executor, core, apps)

    await executor.execute(_ticket("d-gk-1"))

    assert len(apps.created_deployments) == 1
    _, dep_body = apps.created_deployments[0]
    pod_labels = dep_body["spec"]["template"]["metadata"]["labels"]
    assert "app" in pod_labels
    assert "app.kubernetes.io/name" in pod_labels
    container = dep_body["spec"]["template"]["spec"]["containers"][0]
    assert "requests" in container["resources"]
    assert "limits" in container["resources"]


# --------------------------------------------------------------------------- #
# 2. Fail-fast sem provider real                                               #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio()
async def test_no_provider_fails_fast_no_simulation():
    """Sem argocd/flux client e kubernetes_asyncio indisponível → FAILED."""
    metrics = SimpleNamespace(real_path_unavailable_total=_CounterSpy())
    executor = DeployExecutor(SimpleNamespace(), metrics=metrics)
    # argocd_client e flux_client são None por omissão.

    # Simula ImportError no init real de k8s.
    async def _failing_init():
        raise ImportError("kubernetes_asyncio not installed")

    executor._init_k8s_clients = _failing_init

    result = await executor.execute(_ticket("d-noprov", provider="imperative"))

    assert result["success"] is False
    assert result["metadata"].get("simulated") is not True
    assert result["metadata"].get("real_path_unavailable") is True
    assert metrics.real_path_unavailable_total.incremented >= 1


# --------------------------------------------------------------------------- #
# 3. Timeout sem reconciliar                                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio()
async def test_imperative_timeout_not_reconciled_is_failed():
    """Deployment nunca atinge available_replicas==replicas → FAILED (não verde)."""
    executor = DeployExecutor(SimpleNamespace())
    core = _FakeCoreV1Api()
    apps = _FakeAppsV1Api(available=0, ready=0, replicas=2)  # nunca reconcilia
    _install_fake_k8s(executor, core, apps)

    result = await executor.execute(
        _ticket("d-timeout", replicas=2, timeout_seconds=1, poll_interval=0)
    )

    assert result["success"] is False
    assert result["metadata"].get("simulated") is not True


# --------------------------------------------------------------------------- #
# 4. Sem simulação silenciosa em qualquer caminho                              #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio()
async def test_simulation_method_removed():
    """`_execute_simulation` foi removido/fechado — nunca verde-falso simulado."""
    assert not hasattr(DeployExecutor, "_execute_simulation")


@pytest.mark.asyncio()
async def test_never_returns_silent_simulation():
    """Nenhum caminho devolve success=True com simulated=True."""
    # Caminho real
    executor = DeployExecutor(SimpleNamespace())
    _install_fake_k8s(executor, _FakeCoreV1Api(), _FakeAppsV1Api(available=2, ready=2, replicas=2))
    r1 = await executor.execute(_ticket("d-ns-real"))
    assert not (r1["metadata"].get("simulated") and r1["success"])

    # Sem provider
    executor2 = DeployExecutor(SimpleNamespace())

    async def _failing_init():
        raise ImportError("no k8s")

    executor2._init_k8s_clients = _failing_init
    r2 = await executor2.execute(_ticket("d-ns-noprov"))
    assert not (r2["metadata"].get("simulated") and r2["success"])
