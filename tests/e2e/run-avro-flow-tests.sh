#!/bin/bash
# Script para executar testes E2E do fluxo Avro localmente
#
# Uso:
#   ./tests/e2e/run-avro-flow-tests.sh
#   ./tests/e2e/run-avro-flow-tests.sh --verbose
#   ./tests/e2e/run-avro-flow-tests.sh -k "test_schema_registry"
#
# Pré-requisitos:
#   - Cluster Kubernetes com Neural Hive Mind deployado
#   - Schema Registry (Apicurio) operacional
#   - Schemas registrados (via init job)

set -e

echo "🧪 Executando Testes E2E do Fluxo Avro"
echo "======================================="

# Verificar cluster Kubernetes
echo ""
echo "📋 Verificando pré-requisitos..."

if ! kubectl cluster-info &> /dev/null; then
    echo "❌ Cluster Kubernetes não acessível"
    echo "   Verifique se kubectl está configurado corretamente"
    exit 1
fi
echo "✅ Cluster Kubernetes acessível"

# Verificar namespaces necessários
REQUIRED_NAMESPACES=("neural-hive-kafka" "neural-hive-specialists" "neural-hive-orchestration")
for ns in "${REQUIRED_NAMESPACES[@]}"; do
    if ! kubectl get namespace "$ns" &> /dev/null; then
        echo "❌ Namespace $ns não encontrado"
        exit 1
    fi
done
echo "✅ Namespaces necessários existem"

# Verificar Schema Registry
SCHEMA_REGISTRY_POD=$(kubectl get pods -n neural-hive-kafka -l app=schema-registry -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [ -z "$SCHEMA_REGISTRY_POD" ]; then
    echo "⚠️  Schema Registry pod não encontrado"
    echo "   Testes que dependem do Schema Registry podem falhar"
else
    echo "✅ Schema Registry pod encontrado: $SCHEMA_REGISTRY_POD"
fi

# Verificar Kafka
KAFKA_POD=$(kubectl get pods -n neural-hive-kafka -l app.kubernetes.io/name=kafka -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [ -z "$KAFKA_POD" ]; then
    echo "⚠️  Kafka pod não encontrado"
    echo "   Testes que dependem do Kafka podem falhar"
else
    echo "✅ Kafka pod encontrado: $KAFKA_POD"
fi

# Verificar Consensus Engine
CONSENSUS_POD=$(kubectl get pods -n neural-hive-orchestration -l app=consensus-engine -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [ -z "$CONSENSUS_POD" ]; then
    echo "⚠️  Consensus Engine pod não encontrado"
else
    echo "✅ Consensus Engine pod encontrado: $CONSENSUS_POD"
fi

echo ""
echo "🚀 Iniciando testes..."
echo ""

# Criar diretório de resultados se não existir
mkdir -p tests/results

# Executar testes
pytest tests/e2e/test_avro_flow_complete.py \
    -v \
    --tb=short \
    --junit-xml=tests/results/avro-flow-junit.xml \
    --cov=services/semantic-translation-engine \
    --cov=services/consensus-engine \
    --cov-report=html:tests/results/avro-flow-coverage \
    --log-cli-level=INFO \
    "$@"

echo ""
echo "✅ Testes E2E do Fluxo Avro concluídos"
echo "📊 Relatório de cobertura: tests/results/avro-flow-coverage/index.html"
