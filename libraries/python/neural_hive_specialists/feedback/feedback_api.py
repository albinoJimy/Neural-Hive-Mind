"""
FastAPI router para submissão e consulta de feedback humano.

Este módulo expõe endpoints REST para revisores humanos submeterem feedback
sobre opiniões de especialistas.
"""

from datetime import datetime
from typing import Dict, Any, Optional, List, Callable, TYPE_CHECKING
import structlog

if TYPE_CHECKING:
    from ..metrics import SpecialistMetrics
    from ..compliance.pii_detector import PIIDetector
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field, field_validator
import jwt
import pybreaker

from ..config import SpecialistConfig
from .feedback_collector import FeedbackCollector, FeedbackDocument, FeedbackStoreUnavailable
from ..compliance import AuditLogger

logger = structlog.get_logger()


class SubmitFeedbackRequest(BaseModel):
    """Request body para submissão de feedback."""

    opinion_id: str = Field(
        ...,
        description="ID da opinião sendo avaliada"
    )
    human_rating: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Rating de concordância (0.0-1.0)"
    )
    human_recommendation: str = Field(
        ...,
        description="Recomendação: approve, reject, review_required"
    )
    feedback_notes: str = Field(
        default='',
        description="Notas textuais do revisor"
    )
    submitted_by: Optional[str] = Field(
        default=None,
        description="Identificador do revisor (extraído do JWT se não fornecido)"
    )

    @field_validator('human_recommendation')
    @classmethod
    def validate_recommendation(cls, v):
        """Valida recomendação."""
        valid = ['approve', 'reject', 'review_required']
        if v not in valid:
            raise ValueError(f"human_recommendation deve ser um de {valid}")
        return v


class SubmitFeedbackResponse(BaseModel):
    """Response para submissão de feedback."""

    feedback_id: str = Field(..., description="ID do feedback criado")
    opinion_id: str = Field(..., description="ID da opinião avaliada")
    submitted_at: str = Field(..., description="Timestamp ISO-8601")
    status: str = Field(default='success', description="Status da operação")


class GetFeedbackResponse(BaseModel):
    """Response para consulta de feedbacks."""

    feedbacks: List[FeedbackDocument] = Field(..., description="Lista de feedbacks")
    count: int = Field(..., description="Quantidade de feedbacks")
    statistics: Optional[Dict[str, Any]] = Field(None, description="Estatísticas agregadas")


def verify_jwt_token(
    authorization: Optional[str] = Header(None),
    config: SpecialistConfig = None,
    audit_logger: Optional[AuditLogger] = None,
    request_path: str = '/api/v1/feedback'
) -> Dict[str, Any]:
    """
    Verifica token JWT e extrai payload.

    Args:
        authorization: Header Authorization com Bearer token
        config: Configuração do especialista
        audit_logger: Logger de auditoria (opcional)
        request_path: Path da requisição (opcional)

    Returns:
        Payload do JWT decodificado

    Raises:
        HTTPException 401: Se token inválido ou ausente
        HTTPException 403: Se role não tem permissão
    """
    if not config.feedback_require_authentication:
        # Autenticação desabilitada - retornar payload default
        return {
            'sub': 'anonymous',
            'role': 'human_expert'
        }

    if not authorization or not authorization.startswith('Bearer '):
        # Auditar tentativa de acesso sem token
        if audit_logger:
            audit_logger.log_data_access(
                operation='feedback_auth_denied',
                resource_id='feedback_api',
                details={
                    'reason': 'missing_token',
                    'path': request_path,
                    'status_code': 401
                }
            )
        raise HTTPException(
            status_code=401,
            detail="Token JWT ausente ou inválido"
        )

    token = authorization.replace('Bearer ', '')

    try:
        # Decodificar JWT
        payload = jwt.decode(
            token,
            config.jwt_secret_key,
            algorithms=['HS256']
        )

        # Normalizar e verificar role
        user_role = payload.get('role', '').lower().strip()
        normalized_allowed_roles = [role.lower().strip() for role in config.feedback_allowed_roles]

        if user_role not in normalized_allowed_roles:
            # Auditar tentativa de acesso não autorizado
            user_sub = payload.get('sub', 'unknown')
            logger.warning(
                "Unauthorized role attempted feedback submission",
                user_role=user_role,
                user_sub=user_sub,
                allowed_roles=normalized_allowed_roles
            )
            if audit_logger:
                audit_logger.log_data_access(
                    operation='feedback_auth_denied',
                    resource_id='feedback_api',
                    details={
                        'sub': user_sub,
                        'role': user_role,
                        'reason': 'insufficient_permissions',
                        'path': request_path,
                        'status_code': 403
                    }
                )
            raise HTTPException(
                status_code=403,
                detail=f"Role '{user_role}' não tem permissão para submeter feedback"
            )

        return payload

    except jwt.ExpiredSignatureError:
        # Auditar token expirado
        if audit_logger:
            audit_logger.log_data_access(
                operation='feedback_auth_denied',
                resource_id='feedback_api',
                details={
                    'reason': 'expired_token',
                    'path': request_path,
                    'status_code': 401
                }
            )
        raise HTTPException(
            status_code=401,
            detail="Token JWT expirado"
        )
    except jwt.InvalidTokenError as e:
        # Auditar token inválido
        if audit_logger:
            audit_logger.log_data_access(
                operation='feedback_auth_denied',
                resource_id='feedback_api',
                details={
                    'reason': 'invalid_token',
                    'error': str(e),
                    'path': request_path,
                    'status_code': 401
                }
            )
        raise HTTPException(
            status_code=401,
            detail=f"Token JWT inválido: {str(e)}"
        )


def create_feedback_router(
    feedback_collector: FeedbackCollector,
    config: SpecialistConfig,
    metrics: 'SpecialistMetrics' = None,
    pii_detector: 'PIIDetector' = None,
    audit_logger: Optional[AuditLogger] = None
) -> APIRouter:
    """
    Cria router FastAPI com endpoints de feedback.

    Args:
        feedback_collector: Instância do FeedbackCollector
        config: Configuração do especialista
        metrics: Instância de SpecialistMetrics (opcional)
        pii_detector: Instância de PIIDetector para anonimização (opcional)
        audit_logger: Instância de AuditLogger para auditoria (opcional)

    Returns:
        APIRouter configurado
    """
    router = APIRouter()

    @router.post(
        '/feedback',
        response_model=SubmitFeedbackResponse,
        status_code=201,
        summary="Submeter feedback sobre opinião",
        description="Permite revisores humanos submeterem feedback sobre opiniões de especialistas"
    )
    async def submit_feedback(
        request: SubmitFeedbackRequest,
        authorization: Optional[str] = Header(None)
    ):
        """
        Submete feedback humano sobre uma opinião.

        Args:
            request: Dados do feedback
            authorization: Header Authorization com Bearer token

        Returns:
            SubmitFeedbackResponse com feedback_id criado

        Raises:
            HTTPException 400: Validação falhou
            HTTPException 401: Não autenticado
            HTTPException 403: Sem permissão
            HTTPException 404: Opinião não encontrada
            HTTPException 503: Serviço indisponível
        """
        try:
            # Verificar autenticação
            payload = verify_jwt_token(authorization, config, audit_logger, '/api/v1/feedback')

            # Buscar metadados da opinião usando método público
            try:
                opinion_metadata = feedback_collector.get_opinion_metadata(request.opinion_id)
            except ValueError as e:
                if 'não encontrada' in str(e) or 'not found' in str(e).lower():
                    raise HTTPException(
                        status_code=404,
                        detail=str(e)
                    )
                raise

            # Anonimizar feedback_notes se PII detector disponível
            feedback_notes = request.feedback_notes
            pii_metadata = {}

            if pii_detector and pii_detector.enabled and feedback_notes:
                try:
                    anonymized_notes, pii_entities = pii_detector.anonymize_text(
                        text=feedback_notes,
                        language='pt'  # Pode ser parametrizado
                    )

                    if pii_entities:
                        feedback_notes = anonymized_notes
                        pii_metadata = {
                            'pii_detected': True,
                            'pii_entities_count': len(pii_entities),
                            'pii_entity_types': list(set(e['entity_type'] for e in pii_entities))
                        }

                        logger.info(
                            "PII detected and anonymized in feedback notes",
                            opinion_id=request.opinion_id,
                            entities_count=len(pii_entities),
                            entity_types=pii_metadata['pii_entity_types']
                        )

                        # Emitir métricas de compliance
                        if metrics:
                            for entity in pii_entities:
                                metrics.increment_pii_entities_detected(entity['entity_type'])
                            metrics.increment_pii_anonymization(config.pii_anonymization_strategy)
                    else:
                        pii_metadata = {'pii_detected': False}

                except Exception as e:
                    logger.warning(
                        "Error during PII detection/anonymization - using original text",
                        error=str(e),
                        opinion_id=request.opinion_id
                    )
                    if metrics:
                        metrics.increment_pii_detection_error('anonymization_failed')
                    # Continuar com texto original em caso de erro

            # Preparar dados completos do feedback
            feedback_data = {
                'opinion_id': request.opinion_id,
                'plan_id': opinion_metadata['plan_id'],
                'specialist_type': opinion_metadata['specialist_type'],
                'human_rating': request.human_rating,
                'human_recommendation': request.human_recommendation,
                'feedback_notes': feedback_notes,
                'submitted_by': request.submitted_by or payload.get('sub', 'unknown'),
                'metadata': pii_metadata if pii_metadata else {}
            }

            # Submeter feedback
            feedback_id = feedback_collector.submit_feedback(feedback_data)

            # Emitir métricas
            if metrics:
                role = payload.get('role', 'unknown')
                metrics.increment_feedback_submission(submitted_by_role=role)
                metrics.observe_feedback_rating(request.human_rating)
                metrics.increment_feedback_recommendation(request.human_recommendation)

            logger.info(
                "Feedback submitted via API",
                feedback_id=feedback_id,
                opinion_id=request.opinion_id,
                submitted_by=feedback_data['submitted_by'],
                rating=request.human_rating
            )

            return SubmitFeedbackResponse(
                feedback_id=feedback_id,
                opinion_id=request.opinion_id,
                submitted_at=datetime.utcnow().isoformat(),
                status='success'
            )

        except HTTPException:
            raise
        except ValueError as e:
            error_msg = str(e)
            # Mapear ValueError de "opinião não encontrada" para 404
            if 'não encontrada' in error_msg or 'not found' in error_msg.lower():
                if metrics:
                    metrics.increment_feedback_api_error('not_found')
                raise HTTPException(status_code=404, detail=error_msg)
            # Outras validações resultam em 400
            if metrics:
                metrics.increment_feedback_api_error('validation')
            raise HTTPException(status_code=400, detail=error_msg)
        except pybreaker.CircuitBreakerError as e:
            logger.error(
                "Circuit breaker open - service unavailable",
                error=str(e),
                opinion_id=request.opinion_id
            )
            if metrics:
                metrics.increment_feedback_api_error('service_unavailable')
            raise HTTPException(
                status_code=503,
                detail="Serviço de feedback temporariamente indisponível. Tente novamente mais tarde."
            )
        except Exception as e:
            logger.error(
                "Error submitting feedback",
                error=str(e),
                opinion_id=request.opinion_id
            )
            if metrics:
                metrics.increment_feedback_api_error('internal_error')
            raise HTTPException(
                status_code=503,
                detail=f"Erro ao submeter feedback: {str(e)}"
            )

    @router.get(
        '/feedback/opinion/{opinion_id}',
        response_model=GetFeedbackResponse,
        summary="Buscar feedbacks de uma opinião",
        description="Retorna todos os feedbacks submetidos para uma opinião específica"
    )
    async def get_feedback_by_opinion(
        opinion_id: str,
        authorization: Optional[str] = Header(None)
    ):
        """
        Busca feedbacks de uma opinião.

        Args:
            opinion_id: ID da opinião
            authorization: Header Authorization com Bearer token

        Returns:
            GetFeedbackResponse com lista de feedbacks
        """
        try:
            # Verificar autenticação
            verify_jwt_token(authorization, config, audit_logger, f'/api/v1/feedback/opinion/{opinion_id}')

            # Buscar feedbacks
            feedbacks = feedback_collector.get_feedback_by_opinion(opinion_id)

            return GetFeedbackResponse(
                feedbacks=feedbacks,
                count=len(feedbacks),
                statistics=None
            )

        except HTTPException:
            raise
        except FeedbackStoreUnavailable as e:
            logger.error(
                "Feedback store unavailable - cannot retrieve feedbacks",
                opinion_id=opinion_id,
                error=str(e)
            )
            if metrics:
                metrics.increment_feedback_api_error('store_unavailable')
            raise HTTPException(
                status_code=503,
                detail="Serviço de feedback temporariamente indisponível. Tente novamente mais tarde."
            )
        except Exception as e:
            logger.error(
                "Unexpected error retrieving feedbacks",
                opinion_id=opinion_id,
                error=str(e)
            )
            if metrics:
                metrics.increment_feedback_api_error('internal_error')
            raise HTTPException(
                status_code=503,
                detail=f"Erro ao buscar feedbacks: {str(e)}"
            )

    @router.get(
        '/feedback/stats',
        summary="Estatísticas de feedback",
        description="Retorna estatísticas agregadas de feedback para um especialista"
    )
    async def get_feedback_stats(
        specialist_type: str,
        window_days: int = 30,
        authorization: Optional[str] = Header(None)
    ):
        """
        Calcula estatísticas de feedback.

        Args:
            specialist_type: Tipo do especialista
            window_days: Janela de tempo em dias (default: 30)
            authorization: Header Authorization com Bearer token

        Returns:
            Dict com estatísticas
        """
        try:
            # Verificar autenticação
            verify_jwt_token(authorization, config, audit_logger, '/api/v1/feedback/stats')

            # Calcular estatísticas
            stats = feedback_collector.get_feedback_statistics(
                specialist_type=specialist_type,
                window_days=window_days
            )

            # Emitir métricas
            if metrics:
                metrics.set_feedback_count_current(stats.get('count', 0))
                metrics.set_feedback_avg_rating(stats.get('avg_rating', 0.0))

            return stats

        except HTTPException:
            raise
        except FeedbackStoreUnavailable as e:
            logger.error(
                "Feedback store unavailable - cannot calculate statistics",
                specialist_type=specialist_type,
                error=str(e)
            )
            if metrics:
                metrics.increment_feedback_api_error('store_unavailable')
            raise HTTPException(
                status_code=503,
                detail="Serviço de feedback temporariamente indisponível. Tente novamente mais tarde."
            )
        except Exception as e:
            logger.error(
                "Unexpected error calculating feedback statistics",
                specialist_type=specialist_type,
                error=str(e)
            )
            if metrics:
                metrics.increment_feedback_api_error('internal_error')
            raise HTTPException(
                status_code=503,
                detail=f"Erro ao calcular estatísticas: {str(e)}"
            )

    @router.post(
        '/feedback/trigger-online-update',
        summary="Disparar atualização de modelo online",
        description="Dispara atualização incremental do modelo online com feedbacks recentes"
    )
    async def trigger_online_update(
        specialist_type: str,
        force: bool = False,
        authorization: Optional[str] = Header(None)
    ):
        """
        Dispara atualização de modelo online.

        Este endpoint permite disparar manualmente uma atualização incremental
        do modelo online usando feedbacks coletados recentemente.

        Args:
            specialist_type: Tipo do especialista
            force: Forçar update ignorando cooldown
            authorization: Header Authorization com Bearer token

        Returns:
            Dict com status da atualização
        """
        try:
            # Verificar autenticação (requer role admin)
            payload = verify_jwt_token(authorization, config, audit_logger, '/api/v1/feedback/trigger-online-update')
            user_role = payload.get('role', '').lower()

            if user_role not in ['admin', 'ml_engineer']:
                raise HTTPException(
                    status_code=403,
                    detail="Apenas admin ou ml_engineer podem disparar atualizações online"
                )

            # Tentar importar e executar o orchestrator
            try:
                from ml_pipelines.online_learning import OnlineDeploymentOrchestrator, OnlineLearningConfig
                import asyncio

                ol_config = OnlineLearningConfig()

                if not ol_config.online_learning_enabled:
                    return {
                        'status': 'disabled',
                        'message': 'Online learning está desabilitado',
                        'specialist_type': specialist_type
                    }

                logger.info(
                    "online_update_triggered",
                    specialist_type=specialist_type,
                    force=force,
                    triggered_by=payload.get('sub', 'unknown')
                )

                # Carregar modelo batch do MLflow ou usar stub
                batch_model = _load_batch_model_for_update(specialist_type, ol_config)

                # Criar orchestrator com assinaturas corretas
                orchestrator = OnlineDeploymentOrchestrator(
                    config=ol_config,
                    specialist_type=specialist_type,
                    batch_model=batch_model,
                    feedback_collector=feedback_collector,
                    feature_extractor=_get_feature_extractor_for_update(specialist_type)
                )

                # Executar ciclo de deployment de forma assíncrona
                try:
                    # Criar loop se necessário ou usar existente
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                    # Executar deployment cycle
                    result = loop.run_until_complete(
                        orchestrator.run_deployment_cycle(
                            force=force,
                            validation_data=None
                        )
                    )

                    orchestrator.close()

                    return {
                        'status': result.get('status', 'unknown'),
                        'message': f"Atualização online executada para {specialist_type}",
                        'specialist_type': specialist_type,
                        'force': force,
                        'triggered_by': payload.get('sub', 'unknown'),
                        'deployment_id': result.get('deployment_id'),
                        'model_version': result.get('model_version'),
                        'duration_seconds': result.get('duration_seconds'),
                        'reason': result.get('reason')
                    }

                except Exception as e:
                    orchestrator.close()
                    logger.error(
                        "online_update_execution_failed",
                        specialist_type=specialist_type,
                        error=str(e)
                    )
                    raise HTTPException(
                        status_code=500,
                        detail=f"Falha ao executar atualização online: {str(e)}"
                    )

            except ImportError:
                logger.warning(
                    "online_learning_module_not_available",
                    specialist_type=specialist_type
                )
                return {
                    'status': 'unavailable',
                    'message': 'Módulo de online learning não está disponível',
                    'specialist_type': specialist_type
                }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                "trigger_online_update_failed",
                specialist_type=specialist_type,
                error=str(e)
            )
            if metrics:
                metrics.increment_feedback_api_error('online_update_failed')
            raise HTTPException(
                status_code=503,
                detail=f"Erro ao disparar atualização online: {str(e)}"
            )

    @router.get(
        '/feedback/health',
        summary="Health check for feedback API",
        description="Verifica se o feedback API está operacional"
    )
    async def feedback_health_check():
        """
        Health check específico para feedback API.

        Verifica:
        - FeedbackCollector está inicializado
        - MongoDB está acessível
        - Circuit breaker não está aberto

        Returns:
            Dict com status de saúde
        """
        try:
            # Verificar se feedback collector está funcional
            if not feedback_collector:
                return {
                    "status": "unhealthy",
                    "reason": "feedback_collector_not_initialized"
                }

            # Verificar conexão MongoDB (quick check)
            try:
                # Tentar contar documentos (operação leve)
                count = feedback_collector.count_recent_feedback(
                    specialist_type=config.specialist_type,
                    window_days=1
                )

                return {
                    "status": "healthy",
                    "specialist_type": config.specialist_type,
                    "mongodb_connected": True,
                    "recent_feedback_count": count
                }
            except FeedbackStoreUnavailable:
                return {
                    "status": "degraded",
                    "reason": "mongodb_unavailable",
                    "specialist_type": config.specialist_type
                }

        except Exception as e:
            logger.error("Feedback health check failed", error=str(e))
            return {
                "status": "unhealthy",
                "reason": str(e),
                "specialist_type": config.specialist_type
            }

    return router


# ============================================================================
# Funções auxiliares para trigger de online update
# ============================================================================

def _load_batch_model_for_update(specialist_type: str, config: Any) -> Any:
    """
    Carrega modelo batch do MLflow ou retorna stub para trigger de update.

    Args:
        specialist_type: Tipo do especialista
        config: Configuração de online learning

    Returns:
        Modelo batch ou stub se não disponível
    """
    try:
        import mlflow
        from mlflow.tracking import MlflowClient

        mlflow.set_tracking_uri(config.mlflow_tracking_uri)
        model_name = f"{specialist_type}_specialist"

        try:
            model_uri = f"models:/{model_name}/Production"
            model = mlflow.pyfunc.load_model(model_uri)
            logger.info(
                "batch_model_loaded_for_update",
                specialist_type=specialist_type,
                model_name=model_name
            )
            return model
        except Exception as e:
            logger.warning(
                "mlflow_model_not_found_for_update",
                specialist_type=specialist_type,
                error=str(e)
            )
    except ImportError:
        logger.warning("mlflow_not_available_for_update")
    except Exception as e:
        logger.warning(
            "batch_model_load_failed_for_update",
            specialist_type=specialist_type,
            error=str(e)
        )

    # Retornar stub com interface mínima
    return _BatchModelStubForUpdate(specialist_type)


class _BatchModelStubForUpdate:
    """Stub para modelo batch quando MLflow não disponível no trigger."""

    def __init__(self, specialist_type: str):
        self.specialist_type = specialist_type

    def predict_proba(self, X):
        """Retorna probabilidades uniformes para stub."""
        import numpy as np
        n_samples = len(X) if hasattr(X, '__len__') else 1
        return np.ones((n_samples, 3)) / 3.0

    def predict(self, X):
        """Retorna predição default para stub."""
        import numpy as np
        n_samples = len(X) if hasattr(X, '__len__') else 1
        return np.array(['review_required'] * n_samples)


def _get_feature_extractor_for_update(specialist_type: str) -> Optional[callable]:
    """
    Obtém função de extração de features para trigger de update.

    Args:
        specialist_type: Tipo do especialista

    Returns:
        Função de extração ou None
    """
    try:
        from ..feature_extraction import FeatureExtractor

        extractor = FeatureExtractor()

        def extract_features(feedback: dict) -> list:
            """Extrai features de um feedback."""
            plan_data = feedback.get('cognitive_plan_snapshot', {})
            if not plan_data:
                import numpy as np
                return np.zeros(64).tolist()

            features = extractor.extract_features(plan_data)
            return features.get('aggregated_features', [])

        return extract_features

    except ImportError:
        logger.warning(
            "feature_extractor_not_available_for_update",
            specialist_type=specialist_type
        )
        return None
    except Exception as e:
        logger.warning(
            "feature_extractor_init_failed_for_update",
            specialist_type=specialist_type,
            error=str(e)
        )
        return None
