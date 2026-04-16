"""API handlers para inferência ML."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request
from pydantic import ValidationError

from src.models.inference import InferenceRequest, InferenceStatus, ModelType
from src.services.inference_service import InferenceService


async def predict_handler(request: Request) -> dict[str, Any]:
    """Handler para predição ML via REST.

    Args:
        request: Request FastAPI

    Returns:
        Resultado da predição
    """
    inference_service: InferenceService = request.app.state.inference_service

    if not inference_service:
        raise HTTPException(status_code=503, detail="inference_service_not_available")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json")

    # Extrair e validar campos
    request_id = body.get("request_id", str(uuid4()))
    model_name = body.get("model_name", "default_model")
    model_version = body.get("model_version", "latest")
    model_type_str = body.get("model_type", "classification")
    features = body.get("features", {})
    context = body.get("context", {})

    # Converter tipo de modelo
    try:
        model_type = ModelType(model_type_str)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"invalid_model_type: {model_type_str}"
        )

    # Criar requisição de inferência
    try:
        inference_request = InferenceRequest(
            request_id=request_id,
            model_name=model_name,
            model_version=model_version,
            model_type=model_type,
            features=features,
            context=context,
            created_at=datetime.now(timezone.utc),
        )
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Executar predição
    response = await inference_service.predict(inference_request, use_cache=True)

    return {
        "request_id": response.request_id,
        "model_name": response.model_name,
        "model_version": response.model_version,
        "status": response.status.value,
        "prediction": response.prediction,
        "confidence": response.confidence,
        "latency_ms": response.latency_ms,
        "cached": response.cached,
        "error": response.error,
        "processed_at": response.processed_at.isoformat(),
    }


async def batch_predict_handler(request: Request) -> dict[str, Any]:
    """Handler para predição em lote via REST.

    Args:
        request: Request FastAPI

    Returns:
        Resultados das predições em lote
    """
    inference_service: InferenceService = request.app.state.inference_service

    if not inference_service:
        raise HTTPException(status_code=503, detail="inference_service_not_available")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json")

    requests_data = body.get("requests", [])
    if not isinstance(requests_data, list):
        raise HTTPException(status_code=400, detail="requests_must_be_array")

    results = []
    for req_data in requests_data:
        request_id = req_data.get("request_id", str(uuid4()))
        model_name = req_data.get("model_name", "default_model")
        model_version = req_data.get("model_version", "latest")
        model_type_str = req_data.get("model_type", "classification")
        features = req_data.get("features", {})
        context = req_data.get("context", {})

        try:
            model_type = ModelType(model_type_str)
        except ValueError:
            results.append({
                "request_id": request_id,
                "status": "failed",
                "error": f"invalid_model_type: {model_type_str}",
            })
            continue

        inference_request = InferenceRequest(
            request_id=request_id,
            model_name=model_name,
            model_version=model_version,
            model_type=model_type,
            features=features,
            context=context,
            created_at=datetime.now(timezone.utc),
        )

        response = await inference_service.predict(inference_request, use_cache=True)

        results.append({
            "request_id": response.request_id,
            "status": response.status.value,
            "prediction": response.prediction,
            "confidence": response.confidence,
            "cached": response.cached,
            "error": response.error,
        })

    return {
        "total": len(results),
        "results": results,
    }


async def models_list_handler(request: Request) -> dict[str, Any]:
    """Handler para listar modelos disponíveis.

    Args:
        request: Request FastAPI

    Returns:
        Lista de modelos disponíveis
    """
    # Em produção, listaria modelos do registro
    return {
        "models": [
            {
                "name": "classification_model",
                "version": "1.0.0",
                "type": "classification",
            },
            {
                "name": "regression_model",
                "version": "1.0.0",
                "type": "regression",
            },
            {
                "name": "anomaly_detector",
                "version": "1.0.0",
                "type": "anomaly_detection",
            },
        ]
    }


async def cache_stats_handler(request: Request) -> dict[str, Any]:
    """Handler para estatísticas do cache.

    Args:
        request: Request FastAPI

    Returns:
        Estatísticas do cache
    """
    inference_service: InferenceService = request.app.state.inference_service

    if not inference_service:
        raise HTTPException(status_code=503, detail="inference_service_not_available")

    return inference_service.get_cache_stats()


async def cache_clear_handler(request: Request) -> dict[str, str]:
    """Handler para limpar o cache.

    Args:
        request: Request FastAPI

    Returns:
        Status da operação
    """
    inference_service: InferenceService = request.app.state.inference_service

    if not inference_service:
        raise HTTPException(status_code=503, detail="inference_service_not_available")

    inference_service.clear_cache()
    return {"status": "cache_cleared"}
