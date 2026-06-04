"""
Multi-Language Pattern Discovery - Detecção de padrões multi-linguagem.

Suporta:
- Python (via ast)
- TypeScript/JavaScript (via parsed AST ou regex)
- YAML (configurações estruturais)
- JSON (configurações estruturais)
"""

import re
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger()


class PatternMatch:
    """Resultado de detecção de padrão."""

    def __init__(
        self,
        name: str,
        confidence: float,
        class_name: Optional[str] = None,
        filename: Optional[str] = None,
        language: Optional[str] = None,
        methods: Optional[list] = None,
    ):
        self.name = name
        self.confidence = confidence
        self.class_name = class_name
        self.filename = filename
        self.language = language
        self.methods = methods or []

    def __repr__(self) -> str:
        return f"PatternMatch(name={self.name}, confidence={self.confidence})"


class PatternLanguage(str, Enum):
    """Linguagens suportadas."""

    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    YAML = "yaml"
    JSON = "json"


class MultiLanguagePatternDiscovery:
    """Detecção de padrões de design multi-linguagem."""

    # Configurações de padrão por linguagem
    LANGUAGE_PATTERNS = {
        PatternLanguage.PYTHON: {
            "class_keywords": {
                "repository": ["repository", "repo", "dao"],
                "service": ["service", "handler", "manager"],
                "factory": ["factory", "creator", "maker"],
                "singleton": ["instance", "singleton", "manager"],
                "builder": ["builder"],
                "prototype": ["prototype", "cloneable"],
                "adapter": ["adapter", "wrapper"],
                "bridge": ["bridge"],
                "composite": ["composite", "component", "node", "leaf"],
                "decorator": ["decorator"],
                "facade": ["facade", "api"],
                "proxy": ["proxy"],
                "strategy": ["strategy"],
                "observer": ["observer", "listener", "subscriber", "notifier", "subject"],
                "command": ["command", "action", "operation"],
                "chain": ["chain", "handler", "middleware", "filter"],
                "template_method": ["template"],
                "mediator": ["mediator"],
                "memento": ["memento", "snapshot", "state"],
                "state": ["state", "context"],
            },
            "method_keywords": {
                "repository": [
                    "find",
                    "save",
                    "delete",
                    "update",
                    "get",
                    "list",
                    "create",
                    "remove",
                    "query",
                    "insert",
                ],
                "service": ["create", "update", "delete", "get", "process", "handle", "execute"],
                "factory": ["create", "make", "build", "from_"],
                "builder": ["build", "with_", "set_", "add_"],
                "prototype": ["clone", "copy"],
                "adapter": ["adapt", "convert", "transform", "map"],
                "composite": ["add", "remove", "get_child", "children"],
                "facade": ["initialize", "start", "stop"],
                "proxy": ["get", "set", "access", "request", "forward"],
                "strategy": ["execute", "calculate", "compute", "run"],
                "observer": ["attach", "detach", "notify", "subscribe", "register", "emit"],
                "command": ["execute", "undo", "redo", "run"],
                "chain": ["handle", "process", "set_next", "do_filter"],
                "template_method": ["template", "build", "process"],
                "mediator": ["notify", "send", "mediate", "communicate"],
                "memento": ["save", "restore", "snapshot", "get_state", "set_state"],
                "state": ["handle", "change", "transition", "enter", "exit"],
            },
        },
        PatternLanguage.TYPESCRIPT: {
            "class_keywords": {
                "repository": ["Repository", "Repo", "DAO", "repository", "repo"],
                "service": ["Service", "Handler", "Manager", "service", "handler"],
                "factory": ["Factory", "Creator", "Maker", "factory"],
                "singleton": ["Singleton", "Instance", "Manager", "singleton"],
                "builder": ["Builder", "builder"],
                "prototype": ["Prototype", "prototype", "Cloneable", "cloneable"],
                "adapter": ["Adapter", "Wrapper", "adapter", "wrapper"],
                "bridge": ["Bridge", "bridge"],
                "composite": ["Composite", "Component", "Node", "Leaf", "composite"],
                "decorator": ["Decorator", "decorator"],
                "facade": ["Facade", "facade"],
                "proxy": ["Proxy", "proxy"],
                "strategy": ["Strategy", "strategy"],
                "observer": [
                    "Observer",
                    "Listener",
                    "Subscriber",
                    "Subject",
                    "observer",
                    "listener",
                ],
                "command": ["Command", "Action", "Operation", "command"],
                "chain": ["Chain", "Handler", "Middleware", "chain", "handler", "middleware"],
                "template_method": ["Template", "template"],
                "mediator": ["Mediator", "mediator"],
                "memento": ["Memento", "Snapshot", "memento"],
                "state": ["State", "Context", "state"],
            },
            "method_keywords": {
                "repository": [
                    "find",
                    "save",
                    "delete",
                    "update",
                    "get",
                    "list",
                    "create",
                    "remove",
                    "query",
                    "insert",
                ],
                "service": ["create", "update", "delete", "get", "process", "handle", "execute"],
                "factory": ["create", "make", "build", "from"],
                "builder": ["build", "with", "set", "add"],
                "prototype": ["clone", "copy"],
                "adapter": ["adapt", "convert", "transform", "map"],
                "composite": ["add", "remove", "getChild", "children"],
                "facade": ["initialize", "start", "stop"],
                "proxy": ["get", "set", "access", "request"],
                "strategy": ["execute", "calculate", "compute", "run"],
                "observer": ["attach", "detach", "notify", "subscribe", "emit", "on"],
                "command": ["execute", "undo", "redo", "run"],
                "chain": ["handle", "process", "setNext"],
                "template_method": ["template", "build", "process"],
                "mediator": ["notify", "send", "mediate"],
                "memento": ["save", "restore", "snapshot"],
                "state": ["handle", "change", "transition"],
            },
        },
        PatternLanguage.JAVASCRIPT: {
            # JavaScript usa as mesmas configurações de TypeScript
            "class_keywords": {
                "repository": ["Repository", "Repo", "DAO", "repository", "repo"],
                "service": ["Service", "Handler", "Manager", "service", "handler"],
                "factory": ["Factory", "Creator", "Maker", "factory"],
                "singleton": ["Singleton", "Instance", "Manager", "singleton"],
                "builder": ["Builder", "builder"],
                "prototype": ["Prototype", "prototype"],
                "adapter": ["Adapter", "Wrapper", "adapter", "wrapper"],
                "bridge": ["Bridge", "bridge"],
                "composite": ["Composite", "Component", "composite"],
                "decorator": ["Decorator", "decorator"],
                "facade": ["Facade", "facade"],
                "proxy": ["Proxy", "proxy"],
                "strategy": ["Strategy", "strategy"],
                "observer": ["Observer", "Listener", "Subject", "observer", "listener"],
                "command": ["Command", "command"],
                "chain": ["Handler", "Middleware", "handler", "middleware"],
                "template_method": ["Template", "template"],
                "mediator": ["Mediator", "mediator"],
                "memento": ["Memento", "memento"],
                "state": ["State", "Context", "state"],
            },
            "method_keywords": {
                "repository": ["find", "save", "delete", "update", "get", "create"],
                "service": ["create", "update", "delete", "get", "process", "handle"],
                "factory": ["create", "make", "build"],
                "builder": ["build", "with", "set"],
                "prototype": ["clone"],
                "adapter": ["adapt", "convert"],
                "composite": ["add", "remove"],
                "facade": ["init", "start", "stop"],
                "proxy": ["get", "set"],
                "strategy": ["execute", "calculate"],
                "observer": ["attach", "detach", "notify", "subscribe", "emit", "on"],
                "command": ["execute", "undo", "redo"],
                "chain": ["handle", "process", "setNext"],
                "template_method": ["template", "build"],
                "mediator": ["notify", "send"],
                "memento": ["save", "restore", "snapshot"],
                "state": ["handle", "change"],
            },
        },
        PatternLanguage.YAML: {
            # YAML tem padrões de estrutura
            "structural_keywords": {
                "composite": ["service", "deployment", "container", "job", "pod"],
                "facade": ["api", "gateway", "ingress", "service"],
                "proxy": ["proxy", "sidecar", "ambassador"],
                "adapter": ["adapter", "transform"],
                "template_method": ["template", "workflow"],
            }
        },
        PatternLanguage.JSON: {
            # JSON tem padrões de estrutura
            "structural_keywords": {
                "composite": ["services", "components", "modules"],
                "facade": ["api", "endpoints"],
                "adapter": ["adapters", "transformers"],
            }
        },
    }

    def __init__(self):
        """Inicializa o detector multi-linguagem."""
        self._analyzed_files: dict[str, dict] = {}

    def discover_patterns(
        self, code: str, filename: str, language: PatternLanguage
    ) -> list[PatternMatch]:
        """
        Descobre padrões no código baseado na linguagem.

        Args:
            code: Conteúdo do código/config
            filename: Nome do arquivo
            language: Linguagem do código

        Returns:
            Lista de padrões detectados com confiança
        """
        if language == PatternLanguage.PYTHON:
            return self._discover_python_patterns(code, filename)
        elif language in (PatternLanguage.TYPESCRIPT, PatternLanguage.JAVASCRIPT):
            return self._discover_js_ts_patterns(code, filename, language)
        elif language == PatternLanguage.YAML:
            return self._discover_yaml_patterns(code, filename)
        elif language == PatternLanguage.JSON:
            return self._discover_json_patterns(code, filename)
        else:
            logger.warning("unsupported_language", language=language)
            return []

    def _discover_python_patterns(self, code: str, filename: str) -> list[PatternMatch]:
        """Descobre padrões em Python."""
        from ..pattern_discovery import PatternDiscovery

        discovery = PatternDiscovery()
        raw_patterns = discovery.identify_patterns(code, filename)

        # Converter dicts para PatternMatch
        patterns = []
        for p in raw_patterns:
            patterns.append(
                PatternMatch(
                    name=p.get("name", "unknown"),
                    confidence=p.get("confidence", 0.0),
                    class_name=p.get("class_name"),
                    filename=p.get("filename", filename),
                    language=PatternLanguage.PYTHON.value,
                    methods=p.get("methods", []),
                )
            )

        return patterns

    def _discover_js_ts_patterns(
        self, code: str, filename: str, language: PatternLanguage
    ) -> list[PatternMatch]:
        """Descobre padrões em TypeScript/JavaScript."""
        patterns = []
        config = self.LANGUAGE_PATTERNS[language]

        try:
            # Analisar classes
            classes_info = self._extract_js_ts_classes(code, filename)

            for class_info in classes_info:
                class_patterns = self._analyze_js_ts_class(class_info, config)
                for pattern_name, confidence in class_patterns.items():
                    if confidence >= 0.3:  # Threshold reduzido para capturar mais padrões
                        patterns.append(
                            PatternMatch(
                                name=pattern_name,
                                confidence=round(confidence, 2),
                                class_name=class_info["name"],
                                filename=filename,
                                language=language.value,
                                methods=class_info.get("methods", []),
                            )
                        )

        except Exception as e:
            logger.error("js_ts_pattern_detection_failed", filename=filename, error=str(e))

        return patterns

    def _discover_yaml_patterns(self, code: str, filename: str) -> list[PatternMatch]:
        """Descobre padrões estruturais em YAML."""
        patterns = []
        self.LANGUAGE_PATTERNS[PatternLanguage.YAML]

        try:
            # Detectar tipo de arquivo YAML
            is_k8s = self._detect_yaml_type(code) == "kubernetes"
            is_compose = self._detect_yaml_type(code) == "docker-compose"
            is_ci = self._detect_yaml_type(code) in ["github-actions", "gitlab-ci", "circleci"]

            # Composite: múltiplos serviços/componentes
            if is_k8s or is_compose:
                services = self._count_yaml_services(code)
                if services >= 2:
                    patterns.append(
                        PatternMatch(
                            name="composite",
                            confidence=min(0.9, 0.3 + (services * 0.1)),
                            filename=filename,
                            language=PatternLanguage.YAML.value,
                        )
                    )
                # Para Kubernetes, mesmo com 0 ou 1 serviço, detectamos composite
                # porque tem spec.containers, metadata, etc.
                elif is_k8s:
                    patterns.append(
                        PatternMatch(
                            name="composite",
                            confidence=0.5,
                            filename=filename,
                            language=PatternLanguage.YAML.value,
                        )
                    )

            # Facade: API Gateway/Ingress
            if is_k8s:
                has_ingress = "kind: Ingress" in code or "Ingress" in code
                has_gateway = "kind: Gateway" in code or "Gateway" in code
                if has_ingress or has_gateway:
                    patterns.append(
                        PatternMatch(
                            name="facade",
                            confidence=0.7,
                            filename=filename,
                            language=PatternLanguage.YAML.value,
                        )
                    )

            # Template Method: workflows/pipelines
            if is_ci:
                patterns.append(
                    PatternMatch(
                        name="template_method",
                        confidence=0.6,
                        filename=filename,
                        language=PatternLanguage.YAML.value,
                    )
                )

        except Exception as e:
            logger.error("yaml_pattern_detection_failed", filename=filename, error=str(e))

        return patterns

    def _discover_json_patterns(self, code: str, filename: str) -> list[PatternMatch]:
        """Descobre padrões estruturais em JSON."""
        patterns = []

        try:
            import json

            data = json.loads(code)

            # Composite: múltiplos componentes/serviços ou arrays
            if "services" in data and len(data["services"]) >= 2:
                patterns.append(
                    PatternMatch(
                        name="composite",
                        confidence=0.8,
                        filename=filename,
                        language=PatternLanguage.JSON.value,
                    )
                )

            # Detectar arrays de objetos (composite)
            for key, value in data.items():
                if isinstance(value, list) and len(value) >= 1:
                    patterns.append(
                        PatternMatch(
                            name="composite",
                            confidence=0.5,
                            filename=filename,
                            language=PatternLanguage.JSON.value,
                        )
                    )
                    break

            # Facade: API/endpoints ou pagination
            if "endpoints" in data or "api" in data or "pagination" in data:
                patterns.append(
                    PatternMatch(
                        name="facade",
                        confidence=0.7,
                        filename=filename,
                        language=PatternLanguage.JSON.value,
                    )
                )

            # Proxy: config com múltiplas seções
            if len([k for k, v in data.items() if isinstance(v, dict)]) >= 2:
                patterns.append(
                    PatternMatch(
                        name="proxy",
                        confidence=0.4,
                        filename=filename,
                        language=PatternLanguage.JSON.value,
                    )
                )

        except json.JSONDecodeError:
            pass  # Não é JSON válido

        return patterns

    def _extract_js_ts_classes(self, code: str, filename: str) -> list[dict[str, Any]]:
        """Extrai informações de classes TypeScript/JavaScript."""
        classes = []

        # Padrão regex para classes - mais simples e robusto
        # Captura: nome, extends (implements é ignorado)
        class_pattern = r"\bclass\s+(\w+)(?:\s*<[^>]*>)?\s*(?:extends\s+(\w+))?(?:\s+implements\s+[\w\s,\{]+)?\s*\{"

        for match in re.finditer(class_pattern, code, re.MULTILINE):
            name = match.group(1)  # Nome da classe
            extends = match.group(2) if match.lastindex >= 2 else None  # Classe base
            start_pos = match.end()

            # Encontrar o corpo da classe
            brace_pos = self._find_matching_brace(code, start_pos)
            class_body = code[start_pos:brace_pos] if brace_pos else ""

            # Extrair métodos
            methods = self._extract_js_ts_methods(class_body)

            # Extrair atributos (via regex no corpo)
            attributes = self._extract_js_ts_attributes(class_body)

            # Extrair decorators da linha anterior à classe
            decorators = []
            line_start = code.rfind("\n", 0, match.start()) + 1
            line_before = code[line_start : match.start()]
            for decorator_match in re.finditer(r"@(\w+)", line_before):
                decorators.append(f"@{decorator_match.group(1)}")

            classes.append(
                {
                    "name": name,
                    "extends": extends,
                    "decorators": decorators,
                    "methods": methods,
                    "attributes": attributes,
                    "lineno": code[: match.start()].count("\n") + 1,
                }
            )

        return classes

    def _extract_js_ts_methods(self, class_body: str) -> list[dict[str, Any]]:
        """Extrai métodos de classe TS/JS."""
        methods = []

        # Padrão simplificado para métodos: captura nome e parâmetros
        # Formato: [async] [visibility] [static] name(params)[: returntype]
        method_pattern = r"(?:async\s+)?(?:public|private|protected\s+)?(?:static\s+)?(?:get\s+)?(?:set\s+)?(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)"

        for match in re.finditer(method_pattern, class_body):
            name = match.group(1)
            params = match.group(2) or ""

            methods.append(
                {
                    "name": name,
                    "async": False,  # Simplificado
                    "visibility": "public",  # Simplificado
                    "params": params,
                }
            )

        return methods

    def _extract_js_ts_attributes(self, class_body: str) -> list[str]:
        """Extrai atributos de classe TS/JS."""
        attributes = []

        # Padrão para this.attribute = ou this.attribute: (TS)
        attr_pattern = r"this\.(\w+)\s*[=:]"

        for match in re.finditer(attr_pattern, class_body):
            attributes.append(match.group(1))

        return attributes

    def _extract_decorators(self, decorators_str: str) -> list[str]:
        """Extrai decorators de uma string."""
        decorators = []
        for match in re.finditer(r"@(\w+)", decorators_str):
            decorators.append(f"@{match.group(1)}")
        return decorators

    def _analyze_js_ts_class(self, class_info: dict, config: dict) -> dict[str, float]:
        """Analisa uma classe para calcular confiança por padrão."""
        confidences = {}
        class_name_lower = class_info["name"].lower()
        class_info["name"]
        extends = class_info.get("extends", "").lower() if class_info.get("extends") else ""

        class_keywords = config.get("class_keywords", {})
        method_keywords = config.get("method_keywords", {})

        # Verificar cada padrão
        for pattern_name, keywords in class_keywords.items():
            confidence = 0.0

            # 1. Nome da classe contém keyword
            for keyword in keywords:
                if keyword.lower() in class_name_lower:
                    confidence += 0.4
                    break

            # 2. Herança indica certos padrões
            if extends:
                if pattern_name == "composite" and "component" in extends:
                    confidence += 0.2
                elif pattern_name == "decorator" and "decorator" in extends:
                    confidence += 0.3

            # 3. Métodos comuns
            methods = class_info.get("methods", [])
            method_names = [m["name"].lower() for m in methods]
            pattern_methods = method_keywords.get(pattern_name, [])

            matches = sum(1 for pm in pattern_methods for method in method_names if pm in method)
            if pattern_methods and matches > 0:
                confidence += min((matches / len(pattern_methods)) * 0.3, 0.3)

            # 4. Indicadores específicos
            attrs = class_info.get("attributes", [])

            if pattern_name == "singleton":
                if any("instance" in a.lower() for a in attrs):
                    confidence += 0.2
                # Verificar método getInstance
                if any(
                    "getinstance" in m.lower() or "get_instance" in m.lower() for m in method_names
                ):
                    confidence += 0.4
                # Nome comum para singleton
                if any(
                    suffix in class_name_lower
                    for suffix in ["connection", "manager", "instance", "database", "config"]
                ):
                    confidence += 0.15

            elif pattern_name == "observer":
                if any(
                    "observer" in a.lower() or "listener" in a.lower() or "subscriber" in a.lower()
                    for a in attrs
                ):
                    confidence += 0.2
                if any(
                    "attach" in m or "detach" in m or "notify" in m or "emit" in m
                    for m in method_names
                ):
                    confidence += 0.3

            elif pattern_name == "command":
                if "execute" in method_names:
                    confidence += 0.3

            elif pattern_name == "chain":
                if "handle" in method_names:
                    confidence += 0.3
                if any("next" in m.lower() for m in method_names):
                    confidence += 0.1

            elif pattern_name == "builder":
                if "build" in method_names:
                    confidence += 0.3
                if any(m.startswith("with") or m.startswith("set") for m in method_names):
                    confidence += 0.1

            # 5. Decorators
            decorators = class_info.get("decorators", [])
            if pattern_name == "decorator" and any("decorator" in d.lower() for d in decorators):
                confidence += 0.3

            confidences[pattern_name] = min(confidence, 1.0)

        return confidences

    def _detect_yaml_type(self, code: str) -> str:
        """Detecta o tipo de arquivo YAML."""
        if "kind:" in code and "apiVersion:" in code:
            return "kubernetes"
        elif "services:" in code and "version:" in code:
            return "docker-compose"
        elif "on:" in code and "jobs:" in code:
            return "github-actions"
        elif "stages:" in code or "image:" in code:
            return "gitlab-ci"
        return "unknown"

    def _count_yaml_services(self, code: str) -> int:
        """Conta serviços em arquivo YAML."""
        services_count = 0

        # Verificar se estamos na seção services
        in_services = False
        indent_level = 0

        for line in code.split("\n"):
            stripped = line.strip()

            # Entrar na seção services
            if stripped.startswith("services:"):
                in_services = True
                indent_level = len(line) - len(line.lstrip())
                continue

            if in_services:
                # Se linha vazia ou comentário, skip
                if not stripped or stripped.startswith("#"):
                    continue

                # Calcular indentação atual
                current_indent = len(line) - len(line.lstrip())

                # Se indentação voltou ao nível ou abaixo de services, sair
                if current_indent <= indent_level:
                    break

                # Se indentação é services: + 2 espaços e termina com :,
                # e não é um sub-atributo (indentação seguinte não é maior)
                if current_indent == indent_level + 2 and ":" in line:
                    # Verificar se é um nome de serviço (letras e números)
                    service_name = line.split(":")[0].strip()
                    if service_name and service_name.replace("_", "").replace("-", "").isalnum():
                        services_count += 1

        return services_count

    def _find_matching_brace(self, code: str, start: int) -> Optional[int]:
        """Encontra a closing brace."""
        brace_count = 1
        i = start
        while i < len(code) and brace_count > 0:
            if code[i] == "{":
                brace_count += 1
            elif code[i] == "}":
                brace_count -= 1
            i += 1
        return i if brace_count == 0 else None

    def get_supported_languages(self) -> list[str]:
        """Retorna lista de linguagens suportadas."""
        return [lang.value for lang in PatternLanguage]

    def get_language_patterns(self, language: str) -> list[str]:
        """Retorna padrões disponíveis para uma linguagem."""
        try:
            lang_enum = PatternLanguage(language)
            config = self.LANGUAGE_PATTERNS[lang_enum]
            return list(config["class_keywords"].keys())
        except (ValueError, KeyError):
            return []

    def detect_language(self, filename: str) -> PatternLanguage:
        """Detecta linguagem baseado na extensão do arquivo.

        Args:
            filename: Nome do arquivo

        Returns:
            PatternLanguage detectada
        """
        extension_map = {
            ".py": PatternLanguage.PYTHON,
            ".ts": PatternLanguage.TYPESCRIPT,
            ".tsx": PatternLanguage.TYPESCRIPT,
            ".js": PatternLanguage.JAVASCRIPT,
            ".jsx": PatternLanguage.JAVASCRIPT,
            ".mjs": PatternLanguage.JAVASCRIPT,
            ".cjs": PatternLanguage.JAVASCRIPT,
            ".yaml": PatternLanguage.YAML,
            ".yml": PatternLanguage.YAML,
            ".json": PatternLanguage.JSON,
        }

        for ext, lang in extension_map.items():
            if filename.endswith(ext):
                return lang

        # Default para Python se extensão não reconhecida
        return PatternLanguage.PYTHON
