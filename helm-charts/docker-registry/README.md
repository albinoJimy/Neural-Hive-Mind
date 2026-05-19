# Docker Registry HA - Neural Hive Mind

## Visão Geral

Registry privado com alta disponibilidade para o cluster Neural Hive Mind.

## Arquitetura

- **3 réplicas** com anti-affinity
- **Storage S3** compartilhado
- **Redis** para cache distribuído
- **Proxy Docker Hub** para cache de pulls
- **LoadBalancer** com DNS `registry.neural-hive.local`

## Deploy

### Staging
```bash
./scripts/deploy-registry-ha.sh deploy staging
```

### Produção
```bash
./scripts/deploy-registry-ha.sh deploy production
```

## Testes

```bash
./scripts/test-registry-ha.sh
```

## Configuração DNS

Adicionar ao `/etc/hosts` ou DNS corporativo:
```
<LOADBALANCER_IP> registry.neural-hive.local
```

Obter IP do LoadBalancer:
```bash
kubectl get svc docker-registry -n registry -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
```

## Monitoramento

```bash
# Status dos pods
kubectl get pods -n registry -l app.kubernetes.io/name=docker-registry

# Logs
kubectl logs -n registry -l app.kubernetes.io/name=docker-registry --tail=100

# Métricas
curl http://registry.neural-hive.local:5000/metrics
```

## Rollback

```bash
./scripts/deploy-registry-ha.sh rollback
```

## Modo pull-through proxy (cache ghcr.io)

Para mitigar instabilidade de rede com ghcr.io no node vmi3306611
(packet loss intermitente no backbone Contabo, DNS lento ~2s), o
registry pode ser reconfigurado como pull-through cache. Pulls são
servidos da rede interna (NodePort 30500 no master), eliminando
travessia de backbone externo para imagens já cacheadas.

**Trade-off:** em modo proxy, o registry deixa de aceitar push.
Confirmar que nenhum pipeline faz push para `37.60.241.150:30500`
antes de activar.

### Activar server-side

```bash
helm upgrade registry helm-charts/docker-registry \
  -n registry \
  -f helm-charts/docker-registry/values-pullthrough-ghcr.yaml
```

### Configurar containerd (em CADA nó)

Criar `/etc/containerd/certs.d/ghcr.io/hosts.toml`:

```toml
server = "https://ghcr.io"

[host."http://37.60.241.150:30500"]
  capabilities = ["pull", "resolve"]
```

E garantir que `/etc/containerd/config.toml` tem:

```toml
[plugins."io.containerd.grpc.v1.cri".registry]
  config_path = "/etc/containerd/certs.d"
```

Recarregar containerd (não restart hard, evita matar pods):

```bash
systemctl reload containerd  # ou kill -SIGHUP $(pidof containerd)
```

### Validar

```bash
# A partir de um pod no cluster
crictl pull ghcr.io/albinojimy/neural-hive-mind/approval-service:05ca2b2

# No master, ver cache populado
curl http://localhost:30500/v2/_catalog
# Deve listar albinojimy/neural-hive-mind/approval-service
```

## Troubleshooting

### Registry indisponível
```bash
# Verificar pods
kubectl get pods -n registry

# Verificar service
kubectl get svc docker-registry -n registry

# Testar conectividade
curl http://registry.neural-hive.local:5000/v2/
```

### Fallback não funciona
```bash
# Verificar variáveis de ambiente
echo $REGISTRY_PRIMARY
echo $REGISTRY_SECONDARY

# Testar manualmente
docker push registry.neural-hive.local:5000/test:latest
docker push 37.60.241.150:30500/test:latest
```

## Variáveis de Ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `REGISTRY_PRIMARY` | `registry.neural-hive.local:5000` | Registry primário (DNS) |
| `REGISTRY_SECONDARY` | `37.60.241.150:30500` | Registry secundário (IP) |
| `AWS_REGION` | `us-east-1` | Região AWS para fallback ECR |

## Segurança

- Storage S3 com encryption at rest
- Redis sem autenticação (rede interna)
- LoadBalancer interno (não exposto publicamente)
- Network policies aplicadas
