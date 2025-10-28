#!/bin/bash
set -e

echo "🚀 Iniciando deployment local do Neural Hive-Mind"

# Configurar contexto kubectl
echo "📋 Verificando contexto Kubernetes..."
CONTEXT=$(kubectl config current-context)
echo "✅ Usando contexto: $CONTEXT"

# Variáveis de ambiente
export ENV=local
export NAMESPACE_PREFIX=neural-hive

# Verificar se os namespaces foram criados
echo "🏗️ Verificando namespaces..."
kubectl get namespaces | grep neural-hive || {
    echo "❌ Namespaces não encontrados. Criando..."
    kubectl apply -f k8s/bootstrap/namespaces.yaml
}

# Verificar status do Istio
echo "🕸️ Verificando Istio..."
kubectl get pods -n istio-system | grep istiod | grep Running || {
    echo "❌ Istio não está rodando corretamente"
    exit 1
}
echo "✅ Istio está ativo"

# Verificar status do Gatekeeper
echo "🚦 Verificando OPA Gatekeeper..."
if kubectl get pods -n gatekeeper-system | grep -q "Running"; then
    echo "✅ Gatekeeper está ativo"
    GATEKEEPER_READY=true
else
    echo "⏳ Gatekeeper ainda não está pronto"
    GATEKEEPER_READY=false
fi

# Aplicar configurações Istio específicas para Neural Hive
echo "🔐 Aplicando políticas de autenticação Istio..."
kubectl apply -f k8s/bootstrap/istio-auth-policies.yaml

# Deploy de serviços básicos de teste
echo "🧪 Deployando serviços de teste..."

# Criar um deployment de teste simples
cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: neural-test-service
  namespace: neural-hive-system
spec:
  replicas: 1
  selector:
    matchLabels:
      app: neural-test-service
  template:
    metadata:
      labels:
        app: neural-test-service
        version: v1
      annotations:
        sidecar.istio.io/inject: "true"
    spec:
      containers:
      - name: test-service
        image: nginx:alpine
        ports:
        - containerPort: 80
        resources:
          requests:
            cpu: 50m
            memory: 64Mi
          limits:
            cpu: 100m
            memory: 128Mi
        readinessProbe:
          httpGet:
            path: /
            port: 80
          initialDelaySeconds: 5
          periodSeconds: 5
        livenessProbe:
          httpGet:
            path: /
            port: 80
          initialDelaySeconds: 30
          periodSeconds: 30
---
apiVersion: v1
kind: Service
metadata:
  name: neural-test-service
  namespace: neural-hive-system
  labels:
    app: neural-test-service
spec:
  selector:
    app: neural-test-service
  ports:
  - port: 80
    targetPort: 80
    name: http
EOF

# Aguardar o pod estar pronto
echo "⏳ Aguardando serviço de teste estar pronto..."
kubectl wait --for=condition=ready pod -l app=neural-test-service -n neural-hive-system --timeout=120s

# Aplicar políticas Gatekeeper se estiver pronto
if [ "$GATEKEEPER_READY" = true ]; then
    echo "📋 Aplicando constraint templates..."
    kubectl apply -f policies/constraint-templates/ || echo "⚠️ Algumas constraint templates falharam"

    echo "⏳ Aguardando processamento dos templates..."
    sleep 15

    echo "🔒 Aplicando constraints..."
    kubectl apply -f policies/constraints/ || echo "⚠️ Algumas constraints falharam"
else
    echo "⚠️ Pulando configuração de políticas - Gatekeeper não está pronto"
fi

# Status final
echo ""
echo "📊 Status Final do Deployment:"
echo "================================"

echo "🏠 Namespaces:"
kubectl get namespaces | grep neural-hive

echo ""
echo "🧠 Pods por namespace:"
for ns in neural-hive-system neural-hive-cognition neural-hive-orchestration neural-hive-execution neural-hive-observability; do
    echo "  $ns:"
    kubectl get pods -n $ns 2>/dev/null || echo "    Nenhum pod encontrado"
done

echo ""
echo "🌐 Serviços:"
kubectl get svc -n neural-hive-system

echo ""
echo "🚦 Status Gatekeeper:"
if kubectl get pods -n gatekeeper-system &>/dev/null; then
    kubectl get pods -n gatekeeper-system
else
    echo "  Gatekeeper não instalado"
fi

echo ""
echo "✅ Deployment local concluído!"
echo ""
echo "🔧 Comandos úteis:"
echo "  - Verificar todos os pods: kubectl get pods -A | grep neural-hive"
echo "  - Acessar logs do teste: kubectl logs -f deployment/neural-test-service -n neural-hive-system"
echo "  - Port-forward do teste: kubectl port-forward svc/neural-test-service 8080:80 -n neural-hive-system"
echo "  - Kiali dashboard: kubectl port-forward svc/kiali 20001:20001 -n istio-system"
echo "  - Grafana dashboard: kubectl port-forward svc/grafana 3000:3000 -n istio-system"
echo ""
echo "🌟 Neural Hive-Mind local está pronto para desenvolvimento!"