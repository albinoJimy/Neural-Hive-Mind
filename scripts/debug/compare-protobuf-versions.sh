#!/bin/bash

# ==============================================================================
# Compare Protobuf Versions Across Components
# ==============================================================================
# Purpose: Compare specialist_pb2.py versions between consensus-engine and specialists
# References:
#   - libraries/python/neural_hive_specialists/proto_gen/specialist_pb2.py
#   - services/consensus-engine/src/clients/specialists_grpc_client.py
# ==============================================================================

set -euo pipefail

# Configuration
NAMESPACE="${NAMESPACE:-neural-hive}"
COMPONENTS=("consensus-engine" "specialist-business" "specialist-technical" "specialist-behavior" "specialist-evolution" "specialist-architecture")

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Create temporary directory
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Storage for results
declare -A HASHES_PB2
declare -A HASHES_GRPC
declare -A SIZES_PB2
declare -A SIZES_GRPC
declare -A VERSIONS
declare -a DIFF_FILES

echo "========================================"
echo "Compare Protobuf Versions"
echo "Timestamp: $(date -Iseconds)"
echo "Temp directory: $TEMP_DIR"
echo "========================================"
echo ""

# Check prerequisites
echo -e "${BLUE}Checking prerequisites...${NC}"
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}✗ kubectl not found${NC}"
    exit 1
fi

if ! kubectl cluster-info &> /dev/null; then
    echo -e "${RED}✗ Cannot connect to Kubernetes cluster${NC}"
    exit 1
fi

echo -e "${GREEN}✓ kubectl found and cluster accessible${NC}"
echo ""

# Extract protobuf files from each component
for component in "${COMPONENTS[@]}"; do
    echo "========================================"
    echo -e "${YELLOW}Processing: ${component}${NC}"
    echo "========================================"
    echo ""

    # Find pod - try multiple label strategies
    echo -e "${BLUE}Finding pod...${NC}"

    # Try app.kubernetes.io/name label first
    POD=$(kubectl get pod -n "$NAMESPACE" -l "app.kubernetes.io/name=${component}" -o jsonpath='{.items[?(@.status.phase=="Running")].metadata.name}' 2>/dev/null | awk '{print $1}')

    # Fallback to app label
    if [ -z "$POD" ]; then
        POD=$(kubectl get pod -n "$NAMESPACE" -l "app=${component}" -o jsonpath='{.items[?(@.status.phase=="Running")].metadata.name}' 2>/dev/null | awk '{print $1}')
    fi

    # Fallback to component label
    if [ -z "$POD" ]; then
        POD=$(kubectl get pod -n "$NAMESPACE" -l "component=${component}" -o jsonpath='{.items[?(@.status.phase=="Running")].metadata.name}' 2>/dev/null | awk '{print $1}')
    fi

    if [ -z "$POD" ]; then
        echo -e "${RED}✗ No Running pod found for ${component}${NC}"
        echo "  Tried labels: app.kubernetes.io/name, app, component"
        echo "  Skipping this component"
        echo ""
        continue
    fi

    # Check pod status
    POD_STATUS=$(kubectl get pod -n "$NAMESPACE" "$POD" -o jsonpath='{.status.phase}')
    if [ "$POD_STATUS" != "Running" ]; then
        echo -e "${RED}✗ Pod ${POD} is not Running (status: ${POD_STATUS})${NC}"
        echo "  Skipping this component"
        echo ""
        continue
    fi

    echo -e "${GREEN}✓ Pod found: ${POD}${NC}"
    echo "  Status: ${POD_STATUS}"
    echo ""

    # Extract specialist_pb2.py
    echo -e "${BLUE}Extracting specialist_pb2.py...${NC}"

    # Locate package path dynamically
    PACKAGE_PATH=$(kubectl exec -n "$NAMESPACE" "$POD" -- python -c "import neural_hive_specialists, inspect, os; print(os.path.dirname(neural_hive_specialists.__file__))" 2>/dev/null || echo "")

    if [ -z "$PACKAGE_PATH" ]; then
        echo -e "${YELLOW}⚠ Could not locate package dynamically, trying default path${NC}"
        PACKAGE_PATH="/app/libraries/python/neural_hive_specialists"
    else
        echo "  Package path: $PACKAGE_PATH"
    fi

    PB2_PATH="${PACKAGE_PATH}/proto_gen/specialist_pb2.py"

    if kubectl exec -n "$NAMESPACE" "$POD" -- test -f "$PB2_PATH" 2>/dev/null; then
        kubectl exec -n "$NAMESPACE" "$POD" -- cat "$PB2_PATH" > "$TEMP_DIR/${component}_specialist_pb2.py" 2>/dev/null

        if [ -s "$TEMP_DIR/${component}_specialist_pb2.py" ]; then
            MD5=$(md5sum "$TEMP_DIR/${component}_specialist_pb2.py" | awk '{print $1}')
            SIZE=$(wc -l < "$TEMP_DIR/${component}_specialist_pb2.py")

            HASHES_PB2[$component]=$MD5
            SIZES_PB2[$component]=$SIZE

            echo -e "${GREEN}✓ specialist_pb2.py extracted${NC}"
            echo "  Path: $PB2_PATH"
            echo "  MD5: $MD5"
            echo "  Lines: $SIZE"
        else
            echo -e "${RED}✗ Extracted file is empty${NC}"
        fi
    else
        echo -e "${RED}✗ File not found: $PB2_PATH${NC}"
    fi
    echo ""

    # Extract specialist_pb2_grpc.py
    echo -e "${BLUE}Extracting specialist_pb2_grpc.py...${NC}"
    GRPC_PATH="${PACKAGE_PATH}/proto_gen/specialist_pb2_grpc.py"

    if kubectl exec -n "$NAMESPACE" "$POD" -- test -f "$GRPC_PATH" 2>/dev/null; then
        kubectl exec -n "$NAMESPACE" "$POD" -- cat "$GRPC_PATH" > "$TEMP_DIR/${component}_specialist_pb2_grpc.py" 2>/dev/null

        if [ -s "$TEMP_DIR/${component}_specialist_pb2_grpc.py" ]; then
            MD5=$(md5sum "$TEMP_DIR/${component}_specialist_pb2_grpc.py" | awk '{print $1}')
            SIZE=$(wc -l < "$TEMP_DIR/${component}_specialist_pb2_grpc.py")

            HASHES_GRPC[$component]=$MD5
            SIZES_GRPC[$component]=$SIZE

            echo -e "${GREEN}✓ specialist_pb2_grpc.py extracted${NC}"
            echo "  Path: $GRPC_PATH"
            echo "  MD5: $MD5"
            echo "  Lines: $SIZE"
        else
            echo -e "${RED}✗ Extracted file is empty${NC}"
        fi
    else
        echo -e "${RED}✗ File not found: $GRPC_PATH${NC}"
    fi
    echo ""

    # Extract library version
    echo -e "${BLUE}Extracting neuralHiveSpecialists version...${NC}"
    VERSION=$(kubectl exec -n "$NAMESPACE" "$POD" -- pip show neuralHiveSpecialists 2>/dev/null | grep "Version:" | awk '{print $2}' || echo "N/A")

    VERSIONS[$component]=$VERSION
    echo "  Version: $VERSION"
    echo ""
done

# Analyze differences
echo "========================================"
echo "ANÁLISE DE DIFERENÇAS"
echo "========================================"
echo ""

# Use consensus-engine as baseline
BASELINE_HASH_PB2="${HASHES_PB2[consensus-engine]:-}"
BASELINE_HASH_GRPC="${HASHES_GRPC[consensus-engine]:-}"

if [ -z "$BASELINE_HASH_PB2" ]; then
    echo -e "${RED}✗ Could not extract baseline from consensus-engine${NC}"
    echo "Cannot proceed with comparison"
    exit 1
fi

echo -e "${BLUE}Baseline (consensus-engine):${NC}"
echo "  specialist_pb2.py MD5: $BASELINE_HASH_PB2"
echo "  specialist_pb2_grpc.py MD5: $BASELINE_HASH_GRPC"
echo ""

# Compare specialist_pb2.py hashes
echo -e "${BLUE}Comparing specialist_pb2.py:${NC}"
IDENTICAL_COUNT=0
DIFFERENT_COUNT=0

for component in "${COMPONENTS[@]}"; do
    if [ "$component" == "consensus-engine" ]; then
        continue
    fi

    HASH="${HASHES_PB2[$component]:-}"

    if [ -z "$HASH" ]; then
        echo -e "${YELLOW}⚠ ${component}: No hash available (extraction failed)${NC}"
        continue
    fi

    if [ "$HASH" == "$BASELINE_HASH_PB2" ]; then
        echo -e "${GREEN}✓ ${component}: IDÊNTICO ao consensus-engine${NC}"
        ((IDENTICAL_COUNT++))
    else
        echo -e "${RED}✗ ${component}: DIFERENTE do consensus-engine${NC}"
        echo "  Hash: $HASH"
        echo "  Baseline: $BASELINE_HASH_PB2"
        ((DIFFERENT_COUNT++))

        # Generate diff
        echo "  Generating diff..."
        diff -u "$TEMP_DIR/consensus-engine_specialist_pb2.py" "$TEMP_DIR/${component}_specialist_pb2.py" > "$TEMP_DIR/diff_${component}_pb2.txt" || true

        DIFF_LINES=$(wc -l < "$TEMP_DIR/diff_${component}_pb2.txt")
        echo "  Diff lines: $DIFF_LINES"

        if [ "$DIFF_LINES" -gt 0 ]; then
            echo "  First 50 lines of diff:"
            head -n 50 "$TEMP_DIR/diff_${component}_pb2.txt" | sed 's/^/    /'

            # Save permanent copy
            DIFF_FILE="/tmp/protobuf_diff_${component}_pb2_$(date +%Y%m%d_%H%M%S).txt"
            cp "$TEMP_DIR/diff_${component}_pb2.txt" "$DIFF_FILE"
            DIFF_FILES+=("$DIFF_FILE")
            echo "  Full diff saved: $DIFF_FILE"
        fi
    fi
done
echo ""

# Display versions table
echo "========================================"
echo "TABELA DE VERSÕES"
echo "========================================"
echo ""
printf "| %-25s | %-25s | %-20s |\n" "Componente" "Versão neuralHiveSpecialists" "MD5 specialist_pb2.py"
echo "|---------------------------|---------------------------|----------------------|"
for component in "${COMPONENTS[@]}"; do
    VERSION="${VERSIONS[$component]:-N/A}"
    HASH="${HASHES_PB2[$component]:-N/A}"
    printf "| %-25s | %-25s | %-20s |\n" "$component" "$VERSION" "${HASH:0:20}"
done
echo ""

# Analyze evaluated_at definitions
echo "========================================"
echo "ANÁLISE DE DEFINIÇÃO evaluated_at"
echo "========================================"
echo ""

for component in "${COMPONENTS[@]}"; do
    FILE="$TEMP_DIR/${component}_specialist_pb2.py"

    if [ -f "$FILE" ]; then
        echo -e "${BLUE}${component}:${NC}"

        # Extract EvaluatePlanResponse class definition
        grep -A 20 "class EvaluatePlanResponse" "$FILE" > "$TEMP_DIR/${component}_evaluated_at_definition.txt" 2>/dev/null || echo "Class not found" > "$TEMP_DIR/${component}_evaluated_at_definition.txt"

        # Look for evaluated_at field
        if grep -q "evaluated_at" "$TEMP_DIR/${component}_evaluated_at_definition.txt"; then
            grep "evaluated_at" "$TEMP_DIR/${component}_evaluated_at_definition.txt" | sed 's/^/  /'
        else
            echo "  evaluated_at field not found in class definition"
        fi

        echo ""
    fi
done

# Compare evaluated_at definitions
if [ "${DIFFERENT_COUNT}" -gt 0 ]; then
    echo -e "${YELLOW}Comparing evaluated_at definitions:${NC}"

    for component in "${COMPONENTS[@]}"; do
        if [ "$component" == "consensus-engine" ]; then
            continue
        fi

        HASH="${HASHES_PB2[$component]:-}"
        if [ -z "$HASH" ] || [ "$HASH" == "$BASELINE_HASH_PB2" ]; then
            continue
        fi

        echo -e "${BLUE}Diff evaluated_at: consensus-engine vs ${component}${NC}"
        diff -u "$TEMP_DIR/consensus-engine_evaluated_at_definition.txt" "$TEMP_DIR/${component}_evaluated_at_definition.txt" | sed 's/^/  /' || echo "  No differences in evaluated_at definition"
        echo ""
    done
fi

# Generate report
REPORT_FILE="/tmp/protobuf_comparison_report_$(date +%Y%m%d_%H%M%S).txt"

cat > "$REPORT_FILE" <<EOF
========================================
Protobuf Comparison Report
========================================
Generated: $(date -Iseconds)
Namespace: $NAMESPACE

Components Analyzed: ${#COMPONENTS[@]}
Identical files (specialist_pb2.py): $IDENTICAL_COUNT
Different files (specialist_pb2.py): $DIFFERENT_COUNT

========================================
VERSIONS TABLE
========================================

$(printf "| %-25s | %-25s | %-20s |\n" "Component" "neuralHiveSpecialists" "MD5 specialist_pb2.py")
$(echo "|---------------------------|---------------------------|----------------------|")
$(for component in "${COMPONENTS[@]}"; do
    VERSION="${VERSIONS[$component]:-N/A}"
    HASH="${HASHES_PB2[$component]:-N/A}"
    printf "| %-25s | %-25s | %-20s |\n" "$component" "$VERSION" "${HASH:0:20}"
done)

========================================
BASELINE
========================================
Component: consensus-engine
specialist_pb2.py MD5: $BASELINE_HASH_PB2
specialist_pb2_grpc.py MD5: $BASELINE_HASH_GRPC

========================================
DIFF FILES GENERATED
========================================
$(if [ "${#DIFF_FILES[@]}" -gt 0 ]; then
    for df in "${DIFF_FILES[@]}"; do
        if [ -f "$df" ]; then
            ls -lh "$df"
        fi
    done
else
    echo "None (all files identical)"
fi)

========================================
RECOMMENDATIONS
========================================
$(if [ "$DIFFERENT_COUNT" -gt 0 ]; then
    echo "⚠ ACTION REQUIRED: Protobuf version mismatch detected"
    echo ""
    echo "Components with different protobuf files:"
    for component in "${COMPONENTS[@]}"; do
        if [ "$component" == "consensus-engine" ]; then
            continue
        fi
        HASH="${HASHES_PB2[$component]:-}"
        if [ -n "$HASH" ] && [ "$HASH" != "$BASELINE_HASH_PB2" ]; then
            echo "  - $component"
        fi
    done
    echo ""
    echo "Steps to fix:"
    echo "  1. Regenerate protobufs using the same specialist.proto"
    echo "  2. Run: ./libraries/python/neural_hive_specialists/scripts/generate_protos.sh"
    echo "  3. Rebuild all affected Docker images"
    echo "  4. Redeploy all components"
else
    echo "✓ All components use identical protobuf files"
    echo ""
    echo "The TypeError is NOT caused by protobuf version mismatch."
    echo ""
    echo "Suggested next steps:"
    echo "  1. Investigate serialization/deserialization logic"
    echo "  2. Check timeout configurations"
    echo "  3. Review validation code in specialists_grpc_client.py"
    echo "  4. Run test-grpc-isolated.py for detailed error analysis"
fi)

EOF

echo ""
echo "========================================"
echo "RESUMO"
echo "========================================"
echo ""
echo "Total de componentes analisados: ${#COMPONENTS[@]}"
echo "Arquivos idênticos (specialist_pb2.py): $IDENTICAL_COUNT"
echo "Arquivos diferentes (specialist_pb2.py): $DIFFERENT_COUNT"
echo ""

if [ "$DIFFERENT_COUNT" -gt 0 ]; then
    echo -e "${RED}⚠ AÇÃO NECESSÁRIA: Incompatibilidade de protobuf detectada${NC}"
    echo ""
    echo "Componentes com arquivos diferentes:"
    for component in "${COMPONENTS[@]}"; do
        if [ "$component" == "consensus-engine" ]; then
            continue
        fi
        HASH="${HASHES_PB2[$component]:-}"
        if [ -n "$HASH" ] && [ "$HASH" != "$BASELINE_HASH_PB2" ]; then
            echo "  - $component"
        fi
    done
    echo ""
    echo "Recomendação:"
    echo "  1. Regenerar protobufs: ./libraries/python/neural_hive_specialists/scripts/generate_protos.sh"
    echo "  2. Rebuild de todas as imagens Docker"
    echo "  3. Redeploy de todos os componentes"
else
    echo -e "${GREEN}✓ Todos os componentes usam arquivos protobuf idênticos${NC}"
    echo ""
    echo -e "${GREEN}✓ O TypeError NÃO é causado por incompatibilidade de protobuf${NC}"
    echo ""
    echo "Próximas investigações:"
    echo "  1. Executar test-grpc-isolated.py para análise detalhada"
    echo "  2. Revisar lógica de serialização/deserialização"
    echo "  3. Verificar código de validação no cliente"
fi
echo ""

echo "Relatório salvo em: $REPORT_FILE"
echo ""

# Exit code
if [ "$DIFFERENT_COUNT" -gt 0 ]; then
    exit 1
else
    exit 0
fi
