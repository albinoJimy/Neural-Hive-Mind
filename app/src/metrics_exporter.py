#!/usr/bin/env python3
"""
Prometheus Metrics Exporter for Gateway de Intenções

This module runs a dedicated Prometheus HTTP server on port 8080 to expose
metrics in Prometheus text format. It integrates with the existing metrics
defined in observability/metrics.py.
"""

import logging
import threading
from prometheus_client import start_http_server, Counter, Histogram, Gauge
from typing import Optional

# Import existing metrics from observability module
from observability.metrics import (
    intent_counter as neural_hive_requests_total,
    latency_histogram as neural_hive_request_duration_seconds,
    confidence_histogram as neural_hive_intent_confidence,
    active_connections as neural_hive_active_connections,
    low_confidence_routed_counter,
    record_too_large_counter,
)

logger = logging.getLogger(__name__)

# Global variable to track if the server is running
_metrics_server_started = False
_metrics_server_thread: Optional[threading.Thread] = None


def start_metrics_server(port: int = 8080, host: str = "0.0.0.0") -> None:
    """
    Start the Prometheus HTTP server in a separate thread.

    Args:
        port: Port to listen on (default: 8080)
        host: Host to bind to (default: 0.0.0.0)
    """
    global _metrics_server_started, _metrics_server_thread

    if _metrics_server_started:
        logger.warning(f"Metrics server already running on port {port}")
        return

    def _run_server():
        """Run the metrics server in a separate thread."""
        try:
            logger.info(f"Starting Prometheus metrics server on {host}:{port}")
            start_http_server(port=port, addr=host)
            logger.info(f"Prometheus metrics server started successfully on port {port}")
        except Exception as e:
            logger.error(f"Failed to start Prometheus metrics server: {e}")
            raise

    # Start the server in a daemon thread
    _metrics_server_thread = threading.Thread(target=_run_server, daemon=True)
    _metrics_server_thread.start()
    _metrics_server_started = True
    logger.info(f"Prometheus metrics server thread started for port {port}")


def is_metrics_server_running() -> bool:
    """
    Check if the metrics server is running.

    Returns:
        True if the server is running, False otherwise.
    """
    return _metrics_server_started


def get_metrics_summary() -> dict:
    """
    Get a summary of available metrics.

    Returns:
        Dictionary containing metrics metadata.
    """
    return {
        "neural_hive_requests_total": {
            "type": "Counter",
            "description": "Total de requisições processadas no Neural Hive-Mind",
            "labels": ["neural_hive_component", "neural_hive_layer", "domain", "channel", "status"],
        },
        "neural_hive_request_duration_seconds": {
            "type": "Histogram",
            "description": "Duração da captura de intenções (Fluxo A)",
            "labels": ["neural_hive_component", "neural_hive_layer", "domain", "channel"],
            "buckets": [0.01, 0.025, 0.05, 0.1, 0.15, 0.2, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        },
        "neural_hive_intent_confidence": {
            "type": "Histogram",
            "description": "Distribuição de confiança das intenções",
            "labels": ["neural_hive_component", "neural_hive_layer", "domain", "channel"],
            "buckets": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        },
        "neural_hive_active_connections": {
            "type": "Gauge",
            "description": "Conexões ativas no gateway",
            "labels": [],
        },
    }


if __name__ == "__main__":
    # Test the metrics server when running this module directly
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    print("Starting standalone metrics server...")
    print("Metrics will be available at http://localhost:8080/metrics")
    print("Press Ctrl+C to stop")
    
    try:
        start_metrics_server()
        
        # Keep the main thread alive
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down metrics server...")
    except Exception as e:
        print(f"Error: {e}")
        import sys
        sys.exit(1)
