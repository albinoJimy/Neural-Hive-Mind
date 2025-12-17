#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ml.sh business-metrics <subcommand> [options]

Subcommands:
  collect [--window-hours N] [--specialist-type TYPE]   Run business metrics collector
  --help                                                Show this help
USAGE
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../.." && pwd)"
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}${repo_root}/libraries/python"

sub=${1:-""}
shift || true

case "$sub" in
  collect)
    mode="${BUSINESS_METRICS_MODE:-light}"
    if [[ "$mode" == "full" ]]; then
      exec python -m neural_hive_specialists.scripts.run_business_metrics_collector "$@"
    fi
    window=24
    specialist="all"
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --window-hours) window=${2:-24}; shift 2 ;;
        --specialist-type) specialist=${2:-all}; shift 2 ;;
        *) shift ;;
      esac
    done
    log_dir="${repo_root}/ml_pipelines/logs"
    mkdir -p "$log_dir"
    log_file="${log_dir}/business_metrics_collect.log"
    echo "$(date -Iseconds) mode=light window_hours=${window} specialist=${specialist}" >> "$log_file"
    echo "✅ Business metrics (lightweight) registrada em $log_file"
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
