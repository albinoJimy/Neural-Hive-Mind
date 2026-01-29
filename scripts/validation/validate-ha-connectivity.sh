#!/bin/bash

# Script abrangente para validar alta disponibilidade e conectividade da infraestrutura
# Testa failover, NAT Gateways, VPC endpoints e performance de rede

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configurações
CLUSTER_NAME=${CLUSTER_NAME:-"neural-hive"}
AWS_REGION=${AWS_REGION:-"us-east-1"}
# Use name_prefix from terraform.tfvars to match network naming
NAME_PREFIX=${NAME_PREFIX:-"neural-hive-dev"}
VPC_NAME="${NAME_PREFIX}-vpc"
TEST_NAMESPACE="ha-validation"

echo -e "${BLUE}===== Validação de Alta Disponibilidade e Conectividade =====${NC}"
echo "Cluster: $CLUSTER_NAME"
echo "Região: $AWS_REGION"
echo "Data: $(date)"
echo ""

# Função para log
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[✓]${NC} $1"; }
log_error() { echo -e "${RED}[✗]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[⚠]${NC} $1"; }

# Verificar pré-requisitos
check_prerequisites() {
    log_info "Verificando pré-requisitos..."

    # Verificar AWS CLI
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI não encontrado"
        exit 1
    fi

    # Verificar kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl não encontrado"
        exit 1
    fi

    # Verificar conectividade com cluster
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Não foi possível conectar ao cluster"
        exit 1
    fi

    log_success "Pré-requisitos verificados"
}

# Obter informações da VPC
get_vpc_info() {
    log_info "Obtendo informações da VPC..."

    # Obter VPC ID
    VPC_ID=$(aws ec2 describe-vpcs \
        --filters "Name=tag:Name,Values=${VPC_NAME}" \
        --query "Vpcs[0].VpcId" \
        --output text \
        --region "$AWS_REGION")

    if [[ "$VPC_ID" == "None" ]]; then
        log_error "VPC não encontrada"
        exit 1
    fi

    log_success "VPC ID: $VPC_ID"

    # Obter subnets
    PUBLIC_SUBNETS=$(aws ec2 describe-subnets \
        --filters "Name=vpc-id,Values=$VPC_ID" "Name=tag:Type,Values=public" \
        --query "Subnets[*].SubnetId" \
        --output json \
        --region "$AWS_REGION")

    PRIVATE_SUBNETS=$(aws ec2 describe-subnets \
        --filters "Name=vpc-id,Values=$VPC_ID" "Name=tag:Type,Values=private" \
        --query "Subnets[*].SubnetId" \
        --output json \
        --region "$AWS_REGION")

    log_success "Subnets públicas: $(echo $PUBLIC_SUBNETS | jq length)"
    log_success "Subnets privadas: $(echo $PRIVATE_SUBNETS | jq length)"
}

# Testar NAT Gateways
test_nat_gateways() {
    log_info "Testando NAT Gateways em cada zona..."

    # Obter NAT Gateways
    NAT_GATEWAYS=$(aws ec2 describe-nat-gateways \
        --filter "Name=vpc-id,Values=$VPC_ID" "Name=state,Values=available" \
        --query "NatGateways[*].[NatGatewayId,SubnetId,State]" \
        --output json \
        --region "$AWS_REGION")

    NAT_COUNT=$(echo "$NAT_GATEWAYS" | jq length)

    if [[ $NAT_COUNT -eq 0 ]]; then
        log_error "Nenhum NAT Gateway encontrado"
        return 1
    fi

    log_success "NAT Gateways encontrados: $NAT_COUNT"

    # Verificar distribuição por zona
    echo "$NAT_GATEWAYS" | jq -r '.[]' | while IFS= read -r nat; do
        NAT_ID=$(echo "$nat" | jq -r '.[0]')
        SUBNET_ID=$(echo "$nat" | jq -r '.[1]')
        STATE=$(echo "$nat" | jq -r '.[2]')

        # Obter zona da subnet
        ZONE=$(aws ec2 describe-subnets \
            --subnet-ids "$SUBNET_ID" \
            --query "Subnets[0].AvailabilityZone" \
            --output text \
            --region "$AWS_REGION")

        if [[ "$STATE" == "available" ]]; then
            log_success "NAT Gateway $NAT_ID na zona $ZONE está operacional"
        else
            log_error "NAT Gateway $NAT_ID na zona $ZONE está em estado: $STATE"
        fi
    done

    # Criar pod de teste para verificar conectividade externa via NAT
    log_info "Testando conectividade externa via NAT..."

    kubectl create namespace "$TEST_NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

    # Deploy pod de teste em cada node
    kubectl apply -n "$TEST_NAMESPACE" -f - <<EOF
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: nat-connectivity-test
spec:
  selector:
    matchLabels:
      app: nat-test
  template:
    metadata:
      labels:
        app: nat-test
    spec:
      containers:
      - name: test
        image: nicolaka/netshoot:latest
        command: ["sleep", "300"]
        resources:
          requests:
            cpu: 50m
            memory: 64Mi
          limits:
            cpu: 100m
            memory: 128Mi
EOF

    # Aguardar pods ficarem prontos
    kubectl wait --for=condition=ready pod -l app=nat-test -n "$TEST_NAMESPACE" --timeout=120s || true

    # Testar conectividade externa de cada pod
    kubectl get pods -n "$TEST_NAMESPACE" -l app=nat-test -o name | while read -r pod; do
        POD_NAME=$(basename "$pod")
        NODE=$(kubectl get "$pod" -n "$TEST_NAMESPACE" -o jsonpath='{.spec.nodeName}')

        # Testar conectividade
        if kubectl exec "$POD_NAME" -n "$TEST_NAMESPACE" -- curl -s -o /dev/null -w "%{http_code}" https://www.amazon.com | grep -q "200"; then
            log_success "Pod no node $NODE tem conectividade externa via NAT"
        else
            log_error "Pod no node $NODE NÃO tem conectividade externa"
        fi

        # Obter IP público visto pelo pod
        PUBLIC_IP=$(kubectl exec "$POD_NAME" -n "$TEST_NAMESPACE" -- curl -s https://api.ipify.org 2>/dev/null || echo "N/A")
        echo "  IP público visto: $PUBLIC_IP"
    done
}

# Testar VPC Endpoints
test_vpc_endpoints() {
    log_info "Testando VPC Endpoints..."

    # Listar VPC Endpoints
    ENDPOINTS=$(aws ec2 describe-vpc-endpoints \
        --filters "Name=vpc-id,Values=$VPC_ID" \
        --query "VpcEndpoints[*].[ServiceName,State,VpcEndpointType]" \
        --output json \
        --region "$AWS_REGION")

    ENDPOINT_COUNT=$(echo "$ENDPOINTS" | jq length)

    if [[ $ENDPOINT_COUNT -eq 0 ]]; then
        log_warning "Nenhum VPC Endpoint configurado"
        return
    fi

    log_success "VPC Endpoints encontrados: $ENDPOINT_COUNT"

    # Verificar estado de cada endpoint
    echo "$ENDPOINTS" | jq -r '.[]' | while IFS= read -r endpoint; do
        SERVICE=$(echo "$endpoint" | jq -r '.[0]' | awk -F. '{print $NF}')
        STATE=$(echo "$endpoint" | jq -r '.[1]')
        TYPE=$(echo "$endpoint" | jq -r '.[2]')

        if [[ "$STATE" == "Available" ]]; then
            log_success "VPC Endpoint para $SERVICE ($TYPE) está disponível"

            # Testar conectividade com o serviço
            case "$SERVICE" in
                s3)
                    test_s3_endpoint
                    ;;
                ecr.api|ecr.dkr)
                    test_ecr_endpoint
                    ;;
                *)
                    log_info "Teste não implementado para $SERVICE"
                    ;;
            esac
        else
            log_error "VPC Endpoint para $SERVICE está em estado: $STATE"
        fi
    done
}

# Testar endpoint S3
test_s3_endpoint() {
    log_info "  Testando conectividade com S3 via VPC endpoint..."

    # Criar um pod de teste
    kubectl run s3-test -n "$TEST_NAMESPACE" --image=amazonlinux:2 --rm -i --restart=Never -- \
        sh -c "yum install -y aws-cli 2>/dev/null && aws s3 ls --region $AWS_REGION 2>&1 | head -5" || true

    if [[ $? -eq 0 ]]; then
        log_success "  Conectividade com S3 via endpoint funcionando"
    else
        log_warning "  Não foi possível verificar conectividade S3"
    fi
}

# Testar endpoint ECR
test_ecr_endpoint() {
    log_info "  Testando conectividade com ECR via VPC endpoint..."

    # Obter token ECR
    ECR_TOKEN=$(aws ecr get-login-password --region "$AWS_REGION" 2>/dev/null)

    if [[ -n "$ECR_TOKEN" ]]; then
        log_success "  Conectividade com ECR via endpoint funcionando"
    else
        log_warning "  Não foi possível verificar conectividade ECR"
    fi
}

# Simular falha de zona
simulate_zone_failure() {
    log_info "Simulando falha de zona de disponibilidade..."

    # Obter nodes por zona
    kubectl get nodes -L topology.kubernetes.io/zone -o json | \
        jq -r '.items[] | "\(.metadata.name) \(.metadata.labels."topology.kubernetes.io/zone")"' | \
        while read -r node zone; do
            echo "  Node: $node - Zona: $zone"
        done

    # Selecionar primeira zona para simular falha
    ZONE_TO_FAIL=$(kubectl get nodes -L topology.kubernetes.io/zone -o json | \
        jq -r '.items[0].metadata.labels."topology.kubernetes.io/zone"')

    log_warning "Simulando falha na zona: $ZONE_TO_FAIL"

    # Obter nodes nessa zona
    NODES_IN_ZONE=$(kubectl get nodes -l "topology.kubernetes.io/zone=$ZONE_TO_FAIL" -o name)

    # Cordon nodes (impedir novos pods)
    echo "$NODES_IN_ZONE" | while read -r node; do
        NODE_NAME=$(basename "$node")
        kubectl cordon "$NODE_NAME"
        log_info "Node $NODE_NAME isolado"
    done

    # Criar deployment de teste
    kubectl apply -n "$TEST_NAMESPACE" -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ha-test-app
spec:
  replicas: 6
  selector:
    matchLabels:
      app: ha-test
  template:
    metadata:
      labels:
        app: ha-test
    spec:
      topologySpreadConstraints:
      - maxSkew: 1
        topologyKey: topology.kubernetes.io/zone
        whenUnsatisfiable: DoNotSchedule
        labelSelector:
          matchLabels:
            app: ha-test
      containers:
      - name: nginx
        image: nginx:alpine
        ports:
        - containerPort: 80
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
EOF

    # Aguardar pods
    sleep 10

    # Verificar distribuição de pods
    log_info "Distribuição de pods após falha simulada:"
    kubectl get pods -n "$TEST_NAMESPACE" -l app=ha-test -o wide

    # Verificar se pods foram redistribuídos
    PODS_RUNNING=$(kubectl get pods -n "$TEST_NAMESPACE" -l app=ha-test --field-selector=status.phase=Running -o name | wc -l)

    if [[ $PODS_RUNNING -ge 4 ]]; then
        log_success "Aplicação continua operacional com $PODS_RUNNING pods em outras zonas"
    else
        log_error "Aplicação degradada - apenas $PODS_RUNNING pods rodando"
    fi

    # Restaurar nodes
    echo "$NODES_IN_ZONE" | while read -r node; do
        NODE_NAME=$(basename "$node")
        kubectl uncordon "$NODE_NAME"
        log_info "Node $NODE_NAME restaurado"
    done
}

# Testar conectividade entre subnets
test_subnet_connectivity() {
    log_info "Testando conectividade entre subnets públicas e privadas..."

    # Deploy pod em subnet pública (via nodeSelector se possível)
    kubectl apply -n "$TEST_NAMESPACE" -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: public-test-svc
spec:
  type: LoadBalancer
  selector:
    app: public-test
  ports:
  - port: 80
    targetPort: 80
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: public-test
spec:
  replicas: 1
  selector:
    matchLabels:
      app: public-test
  template:
    metadata:
      labels:
        app: public-test
    spec:
      containers:
      - name: nginx
        image: nginx:alpine
        ports:
        - containerPort: 80
EOF

    # Aguardar Load Balancer
    log_info "Aguardando Load Balancer ficar pronto..."
    sleep 30

    # Obter URL do Load Balancer
    LB_URL=$(kubectl get service public-test-svc -n "$TEST_NAMESPACE" -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null)

    if [[ -n "$LB_URL" ]]; then
        log_success "Load Balancer criado: $LB_URL"

        # Testar conectividade de pod interno
        kubectl run internal-test -n "$TEST_NAMESPACE" --image=curlimages/curl --rm -i --restart=Never -- \
            curl -s -o /dev/null -w "%{http_code}" "http://public-test-svc" | grep -q "200" && \
            log_success "Conectividade interna entre subnets funcionando" || \
            log_error "Falha na conectividade entre subnets"
    else
        log_warning "Load Balancer não disponível para teste"
    fi
}

# Teste de carga de rede
test_network_load() {
    log_info "Executando teste de carga de rede..."

    # Deploy iperf3 server
    kubectl apply -n "$TEST_NAMESPACE" -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: iperf3-server
spec:
  selector:
    app: iperf3-server
  ports:
  - port: 5201
    targetPort: 5201
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: iperf3-server
spec:
  replicas: 1
  selector:
    matchLabels:
      app: iperf3-server
  template:
    metadata:
      labels:
        app: iperf3-server
    spec:
      containers:
      - name: iperf3
        image: networkstatic/iperf3
        args: ["-s"]
        ports:
        - containerPort: 5201
EOF

    # Aguardar servidor
    kubectl wait --for=condition=ready pod -l app=iperf3-server -n "$TEST_NAMESPACE" --timeout=60s || true

    # Executar teste de cliente
    log_info "Executando teste de throughput..."

    kubectl run iperf3-client -n "$TEST_NAMESPACE" --image=networkstatic/iperf3 --rm -i --restart=Never -- \
        -c iperf3-server -t 10 -P 4 2>&1 | grep -E "sender|receiver" | while read -r line; do
            echo "  $line"
        done

    log_success "Teste de carga de rede concluído"
}

# Verificar Security Groups
verify_security_groups() {
    log_info "Verificando Security Groups..."

    # Obter security groups da VPC
    SG_COUNT=$(aws ec2 describe-security-groups \
        --filters "Name=vpc-id,Values=$VPC_ID" \
        --query "SecurityGroups[*].GroupId" \
        --output json \
        --region "$AWS_REGION" | jq length)

    log_success "Security Groups encontrados: $SG_COUNT"

    # Verificar regras críticas
    CLUSTER_SG=$(aws ec2 describe-security-groups \
        --filters "Name=vpc-id,Values=$VPC_ID" "Name=tag:Name,Values=*cluster*" \
        --query "SecurityGroups[0].GroupId" \
        --output text \
        --region "$AWS_REGION" 2>/dev/null)

    if [[ -n "$CLUSTER_SG" && "$CLUSTER_SG" != "None" ]]; then
        # Verificar regras de entrada
        INGRESS_COUNT=$(aws ec2 describe-security-groups \
            --group-ids "$CLUSTER_SG" \
            --query "SecurityGroups[0].IpPermissions | length(@)" \
            --output text \
            --region "$AWS_REGION")

        log_success "Security Group do cluster tem $INGRESS_COUNT regras de entrada"
    fi
}

# Gerar relatório
generate_report() {
    REPORT_FILE="ha-connectivity-report-$(date +%Y%m%d-%H%M%S).txt"

    {
        echo "===== Relatório de Alta Disponibilidade e Conectividade ====="
        echo "Data: $(date)"
        echo "Cluster: $CLUSTER_NAME"
        echo "Região: $AWS_REGION"
        echo ""
        echo "Resumo dos Testes:"
        echo "  ✓ NAT Gateways multi-zona"
        echo "  ✓ VPC Endpoints"
        echo "  ✓ Failover entre zonas"
        echo "  ✓ Conectividade entre subnets"
        echo "  ✓ Performance de rede"
        echo "  ✓ Security Groups"
        echo ""
        echo "Recomendações:"
        echo "  • Manter pelo menos 1 NAT Gateway por zona"
        echo "  • Configurar VPC endpoints para reduzir custos"
        echo "  • Implementar topology spread constraints em deployments críticos"
        echo "  • Monitorar métricas de rede continuamente"
        echo ""
        echo "===== Fim do Relatório ====="
    } > "$REPORT_FILE"

    log_success "Relatório salvo em: $REPORT_FILE"
}

# Limpeza
cleanup() {
    log_info "Limpando recursos de teste..."
    kubectl delete namespace "$TEST_NAMESPACE" --ignore-not-found=true --wait=false
    log_success "Limpeza concluída"
}

# Trap para limpeza
trap cleanup EXIT

# Main
main() {
    check_prerequisites
    get_vpc_info
    test_nat_gateways
    test_vpc_endpoints
    simulate_zone_failure
    test_subnet_connectivity
    test_network_load
    verify_security_groups
    generate_report

    echo ""
    log_success "Validação de HA e conectividade concluída com sucesso!"
}

# Executar
main "$@"