#!/bin/bash
# Script de deploy do Self-Healing Engine via Helm

set -e

RELEASE_NAME="self-healing-engine"
CHART_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/helm/self-healing-engine"
NAMESPACE="neural-hive-orchestration"

echo "🚀 Deploying Self-Healing Engine via Helm..."
echo "Release: $RELEASE_NAME"
echo "Namespace: $NAMESPACE"
echo "Chart: $CHART_DIR"

# Criar namespace se não existir
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# Verificar se release já existe
if helm list -n "$NAMESPACE" | grep -q "^$RELEASE_NAME\s"; then
    echo "📦 Upgrading existing release..."
    helm upgrade "$RELEASE_NAME" "$CHART_DIR" \
        --namespace "$NAMESPACE" \
        --wait \
        --timeout 5m
else
    echo "📦 Installing new release..."
    helm install "$RELEASE_NAME" "$CHART_DIR" \
        --namespace "$NAMESPACE" \
        --wait \
        --timeout 5m
fi

echo ""
echo "✅ Self-Healing Engine deployed successfully!"
echo ""
echo "🔍 Check pods:"
kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=self-healing-engine
echo ""
echo "📊 Get release status:"
helm status "$RELEASE_NAME" -n "$NAMESPACE"
echo ""
echo "📈 Check HPA:"
kubectl get hpa -n "$NAMESPACE" -l app.kubernetes.io/name=self-healing-engine

echo ""
echo "💡 To uninstall:"
echo "   helm uninstall $RELEASE_NAME -n $NAMESPACE"
