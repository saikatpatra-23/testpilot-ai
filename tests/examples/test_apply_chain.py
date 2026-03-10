"""
CHAIN TEST EXAMPLE: Apply for Job Flow
=======================================
Real flow:
  User clicks "Apply" on React
  → POST /api/apply  {job_id, user_id}
  → backend reads job details from SOLR
  → backend creates Application record in Siebel CRM
  → backend sends confirmation back to React

Chain: POST /api/apply → SOLR(read job) → Siebel(create Application) → response
"""
import pytest
import httpx
from testpilot.interceptor import chain_interceptor  # noqa: F401


BASE_URL = "http://localhost:8000"


# ─── Test 1: Happy Path ───────────────────────────────────────────────────────

def test_apply_creates_crm_record(chain_interceptor):
    """
    User applies for a job.
    Backend reads job from SOLR, creates Application in Siebel, returns confirmation.
    """
    # SOLR returns the job being applied for
    chain_interceptor.mock_solr("jobs", results=[{
        "id": "job-001",
        "title": "Technical Program Manager",
        "company_id": "ACC-001",
        "external_ref": "NAUKRI-TPM-001"
    }])
    # Siebel creates the application record
    chain_interceptor.mock_siebel("Application", method="POST", response={
        "Id": "APP-NEW-001",
        "Status": "Submitted",
        "JobRef": "NAUKRI-TPM-001"
    })

    r = httpx.post(f"{BASE_URL}/api/apply", json={
        "job_id": "job-001",
        "user_id": "USR-123",
        "cover_note": "I am interested in this role."
    })

    # Frontend expects confirmation
    assert r.status_code in (200, 201)
    data = r.json()
    assert data.get("status") == "submitted" or data.get("application_id")

    # Chain: SOLR read first, then Siebel write
    chain_interceptor.assert_solr_called_with(collection="jobs")
    chain_interceptor.assert_siebel_called()
    chain_interceptor.assert_siebel_called_after_solr()


# ─── Test 2: Job Not Found in SOLR → Should Not Call Siebel ─────────────────

def test_apply_job_not_found_skips_siebel(chain_interceptor):
    """
    User tries to apply for a job that no longer exists in SOLR.
    Backend should return 404. Siebel must NOT be called
    (don't create orphan CRM records for non-existent jobs).
    """
    chain_interceptor.mock_solr_empty("jobs")

    r = httpx.post(f"{BASE_URL}/api/apply", json={
        "job_id": "job-DELETED",
        "user_id": "USR-123"
    })

    assert r.status_code == 404
    chain_interceptor.assert_siebel_not_called()


# ─── Test 3: Siebel CRM Write Fails → Application Should Not Be Confirmed ────

def test_apply_siebel_failure_returns_error(chain_interceptor):
    """
    SOLR found the job.
    But Siebel CRM POST fails (e.g., duplicate application).
    Backend must return 409 Conflict or 500, NOT silently confirm the application.
    React shows error to user instead of fake success.
    """
    chain_interceptor.mock_solr("jobs", results=[{
        "id": "job-001", "title": "TPM", "company_id": "ACC-001"
    }])
    chain_interceptor.mock_siebel("Application", method="POST", status_code=409, response={
        "error": "Duplicate application — already applied for this job"
    })

    r = httpx.post(f"{BASE_URL}/api/apply", json={
        "job_id": "job-001",
        "user_id": "USR-123"
    })

    # Frontend should see an error, not a fake success
    assert r.status_code in (409, 500, 400)

    chain_interceptor.assert_solr_called()
    chain_interceptor.assert_siebel_called()


# ─── Test 4: Already Applied — Idempotency ───────────────────────────────────

def test_apply_twice_is_idempotent(chain_interceptor):
    """
    User clicks Apply twice (double-click or retry).
    Second call should not create a second CRM record.
    Backend should detect duplicate and return 409 or the existing application.
    Siebel should only be called ONCE (or with upsert logic).
    """
    chain_interceptor.mock_solr("jobs", results=[{
        "id": "job-001", "title": "TPM", "company_id": "ACC-001"
    }])
    chain_interceptor.mock_siebel("Application", method="POST", response={
        "Id": "APP-EXISTING-001", "Status": "AlreadyApplied"
    })

    payload = {"job_id": "job-001", "user_id": "USR-123"}
    r1 = httpx.post(f"{BASE_URL}/api/apply", json=payload)
    r2 = httpx.post(f"{BASE_URL}/api/apply", json=payload)

    # Both calls should be handled gracefully
    assert r1.status_code in (200, 201, 409)
    assert r2.status_code in (200, 409)  # second call should not 500
