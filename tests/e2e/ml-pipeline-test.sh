#!/bin/bash
set -e

echo "🧪 Executando testes E2E de modelos preditivos..."

# Port-forward orchestrator
kubectl port-forward -n semantic-translation svc/orchestrator-dynamic 8000:8000 &
PF_PID=$!

# Aguardar port-forward
sleep 5

# Executar testes
pytest tests/e2e/test_predictive_models_e2e.py \
    -v \
    --tb=short \
    --log-cli-level=INFO \
    -m e2e

EXIT_CODE=$?

# Cleanup
kill $PF_PID 2>/dev/null || true

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Todos os testes E2E passaram"
else
    echo "❌ Alguns testes E2E falharam"
fi

exit $EXIT_CODE
