# Quick Start - Fase 2

Guia rápido para configurar integrações externas da Fase 2.

## Pré-requisitos

- Kubernetes cluster (v1.24+)
- Helm 3.x
- kubectl configurado
- Fase 0 e Fase 1 deployadas

## Passo 1: Configurar API Keys

```bash
# OpenAI
export OPENAI_API_KEY="sk-..."

# Anthropic (opcional)
export ANTHROPIC_API_KEY="sk-ant-..."

# ArgoCD
export ARGOCD_TOKEN="eyJhbGc..."
export ARGOCD_URL="https://argocd.example.com"
```

## Passo 2: Criar Secrets

```bash
# Code Forge LLM
kubectl create secret generic code-forge-llm-secrets \
  -n neural-hive-execution \
  --from-literal=LLM_API_KEY="$OPENAI_API_KEY" \
  --from-literal=LLM_ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY"

# Worker Agents ArgoCD
kubectl create secret generic worker-agents-argocd-secrets \
  -n neural-hive-execution \
  --from-literal=argocd_token="$ARGOCD_TOKEN"
```

## Passo 3: Deploy com Helm

```bash
# Code Forge com LLM habilitado
helm upgrade --install code-forge helm-charts/code-forge \
  -n neural-hive-execution \
  --set config.LLM_ENABLED=true \
  --set config.LLM_PROVIDER=openai \
  --set config.LLM_MODEL=gpt-4 \
  --set secrets.existingSecret=code-forge-llm-secrets

# Worker Agents com ArgoCD
helm upgrade --install worker-agents helm-charts/worker-agents \
  -n neural-hive-execution \
  --set config.argocd.enabled=true \
  --set config.argocd.url="$ARGOCD_URL" \
  --set secrets.argoCdToken="$ARGOCD_TOKEN"
```

## Passo 4: Validar Configuração

```bash
bash scripts/validation/validate-phase2-config.sh
```

## Passo 5: Testar Integração

```bash
# Testar LLM
kubectl exec -it deployment/code-forge -n neural-hive-execution -- \
  python -c "from src.config.settings import get_settings; s=get_settings(); print(f'LLM: {s.LLM_PROVIDER}')"

# Testar ArgoCD
kubectl exec -it deployment/worker-agents -n neural-hive-execution -- \
  python -c "from src.config.settings import get_settings; s=get_settings(); print(f'ArgoCD: {s.argocd_url}')"
```

## Verificar Status

```bash
# Pods
kubectl get pods -n neural-hive-execution

# Logs
kubectl logs -n neural-hive-execution -l app.kubernetes.io/name=code-forge --tail=50
kubectl logs -n neural-hive-execution -l app.kubernetes.io/name=worker-agents --tail=50
```

## Próximos Passos

1. Configure políticas OPA em `policies/rego/`
2. Execute testes E2E: `pytest tests/e2e/`
3. Configure dashboards Grafana em `observability/grafana/dashboards/`
