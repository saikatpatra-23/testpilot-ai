"""
TestPilot AI — AI Test Generator
Reads your Python source files → generates pytest tests using Claude.
Usage:
    python -m testpilot.generator --source src/api/jobs.py
    python -m testpilot.generator --diff HEAD~1   # only changed files
"""
import argparse
import ast
import os
import subprocess
import sys
from pathlib import Path

import anthropic

from .config import load_config


SYSTEM_PROMPT = """You are TestPilot AI, an expert Python test engineer.
Given Python source code, generate comprehensive pytest test cases.

Rules:
1. Use pytest style (no unittest classes unless needed)
2. Use httpx for HTTP tests, unittest.mock for mocking
3. Cover: happy path, edge cases, validation errors, auth errors
4. For Siebel CRM calls — always add a mock so tests run without real Siebel
5. For SOLR calls — mock the HTTP call, validate query shape
6. Name tests descriptively: test_<function>_<scenario>
7. Add a module docstring explaining what's being tested
8. Return ONLY valid Python code, no explanations outside the code
"""


def extract_functions(source_code: str) -> list[str]:
    """Extract function/class names from Python source."""
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return []
    names = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
    return names


def generate_tests_for_file(source_path: str, cfg: dict, base_url: str = None) -> str:
    """Call Claude to generate tests for a single Python file."""
    source_code = Path(source_path).read_text(encoding="utf-8")
    functions = extract_functions(source_code)

    if not functions:
        print(f"  [skip] No functions found in {source_path}")
        return ""

    print(f"  [generate] {source_path} ({len(functions)} functions: {', '.join(functions[:5])}{'...' if len(functions) > 5 else ''})")

    client = anthropic.Anthropic(api_key=cfg["anthropic"]["api_key"])
    url_hint = f"\nBackend base URL for HTTP tests: {base_url}" if base_url else ""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"""Generate pytest tests for this Python file: {source_path}{url_hint}

Source code:
```python
{source_code}
```

Generate tests covering all public functions and classes."""
        }]
    )

    return message.content[0].text


def get_changed_files(since: str) -> list[str]:
    """Get Python files changed since a git ref."""
    result = subprocess.run(
        ["git", "diff", "--name-only", since],
        capture_output=True, text=True
    )
    files = [f for f in result.stdout.strip().split("\n") if f.endswith(".py") and f]
    return files


def save_generated_tests(source_path: str, test_code: str, output_dir: str) -> str:
    """Save generated test code to output directory."""
    source = Path(source_path)
    test_name = f"test_ai_{source.stem}.py"
    out_path = Path(output_dir) / test_name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(test_code, encoding="utf-8")
    return str(out_path)


def main():
    parser = argparse.ArgumentParser(description="TestPilot AI — Generate tests from source code")
    parser.add_argument("--source", nargs="+", help="Python file(s) to generate tests for")
    parser.add_argument("--diff", help="Generate tests for files changed since this git ref (e.g. HEAD~1)")
    parser.add_argument("--output", default=None, help="Output directory (overrides config)")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    output_dir = args.output or cfg.get("backend", {}).get("test_output_dir", "tests/ai_generated")
    base_url = cfg.get("backend", {}).get("url", "http://localhost:8000")

    # Determine which files to process
    files = []
    if args.source:
        files = args.source
    elif args.diff:
        files = get_changed_files(args.diff)
        if not files:
            print(f"No Python files changed since {args.diff}")
            return
        print(f"Changed files since {args.diff}: {files}")
    else:
        # Fall back to configured source dirs
        for src_dir in cfg.get("backend", {}).get("source_dirs", ["src/"]):
            files.extend([str(p) for p in Path(src_dir).rglob("*.py")
                          if not p.name.startswith("test_")])

    if not files:
        print("No files to process. Use --source <file.py> or --diff HEAD~1")
        sys.exit(1)

    print(f"\nTestPilot AI — generating tests for {len(files)} file(s)...\n")
    generated = []
    for f in files:
        if not Path(f).exists():
            print(f"  [skip] {f} not found")
            continue
        test_code = generate_tests_for_file(f, cfg, base_url)
        if test_code:
            out = save_generated_tests(f, test_code, output_dir)
            generated.append(out)
            print(f"  [saved] → {out}")

    print(f"\nDone. {len(generated)} test file(s) generated in {output_dir}/")
    print("Run them with: pytest tests/ai_generated/ -v")


if __name__ == "__main__":
    main()
