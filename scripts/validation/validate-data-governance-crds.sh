#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
#
# validate-data-governance-crds.sh
# Script para validar CRDs de governança de dados do Neural Hive-Mind
#

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Contadores
TESTS_TOTAL=0
TESTS_PASSED=0
TESTS_FAILED=0

# Logging functions
log() { echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; ((TESTS_PASSED++)); }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; ((TESTS_FAILED++)); }
log_test() { echo -e "${BLUE}[TEST]${NC} $1"; ((TESTS_TOTAL++)); }

TEMP_DIR="/tmp/neuralhive-crd-validation"
TEST_NAMESPACE="neural-hive-system"

check_dependencies() {
    log "Verificando dependências..."
    for dep in kubectl; do
        if ! command -v "$dep" &> /dev/null; then
            log_error "Dependência necessária não encontrada: $dep"
            exit 1
        fi
    done
    log_success "Dependências verificadas"
}

cleanup() {
    [[ -d "$TEMP_DIR" ]] && rm -rf "$TEMP_DIR"
    # Cleanup test resources
    kubectl delete apiasset test-api-asset -n "$TEST_NAMESPACE" --ignore-not-found=true &> /dev/null
    kubectl delete dataasset test-data-asset -n "$TEST_NAMESPACE" --ignore-not-found=true &> /dev/null
    kubectl delete servicecontract test-service-contract -n "$TEST_NAMESPACE" --ignore-not-found=true &> /dev/null
    kubectl delete datalineage test-data-lineage -n "$TEST_NAMESPACE" --ignore-not-found=true &> /dev/null
}

test_crds_installed() {
    log_test "Teste 1: Verificar se CRDs estão instalados"

    local crds=("apiassets.catalog.neural-hive.io" "dataassets.catalog.neural-hive.io"
                "servicecontracts.catalog.neural-hive.io" "datalineages.catalog.neural-hive.io")

    local failures=0
    for crd in "${crds[@]}"; do
        if kubectl get crd "$crd" &> /dev/null; then
            log_success "CRD instalado: $crd"
        else
            log_error "CRD não encontrado: $crd"
            ((failures++))
        fi
    done

    [[ $failures -eq 0 ]]
}

test_valid_apiasset() {
    log_test "Teste 2: Criar ApiAsset válido"

    mkdir -p "$TEMP_DIR"

    cat <<EOF > "$TEMP_DIR/valid-apiasset.yaml"
apiVersion: catalog.neural-hive.io/v1alpha1
kind: ApiAsset
metadata:
  name: test-api-asset
  namespace: $TEST_NAMESPACE
spec:
  owner: team-cognitive
  classification: internal
  sla_tier: silver
  version: v1
  description: "API de teste para validação"
  endpoints:
  - path: "/api/v1/test"
    method: GET
    sensitive_data: false
    requires_auth: true
  retention_policy: "90d"
  tags: ["test", "validation"]
EOF

    if kubectl apply -f "$TEMP_DIR/valid-apiasset.yaml" &> /dev/null; then
        log_success "ApiAsset válido criado com sucesso"
        return 0
    else
        log_error "Falha ao criar ApiAsset válido"
        return 1
    fi
}

test_invalid_apiasset() {
    log_test "Teste 3: Rejeitar ApiAsset inválido"

    cat <<EOF > "$TEMP_DIR/invalid-apiasset.yaml"
apiVersion: catalog.neural-hive.io/v1alpha1
kind: ApiAsset
metadata:
  name: invalid-api-asset
  namespace: $TEST_NAMESPACE
spec:
  owner: "invalid-owner-format"
  classification: "invalid-classification"
  sla_tier: "invalid-tier"
EOF

    if kubectl apply -f "$TEMP_DIR/invalid-apiasset.yaml" &> /dev/null; then
        log_error "ApiAsset inválido foi aceito (deveria ser rejeitado)"
        kubectl delete apiasset invalid-api-asset -n "$TEST_NAMESPACE" --ignore-not-found=true &> /dev/null
        return 1
    else
        log_success "ApiAsset inválido rejeitado corretamente"
        return 0
    fi
}

test_valid_dataasset() {
    log_test "Teste 4: Criar DataAsset válido"

    cat <<EOF > "$TEMP_DIR/valid-dataasset.yaml"
apiVersion: catalog.neural-hive.io/v1alpha1
kind: DataAsset
metadata:
  name: test-data-asset
  namespace: $TEST_NAMESPACE
spec:
  owner: team-data
  classification: confidential
  storage_location: "postgres://neural-hive-db.test-table"
  retention_policy: "1y"
  pii_fields: ["email", "phone"]
  data_schema:
    format: json
    fields:
    - name: "user_id"
      type: "string"
      required: true
      sensitive: false
    - name: "email"
      type: "string"
      required: true
      sensitive: true
EOF

    if kubectl apply -f "$TEMP_DIR/valid-dataasset.yaml" &> /dev/null; then
        log_success "DataAsset válido criado com sucesso"
        return 0
    else
        log_error "Falha ao criar DataAsset válido"
        return 1
    fi
}

test_valid_servicecontract() {
    log_test "Teste 5: Criar ServiceContract válido"

    cat <<EOF > "$TEMP_DIR/valid-servicecontract.yaml"
apiVersion: catalog.neural-hive.io/v1alpha1
kind: ServiceContract
metadata:
  name: test-service-contract
  namespace: $TEST_NAMESPACE
spec:
  provider: "cognitive-service"
  consumer: "orchestration-service"
  version: v1
  sla_requirements:
    availability: "99.9%"
    response_time_p95: "100ms"
    throughput: "1000rps"
  data_sharing_agreement:
    allowed_fields: ["user_id", "timestamp"]
    forbidden_fields: ["email", "phone"]
    purpose: "analytics"
    retention_limit: "30d"
  expiry_date: "2025-12-31"
EOF

    if kubectl apply -f "$TEMP_DIR/valid-servicecontract.yaml" &> /dev/null; then
        log_success "ServiceContract válido criado com sucesso"
        return 0
    else
        log_error "Falha ao criar ServiceContract válido"
        return 1
    fi
}

test_valid_datalineage() {
    log_test "Teste 6: Criar DataLineage válido"

    cat <<EOF > "$TEMP_DIR/valid-datalineage.yaml"
apiVersion: catalog.neural-hive.io/v1alpha1
kind: DataLineage
metadata:
  name: test-data-lineage
  namespace: $TEST_NAMESPACE
spec:
  source:
    asset_reference: "source-namespace/source-asset"
    fields: ["user_id", "timestamp"]
    namespace: "neural-hive-cognition"
  target:
    asset_reference: "target-namespace/target-asset"
    fields: ["processed_user_id", "processed_timestamp"]
    namespace: "neural-hive-execution"
  transformation_type: "aggregate"
  transformation_logic: "SELECT user_id, COUNT(*) FROM source GROUP BY user_id"
  data_sensitivity: "medium"
  processing_frequency: "daily"
  owner: "team-data-engineering"
  tags: ["etl", "aggregation"]
EOF

    if kubectl apply -f "$TEMP_DIR/valid-datalineage.yaml" &> /dev/null; then
        log_success "DataLineage válido criado com sucesso"
        return 0
    else
        log_error "Falha ao criar DataLineage válido"
        return 1
    fi
}

test_crd_status_conditions() {
    log_test "Teste 7: Verificar status conditions dos CRDs"

    # Aguardar um momento para status ser atualizado
    sleep 2

    local resources=("apiasset/test-api-asset" "dataasset/test-data-asset"
                    "servicecontract/test-service-contract" "datalineage/test-data-lineage")

    local failures=0
    for resource in "${resources[@]}"; do
        if kubectl get "$resource" -n "$TEST_NAMESPACE" &> /dev/null; then
            log_success "Recurso existe: $resource"
        else
            log_error "Recurso não encontrado: $resource"
            ((failures++))
        fi
    done

    [[ $failures -eq 0 ]]
}

test_crd_finalizers() {
    log_test "Teste 8: Verificar finalizers nos CRDs"

    local crds=("apiassets.catalog.neural-hive.io" "dataassets.catalog.neural-hive.io"
                "servicecontracts.catalog.neural-hive.io" "datalineages.catalog.neural-hive.io")

    local failures=0
    for crd in "${crds[@]}"; do
        local finalizers
        finalizers=$(kubectl get crd "$crd" -o jsonpath='{.metadata.finalizers}' 2>/dev/null || echo "")

        if [[ -n "$finalizers" ]]; then
            log_success "CRD tem finalizers: $crd"
        else
            log_error "CRD sem finalizers: $crd"
            ((failures++))
        fi
    done

    [[ $failures -eq 0 ]]
}

test_crd_labels() {
    log_test "Teste 9: Verificar labels automáticos nos recursos"

    # Verificar se recursos têm labels baseados em specs
    local api_classification
    api_classification=$(kubectl get apiasset test-api-asset -n "$TEST_NAMESPACE" -o jsonpath='{.spec.classification}' 2>/dev/null || echo "")

    if [[ "$api_classification" == "internal" ]]; then
        log_success "ApiAsset tem classificação correta"
        return 0
    else
        log_error "ApiAsset não tem classificação esperada"
        return 1
    fi
}

test_storage_location_validation() {
    log_test "Teste 10: Testar validação de storage_location"

    cat <<EOF > "$TEMP_DIR/invalid-storage-dataasset.yaml"
apiVersion: catalog.neural-hive.io/v1alpha1
kind: DataAsset
metadata:
  name: invalid-storage-asset
  namespace: $TEST_NAMESPACE
spec:
  owner: team-data
  classification: internal
  storage_location: "invalid://location/format"
  retention_policy: "30d"
EOF

    if kubectl apply -f "$TEMP_DIR/invalid-storage-dataasset.yaml" &> /dev/null; then
        log_error "DataAsset com storage_location inválido foi aceito"
        kubectl delete dataasset invalid-storage-asset -n "$TEST_NAMESPACE" --ignore-not-found=true &> /dev/null
        return 1
    else
        log_success "DataAsset com storage_location inválido rejeitado corretamente"
        return 0
    fi
}

generate_report() {
    echo
    log "=========================================="
    log "RELATÓRIO DE VALIDAÇÃO DE CRDs"
    log "=========================================="
    echo
    log "Total de testes executados: $TESTS_TOTAL"
    log_success "Testes que passaram: $TESTS_PASSED"
    log_error "Testes que falharam: $TESTS_FAILED"

    local success_rate=0
    if [[ $TESTS_TOTAL -gt 0 ]]; then
        success_rate=$((TESTS_PASSED * 100 / TESTS_TOTAL))
    fi

    log "Taxa de sucesso: ${success_rate}%"

    if [[ $TESTS_FAILED -eq 0 ]]; then
        log_success "🎉 TODOS OS TESTES DE CRDs PASSARAM!"
        return 0
    else
        log_error "❌ ALGUNS TESTES FALHARAM"
        return 1
    fi
}

main() {
    log "Iniciando validação de CRDs de governança de dados"

    trap cleanup EXIT

    check_dependencies
    mkdir -p "$TEMP_DIR"

    test_crds_installed
    test_valid_apiasset
    test_invalid_apiasset
    test_valid_dataasset
    test_valid_servicecontract
    test_valid_datalineage
    test_crd_status_conditions
    test_crd_finalizers
    test_crd_labels
    test_storage_location_validation

    generate_report
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi