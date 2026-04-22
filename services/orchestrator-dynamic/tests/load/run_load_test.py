#!/usr/bin/env python3
"""
Script para executar load tests do Fluxo G com Locust.

Uso:
    python run_load_test.py --headless --users 100 --run-time 5m
    python run_load_test.py --gui  # Para modo com interface web
"""

import argparse
import subprocess
import sys


def run_locust(
    host: str,
    users: int,
    spawn_rate: float,
    run_time: str,
    headless: bool = True,
    master: bool = False,
    worker: bool = False,
    master_host: str = None,
    html_report: str = None,
    users_file: str = None,
):
    """
    Executa teste de carga com Locust.

    Args:
        host: URL do servidor alvo
        users: Número de usuários simulados
        spawn_rate: Taxa de criação de usuários por segundo
        run_time: Duração do teste (ex: 5m, 1h, 30s)
        headless: Executar sem interface web
        master: Executar como master (modo distribuído)
        worker: Executar como worker (modo distribuído)
        master_host: Host do master (para workers)
        html_report: Caminho para salvar relatório HTML
        users_file: Arquivo com usuários customizados
    """
    cmd = [
        "locust",
        "-f",
        "tests/load/locustfile.py",
        "--host",
        host,
        "--users",
        str(users),
        "--spawn-rate",
        str(spawn_rate),
        "--run-time",
        run_time,
    ]

    if headless:
        cmd.append("--headless")

    if html_report:
        cmd.extend(["--html", html_report])

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
            "locust.log",
            "--loglevel",
            "INFO",
        ]
    )

    print(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, check=True)
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"Locust failed with exit code {e.returncode}")
        return e.returncode
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        return 130


def main():
    parser = argparse.ArgumentParser(
        description="Run Fluxo G Load Tests with Locust",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Teste simples com 100 usuários por 5 minutos
  python run_load_test.py --headless --users 100 --run-time 5m

  # Teste com interface web
  python run_load_test.py --gui

  # Teste pesado: 1000 usuários por 30 minutos
  python run_load_test.py --headless --users 1000 --run-time 30m

  # Modo distribuído (master + workers)
  # Terminal 1:
  python run_load_test.py --master --users 2000
  # Terminal 2+:
  python run_load_test.py --worker --master-host localhost
        """,
    )

    # Target configuration
    parser.add_argument(
        "--host",
        default="http://localhost:8003",
        help="Target host URL (default: http://localhost:8003)",
    )

    # Load test configuration
    parser.add_argument(
        "--users", "-u", type=int, default=100, help="Number of users to spawn (default: 100)"
    )
    parser.add_argument(
        "--spawn-rate", "-r", type=float, default=10, help="Users spawned per second (default: 10)"
    )
    parser.add_argument(
        "--run-time", "-t", default="5m", help="Test duration (default: 5m). Examples: 30s, 5m, 1h"
    )

    # Output options
    parser.add_argument("--gui", action="store_true", help="Run with web UI (default: headless)")
    parser.add_argument("--html", metavar="FILE", help="Generate HTML report at specified path")

    # Distributed mode
    parser.add_argument("--master", action="store_true", help="Run as master in distributed mode")
    parser.add_argument("--worker", action="store_true", help="Run as worker in distributed mode")
    parser.add_argument("--master-host", help="Master host for workers (default: localhost)")

    # Presets
    parser.add_argument(
        "--preset",
        choices=["smoke", "baseline", "stress", "soak"],
        help="Use preset configuration (overrides other options)",
    )

    args = parser.parse_args()

    # Apply presets
    if args.preset == "smoke":
        args.users = 10
        args.spawn_rate = 2
        args.run_time = "1m"
    elif args.preset == "baseline":
        args.users = 100
        args.spawn_rate = 10
        args.run_time = "5m"
    elif args.preset == "stress":
        args.users = 1000
        args.spawn_rate = 50
        args.run_time = "10m"
    elif args.preset == "soak":
        args.users = 200
        args.spawn_rate = 10
        args.run_time = "1h"

    # Run test
    exit_code = run_locust(
        host=args.host,
        users=args.users,
        spawn_rate=args.spawn_rate,
        run_time=args.run_time,
        headless=not args.gui,
        master=args.master,
        worker=args.worker,
        master_host=args.master_host,
        html_report=args.html,
    )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
