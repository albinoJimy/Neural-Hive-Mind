"""
YAML Parser - Análise de arquivos YAML.

Suporta detecção de recursos Kubernetes, docker-compose, CI/CD configs.
"""
import re
from typing import Any, Dict, List, Optional

import structlog

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

logger = structlog.get_logger()


class YAMLParser:
    """Parser para arquivos YAML."""

    # Padrões para detecção de segredos
    SECRET_PATTERNS = [
        r'password\s*:\s*[\'"]?[\w]+',
        r'api_key\s*:\s*[\'"]?[\w-]+',
        r'secret\s*:\s*[\'"]?[\w-]+',
        r'token\s*:\s*[\'"]?[\w\.-]+',
        r'private_key\s*:\s*[\'"]?[A-Za-z0-9/+=]+',
        r'access_key\s*:\s*[\'"]?[\w-]+',
    ]

    # Padrões para detecção base64
    BASE64_PATTERN = r"[A-Za-z0-9+/]{20,}={0,2}"

    def __init__(self):
        """Inicializa o YAMLParser."""
        self._parsed_cache: Dict[str, Dict] = {}
        self._parse_errors: set = set()

    def parse(self, code: str, filename: str) -> Optional[Dict[str, Any]]:
        """
        Faz parsing de arquivo YAML.

        Args:
            code: Conteúdo YAML
            filename: Nome do arquivo

        Returns:
            Dict com chaves, estrutura, metadados
        """
        if not code or not code.strip():
            return {
                "keys": [],
                "has_secrets": False,
                "secret_keys": [],
                "has_base64": False,
                "document_count": 1,
                "kind": None,
                "ci_platform": None,
                "ci_type": None,
                "has_errors": False,
            }

        try:
            if YAML_AVAILABLE:
                return self._parse_with_yaml_lib(code, filename)
            else:
                logger.warning(
                    "yaml_not_available",
                    filename=filename,
                    message="Using regex-based fallback parser",
                )
                return self._parse_with_regex(code, filename)

        except Exception as e:
            logger.error("yaml_parse_error", filename=filename, error=str(e))
            self._parse_errors.add(filename)
            return None

    def _parse_with_yaml_lib(self, code: str, filename: str) -> Dict[str, Any]:
        """Parse usando biblioteca yaml."""
        try:
            # Tentar parsear múltiplos documentos
            docs = list(yaml.safe_load_all(code))

            result = {
                "keys": [],
                "has_secrets": False,
                "secret_keys": [],
                "has_base64": False,
                "document_count": len(docs),
                "kind": None,
                "ci_platform": None,
                "ci_type": None,
                "has_errors": False,
            }

            all_keys = set()

            for doc in docs:
                if doc is None:
                    continue

                # Extrair chaves do documento
                self._extract_keys_recursive(doc, all_keys, "")

                # Detectar tipo de recurso
                kind = doc.get("kind") if isinstance(doc, dict) else None
                if kind:
                    result["kind"] = kind

                # Detectar metadados Kubernetes
                if kind:
                    metadata = doc.get("metadata", {})
                    if isinstance(metadata, dict):
                        result["name"] = metadata.get("name")
                        result["namespace"] = metadata.get("namespace")
                        result["api_version"] = doc.get("apiVersion")

                # Detectar plataforma CI
                ci_platform = self._detect_ci_platform(doc)
                if ci_platform:
                    result["ci_platform"] = ci_platform
                    result["ci_type"] = ci_platform

            result["keys"] = list(all_keys)

            # Detectar segredos no código original
            result["has_secrets"], result["secret_keys"] = self._detect_secrets(code)
            result["has_base64"] = self._has_base64(code)

            return result

        except yaml.YAMLError as e:
            logger.debug("yaml_parse_failed", filename=filename, error=str(e))
            # Fallback para regex, mas marca erro
            result = self._parse_with_regex(code, filename)
            if result:
                result["has_errors"] = True
            return result

    def _parse_with_regex(self, code: str, filename: str) -> Dict[str, Any]:
        """Parse baseado em regex (fallback)."""
        result = {
            "keys": [],
            "has_secrets": False,
            "secret_keys": [],
            "has_base64": False,
            "document_count": code.count("---") + 1,
            "kind": None,
            "ci_platform": None,
            "ci_type": None,
            "has_errors": False,
        }

        # Extrair chaves de nível superior
        for match in re.finditer(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:", code, re.MULTILINE):
            result["keys"].append(match.group(1))

        # Detectar kind Kubernetes
        kind_match = re.search(r"kind:\s*([A-Za-z]+)", code)
        if kind_match:
            result["kind"] = kind_match.group(1)

        # Detectar nome Kubernetes
        name_match = re.search(r"name:\s*([A-Za-z0-9-]+)", code)
        if name_match:
            result["name"] = name_match.group(1)

        # Detectar segredos
        result["has_secrets"], result["secret_keys"] = self._detect_secrets(code)
        result["has_base64"] = self._has_base64(code)

        # Detectar plataforma CI
        result["ci_platform"] = self._detect_ci_platform_regex(code)
        if result["ci_platform"]:
            result["ci_type"] = result["ci_platform"]

        return result

    def _extract_keys_recursive(self, obj: Any, keys: set, prefix: str):
        """Extrai chaves recursivamente de um objeto."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                full_key = f"{prefix}.{key}" if prefix else key
                keys.add(full_key)
                self._extract_keys_recursive(value, keys, full_key)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                full_key = f"{prefix}[{i}]" if prefix else f"[{i}]"
                self._extract_keys_recursive(item, keys, full_key)

    def _detect_ci_platform(self, doc: Any) -> Optional[str]:
        """Detecta plataforma CI baseada no conteúdo."""

        def check_recursive(obj: Any) -> Optional[str]:
            """Busca recursivamente por indicadores de plataforma CI."""
            if isinstance(obj, dict):
                # GitHub Actions
                if "on" in obj or "runs-on" in obj:
                    return "github-actions"

                # GitLab CI
                if "stages" in obj:
                    return "gitlab-ci"
                if "image" in obj:
                    # Verificar se tem jobs com script
                    for val in obj.values():
                        if isinstance(val, dict) and "script" in val:
                            return "gitlab-ci"

                # CircleCI (tem ambos version e jobs)
                if "version" in obj and "jobs" in obj:
                    return "circleci"

                # Kubernetes
                if "kind" in obj or "apiVersion" in obj:
                    return "kubernetes"

                # Docker Compose (tem services, mas NÃO tem jobs juntos com version)
                if "services" in obj:
                    return "docker-compose"

                # Recursão para valores aninhados
                for val in obj.values():
                    result = check_recursive(val)
                    if result:
                        return result

            elif isinstance(obj, list):
                for item in obj:
                    result = check_recursive(item)
                    if result:
                        return result

            return None

        return check_recursive(doc)

    def _detect_ci_platform_regex(self, code: str) -> Optional[str]:
        """Detecta plataforma CI usando regex."""
        if re.search(r"^\s*(name|on|runs-on)\s*:", code, re.MULTILINE):
            return "github-actions"
        if re.search(r"^\s*(stages|image)\s*:", code, re.MULTILINE):
            return "gitlab-ci"
        if re.search(r"kind:\s*(Deployment|Service|Pod)", code):
            return "kubernetes"
        if re.search(r"^\s*services\s*:", code, re.MULTILINE):
            return "docker-compose"
        return None

    def _detect_secrets(self, code: str) -> tuple[bool, List[str]]:
        """Detecta possíveis segredos no código."""
        secret_keys = []

        # Padrão mais simples: apenas verificar nomes de chaves suspeitas
        # seguidas por algum valor (não vazio, não null)
        suspicious_keys = [
            "password",
            "passwd",
            "pwd",
            "api_key",
            "apikey",
            "api-key",
            "secret",
            "secret_key",
            "private_key",
            "access_token",
            "auth_token",
            "token",
            "credential",
            "credentials",
            "jwt",
            "bearer",
            "authorization",
        ]

        for key in suspicious_keys:
            # Procurar chave seguida por dois pontos e valor
            # Suporta: key: value, key: "value", key: 'value', key: | multiline
            pattern = r'(?:^|\n)\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?:"[^"]*"|\'[^\']*\'|[^\s\n#]+|\|\s*\n(?:\s+[^\n]*\n)+)'
            for match in re.finditer(pattern, code, re.MULTILINE):
                key_name = match.group(1).lower()
                if key in key_name and key_name not in secret_keys:
                    secret_keys.append(match.group(1))

        has_secrets = len(secret_keys) > 0
        return has_secrets, secret_keys

    def _has_base64(self, code: str) -> bool:
        """Detecta valores codificados em base64."""
        # Padrão para detectar valores que parecem base64 em YAML
        # Deve ter:
        # - Mínimo de 20 caracteres (base64 real tem mais)
        # - Apenas caracteres base64 válidos: A-Za-z0-9+/=
        # - Padding opcional = ou == no final
        # - Não deve ser uma palavra normal (apenas letras)

        # Padrão que captura valores após dois pontos
        # Suporta: key: value, key: "value", key: 'value', key: | multiline
        pattern = r':\s*(?:"|\')?([A-Za-z0-9+/={20,}]+)(?:"|\')?(?:\s|#|$|,|\])'

        for match in re.finditer(pattern, code):
            value = match.group(1)

            # Limpar valor de possíveis caracteres de fim
            value = value.rstrip(")").rstrip(",").rstrip("]").rstrip("}").rstrip("=")

            # Pular se muito curto
            if len(value) < 20:
                continue

            # Se é apenas letras (maiúsculas ou minúsculas), pode ser texto normal
            # Mas se for muito longo e parecer aleatório, pode ser base64
            if re.match(r"^[a-zA-Z]+$", value):
                # Texto muito longo com apenas letras é suspeito
                # Verificar se parece codificado (mistura upper/lower sem espaços)
                if len(value) > 40:
                    has_upper = any(c.isupper() for c in value)
                    has_lower = any(c.islower() for c in value)
                    # Base64 geralmente tem mistura de upper e lower
                    if has_upper and has_lower:
                        return True
                continue

            # Verificar se tem apenas caracteres base64 válidos
            if not re.match(r"^[A-Za-z0-9+/=]+$", value):
                continue

            # Verificar padding - base64 tem 0, 1 ou 2 = no final
            padding_count = value.count("=")
            if padding_count > 2:
                continue

            # Se tem + ou / ou mistura de upper/lower/digits, provavelmente é base64
            has_special = any(c in "/+" for c in value)
            has_upper = any(c.isupper() for c in value)
            has_lower = any(c.islower() for c in value)
            has_digit = any(c.isdigit() for c in value)

            # Base64 tipicamente tem mistura de caracteres
            score = sum([has_upper, has_lower, has_digit, has_special])
            if score >= 2:
                return True

        return False

    def has_errors(self, filename: str) -> bool:
        """Verifica se arquivo tem erros de parsing."""
        return filename in self._parse_errors

    def get_stats(self) -> Dict[str, int]:
        """Retorna estatísticas do parser."""
        return {
            "parsed_files": len(self._parsed_cache),
            "files_with_errors": len(self._parse_errors),
        }
