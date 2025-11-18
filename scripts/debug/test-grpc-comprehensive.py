#!/usr/bin/env python3
"""
gRPC Comprehensive Test Suite for Specialists

This script extends test-grpc-isolated.py with multiple payload scenarios
to thoroughly validate the evaluated_at timestamp field and gRPC communication.

Test Scenarios:
- Simple Payload: Minimal valid cognitive plan
- Complex Payload: Full structure with nested tasks and metadata
- Special Characters: Unicode, emojis, escape characters
- Edge Cases: Empty fields, extreme values, large payloads
- Minimal Payload: Absolute minimum required fields

Critical Validation:
1. Response is not None
2. Response type is EvaluatePlanResponse
3. Field 'evaluated_at' exists
4. Field 'evaluated_at' is Timestamp protobuf type
5. Access to evaluated_at.seconds and evaluated_at.nanos succeeds
6. Conversion to ISO datetime succeeds

Usage:
  python3 test-grpc-comprehensive.py                    # Test all specialists, all scenarios
  python3 test-grpc-comprehensive.py --focus-business   # Test specialist-business extensively
  python3 test-grpc-comprehensive.py --specialist technical  # Test specific specialist
  python3 test-grpc-comprehensive.py --scenario complex      # Test specific scenario
"""

import sys
import os
import json
import time
import uuid
import string
import random
import traceback
import argparse
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from pathlib import Path

import grpc
import structlog
from google.protobuf.timestamp_pb2 import Timestamp

# Add libraries path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../libraries/python'))

from neural_hive_specialists.proto_gen import specialist_pb2, specialist_pb2_grpc

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ]
)
logger = structlog.get_logger()


class PayloadGenerator:
    """Generate various test payloads for comprehensive testing"""

    def __init__(self):
        self.base_plan_id_prefix = f"test-comprehensive-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.counter = 0

    def _next_id(self) -> str:
        """Generate unique ID for test"""
        self.counter += 1
        return f"{self.base_plan_id_prefix}-{self.counter:03d}"

    def generate_simple_payload(self, specialist_type: str) -> Dict[str, Any]:
        """Generate minimal valid payload with only required fields"""
        plan_id = self._next_id()
        return {
            "plan_id": plan_id,
            "intent_id": f"intent-simple-{plan_id}",
            "version": "1.0",
            "description": "Simple test payload with minimal required fields for validation.",
            "specialist_type": specialist_type,
            "domain": "test",
            "priority": "normal"
        }

    def generate_complex_payload(self, specialist_type: str) -> Dict[str, Any]:
        """Generate complex payload with all nested structures"""
        plan_id = self._next_id()

        # Generate 8 tasks with dependencies
        tasks = []
        for i in range(8):
            task = {
                "task_id": f"task-{i+1}",
                "description": f"Complex task {i+1} with nested structure and multiple dependencies",
                "estimated_duration_seconds": random.randint(60, 3600),
                "required_capabilities": [f"capability-{j}" for j in range(1, 4)],
                "dependencies": [f"task-{j}" for j in range(1, max(1, i))] if i > 0 else []
            }
            tasks.append(task)

        # Generate extensive metadata
        metadata = {
            "tenant_id": "tenant-complex-001",
            "user_id": "user-complex-001",
            "session_id": f"session-{plan_id}",
            "correlation_id": str(uuid.uuid4()),
            "environment": "test",
            "region": "us-east-1",
            "security_level": "confidential",
            "compliance_flags": ["GDPR", "HIPAA", "SOC2"],
            "business_context": {
                "department": "engineering",
                "cost_center": "R&D-001",
                "project": "neural-hive-validation",
                "phase": "comprehensive-testing"
            },
            "technical_context": {
                "api_version": "v2",
                "client_version": "1.0.0",
                "protocol": "grpc",
                "encoding": "protobuf"
            }
        }

        # Generate risk factors
        risk_factors = {
            "data_sensitivity": "high",
            "operational_impact": "medium",
            "compliance_risk": "low",
            "security_risk": "medium",
            "factors": [
                {"name": "data_volume", "score": 0.75, "description": "Large data volume requires careful processing"},
                {"name": "complexity", "score": 0.85, "description": "High complexity with nested dependencies"},
                {"name": "latency_sensitivity", "score": 0.60, "description": "Moderate latency requirements"}
            ]
        }

        return {
            "plan_id": plan_id,
            "intent_id": f"intent-complex-{plan_id}",
            "version": "2.0",
            "description": "Complex test payload with extensive nested structures, multiple tasks, dependencies, and comprehensive metadata for thorough validation of serialization and deserialization capabilities.",
            "specialist_type": specialist_type,
            "domain": "test-complex",
            "priority": "high",
            "tasks": tasks,
            "metadata": metadata,
            "risk_factors": risk_factors,
            "complexity_score": 0.87,
            "confidence_score": 0.92,
            "explainability_token": "complex-" + "x" * 500,  # 500+ chars
            "constraints": {
                "max_execution_time_seconds": 7200,
                "max_cost_usd": 100.0,
                "allowed_services": ["service-a", "service-b", "service-c"],
                "forbidden_actions": ["delete", "truncate"]
            }
        }

    def generate_special_characters_payload(self, specialist_type: str) -> Dict[str, Any]:
        """Generate payload with Unicode, emojis, and special characters"""
        plan_id = self._next_id()

        return {
            "plan_id": plan_id,
            "intent_id": f"intent-special-{plan_id}",
            "version": "1.0",
            "description": "Test payload with special characters: Unicode 你好 مرحبا Привет, Emojis 🚀🔥💡🎯✨, Escapes \n\t\"\', and JSON special null []",
            "specialist_type": specialist_type,
            "domain": "test-special-chars",
            "priority": "normal",
            "metadata": {
                "unicode_chinese": "你好世界",
                "unicode_arabic": "مرحبا بك",
                "unicode_russian": "Привет мир",
                "unicode_japanese": "こんにちは",
                "emojis": "🚀🔥💡🎯✨🌟💻🧠🤖",
                "escape_newline": "line1\nline2\nline3",
                "escape_tab": "col1\tcol2\tcol3",
                "escape_quotes": "He said \"Hello\" to me",
                "escape_single": "It's a test",
                "escape_backslash": "path\\to\\file",
                "json_null": None,
                "json_empty_array": [],
                "json_empty_object": {}
            },
            "tasks": [
                {
                    "task_id": "task-unicode-1",
                    "description": "Process Unicode: 你好 (Chinese), مرحبا (Arabic), Привет (Russian) 🚀",
                    "estimated_duration_seconds": 60
                }
            ]
        }

    def generate_edge_case_payload(self, specialist_type: str) -> Dict[str, Any]:
        """Generate payload with edge cases: empty fields, extreme values"""
        plan_id = self._next_id()

        # Generate large task list
        large_tasks = []
        for i in range(100):
            large_tasks.append({
                "task_id": f"edge-task-{i+1}",
                "description": f"Edge case task {i+1}",
                "estimated_duration_seconds": i * 10,
                "dependencies": [f"edge-task-{j}" for j in range(max(1, i-5), i)] if i > 0 else []
            })

        # Generate very long description (10,000 chars)
        long_description = "EDGE_CASE_PAYLOAD: " + "x" * 9980

        return {
            "plan_id": plan_id,
            "intent_id": f"intent-edge-{plan_id}",
            "version": "1.0",
            "description": long_description,
            "specialist_type": specialist_type,
            "domain": "test-edge-cases",
            "priority": "critical",
            "tasks": large_tasks,
            "metadata": {
                "empty_string": "",
                "zero_value": 0,
                "max_int": 2147483647,
                "min_float": 0.0,
                "max_float": 0.999999999,
                "large_array": list(range(500))
            },
            "complexity_score": 0.0,
            "confidence_score": 1.0,
            "risk_score": 0.999999
        }

    def generate_minimal_payload(self, specialist_type: str) -> Dict[str, Any]:
        """Generate absolute minimal payload with only required fields"""
        plan_id = self._next_id()
        return {
            "plan_id": plan_id,
            "intent_id": f"intent-minimal-{plan_id}"
        }


class ComprehensiveSpecialistTester:
    """Comprehensive tester for all specialists with multiple scenarios"""

    SPECIALISTS = {
        "business": "specialist-business",
        "technical": "specialist-technical",
        "behavior": "specialist-behavior",
        "evolution": "specialist-evolution",
        "architecture": "specialist-architecture"
    }

    def __init__(self, namespace: str = "neural-hive", output_dir: str = "/tmp/grpc-comprehensive-tests"):
        self.namespace = namespace
        self.output_dir = Path(output_dir)
        self.channels = {}
        self.stubs = {}
        self.payload_generator = PayloadGenerator()
        self.test_results = []

        # Create output directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "stacktraces").mkdir(exist_ok=True)
        (self.output_dir / "payloads").mkdir(exist_ok=True)
        (self.output_dir / "logs").mkdir(exist_ok=True)

        logger.info("comprehensive_tester_initialized", namespace=namespace, output_dir=str(output_dir))

    def initialize(self) -> bool:
        """Initialize gRPC channels and stubs for all specialists"""
        logger.info("initializing_grpc_connections")

        # Configure gRPC channel options for large payloads and keepalive
        options = [
            ('grpc.max_send_message_length', 50 * 1024 * 1024),  # 50 MB
            ('grpc.max_receive_message_length', 50 * 1024 * 1024),  # 50 MB
            ('grpc.keepalive_time_ms', 30000),  # 30 seconds
            ('grpc.keepalive_timeout_ms', 10000),  # 10 seconds
            ('grpc.http2.max_pings_without_data', 0),  # Allow pings without data
            ('grpc.keepalive_permit_without_calls', 1),  # Allow keepalive without calls
        ]

        for specialist_type, service_name in self.SPECIALISTS.items():
            try:
                endpoint = f"{service_name}.{self.namespace}.svc.cluster.local:50051"
                logger.info("connecting_to_specialist", specialist=specialist_type, endpoint=endpoint)

                channel = grpc.insecure_channel(endpoint, options=options)
                stub = specialist_pb2_grpc.SpecialistServiceStub(channel)

                # Test connection
                grpc.channel_ready_future(channel).result(timeout=10)

                self.channels[specialist_type] = channel
                self.stubs[specialist_type] = stub

                logger.info("specialist_connected", specialist=specialist_type)
            except Exception as e:
                logger.error("specialist_connection_failed", specialist=specialist_type, error=str(e))
                return False

        logger.info("all_specialists_connected", count=len(self.stubs))
        return True

    def test_evaluate_plan_with_scenario(
        self,
        specialist_type: str,
        scenario_name: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Test EvaluatePlan with specific scenario payload"""

        test_start_time = time.time()
        result = {
            "specialist_type": specialist_type,
            "scenario_name": scenario_name,
            "success": False,
            "test_timestamp": datetime.now(timezone.utc).isoformat()
        }

        try:
            stub = self.stubs.get(specialist_type)
            if not stub:
                raise ValueError(f"Specialist {specialist_type} not initialized")

            logger.info("testing_scenario", specialist=specialist_type, scenario=scenario_name)

            # Serialize payload
            serialization_start = time.time()
            payload_bytes = json.dumps(payload).encode('utf-8')
            serialization_time = (time.time() - serialization_start) * 1000

            result["payload_size_bytes"] = len(payload_bytes)
            result["serialization_time_ms"] = round(serialization_time, 2)
            result["payload_preview"] = json.dumps(payload)[:200] + "..."

            # Save full payload
            payload_file = self.output_dir / "payloads" / f"{specialist_type}_{scenario_name}_payload.json"
            with open(payload_file, 'w') as f:
                json.dump(payload, f, indent=2)

            # Create gRPC request
            request = specialist_pb2.EvaluatePlanRequest(
                plan_id=payload.get("plan_id", "unknown"),
                intent_id=payload.get("intent_id", "unknown"),
                correlation_id=str(uuid.uuid4()),
                trace_id=f"trace-{scenario_name}-{int(time.time())}",
                span_id=f"span-{scenario_name}-{int(time.time())}",
                cognitive_plan=payload_bytes,
                plan_version="1.0.0",
                context={
                    "test_type": "comprehensive",
                    "scenario": scenario_name,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                },
                timeout_ms=30000
            )

            # Execute gRPC call
            grpc_start = time.time()
            response = stub.EvaluatePlan(request, timeout=30)
            grpc_time = (time.time() - grpc_start) * 1000
            result["grpc_call_time_ms"] = round(grpc_time, 2)

            # Deserialize response
            deserialization_start = time.time()

            # CRITICAL VALIDATIONS (from test-grpc-isolated.py lines 164-218)

            # Validation 1: Response is not None
            if response is None:
                raise ValueError("Response is None")
            logger.info("validation_1_passed", check="response_not_none")

            # Validation 2: Response type is EvaluatePlanResponse
            if not isinstance(response, specialist_pb2.EvaluatePlanResponse):
                raise TypeError(f"Response type is {type(response)}, expected EvaluatePlanResponse")
            logger.info("validation_2_passed", check="response_type_correct")

            # Validation 3: Field 'evaluated_at' exists
            if not response.HasField('evaluated_at'):
                raise ValueError("Response does not have 'evaluated_at' field")
            logger.info("validation_3_passed", check="evaluated_at_field_exists")

            # Validation 4: Field 'evaluated_at' is Timestamp
            if not isinstance(response.evaluated_at, Timestamp):
                raise TypeError(
                    f"Field 'evaluated_at' is type {type(response.evaluated_at)}, expected Timestamp. "
                    f"Value: {response.evaluated_at}"
                )
            logger.info("validation_4_passed", check="evaluated_at_is_timestamp")

            # Validation 5: Access to evaluated_at.seconds and evaluated_at.nanos (CRITICAL)
            try:
                seconds = response.evaluated_at.seconds
                nanos = response.evaluated_at.nanos
                logger.info("validation_5_passed", check="timestamp_fields_accessible", seconds=seconds, nanos=nanos)

                # Convert to datetime with nanosecond precision
                timestamp_float = seconds + (nanos / 1e9)
                evaluated_at_dt = datetime.fromtimestamp(timestamp_float, tz=timezone.utc)
                evaluated_at_iso = evaluated_at_dt.isoformat()

                result["evaluated_at_seconds"] = seconds
                result["evaluated_at_nanos"] = nanos
                result["evaluated_at_iso"] = evaluated_at_iso

            except AttributeError as e:
                logger.error("validation_5_failed", check="timestamp_fields_access", error=str(e))
                raise TypeError(f"'int' object has no attribute 'seconds': {e}") from e

            deserialization_time = (time.time() - deserialization_start) * 1000
            result["deserialization_time_ms"] = round(deserialization_time, 2)

            # Extract other response fields from nested opinion structure
            if response.HasField('opinion'):
                result["recommendation"] = response.opinion.recommendation[:100] if response.opinion.recommendation else "N/A"
                result["confidence_score"] = response.opinion.confidence_score
                result["reasoning_summary"] = response.opinion.reasoning_summary[:100] if response.opinion.reasoning_summary else "N/A"
            else:
                result["recommendation"] = "N/A (no opinion)"
                result["confidence_score"] = 0.0
                result["reasoning_summary"] = "N/A (no opinion)"

            # Test passed
            result["success"] = True
            result["total_time_ms"] = round((time.time() - test_start_time) * 1000, 2)

            logger.info(
                "scenario_test_passed",
                specialist=specialist_type,
                scenario=scenario_name,
                total_time_ms=result["total_time_ms"]
            )

        except grpc.RpcError as e:
            result["error"] = f"gRPC Error: {e.code()}: {e.details()}"
            result["error_type"] = "grpc.RpcError"
            result["traceback"] = traceback.format_exc()
            logger.error("scenario_test_failed_grpc", specialist=specialist_type, scenario=scenario_name, error=str(e))
            self._save_stack_trace(specialist_type, scenario_name, result, payload)

        except (TypeError, ValueError, AttributeError) as e:
            result["error"] = str(e)
            result["error_type"] = type(e).__name__
            result["traceback"] = traceback.format_exc()
            logger.error("scenario_test_failed_validation", specialist=specialist_type, scenario=scenario_name, error=str(e))
            self._save_stack_trace(specialist_type, scenario_name, result, payload)

        except Exception as e:
            result["error"] = f"Unexpected error: {str(e)}"
            result["error_type"] = type(e).__name__
            result["traceback"] = traceback.format_exc()
            logger.error("scenario_test_failed_unexpected", specialist=specialist_type, scenario=scenario_name, error=str(e))
            self._save_stack_trace(specialist_type, scenario_name, result, payload)

        self.test_results.append(result)
        return result

    def _save_stack_trace(self, specialist_type: str, scenario_name: str, result: Dict[str, Any], payload: Dict[str, Any]):
        """Save detailed stack trace for failed test"""
        stack_trace_file = self.output_dir / "stacktraces" / f"{specialist_type}_{scenario_name}_stacktrace.txt"

        with open(stack_trace_file, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write(f"STACK TRACE: {specialist_type} - {scenario_name}\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Timestamp: {result.get('test_timestamp', 'N/A')}\n")
            f.write(f"Error Type: {result.get('error_type', 'N/A')}\n")
            f.write(f"Error Message: {result.get('error', 'N/A')}\n\n")
            f.write("-" * 80 + "\n")
            f.write("FULL PAYLOAD:\n")
            f.write("-" * 80 + "\n")
            f.write(json.dumps(payload, indent=2) + "\n\n")
            f.write("-" * 80 + "\n")
            f.write("TRACEBACK:\n")
            f.write("-" * 80 + "\n")
            f.write(result.get('traceback', 'No traceback available') + "\n")

        logger.info("stack_trace_saved", file=str(stack_trace_file))

    def test_specialist_all_scenarios(self, specialist_type: str) -> List[Dict[str, Any]]:
        """Test all scenarios for a specific specialist"""
        logger.info("testing_specialist_all_scenarios", specialist=specialist_type)

        scenarios = [
            ("simple", self.payload_generator.generate_simple_payload(specialist_type)),
            ("complex", self.payload_generator.generate_complex_payload(specialist_type)),
            ("special_chars", self.payload_generator.generate_special_characters_payload(specialist_type)),
            ("edge_case", self.payload_generator.generate_edge_case_payload(specialist_type)),
            ("minimal", self.payload_generator.generate_minimal_payload(specialist_type))
        ]

        results = []
        for scenario_name, payload in scenarios:
            result = self.test_evaluate_plan_with_scenario(specialist_type, scenario_name, payload)
            results.append(result)

            # Small delay between tests
            time.sleep(1)

        return results

    def test_all_specialists_all_scenarios(self) -> Dict[str, List[Dict[str, Any]]]:
        """Test all specialists with all scenarios"""
        logger.info("testing_all_specialists_all_scenarios")

        all_results = {}
        for specialist_type in self.SPECIALISTS.keys():
            logger.info("starting_specialist_tests", specialist=specialist_type)
            results = self.test_specialist_all_scenarios(specialist_type)
            all_results[specialist_type] = results
            logger.info("completed_specialist_tests", specialist=specialist_type, total_tests=len(results))

        return all_results

    def test_specialist_business_focused(self) -> List[Dict[str, Any]]:
        """Execute extensive testing for specialist-business only"""
        logger.info("testing_specialist_business_focused")

        specialist_type = "business"

        # Standard 5 scenarios
        scenarios = [
            ("simple", self.payload_generator.generate_simple_payload(specialist_type)),
            ("complex", self.payload_generator.generate_complex_payload(specialist_type)),
            ("special_chars", self.payload_generator.generate_special_characters_payload(specialist_type)),
            ("edge_case", self.payload_generator.generate_edge_case_payload(specialist_type)),
            ("minimal", self.payload_generator.generate_minimal_payload(specialist_type))
        ]

        # Additional business-specific scenarios
        plan_id = self.payload_generator._next_id()
        scenarios.extend([
            ("business_domain", {
                "plan_id": plan_id,
                "intent_id": f"intent-business-{plan_id}",
                "domain": "business",
                "specialist_type": "business",
                "description": "Business domain specific payload"
            }),
            ("critical_priority", {
                "plan_id": self.payload_generator._next_id(),
                "intent_id": f"intent-critical-{plan_id}",
                "priority": "critical",
                "specialist_type": "business",
                "description": "Critical priority business payload"
            }),
            ("confidential_security", {
                "plan_id": self.payload_generator._next_id(),
                "intent_id": f"intent-confidential-{plan_id}",
                "security_level": "confidential",
                "specialist_type": "business",
                "description": "Confidential security level payload",
                "metadata": {"classification": "confidential", "clearance_required": "level-3"}
            }),
            ("multi_tenant", {
                "plan_id": self.payload_generator._next_id(),
                "intent_id": f"intent-multitenant-{plan_id}",
                "specialist_type": "business",
                "description": "Multi-tenant business payload",
                "metadata": {"tenant_id": "tenant-001", "tenant_name": "Acme Corp", "tenant_tier": "enterprise"}
            }),
            ("extensive_explainability", {
                "plan_id": self.payload_generator._next_id(),
                "intent_id": f"intent-explain-{plan_id}",
                "specialist_type": "business",
                "description": "Payload with extensive explainability token",
                "explainability_token": "business-explainability-" + "x" * 1000
            })
        ])

        results = []
        for scenario_name, payload in scenarios:
            result = self.test_evaluate_plan_with_scenario(specialist_type, scenario_name, payload)
            results.append(result)
            time.sleep(1)

        return results

    def close(self):
        """Close all gRPC channels"""
        logger.info("closing_grpc_connections")
        for specialist_type, channel in self.channels.items():
            try:
                channel.close()
                logger.info("channel_closed", specialist=specialist_type)
            except Exception as e:
                logger.error("channel_close_failed", specialist=specialist_type, error=str(e))


class TestResultsDocumenter:
    """Generate comprehensive documentation of test results"""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def generate_json_report(self, results: List[Dict[str, Any]], namespace: str) -> str:
        """Generate JSON report with full test results"""
        timestamp = datetime.now(timezone.utc).isoformat()

        report = {
            "test_session": {
                "timestamp": timestamp,
                "namespace": namespace,
                "protobuf_version": self._get_protobuf_version(),
                "grpcio_version": self._get_grpcio_version(),
                "python_version": sys.version
            },
            "results": self._group_results_by_specialist(results),
            "summary": self._calculate_summary(results)
        }

        output_file = self.output_dir / f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)

        logger.info("json_report_generated", file=str(output_file))
        return str(output_file)

    def generate_markdown_report(self, results: List[Dict[str, Any]], namespace: str) -> str:
        """Generate formatted Markdown report"""
        timestamp = datetime.now(timezone.utc)

        summary = self._calculate_summary(results)
        grouped_results = self._group_results_by_specialist(results)

        md_content = f"""# gRPC Comprehensive Test Results

## Test Session Information
- **Timestamp**: {timestamp.isoformat()}
- **Namespace**: {namespace}
- **Protobuf Version**: {self._get_protobuf_version()}
- **gRPC Version**: {self._get_grpcio_version()}
- **Python Version**: {sys.version.split()[0]}
- **Test Script**: test-grpc-comprehensive.py
- **Output Directory**: {self.output_dir}

## Executive Summary

### Overall Results
- **Total Tests**: {summary['total_tests']}
- **Passed**: {summary['passed']} ✅
- **Failed**: {summary['failed']} ❌
- **Pass Rate**: {summary['pass_rate']:.1f}%

"""

        if summary['failed'] > 0:
            md_content += f"""### Critical Findings
⚠️ **CRITICAL**: {summary['failed']} tests failed. Review failure details below.

"""
        else:
            md_content += """### Critical Findings
✅ **SUCCESS**: All tests passed! The TypeError issue appears to be resolved.

"""

        # Results by specialist
        md_content += "## Results by Specialist\n\n"

        for specialist_type, specialist_results in grouped_results.items():
            md_content += f"### specialist-{specialist_type}\n\n"
            md_content += "| Scenario | Status | Payload Size | Processing Time | evaluated_at | Error |\n"
            md_content += "|----------|--------|--------------|-----------------|--------------|-------|\n"

            for result in specialist_results:
                status = "✅ PASS" if result['success'] else "❌ FAIL"
                payload_size = f"{result.get('payload_size_bytes', 0)} bytes"
                processing_time = f"{result.get('total_time_ms', 0):.0f} ms"
                evaluated_at = result.get('evaluated_at_iso', 'N/A')
                error = result.get('error', '-')[:50] if not result['success'] else '-'

                md_content += f"| {result['scenario_name']} | {status} | {payload_size} | {processing_time} | {evaluated_at} | {error} |\n"

            pass_count = sum(1 for r in specialist_results if r['success'])
            pass_rate = (pass_count / len(specialist_results) * 100) if specialist_results else 0
            md_content += f"\n**Pass Rate**: {pass_rate:.0f}% ({pass_count}/{len(specialist_results)})\n\n"

        # Failure analysis
        failures = [r for r in results if not r['success']]
        if failures:
            md_content += "## Detailed Failure Analysis\n\n"
            for i, failure in enumerate(failures, 1):
                md_content += f"### Failure {i}: {failure['specialist_type']} - {failure['scenario_name']}\n\n"
                md_content += f"**Error Type**: {failure.get('error_type', 'Unknown')}\n\n"
                md_content += f"**Error Message**:\n```\n{failure.get('error', 'No error message')}\n```\n\n"
                md_content += f"**Payload Preview**:\n```\n{failure.get('payload_preview', 'N/A')}\n```\n\n"
                md_content += f"**Full Stack Trace**: See `stacktraces/{failure['specialist_type']}_{failure['scenario_name']}_stacktrace.txt`\n\n"

        # Performance metrics
        md_content += "## Performance Metrics\n\n"
        md_content += self._generate_performance_tables(grouped_results)

        # Recommendations
        md_content += "\n## Recommendations\n\n"
        if summary['failed'] > 0:
            md_content += """### Immediate Actions
1. **CRITICAL**: Review failure stack traces in `stacktraces/` directory
2. **HIGH**: Verify protobuf version compatibility
3. **HIGH**: Check serialization/deserialization logic

### Next Steps
1. Review failure details in this report
2. Execute protobuf version analysis: `./scripts/debug/run-full-version-analysis.sh`
3. Implement corrections based on findings
4. Re-run this test: `./scripts/debug/run-grpc-comprehensive-tests.sh`

"""
        else:
            md_content += """### Success Path
✅ All tests passed! Next steps:
1. Document successful resolution
2. Execute E2E test: `python3 test-fluxo-completo-e2e.py`
3. Monitor production for 24 hours
4. Close related tickets

"""

        output_file = self.output_dir / f"TEST_RESULTS_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(output_file, 'w') as f:
            f.write(md_content)

        logger.info("markdown_report_generated", file=str(output_file))
        return str(output_file)

    def _group_results_by_specialist(self, results: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group results by specialist type"""
        grouped = {}
        for result in results:
            specialist = result['specialist_type']
            if specialist not in grouped:
                grouped[specialist] = []
            grouped[specialist].append(result)
        return grouped

    def _calculate_summary(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate summary statistics"""
        total = len(results)
        passed = sum(1 for r in results if r['success'])
        failed = total - passed
        pass_rate = (passed / total * 100) if total > 0 else 0

        return {
            "total_tests": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": pass_rate
        }

    def _generate_performance_tables(self, grouped_results: Dict[str, List[Dict[str, Any]]]) -> str:
        """Generate performance metrics tables"""
        md = "### Processing Time by Specialist\n\n"
        md += "| Specialist | Min | Max | Avg | Median |\n"
        md += "|------------|-----|-----|-----|--------|\n"

        for specialist, results in grouped_results.items():
            times = [r.get('total_time_ms', 0) for r in results if r.get('total_time_ms')]
            if times:
                min_time = min(times)
                max_time = max(times)
                avg_time = sum(times) / len(times)
                median_time = sorted(times)[len(times) // 2]
                md += f"| {specialist} | {min_time:.0f}ms | {max_time:.0f}ms | {avg_time:.0f}ms | {median_time:.0f}ms |\n"

        return md

    def _get_protobuf_version(self) -> str:
        """Get protobuf version"""
        try:
            import google.protobuf
            return google.protobuf.__version__
        except:
            return "unknown"

    def _get_grpcio_version(self) -> str:
        """Get grpcio version"""
        try:
            import grpc
            return grpc.__version__
        except:
            return "unknown"


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Comprehensive gRPC testing for Neural Hive specialists",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test all specialists with all scenarios
  python3 test-grpc-comprehensive.py

  # Test only specialist-business with focused scenarios
  python3 test-grpc-comprehensive.py --focus-business

  # Test specific specialist
  python3 test-grpc-comprehensive.py --specialist technical

  # Test specific scenario across all specialists
  python3 test-grpc-comprehensive.py --scenario complex
        """
    )

    parser.add_argument(
        '--specialist',
        type=str,
        choices=['business', 'technical', 'behavior', 'evolution', 'architecture'],
        help='Test only specific specialist'
    )

    parser.add_argument(
        '--scenario',
        type=str,
        choices=['simple', 'complex', 'special_chars', 'edge_case', 'minimal'],
        help='Test only specific scenario'
    )

    parser.add_argument(
        '--focus-business',
        action='store_true',
        help='Execute extensive testing for specialist-business (10 scenarios)'
    )

    parser.add_argument(
        '--namespace',
        type=str,
        default='neural-hive',
        help='Kubernetes namespace (default: neural-hive)'
    )

    parser.add_argument(
        '--output-dir',
        type=str,
        default='/tmp/grpc-comprehensive-tests',
        help='Output directory for results (default: /tmp/grpc-comprehensive-tests)'
    )

    return parser.parse_args()


def print_banner(args):
    """Print test banner with configuration"""
    print("=" * 80)
    print("  gRPC COMPREHENSIVE TEST SUITE")
    print("  Neural Hive Mind - Specialist Testing")
    print("=" * 80)
    print(f"Namespace:    {args.namespace}")
    print(f"Output Dir:   {args.output_dir}")
    print(f"Timestamp:    {datetime.now(timezone.utc).isoformat()}")

    try:
        import google.protobuf
        print(f"Protobuf:     {google.protobuf.__version__}")
    except:
        print("Protobuf:     unknown")

    try:
        import grpc
        print(f"gRPC:         {grpc.__version__}")
    except:
        print("gRPC:         unknown")

    print(f"Python:       {sys.version.split()[0]}")
    print("=" * 80)
    print()


def main():
    """Main execution function"""
    args = parse_arguments()

    print_banner(args)

    tester = None
    exit_code = 0

    try:
        # Initialize tester
        tester = ComprehensiveSpecialistTester(
            namespace=args.namespace,
            output_dir=args.output_dir
        )

        if not tester.initialize():
            logger.error("initialization_failed")
            return 1

        # Execute tests based on arguments
        if args.focus_business:
            print("Executing focused testing for specialist-business (10 scenarios)...\n")
            results = tester.test_specialist_business_focused()

        elif args.specialist and args.scenario:
            print(f"Executing single test: {args.specialist} - {args.scenario}\n")
            payload_gen = PayloadGenerator()
            payload = getattr(payload_gen, f"generate_{args.scenario}_payload")(args.specialist)
            result = tester.test_evaluate_plan_with_scenario(args.specialist, args.scenario, payload)
            results = [result]

        elif args.specialist:
            print(f"Executing all scenarios for specialist: {args.specialist}\n")
            results = tester.test_specialist_all_scenarios(args.specialist)

        elif args.scenario:
            print(f"Executing scenario '{args.scenario}' for all specialists\n")
            results = []
            payload_gen = PayloadGenerator()
            for specialist in ComprehensiveSpecialistTester.SPECIALISTS.keys():
                payload = getattr(payload_gen, f"generate_{args.scenario}_payload")(specialist)
                result = tester.test_evaluate_plan_with_scenario(specialist, args.scenario, payload)
                results.append(result)

        else:
            print("Executing all scenarios for all specialists (25 tests total)...\n")
            all_results = tester.test_all_specialists_all_scenarios()
            results = []
            for specialist_results in all_results.values():
                results.extend(specialist_results)

        # Generate reports
        print("\nGenerating reports...\n")
        documenter = TestResultsDocumenter(Path(args.output_dir))

        json_file = documenter.generate_json_report(results, args.namespace)
        print(f"✅ JSON report:     {json_file}")

        md_file = documenter.generate_markdown_report(results, args.namespace)
        print(f"✅ Markdown report: {md_file}")

        # Display summary
        print("\n" + "=" * 80)
        print("  TEST SUMMARY")
        print("=" * 80)

        total = len(results)
        passed = sum(1 for r in results if r['success'])
        failed = total - passed
        pass_rate = (passed / total * 100) if total > 0 else 0

        print(f"Total Tests:  {total}")
        print(f"Passed:       {passed} ✅")
        print(f"Failed:       {failed} ❌")
        print(f"Pass Rate:    {pass_rate:.1f}%")
        print("=" * 80)

        if failed > 0:
            print("\n⚠️  FAILURES DETECTED")
            print(f"Review detailed results in: {md_file}")
            print(f"Stack traces available in: {Path(args.output_dir) / 'stacktraces'}/")
            exit_code = 1
        else:
            print("\n✅ SUCCESS: All tests passed!")
            print("The evaluated_at timestamp field is working correctly.")

        print(f"\nAll results saved to: {args.output_dir}")
        print()

    except KeyboardInterrupt:
        logger.warning("test_interrupted_by_user")
        print("\n\n⚠️  Tests interrupted by user")
        exit_code = 130

    except Exception as e:
        logger.error("test_execution_failed", error=str(e), traceback=traceback.format_exc())
        print(f"\n\n❌ ERROR: {str(e)}")
        print("See logs for details")
        exit_code = 1

    finally:
        if tester:
            tester.close()

    return exit_code


if __name__ == '__main__':
    sys.exit(main())
