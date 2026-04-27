from datetime import datetime, timezone

import pytest
from src.models.pipeline import (
    DeployRequest,
    Insight,
    InsightsReport,
    PipelineRun,
    RollbackRequest,
)
from src.models.schemas import (
    InsightType,
    PipelineProvider,
    PipelineStage,
    PipelineStatus,
    Severity,
)


def test_pipeline_run_creation():
    run = PipelineRun(
        run_id="run-123",
        manifest_id="manifest-456",
        repo_url="https://github.com/org/repo",
        git_sha="abc123",
    )
    assert run.run_id == "run-123"
    assert run.status == PipelineStatus.PENDING
    assert run.current_stage is None
    assert run.stages_completed == []


def test_deploy_request_validation():
    request = DeployRequest(
        repo_url="https://github.com/org/repo",
        git_sha="abc123",
        environment="staging",
    )
    assert request.environment == "staging"
    assert request.branch == "main"
    assert request.provider == PipelineProvider.GITHUB_ACTIONS


def test_deploy_request_invalid_environment():
    with pytest.raises(ValueError):
        DeployRequest(
            repo_url="https://github.com/org/repo",
            git_sha="abc123",
            environment="invalid",
        )


def test_pipeline_run_stage_progression():
    run = PipelineRun(
        run_id="run-123",
        manifest_id="manifest-456",
        repo_url="https://github.com/org/repo",
        git_sha="abc123",
    )
    run.stages_completed.append(PipelineStage.BUILD)
    run.current_stage = PipelineStage.TEST
    run.status = PipelineStatus.RUNNING

    assert len(run.stages_completed) == 1
    assert run.current_stage == PipelineStage.TEST
    assert run.status == PipelineStatus.RUNNING


def test_rollback_request():
    request = RollbackRequest(
        run_id="run-123",
        reason="Health check failed",
    )
    assert request.run_id == "run-123"
    assert request.reason == "Health check failed"
    assert request.force is False


def test_pipeline_manifest_with_utcnow():
    from src.models.pipeline import PipelineManifest

    manifest = PipelineManifest(
        manifest_id="manifest-123",
        repo_url="https://github.com/org/repo",
        branch="main",
        provider=PipelineProvider.GITHUB_ACTIONS,
        content="name: test",
        stack={"language": "python"},
    )
    assert manifest.manifest_id == "manifest-123"
    assert isinstance(manifest.created_at, datetime)


def test_anomaly_model():
    from src.models.pipeline import Anomaly
    from src.models.schemas import AnomalyType, Severity

    anomaly = Anomaly(
        anomaly_id="anom-1",
        repo_url="https://github.com/org/repo",
        type=AnomalyType.FLAKY_TEST,
        severity=Severity.HIGH,
        description="Test fails intermittently",
    )
    assert anomaly.anomaly_id == "anom-1"
    assert anomaly.resolved is False


def test_insight_model():
    insight = Insight(
        insight_id="insight-1",
        repo_url="https://github.com/org/repo",
        insight_type=InsightType.FLAKY_TEST,
        title="Flaky test in authentication module",
        description="TestAuthService::test_login fails intermittently",
        impact=Severity.MEDIUM,
        effort="M",
    )
    assert insight.insight_id == "insight-1"
    assert insight.insight_type == InsightType.FLAKY_TEST
    assert insight.effort == "M"


def test_insights_report_model():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 31, tzinfo=UTC)

    insight = Insight(
        insight_id="insight-1",
        repo_url="https://github.com/org/repo",
        insight_type=InsightType.SLOW_TEST,
        title="Slow integration test",
        description="Test takes 15 minutes to run",
        impact=Severity.LOW,
        effort="S",
    )

    report = InsightsReport(
        repo_url="https://github.com/org/repo",
        timeframe_start=start,
        timeframe_end=end,
        total_runs=100,
        success_rate=0.92,
        average_duration_seconds=300.0,
        slow_tests=[insight],
    )
    assert report.total_runs == 100
    assert report.success_rate == 0.92
    assert len(report.slow_tests) == 1
    assert report.slow_tests[0].insight_type == InsightType.SLOW_TEST


def test_component_replicas_validation():
    from pydantic import ValidationError
    from src.models.schemas import Component

    # Valid: replicas >= 0
    component = Component(name="api", image="api:latest", replicas=0)
    assert component.replicas == 0

    # Valid: replicas > 0
    component = Component(name="api", image="api:latest", replicas=3)
    assert component.replicas == 3

    # Invalid: negative replicas should raise error
    with pytest.raises(ValidationError):
        Component(name="api", image="api:latest", replicas=-1)


def test_deploy_request_timeout_validation():
    from pydantic import ValidationError

    # Valid: timeout within range
    request = DeployRequest(
        repo_url="https://github.com/org/repo",
        git_sha="abc123",
        environment="staging",
        timeout_minutes=60,
    )
    assert request.timeout_minutes == 60

    # Valid: max timeout (720 minutes = 12 hours)
    request = DeployRequest(
        repo_url="https://github.com/org/repo",
        git_sha="abc123",
        environment="staging",
        timeout_minutes=720,
    )
    assert request.timeout_minutes == 720

    # Invalid: timeout > 720
    with pytest.raises(ValidationError):
        DeployRequest(
            repo_url="https://github.com/org/repo",
            git_sha="abc123",
            environment="staging",
            timeout_minutes=721,
        )

    # Invalid: timeout < 1
    with pytest.raises(ValidationError):
        DeployRequest(
            repo_url="https://github.com/org/repo",
            git_sha="abc123",
            environment="staging",
            timeout_minutes=0,
        )


def test_extra_fields_forbidden():
    from pydantic import ValidationError
    from src.models.schemas import Component

    # Extra fields should raise error
    with pytest.raises(ValidationError):
        Component(
            name="api",
            image="api:latest",
            replicas=1,
            unknown_field="should_fail",
        )
