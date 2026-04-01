"""
JSON Parser - Análise de arquivos JSON.

Suporta package.json, tsconfig.json, configs genéricas.
"""
import json
import re
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()


class JSONParser:
    """Parser para arquivos JSON."""

    # Padrões para detecção de segredos
    SECRET_KEY_PATTERNS = [
        r"password",
        r"api_key",
        r"apikey",
        r"secret",
        r"token",
        r"private_key",
        r"access_token",
        r"auth_token",
        r"jwt",
        r"credential",
    ]

    # Padrões para valores de segredo
    SECRET_VALUE_PATTERNS = [
        r"sk_live_[a-zA-Z0-9]+",  # Stripe
        r"sk_test_[a-zA-Z0-9]+",  # Stripe test
        r"ghp_[a-zA-Z0-9]{36}",  # GitHub PAT
        r"gho_[a-zA-Z0-9]{36}",  # GitHub OAuth
        r"ghu_[a-zA-Z0-9]{36}",  # GitHub user
        r"ghs_[a-zA-Z0-9]{36}",  # GitHub server
        r"ghr_[a-zA-Z0-9]{36}",  # GitHub refresh
        r"eyJ[a-zA-Z0-9+/=]+\.",  # JWT start
        r"AIza[a-zA-Z0-9\-_]{35}",  # Google API key
        r"AKIA[0-9A-Z]{16}",  # AWS Access Key
        r"[a-zA-Z0-9+/]{32,}={0,2}",  # Possible base64
    ]

    def __init__(self):
        """Inicializa o JSONParser."""
        self._parsed_cache: Dict[str, Dict] = {}
        self._parse_errors: set = set()

    def parse(self, code: str, filename: str) -> Optional[Dict[str, Any]]:
        """
        Faz parsing de arquivo JSON.

        Args:
            code: Conteúdo JSON
            filename: Nome do arquivo

        Returns:
            Dict com chaves, estrutura, metadados
        """
        if not code or not code.strip():
            return {
                "keys": [],
                "has_secrets": False,
                "secret_keys": [],
                "has_empty_containers": False,
                "empty_count": 0,
                "max_depth": 0,
                "type": self._detect_file_type(filename),
                "has_errors": False,
            }

        try:
            data = json.loads(code)

            result = {
                "keys": [],
                "has_secrets": False,
                "secret_keys": [],
                "has_empty_containers": False,
                "empty_count": 0,
                "max_depth": 0,
                "type": self._detect_file_type(filename),
                "has_errors": False,
            }

            # Analisar estrutura
            all_keys = set()
            max_depth = [0]
            empty_count = [0]

            self._analyze_structure(data, all_keys, 0, max_depth, empty_count)

            result["keys"] = list(all_keys)
            result["max_depth"] = max_depth[0]
            result["has_empty_containers"] = empty_count[0] > 0
            result["empty_count"] = empty_count[0]

            # Detectar tipo específico de arquivo
            if isinstance(data, dict):
                result.update(self._extract_file_specific_info(data, filename))

            # Detectar segredos no código original
            result["has_secrets"], result["secret_keys"] = self._detect_secrets(code)

            return result

        except json.JSONDecodeError as e:
            logger.error(
                "json_parse_error", filename=filename, error=str(e), line=e.lineno, column=e.colno
            )
            self._parse_errors.add(filename)
            return None
        except Exception as e:
            logger.error("json_parse_error", filename=filename, error=str(e))
            self._parse_errors.add(filename)
            return None

    def _analyze_structure(
        self, obj: Any, keys: set, depth: int, max_depth: list, empty_count: list
    ):
        """Analisa estrutura recursivamente."""
        max_depth[0] = max(max_depth[0], depth)

        if isinstance(obj, dict):
            if not obj:
                empty_count[0] += 1
            for key, value in obj.items():
                keys.add(key)
                self._analyze_structure(value, keys, depth + 1, max_depth, empty_count)

        elif isinstance(obj, list):
            if not obj:
                empty_count[0] += 1
            for i, item in enumerate(obj):
                self._analyze_structure(item, keys, depth + 1, max_depth, empty_count)

    def _detect_file_type(self, filename: str) -> Optional[str]:
        """Detecta tipo de arquivo baseado no nome."""
        filename_lower = filename.lower()

        if filename_lower.endswith("package.json"):
            return "package.json"
        if filename_lower.endswith("tsconfig.json"):
            return "tsconfig.json"
        if filename_lower.endswith(".eslintrc.json") or filename_lower == ".eslintrc":
            return ".eslintrc.json"
        if filename_lower.endswith("babelrc.json") or filename_lower == ".babelrc":
            return "babelrc.json"
        if "prettierrc" in filename_lower:
            return "prettierrc.json"
        if filename_lower.endswith("config.json"):
            return "config.json"

        return None

    def _extract_file_specific_info(self, data: Dict, filename: str) -> Dict[str, Any]:
        """Extrai informações específicas do tipo de arquivo."""
        info = {}
        file_type = self._detect_file_type(filename)

        if file_type == "package.json":
            # Extrair scripts
            scripts = data.get("scripts", {})
            if scripts:
                info["scripts"] = scripts

            # Extrair dependências
            for dep_type in [
                "dependencies",
                "devDependencies",
                "peerDependencies",
                "optionalDependencies",
            ]:
                if dep_type in data:
                    info[dep_type] = list(data[dep_type].keys())

        elif file_type == "tsconfig.json":
            # Extrai compiler options
            if "compilerOptions" in data:
                info["compiler_options"] = data["compilerOptions"]

        elif file_type == ".eslintrc.json":
            # Extrai regras
            if "rules" in data:
                info["rules"] = data["rules"]

        return info

    def _detect_secrets(self, code: str) -> tuple[bool, List[str]]:
        """Detecta possíveis segredos no código JSON."""
        secret_keys = []

        # Encontrar todas as chaves
        for match in re.finditer(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:', code):
            key = match.group(1).lower()

            # Verificar se a chave sugere um segredo
            for pattern in self.SECRET_KEY_PATTERNS:
                if pattern in key:
                    secret_keys.append(match.group(1))
                    break

        # Verificar valores suspeitos
        for pattern in self.SECRET_VALUE_PATTERNS:
            if re.search(pattern, code):
                # Encontrar chave associada
                context_match = re.search(
                    rf'"([A-Za-z_][A-Za-z0-9_]*)"\s*:\s*"[^"]*{re.escape(pattern)}', code
                )
                if context_match:
                    key = context_match.group(1)
                    if key not in secret_keys:
                        secret_keys.append(key)

        has_secrets = len(secret_keys) > 0
        return has_secrets, secret_keys

    def has_errors(self, filename: str) -> bool:
        """Verifica se arquivo tem erros de parsing."""
        return filename in self._parse_errors

    def get_stats(self) -> Dict[str, int]:
        """Retorna estatísticas do parser."""
        return {
            "parsed_files": len(self._parsed_cache),
            "files_with_errors": len(self._parse_errors),
        }
