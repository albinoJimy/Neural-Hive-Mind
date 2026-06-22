"""
Testes unitários para `scripts/tr3_preflight_check.py`.

Foco: lógica de classificação (blocker vs warning vs info) dada output
sintético de `kubectl`. Não invoca kubectl real — monkeypatch de
`_kubectl()` injecta respostas.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "tr3_preflight_check.py"
spec = importlib.util.spec_from_file_location("tr3_preflight_check", SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Não consigo carregar {SCRIPT_PATH}")
tr3 = importlib.util.module_from_spec(spec)
sys.modules["tr3_preflight_check"] = tr3
spec.loader.exec_module(tr3)


def _make_kubectl_stub(responses: dict[tuple[str, ...], tuple[int, str, str]]):
    """Devolve um callable que substitui `_kubectl`. `responses` mapeia
    prefixos de args (tuple) para (rc, stdout, stderr)."""

    def _stub(args):
        for key, value in responses.items():
            if tuple(args[: len(key)]) == key:
                return value
        return (1, "", f"unknown args: {args}")

    return _stub


def test_ns_does_not_exist_returns_ok_with_warning(monkeypatch):
    """ns inexistente → TR-3 já feito ou drift inexistente → OK + warning."""
    responses = {("get", "ns", "orchestrator-dynamic"): (1, "", "NotFound")}
    monkeypatch.setattr(tr3, "_kubectl", _make_kubectl_stub(responses))

    report = tr3.run("orchestrator-dynamic", "neural-hive")

    assert report.ok is True
    assert report.info["ns_legacy_exists"] is False
    assert any("já foi consolidado" in w for w in report.warnings)


def test_ns_exists_no_state_no_workloads_returns_ok(monkeypatch):
    """ns vazio (sem PVCs/secrets/deploys) → seguro proceder."""
    responses = {
        ("get", "ns", "orchestrator-dynamic"): (0, json.dumps({"metadata": {}}), ""),
        ("get", "deployment", "-n", "orchestrator-dynamic"): (
            0,
            json.dumps({"items": []}),
            "",
        ),
        ("get", "statefulset", "-n", "orchestrator-dynamic"): (
            0,
            json.dumps({"items": []}),
            "",
        ),
        ("get", "daemonset", "-n", "orchestrator-dynamic"): (
            0,
            json.dumps({"items": []}),
            "",
        ),
        ("get", "pvc", "-n", "orchestrator-dynamic"): (0, json.dumps({"items": []}), ""),
        ("get", "secret", "-n", "orchestrator-dynamic"): (0, json.dumps({"items": []}), ""),
        ("get", "deploy", "-n", "orchestrator-dynamic"): (0, json.dumps({"items": []}), ""),
        ("get", "deploy", "-n", "neural-hive"): (0, json.dumps({"items": []}), ""),
        ("exec", "-n", "kafka"): (1, "", "no kafka pod"),
    }
    monkeypatch.setattr(tr3, "_kubectl", _make_kubectl_stub(responses))

    report = tr3.run("orchestrator-dynamic", "neural-hive")

    assert report.ok is True
    assert report.blockers == []


def test_pvc_present_blocks_proceed(monkeypatch):
    """PVC no ns legacy → BLOCKER (state pode ser crítico)."""
    pvc_doc = {
        "items": [
            {
                "metadata": {"name": "workflow-state"},
                "spec": {
                    "resources": {"requests": {"storage": "10Gi"}},
                    "storageClassName": "longhorn",
                },
            }
        ]
    }
    responses = {
        ("get", "ns", "orchestrator-dynamic"): (0, json.dumps({"metadata": {}}), ""),
        ("get", "deployment", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "statefulset", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "daemonset", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "pvc", "-n", "orchestrator-dynamic"): (0, json.dumps(pvc_doc), ""),
        ("get", "secret", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "deploy", "-n"): (0, json.dumps({"items": []}), ""),
        ("exec",): (1, "", "skip"),
    }
    monkeypatch.setattr(tr3, "_kubectl", _make_kubectl_stub(responses))

    report = tr3.run("orchestrator-dynamic", "neural-hive")

    assert report.ok is False
    assert any("PVC" in b for b in report.blockers)
    assert "pvcs_legacy" in report.info


def test_finalizers_in_ns_metadata_warn(monkeypatch):
    """Finalizers no ns → warning sobre risco de delete bloquear."""
    ns_with_finalizers = {"metadata": {"finalizers": ["custom.io/cleanup"]}}
    responses = {
        ("get", "ns", "orchestrator-dynamic"): (0, json.dumps(ns_with_finalizers), ""),
        ("get", "deployment", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "statefulset", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "daemonset", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "pvc", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "secret", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "deploy", "-n"): (0, json.dumps({"items": []}), ""),
        ("exec",): (1, "", "skip"),
    }
    monkeypatch.setattr(tr3, "_kubectl", _make_kubectl_stub(responses))

    report = tr3.run("orchestrator-dynamic", "neural-hive")

    assert any("finalizers" in w for w in report.warnings)
    assert report.info["ns_finalizers"] == ["custom.io/cleanup"]


def test_image_divergence_warns(monkeypatch):
    """Imagens diferentes legacy vs canónico → warning."""
    legacy = {
        "items": [
            {
                "spec": {
                    "template": {
                        "spec": {"containers": [{"image": "ghcr.io/test/orch:legacy-build"}]}
                    }
                }
            }
        ]
    }
    canonical = {
        "items": [
            {"spec": {"template": {"spec": {"containers": [{"image": "ghcr.io/test/orch:1.0.0"}]}}}}
        ]
    }
    responses = {
        ("get", "ns", "orchestrator-dynamic"): (0, json.dumps({"metadata": {}}), ""),
        ("get", "deployment", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "statefulset", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "daemonset", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "pvc", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "secret", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "deploy", "-n", "orchestrator-dynamic"): (0, json.dumps(legacy), ""),
        ("get", "deploy", "-n", "neural-hive"): (0, json.dumps(canonical), ""),
        ("exec",): (1, "", "skip"),
    }
    monkeypatch.setattr(tr3, "_kubectl", _make_kubectl_stub(responses))

    report = tr3.run("orchestrator-dynamic", "neural-hive")

    assert any("Imagens divergem" in w for w in report.warnings)


def test_custom_secrets_warn_but_dont_block(monkeypatch):
    """Secrets custom → warning, não blocker."""
    secrets_doc = {
        "items": [
            {"metadata": {"name": "vault-token"}, "type": "Opaque"},
            {
                "metadata": {"name": "default-token-abc"},
                "type": "kubernetes.io/service-account-token",
            },
        ]
    }
    responses = {
        ("get", "ns", "orchestrator-dynamic"): (0, json.dumps({"metadata": {}}), ""),
        ("get", "deployment", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "statefulset", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "daemonset", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "pvc", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "secret", "-n"): (0, json.dumps(secrets_doc), ""),
        ("get", "deploy", "-n"): (0, json.dumps({"items": []}), ""),
        ("exec",): (1, "", "skip"),
    }
    monkeypatch.setattr(tr3, "_kubectl", _make_kubectl_stub(responses))

    report = tr3.run("orchestrator-dynamic", "neural-hive")

    assert report.ok is True  # warning, não blocker
    assert any("secret(s) custom" in w for w in report.warnings)
    # Default tokens ignorados na contagem
    assert "vault-token" in str(report.info.get("secrets_legacy", []))
    assert "default-token-abc" not in str(report.info.get("secrets_legacy", []))


def test_json_output_serializes(monkeypatch, capsys):
    responses = {("get", "ns", "orchestrator-dynamic"): (1, "", "NotFound")}
    monkeypatch.setattr(tr3, "_kubectl", _make_kubectl_stub(responses))

    exit_code = tr3.main(["--json"])
    captured = capsys.readouterr().out

    payload = json.loads(captured)
    assert payload["ok"] is True
    assert payload["legacy_ns"] == "orchestrator-dynamic"
    assert payload["canonical_ns"] == "neural-hive"
    assert exit_code == 0


def test_exit_code_1_when_blocker(monkeypatch, capsys):
    pvc_doc = {
        "items": [
            {
                "metadata": {"name": "x"},
                "spec": {
                    "resources": {"requests": {"storage": "1Gi"}},
                    "storageClassName": "default",
                },
            }
        ]
    }
    responses = {
        ("get", "ns", "orchestrator-dynamic"): (0, json.dumps({"metadata": {}}), ""),
        ("get", "deployment", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "statefulset", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "daemonset", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "pvc", "-n", "orchestrator-dynamic"): (0, json.dumps(pvc_doc), ""),
        ("get", "secret", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "deploy", "-n"): (0, json.dumps({"items": []}), ""),
        ("exec",): (1, "", "skip"),
    }
    monkeypatch.setattr(tr3, "_kubectl", _make_kubectl_stub(responses))

    exit_code = tr3.main([])
    assert exit_code == 1


def test_consumer_group_skipped_when_kafka_unreachable(monkeypatch):
    responses = {
        ("get", "ns", "orchestrator-dynamic"): (0, json.dumps({"metadata": {}}), ""),
        ("get", "deployment", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "statefulset", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "daemonset", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "pvc", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "secret", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "deploy", "-n"): (0, json.dumps({"items": []}), ""),
        ("exec", "-n", "kafka"): (1, "", "pod not found"),
    }
    monkeypatch.setattr(tr3, "_kubectl", _make_kubectl_stub(responses))

    report = tr3.run("orchestrator-dynamic", "neural-hive")

    assert report.ok is True
    # Cada um dos 5 grupos deve estar marcado como "skipped"
    cg_check = report.info.get("consumer_group_check", {})
    assert isinstance(cg_check, dict)
    assert len(cg_check) == len(tr3.CONSUMER_GROUPS)
    assert all(g["status"] == "skipped" for g in cg_check.values())


def test_consumer_group_detects_split_brain(monkeypatch):
    """CR-002 + CR-003: detectar excess de consumer-ids num qualquer grupo."""
    # Output sintético com 4 consumer-ids distintos (split entre 2 nss)
    describe_out = (
        "GROUP TOPIC PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG CONSUMER-ID HOST CLIENT-ID\n"
        "g topic 0 100 100 0 consumer-id-a host-1 c1\n"
        "g topic 1 100 100 0 consumer-id-b host-2 c2\n"
        "g topic 2 100 100 0 consumer-id-c host-3 c3\n"
        "g topic 0 100 100 0 consumer-id-d host-4 c4\n"  # 4º member, partição já vista
    )
    responses = {
        ("get", "ns", "orchestrator-dynamic"): (0, json.dumps({"metadata": {}}), ""),
        ("get", "deployment", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "statefulset", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "daemonset", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "pvc", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "secret", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "deploy", "-n"): (0, json.dumps({"items": []}), ""),
        ("exec", "-n", "kafka"): (0, describe_out, ""),
    }
    monkeypatch.setattr(tr3, "_kubectl", _make_kubectl_stub(responses))

    report = tr3.run("orchestrator-dynamic", "neural-hive")

    # Threshold default expected_members=2 → 4 members > 2 → warning per group
    assert any("consumo competitivo" in w for w in report.warnings)


def test_consumer_id_counting_ignores_header_and_idle(monkeypatch):
    """CR-002: header (GROUP) e partições sem owner (-) não contam."""
    out = (
        "GROUP TOPIC PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG CONSUMER-ID HOST CLIENT-ID\n"
        "g topic 0 100 100 0 consumer-a host-1 c1\n"
        "g topic 1 100 100 0 - - -\n"  # partição sem owner
        "g topic 2 100 100 0 consumer-a host-1 c1\n"  # mesmo consumer 2x
    )
    assert tr3._count_distinct_consumer_ids(out) == 1


def test_pvc_malformed_json_blocks(monkeypatch):
    """CR-001 CRITICAL: kubectl PVC output malformed deve BLOQUEAR."""
    responses = {
        ("get", "ns", "orchestrator-dynamic"): (0, json.dumps({"metadata": {}}), ""),
        ("get", "deployment", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "statefulset", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "daemonset", "-n"): (0, json.dumps({"items": []}), ""),
        # PVC retorna JSON malformed (kubectl truncado, version mismatch).
        ("get", "pvc", "-n", "orchestrator-dynamic"): (0, "{ not json", ""),
        ("get", "secret", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "deploy", "-n"): (0, json.dumps({"items": []}), ""),
        ("exec",): (1, "", "skip"),
    }
    monkeypatch.setattr(tr3, "_kubectl", _make_kubectl_stub(responses))

    report = tr3.run("orchestrator-dynamic", "neural-hive")

    assert report.ok is False
    assert any("não-parseável" in b for b in report.blockers)


def test_kubectl_absent_returns_exit_2(monkeypatch, capsys):
    """CR-007: kubectl não disponível → exit 2 (erro de execução)."""

    def _no_kubectl(_args):
        raise RuntimeError("kubectl não disponível no PATH")

    monkeypatch.setattr(tr3, "_kubectl", _no_kubectl)

    exit_code = tr3.main([])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "kubectl não disponível" in captured.err


def test_workload_list_populated(monkeypatch):
    deploy_doc = {
        "items": [
            {
                "metadata": {"name": "orchestrator-dynamic"},
                "spec": {
                    "replicas": 2,
                    "template": {"spec": {"containers": [{"image": "ghcr.io/test/orch:legacy"}]}},
                },
                "status": {"readyReplicas": 1},
            }
        ]
    }
    responses = {
        ("get", "ns", "orchestrator-dynamic"): (0, json.dumps({"metadata": {}}), ""),
        ("get", "deployment", "-n", "orchestrator-dynamic"): (
            0,
            json.dumps(deploy_doc),
            "",
        ),
        ("get", "statefulset", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "daemonset", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "pvc", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "secret", "-n"): (0, json.dumps({"items": []}), ""),
        ("get", "deploy", "-n"): (0, json.dumps({"items": []}), ""),
        ("exec",): (1, "", "skip"),
    }
    monkeypatch.setattr(tr3, "_kubectl", _make_kubectl_stub(responses))

    report = tr3.run("orchestrator-dynamic", "neural-hive")

    assert "deployments_legacy" in report.info
    workloads = report.info["deployments_legacy"]
    assert workloads[0]["name"] == "orchestrator-dynamic"
    assert workloads[0]["replicas"] == 2
    assert workloads[0]["ready"] == 1
    assert "legacy" in workloads[0]["image"]
