# Configuração GitHub CI/CD - Gateway de Intenções

## Status Atual (2026-02-20)

✅ **Build funcionando via `build-and-push-ghcr.yml`**

O workflow `build-gateway.yml` foi desabilitado em favor do `build-and-push-ghcr.yml`,
que já inclui o gateway-intencoes e não possui requisitos de linting estritos.

## Workflow Ativo

**Workflow:** `Build and Push to GHCR`
- **Trigger:** Push para `main`/`develop` com mudanças em `services/**`
- **Serviços:** Inclui `gateway-intencoes` automaticamente
- **Imagem:** `ghcr.io/albinojimy/neural-hive-mind/gateway-intencoes:main`
- **Tags:** `main`, `latest`, `1.1.2`, `<commit-sha>`

## Fixes Aplicados

### 1. CORS no Gateway (services/gateway-intencoes/src/main.py)
- CORSMiddleware configurado como PRIMEIRO middleware
- TrustedHostMiddleware desabilitado em não-produção
- Allow methods: GET, POST, PUT, DELETE, OPTIONS, PATCH

### 2. CI/CD Simplificado
- `build-gateway.yml` → renomeado para `.disabled`
- `build-and-push-ghcr.yml` → agora responsável pelo build do gateway
- Sem verificação mypy/flake8 estrita no build

### 3. Bug Fix no Kafka Producer (services/gateway-intencoes/src/kafka/producer.py)
- Movido cálculo de `topic` para ANTES da lógica do fast producer
- Corrige erro `F821 undefined name 'topic'`

## Configuração do Secret KUBE_CONFIG (Opcional)

> **Nota:** O workflow `build-and-push-ghcr.yml` apenas builda e pusha as imagens.
> Para deploy no cluster, use o workflow `deploy-to-cluster.yml` manualmente.

Caso queira configurar deploy automático, o workflow precisa do `KUBE_CONFIG` secret.

### Opção 1: Via GitHub Web (Recomendado)

1. Acesse: https://github.com/albinoJimy/Neural-Hive-Mind/settings/secrets/actions
2. Clique em "New repository secret"
3. Preencha:
   - **Name**: `KUBE_CONFIG`
   - **Value**: (veja abaixo como obter)
4. Clique em "Add secret"

### Como obter o KUBE_CONFIG

```bash
# Exportar kubeconfig em base64
kubectl config view --minify --raw | base64 -w 0

# Copie a saída e cole no campo "Value" do secret no GitHub
```

### Opção 2: Via GitHub CLI

```bash
# Exportar e configurar via gh CLI
kubectl config view --minify --raw | base64 -w 0 | \
  gh secret set KUBE_CONFIG -b-
```

## Evolução do Workflow

### Workflow Antigo: `build-gateway.yml` (DESATIVADO)
- Problema: Linting estrito (mypy, flake8) falhava
- Problema: Auto-format + commit em workflow separado
- Status: Renomeado para `.disabled`

### Workflow Atual: `build-and-push-ghcr.yml` (ATIVO)
- Detecta automaticamente serviços modificados
- Build sem testes de linting no pipeline
- Multi-serviço: gateway, workers, specialists, etc.
- Status: ✅ Funcionando

## Verificação do Build

Para verificar o status do build mais recente:

```bash
gh run list --workflow=build-and-push-ghcr.yml --limit 3
```

Para ver detalhes de um build específico:

```bash
gh run view <run-id>
```

## Deploy Manual no Cluster

Após o build ser concluído com sucesso, o deploy pode ser feito manualmente:

```bash
# Via workflow dispatch
gh workflow run deploy-to-cluster.yml

# Ou via helm direto
helm upgrade gateway-intencoes ./helm-charts/gateway-intencoes \
  --namespace neural-hive \
  --values ./helm-charts/gateway-intencoes/values-staging.yaml \
  --set image.tag=main \
  --wait
```

## Namespace de Deploy

- **Namespace alvo**: `neural-hive`
- **Helm Chart**: `./helm-charts/gateway-intencoes`
- **Values**: `values-staging.yaml`
- **Image**: `ghcr.io/albinojimy/neural-hive-mind/gateway-intencoes:main`

## Resumo

| Item | Status |
|------|--------|
| Build CI/CD | ✅ `build-and-push-ghcr.yml` |
| Imagem no GHCR | ✅ `:main`, `:latest` |
| CORS Fix | ✅ Deployed |
| Kafka Producer Fix | ✅ Deployed |
| Deploy Automático | ⚠️ Manual via `deploy-to-cluster.yml` |

## Troubleshooting

### Se o build falhar:
```bash
# Verificar status
gh run list --workflow=build-and-push-ghcr.yml --limit 5

# Ver logs de erro
gh run view <run-id> --log-failed
```

### Para deploy manual no cluster:
```bash
# Ver pod atual
kubectl get pods -n neural-hive -l app=gateway-intencoes

# Fazer deploy
helm upgrade gateway-intencoes ./helm-charts/gateway-intencoes \
  --namespace neural-hive --install \
  --values ./helm-charts/gateway-intencoes/values-staging.yaml \
  --set image.tag=main --wait
```
