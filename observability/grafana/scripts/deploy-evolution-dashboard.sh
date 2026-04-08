#!/bin/bash
# Script para deploy do Evolution Executive Dashboard no Grafana
# Uso: ./deploy-evolution-dashboard.sh [namespace]

set -e

NAMESPACE=${1:-monitoring}

echo "Deploying Evolution Executive Overview Dashboard..."
echo "Namespace: $NAMESPACE"

# Verificar se kubectl está disponível
if ! command -v kubectl &> /dev/null; then
    echo "Error: kubectl not found. Please install kubectl first."
    exit 1
fi

# Verificar se o namespace existe
if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
    echo "Creating namespace: $NAMESPACE"
    kubectl create namespace "$NAMESPACE"
fi

# Aplicar o ConfigMap
echo "Applying ConfigMap..."
kubectl apply -f "$(dirname "$0")/../k8s/evolution-dashboard-configmap.yaml" -n "$NAMESPACE"

# Verificar se o Grafana Deployment existe e tem o volume montado
GRAFANA_DEPLOYMENT=$(kubectl get deployment -n "$NAMESPACE" -l app=grafana -o name 2>/dev/null || echo "")

if [ -z "$GRAFANA_DEPLOYMENT" ]; then
    echo "Warning: Grafana deployment not found in namespace $NAMESPACE"
    echo "Please ensure Grafana is installed and the ConfigMap is mounted as a volume"
    echo ""
    echo "To mount the dashboard, add to your Grafana deployment:"
    echo "  volumeMounts:"
    echo "    - name: evolution-dashboard"
    echo "      mountPath: /etc/grafana/provisioning/dashboards/evolution"
    echo "  volumes:"
    echo "    - name: evolution-dashboard"
    echo "      configMap:"
    echo "        name: grafana-evolution-dashboard"
else
    echo "Grafana deployment found: $GRAFANA_DEPLOYMENT"
    echo "Dashboard ConfigMap applied successfully"
    echo ""
    echo "Note: You may need to restart Grafana pods to load the new dashboard:"
    echo "  kubectl rollout restart $GRAFANA_DEPLOYMENT -n $NAMESPACE"
fi

echo ""
echo "Dashboard Details:"
echo "  UID: evolution-executive-overview"
echo "  Title: Evolution Executive Overview"
echo "  Tags: evolution, executive, ml, meta-learning, fase4"
echo ""
echo "Access the dashboard at: http://grafana.$NAMESPACE.svc.cluster.local/d/evolution-executive-overview"
