"""
Parsers para relatorios de teste e coverage.

Suporta formatos:
- JUnit XML (pytest, JUnit, Jest, etc.)
- Cobertura XML (coverage.py, pytest-cov, etc.)
- LCOV (Jest, Istanbul, etc.)
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import structlog


logger = structlog.get_logger()


@dataclass
class TestCase:
    """Representa um caso de teste individual."""
    name: str
    classname: str
    time: float
    status: str  # 'passed', 'failed', 'skipped', 'error'
    message: Optional[str] = None
    stack_trace: Optional[str] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None

    @property
    def passed(self) -> bool:
        return self.status == 'passed'

    @property
    def failed(self) -> bool:
        return self.status == 'failed'


@dataclass
class TestResults:
    """Resultado agregado de testes."""
    total: int
    passed: int
    failed: int
    skipped: int
    errors: int
    duration_seconds: float
    test_cases: List[TestCase] = field(default_factory=list)
    test_suites: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100.0

    @property
    def all_passed(self) -> bool:
        return self.failed == 0 and self.errors == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total': self.total,
            'passed': self.passed,
            'failed': self.failed,
            'skipped': self.skipped,
            'errors': self.errors,
            'duration_seconds': self.duration_seconds,
            'success_rate': self.success_rate,
            'all_passed': self.all_passed,
            'test_cases_count': len(self.test_cases)
        }


@dataclass
class CoverageResults:
    """Resultado de coverage."""
    line_coverage: float  # Percentual 0-100
    branch_coverage: Optional[float] = None
    function_coverage: Optional[float] = None
    lines_covered: int = 0
    lines_total: int = 0
    branches_covered: int = 0
    branches_total: int = 0
    functions_covered: int = 0
    functions_total: int = 0
    complexity: Optional[int] = None
    files: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'line_coverage': self.line_coverage,
            'branch_coverage': self.branch_coverage,
            'function_coverage': self.function_coverage,
            'lines_covered': self.lines_covered,
            'lines_total': self.lines_total,
            'branches_covered': self.branches_covered,
            'branches_total': self.branches_total,
            'functions_covered': self.functions_covered,
            'functions_total': self.functions_total,
            'complexity': self.complexity,
            'files_count': len(self.files)
        }


class JUnitXMLParser:
    """
    Parser para JUnit XML format.

    Compativel com:
    - pytest --junitxml
    - JUnit (Java)
    - Jest (JavaScript)
    - go test -v -json | go-junit-report
    - NUnit (C#)
    """

    def __init__(self):
        self.logger = logger.bind(parser='junit_xml')

    def parse(self, content: Union[str, bytes]) -> TestResults:
        """
        Parseia conteudo JUnit XML.

        Args:
            content: XML string ou bytes

        Returns:
            TestResults com todos os casos de teste

        Raises:
            ValueError: Se XML for invalido
        """
        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='replace')

        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            self.logger.error('junit_xml_parse_error', error=str(e))
            raise ValueError(f'Invalid JUnit XML: {e}')

        test_cases: List[TestCase] = []
        test_suites: List[Dict[str, Any]] = []
        total_tests = 0
        total_passed = 0
        total_failed = 0
        total_skipped = 0
        total_errors = 0
        total_time = 0.0

        # Handle both <testsuites> (multiple) and <testsuite> (single) root elements
        if root.tag == 'testsuites':
            suites = root.findall('testsuite')
        elif root.tag == 'testsuite':
            suites = [root]
        else:
            self.logger.warning('junit_xml_unknown_root', tag=root.tag)
            suites = []

        for suite in suites:
            suite_name = suite.get('name', 'unknown')
            suite_tests = int(suite.get('tests', 0))
            suite_failures = int(suite.get('failures', 0))
            suite_errors = int(suite.get('errors', 0))
            suite_skipped = int(suite.get('skipped', 0))
            suite_time = float(suite.get('time', 0))

            test_suites.append({
                'name': suite_name,
                'tests': suite_tests,
                'failures': suite_failures,
                'errors': suite_errors,
                'skipped': suite_skipped,
                'time': suite_time
            })

            total_tests += suite_tests
            total_failed += suite_failures
            total_errors += suite_errors
            total_skipped += suite_skipped
            total_time += suite_time

            for testcase in suite.findall('testcase'):
                case = self._parse_testcase(testcase)
                test_cases.append(case)

                # Count passed tests (not failed, error, or skipped)
                if case.status == 'passed':
                    total_passed += 1

        # If no explicit test count from attributes, calculate from test cases
        if total_tests == 0 and test_cases:
            total_tests = len(test_cases)
            total_passed = sum(1 for tc in test_cases if tc.status == 'passed')
            total_failed = sum(1 for tc in test_cases if tc.status == 'failed')
            total_errors = sum(1 for tc in test_cases if tc.status == 'error')
            total_skipped = sum(1 for tc in test_cases if tc.status == 'skipped')
        elif total_tests > 0:
            # Calculate passed from totals
            total_passed = total_tests - total_failed - total_errors - total_skipped

        self.logger.info(
            'junit_xml_parsed',
            total=total_tests,
            passed=total_passed,
            failed=total_failed,
            errors=total_errors,
            skipped=total_skipped,
            suites=len(test_suites)
        )

        return TestResults(
            total=total_tests,
            passed=total_passed,
            failed=total_failed,
            skipped=total_skipped,
            errors=total_errors,
            duration_seconds=total_time,
            test_cases=test_cases,
            test_suites=test_suites
        )

    def _parse_testcase(self, element: ET.Element) -> TestCase:
        """Parseia um elemento <testcase>."""
        name = element.get('name', 'unknown')
        classname = element.get('classname', '')
        time = float(element.get('time', 0))

        # Determine status
        status = 'passed'
        message = None
        stack_trace = None

        failure = element.find('failure')
        if failure is not None:
            status = 'failed'
            message = failure.get('message', '')
            stack_trace = failure.text

        error = element.find('error')
        if error is not None:
            status = 'error'
            message = error.get('message', '')
            stack_trace = error.text

        skipped = element.find('skipped')
        if skipped is not None:
            status = 'skipped'
            message = skipped.get('message', skipped.text)

        # Get stdout/stderr if present
        stdout_el = element.find('system-out')
        stderr_el = element.find('system-err')

        return TestCase(
            name=name,
            classname=classname,
            time=time,
            status=status,
            message=message,
            stack_trace=stack_trace,
            stdout=stdout_el.text if stdout_el is not None else None,
            stderr=stderr_el.text if stderr_el is not None else None
        )

    def parse_file(self, file_path: Union[str, Path]) -> TestResults:
        """
        Parseia arquivo JUnit XML.

        Args:
            file_path: Caminho para o arquivo

        Returns:
            TestResults
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f'JUnit XML file not found: {file_path}')

        content = path.read_text(encoding='utf-8', errors='replace')
        return self.parse(content)


class CoberturaXMLParser:
    """
    Parser para Cobertura XML format.

    Compativel com:
    - coverage.py (Python)
    - pytest-cov
    - Cobertura (Java)
    - Istanbul (JavaScript)
    """

    def __init__(self):
        self.logger = logger.bind(parser='cobertura_xml')

    def parse(self, content: Union[str, bytes]) -> CoverageResults:
        """
        Parseia conteudo Cobertura XML.

        Args:
            content: XML string ou bytes

        Returns:
            CoverageResults

        Raises:
            ValueError: Se XML for invalido
        """
        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='replace')

        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            self.logger.error('cobertura_xml_parse_error', error=str(e))
            raise ValueError(f'Invalid Cobertura XML: {e}')

        # Get coverage attributes from root
        line_rate = float(root.get('line-rate', 0))
        branch_rate = float(root.get('branch-rate', 0)) if root.get('branch-rate') else None
        complexity = int(root.get('complexity', 0)) if root.get('complexity') else None

        lines_covered = 0
        lines_total = 0
        branches_covered = 0
        branches_total = 0
        functions_covered = 0
        functions_total = 0
        files_data: List[Dict[str, Any]] = []

        # Parse packages -> classes -> lines
        for package in root.findall('.//package'):
            pkg_name = package.get('name', '')

            for cls in package.findall('classes/class'):
                filename = cls.get('filename', '')
                cls_line_rate = float(cls.get('line-rate', 0))
                cls_branch_rate = float(cls.get('branch-rate', 0)) if cls.get('branch-rate') else None
                cls_complexity = int(cls.get('complexity', 0)) if cls.get('complexity') else None

                file_lines_covered = 0
                file_lines_total = 0
                file_branches_covered = 0
                file_branches_total = 0

                for line in cls.findall('lines/line'):
                    file_lines_total += 1
                    lines_total += 1

                    hits = int(line.get('hits', 0))
                    if hits > 0:
                        file_lines_covered += 1
                        lines_covered += 1

                    # Branch coverage
                    branch = line.get('branch', 'false').lower() == 'true'
                    if branch:
                        cond_coverage = line.get('condition-coverage', '')
                        match = re.search(r'(\d+)/(\d+)', cond_coverage)
                        if match:
                            covered = int(match.group(1))
                            total = int(match.group(2))
                            file_branches_covered += covered
                            file_branches_total += total
                            branches_covered += covered
                            branches_total += total

                # Count methods/functions
                for method in cls.findall('methods/method'):
                    functions_total += 1
                    method_line_rate = float(method.get('line-rate', 0))
                    if method_line_rate > 0:
                        functions_covered += 1

                files_data.append({
                    'filename': filename,
                    'package': pkg_name,
                    'line_rate': cls_line_rate,
                    'branch_rate': cls_branch_rate,
                    'complexity': cls_complexity,
                    'lines_covered': file_lines_covered,
                    'lines_total': file_lines_total
                })

        # Calculate percentages
        line_coverage = (lines_covered / lines_total * 100) if lines_total > 0 else line_rate * 100
        branch_coverage = (branches_covered / branches_total * 100) if branches_total > 0 else (branch_rate * 100 if branch_rate else None)
        function_coverage = (functions_covered / functions_total * 100) if functions_total > 0 else None

        self.logger.info(
            'cobertura_xml_parsed',
            line_coverage=line_coverage,
            branch_coverage=branch_coverage,
            function_coverage=function_coverage,
            files=len(files_data)
        )

        return CoverageResults(
            line_coverage=line_coverage,
            branch_coverage=branch_coverage,
            function_coverage=function_coverage,
            lines_covered=lines_covered,
            lines_total=lines_total,
            branches_covered=branches_covered,
            branches_total=branches_total,
            functions_covered=functions_covered,
            functions_total=functions_total,
            complexity=complexity,
            files=files_data
        )

    def parse_file(self, file_path: Union[str, Path]) -> CoverageResults:
        """
        Parseia arquivo Cobertura XML.

        Args:
            file_path: Caminho para o arquivo

        Returns:
            CoverageResults
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f'Cobertura XML file not found: {file_path}')

        content = path.read_text(encoding='utf-8', errors='replace')
        return self.parse(content)


class LCOVParser:
    """
    Parser para LCOV format.

    Compativel com:
    - Jest coverage
    - Istanbul/nyc
    - lcov/genhtml
    """

    def __init__(self):
        self.logger = logger.bind(parser='lcov')

    def parse(self, content: Union[str, bytes]) -> CoverageResults:
        """
        Parseia conteudo LCOV.

        Args:
            content: LCOV string ou bytes

        Returns:
            CoverageResults
        """
        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='replace')

        lines_found = 0
        lines_hit = 0
        functions_found = 0
        functions_hit = 0
        branches_found = 0
        branches_hit = 0
        files_data: List[Dict[str, Any]] = []

        current_file = None
        file_lines_found = 0
        file_lines_hit = 0
        file_functions_found = 0
        file_functions_hit = 0
        file_branches_found = 0
        file_branches_hit = 0

        for line in content.strip().split('\n'):
            line = line.strip()

            if line.startswith('SF:'):
                # Start of file record
                if current_file:
                    # Save previous file
                    files_data.append({
                        'filename': current_file,
                        'lines_found': file_lines_found,
                        'lines_hit': file_lines_hit,
                        'functions_found': file_functions_found,
                        'functions_hit': file_functions_hit,
                        'branches_found': file_branches_found,
                        'branches_hit': file_branches_hit,
                        'line_rate': (file_lines_hit / file_lines_found * 100) if file_lines_found > 0 else 0
                    })
                current_file = line[3:]
                file_lines_found = 0
                file_lines_hit = 0
                file_functions_found = 0
                file_functions_hit = 0
                file_branches_found = 0
                file_branches_hit = 0

            elif line.startswith('LF:'):
                # Lines Found
                try:
                    file_lines_found = int(line[3:])
                    lines_found += file_lines_found
                except ValueError:
                    pass

            elif line.startswith('LH:'):
                # Lines Hit
                try:
                    file_lines_hit = int(line[3:])
                    lines_hit += file_lines_hit
                except ValueError:
                    pass

            elif line.startswith('FNF:'):
                # Functions Found
                try:
                    file_functions_found = int(line[4:])
                    functions_found += file_functions_found
                except ValueError:
                    pass

            elif line.startswith('FNH:'):
                # Functions Hit
                try:
                    file_functions_hit = int(line[4:])
                    functions_hit += file_functions_hit
                except ValueError:
                    pass

            elif line.startswith('BRF:'):
                # Branches Found
                try:
                    file_branches_found = int(line[4:])
                    branches_found += file_branches_found
                except ValueError:
                    pass

            elif line.startswith('BRH:'):
                # Branches Hit
                try:
                    file_branches_hit = int(line[4:])
                    branches_hit += file_branches_hit
                except ValueError:
                    pass

            elif line == 'end_of_record':
                # End of file record
                if current_file:
                    files_data.append({
                        'filename': current_file,
                        'lines_found': file_lines_found,
                        'lines_hit': file_lines_hit,
                        'functions_found': file_functions_found,
                        'functions_hit': file_functions_hit,
                        'branches_found': file_branches_found,
                        'branches_hit': file_branches_hit,
                        'line_rate': (file_lines_hit / file_lines_found * 100) if file_lines_found > 0 else 0
                    })
                    current_file = None

        # Calculate percentages
        line_coverage = (lines_hit / lines_found * 100) if lines_found > 0 else 0.0
        function_coverage = (functions_hit / functions_found * 100) if functions_found > 0 else None
        branch_coverage = (branches_hit / branches_found * 100) if branches_found > 0 else None

        self.logger.info(
            'lcov_parsed',
            line_coverage=line_coverage,
            function_coverage=function_coverage,
            branch_coverage=branch_coverage,
            files=len(files_data)
        )

        return CoverageResults(
            line_coverage=line_coverage,
            branch_coverage=branch_coverage,
            function_coverage=function_coverage,
            lines_covered=lines_hit,
            lines_total=lines_found,
            branches_covered=branches_hit,
            branches_total=branches_found,
            functions_covered=functions_hit,
            functions_total=functions_found,
            files=files_data
        )

    def parse_file(self, file_path: Union[str, Path]) -> CoverageResults:
        """
        Parseia arquivo LCOV.

        Args:
            file_path: Caminho para o arquivo

        Returns:
            CoverageResults
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f'LCOV file not found: {file_path}')

        content = path.read_text(encoding='utf-8', errors='replace')
        return self.parse(content)


def parse_test_report(
    content: Union[str, bytes],
    format: str = 'junit'
) -> TestResults:
    """
    Conveniencia para parsear relatorio de teste.

    Args:
        content: Conteudo do relatorio
        format: Formato ('junit', 'xunit')

    Returns:
        TestResults
    """
    parser = JUnitXMLParser()
    return parser.parse(content)


def parse_coverage_report(
    content: Union[str, bytes],
    format: str = 'cobertura'
) -> CoverageResults:
    """
    Conveniencia para parsear relatorio de coverage.

    Args:
        content: Conteudo do relatorio
        format: Formato ('cobertura', 'lcov')

    Returns:
        CoverageResults
    """
    if format == 'lcov':
        parser = LCOVParser()
    else:
        parser = CoberturaXMLParser()
    return parser.parse(content)


def detect_report_format(content: Union[str, bytes]) -> str:
    """
    Detecta formato do relatorio automaticamente.

    Args:
        content: Conteudo do relatorio

    Returns:
        Nome do formato detectado
    """
    if isinstance(content, bytes):
        content = content.decode('utf-8', errors='replace')

    content_lower = content.strip().lower()

    # JUnit XML
    if '<?xml' in content_lower and ('<testsuite' in content_lower or '<testsuites' in content_lower):
        return 'junit'

    # Cobertura XML
    if '<?xml' in content_lower and '<coverage' in content_lower:
        return 'cobertura'

    # LCOV
    if content.startswith('TN:') or content.startswith('SF:'):
        return 'lcov'

    return 'unknown'
