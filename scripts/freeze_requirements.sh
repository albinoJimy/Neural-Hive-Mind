#!/bin/bash
# Script para fazer pinning de dependências Python
# Usa versões instaladas para fazer pinning

set -e

echo "# Creating requirements.frozen files with pinned versions"
echo ""

# Mapa de versões com base no pip freeze
FREEZE_VERSIONS="
opentelemetry-api==1.39.1
opentelemetry-sdk==1.39.1
opentelemetry-exporter-otlp-proto-grpc==1.39.1
opentelemetry-instrumentation-fastapi==0.60b1
opentelemetry-instrumentation-grpc==0.60b1
opentelemetry-instrumentation-kafka-python==0.50b0
opentelemetry-exporter-otlp==1.29.0
tenacity==8.5.0
typing_extensions==4.12.2
cryptography==45.0.7
requests==2.32.3
python-json-logger==2.0.7
sqlalchemy==2.0.40
asyncpg==0.29.0
alembic==1.16.5
openai==1.105.0
anthropic==0.66.0
jinja2==3.1.6
gitpython==3.1.45
pyyaml==6.0.4
orjson==3.10.16
python-jose==3.3.0
python-dateutil==2.9.0.post0
aiofiles==23.2.1
boto3==1.37.22
attrs==25.3.0
authlib==1.5.1
aiohttp==3.12.15
grpcio-tools==1.68.1
grpcio-health-checking==1.68.1
redis==5.2.1
numpy==2.2.6
aiokafka==0.10.0
numba==0.62.1
fastmcp==2.1.2
fastapi==0.109.2
uvicorn==0.34.2
pydantic==2.12.5
pydantic-settings==2.7.1
structlog==24.4.0
prometheus-client==0.21.1
neo4j==6.1.0
clickhouse-connect==0.14.1
pytest==7.4.3
pytest-asyncio==0.21.1
dowhy==0.12.0
httpx==0.28.1
aiodocker==0.21.0
aioboto3==11.4.2
"

# Função para processar um arquivo
freeze_file() {
    local input="$1"
    local output="${input}.frozen"

    # Se já existe frozen, skip
    if [ -f "$output" ]; then
        echo "  [SKIP] $output already exists"
        return
    fi

    echo "  [CREATE] $output"

    # Copiar arquivo original
    cp "$input" "$output"

    # Substituir ranges por versões exatas
    while IFS='=' read -r pkg version || [ -n "$pkg" ]; do
        [ -z "$pkg" ] && continue
        [ "$(echo "$pkg" | cut -c1)" = "#" ] && continue

        pkg_name=$(echo "$pkg" | tr -d ' ')

        # Substituir >=, ~=, >, < (preservando comentários inline)
        sed -i "s/^${pkg_name}>=.*/${pkg_name}==${version}/" "$output" 2>/dev/null || true
        sed -i "s/^${pkg_name}~=.*/${pkg_name}==${version}/" "$output" 2>/dev/null || true
        sed -i "s/^${pkg_name}>[^=].*/${pkg_name}==${version}/" "$output" 2>/dev/null || true
        sed -i "s/^${pkg_name}<.*/${pkg_name}==${version}/" "$output" 2>/dev/null || true
    done <<< "$FREEZE_VERSIONS"
}

# Encontrar todos os requirements.txt
find services -name "requirements*.txt" -not -name "*dev*" -not -name "*test*" -not -name "*frozen*" -not -path "*/mlruns/*" | sort | while read -r file; do
    dir=$(dirname "$file")
    base=$(basename "$file")

    # Verificar se há ranges neste arquivo
    if grep -qE "(>=|~=|>|<)" "$file" 2>/dev/null; then
        echo "$file:"
        freeze_file "$file"
    fi
done

echo ""
echo "# Done! Check *.frozen files"
