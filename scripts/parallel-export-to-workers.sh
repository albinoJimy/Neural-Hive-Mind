#!/bin/bash
# Exportação paralela de todas as imagens para os 2 workers
# Cada imagem é transferida em background

WORKER1="158.220.101.216"
WORKER2="84.247.138.35"
LOG_DIR="/jimy/Neural-Hive-Mind/logs/export-parallel"

mkdir -p "$LOG_DIR"

IMAGES=(
  "neural-hive-mind/gateway-intencoes:1.0.8"
  "neural-hive-mind/semantic-translation-engine:1.0.8"
  "neural-hive-mind/orchestrator-dynamic:1.0.8"
  "neural-hive-mind/consensus-engine:1.0.8"
  "neural-hive-mind/specialist-architecture:1.0.8"
  "neural-hive-mind/specialist-behavior:1.0.8"
  "neural-hive-mind/specialist-business:1.0.8"
  "neural-hive-mind/specialist-evolution:1.0.8"
  "neural-hive-mind/specialist-technical:1.0.8"
)

export_to_worker() {
  local img=$1
  local worker=$2
  local name=$(echo "$img" | cut -d'/' -f2 | cut -d':' -f1)
  local log="$LOG_DIR/${name}-${worker}.log"

  echo "[$(date +%H:%M:%S)] START $name → $worker" > "$log"

  if docker save "$img" | ssh -o StrictHostKeyChecking=no "root@${worker}" "ctr -n k8s.io images import -" >> "$log" 2>&1; then
    echo "[$(date +%H:%M:%S)] SUCCESS $name → $worker" >> "$log"
    echo "✅ $name → $worker"
  else
    echo "[$(date +%H:%M:%S)] FAILED $name → $worker" >> "$log"
    echo "❌ $name → $worker"
  fi
}

echo "=== EXPORTAÇÃO PARALELA DE ${#IMAGES[@]} IMAGENS PARA 2 WORKERS ==="
echo "Iniciando $(( ${#IMAGES[@]} * 2 )) transferências em background..."
echo "Logs em: $LOG_DIR"
echo ""

# Iniciar todas as transferências em background
for img in "${IMAGES[@]}"; do
  name=$(echo "$img" | cut -d'/' -f2 | cut -d':' -f1)
  echo "🚀 Iniciando: $name"

  export_to_worker "$img" "$WORKER1" &
  export_to_worker "$img" "$WORKER2" &
done

echo ""
echo "Todas as transferências iniciadas!"
echo "Aguardando conclusão..."
echo ""

# Aguardar todas as transferências
wait

echo ""
echo "=== RESUMO FINAL ==="
echo ""

# Contar sucesso/falha
SUCCESS=$(grep -l "SUCCESS" "$LOG_DIR"/*.log 2>/dev/null | wc -l)
FAILED=$(grep -l "FAILED" "$LOG_DIR"/*.log 2>/dev/null | wc -l)

echo "Sucesso: $SUCCESS/18"
echo "Falhas: $FAILED/18"

echo ""
echo "=== IMAGENS NOS WORKERS ==="
echo "Worker 1 ($WORKER1):"
ssh "root@$WORKER1" "ctr -n k8s.io images list | grep -E 'neural-hive-mind.*(gateway|semantic|orchestrator|consensus|specialist).*1.0.8' | wc -l" 2>/dev/null

echo "Worker 2 ($WORKER2):"
ssh "root@$WORKER2" "ctr -n k8s.io images list | grep -E 'neural-hive-mind.*(gateway|semantic|orchestrator|consensus|specialist).*1.0.8' | wc -l" 2>/dev/null

echo ""
echo "✅ Exportação concluída!"
