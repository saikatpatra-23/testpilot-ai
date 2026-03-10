"""
TestPilot AI — Siebel SOAP Adapter
Contract testing for Siebel SOAP services.
"""
from unittest.mock import MagicMock, patch
from contextlib import contextmanager


@contextmanager
def mock_siebel_soap(service_responses: dict):
    """
    Context manager to mock Siebel SOAP calls.

    Usage:
        with mock_siebel_soap({
            "QueryOpportunity": {"Id": "OPP-001", "Name": "Big Deal"},
            "UpdateOpportunity": {"Status": "Success"}
        }) as mock_client:
            result = your_module.get_opportunity("OPP-001")
            assert result["Id"] == "OPP-001"
    """
    mock_service = MagicMock()
    for method_name, return_value in service_responses.items():
        getattr(mock_service, method_name).return_value = return_value

    mock_client = MagicMock()
    mock_client.service = mock_service

    with patch("zeep.Client", return_value=mock_client):
        yield mock_client


def validate_soap_envelope(xml_str: str) -> bool:
    """Basic validation that a SOAP request is well-formed."""
    required_tags = ["Envelope", "Body"]
    return all(tag in xml_str for tag in required_tags)
