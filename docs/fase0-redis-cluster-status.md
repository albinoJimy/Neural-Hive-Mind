# REDIS CLUSTER - STATUS E PRÓXIMOS PASSOS

Data: 2026-04-12

## ESTADO ATUAL

### Pods Instalados
- **3 Leaders**: 2/3 Ready (1 Pendente - falta de recursos)
- **3 Followers**: 2/3 Ready (1 Pendente - falta de recursos)

### Configuração
- **cluster-enabled**: no (standalone mode)
- **TLS**: ✓ Configurado
- **Secrets**: redis-ca, redis-tls

## PROBLEMAS IDENTIFICADOS

1. **Operador Redis Não Funcional**
   - O operador Opstree Redis não está a correr
   - O deployment "redis" está em 0/0 replicas

2. **Cluster Bootstrap Não Completo**
   - Redis em modo standalone em vez de cluster
   - Necessário ativar `cluster-enabled yes`

3. **Recursos Insuficientes**
   - Alguns pods não conseguem ser agendados

## PRÓXIMOS PASSOS RECOMENDADOS

### Opção A: Reinstalar Operador Redis
1. Escalar deployment `redis` para 1 replica
2. Deixar o operador gerir o bootstrap do cluster
3. Validar estado do cluster

### Opção B: Configuração Manual
1. Criar ConfigMap com `cluster-enabled yes`
2. Adicionar volume mount aos Statefulsets
3. Reiniciar pods
4. Executar `CLUSTER MEET` entre os 3 masters
5. Adicionar replicas com `CLUSTER REPLICATE`

### Opção C: Usar Redis Operator Alternativo
1. Considerar usar Redis Enterprise ou Redis Cloud
2. Ou usar um operador diferente (como Spotah)

## COMANDOS ÚTEIS

### Verificar estado do cluster
```bash
kubectl exec -n redis-cluster redis-cluster-leader-0 -- redis-cli CLUSTER INFO
kubectl exec -n redis-cluster redis-cluster-leader-0 -- redis-cli CLUSTER NODES
```

### Verificar configuração
```bash
kubectl exec -n redis-cluster redis-cluster-leader-0 -- redis-cli CONFIG GET cluster-enabled
```

### Inicializar cluster manualmente
```bash
# Nos 3 pods leader:
kubectl exec -n redis-cluster redis-cluster-leader-0 -- redis-cli CLUSTER MEET <pod-ip> 6379
kubectl exec -n redis-cluster redis-cluster-leader-0 -- redis-cli CLUSTER MEET <pod-ip> 6379
kubectl exec -n redis-cluster redis-cluster-leader-0 -- redis-cli CLUSTER NODES
```

### Escalar operador
```bash
kubectl scale deployment redis -n redis-cluster --replicas=1
```
