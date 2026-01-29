#!/bin/bash
# Script para gerar arquivos protobuf Python

set -e

PROTO_DIR="schemas/specialist-opinion"
OUT_DIR="libraries/python/neural_hive_specialists/proto_gen"

echo "Gerando arquivos protobuf..."

# Criar diretório de saída
mkdir -p "$OUT_DIR"

# Gerar usando Docker (evita problemas de dependências locais)
docker run --rm \
  -v "$(pwd):/workspace" \
  -w /workspace \
  namely/protoc-all:1.29_0 \
  -d "$PROTO_DIR" \
  -o "$OUT_DIR" \
  -l python \
  --with-grpc

# Corrigir imports nos arquivos gerados
find "$OUT_DIR" -name "*.py" -exec sed -i 's/^import \([^ ]*\)_pb2/from . import \1_pb2/' {} \;

echo "Arquivos protobuf gerados com sucesso em $OUT_DIR"
