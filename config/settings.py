import os
import json
from dotenv import load_dotenv

# Load .env file from the root directory
load_dotenv()

# Root directory of the project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_active_user():
    """Reads the active user from users/active_user.json. Falls back to first user directory if found."""
    active_user_file = os.path.join(BASE_DIR, "users", "active_user.json")
    if os.path.exists(active_user_file):
        try:
            with open(active_user_file, "r") as f:
                data = json.load(f)
                user = data.get("selected_user")
                if user:
                    return user
        except Exception:
            pass

    # Fallback scan of the users folder
    users_dir = os.path.join(BASE_DIR, "users")
    if os.path.exists(users_dir):
        try:
            subdirs = [d for d in os.listdir(users_dir) if os.path.isdir(os.path.join(users_dir, d)) and d != "default"]
            if subdirs:
                return sorted(subdirs)[0]
        except Exception:
            pass
    return None

def get_user_dir():
    """Returns the base directory for the active user's isolated data."""
    user = get_active_user()
    if not user:
        user = "default"
    return os.path.join(BASE_DIR, "users", user)

def get_data_dir():
    path = os.path.join(get_user_dir(), "data")
    os.makedirs(path, exist_ok=True)
    return path

def get_logs_dir():
    path = os.path.join(get_user_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path

def get_resumes_dir():
    path = os.path.join(get_user_dir(), "resumes")
    os.makedirs(path, exist_ok=True)
    return path

# Dynamic resolution getters for individual file paths
def get_job_tracker_file():
    return os.path.join(get_data_dir(), "job_tracker.xlsx")

def get_job_leads_file():
    return os.path.join(get_data_dir(), "LinkedIn_Job_Tracker.xlsx")

def get_jobs_json_file():
    return os.path.join(get_data_dir(), "linkedin_jobs.json")

def get_audit_json_file():
    return os.path.join(get_data_dir(), "linkedin_jobs_audit.json")

def get_log_file():
    return os.path.join(get_logs_dir(), "automation.log")

def get_linkedin_connect_log_file():
    return os.path.join(get_logs_dir(), "linkedin_connect.log")

def get_chrome_profile_dir():
    env_path = os.getenv("CHROME_PROFILE_DIR")
    if env_path:
        return env_path
    path = os.path.join(get_user_dir(), "chrome-profile")
    os.makedirs(path, exist_ok=True)
    return path

# Constants & static files (remain root-level or system-wide)
MAC_CHROME_BINARY = "/System/Volumes/Data/Volumes/Google Chrome/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROMEDRIVER_PATH = os.path.join(BASE_DIR, "chromedriver")

# Support PEP 562 module attribute lookup (for python 3.7+)
# This maps legacy static imports (e.g. from config.settings import DATA_DIR)
# to dynamic evaluation, preventing stale variables in subprocesses.
def __getattr__(name):
    if name == "DATA_DIR":
        return get_data_dir()
    elif name == "LOGS_DIR":
        return get_logs_dir()
    elif name == "RESUMES_DIR":
        return get_resumes_dir()
    elif name == "JOB_TRACKER_FILE":
        return get_job_tracker_file()
    elif name == "JOB_LEADS_FILE":
        return get_job_leads_file()
    elif name == "JOBS_JSON_FILE":
        return get_jobs_json_file()
    elif name == "AUDIT_JSON_FILE":
        return get_audit_json_file()
    elif name == "LOG_FILE":
        return get_log_file()
    elif name == "LINKEDIN_CONNECT_LOG_FILE":
        return get_linkedin_connect_log_file()
    elif name == "CHROME_PROFILE_DIR":
        return get_chrome_profile_dir()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
