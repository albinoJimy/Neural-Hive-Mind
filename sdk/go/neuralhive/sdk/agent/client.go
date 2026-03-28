// Package neuralhive provides the Neural Hive-Mind Agent SDK for Go.
package neuralhive

import (
	"context"
	"crypto/tls"
	"fmt"
	"log"
	"math/rand"
	"os"
	"sync"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/keepalive"
	"google.golang.org/grpc/status"
)

const (
	// DefaultHeartbeatInterval is the default interval between heartbeats
	DefaultHeartbeatInterval = 30 * time.Second
	// DefaultGRPCTimeout is the default timeout for gRPC calls
	DefaultGRPCTimeout = 5 * time.Second
	// DefaultMaxRetries is the default maximum number of retries
	DefaultMaxRetries = 3
)

// AgentType represents the type of agent
type AgentType int32

const (
	AgentTypeUnspecified AgentType = iota
	AgentTypeWorker
	AgentTypeScout
	AgentTypeGuard
	AgentTypeAnalyst
)

// String returns the string representation of AgentType
func (a AgentType) String() string {
	switch a {
	case AgentTypeWorker:
		return "WORKER"
	case AgentTypeScout:
		return "SCOUT"
	case AgentTypeGuard:
		return "GUARD"
	case AgentTypeAnalyst:
		return "ANALYST"
	default:
		return "AGENT_TYPE_UNSPECIFIED"
	}
}

// ParseAgentType parses a string into AgentType
func ParseAgentType(s string) AgentType {
	switch s {
	case "WORKER":
		return AgentTypeWorker
	case "SCOUT":
		return AgentTypeScout
	case "GUARD":
		return AgentTypeGuard
	case "ANALYST":
		return AgentTypeAnalyst
	default:
		return AgentTypeUnspecified
	}
}

// AgentStatus represents the health status of an agent
type AgentStatus int32

const (
	AgentStatusUnspecified AgentStatus = iota
	AgentStatusHealthy
	AgentStatusUnhealthy
	AgentStatusDegraded
)

// AgentTelemetry holds telemetry data for an agent
type AgentTelemetry struct {
	SuccessRate       float64 `json:"success_rate"`
	AvgDurationMs     int64   `json:"avg_duration_ms"`
	TotalExecutions   int64   `json:"total_executions"`
	FailedExecutions  int64   `json:"failed_executions"`
	LastExecutionAt   int64   `json:"last_execution_at"`
}

// NewAgentTelemetry creates a new AgentTelemetry with default values
func NewAgentTelemetry() *AgentTelemetry {
	return &AgentTelemetry{
		SuccessRate:     0.0,
		AvgDurationMs:   0,
		TotalExecutions: 0,
		FailedExecutions: 0,
		LastExecutionAt: time.Now().Unix(),
	}
}

// AgentConfig holds configuration for the agent client
type AgentConfig struct {
	// RegistryEndpoint is the gRPC endpoint of the Service Registry
	RegistryEndpoint string `json:"registry_endpoint"`
	// Namespace is the Kubernetes namespace
	Namespace string `json:"namespace"`
	// Cluster is the cluster name
	Cluster string `json:"cluster"`
	// Version is the agent version
	Version string `json:"version"`
	// HeartbeatInterval is the interval between heartbeats
	HeartbeatInterval time.Duration `json:"heartbeat_interval"`
	// GRPCTimeout is the timeout for gRPC calls
	GRPCTimeout time.Duration `json:"grpc_timeout"`
	// MaxRetries is the maximum number of retries for gRPC calls
	MaxRetries int `json:"max_retries"`
	// TLSEnabled enables TLS for gRPC connections
	TLSEnabled bool `json:"tls_enabled"`
	// Log enables logging
	Log bool `json:"log"`
}

// DefaultConfig returns a new AgentConfig with default values
func DefaultConfig() *AgentConfig {
	return &AgentConfig{
		RegistryEndpoint:   envOrDefault("AGENT_REGISTRY_ENDPOINT", "service-registry:50051"),
		Namespace:          envOrDefault("AGENT_NAMESPACE", "default"),
		Cluster:            envOrDefault("AGENT_CLUSTER", "local"),
		Version:            envOrDefault("AGENT_VERSION", "1.0.0"),
		HeartbeatInterval:  parseDuration(envOrDefault("AGENT_HEARTBEAT_INTERVAL", "30s")),
		GRPCTimeout:        parseDuration(envOrDefault("AGENT_GRPC_TIMEOUT", "5s")),
		MaxRetries:         parseInt(envOrDefault("AGENT_GRPC_MAX_RETRIES", "3")),
		TLSEnabled:         parseBool(envOrDefault("AGENT_TLS_ENABLED", "false")),
		Log:                parseBool(envOrDefault("AGENT_LOG", "true")),
	}
}

// envOrDefault returns the environment variable or the default value
func envOrDefault(key, defaultValue string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultValue
}

// parseDuration parses a duration string
func parseDuration(s string) time.Duration {
	if d, err := time.ParseDuration(s); err == nil {
		return d
	}
	// Return default on error
	switch s {
	case "30", "30s":
		return DefaultHeartbeatInterval
	case "5", "5s":
		return DefaultGRPCTimeout
	default:
		return DefaultHeartbeatInterval
	}
}

// parseInt parses an integer string
func parseInt(s string) int {
	var i int
	if _, err := fmt.Sscanf(s, "%d", &i); err == nil {
		return i
	}
	return 3 // Default
}

// parseBool parses a boolean string
func parseBool(s string) bool {
	return s == "true" || s == "1" || s == "yes"
}

// AgentClient is the client for interacting with the Service Registry
type AgentClient struct {
	config       *AgentConfig
	conn         *grpc.ClientConn
	agentID      string
	token        string
	telemetry    *AgentTelemetry
	mu           sync.RWMutex
	heartbeatCtx context.Context
	cancelHB     context.CancelFunc
	hbWg         sync.WaitGroup
	logger       *log.Logger
}

// NewAgentClient creates a new AgentClient with the given configuration
func NewAgentClient(config *AgentConfig) *AgentClient {
	if config == nil {
		config = DefaultConfig()
	}

	return &AgentClient{
		config:    config,
		telemetry: NewAgentTelemetry(),
		logger:    log.New(os.Stdout, "[AgentClient] ", log.LstdFlags),
	}
}

// connect establishes a gRPC connection with retry logic
func (c *AgentClient) connect(ctx context.Context) error {
	var lastErr error

	for attempt := 0; attempt < c.config.MaxRetries; attempt++ {
		if attempt > 0 {
			// Exponential backoff with jitter
			backoff := time.Duration(1<<uint(attempt))*time.Second + time.Duration(rand.Int63n(1000))*time.Millisecond
			c.log("connection attempt %d failed, retrying in %v", attempt+1, backoff)
			select {
			case <-time.After(backoff):
			case <-ctx.Done():
				return ctx.Err()
			}
		}

		opts := []grpc.DialOption{
			grpc.WithKeepaliveParams(keepalive.ClientParameters{
				Time:                10 * time.Second,
				Timeout:             time.Second,
				PermitWithoutStream: true,
			}),
			grpc.WithDefaultCallOptions(
				grpc.MaxCallRecvMsgSize(50*1024*1024),
				grpc.MaxCallSendMsgSize(50*1024*1024),
			),
		}

		if c.config.TLSEnabled {
			opts = append(opts, grpc.WithTransportCredentials(credentials.NewTLS(&tls.Config{
				MinVersion: tls.VersionTLS12,
			})))
		} else {
			opts = append(opts, grpc.WithTransportCredentials(insecure.NewCredentials()))
		}

		conn, err := grpc.DialContext(ctx, c.config.RegistryEndpoint, opts...)
		if err == nil {
			c.conn = conn
			c.log("connected to service registry at %s", c.config.RegistryEndpoint)
			return nil
		}

		lastErr = err
		c.log("connection attempt %d failed: %v", attempt+1, err)
	}

	return fmt.Errorf("failed to connect after %d attempts: %w", c.config.MaxRetries, lastErr)
}

// Register registers the agent with the Service Registry
func (c *AgentClient) Register(ctx context.Context, agentType AgentType, capabilities []string, metadata map[string]string) (string, error) {
	if err := c.connect(ctx); err != nil {
		return "", fmt.Errorf("failed to connect: %w", err)
	}

	// Prepare metadata
	if metadata == nil {
		metadata = make(map[string]string)
	}
	metadata["namespace"] = c.config.Namespace
	metadata["cluster"] = c.config.Cluster
	metadata["version"] = c.config.Version

	// TODO: Call gRPC Register RPC when proto is compiled
	// For now, generate a mock agent ID
	c.agentID = fmt.Sprintf("agent-%s-%d", agentType.String(), time.Now().UnixNano())
	c.token = fmt.Sprintf("token-%s", c.agentID)

	c.log("registered agent %s (type: %s, capabilities: %v)", c.agentID, agentType, capabilities)

	// Start heartbeat
	c.startHeartbeat(ctx)

	return c.agentID, nil
}

// startHeartbeat starts the automatic heartbeat loop
func (c *AgentClient) startHeartbeat(ctx context.Context) {
	c.mu.Lock()
	if c.heartbeatCtx != nil {
		c.mu.Unlock()
		return // Already running
	}
	c.heartbeatCtx, c.cancelHB = context.WithCancel(ctx)
	c.mu.Unlock()

	c.hbWg.Add(1)
	go c.heartbeatLoop()
}

// heartbeatLoop runs the heartbeat loop
func (c *AgentClient) heartbeatLoop() {
	defer c.hbWg.Done()

	ticker := time.NewTicker(c.config.HeartbeatInterval)
	defer ticker.Stop()

	c.log("heartbeat started (interval: %v)", c.config.HeartbeatInterval)

	for {
		select {
		case <-c.heartbeatCtx.Done():
			c.log("heartbeat stopped")
			return
		case <-ticker.C:
			if err := c.sendHeartbeat(c.heartbeatCtx); err != nil {
				c.log("heartbeat failed: %v", err)
			}
		}
	}
}

// sendHeartbeat sends a heartbeat to the Service Registry
func (c *AgentClient) sendHeartbeat(ctx context.Context) error {
	c.mu.RLock()
	agentID := c.agentID
	telemetry := c.telemetry
	c.mu.RUnlock()

	if agentID == "" {
		return fmt.Errorf("agent not registered")
	}

	// TODO: Call gRPC Heartbeat RPC when proto is compiled
	c.log("heartbeat sent for agent %s (success_rate: %.2f, executions: %d)",
		agentID, telemetry.SuccessRate, telemetry.TotalExecutions)

	return nil
}

// UpdateTelemetry updates the telemetry for the next heartbeat
func (c *AgentClient) UpdateTelemetry(telemetry *AgentTelemetry) {
	c.mu.Lock()
	defer c.mu.Unlock()

	c.telemetry = telemetry
	c.log("telemetry updated: success_rate=%.2f, total=%d", telemetry.SuccessRate, telemetry.TotalExecutions)
}

// GetAgentID returns the current agent ID
func (c *AgentClient) GetAgentID() string {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.agentID
}

// GetTelemetry returns the current telemetry
func (c *AgentClient) GetTelemetry() *AgentTelemetry {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.telemetry
}

// Deregister deregisters the agent from the Service Registry
func (c *AgentClient) Deregister(ctx context.Context) error {
	c.mu.Lock()
	agentID := c.agentID
	c.mu.Unlock()

	if agentID == "" {
		c.log("deregister skipped: agent not registered")
		return nil
	}

	// Stop heartbeat
	c.stopHeartbeat()

	// TODO: Call gRPC Deregister RPC when proto is compiled
	c.log("agent %s deregistered", agentID)

	// Close connection
	if c.conn != nil {
		if err := c.conn.Close(); err != nil {
			c.log("warning: failed to close connection: %v", err)
		}
		c.conn = nil
	}

	c.mu.Lock()
	c.agentID = ""
	c.token = ""
	c.mu.Unlock()

	return nil
}

// stopHeartbeat stops the heartbeat loop
func (c *AgentClient) stopHeartbeat() {
	c.mu.Lock()
	if c.cancelHB != nil {
		c.cancelHB()
		c.cancelHB = nil
	}
	c.heartbeatCtx = nil
	c.mu.Unlock()

	// Wait for heartbeat goroutine to finish
	c.hbWg.Wait()
}

// Close is an alias for Deregister for compatibility with context interfaces
func (c *AgentClient) Close() error {
	return c.Deregister(context.Background())
}

// log logs a message if logging is enabled
func (c *AgentClient) log(format string, args ...interface{}) {
	if c.config.Log {
		c.logger.Printf(format, args...)
	}
}

// IsRetryableError checks if an error is retryable
func IsRetryableError(err error) bool {
	if err == nil {
		return false
	}

	st, ok := status.FromError(err)
	if !ok {
		return false
	}

	switch st.Code() {
	case codes.DeadlineExceeded,
		codes.Unavailable,
		codes.Aborted,
		codes.Internal,
		codes.Unknown:
		return true
	default:
		return false
	}
}
