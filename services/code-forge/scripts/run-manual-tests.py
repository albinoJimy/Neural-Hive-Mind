#!/usr/bin/env python3
"""
Script auxiliar para execução dos testes manuais do CodeForge Builds Reais.

Este script facilita a execução dos casos de teste descritos no
PLANO_TESTE_MANUAL_CODEFORGE.md, fornecendo comandos prontos e
um ambiente de teste organizado.
"""

import os
import sys
import tempfile
import subprocess
import shutil
from pathlib import Path
from typing import Optional

# Adicionar src ao path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class Colors:
    """Cores para terminal."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str):
    """Imprime cabeçalho formatado."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 60}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(60)}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 60}{Colors.END}\n")


def print_step(step: str):
    """Imprime passo formatado."""
    print(f"{Colors.CYAN}➜{Colors.END} {step}")


def print_success(text: str):
    """Imprime sucesso."""
    print(f"{Colors.GREEN}✓{Colors.END} {text}")


def print_error(text: str):
    """Imprime erro."""
    print(f"{Colors.RED}✗{Colors.END} {text}")


def print_info(text: str):
    """Imprime informação."""
    print(f"{Colors.BLUE}ℹ{Colors.END} {text}")


def create_test_environment(base_dir: str = "/tmp/codeforge-test") -> Path:
    """Cria diretório de teste."""
    test_dir = Path(base_dir)
    test_dir.mkdir(parents=True, exist_ok=True)
    return test_dir


def setup_python_fastapi(test_dir: Path) -> Path:
    """Configura projeto Python FastAPI para teste."""
    project_dir = test_dir / "python-fastapi"
    project_dir.mkdir(exist_ok=True)

    # main.py
    (project_dir / "main.py").write_text('''from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello World"}

@app.get("/health")
def health():
    return {"status": "healthy"}
''')

    # requirements.txt
    (project_dir / "requirements.txt").write_text('''fastapi==0.104.1
uvicorn==0.24.0
''')

    print_success(f"Projeto Python criado em {project_dir}")
    return project_dir


def setup_nodejs_express(test_dir: Path) -> Path:
    """Configura projeto Node.js Express para teste."""
    project_dir = test_dir / "nodejs-express"
    project_dir.mkdir(exist_ok=True)

    # package.json
    (project_dir / "package.json").write_text('''{
  "name": "test-express",
  "version": "1.0.0",
  "main": "index.js",
  "dependencies": {
    "express": "^4.18.2"
  }
}
''')

    # index.js
    (project_dir / "index.js").write_text('''const express = require('express');
const app = express();
app.get('/', (req, res) => res.json({message: 'Hello World'}));
app.get('/health', (req, res) => res.json({status: 'healthy'}));
app.listen(3000);
''')

    print_success(f"Projeto Node.js criado em {project_dir}")
    return project_dir


def setup_go_gin(test_dir: Path) -> Path:
    """Configura projeto Go Gin para teste."""
    project_dir = test_dir / "go-gin"
    project_dir.mkdir(exist_ok=True)

    # main.go
    (project_dir / "main.go").write_text('''package main

import "github.com/gin-gonic/gin"

func main() {
    r := gin.Default()
    r.GET("/", func(c *gin.Context) {
        c.JSON(200, gin.H{"message": "Hello World"})
    })
    r.GET("/health", func(c *gin.Context) {
        c.JSON(200, gin.H{"status": "healthy"})
    })
    r.Run(":8080")
}
''')

    # go.mod
    (project_dir / "go.mod").write_text('''module test-gin

go 1.21

require github.com/gin-gonic/gin v1.9.1
''')

    print_success(f"Projeto Go criado em {project_dir}")
    return project_dir


def check_prerequisites() -> dict:
    """Verifica pré-requisitos."""
    print_header("VERIFICANDO PRÉ-REQUISITOS")

    results = {}

    # Python
    try:
        result = subprocess.run(
            ["python3", "--version"],
            capture_output=True, text=True
        )
        results["python"] = {
            "available": True,
            "version": result.stdout.strip(),
            "color": Colors.GREEN if result.returncode == 0 else Colors.RED
        }
    except FileNotFoundError:
        results["python"] = {"available": False, "color": Colors.RED}

    # Docker
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True, text=True
        )
        results["docker"] = {
            "available": True,
            "version": result.stdout.strip(),
            "color": Colors.GREEN if result.returncode == 0 else Colors.RED
        }
    except FileNotFoundError:
        results["docker"] = {"available": False, "color": Colors.RED}

    # kubectl
    try:
        result = subprocess.run(
            ["kubectl", "version", "--client", "--short"],
            capture_output=True, text=True
        )
        results["kubectl"] = {
            "available": True,
            "version": result.stdout.strip().split('\n')[0],
            "color": Colors.GREEN if result.returncode == 0 else Colors.RED
        }
    except FileNotFoundError:
        results["kubectl"] = {"available": False, "color": Colors.YELLOW}

    # Cluster connection
    try:
        result = subprocess.run(
            ["kubectl", "cluster-info"],
            capture_output=True, text=True, timeout=5
        )
        results["cluster"] = {
            "available": result.returncode == 0,
            "color": Colors.GREEN if result.returncode == 0 else Colors.RED
        }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        results["cluster"] = {"available": False, "color": Colors.YELLOW}

    # Imprimir resultados
    for name, info in results.items():
        status = "OK" if info.get("available", False) else "NOK"
        version = info.get("version", "")
        print(f"  {info['color']}{status.upper():<6}{Colors.END} {name.upper():<10} {version}")

    return results


def print_menu():
    """Imprime menu de testes."""
    print_header("CODEFORGE BUILDS REAIS - TESTE MANUAL")
    print(f"""
{Colors.BOLD}Selecione um caso de teste:{Colors.END}

  {Colors.GREEN}[BÁSICO]{Colors.END}
  1. TC-001: DockerfileGenerator - Python FastAPI
  2. TC-002: DockerfileGenerator - Node.js Express
  3. TC-003: DockerfileGenerator - Go Gin
  4. TC-004: ContainerBuilder - Docker CLI (Build Local)
  5. TC-005: ContainerBuilder - BuildKit Cache

  {Colors.YELLOW}[AVANÇADO]{Colors.END}
  6. TC-006: Multi-arch Build (Docker)
  7. TC-007: Kaniko Builder (Kubernetes)
  8. TC-008: Kaniko QEMU Multi-arch

  {Colors.CYAN}[MÉTRICAS]{Colors.END}
  9. TC-009: Performance Metrics - Coleta
  10. TC-010: Performance Metrics - Exportação

  {Colors.BLUE}[INTEGRAÇÃO]{Colors.END}
  11. TC-011: Pipeline Completo

  {Colors.BOLD}[UTILIDADES]{Colors.END}
  p - Verificar pré-requisitos
  e - Configurar ambiente de teste
  c - Limpar ambiente de teste
  m - Ver métricas coletadas
  h - Ajuda
  q - Sair

  {Colors.CYAN}Opção:{Colors.END} """, end="")


def print_help():
    """Imprime ajuda."""
    print_header("AJUDA - TESTE MANUAL")

    print(f"""
{Colors.BOLD}Fluxo Recomendado:{Colors.END}

  1. Execute {Colors.GREEN}'p'{Colors.END} para verificar pré-requisitos
  2. Execute {Colors.GREEN}'e'{Colors.END} para configurar ambiente
  3. Execute TC-001 para validar geração básica
  4. Execute TC-004 para validar build Docker
  5. Execute TC-007 para validar Kaniko (se cluster disponível)
  6. Execute TC-009 para verificar métricas

{Colors.BOLD}Documentação:{Colors.END}
  - Plano completo: docs/code-forge/PLANO_TESTE_MANUAL_CODEFORGE.md
  - Release notes: RELEASE_NOTES.md
  - Análise de completude: docs/code-forge/ANALISE_COMPLETUDE_V1.2.0.md

{Colors.BOLD}Diretórios:{Colors.END}
  - Ambiente de teste: /tmp/codeforge-test/
  - Métricas: metrics/build_metrics.jsonl
  - Logs: Ver logs durante execução dos testes
    """)


def run_tc001():
    """Executa TC-001: Python FastAPI DockerfileGenerator."""
    print_header("TC-001: DockerfileGenerator - Python FastAPI")

    test_dir = create_test_environment()
    project_dir = setup_python_fastapi(test_dir)

    print_step("Gerando Dockerfile com DockerfileGenerator...")

    try:
        from src.services.dockerfile_generator import (
            DockerfileGenerator,
            ArtifactType,
            PythonVersion
        )

        generator = DockerfileGenerator()
        dockerfile = generator.generate_python_dockerfile(
            python_version=PythonVersion.PYTHON_3_11_SLIM,
            artifact_type=ArtifactType.MICROSERVICE,
            framework="fastapi",
            port=8000,
            healthcheck_path="/health"
        )

        # Salvar Dockerfile
        dockerfile_path = project_dir / "Dockerfile"
        dockerfile_path.write_text(dockerfile)

        print_success("Dockerfile gerado com sucesso!")
        print_info(f"Local: {dockerfile_path}")

        # Verificar conteúdo
        print("\n--- Conteúdo do Dockerfile (primeiras 15 linhas) ---")
        for i, line in enumerate(dockerfile.split('\n')[:15], 1):
            print(f"{i:2d}: {line}")

        # Validar elementos
        checks = {
            "FROM python:3.11-slim": "FROM python:3.11-slim" in dockerfile,
            "HEALTHCHECK": "HEALTHCHECK" in dockerfile,
            "EXPOSE 8000": "EXPOSE 8000" in dockerfile,
            "CMD uvicorn": "CMD" in dockerfile and "uvicorn" in dockerfile,
        }

        print("\n--- Validações ---")
        for check, passed in checks.items():
            status = f"{Colors.GREEN}✓ PASS{Colors.END}" if passed else f"{Colors.RED}✗ FAIL{Colors.END}"
            print(f"  {status} {check}")

        all_passed = all(checks.values())
        if all_passed:
            print_success(f"\n{Colors.BOLD}TC-001: PASS{Colors.END}")
        else:
            print_error(f"\n{Colors.BOLD}TC-001: FAIL{Colors.END}")

        return all_passed

    except Exception as e:
        print_error(f"Erro ao executar teste: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_tc004():
    """Executa TC-004: ContainerBuilder Docker CLI."""
    print_header("TC-004: ContainerBuilder - Docker CLI")

    # Verificar Docker disponível
    try:
        subprocess.run(["docker", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print_error("Docker não está disponível. Execute 'p' para verificar pré-requisitos.")
        return False

    test_dir = create_test_environment()
    project_dir = setup_python_fastapi(test_dir)

    # Primeiro gerar o Dockerfile
    print_step("Gerando Dockerfile...")
    try:
        from src.services.dockerfile_generator import (
            DockerfileGenerator,
            ArtifactType,
            PythonVersion
        )

        generator = DockerfileGenerator()
        dockerfile = generator.generate_python_dockerfile(
            python_version=PythonVersion.PYTHON_3_11_SLIM,
            artifact_type=ArtifactType.MICROSERVICE,
            framework="fastapi",
            port=8000
        )
        (project_dir / "Dockerfile").write_text(dockerfile)
        print_success("Dockerfile gerado")
    except Exception as e:
        print_error(f"Erro ao gerar Dockerfile: {e}")
        return False

    # Executar build
    print_step("Executando build com Docker CLI...")

    try:
        import asyncio
        from src.services.container_builder import ContainerBuilder, BuilderType

        async def build():
            builder = ContainerBuilder(
                builder_type=BuilderType.DOCKER,
                enable_metrics=True
            )

            result = await builder.build_container(
                dockerfile_path=str(project_dir / "Dockerfile"),
                build_context=str(project_dir),
                image_tag="test-python:latest",
                platforms=["linux/amd64"]
            )

            return result

        result = asyncio.run(build())

        print("\n--- Resultado do Build ---")
        print(f"  Success: {Colors.GREEN if result.success else Colors.RED}{result.success}{Colors.END}")
        print(f"  Image Tag: {result.image_tag or 'N/A'}")
        print(f"  Digest: {result.image_digest or 'N/A'}")
        print(f"  Size: {result.size_bytes or 0:,} bytes" if result.size_bytes else "  Size: N/A")
        print(f"  Duration: {result.duration_seconds:.2f}s")

        if result.build_logs:
            print(f"\n--- Últimas 5 linhas do log ---")
            for log in result.build_logs[-5:]:
                print(f"  {log}")

        if result.success:
            print_success(f"\n{Colors.BOLD}TC-004: PASS{Colors.END}")

            # Verificar imagem
            print_step("Verificando imagem criada...")
            try:
                output = subprocess.run(
                    ["docker", "images", "test-python:latest", "--format", "{{.ID}}"],
                    capture_output=True, text=True
                )
                if output.stdout.strip():
                    print_success(f"Imagem criada: {output.stdout.strip()}")
            except:
                pass

            return True
        else:
            print_error(f"\n{Colors.BOLD}TC-004: FAIL{Colors.END}")
            if result.error_message:
                print_error(f"Erro: {result.error_message}")
            return False

    except Exception as e:
        print_error(f"Erro ao executar build: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_tc009():
    """Executa TC-009: Performance Metrics Coleta."""
    print_header("TC-009: Performance Metrics - Coleta")

    try:
        from src.services.build_metrics import get_metrics_collector

        print_step("Obtendo coletor de métricas...")
        collector = get_metrics_collector()

        print_step("Gerando relatório de performance...")
        report = collector.get_performance_report()

        print("\n=== RELATÓRIO DE PERFORMANCE ===\n")
        print(f"Total de builds: {report['summary']['total_builds']}")
        print(f"Builds bem-sucedidos: {report['summary']['successful_builds']}")
        print(f"Taxa de sucesso: {report['summary']['success_rate']:.1%}")

        if report['duration_by_language']:
            print(f"\n--- Duração por Linguagem ---")
            for lang, stats in report['duration_by_language'].items():
                print(f"  {lang}:")
                print(f"    Média: {stats['mean']:.2f}s")
                print(f"    Mediana: {stats['median']:.2f}s")
                print(f"    Min/Max: {stats['min']:.2f}s / {stats['max']:.2f}s")
                print(f"    Count: {stats['count']}")

        if report['cache_hit_rate_by_language']:
            print(f"\n--- Cache Hit Rate por Linguagem ---")
            for lang, rate in report['cache_hit_rate_by_language'].items():
                print(f"  {lang}: {rate:.1f}%")

        ma = report['multi_arch_impact']
        if ma['single_arch_count'] > 0 or ma['multi_arch_count'] > 0:
            print(f"\n--- Impacto Multi-arch ---")
            print(f"  Single-arch builds: {ma['single_arch_count']}")
            print(f"  Multi-arch builds: {ma['multi_arch_count']}")
            if ma['single_arch_avg_duration'] > 0:
                print(f"  Avg single-arch: {ma['single_arch_avg_duration']:.2f}s")
            if ma['multi_arch_avg_duration'] > 0:
                print(f"  Avg multi-arch: {ma['multi_arch_avg_duration']:.2f}s")
            if ma['multi_arch_overhead_percent'] > 0:
                print(f"  Overhead: {ma['multi_arch_overhead_percent']:.1f}%")

        # Verificar arquivo de métricas
        metrics_file = Path("metrics/build_metrics.jsonl")
        if metrics_file.exists():
            line_count = len(metrics_file.read_text().split('\n')) if metrics_file.read_text() else 0
            print(f"\n--- Métricas Persistidas ---")
            print_success(f"Arquivo: {metrics_file}")
            print(f"Linhas: {line_count}")

        print_success(f"\n{Colors.BOLD}TC-009: PASS{Colors.END}")
        return True

    except Exception as e:
        print_error(f"Erro ao executar teste: {e}")
        import traceback
        traceback.print_exc()
        return False


def setup_environment():
    """Configura ambiente de teste."""
    print_header("CONFIGURANDO AMBIENTE DE TESTE")

    test_dir = create_test_environment()

    print_step("Criando projetos de teste...")

    projects = {
        "Python FastAPI": setup_python_fastapi,
        "Node.js Express": setup_nodejs_express,
        "Go Gin": setup_go_gin,
    }

    for name, setup_fn in projects.items():
        try:
            setup_fn(test_dir)
        except Exception as e:
            print_error(f"Erro ao criar {name}: {e}")

    print_success(f"\nAmbiente configurado em: {test_dir}")
    print_info("Projetos criados:")
    for project in test_dir.iterdir():
        if project.is_dir():
            print(f"  - {project.name}/")


def clean_environment():
    """Limpa ambiente de teste."""
    print_header("LIMPANDO AMBIENTE DE TESTE")

    test_dir = Path("/tmp/codeforge-test")

    # Remover projetos de teste
    if test_dir.exists():
        print_step("Removendo projetos de teste...")
        shutil.rmtree(test_dir)
        print_success("Projetos removidos")

    # Remover imagens de teste
    print_step("Removendo imagens Docker de teste...")
    try:
        result = subprocess.run(
            ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
            capture_output=True, text=True
        )
        test_images = ["test-python:latest", "test-cache:1", "test-cache:2",
                       "test-multiarch:latest"]

        for img in test_images:
            if img in result.stdout:
                subprocess.run(["docker", "rmi", "-f", img],
                             capture_output=True)
                print_success(f"Removida: {img}")
    except:
        pass

    # Perguntar sobre métricas
    metrics_file = Path("metrics/build_metrics.jsonl")
    if metrics_file.exists():
        print_info(f"\nMétricas preservadas em: {metrics_file}")
        print_info("Para remover, execute: rm metrics/build_metrics.jsonl")

    print_success("\nLimpeza concluída!")


def show_metrics():
    """Mostra métricas coletadas."""
    print_header("MÉTRICAS COLETADAS")

    metrics_file = Path("metrics/build_metrics.jsonl")

    if not metrics_file.exists():
        print_info("Nenhuma métrica coletada ainda.")
        print_info("Execute alguns builds primeiro (TC-004, TC-007).")
        return

    print_step("Lendo arquivo de métricas...")
    content = metrics_file.read_text()
    lines = [l for l in content.split('\n') if l.strip()]

    print(f"\nTotal de registros: {len(lines)}")
    print(f"Arquivo: {metrics_file}")
    print(f"Tamanho: {len(content):,} bytes")

    if lines:
        print("\n--- Últimos 5 registros ---")
        import json
        for line in lines[-5:]:
            try:
                data = json.loads(line)
                print(f"  {data['timestamp'][:19]} | {data['language']:<10} | "
                      f"{data.get('framework', 'N/A'):<10} | "
                      f"{'✓' if data['success'] else '✗'} | "
                      f"{data['duration_seconds']:.1f}s")
            except:
                pass


def main():
    """Função principal."""
    import sys

    if len(sys.argv) > 1:
        # Modo direto: ./script.py TC-001
        test_case = sys.argv[1].upper()
        if test_case == "TC-001" or test_case == "1":
            run_tc001()
        elif test_case == "TC-004" or test_case == "4":
            run_tc004()
        elif test_case == "TC-009" or test_case == "9":
            run_tc009()
        else:
            print(f"Teste {test_case} não implementado no script.")
        return

    # Modo interativo
    while True:
        print_menu()
        choice = input().strip().lower()

        if choice == 'q':
            print("\nAté logo!")
            break
        elif choice == 'h':
            print_help()
        elif choice == 'p':
            check_prerequisites()
        elif choice == 'e':
            setup_environment()
        elif choice == 'c':
            clean_environment()
        elif choice == 'm':
            show_metrics()
        elif choice == '1':
            run_tc001()
        elif choice == '4':
            run_tc004()
        elif choice == '9':
            run_tc009()
        else:
            print_info(f"Opção '{choice}' não implementada. Use 'h' para ajuda.")

        input("\nPressione Enter para continuar...")


if __name__ == "__main__":
    main()
