import sys
import os
import pytest
from unittest.mock import MagicMock, patch
from app import SubprocessRunner

def test_subprocess_runner_start_time():
    runner = SubprocessRunner("user::scraper_pipeline::full", [("run_email_outreach.py", [])], "user")
    assert runner.start_time is not None
    assert runner.start_time > 0

@patch("subprocess.Popen")
def test_subprocess_runner_step_tracking(mock_popen):
    # Mock popen to return a mock process whose stdout yields line-by-line
    mock_process = MagicMock()
    mock_process.stdout.readline.side_effect = [
        "Executing Phase 1: Post email scraping...\n",
        "Executing Phase 2: Email sending...\n",
        ""
    ]
    mock_process.wait.return_value = 0
    mock_popen.return_value = mock_process

    runner = SubprocessRunner("user::scraper_pipeline::full", [("run_email_outreach.py", [])], "user")
    
    # We run _run_loop synchronously
    runner._run_loop()
    
    # Verify current_step ended up at 2
    assert runner.current_step == 2
    assert runner.status == "success"

@patch("subprocess.Popen")
def test_subprocess_runner_log_isolation_scraper(mock_popen):
    mock_process = MagicMock()
    mock_process.stdout.readline.return_value = ""
    mock_process.wait.return_value = 0
    mock_popen.return_value = mock_process

    # Scraper pipeline
    runner = SubprocessRunner("user::scraper_pipeline::full", [("run_email_outreach.py", [])], "user")
    runner._run_loop()
    
    # Verify logs do not contain referral summary
    for log in runner.logs:
        assert "Pipeline Execution Summary" not in log
        assert "Existing Employee Messages Sent" not in log

@patch("subprocess.Popen")
@patch("core.storage.database.load_all_referrals")
def test_subprocess_runner_log_isolation_referral(mock_load_referrals, mock_popen):
    mock_process = MagicMock()
    mock_process.stdout.readline.return_value = ""
    mock_process.wait.return_value = 0
    mock_popen.return_value = mock_process
    
    mock_load_referrals.return_value = []

    # Referral pipeline
    runner = SubprocessRunner("user::referral_pipeline::full", [("run_job_search.py", [])], "user")
    runner._run_loop()
    
    # Verify logs DO contain referral summary
    has_summary = any("Pipeline Execution Summary" in log for log in runner.logs)
    assert has_summary is True
