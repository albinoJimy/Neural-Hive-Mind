"""
Activity Temporal para Feedback Loop - Coleta de métricas pós-deploy.
"""

from typing import Any

import structlog
from temporalio import activity

logger = structlog.get_logger(__name__)


@activity.defn
async def collect_post_deployment_metrics(
    deployment_id: str,
    plan_id: str,
    workflow_id: str,
    service_url: str,
) -> dict[str, Any]:
    """
    Coleta métricas pós-deployment do serviço.

    Args:
        deployment_id: ID do deployment
        plan_id: ID do plano cognitivo
        workflow_id: ID do workflow executado
        service_url: URL do serviço deployado

    Returns:
        Dict com métricas coletadas
    """
    logger.info(
        "collecting_post_deployment_metrics",
        deployment_id=deployment_id,
        plan_id=plan_id,
        service_url=service_url,
    )

    # Em produção, isso consultaria Prometheus/Grafana/Datadog
    # Por ora, retornar métricas simuladas
    metrics = {
        "deployment_id": deployment_id,
        "plan_id": plan_id,
        "workflow_id": workflow_id,
        "service_url": service_url,
        "collected_at": activity.now().isoformat(),
        "performance": {
            "response_time_ms": 150.0,
            "throughput_rps": 45.0,
            "error_rate": 0.001,
        },
        "reliability": {
            "uptime_pct": 99.9,
            "restart_count": 0,
            "crash_count": 0,
        },
        "quality": {
            "test_coverage": 0.85,
            "lint_issues": 3,
            "security_issues": 0,
        },
        "resource_usage": {
            "avg_cpu_pct": 35.0,
            "avg_memory_mb": 256.0,
            "peak_memory_mb": 512.0,
        },
        "health_status": "healthy",
    }

    logger.info(
        "post_deployment_metrics_collected",
        deployment_id=deployment_id,
        response_time_ms=metrics["performance"]["response_time_ms"],
        error_rate=metrics["performance"]["error_rate"],
        health_status=metrics["health_status"],
    )

    return metrics


@activity.defn
async def analyze_deployment_quality(
    deployment_metrics: dict[str, Any],
    quality_thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Analisa a qualidade de um deployment e gera score.

    Args:
        deployment_metrics: Métricas coletadas
        quality_thresholds: Thresholds customizados

    Returns:
        Dict com análise e score de qualidade
    """
    logger.info(
        "analyzing_deployment_quality",
        deployment_id=deployment_metrics.get("deployment_id"),
    )

    thresholds = quality_thresholds or {
        "max_response_time_ms": 500,
        "max_error_rate": 0.05,
        "min_uptime_pct": 99.0,
        "min_test_coverage": 0.7,
        "max_cpu_pct": 80.0,
    }

    performance = deployment_metrics.get("performance", {})
    reliability = deployment_metrics.get("reliability", {})
    quality = deployment_metrics.get("quality", {})
    resources = deployment_metrics.get("resource_usage", {})

    # Calcular score individual (0-1)
    response_time_score = max(
        0,
        1 - (performance.get("response_time_ms", 0) / thresholds["max_response_time_ms"]),
    )
    error_rate_score = max(0, 1 - (performance.get("error_rate", 0) / thresholds["max_error_rate"]))
    uptime_score = min(
        1,
        reliability.get("uptime_pct", 0) / thresholds["min_uptime_pct"],
    )
    test_coverage_score = min(
        1,
        quality.get("test_coverage", 0) / thresholds["min_test_coverage"],
    )
    cpu_score = max(
        0,
        1 - (resources.get("avg_cpu_pct", 0) / thresholds["max_cpu_pct"]),
    )

    # Score geral (média ponderada)
    overall_score = (
        response_time_score * 0.25
        + error_rate_score * 0.30
        + uptime_score * 0.20
        + test_coverage_score * 0.15
        + cpu_score * 0.10
    )

    # Determinar status
    if overall_score >= 0.9:
        status = "excellent"
    elif overall_score >= 0.75:
        status = "good"
    elif overall_score >= 0.6:
        status = "acceptable"
    else:
        status = "needs_improvement"

    # Identificar issues
    issues = []
    if response_time_score < 0.6:
        issues.append("high_response_time")
    if error_rate_score < 0.6:
        issues.append("high_error_rate")
    if uptime_score < 0.6:
        issues.append("low_uptime")
    if test_coverage_score < 0.6:
        issues.append("low_test_coverage")
    if cpu_score < 0.6:
        issues.append("high_cpu_usage")

    result = {
        "deployment_id": deployment_metrics.get("deployment_id"),
        "overall_score": round(overall_score, 3),
        "status": status,
        "scores": {
            "response_time": round(response_time_score, 3),
            "error_rate": round(error_rate_score, 3),
            "uptime": round(uptime_score, 3),
            "test_coverage": round(test_coverage_score, 3),
            "cpu_usage": round(cpu_score, 3),
        },
        "issues": issues,
        "recommendations": _generate_recommendations(issues, overall_score),
        "analyzed_at": activity.now().isoformat(),
    }

    logger.info(
        "deployment_quality_analyzed",
        deployment_id=deployment_metrics.get("deployment_id"),
        overall_score=result["overall_score"],
        status=status,
        issues_count=len(issues),
    )

    return result


@activity.defn
async def generate_specialist_feedback(
    plan_id: str,
    deployment_id: str,
    quality_analysis: dict[str, Any],
    workflow_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Gera feedback para especialistas baseado na análise de qualidade.

    Args:
        plan_id: ID do plano
        deployment_id: ID do deployment
        quality_analysis: Análise de qualidade
        workflow_result: Resultado completo do workflow

    Returns:
        Dict com feedback gerado
    """
    logger.info(
        "generating_specialist_feedback",
        plan_id=plan_id,
        deployment_id=deployment_id,
        overall_score=quality_analysis.get("overall_score"),
    )

    feedback = {
        "plan_id": plan_id,
        "deployment_id": deployment_id,
        "feedback_type": "post_deployment",
        "generated_at": activity.now().isoformat(),
        "overall_score": quality_analysis.get("overall_score"),
        "status": quality_analysis.get("status"),
        "actionable": len(quality_analysis.get("issues", [])) > 0,
    }

    # Adicionar recomendações
    if quality_analysis.get("status") in ["needs_improvement", "acceptable"]:
        feedback["recommendations"] = quality_analysis.get("recommendations", [])
        feedback["priority"] = (
            "high" if quality_analysis.get("status") == "needs_improvement" else "normal"
        )
    else:
        feedback["recommendations"] = ["Deployment successful, continue monitoring"]
        feedback["priority"] = "low"

    # Adicionar contexto do workflow
    if workflow_result:
        feedback["workflow_context"] = {
            "workflow_id": workflow_result.get("workflow_id"),
            "workflow_type": workflow_result.get("workflow_type"),
            "duration_ms": workflow_result.get("duration_ms"),
        }

    logger.info(
        "specialist_feedback_generated",
        plan_id=plan_id,
        priority=feedback.get("priority"),
        recommendations_count=len(feedback.get("recommendations", [])),
    )

    return feedback


@activity.defn
async def record_feedback_for_ml(
    plan_id: str,
    workflow_type: str,
    intent_text: str,
    deployment_result: dict[str, Any],
    quality_score: float,
    user_feedback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Registra feedback para retreinamento de modelos ML.

    Args:
        plan_id: ID do plano
        workflow_type: Tipo de workflow (orchestration/generation)
        intent_text: Texto da intent original
        deployment_result: Resultado do deployment
        quality_score: Score de qualidade
        user_feedback: Feedback opcional do usuário

    Returns:
        Dict com dados registrados
    """
    logger.info(
        "recording_feedback_for_ml",
        plan_id=plan_id,
        workflow_type=workflow_type,
        quality_score=quality_score,
    )

    # Construir exemplo de treinamento
    training_example = {
        "plan_id": plan_id,
        "features": {
            "intent_text": intent_text,
            "workflow_type": workflow_type,
            "deployment_success": deployment_result.get("status") == "deployed",
            "quality_score": quality_score,
        },
        "labels": {
            "success": quality_score > 0.7,
            "user_satisfied": user_feedback.get("rating", 5) >= 4 if user_feedback else None,
        },
        "metadata": {
            "deployment_id": deployment_result.get("deployment_id"),
            "service_url": deployment_result.get("service_url"),
            "recorded_at": activity.now().isoformat(),
        },
    }

    # Adicionar feedback do usuário se disponível
    if user_feedback:
        training_example["user_feedback"] = user_feedback

    # Em produção, isso seria salvo no MongoDB/Data Lake
    # para posterior uso em retreinamento

    logger.info(
        "feedback_recorded_for_ml",
        plan_id=plan_id,
        success_label=training_example["labels"]["success"],
    )

    return {
        "status": "recorded",
        "training_example": training_example,
    }


@activity.defn
async def check_feedback_thresholds(
    quality_analysis: dict[str, Any],
    feedback_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Verifica se thresholds de feedback foram atingidos.

    Args:
        quality_analysis: Análise de qualidade
        feedback_summary: Resumo de feedback existente

    Returns:
        Dict com resultado da verificação
    """
    overall_score = quality_analysis.get("overall_score", 0)
    issues = quality_analysis.get("issues", [])

    # Thresholds para acionar feedback
    needs_feedback = overall_score < 0.7 or len(issues) > 0

    result = {
        "needs_feedback": needs_feedback,
        "overall_score": overall_score,
        "issues_count": len(issues),
        "trigger_reason": None,
        "action": "continue_monitoring" if not needs_feedback else "request_specialist_review",
    }

    if needs_feedback:
        if overall_score < 0.5:
            result["trigger_reason"] = "very_low_quality_score"
            result["action"] = "escalate_immediately"
        elif len(issues) >= 3:
            result["trigger_reason"] = "multiple_critical_issues"
            result["action"] = "request_specialist_review"
        else:
            result["trigger_reason"] = "below_quality_threshold"
            result["action"] = "schedule_review"

    logger.info(
        "feedback_thresholds_checked",
        needs_feedback=needs_feedback,
        action=result["action"],
    )

    return result


def _generate_recommendations(issues: list[str], overall_score: float) -> list[str]:
    """Gera recomendações baseadas nos issues."""
    recommendations = []

    if "high_response_time" in issues:
        recommendations.append("Optimize code performance or increase resource allocation")

    if "high_error_rate" in issues:
        recommendations.append("Investigate and fix errors, consider rollback if severe")

    if "low_uptime" in issues:
        recommendations.append("Review infrastructure stability and add redundancy")

    if "low_test_coverage" in issues:
        recommendations.append("Increase test coverage before next deployment")

    if "high_cpu_usage" in issues:
        recommendations.append("Optimize resource usage or scale horizontally")

    if overall_score >= 0.9 and not issues:
        recommendations.append("Excellent deployment, consider as gold standard")

    return recommendations
