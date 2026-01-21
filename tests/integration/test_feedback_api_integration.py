"""
Integration tests for Feedback API across all specialists.

Tests the feedback API endpoints including:
- Health check endpoint
- Feedback submission with authentication
- Feedback statistics
- PII anonymization
"""
import pytest
import requests
import jwt
from datetime import datetime, timedelta
from typing import Optional
import os

SPECIALISTS = [
    "specialist-technical",
    "specialist-business",
    "specialist-architecture",
    "specialist-behavior",
    "specialist-evolution"
]

# Configuration from environment
NAMESPACE = os.getenv("K8S_NAMESPACE", "neural-hive-mind")
JWT_SECRET = os.getenv("JWT_SECRET_KEY", "test-secret-key-for-development")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
USE_LOCAL = os.getenv("USE_LOCAL", "false").lower() == "true"


def get_base_url(specialist: str) -> str:
    """Get the base URL for a specialist service."""
    if USE_LOCAL:
        # For local testing, use localhost with different ports
        port_map = {
            "specialist-technical": 8001,
            "specialist-business": 8002,
            "specialist-architecture": 8003,
            "specialist-behavior": 8004,
            "specialist-evolution": 8005
        }
        return f"http://localhost:{port_map.get(specialist, 8000)}"
    else:
        # For Kubernetes testing
        return f"http://{specialist}.{NAMESPACE}.svc.cluster.local:8000"


def generate_jwt_token(
    subject: str = "test-reviewer",
    role: str = "human_expert",
    expires_in_hours: int = 1
) -> str:
    """Generate a valid JWT token for testing."""
    payload = {
        'sub': subject,
        'role': role,
        'exp': datetime.utcnow() + timedelta(hours=expires_in_hours),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


@pytest.fixture
def jwt_token():
    """Generate valid JWT token for testing."""
    return generate_jwt_token()


@pytest.fixture
def admin_jwt_token():
    """Generate admin JWT token for testing."""
    return generate_jwt_token(subject="admin-user", role="admin")


class TestFeedbackHealthEndpoint:
    """Tests for the /feedback/health endpoint."""

    @pytest.mark.parametrize("specialist", SPECIALISTS)
    def test_feedback_health_endpoint_returns_200(self, specialist):
        """Test that feedback health check endpoint returns 200 OK."""
        url = f"{get_base_url(specialist)}/api/v1/feedback/health"

        try:
            response = requests.get(url, timeout=10)
            assert response.status_code == 200

            data = response.json()
            assert 'status' in data
            assert data['status'] in ['healthy', 'degraded', 'unhealthy']

        except requests.exceptions.ConnectionError:
            pytest.skip(f"Cannot connect to {specialist} - service may not be running")

    @pytest.mark.parametrize("specialist", SPECIALISTS)
    def test_feedback_health_returns_specialist_type(self, specialist):
        """Test that health check returns the correct specialist type."""
        url = f"{get_base_url(specialist)}/api/v1/feedback/health"

        try:
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'healthy':
                    assert 'specialist_type' in data
                    expected_type = specialist.replace("specialist-", "")
                    assert data['specialist_type'] == expected_type

        except requests.exceptions.ConnectionError:
            pytest.skip(f"Cannot connect to {specialist} - service may not be running")


class TestFeedbackAuthentication:
    """Tests for feedback API authentication."""

    @pytest.mark.parametrize("specialist", SPECIALISTS)
    def test_submit_feedback_requires_auth(self, specialist):
        """Test that feedback submission requires authentication."""
        url = f"{get_base_url(specialist)}/api/v1/feedback"

        payload = {
            "opinion_id": "test-opinion-123",
            "human_rating": 0.9,
            "human_recommendation": "approve",
            "feedback_notes": "Test feedback"
        }

        try:
            # Without token - should fail with 401
            response = requests.post(url, json=payload, timeout=10)
            assert response.status_code == 401, \
                f"Expected 401 without auth, got {response.status_code}"

        except requests.exceptions.ConnectionError:
            pytest.skip(f"Cannot connect to {specialist} - service may not be running")

    @pytest.mark.parametrize("specialist", SPECIALISTS)
    def test_invalid_jwt_token_rejected(self, specialist):
        """Test that invalid JWT tokens are rejected."""
        url = f"{get_base_url(specialist)}/api/v1/feedback"

        headers = {
            "Authorization": "Bearer invalid-token-here"
        }

        payload = {
            "opinion_id": "test-opinion-123",
            "human_rating": 0.9,
            "human_recommendation": "approve",
            "feedback_notes": "Test feedback"
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            assert response.status_code == 401, \
                f"Expected 401 with invalid token, got {response.status_code}"

        except requests.exceptions.ConnectionError:
            pytest.skip(f"Cannot connect to {specialist} - service may not be running")

    @pytest.mark.parametrize("specialist", SPECIALISTS)
    def test_expired_jwt_token_rejected(self, specialist):
        """Test that expired JWT tokens are rejected."""
        url = f"{get_base_url(specialist)}/api/v1/feedback"

        # Generate expired token
        payload = {
            'sub': 'test-reviewer',
            'role': 'human_expert',
            'exp': datetime.utcnow() - timedelta(hours=1),  # Expired
            'iat': datetime.utcnow() - timedelta(hours=2)
        }
        expired_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

        headers = {
            "Authorization": f"Bearer {expired_token}"
        }

        request_payload = {
            "opinion_id": "test-opinion-123",
            "human_rating": 0.9,
            "human_recommendation": "approve",
            "feedback_notes": "Test feedback"
        }

        try:
            response = requests.post(
                url, json=request_payload, headers=headers, timeout=10
            )
            assert response.status_code == 401, \
                f"Expected 401 with expired token, got {response.status_code}"

        except requests.exceptions.ConnectionError:
            pytest.skip(f"Cannot connect to {specialist} - service may not be running")


class TestFeedbackSubmission:
    """Tests for feedback submission endpoint."""

    @pytest.mark.parametrize("specialist", SPECIALISTS)
    def test_submit_feedback_with_valid_token(self, specialist, jwt_token):
        """Test feedback submission with valid JWT."""
        url = f"{get_base_url(specialist)}/api/v1/feedback"

        headers = {
            "Authorization": f"Bearer {jwt_token}"
        }

        payload = {
            "opinion_id": f"test-opinion-{specialist}-456",
            "human_rating": 0.85,
            "human_recommendation": "approve_with_conditions",
            "feedback_notes": "Good analysis but needs minor adjustments"
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)

            # Should succeed (201) or return 404 if opinion doesn't exist
            assert response.status_code in [201, 404], \
                f"Expected 201 or 404, got {response.status_code}: {response.text}"

            if response.status_code == 201:
                data = response.json()
                assert 'feedback_id' in data
                assert data['opinion_id'] == payload['opinion_id']
                assert data['status'] == 'success'

        except requests.exceptions.ConnectionError:
            pytest.skip(f"Cannot connect to {specialist} - service may not be running")

    @pytest.mark.parametrize("specialist", SPECIALISTS)
    def test_submit_feedback_validates_rating(self, specialist, jwt_token):
        """Test that feedback submission validates rating bounds."""
        url = f"{get_base_url(specialist)}/api/v1/feedback"

        headers = {
            "Authorization": f"Bearer {jwt_token}"
        }

        # Invalid rating > 1.0
        payload = {
            "opinion_id": "test-opinion-123",
            "human_rating": 1.5,  # Invalid: should be 0.0-1.0
            "human_recommendation": "approve",
            "feedback_notes": "Test"
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            assert response.status_code == 422, \
                f"Expected 422 for invalid rating, got {response.status_code}"

        except requests.exceptions.ConnectionError:
            pytest.skip(f"Cannot connect to {specialist} - service may not be running")

    @pytest.mark.parametrize("specialist", SPECIALISTS)
    def test_submit_feedback_validates_recommendation(self, specialist, jwt_token):
        """Test that feedback submission validates recommendation values."""
        url = f"{get_base_url(specialist)}/api/v1/feedback"

        headers = {
            "Authorization": f"Bearer {jwt_token}"
        }

        # Invalid recommendation
        payload = {
            "opinion_id": "test-opinion-123",
            "human_rating": 0.8,
            "human_recommendation": "invalid_recommendation",  # Invalid
            "feedback_notes": "Test"
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            assert response.status_code == 422, \
                f"Expected 422 for invalid recommendation, got {response.status_code}"

        except requests.exceptions.ConnectionError:
            pytest.skip(f"Cannot connect to {specialist} - service may not be running")


class TestFeedbackStatistics:
    """Tests for feedback statistics endpoint."""

    @pytest.mark.parametrize("specialist", SPECIALISTS)
    def test_get_feedback_stats(self, specialist, jwt_token):
        """Test feedback statistics endpoint."""
        specialist_type = specialist.replace("specialist-", "")
        url = f"{get_base_url(specialist)}/api/v1/feedback/stats"

        headers = {
            "Authorization": f"Bearer {jwt_token}"
        }

        params = {
            "specialist_type": specialist_type,
            "window_days": 30
        }

        try:
            response = requests.get(
                url, params=params, headers=headers, timeout=10
            )

            # Stats should return 200 even if no data
            assert response.status_code == 200, \
                f"Expected 200, got {response.status_code}: {response.text}"

            data = response.json()
            assert 'count' in data
            assert isinstance(data['count'], int)
            assert data['count'] >= 0

        except requests.exceptions.ConnectionError:
            pytest.skip(f"Cannot connect to {specialist} - service may not be running")

    @pytest.mark.parametrize("specialist", SPECIALISTS)
    def test_stats_requires_authentication(self, specialist):
        """Test that stats endpoint requires authentication."""
        specialist_type = specialist.replace("specialist-", "")
        url = f"{get_base_url(specialist)}/api/v1/feedback/stats"

        params = {
            "specialist_type": specialist_type,
            "window_days": 30
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            assert response.status_code == 401, \
                f"Expected 401 without auth, got {response.status_code}"

        except requests.exceptions.ConnectionError:
            pytest.skip(f"Cannot connect to {specialist} - service may not be running")


class TestPIIAnonymization:
    """Tests for PII anonymization in feedback notes."""

    @pytest.mark.parametrize("specialist", SPECIALISTS)
    def test_submit_feedback_with_pii(self, specialist, jwt_token):
        """Test that PII in feedback notes is handled properly."""
        url = f"{get_base_url(specialist)}/api/v1/feedback"

        headers = {
            "Authorization": f"Bearer {jwt_token}"
        }

        # Feedback with PII that should be anonymized
        payload = {
            "opinion_id": f"test-opinion-pii-{specialist}",
            "human_rating": 0.75,
            "human_recommendation": "review_required",
            "feedback_notes": "Contact John Doe at john.doe@example.com or call +1-555-123-4567"
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)

            # Should succeed or 404 if opinion doesn't exist
            # PII detection happens asynchronously during storage
            assert response.status_code in [201, 404], \
                f"Expected 201 or 404, got {response.status_code}"

        except requests.exceptions.ConnectionError:
            pytest.skip(f"Cannot connect to {specialist} - service may not be running")


class TestOnlineUpdateTrigger:
    """Tests for online update trigger endpoint."""

    @pytest.mark.parametrize("specialist", SPECIALISTS)
    def test_trigger_online_update_requires_admin(self, specialist, jwt_token):
        """Test that online update trigger requires admin role."""
        url = f"{get_base_url(specialist)}/api/v1/feedback/trigger-online-update"

        # Using regular human_expert token (not admin)
        headers = {
            "Authorization": f"Bearer {jwt_token}"
        }

        try:
            response = requests.post(url, headers=headers, timeout=10)

            # Should be forbidden for non-admin users
            assert response.status_code in [403, 401], \
                f"Expected 403/401 for non-admin, got {response.status_code}"

        except requests.exceptions.ConnectionError:
            pytest.skip(f"Cannot connect to {specialist} - service may not be running")

    @pytest.mark.parametrize("specialist", SPECIALISTS)
    def test_trigger_online_update_with_admin(self, specialist, admin_jwt_token):
        """Test online update trigger with admin credentials."""
        url = f"{get_base_url(specialist)}/api/v1/feedback/trigger-online-update"

        headers = {
            "Authorization": f"Bearer {admin_jwt_token}"
        }

        try:
            response = requests.post(url, headers=headers, timeout=30)

            # Should succeed or return unavailable if ML module not installed
            assert response.status_code in [200, 503], \
                f"Expected 200 or 503, got {response.status_code}"

            if response.status_code == 200:
                data = response.json()
                assert 'status' in data

        except requests.exceptions.ConnectionError:
            pytest.skip(f"Cannot connect to {specialist} - service may not be running")


# Utility function for running tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
