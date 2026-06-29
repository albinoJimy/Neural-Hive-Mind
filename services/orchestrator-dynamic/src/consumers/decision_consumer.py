"""
Kafka consumer para tópico plans.consensus.
Consome decisões consolidadas e inicia workflows Temporal.

Suporta deserialização Avro (Confluent wire format) e JSON fallback.
Implementa deduplicação baseada em Redis para idempotência.
"""

import io
import json
import os
from datetime import datetime, timezone
from typing import Any

import structlog
from aiokafka import AIOKafkaConsumer
from opentelemetry import trace

from neural_hive_observability import instrument_kafka_consumer, trace_plan
from neural_hive_observability.context import extract_context_from_headers, set_baggage

# Avro support
try:
    import fastavro
    from confluent_kafka.schema_registry import SchemaRegistryClient

    AVRO_AVAILABLE = True
except ImportError:
    AVRO_AVAILABLE = False

from src.capabilities.generate import (
    GenerateCapability,
    GenerateRequest,
    GenerateTarget,
    UnsupportedStackError,
)
from src.workflows.fluxo_g_workflow import FluxoGWorkflow
from src.workflows.migrate_journey_workflow import MigrateJourneyWorkflow
from src.workflows.orchestration_workflow import OrchestrationWorkflow

logger = structlog.get_logger()


# Drift detection support
try:
    from src.ml.drift_detector import DriftDetector  # noqa: F401 - deteção de feature

    DRIFT_DETECTION_AVAILABLE = True
except ImportError:
    DRIFT_DETECTION_AVAILABLE = False
    logger.warning("drift_detector_not_available", message="DriftDetector module not found")

# Drift-retrain connector support (FASE 0)
try:
    from src.ml.drift_retrain_connector import (  # noqa: F401 - deteção de feature
        DriftAlert,
        DriftRetrainConnector,
        get_drift_retrain_connector,
    )

    DRIFT_RETRAIN_AVAILABLE = True
except ImportError:
    DRIFT_RETRAIN_AVAILABLE = False
    logger.warning(
        "drift_retrain_connector_not_available", message="DriftRetrainConnector module not found"
    )


def _deserialize_avro_or_json(raw_bytes: bytes, schema_registry_url: str | None = None) -> dict:
    """
    Deserialize message supporting both Avro (Confluent wire format) and JSON.

    Confluent wire format:
    - Byte 0: Magic byte (0x00)
    - Bytes 1-4: Schema ID (big-endian int)
    - Bytes 5+: Avro payload
    """
    # Log bytes brutos para debug (primeiros 100 bytes)
    logger.debug(
        "avro_deserialization_attempt",
        raw_bytes_hex=raw_bytes[:100].hex() if len(raw_bytes) >= 100 else raw_bytes.hex(),
        bytes_length=len(raw_bytes),
        first_bytes=list(raw_bytes[:20]),
    )

    if len(raw_bytes) < 5:
        # Too short for Avro wire format, try JSON
        logger.debug("message_too_short_for_avro", trying_json=True)
        try:
            return json.loads(raw_bytes.decode("utf-8"))
        except json.JSONDecodeError as e:
            logger.exception(
                "json_deserialization_failed", error=str(e), raw_bytes_preview=raw_bytes[:100]
            )
            raise ValueError(f"Failed to deserialize as JSON: {e}") from e

    magic_byte = raw_bytes[0]
    if magic_byte != 0:
        # Not Avro wire format, try JSON
        logger.debug("invalid_magic_byte", magic_byte=magic_byte, trying_json=True)
        try:
            return json.loads(raw_bytes.decode("utf-8"))
        except json.JSONDecodeError as e:
            logger.exception(
                "json_deserialization_failed", error=str(e), raw_bytes_preview=raw_bytes[:100]
            )
            raise ValueError(f"Failed to deserialize as JSON: {e}") from e

    # Extract schema ID and Avro payload
    schema_id = int.from_bytes(raw_bytes[1:5], byteorder="big")
    avro_payload = raw_bytes[5:]

    logger.debug(
        "avro_wire_format_detected",
        schema_id=schema_id,
        payload_size=len(avro_payload),
        payload_hex=avro_payload[:50].hex() if len(avro_payload) >= 50 else avro_payload.hex(),
    )

    if AVRO_AVAILABLE:
        try:
            # Configurar conf para Schema Registry com suporte SSL
            conf = {"url": schema_registry_url}
            if schema_registry_url.startswith("https://"):
                # Adicionar configuração SSL para HTTPS
                # Desabilitar verificação de certificado para ambientes internos
                conf["ssl.ca.location"] = "/etc/ssl/certs/ca-bundle.crt"
                conf["ssl.check.hostname"] = "false"
                conf["ssl.endpoint.identification.algorithm"] = "none"
                logger.debug("using_ssl_for_schema_registry", url=schema_registry_url)

            client = SchemaRegistryClient(conf)
            schema = client.get_schema(schema_id)
            logger.debug(
                "schema_retrieved", schema_id=schema_id, schema_schema_str=schema.schema_str[:200]
            )
            writer_schema = fastavro.parse_schema(json.loads(schema.schema_str))
            reader = io.BytesIO(avro_payload)
            # schemaless_reader pode retornar um generator ou um dict diretamente
            avro_result = fastavro.schemaless_reader(reader, writer_schema)
            # Converter para dict se necessário (pode vir como dict ou como generator)
            result = (
                dict(avro_result)
                if isinstance(avro_result, dict)
                or (not isinstance(avro_result, dict) and hasattr(avro_result, "__iter__"))
                else avro_result
            )
            logger.info(
                "avro_deserialization_success",
                schema_id=schema_id,
                result_type=type(result).__name__,
            )
            return result
        except Exception as e:
            logger.exception(
                "avro_deserialization_failed",
                schema_id=schema_id,
                error=str(e),
                error_type=type(e).__name__,
                payload_preview=avro_payload[:100].hex(),
            )
            # Tentar JSON como fallback
            try:
                json_result = json.loads(avro_payload.decode("utf-8"))
                logger.warning("avro_failed_json_success", schema_id=schema_id)
                return json_result
            except (json.JSONDecodeError, UnicodeDecodeError) as json_err:
                logger.exception(
                    "json_fallback_also_failed", json_error=str(json_err), avro_error=str(e)
                )
                raise ValueError(
                    f"Failed to deserialize Avro message: {e}. JSON fallback also failed: {json_err}"
                ) from e

    raise ValueError("Avro deserialization not available")


def _get_workflow_type_from_plan(plan: dict) -> str:
    """
    Extrai workflow_type do Cognitive Plan.

    Args:
        plan: Dicionário do Cognitive Plan

    Returns:
        "orchestration" (default) ou "generation"
    """
    return plan.get("workflow_type", "orchestration")


def _select_workflow_class(workflow_type: str):
    """
    Seleciona a classe de workflow baseado no tipo.

    Args:
        workflow_type: "orchestration" ou "generation"

    Returns:
        OrchestrationWorkflow ou FluxoGWorkflow
    """
    if workflow_type == "generation":
        return FluxoGWorkflow
    return OrchestrationWorkflow


def _get_journey_from_plan(plan: dict) -> str:
    """Extrai a journey do Cognitive Plan (decidida no STE).

    Defensivo e case-insensitive. Planos antigos (sem journey) ou com journey
    vazia (default do modelo) devolvem "UNKNOWN", o que aciona o fallback ao
    roteamento legado por workflow_type.

    Args:
        plan: Dicionário do Cognitive Plan.

    Returns:
        Journey em UPPER_CASE (ex: "J3_BUILD") ou "UNKNOWN".
    """
    journey = plan.get("journey")
    if isinstance(journey, str) and journey.strip():
        return journey.strip().upper()
    return "UNKNOWN"


def _is_plan_only(journey: str) -> bool:
    """J1_PLAN_ONLY significa planeamento sem execução a jusante."""
    return journey == "J1_PLAN_ONLY"


def _select_workflow_class_by_journey(journey: str):
    """Seleciona a classe de workflow por journey (decisão única do STE).

    - J3_BUILD       -> FluxoGWorkflow (geração / fluxo G)
    - J2_ORCHESTRATE -> OrchestrationWorkflow
    - J4_MIGRATE     -> OrchestrationWorkflow (cutover é sub-fluxo da orquestração)
    - J1_PLAN_ONLY   -> None (sem execução; plan-only)
    - UNKNOWN/outras -> None (sinaliza ao chamador para fazer fallback workflow_type)

    Returns:
        Classe de workflow, ou None quando não há decisão de execução por journey
        (plan-only ou journey ausente/desconhecida → fallback workflow_type).

    NOTA (fronteira GENERATE): para jornadas de geração esta função NÃO é a
    autoridade de routing — `_requires_generate_capability` é. O mapeamento
    J3_BUILD → FluxoGWorkflow mantém-se aqui (compatibilidade / fallback legado),
    mas o caminho de geração é interceptado antes pela capacidade. Ao adicionar
    uma nova jornada de geração, atualiza `_journey_requires_generation` (e NÃO
    apenas esta função), senão a nova jornada arrancaria o FluxoGWorkflow sem a
    resolução de estratégia de stack (plano não enriquecido).
    """
    if journey == "J3_BUILD":
        return FluxoGWorkflow
    if journey in ("J2_ORCHESTRATE", "J4_MIGRATE"):
        return OrchestrationWorkflow
    # J1_PLAN_ONLY e UNKNOWN não têm workflow de execução por journey.
    return None


def _journey_requires_generation(journey: str) -> bool:
    """Jornadas que requerem a capacidade GENERATE (hoje só J3_BUILD).

    A decisão deriva da SEMÂNTICA da jornada (não de conhecer a classe do
    workflow) — é isto que des-vaza a fronteira.
    """
    return journey == "J3_BUILD"


def _requires_generate_capability(journey: str, workflow_type: str) -> bool:
    """Autoridade ÚNICA: a execução requer a capacidade GENERATE?

    Partilhada pelo caminho direto (decision_consumer) e pelo resume
    pós-aprovação (main.py) para que NUNCA divirjam. A decisão primária deriva da
    jornada (`_journey_requires_generation`); o fallback compat cobre planos sem
    journey (UNKNOWN) com `workflow_type=generation` — preservando o roteamento
    legado por workflow_type.

    Plan-only (J1) NUNCA executa: o guard explícito torna o contrato da função
    auto-consistente (não depende do `_is_plan_only` upstream dos call sites),
    senão o fallback compat (`workflow_class is None`) classificaria J1+generation
    como geração — ver auditoria de qualidade Task 5 (CR-003).
    """
    if _is_plan_only(journey):
        return False
    return _journey_requires_generation(journey) or (
        _select_workflow_class_by_journey(journey) is None and workflow_type == "generation"
    )


def _extract_generate_target(plan: dict) -> GenerateTarget:
    """Deriva a stack-alvo do plano para a capacidade GENERATE.

    Planos de geração hoje não fixam a stack explicitamente (o code-forge
    materializa FastAPI a partir do intent). Na ausência de language/framework
    em parameters usamos a única stack provada (python/fastapi), preservando o
    comportamento atual. Um plano que FIXE uma stack diferente é resolvido pelo
    registry (desconhecida → FAILED), sem fallback silencioso — multi-linguagem-ready.

    Um valor só-com-espaços (whitespace) é tratado como *ausência* de stack (cai
    no default), nunca como input malformado: assim a derivação da target não
    levanta ValidationError fora do ``try`` do caller (que evitaria o tratamento
    gracioso e produziria poison-message/HTTP 500). Stack real mas desconhecida
    continua a falhar fechada no registry — sem fallback silencioso.
    """
    params = plan.get("parameters") or {}
    language = str(params.get("language") or "").strip() or "python"
    framework = str(params.get("framework") or "").strip() or "fastapi"
    return GenerateTarget(language=language, framework=framework)


def _journey_requires_migration(journey: str) -> bool:
    """Jornadas que requerem a capacidade MIGRATE (hoje só J4_MIGRATE).

    Espelha ``_journey_requires_generation``: a decisão deriva da SEMÂNTICA da
    jornada (não de conhecer a classe do workflow) — é isto que des-vaza a
    fronteira de migração.
    """
    return journey == "J4_MIGRATE"


def _requires_migration(journey: str, workflow_type: str) -> bool:
    """Autoridade ÚNICA: a execução requer a capacidade MIGRATE?

    Espelha a ESTRUTURA de ``_requires_generate_capability``: a decisão deriva da
    jornada (``_journey_requires_migration``) e plan-only (J1) NUNCA executa. Ao
    contrário de GENERATE, não há fallback compat por ``workflow_type`` (não
    existe "migration" legado por workflow_type), pelo que ``workflow_type`` é
    aceite por simetria de assinatura mas não condiciona a decisão hoje.

    NOTA DE ÂMBITO (Fase 1): esta autoridade serve, por enquanto, APENAS o caminho
    direto (``decision_consumer``). Ao contrário de GENERATE — que já partilha a
    autoridade com o resume pós-aprovação (``main.py``) —, o resume ainda NÃO
    invoca esta função nem arranca ``DataMigrationWorkflow``. Um plano J4 aprovado
    por revisão humana cai hoje na orquestração genérica; fechar essa paridade
    (resume → MIGRATE) é escopo de fase posterior. Não afirmar paridade já
    existente com o resume.
    """
    if _is_plan_only(journey):
        return False
    return _journey_requires_migration(journey)


class InvalidMigrationConfigError(ValueError):
    """``migration_config`` ausente ou inválido — fail-closed, sem defaults.

    Anti-verde-falso: um plano J4 com ``migration_config`` presente mas malformado
    (sem ``legacy_connection_id`` ou com ``tables`` vazias) NÃO pode ser migrado
    nem cair silenciosamente na orquestração genérica — o consumer trata-o como
    erro permanente.
    """


def _extract_migration_config(plan: dict) -> dict:
    """Deriva e valida o ``migration_config`` do plano J4 (fail-closed).

    Reusa o formato de ``build_j4_migrate_plan_message`` (Fase 0): exige
    ``legacy_connection_id`` (str não-vazia) e ``tables`` (lista com ≥1 entrada
    não-vazia). Sem defaults silenciosos — ausente/inválido levanta
    ``InvalidMigrationConfigError`` (ao contrário de GENERATE, MIGRATE não tem
    stack-default provada). ``modern_connection_id`` é opcional; ``schema``
    assume "public" quando ausente.
    """
    raw = plan.get("migration_config")
    if not isinstance(raw, dict) or not raw:
        raise InvalidMigrationConfigError("migration_config ausente ou vazio")

    legacy = str(raw.get("legacy_connection_id") or "").strip()
    if not legacy:
        raise InvalidMigrationConfigError("legacy_connection_id ausente ou vazio")

    tables_raw = raw.get("tables")
    tables = (
        [str(t).strip() for t in tables_raw if str(t).strip()]
        if isinstance(tables_raw, list)
        else []
    )
    if not tables:
        raise InvalidMigrationConfigError("tables ausente ou vazia")

    modern = str(raw.get("modern_connection_id") or "").strip()
    schema = str(raw.get("schema") or "").strip() or "public"
    return {
        "legacy_connection_id": legacy,
        "modern_connection_id": modern or None,
        "schema": schema,
        "tables": tables,
    }


class DecisionConsumer:
    """Consumer Kafka para decisões consolidadas."""

    # TTL para deduplicação de decisões (24 horas)
    DEDUPLICATION_TTL_SECONDS = 86400
    # TTL para chave de processing (5 minutos - tempo máximo esperado de processamento)
    PROCESSING_TTL_SECONDS = 300

    def __init__(
        self,
        config,
        temporal_client,  # Client ou TemporalClientWrapper
        mongodb_client,
        redis_client=None,
        metrics=None,
        drift_detector=None,
        drift_retrain_connector=None,
        sasl_username_override: str | None = None,
        sasl_password_override: str | None = None,
    ):
        """
        Inicializa o consumer.

        Args:
            config: Configurações da aplicação
            temporal_client: Cliente Temporal para iniciar workflows
            mongodb_client: Cliente MongoDB para buscar Cognitive Plans
            redis_client: Cliente Redis para deduplicação (opcional)
            metrics: Instância de OrchestratorMetrics para métricas compartilhadas
            drift_detector: Instância de DriftDetector para verificar drift ML
            drift_retrain_connector: Instância de DriftRetrainConnector (FASE 0)
            sasl_username_override: Username SASL (ex: obtido do Vault)
            sasl_password_override: Password SASL (ex: obtido do Vault)
        """
        self.config = config
        self.temporal_client = temporal_client
        # Capacidade GENERATE construída com o cliente Temporal injetado (mesmos
        # prefix/queue do caminho legado → workflow_id idêntico). É a fronteira
        # de geração: o consumer delega-lhe o arranque do FluxoGWorkflow.
        self.generate_capability = GenerateCapability(
            temporal_client=temporal_client,
            task_queue=config.temporal_task_queue,
            workflow_id_prefix=config.temporal_workflow_id_prefix,
        )
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client
        self.metrics = metrics
        self.drift_detector = drift_detector
        self.drift_retrain_connector = drift_retrain_connector
        self.consumer: AIOKafkaConsumer | None = None
        self.running = False
        self.sasl_username = (
            sasl_username_override
            if sasl_username_override is not None
            else config.kafka_sasl_username
        )
        self.sasl_password = (
            sasl_password_override
            if sasl_password_override is not None
            else config.kafka_sasl_password
        )
        self.security_protocol = config.kafka_security_protocol
        self.sasl_mechanism = getattr(config, "kafka_sasl_mechanism", "PLAIN")
        self.schema_registry_url = os.getenv(
            "SCHEMA_REGISTRY_URL",
            "http://schema-registry.kafka.svc.cluster.local:8080/apis/ccompat/v6",
        )

        # Configuração de drift detection
        self.ml_drift_check_enabled = getattr(config, "ml_drift_check_enabled", False)

    async def initialize(self):
        """Inicializa o consumer Kafka."""
        logger.info("Inicializando Kafka consumer", topic=self.config.kafka_consensus_topic)

        # Não usar value_deserializer - deserialização manual para suportar Avro e JSON
        consumer_config = {
            "bootstrap_servers": self.config.kafka_bootstrap_servers,
            "group_id": self.config.kafka_consumer_group_id,
            "auto_offset_reset": self.config.kafka_auto_offset_reset,
            "enable_auto_commit": self.config.kafka_enable_auto_commit,
            # Recebemos bytes crus para deserialização manual (Avro/JSON)
        }

        if self.security_protocol and self.security_protocol != "PLAINTEXT":
            consumer_config.update(
                {
                    "security_protocol": self.security_protocol,
                    "sasl_mechanism": self.sasl_mechanism,
                    "sasl_plain_username": self.sasl_username,
                    "sasl_plain_password": self.sasl_password,
                }
            )
            logger.info(
                "Kafka consumer configurado com SASL",
                mechanism=self.sasl_mechanism,
                security_protocol=self.security_protocol,
            )

        self.consumer = instrument_kafka_consumer(
            AIOKafkaConsumer(self.config.kafka_consensus_topic, **consumer_config)
        )
        logger.info("Kafka consumer instrumented with OpenTelemetry")

        await self.consumer.start()
        logger.info("Kafka consumer inicializado com sucesso")

    async def start(self):
        """Inicia loop de consumo de mensagens."""
        if not self.consumer:
            raise RuntimeError("Consumer não foi inicializado. Chame initialize() primeiro.")

        logger.info("Iniciando consumo de mensagens", topic=self.config.kafka_consensus_topic)
        self.running = True

        try:
            async for message in self.consumer:
                if not self.running:
                    break

                try:
                    await self._process_message(message)
                except Exception as e:
                    logger.error(
                        "Erro ao processar mensagem",
                        topic=message.topic,
                        partition=message.partition,
                        offset=message.offset,
                        error=str(e),
                        exc_info=True,
                    )

        except Exception as e:
            logger.error("Erro no loop de consumo", error=str(e), exc_info=True)
            raise

    async def stop(self):
        """Para o consumer gracefully."""
        logger.info("Parando Kafka consumer")
        self.running = False

        if self.consumer:
            await self.consumer.stop()

        logger.info("Kafka consumer parado")

    async def _is_duplicate_decision(self, decision_id: str) -> bool:
        """
        Verificar se decisão já foi processada usando Redis (two-phase scheme).

        Implementa deduplicação em duas fases:
        1. Verifica se já existe chave 'processed' (processamento concluído anteriormente)
        2. Verifica se já existe chave 'processing' (processamento em andamento)
        3. Se nenhuma existe, marca como 'processing' com TTL curto

        Args:
            decision_id: ID da decisão consolidada

        Returns:
            True se duplicata (já processada ou em processamento), False caso contrário
        """
        if not self.redis_client:
            logger.warning("redis_client_not_available_skipping_deduplication")
            return False

        try:
            processed_key = f"decision:processed:{decision_id}"
            processing_key = f"decision:processing:{decision_id}"

            # Fase 1: Verificar se já foi processada com sucesso
            if await self.redis_client.exists(processed_key):
                logger.info(
                    "duplicate_decision_detected",
                    decision_id=decision_id,
                    message="Decisão já foi processada com sucesso, ignorando",
                )
                if self.metrics:
                    self.metrics.record_duplicate_detected("decision_consumer")
                return True

            # Fase 2: Tentar marcar como em processamento (SETNX)
            # Retorna True se chave foi criada (primeira vez), False se já existe
            is_new = await self.redis_client.set(
                processing_key, "1", ex=self.PROCESSING_TTL_SECONDS, nx=True
            )

            if not is_new:
                logger.info(
                    "decision_already_processing",
                    decision_id=decision_id,
                    message="Decisão já está em processamento por outro worker, ignorando",
                )
                if self.metrics:
                    self.metrics.record_duplicate_detected("decision_consumer")
                return True

            logger.debug("decision_marked_as_processing", decision_id=decision_id)
            return False

        except Exception as e:
            logger.exception(
                "deduplication_check_failed",
                decision_id=decision_id,
                error=str(e),
                message="Continuando processamento sem deduplicação",
            )
            # Fail-open: continuar processamento em caso de erro no Redis
            return False

    async def _mark_decision_processed(self, decision_id: str) -> None:
        """
        Marca decisão como processada com sucesso e remove chave de processing.

        Args:
            decision_id: ID da decisão consolidada
        """
        if not self.redis_client:
            return

        try:
            processed_key = f"decision:processed:{decision_id}"
            processing_key = f"decision:processing:{decision_id}"

            # Marcar como processada com TTL longo
            await self.redis_client.set(processed_key, "1", ex=self.DEDUPLICATION_TTL_SECONDS)

            # Remover chave de processing
            await self.redis_client.delete(processing_key)

            logger.debug("decision_marked_as_processed", decision_id=decision_id)

        except Exception as e:
            logger.exception(
                "mark_decision_processed_failed", decision_id=decision_id, error=str(e)
            )

    async def _clear_decision_processing(self, decision_id: str) -> None:
        """
        Limpa chave de processing para permitir reprocessamento após falha.

        Args:
            decision_id: ID da decisão consolidada
        """
        if not self.redis_client:
            return

        try:
            processing_key = f"decision:processing:{decision_id}"
            await self.redis_client.delete(processing_key)
            logger.debug("decision_processing_cleared", decision_id=decision_id)

        except Exception as e:
            logger.exception(
                "clear_decision_processing_failed", decision_id=decision_id, error=str(e)
            )

    async def _check_ml_drift(self) -> dict[str, Any] | None:
        """
        Verifica drift em modelos ML antes de processar decisão.

        Returns:
            Dict com relatório de drift ou None se drift detection não disponível
        """
        if not self.ml_drift_check_enabled:
            return None

        if not self.drift_detector:
            logger.debug("drift_detector_not_configured", message="Drift detector not available")
            return None

        try:
            drift_report = await self.drift_detector.run_drift_check()

            if drift_report.get("overall_status") != "ok":
                overall_status = drift_report.get("overall_status")
                logger.warning(
                    "ml_drift_detected",
                    status=overall_status,
                    recommendations=drift_report.get("recommendations", []),
                    feature_drift=drift_report.get("feature_drift", {}),
                    prediction_drift=drift_report.get("prediction_drift", {}),
                    target_drift=drift_report.get("target_drift", {}),
                )

                # Registrar métrica de drift detectado
                if self.metrics:
                    self.metrics.record_drift_score(
                        drift_type="overall",
                        score=1.0 if overall_status == "critical" else 0.5,
                        model_name="orchestrator-ml",
                    )

                # FASE 0: Trigger auto-retrain se connector disponível
                if self.drift_retrain_connector:
                    await self._trigger_retrain_on_drift(drift_report)

            return drift_report

        except Exception as e:
            logger.exception("ml_drift_check_failed", error=str(e))
            # Não falhar o processamento por erro no drift check
            return None

    async def _trigger_retrain_on_drift(self, drift_report: dict[str, Any]) -> None:
        """
        Trigger auto-retrain quando drift significativo é detectado.

        Args:
            drift_report: Relatório de drift do DriftDetector
        """
        if not DRIFT_RETRAIN_AVAILABLE:
            return

        if not self.drift_retrain_connector:
            return

        try:
            # Determinar severidade e tipo de drift
            overall_status = drift_report.get("overall_status", "ok")
            feature_drift = drift_report.get("feature_drift", {})
            prediction_drift = drift_report.get("prediction_drift", {})
            target_drift = drift_report.get("target_drift", {})

            # Encontrar o drift mais significativo
            max_drift_score = 0.0
            drift_type = "unknown"
            drift_details = {}

            for dt, data in [
                ("feature", feature_drift),
                ("prediction", prediction_drift),
                ("target", target_drift),
            ]:
                score = data.get("max_drift_score", 0.0)
                if score > max_drift_score:
                    max_drift_score = score
                    drift_type = dt
                    drift_details = data

            severity = (
                "ok"
                if overall_status == "ok"
                else ("warning" if overall_status == "warning" else "critical")
            )

            # Parse timestamp (pode ser string ISO ou datetime)
            timestamp_str = drift_report.get("timestamp")
            if isinstance(timestamp_str, str):
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                except ValueError:
                    timestamp = datetime.now(timezone.utc)
            else:
                timestamp = timestamp_str or datetime.now(timezone.utc)

            # Criar alerta de drift
            alert = DriftAlert(
                timestamp=timestamp,
                model_name="nhm_approval_model",
                model_version=drift_report.get("model_version", "unknown"),
                drift_type=drift_type,
                severity=severity,
                score=max_drift_score,
                details=drift_details,
            )

            # Trigger retrain se necessário
            retrain_result = await self.drift_retrain_connector.trigger_retrain_if_needed(alert)

            if retrain_result.get("triggered"):
                logger.info(
                    "ml_retrain_triggered",
                    reason=retrain_result.get("reason"),
                    priority=retrain_result.get("priority"),
                    drift_type=drift_type,
                    drift_score=max_drift_score,
                )
            else:
                logger.debug(
                    "ml_retrain_not_triggered",
                    reason=retrain_result.get("reason"),
                )

        except Exception as e:
            logger.exception("trigger_retrain_on_drift_failed", error=str(e))
            # Não falhar o processamento por erro no trigger

    @trace_plan()
    async def _process_message(self, message):
        """
        Processa uma mensagem do Kafka.

        Args:
            message: Mensagem do Kafka contendo ConsolidatedDecision
        """
        # Preserve tracing headers as binary for W3C traceparent/baggage compatibility
        extract_context_from_headers(message.headers or [])

        business_headers = {}
        for key, value in message.headers or []:
            if key in ("x-neural-hive-intent-id", "x-neural-hive-plan-id", "x-neural-hive-user-id"):
                if isinstance(value, bytes):
                    try:
                        business_headers[key] = value.decode("utf-8")
                    except Exception:
                        continue
                elif value is not None:
                    business_headers[key] = str(value)

        intent_id = business_headers.get("x-neural-hive-intent-id")
        plan_id = business_headers.get("x-neural-hive-plan-id")
        user_id = business_headers.get("x-neural-hive-user-id")

        if intent_id:
            set_baggage("intent_id", intent_id)
        if plan_id:
            set_baggage("plan_id", plan_id)
        if user_id:
            set_baggage("user_id", user_id)

        # Deserializar mensagem (suporta Avro e JSON)
        raw_value = message.value
        if isinstance(raw_value, bytes):
            try:
                consolidated_decision = _deserialize_avro_or_json(
                    raw_value, self.schema_registry_url
                )
            except Exception as deser_err:
                logger.warning("avro_deserialization_failed_trying_json", error=str(deser_err))
                # Fallback para JSON
                consolidated_decision = json.loads(raw_value.decode("utf-8"))
        else:
            consolidated_decision = raw_value

        logger.info(
            "Mensagem recebida do Kafka",
            topic=message.topic,
            partition=message.partition,
            offset=message.offset,
            decision_id=consolidated_decision.get("decision_id"),
            plan_id=consolidated_decision.get("plan_id"),
        )
        span = trace.get_current_span()
        decision_id = consolidated_decision.get("decision_id")
        if decision_id:  # Só seta se não for None
            span.set_attribute("neural.hive.decision.id", decision_id)
        span.set_attribute("neural.hive.plan.id", consolidated_decision.get("plan_id"))
        span.set_attribute("neural.hive.intent.id", consolidated_decision.get("intent_id"))
        span.set_attribute("messaging.kafka.topic", message.topic)
        span.set_attribute("messaging.kafka.partition", message.partition)
        span.set_attribute("messaging.kafka.offset", message.offset)

        # Verificar duplicata antes de processar
        if decision_id and await self._is_duplicate_decision(decision_id):
            span.set_attribute("neural.hive.duplicate", True)
            # Commit offset para não reprocessar
            await self.consumer.commit()
            logger.info(
                "duplicate_decision_skipped", decision_id=decision_id, offset=message.offset
            )
            return

        # Verificar drift em modelos ML antes de processar
        drift_report = await self._check_ml_drift()
        if drift_report and drift_report.get("overall_status") != "ok":
            # Marcar decisão com drift detectado para tracking
            consolidated_decision["drift_detected"] = True
            consolidated_decision["drift_status"] = drift_report.get("overall_status")
            consolidated_decision["drift_timestamp"] = drift_report.get("timestamp")

            # Adicionar ao span para tracing
            span.set_attribute("neural.hive.ml.drift_detected", True)
            span.set_attribute("neural.hive.ml.drift_status", drift_report.get("overall_status"))

        try:
            # Detectar se é um Cognitive Plan direto do STE (sem approval)
            # ou uma Decisão Consolidada (com approval)
            is_direct_plan = (
                "tasks" in consolidated_decision and "decision_id" not in consolidated_decision
            )

            if is_direct_plan:
                # Plan direto do STE - tratar como Cognitive Plan
                logger.info(
                    "Plan direto do STE detectado (sem decision_id)",
                    plan_id=consolidated_decision.get("plan_id"),
                    tasks_count=len(consolidated_decision.get("tasks", [])),
                )
                plan_id = consolidated_decision["plan_id"]
                cognitive_plan = consolidated_decision
                decision_id = None
            else:
                # Decisão consolidada - validar campos obrigatórios
                required_fields = ["decision_id", "plan_id", "final_decision"]
                for field in required_fields:
                    if field not in consolidated_decision:
                        logger.error(f"Campo obrigatório ausente: {field}")
                        return

                # Verificar se decisão foi aprovada
                final_decision = consolidated_decision.get("final_decision")
                if final_decision == "reject":
                    logger.warning(
                        "Decisão foi rejeitada, não gerando tickets",
                        decision_id=consolidated_decision["decision_id"],
                    )
                    await self.consumer.commit()
                    return

                if consolidated_decision.get("requires_human_review", False):
                    logger.info(
                        "Decisão requer revisão humana, aguardando aprovação",
                        decision_id=consolidated_decision["decision_id"],
                    )
                    await self.consumer.commit()
                    return

                # Buscar Cognitive Plan associado no MongoDB
                plan_id = consolidated_decision["plan_id"]
                cognitive_plan = await self.mongodb_client.get_cognitive_plan(plan_id)

            if not cognitive_plan:
                logger.error(
                    "Cognitive Plan não encontrado no ledger",
                    plan_id=plan_id,
                    # is_direct_plan força decision_id ausente → .get evita KeyError
                    # (que faria loop infinito de retry sem commit do offset).
                    decision_id=consolidated_decision.get("decision_id"),
                )
                # Não commitar o offset para permitir retry
                # Este é um erro que pode ser temporário (plan ainda não persistido)
                return

            # Validar campos obrigatórios do Cognitive Plan
            required_plan_fields = ["tasks", "execution_order", "risk_band"]
            for field in required_plan_fields:
                if field not in cognitive_plan:
                    logger.error(
                        "Cognitive Plan com campos obrigatórios ausentes",
                        plan_id=plan_id,
                        missing_field=field,
                    )
                    # Commitar porque este é um erro permanente
                    await self.consumer.commit()
                    return

            logger.info(
                "Cognitive Plan recuperado com sucesso",
                plan_id=plan_id,
                task_count=len(cognitive_plan.get("tasks", [])),
                risk_band=cognitive_plan.get("risk_band"),
            )

            # Iniciar workflow Temporal
            workflow_id = f"{self.config.temporal_workflow_id_prefix}{plan_id}"

            # Serializar cognitive_plan para JSON para converter datetimes
            # Isso é necessário para plans diretos do STE que contêm datetime
            import json
            from datetime import datetime

            def convert_datetime(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                raise TypeError(f"Type {type(obj)} not serializable")

            cognitive_plan_json = json.loads(json.dumps(cognitive_plan, default=convert_datetime))

            input_data = {
                "consolidated_decision": consolidated_decision if not is_direct_plan else None,
                "cognitive_plan": cognitive_plan_json,
                "is_direct_plan": is_direct_plan,
            }

            # Routing por Journey (spec journey-router Fase 3): a journey é decidida
            # no STE e gravada no plano; aqui apenas roteamos por ela (não se
            # re-deriva). COMPATIBILIDADE: planos sem journey ou journey=UNKNOWN
            # (planos antigos) fazem fallback ao roteamento legado por workflow_type.
            journey = _get_journey_from_plan(cognitive_plan_json)
            workflow_type = _get_workflow_type_from_plan(cognitive_plan_json)

            # J1_PLAN_ONLY: planeamento sem execução a jusante — não inicia workflow.
            if _is_plan_only(journey):
                logger.info(
                    "journey_plan_only_no_execution",
                    plan_id=plan_id,
                    journey=journey,
                    message="Journey J1_PLAN_ONLY: plano não é executado (plan-only)",
                )
                span.set_attribute("neural.hive.journey", journey)
                span.set_attribute("neural.hive.plan_only", True)
                await self.consumer.commit()
                if decision_id:
                    await self._mark_decision_processed(decision_id)
                return

            # Fronteira não-vazada: decide-se "requer geração" pela semântica da
            # jornada (autoridade única partilhada com o resume em main.py), não
            # por conhecer a classe do workflow. Fallback compat: journey
            # ausente/UNKNOWN + workflow_type=generation também é geração.
            by_journey = _journey_requires_generation(journey)
            requires_generation = _requires_generate_capability(journey, workflow_type)

            if requires_generation:
                target = _extract_generate_target(cognitive_plan_json)
                routing_basis = "journey" if by_journey else "workflow_type_fallback"
                span.set_attribute("neural.hive.journey", journey)
                span.set_attribute("neural.hive.routing_basis", routing_basis)
                span.set_attribute("neural.hive.capability", "GENERATE")
                logger.info(
                    "Invocando capacidade GENERATE",
                    workflow_id=workflow_id,
                    plan_id=plan_id,
                    journey=journey,
                    routing_basis=routing_basis,
                    target=f"{target.language}/{target.framework}",
                )
                try:
                    handle = await self.generate_capability.start(
                        GenerateRequest(
                            plan_id=plan_id,
                            journey=journey,
                            cognitive_plan=cognitive_plan_json,
                            target=target,
                        )
                    )
                except UnsupportedStackError as stack_err:
                    # Anti-verde-falso: stack não suportada → NÃO inicia nada; erro
                    # permanente (commit do offset p/ não reprocessar em loop).
                    logger.error(
                        "generate_capability_unsupported_stack",
                        plan_id=plan_id,
                        journey=journey,
                        target=f"{target.language}/{target.framework}",
                        error=str(stack_err),
                    )
                    await self.consumer.commit()
                    if decision_id:
                        await self._mark_decision_processed(decision_id)
                    return
                logger.info(
                    "Capacidade GENERATE iniciada",
                    workflow_id=handle.workflow_id,
                    plan_id=plan_id,
                    journey=handle.journey,
                )
                await self.consumer.commit()
                if decision_id:
                    await self._mark_decision_processed(decision_id)
                logger.info("Mensagem processada com sucesso", offset=message.offset)
                return

            # Fronteira não-vazada MIGRATE (espelha GENERATE): J4_MIGRATE com um
            # migration_config explícito invoca a jornada composta de migração
            # (MigrateJourneyWorkflow durável: GENERATE condicional → MIGRATE via
            # child-workflows), NÃO a OrchestrationWorkflow genérica de J2. A
            # decisão deriva da semântica da jornada (autoridade única
            # _requires_migration). Um plano J4 SEM migration_config não tem o que
            # migrar → cai no roteamento legado (compat); a capacidade só ativa com
            # spec presente.
            if _requires_migration(journey, workflow_type) and "migration_config" in cognitive_plan_json:
                try:
                    # Gate fail-closed na FRONTEIRA (anti-verde-falso): config
                    # presente mas inválido NÃO arranca a jornada. A config
                    # normalizada/validada substitui a do plano antes do start
                    # durável (o workflow deriva os inputs dos child a partir dela).
                    migration_config = _extract_migration_config(cognitive_plan_json)
                except InvalidMigrationConfigError as cfg_err:
                    # Anti-verde-falso: migration_config PRESENTE mas inválido →
                    # NÃO inicia nada e NÃO cai na orquestração genérica; erro
                    # permanente (commit do offset p/ não reprocessar em loop).
                    logger.error(
                        "migration_config_invalid",
                        plan_id=plan_id,
                        journey=journey,
                        error=str(cfg_err),
                    )
                    await self.consumer.commit()
                    if decision_id:
                        await self._mark_decision_processed(decision_id)
                    return

                cognitive_plan_json["migration_config"] = migration_config

                span.set_attribute("neural.hive.journey", journey)
                span.set_attribute("neural.hive.routing_basis", "journey")
                span.set_attribute("neural.hive.capability", "MIGRATE")
                logger.info(
                    "Invocando capacidade MIGRATE",
                    workflow_id=workflow_id,
                    plan_id=plan_id,
                    journey=journey,
                    routing_basis="journey",
                    tables=migration_config["tables"],
                )
                # A jornada composta recebe o cognitive_plan (com migration_config
                # validado e, opcional, generate_target sinalizando geração).
                await self.temporal_client.start_workflow(
                    MigrateJourneyWorkflow.run,
                    cognitive_plan_json,
                    id=workflow_id,
                    task_queue=self.config.temporal_task_queue,
                )
                logger.info(
                    "MigrateJourneyWorkflow iniciado",
                    workflow_id=workflow_id,
                    plan_id=plan_id,
                    journey=journey,
                )
                await self.consumer.commit()
                if decision_id:
                    await self._mark_decision_processed(decision_id)
                logger.info("Mensagem processada com sucesso", offset=message.offset)
                return

            # Caso contrário: orquestração (J2/J4 ou fallback workflow_type=orchestration).
            workflow_class = _select_workflow_class_by_journey(journey)
            routing_basis = "journey"
            if workflow_class is None:
                # Fallback compat: journey ausente/UNKNOWN -> roteamento legado.
                workflow_class = _select_workflow_class(workflow_type)
                routing_basis = "workflow_type_fallback"

            span.set_attribute("neural.hive.journey", journey)
            span.set_attribute("neural.hive.routing_basis", routing_basis)

            logger.info(
                "Iniciando workflow Temporal",
                workflow_id=workflow_id,
                plan_id=plan_id,
                is_direct_plan=is_direct_plan,
                journey=journey,
                routing_basis=routing_basis,
                workflow_type=workflow_type,
                workflow_class=workflow_class.__name__,
            )

            await self.temporal_client.start_workflow(
                workflow_class.run,
                input_data,
                id=workflow_id,
                task_queue=self.config.temporal_task_queue,
            )

            logger.info(
                "Workflow Temporal iniciado com sucesso",
                workflow_id=workflow_id,
                workflow_type=workflow_type,
            )

            # Commit manual do offset
            await self.consumer.commit()

            # Marcar decisão como processada com sucesso (two-phase scheme)
            if decision_id:
                await self._mark_decision_processed(decision_id)

            logger.info("Mensagem processada com sucesso", offset=message.offset)

        except Exception as e:
            logger.error(
                "Erro ao processar mensagem",
                error=str(e),
                decision_id=consolidated_decision.get("decision_id"),
                exc_info=True,
            )
            # Limpar chave de processing para permitir retry (two-phase scheme)
            if decision_id:
                await self._clear_decision_processing(decision_id)
            # Não commitar offset para permitir retry
            raise
