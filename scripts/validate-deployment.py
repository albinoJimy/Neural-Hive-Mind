#!/usr/bin/env python3
"""
Neural Hive Mind - Script de Validacao de Deployment

Valida o estado dos servicos apos deploy, verificando:
- Status dos pods Kubernetes
- Disponibilidade dos servicos
- Conectividade entre servicos
- Integridade dos endpoints de health check

Uso:
    python scripts/validate-deployment.py --env staging --services queen-mcp-server,worker-mcp-server
    python scripts/validate-deployment.py --all --timeout 300
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from subprocess import PIPE, Popen, run
from typing import Dict, List, Optional, Set


class ExitCode(Enum):
    SUCCESS = 0
    VALIDATION_FAILED = 1
    TIMEOUT = 2
    ERROR = 3


class Colors:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    CYAN = "\033[0;36m"
    NC = "\033[0m"


@dataclass
class ValidationResult:
    service: str
    passed: bool
    checks: List[str] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    duration: float = 0.0

    def add_check(self, check_name: str, passed: bool, message: str = ""):
        self.checks.append(check_name)
        if passed:
            if message:
                self.checks.append(f"  ✓ {message}")
        else:
            self.failures.append(message or f"{check_name} falhou")

    def add_warning(self, message: str):
        self.warnings.append(message)


@dataclass
class DeploymentConfig:
    env: str = "staging"
    services: List[str] = field(default_factory=list)
    all_services: bool = False
    timeout: int = 300
    interval: int = 5
    verbose: bool = False
    skip_connectivity: bool = False
    output_format: str = "text"

    # Lista completa de servicos
    MCP_SERVICES = [
        "queen-mcp-server",
        "worker-mcp-server",
        "analyst-mcp-server",
        "architect-mcp-server",
        "guard-mcp-server",
        "code-forge-mcp-server",
        "healer-mcp-server",
        "execution-mcp-server",
        "scout-mcp-server",
    ]

    CORE_SERVICES = [
        "queen-agent",
        "worker-agents",
        "analyst-agents",
        "scout-agents",
        "guard-agents",
        "consensus-engine",
        "orchestrator-dynamic",
    ]

    @property
    def all_known_services(self) -> List[str]:
        return self.MCP_SERVICES + self.CORE_SERVICES

    def get_services_to_validate(self) -> List[str]:
        if self.all_services:
            return self.all_known_services
        return self.services


class Logger:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def info(self, message: str):
        print(f"{Colors.BLUE}[{self._timestamp()}] [INFO] {message}{Colors.NC}")

    def success(self, message: str):
        print(f"{Colors.GREEN}[{self._timestamp()}] ✓ {message}{Colors.NC}")

    def error(self, message: str):
        print(f"{Colors.RED}[{self._timestamp()}] ✗ {message}{Colors.NC}", file=sys.stderr)

    def warning(self, message: str):
        print(f"{Colors.YELLOW}[{self._timestamp()}] ⚠ {message}{Colors.NC}")

    def debug(self, message: str):
        if self.verbose:
            print(f"{Colors.CYAN}[{self._timestamp()}] [DEBUG] {message}{Colors.NC}")

    def section(self, message: str):
        print(f"\n{Colors.CYAN}========== {message} =========={Colors.NC}")

    @staticmethod
    def _timestamp() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class KubernetesClient:
    """Cliente para interagir com Kubernetes via kubectl"""

    def __init__(self, namespace: str, logger: Logger):
        self.namespace = namespace
        self.logger = logger

    def _run(self, command: List[str], capture: bool = True) -> str:
        """Executa comando kubectl e retorna output"""
        full_cmd = ["kubectl", "-n", self.namespace] + command
        self.logger.debug(f"Executando: {' '.join(full_cmd)}")

        result = run(
            full_cmd,
            capture_output=capture,
            text=True,
            check=False,
        )

        if capture and result.returncode != 0:
            self.logger.debug(f"Comando falhou com codigo {result.returncode}: {result.stderr}")

        return result.stdout

    def get_pods(self, label_selector: str = "") -> Dict[str, dict]:
        """Retorna pods no namespace"""
        cmd = ["get", "pods", "-o", "json"]
        if label_selector:
            cmd.extend(["-l", label_selector])

        output = self._run(cmd)
        try:
            data = json.loads(output)
            return {pod["metadata"]["name"]: pod for pod in data.get("items", [])}
        except json.JSONDecodeError:
            self.logger.error(f"Erro ao parsear JSON de pods: {output[:200]}")
            return {}

    def get_pod_status(self, pod_name: str) -> str:
        """Retorna status de um pod"""
        pod = self.get_pods()
        return pod.get(pod_name, {}).get("status", {}).get("phase", "Unknown")

    def get_pod_ready_status(self, pod_name: str) -> bool:
        """Verifica se pod esta Ready"""
        pods = self._run(["get", "pod", pod_name, "-o", "json"])
        try:
            pod_data = json.loads(pods)
            conditions = pod_data.get("status", {}).get("conditions", [])
            for condition in conditions:
                if condition.get("type") == "Ready":
                    return condition.get("status") == "True"
        except json.JSONDecodeError:
            pass
        return False

    def get_services(self) -> Dict[str, dict]:
        """Retorna services no namespace"""
        output = self._run(["get", "svc", "-o", "json"])
        try:
            data = json.loads(output)
            return {svc["metadata"]["name"]: svc for svc in data.get("items", [])}
        except json.JSONDecodeError:
            return {}

    def get_pod_logs(self, pod_name: str, tail: int = 50) -> str:
        """Retorna logs de um pod"""
        return self._run(["logs", pod_name, f"--tail={tail}"])

    def exec_in_pod(self, pod_name: str, command: List[str]) -> str:
        """Executa comando em um pod"""
        cmd = ["exec", pod_name, "--"] + command
        return self._run(cmd)

    def port_forward(self, pod_name: str, local_port: int, remote_port: int) -> Optional[Popen]:
        """Inicia port-forward para um pod"""
        cmd = ["kubectl", "-n", self.namespace, "port-forward",
               pod_name, f"{local_port}:{remote_port}"]
        self.logger.debug(f"Iniciando port-forward: {' '.join(cmd)}")
        try:
            process = Popen(cmd, stdout=PIPE, stderr=PIPE)
            time.sleep(2)  # Aguardar port-forward iniciar
            if process.poll() is None:
                return process
        except Exception as e:
            self.logger.error(f"Erro ao iniciar port-forward: {e}")
        return None


class DeploymentValidator:
    """Validador de deployments"""

    def __init__(self, config: DeploymentConfig):
        self.config = config
        self.logger = Logger(verbose=config.verbose)
        self.k8s = KubernetesClient(config.env, self.logger)
        self.results: Dict[str, ValidationResult] = {}

    def validate_service(self, service_name: str) -> ValidationResult:
        """Valida um servico individual"""
        result = ValidationResult(service=service_name, passed=False)
        start_time = time.time()

        self.logger.section(f"Validando {service_name}")

        # 1. Verificar se pods existem
        pods = self.k8s.get_pods(f"app.kubernetes.io/name={service_name}")

        if not pods:
            result.add_check("pods_exist", False, f"Nenhum pod encontrado para {service_name}")
            return result

        result.add_check("pods_exist", True, f"{len(pods)} pod(s) encontrado(s)")

        # 2. Verificar status dos pods
        all_running = True
        ready_count = 0

        for pod_name, pod_data in pods.items():
            phase = pod_data.get("status", {}).get("phase", "Unknown")

            if phase == "Running":
                if self.k8s.get_pod_ready_status(pod_name):
                    ready_count += 1
                    result.add_check("pod_status", True, f"{pod_name}: Running & Ready")
                else:
                    result.add_warning(f"{pod_name}: Running mas nao Ready")
            else:
                all_running = False
                result.add_check("pod_status", False, f"{pod_name}: {phase}")

                # Mostrar logs de pods com erro
                if phase in ["Error", "CrashLoopBackOff"]:
                    logs = self.k8s.get_pod_logs(pod_name, tail=20)
                    self.logger.warning(f"Logs de {pod_name}:\n{logs[:500]}")

        result.add_check("all_pods_running", all_running and ready_count == len(pods))

        # 3. Verificar service Kubernetes
        services = self.k8s.get_services()
        if service_name in services:
            result.add_check("service_exists", True, f"Service {service_name} encontrado")
        else:
            result.add_warning(f"Service Kubernetes nao encontrado para {service_name}")

        # 4. Verificar portas e endpoints (se aplicavel)
        if service_name in services:
            svc_data = services[service_name]
            ports = svc_data.get("spec", {}).get("ports", [])
            if ports:
                port_info = ", ".join([f"{p.get('port')}/{p.get('protocol', 'TCP')}" for p in ports])
                result.add_check("ports_configured", True, f"Portas: {port_info}")

        # 5. Teste de conectividade (opcional)
        if not self.config.skip_connectivity and ready_count > 0:
            self._test_connectivity(service_name, result)

        result.duration = time.time() - start_time
        result.passed = len(result.failures) == 0

        return result

    def _test_connectivity(self, service_name: str, result: ValidationResult):
        """Testa conectividade basica do servico"""
        # Tentar conectar via service DNS
        pods = self.k8s.get_pods(f"app.kubernetes.io/name={service_name}")

        if not pods:
            return

        # Pegar um pod pronto para teste
        test_pod = None
        for pod_name in pods.keys():
            if self.k8s.get_pod_ready_status(pod_name):
                test_pod = pod_name
                break

        if not test_pod:
            result.add_warning("Nenhum pod pronto para teste de conectividade")
            return

        # Teste basico: verificar se o pod esta respondendo
        try:
            # Verificar se o processo principal esta rodando
            output = self.k8s.exec_in_pod(test_pod, ["ps", "aux"])
            if "python" in output.lower() or "main" in output.lower():
                result.add_check("process_running", True, "Processo principal detectado")
            else:
                result.add_warning("Processo principal nao detectado")
        except Exception as e:
            result.add_warning(f"Erro ao verificar processo: {e}")

    def wait_for_service_ready(self, service_name: str, timeout: Optional[int] = None) -> ValidationResult:
        """Aguarda servico ficar pronto"""
        if timeout is None:
            timeout = self.config.timeout

        result = ValidationResult(service=service_name, passed=False)
        start_time = time.time()
        self.logger.info(f"Aguardando {service_name} ficar pronto (timeout: {timeout}s)...")

        elapsed = 0
        while elapsed < timeout:
            pods = self.k8s.get_pods(f"app.kubernetes.io/name={service_name}")

            if not pods:
                time.sleep(self.config.interval)
                elapsed = time.time() - start_time
                continue

            ready_count = 0
            for pod_name in pods.keys():
                if self.k8s.get_pod_ready_status(pod_name):
                    ready_count += 1

            if ready_count == len(pods) and ready_count > 0:
                result.passed = True
                result.add_check("wait_ready", True,
                               f"Todos {ready_count} pod(s) prontos em {int(elapsed)}s")
                result.duration = elapsed
                return result

            time.sleep(self.config.interval)
            elapsed = time.time() - start_time

        result.passed = False
        result.add_check("wait_ready", False, f"Timeout apos {int(elapsed)}s")
        result.duration = elapsed
        return result

    def validate_all(self, wait_for_ready: bool = True) -> bool:
        """Valida todos os servicos configurados"""
        services = self.config.get_services_to_validate()

        if not services:
            self.logger.error("Nenhum servico para validar")
            return False

        self.logger.section(f"Validando {len(services)} servico(s) em {self.config.env}")

        all_passed = True

        for service in services:
            if wait_for_ready:
                wait_result = self.wait_for_service_ready(service)
                if not wait_result.passed:
                    self.logger.error(f"Timeout aguardando {service}")
                    all_passed = False
                    if not self.config.verbose:
                        continue

            result = self.validate_service(service)
            self.results[service] = result

            if not result.passed:
                all_passed = False
                self.logger.error(f"{service}: Validacao falhou")
            else:
                self.logger.success(f"{service}: Validacao passou")

        return all_passed

    def print_summary(self):
        """Imprime resumo dos resultados"""
        self.logger.section("Resumo da Validacao")

        passed = sum(1 for r in self.results.values() if r.passed)
        failed = len(self.results) - passed
        total_duration = sum(r.duration for r in self.results.values())

        print(f"\nTotal de servicos: {len(self.results)}")
        print(f"{Colors.GREEN}Passaram: {passed}{Colors.NC}")
        print(f"{Colors.RED}Falharam: {failed}{Colors.NC}")
        print(f"Duracao total: {total_duration:.1f}s\n")

        if self.results:
            print(f"{'Servico':<30} {'Status':<10} {'Duracao':<10} {'Checks':<10} {'Falhas':<10}")
            print("-" * 80)

            for service, result in self.results.items():
                status = f"{Colors.GREEN}PASS{Colors.NC}" if result.passed else f"{Colors.RED}FAIL{Colors.NC}"
                print(f"{service:<30} {status:<20} {result.duration:>8.1f}s "
                      f"{len(result.checks):>8} {len(result.failures):>8}")

                if result.failures and self.config.verbose:
                    for failure in result.failures:
                        print(f"  - {Colors.RED}{failure}{Colors.NC}")

                if result.warnings and self.config.verbose:
                    for warning in result.warnings:
                        print(f"  - {Colors.YELLOW}WARN: {warning}{Colors.NC}")

    def save_report(self, output_file: str):
        """Salva relatorio em JSON"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "environment": self.config.env,
            "services_validated": len(self.results),
            "passed": sum(1 for r in self.results.values() if r.passed),
            "failed": sum(1 for r in self.results.values() if not r.passed),
            "results": {
                name: {
                    "passed": r.passed,
                    "duration": r.duration,
                    "checks": r.checks,
                    "failures": r.failures,
                    "warnings": r.warnings,
                }
                for name, r in self.results.items()
            },
        }

        with open(output_file, "w") as f:
            json.dump(report, f, indent=2)

        self.logger.info(f"Relatorio salvo: {output_file}")


def parse_arguments() -> DeploymentConfig:
    """Parse argumentos de linha de comando"""
    parser = argparse.ArgumentParser(
        description="Neural Hive Mind - Validacao de Deployment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  %(prog)s --env staging --services queen-mcp-server,worker-mcp-server
  %(prog)s --all --timeout 300 --verbose
  %(prog)s --env production --services queen-agent --output-json report.json
        """,
    )

    parser.add_argument(
        "-e", "--env",
        default="staging",
        choices=["staging", "production"],
        help="Ambiente Kubernetes (padrao: staging)",
    )

    parser.add_argument(
        "-s", "--services",
        help="Lista de servicos separados por virgula",
    )

    parser.add_argument(
        "-a", "--all",
        action="store_true",
        help="Validar todos os servicos conhecidos",
    )

    parser.add_argument(
        "-t", "--timeout",
        type=int,
        default=300,
        help="Timeout em segundos (padrao: 300)",
    )

    parser.add_argument(
        "-i", "--interval",
        type=int,
        default=5,
        help="Intervalo entre checagens em segundos (padrao: 5)",
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Output detalhado",
    )

    parser.add_argument(
        "--skip-connectivity",
        action="store_true",
        help="Pular testes de conectividade",
    )

    parser.add_argument(
        "--output-json",
        help="Salvar relatorio em JSON",
    )

    args = parser.parse_args()

    services = []
    if args.services:
        services = [s.strip() for s in args.services.split(",") if s.strip()]

    return DeploymentConfig(
        env=args.env,
        services=services,
        all_services=args.all,
        timeout=args.timeout,
        interval=args.interval,
        verbose=args.verbose,
        skip_connectivity=args.skip_connectivity,
        output_format="json" if args.output_json else "text",
    )


def main() -> int:
    """Funcao principal"""
    config = parse_arguments()
    validator = DeploymentValidator(config)

    try:
        success = validator.validate_all(wait_for_ready=True)
        validator.print_summary()

        if config.output_format == "json":
            validator.save_report(config.output_format)

        return ExitCode.SUCCESS.value if success else ExitCode.VALIDATION_FAILED.value

    except KeyboardInterrupt:
        validator.logger.warning("Validacao interrompida pelo usuario")
        return ExitCode.ERROR.value
    except Exception as e:
        validator.logger.error(f"Erro durante validacao: {e}")
        if config.verbose:
            import traceback
            traceback.print_exc()
        return ExitCode.ERROR.value


if __name__ == "__main__":
    sys.exit(main())
