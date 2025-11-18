#!/usr/bin/env bash
set -euo pipefail

# Simple installer for Portainer (Helm) on a Kubernetes cluster.
# Requires: kubectl configured to target the cluster, and helm installed.

NAMESPACE=portainer
RELEASE=portainer
HELM_REPO_NAME=portainer
# Try a few possible Helm repo URLs for Portainer (some versions/use-cases use slightly different paths)
HELM_REPO_URLS=(
  "https://portainer.github.io/k8s/helm/"
  "https://portainer.github.io/k8s/"
  "https://charts.portainer.io/"
)
VALUES_FILE="$(dirname "$0")/portainer-values.yaml"

function die(){ echo "$*" >&2; exit 1; }

command -v kubectl >/dev/null 2>&1 || die "kubectl not found in PATH. Install kubectl and configure your cluster context."
command -v helm >/dev/null 2>&1 || die "helm not found in PATH. Install Helm (v3+) to use this installer."

echo "Creating namespace '${NAMESPACE}' (if missing)..."
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

echo "Adding Helm repo ${HELM_REPO_NAME} (trying multiple known URLs)..."
added=false
for url in "${HELM_REPO_URLS[@]}"; do
  echo "  trying: $url"
  if helm repo add "${HELM_REPO_NAME}" "$url" 2>/dev/null; then
    echo "  added repo ${HELM_REPO_NAME} -> $url"
    added=true
    break
  else
    echo "  failed: $url"
    # remove any partial entry
    helm repo remove "${HELM_REPO_NAME}" >/dev/null 2>&1 || true
  fi
done

if ! $added; then
  echo "Warning: could not add a working Helm repo for '${HELM_REPO_NAME}'."
  echo "The subsequent install attempt may fail with 'repo not found'."
  echo "Please check your network/firewall or verify the correct Portainer Helm repo URL in the official docs."
fi

helm repo update

# Use supplied values file if present, otherwise install with defaults and LoadBalancer service
if [ -f "$VALUES_FILE" ]; then
  echo "Using values file: $VALUES_FILE"
  helm upgrade --install ${RELEASE} ${HELM_REPO_NAME}/portainer \
    --namespace ${NAMESPACE} \
    --create-namespace \
    -f "$VALUES_FILE"
else
  echo "No values file found. Installing with default values and service.type=LoadBalancer"
  helm upgrade --install ${RELEASE} ${HELM_REPO_NAME}/portainer \
    --namespace ${NAMESPACE} \
    --create-namespace \
    --set service.type=LoadBalancer
fi

echo "Deployment requested. To check status run:"
echo "  kubectl get all -n ${NAMESPACE}"
echo "To find the Portainer external endpoint (if LoadBalancer):"
echo "  kubectl get svc -n ${NAMESPACE}"

echo "If your cluster does not support LoadBalancer, consider setting service.type=NodePort or using an Ingress. See deploy/portainer/README.md for details."
