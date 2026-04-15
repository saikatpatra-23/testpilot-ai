# TestPilot AI — Unit Test Generator

[![VS Code Marketplace](https://img.shields.io/visual-studio-marketplace/v/testpilot-ai.testpilot-ai?label=VS%20Code%20Marketplace&color=blue&logo=visualstudiocode)](https://marketplace.visualstudio.com/items?itemName=testpilot-ai.testpilot-ai)
[![Open VSX](https://img.shields.io/open-vsx/v/testpilot-ai/testpilot-ai?label=Open%20VSX&color=purple)](https://open-vsx.org/extension/testpilot-ai/testpilot-ai)
[![Installs](https://img.shields.io/visual-studio-marketplace/i/testpilot-ai.testpilot-ai?color=green)](https://marketplace.visualstudio.com/items?itemName=testpilot-ai.testpilot-ai)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Generate pytest unit tests instantly with AI.** Right-click any Python file → tests written in seconds, covering happy paths, edge cases, and null inputs.

No more staring at a blank `test_` file. TestPilot reads your functions and writes the tests for you.

---

## ⚡ How It Works

1. Open any `.py` file in VS Code
2. Right-click → **TestPilot AI: Generate Tests for This File**
3. Tests are written to `tests/ai_generated/test_ai_<yourfile>.py` and opened automatically

That's it.

---

## ✨ Features

### AI Test Generation (Free — 20 tests/month)
- Generates pytest tests from your Python functions automatically
- Covers: happy path, edge cases, null inputs, boundary values
- Understands your docstrings and existing code patterns
- No copy-paste — tests appear in a ready-to-run file

### Smart Git Diff Mode
Only generates tests for files you actually changed:

**Command Palette → TestPilot AI: Generate Tests for Changed Files**

Perfect for PR reviews — no noise, targeted coverage.

### Live Dashboard
Sidebar panel shows real-time test run output, pass/fail status, and generation history — without leaving your editor.

### Auto-Generate on Save *(Pro)*
Enable `testpilot.autoGenOnSave` and tests update every time you save a Python file.

### CI/CD Ready
Ships with a GitHub Actions workflow. Auto-generate + run tests on every PR.

---

## 🆓 Free vs Pro

| Feature | Free | Pro ($4.99/mo) |
|---|---|---|
| Test generations | 20/month | Unlimited |
| Git diff mode | ✅ | ✅ |
| Auto-gen on save | ❌ | ✅ |
| Priority support | ❌ | ✅ |

**[Upgrade to Pro →](https://classy5b.gumroad.com/l/testpilot-ai-pro)**

Enter your license key: `Settings → TestPilot AI → License Key`

---

## 🚀 Quick Start

### Step 1 — Install the Python backend

```bash
pip install git+https://github.com/saikatpatra-23/testpilot-ai.git
```

### Step 2 — Initialize your project

`Ctrl+Shift+P` → **TestPilot AI: Initialize Project**

Creates `config.yaml` in your workspace root.

### Step 3 — Add your API key

Open `config.yaml`:

```yaml
anthropic:
  api_key: "sk-ant-..."   # Get free at https://console.anthropic.com
```

### Step 4 — Generate tests

Open any `.py` file → right-click → **TestPilot AI: Generate Tests for This File**

---

## Requirements

- Python 3.9+
- An [Anthropic API key](https://console.anthropic.com) (free tier available)

---

## Extension Settings

| Setting | Default | Description |
|---|---|---|
| `testpilot.licenseKey` | *(empty)* | Pro license key from Gumroad |
| `testpilot.pythonPath` | `python` | Path to Python executable |
| `testpilot.autoGenOnSave` | `false` | Auto-generate tests on file save *(Pro)* |

---

## Supported Stack

- **Unit tests:** Python + pytest
- **Diff mode:** git-aware, PR-ready
- **CI/CD:** GitHub Actions workflow included
- **Frontend E2E:** React + Playwright

---

## Troubleshooting

**"Python package not installed"**
```bash
pip install git+https://github.com/saikatpatra-23/testpilot-ai.git
```

**Wrong Python being used**

Set `testpilot.pythonPath` in VS Code Settings to your venv Python path.

---

## Links

- [GitHub](https://github.com/saikatpatra-23/testpilot-ai)
- [Report Issue](https://github.com/saikatpatra-23/testpilot-ai/issues)
- [Upgrade to Pro](https://classy5b.gumroad.com/l/testpilot-ai-pro)

---

## License

MIT
