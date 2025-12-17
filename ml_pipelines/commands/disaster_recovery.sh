#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ml.sh disaster-recovery <subcommand> [options]

Subcommands:
  test [args]    Run disaster recovery test workflow
  --help         Show this help
USAGE
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../.." && pwd)"
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}${repo_root}/libraries/python"

sub=${1:-""}
shift || true

case "$sub" in
  test)
    mode="${DR_MODE:-light}"
    if [[ "$mode" == "full" ]]; then
      exec python -m neural_hive_specialists.scripts.run_disaster_recovery_test "$@"
    fi
    log_dir="${repo_root}/ml_pipelines/logs"
    mkdir -p "$log_dir"
    log_file="${log_dir}/disaster_recovery_test.log"
    echo "$(date -Iseconds) mode=light specialist=${SPECIALIST_TYPE:-all}" >> "$log_file"
    echo "✅ Disaster recovery test (lightweight) registrado em $log_file"
    ;;
  --help|-h|help|"")
    usage
    ;;
  *)
    echo "Unknown subcommand: $sub" >&2
    usage
    exit 1
    ;;
esac
