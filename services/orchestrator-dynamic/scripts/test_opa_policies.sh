#!/bin/bash
#
# Script para testar políticas OPA Rego do Orchestrator Dynamic
#
# Uso:
#   ./test_opa_policies.sh [opção]
#
# Opções:
#   test     - Executar testes unitários das políticas (opa test)
#   eval     - Executar casos de exemplo (opa eval)
#   all      - Executar test + eval (padrão)
#   coverage - Executar testes com cobertura
#

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Diretórios
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
POLICIES_DIR="${PROJECT_ROOT}/policies/rego/orchestrator"
TESTS_DIR="${POLICIES_DIR}/tests"

echo -e "${BLUE}=== Teste de Políticas OPA - Orchestrator Dynamic ===${NC}"
echo ""

# Verificar se OPA está instalado
if ! command -v opa &> /dev/null; then
    echo -e "${RED}❌ OPA não encontrado. Instale com:${NC}"
    echo ""
    echo "  # Linux/Mac:"
    echo "  curl -L -o opa https://openpolicyagent.org/downloads/latest/opa_linux_amd64"
    echo "  chmod +x opa"
    echo "  sudo mv opa /usr/local/bin/"
    echo ""
    echo "  # Ou via Docker:"
    echo "  docker pull openpolicyagent/opa:0.58.0"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓ OPA instalado: $(opa version | head -1)${NC}"
echo ""

# Verificar se diretório de políticas existe
if [ ! -d "${POLICIES_DIR}" ]; then
    echo -e "${RED}❌ Diretório de políticas não encontrado: ${POLICIES_DIR}${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Diretório de políticas: ${POLICIES_DIR}${NC}"
echo ""

# Opção do comando
COMMAND="${1:-all}"

#
# Função: Executar testes unitários
#
run_tests() {
    echo -e "${BLUE}=== Executando Testes Unitários (opa test) ===${NC}"
    echo ""

    if [ -d "${TESTS_DIR}" ]; then
        # Executar testes com verbose
        if opa test "${POLICIES_DIR}" -v; then
            echo ""
            echo -e "${GREEN}✓ Todos os testes passaram!${NC}"
            return 0
        else
            echo ""
            echo -e "${RED}❌ Alguns testes falharam${NC}"
            return 1
        fi
    else
        echo -e "${YELLOW}⚠ Diretório de testes não encontrado: ${TESTS_DIR}${NC}"
        echo -e "${YELLOW}⚠ Pulando testes unitários${NC}"
        return 0
    fi
}

#
# Função: Executar testes com cobertura
#
run_coverage() {
    echo -e "${BLUE}=== Executando Testes com Cobertura ===${NC}"
    echo ""

    if [ -d "${TESTS_DIR}" ]; then
        # Executar testes com coverage
        if opa test "${POLICIES_DIR}" --coverage --format=json > /tmp/opa-coverage.json; then
            echo ""
            echo -e "${GREEN}✓ Testes executados com cobertura${NC}"
            echo ""

            # Exibir cobertura
            opa test "${POLICIES_DIR}" --coverage

            echo ""
            echo -e "${BLUE}Relatório de cobertura salvo em: /tmp/opa-coverage.json${NC}"
            return 0
        else
            echo ""
            echo -e "${RED}❌ Falha ao executar testes com cobertura${NC}"
            return 1
        fi
    else
        echo -e "${YELLOW}⚠ Diretório de testes não encontrado: ${TESTS_DIR}${NC}"
        return 0
    fi
}

#
# Função: Executar casos de exemplo
#
run_eval_examples() {
    echo -e "${BLUE}=== Executando Casos de Exemplo (opa eval) ===${NC}"
    echo ""

    local EXIT_CODE=0

    # Exemplo 1: Resource Limits - Ticket válido
    echo -e "${YELLOW}Exemplo 1: Resource Limits - Ticket válido (high risk_band)${NC}"
    cat > /tmp/opa-input-1.json <<EOF
{
  "resource": {
    "ticket_id": "example-1",
    "risk_band": "high",
    "sla": {
      "timeout_ms": 60000,
      "max_retries": 3
    },
    "estimated_duration_ms": 30000,
    "required_capabilities": ["code_generation"]
  },
  "parameters": {
    "allowed_capabilities": ["code_generation", "deployment", "testing"],
    "max_concurrent_tickets": 100
  },
  "context": {
    "total_tickets": 50
  }
}
EOF

    if opa eval -d "${POLICIES_DIR}/resource_limits.rego" -i /tmp/opa-input-1.json \
        'data.neuralhive.orchestrator.resource_limits.result' --format pretty; then
        echo -e "${GREEN}✓ Avaliação bem-sucedida${NC}"
    else
        echo -e "${RED}❌ Falha na avaliação${NC}"
        EXIT_CODE=1
    fi
    echo ""

    # Exemplo 2: Resource Limits - Timeout excedido
    echo -e "${YELLOW}Exemplo 2: Resource Limits - Timeout excedido${NC}"
    cat > /tmp/opa-input-2.json <<EOF
{
  "resource": {
    "ticket_id": "example-2",
    "risk_band": "high",
    "sla": {
      "timeout_ms": 7200000,
      "max_retries": 3
    },
    "estimated_duration_ms": 30000,
    "required_capabilities": ["code_generation"]
  },
  "parameters": {
    "allowed_capabilities": ["code_generation"],
    "max_concurrent_tickets": 100
  },
  "context": {
    "total_tickets": 50
  }
}
EOF

    if opa eval -d "${POLICIES_DIR}/resource_limits.rego" -i /tmp/opa-input-2.json \
        'data.neuralhive.orchestrator.resource_limits.result' --format pretty; then
        echo -e "${GREEN}✓ Avaliação bem-sucedida (violação esperada)${NC}"
    else
        echo -e "${RED}❌ Falha na avaliação${NC}"
        EXIT_CODE=1
    fi
    echo ""

    # Exemplo 3: SLA Enforcement - Deadline no passado
    echo -e "${YELLOW}Exemplo 3: SLA Enforcement - Deadline no passado${NC}"
    CURRENT_TIME=$(date +%s)000
    PAST_DEADLINE=$((CURRENT_TIME - 3600000))

    cat > /tmp/opa-input-3.json <<EOF
{
  "resource": {
    "ticket_id": "example-3",
    "risk_band": "critical",
    "sla": {
      "timeout_ms": 120000,
      "deadline": ${PAST_DEADLINE}
    },
    "qos": {
      "delivery_mode": "EXACTLY_ONCE",
      "consistency": "STRONG"
    },
    "priority": "critical",
    "estimated_duration_ms": 60000
  },
  "context": {
    "current_time": ${CURRENT_TIME}
  }
}
EOF

    if opa eval -d "${POLICIES_DIR}/sla_enforcement.rego" -i /tmp/opa-input-3.json \
        'data.neuralhive.orchestrator.sla_enforcement.result' --format pretty; then
        echo -e "${GREEN}✓ Avaliação bem-sucedida (violação esperada)${NC}"
    else
        echo -e "${RED}❌ Falha na avaliação${NC}"
        EXIT_CODE=1
    fi
    echo ""

    # Exemplo 4: SLA Enforcement - QoS válido
    echo -e "${YELLOW}Exemplo 4: SLA Enforcement - QoS válido${NC}"
    FUTURE_DEADLINE=$((CURRENT_TIME + 3600000))

    cat > /tmp/opa-input-4.json <<EOF
{
  "resource": {
    "ticket_id": "example-4",
    "risk_band": "critical",
    "sla": {
      "timeout_ms": 120000,
      "deadline": ${FUTURE_DEADLINE}
    },
    "qos": {
      "delivery_mode": "EXACTLY_ONCE",
      "consistency": "STRONG"
    },
    "priority": "critical",
    "estimated_duration_ms": 60000
  },
  "context": {
    "current_time": ${CURRENT_TIME}
  }
}
EOF

    if opa eval -d "${POLICIES_DIR}/sla_enforcement.rego" -i /tmp/opa-input-4.json \
        'data.neuralhive.orchestrator.sla_enforcement.result' --format pretty; then
        echo -e "${GREEN}✓ Avaliação bem-sucedida${NC}"
    else
        echo -e "${RED}❌ Falha na avaliação${NC}"
        EXIT_CODE=1
    fi
    echo ""

    # Exemplo 5: Feature Flags - Intelligent Scheduler para critical
    echo -e "${YELLOW}Exemplo 5: Feature Flags - Intelligent Scheduler habilitado${NC}"
    cat > /tmp/opa-input-5.json <<EOF
{
  "resource": {
    "ticket_id": "example-5",
    "risk_band": "critical"
  },
  "flags": {
    "intelligent_scheduler_enabled": true,
    "scheduler_namespaces": ["production", "staging"],
    "burst_capacity_enabled": false,
    "predictive_allocation_enabled": false,
    "auto_scaling_enabled": false
  },
  "context": {
    "namespace": "production",
    "current_load": 0.5,
    "tenant_id": "tenant-1",
    "queue_depth": 50,
    "current_time": ${CURRENT_TIME},
    "model_accuracy": 0.9
  }
}
EOF

    if opa eval -d "${POLICIES_DIR}/feature_flags.rego" -i /tmp/opa-input-5.json \
        'data.neuralhive.orchestrator.feature_flags.result' --format pretty; then
        echo -e "${GREEN}✓ Avaliação bem-sucedida${NC}"
    else
        echo -e "${RED}❌ Falha na avaliação${NC}"
        EXIT_CODE=1
    fi
    echo ""

    # Cleanup
    rm -f /tmp/opa-input-*.json

    return $EXIT_CODE
}

#
# Main
#
case "${COMMAND}" in
    test)
        run_tests
        ;;
    eval)
        run_eval_examples
        ;;
    coverage)
        run_coverage
        ;;
    all)
        run_tests
        TEST_EXIT=$?

        run_eval_examples
        EVAL_EXIT=$?

        if [ $TEST_EXIT -eq 0 ] && [ $EVAL_EXIT -eq 0 ]; then
            echo ""
            echo -e "${GREEN}=== ✓ Todos os testes e exemplos passaram! ===${NC}"
            exit 0
        else
            echo ""
            echo -e "${RED}=== ✗ Alguns testes ou exemplos falharam ===${NC}"
            exit 1
        fi
        ;;
    *)
        echo -e "${RED}Opção inválida: ${COMMAND}${NC}"
        echo ""
        echo "Uso: $0 [test|eval|coverage|all]"
        echo ""
        echo "  test     - Executar testes unitários (opa test)"
        echo "  eval     - Executar casos de exemplo (opa eval)"
        echo "  coverage - Executar testes com cobertura"
        echo "  all      - Executar test + eval (padrão)"
        echo ""
        exit 1
        ;;
esac
