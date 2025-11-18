#!/bin/bash

echo "========================================="
echo "Neural Hive Mind - Teste E2E Fase 1 (CORRIGIDO)"
echo "========================================="
echo ""

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PASSED=0
FAILED=0

test_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $2"
        PASSED=$((PASSED + 1))
    else
        echo -e "${RED}✗${NC} $2"
        FAILED=$((FAILED + 1))
    fi
}

cleanup_port_forward() {
    pkill -f "kubectl port-forward" 2>/dev/null
}
trap cleanup_port_forward EXIT

echo -e "${BLUE}=== FASE 1: Infraestrutura ===${NC}"
echo ""

echo "1.1 Verificando camadas de memória..."
for component in redis-cluster mongodb-cluster neo4j-cluster clickhouse-cluster; do
    if kubectl get statefulset -n ${component} &> /dev/null || kubectl get deployment -n ${component} &> /dev/null; then
        test_result 0 "${component} deployado"
    else
        test_result 1 "${component} NÃO deployado"
    fi
done
echo ""

echo "1.2 Verificando serviços Fase 1..."
declare -A services=(
    ["gateway-intencoes"]="gateway-intencoes"
    ["gateway"]="gateway-intencoes"
    ["semantic-translation-engine"]="semantic-translation-engine"
    ["specialist-business"]="specialist-business"
    ["specialist-technical"]="specialist-technical"
    ["specialist-behavior"]="specialist-behavior"
    ["specialist-evolution"]="specialist-evolution"
    ["specialist-architecture"]="specialist-architecture"
    ["consensus-engine"]="consensus-engine"
    ["memory-layer-api"]="memory-layer-api"
)

checked_services=()
for ns in "${!services[@]}"; do
    name="${services[$ns]}"
    
    # Evitar verificar o mesmo serviço duas vezes
    if [[ " ${checked_services[@]} " =~ " ${name} " ]]; then
        continue
    fi
    checked_services+=("$name")
    
    if kubectl get deployment -n "$ns" 2>/dev/null | grep -q "$name"; then
        running=$(kubectl get pods -n "$ns" -o wide 2>/dev/null | grep -c "Running" || echo "0")
        if [ "$running" -gt 0 ]; then
            test_result 0 "${name} Running em ${ns}"
        else
            test_result 1 "${name} não Running em ${ns}"
        fi
    else
        test_result 1 "${name} não encontrado em ${ns}"
    fi
done
echo ""

echo -e "${BLUE}=== FASE 2: Health Checks (via Service) ===${NC}"
echo ""

echo "2.1 Verificando health dos specialists via port-forward..."
for spec in business technical behavior evolution architecture; do
    ns="specialist-$spec"
    pod=$(kubectl get pods -n "$ns" -o jsonpath='{.items[?(@.status.phase=="Running")].metadata.name}' 2>/dev/null | awk '{print $1}')
    
    if [ -n "$pod" ]; then
        port=$((9000 + RANDOM % 1000))
        kubectl port-forward -n "$ns" "$pod" "$port:8000" &>/dev/null &
        PF_PID=$!
        sleep 2
        
        health=$(curl -s --max-time 3 http://localhost:$port/health 2>/dev/null || echo "error")
        kill $PF_PID 2>/dev/null
        
        if echo "$health" | grep -q "healthy\|ok"; then
            test_result 0 "specialist-$spec health OK"
        else
            test_result 1 "specialist-$spec health FAIL"
        fi
    else
        test_result 1 "specialist-$spec pod não encontrado"
    fi
done
echo ""

echo "2.2 Verificando health do gateway..."
for ns in gateway-intencoes gateway; do
    pod=$(kubectl get pods -n "$ns" -o jsonpath='{.items[?(@.status.phase=="Running")].metadata.name}' 2>/dev/null | head -1)
    if [ -n "$pod" ]; then
        port=$((9000 + RANDOM % 1000))
        kubectl port-forward -n "$ns" "$pod" "$port:8000" &>/dev/null &
        PF_PID=$!
        sleep 2
        
        health=$(curl -s --max-time 3 http://localhost:$port/health 2>/dev/null || echo "error")
        kill $PF_PID 2>/dev/null
        
        if echo "$health" | grep -q "healthy"; then
            test_result 0 "gateway-intencoes health OK (ns: $ns)"
            break
        fi
    fi
done
echo ""

echo "2.3 Verificando health do Semantic Translation Engine..."
pod=$(kubectl get pods -n semantic-translation-engine -o jsonpath='{.items[?(@.status.phase=="Running")].metadata.name}' 2>/dev/null | head -1)
if [ -n "$pod" ]; then
    port=$((9000 + RANDOM % 1000))
    kubectl port-forward -n semantic-translation-engine "$pod" "$port:8000" &>/dev/null &
    PF_PID=$!
    sleep 2
    
    health=$(curl -s --max-time 3 http://localhost:$port/health 2>/dev/null || echo "error")
    kill $PF_PID 2>/dev/null
    
    if echo "$health" | grep -q "healthy\|ok"; then
        test_result 0 "semantic-translation-engine health OK"
    else
        test_result 1 "semantic-translation-engine health FAIL"
    fi
else
    test_result 1 "semantic-translation-engine pod não encontrado"
fi
echo ""

echo -e "${BLUE}=== FASE 3: Conectividade ===${NC}"
echo ""

echo "3.1 Verificando Redis..."
redis_pod=$(kubectl get pods -n redis-cluster -l "app.kubernetes.io/name=redis" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -z "$redis_pod" ]; then
    redis_pod=$(kubectl get pods -n redis-cluster -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
fi

if [ -n "$redis_pod" ]; then
    redis_ping=$(kubectl exec -n redis-cluster "$redis_pod" -- redis-cli PING 2>/dev/null || echo "error")
    if [ "$redis_ping" = "PONG" ]; then
        test_result 0 "Redis conectividade OK"
    else
        test_result 1 "Redis ping FAIL"
    fi
else
    test_result 1 "Redis pod não encontrado"
fi
echo ""

echo "3.2 Verificando MongoDB..."
mongo_pod=$(kubectl get pods -n mongodb-cluster -l "app.kubernetes.io/name=mongodb" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$mongo_pod" ]; then
    mongo_ping=$(kubectl exec -n mongodb-cluster "$mongo_pod" -- mongosh --quiet --eval "db.adminCommand('ping').ok" 2>/dev/null || echo "0")
    if [ "$mongo_ping" = "1" ]; then
        test_result 0 "MongoDB conectividade OK"
    else
        test_result 1 "MongoDB ping FAIL"
    fi
else
    test_result 1 "MongoDB pod não encontrado"
fi
echo ""

echo "3.3 Verificando Kafka..."
kafka_pod=$(kubectl get pods -n kafka -l app.kubernetes.io/name=kafka -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$kafka_pod" ]; then
    topics=$(kubectl exec -n kafka "$kafka_pod" -- bin/kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null | wc -l)
    if [ "$topics" -gt 0 ]; then
        test_result 0 "Kafka conectividade OK ($topics topics)"
    else
        test_result 1 "Kafka sem topics"
    fi
else
    test_result 1 "Kafka pod não encontrado"
fi
echo ""

echo "========================================="
echo "RESUMO FINAL"
echo "========================================="
echo -e "${GREEN}Testes Passados:${NC} $PASSED"
echo -e "${RED}Testes Falhados:${NC} $FAILED"
echo -e "Total: $((PASSED + FAILED))"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ TODOS OS TESTES PASSARAM!${NC}"
    exit 0
else
    PERCENT=$((PASSED * 100 / (PASSED + FAILED)))
    echo -e "${YELLOW}⚠ Taxa de sucesso: ${PERCENT}%${NC}"
    exit 1
fi
