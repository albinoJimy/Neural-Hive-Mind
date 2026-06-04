"""
Script para executar testes de carga do Fluxo G com Locust.

Usage:
    python run_fluxo_g_load_test.py --users 100 --spawn-rate 10 --run-time 5m
    python run_fluxo_g_load_test.py --gui  # Web UI
"""

import argparse
import subprocess
import sys


def run_locust(
    users: int,
    spawn_rate: float,
    run_time: str,
    headless: bool = True,
    master: bool = False,
    worker: bool = False,
    master_host: str = None,
):
    """Executa teste de carga com Locust."""

    cmd = [
        "locust",
        "-f",
        "tests/load/fluxo_g_locustfile.py",
        "--users",
        str(users),
        "--spawn-rate",
        str(spawn_rate),
        "--run-time",
        run_time,
        "--html",
        "fluxo_g_load_test_report.html",
    ]

    if headless:
        cmd.append("--headless")

    if master:
        cmd.append("--master")
        cmd.extend(["--expect-workers", str(max(1, users // 100))])

    if worker:
        cmd.append("--worker")
        if master_host:
            cmd.extend(["--master-host", master_host])

    # Output configs
    cmd.extend(
        [
            "--logfile",
            "fluxo_g_locust.log",
            "--loglevel",
            "INFO",
        ]
    )

    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser(
        description="Run Fluxo G load tests with Locust",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic load test with 100 users
  python run_fluxo_g_load_test.py --users 100 --spawn-rate 10 --run-time 5m

  # Load test with web UI
  python run_fluxo_g_load_test.py --gui

  # Distributed load test (master)
  python run_fluxo_g_load_test.py --users 1000 --master

  # Worker node
  python run_fluxo_g_load_test.py --worker --master-host localhost

  # Stress test
  python run_fluxo_g_load_test.py --users 5000 --spawn-rate 500 --run-time 10m
        """,
    )
    parser.add_argument("--users", type=int, default=100, help="Number of users (default: 100)")
    parser.add_argument(
        "--spawn-rate", type=float, default=10, help="Users spawned per second (default: 10)"
    )
    parser.add_argument(
        "--run-time", default="5m", help="Test duration, e.g., 5m, 1h (default: 5m)"
    )
    parser.add_argument(
        "--gui", action="store_true", help="Run with web UI instead of headless mode"
    )
    parser.add_argument("--master", action="store_true", help="Run as master in distributed mode")
    parser.add_argument("--worker", action="store_true", help="Run as worker in distributed mode")
    parser.add_argument("--master-host", help="Master host for workers (default: localhost)")

    args = parser.parse_args()

    try:
        run_locust(
            users=args.users,
            spawn_rate=args.spawn_rate,
            run_time=args.run_time,
            headless=not args.gui,
            master=args.master,
            worker=args.worker,
            master_host=args.master_host,
        )
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(0)
    except subprocess.CalledProcessError as e:
        print(f"Error running locust: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
