"""MLManagementRouter - API de Gestão de Modelos ML."""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RetrainRequest(BaseModel):
    """Request para POST /retrain."""

    force: bool = Field(
        default=False,
        description="Forçar retreino mesmo sem threshold"
    )
    samples_override: Optional[int] = Field(
        default=None,
        description="Override número de samples"
    )


class PromoteRequest(BaseModel):
    """Request para POST /models/{version}/promote."""

    strategy: str = Field(
        default="immediate",
        description="Estratégia: immediate ou canary"
    )


class MLManagementRouter:
    """
    Router para gestão de modelos ML.

    Fornece endpoints para retreino, versionamento,
    promoção e monitoramento de drift.
    """

    def __init__(
        self,
        mlflow_client: any,
        model_repo: any,
        retraining_job: any,
        drift_detector: any
    ):
        """
        Inicializa o router.

        Args:
            mlflow_client: Cliente MLflow
            model_repo: Repositório de versões
            retraining_job: Job de retreinamento
            drift_detector: Detector de drift
        """
        self.mlflow_client = mlflow_client
        self.model_repo = model_repo
        self.retraining_job = retraining_job
        self.drift_detector = drift_detector
        self.router = APIRouter()

        self._setup_routes()

    def _setup_routes(self):
        """Configura rotas da API."""

        @self.router.post("/retrain", status_code=202)
        async def post_retrain(request: RetrainRequest):
            """
            Forçar retreinamento manual do modelo.

            Retorna 202 Accepted com job_id para acompanhamento.
            """
            try:
                # Executa retreino em background
                import asyncio

                async def run_retrain_bg():
                    return await self.retraining_job.run_retraining(force=request.force)

                # Em produção, usaria background tasks
                # Por ora, executa síncrono para simplificar
                result = await run_retrain_bg()

                return {
                    "job_id": result.get("job_id", "unknown"),
                    "status": "queued" if result.get("success") else "failed",
                    "estimated_samples": request.samples_override or 0
                }

            except Exception as e:
                logger.error(f"Erro ao enfileirar retreino: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.get("/retrain/{job_id}")
        async def get_retrain_status(job_id: str):
            """
            Status do job de retreinamento.

            Retorna detalhes do job incluindo métricas se completado.
            """
            try:
                status = await self.retraining_job.get_job_status(job_id)

                if not status:
                    raise HTTPException(status_code=404, detail="Job not found")

                return status

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Erro ao buscar status: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.get("/models")
        async def list_models(
            stage: Optional[str] = Query(None, description="Filtro por estágio"),
            is_active: Optional[bool] = Query(None, description="Filtro por ativo"),
            limit: int = Query(20, ge=1, le=100),
            offset: int = Query(0, ge=0)
        ):
            """
            Listar versões de modelos registrados.

            Suporta filtros por estágio e status ativo.
            """
            try:
                models = await self.model_repo.list_models(
                    stage=stage,
                    is_active=is_active,
                    limit=limit,
                    offset=offset
                )

                # Conta total (sem paginação)
                total = len(models)  # TODO: implementar count real

                return {
                    "models": models,
                    "total": total,
                    "limit": limit,
                    "offset": offset
                }

            except Exception as e:
                logger.error(f"Erro ao listar modelos: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.get("/models/{version}")
        async def get_model_details(version: str):
            """
            Detalhes de versão específica do modelo.

            Inclui métricas, feature importance e drift metrics.
            """
            try:
                model = await self.model_repo.get_model_version(version)

                if not model:
                    raise HTTPException(status_code=404, detail="Model version not found")

                return model

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Erro ao buscar modelo: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.post("/models/{version}/promote")
        async def promote_model(version: str, request: PromoteRequest):
            """
            Promover modelo para production.

            Suporta estratégias immediate e canary.
            """
            try:
                # Verifica se modelo está em staging
                model = await self.model_repo.get_model_version(version)

                if not model:
                    raise HTTPException(status_code=404, detail="Model not found")

                if model.get("stage") != "staging":
                    raise HTTPException(
                        status_code=400,
                        detail="Only staging models can be promoted"
                    )

                # Promove modelo
                if request.strategy == "immediate":
                    success = await self.model_repo.promote_model(
                        version=version,
                        stage="production",
                        promoted_by="manual"
                    )
                elif request.strategy == "canary":
                    # TODO: Implementar canary deployment
                    success = await self.model_repo.promote_model(
                        version=version,
                        stage="production",
                        promoted_by="canary"
                    )
                else:
                    raise HTTPException(status_code=400, detail="Invalid strategy")

                if not success:
                    raise HTTPException(status_code=500, detail="Promotion failed")

                return {
                    "version": version,
                    "previous_version": model.get("previous_version"),
                    "stage": "production",
                    "promoted_at": model.get("promoted_at"),
                    "strategy": request.strategy
                }

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Erro ao promover modelo: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.get("/drift")
        async def get_drift_metrics(
            window: int = Query(168, ge=1, le=720, description="Janela em horas")
        ):
            """
            Métricas de drift do modelo atual.

            Compara baseline com current para detectar degradation.
            """
            try:
                drift_data = await self.drift_detector.detect_drift(window_hours=window)

                # Adiciona recomendação
                if drift_data.get("drift_detected"):
                    drift_data["recommendation"] = "Consider retraining with latest 100+ samples"

                return drift_data

            except Exception as e:
                logger.error(f"Erro ao buscar drift metrics: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.get("/metrics")
        async def get_prometheus_metrics():
            """
            Métricas em formato Prometheus.

            Endpoint para scraping do Prometheus.
            """
            try:
                active_model = await self.model_repo.get_active_model()

                metrics = []
                if active_model:
                    metrics.append(f'ml_approval_model_version{{version="{active_model["version"]}"}} 1')
                    metrics.append(f'ml_approval_model_f1_score{{version="{active_model["version"]}"}} {active_model.get("f1_score", 0)}')
                    metrics.append(f'ml_approval_model_accuracy{{version="{active_model["version"]}"}} {active_model.get("accuracy", 0)}')

                # Drift detected
                # drift_data = await self.drift_detector.detect_drift()
                # metrics.append(f'ml_approval_drift_detected {1 if drift_data.get("drift_detected") else 0}')

                # Samples available (TODO: implementar contagem real)
                # metrics.append('ml_approval_samples_available 523')

                return "\n".join(metrics), {
                    "media_type": "text/plain",
                    "Content-Type": "text/plain; charset=utf-8"
                }

            except Exception as e:
                logger.error(f"Erro ao gerar métricas: {e}")
                raise HTTPException(status_code=500, detail=str(e))
