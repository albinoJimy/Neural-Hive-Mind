#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./scripts/setup.sh <command> [options]

Commands:
  minikube           Setup local Minikube environment
  eks [--auto]       Setup EKS environment (use --auto for automatic config)
  backend            Setup backend dependencies
  --help             Show this help
USAGE
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cmd=${1:-""}
shift || true

case "$cmd" in
  --help|-h|help|"")
    usage
    ;;
  minikube)
    exec "${script_dir}/setup/setup-minikube-local.sh" "$@"
    ;;
  eks)
    if [[ "${1:-""}" == "--auto" ]]; then
      shift
      exec "${script_dir}/setup-eks-env-auto.sh" "$@"
    else
      exec "${script_dir}/setup-eks-env.sh" "$@"
    fi
    ;;
  backend)
    exec "${script_dir}/setup/setup-backend.sh" "$@"
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    usage
    exit 1
    ;;
fi
