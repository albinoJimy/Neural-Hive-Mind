import asyncio
from datetime import datetime, timezone
from typing import Any
from structlog import get_logger

from src.models.pipeline import PipelineRun, RollbackRequest
from src.models.schemas import PipelineStatus, PipelineStage
from src.orchestrators.stages import (
    BaseStage,
    PreFlightStage,
    BuildStage,
    TestStage,
    SecurityStage,
    StagingStage,
    ApprovalStage,
    ProductionStage,
    StageResult,
)


class OrchestratorConfig:
    """Configuração para orquestração de pipelines."""

    def __init__(
        self,
        timeout_minutes: int = 60,
        max_retries: int = 3,
        enable_auto_rollback: bool = True,
        rollback_on_health_check: bool = True,
        rollback_on_metrics_degradation: bool = True,
    ):
        self.timeout_minutes = timeout_minutes
        self.max_retries = max_retries
        self.enable_auto_rollback = enable_auto_rollback
        self.rollback_on_health_check = rollback_on_health_check
        self.rollback_on_metrics_degradation = rollback_on_metrics_degradation


class PipelineOrchestrator:
    """Orquestra a execução de pipelines CI/CD."""

    def __init__(self, config: OrchestratorConfig | None = None):
        self.config = config or OrchestratorConfig()
        self.logger = get_logger()
        self.stages: dict[PipelineStage, BaseStage] = {
            PipelineStage.PRE_FLIGHT: PreFlightStage(),
            PipelineStage.BUILD: BuildStage(),
            PipelineStage.TEST: TestStage(),
            PipelineStage.SECURITY: SecurityStage(),
            PipelineStage.STAGING: StagingStage(),
            PipelineStage.APPROVAL: ApprovalStage(),
            PipelineStage.PRODUCTION: ProductionStage(),
        }

    async def execute(self, run: PipelineRun, context: dict) -> PipelineRun:
        """Executa o pipeline run através de todos os estágios."""
        self.logger.info("pipeline_execution_starting", run_id=run.run_id)

        run.status = PipelineStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)

        try:
            # Define stage sequence based on environment
            stage_sequence = self._get_stage_sequence(
                context.get("environment", "staging")
            )

            for stage in stage_sequence:
                if not await self._execute_stage(run, stage, context):
                    # Stage failed - stop execution
                    run.status = PipelineStatus.FAILED
                    run.finished_at = datetime.now(timezone.utc)
                    self.logger.error("pipeline_failed", run_id=run.run_id, stage=stage)
                    return run

            # All stages completed successfully
            run.status = PipelineStatus.SUCCESS
            run.finished_at = datetime.now(timezone.utc)
            run.duration_seconds = int(
                (run.finished_at - run.started_at).total_seconds()
            )

            self.logger.info("pipeline_completed_successfully", run_id=run.run_id)
            return run

        except Exception as e:
            self.logger.error("pipeline_error", run_id=run.run_id, error=str(e))
            run.status = PipelineStatus.FAILED
            run.finished_at = datetime.now(timezone.utc)
            return run

    async def _execute_stage(
        self, run: PipelineRun, stage: PipelineStage, context: dict
    ) -> bool:
        """Executa um único estágio com lógica de retry."""
        run.current_stage = stage

        executor = self.stages.get(stage)
        if not executor:
            self.logger.warning("stage_not_found", stage=stage)
            return True  # Skip unknown stages

        for attempt in range(self.config.max_retries):
            try:
                result = await asyncio.wait_for(
                    executor.execute(run, context),
                    timeout=self.config.timeout_minutes * 60,
                )

                if result.success:
                    run.stages_completed.append(stage)
                    self.logger.info(
                        "stage_completed",
                        run_id=run.run_id,
                        stage=stage,
                        duration=result.duration_seconds,
                    )
                    return True
                else:
                    run.stages_failed.append(stage)
                    self.logger.error(
                        "stage_failed",
                        run_id=run.run_id,
                        stage=stage,
                        message=result.message,
                    )
                    return False  # Don't retry on failure

            except asyncio.TimeoutError:
                self.logger.warning(
                    "stage_timeout",
                    run_id=run.run_id,
                    stage=stage,
                    attempt=attempt + 1,
                )
                if attempt == self.config.max_retries - 1:
                    run.stages_failed.append(stage)
                    return False

            except Exception as e:
                self.logger.error(
                    "stage_error",
                    run_id=run.run_id,
                    stage=stage,
                    error=str(e),
                )
                if attempt == self.config.max_retries - 1:
                    run.stages_failed.append(stage)
                    return False

        return False

    def _get_stage_sequence(self, environment: str) -> list[PipelineStage]:
        """Retorna a sequência de estágios para um ambiente."""
        base_stages = [
            PipelineStage.PRE_FLIGHT,
            PipelineStage.BUILD,
            PipelineStage.TEST,
            PipelineStage.SECURITY,
        ]

        if environment == "staging":
            return base_stages + [PipelineStage.STAGING]

        if environment == "production":
            return base_stages + [
                PipelineStage.STAGING,
                PipelineStage.APPROVAL,
                PipelineStage.PRODUCTION,
            ]

        return base_stages

    async def rollback(self, request: RollbackRequest, context: dict) -> PipelineRun:
        """Executa um rollback para um deploy falhado."""
        self.logger.info(
            "rollback_initiated", run_id=request.run_id, reason=request.reason
        )

        run = context.get("run")
        if not run:
            raise ValueError(f"Run {request.run_id} not found")

        # Execute rollback logic (this would integrate with GitOps provider)
        run.status = PipelineStatus.ROLLED_BACK
        run.rollback_reason = request.reason
        run.finished_at = datetime.now(timezone.utc)

        self.logger.info("rollback_completed", run_id=request.run_id)
        return run

    async def check_health(self, run: PipelineRun) -> bool:
        """Verifica se a aplicação deployada está saudável."""
        self.logger.info("health_check", run_id=run.run_id)

        # This would integrate with actual health check endpoints
        # For now, simulate a successful check
        await asyncio.sleep(2)

        return True

    async def should_rollback(self, run: PipelineRun) -> tuple[bool, str]:
        """Determina se um rollback deve ser iniciado."""
        reasons = []

        if self.config.rollback_on_health_check:
            healthy = await self.check_health(run)
            if not healthy:
                reasons.append("Health check failed")

        if self.config.rollback_on_metrics_degradation:
            degraded = await self._check_metrics_degradation(run)
            if degraded:
                reasons.append("Metrics degraded")

        return len(reasons) > 0, "; ".join(reasons)

    async def _check_metrics_degradation(self, run: PipelineRun) -> bool:
        """Verifica se métricas degradaram após o deploy."""
        # This would query Prometheus for actual metrics
        # For now, return False (no degradation)
        return False
