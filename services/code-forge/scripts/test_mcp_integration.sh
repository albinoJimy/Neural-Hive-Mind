#!/bin/bash
# Script de teste manual de integração MCP

set -e

echo "[TEST] Testando integração MCP Tool Catalog..."

# 1. Verificar que MCP Tool Catalog está rodando
echo "[1] Verificando MCP Tool Catalog..."
curl -f http://mcp-tool-catalog:8080/health || {
    echo "[ERRO] MCP Tool Catalog não está disponível"
    exit 1
}

# 2. Listar ferramentas disponíveis
echo "[2] Listando ferramentas MCP..."
curl -s http://mcp-tool-catalog:8080/api/v1/tools | jq '.total'

# 3. Criar execution ticket de teste
echo "[3] Criando execution ticket..."
TICKET_ID=$(uuidgen)
cat > /tmp/test_ticket.json <<EOF
{
  "ticket_id": "$TICKET_ID",
  "task_type": "BUILD",
  "parameters": {
    "artifact_type": "MICROSERVICE",
    "language": "python",
    "service_name": "test-service",
    "description": "Test MCP integration"
  }
}
EOF

# 4. Publicar ticket no Kafka
echo "[4] Publicando ticket no Kafka..."
kafka-console-producer --bootstrap-server kafka:9092 \
  --topic execution.tickets < /tmp/test_ticket.json

# 5. Aguardar processamento (30s)
echo "[5] Aguardando processamento..."
sleep 30

# 6. Verificar resultado no PostgreSQL
echo "[6] Verificando resultado..."
psql -h postgres -U code_forge -d code_forge -c \
  "SELECT pipeline_id, status, metadata->>'mcp_selection_id' 
   FROM pipelines WHERE ticket_id = '$TICKET_ID';"

# 7. Verificar métricas Prometheus
echo "[7] Verificando métricas..."
curl -s http://code-forge:9090/metrics | grep mcp_selection_requests_total

echo "[OK] Teste de integração MCP concluído!"
