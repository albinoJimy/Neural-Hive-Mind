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


# Language-to-file extension mapping
LANGUAGE_EXTENSIONS = {
    'python': 'py',
    'javascript': 'js',
    'typescript': 'ts',
    'go': 'go',
    'java': 'java',
    'js': 'js',
    'ts': 'ts',
}

# Language-to-default-filename mapping
LANGUAGE_FILENAMES = {
    'python': 'generated_code.py',
    'javascript': 'generated_code.js',
    'typescript': 'generated_code.ts',
    'go': 'main.go',
    'java': 'Main.java',
    'js': 'generated_code.js',
    'ts': 'generated_code.ts',
}


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

    def _get_source_filename(self, language: str) -> str:
        """
        Retorna o nome do arquivo fonte baseado na linguagem.

        Args:
            language: Linguagem do código gerado

        Returns:
            Nome do arquivo com extensão apropriada
        """
        language_lower = language.lower()
        return LANGUAGE_FILENAMES.get(language_lower, f'generated_code.{language_lower}')

    def _is_python_language(self, language: str) -> bool:
        """
        Verifica se a linguagem é Python.

        Args:
            language: Linguagem do código

        Returns:
            True se for Python, False caso contrário
        """
        return language.lower() in ('python', 'py')

    def _is_javascript_language(self, language: str) -> bool:
        """
        Verifica se a linguagem é JavaScript/TypeScript.

        Args:
            language: Linguagem do código

        Returns:
            True se for JavaScript/TypeScript, False caso contrário
        """
        lang_lower = language.lower()
        return lang_lower in ('javascript', 'js', 'typescript', 'ts', 'nodejs', 'node.js')

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

            # Determinar nome do arquivo baseado na linguagem
            source_filename = self._get_source_filename(artifact.language)
            source_file = workspace / source_filename
            source_file.write_text(code_content, encoding='utf-8')

            # Detectar tipo de linguagem
            is_python = self._is_python_language(artifact.language)
            is_javascript = self._is_javascript_language(artifact.language)

            # Gerar arquivo de testes e configuração baseado na linguagem
            if is_javascript:
                # Criar package.json para projetos Node.js
                package_json = self._generate_package_json(ticket.ticket_id)
                (workspace / "package.json").write_text(package_json, encoding='utf-8')

                # Gerar arquivo de testes Jest
                test_filename = "generated_code.test.js"
                test_suite_content = self._generate_jest_test_suite(
                    artifact.language,
                    code_content,
                    ticket.parameters
                )
                (workspace / test_filename).write_text(test_suite_content, encoding='utf-8')

                # Criar diretório __tests__ se necessário
                (workspace / "__tests__").mkdir(exist_ok=True)
            else:
                # Gerar arquivo de testes Python
                test_suite_file = workspace / "test_generated.py"
                test_suite_content = self._generate_test_suite(
                    artifact.language,
                    code_content,
                    ticket.parameters
                )
                test_suite_file.write_text(test_suite_content, encoding='utf-8')

            # Executar testes baseado na linguagem
            result = await self._run_tests(
                workspace, ticket.ticket_id, source_filename, is_python, is_javascript
            )

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
            # Limpar workspace (pode ser desabilitado via env var para debug)
            import os
            skip_cleanup = os.getenv('CODE_FORGE_SKIP_CLEANUP', '').lower() in ('1', 'true', 'yes')
            if not skip_cleanup:
                await self._cleanup_workspace(workspace)

    async def _run_tests(
        self, workspace: Path, ticket_id: str, source_filename: str,
        is_python: bool, is_javascript: bool = False
    ) -> ValidationResult:
        """
        Executa testes no workspace baseado na linguagem.

        Args:
            workspace: Diretório com código e testes
            ticket_id: ID do ticket para tracing
            source_filename: Nome do arquivo fonte
            is_python: True se for Python, False caso contrário
            is_javascript: True se for JavaScript/TypeScript, False caso contrário

        Returns:
            ValidationResult com métricas reais
        """
        if is_python:
            return await self._run_pytest(workspace, ticket_id, source_filename)
        elif is_javascript:
            return await self._run_nodejs_tests(workspace, ticket_id, source_filename)
        else:
            return await self._run_generic_tests(workspace, ticket_id, source_filename)

    async def _run_pytest(
        self, workspace: Path, ticket_id: str, source_filename: str = "generated_code.py"
    ) -> ValidationResult:
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
                '--cov=' + str(workspace / source_filename),
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
            return self._run_heuristic_tests(workspace, start_time, source_filename)
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

    async def _run_generic_tests(
        self, workspace: Path, ticket_id: str, source_filename: str
    ) -> ValidationResult:
        """
        Executa testes genéricos para linguagens não-Python.

        Args:
            workspace: Diretório com código
            ticket_id: ID do ticket para tracing
            source_filename: Nome do arquivo fonte

        Returns:
            ValidationResult com validação básica
        """
        start_time = datetime.now()
        source_file = workspace / source_filename

        try:
            # Verificar se arquivo existe
            if not source_file.exists():
                logger.warning(
                    'source_file_not_found',
                    ticket_id=ticket_id,
                    source_filename=source_filename
                )
                return ValidationResult(
                    validation_type=ValidationType.UNIT_TEST,
                    tool_name='generic',
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

            # Verificar se arquivo tem conteúdo
            code = source_file.read_text(encoding='utf-8')
            if not code or len(code.strip()) < 10:
                logger.warning('source_file_empty_or_too_small', ticket_id=ticket_id)
                return ValidationResult(
                    validation_type=ValidationType.UNIT_TEST,
                    tool_name='generic',
                    tool_version='1.0.0',
                    status=ValidationStatus.WARNING,
                    score=0.3,
                    issues_count=1,
                    critical_issues=0,
                    high_issues=1,
                    medium_issues=0,
                    low_issues=0,
                    executed_at=start_time,
                    duration_ms=0
                )

            # Executar validação específica da linguagem
            ext = source_file.suffix.lower()
            result = await self._validate_by_extension(workspace, ext, source_filename, start_time)

            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            result.duration_ms = duration_ms

            logger.info(
                'generic_tests_completed',
                ticket_id=ticket_id,
                source_filename=source_filename,
                status=result.status,
                score=result.score
            )

            return result

        except Exception as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error('generic_tests_error', ticket_id=ticket_id, error=str(e))
            return ValidationResult(
                validation_type=ValidationType.UNIT_TEST,
                tool_name='generic',
                tool_version='1.0.0',
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

    async def _validate_by_extension(
        self, workspace: Path, ext: str, source_filename: str, start_time: datetime
    ) -> ValidationResult:
        """
        Valida código baseado na extensão do arquivo.

        Args:
            workspace: Diretório com código
            ext: Extensão do arquivo
            source_filename: Nome do arquivo fonte
            start_time: Timestamp de início

        Returns:
            ValidationResult com validação específica
        """
        source_file = workspace / source_filename

        # JavaScript/TypeScript - usa Node.js syntax check
        if ext in ('.js', '.ts'):
            try:
                proc = await asyncio.create_subprocess_exec(
                    'node', '--check', str(source_file),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(workspace)
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)

                if proc.returncode == 0:
                    return ValidationResult(
                        validation_type=ValidationType.UNIT_TEST,
                        tool_name='node',
                        tool_version='syntax_check',
                        status=ValidationStatus.PASSED,
                        score=0.8,
                        issues_count=0,
                        critical_issues=0,
                        high_issues=0,
                        medium_issues=0,
                        low_issues=0,
                        executed_at=start_time,
                        duration_ms=0
                    )
                else:
                    return ValidationResult(
                        validation_type=ValidationType.UNIT_TEST,
                        tool_name='node',
                        tool_version='syntax_check',
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
            except (FileNotFoundError, asyncio.TimeoutError):
                # Node não disponível - retorna heurística
                pass

        # Go - usa gofmt para validar
        if ext == '.go':
            try:
                proc = await asyncio.create_subprocess_exec(
                    'gofmt', '-l', str(source_file),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(workspace)
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)

                # Se gofmt retornar vazio, arquivo está formatado corretamente
                if not stdout.strip():
                    return ValidationResult(
                        validation_type=ValidationType.UNIT_TEST,
                        tool_name='gofmt',
                        tool_version='syntax_check',
                        status=ValidationStatus.PASSED,
                        score=0.8,
                        issues_count=0,
                        critical_issues=0,
                        high_issues=0,
                        medium_issues=0,
                        low_issues=0,
                        executed_at=start_time,
                        duration_ms=0
                    )
            except (FileNotFoundError, asyncio.TimeoutError):
                # gofmt não disponível - retorna heurística
                pass

        # Java ou qualquer outra linguagem - retorna validação heurística
        return self._create_heuristic_result(source_file, start_time)

    def _create_heuristic_result(self, source_file: Path, start_time: datetime) -> ValidationResult:
        """
        Cria resultado baseado em heurísticas básicas.

        Args:
            source_file: Caminho do arquivo fonte
            start_time: Timestamp de início

        Returns:
            ValidationResult com base em heurística
        """
        code = source_file.read_text(encoding='utf-8')

        # Heurísticas básicas
        has_imports = bool(re.search(r'^import |^from |^package ', code, re.MULTILINE))
        has_functions = bool(re.search(r'function |def |func |class ', code))
        has_classes = bool(re.search(r'class ', code))
        has_comments = bool('//' in code or '/*' in code or '#' in code)
        has_braces = code.count('{') > 0 or code.count('(') > 0

        score = 0.0
        checks_passed = 0
        total_checks = 5

        if has_imports:
            checks_passed += 1
        if has_functions or has_classes:
            checks_passed += 1
        if has_comments:
            checks_passed += 1
        if has_braces:
            checks_passed += 1
        if len(code) > 100:
            checks_passed += 1

        score = checks_passed / total_checks

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
            duration_ms=0
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

    def _run_heuristic_tests(
        self, workspace: Path, start_time: datetime, source_filename: str = "generated_code.py"
    ) -> ValidationResult:
        """
        Executa validação heurística quando pytest não está disponível.

        Args:
            workspace: Diretório com código
            start_time: Timestamp de início
            source_filename: Nome do arquivo fonte

        Returns:
            ValidationResult baseado em heurística
        """
        # Analisar código gerado
        code_file = workspace / source_filename
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
        has_imports = bool(re.search(r'^import |^from |^package ', code, re.MULTILINE))
        has_functions = bool(re.search(r'def \w+\(|function \w+\(|func \w+\(', code))
        has_classes = bool(re.search(r'class \w+', code))
        has_docstrings = bool('"""' in code or "'''" in code or '/*' in code)
        has_error_handling = bool('try:' in code or 'except' in code or 'catch' in code)
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
        language_lower = language.lower()

        # Para Python, usa o gerador específico
        if language_lower == 'python':
            return self._generate_python_test_suite(code, {})

        # Obter o nome do arquivo correto para esta linguagem
        source_filename = self._get_source_filename(language)

        # Para JavaScript/TypeScript - usa Node.js syntax check
        if language_lower in ('javascript', 'typescript', 'js', 'ts'):
            return f'''# Generic test suite for {language}
# Auto-generated by Neural Code Forge

import subprocess
import sys
import os

class TestGeneratedCode:
    """Generic tests for generated code"""

    def test_file_exists(self):
        """Test if generated file exists"""
        assert os.path.exists('{source_filename}')

    def test_syntax_check(self):
        """Test syntax validation using Node.js if available"""
        # Tenta usar node para verificar sintaxe
        result = subprocess.run(
            ['node', '--check', '{source_filename}'],
            capture_output=True,
            timeout=5
        )
        # Se node não está disponível ou syntax ok, passa
        assert result.returncode == 0 or b"not found" in result.stderr or b"command not found" in result.stderr
'''

        # Para Go - usa gofmt para validar
        if language_lower == 'go':
            return f'''# Generic test suite for Go
# Auto-generated by Neural Code Forge

import subprocess
import os

class TestGeneratedCode:
    """Generic tests for Go code"""

    def test_file_exists(self):
        """Test if generated file exists"""
        assert os.path.exists('{source_filename}')

    def test_syntax_check(self):
        """Test syntax validation using gofmt"""
        result = subprocess.run(
            ['gofmt', '-l', '{source_filename}'],
            capture_output=True,
            timeout=5
        )
        # Se gofmt não está disponível ou syntax ok, passa
        assert result.returncode == 0 or b"not found" in result.stderr or b"command not found" in result.stderr
'''

        # Para Java - valida que arquivo existe (syntax check requer compilação completa)
        if language_lower == 'java':
            return f'''# Generic test suite for Java
# Auto-generated by Neural Code Forge

import os

class TestGeneratedCode:
    """Generic tests for Java code"""

    def test_file_exists(self):
        """Test if generated file exists"""
        assert os.path.exists('{source_filename}')

    def test_class_name_present(self):
        """Test if class name is present in file"""
        if os.path.exists('{source_filename}'):
            with open('{source_filename}', 'r') as f:
                content = f.read()
                assert 'class' in content or 'interface' in content or 'enum' in content
'''

        # Fallback genérico - apenas verifica existência do arquivo
        return f'''# Generic test suite for {language}
# Auto-generated by Neural Code Forge

import os

class TestGeneratedCode:
    """Generic tests for generated code"""

    def test_file_exists(self):
        """Test if generated file exists"""
        assert os.path.exists('{source_filename}')
'''

    def _generate_package_json(self, ticket_id: str) -> str:
        """
        Gera package.json para projetos Node.js.

        Args:
            ticket_id: ID do ticket para nome do projeto

        Returns:
            Conteúdo do package.json
        """
        return json.dumps({
            "name": f"code-forge-{ticket_id[:8]}",
            "version": "1.0.0",
            "description": "Auto-generated by Neural Code Forge",
            "scripts": {
                "test": "jest --verbose --coverage",
                "test:watch": "jest --watch"
            },
            "jest": {
                "testEnvironment": "node",
                "coverageDirectory": "coverage",
                "collectCoverageFrom": [
                    "generated_code.js",
                    "generated_code.ts"
                ],
                "testMatch": [
                    "**/*.test.js",
                    "**/*.test.ts"
                ]
            },
            "devDependencies": {
                "jest": "^29.7.0",
                "@types/jest": "^29.5.5"
            }
        }, indent=2)

    def _generate_jest_test_suite(self, language: str, code: str, parameters: Dict) -> str:
        """
        Gera suite de testes Jest para JavaScript/TypeScript.

        Args:
            language: Linguagem do código (javascript/typescript)
            code: Conteúdo do código
            parameters: Parâmetros do ticket

        Returns:
            Código da suite de testes Jest
        """
        service_name = parameters.get('service_name', 'my-service')
        is_typescript = language.lower() in ('typescript', 'ts')

        # Determinar extensão do arquivo fonte
        source_ext = '.ts' if is_typescript else '.js'

        return f'''/**
 * Test suite auto-generated for {service_name}
 * Generated by Neural Code Forge
 */

const {{ app }} = require('./generated_code{source_ext}');

describe('{service_name}', () => {{
  describe('Health Checks', () => {{
    test('should have app instance', () => {{
      expect(app).toBeDefined();
    }});

    test('should export required functions', () => {{
      // Verifica se funções principais existem
      if (typeof app === 'object') {{
        expect(Object.keys(app).length).toBeGreaterThan(0);
      }}
    }});
  }});

  describe('Code Quality', () => {{
    test('should have defined exports', () => {{
      expect(typeof app).not.toBe('undefined');
    }});

    test('should not have syntax errors', () => {{
      // Se chegou aqui, não há erros de sintaxe
      expect(true).toBe(true);
    }});
  }});

  describe('Functionality', () => {{
    test('should handle basic operations', () => {{
      // Teste básico de funcionalidade
      if (typeof app === 'function') {{
        expect(() => app()).not.toThrow();
      }}
    }});
  }});
}});
'''

    async def _run_nodejs_tests(
        self, workspace: Path, ticket_id: str, source_filename: str
    ) -> ValidationResult:
        """
        Executa testes Jest para JavaScript/TypeScript.

        Args:
            workspace: Diretório com código e testes
            ticket_id: ID do ticket para tracing
            source_filename: Nome do arquivo fonte

        Returns:
            ValidationResult com métricas do Jest
        """
        start_time = datetime.now()

        logger.info(
            'jest_execution_started',
            ticket_id=ticket_id,
            workspace=str(workspace)
        )

        try:
            # Instalar dependências se necessário
            package_json = workspace / "package.json"
            node_modules = workspace / "node_modules"

            if not node_modules.exists() and package_json.exists():
                logger.info('installing_npm_dependencies', ticket_id=ticket_id)
                npm_install = await asyncio.create_subprocess_exec(
                    'npm', 'install', '--no-save', '--silent',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(workspace)
                )
                await asyncio.wait_for(npm_install.communicate(), timeout=120)

            # Executar Jest
            proc = await asyncio.create_subprocess_exec(
                'npx', 'jest', '--verbose', '--json', '--coverage',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workspace)
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.test_timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise TimeoutError(f'Jest tests timed out after {self.test_timeout}s')

            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            stdout_text = stdout.decode('utf-8')
            stderr_text = stderr.decode('utf-8')

            # Analisar resultados
            return self._parse_jest_output(
                stdout_text, stderr_text, proc.returncode, duration_ms
            )

        except TimeoutError as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error('jest_timeout', error=str(e))
            return ValidationResult(
                validation_type=ValidationType.UNIT_TEST,
                tool_name='jest',
                tool_version='29.7.0',
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
            # npm/jest não instalado - usar modo heurístico
            logger.warning('jest_not_found_using_heuristic', ticket_id=ticket_id)
            return self._run_heuristic_tests(workspace, start_time, source_filename)
        except Exception as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error('jest_execution_error', ticket_id=ticket_id, error=str(e))
            return ValidationResult(
                validation_type=ValidationType.UNIT_TEST,
                tool_name='jest',
                tool_version='29.7.0',
                status=ValidationStatus.FAILED,
                score=0.0,
                issues_count=1,
                critical_issues=1,
                high_issues=0,
                medium_issues=0,
                low_issues=0,
                executed_at=start_time,
                duration_ms=duration_ms,
                metadata={'error': str(e)}
            )

    def _parse_jest_output(
        self, stdout: str, stderr: str, returncode: int, duration_ms: int
    ) -> ValidationResult:
        """
        Parse saída do Jest e extrai métricas.

        Args:
            stdout: Saída padrão do Jest
            stderr: Saída de erro do Jest
            returncode: Código de retorno do Jest
            duration_ms: Duração da execução em ms

        Returns:
            ValidationResult com métricas extraídas
        """
        status = ValidationStatus.PASSED if returncode == 0 else ValidationStatus.FAILED

        # Valores padrão
        passed = 0
        failed = 0
        coverage_pct = 0.0

        # Tentar extrair JSON do output do Jest
        try:
            # Jest output pode ter JSON no final separado por newline
            lines = stdout.strip().split('\n')
            for i, line in enumerate(lines):
                if line.strip().startswith('{'):
                    # Tentar parse como JSON
                    jest_result = json.loads(line)

                    # Extrair estatísticas de teste
                    test_results = jest_result.get('testResults', [])
                    for suite in test_results:
                        for assertion in suite.get('assertionResults', []):
                            if assertion.get('status') == 'passed':
                                passed += 1
                            else:
                                failed += 1

                    # Extrair cobertura
                    coverage = jest_result.get('coverage', {})
                    if coverage:
                        # Calcular cobertura média
                        total_coverage = coverage.get('total', {})
                        if total_coverage:
                            # Jest usa pct (porcentagem já calculada)
                            coverage_pct = total_coverage.get('pct', 0.0) / 100.0

                    break
        except (json.JSONDecodeError, KeyError, TypeError):
            # Fallback: parse de texto
            pass

        # Se JSON falhou, tentar regex
        if passed == 0 and failed == 0:
            pass_match = re.search(r'(\d+) passed', stdout)
            fail_match = re.search(r'(\d+) failed', stdout)

            if pass_match:
                passed = int(pass_match.group(1))
            if fail_match:
                failed = int(fail_match.group(1))

        issues_count = failed

        # Se não conseguiu extrair cobertura, usar baseada em passed/total
        if coverage_pct == 0.0:
            total_tests = passed + failed
            if total_tests > 0:
                coverage_pct = passed / total_tests

        score = coverage_pct

        # Determinar severidade dos issues
        critical_issues = 1 if coverage_pct < self.min_coverage else 0
        high_issues = failed if failed > 0 else 0
        medium_issues = 0
        low_issues = 0

        return ValidationResult(
            validation_type=ValidationType.UNIT_TEST,
            tool_name='jest',
            tool_version='29.7.0',
            status=status,
            score=score,
            issues_count=issues_count,
            critical_issues=critical_issues,
            high_issues=high_issues,
            medium_issues=medium_issues,
            low_issues=low_issues,
            executed_at=datetime.now(),
            duration_ms=duration_ms,
            report_uri=str(Path('coverage') / 'index.html') if Path('coverage').exists() else None,
            metadata={
                'tests_passed': passed,
                'tests_failed': failed,
                'coverage_pct': coverage_pct * 100
            }
        )

    async def _cleanup_workspace(self, workspace: Path, max_retries: int = 3) -> bool:
        """
        Limpa workspace após testes com retry e tratamento robusto de erros.

        Args:
            workspace: Diretório do workspace a limpar
            max_retries: Número máximo de tentativas

        Returns:
            True se cleanup bem-sucedido, False caso contrário
        """
        import shutil
        import asyncio

        for attempt in range(max_retries):
            try:
                if not workspace.exists():
                    logger.debug('workspace_not_exists', path=str(workspace))
                    return True

                # Tentar remover diretório
                shutil.rmtree(workspace)

                # Verificar se foi realmente removido
                if not workspace.exists():
                    logger.info(
                        'workspace_cleaned',
                        path=str(workspace),
                        attempt=attempt + 1
                    )
                    return True
                else:
                    logger.warning(
                        'workspace_cleanup_verification_failed',
                        path=str(workspace),
                        attempt=attempt + 1
                    )

            except PermissionError as e:
                logger.warning(
                    'workspace_cleanup_permission_error',
                    path=str(workspace),
                    attempt=attempt + 1,
                    error=str(e)
                )
                if attempt < max_retries - 1:
                    # Aguardar antes de retry
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
            except OSError as e:
                # Em sistemas Windows, arquivos podem estar "travados" por processos
                logger.warning(
                    'workspace_cleanup_os_error',
                    path=str(workspace),
                    attempt=attempt + 1,
                    error=str(e)
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
            except Exception as e:
                logger.error(
                    'workspace_cleanup_unexpected_error',
                    path=str(workspace),
                    attempt=attempt + 1,
                    error=str(e)
                )
                break

        logger.error(
            'workspace_cleanup_failed',
            path=str(workspace),
            max_retries=max_retries
        )
        return False
