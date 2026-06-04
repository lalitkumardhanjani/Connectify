import os
from dotenv import load_dotenv

# Load .env file from the root directory
load_dotenv()

# Root directory of the project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Project Directories
DATA_DIR = os.path.join(BASE_DIR, "data")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
RESUMES_DIR = os.path.join(BASE_DIR, "resumes")

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(RESUMES_DIR, exist_ok=True)

# Tracking Database File Paths
JOB_TRACKER_FILE = os.path.join(DATA_DIR, "job_tracker.xlsx")
JOB_LEADS_FILE = os.path.join(DATA_DIR, "LinkedIn_Job_Tracker.xlsx")
JOBS_JSON_FILE = os.path.join(DATA_DIR, "linkedin_jobs.json")
AUDIT_JSON_FILE = os.path.join(DATA_DIR, "linkedin_jobs_audit.json")

# Log File Path
LOG_FILE = os.path.join(LOGS_DIR, "automation.log")
LINKEDIN_CONNECT_LOG_FILE = os.path.join(LOGS_DIR, "linkedin_connect.log")

# Chrome Profile Directories
DEFAULT_CHROME_PROFILE_DIR = os.path.join(BASE_DIR, ".chrome-profile")
CHROME_PROFILE_DIR = os.getenv("CHROME_PROFILE_DIR", DEFAULT_CHROME_PROFILE_DIR)

# Chrome Application Path (Mac specific fallback configuration)
MAC_CHROME_BINARY = "/System/Volumes/Data/Volumes/Google Chrome/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROMEDRIVER_PATH = os.path.join(BASE_DIR, "chromedriver")
