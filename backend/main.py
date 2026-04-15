"""
TestPilot AI — Cloud Backend
Handles test generation via Claude API.
Users don't need their own API key.
"""

import os
import sqlite3
from datetime import datetime
from contextlib import contextmanager

import anthropic
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ─── Config ──────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
FREE_MONTHLY_LIMIT = 20
GUMROAD_PRODUCT = "testpilot-ai-pro"
DB_PATH = os.environ.get("DB_PATH", "usage.db")

# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(title="TestPilot AI API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# ─── Database ─────────────────────────────────────────────────────────────────

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usage (
                machine_id TEXT NOT NULL,
                month      TEXT NOT NULL,
                count      INTEGER DEFAULT 0,
                PRIMARY KEY (machine_id, month)
            )
        """)


init_db()


def get_month_usage(machine_id: str) -> int:
    month = datetime.now().strftime("%Y-%m")
    with get_db() as conn:
        row = conn.execute(
            "SELECT count FROM usage WHERE machine_id=? AND month=?",
            (machine_id, month)
        ).fetchone()
    return row["count"] if row else 0


def increment_usage(machine_id: str) -> int:
    month = datetime.now().strftime("%Y-%m")
    with get_db() as conn:
        conn.execute("""
            INSERT INTO usage (machine_id, month, count) VALUES (?, ?, 1)
            ON CONFLICT(machine_id, month) DO UPDATE SET count = count + 1
        """, (machine_id, month))
        row = conn.execute(
            "SELECT count FROM usage WHERE machine_id=? AND month=?",
            (machine_id, month)
        ).fetchone()
    return row["count"]

# ─── License check ────────────────────────────────────────────────────────────

async def verify_gumroad_license(license_key: str) -> bool:
    if not license_key or len(license_key) < 8:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://api.gumroad.com/v2/licenses/verify",
                data={
                    "product_permalink": GUMROAD_PRODUCT,
                    "license_key": license_key,
                }
            )
            return r.json().get("success", False)
    except Exception:
        return False

# ─── Models ──────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    code: str
    filename: str
    machine_id: str
    license_key: str = ""


class GenerateResponse(BaseModel):
    tests: str
    test_filename: str
    used: int
    limit: int
    plan: str

# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.3.0"}


@app.get("/usage/{machine_id}")
async def usage_status(machine_id: str, license_key: str = ""):
    is_pro = await verify_gumroad_license(license_key) if license_key else False
    used = get_month_usage(machine_id)
    return {
        "plan": "pro" if is_pro else "free",
        "used": used,
        "limit": FREE_MONTHLY_LIMIT,
        "remaining": None if is_pro else max(0, FREE_MONTHLY_LIMIT - used),
    }


@app.post("/generate", response_model=GenerateResponse)
async def generate_tests(req: GenerateRequest):
    # Input validation
    if not req.code.strip():
        raise HTTPException(400, "No code provided")
    if not req.machine_id:
        raise HTTPException(400, "machine_id required")
    if len(req.code) > 60_000:
        raise HTTPException(400, "File too large (max 60 KB)")

    # License check
    is_pro = await verify_gumroad_license(req.license_key)

    # Quota check (server-side enforcement)
    used = get_month_usage(req.machine_id)
    if not is_pro and used >= FREE_MONTHLY_LIMIT:
        raise HTTPException(
            429,
            f"Free limit reached ({FREE_MONTHLY_LIMIT}/month). "
            "Upgrade to Pro: https://classy5b.gumroad.com/l/testpilot-ai-pro"
        )

    # Generate with Claude Haiku (fast + cheap)
    if not ANTHROPIC_API_KEY:
        raise HTTPException(500, "API key not configured on server")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    base_name = req.filename.removesuffix(".py")
    test_filename = f"test_ai_{base_name}.py"

    prompt = f"""You are an expert Python test engineer. Write comprehensive pytest unit tests for the code below.

Rules:
- pytest framework only, no unittest classes
- Test function names: test_<function>_<scenario>
- Cover: happy path, edge cases, null/empty inputs, boundary values, exceptions
- Mock external calls (HTTP, DB, file I/O) with unittest.mock
- Each test must be independent and deterministic
- Add a one-line docstring per test
- Output ONLY the Python test file content — no markdown, no explanation

File: {req.filename}

```python
{req.code}
```"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    tests = message.content[0].text.strip()

    # Strip markdown fences if model wrapped the output
    for fence in ("```python\n", "```\n", "```python", "```"):
        if tests.startswith(fence):
            tests = tests[len(fence):]
    if tests.endswith("```"):
        tests = tests[:-3].rstrip()

    # Track usage
    new_count = increment_usage(req.machine_id)

    return GenerateResponse(
        tests=tests,
        test_filename=test_filename,
        used=new_count,
        limit=FREE_MONTHLY_LIMIT,
        plan="pro" if is_pro else "free",
    )
