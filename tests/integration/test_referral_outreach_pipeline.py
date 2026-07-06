"""
Integration Tests: Referral Outreach Pipeline
(pipelines/linkedin_outreach/services/referral_outreach.py)

Tests the discover and send phases: candidate finding,
template rendering, status transitions, and multi-job tracking.

Run with:
    pytest tests/integration/test_referral_outreach_pipeline.py -v
"""

import pytest
from unittest.mock import MagicMock


def _make_employee_referral(name="Employee", profile_url=None, company="RefCo",
                             job_id="1", job_url="https://refco.com/j/1", status="pending"):
    profile_url = profile_url or f"https://linkedin.com/in/{name.lower().replace(' ', '')}/"
    return {
        "JobID": job_id,
        "CompanyName": company,
        "Company_URL": f"https://linkedin.com/company/{company.lower().replace(' ', '')}/",
        "JobTitle": "Data Engineer",
        "Job_URL": job_url,
        "Referral_Person_Name": name,
        "Referral_Person_Profile_URL": profile_url,
        "Referral_Source": "existing employee",
        "Referral_Status": status,
        "Outreach_Message": "",
        "Response_Notes": "",
        "DateTime": "2025-01-01 10:00:00",
    }


class TestReferralOutreachLocal:
    """Tests for Referral Outreach pipeline under local storage."""

    def test_discover_saves_employee_referral(self, local_user):
        """Referral outreach discover phase saves candidate to referrals table."""
        from core.storage.database import add_or_update_referral, load_all_referrals

        add_or_update_referral(_make_employee_referral(name="Alice Employee"))

        referrals = load_all_referrals()
        assert len(referrals) == 1
        assert referrals[0]["Referral_Source"] == "existing employee"
        assert referrals[0]["Referral_Status"] == "pending"

    def test_send_phase_updates_status_to_sent(self, local_user):
        """After sending referral message, status should be 'sent'."""
        from core.storage.database import add_or_update_referral, load_all_referrals

        ref = _make_employee_referral(name="Bob Employee", status="pending")
        add_or_update_referral(ref)

        # Simulate send phase: update status to 'sent'
        ref["Referral_Status"] = "sent"
        ref["Outreach_Message"] = "Hi Bob, I saw your company..."
        add_or_update_referral(ref)

        referrals = load_all_referrals()
        assert referrals[0]["Referral_Status"] == "sent"
        assert referrals[0]["Outreach_Message"] != ""

    def test_referral_template_renders_correctly(self, local_user):
        """Referral message template should substitute all known placeholders."""
        config = local_user["config"]
        template = config["referral_outreach"]["message_template"]
        profile = config["profile"]

        rendered = template
        replacements = {
            "{RECEIVER_NAME}": "Charlie",
            "{COMPANY}": "TechCorp",
            "{JOB_URL}": "https://techcorp.com/j/1",
            "{FIRST_NAME}": profile.get("first_name", ""),
            "{LAST_NAME}": profile.get("last_name", ""),
            "{EMAIL}": profile.get("email", ""),
            "{PHONE_NUMBER}": str(profile.get("phone", "")),
            "{EXPERIENCE}": str(profile.get("experience", "")),
            "{LINKEDIN_PROFILE_URL}": profile.get("linkedin_url", ""),
        }
        for k, v in replacements.items():
            rendered = rendered.replace(k, str(v))

        assert "Charlie" in rendered
        assert "{RECEIVER_NAME}" not in rendered

    def test_deduplication_across_different_jobs(self, local_user):
        """Same employee reached for different jobs should be tracked separately."""
        from core.storage.database import add_or_update_referral, load_all_referrals

        profile_url = "https://linkedin.com/in/multiemployee/"
        add_or_update_referral(_make_employee_referral(
            name="Multi Emp", profile_url=profile_url, job_id="1", company="Co1",
            job_url="https://co1.com/j/1"
        ))
        add_or_update_referral(_make_employee_referral(
            name="Multi Emp", profile_url=profile_url, job_id="2", company="Co2",
            job_url="https://co2.com/j/2"
        ))

        referrals = load_all_referrals()
        # Same person, different jobs → 2 separate rows
        assert len(referrals) == 2

    def test_completed_referral_count_per_company(self, local_user):
        """get_completed_referral_count returns correct count for a company+job."""
        from core.storage.database import add_or_update_referral, get_completed_referral_count

        company = "TargetCo"
        job_id = "3"
        for i in range(3):
            add_or_update_referral(_make_employee_referral(
                name=f"Emp{i}",
                profile_url=f"https://linkedin.com/in/emp{i}/",
                company=company,
                job_id=job_id,
                status="sent"
            ))

        count = get_completed_referral_count(company, job_id=job_id)
        assert count == 3

    def test_referral_not_sent_does_not_count(self, local_user):
        """Pending referrals should not count towards the completed count."""
        from core.storage.database import add_or_update_referral, get_completed_referral_count

        company = "PendingCo"
        job_id = "5"
        add_or_update_referral(_make_employee_referral(
            name="Pending Emp",
            profile_url="https://linkedin.com/in/pending/",
            company=company, job_id=job_id, status="pending"
        ))

        count = get_completed_referral_count(company, job_id=job_id)
        assert count == 0

    def test_employee_outreach_progress_tracking(self, local_user):
        """get_employee_outreach_progress() returns correct sent/replied breakdown."""
        from core.storage.database import add_or_update_referral, get_employee_outreach_progress

        company = "ProgressRefCo"
        add_or_update_referral(_make_employee_referral(
            name="E1", profile_url="https://linkedin.com/in/e1/", company=company, status="sent"
        ))
        add_or_update_referral(_make_employee_referral(
            name="E2", profile_url="https://linkedin.com/in/e2/", company=company, status="replied"
        ))
        add_or_update_referral(_make_employee_referral(
            name="E3", profile_url="https://linkedin.com/in/e3/", company=company, status="pending"
        ))

        progress = get_employee_outreach_progress(company)
        assert progress["sent"] == 2   # sent + replied
        assert progress["replied"] == 1

    def test_edit_referral_contact_row(self, local_user):
        """edit_referral_contact_row() should update all fields correctly."""
        from core.storage.database import add_or_update_referral, edit_referral_contact_row, load_all_referrals

        add_or_update_referral(_make_employee_referral(name="EditEmp", status="pending"))
        referrals = load_all_referrals()
        ref_id = referrals[0]["ReferralID"]

        edit_referral_contact_row(ref_id, {
            "Referral_Status": "sent",
            "Outreach_Message": "Updated message",
            "Response_Notes": "No response yet",
        })

        updated = load_all_referrals()[0]
        assert updated["Referral_Status"] == "sent"
        assert updated["Outreach_Message"] == "Updated message"


class TestReferralOutreachSheets:
    """Tests for Referral Outreach pipeline under Google Sheets storage."""

    def test_discover_saves_to_sheets(self, sheets_user):
        """Referral candidate should be saved to the mock Sheets backend."""
        from core.storage.database import add_or_update_referral, load_all_referrals

        add_or_update_referral(_make_employee_referral(
            name="Sheets Employee",
            profile_url="https://linkedin.com/in/sheetsemployee/"
        ))

        referrals = load_all_referrals()
        assert len(referrals) == 1

    def test_send_phase_in_sheets(self, sheets_user):
        """Status update to 'sent' should persist in Sheets mock."""
        from core.storage.database import add_or_update_referral, load_all_referrals

        url = "https://linkedin.com/in/sheetsempsend/"
        ref = _make_employee_referral(profile_url=url, status="pending")
        add_or_update_referral(ref)

        ref["Referral_Status"] = "sent"
        add_or_update_referral(ref)

        referrals = load_all_referrals()
        assert referrals[0]["Referral_Status"] == "sent"

    def test_multiple_jobs_same_employee_in_sheets(self, sheets_user):
        """Same employee for two jobs should produce 2 rows in Sheets."""
        from core.storage.database import add_or_update_referral, load_all_referrals

        url = "https://linkedin.com/in/multijobsheetsempl/"
        add_or_update_referral(_make_employee_referral(profile_url=url, job_id="1", company="CoS1"))
        add_or_update_referral(_make_employee_referral(profile_url=url, job_id="2", company="CoS2"))

        referrals = load_all_referrals()
        assert len(referrals) == 2
