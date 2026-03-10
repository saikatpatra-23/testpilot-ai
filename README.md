# TestPilot AI

**AI-powered automated testing for enterprise stacks — Python · Siebel CRM · Apache SOLR · React · Flutter · Kotlin · iOS**

Stop doing manual unit testing. Point TestPilot at your code, it reads your functions, generates tests, runs them on every PR, and pings your team on Telegram.

---

## What it does

| Layer | Technology | What TestPilot checks |
|-------|------------|----------------------|
| Python Backend | pytest + httpx | API contracts, auth, edge cases, error handling |
| Siebel CRM (REST) | respx mock | Request shape, required fields, error propagation |
| Siebel CRM (SOAP) | zeep mock | Service method calls, response parsing, downtime handling |
| Apache SOLR | httpx | Schema drift, stale documents, relevance, null data |
| React Frontend | Playwright | Smoke tests, login flow, responsive layouts, screenshots |
| Mobile (Phase 2) | Appium / Flutter | Cross-platform E2E flows |
| Notifications | Telegram Bot | Pass/fail summary on every CI run |

---

## How it works

```
git push / PR opened
       │
       ▼
GitHub Actions triggers TestPilot
       │
       ├── Claude reads your changed .py files
       │   └── Generates pytest tests for every function
       │
       ├── pytest runs all tests (unit + contract + integration)
       │
       ├── SOLR validator checks schema + freshness
       │
       ├── Playwright runs smoke tests on your React app
       │
       └── Telegram: "✅ 47 passed" or "❌ 3 failed — test names here"
```

---

## Quickstart (15 minutes)

**1. Clone and install**
```bash
git clone https://github.com/saikatpatra-23/testpilot-ai.git
cd testpilot-ai
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
npm install && npx playwright install chromium
```

**2. Configure**
```bash
cp config.example.yaml config.yaml
# Fill in: Anthropic API key, Siebel URL/creds, SOLR URL, React app URL, Telegram bot
```

**3. Generate tests from your code**
```bash
python -m testpilot generate --source path/to/your/api/endpoints.py
# Review tests/ai_generated/ → commit
```

**4. Run**
```bash
python -m testpilot run
```

See [INSTALL.txt](INSTALL.txt) for the full step-by-step guide.

---

## Plug into your existing repo

Copy the `testpilot/` folder into your org's repo root — no package publishing needed:

```bash
cp -r testpilot-ai/testpilot/          your-org-repo/testpilot/
cp -r testpilot-ai/tests/              your-org-repo/tests/
cp    testpilot-ai/scripts/playwright_runner.js  your-org-repo/scripts/
cp    testpilot-ai/config.example.yaml your-org-repo/
```

Then in your existing test files, use the adapters directly:

```python
# Siebel REST — mock in any pytest file
from testpilot.adapters.siebel_rest import make_siebel_mock

def test_create_lead():
    with make_siebel_mock({"Lead": {"Id": "1-ABC", "Status": "New"}}):
        result = your_crm_module.create_lead({"name": "Test User"})
        assert result["Id"] == "1-ABC"
```

```python
# Siebel SOAP — mock zeep calls
from testpilot.adapters.siebel_soap import mock_siebel_soap

def test_get_opportunity():
    with mock_siebel_soap({"QueryOpportunity": {"Id": "OPP-001", "Stage": "Proposal"}}):
        result = your_soap_module.get_opportunity("OPP-001")
        assert result["Stage"] == "Proposal"
```

```python
# SOLR — validate schema
from testpilot.adapters.solr import SOLRValidator

def test_schema_integrity():
    v = SOLRValidator("http://your-solr:8983/solr")
    missing = v.check_required_fields("jobs", ["id", "title", "location"])
    assert missing == [], f"Schema drift detected: {missing}"
```

---

## CLI Reference

```bash
python -m testpilot run                       # Run all configured test suites
python -m testpilot generate --diff HEAD~1    # AI-generate tests for changed files
python -m testpilot generate --source f.py    # AI-generate tests for specific file
python -m testpilot solr                      # Run SOLR validation only
python -m testpilot react                     # Run React Playwright E2E only
pytest tests/examples/ -v                     # Run examples (mocked, no config needed)
```

---

## GitHub Actions CI/CD

Copy `.github/workflows/testpilot.yml` to your repo. Add these secrets:

| Secret | Value |
|--------|-------|
| `ANTHROPIC_API_KEY` | Your Anthropic key |
| `SIEBEL_USERNAME` | Siebel service account |
| `SIEBEL_PASSWORD` | Siebel service account |
| `SOLR_URL` | `http://solr.yourorg.com:8983/solr` |
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token |
| `TELEGRAM_CHAT_ID` | Your group/personal chat ID |
| `APP_URL` | Your React staging URL |

Every PR then automatically:
1. Generates tests for changed files (AI)
2. Runs pytest + Siebel contracts + SOLR checks
3. Runs Playwright E2E on React
4. Sends Telegram notification

---

## Architecture

See [ARCHITECTURE.txt](ARCHITECTURE.txt) for the full system diagram.

```
testpilot-ai/
├── testpilot/
│   ├── generator.py          # AI test generation (Claude Sonnet)
│   ├── config.py             # Config loader (YAML + env vars)
│   ├── __main__.py           # CLI entry point
│   ├── adapters/
│   │   ├── siebel_rest.py    # Siebel REST mock + client
│   │   ├── siebel_soap.py    # Siebel SOAP mock (zeep)
│   │   └── solr.py           # SOLR schema + freshness validator
│   ├── runners/
│   │   ├── pytest_runner.py  # pytest orchestrator
│   │   └── solr_runner.py    # SOLR check runner
│   └── reporters/
│       └── telegram.py       # Telegram pass/fail notifications
├── scripts/
│   └── playwright_runner.js  # React E2E (smoke + login + responsive)
├── tests/
│   └── examples/             # Ready-to-run example tests (all mocked)
├── .github/workflows/
│   └── testpilot.yml         # Full CI/CD pipeline
├── config.example.yaml       # Copy → config.yaml, fill in your values
├── ARCHITECTURE.txt          # Full system architecture diagram
└── INSTALL.txt               # Step-by-step installation guide
```

---

## Roadmap

- **Phase 1 (current)** — Python · Siebel REST/SOAP · SOLR · React · GitHub Actions · Telegram
- **Phase 2** — Flutter integration_test · Kotlin Espresso · iOS XCTest · Appium cross-platform
- **Phase 3** — Visual regression diffing · Performance benchmarking · Security test generation

---

## Requirements

- Python 3.11+
- Node.js 18+
- Anthropic API key ([console.anthropic.com](https://console.anthropic.com))
- Telegram bot (5 min setup — see INSTALL.txt)

---

## License

MIT
