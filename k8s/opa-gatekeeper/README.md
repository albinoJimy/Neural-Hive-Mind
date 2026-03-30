# OPA Gatekeeper - Neural Hive-Mind

Epic H - OPA Gatekeeper Webhook Configuration

## Visão Geral

Este diretório contém a configuração do OPA Gatekeeper com 17 políticas de segurança para o Neural Hive-Mind. As políticas são aplicadas via admission webhook antes da criação/atualização de recursos no cluster Kubernetes.

## Arquivos

| Arquivo | Descrição |
|---------|-----------|
| `config.yaml` | ConstraintTemplates e Constraints para 17 políticas |
| `validating-webhook.yaml` | Configuração do admission webhook |
| `DEPLOY.md` | Guia completo de deploy |
| `run-tests.sh` | Script para executar testes OPA |
| `README.md` | Este arquivo |

## 17 Políticas de Segurança

| # | Política | Descrição | Ticket |
|---|----------|-----------|--------|
| 1 | **OAuth2 Token Required** | Exige autenticação OAuth2 para serviços críticos | H001-01 |
| 2 | **Mesh mTLS Required** | Exige mTLS STRICT para workloads no service mesh | H001-02 |
| 3 | **Redis Security Required** | Exige configurações de segurança para Redis clusters | H001-03 |
| 4 | **Ethical Guardrails** | Aplica guardrails éticos para decisões críticas | H001-04 |
| 5 | **Pod Security Policy** | Aplica políticas de segurança para pods (baseline) | H001-05 |
| 6 | **Resource Limits** | Exige resource limits e requests para containers | H001-06 |
| 7 | **Image Policy** | Controla imagens de container permitidas | H001-07 |
| 8 | **Namespace Labels** | Exige labels obrigatórios em namespaces | H001-08 |
| 9 | **Ingress TLS** | Exige TLS em ingresses para produção | H001-09 |
| 10 | **Storage Encryption** | Exige criptografia para PVCs em produção | H001-10 |
| 11 | **Secret Encryption** | Exige ExternalSecrets para secrets em produção | H001-11 |
| 12 | **Network Policy** | Exige NetworkPolicy para workloads críticos | H001-12 |
| 13 | **RBAC Restrictions** | Restringe role bindings permissivas | H001-13 |
| 14 | **Container Runtime** | Restringe configurações de runtime de container | H001-14 |
| 15 | **CPU Limit** | Limita o máximo de CPU por container | H001-15 |
| 16 | **Memory Limit** | Limita o máximo de memória por container | H001-16 |
| 17 | **Audit Logging** | Exige configuração de audit logging | H001-17 |

## Deploy Rápido

```bash
# 1. Instalar Gatekeeper
kubectl apply -f https://raw.githubusercontent.com/open-policy-agent/gatekeeper/release-3.16/deploy/gatekeeper.yaml

# 2. Aplicar políticas
kubectl apply -f k8s/opa-gatekeeper/config.yaml

# 3. Aplicar webhooks
kubectl apply -f k8s/opa-gatekeeper/validating-webhook.yaml
```

## Testes

```bash
# Executar todos os testes
./k8s/opa-gatekeeper/run-tests.sh
```

Ou manualmente:
```bash
opa test policies/rego/gatekeeper/tests/ -v
```

## Estrutura das Políticas

### ConstraintTemplates

Definem a estrutura e lógica das políticas em Rego:

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: minhapolitica
spec:
  crd:
    spec:
      names:
        kind: MinhaPolitica
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package minhapolitica
        violation[{"msg": msg}] {
          # lógica aqui
        }
```

### Constraints

Instâncias das templates com parâmetros:

```yaml
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: MinhaPolitica
metadata:
  name: minhapolitica-constraint
spec:
  enforcementAction: deny  # ou warn, dryrun
  match:
    kinds:
      - apiGroups: [""]
        kinds: ["Pod"]
  parameters:
    # parâmetros da template
```

## Parâmetros Configuráveis

### OAuth2 Token Required
- `oauth2_required_services`: Lista de serviços que requerem OAuth2

### Mesh mTLS Required
- `excluded_namespaces`: Namespaces excluídos da verificação mTLS

### Ethical Guardrails
- `max_risk_score`: Score máximo permitido (default: 0.9)
- `min_confidence_for_critical`: Confiança mínima para decisões críticas (default: 0.7)

### Pod Security Policy
- `allowPrivileged`: Permitir containers privilegiados (default: false)
- `allowHostNetwork`: Permitir hostNetwork (default: false)
- `allowHostPID`: Permitir hostPID (default: false)
- `allowHostIPC`: Permitir hostIPC (default: false)

### Resource Limits
- `max_cpu`: CPU máxima permitida (default: "4")
- `max_memory`: Memória máxima permitida (default: "8Gi")

### Image Policy
- `allowed_registries`: Lista de registries permitidos
- `require_signature`: Exibir assinatura de imagem (default: false)
- `allow_latest_tag`: Permitir tag :latest (default: false)

### Ingress TLS
- `require_in_prod`: Exigir TLS em produção (default: true)
- `excluded_namespaces`: Namespaces excluídos

### Network Policy
- `require_for_namespaces`: Namespaces que requerem NetworkPolicy
- `excluded_workloads`: Workloads excluídos

### RBAC Restrictions
- `forbidden_roles`: Roles proibidas (cluster-admin, admin, edit)
- `allowed_subjects`: Subjects permitidos para roles perigosas

### Container Runtime
- `allow_capabilities_add`: Capabilities permitidas
- `require_read_only_root`: Exigir root filesystem read-only
- `require_drop_all`: Exigir drop de ALL capabilities

## Modos de Enforcement

| Modo | Comportamento |
|------|---------------|
| `deny` | Bloqueia recursos que violam (padrão) |
| `warn` | Avisa mas não bloqueia |
| `dryrun` | Registra violações mas não bloqueia |

## Namespaces Excluídos

Por padrão, os seguintes namespaces são excluídos da validação:
- `kube-system`
- `kube-public`
- `kube-node-lease`
- `gatekeeper-system`
- `istio-system`

## Troubleshooting

### Ver violações
```bash
kubectl get k8sdenys -n gatekeeper-system
```

### Ver logs
```bash
kubectl logs -n gatekeeper-system -l control-plane=controller-manager -f
```

### Testar política específica
```bash
opa test policies/rego/gatekeeper/tests/nome_da_politica_test.rego -v
```

## Documentação Adicional

- [DEPLOY.md](./DEPLOY.md) - Guia completo de deploy
- [OPA Documentation](https://www.openpolicyagent.org/docs/latest/)
- [Gatekeeper Documentation](https://open-policy-agent.github.io/gatekeeper/)

## Epic H - Tickets

- **H001**: OPA Gatekeeper Configuration
- **H002**: ValidatingWebhookConfiguration
- **H003**: Testes de OPA Policies

## Status

| Status | Políticas |
|--------|-----------|
| Configuradas | 17/17 |
| Testadas | 17/17 |
| Documentadas | 17/17 |
