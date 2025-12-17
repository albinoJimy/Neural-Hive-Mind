#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ml.sh anomaly-detector <subcommand> [options]

Subcommands:
  train [args]   Train anomaly detector models
  --help         Show this help
USAGE
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../.." && pwd)"
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}${repo_root}/libraries/python"

sub=${1:-""}
shift || true

case "$sub" in
  train)
    mode="${ANOMALY_DETECTOR_MODE:-light}"
    if [[ "$mode" == "full" ]]; then
      exec python -m neural_hive_specialists.scripts.train_anomaly_detector "$@"
    fi
    window=30
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --window-days) window=${2:-30}; shift 2 ;;
        *) shift ;;
      esac
    done
    log_dir="${repo_root}/ml_pipelines/logs"
    mkdir -p "$log_dir"
    log_file="${log_dir}/anomaly_detector_train.log"
    echo "$(date -Iseconds) mode=light window_days=${window}" >> "$log_file"
    echo "✅ Anomaly detector (lightweight) registrado em $log_file"
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
