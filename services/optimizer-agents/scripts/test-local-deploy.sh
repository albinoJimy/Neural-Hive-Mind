#!/bin/bash
set -e

# Teste local do Optimizer Agents usando Docker Compose
# Útil para validar antes do deploy em cluster

echo "=== Teste Local - Optimizer Agents ==="
echo ""

# Verificar se Docker Compose está instalado
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose não encontrado"
    exit 1
fi

# Build da imagem
echo "[1/4] Build da imagem..."
docker build -t optimizer-agents:test -f Dockerfile ../../

# Verificar se há docker-compose.yml
if [ ! -f "../../docker-compose.yml" ]; then
    echo "[2/4] Criando docker-compose.yml para teste..."

    cat > ../../docker-compose.optimizer-test.yml <<'EOF'
version: '3.8'

services:
  optimizer-agents:
    image: optimizer-agents:test
    container_name: optimizer-test
    ports:
      - "8000:8000"
      - "50051:50051"
      - "8080:8080"
    environment:
      - ENVIRONMENT=test
      - DEBUG=true
      - LOG_LEVEL=DEBUG
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
      - MONGODB_URL=mongodb://mongodb:27017
      - REDIS_URL=redis://redis:6379
    depends_on:
      - mongodb
      - redis
    networks:
      - neural-hive

  mongodb:
    image: mongo:7
    container_name: optimizer-mongo-test
    ports:
      - "27017:27017"
    networks:
      - neural-hive

  redis:
    image: redis:7-alpine
    container_name: optimizer-redis-test
    ports:
      - "6379:6379"
    networks:
      - neural-hive

networks:
  neural-hive:
    driver: bridge
EOF

    COMPOSE_FILE="../../docker-compose.optimizer-test.yml"
else
    COMPOSE_FILE="../../docker-compose.yml"
fi

# Subir serviços
echo "[3/4] Subindo serviços..."
docker-compose -f $COMPOSE_FILE up -d

# Aguardar health check
echo "[4/4] Aguardando health check..."
sleep 10

if curl -f http://localhost:8000/health; then
    echo ""
    echo "✅ Teste local passou!"
    echo ""
    echo "Serviços disponíveis:"
    echo "  HTTP API:  http://localhost:8000"
    echo "  gRPC:      localhost:50051"
    echo "  Métricas:  http://localhost:8080/metrics"
    echo ""
    echo "Para derrubar:"
    echo "  docker-compose -f $COMPOSE_FILE down"
else
    echo ""
    echo "❌ Teste falhou!"
    docker-compose -f $COMPOSE_FILE logs optimizer-agents
    exit 1
fi
