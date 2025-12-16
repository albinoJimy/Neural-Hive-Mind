#!/usr/bin/env bash
#
# Populate Vault with secrets for Neural Hive Mind services
#
# This script populates HashiCorp Vault with all secrets required for
# Phase 1 and Phase 2 services. Supports dry-run mode for testing.
#
# Usage:
#   ./scripts/vault-populate-secrets.sh
#   DRY_RUN=true ./scripts/vault-populate-secrets.sh
#
# Environment variables:
#   VAULT_ADDR - Vault server address
#   DRY_RUN    - Set to "true" to simulate without making changes
#

set -euo pipefail

DRY_RUN=${DRY_RUN:-false}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[vault-populate]${NC} $*"; }
log_success() { echo -e "${GREEN}[vault-populate]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[vault-populate]${NC} $*"; }
log_error() { echo -e "${RED}[vault-populate]${NC} $*"; }

run_vault() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    log "[DRY-RUN] vault $*"
  else
    vault "$@"
  fi
}

# Generate random password if not provided
generate_password() {
  openssl rand -hex 16
}

if ! command -v vault &> /dev/null; then
  log_error "Vault CLI não encontrado"
  exit 1
fi

if ! vault token lookup &> /dev/null; then
  log_error "Não autenticado no Vault. Execute: vault login"
  exit 1
fi

log "=============================================="
log "Neural Hive Mind - Vault Secrets Population"
log "=============================================="
log "Dry Run: ${DRY_RUN}"
log ""

# =============================================================================
# PHASE 1 SECRETS (Original)
# =============================================================================

log "Populando segredos do orchestrator (Phase 1)..."
ORCH_MONGODB_URI=${ORCHESTRATOR_MONGODB_URI:-"mongodb://mongo.neural-hive-orchestration:27017/neural_hive_orchestration"}
ORCH_KAFKA_USERNAME=${ORCHESTRATOR_KAFKA_USERNAME:-"orch-kafka"}
ORCH_KAFKA_PASSWORD=${ORCHESTRATOR_KAFKA_PASSWORD:-"changeme"}
ORCH_REDIS_PASSWORD=${ORCHESTRATOR_REDIS_PASSWORD:-"changeme"}

run_vault kv put secret/orchestrator/mongodb uri="${ORCH_MONGODB_URI}"
run_vault kv put secret/orchestrator/kafka username="${ORCH_KAFKA_USERNAME}" password="${ORCH_KAFKA_PASSWORD}"
run_vault kv put secret/orchestrator/redis password="${ORCH_REDIS_PASSWORD}"

log "Populando segredos dos workers (Phase 1)..."
WORKER_KAFKA_USERNAME=${WORKER_KAFKA_USERNAME:-"worker-kafka"}
WORKER_KAFKA_PASSWORD=${WORKER_KAFKA_PASSWORD:-"changeme"}
WORKER_EXECUTION_BUILD=${WORKER_EXECUTION_BUILD_CREDENTIALS:-"{}"}

run_vault kv put secret/worker/kafka username="${WORKER_KAFKA_USERNAME}" password="${WORKER_KAFKA_PASSWORD}"
run_vault kv put secret/worker/execution/build credentials="${WORKER_EXECUTION_BUILD}"

# =============================================================================
# PHASE 2 SECRETS
# =============================================================================

log ""
log "=============================================="
log "Populando segredos da Phase 2..."
log "=============================================="

# -----------------------------------------------------------------------------
# Orchestrator Dynamic (Extended)
# -----------------------------------------------------------------------------
log ""
log "--- orchestrator-dynamic ---"
ORCH_POSTGRES_USER=${ORCH_POSTGRES_USER:-"orchestrator"}
ORCH_POSTGRES_PASSWORD=${ORCH_POSTGRES_PASSWORD:-$(generate_password)}

run_vault kv put secret/orchestrator-dynamic/postgres \
  user="${ORCH_POSTGRES_USER}" \
  password="${ORCH_POSTGRES_PASSWORD}"

run_vault kv put secret/orchestrator-dynamic/mongodb \
  uri="${ORCH_MONGODB_URI}"

run_vault kv put secret/orchestrator-dynamic/redis \
  password="${ORCH_REDIS_PASSWORD}"

run_vault kv put secret/orchestrator-dynamic/kafka \
  username="${ORCH_KAFKA_USERNAME}" \
  password="${ORCH_KAFKA_PASSWORD}"

# -----------------------------------------------------------------------------
# Execution Ticket Service
# -----------------------------------------------------------------------------
log ""
log "--- execution-ticket-service ---"
ETS_POSTGRES_PASSWORD=${ETS_POSTGRES_PASSWORD:-$(generate_password)}
ETS_JWT_SECRET=${ETS_JWT_SECRET:-$(generate_password)}
ETS_MONGODB_URI=${ETS_MONGODB_URI:-"mongodb://mongo.neural-hive-orchestration:27017/execution_tickets"}

run_vault kv put secret/execution-ticket-service/postgres \
  password="${ETS_POSTGRES_PASSWORD}"

run_vault kv put secret/execution-ticket-service/mongodb \
  uri="${ETS_MONGODB_URI}"

run_vault kv put secret/execution-ticket-service/jwt \
  secret_key="${ETS_JWT_SECRET}"

# -----------------------------------------------------------------------------
# Queen Agent
# -----------------------------------------------------------------------------
log ""
log "--- queen-agent ---"
QUEEN_MONGODB_URI=${QUEEN_MONGODB_URI:-"mongodb://mongo.neural-hive-queen:27017/queen_agent"}
QUEEN_REDIS_PASSWORD=${QUEEN_REDIS_PASSWORD:-$(generate_password)}
QUEEN_REDIS_NODES=${QUEEN_REDIS_NODES:-"redis-cluster-0.redis-cluster-headless.neural-hive-infrastructure:6379,redis-cluster-1.redis-cluster-headless.neural-hive-infrastructure:6379,redis-cluster-2.redis-cluster-headless.neural-hive-infrastructure:6379"}
QUEEN_NEO4J_URI=${QUEEN_NEO4J_URI:-"bolt://neo4j.neural-hive-infrastructure:7687"}
QUEEN_NEO4J_USER=${QUEEN_NEO4J_USER:-"neo4j"}
QUEEN_NEO4J_PASSWORD=${QUEEN_NEO4J_PASSWORD:-$(generate_password)}

run_vault kv put secret/queen-agent/mongodb \
  uri="${QUEEN_MONGODB_URI}"

run_vault kv put secret/queen-agent/redis \
  password="${QUEEN_REDIS_PASSWORD}" \
  cluster_nodes="${QUEEN_REDIS_NODES}"

run_vault kv put secret/queen-agent/neo4j \
  uri="${QUEEN_NEO4J_URI}" \
  user="${QUEEN_NEO4J_USER}" \
  password="${QUEEN_NEO4J_PASSWORD}"

# -----------------------------------------------------------------------------
# Worker Agents (Extended)
# -----------------------------------------------------------------------------
log ""
log "--- worker-agents ---"
WORKER_ARGOCD_TOKEN=${WORKER_ARGOCD_TOKEN:-$(generate_password)}
WORKER_JENKINS_TOKEN=${WORKER_JENKINS_TOKEN:-$(generate_password)}
WORKER_SONARQUBE_TOKEN=${WORKER_SONARQUBE_TOKEN:-$(generate_password)}
WORKER_SNYK_TOKEN=${WORKER_SNYK_TOKEN:-$(generate_password)}

run_vault kv put secret/worker-agents/kafka \
  username="${WORKER_KAFKA_USERNAME}" \
  password="${WORKER_KAFKA_PASSWORD}"

run_vault kv put secret/worker-agents/argocd \
  token="${WORKER_ARGOCD_TOKEN}"

run_vault kv put secret/worker-agents/jenkins \
  token="${WORKER_JENKINS_TOKEN}"

run_vault kv put secret/worker-agents/sonarqube \
  token="${WORKER_SONARQUBE_TOKEN}"

run_vault kv put secret/worker-agents/snyk \
  token="${WORKER_SNYK_TOKEN}"

# -----------------------------------------------------------------------------
# Code Forge
# -----------------------------------------------------------------------------
log ""
log "--- code-forge ---"
CF_POSTGRES_USER=${CF_POSTGRES_USER:-"code_forge"}
CF_POSTGRES_PASSWORD=${CF_POSTGRES_PASSWORD:-$(generate_password)}
CF_MONGODB_URI=${CF_MONGODB_URI:-"mongodb://mongo.neural-hive-execution:27017/code_forge"}
CF_REDIS_PASSWORD=${CF_REDIS_PASSWORD:-$(generate_password)}
CF_GIT_USERNAME=${CF_GIT_USERNAME:-"code-forge-bot"}
CF_GIT_TOKEN=${CF_GIT_TOKEN:-$(generate_password)}
CF_OPENAI_API_KEY=${CF_OPENAI_API_KEY:-"sk-placeholder"}
CF_ANTHROPIC_API_KEY=${CF_ANTHROPIC_API_KEY:-"sk-ant-placeholder"}

run_vault kv put secret/code-forge/postgres \
  user="${CF_POSTGRES_USER}" \
  password="${CF_POSTGRES_PASSWORD}"

run_vault kv put secret/code-forge/mongodb \
  uri="${CF_MONGODB_URI}"

run_vault kv put secret/code-forge/redis \
  password="${CF_REDIS_PASSWORD}"

run_vault kv put secret/code-forge/kafka \
  username="${ORCH_KAFKA_USERNAME}" \
  password="${ORCH_KAFKA_PASSWORD}"

run_vault kv put secret/code-forge/git \
  username="${CF_GIT_USERNAME}" \
  token="${CF_GIT_TOKEN}"

run_vault kv put secret/code-forge/llm \
  openai_api_key="${CF_OPENAI_API_KEY}" \
  anthropic_api_key="${CF_ANTHROPIC_API_KEY}"

# -----------------------------------------------------------------------------
# Service Registry
# -----------------------------------------------------------------------------
log ""
log "--- service-registry ---"
SR_REDIS_PASSWORD=${SR_REDIS_PASSWORD:-$(generate_password)}
SR_ETCD_USERNAME=${SR_ETCD_USERNAME:-"service-registry"}
SR_ETCD_PASSWORD=${SR_ETCD_PASSWORD:-$(generate_password)}

run_vault kv put secret/service-registry/redis \
  password="${SR_REDIS_PASSWORD}"

run_vault kv put secret/service-registry/etcd \
  username="${SR_ETCD_USERNAME}" \
  password="${SR_ETCD_PASSWORD}"

# -----------------------------------------------------------------------------
# Scout Agents
# -----------------------------------------------------------------------------
log ""
log "--- scout-agents ---"
SCOUT_KAFKA_USERNAME=${SCOUT_KAFKA_USERNAME:-"scout-kafka"}
SCOUT_KAFKA_PASSWORD=${SCOUT_KAFKA_PASSWORD:-$(generate_password)}
SCOUT_REDIS_PASSWORD=${SCOUT_REDIS_PASSWORD:-$(generate_password)}

run_vault kv put secret/scout-agents/kafka \
  username="${SCOUT_KAFKA_USERNAME}" \
  password="${SCOUT_KAFKA_PASSWORD}"

run_vault kv put secret/scout-agents/redis \
  password="${SCOUT_REDIS_PASSWORD}"

# -----------------------------------------------------------------------------
# Analyst Agents
# -----------------------------------------------------------------------------
log ""
log "--- analyst-agents ---"
ANALYST_MONGODB_URI=${ANALYST_MONGODB_URI:-"mongodb://mongo.neural-hive-estrategica:27017/analyst_agents"}
ANALYST_REDIS_PASSWORD=${ANALYST_REDIS_PASSWORD:-$(generate_password)}
ANALYST_NEO4J_PASSWORD=${ANALYST_NEO4J_PASSWORD:-$(generate_password)}
ANALYST_CLICKHOUSE_PASSWORD=${ANALYST_CLICKHOUSE_PASSWORD:-$(generate_password)}
ANALYST_ELASTICSEARCH_PASSWORD=${ANALYST_ELASTICSEARCH_PASSWORD:-$(generate_password)}

run_vault kv put secret/analyst-agents/mongodb \
  uri="${ANALYST_MONGODB_URI}"

run_vault kv put secret/analyst-agents/redis \
  password="${ANALYST_REDIS_PASSWORD}"

run_vault kv put secret/analyst-agents/neo4j \
  password="${ANALYST_NEO4J_PASSWORD}"

run_vault kv put secret/analyst-agents/clickhouse \
  password="${ANALYST_CLICKHOUSE_PASSWORD}"

run_vault kv put secret/analyst-agents/elasticsearch \
  password="${ANALYST_ELASTICSEARCH_PASSWORD}"

# -----------------------------------------------------------------------------
# Optimizer Agents
# -----------------------------------------------------------------------------
log ""
log "--- optimizer-agents ---"
OPTIMIZER_MONGODB_URI=${OPTIMIZER_MONGODB_URI:-"mongodb://mongo.neural-hive-estrategica:27017/optimizer_agents"}
OPTIMIZER_REDIS_PASSWORD=${OPTIMIZER_REDIS_PASSWORD:-$(generate_password)}
OPTIMIZER_MLFLOW_TOKEN=${OPTIMIZER_MLFLOW_TOKEN:-$(generate_password)}

run_vault kv put secret/optimizer-agents/mongodb \
  uri="${OPTIMIZER_MONGODB_URI}"

run_vault kv put secret/optimizer-agents/redis \
  password="${OPTIMIZER_REDIS_PASSWORD}"

run_vault kv put secret/optimizer-agents/mlflow \
  tracking_token="${OPTIMIZER_MLFLOW_TOKEN}"

# -----------------------------------------------------------------------------
# Guard Agents
# -----------------------------------------------------------------------------
log ""
log "--- guard-agents ---"
GUARD_MONGODB_PASSWORD=${GUARD_MONGODB_PASSWORD:-$(generate_password)}
GUARD_REDIS_PASSWORD=${GUARD_REDIS_PASSWORD:-$(generate_password)}
GUARD_KAFKA_USERNAME=${GUARD_KAFKA_USERNAME:-"guard-kafka"}
GUARD_KAFKA_PASSWORD=${GUARD_KAFKA_PASSWORD:-$(generate_password)}

run_vault kv put secret/guard-agents/mongodb \
  password="${GUARD_MONGODB_PASSWORD}"

run_vault kv put secret/guard-agents/redis \
  password="${GUARD_REDIS_PASSWORD}"

run_vault kv put secret/guard-agents/kafka \
  username="${GUARD_KAFKA_USERNAME}" \
  password="${GUARD_KAFKA_PASSWORD}"

# -----------------------------------------------------------------------------
# Self-Healing Engine
# -----------------------------------------------------------------------------
log ""
log "--- self-healing-engine ---"
SHE_MONGODB_PASSWORD=${SHE_MONGODB_PASSWORD:-$(generate_password)}
SHE_REDIS_PASSWORD=${SHE_REDIS_PASSWORD:-$(generate_password)}
SHE_KAFKA_PASSWORD=${SHE_KAFKA_PASSWORD:-$(generate_password)}
SHE_PAGERDUTY_API_KEY=${SHE_PAGERDUTY_API_KEY:-"placeholder-pagerduty-key"}
SHE_SLACK_WEBHOOK_URL=${SHE_SLACK_WEBHOOK_URL:-"https://hooks.slack.com/services/placeholder"}

run_vault kv put secret/self-healing-engine/mongodb \
  password="${SHE_MONGODB_PASSWORD}"

run_vault kv put secret/self-healing-engine/redis \
  password="${SHE_REDIS_PASSWORD}"

run_vault kv put secret/self-healing-engine/kafka \
  password="${SHE_KAFKA_PASSWORD}"

run_vault kv put secret/self-healing-engine/alerts \
  pagerduty_api_key="${SHE_PAGERDUTY_API_KEY}" \
  slack_webhook_url="${SHE_SLACK_WEBHOOK_URL}"

# -----------------------------------------------------------------------------
# SLA Management System
# -----------------------------------------------------------------------------
log ""
log "--- sla-management-system ---"
SLA_POSTGRES_USER=${SLA_POSTGRES_USER:-"sla_management"}
SLA_POSTGRES_PASSWORD=${SLA_POSTGRES_PASSWORD:-$(generate_password)}
SLA_REDIS_PASSWORD=${SLA_REDIS_PASSWORD:-$(generate_password)}
SLA_PROMETHEUS_TOKEN=${SLA_PROMETHEUS_TOKEN:-$(generate_password)}

run_vault kv put secret/sla-management-system/postgres \
  user="${SLA_POSTGRES_USER}" \
  password="${SLA_POSTGRES_PASSWORD}"

run_vault kv put secret/sla-management-system/redis \
  password="${SLA_REDIS_PASSWORD}"

run_vault kv put secret/sla-management-system/prometheus \
  bearer_token="${SLA_PROMETHEUS_TOKEN}"

# -----------------------------------------------------------------------------
# MCP Tool Catalog
# -----------------------------------------------------------------------------
log ""
log "--- mcp-tool-catalog ---"
MCP_MONGODB_URI=${MCP_MONGODB_URI:-"mongodb://mongo.neural-hive-mcp:27017/mcp_tool_catalog"}
MCP_REDIS_PASSWORD=${MCP_REDIS_PASSWORD:-$(generate_password)}
MCP_KAFKA_USERNAME=${MCP_KAFKA_USERNAME:-"mcp-kafka"}
MCP_KAFKA_PASSWORD=${MCP_KAFKA_PASSWORD:-$(generate_password)}
MCP_GITHUB_TOKEN=${MCP_GITHUB_TOKEN:-"ghp_placeholder"}
MCP_GITLAB_TOKEN=${MCP_GITLAB_TOKEN:-"glpat_placeholder"}

run_vault kv put secret/mcp-tool-catalog/mongodb \
  uri="${MCP_MONGODB_URI}"

run_vault kv put secret/mcp-tool-catalog/redis \
  password="${MCP_REDIS_PASSWORD}"

run_vault kv put secret/mcp-tool-catalog/kafka \
  username="${MCP_KAFKA_USERNAME}" \
  password="${MCP_KAFKA_PASSWORD}"

run_vault kv put secret/mcp-tool-catalog/integrations \
  github_token="${MCP_GITHUB_TOKEN}" \
  gitlab_token="${MCP_GITLAB_TOKEN}"

# =============================================================================
# SUMMARY
# =============================================================================

log ""
log "=============================================="
log_success "Vault secrets populated successfully!"
log "=============================================="
log ""
log "Secrets created for the following services:"
log "  Phase 1:"
log "    - orchestrator"
log "    - worker"
log ""
log "  Phase 2:"
log "    - orchestrator-dynamic"
log "    - execution-ticket-service"
log "    - queen-agent"
log "    - worker-agents"
log "    - code-forge"
log "    - service-registry"
log "    - scout-agents"
log "    - analyst-agents"
log "    - optimizer-agents"
log "    - guard-agents"
log "    - self-healing-engine"
log "    - sla-management-system"
log "    - mcp-tool-catalog"
log ""
log "Use DRY_RUN=true to simulate without making changes."
log ""
log "To list all secrets:"
log "  vault kv list secret/"
log ""
log "To read a specific secret:"
log "  vault kv get secret/<service>/<component>"
