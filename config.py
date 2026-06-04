import os
from dotenv import load_dotenv

load_dotenv()

# Load dynamic configuration from users_config.json
try:
    from user_config_manager import get_selected_user_config, get_global_settings
    user_conf = get_selected_user_config()
    global_conf = get_global_settings()
except Exception:
    user_conf = {}
    global_conf = {}

# LinkedIn Credentials (from global settings with environment fallbacks)
LINKEDIN_EMAIL = global_conf.get("linkedin_email") or os.getenv("LINKEDIN_EMAIL")
LINKEDIN_PASSWORD = global_conf.get("linkedin_password") or os.getenv("LINKEDIN_PASSWORD")

# SMTP Credentials
SMTP_SERVER = global_conf.get("smtp_server") or os.getenv("SMTP_SERVER", "smtp.gmail.com")
try:
    SMTP_PORT = int(global_conf.get("smtp_port") or os.getenv("SMTP_PORT", 587))
except ValueError:
    SMTP_PORT = 587
SMTP_EMAIL = global_conf.get("smtp_email") or os.getenv("SMTP_EMAIL", "lk356003@gmail.com")
SMTP_PASSWORD = global_conf.get("smtp_password") or os.getenv("SMTP_PASSWORD")

# Selected User Profile details
profile = user_conf.get("profile", {})
_first = profile.get("first_name", "")
_last = profile.get("last_name", "")
_full = (_first + " " + _last).strip()
SISTER_NAME = _full or profile.get("full_name") or os.getenv("SISTER_NAME", "Yuvashree J")
SISTER_EMAIL = profile.get("email") or os.getenv("SISTER_EMAIL", "yuvashreej199@gmail.com")
PHONE_NUMBER = profile.get("phone") or os.getenv("PHONE_NUMBER", "8971799691")
RESUME_LINK = profile.get("resume_url") or os.getenv("RESUME_LINK", "https://shorturl.at/F3SGD")

def get_resume_file_path(profile_dict):
    local_resume_name = profile_dict.get("resume_name", "")
    if local_resume_name:
        return os.path.join(os.getcwd(), "resumes", local_resume_name)
    else:
        return os.getenv(
            "RESUME_FILE_PATH",
            os.path.abspath(os.path.join(os.getcwd(), "Resume_YuvashreeJ_SQLDBA.pdf"))
        )

# Local Resume File Path
RESUME_FILE_PATH = get_resume_file_path(profile)

# Email Scraper pipeline settings
email_scraper = user_conf.get("email_scraper", {})
REVIEW_MODE = email_scraper.get("review_mode", False)
DEFAULT_SEARCH_KEYWORDS = email_scraper.get("keywords", [])
if not DEFAULT_SEARCH_KEYWORDS:
    DEFAULT_SEARCH_KEYWORDS = [
        "SQL Server DBA", "SQL DBA", "MS SQL DBA", "MSSQL DBA",
        "Microsoft SQL Server DBA", "SQL Database Administrator",
        "SQL Server Database Administrator", "Database Administrator",
        "Database Admin", "DBA"
    ]

# Backwards compatibility and static values
DBA_KEYWORDS = DEFAULT_SEARCH_KEYWORDS

# File Paths
CONTACTED_EMAILS_FILE = "contacted_emails.xlsx"
DBA_JOB_LEADS_FILE = "dba_job_leads.xlsx"
LOG_FILE = "automation.log"

# Chrome Profile Path
CHROME_PROFILE_PATH = r"C:\selenium-chrome-profile"
