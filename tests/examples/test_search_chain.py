"""
CHAIN TEST EXAMPLE: Search Flow
================================
Real flow in your org:
  User types in React search box → clicks Search
  → GET /api/search?q=TPM&city=Pune
  → backend calls SOLR to find jobs
  → for each result, backend enriches with Siebel CRM data
  → returns enriched list to React

This single test covers the ENTIRE chain.
No isolated SOLR test. No isolated Siebel test.
One test = one business flow.
"""
import pytest
import httpx
from testpilot.interceptor import chain_interceptor  # noqa: F401 (pytest fixture)

BASE_URL = "http://localhost:8000"  # your backend


# ─── Test 1: Happy Path — SOLR returns results → Siebel is called ───────────

def test_search_happy_path(chain_interceptor):
    """
    User searches for TPM jobs.
    SOLR finds 2 jobs → backend calls Siebel to enrich each → returns to React.

    Chain: /api/search → SOLR(jobs) → Siebel(Account) → response
    """
    # ARRANGE: mock dependencies
    chain_interceptor.mock_solr("jobs", results=[
        {"id": "job-001", "title": "Technical Program Manager", "company_id": "ACC-001", "location": "Pune"},
        {"id": "job-002", "title": "Senior TPM",               "company_id": "ACC-002", "location": "Mumbai"},
    ])
    chain_interceptor.mock_siebel("Account", response={
        "items": [{"Id": "ACC-001", "Name": "Tata Motors", "Size": "10000+"}]
    })

    # ACT: call the real API (same as what React frontend calls)
    r = httpx.get(f"{BASE_URL}/api/search", params={"q": "TPM", "city": "Pune"})

    # ASSERT: response to frontend
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert len(data["results"]) == 2
    assert data["results"][0]["title"] == "Technical Program Manager"
    # Company data enriched from Siebel
    assert data["results"][0]["company_name"] == "Tata Motors"

    # ASSERT: the chain happened correctly
    chain_interceptor.assert_solr_called_with(collection="jobs", query_contains="TPM")
    chain_interceptor.assert_siebel_called()
    chain_interceptor.assert_siebel_called_after_solr()  # Siebel MUST be called AFTER SOLR

    print(f"\nChain: {chain_interceptor.call_summary()}")


# ─── Test 2: SOLR Returns Empty → Siebel Must NOT Be Called ─────────────────

def test_search_no_results_skips_siebel(chain_interceptor):
    """
    SOLR returns 0 results.
    Backend should return empty list immediately — Siebel must NOT be called.
    (Don't waste Siebel API quota when there's nothing to enrich.)

    Chain: /api/search → SOLR(jobs) → [empty] → skip Siebel → return []
    """
    chain_interceptor.mock_solr_empty("jobs")

    r = httpx.get(f"{BASE_URL}/api/search", params={"q": "NonexistentJobTitle12345"})

    assert r.status_code == 200
    assert r.json()["results"] == []

    chain_interceptor.assert_solr_called()
    chain_interceptor.assert_siebel_not_called()  # KEY ASSERTION — no Siebel call on empty


# ─── Test 3: SOLR Is Down → API Returns 503, Frontend Gets Error ─────────────

def test_search_solr_down_returns_503(chain_interceptor):
    """
    SOLR is unreachable.
    Backend should NOT crash — return 503 to frontend with a message.
    Siebel must NOT be called (no point without SOLR data).

    Chain: /api/search → SOLR(DOWN) → 503 to React
    """
    chain_interceptor.mock_solr_error("jobs", status_code=500)

    r = httpx.get(f"{BASE_URL}/api/search", params={"q": "TPM"})

    assert r.status_code in (503, 502, 500)
    chain_interceptor.assert_siebel_not_called()


# ─── Test 4: Siebel Is Down → Partial Data Still Returned ────────────────────

def test_search_siebel_down_returns_partial_data(chain_interceptor):
    """
    SOLR works fine, returns jobs.
    Siebel is down during enrichment.
    Backend should return jobs WITHOUT company enrichment (graceful degradation).
    Frontend gets data, just without Siebel-enriched fields.

    Chain: /api/search → SOLR(jobs) → Siebel(DOWN) → return partial results
    """
    chain_interceptor.mock_solr("jobs", results=[
        {"id": "job-001", "title": "TPM", "company_id": "ACC-001", "location": "Pune"},
    ])
    chain_interceptor.mock_siebel_down()

    r = httpx.get(f"{BASE_URL}/api/search", params={"q": "TPM"})

    # Still returns results — just without Siebel enrichment
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) == 1
    assert results[0]["title"] == "TPM"
    # company_name may be None/missing — that's acceptable when Siebel is down

    chain_interceptor.assert_solr_called()
    chain_interceptor.assert_call_order(["solr", "siebel"])


# ─── Test 5: React Frontend Click → Full Chain via Playwright ────────────────
# (Run separately with: python -m testpilot react)
# See: scripts/playwright_chain.js
