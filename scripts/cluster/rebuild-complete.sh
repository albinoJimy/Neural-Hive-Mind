#!/bin/bash
# Script principal de destruição e reconstrução completa do cluster
# Uso: ./rebuild-complete.sh <ambiente> [--skip-backup] [--skip-terraform]

set -e

ENV="${1:-local}"
SKIP_BACKUP=false
SKIP_TERRAFORM=false
BACKUP_DIR=""

# Parse argumentos
shift
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-backup)
      SKIP_BACKUP=true
      shift
      ;;
    --skip-terraform)
      SKIP_TERRAFORM=true
      shift
      ;;
    --use-backup)
      BACKUP_DIR="${2}"
      shift 2
      ;;
    *)
      echo "Argumento desconhecido: $1"
      exit 1
      ;;
  esac
done

echo "╔════════════════════════════════════════════════════════════╗"
echo "║  Neural Hive-Mind - Reconstrução Completa do Cluster      ║"
echo "║  Ambiente: ${ENV}                                      ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Registrar tempo de início
START_TIME=$(date +%s)

# Fase 1: Preparação e Backup
if [[ "${SKIP_BACKUP}" == false ]]; then
  echo "═════════════════════════════════════════════════════════════"
  echo " FASE 1: PREPARAÇÃO E BACKUP"
  echo "═════════════════════════════════════════════════════════════"
  chmod +x scripts/cluster/backup-all-data.sh
  scripts/cluster/backup-all-data.sh "${ENV}"
  BACKUP_DIR=$(ls -td backup/cluster-backup-* 2>/dev/null | head -1)
  echo "Backup concluído: ${BACKUP_DIR}"
  echo ""
elif [[ -n "${BACKUP_DIR}" && -d "${BACKUP_DIR}" ]]; then
  echo "Usando backup existente: ${BACKUP_DIR}"
else
  echo "AVISO: Backup pulado, restore não será disponível."
fi

# Fase 2: Destruição Ordenada
echo "═════════════════════════════════════════════════════════════"
echo " FASE 2: DESTRUIÇÃO ORDENADA"
echo "═════════════════════════════════════════════════════════════"
read -p "Confirmar início da destruição? (s/N): " confirm
if [[ "${confirm}" =~ ^[Ss]$ ]]; then
  chmod +x scripts/cluster/destroy-cluster-ordered.sh
  TERRAFORM_ARG=""
  [[ "${SKIP_TERRAFORM}" == true ]] && TERRAFORM_ARG="--skip-terraform"
  scripts/cluster/destroy-cluster-ordered.sh "${ENV}" ${TERRAFORM_ARG}
  echo "Destruição concluída."
else
  echo "Operação cancelada."
  exit 0
fi
echo ""

# Aguardar confirmação antes de reconstruir
echo ""
read -p "Iniciar reconstrução? (s/N): " confirm
if [[ ! "${confirm}" =~ ^[Ss]$ ]]; then
  echo "Operação pausada após destruição. Para continuar:"
  echo "  scripts/cluster/rebuild-cluster.sh ${ENV} ${BACKUP_DIR}"
  exit 0
fi

# Fase 3: Reconstrução do Cluster
echo "═════════════════════════════════════════════════════════════"
echo " FASE 3: RECONSTRUÇÃO DO CLUSTER"
echo "═════════════════════════════════════════════════════════════"
chmod +x scripts/cluster/rebuild-cluster.sh
scripts/cluster/rebuild-cluster.sh "${ENV}" "${BACKUP_DIR}"
echo ""

# Fase 4: Deploy de Serviços
echo "═════════════════════════════════════════════════════════════"
echo " FASE 4: DEPLOY DE SERVIÇOS"
echo "═════════════════════════════════════════════════════════════"
chmod +x scripts/cluster/deploy-services-ordered.sh
scripts/cluster/deploy-services-ordered.sh "${ENV}"
echo ""

# Fase 5: Validação Completa
echo "═════════════════════════════════════════════════════════════"
echo " FASE 5: VALIDAÇÃO COMPLETA"
echo "═════════════════════════════════════════════════════════════"
chmod +x scripts/cluster/validate-complete-cluster.sh
scripts/cluster/validate-complete-cluster.sh
echo ""

# Relatório Final
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
HOURS=$((DURATION / 3600))
MINUTES=$(((DURATION % 3600) / 60))
SECONDS=$((DURATION % 60))

echo "╔════════════════════════════════════════════════════════════╗"
echo "║  RECONSTRUÇÃO COMPLETA CONCLUÍDA                       ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "  Tempo Total: ${HOURS}h ${MINUTES}m ${SECONDS}s"
echo "  Backup: ${BACKUP_DIR:-N/A}"
echo "  Ambiente: ${ENV}"
echo ""
echo "Próximos passos:"
echo "  1. Acessar dashboards: scripts/observability.sh dashboards access"
echo "  2. Monitorar logs: scripts/cluster/monitor-cluster-health.sh"
echo "  3. Executar testes E2E completos: tests/run-tests.sh --type e2e"
echo ""
