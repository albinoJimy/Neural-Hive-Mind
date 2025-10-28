# Runbook Operacional do Neural Hive-Mind

## Visão Geral

Este runbook contém procedimentos operacionais passo-a-passo para o sistema Neural Hive-Mind, incluindo tarefas de rotina, resposta a alertas e procedimentos de manutenção.

## Informações do Sistema

### Arquitetura
- **Plataforma**: Kubernetes
- **Service Mesh**: Istio
- **Monitoramento**: Prometheus + Grafana
- **Logging**: ELK Stack
- **Backup**: Velero
- **CI/CD**: GitOps com ArgoCD

### Componentes Críticos
- **Neural Engine**: Processamento principal
- **API Gateway**: Entrada de requisições
- **Database**: PostgreSQL cluster
- **Message Queue**: Redis/RabbitMQ
- **Storage**: Persistent Volumes

### SLOs Definidos
- **Availability**: 99.9%
- **Response Time P95**: < 500ms
- **Error Rate**: < 0.1%
- **Throughput**: > 1000 req/s

## Procedimentos de Startup

### 1. Startup Completo do Sistema

**Quando usar**: Após manutenção planejada ou falha completa do sistema

**Pré-condições**:
- Cluster Kubernetes operacional
- Acesso aos repositórios de código
- Credenciais de deploy disponíveis

**Procedimento**:

```bash
# 1. Verificar saúde do cluster
kubectl get nodes
kubectl get pods -A | grep -v Running

# 2. Deploy da infraestrutura base
./scripts/deploy/deploy-foundation.sh

# 3. Aguardar conclusão do deploy
kubectl get pods -n neural-hive-mind -w

# 4. Executar validação completa
./scripts/validation/validate-comprehensive-suite.sh

# 5. Verificar SLOs
./scripts/validation/validate-cluster-health.sh --slo-check

# 6. Gerar dashboard de status
./scripts/validation/generate-health-dashboard.sh
```

**Critérios de Sucesso**:
- Todos os pods em estado `Running`
- Todos os testes de validação passando
- SLOs dentro dos targets
- Dashboard mostrando status verde

**Rollback**:
```bash
# Se startup falhar
helm rollback neural-hive-mind
kubectl delete namespace neural-hive-mind --force --grace-period=0
```

### 2. Startup Seletivo de Componentes

**Quando usar**: Restart de componentes específicos

**Procedimento por Componente**:

**Neural Engine**:
```bash
kubectl rollout restart deployment/neural-engine -n neural-hive-mind
kubectl rollout status deployment/neural-engine -n neural-hive-mind
./scripts/validation/test-mtls-connectivity.sh --component=neural-engine
```

**API Gateway**:
```bash
kubectl rollout restart deployment/api-gateway -n neural-hive-mind
kubectl rollout status deployment/api-gateway -n neural-hive-mind
curl -f http://api-gateway.neural-hive-mind.svc.cluster.local/health
```

**Database**:
```bash
kubectl rollout restart statefulset/postgresql -n neural-hive-mind
kubectl wait --for=condition=ready pod -l app=postgresql -n neural-hive-mind --timeout=300s
kubectl exec -it postgresql-0 -n neural-hive-mind -- pg_isready
```

## Resposta a Alertas

### Alert: High CPU Usage

**Severidade**: Warning/Critical
**Threshold**: Warning > 80%, Critical > 90%

**Procedimento**:

```bash
# 1. Identificar pods com alto CPU
kubectl top pods -n neural-hive-mind --sort-by=cpu

# 2. Verificar histórico de métricas
kubectl describe pod <high-cpu-pod> -n neural-hive-mind

# 3. Verificar logs para problemas
kubectl logs <high-cpu-pod> -n neural-hive-mind --tail=100

# 4. Se necessário, escalar horizontalmente
kubectl scale deployment <deployment-name> --replicas=<new-count> -n neural-hive-mind

# 5. Monitorar por 15 minutos
watch kubectl top pods -n neural-hive-mind
```

**Escalação**: Se CPU > 95% por mais de 10 minutos, escalar para nível 2

### Alert: High Memory Usage

**Severidade**: Warning/Critical
**Threshold**: Warning > 85%, Critical > 95%

**Procedimento**:

```bash
# 1. Identificar pods com alta memória
kubectl top pods -n neural-hive-mind --sort-by=memory

# 2. Verificar se há OOMKills recentes
kubectl get events -n neural-hive-mind | grep OOMKilled

# 3. Verificar memory limits
kubectl describe pod <high-memory-pod> -n neural-hive-mind | grep -A5 -B5 Limits

# 4. Se necessário, aumentar memory limits
kubectl patch deployment <deployment-name> -n neural-hive-mind -p='{"spec":{"template":{"spec":{"containers":[{"name":"<container>","resources":{"limits":{"memory":"2Gi"}}}]}}}}'

# 5. Restart pod se necessário
kubectl delete pod <pod-name> -n neural-hive-mind
```

### Alert: Pod CrashLoopBackOff

**Severidade**: Critical

**Procedimento**:

```bash
# 1. Identificar pods em crash loop
kubectl get pods -n neural-hive-mind | grep CrashLoopBackOff

# 2. Examinar logs do container
kubectl logs <pod-name> -n neural-hive-mind --previous

# 3. Verificar eventos do pod
kubectl describe pod <pod-name> -n neural-hive-mind

# 4. Verificar recursos e configuração
kubectl get deployment <deployment-name> -n neural-hive-mind -o yaml

# 5. Se problema de configuração, aplicar fix
kubectl edit deployment <deployment-name> -n neural-hive-mind

# 6. Se problema de recurso, ajustar
kubectl patch deployment <deployment-name> -n neural-hive-mind -p='{"spec":{"template":{"spec":{"containers":[{"name":"<container>","resources":{"requests":{"memory":"512Mi","cpu":"250m"}}}]}}}}'
```

### Alert: High Error Rate

**Severidade**: Critical
**Threshold**: > 1% error rate

**Procedimento**:

```bash
# 1. Verificar métricas de erro detalhadas
kubectl logs -l app=api-gateway -n neural-hive-mind | grep ERROR | tail -50

# 2. Verificar conectividade entre serviços
./scripts/validation/test-mtls-connectivity.sh

# 3. Verificar status dos backends
kubectl get pods -n neural-hive-mind -o wide

# 4. Verificar métricas de latência
./scripts/validation/validate-performance-benchmarks.sh --latency-only

# 5. Se necessário, fazer rollback
helm rollback neural-hive-mind

# 6. Verificar recuperação
watch curl -s -o /dev/null -w "%{http_code}" http://api-gateway.neural-hive-mind.svc.cluster.local/health
```

### Alert: Certificate Expiring

**Severidade**: Warning (< 30 days), Critical (< 7 days)

**Procedimento**:

```bash
# 1. Verificar certificados próximos ao vencimento
kubectl get certificates -n neural-hive-mind -o custom-columns=NAME:.metadata.name,READY:.status.conditions[0].status,EXPIRES:.status.notAfter

# 2. Forçar renovação se necessário
kubectl annotate certificate <cert-name> cert-manager.io/force-renewal=true -n neural-hive-mind

# 3. Verificar cert-manager
kubectl get pods -n cert-manager

# 4. Verificar se renovação foi bem-sucedida
kubectl describe certificate <cert-name> -n neural-hive-mind

# 5. Testar conectividade mTLS após renovação
./scripts/validation/test-mtls-connectivity.sh --cert-check
```

### Alert: Disk Space Low

**Severidade**: Warning > 80%, Critical > 90%

**Procedimento**:

```bash
# 1. Verificar uso de disco nos nós
kubectl get nodes -o custom-columns=NAME:.metadata.name,DISK:.status.allocatable.ephemeral-storage

# 2. Identificar pods com alto uso de disk
kubectl exec -it <pod-name> -n neural-hive-mind -- df -h

# 3. Limpar logs antigos
kubectl exec -it <pod-name> -n neural-hive-mind -- find /var/log -name "*.log" -mtime +7 -delete

# 4. Verificar PVCs com pouco espaço
kubectl get pvc -n neural-hive-mind

# 5. Se necessário, expandir PVC
kubectl patch pvc <pvc-name> -n neural-hive-mind -p='{"spec":{"resources":{"requests":{"storage":"20Gi"}}}}'
```

## Procedimentos de Manutenção

### 1. Manutenção Semanal

**Agenda**: Toda sexta-feira às 02:00 UTC
**Duração**: 2 horas
**Downtime**: Nenhum (rolling updates)

**Checklist**:

```bash
# 1. Backup completo
./scripts/maintenance/backup-restore.sh backup --full

# 2. Verificação de saúde do sistema
./scripts/validation/validate-cluster-health.sh

# 3. Limpeza de recursos órfãos
kubectl delete pods --field-selector=status.phase=Succeeded -A
kubectl delete jobs --field-selector=status.conditions[0].type=Complete -A

# 4. Verificação de certificados
./scripts/validation/test-mtls-connectivity.sh --cert-check

# 5. Teste de autoscaler
./scripts/validation/test-autoscaler.sh

# 6. Relatório de performance
./scripts/validation/validate-performance-benchmarks.sh

# 7. Gerar relatório semanal
./scripts/validation/generate-health-dashboard.sh --weekly-report
```

### 2. Manutenção Mensal

**Agenda**: Primeiro sábado do mês às 04:00 UTC
**Duração**: 4 horas
**Downtime**: 30 minutos (para updates críticos)

**Checklist**:

```bash
# 1. Backup completo com verificação
./scripts/maintenance/backup-restore.sh backup --full --verify

# 2. Atualização de imagens
kubectl set image deployment/neural-engine neural-engine=<new-image> -n neural-hive-mind
kubectl rollout status deployment/neural-engine -n neural-hive-mind

# 3. Teste de disaster recovery
./scripts/validation/test-disaster-recovery.sh

# 4. Otimização de custos
./scripts/maintenance/cost-optimization.sh analyze
./scripts/maintenance/cost-optimization.sh optimize --dry-run

# 5. Scan de segurança
kubectl run security-scan --image=aquasec/trivy --rm -it -- image <image-name>

# 6. Rotação de secrets
kubectl create secret generic new-secret --from-literal=key=new-value -n neural-hive-mind
kubectl patch deployment <deployment> -p='{"spec":{"template":{"spec":{"containers":[{"name":"<container>","env":[{"name":"SECRET","valueFrom":{"secretKeyRef":{"name":"new-secret","key":"key"}}}]}]}}}}' -n neural-hive-mind

# 7. Limpeza de logs antigos
kubectl exec -it <log-pod> -n neural-hive-mind -- find /var/log -mtime +30 -delete

# 8. Verificação de compliance
./scripts/validation/validate-cluster-health.sh --compliance-check

# 9. Relatório mensal
./scripts/validation/generate-health-dashboard.sh --monthly-report
```

### 3. Rotação de Certificados

**Frequência**: Conforme necessário (alertas)
**Downtime**: Rolling restart (< 5 minutos por serviço)

**Procedimento**:

```bash
# 1. Backup atual dos certificados
kubectl get secret -n neural-hive-mind -o yaml > certs-backup-$(date +%Y%m%d).yaml

# 2. Verificar certificados a vencer
kubectl get certificates -n neural-hive-mind -o custom-columns=NAME:.metadata.name,EXPIRES:.status.notAfter | grep $(date -d "+30 days" +%Y-%m)

# 3. Forçar renovação
kubectl annotate certificate <cert-name> cert-manager.io/force-renewal=true -n neural-hive-mind

# 4. Aguardar nova emissão
kubectl wait --for=condition=ready certificate <cert-name> -n neural-hive-mind --timeout=300s

# 5. Rolling restart dos deployments
kubectl rollout restart deployment -n neural-hive-mind

# 6. Verificar conectividade
./scripts/validation/test-mtls-connectivity.sh

# 7. Limpar certificados antigos se tudo ok
kubectl delete secret <old-cert-secret> -n neural-hive-mind
```

## Procedimentos de Backup e Restore

### 1. Backup Diário

**Agenda**: Diário às 01:00 UTC
**Retenção**: 30 dias

**Procedimento Automático**:
```bash
# Configurado via CronJob
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-backup
  namespace: neural-hive-mind
spec:
  schedule: "0 1 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: neural-hive-mind/backup:latest
            command: ["/scripts/maintenance/backup-restore.sh", "backup", "--daily"]
```

**Verificação Manual**:
```bash
# Verificar último backup
./scripts/maintenance/backup-restore.sh status

# Verificar integridade
./scripts/maintenance/backup-restore.sh verify --latest
```

### 2. Restore de Emergência

**Quando usar**: Perda de dados ou corrupção

**Procedimento**:

```bash
# 1. Parar todas as aplicações
kubectl scale deployment --replicas=0 -n neural-hive-mind --all

# 2. Verificar backups disponíveis
./scripts/maintenance/backup-restore.sh list

# 3. Restore do backup mais recente
./scripts/maintenance/backup-restore.sh restore --timestamp=<timestamp>

# 4. Verificar integridade dos dados
./scripts/validation/test-disaster-recovery.sh --data-integrity

# 5. Reiniciar aplicações
kubectl scale deployment --replicas=3 -n neural-hive-mind --all

# 6. Validação completa
./scripts/validation/validate-comprehensive-suite.sh

# 7. Comunicar status
echo "Restore concluído em $(date)" | mail -s "Neural Hive-Mind Restore" operations@company.com
```

## Procedimentos de Scaling

### 1. Scale Up Manual

**Quando usar**: Aumento de carga previsto ou detectado

**Procedimento**:

```bash
# 1. Verificar métricas atuais
kubectl top pods -n neural-hive-mind

# 2. Scale horizontal
kubectl scale deployment neural-engine --replicas=10 -n neural-hive-mind
kubectl scale deployment api-gateway --replicas=5 -n neural-hive-mind

# 3. Verificar distribuição
kubectl get pods -n neural-hive-mind -o wide

# 4. Monitorar performance
watch kubectl top pods -n neural-hive-mind

# 5. Ajustar HPA se necessário
kubectl patch hpa neural-engine-hpa -n neural-hive-mind -p='{"spec":{"maxReplicas":15}}'
```

### 2. Scale Down Manual

**Quando usar**: Redução de carga ou economia de recursos

**Procedimento**:

```bash
# 1. Verificar que carga diminuiu
kubectl top pods -n neural-hive-mind

# 2. Scale down gradual
kubectl scale deployment neural-engine --replicas=3 -n neural-hive-mind

# 3. Aguardar estabilização
sleep 60

# 4. Verificar que performance não degradou
./scripts/validation/validate-performance-benchmarks.sh --quick

# 5. Continuar scale down se ok
kubectl scale deployment api-gateway --replicas=2 -n neural-hive-mind
```

## Procedimentos de Deploy

### 1. Deploy de Atualização

**Quando usar**: Nova versão da aplicação

**Procedimento**:

```bash
# 1. Backup antes do deploy
./scripts/maintenance/backup-restore.sh backup --pre-deploy

# 2. Deploy com validação
./scripts/deploy/deploy-foundation.sh --version=<new-version>

# 3. Monitorar rollout
kubectl rollout status deployment/neural-engine -n neural-hive-mind

# 4. Validação pós-deploy
./scripts/validation/validate-comprehensive-suite.sh

# 5. Teste de carga
./scripts/validation/validate-performance-benchmarks.sh

# 6. Se problemas, rollback
if [ $? -ne 0 ]; then
    helm rollback neural-hive-mind
    kubectl rollout status deployment/neural-engine -n neural-hive-mind
fi
```

### 2. Rollback de Emergência

**Quando usar**: Deploy com problemas críticos

**Procedimento**:

```bash
# 1. Rollback imediato
helm rollback neural-hive-mind

# 2. Verificar status
kubectl get pods -n neural-hive-mind

# 3. Validação rápida
./scripts/validation/validate-cluster-health.sh --quick

# 4. Comunicar incidente
echo "Rollback executado em $(date). Razão: <motivo>" | mail -s "URGENTE: Rollback Neural Hive-Mind" operations@company.com

# 5. Coleta de dados para post-mortem
./scripts/maintenance/collect-diagnostic-info.sh
```

## Monitoramento e Alertas

### 1. Verificação de Saúde de Rotina

**Frequência**: A cada 15 minutos

**Script Automático**:
```bash
#!/bin/bash
# health-monitor.sh

./scripts/validation/validate-cluster-health.sh --silent

if [ $? -ne 0 ]; then
    echo "Health check failed at $(date)" | mail -s "Neural Hive-Mind Health Alert" operations@company.com
    slack-notify "#alerts" "Neural Hive-Mind health check failed"
fi
```

### 2. Coleta de Métricas

**Endpoints de Métricas**:
- Prometheus: `http://prometheus.monitoring.svc.cluster.local:9090`
- Grafana: `http://grafana.monitoring.svc.cluster.local:3000`
- Application: `http://api-gateway.neural-hive-mind.svc.cluster.local/metrics`

**Métricas Críticas**:
- `neural_hive_mind_requests_total`
- `neural_hive_mind_request_duration_seconds`
- `neural_hive_mind_errors_total`
- `neural_hive_mind_active_connections`

## Contatos e Escalação

### Plantão Operacional
- **Primário**: operations@company.com / +55 11 99999-0001
- **Secundário**: backup-ops@company.com / +55 11 99999-0002

### Escalação Técnica
1. **Nível 1**: DevOps Engineer (0-30 min)
2. **Nível 2**: Senior DevOps (30-60 min)
3. **Nível 3**: Tech Lead (60-120 min)
4. **Nível 4**: Engineering Manager (120+ min)

### Canais de Comunicação
- **Slack**: #neural-hive-mind-ops
- **Incident Chat**: #incident-response
- **Status Page**: https://status.neural-hive-mind.com

### Documentação de Referência
- **Wiki**: https://wiki.company.com/neural-hive-mind
- **Playbooks**: https://playbooks.company.com/neural-hive-mind
- **Architecture**: https://docs.company.com/neural-hive-mind/architecture