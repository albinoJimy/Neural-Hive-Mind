#!/bin/bash
# Script de acesso aos dashboards de monitoramento
# Uso: ./dashboards-access.sh [service]

set -e

SERVICE="${1:-list}"
PORT_GRAFANA=3000
PORT_PROMETHEUS=9090
PORT_JAEGER=16686

# Função para matar processo existente em porta
kill_port() {
  local port=$1
  local pid=$(lsof -ti:${port} 2>/dev/null)
  if [[ -n "${pid}" ]]; then
    kill -9 ${pid} 2>/dev/null || true
    echo "Porta ${port} liberada (PID ${pid} eliminado)."
  fi
}

case "${SERVICE}" in
  list|help)
    echo "=== Dashboards Disponíveis ==="
    echo ""
    echo "Uso: ./dashboards-access.sh <service>"
    echo ""
    echo "Serviços disponíveis:"
    echo "  grafana     - Dashboard Grafana (porta ${PORT_GRAFANA})"
    echo "  prometheus   - Dashboard Prometheus (porta ${PORT_PROMETHEUS})"
    echo "  jaeger       - Dashboard Jaeger Tracing (porta ${PORT_JAEGER})"
    echo "  all          - Todos os dashboards em background"
    echo "  stop         - Parar todos os port forwards"
    echo "  list         - Esta mensagem de ajuda"
    echo ""
    echo "Acessar em navegador:"
    echo "  Grafana: http://localhost:${PORT_GRAFANA}"
    echo "  Prometheus: http://localhost:${PORT_PROMETHEUS}"
    echo "  Jaeger: http://localhost:${PORT_JAEGER}"
    ;;

  grafana)
    echo "Iniciando Grafana..."
    kill_port ${PORT_GRAFANA}
    kubectl port-forward -n neural-hive-observability svc/grafana ${PORT_GRAFANA}:3000
    ;;

  prometheus|prom)
    echo "Iniciando Prometheus..."
    kill_port ${PORT_PROMETHEUS}
    kubectl port-forward -n neural-hive-observability svc/prometheus ${PORT_PROMETHEUS}:9090
    ;;

  jaeger)
    echo "Iniciando Jaeger..."
    kill_port ${PORT_JAEGER}
    kubectl port-forward -n neural-hive-observability svc/jaeger-query ${PORT_JAEGER}:16686
    ;;

  all)
    echo "Iniciando todos os dashboards em background..."
    kill_port ${PORT_GRAFANA}
    kill_port ${PORT_PROMETHEUS}
    kill_port ${PORT_JAEGER}

    kubectl port-forward -n neural-hive-observability svc/grafana ${PORT_GRAFANA}:3000 >/dev/null 2>&1 &
    echo "  Grafana: http://localhost:${PORT_GRAFANA} (background)"

    kubectl port-forward -n neural-hive-observability svc/prometheus ${PORT_PROMETHEUS}:9090 >/dev/null 2>&1 &
    echo "  Prometheus: http://localhost:${PORT_PROMETHEUS} (background)"

    kubectl port-forward -n neural-hive-observability svc/jaeger-query ${PORT_JAEGER}:16686 >/dev/null 2>&1 &
    echo "  Jaeger: http://localhost:${PORT_JAEGER} (background)"

    echo ""
    echo "Para parar: ./dashboards-access.sh stop"
    ;;

  stop)
    echo "Parando todos os port forwards..."
    kill_port ${PORT_GRAFANA}
    kill_port ${PORT_PROMETHEUS}
    kill_port ${PORT_JAEGER}
    echo "Todos parados."
    ;;

  *)
    echo "Serviço desconhecido: ${SERVICE}"
    echo "Use 'list' para ver serviços disponíveis."
    exit 1
    ;;
esac
