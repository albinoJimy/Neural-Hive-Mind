# Guia: Adicionar Worker Nodes ao Cluster Kubernetes

## Visão Geral

Este guia explica como adicionar 2 worker nodes ao cluster Kubernetes existente.

**Cluster atual:**
- Control-plane: `vmi2092350.contaboserver.net` (37.60.241.150)
- Versão Kubernetes: v1.29.15
- Workers atuais: 0
- Workers a adicionar: 2

---

## Requisitos das VMs/Máquinas Worker

Cada worker node deve ter:
- **OS**: Ubuntu 20.04 ou superior
- **CPU**: Mínimo 2 cores (recomendado 4+)
- **RAM**: Mínimo 4GB (recomendado 8GB+)
- **Disco**: Mínimo 20GB
- **Rede**: Acesso ao control-plane em 37.60.241.150:6443
- **Acesso root**: Via sudo

### Portas necessárias abertas no firewall:
- **10250/tcp**: Kubelet API
- **30000-32767/tcp**: NodePort Services

---

## Passo 1: Preparar as VMs

Para cada uma das 2 VMs que serão workers:

### 1.1 Copiar o script de instalação

No **control-plane** atual, o script está em:
```bash
/jimy/Neural-Hive-Mind/scripts/setup-k8s-worker.sh
```

Copie este script para cada VM worker:
```bash
# Exemplo usando scp (execute no control-plane)
scp /jimy/Neural-Hive-Mind/scripts/setup-k8s-worker.sh root@<IP_WORKER_1>:/tmp/
scp /jimy/Neural-Hive-Mind/scripts/setup-k8s-worker.sh root@<IP_WORKER_2>:/tmp/
```

---

## Passo 2: Executar instalação em cada Worker

**Em cada VM worker**, execute:

```bash
# Conectar à VM worker
ssh root@<IP_WORKER>

# Executar o script
sudo bash /tmp/setup-k8s-worker.sh
```

O script irá:
1. ✓ Desabilitar swap
2. ✓ Configurar módulos do kernel
3. ✓ Instalar containerd
4. ✓ Instalar kubeadm, kubelet e kubectl
5. ✓ Configurar rede e firewall
6. ✓ Verificar instalação

---

## Passo 3: Fazer Join ao Cluster

Após o script terminar, **em cada worker**, execute o comando de join:

```bash
sudo kubeadm join 37.60.241.150:6443 \
  --token vcknwv.u965dgbhjcgv5gre \
  --discovery-token-ca-cert-hash sha256:aa809c60d71383b75447b3573683af29c57643feb8862bc5cfe1e1853bfd6562
```

**⚠️ IMPORTANTE**: Este token é válido por 24 horas.

### Se o token expirar:

No **control-plane**, gere um novo token:
```bash
sudo kubeadm token create --print-join-command
```

---

## Passo 4: Verificar Workers no Cluster

No **control-plane**, verifique se os workers foram adicionados:

```bash
# Listar todos os nodes
kubectl get nodes

# Verificar detalhes dos nodes
kubectl get nodes -o wide

# Verificar labels dos nodes
kubectl get nodes --show-labels
```

Você deverá ver 3 nodes no total:
- 1 control-plane (vmi2092350.contaboserver.net)
- 2 workers

---

## Passo 5: Aplicar Labels aos Workers (Opcional)

Para organizar melhor os workloads, você pode aplicar labels aos workers:

```bash
# Worker 1 - para specialists
kubectl label node <WORKER_1_NAME> workload=specialists tier=compute

# Worker 2 - para services
kubectl label node <WORKER_2_NAME> workload=services tier=compute
```

---

## Passo 6: Testar Distribuição de Pods

Após adicionar os workers, teste se os pods estão sendo distribuídos:

```bash
# Ver distribuição de pods por node
kubectl get pods -A -o wide | grep -E "NODE|<WORKER_1_NAME>|<WORKER_2_NAME>"

# Forçar redistribuição (opcional)
kubectl rollout restart deployment -n gateway-intencoes gateway-intencoes
kubectl rollout restart deployment -n semantic-translation-engine semantic-translation-engine
```

---

## Troubleshooting

### Worker não aparece no cluster

1. Verificar conectividade:
```bash
# No worker
ping 37.60.241.150
telnet 37.60.241.150 6443
```

2. Verificar logs do kubelet:
```bash
# No worker
sudo journalctl -u kubelet -f
```

3. Verificar status do containerd:
```bash
# No worker
sudo systemctl status containerd
```

### Worker aparece como "NotReady"

1. Verificar rede (CNI):
```bash
# No control-plane
kubectl get pods -n kube-flannel
```

2. Verificar logs do node:
```bash
kubectl describe node <WORKER_NAME>
```

### Token expirado

Se o token expirou (24h), gere um novo:
```bash
# No control-plane
sudo kubeadm token create --print-join-command
```

---

## Remover um Worker (se necessário)

Se precisar remover um worker do cluster:

```bash
# No control-plane
kubectl drain <WORKER_NAME> --delete-emptydir-data --force --ignore-daemonsets
kubectl delete node <WORKER_NAME>

# No worker
sudo kubeadm reset
sudo rm -rf /etc/cni/net.d
sudo systemctl restart containerd
```

---

## Checklist de Conclusão

- [ ] Script executado em Worker 1
- [ ] Script executado em Worker 2
- [ ] Join executado em Worker 1
- [ ] Join executado em Worker 2
- [ ] Worker 1 aparece com `kubectl get nodes`
- [ ] Worker 2 aparece com `kubectl get nodes`
- [ ] Ambos workers estão com status "Ready"
- [ ] Labels aplicados aos workers
- [ ] Pods sendo distribuídos nos workers

---

## Comandos de Verificação Final

```bash
# Ver todos os nodes
kubectl get nodes -o wide

# Ver capacidade dos nodes
kubectl top nodes

# Ver pods distribuídos
kubectl get pods -A -o wide | awk '{print $8}' | sort | uniq -c

# Ver recursos disponíveis
kubectl describe nodes
```

---

## Informações Adicionais

- **Token de join atual**: Válido até aproximadamente 24 horas após geração
- **Control-plane IP**: 37.60.241.150
- **Porta API**: 6443
- **CNI**: Flannel (já configurado no cluster)
- **Container Runtime**: containerd 1.7.27

---

**Data de criação**: 2025-11-15
**Versão do cluster**: v1.29.15
