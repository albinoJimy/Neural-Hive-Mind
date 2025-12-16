#!/usr/bin/env bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
#
# validate-phase2-services.sh - Comprehensive Phase 2 Services Validation
#
# This script validates all 13 Phase 2 services across 8 validation phases:
# 1. Kubernetes Pods Status
# 2. HTTP Endpoints (health, ready, metrics)
# 3. Prometheus Metrics
# 4. Database Connectivity (MongoDB, PostgreSQL, Redis, Neo4j)
# 5. gRPC Communication
# 6. Kafka Consumers
# 7. Structured Logs
# 8. Consolidated Report
#
# Usage: ./validate-phase2-services.sh [--quick|--full|--json]
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPORT_DIR="${PROJECT_ROOT}/reports"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_FILE="${REPORT_DIR}/phase2-validation-report-${TIMESTAMP}.json"

# Configurable namespace and label (via environment variables)
SERVICE_NAMESPACE="${SERVICE_NAMESPACE:-neural-hive}"
KAFKA_NAMESPACE="${KAFKA_NAMESPACE:-kafka}"
SERVICE_LABEL_KEY="${SERVICE_LABEL_KEY:-app}"

# Namespaces for Phase 2 services (uses configurable default)
declare -A SERVICE_NAMESPACES=(
    ["orchestrator-dynamic"]="$SERVICE_NAMESPACE"
    ["queen-agent"]="$SERVICE_NAMESPACE"
    ["worker-agents"]="$SERVICE_NAMESPACE"
    ["code-forge"]="$SERVICE_NAMESPACE"
    ["service-registry"]="$SERVICE_NAMESPACE"
    ["execution-ticket-service"]="$SERVICE_NAMESPACE"
    ["scout-agents"]="$SERVICE_NAMESPACE"
    ["analyst-agents"]="$SERVICE_NAMESPACE"
    ["optimizer-agents"]="$SERVICE_NAMESPACE"
    ["guard-agents"]="$SERVICE_NAMESPACE"
    ["sla-management-system"]="$SERVICE_NAMESPACE"
    ["mcp-tool-catalog"]="$SERVICE_NAMESPACE"
    ["self-healing-engine"]="$SERVICE_NAMESPACE"
)

# Service ports
declare -A SERVICE_PORTS=(
    ["orchestrator-dynamic"]="8000"
    ["queen-agent"]="8000"
    ["worker-agents"]="8000"
    ["code-forge"]="8000"
    ["service-registry"]="8000"
    ["execution-ticket-service"]="8000"
    ["scout-agents"]="8000"
    ["analyst-agents"]="8000"
    ["optimizer-agents"]="8000"
    ["guard-agents"]="8000"
    ["sla-management-system"]="8000"
    ["mcp-tool-catalog"]="8000"
    ["self-healing-engine"]="8000"
)

# gRPC services and ports
declare -A GRPC_SERVICES=(
    ["queen-agent"]="50051"
    ["service-registry"]="50051"
    ["optimizer-agents"]="50051"
)

# Services with database dependencies
declare -A MONGODB_SERVICES=(
    ["orchestrator-dynamic"]="orchestration_ledger"
    ["queen-agent"]="strategic_decisions"
    ["analyst-agents"]="analyst_insights"
    ["code-forge"]="code_forge_db"
    ["guard-agents"]="guard_audit"
    ["optimizer-agents"]="optimizer_db"
    ["mcp-tool-catalog"]="mcp_catalog"
    ["execution-ticket-service"]="execution_tickets"
)

declare -A POSTGRESQL_SERVICES=(
    ["execution-ticket-service"]="tickets"
    ["sla-management-system"]="sla_management"
    ["code-forge"]="code_forge"
)

declare -A REDIS_SERVICES=(
    ["queen-agent"]="pheromone"
    ["orchestrator-dynamic"]="cache"
    ["optimizer-agents"]="forecast_cache"
    ["sla-management-system"]="sla_cache"
    ["service-registry"]="service_cache"
)

declare -A NEO4J_SERVICES=(
    ["queen-agent"]="intent_graph"
    ["analyst-agents"]="analysis_graph"
)

# Kafka consumer services
declare -A KAFKA_CONSUMERS=(
    ["orchestrator-dynamic"]="cognitive-plans-consolidated"
    ["queen-agent"]="consensus-decisions,system-telemetry,orchestration-incidents"
    ["worker-agents"]="execution-tickets"
    ["code-forge"]="code-generation-tickets"
    ["guard-agents"]="security-events"
)

# Prometheus metrics to validate per service
declare -A SERVICE_METRICS=(
    ["orchestrator-dynamic"]="orchestrator_workflows_started_total,orchestrator_ml_predictions_total"
    ["queen-agent"]="queen_agent_decisions_total,queen_agent_conflicts_detected_total"
    ["worker-agents"]="worker_tasks_executed_total,worker_executor_duration_seconds"
    ["code-forge"]="code_forge_pipelines_started_total,code_forge_validation_score"
    ["service-registry"]="service_registry_agents_registered_total"
)

# Counters for results
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNINGS=0

# Results storage for JSON report
declare -A PHASE_RESULTS
declare -a FAILED_SERVICES
declare -a WARNING_SERVICES

# Parse arguments
QUICK_MODE=false
FULL_MODE=false
JSON_OUTPUT=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --quick)
            QUICK_MODE=true
            shift
            ;;
        --full)
            FULL_MODE=true
            shift
            ;;
        --json)
            JSON_OUTPUT=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--quick|--full|--json]"
            exit 1
            ;;
    esac
done

# Utility functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASSED_CHECKS++))
    ((TOTAL_CHECKS++))
}

log_failure() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAILED_CHECKS++))
    ((TOTAL_CHECKS++))
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    ((WARNINGS++))
    ((TOTAL_CHECKS++))
}

log_header() {
    echo ""
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${CYAN}  $1${NC}"
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo ""
}

log_subheader() {
    echo -e "${BOLD}  ─── $1 ───${NC}"
}

# Check prerequisites
check_prerequisites() {
    log_header "PHASE 0: Prerequisites Check"

    local prereq_ok=true

    # Check kubectl
    if command -v kubectl &> /dev/null; then
        log_success "kubectl is available"
    else
        log_failure "kubectl is not installed"
        prereq_ok=false
    fi

    # Check cluster connectivity
    if kubectl cluster-info &> /dev/null; then
        log_success "Kubernetes cluster is accessible"
    else
        log_failure "Cannot connect to Kubernetes cluster"
        prereq_ok=false
    fi

    # Check Python for helper scripts
    if command -v python3 &> /dev/null; then
        log_success "Python3 is available"
    else
        log_warning "Python3 not found - some validations will be skipped"
    fi

    # Check jq for JSON processing
    if command -v jq &> /dev/null; then
        log_success "jq is available"
    else
        log_warning "jq not found - JSON output may be limited"
    fi

    # Create reports directory
    mkdir -p "${REPORT_DIR}"

    if [ "$prereq_ok" = false ]; then
        echo ""
        log_failure "Prerequisites check failed. Cannot continue."
        exit 1
    fi
}

# Phase 1: Validate Kubernetes Pods
validate_k8s_pods() {
    log_header "PHASE 1: Kubernetes Pods Validation"

    local phase_passed=true
    local pods_status=()

    for service in "${!SERVICE_NAMESPACES[@]}"; do
        local namespace="${SERVICE_NAMESPACES[$service]}"
        log_subheader "Checking $service in namespace $namespace"

        # Get pod status
        local pod_info
        pod_info=$(kubectl get pods -n "$namespace" -l "${SERVICE_LABEL_KEY}=$service" -o json 2>/dev/null || echo '{"items":[]}')

        local pod_count
        pod_count=$(echo "$pod_info" | jq '.items | length')

        if [ "$pod_count" -eq 0 ]; then
            log_failure "$service: No pods found"
            FAILED_SERVICES+=("$service:no_pods")
            phase_passed=false
            continue
        fi

        # Check each pod
        local ready_pods=0
        local total_pods=0

        for pod in $(echo "$pod_info" | jq -r '.items[].metadata.name'); do
            ((total_pods++))

            local pod_status
            pod_status=$(kubectl get pod "$pod" -n "$namespace" -o jsonpath='{.status.phase}' 2>/dev/null)

            local ready_status
            ready_status=$(kubectl get pod "$pod" -n "$namespace" -o jsonpath='{.status.containerStatuses[0].ready}' 2>/dev/null)

            if [ "$pod_status" = "Running" ] && [ "$ready_status" = "true" ]; then
                ((ready_pods++))
            else
                # Get events for problematic pod
                log_warning "$service/$pod: Status=$pod_status, Ready=$ready_status"
                kubectl get events -n "$namespace" --field-selector "involvedObject.name=$pod" --sort-by='.lastTimestamp' 2>/dev/null | tail -3
            fi
        done

        if [ "$ready_pods" -eq "$total_pods" ]; then
            log_success "$service: $ready_pods/$total_pods pods Running and Ready"
            pods_status+=("$service:$ready_pods/$total_pods:ok")
        else
            log_failure "$service: Only $ready_pods/$total_pods pods Ready"
            FAILED_SERVICES+=("$service:pods_not_ready")
            phase_passed=false
        fi

        # Verify probes are configured
        local has_liveness
        has_liveness=$(echo "$pod_info" | jq -r '.items[0].spec.containers[0].livenessProbe // empty')
        local has_readiness
        has_readiness=$(echo "$pod_info" | jq -r '.items[0].spec.containers[0].readinessProbe // empty')

        if [ -n "$has_liveness" ] && [ -n "$has_readiness" ]; then
            log_success "$service: Liveness and Readiness probes configured"
        else
            log_warning "$service: Missing probes (liveness: ${has_liveness:+yes}${has_liveness:-no}, readiness: ${has_readiness:+yes}${has_readiness:-no})"
            WARNING_SERVICES+=("$service:missing_probes")
        fi
    done

    PHASE_RESULTS["phase1_pods"]=$phase_passed

    if [ "$phase_passed" = true ]; then
        log_success "Phase 1 PASSED: All pods are Running and Ready"
    else
        log_failure "Phase 1 FAILED: Some pods are not Ready"
    fi
}

# Phase 2: Validate HTTP Endpoints
validate_http_endpoints() {
    log_header "PHASE 2: HTTP Endpoints Validation"

    local phase_passed=true

    for service in "${!SERVICE_PORTS[@]}"; do
        local namespace="${SERVICE_NAMESPACES[$service]}"
        local port="${SERVICE_PORTS[$service]}"

        log_subheader "Checking $service HTTP endpoints"

        # Get first running pod
        local pod
        pod=$(kubectl get pods -n "$namespace" -l "${SERVICE_LABEL_KEY}=$service" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

        if [ -z "$pod" ]; then
            log_failure "$service: No pod found for HTTP check"
            phase_passed=false
            continue
        fi

        # Check /health endpoint (liveness)
        local health_response
        health_response=$(kubectl exec -n "$namespace" "$pod" -- curl -s -o /dev/null -w "%{http_code}" "http://localhost:${port}/health" 2>/dev/null || echo "000")

        if [ "$health_response" = "200" ]; then
            log_success "$service: /health endpoint OK (HTTP $health_response)"
        else
            log_failure "$service: /health endpoint failed (HTTP $health_response)"
            FAILED_SERVICES+=("$service:health_endpoint")
            phase_passed=false
        fi

        # Check /ready endpoint (readiness)
        local ready_response
        ready_response=$(kubectl exec -n "$namespace" "$pod" -- curl -s -o /dev/null -w "%{http_code}" "http://localhost:${port}/ready" 2>/dev/null || echo "000")

        if [ "$ready_response" = "200" ]; then
            log_success "$service: /ready endpoint OK (HTTP $ready_response)"
        else
            log_failure "$service: /ready endpoint failed (HTTP $ready_response)"
            FAILED_SERVICES+=("$service:ready_endpoint")
            phase_passed=false
        fi

        # Check /metrics endpoint (Prometheus)
        local metrics_response
        metrics_response=$(kubectl exec -n "$namespace" "$pod" -- curl -s -o /dev/null -w "%{http_code}" "http://localhost:${port}/metrics" 2>/dev/null || echo "000")

        if [ "$metrics_response" = "200" ]; then
            log_success "$service: /metrics endpoint OK (HTTP $metrics_response)"
        else
            log_warning "$service: /metrics endpoint not available (HTTP $metrics_response)"
            WARNING_SERVICES+=("$service:no_metrics")
        fi

        # Validate health response body
        local health_body
        health_body=$(kubectl exec -n "$namespace" "$pod" -- curl -s "http://localhost:${port}/health" 2>/dev/null || echo "{}")

        local status_field
        status_field=$(echo "$health_body" | jq -r '.status // .healthy // empty' 2>/dev/null)

        if [ "$status_field" = "healthy" ] || [ "$status_field" = "true" ] || [ "$status_field" = "ok" ]; then
            log_success "$service: Health response body valid (status=$status_field)"
        else
            log_warning "$service: Health response body format unexpected"
        fi
    done

    PHASE_RESULTS["phase2_http"]=$phase_passed

    if [ "$phase_passed" = true ]; then
        log_success "Phase 2 PASSED: All HTTP endpoints responding"
    else
        log_failure "Phase 2 FAILED: Some HTTP endpoints not responding"
    fi
}

# Phase 3: Validate Prometheus Metrics
validate_prometheus_metrics() {
    log_header "PHASE 3: Prometheus Metrics Validation"

    local phase_passed=true

    for service in "${!SERVICE_METRICS[@]}"; do
        local namespace="${SERVICE_NAMESPACES[$service]}"
        local port="${SERVICE_PORTS[$service]}"
        local metrics="${SERVICE_METRICS[$service]}"

        log_subheader "Checking $service metrics"

        # Get first running pod
        local pod
        pod=$(kubectl get pods -n "$namespace" -l "${SERVICE_LABEL_KEY}=$service" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

        if [ -z "$pod" ]; then
            log_warning "$service: No pod found for metrics check"
            continue
        fi

        # Get metrics output
        local metrics_output
        metrics_output=$(kubectl exec -n "$namespace" "$pod" -- curl -s "http://localhost:${port}/metrics" 2>/dev/null || echo "")

        if [ -z "$metrics_output" ]; then
            log_warning "$service: No metrics output"
            continue
        fi

        # Check each expected metric
        IFS=',' read -ra METRIC_ARRAY <<< "$metrics"
        for metric in "${METRIC_ARRAY[@]}"; do
            if echo "$metrics_output" | grep -q "^${metric}"; then
                # Extract value
                local metric_value
                metric_value=$(echo "$metrics_output" | grep "^${metric}" | head -1 | awk '{print $2}')
                log_success "$service: Metric $metric exists (value=$metric_value)"
            else
                log_warning "$service: Metric $metric not found"
                WARNING_SERVICES+=("$service:missing_metric:$metric")
            fi
        done
    done

    PHASE_RESULTS["phase3_metrics"]=$phase_passed

    log_success "Phase 3 COMPLETED: Prometheus metrics validated"
}

# Phase 4: Validate Database Connectivity
validate_database_connectivity() {
    log_header "PHASE 4: Database Connectivity Validation"

    local phase_passed=true

    # Check if Python helper script exists
    local python_script="${SCRIPT_DIR}/test_database_connectivity.py"

    if [ -f "$python_script" ] && command -v python3 &> /dev/null; then
        log_info "Running Python database connectivity tests..."

        if python3 "$python_script" --quiet; then
            log_success "Database connectivity tests passed"
        else
            log_failure "Database connectivity tests failed"
            phase_passed=false
        fi
    else
        log_info "Python script not available, using kubectl-based validation..."

        # MongoDB validation
        log_subheader "MongoDB Connectivity"
        for service in "${!MONGODB_SERVICES[@]}"; do
            local namespace="${SERVICE_NAMESPACES[$service]}"
            local pod
            pod=$(kubectl get pods -n "$namespace" -l "${SERVICE_LABEL_KEY}=$service" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

            if [ -z "$pod" ]; then
                continue
            fi

            # Check logs for MongoDB initialization
            local mongo_init
            mongo_init=$(kubectl logs -n "$namespace" "$pod" --tail=100 2>/dev/null | grep -i "mongodb.*connect\|mongo.*initialized" || echo "")

            if [ -n "$mongo_init" ]; then
                log_success "$service: MongoDB connection initialized"
            else
                log_warning "$service: MongoDB connection status unclear"
            fi
        done

        # PostgreSQL validation
        log_subheader "PostgreSQL Connectivity"
        for service in "${!POSTGRESQL_SERVICES[@]}"; do
            local namespace="${SERVICE_NAMESPACES[$service]}"
            local pod
            pod=$(kubectl get pods -n "$namespace" -l "${SERVICE_LABEL_KEY}=$service" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

            if [ -z "$pod" ]; then
                continue
            fi

            # Check logs for PostgreSQL initialization
            local pg_init
            pg_init=$(kubectl logs -n "$namespace" "$pod" --tail=100 2>/dev/null | grep -i "postgres.*connect\|asyncpg.*initialized\|database.*ready" || echo "")

            if [ -n "$pg_init" ]; then
                log_success "$service: PostgreSQL connection initialized"
            else
                log_warning "$service: PostgreSQL connection status unclear"
            fi
        done

        # Redis validation
        log_subheader "Redis Connectivity"
        for service in "${!REDIS_SERVICES[@]}"; do
            local namespace="${SERVICE_NAMESPACES[$service]}"
            local pod
            pod=$(kubectl get pods -n "$namespace" -l "${SERVICE_LABEL_KEY}=$service" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

            if [ -z "$pod" ]; then
                continue
            fi

            # Check logs for Redis initialization
            local redis_init
            redis_init=$(kubectl logs -n "$namespace" "$pod" --tail=100 2>/dev/null | grep -i "redis.*connect\|redis.*initialized\|cache.*ready" || echo "")

            if [ -n "$redis_init" ]; then
                log_success "$service: Redis connection initialized"
            else
                log_warning "$service: Redis connection status unclear"
            fi
        done

        # Neo4j validation
        log_subheader "Neo4j Connectivity"
        for service in "${!NEO4J_SERVICES[@]}"; do
            local namespace="${SERVICE_NAMESPACES[$service]}"
            local pod
            pod=$(kubectl get pods -n "$namespace" -l "${SERVICE_LABEL_KEY}=$service" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

            if [ -z "$pod" ]; then
                continue
            fi

            # Check logs for Neo4j initialization
            local neo4j_init
            neo4j_init=$(kubectl logs -n "$namespace" "$pod" --tail=100 2>/dev/null | grep -i "neo4j.*connect\|graph.*initialized\|neo4j.*ready" || echo "")

            if [ -n "$neo4j_init" ]; then
                log_success "$service: Neo4j connection initialized"
            else
                log_warning "$service: Neo4j connection status unclear"
            fi
        done
    fi

    PHASE_RESULTS["phase4_databases"]=$phase_passed

    if [ "$phase_passed" = true ]; then
        log_success "Phase 4 PASSED: Database connectivity validated"
    else
        log_failure "Phase 4 FAILED: Some database connections failed"
    fi
}

# Phase 5: Validate gRPC Communication
validate_grpc_communication() {
    log_header "PHASE 5: gRPC Communication Validation"

    local phase_passed=true

    # Check if Python helper script exists
    local python_script="${SCRIPT_DIR}/test_grpc_communication.py"

    if [ -f "$python_script" ] && command -v python3 &> /dev/null; then
        log_info "Running Python gRPC communication tests..."

        if python3 "$python_script" --quiet; then
            log_success "gRPC communication tests passed"
        else
            log_failure "gRPC communication tests failed"
            phase_passed=false
        fi
    else
        log_info "Python script not available, using kubectl-based validation..."

        for service in "${!GRPC_SERVICES[@]}"; do
            local namespace="${SERVICE_NAMESPACES[$service]}"
            local grpc_port="${GRPC_SERVICES[$service]}"

            log_subheader "Checking $service gRPC service"

            # Get first running pod
            local pod
            pod=$(kubectl get pods -n "$namespace" -l "${SERVICE_LABEL_KEY}=$service" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

            if [ -z "$pod" ]; then
                log_warning "$service: No pod found for gRPC check"
                continue
            fi

            # Check if gRPC port is listening
            local port_check
            port_check=$(kubectl exec -n "$namespace" "$pod" -- sh -c "netstat -tlnp 2>/dev/null | grep :${grpc_port} || ss -tlnp 2>/dev/null | grep :${grpc_port} || echo ''" 2>/dev/null)

            if [ -n "$port_check" ]; then
                log_success "$service: gRPC port $grpc_port is listening"
            else
                log_failure "$service: gRPC port $grpc_port not listening"
                FAILED_SERVICES+=("$service:grpc_port")
                phase_passed=false
            fi

            # Check logs for gRPC server initialization
            local grpc_init
            grpc_init=$(kubectl logs -n "$namespace" "$pod" --tail=100 2>/dev/null | grep -i "grpc.*server\|grpc.*started\|grpc.*listening" || echo "")

            if [ -n "$grpc_init" ]; then
                log_success "$service: gRPC server initialized"
            else
                log_warning "$service: gRPC server initialization not confirmed in logs"
            fi
        done

        # Test gRPC health check if grpc-health-probe is available
        for service in "${!GRPC_SERVICES[@]}"; do
            local namespace="${SERVICE_NAMESPACES[$service]}"
            local grpc_port="${GRPC_SERVICES[$service]}"
            local pod
            pod=$(kubectl get pods -n "$namespace" -l "${SERVICE_LABEL_KEY}=$service" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

            if [ -z "$pod" ]; then
                continue
            fi

            # Try gRPC health check if tool is available in pod
            local health_check
            health_check=$(kubectl exec -n "$namespace" "$pod" -- grpc-health-probe -addr=localhost:${grpc_port} 2>/dev/null && echo "healthy" || echo "")

            if [ "$health_check" = "healthy" ]; then
                log_success "$service: gRPC Health Check SERVING"
            else
                log_warning "$service: gRPC Health Check not available (grpc-health-probe may not be installed)"
            fi
        done
    fi

    PHASE_RESULTS["phase5_grpc"]=$phase_passed

    if [ "$phase_passed" = true ]; then
        log_success "Phase 5 PASSED: gRPC communication validated"
    else
        log_failure "Phase 5 FAILED: Some gRPC services not responding"
    fi
}

# Phase 6: Validate Kafka Consumers
validate_kafka_consumers() {
    log_header "PHASE 6: Kafka Consumers Validation"

    local phase_passed=true

    # Check if Kafka consumers validation script exists
    local kafka_script="${SCRIPT_DIR}/test_kafka_consumers.sh"

    if [ -f "$kafka_script" ] && [ -x "$kafka_script" ]; then
        log_info "Running Kafka consumers validation script..."

        if bash "$kafka_script" --quiet; then
            log_success "Kafka consumers validation passed"
        else
            log_failure "Kafka consumers validation failed"
            phase_passed=false
        fi
    else
        log_info "Using kubectl-based Kafka validation..."

        for service in "${!KAFKA_CONSUMERS[@]}"; do
            local namespace="${SERVICE_NAMESPACES[$service]}"
            local topics="${KAFKA_CONSUMERS[$service]}"

            log_subheader "Checking $service Kafka consumers"

            # Get first running pod
            local pod
            pod=$(kubectl get pods -n "$namespace" -l "${SERVICE_LABEL_KEY}=$service" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

            if [ -z "$pod" ]; then
                log_warning "$service: No pod found for Kafka check"
                continue
            fi

            # Check logs for Kafka consumer initialization
            local kafka_init
            kafka_init=$(kubectl logs -n "$namespace" "$pod" --tail=200 2>/dev/null | grep -i "kafka.*consumer\|consumer.*started\|subscribed.*topic\|aiokafka" || echo "")

            if [ -n "$kafka_init" ]; then
                log_success "$service: Kafka consumer initialized"

                # Check for specific topics
                IFS=',' read -ra TOPIC_ARRAY <<< "$topics"
                for topic in "${TOPIC_ARRAY[@]}"; do
                    local topic_subscribed
                    topic_subscribed=$(kubectl logs -n "$namespace" "$pod" --tail=200 2>/dev/null | grep -i "$topic" || echo "")

                    if [ -n "$topic_subscribed" ]; then
                        log_success "$service: Subscribed to topic $topic"
                    else
                        log_warning "$service: Topic $topic subscription not confirmed"
                    fi
                done
            else
                log_warning "$service: Kafka consumer initialization not confirmed"
                WARNING_SERVICES+=("$service:kafka_consumer")
            fi

            # Check for consumer errors
            local kafka_errors
            kafka_errors=$(kubectl logs -n "$namespace" "$pod" --tail=200 2>/dev/null | grep -i "kafka.*error\|consumer.*error\|connection.*refused" || echo "")

            if [ -n "$kafka_errors" ]; then
                log_warning "$service: Kafka consumer errors detected"
                echo "$kafka_errors" | head -3
            fi
        done

        # Check Kafka consumer lag if kafka namespace exists
        local kafka_namespace="kafka"
        local kafka_pod
        kafka_pod=$(kubectl get pods -n "$kafka_namespace" -l "app.kubernetes.io/name=kafka" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

        if [ -n "$kafka_pod" ]; then
            log_subheader "Checking Kafka consumer groups"

            local consumer_groups
            consumer_groups=$(kubectl exec -n "$kafka_namespace" "$kafka_pod" -- kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list 2>/dev/null || echo "")

            if [ -n "$consumer_groups" ]; then
                log_success "Consumer groups found:"
                echo "$consumer_groups" | while read -r group; do
                    if [ -n "$group" ]; then
                        echo "  - $group"
                    fi
                done
            else
                log_warning "Could not list consumer groups"
            fi
        fi
    fi

    PHASE_RESULTS["phase6_kafka"]=$phase_passed

    if [ "$phase_passed" = true ]; then
        log_success "Phase 6 PASSED: Kafka consumers validated"
    else
        log_failure "Phase 6 FAILED: Some Kafka consumers not active"
    fi
}

# Phase 7: Validate Structured Logs
validate_structured_logs() {
    log_header "PHASE 7: Structured Logs Validation"

    local phase_passed=true

    for service in "${!SERVICE_NAMESPACES[@]}"; do
        local namespace="${SERVICE_NAMESPACES[$service]}"

        log_subheader "Checking $service logs"

        # Get first running pod
        local pod
        pod=$(kubectl get pods -n "$namespace" -l "${SERVICE_LABEL_KEY}=$service" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

        if [ -z "$pod" ]; then
            log_warning "$service: No pod found for log check"
            continue
        fi

        # Get recent logs
        local logs
        logs=$(kubectl logs -n "$namespace" "$pod" --tail=50 2>/dev/null || echo "")

        if [ -z "$logs" ]; then
            log_warning "$service: No logs available"
            continue
        fi

        # Check for JSON structured logs
        local json_logs
        json_logs=$(echo "$logs" | grep -E '^\{.*\}$' | head -1 || echo "")

        if [ -n "$json_logs" ]; then
            log_success "$service: Structured JSON logs detected"
        else
            log_warning "$service: Logs may not be in JSON format"
        fi

        # Check for initialization messages
        local init_messages
        init_messages=$(echo "$logs" | grep -i "initialized\|started\|ready\|listening" || echo "")

        if [ -n "$init_messages" ]; then
            log_success "$service: Initialization messages found"
        else
            log_warning "$service: No initialization messages in recent logs"
        fi

        # Check for errors
        local error_messages
        error_messages=$(echo "$logs" | grep -i "ERROR\|CRITICAL\|FATAL" || echo "")

        if [ -n "$error_messages" ]; then
            local error_count
            error_count=$(echo "$error_messages" | wc -l)
            log_warning "$service: $error_count error(s) found in recent logs"
            echo "$error_messages" | head -3
        else
            log_success "$service: No errors in recent logs"
        fi

        # Check for trace_id (OpenTelemetry correlation)
        local trace_ids
        trace_ids=$(echo "$logs" | grep -i "trace_id\|trace-id\|traceid" || echo "")

        if [ -n "$trace_ids" ]; then
            log_success "$service: OpenTelemetry trace correlation detected"
        fi
    done

    PHASE_RESULTS["phase7_logs"]=$phase_passed

    log_success "Phase 7 COMPLETED: Log validation finished"
}

# Phase 8: Generate Consolidated Report
generate_report() {
    log_header "PHASE 8: Generating Consolidated Report"

    # Calculate overall status
    local overall_status="PASSED"
    if [ "$FAILED_CHECKS" -gt 0 ]; then
        overall_status="FAILED"
    elif [ "$WARNINGS" -gt 5 ]; then
        overall_status="WARNING"
    fi

    # Generate JSON report
    cat > "$REPORT_FILE" << EOF
{
  "report_metadata": {
    "timestamp": "$(date -Iseconds)",
    "report_id": "${TIMESTAMP}",
    "overall_status": "${overall_status}"
  },
  "summary": {
    "total_checks": ${TOTAL_CHECKS},
    "passed_checks": ${PASSED_CHECKS},
    "failed_checks": ${FAILED_CHECKS},
    "warnings": ${WARNINGS},
    "pass_rate": $(awk "BEGIN {printf \"%.2f\", ${PASSED_CHECKS}/${TOTAL_CHECKS}*100}")
  },
  "phases": {
    "phase1_pods": ${PHASE_RESULTS["phase1_pods"]:-false},
    "phase2_http": ${PHASE_RESULTS["phase2_http"]:-false},
    "phase3_metrics": ${PHASE_RESULTS["phase3_metrics"]:-true},
    "phase4_databases": ${PHASE_RESULTS["phase4_databases"]:-true},
    "phase5_grpc": ${PHASE_RESULTS["phase5_grpc"]:-true},
    "phase6_kafka": ${PHASE_RESULTS["phase6_kafka"]:-true},
    "phase7_logs": ${PHASE_RESULTS["phase7_logs"]:-true}
  },
  "failed_services": [
$(printf '    "%s",\n' "${FAILED_SERVICES[@]}" | sed '$ s/,$//')
  ],
  "warnings": [
$(printf '    "%s",\n' "${WARNING_SERVICES[@]}" | sed '$ s/,$//')
  ]
}
EOF

    log_success "Report saved to: $REPORT_FILE"

    # Print summary table
    echo ""
    echo -e "${BOLD}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}║              PHASE 2 VALIDATION SUMMARY                        ║${NC}"
    echo -e "${BOLD}╠════════════════════════════════════════════════════════════════╣${NC}"
    printf "${BOLD}║${NC} %-20s │ %s\n" "Total Checks:" "$TOTAL_CHECKS ${BOLD}║${NC}"
    printf "${BOLD}║${NC} %-20s │ ${GREEN}%s${NC}\n" "Passed:" "$PASSED_CHECKS ${BOLD}║${NC}"
    printf "${BOLD}║${NC} %-20s │ ${RED}%s${NC}\n" "Failed:" "$FAILED_CHECKS ${BOLD}║${NC}"
    printf "${BOLD}║${NC} %-20s │ ${YELLOW}%s${NC}\n" "Warnings:" "$WARNINGS ${BOLD}║${NC}"
    echo -e "${BOLD}╠════════════════════════════════════════════════════════════════╣${NC}"

    if [ "$overall_status" = "PASSED" ]; then
        echo -e "${BOLD}║${NC}              ${GREEN}${BOLD}OVERALL STATUS: PASSED${NC}                           ${BOLD}║${NC}"
    elif [ "$overall_status" = "WARNING" ]; then
        echo -e "${BOLD}║${NC}              ${YELLOW}${BOLD}OVERALL STATUS: WARNING${NC}                          ${BOLD}║${NC}"
    else
        echo -e "${BOLD}║${NC}              ${RED}${BOLD}OVERALL STATUS: FAILED${NC}                           ${BOLD}║${NC}"
    fi

    echo -e "${BOLD}╚════════════════════════════════════════════════════════════════╝${NC}"

    # JSON output if requested
    if [ "$JSON_OUTPUT" = true ]; then
        echo ""
        cat "$REPORT_FILE"
    fi

    # Return appropriate exit code
    if [ "$overall_status" = "FAILED" ]; then
        return 1
    fi
    return 0
}

# Main execution
main() {
    echo -e "${BOLD}${CYAN}"
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║     NEURAL HIVE MIND - PHASE 2 SERVICES VALIDATION            ║"
    echo "║                                                                ║"
    echo "║     Comprehensive validation of 13 Phase 2 services           ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    local start_time
    start_time=$(date +%s)

    # Run all phases
    check_prerequisites
    validate_k8s_pods
    validate_http_endpoints

    if [ "$QUICK_MODE" = false ]; then
        validate_prometheus_metrics
        validate_database_connectivity
        validate_grpc_communication
        validate_kafka_consumers
        validate_structured_logs
    fi

    generate_report
    local result=$?

    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))

    echo ""
    log_info "Validation completed in ${duration} seconds"

    exit $result
}

# Run main
main "$@"
