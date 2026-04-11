# Gatekeeper Troubleshooting Runbook

## Common Issues

### Deployment blocked by policy
**Symptom:** kubectl apply fails with "admission webhook denied the request"

**Diagnosis:**
```bash
kubectl describe deployment <NAME> -n <NAMESPACE>
kubectl get violations -n <NAMESPACE>
```

**Solution:**
1. Verificar quais labels/faltam
2. Adicionar labels ao recurso
3. Ou criar exemption se necessário

### Webhook timeout
**Symptom:** "Timeout waiting for webhook" errors

**Diagnosis:**
```bash
kubectl get pods -n gatekeeper-system
kubectl logs -n gatekeeper-system -l control-plane=controller-manager
```

**Solution:**
- Verificar resource limits
- Aumentar réplicas se necessário
- Verificar OPA queries estão otimizadas

### Constraint not evaluating
**Symptom:** Constraint criado mas não bloqueia recursos

**Diagnosis:**
```bash
kubectl get constrainttemplates
kubectl get constraints -A
```

**Solution:**
- Verificar match criteria do constraint
- Verificar se namespace está incluído
- Verificar se kind está correto