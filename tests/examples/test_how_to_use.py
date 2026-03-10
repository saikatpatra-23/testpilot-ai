"""
HOW YOUR DEVELOPERS ACTUALLY USE TESTPILOT
===========================================
This file shows 3 usage patterns.
Copy the pattern that fits your team's workflow.
"""

# ─────────────────────────────────────────────────────────────────────────────
# PATTERN 1: Inline in your test file (no CLI needed)
#
# Developer edits src/api/search.py
# Adds this to the bottom of their test file
# Runs: python src/api/search.py  (or via VS Code)
# ─────────────────────────────────────────────────────────────────────────────

def run_inline_example():
    """
    Drop this at the bottom of any Python file you're working on.
    When you run the file directly, it tests itself.
    """
    import testpilot

    print("Running tests for my changed file...")
    results = testpilot.run_file("src/api/search.py")

    if results.get("failed"):
        print("TESTS FAILED:")
        for f in results["failed"]:
            print(f"  ❌ {f}")
        exit(1)
    else:
        print("✅ All tests passed")


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN 2: In conftest.py — auto-runs on every pytest session
#
# Copy this to your project's conftest.py.
# Every time anyone runs pytest, only changed tests run.
# ─────────────────────────────────────────────────────────────────────────────

# your_project/conftest.py:
#
# import testpilot
# from testpilot.interceptor import chain_interceptor  # makes fixture available
#
# The --testpilot-diff flag is added automatically to pytest once installed.
# Use it as:
#   pytest --testpilot-diff           # only tests for what changed
#   pytest --testpilot-diff=origin/main  # only tests changed vs main branch


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN 3: Pre-commit hook (runs before every git commit)
#
# Run: testpilot install-hooks
# OR manually add to .git/hooks/pre-commit:
# ─────────────────────────────────────────────────────────────────────────────

PRE_COMMIT_HOOK = """#!/bin/bash
# TestPilot AI pre-commit hook
# Runs ONLY tests for staged files before allowing commit

echo "TestPilot AI: Testing staged changes..."

python -m testpilot diff HEAD
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "❌ TestPilot: Tests failed. Fix before committing."
    echo "   To skip (not recommended): git commit --no-verify"
    exit 1
fi

echo "✅ TestPilot: All tests passed. Proceeding with commit."
exit 0
"""


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN 4: The chain_interceptor fixture in your team's tests
#
# Once testpilot-ai is installed, chain_interceptor is available in ALL tests.
# No import needed (registered as pytest plugin).
# ─────────────────────────────────────────────────────────────────────────────

import pytest
import httpx

# Backend must be running locally: python app.py / uvicorn app:app / flask run
BASE_URL = "http://localhost:8000"


def test_my_feature_chain(chain_interceptor):
    """
    Template: copy this pattern for any feature your team works on.

    Steps:
    1. Mock external deps (SOLR, Siebel) with what they'd normally return
    2. Call YOUR real API endpoint
    3. Assert what React frontend receives
    4. Assert the chain happened correctly (order, params)
    """
    # 1. Setup mocks for this feature's chain
    chain_interceptor.mock_solr("your_collection", results=[
        {"id": "item-001", "title": "Example Result", "status": "active"}
    ])
    chain_interceptor.mock_siebel("YourSiebelResource", response={
        "Id": "CRM-001", "Status": "Active"
    })

    # 2. Call your real backend (running locally)
    r = httpx.get(f"{BASE_URL}/api/your-endpoint", params={"q": "example"})

    # 3. Assert response to frontend
    assert r.status_code == 200
    data = r.json()
    assert "results" in data             # response has expected structure
    assert len(data["results"]) > 0      # data came through

    # 4. Assert the chain
    chain_interceptor.assert_solr_called_with(collection="your_collection")
    chain_interceptor.assert_siebel_called()
    chain_interceptor.assert_siebel_called_after_solr()   # order check


def test_my_feature_empty_state(chain_interceptor):
    """When SOLR returns nothing, Siebel must NOT be called."""
    chain_interceptor.mock_solr_empty("your_collection")

    r = httpx.get(f"{BASE_URL}/api/your-endpoint", params={"q": "no_results_xyz"})

    assert r.status_code == 200
    assert r.json()["results"] == []
    chain_interceptor.assert_siebel_not_called()          # critical guard


def test_my_feature_siebel_down(chain_interceptor):
    """When Siebel is down, return partial data — don't 500."""
    chain_interceptor.mock_solr("your_collection", results=[
        {"id": "item-001", "title": "Example"}
    ])
    chain_interceptor.mock_siebel_down()

    r = httpx.get(f"{BASE_URL}/api/your-endpoint", params={"q": "example"})

    assert r.status_code == 200          # graceful degradation — not 500
    chain_interceptor.assert_solr_called()
