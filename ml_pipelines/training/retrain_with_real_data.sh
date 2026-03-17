#!/bin/bash
set -e

# ============================================================================
# Retreino de Modelos ML com Dados Reais
# ============================================================================
# Contexto:
# - 2402 feedbacks já coletados (2026-02-08)
# - Distribuição real: review_required 64.7%, approve 20.1%, reject 15%
# - Modelo atual treinado em sintético (confidence ~0.5)
# Objetivo: Elevar confiança para >0.8 através de retreino com dados reais
# ============================================================================

echo "============================================="
echo "Neural Hive - ML Retraining with Real Data"
echo "============================================="
echo ""

# Configurações
SPECIALIST_TYPE=${1:-"all"}  # all, technical, business, behavior, evolution, architecture
MIN_REAL_SAMPLES=${MIN_REAL_SAMPLES:-400}  # Reduzido para ~480 disponíveis
REAL_DATA_DAYS=${REAL_DATA_DAYS:-60}
ALLOW_SYNTHETIC_FALLBACK=${ALLOW_SYNTHETIC_FALLBACK:-"false"}  # Exigir dados reais
MODEL_TYPE=${MODEL_TYPE:-"random_forest"}
HYPERPARAMETER_TUNING=${HYPERPARAMETER_TUNING:-"false"}
PROMOTE_IF_BETTER=${PROMOTE_IF_BETTER:-"true"}

# Environment
export MLFLOW_TRACKING_URI=${MLFLOW_TRACKING_URI:-"http://mlflow.mlflow:5000"}
export MONGODB_URI=${MONGODB_URI:-"mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin"}
export ENVIRONMENT=${ENVIRONMENT:-"production"}

# Exportar para subprocessos
export ALLOW_SYNTHETIC_FALLBACK
export REAL_DATA_DAYS
export MIN_REAL_SAMPLES

echo "📋 Configuração:"
echo "   Specialist: $SPECIALIST_TYPE"
echo "   Min Real Samples: $MIN_REAL_SAMPLES"
echo "   Real Data Days: $REAL_DATA_DAYS"
echo "   Allow Synthetic: $ALLOW_SYNTHETIC_FALLBACK"
echo "   Environment: $ENVIRONMENT"
echo "   MLflow URI: $MLFLOW_TRACKING_URI"
echo "   MongoDB URI: $MONGODB_URI"
echo ""

# Pre-flight checks
echo "🔍 Pre-flight checks..."

# Check MLflow
echo "   Checking MLflow..."
if kubectl exec -n mlflow deployment/mlflow -- curl -sf http://localhost:5000/health > /dev/null 2>&1; then
    echo "   ✅ MLflow OK"
else
    echo "   ❌ MLflow not accessible"
    exit 1
fi

# Check MongoDB
echo "   Checking MongoDB..."
if kubectl exec -n approval deployment/approval-service -- python3 -c "
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
async def check():
    client = AsyncIOMotorClient('$MONGODB_URI')
    await db.command('ping')
asyncio.run(check())
" 2>/dev/null; then
    echo "   ✅ MongoDB OK"
else
    echo "   ⚠️  MongoDB warning (continuing anyway)"
fi

# Check feedback data
echo "   Checking feedback data..."
FEEDBACK_COUNT=$(kubectl exec -n approval deployment/approval-service -- python3 -c "
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
async def check():
    client = AsyncIOMotorClient('$MONGODB_URI')
    db = client['neural_hive']
    count = await db['specialist_feedback'].count_documents({})
    print(count)
asyncio.run(check())
" 2>/dev/null || echo "0")

echo "   📊 Feedback documents: $FEEDBACK_COUNT"

if [ "$FEEDBACK_COUNT" -lt "$MIN_REAL_SAMPLES" ]; then
    echo "   ⚠️  WARNING: Feedback count ($FEEDBACK_COUNT) < MIN_REAL_SAMPLES ($MIN_REAL_SAMPLES)"
    echo "   ⚠️  Training may fail or use synthetic fallback"
    read -p "   Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""
echo "============================================="
echo "🚀 Starting retraining with REAL DATA"
echo "============================================="
echo ""

# Lista de especialistas
if [ "$SPECIALIST_TYPE" = "all" ]; then
    SPECIALISTS=("technical" "business" "behavior" "evolution" "architecture")
else
    SPECIALISTS=("$SPECIALIST_TYPE")
fi

# Verificar se estamos no cluster ou local
if [ -f "/home/jimy/NHM/Neural-Hive-Mind/ml_pipelines/training/train_specialist_model.py" ]; then
    # Execução local (fora do cluster)
    TRAINING_DIR="/home/jimy/NHM/Neural-Hive-Mind/ml_pipelines/training"
    echo "🏠 Running in LOCAL mode"
    echo "   Training directory: $TRAINING_DIR"
    echo ""

    # Port-forward MLflow se necessário
    if ! curl -sf http://localhost:5000/health > /dev/null 2>&1; then
        echo "   Starting MLflow port-forward..."
        kubectl port-forward -n mlflow svc/mlflow 5000:5000 >/dev/null 2>&1 &
        PF_PID=$!
        sleep 2
        echo "   ✅ MLflow port-forwarded (PID: $PF_PID)"
        echo ""

        # Trap para limpar port-forward on exit
        trap "kill $PF_PID 2>/dev/null || true" EXIT
    fi

    # Port-forward MongoDB se necessário
    if ! mongosh mongodb://localhost:27017 --eval "db.adminCommand('ping')" >/dev/null 2>&1; then
        echo "   Starting MongoDB port-forward..."
        kubectl port-forward -n data-layer svc/mongodb 27017:27017 >/dev/null 2>&1 &
        PF_MONGO_PID=$!
        sleep 2
        echo "   ✅ MongoDB port-forwarded (PID: $PF_MONGO_PID)"
        echo ""

        # Trap para limpar port-forward on exit
        trap "kill $PF_PID $PF_MONGO_PID 2>/dev/null || true" EXIT
    fi
else
    # Execução no cluster (pod)
    TRAINING_DIR="/app/training"
    echo "🐳 Running in CLUSTER mode"
    echo ""
fi

cd "$TRAINING_DIR"

# Loop de treinamento
RESULTS=()
for specialist in "${SPECIALISTS[@]}"; do
    echo "📊 Training model for: $specialist"
    echo "   Min samples: $MIN_REAL_SAMPLES"
    echo ""

    LOG_FILE="/tmp/retrain_${specialist}_$(date +%Y%m%d_%H%M%S).log"

    if python3 train_specialist_model.py \
        --specialist-type "$specialist" \
        --model-type "$MODEL_TYPE" \
        --hyperparameter-tuning "$HYPERPARAMETER_TUNING" \
        --promote-if-better "$PROMOTE_IF_BETTER" \
        --allow-synthetic-fallback "$ALLOW_SYNTHETIC_FALLBACK" \
        --real-data-days "$REAL_DATA_DAYS" \
        --min-real-samples "$MIN_REAL_SAMPLES" 2>&1 | tee "$LOG_FILE"; then
        echo "   ✅ Model trained for $specialist"
        RESULTS+=("$specialist:SUCCESS")

        # Extrair métricas do log
        PRECISION=$(grep -oP 'test_precision: \K[\d.]+' "$LOG_FILE" || echo "N/A")
        RECALL=$(grep -oP 'test_recall: \K[\d.]+' "$LOG_FILE" || echo "N/A")
        F1=$(grep -oP 'test_f1: \K[\d.]+' "$LOG_FILE" || echo "N/A")

        echo "   📈 Metrics: Precision=$PRECISION, Recall=$RECALL, F1=$F1"
    else
        echo "   ❌ Training failed for $specialist"
        RESULTS+=("$specialist:FAILED")

        # Mostrar últimas linhas do log para debug
        echo "   📋 Last 20 lines of log:"
        tail -20 "$LOG_FILE" | sed 's/^/      /'
    fi

    echo ""

    # Aguardar entre specialists
    if [ "$specialist" != "${SPECIALISTS[-1]}" ]; then
        sleep 2
    fi
done

echo ""
echo "============================================="
echo "📊 Training Summary"
echo "============================================="
echo ""

for result in "${RESULTS[@]}"; do
    specialist="${result%:*}"
    status="${result#*:}"
    if [ "$status" = "SUCCESS" ]; then
        echo "   ✅ $specialist"
    else
        echo "   ❌ $specialist"
    fi
done

echo ""
echo "🔄 Next steps:"
echo "   1. Validate models loaded:"
echo "      kubectl exec -n semantic-translation deployment/specialist-technical -- curl -s http://localhost:8080/status | jq ."
echo ""
echo "   2. If models not updated, restart pods:"
echo "      kubectl rollout restart deployment -n semantic-translation -l app.kubernetes.io/component=specialist"
echo ""
echo "   3. Monitor predictions confidence in logs:"
echo "      kubectl logs -n semantic-translation -f -l app.kubernetes.io/component=specialist | grep confidence"
echo ""
