"""
TestPilot AI — Telegram Reporter
Sends test results to a Telegram chat/group.
"""
import httpx
from datetime import datetime


class TelegramReporter:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = str(chat_id)
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    def send(self, message: str) -> bool:
        try:
            r = httpx.post(f"{self.base_url}/sendMessage", json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML"
            }, timeout=10)
            return r.status_code == 200
        except Exception as e:
            print(f"[telegram] Failed to send: {e}")
            return False

    def report_results(self, results: dict, project: str = "TestPilot", branch: str = "main") -> bool:
        passed = len(results.get("passed", []))
        failed = len(results.get("failed", []))
        errors = len(results.get("errors", []))
        total = passed + failed + errors

        status_icon = "✅" if failed == 0 and errors == 0 else "❌"
        timestamp = datetime.now().strftime("%d %b %Y, %H:%M")

        lines = [
            f"{status_icon} <b>TestPilot AI — {project}</b>",
            f"Branch: <code>{branch}</code> | {timestamp}",
            f"",
            f"Total: {total} | Passed: {passed} | Failed: {failed} | Errors: {errors}",
        ]

        if failed > 0:
            lines.append("\n<b>Failed:</b>")
            for f in results["failed"][:5]:
                lines.append(f"  • {f}")
            if len(results["failed"]) > 5:
                lines.append(f"  ... and {len(results['failed']) - 5} more")

        if errors > 0:
            lines.append("\n<b>Errors:</b>")
            for e in results["errors"][:3]:
                lines.append(f"  ⚠ {e}")

        return self.send("\n".join(lines))

    def report_pytest(self, pytest_output: str, project: str = "TestPilot") -> bool:
        """Parse pytest output and send summary."""
        lines = pytest_output.strip().split("\n")
        summary_line = ""
        for line in reversed(lines):
            if "passed" in line or "failed" in line or "error" in line:
                summary_line = line.strip()
                break

        failed = "failed" in summary_line or "error" in summary_line
        icon = "❌" if failed else "✅"
        timestamp = datetime.now().strftime("%d %b %Y, %H:%M")

        message = f"{icon} <b>{project} — pytest</b>\n{timestamp}\n\n<code>{summary_line}</code>"
        return self.send(message)
