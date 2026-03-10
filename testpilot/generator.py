"""
TestPilot AI — Chain Test Generator (CLI entry point)

Reads your Python API code → maps call chains → generates chain integration tests.

Usage:
    python -m testpilot generate --source src/api/search.py
    python -m testpilot generate --diff HEAD~1
"""
import argparse
import subprocess
import sys
from pathlib import Path

from .chain_analyzer import analyze_chains
from .chain_generator import generate_chain_tests
from .config import load_config


def get_changed_files(since: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", since],
        capture_output=True, text=True
    )
    return [f for f in result.stdout.strip().split("\n") if f.endswith(".py") and f]


def save_tests(source_path: str, test_code: str, output_dir: str) -> str:
    source = Path(source_path)
    test_name = f"test_chain_{source.stem}.py"
    out_path = Path(output_dir) / test_name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(test_code, encoding="utf-8")
    return str(out_path)


def main():
    parser = argparse.ArgumentParser(description="TestPilot AI — Generate chain tests")
    parser.add_argument("--source", nargs="+", help="Python API file(s)")
    parser.add_argument("--diff", help="Files changed since this git ref (e.g. HEAD~1)")
    parser.add_argument("--output", default=None)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    output_dir = args.output or cfg.get("backend", {}).get("test_output_dir", "tests/ai_generated")

    files = []
    if args.source:
        files = args.source
    elif args.diff:
        files = get_changed_files(args.diff)
        if not files:
            print(f"No Python files changed since {args.diff}")
            return
    else:
        for src_dir in cfg.get("backend", {}).get("source_dirs", ["src/"]):
            files.extend([str(p) for p in Path(src_dir).rglob("*.py")
                          if not p.name.startswith("test_")])

    if not files:
        print("No files. Use --source <file.py> or --diff HEAD~1")
        sys.exit(1)

    print(f"\nTestPilot AI — analyzing {len(files)} file(s) for call chains...\n")

    # Step 1: Analyze call chains across ALL provided files together
    source_codes = {}
    for f in files:
        p = Path(f)
        if p.exists():
            source_codes[f] = p.read_text(encoding="utf-8")

    print("  Mapping call chains with Claude...")
    chains = analyze_chains(list(source_codes.keys()), cfg)

    if not chains:
        print("  No API call chains detected. Make sure files contain API endpoint handlers.")
        sys.exit(1)

    print(f"  Found {len(chains)} chain(s):")
    for c in chains:
        deps = " → ".join(c.get("external_deps", []))
        print(f"    · {c.get('endpoint', '?')} [{deps}]")

    # Step 2: Generate chain integration tests
    print("\n  Generating chain integration tests...")
    combined_source = "\n\n".join(source_codes.values())
    test_code = generate_chain_tests(chains, cfg, combined_source)

    if not test_code:
        print("  Generation failed.")
        sys.exit(1)

    # Step 3: Save — one file covers all chains from the given source files
    stem = Path(files[0]).stem if len(files) == 1 else "api"
    out = save_tests(f"{stem}.py", test_code, output_dir)
    print(f"\n  [saved] → {out}")
    print(f"\nRun with: pytest {out} -v")


if __name__ == "__main__":
    main()
