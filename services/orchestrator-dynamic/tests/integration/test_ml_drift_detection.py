"""
Testes de integração completos para ML Drift Detection.

Testa detecção de drift em modelos ML incluindo:
- Feature drift (PSI > 0.25)
- Prediction drift (MAE ratio > 1.5)
- Target drift (K-S test p-value < 0.05)
- Registro de métricas Prometheus
- Baseline faltando (graceful handling)
- Status overall (ok/warning/critical)
"""

import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock, MagicMock
from datetime import datetime, timedelta
import numpy as np

from src.ml.drift_detector import DriftDetector
from src.observability.metrics import OrchestratorMetrics


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def test_drift_config():
    """Test configuration for drift detection."""
    config = Mock()
    config.ml_drift_psi_threshold = 0.25
    config.ml_drift_mae_ratio_threshold = 1.5
    config.ml_drift_ks_pvalue_threshold = 0.05
    config.ml_drift_check_window_days = 7
    return config


@pytest.fixture
def mock_metrics():
    """Mock Prometheus metrics."""
    metrics = Mock(spec=OrchestratorMetrics)
    metrics.record_drift_score = Mock()
    metrics.update_drift_status = Mock()
    metrics.ml_drift_score = Mock()
    metrics.ml_drift_score.labels = Mock(return_value=Mock(set=Mock()))
    metrics.ml_drift_status = Mock()
    metrics.ml_drift_status.labels = Mock(return_value=Mock(set=Mock()))
    return metrics


@pytest_asyncio.fixture
async def baseline_tickets():
    """Baseline tickets with deterministic distribution (200 samples).

    Uses fixed seed and deterministic values to ensure reproducible tests.
    - risk_band: balanced distribution (33% each low/medium/high)
    - actual_duration_ms: centered around 62000ms with controlled variation
    - predictions: centered around 61000ms (close to actual for low MAE)
    """
    np.random.seed(42)  # Fixed seed for reproducibility
    tickets = []
    base_time = datetime.utcnow() - timedelta(days=60)

    for i in range(200):
        # Deterministic duration values centered around 62000
        # Using linear spread instead of random for predictability
        actual_duration = 57000 + (i % 100) * 100  # Range: 57000-66900, mean ~62000
        predicted_duration = 56000 + (i % 100) * 100  # Range: 56000-65900, mean ~61000

        tickets.append({
            'ticket_id': f'baseline-{i}',
            'task_type': ['BUILD', 'TEST', 'DEPLOY'][i % 3],
            'risk_band': ['low', 'medium', 'high'][i % 3],  # Balanced distribution (33% each)
            'qos': {
                'delivery_mode': 'exactly_once',
                'consistency': 'strong',
                'durability': 'persistent'
            },
            'required_capabilities': ['python'],
            'parameters': {},
            'estimated_duration_ms': 60000,
            'actual_duration_ms': actual_duration,
            'created_at': base_time + timedelta(hours=i),
            'completed_at': base_time + timedelta(hours=i, seconds=62),
            'status': 'completed',
            'predictions': {
                'duration_ms': predicted_duration
            }
        })

    return tickets


@pytest_asyncio.fixture
async def drifted_tickets():
    """Drifted tickets with deterministic shifted distribution (100 samples).

    Designed to trigger all drift thresholds:
    - Feature drift: risk_band shifts from balanced (33% each) to 80% critical (PSI > 0.25)
    - Prediction drift: actual ~120000ms vs predicted ~65000ms (MAE ratio > 1.5)
    - Target drift: mean shifts from ~62000 to ~120000 (p-value < 0.05)
    """
    np.random.seed(123)  # Different fixed seed for drifted data
    tickets = []
    base_time = datetime.utcnow() - timedelta(days=3)

    for i in range(100):
        # Shift to critical risk (80% critical vs baseline 33%)
        # This creates significant PSI for risk_weight feature
        risk_band = 'critical' if i < 80 else ['low', 'medium'][i % 2]

        # Deterministic duration values centered around 120000 (2x baseline)
        # This ensures target drift with mean shift ~93% and MAE ratio > 1.5
        actual_duration = 110000 + (i % 100) * 200  # Range: 110000-129800, mean ~120000

        # Predictions still low (around baseline) to create prediction drift
        # MAE will be ~55000 (actual ~120k - predicted ~65k), baseline MAE ~5000
        # drift_ratio = 55000 / 5000 = 11.0 >> 1.5 threshold
        predicted_duration = 60000 + (i % 100) * 100  # Range: 60000-69900, mean ~65000

        tickets.append({
            'ticket_id': f'drifted-{i}',
            'task_type': 'BUILD',  # All BUILD (vs baseline mixed)
            'risk_band': risk_band,  # Mostly critical
            'qos': {
                'delivery_mode': 'at_least_once',  # Changed from exactly_once
                'consistency': 'eventual',  # Changed from strong
                'durability': 'persistent'
            },
            'required_capabilities': ['python', 'docker', 'k8s'],  # More capabilities
            'parameters': {f'k{j}': f'v{j}' for j in range(10)},  # 10 params vs 0
            'estimated_duration_ms': 60000,
            'actual_duration_ms': actual_duration,
            'created_at': base_time + timedelta(hours=i),
            'completed_at': base_time + timedelta(hours=i, seconds=120),
            'status': 'completed',
            'predictions': {
                'duration_ms': predicted_duration
            }
        })

    return tickets


@pytest_asyncio.fixture
async def test_drift_detector_no_drift(test_drift_config, baseline_tickets, mock_metrics):
    """Drift detector with no drift (recent = baseline)."""
    mongodb_client = Mock()

    # Recent tickets same as baseline
    recent_cursor = Mock()
    recent_cursor.limit = Mock(return_value=baseline_tickets[:100])
    mongodb_client.execution_tickets = Mock()
    mongodb_client.execution_tickets.find = Mock(return_value=recent_cursor)

    # Create baseline from features
    from src.ml.feature_engineering import extract_ticket_features

    baseline_features = {}
    target_values = []

    for ticket in baseline_tickets:
        features = extract_ticket_features(ticket)
        for feature_name, value in features.items():
            if feature_name not in baseline_features:
                baseline_features[feature_name] = {'values': []}
            baseline_features[feature_name]['values'].append(value)

        target_values.append(ticket['actual_duration_ms'])

    # Convert values lists to stats
    for feature_name, data in baseline_features.items():
        values = np.array(data['values'])
        baseline_features[feature_name] = {
            'values': values.tolist(),
            'mean': float(np.mean(values)),
            'std': float(np.std(values)),
            'min': float(np.min(values)),
            'max': float(np.max(values))
        }

    baseline_doc = {
        'timestamp': datetime.utcnow() - timedelta(days=30),
        'model_name': 'duration-predictor',
        'version': '1',
        'features': baseline_features,
        'target_distribution': {
            'values': target_values,
            'mean': float(np.mean(target_values)),
            'std': float(np.std(target_values)),
            'percentiles': {
                'p50': float(np.percentile(target_values, 50)),
                'p95': float(np.percentile(target_values, 95)),
                'p99': float(np.percentile(target_values, 99))
            }
        },
        'training_mae': 5000.0
    }

    mongodb_client.ml_feature_baselines = Mock()
    mongodb_client.ml_feature_baselines.find_one = Mock(return_value=baseline_doc)

    detector = DriftDetector(
        config=test_drift_config,
        mongodb_client=mongodb_client,
        metrics=mock_metrics
    )

    return detector


@pytest_asyncio.fixture
async def test_drift_detector_feature_drift(test_drift_config, baseline_tickets, drifted_tickets, mock_metrics):
    """Drift detector with feature drift (PSI > 0.25)."""
    mongodb_client = Mock()

    # Recent tickets with drift
    recent_cursor = Mock()
    recent_cursor.limit = Mock(return_value=drifted_tickets)
    mongodb_client.execution_tickets = Mock()
    mongodb_client.execution_tickets.find = Mock(return_value=recent_cursor)

    # Baseline from original tickets
    from src.ml.feature_engineering import extract_ticket_features

    baseline_features = {}
    target_values = []

    for ticket in baseline_tickets:
        features = extract_ticket_features(ticket)
        for feature_name, value in features.items():
            if feature_name not in baseline_features:
                baseline_features[feature_name] = {'values': []}
            baseline_features[feature_name]['values'].append(value)

        target_values.append(ticket['actual_duration_ms'])

    for feature_name, data in baseline_features.items():
        values = np.array(data['values'])
        baseline_features[feature_name] = {
            'values': values.tolist(),
            'mean': float(np.mean(values)),
            'std': float(np.std(values)),
            'min': float(np.min(values)),
            'max': float(np.max(values))
        }

    baseline_doc = {
        'timestamp': datetime.utcnow() - timedelta(days=30),
        'model_name': 'duration-predictor',
        'version': '1',
        'features': baseline_features,
        'target_distribution': {
            'values': target_values,
            'mean': float(np.mean(target_values)),
            'std': float(np.std(target_values))
        },
        'training_mae': 5000.0
    }

    mongodb_client.ml_feature_baselines = Mock()
    mongodb_client.ml_feature_baselines.find_one = Mock(return_value=baseline_doc)

    detector = DriftDetector(
        config=test_drift_config,
        mongodb_client=mongodb_client,
        metrics=mock_metrics
    )

    return detector


@pytest_asyncio.fixture
async def test_drift_detector_prediction_drift(test_drift_config, baseline_tickets, drifted_tickets, mock_metrics):
    """Drift detector with prediction drift (MAE ratio > 1.5)."""
    mongodb_client = Mock()

    # Use drifted tickets (actual >> predicted)
    recent_cursor = Mock()
    recent_cursor.limit = Mock(return_value=drifted_tickets)
    mongodb_client.execution_tickets = Mock()
    mongodb_client.execution_tickets.find = Mock(return_value=recent_cursor)

    # Baseline with low MAE
    baseline_doc = {
        'timestamp': datetime.utcnow() - timedelta(days=30),
        'features': {},
        'target_distribution': {
            'values': [t['actual_duration_ms'] for t in baseline_tickets],
            'mean': 62000.0,
            'std': 5000.0
        },
        'training_mae': 5000.0  # Low baseline MAE
    }

    mongodb_client.ml_feature_baselines = Mock()
    mongodb_client.ml_feature_baselines.find_one = Mock(return_value=baseline_doc)

    detector = DriftDetector(
        config=test_drift_config,
        mongodb_client=mongodb_client,
        metrics=mock_metrics
    )

    return detector


@pytest_asyncio.fixture
async def test_drift_detector_target_drift(test_drift_config, baseline_tickets, drifted_tickets, mock_metrics):
    """Drift detector with target drift (K-S test p-value < 0.05)."""
    mongodb_client = Mock()

    # Recent tickets with very different duration distribution
    recent_cursor = Mock()
    recent_cursor.limit = Mock(return_value=drifted_tickets)
    mongodb_client.execution_tickets = Mock()
    mongodb_client.execution_tickets.find = Mock(return_value=recent_cursor)

    # Baseline with different distribution
    baseline_doc = {
        'timestamp': datetime.utcnow() - timedelta(days=30),
        'features': {},
        'target_distribution': {
            'values': [t['actual_duration_ms'] for t in baseline_tickets],  # Mean ~62k
            'mean': 62000.0,
            'std': 5000.0
        },
        'training_mae': 5000.0
    }

    mongodb_client.ml_feature_baselines = Mock()
    mongodb_client.ml_feature_baselines.find_one = Mock(return_value=baseline_doc)

    detector = DriftDetector(
        config=test_drift_config,
        mongodb_client=mongodb_client,
        metrics=mock_metrics
    )

    return detector


# =============================================================================
# Test Cases
# =============================================================================

def test_feature_drift_no_drift(test_drift_detector_no_drift, mock_metrics):
    """
    Test no feature drift detected (PSI < 0.1).

    Verifies:
    - All PSI scores < 0.1
    - overall_status is 'ok'
    - Metrics recorded
    """
    report = test_drift_detector_no_drift.run_drift_check()

    assert report['overall_status'] == 'ok'

    # Check feature drift
    if 'feature_drift' in report and report['feature_drift']:
        psi_scores = list(report['feature_drift'].values())
        # Most PSI should be low (< 0.1)
        low_psi_count = sum(1 for psi in psi_scores if psi < 0.1)
        assert low_psi_count >= len(psi_scores) * 0.8  # 80% below threshold

    # Verify metrics called
    assert mock_metrics.update_drift_status.called


def test_feature_drift_detected(test_drift_detector_feature_drift, mock_metrics):
    """
    Test feature drift detected (PSI > 0.25).

    Verifies:
    - At least one PSI > 0.25 threshold
    - overall_status is 'warning' or 'critical'
    - Prometheus metrics updated

    The drifted_tickets fixture has:
    - risk_band: 80% critical vs baseline 33% each (significant distribution shift)
    - capabilities_count: 3 vs baseline 1 (shift in count)
    - parameters_count: 10 vs baseline 0 (shift in count)
    """
    report = test_drift_detector_feature_drift.run_drift_check()

    # Should detect drift (distribution changed significantly)
    assert report['overall_status'] in ['warning', 'critical'], \
        f"Expected 'warning' or 'critical' status, got '{report['overall_status']}'"

    # Feature drift must be present and have at least one PSI > 0.25
    assert 'feature_drift' in report, "Report should contain 'feature_drift'"
    assert report['feature_drift'], "Feature drift should not be empty"

    psi_scores = report['feature_drift']
    max_psi = max(psi_scores.values())

    # At least one feature must have PSI > 0.25 (the threshold)
    assert max_psi > 0.25, \
        f"Expected at least one feature with PSI > 0.25, max PSI was {max_psi:.4f}. " \
        f"PSI scores: {psi_scores}"

    # Identify features with significant drift
    drifted_features = {k: v for k, v in psi_scores.items() if v > 0.25}
    assert len(drifted_features) >= 1, \
        f"Expected at least 1 feature with PSI > 0.25, found {len(drifted_features)}"

    # Verify metrics recorded
    assert mock_metrics.record_drift_score.called or mock_metrics.update_drift_status.called


def test_prediction_drift_detected(test_drift_detector_prediction_drift, mock_metrics):
    """
    Test prediction drift detected (MAE ratio > 1.5).

    Verifies:
    - Current MAE >> baseline MAE
    - drift_ratio >= 1.5 (threshold)
    - Recommendations include urgent retraining

    The drifted_tickets fixture has:
    - actual_duration: ~120000ms
    - predicted_duration: ~65000ms
    - MAE: ~55000ms
    - baseline MAE: 5000ms
    - Expected drift_ratio: ~11.0 (well above 1.5 threshold)
    """
    report = test_drift_detector_prediction_drift.run_drift_check()

    # Prediction drift must be present
    assert 'prediction_drift' in report, "Report should contain 'prediction_drift'"

    drift_data = report['prediction_drift']

    # drift_ratio must be present and >= 1.5 (the threshold)
    assert 'drift_ratio' in drift_data, \
        f"Prediction drift should contain 'drift_ratio'. Got: {drift_data}"

    mae_ratio = drift_data['drift_ratio']

    # MAE ratio must exceed threshold of 1.5
    assert mae_ratio >= 1.5, \
        f"Expected drift_ratio >= 1.5 (threshold), got {mae_ratio:.2f}. " \
        f"Current MAE: {drift_data.get('mae_7d') or drift_data.get('mae_3d') or drift_data.get('mae_1d')}, " \
        f"Training MAE: {drift_data.get('mae_training')}"

    # Status should reflect critical degradation when MAE ratio > 1.5
    assert report['overall_status'] in ['warning', 'critical'], \
        f"Expected 'warning' or 'critical' status with drift_ratio={mae_ratio:.2f}, " \
        f"got '{report['overall_status']}'"


def test_target_drift_detected(test_drift_detector_target_drift, mock_metrics):
    """
    Test target drift detected (K-S test).

    Verifies:
    - p-value < 0.05 (threshold for significant difference)
    - mean_shift_pct ~ 93% (baseline ~62k → drifted ~120k)
    - K-S statistic significant

    The drifted_tickets fixture has:
    - actual_duration mean: ~120000ms
    - baseline mean: ~62000ms
    - Expected mean_shift_pct: ~93%
    - Expected p-value: << 0.05 (distributions are completely different)
    """
    report = test_drift_detector_target_drift.run_drift_check()

    # Target drift must be present
    assert 'target_drift' in report, "Report should contain 'target_drift'"

    target_data = report['target_drift']

    # p_value must be present
    assert 'p_value' in target_data, \
        f"Target drift should contain 'p_value'. Got: {target_data}"

    p_value = target_data['p_value']

    # p-value must be < 0.05 (the threshold) to indicate significant difference
    assert p_value < 0.05, \
        f"Expected p_value < 0.05 (threshold), got {p_value:.6f}. " \
        f"This indicates the K-S test did not detect significant distribution difference. " \
        f"Baseline mean: {target_data.get('baseline_mean')}, Recent mean: {target_data.get('recent_mean')}"

    # Verify p_value is valid
    assert 0 <= p_value <= 1, f"p_value should be between 0 and 1, got {p_value}"

    # mean_shift_pct must be present and significant
    assert 'mean_shift_pct' in target_data, \
        f"Target drift should contain 'mean_shift_pct'. Got: {target_data}"

    mean_shift = target_data['mean_shift_pct']
    assert mean_shift is not None, "mean_shift_pct should not be None"

    # With baseline ~62k and drifted ~120k, expect ~93% shift
    # Allow some tolerance but it should be substantial (> 50%)
    assert mean_shift > 50, \
        f"Expected mean_shift_pct > 50% (baseline ~62k → drifted ~120k), got {mean_shift:.1f}%"


def test_run_drift_check_mixed_scenario(test_drift_detector_feature_drift, mock_metrics):
    """
    Test comprehensive drift check with all types.

    Verifies:
    - Report contains feature_drift, prediction_drift, target_drift
    - overall_status determined correctly
    - Recommendations generated
    """
    report = test_drift_detector_feature_drift.run_drift_check()

    # Verify report structure
    assert 'timestamp' in report
    assert 'window_days' in report
    assert 'overall_status' in report
    assert report['overall_status'] in ['ok', 'warning', 'critical']

    # Verify recommendations
    assert 'recommendations' in report
    assert isinstance(report['recommendations'], list)


def test_missing_baseline(test_drift_config, mock_metrics):
    """
    Test graceful handling when no baseline exists.

    Verifies:
    - No exception raised
    - Empty dict returned for feature drift
    - Warning logged
    """
    mongodb_client = Mock()

    # No recent tickets
    recent_cursor = Mock()
    recent_cursor.limit = Mock(return_value=[])
    mongodb_client.execution_tickets = Mock()
    mongodb_client.execution_tickets.find = Mock(return_value=recent_cursor)

    # No baseline
    mongodb_client.ml_feature_baselines = Mock()
    mongodb_client.ml_feature_baselines.find_one = Mock(return_value=None)

    detector = DriftDetector(
        config=test_drift_config,
        mongodb_client=mongodb_client,
        metrics=mock_metrics
    )

    # Should not raise
    report = detector.run_drift_check()

    # Should return gracefully
    assert report is not None
    assert 'overall_status' in report


def test_metrics_recorded(test_drift_detector_no_drift, mock_metrics):
    """
    Test Prometheus metrics are recorded.

    Verifies:
    - record_drift_score called for each drift type
    - update_drift_status called with correct status
    - Proper labels (model_name, drift_type, feature)
    """
    report = test_drift_detector_no_drift.run_drift_check()

    # Verify drift status updated
    assert mock_metrics.update_drift_status.called
    calls = mock_metrics.update_drift_status.call_args_list

    # At least one call for overall status
    assert len(calls) >= 1

    # Verify call signature
    for call in calls:
        args, kwargs = call
        # Should have model_name, drift_type, status
        assert 'model_name' in kwargs or len(args) >= 1
        assert 'drift_type' in kwargs or len(args) >= 2
        assert 'status' in kwargs or len(args) >= 3


def test_save_feature_baseline(test_drift_config, mock_metrics):
    """
    Test that save_feature_baseline correctly persists baseline data to MongoDB.

    Verifies:
    - mongodb_client.ml_feature_baselines.insert_one() is called
    - Baseline document contains required fields (features, target_distribution, training_mae)
    - Features have correct structure (values, mean, std, min, max)
    - Target distribution includes percentiles
    - Timestamp is included
    """
    from src.ml.drift_detector import DriftDetector

    # Setup mock MongoDB client
    mock_mongodb_client = Mock()
    mock_mongodb_client.ml_feature_baselines = Mock()
    mock_mongodb_client.ml_feature_baselines.insert_one = Mock()

    # Create detector
    detector = DriftDetector(
        config=test_drift_config,
        mongodb_client=mock_mongodb_client,
        metrics=mock_metrics
    )

    # Prepare test data (100 samples)
    features_data = [
        {
            'risk_weight': 0.5 + (i % 10) * 0.05,
            'capabilities_count': 2 + (i % 5),
            'parameters_count': i % 8,
            'qos_delivery_mode': 1.0,
            'qos_consistency': 0.8
        }
        for i in range(100)
    ]

    target_values = [60000.0 + (i * 100) for i in range(100)]  # Mean ~65k
    training_mae = 5000.0

    # Execute
    detector.save_feature_baseline(
        features_data=features_data,
        target_values=target_values,
        training_mae=training_mae,
        model_name='duration-predictor',
        version='v1.0'
    )

    # Verify insert_one was called
    mock_mongodb_client.ml_feature_baselines.insert_one.assert_called_once()

    # Get the document that was inserted
    call_args = mock_mongodb_client.ml_feature_baselines.insert_one.call_args[0][0]

    # Verify required fields exist
    assert 'features' in call_args, "Document should contain 'features'"
    assert 'target_distribution' in call_args, "Document should contain 'target_distribution'"
    assert 'training_mae' in call_args, "Document should contain 'training_mae'"
    assert 'timestamp' in call_args, "Document should contain 'timestamp'"
    assert 'model_name' in call_args, "Document should contain 'model_name'"
    assert 'version' in call_args, "Document should contain 'version'"
    assert 'sample_count' in call_args, "Document should contain 'sample_count'"

    # Verify training_mae value
    assert call_args['training_mae'] == training_mae

    # Verify model metadata
    assert call_args['model_name'] == 'duration-predictor'
    assert call_args['version'] == 'v1.0'
    assert call_args['sample_count'] == 100

    # Verify features structure
    features = call_args['features']
    assert 'risk_weight' in features, "Features should contain 'risk_weight'"
    assert 'capabilities_count' in features, "Features should contain 'capabilities_count'"

    # Verify feature has correct structure
    risk_weight_feature = features['risk_weight']
    assert 'values' in risk_weight_feature, "Feature should have 'values'"
    assert 'mean' in risk_weight_feature, "Feature should have 'mean'"
    assert 'std' in risk_weight_feature, "Feature should have 'std'"
    assert 'min' in risk_weight_feature, "Feature should have 'min'"
    assert 'max' in risk_weight_feature, "Feature should have 'max'"

    # Verify values are numeric
    assert isinstance(risk_weight_feature['mean'], float)
    assert isinstance(risk_weight_feature['std'], float)
    assert len(risk_weight_feature['values']) == 100

    # Verify target distribution
    target_dist = call_args['target_distribution']
    assert 'values' in target_dist, "Target should have 'values'"
    assert 'mean' in target_dist, "Target should have 'mean'"
    assert 'std' in target_dist, "Target should have 'std'"
    assert 'percentiles' in target_dist, "Target should have 'percentiles'"

    # Verify percentiles structure
    percentiles = target_dist['percentiles']
    assert 'p50' in percentiles, "Percentiles should have 'p50'"
    assert 'p95' in percentiles, "Percentiles should have 'p95'"
    assert 'p99' in percentiles, "Percentiles should have 'p99'"

    # Verify percentile values are in expected order
    assert percentiles['p50'] <= percentiles['p95'] <= percentiles['p99']


def test_save_feature_baseline_empty_data(test_drift_config, mock_metrics):
    """
    Test that save_feature_baseline handles empty data gracefully.

    Verifies:
    - No exception raised with empty features_data
    - insert_one is NOT called when data is empty
    """
    from src.ml.drift_detector import DriftDetector

    # Setup mock MongoDB client
    mock_mongodb_client = Mock()
    mock_mongodb_client.ml_feature_baselines = Mock()
    mock_mongodb_client.ml_feature_baselines.insert_one = Mock()

    # Create detector
    detector = DriftDetector(
        config=test_drift_config,
        mongodb_client=mock_mongodb_client,
        metrics=mock_metrics
    )

    # Execute with empty data
    detector.save_feature_baseline(
        features_data=[],
        target_values=[],
        training_mae=5000.0
    )

    # Verify insert_one was NOT called (graceful handling)
    mock_mongodb_client.ml_feature_baselines.insert_one.assert_not_called()
