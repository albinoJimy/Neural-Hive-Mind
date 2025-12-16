#!/bin/bash
# Script para exportar imagens Docker para containerd nos worker nodes
# Uso: ./export-images-to-workers.sh [--version VERSION] [--services "service1,service2,..."]

set -e

VERSION="${VERSION:-1.0.8}"
WORKERS=("158.220.101.216" "84.247.138.35")
TEMP_DIR="/tmp/neural-hive-images"
REGISTRY="neural-hive-mind"

# Parse args
while [[ $# -gt 0 ]]; do
  case $1 in
    --version) VERSION="$2"; shift 2 ;;
    --services) IFS=',' read -ra SERVICES <<< "$2"; shift 2 ;;
    *) shift ;;
  esac
done

# Default services (Flow A→C)
if [[ ${#SERVICES[@]} -eq 0 ]]; then
  SERVICES=(
    "gateway-intencoes"
    "semantic-translation-engine"
    "orchestrator-dynamic"
    "consensus-engine"
    "specialist-architecture"
    "specialist-behavior"
    "specialist-business"
    "specialist-evolution"
    "specialist-technical"
  )
fi

mkdir -p "$TEMP_DIR"

echo "=== EXPORTANDO IMAGENS PARA WORKERS ==="
echo "Versão: $VERSION"
echo "Workers: ${WORKERS[*]}"
echo "Total: ${#SERVICES[@]} serviços"
echo ""

export_image() {
  local name=$1
  local image="${REGISTRY}/${name}:${VERSION}"
  local tar_file="${TEMP_DIR}/${name}.tar"

  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "📦 Processando: $name"

  # Verificar se imagem existe
  if ! docker image inspect "$image" &>/dev/null; then
    echo "⚠️  Imagem não encontrada: $image"
    return 1
  fi

  # Salvar imagem
  echo "   → Salvando tar..."
  docker save "$image" > "$tar_file"
  local size=$(du -h "$tar_file" | cut -f1)
  echo "   → Tamanho: $size"

  # Transferir e importar em cada worker
  for worker in "${WORKERS[@]}"; do
    echo "   → Worker $worker: transferindo..."

    # Transferir via pipe (evita espaço em disco no worker)
    cat "$tar_file" | ssh -o StrictHostKeyChecking=no "root@${worker}" \
      "ctr -n k8s.io images import - && echo 'OK'"

    if [[ $? -eq 0 ]]; then
      echo "   ✅ Worker $worker: importado"
    else
      echo "   ❌ Worker $worker: falhou"
    fi
  done

  # Limpar tar local
  rm -f "$tar_file"
  echo "   ✅ $name concluído"
}

# Processar cada serviço
FAILED=()
for svc in "${SERVICES[@]}"; do
  if ! export_image "$svc"; then
    FAILED+=("$svc")
  fi
done

echo ""
echo "=== RESUMO ==="
echo "Sucesso: $((${#SERVICES[@]} - ${#FAILED[@]}))/${#SERVICES[@]}"
if [[ ${#FAILED[@]} -gt 0 ]]; then
  echo "Falhas: ${FAILED[*]}"
fi

# Verificar imagens nos workers
echo ""
echo "=== IMAGENS NOS WORKERS ==="
for worker in "${WORKERS[@]}"; do
  echo "Worker $worker:"
  ssh "root@${worker}" "ctr -n k8s.io images list | grep neural-hive-mind | grep ${VERSION} | wc -l" 2>/dev/null
done

echo ""
echo "✅ Exportação concluída!"
