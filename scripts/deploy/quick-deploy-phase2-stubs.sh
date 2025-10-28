#!/bin/bash
# Quick Deploy - Phase 2 Service Stubs
# Deploy minimal mock services for end-to-end testing

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================="
echo "Quick Deploy - Phase 2 Service Stubs"
echo "=========================================${NC}"

# Create all required namespaces
echo -e "\n${YELLOW}Creating namespaces...${NC}"
for ns in neural-hive-service-registry neural-hive-queen neural-hive-workers neural-hive-scouts neural-hive-analysts neural-hive-optimizers neural-hive-guards neural-hive-sla neural-hive-code-forge neural-hive-mcp neural-hive-healing; do
  kubectl create namespace $ns --dry-run=client -o yaml | kubectl apply -f - 2>/dev/null || true
done

# Deploy stub services using simple nginx with custom index
kubectl apply -f - <<'EOF'
# Service Registry
apiVersion: apps/v1
kind: Deployment
metadata:
  name: service-registry
  namespace: neural-hive-service-registry
spec:
  replicas: 1
  selector:
    matchLabels:
      app: service-registry
  template:
    metadata:
      labels:
        app: service-registry
    spec:
      containers:
      - name: stub
        image: nginx:alpine
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: service-registry
  namespace: neural-hive-service-registry
spec:
  selector:
    app: service-registry
  ports:
  - port: 80
---
# Execution Ticket Service
apiVersion: apps/v1
kind: Deployment
metadata:
  name: execution-ticket-service
  namespace: neural-hive-orchestration
spec:
  replicas: 1
  selector:
    matchLabels:
      app: execution-ticket-service
  template:
    metadata:
      labels:
        app: execution-ticket-service
    spec:
      containers:
      - name: stub
        image: nginx:alpine
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: execution-ticket-service
  namespace: neural-hive-orchestration
spec:
  selector:
    app: execution-ticket-service
  ports:
  - port: 80
---
# Queen Agent
apiVersion: apps/v1
kind: Deployment
metadata:
  name: queen-agent
  namespace: neural-hive-queen
spec:
  replicas: 1
  selector:
    matchLabels:
      app: queen-agent
  template:
    metadata:
      labels:
        app: queen-agent
    spec:
      containers:
      - name: stub
        image: nginx:alpine
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: queen-agent
  namespace: neural-hive-queen
spec:
  selector:
    app: queen-agent
  ports:
  - port: 80
---
# Worker Agents
apiVersion: apps/v1
kind: Deployment
metadata:
  name: worker-agents
  namespace: neural-hive-workers
spec:
  replicas: 1
  selector:
    matchLabels:
      app: worker-agents
  template:
    metadata:
      labels:
        app: worker-agents
    spec:
      containers:
      - name: stub
        image: nginx:alpine
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: worker-agents
  namespace: neural-hive-workers
spec:
  selector:
    app: worker-agents
  ports:
  - port: 80
---
# Scout Agents
apiVersion: apps/v1
kind: Deployment
metadata:
  name: scout-agents
  namespace: neural-hive-scouts
spec:
  replicas: 1
  selector:
    matchLabels:
      app: scout-agents
  template:
    metadata:
      labels:
        app: scout-agents
    spec:
      containers:
      - name: stub
        image: nginx:alpine
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: scout-agents
  namespace: neural-hive-scouts
spec:
  selector:
    app: scout-agents
  ports:
  - port: 80
---
# Analyst Agents
apiVersion: apps/v1
kind: Deployment
metadata:
  name: analyst-agents
  namespace: neural-hive-analysts
spec:
  replicas: 1
  selector:
    matchLabels:
      app: analyst-agents
  template:
    metadata:
      labels:
        app: analyst-agents
    spec:
      containers:
      - name: stub
        image: nginx:alpine
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: analyst-agents
  namespace: neural-hive-analysts
spec:
  selector:
    app: analyst-agents
  ports:
  - port: 80
---
# Optimizer Agents
apiVersion: apps/v1
kind: Deployment
metadata:
  name: optimizer-agents
  namespace: neural-hive-optimizers
spec:
  replicas: 1
  selector:
    matchLabels:
      app: optimizer-agents
  template:
    metadata:
      labels:
        app: optimizer-agents
    spec:
      containers:
      - name: stub
        image: nginx:alpine
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: optimizer-agents
  namespace: neural-hive-optimizers
spec:
  selector:
    app: optimizer-agents
  ports:
  - port: 80
---
# Guard Agents
apiVersion: apps/v1
kind: Deployment
metadata:
  name: guard-agents
  namespace: neural-hive-guards
spec:
  replicas: 1
  selector:
    matchLabels:
      app: guard-agents
  template:
    metadata:
      labels:
        app: guard-agents
    spec:
      containers:
      - name: stub
        image: nginx:alpine
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: guard-agents
  namespace: neural-hive-guards
spec:
  selector:
    app: guard-agents
  ports:
  - port: 80
---
# SLA Management System
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sla-management-system
  namespace: neural-hive-sla
spec:
  replicas: 1
  selector:
    matchLabels:
      app: sla-management-system
  template:
    metadata:
      labels:
        app: sla-management-system
    spec:
      containers:
      - name: stub
        image: nginx:alpine
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: sla-management-system
  namespace: neural-hive-sla
spec:
  selector:
    app: sla-management-system
  ports:
  - port: 80
---
# Code Forge
apiVersion: apps/v1
kind: Deployment
metadata:
  name: code-forge
  namespace: neural-hive-code-forge
spec:
  replicas: 1
  selector:
    matchLabels:
      app: code-forge
  template:
    metadata:
      labels:
        app: code-forge
    spec:
      containers:
      - name: stub
        image: nginx:alpine
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: code-forge
  namespace: neural-hive-code-forge
spec:
  selector:
    app: code-forge
  ports:
  - port: 80
---
# MCP Tool Catalog
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-tool-catalog
  namespace: neural-hive-mcp
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mcp-tool-catalog
  template:
    metadata:
      labels:
        app: mcp-tool-catalog
    spec:
      containers:
      - name: stub
        image: nginx:alpine
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: mcp-tool-catalog
  namespace: neural-hive-mcp
spec:
  selector:
    app: mcp-tool-catalog
  ports:
  - port: 80
---
# Self-Healing Engine
apiVersion: apps/v1
kind: Deployment
metadata:
  name: self-healing-engine
  namespace: neural-hive-healing
spec:
  replicas: 1
  selector:
    matchLabels:
      app: self-healing-engine
  template:
    metadata:
      labels:
        app: self-healing-engine
    spec:
      containers:
      - name: stub
        image: nginx:alpine
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: self-healing-engine
  namespace: neural-hive-healing
spec:
  selector:
    app: self-healing-engine
  ports:
  - port: 80
EOF

echo -e "${GREEN}✓ All Phase 2 service stubs deployed${NC}"
echo ""
echo "Waiting for pods to be ready..."
sleep 15

echo -e "\n${YELLOW}Verification:${NC}"
kubectl get deployments -n neural-hive-service-registry
kubectl get deployments -n neural-hive-orchestration -l app=execution-ticket-service
kubectl get deployments -n neural-hive-queen
kubectl get deployments -n neural-hive-workers
kubectl get deployments -n neural-hive-scouts
kubectl get deployments -n neural-hive-analysts
kubectl get deployments -n neural-hive-optimizers
kubectl get deployments -n neural-hive-guards
kubectl get deployments -n neural-hive-sla
kubectl get deployments -n neural-hive-code-forge
kubectl get deployments -n neural-hive-mcp
kubectl get deployments -n neural-hive-healing

echo -e "\n${GREEN}========================================="
echo "✓ Phase 2 stub services deployed!"
echo "=========================================${NC}"
