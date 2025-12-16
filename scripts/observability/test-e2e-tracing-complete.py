#!/usr/bin/env python3
"""
E2E Tracing Validation Script for Neural Hive

This script validates end-to-end distributed tracing across the Neural Hive system,
from gateway-intencoes through orchestrator-dynamic to specialists.

Usage:
    python scripts/observability/test-e2e-tracing-complete.py \
        --gateway-url http://gateway-intencoes:8000 \
        --jaeger-url http://jaeger-query:16686 \
        --verbose \
        --output-json reports/e2e-tracing-$(date +%Y%m%d-%H%M%S).json
"""

import argparse
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class TestStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


@dataclass
class SpanValidation:
    """Validation result for a single span"""
    operation_name: str
    service_name: str
    found: bool
    duration_ms: Optional[float] = None
    has_error: bool = False
    attributes_found: list = field(default_factory=list)
    attributes_missing: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


@dataclass
class ScenarioResult:
    """Result for a single test scenario"""
    name: str
    status: TestStatus
    intent_id: str
    plan_id: Optional[str] = None
    trace_id: Optional[str] = None
    spans_found: list = field(default_factory=list)
    spans_missing: list = field(default_factory=list)
    span_validations: list = field(default_factory=list)
    context_propagation_valid: bool = False
    plan_id_propagation_valid: bool = False
    has_span_errors: bool = False
    trace_continuity_valid: bool = False
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass
class ValidationReport:
    """Complete validation report"""
    timestamp: str
    duration_seconds: float
    gateway_url: str
    jaeger_url: str
    scenarios_total: int
    scenarios_passed: int
    scenarios_failed: int
    scenarios_warned: int
    success_rate: float
    avg_e2e_latency_ms: float
    span_coverage_percent: float
    results: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)


class JaegerClient:
    """Client for Jaeger Query API"""

    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def health_check(self) -> bool:
        """Check if Jaeger Query API is available"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/services",
                timeout=self.timeout
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def get_services(self) -> list:
        """Get list of services with traces"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/services",
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json().get("data", [])
        except requests.RequestException:
            return []

    def find_traces_by_tag(
        self,
        tag_key: str,
        tag_value: str,
        service: str = None,
        limit: int = 20,
        lookback_hours: int = 1
    ) -> list:
        """Find traces by tag (e.g., neural.hive.intent.id)"""
        params = {
            "tag": f"{tag_key}:{tag_value}",
            "limit": limit,
            "lookback": f"{lookback_hours}h"
        }
        if service:
            params["service"] = service

        try:
            response = self.session.get(
                f"{self.base_url}/api/traces",
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json().get("data", [])
        except requests.RequestException as e:
            print(f"Error querying Jaeger: {e}")
            return []

    def get_trace_by_id(self, trace_id: str) -> Optional[dict]:
        """Get a specific trace by ID"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/traces/{trace_id}",
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json().get("data", [])
            return data[0] if data else None
        except requests.RequestException:
            return None


class GatewayClient:
    """Client for Gateway Intencoes API"""

    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()

    def health_check(self) -> bool:
        """Check if Gateway is available"""
        try:
            response = self.session.get(
                f"{self.base_url}/health",
                timeout=self.timeout
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def send_intent(
        self,
        text: str,
        intent_id: str,
        user_id: str = "test-user",
        session_id: str = None,
        specialist_type: str = None
    ) -> tuple[Optional[dict], Optional[str]]:
        """
        Send intent to gateway and return response with trace_id
        Returns: (response_data, trace_id)
        """
        session_id = session_id or f"session-{uuid.uuid4().hex[:8]}"

        headers = {
            "Content-Type": "application/json",
            "X-Neural-Hive-Intent-ID": intent_id,
            "X-Neural-Hive-User-ID": user_id,
            "X-Neural-Hive-Session-ID": session_id,
        }

        payload = {
            "text": text,
            "context": {
                "user_id": user_id,
                "session_id": session_id,
            }
        }

        if specialist_type:
            payload["specialist_type"] = specialist_type

        try:
            response = self.session.post(
                f"{self.base_url}/intents/text",
                json=payload,
                headers=headers,
                timeout=self.timeout
            )

            # Extract trace_id from response headers (traceparent format)
            trace_id = None
            traceparent = response.headers.get("traceparent")
            if traceparent:
                # Format: 00-<trace_id>-<span_id>-<flags>
                parts = traceparent.split("-")
                if len(parts) >= 2:
                    trace_id = parts[1]

            # Also check response body for trace_id
            response_data = None
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    if not trace_id and "trace_id" in response_data:
                        trace_id = response_data["trace_id"]
                except json.JSONDecodeError:
                    pass

            return response_data, trace_id

        except requests.RequestException as e:
            print(f"Error sending intent: {e}")
            return None, None


class E2ETracingValidator:
    """Main validator for E2E tracing"""

    # Expected spans per service
    EXPECTED_SPANS = {
        "gateway-intencoes": [
            "POST /intents/text",
            "asr.process",
            "nlu.process",
            "kafka.produce"
        ],
        "orchestrator-dynamic": [
            "kafka.consume",
            "orchestration_workflow.run",
            "generate_execution_tickets",
            "allocate_resources"
        ],
        "specialist-business": ["Evaluate", "model.predict"],
        "specialist-technical": ["Evaluate", "model.predict"],
        "specialist-architecture": ["Evaluate", "model.predict"],
        "specialist-behavior": ["Evaluate", "model.predict"],
        "specialist-evolution": ["Evaluate", "model.predict"],
    }

    # Required Neural Hive attributes
    REQUIRED_ATTRIBUTES = [
        "neural.hive.intent.id",
        "neural.hive.plan.id",
        "neural.hive.component",
        "neural.hive.layer"
    ]

    # Optional but recommended attributes
    OPTIONAL_ATTRIBUTES = [
        "neural.hive.user.id",
        "neural.hive.domain"
    ]

    # Services that must have plan_id propagated
    PLAN_ID_REQUIRED_SERVICES = [
        "orchestrator-dynamic",
        "specialist-business",
        "specialist-technical",
        "specialist-architecture",
        "specialist-behavior",
        "specialist-evolution"
    ]

    # Test scenarios covering all specialists
    TEST_SCENARIOS = [
        {
            "name": "Business Analysis Intent",
            "text": "Analyze the business impact of launching a new product line for enterprise customers",
            "specialist_type": "business",
            "expected_domain": "business"
        },
        {
            "name": "Technical Implementation Intent",
            "text": "Implement a high-performance caching layer using Redis with cluster mode enabled",
            "specialist_type": "technical",
            "expected_domain": "technical"
        },
        {
            "name": "Architecture Design Intent",
            "text": "Design a microservices architecture for a real-time analytics platform with event sourcing",
            "specialist_type": "architecture",
            "expected_domain": "architecture"
        },
        {
            "name": "Behavior Optimization Intent",
            "text": "Optimize user onboarding flow to reduce drop-off rate and improve engagement metrics",
            "specialist_type": "behavior",
            "expected_domain": "behavior"
        },
        {
            "name": "Evolution Strategy Intent",
            "text": "Plan the evolution strategy for migrating legacy monolith to cloud-native architecture",
            "specialist_type": "evolution",
            "expected_domain": "evolution"
        }
    ]

    def __init__(
        self,
        gateway_url: str,
        jaeger_url: str,
        timeout: int = 60,
        async_wait_seconds: int = 35,
        verbose: bool = False
    ):
        self.gateway = GatewayClient(gateway_url, timeout)
        self.jaeger = JaegerClient(jaeger_url, timeout)
        self.gateway_url = gateway_url
        self.jaeger_url = jaeger_url
        self.timeout = timeout
        self.async_wait_seconds = async_wait_seconds
        self.verbose = verbose

    def log(self, message: str, level: str = "INFO"):
        """Log message if verbose mode is enabled"""
        if self.verbose or level in ["ERROR", "WARN"]:
            timestamp = datetime.now().strftime("%H:%M:%S")
            color = {
                "INFO": "\033[0m",
                "SUCCESS": "\033[92m",
                "WARN": "\033[93m",
                "ERROR": "\033[91m"
            }.get(level, "\033[0m")
            reset = "\033[0m"
            print(f"[{timestamp}] {color}{level}{reset}: {message}")

    def validate_connectivity(self) -> bool:
        """Validate connectivity to Gateway and Jaeger"""
        self.log("Validating connectivity...")

        # Check Gateway
        if not self.gateway.health_check():
            self.log(f"Gateway at {self.gateway_url} is not reachable", "ERROR")
            return False
        self.log(f"Gateway at {self.gateway_url} is reachable", "SUCCESS")

        # Check Jaeger
        if not self.jaeger.health_check():
            self.log(f"Jaeger at {self.jaeger_url} is not reachable", "ERROR")
            return False
        self.log(f"Jaeger at {self.jaeger_url} is reachable", "SUCCESS")

        # Check Jaeger has services
        services = self.jaeger.get_services()
        if not services:
            self.log("Jaeger has no services with traces", "WARN")
        else:
            self.log(f"Jaeger has {len(services)} services with traces", "SUCCESS")

        return True

    def extract_spans_from_trace(self, trace: dict) -> dict:
        """Extract spans organized by service from a trace"""
        spans_by_service = {}

        if not trace:
            return spans_by_service

        spans = trace.get("spans", [])
        processes = trace.get("processes", {})

        for span in spans:
            process_id = span.get("processID", "")
            process = processes.get(process_id, {})
            service_name = process.get("serviceName", "unknown")

            if service_name not in spans_by_service:
                spans_by_service[service_name] = []

            span_info = {
                "operation_name": span.get("operationName", ""),
                "span_id": span.get("spanID", ""),
                "duration_us": span.get("duration", 0),
                "duration_ms": span.get("duration", 0) / 1000,
                "tags": {t["key"]: t["value"] for t in span.get("tags", [])},
                "logs": span.get("logs", []),
                "warnings": span.get("warnings", []),
                "has_error": any(
                    t["key"] == "error" and t["value"] == True
                    for t in span.get("tags", [])
                )
            }
            spans_by_service[service_name].append(span_info)

        return spans_by_service

    def validate_span_attributes(
        self,
        span: dict,
        intent_id: str
    ) -> SpanValidation:
        """Validate Neural Hive attributes in a span"""
        tags = span.get("tags", {})

        validation = SpanValidation(
            operation_name=span["operation_name"],
            service_name="",  # Will be set by caller
            found=True,
            duration_ms=span["duration_ms"],
            has_error=span["has_error"]
        )

        # Check required attributes
        for attr in self.REQUIRED_ATTRIBUTES:
            if attr in tags:
                validation.attributes_found.append(attr)
            else:
                validation.attributes_missing.append(attr)

        # Check optional attributes
        for attr in self.OPTIONAL_ATTRIBUTES:
            if attr in tags:
                validation.attributes_found.append(attr)

        # Validate intent_id matches
        span_intent_id = tags.get("neural.hive.intent.id")
        if span_intent_id and span_intent_id != intent_id:
            validation.warnings.append(
                f"intent_id mismatch: expected {intent_id}, got {span_intent_id}"
            )

        return validation

    def validate_context_propagation(
        self,
        spans_by_service: dict,
        intent_id: str
    ) -> tuple[bool, list, bool, list]:
        """
        Validate context propagation across services.

        Returns:
            tuple: (intent_id_valid, intent_warnings, plan_id_valid, plan_warnings)
        """
        intent_warnings = []
        plan_warnings = []
        services_with_intent_id = []
        services_with_plan_id = []

        for service_name, spans in spans_by_service.items():
            for span in spans:
                tags = span.get("tags", {})
                if tags.get("neural.hive.intent.id") == intent_id:
                    services_with_intent_id.append(service_name)
                if tags.get("neural.hive.plan.id"):
                    services_with_plan_id.append(service_name)
                    break

        # Check gateway has intent_id
        if "gateway-intencoes" in spans_by_service and \
           "gateway-intencoes" not in services_with_intent_id:
            intent_warnings.append("intent_id not found in gateway-intencoes spans")

        # Check orchestrator has intent_id
        if "orchestrator-dynamic" in spans_by_service and \
           "orchestrator-dynamic" not in services_with_intent_id:
            intent_warnings.append("intent_id not propagated to orchestrator-dynamic")

        # Check specialists have intent_id
        specialist_services = [s for s in spans_by_service.keys() if s.startswith("specialist-")]
        for service in specialist_services:
            if service not in services_with_intent_id:
                intent_warnings.append(f"intent_id not propagated to {service}")

        # Validate plan_id propagation in downstream services
        for service in self.PLAN_ID_REQUIRED_SERVICES:
            if service in spans_by_service and service not in services_with_plan_id:
                plan_warnings.append(f"plan_id not propagated to {service}")

        # Consider intent_id valid if at least gateway and one other service have it
        intent_valid = len(services_with_intent_id) >= 2

        # Consider plan_id valid if orchestrator and at least one specialist have it
        plan_id_in_orchestrator = "orchestrator-dynamic" in services_with_plan_id
        plan_id_in_specialist = any(
            s.startswith("specialist-") and s in services_with_plan_id
            for s in spans_by_service.keys()
        )
        plan_valid = plan_id_in_orchestrator and plan_id_in_specialist

        return intent_valid, intent_warnings, plan_valid, plan_warnings

    def validate_trace_continuity(
        self,
        traces: list,
        expected_trace_id: Optional[str]
    ) -> tuple[bool, list]:
        """
        Validate trace continuity - all spans should share the same trace_id.

        Returns:
            tuple: (is_valid, errors)
        """
        errors = []

        if not traces:
            return False, ["No traces to validate"]

        # Collect all trace_ids from all traces
        trace_ids = set()
        for trace in traces:
            trace_id = trace.get("traceID")
            if trace_id:
                trace_ids.add(trace_id)

        # Check if we have multiple trace_ids (fragmented trace)
        if len(trace_ids) > 1:
            errors.append(
                f"Trace fragmentation detected: found {len(trace_ids)} different trace_ids"
            )

        # Check if expected trace_id is present
        if expected_trace_id and expected_trace_id not in trace_ids:
            errors.append(
                f"Expected trace_id '{expected_trace_id}' not found in traces"
            )

        # Validate parent-child relationships within each trace
        for trace in traces:
            spans = trace.get("spans", [])
            span_ids = {span.get("spanID") for span in spans}
            parent_ids = set()

            for span in spans:
                for ref in span.get("references", []):
                    if ref.get("refType") == "CHILD_OF":
                        parent_id = ref.get("spanID")
                        if parent_id:
                            parent_ids.add(parent_id)

            # Find orphan spans (excluding root spans which have no parent)
            orphan_parents = parent_ids - span_ids
            if orphan_parents:
                errors.append(
                    f"Found {len(orphan_parents)} spans with missing parent references (orphan spans)"
                )

        is_valid = len(errors) == 0
        return is_valid, errors

    def check_spans_for_errors(
        self,
        spans_by_service: dict
    ) -> tuple[bool, list]:
        """
        Check if any spans have error tags.

        Returns:
            tuple: (has_errors, error_details)
        """
        error_details = []

        for service_name, spans in spans_by_service.items():
            for span in spans:
                if span.get("has_error"):
                    error_msg = span.get("tags", {}).get("error.message", "Unknown error")
                    error_details.append(
                        f"{service_name}.{span['operation_name']}: {error_msg}"
                    )

        has_errors = len(error_details) > 0
        return has_errors, error_details

    def run_scenario(self, scenario: dict) -> ScenarioResult:
        """Run a single test scenario"""
        intent_id = f"intent-{uuid.uuid4()}"
        user_id = f"test-user-{uuid.uuid4().hex[:8]}"

        result = ScenarioResult(
            name=scenario["name"],
            status=TestStatus.FAIL,
            intent_id=intent_id
        )

        start_time = time.time()

        # Step 1: Send intent to gateway
        self.log(f"Sending intent: {scenario['name']}")
        response_data, trace_id = self.gateway.send_intent(
            text=scenario["text"],
            intent_id=intent_id,
            user_id=user_id,
            specialist_type=scenario.get("specialist_type")
        )

        if not response_data:
            result.errors.append("Gateway did not return response")
            result.duration_ms = (time.time() - start_time) * 1000
            return result

        result.trace_id = trace_id
        if response_data.get("plan_id"):
            result.plan_id = response_data["plan_id"]

        self.log(f"Intent sent. trace_id={trace_id}, intent_id={intent_id}")

        # Step 2: Wait for async processing
        self.log(f"Waiting {self.async_wait_seconds}s for async processing...")
        time.sleep(self.async_wait_seconds)

        # Step 3: Query Jaeger for traces
        self.log(f"Querying Jaeger for intent_id={intent_id}")
        traces = self.jaeger.find_traces_by_tag(
            tag_key="neural.hive.intent.id",
            tag_value=intent_id,
            limit=20
        )

        # Fallback to trace_id if intent_id search fails
        if not traces and trace_id:
            self.log("No traces found by intent_id, trying trace_id fallback")
            trace = self.jaeger.get_trace_by_id(trace_id)
            if trace:
                traces = [trace]

        if not traces:
            result.errors.append("No traces found in Jaeger")
            result.warnings.append(
                "Check: sampling rate, OTEL export, Jaeger connectivity"
            )
            result.duration_ms = (time.time() - start_time) * 1000
            return result

        self.log(f"Found {len(traces)} trace(s)")

        # Step 4: Validate trace continuity
        continuity_valid, continuity_errors = self.validate_trace_continuity(traces, trace_id)
        result.trace_continuity_valid = continuity_valid
        if not continuity_valid:
            for error in continuity_errors:
                result.errors.append(f"Trace continuity: {error}")

        # Step 5: Analyze traces - combine all spans from all traces
        all_spans_by_service = {}
        for trace in traces:
            spans_by_service = self.extract_spans_from_trace(trace)
            for service, spans in spans_by_service.items():
                if service not in all_spans_by_service:
                    all_spans_by_service[service] = []
                all_spans_by_service[service].extend(spans)

        # Step 6: Check for span errors
        has_span_errors, span_error_details = self.check_spans_for_errors(all_spans_by_service)
        result.has_span_errors = has_span_errors
        if has_span_errors:
            for error_detail in span_error_details:
                result.errors.append(f"Span error: {error_detail}")

        # Step 7: Validate expected spans
        expected_specialist = f"specialist-{scenario.get('specialist_type', 'business')}"

        for service_name, expected_ops in self.EXPECTED_SPANS.items():
            # Only validate the expected specialist
            if service_name.startswith("specialist-") and service_name != expected_specialist:
                continue

            service_spans = all_spans_by_service.get(service_name, [])
            service_operations = [s["operation_name"] for s in service_spans]

            for expected_op in expected_ops:
                # Check if operation exists (partial match)
                found = any(
                    expected_op.lower() in op.lower()
                    for op in service_operations
                )

                if found:
                    result.spans_found.append(f"{service_name}.{expected_op}")
                    # Find the actual span and validate attributes
                    for span in service_spans:
                        if expected_op.lower() in span["operation_name"].lower():
                            validation = self.validate_span_attributes(span, intent_id)
                            validation.service_name = service_name
                            result.span_validations.append(asdict(validation))
                            break
                else:
                    result.spans_missing.append(f"{service_name}.{expected_op}")

        # Step 8: Validate context propagation (intent_id and plan_id)
        intent_valid, intent_warnings, plan_valid, plan_warnings = self.validate_context_propagation(
            all_spans_by_service, intent_id
        )
        result.context_propagation_valid = intent_valid
        result.plan_id_propagation_valid = plan_valid
        result.warnings.extend(intent_warnings)

        # plan_id warnings are more severe - add as errors if plan_id is missing in downstream
        if not plan_valid:
            for warning in plan_warnings:
                result.errors.append(f"plan_id propagation: {warning}")
        else:
            result.warnings.extend(plan_warnings)

        # Step 9: Determine final status
        total_expected = sum(
            len(ops) for service, ops in self.EXPECTED_SPANS.items()
            if not service.startswith("specialist-") or service == expected_specialist
        )

        found_count = len(result.spans_found)
        coverage = found_count / total_expected if total_expected > 0 else 0

        # Determine status based on multiple factors
        critical_errors = (
            has_span_errors or
            not continuity_valid or
            not plan_valid
        )

        if coverage >= 0.8 and intent_valid and plan_valid and not result.errors and not critical_errors:
            result.status = TestStatus.PASS
        elif critical_errors:
            # Critical errors always result in FAIL
            result.status = TestStatus.FAIL
        elif coverage >= 0.5 or (found_count > 0 and not result.errors):
            result.status = TestStatus.WARN
        else:
            result.status = TestStatus.FAIL

        result.duration_ms = (time.time() - start_time) * 1000

        status_icon = {
            TestStatus.PASS: "\033[92m[PASS]\033[0m",
            TestStatus.WARN: "\033[93m[WARN]\033[0m",
            TestStatus.FAIL: "\033[91m[FAIL]\033[0m"
        }[result.status]

        propagation_status = []
        if intent_valid:
            propagation_status.append("intent_id:OK")
        else:
            propagation_status.append("intent_id:FAIL")
        if plan_valid:
            propagation_status.append("plan_id:OK")
        else:
            propagation_status.append("plan_id:FAIL")

        self.log(
            f"{status_icon} {scenario['name']}: "
            f"spans={found_count}/{total_expected}, "
            f"propagation=[{', '.join(propagation_status)}], "
            f"errors={len(result.errors)}"
        )

        return result

    def generate_recommendations(self, results: list) -> list:
        """Generate recommendations based on validation results"""
        recommendations = []

        # Check for common issues
        missing_spans_count = {}
        intent_propagation_failures = 0
        plan_propagation_failures = 0
        span_error_count = 0
        trace_continuity_failures = 0
        total_scenarios = len(results)

        for result in results:
            if not result.context_propagation_valid:
                intent_propagation_failures += 1

            if not result.plan_id_propagation_valid:
                plan_propagation_failures += 1

            if result.has_span_errors:
                span_error_count += 1

            if not result.trace_continuity_valid:
                trace_continuity_failures += 1

            for missing in result.spans_missing:
                if missing not in missing_spans_count:
                    missing_spans_count[missing] = 0
                missing_spans_count[missing] += 1

        # Recommendation: Missing spans
        for span, count in missing_spans_count.items():
            if count > total_scenarios / 2:
                service = span.split(".")[0]
                operation = span.split(".")[-1]
                recommendations.append({
                    "issue": f"Span '{span}' missing in {count}/{total_scenarios} scenarios",
                    "recommendation": f"Verify instrumentation in {service} for '{operation}' operation",
                    "severity": "high" if count == total_scenarios else "medium"
                })

        # Recommendation: intent_id propagation
        if intent_propagation_failures > 0:
            recommendations.append({
                "issue": f"intent_id propagation failed in {intent_propagation_failures}/{total_scenarios} scenarios",
                "recommendation": "Check baggage/header injection in Kafka producer and extraction in consumers",
                "severity": "high" if intent_propagation_failures == total_scenarios else "medium"
            })

        # Recommendation: plan_id propagation (critical)
        if plan_propagation_failures > 0:
            recommendations.append({
                "issue": f"plan_id propagation failed in {plan_propagation_failures}/{total_scenarios} scenarios",
                "recommendation": "Ensure orchestrator-dynamic sets plan_id in baggage and propagates to specialists via gRPC metadata",
                "severity": "critical" if plan_propagation_failures == total_scenarios else "high"
            })

        # Recommendation: Span errors
        if span_error_count > 0:
            recommendations.append({
                "issue": f"Spans with errors found in {span_error_count}/{total_scenarios} scenarios",
                "recommendation": "Review error logs and fix underlying service issues before validating tracing",
                "severity": "critical" if span_error_count == total_scenarios else "high"
            })

        # Recommendation: Trace continuity
        if trace_continuity_failures > 0:
            recommendations.append({
                "issue": f"Trace continuity issues in {trace_continuity_failures}/{total_scenarios} scenarios",
                "recommendation": "Check context propagation between services (Kafka headers, gRPC metadata) - traces are fragmented",
                "severity": "critical" if trace_continuity_failures == total_scenarios else "high"
            })

        # Recommendation: No traces
        no_traces = sum(1 for r in results if not r.spans_found)
        if no_traces > 0:
            recommendations.append({
                "issue": f"No traces found in {no_traces}/{total_scenarios} scenarios",
                "recommendation": "Check OTEL Collector export, Jaeger connectivity, and sampling configuration",
                "severity": "critical" if no_traces == total_scenarios else "high"
            })

        return recommendations

    def run_validation(self) -> ValidationReport:
        """Run complete E2E validation"""
        start_time = time.time()

        print("\n" + "="*60)
        print("Neural Hive E2E Tracing Validation")
        print("="*60 + "\n")

        # Validate connectivity
        if not self.validate_connectivity():
            return ValidationReport(
                timestamp=datetime.now().isoformat(),
                duration_seconds=time.time() - start_time,
                gateway_url=self.gateway_url,
                jaeger_url=self.jaeger_url,
                scenarios_total=len(self.TEST_SCENARIOS),
                scenarios_passed=0,
                scenarios_failed=len(self.TEST_SCENARIOS),
                scenarios_warned=0,
                success_rate=0.0,
                avg_e2e_latency_ms=0.0,
                span_coverage_percent=0.0,
                results=[],
                recommendations=[{
                    "issue": "Connectivity validation failed",
                    "recommendation": "Ensure Gateway and Jaeger are accessible",
                    "severity": "critical"
                }]
            )

        # Run scenarios
        print("\n" + "-"*40)
        print("Running Test Scenarios")
        print("-"*40 + "\n")

        results = []
        for scenario in self.TEST_SCENARIOS:
            result = self.run_scenario(scenario)
            results.append(result)
            time.sleep(2)  # Small delay between scenarios

        # Calculate metrics
        passed = sum(1 for r in results if r.status == TestStatus.PASS)
        failed = sum(1 for r in results if r.status == TestStatus.FAIL)
        warned = sum(1 for r in results if r.status == TestStatus.WARN)

        total_spans_found = sum(len(r.spans_found) for r in results)
        total_spans_expected = sum(
            len(r.spans_found) + len(r.spans_missing)
            for r in results
        )

        avg_latency = sum(r.duration_ms for r in results) / len(results) if results else 0
        span_coverage = (total_spans_found / total_spans_expected * 100) if total_spans_expected > 0 else 0

        # Generate recommendations
        recommendations = self.generate_recommendations(results)

        # Create report
        report = ValidationReport(
            timestamp=datetime.now().isoformat(),
            duration_seconds=time.time() - start_time,
            gateway_url=self.gateway_url,
            jaeger_url=self.jaeger_url,
            scenarios_total=len(results),
            scenarios_passed=passed,
            scenarios_failed=failed,
            scenarios_warned=warned,
            success_rate=passed / len(results) * 100 if results else 0,
            avg_e2e_latency_ms=avg_latency,
            span_coverage_percent=span_coverage,
            results=[asdict(r) for r in results],
            recommendations=recommendations
        )

        # Print summary
        print("\n" + "="*60)
        print("Validation Summary")
        print("="*60)
        print(f"\nScenarios: {passed} passed, {warned} warned, {failed} failed")
        print(f"Success Rate: {report.success_rate:.1f}%")
        print(f"Span Coverage: {span_coverage:.1f}%")
        print(f"Avg E2E Latency: {avg_latency:.0f}ms")
        print(f"Total Duration: {report.duration_seconds:.1f}s")

        if recommendations:
            print("\n" + "-"*40)
            print("Recommendations:")
            for rec in recommendations:
                severity_color = {
                    "critical": "\033[91m",
                    "high": "\033[93m",
                    "medium": "\033[0m"
                }.get(rec["severity"], "\033[0m")
                print(f"\n{severity_color}[{rec['severity'].upper()}]\033[0m {rec['issue']}")
                print(f"  -> {rec['recommendation']}")

        status_color = "\033[92m" if report.success_rate >= 80 else (
            "\033[93m" if report.success_rate >= 50 else "\033[91m"
        )
        print(f"\n{status_color}Overall Status: {'PASS' if report.success_rate >= 80 else 'FAIL'}\033[0m\n")

        return report


def main():
    parser = argparse.ArgumentParser(
        description="E2E Tracing Validation for Neural Hive"
    )
    parser.add_argument(
        "--gateway-url",
        default=os.environ.get("GATEWAY_URL", "http://gateway-intencoes:8000"),
        help="Gateway Intencoes URL"
    )
    parser.add_argument(
        "--jaeger-url",
        default=os.environ.get("JAEGER_URL", "http://jaeger-query:16686"),
        help="Jaeger Query API URL"
    )
    parser.add_argument(
        "--namespace",
        default="neural-hive",
        help="Kubernetes namespace (for auto-detection)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Timeout for API calls (seconds)"
    )
    parser.add_argument(
        "--async-wait",
        type=int,
        default=35,
        help="Wait time for async processing (seconds)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--output-json",
        help="Path to save JSON report"
    )

    args = parser.parse_args()

    # Create validator
    validator = E2ETracingValidator(
        gateway_url=args.gateway_url,
        jaeger_url=args.jaeger_url,
        timeout=args.timeout,
        async_wait_seconds=args.async_wait,
        verbose=args.verbose
    )

    # Run validation
    report = validator.run_validation()

    # Save JSON report if requested
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert enums to strings
        report_dict = asdict(report)
        for result in report_dict["results"]:
            result["status"] = result["status"].value if isinstance(result["status"], TestStatus) else result["status"]

        with open(output_path, "w") as f:
            json.dump(report_dict, f, indent=2, default=str)

        print(f"Report saved to: {output_path}")

    # Exit with appropriate code
    sys.exit(0 if report.success_rate >= 80 else 1)


if __name__ == "__main__":
    main()
