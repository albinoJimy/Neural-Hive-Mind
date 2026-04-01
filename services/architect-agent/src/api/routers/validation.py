"""Router para endpoints de validação."""

from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, HTTPException, status

from src.api.schemas import (
    SuggestionResponse,
    ValidationRequest,
    ValidationResponse,
    ViolationResponse,
)
from src.repositories.validation_repository import ValidationRepository
from src.validators.validate_engine import ValidateEngine

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/validation", tags=["validation"])

# Dependências (singleton instances)
_validate_engine_instance = None
_validation_repository_instance = None


def get_validate_engine() -> ValidateEngine:
    """Retorna instância singleton do ValidateEngine."""
    global _validate_engine_instance
    if _validate_engine_instance is None:
        _validate_engine_instance = ValidateEngine()
    return _validate_engine_instance


def get_validation_repository() -> ValidationRepository:
    """Retorna instância singleton do ValidationRepository."""
    global _validation_repository_instance
    if _validation_repository_instance is None:
        _validation_repository_instance = ValidationRepository()
    return _validation_repository_instance


@router.post("", response_model=ValidationResponse, status_code=status.HTTP_201_CREATED)
async def validate_repository(request: ValidationRequest) -> ValidationResponse:
    """Executa validação de repositório."""
    try:
        validate_engine = get_validate_engine()
        validation_repository = get_validation_repository()

        target = {
            "repo_url": request.repo_url,
            "branch": request.branch,
        }

        # Executar validação
        report = await validate_engine.validate(target)

        # Persistir relatório
        await validation_repository.create(report)

        logger.info(
            "validation_completed",
            report_id=report.report_id,
            health_score=report.health_score,
        )

        return ValidationResponse(
            report_id=report.report_id,
            repo_url=report.repo_url,
            branch=report.branch,
            health_score=report.health_score,
            trend=report.trend.value,
            violations=[
                ViolationResponse(
                    type=v.type.value,
                    severity=v.severity.value,
                    location=v.location,
                    description=v.description,
                    suggestion=v.suggestion,
                )
                for v in report.violations
            ],
            suggestions=[
                SuggestionResponse(
                    priority=s.priority,
                    description=s.description,
                    effort=s.effort,
                    affected_files=s.affected_files,
                )
                for s in report.suggestions
            ],
            created_at=report.created_at or datetime.now(timezone.utc),
        )

    except Exception as e:
        logger.error("validation_error", error=str(e))
        raise HTTPException(status_code=500, detail="Validation failed")


@router.get("/{report_id}", response_model=ValidationResponse)
async def get_validation_report(report_id: str) -> ValidationResponse:
    """Obtém relatório de validação por ID."""
    validation_repository = get_validation_repository()
    report = await validation_repository.get_by_report_id(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Validation report not found")

    return ValidationResponse(
        report_id=report.report_id,
        repo_url=report.repo_url,
        branch=report.branch,
        health_score=report.health_score,
        trend=report.trend.value,
        violations=[
            ViolationResponse(
                type=v.type.value,
                severity=v.severity.value,
                location=v.location,
                description=v.description,
                suggestion=v.suggestion,
            )
            for v in report.violations
        ],
        suggestions=[
            SuggestionResponse(
                priority=s.priority,
                description=s.description,
                effort=s.effort,
                affected_files=s.affected_files,
            )
            for s in report.suggestions
        ],
        created_at=report.created_at or datetime.now(timezone.utc),
    )


@router.get("/repo/{repo_url:path}", response_model=list[ValidationResponse])
async def get_validations_by_repo(repo_url: str, limit: int = 10) -> list[ValidationResponse]:
    """Obtém validações de um repositório."""
    validation_repository = get_validation_repository()
    reports = await validation_repository.get_by_repo_url(repo_url, limit)

    return [
        ValidationResponse(
            report_id=r.report_id,
            repo_url=r.repo_url,
            branch=r.branch,
            health_score=r.health_score,
            trend=r.trend.value,
            violations=[
                ViolationResponse(
                    type=v.type.value,
                    severity=v.severity.value,
                    location=v.location,
                    description=v.description,
                    suggestion=v.suggestion,
                )
                for v in r.violations
            ],
            suggestions=[
                SuggestionResponse(
                    priority=s.priority,
                    description=s.description,
                    effort=s.effort,
                    affected_files=s.affected_files,
                )
                for s in r.suggestions
            ],
            created_at=r.created_at or datetime.now(timezone.utc),
        )
        for r in reports
    ]
