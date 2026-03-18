"""
Scout MCP HTTP Server - Servidor HTTP simplificado para expor ferramentas de descoberta de código.

Expõe endpoints REST para:
- Escanear estrutura de repositórios
- Encontrar arquivos por padrão
- Analisar dependências
- Identificar tecnologias usadas

Este servidor HTTP expõe as mesmas funcionalidades do Scout MCP Server
mas usando endpoints REST simples em vez do protocolo MCP stdio.
"""
import asyncio
import json
import os
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import cgi

# ============ Models ============

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
        "css": [".css"],
        "yaml": [".yaml", ".yml"],
        "json": [".json"],
        "xml": [".xml"],
        "markdown": [".md", ".markdown"],
        "text": [".txt"],
        "shell": [".sh", ".bash"],
    }

    # Frameworks por linguagem
    FRAMEWORK_PATTERNS = {
        "javascript": [
            ("package.json", "node"),
            ("tsconfig.json", "typescript"),
            ("vue.config.js", "vue"),
            ("nuxt.config.js", "nuxt"),
        ],
        "python": [
            ("requirements.txt", "pip"),
            ("setup.py", "setuptools"),
            ("pyproject.toml", "poetry"),
            ("Pipfile", "pipenv"),
            ("py.typed", "mypy"),
        ],
        "ruby": [
            ("Gemfile", "bundler"),
            ("Rakefile", "rake"),
        ],
        "java": [
            ("pom.xml", "maven"),
            ("build.gradle", "gradle"),
        ],
        "go": [
            ("go.mod", "go"),
        ],
        "php": [
            ("composer.json", "composer"),
        ],
    }

    def __init__(self, base_path: str = ".", max_depth: int = 5):
        self.base_path = Path(base_path)
        self.max_depth = max_depth

    def _is_excluded_dir(self, dir_name: str) -> bool:
        """Verifica se diretório deve ser excluído."""
        excluded = {
            ".git",
            ".svn",
            ".hg",
            "node_modules",
            "__pycache__",
            ".pytest_cache",
            ".venv",
            "venv",
            "env",
            "dist",
            "build",
            "target",
            "out",
            ".next",
            ".nuxt",
            "vendor",
            "bower_components",
        }
        return dir_name in excluded

    def scan_directory(
        self, path: str = ".", max_depth: int = 5, exclude_dirs: str = ""
    ) -> dict[str, Any]:
        """Escaneia diretório recursivamente."""
        exclude_list = [d.strip() for d in exclude_dirs.split(",") if d.strip()]
        exclude_set = set(exclude_list) | {
            ".git", ".svn", ".hg", "node_modules", "__pycache__",
            ".pytest_cache", ".venv", "venv", "dist", "build", "target"
        }

        result = ScanResult(path=path)
        root_path = Path(self.base_path) / path

        if not root_path.exists():
            return {
                "error": f"Path not found: {path}",
                "path": path
            }

        def scan_dir(current_path: Path, depth: int) -> None:
            if depth > max_depth:
                return

            try:
                for item in current_path.iterdir():
                    if item.is_dir():
                        if not self._is_excluded_dir(item.name):
                            result.total_dirs += 1
                            scan_dir(item, depth + 1)
                    elif item.is_file():
                        result.total_files += 1
                        # Detectar linguagem
                        for lang, exts in self.LANGUAGE_EXTENSIONS.items():
                            if item.suffix in exts:
                                result.languages[lang] = result.languages.get(lang, 0) + 1
            except PermissionError:
                pass

        scan_dir(root_path, 0)

        # Detectar frameworks
        result.frameworks = self._detect_frameworks(root_path)

        return {
            "path": result.path,
            "total_files": result.total_files,
            "total_dirs": result.total_dirs,
            "languages": result.languages,
            "frameworks": result.frameworks,
            "dependencies": self._detect_dependencies(root_path)
        }

    def _detect_frameworks(self, root_path: Path) -> list[str]:
        """Detecta frameworks usados no projeto."""
        detected = []
        for lang, patterns in self.FRAMEWORK_PATTERNS.items():
            for file_name, framework in patterns:
                if (root_path / file_name).exists():
                    if framework not in detected:
                        detected.append(f"{lang}:{framework}")
        return detected

    def _detect_dependencies(self, root_path: Path) -> dict[str, list[str]]:
        """Detecta dependências do projeto."""
        dependencies = {}

        # Python - requirements.txt
        req_file = root_path / "requirements.txt"
        if req_file.exists():
            try:
                with open(req_file) as f:
                    deps = [line.strip().split("==")[0].strip()
                           for line in f
                           if line.strip() and not line.startswith("#")]
                dependencies["python"] = deps[:10]  # Primeiras 10
            except Exception:
                pass

        # JavaScript - package.json
        pkg_file = root_path / "package.json"
        if pkg_file.exists():
            try:
                import json
                with open(pkg_file) as f:
                    data = json.load(f)
                    deps = list(data.get("dependencies", {}).keys())
                    dependencies["javascript"] = deps[:10]
            except Exception:
                pass

        return dependencies

    def find_files(
        self, path: str = ".", pattern: str = "*", recursive: bool = True
    ) -> dict[str, Any]:
        """Encontra arquivos por padrão."""
        search_path = Path(self.base_path) / path
        if not search_path.exists():
            return {"error": f"Path not found: {path}", "files": []}

        files = []
        try:
            if recursive:
                files = [
                    str(f.relative_to(search_path))
                    for f in search_path.rglob(pattern)
                    if f.is_file()
                ]
            else:
                files = [
                    str(f.name)
                    for f in search_path.glob(pattern)
                    if f.is_file()
                ]
        except Exception as e:
            return {"error": str(e), "files": []}

        return {"path": path, "pattern": pattern, "files": files[:100]}

    def analyze_project_structure(self, path: str = ".") -> dict[str, Any]:
        """Analisa estrutura completa do projeto."""
        return self.scan_directory(path=path)


# ============ HTTP Server ============

class ScoutHTTPRequestHandler(BaseHTTPRequestHandler):
    """Handler HTTP para Scout MCP Server."""

    scanner = None

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
            self.wfile.write(json.dumps({
                "status": "healthy",
                "server": "Scout MCP HTTP Server",
                "version": "1.0.0"
            }).encode())
            return

        # /tools - Lista ferramentas disponíveis
        if path_parts[0] == "tools":
            self._set_json_headers()
            self.wfile.write(json.dumps({
                "tools": [
                    {"name": "scan_directory", "description": "Scan directory recursively"},
                    {"name": "find_files", "description": "Find files by pattern"},
                    {"name": "detect_dependencies", "description": "Detect project dependencies"},
                    {"name": "analyze_project_structure", "description": "Analyze project structure"}
                ]
            }).encode())
            return

        # /scan - Escanear diretório
        if path_parts[0] == "scan":
            query = parse_qs(parsed_path.query)
            path = query.get("path", ["."])[0]
            max_depth = int(query.get("max_depth", ["5"])[0])
            exclude_dirs = query.get("exclude_dirs", [""])[0]

            if not self.scanner:
                base_path = os.getenv("SCOUT_BASE_PATH", "/repo")
                self.scanner = CodeScanner(base_path=base_path)

            result = self.scanner.scan_directory(
                path=path, max_depth=max_depth, exclude_dirs=exclude_dirs
            )
            self._set_json_headers()
            self.wfile.write(json.dumps(result).encode())
            return

        # /files - Encontrar arquivos
        if path_parts[0] == "files":
            query = parse_qs(parsed_path.query)
            path = query.get("path", ["."])[0]
            pattern = query.get("pattern", ["*"])[0]
            recursive = query.get("recursive", ["true"])[0].lower() == "true"

            if not self.scanner:
                base_path = os.getenv("SCOUT_BASE_PATH", "/repo")
                self.scanner = CodeScanner(base_path=base_path)

            result = self.scanner.find_files(
                path=path, pattern=pattern, recursive=recursive
            )
            self._set_json_headers()
            self.wfile.write(json.dumps(result).encode())
            return

        # /analyze - Analisar estrutura
        if path_parts[0] == "analyze":
            query = parse_qs(parsed_path.query)
            path = query.get("path", ["."])[0]

            if not self.scanner:
                base_path = os.getenv("SCOUT_BASE_PATH", "/repo")
                self.scanner = CodeScanner(base_path=base_path)

            result = self.scanner.analyze_project_structure(path=path)
            self._set_json_headers()
            self.wfile.write(json.dumps(result).encode())
            return

        # /deps - Dependências
        if path_parts[0] == "deps":
            query = parse_qs(parsed_path.query)
            path = query.get("path", ["."])[0]

            if not self.scanner:
                base_path = os.getenv("SCOUT_BASE_PATH", "/repo")
                self.scanner = CodeScanner(base_path=base_path)

            root_path = Path(self.scanner.base_path) / path
            deps = self.scanner._detect_dependencies(root_path)
            self._set_json_headers()
            self.wfile.write(json.dumps({"path": path, "dependencies": deps}).encode())
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
                except:
                    data = {}
            else:
                data = {}

            tool = data.get("tool")
            params = data.get("params", {})

            if not self.scanner:
                base_path = os.getenv("SCOUT_BASE_PATH", "/repo")
                self.scanner = CodeScanner(base_path=base_path)

            result = {}
            if tool == "scan_directory":
                result = self.scanner.scan_directory(
                    path=params.get("path", "."),
                    max_depth=params.get("max_depth", 5),
                    exclude_dirs=params.get("exclude_dirs", "")
                )
            elif tool == "find_files":
                result = self.scanner.find_files(
                    path=params.get("path", "."),
                    pattern=params.get("pattern", "*"),
                    recursive=params.get("recursive", True)
                )
            elif tool == "analyze_project_structure":
                result = self.scanner.analyze_project_structure(
                    path=params.get("path", ".")
                )
            elif tool == "detect_dependencies":
                root_path = Path(self.scanner.base_path) / params.get("path", ".")
                deps = self.scanner._detect_dependencies(root_path)
                result = {"path": params.get("path", "."), "dependencies": deps}
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
    httpd = HTTPServer(server_address, ScoutHTTPRequestHandler)
    print(f"Scout HTTP Server running on port {port}")
    httpd.serve_forever()


if __name__ == "__main__":
    import sys

    # Configurar base path via argumento
    if len(sys.argv) > 1:
        os.environ["SCOUT_BASE_PATH"] = sys.argv[1]

    port = int(os.getenv("PORT", "8080"))
    run_server(port)
