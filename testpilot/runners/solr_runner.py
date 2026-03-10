"""
TestPilot AI — SOLR Validation Runner
Standalone runner for SOLR integrity checks.
"""
from ..adapters.solr import SOLRValidator
from ..config import load_config


def run_solr_checks(config_path: str = None) -> dict:
    cfg = load_config(config_path)
    solr_cfg = cfg.get("solr", {})

    if not solr_cfg.get("enabled", False):
        return {"skipped": True, "reason": "SOLR disabled in config"}

    validator = SOLRValidator(solr_cfg["base_url"])
    results = validator.run_all_checks(solr_cfg)

    return results


if __name__ == "__main__":
    results = run_solr_checks()
    passed = len(results.get("passed", []))
    failed = len(results.get("failed", []))

    for item in results.get("passed", []):
        print(f"  ✅ {item}")
    for item in results.get("failed", []):
        print(f"  ❌ {item}")
    for item in results.get("errors", []):
        print(f"  ⚠️  {item}")

    print(f"\n{passed} passed, {failed} failed")
    exit(0 if failed == 0 else 1)
