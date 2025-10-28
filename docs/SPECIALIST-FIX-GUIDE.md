# Guia de Correção dos Specialists

**Problema**: Todos os 5 specialists estão em CrashLoopBackOff devido a `ModuleNotFoundError: No module named 'structlog'`

**Status**: ✅ Dependência adicionada ao código | ⏳ Imagens precisam ser rebuildadas

---

## ✅ O Que Foi Feito

1. **Adicionado `structlog>=23.1.0`** aos `requirements.txt` de todos os 5 specialists:
   - ✅ `services/specialist-business/requirements.txt`
   - ✅ `services/specialist-behavior/requirements.txt`
   - ✅ `services/specialist-evolution/requirements.txt`
   - ✅ `services/specialist-architecture/requirements.txt`
   - ✅ `services/specialist-technical/requirements.txt`

2. **Deployments escalados para 0** para economizar recursos

---

## 🔨 Próximos Passos (Requer Rebuild das Imagens)

### Opção 1: Build Manual Sequencial (Recomendado para primeiro teste)

```bash
cd /home/jimy/Base/Neural-Hive-Mind

# Build apenas specialist-business para testar
docker build \
  -t localhost:5000/specialist-business:v1.0.1 \
  -t localhost:5000/specialist-business:latest \
  -f services/specialist-business/Dockerfile \
  .

# Push para registry
docker push localhost:5000/specialist-business:v1.0.1
docker push localhost:5000/specialist-business:latest

# Atualizar deployment para usar nova imagem
kubectl set image deployment/specialist-business \
  specialist-business=localhost:5000/specialist-business:v1.0.1 \
  -n neural-hive-mind

# Escalar para 1 réplica
kubectl scale deployment specialist-business --replicas=1 -n neural-hive-mind

# Verificar logs
kubectl logs -f deployment/specialist-business -n neural-hive-mind
```

Se funcionar, repita para os outros 4 specialists.

---

### Opção 2: Build de Todos os Specialists

**⚠️ AVISO**: Cada specialist demora ~5-10 minutos para buildar (dependências pesadas como PyTorch, Prophet, etc.)

```bash
cd /home/jimy/Base/Neural-Hive-Mind

# Definir nova versão
VERSION="v1.0.1"

# Build todos os specialists
for spec in business technical behavior evolution architecture; do
  echo "=== Building specialist-$spec ==="

  docker build \
    -t localhost:5000/specialist-$spec:$VERSION \
    -t localhost:5000/specialist-$spec:latest \
    -f services/specialist-$spec/Dockerfile \
    .

  # Push para registry
  docker push localhost:5000/specialist-$spec:$VERSION
  docker push localhost:5000/specialist-$spec:latest
done

# Atualizar todos os deployments
for spec in business technical behavior evolution architecture; do
  kubectl set image deployment/specialist-$spec \
    specialist-$spec=localhost:5000/specialist-$spec:$VERSION \
    -n neural-hive-mind
done

# Escalar todos para 1 réplica
for spec in business technical behavior evolution architecture; do
  kubectl scale deployment specialist-$spec --replicas=1 -n neural-hive-mind
done

# Monitorar rollout
kubectl get pods -n neural-hive-mind -w
```

---

### Opção 3: Build em Background (Paralelo)

Para acelerar, você pode buildar todos em paralelo:

```bash
cd /home/jimy/Base/Neural-Hive-Mind
VERSION="v1.0.1"

# Iniciar builds em background
for spec in business technical behavior evolution architecture; do
  (
    echo "Starting build for specialist-$spec..."
    docker build \
      -t localhost:5000/specialist-$spec:$VERSION \
      -t localhost:5000/specialist-$spec:latest \
      -f services/specialist-$spec/Dockerfile \
      . > /tmp/build-$spec.log 2>&1

    if [ $? -eq 0 ]; then
      echo "✅ Build completed: specialist-$spec"
      docker push localhost:5000/specialist-$spec:$VERSION
      docker push localhost:5000/specialist-$spec:latest
    else
      echo "❌ Build failed: specialist-$spec (check /tmp/build-$spec.log)"
    fi
  ) &
done

# Aguardar todos completarem
wait
echo "All builds completed!"

# Verificar quais imagens foram criadas
docker images localhost:5000/specialist-* --format "table {{.Repository}}\t{{.Tag}}\t{{.CreatedAt}}"
```

---

## 🔍 Verificação Após Build

### 1. Verificar que as imagens foram criadas

```bash
docker images localhost:5000/specialist-* | grep v1.0.1
```

Deve mostrar todas as 5 imagens com tag `v1.0.1`.

### 2. Testar um specialist primeiro

```bash
# Escalar specialist-business
kubectl scale deployment specialist-business --replicas=1 -n neural-hive-mind

# Monitorar o pod
kubectl get pods -n neural-hive-mind -l app=specialist-business -w

# Ver logs em tempo real
kubectl logs -f -n neural-hive-mind -l app=specialist-business

# Verificar se não há mais erro de structlog
kubectl logs -n neural-hive-mind -l app=specialist-business | grep -i "modulenotfound\|structlog\|error"
```

### 3. Se funcionar, escalar os outros

```bash
for spec in technical behavior evolution architecture; do
  kubectl scale deployment specialist-$spec --replicas=1 -n neural-hive-mind
done

# Monitorar todos
kubectl get pods -n neural-hive-mind | grep specialist
```

---

## 📊 Status Esperado Após Correção

```
NAME                                       READY   STATUS    RESTARTS   AGE
specialist-architecture-xxxxx              1/1     Running   0          2m
specialist-behavior-xxxxx                  1/1     Running   0          2m
specialist-business-xxxxx                  1/1     Running   0          2m
specialist-evolution-xxxxx                 1/1     Running   0          2m
specialist-technical-xxxxx                 1/1     Running   0          2m
```

---

## 🐛 Troubleshooting

### Build falha com erro de espaço

```bash
# Limpar cache de build
docker builder prune -af

# Limpar imagens antigas
docker image prune -a --filter "until=24h"
```

### Pod continua em CrashLoopBackOff após build

```bash
# Verificar se a imagem correta está sendo usada
kubectl describe pod <pod-name> -n neural-hive-mind | grep Image:

# Forçar pull da nova imagem
kubectl delete pod <pod-name> -n neural-hive-mind

# Ver eventos do pod
kubectl describe pod <pod-name> -n neural-hive-mind | grep -A20 Events
```

### Rollout travado

```bash
# Ver status do rollout
kubectl rollout status deployment/specialist-business -n neural-hive-mind

# Fazer rollout undo se necessário
kubectl rollout undo deployment/specialist-business -n neural-hive-mind
```

---

## 📝 Notas Importantes

1. **Tempo de Build**: Cada specialist pode levar 5-10 minutos devido a dependências pesadas:
   - PyTorch (~900MB)
   - Prophet
   - scikit-learn
   - pandas/numpy
   - spaCy

2. **Espaço em Disco**: Certifique-se de ter pelo menos 10GB livres antes de iniciar os builds.

3. **Registry Local**: O registry local `localhost:5000` precisa estar rodando:
   ```bash
   docker ps | grep registry
   ```

4. **Imagens Antigas**: As imagens antigas (`v1.0.0-1759844589`) podem ser removidas após confirmar que as novas funcionam:
   ```bash
   docker rmi localhost:5000/specialist-business:v1.0.0-1759844589
   ```

---

## ✅ Checklist de Validação Final

- [ ] Todas as 5 imagens buildadas com tag `v1.0.1`
- [ ] Imagens pushed para `localhost:5000`
- [ ] Deployments atualizados para usar `v1.0.1`
- [ ] Pods em status `Running` (não `CrashLoopBackOff`)
- [ ] Logs não mostram erro de `structlog`
- [ ] Health checks passando (opcional)
- [ ] Serviços respondendo em suas portas (50051, 8000, 8080)

---

**Criado em**: 2025-10-20
**Problema Original**: `ModuleNotFoundError: No module named 'structlog'`
**Solução**: Adicionar `structlog>=23.1.0` ao requirements.txt + Rebuild imagens
