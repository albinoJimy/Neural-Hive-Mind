package neuralhive

import (
	"context"
	"os"
	"testing"
	"time"
)

func TestDefaultConfig(t *testing.T) {
	config := DefaultConfig()

	if config.RegistryEndpoint == "" {
		t.Error("RegistryEndpoint should not be empty")
	}
	if config.Namespace == "" {
		t.Error("Namespace should not be empty")
	}
	if config.HeartbeatInterval == 0 {
		t.Error("HeartbeatInterval should not be zero")
	}
	if config.GRPCTimeout == 0 {
		t.Error("GRPCTimeout should not be zero")
	}
}

func TestAgentConfig_EnvOverrides(t *testing.T) {
	// Set environment variables
	os.Setenv("AGENT_REGISTRY_ENDPOINT", "test-registry:6000")
	os.Setenv("AGENT_NAMESPACE", "test-ns")
	os.Setenv("AGENT_CLUSTER", "test-cluster")
	os.Setenv("AGENT_VERSION", "2.0.0")
	os.Setenv("AGENT_HEARTBEAT_INTERVAL", "60s")
	os.Setenv("AGENT_GRPC_TIMEOUT", "10s")
	os.Setenv("AGENT_GRPC_MAX_RETRIES", "5")
	os.Setenv("AGENT_TLS_ENABLED", "true")
	os.Setenv("AGENT_LOG", "false")
	defer func() {
		os.Unsetenv("AGENT_REGISTRY_ENDPOINT")
		os.Unsetenv("AGENT_NAMESPACE")
		os.Unsetenv("AGENT_CLUSTER")
		os.Unsetenv("AGENT_VERSION")
		os.Unsetenv("AGENT_HEARTBEAT_INTERVAL")
		os.Unsetenv("AGENT_GRPC_TIMEOUT")
		os.Unsetenv("AGENT_GRPC_MAX_RETRIES")
		os.Unsetenv("AGENT_TLS_ENABLED")
		os.Unsetenv("AGENT_LOG")
	}()

	config := DefaultConfig()

	if config.RegistryEndpoint != "test-registry:6000" {
		t.Errorf("Expected RegistryEndpoint 'test-registry:6000', got '%s'", config.RegistryEndpoint)
	}
	if config.Namespace != "test-ns" {
		t.Errorf("Expected Namespace 'test-ns', got '%s'", config.Namespace)
	}
	if config.Cluster != "test-cluster" {
		t.Errorf("Expected Cluster 'test-cluster', got '%s'", config.Cluster)
	}
	if config.Version != "2.0.0" {
		t.Errorf("Expected Version '2.0.0', got '%s'", config.Version)
	}
	if config.HeartbeatInterval != 60*time.Second {
		t.Errorf("Expected HeartbeatInterval 60s, got %v", config.HeartbeatInterval)
	}
	if config.GRPCTimeout != 10*time.Second {
		t.Errorf("Expected GRPCTimeout 10s, got %v", config.GRPCTimeout)
	}
	if config.MaxRetries != 5 {
		t.Errorf("Expected MaxRetries 5, got %d", config.MaxRetries)
	}
	if !config.TLSEnabled {
		t.Error("Expected TLSEnabled to be true")
	}
	if config.Log {
		t.Error("Expected Log to be false")
	}
}

func TestNewAgentTelemetry(t *testing.T) {
	telemetry := NewAgentTelemetry()

	if telemetry.SuccessRate != 0.0 {
		t.Errorf("Expected SuccessRate 0.0, got %f", telemetry.SuccessRate)
	}
	if telemetry.AvgDurationMs != 0 {
		t.Errorf("Expected AvgDurationMs 0, got %d", telemetry.AvgDurationMs)
	}
	if telemetry.TotalExecutions != 0 {
		t.Errorf("Expected TotalExecutions 0, got %d", telemetry.TotalExecutions)
	}
	if telemetry.FailedExecutions != 0 {
		t.Errorf("Expected FailedExecutions 0, got %d", telemetry.FailedExecutions)
	}
	if telemetry.LastExecutionAt == 0 {
		t.Error("Expected LastExecutionAt to be set")
	}
}

func TestAgentType_String(t *testing.T) {
	tests := []struct {
		agentType AgentType
		expected  string
	}{
		{AgentTypeUnspecified, "AGENT_TYPE_UNSPECIFIED"},
		{AgentTypeWorker, "WORKER"},
		{AgentTypeScout, "SCOUT"},
		{AgentTypeGuard, "GUARD"},
		{AgentTypeAnalyst, "ANALYST"},
	}

	for _, tt := range tests {
		t.Run(tt.expected, func(t *testing.T) {
			result := tt.agentType.String()
			if result != tt.expected {
				t.Errorf("AgentType.String() = %s, want %s", result, tt.expected)
			}
		})
	}
}

func TestParseAgentType(t *testing.T) {
	tests := []struct {
		input    string
		expected AgentType
	}{
		{"WORKER", AgentTypeWorker},
		{"SCOUT", AgentTypeScout},
		{"GUARD", AgentTypeGuard},
		{"ANALYST", AgentTypeAnalyst},
		{"INVALID", AgentTypeUnspecified},
		{"", AgentTypeUnspecified},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			result := ParseAgentType(tt.input)
			if result != tt.expected {
				t.Errorf("ParseAgentType(%q) = %v, want %v", tt.input, result, tt.expected)
			}
		})
	}
}

func TestNewAgentClient(t *testing.T) {
	client := NewAgentClient(nil)

	if client == nil {
		t.Fatal("Expected non-nil client")
	}
	if client.config == nil {
		t.Error("Expected config to be initialized")
	}
	if client.telemetry == nil {
		t.Error("Expected telemetry to be initialized")
	}
}

func TestNewAgentClient_WithConfig(t *testing.T) {
	config := &AgentConfig{
		RegistryEndpoint: "custom:6000",
		Namespace:         "custom",
		Cluster:           "custom-cluster",
		Version:           "2.0.0",
		Log:               false,
	}

	client := NewAgentClient(config)

	if client.config.RegistryEndpoint != "custom:6000" {
		t.Errorf("Expected RegistryEndpoint 'custom:6000', got '%s'", client.config.RegistryEndpoint)
	}
	if client.config.Namespace != "custom" {
		t.Errorf("Expected Namespace 'custom', got '%s'", client.config.Namespace)
	}
}

func TestUpdateTelemetry(t *testing.T) {
	client := NewAgentClient(&AgentConfig{Log: false})

	newTelemetry := &AgentTelemetry{
		SuccessRate:      0.95,
		AvgDurationMs:    150,
		TotalExecutions:  1000,
		FailedExecutions: 50,
		LastExecutionAt:  time.Now().Unix(),
	}

	client.UpdateTelemetry(newTelemetry)

	retrieved := client.GetTelemetry()
	if retrieved.SuccessRate != 0.95 {
		t.Errorf("Expected SuccessRate 0.95, got %f", retrieved.SuccessRate)
	}
	if retrieved.TotalExecutions != 1000 {
		t.Errorf("Expected TotalExecutions 1000, got %d", retrieved.TotalExecutions)
	}
}

func TestGetAgentID_BeforeRegister(t *testing.T) {
	client := NewAgentClient(&AgentConfig{Log: false})

	agentID := client.GetAgentID()
	if agentID != "" {
		t.Errorf("Expected empty agent ID before register, got '%s'", agentID)
	}
}

func TestDeregister_BeforeRegister(t *testing.T) {
	client := NewAgentClient(&AgentConfig{Log: false})
	ctx := context.Background()

	err := client.Deregister(ctx)
	if err != nil {
		t.Errorf("Expected no error when deregistering before register, got %v", err)
	}
}

func TestParseDuration(t *testing.T) {
	tests := []struct {
		input    string
		expected time.Duration
	}{
		{"30s", 30 * time.Second},
		{"5s", 5 * time.Second},
		{"1m", 60 * time.Second},
		{"100ms", 100 * time.Millisecond},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			result := parseDuration(tt.input)
			if result != tt.expected {
				t.Errorf("parseDuration(%q) = %v, want %v", tt.input, result, tt.expected)
			}
		})
	}
}

func TestParseInt(t *testing.T) {
	tests := []struct {
		input    string
		expected int
	}{
		{"3", 3},
		{"5", 5},
		{"10", 10},
		{"invalid", 3}, // Default on error
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			result := parseInt(tt.input)
			if result != tt.expected {
				t.Errorf("parseInt(%q) = %d, want %d", tt.input, result, tt.expected)
			}
		})
	}
}

func TestParseBool(t *testing.T) {
	tests := []struct {
		input    string
		expected bool
	}{
		{"true", true},
		{"1", true},
		{"yes", true},
		{"false", false},
		{"0", false},
		{"no", false},
		{"invalid", false},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			result := parseBool(tt.input)
			if result != tt.expected {
				t.Errorf("parseBool(%q) = %v, want %v", tt.input, result, tt.expected)
			}
		})
	}
}

func TestAgentClient_MutexProtection(t *testing.T) {
	client := NewAgentClient(&AgentConfig{Log: false})

	// Test concurrent access to telemetry
	done := make(chan bool)
	for i := 0; i < 10; i++ {
		go func() {
			client.UpdateTelemetry(&AgentTelemetry{
				SuccessRate: 0.9,
			})
			client.GetTelemetry()
			client.GetAgentID()
			done <- true
		}()
	}

	// Wait for all goroutines
	for i := 0; i < 10; i++ {
		<-done
	}
}
