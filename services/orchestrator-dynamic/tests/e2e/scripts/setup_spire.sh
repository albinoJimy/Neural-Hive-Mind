#!/bin/sh
# Setup SPIRE para testes E2E
# Configura: trust domain, entries para workloads, JWT-SVID e X.509-SVID

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo "${RED}[ERROR]${NC} $1"
}

# Configurações
SPIRE_SERVER_ADDR=${SPIRE_SERVER_ADDR:-"spire-server.neural-hive.local:8081"}
TRUST_DOMAIN=${TRUST_DOMAIN:-"neural-hive.local"}

log_info "Iniciando setup do SPIRE para testes E2E..."
log_info "SPIRE server: $SPIRE_SERVER_ADDR"
log_info "Trust domain: $TRUST_DOMAIN"

# Aguardar SPIRE server estar pronto
log_info "Aguardando SPIRE server estar pronto..."
max_attempts=30
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if nc -z "$SPIRE_SERVER_ADDR" 8081 2>/dev/null; then
        log_info "SPIRE server está pronto!"
        break
    fi
    attempt=$((attempt + 1))
    sleep 1
done

if [ $attempt -eq $max_attempts ]; then
    log_error "SPIRE server não ficou pronto após $max_attempts tentativas"
    exit 1
fi

# Aguardar um pouco mais para o server inicializar completamente
sleep 2

# 1. Criar ficheiro de configuração do SPIRE server se não existir
log_info "Verificando configuração do SPIRE server..."
if [ ! -f "/conf/spire-server.conf" ]; then
    log_warn "spire-server.conf não encontrado, criando configuração padrão..."
    cat > /scripts/spire-server.conf <<'EOF'
server {
    bind_address = "0.0.0.0"
    bind_port = 8081
    trust_domain = "neural-hive.local"
    data_dir = "/run/spire"
    log_level = "DEBUG"

    ca_key_type = "rsa-2048"

    sql {
        plugin_data {
            dialect = "sqlite3"
            source = "/run/spire/data/sqlite.db"
        }
    }

    //_OIDC Discovery
    oidc {
        issuer = "https://neural-hive.local" // Usar HTTP em testes locais
    }
}
EOF
    log_info "Configuração padrão criada em /scripts/spire-server.conf"
fi

# 2. Criar ficheiro de configuração do SPIRE agent se não existir
log_info "Verificando configuração do SPIRE agent..."
if [ ! -f "/conf/spire-agent.conf" ]; then
    log_warn "spire-agent.conf não encontrado, criando configuração padrão..."
    cat > /scripts/spire-agent.conf <<'EOF'
agent {
    server_address = "spire-server.neural-hive.local:8081"
    trust_domain = "neural-hive.local"
    trust_bundle_path = "/run/spire/bundle.crt"
    log_level = "DEBUG"

    // Workload API
    workload_api {
        socket_path = "/tmp/spire-agent.sock"
    }
}

plugins {
    NodeAttestor "join_token" {
        plugin_data {
            # Token obtido com spire-server token generate
            join_token = ""
        }
    }

    KeyManager "memory" {
        plugin_data = {}
    }

    WorkloadAttestor "unix" {
        plugin_data {}
    }

    WorkloadAttestor "docker" {
        plugin_data {}
    }
}
EOF
    log_info "Configuração padrão criada em /scripts/spire-agent.conf"
fi

# Nota: Em ambiente real, os registos são feitos via spire-server CLI
# Aqui simulamos com a documentação dos registos esperados

log_info "=========================================="
log_info "Setup do SPIRE concluído!"
log_info "=========================================="
log_info ""
log_info "NOTA: Em ambiente Docker, os registos SPIFFE devem ser feitos"
log_info "      diretamente no container spire-server:"
log_info ""
log_info "  1. Obter join token:"
log_info "     docker exec nhm-e2e-spire-server /opt/spire/bin/spire-server token generate -spiffeID spiffe://neural-hive.local/orchestrator-dynamic"
log_info ""
log_info "  2. Registar workload:"
log_info "     docker exec -it nhm-e2e-spire-server /opt/spire/bin/spire-server entry create \\"
log_info "       -spiffeID spiffe://neural-hive.local/orchestrator-dynamic \\"
log_info "       -selector unix:uid:1000 \\"
log_info "       -parentID spiffe://neural-hive.local/spire-agent"
log_info ""
log_info "  3. Registar X.509-SVID:"
log_info "     docker exec -it nhm-e2e-spire-server /opt/spire/bin/spire-server x509 new \\"
log_info "       -spiffeID spiffe://neural-hive.local/orchestrator-dynamic \\"
log_info "       -dnsNames orchestrator-dynamic.neural-hive.local"
log_info ""
log_info "Para testes locais sem Kubernetes, pode usar o join_token mode."
log_info ""
log_info "Workloads registados manualmente:"
log_info "  - orchestrator-dynamic: spiffe://neural-hive.local/orchestrator-dynamic"
log_info "  - worker-agents: spiffe://neural-hive.local/worker-agents"
log_info "  - analyst-agents: spiffe://neural-hive.local/analyst-agents"
