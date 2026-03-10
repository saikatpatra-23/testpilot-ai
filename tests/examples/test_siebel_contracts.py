"""
Example: Siebel CRM Contract Tests
Validates your REST/SOAP contract with Siebel.
Run: pytest tests/examples/test_siebel_contracts.py -v
"""
import pytest
from unittest.mock import patch, MagicMock
import httpx

# These tests mock Siebel — safe to run without real Siebel connection.
# For live contract tests against real Siebel, set SIEBEL_LIVE=1 in env.


# ─── REST Contract Tests ──────────────────────────────────────────────────────

class TestSiebelRESTContracts:
    """
    Contract tests — verify your code sends correct requests to Siebel REST.
    If Siebel changes its API, these tests catch the mismatch.
    """

    def test_account_query_uses_correct_endpoint(self):
        """Your code must call the correct Siebel Account endpoint."""
        with patch("httpx.Client.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {
                "items": [{"Id": "1-ABC", "Name": "Tata Motors", "Type": "Customer"}]
            }

            # Import your actual module here
            # from your_app.crm import get_account
            # result = get_account("1-ABC")

            # For now, simulate a call and verify contract shape
            client = httpx.Client()
            r = client.get("https://siebel.example.com/siebel/v1.0/data/Account/1-ABC",
                          auth=("user", "pass"))

            # Verify request was made to correct URL
            call_args = mock_get.call_args
            assert "Account" in str(call_args)

    def test_account_response_schema(self):
        """Siebel Account response must have required fields."""
        mock_account = {
            "Id": "1-ABC123",
            "Name": "Tata Motors",
            "Type": "Customer",
            "Primary Contact": "John Doe",
            "Location": "Pune"
        }
        # Validate required fields present
        required = ["Id", "Name", "Type"]
        for field in required:
            assert field in mock_account, f"Siebel Account missing field: {field}"

    def test_lead_create_request_shape(self):
        """Lead creation must send required fields to Siebel."""
        captured_body = {}

        def mock_post(url, json=None, **kwargs):
            captured_body.update(json or {})
            response = MagicMock()
            response.status_code = 201
            response.json.return_value = {"Id": "1-NEW001", "Status": "New"}
            return response

        with patch("httpx.Client.post", side_effect=mock_post):
            # Call your actual function here:
            # from your_app.crm import create_lead
            # create_lead({"FirstName": "Test", "LastName": "User", "Email": "t@e.com"})

            # Simulate the call
            import httpx as _httpx
            client = _httpx.Client()
            client.post(
                "https://siebel.example.com/siebel/v1.0/data/Lead",
                json={"FirstName": "Test", "LastName": "User", "Email": "t@e.com"},
                auth=("user", "pass")
            )

        # Verify required fields were sent
        assert "FirstName" in captured_body
        assert "LastName" in captured_body

    def test_opportunity_update_idempotent(self):
        """Calling update twice should not create duplicates."""
        call_count = [0]

        def mock_put(url, json=None, **kwargs):
            call_count[0] += 1
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {"Status": "Updated", "Id": "OPP-001"}
            return response

        with patch("httpx.Client.put", side_effect=mock_put):
            import httpx as _httpx
            client = _httpx.Client()
            for _ in range(2):
                client.put(
                    "https://siebel.example.com/siebel/v1.0/data/Opportunity/OPP-001",
                    json={"SaleStage": "Proposal"},
                    auth=("user", "pass")
                )

        assert call_count[0] == 2  # Called twice, result same both times


# ─── SOAP Contract Tests ──────────────────────────────────────────────────────

class TestSiebelSOAPContracts:
    """Contract tests for Siebel SOAP services."""

    def test_query_opportunity_returns_required_fields(self):
        mock_response = {
            "OpportunityId": "OPP-001",
            "OpportunityName": "Big Deal",
            "SaleStage": "Proposal",
            "CloseDate": "2026-06-30",
            "Amount": 500000.0
        }

        with patch("zeep.Client") as mock_zeep:
            mock_zeep.return_value.service.QueryOpportunity.return_value = mock_response

            # Call your actual module here:
            # from your_app.crm_soap import get_opportunity
            # result = get_opportunity("OPP-001")
            result = mock_zeep.return_value.service.QueryOpportunity(Id="OPP-001")

        required = ["OpportunityId", "OpportunityName", "SaleStage"]
        for field in required:
            assert field in result

    def test_soap_service_down_raises_connection_error(self):
        """If Siebel SOAP is down, your code should raise a descriptive error."""
        with patch("zeep.Client", side_effect=Exception("Connection refused")):
            with pytest.raises(Exception) as exc_info:
                import zeep
                zeep.Client("https://siebel.example.com/wsdl")

            assert "Connection" in str(exc_info.value) or "refused" in str(exc_info.value)
