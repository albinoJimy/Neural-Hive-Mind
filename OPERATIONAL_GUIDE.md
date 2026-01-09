# Guia Operacional Completo - Neural Hive-Mind

## Visão Geral

Este guia consolidado fornece uma visão completa das operações do sistema Neural Hive-Mind, incluindo todas as melhorias de automação implementadas para deploy, validação e manutenção.
Todos os fluxos operacionais agora estão centralizados nos CLIs unificados (`scripts/build.sh`, `scripts/deploy.sh`, `tests/run-tests.sh`, `scripts/validate.sh`, `scripts/security.sh`, `ml_pipelines/ml.sh`); use os guias em `docs/scripts/` para referência rápida.

## Estrutura do Sistema

### Componentes Principais
- **Neural Engine**: Núcleo de processamento
- **API Gateway**: Ponto de entrada das requisições
- **Database**: PostgreSQL cluster para persistência
- **Message Queue**: Redis/RabbitMQ para comunicação assíncrona
- **Service Mesh**: Istio para conectividade mTLS
- **Monitoring**: Prometheus + Grafana para observabilidade

### Arquitetura de Deploy
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Deploy        │    │   Validation     │    │   Maintenance   │
│   Foundation    │────│   Comprehensive  │────│   Automation    │
│                 │    │   Suite          │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                        │                        │
         ▼                        ▼                        ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ • Terraform     │    │ • mTLS Tests     │    │ • Cluster       │
│ • Helm Charts   │    │ • Autoscaler     │    │   Maintenance   │
│ • Validation    │    │ • Health Checks  │    │ • Cost Optim.   │
│ • Rollback      │    │ • Performance    │    │ • Backup/Restore│
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Scripts de Automação Implementados

### 1. Deploy e Orquestração

#### `scripts/deploy/deploy-foundation.sh`
Script principal para deploy da infraestrutura com melhorias implementadas:

**Funcionalidades:**
- Orquestração completa de deploy com validação integrada
- Controle granular de suites de validação
- Sistema de rollback automatizado
- Logs estruturados com correlation IDs
- Suporte a dry-run e debugging

**Uso Básico:**
```bash
# Deploy completo com validação
./scripts/deploy/deploy-foundation.sh

# Deploy com validações específicas
VALIDATION_SUITES="security,performance" ./scripts/deploy/deploy-foundation.sh

# Deploy com rollback automático habilitado
ENABLE_AUTO_ROLLBACK=true ./scripts/deploy/deploy-foundation.sh
```

### 2. Validação e Testes

#### `scripts/validation/validate-comprehensive-suite.sh`
Orquestrador de todas as validações do sistema:

**Funcionalidades:**
- Execução coordenada de todos os testes de validação
- Modos paralelo e sequencial
- Geração de relatórios consolidados
- Retry automático para testes intermitentes
- Dashboard HTML interativo

**Uso:**
```bash
# Validação completa
./scripts/validation/validate-comprehensive-suite.sh

# Modo paralelo para velocidade
./scripts/validation/validate-comprehensive-suite.sh --parallel

# Validação rápida
./scripts/validation/validate-comprehensive-suite.sh --quick
```

#### Scripts de Validação Específicos

**mTLS Connectivity (`test-mtls-connectivity.sh`)**
- Testes de conectividade cross-namespace
- Simulação de rotação de certificados
- Validação de identidades SPIFFE
- Testes de performance de mTLS

**Autoscaler (`test-autoscaler.sh`)**
- Testes de scaling gradual e agressivo
- Validação multi-zona
- Testes de contention de recursos
- Análise de métricas de decisão

**Cluster Health (`validate-cluster-health.sh`)**
- Compliance com SLOs definidos
- Validação de certificados
- Verificação de segurança de containers
- Geração de recomendações automáticas

**Performance Benchmarks (`validate-performance-benchmarks.sh`)**
- Benchmarks de throughput e latência
- Testes de eficiência de recursos
- Validação de performance de storage
- Testes de carga com usuários concorrentes

**Disaster Recovery (`test-disaster-recovery.sh`)**
- Simulação de falhas de zona
- Testes de backup e restore
- Validação de RTO/RPO
- Testes de particionamento de rede

### 3. Manutenção e Automação

#### `scripts/maintenance/cluster-maintenance.sh`
Automação completa de manutenção do cluster:

**Operações Disponíveis:**
```bash
# Manutenção de rotina
./scripts/maintenance/cluster-maintenance.sh routine

# Manutenção profunda (mensal)
./scripts/maintenance/cluster-maintenance.sh deep

# Apenas limpeza
./scripts/maintenance/cluster-maintenance.sh cleanup

# Otimização de recursos
OPTIMIZE_RESOURCES=true ./scripts/maintenance/cluster-maintenance.sh optimize
```

#### `scripts/maintenance/cost-optimization.sh`
Análise e otimização de custos:

**Funcionalidades:**
```bash
# Análise de oportunidades
./scripts/maintenance/cost-optimization.sh analyze

# Gerar recomendações
./scripts/maintenance/cost-optimization.sh recommend

# Implementar otimizações
DRY_RUN=false ./scripts/maintenance/cost-optimization.sh optimize
```

#### `scripts/maintenance/backup-restore.sh`
Sistema completo de backup e restore:

**Operações:**
```bash
# Backup completo
./scripts/maintenance/backup-restore.sh backup $(date +%Y%m%d_%H%M%S) full

# Backup incremental
./scripts/maintenance/backup-restore.sh backup $(date +%Y%m%d_%H%M%S) incremental

# Restore de emergência
./scripts/maintenance/backup-restore.sh restore latest

# Verificar integridade
./scripts/maintenance/backup-restore.sh verify latest
```

### 4. Geração de Dashboards

#### `scripts/validation/generate-health-dashboard.sh`
Geração de dashboards interativos:

**Recursos:**
- Dashboard HTML com métricas em tempo real
- Integração com Prometheus e Grafana
- Relatórios JSON estruturados
- Alertas visuais por componente

## Biblioteca de Funções Comuns

### `scripts/validation/common-validation-functions.sh`
Biblioteca padronizada com:

**Funções de Logging:**
- `log_info()`, `log_warn()`, `log_error()`
- Logging estruturado com timestamps
- Suporte a correlation IDs

**Funções de Teste:**
- `add_test_result()` - Registra resultados
- `generate_summary_report()` - Relatórios consolidados
- `initialize_test_run()` - Inicialização padronizada

**Funções de Validação:**
- `check_prerequisites()` - Verificações pré-requisitos
- `validate_certificate()` - Validação de certificados
- `calculate_health_score()` - Pontuação de saúde

## Procedimentos Operacionais

### Deploy em Produção

**Pré-requisitos:**
1. Código revisado e aprovado
2. Testes passando em staging
3. Backup pré-deploy executado
4. Janela de manutenção aprovada

**Processo:**
```bash
# 1. Backup pré-deploy
./scripts/maintenance/backup-restore.sh backup $(date +%Y%m%d_%H%M%S) pre-deploy

# 2. Deploy com validação
./scripts/deploy/deploy-foundation.sh --version=v1.2.3

# 3. Validação pós-deploy
./scripts/validation/validate-comprehensive-suite.sh

# 4. Monitoramento contínuo
./scripts/validation/generate-health-dashboard.sh --real-time
```

### Resposta a Incidentes

**Severidade 1 (Crítico):**
```bash
# 1. Diagnóstico rápido
./scripts/validation/validate-cluster-health.sh --quick

# 2. Coleta de informações
./scripts/maintenance/collect-diagnostic-info.sh

# 3. Rollback se necessário
helm rollback neural-hive-mind
./scripts/validation/validate-comprehensive-suite.sh --quick

# 4. Restore se necessário
./scripts/maintenance/backup-restore.sh restore latest
```

### Manutenção Preventiva

**Semanal:**
```bash
# Domingo às 02:00 UTC
./scripts/maintenance/cluster-maintenance.sh routine
./scripts/validation/validate-comprehensive-suite.sh --weekly
```

**Mensal:**
```bash
# Primeiro sábado às 04:00 UTC
./scripts/maintenance/cluster-maintenance.sh deep
./scripts/maintenance/cost-optimization.sh analyze
./scripts/validation/test-disaster-recovery.sh
```

## Monitoramento e Alertas

### SLOs Definidos
- **Availability**: ≥ 99.9%
- **Response Time P95**: ≤ 500ms
- **Error Rate**: ≤ 0.1%
- **Throughput**: ≥ 1000 req/s

### Dashboards Principais
1. **System Health**: Status geral do sistema
2. **Performance**: Métricas de latência e throughput
3. **Security**: Status de certificados e mTLS
4. **Cost**: Análise de custos e otimizações

### Alertas Críticos
- Pods em CrashLoopBackOff
- Certificados expirando em < 7 dias
- CPU/Memory > 90%
- Taxa de erro > 1%
- Falhas de conectividade mTLS

## Documentação de Referência

### Operacional
- **Procedimentos**: `docs/operations/operational-procedures.md`
- **Troubleshooting**: `docs/operations/troubleshooting-guide.md`
- **Runbook**: `docs/operations/runbook.md`

### Templates
- **Incident Response**: `docs/templates/incident-response-template.md`
- **Maintenance Checklist**: `docs/templates/maintenance-checklist-template.md`
- **Deployment Checklist**: `docs/templates/deployment-checklist-template.md`

## Melhores Práticas

### Deploy
1. **Sempre** fazer backup antes de deploy em produção
2. **Nunca** fazer deploy direto sem passar por staging
3. **Sempre** executar validação completa pós-deploy
4. **Sempre** ter plano de rollback preparado
5. **Monitorar** sistema por pelo menos 1h após deploy

### Manutenção
1. **Executar** manutenção preventiva regularmente
2. **Monitorar** métricas de custo mensalmente
3. **Testar** procedimentos de disaster recovery trimestralmente
4. **Atualizar** documentação após mudanças
5. **Treinar** equipe em novos procedimentos

### Segurança
1. **Rotacionar** certificados antes do vencimento
2. **Monitorar** logs de auditoria regularmente
3. **Executar** scans de segurança semanalmente
4. **Validar** políticas de rede após mudanças
5. **Manter** inventário de vulnerabilidades atualizado

### Performance
1. **Executar** benchmarks antes/depois de mudanças
2. **Monitorar** SLOs continuamente
3. **Otimizar** recursos baseado em métricas reais
4. **Investigar** degradações de performance imediatamente
5. **Documentar** mudanças de performance

## SemanticPipeline Fallback

### Visão Geral
O sistema utiliza **SemanticPipeline** como fallback inteligente quando modelos ML não estão disponíveis, ao invés de heurísticas simples. O SemanticPipeline combina:
- **Análise Semântica**: Embeddings de sentence-transformers para avaliar segurança, arquitetura, performance e qualidade
- **Avaliação Ontológica**: Conhecimento estruturado sobre domínios, complexidade e padrões de risco

### Configuração
O fallback está **habilitado por padrão** via:
- **Config Python**: `use_semantic_fallback=True` em `config.py`
- **Helm Values**: `config.features.useSemanticFallback: true` em `values.yaml`
- **Env Var**: `USE_SEMANTIC_FALLBACK=true` nos pods

### Desabilitar SemanticPipeline (Rollback para Heurísticas)
Se necessário reverter para heurísticas simples:

```bash
# Opção 1: Via Helm (recomendado)
helm upgrade specialist-technical ./helm-charts/specialist-technical \
  --set config.features.useSemanticFallback=false \
  --reuse-values

# Opção 2: Via Env Var (temporário)
kubectl set env deployment/specialist-technical \
  -n neural-hive \
  USE_SEMANTIC_FALLBACK=false

# Verificar mudança
kubectl logs -n neural-hive deployment/specialist-technical | \
  grep "use_semantic_fallback"
```

### Monitoramento
**Logs**: Buscar por `"Falling back to semantic pipeline"` ou `"Falling back to specialist heuristics"`

**Métricas Prometheus**:
```promql
# Taxa de uso do SemanticPipeline
rate(neural_hive_specialist_evaluations_total{model_source="semantic_pipeline"}[5m])

# Taxa de uso de heurísticas
rate(neural_hive_specialist_evaluations_total{model_source="heuristics"}[5m])
```

**Grafana Dashboard**: Painel "Specialist Inference Sources" mostra distribuição ML/SemanticPipeline/Heuristics

### Troubleshooting SemanticPipeline
**Problema**: SemanticPipeline não está sendo usado (logs mostram "heuristics")
- **Causa**: `USE_SEMANTIC_FALLBACK=false` ou erro na inicialização do SemanticPipeline
- **Solução**: Verificar env var e logs de inicialização do specialist

**Problema**: Confiança muito baixa com SemanticPipeline
- **Causa**: Descrições de tarefas pobres (STE gerando descrições vazias)
- **Solução**: Enriquecer prompts do STE (ver fase subsequente)

### Calibração de Confiança
O sistema **reduz confiança em 20%** quando usa fallback (SemanticPipeline ou heurísticas) para sinalizar que não é inferência ML:
- **ML**: `confidence_score` original
- **SemanticPipeline**: `confidence_score * 0.8`
- **Heurísticas**: `confidence_score * 0.8`

Isso garante que decisões de consenso priorizem opiniões baseadas em ML quando disponíveis.

### Script de Validação
```bash
# Validar configuração de fallback
./scripts/validation/test-semantic-fallback.sh

# Validar todos os specialists
./scripts/validation/test-semantic-fallback.sh all

# Testar fallback com MLflow desligado (interativo)
./scripts/validation/test-semantic-fallback.sh technical
```

## Worker Agents - Validação de Executors

### Visão Geral

Os Worker Agents implementam 5 executors com integrações reais a sistemas externos. Esta seção documenta comandos de validação para cada executor.

### Validação Completa

```bash
# Validar todas as integrações Worker Agents
bash scripts/validation/validate-worker-agents-integrations.sh

# Saída esperada:
# ✅ BUILD Executor: Code Forge integration OK
# ✅ DEPLOY Executor: ArgoCD integration OK
# ✅ DEPLOY Executor: Flux integration OK
# ✅ TEST Executor: GitHub Actions integration OK
# ✅ VALIDATE Executor: OPA integration OK
# ✅ EXECUTE Executor: K8s Jobs integration OK
```

### Validação por Executor

**BUILD Executor - Code Forge**:
```bash
# Validar conectividade Code Forge
kubectl exec -n neural-hive-execution deployment/worker-agents -- \
  curl -f http://code-forge.neural-hive-code-forge:8000/health

# Validar executor
bash scripts/validation/validate-build-executor.sh

# Verificar métricas
kubectl port-forward -n neural-hive-execution svc/worker-agents 8000:8000
curl -s http://localhost:8000/metrics | grep build_tasks_executed_total
```

**DEPLOY Executor - ArgoCD/Flux**:
```bash
# Verificar integração ArgoCD
kubectl exec -n neural-hive-execution deployment/worker-agents -- \
  curl -k https://argocd.neural-hive-argocd/api/version

# Verificar integração Flux
kubectl get kustomizations -n flux-system

# Validar executor
bash scripts/validation/validate-deploy-executor.sh
```

**TEST Executor - CI/CD**:
```bash
# Verificar token GitHub
kubectl get secret github-token -n neural-hive-execution

# Validar executor
bash scripts/validation/validate-test-executor.sh

# Verificar métricas
curl -s http://localhost:8000/metrics | grep test_tasks_executed_total
```

**VALIDATE Executor - OPA/Security**:
```bash
# Verificar integração OPA
kubectl exec -n neural-hive-execution deployment/worker-agents -- \
  curl http://opa.neural-hive-governance:8181/health

# Verificar Trivy instalado
kubectl exec -n neural-hive-execution deployment/worker-agents -- trivy --version

# Validar executor
bash scripts/validation/validate-validate-executor.sh
```

**EXECUTE Executor - Multi-Runtime**:
```bash
# Verificar K8s Jobs RBAC
kubectl auth can-i create jobs --as=system:serviceaccount:neural-hive-execution:worker-agent-executor

# Verificar Docker disponível
kubectl exec -n neural-hive-execution deployment/worker-agents -- docker ps 2>/dev/null || echo "Docker não disponível"

# Validar executor
bash scripts/validation/validate-execute-executor.sh
```

### Monitoramento Contínuo

```bash
# Dashboard Grafana Worker Agents
kubectl port-forward -n observability svc/grafana 3000:3000
# Acessar http://localhost:3000/d/worker-agents

# Alertas Prometheus
kubectl port-forward -n observability svc/prometheus 9090:9090
# Acessar http://localhost:9090/alerts - buscar "WorkerAgent"

# Distributed Tracing (Jaeger)
kubectl port-forward -n observability svc/jaeger-query 16686:16686
# Buscar por service="worker-agents" operation="task_execution"
```

### Manutenção Preventiva Worker Agents

**Semanal**:
```bash
# Validar integrações
bash scripts/validation/validate-worker-agents-integrations.sh

# Verificar métricas de erro
kubectl exec -n observability deployment/prometheus -- \
  promtool query instant 'rate(build_tasks_executed_total{status="failed"}[1h]) > 0.1'
```

**Mensal**:
```bash
# Rotacionar tokens de integração
kubectl delete secret github-token gitlab-token jenkins-token -n neural-hive-execution
# Recriar secrets com novos tokens

# Atualizar políticas OPA
kubectl apply -f policies/rego/guard-agents/

# Testar disaster recovery
bash tests/e2e/phase2/worker-agents-disaster-recovery-test.sh
```

### Troubleshooting Worker Agents

**Executor não encontra cliente de integração**:
- **Sintoma**: Logs mostram fallback para simulação imediatamente
- **Causa**: Cliente não inicializado (URL/token não configurado)
- **Solução**: Verificar Helm values e secrets Kubernetes

**Timeout em operações longas**:
- **Sintoma**: Logs mostram timeout após X segundos
- **Causa**: Timeout padrão insuficiente para operação
- **Solução**: Aumentar `timeout_seconds` no ticket ou configuração global

**Retry esgotado**:
- **Sintoma**: Logs mostram 3 tentativas falhadas
- **Causa**: Serviço externo indisponível ou erro persistente
- **Solução**: Verificar conectividade e logs do serviço externo

**Comandos de diagnóstico**:
```bash
# Verificar conectividade com serviços externos
kubectl exec -n neural-hive-execution deployment/worker-agents -- \
  curl -v http://code-forge:8000/health

# Verificar secrets montados
kubectl exec -n neural-hive-execution deployment/worker-agents -- \
  ls -la /etc/secrets/

# Verificar logs estruturados
kubectl logs -n neural-hive-execution deployment/worker-agents --tail=100 | jq .

# Verificar traces OpenTelemetry
kubectl port-forward -n observability svc/jaeger-query 16686:16686
```

**Guia de Integração Completo**: `docs/WORKER_AGENTS_INTEGRATION_GUIDE.md`

---

## Troubleshooting Rápido

### Problemas Comuns

**Pods não inicializando:**
```bash
kubectl describe pod <pod-name> -n neural-hive-mind
kubectl logs <pod-name> -n neural-hive-mind --previous
```

**Conectividade mTLS falhando:**
```bash
./scripts/validation/test-mtls-connectivity.sh --debug
kubectl get certificates -n neural-hive-mind
```

**Performance degradada:**
```bash
./scripts/validation/validate-performance-benchmarks.sh
kubectl top pods -n neural-hive-mind --sort-by=cpu
```

**Alto uso de recursos:**
```bash
./scripts/maintenance/cost-optimization.sh analyze
kubectl describe nodes
```

**OpenTelemetry Span Export Failures (TypeError):**

Sintomas:
- Alerta `MCPToolCatalogSpanExportTypeError` disparado
- Logs contendo "TypeError durante export de spans"
- Métrica `neural_hive_span_export_failures_total{error_type="TypeError"}` > 0

Diagnóstico:
```bash
# Verificar Logs
kubectl logs -n <namespace> deployment/mcp-tool-catalog | grep -A 10 "TypeError.*export"

# Verificar Métricas
curl -s 'http://prometheus:9090/api/v1/query?query=rate(neural_hive_span_export_failures_total{service="mcp-tool-catalog",error_type="TypeError"}[5m])'

# Verificar Headers Customizados
# Revisar helm-charts/mcp-tool-catalog/templates/configmap.yaml
```

Resolução Curto Prazo:
1. Verificar que `neural_hive_observability` v1.2.2 está instalado
2. Confirmar que headers estão sendo sanitizados
3. Reiniciar pods se necessário

Resolução Longo Prazo:
1. Avaliar upgrade para OpenTelemetry 1.40+
2. Testar em ambiente de staging
3. Aplicar em produção se validado

## Contatos de Emergência

### Escalação
1. **L1**: DevOps Engineer (0-30 min)
2. **L2**: Senior DevOps (30-60 min)
3. **L3**: Tech Lead (60-120 min)
4. **L4**: Engineering Manager (120+ min)

### Canais
- **Slack**: #neural-hive-mind-ops
- **Emergency**: #incident-response
- **Email**: operations@neural-hive-mind.com
- **Status**: https://status.neural-hive-mind.com

## Próximos Passos

### Melhorias Futuras
1. **Automação**: Expandir automação de healing
2. **AI/ML**: Implementar detecção proativa de anomalias
3. **Multi-cluster**: Suporte a deployments multi-cluster
4. **Observability**: Melhorar tracing distribuído
5. **Security**: Implementar zero-trust networking

### Métricas de Sucesso
- Redução de MTTR em 50%
- Aumento de availability para 99.95%
- Redução de custos operacionais em 20%
- Automação de 80% das tarefas de manutenção

---

**Este guia operacional deve ser revisado mensalmente e atualizado conforme necessário.**

**Última Atualização:** $(date)
**Versão:** 1.0
**Mantenedores:** Equipe DevOps Neural Hive-Mind
