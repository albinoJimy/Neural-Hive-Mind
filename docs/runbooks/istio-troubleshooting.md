# Istio Troubleshooting Runbook

## Common Issues

### Pods not starting with sidecar
**Symptom:** Pod stuck in ContainerCreating or CrashLoopBackOff

**Diagnosis:**
```bash
kubectl get pod <POD> -n <NAMESPACE> -o yaml | grep -A 5 "istio-proxy"
kubectl logs <POD> -c istio-proxy -n <NAMESPACE>
```

**Solution:**
- Verificar istiod está running: `kubectl get pods -n istio-system`
- Verificar webhook configuration: `kubectl get validatingwebhookconfiguration`
- Restart pod: `kubectl delete pod <POD> -n <NAMESPACE>`

### mTLS connection errors
**Symptom:** 503 errors between services

**Diagnosis:**
```bash
kubectl get peerauthentication -A
istioctl authn tls-check <SERVICE> -n <NAMESPACE>
```

**Solution:**
- Verificar PeerAuthentication está STRICT/PERMISSIVE correto
- Verificar ambos serviços têm sidecar injetado
- Temporariamente usar PERMISSIVE para debugging

### High latency after Istio install
**Symptom:** Requests slower than before

**Diagnosis:**
```bash
istioctl proxy-config endpoints <POD> -n <NAMESPACE>
kubectl top pods -n <NAMESPACE>
```

**Solution:**
- Verificar resource limits no istio-proxy
- Ajustar sampling rate: `PILOT_TRACE_SAMPLING`
- Verificar mesh config para otimizações