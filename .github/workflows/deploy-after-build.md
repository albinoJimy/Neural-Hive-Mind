# Workflow: Deploy After Build

## Visão Geral

Este workflow GitHub Actions automatiza o processo de deployment de serviços no Kubernetes após a conclusão de um build. Ele atualiza as tags das imagens Docker nos arquivos de configuração do Helm e executa o deploy usando Helm charts.

## Arquivo

`.github/workflows/deploy-after-build.yml`

---

## Gatilho (Trigger)

O workflow é disparado manualmente via `workflow_dispatch`, podendo ser chamado por:
- Outros workflows (como o workflow de build)
- Intervenção manual através da interface do GitHub Actions

---

## Parâmetros de Entrada (Inputs)

| Parâmetro | Tipo | Obrigatório | Padrão | Descrição |
|-----------|------|-------------|--------|-----------|
| `environment` | choice | Sim | `staging` | Ambiente de deployment: `development`, `staging` ou `production` |
| `services` | string | Sim | - | Lista de serviços para deploy, separados por vírgula (ex: `gateway,api,worker`) |
| `image_tag` | string | Sim | - | Tag da imagem Docker (SHA, versão semver ou `latest`) |
| `dry_run` | boolean | Não | `false` | Simula o deployment sem aplicar mudanças reais |

---

## Variáveis de Ambiente

```yaml
REGISTRY: ghcr.io                    # Registro de container (GitHub Container Registry)
IMAGE_PREFIX: albinojimy/neural-hive-mind  # Prefixo das imagens
```

---

## Estrutura dos Jobs

### Job 1: Preparar Deployment (`prepare`)

**Objetivo:** Validação e preparação inicial do deployment.

**Executa em:** `self-hosted`

**Outputs:**
- `environment`: Ambiente selecionado
- `services`: Lista de serviços (string)
- `services_list`: Lista de serviços (JSON array)
- `image_tag`: Tag da imagem
- `should_deploy`: Flag indicando se o deploy deve prosseguir (`true`/`false`)

**Passos:**
1. **Checkout** - Faz checkout do código
2. **Parsear lista de serviços** - Converte string de serviços em array JSON usando `jq`
3. **Validar pré-requisitos**:
   - Verifica se está em modo dry-run
   - Valida se há serviços especificados
4. **Gerar resumo** - Cria sumário markdown no GitHub Actions

**Lógica de Validação:**
- Se `dry_run=true`: define `should_deploy=false` (apenas simulação)
- Se `services` estiver vazio: define `should_deploy=false`

---

### Job 2: Atualizar Tags (`update-values`)

**Objetivo:** Atualiza as tags das imagens nos arquivos de valores do Helm.

**Dependência:** `prepare` (deve ter `should_deploy=true`)

**Estratégia:** Matrix build com `fail-fast: false` (todos os serviços tentam executar, mesmo que um falhe)

**Serviços:** Lista dinâmica baseada no input `services`

**Passos:**
1. **Checkout** do código
2. **Atualizar tag da imagem**:
   - Identifica arquivos de valores:
     - Arquivo base: `helm-charts/{servico}/values.yaml`
     - Arquivo de ambiente:
       - Produção: `environments/prod/helm-values/{servico}-values.yaml`
       - Staging: `environments/staging/helm-values/{servico}-values.yaml`
   - Atualiza a tag usando `sed`
   - Modo dry-run apenas mostra o que seria alterado

---

### Job 3: Deploy via Helm (`deploy`)

**Objetivo:** Executa o deployment real no cluster Kubernetes usando Helm.

**Dependências:** `prepare` e `update-values`

**Condição:** Apenas executa se `should_deploy=true` e não está em dry-run

**Proteção de Ambiente:** Requer aprovação para deployment em `production`

**Estratégia:** Matrix build com:
- `fail-fast: false`: Todos os serviços tentam executar
- `max-parallel: 3`: Máximo de 3 deploys simultâneos

**Passos:**

1. **Checkout** do código

2. **Configurar kubeconfig**:
   - Decodifica base64 do secret `KUBECONFIG`
   - Salva em `~/.kube/config`

3. **Instalar ferramentas**:
   - Helm v3.14.0
   - kubectl v1.29.0

4. **Determinar namespace**:
   | Ambiente | Namespace |
   |----------|-----------|
   | production | `neural-hive` |
   | staging | `neural-hive-staging` |
   | development | `neural-hive-dev` |

5. **Adicionar repositórios Helm**:
   - `bitnami` (dependências comuns)
   - Repositório local de templates

6. **Atualizar dependências**:
   - Executa `helm dependency update` e `build` no chart do serviço

7. **Deploy com Helm**:
   - Comando: `helm upgrade --install`
   - Argumentos:
     - `--atomic`: Rollback automático em caso de falha
     - `--cleanup-on-fail`: Limpa recursos em caso de falha
     - `--wait`: Aguarda recursos estarem prontos
     - `--timeout 10m`: Timeout de 10 minutos
     - `--set image.tag={tag}`: Define a tag da imagem
     - `--set image.repository={registry}/{prefix}/{servico}`: Define o repositório
   - Valida existência do chart
   - Inclui arquivo de valores específico do ambiente se existir

8. **Verificar rollout**:
   - Aguarda rollout do deployment com timeout de 5 minutos

9. **Verificar health**:
   - Lista pods do serviço para verificação visual

---

### Job 4: Resumo do Deployment (`summary`)

**Objetivo:** Gera resumo final do deployment.

**Dependências:** Todos os jobs anteriores (`prepare`, `update-values`, `deploy`)

**Condição:** Sempre executa (`always()`), mesmo se jobs anteriores falharem

**Passos:**
1. **Gerar resumo em markdown**:
   - Exibe ambiente, tag e serviços
   - Status: ✅ Sucesso / ⏭️ Pulado / ❌ Falha
   - Instruções de próximos passos (comandos kubectl)

2. **Notificar resultado**:
   - Log do resultado final

---

## Fluxo de Execução

```
┌─────────────┐
│   prepare   │
│  (validação)│
└──────┬──────┘
       │ should_deploy=true?
       ▼
┌─────────────┐     ┌─────────────┐
│ update-values│────▶│   deploy    │
│(atualiza tags)│     │ (helm/k8s)  │
└─────────────┘     └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   summary   │
                    │  (resumo)   │
                    └─────────────┘
```

---

## Estrutura de Arquivos Esperada

```
helm-charts/
├── {servico}/
│   ├── Chart.yaml
│   ├── values.yaml              # Arquivo base
│   └── templates/
│       └── ...
└── common-templates/            # Templates compartilhados

environments/
├── prod/
│   └── helm-values/
│       └── {servico}-values.yaml
├── staging/
│   └── helm-values/
│       └── {servico}-values.yaml
└── dev/
    └── helm-values/
        └── {servico}-values.yaml
```

---

## Exemplos de Uso

### Exemplo 1: Deploy de múltiplos serviços em staging

```yaml
# Chamada manual via GitHub UI ou API
{
  "environment": "staging",
  "services": "gateway,api-service,worker-service",
  "image_tag": "v1.2.3",
  "dry_run": false
}
```

### Exemplo 2: Simulação de deploy (dry-run)

```yaml
{
  "environment": "production",
  "services": "api-service",
  "image_tag": "abc123def",
  "dry_run": true
}
```

### Exemplo 3: Chamada via workflow de build

```yaml
jobs:
  trigger-deploy:
    needs: build-and-push
    uses: ./.github/workflows/deploy-after-build.yml
    with:
      environment: staging
      services: ${{ needs.build-and-push.outputs.changed_services }}
      image_tag: ${{ github.sha }}
```

---

## Segurança

### Proteções Implementadas

1. **Aprovação para Produção**: Job `deploy` usa `environment: production` que requer aprovação manual
2. **Simulação (dry-run)**: Permite validar alterações antes do deploy real
3. **Validação de Inputs**: Job `prepare` valida todos os parâmetros
4. **Atomic Deployments**: Flag `--atomic` garante rollback automático em caso de falha
5. **Kubeconfig**: Usa secrets GitHub para armazenar credenciais do cluster

### Secrets Necessários

| Secret | Descrição |
|--------|-----------|
| `KUBECONFIG` | Configuração do Kubernetes em base64 (contém credenciais do cluster) |

---

## Troubleshooting

### Problema: Chart não encontrado

**Sintoma:** `❌ Chart não encontrado: helm-charts/{servico}`

**Solução:**
- Verificar se o diretório `helm-charts/{servico}/` existe
- Verificar se `Chart.yaml` está presente no diretório

### Problema: Falha no rollout

**Sintoma:** Pods não iniciam ou ficam em `CrashLoopBackOff`

**Comandos de diagnóstico:**
```bash
# Verificar pods
kubectl get pods -n neural-hive -l app.kubernetes.io/name={servico}

# Ver logs
kubectl logs -n neural-hive -l app.kubernetes.io/name={servico} -f

# Descrever pod
kubectl describe pod -n neural-hive {nome-do-pod}
```

### Problema: Tag não atualizada

**Sintoma:** Deploy usa tag antiga

**Verificação:**
```bash
# Verificar valores atuais
helm get values {servico} -n neural-hive

# Verificar template renderizado
helm template {servico} helm-charts/{servico} -f environments/prod/helm-values/{servico}-values.yaml
```

---

## Manutenção

### Atualizar Versões das Ferramentas

Linhas que podem precisar de atualização:
- Helm: Linha 206 (`version: 'v3.14.0'`)
- kubectl: Linha 211 (`version: 'v1.29.0'`)

### Adicionar Novo Ambiente

Para adicionar um novo ambiente (ex: `qa`):

1. Adicionar opção no input `environment` (linha 12-14)
2. Adicionar case no job `update-values` (linha 130-139)
3. Adicionar case no job `deploy` para namespace (linha 217-227)
4. Adicionar case no job `deploy` para arquivo de valores (linha 272-281)

---

## Notas de Implementação

- O workflow usa `self-hosted` runners, exigindo runners configurados no repositório
- O parsing de serviços usa `jq` para manipulação segura de JSON
- Atualização de tags usa `sed` para compatibilidade máxima
- Timeouts configurados: 10 minutos para helm, 5 minutos para rollout
