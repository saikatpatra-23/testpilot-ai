"""
TestPilot AI — pytest plugin

Adds --testpilot-diff flag to pytest.
When used, pytest automatically runs ONLY tests relevant to changed code.

Install once (pip install testpilot-ai), then:
    pytest --testpilot-diff          # test only what changed since HEAD~1
    pytest --testpilot-diff=origin/main   # test only what changed vs main
    pytest --testpilot-watch         # watch mode inside pytest
"""
import pytest
from pathlib import Path


def pytest_addoption(parser):
    group = parser.getgroup("testpilot", "TestPilot AI — targeted testing")
    group.addoption(
        "--testpilot-diff",
        nargs="?",
        const="HEAD~1",
        default=None,
        metavar="GIT_REF",
        help="Run only tests for code changed since GIT_REF (default: HEAD~1)",
    )
    group.addoption(
        "--testpilot-generate",
        action="store_true",
        default=False,
        help="Auto-generate missing chain tests before running",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "testpilot_affected: marks tests as affected by current git diff (set by TestPilot)",
    )
    # Register feature marker
    config.addinivalue_line(
        "markers",
        "feature(name): mark test as belonging to a named feature",
    )


def pytest_collection_modifyitems(session, config, items):
    """
    If --testpilot-diff is passed, filter test items to only those
    relevant to changed files.
    """
    since = config.getoption("--testpilot-diff", default=None)
    if since is None:
        return  # normal pytest run — don't filter anything

    try:
        from .diff_detector import analyze_impact, find_test_files_for_changed
    except ImportError:
        return

    impact = analyze_impact(since)
    relevant_test_files = set(impact.get("test_files_to_run", []))

    if impact.get("run_everything"):
        # Infrastructure change — run all tests, don't filter
        print(f"\n[TestPilot] Infrastructure change detected — running full suite")
        return

    if not relevant_test_files:
        # Generate tests if flag set
        if config.getoption("--testpilot-generate", default=False):
            print(f"\n[TestPilot] No existing tests found. Generating...")
            _auto_generate(impact, config)
            # Re-detect after generation
            impact = analyze_impact(since)
            relevant_test_files = set(impact.get("test_files_to_run", []))

    if not relevant_test_files:
        print(f"\n[TestPilot] No relevant tests found for changed files: {impact['changed_py_files']}")
        print(f"[TestPilot] Run with --testpilot-generate to auto-generate chain tests")
        # Skip all items (nothing relevant to run)
        for item in items:
            item.add_marker(pytest.mark.skip(reason="Not affected by current changes (TestPilot)"))
        return

    changed_stems = {Path(f).stem for f in impact["changed_py_files"]}
    print(f"\n[TestPilot] Changed: {impact['changed_py_files']}")
    print(f"[TestPilot] Running targeted tests: {sorted(relevant_test_files)}")

    # Mark items not in relevant files as skip
    skipped = 0
    kept = 0
    for item in items:
        item_file = str(item.fspath)
        item_file_norm = item_file.replace("\\", "/")

        is_relevant = any(
            rf.replace("\\", "/") in item_file_norm or item_file_norm.endswith(rf)
            for rf in relevant_test_files
        )

        # Also keep if test name contains a changed module name
        if not is_relevant:
            is_relevant = any(stem in item.name.lower() for stem in changed_stems)

        if not is_relevant:
            item.add_marker(pytest.mark.skip(
                reason=f"Not affected by changes to {impact['changed_py_files']} (TestPilot)"
            ))
            skipped += 1
        else:
            item.add_marker(pytest.mark.testpilot_affected)
            kept += 1

    print(f"[TestPilot] Running {kept} test(s), skipping {skipped} unaffected test(s)\n")


def _auto_generate(impact: dict, config):
    """Auto-generate chain tests for changed files."""
    try:
        from .config import load_config
        from .chain_analyzer import analyze_chains
        from .chain_generator import generate_chain_tests
        import os

        cfg = load_config()
        chains = analyze_chains(impact["changed_py_files"], cfg)
        if not chains:
            return

        test_code = generate_chain_tests(chains, cfg)
        out_dir = cfg.get("backend", {}).get("test_output_dir", "tests/ai_generated")
        os.makedirs(out_dir, exist_ok=True)
        test_path = f"{out_dir}/test_chain_targeted.py"
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(test_code)
        print(f"[TestPilot] Generated: {test_path}")
    except Exception as e:
        print(f"[TestPilot] Generation failed: {e}")
