#!/bin/bash
set -e

echo "Setting up cert-manager for Istio certificates..."

if ! kubectl get namespace cert-manager &>/dev/null; then
  echo "cert-manager not found. Installing..."
  kubectl create namespace cert-manager
  helm repo add jetstack https://charts.jetstack.io
  helm repo update
  helm install cert-manager jetstack/cert-manager \
    --namespace cert-manager \
    --version v1.13.0 \
    --set installCRDs=true
fi

kubectl apply -f helm/istio-base/cert-manager-issuer.yaml

echo "Waiting for certificate to be ready..."
kubectl wait --for=condition=Ready certificate/istio-ingressgateway-cert \
  -n istio-system --timeout=300s

echo "cert-manager setup complete!"