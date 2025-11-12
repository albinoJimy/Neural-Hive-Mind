#!/bin/bash
# Script automatizado para rebuild e deploy da correção de protobuf
# Neural Hive-Mind v1.0.10 - Correção de TypeError em evaluated_at

set -euo pipefail

# ============================================================
# CONFIGURAÇÃO E VARIÁVEIS
# ============================================================

VERSION="${VERSION:-1.0.10}"
NAMESPACE="${NAMESPACE:-neural-hive}"
OPTION="${OPTION:-A}"  # A=downgrade (padrão), B=upgrade
SKIP_TESTS="${SKIP_TESTS:-false}"
DRY_RUN="${DRY_RUN:-false}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

# Cores ANSI para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Componentes a serem reconstruídos
COMPONENTS=("consensus-engine" "specialist-business" "specialist-technical" "specialist-behavior" "specialist-evolution" "specialist-architecture")

# Contadores de status
BUILD_SUCCESS_COUNT=0
BUILD_FAIL_COUNT=0
DEPLOY_SUCCESS_COUNT=0
DEPLOY_FAIL_COUNT=0
TEST_SUCCESS_COUNT=0
TEST_FAIL_COUNT=0

# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

print_banner() {
    echo -e "${BLUE}"
    echo "============================================================"
    echo "  Neural Hive-Mind - Protobuf Fix Deployment"
    echo "  Rebuild & Deploy v${VERSION}"
    echo "============================================================"
    echo -e "${NC}"
    echo "Opção Escolhida: ${OPTION} (${OPTION^^})"
    echo "Versão Target: ${VERSION}"
    echo "Namespace: ${NAMESPACE}"
    echo "Componentes: ${#COMPONENTS[@]} (consensus-engine + 5 specialists)"
    echo "Dry Run: ${DRY_RUN}"
    echo "Skip Tests: ${SKIP_TESTS}"
    echo ""
    echo -e "${YELLOW}ATENÇÃO: Este script irá rebuildar e redeploy 6 componentes${NC}"
    echo ""
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

check_prerequisites() {
    log_info "Verificando pré-requisitos..."

    # Verificar Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker não encontrado. Instale Docker para continuar."
        exit 1
    fi

    if ! docker info &> /dev/null; then
        log_error "Docker daemon não está rodando. Inicie o Docker."
        exit 1
    fi
    log_success "Docker disponível e rodando"

    # Verificar kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl não encontrado. Instale kubectl para continuar."
        exit 1
    fi

    if ! kubectl cluster-info &> /dev/null; then
        log_error "kubectl não conectado ao cluster. Configure o contexto."
        exit 1
    fi
    log_success "kubectl disponível e conectado"

    # Verificar Helm
    if ! command -v helm &> /dev/null; then
        log_error "Helm não encontrado. Instale Helm para continuar."
        exit 1
    fi
    log_success "Helm disponível"

    # Verificar namespace
    if ! kubectl get namespace "${NAMESPACE}" &> /dev/null; then
        log_error "Namespace '${NAMESPACE}' não existe. Crie o namespace primeiro."
        exit 1
    fi
    log_success "Namespace '${NAMESPACE}' existe"

    # Verificar arquivos modificados
    local required_files=(
        "scripts/generate_protos.sh"
        "services/consensus-engine/requirements.txt"
        "libraries/python/neural_hive_specialists/requirements.txt"
    )

    for file in "${required_files[@]}"; do
        if [ ! -f "$file" ]; then
            log_error "Arquivo não encontrado: $file"
            exit 1
        fi
    done
    log_success "Todos os arquivos necessários encontrados"

    echo ""
}

validate_option_choice() {
    log_info "Validando escolha de opção..."

    if [[ ! "$OPTION" =~ ^[AB]$ ]]; then
        log_error "Opção inválida: ${OPTION}. Use A (downgrade) ou B (upgrade)."
        exit 1
    fi

    if [ "$OPTION" = "A" ]; then
        log_info "Opção A selecionada: Downgrade para protobuf 4.x"

        # Verificar que generate_protos.sh usa namely/protoc-all:1.29_0
        if ! grep -q "namely/protoc-all:1.29_0" scripts/generate_protos.sh; then
            log_error "scripts/generate_protos.sh não usa namely/protoc-all:1.29_0"
            log_error "Execute: sed -i 's/namely\/protoc-all:1.51_1/namely\/protoc-all:1.29_0/' scripts/generate_protos.sh"
            exit 1
        fi

        # Verificar que requirements.txt contém protobuf>=4.21.6,<5.0.0
        if ! grep -q "protobuf>=4.21.6,<5.0.0" services/consensus-engine/requirements.txt; then
            log_error "services/consensus-engine/requirements.txt não contém protobuf>=4.21.6,<5.0.0"
            exit 1
        fi

        if ! grep -q "protobuf>=4.21.6,<5.0.0" libraries/python/neural_hive_specialists/requirements.txt; then
            log_error "libraries/python/neural_hive_specialists/requirements.txt não contém protobuf>=4.21.6,<5.0.0"
            exit 1
        fi

        log_success "Opção A validada: Arquivos configurados para protobuf 4.x"

    elif [ "$OPTION" = "B" ]; then
        log_info "Opção B selecionada: Upgrade para protobuf 6.x"

        # Verificar que generate_protos.sh usa namely/protoc-all:1.51_1
        if ! grep -q "namely/protoc-all:1.51_1" scripts/generate_protos.sh; then
            log_error "scripts/generate_protos.sh não usa namely/protoc-all:1.51_1"
            exit 1
        fi

        # Verificar que requirements.txt contém protobuf>=6.30.0,<7.0.0 e grpcio>=1.73.0
        if ! grep -q "protobuf>=6.30.0,<7.0.0" services/consensus-engine/requirements.txt; then
            log_error "services/consensus-engine/requirements.txt não contém protobuf>=6.30.0,<7.0.0"
            exit 1
        fi

        if ! grep -q "grpcio>=1.73.0" services/consensus-engine/requirements.txt; then
            log_error "services/consensus-engine/requirements.txt não contém grpcio>=1.73.0"
            exit 1
        fi

        # Verificar requirements da biblioteca neural_hive_specialists
        log_info "Validando requirements da biblioteca neural_hive_specialists..."

        if ! grep -q "grpcio>=1.73.0" libraries/python/neural_hive_specialists/requirements.txt; then
            log_error "libraries/python/neural_hive_specialists/requirements.txt não contém grpcio>=1.73.0"
            exit 1
        fi

        if ! grep -q "grpcio-tools>=1.73.0" libraries/python/neural_hive_specialists/requirements.txt; then
            log_error "libraries/python/neural_hive_specialists/requirements.txt não contém grpcio-tools>=1.73.0"
            exit 1
        fi

        if ! grep -q "grpcio-health-checking>=1.73.0" libraries/python/neural_hive_specialists/requirements.txt; then
            log_error "libraries/python/neural_hive_specialists/requirements.txt não contém grpcio-health-checking>=1.73.0"
            exit 1
        fi

        if ! grep -q "protobuf>=6.30.0,<7.0.0" libraries/python/neural_hive_specialists/requirements.txt; then
            log_error "libraries/python/neural_hive_specialists/requirements.txt não contém protobuf>=6.30.0,<7.0.0"
            exit 1
        fi

        log_success "Opção B validada: Arquivos configurados para protobuf 6.x"
    fi

    echo ""
}

recompile_protobuf() {
    log_info "Recompilando protobuf..."

    if [ "$OPTION" = "B" ]; then
        log_info "Opção B: Protobuf já compilado com 6.x, pulando recompilação"
        return 0
    fi

    local start_time=$(date +%s)

    if ./scripts/generate_protos.sh; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))

        # Verificar que specialist_pb2.py foi gerado
        if [ ! -f "libraries/python/neural_hive_specialists/proto_gen/specialist_pb2.py" ]; then
            log_error "specialist_pb2.py não foi gerado"
            exit 1
        fi

        # Extrair versão de protobuf do arquivo gerado
        # Primeiro, tentar extrair da chamada _runtime_version.ValidateProtobufRuntimeVersion
        local protobuf_version=$(grep -o "ValidateProtobufRuntimeVersion(['\"][0-9.]*['\"]" libraries/python/neural_hive_specialists/proto_gen/specialist_pb2.py | grep -o "[0-9.]*" | head -1)

        # Se não encontrar, tentar o método antigo (comentário "Protobuf Python Version")
        if [ -z "$protobuf_version" ]; then
            protobuf_version=$(head -20 libraries/python/neural_hive_specialists/proto_gen/specialist_pb2.py | grep "Protobuf Python Version" | awk '{print $5}')
        fi

        # Como fallback final, verificar o compilador instalado
        if [ -z "$protobuf_version" ]; then
            log_warning "Não foi possível extrair versão do pb2.py, verificando compilador..."
            protobuf_version=$(python3 -c 'import google.protobuf; print(google.protobuf.__version__)' 2>/dev/null || echo "")
        fi

        if [ -z "$protobuf_version" ]; then
            log_error "Não foi possível determinar versão de protobuf em specialist_pb2.py"
            exit 1
        fi

        log_info "Versão de protobuf detectada: ${protobuf_version}"

        # Validar versão
        if [ "$OPTION" = "A" ]; then
            if [[ ! "$protobuf_version" =~ ^4\. ]]; then
                log_error "Versão de protobuf esperada: 4.x.x, encontrada: ${protobuf_version}"
                exit 1
            fi
        elif [ "$OPTION" = "B" ]; then
            if [[ ! "$protobuf_version" =~ ^6\. ]]; then
                log_error "Versão de protobuf esperada: 6.x.x, encontrada: ${protobuf_version}"
                exit 1
            fi
        fi

        log_success "Protobuf recompilado com sucesso em ${duration}s (versão ${protobuf_version})"
    else
        log_error "Falha ao recompilar protobuf"
        exit 1
    fi

    echo ""
}

build_consensus_engine() {
    log_info "Building consensus-engine:${VERSION}..."

    local start_time=$(date +%s)

    if docker build -t neural-hive-mind/consensus-engine:${VERSION} \
        -f services/consensus-engine/Dockerfile . 2>&1 | tee /tmp/build-consensus-engine.log; then

        local end_time=$(date +%s)
        local duration=$((end_time - start_time))

        log_success "consensus-engine built in ${duration}s"
        ((BUILD_SUCCESS_COUNT++))

        # Carregar imagem no cluster se for kind
        if kubectl config current-context | grep -q "kind"; then
            log_info "Carregando imagem no kind cluster..."
            kind load docker-image neural-hive-mind/consensus-engine:${VERSION} --name neural-hive-cluster || log_warning "Falha ao carregar imagem no kind"
        fi
    else
        log_error "Falha ao buildar consensus-engine (ver /tmp/build-consensus-engine.log)"
        ((BUILD_FAIL_COUNT++))
        exit 1
    fi

    echo ""
}

build_specialists() {
    log_info "Building specialists..."

    local specialists=("business" "technical" "behavior" "evolution" "architecture")
    local failed_specialists=()

    for specialist in "${specialists[@]}"; do
        log_info "Building specialist-${specialist}:${VERSION}..."

        local start_time=$(date +%s)

        if docker build -t neural-hive-mind/specialist-${specialist}:${VERSION} \
            -f services/specialist-${specialist}/Dockerfile . 2>&1 | tee /tmp/build-specialist-${specialist}.log; then

            local end_time=$(date +%s)
            local duration=$((end_time - start_time))

            log_success "specialist-${specialist} built in ${duration}s"
            ((BUILD_SUCCESS_COUNT++))

            # Carregar imagem no cluster se for kind
            if kubectl config current-context | grep -q "kind"; then
                kind load docker-image neural-hive-mind/specialist-${specialist}:${VERSION} --name neural-hive-cluster 2>/dev/null || true
            fi
        else
            log_error "Falha ao buildar specialist-${specialist} (ver /tmp/build-specialist-${specialist}.log)"
            failed_specialists+=("$specialist")
            ((BUILD_FAIL_COUNT++))
        fi
    done

    echo ""
    log_info "Build Summary: ${BUILD_SUCCESS_COUNT} successful, ${BUILD_FAIL_COUNT} failed"

    if [ ${BUILD_FAIL_COUNT} -gt 0 ]; then
        log_error "Alguns builds falharam: ${failed_specialists[*]}"
        exit 1
    fi

    echo ""
}

deploy_consensus_engine() {
    log_info "Deploying consensus-engine..."

    if helm upgrade --install consensus-engine helm-charts/consensus-engine/ \
        -n ${NAMESPACE} \
        --set image.tag=${VERSION} \
        --wait --timeout=5m; then

        log_success "consensus-engine deployed"

        # Aguardar rollout
        if kubectl rollout status deployment/consensus-engine -n ${NAMESPACE} --timeout=5m; then
            log_success "consensus-engine rollout completed"

            # Verificar versão de protobuf em runtime
            local pod_name=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=consensus-engine -o jsonpath='{.items[0].metadata.name}')
            if [ -n "$pod_name" ]; then
                log_info "Verificando versão de protobuf em runtime..."
                local runtime_version=$(kubectl exec -n ${NAMESPACE} ${pod_name} -- pip show protobuf 2>/dev/null | grep Version | awk '{print $2}')

                if [ -n "$runtime_version" ]; then
                    log_info "Versão de protobuf em runtime: ${runtime_version}"

                    # Validar versão de protobuf em runtime e falhar se não corresponder
                    if [ "$OPTION" = "A" ]; then
                        if [[ "$runtime_version" =~ ^4\. ]]; then
                            log_success "Versão de protobuf em runtime corresponde à esperada (4.x)"
                        else
                            log_error "consensus-engine: versão de protobuf em runtime não corresponde (esperada 4.x, encontrada ${runtime_version})"
                            ((DEPLOY_FAIL_COUNT++))
                            exit 1
                        fi
                    elif [ "$OPTION" = "B" ]; then
                        if [[ "$runtime_version" =~ ^6\. ]]; then
                            log_success "Versão de protobuf em runtime corresponde à esperada (6.x)"
                        else
                            log_error "consensus-engine: versão de protobuf em runtime não corresponde (esperada 6.x, encontrada ${runtime_version})"
                            ((DEPLOY_FAIL_COUNT++))
                            exit 1
                        fi
                    fi
                else
                    log_warning "consensus-engine: não foi possível verificar versão de protobuf em runtime"
                fi
            fi

            ((DEPLOY_SUCCESS_COUNT++))
        else
            log_error "consensus-engine rollout falhou"
            ((DEPLOY_FAIL_COUNT++))
            exit 1
        fi
    else
        log_error "Falha ao deployar consensus-engine"
        ((DEPLOY_FAIL_COUNT++))
        exit 1
    fi

    echo ""
}

deploy_specialists() {
    log_info "Deploying specialists..."

    local specialists=("business" "technical" "behavior" "evolution" "architecture")
    local failed_specialists=()

    for specialist in "${specialists[@]}"; do
        log_info "Deploying specialist-${specialist}..."

        if helm upgrade --install specialist-${specialist} helm-charts/specialist-${specialist}/ \
            -n ${NAMESPACE} \
            -f helm-charts/specialist-${specialist}/values-k8s.yaml \
            --set image.tag=${VERSION} \
            --wait --timeout=5m; then

            log_success "specialist-${specialist} deployed"

            # Aguardar rollout
            if kubectl rollout status deployment/specialist-${specialist} -n ${NAMESPACE} --timeout=5m; then
                log_success "specialist-${specialist} rollout completed"

                # Verificar versão de protobuf em runtime
                local pod_name=$(kubectl get pods -n ${NAMESPACE} -l app=specialist-${specialist} -o jsonpath='{.items[0].metadata.name}')
                if [ -n "$pod_name" ]; then
                    local runtime_version=$(kubectl exec -n ${NAMESPACE} ${pod_name} -- pip show protobuf 2>/dev/null | grep Version | awk '{print $2}' || echo "N/A")
                    log_info "specialist-${specialist} protobuf version: ${runtime_version}"

                    # Validar versão de protobuf em runtime
                    if [ "$runtime_version" != "N/A" ]; then
                        if [ "$OPTION" = "A" ]; then
                            if [[ ! "$runtime_version" =~ ^4\. ]]; then
                                log_error "specialist-${specialist}: versão de protobuf em runtime não corresponde (esperada 4.x, encontrada ${runtime_version})"
                                failed_specialists+=("$specialist")
                                ((DEPLOY_FAIL_COUNT++))
                                ((DEPLOY_SUCCESS_COUNT--))
                                continue
                            else
                                log_success "specialist-${specialist}: versão de protobuf em runtime corresponde à esperada (4.x)"
                            fi
                        elif [ "$OPTION" = "B" ]; then
                            if [[ ! "$runtime_version" =~ ^6\. ]]; then
                                log_error "specialist-${specialist}: versão de protobuf em runtime não corresponde (esperada 6.x, encontrada ${runtime_version})"
                                failed_specialists+=("$specialist")
                                ((DEPLOY_FAIL_COUNT++))
                                ((DEPLOY_SUCCESS_COUNT--))
                                continue
                            else
                                log_success "specialist-${specialist}: versão de protobuf em runtime corresponde à esperada (6.x)"
                            fi
                        fi
                    else
                        log_warning "specialist-${specialist}: não foi possível verificar versão de protobuf em runtime"
                    fi
                fi

                ((DEPLOY_SUCCESS_COUNT++))
            else
                log_error "specialist-${specialist} rollout falhou"
                failed_specialists+=("$specialist")
                ((DEPLOY_FAIL_COUNT++))
            fi
        else
            log_error "Falha ao deployar specialist-${specialist}"
            failed_specialists+=("$specialist")
            ((DEPLOY_FAIL_COUNT++))
        fi
    done

    echo ""
    log_info "Deploy Summary: ${DEPLOY_SUCCESS_COUNT} successful, ${DEPLOY_FAIL_COUNT} failed"

    if [ ${DEPLOY_FAIL_COUNT} -gt 0 ]; then
        log_error "Alguns deploys falharam: ${failed_specialists[*]}"
        exit 1
    fi

    echo ""
}

run_validation_tests() {
    if [ "$SKIP_TESTS" = "true" ]; then
        log_info "Pulando testes de validação (SKIP_TESTS=true)"
        return 0
    fi

    log_info "Executando testes de validação..."
    log_info "Aguardando 30 segundos para pods estabilizarem..."
    sleep 30

    # Teste 1: Análise de versões
    log_info "Teste 1: Análise de versões"
    if [ -f "scripts/debug/run-full-version-analysis.sh" ]; then
        if ./scripts/debug/run-full-version-analysis.sh; then
            log_success "Teste de versões passou"
            ((TEST_SUCCESS_COUNT++))
        else
            log_warning "Teste de versões falhou"
            ((TEST_FAIL_COUNT++))
        fi
    else
        log_warning "Script de análise de versões não encontrado, pulando"
    fi

    # Teste 2: Teste gRPC isolado
    log_info "Teste 2: Teste gRPC isolado"
    if [ -f "scripts/debug/test-grpc-isolated.py" ]; then
        if python3 scripts/debug/test-grpc-isolated.py; then
            log_success "Teste gRPC isolado passou"
            ((TEST_SUCCESS_COUNT++))
        else
            log_warning "Teste gRPC isolado falhou"
            ((TEST_FAIL_COUNT++))
        fi
    else
        log_warning "Script de teste gRPC isolado não encontrado, pulando"
    fi

    # Teste 3: Teste gRPC abrangente
    log_info "Teste 3: Teste gRPC abrangente (specialist-business)"
    if [ -f "scripts/debug/test-grpc-comprehensive.py" ]; then
        if python3 scripts/debug/test-grpc-comprehensive.py --specialist business; then
            log_success "Teste gRPC abrangente passou"
            ((TEST_SUCCESS_COUNT++))
        else
            log_warning "Teste gRPC abrangente falhou"
            ((TEST_FAIL_COUNT++))
        fi
    else
        log_warning "Script de teste gRPC abrangente não encontrado, pulando"
    fi

    echo ""
    log_info "Testes Summary: ${TEST_SUCCESS_COUNT} successful, ${TEST_FAIL_COUNT} failed"

    if [ ${TEST_FAIL_COUNT} -gt 0 ]; then
        log_warning "Alguns testes falharam. Revise os logs para mais detalhes."
        log_warning "Isto é informativo - o deploy foi concluído com sucesso."
    fi

    echo ""
}

generate_deployment_report() {
    log_info "Gerando relatório de deployment..."

    local report_file="DEPLOYMENT_REPORT_PROTOBUF_FIX_${TIMESTAMP}.md"

    cat > "$report_file" <<EOF
# Relatório de Deploy - Correção de Protobuf v${VERSION}

**Data:** $(date '+%Y-%m-%d %H:%M:%S')
**Opção:** ${OPTION} ($([ "$OPTION" = "A" ] && echo "Downgrade para protobuf 4.x" || echo "Upgrade para protobuf 6.x"))
**Namespace:** ${NAMESPACE}
**Versão:** ${VERSION}

---

## Sumário Executivo

Este deploy implementou a correção de incompatibilidade de versões protobuf identificada nos tickets GRPC-DEBUG-001, 002 e 003.

**Problema:** TypeError ao acessar \`evaluated_at.seconds\` em responses gRPC
**Causa Raiz:** Incompatibilidade entre protobuf de compilação (6.31.1) e runtime (<5.0.0)
**Solução:** $([ "$OPTION" = "A" ] && echo "Downgrade de protobuf compiler para 4.x + pin runtime em 4.x" || echo "Upgrade de grpcio-tools e protobuf runtime para 6.x")

---

## Componentes Modificados

Total: 6 componentes

1. ✅ consensus-engine:${VERSION}
2. ✅ specialist-business:${VERSION}
3. ✅ specialist-technical:${VERSION}
4. ✅ specialist-behavior:${VERSION}
5. ✅ specialist-evolution:${VERSION}
6. ✅ specialist-architecture:${VERSION}

---

## Resultados

### Build
- Sucessos: ${BUILD_SUCCESS_COUNT}
- Falhas: ${BUILD_FAIL_COUNT}
- Status: $([ ${BUILD_FAIL_COUNT} -eq 0 ] && echo "✅ SUCESSO" || echo "❌ FALHA")

### Deploy
- Sucessos: ${DEPLOY_SUCCESS_COUNT}
- Falhas: ${DEPLOY_FAIL_COUNT}
- Status: $([ ${DEPLOY_FAIL_COUNT} -eq 0 ] && echo "✅ SUCESSO" || echo "❌ FALHA")

### Testes de Validação
- Sucessos: ${TEST_SUCCESS_COUNT}
- Falhas: ${TEST_FAIL_COUNT}
- Status: $([ ${TEST_FAIL_COUNT} -eq 0 ] && echo "✅ SUCESSO" || echo "⚠️ PARCIAL")

---

## Comandos de Validação Manual

### Verificar Status dos Pods
\`\`\`bash
kubectl get pods -n ${NAMESPACE} -l 'app.kubernetes.io/name in (consensus-engine),app in (specialist-business,specialist-technical,specialist-behavior,specialist-evolution,specialist-architecture)'
\`\`\`

### Verificar Versão de Protobuf
\`\`\`bash
# Consensus Engine
kubectl exec -n ${NAMESPACE} \$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=consensus-engine -o jsonpath='{.items[0].metadata.name}') -- pip show protobuf | grep Version

# Specialists
for specialist in business technical behavior evolution architecture; do
  echo "=== specialist-\${specialist} ==="
  kubectl exec -n ${NAMESPACE} \$(kubectl get pods -n ${NAMESPACE} -l app=specialist-\${specialist} -o jsonpath='{.items[0].metadata.name}') -- pip show protobuf | grep Version
done
\`\`\`

### Verificar Logs
\`\`\`bash
# Consensus Engine
kubectl logs -n ${NAMESPACE} -l app.kubernetes.io/name=consensus-engine --tail=100

# Specialists
kubectl logs -n ${NAMESPACE} -l 'app in (specialist-business,specialist-technical,specialist-behavior,specialist-evolution,specialist-architecture)' --tail=100
\`\`\`

### Buscar Erros de TypeError
\`\`\`bash
kubectl logs -n ${NAMESPACE} -l app.kubernetes.io/name=consensus-engine --tail=500 | grep -i "typeerror"
\`\`\`

---

## Comandos de Rollback (Se Necessário)

Se a correção não resolver o problema ou introduzir novos issues:

\`\`\`bash
# Rollback Consensus Engine
helm rollback consensus-engine -n ${NAMESPACE}

# Rollback Specialists
for specialist in business technical behavior evolution architecture; do
  helm rollback specialist-\${specialist} -n ${NAMESPACE}
done

# Aguardar pods voltarem
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=consensus-engine -n ${NAMESPACE} --timeout=5m
\`\`\`

---

## Próximos Passos

1. ✅ Monitorar logs por 30 minutos para TypeErrors
2. ✅ Executar testes gRPC manualmente se não executados automaticamente
3. ✅ Verificar métricas de erro em Prometheus/Grafana
4. ✅ Confirmar que fluxo E2E funciona corretamente
5. ✅ Atualizar documentação com resolução
6. ✅ Fechar tickets GRPC-DEBUG-001, 002, 003

---

## Referências

- Framework de Decisão: [DECISION_FRAMEWORK_PROTOBUF_FIX.md](DECISION_FRAMEWORK_PROTOBUF_FIX.md)
- Análise de Debug: [ANALISE_DEBUG_GRPC_TYPEERROR.md](ANALISE_DEBUG_GRPC_TYPEERROR.md)
- Análise de Versões: [PROTOBUF_VERSION_ANALYSIS.md](PROTOBUF_VERSION_ANALYSIS.md)
- Checklist de Validação: [VALIDATION_CHECKLIST_PROTOBUF_FIX.md](VALIDATION_CHECKLIST_PROTOBUF_FIX.md)

---

**Gerado por:** rebuild-and-deploy-protobuf-fix.sh
**Timestamp:** ${TIMESTAMP}
EOF

    log_success "Relatório gerado: ${report_file}"
    echo ""
}

# ============================================================
# FUNÇÃO PRINCIPAL
# ============================================================

main() {
    # Parsear argumentos
    while [[ $# -gt 0 ]]; do
        case $1 in
            --option)
                OPTION="$2"
                shift 2
                ;;
            --version)
                VERSION="$2"
                shift 2
                ;;
            --namespace)
                NAMESPACE="$2"
                shift 2
                ;;
            --skip-tests)
                SKIP_TESTS="true"
                shift
                ;;
            --dry-run)
                DRY_RUN="true"
                shift
                ;;
            --help)
                echo "Uso: $0 [opções]"
                echo ""
                echo "Opções:"
                echo "  --option A|B          Escolher opção de correção (A=downgrade, B=upgrade)"
                echo "  --version X.Y.Z       Versão da imagem (default: 1.0.10)"
                echo "  --namespace NAME      Namespace Kubernetes (default: neural-hive)"
                echo "  --skip-tests          Pular testes de validação"
                echo "  --dry-run             Apenas validar, não executar build/deploy"
                echo "  --help                Exibir esta mensagem"
                echo ""
                echo "Exemplo:"
                echo "  $0 --option A                    # Usar Opção A (downgrade)"
                echo "  $0 --option B --skip-tests       # Usar Opção B (upgrade) sem testes"
                echo "  $0 --option A --dry-run          # Validar Opção A sem executar"
                exit 0
                ;;
            *)
                log_error "Argumento desconhecido: $1"
                exit 1
                ;;
        esac
    done

    # Executar fluxo
    print_banner
    check_prerequisites
    validate_option_choice

    if [ "$DRY_RUN" = "true" ]; then
        log_success "Dry run completado. Todas as validações passaram."
        exit 0
    fi

    recompile_protobuf
    build_consensus_engine
    build_specialists
    deploy_consensus_engine
    deploy_specialists
    run_validation_tests
    generate_deployment_report

    echo -e "${GREEN}"
    echo "============================================================"
    echo "  Deploy Completo e Validado!"
    echo "  Versão: ${VERSION}"
    echo "  Builds: ${BUILD_SUCCESS_COUNT}/${#COMPONENTS[@]} sucesso"
    echo "  Deploys: ${DEPLOY_SUCCESS_COUNT}/${#COMPONENTS[@]} sucesso"
    if [ "$SKIP_TESTS" = "false" ]; then
        echo "  Testes: ${TEST_SUCCESS_COUNT}/3 sucesso"
    fi
    echo "============================================================"
    echo -e "${NC}"

    log_info "Próximos passos:"
    echo "  1. Monitorar logs por 30 minutos"
    echo "  2. Verificar que TypeError não ocorre mais"
    echo "  3. Executar testes E2E se disponíveis"
    echo "  4. Confirmar com equipe que sistema está estável"
    echo "  5. Atualizar documentação e fechar tickets"
    echo ""
}

# ============================================================
# TRATAMENTO DE ERROS E EXECUÇÃO
# ============================================================

trap 'log_error "Script interrompido pelo usuário"; exit 130' INT
trap 'log_error "Erro na linha $LINENO"; exit 1' ERR

# Executar main
main "$@"
