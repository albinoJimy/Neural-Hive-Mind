#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ml.sh feedback submit [options]

Options:
  --specialist TYPE   Specialist type (technical|business|behavior|evolution|architecture)
  --rating N          Numeric rating (0-5)
  --message TEXT      Feedback text
  --source NAME       Source identifier (default: cli)
  --help              Show this help
USAGE
}

sub=${1:-""}
shift || true

if [[ "$sub" =~ ^(--help|-h|help)$ || -z "$sub" ]]; then
  usage
  exit 0
fi

if [[ "$sub" != "submit" ]]; then
  echo "Unknown subcommand: $sub" >&2
  usage
  exit 1
fi

specialist="${SPECIALIST_TYPE:-}"; rating=""; message=""; source="cli"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --specialist)
      specialist=${2:-}
      shift 2
      ;;
    --rating)
      rating=${2:-}
      shift 2
      ;;
    --message)
      message=${2:-}
      shift 2
      ;;
    --source)
      source=${2:-}
      shift 2
      ;;
    --help|-h)
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

log_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)/logs"
mkdir -p "$log_dir"
log_file="$log_dir/feedback_submissions.log"

cat >> "$log_file" <<EOFLOG
$(date -Iseconds) specialist=${specialist:-unset} rating=${rating:-unset} source=${source} message="${message}"
EOFLOG

echo "Feedback registrado em $log_file"
