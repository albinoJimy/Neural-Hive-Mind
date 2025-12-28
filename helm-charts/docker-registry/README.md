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
