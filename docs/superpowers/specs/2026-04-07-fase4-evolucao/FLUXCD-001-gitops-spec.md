# FLUXCD-001: Automatizar GitOps com FluxCD

**Data:** 2026-04-07
**Prioridade:** ALTA
**Estimativa:** XL (3-4 semanas)

---

## Metadata

| Campo | Valor |
|-------|-------|
| Componente | Incremental Deployment System (FluxCD) |
| Localização | infrastructure/fluxcd/ |
| Status Atual | PARCIAL (30%) |
| Status Alvo | IMPLEMENTADO (95%+) |

---

## 1. Validação Funcionalidade

### 1.1 Funcionalidade Esperada

Baseado na especificação da Fase 4, o componente deve:
- Implementar pipeline GitOps completo com FluxCD
- Automatizar deploy dev → staging → production
- Gerenciar versionamento de manifests
- Implementar promotion automática com testes
- Suportar rollback instantâneo

### 1.2 Funcionalidade Implementada

**Atual:**
- Manifestos FluxCD básicos existem (114 linhas)
- GotK components instalados
- Alguns serviços manifestados (gateway-intencoes, worker-agents)

**Gaps Identificados:**
- ❌ Pipeline dev→staging→prod não automatizado
- ❌ Falta manifests para todos os serviços
- ❌ Sem automação de deploy
- ❌ Sem testes automatizados entre ambientes
- ❌ Sem promoção automática

### 1.3 Gaps de Funcionalidade

- [ ] FLUXCD-001-01: Criar estrutura de repositório GitOps
- [ ] FLUXCD-001-02: Definir manifests para todos os 15+ serviços
- [ ] FLUXCD-001-03: Implementar pipeline de promotion (dev→staging→prod)
- [ ] FLUXCD-001-04: Integrar testes automatizados no pipeline
- [x] FLUXCD-001-05: Implementar notification webhook (Slack) ✅ (2026-04-08)
- [ ] FLUXCD-001-06: Configurar drift detection
- [ ] FLUXCD-001-07: Implementar automatic secret decryption
- [ ] FLUXCD-001-08: Configurar ImageRepository para todos os containers

---

## 2. Validação Testes

### 2.1 Cobertura Unitária

**Atual:** N/A

**Gaps:**
- [ ] FLUXCD-001-09: Testar sintaxe de todos os manifests (kubeval)
- [ ] FLUXCD-001-10: Testar aplicação em cluster local (kind/minikube)
- [ ] FLUXCD-001-11: Testar policy validation (OPA Gatekeeper)

### 2.2 Cobertura Integração

**Gaps:**
- [ ] FLUXCD-001-12: Teste E2E do pipeline completo
- [ ] FLUXCD-001-13: Teste de rollback automático
- [ ] FLUXCD-001-14: Teste de promotion com falha

---

## 3. Validação Integração

### 3.1 Dependências Externas

| Serviço | Método | Status |
|---------|--------|--------|
| GitHub | GitOps source | ⚠️ Parcial |
| Container Registry | Image updates | ⚠️ Parcial |
| Kubernetes | Deployment target | ✅ |
| Slack | Notifications | ❌ |
| OPA | Policy validation | ❌ |

### 3.2 Gaps de Integração

- [ ] FLUXCD-001-15: Integração com GitHub repositories (flux-system, services)
- [ ] FLUXCD-001-16: Integração com GitHub Container Registry
- [ ] FLUXCD-001-17: Webhook notifications para Slack
- [ ] FLUXCD-001-18: Integração com OPA Gatekeeper para policies
- [ ] FLUXCD-001-19: Integração com CI/CD (GitHub Actions) para image tagging

---

## 4. Validação Observabilidade

### 4.1 Métricas Prometheus

**Gaps:**
- [ ] FLUXCD-001-20: `flux_reconcile_total`
- [ ] FLUXCD-001-21: `flux_reconcile_failed_total`
- [ ] FLUXCD-001-22: `flux_git_operations_duration_seconds`
- [ ] FLUXCD-001-23: `flux_kustomization_ready`

### 4.2 Tracing OpenTelemetry

**Gaps:**
- [ ] FLUXCD-001-24: Spans para reconciliação de Kustomizations
- [ ] FLUXCD-001-25: Spans para Helm releases

### 4.3 Logging Structlog

**Gaps:**
- [ ] FLUXCD-001-26: Logs estruturados de operações Flux
- [ ] FLUXCD-001-27: Logs de eventos de GitOps

---

## 5. Validação Documentação

### 5.1 Documentação Técnica

| Doc | Existe | Localização |
|-----|--------|-------------|
| README | ❌ | — |
| Arquitetura GitOps | ❌ | — |
| Runbooks | ❌ | — |
| Pipeline Docs | ❌ | — |

### 5.2 Gaps de Documentação

- [ ] FLUXCD-001-28: README com instruções de GitOps workflow
- [ ] FLUXCD-001-29: Diagrama do pipeline dev→staging→prod
- [ ] FLUXCD-001-30: Runbook de rollback via GitOps
- [ ] FLUXCD-001-31: Runbook de promotion manual
- [ ] FLUXCD-001-32: Documentação de estrutura de repositórios

---

## 6. Tickets Decompostos

### FLUXCD-001-01: Criar estrutura de repositório GitOps

**Tipo:** feature
**Estimativa:** S (2-3 dias)

**Descrição:**
Criar estrutura monorepo ou multirepo para GitOps com organização de ambientes e serviços.

**Acceptance Criteria:**
- [ ] Repositório `nhm-gitops` criado
- [ ] Estrutura: `/clusters/{cluster}/`, `/apps/`, `/infrastructure/`
- [ ] Ambientes: dev, staging, production
- [ ] Documentação da estrutura
- [ ] Política de branches

---

### FLUXCD-001-02: Definir manifests para todos os 15+ serviços

**Tipo:** feature
**Estimativa:** L (2-3 semanas)

**Descrição:**
Criar Helm charts e Kustomizations para todos os serviços do NHM.

**Services:**
1. gateway-intencoes
2. semantic-translation-engine
3. consensus-engine
4. orchestrator-dynamic
5. approval-service
6. worker-agents
7. queen-agent
8. service-registry
9. analyst-agents
10. scout-agents
11. guard-agents
12. optimizer-agents
13. self-healing-engine
14. execution-ticket-service
15. sla-management-system

**Acceptance Criteria:**
- [ ] Helm chart base criado (common)
- [ ] Kustomization para cada serviço
- [ ] Values por ambiente (dev, staging, prod)
- [ ] Testes de aplicação
- [ ] Documentação de customização

---

### FLUXCD-001-03: Implementar pipeline de promotion (dev→staging→prod)

**Tipo:** feature
**Estimativa:** M (1 semana)

**Descrição:**
Implementar pipeline automatizado de promoção entre ambientes com gates de aprovação.

**Acceptance Criteria:**
- [ ] FluxCD Kustomization por ambiente
- [ ] Política de promotion automática para dev→staging
- [ ] Aprovação manual para staging→prod
- [ ] Testes automatizados como gate
- [ ] Rollback automático em falha
- [ ] Dashboard de status

---

### FLUXCD-001-04: Integrar testes automatizados no pipeline

**Tipo:** feature
**Estimativa:** M (1 semana)

**Descrição:**
Integrar testes E2E e smoke tests no pipeline de promotion.

**Acceptance Criteria:**
- [ ] Job Kubernetes pós-deploy em staging
- [ ] Smoke tests para cada serviço
- [ ] Testes E2E do cognitive pipeline
- [ ] Report de testes no Slack
- [ ] Bloqueio de promotion em falha

---

### FLUXCD-001-05: Implementar notification webhook (Slack) ✅

**Tipo:** feature
**Estimativa:** S (2-3 dias)
**Status:** COMPLETO (2026-04-08)

**Descrição:**
Configurar notificações Slack para eventos GitOps.

**Acceptance Criteria:**
- [x] Notification provider configurado (3 providers: dev, staging, prod)
- [x] Canal Slack por ambiente (#nhm-gitops-dev, #nhm-gitops-staging, #nhm-gitops-prod)
- [x] Eventos: deploy success/failure, drift detected
- [x] Mensagens formatadas com informações relevantes
- [x] Alertas para falhas críticas (com escalarão: on-call, security)

**Relatório:** `./FLUXCD-001-05-IMPLEMENTATION.md`

---

### FLUXCD-001-06: Configurar drift detection

**Tipo:** feature
**Estimativa:** S (2-3 dias)

**Descrição:**
Configurar detecção de drift entre estado Git e cluster.

**Acceptance Criteria:**
- [ ] Drift detection habilitado
- [ ] Alertas em drift detectado
- [ ] Auto-correção opcional (apenas dev)
- [ ] Report de drift no dashboard
- [ ] Integração com Slack para alertas

---

### FLUXCD-001-07: Implementar automatic secret decryption

**Tipo:** feature
**Estimativa:** M (1 semana)

**Descrição:**
Integrar external secrets ou SOPS para gerenciar secrets via GitOps.

**Acceptance Criteria:**
- [ ] External Secrets Operator instalado
- [ ] SecretStore configurado (AWS Secrets Manager ou Vault)
- [ ] Manifests de ExternalSecret
- [ ] Rotação automática
- [ ] Testes de sync

---

### FLUXCD-001-08: Configurar ImageRepository para todos os containers

**Tipo:** feature
**Estimativa:** M (1 semana)

**Descrição:**
Configurar ImageUpdateAutomation para atualização automática de imagens.

**Acceptance Criteria:**
- [ ] ImageRepository para cada serviço
- [ ] ImagePolicy para semver ou tag regex
- [ ] ImageUpdateAutomation automático
- [ ] Notificação em nova imagem
- [ ] Testes de atualização

---

## 7. Arquitetura Proposta

```
┌─────────────────────────────────────────────────────────────────┐
│                         GitHub Repositories                      │
├─────────────────────────────────────────────────────────────────┤
│  nhm-code/           │  nhm-gitops/           │  nhm-infra/     │
│  ────────────────    │  ────────────────────   │  ───────────    │
│  services/*         │  clusters/dev/         │  terraform/     │
│  libraries/         │  clusters/staging/     │  ───────────    │
│  infrastructure/    │  clusters/prod/        │                 │
│                     │  apps/                 │                 │
│                     │  infrastructure/        │                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CI/CD (GitHub Actions)                       │
├─────────────────────────────────────────────────────────────────┤
│  1. PR Tests → 2. Build Image → 3. Push to GHCR                │
│                                        │                        │
│                         ┌──────────────┘                        │
│                         ▼                                       │
│              4. Update tag in GitOps                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GitOps (FluxCD)                              │
├─────────────────────────────────────────────────────────────────┤
│  Dev Cluster          │  Staging Cluster   │  Prod Cluster     │
│  ──────────────       │  ────────────────   │  ────────────    │
│  Auto-sync (1min)     │  Auto-sync (5min)   │  Auto (manual)   │
│  Auto-promote         │  Manual approve     │  Manual approve  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 8. Resumo Executivo

**Completude Atual:** 30%
**Completude Alvo:** 95%
**Gaps Totais:** 32
**Tickets Propostos:** 8 (acima) + 24 (detalhados nos gaps)
**Estimativa Total:** XL (3-4 semanas)

**Dependências:**
- GitHub/GitHub Container Registry
- Clusters Kubernetes (dev, staging, prod)
- Slack workspace
- AWS Secrets Manager ou Vault

**Riscos:**
- Complexidade inicial alta
- Necessita mudança de cultura (push → pull)
- Requer disciplina no fluxo de trabalho

**Mitigações:**
- Começar com ambiente dev apenas
- Documentação extensa e treinamento
- Pipeline de rollback bem definido
- Testes automatizados como gate
