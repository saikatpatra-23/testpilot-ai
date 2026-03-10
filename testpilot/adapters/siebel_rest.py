"""
TestPilot AI — Siebel REST Adapter
Validates your Siebel REST API contract tests.
Plug in your Siebel base URL + auth → run contract tests.
"""
import httpx
from typing import Any


class SiebelRESTClient:
    """Thin client to call Siebel REST API in tests."""

    def __init__(self, base_url: str, username: str, password: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.auth = (username, password)
        self.timeout = timeout
        self._client = httpx.Client(auth=self.auth, timeout=self.timeout, verify=False)

    def get(self, resource: str, **params) -> httpx.Response:
        return self._client.get(f"{self.base_url}/{resource}", params=params)

    def post(self, resource: str, data: dict) -> httpx.Response:
        return self._client.post(
            f"{self.base_url}/{resource}",
            json=data,
            headers={"Content-Type": "application/json"}
        )

    def put(self, resource: str, record_id: str, data: dict) -> httpx.Response:
        return self._client.put(
            f"{self.base_url}/{resource}/{record_id}",
            json=data,
            headers={"Content-Type": "application/json"}
        )

    def close(self):
        self._client.close()


def make_siebel_mock(responses: dict[str, Any]):
    """
    Create a respx mock for Siebel REST endpoints.
    Usage in tests:
        with make_siebel_mock({"Account": [{"Id": "1-ABC", "Name": "Tata"}]}) as mock:
            result = your_function_that_calls_siebel()
            assert result["Id"] == "1-ABC"
    """
    try:
        import respx
    except ImportError:
        raise ImportError("Install respx: pip install respx")

    mock = respx.MockRouter()
    for resource, response_data in responses.items():
        mock.get(url__contains=resource).mock(
            return_value=httpx.Response(200, json={"items": response_data if isinstance(response_data, list) else [response_data]})
        )
        mock.post(url__contains=resource).mock(
            return_value=httpx.Response(201, json=response_data if isinstance(response_data, dict) else response_data[0])
        )
        mock.put(url__contains=resource).mock(
            return_value=httpx.Response(200, json={"Status": "Success"})
        )
    return mock
