#!/bin/bash
set -euo pipefail

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configurações
NAMESPACE="${NAMESPACE:-neural-hive-exploration}"

# Contadores
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0

check_pass() {
    echo -e "${GREEN}✅ PASS:${NC} $1"
    ((PASSED_CHECKS++))
    ((TOTAL_CHECKS++))
}

check_fail() {
    echo -e "${RED}❌ FAIL:${NC} $1"
    ((FAILED_CHECKS++))
    ((TOTAL_CHECKS++))
}

check_warn() {
    echo -e "${YELLOW}⚠️  WARN:${NC} $1"
    ((TOTAL_CHECKS++))
}

section_header() {
    echo -e "\n${BLUE}===== $1 =====${NC}"
}

# FASE 1: Infraestrutura
section_header "FASE 1: Validação de Infraestrutura"

# Check 1.1: Namespace existe
if kubectl get namespace "$NAMESPACE" &> /dev/null; then
    check_pass "Namespace $NAMESPACE existe"
else
    check_fail "Namespace $NAMESPACE não existe"
    exit 1
fi

# Check 1.2: Labels do namespace
LABELS=$(kubectl get namespace "$NAMESPACE" -o jsonpath='{.metadata.labels}')
if echo "$LABELS" | grep -q "neural-hive.io/layer"; then
    check_pass "Labels do namespace corretos"
else
    check_warn "Labels do namespace podem estar faltando"
fi

# Check 1.3: Tópicos Kafka existem
if kubectl get kafkatopic exploration-signals -n kafka &> /dev/null; then
    check_pass "Tópico exploration.signals existe"
else
    check_fail "Tópico exploration.signals não existe"
fi

if kubectl get kafkatopic exploration-opportunities -n kafka &> /dev/null; then
    check_pass "Tópico exploration.opportunities existe"
else
    check_fail "Tópico exploration.opportunities não existe"
fi

# Check 1.4: Service Registry acessível
if kubectl get svc service-registry -n neural-hive-services &> /dev/null; then
    check_pass "Service Registry acessível"
else
    check_warn "Service Registry pode não estar acessível"
fi

# Check 1.5: Memory Layer API acessível
if kubectl get svc memory-layer-api -n neural-hive-services &> /dev/null; then
    check_pass "Memory Layer API acessível"
else
    check_warn "Memory Layer API pode não estar acessível"
fi

# FASE 2: Deployment
section_header "FASE 2: Validação de Deployment"

# Check 2.1: Deployment existe
if kubectl get deployment scout-agents -n "$NAMESPACE" &> /dev/null; then
    check_pass "Deployment scout-agents existe"
else
    check_fail "Deployment scout-agents não existe"
    exit 1
fi

# Check 2.2: Réplicas desejadas
DESIRED=$(kubectl get deployment scout-agents -n "$NAMESPACE" -o jsonpath='{.spec.replicas}')
READY=$(kubectl get deployment scout-agents -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}')

if [ "$DESIRED" = "$READY" ]; then
    check_pass "Réplicas prontas: $READY/$DESIRED"
else
    check_fail "Réplicas não prontas: $READY/$DESIRED"
fi

# Check 2.3: Pods running
PODS_RUNNING=$(kubectl get pods -l app.kubernetes.io/name=scout-agents -n "$NAMESPACE" -o jsonpath='{.items[*].status.phase}' | tr ' ' '\n' | grep -c "Running" || true)

if [ "$PODS_RUNNING" -gt 0 ]; then
    check_pass "$PODS_RUNNING pods em estado Running"
else
    check_fail "Nenhum pod em estado Running"
fi

# Check 2.4: Service existe
if kubectl get svc scout-agents -n "$NAMESPACE" &> /dev/null; then
    check_pass "Service scout-agents existe"
else
    check_fail "Service scout-agents não existe"
fi

# Check 2.5: Service tem endpoints
ENDPOINTS=$(kubectl get endpoints scout-agents -n "$NAMESPACE" -o jsonpath='{.subsets[*].addresses[*].ip}' | wc -w)

if [ "$ENDPOINTS" -gt 0 ]; then
    check_pass "Service tem $ENDPOINTS endpoints"
else
    check_fail "Service não tem endpoints"
fi

# Check 2.6: ServiceMonitor
if kubectl get servicemonitor scout-agents -n "$NAMESPACE" &> /dev/null; then
    check_pass "ServiceMonitor existe"
else
    check_warn "ServiceMonitor não existe (opcional)"
fi

# Check 2.7: HPA
if kubectl get hpa scout-agents -n "$NAMESPACE" &> /dev/null; then
    check_pass "HorizontalPodAutoscaler existe"
else
    check_warn "HPA não existe (pode estar desabilitado)"
fi

# FASE 3: Funcionalidade
section_header "FASE 3: Validação de Funcionalidade"

# Get primeiro pod
POD=$(kubectl get pods -l app.kubernetes.io/name=scout-agents -n "$NAMESPACE" -o jsonpath='{.items[0].metadata.name}')

if [ -z "$POD" ]; then
    check_fail "Nenhum pod disponível para testes funcionais"
else
    # Check 3.1: Liveness probe
    if kubectl exec -n "$NAMESPACE" "$POD" -- curl -sf http://localhost:8000/health/live > /dev/null 2>&1; then
        check_pass "Liveness probe respondendo"
    else
        check_fail "Liveness probe falhou"
    fi

    # Check 3.2: Readiness probe
    if kubectl exec -n "$NAMESPACE" "$POD" -- curl -sf http://localhost:8000/health/ready > /dev/null 2>&1; then
        check_pass "Readiness probe respondendo"
    else
        check_fail "Readiness probe falhou"
    fi

    # Check 3.3: Metrics endpoint
    if kubectl exec -n "$NAMESPACE" "$POD" -- curl -sf http://localhost:9090/metrics > /dev/null 2>&1; then
        check_pass "Metrics endpoint respondendo"
    else
        check_fail "Metrics endpoint falhou"
    fi

    # Check 3.4: Status API
    if kubectl exec -n "$NAMESPACE" "$POD" -- curl -sf http://localhost:8000/api/v1/status > /dev/null 2>&1; then
        check_pass "Status API respondendo"
    else
        check_warn "Status API não respondendo"
    fi

    # Check 3.5: Logs sem erros críticos
    CRITICAL_ERRORS=$(kubectl logs -n "$NAMESPACE" "$POD" --tail=100 | grep -i "error\|critical\|fatal" | wc -l)

    if [ "$CRITICAL_ERRORS" -eq 0 ]; then
        check_pass "Sem erros críticos nos logs"
    else
        check_warn "$CRITICAL_ERRORS possíveis erros encontrados nos logs"
    fi
fi

# FASE 4: Integração
section_header "FASE 4: Validação de Integração"

if [ -n "$POD" ]; then
    # Check 4.1: Simular sinal
    SIMULATION=$(kubectl exec -n "$NAMESPACE" "$POD" -- curl -sf -X POST "http://localhost:8000/api/v1/signals/simulate?domain=TECHNICAL" 2>&1 || true)

    if echo "$SIMULATION" | grep -q "signal_detected\|no_signal_detected"; then
        check_pass "Simulação de sinal funcionando"
    else
        check_warn "Simulação de sinal pode ter falhado"
    fi

    # Check 4.2: Verificar métricas Prometheus
    METRICS=$(kubectl exec -n "$NAMESPACE" "$POD" -- curl -s http://localhost:9090/metrics 2>&1)

    if echo "$METRICS" | grep -q "scout_agent_startup_total"; then
        check_pass "Métricas Prometheus sendo expostas"
    else
        check_fail "Métricas Prometheus não encontradas"
    fi

    # Check 4.3: Verificar métricas de detecção
    if echo "$METRICS" | grep -q "scout_agent_signals_detected_total"; then
        check_pass "Métricas de detecção configuradas"
    else
        check_warn "Métricas de detecção podem não estar sendo geradas"
    fi
fi

# FASE 5: Performance
section_header "FASE 5: Validação de Performance"

if [ -n "$POD" ]; then
    # Check 5.1: CPU usage
    CPU_USAGE=$(kubectl top pod "$POD" -n "$NAMESPACE" 2>&1 | tail -1 | awk '{print $2}' | sed 's/m//' || echo "0")

    if [ "$CPU_USAGE" -lt 400 ]; then
        check_pass "CPU usage OK ($CPU_USAGE millicores)"
    else
        check_warn "CPU usage elevado ($CPU_USAGE millicores)"
    fi

    # Check 5.2: Memory usage
    MEMORY_USAGE=$(kubectl top pod "$POD" -n "$NAMESPACE" 2>&1 | tail -1 | awk '{print $3}' | sed 's/Mi//' || echo "0")

    if [ "$MEMORY_USAGE" -lt 410 ]; then
        check_pass "Memory usage OK ($MEMORY_USAGE Mi)"
    else
        check_warn "Memory usage elevado ($MEMORY_USAGE Mi)"
    fi
fi

# Relatório Final
section_header "RELATÓRIO FINAL"

echo "Total de verificações: $TOTAL_CHECKS"
echo -e "${GREEN}Passaram: $PASSED_CHECKS${NC}"
echo -e "${RED}Falharam: $FAILED_CHECKS${NC}"

if [ "$FAILED_CHECKS" -eq 0 ]; then
    echo -e "\n${GREEN}✅ TODAS AS VALIDAÇÕES PASSARAM!${NC}"
    exit 0
else
    echo -e "\n${RED}❌ ALGUMAS VALIDAÇÕES FALHARAM${NC}"
    exit 1
fi
