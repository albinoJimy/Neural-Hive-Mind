# Neural Hive-Mind Agent SDK for Go

**Version:** 1.0.0
**Status:** Alpha (Core functionality complete, gRPC integration pending proto compilation)

## Overview

The Go SDK provides a type-safe, idiomatic Go client for integrating agents with the Neural Hive-Mind Service Registry.

## Installation

```bash
go get github.com/neural-hive-mind/sdk/go
```

## Quick Start

```go
package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"

	neuralhive "github.com/neural-hive-mind/sdk/go"
)

func main() {
	// Create client with default configuration
	client := neuralhive.NewAgentClient(nil)

	// Context for cancellation
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Handle shutdown signals
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	// Register agent
	agentID, err := client.Register(
		ctx,
		neuralhive.AgentTypeWorker,
		[]string{"query", "transform", "validate"},
		map[string]string{"region": "us-east-1"},
	)
	if err != nil {
		log.Fatalf("Failed to register: %v", err)
	}

	log.Printf("Agent registered: %s", agentID)

	// Update telemetry
	client.UpdateTelemetry(&neuralhive.AgentTelemetry{
		SuccessRate:      0.95,
		AvgDurationMs:    150,
		TotalExecutions:  1000,
		FailedExecutions: 50,
	})

	// Wait for shutdown signal
	<-sigCh
	log.Println("Shutting down...")

	// Deregister
	if err := client.Deregister(ctx); err != nil {
		log.Fatalf("Failed to deregister: %v", err)
	}

	log.Println("Agent stopped")
}
```

## Configuration

### Default Configuration

```go
client := neuralhive.NewAgentClient(nil)
```

Default values are loaded from environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_REGISTRY_ENDPOINT` | `service-registry:50051` | gRPC endpoint |
| `AGENT_NAMESPACE` | `default` | Kubernetes namespace |
| `AGENT_CLUSTER` | `local` | Cluster name |
| `AGENT_VERSION` | `1.0.0` | Agent version |
| `AGENT_HEARTBEAT_INTERVAL` | `30s` | Heartbeat interval |
| `AGENT_GRPC_TIMEOUT` | `5s` | gRPC timeout |
| `AGENT_GRPC_MAX_RETRIES` | `3` | Max retries |
| `AGENT_TLS_ENABLED` | `false` | Enable TLS |
| `AGENT_LOG` | `true` | Enable logging |

### Custom Configuration

```go
config := &neuralhive.AgentConfig{
	RegistryEndpoint:  "custom-registry:6000",
	Namespace:         "production",
	Cluster:           "us-east-1",
	Version:           "2.0.0",
	HeartbeatInterval: 20 * time.Second,
	GRPCTimeout:       10 * time.Second,
	MaxRetries:        5,
	TLSEnabled:        true,
	Log:               true,
}

client := neuralhive.NewAgentClient(config)
```

## API Reference

### AgentType

```go
const (
	AgentTypeUnspecified neuralhive.AgentType = iota
	AgentTypeWorker
	AgentTypeScout
	AgentTypeGuard
	AgentTypeAnalyst
)
```

### AgentTelemetry

```go
type AgentTelemetry struct {
	SuccessRate      float64 // 0.0 to 1.0
	AvgDurationMs    int64
	TotalExecutions  int64
	FailedExecutions int64
	LastExecutionAt  int64  // Unix timestamp
}
```

### AgentClient Methods

#### Register

```go
func (c *AgentClient) Register(
	ctx context.Context,
	agentType AgentType,
	capabilities []string,
	metadata map[string]string,
) (string, error)
```

Registers the agent with the Service Registry and returns the agent ID.

#### UpdateTelemetry

```go
func (c *AgentClient) UpdateTelemetry(telemetry *AgentTelemetry)
```

Updates the telemetry for the next heartbeat.

#### Deregister

```go
func (c *AgentClient) Deregister(ctx context.Context) error
```

Deregisters the agent and stops the heartbeat loop.

#### GetAgentID

```go
func (c *AgentClient) GetAgentID() string
```

Returns the current agent ID.

#### GetTelemetry

```go
func (c *AgentClient) GetTelemetry() *AgentTelemetry
```

Returns the current telemetry.

## Agent Types

| Type | Description |
|------|-------------|
| `AgentTypeWorker` | Executes tasks (query, transform, validate) |
| `AgentTypeScout` | Explores and discovers resources |
| `AgentTypeGuard` | Validates and enforces policies |
| `AgentTypeAnalyst` | Analyzes data and generates insights |

## Error Handling

The SDK automatically retries on retryable errors:

- `DEADLINE_EXCEEDED`
- `UNAVAILABLE`
- `ABORTED`
- `INTERNAL`
- `UNKNOWN`

Retry strategy: exponential backoff (2^n seconds) with jitter.

```go
if err != nil {
	if neuralhive.IsRetryableError(err) {
		// Retry recommended
	}
}
```

## Examples

### Worker Agent

```go
package main

import (
	"context"
	"log"
	"time"

	neuralhive "github.com/neural-hive-mind/sdk/go"
)

func main() {
	client := neuralhive.NewAgentClient(nil)
	ctx := context.Background()

	agentID, err := client.Register(
		ctx,
		neuralhive.AgentTypeWorker,
		[]string{"query", "transform"},
		nil,
	)
	if err != nil {
		log.Fatal(err)
	}

	// Simulate work
	for i := 0; i < 10; i++ {
		time.Sleep(1 * time.Second)

		client.UpdateTelemetry(&neuralhive.AgentTelemetry{
			SuccessRate:      0.95,
			AvgDurationMs:    100,
			TotalExecutions:  int64(i + 1),
			FailedExecutions: 0,
		})
	}

	client.Deregister(ctx)
	log.Printf("Worker %s completed", agentID)
}
```

### Scout Agent with Custom Config

```go
package main

import (
	"context"
	"log"
	"time"

	neuralhive "github.com/neural-hive-mind/sdk/go"
)

func main() {
	config := &neuralhive.AgentConfig{
		RegistryEndpoint: "service-registry.production.svc.cluster.local:50051",
		Namespace:         "production",
		Cluster:           "us-prod",
		Version:           "1.2.0",
		HeartbeatInterval: 15 * time.Second,
		TLSEnabled:        true,
	}

	client := neuralhive.NewAgentClient(config)
	ctx := context.Background()

	agentID, err := client.Register(
		ctx,
		neuralhive.AgentTypeScout,
		[]string{"explore", "discover", "scan"},
		map[string]string{
			"region":      "us-west-2",
			"environment": "production",
		},
	)
	if err != nil {
		log.Fatal(err)
	}

	log.Printf("Scout agent %s exploring...", agentID)
	time.Sleep(30 * time.Second)

	client.Deregister(ctx)
}
```

## Testing

```go
package neuralhive_test

import (
	"context"
	"testing"
	"time"

	neuralhive "github.com/neural-hive-mind/sdk/go"
)

func TestAgentClient_Register(t *testing.T) {
	client := neuralhive.NewAgentClient(&neuralhive.AgentConfig{
		Log: false, // Disable logs in tests
	})
	ctx := context.Background()

	agentID, err := client.Register(
		ctx,
		neuralhive.AgentTypeWorker,
		[]string{"test"},
		nil,
	)

	if err != nil {
		t.Fatalf("Register failed: %v", err)
	}

	if agentID == "" {
		t.Error("Expected non-empty agent ID")
	}

	client.Deregister(ctx)
}

func TestAgentTelemetry(t *testing.T) {
	telemetry := neuralhive.NewAgentTelemetry()

	if telemetry.SuccessRate != 0.0 {
		t.Errorf("Expected SuccessRate 0.0, got %f", telemetry.SuccessRate)
	}

	telemetry.SuccessRate = 0.95
	telemetry.TotalExecutions = 100

	if telemetry.SuccessRate != 0.95 {
		t.Errorf("Expected SuccessRate 0.95, got %f", telemetry.SuccessRate)
	}
}

func TestParseAgentType(t *testing.T) {
	tests := []struct {
		input    string
		expected neuralhive.AgentType
	}{
		{"WORKER", neuralhive.AgentTypeWorker},
		{"SCOUT", neuralhive.AgentTypeScout},
		{"GUARD", neuralhive.AgentTypeGuard},
		{"ANALYST", neuralhive.AgentTypeAnalyst},
		{"INVALID", neuralhive.AgentTypeUnspecified},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			result := neuralhive.ParseAgentType(tt.input)
			if result != tt.expected {
				t.Errorf("ParseAgentType(%q) = %v, want %v", tt.input, result, tt.expected)
			}
		})
	}
}
```

## Building

```bash
# Build the SDK
cd sdk/go
go build ./...

# Run tests
go test ./...

# Run with coverage
go test -cover ./...
```

## Docker

```dockerfile
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

## Status

- ✅ Configuration management
- ✅ AgentClient lifecycle
- ✅ Heartbeat loop
- ✅ Telemetry tracking
- ✅ Error handling with retry
- ✅ Environment variable support
- ⏳ gRPC proto compilation (pending)
- ⏳ Integration tests (pending)

## See Also

- [Python SDK](../../../libraries/python/neural_hive_agent_sdk/)
- [Service Registry](../../../services/service-registry/)
- [Multi-Language Spec](../../../docs/sdk/MULTI_LANGUAGE_SDK.md)
