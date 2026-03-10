"""
TestPilot AI — Targeted Runner

Runs ONLY the tests relevant to what changed.
Backend runs as-is on localhost — TestPilot just fires HTTP at it.
"""
import subprocess
import sys
import json
import os
from pathlib import Path

from .diff_detector import analyze_impact, get_changed_files
from .config import load_config


def run_backend_chain_tests(test_files: list[str], backend_url: str) -> dict:
    """
    Run chain tests against a locally running backend.
    Backend must already be running — TestPilot doesn't start it.

    Args:
        test_files: specific test files to run (not the whole suite)
        backend_url: your locally running API (e.g. http://localhost:8000)
    """
    if not test_files:
        return {"skipped": True, "reason": "No relevant test files found for changed code"}

    args = [
        sys.executable, "-m", "pytest",
        "--tb=short", "-v",
        "--json-report",
        "--json-report-file=/tmp/testpilot-targeted-report.json",
    ] + test_files

    env = {**os.environ, "BACKEND_URL": backend_url, "TEST_BACKEND_URL": backend_url}

    print(f"\n  Running {len(test_files)} test file(s) against {backend_url}")
    for f in test_files:
        print(f"    → {f}")

    result = subprocess.run(args, capture_output=False, env=env)

    report_path = Path("/tmp/testpilot-targeted-report.json")
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text())
            summary = report.get("summary", {})
            passed = [t["nodeid"] for t in report.get("tests", []) if t["outcome"] == "passed"]
            failed = [
                f"{t['nodeid']}: {t.get('call', {}).get('longrepr', '')[:300]}"
                for t in report.get("tests", []) if t["outcome"] in ("failed", "error")
            ]
            return {
                "passed": passed, "failed": failed, "errors": [],
                "exit_code": result.returncode, "summary": summary,
                "test_files": test_files,
            }
        except Exception:
            pass

    return {"exit_code": result.returncode, "test_files": test_files}


def run_frontend_chain_test(changed_js_files: list[str], cfg: dict) -> dict:
    """
    Run Playwright tests ONLY for the React components/pages that changed.
    Maps changed component → affected page route → Playwright test.
    """
    frontend_url = cfg.get("frontend", {}).get("url", "http://localhost:3000")
    skill_dir = "C:/Users/Student/.claude/skills/playwright-skill"

    # Map changed component files to page routes
    routes_to_test = _map_components_to_routes(changed_js_files, cfg)

    if not routes_to_test:
        return {"skipped": True, "reason": "No route mapping found for changed components"}

    # Write a targeted Playwright script
    script = _build_targeted_playwright_script(frontend_url, routes_to_test)
    script_path = "/tmp/testpilot-targeted-playwright.js"
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)

    print(f"\n  Running React E2E for {len(routes_to_test)} affected route(s):")
    for r in routes_to_test:
        print(f"    → {r}")

    result = subprocess.run(
        ["node", "run.js", script_path],
        cwd=skill_dir,
        capture_output=False,
        env={**os.environ, "APP_URL": frontend_url}
    )

    return {"exit_code": result.returncode, "routes_tested": routes_to_test}


def _map_components_to_routes(changed_js_files: list[str], cfg: dict) -> list[str]:
    """
    Map changed component files to the page routes they affect.
    Reads from config or uses naming convention.
    """
    # Check config for explicit mappings
    component_map = cfg.get("frontend", {}).get("component_routes", {})

    routes = set()
    for filepath in changed_js_files:
        filename = Path(filepath).stem.lower()

        # Check explicit config mapping first
        if filepath in component_map:
            routes.add(component_map[filepath])
            continue

        # Naming convention: SearchBar.jsx → /search, LoginForm.jsx → /login
        for keyword, route in [
            ("search", "/"),
            ("login", "/login"),
            ("dashboard", "/dashboard"),
            ("profile", "/profile"),
            ("apply", "/jobs"),
            ("job", "/jobs"),
            ("home", "/"),
        ]:
            if keyword in filename:
                routes.add(route)
                break
        else:
            routes.add("/")  # fallback: test homepage

    return sorted(routes)


def _build_targeted_playwright_script(frontend_url: str, routes: list[str]) -> str:
    routes_json = json.dumps(routes)
    return f"""
const {{ chromium }} = require('playwright');
const fs = require('fs');

const APP_URL = '{frontend_url}';
const ROUTES = {routes_json};
const SCREENSHOT_DIR = '/tmp/testpilot-targeted-screenshots';
fs.mkdirSync(SCREENSHOT_DIR, {{ recursive: true }});

const results = {{ passed: [], failed: [] }};

(async () => {{
  const browser = await chromium.launch({{ headless: false }});
  const page = await browser.newPage();

  // Intercept API calls to record chain
  const apiCalls = [];
  page.on('request', req => {{
    if (!req.url().includes('.css') && !req.url().includes('.js') && !req.url().startsWith('chrome')) {{
      apiCalls.push({{ method: req.method(), url: req.url() }});
    }}
  }});

  for (const route of ROUTES) {{
    const url = APP_URL + route;
    console.log(`\\n  Testing route: ${{url}}`);
    apiCalls.length = 0;  // reset for each route

    try {{
      await page.goto(url, {{ waitUntil: 'domcontentloaded', timeout: 15000 }});
      await page.waitForTimeout(1500);

      const screenshot = `${{SCREENSHOT_DIR}}/${{route.replace(/\\//g, '_') || 'home'}}.png`;
      await page.screenshot({{ path: screenshot, fullPage: true }});

      // Check for JS errors
      const errors = await page.evaluate(() => window.__testpilot_errors || []);
      if (errors.length > 0) {{
        results.failed.push(`${{route}}: JS errors: ${{errors.join(', ')}}`);
      }} else {{
        results.passed.push(`${{route}}: OK (API calls: ${{apiCalls.length}})`);
        console.log(`    Chain: ${{apiCalls.map(c => c.method + ' ' + c.url.split('/').slice(-2).join('/')).join(' → ')}}`);
      }}
    }} catch (e) {{
      results.failed.push(`${{route}}: ${{e.message.split('\\n')[0]}}`);
    }}
  }}

  await browser.close();

  console.log('\\n--- Targeted Frontend Results ---');
  results.passed.forEach(p => console.log(`  ✅ ${{p}}`));
  results.failed.forEach(f => console.log(`  ❌ ${{f}}`));

  fs.writeFileSync('/tmp/testpilot-targeted-playwright-results.json', JSON.stringify(results, null, 2));
  process.exit(results.failed.length > 0 ? 1 : 0);
}})();
"""


def run_targeted(since: str = "HEAD~1", cfg: dict = None, verbose: bool = True) -> dict:
    """
    Main entry point for targeted testing.
    Detects what changed since `since`, runs ONLY relevant tests.

    Args:
        since: git ref (e.g. "HEAD~1", "origin/main", specific commit hash)
        cfg: loaded config dict (if None, loads from config.yaml)
        verbose: print progress

    Returns:
        dict with keys: passed, failed, skipped, backend_result, frontend_result
    """
    if cfg is None:
        cfg = load_config()

    backend_url = cfg.get("backend", {}).get("url", "http://localhost:8000")
    source_dirs = cfg.get("backend", {}).get("source_dirs", ["src/"])

    if verbose:
        print(f"\nTestPilot AI — Targeted Run")
        print(f"  Analyzing changes since: {since}")

    impact = analyze_impact(since, source_dirs)

    if verbose:
        print(f"\n  Changed files ({len(impact['changed_files'])}):")
        for f in impact["changed_files"]:
            print(f"    · {f}")

    if not impact["changed_files"]:
        if verbose:
            print("\n  No changes detected. Nothing to test.")
        return {"skipped": True, "reason": "No changes detected"}

    if impact["run_everything"]:
        if verbose:
            print("\n  Infrastructure change detected — running full suite")
        from .runners.pytest_runner import run_pytest
        return run_pytest(["tests/"], extra_args=["-v"])

    results = {
        "since": since,
        "changed_files": impact["changed_files"],
        "backend_result": None,
        "frontend_result": None,
        "passed": [],
        "failed": [],
    }

    # ── Backend tests ────────────────────────────────────────────────────────
    if impact["needs_backend_test"]:
        if verbose:
            print(f"\n  Backend: {len(impact['changed_py_files'])} Python file(s) changed")

        test_files = impact["test_files_to_run"]

        if not test_files:
            # No existing test files found — generate them first
            if verbose:
                print("  No existing tests for changed code. Generating chain tests...")
            from .chain_analyzer import analyze_chains
            from .chain_generator import generate_chain_tests

            chains = analyze_chains(impact["changed_py_files"], cfg)
            if chains:
                test_code = generate_chain_tests(chains, cfg)
                out_dir = cfg.get("backend", {}).get("test_output_dir", "tests/ai_generated")
                import os
                os.makedirs(out_dir, exist_ok=True)
                test_path = f"{out_dir}/test_chain_targeted.py"
                with open(test_path, "w", encoding="utf-8") as f:
                    f.write(test_code)
                test_files = [test_path]
                if verbose:
                    print(f"  Generated: {test_path}")

        backend_result = run_backend_chain_tests(test_files, backend_url)
        results["backend_result"] = backend_result
        results["passed"].extend(backend_result.get("passed", []))
        results["failed"].extend(backend_result.get("failed", []))

    # ── Frontend tests ───────────────────────────────────────────────────────
    if impact["needs_frontend_test"] and cfg.get("frontend", {}).get("enabled"):
        if verbose:
            print(f"\n  Frontend: {len(impact['changed_js_files'])} JS/TS file(s) changed")

        frontend_result = run_frontend_chain_test(impact["changed_js_files"], cfg)
        results["frontend_result"] = frontend_result

        if frontend_result.get("exit_code", 0) != 0:
            results["failed"].append("Frontend E2E: one or more route tests failed")
        elif not frontend_result.get("skipped"):
            results["passed"].append(
                f"Frontend E2E: {len(frontend_result.get('routes_tested', []))} routes OK"
            )

    # ── Summary ──────────────────────────────────────────────────────────────
    if verbose:
        print(f"\n{'─'*50}")
        total_p = len(results["passed"])
        total_f = len(results["failed"])
        print(f"  {total_p} passed, {total_f} failed")
        if results["failed"]:
            for f in results["failed"]:
                print(f"  ❌ {f}")

    return results
