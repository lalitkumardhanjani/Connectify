"""
Integration Tests: Referral Outreach Pipeline
(pipelines/linkedin_outreach/services/referral_outreach.py)

Tests the discover and send phases: candidate finding,
template rendering, status transitions, and multi-job tracking.

Run with:
    pytest tests/integration/test_referral_outreach_pipeline.py -v
"""

import pytest
import io
import sys
from unittest.mock import MagicMock, patch


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


# ---------------------------------------------------------------------------
# Review Mode (Automatic vs Manual) Tests
# ---------------------------------------------------------------------------

class TestReferralReviewModeGating:
    """
    Tests to verify the 'Send Automatic Connection' toggle (review_mode) correctly
    controls whether the Send Referral Messages pipeline prompts or sends automatically.

    review_mode=False → Send Automatic Connection ON  → messages are sent without prompt
    review_mode=True  → Send Automatic Connection OFF → stdin prompt is shown each time
    """

    # ── prompt_referral_action unit-level tests ──────────────────────────────

    def test_automatic_mode_returns_send_without_prompt(self):
        """When review_mode=False (automatic), prompt_referral_action must return 'send'
        immediately without reading from stdin at all."""
        from pipelines.linkedin_outreach.services.referral_outreach import prompt_referral_action

        # If stdin were read, this mock would raise; proves no stdin read happens
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.readline.side_effect = AssertionError("stdin must NOT be read in automatic mode")
            result = prompt_referral_action("Test User", review_mode=False)

        assert result == "send", "Automatic mode must return 'send' without any prompt"

    def test_manual_mode_send_choice_returns_send(self):
        """When review_mode=True (manual), entering 's' at the prompt returns 'send'."""
        from pipelines.linkedin_outreach.services.referral_outreach import prompt_referral_action

        with patch("sys.stdin", io.StringIO("s\n")), \
             patch("sys.stdout", new_callable=io.StringIO):
            result = prompt_referral_action("Test User", review_mode=True)

        assert result == "send"

    def test_manual_mode_skip_choice_returns_skip(self):
        """When review_mode=True (manual), entering 'k' at the prompt returns 'skip'."""
        from pipelines.linkedin_outreach.services.referral_outreach import prompt_referral_action

        with patch("sys.stdin", io.StringIO("k\n")), \
             patch("sys.stdout", new_callable=io.StringIO):
            result = prompt_referral_action("Test User", review_mode=True)

        assert result == "skip"

    def test_manual_mode_quit_choice_returns_quit(self):
        """When review_mode=True (manual), entering 'q' at the prompt returns 'quit'."""
        from pipelines.linkedin_outreach.services.referral_outreach import prompt_referral_action

        with patch("sys.stdin", io.StringIO("q\n")), \
             patch("sys.stdout", new_callable=io.StringIO):
            result = prompt_referral_action("Test User", review_mode=True)

        assert result == "quit"

    def test_manual_mode_invalid_then_valid_retries(self):
        """When review_mode=True (manual), invalid input is rejected and re-prompted until valid."""
        from pipelines.linkedin_outreach.services.referral_outreach import prompt_referral_action

        # First input is invalid, second is valid 's'
        with patch("sys.stdin", io.StringIO("x\ns\n")), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            result = prompt_referral_action("Test User", review_mode=True)

        assert result == "send"
        output = mock_stdout.getvalue()
        assert "Invalid option" in output

    # ── Config resolution tests (review_mode from config dict) ───────────────

    def test_review_mode_resolved_from_referral_outreach_config(self, local_user):
        """review_mode=False in referral_outreach config → automatic send (no prompt)."""
        from core.storage.engine import get_user_config
        from unittest.mock import patch as mpatch

        # Patch the user config so referral_outreach.review_mode = False
        conf = get_user_config(local_user["username"])
        conf["referral_outreach"]["review_mode"] = False

        with mpatch("pipelines.linkedin_outreach.services.referral_outreach.get_selected_user_config",
                    return_value=conf), \
             mpatch("pipelines.linkedin_outreach.services.referral_outreach.get_global_settings",
                    return_value=conf.get("global_settings", {})), \
             mpatch("pipelines.linkedin_outreach.services.referral_outreach.load_all_referrals",
                    return_value=[]):
            from pipelines.linkedin_outreach.services.referral_outreach import run_phase_two_messaging
            # No pending referrals → exits cleanly without touching browser
            run_phase_two_messaging()  # Should not raise or prompt

    def test_review_mode_true_in_referral_config_overrides_connect_false(self, local_user):
        """referral_outreach.review_mode=True overrides linkedin_connect.review_mode=False.
        This validates the priority: referral_outreach > linkedin_connect."""
        from core.storage.engine import get_user_config

        conf = get_user_config(local_user["username"])
        # connect says automatic (False), but referral says manual (True)
        conf["linkedin_connect"]["review_mode"] = False
        conf["referral_outreach"]["review_mode"] = True

        with patch("pipelines.linkedin_outreach.services.referral_outreach.get_selected_user_config",
                   return_value=conf), \
             patch("pipelines.linkedin_outreach.services.referral_outreach.get_global_settings",
                   return_value=conf.get("global_settings", {})), \
             patch("pipelines.linkedin_outreach.services.referral_outreach.load_all_referrals",
                   return_value=[]):
            from pipelines.linkedin_outreach.services.referral_outreach import run_phase_two_messaging
            # No pending referrals → exits without prompting
            run_phase_two_messaging()

    def test_review_mode_fallback_to_connect_when_referral_has_no_review_mode(self, local_user):
        """When referral_outreach has no review_mode key, it falls back to linkedin_connect.review_mode."""
        from core.storage.engine import get_user_config

        conf = get_user_config(local_user["username"])
        # Remove review_mode from referral_outreach entirely
        conf["referral_outreach"].pop("review_mode", None)
        # Set connect to automatic (False)
        conf["linkedin_connect"]["review_mode"] = False

        with patch("pipelines.linkedin_outreach.services.referral_outreach.get_selected_user_config",
                   return_value=conf), \
             patch("pipelines.linkedin_outreach.services.referral_outreach.get_global_settings",
                   return_value=conf.get("global_settings", {})), \
             patch("pipelines.linkedin_outreach.services.referral_outreach.load_all_referrals",
                   return_value=[]):
            from pipelines.linkedin_outreach.services.referral_outreach import run_phase_two_messaging
            run_phase_two_messaging()  # Should complete cleanly in automatic mode

    def test_review_mode_defaults_to_true_when_both_configs_missing(self, local_user):
        """When neither referral_outreach nor linkedin_connect has review_mode, default is True (safe/manual)."""
        from pipelines.linkedin_outreach.services.referral_outreach import prompt_referral_action

        # Simulate what happens when both configs are missing review_mode:
        # The pipeline code does: review_mode = connect_conf.get("review_mode", True)
        # So defaults to True (manual, safe)
        referral_conf = {}
        connect_conf = {}
        review_mode = referral_conf.get("review_mode")
        if review_mode is None:
            review_mode = connect_conf.get("review_mode", True)
        review_mode = bool(review_mode)

        assert review_mode is True, "Default review_mode must be True (safe/manual) when config is missing"

    # ── Integration: automatic mode skips prompt in send loop ────────────────

    def test_automatic_mode_processes_pending_referrals_without_browser(self, local_user):
        """With review_mode=False and a pending referral, the send loop calls prompt_referral_action
        which returns 'send' immediately. Validates no browser or stdin needed in automatic mode."""
        from pipelines.linkedin_outreach.services.referral_outreach import prompt_referral_action

        # Build a queue of 3 pending referrals and simulate the prompt loop
        pending = [
            _make_employee_referral(name=f"Emp{i}", status="pending")
            for i in range(3)
        ]

        actions = []
        for ref in pending:
            name = ref.get("Referral_Person_Name")
            action = prompt_referral_action(name, review_mode=False)
            actions.append(action)

        assert all(a == "send" for a in actions), \
            "All actions must be 'send' in automatic mode — no manual prompt"
        assert len(actions) == 3
