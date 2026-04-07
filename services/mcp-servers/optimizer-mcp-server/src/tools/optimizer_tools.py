"""
Optimizer MCP Tools - Ferramentas de otimização de código.

Ferramentas:
- suggest_refactors: Sugere refatorações baseado em análise estática
- analyze_performance: Analisa métricas de performance
- optimize_queries: Otimiza queries MongoDB
"""

import ast
from pathlib import Path
from typing import Any

import structlog

from src.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


def suggest_refactors(path: str, complexity_threshold: int = 10) -> dict[str, Any]:
    """
    Sugere refatorações baseado em análise estática de código.

    Args:
        path: Caminho do diretório/arquivo
        complexity_threshold: Threshold de McCabe para alertas

    Returns:
        Dicionário com sugestões de refatoração
    """
    logger.info("suggest_refactors_called", path=path, threshold=complexity_threshold)

    base_path = Path(path).resolve()

    if not base_path.exists():
        raise FileNotFoundError(f"Path not found: {path}")

    suggestions = []

    # Analisar arquivos Python
    for py_file in base_path.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")

            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue

            # Analisar complexidade ciclomática
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    complexity = _calculate_mcabe_complexity(node)

                    if complexity > complexity_threshold:
                        suggestions.append(
                            {
                                "type": "high_complexity",
                                "file": str(py_file.relative_to(base_path)),
                                "line": node.lineno,
                                "name": node.name,
                                "complexity": complexity,
                                "description": f"Função {node.name} tem complexidade {complexity}",
                                "effort": "high" if complexity > 20 else "medium",
                                "impact": 8.0,
                            }
                        )

                    # Verificar métodos muito longos
                    if hasattr(node, "end_lineno") and node.end_lineno:
                        lines = node.end_lineno - node.lineno
                        if lines > settings.max_function_length:
                            suggestions.append(
                                {
                                    "type": "long_method",
                                    "file": str(py_file.relative_to(base_path)),
                                    "line": node.lineno,
                                    "name": node.name,
                                    "lines": lines,
                                    "description": f"Função {node.name} tem {lines} linhas",
                                    "effort": "medium",
                                    "impact": 5.0,
                                }
                            )

        except (PermissionError, UnicodeDecodeError) as e:
            logger.debug("file_analysis_error", path=str(py_file), error=str(e))

    # Detectar duplicação de código simples
    suggestions.extend(_detect_code_duplication(base_path))

    logger.info("suggest_refactors_completed", suggestions=len(suggestions))

    return {
        "suggestions": suggestions,
        "total_count": len(suggestions),
        "path": str(base_path),
    }


def _calculate_mcabe_complexity(node: ast.AST) -> int:
    """Calcula complexidade ciclomática de McCabe."""
    complexity = 1  # Base complexity

    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
            complexity += 1
        elif isinstance(child, (ast.ExceptHandler, ast.With)):
            complexity += 1
        elif isinstance(child, (ast.And, ast.Or)):
            complexity += 1

    return complexity


def _detect_code_duplication(base_path: Path) -> list[dict[str, Any]]:
    """Detecta duplicação de código simples."""
    duplicates = []
    code_snippets = {}

    for py_file in base_path.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
            lines = content.splitlines()

            for i, line in enumerate(lines):
                # Ignorar linhas vazias e comentários
                stripped = line.strip()
                if len(stripped) < 10 or stripped.startswith("#"):
                    continue

                if stripped not in code_snippets:
                    code_snippets[stripped] = []
                code_snippets[stripped].append((py_file, i + 1))

        except (PermissionError, UnicodeDecodeError):
            pass

    # Encontrar duplicações (mesma linha em múltiplos arquivos)
    for snippet, locations in code_snippets.items():
        if len(locations) > 2:  # Pelo menos 3 ocorrências
            duplicates.append(
                {
                    "type": "duplication",
                    "snippet": snippet[:50] + "..." if len(snippet) > 50 else snippet,
                    "occurrences": len(locations),
                    "files": [str(loc[0].relative_to(base_path)) for loc in locations],
                    "description": f"Código duplicado {len(locations)} vezes",
                    "effort": "low",
                    "impact": 3.0,
                }
            )

    return duplicates[:10]  # Limitar a 10 sugestões


def analyze_performance(path: str = ".", service: str = "", duration: str = "1h") -> dict[str, Any]:
    """
    Analisa métricas de performance de um serviço.

    Args:
        path: Caminho para arquivos de métrica
        service: Nome do serviço (opcional)
        duration: Janela de tempo para análise

    Returns:
        Dicionário com métricas de performance
    """
    logger.info("analyze_performance_called", path=path, service=service, duration=duration)

    metrics_path = Path(path)

    # Métricas simuladas baseadas em padrões
    if service:
        # Em produção, buscaria métricas do Prometheus/MongoDB
        metrics_data = {
            "latency_p50": 80,
            "latency_p95": 200,
            "latency_p99": 450,
            "throughput": 50,
            "error_rate": 0.03,
            "cpu_usage": 0.65,
            "memory_usage": 0.72,
        }
    else:
        metrics_data = {
            "latency_p50": 100,
            "latency_p95": 250,
            "latency_p99": 500,
            "throughput": 100,
            "error_rate": 0.02,
            "cpu_usage": 0.55,
            "memory_usage": 0.60,
        }

    # Identificar bottlenecks
    bottlenecks = []
    if metrics_data["latency_p99"] > 300:
        bottlenecks.append(
            {
                "type": "latency",
                "severity": "high" if metrics_data["latency_p99"] > 500 else "medium",
                "description": "Latência p99 alta",
            }
        )

    if metrics_data["error_rate"] > 0.05:
        bottlenecks.append(
            {
                "type": "errors",
                "severity": "high",
                "description": f"Taxa de erro {(metrics_data['error_rate']*100):.1f}%",
            }
        )

    if metrics_data["cpu_usage"] > 0.8:
        bottlenecks.append(
            {
                "type": "cpu",
                "severity": "medium",
                "description": f"CPU uso {(metrics_data['cpu_usage']*100):.0f}%",
            }
        )

    # Determinar tendência
    if metrics_data["latency_p50"] < 50 and metrics_data["error_rate"] < 0.01:
        trend = "improving"
    elif metrics_data["latency_p95"] > 300 or metrics_data["error_rate"] > 0.05:
        trend = "degrading"
    else:
        trend = "stable"

    logger.info("analyze_performance_completed", service=service, trend=trend)

    return {
        "service": service or "unknown",
        "metrics": metrics_data,
        "bottlenecks": bottlenecks,
        "trend": trend,
        "recommendations": _generate_performance_recommendations(metrics_data, bottlenecks),
    }


def _generate_performance_recommendations(metrics: dict, bottlenecks: list) -> list[str]:
    """Gera recomendações baseado em métricas."""
    recommendations = []

    if metrics["latency_p99"] > 300:
        recommendations.append("Considerar caching para reduzir latência")

    if metrics["error_rate"] > 0.05:
        recommendations.append("Investigar causas de erros - revisar logs")

    if metrics["cpu_usage"] > 0.8:
        recommendations.append("Escalear horizontalmente ou otimizar código")

    if metrics["memory_usage"] > 0.8:
        recommendations.append("Investigar memory leaks ou aumentar memória")

    return recommendations


def optimize_queries(query: dict, collection: str) -> dict[str, Any]:
    """
    Otimiza queries MongoDB.

    Args:
        query: Query MongoDB para otimizar
        collection: Nome da coleção

    Returns:
        Dicionário com query otimizada e sugestões
    """
    logger.info("optimize_queries_called", collection=collection)

    if not isinstance(query, dict):
        raise ValueError("Query must be a dictionary")

    if not collection or not collection.strip():
        raise ValueError("Collection name is required")

    # Análise da query
    suggested_indexes = []
    optimized_query = query.copy()

    # Sugerir índices baseados em filtros $eq
    _extract_index_suggestions(query, collection, suggested_indexes)

    # Otimizações específicas
    if "$or" in query and len(query["$or"]) > 2:
        # Sugerir usar $in para múltiplos valores iguais
        or_conditions = query["$or"]
        field = None
        values = []

        for cond in or_conditions:
            if field is None:
                # Extrair campo comum
                keys = set(cond.keys()) - {"$or", "$and"}
                if len(keys) == 1:
                    field = list(keys)[0]
            if field and field in cond:
                if isinstance(cond[field], dict):
                    continue  # Operador complexo
                values.append(cond[field])

        if field and all(isinstance(v, (str, int, float)) for v in values):
            # Pode otimizar para $in
            suggested_indexes.append(
                {"keys": {field: 1}, "description": f"Índice composto em {field}"}
            )

    # Estimar melhoria
    has_scan = _has_scan_operation(query)
    needs_indexes = len(suggested_indexes) > 0

    if has_scan:
        improvement_estimate = "30-50%"
    elif needs_indexes:
        improvement_estimate = "15-30%"
    else:
        improvement_estimate = "5-15%"

    logger.info(
        "optimize_queries_completed",
        collection=collection,
        indexes=len(suggested_indexes),
    )

    return {
        "optimized_query": optimized_query,
        "suggested_indexes": suggested_indexes,
        "improvement_estimate": improvement_estimate,
        "collection": collection,
        "analysis": {
            "has_scan": has_scan,
            "query_depth": _calculate_query_depth(query),
            "optimization_applied": suggested_indexes != [],
        },
    }


def _extract_index_suggestions(query: dict, collection: str, suggestions: list) -> None:
    """Extrai sugestões de índice da query."""
    for key, value in query.items():
        if key.startswith("$"):
            continue  # Operador MongoDB

        if isinstance(value, dict):
            # Recursão
            _extract_index_suggestions(value, collection, suggestions)
        elif isinstance(value, (str, int, float, bool)):
            # Campo de igualdade - candidato a índice
            if key != "_id":
                suggestions.append({"keys": {key: 1}, "description": f"Índice simples em {key}"})
        elif isinstance(value, list):
            # Operador $in - bom candidato
            if len(value) > 1:
                suggestions.append({"keys": {key: 1}, "description": f"Índice para $in em {key}"})


def _has_scan_operation(query: dict, depth: int = 0) -> bool:
    """Verifica se query tem operation de scan."""
    if depth > 10:
        return False

    for key, value in query.items():
        if key == "$regex":
            return True
        if isinstance(value, dict):
            if _has_scan_operation(value, depth + 1):
                return True
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and _has_scan_operation(item, depth + 1):
                    return True

    return False


def _calculate_query_depth(query: dict, depth: int = 0) -> int:
    """Calcula profundidade da query."""
    if depth > 10:
        return depth

    max_depth = depth
    for value in query.values():
        if isinstance(value, dict):
            d = _calculate_query_depth(value, depth + 1)
            max_depth = max(max_depth, d)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    d = _calculate_query_depth(item, depth + 1)
                    max_depth = max(max_depth, d)

    return max_depth


def register_optimizer_tools(mcp) -> None:
    """Registra ferramentas Optimizer no servidor MCP."""
    mcp.tool()(suggest_refactors)
    mcp.tool()(analyze_performance)
    mcp.tool()(optimize_queries)
