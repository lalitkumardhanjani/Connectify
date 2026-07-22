import os
import json
import warnings
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL.*')
from dotenv import load_dotenv

# Load .env file from the root directory
load_dotenv()

# Root directory of the project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_active_user():
    """Reads the active user. When called inside a pipeline subprocess, CONNECTIFY_USER
    is set by SubprocessRunner to pin the process to the correct user profile permanently,
    regardless of which user is currently selected in the UI (active_user.json)."""
    # Subprocess isolation: pipeline subprocesses are launched with CONNECTIFY_USER set
    # so they always read the correct user's config/data/chrome-profile.
    env_user = os.getenv("CONNECTIFY_USER")
    if env_user:
        return env_user

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

def get_referrals_file():
    return os.path.join(get_data_dir(), "referrals.xlsx")


def get_log_file():
    return os.path.join(get_logs_dir(), "automation.log")

def get_linkedin_connect_log_file():
    return os.path.join(get_logs_dir(), "linkedin_connect.log")

def get_chrome_profile_dir():
    env_path = os.getenv("CHROME_PROFILE_DIR")
    if env_path:
        os.makedirs(env_path, exist_ok=True)
        return env_path
    
    import sys
    script_name = os.path.basename(sys.argv[0])
    
    # Map each specific runner script to its own isolated Chrome profile directory
    if "run_email_scraper" in script_name:
        suffix = "chrome-profile-scraper-phase1"
    elif "run_email_sender" in script_name:
        suffix = "chrome-profile-scraper-phase2"
    elif "run_email_outreach" in script_name:
        suffix = "chrome-profile-scraper-full"
    elif "run_job_search" in script_name:
        suffix = "chrome-profile-referral-step1"
    elif "run_referral_review" in script_name:
        suffix = "chrome-profile-referral-step2"
    elif "run_referral_outreach_discover" in script_name:
        suffix = "chrome-profile-referral-step3"
    elif "run_referral_outreach_send" in script_name:
        suffix = "chrome-profile-referral-step4"
    elif "run_url_shortener" in script_name:
        suffix = "chrome-profile-referral-step5"
    elif "run_linkedin_connect" in script_name:
        suffix = "chrome-profile-referral-step6"
    elif "run_referral" in script_name:
        suffix = "chrome-profile-referral-full"
    elif "run_recruiter_outreach_discover" in script_name:
        suffix = "chrome-profile-recruiter-step1"
    elif "run_recruiter_outreach_send" in script_name:
        suffix = "chrome-profile-recruiter-step2"
    elif "run_recruiter" in script_name:
        suffix = "chrome-profile-recruiter-step3"
    else:
        suffix = "chrome-profile"

    path = os.path.join(get_user_dir(), suffix)
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
    elif name == "REFERRALS_FILE":
        return get_referrals_file()

    elif name == "LOG_FILE":
        return get_log_file()
    elif name == "LINKEDIN_CONNECT_LOG_FILE":
        return get_linkedin_connect_log_file()
    elif name == "CHROME_PROFILE_DIR":
        return get_chrome_profile_dir()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
