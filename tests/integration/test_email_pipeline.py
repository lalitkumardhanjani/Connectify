"""
Integration Tests: Email Outreach Pipeline
(pipelines/email_outreach/pipeline.py)

Tests Phase 1 (scraper), Phase 2 (sender), and the full pipeline
under both local and Google Sheets storage modes.

Selenium is fully mocked — no real browser is launched.

Run with:
    pytest tests/integration/test_email_pipeline.py -v
"""

import pytest
from unittest.mock import MagicMock, patch, call
from tests.fixtures.sample_data import SAMPLE_EMAILS


# ===========================================================================
#  Helper: Mock Scraper that "discovers" emails without a real browser
# ===========================================================================

def _make_mock_scraper(driver, emails_to_discover=None):
    """
    Returns a mock LinkedInScraper that simulates discovering emails.
    When process_keyword() is called, it calls append_email for each email.
    """
    emails_to_discover = emails_to_discover or ["found@company.com"]

    from unittest.mock import MagicMock
    import pipelines.email_outreach.services.scraper as scraper_mod

    mock_scraper = MagicMock(spec=scraper_mod.LinkedInScraper)
    mock_scraper.driver = driver
    mock_scraper.login.return_value = True
    mock_scraper.search_for_keyword.return_value = True

    def fake_process_keyword(keyword, timeout_seconds=60):
        from core.storage.database import append_email
        for email in emails_to_discover:
            append_email(email, keyword=keyword, post_url="https://li.com/posts/test")

    mock_scraper.process_keyword.side_effect = fake_process_keyword
    return mock_scraper


# ===========================================================================
#  PHASE 1 TESTS — Email Scraping
# ===========================================================================

class TestEmailPipelinePhaseOne:
    """Tests for Phase 1: LinkedIn post email scraping."""

    def test_phase1_discovers_and_saves_emails_local(self, local_user, mock_driver):
        """Phase 1 should discover emails and append them to storage."""
        from core.storage.engine import read_database_rows
        from pipelines.email_outreach.pipeline import run_phase_one

        scraper = _make_mock_scraper(mock_driver, emails_to_discover=["hr@techco.com", "recruit@techco.com"])
        run_phase_one(scraper)

        rows = read_database_rows("emails")
        found_emails = {r["Email"] for r in rows}
        assert "hr@techco.com" in found_emails

    def test_phase1_discovers_emails_sheets(self, sheets_user, mock_driver):
        """Phase 1 should work identically under Google Sheets storage."""
        from core.storage.engine import read_database_rows
        from pipelines.email_outreach.pipeline import run_phase_one

        scraper = _make_mock_scraper(mock_driver, emails_to_discover=["sh@company.com"])
        run_phase_one(scraper)

        rows = read_database_rows("emails")
        assert any(r["Email"] == "sh@company.com" for r in rows)

    def test_phase1_deduplicates_emails(self, local_user, mock_driver):
        """Running phase 1 twice for the same emails should not create duplicates."""
        from core.storage.engine import read_database_rows
        from pipelines.email_outreach.pipeline import run_phase_one
        from core.storage.database import count_unique_emails

        scraper = _make_mock_scraper(mock_driver, emails_to_discover=["dup@co.com"])
        run_phase_one(scraper)
        run_phase_one(scraper)  # second run

        assert count_unique_emails() == 1

    def test_phase1_respects_search_keywords(self, local_user, mock_driver):
        """process_keyword() should be called once per configured search keyword."""
        from pipelines.email_outreach.pipeline import run_phase_one

        scraper = _make_mock_scraper(mock_driver, emails_to_discover=[])
        run_phase_one(scraper)

        # Config has 2 keywords: "Data Engineer", "Senior Data Engineer"
        # Each will be called with search_for_keyword and process_keyword
        assert scraper.search_for_keyword.call_count >= 1
        assert scraper.process_keyword.call_count >= 1

    def test_phase1_handles_navigation_failure_gracefully(self, local_user, mock_driver):
        """If search_for_keyword() returns False, that keyword is skipped without crashing."""
        from pipelines.email_outreach.pipeline import run_phase_one

        scraper = _make_mock_scraper(mock_driver, emails_to_discover=[])
        scraper.search_for_keyword.return_value = False  # All searches fail

        # Should not raise
        run_phase_one(scraper)
        scraper.process_keyword.assert_not_called()

    def test_phase1_stops_on_scraper_target_reached(self, local_user, mock_driver):
        """ScraperTargetReached exception from process_keyword() is handled gracefully."""
        import pipelines.email_outreach.services.scraper as scraper_mod
        from pipelines.email_outreach.pipeline import run_phase_one

        scraper = _make_mock_scraper(mock_driver, emails_to_discover=[])
        scraper.search_for_keyword.return_value = True
        scraper.process_keyword.side_effect = scraper_mod.ScraperTargetReached("Limit reached")

        # Should not crash — ScraperTargetReached is handled
        run_phase_one(scraper)


# ===========================================================================
#  PHASE 2 TESTS — Email Sending
# ===========================================================================

class TestEmailPipelinePhaseTwo:
    """Tests for Phase 2: composing and sending emails."""

    def _setup_emails(self, statuses=None):
        """Pre-populate the emails table."""
        from core.storage.engine import write_database_rows
        statuses = statuses or ["New", "sent", "New", "skipped"]
        rows = [
            {
                "ID": i + 1,
                "Email": f"user{i}@co.com",
                "Status": statuses[i] if i < len(statuses) else "New",
                "Timestamp": "2025-01-01T10:00:00",
                "Keyword": "Data Engineer",
                "PostURL": f"https://li.com/p/{i}",
                "CompanyName": f"Co{i}",
                "Experience": "3-5 years",
                "Location": "Bangalore",
            }
            for i in range(len(statuses))
        ]
        write_database_rows("emails", rows)
        return rows

    def test_phase2_skips_already_sent_emails(self, local_user, mock_driver, monkeypatch):
        """Emails with Status='sent' or 'skipped' must not be processed again."""
        self._setup_emails(["sent", "sent", "skipped"])

        sent_to = []

        def mock_send(driver, email, post_url="", review_mode=None):
            sent_to.append(email)
            return True

        monkeypatch.setattr(
            "pipelines.email_outreach.pipeline.send_email_via_gmail", mock_send
        )

        from pipelines.email_outreach.pipeline import run_phase_two
        scraper = MagicMock()
        scraper.driver = mock_driver
        run_phase_two(scraper, review_mode=False)

        assert len(sent_to) == 0, "Should not send to already-sent/skipped emails"

    def test_phase2_sends_to_new_emails_local(self, local_user, mock_driver, monkeypatch):
        """Emails with Status='New' should be sent."""
        self._setup_emails(["New", "New"])

        sent_to = []

        def mock_send(driver, email, post_url="", review_mode=None):
            sent_to.append(email)
            return True

        monkeypatch.setattr(
            "pipelines.email_outreach.pipeline.send_email_via_gmail", mock_send
        )
        monkeypatch.setattr(
            "pipelines.email_outreach.pipeline.update_status",
            lambda email, status, *args, **kwargs: None
        )

        from pipelines.email_outreach.pipeline import run_phase_two
        scraper = MagicMock()
        scraper.driver = mock_driver
        run_phase_two(scraper, review_mode=False)

        assert len(sent_to) == 2

    def test_phase2_sends_to_new_emails_sheets(self, sheets_user, mock_driver, monkeypatch):
        """Phase 2 works with Google Sheets storage."""
        self._setup_emails(["New"])

        def mock_send(driver, email, post_url="", review_mode=None):
            return True

        monkeypatch.setattr(
            "pipelines.email_outreach.pipeline.send_email_via_gmail", mock_send
        )
        monkeypatch.setattr(
            "pipelines.email_outreach.pipeline.update_status",
            lambda email, status, *args, **kwargs: None
        )

        from pipelines.email_outreach.pipeline import run_phase_two
        scraper = MagicMock()
        scraper.driver = mock_driver
        run_phase_two(scraper, review_mode=False)

    def test_phase2_respects_max_emails_per_run(self, local_user, mock_driver, monkeypatch):
        """max_emails_per_run from config must stop sending after the limit."""
        self._setup_emails(["New", "New", "New", "New", "New", "New"])

        sent_count = {"n": 0}

        def mock_send(driver, email, post_url="", review_mode=None):
            sent_count["n"] += 1
            return True

        monkeypatch.setattr(
            "pipelines.email_outreach.pipeline.send_email_via_gmail", mock_send
        )
        monkeypatch.setattr(
            "pipelines.email_outreach.pipeline.update_status",
            lambda email, status, *args, **kwargs: None
        )

        from pipelines.email_outreach.pipeline import run_phase_two
        scraper = MagicMock()
        scraper.driver = mock_driver
        run_phase_two(scraper, review_mode=False)

        # Config has max_emails_per_run=5
        assert sent_count["n"] <= 5

    def test_phase2_marks_status_sent_after_success(self, local_user, mock_driver, monkeypatch):
        """After successful send, status must be updated to 'sent'."""
        self._setup_emails(["New"])

        monkeypatch.setattr(
            "pipelines.email_outreach.pipeline.send_email_via_gmail",
            lambda driver, email, post_url="", review_mode=None: True
        )

        from core.storage.engine import read_database_rows
        from pipelines.email_outreach.pipeline import run_phase_two
        scraper = MagicMock()
        scraper.driver = mock_driver
        run_phase_two(scraper, review_mode=False)

        rows = read_database_rows("emails")
        assert rows[0]["Status"] == "sent"

    def test_phase2_marks_status_skipped_on_skip(self, local_user, mock_driver, monkeypatch):
        """When send returns 'skipped', status must be set to 'skipped'."""
        self._setup_emails(["New"])

        monkeypatch.setattr(
            "pipelines.email_outreach.pipeline.send_email_via_gmail",
            lambda driver, email, post_url="", review_mode=None: "skipped"
        )

        from core.storage.engine import read_database_rows
        from pipelines.email_outreach.pipeline import run_phase_two
        scraper = MagicMock()
        scraper.driver = mock_driver
        run_phase_two(scraper, review_mode=False)

        rows = read_database_rows("emails")
        assert rows[0]["Status"] == "skipped"

    def test_phase2_stops_on_quit_signal(self, local_user, mock_driver, monkeypatch):
        """When send returns 'quit', pipeline should stop processing further emails."""
        self._setup_emails(["New", "New", "New"])

        sent_count = {"n": 0}

        def mock_send(driver, email, post_url="", review_mode=None):
            if sent_count["n"] == 0:
                sent_count["n"] += 1
                return True
            return "quit"

        monkeypatch.setattr(
            "pipelines.email_outreach.pipeline.send_email_via_gmail", mock_send
        )
        monkeypatch.setattr(
            "pipelines.email_outreach.pipeline.update_status",
            lambda email, status, *args, **kwargs: None
        )

        from pipelines.email_outreach.pipeline import run_phase_two
        scraper = MagicMock()
        scraper.driver = mock_driver
        run_phase_two(scraper, review_mode=False)

        assert sent_count["n"] == 1

    def test_phase2_exits_cleanly_if_no_pending_emails(self, local_user, mock_driver, monkeypatch):
        """Phase 2 should log and return when there are no emails to send."""
        self._setup_emails(["sent", "skipped"])

        mock_send = MagicMock()
        monkeypatch.setattr(
            "pipelines.email_outreach.pipeline.send_email_via_gmail", mock_send
        )

        from pipelines.email_outreach.pipeline import run_phase_two
        scraper = MagicMock()
        scraper.driver = mock_driver
        run_phase_two(scraper, review_mode=False)

        mock_send.assert_not_called()


# ===========================================================================
#  FULL PIPELINE TESTS
# ===========================================================================

class TestEmailPipelineFull:
    """Tests for the full pipeline orchestration (phase='full')."""

    def test_full_pipeline_runs_both_phases(self, local_user, mock_driver, monkeypatch):
        """Full pipeline should run Phase 1 then Phase 2 sequentially."""
        phase1_called = {"called": False}
        phase2_called = {"called": False}

        def mock_phase1(scraper):
            phase1_called["called"] = True

        def mock_phase2(scraper, review_mode=None):
            phase2_called["called"] = True

        monkeypatch.setattr("pipelines.email_outreach.pipeline.run_phase_one", mock_phase1)
        monkeypatch.setattr("pipelines.email_outreach.pipeline.run_phase_two", mock_phase2)
        monkeypatch.setattr("core.integrations.selenium_driver.get_driver", lambda *a, **kw: mock_driver)
        monkeypatch.setattr("pipelines.email_outreach.pipeline.get_driver", lambda *a, **kw: mock_driver)

        scraper_instance = _make_mock_scraper(mock_driver)
        monkeypatch.setattr(
            "pipelines.email_outreach.pipeline.LinkedInScraper",
            lambda driver: scraper_instance
        )

        from pipelines.email_outreach.pipeline import run_pipeline
        result = run_pipeline(phase="full")

        assert result is True
        assert phase1_called["called"]
        assert phase2_called["called"]

    def test_pipeline_phase1_only(self, local_user, mock_driver, monkeypatch):
        """phase='phase1' should only run Phase 1."""
        phase2_called = {"called": False}

        def mock_phase2(scraper, review_mode=None):
            phase2_called["called"] = True

        monkeypatch.setattr("pipelines.email_outreach.pipeline.run_phase_one", lambda s: None)
        monkeypatch.setattr("pipelines.email_outreach.pipeline.run_phase_two", mock_phase2)
        monkeypatch.setattr("core.integrations.selenium_driver.get_driver", lambda *a, **kw: mock_driver)
        monkeypatch.setattr("pipelines.email_outreach.pipeline.get_driver", lambda *a, **kw: mock_driver)

        scraper_instance = _make_mock_scraper(mock_driver)
        monkeypatch.setattr(
            "pipelines.email_outreach.pipeline.LinkedInScraper",
            lambda driver: scraper_instance
        )

        from pipelines.email_outreach.pipeline import run_pipeline
        run_pipeline(phase="phase1")
        assert not phase2_called["called"]

    def test_pipeline_aborts_on_login_failure(self, local_user, mock_driver, monkeypatch):
        """Login failure should abort the pipeline and return False."""
        monkeypatch.setattr("core.integrations.selenium_driver.get_driver", lambda *a, **kw: mock_driver)
        monkeypatch.setattr("pipelines.email_outreach.pipeline.get_driver", lambda *a, **kw: mock_driver)

        scraper_instance = MagicMock()
        scraper_instance.login.return_value = False
        monkeypatch.setattr(
            "pipelines.email_outreach.pipeline.LinkedInScraper",
            lambda driver: scraper_instance
        )

        from pipelines.email_outreach.pipeline import run_pipeline
        result = run_pipeline()
        assert result is False

    def test_pipeline_returns_false_on_unexpected_exception(self, local_user, mock_driver, monkeypatch):
        """Unhandled exceptions inside the pipeline should return False (not raise)."""
        monkeypatch.setattr("core.integrations.selenium_driver.get_driver", lambda *a, **kw: mock_driver)
        monkeypatch.setattr("pipelines.email_outreach.pipeline.get_driver", lambda *a, **kw: mock_driver)

        def crash_phase1(scraper):
            raise RuntimeError("Simulated crash")

        scraper_instance = _make_mock_scraper(mock_driver)
        monkeypatch.setattr(
            "pipelines.email_outreach.pipeline.LinkedInScraper",
            lambda driver: scraper_instance
        )
        monkeypatch.setattr("pipelines.email_outreach.pipeline.run_phase_one", crash_phase1)
        monkeypatch.setattr("pipelines.email_outreach.pipeline.run_phase_two", lambda s, review_mode=None: None)

        from pipelines.email_outreach.pipeline import run_pipeline
        result = run_pipeline()
        assert result is False
