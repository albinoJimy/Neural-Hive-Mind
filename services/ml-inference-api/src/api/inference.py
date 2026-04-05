"""
API de inferência ML para predição de aprovação de planos cognitivos.
"""
import time
import uuid
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Request, Response, status, Depends, Header
from slowapi import Limiter
from slowapi.util import get_remote_address
import structlog

from ..config import get_settings
from ..models.schemas import (
    PredictRequest,
    PredictResponse,
    PredictOptions,
    BatchPredictRequest,
    BatchPredictResponse,
    BatchOptions,
    ErrorResponse,
)
from ..services import PredictorService, BatchInferenceEngine, CircuitBreakerOpenError
from ..schemas.avro_schemas import (
    pydantic_to_avro,
    pydantic_response_to_avro,
    batch_pydantic_to_avro,
    batch_avro_to_pydantic_response,
    AvroSchemaRegistry,
)
from ..middleware.avro_middleware import (
    avro_response,
    parse_avro_body,
)


logger = structlog.get_logger()
router = APIRouter()
settings = get_settings()

# Schema registry singleton
_schema_registry: Optional[AvroSchemaRegistry] = None


def get_schema_registry() -> AvroSchemaRegistry:
    """Retorna singleton do schema registry."""
    global _schema_registry
    if _schema_registry is None:
        _schema_registry = AvroSchemaRegistry()
    return _schema_registry


CONTENT_TYPE_AVRO = "application/avro"
CONTENT_TYPE_JSON = "application/json"

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


async def get_predictor(request: Request) -> PredictorService:
    """Dependency para obter predictor service."""
    if not hasattr(request.app.state, "predictor_service"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Predictor service not initialized",
        )
    return request.app.state.predictor_service


async def get_batch_engine(
    request: Request,
    predictor: PredictorService = Depends(get_predictor),
) -> BatchInferenceEngine:
    """Dependency para obter batch engine."""
    if not hasattr(request.app.state, "batch_engine"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Batch engine not initialized",
        )
    return request.app.state.batch_engine


@router.post(
    "/api/v1/inference/predict",
    response_model=PredictResponse,
    status_code=status.HTTP_200_OK,
    summary="Predição individual de aprovação",
    description="Faz predição de aprovação para uma intenção individual",
)
async def predict(
    request_data: PredictRequest,
    request: Request,
    predictor: PredictorService = Depends(get_predictor),
) -> PredictResponse:
    """
    Endpoint de predição individual.

    Args:
        request_data: Dados da predição
        request: Request FastAPI
        predictor: Serviço de predição injetado

    Returns:
        PredictResponse com decisão e confiança

    Raises:
        HTTPException: Em caso de erro
    """
    start_time = time.time()

    try:
        logger.info(
            "prediction_request",
            intent_length=len(request_data.intent_text),
            confidence=request_data.specialist_confidence,
        )

        # Executar predição
        result = await predictor.predict(
            intent_text=request_data.intent_text,
            specialist_confidence=request_data.specialist_confidence,
            specialist_type=request_data.specialist_type,
        )

        inference_time = (time.time() - start_time) * 1000  # ms

        # Aplicar opções
        probabilities = (
            result.get("probabilities")
            if request_data.options and request_data.options.return_probabilities
            else None
        )

        # Aplicar threshold customizado se especificado
        decision = result["decision"]
        if request_data.options and request_data.options.threshold is not None:
            threshold = request_data.options.threshold
            if result["confidence"] < threshold:
                decision = "review_required"

        response = PredictResponse(
            decision=decision,
            confidence=result["confidence"],
            probabilities=probabilities,
            features=None,  # Features não retornadas por padrão
            model_version=result.get("model_version", "unknown"),
            inference_time_ms=inference_time,
        )

        logger.info(
            "prediction_completed",
            decision=decision,
            confidence=result["confidence"],
            inference_time_ms=inference_time,
        )

        return response

    except CircuitBreakerOpenError as e:
        logger.error("circuit_breaker_open", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML inference circuit breaker is open - service temporarily unavailable",
        )

    except ValueError as e:
        logger.warning("validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    except Exception as e:
        logger.error("prediction_failed", error=str(e), error_type=type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prediction failed: {str(e)}",
        )


@router.post(
    "/api/v1/inference/predict-batch",
    response_model=BatchPredictResponse,
    status_code=status.HTTP_200_OK,
    summary="Predição em batch",
    description="Processa múltiplas predições em paralelo",
)
async def predict_batch(
    request_data: BatchPredictRequest,
    request: Request,
    batch_engine: BatchInferenceEngine = Depends(get_batch_engine),
) -> BatchPredictResponse:
    """
    Endpoint de predição em batch.

    Args:
        request_data: Dados do batch
        request: Request FastAPI
        batch_engine: Engine de batch injetado

    Returns:
        BatchPredictResponse com resultados e estatísticas

    Raises:
        HTTPException: Em caso de erro
    """
    try:
        logger.info(
            "batch_prediction_request",
            batch_size=len(request_data.requests),
        )

        # Processar batch
        parallel = request_data.options.parallel if request_data.options else True
        response = await batch_engine.process_batch(
            requests=request_data.requests,
            parallel=parallel,
        )

        logger.info(
            "batch_prediction_completed",
            total=response.total_processed,
            successful=response.successful,
            failed=response.failed,
        )

        return response

    except ValueError as e:
        logger.warning("batch_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    except Exception as e:
        logger.error(
            "batch_prediction_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch prediction failed: {str(e)}",
        )


@router.post(
    "/api/v1/inference/circuit-breaker/reset",
    response_model=dict,
    summary="Reset circuit breaker",
    description="Reseta o circuit breaker manualmente (apenas admin)",
)
async def reset_circuit_breaker(
    request: Request,
    predictor: PredictorService = Depends(get_predictor),
) -> dict:
    """
    Reseta o circuit breaker.

    ATENÇÃO: Este endpoint deve ser protegido em produção.

    Args:
        request: Request FastAPI
        predictor: Serviço de predição injetado

    Returns:
        Status do reset
    """
    # TODO: Adicionar verificação de admin/token
    logger.warning("circuit_breaker_manual_reset")

    predictor.reset_circuit_breaker()

    return {
        "status": "reset",
        "message": "Circuit breaker has been reset to CLOSED state",
    }


# ============================================================================
# AVRO ENDPOINTS
# ============================================================================

@router.post(
    "/api/v1/inference/predict/avro",
    summary="Predição com formato Avro",
    description="""
    Endpoint de predição que aceita e retorna dados em formato Avro binário.

    Content-Type: application/avro
    Accept: application/avro

    Usa schemas Avro definidos em /schemas/ml-inference-request e
    /schemas/ml-inference-response para compatibilidade com Schema Registry.
    """,
)
async def predict_avro(
    request: Request,
    predictor: PredictorService = Depends(get_predictor),
    content_type: str = Header(...),
    accept: str = Header(...),
) -> Response:
    """
    Endpoint de predição com suporte Avro.

    Processa requests em formato Avro e retorna responses também em Avro,
    usando os schemas definidos para compatibilidade com Kafka Schema Registry.

    Args:
        request: Request FastAPI
        predictor: Serviço de predição injetado
        content_type: Content-Type header
        accept: Accept header

    Returns:
        Response com dados Avro ou JSON (fallback)
    """
    start_time = time.time()
    request_id = str(uuid.uuid4())

    try:
        # Parsear body (Avro ou JSON)
        if CONTENT_TYPE_AVRO in content_type:
            body_data = await parse_avro_body(request, "inference_request")
        else:
            # Fallback para JSON
            body_data = await request.json()

        logger.info(
            "avro_prediction_request",
            request_id=request_id,
            has_intent_text="intent_text" in body_data,
            content_type=content_type,
        )

        # Executar predição
        result = await predictor.predict(
            intent_text=body_data.get("intent_text", ""),
            specialist_confidence=body_data.get("specialist_confidence", 0.5),
            specialist_type=body_data.get("specialist_type"),
        )

        inference_time = (time.time() - start_time) * 1000

        # Criar response
        response_data = create_inference_response(
            request_id=request_id,
            decision=result["decision"],
            confidence=result["confidence"],
            model_version=result.get("model_version", "unknown"),
            inference_time_ms=inference_time,
            probabilities=result.get("probabilities"),
        )

        # Retornar no formato solicitado
        return avro_response(
            response_data,
            schema_name="inference_response",
            request=request,
        )

    except CircuitBreakerOpenError as e:
        logger.error("avro_circuit_breaker_open", error=str(e))
        error_data = create_error_response(
            request_id=request_id,
            error="circuit_breaker_open",
            message="ML inference circuit breaker is open",
            detail=str(e),
        )
        return avro_response(error_data, "inference_response", request)

    except ValueError as e:
        logger.warning("avro_validation_error", error=str(e))
        error_data = create_error_response(
            request_id=request_id,
            error="validation_error",
            message=str(e),
        )
        return avro_response(error_data, "inference_response", request)

    except Exception as e:
        logger.error("avro_prediction_failed", error=str(e), error_type=type(e).__name__)
        error_data = create_error_response(
            request_id=request_id,
            error="prediction_failed",
            message=f"Prediction failed: {str(e)}",
        )
        return avro_response(error_data, "inference_response", request)


@router.post(
    "/api/v1/inference/predict-batch/avro",
    summary="Predição em batch com formato Avro",
    description="""
    Endpoint de predição batch que aceita e retorna dados em formato Avro.

    Content-Type: application/avro
    Accept: application/avro
    """,
)
async def predict_batch_avro(
    request: Request,
    batch_engine: BatchInferenceEngine = Depends(get_batch_engine),
    content_type: str = Header(...),
    accept: str = Header(...),
) -> Response:
    """
    Endpoint de predição batch com suporte Avro.

    Args:
        request: Request FastAPI
        batch_engine: Engine de batch injetado
        content_type: Content-Type header
        accept: Accept header

    Returns:
        Response com dados Avro ou JSON (fallback)
    """
    start_time = time.time()
    batch_id = str(uuid.uuid4())

    try:
        # Parsear body
        if CONTENT_TYPE_AVRO in content_type:
            body_data = await parse_avro_body(request, "batch_request")
        else:
            body_data = await request.json()

        requests_list = body_data.get("requests", [])
        options_data = body_data.get("options")

        logger.info(
            "avro_batch_request",
            batch_id=batch_id,
            batch_size=len(requests_list),
        )

        # Processar batch
        response = await batch_engine.process_batch(
            requests=[PredictRequest(**req) for req in requests_list],
            parallel=options_data.get("parallel", True) if options_data else True,
        )

        total_time = (time.time() - start_time) * 1000

        # Criar response Avro
        response_data = create_batch_response(
            batch_id=batch_id,
            response=response,
            total_inference_time_ms=total_time,
        )

        return avro_response(
            response_data,
            schema_name="batch_response",
            request=request,
        )

    except Exception as e:
        logger.error("avro_batch_failed", error=str(e))
        error_data = create_batch_error_response(
            batch_id=batch_id,
            error=str(e),
        )
        return avro_response(error_data, "batch_response", request)


@router.get(
    "/api/v1/inference/schemas",
    summary="Listar schemas Avro disponíveis",
    description="Retorna lista de schemas Avro suportados pelo serviço",
)
async def list_schemas() -> dict:
    """
    Lista schemas Avro disponíveis.

    Returns:
        Dicionário com schemas disponíveis
    """
    registry = get_schema_registry()

    return {
        "schemas": [
            {
                "name": "inference_request",
                "namespace": "io.neuralhive.inference",
                "description": "Schema para requests de inferência individual",
            },
            {
                "name": "inference_response",
                "namespace": "io.neuralhive.inference",
                "description": "Schema para responses de inferência individual",
            },
            {
                "name": "batch_request",
                "namespace": "io.neuralhive.inference",
                "description": "Schema para requests de inferência em batch",
            },
            {
                "name": "batch_response",
                "namespace": "io.neuralhive.inference",
                "description": "Schema para responses de inferência em batch",
            },
        ],
        "format": "avro",
        "version": "1.0",
    }


@router.get(
    "/api/v1/inference/schemas/{schema_name}",
    summary="Obter definição de schema Avro",
    description="Retorna a definição completa do schema Avro em formato JSON",
)
async def get_schema(schema_name: str) -> dict:
    """
    Retorna definição de schema Avro.

    Args:
        schema_name: Nome do schema (inference_request, inference_response, etc.)

    Returns:
        Definição do schema

    Raises:
        HTTPException: Se schema não existir
    """
    registry = get_schema_registry()

    try:
        schema = registry.get_schema(schema_name)
        return schema
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schema '{schema_name}' not found",
        )


@router.get(
    "/api/v1/inference/schemas/{schema_name}.avsc",
    summary="Download de arquivo .avsc",
    description="Retorna o arquivo .avsc para download",
    response_class=Response,
)
async def download_schema(schema_name: str) -> Response:
    """
    Retorna arquivo .avsc para download.

    Args:
        schema_name: Nome do schema

    Returns:
        Response com arquivo .avsc
    """
    import json

    registry = get_schema_registry()

    try:
        schema = registry.get_schema(schema_name)
        schema_json = json.dumps(schema, indent=2)

        return Response(
            content=schema_json,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{schema_name}.avsc"',
            },
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schema '{schema_name}' not found",
        )


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_inference_response(
    request_id: str,
    decision: str,
    confidence: float,
    model_version: str,
    inference_time_ms: float,
    probabilities: Optional[dict] = None,
    features: Optional[dict] = None,
) -> dict:
    """Cria dicionário de response compatível com schema Avro."""
    return {
        "request_id": request_id,
        "decision": decision,
        "confidence": confidence,
        "probabilities": probabilities,
        "features": features,
        "model_version": model_version,
        "inference_time_ms": inference_time_ms,
        "timestamp": None,
        "error": None,
    }


def create_error_response(
    request_id: str,
    error: str,
    message: str,
    detail: Optional[str] = None,
) -> dict:
    """Cria response de erro compatível com schema Avro."""
    return {
        "request_id": request_id,
        "decision": "review_required",
        "confidence": 0.0,
        "probabilities": None,
        "features": None,
        "model_version": "unknown",
        "inference_time_ms": 0.0,
        "timestamp": None,
        "error": f"{error}: {message}",
    }


def create_batch_response(
    batch_id: str,
    response: BatchPredictResponse,
    total_inference_time_ms: float,
) -> dict:
    """Cria dicionário de batch response compatível com schema Avro."""
    # Converter cada PredictResponse para dict
    results = []
    for r in response.results:
        results.append({
            "request_id": f"{batch_id}-{len(results)}",
            "decision": r.decision.value if hasattr(r.decision, 'value') else str(r.decision),
            "confidence": r.confidence,
            "probabilities": r.probabilities,
            "features": r.features,
            "model_version": r.model_version,
            "inference_time_ms": r.inference_time_ms,
            "timestamp": int(r.timestamp.timestamp() * 1000) if r.timestamp else None,
            "error": None,
        })

    return {
        "batch_id": batch_id,
        "results": results,
        "total_processed": response.total_processed,
        "successful": response.successful,
        "failed": response.failed,
        "aggregate_stats": response.aggregate_stats,
        "total_inference_time_ms": total_inference_time_ms,
        "timestamp": int(response.timestamp.timestamp() * 1000) if response.timestamp else None,
    }


def create_batch_error_response(
    batch_id: str,
    error: str,
) -> dict:
    """Cria response de erro batch compatível com schema Avro."""
    return {
        "batch_id": batch_id,
        "results": [],
        "total_processed": 0,
        "successful": 0,
        "failed": 0,
        "aggregate_stats": None,
        "total_inference_time_ms": 0.0,
        "timestamp": None,
    }
