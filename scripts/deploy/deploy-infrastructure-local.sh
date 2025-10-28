#!/usr/bin/env bash

################################################################################
# Deploy Infrastructure Base - Local Minikube
#
# This script deploys all infrastructure base components for the Neural Hive-Mind
# project on a local Minikube cluster in the correct order with dependency management.
#
# Components deployed:
#   1. Strimzi Kafka Operator + Kafka Cluster
#   2. Redis
#   3. MongoDB
#   4. Neo4j
#   5. ClickHouse
#   6. Keycloak
#
# Prerequisites:
#   - Minikube cluster running with sufficient resources
#   - kubectl configured for Minikube context
#   - Helm 3 installed
#   - Phase 1 bootstrap completed
#
################################################################################

set -euo pipefail

# Script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Log file
LOG_DIR="${PROJECT_ROOT}/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/infrastructure-deployment-$(date +%Y%m%d-%H%M%S).log"

# Environment configuration
ENV="local"
export ENV

# Component namespaces
KAFKA_NAMESPACE="kafka"
REDIS_NAMESPACE="redis-cluster"
MONGODB_NAMESPACE="mongodb-cluster"
MONGODB_OPERATOR_NAMESPACE="mongodb-operator"
NEO4J_NAMESPACE="neo4j-cluster"
CLICKHOUSE_NAMESPACE="clickhouse-cluster"
CLICKHOUSE_OPERATOR_NAMESPACE="clickhouse-operator"
KEYCLOAK_NAMESPACE="keycloak"

# Timeout values (seconds)
TIMEOUT_OPERATOR=300
TIMEOUT_SERVICE=600
TIMEOUT_VALIDATION=120

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

################################################################################
# Helper Functions
################################################################################

log_info() {
  local msg="$1"
  echo -e "${BLUE}[INFO]${NC} ${msg}" | tee -a "${LOG_FILE}"
}

log_success() {
  local msg="$1"
  echo -e "${GREEN}[SUCCESS]${NC} ${msg}" | tee -a "${LOG_FILE}"
}

log_warning() {
  local msg="$1"
  echo -e "${YELLOW}[WARNING]${NC} ${msg}" | tee -a "${LOG_FILE}"
}

log_error() {
  local msg="$1"
  echo -e "${RED}[ERROR]${NC} ${msg}" | tee -a "${LOG_FILE}"
}

log_section() {
  local msg="$1"
  echo "" | tee -a "${LOG_FILE}"
  echo -e "${MAGENTA}═══════════════════════════════════════════════════════════════${NC}" | tee -a "${LOG_FILE}"
  echo -e "${MAGENTA}  ${msg}${NC}" | tee -a "${LOG_FILE}"
  echo -e "${MAGENTA}═══════════════════════════════════════════════════════════════${NC}" | tee -a "${LOG_FILE}"
  echo "" | tee -a "${LOG_FILE}"
}

wait_for_pods() {
  local namespace="$1"
  local timeout="${2:-${TIMEOUT_SERVICE}}"
  local label="${3:-}"

  log_info "Waiting for pods in namespace ${namespace} to be ready (timeout: ${timeout}s)..."

  local wait_cmd="kubectl wait --for=condition=ready pod --all -n ${namespace} --timeout=${timeout}s"
  if [[ -n "${label}" ]]; then
    wait_cmd="kubectl wait --for=condition=ready pod -l ${label} -n ${namespace} --timeout=${timeout}s"
  fi

  if eval "${wait_cmd}" >> "${LOG_FILE}" 2>&1; then
    log_success "Pods in ${namespace} are ready"
    return 0
  else
    log_error "Pods in ${namespace} failed to become ready within ${timeout}s"
    kubectl get pods -n "${namespace}" | tee -a "${LOG_FILE}"
    return 1
  fi
}

wait_for_condition() {
  local description="$1"
  local check_command="$2"
  local timeout="${3:-${TIMEOUT_VALIDATION}}"
  local interval=5

  log_info "Waiting for: ${description} (timeout: ${timeout}s)..."

  local elapsed=0
  while [[ ${elapsed} -lt ${timeout} ]]; do
    if eval "${check_command}" >> "${LOG_FILE}" 2>&1; then
      log_success "${description} - condition met"
      return 0
    fi
    sleep ${interval}
    elapsed=$((elapsed + interval))
    echo -n "." | tee -a "${LOG_FILE}"
  done

  echo "" | tee -a "${LOG_FILE}"
  log_error "${description} - timeout after ${timeout}s"
  return 1
}

check_helm_repo() {
  local repo_name="$1"
  local repo_url="$2"

  if helm repo list | grep -q "^${repo_name}"; then
    log_info "Helm repo ${repo_name} already exists"
  else
    log_info "Adding Helm repo: ${repo_name}"
    helm repo add "${repo_name}" "${repo_url}" >> "${LOG_FILE}" 2>&1
  fi

  log_info "Updating Helm repos..."
  helm repo update >> "${LOG_FILE}" 2>&1
}

validate_component() {
  local component="$1"
  local namespace="$2"

  log_info "Validating ${component} deployment..."

  # Check pods
  local pod_count
  pod_count=$(kubectl get pods -n "${namespace}" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)

  if [[ ${pod_count} -gt 0 ]]; then
    log_success "${component}: ${pod_count} pod(s) running"
  else
    log_error "${component}: No running pods found"
    return 1
  fi

  # Check services
  local svc_count
  svc_count=$(kubectl get svc -n "${namespace}" --no-headers 2>/dev/null | wc -l)

  if [[ ${svc_count} -gt 0 ]]; then
    log_success "${component}: ${svc_count} service(s) exist"
  else
    log_warning "${component}: No services found"
  fi

  return 0
}

################################################################################
# Prerequisite Checks
################################################################################

check_prerequisites() {
  log_section "Checking Prerequisites"

  # Check if Minikube is running
  log_info "Checking Minikube status..."
  if ! minikube status >> "${LOG_FILE}" 2>&1; then
    log_error "Minikube is not running. Please start Minikube first."
    exit 1
  fi
  log_success "Minikube is running"

  # Check kubectl context
  log_info "Checking kubectl context..."
  local current_context
  current_context=$(kubectl config current-context)
  if [[ "${current_context}" != "minikube" ]]; then
    log_error "kubectl context is not set to minikube (current: ${current_context})"
    exit 1
  fi
  log_success "kubectl context is set to minikube"

  # Check Helm installation
  log_info "Checking Helm installation..."
  if ! command -v helm &> /dev/null; then
    log_error "Helm is not installed. Please install Helm 3."
    exit 1
  fi
  local helm_version
  helm_version=$(helm version --short)
  log_success "Helm is installed: ${helm_version}"

  # Check cluster resources
  log_info "Checking cluster nodes..."
  kubectl get nodes | tee -a "${LOG_FILE}"

  # Check if bootstrap namespaces exist (Phase 1)
  log_info "Checking bootstrap namespaces from Phase 1..."
  local bootstrap_namespaces=("${KAFKA_NAMESPACE}" "${REDIS_NAMESPACE}" "${MONGODB_NAMESPACE}" "${NEO4J_NAMESPACE}" "${CLICKHOUSE_NAMESPACE}" "${KEYCLOAK_NAMESPACE}")

  for ns in "${bootstrap_namespaces[@]}"; do
    if ! kubectl get namespace "${ns}" &> /dev/null; then
      log_warning "Namespace ${ns} does not exist - will be created during deployment"
    else
      log_success "Namespace ${ns} exists"
    fi
  done

  log_success "All prerequisite checks passed"
}

################################################################################
# Component Deployment Functions
################################################################################

deploy_strimzi_operator() {
  log_section "Deploying Strimzi Kafka Operator"

  # Create namespace if not exists
  kubectl create namespace "${KAFKA_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f - >> "${LOG_FILE}" 2>&1

  # Add Strimzi Helm repository
  check_helm_repo "strimzi" "https://strimzi.io/charts/"

  # Install Strimzi operator
  log_info "Installing Strimzi Kafka operator..."
  if helm list -n "${KAFKA_NAMESPACE}" | grep -q "strimzi-kafka-operator"; then
    log_info "Strimzi operator already installed, upgrading..."
    helm upgrade strimzi-kafka-operator strimzi/strimzi-kafka-operator \
      --namespace "${KAFKA_NAMESPACE}" \
      --set "watchNamespaces={${KAFKA_NAMESPACE}}" \
      --wait \
      --timeout 10m >> "${LOG_FILE}" 2>&1
  else
    helm install strimzi-kafka-operator strimzi/strimzi-kafka-operator \
      --namespace "${KAFKA_NAMESPACE}" \
      --set "watchNamespaces={${KAFKA_NAMESPACE}}" \
      --create-namespace \
      --wait \
      --timeout 10m >> "${LOG_FILE}" 2>&1
  fi

  # Wait for operator pods
  wait_for_pods "${KAFKA_NAMESPACE}" "${TIMEOUT_OPERATOR}" "name=strimzi-cluster-operator"

  # Validate CRDs are installed
  log_info "Validating Strimzi CRDs..."
  local required_crds=("kafkas.kafka.strimzi.io" "kafkatopics.kafka.strimzi.io" "kafkausers.kafka.strimzi.io")
  for crd in "${required_crds[@]}"; do
    if kubectl get crd "${crd}" &> /dev/null; then
      log_success "CRD ${crd} is installed"
    else
      log_error "CRD ${crd} is not installed"
      return 1
    fi
  done

  validate_component "Strimzi Operator" "${KAFKA_NAMESPACE}"
  log_success "Strimzi Kafka Operator deployed successfully"
}

deploy_kafka_cluster() {
  log_section "Deploying Kafka Cluster"

  # Apply Kafka cluster manifest
  local kafka_manifest="${PROJECT_ROOT}/k8s/kafka-local.yaml"
  if [[ ! -f "${kafka_manifest}" ]]; then
    log_error "Kafka manifest not found: ${kafka_manifest}"
    return 1
  fi

  log_info "Applying Kafka cluster manifest..."
  kubectl apply -f "${kafka_manifest}" >> "${LOG_FILE}" 2>&1

  # Wait for Kafka cluster to be ready
  log_info "Waiting for Kafka cluster to be ready (this may take several minutes)..."
  wait_for_condition "Kafka cluster ready" \
    "kubectl get kafka neural-hive-kafka -n ${KAFKA_NAMESPACE} -o jsonpath='{.status.conditions[?(@.type==\"Ready\")].status}' | grep -q True" \
    600

  # Wait for all Kafka-related pods
  wait_for_pods "${KAFKA_NAMESPACE}" "${TIMEOUT_SERVICE}"

  # Validate Kafka topics
  log_info "Validating Kafka topics..."
  sleep 10  # Give time for topics to be created

  local kafka_pod
  kafka_pod=$(kubectl get pods -n "${KAFKA_NAMESPACE}" -l strimzi.io/name=neural-hive-kafka-kafka -o jsonpath='{.items[0].metadata.name}')

  if [[ -n "${kafka_pod}" ]]; then
    log_info "Listing Kafka topics..."
    kubectl exec -n "${KAFKA_NAMESPACE}" "${kafka_pod}" -- \
      bin/kafka-topics.sh --bootstrap-server localhost:9092 --list | tee -a "${LOG_FILE}"

    # Check for expected topics
    local expected_topics=("intentions-business" "intentions-technical" "intentions-infrastructure" "intentions-security" "intentions-validation")
    for topic in "${expected_topics[@]}"; do
      if kubectl exec -n "${KAFKA_NAMESPACE}" "${kafka_pod}" -- \
        bin/kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null | grep -q "${topic}"; then
        log_success "Topic ${topic} exists"
      else
        log_warning "Topic ${topic} not found (may be created by application)"
      fi
    done
  fi

  validate_component "Kafka Cluster" "${KAFKA_NAMESPACE}"
  log_success "Kafka Cluster deployed successfully"
}

deploy_redis() {
  log_section "Deploying Redis"

  # Create namespace if not exists
  kubectl create namespace "${REDIS_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f - >> "${LOG_FILE}" 2>&1

  # Apply Redis manifest
  local redis_manifest="${PROJECT_ROOT}/k8s/redis-local.yaml"
  if [[ ! -f "${redis_manifest}" ]]; then
    log_error "Redis manifest not found: ${redis_manifest}"
    return 1
  fi

  log_info "Applying Redis manifest..."
  kubectl apply -f "${redis_manifest}" >> "${LOG_FILE}" 2>&1

  # Wait for Redis deployment
  wait_for_pods "${REDIS_NAMESPACE}" "${TIMEOUT_SERVICE}"

  # Test Redis connectivity
  log_info "Testing Redis connectivity..."
  local redis_pod
  redis_pod=$(kubectl get pods -n "${REDIS_NAMESPACE}" -l app=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

  if [[ -n "${redis_pod}" ]]; then
    if kubectl exec -n "${REDIS_NAMESPACE}" "${redis_pod}" -- redis-cli ping 2>&1 | grep -q PONG; then
      log_success "Redis is responding to ping"
    else
      log_warning "Redis ping test failed"
    fi
  fi

  validate_component "Redis" "${REDIS_NAMESPACE}"
  log_success "Redis deployed successfully"
}

deploy_mongodb() {
  log_section "Deploying MongoDB"

  # Create namespaces
  kubectl create namespace "${MONGODB_OPERATOR_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f - >> "${LOG_FILE}" 2>&1
  kubectl create namespace "${MONGODB_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f - >> "${LOG_FILE}" 2>&1

  # Check if MongoDB Community Operator is needed
  log_info "Checking for MongoDB Community Operator..."
  if ! kubectl get crd mongodbcommunity.mongodbcommunity.mongodb.com &> /dev/null; then
    log_info "Installing MongoDB Community Operator..."
    kubectl apply -f https://raw.githubusercontent.com/mongodb/mongodb-kubernetes-operator/master/config/crd/bases/mongodbcommunity.mongodbcommunity.mongodb.com_mongodbcommunity.yaml >> "${LOG_FILE}" 2>&1
    kubectl apply -f https://raw.githubusercontent.com/mongodb/mongodb-kubernetes-operator/master/config/rbac/role.yaml -n "${MONGODB_OPERATOR_NAMESPACE}" >> "${LOG_FILE}" 2>&1
    kubectl apply -f https://raw.githubusercontent.com/mongodb/mongodb-kubernetes-operator/master/config/rbac/role_binding.yaml -n "${MONGODB_OPERATOR_NAMESPACE}" >> "${LOG_FILE}" 2>&1
    kubectl apply -f https://raw.githubusercontent.com/mongodb/mongodb-kubernetes-operator/master/config/rbac/service_account.yaml -n "${MONGODB_OPERATOR_NAMESPACE}" >> "${LOG_FILE}" 2>&1
    kubectl apply -f https://raw.githubusercontent.com/mongodb/mongodb-kubernetes-operator/master/config/manager/manager.yaml -n "${MONGODB_OPERATOR_NAMESPACE}" >> "${LOG_FILE}" 2>&1

    wait_for_pods "${MONGODB_OPERATOR_NAMESPACE}" "${TIMEOUT_OPERATOR}"
  else
    log_info "MongoDB Community Operator already installed"
  fi

  # Install MongoDB using Helm
  local values_file="${PROJECT_ROOT}/helm-charts/mongodb/values-local.yaml"
  if [[ ! -f "${values_file}" ]]; then
    log_error "MongoDB values file not found: ${values_file}"
    return 1
  fi

  # Update Helm dependencies for MongoDB chart
  log_info "Updating Helm dependencies for MongoDB chart..."
  helm dependency update "${PROJECT_ROOT}/helm-charts/mongodb" >> "${LOG_FILE}" 2>&1 || log_warning "Failed to update MongoDB chart dependencies (may not be needed)"

  log_info "Installing MongoDB with Helm..."
  if helm list -n "${MONGODB_NAMESPACE}" | grep -q "neural-hive-mongodb"; then
    log_info "MongoDB already installed, upgrading..."
    helm upgrade neural-hive-mongodb "${PROJECT_ROOT}/helm-charts/mongodb" \
      --namespace "${MONGODB_NAMESPACE}" \
      --values "${values_file}" \
      --wait \
      --timeout 10m >> "${LOG_FILE}" 2>&1
  else
    helm install neural-hive-mongodb "${PROJECT_ROOT}/helm-charts/mongodb" \
      --namespace "${MONGODB_NAMESPACE}" \
      --values "${values_file}" \
      --create-namespace \
      --wait \
      --timeout 10m >> "${LOG_FILE}" 2>&1
  fi

  # Wait for MongoDB pods
  wait_for_pods "${MONGODB_NAMESPACE}" "${TIMEOUT_SERVICE}"

  validate_component "MongoDB" "${MONGODB_NAMESPACE}"
  log_success "MongoDB deployed successfully"
}

deploy_neo4j() {
  log_section "Deploying Neo4j"

  # Create namespace if not exists
  kubectl create namespace "${NEO4J_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f - >> "${LOG_FILE}" 2>&1

  # Add Neo4j Helm repository
  check_helm_repo "neo4j" "https://helm.neo4j.com/neo4j"

  # Install Neo4j using Helm
  local values_file="${PROJECT_ROOT}/helm-charts/neo4j/values-local.yaml"
  if [[ ! -f "${values_file}" ]]; then
    log_error "Neo4j values file not found: ${values_file}"
    return 1
  fi

  # Update Helm dependencies for Neo4j chart
  log_info "Updating Helm dependencies for Neo4j chart..."
  helm dependency update "${PROJECT_ROOT}/helm-charts/neo4j" >> "${LOG_FILE}" 2>&1 || log_warning "Failed to update Neo4j chart dependencies (may not be needed)"

  log_info "Installing Neo4j with Helm..."
  if helm list -n "${NEO4J_NAMESPACE}" | grep -q "neural-hive-neo4j"; then
    log_info "Neo4j already installed, upgrading..."
    helm upgrade neural-hive-neo4j "${PROJECT_ROOT}/helm-charts/neo4j" \
      --namespace "${NEO4J_NAMESPACE}" \
      --values "${values_file}" \
      --wait \
      --timeout 10m >> "${LOG_FILE}" 2>&1
  else
    helm install neural-hive-neo4j "${PROJECT_ROOT}/helm-charts/neo4j" \
      --namespace "${NEO4J_NAMESPACE}" \
      --values "${values_file}" \
      --create-namespace \
      --wait \
      --timeout 10m >> "${LOG_FILE}" 2>&1
  fi

  # Wait for Neo4j pods
  wait_for_pods "${NEO4J_NAMESPACE}" "${TIMEOUT_SERVICE}"

  validate_component "Neo4j" "${NEO4J_NAMESPACE}"
  log_success "Neo4j deployed successfully"
}

deploy_clickhouse() {
  log_section "Deploying ClickHouse"

  # Create namespace for ClickHouse cluster
  # Note: ClickHouse Operator is installed into kube-system namespace by the Altinity install bundle
  kubectl create namespace "${CLICKHOUSE_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f - >> "${LOG_FILE}" 2>&1

  # Check if ClickHouse Operator is needed
  log_info "Checking for ClickHouse Operator..."
  if ! kubectl get crd clickhouseinstallations.clickhouse.altinity.com &> /dev/null; then
    log_info "Installing ClickHouse Operator into kube-system namespace..."
    kubectl apply -f https://raw.githubusercontent.com/Altinity/clickhouse-operator/master/deploy/operator/clickhouse-operator-install-bundle.yaml >> "${LOG_FILE}" 2>&1

    # Wait for operator
    wait_for_condition "ClickHouse Operator ready" \
      "kubectl get deployment clickhouse-operator -n kube-system -o jsonpath='{.status.readyReplicas}' | grep -q 1" \
      "${TIMEOUT_OPERATOR}"
  else
    log_info "ClickHouse Operator already installed in kube-system"
  fi

  # Install ClickHouse using Helm
  local values_file="${PROJECT_ROOT}/helm-charts/clickhouse/values-local.yaml"
  if [[ ! -f "${values_file}" ]]; then
    log_error "ClickHouse values file not found: ${values_file}"
    return 1
  fi

  # Update Helm dependencies for ClickHouse chart
  log_info "Updating Helm dependencies for ClickHouse chart..."
  helm dependency update "${PROJECT_ROOT}/helm-charts/clickhouse" >> "${LOG_FILE}" 2>&1 || log_warning "Failed to update ClickHouse chart dependencies (may not be needed)"

  log_info "Installing ClickHouse with Helm..."
  if helm list -n "${CLICKHOUSE_NAMESPACE}" | grep -q "neural-hive-clickhouse"; then
    log_info "ClickHouse already installed, upgrading..."
    helm upgrade neural-hive-clickhouse "${PROJECT_ROOT}/helm-charts/clickhouse" \
      --namespace "${CLICKHOUSE_NAMESPACE}" \
      --values "${values_file}" \
      --wait \
      --timeout 10m >> "${LOG_FILE}" 2>&1
  else
    helm install neural-hive-clickhouse "${PROJECT_ROOT}/helm-charts/clickhouse" \
      --namespace "${CLICKHOUSE_NAMESPACE}" \
      --values "${values_file}" \
      --create-namespace \
      --wait \
      --timeout 10m >> "${LOG_FILE}" 2>&1
  fi

  # Wait for ClickHouse pods
  wait_for_pods "${CLICKHOUSE_NAMESPACE}" "${TIMEOUT_SERVICE}"

  validate_component "ClickHouse" "${CLICKHOUSE_NAMESPACE}"
  log_success "ClickHouse deployed successfully"
}

deploy_keycloak() {
  log_section "Deploying Keycloak"

  # Create namespace if not exists
  kubectl create namespace "${KEYCLOAK_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f - >> "${LOG_FILE}" 2>&1

  # Apply Keycloak manifest
  local keycloak_manifest="${PROJECT_ROOT}/k8s/keycloak-local.yaml"
  if [[ ! -f "${keycloak_manifest}" ]]; then
    log_error "Keycloak manifest not found: ${keycloak_manifest}"
    return 1
  fi

  log_info "Applying Keycloak manifest..."
  kubectl apply -f "${keycloak_manifest}" >> "${LOG_FILE}" 2>&1

  # Wait for Keycloak deployment with proper readiness check
  log_info "Waiting for Keycloak pods to be ready (this may take up to 5 minutes)..."
  if ! kubectl wait --for=condition=ready pod -l app=keycloak -n "${KEYCLOAK_NAMESPACE}" --timeout=300s >> "${LOG_FILE}" 2>&1; then
    log_warning "Keycloak pod readiness timeout, checking pod status..."
    kubectl get pods -n "${KEYCLOAK_NAMESPACE}" | tee -a "${LOG_FILE}"
  fi

  validate_component "Keycloak" "${KEYCLOAK_NAMESPACE}"
  log_success "Keycloak deployed successfully"
}

################################################################################
# Main Execution
################################################################################

print_banner() {
  echo -e "${CYAN}"
  cat << "EOF"
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   Neural Hive-Mind Infrastructure Deployment                 ║
║   Environment: Local (Minikube)                              ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
EOF
  echo -e "${NC}"
  echo "Deployment log: ${LOG_FILE}"
  echo ""
}

generate_summary() {
  log_section "Deployment Summary"

  echo "" | tee -a "${LOG_FILE}"
  echo -e "${CYAN}╔═══════════════════════════════════════════════════════════════╗${NC}" | tee -a "${LOG_FILE}"
  echo -e "${CYAN}║                    DEPLOYMENT COMPLETE                       ║${NC}" | tee -a "${LOG_FILE}"
  echo -e "${CYAN}╔═══════════════════════════════════════════════════════════════╗${NC}" | tee -a "${LOG_FILE}"
  echo "" | tee -a "${LOG_FILE}"

  # Component status
  echo -e "${MAGENTA}Component Status:${NC}" | tee -a "${LOG_FILE}"
  echo "┌────────────────────────────┬────────────┬────────────────────┐" | tee -a "${LOG_FILE}"
  echo "│ Component                  │ Namespace  │ Status             │" | tee -a "${LOG_FILE}"
  echo "├────────────────────────────┼────────────┼────────────────────┤" | tee -a "${LOG_FILE}"

  local components=(
    "Strimzi Operator:${KAFKA_NAMESPACE}"
    "Kafka Cluster:${KAFKA_NAMESPACE}"
    "Redis:${REDIS_NAMESPACE}"
    "MongoDB:${MONGODB_NAMESPACE}"
    "Neo4j:${NEO4J_NAMESPACE}"
    "ClickHouse:${CLICKHOUSE_NAMESPACE}"
    "Keycloak:${KEYCLOAK_NAMESPACE}"
  )

  for comp in "${components[@]}"; do
    local name="${comp%:*}"
    local ns="${comp#*:}"
    local pod_count
    pod_count=$(kubectl get pods -n "${ns}" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l || echo "0")

    if [[ ${pod_count} -gt 0 ]]; then
      printf "│ %-26s │ %-10s │ ${GREEN}✓ Running (${pod_count})${NC}     │\n" "${name}" "${ns}" | tee -a "${LOG_FILE}"
    else
      printf "│ %-26s │ %-10s │ ${RED}✗ Not Running${NC}      │\n" "${name}" "${ns}" | tee -a "${LOG_FILE}"
    fi
  done

  echo "└────────────────────────────┴────────────┴────────────────────┘" | tee -a "${LOG_FILE}"
  echo "" | tee -a "${LOG_FILE}"

  # Service endpoints
  echo -e "${MAGENTA}Service Access:${NC}" | tee -a "${LOG_FILE}"
  echo "  Kafka Bootstrap: neural-hive-kafka-kafka-bootstrap.${KAFKA_NAMESPACE}.svc.cluster.local:9092" | tee -a "${LOG_FILE}"
  echo "  Redis: neural-hive-cache.${REDIS_NAMESPACE}.svc.cluster.local:6379" | tee -a "${LOG_FILE}"

  # MongoDB - dynamically discover service
  local mongodb_svc
  mongodb_svc=$(kubectl get svc -n "${MONGODB_NAMESPACE}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
  if [[ -n "${mongodb_svc}" ]]; then
    echo "  MongoDB: ${mongodb_svc}.${MONGODB_NAMESPACE}.svc.cluster.local:27017" | tee -a "${LOG_FILE}"
  else
    echo "  MongoDB: Service not found" | tee -a "${LOG_FILE}"
  fi

  # Neo4j - dynamically discover bolt and http services
  local neo4j_bolt_svc
  local neo4j_http_svc
  neo4j_bolt_svc=$(kubectl get svc -n "${NEO4J_NAMESPACE}" -o jsonpath='{.items[?(@.spec.ports[*].port==7687)].metadata.name}' 2>/dev/null || echo "")
  neo4j_http_svc=$(kubectl get svc -n "${NEO4J_NAMESPACE}" -o jsonpath='{.items[?(@.spec.ports[*].port==7474)].metadata.name}' 2>/dev/null || echo "")

  if [[ -n "${neo4j_bolt_svc}" ]]; then
    echo "  Neo4j Bolt: ${neo4j_bolt_svc}.${NEO4J_NAMESPACE}.svc.cluster.local:7687" | tee -a "${LOG_FILE}"
  else
    echo "  Neo4j Bolt: Service not found (port 7687)" | tee -a "${LOG_FILE}"
  fi

  if [[ -n "${neo4j_http_svc}" ]]; then
    echo "  Neo4j HTTP: ${neo4j_http_svc}.${NEO4J_NAMESPACE}.svc.cluster.local:7474" | tee -a "${LOG_FILE}"
  else
    echo "  Neo4j HTTP: Service not found (port 7474)" | tee -a "${LOG_FILE}"
  fi

  # ClickHouse - dynamically discover http and native services
  local clickhouse_http_svc
  local clickhouse_native_svc
  clickhouse_http_svc=$(kubectl get svc -n "${CLICKHOUSE_NAMESPACE}" -o jsonpath='{.items[?(@.spec.ports[*].port==8123)].metadata.name}' 2>/dev/null || echo "")
  clickhouse_native_svc=$(kubectl get svc -n "${CLICKHOUSE_NAMESPACE}" -o jsonpath='{.items[?(@.spec.ports[*].port==9000)].metadata.name}' 2>/dev/null || echo "")

  if [[ -n "${clickhouse_http_svc}" ]]; then
    echo "  ClickHouse HTTP: ${clickhouse_http_svc}.${CLICKHOUSE_NAMESPACE}.svc.cluster.local:8123" | tee -a "${LOG_FILE}"
  else
    echo "  ClickHouse HTTP: Service not found (port 8123)" | tee -a "${LOG_FILE}"
  fi

  if [[ -n "${clickhouse_native_svc}" ]]; then
    echo "  ClickHouse Native: ${clickhouse_native_svc}.${CLICKHOUSE_NAMESPACE}.svc.cluster.local:9000" | tee -a "${LOG_FILE}"
  else
    echo "  ClickHouse Native: Service not found (port 9000)" | tee -a "${LOG_FILE}"
  fi

  # Keycloak - dynamically discover service
  local keycloak_svc
  keycloak_svc=$(kubectl get svc -n "${KEYCLOAK_NAMESPACE}" -o jsonpath='{.items[?(@.spec.ports[*].port==8080)].metadata.name}' 2>/dev/null || echo "")
  if [[ -n "${keycloak_svc}" ]]; then
    echo "  Keycloak: ${keycloak_svc}.${KEYCLOAK_NAMESPACE}.svc.cluster.local:8080" | tee -a "${LOG_FILE}"
  else
    echo "  Keycloak: Service not found (port 8080)" | tee -a "${LOG_FILE}"
  fi

  echo "" | tee -a "${LOG_FILE}"

  # Next steps
  echo -e "${MAGENTA}Next Steps:${NC}" | tee -a "${LOG_FILE}"
  echo "  1. Run validation: ./scripts/validation/validate-infrastructure-local.sh" | tee -a "${LOG_FILE}"
  echo "  2. Review logs: ${LOG_FILE}" | tee -a "${LOG_FILE}"
  echo "  3. Access services using kubectl port-forward" | tee -a "${LOG_FILE}"
  echo "  4. Proceed to Phase 3: Gateway deployment" | tee -a "${LOG_FILE}"
  echo "" | tee -a "${LOG_FILE}"

  log_success "Infrastructure deployment completed successfully!"
}

cleanup_on_error() {
  log_error "Deployment failed. Cleaning up..."
  log_error "Check logs for details: ${LOG_FILE}"
  echo ""
  echo "To troubleshoot, check pod status with:"
  echo "  kubectl get pods --all-namespaces"
  echo ""
  echo "To view logs for a specific pod:"
  echo "  kubectl logs <pod-name> -n <namespace>"
  echo ""
  echo "To retry deployment, run:"
  echo "  ./scripts/deploy/deploy-infrastructure-local.sh"
}

main() {
  print_banner

  # Set up error handler
  trap cleanup_on_error ERR

  # Run deployment steps
  check_prerequisites

  deploy_strimzi_operator
  deploy_kafka_cluster
  deploy_redis
  deploy_mongodb
  deploy_neo4j
  deploy_clickhouse
  deploy_keycloak

  generate_summary
}

# Execute main function
main "$@"
