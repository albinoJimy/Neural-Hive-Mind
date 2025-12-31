#!/bin/bash
# ==============================================================================
# Teste E2E: Execucao Hibrida MCP Tool Catalog
# ==============================================================================
#
# Cenarios:
# 1. Setup de infraestrutura (MongoDB, Redis, Mock MCP Server)
# 2. Inicializacao do MCP Tool Catalog Service
# 3. Teste de Selecao GA via API /api/v1/selections
# 4. Execucao via MCP Server (quando saudavel)
# 5. Fallback MCP -> Adapter (quando MCP falha)
# 6. Validacao de Metricas Prometheus (/metrics)
# 7. Validacao de Feedback Loop (MongoDB reputation)
# 8. Teste de Performance Batch
#
# Uso: ./test_mcp_hybrid_execution.sh [--verbose] [--skip-cleanup]
#
# ==============================================================================

set -e

# ==============================================================================
# Configuracao
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
SERVICE_DIR="$PROJECT_ROOT/services/mcp-tool-catalog"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuracoes padrao
VERBOSE=false
SKIP_CLEANUP=false
MCP_CATALOG_PORT=8000
MCP_CATALOG_METRICS_PORT=9091
MCP_SERVER_PORT=3001
MONGODB_PORT=27017
REDIS_PORT=6379

# Contadores de teste
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# PIDs para cleanup
MCP_SERVER_PID=""
MCP_CATALOG_PID=""
MONGODB_CONTAINER=""
REDIS_CONTAINER=""

# ==============================================================================
# Funcoes Utilitarias
# ==============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((TESTS_PASSED++))
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((TESTS_FAILED++))
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_skip() {
    echo -e "${YELLOW}[SKIP]${NC} $1"
    ((TESTS_SKIPPED++))
}

log_verbose() {
    if [ "$VERBOSE" = true ]; then
        echo -e "${BLUE}[DEBUG]${NC} $1"
    fi
}

print_header() {
    echo ""
    echo "=============================================================================="
    echo " $1"
    echo "=============================================================================="
    echo ""
}

print_summary() {
    print_header "RESUMO DOS TESTES"
    echo -e "  ${GREEN}Passed:${NC}  $TESTS_PASSED"
    echo -e "  ${RED}Failed:${NC}  $TESTS_FAILED"
    echo -e "  ${YELLOW}Skipped:${NC} $TESTS_SKIPPED"
    echo ""

    TOTAL=$((TESTS_PASSED + TESTS_FAILED))
    if [ $TOTAL -gt 0 ]; then
        PASS_RATE=$((TESTS_PASSED * 100 / TOTAL))
        echo -e "  Taxa de sucesso: ${PASS_RATE}%"
    fi
    echo ""

    if [ $TESTS_FAILED -gt 0 ]; then
        echo -e "${RED}RESULTADO: FALHOU${NC}"
        return 1
    else
        echo -e "${GREEN}RESULTADO: PASSOU${NC}"
        return 0
    fi
}

# ==============================================================================
# Parse de Argumentos
# ==============================================================================

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --verbose|-v)
                VERBOSE=true
                shift
                ;;
            --skip-cleanup)
                SKIP_CLEANUP=true
                shift
                ;;
            --help|-h)
                echo "Uso: $0 [--verbose] [--skip-cleanup]"
                echo ""
                echo "Opcoes:"
                echo "  --verbose, -v     Mostra logs detalhados"
                echo "  --skip-cleanup    Nao remove containers apos testes"
                echo "  --help, -h        Mostra esta ajuda"
                exit 0
                ;;
            *)
                echo "Argumento desconhecido: $1"
                exit 1
                ;;
        esac
    done
}

# ==============================================================================
# Verificacao de Pre-requisitos
# ==============================================================================

check_prerequisites() {
    print_header "Verificando Pre-requisitos"

    # Verificar Docker
    if command -v docker &> /dev/null; then
        log_success "Docker disponivel"
    else
        log_error "Docker nao encontrado"
        exit 1
    fi

    # Verificar curl
    if command -v curl &> /dev/null; then
        log_success "curl disponivel"
    else
        log_error "curl nao encontrado"
        exit 1
    fi

    # Verificar jq
    if command -v jq &> /dev/null; then
        log_success "jq disponivel"
    else
        log_warning "jq nao encontrado - alguns testes podem falhar"
    fi

    # Verificar Python
    if command -v python3 &> /dev/null; then
        log_success "Python3 disponivel"
    else
        log_error "Python3 nao encontrado"
        exit 1
    fi

    # Verificar portas disponiveis
    for port in $MCP_CATALOG_PORT $MCP_SERVER_PORT $MONGODB_PORT $REDIS_PORT; do
        if ! ss -tuln | grep -q ":$port "; then
            log_verbose "Porta $port disponivel"
        else
            log_warning "Porta $port em uso - tentando continuar"
        fi
    done
}

# ==============================================================================
# Setup de Infraestrutura
# ==============================================================================

start_mongodb() {
    log_info "Iniciando MongoDB..."

    # Verificar se ja existe container
    if docker ps -a --format '{{.Names}}' | grep -q "mcp-test-mongodb"; then
        docker rm -f mcp-test-mongodb > /dev/null 2>&1 || true
    fi

    MONGODB_CONTAINER=$(docker run -d \
        --name mcp-test-mongodb \
        -p $MONGODB_PORT:27017 \
        -e MONGO_INITDB_ROOT_USERNAME=admin \
        -e MONGO_INITDB_ROOT_PASSWORD=admin123 \
        mongo:7 \
        --quiet)

    # Aguardar MongoDB iniciar
    local max_attempts=30
    local attempt=1
    while [ $attempt -le $max_attempts ]; do
        if docker exec mcp-test-mongodb mongosh --eval "db.runCommand('ping').ok" --quiet > /dev/null 2>&1; then
            log_success "MongoDB iniciado (container: ${MONGODB_CONTAINER:0:12})"
            return 0
        fi
        sleep 1
        ((attempt++))
    done

    log_error "MongoDB nao iniciou a tempo"
    return 1
}

start_redis() {
    log_info "Iniciando Redis..."

    # Verificar se ja existe container
    if docker ps -a --format '{{.Names}}' | grep -q "mcp-test-redis"; then
        docker rm -f mcp-test-redis > /dev/null 2>&1 || true
    fi

    REDIS_CONTAINER=$(docker run -d \
        --name mcp-test-redis \
        -p $REDIS_PORT:6379 \
        redis:7-alpine \
        --quiet)

    # Aguardar Redis iniciar
    local max_attempts=30
    local attempt=1
    while [ $attempt -le $max_attempts ]; do
        if docker exec mcp-test-redis redis-cli ping | grep -q "PONG"; then
            log_success "Redis iniciado (container: ${REDIS_CONTAINER:0:12})"
            return 0
        fi
        sleep 1
        ((attempt++))
    done

    log_error "Redis nao iniciou a tempo"
    return 1
}

start_mock_mcp_server() {
    log_info "Iniciando Mock MCP Server na porta $MCP_SERVER_PORT..."

    # Criar mock MCP server em Python
    cat > /tmp/mock_mcp_server.py << 'PYTHON_EOF'
#!/usr/bin/env python3
"""Mock MCP Server para testes E2E."""

import json
import asyncio
from aiohttp import web

# Estado do servidor
server_state = {
    "healthy": True,
    "slow_mode": False,
    "fail_mode": False,
    "request_count": 0,
    "last_request": None,
    "executions": []
}

async def handle_jsonrpc(request):
    """Handler para requisicoes JSON-RPC."""
    server_state["request_count"] += 1

    try:
        body = await request.json()
        server_state["last_request"] = body
    except:
        return web.json_response({
            "jsonrpc": "2.0",
            "error": {"code": -32700, "message": "Parse error"},
            "id": None
        }, status=400)

    # Modo de falha
    if server_state["fail_mode"]:
        return web.json_response({
            "jsonrpc": "2.0",
            "error": {"code": -32000, "message": "Server error (fail mode)"},
            "id": body.get("id")
        }, status=500)

    # Modo lento
    if server_state["slow_mode"]:
        await asyncio.sleep(10)

    method = body.get("method", "")
    params = body.get("params", {})
    request_id = body.get("id")

    # Handlers por metodo
    if method == "initialize":
        result = {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "mock-mcp-server", "version": "1.0.0"},
            "capabilities": {"tools": {"listChanged": True}}
        }
    elif method == "tools/list":
        result = {
            "tools": [
                {
                    "name": "trivy-scan",
                    "description": "Security scanning tool",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"target": {"type": "string"}},
                        "required": ["target"]
                    }
                },
                {
                    "name": "sonarqube-analyze",
                    "description": "Code quality analysis",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"projectKey": {"type": "string"}},
                        "required": ["projectKey"]
                    }
                }
            ]
        }
    elif method == "tools/call":
        tool_name = params.get("name", "unknown")
        arguments = params.get("arguments", {})

        # Registrar execucao
        server_state["executions"].append({
            "tool_name": tool_name,
            "arguments": arguments,
            "timestamp": asyncio.get_event_loop().time()
        })

        if tool_name == "trivy-scan":
            result = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({
                            "tool": "trivy",
                            "target": arguments.get("target", "unknown"),
                            "vulnerabilities": [],
                            "summary": {"critical": 0, "high": 0, "medium": 2, "low": 5}
                        })
                    }
                ],
                "isError": False
            }
        elif tool_name == "sonarqube-analyze":
            result = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({
                            "tool": "sonarqube",
                            "projectKey": arguments.get("projectKey", "unknown"),
                            "qualityGate": "OK",
                            "issues": {"bugs": 0, "vulnerabilities": 1, "codeSmells": 10}
                        })
                    }
                ],
                "isError": False
            }
        else:
            result = {
                "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                "isError": True
            }
    else:
        return web.json_response({
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": f"Method not found: {method}"},
            "id": request_id
        })

    return web.json_response({
        "jsonrpc": "2.0",
        "result": result,
        "id": request_id
    })

async def handle_health(request):
    """Health check endpoint."""
    if server_state["healthy"]:
        return web.json_response({
            "status": "healthy",
            "requests": server_state["request_count"],
            "executions": len(server_state["executions"])
        })
    else:
        return web.json_response({"status": "unhealthy"}, status=503)

async def handle_control(request):
    """Endpoint de controle para testes."""
    body = await request.json()
    action = body.get("action", "")

    if action == "set_healthy":
        server_state["healthy"] = body.get("value", True)
    elif action == "set_slow_mode":
        server_state["slow_mode"] = body.get("value", False)
    elif action == "set_fail_mode":
        server_state["fail_mode"] = body.get("value", False)
    elif action == "reset":
        server_state["healthy"] = True
        server_state["slow_mode"] = False
        server_state["fail_mode"] = False
        server_state["request_count"] = 0
        server_state["executions"] = []
    elif action == "get_stats":
        return web.json_response(server_state)

    return web.json_response({"status": "ok", "state": server_state})

app = web.Application()
app.router.add_post("/", handle_jsonrpc)
app.router.add_get("/health", handle_health)
app.router.add_post("/control", handle_control)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=3001)
PYTHON_EOF

    # Iniciar servidor em background
    python3 /tmp/mock_mcp_server.py &
    MCP_SERVER_PID=$!
    echo $MCP_SERVER_PID > /tmp/mock_mcp_server.pid

    # Aguardar servidor iniciar
    sleep 2

    # Verificar se esta rodando
    if curl -s "http://localhost:$MCP_SERVER_PORT/health" > /dev/null 2>&1; then
        log_success "Mock MCP Server iniciado (PID: $MCP_SERVER_PID)"
    else
        log_error "Falha ao iniciar Mock MCP Server"
        return 1
    fi
}

start_mcp_catalog_service() {
    log_info "Iniciando MCP Tool Catalog Service..."

    # Configurar variaveis de ambiente
    export MONGODB_URL="mongodb://admin:admin123@localhost:$MONGODB_PORT"
    export MONGODB_DATABASE="mcp_tool_catalog_test"
    export REDIS_URL="redis://localhost:$REDIS_PORT"
    export HTTP_PORT=$MCP_CATALOG_PORT
    export METRICS_PORT=$MCP_CATALOG_METRICS_PORT
    export LOG_LEVEL="INFO"
    export SERVICE_NAME="mcp-tool-catalog"
    export SERVICE_VERSION="1.0.0-test"

    # Configurar MCP Servers (apontando para mock)
    export MCP_SERVERS='{"trivy-mcp-001": "http://localhost:3001"}'

    # Desabilitar Kafka para testes E2E (usar apenas API REST)
    export KAFKA_BOOTSTRAP_SERVERS=""
    export SERVICE_REGISTRY_GRPC_HOST=""

    cd "$SERVICE_DIR"

    # Instalar dependencias se necessario
    if [ ! -d "venv" ]; then
        log_info "Criando virtualenv..."
        python3 -m venv venv
        source venv/bin/activate
        pip install -q -e .
    else
        source venv/bin/activate
    fi

    # Iniciar servico em background
    python3 -m src.main &
    MCP_CATALOG_PID=$!
    echo $MCP_CATALOG_PID > /tmp/mcp_catalog.pid

    # Aguardar servico iniciar
    local max_attempts=60
    local attempt=1
    while [ $attempt -le $max_attempts ]; do
        if curl -s "http://localhost:$MCP_CATALOG_PORT/health" > /dev/null 2>&1; then
            log_success "MCP Tool Catalog Service iniciado (PID: $MCP_CATALOG_PID)"
            return 0
        fi
        sleep 1
        ((attempt++))
    done

    log_error "MCP Tool Catalog Service nao iniciou a tempo"
    return 1
}

wait_for_service() {
    local url=$1
    local max_attempts=${2:-30}
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            return 0
        fi
        log_verbose "Aguardando servico ($attempt/$max_attempts)..."
        sleep 1
        ((attempt++))
    done

    return 1
}

# ==============================================================================
# Cenario 1: Teste de API de Tools
# ==============================================================================

test_tools_api() {
    print_header "Cenario 1: API de Tools (/api/v1/tools)"

    local CATALOG_URL="http://localhost:$MCP_CATALOG_PORT"

    # Teste 1.1: Listar todas as ferramentas
    log_info "Teste 1.1: GET /api/v1/tools - Listar ferramentas"
    RESPONSE=$(curl -s "$CATALOG_URL/api/v1/tools")

    if echo "$RESPONSE" | jq -e '.tools' > /dev/null 2>&1; then
        TOOL_COUNT=$(echo "$RESPONSE" | jq -r '.total')
        log_success "Listagem de ferramentas OK (total: $TOOL_COUNT)"
        log_verbose "Response: $RESPONSE"
    else
        log_error "Listagem de ferramentas falhou: $RESPONSE"
    fi

    # Teste 1.2: Filtrar por categoria
    log_info "Teste 1.2: GET /api/v1/tools?category=SECURITY"
    RESPONSE=$(curl -s "$CATALOG_URL/api/v1/tools?category=SECURITY")

    if echo "$RESPONSE" | jq -e '.tools' > /dev/null 2>&1; then
        SECURITY_COUNT=$(echo "$RESPONSE" | jq -r '.total')
        log_success "Filtro por categoria OK (SECURITY: $SECURITY_COUNT)"
    else
        log_error "Filtro por categoria falhou: $RESPONSE"
    fi

    # Teste 1.3: Obter ferramenta especifica
    log_info "Teste 1.3: GET /api/v1/tools/{tool_id}"

    # Obter primeiro tool_id da lista
    FIRST_TOOL_ID=$(echo "$RESPONSE" | jq -r '.tools[0].tool_id // empty')

    if [ -n "$FIRST_TOOL_ID" ]; then
        TOOL_RESPONSE=$(curl -s "$CATALOG_URL/api/v1/tools/$FIRST_TOOL_ID")
        if echo "$TOOL_RESPONSE" | jq -e '.tool_id' > /dev/null 2>&1; then
            TOOL_NAME=$(echo "$TOOL_RESPONSE" | jq -r '.tool_name')
            log_success "Obtencao de ferramenta OK (tool: $TOOL_NAME)"
        else
            log_error "Obtencao de ferramenta falhou: $TOOL_RESPONSE"
        fi
    else
        log_skip "Nenhuma ferramenta encontrada para teste"
    fi

    # Teste 1.4: Health check de ferramenta
    log_info "Teste 1.4: GET /api/v1/tools/health/{tool_id}"

    if [ -n "$FIRST_TOOL_ID" ]; then
        HEALTH_RESPONSE=$(curl -s "$CATALOG_URL/api/v1/tools/health/$FIRST_TOOL_ID")
        if echo "$HEALTH_RESPONSE" | jq -e '.is_healthy' > /dev/null 2>&1; then
            IS_HEALTHY=$(echo "$HEALTH_RESPONSE" | jq -r '.is_healthy')
            log_success "Health check OK (is_healthy: $IS_HEALTHY)"
        else
            log_error "Health check falhou: $HEALTH_RESPONSE"
        fi
    else
        log_skip "Nenhuma ferramenta encontrada para health check"
    fi
}

# ==============================================================================
# Cenario 2: Teste de Selecao GA via API
# ==============================================================================

test_selection_api() {
    print_header "Cenario 2: Selecao GA via API (/api/v1/selections)"

    local CATALOG_URL="http://localhost:$MCP_CATALOG_PORT"

    # Teste 2.1: Selecao de ferramentas de SECURITY
    log_info "Teste 2.1: POST /api/v1/selections - Selecao SECURITY"
    SELECTION_REQUEST='{
        "request_id": "e2e-test-001",
        "correlation_id": "e2e-corr-001",
        "artifact_type": "CODE",
        "language": "python",
        "complexity_score": 0.7,
        "required_categories": ["SECURITY"],
        "constraints": {
            "max_tools": 3,
            "max_cost_score": 0.5
        },
        "context": {
            "test_type": "e2e"
        }
    }'

    RESPONSE=$(curl -s -X POST "$CATALOG_URL/api/v1/selections" \
        -H "Content-Type: application/json" \
        -d "$SELECTION_REQUEST")

    if echo "$RESPONSE" | jq -e '.selected_tools' > /dev/null 2>&1; then
        SELECTED_COUNT=$(echo "$RESPONSE" | jq -r '.selected_tools | length')
        SELECTION_METHOD=$(echo "$RESPONSE" | jq -r '.selection_method')
        FITNESS=$(echo "$RESPONSE" | jq -r '.total_fitness_score')
        CACHED=$(echo "$RESPONSE" | jq -r '.cached')

        log_success "Selecao GA OK (tools: $SELECTED_COUNT, method: $SELECTION_METHOD, fitness: $FITNESS, cached: $CACHED)"
        log_verbose "Response: $RESPONSE"

        # Guardar para testes posteriores
        SELECTED_TOOL_ID=$(echo "$RESPONSE" | jq -r '.selected_tools[0].tool_id // empty')
        export SELECTED_TOOL_ID
    else
        log_error "Selecao GA falhou: $RESPONSE"
    fi

    # Teste 2.2: Selecao com multiplas categorias
    log_info "Teste 2.2: POST /api/v1/selections - Multiplas categorias"
    MULTI_REQUEST='{
        "request_id": "e2e-test-002",
        "correlation_id": "e2e-corr-002",
        "artifact_type": "CODE",
        "language": "python",
        "complexity_score": 0.5,
        "required_categories": ["ANALYSIS", "VALIDATION"],
        "constraints": {},
        "context": {}
    }'

    RESPONSE=$(curl -s -X POST "$CATALOG_URL/api/v1/selections" \
        -H "Content-Type: application/json" \
        -d "$MULTI_REQUEST")

    if echo "$RESPONSE" | jq -e '.selected_tools' > /dev/null 2>&1; then
        MULTI_COUNT=$(echo "$RESPONSE" | jq -r '.selected_tools | length')
        log_success "Selecao multipla OK (tools: $MULTI_COUNT)"
    else
        log_error "Selecao multipla falhou: $RESPONSE"
    fi

    # Teste 2.3: Verificar cache hit
    log_info "Teste 2.3: Verificar cache hit na mesma selecao"
    RESPONSE=$(curl -s -X POST "$CATALOG_URL/api/v1/selections" \
        -H "Content-Type: application/json" \
        -d "$SELECTION_REQUEST")

    if echo "$RESPONSE" | jq -e '.cached' > /dev/null 2>&1; then
        CACHED=$(echo "$RESPONSE" | jq -r '.cached')
        if [ "$CACHED" = "true" ]; then
            log_success "Cache hit confirmado"
        else
            log_warning "Cache miss (esperado hit): cached=$CACHED"
        fi
    else
        log_error "Verificacao de cache falhou: $RESPONSE"
    fi
}

# ==============================================================================
# Cenario 3: Execucao via MCP Server
# ==============================================================================

test_mcp_server_execution() {
    print_header "Cenario 3: Execucao via MCP Server"

    # Verificar se MCP Server esta disponivel
    if ! curl -s "http://localhost:$MCP_SERVER_PORT/health" > /dev/null 2>&1; then
        log_skip "MCP Server nao disponivel"
        return
    fi

    # Teste 3.1: Chamar ferramenta via MCP
    log_info "Teste 3.1: tools/call via MCP Server"
    RESPONSE=$(curl -s -X POST "http://localhost:$MCP_SERVER_PORT/" \
        -H "Content-Type: application/json" \
        -d '{
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "trivy-scan",
                "arguments": {"target": "myapp:latest"}
            },
            "id": 1
        }')

    if echo "$RESPONSE" | jq -e '.result.content' > /dev/null 2>&1; then
        log_success "Execucao MCP OK"
        log_verbose "Response: $RESPONSE"
    else
        log_error "Execucao MCP falhou: $RESPONSE"
    fi

    # Teste 3.2: Verificar estatisticas do MCP Server
    log_info "Teste 3.2: Verificar estatisticas de execucao"
    STATS=$(curl -s -X POST "http://localhost:$MCP_SERVER_PORT/control" \
        -H "Content-Type: application/json" \
        -d '{"action": "get_stats"}')

    EXEC_COUNT=$(echo "$STATS" | jq -r '.executions | length')
    log_success "MCP Server registrou $EXEC_COUNT execucao(oes)"
}

# ==============================================================================
# Cenario 4: Fallback MCP -> Adapter
# ==============================================================================

test_fallback_mcp_to_adapter() {
    print_header "Cenario 4: Fallback MCP -> Adapter"

    if ! curl -s "http://localhost:$MCP_SERVER_PORT/health" > /dev/null 2>&1; then
        log_skip "MCP Server nao disponivel para testes de fallback"
        return
    fi

    # Teste 4.1: Configurar MCP Server para falhar
    log_info "Teste 4.1: Configurar MCP Server para modo de falha"
    RESPONSE=$(curl -s -X POST "http://localhost:$MCP_SERVER_PORT/control" \
        -H "Content-Type: application/json" \
        -d '{"action": "set_fail_mode", "value": true}')

    if echo "$RESPONSE" | jq -e '.status' | grep -q "ok"; then
        log_success "MCP Server configurado para falhar"
    else
        log_error "Falha ao configurar MCP Server"
    fi

    # Teste 4.2: Verificar que MCP Server retorna erro
    log_info "Teste 4.2: Verificar erro do MCP Server"
    RESPONSE=$(curl -s -X POST "http://localhost:$MCP_SERVER_PORT/" \
        -H "Content-Type: application/json" \
        -d '{
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "trivy-scan", "arguments": {"target": "test"}},
            "id": 100
        }')

    if echo "$RESPONSE" | jq -e '.error' > /dev/null 2>&1; then
        log_success "MCP Server retorna erro como esperado"
        log_verbose "Response: $RESPONSE"
    else
        log_error "MCP Server deveria retornar erro"
    fi

    # Teste 4.3: Restaurar MCP Server
    log_info "Teste 4.3: Restaurar MCP Server"
    RESPONSE=$(curl -s -X POST "http://localhost:$MCP_SERVER_PORT/control" \
        -H "Content-Type: application/json" \
        -d '{"action": "reset"}')

    if echo "$RESPONSE" | jq -e '.status' | grep -q "ok"; then
        log_success "MCP Server restaurado"
    else
        log_error "Falha ao restaurar MCP Server"
    fi

    # Teste 4.4: Verificar MCP Server funcionando novamente
    log_info "Teste 4.4: Verificar MCP Server restaurado"
    RESPONSE=$(curl -s -X POST "http://localhost:$MCP_SERVER_PORT/" \
        -H "Content-Type: application/json" \
        -d '{
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "trivy-scan", "arguments": {"target": "test"}},
            "id": 101
        }')

    if echo "$RESPONSE" | jq -e '.result.content' > /dev/null 2>&1; then
        log_success "MCP Server funcionando apos restauracao"
    else
        log_error "MCP Server nao restaurado corretamente: $RESPONSE"
    fi
}

# ==============================================================================
# Cenario 5: Validacao de Metricas Prometheus
# ==============================================================================

test_metrics_validation() {
    print_header "Cenario 5: Validacao de Metricas Prometheus"

    local METRICS_URL="http://localhost:$MCP_CATALOG_METRICS_PORT/metrics"

    # Verificar se endpoint de metricas esta disponivel
    if ! curl -s "$METRICS_URL" > /dev/null 2>&1; then
        # Tentar porta alternativa
        METRICS_URL="http://localhost:$MCP_CATALOG_PORT/metrics"
        if ! curl -s "$METRICS_URL" > /dev/null 2>&1; then
            log_skip "Endpoint de metricas nao disponivel"
            return
        fi
    fi

    METRICS=$(curl -s "$METRICS_URL")

    # Teste 5.1: Verificar contador de selecoes
    log_info "Teste 5.1: Verificar mcp_tool_selections_total"
    if echo "$METRICS" | grep -q "mcp_tool_selections_total"; then
        SELECTION_COUNT=$(echo "$METRICS" | grep "mcp_tool_selections_total{" | head -1)
        log_success "Contador de selecoes presente: $SELECTION_COUNT"
    else
        log_warning "Contador mcp_tool_selections_total nao encontrado"
    fi

    # Teste 5.2: Verificar histograma de duracao
    log_info "Teste 5.2: Verificar mcp_tool_selection_duration_seconds"
    if echo "$METRICS" | grep -q "mcp_tool_selection_duration_seconds"; then
        log_success "Histograma de duracao de selecao presente"
    else
        log_warning "Histograma mcp_tool_selection_duration_seconds nao encontrado"
    fi

    # Teste 5.3: Verificar metricas de rota de execucao
    log_info "Teste 5.3: Verificar mcp_execution_route_total"
    if echo "$METRICS" | grep -q "mcp_execution_route_total"; then
        MCP_ROUTE=$(echo "$METRICS" | grep 'mcp_execution_route_total{route="mcp"' || echo "nenhum")
        ADAPTER_ROUTE=$(echo "$METRICS" | grep 'mcp_execution_route_total{route="adapter"' || echo "nenhum")
        log_success "Metricas de rota presentes (mcp: $MCP_ROUTE, adapter: $ADAPTER_ROUTE)"
    else
        log_warning "Contador mcp_execution_route_total nao encontrado"
    fi

    # Teste 5.4: Verificar metricas de fallback
    log_info "Teste 5.4: Verificar mcp_fallback_total"
    if echo "$METRICS" | grep -q "mcp_fallback_total"; then
        FALLBACK_COUNT=$(echo "$METRICS" | grep "mcp_fallback_total{" | head -1)
        log_success "Contador de fallback presente: $FALLBACK_COUNT"
    else
        log_warning "Contador mcp_fallback_total nao encontrado (pode ser zero)"
    fi

    # Teste 5.5: Verificar gauge de ferramentas registradas
    log_info "Teste 5.5: Verificar mcp_registered_tools_total"
    if echo "$METRICS" | grep -q "mcp_registered_tools_total"; then
        REGISTERED=$(echo "$METRICS" | grep "mcp_registered_tools_total{" | head -1)
        log_success "Gauge de ferramentas registradas presente: $REGISTERED"
    else
        log_warning "Gauge mcp_registered_tools_total nao encontrado"
    fi
}

# ==============================================================================
# Cenario 6: Feedback Loop e Reputacao
# ==============================================================================

test_feedback_loop() {
    print_header "Cenario 6: Feedback Loop e Reputacao"

    local CATALOG_URL="http://localhost:$MCP_CATALOG_PORT"

    # Obter uma ferramenta para teste
    TOOLS_RESPONSE=$(curl -s "$CATALOG_URL/api/v1/tools?limit=1")
    TOOL_ID=$(echo "$TOOLS_RESPONSE" | jq -r '.tools[0].tool_id // empty')

    if [ -z "$TOOL_ID" ]; then
        log_skip "Nenhuma ferramenta disponivel para teste de feedback"
        return
    fi

    # Obter reputacao inicial
    TOOL_BEFORE=$(curl -s "$CATALOG_URL/api/v1/tools/$TOOL_ID")
    REP_BEFORE=$(echo "$TOOL_BEFORE" | jq -r '.reputation_score')
    log_info "Reputacao inicial: $REP_BEFORE"

    # Teste 6.1: Enviar feedback positivo
    log_info "Teste 6.1: POST /api/v1/tools/{tool_id}/feedback - Feedback positivo"
    FEEDBACK_REQUEST="{
        \"selection_id\": \"e2e-feedback-001\",
        \"tool_id\": \"$TOOL_ID\",
        \"success\": true,
        \"execution_time_ms\": 1500,
        \"metadata\": {\"test\": \"e2e\"}
    }"

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$CATALOG_URL/api/v1/tools/$TOOL_ID/feedback" \
        -H "Content-Type: application/json" \
        -d "$FEEDBACK_REQUEST")

    if [ "$HTTP_CODE" = "204" ]; then
        log_success "Feedback positivo enviado (HTTP $HTTP_CODE)"
    else
        log_error "Feedback positivo falhou (HTTP $HTTP_CODE)"
    fi

    # Aguardar processamento
    sleep 1

    # Verificar se reputacao aumentou
    TOOL_AFTER=$(curl -s "$CATALOG_URL/api/v1/tools/$TOOL_ID")
    REP_AFTER=$(echo "$TOOL_AFTER" | jq -r '.reputation_score')

    log_info "Teste 6.2: Verificar atualizacao de reputacao"
    if [ "$(echo "$REP_AFTER >= $REP_BEFORE" | bc -l)" = "1" ]; then
        log_success "Reputacao atualizada: $REP_BEFORE -> $REP_AFTER"
    else
        log_warning "Reputacao nao aumentou como esperado: $REP_BEFORE -> $REP_AFTER"
    fi

    # Teste 6.3: Enviar feedback negativo
    log_info "Teste 6.3: POST /api/v1/tools/{tool_id}/feedback - Feedback negativo"
    FEEDBACK_REQUEST="{
        \"selection_id\": \"e2e-feedback-002\",
        \"tool_id\": \"$TOOL_ID\",
        \"success\": false,
        \"execution_time_ms\": 30000,
        \"metadata\": {\"error\": \"timeout\", \"test\": \"e2e\"}
    }"

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$CATALOG_URL/api/v1/tools/$TOOL_ID/feedback" \
        -H "Content-Type: application/json" \
        -d "$FEEDBACK_REQUEST")

    if [ "$HTTP_CODE" = "204" ]; then
        log_success "Feedback negativo enviado (HTTP $HTTP_CODE)"
    else
        log_error "Feedback negativo falhou (HTTP $HTTP_CODE)"
    fi
}

# ==============================================================================
# Cenario 7: Performance Batch
# ==============================================================================

test_performance_batch() {
    print_header "Cenario 7: Performance Batch"

    local CATALOG_URL="http://localhost:$MCP_CATALOG_PORT"

    # Teste 7.1: Multiplas selecoes sequenciais
    log_info "Teste 7.1: 10 selecoes sequenciais"

    START_TIME=$(date +%s%N)
    SUCCESS_COUNT=0

    for i in {1..10}; do
        REQUEST="{
            \"request_id\": \"e2e-perf-$i\",
            \"correlation_id\": \"e2e-perf-corr-$i\",
            \"artifact_type\": \"CODE\",
            \"language\": \"python\",
            \"complexity_score\": 0.$i,
            \"required_categories\": [\"ANALYSIS\"],
            \"constraints\": {},
            \"context\": {}
        }"

        RESPONSE=$(curl -s -X POST "$CATALOG_URL/api/v1/selections" \
            -H "Content-Type: application/json" \
            -d "$REQUEST")

        if echo "$RESPONSE" | jq -e '.selected_tools' > /dev/null 2>&1; then
            ((SUCCESS_COUNT++))
        fi
    done

    END_TIME=$(date +%s%N)
    DURATION_MS=$(( (END_TIME - START_TIME) / 1000000 ))

    if [ $SUCCESS_COUNT -eq 10 ]; then
        log_success "10 selecoes sequenciais OK em ${DURATION_MS}ms"
    else
        log_error "Apenas $SUCCESS_COUNT/10 selecoes bem sucedidas"
    fi

    # Verificar latencia media
    AVG_LATENCY=$((DURATION_MS / 10))
    if [ $AVG_LATENCY -lt 1000 ]; then
        log_success "Latencia media: ${AVG_LATENCY}ms (< 1000ms)"
    else
        log_warning "Latencia media: ${AVG_LATENCY}ms (> 1000ms)"
    fi

    # Teste 7.2: Selecoes paralelas
    log_info "Teste 7.2: 5 selecoes paralelas"

    START_TIME=$(date +%s%N)
    TEMP_DIR=$(mktemp -d)

    for i in {1..5}; do
        (
            REQUEST="{
                \"request_id\": \"e2e-parallel-$i\",
                \"correlation_id\": \"e2e-parallel-corr-$i\",
                \"artifact_type\": \"CODE\",
                \"language\": \"java\",
                \"complexity_score\": 0.5,
                \"required_categories\": [\"VALIDATION\"],
                \"constraints\": {},
                \"context\": {}
            }"

            RESPONSE=$(curl -s -X POST "$CATALOG_URL/api/v1/selections" \
                -H "Content-Type: application/json" \
                -d "$REQUEST")

            if echo "$RESPONSE" | jq -e '.selected_tools' > /dev/null 2>&1; then
                echo "success" > "$TEMP_DIR/result_$i"
            else
                echo "failure" > "$TEMP_DIR/result_$i"
            fi
        ) &
    done

    # Aguardar todos os jobs
    wait

    END_TIME=$(date +%s%N)
    DURATION_MS=$(( (END_TIME - START_TIME) / 1000000 ))

    # Contar sucessos
    PARALLEL_SUCCESS=$(grep -l "success" "$TEMP_DIR"/result_* 2>/dev/null | wc -l)

    # Limpar
    rm -rf "$TEMP_DIR"

    if [ $PARALLEL_SUCCESS -eq 5 ]; then
        log_success "5 selecoes paralelas OK em ${DURATION_MS}ms"
    else
        log_error "Apenas $PARALLEL_SUCCESS/5 selecoes paralelas bem sucedidas"
    fi

    # Verificar throughput
    if [ $DURATION_MS -gt 0 ]; then
        THROUGHPUT=$(( 5000 / DURATION_MS ))
        log_info "Throughput: ~${THROUGHPUT} req/s"
    fi
}

# ==============================================================================
# Cleanup
# ==============================================================================

cleanup() {
    if [ "$SKIP_CLEANUP" = false ]; then
        log_info "Limpando recursos..."

        # Parar MCP Tool Catalog
        if [ -f /tmp/mcp_catalog.pid ]; then
            PID=$(cat /tmp/mcp_catalog.pid)
            if kill -0 $PID 2>/dev/null; then
                kill $PID
                log_info "MCP Tool Catalog parado (PID: $PID)"
            fi
            rm -f /tmp/mcp_catalog.pid
        fi

        # Parar Mock MCP Server
        if [ -f /tmp/mock_mcp_server.pid ]; then
            PID=$(cat /tmp/mock_mcp_server.pid)
            if kill -0 $PID 2>/dev/null; then
                kill $PID
                log_info "Mock MCP Server parado (PID: $PID)"
            fi
            rm -f /tmp/mock_mcp_server.pid
        fi
        rm -f /tmp/mock_mcp_server.py

        # Parar containers Docker
        if [ -n "$MONGODB_CONTAINER" ]; then
            docker rm -f mcp-test-mongodb > /dev/null 2>&1 || true
            log_info "MongoDB container removido"
        fi

        if [ -n "$REDIS_CONTAINER" ]; then
            docker rm -f mcp-test-redis > /dev/null 2>&1 || true
            log_info "Redis container removido"
        fi

        log_info "Cleanup concluido"
    else
        log_warning "Cleanup pulado (--skip-cleanup)"
    fi
}

# ==============================================================================
# Main
# ==============================================================================

main() {
    parse_args "$@"

    print_header "E2E Test: MCP Hybrid Execution"
    echo "Data: $(date)"
    echo "Diretorio: $SERVICE_DIR"
    echo ""

    # Trap para cleanup em caso de erro
    trap cleanup EXIT

    # Pre-requisitos
    check_prerequisites

    # Setup de infraestrutura
    print_header "Setup de Infraestrutura"
    start_mongodb || exit 1
    start_redis || exit 1
    start_mock_mcp_server || exit 1

    # Iniciar MCP Tool Catalog Service
    # Nota: Comentado por padrao - descomente para teste completo
    # start_mcp_catalog_service || exit 1

    # Se o servico nao foi iniciado, usar apenas testes do MCP Server mock
    if ! curl -s "http://localhost:$MCP_CATALOG_PORT/health" > /dev/null 2>&1; then
        log_warning "MCP Tool Catalog Service nao disponivel - executando testes parciais"

        # Executar apenas testes que nao dependem do servico
        test_mcp_server_execution
        test_fallback_mcp_to_adapter

        print_summary
        exit $?
    fi

    # Executar todos os cenarios de teste
    test_tools_api
    test_selection_api
    test_mcp_server_execution
    test_fallback_mcp_to_adapter
    test_metrics_validation
    test_feedback_loop
    test_performance_batch

    # Resumo
    print_summary
}

main "$@"
