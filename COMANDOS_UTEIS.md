# 🔧 Comandos Úteis - Neural Hive-Mind Local

## 📋 Monitoramento

### Status Geral
```bash
# Status de todos os pods
kubectl get pods -A | grep neural-hive

# Status dos namespaces
kubectl get namespaces | grep neural-hive

# Status dos serviços
kubectl get svc -A | grep neural-hive

# Verificar recursos por namespace
kubectl top pods -A | grep neural-hive
```

### Logs
```bash
# Logs do serviço de teste
kubectl logs -f deployment/neural-test-service -n neural-hive-system

# Logs do Istio
kubectl logs -f deployment/istiod -n istio-system

# Logs do Gatekeeper
kubectl logs -f deployment/gatekeeper-controller-manager -n gatekeeper-system
```

## 🌐 Acesso aos Dashboards

### Kiali (Service Mesh)
```bash
kubectl port-forward svc/kiali 20001:20001 -n istio-system
# Acesse: http://localhost:20001
```

### Grafana (Métricas)
```bash
kubectl port-forward svc/grafana 3000:3000 -n istio-system
# Acesse: http://localhost:3000
```

### Jaeger (Tracing)
```bash
kubectl port-forward svc/jaeger 16686:16686 -n istio-system
# Acesse: http://localhost:16686
```

### Prometheus (Métricas Raw)
```bash
kubectl port-forward svc/prometheus 9090:9090 -n istio-system
# Acesse: http://localhost:9090
```

## 🧪 Teste e Desenvolvimento

### Acessar Serviço de Teste
```bash
# Via port-forward
kubectl port-forward svc/neural-test-service 8080:80 -n neural-hive-system
# Acesse: http://localhost:8080

# Teste interno
kubectl exec -n neural-hive-system deployment/neural-test-service -- curl localhost
```

### Deploy de Novos Serviços
```bash
# Template básico
cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: meu-servico
  namespace: neural-hive-cognition
  labels:
    app: meu-servico
spec:
  replicas: 1
  selector:
    matchLabels:
      app: meu-servico
  template:
    metadata:
      labels:
        app: meu-servico
      annotations:
        sidecar.istio.io/inject: "true"
    spec:
      containers:
      - name: app
        image: nginx:alpine
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: meu-servico
  namespace: neural-hive-cognition
spec:
  selector:
    app: meu-servico
  ports:
  - port: 80
    targetPort: 80
EOF
```

## 🛡️ Políticas e Segurança

### Verificar Políticas OPA
```bash
# Listar constraint templates
kubectl get constrainttemplates

# Listar constraints ativos
kubectl get constraints -A

# Verificar violações
kubectl get neuralhivemtlsrequired -A -o yaml
```

### Verificar mTLS
```bash
# Status de peer authentication
kubectl get peerauthentication -A

# Testar mTLS entre serviços
istioctl authn tls-check neural-test-service.neural-hive-system
```

## 🔄 Limpeza e Reset

### Limpar Deployment Local
```bash
# Remover serviços de teste
kubectl delete -f test-service-local.yaml

# Remover políticas aplicadas
kubectl delete constrainttemplates --all
kubectl delete peerauthentication -A --all

# Reset completo (CUIDADO!)
kubectl delete namespace neural-hive-cognition neural-hive-orchestration neural-hive-execution neural-hive-observability
```

### Restart de Componentes
```bash
# Restart do Gatekeeper
kubectl rollout restart deployment gatekeeper-controller-manager -n gatekeeper-system
kubectl rollout restart deployment gatekeeper-audit -n gatekeeper-system

# Restart do Istio
kubectl rollout restart deployment istiod -n istio-system
```

## 🚨 Troubleshooting

### Pods não iniciam
```bash
# Verificar eventos
kubectl get events --sort-by='.lastTimestamp' -A

# Descrever pod problemático
kubectl describe pod <nome-do-pod> -n <namespace>

# Verificar recursos
kubectl top nodes
kubectl top pods -A
```

### Problemas de Conectividade
```bash
# Testar DNS
kubectl run dns-test --image=busybox --rm -it -- nslookup kubernetes.default

# Testar conectividade entre namespaces
kubectl run network-test --image=busybox --rm -it --namespace neural-hive-system -- ping neural-test-service
```

### Problemas com Istio
```bash
# Verificar configuração do mesh
istioctl analyze

# Status dos proxies
istioctl proxy-status

# Configuração de um pod específico
istioctl proxy-config cluster <pod-name>.<namespace>
```

### Debug de Políticas OPA
```bash
# Logs detalhados do Gatekeeper
kubectl logs deployment/gatekeeper-controller-manager -n gatekeeper-system --tail=50

# Testar criação de recurso
kubectl apply --dry-run=server -f meu-arquivo.yaml
```

## 📚 Referências Rápidas

### Estrutura de Namespaces
- `neural-hive-system`: Componentes principais e testes
- `neural-hive-cognition`: Processamento e interpretação
- `neural-hive-orchestration`: Coordenação e workflow
- `neural-hive-execution`: Agentes e workers
- `neural-hive-observability`: Métricas, logs e tracing

### Portas Padrão
- Kiali: 20001
- Grafana: 3000
- Jaeger: 16686
- Prometheus: 9090
- Serviço de teste: 8080 (via port-forward)

---

🤖 **Para mais informações, consulte DEPLOYMENT_LOCAL.md**