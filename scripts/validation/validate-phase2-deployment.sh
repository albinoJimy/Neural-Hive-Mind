#!/bin/bash
# Validação simples do deployment Fase 2

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================="
echo "Validação de Deployment - Fase 2"
echo "=========================================${NC}"

TOTAL_OK=0
TOTAL_FAIL=0

check() {
  if [ $1 -eq 0 ]; then
    echo -e "${GREEN}✓${NC} $2"
    TOTAL_OK=$((TOTAL_OK + 1))
  else
    echo -e "${RED}✗${NC} $2"
    TOTAL_FAIL=$((TOTAL_FAIL + 1))
  fi
}

echo -e "\n${YELLOW}1. Bancos de Dados${NC}"
kubectl get pods -n mongodb-cluster -l app=mongodb --no-headers | grep -q Running && check 0 "MongoDB Running" || check 1 "MongoDB"
kubectl get pods -n neural-hive-temporal -l app=postgresql-temporal --no-headers | grep -q Running && check 0 "PostgreSQL Temporal Running" || check 1 "PostgreSQL Temporal"
kubectl get pods -n neural-hive-orchestration -l app=postgresql-tickets --no-headers | grep -q Running && check 0 "PostgreSQL Tickets Running" || check 1 "PostgreSQL Tickets"

echo -e "\n${YELLOW}2. Temporal Server${NC}"
kubectl get pods -n neural-hive-temporal -l app=temporal-frontend --no-headers | grep -q Running && check 0 "Temporal Frontend Running" || check 1 "Temporal Frontend"
kubectl get pods -n neural-hive-temporal -l app=temporal-history --no-headers | grep -q Running && check 0 "Temporal History Running" || check 1 "Temporal History"
kubectl get pods -n neural-hive-temporal -l app=temporal-matching --no-headers | grep -q Running && check 0 "Temporal Matching Running" || check 1 "Temporal Matching"
kubectl get pods -n neural-hive-temporal -l app=temporal-worker --no-headers | grep -q Running && check 0 "Temporal Worker Running" || check 1 "Temporal Worker"

echo -e "\n${YELLOW}3. Serviços Fase 2 (13 componentes)${NC}"
kubectl get deployments -n neural-hive-orchestration orchestrator-dynamic &>/dev/null && check 0 "orchestrator-dynamic" || check 1 "orchestrator-dynamic"
kubectl get deployments -n neural-hive-service-registry service-registry &>/dev/null && check 0 "service-registry" || check 1 "service-registry"
kubectl get deployments -n neural-hive-orchestration execution-ticket-service &>/dev/null && check 0 "execution-ticket-service" || check 1 "execution-ticket-service"
kubectl get deployments -n neural-hive-queen queen-agent &>/dev/null && check 0 "queen-agent" || check 1 "queen-agent"
kubectl get deployments -n neural-hive-workers worker-agents &>/dev/null && check 0 "worker-agents" || check 1 "worker-agents"
kubectl get deployments -n neural-hive-scouts scout-agents &>/dev/null && check 0 "scout-agents" || check 1 "scout-agents"
kubectl get deployments -n neural-hive-analysts analyst-agents &>/dev/null && check 0 "analyst-agents" || check 1 "analyst-agents"
kubectl get deployments -n neural-hive-optimizers optimizer-agents &>/dev/null && check 0 "optimizer-agents" || check 1 "optimizer-agents"
kubectl get deployments -n neural-hive-guards guard-agents &>/dev/null && check 0 "guard-agents" || check 1 "guard-agents"
kubectl get deployments -n neural-hive-sla sla-management-system &>/dev/null && check 0 "sla-management-system" || check 1 "sla-management-system"
kubectl get deployments -n neural-hive-code-forge code-forge &>/dev/null && check 0 "code-forge" || check 1 "code-forge"
kubectl get deployments -n neural-hive-mcp mcp-tool-catalog &>/dev/null && check 0 "mcp-tool-catalog" || check 1 "mcp-tool-catalog"
kubectl get deployments -n neural-hive-healing self-healing-engine &>/dev/null && check 0 "self-healing-engine" || check 1 "self-healing-engine"

echo -e "\n${YELLOW}4. Infraestrutura Base${NC}"
kubectl get pods -n kafka | grep -q neural-hive-kafka && check 0 "Kafka Running" || check 1 "Kafka"
kubectl get pods -n redis-cluster | grep -q redis && check 0 "Redis Running" || check 1 "Redis"

echo -e "\n${BLUE}========================================="
echo "Resultado Final"
echo "=========================================${NC}"
echo -e "${GREEN}✓ Sucesso: $TOTAL_OK${NC}"
echo -e "${RED}✗ Falha: $TOTAL_FAIL${NC}"

TOTAL=$((TOTAL_OK + TOTAL_FAIL))
SUCCESS_RATE=$((TOTAL_OK * 100 / TOTAL))

echo ""
echo "Taxa de sucesso: ${SUCCESS_RATE}%"

if [ $TOTAL_FAIL -eq 0 ]; then
  echo -e "\n${GREEN}🎉 Todos os componentes estão operacionais!${NC}"
  exit 0
else
  echo -e "\n${YELLOW}⚠ Alguns componentes precisam de atenção${NC}"
  exit 1
fi
