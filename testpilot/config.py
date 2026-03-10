"""TestPilot AI — Config loader"""
import os
import yaml
from pathlib import Path


def load_config(path: str = None) -> dict:
    if path is None:
        # Look for config.yaml in cwd or parent dirs
        cwd = Path.cwd()
        for candidate in [cwd / "config.yaml", cwd.parent / "config.yaml"]:
            if candidate.exists():
                path = str(candidate)
                break
    if path is None:
        raise FileNotFoundError(
            "config.yaml not found. Copy config.example.yaml → config.yaml and fill in values."
        )
    with open(path) as f:
        cfg = yaml.safe_load(f)

    # Allow env var overrides for CI/CD
    if os.getenv("ANTHROPIC_API_KEY"):
        cfg.setdefault("anthropic", {})["api_key"] = os.getenv("ANTHROPIC_API_KEY")
    if os.getenv("SIEBEL_USERNAME"):
        cfg.setdefault("siebel", {}).setdefault("rest", {})["username"] = os.getenv("SIEBEL_USERNAME")
    if os.getenv("SIEBEL_PASSWORD"):
        cfg.setdefault("siebel", {}).setdefault("rest", {})["password"] = os.getenv("SIEBEL_PASSWORD")
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        cfg.setdefault("notifications", {}).setdefault("telegram", {})["bot_token"] = os.getenv("TELEGRAM_BOT_TOKEN")
    if os.getenv("TELEGRAM_CHAT_ID"):
        cfg.setdefault("notifications", {}).setdefault("telegram", {})["chat_id"] = os.getenv("TELEGRAM_CHAT_ID")

    return cfg
