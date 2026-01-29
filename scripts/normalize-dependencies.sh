#!/bin/bash
# =============================================================================
# Neural Hive-Mind - Normalização de Dependências
# =============================================================================
# Este script normaliza TODAS as versões de dependências em todo o projeto
# para garantir consistência e evitar conflitos de build.
# =============================================================================

set -e

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_DIR="/jimy/Neural-Hive-Mind"

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

# =============================================================================
# VERSÕES CANÔNICAS - FONTE DE VERDADE
# =============================================================================
# IMPORTANTE: grpcio-tools 1.75.1 requer protobuf>=6.31.1
# Atualizado em: 2025-12-18

# Core Web Framework
FASTAPI_VERSION="0.115.6"
UVICORN_VERSION="0.34.0"
PYDANTIC_VERSION="2.10.4"
PYDANTIC_SETTINGS_VERSION="2.7.1"

# gRPC Stack (CRÍTICO: versões devem ser compatíveis)
GRPCIO_VERSION="1.68.1"
GRPCIO_TOOLS_VERSION="1.68.1"
GRPCIO_HEALTH_VERSION="1.68.1"
GRPCIO_REFLECTION_VERSION="1.68.1"
PROTOBUF_VERSION="5.29.2"  # Compatível com grpcio-tools 1.68.1

# Kafka/Messaging
CONFLUENT_KAFKA_VERSION="2.6.1"
AIOKAFKA_VERSION="0.12.0"
FASTAVRO_VERSION="1.9.7"

# Observability - OpenTelemetry
OTEL_VERSION="1.29.0"
OTEL_INSTRUMENTATION_VERSION="0.50b0"

# Logging
STRUCTLOG_VERSION="24.4.0"
PROMETHEUS_CLIENT_VERSION="0.21.1"

# HTTP Clients
HTTPX_VERSION="0.28.1"
AIOHTTP_VERSION="3.11.11"

# Databases
REDIS_VERSION="5.2.1"
PYMONGO_VERSION="4.10.1"
MOTOR_VERSION="3.6.0"

# Data Science
NUMPY_VERSION="1.26.4"
PANDAS_VERSION="2.2.3"
SCIPY_VERSION="1.14.1"
SCIKIT_LEARN_VERSION="1.6.0"

# ML/AI
MLFLOW_VERSION="2.19.0"
TORCH_VERSION="2.5.1"
SENTENCE_TRANSFORMERS_VERSION="3.3.1"

# Utils
PYTHON_DOTENV_VERSION="1.0.1"
TENACITY_VERSION="9.0.0"
CACHETOOLS_VERSION="5.5.0"

# =============================================================================
# FUNÇÕES DE NORMALIZAÇÃO
# =============================================================================

normalize_file() {
    local file=$1
    local backup="${file}.bak"

    if [ ! -f "$file" ]; then
        return
    fi

    log_info "Normalizando: $file"

    # Criar backup
    cp "$file" "$backup"

    # Aplicar substituições
    sed -i \
        -e "s/fastapi[>=<]*[0-9.]*/fastapi==${FASTAPI_VERSION}/g" \
        -e "s/uvicorn\[standard\][>=<]*[0-9.]*/uvicorn[standard]==${UVICORN_VERSION}/g" \
        -e "s/uvicorn[>=<]*[0-9.]*/uvicorn==${UVICORN_VERSION}/g" \
        -e "s/pydantic\[email\][>=<]*[0-9.]*/pydantic[email]==${PYDANTIC_VERSION}/g" \
        -e "s/pydantic[>=<]*[0-9.]*/pydantic==${PYDANTIC_VERSION}/g" \
        -e "s/pydantic-settings[>=<]*[0-9.]*/pydantic-settings==${PYDANTIC_SETTINGS_VERSION}/g" \
        -e "s/grpcio-tools[>=<]*[0-9.]*/grpcio-tools==${GRPCIO_TOOLS_VERSION}/g" \
        -e "s/grpcio-health-checking[>=<]*[0-9.]*/grpcio-health-checking==${GRPCIO_HEALTH_VERSION}/g" \
        -e "s/grpcio-reflection[>=<]*[0-9.]*/grpcio-reflection==${GRPCIO_REFLECTION_VERSION}/g" \
        -e "s/grpcio[>=<]*[0-9.]*/grpcio==${GRPCIO_VERSION}/g" \
        -e "s/protobuf[>=<]*[0-9.]*/protobuf==${PROTOBUF_VERSION}/g" \
        -e "s/confluent-kafka\[avro\][>=<]*[0-9.]*/confluent-kafka[avro]==${CONFLUENT_KAFKA_VERSION}/g" \
        -e "s/confluent-kafka[>=<]*[0-9.]*/confluent-kafka==${CONFLUENT_KAFKA_VERSION}/g" \
        -e "s/aiokafka[>=<]*[0-9.]*/aiokafka==${AIOKAFKA_VERSION}/g" \
        -e "s/fastavro[>=<]*[0-9.]*/fastavro==${FASTAVRO_VERSION}/g" \
        -e "s/opentelemetry-api[>=<]*[0-9.b]*/opentelemetry-api==${OTEL_VERSION}/g" \
        -e "s/opentelemetry-sdk[>=<]*[0-9.b]*/opentelemetry-sdk==${OTEL_VERSION}/g" \
        -e "s/opentelemetry-exporter-otlp[>=<]*[0-9.b]*/opentelemetry-exporter-otlp==${OTEL_VERSION}/g" \
        -e "s/opentelemetry-instrumentation-fastapi[>=<]*[0-9.b]*/opentelemetry-instrumentation-fastapi==${OTEL_INSTRUMENTATION_VERSION}/g" \
        -e "s/opentelemetry-instrumentation-grpc[>=<]*[0-9.b]*/opentelemetry-instrumentation-grpc==${OTEL_INSTRUMENTATION_VERSION}/g" \
        -e "s/opentelemetry-instrumentation-kafka-python[>=<]*[0-9.b]*/opentelemetry-instrumentation-kafka-python==${OTEL_INSTRUMENTATION_VERSION}/g" \
        -e "s/structlog[>=<]*[0-9.]*/structlog==${STRUCTLOG_VERSION}/g" \
        -e "s/prometheus-client[>=<]*[0-9.]*/prometheus-client==${PROMETHEUS_CLIENT_VERSION}/g" \
        -e "s/httpx[>=<]*[0-9.]*/httpx==${HTTPX_VERSION}/g" \
        -e "s/aiohttp[>=<]*[0-9.]*/aiohttp==${AIOHTTP_VERSION}/g" \
        -e "s/redis\[hiredis\][>=<]*[0-9.]*/redis[hiredis]==${REDIS_VERSION}/g" \
        -e "s/redis[>=<]*[0-9.]*/redis==${REDIS_VERSION}/g" \
        -e "s/pymongo[>=<]*[0-9.]*/pymongo==${PYMONGO_VERSION}/g" \
        -e "s/motor[>=<]*[0-9.]*/motor==${MOTOR_VERSION}/g" \
        -e "s/numpy[>=<]*[0-9.]*/numpy==${NUMPY_VERSION}/g" \
        -e "s/pandas[>=<]*[0-9.]*/pandas==${PANDAS_VERSION}/g" \
        -e "s/scipy[>=<]*[0-9.]*/scipy==${SCIPY_VERSION}/g" \
        -e "s/scikit-learn[>=<]*[0-9.]*/scikit-learn==${SCIKIT_LEARN_VERSION}/g" \
        -e "s/mlflow[>=<]*[0-9.]*/mlflow==${MLFLOW_VERSION}/g" \
        -e "s/sentence-transformers[>=<]*[0-9.]*/sentence-transformers==${SENTENCE_TRANSFORMERS_VERSION}/g" \
        -e "s/python-dotenv[>=<]*[0-9.]*/python-dotenv==${PYTHON_DOTENV_VERSION}/g" \
        -e "s/tenacity[>=<]*[0-9.]*/tenacity==${TENACITY_VERSION}/g" \
        -e "s/cachetools[>=<]*[0-9.]*/cachetools==${CACHETOOLS_VERSION}/g" \
        "$file"

    # Verificar se houve mudanças
    if diff -q "$file" "$backup" > /dev/null 2>&1; then
        rm "$backup"
    else
        log_success "Atualizado: $file"
        rm "$backup"
    fi
}

normalize_all_requirements() {
    log_info "Normalizando todos os requirements.txt..."

    find "$PROJECT_DIR/services" -name "requirements*.txt" | while read file; do
        normalize_file "$file"
    done

    find "$PROJECT_DIR/libraries" -name "requirements*.txt" | while read file; do
        normalize_file "$file"
    done

    find "$PROJECT_DIR/ml_pipelines" -name "requirements*.txt" | while read file; do
        normalize_file "$file"
    done

    find "$PROJECT_DIR/tests" -name "requirements*.txt" | while read file; do
        normalize_file "$file"
    done
}

update_versions_file() {
    log_info "Atualizando versions.txt..."

    cat > "$PROJECT_DIR/versions.txt" << EOF
# =============================================================================
# Neural Hive-Mind - Versões Canônicas de Dependências
# =============================================================================
# Este arquivo é a FONTE DE VERDADE para todas as versões de dependências.
# Atualizado: $(date +%Y-%m-%d)
# Versão: 2.0.0
# =============================================================================

# Core Web Framework
fastapi==${FASTAPI_VERSION}
uvicorn[standard]==${UVICORN_VERSION}
pydantic==${PYDANTIC_VERSION}
pydantic-settings==${PYDANTIC_SETTINGS_VERSION}

# gRPC Stack (versões devem ser compatíveis entre si)
grpcio==${GRPCIO_VERSION}
grpcio-tools==${GRPCIO_TOOLS_VERSION}
grpcio-health-checking==${GRPCIO_HEALTH_VERSION}
grpcio-reflection==${GRPCIO_REFLECTION_VERSION}
protobuf==${PROTOBUF_VERSION}

# Kafka/Messaging
confluent-kafka==${CONFLUENT_KAFKA_VERSION}
aiokafka==${AIOKAFKA_VERSION}
fastavro==${FASTAVRO_VERSION}

# Observability - OpenTelemetry
opentelemetry-api==${OTEL_VERSION}
opentelemetry-sdk==${OTEL_VERSION}
opentelemetry-exporter-otlp==${OTEL_VERSION}
opentelemetry-instrumentation-fastapi==${OTEL_INSTRUMENTATION_VERSION}
opentelemetry-instrumentation-grpc==${OTEL_INSTRUMENTATION_VERSION}
opentelemetry-instrumentation-kafka-python==${OTEL_INSTRUMENTATION_VERSION}

# Logging
structlog==${STRUCTLOG_VERSION}
prometheus-client==${PROMETHEUS_CLIENT_VERSION}

# HTTP Clients
httpx==${HTTPX_VERSION}
aiohttp==${AIOHTTP_VERSION}

# Databases
redis[hiredis]==${REDIS_VERSION}
pymongo==${PYMONGO_VERSION}
motor==${MOTOR_VERSION}

# Data Science
numpy==${NUMPY_VERSION}
pandas==${PANDAS_VERSION}
scipy==${SCIPY_VERSION}
scikit-learn==${SCIKIT_LEARN_VERSION}

# ML/AI
mlflow==${MLFLOW_VERSION}
torch==${TORCH_VERSION}
sentence-transformers==${SENTENCE_TRANSFORMERS_VERSION}

# Utils
python-dotenv==${PYTHON_DOTENV_VERSION}
tenacity==${TENACITY_VERSION}
cachetools==${CACHETOOLS_VERSION}

# Internal Libraries
neural_hive_observability==1.1.0
neural_hive_specialists==1.0.0
neural_hive_integration==1.0.0
EOF

    log_success "versions.txt atualizado"
}

update_dependency_versions_md() {
    log_info "Atualizando DEPENDENCY_VERSIONS.md..."

    cat > "$PROJECT_DIR/DEPENDENCY_VERSIONS.md" << EOF
# Versões Canônicas de Dependências - Neural Hive-Mind

Este documento consolida os pinos finais usados pelos serviços e bibliotecas internas.
**Fonte de verdade:** \`versions.txt\`

## Atualização: $(date +%Y-%m-%d)

### IMPORTANTE: Compatibilidade gRPC/Protobuf
- \`grpcio-tools ${GRPCIO_TOOLS_VERSION}\` requer \`protobuf>=${PROTOBUF_VERSION}\`
- Todas as versões foram atualizadas para garantir compatibilidade

## Pinos Canônicos (principais)

| Categoria | Dependência | Versão |
|-----------|-------------|--------|
| Web | fastapi | ${FASTAPI_VERSION} |
| Web | uvicorn[standard] | ${UVICORN_VERSION} |
| Validação | pydantic | ${PYDANTIC_VERSION} |
| Config | pydantic-settings | ${PYDANTIC_SETTINGS_VERSION} |
| gRPC | grpcio / grpcio-tools / grpcio-health-checking / grpcio-reflection | ${GRPCIO_VERSION} |
| Protobuf | protobuf | ${PROTOBUF_VERSION} |
| Kafka | confluent-kafka | ${CONFLUENT_KAFKA_VERSION} |
| Kafka | aiokafka | ${AIOKAFKA_VERSION} |
| Avro | fastavro | ${FASTAVRO_VERSION} |
| Observabilidade | opentelemetry-* (api, sdk, exporters) | ${OTEL_VERSION} |
| Observabilidade | opentelemetry-instrumentation-* | ${OTEL_INSTRUMENTATION_VERSION} |
| Observabilidade | neural_hive_observability | 1.1.0 |
| Logging | structlog | ${STRUCTLOG_VERSION} |
| Prometheus | prometheus-client | ${PROMETHEUS_CLIENT_VERSION} |
| HTTP | httpx | ${HTTPX_VERSION} |
| HTTP | aiohttp | ${AIOHTTP_VERSION} |
| Redis | redis[hiredis] | ${REDIS_VERSION} |
| MongoDB | pymongo | ${PYMONGO_VERSION} |
| MongoDB | motor | ${MOTOR_VERSION} |
| Numérico | numpy | ${NUMPY_VERSION} |
| Numérico | pandas | ${PANDAS_VERSION} |
| Numérico | scipy | ${SCIPY_VERSION} |
| ML | scikit-learn | ${SCIKIT_LEARN_VERSION} |
| ML | mlflow | ${MLFLOW_VERSION} |
| Deep Learning | torch | ${TORCH_VERSION} |
| NLP | sentence-transformers | ${SENTENCE_TRANSFORMERS_VERSION} |

## Status de Normalização
- ✅ Serviços: Todos atualizados para os pinos acima
- ✅ Bibliotecas internas: neural_hive_observability, neural_hive_specialists, neural_hive_integration alinhadas
- ✅ Base images: python-specialist-base e python-mlops-base atualizadas

## Script de Normalização

Para normalizar todas as dependências, execute:

\`\`\`bash
./scripts/normalize-dependencies.sh
\`\`\`

## Referência
- Fonte de verdade: \`versions.txt\`
- Script de normalização: \`scripts/normalize-dependencies.sh\`
EOF

    log_success "DEPENDENCY_VERSIONS.md atualizado"
}

show_summary() {
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  NORMALIZAÇÃO CONCLUÍDA${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Versões principais aplicadas:"
    echo "  - fastapi: ${FASTAPI_VERSION}"
    echo "  - pydantic: ${PYDANTIC_VERSION}"
    echo "  - grpcio: ${GRPCIO_VERSION}"
    echo "  - protobuf: ${PROTOBUF_VERSION}"
    echo "  - opentelemetry: ${OTEL_VERSION}"
    echo ""
    echo "Execute './scripts/build-services-sequential.sh --all' para fazer o build"
}

# =============================================================================
# EXECUÇÃO PRINCIPAL
# =============================================================================

main() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Neural Hive-Mind - Normalização de Dependências${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
    echo ""

    update_versions_file
    update_dependency_versions_md
    normalize_all_requirements
    show_summary
}

main "$@"
