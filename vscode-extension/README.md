# TestPilot AI

**AI-powered test generation for Python projects.** Right-click any Python file → get pytest tests instantly, written by Claude AI.

Stop writing boilerplate tests. TestPilot reads your functions, understands your logic, and generates tests that cover happy paths, edge cases, and null inputs — all in seconds.

---

## Features

### ✨ Generate Tests Instantly
Right-click any `.py` file in the editor or Explorer → **TestPilot AI: Generate Tests for This File**

TestPilot reads your functions and docstrings, then uses Claude AI to write pytest tests covering:
- Happy path scenarios
- Edge cases (empty input, nulls, boundaries)
- Auth and permission scenarios
- Contract validation

Generated tests are saved to `tests/ai_generated/test_ai_<filename>.py` and opened automatically.

### 🔀 Smart Git Diff Mode
Only changed files get new tests — no noise, no regressions.

**Command Palette → TestPilot AI: Generate Tests for Changed Files (git diff)**

Detects all `.py` files modified since the last commit and generates tests for them in one shot.

### ▶ Run All Tests
One click runs your full pytest suite from the sidebar or status bar.

### 🗄 SOLR Validation
Checks your SOLR collections for schema integrity, data freshness, and relevance against golden queries.

### 🌐 React E2E (Playwright)
Runs smoke tests, login flow, and responsive layout checks on your React frontend.

### 📊 Live Dashboard
The TestPilot sidebar shows a live status indicator, streaming output from test runs, and a summary of the last result — all without leaving VS Code.

---

## Quick Start

### 1. Install the Python backend

```bash
pip install git+https://github.com/saikatpatra-23/testpilot-ai.git
```

### 2. Initialize your project

Open the Command Palette (`Ctrl+Shift+P`) → **TestPilot AI: Initialize Project**

This creates a `config.yaml` in your workspace root.

### 3. Add your Anthropic API key

Open `config.yaml` and fill in:

```yaml
anthropic:
  api_key: "sk-ant-..."   # Get from https://console.anthropic.com
```

### 4. Generate your first tests

Open any `.py` file → right-click → **TestPilot AI: Generate Tests for This File**

---

## Requirements

- Python 3.9+
- `pip install git+https://github.com/saikatpatra-23/testpilot-ai.git`
- An [Anthropic API key](https://console.anthropic.com) (Claude API)
- For SOLR validation: a running SOLR instance
- For React E2E: Node.js + Playwright (`npm install`)

---

## Extension Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `testpilot.pythonPath` | `python` | Path to your Python executable |
| `testpilot.configPath` | `config.yaml` | Path to config file (relative to workspace root) |
| `testpilot.autoGenOnSave` | `false` | Auto-generate tests on every Python file save |

---

## Commands

| Command | Description |
|---------|-------------|
| `TestPilot AI: Generate Tests for This File` | Generate tests for the open Python file |
| `TestPilot AI: Generate Tests for Changed Files (git diff)` | Generate tests only for files changed since last commit |
| `TestPilot AI: Run All Tests` | Run full pytest suite |
| `TestPilot AI: Run SOLR Validation` | Run SOLR schema + freshness + relevance checks |
| `TestPilot AI: Run React E2E` | Run Playwright smoke + login + responsive tests |
| `TestPilot AI: Initialize Project` | Create `config.yaml` and `.vscode/tasks.json` |
| `TestPilot AI: Show Dashboard` | Open the TestPilot sidebar panel |

---

## How It Works

TestPilot uses **Claude AI (Anthropic)** to analyze your Python source code and generate meaningful tests. The VS Code extension is a lightweight controller — it spawns `python -m testpilot` CLI commands and streams output back to the sidebar and output channel.

```
Your .py file
     ↓
TestPilot reads functions + docstrings
     ↓
Claude AI generates pytest cases
     ↓
tests/ai_generated/test_ai_<file>.py
```

---

## Supported Stack

- **Unit tests:** Python + pytest
- **API contract tests:** Siebel CRM REST/SOAP (mock-based)
- **Search validation:** Apache SOLR
- **Frontend E2E:** React + Playwright (Chromium)
- **CI/CD:** GitHub Actions workflow included

---

## CI/CD Integration

TestPilot ships with a ready-made GitHub Actions workflow. On every PR:
1. Auto-generates tests for changed files
2. Runs the full test suite
3. Sends pass/fail to your Telegram group

See [INTEGRATION_GUIDE.md](https://github.com/saikatpatra-23/testpilot-ai/blob/main/INTEGRATION_GUIDE.md) for setup instructions.

---

## Troubleshooting

**"Python package not installed" warning on startup**

Run in your terminal:
```bash
pip install git+https://github.com/saikatpatra-23/testpilot-ai.git
```

**Extension is using the wrong Python**

Set `testpilot.pythonPath` in VS Code Settings to your virtual environment's Python:
```
/path/to/venv/bin/python   # macOS/Linux
C:\path\to\venv\Scripts\python.exe   # Windows
```

Or install the [Python extension](https://marketplace.visualstudio.com/items?itemName=ms-python.python) — TestPilot will use its active interpreter automatically.

**Tests generated but file not opening**

The test file is at `tests/ai_generated/test_ai_<yourfile>.py` in your workspace root. Open it manually from the Explorer if the prompt doesn't appear.

---

## Links

- [GitHub Repository](https://github.com/saikatpatra-23/testpilot-ai)
- [Report an Issue](https://github.com/saikatpatra-23/testpilot-ai/issues)
- [Integration Guide](https://github.com/saikatpatra-23/testpilot-ai/blob/main/INTEGRATION_GUIDE.md)

---

## License

MIT — free to use, modify, and distribute.
