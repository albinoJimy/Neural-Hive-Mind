# Guia de Troubleshooting do Neural Hive-Mind

## Visão Geral

Este guia fornece procedimentos estruturados para diagnóstico e resolução de problemas no sistema Neural Hive-Mind.

## Metodologia de Troubleshooting

### Abordagem Sistemática

1. **Identificação do Problema**
   - Definir sintomas observados
   - Determinar impacto e severidade
   - Coletar informações iniciais

2. **Isolamento do Problema**
   - Identificar componentes afetados
   - Determinar escopo do problema
   - Verificar dependências

3. **Análise da Causa Raiz**
   - Examinar logs e métricas
   - Reproduzir o problema
   - Testar hipóteses

4. **Implementação da Solução**
   - Aplicar correção
   - Verificar resolução
   - Monitorar estabilidade

5. **Prevenção**
   - Documentar solução
   - Implementar melhorias
   - Atualizar monitoramento

## Problemas por Categoria

### 1. Problemas de Deployment

#### 1.1 Pods Não Inicializam

**Sintomas:**
- Pods ficam em estado `Pending`, `CrashLoopBackOff` ou `ImagePullBackOff`
- Aplicação não responde

**Diagnóstico:**
```bash
# Verificar status dos pods
kubectl get pods -n neural-hive-mind -o wide

# Examinar eventos do pod
kubectl describe pod <pod-name> -n neural-hive-mind

# Verificar logs
kubectl logs <pod-name> -n neural-hive-mind --previous

# Verificar recursos disponíveis
kubectl top nodes
kubectl describe nodes
```

**Soluções Comuns:**

1. **ImagePullBackOff**
   ```bash
   # Verificar se a imagem existe
   docker pull <image-name>

   # Verificar secrets de registry
   kubectl get secrets -n neural-hive-mind | grep docker

   # Recrear secret se necessário
   kubectl create secret docker-registry regcred \
     --docker-server=<registry-url> \
     --docker-username=<username> \
     --docker-password=<password>
   ```

2. **Recursos Insuficientes**
   ```bash
   # Verificar requisitos vs disponível
   kubectl describe nodes | grep -A5 "Allocated resources"

   # Ajustar requests/limits
   kubectl edit deployment <deployment-name> -n neural-hive-mind
   ```

3. **Problemas de Configuração**
   ```bash
   # Verificar ConfigMaps e Secrets
   kubectl get configmaps,secrets -n neural-hive-mind

   # Validar configurações
   kubectl describe configmap <configmap-name> -n neural-hive-mind
   ```

#### 1.2 Deploy Falha

**Sintomas:**
- Script de deploy retorna erro
- Componentes não são criados
- Timeout durante deploy

**Diagnóstico:**
```bash
# Executar deploy com debug
./scripts/deploy/deploy-foundation.sh --debug

# Verificar logs do deploy
tail -f /tmp/neural-hive-mind-deploy-*.log

# Verificar status dos recursos
kubectl get all -n neural-hive-mind
```

**Soluções:**

1. **Dependências Não Satisfeitas**
   ```bash
   # Verificar pré-requisitos
   ./scripts/validation/validate-cluster-health.sh --prereq-only

   # Instalar dependências faltantes
   helm repo update
   kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.19/samples/addons/prometheus.yaml
   ```

2. **Problemas de Permissão**
   ```bash
   # Verificar RBAC
   kubectl auth can-i create deployments --namespace=neural-hive-mind

   # Verificar ServiceAccount
   kubectl get serviceaccounts -n neural-hive-mind
   ```

3. **Conflitos de Recursos**
   ```bash
   # Limpar recursos conflitantes
   kubectl delete deployment <conflicting-deployment> -n neural-hive-mind

   # Forçar recriação
   kubectl replace --force -f <resource-file>
   ```

### 2. Problemas de Conectividade

#### 2.1 Falhas de mTLS

**Sintomas:**
- Erros de TLS handshake
- Conexões rejeitadas entre serviços
- Certificados expirados

**Diagnóstico:**
```bash
# Executar teste de mTLS
./scripts/validation/test-mtls-connectivity.sh

# Verificar certificados
kubectl get certificates -n neural-hive-mind

# Verificar políticas Istio
kubectl get peerauthentication,authorizationpolicy -n neural-hive-mind
```

**Soluções:**

1. **Certificados Expirados**
   ```bash
   # Verificar expiração
   kubectl get certificates -n neural-hive-mind -o custom-columns=NAME:.metadata.name,READY:.status.conditions[0].status,EXPIRES:.status.notAfter

   # Forçar renovação
   kubectl annotate certificate <cert-name> cert-manager.io/force-renewal=true -n neural-hive-mind
   ```

2. **Configuração Istio Incorreta**
   ```bash
   # Verificar sidecar injection
   kubectl get namespace neural-hive-mind -o yaml | grep istio-injection

   # Habilitar injection se necessário
   kubectl label namespace neural-hive-mind istio-injection=enabled --overwrite

   # Restart pods para aplicar sidecar
   kubectl rollout restart deployment -n neural-hive-mind
   ```

3. **Políticas de Segurança Restritivas**
   ```bash
   # Verificar políticas
   kubectl get authorizationpolicy -n neural-hive-mind -o yaml

   # Temporariamente relaxar políticas para teste
   kubectl patch authorizationpolicy <policy-name> -n neural-hive-mind --type='merge' -p='{"spec":{"action":"ALLOW"}}'
   ```

#### 2.2 Problemas de Rede

**Sintomas:**
- Timeouts de conexão
- DNS resolution failures
- Pods não conseguem se comunicar

**Diagnóstico:**
```bash
# Teste de conectividade básica
kubectl exec -it <pod-name> -n neural-hive-mind -- ping google.com

# Teste de DNS
kubectl exec -it <pod-name> -n neural-hive-mind -- nslookup kubernetes.default

# Verificar políticas de rede
kubectl get networkpolicies -n neural-hive-mind
```

**Soluções:**

1. **Problemas de DNS**
   ```bash
   # Verificar CoreDNS
   kubectl get pods -n kube-system -l k8s-app=kube-dns

   # Verificar configuração DNS
   kubectl get configmap coredns -n kube-system -o yaml

   # Restart CoreDNS se necessário
   kubectl rollout restart deployment/coredns -n kube-system
   ```

2. **Network Policies Restritivas**
   ```bash
   # Listar políticas
   kubectl get networkpolicies -n neural-hive-mind

   # Temporariamente remover política para teste
   kubectl delete networkpolicy <policy-name> -n neural-hive-mind
   ```

3. **Problemas de CNI**
   ```bash
   # Verificar status do CNI
   kubectl get pods -n kube-system -l name=<cni-name>

   # Verificar logs do CNI
   kubectl logs -n kube-system -l name=<cni-name>
   ```

### 3. Problemas de Performance

#### 3.1 Alta Latência

**Sintomas:**
- Respostas lentas da aplicação
- Timeouts intermitentes
- Alta latência P95

**Diagnóstico:**
```bash
# Executar benchmark de performance
./scripts/validation/validate-performance-benchmarks.sh

# Verificar métricas de latência
kubectl top pods -n neural-hive-mind

# Analisar traces
# (Verificar Jaeger/Zipkin se configurado)
```

**Soluções:**

1. **Recursos Insuficientes**
   ```bash
   # Aumentar recursos do pod
   kubectl patch deployment <deployment-name> -n neural-hive-mind -p='{"spec":{"template":{"spec":{"containers":[{"name":"<container-name>","resources":{"requests":{"cpu":"500m","memory":"1Gi"},"limits":{"cpu":"1000m","memory":"2Gi"}}}]}}}}'

   # Verificar HPA
   kubectl get hpa -n neural-hive-mind
   ```

2. **Problemas de Rede**
   ```bash
   # Testar throughput de rede
   ./scripts/validation/validate-performance-benchmarks.sh --network-only

   # Verificar configurações de service mesh
   kubectl get destinationrule -n neural-hive-mind
   ```

3. **Configurações de Application**
   ```bash
   # Verificar configurações de timeout
   kubectl get configmap -n neural-hive-mind -o yaml | grep -i timeout

   # Ajustar configurações JVM (se aplicável)
   kubectl patch deployment <deployment-name> -n neural-hive-mind -p='{"spec":{"template":{"spec":{"containers":[{"name":"<container-name>","env":[{"name":"JAVA_OPTS","value":"-Xmx1g -XX:+UseG1GC"}]}]}}}}'
   ```

#### 3.2 Alto Uso de CPU/Memória

**Sintomas:**
- Pods sendo killed por OOMKiller
- CPU throttling
- Slow response times

**Diagnóstico:**
```bash
# Verificar uso atual
kubectl top pods -n neural-hive-mind --sort-by=cpu
kubectl top pods -n neural-hive-mind --sort-by=memory

# Verificar métricas históricas
kubectl describe pod <pod-name> -n neural-hive-mind | grep -A5 -B5 "Last State"

# Verificar eventos OOMKilled
kubectl get events -n neural-hive-mind | grep OOMKilled
```

**Soluções:**

1. **Memory Leaks**
   ```bash
   # Analisar heap dump (Java)
   kubectl exec -it <pod-name> -n neural-hive-mind -- jcmd <pid> GC.run_finalization

   # Verificar logs para vazamentos
   kubectl logs <pod-name> -n neural-hive-mind | grep -i "memory\|leak\|gc"
   ```

2. **Ajustar Limits**
   ```bash
   # Aumentar memory limits
   kubectl patch deployment <deployment-name> -n neural-hive-mind -p='{"spec":{"template":{"spec":{"containers":[{"name":"<container-name>","resources":{"limits":{"memory":"2Gi"}}}]}}}}'

   # Configurar CPU requests adequados
   kubectl patch deployment <deployment-name> -n neural-hive-mind -p='{"spec":{"template":{"spec":{"containers":[{"name":"<container-name>","resources":{"requests":{"cpu":"100m"},"limits":{"cpu":"500m"}}}]}}}}'
   ```

### 4. Problemas de Autoscaling

#### 4.1 HPA Não Funciona

**Sintomas:**
- Pods não escalam automaticamente
- HPA mostra métricas "unknown"
- Scaling manual funciona mas automático não

**Diagnóstico:**
```bash
# Verificar status do HPA
kubectl get hpa -n neural-hive-mind -o wide

# Verificar métricas disponíveis
kubectl top pods -n neural-hive-mind

# Verificar metrics server
kubectl get pods -n kube-system -l k8s-app=metrics-server
```

**Soluções:**

1. **Metrics Server Issues**
   ```bash
   # Verificar logs do metrics server
   kubectl logs -n kube-system -l k8s-app=metrics-server

   # Restart metrics server
   kubectl rollout restart deployment/metrics-server -n kube-system
   ```

2. **HPA Configuration Issues**
   ```bash
   # Verificar configuração do HPA
   kubectl describe hpa <hpa-name> -n neural-hive-mind

   # Recrear HPA se necessário
   kubectl delete hpa <hpa-name> -n neural-hive-mind
   kubectl autoscale deployment <deployment-name> --cpu-percent=50 --min=1 --max=10 -n neural-hive-mind
   ```

#### 4.2 Cluster Autoscaler Issues

**Sintomas:**
- Nós não são adicionados quando necessário
- Pods ficam em estado Pending
- Nós não são removidos quando não necessários

**Diagnóstico:**
```bash
# Verificar status do cluster autoscaler
kubectl get pods -n kube-system -l app=cluster-autoscaler

# Verificar eventos
kubectl get events -n kube-system | grep cluster-autoscaler

# Verificar configuração dos node groups
kubectl get nodes -o wide
```

**Soluções:**

1. **Configuração do Cloud Provider**
   ```bash
   # Verificar permissões IAM (AWS)
   aws iam get-role-policy --role-name <cluster-autoscaler-role> --policy-name <policy-name>

   # Verificar tags dos ASGs (AWS)
   aws autoscaling describe-auto-scaling-groups --query 'AutoScalingGroups[?contains(Tags[?Key==`k8s.io/cluster-autoscaler/enabled`].Value, `true`)]'
   ```

2. **Resource Requests**
   ```bash
   # Verificar se pods têm resource requests definidos
   kubectl get pods -n neural-hive-mind -o yaml | grep -A3 -B3 requests

   # Adicionar requests se necessário
   kubectl patch deployment <deployment-name> -n neural-hive-mind -p='{"spec":{"template":{"spec":{"containers":[{"name":"<container-name>","resources":{"requests":{"cpu":"100m","memory":"128Mi"}}}]}}}}'
   ```

### 5. Problemas de Armazenamento

#### 5.1 PVCs em Estado Pending

**Sintomas:**
- PersistentVolumeClaims não são satisfeitos
- Pods não conseguem montar volumes
- Aplicação não consegue acessar dados

**Diagnóstico:**
```bash
# Verificar status dos PVCs
kubectl get pvc -n neural-hive-mind

# Verificar eventos
kubectl describe pvc <pvc-name> -n neural-hive-mind

# Verificar storage classes
kubectl get storageclass
```

**Soluções:**

1. **Storage Class Issues**
   ```bash
   # Verificar se storage class existe
   kubectl get storageclass <storage-class-name>

   # Criar storage class se necessário
   kubectl apply -f - <<EOF
   apiVersion: storage.k8s.io/v1
   kind: StorageClass
   metadata:
     name: fast-ssd
   provisioner: kubernetes.io/aws-ebs
   parameters:
     type: gp3
   EOF
   ```

2. **Quota Issues**
   ```bash
   # Verificar quotas de armazenamento
   kubectl describe quota -n neural-hive-mind

   # Verificar disponibilidade no cloud provider
   aws ec2 describe-volumes --query 'Volumes[?State==`available`]' --region <region>
   ```

#### 5.2 Performance de I/O Baixa

**Sintomas:**
- Operações de disco lentas
- Alto wait time
- Aplicação responde lentamente

**Diagnóstico:**
```bash
# Executar benchmark de storage
./scripts/validation/validate-performance-benchmarks.sh --storage-only

# Verificar métricas de I/O
kubectl exec -it <pod-name> -n neural-hive-mind -- iostat -x 1 5
```

**Soluções:**

1. **Tipo de Volume**
   ```bash
   # Mudar para storage class mais rápida
   kubectl patch pvc <pvc-name> -n neural-hive-mind -p='{"spec":{"storageClassName":"fast-ssd"}}'
   ```

2. **Configurações de Aplicação**
   ```bash
   # Otimizar configurações de banco de dados
   kubectl patch configmap <db-config> -n neural-hive-mind -p='{"data":{"postgresql.conf":"shared_buffers = 256MB\neffective_cache_size = 1GB"}}'
   ```

## Scripts de Diagnóstico

### Script de Coleta Automática

```bash
#!/bin/bash
# collect-diagnostic-info.sh

NAMESPACE="neural-hive-mind"
OUTPUT_DIR="/tmp/neural-hive-mind-diagnostics-$(date +%Y%m%d_%H%M%S)"

mkdir -p "$OUTPUT_DIR"

# Informações básicas
kubectl cluster-info > "$OUTPUT_DIR/cluster-info.txt"
kubectl version > "$OUTPUT_DIR/version.txt"
kubectl get nodes -o wide > "$OUTPUT_DIR/nodes.txt"

# Status dos recursos
kubectl get all -n "$NAMESPACE" -o wide > "$OUTPUT_DIR/resources.txt"
kubectl get pv,pvc -A > "$OUTPUT_DIR/storage.txt"
kubectl get events -n "$NAMESPACE" > "$OUTPUT_DIR/events.txt"

# Logs
kubectl logs -l app=neural-hive-mind -n "$NAMESPACE" --tail=1000 > "$OUTPUT_DIR/app-logs.txt"

# Métricas
kubectl top nodes > "$OUTPUT_DIR/node-metrics.txt"
kubectl top pods -n "$NAMESPACE" > "$OUTPUT_DIR/pod-metrics.txt"

echo "Diagnósticos coletados em: $OUTPUT_DIR"
```

### Script de Verificação Rápida

```bash
#!/bin/bash
# quick-health-check.sh

echo "=== Quick Health Check ==="

# Verificar nós
echo "Nodes:"
kubectl get nodes | grep -v Ready && echo "❌ Nodes with issues found" || echo "✅ All nodes ready"

# Verificar pods críticos
echo -e "\nCritical Pods:"
CRITICAL_PODS=$(kubectl get pods -n neural-hive-mind --field-selector=status.phase!=Running --no-headers)
if [ -n "$CRITICAL_PODS" ]; then
    echo "❌ Critical pods not running:"
    echo "$CRITICAL_PODS"
else
    echo "✅ All critical pods running"
fi

# Verificar recursos
echo -e "\nResource Usage:"
HIGH_CPU=$(kubectl top nodes --no-headers | awk '$3 > 80 {print $1}')
if [ -n "$HIGH_CPU" ]; then
    echo "⚠️ High CPU usage on: $HIGH_CPU"
else
    echo "✅ CPU usage normal"
fi

HIGH_MEM=$(kubectl top nodes --no-headers | awk '$5 > 85 {print $1}')
if [ -n "$HIGH_MEM" ]; then
    echo "⚠️ High memory usage on: $HIGH_MEM"
else
    echo "✅ Memory usage normal"
fi
```

## Procedimentos de Emergência

### Sistema Completamente Indisponível

1. **Verificação Inicial**
   ```bash
   kubectl get nodes
   kubectl get pods -A | grep -v Running
   ```

2. **Restart de Emergência**
   ```bash
   # Restart todos os deployments
   kubectl rollout restart deployment -n neural-hive-mind

   # Verificar recuperação
   kubectl get pods -n neural-hive-mind -w
   ```

3. **Rollback de Emergência**
   ```bash
   # Rollback para versão anterior
   helm rollback neural-hive-mind

   # Verificar status
   helm status neural-hive-mind
   ```

### Perda de Dados

1. **Parar Todas as Operações**
   ```bash
   kubectl scale deployment --replicas=0 -n neural-hive-mind --all
   ```

2. **Restore do Backup**
   ```bash
   ./scripts/maintenance/backup-restore.sh restore --latest
   ```

3. **Validação do Restore**
   ```bash
   ./scripts/validation/test-disaster-recovery.sh --restore-validation
   ```

4. **Restart da Aplicação**
   ```bash
   kubectl scale deployment --replicas=3 -n neural-hive-mind --all
   ```

## Contatos de Escalação

### Escalação Técnica
1. **Nível 1**: Equipe de Operações
2. **Nível 2**: Equipe de Desenvolvimento
3. **Nível 3**: Arquitetos de Sistema
4. **Nível 4**: Fornecedores/Cloud Provider

### Informações de Contato
- **Plantão 24x7**: operations@neural-hive-mind.com
- **Chat de Emergência**: #incident-response
- **Phone Tree**: [Documento interno com telefones]