#!/bin/bash
# Script para gerar arquivos protobuf Python

set -e

PROTO_DIR="schemas/specialist-opinion"
OUT_DIR="libraries/python/neural_hive_specialists/proto_gen"

echo "Gerando arquivos protobuf..."

# Criar diretório de saída
mkdir -p "$OUT_DIR"

# Gerar via grpcio-tools pinado (mesmo toolchain dos requirements: grpcio-tools==1.68.1
# -> gencode protobuf 5.28.x, compatível com o runtime protobuf 5.29.x).
#
# Antes usava o Docker `namely/protoc-all:1.29_0`, cujo protoc obsoleto (pré-3.19) gerava
# stubs incompatíveis com protobuf>=4: o campo `map<string,string>` perdia a semântica de
# map (tratado como `repeated ContextEntry`) e disparava em runtime
# "RepeatedCompositeFieldContainer object does not support item assignment" e
# "Descriptors cannot be created directly". Isso dessincronizava o stub regenerado no CI
# do stub commitado (gerado com protoc 5.28.1) e fazia falhar os testes de contrato gRPC.
python3 -m grpc_tools.protoc \
  -I "$PROTO_DIR" \
  --python_out="$OUT_DIR" \
  --grpc_python_out="$OUT_DIR" \
  "$PROTO_DIR"/*.proto

# Corrigir imports nos arquivos gerados (import X_pb2 -> from . import X_pb2)
find "$OUT_DIR" -name "*.py" -exec sed -i 's/^import \([^ ]*\)_pb2/from . import \1_pb2/' {} \;

echo "Arquivos protobuf gerados com sucesso em $OUT_DIR"
