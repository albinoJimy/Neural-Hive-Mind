"""
Schemas Avro para ML Inference API com conversão Pydantic <-> Avro.

Este módulo fornece:
1. Definições de schemas Avro compatíveis com Schema Registry
2. Conversão bidirecional entre modelos Pydantic e dicionários Avro
3. Validação de schemas para mensagens Kafka
"""
import io
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import avro.io
    import avro.schema

    AVRO_AVAILABLE = True
except ImportError:
    AVRO_AVAILABLE = False

import structlog

from ..models.schemas import (
    BatchPredictRequest,
    BatchPredictResponse,
    DecisionType,
    PredictOptions,
    PredictRequest,
    PredictResponse,
)

logger = structlog.get_logger()


# ============================================================================
# AVRO SCHEMA DEFINITIONS
# ============================================================================

INFERENCE_REQUEST_AVRO_SCHEMA = {
    "type": "record",
    "name": "InferenceRequest",
    "namespace": "io.neuralhive.inference",
    "doc": "Schema Avro para requests de inferência ML",
    "fields": [
        {
            "name": "request_id",
            "type": "string",
            "doc": "Identificador único do request (UUID)",
        },
        {
            "name": "intent_text",
            "type": ["null", "string"],
            "default": None,
            "doc": "Texto da intenção do usuário",
        },
        {
            "name": "features",
            "type": [
                {
                    "type": "map",
                    "values": "double",
                },
                "null",
            ],
            "default": None,
            "doc": "Features extraídas (map string -> double)",
        },
        {
            "name": "specialist_confidence",
            "type": "double",
            "default": 0.5,
            "doc": "Confiança do especialista (0.0 - 1.0)",
        },
        {
            "name": "specialist_type",
            "type": ["null", "string"],
            "default": None,
            "doc": "Tipo do especialista",
        },
        {
            "name": "model_version",
            "type": ["null", "string"],
            "default": "latest",
            "doc": "Versão do modelo a usar",
        },
        {
            "name": "options",
            "type": [
                {
                    "type": "record",
                    "name": "InferenceOptions",
                    "namespace": "io.neuralhive.inference",
                    "doc": "Opções adicionais de inferência",
                    "fields": [
                        {
                            "name": "explain",
                            "type": "boolean",
                            "default": False,
                            "doc": "Retornar explicação da decisão",
                        },
                        {
                            "name": "include_probabilities",
                            "type": "boolean",
                            "default": True,
                            "doc": "Incluir probabilidades por classe",
                        },
                        {
                            "name": "include_features",
                            "type": "boolean",
                            "default": False,
                            "doc": "Incluir features extraídas",
                        },
                        {
                            "name": "threshold",
                            "type": ["null", "double"],
                            "default": None,
                            "doc": "Threshold customizado para decisão",
                        },
                    ],
                },
                "null",
            ],
            "default": None,
            "doc": "Opções de inferência",
        },
        {
            "name": "timestamp",
            "type": ["null", {"type": "long", "logicalType": "timestamp-millis"}],
            "default": None,
            "doc": "Timestamp do request (milliseconds desde epoch)",
        },
    ],
}

INFERENCE_RESPONSE_AVRO_SCHEMA = {
    "type": "record",
    "name": "InferenceResponse",
    "namespace": "io.neuralhive.inference",
    "doc": "Schema Avro para responses de inferência ML",
    "fields": [
        {
            "name": "request_id",
            "type": "string",
            "doc": "ID do request original",
        },
        {
            "name": "decision",
            "type": {
                "type": "enum",
                "name": "DecisionTypeEnum",
                "symbols": ["approve", "reject", "review_required"],
            },
            "doc": "Decisão do modelo",
        },
        {
            "name": "confidence",
            "type": "double",
            "doc": "Confiança da predição (0.0 - 1.0)",
        },
        {
            "name": "probabilities",
            "type": [
                {
                    "type": "map",
                    "values": "double",
                },
                "null",
            ],
            "default": None,
            "doc": "Probabilidades por classe",
        },
        {
            "name": "features",
            "type": [
                {
                    "type": "map",
                    "values": "double",
                },
                "null",
            ],
            "default": None,
            "doc": "Features usadas na predição",
        },
        {
            "name": "model_version",
            "type": "string",
            "doc": "Versão do modelo usado",
        },
        {
            "name": "inference_time_ms",
            "type": "double",
            "doc": "Tempo de inferência em ms",
        },
        {
            "name": "timestamp",
            "type": {"type": "long", "logicalType": "timestamp-millis"},
            "doc": "Timestamp da resposta (milliseconds desde epoch)",
        },
        {
            "name": "error",
            "type": ["null", "string"],
            "default": None,
            "doc": "Mensagem de erro se a predição falhou",
        },
    ],
}

BATCH_INFERENCE_REQUEST_AVRO_SCHEMA = {
    "type": "record",
    "name": "BatchInferenceRequest",
    "namespace": "io.neuralhive.inference",
    "doc": "Schema Avro para requests de inferência em batch",
    "fields": [
        {
            "name": "batch_id",
            "type": "string",
            "doc": "Identificador único do batch (UUID)",
        },
        {
            "name": "requests",
            "type": {
                "type": "array",
                "items": "InferenceRequest",
            },
            "doc": "Lista de requests de inferência",
        },
        {
            "name": "options",
            "type": [
                {
                    "type": "record",
                    "name": "BatchOptions",
                    "namespace": "io.neuralhive.inference",
                    "doc": "Opções de processamento em batch",
                    "fields": [
                        {
                            "name": "parallel",
                            "type": "boolean",
                            "default": True,
                            "doc": "Processar em paralelo",
                        },
                        {
                            "name": "max_workers",
                            "type": ["null", "int"],
                            "default": None,
                            "doc": "Número máximo de workers",
                        },
                        {
                            "name": "aggregate_results",
                            "type": "boolean",
                            "default": True,
                            "doc": "Agregar estatísticas dos resultados",
                        },
                    ],
                },
                "null",
            ],
            "default": None,
            "doc": "Opções de batch",
        },
        {
            "name": "timestamp",
            "type": {"type": "long", "logicalType": "timestamp-millis"},
            "doc": "Timestamp do batch request",
        },
    ],
}

BATCH_INFERENCE_RESPONSE_AVRO_SCHEMA = {
    "type": "record",
    "name": "BatchInferenceResponse",
    "namespace": "io.neuralhive.inference",
    "doc": "Schema Avro para responses de inferência em batch",
    "fields": [
        {
            "name": "batch_id",
            "type": "string",
            "doc": "ID do batch original",
        },
        {
            "name": "results",
            "type": {
                "type": "array",
                "items": "InferenceResponse",
            },
            "doc": "Resultados individuais",
        },
        {
            "name": "total_processed",
            "type": "int",
            "doc": "Total de itens processados",
        },
        {
            "name": "successful",
            "type": "int",
            "doc": "Número de predições bem-sucedidas",
        },
        {
            "name": "failed",
            "type": "int",
            "doc": "Número de predições falhadas",
        },
        {
            "name": "aggregate_stats",
            "type": [
                {
                    "type": "map",
                    "values": "double",
                },
                "null",
            ],
            "default": None,
            "doc": "Estatísticas agregadas",
        },
        {
            "name": "total_inference_time_ms",
            "type": "double",
            "doc": "Tempo total de inferência em ms",
        },
        {
            "name": "timestamp",
            "type": {"type": "long", "logicalType": "timestamp-millis"},
            "doc": "Timestamp da resposta",
        },
    ],
}


# ============================================================================
# AVRO CODEC CLASS
# ============================================================================


class AvroSchemaRegistry:
    """
    Registry para schemas Avro do ML Inference API.

    Fornece serialização/desserialização compatível com Schema Registry Kafka.
    """

    def __init__(self, schema_dir: Path | None = None):
        """
        Inicializa o registry de schemas Avro.

        Args:
            schema_dir: Diretório para salvar arquivos .avsc (opcional)
        """
        self.schema_dir = schema_dir
        self.schemas: dict[str, dict] = {
            "inference_request": INFERENCE_REQUEST_AVRO_SCHEMA,
            "inference_response": INFERENCE_RESPONSE_AVRO_SCHEMA,
            "batch_request": BATCH_INFERENCE_REQUEST_AVRO_SCHEMA,
            "batch_response": BATCH_INFERENCE_RESPONSE_AVRO_SCHEMA,
        }
        self._parsed_schemas: dict[str, Any] = {}

        if AVRO_AVAILABLE:
            self._parse_schemas()
        else:
            logger.warning("avro_not_available_fallback_to_json")

    def _parse_schemas(self):
        """Parse schemas Avro para uso com avro-python3."""
        if not AVRO_AVAILABLE:
            return

        try:
            for name, schema_dict in self.schemas.items():
                self._parsed_schemas[name] = avro.schema.parse(
                    json.dumps(schema_dict)
                )
                logger.info("avro_schema_parsed", schema_name=name)
        except Exception as e:
            logger.error("avro_schema_parse_failed", error=str(e))

    def get_schema(self, name: str) -> dict:
        """
        Retorna definição de schema.

        Args:
            name: Nome do schema

        Returns:
            Dicionário com definição Avro

        Raises:
            ValueError: Se schema não existir
        """
        if name not in self.schemas:
            raise ValueError(f"Schema '{name}' not found. Available: {list(self.schemas.keys())}")
        return self.schemas[name]

    def get_parsed_schema(self, name: str) -> Any:
        """
        Retorna schema parseado para uso com avro-python3.

        Args:
            name: Nome do schema

        Returns:
            Schema parseado
        """
        if not AVRO_AVAILABLE:
            raise RuntimeError("Avro not available")
        if name not in self._parsed_schemas:
            raise ValueError(f"Schema '{name}' not parsed")
        return self._parsed_schemas[name]

    def serialize(
        self,
        data: dict,
        schema_name: str,
    ) -> bytes:
        """
        Serializa dicionário para bytes Avro.

        Args:
            data: Dicionário com dados
            schema_name: Nome do schema a usar

        Returns:
            Bytes serializados
        """
        if not AVRO_AVAILABLE:
            # Fallback para JSON
            return json.dumps(data).encode("utf-8")

        try:
            schema = self.get_parsed_schema(schema_name)
            writer = avro.io.DatumWriter(schema)
            bytes_writer = io.BytesIO()
            encoder = avro.io.BinaryEncoder(bytes_writer)
            writer.write(data, encoder)
            return bytes_writer.getvalue()
        except Exception as e:
            logger.error(
                "avro_serialization_failed",
                error=str(e),
                schema_name=schema_name,
            )
            # Fallback para JSON
            return json.dumps(data).encode("utf-8")

    def deserialize(
        self,
        data: bytes,
        schema_name: str,
    ) -> dict | None:
        """
        Desserializa bytes Avro para dicionário.

        Args:
            data: Bytes serializados
            schema_name: Nome do schema a usar

        Returns:
            Dicionário desserializado ou None
        """
        # Tentar JSON primeiro (compatibilidade)
        try:
            return json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        if not AVRO_AVAILABLE:
            return None

        try:
            schema = self.get_parsed_schema(schema_name)
            bytes_reader = io.BytesIO(data)
            decoder = avro.io.BinaryDecoder(bytes_reader)
            reader = avro.io.DatumReader(schema)
            return reader.read(decoder)
        except Exception as e:
            logger.error(
                "avro_deserialization_failed",
                error=str(e),
                schema_name=schema_name,
            )
            return None

    def save_schema_files(self):
        """Salva schemas em arquivos .avsc no diretório configurado."""
        if not self.schema_dir:
            logger.info("no_schema_dir_skipped")
            return

        self.schema_dir.mkdir(parents=True, exist_ok=True)

        for name, schema_dict in self.schemas.items():
            schema_path = self.schema_dir / f"{name}.avsc"
            with open(schema_path, "w") as f:
                json.dump(schema_dict, f, indent=2)
            logger.info("avro_schema_saved", path=str(schema_path))

    def validate(self, data: dict, schema_name: str) -> bool:
        """
        Valida dados contra schema Avro.

        Args:
            data: Dicionário a validar
            schema_name: Nome do schema

        Returns:
            True se válido, False caso contrário
        """
        try:
            # Serializar e desserializar para validar
            serialized = self.serialize(data, schema_name)
            deserialized = self.deserialize(serialized, schema_name)
            return deserialized is not None
        except Exception as e:
            logger.warning(
                "avro_validation_failed",
                error=str(e),
                schema_name=schema_name,
            )
            return False


# ============================================================================
# PYDANTIC <-> AVRO CONVERTERS
# ============================================================================


def _datetime_to_millis(dt: datetime | None) -> int | None:
    """Converte datetime para milliseconds desde epoch."""
    if dt is None:
        return None
    return int(dt.timestamp() * 1000)


def _millis_to_datetime(millis: int | None) -> datetime | None:
    """Converte milliseconds desde epoch para datetime."""
    if millis is None:
        return None
    return datetime.fromtimestamp(millis / 1000.0)


def pydantic_to_avro(request: PredictRequest, request_id: str | None = None) -> dict:
    """
    Converte PredictRequest Pydantic para dicionário Avro.

    Args:
        request: Request Pydantic
        request_id: ID do request (gera UUID se None)

    Returns:
        Dicionário compatível com schema Avro
    """
    if request_id is None:
        request_id = str(uuid.uuid4())

    avro_dict: dict[str, Any] = {
        "request_id": request_id,
        "intent_text": request.intent_text,
        "features": None,  # Features são extraídas internamente
        "specialist_confidence": request.specialist_confidence,
        "specialist_type": request.specialist_type,
        "model_version": "latest",  # Default
        "timestamp": _datetime_to_millis(None),
    }

    # Converter options se presente
    if request.options:
        avro_dict["options"] = {
            "explain": False,  # Não suportado ainda
            "include_probabilities": request.options.return_probabilities,
            "include_features": request.options.return_features,
            "threshold": request.options.threshold,
        }

    return avro_dict


def avro_to_pydantic(avro_dict: dict) -> PredictRequest:
    """
    Converte dicionário Avro para PredictRequest Pydantic.

    Args:
        avro_dict: Dicionário Avro

    Returns:
        PredictRequest Pydantic
    """
    options = None
    if avro_dict.get("options"):
        options_data = avro_dict["options"]
        options = PredictOptions(
            return_probabilities=options_data.get("include_probabilities", True),
            return_features=options_data.get("include_features", False),
            threshold=options_data.get("threshold"),
        )

    return PredictRequest(
        intent_text=avro_dict.get("intent_text", ""),
        specialist_confidence=avro_dict.get("specialist_confidence", 0.5),
        specialist_type=avro_dict.get("specialist_type"),
        options=options,
    )


def pydantic_response_to_avro(
    response: PredictResponse,
    request_id: str,
) -> dict:
    """
    Converte PredictResponse Pydantic para dicionário Avro.

    Args:
        response: Response Pydantic
        request_id: ID do request original

    Returns:
        Dicionário compatível com schema Avro
    """
    return {
        "request_id": request_id,
        "decision": response.decision.value if isinstance(response.decision, DecisionType) else response.decision,
        "confidence": response.confidence,
        "probabilities": response.probabilities,
        "features": response.features,
        "model_version": response.model_version,
        "inference_time_ms": response.inference_time_ms,
        "timestamp": _datetime_to_millis(response.timestamp),
        "error": None,
    }


def avro_to_pydantic_response(avro_dict: dict) -> PredictResponse:
    """
    Converte dicionário Avro para PredictResponse Pydantic.

    Args:
        avro_dict: Dicionário Avro

    Returns:
        PredictResponse Pydantic
    """
    decision_str = avro_dict["decision"]
    try:
        decision = DecisionType(decision_str)
    except ValueError:
        decision = DecisionType.REVIEW_REQUIRED

    # Converter timestamp - usa default_factory se None
    ts_millis = avro_dict.get("timestamp")
    ts_value = _millis_to_datetime(ts_millis) if ts_millis else datetime.utcnow()

    return PredictResponse(
        decision=decision,
        confidence=avro_dict["confidence"],
        probabilities=avro_dict.get("probabilities"),
        features=avro_dict.get("features"),
        model_version=avro_dict.get("model_version", "unknown"),
        inference_time_ms=avro_dict.get("inference_time_ms", 0.0),
        timestamp=ts_value,
    )


def batch_pydantic_to_avro(
    request: BatchPredictRequest,
    batch_id: str | None = None,
) -> dict:
    """
    Converte BatchPredictRequest Pydantic para dicionário Avro.

    Args:
        request: Request Pydantic
        batch_id: ID do batch (gera UUID se None)

    Returns:
        Dicionário compatível com schema Avro
    """
    if batch_id is None:
        batch_id = str(uuid.uuid4())

    # Converter cada request individual
    requests_avro = []
    for i, req in enumerate(request.requests):
        req_avro = pydantic_to_avro(req, request_id=f"{batch_id}-{i}")
        requests_avro.append(req_avro)

    avro_dict: dict[str, Any] = {
        "batch_id": batch_id,
        "requests": requests_avro,
        "timestamp": _datetime_to_millis(None),
    }

    # Converter options se presente
    if request.options:
        avro_dict["options"] = {
            "parallel": request.options.parallel,
            "max_workers": request.options.max_workers,
            "aggregate_results": request.options.aggregate_results,
        }

    return avro_dict


def batch_avro_to_pydantic_response(avro_dict: dict) -> BatchPredictResponse:
    """
    Converte dicionário Avro para BatchPredictResponse Pydantic.

    Args:
        avro_dict: Dicionário Avro

    Returns:
        BatchPredictResponse Pydantic
    """
    results = []
    for result_dict in avro_dict.get("results", []):
        result = avro_to_pydantic_response(result_dict)
        results.append(result)

    # Converter timestamp - usa default_factory se None
    ts_millis = avro_dict.get("timestamp")
    ts_value = _millis_to_datetime(ts_millis) if ts_millis else datetime.utcnow()

    return BatchPredictResponse(
        results=results,
        total_processed=avro_dict.get("total_processed", len(results)),
        successful=avro_dict.get("successful", len(results)),
        failed=avro_dict.get("failed", 0),
        aggregate_stats=avro_dict.get("aggregate_stats"),
        total_inference_time_ms=avro_dict.get("total_inference_time_ms", 0.0),
        timestamp=ts_value,
    )


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def create_inference_request(
    intent_text: str,
    specialist_confidence: float = 0.5,
    specialist_type: str | None = None,
    model_version: str = "latest",
    include_probabilities: bool = True,
    request_id: str | None = None,
) -> dict:
    """
    Cria dicionário Avro InferenceRequest com valores padrão.

    Args:
        intent_text: Texto da intenção
        specialist_confidence: Confiança do especialista
        specialist_type: Tipo do especialista
        model_version: Versão do modelo
        include_probabilities: Incluir probabilidades na resposta
        request_id: ID do request (gera UUID se None)

    Returns:
        Dicionário Avro pronto para serialização
    """
    avro_dict = {
        "request_id": request_id or str(uuid.uuid4()),
        "intent_text": intent_text,
        "features": None,
        "specialist_confidence": specialist_confidence,
        "specialist_type": specialist_type,
        "model_version": model_version,
        "options": {
            "explain": False,
            "include_probabilities": include_probabilities,
            "include_features": False,
            "threshold": None,
        },
        "timestamp": _datetime_to_millis(None),
    }
    return avro_dict


def create_inference_response(
    request_id: str,
    decision: str,
    confidence: float,
    model_version: str,
    inference_time_ms: float,
    probabilities: dict[str, float] | None = None,
    features: dict[str, float] | None = None,
    error: str | None = None,
) -> dict:
    """
    Cria dicionário Avro InferenceResponse com valores.

    Args:
        request_id: ID do request original
        decision: Decisão do modelo
        confidence: Confiança da predição
        model_version: Versão do modelo
        inference_time_ms: Tempo de inferência
        probabilities: Probabilidades por classe
        features: Features usadas
        error: Mensagem de erro se aplicável

    Returns:
        Dicionário Avro pronto para serialização
    """
    avro_dict = {
        "request_id": request_id,
        "decision": decision,
        "confidence": confidence,
        "probabilities": probabilities,
        "features": features,
        "model_version": model_version,
        "inference_time_ms": inference_time_ms,
        "timestamp": _datetime_to_millis(None),
        "error": error,
    }
    return avro_dict


# ============================================================================
# VALIDATION DECORATORS
# ============================================================================


def validate_avro_request(schema_name: str = "inference_request"):
    """
    Decorador para validar request Avro em endpoints FastAPI.

    Args:
        schema_name: Nome do schema Avro a usar para validação

    Returns:
        Decorador configurado
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Em implementação real, aqui seria extraído o payload Avro
            # e validado contra o schema
            return await func(*args, **kwargs)

        return wrapper

    return decorator


# Singleton do registry
_schema_registry: AvroSchemaRegistry | None = None


def get_schema_registry() -> AvroSchemaRegistry:
    """Retorna singleton do registry de schemas."""
    global _schema_registry
    if _schema_registry is None:
        _schema_registry = AvroSchemaRegistry()
    return _schema_registry
