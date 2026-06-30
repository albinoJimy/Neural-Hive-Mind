"""Cliente HTTP para integração com Gateway Intenções."""

import uuid
from typing import Any

import structlog
from httpx import AsyncClient, ConnectError, HTTPStatusError, TimeoutException

from src.models.entities import EntitySet, EntityType

logger = structlog.get_logger(__name__)


class GatewayClientError(Exception):
    """Erro na comunicação com Gateway Intenções."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class GatewayClient:
    """Cliente para integração com Gateway Intenções.

    Responsável por:
    - Converter EntitySet para CognitivePlan (texto em linguagem natural)
    - Enviar intenções para o Gateway
    - Verificar status de intenções
    """

    def __init__(
        self,
        gateway_url: str,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """Inicializa cliente do Gateway.

        Args:
            gateway_url: URL base do Gateway Intenções (ex: http://gateway-intencoes:8000)
            timeout: Timeout em segundos para requisições HTTP
            max_retries: Número máximo de retries em caso de falha
        """
        self._gateway_url = gateway_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._logger = logger

    async def generate_cognitive_plan(self, entity_set: EntitySet) -> dict[str, Any]:
        """Gera CognitivePlan a partir de EntitySet.

        Converte entidades extraídas em texto de intenção em linguagem natural
        que pode ser processado pelo Gateway Intenções.

        Args:
            entity_set: Conjunto de entidades extraídas do documento.

        Returns:
            Dicionário com CognitivePlan contendo 'text' e 'document_id'.
        """
        if not entity_set.entities:
            return {
                "text": "No entities were extracted from the document. Please review the document content.",
                "document_id": entity_set.document_id,
                "entity_count": 0,
            }

        # Agrupar entidades por tipo
        by_type: dict[EntityType, list] = {et: [] for et in EntityType}
        for entity in entity_set.entities:
            by_type[entity.type].append(entity)

        # Construir narrativa em linguagem natural
        sections = []

        # Funcionalidades
        if by_type[EntityType.FUNCTIONALITY]:
            sections.append(
                f"The document describes {len(by_type[EntityType.FUNCTIONALITY])} main functionalities: "
                + "; ".join([f.name for f in by_type[EntityType.FUNCTIONALITY][:5]])
            )

        # Requisitos
        if by_type[EntityType.REQUIREMENT]:
            sections.append(
                f"It specifies {len(by_type[EntityType.REQUIREMENT])} requirements, "
                f"including: {', '.join([r.name for r in by_type[EntityType.REQUIREMENT][:3]])}"
            )

        # APIs
        if by_type[EntityType.API]:
            api_names = [api.name for api in by_type[EntityType.API][:5]]
            sections.append(
                f"The system exposes {len(api_names)} API endpoints: {', '.join(api_names)}"
            )

        # Modelos de dados
        if by_type[EntityType.DATA_MODEL]:
            sections.append(
                f"It defines {len(by_type[EntityType.DATA_MODEL])} data models "
                f"such as: {', '.join([dm.name for dm in by_type[EntityType.DATA_MODEL][:3]])}"
            )

        # Tech stack
        if by_type[EntityType.TECH_STACK]:
            tech_items = [ts.name for ts in by_type[EntityType.TECH_STACK][:5]]
            sections.append(f"Tech stack includes: {', '.join(tech_items)}")

        # Dependências
        if by_type[EntityType.DEPENDENCY]:
            deps = [d.name for d in by_type[EntityType.DEPENDENCY][:5]]
            sections.append(f"External dependencies: {', '.join(deps)}")

        # Combinar seções em texto coeso
        if sections:
            text = " ".join(sections)
            # Adicionar introdução
            text = (
                f"Based on legacy documentation, I want to migrate/implement a system "
                f"with the following characteristics: {text}"
            )
        else:
            text = "The document contains entities that need to be analyzed for migration."

        return {
            "text": text,
            "document_id": entity_set.document_id,
            "entity_count": entity_set.total_count,
        }

    def _build_intent_request(
        self,
        document_id: str,
        plan: dict[str, Any],
        ingestion_id: str | None = None,
    ) -> dict[str, Any]:
        """Constrói request para o Gateway.

        Args:
            document_id: ID do documento de origem.
            plan: CognitivePlan com texto da intenção.
            ingestion_id: ID opcional do processo de ingestão.

        Returns:
            Dicionário com request formatado para o Gateway.
        """
        request = {
            "text": plan["text"],
            "language": "pt-BR",
            "source": "legacy_document",
            "metadata": {
                "document_id": document_id,
                "ingestion_id": ingestion_id or str(uuid.uuid4()),
                "entity_count": plan.get("entity_count", 0),
            },
            # Marcador de ingestão (J4) — sinal estruturado para o Tier 1 do
            # JourneyClassifier (STE): context.source == "doc-ingestion" -> J4_MIGRATE.
            # Sinais, não keywords: a jornada é decidida por este marcador fiável,
            # não por palavras como "migração" no texto. O journey_hint é um
            # reforço opcional para explicabilidade/observabilidade.
            "context": {
                "source": "doc-ingestion",
                "metadata": {"journey_hint": "MIGRATE"},
            },
        }
        return request

    async def send_to_gateway(
        self,
        document_id: str,
        entity_set: EntitySet,
        ingestion_id: str | None = None,
    ) -> dict[str, Any]:
        """Envia entidades extraídas para o Gateway Intenções.

        Converte EntitySet em CognitivePlan e envia como intenção para processamento.

        Args:
            document_id: ID do documento.
            entity_set: Conjunto de entidades extraídas.
            ingestion_id: ID opcional do processo de ingestão.

        Returns:
            Dicionário com resposta do Gateway contendo intent_id e status.

        Raises:
            GatewayClientError: Se a comunicação falhar após retries.
        """
        self._logger.info(
            "sending_to_gateway",
            document_id=document_id,
            entity_count=entity_set.total_count,
        )

        # Gerar CognitivePlan
        plan = await self.generate_cognitive_plan(entity_set)

        # Construir request
        request = self._build_intent_request(
            document_id=document_id,
            plan=plan,
            ingestion_id=ingestion_id,
        )

        # Tentar enviar com retries
        last_error = None
        for attempt in range(self._max_retries):
            try:
                async with AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        f"{self._gateway_url}/intentions",
                        json=request,
                        headers={"Content-Type": "application/json"},
                    )

                    response.raise_for_status()
                    result = response.json()

                    self._logger.info(
                        "gateway_send_success",
                        document_id=document_id,
                        intent_id=result.get("intent_id"),
                        status=result.get("status"),
                        attempt=attempt + 1,
                    )

                    return result

            except TimeoutException as e:
                last_error = e
                self._logger.warning(
                    "gateway_send_timeout",
                    document_id=document_id,
                    attempt=attempt + 1,
                    error=str(e),
                )
                # Não retry em timeout (pode ser overload)
                if attempt == self._max_retries - 1:
                    break

            except ConnectError as e:
                last_error = e
                self._logger.warning(
                    "gateway_send_connection_error",
                    document_id=document_id,
                    attempt=attempt + 1,
                    error=str(e),
                )
                # Retry em erro de conexão

            except HTTPStatusError as e:
                # Não retry em erros 4xx (client errors)
                if 400 <= e.response.status_code < 500:
                    error_msg = (
                        f"Gateway rejected request: {e.response.status_code} - {e.response.text}"
                    )
                    self._logger.error("gateway_send_client_error", error=error_msg)
                    raise GatewayClientError(error_msg, status_code=e.response.status_code) from e

                last_error = e
                self._logger.warning(
                    "gateway_send_server_error",
                    document_id=document_id,
                    status_code=e.response.status_code,
                    attempt=attempt + 1,
                )
                # Retry em erros 5xx

        # Todos os retries falharam
        error_msg = f"Failed to send to Gateway after {self._max_retries} attempts: {last_error}"
        self._logger.error("gateway_send_failed", error=error_msg)
        raise GatewayClientError(error_msg)

    async def check_intent_status(self, intent_id: str) -> dict[str, Any] | None:
        """Verifica status de intenção no Gateway.

        Args:
            intent_id: ID da intenção a consultar.

        Returns:
            Dicionário com status e dados da intenção, ou None se não encontrado.
        """
        self._logger.debug("checking_intent_status", intent_id=intent_id)

        try:
            async with AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    f"{self._gateway_url}/intentions/{intent_id}",
                )

                if response.status_code == 404:
                    self._logger.info("intent_not_found", intent_id=intent_id)
                    return None

                response.raise_for_status()
                result = response.json()

                self._logger.debug(
                    "intent_status_retrieved",
                    intent_id=intent_id,
                    status=result.get("status"),
                )

                return result

        except HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            self._logger.error("intent_status_error", intent_id=intent_id, error=str(e))
            raise GatewayClientError(
                f"Failed to check intent status: {e}", status_code=e.response.status_code
            ) from e
        except Exception as e:
            self._logger.error("intent_status_error", intent_id=intent_id, error=str(e))
            raise GatewayClientError(f"Failed to check intent status: {e}") from None
