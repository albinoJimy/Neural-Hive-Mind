# Relatório de Falha no Build dos Specialists

**Data**: 2025-10-20
**Status**: ❌ Build falhou após ~2h40min

---

## 🔴 Problema Identificado

Todos os 5 builds falharam no **mesmo ponto**:

```
Downloading nvidia_curand_cu12-10.3.9.90 (63.6 MB)
Progress: 32.0/63.6 MB (50%)
ERROR: Exception - Timeout após 9570 segundos (~160 minutos)
```

**Causa Raiz**:
- Downloads de dependências CUDA muito grandes (total ~3GB por specialist)
- Timeout de rede após 2h40min de build
- 5 builds paralelos competindo por banda

---

## 📊 Dependências Problemáticas

| Pacote | Tamanho | Status |
|--------|---------|--------|
| torch | 900 MB | ✅ Baixado |
| nvidia_cublas_cu12 | 594 MB | ✅ Baixado |
| nvidia_cudnn_cu12 | 707 MB | ✅ Baixado |
| nvidia_cufft_cu12 | 193 MB | ⚠️ Parcial (140MB) |
| **nvidia_curand_cu12** | **64 MB** | **❌ Falhou (32MB)** |

---

## ✅ Solução Aplicada (Código)

O problema original (`ModuleNotFoundError: structlog`) **JÁ FOI CORRIGIDO** no código:

```bash
✅ services/specialist-business/requirements.txt
✅ services/specialist-behavior/requirements.txt
✅ services/specialist-evolution/requirements.txt
✅ services/specialist-architecture/requirements.txt
✅ services/specialist-technical/requirements.txt
```

Todos contêm agora: `structlog>=23.1.0`

---

## 🔧 Soluções Alternativas

### Opção 1: Build Sequencial (Recomendado)

Buildar um specialist por vez para evitar competição de banda:

```bash
cd /home/jimy/Base/Neural-Hive-Mind

for spec in business technical behavior evolution architecture; do
  echo "=== Building specialist-$spec ==="

  docker build \
    --network=host \
    -t localhost:5000/specialist-$spec:v1.0.1 \
    -f services/specialist-$spec/Dockerfile \
    . 2>&1 | tee /tmp/build-$spec-retry.log

  if [ $? -eq 0 ]; then
    echo "✅ Success: $spec"
    docker push localhost:5000/specialist-$spec:v1.0.1
  else
    echo "❌ Failed: $spec"
    break
  fi

  # Pequena pausa entre builds
  sleep 10
done
```

**Tempo estimado**: 30-45 minutos por specialist = 2.5-4 horas total

---

### Opção 2: Usar Imagem Base com PyTorch

Criar um Dockerfile base com PyTorch pré-instalado:

```dockerfile
# Dockerfile.base
FROM python:3.11-slim

# Instalar PyTorch e dependências CUDA de uma vez
RUN pip install torch==2.9.0 --index-url https://download.pytorch.org/whl/cpu

# Outras dependências pesadas comuns
RUN pip install \
    pandas>=2.1.0 \
    numpy>=1.24.0 \
    scikit-learn>=1.3.0

# Salvar como imagem base
```

Depois adaptar os Dockerfiles dos specialists para usar essa base.

---

### Opção 3: Build Sem PyTorch (Mais Rápido)

Se PyTorch não for crítico para os specialists, remover temporariamente do SHAP:

```bash
# Editar libraries/python/neural_hive_specialists/requirements.txt
# Comentar: shap>=0.44.0 (que puxa o PyTorch)
```

**Tempo estimado**: 5-10 minutos por specialist

---

### Opção 4: Usar Registry Externo

Se você tem Docker Hub ou outro registry:

```bash
# Build em uma máquina com melhor conexão
# Push para Docker Hub
docker tag localhost:5000/specialist-business:v1.0.1 seurepo/specialist-business:v1.0.1
docker push seurepo/specialist-business:v1.0.1

# No Kubernetes, usar a imagem do Docker Hub
kubectl set image deployment/specialist-business \
  specialist-business=seurepo/specialist-business:v1.0.1 \
  -n neural-hive-mind
```

---

## 🎯 Recomendação Imediata

**Use a Opção 3** (Build sem PyTorch temporariamente):

1. Comentar SHAP do requirements.txt:
   ```bash
   sed -i 's/shap>=0.44.0/# shap>=0.44.0/' \
     libraries/python/neural_hive_specialists/requirements.txt
   ```

2. Build rápido (5-10 min cada):
   ```bash
   docker build -t localhost:5000/specialist-business:v1.0.1 \
     -f services/specialist-business/Dockerfile .
   ```

3. Deploy e validar que `structlog` foi corrigido

4. Depois, re-adicionar SHAP quando tiver melhor conexão

---

## 📝 Lições Aprendidas

1. **Builds paralelos**: 5× em paralelo causa competição de banda
2. **Dependências CUDA**: ~3GB por imagem = 15GB total baixado
3. **Timeout**: Após ~2h40min a conexão caiu
4. **Solução**: Build sequencial ou remover dependências pesadas temporariamente

---

## ✅ Status do Código-Fonte

| Item | Status |
|------|--------|
| Dependência structlog adicionada | ✅ Completo |
| Código atualizado nos 5 specialists | ✅ Completo |
| Imagens Docker rebuildadas | ❌ Falhou (timeout) |
| Deployments atualizados | ⏸️ Aguardando imagens |

---

## 🚀 Próxima Ação

Escolha uma das opções acima e execute. A **Opção 3** (sem PyTorch) é a mais rápida para validar o fix do `structlog`.

Após validar que funciona, você pode rebuildar com PyTorch em um momento com melhor conexão ou fora do horário de pico.

---

**Criado**: 2025-10-20 15:00
**Tempo total de tentativa**: 2h40min
**Resultado**: Build falhou por timeout de rede
**Fix do código**: ✅ Completo e pronto
