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
    BASE_DIR, get_job_tracker_file, get_job_leads_file, get_resumes_dir, get_active_user
)
from config.user_profiles import (
    load_all_configs, save_all_configs, get_selected_user_name,
    get_selected_user_config, get_global_settings, get_resume_file_path
)
from config.email_templates import DEFAULT_EMAIL_TEMPLATE, DEFAULT_CONNECTION_TEMPLATE
from core.analytics.metrics import get_email_metrics, get_company_metrics
from core.storage.database import _trigger_mac_excel_reload, update_status_by_id, edit_row, edit_lead_row

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
    def __init__(self, task_id, commands):
        self.task_id = task_id
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
                try:
                    from config.user_profiles import get_selected_user_config
                    from core.storage.database import load_all_referrals
                    user_conf = get_selected_user_config()
                    connect_conf = user_conf.get("linkedin_connect", {})
                    max_connections = int(connect_conf.get("max_connections_per_run") or 5)
                    
                    referrals = load_all_referrals()
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    ref_sent_count = sum(
                        1 for r in referrals
                        if str(r.get('Referral_Status') or '').strip().lower() == 'sent'
                        and str(r.get('Sent_Time') or '').strip().startswith(today_str)
                    )
                    if ref_sent_count >= max_connections:
                        self.log(f"Target count of {max_connections} reached via referral messages today. Skipping subsequent connection requests pipeline.")
                        break
                    
                    pending_referrals = [
                        r for r in referrals
                        if str(r.get('Referral_Status') or '').strip().lower() == 'pending'
                    ]
                    if not pending_referrals:
                        self.log("All referral outreach contacts have been processed. Stopping the pipeline with success.")
                        break
                except Exception as e:
                    self.log(f"Warning: error checking run target limits or pending referrals in runner: {e}")
            elif script == "run_recruiter_outreach.py":
                try:
                    from core.storage.database import load_all_referrals
                    referrals = load_all_referrals()
                    pending_recruiters = [
                        r for r in referrals
                        if str(r.get('Referral_Status') or '').strip().lower() == 'pending'
                        and str(r.get('Referral_Source') or '').strip().startswith('Recruiter')
                    ]
                    if not pending_recruiters:
                        self.log("All recruiter outreach contacts have been processed. Stopping the pipeline with success.")
                        break
                except Exception as e:
                    self.log(f"Warning: error checking pending recruiters in runner: {e}")
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
                    self.status = "failed"
                return
            
            self.log(f"Step {self.current_step} completed successfully.")

        if self.status != "killed":
            self.status = "success"

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

@app.route('/api/stats')
def get_stats():
    job_tracker = get_excel_data(get_job_tracker_file())
    job_leads = get_excel_data(get_job_leads_file())

    total_emails = len(job_tracker)
    emails_sent = sum(1 for r in job_tracker if str(r.get('Status')).strip().lower() == 'sent')
    
    total_leads = len(job_leads)
    
    referral_requests_sent = sum(1 for r in job_leads if str(r.get('Status')).strip().lower() in ('ask for referral', 'done'))
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

@app.route('/api/data/job_tracker')
def job_tracker_data():
    from core.storage.database import init_scraper_store
    init_scraper_store()
    return jsonify(get_excel_data(get_job_tracker_file()))

@app.route('/api/data/job_leads')
def job_leads_data():
    from core.storage.database import init_job_leads_store
    init_job_leads_store()
    return jsonify(get_excel_data(get_job_leads_file()))


@app.route('/api/run/scraper', methods=['POST'])
def start_scraper():
    with task_lock:
        task_id = "scraper_pipeline"
        if task_id in active_tasks and active_tasks[task_id].status == "running":
            return jsonify({"status": "error", "message": "Scraper pipeline is already running"}), 400
        
        body = request.get_json(silent=True) or {}
        phase = body.get("phase", "full")
        
        args = []
        if phase in ("phase1", "phase2"):
            args = ["--phase", phase]
        
        runner = SubprocessRunner(task_id, [("run_email_outreach.py", args)])
        active_tasks[task_id] = runner
        runner.start()
        
        return jsonify({"status": "success", "task_id": task_id})


@app.route('/api/run/referral', methods=['POST'])
def start_referral():
    with task_lock:
        task_id = "referral_pipeline"
        if task_id in active_tasks and active_tasks[task_id].status == "running":
            return jsonify({"status": "error", "message": "Referral pipeline is already running"}), 400
        
        body = request.get_json() or {}
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
        
        runner = SubprocessRunner(task_id, commands)
        active_tasks[task_id] = runner
        runner.start()
        
        return jsonify({"status": "success", "task_id": task_id})


@app.route('/api/run/recruiter', methods=['POST'])
def start_recruiter():
    with task_lock:
        task_id = "recruiter_pipeline"
        if task_id in active_tasks and active_tasks[task_id].status == "running":
            return jsonify({"status": "error", "message": "Recruiter outreach pipeline is already running"}), 400
        
        body = request.get_json() or {}
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
        
        runner = SubprocessRunner(task_id, commands)
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
            "keywords": [],
            "excluded_keywords": [],
            "sender_email": "",
            "interval": "60",
            "review_mode": True,
            "max_emails_per_run": "5"
        },
        "linkedin_connect": {
            "message_template": DEFAULT_CONNECTION_TEMPLATE,
            "keywords": [],
            "excluded_keywords": [],
            "interval": "60",
            "review_mode": True,
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
            "message_template": "Hi {PERSON_NAME}, I noticed we are connected and saw you work as {employee_designation} at {company}. I'm interested in the {target_role} role there. I'd love to get your guidance or a referral if possible! My resume: {resume}",
            "interval": "60",
            "max_referrals_per_run": "5",
            "review_mode": True
        }
    }
    config["selected_user"] = username
    save_all_configs(config)
    return jsonify({"status": "success", "selected_user": username})


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
        
    user_profile = body.get("profile", {})
    email_scraper = body.get("email_scraper", {})
    linkedin_connect = body.get("linkedin_connect", {})
    recruiter_outreach = body.get("recruiter_outreach", {})
    referral_outreach = body.get("referral_outreach", {})
    global_settings = body.get("global_settings", {})
    
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
        "SEARCH_KEYWORDS": "|".join(scraper.get("keywords", [])),
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
            config["users"][username]["email_scraper"]["keywords"] = [k.strip() for k in body["SEARCH_KEYWORDS"].split("|") if k.strip()]
        
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
        path = get_job_tracker_file()
        if not os.path.exists(path):
            return jsonify({"status": "error", "message": "File not found"}), 404
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        col_indices = {cell.value: idx for idx, cell in enumerate(ws[1], start=1)}
        id_col = col_indices.get('ID', 1)
        status_col = col_indices.get('Status', 3)
        timestamp_col = col_indices.get('Timestamp', 4)
        updated = False
        for row in range(2, ws.max_row + 1):
            if ws.cell(row=row, column=id_col).value == row_id:
                ws.cell(row=row, column=status_col, value=status)
                ws.cell(row=row, column=timestamp_col, value=datetime.utcnow().isoformat())
                updated = True
                break
        if updated:
            wb.save(path)
            try:
                _trigger_mac_excel_reload(path)
            except Exception:
                pass
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
        
    try:
        row_id = int(row_id)
    except ValueError:
        pass
        
    path = get_job_tracker_file() if db_type == "scraper" else get_job_leads_file()
    if not os.path.exists(path):
        return jsonify({"status": "error", "message": "File not found"}), 404
        
    try:
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        col_indices = {cell.value: idx for idx, cell in enumerate(ws[1], start=1)}
        id_col_name = 'ID' if db_type == "scraper" else 'JobID'
        id_col = col_indices.get(id_col_name)
        
        if not id_col:
            return jsonify({"status": "error", "message": "ID column not found"}), 500
            
        deleted = False
        for row in range(2, ws.max_row + 1):
            if ws.cell(row=row, column=id_col).value == row_id:
                ws.delete_rows(row)
                deleted = True
                break
                
        if deleted:
            wb.save(path)
            try:
                _trigger_mac_excel_reload(path)
            except Exception:
                pass
            return jsonify({"status": "success"})
            
        return jsonify({"status": "error", "message": "ID not found"}), 404
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
        if not email or not status:
            return jsonify({"status": "error", "message": "Missing required fields"}), 400
        success = edit_row(row_id, email, status, keyword, get_job_tracker_file())
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
    from core.storage.database import init_referrals_store, load_all_referrals
    init_referrals_store()
    return jsonify(load_all_referrals(get_job_leads_file()))


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
        
    from core.storage.database import edit_referral_contact_row
    success = edit_referral_contact_row(referral_id, {"Referral_Status": status}, get_job_leads_file())
    if success:
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
    designation = body.get("designation")
    source = body.get("source")
    status = body.get("status")
    company = body.get("company")
    notes = body.get("notes")
    
    if not name or not profile_url or not status or not company:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400
        
    update_data = {
        "CompanyName": company,
        "Referral_Person_Name": name,
        "Referral_Person_Email": email or "",
        "Referral_Person_Profile_URL": profile_url,
        "Referral_Person_Designation": designation or "",
        "Referral_Source": source or "Existing Connection",
        "Referral_Status": status,
        "Error_Reason": notes or ""
    }
    
    from core.storage.database import edit_referral_contact_row
    success = edit_referral_contact_row(referral_id, update_data, get_job_leads_file())
    if success:
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
        
    path = get_job_leads_file()
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
