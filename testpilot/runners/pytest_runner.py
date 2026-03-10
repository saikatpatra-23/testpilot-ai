"""
TestPilot AI — pytest Runner
Runs tests and returns structured results.
"""
import subprocess
import sys
import json
from pathlib import Path


def run_pytest(test_paths: list[str], extra_args: list[str] = None) -> dict:
    """
    Run pytest on given paths, return structured results.
    Returns: {passed, failed, errors, output, exit_code}
    """
    args = [
        sys.executable, "-m", "pytest",
        "--tb=short",
        "--json-report",
        "--json-report-file=/tmp/testpilot-report.json",
        "-v",
    ] + (extra_args or []) + test_paths

    result = subprocess.run(args, capture_output=True, text=True)
    output = result.stdout + result.stderr

    # Try to parse JSON report
    report_path = Path("/tmp/testpilot-report.json")
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text())
            summary = report.get("summary", {})
            passed_tests = [t["nodeid"] for t in report.get("tests", []) if t["outcome"] == "passed"]
            failed_tests = [
                f"{t['nodeid']}: {t.get('call', {}).get('longrepr', '')[:200]}"
                for t in report.get("tests", [])
                if t["outcome"] in ("failed", "error")
            ]
            return {
                "passed": passed_tests,
                "failed": failed_tests,
                "errors": [],
                "output": output,
                "exit_code": result.returncode,
                "summary": summary,
            }
        except Exception:
            pass

    # Fallback: parse stdout
    passed, failed, errors = [], [], []
    for line in output.split("\n"):
        if " PASSED" in line:
            passed.append(line.strip())
        elif " FAILED" in line:
            failed.append(line.strip())
        elif " ERROR" in line:
            errors.append(line.strip())

    return {
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "output": output,
        "exit_code": result.returncode,
    }
