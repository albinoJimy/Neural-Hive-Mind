# Neural Hive-Mind Service Health Check Templates

This directory contains standardized templates for implementing health checks across all Neural Hive-Mind services.

## Overview

All Neural Hive-Mind services should implement consistent health check patterns for:
- Kubernetes liveness probes (`/health`)
- Kubernetes readiness probes (`/ready`)
- Component-specific health checks (`/health/{component}`)
- Prometheus metrics integration
- Centralized logging

## Usage

### 1. Basic Setup

```python
from fastapi import FastAPI
from neural_hive_observability.templates.service_health_template import ServiceHealthManager, setup_health_endpoints

app = FastAPI()

# Initialize health manager
health_manager = ServiceHealthManager(
    service_name="your-service-name",
    component="your-component",  # gateway, processor, orchestrator, etc.
    layer="your-layer",         # experiencia, cognicao, orquestracao, etc.
    version="1.0.0"
)

# Add health checks for your components
health_manager.add_redis_check(your_redis_client)
health_manager.add_kafka_check(lambda: your_kafka_producer.is_ready())
health_manager.add_custom_check("custom_component", lambda: check_custom_health())

# Mark as initialized
health_manager.mark_initialized()

# Setup standardized endpoints
setup_health_endpoints(app, health_manager, critical_checks=["redis", "kafka"])
```

### 2. Service-Specific Examples

#### Gateway Service
```python
from neural_hive_observability.templates.service_health_template import setup_gateway_health

health_manager = setup_gateway_health(
    app,
    redis_client=redis_client,
    kafka_producer=kafka_producer,
    asr_pipeline=asr_pipeline,
    nlu_pipeline=nlu_pipeline,
    oauth2_validator=oauth2_validator
)
```

#### Processor Service
```python
from neural_hive_observability.templates.service_health_template import setup_processor_health

health_manager = setup_processor_health(
    app,
    database_conn=database_connection,
    message_queue=message_queue
)
```

## Health Check Types

### 1. Liveness Probe (`/health`)
- Returns overall service health status
- Includes all component statuses and details
- HTTP status codes:
  - `200`: Service is healthy or degraded
  - `503`: Service is unhealthy

### 2. Readiness Probe (`/ready`)
- Checks if service is ready to accept traffic
- Only checks critical components
- HTTP status codes:
  - `200`: Service is ready
  - `503`: Service is not ready

### 3. Component Health (`/health/{component}`)
- Check specific component health
- Returns detailed component information
- HTTP status codes:
  - `200`: Component is healthy
  - `404`: Component not found
  - `503`: Component is unhealthy

## Response Formats

### Health Response
```json
{
  "status": "healthy|degraded|unhealthy",
  "timestamp": "2023-09-26T10:30:00.000Z",
  "version": "1.0.0",
  "service_name": "gateway-intencoes",
  "neural_hive_component": "gateway",
  "neural_hive_layer": "experiencia",
  "components": {
    "redis": {
      "status": "healthy",
      "message": "Redis connection OK",
      "duration_seconds": 0.002,
      "timestamp": 1695721800.123,
      "details": {}
    },
    "kafka": {
      "status": "healthy",
      "message": "Kafka producer ready",
      "duration_seconds": 0.001,
      "timestamp": 1695721800.124,
      "details": {}
    }
  }
}
```

### Readiness Response
```json
{
  "status": "ready|not_ready",
  "timestamp": "2023-09-26T10:30:00.000Z",
  "service_name": "gateway-intencoes",
  "neural_hive_component": "gateway"
}
```

## Kubernetes Integration

### Deployment Configuration
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: your-service
spec:
  template:
    spec:
      containers:
      - name: your-service
        ports:
        - containerPort: 8000
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
          timeoutSeconds: 3
          successThreshold: 1
          failureThreshold: 3
```

## Neural Hive-Mind Standards

### Component Types
- `gateway`: API gateways and entry points
- `processor`: Data and intent processors
- `orchestrator`: Workflow orchestrators
- `storage`: Storage services
- `ml-model`: Machine learning models

### Layer Types
- `experiencia`: User experience layer
- `cognicao`: Cognitive processing layer
- `orquestracao`: Orchestration layer
- `dados`: Data layer
- `observabilidade`: Observability layer
- `resiliencia`: Resilience layer

### Metrics Integration
Health checks automatically expose metrics to Prometheus:
- `neural_hive_health_check_status`: Component health status (0/1)
- `neural_hive_health_check_duration_seconds`: Health check duration
- `neural_hive_health_check_total`: Total health checks performed

### Correlation Context
Health checks are automatically traced and correlated with:
- Service name and version
- Neural Hive component and layer
- Request correlation IDs when available

## Best Practices

1. **Always use the standardized templates** for consistency
2. **Define critical components** for readiness probes carefully
3. **Keep health checks fast** (< 1 second per check)
4. **Implement proper timeouts** for external dependencies
5. **Log health check failures** for debugging
6. **Use appropriate HTTP status codes** for Kubernetes
7. **Include meaningful error messages** in responses
8. **Test health checks** in your CI/CD pipeline
9. **Monitor health check metrics** in production
10. **Update health checks** when adding new dependencies