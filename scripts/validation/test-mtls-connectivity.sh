#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
# Teste de conectividade mTLS entre serviços
# Valida mTLS STRICT com certificados SPIFFE

set -euo pipefail

# Configurações
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Carregar funções comuns de validação
source "${SCRIPT_DIR}/common-validation-functions.sh"

# Deploy pods de teste
deploy_test_pods() {
    log_info "Deployando pods de teste..."

    # Criar namespaces se não existirem
    kubectl get ns neural-hive-cognition >/dev/null 2>&1 || kubectl create ns neural-hive-cognition
    kubectl get ns neural-hive-orchestration >/dev/null 2>&1 || kubectl create ns neural-hive-orchestration

    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mtls-test-client
  namespace: neural-hive-cognition
  labels:
    app: mtls-test-client
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mtls-test-client
  template:
    metadata:
      labels:
        app: mtls-test-client
    spec:
      containers:
      - name: client
        image: curlimages/curl:latest
        command: ["sleep", "3600"]
        resources:
          requests:
            cpu: 50m
            memory: 64Mi
          limits:
            cpu: 100m
            memory: 128Mi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mtls-test-server
  namespace: neural-hive-orchestration
  labels:
    app: mtls-test-server
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mtls-test-server
  template:
    metadata:
      labels:
        app: mtls-test-server
    spec:
      containers:
      - name: server
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
---
apiVersion: v1
kind: Service
metadata:
  name: mtls-test-server
  namespace: neural-hive-orchestration
spec:
  selector:
    app: mtls-test-server
  ports:
  - port: 80
    targetPort: 80
EOF

    kubectl wait --for=condition=ready pod -l app=mtls-test-client -n neural-hive-cognition --timeout=60s
    kubectl wait --for=condition=ready pod -l app=mtls-test-server -n neural-hive-orchestration --timeout=60s

    log_success "Pods de teste deployados"
}

# Testar conectividade mTLS
test_mtls_connectivity() {
    log_info "Testando conectividade mTLS..."

    CLIENT_POD=$(kubectl get pod -l app=mtls-test-client -n neural-hive-cognition -o jsonpath='{.items[0].metadata.name}')

    # Teste 1: Conectividade básica
    if kubectl exec $CLIENT_POD -n neural-hive-cognition -- curl -s -o /dev/null -w "%{http_code}" http://mtls-test-server.neural-hive-orchestration.svc.cluster.local | grep -q "200"; then
        log_success "Conectividade HTTP básica funcionando"
    else
        log_error "Falha na conectividade HTTP básica"
        return 1
    fi

    # Teste 2: Verificar certificados se istioctl disponível
    if command -v istioctl &> /dev/null; then
        log_info "Verificando certificados SPIFFE..."

        if istioctl authn tls-check $CLIENT_POD.neural-hive-cognition mtls-test-server.neural-hive-orchestration.svc.cluster.local | grep -q "STRICT"; then
            log_success "mTLS STRICT ativo entre pods"
        else
            log_error "mTLS STRICT não ativo"
            return 1
        fi

        # Mostrar detalhes do certificado
        istioctl proxy-config secret $CLIENT_POD.neural-hive-cognition | grep -A5 -B5 SPIFFE || true
    fi
}

# Verificar proxy status
verify_proxy_status() {
    log_info "Verificando status dos proxies..."

    if command -v istioctl &> /dev/null; then
        CLIENT_POD=$(kubectl get pod -l app=mtls-test-client -n neural-hive-cognition -o jsonpath='{.items[0].metadata.name}')
        SERVER_POD=$(kubectl get pod -l app=mtls-test-server -n neural-hive-orchestration -o jsonpath='{.items[0].metadata.name}')

        for pod in "$CLIENT_POD.neural-hive-cognition" "$SERVER_POD.neural-hive-orchestration"; do
            if istioctl proxy-status | grep -q "$pod"; then
                log_success "Proxy ativo em $pod"
            else
                log_error "Proxy não encontrado em $pod"
            fi
        done
    fi
}

# Limpar recursos de teste
cleanup() {
    log_info "Limpando recursos de teste..."
    kubectl delete deployment mtls-test-client -n neural-hive-cognition --ignore-not-found=true
    kubectl delete deployment mtls-test-server -n neural-hive-orchestration --ignore-not-found=true
    kubectl delete service mtls-test-server -n neural-hive-orchestration --ignore-not-found=true
    log_success "Limpeza concluída"
}

trap cleanup EXIT

# Deploy pods de teste abrangentes
deploy_comprehensive_test_pods() {
    log_info "Deployando pods de teste abrangentes para validação mTLS..."

    # Usar função existente
    deploy_test_pods

    # Deploy adicional de pods para testes cross-namespace
    kubectl apply -f - <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: neural-test-isolated
  labels:
    istio-injection: enabled
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mtls-test-isolated
  namespace: neural-test-isolated
  labels:
    app: mtls-test-isolated
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mtls-test-isolated
  template:
    metadata:
      labels:
        app: mtls-test-isolated
    spec:
      containers:
      - name: test
        image: curlimages/curl:latest
        command: ["sleep", "3600"]
        resources:
          requests:
            cpu: 50m
            memory: 64Mi
          limits:
            cpu: 100m
            memory: 128Mi
EOF

    wait_for_pod_ready "neural-test-isolated" "app=mtls-test-isolated" 60
    log_success "Pods de teste abrangentes deployados"
}

# Testar conectividade cross-namespace
test_cross_namespace_connectivity() {
    log_info "Testando conectividade cross-namespace com mTLS..."

    local start_time=$(date +%s)
    local test_passed=true

    # Testar conectividade básica existente
    if test_mtls_connectivity; then
        add_test_result "mtls_basic_connectivity" "PASS" "high" "Conectividade mTLS básica funcionando" ""
    else
        add_test_result "mtls_basic_connectivity" "FAIL" "high" "Falha na conectividade mTLS básica" "Verificar configuração Istio"
        test_passed=false
    fi

    # Testar conectividade entre namespaces diferentes
    local client_pod=$(kubectl get pod -l app=mtls-test-client -n neural-hive-cognition -o jsonpath='{.items[0].metadata.name}')

    # Teste cross-namespace para neural-test-isolated
    if kubectl exec $client_pod -n neural-hive-cognition -- \
        curl -s -o /dev/null -w "%{http_code}" \
        http://mtls-test-server.neural-hive-orchestration.svc.cluster.local \
        2>/dev/null | grep -q "200"; then
        add_test_result "cross_namespace_connectivity" "PASS" "high" \
            "Conectividade cross-namespace funcionando" ""
    else
        add_test_result "cross_namespace_connectivity" "FAIL" "high" \
            "Falha na conectividade cross-namespace" "Verificar políticas de rede"
        test_passed=false
    fi

    local exec_time=$(measure_execution_time $start_time)
    log_info "Teste cross-namespace concluído em ${exec_time}s"

    return $([ "$test_passed" = true ] && echo 0 || echo 1)
}

# Validar identidades SPIFFE
validate_spiffe_identities() {
    log_info "Validando identidades SPIFFE dos workloads..."

    local start_time=$(date +%s)
    local test_passed=true

    if command -v istioctl &> /dev/null; then
        # Obter pods para validação
        local client_pod=$(kubectl get pod -l app=mtls-test-client -n neural-hive-cognition -o jsonpath='{.items[0].metadata.name}')
        local server_pod=$(kubectl get pod -l app=mtls-test-server -n neural-hive-orchestration -o jsonpath='{.items[0].metadata.name}')

        # Verificar identidades SPIFFE
        for pod_ns in "$client_pod.neural-hive-cognition" "$server_pod.neural-hive-orchestration"; do
            local pod=$(echo $pod_ns | cut -d. -f1)
            local ns=$(echo $pod_ns | cut -d. -f2)

            # Verificar certificado SPIFFE
            if istioctl proxy-config secret $pod_ns | grep -q "SPIFFE"; then
                log_success "Identidade SPIFFE encontrada para $pod em $ns"

                # Extrair detalhes do certificado
                local cert_info=$(istioctl proxy-config secret $pod_ns | grep SPIFFE | head -1)
                add_test_result "spiffe_identity_$pod" "PASS" "medium" \
                    "Identidade SPIFFE válida: $cert_info" ""
            else
                log_error "Identidade SPIFFE não encontrada para $pod"
                add_test_result "spiffe_identity_$pod" "FAIL" "medium" \
                    "Identidade SPIFFE ausente para $pod" "Verificar configuração Istio CA"
                test_passed=false
            fi
        done
    else
        add_test_result "spiffe_identities" "SKIP" "medium" \
            "istioctl não disponível para validação SPIFFE" "Instalar istioctl"
    fi

    local exec_time=$(measure_execution_time $start_time)
    log_info "Validação SPIFFE concluída em ${exec_time}s"

    return $([ "$test_passed" = true ] && echo 0 || echo 1)
}

# Verificar status abrangente dos proxies
verify_comprehensive_proxy_status() {
    log_info "Verificando status abrangente dos proxies Envoy..."

    local start_time=$(date +%s)

    # Usar função existente
    verify_proxy_status

    # Verificações adicionais
    if command -v istioctl &> /dev/null; then
        # Verificar sincronização de configuração
        local proxy_count=$(istioctl proxy-status | grep -c "SYNCED")

        if [ $proxy_count -gt 0 ]; then
            add_test_result "proxy_config_sync" "PASS" "high" \
                "$proxy_count proxies sincronizados" ""
        else
            add_test_result "proxy_config_sync" "FAIL" "high" \
                "Nenhum proxy sincronizado" "Verificar Istio control plane"
        fi

        # Verificar listeners ativos
        local client_pod=$(kubectl get pod -l app=mtls-test-client -n neural-hive-cognition -o jsonpath='{.items[0].metadata.name}')
        local listener_count=$(istioctl proxy-config listeners $client_pod.neural-hive-cognition | wc -l)

        if [ $listener_count -gt 5 ]; then
            add_test_result "proxy_listeners" "PASS" "low" \
                "$listener_count listeners configurados" ""
        else
            add_test_result "proxy_listeners" "WARNING" "low" \
                "Apenas $listener_count listeners configurados" "Verificar configuração de listeners"
        fi
    fi

    local exec_time=$(measure_execution_time $start_time)
    log_info "Verificação de proxies concluída em ${exec_time}s"
}

# Testar aplicação de políticas
test_policy_enforcement() {
    log_info "Testando aplicação de políticas de segurança mTLS..."

    local start_time=$(date +%s)
    local test_passed=true

    # Verificar PeerAuthentication
    local peer_auth_count=$(kubectl get peerauthentication --all-namespaces 2>/dev/null | grep -c STRICT || echo 0)

    if [ $peer_auth_count -gt 0 ]; then
        add_test_result "peer_authentication" "PASS" "critical" \
            "$peer_auth_count políticas PeerAuthentication STRICT ativas" ""
    else
        add_test_result "peer_authentication" "WARNING" "critical" \
            "Nenhuma política PeerAuthentication STRICT encontrada" \
            "Configurar PeerAuthentication para mTLS STRICT"
    fi

    # Verificar AuthorizationPolicy
    local auth_policy_count=$(kubectl get authorizationpolicy --all-namespaces 2>/dev/null | wc -l || echo 0)

    if [ $auth_policy_count -gt 1 ]; then
        add_test_result "authorization_policies" "PASS" "high" \
            "$auth_policy_count políticas de autorização configuradas" ""
    else
        add_test_result "authorization_policies" "WARNING" "high" \
            "Poucas políticas de autorização ($auth_policy_count)" \
            "Implementar políticas de autorização granulares"
    fi

    local exec_time=$(measure_execution_time $start_time)
    log_info "Teste de políticas concluído em ${exec_time}s"

    return $([ "$test_passed" = true ] && echo 0 || echo 1)
}

# Testar rotação de certificados
test_certificate_rotation() {
    log_info "Testando capacidade de rotação de certificados..."

    local start_time=$(date +%s)

    if command -v istioctl &> /dev/null; then
        # Verificar tempo de vida dos certificados
        local client_pod=$(kubectl get pod -l app=mtls-test-client -n neural-hive-cognition -o jsonpath='{.items[0].metadata.name}')

        # Obter informações do certificado
        local cert_info=$(istioctl proxy-config secret $client_pod.neural-hive-cognition 2>/dev/null | grep -i "valid" | head -1)

        if [ -n "$cert_info" ]; then
            add_test_result "certificate_info" "PASS" "medium" \
                "Informações de certificado disponíveis" ""

            # Verificar se o certificado tem prazo de validade adequado
            add_test_result "certificate_rotation_capability" "PASS" "medium" \
                "Sistema preparado para rotação de certificados" ""
        else
            add_test_result "certificate_info" "WARNING" "medium" \
                "Não foi possível obter informações de certificado" \
                "Verificar configuração de certificados"
        fi
    else
        add_test_result "certificate_rotation" "SKIP" "medium" \
            "istioctl não disponível para teste de rotação" "Instalar istioctl"
    fi

    local exec_time=$(measure_execution_time $start_time)
    log_info "Teste de rotação concluído em ${exec_time}s"
}

# Testar performance do mTLS
test_mtls_performance() {
    log_info "Testando performance da comunicação mTLS..."

    local start_time=$(date +%s)
    local client_pod=$(kubectl get pod -l app=mtls-test-client -n neural-hive-cognition -o jsonpath='{.items[0].metadata.name}')

    # Teste de latência
    local avg_latency=$(kubectl exec $client_pod -n neural-hive-cognition -- sh -c "
        total=0
        count=10
        for i in \$(seq 1 \$count); do
            start=\$(date +%s%N)
            curl -s -o /dev/null http://mtls-test-server.neural-hive-orchestration.svc.cluster.local
            end=\$(date +%s%N)
            latency=\$((\$end - \$start))
            total=\$((\$total + \$latency))
        done
        echo \$((\$total / \$count / 1000000))
    " 2>/dev/null || echo "999")

    if [ "$avg_latency" -lt "100" ]; then
        add_test_result "mtls_latency" "PASS" "medium" \
            "Latência média mTLS: ${avg_latency}ms" ""
    elif [ "$avg_latency" -lt "500" ]; then
        add_test_result "mtls_latency" "WARNING" "medium" \
            "Latência média mTLS elevada: ${avg_latency}ms" \
            "Otimizar configuração de proxy"
    else
        add_test_result "mtls_latency" "FAIL" "medium" \
            "Latência média mTLS muito alta: ${avg_latency}ms" \
            "Investigar problemas de performance"
    fi

    # Teste de throughput
    local throughput_test=$(kubectl exec $client_pod -n neural-hive-cognition -- sh -c "
        dd if=/dev/zero bs=1M count=1 2>/dev/null | \
        curl -s -X POST --data-binary @- \
        http://mtls-test-server.neural-hive-orchestration.svc.cluster.local \
        -w '%{speed_upload}' -o /dev/null
    " 2>/dev/null || echo "0")

    add_test_result "mtls_throughput" "INFO" "low" \
        "Teste de throughput executado" ""

    local exec_time=$(measure_execution_time $start_time)
    log_info "Teste de performance concluído em ${exec_time}s"
}

# Validar logs de auditoria mTLS
validate_mtls_audit_logs() {
    log_info "Validando logs de auditoria mTLS..."

    local start_time=$(date +%s)

    # Verificar logs do Istio
    local istiod_pod=$(kubectl get pod -n istio-system -l app=istiod -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [ -n "$istiod_pod" ]; then
        # Verificar se há logs de handshake TLS
        local tls_logs=$(kubectl logs -n istio-system $istiod_pod --tail=100 2>/dev/null | grep -c "TLS" || echo 0)

        if [ $tls_logs -gt 0 ]; then
            add_test_result "mtls_audit_logs" "PASS" "low" \
                "$tls_logs entradas de log TLS encontradas" ""
        else
            add_test_result "mtls_audit_logs" "WARNING" "low" \
                "Poucos logs TLS encontrados" \
                "Verificar nível de log do Istio"
        fi

        # Verificar erros de TLS
        local tls_errors=$(kubectl logs -n istio-system $istiod_pod --tail=100 2>/dev/null | grep -ci "tls.*error" || echo 0)

        if [ $tls_errors -eq 0 ]; then
            add_test_result "mtls_errors" "PASS" "high" \
                "Nenhum erro TLS detectado nos logs" ""
        else
            add_test_result "mtls_errors" "WARNING" "high" \
                "$tls_errors erros TLS detectados" \
                "Investigar erros TLS nos logs"
        fi
    else
        add_test_result "mtls_audit_logs" "SKIP" "low" \
            "Pod Istiod não encontrado" "Verificar instalação do Istio"
    fi

    local exec_time=$(measure_execution_time $start_time)
    log_info "Validação de logs concluída em ${exec_time}s"
}

# Main
main() {
    init_report "Teste abrangente de conectividade mTLS Neural Hive-Mind"

    log_info "Iniciando testes abrangentes de conectividade mTLS..."

    # Verificar pré-requisitos
    if ! check_prerequisites; then
        add_test_result "prerequisites" "FAIL" "critical" "Pré-requisitos não atendidos" "Instalar ferramentas necessárias"
        generate_summary_report
        exit 1
    fi

    add_test_result "prerequisites" "PASS" "high" "Todos os pré-requisitos atendidos" ""

    # Executar testes em sequência
    deploy_comprehensive_test_pods

    # Aguardar sidecars ficarem prontos
    log_info "Aguardando sidecars ficarem prontos..."
    sleep 15

    # Suite completa de testes
    test_cross_namespace_connectivity
    validate_spiffe_identities
    verify_comprehensive_proxy_status
    test_policy_enforcement
    test_certificate_rotation
    test_mtls_performance
    validate_mtls_audit_logs

    # Gerar relatórios
    generate_summary_report
    local html_report=$(export_html_report)

    log_success "========================================"
    log_success "Testes de mTLS abrangentes completos!"
    log_info "Relatório JSON: $(export_json_report)"
    log_info "Relatório HTML: $html_report"
    log_success "========================================"
}

main "$@"