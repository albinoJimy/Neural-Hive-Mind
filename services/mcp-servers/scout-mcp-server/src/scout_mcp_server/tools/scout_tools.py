"""
Scout MCP Tools - Ferramentas de descoberta de código.

Ferramentas:
- list_files: Lista arquivos de um diretório
- search_code: Busca padrões no código
- analyze_structure: Analisa estrutura de diretórios
"""

import os
import re
from pathlib import Path
from typing import Any

import structlog

from scout_mcp_server.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


def list_files(
    path: str,
    pattern: str = "*",
    recursive: bool = True
) -> dict[str, Any]:
    """
    Lista arquivos de um diretório.

    Args:
        path: Caminho do diretório
        pattern: Filtro glob (ex: "*.py", "test_*")
        recursive: Busca recursiva em subdiretórios

    Returns:
        Dicionário com lista de arquivos e metadata
    """
    logger.info("list_files_called", path=path, pattern=pattern, recursive=recursive)

    base_path = Path(path).resolve()

    if not base_path.exists():
        raise FileNotFoundError(f"Path not found: {path}")

    if not base_path.is_dir():
        raise ValueError(f"Path is not a directory: {path}")

    files = []
    count = 0

    # Função de coleta
    def collect_files(current_path: Path, depth: int = 0) -> None:
        nonlocal count

        if count >= settings.max_files_per_scan:
            return

        try:
            for item in current_path.iterdir():
                if count >= settings.max_files_per_scan:
                    break

                # Skip hidden directories e comuns
                if item.name.startswith((".", "__")):
                    if item.is_dir():
                        continue

                try:
                    is_dir = item.is_dir()
                    is_file = item.is_file()

                    # Aplicar filtro de pattern
                    # Se pattern não é curinga "*", filtramos arquivos
                    if pattern != "*":
                        # Pular diretórios quando pattern específico
                        if is_dir:
                            continue
                        # Verificar se arquivo casa com pattern
                        if not item.match(pattern):
                            continue

                    # Calcular caminho relativo
                    try:
                        rel_path = item.relative_to(base_path)
                    except ValueError:
                        rel_path = item  # Fora da base, usar absoluto

                    file_info = {
                        "path": str(rel_path),
                        "size": item.stat().st_size if is_file else 0,
                        "type": "directory" if is_dir else "file"
                    }

                    # Adicionar metadata adicional
                    if is_file:
                        file_info["extension"] = item.suffix
                        if item.stat().st_size > settings.max_file_size_bytes:
                            file_info["too_large"] = True

                    files.append(file_info)
                    count += 1

                    # Recursão
                    if is_dir and recursive:
                        # Limitar profundidade para evitar ciclos
                        if depth < 50:
                            collect_files(item, depth + 1)

                except (PermissionError, OSError) as e:
                    logger.warning("file_access_error", path=str(item), error=str(e))

        except (PermissionError, OSError) as e:
            logger.warning("directory_access_error", path=str(current_path), error=str(e))

    collect_files(base_path)

    logger.info("list_files_completed", count=count, path=path)

    return {
        "files": files,
        "count": count,
        "base_path": str(base_path)
    }


def search_code(
    query: str,
    path: str = ".",
    file_pattern: str = "*",
    max_results: int = 100
) -> dict[str, Any]:
    """
    Busca padrões no código.

    Args:
        query: Query de busca (regex ou substring)
        path: Caminho base para busca
        file_pattern: Filtro de arquivo (ex: "*.py")
        max_results: Número máximo de resultados

    Returns:
        Dicionário com matches encontrados
    """
    logger.info("search_code_called", query=query, path=path, file_pattern=file_pattern)

    base_path = Path(path).resolve()

    if not base_path.exists():
        raise FileNotFoundError(f"Path not found: {path}")

    # Compilar regex se válido, senão usar substring
    try:
        regex = re.compile(query, re.IGNORECASE | re.MULTILINE)
        use_regex = True
    except re.error:
        regex = None
        use_regex = False

    matches = []
    files_scanned = 0

    # Buscar arquivos
    for item in base_path.rglob(file_pattern):
        if len(matches) >= max_results:
            break

        if not item.is_file():
            continue

        # Skip binários comuns
        if item.suffix in [".pyc", ".so", ".dll", ".exe", ".bin"]:
            continue

        files_scanned += 1

        try:
            content = item.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()

            for line_num, line in enumerate(lines, 1):
                if len(matches) >= max_results:
                    break

                # Buscar match
                is_match = False
                if use_regex:
                    if regex.search(line):
                        is_match = True
                else:
                    if query.lower() in line.lower():
                        is_match = True

                if is_match:
                    # Extrair contexto
                    start_ctx = max(0, line_num - 3)
                    end_ctx = min(len(lines), line_num + 2)
                    context_lines = lines[start_ctx:end_ctx]

                    match_info = {
                        "file": str(item.relative_to(base_path)),
                        "line": line_num,
                        "content": line.strip(),
                        "context": context_lines
                    }

                    matches.append(match_info)

        except (PermissionError, UnicodeDecodeError, OSError) as e:
            logger.debug("file_search_error", path=str(item), error=str(e))

    logger.info("search_code_completed", matches=len(matches), files_scanned=files_scanned)

    return {
        "matches": matches,
        "total_matches": len(matches),
        "files_scanned": files_scanned
    }


def analyze_structure(
    path: str,
    depth: int = 10
) -> dict[str, Any]:
    """
    Analisa estrutura de diretórios.

    Args:
        path: Caminho base
        depth: Profundidade máxima de análise

    Returns:
        Dicionário com estrutura e métricas
    """
    logger.info("analyze_structure_called", path=path, depth=depth)

    base_path = Path(path).resolve()

    if not base_path.exists():
        raise FileNotFoundError(f"Path not found: {path}")

    structure = {}
    file_count = 0
    dir_count = 0

    def build_tree(current_path: Path, tree: dict, current_depth: int) -> None:
        nonlocal file_count, dir_count

        if current_depth > depth:
            return

        try:
            for item in sorted(current_path.iterdir()):
                # Skip ocultos
                if item.name.startswith("."):
                    continue

                if item.is_dir():
                    dir_count += 1
                    tree[item.name] = {}
                    build_tree(item, tree[item.name], current_depth + 1)
                elif item.is_file():
                    file_count += 1
                    # Usar dict para indicar arquivo (leaf node)
                    tree[item.name] = None

        except (PermissionError, OSError):
            pass

    build_tree(base_path, structure, 0)

    # Calcular complexidade baseada em:
    # - número de níveis
    # - dispersão de arquivos
    def count_levels(d: dict, level: int = 0) -> int:
        if not d:
            return level
        return max((count_levels(v, level + 1) if isinstance(v, dict) else level
                   for v in d.values()), default=level)

    max_levels = count_levels(structure)

    # Complexidade = (niveis * 10) + (arquivos / diretorios)
    complexity = (max_levels * 10) + (file_count / max(dir_count, 1))

    logger.info(
        "analyze_structure_completed",
        files=file_count,
        dirs=dir_count,
        complexity=complexity
    )

    return {
        "structure": structure,
        "metrics": {
            "files": file_count,
            "dirs": dir_count,
            "max_depth": max_levels,
            "complexity": round(complexity, 2)
        }
    }


def register_scout_tools(mcp) -> None:
    """Registra ferramentas Scout no servidor MCP."""
    mcp.tool()(list_files)
    mcp.tool()(search_code)
    mcp.tool()(analyze_structure)
