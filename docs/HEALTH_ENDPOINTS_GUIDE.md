# Health Endpoints Guide

## Overview

Todos os serviços Neural Hive-Mind expõem endpoints padronizados para health checks utilizados pelo Kubernetes.

## Endpoints

### `/health` - Liveness Probe

Verifica se o processo está vivo. Se falhar, o Kubernetes reinicia o container.

**Response:**
```json
{
  "status": "healthy",
  "service": "service-name",
  "version": "1.0.0"
}
```

### `/ready` - Readiness Probe

Verifica se o serviço está pronto para receber tráfego.

**Response:**
```json
{
  "ready": true,
  "checks": {
    "mongodb": "connected",
    "redis": "connected"
  }
}
```

### `/health/startup` - Startup Probe

Indica que o serviço completou sua inicialização.

**Response:**
```json
{
  "status": "started",
  "service": "service-name",
  "version": "1.0.0",
  "started_at": "2026-04-14T10:30:00Z"
}
```

## Kubernetes Probes Configuration

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: http
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /ready
    port: http
  initialDelaySeconds: 10
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 3

startupProbe:
  httpGet:
    path: /health/startup
    port: http
  initialDelaySeconds: 10
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 6
```
