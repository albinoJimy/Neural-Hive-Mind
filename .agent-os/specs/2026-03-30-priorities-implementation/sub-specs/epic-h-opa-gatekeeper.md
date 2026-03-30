# Sub-Spec: Epic H - OPA Gatekeeper Webhook

## Objetivo

Configurar OPA Gatekeeper com webhook de admission para activar 17 policies de segurança no cluster Kubernetes.

## Componentes

### 1. OPA Gatekeeper Configuration (NOVO)
**Arquivo:** `k8s/opa-gatekeeper/config.yaml`

**Funcionalidades:**
- Webhook de admission configurado
- Policies de OPA aplicadas
- Validations e Mutations activadas

```yaml
apiVersion: config.gatekeeper.sh/v1alpha1
kind: Config
metadata:
  name: config
namespace: gatekeeper-system
spec:
  # Sync configs
  sync:
    syncOnly:
      - group: ""
        kind: Namespace
    - group: neural-hive.com
        kind: "*"

  # Validation configs
  validate:
    - extractors: []
      match:
        kinds:
          - apiGroups: [""]
            kinds: ["Pod"]
      validators:
        - name: require-security-context.neural-hive
        - name: require-resource-limits.neural-hive
        - name: disallow-privileged.neural-hive

  # Mutation configs
  mutate:
    - extractors: []
      match:
        kinds:
          - apiGroups: [""]
            kinds: ["Pod"]
      mutators:
        - name: add-default-labels.neural-hive
        - name: set-resource-requests.neural-hive
```

### 2. ValidatingWebhookConfiguration (NOVO)
**Arquivo:** `k8s/opa-gatekeeper/validating-webhook.yaml`

**Funcionalidades:**
- Webhook de admission para pods
- Validar configurations antes de aplicar
- Bloquear violações de segurança

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingWebhookConfiguration
metadata:
  name: gatekeeper-validating-webhook-configuration
spec:
  sideEffects: None
  admissionReviewVersions: ["v1"]
  matchPolicy: Equivalent
  rules:
    - operations: ["CREATE", "UPDATE"]
      apiGroups: [""]
      apiVersions: ["v1"]
      resources: ["pods"]
      operations: ["CREATE", "UPDATE"]
  namespaceSelector:
    matchExpressions:
      - key: kubernetes.io/metadata.name
        operator: NotIn
        values: ["kube-system", "gatekeeper-system"]
  failurePolicy: Fail
  timeoutSeconds: 5
  clientConfig:
    service:
      namespace: gatekeeper-system
      name: gatekeeper-webhook-service
      path: /v1/admit
```

### 3. Testes de OPA Policies (NOVO)
**Diretório:** `opa/policies/test/`

**Policies a testar:**
1. oauth2-token-required.rego
2. mesh-mtls-required.rego
3. redis-security-required.rego
4. ethical_guardrails.rego
5. pod-security-policy.rego
6. resource-limits.rego
7. image-policy.rego
8. namespace-labels.rego
9. ingress-tls.rego
10. storage-encryption.rego
11. secret-encryption.rego
12. network-policy.rego
13. rbac-restrictions.rego
14. container-runtime.rego
15. cpu-limit.rego
16. memory-limit.rego
17. audit-logging.rego

**Framework de teste:** OPA test framework

```bash
# Instalar OPA
brew install opa

# Executar testes
opa test opa/policies/ opa/policies/test/*.rego

# Verificar coverage
opa test opa/policies/ --coverage
```

**Exemplo de teste:**
```rego
# oauth2-token-required.rego
package oauth2

default allow = false

allow {
    input.request.kind.kind == "Pod"
    input.request.operation in ["CREATE", "UPDATE"]
    has_oauth2_token(input.request.object)
}

has_oauth2_token(pod) {
    pod.spec.containers[_].env[_].name == "OAUTH2_TOKEN"
}
```

```rego
# test/oauth2-token-required_test.rego
package oauth2

test_oauth_token_required {
    inputs = [
        {
            "request": {
                "kind": {"kind": "Pod"},
                "operation": "CREATE"
            },
            "object": {
                "spec": {
                    "containers": [
                        {"name": "app", "env": []}
                    ]
                }
            }
        }
    }
  ]
    result = deny with input.errors
    expected = "OAuth2 token required"
}

test_oauth_token_present {
    inputs = [
        {
            "request": {
                "kind": {"kind": "Pod"},
                "operation": "CREATE"
            },
            "object": {
                "spec": {
                    "containers": [
                        {"name": "app", "env": [
                            {"name": "OAUTH2_TOKEN", "value": "token"}
                        ]}
                    ]
                }
            }
        }
    }
    ]
    result = allow
}
```

## Verificação

```bash
# Verificar Gatekeeper instalado
kubectl get pods -n gatekeeper-system

# Verificar configs
kubectl get config -n gatekeeper-system

# Verificar webhooks
kubectl get validatingwebhookconfiguration

# Testar violação de policy (deve ser bloqueado)
kubectl run nginx --image=nginx --limits=cpu=100m --requests=cpu=200m
# Deve ser bloqueado (requests > limits)

# Testar pod válido (deve ser criado)
kubectl run nginx --image=nginx --limits=cpu=200m --requests=cpu=100m
# Deve ser criado com sucesso

# Verificar logs do Gatekeeper
kubectl logs -n gatekeeper-system -l gatekeeper-controller
```

## Deploy

```bash
# Instalar Gatekeeper
kubectl apply -f https://raw.githubusercontent.com/open-policy-agent/gatekeeper/release-v3.13.0/deploy/gatekeeper.yaml

# Aplicar configs
kubectl apply -f k8s/opa-gatekeeper/config.yaml
kubectl apply -f k8s/opa-gatekeeper/validating-webhook.yaml

# Sincronizar policies
kubectl apply -f opa/policies/*.rego
```

## Rollback

```bash
# Se algo der errado
kubectl delete -f k8s/opa-gatekeeper/validating-webhook.yaml
kubectl delete -f k8s/opa-gatekeeper/config.yaml

# Ou desactivar temporariamente
kubectl label ns gatekeeper-system admission.gatekeeper.sh/ignore=no-watches
```
