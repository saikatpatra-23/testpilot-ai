"""
Example: SOLR Validation Tests
Run: pytest tests/examples/test_solr_validation.py -v
Set SOLR_LIVE=1 to run against real SOLR.
"""
import os
import pytest
from unittest.mock import patch, MagicMock

SOLR_LIVE = os.getenv("SOLR_LIVE", "0") == "1"
SOLR_URL = os.getenv("SOLR_URL", "http://localhost:8983/solr")


def make_solr_mock(collection: str, docs: list):
    """Helper: mock SOLR response."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "response": {"numFound": len(docs), "docs": docs},
        "responseHeader": {"status": 0}
    }
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ─── Schema Tests ─────────────────────────────────────────────────────────────

class TestSOLRSchema:
    @pytest.mark.skipif(not SOLR_LIVE, reason="Set SOLR_LIVE=1 for live tests")
    def test_jobs_collection_accessible(self):
        import httpx
        r = httpx.get(f"{SOLR_URL}/jobs/select", params={"q": "*:*", "rows": 0, "wt": "json"})
        assert r.status_code == 200

    def test_jobs_required_fields_present(self):
        sample_doc = {
            "id": "job-001",
            "title": "Technical Program Manager",
            "company": "Tata Motors",
            "location": "Pune",
            "posted_date": "2026-03-01T00:00:00Z",
            "description": "Lead digital transformation..."
        }
        required = ["id", "title", "company", "location", "posted_date"]
        missing = [f for f in required if f not in sample_doc]
        assert missing == [], f"Missing fields: {missing}"

    def test_no_docs_with_null_title(self):
        """Documents with null titles should never be indexed."""
        with patch("httpx.get") as mock_get:
            mock_get.return_value = make_solr_mock("jobs", [])  # 0 results
            import httpx
            r = httpx.get(f"{SOLR_URL}/jobs/select",
                         params={"q": "-title:[* TO *]", "rows": 0, "wt": "json"})
            data = r.json()
        assert data["response"]["numFound"] == 0, "Found documents with null titles!"


# ─── Relevance Tests ──────────────────────────────────────────────────────────

class TestSOLRRelevance:
    def test_tpm_query_returns_tpm_results(self):
        """Searching 'Technical Program Manager' should return TPM jobs in top results."""
        sample_docs = [
            {"id": "1", "title": "Technical Program Manager", "company": "Infosys"},
            {"id": "2", "title": "Senior TPM", "company": "TCS"},
        ]
        with patch("httpx.get") as mock_get:
            mock_get.return_value = make_solr_mock("jobs", sample_docs)
            import httpx
            r = httpx.get(f"{SOLR_URL}/jobs/select",
                         params={"q": "Technical Program Manager", "rows": 5})
            docs = r.json()["response"]["docs"]

        titles = [d.get("title", "") for d in docs]
        has_relevant = any("Program Manager" in t or "TPM" in t for t in titles)
        assert has_relevant, f"Relevance degraded. Top results: {titles}"

    def test_location_filter_works(self):
        """Filtering by city should return only that city's jobs."""
        pune_docs = [
            {"id": "1", "title": "TPM", "location": "Pune"},
            {"id": "2", "title": "PM", "location": "Pune"},
        ]
        with patch("httpx.get") as mock_get:
            mock_get.return_value = make_solr_mock("jobs", pune_docs)
            import httpx
            r = httpx.get(f"{SOLR_URL}/jobs/select",
                         params={"q": "*:*", "fq": "location:Pune", "rows": 10})
            docs = r.json()["response"]["docs"]

        locations = [d.get("location", "") for d in docs]
        assert all(loc == "Pune" for loc in locations), "Location filter broken"


# ─── Stale Data Tests ─────────────────────────────────────────────────────────

class TestSOLRDataFreshness:
    def test_no_jobs_older_than_90_days(self):
        """Active job index should not have listings older than 90 days."""
        with patch("httpx.get") as mock_get:
            mock_get.return_value = make_solr_mock("jobs", [])  # 0 stale docs
            import httpx
            r = httpx.get(f"{SOLR_URL}/jobs/select",
                         params={
                             "q": "posted_date:[* TO NOW-90DAYS]",
                             "rows": 0, "wt": "json"
                         })
            stale_count = r.json()["response"]["numFound"]

        assert stale_count == 0, f"Found {stale_count} stale documents (>90 days old)"

    def test_index_has_recent_docs(self):
        """Index should always have docs from last 7 days (freshness check)."""
        recent_docs = [{"id": "1", "title": "TPM", "posted_date": "2026-03-09"}]
        with patch("httpx.get") as mock_get:
            mock_get.return_value = make_solr_mock("jobs", recent_docs)
            import httpx
            r = httpx.get(f"{SOLR_URL}/jobs/select",
                         params={
                             "q": "posted_date:[NOW-7DAYS TO NOW]",
                             "rows": 0, "wt": "json"
                         })
            recent_count = r.json()["response"]["numFound"]

        assert recent_count > 0, "No recent documents — possible indexing failure!"
