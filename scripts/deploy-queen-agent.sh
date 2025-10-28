#!/bin/bash

set -e

NAMESPACE="neural-hive"
RELEASE_NAME="queen-agent"
CHART_PATH="./services/queen-agent/helm-chart"

echo "🚀 Deploying Queen Agent to Kubernetes..."

# Verificar se o namespace existe
if ! kubectl get namespace $NAMESPACE &> /dev/null; then
    echo "📦 Creating namespace $NAMESPACE..."
    kubectl create namespace $NAMESPACE
fi

# Verificar se os secrets necessários existem
echo "🔐 Checking required secrets..."

SECRETS_MISSING=false

if ! kubectl get secret queen-agent-mongodb -n $NAMESPACE &> /dev/null; then
    echo "⚠️  Secret 'queen-agent-mongodb' not found"
    SECRETS_MISSING=true
fi

if ! kubectl get secret queen-agent-redis -n $NAMESPACE &> /dev/null; then
    echo "⚠️  Secret 'queen-agent-redis' not found"
    SECRETS_MISSING=true
fi

if ! kubectl get secret queen-agent-neo4j -n $NAMESPACE &> /dev/null; then
    echo "⚠️  Secret 'queen-agent-neo4j' not found"
    SECRETS_MISSING=true
fi

if [ "$SECRETS_MISSING" = true ]; then
    echo ""
    echo "❌ Missing required secrets. Please create them first:"
    echo ""
    echo "  kubectl create secret generic queen-agent-mongodb -n $NAMESPACE \\"
    echo "    --from-literal=MONGODB_URI='mongodb://user:password@mongodb:27017'"
    echo ""
    echo "  kubectl create secret generic queen-agent-redis -n $NAMESPACE \\"
    echo "    --from-literal=REDIS_CLUSTER_NODES='redis-0:6379,redis-1:6379,redis-2:6379' \\"
    echo "    --from-literal=REDIS_PASSWORD='your-redis-password'"
    echo ""
    echo "  kubectl create secret generic queen-agent-neo4j -n $NAMESPACE \\"
    echo "    --from-literal=NEO4J_URI='bolt://neo4j:7687' \\"
    echo "    --from-literal=NEO4J_USER='neo4j' \\"
    echo "    --from-literal=NEO4J_PASSWORD='your-neo4j-password'"
    echo ""
    exit 1
fi

# Deploy do Kafka topic
echo "📡 Deploying Kafka topic..."
kubectl apply -f ./k8s/kafka-topics/strategic-decisions-topic.yaml

# Aguardar o topic estar pronto
echo "⏳ Waiting for Kafka topic to be ready..."
kubectl wait --for=condition=Ready kafkatopic/strategic-decisions -n neural-hive --timeout=60s

# Deploy via Helm
echo "📦 Installing/Upgrading Helm release..."
helm upgrade --install $RELEASE_NAME $CHART_PATH \
    --namespace $NAMESPACE \
    --create-namespace \
    --wait \
    --timeout 5m \
    --set secrets.MONGODB_URI="" \
    --set secrets.REDIS_CLUSTER_NODES="" \
    --set secrets.REDIS_PASSWORD="" \
    --set secrets.NEO4J_URI="" \
    --set secrets.NEO4J_USER="" \
    --set secrets.NEO4J_PASSWORD=""

echo ""
echo "✅ Queen Agent deployed successfully!"
echo ""
echo "📊 Deployment status:"
kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=queen-agent
echo ""
echo "🔍 To check logs:"
echo "  kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=queen-agent -f"
echo ""
echo "📈 To access metrics:"
echo "  kubectl port-forward -n $NAMESPACE svc/queen-agent 9090:9090"
echo ""
