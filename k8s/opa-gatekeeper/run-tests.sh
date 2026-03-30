#!/bin/bash
# Script de Teste para Políticas OPA Gatekeeper
# Epic H - H003: Testes de OPA Policies
#
# Execute: ./k8s/opa-gatekeeper/run-tests.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
POLICIES_DIR="$PROJECT_ROOT/policies/rego/gatekeeper/tests"

echo "=========================================="
echo "OPA Gatekeeper - Test Runner"
echo "Epic H - H003"
echo "=========================================="
echo ""

# Verificar se OPA está instalado
if ! command -v opa &> /dev/null; then
    echo "ERRO: OPA não está instalado."
    echo "Instale com: brew install opa"
    echo "Ou: https://www.openpolicyagent.org/docs/latest/#running-opa"
    exit 1
fi

echo "OPA version: $(opa version --format json | jq -r '.version')"
echo ""

# Contar testes
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Lista de arquivos de teste
TEST_FILES=(
    "oauth2_token_required_test.rego"
    "mesh_mtls_required_test.rego"
    "redis_security_required_test.rego"
    "ethical_guardrails_test.rego"
    "pod_security_policy_test.rego"
    "resource_limits_test.rego"
    "image_policy_test.rego"
    "namespace_labels_test.rego"
    "ingress_tls_test.rego"
    "storage_encryption_test.rego"
    "secret_encryption_test.rego"
    "network_policy_test.rego"
    "rbac_restrictions_test.rego"
    "container_runtime_test.rego"
    "cpu_limit_test.rego"
    "memory_limit_test.rego"
    "audit_logging_test.rego"
)

echo "Executando testes..."
echo ""

for test_file in "${TEST_FILES[@]}"; do
    test_path="$POLICIES_DIR/$test_file"

    if [ ! -f "$test_path" ]; then
        echo "⚠️  ARQUIVO NÃO ENCONTRADO: $test_file"
        continue
    fi

    echo "▶️  Testando: $test_file"

    # Executar testes OPA
    if opa test "$test_path" -v 2>&1; then
        echo "✅ PASS: $test_file"
        ((PASSED_TESTS++))
    else
        echo "❌ FAIL: $test_file"
        ((FAILED_TESTS++))
    fi

    ((TOTAL_TESTS++))
    echo ""
done

# Resumo
echo "=========================================="
echo "RESUMO DOS TESTES"
echo "=========================================="
echo "Total de arquivos de teste: $TOTAL_TESTS"
echo "Testes passados: $PASSED_TESTS"
echo "Testes falhados: $FAILED_TESTS"
echo ""

if [ $FAILED_TESTS -eq 0 ]; then
    echo "✅ TODOS OS TESTES PASSARAM!"
    exit 0
else
    echo "❌ ALGUNS TESTES FALHARAM"
    exit 1
fi
