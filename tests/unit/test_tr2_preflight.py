"""
Testes unitários para `scripts/tr2_preflight_check.py`.

Foco: lógica de verificação por chart (pod labels Gatekeeper, image
reference, HPA presence), com manifests sintéticos injectados via
monkeypatch de `render_chart` — não invocam o binário `helm`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Carregar o script como módulo (não é um package — está em scripts/).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "tr2_preflight_check.py"
spec = importlib.util.spec_from_file_location("tr2_preflight_check", SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Não consigo carregar {SCRIPT_PATH}")
tr2 = importlib.util.module_from_spec(spec)
sys.modules["tr2_preflight_check"] = tr2
spec.loader.exec_module(tr2)


def _deployment(
    pod_labels: dict | None = None,
    image: str = "ghcr.io/test/svc:1.0.0",
    containers: list | None = None,
) -> dict:
    """Constrói um Deployment YAML dict sintético."""
    if containers is None:
        containers = [{"name": "svc", "image": image}]
    return {
        "kind": "Deployment",
        "metadata": {"name": "test"},
        "spec": {
            "template": {
                "metadata": {"labels": pod_labels or {}},
                "spec": {"containers": containers},
            },
        },
    }


def _hpa(min_replicas: int = 2, max_replicas: int = 10) -> dict:
    return {
        "kind": "HorizontalPodAutoscaler",
        "spec": {"minReplicas": min_replicas, "maxReplicas": max_replicas},
    }


def _service(labels: dict | None = None) -> dict:
    return {
        "kind": "Service",
        "metadata": {"name": "svc", "labels": labels or {}},
    }


def _gatekeeper_compliant_labels() -> dict:
    return {"app": "svc", "component": "svc", "version": "1.0.0"}


def _full_service_labels() -> dict:
    return {
        "app": "svc",
        "component": "svc",
        "part-of": "neural-hive-mind",
        "managed-by": "Helm",
    }


def test_check_chart_ok_when_all_labels_present(monkeypatch, tmp_path):
    docs = [_deployment(_gatekeeper_compliant_labels()), _service(_full_service_labels()), _hpa()]
    monkeypatch.setattr(tr2, "render_chart", lambda _p: docs)

    result = tr2.check_chart(tmp_path / "svc")

    assert result.ok is True
    assert result.errors == []
    assert result.warnings == []


def test_check_chart_fails_missing_pod_labels(monkeypatch, tmp_path):
    docs = [_deployment({"app.kubernetes.io/name": "svc"}), _hpa()]
    monkeypatch.setattr(tr2, "render_chart", lambda _p: docs)

    result = tr2.check_chart(tmp_path / "svc")

    assert result.ok is False
    assert any("Gatekeeper-compliant" in err for err in result.errors)
    assert any("missing=" in err for err in result.errors)


def test_check_chart_fails_no_deployment(monkeypatch, tmp_path):
    """Chart sem Deployment é unactionable."""
    monkeypatch.setattr(tr2, "render_chart", lambda _p: [_service(_full_service_labels())])

    result = tr2.check_chart(tmp_path / "svc")

    assert result.ok is False
    assert "Deployment" in result.errors[0]


def test_check_chart_fails_image_without_tag(monkeypatch, tmp_path):
    docs = [_deployment(_gatekeeper_compliant_labels(), image="ghcr.io/test/svc"), _hpa()]
    monkeypatch.setattr(tr2, "render_chart", lambda _p: docs)

    result = tr2.check_chart(tmp_path / "svc")

    assert result.ok is False
    assert any("sem tag explícita" in err for err in result.errors)


def test_check_chart_warns_non_ghcr_image(monkeypatch, tmp_path):
    docs = [
        _deployment(_gatekeeper_compliant_labels(), image="docker.io/test/svc:1.0"),
        _hpa(),
    ]
    monkeypatch.setattr(tr2, "render_chart", lambda _p: docs)

    result = tr2.check_chart(tmp_path / "svc")

    assert result.ok is True
    assert any("não é do GHCR" in w for w in result.warnings)


def test_check_chart_warns_when_hpa_absent(monkeypatch, tmp_path):
    docs = [_deployment(_gatekeeper_compliant_labels()), _service(_full_service_labels())]
    monkeypatch.setattr(tr2, "render_chart", lambda _p: docs)

    result = tr2.check_chart(tmp_path / "svc")

    assert result.ok is True
    assert any("não define HPA" in w for w in result.warnings)


def test_check_chart_fails_hpa_min_replicas_zero(monkeypatch, tmp_path):
    docs = [_deployment(_gatekeeper_compliant_labels()), _hpa(min_replicas=0)]
    monkeypatch.setattr(tr2, "render_chart", lambda _p: docs)

    result = tr2.check_chart(tmp_path / "svc")

    assert result.ok is False
    assert any("minReplicas=0" in err for err in result.errors)


def test_check_chart_warns_service_missing_labels(monkeypatch, tmp_path):
    docs = [
        _deployment(_gatekeeper_compliant_labels()),
        _service({"app": "svc"}),  # falta component/part-of/managed-by
        _hpa(),
    ]
    monkeypatch.setattr(tr2, "render_chart", lambda _p: docs)

    result = tr2.check_chart(tmp_path / "svc")

    assert result.ok is True  # service labels são warning, não error
    assert any("neural-hive-service-labels" in w for w in result.warnings)


def test_check_chart_fails_when_render_raises(monkeypatch, tmp_path):
    def _explode(_p):
        raise RuntimeError("helm template failed: invalid template")

    monkeypatch.setattr(tr2, "render_chart", _explode)

    result = tr2.check_chart(tmp_path / "svc")

    assert result.ok is False
    assert "helm template failed" in result.errors[0]


def test_check_chart_warns_on_version_label_drift(monkeypatch, tmp_path):
    """CR-002: detectar drift entre podLabels.version e image.tag."""
    labels = {"app": "svc", "component": "svc", "version": "1.0.0"}
    docs = [
        _deployment(labels, image="ghcr.io/test/svc:2.0.0"),  # tag != label
        _hpa(),
    ]
    monkeypatch.setattr(tr2, "render_chart", lambda _p: docs)

    result = tr2.check_chart(tmp_path / "svc")

    assert result.ok is True  # drift é warning, não error
    assert any("diverge de image.tag" in w for w in result.warnings)


def test_check_chart_no_warning_when_version_matches_image(monkeypatch, tmp_path):
    """CR-002 (negative): sem drift, nenhum warning de version."""
    labels = {"app": "svc", "component": "svc", "version": "1.0.0"}
    docs = [_deployment(labels, image="ghcr.io/test/svc:1.0.0"), _hpa()]
    monkeypatch.setattr(tr2, "render_chart", lambda _p: docs)

    result = tr2.check_chart(tmp_path / "svc")

    assert not any("diverge de image.tag" in w for w in result.warnings)


def test_check_chart_iterates_multiple_deployments(monkeypatch, tmp_path):
    """CR-004: chart com 2 Deployments, segundo sem labels → falha registada."""
    docs = [
        _deployment({"app": "svc", "component": "svc", "version": "1.0.0"}),
        _deployment({"app.kubernetes.io/name": "svc"}),  # sem bare labels → fail
        _hpa(),
    ]
    monkeypatch.setattr(tr2, "render_chart", lambda _p: docs)

    result = tr2.check_chart(tmp_path / "svc")

    assert result.ok is False
    assert any("Gatekeeper-compliant" in err for err in result.errors)


def test_run_returns_exit_1_on_any_failure(monkeypatch, tmp_path):
    """Se um único chart falha, o exit code agregado é 1."""
    monkeypatch.setattr(
        tr2,
        "render_chart",
        lambda p: (
            [_deployment(_gatekeeper_compliant_labels()), _hpa()]
            if "ok-chart" in str(p)
            else [_deployment({})]  # sem labels → fail
        ),
    )
    (tmp_path / "ok-chart").mkdir()
    (tmp_path / "broken-chart").mkdir()

    results, exit_code = tr2.run(tmp_path, ["ok-chart", "broken-chart"])

    assert exit_code == 1
    assert results[0].ok is True
    assert results[1].ok is False


def test_run_returns_exit_0_when_all_ok(monkeypatch, tmp_path):
    docs = [_deployment(_gatekeeper_compliant_labels()), _service(_full_service_labels()), _hpa()]
    monkeypatch.setattr(tr2, "render_chart", lambda _p: docs)

    chart_dir = tmp_path
    for name in ("a", "b", "c"):
        (chart_dir / name).mkdir()

    results, exit_code = tr2.run(chart_dir, ["a", "b", "c"])

    assert exit_code == 0
    assert all(r.ok for r in results)
    assert all(r.warnings == [] for r in results)


def test_run_handles_missing_chart_dir(tmp_path):
    """Worker listado mas chart não existe → falha registada."""
    results, exit_code = tr2.run(tmp_path, ["nonexistent"])

    assert exit_code == 1
    assert results[0].ok is False
    assert "não encontrado" in results[0].errors[0]


def test_json_output_when_flag_present(monkeypatch, tmp_path, capsys):
    docs = [_deployment(_gatekeeper_compliant_labels()), _hpa()]
    monkeypatch.setattr(tr2, "render_chart", lambda _p: docs)
    (tmp_path / "svc").mkdir()

    import json

    exit_code = tr2.main(["--chart-dir", str(tmp_path), "--json", "--workers", "svc"])
    captured = capsys.readouterr().out

    assert exit_code == 0
    payload = json.loads(captured)
    assert payload["ok"] is True
    assert payload["results"][0]["chart"] == "svc"
    assert payload["results"][0]["ok"] is True
