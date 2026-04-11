# Changelog

All notable changes to TestPilot AI are documented here.

## [0.1.0] — 2026-04-11

### Initial Release

- **Generate Tests for This File** — right-click any Python file to generate pytest tests via Claude AI
- **Generate Tests for Changed Files** — git diff mode: only generates tests for files changed since last commit
- **Run All Tests** — one-click pytest execution from sidebar or status bar
- **SOLR Validation** — schema integrity, data freshness, and relevance checks
- **React E2E** — Playwright smoke tests, login flow, and responsive layout validation
- **Live Sidebar Dashboard** — streaming test output, colored status indicator, quick-action buttons
- **Status Bar Integration** — always-visible test state with pass/fail color coding
- **Initialize Project** — creates `config.yaml` and `.vscode/tasks.json` in one step
- **Auto Python detection** — uses VS Code's active Python interpreter automatically
- **Auto-generate on save** — optional setting to generate tests on every `.py` file save
- **Telegram notifications** — pass/fail alerts sent to your team Telegram group (configured in `config.yaml`)
- **GitHub Actions CI/CD** — included workflow for auto-generate + run + notify on every PR
