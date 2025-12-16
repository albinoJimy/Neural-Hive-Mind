#!/bin/bash
set -eo pipefail
source "$(dirname "$0")/../lib/k8s.sh"

echo "🛑 Parando todos os dashboards do Neural Hive-Mind..."

# Função para matar processos por porta
kill_by_port() {
    local port=$1
    local name=$2
    local pids=$(lsof -ti:$port 2>/dev/null)
    if [ ! -z "$pids" ]; then
        echo "🔄 Parando $name (porta $port)..."
        echo $pids | xargs kill -9 2>/dev/null
        sleep 1
        echo "✅ $name parado"
    else
        echo "ℹ️  $name não estava rodando"
    fi
}

# Parar por PIDs salvos
if [ -f /tmp/neural-hive-dashboards.pid ]; then
    echo "🔄 Parando processos salvos..."
    while read pid; do
        if ps -p $pid > /dev/null 2>&1; then
            kill $pid 2>/dev/null
            echo "✅ Processo $pid parado"
        fi
    done < /tmp/neural-hive-dashboards.pid
    rm -f /tmp/neural-hive-dashboards.pid
fi

# Parar por portas específicas
echo ""
echo "🔄 Verificando portas específicas..."
kill_by_port "20001" "Kiali"
kill_by_port "3000" "Grafana"
kill_by_port "16686" "Jaeger"
kill_by_port "9090" "Prometheus"
kill_by_port "8080" "Neural Test Service"

# Parar todos os kubectl port-forward
echo ""
echo "🔄 Parando todos os kubectl port-forward..."
pkill -f "kubectl port-forward" 2>/dev/null && echo "✅ Todos os port-forwards parados" || echo "ℹ️  Nenhum port-forward ativo"

echo ""
echo "✅ Todos os dashboards foram parados!"
echo "🔧 Para reativar, execute: ./access-dashboards.sh"
