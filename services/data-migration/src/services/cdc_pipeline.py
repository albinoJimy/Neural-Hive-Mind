"""
CDC Pipeline Service para Data Migration System.

Implementa pipeline de Change Data Capture usando Debezium para
sincronização de dados em tempo real do banco legado para o moderno.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

import structlog

from src.config.settings import get_settings
from src.models.migration import SchemaMapping, TableMapping

__all__ = [
    "CDCPipeline",
    "CDCStatus",
    "CDCPipelineError",
    "CDCConnectorError",
    "CDCConsumerError",
    "CDCTransformError",
    "get_cdc_pipeline",
]

logger = structlog.get_logger()


class CDCStatus:
    """
    Status do connector e consumo CDC.

    Attributes:
        connector_id: ID do connector Debezium
        connector_state: Estado do connector (RUNNING, PAUSED, STOPPED, FAILED)
        running: Se o consumo está ativo
        task_states: Estados das tarefas do connector
        lag_ms: Lag em milissegundos
        error: Mensagem de erro se aplicável
    """

    def __init__(
        self,
        connector_id: Optional[str],
        connector_state: str,
        running: bool,
        task_states: List[str],
        lag_ms: int,
        error: Optional[str] = None,
    ):
        self.connector_id = connector_id
        self.connector_state = connector_state
        self.running = running
        self.task_states = task_states
        self.lag_ms = lag_ms
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "connector_id": self.connector_id,
            "connector_state": self.connector_state,
            "running": self.running,
            "task_states": self.task_states,
            "lag_ms": self.lag_ms,
            "error": self.error,
        }


class CDCPipelineError(Exception):
    """Exceção base para erros do CDC Pipeline."""


class CDCConnectorError(CDCPipelineError):
    """Erro na operação do connector Debezium."""


class CDCConsumerError(CDCPipelineError):
    """Erro no consumo de eventos CDC."""


class CDCTransformError(CDCPipelineError):
    """Erro na transformação de dados."""


class CDCPipeline:
    """
    Pipeline de Change Data Capture usando Debezium.

    Gerencia conectores Debezium, consome eventos de mudança do Kafka,
    aplica transformações e escreve no banco de dados alvo.
    """

    def __init__(
        self,
        job_id: str,
        kafka_bootstrap_servers: Optional[str] = None,
        debezium_url: Optional[str] = None,
        consumer_group: Optional[str] = None,
        topic_prefix: str = "pg-legacy",
    ):
        """
        Inicializa CDC Pipeline.

        Args:
            job_id: ID do job de migração
            kafka_bootstrap_servers: Endereços do Kafka (bootstrap servers)
            debezium_url: URL da REST API do Debezium
            consumer_group: Grupo de consumidores Kafka
            topic_prefix: Prefixo dos tópicos Debezium
        """
        settings = get_settings()

        self.job_id = job_id
        self.kafka_bootstrap_servers = kafka_bootstrap_servers or settings.kafka_bootstrap_servers
        self.debezium_url = debezium_url or settings.debezium_url
        self.consumer_group = consumer_group or settings.kafka_consumer_group
        self.topic_prefix = topic_prefix

        # Estado interno
        self._connector_id: Optional[str] = None
        self._consumer: Optional[Any] = None
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None

    async def create_connector(
        self,
        schema_mapping: SchemaMapping,
        database_hostname: str,
        database_port: int,
        database_user: str,
        database_password: str,
        database_dbname: str,
        plugin_name: str = "pgoutput",
        snapshot_mode: str = "initial",
    ) -> str:
        """
        Cria connector Debezium para PostgreSQL legado.

        Args:
            schema_mapping: Mapeamento de schema
            database_hostname: Host do PostgreSQL legado
            database_port: Porta do PostgreSQL legado
            database_user: Usuário do PostgreSQL legado
            database_password: Senha do PostgreSQL legado
            database_dbname: Nome do banco de dados legado
            plugin_name: Plugin logical decoding (pgoutput, wal2json, etc)
            snapshot_mode: Modo de snapshot (initial, schema_only, etc)

        Returns:
            ID do connector criado

        Raises:
            CDCConnectorError: Se falhar criação do connector
        """
        connector_name = f"postgres-connector-{self.job_id}"
        self._connector_id = connector_name

        try:
            import httpx

            # Construir configuração do connector
            config = await self._build_debezium_config(
                schema_mapping=schema_mapping,
                database_hostname=database_hostname,
                database_port=database_port,
                database_user=database_user,
                database_password=database_password,
                database_dbname=database_dbname,
                plugin_name=plugin_name,
                snapshot_mode=snapshot_mode,
            )

            payload = {"name": connector_name, "config": config}

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.debezium_url}/connectors",
                    json=payload,
                )

                if response.status_code not in (200, 201):
                    error_msg = response.text or response.reason_phrase
                    logger.error(
                        "debezium_connector_creation_failed",
                        status_code=response.status_code,
                        error=error_msg,
                    )
                    raise CDCConnectorError(
                        f"Falha ao criar connector Debezium: {response.status_code} - {error_msg}"
                    )

                logger.info(
                    "debezium_connector_created",
                    connector_name=connector_name,
                    job_id=self.job_id,
                    tables_count=len(schema_mapping.tables),
                )

                return connector_name

        except httpx.HTTPError as e:
            logger.error("debezium_http_error", error=str(e))
            raise CDCConnectorError(f"Erro HTTP ao criar connector: {e}") from e
        except Exception as e:
            logger.error("connector_creation_error", error=str(e))
            raise CDCConnectorError(f"Erro ao criar connector: {e}") from e

    async def start_cdc(
        self,
        schema_mapping: SchemaMapping,
        target_client: Optional[Any] = None,
    ) -> None:
        """
        Inicia consumo de eventos CDC via Kafka.

        Args:
            schema_mapping: Mapeamento de schema para transformações
            target_client: Cliente do banco alvo para escrita

        Raises:
            CDCPipelineError: Se CDC já estiver rodando
            CDCConsumerError: Se falhar início do consumo
        """
        if self._running:
            raise CDCPipelineError("CDC já está rodando para este job")

        try:
            from aiokafka import AIOKafkaConsumer

            # Construir lista de tópicos
            topics = []
            for table in schema_mapping.tables:
                topic = f"{self.topic_prefix}.{table.source_schema}.{table.source_table}"
                topics.append(topic)

            logger.info(
                "starting_cdc_consumption",
                job_id=self.job_id,
                topics=topics,
            )

            # Criar consumidor
            self._consumer = AIOKafkaConsumer(
                *topics,
                bootstrap_servers=self.kafka_bootstrap_servers,
                group_id=self.consumer_group,
                auto_offset_reset="earliest",
                enable_auto_commit=True,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            )

            await self._consumer.start()
            self._running = True

            logger.info(
                "cdc_consumption_started",
                job_id=self.job_id,
                connector_id=self._connector_id,
            )

        except ImportError as e:
            logger.error("aiokafka_not_available")
            raise CDCConsumerError("aiokafka não disponível. Instale: pip install aiokafka") from e
        except Exception as e:
            logger.error("cdc_start_failed", error=str(e))
            self._running = False
            raise CDCConsumerError(f"Falha ao iniciar consumo CDC: {e}") from e

    async def consume_and_process(
        self,
        schema_mapping: SchemaMapping,
        target_client: Any,
        batch_size: int = 100,
        batch_timeout: float = 1.0,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Consome e processa eventos CDC em lote.

        Args:
            schema_mapping: Mapeamento de schema
            target_client: Cliente do banco alvo
            batch_size: Tamanho do lote para processamento
            batch_timeout: Timeout máximo para acumular lote (segundos)

        Yields:
            Dicionários com estatísticas do lote processado

        Raises:
            CDCConsumerError: Se falhar processamento
        """
        if not self._running or not self._consumer:
            raise CDCPipelineError("CDC não está rodando. Chame start_cdc() primeiro.")

        batch = []
        stats = {
            "processed": 0,
            "inserts": 0,
            "updates": 0,
            "deletes": 0,
            "errors": 0,
        }

        try:
            async for msg in self._consumer:
                try:
                    event = msg.value

                    # Processar evento
                    await self._process_cdc_event(
                        event=event,
                        schema_mapping=schema_mapping,
                        target_client=target_client,
                    )

                    # Atualizar estatísticas
                    op = event.get("op", "")
                    if op == "c" or op == "r":  # create ou read (snapshot)
                        stats["inserts"] += 1
                    elif op == "u":  # update
                        stats["updates"] += 1
                    elif op == "d":  # delete
                        stats["deletes"] += 1

                    stats["processed"] += 1
                    batch.append(event)

                    # Yield batch quando completo
                    if len(batch) >= batch_size:
                        yield stats.copy()
                        batch.clear()
                        stats = {
                            "processed": 0,
                            "inserts": 0,
                            "updates": 0,
                            "deletes": 0,
                            "errors": 0,
                        }

                except CDCPipelineError as e:
                    stats["errors"] += 1
                    logger.error(
                        "cdc_event_processing_error",
                        error=str(e),
                        event_key=msg.key,
                    )
                except Exception as e:
                    stats["errors"] += 1
                    logger.error("cdc_unexpected_error", error=str(e))

        except Exception as e:
            logger.error("cdc_consumption_error", error=str(e))
            raise CDCConsumerError(f"Erro no consumo CDC: {e}") from e
        finally:
            if batch:
                yield stats

    async def _process_cdc_event(
        self,
        event: Dict[str, Any],
        schema_mapping: SchemaMapping,
        target_client: Any,
    ) -> None:
        """
        Processa um evento CDC individual.

        Args:
            event: Evento Debezium
            schema_mapping: Mapeamento de schema
            target_client: Cliente do banco alvo

        Raises:
            CDCConsumerError: Se operação for inválida
            CDCTransformError: Se falhar transformação
        """
        op = event.get("op", "")

        # Extrair informação da fonte
        source = event.get("source", {})
        source_schema = source.get("schema", "public")
        source_table = source.get("table", "")

        # Encontrar mapeamento correspondente
        table_mapping = None
        for table in schema_mapping.tables:
            if table.source_schema == source_schema and table.source_table == source_table:
                table_mapping = table
                break

        if not table_mapping:
            logger.warning(
                "cdc_event_no_mapping",
                schema=source_schema,
                table=source_table,
            )
            return

        # Extrair dados before/after
        before = event.get("before")
        after = event.get("after")

        try:
            if op in ("c", "r"):  # create ou read (snapshot inicial)
                transformed = await self._apply_transformations(after, table_mapping)
                await target_client.insert(
                    table=table_mapping.target_table,
                    data=transformed,
                )

            elif op == "u":  # update
                transformed = await self._apply_transformations(after, table_mapping)
                await target_client.update(
                    table=table_mapping.target_table,
                    data=transformed,
                )

            elif op == "d":  # delete
                transformed = await self._apply_transformations(before, table_mapping)
                await target_client.delete(
                    table=table_mapping.target_table,
                    data=transformed,
                )

            else:
                raise CDCConsumerError(f"Operação CDC desconhecida: {op}")

        except Exception as e:
            logger.error(
                "cdc_process_event_failed",
                op=op,
                table=source_table,
                error=str(e),
            )
            raise CDCTransformError(f"Falha ao processar evento {op}: {e}") from e

    async def _apply_transformations(
        self,
        source_data: Optional[Dict[str, Any]],
        table_mapping: TableMapping,
    ) -> Dict[str, Any]:
        """
        Aplica transformações baseadas no SchemaMapping.

        Args:
            source_data: Dados originais do evento
            table_mapping: Mapeamento da tabela

        Returns:
            Dados transformados
        """
        if not source_data:
            return {}

        transformed = {}

        for field_mapping in table_mapping.fields:
            source_value = source_data.get(field_mapping.source_field)

            # Aplicar valor default se ausente ou None
            if source_value is None and field_mapping.default_value is not None:
                source_value = self._parse_default_value(field_mapping.default_value)

            # Aplicar transformação se especificada
            if source_value is not None and field_mapping.transform:
                source_value = await self._apply_field_transform(
                    value=source_value,
                    transform=field_mapping.transform,
                    data_type=field_mapping.data_type,
                )

            transformed[field_mapping.target_field] = source_value

        return transformed

    async def _apply_field_transform(
        self,
        value: Any,
        transform: str,
        data_type: str,
    ) -> Any:
        """
        Aplica transformação em um campo.

        Args:
            value: Valor original
            transform: Nome da transformação
            data_type: Tipo de dados alvo

        Returns:
            Valor transformado
        """
        if transform == "CAST_TIMESTAMP_UTC":
            if isinstance(value, str):
                # Tentar parse de timestamp comum
                try:
                    # Formatos comuns
                    for fmt in (
                        "%Y-%m-%d %H:%M:%S",
                        "%Y-%m-%d %H:%M:%S.%f",
                        "%Y-%m-%dT%H:%M:%S",
                        "%Y-%m-%dT%H:%M:%S.%f",
                        "%Y-%m-%dT%H:%M:%SZ",
                        "%Y-%m-%dT%H:%M:%S.%fZ",
                    ):
                        try:
                            parsed = datetime.strptime(value, fmt)
                            if parsed.tzinfo is None:
                                parsed = parsed.replace(tzinfo=timezone.utc)
                            return parsed
                        except ValueError:
                            continue
                except Exception:
                    pass
            return value

        elif transform == "CAST_TO_UUID":
            # Já deveria ser string UUID
            return str(value)

        elif transform == "CAST_TO_INT":
            return int(value)

        elif transform == "CAST_TO_FLOAT":
            return float(value)

        elif transform == "PARSE_JSON":
            if isinstance(value, str):
                return json.loads(value)
            return value

        elif transform == "UPPERCASE":
            return str(value).upper() if value else value

        elif transform == "LOWERCASE":
            return str(value).lower() if value else value

        return value

    def _parse_default_value(self, value: str) -> Any:
        """
        Faz parse de valor default.

        Args:
            value: String de valor default

        Returns:
            Valor parseado
        """
        # Valores especiais
        if value.lower() == "null":
            return None
        elif value.lower() == "true":
            return True
        elif value.lower() == "false":
            return False

        # Tentar números
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            pass

        # Tentar JSON
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            pass

        # Retornar como string
        return value

    async def _build_debezium_config(
        self,
        schema_mapping: SchemaMapping,
        database_hostname: str,
        database_port: int,
        database_user: str,
        database_password: str,
        database_dbname: str,
        plugin_name: str = "pgoutput",
        snapshot_mode: str = "initial",
    ) -> Dict[str, str]:
        """
        Constrói configuração do connector Debezium.

        Args:
            schema_mapping: Mapeamento de schema
            database_hostname: Host do PostgreSQL
            database_port: Porta do PostgreSQL
            database_user: Usuário do PostgreSQL
            database_password: Senha do PostgreSQL
            database_dbname: Nome do banco
            plugin_name: Plugin logical decoding
            snapshot_mode: Modo de snapshot

        Returns:
            Dicionário de configuração
        """
        # Construir lista de tabelas
        table_list = []
        for table in schema_mapping.tables:
            table_list.append(f"{table.source_schema}.{table.source_table}")

        # Snapshot mode do metadata ou padrão
        metadata_snapshot = schema_mapping.metadata.get("snapshot_mode")
        if metadata_snapshot:
            snapshot_mode = metadata_snapshot

        config = {
            # Connector básico
            "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
            "database.hostname": database_hostname,
            "database.port": str(database_port),
            "database.user": database_user,
            "database.password": database_password,
            "database.dbname": database_dbname,
            "topic.prefix": self.topic_prefix,
            "plugin.name": plugin_name,
            # Tabelas a incluir
            "table.include.list": ",".join(table_list),
            # Snapshot
            "snapshot.mode": snapshot_mode,
            # Configurações de performance
            "max.batch.size": "1000",
            "max.queue.size": "10000",
            "poll.interval.ms": "500",
        }

        # Adicionar SMTs (Single Message Transformations) se houver
        if any(field.transform for table in schema_mapping.tables for field in table.fields):
            config.update(self._build_smt_config(schema_mapping))

        return config

    def _build_smt_config(self, schema_mapping: SchemaMapping) -> Dict[str, str]:
        """
        Constrói configuração de SMTs para Debezium.

        Args:
            schema_mapping: Mapeamento de schema

        Returns:
            Dicionário com configs SMT
        """
        # Configuração básica de transformação
        return {
            "transforms": "unwrap",
            "transforms.unwrap.type": "io.debezium.transforms.ExtractNewRecordState",
            "transforms.unwrap.drop.tombstones": "true",
            "transforms.unwrap.add.fields": "op,ts_ms",
        }

    async def stop_cdc(self) -> None:
        """
        Para consumo de eventos CDC.

        Para o consumidor Kafka e limpa recursos.
        """
        if not self._running:
            return

        try:
            if self._consumer:
                await self._consumer.stop()
                self._consumer = None

            self._running = False

            logger.info(
                "cdc_consumption_stopped",
                job_id=self.job_id,
                connector_id=self._connector_id,
            )

        except Exception as e:
            logger.error("cdc_stop_error", error=str(e))
            self._running = False

    async def get_cdc_status(self) -> CDCStatus:
        """
        Retorna status do connector e consumo CDC.

        Returns:
            CDCStatus com informações do connector

        Raises:
            CDCConnectorError: Se falhar obtenção de status
        """
        if not self._connector_id:
            return CDCStatus(
                connector_id=None,
                connector_state="NOT_CONFIGURED",
                running=self._running,
                task_states=[],
                lag_ms=0,
                error="Connector não configurado",
            )

        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.debezium_url}/connectors/{self._connector_id}/status"
                )

                if response.status_code == 404:
                    return CDCStatus(
                        connector_id=self._connector_id,
                        connector_state="NOT_FOUND",
                        running=False,
                        task_states=[],
                        lag_ms=0,
                        error="Connector não encontrado no Debezium",
                    )

                if response.status_code != 200:
                    return CDCStatus(
                        connector_id=self._connector_id,
                        connector_state="ERROR",
                        running=self._running,
                        task_states=[],
                        lag_ms=0,
                        error=f"Erro ao obter status: {response.status_code}",
                    )

                status_data = response.json()

                connector_state = status_data.get("connector", {}).get("state", "UNKNOWN")
                tasks = status_data.get("tasks", [])
                task_states = [task.get("state", "UNKNOWN") for task in tasks]

                # Calcular lag
                lag_ms = 0
                for task in tasks:
                    task_lag = task.get("ts_lag", 0)
                    if task_lag > lag_ms:
                        lag_ms = task_lag

                is_running = connector_state == "RUNNING" and self._running

                return CDCStatus(
                    connector_id=self._connector_id,
                    connector_state=connector_state,
                    running=is_running,
                    task_states=task_states,
                    lag_ms=lag_ms,
                )

        except httpx.HTTPError as e:
            logger.error("debezium_status_http_error", error=str(e))
            return CDCStatus(
                connector_id=self._connector_id,
                connector_state="ERROR",
                running=self._running,
                task_states=[],
                lag_ms=0,
                error=f"Erro HTTP ao obter status: {e}",
            )
        except Exception as e:
            logger.error("debezium_status_error", error=str(e))
            return CDCStatus(
                connector_id=self._connector_id,
                connector_state="ERROR",
                running=self._running,
                task_states=[],
                lag_ms=0,
                error=f"Erro ao obter status: {e}",
            )

    async def pause_connector(self) -> None:
        """
        Pausa o connector Debezium.

        Raises:
            CDCConnectorError: Se connector não estiver configurado ou falhar pausa
        """
        if not self._connector_id:
            raise CDCConnectorError("Connector não configurado")

        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.put(
                    f"{self.debezium_url}/connectors/{self._connector_id}/pause"
                )

                if response.status_code not in (200, 202, 204):
                    raise CDCConnectorError(f"Falha ao pausar connector: {response.status_code}")

                logger.info(
                    "debezium_connector_paused",
                    connector_id=self._connector_id,
                )

        except httpx.HTTPError as e:
            raise CDCConnectorError(f"Erro HTTP ao pausar connector: {e}") from e

    async def resume_connector(self) -> None:
        """
        Retoma o connector Debezium.

        Raises:
            CDCConnectorError: Se connector não estiver configurado ou falhar retomada
        """
        if not self._connector_id:
            raise CDCConnectorError("Connector não configurado")

        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.put(
                    f"{self.debezium_url}/connectors/{self._connector_id}/resume"
                )

                if response.status_code not in (200, 202, 204):
                    raise CDCConnectorError(f"Falha ao retomar connector: {response.status_code}")

                logger.info(
                    "debezium_connector_resumed",
                    connector_id=self._connector_id,
                )

        except httpx.HTTPError as e:
            raise CDCConnectorError(f"Erro HTTP ao retomar connector: {e}") from e

    async def delete_connector(self) -> None:
        """
        Deleta o connector Debezium.

        Opera de forma idempotente - não levanta erro se connector não existir.
        """
        if not self._connector_id:
            return

        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.delete(
                    f"{self.debezium_url}/connectors/{self._connector_id}"
                )

                # 404 é aceitável (connector já não existe)
                if response.status_code not in (200, 204, 404):
                    logger.warning(
                        "debezium_connector_delete_unexpected",
                        status_code=response.status_code,
                    )
                else:
                    logger.info(
                        "debezium_connector_deleted",
                        connector_id=self._connector_id,
                    )

        except httpx.HTTPError as e:
            logger.warning("debezium_delete_http_error", error=str(e))
        finally:
            self._connector_id = None

    async def __aenter__(self):
        """Suporte a context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup ao sair do context manager."""
        await self.stop_cdc()


# Singleton instance
_cdc_pipeline: Optional[CDCPipeline] = None


def get_cdc_pipeline(
    job_id: Optional[str] = None,
) -> CDCPipeline:
    """
    Retorna singleton do CDC Pipeline.

    Args:
        job_id: ID do job (obrigatório na primeira chamada)

    Returns:
        Instância de CDCPipeline
    """
    global _cdc_pipeline
    if _cdc_pipeline is None:
        if not job_id:
            raise ValueError("job_id é obrigatório na primeira chamada")
        _cdc_pipeline = CDCPipeline(job_id=job_id)
    return _cdc_pipeline
