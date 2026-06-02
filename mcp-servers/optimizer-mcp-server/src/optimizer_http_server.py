"""
Optimizer MCP HTTP Server - Servidor HTTP para análise de performance de código.

Expõe endpoints REST para:
- Análise de complexidade ciclomática
- Detecção de code smells
- Análise de tamanho de funções
- Recomendações de otimização

Este servidor HTTP expõe as mesmas funcionalidades do Optimizer MCP Server
mas usando endpoints REST simples em vez do protocolo MCP stdio.
"""

import ast
import json
import os
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass
from collections import defaultdict
from enum import Enum
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse


# ============ Models ============


class Severity(Enum):
    """Níveis de severidade de problemas."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Issue:
    """Representa um problema encontrado."""

    file_path: str
    line: int
    column: int
    severity: Severity
    category: str
    message: str
    suggestion: Optional[str] = None


@dataclass
class FileMetrics:
    """Métricas de um arquivo."""

    path: str
    total_lines: int = 0
    code_lines: int = 0
    comment_lines: int = 0
    blank_lines: int = 0
    functions: int = 0
    classes: int = 0
    avg_function_length: float = 0.0
    max_function_length: int = 0
    max_complexity: int = 0


class PythonAnalyzer(ast.NodeVisitor):
    """
    Analisador AST para código Python.

    Calcula métricas de complexidade e detecta problemas.
    """

    def __init__(self, file_path: str, source_code: str):
        """
        Inicializa analisador.

        Args:
            file_path: Caminho do arquivo
            source_code: Código fonte
        """
        self.file_path = file_path
        self.source_code = source_code
        self.lines = source_code.splitlines()

        # Métricas
        self.functions: list[dict[str, Any]] = []
        self.classes: list[dict[str, Any]] = []
        self.imports: list[str] = []
        self.complexity: dict[str, int] = defaultdict(int)

        # Issues
        self.issues: list[Issue] = []

        # Estado atual
        self.current_class: Optional[str] = None
        self.current_function: Optional[str] = None
        self.nesting_level = 0

    def analyze(self) -> FileMetrics:
        """
        Executa análise completa.

        Returns:
            FileMetrics com resultados
        """
        try:
            tree = ast.parse(self.source_code)
            self.visit(tree)
        except SyntaxError as e:
            self.issues.append(
                Issue(
                    file_path=self.file_path,
                    line=e.lineno or 0,
                    column=e.offset or 0,
                    severity=Severity.HIGH,
                    category="syntax",
                    message=f"Syntax error: {e.msg}",
                )
            )

        metrics = FileMetrics(path=self.file_path)
        metrics.total_lines = len(self.source_code.split("\n"))
        metrics.code_lines = self._count_code_lines()
        metrics.comment_lines = self._count_comment_lines()
        metrics.blank_lines = self._count_blank_lines()
        metrics.functions = len(self.functions)
        metrics.classes = len(self.classes)

        if self.functions:
            lengths = [f["length"] for f in self.functions]
            metrics.avg_function_length = sum(lengths) / len(lengths)
            metrics.max_function_length = max(lengths)

        if self.complexity:
            metrics.max_complexity = max(self.complexity.values())

        return metrics

    def _count_code_lines(self) -> int:
        """Conta linhas de código."""
        count = 0
        for line in self.lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                count += 1
        return count

    def _count_comment_lines(self) -> int:
        """Conta linhas de comentário."""
        count = 0
        for line in self.lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                count += 1
        return count

    def _count_blank_lines(self) -> int:
        """Conta linhas em branco."""
        return sum(1 for line in self.lines if not line.strip())

    # ============ AST Visitors ============

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visita definição de função."""
        func_name = node.name
        self.current_function = func_name

        # Calcular complexidade ciclomática (simplificada)
        complexity = 1  # Base
        complexity += sum(
            1
            for _ in ast.walk(node)
            if isinstance(_, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With))
        )
        self.complexity[func_name] = complexity

        # Calcular comprimento da função
        start_line = node.lineno
        end_line = node.end_lineno if hasattr(node, "end_lineno") else start_line
        func_length = end_line - start_line + 1

        func_info = {
            "name": func_name,
            "lineno": start_line,
            "end_lineno": end_line,
            "length": func_length,
            "complexity": complexity,
            "args_count": len(node.args.args),
            "class": self.current_class,
        }

        self.functions.append(func_info)

        # Detectar problemas
        if func_length > 50:
            self.issues.append(
                Issue(
                    file_path=self.file_path,
                    line=start_line,
                    column=node.col_offset or 0,
                    severity=Severity.MEDIUM if func_length < 100 else Severity.HIGH,
                    category="function_length",
                    message=f"Function {func_name} is too long ({func_length} lines)",
                    suggestion="Consider splitting into smaller functions",
                )
            )

        if complexity > 10:
            self.issues.append(
                Issue(
                    file_path=self.file_path,
                    line=start_line,
                    column=node.col_offset or 0,
                    severity=Severity.MEDIUM if complexity < 20 else Severity.HIGH,
                    category="complexity",
                    message=f"Function {func_name} has high cyclomatic complexity ({complexity})",
                    suggestion="Consider simplifying logic or extracting methods",
                )
            )

        if len(node.args.args) > 7:
            self.issues.append(
                Issue(
                    file_path=self.file_path,
                    line=start_line,
                    column=node.col_offset or 0,
                    severity=Severity.LOW,
                    category="parameter_count",
                    message=f"Function {func_name} has too many parameters ({len(node.args.args)})",
                    suggestion="Consider using a dataclass or configuration object",
                )
            )

        self.nesting_level += 1
        self.generic_visit(node)
        self.nesting_level -= 1
        self.current_function = None

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """Visita definição de função assíncrona."""
        # Tratar como função normal
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        """Visita definição de classe."""
        class_name = node.name
        self.current_class = class_name

        # Contar métodos
        methods = [
            n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]

        class_info = {
            "name": class_name,
            "lineno": node.lineno,
            "methods": methods,
            "method_count": len(methods),
        }

        self.classes.append(class_info)

        # Detectar classe muito grande
        class_length = 0
        if hasattr(node, "end_lineno"):
            class_length = node.end_lineno - node.lineno + 1

        if class_length > 300:
            self.issues.append(
                Issue(
                    file_path=self.file_path,
                    line=node.lineno,
                    column=node.col_offset or 0,
                    severity=Severity.MEDIUM,
                    category="class_length",
                    message=f"Class {class_name} is too long ({class_length} lines)",
                    suggestion="Consider splitting into smaller classes",
                )
            )

        if len(methods) > 20:
            self.issues.append(
                Issue(
                    file_path=self.file_path,
                    line=node.lineno,
                    column=node.col_offset or 0,
                    severity=Severity.MEDIUM,
                    category="class_methods",
                    message=f"Class {class_name} has too many methods ({len(methods)})",
                    suggestion="Consider splitting into smaller classes",
                )
            )

        self.generic_visit(node)
        self.current_class = None

    def visit_Import(self, node: ast.Import):
        """Visita import."""
        for alias in node.names:
            self.imports.append(alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Visita import from."""
        if node.module:
            self.imports.append(node.module)

    def visit_For(self, node: ast.For):
        """Visita loop for - detecta nesting profundo."""
        if self.nesting_level >= 3:
            self.issues.append(
                Issue(
                    file_path=self.file_path,
                    line=node.lineno,
                    column=node.col_offset or 0,
                    severity=Severity.LOW,
                    category="nesting",
                    message=f"Deep nesting detected (level {self.nesting_level + 1})",
                    suggestion="Consider extracting to a function",
                )
            )

        self.nesting_level += 1
        self.generic_visit(node)
        self.nesting_level -= 1

    def visit_While(self, node: ast.While):
        """Visita loop while."""
        if self.nesting_level >= 3:
            self.issues.append(
                Issue(
                    file_path=self.file_path,
                    line=node.lineno,
                    column=node.col_offset or 0,
                    severity=Severity.LOW,
                    category="nesting",
                    message=f"Deep nesting detected (level {self.nesting_level + 1})",
                    suggestion="Consider extracting to a function",
                )
            )

        self.nesting_level += 1
        self.generic_visit(node)
        self.nesting_level -= 1

    def visit_If(self, node: ast.If):
        """Visita if - detecta múltiplas condições."""
        # Contar condições elif
        conditions = 1
        current = node
        while current.orelse:
            for stmt in current.orelse:
                if isinstance(stmt, ast.If):
                    conditions += 1
                    current = stmt
                    break
            else:
                break

        if conditions >= 5:
            self.issues.append(
                Issue(
                    file_path=self.file_path,
                    line=node.lineno,
                    column=node.col_offset or 0,
                    severity=Severity.MEDIUM,
                    category="complex_condition",
                    message=f"Complex if/elif chain ({conditions} conditions)",
                    suggestion="Consider using a dictionary lookup or match statement",
                )
            )

        self.generic_visit(node)

    def visit_Try(self, node: ast.Try):
        """Visita try/except - detecta bare except."""
        for handler in node.handlers:
            if handler.type is None:
                self.issues.append(
                    Issue(
                        file_path=self.file_path,
                        line=handler.lineno,
                        column=handler.col_offset or 0,
                        severity=Severity.MEDIUM,
                        category="bare_except",
                        message="Bare except clause catches all exceptions",
                        suggestion="Specify the exception type to catch",
                    )
                )

        self.generic_visit(node)


class CodeOptimizer:
    """
    Otimizador de código que analisa e gera recomendações.
    """

    def __init__(self, base_path: str = "/app"):
        """
        Inicializa otimizador.

        Args:
            base_path: Caminho base para análise
        """
        self.base_path = Path(base_path)

    def analyze_file(self, file_path: str) -> tuple[FileMetrics, list[Issue]]:
        """
        Analisa um arquivo específico.

        Args:
            file_path: Caminho relativo do arquivo

        Returns:
            Tupla (metrics, issues)
        """
        full_path = self.base_path / file_path

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")

        source_code = full_path.read_text(encoding="utf-8", errors="ignore")

        if file_path.endswith(".py"):
            analyzer = PythonAnalyzer(str(full_path), source_code)
            metrics = analyzer.analyze()
            issues = analyzer.issues
        else:
            # Para não-Python, retornar métricas básicas
            metrics = FileMetrics(path=file_path)
            lines = source_code.splitlines()
            metrics.total_lines = len(lines)
            metrics.code_lines = sum(1 for line in lines if line.strip())
            metrics.blank_lines = sum(1 for line in lines if not line.strip())
            issues = []

        return metrics, issues

    def analyze_directory(
        self,
        path: str = ".",
        pattern: str = "*.py",
        exclude_dirs: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Analisa todos os arquivos de um diretório.

        Args:
            path: Caminho do diretório
            pattern: Padrão de arquivos
            exclude_dirs: Diretórios a excluir

        Returns:
            Dicionário com resultados agregados
        """
        if exclude_dirs is None:
            exclude_dirs = [
                "node_modules",
                ".git",
                "__pycache__",
                "venv",
                ".venv",
                "dist",
                "build",
            ]

        full_path = self.base_path / path
        if not full_path.exists():
            raise FileNotFoundError(f"Path not found: {full_path}")

        all_metrics: list[FileMetrics] = []
        all_issues: list[Issue] = []

        for root, dirs, files in os.walk(full_path):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            for file in files:
                if not file.endswith(".py"):
                    continue

                file_path = Path(root) / file
                rel_path = str(file_path.relative_to(self.base_path))

                try:
                    metrics, issues = self.analyze_file(rel_path)
                    all_metrics.append(metrics)
                    all_issues.extend(issues)
                except Exception as e:
                    # Continuar mesmo se houver erro em um arquivo
                    all_issues.append(
                        Issue(
                            file_path=rel_path,
                            line=0,
                            column=0,
                            severity=Severity.LOW,
                            category="analysis_error",
                            message=f"Failed to analyze: {e}",
                        )
                    )

        # Agregar resultados
        total_files = len(all_metrics)
        total_issues = len(all_issues)
        total_lines = sum(m.total_lines for m in all_metrics)
        total_functions = sum(m.functions for m in all_metrics)

        # Contar issues por severidade
        severity_counts = defaultdict(int)
        for issue in all_issues:
            severity_counts[issue.severity.value] += 1

        # Contar issues por categoria
        category_counts = defaultdict(int)
        for issue in all_issues:
            category_counts[issue.category] += 1

        # Top arquivos com mais issues
        issues_by_file = defaultdict(list)
        for issue in all_issues:
            issues_by_file[issue.file_path].append(issue)

        top_files = sorted(issues_by_file.items(), key=lambda x: len(x[1]), reverse=True)[:10]

        return {
            "summary": {
                "total_files": total_files,
                "total_lines": total_lines,
                "total_functions": total_functions,
                "total_issues": total_issues,
                "avg_issues_per_file": total_issues / total_files if total_files > 0 else 0,
            },
            "severity_breakdown": dict(severity_counts),
            "category_breakdown": dict(category_counts),
            "top_files": [{"path": path, "issue_count": len(issues)} for path, issues in top_files],
            "issues": all_issues[:100],  # Limitar a 100 issues
        }

    def generate_recommendations(
        self,
        analysis_result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Gera recomendações baseadas na análise.

        Args:
            analysis_result: Resultado de analyze_directory

        Returns:
            Lista de recomendações
        """
        recommendations = []

        severity = analysis_result["severity_breakdown"]
        categories = analysis_result["category_breakdown"]

        # Alta complexidade
        if severity.get("high", 0) + severity.get("critical", 0) > 5:
            recommendations.append(
                {
                    "priority": "high",
                    "category": "complexity",
                    "title": "Reduce Code Complexity",
                    "description": f"{severity.get('high', 0) + severity.get('critical', 0)} high/critical complexity issues found",
                    "actions": [
                        "Extract complex methods into smaller functions",
                        "Use strategy pattern to replace complex conditionals",
                        "Consider using guard clauses to reduce nesting",
                    ],
                }
            )

        # Funções muito longas
        if categories.get("function_length", 0) > 0:
            recommendations.append(
                {
                    "priority": "medium",
                    "category": "function_length",
                    "title": "Refactor Long Functions",
                    "description": f"{categories['function_length']} functions are too long",
                    "actions": [
                        "Split functions longer than 50 lines",
                        "Extract logic into separate helper functions",
                        "Use early returns to reduce nesting",
                    ],
                }
            )

        # Classes muito grandes
        if categories.get("class_length", 0) > 0:
            recommendations.append(
                {
                    "priority": "medium",
                    "category": "class_length",
                    "title": "Break Down Large Classes",
                    "description": f"{categories['class_length']} classes are too long",
                    "actions": [
                        "Apply Single Responsibility Principle",
                        "Extract related methods into separate classes",
                        "Use composition over inheritance",
                    ],
                }
            )

        # Nested code
        if categories.get("nesting", 0) > 10:
            recommendations.append(
                {
                    "priority": "low",
                    "category": "nesting",
                    "title": "Reduce Nesting Depth",
                    "description": f"{categories['nesting']} instances of deep nesting found",
                    "actions": [
                        "Extract nested logic into separate functions",
                        "Use early return/continue patterns",
                        "Consider using guard clauses",
                    ],
                }
            )

        # Bare except
        if categories.get("bare_except", 0) > 0:
            recommendations.append(
                {
                    "priority": "medium",
                    "category": "error_handling",
                    "title": "Fix Bare Except Clauses",
                    "description": f"{categories['bare_except']} bare except clauses found",
                    "actions": [
                        "Specify exception types to catch",
                        "Use logging for unexpected errors",
                        "Consider re-raising with context",
                    ],
                }
            )

        return recommendations


# Instância global
_optimizer: Optional[CodeOptimizer] = None


def get_optimizer() -> CodeOptimizer:
    """Retorna instância do otimizador."""
    global _optimizer
    if _optimizer is None:
        base_path = os.getenv("OPTIMIZER_BASE_PATH", "/app")
        _optimizer = CodeOptimizer(base_path=base_path)
    return _optimizer


def _issue_to_dict(issue: Issue) -> dict[str, Any]:
    """Converte Issue para dict."""
    return {
        "file": issue.file_path,
        "line": issue.line,
        "column": issue.column,
        "severity": issue.severity.value,
        "category": issue.category,
        "message": issue.message,
        "suggestion": issue.suggestion,
    }


# ============ HTTP Server ============


class OptimizerHTTPRequestHandler(BaseHTTPRequestHandler):
    """Handler HTTP para Optimizer MCP Server."""

    optimizer = None

    def _set_json_headers(self):
        """Define headers para resposta JSON."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

    def do_GET(self):
        """Handler para requisições GET."""
        parsed_path = urlparse(self.path)
        path_parts = parsed_path.path.strip("/").split("/")

        # Health check
        if path_parts[0] == "health" or path_parts[0] == "":
            self._set_json_headers()
            self.wfile.write(
                json.dumps(
                    {"status": "healthy", "server": "Optimizer MCP HTTP Server", "version": "1.0.0"}
                ).encode()
            )
            return

        # /tools - Lista ferramentas disponíveis
        if path_parts[0] == "tools":
            self._set_json_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "tools": [
                            {
                                "name": "analyze_file_performance",
                                "description": "Analyze single file performance",
                            },
                            {
                                "name": "analyze_directory_performance",
                                "description": "Analyze directory performance",
                            },
                            {
                                "name": "get_optimization_recommendations",
                                "description": "Get optimization recommendations",
                            },
                            {"name": "detect_code_smells", "description": "Detect code smells"},
                        ]
                    }
                ).encode()
            )
            return

        # /analyze-file - Analisar arquivo
        if path_parts[0] == "analyze-file":
            query = parse_qs(parsed_path.query)
            file_path = query.get("path", [""])[0]

            if not self.optimizer:
                base_path = os.getenv("OPTIMIZER_BASE_PATH", "/app")
                self.optimizer = CodeOptimizer(base_path=base_path)

            try:
                metrics, issues = self.optimizer.analyze_file(file_path)

                result = {
                    "file_path": file_path,
                    "metrics": {
                        "total_lines": metrics.total_lines,
                        "code_lines": metrics.code_lines,
                        "comment_lines": metrics.comment_lines,
                        "blank_lines": metrics.blank_lines,
                        "functions": metrics.functions,
                        "classes": metrics.classes,
                        "avg_function_length": metrics.avg_function_length,
                        "max_function_length": metrics.max_function_length,
                        "max_complexity": metrics.max_complexity,
                    },
                    "issues": [_issue_to_dict(i) for i in issues],
                    "issue_count": len(issues),
                    "summary": {
                        "complexity": (
                            "high"
                            if metrics.max_complexity > 20
                            else "medium"
                            if metrics.max_complexity > 10
                            else "low"
                        ),
                        "maintainability": (
                            "good"
                            if len(issues) < 5
                            else "needs_attention"
                            if len(issues) < 10
                            else "poor"
                        ),
                    },
                }
                self._set_json_headers()
                self.wfile.write(json.dumps(result).encode())
            except FileNotFoundError as e:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e), "file_path": file_path}).encode())
            return

        # /analyze-directory - Analisar diretório
        if path_parts[0] == "analyze-directory":
            query = parse_qs(parsed_path.query)
            path = query.get("path", ["."])[0]
            exclude_dirs = query.get("exclude_dirs", [""])[0]

            if not self.optimizer:
                base_path = os.getenv("OPTIMIZER_BASE_PATH", "/app")
                self.optimizer = CodeOptimizer(base_path=base_path)

            exclude_list = [d.strip() for d in exclude_dirs.split(",") if d.strip()]

            try:
                result = self.optimizer.analyze_directory(
                    path=path,
                    pattern="*.py",
                    exclude_dirs=exclude_list,
                )
                result["issues"] = [_issue_to_dict(i) for i in result.get("issues", [])]
                self._set_json_headers()
                self.wfile.write(json.dumps(result).encode())
            except FileNotFoundError as e:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e), "path": path}).encode())
            return

        # /recommendations - Recomendações de otimização
        if path_parts[0] == "recommendations":
            query = parse_qs(parsed_path.query)
            path = query.get("path", ["."])[0]

            if not self.optimizer:
                base_path = os.getenv("OPTIMIZER_BASE_PATH", "/app")
                self.optimizer = CodeOptimizer(base_path=base_path)

            try:
                analysis = self.optimizer.analyze_directory(path=path)
                recommendations = self.optimizer.generate_recommendations(analysis)

                # Priorizar
                priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
                recommendations.sort(key=lambda r: priority_order.get(r["priority"], 4))

                result = {
                    "path": path,
                    "recommendations": recommendations,
                    "total_recommendations": len(recommendations),
                    "summary": {
                        "high_priority": sum(
                            1 for r in recommendations if r["priority"] in ("critical", "high")
                        ),
                        "medium_priority": sum(
                            1 for r in recommendations if r["priority"] == "medium"
                        ),
                        "low_priority": sum(1 for r in recommendations if r["priority"] == "low"),
                    },
                }
                self._set_json_headers()
                self.wfile.write(json.dumps(result).encode())
            except FileNotFoundError as e:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
            return

        # /code-smells - Detectar code smells
        if path_parts[0] == "code-smells":
            query = parse_qs(parsed_path.query)
            path = query.get("path", ["."])[0]
            severity = query.get("severity", ["medium"])[0]

            if not self.optimizer:
                base_path = os.getenv("OPTIMIZER_BASE_PATH", "/app")
                self.optimizer = CodeOptimizer(base_path=base_path)

            try:
                analysis = self.optimizer.analyze_directory(path=path)

                # Filtrar por severidade
                severity_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
                min_severity = severity_order.get(severity, 2)

                all_issues = [_issue_to_dict(i) for i in analysis.get("issues", [])]
                filtered_issues = [
                    issue
                    for issue in all_issues
                    if severity_order.get(issue["severity"], 0) >= min_severity
                ]

                # Agrupar por categoria
                by_category: dict[str, list[dict]] = defaultdict(list)
                for issue in filtered_issues:
                    by_category[issue["category"]].append(issue)

                result = {
                    "path": path,
                    "severity_filter": severity,
                    "total_smells": len(filtered_issues),
                    "by_category": {
                        cat: {
                            "count": len(issues),
                            "sample": issues[:5],
                        }
                        for cat, issues in by_category.items()
                    },
                    "all_smells": filtered_issues[:50],
                }
                self._set_json_headers()
                self.wfile.write(json.dumps(result).encode())
            except FileNotFoundError as e:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
            return

        # 404
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error": "Not found"}')

    def do_POST(self):
        """Handler para requisições POST."""
        parsed_path = urlparse(self.path)
        path_parts = parsed_path.path.strip("/").split("/")

        # /execute - Executar ferramenta
        if path_parts[0] == "execute":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                try:
                    data = json.loads(self.rfile.read(content_length).decode())
                except Exception:
                    data = {}
            else:
                data = {}

            tool = data.get("tool")
            params = data.get("params", {})

            if not self.optimizer:
                base_path = os.getenv("OPTIMIZER_BASE_PATH", "/app")
                self.optimizer = CodeOptimizer(base_path=base_path)

            result = {}
            if tool == "analyze_file_performance":
                file_path = params.get("file_path", "")
                try:
                    metrics, issues = self.optimizer.analyze_file(file_path)
                    result = {
                        "file_path": file_path,
                        "metrics": {
                            "total_lines": metrics.total_lines,
                            "code_lines": metrics.code_lines,
                            "comment_lines": metrics.comment_lines,
                            "blank_lines": metrics.blank_lines,
                            "functions": metrics.functions,
                            "classes": metrics.classes,
                            "avg_function_length": metrics.avg_function_length,
                            "max_function_length": metrics.max_function_length,
                            "max_complexity": metrics.max_complexity,
                        },
                        "issues": [_issue_to_dict(i) for i in issues],
                        "issue_count": len(issues),
                    }
                except FileNotFoundError as e:
                    result = {"error": str(e), "file_path": file_path}
            elif tool == "analyze_directory_performance":
                path = params.get("path", ".")
                exclude_dirs_str = params.get("exclude_dirs", "")
                exclude_list = [d.strip() for d in exclude_dirs_str.split(",") if d.strip()]
                try:
                    analysis = self.optimizer.analyze_directory(
                        path=path, pattern="*.py", exclude_dirs=exclude_list
                    )
                    analysis["issues"] = [_issue_to_dict(i) for i in analysis.get("issues", [])]
                    result = analysis
                except FileNotFoundError as e:
                    result = {"error": str(e), "path": path}
            elif tool == "get_optimization_recommendations":
                path = params.get("path", ".")
                try:
                    analysis = self.optimizer.analyze_directory(path=path)
                    recommendations = self.optimizer.generate_recommendations(analysis)
                    result = {
                        "path": path,
                        "recommendations": recommendations,
                        "total_recommendations": len(recommendations),
                    }
                except FileNotFoundError as e:
                    result = {"error": str(e)}
            elif tool == "detect_code_smells":
                path = params.get("path", ".")
                severity = params.get("severity", "medium")
                try:
                    analysis = self.optimizer.analyze_directory(path=path)
                    severity_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
                    min_severity = severity_order.get(severity, 2)
                    all_issues = [_issue_to_dict(i) for i in analysis.get("issues", [])]
                    filtered_issues = [
                        i
                        for i in all_issues
                        if severity_order.get(i["severity"], 0) >= min_severity
                    ]
                    result = {
                        "path": path,
                        "total_smells": len(filtered_issues),
                        "smells": filtered_issues[:50],
                    }
                except FileNotFoundError as e:
                    result = {"error": str(e)}
            else:
                result = {"error": f"Unknown tool: {tool}"}

            self._set_json_headers()
            self.wfile.write(json.dumps(result).encode())
            return

        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error": "Not found"}')

    def log_message(self, format, *args):
        """Log mensagem (opcional)."""
        pass


def run_server(port: int = 8080):
    """Executa servidor HTTP."""
    server_address = ("", port)
    httpd = HTTPServer(server_address, OptimizerHTTPRequestHandler)
    print(f"Optimizer HTTP Server running on port {port}")
    httpd.serve_forever()


if __name__ == "__main__":
    import sys

    # Configurar base path via argumento
    if len(sys.argv) > 1:
        os.environ["OPTIMIZER_BASE_PATH"] = sys.argv[1]

    port = int(os.getenv("PORT", "8080"))
    run_server(port)
