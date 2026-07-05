import warnings
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL.*')
import logging

class NoDevServerWarningFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        return "development server" not in msg and "production deployment" not in msg

logging.getLogger("werkzeug").addFilter(NoDevServerWarningFilter())
import os
import sys
import json
import time
import subprocess
import threading
import signal
from datetime import datetime
from flask import Flask, jsonify, request, render_template, send_from_directory, send_file, Response
from werkzeug.utils import secure_filename
import pandas as pd
import openpyxl

# Connectify Consolidated Configurations and Core Imports
from config.settings import (
    BASE_DIR, get_job_tracker_file, get_job_leads_file, get_referrals_file, get_resumes_dir, get_active_user, get_user_dir
)
from config.user_profiles import (
    load_all_configs, save_all_configs, get_selected_user_name,
    get_selected_user_config, get_global_settings, get_resume_file_path
)
from config.email_templates import DEFAULT_EMAIL_TEMPLATE, DEFAULT_CONNECTION_TEMPLATE
from core.analytics.metrics import get_email_metrics, get_company_metrics, get_outreach_metrics
from core.storage.database import update_status_by_id, edit_row, edit_lead_row

app = Flask(__name__, template_folder='templates', static_folder='static')


if sys.platform == 'win32':
    PYTHON_BIN = os.path.join(os.getcwd(), ".venv", "Scripts", "python.exe")
    if not os.path.exists(PYTHON_BIN):
        PYTHON_BIN = "python"
else:
    PYTHON_BIN = os.path.join(os.getcwd(), ".venv", "bin", "python")
    if not os.path.exists(PYTHON_BIN):
        PYTHON_BIN = "python3"

# Active task tracking
active_tasks = {}
task_lock = threading.Lock()

class SubprocessRunner:
    def __init__(self, task_id, commands, username):
        self.task_id = task_id
        self.username = username          # The user profile this pipeline is pinned to
        self.commands = commands # List of (script_name, list_of_args)
        self.logs = []
        self.status = "queued"
        self.waiting_for_input = False
        self.process = None
        self.current_step = 0
        self.thread = None

    def start(self):
        self.status = "running"
        self.thread = threading.Thread(target=self._run_loop)
        self.thread.daemon = True
        self.thread.start()

    def log(self, text):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp}] {text}")

    def _run_loop(self):
        for idx, (script, args) in enumerate(self.commands):
            self.current_step = idx + 1
            if script == "run_linkedin_connect.py":
                pass
            elif script == "run_recruiter_outreach.py":
                try:
                    from config.user_profiles import load_all_configs
                    from core.storage.database import load_all_referrals
                    # Read config for the pinned user (not the currently selected UI user)
                    all_cfg = load_all_configs()
                    user_conf = all_cfg.get("users", {}).get(self.username, {})
                    recruiter_conf = user_conf.get("recruiter_outreach", {})
                    target_count = int(recruiter_conf.get("target_count") or 2)
                    
                    referrals = load_all_referrals()
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    
                    # Count recruiter connection requests and recruiter messages sent today
                    rec_msg_sent = sum(
                        1 for r in referrals
                        if str(r.get('Referral_Status') or '').strip().lower() == 'sent'
                        and str(r.get('Sent_Time') or '').strip().startswith(today_str)
                        and str(r.get('Referral_Source') or '').strip() == 'Existing Recruiter'
                    )
                    rec_conn_sent = sum(
                        1 for r in referrals
                        if str(r.get('Referral_Status') or '').strip().lower() == 'sent'
                        and str(r.get('Sent_Time') or '').strip().startswith(today_str)
                        and str(r.get('Referral_Source') or '').strip() == 'Sent Recruiter Connection'
                    )
                    total_rec_sent_today = rec_msg_sent + rec_conn_sent
                    
                    if total_rec_sent_today >= target_count:
                        self.log(f"Target count of {target_count} reached via recruiter outreach today ({total_rec_sent_today} sent). Skipping recruiter connection requests pipeline.")
                        break
                except Exception as e:
                    self.log(f"Warning: error checking recruiter target limits in runner: {e}")
            script_path = os.path.join(os.getcwd(), script)
            cmd = [PYTHON_BIN, "-u", script_path] + args
            
            self.log(f"--- Launching Step {self.current_step}/{len(self.commands)}: {script} ---")
            
            # Read fresh env variables from .env to forward to subprocess
            env_copy = os.environ.copy()
            if os.path.exists(".env"):
                with open(".env", "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            env_copy[k.strip()] = v.strip()

            # Enable isolated and parallel execution of Chrome instances.
            # CONNECTIFY_USER pins this subprocess to the exact user profile — all calls to
            # get_active_user(), get_selected_user_config(), get_data_dir() etc. inside the
            # subprocess will use this user's isolated directories and config, regardless of
            # which user is currently selected in the UI.
            env_copy["CONNECTIFY_USER"] = self.username
            env_copy["CONNECTIFY_PARALLEL"] = "true"
            
            # Derive per-user, per-pipeline Chrome profile directories
            user_dir_for_runner = os.path.join(BASE_DIR, "users", self.username)
            pipeline_type = self.task_id.split("::")[-1]  # e.g. "scraper_pipeline"
            if pipeline_type == "scraper_pipeline":
                env_copy["CHROME_PROFILE_DIR"] = os.path.join(user_dir_for_runner, "chrome-profile-scraper")
            elif pipeline_type == "referral_pipeline":
                env_copy["CHROME_PROFILE_DIR"] = os.path.join(user_dir_for_runner, "chrome-profile-referral")
            elif pipeline_type == "recruiter_pipeline":
                env_copy["CHROME_PROFILE_DIR"] = os.path.join(user_dir_for_runner, "chrome-profile-recruiter")
            
            try:
                self.process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    preexec_fn=None if sys.platform == 'win32' else os.setsid,
                    env=env_copy
                )
            except Exception as e:
                self.log(f"Failed to start script {script}: {e}")
                self.status = "failed"
                return

            # Read stdout line by line
            while True:
                line = self.process.stdout.readline()
                if not line:
                    break
                
                clean_line = line.strip()
                self.logs.append(line.rstrip('\r\n'))
                
                # Check if review_for_referral or job search is waiting for option/confirmation selection
                if "Enter choice:" in clean_line or "Options:" in clean_line or "press ENTER to continue" in clean_line or "Send [S] / Skip [K] / Quit [Q]" in clean_line:
                    time.sleep(0.2)
                    self.waiting_for_input = True

            self.process.stdout.close()
            return_code = self.process.wait()
            self.waiting_for_input = False
            
            if return_code != 0:
                self.log(f"Script {script} exited with non-zero status code: {return_code}")
                if self.status != "killed":
                    # Exit code 2 = user-initiated Quit (Quality Gate). Show as
                    # 'stopped' rather than 'failed' so the dashboard badge is correct.
                    if return_code == 2:
                        self.status = "stopped"
                    else:
                        self.status = "failed"
                return
            
            self.log(f"Step {self.current_step} completed successfully.")

        if self.status != "killed":
            self.status = "success"
            # Print execution summary & adjust status if no candidates were found/processed
            try:
                from core.storage.database import load_all_referrals
                referrals = load_all_referrals()
                today_str = datetime.now().strftime("%Y-%m-%d")
                
                # Count sent today
                emp_messages_sent = sum(
                    1 for r in referrals
                    if str(r.get('Referral_Status') or '').strip().lower() == 'sent'
                    and str(r.get('Sent_Time') or '').strip().startswith(today_str)
                    and str(r.get('Referral_Source') or '').strip() == 'Existing Employee'
                )
                emp_connections_sent = sum(
                    1 for r in referrals
                    if str(r.get('Referral_Status') or '').strip().lower() == 'sent'
                    and str(r.get('Sent_Time') or '').strip().startswith(today_str)
                    and str(r.get('Referral_Source') or '').strip() == 'Sent Employee Connection'
                )
                rec_messages_sent = sum(
                    1 for r in referrals
                    if str(r.get('Referral_Status') or '').strip().lower() == 'sent'
                    and str(r.get('Sent_Time') or '').strip().startswith(today_str)
                    and str(r.get('Referral_Source') or '').strip() == 'Existing Recruiter'
                )
                rec_connections_sent = sum(
                    1 for r in referrals
                    if str(r.get('Referral_Status') or '').strip().lower() == 'sent'
                    and str(r.get('Sent_Time') or '').strip().startswith(today_str)
                    and str(r.get('Referral_Source') or '').strip() == 'Sent Recruiter Connection'
                )
                
                total_sent = emp_messages_sent + emp_connections_sent + rec_messages_sent + rec_connections_sent
                
                self.log("=" * 60)
                self.log("--- Pipeline Execution Summary ---")
                self.log(f"Existing Employee Messages Sent   : {emp_messages_sent}")
                self.log(f"Employee Connection Requests Sent : {emp_connections_sent}")
                self.log(f"Existing Recruiter Messages Sent   : {rec_messages_sent}")
                self.log(f"Recruiter Connection Requests Sent : {rec_connections_sent}")
                self.log(f"Total Outreach Actions Sent Today : {total_sent}")
                
                # Load selected config targets for the pinned user
                from config.user_profiles import load_all_configs
                all_cfg = load_all_configs()
                user_conf = all_cfg.get("users", {}).get(self.username, {})
                connect_conf = user_conf.get("linkedin_connect", {})
                max_connections = int(connect_conf.get("max_connections_per_run") or 5)
                
                if total_sent > 0:
                    self.log("Status: Completed Successfully")
                else:
                    self.log("Status: Completed – No Candidates Available")
                self.log("=" * 60)
            except Exception as e:
                self.log(f"Warning: error compiling execution summary: {e}")

    def send_input(self, text):
        if self.process and self.process.stdin:
            try:
                self.process.stdin.write(text + "\n")
                self.process.stdin.flush()
                self.log(f"Piped input: {text}")
                self.waiting_for_input = False
                return True
            except Exception as e:
                self.log(f"Failed to write to stdin: {e}")
        return False

    def kill(self):
        if self.process:
            try:
                if sys.platform == 'win32':
                    self.process.terminate()
                else:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                self.log("Process terminated by user.")
            except Exception as e:
                self.log(f"Error terminating process: {e}")
        self.status = "killed"
        self.waiting_for_input = False


def get_excel_data(file_path):
    from core.storage.database import get_sheets_config
    sheets_conf = get_sheets_config()
    if sheets_conf:
        url, creds = sheets_conf
        from core.storage.sheets import read_rows
        from config.settings import get_job_tracker_file, get_job_leads_file, get_referrals_file
        
        worksheet_name = None
        if str(file_path) == str(get_job_tracker_file()):
            worksheet_name = "Scraped Emails"
        elif str(file_path) == str(get_job_leads_file()):
            worksheet_name = "Job Leads"
        elif str(file_path) == str(get_referrals_file()):
            worksheet_name = "Referrals & Connections"
            
        if worksheet_name:
            try:
                return read_rows(url, creds, worksheet_name)
            except Exception as e:
                print(f"Error reading Google Sheets worksheet '{worksheet_name}': {e}")

    if not os.path.exists(file_path):
        return []
    try:
        df = pd.read_excel(file_path)
        df = df.fillna("")
        return df.to_dict(orient="records")
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return []


@app.route('/')
def home():
    return render_template('index.html')

def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.after_request
def add_header(response):
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1'
    return response

@app.route('/api/stats')
def get_stats():
    job_tracker = get_excel_data(get_job_tracker_file())
    job_leads = get_excel_data(get_job_leads_file())

    total_emails = len(job_tracker)
    emails_sent = sum(1 for r in job_tracker if str(r.get('Status')).strip().lower() == 'sent')
    
    total_leads = len(job_leads)
    
    referral_requests_sent = sum(1 for r in job_leads if str(r.get('Status')).strip().lower() in ('ask for referral', 'asked for referral', 'done', 'referred'))
    done_referrals = sum(1 for r in job_leads if str(r.get('Status')).strip().lower() == 'done')

    return jsonify({
        "total_emails_scraped": total_emails,
        "emails_sent": emails_sent,
        "total_jobs_scraped": total_leads,
        "referral_requests_sent": referral_requests_sent,
        "done_jobs_count": done_referrals
    })


@app.route('/api/email_stats')
def email_stats():
    return jsonify(get_email_metrics())

@app.route('/api/company_stats')
def company_stats():
    return jsonify(get_company_metrics())

@app.route('/api/outreach_stats')
def outreach_stats():
    return jsonify(get_outreach_metrics())

@app.route('/api/data/job_tracker')
def job_tracker_data():
    from core.storage.database import get_sheets_config, init_scraper_store
    # Only initialise local file when not using Google Sheets (avoids creating
    # unnecessary xlsx files and hitting the Sheets API on startup)
    if not get_sheets_config():
        init_scraper_store()
    return jsonify(get_excel_data(get_job_tracker_file()))

@app.route('/api/data/job_leads')
def job_leads_data():
    from core.storage.database import load_job_leads_with_referral_counts
    return jsonify(load_job_leads_with_referral_counts())


@app.route('/api/run/scraper', methods=['POST'])
def start_scraper():
    with task_lock:
        body = request.get_json(silent=True) or {}
        # Use username from request body, or fall back to the currently selected user
        username = body.get("username") or get_selected_user_name()
        task_id = f"{username}::scraper_pipeline"
        
        if task_id in active_tasks and active_tasks[task_id].status in ("running", "queued"):
            return jsonify({"status": "error", "message": "Pipeline is already running or queued."}), 400
        
        phase = body.get("phase", "full")
        
        # Route each phase to its dedicated runner script for clean separation of concerns.
        # The combined run_email_outreach.py is used only for the full pipeline run.
        if phase == "phase1":
            commands = [("run_email_scraper.py", [])]
        elif phase == "phase2":
            commands = [("run_email_sender.py", [])]
        else:
            commands = [("run_email_outreach.py", [])]
        
        runner = SubprocessRunner(task_id, commands, username)
        active_tasks[task_id] = runner
        runner.start()
        
        return jsonify({"status": "success", "task_id": task_id})


@app.route('/api/run/referral', methods=['POST'])
def start_referral():
    with task_lock:
        body = request.get_json() or {}
        username = body.get("username") or get_selected_user_name()
        task_id = f"{username}::referral_pipeline"
        
        if task_id in active_tasks and active_tasks[task_id].status in ("running", "queued"):
            return jsonify({"status": "error", "message": "Pipeline is already running or queued."}), 400
        
        step = body.get("step")
        
        all_commands = [
            ("run_job_search.py", []),
            ("run_referral_review.py", []),
            ("run_referral_outreach_discover.py", []),
            ("run_referral_outreach_send.py", []),
            ("run_url_shortener.py", []),
            ("run_linkedin_connect.py", [])
        ]
        
        if step is not None:
            try:
                step_idx = int(step) - 1
                if step_idx < 0 or step_idx >= len(all_commands):
                    return jsonify({"status": "error", "message": f"Invalid step: {step}"}), 400
                commands = [all_commands[step_idx]]
            except ValueError:
                return jsonify({"status": "error", "message": f"Step must be an integer: {step}"}), 400
        else:
            commands = all_commands
        
        runner = SubprocessRunner(task_id, commands, username)
        active_tasks[task_id] = runner
        runner.start()
        
        return jsonify({"status": "success", "task_id": task_id})


@app.route('/api/run/recruiter', methods=['POST'])
def start_recruiter():
    with task_lock:
        body = request.get_json() or {}
        username = body.get("username") or get_selected_user_name()
        task_id = f"{username}::recruiter_pipeline"
        
        if task_id in active_tasks and active_tasks[task_id].status in ("running", "queued"):
            return jsonify({"status": "error", "message": "Pipeline is already running or queued."}), 400
        
        step = body.get("step")
        
        all_commands = [
            ("run_recruiter_outreach_discover.py", []),
            ("run_recruiter_outreach_send.py", []),
            ("run_recruiter_outreach.py", [])
        ]
        
        if step is not None:
            try:
                step_idx = int(step) - 1
                if step_idx < 0 or step_idx >= len(all_commands):
                    return jsonify({"status": "error", "message": f"Invalid step: {step}"}), 400
                commands = [all_commands[step_idx]]
            except ValueError:
                return jsonify({"status": "error", "message": f"Step must be an integer: {step}"}), 400
        else:
            commands = all_commands
        
        runner = SubprocessRunner(task_id, commands, username)
        active_tasks[task_id] = runner
        runner.start()
        
        return jsonify({"status": "success", "task_id": task_id})


@app.route('/api/tasks')
def get_all_tasks():
    with task_lock:
        result = {}
        for tid, runner in active_tasks.items():
            result[tid] = {
                "status": runner.status,
                "username": runner.username,
                "waiting_for_input": runner.waiting_for_input,
                "current_step": runner.current_step,
                "total_steps": len(runner.commands)
            }
        return jsonify(result)


@app.route('/api/task/<task_id>/logs')
def get_task_logs(task_id):
    with task_lock:
        if task_id not in active_tasks:
            return jsonify({"status": "error", "message": "Task not found"}), 404
        
        runner = active_tasks[task_id]
        current_step_name = None
        args = []
        if runner.current_step > 0 and runner.current_step <= len(runner.commands):
            cmd_tuple = runner.commands[runner.current_step - 1]
            current_step_name = cmd_tuple[0]
            args = cmd_tuple[1]
        
        return jsonify({
            "status": runner.status,
            "waiting_for_input": runner.waiting_for_input,
            "logs": runner.logs,
            "current_step_name": current_step_name,
            "args": args,
            "is_single_step": len(runner.commands) == 1
        })


@app.route('/api/task/<task_id>/input', methods=['POST'])
def send_task_input(task_id):
    with task_lock:
        if task_id not in active_tasks:
            return jsonify({"status": "error", "message": "Task not found"}), 404
        
        body = request.get_json() or {}
        val = body.get("input", "")
        
        runner = active_tasks[task_id]
        success = runner.send_input(val)
        
        if success:
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "error", "message": "Failed to send input"}), 500


@app.route('/api/task/<task_id>/kill', methods=['POST'])
def kill_task(task_id):
    with task_lock:
        if task_id not in active_tasks:
            return jsonify({"status": "error", "message": "Task not found"}), 404
        
        runner = active_tasks[task_id]
        runner.kill()
        return jsonify({"status": "success"})


@app.route('/api/users', methods=['GET'])
def get_users_list():
    config = load_all_configs()
    users = list(config.get("users", {}).keys())
    selected = config.get("selected_user", "")
    
    # Extract profile names for all users
    user_details = {}
    for username, data in config.get("users", {}).items():
        profile = data.get("profile", {})
        user_details[username] = {
            "first_name": profile.get("first_name", ""),
            "last_name": profile.get("last_name", "")
        }
        
    return jsonify({
        "users": users,
        "selected_user": selected,
        "user_details": user_details
    })


@app.route('/api/users/select', methods=['POST'])
def select_active_user():
    body = request.get_json() or {}
    user = body.get("user")
    config = load_all_configs()
    if not user or user not in config.get("users", {}):
        return jsonify({"status": "error", "message": "User not found"}), 404
    config["selected_user"] = user
    save_all_configs(config)
    return jsonify({"status": "success"})


@app.route('/api/users/create', methods=['POST'])
def create_user_profile():
    body = request.get_json() or {}
    username = body.get("username", "").strip()
    if not username:
        return jsonify({"status": "error", "message": "Username is required"}), 400
    
    config = load_all_configs()
    if username in config.get("users", {}):
        return jsonify({"status": "error", "message": "User already exists"}), 400
        
    config["users"][username] = {
        "profile": {
            "first_name": username,
            "last_name": "",
            "email": "",
            "phone": "",
            "resume_name": "",
            "resume_url": "",
            "current_location": "",
            "preferred_locations": "",
            "experience": "",
            "linkedin_url": "",
            "current_ctc": "",
            "expected_ctc": ""
        },
        "email_scraper": {
            "email_template": DEFAULT_EMAIL_TEMPLATE,
            "email_subject": "",
            "search_keywords": [],
            "title_keywords": [],
            "keywords": [],
            "excluded_keywords": [],
            "sender_email": "",
            "interval": "60",
            "review_mode": True,
            "max_emails_per_run": "5"
        },
        "linkedin_connect": {
            "message_template": DEFAULT_CONNECTION_TEMPLATE,
            "search_keywords": [],
            "title_keywords": [],
            "keywords": [],
            "excluded_keywords": [],
            "interval": "60",
            "review_mode": True,
            "max_connections_per_company": "5",
            "max_connections_per_run": "5"
        },
        "recruiter_outreach": {
            "message_template": "Hi {first_name}, let's connect! I saw you handle Talent Acquisition at {company}. I am interested in opportunities there. My resume: {resume}",
            "interval": "120",
            "daily_limit": "5",
            "target_count": "2",
            "review_mode": True
        },
        "referral_outreach": {
            "message_template": "Hi {RECEIVER_NAME},\n\nI hope you're doing well! I saw we're connected on LinkedIn and noticed you work at {COMPANY}.\n\nI'm interested in a role there and would love your guidance or a referral if possible.\n\nJob: {JOB_URL}\nResume: {RESUME}\n\nThank you!",
            "interval": "60",
            "max_referrals_per_run": "5",
            "review_mode": True
        }
    }
    config["selected_user"] = username
    save_all_configs(config)
    return jsonify({"status": "success", "selected_user": username})


@app.route('/api/config/sheets/test', methods=['POST'])
def test_sheets_connection():
    body = request.get_json() or {}
    url = body.get("google_sheet_url", "").strip()
    creds = body.get("google_credentials_json", "").strip()
    
    if not url:
        return jsonify({"status": "error", "message": "Google Sheet URL is required"}), 400
    if not creds:
        return jsonify({"status": "error", "message": "Google Credentials JSON content is required"}), 400
        
    try:
        from core.storage.sheets import ensure_worksheets_exist
        ensure_worksheets_exist(url, creds)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route('/api/config/storage/switch', methods=['POST'])
def switch_storage_type():
    """Streams migration progress via Server-Sent Events (SSE).
    
    When a user changes database_type in Settings, this endpoint:
      - Detects the switch direction (local→sheets or sheets→local)
      - Runs the appropriate migration inline with live log streaming
      - Saves the new config after successful migration
    
    The client polls this endpoint using EventSource / fetch+ReadableStream.
    Each SSE event is a JSON line: {"type": "log"|"done"|"error", "message": "..."}
    """
    body = request.get_json() or {}
    new_type = body.get("database_type", "").strip()       # "local" or "google_sheets"
    global_settings_payload = body.get("global_settings") or {}

    if new_type not in ("local", "google_sheets"):
        return jsonify({"status": "error", "message": "Invalid database_type value"}), 400

    def generate():
        import traceback, time as _time

        def emit(event_type, message):
            """Yield a Server-Sent Events line."""
            import json as _json
            yield f"data: {_json.dumps({'type': event_type, 'message': message})}\n\n"

        try:
            from config.user_profiles import (
                load_all_configs, save_all_configs, get_selected_user_name, get_global_settings
            )
            from config.settings import get_job_tracker_file, get_job_leads_file, get_referrals_file
            from config.constants import GOOGLE_SHEET_WORKSHEETS

            username = get_selected_user_name()
            current_type = get_global_settings().get("database_type", "local")

            yield from emit("log", f"Active profile: {username}")
            yield from emit("log", f"Current storage: {current_type}  →  New storage: {new_type}")

            if current_type == new_type:
                yield from emit("log", "Storage type unchanged. Saving config...")
                # Still persist the rest of the settings
                config = load_all_configs()
                config["global_settings"] = {**config.get("global_settings", {}), **global_settings_payload, "database_type": new_type}
                save_all_configs(config)
                yield from emit("done", "Configuration saved. No migration needed.")
                return

            # ---------------------------------------------------------------
            # LOCAL  →  GOOGLE SHEETS
            # ---------------------------------------------------------------
            if new_type == "google_sheets":
                yield from emit("log", "Direction: Local Excel → Google Sheets")

                sheet_url = global_settings_payload.get("google_sheet_url", "").strip()
                creds_content = global_settings_payload.get("google_credentials_json", "").strip()

                if not sheet_url or not creds_content:
                    yield from emit("error", "Google Sheet URL and Credentials JSON are required to switch to Google Sheets storage.")
                    return

                yield from emit("log", "Step 1: Authenticating with Google APIs...")
                try:
                    import gspread, json as _json2
                    from google.oauth2.service_account import Credentials
                    scopes = [
                        "https://spreadsheets.google.com/feeds",
                        "https://www.googleapis.com/auth/drive"
                    ]
                    creds_dict = _json2.loads(creds_content)
                    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
                    client = gspread.authorize(credentials)
                    sh = client.open_by_url(sheet_url)
                    yield from emit("log", f"Authentication OK. Opened sheet: '{sh.title}'")
                except Exception as e:
                    yield from emit("error", f"Authentication failed: {e}")
                    return

                local_paths = {
                    "Job Leads": get_job_leads_file(),
                    "Scraped Emails": get_job_tracker_file(),
                    "Referrals & Connections": get_referrals_file()
                }
                id_cols = {
                    "Job Leads": "JobID",
                    "Scraped Emails": "ID",
                    "Referrals & Connections": "ReferralID"
                }

                import openpyxl as _xl

                yield from emit("log", "Step 2: Migrating local Excel data to Google Sheets...")
                for key, info in GOOGLE_SHEET_WORKSHEETS.items():
                    if key == "config":
                        continue
                    ws_name = info["name"]
                    headers = info["headers"]
                    local_file = local_paths[ws_name]
                    id_col = id_cols[ws_name]

                    yield from emit("log", f"  Processing '{ws_name}'...")
                    _time.sleep(1.5)  # throttle to avoid 429

                    # Read cloud IDs
                    try:
                        ws = sh.worksheet(ws_name)
                        cloud_rows = ws.get_all_records()
                    except Exception as e:
                        yield from emit("log", f"  Warning: Could not read worksheet '{ws_name}': {e}")
                        cloud_rows = []

                    cloud_ids = {str(r.get(id_col, "") or "").rstrip(".0") for r in cloud_rows}

                    if not os.path.exists(local_file):
                        yield from emit("log", f"  No local file found for '{ws_name}'. Skipping.")
                        continue

                    try:
                        wb = _xl.load_workbook(local_file)
                        lws = wb.active
                        col_map = {cell.value: idx for idx, cell in enumerate(lws[1], start=1)}
                        id_idx = col_map.get(id_col)
                        new_rows = []
                        for row in range(2, lws.max_row + 1):
                            row_id = str(lws.cell(row=row, column=id_idx).value or "").rstrip(".0") if id_idx else ""
                            if row_id and row_id not in cloud_ids:
                                row_data = {}
                                for h, ci in col_map.items():
                                    row_data[h] = lws.cell(row=row, column=ci).value or ""
                                new_rows.append(row_data)
                    except Exception as e:
                        yield from emit("log", f"  Warning: Could not read local file for '{ws_name}': {e}")
                        continue

                    yield from emit("log", f"  Local rows: {lws.max_row - 1}  |  Cloud rows: {len(cloud_rows)}  |  New to upload: {len(new_rows)}")

                    if new_rows:
                        try:
                            for r in new_rows:
                                row_vals = [str(r.get(h, "") or "") for h in headers]
                                ws.append_row(row_vals)
                                _time.sleep(0.3)
                            yield from emit("log", f"  Uploaded {len(new_rows)} new rows to '{ws_name}'.")
                        except Exception as e:
                            yield from emit("log", f"  Warning: Upload error for '{ws_name}': {e}")
                    else:
                        yield from emit("log", f"  '{ws_name}' already up to date.")

                    # Invalidate sheets cache so next UI load fetches fresh data
                    try:
                        from core.storage.sheets import _cache_invalidate
                        _cache_invalidate(ws_name)
                    except Exception:
                        pass

            # ---------------------------------------------------------------
            # GOOGLE SHEETS  →  LOCAL
            # ---------------------------------------------------------------
            else:  # new_type == "local"
                yield from emit("log", "Direction: Google Sheets → Local Excel")

                current_settings = get_global_settings()
                sheet_url = current_settings.get("google_sheet_url", "").strip()
                creds_content = current_settings.get("google_credentials_json", "").strip()

                if not sheet_url or not creds_content:
                    yield from emit("log", "No Google Sheets credentials found. Switching to local without migration.")
                else:
                    yield from emit("log", "Step 1: Authenticating with Google APIs...")
                    try:
                        import gspread, json as _json3
                        from google.oauth2.service_account import Credentials
                        scopes = [
                            "https://spreadsheets.google.com/feeds",
                            "https://www.googleapis.com/auth/drive"
                        ]
                        creds_dict = _json3.loads(creds_content)
                        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
                        client = gspread.authorize(credentials)
                        sh = client.open_by_url(sheet_url)
                        yield from emit("log", f"Authentication OK. Opened sheet: '{sh.title}'")
                    except Exception as e:
                        yield from emit("error", f"Authentication failed: {e}")
                        return

                    local_paths = {
                        "Job Leads": get_job_leads_file(),
                        "Scraped Emails": get_job_tracker_file(),
                        "Referrals & Connections": get_referrals_file()
                    }
                    id_cols = {
                        "Job Leads": "JobID",
                        "Scraped Emails": "ID",
                        "Referrals & Connections": "ReferralID"
                    }

                    import openpyxl as _xl2

                    yield from emit("log", "Step 2: Pulling Google Sheets data into local Excel files...")
                    for key, info in GOOGLE_SHEET_WORKSHEETS.items():
                        if key == "config":
                            continue
                        ws_name = info["name"]
                        headers = info["headers"]
                        local_file = local_paths[ws_name]
                        id_col = id_cols[ws_name]

                        yield from emit("log", f"  Processing '{ws_name}'...")
                        _time.sleep(1.5)

                        try:
                            ws = sh.worksheet(ws_name)
                            cloud_rows = ws.get_all_records()
                        except Exception as e:
                            yield from emit("log", f"  Warning: Could not read '{ws_name}': {e}")
                            continue

                        if not cloud_rows:
                            yield from emit("log", f"  No data in '{ws_name}'. Skipping.")
                            continue

                        # Load existing local IDs
                        existing_ids = set()
                        if os.path.exists(local_file):
                            try:
                                wb = _xl2.load_workbook(local_file)
                                lws = wb.active
                                col_map = {cell.value: idx for idx, cell in enumerate(lws[1], start=1)}
                                id_idx = col_map.get(id_col)
                                if id_idx:
                                    for row in range(2, lws.max_row + 1):
                                        val = lws.cell(row=row, column=id_idx).value
                                        if val is not None:
                                            existing_ids.add(str(val).rstrip(".0"))
                            except Exception:
                                pass

                        new_rows = [
                            r for r in cloud_rows
                            if str(r.get(id_col, "") or "").rstrip(".0") not in existing_ids
                            and str(r.get(id_col, "") or "").strip()
                        ]

                        yield from emit("log", f"  Cloud rows: {len(cloud_rows)}  |  Local existing: {len(existing_ids)}  |  New to write: {len(new_rows)}")

                        if not new_rows:
                            yield from emit("log", f"  Local already up to date.")
                            continue

                        try:
                            if os.path.exists(local_file):
                                wb = _xl2.load_workbook(local_file)
                                lws = wb.active
                            else:
                                wb = _xl2.Workbook()
                                lws = wb.active
                                lws.title = ws_name.replace(" & ", " ")
                                lws.append(headers)

                            for r in new_rows:
                                lws.append([str(r.get(h, "") or "") for h in headers])
                            wb.save(local_file)
                            yield from emit("log", f"  Written {len(new_rows)} rows to local file.")
                        except Exception as e:
                            yield from emit("log", f"  Warning: Could not write to local file for '{ws_name}': {e}")

            # ---------------------------------------------------------------
            # Save updated config after successful migration
            # ---------------------------------------------------------------
            yield from emit("log", "Step 3: Saving new storage configuration...")
            config = load_all_configs()
            existing_gs = config.get("global_settings", {})
            merged_gs = {**existing_gs, **global_settings_payload, "database_type": new_type}
            config["global_settings"] = merged_gs
            save_all_configs(config)
            yield from emit("done", f"Migration complete! Active storage is now: {new_type.replace('_', ' ').title()}")

        except GeneratorExit:
            return
        except Exception as e:
            yield from emit("error", f"Unexpected error during migration: {traceback.format_exc()}")

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})




@app.route('/api/users/config', methods=['GET'])
def get_user_configuration():
    config = load_all_configs()
    username = get_selected_user_name()
    user_data = config.get("users", {}).get(username, {})
    global_settings = get_global_settings()
    return jsonify({
        "username": username,
        "config": user_data,
        "global_settings": global_settings
    })


@app.route('/api/users/config', methods=['POST'])
def save_user_configuration():
    body = request.get_json() or {}
    config = load_all_configs()
    username = get_selected_user_name()
    
    if username not in config.get("users", {}):
        return jsonify({"status": "error", "message": f"User {username} not found"}), 404
    
    existing_user = config["users"][username]
    
    # Helper: deep merge incoming section over existing section so no fields are lost
    def merge_section(existing, incoming):
        if not incoming:
            return existing
        merged = dict(existing)
        merged.update({k: v for k, v in incoming.items() if v is not None and v != ''})
        return merged
    
    # For profile and global_settings, always use the full incoming value (they are fully managed by UI)
    user_profile = body.get("profile") or {}
    global_settings = body.get("global_settings") or {}
    
    # For pipeline sections, merge incoming over existing so stale/missing fields are preserved
    email_scraper_incoming = body.get("email_scraper") or {}
    linkedin_connect_incoming = body.get("linkedin_connect") or {}
    recruiter_outreach_incoming = body.get("recruiter_outreach") or {}
    referral_outreach_incoming = body.get("referral_outreach") or {}
    
    existing_scraper = existing_user.get("email_scraper") or {}
    existing_connect = existing_user.get("linkedin_connect") or {}
    existing_recruiter = existing_user.get("recruiter_outreach") or {}
    existing_referral = existing_user.get("referral_outreach") or {}
    
    # Apply scraper defaults for missing fields
    scraper_defaults = {
        "interval": "60",
        "review_mode": True,
        "max_emails_per_run": "5",
        "search_keywords": [],
        "title_keywords": [],
        "keywords": [],
        "excluded_keywords": [],
        "email_subject": "",
        "email_template": "",
        "sender_email": ""
    }
    existing_scraper = {**scraper_defaults, **existing_scraper}
    
    # Apply connect defaults for missing fields
    connect_defaults = {
        "interval": "60",
        "review_mode": True,
        "max_connections_per_company": "5",
        "max_connections_per_run": "5",
        "search_keywords": [],
        "title_keywords": [],
        "keywords": [],
        "excluded_keywords": [],
        "message_template": ""
    }
    existing_connect = {**connect_defaults, **existing_connect}
    
    # Apply recruiter defaults for missing fields
    recruiter_defaults = {
        "interval": "120",
        "target_count": "2",
        "review_mode": True,
        "message_template": "",
        "direct_message_template": ""
    }
    existing_recruiter = {**recruiter_defaults, **existing_recruiter}
    
    # Merge: incoming takes precedence, but existing fills gaps
    email_scraper = {**existing_scraper, **{k: v for k, v in email_scraper_incoming.items() if v is not None}}
    linkedin_connect = {**existing_connect, **{k: v for k, v in linkedin_connect_incoming.items() if v is not None}}
    recruiter_outreach = {**existing_recruiter, **{k: v for k, v in recruiter_outreach_incoming.items() if v is not None}}
    referral_outreach = {**existing_referral, **{k: v for k, v in referral_outreach_incoming.items() if v is not None}}
    
    config["users"][username]["profile"] = user_profile
    config["users"][username]["email_scraper"] = email_scraper
    config["users"][username]["linkedin_connect"] = linkedin_connect
    config["users"][username]["recruiter_outreach"] = recruiter_outreach
    config["users"][username]["referral_outreach"] = referral_outreach
    config["global_settings"] = global_settings
    
    save_all_configs(config)
    return jsonify({"status": "success"})


@app.route('/api/users/config/keywords', methods=['POST'])
def save_user_keywords():
    body = request.get_json() or {}
    kws_type = body.get("type")
    keywords = body.get("keywords", [])

    valid_types = ("scraper", "connect", "scraper-excluded", "connect-excluded")
    if kws_type not in valid_types:
        return jsonify({"status": "error", "message": "Invalid keywords type"}), 400

    config = load_all_configs()
    username = get_selected_user_name()
    if username not in config.get("users", {}):
        return jsonify({"status": "error", "message": f"User {username} not found"}), 404

    if kws_type in ("scraper", "scraper-excluded"):
        target_section = "email_scraper"
    else:
        target_section = "linkedin_connect"

    field = "keywords" if kws_type in ("scraper", "connect") else "excluded_keywords"
    config["users"][username][target_section][field] = [k.strip() for k in keywords if str(k).strip()]

    save_all_configs(config)
    return jsonify({"status": "success"})


@app.route('/api/users/resume/upload', methods=['POST'])
def upload_user_resume():
    if 'resume' not in request.files:
        return jsonify({"status": "error", "message": "No file uploaded"}), 400
    file = request.files['resume']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No file selected"}), 400
        
    if file:
        config = load_all_configs()
        username = get_selected_user_name()
        resumes_dir = get_resumes_dir()
        os.makedirs(resumes_dir, exist_ok=True)
        
        # Resume Replacement Logic: remove previous active resume if it exists
        if username in config.get("users", {}):
            old_resume_name = config["users"][username].get("profile", {}).get("resume_name", "")
            if old_resume_name:
                old_resume_path = os.path.join(resumes_dir, old_resume_name)
                if os.path.exists(old_resume_path):
                    try:
                        os.remove(old_resume_path)
                    except Exception as e:
                        app.logger.warning(f"Failed to delete old resume file {old_resume_path}: {e}")

        filename = secure_filename(file.filename)
        new_filename = filename
        save_path = os.path.join(resumes_dir, new_filename)
        file.save(save_path)
        
        if username in config.get("users", {}):
            config["users"][username]["profile"]["resume_name"] = new_filename
            save_all_configs(config)
            
        return jsonify({"status": "success", "resume_name": new_filename})


@app.route('/api/users/resume/download/<username>', methods=['GET'])
def download_user_resume(username):
    config = load_all_configs()
    user_data = config.get("users", {}).get(username, {})
    resume_name = user_data.get("profile", {}).get("resume_name", "")
    
    resumes_dir = get_resumes_dir()
    user_resume_path = os.path.join(resumes_dir, resume_name) if resume_name else ""

    if resume_name and os.path.exists(user_resume_path):
        return send_from_directory(resumes_dir, resume_name, as_attachment=False)

    # Fall back to the default resume path
    default_path = get_resume_file_path(user_data.get("profile", {}))
    if os.path.exists(default_path):
        return send_file(default_path, as_attachment=False)

    return "Resume not found", 404


@app.route('/api/config', methods=['GET'])
def get_config():
    user_conf = get_selected_user_config()
    global_conf = get_global_settings()
    profile = user_conf.get("profile", {})
    scraper = user_conf.get("email_scraper", {})
    
    response_data = {
        "LINKEDIN_EMAIL": global_conf.get("linkedin_email", ""),
        "LINKEDIN_PASSWORD": global_conf.get("linkedin_password", ""),
        "SEARCH_KEYWORDS": "|".join(scraper.get("search_keywords") or scraper.get("keywords") or []),
        "SEARCH_LOCATION": global_conf.get("search_location", "Bangalore, Karnataka, India"),
        "SEARCH_TIME_RANGE": global_conf.get("search_time_range", "r604800"),
        "DRY_RUN": global_conf.get("dry_run", "0"),
        "MAX_RUN_DURATION_SECONDS": global_conf.get("max_run_duration_seconds", "600"),
        "RESUME_LINK": profile.get("resume_url", ""),
        "OUTREACH_MODE": "both",
        "MAX_APPLY": global_conf.get("max_apply", "5"),
        "SMTP_EMAIL": global_conf.get("smtp_email", ""),
        "SMTP_PASSWORD": global_conf.get("smtp_password", ""),
        "SISTER_NAME": (profile.get("first_name", "") + " " + profile.get("last_name", "")).strip() or profile.get("full_name", ""),
        "SISTER_EMAIL": profile.get("email", ""),
        "PHONE_NUMBER": profile.get("phone", "")
    }
    return jsonify(response_data)


@app.route('/api/config', methods=['POST'])
def save_config():
    body = request.get_json() or {}
    config = load_all_configs()
    username = get_selected_user_name()
    if username in config.get("users", {}):
        if "SISTER_NAME" in body:
            full_name = (body["SISTER_NAME"] or "").strip()
            parts = full_name.split(maxsplit=1)
            first_name = parts[0] if parts else ""
            last_name = parts[1] if len(parts) > 1 else ""
            config["users"][username]["profile"]["first_name"] = first_name
            config["users"][username]["profile"]["last_name"] = last_name
        if "SISTER_EMAIL" in body:
            config["users"][username]["profile"]["email"] = body["SISTER_EMAIL"]
        if "PHONE_NUMBER" in body:
            config["users"][username]["profile"]["phone"] = body["PHONE_NUMBER"]
        if "RESUME_LINK" in body:
            config["users"][username]["profile"]["resume_url"] = body["RESUME_LINK"]
        if "SEARCH_KEYWORDS" in body:
            keywords_list = [k.strip() for k in body["SEARCH_KEYWORDS"].split("|") if k.strip()]
            config["users"][username]["email_scraper"]["search_keywords"] = keywords_list
            config["users"][username]["email_scraper"]["title_keywords"] = keywords_list
            config["users"][username]["email_scraper"]["keywords"] = keywords_list
        
        # global settings
        if "LINKEDIN_EMAIL" in body:
            config["global_settings"]["linkedin_email"] = body["LINKEDIN_EMAIL"]
        if "LINKEDIN_PASSWORD" in body:
            config["global_settings"]["linkedin_password"] = body["LINKEDIN_PASSWORD"]
        if "SEARCH_LOCATION" in body:
            config["global_settings"]["search_location"] = body["SEARCH_LOCATION"]
        if "SEARCH_TIME_RANGE" in body:
            config["global_settings"]["search_time_range"] = body["SEARCH_TIME_RANGE"]
        if "DRY_RUN" in body:
            config["global_settings"]["dry_run"] = body["DRY_RUN"]
        if "MAX_APPLY" in body:
            config["global_settings"]["max_apply"] = body["MAX_APPLY"]
        if "SMTP_EMAIL" in body:
            config["global_settings"]["smtp_email"] = body["SMTP_EMAIL"]
        if "SMTP_PASSWORD" in body:
            config["global_settings"]["smtp_password"] = body["SMTP_PASSWORD"]
            
        save_all_configs(config)
    return jsonify({"status": "success"})


@app.route('/api/data/update_status', methods=['POST'])
def update_row_status():
    body = request.get_json() or {}
    db_type = body.get("db_type")
    row_id = body.get("id")
    status = body.get("status")
    
    if not db_type or row_id is None or not status:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400
        
    try:
        row_id = int(row_id)
    except ValueError:
        pass
        
    if db_type == "scraper":
        from core.storage.engine import read_database_rows, write_database_rows
        rows = read_database_rows("emails")
        updated = False
        for r in rows:
            if str(r.get('ID')).rstrip(".0") == str(row_id).rstrip(".0"):
                r['Status'] = status
                r['Timestamp'] = datetime.utcnow().isoformat()
                updated = True
                break
        if updated:
            write_database_rows("emails", rows)
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "ID not found"}), 404
        
    elif db_type == "referral":
        success = update_status_by_id(row_id, status)
        if success:
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "JobID not found"}), 404
        
    else:
        return jsonify({"status": "error", "message": "Invalid db_type"}), 400


@app.route('/api/data/delete_row', methods=['POST'])
def delete_table_row():
    body = request.get_json() or {}
    db_type = body.get("db_type")
    row_id = body.get("id")
    
    if not db_type or row_id is None:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400
        
    table_key = "emails" if db_type == "scraper" else "jobs"
    id_field = "ID" if db_type == "scraper" else "JobID"
    
    from core.storage.engine import read_database_rows, write_database_rows
    try:
        rows = read_database_rows(table_key)
        filtered_rows = [r for r in rows if str(r.get(id_field)).rstrip(".0") != str(row_id).rstrip(".0")]
        if len(filtered_rows) < len(rows):
            write_database_rows(table_key, filtered_rows)
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": f"{id_field} not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/data/edit_row', methods=['POST'])
def edit_table_row():
    body = request.get_json() or {}
    db_type = body.get("db_type")
    row_id = body.get("id")
    
    if not db_type or row_id is None:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400
        
    try:
        row_id = int(row_id)
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid ID"}), 400
        
    if db_type == "scraper":
        email = body.get("email")
        status = body.get("status")
        keyword = body.get("keyword")
        post_url = body.get("post_url")
        company_name = body.get("company_name")
        experience = body.get("experience")
        location = body.get("location")
        if not email or not status:
            return jsonify({"status": "error", "message": "Missing required fields"}), 400
        success = edit_row(row_id, email, status, keyword,
                           post_url=post_url, company_name=company_name,
                           experience=experience, location=location,
                           path=get_job_tracker_file())
        if success:
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "ID not found"}), 404
    elif db_type == "referral":
        company = body.get("company")
        url = body.get("url")
        shorten = body.get("shorten")
        keyword = body.get("keyword")
        position = body.get("position")
        status = body.get("status")
        if not company or not url or not status:
            return jsonify({"status": "error", "message": "Missing company, url, or status"}), 400
        success = edit_lead_row(row_id, company, url, shorten, keyword, position, status, get_job_leads_file())
        if success:
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "JobID not found"}), 404
    else:
        return jsonify({"status": "error", "message": "Invalid db_type"}), 400


@app.route('/api/data/referrals')
def referrals_data():
    from core.storage.database import get_sheets_config, init_referrals_store, load_all_referrals
    # Only initialise local file when not using Google Sheets
    if not get_sheets_config():
        init_referrals_store()
    # Do NOT pass path= here — load_all_referrals() detects Sheets mode automatically
    return jsonify(load_all_referrals())


@app.route('/api/data/update_referral_status', methods=['POST'])
def update_referral_status():
    body = request.get_json() or {}
    referral_id = body.get("id")
    status = body.get("status") 
    
    if referral_id is None or not status:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400
        
    try:
        referral_id = int(referral_id)
    except ValueError:
        pass
        
    from core.storage.database import edit_referral_contact_row, sync_job_lead_referral_statuses
    success = edit_referral_contact_row(referral_id, {"Referral_Status": status}, get_referrals_file())
    if success:
        sync_job_lead_referral_statuses()
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "ReferralID not found"}), 404


@app.route('/api/data/edit_referral_row', methods=['POST'])
def edit_referral_row():
    body = request.get_json() or {}
    referral_id = body.get("id")
    if referral_id is None:
        return jsonify({"status": "error", "message": "Missing ReferralID"}), 400
        
    try:
        referral_id = int(referral_id)
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid ReferralID"}), 400
        
    name = body.get("name")
    email = body.get("email")
    profile_url = body.get("profile_url")
    source = body.get("source")
    status = body.get("status")
    company = body.get("company")
    job_url = body.get("job_url") or body.get("company_url")
    notes = body.get("notes")
    verification = body.get("employment_verification_status") or "Verified"
    
    if not name or not profile_url or not status or not company:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400
        
    update_data = {
        "CompanyName": company,
        "Job_URL": job_url or "",
        "Referral_Person_Name": name,
        "Referral_Person_Email": email or "",
        "Referral_Person_Profile_URL": profile_url,
        "Referral_Source": source or "Existing Connection",
        "Referral_Status": status,
        "Employment_Verification_Status": verification,
        "Error_Reason": notes or ""
    }
    
    from core.storage.database import edit_referral_contact_row, sync_job_lead_referral_statuses
    success = edit_referral_contact_row(referral_id, update_data, get_referrals_file())
    if success:
        sync_job_lead_referral_statuses()
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "ReferralID not found"}), 404


@app.route('/api/data/delete_referral_row', methods=['POST'])
def delete_referral_row():
    body = request.get_json() or {}
    referral_id = body.get("id")
    if referral_id is None:
        return jsonify({"status": "error", "message": "Missing ReferralID"}), 400
        
    try:
        referral_id = int(referral_id)
    except ValueError:
        pass
        
    from core.storage.database import get_sheets_config
    sheets_conf = get_sheets_config()
    if sheets_conf:
        url, creds = sheets_conf
        from core.storage.sheets import read_rows, write_rows
        try:
            rows = read_rows(url, creds, "Referrals & Connections")
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 400
        filtered_rows = [r for r in rows if str(r.get("ReferralID")).strip() != str(referral_id).strip()]
        if len(filtered_rows) < len(rows):
            write_rows(url, creds, "Referrals & Connections", filtered_rows)
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "ReferralID not found in Google Sheets"}), 404

    path = get_referrals_file()
    if not os.path.exists(path):
        return jsonify({"status": "error", "message": "File not found"}), 404
        
    try:
        wb = openpyxl.load_workbook(path)
        if "Referrals" not in wb.sheetnames:
            return jsonify({"status": "error", "message": "Referrals sheet not found"}), 404
        ws = wb["Referrals"]
        col_indices = {cell.value: idx for idx, cell in enumerate(ws[1], start=1)}
        id_col = col_indices.get('ReferralID')
        if not id_col:
            return jsonify({"status": "error", "message": "ReferralID column not found"}), 500
            
        deleted = False
        for row in range(2, ws.max_row + 1):
            val = ws.cell(row=row, column=id_col).value
            if val is not None and str(val).strip() == str(referral_id).strip():
                ws.delete_rows(row)
                deleted = True
                break
                
        if deleted:
            ws._tables.clear()
            from config.constants import REFERRAL_HEADERS
            ref_range = f"A1:{chr(64 + len(REFERRAL_HEADERS))}{ws.max_row}"
            from openpyxl.worksheet.table import Table, TableStyleInfo
            tab = Table(displayName="ReferralsTable", ref=ref_range)
            style = TableStyleInfo(
                name="TableStyleLight9",
                showFirstColumn=False,
                showLastColumn=False,
                showRowStripes=True,
                showColumnStripes=False,
            )
            tab.tableStyleInfo = style
            ws.add_table(tab)
            wb.save(path)
            _trigger_mac_excel_reload(path)
            from core.storage.database import sync_job_lead_referral_statuses
            sync_job_lead_referral_statuses()
            return jsonify({"status": "success"})
            
        return jsonify({"status": "error", "message": "ReferralID not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500



@app.route('/api/dev-reload')
def dev_reload():
    def event_stream():
        while True:
            time.sleep(10)
            yield "data: ping\n\n"
    return Response(event_stream(), mimetype="text/event-stream")


def sanitize_excel_files():
    # Loop over all users and sanitize their LinkedIn_Job_Tracker.xlsx file to match the latest schema
    config_dir = "users"
    if os.path.exists(config_dir):
        for user in os.listdir(config_dir):
            user_path = os.path.join(config_dir, user)
            if os.path.isdir(user_path):
                excel_path = os.path.join(user_path, "data", "LinkedIn_Job_Tracker.xlsx")
                if os.path.exists(excel_path):
                    try:
                        from core.storage.database import trim_job_leads_excel_to_schema
                        trim_job_leads_excel_to_schema(excel_path)
                        print(f"Sanitized: aligned {excel_path} to latest schema")
                    except Exception as e:
                        print(f"Error sanitizing {excel_path}: {e}")


if __name__ == '__main__':
    # Ensure standard directories exist
    os.makedirs("templates", exist_ok=True)
    os.makedirs("static/css", exist_ok=True)
    os.makedirs("static/js", exist_ok=True)
    
    # Sanitize existing databases
    sanitize_excel_files()
    
    # Watch templates and static files to trigger reloader
    extra_files = []
    for extra_dir in ["templates", "static"]:
        if os.path.exists(extra_dir):
            for root, dirs, files in os.walk(extra_dir):
                for file in files:
                    extra_files.append(os.path.join(root, file))
    
    print("Connectify Automation Hub starting at http://127.0.0.1:5001")
    app.run(host='127.0.0.1', port=5001, debug=True, extra_files=extra_files)
