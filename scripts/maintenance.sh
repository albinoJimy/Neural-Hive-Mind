#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./scripts/maintenance.sh <command> [options]

Commands:
  backup [args]                 Run backup workflow
  restore [args]                Run restore workflow
  cluster [args]                Perform cluster maintenance tasks
  cost-optimize [args]          Execute cost optimization tasks
  disaster-recovery [args]      Disaster recovery utilities (e.g., status)
  --help                        Show this help
USAGE
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cmd=${1:-""}
shift || true

case "$cmd" in
  --help|-h|help|"")
    usage
    ;;
  backup)
    exec "${script_dir}/maintenance/backup-restore.sh" backup "$@"
    ;;
  restore)
    exec "${script_dir}/maintenance/backup-restore.sh" restore "$@"
    ;;
  cluster)
    exec "${script_dir}/maintenance/cluster-maintenance.sh" "$@"
    ;;
  cost-optimize)
    exec "${script_dir}/maintenance/cost-optimization.sh" "$@"
    ;;
  disaster-recovery)
    exec "${script_dir}/maintenance/cluster-maintenance.sh" disaster-recovery "$@"
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    usage
    exit 1
    ;;
fi
