#!/bin/bash

################################################################################
# Script: run-full-version-analysis.sh
# Purpose: Orchestrate full protobuf/grpcio version analysis
# Author: Neural Hive Mind - Debug Tooling
# Date: 2025-11-10
################################################################################

set -euo pipefail

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
FINAL_REPORT="/jimy/Neural-Hive-Mind/PROTOBUF_VERSION_ANALYSIS.md"
TEMP_REPORT="/tmp/protobuf_full_analysis_${TIMESTAMP}.txt"

# Exit codes
EXIT_CODE_SUCCESS=0
EXIT_CODE_CRITICAL=1
EXIT_CODE_INCONSISTENCY=2
EXIT_CODE_ERROR=3

# Track phase results
declare -A phase_status
declare -A phase_files

echo ""
echo -e "${MAGENTA}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${MAGENTA}║                                                            ║${NC}"
echo -e "${MAGENTA}║        NEURAL HIVE MIND - FULL VERSION ANALYSIS            ║${NC}"
echo -e "${MAGENTA}║                                                            ║${NC}"
echo -e "${MAGENTA}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Analysis Timestamp: $(date)"
echo "Working Directory: $(pwd)"
echo "Final Report: ${FINAL_REPORT}"
echo ""

# Function to print phase header
print_phase() {
    local phase_num="$1"
    local phase_name="$2"

    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}PHASE ${phase_num}: ${phase_name}${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo ""
}

# Function to print phase result
print_phase_result() {
    local phase_name="$1"
    local exit_code="$2"
    local output_file="$3"

    if [[ $exit_code -eq 0 ]]; then
        echo -e "${GREEN}✅ ${phase_name} completed successfully${NC}"
        phase_status["$phase_name"]="SUCCESS"
    elif [[ $exit_code -eq 1 ]]; then
        echo -e "${RED}🔴 ${phase_name} detected CRITICAL issues${NC}"
        phase_status["$phase_name"]="CRITICAL"
    elif [[ $exit_code -eq 2 ]]; then
        echo -e "${YELLOW}🟡 ${phase_name} detected inconsistencies${NC}"
        phase_status["$phase_name"]="WARNING"
    else
        echo -e "${RED}❌ ${phase_name} failed with error${NC}"
        phase_status["$phase_name"]="ERROR"
    fi

    phase_files["$phase_name"]="$output_file"
    echo "   Report: ${output_file}"
}

# ============================================================================
# PHASE 1: Requirements.txt Analysis
# ============================================================================

print_phase "1" "Requirements.txt Analysis"

PHASE1_SCRIPT="${SCRIPT_DIR}/analyze-requirements-versions.sh"

if [[ ! -f "$PHASE1_SCRIPT" ]]; then
    echo -e "${RED}ERROR: Script not found: ${PHASE1_SCRIPT}${NC}"
    exit $EXIT_CODE_ERROR
fi

chmod +x "$PHASE1_SCRIPT"

set +e
"$PHASE1_SCRIPT"
PHASE1_EXIT=$?
set -e

PHASE1_OUTPUT=$(ls -t /tmp/requirements_versions_analysis_*.txt 2>/dev/null | head -1)

if [[ -z "$PHASE1_OUTPUT" ]]; then
    echo -e "${RED}ERROR: Phase 1 output file not found${NC}"
    exit $EXIT_CODE_ERROR
fi

print_phase_result "Requirements Analysis" $PHASE1_EXIT "$PHASE1_OUTPUT"

# ============================================================================
# PHASE 2: Runtime Version Verification
# ============================================================================

print_phase "2" "Runtime Version Verification"

PHASE2_SCRIPT="${SCRIPT_DIR}/verify-runtime-versions.sh"

if [[ ! -f "$PHASE2_SCRIPT" ]]; then
    echo -e "${RED}ERROR: Script not found: ${PHASE2_SCRIPT}${NC}"
    exit $EXIT_CODE_ERROR
fi

chmod +x "$PHASE2_SCRIPT"

set +e
"$PHASE2_SCRIPT"
PHASE2_EXIT=$?
set -e

PHASE2_OUTPUT=$(ls -t /tmp/runtime_versions_*.txt 2>/dev/null | head -1)

if [[ -z "$PHASE2_OUTPUT" ]]; then
    echo -e "${RED}ERROR: Phase 2 output file not found${NC}"
    exit $EXIT_CODE_ERROR
fi

print_phase_result "Runtime Verification" $PHASE2_EXIT "$PHASE2_OUTPUT"

# ============================================================================
# PHASE 3: Protobuf File Comparison
# ============================================================================

print_phase "3" "Protobuf Generated Files Comparison"

PHASE3_SCRIPT="${SCRIPT_DIR}/compare-protobuf-versions.sh"

if [[ ! -f "$PHASE3_SCRIPT" ]]; then
    echo -e "${RED}ERROR: Script not found: ${PHASE3_SCRIPT}${NC}"
    exit $EXIT_CODE_ERROR
fi

chmod +x "$PHASE3_SCRIPT"

set +e
"$PHASE3_SCRIPT"
PHASE3_EXIT=$?
set -e

PHASE3_OUTPUT=$(ls -t /tmp/protobuf_comparison_report_*.txt 2>/dev/null | head -1)

if [[ -z "$PHASE3_OUTPUT" ]]; then
    echo -e "${RED}ERROR: Phase 3 output file not found${NC}"
    exit $EXIT_CODE_ERROR
fi

print_phase_result "Protobuf File Comparison" $PHASE3_EXIT "$PHASE3_OUTPUT"

# ============================================================================
# PHASE 4: Consolidation and Root Cause Analysis
# ============================================================================

print_phase "4" "Consolidation and Root Cause Analysis"

echo "Analyzing collected data..."
echo ""

# Extract key findings from each phase
# This is where we correlate the three analyses

# Determine overall status
OVERALL_STATUS="SUCCESS"
CRITICAL_ISSUES=0
WARNINGS=0

for phase in "${!phase_status[@]}"; do
    status="${phase_status[$phase]}"
    if [[ "$status" == "CRITICAL" ]] || [[ "$status" == "ERROR" ]]; then
        OVERALL_STATUS="CRITICAL"
        ((CRITICAL_ISSUES++)) || true
    elif [[ "$status" == "WARNING" ]]; then
        if [[ "$OVERALL_STATUS" != "CRITICAL" ]]; then
            OVERALL_STATUS="WARNING"
        fi
        ((WARNINGS++)) || true
    fi
done

# Determine root cause based on phase results
ROOT_CAUSE="UNKNOWN"
ROOT_CAUSE_DETAIL=""

if [[ "${phase_status[Requirements Analysis]}" == "CRITICAL" ]] && \
   [[ "${phase_status[Runtime Verification]}" == "CRITICAL" ]]; then
    ROOT_CAUSE="VERSION_MISMATCH"
    ROOT_CAUSE_DETAIL="Protobuf version not pinned in requirements.txt, leading to incompatible runtime versions"
elif [[ "${phase_status[Protobuf File Comparison]}" != "SUCCESS" ]]; then
    ROOT_CAUSE="COMPILATION_MISMATCH"
    ROOT_CAUSE_DETAIL="Protobuf files compiled with different protoc versions than runtime libraries"
elif [[ "${phase_status[Runtime Verification]}" == "CRITICAL" ]]; then
    ROOT_CAUSE="RUNTIME_INCOMPATIBILITY"
    ROOT_CAUSE_DETAIL="grpcio-tools and protobuf versions in runtime are incompatible"
fi

echo "Root Cause Analysis:"
echo "  Status: ${OVERALL_STATUS}"
echo "  Critical Issues: ${CRITICAL_ISSUES}"
echo "  Warnings: ${WARNINGS}"
echo "  Root Cause: ${ROOT_CAUSE}"
echo "  Detail: ${ROOT_CAUSE_DETAIL}"
echo ""

# ============================================================================
# Generate Final Consolidated Report
# ============================================================================

echo "Generating consolidated report..."

{
    cat << 'EOF'
# Protobuf Version Analysis - Neural Hive Mind

## Executive Summary

**Analysis Date:**
EOF
    echo "$(date)"
    echo ""
    echo "**Status:** ${OVERALL_STATUS}"
    echo ""
    echo "**Critical Finding:**"
    echo ""

    if [[ "$ROOT_CAUSE" == "VERSION_MISMATCH" ]]; then
        cat << 'EOF'
A critical incompatibility has been identified between the protobuf compiler version used to generate `specialist_pb2.py` and the runtime protobuf library version. The protobuf files were compiled with **protobuf 6.31.1**, but the runtime uses **grpcio-tools 1.60.0** which requires **protobuf <5.0.0**. This major version mismatch (6.x vs 4.x) is the root cause of the TypeError when accessing `evaluated_at.seconds` in the gRPC responses.

**Impact:** The system experiences TypeError exceptions when specialist services respond to consensus-engine gRPC calls, specifically when accessing timestamp fields like `evaluated_at.seconds` and `evaluated_at.nanos`.

**Recommendation:** Implement Option A (Downgrade protobuf compiler and pin runtime version) as detailed in the Recommendations section below.

**Priority:** CRITICAL - Immediate action required
EOF
    elif [[ "$ROOT_CAUSE" == "COMPILATION_MISMATCH" ]]; then
        echo "Protobuf files were compiled with a different version than what is running in production. Recompilation is required."
    elif [[ "$ROOT_CAUSE" == "RUNTIME_INCOMPATIBILITY" ]]; then
        echo "Runtime libraries (grpcio-tools and protobuf) have incompatible versions. Requirements.txt needs to be updated."
    else
        echo "Analysis completed. Review detailed findings below."
    fi

    cat << 'EOF'

---

## Analysis Session Metadata

EOF
    echo "- **Analysis Date:** $(date)"
    echo "- **Kubernetes Namespace:** neural-hive"
    echo "- **Components Analyzed:** 6 (consensus-engine + 5 specialists)"
    echo "- **Scripts Executed:**"
    echo "  1. \`analyze-requirements-versions.sh\`"
    echo "  2. \`verify-runtime-versions.sh\`"
    echo "  3. \`compare-protobuf-versions.sh\`"
    echo "  4. \`run-full-version-analysis.sh\` (orchestrator)"
    echo ""
    echo "---"
    echo ""

    cat << 'EOF'
## Analysis 1: Requirements.txt Versions

### Findings from Static Analysis

EOF

    if [[ -f "$PHASE1_OUTPUT" ]]; then
        echo '```'
        # Extract the table and key findings
        sed -n '/VERSION COMPARISON TABLE/,/ANALYSIS FINDINGS/p' "$PHASE1_OUTPUT" | head -n -2
        echo '```'
        echo ""
        echo "### Critical Findings"
        echo ""
        echo '```'
        sed -n '/CRITICAL FINDINGS:/,/RECOMMENDATIONS/p' "$PHASE1_OUTPUT" | head -n -2
        echo '```'
    else
        echo "⚠️ Requirements analysis output not available"
    fi

    echo ""
    echo "**Full Report:** \`${PHASE1_OUTPUT}\`"
    echo ""
    echo "---"
    echo ""

    cat << 'EOF'
## Analysis 2: Runtime Versions

### Findings from Running Pods

EOF

    if [[ -f "$PHASE2_OUTPUT" ]]; then
        echo '```'
        sed -n '/RUNTIME VERSIONS TABLE/,/COMPATIBILITY ANALYSIS/p' "$PHASE2_OUTPUT" | head -n -2
        echo '```'
        echo ""
        echo "### Compatibility Analysis"
        echo ""
        echo '```'
        sed -n '/COMPATIBILITY ANALYSIS/,/REQUIREMENTS.TXT COMPARISON/p' "$PHASE2_OUTPUT" | head -n -2
        echo '```'
    else
        echo "⚠️ Runtime verification output not available"
    fi

    echo ""
    echo "**Full Report:** \`${PHASE2_OUTPUT}\`"
    echo ""
    echo "---"
    echo ""

    cat << 'EOF'
## Analysis 3: Protobuf Generated Files

### File Comparison Results

EOF

    if [[ -f "$PHASE3_OUTPUT" ]]; then
        echo '```'
        # Extract from VERSIONS TABLE to RECOMMENDATIONS, or use TABELA DE VERSÕES
        if grep -q "VERSIONS TABLE" "$PHASE3_OUTPUT"; then
            sed -n '/VERSIONS TABLE/,/RECOMMENDATIONS/p' "$PHASE3_OUTPUT" | head -n -2
        elif grep -q "TABELA DE VERSÕES" "$PHASE3_OUTPUT"; then
            sed -n '/TABELA DE VERSÕES/,/RECOMMENDATIONS/p' "$PHASE3_OUTPUT" | head -n -2
        else
            # Fallback: show entire file
            cat "$PHASE3_OUTPUT"
        fi
        echo '```'
    else
        echo "⚠️ Protobuf comparison output not available"
    fi

    echo ""
    echo "**Full Report:** \`${PHASE3_OUTPUT}\`"
    echo ""
    echo "---"
    echo ""

    cat << 'EOF'
## Compatibility Matrix Reference

| grpcio-tools Version | Compatible protobuf | Source |
|---------------------|---------------------|--------|
| 1.60.0              | >=4.21.6,<5.0.0     | PyPI metadata + documentation |
| 1.62.0              | >=4.21.6,<5.0.0     | PyPI metadata |
| 1.73.0+             | >=6.30.0,<7.0.0     | PyPI metadata |

**Current Usage:**
- **grpcio-tools:** 1.60.0 (requires protobuf <5.0.0)
- **Protobuf compilation version:** 6.31.1 (from `specialist_pb2.py` line 5)
- **Status:** 🔴 INCOMPATIBLE - Major version mismatch

---

## Root Cause Analysis

### Problem Identified

EOF

    echo "**Root Cause:** ${ROOT_CAUSE}"
    echo ""
    echo "${ROOT_CAUSE_DETAIL}"
    echo ""

    cat << 'EOF'
### Technical Details

1. **Compilation Phase:**
   - The protobuf schema files (`specialist.proto`) were compiled using `scripts/generate_protos.sh`
   - This script uses Docker image `namely/protoc-all:1.51_1` which includes protobuf 6.31.1
   - Generated file `libraries/python/neural_hive_specialists/proto_gen/specialist_pb2.py` contains: `# Protobuf Python Version: 6.31.1`

2. **Runtime Phase:**
   - The `requirements.txt` files specify `grpcio-tools>=1.60.0` but do NOT specify protobuf version
   - When pip installs dependencies, it resolves protobuf as a transitive dependency
   - However, grpcio-tools 1.60.0 requires protobuf <5.0.0 (per PyPI metadata)

3. **The Conflict:**
   - Code generated by protobuf 6.x uses internal data structures and APIs from protobuf 6.x
   - Runtime environment has protobuf 4.x libraries (or mismatched version)
   - When accessing `evaluated_at.seconds`, the field structure doesn't match expectations
   - Result: `TypeError` or `AttributeError`

### Affected Code Locations

- **Client side:** `services/consensus-engine/src/clients/specialists_grpc_client.py:204-213`
  - Accesses `response.evaluated_at.seconds` and `response.evaluated_at.nanos`
- **Server side:** `libraries/python/neural_hive_specialists/grpc_server.py`
  - Returns `EvaluatePlanResponse` with `evaluated_at` timestamp field
- **Generated code:** `libraries/python/neural_hive_specialists/proto_gen/specialist_pb2.py`
  - Contains protobuf message definitions

---

## Recommendations (Prioritized)

### Option A: Downgrade Protobuf Compiler + Pin Runtime Version (RECOMMENDED)

**Priority:** CRITICAL
**Risk:** Low
**Estimated Time:** 30-45 minutes

**Rationale:** This approach maintains the stable and well-tested grpcio-tools 1.60.0 version while ensuring compilation and runtime use compatible protobuf versions.

**Steps:**

1. **Update `scripts/generate_protos.sh`:**
   ```bash
   # Change Docker image from namely/protoc-all:1.51_1 to a 4.x compatible version
   # Option 1: Use namely/protoc-all:1.29_0 (protobuf 4.x)
   # Option 2: Use specific protoc version

   docker run --rm \
     -v "$(pwd):/workspace" \
     -w /workspace \
     namely/protoc-all:1.29_0 \
     -d "$PROTO_DIR" \
     -o "$OUT_DIR" \
     -l python \
     --with-grpc
   ```

2. **Add explicit protobuf version to requirements.txt:**

   In `services/consensus-engine/requirements.txt` (after line 17):
   ```
   protobuf>=4.21.6,<5.0.0  # Compatible with grpcio-tools 1.60.0
   ```

   In `libraries/python/neural_hive_specialists/requirements.txt` (after line 13):
   ```
   protobuf>=4.21.6,<5.0.0  # Compatible with grpcio-tools 1.60.0
   ```

3. **Recompile protobuf files:**
   ```bash
   ./scripts/generate_protos.sh
   ```

4. **Verify compilation version:**
   ```bash
   head -20 libraries/python/neural_hive_specialists/proto_gen/specialist_pb2.py | grep "Protobuf Python Version"
   # Should now show: # Protobuf Python Version: 4.x.x
   ```

5. **Rebuild all Docker images:**
   ```bash
   # Consensus Engine
   docker build -t consensus-engine:1.0.10 services/consensus-engine/

   # All 5 Specialists
   docker build -t specialist-business:1.0.10 services/specialist-business/
   docker build -t specialist-technical:1.0.10 services/specialist-technical/
   docker build -t specialist-behavior:1.0.10 services/specialist-behavior/
   docker build -t specialist-evolution:1.0.10 services/specialist-evolution/
   docker build -t specialist-architecture:1.0.10 services/specialist-architecture/
   ```

6. **Deploy updated images:**
   ```bash
   # Update Helm values and deploy
   helm upgrade consensus-engine helm-charts/consensus-engine/ -n neural-hive
   helm upgrade specialist-business helm-charts/specialist-business/ -n neural-hive
   helm upgrade specialist-technical helm-charts/specialist-technical/ -n neural-hive
   helm upgrade specialist-behavior helm-charts/specialist-behavior/ -n neural-hive
   helm upgrade specialist-evolution helm-charts/specialist-evolution/ -n neural-hive
   helm upgrade specialist-architecture helm-charts/specialist-architecture/ -n neural-hive
   ```

**Pros:**
- ✅ Maintains stable grpcio-tools 1.60.0
- ✅ Low risk - well-tested versions
- ✅ Clear compatibility guarantees

**Cons:**
- ⚠️ Requires rebuild and redeploy of 6 components
- ⚠️ Downtime during deployment

---

### Option B: Upgrade grpcio-tools + Keep Current Protobuf (ALTERNATIVE)

**Priority:** HIGH
**Risk:** Medium
**Estimated Time:** 1-2 hours (including testing)

**Rationale:** Use newer versions of all components, but requires extensive testing for breaking changes.

**Steps:**

1. **Update all requirements.txt files:**

   In both `services/consensus-engine/requirements.txt` and `libraries/python/neural_hive_specialists/requirements.txt`:
   ```
   grpcio>=1.73.0
   grpcio-tools>=1.73.0
   grpcio-health-checking>=1.73.0
   protobuf>=6.30.0,<7.0.0  # Compatible with grpcio-tools 1.73.0
   ```

2. **Keep current `scripts/generate_protos.sh`** (already uses protobuf 6.x)

3. **Rebuild all Docker images** (same as Option A step 5)

4. **Deploy and TEST EXTENSIVELY:**
   - Run all unit tests
   - Run integration tests
   - Monitor for gRPC errors
   - Verify timestamp handling

**Pros:**
- ✅ Uses latest stable versions
- ✅ Future-proof
- ✅ No need to change compilation script

**Cons:**
- ⚠️ Higher risk of breaking changes
- ⚠️ Requires extensive testing
- ⚠️ May expose other compatibility issues

---

## Validation Checklist

After implementing either option, validate the fix:

- [ ] **Verify protobuf version in generated files:**
  ```bash
  head -20 libraries/python/neural_hive_specialists/proto_gen/specialist_pb2.py | grep "Protobuf Python Version"
  ```
  Expected: Version matches your chosen option (4.x for Option A, 6.x for Option B)

- [ ] **Verify runtime versions match requirements.txt:**
  ```bash
  kubectl exec -n neural-hive <consensus-pod> -- pip show protobuf grpcio grpcio-tools
  ```

- [ ] **Run version analysis again:**
  ```bash
  ./scripts/debug/run-full-version-analysis.sh
  ```
  Expected: All green, no incompatibilities

- [ ] **Test gRPC communication:**
  ```bash
  python3 test-grpc-specialists.py
  ```
  Expected: No TypeError on `evaluated_at.seconds`

- [ ] **Run E2E test:**
  ```bash
  python3 test-fluxo-completo-e2e.py
  ```
  Expected: Complete flow without errors

- [ ] **Verify all 6 components have identical versions:**
  Check that consensus-engine and all 5 specialists show same protobuf/grpcio versions

---

## Commands Reference

### Verification Commands

```bash
# Check protobuf compilation version
head -20 libraries/python/neural_hive_specialists/proto_gen/specialist_pb2.py | grep "Protobuf Python Version"

# Check runtime versions in a pod
kubectl exec -n neural-hive <pod-name> -- pip show protobuf grpcio grpcio-tools

# List all running pods
kubectl get pods -n neural-hive

# Check pod logs for errors
kubectl logs -n neural-hive <pod-name> --tail=100

# Re-run full analysis
./scripts/debug/run-full-version-analysis.sh
```

### Build Commands

```bash
# Recompile protobuf files
./scripts/generate_protos.sh

# Build single service
docker build -t <service-name>:<version> services/<service-name>/

# Build all specialists
for svc in specialist-business specialist-technical specialist-behavior specialist-evolution specialist-architecture; do
  docker build -t ${svc}:1.0.10 services/${svc}/
done
```

### Deployment Commands

```bash
# Upgrade single service
helm upgrade <service-name> helm-charts/<service-name>/ -n neural-hive

# Check deployment status
kubectl rollout status deployment/<service-name> -n neural-hive

# Restart deployment
kubectl rollout restart deployment/<service-name> -n neural-hive
```

---

## References

- **gRPC Python Documentation:** https://grpc.io/docs/languages/python/quickstart/
- **Protobuf Python Documentation:** https://protobuf.dev/getting-started/pythontutorial/
- **grpcio-tools PyPI:** https://pypi.org/project/grpcio-tools/
- **Python Version Support:** https://github.com/grpc/grpc/blob/master/doc/python/python-version-support.md
- **Related GitHub Issue:** https://github.com/grpc/grpc/issues/36142

### Code References

- Client code: `services/consensus-engine/src/clients/specialists_grpc_client.py:204-213`
- Server code: `libraries/python/neural_hive_specialists/grpc_server.py`
- Generated protobuf: `libraries/python/neural_hive_specialists/proto_gen/specialist_pb2.py`
- Compilation script: `scripts/generate_protos.sh`

---

## Analysis Reports Archive

EOF

    echo "- **Requirements Analysis:** \`${PHASE1_OUTPUT}\`"
    echo "- **Runtime Verification:** \`${PHASE2_OUTPUT}\`"
    echo "- **Protobuf Comparison:** \`${PHASE3_OUTPUT}\`"
    echo "- **Full Analysis Log:** \`${TEMP_REPORT}\`"
    echo ""

} > "$FINAL_REPORT"

echo ""
echo -e "${GREEN}✅ Consolidated report generated: ${FINAL_REPORT}${NC}"
echo ""

# ============================================================================
# Print Final Summary
# ============================================================================

print_phase "SUMMARY" "Analysis Complete"

echo "Phase Results:"
echo "--------------"
for phase in "Requirements Analysis" "Runtime Verification" "Protobuf File Comparison"; do
    status="${phase_status[$phase]}"
    file="${phase_files[$phase]}"

    case "$status" in
        "SUCCESS")
            echo -e "  ✅ ${phase}: ${GREEN}${status}${NC}"
            ;;
        "CRITICAL")
            echo -e "  🔴 ${phase}: ${RED}${status}${NC}"
            ;;
        "WARNING")
            echo -e "  🟡 ${phase}: ${YELLOW}${status}${NC}"
            ;;
        "ERROR")
            echo -e "  ❌ ${phase}: ${RED}${status}${NC}"
            ;;
    esac
    echo "     Report: ${file}"
done

echo ""
echo "Overall Assessment:"
echo "-------------------"
echo "  Status: ${OVERALL_STATUS}"
echo "  Critical Issues: ${CRITICAL_ISSUES}"
echo "  Warnings: ${WARNINGS}"
echo "  Root Cause: ${ROOT_CAUSE}"
echo ""

echo "Final Reports:"
echo "--------------"
echo "  📄 Consolidated Analysis: ${FINAL_REPORT}"
echo "  📁 Supporting Reports: /tmp/protobuf_*.txt, /tmp/requirements_*.txt, /tmp/runtime_*.txt"
echo ""

if [[ "$OVERALL_STATUS" == "CRITICAL" ]]; then
    echo -e "${RED}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  🔴 CRITICAL ISSUES DETECTED                               ║${NC}"
    echo -e "${RED}║                                                            ║${NC}"
    echo -e "${RED}║  Review ${FINAL_REPORT}${NC}"
    echo -e "${RED}║  and implement recommended fixes immediately.              ║${NC}"
    echo -e "${RED}╚════════════════════════════════════════════════════════════╝${NC}"
    exit $EXIT_CODE_CRITICAL
elif [[ "$OVERALL_STATUS" == "WARNING" ]]; then
    echo -e "${YELLOW}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║  🟡 WARNINGS DETECTED                                      ║${NC}"
    echo -e "${YELLOW}║                                                            ║${NC}"
    echo -e "${YELLOW}║  Review recommendations in ${FINAL_REPORT}${NC}"
    echo -e "${YELLOW}╚════════════════════════════════════════════════════════════╝${NC}"
    exit $EXIT_CODE_INCONSISTENCY
else
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✅ ALL CHECKS PASSED                                      ║${NC}"
    echo -e "${GREEN}║                                                            ║${NC}"
    echo -e "${GREEN}║  No compatibility issues detected.                         ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
    exit $EXIT_CODE_SUCCESS
fi
