#!/bin/bash
# Neural Hive Internal CA Distribution Script
# Distribui o certificado da CA interna para todos os namespaces que precisam
# confiar nos certificados emitidos por ela

set -euo pipefail

# Configurações
CA_SECRET="neural-hive-ca-secret"
SOURCE_NS="cert-manager"
TARGET_NAMESPACES=(
  "fluxo-a"
  "neural-hive"
  "neural-hive-execution"
  "neural-hive-staging"
  "kafka"
)

echo "=========================================="
echo "Neural Hive CA Distribution"
echo "=========================================="
echo ""

# Verificar se o secret da CA existe
echo "🔍 Verificando se CA existe em ${SOURCE_NS}/${CA_SECRET}..."
if ! kubectl get secret "${CA_SECRET}" -n "${SOURCE_NS}" >/dev/null 2>&1; then
  echo "❌ ERRO: Secret ${CA_SECRET} não encontrado em namespace ${SOURCE_NS}"
  echo "Execute primeiro: kubectl apply -f k8s/certificates/neural-hive-ca.yaml"
  exit 1
fi
echo "✅ CA encontrada"
echo ""

# Extrair CA certificado
echo "📥 Extraindo certificado CA..."
CA_CERT=$(kubectl get secret "${CA_SECRET}" -n "${SOURCE_NS}" -o jsonpath='{.data.ca\.crt}' | base64 -d)

if [ -z "$CA_CERT" ]; then
  echo "❌ ERRO: Não foi possível extrair ca.crt do secret"
  exit 1
fi

echo "✅ Certificado extraído (${#CA_CERT} bytes)"
echo ""

# Distribuir para cada namespace
for ns in "${TARGET_NAMESPACES[@]}"; do
  echo "📤 Distribuindo para namespace: ${ns}"
  
  # Verificar se namespace existe
  if ! kubectl get namespace "${ns}" >/dev/null 2>&1; then
    echo "  ⚠️  Namespace ${ns} não existe, pulando..."
    continue
  fi
  
  # Criar ou atualizar ConfigMap com o certificado CA
  kubectl create configmap neural-hive-ca-bundle \
    --from-literal=ca.crt="$CA_CERT" \
    -n "$ns" \
    --dry-run=client -o yaml | kubectl apply -f - > /dev/null
  
  # Adicionar labels para identificação
  kubectl label configmap neural-hive-ca-bundle \
    neural-hive.io/component=ca-bundle \
    neural-hive.io/source=cert-manager \
    neural-hive.io/managed-by=scripts \
    -n "$ns" \
    --overwrite > /dev/null
  
  echo "  ✅ ConfigMap neural-hive-ca-bundle criado/atualizado"
done

echo ""
echo "=========================================="
echo "✅ CA distribuída com sucesso!"
echo "=========================================="
echo ""
echo "Namespaces atualizados:"
for ns in "${TARGET_NAMESPACES[@]}"; do
  if kubectl get namespace "${ns}" >/dev/null 2>&1; then
    echo "  - ${ns}"
  fi
done
echo ""
echo "💡 Próximos passos:"
echo "  1. Atualizar deployments para montar o ConfigMap"
echo "  2. Reiniciar os pods para aplicar as mudanças"
echo "  3. Verificar se a cadeia de confiança está funcionando"
