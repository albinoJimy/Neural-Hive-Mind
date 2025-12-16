#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
set -e

# SLA Management System Validation Script
# Valida que o sistema está funcionando corretamente

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
NAMESPACE="neural-hive-monitoring"

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Contadores
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0

# Argumentos
VERBOSE=false
SKIP_FUNCTIONAL=false
REPORT_FILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        --skip-functional)
            SKIP_FUNCTIONAL=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --report)
            REPORT_FILE="$2"
            shift 2
            ;;
        --help)
            echo "Uso: $0 [opções]"
            echo ""
            echo "Opções:"
            echo "  --namespace <ns>      Valida em namespace específico (default: neural-hive-monitoring)"
            echo "  --skip-functional     Pula testes funcionais (apenas infraestrutura)"
            echo "  --verbose             Mostra output detalhado"
            echo "  --report <file>       Salva relatório em arquivo JSON"
            echo "  --help                Mostra esta mensagem"
            exit 0
            ;;
        *)
            echo "Opção desconhecida: $1"
            exit 1
            ;;
    esac
done

# Funções
log_check() {
    echo -e "${BLUE}[CHECK]${NC} $1"
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASSED_CHECKS++))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAILED_CHECKS++))
}

log_info() {
    if [ "$VERBOSE" = true ]; then
        echo -e "${YELLOW}[INFO]${NC} $1"
    fi
}

run_check() {
    ((TOTAL_CHECKS++))
    log_check "$1"
}

# Início da validação
echo "========================================"
echo "SLA Management System - Validação"
echo "Namespace: $NAMESPACE"
echo "========================================"
echo ""

# 1. VALIDAÇÃO DE INFRAESTRUTURA
echo "=== 1. Validação de Infraestrutura ==="
echo ""

# 1.1 CRDs instalados
run_check "CRDs instalados e estabelecidos"
if kubectl get crd slodefinitions.neural-hive.io &> /dev/null && \
   kubectl get crd slapolicies.neural-hive.io &> /dev/null; then
    log_pass "CRDs instalados: slodefinitions.neural-hive.io, slapolicies.neural-hive.io"
else
    log_fail "CRDs não instalados ou não estabelecidos"
fi

# 1.2 Namespace existe
run_check "Namespace existe"
if kubectl get namespace "$NAMESPACE" &> /dev/null; then
    log_pass "Namespace $NAMESPACE existe"
else
    log_fail "Namespace $NAMESPACE não existe"
    exit 1
fi

# 1.3 Helm release deployado
run_check "Helm release deployado"
if helm list -n "$NAMESPACE" | grep -q sla-management-system; then
    log_pass "Helm release 'sla-management-system' encontrado"
else
    log_fail "Helm release não encontrado"
fi

# 1.4 Pods running
run_check "Pods em execução"
RUNNING_PODS=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=sla-management-system --field-selector=status.phase=Running -o json | jq '.items | length')
if [ "$RUNNING_PODS" -gt 0 ]; then
    log_pass "$RUNNING_PODS pods em execução"
else
    log_fail "Nenhum pod em execução"
fi

# 1.5 Todos os pods prontos
run_check "Todos os pods prontos"
READY_PODS=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=sla-management-system -o json | jq '[.items[] | select(.status.conditions[] | select(.type=="Ready" and .status=="True"))] | length')
if [ "$READY_PODS" -eq "$RUNNING_PODS" ] && [ "$READY_PODS" -gt 0 ]; then
    log_pass "Todos os $READY_PODS pods prontos"
else
    log_fail "Apenas $READY_PODS de $RUNNING_PODS pods prontos"
fi

# 1.6 Serviço criado
run_check "Serviço criado"
if kubectl get svc sla-management-system -n "$NAMESPACE" &> /dev/null; then
    ENDPOINTS=$(kubectl get endpoints sla-management-system -n "$NAMESPACE" -o json | jq '.subsets[0].addresses | length')
    if [ "$ENDPOINTS" -gt 0 ]; then
        log_pass "Serviço criado com $ENDPOINTS endpoints"
    else
        log_fail "Serviço criado mas sem endpoints"
    fi
else
    log_fail "Serviço não encontrado"
fi

# 1.7 ServiceMonitor criado (se habilitado)
run_check "ServiceMonitor criado"
if kubectl get servicemonitor sla-management-system -n "$NAMESPACE" &> /dev/null; then
    log_pass "ServiceMonitor criado"
else
    log_info "ServiceMonitor não encontrado (pode estar desabilitado)"
fi

echo ""

# 2. VALIDAÇÃO DE COMPONENTES
echo "=== 2. Validação de Componentes ==="
echo ""

# 2.1 API Server Health
run_check "API Server health endpoint"
HEALTH_RESPONSE=$(kubectl run curl-test-health --image=curlimages/curl --rm -i --restart=Never -n "$NAMESPACE" -- \
    curl -s -o /dev/null -w "%{http_code}" http://sla-management-system.$NAMESPACE.svc.cluster.local:8000/health 2>/dev/null || echo "000")
if [ "$HEALTH_RESPONSE" = "200" ]; then
    log_pass "Health endpoint retornou 200"
else
    log_fail "Health endpoint retornou $HEALTH_RESPONSE (esperado 200)"
fi

# 2.2 API Server Ready
run_check "API Server ready endpoint"
READY_RESPONSE=$(kubectl run curl-test-ready --image=curlimages/curl --rm -i --restart=Never -n "$NAMESPACE" -- \
    curl -s -o /dev/null -w "%{http_code}" http://sla-management-system.$NAMESPACE.svc.cluster.local:8000/ready 2>/dev/null || echo "000")
if [ "$READY_RESPONSE" = "200" ]; then
    log_pass "Ready endpoint retornou 200"
else
    log_fail "Ready endpoint retornou $READY_RESPONSE (esperado 200)"
fi

# 2.3 Operator running
run_check "Operator em execução"
if kubectl get deployment sla-management-system-operator -n "$NAMESPACE" &> /dev/null; then
    OPERATOR_READY=$(kubectl get deployment sla-management-system-operator -n "$NAMESPACE" -o json | jq '.status.readyReplicas // 0')
    if [ "$OPERATOR_READY" -gt 0 ]; then
        log_pass "Operator com $OPERATOR_READY replicas prontas"
    else
        log_fail "Operator não pronto"
    fi
else
    log_info "Operator não encontrado (pode estar desabilitado)"
fi

# 2.4 Metrics endpoint
run_check "Metrics endpoint acessível"
METRICS_RESPONSE=$(kubectl run curl-test-metrics --image=curlimages/curl --rm -i --restart=Never -n "$NAMESPACE" -- \
    curl -s http://sla-management-system.$NAMESPACE.svc.cluster.local:9090/metrics 2>/dev/null | head -n 1 || echo "")
if [[ "$METRICS_RESPONSE" == \#* ]]; then
    log_pass "Metrics endpoint acessível"
else
    log_fail "Metrics endpoint não acessível"
fi

echo ""

# 3. VALIDAÇÃO DE INTEGRAÇÕES
echo "=== 3. Validação de Integrações ==="
echo ""

# 3.1 PostgreSQL connection
run_check "Conexão PostgreSQL"
READY_JSON=$(kubectl run curl-test-ready-json --image=curlimages/curl --rm -i --restart=Never -n "$NAMESPACE" -- \
    curl -s http://sla-management-system.$NAMESPACE.svc.cluster.local:8000/ready 2>/dev/null || echo "{}")
POSTGRES_OK=$(echo "$READY_JSON" | jq -r '.postgresql // "unknown"')
if [ "$POSTGRES_OK" = "ok" ]; then
    log_pass "PostgreSQL conectado"
else
    log_fail "PostgreSQL: $POSTGRES_OK"
fi

# 3.2 Redis connection
run_check "Conexão Redis"
REDIS_OK=$(echo "$READY_JSON" | jq -r '.redis // "unknown"')
if [ "$REDIS_OK" = "ok" ]; then
    log_pass "Redis conectado"
else
    log_fail "Redis: $REDIS_OK"
fi

# 3.3 Prometheus connection
run_check "Conexão Prometheus"
PROMETHEUS_OK=$(echo "$READY_JSON" | jq -r '.prometheus // "unknown"')
if [ "$PROMETHEUS_OK" = "ok" ]; then
    log_pass "Prometheus conectado"
else
    log_fail "Prometheus: $PROMETHEUS_OK"
fi

# 3.4 Kafka connection
run_check "Conexão Kafka"
KAFKA_OK=$(echo "$READY_JSON" | jq -r '.kafka // "unknown"')
if [ "$KAFKA_OK" = "ok" ]; then
    log_pass "Kafka conectado"
else
    log_info "Kafka: $KAFKA_OK (pode ser opcional)"
fi

echo ""

# 4. TESTES FUNCIONAIS (se não pulados)
if [ "$SKIP_FUNCTIONAL" = false ]; then
    echo "=== 4. Testes Funcionais ==="
    echo ""

    # Criar SLO de teste
    run_check "Criar SLO via CRD"
    TEST_SLO_FILE="/tmp/test-slo-$$.yaml"
    cat > "$TEST_SLO_FILE" << EOF
apiVersion: neural-hive.io/v1
kind: SLODefinition
metadata:
  name: test-slo-validation
  namespace: $NAMESPACE
spec:
  name: "Test SLO - Validation"
  description: "SLO de teste para validação"
  sloType: AVAILABILITY
  serviceName: test-service
  layer: testing
  target: 0.99
  windowDays: 7
  sliQuery:
    metricName: up
    query: "up{job='test'}"
    aggregation: avg
  enabled: true
EOF

    if kubectl apply -f "$TEST_SLO_FILE" &> /dev/null; then
        sleep 5  # Aguardar operator processar
        SLO_SYNCED=$(kubectl get slodefinition test-slo-validation -n "$NAMESPACE" -o json 2>/dev/null | jq -r '.status.synced // false')
        if [ "$SLO_SYNCED" = "true" ]; then
            log_pass "SLO criado e sincronizado"
        else
            log_fail "SLO criado mas não sincronizado"
        fi
    else
        log_fail "Falha ao criar SLO"
    fi

    # Verificar API
    run_check "Listar SLOs via API"
    SLOS_RESPONSE=$(kubectl run curl-test-slos --image=curlimages/curl --rm -i --restart=Never -n "$NAMESPACE" -- \
        curl -s -o /dev/null -w "%{http_code}" http://sla-management-system.$NAMESPACE.svc.cluster.local:8000/api/v1/slos 2>/dev/null || echo "000")
    if [ "$SLOS_RESPONSE" = "200" ]; then
        log_pass "API /api/v1/slos acessível"
    else
        log_fail "API /api/v1/slos retornou $SLOS_RESPONSE"
    fi

    # Limpar
    kubectl delete slodefinition test-slo-validation -n "$NAMESPACE" &> /dev/null || true
    rm -f "$TEST_SLO_FILE"

    echo ""
fi

# 5. VALIDAÇÃO DE MÉTRICAS
echo "=== 5. Validação de Métricas ==="
echo ""

run_check "Métricas sendo expostas"
METRICS_COUNT=$(kubectl run curl-test-metrics-count --image=curlimages/curl --rm -i --restart=Never -n "$NAMESPACE" -- \
    curl -s http://sla-management-system.$NAMESPACE.svc.cluster.local:9090/metrics 2>/dev/null | grep -c "^sla_" || echo "0")
if [ "$METRICS_COUNT" -gt 0 ]; then
    log_pass "$METRICS_COUNT métricas SLA encontradas"
else
    log_fail "Nenhuma métrica SLA encontrada"
fi

echo ""

# 6. RELATÓRIO FINAL
echo "========================================"
echo "Resumo da Validação"
echo "========================================"
echo ""
echo "Total de verificações: $TOTAL_CHECKS"
echo -e "${GREEN}Passou: $PASSED_CHECKS${NC}"
echo -e "${RED}Falhou: $FAILED_CHECKS${NC}"
echo ""

# Calcular percentual
if [ "$TOTAL_CHECKS" -gt 0 ]; then
    SUCCESS_RATE=$((PASSED_CHECKS * 100 / TOTAL_CHECKS))
    echo "Taxa de sucesso: $SUCCESS_RATE%"
fi

# Salvar relatório JSON se solicitado
if [ -n "$REPORT_FILE" ]; then
    cat > "$REPORT_FILE" << EOF
{
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "namespace": "$NAMESPACE",
  "total_checks": $TOTAL_CHECKS,
  "passed": $PASSED_CHECKS,
  "failed": $FAILED_CHECKS,
  "success_rate": $SUCCESS_RATE,
  "status": "$([ $FAILED_CHECKS -eq 0 ] && echo "PASS" || echo "FAIL")"
}
EOF
    echo ""
    echo "Relatório salvo em: $REPORT_FILE"
fi

echo ""

# Exit code baseado em falhas
if [ "$FAILED_CHECKS" -eq 0 ]; then
    echo -e "${GREEN}✓ Validação completada com sucesso!${NC}"
    exit 0
else
    echo -e "${RED}✗ Validação completada com falhas${NC}"
    echo ""
    echo "Para investigar:"
    echo "  kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=sla-management-system"
    echo "  kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=sla-management-system --tail=100"
    exit 1
fi
