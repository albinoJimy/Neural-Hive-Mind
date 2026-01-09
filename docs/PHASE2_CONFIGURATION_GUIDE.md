# Guia de Configuração - Fase 2

Este guia documenta as configurações necessárias para integrações externas da Fase 2 do Neural Hive-Mind.

## Visão Geral

A Fase 2 requer configurações de integrações externas:
- **LLM (OpenAI/Anthropic)**: Geração de código via LLM
- **ArgoCD**: Deploy GitOps via ArgoCD
- **Flux CD**: Deploy GitOps via Flux
- **OPA Gatekeeper**: Validação de políticas

## Configuração LLM (Code Forge)

### Variáveis de Ambiente

| Variável | Descrição | Obrigatório |
|----------|-----------|-------------|
| `LLM_ENABLED` | Habilitar geração LLM | Sim (se usar LLM) |
| `LLM_PROVIDER` | Provider: `openai`, `anthropic`, `local` | Sim (se LLM habilitado) |
| `LLM_API_KEY` | API key OpenAI | Sim (se provider=openai) |
| `LLM_ANTHROPIC_API_KEY` | API key Anthropic | Sim (se provider=anthropic) |
| `LLM_MODEL` | Modelo (ex: `gpt-4`, `claude-3-opus-20240229`) | Não (default: gpt-4) |
| `LLM_BASE_URL` | URL do endpoint local | Sim (se provider=local) |

### Secret Kubernetes

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: code-forge-llm-secrets
  namespace: neural-hive-execution
type: Opaque
stringData:
  LLM_API_KEY: "sk-..."
  LLM_ANTHROPIC_API_KEY: "sk-ant-..."
```

### Helm Values

```yaml
# helm-charts/code-forge/values.yaml
secrets:
  existingSecret: "code-forge-llm-secrets"
  openaiApiKeyKey: LLM_API_KEY
  anthropicApiKeyKey: LLM_ANTHROPIC_API_KEY
```

## Configuração ArgoCD (Worker Agents)

### Variáveis de Ambiente

| Variável | Descrição | Obrigatório |
|----------|-----------|-------------|
| `argocd_enabled` | Habilitar ArgoCD | Sim (se usar ArgoCD) |
| `argocd_url` | URL do ArgoCD | Sim (se habilitado) |
| `argocd_token` | Token de autenticação | Sim (se habilitado) |

### Obter Token ArgoCD

```bash
# Criar conta de serviço
argocd account generate-token --account worker-agents
```

### Secret Kubernetes

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: worker-agents-argocd-secrets
  namespace: neural-hive-execution
type: Opaque
stringData:
  argocd_token: "eyJhbGc..."
```

## Configuração Flux CD (Worker Agents)

### Variáveis de Ambiente

| Variável | Descrição | Obrigatório |
|----------|-----------|-------------|
| `flux_enabled` | Habilitar Flux | Sim (se usar Flux) |
| `flux_kubeconfig_path` | Caminho do kubeconfig | Sim (se habilitado) |
| `flux_namespace` | Namespace do Flux | Não (default: flux-system) |

### Montar Kubeconfig

```yaml
# deployment.yaml
spec:
  template:
    spec:
      volumes:
        - name: kubeconfig
          secret:
            secretName: flux-kubeconfig
      containers:
        - name: worker-agents
          volumeMounts:
            - name: kubeconfig
              mountPath: /etc/kubeconfig
              readOnly: true
```

## Validação de Configuração

Execute o script de validação para verificar todas as configurações:

```bash
bash scripts/validation/validate-phase2-config.sh
```

### Opções do Script

| Flag | Descrição |
|------|-----------|
| `--namespace <ns>` | Namespace para validação |
| `--skip-opa` | Pular validação OPA |
| `--skip-argocd` | Pular validação ArgoCD |
| `--skip-tests` | Pular execução de testes |

### Relatórios

Os relatórios são salvos em:
- JSON: `/tmp/neural-hive-validation-reports/validate-phase2-config_*.json`
- HTML: `/tmp/neural-hive-validation-reports/validate-phase2-config_*.html`

## Troubleshooting

### LLM API Key Inválida

```bash
# Verificar logs do Code Forge
kubectl logs -n neural-hive-execution -l app.kubernetes.io/name=code-forge | grep -i "401\|unauthorized"
```

**Solução**: Verifique se a API key está correta e tem permissões suficientes.

### ArgoCD Inacessível

```bash
# Testar conectividade
curl -I https://argocd.example.com/api/version
```

**Solução**: Verifique firewall, NetworkPolicy, e se o ArgoCD está running.

### Flux Kubeconfig Inválido

```bash
# Verificar kubeconfig montado
kubectl exec -n neural-hive-execution deployment/worker-agents -- cat /etc/kubeconfig/config
```

**Solução**: Verifique permissões RBAC e contexto do kubeconfig.

### Testes Unitários Falhando

```bash
# Executar testes localmente
cd services/orchestrator-dynamic
python -m pytest tests/unit/activities/ -v --tb=long
```

**Solução**: Verifique dependências e mocks nos testes.
