"""
TestPilot AI — Main CLI
Usage:
    python -m testpilot run              # run all configured tests
    python -m testpilot generate --diff HEAD~1  # generate tests for changed files
    python -m testpilot solr             # run SOLR checks only
    python -m testpilot react            # run Playwright E2E only
"""
import argparse
import subprocess
import sys
from pathlib import Path

from .config import load_config
from .runners.pytest_runner import run_pytest
from .runners.solr_runner import run_solr_checks
from .reporters.telegram import TelegramReporter


def cmd_generate(args, cfg):
    from .generator import main as gen_main
    sys.argv = ["generator"]
    if args.diff:
        sys.argv += ["--diff", args.diff]
    if args.source:
        sys.argv += ["--source"] + args.source
    gen_main()


def cmd_solr(args, cfg):
    print("\nTestPilot AI — SOLR Validation\n")
    results = run_solr_checks()
    for item in results.get("passed", []):
        print(f"  ✅ {item}")
    for item in results.get("failed", []):
        print(f"  ❌ {item}")
    for item in results.get("errors", []):
        print(f"  ⚠️  {item}")

    failed = len(results.get("failed", [])) + len(results.get("errors", []))
    _maybe_notify(results, cfg, "SOLR")
    return 0 if failed == 0 else 1


def cmd_react(args, cfg):
    print("\nTestPilot AI — React E2E\n")
    runner_path = Path(__file__).parent.parent / "scripts" / "playwright_runner.js"
    env = {}
    if cfg.get("frontend", {}).get("url"):
        env["APP_URL"] = cfg["frontend"]["url"]

    result = subprocess.run(
        ["node", str(runner_path)],
        env={**__import__("os").environ, **env}
    )
    return result.returncode


def cmd_run(args, cfg):
    """Run all configured test suites."""
    all_results = {"passed": [], "failed": [], "errors": []}
    exit_code = 0

    # 1. pytest
    print("\n--- pytest ---")
    test_dirs = ["tests/"]
    pr = run_pytest(test_dirs)
    all_results["passed"].extend(pr.get("passed", []))
    all_results["failed"].extend(pr.get("failed", []))
    print(pr.get("output", "")[-2000:])  # last 2000 chars
    if pr.get("exit_code", 0) != 0:
        exit_code = 1

    # 2. SOLR
    if cfg.get("solr", {}).get("enabled"):
        print("\n--- SOLR ---")
        sr = run_solr_checks()
        all_results["passed"].extend(sr.get("passed", []))
        all_results["failed"].extend(sr.get("failed", []))
        all_results["errors"].extend(sr.get("errors", []))
        if sr.get("failed") or sr.get("errors"):
            exit_code = 1

    # 3. React E2E
    if cfg.get("frontend", {}).get("enabled"):
        print("\n--- React E2E ---")
        rc = cmd_react(args, cfg)
        if rc != 0:
            exit_code = 1
            all_results["failed"].append("React E2E: one or more tests failed")

    # Notify
    _maybe_notify(all_results, cfg, cfg.get("project", {}).get("name", "TestPilot"))

    # Summary
    print(f"\n{'='*40}")
    print(f"TOTAL: {len(all_results['passed'])} passed, {len(all_results['failed'])} failed")
    return exit_code


def _maybe_notify(results, cfg, label):
    tg = cfg.get("notifications", {}).get("telegram", {})
    if tg.get("enabled") and tg.get("bot_token") and tg.get("chat_id"):
        reporter = TelegramReporter(tg["bot_token"], tg["chat_id"])
        reporter.report_results(results, project=label)
        print(f"  [telegram] Notification sent")


def main():
    parser = argparse.ArgumentParser(prog="testpilot", description="TestPilot AI")
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Run all test suites")
    run_p.add_argument("--config", default=None)

    gen_p = sub.add_parser("generate", help="AI-generate tests from source code")
    gen_p.add_argument("--diff", help="Generate for git diff since this ref")
    gen_p.add_argument("--source", nargs="+", help="Specific source files")
    gen_p.add_argument("--config", default=None)

    solr_p = sub.add_parser("solr", help="Run SOLR validation checks")
    solr_p.add_argument("--config", default=None)

    react_p = sub.add_parser("react", help="Run React E2E tests (Playwright)")
    react_p.add_argument("--config", default=None)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    try:
        cfg = load_config(getattr(args, "config", None))
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    dispatch = {
        "run": cmd_run,
        "generate": cmd_generate,
        "solr": cmd_solr,
        "react": cmd_react,
    }
    exit_code = dispatch[args.command](args, cfg)
    sys.exit(exit_code or 0)


if __name__ == "__main__":
    main()
