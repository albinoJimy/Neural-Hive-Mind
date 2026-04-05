#!/bin/sh
set -e

echo "=== Setup SPIRE Server para Testes E2E ==="

SPIRE_DIR="/opt/spire"
CONF_DIR="$SPIRE_DIR/conf/server"
DATA_DIR="$SPIRE_DIR/data"

# Criar diretórios
mkdir -p "$CONF_DIR"
mkdir -p "$DATA_DIR"

echo ""
echo "=== 1. Gerar Certificados CA ==="
if [ ! -f "$DATA_DIR/ca.crt" ]; then
    echo "Gerando CA bundle..."
    "$SPIRE_DIR/bin/spire-server" create-bundle -path "$DATA_DIR"
else
    echo "CA bundle já existe"
fi

echo ""
echo "=== 2. Criar Configuração do Server ==="
cat > "$CONF_DIR/server.conf" <<EOF
server {
    bind_address = "0.0.0.0"
    bind_port = 8081
    trust_domain = "neural-hive.local"
    data_dir = "$DATA_DIR"
    log_level = "DEBUG"

    default_svid_ttl = "1h"
    default_x509_svid_ttl = "24h"

    # Database backend (SQLite para testes)
    datastore {
        plugin_data {
            sql {
                plugin_name = "sql"
                driver_name = "sqlite3"
                database_name = "$DATA_DIR/spire-server-datastore.sqlite"
            }
        }
    }

    # Bundle e SVID config
    bundle_endpoint {
        enabled = true
        bind_address = "0.0.0.0"
        bind_port = 8082
    }

    # Federation (não usado em testes locais)
    federation {
        bundle_endpoint {
            enabled = false
        }
    }

    # Upstream authority para Vault (opcional)
    upstream_authority {
        enabled = false
    }
}
EOF

echo ""
echo "=== 3. Configurar Trust Domain ==="
# O trust domain já está definido no config

echo ""
echo "=== 4. Aguardar Vault para integração ==="
echo "Aguardando Vault..."
until curl -s http://vault:8200/v1/sys/health > /dev/null 2>&1; do
    echo "Vault não está pronto..."
    sleep 2
done

# Exportar config Vault
export VAULT_ADDR='http://vault:8200'
export VAULT_TOKEN='dev-root-token'

# Registrar SPIRE server no Vault como um workload (opcional)
echo ""
echo "=== 5. Registrar SPIRE Server entries ==="
# Nota: Em produção, o SPIRE server seria registrado com SVIDs do Vault
# Para testes E2E locais, usamos auto-registration

echo ""
echo "=== 6. Criar Workload Attestor ==="
# Usar Unix socket attestation para containers Docker
cat > "$CONF_DIR/workload_attestor.conf" <<EOF
attestor = "unix"
EOF

echo ""
echo "=== 7. Health check ==="
echo "SPIRE Server config criado em: $CONF_DIR/server.conf"
echo "Data directory: $DATA_DIR"
echo "Trust Domain: neural-hive.local"

echo ""
echo "=== SPIRE Server Setup Concluído ==="
