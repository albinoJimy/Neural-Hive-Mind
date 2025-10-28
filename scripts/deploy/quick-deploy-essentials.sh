#!/bin/bash
# Quick Deploy - Componentes Essenciais para Teste End-to-End Fase 2
# Deploy mínimo viável para executar o teste completo

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================="
echo "Quick Deploy - Componentes Essenciais"
echo "=========================================

${NC}"

# 1. MongoDB
echo -e "\n${YELLOW}[1/5] Deploying MongoDB...${NC}"
kubectl create namespace mongodb-cluster --dry-run=client -o yaml | kubectl apply -f - 2>/dev/null || true

kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: mongodb
  namespace: mongodb-cluster
spec:
  serviceName: mongodb
  replicas: 1
  selector:
    matchLabels:
      app: mongodb
  template:
    metadata:
      labels:
        app: mongodb
    spec:
      containers:
      - name: mongodb
        image: mongo:7.0
        ports:
        - containerPort: 27017
        env:
        - name: MONGO_INITDB_ROOT_USERNAME
          value: admin
        - name: MONGO_INITDB_ROOT_PASSWORD
          value: admin123
        volumeMounts:
        - name: data
          mountPath: /data/db
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 10Gi
---
apiVersion: v1
kind: Service
metadata:
  name: mongodb
  namespace: mongodb-cluster
spec:
  clusterIP: None
  selector:
    app: mongodb
  ports:
  - port: 27017
    targetPort: 27017
EOF

echo -e "${GREEN}✓ MongoDB StatefulSet created${NC}"

# 2. PostgreSQL Temporal
echo -e "\n${YELLOW}[2/5] Deploying PostgreSQL Temporal...${NC}"
kubectl create namespace neural-hive-temporal --dry-run=client -o yaml | kubectl apply -f - 2>/dev/null || true

kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgresql-temporal
  namespace: neural-hive-temporal
spec:
  serviceName: postgresql-temporal
  replicas: 1
  selector:
    matchLabels:
      app: postgresql-temporal
  template:
    metadata:
      labels:
        app: postgresql-temporal
    spec:
      containers:
      - name: postgres
        image: postgres:16
        ports:
        - containerPort: 5432
        env:
        - name: POSTGRES_DB
          value: temporal
        - name: POSTGRES_USER
          value: temporal
        - name: POSTGRES_PASSWORD
          value: temporal123
        - name: PGDATA
          value: /var/lib/postgresql/data/pgdata
        volumeMounts:
        - name: data
          mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 20Gi
---
apiVersion: v1
kind: Service
metadata:
  name: postgresql-temporal
  namespace: neural-hive-temporal
spec:
  clusterIP: None
  selector:
    app: postgresql-temporal
  ports:
  - port: 5432
    targetPort: 5432
EOF

echo -e "${GREEN}✓ PostgreSQL Temporal StatefulSet created${NC}"

# 3. PostgreSQL Execution Tickets
echo -e "\n${YELLOW}[3/5] Deploying PostgreSQL Execution Tickets...${NC}"

kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgresql-tickets
  namespace: neural-hive-orchestration
spec:
  serviceName: postgresql-tickets
  replicas: 1
  selector:
    matchLabels:
      app: postgresql-tickets
  template:
    metadata:
      labels:
        app: postgresql-tickets
    spec:
      containers:
      - name: postgres
        image: postgres:16
        ports:
        - containerPort: 5432
        env:
        - name: POSTGRES_DB
          value: execution_tickets
        - name: POSTGRES_USER
          value: postgres
        - name: POSTGRES_PASSWORD
          value: postgres123
        - name: PGDATA
          value: /var/lib/postgresql/data/pgdata
        volumeMounts:
        - name: data
          mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 10Gi
---
apiVersion: v1
kind: Service
metadata:
  name: postgresql-tickets
  namespace: neural-hive-orchestration
spec:
  clusterIP: None
  selector:
    app: postgresql-tickets
  ports:
  - port: 5432
    targetPort: 5432
EOF

echo -e "${GREEN}✓ PostgreSQL Tickets StatefulSet created${NC}"

# 4. Aguardar pods ficarem Ready
echo -e "\n${YELLOW}[4/5] Aguardando pods ficarem Ready (pode levar até 5min)...${NC}"
echo "Aguardando MongoDB..."
kubectl wait --for=condition=Ready pod -l app=mongodb -n mongodb-cluster --timeout=300s || echo "MongoDB ainda não está Ready"

echo "Aguardando PostgreSQL Temporal..."
kubectl wait --for=condition=Ready pod -l app=postgresql-temporal -n neural-hive-temporal --timeout=300s || echo "PostgreSQL Temporal ainda não está Ready"

echo "Aguardando PostgreSQL Tickets..."
kubectl wait --for=condition=Ready pod -l app=postgresql-tickets -n neural-hive-orchestration --timeout=300s || echo "PostgreSQL Tickets ainda não está Ready"

# 5. Verificação final
echo -e "\n${YELLOW}[5/5] Verificação final...${NC}"
echo ""
echo "MongoDB:"
kubectl get pods -n mongodb-cluster -l app=mongodb

echo ""
echo "PostgreSQL Temporal:"
kubectl get pods -n neural-hive-temporal -l app=postgresql-temporal

echo ""
echo "PostgreSQL Tickets:"
kubectl get pods -n neural-hive-orchestration -l app=postgresql-tickets

echo -e "\n${GREEN}========================================="
echo "✓ Deploy de componentes essenciais concluído!"
echo "=========================================

${NC}"
echo ""
echo "Próximos passos:"
echo "1. Aguardar todos os pods ficarem Running/Ready"
echo "2. Deploy Temporal Server (temporal-frontend, history, matching, worker)"
echo "3. Deploy Orchestrator Dynamic"
echo "4. Executar teste end-to-end"
