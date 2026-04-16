#!/usr/bin/env python3
"""
Python security scan script for Neural Hive Mind.

Runs Bandit for Python security analysis and generates reports.
Requires: bandit, safety (optional)
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


class SecurityScanner:
    """Security scanner for Python services."""

    def __init__(self, project_root: Path, output_dir: Path = None):
        """Initialize scanner."""
        self.project_root = project_root
        self.output_dir = output_dir or project_root / "security-scans"
        self.output_dir.mkdir(exist_ok=True)

        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Fluxo G services to scan
        self.services = [
            "requirements-engineering",
            "documentation-generation",
            "knowledge-graph-rag",
            "approval-gateway",
            "service-registry",
            "orchestrator-dynamic",
        ]

        self.results = {
            "timestamp": self.timestamp,
            "services": {},
            "summary": {
                "total_services": len(self.services),
                "total_issues": 0,
                "severity_counts": {
                    "LOW": 0,
                    "MEDIUM": 0,
                    "HIGH": 0,
                }
            }
        }

    def run_bandit(self, service: str) -> dict:
        """Run Bandit security scan on a service."""
        service_path = self.project_root / "services" / service / "src"

        if not service_path.exists():
            return {"error": f"Service path {service_path} does not exist"}

        output_file = self.output_dir / f"{service}_bandit_{self.timestamp}.json"

        try:
            # Run bandit with JSON output
            result = subprocess.run(
                [
                    "bandit",
                    "-r", str(service_path),
                    "-f", "json",
                    "-o", str(output_file),
                    # Skip some noisy tests
                    "-skip", "B101,B601",
                ],
                capture_output=True,
                text=True,
            )

            # Parse JSON output
            if output_file.exists():
                with open(output_file) as f:
                    bandit_output = json.load(f)

                # Extract summary
                issues = bandit_output.get("results", [])
                metrics = bandit_output.get("metrics", {})

                severity_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
                for issue in issues:
                    severity = issue.get("issue_severity", "LOW")
                    if severity in severity_counts:
                        severity_counts[severity] += 1

                return {
                    "issues_count": len(issues),
                    "severity_counts": severity_counts,
                    "metrics": metrics,
                    "output_file": str(output_file),
                }
            else:
                return {"issues_count": 0, "severity_counts": {"LOW": 0, "MEDIUM": 0, "HIGH": 0}}

        except FileNotFoundError:
            return {"error": "Bandit not installed. Run: pip install bandit"}
        except Exception as e:
            return {"error": str(e)}

    def scan_service(self, service: str):
        """Scan a single service."""
        print(f"\n{'='*60}")
        print(f"Scanning {service}...")
        print('='*60)

        result = self.run_bandit(service)

        if "error" in result:
            print(f"  ❌ Error: {result['error']}")
            self.results["services"][service] = result
            return

        issues_count = result["issues_count"]
        severity_counts = result["severity_counts"]

        print(f"  Issues found: {issues_count}")
        print(f"    LOW: {severity_counts['LOW']}")
        print(f"    MEDIUM: {severity_counts['MEDIUM']}")
        print(f"    HIGH: {severity_counts['HIGH']}")

        if issues_count == 0:
            print(f"  ✅ No security issues found")
        else:
            print(f"  ⚠️  {issues_count} issue(s) found - see {result['output_file']}")

        self.results["services"][service] = result

        # Update summary
        self.results["summary"]["total_issues"] += issues_count
        for severity, count in severity_counts.items():
            self.results["summary"]["severity_counts"][severity] += count

    def scan_all(self):
        """Scan all services."""
        print(f"{'='*60}")
        print(f"Neural Hive Mind - Python Security Scan")
        print(f"Timestamp: {self.timestamp}")
        print(f"Output directory: {self.output_dir}")
        print('='*60)

        for service in self.services:
            self.scan_service(service)

        self.print_summary()

    def print_summary(self):
        """Print scan summary."""
        print(f"\n{'='*60}")
        print("SCAN SUMMARY")
        print('='*60)

        summary = self.results["summary"]
        print(f"Services scanned: {summary['total_services']}")
        print(f"Total issues: {summary['total_issues']}")
        print()
        print("By severity:")
        print(f"  HIGH: {summary['severity_counts']['HIGH']}")
        print(f"  MEDIUM: {summary['severity_counts']['MEDIUM']}")
        print(f"  LOW: {summary['severity_counts']['LOW']}")

        # Save full results
        results_file = self.output_dir / f"security_scan_results_{self.timestamp}.json"
        with open(results_file, "w") as f:
            json.dump(self.results, f, indent=2)

        print()
        print(f"Full results: {results_file}")

        # Exit code based on HIGH severity issues
        if summary['severity_counts']['HIGH'] > 0:
            print("\n❌ HIGH severity issues found!")
            sys.exit(1)
        else:
            print("\n✅ No HIGH severity issues found")

    def run_safety_check(self):
        """Run safety check for dependency vulnerabilities."""
        print(f"\n{'='*60}")
        print("Running Safety Check (Dependency Vulnerabilities)")
        print('='*60)

        requirements_files = list(self.project_root.glob("**/requirements.txt"))

        if not requirements_files:
            print("No requirements.txt files found")
            return

        for req_file in requirements_files:
            print(f"\nChecking {req_file.relative_to(self.project_root)}...")

            try:
                result = subprocess.run(
                    ["safety", "check", "--file", str(req_file), "--json"],
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0:
                    print(f"  ✅ No vulnerabilities found")
                else:
                    # Parse and display vulnerabilities
                    try:
                        vulns = json.loads(result.stdout)
                        print(f"  ⚠️  {len(vulns)} vulnerabilities found")
                    except:
                        print(f"  ⚠️  Vulnerabilities found")
            except FileNotFoundError:
                print("  (Safety not installed - skip)")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Python security scan for Neural Hive Mind"
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Project root directory (default: cwd)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory for reports (default: project-root/security-scans)"
    )
    parser.add_argument(
        "--safety",
        action="store_true",
        help="Run safety check for dependencies"
    )
    parser.add_argument(
        "--service",
        help="Scan only this service (e.g., requirements-engineering)"
    )

    args = parser.parse_args()

    scanner = SecurityScanner(args.project_root, args.output_dir)

    if args.service:
        scanner.scan_service(args.service)
    else:
        scanner.scan_all()

    if args.safety:
        scanner.run_safety_check()


if __name__ == "__main__":
    main()
