#!/bin/bash

echo "======================================="
echo "Neural Hive-Mind Integration Test"
echo "======================================="

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Função para verificar status
check_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $2"
        return 0
    else
        echo -e "${RED}✗${NC} $2"
        return 1
    fi
}

# 1. Verificar pods
echo -e "\n${YELLOW}1. Verificando status dos pods...${NC}"

kafka_ready=$(kubectl get pods -n neural-hive-orchestration --no-headers 2>/dev/null | grep -c "Running")
redis_ready=$(kubectl get pods -n redis-cluster --no-headers 2>/dev/null | grep -c "Running")
gateway_ready=$(kubectl get pods -n gateway-test --no-headers 2>/dev/null | grep -c "Running")

echo "   Kafka pods rodando: $kafka_ready"
echo "   Redis pods rodando: $redis_ready"
echo "   Gateway pods rodando: $gateway_ready"

# 2. Testar conectividade com Kafka
echo -e "\n${YELLOW}2. Testando conectividade com Kafka...${NC}"

# Criar pod de teste temporário
kubectl run kafka-test --image=busybox --restart=Never -n neural-hive-orchestration \
    --command -- sh -c "nc -zv kafka.neural-hive-orchestration.svc.cluster.local 9092" \
    2>/dev/null

sleep 5

kafka_test=$(kubectl logs kafka-test -n neural-hive-orchestration 2>/dev/null | grep -c "open")
kubectl delete pod kafka-test -n neural-hive-orchestration --force --grace-period=0 2>/dev/null

check_status $kafka_test "Conexão com Kafka"

# 3. Testar conectividade com Redis
echo -e "\n${YELLOW}3. Testando conectividade com Redis...${NC}"

kubectl run redis-test --image=busybox --restart=Never -n redis-cluster \
    --command -- sh -c "nc -zv redis-master.redis-cluster.svc.cluster.local 6379" \
    2>/dev/null

sleep 5

redis_test=$(kubectl logs redis-test -n redis-cluster 2>/dev/null | grep -c "open")
kubectl delete pod redis-test -n redis-cluster --force --grace-period=0 2>/dev/null

check_status $redis_test "Conexão com Redis"

# 4. Criar tópico no Kafka
echo -e "\n${YELLOW}4. Criando tópico de teste no Kafka...${NC}"

kubectl run kafka-client --restart='Never' \
    --image docker.io/bitnami/kafka:4.0.0-debian-12-r10 \
    --namespace neural-hive-orchestration \
    --command -- sh -c "kafka-topics.sh --create --topic test-integration \
        --bootstrap-server kafka.neural-hive-orchestration.svc.cluster.local:9092 \
        --partitions 3 --replication-factor 1" \
    2>/dev/null

sleep 5

topic_created=$(kubectl logs kafka-client -n neural-hive-orchestration 2>/dev/null | grep -c "Created topic")
kubectl delete pod kafka-client -n neural-hive-orchestration --force --grace-period=0 2>/dev/null

check_status $topic_created "Tópico criado no Kafka"

# 5. Testar publicação de mensagem
echo -e "\n${YELLOW}5. Testando publicação de mensagem no Kafka...${NC}"

kubectl run kafka-producer --restart='Never' \
    --image docker.io/bitnami/kafka:4.0.0-debian-12-r10 \
    --namespace neural-hive-orchestration \
    --command -- sh -c "echo 'Test message from integration test' | \
        kafka-console-producer.sh \
        --bootstrap-server kafka.neural-hive-orchestration.svc.cluster.local:9092 \
        --topic test-integration" \
    2>/dev/null

sleep 5

producer_success=$(kubectl logs kafka-producer -n neural-hive-orchestration 2>/dev/null | wc -l)
kubectl delete pod kafka-producer -n neural-hive-orchestration --force --grace-period=0 2>/dev/null

if [ $producer_success -eq 0 ]; then
    check_status 0 "Mensagem publicada no Kafka"
else
    check_status 1 "Falha ao publicar mensagem"
fi

# 6. Testar Redis
echo -e "\n${YELLOW}6. Testando operações no Redis...${NC}"

kubectl run redis-client --restart='Never' \
    --image docker.io/bitnami/redis:8.2.1-debian-12-r0 \
    --namespace redis-cluster \
    --command -- sh -c "redis-cli -h redis-master.redis-cluster.svc.cluster.local \
        SET test-key 'integration-test-value' && \
        redis-cli -h redis-master.redis-cluster.svc.cluster.local GET test-key" \
    2>/dev/null

sleep 5

redis_result=$(kubectl logs redis-client -n redis-cluster 2>/dev/null | grep -c "integration-test-value")
kubectl delete pod redis-client -n redis-cluster --force --grace-period=0 2>/dev/null

check_status $redis_result "Operações Redis (SET/GET)"

# 7. Resumo
echo -e "\n${YELLOW}=======================================${NC}"
echo -e "${YELLOW}Resumo dos Testes de Integração${NC}"
echo -e "${YELLOW}=======================================${NC}"

total_tests=6
passed_tests=0

[ $kafka_test -eq 1 ] && passed_tests=$((passed_tests + 1))
[ $redis_test -eq 1 ] && passed_tests=$((passed_tests + 1))
[ $topic_created -eq 1 ] && passed_tests=$((passed_tests + 1))
[ $producer_success -eq 0 ] && passed_tests=$((passed_tests + 1))
[ $redis_result -eq 1 ] && passed_tests=$((passed_tests + 1))
[ $gateway_ready -gt 0 ] && passed_tests=$((passed_tests + 1))

if [ $passed_tests -eq $total_tests ]; then
    echo -e "${GREEN}✓ Todos os testes passaram! ($passed_tests/$total_tests)${NC}"
    exit 0
else
    echo -e "${RED}✗ Alguns testes falharam. ($passed_tests/$total_tests passaram)${NC}"
    echo -e "${YELLOW}Verifique os logs dos pods para mais detalhes.${NC}"
    exit 1
fi