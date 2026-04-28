"""
Servico de Processamento de Solicitacoes de Exclusao GDPR
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import structlog
from pymongo import UpdateOne
from pymongo.errors import PyMongoError

from src.config.settings import Settings, get_settings
from src.models.erasure import (
    DataType,
    ErasureCommand,
    ErasureRequest,
    ErasureScope,
    ErasureStatus,
    ServiceErasureResult,
)

logger = structlog.get_logger()


class ErasureService:
    """Servico de gerenciamento de solicitacoes de exclusao"""

    def __init__(self, settings: Settings, mongodb_client, redis_client, kafka_producer):
        """
        Inicializa o servico de exclusao.

        Args:
            settings: Configuracoes
            mongodb_client: Cliente MongoDB
            redis_client: Cliente Redis
            kafka_producer: Producer Kafka
        """
        self.settings = settings
        self.db = mongodb_client.client[self.settings.mongodb_database]
        self.redis = redis_client.client
        self.producer = kafka_producer

        # Colecoes
        self.collection = self.db.erasure_requests
        self.tokens_collection = self.db.verification_tokens

        # Mapeamento de data types para services
        self._data_type_service_map = {
            DataType.APPROVALS: "approval-service",
            DataType.SPECIALIST_FEEDBACK: "approval-service",
            DataType.CONTINUOUS_FEEDBACK: "approval-service",
            DataType.CONSENSUS_HISTORY: "consensus-engine",
            DataType.EXECUTION_TICKETS: "execution-ticket-service",
            DataType.MEMORY_ENTRIES: "memory-layer-api",
            DataType.INTENT_HISTORY: "gateway-intencoes",
            DataType.METRICS_LOGS: "observability",
        }

    def _generate_verification_token(self, user_id: str, email: str) -> str:
        """
        Gera token de verificacao seguro.

        Args:
            user_id: ID do usuario
            email: Email do usuario

        Returns:
            Token hexadecimal de 32 bytes
        """
        raw = f"{user_id}:{email}:{secrets.token_hex(16)}:{datetime.now(timezone.utc).isoformat()}"
        salted = f"{raw}:{self.settings.verification_token_salt}"
        return hashlib.sha256(salted.encode()).hexdigest()

    async def create_erasure_request(
        self, user_id: str, input_data: dict
    ) -> ErasureRequest:
        """
        Cria uma nova solicitacao de exclusao.

        Args:
            user_id: ID do usuario solicitante
            input_data: Dados da solicitacao

        Returns:
            ErasureRequest criada

        Raises:
            ValueError: Se ja existir solicitacao em andamento
        """
        logger.info(
            "Criando solicitacao de exclusao",
            user_id_hash=hashlib.sha256(user_id.encode()).hexdigest()[:16],
        )

        # Verificar se ja existe solicitacao em andamento
        existing = await self.collection.find_one(
            {
                "user_id": user_id,
                "status": {
                    "$in": [
                        ErasureStatus.PENDING_VERIFICATION,
                        ErasureStatus.VERIFIED,
                        ErasureStatus.PROCESSING,
                    ]
                },
            }
        )

        if existing:
            logger.warning(
                "Solicitacao de exclusao ja existe",
                request_id=existing.get("request_id"),
                status=existing.get("status"),
            )
            raise ValueError(
                f"Ja existe uma solicitacao em andamento: {existing.get('request_id')}"
            )

        # Determinar data types se nao especificados
        data_types = input_data.get("data_types", [])
        if not data_types:
            data_types = list(DataType)

        # Criar token de verificacao
        token = self._generate_verification_token(user_id, input_data.get("email"))
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=self.settings.redis_token_ttl
        )

        # Criar solicitacao
        request = ErasureRequest(
            user_id=user_id,
            email=input_data.get("email"),
            scope=ErasureScope(input_data.get("scope", ErasureScope.STANDARD)),
            data_types=[DataType(dt) for dt in data_types],
            reason=input_data.get("reason"),
            verification_token=token,
            status=ErasureStatus.PENDING_VERIFICATION,
            expires_at=expires_at,
        )

        # Persistir no MongoDB
        await self.collection.insert_one(request.model_dump())

        # Armazenar token no Redis para validacao rapida
        token_key = f"erasure:token:{token}"
        await self.redis.setex(
            token_key,
            self.settings.redis_token_ttl,
            f"{request.request_id}:{user_id}",
        )

        logger.info(
            "Solicitacao de exclusao criada",
            request_id=request.request_id,
            status=request.status,
        )

        return request

    async def verify_erasure_request(
        self, request_id: str, token: str
    ) -> ErasureRequest:
        """
        Verifica uma solicitacao usando o token enviado por email.

        Args:
            request_id: ID da solicitacao
            token: Token de verificacao

        Returns:
            ErasureRequest verificada

        Raises:
            ValueError: Se token invalido ou expirado
        """
        logger.info("Verificando solicitacao de exclusao", request_id=request_id)

        # Validar token no Redis primeiro (mais rapido)
        token_key = f"erasure:token:{token}"
        token_value = await self.redis.get(token_key)

        if not token_value:
            raise ValueError("Token invalido ou expirado")

        stored_request_id, stored_user_id = token_value.decode().split(":")

        if stored_request_id != request_id:
            raise ValueError("Token nao corresponde a solicitacao")

        # Atualizar status para VERIFIED
        now = datetime.now(timezone.utc)
        await self.collection.update_one(
            {"request_id": request_id, "status": ErasureStatus.PENDING_VERIFICATION},
            {
                "$set": {
                    "status": ErasureStatus.VERIFIED,
                    "verified_at": now,
                }
            },
        )

        # Remover token do Redis ja usado
        await self.redis.delete(token_key)

        # Buscar solicitacao atualizada
        request_doc = await self.collection.find_one({"request_id": request_id})
        request = ErasureRequest(**request_doc)

        logger.info("Solicitacao verificada com sucesso", request_id=request_id)

        return request

    async def process_erasure_request(self, request_id: str) -> ErasureRequest:
        """
        Inicia o processamento de uma solicitacao verificada.

        Args:
            request_id: ID da solicitacao

        Returns:
            ErasureRequest atualizada

        Raises:
            ValueError: Se solicitacao nao verificada
        """
        logger.info("Iniciando processamento de exclusao", request_id=request_id)

        # Buscar solicitacao
        request_doc = await self.collection.find_one({"request_id": request_id})
        if not request_doc:
            raise ValueError(f"Solicitacao nao encontrada: {request_id}")

        request = ErasureRequest(**request_doc)

        if request.status != ErasureStatus.VERIFIED:
            raise ValueError(
                f"Solicitacao deve estar verificada, status atual: {request.status}"
            )

        # Atualizar status para PROCESSING
        await self.collection.update_one(
            {"request_id": request_id},
            {
                "$set": {
                    "status": ErasureStatus.PROCESSING,
                    "processing_started_at": datetime.now(timezone.utc),
                }
            },
        )

        # Enviar comandos para cada servico
        services_to_notify = self._get_target_services(request.data_types)

        for service in set(services_to_notify):  # deduplicar
            await self._send_erasure_command(request, service)

        logger.info(
            "Comandos de exclusao enviados",
            request_id=request_id,
            services_count=len(services_to_notify),
        )

        # Buscar solicitacao atualizada
        request_doc = await self.collection.find_one({"request_id": request_id})
        return ErasureRequest(**request_doc)

    def _get_target_services(self, data_types: list[DataType]) -> list[str]:
        """
        Mapeia data types para services alvo.

        Args:
            data_types: Lista de tipos de dados

        Returns:
            Lista de nomes de servicos
        """
        services = []
        for dt in data_types:
            service = self._data_type_service_map.get(dt)
            if service:
                services.append(service)
        return services

    async def _send_erasure_command(self, request: ErasureRequest, service: str):
        """
        Envia comando de exclusao para um servico.

        Args:
            request: Solicitacao de exclusao
            service: Nome do servico alvo
        """
        command = ErasureCommand(
            request_id=request.request_id,
            user_id=request.user_id,
            data_types=request.data_types,
            scope=request.scope,
            target_service=service,
        )

        await self.producer.produce(
            topic=self.settings.kafka_erasure_commands_topic,
            key=service,
            value=command.to_kafka_dict(),
        )

        logger.debug(
            "Comando de exclusao enviado",
            command_id=command.command_id,
            service=service,
        )

    async def handle_erasure_report(self, report_data: dict) -> None:
        """
        Processa relatorio de conclusao de um servico.

        Args:
            report_data: Dados do relatorio
        """
        request_id = report_data.get("request_id")
        service = report_data.get("service")
        status = report_data.get("status")
        records_affected = report_data.get("records_affected", 0)
        error_message = report_data.get("error_message")

        logger.info(
            "Recebendo relatorio de exclusao",
            request_id=request_id,
            service=service,
            status=status,
        )

        # Criar resultado
        result = ServiceErasureResult(
            service=service,
            data_type=DataType.APPROVALS,  # Generico, pode ser refinado
            status=status,
            records_affected=records_affected,
            error_message=error_message,
            completed_at=datetime.now(timezone.utc),
        )

        # Adicionar a solicitacao
        await self.collection.update_one(
            {"request_id": request_id},
            {"$push": {"results": result.model_dump()}},
        )

        # Verificar se todos os services responderam
        await self._check_completion(request_id)

    async def _check_completion(self, request_id: str) -> None:
        """
        Verifica se a solicitacao esta completa.

        Args:
            request_id: ID da solicitacao
        """
        request_doc = await self.collection.find_one({"request_id": request_id})
        if not request_doc:
            return

        # Contar services esperados
        data_types = [DataType(dt) for dt in request_doc.get("data_types", [])]
        expected_services = set(self._get_target_services(data_types))

        # Services que ja responderam
        completed_services = {
            r["service"] for r in request_doc.get("results", [])
        }

        if completed_services == expected_services:
            # Todos responderam
            final_status = ErasureStatus.COMPLETED

            # Verificar se houve falhas
            has_failures = any(
                r.get("status") == "failed" for r in request_doc.get("results", [])
            )
            if has_failures:
                final_status = ErasureStatus.PARTIALLY_COMPLETED

            await self.collection.update_one(
                {"request_id": request_id},
                {
                    "$set": {
                        "status": final_status,
                        "completed_at": datetime.now(timezone.utc),
                    }
                },
            )

            logger.info(
                "Solicitacao de exclusao completada",
                request_id=request_id,
                final_status=final_status,
            )

    async def get_erasure_status(self, request_id: str) -> dict:
        """
        Retorna o status de uma solicitacao.

        Args:
            request_id: ID da solicitacao

        Returns:
            Dict com status da solicitacao

        Raises:
            ValueError: Se solicitacao nao encontrada
        """
        request_doc = await self.collection.find_one({"request_id": request_id})
        if not request_doc:
            raise ValueError(f"Solicitacao nao encontrada: {request_id}")

        request = ErasureRequest(**request_doc)

        # Calcular resumo dos resultados
        results_summary = {}
        for result in request.results:
            results_summary[result.service] = result.records_affected

        return {
            "request_id": request.request_id,
            "status": request.status,
            "scope": request.scope,
            # use_enum_values=True means data_types are already strings
            "data_types": request.data_types,
            "created_at": request.created_at,
            "verified_at": request.verified_at,
            "completed_at": request.completed_at,
            "results_summary": results_summary,
        }

    async def cleanup_expired_requests(self) -> int:
        """
        Limpa solicitacoes expiradas (background job).

        Returns:
            Quantidade de solicitacoes limpas
        """
        now = datetime.now(timezone.utc)
        retention_date = now - timedelta(days=self.settings.erasure_retention_days)

        result = await self.collection.delete_many(
            {
                "$or": [
                    {"expires_at": {"$lt": now}, "status": ErasureStatus.PENDING_VERIFICATION},
                    {
                        "status": ErasureStatus.COMPLETED,
                        "completed_at": {"$lt": retention_date},
                    },
                    {
                        "status": ErasureStatus.FAILED,
                        "created_at": {"$lt": retention_date},
                    },
                ]
            }
        )

        count = result.deleted_count
        if count > 0:
            logger.info("Solicitacoes expiradas limpas", count=count)

        return count
