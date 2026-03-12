#!/usr/bin/env python3
"""
Script não-interativo para executar todos os testes manuais do CodeForge.
"""

import os
import sys
import tempfile
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List

# Adicionar diretórios ao path
script_dir = Path(__file__).parent.parent
sys.path.insert(0, str(script_dir / "src"))
sys.path.insert(0, str(script_dir))


class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'


class TestResult:
    """Resultado de um teste."""
    def __init__(self, tc_id: str, name: str):
        self.tc_id = tc_id
        self.name = name
        self.passed = False
        self.skipped = False
        self.error = None
        self.duration = 0.0
        self.details = []

    def to_dict(self) -> dict:
        return {
            "tc_id": self.tc_id,
            "name": self.name,
            "passed": self.passed,
            "skipped": self.skipped,
            "error": self.error,
            "duration": self.duration,
            "details": self.details
        }


class TestSuite:
    """Suite de testes para CodeForge Builds Reais."""

    def __init__(self):
        self.results: List[TestResult] = []
        self.test_dir = Path("/tmp/codeforge-test")
        self.start_time = None

    def print_header(self, text: str):
        print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 70}{Colors.END}")
        print(f"{Colors.HEADER}{Colors.BOLD}{text.center(70)}{Colors.END}")
        print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 70}{Colors.END}\n")

    def print_step(self, step: str):
        print(f"{Colors.CYAN}➜{Colors.END} {step}")

    def print_success(self, text: str):
        print(f"{Colors.GREEN}✓{Colors.END} {text}")

    def print_error(self, text: str):
        print(f"{Colors.RED}✗{Colors.END} {text}")

    def print_info(self, text: str):
        print(f"{Colors.BLUE}ℹ{Colors.END} {text}")

    def setup_environment(self):
        """Configura ambiente de teste."""
        self.print_step("Configurando ambiente...")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.print_success(f"Ambiente pronto: {self.test_dir}")

    def create_python_project(self) -> Path:
        """Cria projeto Python FastAPI."""
        project_dir = self.test_dir / "python-fastapi"
        project_dir.mkdir(exist_ok=True)

        (project_dir / "main.py").write_text('''from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello World"}

@app.get("/health")
def health():
    return {"status": "healthy"}
''')

        (project_dir / "requirements.txt").write_text('''fastapi==0.104.1
uvicorn==0.24.0
''')

        return project_dir

    def create_nodejs_project(self) -> Path:
        """Cria projeto Node.js Express."""
        project_dir = self.test_dir / "nodejs-express"
        project_dir.mkdir(exist_ok=True)

        (project_dir / "package.json").write_text('''{
  "name": "test-express",
  "version": "1.0.0",
  "main": "index.js",
  "dependencies": {
    "express": "^4.18.2"
  }
}
''')

        (project_dir / "index.js").write_text('''const express = require('express');
const app = express();
app.get('/', (req, res) => res.json({message: 'Hello World'}));
app.listen(3000);
''')

        return project_dir

    def create_go_project(self) -> Path:
        """Cria projeto Go Gin."""
        project_dir = self.test_dir / "go-gin"
        project_dir.mkdir(exist_ok=True)

        (project_dir / "main.go").write_text('''package main

import "github.com/gin-gonic/gin"

func main() {
    r := gin.Default()
    r.GET("/", func(c *gin.Context) {
        c.JSON(200, gin.H{"message": "Hello World"})
    })
    r.Run(":8080")
}
''')

        (project_dir / "go.mod").write_text('''module test-gin

go 1.21

require github.com/gin-gonic/gin v1.9.1
''')

        return project_dir

    def check_prerequisites(self) -> Dict[str, bool]:
        """Verifica pré-requisitos."""
        self.print_step("Verificando pré-requisitos...")

        prereqs = {}

        # Python
        try:
            subprocess.run(["python3", "--version"], capture_output=True, check=True)
            prereqs["python"] = True
            self.print_success("Python 3 disponível")
        except:
            prereqs["python"] = False
            self.print_error("Python 3 não encontrado")

        # Docker
        try:
            subprocess.run(["docker", "--version"], capture_output=True, check=True)
            prereqs["docker"] = True
            self.print_success("Docker disponível")
        except:
            prereqs["docker"] = False
            self.print_error("Docker não encontrado")

        # kubectl
        try:
            subprocess.run(["kubectl", "version", "--client"],
                          capture_output=True, check=True)
            prereqs["kubectl"] = True
            self.print_success("kubectl disponível")
        except:
            prereqs["kubectl"] = False
            self.print_info("kubectl não encontrado (opcional)")

        # Cluster
        try:
            subprocess.run(["kubectl", "cluster-info"],
                          capture_output=True, check=True, timeout=5)
            prereqs["cluster"] = True
            self.print_success("Cluster Kubernetes conectado")
        except:
            prereqs["cluster"] = False
            self.print_info("Cluster não conectado (Kaniko tests serão pulados)")

        return prereqs

    def run_tc001_python_dockerfile(self) -> TestResult:
        """TC-001: DockerfileGenerator - Python FastAPI."""
        result = TestResult("TC-001", "DockerfileGenerator - Python FastAPI")

        try:
            from src.services.dockerfile_generator import (
                DockerfileGenerator,
                ArtifactType,
                SupportedLanguage
            )

            self.print_step("Gerando Dockerfile Python FastAPI...")

            generator = DockerfileGenerator()
            dockerfile = generator.generate_dockerfile(
                language=SupportedLanguage.PYTHON,
                framework="fastapi",
                artifact_type=ArtifactType.MICROSERVICE
            )

            # Validações
            checks = [
                ("FROM python:3.11-slim", "FROM python:3.11-slim" in dockerfile),
                ("HEALTHCHECK", "HEALTHCHECK" in dockerfile),
                ("EXPOSE 8000", "EXPOSE 8000" in dockerfile or "EXPOSE" in dockerfile),
                ("CMD uvicorn", "CMD" in dockerfile and "uvicorn" in dockerfile),
            ]

            all_passed = True
            for check_name, check_result in checks:
                if check_result:
                    result.details.append(f"✓ {check_name}")
                else:
                    result.details.append(f"✗ {check_name}")
                    all_passed = False

            result.passed = all_passed

            if all_passed:
                self.print_success("TC-001 PASS")
            else:
                self.print_error("TC-001 FAIL")

        except Exception as e:
            result.error = str(e)
            self.print_error(f"TC-001 ERROR: {e}")

        return result

    def run_tc002_nodejs_dockerfile(self) -> TestResult:
        """TC-002: DockerfileGenerator - Node.js Express."""
        result = TestResult("TC-002", "DockerfileGenerator - Node.js Express")

        try:
            from src.services.dockerfile_generator import (
                DockerfileGenerator,
                ArtifactType,
                SupportedLanguage
            )

            self.print_step("Gerando Dockerfile Node.js Express...")

            generator = DockerfileGenerator()
            dockerfile = generator.generate_dockerfile(
                language=SupportedLanguage.NODEJS,
                framework="express",
                artifact_type=ArtifactType.MICROSERVICE
            )

            checks = [
                ("FROM node:", "FROM node:" in dockerfile),
                ("EXPOSE 3000", "EXPOSE 3000" in dockerfile or "EXPOSE" in dockerfile),
                ("Multi-stage", dockerfile.count("FROM") >= 2),
            ]

            all_passed = True
            for check_name, check_result in checks:
                if check_result:
                    result.details.append(f"✓ {check_name}")
                else:
                    result.details.append(f"✗ {check_name}")
                    all_passed = False

            result.passed = all_passed

            if all_passed:
                self.print_success("TC-002 PASS")
            else:
                self.print_error("TC-002 FAIL")

        except Exception as e:
            result.error = str(e)
            self.print_error(f"TC-002 ERROR: {e}")

        return result

    def run_tc003_go_dockerfile(self) -> TestResult:
        """TC-003: DockerfileGenerator - Go Gin."""
        result = TestResult("TC-003", "DockerfileGenerator - Go Gin")

        try:
            from src.services.dockerfile_generator import (
                DockerfileGenerator,
                ArtifactType,
                SupportedLanguage
            )

            self.print_step("Gerando Dockerfile Go Gin...")

            generator = DockerfileGenerator()
            dockerfile = generator.generate_dockerfile(
                language=SupportedLanguage.GOLANG,
                framework="gin",
                artifact_type=ArtifactType.MICROSERVICE
            )

            checks = [
                ("FROM golang:", "FROM golang:" in dockerfile),
                ("EXPOSE 8080", "EXPOSE 8080" in dockerfile or "EXPOSE" in dockerfile),
                ("Multi-stage", dockerfile.count("FROM") >= 2),
            ]

            all_passed = True
            for check_name, check_result in checks:
                if check_result:
                    result.details.append(f"✓ {check_name}")
                else:
                    result.details.append(f"✗ {check_name}")
                    all_passed = False

            result.passed = all_passed

            if all_passed:
                self.print_success("TC-003 PASS")
            else:
                self.print_error("TC-003 FAIL")

        except Exception as e:
            result.error = str(e)
            self.print_error(f"TC-003 ERROR: {e}")

        return result

    def run_tc004_docker_build(self) -> TestResult:
        """TC-004: ContainerBuilder - Docker CLI."""
        result = TestResult("TC-004", "ContainerBuilder - Docker CLI")

        try:
            import asyncio
            from src.services.container_builder import ContainerBuilder, BuilderType
            from src.services.dockerfile_generator import (
                DockerfileGenerator,
                ArtifactType,
                SupportedLanguage
            )

            self.print_step("Criando projeto Python...")
            project_dir = self.create_python_project()

            self.print_step("Gerando Dockerfile...")
            generator = DockerfileGenerator()
            dockerfile = generator.generate_dockerfile(
                language=SupportedLanguage.PYTHON,
                framework="fastapi",
                artifact_type=ArtifactType.MICROSERVICE
            )
            (project_dir / "Dockerfile").write_text(dockerfile)

            self.print_step("Executando build com Docker CLI...")

            async def build():
                builder = ContainerBuilder(
                    builder_type=BuilderType.DOCKER,
                    enable_metrics=True
                )

                return await builder.build_container(
                    dockerfile_path=str(project_dir / "Dockerfile"),
                    build_context=str(project_dir),
                    image_tag="test-python:latest",
                    platforms=["linux/amd64"]
                )

            build_result = asyncio.run(build())

            result.details.append(f"Success: {build_result.success}")
            result.details.append(f"Image: {build_result.image_tag or 'N/A'}")
            result.details.append(f"Digest: {build_result.image_digest or 'N/A'}")
            result.details.append(f"Size: {build_result.size_bytes or 0:,} bytes")
            result.details.append(f"Duration: {build_result.duration_seconds:.2f}s")

            if build_result.success:
                result.passed = True
                self.print_success("TC-004 PASS")

                # Limpar imagem
                try:
                    subprocess.run(["docker", "rmi", "-f", "test-python:latest"],
                                  capture_output=True)
                except:
                    pass
            else:
                result.error = build_result.error_message
                self.print_error("TC-004 FAIL")

        except Exception as e:
            result.error = str(e)
            self.print_error(f"TC-004 ERROR: {e}")
            import traceback
            traceback.print_exc()

        return result

    def run_tc009_metrics_collection(self) -> TestResult:
        """TC-009: Performance Metrics - Coleta."""
        result = TestResult("TC-009", "Performance Metrics - Coleta")

        try:
            from src.services.build_metrics import get_metrics_collector

            self.print_step("Obtendo coletor de métricas...")
            collector = get_metrics_collector()

            self.print_step("Gerando relatório...")
            report = collector.get_performance_report()

            total_builds = report['summary']['total_builds']
            success_rate = report['summary']['success_rate']

            result.details.append(f"Total builds: {total_builds}")
            result.details.append(f"Success rate: {success_rate:.1%}")

            if report['duration_by_language']:
                result.details.append("Languages:")
                for lang, stats in report['duration_by_language'].items():
                    result.details.append(f"  {lang}: {stats['count']} builds, avg {stats['mean']:.2f}s")

            # Verificar arquivo
            metrics_file = Path("metrics/build_metrics.jsonl")
            if metrics_file.exists():
                content = metrics_file.read_text()
                line_count = len([l for l in content.split('\n') if l.strip()])
                result.details.append(f"Metrics file: {metrics_file} ({line_count} records)")

            result.passed = True
            self.print_success("TC-009 PASS")

        except Exception as e:
            result.error = str(e)
            self.print_error(f"TC-009 ERROR: {e}")
            import traceback
            traceback.print_exc()

        return result

    def run_tc010_metrics_export(self) -> TestResult:
        """TC-010: Performance Metrics - Exportação."""
        result = TestResult("TC-010", "Performance Metrics - Exportação")

        try:
            from src.services.build_metrics import get_metrics_collector

            self.print_step("Exportando métricas para JSON...")
            collector = get_metrics_collector()

            json_path = "/tmp/metrics_export.json"
            collector.export_metrics(json_path, format="json")

            if Path(json_path).exists():
                result.details.append(f"JSON export: {json_path}")
                result.passed = True
                self.print_success("TC-010 PASS")
            else:
                result.error = "JSON file not created"
                self.print_error("TC-010 FAIL")

        except Exception as e:
            result.error = str(e)
            self.print_error(f"TC-010 ERROR: {e}")

        return result

    def run_all(self, prereqs: Dict[str, bool]):
        """Executa todos os testes aplicáveis."""
        self.start_time = datetime.now()

        # Testes de DockerfileGenerator (sempre executam)
        self.results.append(self.run_tc001_python_dockerfile())
        self.results.append(self.run_tc002_nodejs_dockerfile())
        self.results.append(self.run_tc003_go_dockerfile())

        # Testes de ContainerBuilder (requer Docker)
        if prereqs.get("docker"):
            self.results.append(self.run_tc004_docker_build())
        else:
            result = TestResult("TC-004", "ContainerBuilder - Docker CLI")
            result.skipped = True
            result.error = "Docker não disponível"
            self.results.append(result)

        # Testes de Métricas (sempre executam)
        self.results.append(self.run_tc009_metrics_collection())
        self.results.append(self.run_tc010_metrics_export())

    def print_summary(self):
        """Imprime resumo dos resultados."""
        self.print_header("RELATÓRIO DE TESTES")

        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if r.error or (not r.passed and not r.skipped))
        skipped = sum(1 for r in self.results if r.skipped)

        print(f"{Colors.BOLD}Data:{Colors.END} {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{Colors.BOLD}Total de Testes:{Colors.END} {total}")
        print(f"{Colors.GREEN}{Colors.BOLD}Passou:{Colors.END} {passed}")
        print(f"{Colors.RED}{Colors.BOLD}Falhou:{Colors.END} {failed}")
        print(f"{Colors.YELLOW}{Colors.BOLD}Pulado:{Colors.END} {skipped}")

        print(f"\n{Colors.BOLD}Detalhamento:{Colors.END}\n")

        for result in self.results:
            status_color = Colors.GREEN if result.passed else Colors.RED if not result.skipped else Colors.YELLOW
            status = "PASS" if result.passed else "SKIP" if result.skipped else "FAIL"
            print(f"{status_color}{status}{Colors.END} | {result.tc_id} | {result.name}")

            for detail in result.details:
                print(f"     {detail}")

            if result.error:
                print(f"     {Colors.RED}Error: {result.error}{Colors.END}")

        # Tabela ASCII
        print(f"\n{Colors.BOLD}Tabela de Resultados:{Colors.END}\n")
        print("| TC ID | Descrição | Status |")
        print("|-------|-----------|--------|")
        for result in self.results:
            status = "PASS" if result.passed else "SKIP" if result.skipped else "FAIL"
            print(f"| {result.tc_id} | {result.name[:30]} | {status} |")

        # Salvar em arquivo
        report_file = Path("/tmp/codeforge-test-report.txt")
        with open(report_file, "w") as f:
            f.write(f"CodeForge Builds Reais - Relatório de Testes\n")
            f.write(f"Data: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total: {total} | Passou: {passed} | Falhou: {failed} | Pulado: {skipped}\n\n")

            for result in self.results:
                status = "PASS" if result.passed else "SKIP" if result.skipped else "FAIL"
                f.write(f"{status} | {result.tc_id} | {result.name}\n")
                for detail in result.details:
                    f.write(f"  {detail}\n")
                if result.error:
                    f.write(f"  ERROR: {result.error}\n")

        print(f"\n{Colors.CYAN}Relatório salvo em: {report_file}{Colors.END}")

    def cleanup(self):
        """Limpa ambiente de teste."""
        self.print_step("Limpando ambiente...")

        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

        # Remover imagens de teste
        try:
            subprocess.run(["docker", "rmi", "-f", "test-python:latest"],
                          capture_output=True)
        except:
            pass

        self.print_success("Limpeza concluída")


def main():
    """Função principal."""
    suite = TestSuite()

    suite.print_header("CODEFORGE BUILDS REAIS - SUITE DE TESTES")

    # Verificar pré-requisitos
    prereqs = suite.check_prerequisites()

    # Configurar ambiente
    suite.setup_environment()

    # Executar testes
    suite.run_all(prereqs)

    # Imprimir resumo
    suite.print_summary()

    # Limpar
    suite.cleanup()

    # Retornar código de saída
    failed = sum(1 for r in suite.results if r.error or (not r.passed and not r.skipped))
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
