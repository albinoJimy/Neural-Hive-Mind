#!/usr/bin/env bash
#
# cleanup_old_pheromones.sh - Clean up old/legacy Redis pheromone keys
#
# This script removes deprecated pheromone key patterns from Redis that are
# no longer used after the migration to DomainMapper-based keys.
#
# WARNING: This is a ONE-TIME cleanup script intended for NON-PRODUCTION environments.
# In production, use with extreme caution and ensure proper backups exist.
#
# Usage: ./scripts/cleanup_old_pheromones.sh [options]
#
# Options:
#   --dry-run       Show keys that would be deleted without deleting them (default)
#   --execute       Actually delete the keys
#   --redis-host    Redis host (default: localhost)
#   --redis-port    Redis port (default: 6379)
#   --redis-db      Redis database (default: 0)
#   --help          Show this help
#

set -euo pipefail

# Default values
DRY_RUN=true
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_DB="${REDIS_DB:-0}"

# Legacy key patterns to clean up
# These patterns were used before the DomainMapper migration
LEGACY_PATTERNS=(
  'pheromone:*'                           # Old flat pheromone keys
  'pheromones:signal:*'                   # Old signal format
  'consensus:pheromone:*'                 # Old consensus namespace
  'specialist:pheromone:*'                # Old specialist-prefixed keys
  'swarm:pheromone:*'                     # Old swarm namespace
)

# Current patterns (DO NOT DELETE - for reference only)
# These are the valid patterns used by DomainMapper:
# - pheromones:consensus:{domain}:{pheromone_type}:{id}
# - pheromones:active:{specialist_type}:{domain}

usage() {
  cat <<'USAGE'
Usage: ./scripts/cleanup_old_pheromones.sh [options]

Clean up deprecated Redis pheromone keys from legacy key formats.

Options:
  --dry-run       Show keys that would be deleted without deleting them (default)
  --execute       Actually delete the keys (USE WITH CAUTION)
  --redis-host    Redis host (default: localhost or REDIS_HOST env var)
  --redis-port    Redis port (default: 6379 or REDIS_PORT env var)
  --redis-db      Redis database (default: 0 or REDIS_DB env var)
  --help          Show this help

Environment Variables:
  REDIS_HOST      Redis host
  REDIS_PORT      Redis port
  REDIS_DB        Redis database number
  REDIS_PASSWORD  Redis password (if authentication is required)

Legacy Patterns Targeted:
  - pheromone:*           Old flat pheromone keys
  - pheromones:signal:*   Old signal format
  - consensus:pheromone:* Old consensus namespace
  - specialist:pheromone:*Old specialist-prefixed keys
  - swarm:pheromone:*     Old swarm namespace

WARNING: This script is intended for ONE-TIME execution in NON-PRODUCTION
environments. Always perform a dry-run first and ensure backups exist.

Examples:
  # Dry run (default) - see what would be deleted
  ./scripts/cleanup_old_pheromones.sh

  # Execute cleanup on local Redis
  ./scripts/cleanup_old_pheromones.sh --execute

  # Execute cleanup on specific Redis instance
  ./scripts/cleanup_old_pheromones.sh --execute --redis-host redis.staging.local

USAGE
}

log_info() {
  echo "[INFO] $(date '+%Y-%m-%d %H:%M:%S') $*"
}

log_warn() {
  echo "[WARN] $(date '+%Y-%m-%d %H:%M:%S') $*" >&2
}

log_error() {
  echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') $*" >&2
}

# Build redis-cli command with authentication if needed
build_redis_cmd() {
  local cmd="redis-cli -h ${REDIS_HOST} -p ${REDIS_PORT} -n ${REDIS_DB}"
  if [[ -n "${REDIS_PASSWORD:-}" ]]; then
    cmd="$cmd -a ${REDIS_PASSWORD}"
  fi
  echo "$cmd"
}

# Count keys matching a pattern
count_keys() {
  local pattern="$1"
  local redis_cmd
  redis_cmd=$(build_redis_cmd)
  $redis_cmd --no-auth-warning KEYS "$pattern" 2>/dev/null | wc -l
}

# List keys matching a pattern
list_keys() {
  local pattern="$1"
  local redis_cmd
  redis_cmd=$(build_redis_cmd)
  $redis_cmd --no-auth-warning KEYS "$pattern" 2>/dev/null
}

# Delete keys matching a pattern using SCAN for safety
delete_keys_by_pattern() {
  local pattern="$1"
  local redis_cmd
  redis_cmd=$(build_redis_cmd)
  local deleted=0

  # Use SCAN to avoid blocking Redis with large KEYS command
  local cursor=0
  while true; do
    local result
    result=$($redis_cmd --no-auth-warning SCAN "$cursor" MATCH "$pattern" COUNT 100 2>/dev/null)
    cursor=$(echo "$result" | head -n1)
    local keys
    keys=$(echo "$result" | tail -n +2)

    if [[ -n "$keys" ]]; then
      while IFS= read -r key; do
        if [[ -n "$key" ]]; then
          $redis_cmd --no-auth-warning DEL "$key" >/dev/null 2>&1
          ((deleted++)) || true
        fi
      done <<< "$keys"
    fi

    if [[ "$cursor" == "0" ]]; then
      break
    fi
  done

  echo "$deleted"
}

# Parse command line arguments
parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run)
        DRY_RUN=true
        shift
        ;;
      --execute)
        DRY_RUN=false
        shift
        ;;
      --redis-host)
        REDIS_HOST="$2"
        shift 2
        ;;
      --redis-port)
        REDIS_PORT="$2"
        shift 2
        ;;
      --redis-db)
        REDIS_DB="$2"
        shift 2
        ;;
      --help|-h)
        usage
        exit 0
        ;;
      *)
        log_error "Unknown option: $1"
        usage
        exit 1
        ;;
    esac
  done
}

# Check Redis connectivity
check_redis_connection() {
  local redis_cmd
  redis_cmd=$(build_redis_cmd)
  if ! $redis_cmd --no-auth-warning PING >/dev/null 2>&1; then
    log_error "Cannot connect to Redis at ${REDIS_HOST}:${REDIS_PORT}"
    exit 1
  fi
  log_info "Connected to Redis at ${REDIS_HOST}:${REDIS_PORT} (db: ${REDIS_DB})"
}

# Main cleanup function
main() {
  parse_args "$@"

  log_info "Starting pheromone cleanup script"
  log_info "Mode: $(if $DRY_RUN; then echo 'DRY-RUN (no changes will be made)'; else echo 'EXECUTE (keys will be deleted)'; fi)"

  check_redis_connection

  local total_found=0
  local total_deleted=0

  echo ""
  log_info "Scanning for legacy pheromone key patterns..."
  echo ""

  for pattern in "${LEGACY_PATTERNS[@]}"; do
    local count
    count=$(count_keys "$pattern")
    total_found=$((total_found + count))

    if [[ "$count" -gt 0 ]]; then
      log_info "Pattern '$pattern': $count keys found"

      if $DRY_RUN; then
        # Show first 10 keys as sample
        log_info "  Sample keys (first 10):"
        list_keys "$pattern" | head -n 10 | while read -r key; do
          echo "    - $key"
        done
        if [[ "$count" -gt 10 ]]; then
          echo "    ... and $((count - 10)) more"
        fi
      else
        local deleted
        deleted=$(delete_keys_by_pattern "$pattern")
        total_deleted=$((total_deleted + deleted))
        log_info "  Deleted $deleted keys"
      fi
    else
      log_info "Pattern '$pattern': no keys found"
    fi
  done

  echo ""
  log_info "=========================================="
  log_info "Summary:"
  log_info "  Total legacy keys found: $total_found"
  if $DRY_RUN; then
    log_info "  Mode: DRY-RUN (no keys deleted)"
    if [[ "$total_found" -gt 0 ]]; then
      echo ""
      log_warn "To delete these keys, run with --execute flag:"
      log_warn "  ./scripts/cleanup_old_pheromones.sh --execute"
    fi
  else
    log_info "  Total keys deleted: $total_deleted"
  fi
  log_info "=========================================="
}

main "$@"
