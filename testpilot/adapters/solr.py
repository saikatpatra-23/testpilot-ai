"""
TestPilot AI — SOLR Adapter
Validates SOLR collections: schema integrity, relevance, stale data.
"""
import httpx
from typing import Optional


class SOLRValidator:
    def __init__(self, base_url: str, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _select(self, collection: str, **params) -> dict:
        url = f"{self.base_url}/{collection}/select"
        params.setdefault("wt", "json")
        r = httpx.get(url, params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def count(self, collection: str, query: str = "*:*") -> int:
        result = self._select(collection, q=query, rows=0)
        return result["response"]["numFound"]

    def sample_doc(self, collection: str, query: str = "*:*") -> Optional[dict]:
        result = self._select(collection, q=query, rows=1)
        docs = result["response"]["docs"]
        return docs[0] if docs else None

    def check_required_fields(self, collection: str, required_fields: list[str]) -> list[str]:
        """Returns list of missing fields (empty = all good)."""
        doc = self.sample_doc(collection)
        if not doc:
            return [f"[EMPTY COLLECTION: {collection}]"]
        return [f for f in required_fields if f not in doc]

    def check_stale_docs(self, collection: str, date_field: str, max_age_days: int) -> int:
        """Returns count of documents older than max_age_days."""
        query = f"{date_field}:[* TO NOW-{max_age_days}DAYS]"
        return self.count(collection, query)

    def check_relevance(self, collection: str, query: str, expected_keyword: str,
                        top_n: int = 5) -> bool:
        """Returns True if expected_keyword appears in top N result titles."""
        result = self._select(collection, q=query, rows=top_n, fl="title,name")
        docs = result["response"]["docs"]
        for doc in docs:
            for field in ["title", "name"]:
                if field in doc and expected_keyword.lower() in doc[field].lower():
                    return True
        return False

    def run_all_checks(self, config: dict) -> dict:
        """Run all configured checks. Returns results dict."""
        results = {"passed": [], "failed": [], "errors": []}

        for coll_cfg in config.get("collections", []):
            name = coll_cfg["name"]
            required = coll_cfg.get("required_fields", [])
            try:
                missing = self.check_required_fields(name, required)
                if missing:
                    results["failed"].append(f"{name}: missing fields {missing}")
                else:
                    results["passed"].append(f"{name}: all required fields present")

                count = self.count(name)
                results["passed"].append(f"{name}: {count} documents indexed")

            except Exception as e:
                results["errors"].append(f"{name}: {e}")

        for gq in config.get("golden_queries", []):
            coll = gq["collection"]
            q = gq["query"]
            min_r = gq.get("min_results", 1)
            try:
                count = self.count(coll, q)
                if count >= min_r:
                    results["passed"].append(f"{coll} golden query '{q}': {count} results")
                else:
                    results["failed"].append(f"{coll} golden query '{q}': only {count} results (need {min_r})")
            except Exception as e:
                results["errors"].append(f"{coll} golden query: {e}")

        return results
