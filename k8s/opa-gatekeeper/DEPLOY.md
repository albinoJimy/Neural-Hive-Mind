# OPA Gatekeeper - Deploy Guide

Epic H - OPA Gatekeeper Webhook Configuration

## Overview

Este documento descreve como fazer deploy do OPA Gatekeeper com 17 políticas de segurança configuradas para o Neural Hive-Mind.

## Pré-requisitos

1. **Kubernetes Cluster** v1.25+
2. **kubectl** configurado
3. **OPA Gatekeeper** instalado (ou usar Helm chart incluído)

## Instalação do Gatekeeper

### Opção 1: Usar o manifesto oficial

```bash
kubectl apply -f https://raw.githubusercontent.com/open-policy-agent/gatekeeper/release-3.16/deploy/gatekeeper.yaml
```

### Opção 2: Usar Helm

```bash
helm repo add gatekeeper https://open-policy-agent.github.io/gatekeeper/charts
helm install gatekeeper gatekeeper/gatekeeper -n gatekeeper-system --create-namespace
```

## Deploy das Políticas

### 1. Aplicar configuração e templates

```bash
# Aplicar config.yaml (ConstraintTemplates + Constraints)
kubectl apply -f k8s/opa-gatekeeper/config.yaml
```

### 2. Aplicar webhook de admission

```bash
# Aplicar validating-webhook.yaml
kubectl apply -f k8s/opa-gatekeeper/validating-webhook.yaml
```

## Verificação do Deploy

### Verificar ConstraintTemplates

```bash
kubectl get constrainttemplates -n gatekeeper-system
```

Saída esperada:
```
NAME                               AGE
auditlogging                       1m
containerruntime                   1m
cpulimit                           1m
ethicalguardrails                  1m
imagepolicy                        1m
ingresstls                         1m
memorylimit                        1m
meshmtlsrequired                    1m
namespacelabels                    1m
networkpolicy                      1m
oauth2tokenrequired                1m
podsecuritypolicy                  1m
redissecurityrequired              1m
resourceconstraints                1m
rbacrestrictions                   1m
secretencryption                   1m
storageencryption                  1m
```

### Verificar Constraints

```bash
kubectl get constraints -A
```

### Verificar Webhooks

```bash
kubectl get validatingwebhookconfiguration
kubectl get mutatingwebhookconfiguration
```

## Testar as Políticas

### Testar OAuth2 Token Required

```bash
# Deve ser rejeitado
kubectl create service clusterip test-service --tcp=80:80 -n production

# Deve ser aceito
kubectl create service clusterip test-service \
  --tcp=80:80 \
  -n production \
  --dry-run=client \
  -o yaml | \
  kubectl apply -f - -n production
```

### Testar Resource Limits

```bash
# Criar pod sem resource limits - deve ser rejeitado
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
  namespace: production
spec:
  containers:
  - name: main
    image: nginx:alpine
EOF
```

## Monitoramento

### Ver violações em tempo real

```bash
kubectl get k8sdenys gatekeeper-system -w
```

### Ver logs do Gatekeeper

```bash
kubectl logs -n gatekeeper-system -l control-plane=controller-manager -f
```

## Troubleshooting

### Recursos são rejeitados inesperadamente

1. Ver qual constraint está bloqueando:
   ```bash
   kubectl describe k8sdeny <deny-name> -n gatekeeper-system
   ```

2. Ver mensagens de violação:
   ```bash
   kubectl get k8sdenys -n gatekeeper-system -o yaml
   ```

### Webhook timeout

Aumentar timeout em `validating-webhook.yaml`:
```yaml
timeoutSeconds: 30  # aumentar para 60 se necessário
```

### Excluir namespace temporariamente

Adicionar namespace a `excludedNamespaces` nas constraints.

## Personalização

### Modificar parâmetros das constraints

Editar `config.yaml` e mudar valores em `parameters`:
```yaml
spec:
  parameters:
    max_cpu: "8"        # aumentar de 4 para 8
    max_memory: "16Gi"  # aumentar de 8Gi para 16Gi
```

### Adicionar novos registries permitidos

Editar `imagepolicy-constraint`:
```yaml
parameters:
  allowed_registries:
    - "ghcr.io/albinojimy/"
    - "docker.io/neuralhive/"
    - "gcr.io/distroless/"
    - "seu-registry.com/"
```

### Desabilitar uma constraint

Mudar `enforcementAction`:
```yaml
spec:
  enforcementAction: warn  # ou dryrun
```

## Referências

- [OPA Gatekeeper Documentation](https://open-policy-agent.github.io/gatekeeper/)
- [Constraint Templates](https://open-policy-agent.github.io/gatekeeper/docs/howto/)
- [Audit](https://open-policy-agent.github.io/gatekeeper/docs/audit/)

## Notas de Produção

1. **Performance**: O Gatekeeper adiciona latência de ~100-200ms por request
2. **Timeouts**: Aumentar timeout se políticas forem complexas
3. **Cache**: O Gatekeeper cacheia resultados de políticas
4. **Audit**: Executa periodicamente para verificar recursos existentes
5. **Mutating**: Webhook de mutação pode injetar labels automaticamente

## Rollback

```bash
# Remover constraints
kubectl delete -f k8s/opa-gatekeeper/config.yaml

# Remover webhooks
kubectl delete -f k8s/opa-gatekeeper/validating-webhook.yaml

# Desinstalar Gatekeeper
helm uninstall gatekeeper -n gatekeeper-system
# ou
kubectl delete -f https://raw.githubusercontent.com/open-policy-agent/gatekeeper/release-3.16/deploy/gatekeeper.yaml
```
