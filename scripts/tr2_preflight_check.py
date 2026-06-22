"""
TR-2 pre-flight: valida que os Helm charts dos 6 workers estão prontos
para reactivação (scale-up de 0 → minReplicas do HPA).

Spec: `.agent-os/specs/2026-05-22-pipeline-flow-recovery/` (TR-2).

Verifica (dry-run, sem cluster):
  1. Helm template renderiza sem erros (chart estruturalmente válido)
  2. Pod template inclui labels exigidas pelo Gatekeeper constraint
     `neural-hive-pod-labels` (`app`, `component`, `version`)
  3. Service inclui labels exigidas por `neural-hive-service-labels`
     (`app`, `component`, `part-of`, `managed-by`)
  4. Imagem GHCR está bem-formada (`ghcr.io/<org>/<repo>:<tag>`)
  5. HPA está presente quando esperado, com `minReplicas >= 1`

Output: JSON estruturado em stdout. Exit code 0 = todos OK, 1 = falhas.

Uso:
    python3 scripts/tr2_preflight_check.py [--chart-dir helm-charts] [--json]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Spec TR-2: lista dos 6 workers a reactivar. A ordem importa para o
# runbook (scale incremental com smoke 30min entre cada).
WORKERS = [
    "optimizer-agents",
    "scout-agents",
    "analyst-agents",
    "guard-agents",
    "worker-agents",
    "self-healing-engine",
]

# Labels exigidas pelos Gatekeeper constraints no ns `neural-hive`
# (ver gatekeeper/constraints/neural-hive-constraints.yaml).
REQUIRED_POD_LABELS: tuple[str, ...] = ("app", "component", "version")
REQUIRED_SERVICE_LABELS: tuple[str, ...] = ("app", "component", "part-of", "managed-by")

GHCR_IMAGE_PREFIX = "ghcr.io/"


@dataclass
class CheckResult:
    chart: str
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict[str, object] = field(default_factory=dict)

    def fail(self, msg: str) -> None:
        self.ok = False
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def render_chart(chart_path: Path) -> list[dict]:
    """Renderiza chart via `helm template` e devolve lista de docs YAML.

    Levanta RuntimeError em falha de render — apanhada pelo caller para
    fazer downgrade a check error.
    """
    helm = shutil.which("helm")
    if not helm:
        raise RuntimeError("helm binary não disponível no PATH")

    # Args são strings literais + chart_path (não-tainted), exec via list
    # (sem shell). Sem injection surface.
    result = subprocess.run(
        [helm, "template", "test", str(chart_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"helm template falhou: {result.stderr.strip()}")
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def _check_pod_labels(deployment: dict, result: CheckResult) -> None:
    labels = deployment.get("spec", {}).get("template", {}).get("metadata", {}).get("labels", {})
    missing = [k for k in REQUIRED_POD_LABELS if k not in labels]
    if missing:
        result.fail(
            f"Pod template não tem labels Gatekeeper-compliant: missing={missing}. "
            "Adiciona-as a `podLabels` no values.yaml. Sem isto, o Gatekeeper "
            "rejeita a criação do pod e o scale-up fica preso em 0/N."
        )
    else:
        result.details["pod_labels"] = {k: labels[k] for k in REQUIRED_POD_LABELS}


def _check_service_labels(service: dict, result: CheckResult) -> None:
    labels = service.get("metadata", {}).get("labels", {}) or {}
    missing = [k for k in REQUIRED_SERVICE_LABELS if k not in labels]
    if missing:
        result.warn(
            f"Service `{service.get('metadata', {}).get('name')}` não tem todas as "
            f"labels exigidas por neural-hive-service-labels: missing={missing}. "
            "Não bloqueia scale-up dos pods mas viola constraint do ns."
        )


def _check_image_reference(deployment: dict, result: CheckResult) -> None:
    containers = (
        deployment.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    )
    if not containers:
        result.fail("Deployment não tem containers definidos.")
        return

    main = containers[0]
    image = main.get("image", "")
    if not image.startswith(GHCR_IMAGE_PREFIX):
        result.warn(
            f"Imagem `{image}` não é do GHCR ({GHCR_IMAGE_PREFIX}*). Confirma "
            "que o registry é acessível a partir do cluster."
        )
    if ":" not in image.split("/")[-1]:
        result.fail(
            f"Imagem `{image}` sem tag explícita — risco de pull não-determinístico. "
            "Especifica `image.tag` no values.yaml."
        )
    else:
        result.details["image"] = image


def _check_version_label_matches_image(deployment: dict, result: CheckResult) -> None:
    """Detecta drift entre `podLabels.version` e `image.tag`.

    `podLabels.version` é mantido manualmente no values.yaml; ferramentas
    de automação (Flux, Renovate) actualizam `image.tag` mas não a
    label. Se a label ficar stale, dashboards de observabilidade que
    filtram por `version=` mostram dados de versão errada.
    """
    pod_labels = (
        deployment.get("spec", {}).get("template", {}).get("metadata", {}).get("labels", {})
    )
    containers = (
        deployment.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    )
    if not containers:
        return

    label_version = pod_labels.get("version")
    image = containers[0].get("image", "")
    # Extrair tag da forma `repo:tag` (último `:` após o último `/`).
    image_tag = image.rsplit(":", 1)[-1] if ":" in image.rsplit("/", 1)[-1] else None

    if label_version and image_tag and label_version != image_tag:
        result.warn(
            f"podLabels.version='{label_version}' diverge de image.tag='{image_tag}'. "
            "Actualizá-los em sincronia ou derivar a label do tag no template."
        )


def _check_hpa(docs: list[dict], chart: str, result: CheckResult) -> None:
    hpas = [d for d in docs if d.get("kind") == "HorizontalPodAutoscaler"]
    if not hpas:
        # Sem HPA, o scale-up manual via `kubectl scale --replicas=N`
        # ainda é viável, mas perde-se auto-scaling em runtime e o
        # critério de aceitação `kubectl get hpa` mostra um deployment
        # sem entrada — falha implicita no spec gate.
        result.warn(
            f"Chart `{chart}` não define HPA. Scale-up manual via "
            "`kubectl scale --replicas=N` é viável; sem HPA não há "
            "auto-scaling em runtime."
        )
        return

    hpa = hpas[0]
    min_replicas = hpa.get("spec", {}).get("minReplicas", 0)
    if min_replicas < 1:
        result.fail(
            f"HPA tem minReplicas={min_replicas}. Para reactivação, "
            "minReplicas >= 1 é obrigatório."
        )
    result.details["hpa_min_replicas"] = min_replicas
    result.details["hpa_max_replicas"] = hpa.get("spec", {}).get("maxReplicas")


def check_chart(chart_path: Path) -> CheckResult:
    result = CheckResult(chart=chart_path.name)

    try:
        docs = render_chart(chart_path)
    except RuntimeError as exc:
        result.fail(str(exc))
        return result

    deployments = [d for d in docs if d.get("kind") == "Deployment"]
    services = [d for d in docs if d.get("kind") == "Service"]

    if not deployments:
        result.fail("Chart não produz Deployment.")
        return result

    # Iterar TODOS os Deployments — alguns charts podem ter side-cars,
    # canary, ou init deployments além do principal. Aceitar só `[0]`
    # mascarava falhas em qualquer um adicional.
    for dep in deployments:
        _check_pod_labels(dep, result)
        _check_image_reference(dep, result)
    _check_version_label_matches_image(deployments[0], result)
    for svc in services:
        _check_service_labels(svc, result)
    _check_hpa(docs, chart_path.name, result)

    return result


def run(chart_dir: Path, workers: list[str]) -> tuple[list[CheckResult], int]:
    results: list[CheckResult] = []
    for worker in workers:
        chart_path = chart_dir / worker
        if not chart_path.exists():
            r = CheckResult(chart=worker)
            r.fail(f"Chart não encontrado em {chart_path}")
            results.append(r)
            continue
        results.append(check_chart(chart_path))

    exit_code = 0 if all(r.ok for r in results) else 1
    return results, exit_code


def _format_human(results: list[CheckResult]) -> str:
    lines = []
    for r in results:
        status = "OK" if r.ok and not r.warnings else ("WARN" if r.ok else "FAIL")
        lines.append(f"[{status}] {r.chart}")
        for err in r.errors:
            lines.append(f"  ERROR: {err}")
        for warn in r.warnings:
            lines.append(f"  WARN:  {warn}")
        if r.details:
            for k, v in r.details.items():
                lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--chart-dir",
        type=Path,
        default=Path("helm-charts"),
        help="Directório que contém os charts (default: helm-charts)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON em vez de human-readable",
    )
    parser.add_argument(
        "--workers",
        nargs="*",
        default=WORKERS,
        help="Subset de workers a verificar (default: todos os 6)",
    )
    args = parser.parse_args(argv)

    results, exit_code = run(args.chart_dir.resolve(), args.workers)

    if args.json:
        payload = {
            "ok": exit_code == 0,
            "results": [
                {
                    "chart": r.chart,
                    "ok": r.ok,
                    "errors": r.errors,
                    "warnings": r.warnings,
                    "details": r.details,
                }
                for r in results
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(_format_human(results))

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
