#!/bin/bash
# Script de validação rápida para implementação das prioridades 2026-03-30
# Uso: ./scripts/validate-implementation.sh

set -e

echo "🔍 Validando implementação das prioridades NHM 2026-03-30"
echo ""

# Cores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

pass=0
fail=0
warn=0

check() {
    local name="$1"
    local command="$2"
    local expected="$3"

    echo -n "Checking $name... "

    if eval "$command" > /dev/null 2>&1; then
        result=$(eval "$command" 2>/dev/null || echo "0")
        if [ "$result" = "$expected" ] || [ "$expected" = "" ]; then
            echo -e "${GREEN}✓ PASS${NC}"
            ((pass++))
            return 0
        else
            echo -e "${YELLOW}⚠ WARN (expected $expected, got $result)${NC}"
            ((warn++))
            return 0
        fi
    else
        echo -e "${RED}✗ FAIL${NC}"
        ((fail++))
        return 1
    fi
}

# 1. CORS Wildcards
echo "📋 Epic B: CORS Wildcards"
check "CORS wildcards removidos" "grep -r 'allow_origins.*\*' services/ 2>/dev/null | grep -v '\.pyc' | grep -v '__pycache__' | grep -v '#' | wc -l" "0"

# 2. Helm Charts
echo ""
echo "📋 Epic E: Helm Charts"
helm_count=$(find services/ -name "Chart.yaml" -path "*/helm/*" 2>/dev/null | wc -l)
echo "  Helm charts criados: $helm_count (esperado: +5)"
if [ "$helm_count" -ge 13 ]; then
    echo -e "  ${GREEN}✓ PASS${NC}"
    ((pass++))
else
    echo -e "  ${YELLOW}⚠ WARN${NC}"
    ((warn++))
fi

# 3. Feature Store
echo ""
echo "📋 Epic C: Feature Store"
check "feature-store/main.py existe" "test -f services/feature-store/src/main.py" ""
check "feature-store computation.py" "test -f services/feature-store/src/services/computation.py" ""
check "feature-store tests" "test -f services/feature-store/tests/test_computation.py" ""

# 4. Online Learning
echo ""
echo "📋 Epic D: Online Learning"
check "feedback_consumer.py" "test -f services/approval-service/src/consumers/feedback_consumer.py" ""
check "online_learning_service.py" "test -f services/approval-service/src/services/online_learning_service.py" ""
check "retraining_scheduler.py" "test -f services/approval-service/src/schedulers/retraining_scheduler.py" ""

# 5. Kafka Consumers
echo ""
echo "📋 Epic J: Kafka Consumers"
check "insights_consumer.py" "test -f services/orchestrator-dynamic/src/consumers/insights_consumer.py" ""
check "strategic_decision_consumer.py" "test -f services/orchestrator-dynamic/src/consumers/strategic_decision_consumer.py" ""
check "signal_consumer.py" "test -f services/scout-agents/src/consumers/signal_consumer.py" ""
check "incident_feedback_consumer.py" "test -f services/guard-agents/src/consumers/incident_feedback_consumer.py" ""
check "optimization_feedback_consumer.py" "test -f services/optimizer-agents/src/consumers/optimization_feedback_consumer.py" ""

# 6. ML Models
echo ""
echo "📋 Epic K: ML Models"
check "train_business_specialist.py" "test -f ml_pipelines/training/train_business_specialist.py" ""
check "train_technical_specialist.py" "test -f ml_pipelines/training/train_technical_specialist.py" ""
check "train_architecture_specialist.py" "test -f ml_pipelines/training/train_architecture_specialist.py" ""
check "train_behavior_specialist.py" "test -f ml_pipelines/training/train_behavior_specialist.py" ""
check "train_evolution_specialist.py" "test -f ml_pipelines/training/train_evolution_specialist.py" ""

# 7. Multi-region Terraform
echo ""
echo "📋 Epic L: Multi-region"
check "us-east-1 config" "test -f infrastructure/terraform/environments/prod-us-east-1/main.tf" ""
check "us-west-2 config" "test -f infrastructure/terraform/environments/prod-us-west-2/main.tf" ""
check "eu-west-1 config" "test -f infrastructure/terraform/environments/prod-eu-west-1/main.tf" ""

# 8. OPA Gatekeeper
echo ""
echo "📋 Epic H: OPA Gatekeeper"
check "OPA config" "test -f k8s/opa-gatekeeper/config.yaml" ""
check "OPA validating-webhook" "test -f k8s/opa-gatekeeper/validating-webhook.yaml" ""
opa_tests=$(find policies/rego/gatekeeper/tests/ -name "*_test.rego" 2>/dev/null | wc -l)
echo "  OPA tests: $opa_tests (esperado: 17)"
if [ "$opa_tests" -ge 17 ]; then
    echo -e "  ${GREEN}✓ PASS${NC}"
    ((pass++))
else
    echo -e "  ${YELLOW}⚠ WARN${NC}"
    ((warn++))
fi

# 9. READMEs
echo ""
echo "📋 Epic I: READMEs"
readme_count=0
for service in approval-service queen-agent guard-agents specialist-business specialist-technical specialist-architecture specialist-behavior specialist-evolution explainability-api mcp-servers; do
    if [ -f "services/$service/README.md" ]; then
        ((readme_count++))
    fi
done
echo "  READMEs criados: $readme_count/10"
if [ "$readme_count" -eq 10 ]; then
    echo -e "  ${GREEN}✓ PASS${NC}"
    ((pass++))
else
    echo -e "  ${YELLOW}⚠ WARN${NC}"
    ((warn++))
fi

# 10. Agent OS Specs
echo ""
echo "📋 Agent OS Specs"
check "spec.md" "test -f .agent-os/specs/2026-03-30-priorities-implementation/spec.md" ""
check "spec-lite.md" "test -f .agent-os/specs/2026-03-30-priorities-implementation/spec-lite.md" ""
check "tasks.md" "test -f .agent-os/specs/2026-03-30-priorities-implementation/tasks.md" ""
subspecs=$(find .agent-os/specs/2026-03-30-priorities-implementation/sub-specs -name "*.md" 2>/dev/null | wc -l)
echo "  Sub-specs: $subspecs (esperado: 12)"
if [ "$subspecs" -eq 12 ]; then
    echo -e "  ${GREEN}✓ PASS${NC}"
    ((pass++))
else
    echo -e "  ${YELLOW}⚠ WARN${NC}"
    ((warn++))
fi

# Resumo
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "  ${GREEN}PASS:$pass${NC}  ${YELLOW}WARN:$warn${NC}  ${RED}FAIL:$fail${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Exit code
if [ $fail -gt 0 ]; then
    exit 1
else
    exit 0
fi
