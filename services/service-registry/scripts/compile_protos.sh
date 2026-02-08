#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$(dirname "$SCRIPT_DIR")"
PROTO_DIR="$SERVICE_DIR/src/proto"
OUT_DIR="$SERVICE_DIR/src/proto"
LIB_OUT_DIR="$SERVICE_DIR/../../libraries/neural_hive_integration/neural_hive_integration/proto_stubs"

echo "Compiling Service Registry protos..."
echo "Proto source: $PROTO_DIR"
echo "Server output: $OUT_DIR"
echo "Library output: $LIB_OUT_DIR"

# Ensure output directories exist
mkdir -p "$OUT_DIR"
mkdir -p "$LIB_OUT_DIR"

# Compile for the service (server-side)
python3 -m grpc_tools.protoc \
    -I"$PROTO_DIR" \
    --python_out="$OUT_DIR" \
    --grpc_python_out="$OUT_DIR" \
    --pyi_out="$OUT_DIR" \
    "$PROTO_DIR/service_registry.proto"

# Compile for the library (client-side)
python3 -m grpc_tools.protoc \
    -I"$PROTO_DIR" \
    --python_out="$LIB_OUT_DIR" \
    --grpc_python_out="$LIB_OUT_DIR" \
    --pyi_out="$LIB_OUT_DIR" \
    "$PROTO_DIR/service_registry.proto"

# Fix relative imports for server-side stubs
if [[ "$(uname)" == "Darwin" ]]; then
    # macOS sed requires different syntax
    sed -i '' 's/^import service_registry_pb2/from . import service_registry_pb2/' \
        "$OUT_DIR/service_registry_pb2_grpc.py"
else
    sed -i 's/^import service_registry_pb2/from . import service_registry_pb2/' \
        "$OUT_DIR/service_registry_pb2_grpc.py"
fi

# Fix relative imports for library stubs
if [[ "$(uname)" == "Darwin" ]]; then
    sed -i '' 's/^import service_registry_pb2/from . import service_registry_pb2/' \
        "$LIB_OUT_DIR/service_registry_pb2_grpc.py"
else
    sed -i 's/^import service_registry_pb2/from . import service_registry_pb2/' \
        "$LIB_OUT_DIR/service_registry_pb2_grpc.py"
fi

echo "Proto stubs compiled successfully!"
echo "Generated files:"
ls -la "$OUT_DIR"/service_registry_pb2*.py 2>/dev/null || echo "  (server-side stubs)"
ls -la "$LIB_OUT_DIR"/service_registry_pb2*.py 2>/dev/null || echo "  (library stubs)"
