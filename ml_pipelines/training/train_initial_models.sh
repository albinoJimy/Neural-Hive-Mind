#!/bin/bash
# =============================================================================
# Script de Treinamento Inicial de Modelos ML
#
# Valida disponibilidade de infraestrutura e treina todos os modelos preditivos:
# - AnomalyDetector (IsolationForest)
# - LoadPredictor (Prophet)
# - SchedulingPredictor (XGBoost)
#
# Uso: ./train_initial_models.sh [--skip-validation] [--dry-run]
# =============================================================================

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Argumentos
SKIP_VALIDATION=false
DRY_RUN=false

for arg in "$@"; do
    case $arg in
        --skip-validation)
            SKIP_VALIDATION=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
    esac
done

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# =============================================================================
# Validacao de Conexoes
# =============================================================================

validate_mongodb() {
    log_info "Validando conexao MongoDB..."

    python3 -c "
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import os

async def check():
    uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    await client.admin.command('ping')
    print('MongoDB: OK')
    client.close()

asyncio.run(check())
" 2>/dev/null

    if [ $? -eq 0 ]; then
        log_info "MongoDB conectado com sucesso"
        return 0
    else
        log_error "Falha ao conectar ao MongoDB"
        return 1
    fi
}

validate_clickhouse() {
    log_info "Validando conexao ClickHouse (opcional)..."

    python3 -c "
from clickhouse_driver import Client
import os

host = os.getenv('CLICKHOUSE_HOST', 'localhost')
port = int(os.getenv('CLICKHOUSE_PORT', '9000'))
user = os.getenv('CLICKHOUSE_USER', 'default')
password = os.getenv('CLICKHOUSE_PASSWORD', '')

client = Client(host=host, port=port, user=user, password=password, connect_timeout=5)
client.execute('SELECT 1')
print('ClickHouse: OK')
" 2>/dev/null

    if [ $? -eq 0 ]; then
        log_info "ClickHouse conectado com sucesso"
        return 0
    else
        log_warn "ClickHouse nao disponivel (continuando apenas com MongoDB)"
        return 0  # Nao falha, ClickHouse e opcional
    fi
}

validate_mlflow() {
    log_info "Validando conexao MLflow..."

    python3 -c "
import mlflow
import os

tracking_uri = os.getenv('MLFLOW_TRACKING_URI', 'http://localhost:5000')
mlflow.set_tracking_uri(tracking_uri)

# Tenta criar experimento de teste
try:
    exp = mlflow.get_experiment_by_name('_validation_test')
    print('MLflow: OK')
except Exception as e:
    # Tenta listar experimentos como fallback
    exps = mlflow.search_experiments()
    print('MLflow: OK')
" 2>/dev/null

    if [ $? -eq 0 ]; then
        log_info "MLflow conectado com sucesso"
        return 0
    else
        log_error "Falha ao conectar ao MLflow"
        return 1
    fi
}

# =============================================================================
# Treinamento de Modelos
# =============================================================================

train_anomaly_detector() {
    log_info "Treinando AnomalyDetector (IsolationForest)..."

    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Comando: python train_predictive_models.py --model-type anomaly --model-algorithm isolation_forest --promote-if-better --min-samples 1000"
        return 0
    fi

    python3 "$SCRIPT_DIR/train_predictive_models.py" \
        --model-type anomaly \
        --model-algorithm isolation_forest \
        --promote-if-better \
        --min-samples 1000 \
        --training-window-days 180

    if [ $? -eq 0 ]; then
        log_info "AnomalyDetector treinado com sucesso"
        return 0
    else
        log_error "Falha ao treinar AnomalyDetector"
        return 1
    fi
}

train_load_predictor() {
    log_info "Treinando LoadPredictor (Prophet)..."

    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Comando: python train_predictive_models.py --model-type load --promote-if-better --training-window-days 540"
        return 0
    fi

    python3 "$SCRIPT_DIR/train_predictive_models.py" \
        --model-type load \
        --promote-if-better \
        --training-window-days 540

    if [ $? -eq 0 ]; then
        log_info "LoadPredictor treinado com sucesso"
        return 0
    else
        log_error "Falha ao treinar LoadPredictor"
        return 1
    fi
}

train_scheduling_predictor() {
    log_info "Treinando SchedulingPredictor (XGBoost)..."

    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Comando: python train_predictive_models.py --model-type scheduling --model-algorithm xgboost --promote-if-better"
        return 0
    fi

    python3 "$SCRIPT_DIR/train_predictive_models.py" \
        --model-type scheduling \
        --model-algorithm xgboost \
        --promote-if-better \
        --min-samples 1000

    if [ $? -eq 0 ]; then
        log_info "SchedulingPredictor treinado com sucesso"
        return 0
    else
        log_error "Falha ao treinar SchedulingPredictor"
        return 1
    fi
}

# =============================================================================
# Verificacao de Modelos Registrados
# =============================================================================

verify_models_registered() {
    log_info "Verificando modelos registrados no MLflow..."

    python3 -c "
from mlflow.tracking import MlflowClient
import os
import sys

mlflow_uri = os.getenv('MLFLOW_TRACKING_URI', 'http://localhost:5000')
client = MlflowClient(mlflow_uri)

expected_models = [
    'anomaly-detector-isolation_forest',
    'load-predictor-60m',
    'load-predictor-360m',
    'load-predictor-1440m',
    'scheduling-predictor-xgboost'
]

missing_models = []
models_in_production = []

for model_name in expected_models:
    try:
        versions = client.get_latest_versions(model_name, stages=['Production'])
        if versions:
            models_in_production.append(model_name)
            print(f'  [OK] {model_name} v{versions[0].version} em Production')
        else:
            # Verifica se existe em qualquer stage
            all_versions = client.get_latest_versions(model_name)
            if all_versions:
                print(f'  [WARN] {model_name} existe mas nao esta em Production')
            else:
                missing_models.append(model_name)
                print(f'  [MISSING] {model_name}')
    except Exception as e:
        missing_models.append(model_name)
        print(f'  [ERROR] {model_name}: {e}')

print('')
print(f'Modelos em Production: {len(models_in_production)}/{len(expected_models)}')

if missing_models:
    print(f'Modelos faltando: {missing_models}')
    sys.exit(1)
else:
    print('Todos os modelos verificados com sucesso!')
    sys.exit(0)
"

    return $?
}

# =============================================================================
# Main
# =============================================================================

main() {
    echo "============================================="
    echo "  Neural Hive-Mind - Treinamento Inicial ML"
    echo "============================================="
    echo ""

    # Validacao de conexoes
    if [ "$SKIP_VALIDATION" = false ]; then
        log_info "Etapa 1/5: Validando conexoes..."

        validate_mongodb || exit 1
        validate_clickhouse
        validate_mlflow || exit 1

        echo ""
    fi

    # Treinamento
    log_info "Etapa 2/5: Treinando AnomalyDetector..."
    train_anomaly_detector || exit 1
    echo ""

    log_info "Etapa 3/5: Treinando LoadPredictor..."
    train_load_predictor || exit 1
    echo ""

    log_info "Etapa 4/5: Treinando SchedulingPredictor..."
    train_scheduling_predictor || exit 1
    echo ""

    # Verificacao
    if [ "$DRY_RUN" = false ]; then
        log_info "Etapa 5/5: Verificando modelos registrados..."
        verify_models_registered

        if [ $? -eq 0 ]; then
            echo ""
            log_info "============================================="
            log_info "  Treinamento inicial concluido com sucesso!"
            log_info "============================================="
        else
            log_warn "Alguns modelos podem nao estar em Production"
            log_warn "Verifique manualmente no MLflow UI"
        fi
    else
        log_info "Etapa 5/5: [DRY-RUN] Verificacao de modelos ignorada"
    fi

    echo ""
}

main "$@"
