import pytest
from src.models.pipeline import PipelineRun, RollbackRequest
from src.models.schemas import PipelineStage, PipelineStatus
from src.orchestrators.pipeline_orchestrator import (
    OrchestratorConfig,
    PipelineOrchestrator,
)


@pytest.mark.asyncio()
async def test_orchestrator_execute_staging_success():
    config = OrchestratorConfig(timeout_minutes=1)
    orchestrator = PipelineOrchestrator(config)

    run = PipelineRun(
        run_id="test-run-1",
        manifest_id="manifest-1",
        repo_url="https://github.com/org/repo",
        git_sha="abc123",
    )

    context = {
        "environment": "staging",
        "preflight_checks": {"has_secrets": True, "version": "1.0.0"},
        "build_info": {"image": "repo:latest", "digest": "sha256:123", "duration": 10},
        "test_results": {"passed": 10, "total": 10, "duration": 5},
        "security_scan": {"critical": 0, "high": 0, "duration": 3},
        "staging_deploy": {"url": "https://staging.example.com", "duration": 8},
    }

    result = await orchestrator.execute(run, context)

    assert result.status == PipelineStatus.SUCCESS
    assert len(result.stages_completed) == 5  # pre_flight, build, test, security, staging
    assert result.finished_at is not None


@pytest.mark.asyncio()
async def test_orchestrator_execute_test_failure():
    orchestrator = PipelineOrchestrator()

    run = PipelineRun(
        run_id="test-run-2",
        manifest_id="manifest-1",
        repo_url="https://github.com/org/repo",
        git_sha="abc123",
    )

    context = {
        "preflight_checks": {"has_secrets": True, "version": "1.0.0"},
        "build_info": {"image": "repo:latest", "digest": "sha256:123", "duration": 10},
        "test_results": {"passed": 5, "total": 10, "duration": 5},  # Failed tests
    }

    result = await orchestrator.execute(run, context)

    assert result.status == PipelineStatus.FAILED
    assert PipelineStage.TEST in result.stages_failed
    assert PipelineStage.SECURITY not in result.stages_completed  # Stopped at test


@pytest.mark.asyncio()
async def test_orchestrator_rollback():
    orchestrator = PipelineOrchestrator()

    run = PipelineRun(
        run_id="test-run-3",
        manifest_id="manifest-1",
        repo_url="https://github.com/org/repo",
        git_sha="abc123",
        status=PipelineStatus.RUNNING,
    )

    request = RollbackRequest(
        run_id="test-run-3",
        reason="Health check failed",
    )

    context = {"run": run}

    result = await orchestrator.rollback(request, context)

    assert result.status == PipelineStatus.ROLLED_BACK
    assert result.rollback_reason == "Health check failed"


@pytest.mark.asyncio()
async def test_orchestrator_health_check():
    orchestrator = PipelineOrchestrator()

    run = PipelineRun(
        run_id="test-run-4",
        manifest_id="manifest-1",
        repo_url="https://github.com/org/repo",
        git_sha="abc123",
    )

    result = await orchestrator.check_health(run)

    assert result is True


@pytest.mark.asyncio()
async def test_orchestrator_should_rollback_no_degradation():
    config = OrchestratorConfig(
        rollback_on_health_check=False,
        rollback_on_metrics_degradation=False,
    )
    orchestrator = PipelineOrchestrator(config)

    run = PipelineRun(
        run_id="test-run-5",
        manifest_id="manifest-1",
        repo_url="https://github.com/org/repo",
        git_sha="abc123",
    )

    should_rollback, reason = await orchestrator.should_rollback(run)

    assert should_rollback is False
    assert reason == ""


@pytest.mark.asyncio()
async def test_orchestrator_production_sequence():
    orchestrator = PipelineOrchestrator()

    run = PipelineRun(
        run_id="test-run-6",
        manifest_id="manifest-1",
        repo_url="https://github.com/org/repo",
        git_sha="abc123",
    )

    context = {
        "environment": "production",
        "preflight_checks": {"has_secrets": True, "version": "1.0.0"},
        "build_info": {"image": "repo:latest", "digest": "sha256:123", "duration": 10},
        "test_results": {"passed": 10, "total": 10, "duration": 5},
        "security_scan": {"critical": 0, "high": 0, "duration": 3},
        "staging_deploy": {"url": "https://staging.example.com", "duration": 8},
        "approved": True,
        "production_deploy": {"url": "https://example.com", "duration": 10},
    }

    result = await orchestrator.execute(run, context)

    assert result.status == PipelineStatus.SUCCESS
    assert len(result.stages_completed) == 7  # All stages including approval


@pytest.mark.asyncio()
async def test_orchestrator_production_approval_denied():
    orchestrator = PipelineOrchestrator()

    run = PipelineRun(
        run_id="test-run-7",
        manifest_id="manifest-1",
        repo_url="https://github.com/org/repo",
        git_sha="abc123",
    )

    context = {
        "environment": "production",
        "preflight_checks": {"has_secrets": True, "version": "1.0.0"},
        "build_info": {"image": "repo:latest", "digest": "sha256:123", "duration": 10},
        "test_results": {"passed": 10, "total": 10, "duration": 5},
        "security_scan": {"critical": 0, "high": 0, "duration": 3},
        "staging_deploy": {"url": "https://staging.example.com", "duration": 8},
        "approved": False,  # Approval denied
    }

    result = await orchestrator.execute(run, context)

    assert result.status == PipelineStatus.FAILED
    assert PipelineStage.APPROVAL in result.stages_failed
    assert PipelineStage.PRODUCTION not in result.stages_completed


@pytest.mark.asyncio()
async def test_orchestrator_security_failure():
    orchestrator = PipelineOrchestrator()

    run = PipelineRun(
        run_id="test-run-8",
        manifest_id="manifest-1",
        repo_url="https://github.com/org/repo",
        git_sha="abc123",
    )

    context = {
        "preflight_checks": {"has_secrets": True, "version": "1.0.0"},
        "build_info": {"image": "repo:latest", "digest": "sha256:123", "duration": 10},
        "test_results": {"passed": 10, "total": 10, "duration": 5},
        "security_scan": {"critical": 2, "high": 5, "duration": 3},  # Critical vulns
    }

    result = await orchestrator.execute(run, context)

    assert result.status == PipelineStatus.FAILED
    assert PipelineStage.SECURITY in result.stages_failed


@pytest.mark.asyncio()
async def test_orchestrator_preflight_failure():
    orchestrator = PipelineOrchestrator()

    run = PipelineRun(
        run_id="test-run-9",
        manifest_id="manifest-1",
        repo_url="https://github.com/org/repo",
        git_sha="abc123",
    )

    context = {
        "preflight_checks": {"has_secrets": False, "version": "1.0.0"},  # No secrets
    }

    result = await orchestrator.execute(run, context)

    assert result.status == PipelineStatus.FAILED
    assert PipelineStage.PRE_FLIGHT in result.stages_failed
