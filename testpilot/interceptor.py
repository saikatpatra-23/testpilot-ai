"""
TestPilot AI — Chain Interceptor

A pytest fixture + context manager that:
1. Intercepts ALL outbound HTTP calls from your API (SOLR + Siebel)
2. Records which calls were made, in what order, with what params
3. Lets you assert the chain was executed correctly
4. Can replay recorded calls for golden-path regression testing

Usage in your tests:
    from testpilot.interceptor import chain_interceptor, SolrMock, SiebelMock

    def test_search_chain(chain_interceptor):
        chain_interceptor.mock_solr("jobs", results=[{"id": "1", "title": "TPM"}])
        chain_interceptor.mock_siebel("Account", response={"Id": "1-ABC"})

        r = httpx.get("http://localhost:8000/api/search", params={"q": "TPM"})

        assert r.status_code == 200
        assert r.json()["results"][0]["title"] == "TPM"

        # Assert the chain
        chain_interceptor.assert_solr_called_with(collection="jobs", query_contains="TPM")
        chain_interceptor.assert_siebel_called()
        chain_interceptor.assert_call_order(["solr", "siebel"])
"""
import pytest
import httpx
import respx
from typing import Any, Optional
from contextlib import contextmanager


class ChainCall:
    def __init__(self, service: str, url: str, method: str, params: dict, body: Any):
        self.service = service  # "solr", "siebel", "unknown"
        self.url = url
        self.method = method
        self.params = params
        self.body = body

    def __repr__(self):
        return f"ChainCall({self.service} {self.method} {self.url} params={self.params})"


class ChainInterceptor:
    """
    Records all outbound HTTP calls made during a test.
    Use to assert your call chain is correct.
    """

    def __init__(self, solr_base: str = "", siebel_base: str = ""):
        self.solr_base = solr_base.rstrip("/")
        self.siebel_base = siebel_base.rstrip("/")
        self.calls: list[ChainCall] = []
        self._router = respx.MockRouter(assert_all_called=False)

    def _classify(self, url: str) -> str:
        if self.solr_base and self.solr_base in url:
            return "solr"
        if self.siebel_base and self.siebel_base in url:
            return "siebel"
        if "solr" in url.lower() or ":8983" in url:
            return "solr"
        if "siebel" in url.lower():
            return "siebel"
        return "unknown"

    def mock_solr(
        self,
        collection: str,
        results: list = None,
        num_found: int = None,
        status_code: int = 200
    ) -> "ChainInterceptor":
        """Mock a SOLR collection response."""
        docs = results or []
        response_body = {
            "response": {
                "numFound": num_found if num_found is not None else len(docs),
                "docs": docs
            },
            "responseHeader": {"status": 0}
        }
        url_pattern = f"{self.solr_base}/{collection}/select" if self.solr_base else None

        def side_effect(request):
            params = dict(request.url.params)
            self.calls.append(ChainCall("solr", str(request.url), request.method, params, None))
            return httpx.Response(status_code, json=response_body)

        if url_pattern:
            self._router.get(url_pattern).mock(side_effect=side_effect)
        else:
            self._router.get(respx.pattern.M(url__contains=f"/{collection}/select")).mock(side_effect=side_effect)

        return self

    def mock_solr_empty(self, collection: str) -> "ChainInterceptor":
        return self.mock_solr(collection, results=[], num_found=0)

    def mock_solr_error(self, collection: str, status_code: int = 500) -> "ChainInterceptor":
        return self.mock_solr(collection, results=[], status_code=status_code)

    def mock_siebel(
        self,
        resource: str,
        response: Any = None,
        method: str = "GET",
        status_code: int = 200
    ) -> "ChainInterceptor":
        """Mock a Siebel REST endpoint."""
        response_body = response or {"items": []}

        def side_effect(request):
            body = None
            try:
                body = request.content and request.read()
            except Exception:
                pass
            self.calls.append(ChainCall("siebel", str(request.url), request.method,
                                         dict(request.url.params), body))
            return httpx.Response(status_code, json=response_body)

        pattern = f"{self.siebel_base}/{resource}" if self.siebel_base else None
        if pattern:
            if method == "GET":
                self._router.get(url__startswith=pattern).mock(side_effect=side_effect)
            elif method == "POST":
                self._router.post(url__startswith=pattern).mock(side_effect=side_effect)
            else:
                self._router.route(method=method, url__startswith=pattern).mock(side_effect=side_effect)
        else:
            self._router.route(url__contains=resource).mock(side_effect=side_effect)

        return self

    def mock_siebel_down(self) -> "ChainInterceptor":
        """Simulate Siebel being unreachable."""
        def side_effect(request):
            self.calls.append(ChainCall("siebel", str(request.url), request.method, {}, None))
            raise httpx.ConnectError("Siebel unreachable")

        if self.siebel_base:
            self._router.route(url__contains=self.siebel_base).mock(side_effect=side_effect)
        else:
            self._router.route(url__contains="siebel").mock(side_effect=side_effect)
        return self

    # ── Assertions ──────────────────────────────────────────────────────────

    def assert_solr_called(self, times: int = None):
        solr_calls = [c for c in self.calls if c.service == "solr"]
        if times is not None:
            assert len(solr_calls) == times, \
                f"Expected SOLR called {times} times, got {len(solr_calls)}"
        else:
            assert len(solr_calls) > 0, "Expected SOLR to be called, but it wasn't"

    def assert_solr_not_called(self):
        solr_calls = [c for c in self.calls if c.service == "solr"]
        assert len(solr_calls) == 0, \
            f"Expected SOLR NOT to be called, but it was called {len(solr_calls)} times"

    def assert_solr_called_with(self, collection: str = None, query_contains: str = None):
        solr_calls = [c for c in self.calls if c.service == "solr"]
        assert solr_calls, "SOLR was never called"
        call = solr_calls[-1]  # last call
        if collection:
            assert collection in call.url, \
                f"Expected SOLR collection '{collection}' in URL '{call.url}'"
        if query_contains:
            q_param = call.params.get("q", "")
            assert query_contains.lower() in q_param.lower(), \
                f"Expected SOLR query to contain '{query_contains}', got '{q_param}'"

    def assert_siebel_called(self, times: int = None):
        siebel_calls = [c for c in self.calls if c.service == "siebel"]
        if times is not None:
            assert len(siebel_calls) == times, \
                f"Expected Siebel called {times} times, got {len(siebel_calls)}"
        else:
            assert len(siebel_calls) > 0, "Expected Siebel to be called, but it wasn't"

    def assert_siebel_not_called(self):
        siebel_calls = [c for c in self.calls if c.service == "siebel"]
        assert len(siebel_calls) == 0, \
            f"Expected Siebel NOT to be called, but it was called {len(siebel_calls)} times"

    def assert_call_order(self, order: list[str]):
        """Assert services were called in the given order. e.g. ['solr', 'siebel']"""
        actual_order = [c.service for c in self.calls if c.service in order]
        # Deduplicate consecutive same-service calls
        deduped = []
        for s in actual_order:
            if not deduped or deduped[-1] != s:
                deduped.append(s)
        assert deduped == order, \
            f"Expected call order {order}, got {deduped}\nAll calls: {self.calls}"

    def assert_siebel_called_after_solr(self):
        self.assert_call_order(["solr", "siebel"])

    def call_summary(self) -> str:
        if not self.calls:
            return "No external calls made"
        return " → ".join(f"{c.service}({c.url.split('/')[-1]})" for c in self.calls)

    def __enter__(self):
        self._router.__enter__()
        return self

    def __exit__(self, *args):
        self._router.__exit__(*args)


@pytest.fixture
def chain_interceptor(request):
    """
    Pytest fixture. Use in your tests:

        def test_my_chain(chain_interceptor):
            chain_interceptor.mock_solr("jobs", results=[...])
            chain_interceptor.mock_siebel("Account", response={...})
            ...
            chain_interceptor.assert_call_order(["solr", "siebel"])
    """
    import os
    # Try to load from config if available
    try:
        from .config import load_config
        cfg = load_config()
        solr_base = cfg.get("solr", {}).get("base_url", "")
        siebel_base = cfg.get("siebel", {}).get("rest", {}).get("base_url", "")
    except Exception:
        solr_base = os.getenv("SOLR_URL", "")
        siebel_base = os.getenv("SIEBEL_URL", "")

    interceptor = ChainInterceptor(solr_base=solr_base, siebel_base=siebel_base)
    with interceptor:
        yield interceptor


@contextmanager
def intercept_chain(solr_base: str = "", siebel_base: str = ""):
    """Context manager version for non-pytest usage."""
    interceptor = ChainInterceptor(solr_base=solr_base, siebel_base=siebel_base)
    with interceptor:
        yield interceptor
