# Spec Requirements Document

> Spec: Self-Healing Engine
> Created: 2026-03-18
> Status: Planning

## Overview

Implementar auto-recuperação completa do Neural Hive-Mind com detecção automática de incidentes, remediação via playbooks YAML, deploy em Kubernetes e testes E2E. O sistema detecta falhas (timeout, crash, lag), valida ações via OPA e executa remediação automaticamente.

## User Stories

### História 1: Operador de Infraestrutura

Como **operador de infraestrutura**, quero que o sistema detecte e repare automaticamente falhas comuns, para reduzir intervenção manual e tempo de resolução.

**Fluxo:**
1. Worker agent crasha (pod em CrashLoopBackOff)
2. Self-Healing detecta via health check
3. Executa playbook: restart_pod → reallocate_ticket
4. Sistema recupera sem intervenção
5. Alerta é registado para análise

### História 2: Engenheiro de Plataforma

Como **engenheiro de plataforma**, quero playbooks configuráveis em YAML com validação OPA, para adaptar remediação a diferentes cenários.

**Fluxo:**
1. Novo playbook criado em YAML
2. Validado contra schema antes de deploy
3. Ações críticas validadas via OPA
4. Testado via chaos engineering
5. Deploy em produção com confiança

### História 3: SRE

Como **SRE**, quero métricas e dashboards de remediação, para monitorar eficácia e identificar melhorias.

**Fluxo:**
1. Dashboard mostra taxa de remediação bem-sucedida
2. Alerta se remediação falha repetidamente
3. Análise de MTTR (Mean Time To Recovery)
4. Identificação de playbooks ineficazes
5. Iteração contínua

## Spec Scope

1. **Testes Automatizados** - Corrigir imports existentes, adicionar testes unitários e E2E (pytest, Docker Compose)
2. **Kubernetes Deployment** - Manifestos K8s completos (Deployment, Service, ConfigMap, Secret, HPA, PDB)
3. **Helm Chart** - Chart para deploy com valores configuráveis por ambiente
4. **Detecção Automática** - Health checks periódicos que disparam remediação (circuit breaker pattern)
5. **Playbooks Adicionais** - Novos cenários: database_connection_recovery, memory_leak_detection, deadlock_recovery
6. **Métricas e Dashboard** - Prometheus metrics expandidas, Grafana dashboard completo

## Out of Scope

- - Implementação de novos injectores de chaos (já existem: pod, network, resource, application)
- - Sistema de alertas externo (PagerDuty, Slack) - usar Kafka events apenas
- - Multi-cluster Kubernetes (single cluster apenas)
- - Rollback automatizado de deployments (fora do âmbito de self-healing)

## Expected Deliverable

1. **Suite de testes completa** com cobertura >80% (unit + integration + E2E)
2. **Manifestos Kubernetes** válidos (`kubectl apply --dry-run=client` sem erros)
3. **Helm chart** funcional (`helm install` com sucesso em cluster)
4. **3 novos playbooks** implementados e testados
5. **Grafana dashboard** importável com todos os painéis de remediação
