import os
import sys
import pytest

def test_get_chrome_profile_dir_env_override(monkeypatch):
    monkeypatch.setenv("CHROME_PROFILE_DIR", "/custom/profile/dir")
    from config.settings import get_chrome_profile_dir
    assert get_chrome_profile_dir() == "/custom/profile/dir"

def test_get_chrome_profile_dir_dynamic_suffix(monkeypatch):
    monkeypatch.delenv("CHROME_PROFILE_DIR", raising=False)
    
    # Mock sys.argv[0] for run_email_scraper
    monkeypatch.setattr(sys, "argv", ["run_email_scraper.py"])
    from config.settings import get_chrome_profile_dir
    path = get_chrome_profile_dir()
    assert "prof-email-phase1" in path

    # Mock sys.argv[0] for run_email_sender
    monkeypatch.setattr(sys, "argv", ["run_email_sender.py"])
    path = get_chrome_profile_dir()
    assert "prof-email-phase2" in path

    # Mock sys.argv[0] for run_recruiter
    monkeypatch.setattr(sys, "argv", ["run_recruiter_outreach.py"])
    path = get_chrome_profile_dir()
    assert "prof-recruiter" in path

    # Mock sys.argv[0] for normal runs
    monkeypatch.setattr(sys, "argv", ["app.py"])
    path = get_chrome_profile_dir()
    assert "prof-default" in path
    assert "prof-email-phase1" not in path

def test_get_driver_custom_profile_suffix(monkeypatch):
    # Mock helper functions to avoid system modifications and real browser instantiation
    monkeypatch.setattr("core.integrations.selenium_driver._kill_stale_chrome_processes", lambda: None)
    monkeypatch.setattr("core.integrations.selenium_driver._kill_lingering_chrome_instances", lambda x: None)
    monkeypatch.setattr("core.integrations.selenium_driver._cleanup_chrome_locks", lambda x: None)
    
    # Mock webdriver.Chrome and webdriver.Edge constructors
    class MockedBrowser:
        def __init__(self, service=None, options=None):
            self.options = options
            
    monkeypatch.setattr("selenium.webdriver.Chrome", MockedBrowser)
    monkeypatch.setattr("selenium.webdriver.Edge", MockedBrowser)
    
    # Mock Options arguments
    arguments_added = []
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.edge.options import Options as EdgeOptions
    
    original_chrome_add = ChromeOptions.add_argument
    def mock_chrome_add(self, arg):
        arguments_added.append(arg)
        original_chrome_add(self, arg)
    monkeypatch.setattr(ChromeOptions, "add_argument", mock_chrome_add)
    
    original_edge_add = EdgeOptions.add_argument
    def mock_edge_add(self, arg):
        arguments_added.append(arg)
        original_edge_add(self, arg)
    monkeypatch.setattr(EdgeOptions, "add_argument", mock_edge_add)

    from core.integrations.selenium_driver import get_driver
    driver = get_driver(profile_suffix="test-custom-suffix")
    
    assert any("test-custom-suffix" in arg for arg in arguments_added)
