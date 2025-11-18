#!/bin/bash

################################################################################
# Script: analyze-requirements-versions.sh
# Purpose: Extract and compare protobuf/grpcio versions from requirements.txt
# Author: Neural Hive Mind - Debug Tooling
# Date: 2025-11-10
################################################################################

set -euo pipefail

# Color codes (matching compare-protobuf-versions.sh)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Timestamp for output files
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
OUTPUT_FILE="/tmp/requirements_versions_analysis_${TIMESTAMP}.txt"

# Components to analyze
COMPONENTS=(
    "consensus-engine"
    "specialist-business"
    "specialist-technical"
    "specialist-behavior"
    "specialist-evolution"
    "specialist-architecture"
    "analyst-agents"
    "guard-agents"
    "optimizer-agents"
    "service-registry"
    "memory-layer-api"
    "semantic-translation-engine"
)

# Libraries that share requirements
SHARED_LIBS=(
    "libraries/python/neural_hive_specialists"
    "libraries/python/neural_hive_observability"
)

# Associative arrays to store versions
declare -A protobuf_versions
declare -A grpcio_versions
declare -A grpcio_tools_versions
declare -A grpcio_health_versions
declare -A files_analyzed

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}Requirements.txt Version Analysis${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
echo "Timestamp: $(date)"
echo "Output file: ${OUTPUT_FILE}"
echo ""

# Function to extract version from requirements line
extract_version() {
    local line="$1"
    local package="$2"

    # Remove comments
    line=$(echo "$line" | sed 's/#.*//')

    # Extract version specifier
    if echo "$line" | grep -q "${package}"; then
        # Get everything after package name
        version=$(echo "$line" | sed "s/.*${package}\s*//")
        echo "$version"
    else
        echo "NOT_FOUND"
    fi
}

# Function to analyze a requirements file
analyze_requirements_file() {
    local file_path="$1"
    local component_name="$2"

    if [[ ! -f "$file_path" ]]; then
        protobuf_versions["$component_name"]="FILE_NOT_FOUND"
        grpcio_versions["$component_name"]="FILE_NOT_FOUND"
        grpcio_tools_versions["$component_name"]="FILE_NOT_FOUND"
        grpcio_health_versions["$component_name"]="FILE_NOT_FOUND"
        return
    fi

    files_analyzed["$component_name"]="$file_path"

    # Extract versions for each package
    local protobuf_ver="ABSENT"
    local grpcio_ver="ABSENT"
    local grpcio_tools_ver="ABSENT"
    local grpcio_health_ver="ABSENT"

    while IFS= read -r line; do
        # Skip comments and empty lines
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$line" ]] && continue

        if echo "$line" | grep -q "^protobuf"; then
            protobuf_ver=$(extract_version "$line" "protobuf")
        elif echo "$line" | grep -q "^grpcio-tools"; then
            grpcio_tools_ver=$(extract_version "$line" "grpcio-tools")
        elif echo "$line" | grep -q "^grpcio-health-checking"; then
            grpcio_health_ver=$(extract_version "$line" "grpcio-health-checking")
        elif echo "$line" | grep -q "^grpcio"; then
            grpcio_ver=$(extract_version "$line" "grpcio")
        fi
    done < "$file_path"

    protobuf_versions["$component_name"]="$protobuf_ver"
    grpcio_versions["$component_name"]="$grpcio_ver"
    grpcio_tools_versions["$component_name"]="$grpcio_tools_ver"
    grpcio_health_versions["$component_name"]="$grpcio_health_ver"
}

# Analyze shared libraries first
echo -e "${BLUE}Analyzing shared libraries...${NC}"
for lib in "${SHARED_LIBS[@]}"; do
    req_file="${lib}/requirements.txt"
    lib_name=$(basename "$lib")
    echo "  - ${lib_name}"
    analyze_requirements_file "$req_file" "$lib_name"
done
echo ""

# Analyze service components
echo -e "${BLUE}Analyzing service components...${NC}"
for component in "${COMPONENTS[@]}"; do
    req_file="services/${component}/requirements.txt"
    echo "  - ${component}"
    analyze_requirements_file "$req_file" "$component"
done
echo ""

# Initialize counters in main scope before generating report
explicit_protobuf=0
range_protobuf=0
absent_protobuf=0
has_critical=0

# Count version types
for comp in "${!protobuf_versions[@]}"; do
    ver="${protobuf_versions[$comp]}"
    if [[ "$ver" == "ABSENT" ]] || [[ "$ver" == "FILE_NOT_FOUND" ]]; then
        ((absent_protobuf++)) || true
    elif [[ "$ver" == *"=="* ]]; then
        ((explicit_protobuf++)) || true
    else
        ((range_protobuf++)) || true
    fi
done

# Generate report content and redirect to file
exec 3>&1  # Save stdout
exec > "$OUTPUT_FILE"

echo "========================================="
echo "Requirements.txt Version Analysis Report"
echo "========================================="
echo ""
echo "Analysis Date: $(date)"
echo "Total Components: $((${#SHARED_LIBS[@]} + ${#COMPONENTS[@]}))"
echo ""

echo "Files Analyzed:"
echo "---------------"
for comp in "${!files_analyzed[@]}"; do
    echo "  ${comp}: ${files_analyzed[$comp]}"
done
echo ""

echo "========================================="
echo "VERSION COMPARISON TABLE"
echo "========================================="
echo ""
printf "%-35s | %-20s | %-15s | %-20s | %-25s\n" \
    "Component" "protobuf" "grpcio" "grpcio-tools" "grpcio-health-checking"
printf "%-35s-+-%-20s-+-%-15s-+-%-20s-+-%-25s\n" \
    "-----------------------------------" "--------------------" "---------------" "--------------------" "-------------------------"

# Print shared libraries first
for lib in "${SHARED_LIBS[@]}"; do
    lib_name=$(basename "$lib")
    printf "%-35s | %-20s | %-15s | %-20s | %-25s\n" \
        "$lib_name" \
        "${protobuf_versions[$lib_name]}" \
        "${grpcio_versions[$lib_name]}" \
        "${grpcio_tools_versions[$lib_name]}" \
        "${grpcio_health_versions[$lib_name]}"
done

printf "%-35s-+-%-20s-+-%-15s-+-%-20s-+-%-25s\n" \
    "-----------------------------------" "--------------------" "---------------" "--------------------" "-------------------------"

# Print service components
for component in "${COMPONENTS[@]}"; do
    printf "%-35s | %-20s | %-15s | %-20s | %-25s\n" \
        "$component" \
        "${protobuf_versions[$component]}" \
        "${grpcio_versions[$component]}" \
        "${grpcio_tools_versions[$component]}" \
        "${grpcio_health_versions[$component]}"
done

echo ""
echo "========================================="
echo "ANALYSIS FINDINGS"
echo "========================================="
echo ""

echo "Protobuf Version Status:"
echo "  - Explicit pinned (==x.y.z):     ${explicit_protobuf}"
echo "  - Range without upper bound:     ${range_protobuf}"
echo "  - ABSENT (transitive dependency): ${absent_protobuf}"
echo ""

# Identify critical issues
echo "CRITICAL FINDINGS:"
echo "------------------"

# Check for absent protobuf
if [[ $absent_protobuf -gt 0 ]]; then
    echo "⚠️  CRITICAL: ${absent_protobuf} components do NOT specify protobuf version"
    echo "   Risk: Transitive dependency installation leads to version mismatch"
    echo "   Components affected:"
    for comp in "${!protobuf_versions[@]}"; do
        if [[ "${protobuf_versions[$comp]}" == "ABSENT" ]]; then
            echo "     - ${comp}"
        fi
    done
    echo ""
    has_critical=1
fi

# Check for version conflicts
declare -A unique_grpcio_tools
for comp in "${!grpcio_tools_versions[@]}"; do
    ver="${grpcio_tools_versions[$comp]}"
    if [[ "$ver" != "ABSENT" ]] && [[ "$ver" != "FILE_NOT_FOUND" ]]; then
        unique_grpcio_tools["$ver"]=1
    fi
done

if [[ ${#unique_grpcio_tools[@]} -gt 1 ]]; then
    echo "⚠️  WARNING: Multiple grpcio-tools versions detected"
    echo "   Versions found: ${!unique_grpcio_tools[@]}"
    echo ""
    has_critical=1
fi

# Check for known incompatibilities
for comp in "${!grpcio_tools_versions[@]}"; do
    grpcio_tools_ver="${grpcio_tools_versions[$comp]}"
    protobuf_ver="${protobuf_versions[$comp]}"

    # Check if grpcio-tools 1.60.0 is used
    if echo "$grpcio_tools_ver" | grep -q "1.60.0"; then
        if [[ "$protobuf_ver" == "ABSENT" ]]; then
            echo "🔴 CRITICAL INCOMPATIBILITY: ${comp}"
            echo "   Uses grpcio-tools>=1.60.0 (requires protobuf <5.0.0)"
            echo "   But protobuf is ABSENT (may install incompatible 5.x or 6.x)"
            echo ""
            has_critical=1
        elif echo "$protobuf_ver" | grep -qE "(>=5\.|>=6\.|==5\.|==6\.)"; then
            echo "🔴 CRITICAL INCOMPATIBILITY: ${comp}"
            echo "   Uses grpcio-tools>=1.60.0 (requires protobuf <5.0.0)"
            echo "   But specifies protobuf ${protobuf_ver}"
            echo ""
            has_critical=1
        fi
    fi
done

if [[ $has_critical -eq 0 ]]; then
    echo "✅ No critical incompatibilities detected in requirements.txt"
    echo ""
fi

echo "========================================="
echo "RECOMMENDATIONS"
echo "========================================="
echo ""

echo "PRIORITY 1 - CRITICAL:"
echo "----------------------"
echo "Add explicit protobuf version to all requirements.txt files:"
echo ""
echo "  For components using grpcio-tools 1.60.0:"
echo "    protobuf>=4.21.6,<5.0.0  # Compatible with grpcio-tools 1.60.0"
echo ""
echo "  For components using grpcio-tools 1.73.0+:"
echo "    protobuf>=6.30.0,<7.0.0  # Compatible with grpcio-tools 1.73.0+"
echo ""

echo "PRIORITY 2 - HIGH:"
echo "------------------"
echo "Unify grpcio/grpcio-tools versions across all components"
echo "Recommended stable version: grpcio-tools==1.60.0 with protobuf==4.25.0"
echo ""

echo "PRIORITY 3 - MEDIUM:"
echo "--------------------"
echo "Pin all grpc-related packages with exact versions (==) instead of ranges (>=)"
echo "This prevents unexpected version changes during builds"
echo ""

echo "========================================="
echo "NEXT STEPS"
echo "========================================="
echo ""
echo "1. Review this report: ${OUTPUT_FILE}"
echo "2. Run runtime verification: ./scripts/debug/verify-runtime-versions.sh"
echo "3. Compare protobuf files: ./scripts/debug/compare-protobuf-versions.sh"
echo "4. Execute full analysis: ./scripts/debug/run-full-version-analysis.sh"
echo ""

# Restore stdout and display to console
exec >&3
cat "$OUTPUT_FILE"

# Print summary to console
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Analysis Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Report saved to: ${CYAN}${OUTPUT_FILE}${NC}"
echo ""

# Exit with appropriate code
if [[ $absent_protobuf -gt 0 ]]; then
    echo -e "${RED}⚠️  CRITICAL issues detected - see report for details${NC}"
    exit 1
else
    echo -e "${GREEN}✅ No critical issues detected in requirements.txt${NC}"
    exit 0
fi
