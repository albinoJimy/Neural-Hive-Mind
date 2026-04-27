from datetime import datetime, timezone, timedelta

import pytest
from src.intelligence.anomaly_detector import (
    AnomalyDetector,
)
from src.intelligence.flaky_test_detector import FlakyTestDetector
from src.intelligence.insights_generator import InsightConfig, InsightsGenerator
from src.models.schemas import Severity


@pytest.mark.asyncio()
async def test_detect_performance_degradation():
    detector = AnomalyDetector()

    current_run = {
        "run_id": "current",
        "repo_url": "https://github.com/org/repo",
        "duration_seconds": 600,  # 10 minutes
    }

    historical_runs = [
        {"run_id": "hist-1", "duration_seconds": 180},
        {"run_id": "hist-2", "duration_seconds": 200},
        {"run_id": "hist-3", "duration_seconds": 190},
    ]

    anomalies = await detector._detect_performance_degradation(current_run, historical_runs)

    assert len(anomalies) == 1
    assert anomalies[0].type == "performance_degradation"


@pytest.mark.asyncio()
async def test_detect_no_flaky_tests():
    detector = AnomalyDetector()

    current_run = {
        "run_id": "current",
        "repo_url": "https://github.com/org/repo",
        "test_results": {
            "failed_tests": ["test_login"],
        },
    }

    historical_runs = [
        {
            "run_id": "hist-1",
            "test_results": {
                "failed_tests": ["test_login"],
                "passed_tests": ["test_logout"],
            },
        },
    ]

    anomalies = await detector._detect_flaky_tests(current_run, historical_runs)

    # test_login failed in both, not flaky
    assert len(anomalies) == 0


@pytest.mark.asyncio()
async def test_detect_flaky_tests():
    detector = AnomalyDetector()

    current_run = {
        "run_id": "current",
        "repo_url": "https://github.com/org/repo",
        "test_results": {
            "failed_tests": ["test_login"],
            "passed_tests": ["test_logout"],
        },
    }

    historical_runs = [
        {
            "run_id": "hist-1",
            "test_results": {
                "failed_tests": [],
                "passed_tests": ["test_login", "test_logout"],
            },
        },
        {
            "run_id": "hist-2",
            "test_results": {
                "failed_tests": [],
                "passed_tests": ["test_login", "test_logout"],
            },
        },
    ]

    anomalies = await detector._detect_flaky_tests(current_run, historical_runs)

    # test_login passed before, now fails - potentially flaky
    assert len(anomalies) == 1
    assert "test_login" in anomalies[0].affected_component


@pytest.mark.asyncio()
async def test_flaky_test_detector():
    detector = FlakyTestDetector(flaky_threshold=0.3)

    test_results = {
        "passed_tests": ["test_a", "test_b"],
        "failed_tests": ["test_c"],
    }

    # First run: test_c fails
    anomalies1 = await detector.analyze_test_results(
        test_results, "https://github.com/org/repo", "run-1"
    )
    assert len(anomalies1) == 0  # Need more data

    # Second run: test_c passes
    test_results["failed_tests"] = []
    test_results["passed_tests"].append("test_c")

    anomalies2 = await detector.analyze_test_results(
        test_results, "https://github.com/org/repo", "run-2"
    )

    # test_c should be flagged as flaky
    flaky_tests = detector.get_flaky_tests()
    assert len(flaky_tests) >= 1


@pytest.mark.asyncio()
async def test_insights_generator_basic():
    generator = InsightsGenerator()

    runs = [
        {
            "run_id": "run-1",
            "status": "success",
            "duration_seconds": 120,
            "test_results": {
                "failed_tests": [],
                "passed_tests": ["test_a", "test_b"],
                "test_durations": {"test_a": 2, "test_b": 3},
            },
            "security_scan": {"total": 0, "critical": 0},
            "cache_hit": True,
        },
        {
            "run_id": "run-2",
            "status": "failed",
            "duration_seconds": 180,
            "test_results": {
                "failed_tests": ["test_a"],
                "passed_tests": ["test_b"],
                "test_durations": {"test_a": 2, "test_b": 3},
            },
            "security_scan": {"total": 1, "critical": 0},
            "cache_hit": False,
        },
    ]

    timeframe_end = datetime.now(timezone.utc)
    timeframe_start = timeframe_end - timedelta(days=1)

    report = await generator.generate_insights(
        "https://github.com/org/repo",
        runs,
        timeframe_start,
        timeframe_end,
    )

    assert report.total_runs == 2
    assert report.success_rate == 0.5
    assert report.average_duration_seconds == 150.0
    assert len(report.flaky_tests) > 0  # test_a should be flaky


@pytest.mark.asyncio()
async def test_insights_generator_empty_runs():
    generator = InsightsGenerator()

    report = await generator.generate_insights(
        "https://github.com/org/repo",
        [],
        datetime.now(timezone.utc) - timedelta(days=1),
        datetime.now(timezone.utc),
    )

    assert report.total_runs == 0
    assert report.success_rate == 0.0


@pytest.mark.asyncio()
async def test_insights_generator_slow_tests():
    generator = InsightsGenerator(config=InsightConfig(slow_test_threshold_seconds=5))

    runs = [
        {
            "run_id": "run-1",
            "status": "success",
            "duration_seconds": 120,
            "test_results": {
                "failed_tests": [],
                "passed_tests": ["test_slow", "test_fast"],
                "test_durations": {"test_slow": 15, "test_fast": 1},
            },
            "security_scan": {"total": 0, "critical": 0},
        },
    ]

    timeframe_end = datetime.now(timezone.utc)
    timeframe_start = timeframe_end - timedelta(days=1)

    report = await generator.generate_insights(
        "https://github.com/org/repo",
        runs,
        timeframe_start,
        timeframe_end,
    )

    assert len(report.slow_tests) == 1
    assert report.slow_tests[0].insight_type == "slow_test"


@pytest.mark.asyncio()
async def test_security_anomaly_detection():
    detector = AnomalyDetector()

    run = {
        "run_id": "test-run",
        "repo_url": "https://github.com/org/repo",
        "security_scan": {
            "critical": 2,
            "high": 3,
        },
    }

    anomalies = await detector._detect_security_anomalies(run)

    assert len(anomalies) == 1
    assert anomalies[0].severity == Severity.CRITICAL


@pytest.mark.asyncio()
async def test_security_anomaly_high_vulns():
    detector = AnomalyDetector()

    run = {
        "run_id": "test-run",
        "repo_url": "https://github.com/org/repo",
        "security_scan": {
            "critical": 0,
            "high": 10,
        },
    }

    anomalies = await detector._detect_security_anomalies(run)

    assert len(anomalies) == 1
    assert anomalies[0].severity == Severity.HIGH


@pytest.mark.asyncio()
async def test_insights_generator_optimization_opportunities():
    generator = InsightsGenerator(config=InsightConfig(cache_miss_threshold=2))

    runs = [
        {
            "run_id": "run-1",
            "status": "success",
            "duration_seconds": 45,
            "test_results": {
                "failed_tests": [],
                "passed_tests": ["test_a"],
            },
            "security_scan": {"total": 0, "critical": 0},
            "cache_hit": False,
        },
        {
            "run_id": "run-2",
            "status": "success",
            "duration_seconds": 50,
            "test_results": {
                "failed_tests": [],
                "passed_tests": ["test_a"],
            },
            "security_scan": {"total": 0, "critical": 0},
            "cache_hit": False,
        },
        {
            "run_id": "run-3",
            "status": "success",
            "duration_seconds": 40,
            "test_results": {
                "failed_tests": [],
                "passed_tests": ["test_a"],
            },
            "security_scan": {"total": 0, "critical": 0},
            "cache_hit": False,
        },
    ]

    timeframe_end = datetime.now(timezone.utc)
    timeframe_start = timeframe_end - timedelta(days=1)

    report = await generator.generate_insights(
        "https://github.com/org/repo",
        runs,
        timeframe_start,
        timeframe_end,
    )

    # Should have cache miss insight (3 cache misses)
    assert len(report.optimization_opportunities) >= 1
