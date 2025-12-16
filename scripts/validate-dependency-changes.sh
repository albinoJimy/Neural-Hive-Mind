#!/usr/bin/env bash
#
# Script para validar mudanças de dependências antes de commits/deploys.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Validando mudanças de dependências ==="

echo "Verificando conflitos de versão..."
python3 "${ROOT_DIR}/scripts/scan-unused-imports.py" --check-conflicts >/tmp/dependency-conflicts.log
cat /tmp/dependency-conflicts.log

echo "Verificando estrutura de requirements-dev.txt..."
for service in "${ROOT_DIR}"/services/*/; do
  dev_file="${service}requirements-dev.txt"
  if [[ -f "$dev_file" ]]; then
    if ! grep -q "^-r requirements.txt" "$dev_file"; then
      echo "ERROR: ${dev_file} não inclui '-r requirements.txt'"
      exit 1
    fi
  fi
done

echo "Verificando separação de dependências dev/prod..."
PATTERN="pytest|black|flake8|mypy|ruff"
for service in "${ROOT_DIR}"/services/*/; do
  req_file="${service}requirements.txt"
  if [[ -f "$req_file" ]] && grep -qE "$PATTERN" "$req_file"; then
    echo "WARNING: ${req_file} contém dependências de desenvolvimento"
  fi
done

echo "Verificando alinhamento de versões críticas..."
GRPC_LINES=$(grep -h "^grpcio" "${ROOT_DIR}"/services/*/requirements.txt | sort -u || true)
GRPC_COUNT=$(printf "%s\n" "$GRPC_LINES" | sed '/^\s*$/d' | wc -l)
if [[ "$GRPC_COUNT" -gt 2 ]]; then
  echo "WARNING: múltiplas versões de grpcio encontradas (esperado máximo 2)"
  printf "%s\n" "$GRPC_LINES"
fi

if [[ "${RUN_E2E_TESTS:-false}" == "true" ]]; then
  echo "Executando testes E2E..."
  # Adicione comandos específicos aqui.
  # Exemplo: pytest tests/e2e/test_grpc_communication.py
fi

echo "=== Validação concluída com sucesso ==="
