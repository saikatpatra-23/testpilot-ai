# TestPilot AI — Integration Guide

How to plug this into your existing organization's codebase.

## Step 1 — Copy TestPilot into your repo

```bash
# Option A: As a subfolder (recommended)
cp -r testpilot-ai/ your-org-repo/testpilot/

# Option B: Install as a package (if you push to PyPI/internal registry)
pip install testpilot-ai
```

## Step 2 — Configure

```bash
cd your-org-repo
cp testpilot/config.example.yaml config.yaml
# Edit config.yaml with your actual values
```

Key things to fill in:
- `backend.url` — your Python API base URL
- `siebel.rest.base_url` — your Siebel server URL
- `siebel.rest.username/password` — or use env vars `SIEBEL_USERNAME` / `SIEBEL_PASSWORD`
- `solr.base_url` — your SOLR URL
- `solr.collections` — your actual collection names + required fields
- `frontend.url` — your React app URL
- `notifications.telegram.bot_token` + `chat_id` — your Telegram bot

## Step 3 — Generate your first tests

Point TestPilot at your existing Python code:

```bash
# Generate tests for a specific file
python -m testpilot generate --source src/api/your_endpoint.py

# Generate tests for all files changed in last commit
python -m testpilot generate --diff HEAD~1

# Generate tests for all source files
python -m testpilot generate
```

Tests are saved to `tests/ai_generated/`. Review them, adjust as needed, commit.

## Step 4 — Run tests locally

```bash
# Run all suites
python -m testpilot run

# Run only backend pytest
pytest tests/ -v

# Run only SOLR validation
python -m testpilot solr

# Run only React E2E
python -m testpilot react
```

## Step 5 — Add to CI/CD (GitHub Actions)

```bash
# Copy the workflow file
cp testpilot/.github/workflows/testpilot.yml .github/workflows/

# Add these secrets to your GitHub repo:
# Settings → Secrets → Actions → New repository secret
# - ANTHROPIC_API_KEY
# - SIEBEL_USERNAME
# - SIEBEL_PASSWORD
# - SOLR_URL
# - TELEGRAM_BOT_TOKEN
# - TELEGRAM_CHAT_ID
# - APP_URL (your React app URL)
```

From here, every PR automatically:
1. AI generates tests for changed files
2. Runs pytest + Siebel contracts + SOLR checks
3. Runs Playwright E2E on your React app
4. Sends Telegram notification with results

---

## Plugging into your specific tech stack

### Python Backend
Replace the example endpoints in `tests/examples/test_python_api.py` with your actual endpoints.
```python
BASE_URL = "http://your-backend:8000"  # ← change this
```

### Siebel REST
```python
# In your existing code, wherever you call Siebel:
from testpilot.adapters.siebel_rest import make_siebel_mock

# In your tests:
with make_siebel_mock({"Account": [{"Id": "1-ABC", "Name": "Test"}]}):
    result = your_crm_module.get_account("1-ABC")
    assert result["Name"] == "Test"
```

### Siebel SOAP
```python
from testpilot.adapters.siebel_soap import mock_siebel_soap

with mock_siebel_soap({"QueryOpportunity": {"Id": "OPP-001", "Status": "Open"}}):
    result = your_soap_module.get_opportunity("OPP-001")
    assert result["Status"] == "Open"
```

### SOLR
```python
from testpilot.adapters.solr import SOLRValidator

validator = SOLRValidator("http://your-solr:8983/solr")
missing = validator.check_required_fields("jobs", ["id", "title", "location"])
assert missing == [], f"Schema drift detected: {missing}"
```

### React (Playwright)
Edit `config.yaml`:
```yaml
frontend:
  url: "http://localhost:3000"    # your React dev server
  auth:
    email: "testuser@yourorg.com"
    password: "testpassword"
  smoke_tests:
    - path: "/"
      wait_for: "h1"
    - path: "/dashboard"
      requires_auth: true
    - path: "/your-key-page"
      wait_for: ".your-selector"
```

---

## Flutter / Kotlin / iOS (Phase 2)

For mobile, TestPilot generates test scaffolding. Runners are platform-native:

**Flutter**: `flutter test integration_test/`
**Android**: `./gradlew test` (JUnit4 + Espresso)
**iOS**: `xcodebuild test -scheme YourApp -destination 'platform=iOS Simulator,name=iPhone 15'`

TestPilot AI will generate the test code — you run it on your platform.
