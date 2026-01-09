#!/bin/bash
#
# Guard Agents OPA Policy Validation Script
# Validates syntax, runs tests, and checks coverage for Guard Agents policies
#
# Usage: ./scripts/validation/validate-guard-policies.sh [--coverage] [--verbose]
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
POLICIES_DIR="${PROJECT_ROOT}/policies/rego/guard-agents"

# Parse arguments
COVERAGE=false
VERBOSE=false
for arg in "$@"; do
    case $arg in
        --coverage)
            COVERAGE=true
            ;;
        --verbose|-v)
            VERBOSE=true
            ;;
        --help|-h)
            echo "Usage: $0 [--coverage] [--verbose]"
            echo ""
            echo "Options:"
            echo "  --coverage    Run tests with coverage report"
            echo "  --verbose     Enable verbose output"
            echo "  --help        Show this help message"
            exit 0
            ;;
    esac
done

# Check OPA is installed
if ! command -v opa &> /dev/null; then
    echo -e "${RED}Error: OPA is not installed.${NC}"
    echo "Install OPA from: https://www.openpolicyagent.org/docs/latest/#running-opa"
    exit 1
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Guard Agents OPA Policy Validation${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if policies directory exists
if [ ! -d "${POLICIES_DIR}" ]; then
    echo -e "${RED}Error: Policies directory not found: ${POLICIES_DIR}${NC}"
    exit 1
fi

# Step 1: Check policy syntax
echo -e "${YELLOW}[1/4] Checking policy syntax...${NC}"
echo ""

SYNTAX_ERRORS=0
for policy_file in "${POLICIES_DIR}"/*.rego; do
    if [ -f "$policy_file" ]; then
        filename=$(basename "$policy_file")
        if opa check "$policy_file" 2>/dev/null; then
            echo -e "  ${GREEN}✓${NC} ${filename}"
        else
            echo -e "  ${RED}✗${NC} ${filename}"
            opa check "$policy_file"
            SYNTAX_ERRORS=$((SYNTAX_ERRORS + 1))
        fi
    fi
done

if [ $SYNTAX_ERRORS -gt 0 ]; then
    echo ""
    echo -e "${RED}Syntax check failed with ${SYNTAX_ERRORS} error(s)${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}Syntax check passed!${NC}"
echo ""

# Step 2: Check test file syntax
echo -e "${YELLOW}[2/4] Checking test file syntax...${NC}"
echo ""

TEST_SYNTAX_ERRORS=0
for test_file in "${POLICIES_DIR}/tests"/*.rego; do
    if [ -f "$test_file" ]; then
        filename=$(basename "$test_file")
        if opa check "$test_file" 2>/dev/null; then
            echo -e "  ${GREEN}✓${NC} ${filename}"
        else
            echo -e "  ${RED}✗${NC} ${filename}"
            opa check "$test_file"
            TEST_SYNTAX_ERRORS=$((TEST_SYNTAX_ERRORS + 1))
        fi
    fi
done

if [ $TEST_SYNTAX_ERRORS -gt 0 ]; then
    echo ""
    echo -e "${RED}Test syntax check failed with ${TEST_SYNTAX_ERRORS} error(s)${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}Test syntax check passed!${NC}"
echo ""

# Step 3: Run tests
echo -e "${YELLOW}[3/4] Running unit tests...${NC}"
echo ""

if [ "$VERBOSE" = true ]; then
    VERBOSE_FLAG="-v"
else
    VERBOSE_FLAG=""
fi

# Run tests for each policy
TEST_RESULTS=0

echo "  Testing security policies..."
if opa test "${POLICIES_DIR}/security_policies.rego" "${POLICIES_DIR}/tests/security_policies_test.rego" $VERBOSE_FLAG; then
    echo -e "  ${GREEN}✓${NC} Security policies tests passed"
else
    echo -e "  ${RED}✗${NC} Security policies tests failed"
    TEST_RESULTS=$((TEST_RESULTS + 1))
fi

echo ""
echo "  Testing compliance policies..."
if opa test "${POLICIES_DIR}/compliance_policies.rego" "${POLICIES_DIR}/tests/compliance_policies_test.rego" $VERBOSE_FLAG; then
    echo -e "  ${GREEN}✓${NC} Compliance policies tests passed"
else
    echo -e "  ${RED}✗${NC} Compliance policies tests failed"
    TEST_RESULTS=$((TEST_RESULTS + 1))
fi

echo ""
echo "  Testing resource policies..."
if opa test "${POLICIES_DIR}/resource_policies.rego" "${POLICIES_DIR}/tests/resource_policies_test.rego" $VERBOSE_FLAG; then
    echo -e "  ${GREEN}✓${NC} Resource policies tests passed"
else
    echo -e "  ${RED}✗${NC} Resource policies tests failed"
    TEST_RESULTS=$((TEST_RESULTS + 1))
fi

echo ""

if [ $TEST_RESULTS -gt 0 ]; then
    echo -e "${RED}${TEST_RESULTS} test suite(s) failed${NC}"
    exit 1
fi

echo -e "${GREEN}All tests passed!${NC}"
echo ""

# Step 4: Coverage report (optional)
if [ "$COVERAGE" = true ]; then
    echo -e "${YELLOW}[4/4] Generating coverage report...${NC}"
    echo ""

    echo "  Security policies coverage:"
    opa test --coverage "${POLICIES_DIR}/security_policies.rego" "${POLICIES_DIR}/tests/security_policies_test.rego" | grep -E "coverage|%"

    echo ""
    echo "  Compliance policies coverage:"
    opa test --coverage "${POLICIES_DIR}/compliance_policies.rego" "${POLICIES_DIR}/tests/compliance_policies_test.rego" | grep -E "coverage|%"

    echo ""
    echo "  Resource policies coverage:"
    opa test --coverage "${POLICIES_DIR}/resource_policies.rego" "${POLICIES_DIR}/tests/resource_policies_test.rego" | grep -E "coverage|%"

    echo ""
    echo -e "${GREEN}Coverage report complete!${NC}"
else
    echo -e "${YELLOW}[4/4] Skipping coverage (use --coverage to enable)${NC}"
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}All validations passed successfully!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Summary
echo "Summary:"
echo "  - Policy files: $(find "${POLICIES_DIR}" -maxdepth 1 -name "*.rego" | wc -l)"
echo "  - Test files: $(find "${POLICIES_DIR}/tests" -name "*.rego" | wc -l)"
echo "  - Total rules:"
echo "    - Security: 17 rules"
echo "    - Compliance: 14 rules"
echo "    - Resource: 16 rules"
echo ""

exit 0
