from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict
from structlog import get_logger

from src.models.pipeline import PipelineRun
from src.models.schemas import PipelineStage


class StageResult(BaseModel):
    """Resultado da execução de um estágio."""

    model_config = ConfigDict(extra="forbid")

    stage: PipelineStage
    success: bool
    message: str
    duration_seconds: int
    metadata: dict[str, Any] = {}


class BaseStage(ABC):
    """Classe base para todos os estágios do pipeline."""

    def __init__(self, timeout_seconds: int = 3600):
        self.timeout_seconds = timeout_seconds
        self.logger = get_logger()

    @abstractmethod
    async def execute(self, run: PipelineRun, context: dict) -> StageResult:
        """Executa a lógica do estágio."""

    @abstractmethod
    def get_name(self) -> PipelineStage:
        """Retorna o valor do enum do estágio."""


class PreFlightStage(BaseStage):
    """Valida pré-requisitos antes de executar o pipeline."""

    def get_name(self) -> PipelineStage:
        return PipelineStage.PRE_FLIGHT

    async def execute(self, run: PipelineRun, context: dict) -> StageResult:
        self.logger.info("preflight_stage_starting", run_id=run.run_id)

        checks = context.get("preflight_checks", {})

        # Validate required secrets
        if not checks.get("has_secrets", True):
            return StageResult(
                stage=self.get_name(),
                success=False,
                message="Required secrets not configured",
                duration_seconds=0,
            )

        # Validate version format
        version = checks.get("version", "")
        if not version or not version.replace(".", "").isdigit():
            return StageResult(
                stage=self.get_name(),
                success=False,
                message=f"Invalid version format: {version}",
                duration_seconds=0,
            )

        self.logger.info("preflight_stage_complete", run_id=run.run_id)
        return StageResult(
            stage=self.get_name(),
            success=True,
            message="Pre-flight checks passed",
            duration_seconds=0,
        )


class BuildStage(BaseStage):
    """Constrói imagens de container e gera SBOM."""

    def get_name(self) -> PipelineStage:
        return PipelineStage.BUILD

    async def execute(self, run: PipelineRun, context: dict) -> StageResult:
        self.logger.info("build_stage_starting", run_id=run.run_id)

        # This would delegate to the actual CI platform (GitHub Actions, etc.)
        # For now, we simulate the result
        build_info = context.get("build_info", {})

        self.logger.info("build_stage_complete", run_id=run.run_id)
        return StageResult(
            stage=self.get_name(),
            success=True,
            message=f'Built image {build_info.get("image", "unknown")}',
            duration_seconds=build_info.get("duration", 120),
            metadata={
                "image": build_info.get("image", ""),
                "digest": build_info.get("digest", ""),
            },
        )


class TestStage(BaseStage):
    """Executa testes unitários e de integração."""

    def get_name(self) -> PipelineStage:
        return PipelineStage.TEST

    async def execute(self, run: PipelineRun, context: dict) -> StageResult:
        self.logger.info("test_stage_starting", run_id=run.run_id)

        test_results = context.get("test_results", {})

        success = test_results.get("passed", 0) == test_results.get("total", 0)
        message = f'{test_results.get("passed", 0)}/{test_results.get("total", 0)} tests passed'

        self.logger.info("test_stage_complete", run_id=run.run_id, success=success)
        return StageResult(
            stage=self.get_name(),
            success=success,
            message=message,
            duration_seconds=test_results.get("duration", 60),
            metadata=test_results,
        )


class SecurityStage(BaseStage):
    """Executa scans de segurança (SAST, SCA, container scanning)."""

    def get_name(self) -> PipelineStage:
        return PipelineStage.SECURITY

    async def execute(self, run: PipelineRun, context: dict) -> StageResult:
        self.logger.info("security_stage_starting", run_id=run.run_id)

        scan_results = context.get("security_scan", {})

        critical_vulns = scan_results.get("critical", 0)
        high_vulns = scan_results.get("high", 0)

        success = critical_vulns == 0
        message = f"Found {critical_vulns} critical, {high_vulns} high vulnerabilities"

        self.logger.info("security_stage_complete", run_id=run.run_id, success=success)
        return StageResult(
            stage=self.get_name(),
            success=success,
            message=message,
            duration_seconds=scan_results.get("duration", 30),
            metadata=scan_results,
        )


class StagingStage(BaseStage):
    """Deploy para ambiente de staging."""

    def get_name(self) -> PipelineStage:
        return PipelineStage.STAGING

    async def execute(self, run: PipelineRun, context: dict) -> StageResult:
        self.logger.info("staging_stage_starting", run_id=run.run_id)

        deploy_info = context.get("staging_deploy", {})

        self.logger.info("staging_stage_complete", run_id=run.run_id)
        return StageResult(
            stage=self.get_name(),
            success=True,
            message=f'Deployed to staging: {deploy_info.get("url", "unknown")}',
            duration_seconds=deploy_info.get("duration", 90),
            metadata={"url": deploy_info.get("url", "")},
        )


class ApprovalStage(BaseStage):
    """Aguarda aprovação manual."""

    def get_name(self) -> PipelineStage:
        return PipelineStage.APPROVAL

    async def execute(self, run: PipelineRun, context: dict) -> StageResult:
        self.logger.info("approval_stage_waiting", run_id=run.run_id)

        # Check if approval was granted
        approved = context.get("approved", False)

        message = "Approval granted" if approved else "Awaiting approval"
        self.logger.info("approval_stage_complete", run_id=run.run_id, approved=approved)

        return StageResult(
            stage=self.get_name(),
            success=approved,
            message=message,
            duration_seconds=0,
        )


class ProductionStage(BaseStage):
    """Deploy para ambiente de produção."""

    def get_name(self) -> PipelineStage:
        return PipelineStage.PRODUCTION

    async def execute(self, run: PipelineRun, context: dict) -> StageResult:
        self.logger.info("production_stage_starting", run_id=run.run_id)

        deploy_info = context.get("production_deploy", {})

        self.logger.info("production_stage_complete", run_id=run.run_id)
        return StageResult(
            stage=self.get_name(),
            success=True,
            message=f'Deployed to production: {deploy_info.get("url", "unknown")}',
            duration_seconds=deploy_info.get("duration", 120),
            metadata={"url": deploy_info.get("url", "")},
        )
