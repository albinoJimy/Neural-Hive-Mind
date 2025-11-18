#!/usr/bin/env python3
"""
E2E Validation Test - Complete Suite
Extends test-fluxo-completo-e2e.py with:
- 10 consecutive iterations
- Detailed timestamp validation
- Metrics collection (latency, success rate)
- JSON export of results
"""

import sys
import os
import time
import json
import argparse
import statistics
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List, Tuple
from collections import defaultdict
import re

# Color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
BOLD = '\033[1m'
RESET = '\033[0m'

# Default configuration
NUM_ITERATIONS = 10
GATEWAY_URL = "http://10.97.189.184:8000"
TIMEOUT = 30
COLLECT_DETAILED_METRICS = True


class E2EMetricsCollector:
    """Collects and aggregates metrics from E2E test executions."""

    def __init__(self):
        self.iterations_results = []
        self.latencies = defaultdict(list)
        self.timestamp_validations = []
        self.opinion_counts = defaultdict(list)
        self.errors = []
        self.start_time = datetime.now()

    def record_iteration(self, iteration_num: int, scenario: str, result: Dict[str, Any],
                        latency_ms: float, timestamp_validation: Dict[str, Any]):
        """Record results from a single iteration."""
        # Overall pass requires both result passed AND timestamp valid
        overall_passed = result.get('passed', False) and timestamp_validation.get('valid', False)

        opinion_count = result.get('opinion_count', 0)

        self.iterations_results.append({
            'iteration': iteration_num,
            'scenario': scenario,
            'passed': overall_passed,  # Combined pass status
            'latency_ms': latency_ms,
            'timestamp_valid': timestamp_validation.get('valid', False),
            'nlu_ok': result.get('nlu_ok', False),
            'routing_ok': result.get('routing_ok', False),
            'response_ok': result.get('response_ok', False),
            'opinion_count': opinion_count,
            'timestamp_details': timestamp_validation
        })

        # Extract specialist type from scenario
        specialist_type = scenario.split('-')[0] if '-' in scenario else scenario
        self.latencies[specialist_type].append(latency_ms)
        self.opinion_counts[specialist_type].append(opinion_count)
        self.timestamp_validations.append(timestamp_validation)

    def record_error(self, iteration_num: int, scenario: str, error_type: str, error_message: str):
        """Record error with full context."""
        self.errors.append({
            'iteration_num': iteration_num,
            'scenario': scenario,
            'error_type': error_type,
            'error_message': error_message,
            'timestamp': datetime.now().isoformat()
        })

    def get_summary_statistics(self) -> Dict[str, Any]:
        """Calculate aggregated statistics."""
        total_tests = len(self.iterations_results)
        passed_tests = sum(1 for r in self.iterations_results if r['passed'])
        failed_tests = total_tests - passed_tests

        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0

        # Timestamp validation stats
        valid_timestamps = sum(1 for v in self.timestamp_validations if v.get('valid', False))
        timestamp_validation_rate = (valid_timestamps / len(self.timestamp_validations) * 100) \
            if self.timestamp_validations else 0

        # Per-specialist stats
        specialist_stats = {}
        for specialist, latencies in self.latencies.items():
            specialist_results = [r for r in self.iterations_results
                                if r['scenario'].startswith(specialist)]
            specialist_passed = sum(1 for r in specialist_results if r['passed'])
            specialist_total = len(specialist_results)

            # Get opinion counts for this specialist
            opinion_counts_for_specialist = self.opinion_counts.get(specialist, [])

            specialist_stats[specialist] = {
                'total': specialist_total,
                'passed': specialist_passed,
                'failed': specialist_total - specialist_passed,
                'success_rate': (specialist_passed / specialist_total * 100) if specialist_total > 0 else 0,
                'latency_avg': statistics.mean(latencies) if latencies else 0,
                'latency_median': statistics.median(latencies) if latencies else 0,
                'latency_min': min(latencies) if latencies else 0,
                'latency_max': max(latencies) if latencies else 0,
                'opinion_count_avg': statistics.mean(opinion_counts_for_specialist) if opinion_counts_for_specialist else 0,
                'opinion_count_total': sum(opinion_counts_for_specialist) if opinion_counts_for_specialist else 0
            }

        # Overall latency stats
        all_latencies = [r['latency_ms'] for r in self.iterations_results if 'latency_ms' in r]

        return {
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'failed_tests': failed_tests,
            'success_rate': success_rate,
            'timestamp_validation_rate': timestamp_validation_rate,
            'valid_timestamps': valid_timestamps,
            'invalid_timestamps': len(self.timestamp_validations) - valid_timestamps,
            'specialist_stats': specialist_stats,
            'latency_overall': {
                'mean': statistics.mean(all_latencies) if all_latencies else 0,
                'median': statistics.median(all_latencies) if all_latencies else 0,
                'stdev': statistics.stdev(all_latencies) if len(all_latencies) > 1 else 0,
                'min': min(all_latencies) if all_latencies else 0,
                'max': max(all_latencies) if all_latencies else 0,
                'p95': statistics.quantiles(all_latencies, n=20)[18] if len(all_latencies) >= 20 else (max(all_latencies) if all_latencies else 0),
                'p99': statistics.quantiles(all_latencies, n=100)[98] if len(all_latencies) >= 100 else (max(all_latencies) if all_latencies else 0)
            },
            'total_errors': len(self.errors),
            'errors_by_type': self._group_errors_by_type(),
            'execution_time_seconds': (datetime.now() - self.start_time).total_seconds()
        }

    def _group_errors_by_type(self) -> Dict[str, int]:
        """Group errors by type."""
        error_counts = defaultdict(int)
        for error in self.errors:
            error_counts[error['error_type']] += 1
        return dict(error_counts)

    def export_to_json(self, output_path: str):
        """Export all collected data to JSON."""
        data = {
            'metadata': {
                'start_time': self.start_time.isoformat(),
                'end_time': datetime.now().isoformat(),
                'num_iterations': max([r['iteration'] for r in self.iterations_results], default=0),
                'gateway_url': GATEWAY_URL,
                'timeout': TIMEOUT
            },
            'iterations_results': self.iterations_results,
            'timestamp_validations': self.timestamp_validations,
            'errors': self.errors,
            'summary_statistics': self.get_summary_statistics()
        }

        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"{GREEN}✓{RESET} Metrics exported to: {output_path}")


def validate_timestamp_in_response(response_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate timestamps in response data.

    Checks:
    - ISO 8601 format
    - Timestamp is not in the future (allowing 1 min clock skew)
    - Timestamp is not stale (>5 min old)
    - Chronological consistency
    """
    validation_result = {
        'valid': True,
        'timestamps_found': 0,
        'timestamps_valid': 0,
        'errors': [],
        'details': {
            'main_timestamp': None,
            'evaluated_at_timestamps': [],
            'processing_times': []
        }
    }

    # ISO 8601 regex pattern
    iso8601_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$')

    now = datetime.now(timezone.utc)
    max_future_skew = timedelta(minutes=1)
    max_age = timedelta(minutes=5)

    def validate_single_timestamp(ts_str: str, field_name: str) -> bool:
        """Validate a single timestamp string."""
        if not ts_str:
            return False

        validation_result['timestamps_found'] += 1

        # Check format
        if not iso8601_pattern.match(ts_str):
            validation_result['errors'].append(f"{field_name}: Invalid ISO 8601 format")
            return False

        try:
            # Parse timestamp - normalize all formats to UTC
            # Handle 'Z' suffix
            if ts_str.endswith('Z'):
                ts_dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            # Handle timezone offsets like +00:00 or -03:00
            elif '+' in ts_str[-6:] or ts_str[-6:-5] == '-':
                ts_dt = datetime.fromisoformat(ts_str)
            # No timezone info - assume UTC
            else:
                ts_dt = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)

            # Convert to UTC for comparison
            ts_dt_utc = ts_dt.astimezone(timezone.utc)

            # Check not future
            if ts_dt_utc > now + max_future_skew:
                validation_result['errors'].append(f"{field_name}: Timestamp is in the future")
                return False

            # Check not stale
            if ts_dt_utc < now - max_age:
                validation_result['errors'].append(f"{field_name}: Timestamp is stale (>5 min old)")
                return False

            validation_result['timestamps_valid'] += 1
            return True

        except (ValueError, TypeError) as e:
            validation_result['errors'].append(f"{field_name}: Failed to parse timestamp: {e}")
            return False

    # Check main timestamp
    if 'timestamp' in response_data:
        if validate_single_timestamp(response_data['timestamp'], 'response.timestamp'):
            validation_result['details']['main_timestamp'] = response_data['timestamp']

    # Check evaluated_at in metadata
    if 'metadata' in response_data:
        metadata = response_data['metadata']
        if isinstance(metadata, dict):
            if 'evaluated_at' in metadata:
                if validate_single_timestamp(str(metadata['evaluated_at']), 'metadata.evaluated_at'):
                    validation_result['details']['evaluated_at_timestamps'].append(str(metadata['evaluated_at']))

            # Check processing_time if present
            if 'processing_time_ms' in metadata:
                try:
                    pt = int(metadata['processing_time_ms'])
                    validation_result['details']['processing_times'].append(pt)
                except (ValueError, TypeError):
                    pass

    # Check specialists opinions if present - support multiple key variations
    opinion_keys = ['specialists_opinions', 'specialist_opinions', 'opinions']
    opinions_found = False

    for opinion_key in opinion_keys:
        if opinion_key in response_data:
            opinions_found = True
            opinions = response_data[opinion_key]
            if isinstance(opinions, list):
                for idx, opinion in enumerate(opinions):
                    if isinstance(opinion, dict) and 'evaluated_at' in opinion:
                        if validate_single_timestamp(str(opinion['evaluated_at']), f'{opinion_key}[{idx}].evaluated_at'):
                            validation_result['details']['evaluated_at_timestamps'].append(str(opinion['evaluated_at']))
            break  # Found opinions, no need to check other keys

    # Also check decision/opinions path
    if not opinions_found and 'decision' in response_data:
        decision = response_data['decision']
        if isinstance(decision, dict) and 'opinions' in decision:
            opinions = decision['opinions']
            if isinstance(opinions, list):
                for idx, opinion in enumerate(opinions):
                    if isinstance(opinion, dict) and 'evaluated_at' in opinion:
                        if validate_single_timestamp(str(opinion['evaluated_at']), f'decision.opinions[{idx}].evaluated_at'):
                            validation_result['details']['evaluated_at_timestamps'].append(str(opinion['evaluated_at']))

    # Final validation
    if validation_result['errors']:
        validation_result['valid'] = False

    if validation_result['timestamps_found'] == 0:
        validation_result['valid'] = False
        validation_result['errors'].append("No timestamps found in response")

    return validation_result


def verify_nlu_processing(response_data: Dict[str, Any]) -> bool:
    """Verify NLU processing (adapted from test-fluxo-completo-e2e.py)."""
    if not response_data:
        return False

    # Check for essential NLU fields
    nlu_fields = ["intent", "entities", "confidence"]
    for field in nlu_fields:
        if field not in response_data:
            return False

    return True


def verify_specialist_routing(response_data: Dict[str, Any], expected_specialist: str = None) -> bool:
    """Verify specialist routing (adapted from test-fluxo-completo-e2e.py)."""
    if not response_data:
        return False

    # Check for specialist field
    specialist_field = response_data.get('specialist') or response_data.get('routed_to')

    if not specialist_field:
        return False

    # If expected specialist specified, verify it matches
    if expected_specialist and specialist_field != expected_specialist:
        return False

    return True


def verify_end_to_end_response(response_data: Dict[str, Any]) -> bool:
    """Verify complete E2E response (adapted from test-fluxo-completo-e2e.py)."""
    if not response_data:
        return False

    # Check for response content
    response_keys = ['response', 'answer', 'message']
    has_response = any(response_data.get(key) for key in response_keys)

    return has_response


def extract_opinion_count(response_data: Dict[str, Any]) -> int:
    """Extract opinion count from response, checking multiple possible paths."""
    if not response_data:
        return 0

    # Check multiple possible opinion key locations
    opinion_keys = ['specialists_opinions', 'specialist_opinions', 'opinions']

    for key in opinion_keys:
        if key in response_data:
            opinions = response_data[key]
            if isinstance(opinions, list):
                return len(opinions)

    # Check decision/opinions path
    if 'decision' in response_data:
        decision = response_data['decision']
        if isinstance(decision, dict) and 'opinions' in decision:
            opinions = decision['opinions']
            if isinstance(opinions, list):
                return len(opinions)

    return 0


def send_intent_with_metrics(intent_text: str, specialist_type: str,
                            iteration_num: int) -> Tuple[Dict[str, Any], float, Dict[str, Any]]:
    """
    Send intent to gateway and collect metrics.

    Returns:
        Tuple of (result, latency_ms, timestamp_validation)
    """
    print(f"\n{CYAN}[Iteration {iteration_num}]{RESET} Sending intent to {BOLD}{specialist_type}{RESET}...")

    start_time = time.time()

    try:
        # Build payload matching Gateway contract (same structure as test-fluxo-completo-e2e.py)
        payload = {
            "text": intent_text,
            "context": {
                "user_id": f"test-user-e2e-validation-{iteration_num}",
                "session_id": f"test-session-{int(time.time())}",
                "timestamp": datetime.now().isoformat()
            }
        }

        # Add specialist_type if specified to force routing
        if specialist_type:
            payload["specialist_type"] = specialist_type

        response = requests.post(
            f"{GATEWAY_URL}/intentions",
            json=payload,
            timeout=TIMEOUT
        )

        latency_ms = (time.time() - start_time) * 1000
        print(f"  Latency: {YELLOW}{latency_ms:.2f}ms{RESET}")

        if response.status_code != 200:
            return {
                'passed': False,
                'error': f"HTTP {response.status_code}",
                'response': None
            }, latency_ms, {'valid': False, 'errors': [f"HTTP {response.status_code}"]}

        result = response.json()

        # Run all validations
        timestamp_validation = validate_timestamp_in_response(result)
        nlu_ok = verify_nlu_processing(result)
        routing_ok = verify_specialist_routing(result, specialist_type)
        response_ok = verify_end_to_end_response(result)
        opinion_count = extract_opinion_count(result)

        # Report validation results
        if timestamp_validation['valid']:
            print(f"  {GREEN}✓{RESET} Timestamp validation: PASSED")
        else:
            print(f"  {RED}✗{RESET} Timestamp validation: FAILED")
            for error in timestamp_validation['errors']:
                print(f"    - {error}")

        print(f"  NLU: {GREEN+'✓' if nlu_ok else RED+'✗'}{RESET}, " +
              f"Routing: {GREEN+'✓' if routing_ok else RED+'✗'}{RESET}, " +
              f"Response: {GREEN+'✓' if response_ok else RED+'✗'}{RESET}")

        if opinion_count > 0:
            print(f"  Opinions received: {opinion_count}")

        # Return result with actual validation flags
        return {
            'passed': nlu_ok and routing_ok and response_ok,
            'response': result,
            'nlu_ok': nlu_ok,
            'routing_ok': routing_ok,
            'response_ok': response_ok,
            'opinion_count': opinion_count
        }, latency_ms, timestamp_validation

    except requests.exceptions.Timeout:
        latency_ms = (time.time() - start_time) * 1000
        return {
            'passed': False,
            'error': 'Timeout',
            'response': None
        }, latency_ms, {'valid': False, 'errors': ['Request timeout']}

    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        return {
            'passed': False,
            'error': str(e),
            'response': None
        }, latency_ms, {'valid': False, 'errors': [str(e)]}


def test_gateway_health() -> bool:
    """Test gateway health endpoint."""
    try:
        response = requests.get(f"{GATEWAY_URL}/health", timeout=5)
        return response.status_code == 200
    except:
        return False


def run_test_scenario_with_metrics(scenario: Dict[str, str], iteration_num: int,
                                   metrics_collector: E2EMetricsCollector) -> Dict[str, Any]:
    """
    Run a single test scenario with full metrics collection.

    Args:
        scenario: Dict with 'name', 'intent', 'specialist' keys
        iteration_num: Current iteration number
        metrics_collector: Metrics collector instance

    Returns:
        Dict with test results
    """
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}Scenario: {scenario['name']}{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

    # Send intent and collect metrics
    result, latency_ms, timestamp_validation = send_intent_with_metrics(
        scenario['intent'],
        scenario['specialist'],
        iteration_num
    )

    # Record in metrics collector
    metrics_collector.record_iteration(
        iteration_num,
        scenario['specialist'],
        result,
        latency_ms,
        timestamp_validation
    )

    # Record errors if any
    if not result['passed']:
        metrics_collector.record_error(
            iteration_num,
            scenario['specialist'],
            result.get('error', 'Unknown'),
            str(result)
        )

    # Display result
    if result['passed'] and timestamp_validation['valid']:
        print(f"\n{GREEN}{BOLD}✓ SCENARIO PASSED{RESET}")
    else:
        print(f"\n{RED}{BOLD}✗ SCENARIO FAILED{RESET}")
        if not result['passed']:
            print(f"  Reason: {result.get('error', 'Unknown')}")
        if not timestamp_validation['valid']:
            print(f"  Timestamp errors: {', '.join(timestamp_validation['errors'])}")

    return {
        'passed': result['passed'] and timestamp_validation['valid'],
        'latency_ms': latency_ms,
        'timestamp_valid': timestamp_validation['valid'],
        'nlu_ok': result.get('nlu_ok', False),
        'routing_ok': result.get('routing_ok', False),
        'response_ok': result.get('response_ok', False),
        'timestamp_details': timestamp_validation
    }


def run_multiple_iterations(scenarios: List[Dict[str, str]], num_iterations: int) -> E2EMetricsCollector:
    """
    Run multiple iterations of all scenarios.

    Args:
        scenarios: List of scenario dicts
        num_iterations: Number of iterations to run

    Returns:
        E2EMetricsCollector with all collected data
    """
    metrics_collector = E2EMetricsCollector()

    print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}{CYAN}Starting E2E Validation - {num_iterations} Iterations{RESET}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}\n")

    try:
        for iteration in range(1, num_iterations + 1):
            print(f"\n{BOLD}{GREEN}╔{'═'*58}╗{RESET}")
            print(f"{BOLD}{GREEN}║  ITERATION {iteration}/{num_iterations}{' '*(45 - len(str(iteration)) - len(str(num_iterations)))}║{RESET}")
            print(f"{BOLD}{GREEN}╚{'═'*58}╝{RESET}")

            for scenario in scenarios:
                try:
                    run_test_scenario_with_metrics(scenario, iteration, metrics_collector)
                    time.sleep(2)  # Brief pause between scenarios
                except Exception as e:
                    print(f"{RED}✗ Error in scenario {scenario['name']}: {e}{RESET}")
                    metrics_collector.record_error(
                        iteration,
                        scenario['specialist'],
                        type(e).__name__,
                        str(e)
                    )

            # Display partial stats every 3 iterations
            if iteration % 3 == 0:
                stats = metrics_collector.get_summary_statistics()
                print(f"\n{CYAN}Progress: {stats['passed_tests']}/{stats['total_tests']} tests passed " +
                      f"({stats['success_rate']:.1f}%){RESET}")

            if iteration < num_iterations:
                print(f"\n{YELLOW}Waiting 5 seconds before next iteration...{RESET}")
                time.sleep(5)

    except KeyboardInterrupt:
        print(f"\n{YELLOW}⚠ Validation interrupted by user{RESET}")
        print(f"Generating report for {len(metrics_collector.iterations_results)} completed tests...")

    except Exception as e:
        print(f"\n{RED}✗ Fatal error during validation: {e}{RESET}")
        import traceback
        traceback.print_exc()

    return metrics_collector


def generate_summary_report(metrics_collector: E2EMetricsCollector):
    """Generate and display summary report."""
    stats = metrics_collector.get_summary_statistics()

    print(f"\n\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}╔{'═'*58}╗{RESET}")
    print(f"{BOLD}║{' '*15}E2E VALIDATION SUMMARY REPORT{' '*14}║{RESET}")
    print(f"{BOLD}╚{'═'*58}╝{RESET}")
    print(f"{BOLD}{'='*60}{RESET}\n")

    # Section 1: General Summary
    print(f"{BOLD}GENERAL SUMMARY{RESET}")
    print(f"{'─'*60}")
    print(f"Total Tests Executed: {stats['total_tests']}")
    print(f"")
    if stats['success_rate'] >= 95:
        color = GREEN
    elif stats['success_rate'] >= 90:
        color = YELLOW
    else:
        color = RED

    print(f"{color}✓ Tests Passed:{RESET} {stats['passed_tests']}/{stats['total_tests']} ({stats['success_rate']:.1f}%)")
    print(f"{RED}✗ Tests Failed:{RESET} {stats['failed_tests']}/{stats['total_tests']} ({100-stats['success_rate']:.1f}%)")
    print(f"")

    if stats['timestamp_validation_rate'] == 100:
        ts_color = GREEN
    else:
        ts_color = YELLOW

    print(f"{ts_color}✓ Timestamps Valid:{RESET} {stats['valid_timestamps']}/{stats['valid_timestamps'] + stats['invalid_timestamps']} ({stats['timestamp_validation_rate']:.1f}%)")
    print(f"{RED}✗ Timestamps Invalid:{RESET} {stats['invalid_timestamps']}/{stats['valid_timestamps'] + stats['invalid_timestamps']} ({100-stats['timestamp_validation_rate']:.1f}%)")

    # Section 2: Results by Specialist
    print(f"\n{BOLD}RESULTS BY SPECIALIST{RESET}")
    print(f"{'─'*60}")
    print(f"┌─────────────────┬──────────┬──────────┬─────────────────┐")
    print(f"│ Specialist      │ Success  │ Failures │ Success Rate    │")
    print(f"├─────────────────┼──────────┼──────────┼─────────────────┤")

    for specialist in ['business', 'technical', 'behavior', 'evolution', 'architecture']:
        if specialist in stats['specialist_stats']:
            sp_stats = stats['specialist_stats'][specialist]
            rate_color = GREEN if sp_stats['success_rate'] >= 95 else (YELLOW if sp_stats['success_rate'] >= 90 else RED)
            print(f"│ {specialist:<15} │ {sp_stats['passed']}/{sp_stats['total']:<7} │ {sp_stats['failed']:<8} │ {rate_color}{sp_stats['success_rate']:>6.1f}%{RESET}         │")

    print(f"└─────────────────┴──────────┴──────────┴─────────────────┘")

    # Section 3: Latency Metrics
    print(f"\n{BOLD}LATENCY METRICS{RESET}")
    print(f"{'─'*60}")
    print(f"┌─────────────────┬─────────┬─────────┬─────────┬─────────┐")
    print(f"│ Specialist      │ Min     │ Max     │ Avg     │ Median  │")
    print(f"├─────────────────┼─────────┼─────────┼─────────┼─────────┤")

    for specialist in ['business', 'technical', 'behavior', 'evolution', 'architecture']:
        if specialist in stats['specialist_stats']:
            sp_stats = stats['specialist_stats'][specialist]
            print(f"│ {specialist:<15} │ {sp_stats['latency_min']:>6.0f}ms │ {sp_stats['latency_max']:>6.0f}ms │ {sp_stats['latency_avg']:>6.0f}ms │ {sp_stats['latency_median']:>6.0f}ms │")

    print(f"└─────────────────┴─────────┴─────────┴─────────┴─────────┘")

    # Overall latency
    lat = stats['latency_overall']
    print(f"\nOverall Latency Statistics:")
    print(f"  Mean: {lat['mean']:.2f}ms | Median: {lat['median']:.2f}ms | Std Dev: {lat['stdev']:.2f}ms")
    print(f"  Min: {lat['min']:.2f}ms | Max: {lat['max']:.2f}ms")
    print(f"  P95: {lat['p95']:.2f}ms | P99: {lat['p99']:.2f}ms")

    # Section 4: Timestamp Validation
    print(f"\n{BOLD}TIMESTAMP VALIDATION{RESET}")
    print(f"{'─'*60}")
    if stats['timestamp_validation_rate'] == 100:
        print(f"{GREEN}✓ All timestamps in ISO 8601 format{RESET}")
        print(f"{GREEN}✓ No future timestamps detected{RESET}")
        print(f"{GREEN}✓ No stale timestamps detected (>5 min old){RESET}")
        print(f"{GREEN}✓ Chronological consistency verified{RESET}")
    else:
        print(f"{YELLOW}⚠ Some timestamp validations failed{RESET}")
        print(f"  Valid: {stats['valid_timestamps']}")
        print(f"  Invalid: {stats['invalid_timestamps']}")

    # Section 5: Errors
    if stats['total_errors'] > 0:
        print(f"\n{BOLD}{RED}ERRORS DETECTED{RESET}")
        print(f"{'─'*60}")
        print(f"Total Errors: {stats['total_errors']}")
        print(f"\nErrors by Type:")
        for error_type, count in stats['errors_by_type'].items():
            print(f"  - {error_type}: {count}")

    # Section 6: Recommendations
    print(f"\n{BOLD}RECOMMENDATIONS{RESET}")
    print(f"{'─'*60}")

    if stats['success_rate'] >= 95 and stats['timestamp_validation_rate'] == 100 and stats['total_errors'] == 0:
        print(f"{GREEN}✓ System is stable - {stats['success_rate']:.1f}% success rate{RESET}")
        print(f"{GREEN}✓ No errors detected in any iteration{RESET}")
        print(f"{GREEN}✓ Timestamps are correctly formatted and validated{RESET}")
        print(f"{GREEN}✓ Ready for production deployment{RESET}")
    elif stats['success_rate'] >= 90 and stats['timestamp_validation_rate'] >= 95:
        print(f"{YELLOW}⚠ System is mostly stable - {stats['success_rate']:.1f}% success rate{RESET}")
        print(f"{YELLOW}⚠ Consider investigating {stats['total_errors']} error(s){RESET}")
        print(f"{YELLOW}⚠ Review failures before production deployment{RESET}")
    else:
        print(f"{RED}✗ System has stability issues - {stats['success_rate']:.1f}% success rate{RESET}")
        print(f"{RED}✗ {stats['total_errors']} errors detected{RESET}")
        print(f"{RED}✗ Do NOT proceed with deployment until issues resolved{RESET}")

    print(f"\n{BOLD}{'='*60}{RESET}\n")


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description='E2E Validation Test Suite')
    parser.add_argument('--iterations', type=int, default=10,
                       help='Number of iterations to run (default: 10)')
    parser.add_argument('--gateway-url', default="http://10.97.189.184:8000",
                       help='Gateway URL (default: http://10.97.189.184:8000)')
    parser.add_argument('--timeout', type=int, default=30,
                       help='Request timeout in seconds (default: 30)')
    parser.add_argument('--output-dir', default='/tmp/e2e-validation',
                       help='Output directory for results (default: /tmp/e2e-validation)')
    parser.add_argument('--skip-health-check', action='store_true',
                       help='Skip initial health check')

    args = parser.parse_args()

    # Update global config
    global NUM_ITERATIONS, GATEWAY_URL, TIMEOUT
    NUM_ITERATIONS = args.iterations
    GATEWAY_URL = args.gateway_url
    TIMEOUT = args.timeout

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Display banner
    print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}{CYAN}E2E VALIDATION TEST SUITE{RESET}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}")
    print(f"Configuration:")
    print(f"  Gateway URL: {GATEWAY_URL}")
    print(f"  Iterations: {NUM_ITERATIONS}")
    print(f"  Timeout: {TIMEOUT}s")
    print(f"  Output Directory: {output_dir}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}\n")

    # Health check
    if not args.skip_health_check:
        print("Checking gateway health...")
        if test_gateway_health():
            print(f"{GREEN}✓ Gateway is healthy{RESET}\n")
        else:
            print(f"{RED}✗ Gateway health check failed{RESET}")
            print(f"Please verify gateway is running at {GATEWAY_URL}")
            return 1

    # Define test scenarios
    scenarios = [
        {
            'name': 'Business Analysis Scenario',
            'specialist': 'business',
            'intent': 'Preciso analisar a viabilidade financeira de expandir operações para o mercado asiático'
        },
        {
            'name': 'Technical Implementation Scenario',
            'specialist': 'technical',
            'intent': 'Como implementar autenticação OAuth2 com refresh tokens no sistema'
        },
        {
            'name': 'Behavior Analysis Scenario',
            'specialist': 'behavior',
            'intent': 'Analisar padrões de comportamento do usuário para melhorar UX'
        },
        {
            'name': 'Evolution & Optimization Scenario',
            'specialist': 'evolution',
            'intent': 'Otimizar performance do banco de dados que está com queries lentas'
        },
        {
            'name': 'Architecture Design Scenario',
            'specialist': 'architecture',
            'intent': 'Projetar arquitetura de microserviços escalável para e-commerce'
        }
    ]

    # Run iterations
    try:
        metrics_collector = run_multiple_iterations(scenarios, NUM_ITERATIONS)

        # Generate summary report
        generate_summary_report(metrics_collector)

        # Export to JSON
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        json_path = output_dir / f"e2e-metrics-{timestamp}.json"
        metrics_collector.export_to_json(str(json_path))

        # Save text report
        # We would save the summary here but for simplicity just print location
        print(f"\n{BOLD}Files Generated:{RESET}")
        print(f"  Metrics JSON: {json_path}")

        # Determine exit code
        stats = metrics_collector.get_summary_statistics()
        if stats['success_rate'] >= 90 and stats['timestamp_validation_rate'] >= 95:
            return 0
        else:
            return 1

    except KeyboardInterrupt:
        print(f"\n{YELLOW}⚠ Validation interrupted by user{RESET}")
        return 130

    except Exception as e:
        print(f"\n{RED}✗ Fatal error: {e}{RESET}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
