"""
PatternDiscovery - Identificação de padrões de design no código.

Responsável por:
- Identificar padrões de design (Repository, Service, Factory, Singleton, etc.)
- Analisar estrutura de classes e métodos
- Calcular frequência e confiança de padrões
- Sugerir aplicação de padrões onde apropriado
"""

import ast
from collections import defaultdict
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()


class PatternDiscovery:
    """Descoberta de padrões de design em código Python."""

    # Padrões pré-configurados com suas características
    KNOWN_PATTERNS = {
        # === Padrões Criacionais ===
        "repository": {
            "keywords": ["repository", "repo", "dao"],
            "common_methods": [
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
            "naming_suffix": ["Repository", "Repo", "DAO"],
            "category": "creational",
        },
        "service": {
            "keywords": ["service", "handler", "manager"],
            "common_methods": [
                "create",
                "update",
                "delete",
                "get",
                "process",
                "handle",
                "execute",
                "run",
            ],
            "naming_suffix": ["Service", "Handler", "Manager"],
            "category": "creational",
        },
        "factory": {
            "keywords": ["factory", "creator", "maker"],
            "common_methods": ["create", "make", "build", "from_", "create_instance"],
            "naming_suffix": ["Factory", "Creator", "Maker"],
            "category": "creational",
        },
        "builder": {
            "keywords": ["builder"],
            "common_methods": ["build", "with_", "set_", "add_", "create"],
            "naming_suffix": ["Builder"],
            "indicators": ["_build", "_result"],
            "category": "creational",
        },
        "prototype": {
            "keywords": ["prototype", "clone"],
            "common_methods": ["clone", "copy", "duplicate"],
            "naming_suffix": ["Prototype", "Cloneable"],
            "category": "creational",
        },
        "singleton": {
            "keywords": ["instance", "singleton"],
            "indicators": ["_instance", "__new__", "_lock", "_initialized"],
            "naming_suffix": ["Manager", "Connection", "Instance", "Engine"],
            "category": "creational",
        },
        # === Padrões Estruturais ===
        "adapter": {
            "keywords": ["adapter", "wrapper"],
            "common_methods": ["adapt", "convert", "transform", "map", "translate"],
            "naming_suffix": ["Adapter", "Wrapper"],
            "indicators": ["_adaptee", "_target"],
            "category": "structural",
        },
        "bridge": {
            "keywords": ["bridge"],
            "common_methods": ["operation", "implement_", "execute"],
            "naming_suffix": ["Bridge"],
            "indicators": ["_abstraction", "_implementation"],
            "category": "structural",
        },
        "composite": {
            "keywords": ["composite", "component", "node", "leaf"],
            "common_methods": ["add", "remove", "get_child", "children", "operation"],
            "naming_suffix": ["Composite", "Component", "Node", "Leaf"],
            "indicators": ["_children", "parent"],
            "category": "structural",
        },
        "decorator": {
            "keywords": ["decorator", "wrapper"],
            "indicators": ["wrapper", "@wraps", "functools", "_wrapped", "_component"],
            "structure": ["inner_function", "wrapper_function"],
            "naming_suffix": ["Decorator"],
            "category": "structural",
        },
        "facade": {
            "keywords": ["facade", "api"],
            "common_methods": ["initialize", "start", "stop", "execute", "run"],
            "naming_suffix": ["Facade", "API", "Client"],
            "indicators": ["_subsystem", "_components"],
            "category": "structural",
        },
        "proxy": {
            "keywords": ["proxy"],
            "common_methods": ["get", "set", "access", "request", "forward"],
            "naming_suffix": ["Proxy"],
            "indicators": ["_real_subject", "_subject", "_wrapped", "__getattr__"],
            "category": "structural",
        },
        # === Padrões Comportamentais ===
        "strategy": {
            "keywords": ["strategy"],
            "common_methods": [
                "execute",
                "execute_algorithm",
                "calculate",
                "process",
                "do_",
                "compute",
            ],
            "naming_suffix": ["Strategy", "Algorithm", "Policy"],
            "category": "behavioral",
        },
        "observer": {
            "keywords": ["observer", "listener", "subscriber", "notifier"],
            "common_methods": [
                "attach",
                "detach",
                "notify",
                "update",
                "on_",
                "emit",
                "subscribe",
                "unsubscribe",
            ],
            "naming_suffix": ["Observer", "Listener", "Subscriber", "Notifier", "Subject"],
            "indicators": ["_observers", "_listeners", "_subscribers"],
            "category": "behavioral",
        },
        "command": {
            "keywords": ["command", "action", "operation"],
            "common_methods": ["execute", "undo", "redo", "run"],
            "naming_suffix": ["Command", "Action", "Operation"],
            "category": "behavioral",
        },
        "chain": {
            "keywords": ["chain", "handler", "middleware", "pipeline"],
            "common_methods": ["handle", "process", "set_next", "do_filter", "execute"],
            "naming_suffix": ["Chain", "Handler", "Middleware", "Filter"],
            "indicators": ["_next", "next_handler"],
            "category": "behavioral",
        },
        "template_method": {
            "keywords": ["template"],
            "common_methods": ["template_method", "build", "process", "execute"],
            "naming_suffix": ["Template"],
            "indicators": ["_steps", "_hooks"],
            "category": "behavioral",
        },
        "mediator": {
            "keywords": ["mediator", "colleague"],
            "common_methods": ["notify", "send", "mediate", "communicate"],
            "naming_suffix": ["Mediator"],
            "indicators": ["_colleagues", "_components"],
            "category": "behavioral",
        },
        "memento": {
            "keywords": ["memento", "snapshot", "state"],
            "common_methods": ["save", "restore", "get_state", "set_state", "create_snapshot"],
            "naming_suffix": ["Memento", "Snapshot", "State"],
            "category": "behavioral",
        },
        "state": {
            "keywords": ["state", "context"],
            "common_methods": ["handle", "change_state", "transition", "enter", "exit"],
            "naming_suffix": ["State", "Context"],
            "indicators": ["_state", "_context"],
            "category": "behavioral",
        },
    }

    def __init__(self):
        """Inicializa o PatternDiscovery."""
        self.patterns_db = dict(self.KNOWN_PATTERNS)
        self._code_samples: Dict[str, str] = {}
        self._analyzed_patterns: Dict[str, List[Dict]] = defaultdict(list)

    def get_known_patterns(self) -> List[str]:
        """Retorna lista de padrões conhecidos."""
        return list(self.patterns_db.keys())

    def get_patterns_by_category(self, category: str) -> List[str]:
        """
        Retorna padrões de uma categoria específica.

        Args:
            category: 'creational', 'structural', ou 'behavioral'

        Returns:
            Lista de nomes de padrões da categoria
        """
        return [
            name for name, config in self.patterns_db.items() if config.get("category") == category
        ]

    def get_pattern_categories(self) -> Dict[str, List[str]]:
        """
        Retorna todos os padrões agrupados por categoria.

        Returns:
            Dict com 'creational', 'structural', 'behavioral'
        """
        categories = {"creational": [], "structural": [], "behavioral": []}
        for name, config in self.patterns_db.items():
            cat = config.get("category", "behavioral")
            categories[cat].append(name)
        return categories

    def get_pattern_info(self, pattern_name: str) -> Optional[Dict[str, Any]]:
        """
        Retorna informações detalhadas sobre um padrão.

        Args:
            pattern_name: Nome do padrão

        Returns:
            Dict com configuração do padrão ou None
        """
        pattern_config = self.patterns_db.get(pattern_name)
        if pattern_config:
            return {
                "name": pattern_name,
                "category": pattern_config.get("category", "behavioral"),
                "keywords": pattern_config.get("keywords", []),
                "common_methods": pattern_config.get("common_methods", []),
                "naming_suffix": pattern_config.get("naming_suffix", []),
                "indicators": pattern_config.get("indicators", []),
            }
        return None

    def identify_patterns(self, code: str, filename: str = "<unknown>") -> List[Dict[str, Any]]:
        """
        Identifica padrões de design em um código.

        Args:
            code: Código fonte Python
            filename: Nome do arquivo (para contexto)

        Returns:
            Lista de padrões encontrados com confiança
        """
        patterns_found = []

        try:
            tree = ast.parse(code)
        except SyntaxError:
            logger.warning("syntax_error_in_pattern_discovery", filename=filename)
            return patterns_found

        # Analisar cada classe
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_patterns = self._analyze_class_for_patterns(node, code, filename)
                patterns_found.extend(class_patterns)

        # Analisar decorators
        decorator_patterns = self._analyze_decorators(code, filename)
        patterns_found.extend(decorator_patterns)

        return patterns_found

    def _analyze_class_for_patterns(
        self, class_node: ast.ClassDef, code: str, filename: str
    ) -> List[Dict[str, Any]]:
        """Analisa uma classe para identificar padrões."""
        patterns = []

        for pattern_name, pattern_config in self.patterns_db.items():
            confidence = self._calculate_pattern_confidence(
                class_node, pattern_name, pattern_config
            )

            if confidence >= 0.5:
                patterns.append(
                    {
                        "name": pattern_name,
                        "class_name": class_node.name,
                        "filename": filename,
                        "confidence": round(confidence, 2),
                        "methods": [
                            n.name
                            for n in class_node.body
                            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                        ],
                    }
                )

        return patterns

    def _calculate_pattern_confidence(
        self, class_node: ast.ClassDef, pattern_name: str, pattern_config: Dict
    ) -> float:
        """Calcula confiança de que a classe implementa o padrão."""
        confidence = 0.0

        # 1. Verificar nome da classe
        class_name_lower = class_node.name.lower()
        for suffix in pattern_config.get("naming_suffix", []):
            if class_node.name.endswith(suffix) or suffix.lower() in class_name_lower:
                confidence += 0.3
                break

        # 2. Verificar keywords no nome
        for keyword in pattern_config.get("keywords", []):
            if keyword in class_name_lower:
                confidence += 0.2
                break

        # 3. Verificar métodos comuns
        methods = [
            n.name
            for n in class_node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        common_methods = pattern_config.get("common_methods", [])

        method_matches = 0
        for method in methods:
            for common in common_methods:
                if common in method.lower():
                    method_matches += 1
                    break

        if common_methods:
            method_ratio = min(method_matches / len(common_methods), 1.0)
            confidence += method_ratio * 0.5

        # 4. Verificar indicadores especiais em atributos
        for indicator in pattern_config.get("indicators", []):
            # Verificar em atributos da classe
            for node in class_node.body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and indicator in target.id:
                            confidence += 0.15
                # Verificar em AnnAssign (anotado)
                elif isinstance(node, ast.AnnAssign):
                    if isinstance(node.target, ast.Name) and indicator in node.target.id:
                        confidence += 0.15

        # 5. Detecção específica por padrão
        confidence += self._pattern_specific_checks(class_node, pattern_name, methods)

        # 6. Bonus para múltiplas heranças (Composite, Bridge, etc)
        if pattern_name in ["composite", "bridge", "decorator", "proxy"]:
            if len(class_node.bases) > 0:
                confidence += 0.1

        return min(confidence, 1.0)

    def _pattern_specific_checks(
        self, class_node: ast.ClassDef, pattern_name: str, methods: List[str]
    ) -> float:
        """Verifica específicos de padrões individuais."""
        bonus = 0.0

        # === Singleton ===
        if pattern_name == "singleton":
            has_new = any(
                n.name == "__new__" for n in class_node.body if isinstance(n, ast.FunctionDef)
            )
            has_instance = any("_instance" in a for a in self._get_all_attribute_names(class_node))
            has_lock = any("_lock" in a for a in self._get_all_attribute_names(class_node))
            if has_new:
                bonus += 0.3
            if has_instance:
                bonus += 0.2
            if has_lock:
                bonus += 0.1

        # === Observer ===
        elif pattern_name == "observer":
            observer_methods = [
                "attach",
                "detach",
                "notify",
                "subscribe",
                "unsubscribe",
                "register",
                "unregister",
            ]
            matches = sum(1 for m in methods if any(obs in m.lower() for obs in observer_methods))
            if matches >= 2:
                bonus += 0.3
            # Verificar atributos de lista de observers
            attrs = self._get_all_attribute_names(class_node)
            if any("observer" in a or "listener" in a or "subscriber" in a for a in attrs):
                bonus += 0.2

        # === Strategy ===
        elif pattern_name == "strategy":
            # Strategy geralmente tem métodos execute/execute_algorithm
            has_execute = any(
                "execute" in m.lower() or "compute" in m.lower() or "calculate" in m.lower()
                for m in methods
            )
            if has_execute:
                bonus += 0.2
            # Strategy frequentemente não tem estado (poucos atributos além de privados)
            attrs = self._get_all_attribute_names(class_node)
            non_private_attrs = [a for a in attrs if not a.startswith("_")]
            if len(non_private_attrs) <= 2:
                bonus += 0.1

        # === Command ===
        elif pattern_name == "command":
            has_execute = "execute" in methods
            has_undo = "undo" in methods
            has_redo = "redo" in methods
            if has_execute:
                bonus += 0.3
            if has_undo or has_redo:
                bonus += 0.2

        # === Chain of Responsibility ===
        elif pattern_name == "chain":
            has_handle = "handle" in methods or "process" in methods
            has_next = "set_next" in methods or any("next" in m.lower() for m in methods)
            if has_handle:
                bonus += 0.2
            if has_next:
                bonus += 0.2
            # Verificar atributo _next
            attrs = self._get_all_attribute_names(class_node)
            if any("_next" in a or "next_handler" in a for a in attrs):
                bonus += 0.2

        # === Composite ===
        elif pattern_name == "composite":
            has_add = "add" in methods or "append" in methods
            has_remove = "remove" in methods or "delete" in methods
            has_child = "child" in methods or "get" in methods
            has_children_attr = any(
                "children" in a for a in self._get_all_attribute_names(class_node)
            )
            if has_add and has_remove:
                bonus += 0.2
            if has_children_attr:
                bonus += 0.2
            if has_child:
                bonus += 0.1

        # === Decorator ===
        elif pattern_name == "decorator":
            # Decorator classes geralmente tem __call__ ou wrapper
            has_call = "__call__" in methods
            has_wrapper = "wrapper" in methods
            attrs = self._get_all_attribute_names(class_node)
            has_wrapped = any("_wrapped" in a or "_component" in a or "_func" in a for a in attrs)
            if has_call or has_wrapper:
                bonus += 0.3
            if has_wrapped:
                bonus += 0.2

        # === Proxy ===
        elif pattern_name == "proxy":
            has_getattr = "__getattr__" in methods or "__getattribute__" in methods
            attrs = self._get_all_attribute_names(class_node)
            has_wrapped = any(
                "_wrapped" in a or "_subject" in a or "_real" in a or "_target" in a for a in attrs
            )
            if has_getattr:
                bonus += 0.3
            if has_wrapped:
                bonus += 0.2

        # === Adapter ===
        elif pattern_name == "adapter":
            attrs = self._get_all_attribute_names(class_node)
            has_adaptee = any("_adaptee" in a or "_wrapped" in a or "_subject" in a for a in attrs)
            has_adapt_method = any(
                "adapt" in m.lower() or "convert" in m.lower() or "transform" in m.lower()
                for m in methods
            )
            if has_adaptee:
                bonus += 0.2
            if has_adapt_method:
                bonus += 0.2

        # === Bridge ===
        elif pattern_name == "bridge":
            attrs = self._get_all_attribute_names(class_node)
            has_impl = any("_impl" in a or "implementation" in a for a in attrs)
            if has_impl:
                bonus += 0.3

        # === Facade ===
        elif pattern_name == "facade":
            # Facade tem muitos métodos que delegam para outros componentes
            if len(methods) >= 5:
                bonus += 0.1
            attrs = self._get_all_attribute_names(class_node)
            has_components = any(
                "_subsystem" in a or "_component" in a or "_service" in a for a in attrs
            )
            if has_components:
                bonus += 0.2

        # === Builder ===
        elif pattern_name == "builder":
            has_build = "build" in methods
            has_with = any(
                m.startswith("with_") or m.startswith("set_") or m.startswith("add_")
                for m in methods
            )
            has_result = any(
                "_result" in a or "_built" in a or "_product" in a
                for a in self._get_all_attribute_names(class_node)
            )
            if has_build:
                bonus += 0.2
            if has_with:
                bonus += 0.2
            if has_result:
                bonus += 0.1

        # === Prototype ===
        elif pattern_name == "prototype":
            has_clone = "clone" in methods or "copy" in methods
            if has_clone:
                bonus += 0.4

        # === Template Method ===
        elif pattern_name == "template_method":
            has_template = "template" in methods or "build" in methods or "process" in methods
            # Verificar métodos abstratos (métodos que levantam NotImplementedError)
            has_abstract = any("_abstract" in a for a in self._get_all_attribute_names(class_node))
            if has_template:
                bonus += 0.2
            if has_abstract:
                bonus += 0.2

        # === Mediator ===
        elif pattern_name == "mediator":
            has_notify = "notify" in methods or "send" in methods or "mediate" in methods
            attrs = self._get_all_attribute_names(class_node)
            has_colleagues = any("_colleague" in a or "_component" in a for a in attrs)
            if has_notify:
                bonus += 0.2
            if has_colleagues:
                bonus += 0.2

        # === Memento ===
        elif pattern_name == "memento":
            has_save = "save" in methods or "create" in methods or "snapshot" in methods
            has_restore = "restore" in methods or "apply" in methods or "rollback" in methods
            if has_save:
                bonus += 0.2
            if has_restore:
                bonus += 0.2

        # === State ===
        elif pattern_name == "state":
            has_handle = "handle" in methods or "process" in methods or "execute" in methods
            has_change = "change" in methods or "transition" in methods or "set" in methods
            if has_handle:
                bonus += 0.2
            if has_change:
                bonus += 0.2

        return bonus

    def _get_all_attribute_names(self, class_node: ast.ClassDef) -> List[str]:
        """Extrai todos os nomes de atributos da classe."""
        attrs = []
        for node in class_node.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        attrs.append(target.id)
                    elif isinstance(target, ast.Attribute):
                        # Atributos aninhados como self.x.y = ...
                        if isinstance(target.value, ast.Name) and target.value.id == "self":
                            attrs.append(target.attr)
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    attrs.append(node.target.id)
                elif isinstance(node.target, ast.Attribute):
                    if isinstance(node.target.value, ast.Name) and node.target.value.id == "self":
                        attrs.append(node.target.attr)
            # Verificar atributos em __init__
            elif (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "__init__"
            ):
                for body_node in ast.walk(node):
                    if isinstance(body_node, ast.Assign):
                        for target in body_node.targets:
                            if isinstance(target, ast.Attribute):
                                if isinstance(target.value, ast.Name) and target.value.id == "self":
                                    attrs.append(target.attr)
        return attrs

    def _analyze_decorators(self, code: str, filename: str) -> List[Dict[str, Any]]:
        """Analisa código para identificar padrões decorator."""
        patterns = []

        # Verificar presença de wrapper + inner function
        if "def wrapper" in code and "def " in code:
            # Verificar estrutura típica de decorator
            tree = ast.parse(code)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Verificar se retorna uma função interna
                    for child in ast.walk(node):
                        if isinstance(child, ast.FunctionDef) and child.name == "wrapper":
                            patterns.append(
                                {
                                    "name": "decorator",
                                    "function_name": node.name,
                                    "filename": filename,
                                    "confidence": 0.85,
                                }
                            )
                            break

        return patterns

    def analyze_pattern_frequency(self, files: Dict[str, str], pattern_name: str) -> Dict[str, Any]:
        """
        Analisa frequência de um padrão em múltiplos arquivos.

        Args:
            files: Dict {filename: code}
            pattern_name: Nome do padrão para buscar

        Returns:
            Dict com count, locations, e average_confidence
        """
        occurrences = []
        total_confidence = 0.0

        for filename, code in files.items():
            patterns = self.identify_patterns(code, filename)
            matching = [p for p in patterns if p["name"] == pattern_name]

            if matching:
                occurrences.append(filename)
                total_confidence += max(p["confidence"] for p in matching)

        return {
            "pattern": pattern_name,
            "count": len(occurrences),
            "locations": occurrences,
            "average_confidence": (
                round(total_confidence / len(occurrences), 2) if occurrences else 0.0
            ),
        }

    def calculate_pattern_confidence(self, files: Dict[str, str], pattern_name: str) -> float:
        """
        Calcula confiança agregada de um padrão no código.

        Args:
            files: Dict {filename: code}
            pattern_name: Nome do padrão

        Returns:
            Float de 0.0 a 1.0 representando confiança
        """
        if not files:
            return 0.0

        frequency = self.analyze_pattern_frequency(files, pattern_name)
        file_ratio = frequency["count"] / len(files)

        # Combinação: razão de arquivos + confiança média
        confidence = (file_ratio * 0.6) + (frequency["average_confidence"] * 0.4)

        return round(confidence, 2)

    def suggest_patterns(self, code: str, filename: str = "<unknown>") -> List[Dict[str, Any]]:
        """
        Sugere padrões que poderiam ser aplicados ao código.

        Args:
            code: Código fonte
            filename: Nome do arquivo

        Returns:
            Lista de sugestões com padrão e razão
        """
        suggestions = []

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return suggestions

        # Analisar cada classe
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_suggestions = self._suggest_for_class(node, filename)
                suggestions.extend(class_suggestions)

        # Analisar funções soltas
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and not self._is_nested_function(tree, node):
                func_suggestions = self._suggest_for_function(node, filename)
                suggestions.extend(func_suggestions)

        return suggestions

    def _suggest_for_class(self, class_node: ast.ClassDef, filename: str) -> List[Dict[str, Any]]:
        """Sugere padrões para uma classe."""
        suggestions = []
        methods = [
            n.name
            for n in class_node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]

        # Se tem muitos métodos de dados mas não parece Repository
        data_methods = ["get", "save", "delete", "find", "query", "insert", "update", "db"]
        has_data_access = any(
            any(keyword in m.lower() for keyword in data_methods) for m in methods
        )

        class_name_lower = class_node.name.lower()
        if has_data_access and not any(s in class_name_lower for s in ["repo", "service", "dao"]):
            suggestions.append(
                {
                    "pattern": "Repository",
                    "class": class_node.name,
                    "reason": "Classe com métodos de acesso a dados pode beneficiar do padrão Repository",
                    "confidence": 0.7,
                }
            )

        # Se tem muitas variações de create/build
        create_methods = [
            m
            for m in methods
            if "create" in m.lower() or "make" in m.lower() or "build" in m.lower()
        ]
        if len(create_methods) >= 3 and "factory" not in class_name_lower:
            suggestions.append(
                {
                    "pattern": "Factory",
                    "class": class_node.name,
                    "reason": f"{len(create_methods)} métodos de criação identificados; considere o padrão Factory",
                    "confidence": 0.65,
                }
            )

        return suggestions

    def _suggest_for_function(
        self, func_node: ast.FunctionDef, filename: str
    ) -> List[Dict[str, Any]]:
        """Sugere padrões para uma função."""
        suggestions = []

        # Função com muitos ifs retornando dicts semelhantes
        # pode sugerir Factory
        if func_node.body:
            return_stmts = list(ast.walk(func_node))
            dict_returns = [
                n
                for n in return_stmts
                if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict)
            ]

            if len(dict_returns) >= 3:
                suggestions.append(
                    {
                        "pattern": "Factory",
                        "function": func_node.name,
                        "reason": "Função com múltiplas construções de dict similares; considere padrão Factory",
                        "confidence": 0.6,
                    }
                )

        return suggestions

    def _is_nested_function(self, tree: ast.Module, func_node: ast.FunctionDef) -> bool:
        """Verifica se a função está aninhada em outra."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for child in ast.walk(node):
                    if child is func_node and node is not func_node:
                        return True
        return False

    def add_code_sample(self, filename: str, code: str) -> None:
        """Adiciona amostra de código para análise."""
        self._code_samples[filename] = code

    def extract_class_structure(self, code: str, filename: str = "<unknown>") -> Dict[str, Any]:
        """
        Extrai estrutura de classes do código.

        Args:
            code: Código fonte
            filename: Nome do arquivo

        Returns:
            Dict com nome, métodos, atributos, decorators
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return {"name": None, "methods": [], "attributes": [], "decorators": []}

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = []
                attributes = []
                decorators = []

                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_decorators = [
                            f"@{self._get_decorator_name(d)}" for d in item.decorator_list
                        ]
                        methods.append(
                            {
                                "name": item.name,
                                "decorators": method_decorators,
                                "args": [a.arg for a in item.args.args if a.arg],
                                "is_async": isinstance(item, ast.AsyncFunctionDef),
                            }
                        )

                    elif isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name):
                                attributes.append(target.id)

                return {
                    "name": node.name,
                    "methods": methods,
                    "attributes": attributes,
                    "decorators": decorators,
                    "bases": [self._get_name(base) for base in node.bases],
                }

        return {"name": None, "methods": [], "attributes": [], "decorators": []}

    def _get_decorator_name(self, decorator: ast.AST) -> str:
        """Extrai nome de decorator."""
        if isinstance(decorator, ast.Name):
            return decorator.id
        elif isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Name):
                return decorator.func.id
            elif isinstance(decorator.func, ast.Attribute):
                return decorator.func.attr
        elif isinstance(decorator, ast.Attribute):
            return decorator.attr
        return "<decorator>"

    def _get_name(self, node: ast.AST) -> str:
        """Extrai nome de um nó AST."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        return str(type(node).__name__)

    def detect_class_dependencies(self, class_name: str) -> List[str]:
        """
        Detecta dependências de uma classe analisando código armazenado.

        Args:
            class_name: Nome da classe

        Returns:
            Lista de classes/dependências encontradas
        """
        dependencies = []

        for filename, code in self._code_samples.items():
            try:
                tree = ast.parse(code)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    # Verificar __init__ para injeções via parâmetros
                    for item in node.body:
                        if (
                            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and item.name == "__init__"
                        ):
                            # Parâmetros do construtor
                            for arg in item.args.args:
                                if arg.arg and arg.arg != "self":
                                    dependencies.append(arg.arg)

                            # Atribuições a self dentro de __init__
                            for body_item in ast.walk(item):
                                if isinstance(body_item, ast.Assign):
                                    for target in body_item.targets:
                                        if (
                                            isinstance(target, ast.Attribute)
                                            and isinstance(target.value, ast.Name)
                                            and target.value.id == "self"
                                        ):
                                            # self.user_repo = ...
                                            attr_name = target.attr
                                            if (
                                                "repo" in attr_name.lower()
                                                or "service" in attr_name.lower()
                                                or "repository" in attr_name.lower()
                                            ):
                                                dependencies.append(attr_name)

                    # Verificar atributos de classe
                    for item in node.body:
                        if isinstance(item, ast.Assign):
                            for target in item.targets:
                                if isinstance(target, ast.Name) and (
                                    "repo" in target.id.lower() or "service" in target.id.lower()
                                ):
                                    dependencies.append(target.id)

        return list(set(dependencies))  # Remover duplicatas

    def generate_pattern_report(self, files: Dict[str, str]) -> Dict[str, Any]:
        """
        Gera relatório de padrões encontrados nos arquivos.

        Args:
            files: Dict {filename: code}

        Returns:
            Dict com resumo de padrões encontrados
        """
        all_patterns = defaultdict(list)
        total_files = len(files)

        for filename, code in files.items():
            patterns = self.identify_patterns(code, filename)
            for pattern in patterns:
                all_patterns[pattern["name"]].append(
                    {
                        "filename": filename,
                        "class_name": pattern.get(
                            "class_name", pattern.get("function_name", "N/A")
                        ),
                        "confidence": pattern["confidence"],
                    }
                )

        # Resumir por padrão
        pattern_summary = []
        for pattern_name, occurrences in all_patterns.items():
            avg_confidence = sum(o["confidence"] for o in occurrences) / len(occurrences)
            pattern_summary.append(
                {
                    "pattern": pattern_name,
                    "occurrences": len(occurrences),
                    "average_confidence": round(avg_confidence, 2),
                    "locations": [o["filename"] for o in occurrences],
                }
            )

        # Ordenar por ocorrências
        pattern_summary.sort(key=lambda x: x["occurrences"], reverse=True)

        return {
            "total_files": total_files,
            "patterns_found": len(all_patterns),
            "pattern_summary": pattern_summary,
            "raw_patterns": dict(all_patterns),
        }

    def export_pattern_graph(self, files: Dict[str, str]) -> Dict[str, Any]:
        """
        Exporta grafo de padrões para visualização.

        Args:
            files: Dict {filename: code}

        Returns:
            Dict com nodes e edges para grafo
        """
        nodes = []
        edges = []
        pattern_id = 0

        for filename, code in files.items():
            patterns = self.identify_patterns(code, filename)

            for pattern in patterns:
                node_id = f"pattern_{pattern_id}"
                label = f"{pattern['name']}\\n{pattern.get('class_name', '')}"
                nodes.append(
                    {
                        "id": node_id,
                        "label": label,
                        "pattern": pattern["name"],
                        "filename": filename,
                        "confidence": pattern["confidence"],
                    }
                )

                pattern_id += 1

        return {"nodes": nodes, "edges": edges, "total_patterns": pattern_id}
