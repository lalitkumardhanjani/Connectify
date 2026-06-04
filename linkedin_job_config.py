import os
import urllib.parse
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

LINKEDIN_EMAIL = global_conf.get("linkedin_email") or os.getenv("LINKEDIN_EMAIL")
LINKEDIN_PASSWORD = global_conf.get("linkedin_password") or os.getenv("LINKEDIN_PASSWORD")

# LinkedIn Connect configurations
connect_conf = user_conf.get("linkedin_connect", {})
SEARCH_KEYWORDS_LIST = connect_conf.get("keywords", [])
if not SEARCH_KEYWORDS_LIST:
    SEARCH_KEYWORDS_LIST = [
        "SQL Server DBA",
        "SQL DBA",
        "MS SQL DBA",
        "MSSQL DBA",
        "Microsoft SQL Server DBA",
        "SQL Database Administrator",
        "SQL Server Database Administrator",
        "Database Administrator",
        "Database Admin",
        "DBA",
        "Senior SQL DBA",
        "Azure SQL DBA"
    ]

SEARCH_LOCATION = global_conf.get("search_location", "Bangalore, Karnataka, India")
SEARCH_TIME_RANGE = global_conf.get("search_time_range", "r604800")
SEARCH_LOCATION_QUERY = urllib.parse.quote_plus(SEARCH_LOCATION)

def build_search_url(keyword):
    quoted = urllib.parse.quote_plus(keyword)
    return (
        f"https://www.linkedin.com/jobs/search/?keywords={quoted}"
        f"&location={SEARCH_LOCATION_QUERY}&f_TPR={SEARCH_TIME_RANGE}"
        f"&trk=public_jobs_jobs-search-bar_search-submit&position=1&pageNum=0"
    )

SEARCH_URLS = []
SEARCH_URL_OVERRIDE = os.getenv("SEARCH_URL", "")
if SEARCH_URL_OVERRIDE:
    SEARCH_URLS = [SEARCH_URL_OVERRIDE]
else:
    SEARCH_URLS = [build_search_url(keyword) for keyword in SEARCH_KEYWORDS_LIST]

TRACKER_FILE = "LinkedIn_Job_Tracker.xlsx"
DRY_RUN = global_conf.get("dry_run", "1") != "0"
CHROME_PROFILE_DIR = os.getenv(
    "CHROME_PROFILE_DIR",
    os.path.join(os.getcwd(), ".chrome-profile")
)
