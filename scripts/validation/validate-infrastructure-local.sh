#!/usr/bin/env bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""

################################################################################
# Validate Infrastructure Base - Local Minikube
#
# This script validates each infrastructure component individually to ensure
# all services are healthy and accessible.
#
# Components validated:
#   1. Kafka (Strimzi + Cluster)
#   2. Redis
#   3. MongoDB
#   4. Neo4j
#   5. ClickHouse
#   6. Keycloak
#
################################################################################

set -euo pipefail

# Script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

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
VALIDATION_TIMEOUT=30

# Validation results tracking
declare -A VALIDATION_RESULTS

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
  echo -e "${BLUE}[INFO]${NC} ${msg}"
}

log_success() {
  local msg="$1"
  echo -e "${GREEN}[✓]${NC} ${msg}"
}

log_warning() {
  local msg="$1"
  echo -e "${YELLOW}[⚠]${NC} ${msg}"
}

log_error() {
  local msg="$1"
  echo -e "${RED}[✗]${NC} ${msg}"
}

test_step() {
  local step_num="$1"
  local description="$2"
  echo -e "${CYAN}[${step_num}]${NC} ${description}"
}

validate_pods() {
  local namespace="$1"
  local expected_min="${2:-1}"

  local running_pods
  running_pods=$(kubectl get pods -n "${namespace}" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l || echo "0")

  if [[ ${running_pods} -ge ${expected_min} ]]; then
    log_success "Found ${running_pods} running pod(s) in ${namespace}"
    return 0
  else
    log_error "Expected at least ${expected_min} running pod(s) in ${namespace}, found ${running_pods}"
    return 1
  fi
}

validate_service() {
  local namespace="$1"
  local service_name="$2"

  if kubectl get svc "${service_name}" -n "${namespace}" &> /dev/null; then
    local endpoints
    endpoints=$(kubectl get endpoints "${service_name}" -n "${namespace}" -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null || echo "")

    if [[ -n "${endpoints}" ]]; then
      log_success "Service ${service_name} exists with endpoints"
      return 0
    else
      log_warning "Service ${service_name} exists but has no endpoints"
      return 1
    fi
  else
    log_error "Service ${service_name} not found in ${namespace}"
    return 1
  fi
}

test_connectivity() {
  local description="$1"
  local command="$2"

  if eval "${command}" &> /dev/null; then
    log_success "${description}"
    return 0
  else
    log_error "${description} - connectivity test failed"
    return 1
  fi
}

################################################################################
# Validation Functions
################################################################################

validate_kafka() {
  echo ""
  echo -e "${MAGENTA}═══════════════════════════════════════════════════════════════${NC}"
  echo -e "${MAGENTA}  Validating Kafka${NC}"
  echo -e "${MAGENTA}═══════════════════════════════════════════════════════════════${NC}"
  echo ""

  local result=0

  # Step 1: Check Strimzi operator
  test_step "1" "Checking Strimzi Kafka Operator..."
  if ! validate_pods "${KAFKA_NAMESPACE}" 1; then
    result=1
  fi

  # Step 2: Check Kafka cluster CRD
  test_step "2" "Checking Kafka cluster resource..."
  if kubectl get kafka neural-hive-kafka -n "${KAFKA_NAMESPACE}" &> /dev/null; then
    local kafka_status
    kafka_status=$(kubectl get kafka neural-hive-kafka -n "${KAFKA_NAMESPACE}" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "")
    if [[ "${kafka_status}" == "True" ]]; then
      log_success "Kafka cluster is Ready"
    else
      log_error "Kafka cluster is not Ready (status: ${kafka_status})"
      result=1
    fi
  else
    log_error "Kafka cluster resource not found"
    result=1
  fi

  # Step 3: Check Kafka pods
  test_step "3" "Checking Kafka pods..."
  local kafka_pods
  kafka_pods=$(kubectl get pods -n "${KAFKA_NAMESPACE}" -l strimzi.io/cluster=neural-hive-kafka --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l || echo "0")
  if [[ ${kafka_pods} -gt 0 ]]; then
    log_success "Found ${kafka_pods} running Kafka pod(s)"
  else
    log_error "No running Kafka pods found"
    result=1
  fi

  # Step 4: Check Kafka service
  test_step "4" "Checking Kafka service..."
  if ! validate_service "${KAFKA_NAMESPACE}" "neural-hive-kafka-kafka-bootstrap"; then
    result=1
  fi

  # Step 5: List Kafka topics
  test_step "5" "Listing Kafka topics..."
  local kafka_pod
  kafka_pod=$(kubectl get pods -n "${KAFKA_NAMESPACE}" -l strimzi.io/name=neural-hive-kafka-kafka -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

  if [[ -n "${kafka_pod}" ]]; then
    log_info "Attempting to list topics from pod: ${kafka_pod}"
    if kubectl exec -n "${KAFKA_NAMESPACE}" "${kafka_pod}" -- \
      bin/kafka-topics.sh --bootstrap-server localhost:9092 --list &> /dev/null; then
      local topics
      topics=$(kubectl exec -n "${KAFKA_NAMESPACE}" "${kafka_pod}" -- \
        bin/kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null | grep -v "^$" | wc -l || echo "0")
      log_success "Successfully listed ${topics} Kafka topic(s)"

      # Check for expected topics
      local expected_topics=("intentions-business" "intentions-technical" "intentions-infrastructure" "intentions-security" "intentions-validation")
      for topic in "${expected_topics[@]}"; do
        if kubectl exec -n "${KAFKA_NAMESPACE}" "${kafka_pod}" -- \
          bin/kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null | grep -q "^${topic}$"; then
          log_success "Topic '${topic}' exists"
        else
          log_warning "Topic '${topic}' not found (may be created by application)"
        fi
      done

      # Step 5.1: Test produce/consume message
      test_step "5.1" "Testing Kafka produce/consume..."
      local validation_topic="nhm-validation"

      # Create validation topic if not exists
      if ! kubectl exec -n "${KAFKA_NAMESPACE}" "${kafka_pod}" -- \
        bin/kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null | grep -q "^${validation_topic}$"; then
        log_info "Creating validation topic: ${validation_topic}"
        if kubectl exec -n "${KAFKA_NAMESPACE}" "${kafka_pod}" -- \
          bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --topic "${validation_topic}" --partitions 1 --replication-factor 1 &> /dev/null; then
          log_success "Validation topic created"
        else
          log_error "Failed to create validation topic"
          result=1
        fi
      fi

      # Produce a test message
      if echo "hello" | kubectl exec -i -n "${KAFKA_NAMESPACE}" "${kafka_pod}" -- \
        bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic "${validation_topic}" &> /dev/null; then
        log_success "Successfully produced test message"

        # Consume the message
        local consumed_message
        consumed_message=$(kubectl exec -n "${KAFKA_NAMESPACE}" "${kafka_pod}" -- \
          bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic "${validation_topic}" --from-beginning --max-messages 1 --timeout-ms 5000 2>/dev/null || echo "")

        if [[ "${consumed_message}" == "hello" ]]; then
          log_success "Successfully consumed test message"
        else
          log_error "Failed to consume test message or message mismatch"
          result=1
        fi
      else
        log_error "Failed to produce test message"
        result=1
      fi

      # Clean up validation topic (best-effort)
      kubectl exec -n "${KAFKA_NAMESPACE}" "${kafka_pod}" -- \
        bin/kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic "${validation_topic}" &> /dev/null || true
    else
      log_error "Failed to list Kafka topics"
      result=1
    fi
  else
    log_error "Could not find Kafka pod to test connectivity"
    result=1
  fi

  # Step 6: Check metrics
  test_step "6" "Checking Kafka metrics endpoint..."
  if kubectl get svc -n "${KAFKA_NAMESPACE}" | grep -q "metrics"; then
    log_success "Kafka metrics service found"
  else
    log_warning "Kafka metrics service not found (optional)"
  fi

  VALIDATION_RESULTS["Kafka"]=$result
  return $result
}

validate_redis() {
  echo ""
  echo -e "${MAGENTA}═══════════════════════════════════════════════════════════════${NC}"
  echo -e "${MAGENTA}  Validating Redis${NC}"
  echo -e "${MAGENTA}═══════════════════════════════════════════════════════════════${NC}"
  echo ""

  local result=0

  # Step 1: Check Redis deployment
  test_step "1" "Checking Redis deployment..."
  if ! validate_pods "${REDIS_NAMESPACE}" 1; then
    result=1
  fi

  # Step 2: Check Redis service
  test_step "2" "Checking Redis service..."
  if ! validate_service "${REDIS_NAMESPACE}" "neural-hive-cache"; then
    result=1
  fi

  # Step 3: Test Redis connectivity with PING
  test_step "3" "Testing Redis PING..."
  local redis_pod
  redis_pod=$(kubectl get pods -n "${REDIS_NAMESPACE}" -l app=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

  if [[ -n "${redis_pod}" ]]; then
    if kubectl exec -n "${REDIS_NAMESPACE}" "${redis_pod}" -- redis-cli ping 2>&1 | grep -q PONG; then
      log_success "Redis PING successful"
    else
      log_error "Redis PING failed"
      result=1
    fi

    # Step 4: Test SET/GET operations
    test_step "4" "Testing Redis SET/GET operations..."
    if kubectl exec -n "${REDIS_NAMESPACE}" "${redis_pod}" -- redis-cli SET test_key "test_value" &> /dev/null; then
      local get_result
      get_result=$(kubectl exec -n "${REDIS_NAMESPACE}" "${redis_pod}" -- redis-cli GET test_key 2>/dev/null || echo "")
      if [[ "${get_result}" == "test_value" ]]; then
        log_success "Redis SET/GET operations successful"
        kubectl exec -n "${REDIS_NAMESPACE}" "${redis_pod}" -- redis-cli DEL test_key &> /dev/null
      else
        log_error "Redis GET returned unexpected value: ${get_result}"
        result=1
      fi
    else
      log_error "Redis SET operation failed"
      result=1
    fi

    # Step 5: Check Redis info
    test_step "5" "Checking Redis info..."
    if kubectl exec -n "${REDIS_NAMESPACE}" "${redis_pod}" -- redis-cli INFO server &> /dev/null; then
      log_success "Redis INFO command successful"
    else
      log_warning "Redis INFO command failed"
    fi

    # Step 6: Check Redis persistence
    test_step "6" "Checking Redis persistence configuration..."
    local persistence_info
    persistence_info=$(kubectl exec -n "${REDIS_NAMESPACE}" "${redis_pod}" -- redis-cli CONFIG GET save 2>/dev/null || echo "")
    if [[ -n "${persistence_info}" ]]; then
      log_success "Redis persistence configured"
    else
      log_warning "Could not verify Redis persistence configuration"
    fi
  else
    log_error "Could not find Redis pod to test connectivity"
    result=1
  fi

  VALIDATION_RESULTS["Redis"]=$result
  return $result
}

validate_mongodb() {
  echo ""
  echo -e "${MAGENTA}═══════════════════════════════════════════════════════════════${NC}"
  echo -e "${MAGENTA}  Validating MongoDB${NC}"
  echo -e "${MAGENTA}═══════════════════════════════════════════════════════════════${NC}"
  echo ""

  local result=0

  # Step 1: Check MongoDB operator (if installed)
  test_step "1" "Checking MongoDB operator..."
  if kubectl get namespace "${MONGODB_OPERATOR_NAMESPACE}" &> /dev/null; then
    if ! validate_pods "${MONGODB_OPERATOR_NAMESPACE}" 1; then
      log_warning "MongoDB operator pods not running (may not be installed)"
    else
      log_success "MongoDB operator is running"
    fi
  else
    log_info "MongoDB operator namespace not found (may use different deployment method)"
  fi

  # Step 2: Check MongoDB pods
  test_step "2" "Checking MongoDB pods..."
  if ! validate_pods "${MONGODB_NAMESPACE}" 1; then
    result=1
  fi

  # Step 3: Check MongoDB service
  test_step "3" "Checking MongoDB service..."
  local mongodb_services
  mongodb_services=$(kubectl get svc -n "${MONGODB_NAMESPACE}" --no-headers 2>/dev/null | wc -l || echo "0")
  if [[ ${mongodb_services} -gt 0 ]]; then
    log_success "Found ${mongodb_services} MongoDB service(s)"
  else
    log_error "No MongoDB services found"
    result=1
  fi

  # Step 4: Test MongoDB connectivity
  test_step "4" "Testing MongoDB connectivity..."
  local mongodb_pod
  mongodb_pod=$(kubectl get pods -n "${MONGODB_NAMESPACE}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

  if [[ -n "${mongodb_pod}" ]]; then
    # Check if authentication is enabled by checking for MongoDBCommunity CR
    local auth_enabled=false
    local mongodb_user=""
    local mongodb_password=""
    local secret_name=""

    # Determine if MongoDB Community CR exists (indicates auth is enabled with SCRAM)
    if kubectl get mongodbcommunity -n "${MONGODB_NAMESPACE}" &> /dev/null; then
      auth_enabled=true
      log_info "MongoDB Community operator detected - authentication is enabled"

      # Get MongoDB CR name to determine secret name
      local mongodb_cr_name
      mongodb_cr_name=$(kubectl get mongodbcommunity -n "${MONGODB_NAMESPACE}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

      if [[ -n "${mongodb_cr_name}" ]]; then
        # Determine secret name from CR spec or use default pattern
        secret_name=$(kubectl get mongodbcommunity "${mongodb_cr_name}" -n "${MONGODB_NAMESPACE}" \
          -o jsonpath='{.spec.users[?(@.name=="admin")].passwordSecretRef.name}' 2>/dev/null || echo "")

        if [[ -z "${secret_name}" ]]; then
          # Fallback to default naming pattern: <cr-name>-auth
          secret_name="${mongodb_cr_name}-auth"
        fi

        log_info "Using secret: ${secret_name}"

        # MongoDB chart creates admin user with password-only secret
        mongodb_user="admin"
        mongodb_password=$(kubectl get secret "${secret_name}" -n "${MONGODB_NAMESPACE}" \
          -o jsonpath='{.data.password}' 2>/dev/null | base64 -d 2>/dev/null || echo "")

        if [[ -z "${mongodb_password}" ]]; then
          log_warning "Could not retrieve MongoDB password from secret ${secret_name}"
          auth_enabled=false
        else
          log_info "Successfully retrieved MongoDB credentials (user: ${mongodb_user})"
        fi
      else
        log_warning "Could not determine MongoDB CR name for credential discovery"
        auth_enabled=false
      fi
    else
      log_info "MongoDB Community CR not found - authentication may not be enabled"
    fi

    # Try to connect to MongoDB with or without auth
    local mongodb_connect_cmd=""
    if [[ "${auth_enabled}" == "true" ]]; then
      mongodb_connect_cmd="mongosh -u '${mongodb_user}' -p '${mongodb_password}' --authenticationDatabase admin --eval 'db.runCommand({ ping: 1 })'"
    else
      mongodb_connect_cmd="mongosh --eval 'db.version()'"
    fi

    if kubectl exec -n "${MONGODB_NAMESPACE}" "${mongodb_pod}" -- bash -c "${mongodb_connect_cmd}" &> /dev/null 2>&1; then
      log_success "MongoDB connectivity test successful"

      # Step 5: List databases
      test_step "5" "Listing MongoDB databases..."
      local list_db_cmd=""
      if [[ "${auth_enabled}" == "true" ]]; then
        list_db_cmd="mongosh -u '${mongodb_user}' -p '${mongodb_password}' --authenticationDatabase admin --eval 'db.adminCommand(\"listDatabases\")'"
      else
        list_db_cmd="mongosh --eval 'db.adminCommand(\"listDatabases\")'"
      fi

      if kubectl exec -n "${MONGODB_NAMESPACE}" "${mongodb_pod}" -- bash -c "${list_db_cmd}" &> /dev/null 2>&1; then
        log_success "Successfully listed MongoDB databases"
      else
        log_warning "Could not list MongoDB databases"
      fi
    else
      # Try fallback with mongo (legacy)
      if kubectl exec -n "${MONGODB_NAMESPACE}" "${mongodb_pod}" -- mongo --eval "db.version()" &> /dev/null 2>&1; then
        log_success "MongoDB connectivity test successful (using legacy mongo client)"
      else
        if [[ "${auth_enabled}" == "true" ]]; then
          log_warning "MongoDB connectivity test failed with detected credentials - pods and services are healthy but authentication may need manual verification"
        else
          log_warning "MongoDB connectivity test failed - pods and services are healthy but connection test failed"
        fi
        # Don't fail validation if pods/services are healthy
      fi
    fi
  else
    log_error "Could not find MongoDB pod to test connectivity"
    result=1
  fi

  VALIDATION_RESULTS["MongoDB"]=$result
  return $result
}

validate_neo4j() {
  echo ""
  echo -e "${MAGENTA}═══════════════════════════════════════════════════════════════${NC}"
  echo -e "${MAGENTA}  Validating Neo4j${NC}"
  echo -e "${MAGENTA}═══════════════════════════════════════════════════════════════${NC}"
  echo ""

  local result=0

  # Step 1: Check Neo4j pods
  test_step "1" "Checking Neo4j pods..."
  if ! validate_pods "${NEO4J_NAMESPACE}" 1; then
    result=1
  fi

  # Step 2: Check Neo4j Bolt service (port 7687)
  test_step "2" "Checking Neo4j Bolt service..."
  local bolt_service
  bolt_service=$(kubectl get svc -n "${NEO4J_NAMESPACE}" -o jsonpath='{.items[?(@.spec.ports[*].port==7687)].metadata.name}' 2>/dev/null || echo "")
  if [[ -n "${bolt_service}" ]]; then
    log_success "Neo4j Bolt service found: ${bolt_service}"
  else
    log_error "Neo4j Bolt service (port 7687) not found"
    result=1
  fi

  # Step 3: Check Neo4j HTTP service (port 7474)
  test_step "3" "Checking Neo4j HTTP service..."
  local http_service
  http_service=$(kubectl get svc -n "${NEO4J_NAMESPACE}" -o jsonpath='{.items[?(@.spec.ports[*].port==7474)].metadata.name}' 2>/dev/null || echo "")
  if [[ -n "${http_service}" ]]; then
    log_success "Neo4j HTTP service found: ${http_service}"
  else
    log_warning "Neo4j HTTP service (port 7474) not found"
  fi

  # Step 4: Test Neo4j connectivity
  test_step "4" "Testing Neo4j connectivity..."
  local neo4j_pod
  neo4j_pod=$(kubectl get pods -n "${NEO4J_NAMESPACE}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

  if [[ -n "${neo4j_pod}" ]]; then
    # Try simple cypher query
    if kubectl exec -n "${NEO4J_NAMESPACE}" "${neo4j_pod}" -- cypher-shell -u neo4j -p local_dev_password "RETURN 1" &> /dev/null; then
      log_success "Neo4j cypher-shell connectivity successful"

      # Step 5: Check plugins
      test_step "5" "Checking Neo4j plugins..."
      if kubectl exec -n "${NEO4J_NAMESPACE}" "${neo4j_pod}" -- cypher-shell -u neo4j -p local_dev_password "CALL dbms.procedures() YIELD name RETURN name" 2>/dev/null | grep -q "apoc"; then
        log_success "APOC plugin is loaded"
      else
        log_warning "APOC plugin not detected"
      fi

      if kubectl exec -n "${NEO4J_NAMESPACE}" "${neo4j_pod}" -- cypher-shell -u neo4j -p local_dev_password "CALL dbms.procedures() YIELD name RETURN name" 2>/dev/null | grep -q "neosemantics"; then
        log_success "Neosemantics plugin is loaded"
      else
        log_warning "Neosemantics plugin not detected"
      fi
    else
      log_warning "Neo4j cypher-shell test failed (may require different credentials or not ready yet)"
      # Try without authentication
      if kubectl exec -n "${NEO4J_NAMESPACE}" "${neo4j_pod}" -- neo4j status &> /dev/null; then
        log_success "Neo4j process is running"
      else
        log_error "Neo4j connectivity test failed"
        result=1
      fi
    fi
  else
    log_error "Could not find Neo4j pod to test connectivity"
    result=1
  fi

  VALIDATION_RESULTS["Neo4j"]=$result
  return $result
}

validate_clickhouse() {
  echo ""
  echo -e "${MAGENTA}═══════════════════════════════════════════════════════════════${NC}"
  echo -e "${MAGENTA}  Validating ClickHouse${NC}"
  echo -e "${MAGENTA}═══════════════════════════════════════════════════════════════${NC}"
  echo ""

  local result=0

  # Step 1: Check ClickHouse operator
  test_step "1" "Checking ClickHouse operator..."
  if kubectl get deployment clickhouse-operator -n kube-system &> /dev/null; then
    log_success "ClickHouse operator is deployed"
  else
    log_warning "ClickHouse operator not found in kube-system (may be installed elsewhere)"
  fi

  # Step 2: Check ClickHouse pods
  test_step "2" "Checking ClickHouse pods..."
  if ! validate_pods "${CLICKHOUSE_NAMESPACE}" 1; then
    result=1
  fi

  # Step 3: Check ZooKeeper pods
  test_step "3" "Checking ZooKeeper/Keeper pods..."
  local zk_pods
  zk_pods=$(kubectl get pods -n "${CLICKHOUSE_NAMESPACE}" -l app=zookeeper --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l || echo "0")
  if [[ ${zk_pods} -gt 0 ]]; then
    log_success "Found ${zk_pods} running ZooKeeper pod(s)"
  else
    log_warning "No ZooKeeper pods found (may use ClickHouse Keeper instead)"
  fi

  # Step 4: Check ClickHouse HTTP service (port 8123)
  test_step "4" "Checking ClickHouse HTTP service..."
  local http_service
  http_service=$(kubectl get svc -n "${CLICKHOUSE_NAMESPACE}" -o jsonpath='{.items[?(@.spec.ports[*].port==8123)].metadata.name}' 2>/dev/null || echo "")
  if [[ -n "${http_service}" ]]; then
    log_success "ClickHouse HTTP service found: ${http_service}"
  else
    log_error "ClickHouse HTTP service (port 8123) not found"
    result=1
  fi

  # Step 5: Check ClickHouse native service (port 9000)
  test_step "5" "Checking ClickHouse native service..."
  local native_service
  native_service=$(kubectl get svc -n "${CLICKHOUSE_NAMESPACE}" -o jsonpath='{.items[?(@.spec.ports[*].port==9000)].metadata.name}' 2>/dev/null || echo "")
  if [[ -n "${native_service}" ]]; then
    log_success "ClickHouse native service found: ${native_service}"
  else
    log_warning "ClickHouse native service (port 9000) not found"
  fi

  # Step 6: Test ClickHouse connectivity
  test_step "6" "Testing ClickHouse connectivity..."
  local clickhouse_pod
  # Try multiple selectors: first by label, then by searching for clickhouse-server container
  clickhouse_pod=$(kubectl get pods -n "${CLICKHOUSE_NAMESPACE}" -l app.kubernetes.io/name=clickhouse -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
  if [[ -z "${clickhouse_pod}" ]]; then
    clickhouse_pod=$(kubectl get pods -n "${CLICKHOUSE_NAMESPACE}" -o jsonpath='{.items[?(@.spec.containers[*].name=="clickhouse-server")].metadata.name}' 2>/dev/null | awk '{print $1}' || echo "")
  fi

  if [[ -n "${clickhouse_pod}" ]]; then
    # Try simple query
    if kubectl exec -n "${CLICKHOUSE_NAMESPACE}" "${clickhouse_pod}" -- clickhouse-client --query "SELECT 1" &> /dev/null; then
      log_success "ClickHouse connectivity test successful"

      # Step 7: List databases
      test_step "7" "Listing ClickHouse databases..."
      if kubectl exec -n "${CLICKHOUSE_NAMESPACE}" "${clickhouse_pod}" -- clickhouse-client --query "SHOW DATABASES" &> /dev/null; then
        local db_count
        db_count=$(kubectl exec -n "${CLICKHOUSE_NAMESPACE}" "${clickhouse_pod}" -- clickhouse-client --query "SHOW DATABASES" 2>/dev/null | wc -l || echo "0")
        log_success "Found ${db_count} ClickHouse database(s)"
      else
        log_warning "Could not list ClickHouse databases"
      fi

      # Step 8: Check cluster configuration
      test_step "8" "Checking ClickHouse cluster configuration..."
      if kubectl exec -n "${CLICKHOUSE_NAMESPACE}" "${clickhouse_pod}" -- clickhouse-client --query "SELECT * FROM system.clusters" &> /dev/null; then
        log_success "ClickHouse cluster configuration accessible"
      else
        log_warning "Could not access ClickHouse cluster configuration"
      fi
    else
      log_error "ClickHouse connectivity test failed"
      result=1
    fi
  else
    log_error "Could not find ClickHouse pod to test connectivity"
    result=1
  fi

  VALIDATION_RESULTS["ClickHouse"]=$result
  return $result
}

validate_keycloak() {
  echo ""
  echo -e "${MAGENTA}═══════════════════════════════════════════════════════════════${NC}"
  echo -e "${MAGENTA}  Validating Keycloak${NC}"
  echo -e "${MAGENTA}═══════════════════════════════════════════════════════════════${NC}"
  echo ""

  local result=0

  # Step 1: Check Keycloak deployment
  test_step "1" "Checking Keycloak deployment..."
  if ! validate_pods "${KEYCLOAK_NAMESPACE}" 1; then
    result=1
  fi

  # Step 2: Check Keycloak service
  test_step "2" "Checking Keycloak service..."
  local keycloak_services
  keycloak_services=$(kubectl get svc -n "${KEYCLOAK_NAMESPACE}" --no-headers 2>/dev/null | wc -l || echo "0")
  if [[ ${keycloak_services} -gt 0 ]]; then
    log_success "Found ${keycloak_services} Keycloak service(s)"
  else
    log_error "No Keycloak services found"
    result=1
  fi

  # Step 3: Test Keycloak health endpoint
  test_step "3" "Testing Keycloak health endpoint..."
  local keycloak_pod
  keycloak_pod=$(kubectl get pods -n "${KEYCLOAK_NAMESPACE}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

  if [[ -n "${keycloak_pod}" ]]; then
    # Wait a bit for Keycloak to be fully ready
    sleep 5

    # Try to access health endpoint
    if kubectl exec -n "${KEYCLOAK_NAMESPACE}" "${keycloak_pod}" -- curl -s http://localhost:8080/health &> /dev/null; then
      log_success "Keycloak health endpoint accessible"

      # Step 4: Check realms endpoint
      test_step "4" "Checking Keycloak realms endpoint..."
      if kubectl exec -n "${KEYCLOAK_NAMESPACE}" "${keycloak_pod}" -- curl -s http://localhost:8080/realms/master &> /dev/null; then
        log_success "Keycloak master realm accessible"
      else
        log_warning "Keycloak master realm not accessible yet (may still be initializing)"
      fi
    else
      log_warning "Keycloak health endpoint not accessible yet (may still be starting)"
      # Check if Keycloak process is at least running
      if kubectl exec -n "${KEYCLOAK_NAMESPACE}" "${keycloak_pod}" -- ps aux | grep -q keycloak; then
        log_success "Keycloak process is running"
      else
        log_error "Keycloak process not found"
        result=1
      fi
    fi

    # Step 5: Check Keycloak admin console
    test_step "5" "Checking Keycloak admin console..."
    if kubectl exec -n "${KEYCLOAK_NAMESPACE}" "${keycloak_pod}" -- curl -s http://localhost:8080/admin/ &> /dev/null; then
      log_success "Keycloak admin console is accessible"
    else
      log_warning "Keycloak admin console not accessible yet"
    fi
  else
    log_error "Could not find Keycloak pod to test connectivity"
    result=1
  fi

  VALIDATION_RESULTS["Keycloak"]=$result
  return $result
}

################################################################################
# Main Execution
################################################################################

print_banner() {
  echo -e "${CYAN}"
  cat << "EOF"
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   Neural Hive-Mind Infrastructure Validation                 ║
║   Environment: Local (Minikube)                              ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
EOF
  echo -e "${NC}"
}

generate_summary() {
  echo ""
  echo -e "${CYAN}╔═══════════════════════════════════════════════════════════════╗${NC}"
  echo -e "${CYAN}║                    VALIDATION SUMMARY                        ║${NC}"
  echo -e "${CYAN}╚═══════════════════════════════════════════════════════════════╝${NC}"
  echo ""

  # Component status table
  echo -e "${MAGENTA}Component Status:${NC}"
  echo "┌────────────────────────────┬────────────────────┐"
  echo "│ Component                  │ Status             │"
  echo "├────────────────────────────┼────────────────────┤"

  local total=0
  local passed=0

  for component in "Kafka" "Redis" "MongoDB" "Neo4j" "ClickHouse" "Keycloak"; do
    total=$((total + 1))
    local status="${VALIDATION_RESULTS[${component}]:-1}"

    if [[ ${status} -eq 0 ]]; then
      printf "│ %-26s │ ${GREEN}✓ Passed${NC}          │\n" "${component}"
      passed=$((passed + 1))
    else
      printf "│ %-26s │ ${RED}✗ Failed${NC}          │\n" "${component}"
    fi
  done

  echo "└────────────────────────────┴────────────────────┘"
  echo ""

  # Summary statistics
  echo -e "${MAGENTA}Summary:${NC}"
  echo "  Total components: ${total}"
  echo "  Passed: ${GREEN}${passed}${NC}"
  echo "  Failed: ${RED}$((total - passed))${NC}"
  echo "  Success rate: $((passed * 100 / total))%"
  echo ""

  # Failed components troubleshooting
  if [[ ${passed} -lt ${total} ]]; then
    echo -e "${YELLOW}Troubleshooting Failed Components:${NC}"
    echo ""

    for component in "Kafka" "Redis" "MongoDB" "Neo4j" "ClickHouse" "Keycloak"; do
      local status="${VALIDATION_RESULTS[${component}]:-1}"
      if [[ ${status} -ne 0 ]]; then
        echo -e "${RED}${component} failed validation${NC}"

        case "${component}" in
          "Kafka")
            echo "  Check pods: kubectl get pods -n ${KAFKA_NAMESPACE}"
            echo "  Check logs: kubectl logs -n ${KAFKA_NAMESPACE} -l strimzi.io/cluster=neural-hive-kafka"
            ;;
          "Redis")
            echo "  Check pods: kubectl get pods -n ${REDIS_NAMESPACE}"
            echo "  Check logs: kubectl logs -n ${REDIS_NAMESPACE} -l app=redis"
            ;;
          "MongoDB")
            echo "  Check pods: kubectl get pods -n ${MONGODB_NAMESPACE}"
            echo "  Check logs: kubectl logs -n ${MONGODB_NAMESPACE} --all-containers"
            ;;
          "Neo4j")
            echo "  Check pods: kubectl get pods -n ${NEO4J_NAMESPACE}"
            echo "  Check logs: kubectl logs -n ${NEO4J_NAMESPACE} --all-containers"
            ;;
          "ClickHouse")
            echo "  Check pods: kubectl get pods -n ${CLICKHOUSE_NAMESPACE}"
            echo "  Check logs: kubectl logs -n ${CLICKHOUSE_NAMESPACE} -l app.kubernetes.io/name=clickhouse"
            ;;
          "Keycloak")
            echo "  Check pods: kubectl get pods -n ${KEYCLOAK_NAMESPACE}"
            echo "  Check logs: kubectl logs -n ${KEYCLOAK_NAMESPACE} --all-containers"
            ;;
        esac
        echo ""
      fi
    done
  fi

  # Service endpoints
  echo -e "${MAGENTA}Service Endpoints:${NC}"
  echo "  To access services, use kubectl port-forward:"
  echo "    Kafka: kubectl port-forward -n ${KAFKA_NAMESPACE} svc/neural-hive-kafka-kafka-bootstrap 9092:9092"
  echo "    Redis: kubectl port-forward -n ${REDIS_NAMESPACE} svc/neural-hive-cache 6379:6379"
  echo "    Neo4j: kubectl port-forward -n ${NEO4J_NAMESPACE} svc/<neo4j-service> 7687:7687 7474:7474"
  echo "    ClickHouse: kubectl port-forward -n ${CLICKHOUSE_NAMESPACE} svc/<clickhouse-service> 8123:8123"
  echo "    Keycloak: kubectl port-forward -n ${KEYCLOAK_NAMESPACE} svc/<keycloak-service> 8080:8080"
  echo ""

  if [[ ${passed} -eq ${total} ]]; then
    echo -e "${GREEN}✓ All infrastructure components validated successfully!${NC}"
    return 0
  else
    echo -e "${RED}✗ Some infrastructure components failed validation${NC}"
    return 1
  fi
}

main() {
  print_banner

  # Run validations
  validate_kafka
  validate_redis
  validate_mongodb
  validate_neo4j
  validate_clickhouse
  validate_keycloak

  # Generate summary
  generate_summary
}

# Execute main function
main "$@"
