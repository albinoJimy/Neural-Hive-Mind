#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./scripts/observability.sh <command> [subcommand] [options]

Commands:
  setup                               Setup observability dashboards
  validate                            Run observability validation checks
  dashboards setup                    Provision dashboards
  dashboards access [--dashboard X]   Open dashboards (optional: specific dashboard)
  dashboards stop                     Stop local dashboard forwarding
  test slos                           Run SLO tests
  test correlation                    Run correlation tests
  --help                              Show this help
USAGE
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root_dir="$(cd "${script_dir}/.." && pwd)"

cmd=${1:-""}
sub=${2:-""}

case "$cmd" in
  --help|-h|help|"")
    usage
    ;;
  setup)
    exec "${script_dir}/observability/setup-dashboards.sh" "${@:2}"
    ;;
  validate)
    exec "${script_dir}/observability/validate-observability.sh" "${@:2}"
    ;;
  dashboards)
    case "$sub" in
      setup)
        exec "${script_dir}/observability/setup-dashboards.sh" "${@:3}"
        ;;
      access|"" )
        exec "${root_dir}/access-dashboards.sh" "${@:3}"
        ;;
      stop)
        exec "${root_dir}/stop-dashboards.sh" "${@:3}"
        ;;
      *)
        echo "Unknown dashboards subcommand: $sub" >&2
        usage
        exit 1
        ;;
    esac
    ;;
  test)
    case "$sub" in
      slos)
        exec "${script_dir}/observability/test-slos.sh" "${@:3}"
        ;;
      correlation)
        exec "${script_dir}/observability/test-correlation.sh" "${@:3}"
        ;;
      *)
        echo "Unknown test subcommand: $sub" >&2
        usage
        exit 1
        ;;
    esac
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    usage
    exit 1
    ;;
fi
