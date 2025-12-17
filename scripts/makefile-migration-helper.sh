#!/usr/bin/env bash
set -euo pipefail

OLD_COMMAND="${1:-}"

if [[ -z "$OLD_COMMAND" ]]; then
  echo "Uso: ./scripts/makefile-migration-helper.sh <comando-antigo>"
  echo "Exemplos: test-specialists-unit | test-phase1-pre-validate"
  exit 1
fi

case "$OLD_COMMAND" in
  test-specialists-unit)
    echo "⚠️  DEPRECATED: Use 'make test-unit' instead"
    echo "Executando: make test-unit"
    exec make test-unit
    ;;
  test-phase1-pre-validate)
    echo "⚠️  DEPRECATED: Use 'make test-phase1' instead"
    echo "Executando: make test-phase1"
    exec make test-phase1
    ;;
  *)
    echo "❌ Comando não encontrado: $OLD_COMMAND"
    echo "Execute 'make help' para ver comandos disponíveis"
    exit 1
    ;;
 esac
