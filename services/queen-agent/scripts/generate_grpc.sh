#!/bin/bash
# Script para gerar stubs gRPC Python a partir do proto

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PROTO_DIR="$PROJECT_ROOT/src/proto"
OUT_DIR="$PROJECT_ROOT/src/proto"

echo "Gerando stubs gRPC Python..."
echo "Proto dir: $PROTO_DIR"
echo "Output dir: $OUT_DIR"

# Gerar stubs Python
python -m grpc_tools.protoc \
    -I"$PROTO_DIR" \
    --python_out="$OUT_DIR" \
    --grpc_python_out="$OUT_DIR" \
    --pyi_out="$OUT_DIR" \
    "$PROTO_DIR/queen_agent.proto"

echo "Stubs gerados com sucesso!"
echo "Arquivos criados:"
echo "  - queen_agent_pb2.py"
echo "  - queen_agent_pb2_grpc.py"
echo "  - queen_agent_pb2.pyi"
