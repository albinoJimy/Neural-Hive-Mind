# FluxCD Slack Notifications - Setup Guide

## Overview

Este guia documenta a implementação de notificações Slack para o FluxCD no Neural Hive Mind, cobrindo os ambientes de desenvolvimento, staging e produção.

## Estrutura de Ficheiros

```
infrastructure/fluxcd/clusters/
├── dev/flux-system/
│   ├── notifications.yaml          # Configuração de notificações dev
│   └── slack-webhook.example.yaml  # Exemplo de configuração webhook
├── staging/flux-system/
│   └── notifications.yaml          # Configuração de notificações staging
└── prod/flux-system/
    └── notifications.yaml          # Configuração de notificações produção
```

## Tipos de Notificações

### Por Ambiente

| Ambiente | Canal Slack | Eventos | Frequência |
|----------|-------------|---------|------------|
| **Dev** | #nhm-gitops-dev | Todos (info, warning, error, drift) | Alta |
| **Staging** | #nhm-gitops-staging | Erros, warnings, drift, success | Média |
| **Prod** | #nhm-gitops-prod | Apenas críticos (error, drift) | Baixa |

### Tipos de Eventos

1. **Kustomization Errors** - Falhas de sincronização GitOps
2. **HelmRelease Errors** - Falhas de deployment Helm
3. **Drift Detection** - Alterações fora do GitOps detectadas
4. **Deployment Success** - Deploy bem-sucedido
5. **Health Check Warnings** - Serviços degradados
6. **ImageRepository Events** - Novas imagens disponíveis
7. **Promotion Events** - Promoções entre ambientes
8. **Reconciliation Failures** - Falhas de reconciliação

## Setup Instructions

### 1. Criar Incoming Webhook no Slack

Para cada ambiente, criar um webhook dedicado:

1. Aceder a https://api.slack.com/apps
2. Criar nova app "FluxCD Notifications"
3. Ativar "Incoming Webhooks"
4. Adicionar webhook para cada canal:
   - Desenvolvimento: `#nhm-gitops-dev`
   - Staging: `#nhm-gitops-staging`
   - Produção: `#nhm-gitops-prod`
5. Copiar as URLs dos webhooks

### 2. Configurar Secrets

**Via kubectl (recomendado apenas para dev):**

```bash
# Ambiente dev
kubectl create secret generic slack-webhook \
  --namespace=flux-system \
  --context=dev-cluster \
  --from-literal=webhookUrl='https://hooks.slack.com/services/YOUR/DEV/WEBHOOK' \
  --from-literal=username='FluxCD Dev' \
  --from-literal=icon-emoji=':bee:' \
  --from-literal=channel='#nhm-gitops-dev'

# Ambiente staging
kubectl create secret generic slack-webhook \
  --namespace=flux-system \
  --context=staging-cluster \
  --from-literal=webhookUrl='https://hooks.slack.com/services/YOUR/STAGING/WEBHOOK' \
  --from-literal=username='FluxCD Staging' \
  --from-literal=icon-emoji=':warning:' \
  --from-literal=channel='#nhm-gitops-staging'

# Ambiente produção
kubectl create secret generic slack-webhook \
  --namespace=flux-system \
  --context=prod-cluster \
  --from-literal=webhookUrl='https://hooks.slack.com/services/YOUR/PROD/WEBHOOK' \
  --from-literal=username='FluxCD PROD' \
  --from-literal=icon-emoji=':rotating_light:' \
  --from-literal=channel='#nhm-gitops-prod'
```

**Via SOPS (recomendado para staging/prod):**

```bash
# Encriptar secret com SOPS
sops --encrypt --kms 'arn:aws:kms:...' slack-webhook-secret.yaml > slack-webhook-secret.sops.yaml

# Desencriptar e aplicar
sops --decrypt slack-webhook-secret.sops.yaml | kubectl apply -f -
```

**Via External Secrets Operator (recomendado para prod):**

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: slack-webhook
  namespace: flux-system
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secrets-manager
    kind: SecretStore
  target:
    name: slack-webhook
    creationPolicy: Owner
  data:
    - secretKey: webhookUrl
      remoteRef:
        key: prod/fluxcd/slack-webhook
        property: url
```

### 3. Aplicar Configuração de Notificações

```bash
# Ambiente dev
kubectl apply -f infrastructure/fluxcd/clusters/dev/flux-system/notifications.yaml \
  --context=dev-cluster

# Ambiente staging
kubectl apply -f infrastructure/fluxcd/clusters/staging/flux-system/notifications.yaml \
  --context=staging-cluster

# Ambiente produção
kubectl apply -f infrastructure/fluxcd/clusters/prod/flux-system/notifications.yaml \
  --context=prod-cluster
```

### 4. Verificar Instalação

```bash
# Ver providers
kubectl get provider -n flux-system

# Esperado:
# NAME          TYPE     CHANNEL            AGE
# slack-dev     slack    nhm-gitops-dev     1m
# slack-staging slack    nhm-gitops-staging 1m
# slack-prod    slack    nhm-gitops-prod    1m

# Ver alerts
kubectl get alert -n flux-system

# Ver eventos recentes
kubectl get events -n flux-system --sort-by='.lastTimestamp'
```

## Estrutura das Mensagens

### Formato das Notificações

As notificações seguem o seguinte formato:

```
[EMOJI] [TIPO] [AMBIENTE]: Kind/Name - Mensagem

Timestamp: 2026-04-08T14:30:00Z
Event: KustomizationReady
Severity: info
Message: Deployment completed successfully
```

### Exemplos de Mensagens

**Deploy Success (Dev):**
```
✅ Deploy bem-sucedido [DEV]: Kustomization/core-services

Timestamp: 2026-04-08T14:30:00Z
Namespace: flux-system
Revision: main@sha1:abc123
```

**Critical Error (Prod):**
```
🚨🚨 ERRO CRÍTICO [PROD]: Kustomization/infrastructure - INTERVENÇÃO MANUAL NECESSÁRIA

Timestamp: 2026-04-08T14:30:00Z
Severity: error
Message: reconciliation failed
Action Required: immediate
Escalation: on-call
```

**Drift Detected (Staging):**
```
⚠️ DRIFT DETECTADO [STAGING]: HelmRelease/gateway-intencoes

Timestamp: 2026-04-08T14:30:00Z
Severity: error
Action Required: true
Message: Configuration drift detected outside GitOps
```

## Customização

### Alterar Canais Slack

Editar o ficheiro `notifications.yaml` do ambiente:

```yaml
apiVersion: notification.toolkit.fluxcd.io/v1beta2
kind: Provider
metadata:
  name: slack-dev
  namespace: flux-system
spec:
  type: slack
  channel: novo-canal-customizado  # Alterar aqui
  secretRef:
    name: slack-webhook
```

### Suspender Notificações

Para suspender temporariamente as notificações (manutenção):

```bash
kubectl patch provider slack-dev -n flux-system --type='merge' -p '{"spec":{"suspend":true}}'

# Reativar
kubectl patch provider slack-dev -n flux-system --type='merge' -p '{"spec":{"suspend":false}}'
```

### Adicionar Novos Alertas

Criar novo alert no ficheiro `notifications.yaml`:

```yaml
apiVersion: notification.toolkit.fluxcd.io/v1beta2
kind: Alert
metadata:
  name: meu-novo-alert
  namespace: flux-system
spec:
  providerRef:
    name: slack-dev
  eventSources:
    - kind: Kustomization
      name: "meu-servico"
      namespace: flux-system
  eventSeverity: info
  eventMetadata:
    custom_field: "custom_value"
  summary: "Minha mensagem customizada"
  timeout: 5m
```

## Troubleshooting

### Notificações não chegam ao Slack

1. Verificar se o secret existe:
   ```bash
   kubectl get secret slack-webhook -n flux-system
   ```

2. Verificar se a webhook URL está correta:
   ```bash
   kubectl get secret slack-webhook -n flux-system -o jsonpath='{.data.webhookUrl}' | base64 -d
   ```

3. Verificar status do provider:
   ```bash
   kubectl get provider slack-dev -n flux-system -o yaml
   ```

4. Verificar eventos do namespace:
   ```bash
   kubectl get events -n flux-system --field-selector involvedObject.name=slack-dev
   ```

### Erro "Failed to send notification"

Verificar:
- Webhook URL válida
- Canal existe no Slack
- App tem permissões para escrever no canal
- Conectividade entre cluster e Slack API

### Testar Webhook Manualmente

```bash
# Teste manual do webhook
curl -X POST \
  'https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK' \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "Teste de webhook FluxCD",
    "username": "FluxCD Test",
    "icon_emoji": ":bee:"
  }'
```

## Melhores Práticas

1. **Separar ambientes**: Usar webhooks diferentes para dev, staging e prod
2. **Limitar spam em prod**: Apenas notificações críticas em produção
3. **Usar canais dedicados**: Criar canais específicos para GitOps
4. **Monitorar frequência**: Evitar sobrecarregar o canal com muitas mensagens
5. **Encriptar secrets**: Usar SOPS ou External Secrets para webhooks em produção
6. **Documentar canais**: Manter documentação atualizada dos canais Slack

## Referências

- [FluxCD Notification Documentation](https://fluxcd.io/flux/components/notification/)
- [Slack Incoming Webhooks](https://api.slack.com/messaging/webhooks)
- [FluxCD Alert Specification](https://fluxcd.io/flux/components/notification/alerts/)
