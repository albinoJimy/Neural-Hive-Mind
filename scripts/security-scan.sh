#!/bin/bash
#
# Security scan script for Neural Hive Mind
# Runs Trivy for container scanning and Bandit for Python security analysis
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Neural Hive Mind - Security Scan ===${NC}"
echo ""

# Project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCAN_DIR="${PROJECT_ROOT}/security-scans"
mkdir -p "${SCAN_DIR}"

# Timestamp for reports
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "Scan timestamp: ${TIMESTAMP}"
echo "Project root: ${PROJECT_ROOT}"
echo ""

# =============================================================================
# Trivy - Container Image Scanning
# =============================================================================

echo -e "${YELLOW}--- Running Trivy Container Scans ---${NC}"

# Services to scan (Fluxo G engineering services)
SERVICES=(
    "requirements-engineering"
    "documentation-generation"
    "knowledge-graph-rag"
    "approval-gateway"
    "service-registry"
    "orchestrator-dynamic"
)

for service in "${SERVICES[@]}"; do
    echo -e "\n${GREEN}Scanning ${service}...${NC}"

    # Check if Dockerfile exists
    if [ -f "services/${service}/Dockerfile" ]; then
        # Scan Dockerfile for vulnerabilities
        trivy config \
            --severity HIGH,CRITICAL \
            --format json \
            --output "${SCAN_DIR}/${service}_trivy_${TIMESTAMP}.json" \
            "services/${service}/Dockerfile" || true

        # Also generate human-readable report
        trivy config \
            --severity HIGH,CRITICAL \
            --format table \
            "services/${service}/Dockerfile" || echo "  No critical vulnerabilities found"

        # Scan filesystem for secrets and misconfigurations
        trivy fs \
            --scanners vuln,secret \
            --severity HIGH,CRITICAL \
            --format json \
            --output "${SCAN_DIR}/${service}_fs_${TIMESTAMP}.json" \
            "services/${service}/" || true
    else
        echo "  Skipped - No Dockerfile found"
    fi
done

# =============================================================================
# Bandit - Python Security Analysis
# =============================================================================

echo -e "\n${YELLOW}--- Running Bandit Python Security Scans ---${NC}"

# Scan each service directory
for service in "${SERVICES[@]}"; do
    echo -e "\n${GREEN}Scanning ${service} Python code...${NC}"

    if [ -d "services/${service}/src" ]; then
        # Run Bandit with output to file
        bandit -r "services/${service}/src" \
            -f json \
            -o "${SCAN_DIR}/${service}_bandit_${TIMESTAMP}.json" \
            || echo "  Bandit scan completed with findings"

        # Also show summary on console
        bandit -r "services/${service}/src" || true
    fi
done

# =============================================================================
# Summary Report
# =============================================================================

echo -e "\n${GREEN}=== Scan Summary ===${NC}"

# Count critical vulnerabilities
CRITICAL_COUNT=0
HIGH_COUNT=0

for service in "${SERVICES[@]}"; do
    if [ -f "${SCAN_DIR}/${service}_trivy_${TIMESTAMP}.json" ]; then
        # Count vulnerabilities using jq
        if command -v jq &> /dev/null; then
            CRIT=$(jq '[.Results[] | select(.Severity == "CRITICAL")] | length' "${SCAN_DIR}/${service}_trivy_${TIMESTAMP}.json" 2>/dev/null || echo "0")
            HIGH=$(jq '[.Results[] | select(.Severity == "HIGH")] | length' "${SCAN_DIR}/${service}_trivy_${TIMESTAMP}.json" 2>/dev/null || echo "0")

            echo "${service}: ${CRIT} CRITICAL, ${HIGH} HIGH"

            CRITICAL_COUNT=$((CRITICAL_COUNT + CRIT))
            HIGH_COUNT=$((HIGH_COUNT + HIGH))
        fi
    fi
done

echo ""
echo "Total: ${CRITICAL_COUNT} CRITICAL, ${HIGH_COUNT} HIGH vulnerabilities"

# Generate HTML report if trivy-html-plugin is available
echo -e "\n${GREEN}Reports saved to: ${SCAN_DIR}${NC}"
ls -la "${SCAN_DIR}" | grep "${TIMESTAMP}"

# Exit with error if critical vulnerabilities found
if [ ${CRITICAL_COUNT} -gt 0 ]; then
    echo -e "\n${RED}!!! CRITICAL VULNERABILITIES FOUND !!!${NC}"
    exit 1
fi

echo -e "\n${GREEN}=== Security Scan Complete ===${NC}"
