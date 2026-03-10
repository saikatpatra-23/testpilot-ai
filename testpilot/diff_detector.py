"""
TestPilot AI — Diff Detector

Answers: "Which files changed? Which API endpoints are affected? Which tests to run?"

Given a git diff, maps:
  changed source file → affected API endpoint → test file to run

This is the core of targeted testing — only run tests for what changed.
"""
import subprocess
import ast
import re
from pathlib import Path
from typing import Optional


def get_changed_files(since: str = "HEAD~1", staged_only: bool = False) -> list[str]:
    """Get list of changed files since a git ref."""
    if staged_only:
        cmd = ["git", "diff", "--cached", "--name-only"]
    else:
        cmd = ["git", "diff", "--name-only", since]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return []
    return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]


def get_changed_functions(filepath: str, since: str = "HEAD~1") -> list[str]:
    """
    Get function/method names that changed in a specific file.
    Uses git diff to find which line ranges changed, then maps to function names.
    """
    result = subprocess.run(
        ["git", "diff", since, "--unified=0", filepath],
        capture_output=True, text=True
    )
    if not result.stdout:
        return []

    # Extract changed line numbers from diff hunk headers: @@ -10,3 +10,5 @@
    changed_lines = set()
    for match in re.finditer(r'^\+\+\+ .*\n.*?@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@',
                              result.stdout, re.MULTILINE):
        start = int(match.group(1))
        count = int(match.group(2)) if match.group(2) else 1
        changed_lines.update(range(start, start + count))

    # Parse the file and find which functions contain those lines
    try:
        source = Path(filepath).read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception:
        return []

    affected_fns = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn_lines = set(range(node.lineno, node.end_lineno + 1))
            if fn_lines & changed_lines:
                affected_fns.append(node.name)

    return affected_fns


def find_affected_endpoints(changed_files: list[str], source_root: str = ".") -> list[dict]:
    """
    For each changed Python file, find which API endpoints it implements or affects.
    Returns list of: {file, endpoint, method, handler_fn}
    """
    affected = []

    # Patterns that indicate route definitions
    route_patterns = [
        # FastAPI
        r'@(?:app|router)\.(get|post|put|patch|delete)\(["\']([^"\']+)["\']',
        # Flask
        r'@(?:app|bp|blueprint)\.(route|get|post|put|delete|patch)\(["\']([^"\']+)["\']',
        # Django urls.py
        r'path\(["\']([^"\']+)["\'].*?(\w+)\.as_view|views\.(\w+)',
    ]

    for filepath in changed_files:
        if not filepath.endswith(".py"):
            continue
        try:
            source = Path(filepath).read_text(encoding="utf-8")
        except FileNotFoundError:
            continue

        for pattern in route_patterns:
            for match in re.finditer(pattern, source, re.IGNORECASE):
                groups = [g for g in match.groups() if g]
                if len(groups) >= 2:
                    method, path = groups[0].upper(), groups[1]
                    affected.append({
                        "file": filepath,
                        "endpoint": f"{method} {path}",
                        "method": method,
                        "path": path,
                    })

        # Also detect if the file contains functions that are CALLED by routes
        # (one level deep — important for service layer changes)
        changed_fns = get_changed_functions(filepath)
        if changed_fns:
            affected.append({
                "file": filepath,
                "changed_functions": changed_fns,
                "endpoint": None,  # indirect — need to find callers
            })

    return affected


def find_test_files_for_changed(
    changed_files: list[str],
    test_dirs: list[str] = None
) -> list[str]:
    """
    Given changed source files, find existing test files that cover them.

    Matching strategy (in order):
    1. Direct match: src/api/search.py → tests/test_chain_search.py
    2. AI-generated: src/api/search.py → tests/ai_generated/test_chain_search.py
    3. Keyword match: search in filename → test files containing "search"
    """
    if test_dirs is None:
        test_dirs = ["tests/", "test/"]

    test_files = []
    for td in test_dirs:
        p = Path(td)
        if p.exists():
            test_files.extend(p.rglob("test_*.py"))
            test_files.extend(p.rglob("*_test.py"))

    result = set()
    for changed in changed_files:
        stem = Path(changed).stem  # e.g. "search" from "src/api/search.py"

        for tf in test_files:
            tf_str = str(tf)
            # Direct name match
            if stem in tf.stem:
                result.add(tf_str)
                continue
            # Chain test naming convention
            if f"chain_{stem}" in tf.stem or f"test_{stem}" in tf.stem:
                result.add(tf_str)
                continue

    return sorted(result)


def analyze_impact(since: str = "HEAD~1", source_dirs: list[str] = None) -> dict:
    """
    Full impact analysis: what changed → what's affected → what to test.

    Returns:
    {
      "changed_files": [...],
      "changed_py_files": [...],
      "changed_js_files": [...],
      "affected_endpoints": [...],
      "test_files_to_run": [...],
      "needs_frontend_test": bool,
      "needs_backend_test": bool,
    }
    """
    all_changed = get_changed_files(since)

    py_files  = [f for f in all_changed if f.endswith(".py")]
    js_files  = [f for f in all_changed if f.endswith((".js", ".jsx", ".ts", ".tsx"))]
    css_files = [f for f in all_changed if f.endswith((".css", ".scss", ".less"))]

    # Config/infra changes → run everything
    infra_changed = any(
        f in all_changed for f in ["requirements.txt", "package.json", "pyproject.toml",
                                    "docker-compose.yml", ".env"]
    )

    affected_endpoints = find_affected_endpoints(py_files)
    test_files = find_test_files_for_changed(py_files)

    return {
        "changed_files": all_changed,
        "changed_py_files": py_files,
        "changed_js_files": js_files,
        "affected_endpoints": affected_endpoints,
        "test_files_to_run": test_files,
        "needs_backend_test": len(py_files) > 0,
        "needs_frontend_test": len(js_files) > 0 or len(css_files) > 0,
        "run_everything": infra_changed,
        "since": since,
    }
