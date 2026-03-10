"""
TestPilot AI — Chain Test Generator

Given a call chain map, generates integration tests that:
1. Call the actual API endpoint (not mocked)
2. Mock SOLR at HTTP level (respx)
3. Mock Siebel at HTTP level (respx)
4. Assert the correct downstream calls happened in the right order
5. Assert conditional logic (e.g. Siebel only called when SOLR returns results)
6. Assert response shape matches what frontend expects
"""
import anthropic
from .config import load_config


SYSTEM_PROMPT = """You are TestPilot AI. Generate pytest INTEGRATION tests for API call chains.

These are NOT unit tests. Each test:
- Calls the REAL API endpoint using httpx
- Mocks only the external dependencies (SOLR, Siebel) at the HTTP boundary using respx
- Verifies the CHAIN BEHAVIOR — correct downstream calls, correct order, correct conditions
- Verifies the response shape that the frontend receives

Rules:
1. Use respx to mock SOLR (httpx.get calls to SOLR)
2. Use respx to mock Siebel REST, or unittest.mock for Siebel SOAP (zeep)
3. Always test 3 scenarios per chain:
   a) HAPPY PATH — normal flow, all dependencies return data
   b) SOLR EMPTY — SOLR returns 0 results; verify Siebel is NOT called
   c) DEPENDENCY DOWN — SOLR or Siebel returns error; verify API returns correct error code
4. Use respx.calls to assert which mocks were hit and with what parameters
5. Assert the exact response shape the frontend expects (field names, types)
6. Add a docstring explaining the business flow being tested

Return ONLY valid Python pytest code.
"""


def generate_chain_tests(
    chains: list[dict],
    cfg: dict,
    source_code: str = ""
) -> str:
    """Generate integration tests for the given call chains."""
    if not chains:
        return ""

    client = anthropic.Anthropic(api_key=cfg["anthropic"]["api_key"])

    backend_url = cfg.get("backend", {}).get("url", "http://localhost:8000")
    solr_url = cfg.get("solr", {}).get("base_url", "http://localhost:8983/solr")
    siebel_url = cfg.get("siebel", {}).get("rest", {}).get("base_url", "")

    import json
    chain_json = json.dumps(chains, indent=2)

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=6000,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"""Generate chain integration tests for these API call chains.

Backend URL: {backend_url}
SOLR URL: {solr_url}
Siebel URL: {siebel_url}

Call chains to test:
{chain_json}

Relevant source code:
{source_code[:3000] if source_code else "(not provided)"}

Generate complete pytest tests covering all chains and their scenarios."""
        }]
    )

    return msg.content[0].text
