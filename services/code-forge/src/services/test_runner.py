import asyncio
import subprocess
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List
import structlog

from ..models.pipeline_context import PipelineContext
from ..models.artifact import ValidationResult, ValidationType, ValidationStatus

logger = structlog.get_logger()


class TestRunner:
    """Subpipeline 4: Testes Automáticos"""

    def __init__(
        self,
        min_coverage: float = 0.8,
        test_timeout: int = 300,
        workspace_root: str = "/tmp/code-forge-tests",
        mongodb_client = None
    ):
        self.min_coverage = min_coverage
        self.test_timeout = test_timeout
        self.workspace_root = Path(workspace_root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.mongodb_client = mongodb_client

    async def run_tests(self, context: PipelineContext):
        """
        Executa testes automáticos no código gerado.

        Args:
            context: Contexto do pipeline
        """
        ticket = context.ticket
        artifact = context.get_latest_artifact()

        if not artifact:
            logger.warning('no_artifact_found_skipping_tests', ticket_id=ticket.ticket_id)
            return

        logger.info(
            'test_execution_started',
            ticket_id=ticket.ticket_id,
            artifact_id=artifact.artifact_id
        )

        try:
            # Recuperar código do MongoDB para executar testes
            if self.mongodb_client:
                code_content = await self.mongodb_client.get_artifact_content(artifact.artifact_id)
            else:
                # Fallback se cliente não injetado
                from ..clients.mongodb_client import MongoDBClient
                temp_client = MongoDBClient(
                    url="mongodb://localhost:27017",
                    db_name="code_forge"
                )
                await temp_client.start()
                try:
                    code_content = await temp_client.get_artifact_content(artifact.artifact_id)
                finally:
                    await temp_client.stop()

            if not code_content:
                logger.warning('artifact_content_empty', ticket_id=ticket.ticket_id)
                return

            # Criar workspace para este ticket
            workspace = self.workspace_root / ticket.ticket_id
            workspace.mkdir(exist_ok=True)

            # Escrever código em arquivo para testar
            test_file = workspace / "generated_code.py"
            test_file.write_text(code_content, encoding='utf-8')

            # Gerar arquivo de testes automatizado
            test_suite_file = workspace / "test_generated.py"
            test_suite_content = self._generate_test_suite(
                artifact.language,
                code_content,
                ticket.parameters
            )
            test_suite_file.write_text(test_suite_content, encoding='utf-8')

            # Executar pytest
            result = await self._run_pytest(workspace, ticket.ticket_id)

            context.add_validation(result)
            logger.info(
                'tests_completed',
                status=result.status,
                score=result.score,
                coverage=result.score >= self.min_coverage
            )

        except Exception as e:
            logger.error('test_execution_failed', error=str(e), exc_info=True)
            # Criar resultado de falha
            failed_result = ValidationResult(
                validation_type=ValidationType.UNIT_TEST,
                tool_name='pytest',
                tool_version='7.4.0',
                status=ValidationStatus.FAILED,
                score=0.0,
                issues_count=1,
                critical_issues=1,
                high_issues=0,
                medium_issues=0,
                low_issues=0,
                executed_at=datetime.now(),
                duration_ms=0,
                report_uri=None
            )
            context.add_validation(failed_result)
        finally:
            # Limpar workspace (opcional - comentado para debug)
            # await self._cleanup_workspace(workspace)
            pass

    async def _run_pytest(self, workspace: Path, ticket_id: str) -> ValidationResult:
        """
        Executa pytest no workspace e retorna resultado validado.

        Args:
            workspace: Diretório com código e testes
            ticket_id: ID do ticket para tracing

        Returns:
            ValidationResult com métricas reais
        """
        start_time = datetime.now()

        try:
            # Comando pytest com cobertura
            cmd = [
                'python', '-m', 'pytest',
                str(workspace / 'test_generated.py'),
                '--cov=' + str(workspace / 'generated_code.py'),
                '--cov-report=json',
                '--cov-report=term-missing',
                '-v',
                '--tb=short',
                '--timeout=' + str(self.test_timeout)
            ]

            # Executar pytest com timeout
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workspace)
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.test_timeout + 10
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise TimeoutError(f'Tests timed out after {self.test_timeout}s')

            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            stdout_text = stdout.decode('utf-8')
            stderr_text = stderr.decode('utf-8')

            # Analisar resultados
            return self._parse_pytest_output(
                workspace, stdout_text, stderr_text, proc.returncode, duration_ms
            )

        except TimeoutError as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error('pytest_timeout', error=str(e))
            return ValidationResult(
                validation_type=ValidationType.UNIT_TEST,
                tool_name='pytest',
                tool_version='7.4.0',
                status=ValidationStatus.FAILED,
                score=0.0,
                issues_count=1,
                critical_issues=1,
                high_issues=0,
                medium_issues=0,
                low_issues=0,
                executed_at=start_time,
                duration_ms=duration_ms
            )
        except FileNotFoundError:
            # pytest não instalado - usar modo heurístico
            logger.warning('pytest_not_found_using_heuristic')
            return self._run_heuristic_tests(workspace, start_time)
        except Exception as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error('pytest_execution_error', error=str(e))
            return ValidationResult(
                validation_type=ValidationType.UNIT_TEST,
                tool_name='pytest',
                tool_version='7.4.0',
                status=ValidationStatus.FAILED,
                score=0.0,
                issues_count=1,
                critical_issues=1,
                high_issues=0,
                medium_issues=0,
                low_issues=0,
                executed_at=start_time,
                duration_ms=duration_ms,
                report_uri=None
            )

    def _parse_pytest_output(
        self, workspace: Path, stdout: str, stderr: str, returncode: int, duration_ms: int
    ) -> ValidationResult:
        """Parse saída do pytest e extrai métricas."""
        status = ValidationStatus.PASSED if returncode == 0 else ValidationStatus.FAILED

        # Extrair estatísticas de teste
        test_match = re.search(r'(\d+) passed', stdout)
        failed_match = re.search(r'(\d+) failed', stdout)
        error_match = re.search(r'(\d+) error', stdout)

        passed = int(test_match.group(1)) if test_match else 0
        failed = int(failed_match.group(1)) if failed_match else 0
        errors = int(error_match.group(1)) if error_match else 0
        total_tests = passed + failed + errors

        issues_count = failed + errors

        # Ler cobertura do arquivo JSON
        coverage_file = workspace / 'coverage.json'
        coverage_pct = 0.0
        if coverage_file.exists():
            try:
                coverage_data = json.loads(coverage_file.read_text())
                totals = coverage_data.get('totals', {})
                coverage_pct = totals.get('percent_covered', 0.0) / 100.0
            except Exception:
                pass

        score = coverage_pct

        # Determinar severidade dos issues
        critical_issues = 1 if coverage_pct < self.min_coverage else 0
        high_issues = failed if failed > 0 else 0
        medium_issues = errors if errors > 0 else 0
        low_issues = 0

        return ValidationResult(
            validation_type=ValidationType.UNIT_TEST,
            tool_name='pytest',
            tool_version='7.4.0',
            status=status,
            score=score,
            issues_count=issues_count,
            critical_issues=critical_issues,
            high_issues=high_issues,
            medium_issues=medium_issues,
            low_issues=low_issues,
            executed_at=datetime.now(),
            duration_ms=duration_ms,
            report_uri=str(coverage_file) if coverage_file.exists() else None
        )

    def _run_heuristic_tests(self, workspace: Path, start_time: datetime) -> ValidationResult:
        """
        Executa validação heurística quando pytest não está disponível.

        Args:
            workspace: Diretório com código
            start_time: Timestamp de início

        Returns:
            ValidationResult baseado em heurística
        """
        # Analisar código gerado
        code_file = workspace / "generated_code.py"
        if not code_file.exists():
            return ValidationResult(
                validation_type=ValidationType.UNIT_TEST,
                tool_name='heuristic',
                tool_version='1.0.0',
                status=ValidationStatus.FAILED,
                score=0.0,
                issues_count=1,
                critical_issues=1,
                high_issues=0,
                medium_issues=0,
                low_issues=0,
                executed_at=start_time,
                duration_ms=0
            )

        code = code_file.read_text()

        # Heurísticas de qualidade
        has_imports = bool(re.search(r'^import |^from ', code, re.MULTILINE))
        has_functions = bool(re.search(r'def \w+\(', code))
        has_classes = bool(re.search(r'class \w+', code))
        has_docstrings = bool('"""' in code or "'''" in code)
        has_error_handling = bool('try:' in code or 'except' in code)
        has_type_hints = bool('->' in code or ': ' in code)

        score = 0.0
        checks_passed = 0
        total_checks = 6

        if has_imports:
            checks_passed += 1
        if has_functions or has_classes:
            checks_passed += 1
        if has_docstrings:
            checks_passed += 1
        if has_error_handling:
            checks_passed += 1
        if has_type_hints:
            checks_passed += 1
        if len(code) > 100:  # Código mínimo
            checks_passed += 1

        score = checks_passed / total_checks

        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        return ValidationResult(
            validation_type=ValidationType.UNIT_TEST,
            tool_name='heuristic',
            tool_version='1.0.0',
            status=ValidationStatus.PASSED if score >= 0.6 else ValidationStatus.WARNING,
            score=score,
            issues_count=0 if score >= 0.6 else 1,
            critical_issues=1 if score < self.min_coverage else 0,
            high_issues=0,
            medium_issues=1 if score < 0.6 else 0,
            low_issues=0,
            executed_at=start_time,
            duration_ms=duration_ms
        )

    def _generate_test_suite(self, language: str, code: str, parameters: Dict) -> str:
        """
        Gera suite de testes baseada no código gerado.

        Args:
            language: Linguagem do código
            code: Conteúdo do código
            parameters: Parâmetros do ticket

        Returns:
            Código da suite de testes
        """
        if language.lower() == 'python':
            return self._generate_python_test_suite(code, parameters)
        else:
            return self._generate_generic_test_suite(language, code)

    def _generate_python_test_suite(self, code: str, parameters: Dict) -> str:
        """Gera testes pytest para código Python."""
        service_name = parameters.get('service_name', 'my-service')

        return f'''"""
Test suite auto-generated for {service_name}
Generated by Neural Code Forge
"""

import pytest
import sys
from pathlib import Path

# Adicionar diretório ao path
sys.path.insert(0, str(Path(__file__).parent))

from generated_code import app


class Test{service_name.replace('-', '_').replace('_', ' ').title().replace(' ', '')}:
    """Testes para {service_name}"""

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Testa endpoint de health check"""
        from fastapi.testclient import TestClient
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    @pytest.mark.asyncio
    async def test_root_endpoint(self):
        """Testa endpoint raiz"""
        from fastapi.testclient import TestClient
        client = TestClient(app)

        response = client.get("/")
        assert response.status_code == 200

    def test_module_imports(self):
        """Testa se módulos podem ser importados"""
        import generated_code
        assert hasattr(generated_code, 'app')

    def test_has_app_instance(self):
        """Testa se instância do app existe"""
        assert app is not None
        assert hasattr(app, 'routes')


class TestCodeQuality:
    """Testes de qualidade de código"""

    def test_has_functions(self):
        """Testa se código possui funções"""
        import generated_code
        functions = [
            name for name in dir(generated_code)
            if not name.startswith('_') and callable(getattr(generated_code, name, None))
        ]
        assert len(functions) > 0

    def test_docstrings_present(self):
        """Testa se há docstrings"""
        import generated_code
        module_doc = generated_code.__doc__
        assert module_doc is not None and len(module_doc.strip()) > 0
'''

    def _generate_generic_test_suite(self, language: str, code: str) -> str:
        """Gera testes genéricos para outras linguagens."""
        return f'''# Generic test suite for {language}
# Auto-generated by Neural Code Forge

import subprocess
import sys

class TestGeneratedCode:
    """Generic tests for generated code"""

    def test_code_syntax(self):
        """Test basic syntax validation"""
        result = subprocess.run(
            [sys.executable, '-m', 'py_compile', 'generated_code.py'],
            capture_output=True
        )
        assert result.returncode == 0, "Syntax check failed"

    def test_file_exists(self):
        """Test if generated file exists"""
        import os
        assert os.path.exists('generated_code.py')
'''

    async def _cleanup_workspace(self, workspace: Path):
        """Limpa workspace após testes."""
        try:
            import shutil
            if workspace.exists():
                shutil.rmtree(workspace)
                logger.debug('workspace_cleaned', path=str(workspace))
        except Exception as e:
            logger.warning('workspace_cleanup_failed', error=str(e))
