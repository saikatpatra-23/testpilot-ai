"""
TestPilot AI — Chain Analyzer

Reads your Python backend code and maps the full call chain for each API endpoint:
  POST /api/search → search_jobs() → query_solr() → [if results] → enrich_from_siebel()

This tells TestPilot WHAT to mock and WHERE to assert in chain tests.
"""
import ast
import os
from pathlib import Path
from typing import Any
import anthropic

from .config import load_config


SYSTEM_PROMPT = """You are TestPilot AI. Analyze Python backend code and map API call chains.

For each API endpoint (Flask route, FastAPI path operation, Django view), identify:
1. The endpoint path + method (e.g. POST /api/search)
2. The function that handles it
3. Every downstream function call in the chain
4. Which calls hit SOLR (look for solr, search, select, httpx.get with solr URL patterns)
5. Which calls hit Siebel (look for siebel, crm, zeep, soap, rest calls to siebel URL patterns)
6. Conditional logic: "if SOLR returns X then call Siebel"
7. The final response shape returned to the caller

Return a JSON array of chain objects. Each chain object:
{
  "endpoint": "POST /api/search",
  "handler": "search_jobs",
  "chain": [
    {"step": 1, "fn": "search_jobs", "calls": ["query_solr"]},
    {"step": 2, "fn": "query_solr", "type": "solr", "collection": "jobs", "condition": null},
    {"step": 3, "fn": "enrich_from_siebel", "type": "siebel", "condition": "if solr_results > 0"}
  ],
  "response_shape": {"results": "list", "total": "int"},
  "external_deps": ["solr", "siebel"]
}

Return ONLY valid JSON, no explanation.
"""


def analyze_chains(source_paths: list[str], cfg: dict) -> list[dict]:
    """
    Analyze Python source files and return a list of call chains.
    """
    all_source = ""
    for path in source_paths:
        if not Path(path).exists():
            continue
        try:
            code = Path(path).read_text(encoding="utf-8")
            all_source += f"\n\n# === FILE: {path} ===\n{code}"
        except Exception:
            pass

    if not all_source.strip():
        return []

    client = anthropic.Anthropic(api_key=cfg["anthropic"]["api_key"])
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Analyze these Python files and map all API call chains:\n{all_source}"
        }]
    )

    import json, re
    text = msg.content[0].text
    # Extract JSON from response
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return []
