import pytest
from datetime import datetime, timezone
from src.models.schemas import PipelineProvider, PipelineStatus, PipelineStage
from src.models.pipeline import PipelineRun, DeployRequest, RollbackRequest


def test_pipeline_run_creation():
    run = PipelineRun(
        run_id='run-123',
        manifest_id='manifest-456',
        repo_url='https://github.com/org/repo',
        git_sha='abc123',
    )
    assert run.run_id == 'run-123'
    assert run.status == PipelineStatus.PENDING
    assert run.current_stage is None
    assert run.stages_completed == []


def test_deploy_request_validation():
    request = DeployRequest(
        repo_url='https://github.com/org/repo',
        git_sha='abc123',
        environment='staging',
    )
    assert request.environment == 'staging'
    assert request.branch == 'main'
    assert request.provider == PipelineProvider.GITHUB_ACTIONS


def test_deploy_request_invalid_environment():
    with pytest.raises(ValueError):
        DeployRequest(
            repo_url='https://github.com/org/repo',
            git_sha='abc123',
            environment='invalid',
        )


def test_pipeline_run_stage_progression():
    run = PipelineRun(
        run_id='run-123',
        manifest_id='manifest-456',
        repo_url='https://github.com/org/repo',
        git_sha='abc123',
    )
    run.stages_completed.append(PipelineStage.BUILD)
    run.current_stage = PipelineStage.TEST
    run.status = PipelineStatus.RUNNING

    assert len(run.stages_completed) == 1
    assert run.current_stage == PipelineStage.TEST
    assert run.status == PipelineStatus.RUNNING


def test_rollback_request():
    request = RollbackRequest(
        run_id='run-123',
        reason='Health check failed',
    )
    assert request.run_id == 'run-123'
    assert request.reason == 'Health check failed'
    assert request.force is False


def test_pipeline_manifest_with_utcnow():
    from src.models.pipeline import PipelineManifest
    from src.models.schemas import ProjectStack

    manifest = PipelineManifest(
        manifest_id='manifest-123',
        repo_url='https://github.com/org/repo',
        branch='main',
        provider=PipelineProvider.GITHUB_ACTIONS,
        content='name: test',
        stack={'language': 'python'},
    )
    assert manifest.manifest_id == 'manifest-123'
    assert isinstance(manifest.created_at, datetime)


def test_anomaly_model():
    from src.models.pipeline import Anomaly
    from src.models.schemas import AnomalyType, Severity

    anomaly = Anomaly(
        anomaly_id='anom-1',
        repo_url='https://github.com/org/repo',
        type=AnomalyType.FLAKY_TEST,
        severity=Severity.HIGH,
        description='Test fails intermittently',
    )
    assert anomaly.anomaly_id == 'anom-1'
    assert anomaly.resolved is False
