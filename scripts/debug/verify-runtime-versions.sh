#!/bin/bash

################################################################################
# Script: verify-runtime-versions.sh
# Purpose: Verify protobuf/grpcio versions installed in running pods
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
NC='\033[0m' # No Color

# Configuration
NAMESPACE="${NAMESPACE:-neural-hive}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
OUTPUT_FILE="/tmp/runtime_versions_${TIMESTAMP}.txt"
REQUIREMENTS_ANALYSIS="/tmp/requirements_versions_analysis_*.txt"

# Associative arrays for runtime versions
declare -A runtime_protobuf
declare -A runtime_grpcio
declare -A runtime_grpcio_tools
declare -A runtime_grpcio_health
declare -A pod_status

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}Runtime Version Verification${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
echo "Timestamp: $(date)"
echo "Namespace: ${NAMESPACE}"
echo "Output file: ${OUTPUT_FILE}"
echo ""

# Check prerequisites
echo -e "${BLUE}Checking prerequisites...${NC}"
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}✗ kubectl not found${NC}"
    echo "Please install kubectl to use this script."
    exit 1
fi

if ! kubectl cluster-info &> /dev/null; then
    echo -e "${RED}✗ Cannot connect to Kubernetes cluster${NC}"
    echo "Please ensure:"
    echo "  1. Kubernetes cluster is running"
    echo "  2. kubectl is configured correctly"
    echo "  3. Current context is set: kubectl config current-context"
    exit 1
fi

echo -e "${GREEN}✓ kubectl found and cluster accessible${NC}"
echo ""

# Function to get pod version for a package
get_pod_version() {
    local pod_name="$1"
    local package="$2"
    local namespace="$3"

    # Try pip show first
    local output
    output=$(kubectl exec -n "$namespace" "$pod_name" -- pip show "$package" 2>/dev/null || echo "")

    # If pip didn't work, try python -m pip
    if [[ -z "$output" ]]; then
        output=$(kubectl exec -n "$namespace" "$pod_name" -- python -m pip show "$package" 2>/dev/null || echo "")
        if [[ -n "$output" ]]; then
            echo "  [Using 'python -m pip' for $package in $pod_name]" >&2
        fi
    fi

    # If still empty, try pip3
    if [[ -z "$output" ]]; then
        output=$(kubectl exec -n "$namespace" "$pod_name" -- pip3 show "$package" 2>/dev/null || echo "")
        if [[ -n "$output" ]]; then
            echo "  [Using 'pip3' for $package in $pod_name]" >&2
        fi
    fi

    # If all methods failed, return NOT_INSTALLED
    if [[ -z "$output" ]]; then
        echo "NOT_INSTALLED"
        return
    fi

    # Extract version line
    local version
    version=$(echo "$output" | grep "^Version:" | awk '{print $2}')

    if [[ -z "$version" ]]; then
        echo "UNKNOWN"
    else
        echo "$version"
    fi
}

# Function to check compatibility
# Compatibility matrix:
# - grpcio-tools 1.60-1.62: requires protobuf >=4.21.6,<5.0.0
# - grpcio-tools 1.73+: requires protobuf >=6.30.0,<7.0.0
check_compatibility() {
    local grpcio_tools_ver="$1"
    local protobuf_ver="$2"

    # Extract version components
    local grpcio_tools_major grpcio_tools_minor
    local protobuf_major protobuf_minor protobuf_patch

    grpcio_tools_major=$(echo "$grpcio_tools_ver" | cut -d'.' -f1)
    grpcio_tools_minor=$(echo "$grpcio_tools_ver" | cut -d'.' -f2)

    protobuf_major=$(echo "$protobuf_ver" | cut -d'.' -f1)
    protobuf_minor=$(echo "$protobuf_ver" | cut -d'.' -f2)
    protobuf_patch=$(echo "$protobuf_ver" | cut -d'.' -f3)

    # Default values if parsing fails
    grpcio_tools_major=${grpcio_tools_major:-0}
    grpcio_tools_minor=${grpcio_tools_minor:-0}
    protobuf_major=${protobuf_major:-0}
    protobuf_minor=${protobuf_minor:-0}

    # grpcio-tools 1.60-1.62 requires protobuf >=4.21.6,<5.0.0
    if [[ "$grpcio_tools_major" == "1" ]] && [[ "$grpcio_tools_minor" -ge 60 ]] && [[ "$grpcio_tools_minor" -le 62 ]]; then
        if [[ "$protobuf_major" == "4" ]]; then
            # Check minimum version 4.21.6
            if [[ "$protobuf_minor" -gt 21 ]] || \
               [[ "$protobuf_minor" == "21" && "${protobuf_patch:-0}" -ge 6 ]]; then
                echo "COMPATIBLE"
            else
                echo "INCOMPATIBLE"
            fi
        else
            echo "INCOMPATIBLE"
        fi
    # grpcio-tools 1.73+ requires protobuf >=6.30.0,<7.0.0
    elif [[ "$grpcio_tools_major" == "1" ]] && [[ "$grpcio_tools_minor" -ge 73 ]]; then
        if [[ "$protobuf_major" == "6" ]]; then
            # Check minimum version 6.30.0
            if [[ "$protobuf_minor" -ge 30 ]]; then
                echo "COMPATIBLE"
            else
                echo "INCOMPATIBLE"
            fi
        else
            echo "INCOMPATIBLE"
        fi
    else
        echo "UNKNOWN"
    fi
}

# Discover pods
echo -e "${BLUE}Discovering pods in namespace ${NAMESPACE}...${NC}"

# Component list
COMPONENTS=(
    "consensus-engine"
    "specialist-business"
    "specialist-technical"
    "specialist-behavior"
    "specialist-evolution"
    "specialist-architecture"
)

ALL_PODS=()

# Find pods using multiple label strategies (matching compare-protobuf-versions.sh)
for component in "${COMPONENTS[@]}"; do
    # Try app.kubernetes.io/name label first
    POD_NAME=$(kubectl get pod -n "$NAMESPACE" -l "app.kubernetes.io/name=${component}" -o jsonpath='{.items[?(@.status.phase=="Running")].metadata.name}' 2>/dev/null | awk '{print $1}')

    # Fallback to app label
    if [[ -z "$POD_NAME" ]]; then
        POD_NAME=$(kubectl get pod -n "$NAMESPACE" -l "app=${component}" -o jsonpath='{.items[?(@.status.phase=="Running")].metadata.name}' 2>/dev/null | awk '{print $1}')
    fi

    # Fallback to component label
    if [[ -z "$POD_NAME" ]]; then
        POD_NAME=$(kubectl get pod -n "$NAMESPACE" -l "component=${component}" -o jsonpath='{.items[?(@.status.phase=="Running")].metadata.name}' 2>/dev/null | awk '{print $1}')
    fi

    if [[ -n "$POD_NAME" ]]; then
        echo "  ✓ Found ${component}: ${POD_NAME}"
        ALL_PODS+=("${component}:${POD_NAME}")
    else
        echo "  ✗ ${component} not found (tried labels: app.kubernetes.io/name, app, component)"
    fi
done

echo ""

if [[ ${#ALL_PODS[@]} -eq 0 ]]; then
    echo -e "${RED}ERROR: No pods found in namespace ${NAMESPACE}${NC}"
    echo "Please check:"
    echo "  1. Namespace exists: kubectl get namespace ${NAMESPACE}"
    echo "  2. Pods are running: kubectl get pods -n ${NAMESPACE}"
    exit 1
fi

# Analyze each pod
echo -e "${BLUE}Analyzing runtime versions...${NC}"

for pod_entry in "${ALL_PODS[@]}"; do
    IFS=':' read -r component pod_name <<< "$pod_entry"

    echo "  - ${component} (${pod_name})"

    # Check if pod is running
    POD_STATUS=$(kubectl get pod -n "$NAMESPACE" "$pod_name" -o jsonpath='{.status.phase}' 2>/dev/null || echo "Unknown")

    if [[ "$POD_STATUS" != "Running" ]]; then
        echo "    ⚠️  Pod status: ${POD_STATUS} - skipping"
        pod_status["$component"]="$POD_STATUS"
        runtime_protobuf["$component"]="POD_NOT_RUNNING"
        runtime_grpcio["$component"]="POD_NOT_RUNNING"
        runtime_grpcio_tools["$component"]="POD_NOT_RUNNING"
        runtime_grpcio_health["$component"]="POD_NOT_RUNNING"
        continue
    fi

    pod_status["$component"]="Running"

    # Get versions
    runtime_protobuf["$component"]=$(get_pod_version "$pod_name" "protobuf" "$NAMESPACE")
    runtime_grpcio["$component"]=$(get_pod_version "$pod_name" "grpcio" "$NAMESPACE")
    runtime_grpcio_tools["$component"]=$(get_pod_version "$pod_name" "grpcio-tools" "$NAMESPACE")
    runtime_grpcio_health["$component"]=$(get_pod_version "$pod_name" "grpcio-health-checking" "$NAMESPACE")

    echo "    protobuf: ${runtime_protobuf[$component]}"
    echo "    grpcio: ${runtime_grpcio[$component]}"
    echo "    grpcio-tools: ${runtime_grpcio_tools[$component]}"
    echo "    grpcio-health-checking: ${runtime_grpcio_health[$component]}"
done

echo ""

# Initialize flags in main scope before generating report
has_incompatible=0
has_inconsistency=0

# Generate report content and redirect to file
exec 3>&1  # Save stdout
exec > "$OUTPUT_FILE"

echo "========================================="
echo "Runtime Version Verification Report"
echo "========================================="
echo ""
echo "Analysis Date: $(date)"
echo "Namespace: ${NAMESPACE}"
echo "Pods Analyzed: ${#ALL_PODS[@]}"
echo ""

echo "========================================="
echo "RUNTIME VERSIONS TABLE"
echo "========================================="
echo ""
printf "%-35s | %-12s | %-15s | %-15s | %-20s | %-10s\n" \
    "Pod Name" "Status" "protobuf" "grpcio" "grpcio-tools" "Compatible"
printf "%-35s-+-%-12s-+-%-15s-+-%-15s-+-%-20s-+-%-10s\n" \
    "-----------------------------------" "------------" "---------------" "---------------" "--------------------" "----------"

for pod_entry in "${ALL_PODS[@]}"; do
    IFS=':' read -r component pod_name <<< "$pod_entry"

    # Check compatibility
    compat="N/A"
    if [[ "${pod_status[$component]}" == "Running" ]]; then
        if [[ "${runtime_grpcio_tools[$component]}" != "NOT_INSTALLED" ]] && \
           [[ "${runtime_protobuf[$component]}" != "NOT_INSTALLED" ]]; then
            compat=$(check_compatibility "${runtime_grpcio_tools[$component]}" "${runtime_protobuf[$component]}")
        fi
    fi

    printf "%-35s | %-12s | %-15s | %-15s | %-20s | %-10s\n" \
        "$component" \
        "${pod_status[$component]}" \
        "${runtime_protobuf[$component]}" \
        "${runtime_grpcio[$component]}" \
        "${runtime_grpcio_tools[$component]}" \
        "$compat"
done

echo ""
echo "========================================="
echo "COMPATIBILITY ANALYSIS"
echo "========================================="
echo ""

# Check for incompatibilities
echo "Compatibility Check:"
echo "--------------------"
for pod_entry in "${ALL_PODS[@]}"; do
    IFS=':' read -r component pod_name <<< "$pod_entry"

    if [[ "${pod_status[$component]}" != "Running" ]]; then
        continue
    fi

    grpcio_tools_ver="${runtime_grpcio_tools[$component]}"
    protobuf_ver="${runtime_protobuf[$component]}"

    if [[ "$grpcio_tools_ver" == "NOT_INSTALLED" ]] || [[ "$protobuf_ver" == "NOT_INSTALLED" ]]; then
        continue
    fi

    compat=$(check_compatibility "$grpcio_tools_ver" "$protobuf_ver")

    if [[ "$compat" == "INCOMPATIBLE" ]]; then
        echo "🔴 CRITICAL: ${component}"
        echo "   grpcio-tools: ${grpcio_tools_ver}"
        echo "   protobuf: ${protobuf_ver}"
        echo "   Status: INCOMPATIBLE"
        echo ""
        has_incompatible=1
    elif [[ "$compat" == "COMPATIBLE" ]]; then
        echo "✅ OK: ${component} - versions compatible"
    fi
done

if [[ $has_incompatible -eq 0 ]]; then
    echo "✅ All running pods have compatible versions"
fi
echo ""

# Check for version consistency across pods
echo "Version Consistency Check:"
echo "--------------------------"

# Get unique protobuf versions
declare -A unique_protobuf
declare -A unique_grpcio_tools

for pod_entry in "${ALL_PODS[@]}"; do
    IFS=':' read -r component pod_name <<< "$pod_entry"

    if [[ "${pod_status[$component]}" == "Running" ]]; then
        pb_ver="${runtime_protobuf[$component]}"
        gt_ver="${runtime_grpcio_tools[$component]}"

        if [[ "$pb_ver" != "NOT_INSTALLED" ]]; then
            unique_protobuf["$pb_ver"]=1
        fi
        if [[ "$gt_ver" != "NOT_INSTALLED" ]]; then
            unique_grpcio_tools["$gt_ver"]=1
        fi
    fi
done

if [[ ${#unique_protobuf[@]} -gt 1 ]]; then
    echo "⚠️  WARNING: Multiple protobuf versions detected across pods"
    echo "   Versions: ${!unique_protobuf[@]}"
    echo ""
    has_inconsistency=1
else
    echo "✅ Protobuf version consistent across all pods"
fi

if [[ ${#unique_grpcio_tools[@]} -gt 1 ]]; then
    echo "⚠️  WARNING: Multiple grpcio-tools versions detected across pods"
    echo "   Versions: ${!unique_grpcio_tools[@]}"
    echo ""
    has_inconsistency=1
else
    echo "✅ grpcio-tools version consistent across all pods"
fi

echo ""

echo "========================================="
echo "REQUIREMENTS.TXT COMPARISON"
echo "========================================="
echo ""

# Try to load requirements analysis if available
req_analysis_file=$(ls -t $REQUIREMENTS_ANALYSIS 2>/dev/null | head -1 || echo "")

if [[ -n "$req_analysis_file" ]] && [[ -f "$req_analysis_file" ]]; then
    echo "Comparing with requirements.txt analysis: ${req_analysis_file}"
    echo ""
    echo "⚠️  Note: Detailed comparison requires manual correlation"
    echo "   Run: ./scripts/debug/run-full-version-analysis.sh for automated analysis"
else
    echo "⚠️  Requirements.txt analysis not found"
    echo "   Run: ./scripts/debug/analyze-requirements-versions.sh first"
fi

echo ""

echo "========================================="
echo "SUMMARY"
echo "========================================="
echo ""

if [[ $has_incompatible -eq 1 ]]; then
    echo "🔴 CRITICAL: Incompatible versions detected!"
    echo "   Action required: Update requirements.txt and rebuild images"
elif [[ $has_inconsistency -eq 1 ]]; then
    echo "🟡 WARNING: Version inconsistencies detected"
    echo "   Recommended: Unify versions across all components"
else
    echo "✅ All versions compatible and consistent"
fi

echo ""

echo "========================================="
echo "RECOMMENDATIONS"
echo "========================================="
echo ""

if [[ $has_incompatible -eq 1 ]]; then
    echo "IMMEDIATE ACTION REQUIRED:"
    echo "-------------------------"
    echo ""
    echo "For pods using grpcio-tools 1.60.x with protobuf 5.x or 6.x:"
    echo ""
    echo "  Option A (Recommended): Downgrade protobuf"
    echo "    1. Update requirements.txt: protobuf>=4.21.6,<5.0.0"
    echo "    2. Rebuild images: docker build ..."
    echo "    3. Redeploy: helm upgrade ..."
    echo ""
    echo "  Option B: Upgrade grpcio-tools"
    echo "    1. Update requirements.txt: grpcio-tools>=1.73.0, protobuf>=6.30.0,<7.0.0"
    echo "    2. Rebuild images: docker build ..."
    echo "    3. Redeploy: helm upgrade ..."
    echo "    4. Test extensively for breaking changes"
    echo ""
fi

echo "NEXT STEPS:"
echo "-----------"
echo "1. Review this report: ${OUTPUT_FILE}"
echo "2. Compare protobuf generated files: ./scripts/debug/compare-protobuf-versions.sh"
echo "3. Run full analysis: ./scripts/debug/run-full-version-analysis.sh"
echo ""

# Restore stdout and display to console
exec >&3
cat "$OUTPUT_FILE"

# Print summary
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Verification Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Report saved to: ${CYAN}${OUTPUT_FILE}${NC}"
echo ""

# Exit with appropriate code
if [[ $has_incompatible -eq 1 ]]; then
    echo -e "${RED}🔴 CRITICAL incompatibilities detected - see report for details${NC}"
    exit 1
elif [[ $has_inconsistency -eq 1 ]]; then
    echo -e "${YELLOW}🟡 Version inconsistencies detected - review recommended${NC}"
    exit 2
else
    echo -e "${GREEN}✅ All versions compatible and consistent${NC}"
    exit 0
fi
