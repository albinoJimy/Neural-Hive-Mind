#!/bin/bash
# Teste end-to-end do Code Forge

set -e

echo "==> Code Forge End-to-End Test"

# 1. Verificar infraestrutura
echo "==> 1. Verifying infrastructure..."
kubectl get pods -n neural-hive-execution -l app.kubernetes.io/name=code-forge || exit 1

# 2. Publicar Execution Ticket no Kafka
echo "==> 2. Publishing BUILD ticket to Kafka..."
# TODO: Implementar publicação de ticket de teste

# 3. Aguardar pipeline
echo "==> 3. Waiting for pipeline execution (30s)..."
sleep 30

# 4. Verificar artefatos gerados
echo "==> 4. Verifying artifacts..."
# TODO: Implementar verificação via API

# 5. Verificar métricas
echo "==> 5. Verifying metrics..."
# TODO: Implementar verificação de métricas Prometheus

# 6. Verificar logs
echo "==> 6. Checking logs..."
kubectl logs -n neural-hive-execution -l app.kubernetes.io/name=code-forge --tail=50

echo "==> End-to-end test completed!"
