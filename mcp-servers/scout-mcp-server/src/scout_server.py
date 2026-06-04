"""
Scout MCP Server - Servidor MCP para descoberta e exploração de código.

Expõe ferramentas para:
- Escanear estrutura de repositórios
- Encontrar arquivos por padrão
- Analisar dependências
- Identificar tecnologias usadas
"""

import os
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict

from fastmcp import FastMCP

# Criar servidor MCP
mcp = FastMCP(name="Scout MCP Server")


@dataclass
class ScanResult:
    """Resultado de scan de diretório."""

    path: str
    total_files: int = 0
    total_dirs: int = 0
    languages: dict[str, int] = field(default_factory=dict)
    frameworks: list[str] = field(default_factory=list)
    dependencies: dict[str, list[str]] = field(default_factory=dict)


class CodeScanner:
    """
    Scanner de código para análise de repositórios.
    """

    # Extensões de arquivo por linguagem
    LANGUAGE_EXTENSIONS = {
        "python": [".py"],
        "javascript": [".js", ".jsx", ".ts", ".tsx"],
        "java": [".java"],
        "go": [".go"],
        "rust": [".rs"],
        "ruby": [".rb"],
        "php": [".php"],
        "typescript": [".ts", ".tsx"],
        "html": [".html", ".htm"],
        "css": [".css", ".scss", ".sass", ".less"],
        "yaml": [".yml", ".yaml"],
        "json": [".json"],
        "markdown": [".md"],
        "shell": [".sh", ".bash"],
        "dockerfile": ["Dockerfile"],
    }

    # Frameworks detectados por padrão de arquivo/diretório
    FRAMEWORK_PATTERNS = {
        "FastAPI": ["fastapi", "requirements.txt*fastapi"],
        "Flask": ["flask", "requirements.txt*flask"],
        "Django": ["django", "manage.py"],
        "React": ["package.json*react", "src/App.jsx", "src/App.tsx"],
        "Vue": ["package.json*vue", "*.vue"],
        "Angular": ["angular.json"],
        "Spring Boot": ["pom.xml*spring", "build.gradle*spring"],
        "Node.js": ["package.json"],
        "Go": ["go.mod"],
        "Rust": ["Cargo.toml"],
        "Docker": ["Dockerfile", "docker-compose.yml"],
        "Kubernetes": ["k8s/", "*.yaml*deployment", "*.yaml*service"],
    }

    def __init__(self, base_path: str = "/repo"):
        """
        Inicializa scanner.

        Args:
            base_path: Caminho base para scans
        """
        self.base_path = Path(base_path)

    def scan_directory(
        self,
        path: str,
        max_depth: int = 5,
        exclude_dirs: Optional[list[str]] = None,
    ) -> ScanResult:
        """
        Escaneia diretório e analise estrutura.

        Args:
            path: Caminho relativo ao base_path
            max_depth: Profundidade máxima de recursão
            exclude_dirs: Diretórios a excluir (node_modules, .git, etc)

        Returns:
            ScanResult com estatísticas
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
                ".pytest_cache",
                ".mypy_cache",
            ]

        full_path = self.base_path / path
        if not full_path.exists():
            raise FileNotFoundError(f"Path not found: {full_path}")

        result = ScanResult(path=path)
        languages = defaultdict(int)
        frameworks = set()

        # Scan files
        for root, dirs, files in os.walk(full_path):
            # Filter excluded dirs
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            # Check depth
            rel_path = Path(root).relative_to(self.base_path)
            if len(rel_path.parts) > max_depth:
                continue

            result.total_dirs += len(dirs)

            for file in files:
                result.total_files += 1

                # Detect language
                ext = Path(file).suffix.lower()
                for lang, exts in self.LANGUAGE_EXTENSIONS.items():
                    if ext in exts:
                        languages[lang] += 1
                        break

            # Detect frameworks by directory structure
            for dir_name in dirs:
                for framework in frameworks:
                    pass  # Placeholder for framework detection

        result.languages = dict(languages)
        result.frameworks = list(frameworks)

        return result

    def find_files(
        self,
        path: str,
        pattern: str,
        exclude_dirs: Optional[list[str]] = None,
    ) -> list[str]:
        """
        Encontra arquivos por padrão.

        Args:
            path: Caminho para busca
            pattern: Padrão glob (ex: "*.py", "**/test_*.py")
            exclude_dirs: Diretórios a excluir

        Returns:
            Lista de caminhos relativos dos arquivos encontrados
        """
        if exclude_dirs is None:
            exclude_dirs = [
                "node_modules",
                ".git",
                "__pycache__",
                "venv",
                ".venv",
            ]

        full_path = self.base_path / path
        if not full_path.exists():
            raise FileNotFoundError(f"Path not found: {full_path}")

        found_files = []

        for root, dirs, files in os.walk(full_path):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            for file in files:
                file_path = Path(root) / file

                # Check glob pattern
                relative_path = file_path.relative_to(full_path)
                if relative_path.match(pattern):
                    found_files.append(str(relative_path))

        return found_files

    def detect_dependencies(self, path: str) -> dict[str, list[str]]:
        """
        Detecta dependências do projeto.

        Args:
            path: Caminho do projeto

        Returns:
            Dicionário {type: [dependencies]}
        """
        full_path = self.base_path / path
        if not full_path.exists():
            raise FileNotFoundError(f"Path not found: {full_path}")

        dependencies = defaultdict(list)

        # Python - requirements.txt
        req_file = full_path / "requirements.txt"
        if req_file.exists():
            with open(req_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        pkg_name = line.split("==")[0].split(">=")[0].split("<=")[0].strip()
                        dependencies["python"].append(pkg_name)

        # Python - pyproject.toml
        pyproject = full_path / "pyproject.toml"
        if pyproject.exists():
            dependencies["python"].append("pyproject.toml")

        # JavaScript - package.json
        package_json = full_path / "package.json"
        if package_json.exists():
            import json

            with open(package_json) as f:
                data = json.load(f)
                deps = data.get("dependencies", {})
                dev_deps = data.get("devDependencies", {})
                dependencies["javascript"] = list(deps.keys()) + list(dev_deps.keys())

        # Go - go.mod
        go_mod = full_path / "go.mod"
        if go_mod.exists():
            dependencies["go"] = ["go.mod"]

        # Rust - Cargo.toml
        cargo = full_path / "Cargo.toml"
        if cargo.exists():
            dependencies["rust"] = ["Cargo.toml"]

        # Java - pom.xml
        pom = full_path / "pom.xml"
        if pom.exists():
            dependencies["java"] = ["pom.xml"]

        return dict(dependencies)


# Instância global do scanner
_scanner: Optional[CodeScanner] = None


def get_scanner() -> CodeScanner:
    """Retorna instância do scanner."""
    global _scanner
    if _scanner is None:
        # Usar diretório configurável via environment
        base_path = os.environ.get("SCOUT_BASE_PATH", "/repo")
        _scanner = CodeScanner(base_path=base_path)
    return _scanner


# ============ MCP Tools ============


@mcp.tool()
async def scan_directory(
    path: str = ".",
    max_depth: int = 5,
    exclude_dirs: str = "node_modules,.git,__pycache__,venv,.venv,dist,build",
) -> dict[str, Any]:
    """
    Escaneia diretório e retorna estatísticas do código.

    Args:
        path: Caminho relativo para scan
        max_depth: Profundidade máxima (1-10)
        exclude_dirs: Diretórios a excluir (separados por vírgula)

    Returns:
        Estatísticas do diretório escaneado
    """
    scanner = get_scanner()
    exclude_list = [d.strip() for d in exclude_dirs.split(",") if d.strip()]

    result = scanner.scan_directory(
        path=path,
        max_depth=max_depth,
        exclude_dirs=exclude_list,
    )

    return {
        "path": result.path,
        "total_files": result.total_files,
        "total_dirs": result.total_dirs,
        "languages": result.languages,
        "frameworks": result.frameworks,
        "summary": {
            "primary_language": (
                max(result.languages.items(), key=lambda x: x[1])[0]
                if result.languages
                else "unknown"
            ),
            "total_languages": len(result.languages),
        },
    }


@mcp.tool()
async def find_files(
    path: str = ".",
    pattern: str = "*.py",
    exclude_dirs: str = "node_modules,.git,__pycache__",
) -> dict[str, Any]:
    """
    Encontra arquivos por padrão glob.

    Args:
        path: Caminho para busca
        pattern: Padrão glob (ex: "*.py", "**/test_*.py", "**/*.yaml")
        exclude_dirs: Diretórios a excluir (separados por vírgula)

    Returns:
        Lista de arquivos encontrados com metadados
    """
    scanner = get_scanner()
    exclude_list = [d.strip() for d in exclude_dirs.split(",") if d.strip()]

    files = scanner.find_files(
        path=path,
        pattern=pattern,
        exclude_dirs=exclude_list,
    )

    return {
        "pattern": pattern,
        "path": path,
        "count": len(files),
        "files": files[:100],  # Limitar a 100 arquivos
        "truncated": len(files) > 100,
    }


@mcp.tool()
async def detect_dependencies(path: str = ".") -> dict[str, Any]:
    """
    Detecta dependências do projeto analisando arquivos de configuração.

    Args:
        path: Caminho do projeto

    Returns:
        Dependências detectadas por tipo de linguagem/ecossistema
    """
    scanner = get_scanner()

    try:
        dependencies = scanner.detect_dependencies(path=path)

        summary = {ecosystem: len(deps) for ecosystem, deps in dependencies.items()}

        return {
            "path": path,
            "dependencies": dependencies,
            "summary": summary,
            "total_ecosystems": len(dependencies),
        }
    except FileNotFoundError as e:
        return {
            "error": str(e),
            "dependencies": {},
            "summary": {},
            "total_ecosystems": 0,
        }


@mcp.tool()
async def analyze_project_structure(path: str = ".") -> dict[str, Any]:
    """
    Analisa estrutura completa do projeto.

    Combina scan de diretório, detecção de dependências
    e análise de arquivos importantes.

    Args:
        path: Caminho do projeto

    Returns:
        Análise completa da estrutura do projeto
    """
    scanner = get_scanner()

    try:
        # Scan directory
        scan_result = scanner.scan_directory(path=path, max_depth=3)

        # Detect dependencies
        dependencies = scanner.detect_dependencies(path=path)

        # Check for common files
        full_path = scanner.base_path / path
        common_files = [
            "README.md",
            "LICENSE",
            ".gitignore",
            "Dockerfile",
            "docker-compose.yml",
            "package.json",
            "requirements.txt",
            "pyproject.toml",
            "go.mod",
            "Cargo.toml",
        ]

        found_files = {}
        for file in common_files:
            file_path = full_path / file
            found_files[file] = file_path.exists()

        return {
            "path": path,
            "scan": {
                "total_files": scan_result.total_files,
                "total_dirs": scan_result.total_dirs,
                "languages": scan_result.languages,
                "primary_language": (
                    max(scan_result.languages.items(), key=lambda x: x[1])[0]
                    if scan_result.languages
                    else "unknown"
                ),
            },
            "dependencies": dependencies,
            "common_files": found_files,
            "recommendations": _generate_recommendations(scan_result, dependencies, found_files),
        }

    except Exception as e:
        return {
            "error": str(e),
            "path": path,
        }


def _generate_recommendations(
    scan_result: ScanResult,
    dependencies: dict[str, list[str]],
    common_files: dict[str, bool],
) -> list[str]:
    """Gera recomendações baseadas na análise."""
    recommendations = []

    # Check for README
    if not common_files.get("README.md"):
        recommendations.append("Add README.md with project documentation")

    # Check for .gitignore
    if not common_files.get(".gitignore"):
        recommendations.append("Add .gitignore to exclude build artifacts")

    # Check for Docker
    if not common_files.get("Dockerfile"):
        recommendations.append("Consider adding Dockerfile for containerization")

    # Check dependencies size
    for ecosystem, deps in dependencies.items():
        if len(deps) > 50:
            recommendations.append(
                f"Review {ecosystem} dependencies - {len(deps)} packages detected"
            )

    return recommendations


@mcp.tool()
async def get_file_info(path: str) -> dict[str, Any]:
    """
    Obtém informações detalhadas sobre um arquivo.

    Args:
        path: Caminho do arquivo

    Returns:
        Informações do arquivo
    """
    scanner = get_scanner()
    full_path = scanner.base_path / path

    if not full_path.exists():
        return {"error": f"File not found: {path}"}

    stat = full_path.stat()

    # Detect language by extension
    ext = full_path.suffix.lower()
    language = "unknown"
    for lang, exts in CodeScanner.LANGUAGE_EXTENSIONS.items():
        if ext in exts:
            language = lang
            break

    return {
        "path": path,
        "name": full_path.name,
        "extension": ext,
        "language": language,
        "size_bytes": stat.st_size,
        "size_human": _format_size(stat.st_size),
        "modified": stat.st_mtime,
        "is_file": full_path.is_file(),
        "is_dir": full_path.is_dir(),
    }


def _format_size(size_bytes: int) -> str:
    """Formata tamanho em bytes para representação humana."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}TB"


# ============ Health Check ============


@mcp.tool()
async def health_check() -> dict[str, str]:
    """
    Verifica saúde do servidor Scout MCP.

    Returns:
        Status de saúde
    """
    return {
        "status": "healthy",
        "server": "Scout MCP Server",
        "version": "1.0.0",
    }


# ============ Main ============

if __name__ == "__main__":
    import sys

    # Configurar base path via argumento
    if len(sys.argv) > 1:
        os.environ["SCOUT_BASE_PATH"] = sys.argv[1]

    # Executar servidor MCP
    # FastMCP por padrão usa stdio para comunicação MCP
    # Para cluster Kubernetes, precisamos de um endpoint HTTP
    # Por enquanto, executar em modo stdio para compatibilidade
    mcp.run()
