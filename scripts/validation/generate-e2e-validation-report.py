#!/usr/bin/env python3
"""
E2E Validation Report Generator
Analyzes test results and log monitoring data to generate comprehensive report
"""

import json
import os
import sys
import argparse
import statistics
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
from collections import defaultdict
import re


class E2EReportGenerator:
    """Generates comprehensive E2E validation reports."""

    def __init__(self, test_results_dir: str, logs_dir: str, output_path: str):
        self.test_results_dir = Path(test_results_dir)
        self.logs_dir = Path(logs_dir)
        self.output_path = Path(output_path)
        self.test_data = None
        self.log_summary = None
        self.report_sections = []

    def load_test_results(self):
        """Load test results from JSON file."""
        print("Loading test results...")

        # Find metrics JSON file
        json_files = list(self.test_results_dir.glob("e2e-metrics-*.json"))

        if not json_files:
            raise FileNotFoundError(f"No metrics JSON file found in {self.test_results_dir}")

        # Sort by modification time (most recent first)
        json_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        metrics_file = json_files[0]  # Use most recent
        print(f"  Found: {metrics_file}")

        if len(json_files) > 1:
            print(f"  Note: Multiple metrics files found, using most recent")

        with open(metrics_file, 'r') as f:
            self.test_data = json.load(f)

        # Validate structure
        if 'iterations_results' not in self.test_data:
            raise ValueError("Invalid test data: missing 'iterations_results'")

        if not self.test_data['iterations_results']:
            raise ValueError("Test data is empty")

        print(f"  Loaded {len(self.test_data['iterations_results'])} test results")

    def load_log_summary(self):
        """Load log monitoring summary."""
        print("Loading log monitoring summary...")

        summary_file = self.logs_dir / "MONITORING_SUMMARY.md"

        if not summary_file.exists():
            print("  Warning: No monitoring summary found, using empty summary")
            self.log_summary = {
                'typeerrors_detected': 0,
                'timestamps_logged': 0,
                'errors_logged': 0,
                'warnings_logged': 0,
                'duration_seconds': 0
            }
            return

        # Parse Markdown to extract key metrics
        with open(summary_file, 'r') as f:
            content = f.read()

        self.log_summary = {}

        # Extract TypeErrors
        match = re.search(r'\*\*TypeErrors detected:\*\* (\d+)', content)
        self.log_summary['typeerrors_detected'] = int(match.group(1)) if match else 0

        # Extract Timestamps
        match = re.search(r'\*\*Timestamps logged:\*\* (\d+)', content)
        self.log_summary['timestamps_logged'] = int(match.group(1)) if match else 0

        # Extract Errors
        match = re.search(r'\*\*Errors logged:\*\* (\d+)', content)
        self.log_summary['errors_logged'] = int(match.group(1)) if match else 0

        # Extract Warnings
        match = re.search(r'\*\*Warnings logged:\*\* (\d+)', content)
        self.log_summary['warnings_logged'] = int(match.group(1)) if match else 0

        # Extract Duration
        match = re.search(r'\*\*Duration:\*\* (\d+) seconds', content)
        self.log_summary['duration_seconds'] = int(match.group(1)) if match else 0

        print(f"  TypeErrors: {self.log_summary['typeerrors_detected']}")
        print(f"  Timestamps: {self.log_summary['timestamps_logged']}")

    def generate_executive_summary(self):
        """Generate executive summary section."""
        stats = self.test_data.get('summary_statistics', {})

        total_tests = stats.get('total_tests', 0)
        passed_tests = stats.get('passed_tests', 0)
        failed_tests = stats.get('failed_tests', 0)
        success_rate = stats.get('success_rate', 0)
        timestamp_validation_rate = stats.get('timestamp_validation_rate', 0)
        typeerrors = self.log_summary.get('typeerrors_detected', 0)

        # Determine verdict
        if success_rate >= 95 and typeerrors == 0 and timestamp_validation_rate == 100:
            verdict = "✅ VALIDATION PASSED - System is stable and ready for production"
            verdict_status = "PASSED"
        elif success_rate >= 90 and typeerrors == 0:
            verdict = "⚠️ VALIDATION PASSED WITH WARNINGS - Review failures before production"
            verdict_status = "PASSED_WITH_WARNINGS"
        else:
            verdict = "❌ VALIDATION FAILED - Critical issues detected, do not deploy"
            verdict_status = "FAILED"

        section = f"""# E2E Validation Report - Final Results

**Generated:** {datetime.now().isoformat()}

## Executive Summary

### Final Verdict
{verdict}

### Key Metrics
- **Total Tests Executed:** {total_tests}
- **Tests Passed:** {passed_tests} ({success_rate:.1f}%)
- **Tests Failed:** {failed_tests} ({100 - success_rate:.1f}%)
- **Timestamp Validation Rate:** {timestamp_validation_rate:.1f}%
- **TypeErrors Detected:** {typeerrors}

### Validation Criteria
- ✓ Success Rate >= 95%: {"PASS" if success_rate >= 95 else "FAIL"}
- ✓ No TypeErrors: {"PASS" if typeerrors == 0 else "FAIL"}
- ✓ All Timestamps Valid: {"PASS" if timestamp_validation_rate == 100 else "FAIL"}
"""

        self.report_sections.append(section)

    def generate_test_results_section(self):
        """Generate test results by specialist section."""
        stats = self.test_data.get('summary_statistics', {})
        specialist_stats = stats.get('specialist_stats', {})

        section = """## Test Results by Specialist

| Specialist    | Total | Passed | Failed | Success Rate | Avg Latency | Min | Max | Median | Opinions |
|---------------|-------|--------|--------|--------------|-------------|-----|-----|--------|----------|
"""

        for specialist in ['business', 'technical', 'behavior', 'evolution', 'architecture']:
            if specialist in specialist_stats:
                sp = specialist_stats[specialist]
                opinion_total = sp.get('opinion_count_total', 0)
                opinion_avg = sp.get('opinion_count_avg', 0)
                section += f"| {specialist:<13} | {sp['total']:>5} | {sp['passed']:>6} | {sp['failed']:>6} | {sp['success_rate']:>11.1f}% | {sp['latency_avg']:>10.0f}ms | {sp['latency_min']:>3.0f} | {sp['latency_max']:>3.0f} | {sp['latency_median']:>6.0f} | {opinion_total} ({opinion_avg:.1f} avg) |\n"

        section += "\n### Opinion Metrics Summary\n\n"

        # Calculate total opinions
        total_opinions = sum(sp.get('opinion_count_total', 0) for sp in specialist_stats.values())
        total_tests = sum(sp.get('total', 0) for sp in specialist_stats.values())
        avg_opinions_per_test = total_opinions / total_tests if total_tests > 0 else 0

        section += f"- **Total Opinions Generated:** {total_opinions}\n"
        section += f"- **Average Opinions per Test:** {avg_opinions_per_test:.1f}\n"

        section += "\n"
        self.report_sections.append(section)

    def generate_timestamp_validation_section(self):
        """Generate timestamp validation section."""
        stats = self.test_data.get('summary_statistics', {})
        valid_timestamps = stats.get('valid_timestamps', 0)
        invalid_timestamps = stats.get('invalid_timestamps', 0)
        total_validations = valid_timestamps + invalid_timestamps
        validation_rate = (valid_timestamps / total_validations * 100) if total_validations > 0 else 0

        section = f"""## Timestamp Validation Results

### Summary
- **Total Timestamps Validated:** {total_validations}
- **Valid Timestamps:** {valid_timestamps} ({validation_rate:.1f}%)
- **Invalid Timestamps:** {invalid_timestamps} ({100 - validation_rate:.1f}%)

### Validation Checks
"""

        if validation_rate == 100:
            section += """- ✅ ISO 8601 Format: All passed
- ✅ Not Future: All passed
- ✅ Not Stale (>5 min): All passed
- ✅ Chronological Consistency: All passed
- ✅ evaluated_at <= response timestamp: All passed

✅ All timestamp validations passed successfully!
"""
        else:
            section += f"""- ⚠️ Some validation checks failed
- Valid: {valid_timestamps}
- Invalid: {invalid_timestamps}

### Issues Detected
Review test logs for specific timestamp validation errors.
"""

        section += "\n"
        self.report_sections.append(section)

    def generate_latency_analysis_section(self):
        """Generate latency analysis section."""
        stats = self.test_data.get('summary_statistics', {})
        lat = stats.get('latency_overall', {})

        mean = lat.get('mean', 0)
        median = lat.get('median', 0)
        stdev = lat.get('stdev', 0)
        min_lat = lat.get('min', 0)
        max_lat = lat.get('max', 0)
        p95 = lat.get('p95', 0)
        p99 = lat.get('p99', 0)

        section = f"""## Latency Analysis

### Overall Statistics
- **Mean:** {mean:.2f}ms
- **Median:** {median:.2f}ms
- **Std Dev:** {stdev:.2f}ms
- **Min:** {min_lat:.2f}ms
- **Max:** {max_lat:.2f}ms
- **P95:** {p95:.2f}ms
- **P99:** {p99:.2f}ms

### Performance Assessment
"""

        if mean < 1000:
            section += "✅ Excellent - Average latency under 1 second\n"
        elif mean < 2000:
            section += "⚠️ Good - Average latency under 2 seconds\n"
        else:
            section += "❌ Poor - Average latency exceeds 2 seconds\n"

        # Latency distribution
        all_latencies = [r['latency_ms'] for r in self.test_data['iterations_results'] if 'latency_ms' in r]

        if all_latencies:
            under_500 = sum(1 for l in all_latencies if l < 500)
            under_1000 = sum(1 for l in all_latencies if 500 <= l < 1000)
            under_2000 = sum(1 for l in all_latencies if 1000 <= l < 2000)
            over_2000 = sum(1 for l in all_latencies if l >= 2000)
            total = len(all_latencies)

            section += f"""
### Latency Distribution
- < 500ms: {under_500} ({under_500/total*100:.1f}%)
- 500-1000ms: {under_1000} ({under_1000/total*100:.1f}%)
- 1000-2000ms: {under_2000} ({under_2000/total*100:.1f}%)
- > 2000ms: {over_2000} ({over_2000/total*100:.1f}%)
"""

        section += "\n"
        self.report_sections.append(section)

    def generate_error_analysis_section(self):
        """Generate error analysis section."""
        errors = self.test_data.get('errors', [])

        section = """## Error Analysis

"""

        if not errors:
            section += "✅ No errors detected during validation!\n"
        else:
            # Group by type
            errors_by_type = defaultdict(list)
            for error in errors:
                error_type = error.get('error_type', 'Unknown')
                errors_by_type[error_type].append(error)

            # Group by specialist
            errors_by_specialist = defaultdict(list)
            for error in errors:
                scenario = error.get('scenario', '')
                specialist = scenario.split('-')[0] if '-' in scenario else scenario
                errors_by_specialist[specialist].append(error)

            section += f"""### Summary
- **Total Errors:** {len(errors)}
- **Unique Error Types:** {len(errors_by_type)}
- **Specialists Affected:** {len(errors_by_specialist)}

### Errors by Type
"""

            for error_type, error_list in errors_by_type.items():
                section += f"\n#### {error_type} ({len(error_list)} occurrences)\n"
                for error in error_list[:3]:  # Show first 3
                    section += f"- **Iteration {error['iteration_num']}**, Scenario: {error['scenario']}\n"
                    section += f"  - Message: {error['error_message']}\n"

            section += "\n### Errors by Specialist\n"
            for specialist, error_list in errors_by_specialist.items():
                section += f"- **{specialist}:** {len(error_list)} errors\n"

        section += "\n"
        self.report_sections.append(section)

    def generate_log_monitoring_section(self):
        """Generate log monitoring results section."""
        typeerrors = self.log_summary.get('typeerrors_detected', 0)
        timestamps = self.log_summary.get('timestamps_logged', 0)
        errors = self.log_summary.get('errors_logged', 0)
        warnings = self.log_summary.get('warnings_logged', 0)
        duration = self.log_summary.get('duration_seconds', 0)

        section = f"""## Log Monitoring Results

### Summary
- **Monitoring Duration:** {duration} seconds
- **TypeErrors Detected:** {typeerrors}
- **Errors Logged:** {errors}
- **Warnings Logged:** {warnings}
- **Timestamps Logged:** {timestamps}

### TypeError Analysis
"""

        if typeerrors > 0:
            section += f"""❌ **CRITICAL:** {typeerrors} TypeErrors detected during monitoring!

This indicates that the protobuf version incompatibility issue has NOT been fully resolved.

**Immediate Actions Required:**
1. Review logs in: `{self.logs_dir}/typeerror-alerts.log`
2. Verify protobuf versions in all components
3. Re-run protobuf version analysis: `./scripts/debug/run-full-version-analysis.sh`
4. Do NOT deploy to production
"""
        else:
            section += """✅ No TypeErrors detected during monitoring period!

This confirms that the protobuf version incompatibility issue has been successfully resolved.
"""

        section += f"""
### Detailed Logs
- Consensus Engine Logs: `{self.logs_dir}/consensus-engine-*-monitor.log`
- Specialist Logs: `{self.logs_dir}/specialist-*-monitor.log`
- TypeError Alerts: `{self.logs_dir}/typeerror-alerts.log`
- Monitoring Summary: `{self.logs_dir}/MONITORING_SUMMARY.md`

"""
        self.report_sections.append(section)

    def generate_recommendations_section(self):
        """Generate recommendations section."""
        stats = self.test_data.get('summary_statistics', {})
        success_rate = stats.get('success_rate', 0)
        timestamp_validation_rate = stats.get('timestamp_validation_rate', 0)
        typeerrors = self.log_summary.get('typeerrors_detected', 0)
        mean_latency = stats.get('latency_overall', {}).get('mean', 0)
        total_errors = stats.get('total_errors', 0)

        recommendations = []

        # Based on success rate
        if success_rate >= 95:
            recommendations.append("✅ System is stable - Ready for production deployment")
        elif success_rate >= 90:
            recommendations.append("⚠️ Review failures before production deployment")
        else:
            recommendations.append("❌ Do NOT deploy - Critical stability issues")

        # Based on TypeErrors
        if typeerrors > 0:
            recommendations.append("❌ CRITICAL: Resolve TypeError issues before deployment")
            recommendations.append("   - Re-run protobuf version analysis")
            recommendations.append("   - Verify all components are using compatible versions")
        else:
            recommendations.append("✅ No TypeErrors - Protobuf issue resolved")

        # Based on timestamps
        if timestamp_validation_rate < 100:
            recommendations.append("⚠️ Some timestamp validations failed - Investigate")
        else:
            recommendations.append("✅ All timestamps valid - Serialization working correctly")

        # Based on latency
        if mean_latency > 2000:
            recommendations.append("⚠️ High latency detected - Consider performance optimization")
        elif mean_latency > 1000:
            recommendations.append("ℹ️ Moderate latency - Monitor in production")
        else:
            recommendations.append("✅ Excellent latency - Performance is optimal")

        section = """## Recommendations

"""
        for rec in recommendations:
            section += f"{rec}\n"

        # Next steps
        all_passed = success_rate >= 95 and typeerrors == 0 and timestamp_validation_rate == 100

        section += "\n### Next Steps\n\n"

        if all_passed:
            section += """1. ✅ Update ANALISE_DEBUG_GRPC_TYPEERROR.md with final validation results
2. ✅ Close related tickets (GRPC-DEBUG-001, 002, 003)
3. ✅ Document resolution in project documentation
4. ✅ Proceed with production deployment
5. ✅ Monitor system for 48 hours post-deployment
"""
        else:
            section += """1. ❌ Review detailed error logs
2. ❌ Address identified issues
3. ❌ Re-run validation suite
4. ❌ Do NOT proceed with deployment until all issues resolved
"""

        section += "\n"
        self.report_sections.append(section)

    def generate_report(self) -> str:
        """Generate complete report."""
        print("\nGenerating validation report...")

        # Load data
        self.load_test_results()
        self.load_log_summary()

        # Generate all sections
        print("  - Executive summary")
        self.generate_executive_summary()

        print("  - Test results")
        self.generate_test_results_section()

        print("  - Timestamp validation")
        self.generate_timestamp_validation_section()

        print("  - Latency analysis")
        self.generate_latency_analysis_section()

        print("  - Error analysis")
        self.generate_error_analysis_section()

        print("  - Log monitoring")
        self.generate_log_monitoring_section()

        print("  - Recommendations")
        self.generate_recommendations_section()

        # Combine sections
        full_report = "\n\n".join(self.report_sections)

        # Add appendix
        metadata = self.test_data.get('metadata', {})
        num_iterations = metadata.get('num_iterations', 'N/A')
        gateway_url = metadata.get('gateway_url', 'N/A')

        appendix = f"""---

## Appendix

### Test Configuration
- Iterations: {num_iterations}
- Gateway URL: {gateway_url}
- Test Script: test-e2e-validation-complete.py
- Log Monitor: monitor-e2e-logs.sh

### File Locations
- Test Results: `{self.test_results_dir}`
- Logs: `{self.logs_dir}`
- This Report: `{self.output_path}`

### Related Documents
- [ANALISE_DEBUG_GRPC_TYPEERROR.md](../../ANALISE_DEBUG_GRPC_TYPEERROR.md)
- [PROTOBUF_VERSION_ANALYSIS.md](../../PROTOBUF_VERSION_ANALYSIS.md)
- [VALIDATION_CHECKLIST_PROTOBUF_FIX.md](../../VALIDATION_CHECKLIST_PROTOBUF_FIX.md)

---

**Report Generated:** {datetime.now().isoformat()}
"""

        full_report += appendix

        # Save report
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, 'w') as f:
            f.write(full_report)

        print(f"\n✓ Report generated: {self.output_path}")
        print(f"  Size: {self.output_path.stat().st_size / 1024:.1f} KB")

        return str(self.output_path)


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description='Generate E2E Validation Report')
    parser.add_argument('--test-results', required=True,
                       help='Directory with test results')
    parser.add_argument('--logs', required=True,
                       help='Directory with captured logs')
    parser.add_argument('--output', required=True,
                       help='Output path for report')

    args = parser.parse_args()

    # Validate arguments
    test_results_dir = Path(args.test_results)
    logs_dir = Path(args.logs)

    if not test_results_dir.exists():
        print(f"Error: Test results directory not found: {test_results_dir}")
        return 1

    if not logs_dir.exists():
        print(f"Error: Logs directory not found: {logs_dir}")
        return 1

    # Generate report
    try:
        generator = E2EReportGenerator(
            test_results_dir=str(test_results_dir),
            logs_dir=str(logs_dir),
            output_path=args.output
        )

        report_path = generator.generate_report()

        print(f"\n✓ Report generated successfully: {report_path}")
        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    except ValueError as e:
        print(f"Error: {e}")
        return 1

    except Exception as e:
        print(f"Error generating report: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
