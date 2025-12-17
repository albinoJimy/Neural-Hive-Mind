#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./scripts/compile_protos.sh (--service NAME | --all)

Options:
  --service NAME   Compile protos for a specific service (specialists|queen-agent|analyst-agents|optimizer-agents)
  --all            Compile protos for all services
USAGE
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
service=""
all=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service)
      service=${2:-}
      shift 2
      ;;
    --all)
      all=true
      shift
      ;;
    --help|-h|help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ "$all" == true ]]; then
  exec "${script_dir}/compile_all_protos.sh"
fi

if [[ -z "$service" ]]; then
  echo "--service NAME ou --all obrigatório" >&2
  usage
  exit 1
fi

case "$service" in
  specialists)
    exec "${script_dir}/generate_protos.sh"
    ;;
  queen-agent|analyst-agents|optimizer-agents)
    target_dir="services/${service}"
    if [[ ! -d "$target_dir" ]]; then
      echo "Diretório de serviço não encontrado: $target_dir" >&2
      exit 1
    fi
    exec make -C "$target_dir" proto
    ;;
  *)
    echo "Serviço desconhecido: $service" >&2
    exit 1
    ;;
fi
