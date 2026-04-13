#!/bin/bash

# Script para aplicar configuração do AlertManager Neural Hive Mind

set -e

NAMESPACE="observability"
CONFIG_DIR="/home/jimy/NHM/Neural-Hive-Mind/monitoring/alertmanager"
SECRET_NAME="neural-hive-alertmanager-config"

echo "=== Neural Hive Mind - AlertManager Configuration ==="
echo ""

# 1. Criar ConfigMap de webhook-logger
echo "📝 Aplicando webhook-logger..."
kubectl apply -f "${CONFIG_DIR}/webhook-logger/deployment.yaml"

if [[ $? -eq 0 ]]; then
    echo "   ✅ webhook-logger aplicado"
else
    echo "   ❌ Falha ao aplicar webhook-logger"
    exit 1
fi

# 2. Criar Secret com configuração do AlertManager
echo ""
echo "📝 Aplicando configuração do AlertManager..."

# Ler e comprimir a configuração
CONFIG_FILE="${CONFIG_DIR}/alertmanager-config.yaml"
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "   ❌ Arquivo não encontrado: $CONFIG_FILE"
    exit 1
fi

# Criar Secret com a configuração comprimida (formato esperado pelo Prometheus Operator)
kubectl create secret generic "$SECRET_NAME" \
    --from-file="alertmanager.yaml.gz=${CONFIG_FILE}" \
    --dry-run=client -o yaml | \
    kubectl apply -n "$NAMESPACE" -f -

if [[ $? -eq 0 ]]; then
    echo "   ✅ Configuração do AlertManager aplicada"
else
    echo "   ❌ Falha ao aplicar configuração"
    exit 1
fi

# 3. Atualizar o AlertManager para usar a nova configuração
echo ""
echo "🔄 Reiniciando AlertManager para aplicar nova configuração..."
kubectl rollout restart deployment neural-hive-prometheus-kub-alertmanager -n "$NAMESPACE"

if [[ $? -eq 0 ]]; then
    echo "   ✅ AlertManager reiniciado"
else
    echo "   ⚠️  Não foi possível reiniciar (pode ser StatefulSet)"
    # Tentar com StatefulSet
    kubectl rollout restart statefulset neural-hive-prometheus-kub-alertmanager -n "$NAMESPACE" 2>/dev/null || echo "   ℹ️  Skip restart manual"
fi

echo ""
echo "=== Verificação ==="
echo ""
echo "Pods:"
kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=webhook-logger 2>/dev/null || echo "  webhook-logger: não encontrado"
kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=alertmanager 2>/dev/null || echo "  alertmanager: não encontrado"

echo ""
echo "Services:"
kubectl get svc -n "$NAMESPACE" webhook-logger 2>/dev/null || echo "  webhook-logger: não encontrado"

echo ""
echo "Secrets:"
kubectl get secret -n "$NAMESPACE" | grep alertmanager

echo ""
echo "=== Teste de Health Check ==="
sleep 5
kubectl run test-webhook --rm -i --restart=Never --image=curlimages/curl -- \
    curl -s http://webhook-logger.${NAMESPACE}.svc.cluster.local:8080/health || echo "  ⚠️  Health check falhou (pod pode estar starting)"

echo ""
echo "=== Configuração concluída ==="
echo ""
echo "Próximos passos:"
echo "1. Configure os endpoints de forward em webhook-logger-config ConfigMap"
echo "2. Teste os alertas simulando uma falha:"
echo "   kubectl scale deployment queen-agent --replicas=0 -n neural-hive"
echo "3. Verifique os alertas em:"
echo "   kubectl port-forward -n ${NAMESPACE} svc/neural-hive-prometheus-kub-alertmanager :9093"
echo "   Acesse: http://localhost:9093"
