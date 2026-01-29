#!/bin/bash
# Script para exportar imagens via pipe direto (sem usar disco local)
# docker save → ssh → ctr import

set -e

WORKERS=("158.220.101.216" "84.247.138.35")

IMAGES=(
  "neural-hive-mind/semantic-translation-engine:1.0.8"
  "neural-hive-mind/orchestrator-dynamic:1.0.8"
  "neural-hive-mind/gateway-intencoes:1.0.8"
  "neural-hive-mind/consensus-engine:1.0.8"
  "neural-hive-mind/specialist-architecture:1.0.8"
  "neural-hive-mind/specialist-behavior:1.0.8"
  "neural-hive-mind/specialist-business:1.0.8"
  "neural-hive-mind/specialist-evolution:1.0.8"
  "neural-hive-mind/specialist-technical:1.0.8"
)

echo "=== EXPORTANDO ${#IMAGES[@]} IMAGENS PARA ${#WORKERS[@]} WORKERS ==="
echo "Workers: ${WORKERS[*]}"
echo ""

TOTAL=$((${#IMAGES[@]} * ${#WORKERS[@]}))
CURRENT=0
FAILED=0

for img in "${IMAGES[@]}"; do
  name=$(echo "$img" | cut -d'/' -f2 | cut -d':' -f1)

  for worker in "${WORKERS[@]}"; do
    CURRENT=$((CURRENT + 1))
    echo "[$CURRENT/$TOTAL] $name → $worker"

    if docker save "$img" | ssh -o StrictHostKeyChecking=no "root@${worker}" "ctr -n k8s.io images import - 2>&1" | grep -q "saved\|sha256"; then
      echo "  ✅ OK"
    else
      echo "  ❌ FALHOU"
      FAILED=$((FAILED + 1))
    fi
  done
done

echo ""
echo "=== RESUMO ==="
echo "Total: $TOTAL"
echo "Sucesso: $((TOTAL - FAILED))"
echo "Falhas: $FAILED"

# Verificar
echo ""
echo "=== VERIFICAÇÃO NOS WORKERS ==="
for worker in "${WORKERS[@]}"; do
  count=$(ssh "root@${worker}" "ctr -n k8s.io images list | grep -E 'neural-hive-mind.*(gateway|semantic|orchestrator|consensus|specialist).*1.0.8' | wc -l" 2>/dev/null)
  echo "Worker $worker: $count/9 imagens"
done
