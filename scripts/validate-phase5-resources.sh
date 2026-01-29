#!/bin/bash
set -euo pipefail

echo "=== Validação Phase 5: Ajuste de Recursos Helm ==="

# 1. Verificar valores atualizados nos charts
echo "1. Verificando valores nos Helm charts..."

SPECIALISTS=("business" "technical" "behavior" "evolution" "architecture")

for spec in "${SPECIALISTS[@]}"; do
  echo "   Checking specialist-$spec..."
  
  # Verificar memory requests
  MEM_REQ=$(grep -A 2 "requests:" helm-charts/specialist-$spec/values.yaml | grep "memory:" | awk '{print $2}')
  if [ "$MEM_REQ" != "512Mi" ]; then
    echo "   ✗ specialist-$spec: memory requests = $MEM_REQ (esperado: 512Mi)"
    exit 1
  fi
  
  # Verificar memory limits
  MEM_LIM=$(grep -A 2 "limits:" helm-charts/specialist-$spec/values.yaml | grep "memory:" | awk '{print $2}')
  if [ "$MEM_LIM" != "1Gi" ]; then
    echo "   ✗ specialist-$spec: memory limits = $MEM_LIM (esperado: 1Gi)"
    exit 1
  fi
  
  # Verificar startup probe
  STARTUP=$(grep "failureThreshold:" helm-charts/specialist-$spec/values.yaml | head -1 | awk '{print $2}' | tr -d '#')
  if [ "$STARTUP" != "15" ]; then
    echo "   ✗ specialist-$spec: failureThreshold = $STARTUP (esperado: 15)"
    exit 1
  fi
  
  echo "   ✓ specialist-$spec: OK"
done

echo "   Checking consensus-engine..."

# Verificar consensus-engine
MEM_REQ=$(grep -A 2 "requests:" helm-charts/consensus-engine/values.yaml | grep "memory:" | awk '{print $2}')
if [ "$MEM_REQ" != "512Mi" ]; then
  echo "   ✗ consensus-engine: memory requests = $MEM_REQ (esperado: 512Mi)"
  exit 1
fi

MEM_LIM=$(grep -A 2 "limits:" helm-charts/consensus-engine/values.yaml | grep "memory:" | awk '{print $2}')
if [ "$MEM_LIM" != "1Gi" ]; then
  echo "   ✗ consensus-engine: memory limits = $MEM_LIM (esperado: 1Gi)"
  exit 1
fi

STARTUP=$(grep "failureThreshold:" helm-charts/consensus-engine/values.yaml | head -1 | awk '{print $2}' | tr -d '#')
if [ "$STARTUP" != "15" ]; then
  echo "   ✗ consensus-engine: failureThreshold = $STARTUP (esperado: 15)"
  exit 1
fi

echo "   ✓ consensus-engine: OK"

# 2. Calcular economia total
echo ""
echo "2. Calculando economia de recursos..."

SPECIALISTS_COUNT=5
CONSENSUS_COUNT=2

OLD_SPEC_REQ_MB=$((768 * SPECIALISTS_COUNT * 2))  # 2 replicas por specialist
NEW_SPEC_REQ_MB=$((512 * SPECIALISTS_COUNT * 2))
SPEC_SAVINGS_MB=$((OLD_SPEC_REQ_MB - NEW_SPEC_REQ_MB))

OLD_CONS_REQ_MB=$((1024 * CONSENSUS_COUNT))
NEW_CONS_REQ_MB=$((512 * CONSENSUS_COUNT))
CONS_SAVINGS_MB=$((OLD_CONS_REQ_MB - NEW_CONS_REQ_MB))

TOTAL_SAVINGS_MB=$((SPEC_SAVINGS_MB + CONS_SAVINGS_MB))
TOTAL_SAVINGS_GB=$((TOTAL_SAVINGS_MB / 1024))

echo "   Specialists: ${SPEC_SAVINGS_MB}Mi economizados"
echo "   Consensus-engine: ${CONS_SAVINGS_MB}Mi economizados"
echo "   Total: ${TOTAL_SAVINGS_GB}Gi economizados"

# 3. Verificar se documentação foi atualizada
echo ""
echo "3. Verificando documentação..."

if ! grep -q "Phase 5: Ajuste de Recursos Helm" DEPENDENCY_CLEANUP_SUMMARY.md; then
  echo "   ✗ DEPENDENCY_CLEANUP_SUMMARY.md não atualizado"
  exit 1
fi

echo "   ✓ Documentação atualizada"

echo ""
echo "=== Validação Concluída com Sucesso ==="
echo ""
echo "Próximos passos:"
echo "1. Fazer commit das mudanças"
echo "2. Aplicar charts no cluster de dev/staging"
echo "3. Monitorar startup times e uso de memória"
echo "4. Se tudo OK, aplicar em produção"
