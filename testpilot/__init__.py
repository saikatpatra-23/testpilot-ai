"""
TestPilot AI — Public API

Call from anywhere in your codebase:

    import testpilot

    # Test only what changed since last commit
    results = testpilot.run_diff()

    # Test only what changed since a specific branch/commit
    results = testpilot.run_diff("origin/main")

    # Test a specific file that you just changed
    results = testpilot.run_file("src/api/search.py")

    # Test a named feature
    results = testpilot.run_feature("search")

    # Watch for changes and auto-test (like jest --watch)
    testpilot.watch()
"""

__version__ = "0.1.0"


def run_diff(since: str = "HEAD~1", config_path: str = None, verbose: bool = True) -> dict:
    """
    Run tests ONLY for code that changed since `since`.

    Args:
        since: git ref — "HEAD~1" (last commit), "origin/main" (vs main branch),
               or a commit hash
        config_path: path to config.yaml (None = auto-detect)
        verbose: print progress to stdout

    Returns:
        dict: {passed: [...], failed: [...], changed_files: [...], ...}

    Example:
        # In a pre-commit hook, CI step, or anywhere in your code:
        results = testpilot.run_diff("HEAD~1")
        if results["failed"]:
            raise RuntimeError(f"Tests failed: {results['failed']}")
    """
    from .config import load_config
    from .targeted_runner import run_targeted
    cfg = load_config(config_path)
    return run_targeted(since=since, cfg=cfg, verbose=verbose)


def run_file(filepath: str, config_path: str = None, verbose: bool = True) -> dict:
    """
    Run chain tests for a specific changed source file.

    Args:
        filepath: path to the Python file you just changed
                  e.g. "src/api/search.py"

    Example:
        # After editing a file:
        results = testpilot.run_file("src/api/search.py")
    """
    from .config import load_config
    from .diff_detector import find_test_files_for_changed, find_affected_endpoints
    from .targeted_runner import run_backend_chain_tests
    from .chain_analyzer import analyze_chains
    from .chain_generator import generate_chain_tests
    import os

    cfg = load_config(config_path)
    backend_url = cfg.get("backend", {}).get("url", "http://localhost:8000")

    test_files = find_test_files_for_changed([filepath])

    if not test_files:
        if verbose:
            print(f"No existing tests for {filepath}. Generating chain tests...")
        chains = analyze_chains([filepath], cfg)
        if chains:
            test_code = generate_chain_tests(chains, cfg)
            out_dir = cfg.get("backend", {}).get("test_output_dir", "tests/ai_generated")
            os.makedirs(out_dir, exist_ok=True)
            import pathlib
            test_path = f"{out_dir}/test_chain_{pathlib.Path(filepath).stem}.py"
            with open(test_path, "w", encoding="utf-8") as f:
                f.write(test_code)
            test_files = [test_path]
            if verbose:
                print(f"Generated: {test_path}")

    return run_backend_chain_tests(test_files, backend_url)


def run_feature(feature_name: str, config_path: str = None, verbose: bool = True) -> dict:
    """
    Run all tests tagged with a feature name.
    Requires tests to be marked: @pytest.mark.feature("search")

    Example:
        results = testpilot.run_feature("search")
    """
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-v", "-m", f"feature_{feature_name}",
         "--tb=short"],
        capture_output=False
    )
    return {"exit_code": result.returncode, "feature": feature_name}


def run_all(config_path: str = None) -> dict:
    """Run the full test suite (not targeted — use run_diff() for targeted)."""
    from .config import load_config
    from .__main__ import cmd_run
    cfg = load_config(config_path)

    class Args:
        config = config_path

    return cmd_run(Args(), cfg)


def watch(since: str = "HEAD", poll_interval: int = 3, config_path: str = None):
    """
    Watch for file changes and auto-run targeted tests.
    Like jest --watch but for your Python backend + React frontend.

    Args:
        poll_interval: seconds between checks (default 3)

    Example:
        testpilot.watch()  # keeps running, tests on every save
    """
    import time
    from .config import load_config
    from .diff_detector import get_changed_files

    cfg = load_config(config_path)
    print(f"\nTestPilot AI — Watch Mode (Ctrl+C to stop)\n")

    last_changed = set()

    while True:
        try:
            changed = set(get_changed_files("HEAD"))
            new_changes = changed - last_changed

            if new_changes:
                print(f"\n[{time.strftime('%H:%M:%S')}] Changes detected: {sorted(new_changes)}")
                from .targeted_runner import run_targeted
                run_targeted(since="HEAD", cfg=cfg, verbose=True)
                last_changed = changed

            time.sleep(poll_interval)

        except KeyboardInterrupt:
            print("\nWatch mode stopped.")
            break


def generate(filepath: str = None, since: str = None, config_path: str = None) -> str:
    """
    AI-generate chain tests for a file or changed files.

    Args:
        filepath: specific file to generate tests for
        since: generate for all files changed since this ref

    Returns:
        path to generated test file

    Example:
        test_path = testpilot.generate("src/api/search.py")
        # → "tests/ai_generated/test_chain_search.py"
    """
    from .config import load_config
    from .chain_analyzer import analyze_chains
    from .chain_generator import generate_chain_tests
    from .diff_detector import get_changed_files
    import os, pathlib

    cfg = load_config(config_path)

    files = [filepath] if filepath else get_changed_files(since or "HEAD~1")
    files = [f for f in files if f.endswith(".py")]

    if not files:
        print("No Python files to generate tests for.")
        return ""

    chains = analyze_chains(files, cfg)
    if not chains:
        print("No API chains detected.")
        return ""

    test_code = generate_chain_tests(chains, cfg)
    out_dir = cfg.get("backend", {}).get("test_output_dir", "tests/ai_generated")
    os.makedirs(out_dir, exist_ok=True)

    stem = pathlib.Path(files[0]).stem if len(files) == 1 else "api"
    out_path = f"{out_dir}/test_chain_{stem}.py"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(test_code)

    print(f"Generated: {out_path}")
    return out_path
