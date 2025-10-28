#!/bin/bash

# Script de Validação - Integração do Gateway de Intenções
# Valida a integração completa entre gateway, Kafka e Redis

set -euo pipefail

# Configurações
NAMESPACE="neural-hive-gateway"
GATEWAY_SERVICE="gateway-intencoes"
REDIS_NAMESPACE="redis-cluster"
KAFKA_NAMESPACE="neural-hive-kafka"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funções de logging
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Verificar dependências
check_dependencies() {
    log_info "Verificando dependências..."

    command -v kubectl >/dev/null 2>&1 || { log_error "kubectl não está instalado"; exit 1; }
    command -v curl >/dev/null 2>&1 || { log_error "curl não está instalado"; exit 1; }
    command -v jq >/dev/null 2>&1 || { log_error "jq não está instalado"; exit 1; }

    log_success "Todas as dependências estão disponíveis"
}

# Verificar se o namespace existe
check_namespace() {
    local namespace=$1
    log_info "Verificando namespace $namespace..."

    if kubectl get namespace "$namespace" >/dev/null 2>&1; then
        log_success "Namespace $namespace existe"
        return 0
    else
        log_error "Namespace $namespace não encontrado"
        return 1
    fi
}

# Verificar deployment do gateway
check_gateway_deployment() {
    log_info "Verificando deployment do Gateway de Intenções..."

    # Verificar se o deployment existe
    if ! kubectl get deployment "$GATEWAY_SERVICE" -n "$NAMESPACE" >/dev/null 2>&1; then
        log_error "Deployment $GATEWAY_SERVICE não encontrado no namespace $NAMESPACE"
        return 1
    fi

    # Verificar se as réplicas estão prontas
    local ready_replicas=$(kubectl get deployment "$GATEWAY_SERVICE" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}')
    local desired_replicas=$(kubectl get deployment "$GATEWAY_SERVICE" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}')

    if [[ "$ready_replicas" == "$desired_replicas" && "$ready_replicas" -gt 0 ]]; then
        log_success "Gateway deployment está saudável ($ready_replicas/$desired_replicas réplicas prontas)"
    else
        log_error "Gateway deployment não está saudável ($ready_replicas/$desired_replicas réplicas prontas)"
        return 1
    fi
}

# Verificar conectividade com Redis
check_redis_connectivity() {
    log_info "Verificando conectividade com Redis Cluster..."

    # Obter um pod do gateway para testar conexão
    local gateway_pod=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name="$GATEWAY_SERVICE" -o jsonpath='{.items[0].metadata.name}')

    if [[ -z "$gateway_pod" ]]; then
        log_error "Nenhum pod do gateway encontrado"
        return 1
    fi

    log_info "Testando conectividade Redis usando pod $gateway_pod..."

    # Testar conexão com Redis via health check
    local redis_test=$(kubectl exec -n "$NAMESPACE" "$gateway_pod" -- python3 -c "
import asyncio
import sys
sys.path.append('/app')
try:
    from src.cache.redis_client import get_redis_client
    async def test():
        client = await get_redis_client()
        health = await client.health_check()
        print(f'Status: {health[\"status\"]}')
        await client.close()
    asyncio.run(test())
except Exception as e:
    print(f'Erro: {e}')
    sys.exit(1)
" 2>/dev/null || echo "FAILED")

    if [[ "$redis_test" == *"Status: healthy"* ]]; then
        log_success "Conexão com Redis Cluster está funcionando"
    else
        log_error "Falha na conexão com Redis Cluster: $redis_test"
        return 1
    fi
}

# Verificar conectividade com Kafka
check_kafka_connectivity() {
    log_info "Verificando conectividade com Kafka..."

    # Obter um pod do gateway para testar conexão
    local gateway_pod=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name="$GATEWAY_SERVICE" -o jsonpath='{.items[0].metadata.name}')

    if [[ -z "$gateway_pod" ]]; then
        log_error "Nenhum pod do gateway encontrado"
        return 1
    fi

    log_info "Testando conectividade Kafka usando pod $gateway_pod..."

    # Verificar configurações de Kafka no pod
    local kafka_bootstrap=$(kubectl exec -n "$NAMESPACE" "$gateway_pod" -- env | grep KAFKA_BOOTSTRAP_SERVERS || echo "NOT_FOUND")

    if [[ "$kafka_bootstrap" == "NOT_FOUND" ]]; then
        log_error "Variável KAFKA_BOOTSTRAP_SERVERS não encontrada no pod"
        return 1
    fi

    log_info "Kafka Bootstrap Servers: $kafka_bootstrap"

    # Testar produção de mensagem de teste (se possível)
    local kafka_test=$(kubectl exec -n "$NAMESPACE" "$gateway_pod" -- python3 -c "
import asyncio
import sys
import os
sys.path.append('/app')
try:
    from src.messaging.kafka_producer import KafkaProducerManager
    async def test():
        producer = KafkaProducerManager()
        await producer.initialize()
        # Apenas testar a conexão, sem enviar mensagem real
        print('Kafka connection OK')
        await producer.close()
    asyncio.run(test())
except Exception as e:
    print(f'Erro: {e}')
    sys.exit(1)
" 2>/dev/null || echo "FAILED")

    if [[ "$kafka_test" == *"Kafka connection OK"* ]]; then
        log_success "Conexão com Kafka está funcionando"
    else
        log_warning "Não foi possível verificar conexão completa com Kafka: $kafka_test"
    fi
}

# Verificar endpoints do gateway
check_gateway_endpoints() {
    log_info "Verificando endpoints do Gateway de Intenções..."

    # Obter IP do serviço
    local service_ip=$(kubectl get service "$GATEWAY_SERVICE" -n "$NAMESPACE" -o jsonpath='{.spec.clusterIP}')
    local service_port=$(kubectl get service "$GATEWAY_SERVICE" -n "$NAMESPACE" -o jsonpath='{.spec.ports[0].port}')

    if [[ -z "$service_ip" || -z "$service_port" ]]; then
        log_error "Não foi possível obter IP ou porta do serviço"
        return 1
    fi

    log_info "Testando endpoint de saúde..."

    # Fazer port-forward temporário para testar
    kubectl port-forward -n "$NAMESPACE" "svc/$GATEWAY_SERVICE" 8080:$service_port >/dev/null 2>&1 &
    local pf_pid=$!

    # Aguardar port-forward ficar pronto
    sleep 3

    # Testar endpoint de health
    local health_response=$(curl -s -w "%{http_code}" http://localhost:8080/health -o /dev/null 2>/dev/null || echo "000")

    # Finalizar port-forward
    kill $pf_pid >/dev/null 2>&1 || true

    if [[ "$health_response" == "200" ]]; then
        log_success "Endpoint de saúde está respondendo (HTTP 200)"
    else
        log_error "Endpoint de saúde não está respondendo adequadamente (HTTP $health_response)"
        return 1
    fi
}

# Verificar métricas do Prometheus
check_prometheus_metrics() {
    log_info "Verificando métricas do Prometheus..."

    # Verificar se o ServiceMonitor existe
    if kubectl get servicemonitor "$GATEWAY_SERVICE" -n "$NAMESPACE" >/dev/null 2>&1; then
        log_success "ServiceMonitor está configurado"
    else
        log_warning "ServiceMonitor não encontrado - métricas podem não estar sendo coletadas"
    fi

    # Testar endpoint de métricas
    kubectl port-forward -n "$NAMESPACE" "svc/$GATEWAY_SERVICE" 8080:8000 >/dev/null 2>&1 &
    local pf_pid=$!

    sleep 3

    local metrics_response=$(curl -s http://localhost:8080/metrics | grep -c "neural_hive" || echo "0")

    kill $pf_pid >/dev/null 2>&1 || true

    if [[ "$metrics_response" -gt 0 ]]; then
        log_success "Métricas do Neural Hive estão sendo expostas ($metrics_response métricas encontradas)"
    else
        log_warning "Métricas do Neural Hive não foram encontradas"
    fi
}

# Verificar configurações de TLS/SSL
check_tls_configuration() {
    log_info "Verificando configurações TLS/SSL..."

    local gateway_pod=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name="$GATEWAY_SERVICE" -o jsonpath='{.items[0].metadata.name}')

    if [[ -z "$gateway_pod" ]]; then
        log_error "Nenhum pod do gateway encontrado"
        return 1
    fi

    # Verificar configurações SSL do Redis
    local redis_ssl=$(kubectl exec -n "$NAMESPACE" "$gateway_pod" -- env | grep REDIS_SSL_ENABLED || echo "NOT_SET")
    if [[ "$redis_ssl" == *"true"* ]]; then
        log_info "SSL do Redis está habilitado"

        # Verificar se certificados estão montados
        if kubectl exec -n "$NAMESPACE" "$gateway_pod" -- ls /etc/ssl/certs/redis-ca.crt >/dev/null 2>&1; then
            log_success "Certificado CA do Redis está montado"
        else
            log_warning "Certificado CA do Redis não encontrado"
        fi
    else
        log_info "SSL do Redis está desabilitado"
    fi

    # Verificar configurações SSL do Kafka
    local kafka_ssl=$(kubectl exec -n "$NAMESPACE" "$gateway_pod" -- env | grep KAFKA_SSL_ENABLED || echo "NOT_SET")
    if [[ "$kafka_ssl" == *"true"* ]]; then
        log_info "SSL do Kafka está habilitado"

        # Verificar se certificados estão montados
        if kubectl exec -n "$NAMESPACE" "$gateway_pod" -- ls /etc/ssl/certs/kafka-ca.crt >/dev/null 2>&1; then
            log_success "Certificado CA do Kafka está montado"
        else
            log_warning "Certificado CA do Kafka não encontrado"
        fi
    else
        log_info "SSL do Kafka está desabilitado"
    fi
}

# Verificar logs do gateway
check_gateway_logs() {
    log_info "Verificando logs do Gateway de Intenções..."

    local gateway_pod=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name="$GATEWAY_SERVICE" -o jsonpath='{.items[0].metadata.name}')

    if [[ -z "$gateway_pod" ]]; then
        log_error "Nenhum pod do gateway encontrado"
        return 1
    fi

    log_info "Analisando logs do pod $gateway_pod..."

    # Verificar se há erros críticos nos logs
    local error_count=$(kubectl logs -n "$NAMESPACE" "$gateway_pod" --tail=100 | grep -i "error\|exception\|failed" | wc -l || echo "0")
    local warning_count=$(kubectl logs -n "$NAMESPACE" "$gateway_pod" --tail=100 | grep -i "warning" | wc -l || echo "0")

    if [[ "$error_count" -gt 5 ]]; then
        log_warning "Muitos erros encontrados nos logs ($error_count erros nas últimas 100 linhas)"
    elif [[ "$error_count" -gt 0 ]]; then
        log_info "Alguns erros encontrados nos logs ($error_count erros nas últimas 100 linhas)"
    else
        log_success "Nenhum erro crítico encontrado nos logs"
    fi

    if [[ "$warning_count" -gt 10 ]]; then
        log_warning "Muitos warnings encontrados nos logs ($warning_count warnings nas últimas 100 linhas)"
    else
        log_info "Nível normal de warnings nos logs ($warning_count warnings)"
    fi
}

# Função principal
main() {
    echo "=================================================="
    echo "     Validação de Integração - Gateway de Intenções"
    echo "=================================================="
    echo

    local failed_checks=0

    # Executar verificações
    check_dependencies || ((failed_checks++))
    echo

    check_namespace "$NAMESPACE" || ((failed_checks++))
    check_namespace "$REDIS_NAMESPACE" || ((failed_checks++))
    check_namespace "$KAFKA_NAMESPACE" || ((failed_checks++))
    echo

    check_gateway_deployment || ((failed_checks++))
    echo

    check_redis_connectivity || ((failed_checks++))
    echo

    check_kafka_connectivity || ((failed_checks++))
    echo

    check_gateway_endpoints || ((failed_checks++))
    echo

    check_prometheus_metrics || ((failed_checks++))
    echo

    check_tls_configuration || ((failed_checks++))
    echo

    check_gateway_logs || ((failed_checks++))
    echo

    # Relatório final
    echo "=================================================="
    echo "             RELATÓRIO FINAL"
    echo "=================================================="

    if [[ $failed_checks -eq 0 ]]; then
        log_success "✅ Todas as verificações passaram com sucesso!"
        log_success "Gateway de Intenções está funcionando corretamente"
        exit 0
    else
        log_error "❌ $failed_checks verificação(ões) falharam"
        log_error "Por favor, revise os problemas identificados acima"
        exit 1
    fi
}

# Executar apenas se chamado diretamente
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi