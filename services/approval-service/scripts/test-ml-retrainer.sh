#!/bin/bash
set -e

# Script de teste local para ml-retrainer
# Simula o que o CronJob executa no cluster

echo "=== Teste Local - ML Retrainer ==="
echo ""

# Verificar dependências
echo "[1/4] Verificando dependências..."
if ! command -v python3 &> /dev/null; then
    echo "❌ python3 não encontrado"
    exit 1
fi

# Verificar variáveis de ambiente
echo "[2/4] Configurando ambiente..."
export MONGODB_URL="${MONGODB_URL:-mongodb://localhost:27017}"
export MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI:-http://localhost:5000}"
export ENVIRONMENT="test"
export LOG_LEVEL="DEBUG"

echo "  MONGODB_URL=$MONGODB_URL"
echo "  MLFLOW_TRACKING_URI=$MLFLOW_TRACKING_URI"
echo ""

# Verificar script de retreino
RETRAIN_SCRIPT="ml_pipelines/training/retrain_v8_balanced.py"
echo "[3/4] Verificando script de retreino..."
if [ ! -f "$RETRAIN_SCRIPT" ]; then
    echo "❌ Script não encontrado: $RETRAIN_SCRIPT"
    echo "   Disponível em:"
    ls -1 ml_pipelines/training/*.py 2>/dev/null || echo "   Nenhum script encontrado"
    exit 1
fi
echo "  ✅ Script encontrado: $RETRAIN_SCRIPT"
echo ""

# Executar teste (dry-run)
echo "[4/4] Executando teste dry-run..."
python3 -c "
import sys
sys.path.insert(0, '.')

# Testa import dos módulos necessários
try:
    from ml_pipelines.training.retrain_v8_balanced import main
    print('  ✅ Import successful')
    print('  Para executar o retreino completo:')
    print(f'    python3 {RETRAIN_SCRIPT} --min-samples 100')
except ImportError as e:
    print(f'  ❌ Import failed: {e}')
    sys.exit(1)
except Exception as e:
    print(f'  ⚠️  Warning: {e}')
"

echo ""
echo "✅ Teste local concluído!"
echo ""
echo "Para executar o CronJob no cluster:"
echo "  kubectl apply -f services/approval-service/kubernetes/ml-retrainer-cronjob.yaml"
