# Deploy Portainer to the Kubernetes cluster

Este diretório contém um script e um exemplo de valores para instalar o Portainer (CE) em um cluster Kubernetes via Helm.

Pré-requisitos
- `kubectl` configurado para apontar para o cluster alvo (kubeconfig/context correto)
- `helm` (v3+)
- Permissões suficientes para criar Namespaces, Services e recursos de RBAC no cluster

Arquivos
- `deploy-portainer.sh` - script de conveniência que faz `helm repo add` e `helm upgrade --install` usando `portainer/portainer` chart.
- `portainer-values.yaml` - arquivo de exemplo com configurações úteis (persistência, service type, agent).

Como usar
1. Verifique o contexto do kubectl:

```bash
kubectl config current-context
kubectl get nodes
```

2. (Opcional) Edite `portainer-values.yaml` para ajustar StorageClass, service.type (LoadBalancer/NodePort), ou outros valores.

3. Execute o script:

```bash
bash deploy/portainer/deploy-portainer.sh
```

4. Verifique recursos e endereço de acesso:

```bash
kubectl get all -n portainer
kubectl get svc -n portainer
```

- Se `service.type=LoadBalancer` e seu provedor suportar LoadBalancers, haverá um EXTERNAL-IP pronto para acessar Portainer.
- Se `service.type=NodePort`, use `NODE_IP:NODE_PORT` para acessar.
- Em clusters sem LoadBalancer (por exemplo, k3s, bare-metal), você pode usar Ingress com um Ingress Controller ou expor via NodePort.

Alternativa via kubectl (sem Helm)
O Portainer também fornece manifests para K8s. Se você não quiser usar Helm, consulte a documentação oficial:
https://documentation.portainer.io/start/install/server/kubernetes

Notas e troubleshooting
- Se o PVC falhar, verifique se existe StorageClass compatível no cluster. Ajuste `portainer-values.yaml` com `storageClass: "<sua-storageclass>"`.
- Se não houver IP externo, seu provedor pode não suportar LoadBalancer; altere para NodePort ou configure um Ingress.

Se quiser, posso tentar executar o deploy para você a partir deste ambiente (preciso de acesso ao seu cluster via kubeconfig), ou gerar manifest YAML puros se preferir não usar Helm.
