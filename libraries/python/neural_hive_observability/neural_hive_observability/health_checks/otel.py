"""
OTEL (OpenTelemetry) pipeline health checks for Neural Hive-Mind.

Validates OTEL Collector connectivity and trace pipeline functionality.
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

import aiohttp

from ..health import HealthCheck, HealthCheckResult, HealthStatus

logger = logging.getLogger(__name__)


class OTELPipelineHealthCheck(HealthCheck):
    """
    Health check for OTEL (OpenTelemetry) pipeline validation.

    Verifies:
    - Connectivity to OTEL Collector
    - Ability to send traces
    - Optional Jaeger backend validation
    """

    def __init__(
        self,
        otel_endpoint: str,
        service_name: str,
        name: str = 'otel_pipeline',
        timeout_seconds: float = 5.0,
        verify_trace_export: bool = True,
    ):
        """
        Initialize OTEL pipeline health check.

        Args:
            otel_endpoint: OTEL Collector endpoint (e.g., http://otel-collector:4317)
            service_name: Name of this service for trace attribution
            name: Name of this health check
            timeout_seconds: Timeout for health check operations
            verify_trace_export: Whether to send a test span to verify export
        """
        super().__init__(name=name, timeout_seconds=timeout_seconds)
        self.otel_endpoint = otel_endpoint
        self.service_name = service_name
        self.verify_trace_export = verify_trace_export

        # Parse endpoint to determine protocol
        self._is_grpc = ':4317' in otel_endpoint or 'grpc' in otel_endpoint.lower()
        self._http_endpoint = self._derive_http_endpoint(otel_endpoint)

    def _derive_http_endpoint(self, endpoint: str) -> str:
        """Derive HTTP endpoint from OTEL endpoint."""
        # If gRPC endpoint (4317), also check HTTP endpoint (4318)
        if ':4317' in endpoint:
            return endpoint.replace(':4317', ':4318')
        elif ':4318' in endpoint:
            return endpoint
        else:
            # Assume HTTP endpoint
            return endpoint

    async def check(self) -> HealthCheckResult:
        """
        Execute health check for OTEL pipeline.

        Verifies:
        1. OTEL Collector is reachable
        2. HTTP traces endpoint is responding
        3. (Optional) Send test span and verify acceptance

        Returns:
            HealthCheckResult with pipeline validation details
        """
        start_time = time.time()

        try:
            # Check collector health endpoint
            collector_healthy = await self._check_collector_health()

            details = {
                'otel_endpoint': self.otel_endpoint,
                'service_name': self.service_name,
                'collector_reachable': collector_healthy,
            }

            if not collector_healthy:
                return self._create_result(
                    HealthStatus.UNHEALTHY,
                    'OTEL Collector not reachable',
                    details=details,
                    start_time=start_time
                )

            # Optionally verify trace export
            if self.verify_trace_export:
                export_success = await self._verify_trace_export()
                details['trace_export_verified'] = export_success

                if not export_success:
                    return self._create_result(
                        HealthStatus.DEGRADED,
                        'OTEL Collector reachable but trace export failed',
                        details=details,
                        start_time=start_time
                    )

            return self._create_result(
                HealthStatus.HEALTHY,
                'OTEL pipeline operational',
                details=details,
                start_time=start_time
            )

        except asyncio.TimeoutError:
            return self._create_result(
                HealthStatus.UNHEALTHY,
                f"Timeout checking OTEL pipeline ({self.timeout_seconds}s)",
                start_time=start_time
            )
        except Exception as e:
            logger.error(f"Error checking OTEL pipeline: {e}")
            return self._create_result(
                HealthStatus.UNHEALTHY,
                f"Error checking OTEL pipeline: {str(e)}",
                start_time=start_time
            )

    async def _check_collector_health(self) -> bool:
        """Check if OTEL Collector is healthy via HTTP endpoint."""
        try:
            # Try health endpoint first
            health_url = f"{self._http_endpoint.rstrip('/')}/health"

            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(
                        health_url,
                        timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)
                    ) as response:
                        if response.status == 200:
                            return True
                except aiohttp.ClientError:
                    pass

                # Try metrics endpoint as fallback
                metrics_url = self._http_endpoint.replace(':4318', ':8888').rstrip('/') + '/metrics'
                try:
                    async with session.get(
                        metrics_url,
                        timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)
                    ) as response:
                        return response.status == 200
                except aiohttp.ClientError:
                    pass

            return False

        except Exception as e:
            logger.debug(f"OTEL collector health check error: {e}")
            return False

    async def _verify_trace_export(self) -> bool:
        """
        Verify trace export by sending a test span.

        Note: This sends a minimal test span to verify the pipeline is working.
        """
        try:
            # Build minimal OTLP trace payload
            trace_payload = self._build_test_trace()

            # Send to OTLP HTTP endpoint
            traces_url = f"{self._http_endpoint.rstrip('/')}/v1/traces"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    traces_url,
                    json=trace_payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)
                ) as response:
                    # 200 or 202 indicates success
                    return response.status in (200, 202)

        except Exception as e:
            logger.debug(f"Trace export verification error: {e}")
            return False

    def _build_test_trace(self) -> Dict:
        """Build a minimal test trace payload in OTLP format."""
        import random
        import struct

        # Generate trace and span IDs
        trace_id = ''.join(f'{random.randint(0, 255):02x}' for _ in range(16))
        span_id = ''.join(f'{random.randint(0, 255):02x}' for _ in range(8))

        current_time_ns = int(time.time() * 1e9)

        return {
            'resourceSpans': [{
                'resource': {
                    'attributes': [{
                        'key': 'service.name',
                        'value': {'stringValue': self.service_name}
                    }, {
                        'key': 'health.check',
                        'value': {'stringValue': 'true'}
                    }]
                },
                'scopeSpans': [{
                    'scope': {
                        'name': 'neural_hive_observability.health_check',
                        'version': '1.0.0'
                    },
                    'spans': [{
                        'traceId': trace_id,
                        'spanId': span_id,
                        'name': 'health_check.otel_pipeline',
                        'kind': 1,  # INTERNAL
                        'startTimeUnixNano': str(current_time_ns - 1000000),  # 1ms ago
                        'endTimeUnixNano': str(current_time_ns),
                        'attributes': [{
                            'key': 'health_check.type',
                            'value': {'stringValue': 'otel_pipeline'}
                        }],
                        'status': {
                            'code': 1  # OK
                        }
                    }]
                }]
            }]
        }


class OTELCollectorMetricsHealthCheck(HealthCheck):
    """
    Health check based on OTEL Collector's own metrics.

    Checks metrics like accepted/rejected spans to verify pipeline health.
    """

    def __init__(
        self,
        metrics_endpoint: str = 'http://otel-collector:8888/metrics',
        name: str = 'otel_collector_metrics',
        timeout_seconds: float = 5.0,
        min_accepted_spans_rate: float = 0.0,
    ):
        """
        Initialize OTEL Collector metrics health check.

        Args:
            metrics_endpoint: Prometheus metrics endpoint of OTEL Collector
            name: Name of this health check
            timeout_seconds: Timeout for health check operations
            min_accepted_spans_rate: Minimum rate of accepted spans (0 to disable)
        """
        super().__init__(name=name, timeout_seconds=timeout_seconds)
        self.metrics_endpoint = metrics_endpoint
        self.min_accepted_spans_rate = min_accepted_spans_rate

    async def check(self) -> HealthCheckResult:
        """Check OTEL Collector health via its metrics endpoint."""
        start_time = time.time()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.metrics_endpoint,
                    timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)
                ) as response:
                    if response.status != 200:
                        return self._create_result(
                            HealthStatus.UNHEALTHY,
                            f"OTEL Collector metrics endpoint returned {response.status}",
                            start_time=start_time
                        )

                    metrics_text = await response.text()

                    # Parse relevant metrics
                    metrics = self._parse_metrics(metrics_text)

                    details = {
                        'metrics_endpoint': self.metrics_endpoint,
                        'accepted_spans': metrics.get('accepted_spans', 0),
                        'refused_spans': metrics.get('refused_spans', 0),
                        'exported_spans': metrics.get('exported_spans', 0),
                    }

                    # Check for high refusal rate
                    total_spans = metrics.get('accepted_spans', 0) + metrics.get('refused_spans', 0)
                    if total_spans > 0:
                        refusal_rate = metrics.get('refused_spans', 0) / total_spans
                        details['refusal_rate'] = refusal_rate

                        if refusal_rate > 0.1:  # More than 10% refused
                            return self._create_result(
                                HealthStatus.DEGRADED,
                                f"High span refusal rate: {refusal_rate:.1%}",
                                details=details,
                                start_time=start_time
                            )

                    return self._create_result(
                        HealthStatus.HEALTHY,
                        'OTEL Collector metrics healthy',
                        details=details,
                        start_time=start_time
                    )

        except asyncio.TimeoutError:
            return self._create_result(
                HealthStatus.UNHEALTHY,
                f"Timeout fetching OTEL Collector metrics ({self.timeout_seconds}s)",
                start_time=start_time
            )
        except Exception as e:
            return self._create_result(
                HealthStatus.UNHEALTHY,
                f"Error checking OTEL Collector metrics: {str(e)}",
                start_time=start_time
            )

    def _parse_metrics(self, metrics_text: str) -> Dict[str, float]:
        """Parse Prometheus metrics text format."""
        metrics = {}

        for line in metrics_text.split('\n'):
            if line.startswith('#') or not line.strip():
                continue

            # Parse metric line
            try:
                if 'otelcol_receiver_accepted_spans' in line:
                    value = float(line.split()[-1])
                    metrics['accepted_spans'] = metrics.get('accepted_spans', 0) + value
                elif 'otelcol_receiver_refused_spans' in line:
                    value = float(line.split()[-1])
                    metrics['refused_spans'] = metrics.get('refused_spans', 0) + value
                elif 'otelcol_exporter_sent_spans' in line:
                    value = float(line.split()[-1])
                    metrics['exported_spans'] = metrics.get('exported_spans', 0) + value
            except (ValueError, IndexError):
                continue

        return metrics


class JaegerHealthCheck(HealthCheck):
    """
    Health check for Jaeger tracing backend.

    Verifies Jaeger Query service is accessible and operational.
    """

    def __init__(
        self,
        jaeger_query_endpoint: str = 'http://jaeger-query:16686',
        name: str = 'jaeger',
        timeout_seconds: float = 5.0,
    ):
        """
        Initialize Jaeger health check.

        Args:
            jaeger_query_endpoint: Jaeger Query service endpoint
            name: Name of this health check
            timeout_seconds: Timeout for health check operations
        """
        super().__init__(name=name, timeout_seconds=timeout_seconds)
        self.jaeger_query_endpoint = jaeger_query_endpoint

    async def check(self) -> HealthCheckResult:
        """Check Jaeger Query service health."""
        start_time = time.time()

        try:
            # Check Jaeger API endpoint
            api_url = f"{self.jaeger_query_endpoint.rstrip('/')}/api/services"

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    api_url,
                    timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)
                ) as response:
                    if response.status != 200:
                        return self._create_result(
                            HealthStatus.UNHEALTHY,
                            f"Jaeger Query returned HTTP {response.status}",
                            start_time=start_time
                        )

                    data = await response.json()
                    services = data.get('data', [])

                    details = {
                        'jaeger_endpoint': self.jaeger_query_endpoint,
                        'services_count': len(services),
                        'services': services[:10],  # First 10 services
                    }

                    if len(services) == 0:
                        return self._create_result(
                            HealthStatus.DEGRADED,
                            'Jaeger is up but no services are reporting traces',
                            details=details,
                            start_time=start_time
                        )

                    return self._create_result(
                        HealthStatus.HEALTHY,
                        f"Jaeger operational with {len(services)} services",
                        details=details,
                        start_time=start_time
                    )

        except asyncio.TimeoutError:
            return self._create_result(
                HealthStatus.UNHEALTHY,
                f"Timeout connecting to Jaeger ({self.timeout_seconds}s)",
                start_time=start_time
            )
        except Exception as e:
            return self._create_result(
                HealthStatus.UNHEALTHY,
                f"Error checking Jaeger: {str(e)}",
                start_time=start_time
            )
