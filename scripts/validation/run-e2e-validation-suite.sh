#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
# Phase 2 E2E Validation Orchestrator (staging)
# Executa validações de infraestrutura, integração e E2E Flow C em sequência,
# gerando um JSON de resumo para consumo por relatórios.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

OUTPUT_DIR="${OUTPUT_DIR:-${PROJECT_ROOT}/reports/e2e-phase2-$(date +%Y%m%d_%H%M%S)}"
SUMMARY_JSON="${SUMMARY_JSON:-${OUTPUT_DIR}/e2e-validation-summary.json}"
LOG_DIR="${OUTPUT_DIR}/logs"

RUN_PYTEST_E2E="${RUN_PYTEST_E2E:-false}"
RUN_VAULT_SPIFFE_E2E="${RUN_VAULT_SPIFFE_E2E:-false}"

mkdir -p "$LOG_DIR"

OVERALL_EXIT=0
RESULTS=()

print_banner() {
    echo "============================================"
    echo " Phase 2 - Staging E2E Validation Orchestrator"
    echo "============================================"
    echo "Output dir: ${OUTPUT_DIR}"
    echo "Summary   : ${SUMMARY_JSON}"
    echo "Optional  : RUN_PYTEST_E2E=${RUN_PYTEST_E2E}, RUN_VAULT_SPIFFE_E2E=${RUN_VAULT_SPIFFE_E2E}"
    echo ""
}

run_step() {
    local name="$1"
    local cmd="$2"
    local log_file="${LOG_DIR}/$(echo "$name" | tr ' /' '__').log"

    echo "▶ ${name}"
    set +e
    bash -c "$cmd" >"$log_file" 2>&1
    local status=$?
    set -e

    if [ $status -eq 0 ]; then
        echo "   ✓ ok (${log_file})"
    else
        echo "   ✗ fail (${log_file})"
        OVERALL_EXIT=1
    fi

    RESULTS+=("${name}|${status}|${log_file}")
}

print_banner

run_step "validate-phase2-deployment" "bash ${PROJECT_ROOT}/scripts/validation/validate-phase2-deployment.sh"
run_step "validate-phase2-integration" "bash ${PROJECT_ROOT}/scripts/validation/validate-phase2-integration.sh"
run_step "phase2-end-to-end-test" "bash ${PROJECT_ROOT}/tests/phase2-end-to-end-test.sh"

if [ "${RUN_PYTEST_E2E}" = "true" ]; then
    run_step "pytest-e2e" "cd ${PROJECT_ROOT} && pytest -m e2e"
fi

if [ "${RUN_VAULT_SPIFFE_E2E}" = "true" ]; then
    run_step "pytest-e2e-vault-spiffe" "cd ${PROJECT_ROOT} && pytest -m e2e -k vault"
fi

RESULTS_SERIALIZED=$(printf "%s;;" "${RESULTS[@]}")
export RESULTS_SERIALIZED

python - "$SUMMARY_JSON" <<'PY'
import json, os, sys

path = sys.argv[1]
raw = os.environ.get("RESULTS_SERIALIZED", "")
results = []
for entry in raw.split(";;"):
    if not entry:
        continue
    name, status, log = entry.split("|", 2)
    results.append({"name": name, "status": int(status), "log": log})

overall = 0 if all(r["status"] == 0 for r in results) else 1
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w", encoding="utf-8") as fh:
    json.dump({"results": results, "overall_status": overall}, fh, indent=2)

print(f"Summary written to {path}")
PY

echo ""
echo "============================================"
echo " Validation summary"
echo "============================================"
for entry in "${RESULTS[@]}"; do
    IFS='|' read -r name status log_file <<<"$entry"
    if [ "$status" -eq 0 ]; then
        echo "✓ ${name}"
    else
        echo "✗ ${name} (log: ${log_file})"
    fi
done
echo "JSON: ${SUMMARY_JSON}"

exit $OVERALL_EXIT
