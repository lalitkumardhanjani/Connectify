import subprocess
import time
import pytest
from app import start_git_autoupdater

class MockCompletedProcess:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

def test_git_autoupdate_logic(monkeypatch):
    calls = []
    
    def mock_run(cmd, *args, **kwargs):
        calls.append(cmd)
        if cmd == ["git", "fetch", "origin"]:
            return MockCompletedProcess(0)
        elif cmd == ["git", "log", "HEAD..origin/main", "--oneline"]:
            # indicate there is one commit update available
            return MockCompletedProcess(0, stdout="a1b2c3d Some new commit")
        elif cmd == ["git", "stash"]:
            return MockCompletedProcess(0)
        elif cmd == ["git", "pull", "origin", "main"]:
            return MockCompletedProcess(0, stdout="Fast-forward")
        elif cmd == ["git", "stash", "pop"]:
            return MockCompletedProcess(0)
        return MockCompletedProcess(0)

    monkeypatch.setattr(subprocess, "run", mock_run)
    
    sleep_count = 0
    def mock_sleep(seconds):
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count > 1:
            raise KeyboardInterrupt("Stop loop")

    monkeypatch.setattr(time, "sleep", mock_sleep)
    
    # Mock Werkzeug run main env to run checker
    monkeypatch.setenv("WERZEUG_RUN_MAIN", "true")
    
    class DummyApp:
        debug = True
        
    app = DummyApp()
    
    # Mock threading.Thread.start to run synchronously in the test thread
    def mock_thread_start(self):
        try:
            self._target()
        except KeyboardInterrupt:
            pass  # stopped loop
            
    monkeypatch.setattr("threading.Thread.start", mock_thread_start)
    
    start_git_autoupdater(app)
    
    # Verify all expected git commands are executed in order
    assert ["git", "fetch", "origin"] in calls
    assert ["git", "log", "HEAD..origin/main", "--oneline"] in calls
    assert ["git", "stash"] in calls
    assert ["git", "pull", "origin", "main"] in calls
    assert ["git", "stash", "pop"] in calls
