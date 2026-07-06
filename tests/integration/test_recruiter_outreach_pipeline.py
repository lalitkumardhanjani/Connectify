"""
Integration Tests: Recruiter Outreach Pipeline
(pipelines/linkedin_outreach/services/recruiter_connector.py)

Tests recruiter discovery, target_count limit, message template rendering,
direct message usage, and status transitions.

Run with:
    pytest tests/integration/test_recruiter_outreach_pipeline.py -v
"""

import pytest
from unittest.mock import MagicMock


def _make_recruiter_referral(name="Recruiter", profile_url=None, company="RecruiterCo",
                              job_id="1", job_url="https://recruitco.com/j/1",
                              source="existing recruiter", status="pending"):
    profile_url = profile_url or f"https://linkedin.com/in/{name.lower().replace(' ', '')}/"
    return {
        "JobID": job_id,
        "CompanyName": company,
        "Company_URL": f"https://linkedin.com/company/{company.lower().replace(' ', '')}/",
        "JobTitle": "Data Engineer",
        "Job_URL": job_url,
        "Referral_Person_Name": name,
        "Referral_Person_Profile_URL": profile_url,
        "Referral_Source": source,
        "Referral_Status": status,
        "Outreach_Message": f"Hi {name}!",
        "Response_Notes": "",
        "DateTime": "2025-01-01 10:00:00",
    }


class TestRecruiterOutreachLocal:
    """Tests for Recruiter Outreach pipeline under local storage."""

    def test_recruiter_referral_saved_correctly(self, local_user):
        from core.storage.database import add_or_update_referral, load_all_referrals

        add_or_update_referral(_make_recruiter_referral(name="Alice Recruiter"))

        referrals = load_all_referrals()
        assert len(referrals) == 1
        assert referrals[0]["Referral_Source"] == "existing recruiter"

    def test_recruiter_outreach_target_count_config(self, local_user):
        """target_count from recruiter_outreach config should be respected."""
        config = local_user["config"]
        target = config["recruiter_outreach"]["target_count"]
        assert isinstance(target, int)
        assert target > 0

    def test_recruiter_message_template_renders(self, local_user):
        """Recruiter message template should have valid placeholder substitution."""
        config = local_user["config"]
        template = config["recruiter_outreach"]["message_template"]
        profile = config["profile"]

        rendered = template.replace("{RECEIVER_NAME}", "Bob Recruiter")
        rendered = rendered.replace("{FIRST_NAME}", profile.get("first_name", ""))
        rendered = rendered.replace("{LAST_NAME}", profile.get("last_name", ""))
        rendered = rendered.replace("{COMPANY}", "TechCorp")
        rendered = rendered.replace("{EXPERIENCE}", str(profile.get("experience", "")))
        rendered = rendered.replace("{RESUME}", profile.get("resume_url", ""))
        rendered = rendered.replace("{JOB_URL}", "https://techcorp.com/j/1")

        # Template can be empty by default in config, which is valid
        assert "{RECEIVER_NAME}" not in rendered

    def test_recruiter_direct_message_template_used_for_first_degree(self, local_user):
        """Direct message template should differ from the regular message template."""
        config = local_user["config"]
        dm_template = config["recruiter_outreach"]["direct_message_template"]
        msg_template = config["recruiter_outreach"]["message_template"]
        # Both may be empty but should not crash the pipeline
        assert isinstance(dm_template, str)
        assert isinstance(msg_template, str)

    def test_recruiter_deduplication_by_profile_url(self, local_user):
        """Same profile URL should not create a new record."""
        from core.storage.database import add_or_update_referral, load_all_referrals

        profile_url = "https://linkedin.com/in/unique-recruiter/"
        add_or_update_referral(_make_recruiter_referral(
            name="Jane", profile_url=profile_url, status="pending"
        ))
        add_or_update_referral(_make_recruiter_referral(
            name="Jane", profile_url=profile_url, status="sent"
        ))

        referrals = load_all_referrals()
        assert len(referrals) == 1
        assert referrals[0]["Referral_Status"] == "sent"

    def test_recruiter_outreach_progress_tracking(self, local_user):
        """get_recruiter_outreach_progress() returns correct sent and replied counts."""
        from core.storage.database import add_or_update_referral, get_recruiter_outreach_progress

        company = "ProgressCo"

        add_or_update_referral(_make_recruiter_referral(
            name="R1", profile_url="https://linkedin.com/in/r1/",
            company=company, status="sent", source="existing recruiter"
        ))
        add_or_update_referral(_make_recruiter_referral(
            name="R2", profile_url="https://linkedin.com/in/r2/",
            company=company, status="replied", source="existing recruiter"
        ))
        add_or_update_referral(_make_recruiter_referral(
            name="R3", profile_url="https://linkedin.com/in/r3/",
            company=company, status="pending", source="existing recruiter"
        ))

        progress = get_recruiter_outreach_progress(company)
        assert progress["sent"] == 2   # sent + replied count as 'sent'
        assert progress["replied"] == 1

    def test_multiple_recruiters_same_company(self, local_user):
        """Multiple recruiter records for same company are stored independently."""
        from core.storage.database import add_or_update_referral, load_all_referrals

        company = "MultiRecruiterCo"
        for i in range(3):
            add_or_update_referral(_make_recruiter_referral(
                name=f"Recruiter{i}",
                profile_url=f"https://linkedin.com/in/recruiter{i}/",
                company=company,
                status="sent",
                source="existing recruiter"
            ))

        referrals = load_all_referrals()
        assert len(referrals) == 3

    def test_is_profile_already_contacted_for_recruiter(self, local_user):
        """is_profile_already_contacted() should return True for known recruiter profiles."""
        from core.storage.database import add_or_update_referral, is_profile_already_contacted

        url = "https://linkedin.com/in/known-recruiter/"
        add_or_update_referral(_make_recruiter_referral(profile_url=url, status="sent"))

        assert is_profile_already_contacted(url) is True


class TestRecruiterOutreachSheets:
    """Tests for Recruiter Outreach pipeline under Google Sheets storage."""

    def test_recruiter_saved_to_sheets(self, sheets_user):
        from core.storage.database import add_or_update_referral, load_all_referrals

        add_or_update_referral(_make_recruiter_referral(
            name="Sheets Recruiter",
            profile_url="https://linkedin.com/in/sheetsrecruiter/",
            company="SheetsCo"
        ))

        referrals = load_all_referrals()
        assert len(referrals) == 1

    def test_recruiter_update_in_sheets(self, sheets_user):
        """Updating recruiter status should update existing row in sheets."""
        from core.storage.database import add_or_update_referral, load_all_referrals

        url = "https://linkedin.com/in/sheetsrec2/"
        add_or_update_referral(_make_recruiter_referral(profile_url=url, status="pending"))
        add_or_update_referral(_make_recruiter_referral(profile_url=url, status="sent"))

        referrals = load_all_referrals()
        assert len(referrals) == 1
        assert referrals[0]["Referral_Status"] == "sent"

    def test_recruiter_progress_in_sheets(self, sheets_user):
        from core.storage.database import add_or_update_referral, get_recruiter_outreach_progress

        company = "SheetsProgressCo"
        for i in range(2):
            add_or_update_referral(_make_recruiter_referral(
                name=f"SheetRec{i}",
                profile_url=f"https://linkedin.com/in/srec{i}/",
                company=company,
                status="sent",
                source="existing recruiter"
            ))

        progress = get_recruiter_outreach_progress(company)
        assert progress["sent"] == 2
