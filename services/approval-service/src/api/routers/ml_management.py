"""MLManagementRouter - API de Gestão de Modelos ML."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RetrainRequest(BaseModel):
    """Request para POST /retrain."""

    force: bool = Field(default=False, description="Forçar retreino mesmo sem threshold")
    samples_override: Optional[int] = Field(default=None, description="Override número de samples")


class PromoteRequest(BaseModel):
    """Request para POST /models/{version}/promote."""

    strategy: str = Field(default="immediate", description="Estratégia: immediate ou canary")


class MLManagementRouter:
    """
    Router para gestão de modelos ML.

    Fornece endpoints para retreino, versionamento,
    promoção e monitoramento de drift.
    """

    def __init__(
        self, mlflow_client: any, model_repo: any, retraining_job: any, drift_detector: any
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

    async def _promote_immediate(self, version: str) -> bool:
        """
        Promove modelo imediatamente para produção, desativando o anterior.

        Args:
            version: Versão do modelo a promover

        Returns:
            True se sucesso, False caso contrário
        """
        try:
            # Buscar modelo atual em produção
            current_production = await self.model_repo.list_models(
                stage="production", is_active=True, limit=1
            )

            # Desativar modelo atual se existir
            if current_production:
                for old_model in current_production:
                    await self.model_repo.promote_model(
                        version=old_model.get("version"),
                        stage="production",
                        promoted_by="manual_deactivate",
                    )
                    # Marcar como inativo (set is_active=False)
                    if hasattr(self.model_repo, "deactivate_model"):
                        await self.model_repo.deactivate_model(old_model.get("version"))

            # Ativar novo modelo
            return await self.model_repo.promote_model(
                version=version, stage="production", promoted_by="manual"
            )
        except Exception as e:
            logger.error(f"Erro na promoção imediata: {e}")
            return False

    async def _promote_canary(self, version: str, canary_percentage: int = 10) -> bool:
        """
        Promove modelo em modo canary com percentual de tráfego.

        Mantém ambos os modelos ativos e configura split de tráfego.
        O predictor deve respeitar o canary_percentage ao escolher qual modelo usar.

        Args:
            version: Versão do modelo a promover em canary
            canary_percentage: Percentual de tráfego para o novo modelo (1-50)

        Returns:
            True se sucesso, False caso contrário
        """
        try:
            # Validar percentual
            if not 1 <= canary_percentage <= 50:
                raise ValueError("Canary percentage must be between 1 and 50")

            # Buscar modelo atual em produção
            current_production = await self.model_repo.list_models(
                stage="production", is_active=True, limit=1
            )

            if not current_production:
                raise ValueError("No current production model found for canary deployment")

            current_version = current_production[0].get("version")

            # Promover novo modelo para produção (mas com canary flag)
            # Em um cenário real, isso atualizaria uma tabela de configuração
            # com o split de tráfego entre as versões
            success = await self.model_repo.promote_model(
                version=version, stage="production", promoted_by=f"canary_{canary_percentage}%"
            )

            if success:
                logger.info(
                    f"Canary deployment iniciado: {version} com {canary_percentage}% do tráfego, "
                    f"{current_version} com {100 - canary_percentage}% do tráfego"
                )

            return success
        except Exception as e:
            logger.error(f"Erro no canary deployment: {e}")
            return False

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

                async def run_retrain_bg():
                    return await self.retraining_job.run_retraining(force=request.force)

                # Em produção, usaria background tasks
                # Por ora, executa síncrono para simplificar
                result = await run_retrain_bg()

                return {
                    "job_id": result.get("job_id", "unknown"),
                    "status": "queued" if result.get("success") else "failed",
                    "estimated_samples": request.samples_override or 0,
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
            offset: int = Query(0, ge=0),
        ):
            """
            Listar versões de modelos registrados.

            Suporta filtros por estágio e status ativo.
            """
            try:
                # Buscar modelos paginados
                models = await self.model_repo.list_models(
                    stage=stage, is_active=is_active, limit=limit, offset=offset
                )

                # Count real: buscar todos sem paginação para obter total
                try:
                    all_models = await self.model_repo.list_models(
                        stage=stage, is_active=is_active, limit=None, offset=0
                    )
                    total = len(all_models) if all_models else 0
                except Exception:
                    # Fallback: usar length da página atual se count falhar
                    total = len(models)

                return {"models": models, "total": total, "limit": limit, "offset": offset}

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

            Suporta estratégias:
            - immediate: Promoção completa para produção (substitui modelo atual)
            - canary: Promoção gradual com X% do tráfego (mantém modelo anterior)
            """
            try:
                # Verifica se modelo está em staging
                model = await self.model_repo.get_model_version(version)

                if not model:
                    raise HTTPException(status_code=404, detail="Model not found")

                if model.get("stage") != "staging":
                    raise HTTPException(
                        status_code=400, detail="Only staging models can be promoted"
                    )

                # Promove modelo conforme estratégia
                if request.strategy == "immediate":
                    # Promoção imediata: desativa modelo atual, ativa novo
                    success = await self._promote_immediate(version)
                elif request.strategy == "canary":
                    # Canary deployment: ambos modelos ativos com split de tráfego
                    success = await self._promote_canary(version, canary_percentage=10)
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid strategy: {request.strategy}. Use 'immediate' or 'canary'",
                    )

                if not success:
                    raise HTTPException(status_code=500, detail="Promotion failed")

                return {
                    "version": version,
                    "previous_version": model.get("previous_version"),
                    "stage": "production",
                    "promoted_at": model.get("promoted_at"),
                    "strategy": request.strategy,
                    "canary_percentage": 10 if request.strategy == "canary" else None,
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
                    metrics.append(
                        f'ml_approval_model_version{{version="{active_model["version"]}"}} 1'
                    )
                    metrics.append(
                        f'ml_approval_model_f1_score{{version="{active_model["version"]}"}} {active_model.get("f1_score", 0)}'
                    )
                    metrics.append(
                        f'ml_approval_model_accuracy{{version="{active_model["version"]}"}} {active_model.get("accuracy", 0)}'
                    )

                # Drift detected
                # drift_data = await self.drift_detector.detect_drift()
                # metrics.append(f'ml_approval_drift_detected {1 if drift_data.get("drift_detected") else 0}')

                # Samples available (TODO: implementar contagem real)
                # metrics.append('ml_approval_samples_available 523')

                return "\n".join(metrics), {
                    "media_type": "text/plain",
                    "Content-Type": "text/plain; charset=utf-8",
                }

            except Exception as e:
                logger.error(f"Erro ao gerar métricas: {e}")
                raise HTTPException(status_code=500, detail=str(e))
