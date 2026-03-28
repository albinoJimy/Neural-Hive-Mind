// Package main demonstrates a worker agent using the Neural Hive-Mind Go SDK
package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	neuralhive "github.com/neural-hive-mind/sdk/go"
)

func main() {
	log.SetFlags(log.LstdFlags | log.Lmicroseconds)
	log.Println("Starting Neural Hive-Mind Worker Agent...")

	// Create client with default configuration
	config := neuralhive.DefaultConfig()
	config.Log = true

	client := neuralhive.NewAgentClient(config)

	// Context for graceful shutdown
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Handle shutdown signals
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	// Register the worker agent
	log.Println("Registering with Service Registry...")
	agentID, err := client.Register(
		ctx,
		neuralhive.AgentTypeWorker,
		[]string{"query", "transform", "validate", "execute"},
		map[string]string{
			"region":      os.Getenv("REGION"),
			"environment": os.Getenv("ENV"),
			"pod":         os.Getenv("POD_NAME"),
		},
	)
	if err != nil {
		log.Fatalf("Failed to register agent: %v", err)
	}

	log.Printf("✓ Agent registered successfully: %s", agentID)

	// Start worker goroutines
	var wg sync.WaitGroup
	taskQueue := make(chan string, 10)

	// Start 3 worker goroutines
	for i := 1; i <= 3; i++ {
		wg.Add(1)
		go worker(ctx, client, &wg, i, taskQueue)
	}

	// Simulate incoming tasks
	go func() {
		for i := 0; ; i++ {
			select {
			case <-ctx.Done():
				return
			default:
				taskQueue <- fmt.Sprintf("task-%d", i)
				time.Sleep(2 * time.Second)
			}
		}
	}()

	// Wait for shutdown signal
	<-sigCh
	log.Println("\nShutdown signal received, stopping agent...")

	// Cancel context to stop all goroutines
	cancel()

	// Close task queue
	close(taskQueue)

	// Wait for workers to finish
	wg.Wait()

	// Update final telemetry
	client.UpdateTelemetry(&neuralhive.AgentTelemetry{
		SuccessRate:      0.98,
		AvgDurationMs:    85,
		TotalExecutions:  150,
		FailedExecutions: 3,
	})

	// Deregister agent
	log.Println("Deregistering from Service Registry...")
	if err := client.Deregister(ctx); err != nil {
		log.Printf("Warning: deregister failed: %v", err)
	} else {
		log.Println("✓ Agent deregistered successfully")
	}

	log.Println("Agent stopped. Goodbye!")
}

// worker processes tasks from the task queue
func worker(ctx context.Context, client *neuralhive.AgentClient, wg *sync.WaitGroup, id int, taskQueue <-chan string) {
	defer wg.Done()

	for {
		select {
		case <-ctx.Done():
			log.Printf("[Worker %d] Shutting down", id)
			return

		case task, ok := <-taskQueue:
			if !ok {
				log.Printf("[Worker %d] Task queue closed", id)
				return
			}

			log.Printf("[Worker %d] Processing: %s", id, task)

			// Simulate task processing
			start := time.Now()
			success := processTask(task)
			duration := time.Since(start)

			// Update telemetry after each task
			currentTelemetry := client.GetTelemetry()
			currentTelemetry.TotalExecutions++
			if !success {
				currentTelemetry.FailedExecutions++
			}
			currentTelemetry.AvgDurationMs = (currentTelemetry.AvgDurationMs*int64(currentTelemetry.TotalExecutions-1) + int64(duration.Milliseconds())) / currentTelemetry.TotalExecutions
			currentTelemetry.SuccessRate = float64(currentTelemetry.TotalExecutions-currentTelemetry.FailedExecutions) / float64(currentTelemetry.TotalExecutions)
			currentTelemetry.LastExecutionAt = time.Now().Unix()

			client.UpdateTelemetry(currentTelemetry)

			if success {
				log.Printf("[Worker %d] ✓ Completed %s in %v", id, task, duration)
			} else {
				log.Printf("[Worker %d] ✗ Failed %s after %v", id, task, duration)
			}
		}
	}
}

// processTask simulates task processing with random success/failure
func processTask(task string) bool {
	// Simulate processing time
	time.Sleep(time.Duration(500+time.Now().UnixNano()%1000) * time.Millisecond)

	// 95% success rate
	return (time.Now().UnixNano() % 100) < 95
}
