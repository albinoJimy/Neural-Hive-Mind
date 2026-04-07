"""
Optimizer MCP Server - Servidor MCP para análise de performance de código.

Expõe ferramentas para:
- Análise de complexidade ciclomática
- Detecção de code smells
- Análise de tamanho de funções
- Identificação de código duplicado
- Recomendações de otimização
"""

import ast
import os
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum

from fastmcp import FastMCP
from starlette.responses import JSONResponse
from starlette.routing import Route

# Criar servidor MCP
mcp = FastMCP(name="Optimizer MCP Server")


# Health check handler
async def health_check(request):
    return JSONResponse({"status": "healthy", "server": "Optimizer MCP Server", "version": "1.0.0"})


# Obter app HTTP do FastMCP (http_app é um método que precisa ser chamado)
http_app = mcp.http_app()

# Adicionar rota de health check ao app HTTP
http_app.routes.append(Route("/health", health_check, methods=["GET"]))


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
        # Usar split('\n') em vez de splitlines() para contar linhas vazias no final
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

    def __init__(self, base_path: str = "/repo"):
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
            metrics.code_lines = sum(1 for l in lines if l.strip())
            metrics.blank_lines = sum(1 for l in lines if not l.strip())
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
        base_path = os.environ.get("OPTIMIZER_BASE_PATH", "/repo")
        _optimizer = CodeOptimizer(base_path=base_path)
    return _optimizer


# ============ MCP Tools ============


@mcp.tool()
async def analyze_file_performance(file_path: str) -> dict[str, Any]:
    """
    Analisa performance de um arquivo específico.

    Args:
        file_path: Caminho do arquivo (relativo ao base path)

    Returns:
        Métricas e issues do arquivo
    """
    optimizer = get_optimizer()

    try:
        metrics, issues = optimizer.analyze_file(file_path)

        # Converter issues para dict
        issues_dict = [
            {
                "file": issue.file_path,
                "line": issue.line,
                "column": issue.column,
                "severity": issue.severity.value,
                "category": issue.category,
                "message": issue.message,
                "suggestion": issue.suggestion,
            }
            for issue in issues
        ]

        return {
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
            "issues": issues_dict,
            "issue_count": len(issues_dict),
            "summary": {
                "complexity": (
                    "high"
                    if metrics.max_complexity > 20
                    else "medium" if metrics.max_complexity > 10 else "low"
                ),
                "maintainability": (
                    "good"
                    if len(issues_dict) < 5
                    else "needs_attention" if len(issues_dict) < 10 else "poor"
                ),
            },
        }

    except FileNotFoundError as e:
        return {
            "error": str(e),
            "file_path": file_path,
            "issues": [],
            "metrics": {},
        }


@mcp.tool()
async def analyze_directory_performance(
    path: str = ".",
    pattern: str = "*.py",
    exclude_dirs: str = "node_modules,.git,__pycache__,venv,.venv,dist,build",
) -> dict[str, Any]:
    """
    Analisa performance de todos os arquivos de um diretório.

    Args:
        path: Caminho do diretório
        pattern: Padrão de arquivos (ex: *.py, **/*.py)
        exclude_dirs: Diretórios a excluir (separados por vírgula)

    Returns:
        Análise agregada do diretório
    """
    optimizer = get_optimizer()
    exclude_list = [d.strip() for d in exclude_dirs.split(",") if d.strip()]

    try:
        result = optimizer.analyze_directory(
            path=path,
            pattern=pattern,
            exclude_dirs=exclude_list,
        )

        # Converter issues para dict
        issues_dict = [
            {
                "file": issue.file_path,
                "line": issue.line,
                "column": issue.column,
                "severity": issue.severity.value,
                "category": issue.category,
                "message": issue.message,
                "suggestion": issue.suggestion,
            }
            for issue in result["issues"]
        ]

        result["issues"] = issues_dict
        return result

    except FileNotFoundError as e:
        return {
            "error": str(e),
            "path": path,
            "summary": {},
            "issues": [],
        }


@mcp.tool()
async def get_optimization_recommendations(
    path: str = ".",
    pattern: str = "*.py",
) -> dict[str, Any]:
    """
    Gera recomendações de otimização para o projeto.

    Args:
        path: Caminho do diretório
        pattern: Padrão de arquivos

    Returns:
        Lista de recomendações priorizadas
    """
    optimizer = get_optimizer()

    try:
        analysis = await analyze_directory_performance(path=path, pattern=pattern)

        if "error" in analysis:
            return {
                "error": analysis["error"],
                "recommendations": [],
            }

        recommendations = optimizer.generate_recommendations(analysis)

        # Priorizar
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        recommendations.sort(key=lambda r: priority_order.get(r["priority"], 4))

        return {
            "path": path,
            "recommendations": recommendations,
            "total_recommendations": len(recommendations),
            "summary": {
                "high_priority": sum(
                    1 for r in recommendations if r["priority"] in ("critical", "high")
                ),
                "medium_priority": sum(1 for r in recommendations if r["priority"] == "medium"),
                "low_priority": sum(1 for r in recommendations if r["priority"] == "low"),
            },
        }

    except Exception as e:
        return {
            "error": str(e),
            "recommendations": [],
        }


@mcp.tool()
async def detect_code_smells(
    path: str = ".",
    severity: str = "medium",
) -> dict[str, Any]:
    """
    Detecta code smells no projeto.

    Args:
        path: Caminho do diretório
        severity: Nível mínimo de severidade (low, medium, high, critical)

    Returns:
        Code smells encontrados por categoria
    """
    optimizer = get_optimizer()

    try:
        analysis = await analyze_directory_performance(path=path)

        if "error" in analysis:
            return {"error": analysis["error"]}

        # Filtrar por severidade
        severity_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        min_severity = severity_order.get(severity, 2)

        filtered_issues = [
            issue
            for issue in analysis["issues"]
            if severity_order.get(issue["severity"], 0) >= min_severity
        ]

        # Agrupar por categoria
        by_category: dict[str, list[dict]] = defaultdict(list)
        for issue in filtered_issues:
            by_category[issue["category"]].append(issue)

        return {
            "path": path,
            "severity_filter": severity,
            "total_smells": len(filtered_issues),
            "by_category": {
                cat: {
                    "count": len(issues),
                    "sample": issues[:5],  # Mostrar até 5 exemplos
                }
                for cat, issues in by_category.items()
            },
            "all_smells": filtered_issues[:50],  # Limitar a 50
        }

    except Exception as e:
        return {
            "error": str(e),
            "code_smells": {},
        }


@mcp.tool()
async def health_check() -> dict[str, str]:
    """
    Verifica saúde do servidor Optimizer MCP.

    Returns:
        Status de saúde
    """
    return {
        "status": "healthy",
        "server": "Optimizer MCP Server",
        "version": "1.0.0",
    }


# ============ Main ============

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        os.environ["OPTIMIZER_BASE_PATH"] = sys.argv[1]

    # Executar servidor com uvicorn
    import uvicorn

    port = int(os.getenv("PORT", "3000"))
    # Usar o sse_app diretamente que já inclui as rotas MCP
    uvicorn.run(sse_app, host="0.0.0.0", port=port)
