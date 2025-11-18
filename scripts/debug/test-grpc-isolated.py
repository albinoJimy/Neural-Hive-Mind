#!/usr/bin/env python3

"""
==============================================================================
Test gRPC Specialists - Isolated Programmatic Invocation
==============================================================================
Purpose: Test EvaluatePlan method using exact validation code from client
References:
  - services/consensus-engine/src/clients/specialists_grpc_client.py
  - libraries/python/neural_hive_specialists/proto_gen/specialist_pb2.py
  - test-grpc-specialists.py
==============================================================================

NOTE: This script tests a single simple payload per specialist.
For comprehensive testing with multiple payload types (simple, complex,
special characters, edge cases), use:
  python3 scripts/debug/test-grpc-comprehensive.py

For orchestrated execution of all test scenarios, use:
  ./scripts/debug/run-grpc-comprehensive-tests.sh
==============================================================================
"""

import asyncio
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Dict

import grpc
import structlog
from google.protobuf.timestamp_pb2 import Timestamp
from neural_hive_specialists.proto_gen import specialist_pb2, specialist_pb2_grpc

# Configure structured logging with DEBUG level
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(colors=True)
    ]
)
logger = structlog.get_logger()


class IsolatedSpecialistTester:
    """Test specialist gRPC communication with detailed validation"""

    def __init__(self):
        # Configuração do namespace (configurável via variável de ambiente)
        specialists_namespace = os.getenv('SPECIALISTS_NAMESPACE', 'neural-hive')

        self.endpoints = {
            'business': f'specialist-business.{specialists_namespace}.svc.cluster.local:50051',
            'technical': f'specialist-technical.{specialists_namespace}.svc.cluster.local:50051',
            'behavior': f'specialist-behavior.{specialists_namespace}.svc.cluster.local:50051',
            'evolution': f'specialist-evolution.{specialists_namespace}.svc.cluster.local:50051',
            'architecture': f'specialist-architecture.{specialists_namespace}.svc.cluster.local:50051'
        }
        self.specialists_namespace = specialists_namespace
        self.channels = {}
        self.stubs = {}
        self.test_results = {}

    async def initialize(self):
        """Initialize gRPC channels and stubs for all specialists"""
        logger.info("Initializing gRPC channels", namespace=self.specialists_namespace)

        # gRPC channel options (same as specialists_grpc_client.py lines 37-42)
        options = [
            ('grpc.max_send_message_length', 50 * 1024 * 1024),
            ('grpc.max_receive_message_length', 50 * 1024 * 1024),
            ('grpc.keepalive_time_ms', 30000),
            ('grpc.keepalive_timeout_ms', 10000),
            ('grpc.http2.max_pings_without_data', 0),
            ('grpc.keepalive_permit_without_calls', 1),
        ]

        for specialist_type, endpoint in self.endpoints.items():
            try:
                channel = grpc.aio.insecure_channel(endpoint, options=options)

                # Wait for channel to be ready
                try:
                    await channel.channel_ready()
                    logger.info(
                        "Channel ready",
                        specialist_type=specialist_type,
                        endpoint=endpoint
                    )
                except Exception as ready_error:
                    logger.error(
                        "Channel failed to become ready",
                        specialist_type=specialist_type,
                        endpoint=endpoint,
                        error=str(ready_error)
                    )
                    await channel.close()
                    raise

                stub = specialist_pb2_grpc.SpecialistServiceStub(channel)

                self.channels[specialist_type] = channel
                self.stubs[specialist_type] = stub

                logger.info(
                    "Channel initialized",
                    specialist_type=specialist_type,
                    endpoint=endpoint
                )
            except Exception as e:
                logger.error(
                    "Failed to initialize channel",
                    specialist_type=specialist_type,
                    endpoint=endpoint,
                    error=str(e)
                )
                raise

    async def test_evaluate_plan(self, specialist_type: str) -> dict:
        """
        Test EvaluatePlan invocation with exact validation from client code
        Replicates specialists_grpc_client.py lines 79-163
        """
        stub = self.stubs[specialist_type]

        # Create test cognitive plan
        cognitive_plan = {
            'plan_id': f'test-isolated-{specialist_type}-001',
            'intent_id': 'test-intent-isolated-001',
            'correlation_id': 'test-correlation-isolated-001',
            'version': '1.0.0',
            'description': f'Teste isolado do specialist {specialist_type}'
        }

        plan_bytes = json.dumps(cognitive_plan).encode('utf-8')

        # Create EvaluatePlanRequest (same structure as specialists_grpc_client.py lines 79-89)
        request = specialist_pb2.EvaluatePlanRequest(
            plan_id=cognitive_plan['plan_id'],
            intent_id=cognitive_plan['intent_id'],
            correlation_id=cognitive_plan.get('correlation_id', ''),
            trace_id='test-trace-isolated-001',
            span_id='test-span-isolated-001',
            cognitive_plan=plan_bytes,
            plan_version='1.0.0',
            context={'test': 'true'},
            timeout_ms=30000
        )

        logger.debug(
            "Sending EvaluatePlan request",
            specialist_type=specialist_type,
            plan_id=cognitive_plan['plan_id'],
            request_size=len(plan_bytes)
        )

        try:
            # Invoke with timeout
            response = await asyncio.wait_for(
                stub.EvaluatePlan(request),
                timeout=30.0
            )

            logger.info(
                "Response received",
                specialist_type=specialist_type,
                response_type=type(response).__name__
            )

            # CRITICAL VALIDATIONS (replicate specialists_grpc_client.py lines 102-163)

            # Validate response is not None
            if response is None:
                raise ValueError("Response is None")

            logger.debug(
                "Validation 1/5: Response is not None",
                specialist_type=specialist_type
            )

            # Validate response type
            if not isinstance(response, specialist_pb2.EvaluatePlanResponse):
                raise TypeError(
                    f"Expected EvaluatePlanResponse, got {type(response).__name__}"
                )

            logger.debug(
                "Validation 2/5: Response type is correct",
                specialist_type=specialist_type,
                response_type=type(response).__name__
            )

            # Validate evaluated_at field exists
            if not response.HasField('evaluated_at'):
                raise ValueError("Response missing 'evaluated_at' field")

            logger.debug(
                "Validation 3/5: evaluated_at field exists",
                specialist_type=specialist_type
            )

            # Validate evaluated_at is Timestamp
            if not isinstance(response.evaluated_at, Timestamp):
                raise TypeError(
                    f"Expected Timestamp for evaluated_at, got {type(response.evaluated_at).__name__}"
                )

            logger.debug(
                "Validation 4/5: evaluated_at is Timestamp",
                specialist_type=specialist_type,
                evaluated_at_type=type(response.evaluated_at).__name__
            )

            # CRITICAL TEST: Access timestamp fields (this is where TypeError occurs)
            try:
                seconds = response.evaluated_at.seconds
                nanos = response.evaluated_at.nanos

                logger.info(
                    "Validation 5/5: Timestamp fields accessed successfully",
                    specialist_type=specialist_type,
                    seconds=seconds,
                    nanos=nanos
                )

                # Convert to datetime
                evaluated_datetime = datetime.fromtimestamp(
                    seconds + nanos / 1e9,
                    tz=timezone.utc
                )

                logger.info(
                    "Timestamp conversion successful",
                    specialist_type=specialist_type,
                    evaluated_at_iso=evaluated_datetime.isoformat()
                )

                # Return success result
                return {
                    'specialist_type': specialist_type,
                    'success': True,
                    'opinion_id': response.opinion_id,
                    'evaluated_at_seconds': seconds,
                    'evaluated_at_nanos': nanos,
                    'evaluated_at_iso': evaluated_datetime.isoformat(),
                    'processing_time_ms': response.processing_time_ms,
                    'response_type': type(response).__name__,
                    'error': None
                }

            except (AttributeError, TypeError) as e:
                # This is the critical error we're investigating
                logger.error(
                    "TypeError/AttributeError during timestamp access",
                    specialist_type=specialist_type,
                    error=str(e),
                    error_type=type(e).__name__,
                    response_type=type(response).__name__,
                    has_evaluated_at=response.HasField('evaluated_at') if response else False,
                    evaluated_at_type=type(response.evaluated_at).__name__ if response and response.HasField('evaluated_at') else None,
                    traceback=traceback.format_exc()
                )

                return {
                    'specialist_type': specialist_type,
                    'success': False,
                    'error': str(e),
                    'error_type': type(e).__name__,
                    'traceback': traceback.format_exc(),
                    'response_type': type(response).__name__,
                    'has_evaluated_at': response.HasField('evaluated_at'),
                    'evaluated_at_type': type(response.evaluated_at).__name__
                }

        except asyncio.TimeoutError:
            logger.error(
                "Timeout waiting for response",
                specialist_type=specialist_type
            )
            return {
                'specialist_type': specialist_type,
                'success': False,
                'error': 'Timeout after 30 seconds',
                'error_type': 'TimeoutError'
            }

        except grpc.RpcError as e:
            logger.error(
                "gRPC error",
                specialist_type=specialist_type,
                error=str(e),
                status_code=e.code() if hasattr(e, 'code') else None,
                details=e.details() if hasattr(e, 'details') else None
            )
            return {
                'specialist_type': specialist_type,
                'success': False,
                'error': str(e),
                'error_type': 'RpcError',
                'status_code': str(e.code()) if hasattr(e, 'code') else None
            }

        except Exception as e:
            logger.error(
                "Unexpected error",
                specialist_type=specialist_type,
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc()
            )
            return {
                'specialist_type': specialist_type,
                'success': False,
                'error': str(e),
                'error_type': type(e).__name__,
                'traceback': traceback.format_exc()
            }

    async def test_all_specialists(self) -> dict:
        """Test all specialists sequentially"""
        logger.info("Starting tests for all specialists")

        for specialist_type in self.endpoints.keys():
            logger.info(
                "Testing specialist",
                specialist_type=specialist_type
            )

            result = await self.test_evaluate_plan(specialist_type)
            self.test_results[specialist_type] = result

            if result['success']:
                logger.info(
                    "Test PASSED",
                    specialist_type=specialist_type
                )
            else:
                logger.error(
                    "Test FAILED",
                    specialist_type=specialist_type,
                    error=result.get('error')
                )

        return self.test_results

    async def close(self):
        """Close all gRPC channels"""
        logger.info("Closing gRPC channels")

        for specialist_type, channel in self.channels.items():
            try:
                await channel.close()
                logger.debug(
                    "Channel closed",
                    specialist_type=specialist_type
                )
            except Exception as e:
                logger.warning(
                    "Error closing channel",
                    specialist_type=specialist_type,
                    error=str(e)
                )


async def main() -> int:
    """Main test execution"""
    namespace = os.getenv('SPECIALISTS_NAMESPACE', 'neural-hive')
    print("========================================")
    print("Teste gRPC Isolado - Specialists")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"Namespace: {namespace}")
    print("========================================")
    print()

    tester = IsolatedSpecialistTester()

    try:
        # Initialize
        await tester.initialize()

        # Run tests
        results = await tester.test_all_specialists()

        # Display summary
        print()
        print("========================================")
        print("RESUMO DOS TESTES")
        print("========================================")
        print()

        success_count = 0
        failure_count = 0

        for specialist_type, result in results.items():
            status = "✓ SUCESSO" if result['success'] else "✗ FALHA"
            print(f"{status} - {specialist_type}")

            if result['success']:
                success_count += 1
                print(f"  opinion_id: {result['opinion_id']}")
                print(f"  evaluated_at.seconds: {result['evaluated_at_seconds']}")
                print(f"  evaluated_at.nanos: {result['evaluated_at_nanos']}")
                print(f"  evaluated_at (ISO): {result['evaluated_at_iso']}")
                print(f"  processing_time_ms: {result['processing_time_ms']}")
            else:
                failure_count += 1
                print(f"  error: {result.get('error')}")
                print(f"  error_type: {result.get('error_type')}")

            print()

        # Statistics
        total = success_count + failure_count
        pass_rate = (success_count * 100 // total) if total > 0 else 0

        print(f"Total: {total}")
        print(f"Sucessos: {success_count}")
        print(f"Falhas: {failure_count}")
        print(f"Taxa de sucesso: {pass_rate}%")
        print()

        # Save results to file
        output_file = '/tmp/test_grpc_isolated_results.json'
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        print(f"Resultados salvos em: {output_file}")
        print()

        return 0 if failure_count == 0 else 1

    except Exception as e:
        logger.error(
            "Fatal error in test execution",
            error=str(e),
            traceback=traceback.format_exc()
        )
        return 1
    finally:
        # Always close connections, even on failure
        try:
            await tester.close()
        except Exception as close_error:
            logger.warning(
                "Error during cleanup",
                error=str(close_error)
            )


if __name__ == '__main__':
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.warning("Teste interrompido pelo usuário")
        sys.exit(130)
    except Exception as e:
        logger.error(
            "Erro fatal no teste",
            error=str(e),
            traceback=traceback.format_exc()
        )
        sys.exit(1)
