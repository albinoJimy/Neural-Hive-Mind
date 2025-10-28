import structlog
from fastapi import APIRouter, HTTPException, Request
from typing import List, Optional
from pydantic import BaseModel, Field

logger = structlog.get_logger()

router = APIRouter()


class SimilarityRequest(BaseModel):
    text1: str
    text2: str


class SimilaritySearchRequest(BaseModel):
    query: str
    texts: List[str]
    top_k: int = Field(5, ge=1, le=100)
    threshold: float = Field(0.7, ge=0.0, le=1.0)


class ClusterRequest(BaseModel):
    texts: List[str]
    eps: float = Field(0.5, ge=0.0, le=1.0)
    min_samples: int = Field(2, ge=1)


class DriftDetectionRequest(BaseModel):
    baseline_texts: List[str]
    current_texts: List[str]
    threshold: float = Field(0.3, ge=0.0, le=1.0)


class OutlierRequest(BaseModel):
    texts: List[str]
    threshold_percentile: float = Field(95.0, ge=50.0, le=99.9)


@router.post('/semantics/similarity')
async def calculate_similarity(request: SimilarityRequest, app_request: Request):
    """Calcular similaridade entre dois textos"""
    try:
        app_state = app_request.app.state.app_state
        if not app_state.embedding_service:
            raise HTTPException(status_code=503, detail='Embedding service not initialized')

        similarity = await app_state.embedding_service.calculate_similarity(
            request.text1,
            request.text2
        )

        return {
            'similarity': similarity,
            'text1_length': len(request.text1),
            'text2_length': len(request.text2)
        }

    except Exception as e:
        logger.error('calculate_similarity_failed', error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/semantics/search')
async def search_similar(request: SimilaritySearchRequest, app_request: Request):
    """Buscar textos similares"""
    try:
        app_state = app_request.app.state.app_state
        if not app_state.embedding_service:
            raise HTTPException(status_code=503, detail='Embedding service not initialized')

        # Construir índice
        await app_state.embedding_service.build_index(request.texts)

        # Buscar similares
        results = await app_state.embedding_service.search_similar(
            request.query,
            top_k=request.top_k,
            threshold=request.threshold
        )

        return {
            'query': request.query,
            'results': results,
            'total_searched': len(request.texts),
            'total_found': len(results)
        }

    except Exception as e:
        logger.error('search_similar_failed', error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/semantics/cluster')
async def cluster_texts(request: ClusterRequest, app_request: Request):
    """Agrupar textos similares"""
    try:
        app_state = app_request.app.state.app_state
        if not app_state.embedding_service:
            raise HTTPException(status_code=503, detail='Embedding service not initialized')

        clusters = await app_state.embedding_service.cluster_texts(
            request.texts,
            eps=request.eps,
            min_samples=request.min_samples
        )

        return {
            'clusters': clusters,
            'total_texts': len(request.texts),
            'total_clusters': len([c for c in clusters if not c['is_noise']]),
            'noise_points': sum(c['size'] for c in clusters if c['is_noise'])
        }

    except Exception as e:
        logger.error('cluster_texts_failed', error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/semantics/drift')
async def detect_drift(request: DriftDetectionRequest, app_request: Request):
    """Detectar drift semântico"""
    try:
        app_state = app_request.app.state.app_state
        if not app_state.embedding_service:
            raise HTTPException(status_code=503, detail='Embedding service not initialized')

        result = await app_state.embedding_service.detect_semantic_drift(
            request.baseline_texts,
            request.current_texts,
            threshold=request.threshold
        )

        return result

    except Exception as e:
        logger.error('detect_drift_failed', error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/semantics/outliers')
async def find_outliers(request: OutlierRequest, app_request: Request):
    """Encontrar textos outliers"""
    try:
        app_state = app_request.app.state.app_state
        if not app_state.embedding_service:
            raise HTTPException(status_code=503, detail='Embedding service not initialized')

        outliers = await app_state.embedding_service.find_outliers(
            request.texts,
            threshold_percentile=request.threshold_percentile
        )

        return {
            'outliers': outliers,
            'total_texts': len(request.texts),
            'total_outliers': len(outliers),
            'outlier_percentage': (len(outliers) / len(request.texts) * 100) if request.texts else 0
        }

    except Exception as e:
        logger.error('find_outliers_failed', error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
