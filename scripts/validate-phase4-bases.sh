#!/bin/bash
set -euo pipefail

echo "=== Validação Phase 4: Otimização de Bases ==="

# 1. Build python-mlops-base
echo "1. Building python-mlops-base..."
docker build -t neural-hive-mind/python-mlops-base:1.0.0 \
  -f base-images/python-mlops-base/Dockerfile \
  --build-arg VERSION=1.0.0 \
  --build-arg BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  .

# 2. Verificar imports em python-mlops-base
echo "2. Verificando imports em python-mlops-base..."
docker run --rm neural-hive-mind/python-mlops-base:1.0.0 \
  python -c "import pandas; import numpy; import scipy; import sklearn; import mlflow; print('✓ MLOps deps OK')"

# 3. Build consensus-engine
echo "3. Building consensus-engine..."
docker build -t test-consensus-engine:1.0.11 \
  -f services/consensus-engine/Dockerfile \
  .

# 4. Verificar tamanho consensus-engine
echo "4. Verificando tamanho consensus-engine..."
SIZE=$(docker images test-consensus-engine:1.0.11 --format "{{.Size}}")
echo "   Tamanho: $SIZE (esperado: ~480MB)"

# 5. Build optimizer-agents
echo "5. Building optimizer-agents..."
docker build -t test-optimizer-agents:1.0.11 \
  -f services/optimizer-agents/Dockerfile \
  .

# 6. Verificar tamanho optimizer-agents
echo "6. Verificando tamanho optimizer-agents..."
SIZE=$(docker images test-optimizer-agents:1.0.11 --format "{{.Size}}")
echo "   Tamanho: $SIZE (esperado: ~800MB)"

# 7. Testar startup consensus-engine
echo "7. Testando startup consensus-engine..."
docker run --rm -d --name test-consensus \
  -e MONGODB_URI=mongodb://localhost:27017 \
  -e REDIS_CLUSTER_NODES=localhost:6379 \
  -e KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
  test-consensus-engine:1.0.11 || true
sleep 5
docker logs test-consensus 2>&1 | grep -q "Consensus Engine" && echo "   ✓ Startup OK" || echo "   ✗ Startup failed"
docker stop test-consensus 2>/dev/null || true

# 8. Testar startup optimizer-agents
echo "8. Testando startup optimizer-agents..."
docker run --rm -d --name test-optimizer \
  -e MONGODB_URI=mongodb://localhost:27017 \
  -e REDIS_HOST=localhost \
  -e KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
  test-optimizer-agents:1.0.11 || true
sleep 5
docker logs test-optimizer 2>&1 | grep -q "optimizer_agents" && echo "   ✓ Startup OK" || echo "   ✗ Startup failed"
docker stop test-optimizer 2>/dev/null || true

echo ""
echo "=== Validação Concluída ==="
