#!/bin/bash
# Script de destruição ordenada do cluster Neural Hive-Mind
# Uso: ./destroy-cluster-ordered.sh [ambiente] [--skip-terraform]

set -e

ENV="${1:-local}"
SKIP_TERRAFORM=false
if [[ "${2}" == "--skip-terraform" ]]; then
  SKIP_TERRAFORM=true
fi

echo "=== Destruição Neural Hive-Mind - ${ENV} ==="
echo "AVISO: Este processo IRREVERSÍVEL irá destruir todo o cluster."
read -p "Confirmar destruição? (digite 'SIM' para continuar): " confirm
if [[ "${confirm}" != "SIM" ]]; then
  echo "Operação cancelada."
  exit 1
fi

# 2.1 Remover Serviços de Aplicação (Camada 7-8)
echo "[Fase 1/8] Removendo serviços de aplicação..."
helm uninstall gateway-intencoes -n gateway-intencoes --no-hooks 2>/dev/null || true
helm uninstall explainability-api -n neural-hive-observability --no-hooks 2>/dev/null || true
helm uninstall approval-service -n neural-hive-orchestration --no-hooks 2>/dev/null || true
helm uninstall execution-ticket-service -n neural-hive-execution --no-hooks 2>/dev/null || true
helm uninstall service-registry -n neural-hive-system --no-hooks 2>/dev/null || true
helm uninstall semantic-translation-engine -n neural-hive-cognition --no-hooks 2>/dev/null || true
helm uninstall code-forge -n neural-hive-code-forge --no-hooks 2>/dev/null || true
helm uninstall mcp-tool-catalog -n neural-hive-mcp --no-hooks 2>/dev/null || true
echo "Serviços de aplicação removidos."

# 2.2 Remover Agentes (Camada 6)
echo "[Fase 2/8] Removendo agentes..."
helm uninstall optimizer-agents -n neural-hive-execution --no-hooks 2>/dev/null || true
helm uninstall analyst-agents -n neural-hive-cognition --no-hooks 2>/dev/null || true
helm uninstall guard-agents -n neural-hive-governance --no-hooks 2>/dev/null || true
helm uninstall scout-agents -n neural-hive-execution --no-hooks 2>/dev/null || true
helm uninstall worker-agents -n neural-hive-execution --no-hooks 2>/dev/null || true
helm uninstall queen-agent -n neural-hive-orchestration --no-hooks 2>/dev/null || true
echo "Agentes removidos."

# 2.3 Remover Especialistas (Camada 5)
echo "[Fase 3/8] Removendo especialistas..."
helm uninstall specialist-evolution -n neural-hive-specialists --no-hooks 2>/dev/null || true
helm uninstall specialist-behavior -n neural-hive-specialists --no-hooks 2>/dev/null || true
helm uninstall specialist-architecture -n neural-hive-specialists --no-hooks 2>/dev/null || true
helm uninstall specialist-technical -n neural-hive-specialists --no-hooks 2>/dev/null || true
helm uninstall specialist-business -n neural-hive-specialists --no-hooks 2>/dev/null || true
echo "Especialistas removidos."

# 2.4 Remover Serviços Core (Camada 4)
echo "[Fase 4/8] Removendo serviços core..."
helm uninstall sla-management-system -n neural-hive-orchestration --no-hooks 2>/dev/null || true
helm uninstall self-healing-engine -n neural-hive-system --no-hooks 2>/dev/null || true
helm uninstall orchestrator-dynamic -n neural-hive-orchestration --no-hooks 2>/dev/null || true
helm uninstall consensus-engine -n neural-hive-cognition --no-hooks 2>/dev/null || true
helm uninstall memory-layer-api -n neural-hive-memory --no-hooks 2>/dev/null || true
echo "Serviços core removidos."

# 2.5 Remover Observabilidade (Camada 3)
echo "[Fase 5/8] Removendo observabilidade..."
helm uninstall grafana -n neural-hive-observability --no-hooks 2>/dev/null || true
helm uninstall prometheus-stack -n neural-hive-observability --no-hooks 2>/dev/null || true
helm uninstall jaeger -n neural-hive-observability --no-hooks 2>/dev/null || true
helm uninstall otel-collector -n neural-hive-observability --no-hooks 2>/dev/null || true
helm uninstall prometheus-pushgateway -n neural-hive-observability --no-hooks 2>/dev/null || true
echo "Observabilidade removida."

# 2.6 Remover Infraestrutura de Dados (Camada 2)
echo "[Fase 6/8] Removendo infraestrutura de dados..."
helm uninstall clickhouse -n clickhouse-cluster --no-hooks 2>/dev/null || true
helm uninstall neo4j -n neo4j-cluster --no-hooks 2>/dev/null || true
helm uninstall mongodb -n mongodb-cluster --no-hooks 2>/dev/null || true
helm uninstall redis-cluster -n redis-cluster --no-hooks 2>/dev/null || true
helm uninstall kafka-topics -n kafka --no-hooks 2>/dev/null || true
kubectl delete kafka neural-hive-kafka -n kafka --ignore-not-found=true 2>/dev/null || true
echo "Infraestrutura de dados removida."

# 2.7 Remover Operators
echo "[Fase 6/8] Removendo operators..."
helm uninstall clickhouse-operator -n clickhouse-operator --no-hooks 2>/dev/null || true
helm uninstall mongodb-operator -n mongodb-operator --no-hooks 2>/dev/null || true
helm uninstall redis-operator -n redis-operator --no-hooks 2>/dev/null || true
helm uninstall strimzi-kafka-operator -n kafka --no-hooks 2>/dev/null || true
echo "Operators removidos."

# 2.8 Remover Segurança e Service Mesh (Camada 1)
echo "[Fase 7/8] Removendo segurança e service mesh..."
kubectl delete -f policies/constraints/ --ignore-not-found=true 2>/dev/null || true
kubectl delete -f policies/constraint-templates/ --ignore-not-found=true 2>/dev/null || true
helm uninstall opa-gatekeeper -n gatekeeper-system --no-hooks 2>/dev/null || true
helm uninstall sigstore-policy-controller -n cosign-system --no-hooks 2>/dev/null || true
helm uninstall istiod -n istio-system --no-hooks 2>/dev/null || true
helm uninstall istio-base -n istio-system --no-hooks 2>/dev/null || true
helm uninstall vault -n vault --no-hooks 2>/dev/null || true
helm uninstall spire -n spire-system --no-hooks 2>/dev/null || true
helm uninstall temporal -n temporal --no-hooks 2>/dev/null || true
echo "Segurança e service mesh removidos."

# 2.9 Remover Bootstrap (Camada 0)
echo "[Fase 8/8] Removendo bootstrap..."
kubectl delete -f k8s/bootstrap/pod-security-standards.yaml --ignore-not-found=true 2>/dev/null || true
kubectl delete -f k8s/bootstrap/network-policies.yaml --ignore-not-found=true 2>/dev/null || true
kubectl delete -f k8s/bootstrap/rbac.yaml --ignore-not-found=true 2>/dev/null || true
kubectl delete -f k8s/bootstrap/data-governance-crds.yaml --ignore-not-found=true 2>/dev/null || true
kubectl delete -f k8s/bootstrap/namespaces.yaml --ignore-not-found=true 2>/dev/null || true
kubectl delete -f k8s/infrastructure/namespaces-infrastructure.yaml --ignore-not-found=true 2>/dev/null || true
echo "Bootstrap removido."

# 2.10 Destruir Cluster Kubernetes (Terraform) - opcional
if [[ "${SKIP_TERRAFORM}" == false ]]; then
  echo "[Fase 9/9] Destruindo cluster Kubernetes (Terraform)..."
  if [[ -d "infrastructure/terraform" ]]; then
    cd infrastructure/terraform
    terraform destroy -var-file="../../environments/${ENV}/terraform.tfvars -auto-approve
  else
    echo "AVISO: Diretório terraform não encontrado, pulando destruição do cluster."
  fi
else
  echo "[Fase 9/9] Destruição do cluster pulada (--skip-terraform)."
fi

echo ""
echo "=== Destruição Completa ==="
echo "Recursos Kubernetes restantes:"
kubectl get all --all-namespaces 2>/dev/null || echo "Nenhum recurso encontrado."
