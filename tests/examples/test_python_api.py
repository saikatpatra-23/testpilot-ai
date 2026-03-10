"""
Example: Python Backend API Tests
Replace base_url and endpoints with your actual API.
Run: pytest tests/examples/test_python_api.py -v
"""
import pytest
import httpx
from unittest.mock import patch, MagicMock

BASE_URL = "http://localhost:8000"


# ─── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """HTTP client for API calls."""
    with httpx.Client(base_url=BASE_URL, timeout=10) as c:
        yield c


@pytest.fixture
def auth_headers():
    """Authenticated request headers. Replace with your actual auth."""
    return {"Authorization": "Bearer test-token-replace-me"}


# ─── Health Check ────────────────────────────────────────────────────────────

class TestHealthCheck:
    def test_health_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_response_has_status(self, client):
        r = client.get("/health")
        data = r.json()
        assert "status" in data
        assert data["status"] in ("ok", "healthy", "up")


# ─── Authentication ──────────────────────────────────────────────────────────

class TestAuth:
    def test_login_valid_credentials(self, client):
        r = client.post("/auth/login", json={
            "email": "test@org.com",
            "password": "validpass123"
        })
        # Should return 200 + token
        assert r.status_code in (200, 201)
        data = r.json()
        assert "token" in data or "access_token" in data

    def test_login_wrong_password_returns_401(self, client):
        r = client.post("/auth/login", json={
            "email": "test@org.com",
            "password": "wrongpassword"
        })
        assert r.status_code == 401

    def test_login_missing_email_returns_422(self, client):
        r = client.post("/auth/login", json={"password": "pass123"})
        assert r.status_code == 422

    def test_protected_route_without_auth_returns_401(self, client):
        r = client.get("/api/protected-endpoint")
        assert r.status_code in (401, 403)


# ─── Siebel Integration (mocked) ─────────────────────────────────────────────

class TestSiebelIntegration:
    """
    Tests for your Python code that calls Siebel.
    Always mock Siebel — never hit real Siebel in tests.
    """

    def test_create_lead_calls_siebel_rest(self, client, auth_headers):
        """Your /api/leads endpoint should POST to Siebel."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"Id": "1-ABC123", "Status": "New"}

        with patch("httpx.Client.post", return_value=mock_response):
            r = client.post("/api/leads", json={
                "first_name": "Test",
                "last_name": "User",
                "email": "test@example.com"
            }, headers=auth_headers)

        assert r.status_code in (200, 201)
        data = r.json()
        assert "id" in data or "lead_id" in data

    def test_create_lead_missing_email_returns_422(self, client, auth_headers):
        r = client.post("/api/leads", json={
            "first_name": "Test",
            "last_name": "User"
            # email missing
        }, headers=auth_headers)
        assert r.status_code == 422

    def test_siebel_down_returns_503(self, client, auth_headers):
        """When Siebel is unreachable, API should return 503, not 500."""
        with patch("httpx.Client.post", side_effect=httpx.ConnectError("Siebel down")):
            r = client.post("/api/leads", json={
                "first_name": "Test",
                "last_name": "User",
                "email": "test@example.com"
            }, headers=auth_headers)
        assert r.status_code in (503, 502, 500)


# ─── SOLR Integration (mocked) ───────────────────────────────────────────────

class TestSOLRIntegration:
    """Your Python endpoints that read from SOLR."""

    def test_search_returns_results(self, client):
        mock_solr_response = {
            "response": {
                "numFound": 10,
                "docs": [
                    {"id": "1", "title": "TPM Role", "company": "Tata Motors"}
                ]
            }
        }
        with patch("httpx.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_solr_response

            r = client.get("/api/search", params={"q": "TPM", "city": "Pune"})
            assert r.status_code == 200
            data = r.json()
            assert "results" in data or "docs" in data

    def test_search_empty_query_returns_400(self, client):
        r = client.get("/api/search", params={"q": "", "city": "Pune"})
        assert r.status_code in (400, 422)
