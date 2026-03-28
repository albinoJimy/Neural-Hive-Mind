# Neural Hive-Mind Agent SDK - Multi-Language Specification

**Version:** 1.0.0
**Status:** Final
**Date:** 2026-03-28

## Overview

This document defines the language-agnostic specification for the Neural Hive-Mind Agent SDK, enabling integration with the Service Registry using gRPC.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Agent SDK Layer                         │
├─────────────────────────────────────────────────────────────┤
│  Language   │  Client  │  Config  │  Telemetry  │  Types   │
├──────────────┼──────────┼─────────┼─────────────┼──────────┤
│  Python      │    ✅    │   ✅    │     ✅      │    ✅    │
│  Go          │    ✅    │   ✅    │     ✅      │    ✅    │
│  Java        │    🚧    │   🚧    │     🚧      │    🚧    │
│  TypeScript  │    📋    │   📋    │     📋      │    📋    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              gRPC AgentService (agent_service.proto)         │
├─────────────────────────────────────────────────────────────┤
│  Register │ Heartbeat │ Deregister │ GetStatus              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Service Registry (service-registry:50051)       │
└─────────────────────────────────────────────────────────────┘
```

## Protocol Buffer Definition

### AgentType Enum

```protobuf
enum AgentType {
  AGENT_TYPE_UNSPECIFIED = 0;
  WORKER = 1;
  SCOUT = 2;
  GUARD = 3;
  ANALYST = 4;
}
```

### AgentStatus Enum

```protobuf
enum AgentStatus {
  AGENT_STATUS_UNSPECIFIED = 0;
  HEALTHY = 1;
  UNHEALTHY = 2;
  DEGRADED = 3;
}
```

### AgentTelemetry Message

```protobuf
message AgentTelemetry {
  double success_rate = 1;        // 0.0 to 1.0
  int64 avg_duration_ms = 2;
  int64 total_executions = 3;
  int64 failed_executions = 4;
  int64 last_execution_at = 5;   // Unix timestamp
}
```

### AgentInfo Message

```protobuf
message AgentInfo {
  string agent_id = 1;
  AgentType agent_type = 2;
  repeated string capabilities = 3;
  map<string, string> metadata = 4;
  AgentTelemetry telemetry = 5;
  AgentStatus status = 6;
  int64 registered_at = 7;
  int64 last_seen = 8;
  string namespace = 9;
  string cluster = 10;
  string version = 11;
  int32 schema_version = 12;
}
```

### RPC Operations

#### Register

**Request:** `RegisterRequest`
```protobuf
message RegisterRequest {
  AgentType agent_type = 1;
  repeated string capabilities = 2;
  map<string, string> metadata = 3;
  string namespace = 4;
  string cluster = 5;
  string version = 6;
  AgentTelemetry telemetry = 7;
}
```

**Response:** `RegisterResponse`
```protobuf
message RegisterResponse {
  string agent_id = 1;
  string registration_token = 2;
  int64 registered_at = 3;
}
```

#### Heartbeat

**Request:** `HeartbeatRequest`
```protobuf
message HeartbeatRequest {
  string agent_id = 1;
  AgentTelemetry telemetry = 2;
}
```

**Response:** `HeartbeatResponse`
```protobuf
message HeartbeatResponse {
  AgentStatus status = 1;
  int64 last_seen = 2;
}
```

#### Deregister

**Request:** `DeregisterRequest`
```protobuf
message DeregisterRequest {
  string agent_id = 1;
}
```

**Response:** `DeregisterResponse`
```protobuf
message DeregisterResponse {
  bool success = 1;
}
```

#### GetStatus

**Request:** `GetStatusRequest`
```protobuf
message GetStatusRequest {
  string agent_id = 1;
}
```

**Response:** `GetStatusResponse`
```protobuf
message GetStatusResponse {
  AgentInfo agent = 1;
}
```

## Client Implementation Requirements

### Configuration

All SDK clients MUST support the following configuration:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| REGISTRY_ENDPOINT | string | "service-registry:50051" | gRPC endpoint |
| NAMESPACE | string | "default" | Kubernetes namespace |
| CLUSTER | string | "local" | Cluster name |
| VERSION | string | "1.0.0" | Agent version |
| HEARTBEAT_INTERVAL | int | 30 | Heartbeat interval (seconds) |
| GRPC_TIMEOUT | int | 5 | gRPC timeout (seconds) |
| GRPC_MAX_RETRIES | int | 3 | Max retries for gRPC calls |

### Telemetry

All SDK clients MUST support telemetry tracking:

```typescript
interface AgentTelemetry {
  success_rate: number;       // 0.0 to 1.0
  avg_duration_ms: number;
  total_executions: number;
  failed_executions: number;
  last_execution_at: number;   // Unix timestamp
}
```

### Lifecycle

All SDK clients MUST implement:

1. **Register** - Connect and register with Service Registry
2. **Heartbeat** - Automatic heartbeat loop
3. **Update Telemetry** - Update telemetry for next heartbeat
4. **Deregister** - Clean deregistration on shutdown
5. **Context Manager** - Auto-register/deregister on scope entry/exit

## Error Handling

### gRPC Status Codes

| Code | When to Use | Client Action |
|------|-------------|---------------|
| OK | Success | Continue |
| INVALID_ARGUMENT | Invalid request parameters | Validate inputs, retry with correct params |
| UNAUTHENTICATED | Missing/invalid auth token | Refresh token, retry |
| ALREADY_EXISTS | Agent already registered | Use existing agent_id |
| NOT_FOUND | Agent not found | Register new agent |
| UNAVAILABLE | Service Registry down | Retry with backoff |
| DEADLINE_EXCEEDED | Request timeout | Retry with longer timeout |
| INTERNAL | Server error | Log and retry |

### Retry Strategy

- **Exponential backoff**: 2^n seconds between retries
- **Max retries**: 3 (configurable)
- **Jitter**: Add random ±1s to avoid thundering herd

## Language-Specific Guidelines

### Go Client

See `sdk/go/README.md` for implementation details.

**Key requirements:**
- Use `google.golang.org/grpc`
- Context-based cancellation
- Goroutine-safe heartbeat
- Graceful shutdown with signal handling

**Package structure:**
```
neuralhive/sdk/
├── agent/
│   ├── client.go       # AgentClient implementation
│   ├── config.go       # AgentConfig struct
│   ├── telemetry.go    # AgentTelemetry struct
│   └── types.go        # AgentType enum, etc.
└── proto/
    └── agent_service.pb.go
```

### Java Client

**Key requirements:**
- Use `io.grpc:grpc-netty`
- ManagedChannel with proper shutdown
- ScheduledExecutorService for heartbeat
- Reactor/Core support for reactive streams

**Package structure:**
```
com.neuralhive.sdk/
├── agent/
│   ├── AgentClient.java
│   ├── AgentConfig.java
│   ├── AgentTelemetry.java
│   └── AgentType.java
└── proto/
    └── AgentServiceGrpc.java
```

### TypeScript/Node Client

**Key requirements:**
- Use `@grpc/grpc-js`
- EventEmitter-based lifecycle
- setInterval for heartbeat
- Promise-based API with async/await

**Package structure:**
```
@neuralhive/sdk/
├── agent/
│   ├── client.ts
│   ├── config.ts
│   ├── telemetry.ts
│   └── types.ts
└── proto/
    └── agent_service_grpc_pb.ts
```

## Testing Requirements

All language implementations MUST include:

1. **Unit Tests** - Mock gRPC channel, test client logic
2. **Integration Tests** - Real gRPC connection to test Service Registry
3. **Contract Tests** - Validate proto message structure
4. **Lifecycle Tests** - Register → Heartbeat → Deregister
5. **Error Tests** - Connection failures, timeouts, invalid responses

## Deployment

### Environment Variables

All clients MUST support environment variable overrides:

```bash
# Common
AGENT_REGISTRY_ENDPOINT=localhost:50051
AGENT_NAMESPACE=default
AGENT_CLUSTER=local
AGENT_VERSION=1.0.0
AGENT_HEARTBEAT_INTERVAL=30
AGENT_GRPC_TIMEOUT=5
AGENT_GRPC_MAX_RETRIES=3
```

### Docker Integration

```dockerfile
# Go example
FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN go build -o agent

FROM alpine:latest
RUN apk --no-cache add ca-certificates
WORKDIR /root/
COPY --from=builder /app/agent .
CMD ["./agent"]
```

## Version Compatibility

| SDK Version | Proto Version | Service Registry |
|-------------|----------------|------------------|
| 1.0.0 | 1.0.0 | 1.0.0+ |

## References

- **Proto Definition:** `/libraries/python/neural_hive_agent_sdk/proto/agent_service.proto`
- **Python SDK:** `/libraries/python/neural_hive_agent_sdk/`
- **Go SDK:** `/sdk/go/` (pending)
- **Service Registry:** `/services/service-registry/`
