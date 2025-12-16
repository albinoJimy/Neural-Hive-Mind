#!/bin/bash
set -eo pipefail
source "$(dirname "$0")/../lib/k8s.sh"

echo "🚀 Configurando acesso aos dashboards do Neural Hive-Mind..."

# Função para verificar se uma porta está em uso
check_port() {
    netstat -tuln 2>/dev/null | grep -q ":$1 " && return 0 || return 1
}

# Função para matar processos usando uma porta específica
kill_port() {
    local port=$1
    local pids=$(lsof -ti:$port 2>/dev/null)
    if [ ! -z "$pids" ]; then
        echo "🔄 Matando processos existentes na porta $port..."
        echo $pids | xargs kill -9 2>/dev/null
        sleep 2
    fi
}

# Função para configurar port-forward
setup_portforward() {
    local service=$1
    local namespace=$2
    local local_port=$3
    local remote_port=$4
    local name=$5

    echo "🔧 Configurando $name..."

    # Matar processos existentes na porta
    kill_port $local_port

    # Configurar port-forward em background
    kubectl port-forward svc/$service $local_port:$remote_port -n $namespace > /dev/null 2>&1 &
    local pid=$!

    # Aguardar um pouco para verificar se funcionou
    sleep 3

    if ps -p $pid > /dev/null 2>&1; then
        echo "✅ $name disponível em: http://localhost:$local_port"
        echo $pid >> /tmp/neural-hive-dashboards.pid
    else
        echo "❌ Falha ao configurar $name"
    fi
}

# Limpar PIDs anteriores
rm -f /tmp/neural-hive-dashboards.pid

echo ""
echo "🔧 Configurando port-forwards..."
echo "================================="

# Kiali - Service Mesh Observability
setup_portforward "kiali" "istio-system" "20001" "20001" "Kiali (Service Mesh)"

# Grafana - Métricas e Dashboards
setup_portforward "grafana" "istio-system" "3000" "3000" "Grafana (Métricas)"

# Prometheus - Métricas Raw
setup_portforward "prometheus" "istio-system" "9090" "9090" "Prometheus (Métricas Raw)"

# Jaeger - Distributed Tracing (usar pod diretamente)
echo "🔧 Configurando Jaeger..."
kill_port 16686
kubectl port-forward pod/$(kubectl get pods -n istio-system -l app=jaeger -o jsonpath='{.items[0].metadata.name}') 16686:16686 -n istio-system > /dev/null 2>&1 &
jaeger_pid=$!
sleep 3
if ps -p $jaeger_pid > /dev/null 2>&1; then
    echo "✅ Jaeger (Tracing) disponível em: http://localhost:16686"
    echo $jaeger_pid >> /tmp/neural-hive-dashboards.pid
else
    echo "❌ Falha ao configurar Jaeger"
fi

# Neural Hive Test Service
echo "🔧 Configurando Serviço de Teste..."
kill_port 8080
kubectl port-forward svc/neural-test-service 8080:80 -n neural-hive-system > /dev/null 2>&1 &
test_pid=$!
sleep 3
if ps -p $test_pid > /dev/null 2>&1; then
    echo "✅ Neural Hive Test Service disponível em: http://localhost:8080"
    echo $test_pid >> /tmp/neural-hive-dashboards.pid
else
    echo "❌ Falha ao configurar Test Service"
fi

echo ""
echo "🌟 ============================================="
echo "🧠 Neural Hive-Mind Dashboards Configurados!"
echo "=============================================="
echo ""
echo "📊 DASHBOARDS DISPONÍVEIS:"
echo "=========================="
echo "🕸️  Kiali (Service Mesh):     http://localhost:20001"
echo "📈 Grafana (Métricas):        http://localhost:3000"
echo "🔍 Jaeger (Tracing):          http://localhost:16686"
echo "📊 Prometheus (Raw Metrics):  http://localhost:9090"
echo "🧪 Neural Test Service:       http://localhost:8080"
echo ""
echo "💡 DICAS DE USO:"
echo "================"
echo "• Kiali: Visualize o service mesh, tráfego entre serviços"
echo "• Grafana: Dashboards de métricas, performance, recursos"
echo "• Jaeger: Rastreamento distribuído, latência de requests"
echo "• Prometheus: Métricas raw, queries customizadas"
echo "• Test Service: Página de teste do Neural Hive-Mind"
echo ""
echo "🔧 COMANDOS ÚTEIS:"
echo "=================="
echo "• Para parar todos os dashboards: ./stop-dashboards.sh"
echo "• Para verificar status: ps aux | grep 'port-forward'"
echo "• Para logs: kubectl logs -f deployment/<service-name> -n istio-system"
echo ""
echo "⚠️  IMPORTANTE:"
echo "==============="
echo "• Mantenha este terminal aberto para manter os port-forwards"
echo "• Use Ctrl+C para parar todos os port-forwards"
echo "• Os PIDs dos processos estão salvos em /tmp/neural-hive-dashboards.pid"
echo ""
echo "🚀 Dashboards prontos para uso!"

# Função para cleanup quando script for interrompido
cleanup() {
    echo ""
    echo "🔄 Parando todos os port-forwards..."
    if [ -f /tmp/neural-hive-dashboards.pid ]; then
        while read pid; do
            if ps -p $pid > /dev/null 2>&1; then
                kill $pid 2>/dev/null
            fi
        done < /tmp/neural-hive-dashboards.pid
        rm -f /tmp/neural-hive-dashboards.pid
    fi
    echo "✅ Cleanup concluído!"
    exit 0
}

# Configurar trap para cleanup
trap cleanup SIGINT SIGTERM

# Manter o script rodando
echo "💤 Mantendo port-forwards ativos... (Pressione Ctrl+C para parar)"
wait
