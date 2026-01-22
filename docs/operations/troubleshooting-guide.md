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

### 6. Problemas de Integração (Kafka, ClickHouse, OTEL)

#### 6.1 Tópicos Kafka Inacessíveis

**Sintomas:**
- Mensagens não estão sendo produzidas/consumidas
- Consumer lag crescente
- Erros de serialização/deserialização
- Timeouts de conexão ao broker

**Diagnóstico:**
```bash
# Validação completa dos tópicos Kafka
./scripts/validation/validate-kafka-topics.sh

# Verificar conectividade com broker
kubectl exec -it kafka-0 -n neural-hive-kafka -- kafka-broker-api-versions.sh --bootstrap-server localhost:9092

# Listar tópicos existentes
kubectl exec -it kafka-0 -n neural-hive-kafka -- kafka-topics.sh --bootstrap-server localhost:9092 --list

# Verificar consumer lag
kubectl exec -it kafka-0 -n neural-hive-kafka -- kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --all-groups

# Verificar configuração do tópico
kubectl exec -it kafka-0 -n neural-hive-kafka -- kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic intentions.security
```

**Soluções:**

1. **Tópicos Não Existem**
   ```bash
   # Criar tópicos via Helm chart
   helm upgrade kafka-topics ./helm-charts/kafka-topics -n neural-hive-kafka

   # Ou criar manualmente
   kubectl exec -it kafka-0 -n neural-hive-kafka -- kafka-topics.sh \
     --bootstrap-server localhost:9092 \
     --create --topic intentions.security \
     --partitions 3 --replication-factor 2
   ```

2. **Nomenclatura Incorreta (hífen vs ponto)**
   ```bash
   # Verificar se existem tópicos com nomenclatura errada
   kubectl exec -it kafka-0 -n neural-hive-kafka -- kafka-topics.sh \
     --bootstrap-server localhost:9092 --list | grep "intentions-"

   # Se encontrar tópicos com hífen, deletar e recriar com ponto
   kubectl exec -it kafka-0 -n neural-hive-kafka -- kafka-topics.sh \
     --bootstrap-server localhost:9092 --delete --topic intentions-security

   kubectl exec -it kafka-0 -n neural-hive-kafka -- kafka-topics.sh \
     --bootstrap-server localhost:9092 --create --topic intentions.security \
     --partitions 3 --replication-factor 2
   ```

3. **Consumer Lag Crítico**
   ```bash
   # Identificar consumer group com lag
   kubectl exec -it kafka-0 -n neural-hive-kafka -- kafka-consumer-groups.sh \
     --bootstrap-server localhost:9092 --describe --group neural-hive-consumers

   # Scale up do serviço consumidor
   kubectl scale deployment orchestrator-dynamic -n neural-hive-mind --replicas=5

   # Reset offset se necessário (cuidado!)
   kubectl exec -it kafka-0 -n neural-hive-kafka -- kafka-consumer-groups.sh \
     --bootstrap-server localhost:9092 --group neural-hive-consumers \
     --reset-offsets --to-latest --topic intentions.security --execute
   ```

4. **Problemas de Schema Registry**
   ```bash
   # Verificar status do Schema Registry
   kubectl get pods -n neural-hive-kafka -l app=schema-registry

   # Verificar conectividade
   kubectl exec -it <pod-name> -n neural-hive-mind -- curl -s http://schema-registry:8081/subjects

   # Restart se necessário
   kubectl rollout restart deployment/schema-registry -n neural-hive-kafka
   ```

#### 6.2 ClickHouse Sem Schema

**Sintomas:**
- Queries falham com "Table not found"
- Dashboard de ML não exibe dados
- Pipelines de treinamento falham
- Alertas de schema incompleto no Prometheus

**Diagnóstico:**
```bash
# Verificar conexão com ClickHouse
kubectl exec -it clickhouse-0 -n clickhouse -- clickhouse-client --query "SELECT 1"

# Verificar se database existe
kubectl exec -it clickhouse-0 -n clickhouse -- clickhouse-client --query "SHOW DATABASES" | grep neural_hive

# Listar tabelas existentes
kubectl exec -it clickhouse-0 -n clickhouse -- clickhouse-client --query "SHOW TABLES FROM neural_hive"

# Contar tabelas (esperado: 6)
kubectl exec -it clickhouse-0 -n clickhouse -- clickhouse-client --query "SELECT count() FROM system.tables WHERE database = 'neural_hive' AND engine NOT LIKE '%View%'"

# Verificar views materializadas (esperado: 2)
kubectl exec -it clickhouse-0 -n clickhouse -- clickhouse-client --query "SELECT count() FROM system.tables WHERE database = 'neural_hive' AND engine LIKE '%View%'"
```

**Soluções:**

1. **Database Não Existe**
   ```bash
   # Criar database
   kubectl exec -it clickhouse-0 -n clickhouse -- clickhouse-client --query "CREATE DATABASE IF NOT EXISTS neural_hive"

   # Aplicar schema completo
   kubectl apply -f k8s/clickhouse-ml-schema.yaml
   ```

2. **Tabelas Faltando**
   ```bash
   # Verificar quais tabelas estão faltando
   kubectl exec -it clickhouse-0 -n clickhouse -- clickhouse-client --query "
     SELECT 'execution_logs' WHERE NOT EXISTS (SELECT 1 FROM system.tables WHERE database = 'neural_hive' AND name = 'execution_logs')
     UNION ALL
     SELECT 'telemetry_metrics' WHERE NOT EXISTS (SELECT 1 FROM system.tables WHERE database = 'neural_hive' AND name = 'telemetry_metrics')
     UNION ALL
     SELECT 'worker_utilization' WHERE NOT EXISTS (SELECT 1 FROM system.tables WHERE database = 'neural_hive' AND name = 'worker_utilization')
     UNION ALL
     SELECT 'queue_snapshots' WHERE NOT EXISTS (SELECT 1 FROM system.tables WHERE database = 'neural_hive' AND name = 'queue_snapshots')
     UNION ALL
     SELECT 'ml_model_performance' WHERE NOT EXISTS (SELECT 1 FROM system.tables WHERE database = 'neural_hive' AND name = 'ml_model_performance')
     UNION ALL
     SELECT 'scheduling_decisions' WHERE NOT EXISTS (SELECT 1 FROM system.tables WHERE database = 'neural_hive' AND name = 'scheduling_decisions')
   "

   # Recriar schema
   kubectl delete -f k8s/clickhouse-ml-schema.yaml
   kubectl apply -f k8s/clickhouse-ml-schema.yaml
   ```

3. **Views Materializadas Ausentes**
   ```bash
   # Verificar views
   kubectl exec -it clickhouse-0 -n clickhouse -- clickhouse-client --query "
     SELECT name FROM system.tables
     WHERE database = 'neural_hive'
     AND engine LIKE '%View%'
   "

   # Recriar views (exemplo)
   kubectl exec -it clickhouse-0 -n clickhouse -- clickhouse-client --query "
     CREATE MATERIALIZED VIEW IF NOT EXISTS neural_hive.hourly_ticket_volume
     ENGINE = SummingMergeTree()
     ORDER BY (hour)
     AS SELECT
       toStartOfHour(timestamp) AS hour,
       count() AS volume
     FROM neural_hive.execution_logs
     GROUP BY hour
   "
   ```

4. **Problemas de Conectividade**
   ```bash
   # Verificar pod do ClickHouse
   kubectl get pods -n clickhouse -l app=clickhouse

   # Verificar service
   kubectl get svc -n clickhouse

   # Testar conectividade de outro pod
   kubectl exec -it <app-pod> -n neural-hive-mind -- nc -zv clickhouse.clickhouse.svc.cluster.local 9000

   # Restart se necessário
   kubectl rollout restart statefulset/clickhouse -n clickhouse
   ```

#### 6.3 Pipeline OTEL/Jaeger Sem Traces

**Sintomas:**
- Jaeger UI não mostra serviços
- Traces não aparecem
- Métricas de spans rejeitados aumentando
- Health checks de OTEL falham

**Diagnóstico:**
```bash
# Verificar status do OTEL Collector
kubectl get pods -n observability -l app=opentelemetry-collector

# Verificar logs do OTEL Collector
kubectl logs -n observability -l app=opentelemetry-collector --tail=100

# Verificar métricas do collector
kubectl exec -it <otel-pod> -n observability -- curl -s localhost:8888/metrics | grep otelcol_receiver

# Verificar Jaeger
kubectl get pods -n observability -l app=jaeger

# Testar endpoint de traces
kubectl exec -it <app-pod> -n neural-hive-mind -- curl -s http://opentelemetry-collector.observability:4318/v1/traces -X POST -H "Content-Type: application/json" -d '{}'
```

**Soluções:**

1. **OTEL Collector Down**
   ```bash
   # Verificar status
   kubectl describe pod -n observability -l app=opentelemetry-collector

   # Verificar configuração
   kubectl get configmap otel-collector-config -n observability -o yaml

   # Restart collector
   kubectl rollout restart deployment/otel-collector -n observability
   ```

2. **Serviços Não Enviam Traces**
   ```bash
   # Verificar variáveis de ambiente OTEL nos pods
   kubectl get deployment <deployment-name> -n neural-hive-mind -o yaml | grep -A2 OTEL

   # Verificar se OTEL está habilitado
   kubectl exec -it <app-pod> -n neural-hive-mind -- env | grep OTEL

   # Adicionar variáveis se faltando
   kubectl patch deployment <deployment-name> -n neural-hive-mind --type='json' -p='[
     {"op": "add", "path": "/spec/template/spec/containers/0/env/-", "value": {"name": "OTEL_ENABLED", "value": "true"}},
     {"op": "add", "path": "/spec/template/spec/containers/0/env/-", "value": {"name": "OTEL_EXPORTER_OTLP_ENDPOINT", "value": "http://opentelemetry-collector.observability:4317"}}
   ]'
   ```

3. **Jaeger Não Recebe Dados**
   ```bash
   # Verificar configuração do exporter no OTEL Collector
   kubectl get configmap otel-collector-config -n observability -o yaml | grep -A10 exporters

   # Verificar conectividade com Jaeger
   kubectl exec -it <otel-pod> -n observability -- nc -zv jaeger-collector.observability 14250

   # Restart Jaeger
   kubectl rollout restart deployment/jaeger-query -n observability
   kubectl rollout restart deployment/jaeger-collector -n observability
   ```

4. **Alta Taxa de Rejeição de Spans**
   ```bash
   # Verificar métricas de rejeição
   kubectl exec -it <otel-pod> -n observability -- curl -s localhost:8888/metrics | grep refused

   # Verificar logs de erro
   kubectl logs -n observability -l app=opentelemetry-collector | grep -i "refused\|error\|fail"

   # Aumentar batch size se necessário
   kubectl edit configmap otel-collector-config -n observability
   # Ajustar: batch/send_batch_size e batch/timeout

   # Restart para aplicar
   kubectl rollout restart deployment/otel-collector -n observability
   ```

#### 6.4 Scripts de Diagnóstico Automatizado

**Script de Validação Completa de Integração:**
```bash
#!/bin/bash
# validate-integration-health.sh

echo "=== Neural Hive-Mind Integration Health Check ==="
echo ""

# Kafka
echo "📨 Kafka Health:"
./scripts/validation/validate-kafka-topics.sh --quick 2>/dev/null
KAFKA_STATUS=$?

# ClickHouse
echo ""
echo "📊 ClickHouse Health:"
CH_TABLES=$(kubectl exec -it clickhouse-0 -n clickhouse -- clickhouse-client --query "SELECT count() FROM system.tables WHERE database = 'neural_hive' AND engine NOT LIKE '%View%'" 2>/dev/null | tr -d '[:space:]')
if [ "$CH_TABLES" -ge 6 ]; then
    echo "  ✅ Schema completo ($CH_TABLES tabelas)"
    CH_STATUS=0
else
    echo "  ❌ Schema incompleto ($CH_TABLES/6 tabelas)"
    CH_STATUS=1
fi

# OTEL/Jaeger
echo ""
echo "🔍 OTEL/Jaeger Health:"
OTEL_POD=$(kubectl get pods -n observability -l app=opentelemetry-collector -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$OTEL_POD" ]; then
    OTEL_RUNNING=$(kubectl get pod $OTEL_POD -n observability -o jsonpath='{.status.phase}' 2>/dev/null)
    if [ "$OTEL_RUNNING" = "Running" ]; then
        echo "  ✅ OTEL Collector running"
        OTEL_STATUS=0
    else
        echo "  ❌ OTEL Collector not running (status: $OTEL_RUNNING)"
        OTEL_STATUS=1
    fi
else
    echo "  ❌ OTEL Collector not found"
    OTEL_STATUS=1
fi

JAEGER_SERVICES=$(kubectl exec -it <jaeger-query-pod> -n observability -- curl -s localhost:16686/api/services 2>/dev/null | jq -r '.data | length' 2>/dev/null || echo "0")
if [ "$JAEGER_SERVICES" -gt 0 ]; then
    echo "  ✅ Jaeger receiving traces ($JAEGER_SERVICES services)"
else
    echo "  ⚠️ Jaeger not receiving traces"
fi

# Summary
echo ""
echo "=== Summary ==="
[ $KAFKA_STATUS -eq 0 ] && echo "  Kafka: ✅ OK" || echo "  Kafka: ❌ ISSUES"
[ $CH_STATUS -eq 0 ] && echo "  ClickHouse: ✅ OK" || echo "  ClickHouse: ❌ ISSUES"
[ $OTEL_STATUS -eq 0 ] && echo "  OTEL: ✅ OK" || echo "  OTEL: ❌ ISSUES"
```

**Uso:**
```bash
# Executar diagnóstico completo
./scripts/validation/validate-infrastructure-health.sh

# Executar apenas Kafka
./scripts/validation/validate-kafka-topics.sh

# Verificar health checks programáticos
curl -s http://<service>:8000/health | jq .
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