"""Parser para coleções Postman (JSON)."""

import json
from typing import Any

from structlog import get_logger

logger = get_logger(__name__)


class PostmanParser:
    """Parser para extrair APIs de coleções Postman em formato JSON."""

    def __init__(self) -> None:
        """Inicializa o parser Postman."""

    async def extract_apis(self, file_content: bytes) -> list[dict[str, Any]]:
        """
        Extrai endpoints de API de coleção Postman.

        Args:
            file_content: Conteúdo binário do arquivo JSON da coleção.

        Returns:
            Lista de dicionários com informações das APIs:
            - name: Nome do request/endpoint
            - method: Método HTTP (GET, POST, etc.)
            - url: URL do endpoint
            - headers: Headers configurados
            - body: Body da request (se houver)
            - auth: Configuração de autenticação (se houver)
            - folder: Nome da pasta (se aninhado)
            Retorna lista vazia em caso de erro.
        """
        if not self._validate_json_bytes(file_content):
            logger.warning("postman_invalid_bytes", size=len(file_content))
            return []

        try:
            data = json.loads(file_content.decode("utf-8"))
            apis = []

            # Processa coleção Postman (formato v2.1)
            if "info" in data and data["info"].get("schema", "").startswith(
                "https://schema.getpostman.com/json/collection/v2.1"
            ):
                apis = self._extract_apis_v21(data)
            # Formato v2
            elif "item" in data:
                apis = self._extract_apis_v2(data)
            else:
                logger.warning("postman_unknown_format")
                return []

            logger.info(
                "postman_apis_extracted",
                api_count=len(apis),
                format=data.get("info", {}).get("schema", "unknown"),
            )

            return apis

        except json.JSONDecodeError as e:
            logger.error("postman_json_decode_failed", error=str(e))
            return []
        except Exception as e:
            logger.error("postman_extraction_failed", error=str(e))
            return []

    async def extract_metadata(self, file_content: bytes) -> dict[str, Any]:
        """
        Extrai metadados da coleção Postman.

        Args:
            file_content: Conteúdo binário do arquivo JSON.

        Returns:
            Dicionário com metadados: name, description, api_count, etc.
        """
        if not self._validate_json_bytes(file_content):
            return {}

        metadata: dict[str, Any] = {}

        try:
            data = json.loads(file_content.decode("utf-8"))

            # Informações da coleção
            if "info" in data:
                info = data["info"]
                if "name" in info:
                    metadata["name"] = info["name"]
                if "description" in info:
                    desc = info["description"]
                    if isinstance(desc, dict):
                        metadata["description"] = desc.get("content", str(desc))
                    else:
                        metadata["description"] = str(desc)
                if "schema" in info:
                    metadata["schema"] = info["schema"]
                if "version" in info:
                    metadata["version"] = info["version"]

            # Contar APIs
            apis = await self.extract_apis(file_content)
            metadata["api_count"] = len(apis)

            # Contar pastas
            metadata["folder_count"] = self._count_folders(data)

            logger.info("postman_metadata_extracted", api_count=metadata.get("api_count"))

        except Exception as e:
            logger.error("postman_metadata_extraction_failed", error=str(e))
            return {}

        return metadata

    def validate(self, file_content: bytes) -> bool:
        """
        Valida se o conteúdo é uma coleção Postman válida.

        Args:
            file_content: Conteúdo binário do arquivo.

        Returns:
            True se for um JSON válido com estrutura Postman, False caso contrário.
        """
        if not self._validate_json_bytes(file_content):
            return False

        try:
            data = json.loads(file_content.decode("utf-8"))

            # Verifica se tem estrutura de coleção Postman
            if "info" in data:
                schema = data["info"].get("schema", "")
                return "postman.com" in schema or "getpostman.com" in schema

            # Formato mais simples - apenas tem "item"
            return "item" in data

        except Exception:
            return False

    def _validate_json_bytes(self, file_content: bytes) -> bool:
        """
        Valida bytes como JSON.

        Args:
            file_content: Conteúdo binário a validar.

        Returns:
            True se parecer JSON válido.
        """
        if not file_content or len(file_content) < 2:
            return False

        stripped = file_content.strip()
        return stripped[0] == ord("{") or stripped[0] == ord("[")

    def _extract_apis_v21(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Extrai APIs de coleção Postman v2.1.

        Args:
            data: Dados da coleção parseados.

        Returns:
            Lista de APIs extraídas.
        """
        apis: list[dict[str, Any]] = []

        def process_item(item: Any, folder: str | None = None) -> None:
            """Processa um item recursivamente."""
            if isinstance(item, dict):
                # Item é um request
                if "request" in item:
                    api_info = self._parse_request(item["request"], folder)
                    if api_info:
                        if "name" in item:
                            api_info["name"] = item["name"]
                        apis.append(api_info)

                # Item é uma pasta (contém outros itens)
                elif "item" in item:
                    folder_name = item.get("name", folder)
                    for sub_item in item["item"]:
                        process_item(sub_item, folder_name)

            # Lista de itens
            elif isinstance(item, list):
                for sub_item in item:
                    process_item(sub_item, folder)

        # Processa itens raiz
        process_item(data.get("item", []))

        return apis

    def _extract_apis_v2(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Extrai APIs de coleção Postman v2 (legado).

        Args:
            data: Dados da coleção parseados.

        Returns:
            Lista de APIs extraídas.
        """
        # V2 é similar a v2.1, usa o mesmo parser
        return self._extract_apis_v21(data)

    def _parse_request(self, request: dict[str, Any], folder: str | None) -> dict[str, Any] | None:
        """
        Faz parsing de um request Postman.

        Args:
            request: Objeto request do Postman.
            folder: Nome da pasta (se aninhado).

        Returns:
            Dicionário com informações da API ou None.
        """
        if not isinstance(request, dict):
            return None

        api_info: dict[str, Any] = {}

        # Método HTTP
        if "method" in request:
            api_info["method"] = request["method"]
        else:
            api_info["method"] = "GET"  # Default

        # URL - pode ser string ou objeto
        if "url" in request:
            url = request["url"]
            if isinstance(url, str):
                api_info["url"] = url
            elif isinstance(url, dict):
                # URL pode ser um objeto com "raw" ou "path"
                api_info["url"] = url.get("raw", "")
                if "protocol" in url:
                    protocol = url["protocol"]
                    host = url.get("host", [])
                    path = url.get("path", [])
                    if host and path:
                        api_info["url"] = f"{protocol}://{'.'.join(host)}/{'/'.join(path)}"

        # Headers
        if "header" in request:
            headers = {}
            for h in request["header"]:
                if isinstance(h, dict) and "key" in h and "value" in h:
                    headers[h["key"]] = h["value"]
            api_info["headers"] = headers

        # Body
        if "body" in request:
            body = request["body"]
            if isinstance(body, dict):
                if "mode" in body:
                    api_info["body_mode"] = body["mode"]
                    if body["mode"] == "raw" and "raw" in body:
                        api_info["body"] = body["raw"]
                    elif body["mode"] == "urlencoded" and "urlencoded" in body:
                        api_info["body"] = [{p["key"]: p["value"]} for p in body["urlencoded"]]
                    elif body["mode"] == "formdata" and "formdata" in body:
                        api_info["body"] = [{p["key"]: p["value"]} for p in body["formdata"]]

        # Auth
        if "auth" in request:
            auth = request["auth"]
            if isinstance(auth, dict) and "type" in auth:
                api_info["auth_type"] = auth["type"]

        # Folder
        if folder:
            api_info["folder"] = folder

        return api_info if "url" in api_info else None

    def _count_folders(self, data: dict[str, Any]) -> int:
        """
        Conta pastas na coleção.

        Args:
            data: Dados da coleção parseados.

        Returns:
            Número de pastas.
        """
        count = 0

        def count_in_items(items: Any) -> None:
            nonlocal count
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        # Item com sub-itens é uma pasta
                        if "item" in item:
                            count += 1
                            count_in_items(item["item"])

        count_in_items(data.get("item", []))
        return count
