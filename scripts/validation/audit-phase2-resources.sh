#!/bin/bash
# Audit resource limits across Phase 2 services

SERVICES=(
  "orchestrator-dynamic"
  "queen-agent"
  "worker-agents"
  "scout-agents"
  "analyst-agents"
  "optimizer-agents"
  "guard-agents"
  "service-registry"
  "execution-ticket-service"
  "sla-management-system"
  "code-forge"
  "self-healing-engine"
  "mcp-tool-catalog"
)

declare -A SERVICE_NAMESPACES=(
  ["orchestrator-dynamic"]="neural-hive-orchestration"
  ["queen-agent"]="neural-hive-estrategica"
  ["worker-agents"]="neural-hive-execution"
  ["scout-agents"]="neural-hive-exploration"
  ["analyst-agents"]="neural-hive-analytics"
  ["optimizer-agents"]="neural-hive-estrategica"
  ["guard-agents"]="neural-hive-resilience"
  ["service-registry"]="neural-hive-registry"
  ["execution-ticket-service"]="neural-hive-orchestration"
  ["sla-management-system"]="neural-hive-orchestration"
  ["code-forge"]="neural-hive-orchestration"
  ["self-healing-engine"]="neural-hive-resilience"
  ["mcp-tool-catalog"]="neural-hive-orchestration"
)

echo "=== Phase 2 Resource Audit ==="
for service in "${SERVICES[@]}"; do
  echo "--- $service ---"
  values_path="helm-charts/$service/values.yaml"
  alt_path="services/$service/helm-chart/values.yaml"

  if [[ -f "$alt_path" ]]; then
    values_path="$alt_path"
  fi

  if [[ -f "$values_path" ]]; then
    # Extract resource limits from Helm values
    yq eval '.resources' "$values_path"
  else
    echo "values.yaml not found for $service"
  fi

  namespace="${SERVICE_NAMESPACES[$service]:-neural-hive-orchestration}"

  # Get actual usage from Kubernetes
  kubectl top pods -n "$namespace" -l app.kubernetes.io/name=$service
  
  # Check HPA configuration
  kubectl get hpa -n "$namespace" -l app.kubernetes.io/name=$service
done
