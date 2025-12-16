#!/usr/bin/env bash
# Script auxiliar para preparar dados de teste E2E
# NÃO executa testes, apenas gera payloads e configurações

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configurações padrão
OUTPUT_DIR=".tmp"
VERBOSE=false
SETUP_PORT_FORWARDS=false

# Função de ajuda
show_help() {
    cat << EOF
Uso: $(basename "$0") [OPÇÕES]

Prepara dados e configurações para teste E2E manual do Neural Hive-Mind.

OPÇÕES:
    -h, --help                  Mostra esta mensagem de ajuda
    -v, --verbose               Modo verbose
    -o, --output-dir DIR        Diretório de saída (padrão: .tmp)
    -p, --setup-port-forwards   Configura port-forwards para Prometheus e Jaeger

EXEMPLOS:
    $(basename "$0")                           # Gera payloads e configs no diretório .tmp
    $(basename "$0") -v -o /tmp/e2e-test      # Modo verbose, output em /tmp/e2e-test
    $(basename "$0") -p                        # Gera configs e configura port-forwards

EOF
}

# Parse de argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -o|--output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -p|--setup-port-forwards)
            SETUP_PORT_FORWARDS=true
            shift
            ;;
        *)
            echo -e "${RED}Erro: Opção desconhecida: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# Função de log
log() {
    local level=$1
    shift
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    case $level in
        INFO)
            echo -e "${BLUE}[$timestamp] INFO:${NC} $*"
            ;;
        SUCCESS)
            echo -e "${GREEN}[$timestamp] SUCCESS:${NC} $*"
            ;;
        WARN)
            echo -e "${YELLOW}[$timestamp] WARN:${NC} $*"
            ;;
        ERROR)
            echo -e "${RED}[$timestamp] ERROR:${NC} $*"
            ;;
    esac
}

# Validar pré-requisitos
validate_prerequisites() {
    log INFO "Validando pré-requisitos..."
    
    local missing_tools=()
    
    for tool in kubectl curl jq mongosh redis-cli; do
        if ! command -v $tool &> /dev/null; then
            missing_tools+=($tool)
        fi
    done
    
    if [ ${#missing_tools[@]} -gt 0 ]; then
        log ERROR "Ferramentas faltando: ${missing_tools[*]}"
        log ERROR "Instale as ferramentas necessárias antes de continuar"
        exit 1
    fi
    
    log SUCCESS "Todos os pré-requisitos instalados"
}

# Detectar pods dos serviços
detect_service_pods() {
    log INFO "Detectando pods dos serviços..."
    
    # Gateway
    GATEWAY_POD=$(kubectl get pod -n gateway-intencoes -l app=gateway-intencoes -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    [ -z "$GATEWAY_POD" ] && log WARN "Gateway pod não encontrado" || log INFO "Gateway: $GATEWAY_POD"
    
    # Kafka
    KAFKA_POD=$(kubectl get pod -n kafka -l app=kafka -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    [ -z "$KAFKA_POD" ] && log WARN "Kafka pod não encontrado" || log INFO "Kafka: $KAFKA_POD"
    
    # MongoDB
    MONGODB_POD=$(kubectl get pod -n mongodb -l app=mongodb -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    [ -z "$MONGODB_POD" ] && log WARN "MongoDB pod não encontrado" || log INFO "MongoDB: $MONGODB_POD"
    
    # Redis
    REDIS_POD=$(kubectl get pod -n redis -l app=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    [ -z "$REDIS_POD" ] && log WARN "Redis pod não encontrado" || log INFO "Redis: $REDIS_POD"
    
    # STE
    STE_POD=$(kubectl get pod -n semantic-translation -l app=semantic-translation-engine -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    [ -z "$STE_POD" ] && log WARN "STE pod não encontrado" || log INFO "STE: $STE_POD"
    
    # Consensus Engine
    CONSENSUS_POD=$(kubectl get pod -n consensus-engine -l app=consensus-engine -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    [ -z "$CONSENSUS_POD" ] && log WARN "Consensus Engine pod não encontrado" || log INFO "Consensus: $CONSENSUS_POD"
    
    # Orchestrator
    ORCHESTRATOR_POD=$(kubectl get pod -n orchestrator-dynamic -l app=orchestrator-dynamic -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    [ -z "$ORCHESTRATOR_POD" ] && log WARN "Orchestrator pod não encontrado" || log INFO "Orchestrator: $ORCHESTRATOR_POD"
}

# Validar status dos pods
validate_pods_status() {
    log INFO "Validando status dos pods..."
    
    local all_running=true
    
    for ns in gateway-intencoes semantic-translation consensus-engine orchestrator-dynamic kafka mongodb redis observability; do
        local not_running=$(kubectl get pods -n $ns 2>/dev/null | grep -v "Running" | grep -v "NAME" | wc -l)
        if [ "$not_running" -gt 0 ]; then
            log WARN "Namespace $ns tem $not_running pod(s) não-Running"
            all_running=false
        fi
    done
    
    if [ "$all_running" = false ]; then
        log WARN "Alguns pods não estão Running. Verifique com: kubectl get pods --all-namespaces"
    else
        log SUCCESS "Todos os pods estão Running"
    fi
}

# Criar diretório de saída
create_output_dir() {
    log INFO "Criando diretório de saída: $OUTPUT_DIR"
    mkdir -p "$OUTPUT_DIR"
    log SUCCESS "Diretório criado: $OUTPUT_DIR"
}

# Gerar payloads de teste
generate_test_payloads() {
    log INFO "Gerando payloads de teste..."
    
    local timestamp=$(date +%s)
    
    # Payload 1: Intenção Técnica
    cat > "$OUTPUT_DIR/intent-technical-001.json" <<EOF
{
  "text": "Analisar viabilidade técnica de implementar autenticação biométrica no aplicativo móvel",
  "language": "pt-BR",
  "correlation_id": "test-e2e-technical-001",
  "context": {
    "user_id": "test-user-e2e",
    "session_id": "test-session-${timestamp}",
    "channel": "API"
  },
  "constraints": {
    "priority": "HIGH",
    "timeout_ms": 30000
  }
}
EOF
    
    # Payload 2: Intenção de Negócio
    cat > "$OUTPUT_DIR/intent-business-001.json" <<EOF
{
  "text": "Criar estratégia de expansão para mercado internacional com foco em redução de custos operacionais",
  "language": "pt-BR",
  "correlation_id": "test-e2e-business-001",
  "context": {
    "user_id": "test-user-e2e",
    "session_id": "test-session-${timestamp}",
    "channel": "API"
  },
  "constraints": {
    "priority": "MEDIUM",
    "timeout_ms": 30000
  }
}
EOF
    
    # Payload 3: Intenção de Infraestrutura
    cat > "$OUTPUT_DIR/intent-infrastructure-001.json" <<EOF
{
  "text": "Migrar banco de dados PostgreSQL para cluster Kubernetes com alta disponibilidade e backup automático",
  "language": "pt-BR",
  "correlation_id": "test-e2e-infrastructure-001",
  "context": {
    "user_id": "test-user-e2e",
    "session_id": "test-session-${timestamp}",
    "channel": "API"
  },
  "constraints": {
    "priority": "HIGH",
    "timeout_ms": 30000
  }
}
EOF
    
    # Payload 4: Intenção de Segurança
    cat > "$OUTPUT_DIR/intent-security-001.json" <<EOF
{
  "text": "Implementar política de zero-trust com autenticação multifator e criptografia end-to-end",
  "language": "pt-BR",
  "correlation_id": "test-e2e-security-001",
  "context": {
    "user_id": "test-user-e2e",
    "session_id": "test-session-${timestamp}",
    "channel": "API"
  },
  "constraints": {
    "priority": "CRITICAL",
    "timeout_ms": 30000
  }
}
EOF
    
    # Payload 5: Intenção de Arquitetura
    cat > "$OUTPUT_DIR/intent-architecture-001.json" <<EOF
{
  "text": "Refatorar arquitetura monolítica para microserviços com comunicação assíncrona via event-driven",
  "language": "pt-BR",
  "correlation_id": "test-e2e-architecture-001",
  "context": {
    "user_id": "test-user-e2e",
    "session_id": "test-session-${timestamp}",
    "channel": "API"
  },
  "constraints": {
    "priority": "MEDIUM",
    "timeout_ms": 30000
  }
}
EOF
    
    log SUCCESS "5 payloads de teste gerados em $OUTPUT_DIR"
}

# Gerar arquivo de configuração
generate_config_file() {
    log INFO "Gerando arquivo de configuração..."
    
    cat > "$OUTPUT_DIR/e2e-test-config.env" <<EOF
# Configuração de Teste E2E - Neural Hive-Mind
# Gerado em: $(date)

# Pods dos Serviços
export GATEWAY_POD="$GATEWAY_POD"
export KAFKA_POD="$KAFKA_POD"
export MONGODB_POD="$MONGODB_POD"
export REDIS_POD="$REDIS_POD"
export STE_POD="$STE_POD"
export CONSENSUS_POD="$CONSENSUS_POD"
export ORCHESTRATOR_POD="$ORCHESTRATOR_POD"

# URLs de Observabilidade (após port-forward)
export PROMETHEUS_URL="http://localhost:9090"
export JAEGER_URL="http://localhost:16686"

# Namespaces
export NS_GATEWAY="gateway-intencoes"
export NS_STE="semantic-translation"
export NS_CONSENSUS="consensus-engine"
export NS_ORCHESTRATOR="orchestrator-dynamic"
export NS_KAFKA="kafka"
export NS_MONGODB="mongodb"
export NS_REDIS="redis"
export NS_OBSERVABILITY="observability"
EOF
    
    log SUCCESS "Arquivo de configuração gerado: $OUTPUT_DIR/e2e-test-config.env"
    log INFO "Para usar: source $OUTPUT_DIR/e2e-test-config.env"
}

# Gerar comandos prontos
generate_commands_script() {
    log INFO "Gerando script de comandos prontos..."
    
    cat > "$OUTPUT_DIR/e2e-test-commands.sh" <<'EOF'
#!/usr/bin/env bash
# Comandos prontos para teste E2E manual
# Copie e cole os comandos conforme necessário

# Carregar configurações
source "$(dirname "$0")/e2e-test-config.env"

echo "=== FASE 1: FLUXO A (Gateway → Kafka) ==="

# 1.1. Health Check do Gateway
echo "# Health Check do Gateway"
kubectl exec -n $NS_GATEWAY $GATEWAY_POD -- \
  curl -s http://localhost:8000/health | jq

# 1.2. Enviar Intenção Técnica
echo "# Enviar Intenção Técnica"
kubectl cp "$(dirname "$0")/intent-technical-001.json" $NS_GATEWAY/$GATEWAY_POD:/tmp/
kubectl exec -n $NS_GATEWAY $GATEWAY_POD -- \
  curl -X POST http://localhost:8000/intentions \
  -H 'Content-Type: application/json' \
  -d @/tmp/intent-technical-001.json | jq

# 1.3. Verificar Logs do Gateway
echo "# Logs do Gateway"
kubectl logs -n $NS_GATEWAY $GATEWAY_POD --tail=50 | grep -E "intent_id|Kafka|published"

# 1.4. Verificar Publicação no Kafka
echo "# Consumir do Kafka (intentions.technical)"
kubectl exec -n $NS_KAFKA $KAFKA_POD -- \
  kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic intentions.technical \
  --from-beginning \
  --max-messages 1 \
  --timeout-ms 5000

# 1.5. Métricas no Prometheus
echo "# Métricas do Gateway"
curl -s "${PROMETHEUS_URL}/api/v1/query?query=neural_hive_intents_published_total{service=\"gateway-intencoes\"}" | jq

# 1.6. Cache no Redis
echo "# Verificar cache no Redis (substitua INTENT_ID)"
# kubectl exec -n $NS_REDIS $REDIS_POD -- redis-cli GET "intent:INTENT_ID"

echo ""
echo "=== FASE 2: FLUXO B (STE → Plano) ==="

# 2.1. Logs do STE
echo "# Logs do STE"
kubectl logs -n $NS_STE $STE_POD --tail=100 | grep -E "Consumindo|Intent|plan_id"

# 2.2. Persistência no MongoDB
echo "# Verificar plano no MongoDB (substitua PLAN_ID)"
# kubectl exec -n $NS_MONGODB $MONGODB_POD -- mongosh --eval \
#   "db.cognitive_ledger.findOne({plan_id: 'PLAN_ID'})" neural_hive

echo ""
echo "=== FASE 3: FLUXO B (Specialists) ==="

# 3.1. Logs dos Specialists
for specialist in business technical behavior evolution architecture; do
    echo "# Logs do Specialist: $specialist"
    SPECIALIST_POD=$(kubectl get pod -n $NS_STE -l app=specialist-$specialist -o jsonpath='{.items[0].metadata.name}')
    kubectl logs -n $NS_STE $SPECIALIST_POD --tail=50 | grep -E "GetOpinion|opinion_id"
done

echo ""
echo "=== FASE 4: FLUXO C (Consensus) ==="

# 4.1. Logs do Consensus Engine
echo "# Logs do Consensus Engine"
kubectl logs -n $NS_CONSENSUS $CONSENSUS_POD --tail=100 | grep -E "Consumindo|decision_id|Agregando"

# 4.2. Feromônios no Redis
echo "# Listar feromônios"
kubectl exec -n $NS_REDIS $REDIS_POD -- redis-cli KEYS 'pheromone:*'

echo ""
echo "=== FASE 5: FLUXO C (Orchestrator) ==="

# 5.1. Logs do Orchestrator
echo "# Logs do Orchestrator"
kubectl logs -n $NS_ORCHESTRATOR $ORCHESTRATOR_POD --tail=100 | grep -E "Consumindo|ticket_id|Gerando"

# 5.2. Tickets no MongoDB
echo "# Verificar tickets no MongoDB (substitua PLAN_ID)"
# kubectl exec -n $NS_MONGODB $MONGODB_POD -- mongosh --eval \
#   "db.execution_tickets.find({plan_id: 'PLAN_ID'}).count()" neural_hive

echo ""
echo "=== VALIDAÇÃO CONSOLIDADA ==="

# Correlação no MongoDB
echo "# Correlação completa (substitua INTENT_ID)"
# kubectl exec -n $NS_MONGODB $MONGODB_POD -- mongosh --eval "
# db.cognitive_ledger.aggregate([
#   {\$match: {intent_id: 'INTENT_ID'}},
#   {\$group: {_id: '\$type', count: {\$sum: 1}}}
# ])
# " neural_hive

# Métricas agregadas
echo "# Métricas agregadas"
curl -s "${PROMETHEUS_URL}/api/v1/query?query=sum(rate(neural_hive_intents_published_total[5m]))" | jq
curl -s "${PROMETHEUS_URL}/api/v1/query?query=sum(rate(neural_hive_plans_generated_total[5m]))" | jq
curl -s "${PROMETHEUS_URL}/api/v1/query?query=sum(rate(neural_hive_consensus_decisions_total[5m]))" | jq
curl -s "${PROMETHEUS_URL}/api/v1/query?query=sum(rate(neural_hive_execution_tickets_generated_total[5m]))" | jq

EOF
    
    chmod +x "$OUTPUT_DIR/e2e-test-commands.sh"
    log SUCCESS "Script de comandos gerado: $OUTPUT_DIR/e2e-test-commands.sh"
}

# Gerar template de relatório
generate_report_template() {
    log INFO "Gerando template de relatório..."
    
    cat > "$OUTPUT_DIR/e2e-test-report-template.md" <<EOF
# Relatório de Teste E2E Manual - Neural Hive-Mind

**Data**: $(date '+%Y-%m-%d')  
**Executor**: ___________________________  
**Cluster**: ___________________________  
**Versão dos Serviços**: ___________________________

---

## FASE 1: Fluxo A (Gateway → Kafka)

### Intenção Enviada
- **Tipo**: ___________________________
- **intent_id**: ___________________________
- **correlation_id**: ___________________________
- **trace_id**: ___________________________
- **domain**: ___________________________
- **confidence**: ___________________________

### Validações
- [ ] Intenção publicada no Kafka
- [ ] Métricas no Prometheus incrementadas
- [ ] Trace visível no Jaeger
- [ ] Cache criado no Redis

### Observações
___________________________

---

## FASE 2: Fluxo B (STE → Plano)

### Plano Gerado
- **plan_id**: ___________________________
- **risk_band**: ___________________________
- **num_tasks**: ___________________________

### Validações
- [ ] Plano gerado pelo STE
- [ ] Plano publicado no Kafka (plans.ready)
- [ ] Plano persistido no MongoDB
- [ ] Métricas do STE no Prometheus

### Observações
___________________________

---

## FASE 3: Fluxo B (Specialists)

### Opiniões Recebidas
- **Business opinion_id**: ___________________________
- **Technical opinion_id**: ___________________________
- **Behavior opinion_id**: ___________________________
- **Evolution opinion_id**: ___________________________
- **Architecture opinion_id**: ___________________________

### Validações
- [ ] 5 Specialists responderam
- [ ] Opiniões persistidas no MongoDB
- [ ] Métricas dos Specialists no Prometheus
- [ ] Traces dos Specialists no Jaeger

### Observações
___________________________

---

## FASE 4: Fluxo C (Consensus Engine)

### Decisão Consolidada
- **decision_id**: ___________________________
- **final_decision**: ___________________________
- **consensus_score**: ___________________________
- **divergence_score**: ___________________________

### Validações
- [ ] Decisão consolidada
- [ ] Decisão publicada no Kafka (plans.consensus)
- [ ] Decisão persistida no MongoDB
- [ ] Feromônios publicados no Redis
- [ ] Métricas do Consensus no Prometheus

### Observações
___________________________

---

## FASE 5: Fluxo C (Orchestrator)

### Tickets Gerados
- **Primeiro ticket_id**: ___________________________
- **Número de tickets**: ___________________________

### Validações
- [ ] Tickets gerados
- [ ] Tickets publicados no Kafka (execution.tickets)
- [ ] Tickets persistidos no MongoDB
- [ ] Métricas do Orchestrator no Prometheus

### Observações
___________________________

---

## Validação Consolidada E2E

### Correlação no MongoDB
- **Intents**: ___ (esperado: 1)
- **Plans**: ___ (esperado: 1)
- **Opinions**: ___ (esperado: 5)
- **Decisions**: ___ (esperado: 1)
- **Tickets**: ___ (esperado: ≥1)

### Trace Completo no Jaeger
- **Duração total E2E**: ___ ms
- **Latência Gateway**: ___ ms
- **Latência STE**: ___ ms
- **Latência Specialists**: ___ ms
- **Latência Consensus**: ___ ms
- **Latência Orchestrator**: ___ ms

### Métricas Agregadas no Prometheus
- **Taxa de intenções**: ___ req/s
- **Taxa de planos**: ___ req/s
- **Taxa de decisões**: ___ req/s
- **Taxa de tickets**: ___ req/s

### Validações
- [ ] Correlação completa verificada
- [ ] Trace end-to-end completo
- [ ] Métricas consistentes (sem perdas)
- [ ] Feromônios publicados

---

## Resultado Final

- [ ] ✅ **TESTE PASSOU** - Todos os fluxos validados com sucesso
- [ ] ❌ **TESTE FALHOU** - Falhas identificadas (detalhar abaixo)

### Falhas Identificadas
1. ___________________________
2. ___________________________
3. ___________________________

### Ações Corretivas
1. ___________________________
2. ___________________________
3. ___________________________

---

**Assinatura**: ___________________________  
**Data de Conclusão**: ___________________________
EOF
    
    log SUCCESS "Template de relatório gerado: $OUTPUT_DIR/e2e-test-report-template.md"
}

# Configurar port-forwards
setup_port_forwards() {
    if [ "$SETUP_PORT_FORWARDS" = true ]; then
        log INFO "Configurando port-forwards..."
        
        # Verificar se já existem port-forwards ativos
        if pgrep -f "port-forward.*prometheus-server" > /dev/null; then
            log WARN "Port-forward do Prometheus já está ativo"
        else
            kubectl port-forward -n observability svc/prometheus-server 9090:80 > /dev/null 2>&1 &
            log SUCCESS "Port-forward do Prometheus configurado: http://localhost:9090"
        fi
        
        if pgrep -f "port-forward.*jaeger-query" > /dev/null; then
            log WARN "Port-forward do Jaeger já está ativo"
        else
            kubectl port-forward -n observability svc/jaeger-query 16686:16686 > /dev/null 2>&1 &
            log SUCCESS "Port-forward do Jaeger configurado: http://localhost:16686"
        fi
        
        log INFO "Para parar os port-forwards: pkill -f 'port-forward.*prometheus-server|port-forward.*jaeger-query'"
    fi
}

# Main
main() {
    log INFO "Iniciando preparação de dados de teste E2E..."
    
    validate_prerequisites
    detect_service_pods
    validate_pods_status
    create_output_dir
    generate_test_payloads
    generate_config_file
    generate_commands_script
    generate_report_template
    setup_port_forwards
    
    log SUCCESS "Preparação concluída!"
    echo ""
    log INFO "Próximos passos:"
    echo "  1. Carregar configurações: source $OUTPUT_DIR/e2e-test-config.env"
    echo "  2. Consultar guia completo: docs/manual-deployment/08-e2e-testing-manual-guide.md"
    echo "  3. Usar comandos prontos: $OUTPUT_DIR/e2e-test-commands.sh"
    echo "  4. Documentar resultados: $OUTPUT_DIR/e2e-test-report-template.md"
    echo ""
    log INFO "Payloads de teste disponíveis em: $OUTPUT_DIR"
    ls -lh "$OUTPUT_DIR"/*.json 2>/dev/null || true
}

main "$@"
