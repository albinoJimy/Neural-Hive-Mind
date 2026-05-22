"""
TR-3 pre-check: audita o namespace `orchestrator-dynamic` (legacy)
antes da consolidação para `neural-hive`.

Spec: `.agent-os/specs/2026-05-22-pipeline-flow-recovery/` (TR-3).

Background:
  - `neural-hive/orchestrator-dynamic` (Flux-managed) é o canónico (2/2 OK).
  - `orchestrator-dynamic/orchestrator-dynamic` (manual deploy) tem
    ~110 restarts/24d e partilha o mesmo consumer group Kafka → split
    rebalances, processamento não-determinístico.

Este script é **READ-ONLY**: NÃO executa scale, delete, ou helm
uninstall. Apenas reporta o estado actual e levanta blockers que
exigem decisão humana antes da execução do runbook.

Verifica (requer `kubectl` configurado contra o cluster alvo):
  1. Namespace `orchestrator-dynamic` existe
  2. Recursos no ns legacy (deployments, statefulsets, PVCs, secrets
     com state externo, finalizers pendentes)
  3. Consumer group Kafka partilhado (best-effort via `kubectl exec`)
  4. Comparação de imagens/tags entre ns legacy e neural-hive

Output JSON ou human-readable. Exit 0 = OK proceder com runbook;
exit 1 = blocker encontrado, intervenção humana necessária.

Uso:
    python3 scripts/tr3_preflight_check.py [--ns orchestrator-dynamic]
            [--json] [--canonical-ns neural-hive]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

LEGACY_NS_DEFAULT = "orchestrator-dynamic"
CANONICAL_NS_DEFAULT = "neural-hive"
# APP_NAME é intencionalmente fixo: identifica o label do Deployment
# (`app=orchestrator-dynamic`) e o prefixo dos consumer groups. O flag
# `--ns` configura apenas o scope namespace das queries, não o nome
# da aplicação. Vide auditoria CR-009.
APP_NAME = "orchestrator-dynamic"

# Consumer groups verificados durante a consolidação. Fonte:
# `services/orchestrator-dynamic/src/config/settings.py` (5 entradas)
# e os respectivos consumers em `src/consumers/`.
CONSUMER_GROUPS = (
    "orchestrator-dynamic",  # decision_consumer (plans.consensus)
    "orchestrator-dynamic-flow-c",  # FlowCConsumer
    "orchestrator-dynamic-approval-responses",  # cognitive-plans-approval-responses
    "orchestrator-execution-results",  # execution.results
    "orchestrator-sla-alerts",  # sla.events
)


@dataclass
class CheckReport:
    legacy_ns: str
    canonical_ns: str
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: dict[str, object] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.blockers

    def block(self, msg: str) -> None:
        self.blockers.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def _kubectl(args: list[str]) -> tuple[int, str, str]:
    """Invoca kubectl; devolve (rc, stdout, stderr)."""
    kubectl = shutil.which("kubectl")
    if not kubectl:
        raise RuntimeError("kubectl não disponível no PATH")
    # Args são lista (sem shell), kubectl literal: zero injection surface.
    proc = subprocess.run([kubectl, *args], capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def check_ns_exists(report: CheckReport) -> bool:
    """Confirma que o namespace legacy existe. Se não existir, nada a
    fazer — TR-3 já foi executado ou nunca houve drift.
    """
    rc, out, _ = _kubectl(["get", "ns", report.legacy_ns, "-o", "json"])
    if rc != 0:
        report.info["ns_legacy_exists"] = False
        report.warn(
            f"Namespace `{report.legacy_ns}` não existe — TR-3 já foi "
            "consolidado ou drift inexistente. Nada a fazer."
        )
        return False

    try:
        meta = json.loads(out).get("metadata", {})
        finalizers = meta.get("finalizers", [])
        if finalizers:
            report.warn(
                f"Namespace `{report.legacy_ns}` tem finalizers: {finalizers}. "
                "Fase 2 (delete ns) pode bloquear até estes serem libertados."
            )
        report.info["ns_legacy_exists"] = True
        report.info["ns_finalizers"] = finalizers
    except json.JSONDecodeError:
        report.warn("Falha a parsear metadata do namespace legacy.")

    return True


def list_legacy_workloads(report: CheckReport) -> None:
    """Lista deployments/statefulsets/daemonsets no ns legacy."""
    for kind in ("deployment", "statefulset", "daemonset"):
        rc, out, _ = _kubectl(["get", kind, "-n", report.legacy_ns, "-o", "json"])
        if rc != 0:
            continue
        try:
            items = json.loads(out).get("items", [])
        except json.JSONDecodeError:
            continue

        if items:
            workload_list = [
                {
                    "name": w.get("metadata", {}).get("name"),
                    "replicas": w.get("spec", {}).get("replicas", 0),
                    "ready": w.get("status", {}).get("readyReplicas", 0),
                    "image": (
                        w.get("spec", {})
                        .get("template", {})
                        .get("spec", {})
                        .get("containers", [{}])[0]
                        .get("image", "")
                    ),
                }
                for w in items
            ]
            report.info[f"{kind}s_legacy"] = workload_list


def check_state_resources(report: CheckReport) -> None:
    """PVCs e StatefulSets no ns legacy implicam state local que vai
    ser perdido com `kubectl delete ns`. Levantar como BLOCKER se
    houver — operador deve confirmar que o state é descartável ou
    migrar para o ns canónico antes da Fase 2.
    """
    rc, out, _ = _kubectl(["get", "pvc", "-n", report.legacy_ns, "-o", "json"])
    if rc == 0:
        try:
            pvcs = json.loads(out).get("items", [])
        except json.JSONDecodeError:
            # CRITICAL: PVC check é o único BLOCKER destrutivo (state real
            # pode ser perdido). Output malformed (kubectl version mismatch,
            # API server stress) NÃO pode silenciar este check.
            report.block(
                "kubectl get pvc devolveu output não-parseável — não é "
                "possível avaliar state em PVCs. Abortar Fase 2."
            )
            pvcs = []
        if pvcs:
            pvc_summary = [
                {
                    "name": p.get("metadata", {}).get("name"),
                    "capacity": p.get("spec", {})
                    .get("resources", {})
                    .get("requests", {})
                    .get("storage"),
                    "storage_class": p.get("spec", {}).get("storageClassName"),
                }
                for p in pvcs
            ]
            report.info["pvcs_legacy"] = pvc_summary
            report.block(
                f"{len(pvcs)} PVC(s) no ns legacy. Confirma com o owner se "
                "estão a guardar state crítico (Temporal workflows persistentes, "
                "audit logs). Se sim, migrar antes de Fase 2. Se descartáveis, "
                "documentar explicitamente."
            )

    rc, out, _ = _kubectl(["get", "secret", "-n", report.legacy_ns, "-o", "json"])
    if rc == 0:
        try:
            secrets = json.loads(out).get("items", [])
        except json.JSONDecodeError:
            secrets = []
        # Ignorar default service-account-token / helm-related.
        relevant = [
            s
            for s in secrets
            if s.get("type") not in ("kubernetes.io/service-account-token",)
            and not s.get("metadata", {}).get("name", "").startswith("sh.helm.release")
        ]
        if relevant:
            report.info["secrets_legacy"] = [
                {"name": s.get("metadata", {}).get("name"), "type": s.get("type")} for s in relevant
            ]
            report.warn(
                f"{len(relevant)} secret(s) custom no ns legacy. Confirma se "
                "credenciais não-replicadas no ns canónico (Vault tokens, "
                "API keys específicas) antes da Fase 2."
            )


def check_image_consistency(report: CheckReport) -> None:
    """Compara imagens entre ns legacy e canónico. Se forem idênticas,
    consolidação é segura. Se divergirem, levantar warning (legacy
    pode ter behavior diferente que vai desaparecer).
    """
    legacy_images = set()
    canonical_images = set()

    for ns, bucket in ((report.legacy_ns, legacy_images), (report.canonical_ns, canonical_images)):
        rc, out, _ = _kubectl(["get", "deploy", "-n", ns, "-l", f"app={APP_NAME}", "-o", "json"])
        if rc != 0:
            continue
        try:
            items = json.loads(out).get("items", [])
        except json.JSONDecodeError:
            continue
        for item in items:
            containers = (
                item.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
            )
            for c in containers:
                if c.get("image"):
                    bucket.add(c["image"])

    report.info["images_legacy"] = sorted(legacy_images)
    report.info["images_canonical"] = sorted(canonical_images)

    if legacy_images and canonical_images and legacy_images != canonical_images:
        report.warn(
            f"Imagens divergem entre ns legacy ({sorted(legacy_images)}) e "
            f"ns canónico ({sorted(canonical_images)}). Verificar se o legacy "
            "tem build especial antes de descartar."
        )


def _count_distinct_consumer_ids(describe_output: str) -> int:
    """Conta CONSUMER-IDs distintos (não-vazios) no output de
    `kafka-consumer-groups.sh --describe`.

    Formato esperado:
        GROUP TOPIC PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG CONSUMER-ID HOST CLIENT-ID

    Contar linhas confunde members com partições (uma topic com 3
    partições e 4 members devolve 3 linhas). Vide auditoria CR-002.
    """
    consumer_ids: set[str] = set()
    for line in describe_output.splitlines():
        cols = line.split()
        if len(cols) < 7 or cols[0] in ("GROUP", "Group"):
            continue
        cid = cols[6]
        # `-` indica partição sem owner activo (rebalance em curso).
        if cid and cid != "-":
            consumer_ids.add(cid)
    return len(consumer_ids)


def check_consumer_group_overlap(report: CheckReport, expected_members: int = 2) -> None:
    """Verifica TODOS os 5 consumer groups conhecidos do orchestrator.

    Auditoria CR-003: o ns legacy pode estar a consumir em qualquer dos
    5 grupos derivados. Verificar só `orchestrator-dynamic` deixa 4 vias
    de split-brain não detectadas.
    """
    per_group: dict[str, dict[str, object]] = {}

    for group in CONSUMER_GROUPS:
        rc, out, err = _kubectl(
            [
                "exec",
                "-n",
                "kafka",
                "neural-hive-kafka-0",
                "--",
                "kafka-consumer-groups.sh",
                "--bootstrap-server",
                "localhost:9092",
                "--group",
                group,
                "--describe",
            ]
        )
        if rc != 0:
            per_group[group] = {"status": "skipped", "reason": err.strip()[:120]}
            continue

        members = _count_distinct_consumer_ids(out)
        per_group[group] = {"status": "ok", "distinct_consumer_ids": members}
        if members > expected_members:
            report.warn(
                f"Consumer group `{group}` tem {members} members distintos "
                f"(esperado ≤{expected_members} no ns canónico). Provável "
                "consumo competitivo entre ns legacy e canónico."
            )

    report.info["consumer_group_check"] = per_group


def run(legacy_ns: str, canonical_ns: str) -> CheckReport:
    report = CheckReport(legacy_ns=legacy_ns, canonical_ns=canonical_ns)

    if not check_ns_exists(report):
        return report

    list_legacy_workloads(report)
    check_state_resources(report)
    check_image_consistency(report)
    check_consumer_group_overlap(report)

    return report


def _format_human(report: CheckReport) -> str:
    lines = [f"TR-3 pre-check: legacy={report.legacy_ns} canonical={report.canonical_ns}", ""]
    if report.blockers:
        lines.append("BLOCKERS (decisão humana necessária):")
        for b in report.blockers:
            lines.append(f"  - {b}")
        lines.append("")
    if report.warnings:
        lines.append("WARNINGS:")
        for w in report.warnings:
            lines.append(f"  - {w}")
        lines.append("")
    if report.info:
        lines.append("INFO:")
        for k, v in report.info.items():
            lines.append(f"  {k}: {v}")
    lines.append("")
    lines.append("OK to proceed with runbook" if report.ok else "BLOCKED — resolve blockers first")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ns", default=LEGACY_NS_DEFAULT, help="Namespace legacy")
    parser.add_argument(
        "--canonical-ns",
        default=CANONICAL_NS_DEFAULT,
        help="Namespace canónico (Flux-managed)",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args(argv)

    try:
        report = run(args.ns, args.canonical_ns)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(
            json.dumps(
                {
                    "ok": report.ok,
                    "legacy_ns": report.legacy_ns,
                    "canonical_ns": report.canonical_ns,
                    "blockers": report.blockers,
                    "warnings": report.warnings,
                    "info": report.info,
                },
                indent=2,
                default=str,
            )
        )
    else:
        print(_format_human(report))

    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
