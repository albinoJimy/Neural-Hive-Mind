#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
set -e

echo "=========================================="
echo "  Complete Flow E2E Validation"
echo "=========================================="

echo "Checking prerequisites..."
command -v kubectl >/dev/null 2>&1 || { echo "kubectl not found"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "docker not found"; exit 1; }
command -v pytest >/dev/null 2>&1 || { echo "pytest not found"; exit 1; }

echo "Checking services..."
SERVICES=(
    "gateway-intencoes"
    "semantic-translation-engine"
    "consensus-engine"
    "orchestrator-dynamic"
    "mcp-tool-catalog"
    "code-forge"
    "worker-agents"
)

for svc in "${SERVICES[@]}"; do
    if kubectl get svc "$svc" -A &>/dev/null; then
        echo "✓ $svc available"
    else
        echo "✗ $svc not found"
        exit 1
    fi
done

echo ""
echo "Running complete flow E2E test..."
pytest tests/e2e/test_complete_flow_intent_to_artifact.py -v --tb=short --log-cli-level=INFO

echo ""
echo "✅ Complete flow E2E validation PASSED"
