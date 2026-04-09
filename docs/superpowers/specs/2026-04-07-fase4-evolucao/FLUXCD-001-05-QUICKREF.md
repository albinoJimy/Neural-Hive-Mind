# FLUXCD-001-05: Notificações Slack - Quick Reference

**Status:** ✅ COMPLETO
**Data:** 2026-04-08

## Deploy Rápido

```bash
# 1. Criar Slack webhook em https://api.slack.com/apps

# 2. Criar secret (substituir URL)
kubectl create secret generic slack-webhook \
  --namespace=flux-system \
  --from-literal=webhookUrl='https://hooks.slack.com/services/YOUR/WEBHOOK'

# 3. Aplicar notificações
kubectl apply -k infrastructure/fluxcd/clusters/dev/flux-system/
kubectl apply -k infrastructure/fluxcd/clusters/staging/flux-system/
kubectl apply -k infrastructure/fluxcd/clusters/prod/flux-system/

# 4. Verificar
kubectl get provider,alert -n flux-system
```

## Canais Slack

| Ambiente | Canal | Tipos de Eventos |
|----------|-------|------------------|
| Dev | `#nhm-gitops-dev` | Todos (info, warning, error) |
| Staging | `#nhm-gitops-staging` | Erro, warning, success |
| Prod | `#nhm-gitops-prod` | Apenas críticos |

## Alertas Configurados

**Dev (9 alertas):**
- kustomization-errors
- helmrelease-errors
- drift-detection
- deployment-success
- health-check-warnings
- image-repository-events
- reconciliation-failure
- slack-dev-receiver

**Staging (10 alertas):**
- kustomization-errors (CRITICAL)
- helmrelease-errors (CRITICAL)
- drift-detection (CRITICAL)
- deployment-success
- health-check-warnings
- image-repository-events
- promotion-events
- reconciliation-failure
- smoke-test-results

**Prod (9 alertas):**
- kustomization-critical-errors (escalation: on-call)
- helmrelease-critical-errors (escalation: on-call)
- drift-detection-critical (escalation: security)
- deployment-success-prod (limitado)
- health-check-warnings-prod
- image-repository-events-prod
- promotion-events-prod
- reconciliation-failure-prod (escalation: on-call)
- rollback-events-prod (escalation: management)

## Ficheiros

```
infrastructure/fluxcd/
├── clusters/
│   ├── dev/flux-system/
│   │   ├── notifications.yaml          (232 linhas, 10 docs)
│   │   ├── kustomization.yaml
│   │   └── slack-webhook.example.yaml
│   ├── staging/flux-system/
│   │   ├── notifications.yaml          (248 linhas, 11 docs)
│   │   └── kustomization.yaml
│   └── prod/flux-system/
│       ├── notifications.yaml          (311 linhas, 12 docs)
│       └── kustomization.yaml
├── docs/
│   └── NOTIFICATIONS_SETUP.md          (Guia completo)
└── scripts/
    └── test-slack-notifications.sh     (Script de teste)
```

## Testes

```bash
# Verificar notificações
./infrastructure/fluxcd/scripts/test-slack-notifications.sh dev
./infrastructure/fluxcd/scripts/test-slack-notifications.sh staging
./infrastructure/fluxcd/scripts/test-slack-notifications.sh prod
```

## Documentação

- Guia completo: `infrastructure/fluxcd/docs/NOTIFICATIONS_SETUP.md`
- Relatório de implementação: `docs/superpowers/specs/2026-04-07-fase4-evolucao/FLUXCD-001-05-IMPLEMENTATION.md`
- Exemplo de webhook: `infrastructure/fluxcd/clusters/dev/flux-system/slack-webhook.example.yaml`
