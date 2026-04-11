# Gatekeeper Enforcement Runbook

## Overview
Runbook para ativar e gerir enforcement de policies OPA Gatekeeper no Neural-Hive-Mind.

## Prerequisites
- Gatekeeper instalado em audit mode
- Constraint templates criados
- Violations analisadas e corrigidas

## Activation Steps

1. **Analisar violations atuais**
```bash
./scripts/gatekeeper-analyze-violations.sh
```

2. **Corrigir violations críticas**
```bash
./scripts/gatekeeper-fix-violations.sh neural-hive
```

3. **Ativar enforcement mode**
```bash
./scripts/gatekeeper-enable-enforcement.sh
```

4. **Testar enforcement**
```bash
# Tentar criar recurso inválido (deve falhar)
kubectl run test-pod --image=nginx -n neural-hive

# Tentar criar recurso válido (deve funcionar)
kubectl run test-pod-valid --image=nginx -n neural-hive \
  --labels=app=test,part-of=neural-hive-mind,version=v1
```

## Rollback
Se enforcement causar problemas:
```bash
helm upgrade gatekeeper helm/gatekeeper \
  --namespace gatekeeper-system \
  --values helm/gatekeeper/values.yaml
```

## Adding Exemptions

Para exemptions temporárias:
```yaml
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sRequiredLabels
metadata:
  name: exempt-namespace
spec:
  match:
    kinds:
      - apiGroups: [""]
        kinds: ["Pod"]
    namespaces: ["exempt-namespace"]
    excludedNamespaces: ["kube-system", "gatekeeper-system"]
```