import os
import json

CONFIG_FILE = "users_config.json"

DEFAULT_EMAIL_TEMPLATE = """Hi,

I came across your post regarding an opportunity.

My name is {FIRST_NAME}, and I have {EXPERIENCE} of experience.

I have attached my resume for your review. If my profile is a good fit for the role, I would be grateful if you could consider referring me or sharing it with the appropriate hiring team.

Email: {EMAIL}
Mobile: {PHONE_NUMBER}
Current Location: {CURRENT_LOCATION}
Preferred Locations: {PREFERRED_LOCATIONS}
LinkedIn: {LINKEDIN_PROFILE_URL}

Thank you for your time and support.

Regards,
{FIRST_NAME}"""

DEFAULT_CONNECTION_TEMPLATE = "Hi, I am {FIRST_NAME}. I am applying for the position at {company}. Would you kindly refer me?\\nJob: {job_url}\\nResume: {resume}\\nThank you for your support."

def substitute_template_variables(template_str, profile_dict, extra_vars=None):
    if not template_str:
        return ""
    
    # Map profile dict fields to template placeholder names
    mappings = {
        "{FIRST_NAME}": profile_dict.get("first_name", ""),
        "{LAST_NAME}": profile_dict.get("last_name", ""),
        "{EMAIL}": profile_dict.get("email", ""),
        "{PHONE_NUMBER}": profile_dict.get("phone", ""),
        "{EXPERIENCE}": profile_dict.get("experience", ""),
        "{LINKEDIN_PROFILE_URL}": profile_dict.get("linkedin_url", ""),
        "{CURRENT_LOCATION}": profile_dict.get("current_location", ""),
        "{PREFERRED_LOCATIONS}": profile_dict.get("preferred_locations", ""),
        "{CURRENT_CTC}": profile_dict.get("current_ctc", ""),
        "{EXPECTED_CTC}": profile_dict.get("expected_ctc", "")
    }
    
    result = template_str
    for placeholder, val in mappings.items():
        result = result.replace(placeholder, str(val))
        
    if extra_vars:
        for placeholder, val in extra_vars.items():
            result = result.replace(placeholder, str(val))
            
    return result

def get_resume_file_path(profile):
    local_resume_name = profile.get("resume_name", "")
    if local_resume_name:
        return os.path.join(os.getcwd(), "resumes", local_resume_name)
    else:
        return os.getenv(
            "RESUME_FILE_PATH",
            os.path.abspath(os.path.join(os.getcwd(), "Resume_YuvashreeJ_SQLDBA.pdf"))
        )

def load_all_configs():
    if not os.path.exists(CONFIG_FILE):
        default_config = {
            "users": {
                "Yuvashree": {
                    "profile": {
                        "first_name": "Yuvashree",
                        "last_name": "J",
                        "email": "yuvashreej199@gmail.com",
                        "phone": "8971799691",
                        "resume_name": "Resume_YuvashreeJ_SQLDBA.pdf",
                        "resume_url": "https://shorturl.at/F3SGD",
                        "current_location": "Bangalore, Karnataka, India",
                        "preferred_locations": "Bangalore, Karnataka, India",
                        "experience": "7+ years",
                        "linkedin_url": "https://www.linkedin.com/in/yuvashree-j",
                        "current_ctc": "15 LPA",
                        "expected_ctc": "22 LPA"
                    },
                    "email_scraper": {
                        "email_template": "Hi,\\n\\nI came across your post regarding a DBA opportunity.\\n\\nMy sister, {FIRST_NAME}, has {EXPERIENCE} of experience in Database Administration and is currently working as a Senior Software Engineer (DBA) at In Time Tec. Her expertise includes database migrations and upgrades, performance tuning, backup and recovery, Always On Availability Groups, HA/DR solutions, Azure cloud migrations, SQL Server security, and automation using PowerShell and DBATools.\\n\\nShe has worked on enterprise environments for organizations such as Simplot, Shell, and Diageo and has extensive experience managing production-critical database systems.\\n\\nI have attached her resume for your review. If her profile is a good fit for the role, I would be grateful if you could consider referring her or sharing it with the appropriate hiring team.\\n\\nEmail: {EMAIL}\\nMobile: {PHONE_NUMBER}\\nLocation : {CURRENT_LOCATION}\\nPreferred Locations: {PREFERRED_LOCATIONS}\\nLinkedIn: {LINKEDIN_PROFILE_URL}\\n\\nThank you for your time and support.\\n\\nRegards,\\nLalit Kumar Dhanjani",
                        "keywords": [
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
                        ],
                        "sender_email": "lk356003@gmail.com",
                        "interval": "60",
                        "review_mode": False
                    },
                    "linkedin_connect": {
                        "message_template": "Hi, my sister {FIRST_NAME} is applying for the DBA position at {company}. Would you kindly refer her?\\nJob: {job_url}\\nResume: {resume}\\nThank you for your support.",
                        "keywords": [
                            "SQL DBA",
                            "SQL Server DBA",
                            "Database Administrator"
                        ],
                        "interval": "60",
                        "review_mode": False
                    }
                },
                "Lalit": {
                    "profile": {
                        "first_name": "Lalit Kumar",
                        "last_name": "Dhanjani",
                        "email": "lk356003@gmail.com",
                        "phone": "9876543210",
                        "resume_name": "",
                        "resume_url": "",
                        "current_location": "Bangalore, India",
                        "preferred_locations": "Bangalore, India",
                        "experience": "5 years",
                        "linkedin_url": "https://www.linkedin.com/in/lalit-kumar-dhanjani",
                        "current_ctc": "",
                        "expected_ctc": ""
                    },
                    "email_scraper": {
                        "email_template": DEFAULT_EMAIL_TEMPLATE,
                        "keywords": [
                            "Python Developer",
                            "Full Stack Developer",
                            "Backend Engineer"
                        ],
                        "sender_email": "lk356003@gmail.com",
                        "interval": "60",
                        "review_mode": True
                    },
                    "linkedin_connect": {
                        "message_template": "Hi, I am {FIRST_NAME}. I am applying for the Developer position. Would you kindly connect and refer me?",
                        "keywords": [
                            "Recruiter",
                            "Hiring Manager"
                        ],
                        "interval": "60",
                        "review_mode": True
                    }
                }
            },
            "selected_user": "Yuvashree",
            "global_settings": {
                "linkedin_email": os.getenv("LINKEDIN_EMAIL", ""),
                "linkedin_password": os.getenv("LINKEDIN_PASSWORD", ""),
                "search_location": "Bangalore, Karnataka, India",
                "search_time_range": "r604800",
                "dry_run": "0",
                "max_run_duration_seconds": "600",
                "max_apply": "5",
                "smtp_server": os.getenv("SMTP_SERVER", "smtp.gmail.com"),
                "smtp_port": os.getenv("SMTP_PORT", "587"),
                "smtp_email": os.getenv("SMTP_EMAIL", "lk356003@gmail.com"),
                "smtp_password": os.getenv("SMTP_PASSWORD", "")
            }
        }
        save_all_configs(default_config)
        return default_config
        
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_all_configs(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

def get_selected_user_name():
    config = load_all_configs()
    return config.get("selected_user", "Yuvashree")

def get_selected_user_config():
    config = load_all_configs()
    user = get_selected_user_name()
    return config.get("users", {}).get(user, {})

def get_global_settings():
    config = load_all_configs()
    # If global_settings key is missing (for legacy user_config), return defaults
    return config.get("global_settings", {
        "linkedin_email": os.getenv("LINKEDIN_EMAIL", ""),
        "linkedin_password": os.getenv("LINKEDIN_PASSWORD", ""),
        "search_location": "Bangalore, Karnataka, India",
        "search_time_range": "r604800",
        "dry_run": "0",
        "max_run_duration_seconds": "600",
        "max_apply": "5",
        "smtp_server": os.getenv("SMTP_SERVER", "smtp.gmail.com"),
        "smtp_port": os.getenv("SMTP_PORT", "587"),
        "smtp_email": os.getenv("SMTP_EMAIL", "lk356003@gmail.com"),
        "smtp_password": os.getenv("SMTP_PASSWORD", "")
    })
