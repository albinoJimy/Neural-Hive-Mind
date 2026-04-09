"""API handlers for impact analysis endpoints."""

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query, status

from src.models.impact import (
    BatchImpactAnalysisRequest,
    ImpactAnalysisRequest,
    ImpactAnalysisResponse,
    ImpactCategory,
    ImpactDirection,
    ImpactMagnitude,
    ImpactSummary,
)
from src.services.impact_analyzer import ImpactAnalyzer

logger = structlog.get_logger()
router = APIRouter(prefix="/impact", tags=["impact"])


def get_analyzer() -> ImpactAnalyzer:
    """Get impact analyzer instance (dependency injection)."""
    from src.main import impact_analyzer
    if impact_analyzer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Impact analyzer not initialized"
        )
    return impact_analyzer


@router.post("/analyze", response_model=ImpactAnalysisResponse)
async def analyze_impact(request: ImpactAnalysisRequest) -> ImpactAnalysisResponse:
    """Analyze impact of an experiment.

    Performs comprehensive impact analysis including short-term and/or
    long-term effects, and can identify correlations with other experiments.

    Args:
        request: Impact analysis request

    Returns:
        Impact analysis response
    """
    analyzer = get_analyzer()

    try:
        logger.info(
            "impact_analysis_requested",
            experiment_id=request.experiment_id,
            timeframes=[tf.value for tf in request.timeframes],
        )

        # Perform analysis
        impact = await analyzer.analyze_experiment_impact(
            experiment_id=request.experiment_id,
            timeframes=request.timeframes,
            include_correlations=request.include_correlations,
            force_refresh=request.force_refresh,
        )

        return ImpactAnalysisResponse(
            impact_id=impact.impact_id,
            experiment_id=impact.experiment_id,
            status="completed",
            overall_direction=impact.overall_direction,
            overall_magnitude=impact.overall_magnitude,
            recommendation=impact.recommendation,
            confidence_level=impact.confidence_level,
            short_term_available=impact.short_term_impact is not None,
            long_term_available=impact.long_term_impact is not None,
            correlations_available=len(impact.correlated_experiments) > 0,
        )

    except ValueError as e:
        logger.warning("experiment_not_found", experiment_id=request.experiment_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment not found: {request.experiment_id}"
        )
    except Exception as e:
        logger.error("impact_analysis_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Impact analysis failed: {str(e)}"
        )


@router.get("/experiment/{experiment_id}")
async def get_experiment_impact(experiment_id: str) -> dict[str, Any]:
    """Get existing impact analysis for an experiment.

    Args:
        experiment_id: Experiment ID

    Returns:
        Impact analysis document
    """
    analyzer = get_analyzer()

    impact = await analyzer.mongodb.get_impact_by_experiment(experiment_id)
    if not impact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No impact analysis found for experiment: {experiment_id}"
        )

    # Remove MongoDB _id
    if "_id" in impact:
        del impact["_id"]

    return impact


@router.get("/summary")
async def get_impact_summary(
    days: int = Query(default=30, ge=1, le=365, description="Days to look back")
) -> ImpactSummary:
    """Get summary of experiment impacts.

    Provides aggregate statistics about all experiment impacts
    within the specified time window.

    Args:
        days: Number of days to look back

    Returns:
        Impact summary
    """
    from datetime import datetime, timedelta, timezone

    UTC = timezone.utc
    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=days)

    analyzer = get_analyzer()

    summary = await analyzer.mongodb.get_impact_summary(start_date, end_date)
    return summary


@router.get("/search")
async def search_impacts(
    direction: ImpactDirection | None = Query(None, description="Filter by impact direction"),
    magnitude: ImpactMagnitude | None = Query(None, description="Filter by impact magnitude"),
    category: ImpactCategory | None = Query(None, description="Filter by impact category"),
    limit: int = Query(default=20, ge=1, le=100, description="Max results"),
) -> list[dict[str, Any]]:
    """Search for impacts matching criteria.

    Args:
        direction: Impact direction filter
        magnitude: Impact magnitude filter
        category: Impact category filter
        limit: Maximum number of results

    Returns:
        List of matching impacts
    """
    analyzer = get_analyzer()

    categories = [category] if category else None
    results = await analyzer.mongodb.find_experiments_with_impact(
        direction=direction,
        magnitude=magnitude,
        categories=categories,
        limit=limit,
    )

    # Clean up MongoDB IDs
    for result in results:
        if "_id" in result:
            del result["_id"]

    return results


@router.post("/batch")
async def batch_analyze(request: BatchImpactAnalysisRequest) -> dict[str, Any]:
    """Analyze multiple experiments in batch.

    Args:
        request: Batch analysis request

    Returns:
        Batch analysis results with status for each experiment
    """
    analyzer = get_analyzer()

    results = {}
    for experiment_id in request.experiment_ids:
        try:
            impact = await analyzer.analyze_experiment_impact(
                experiment_id=experiment_id,
                timeframes=request.timeframes,
                include_correlations=False,  # Skip correlations for batch
                force_refresh=True,
            )
            results[experiment_id] = {
                "status": "completed",
                "impact_id": impact.impact_id,
                "direction": impact.overall_direction.value,
                "magnitude": impact.overall_magnitude.value,
                "confidence": impact.confidence_level,
            }
        except Exception as e:
            logger.warning("batch_analysis_failed", experiment_id=experiment_id, error=str(e))
            results[experiment_id] = {
                "status": "failed",
                "error": str(e),
            }

    return {
        "total": len(request.experiment_ids),
        "completed": sum(1 for r in results.values() if r["status"] == "completed"),
        "failed": sum(1 for r in results.values() if r["status"] == "failed"),
        "results": results,
    }


@router.get("/trends")
async def get_impact_trends(
    metric: str = Query(default="confidence_level", description="Metric to track"),
    days: int = Query(default=30, ge=7, le=365, description="Days to look back"),
) -> list[dict[str, Any]]:
    """Get impact trends over time.

    Returns time series data for the specified metric.

    Args:
        metric: Metric name to track
        days: Number of days to look back

    Returns:
        Time series data points
    """
    from src.repositories.impact_repository import ImpactRepository

    analyzer = get_analyzer()
    repository = ImpactRepository(analyzer.mongodb.get_database())

    trends = await repository.get_time_series(metric_name=metric, days=days)
    return trends


@router.delete("/experiment/{experiment_id}")
async def delete_impact_analysis(experiment_id: str) -> dict[str, Any]:
    """Delete impact analysis for an experiment.

    Args:
        experiment_id: Experiment ID

    Returns:
        Deletion result
    """
    analyzer = get_analyzer()

    # Get the impact first to find its ID
    impact = await analyzer.mongodb.get_impact_by_experiment(experiment_id)
    if not impact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No impact analysis found for experiment: {experiment_id}"
        )

    impact_id = impact.get("impact_id")
    if not impact_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid impact document"
        )

    # Delete from database
    from motor.motor_asyncio import AsyncIOMotorDatabase

    db: AsyncIOMotorDatabase = analyzer.mongodb.get_database()
    collection = db[analyzer.settings.mongodb_impacts_collection]

    result = await collection.delete_one({"impact_id": impact_id})

    return {
        "deleted": result.deleted_count > 0,
        "impact_id": impact_id,
        "experiment_id": experiment_id,
    }
