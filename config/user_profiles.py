import os
import json
import shutil
from config.settings import BASE_DIR
from config.email_templates import DEFAULT_EMAIL_TEMPLATE, DEFAULT_CONNECTION_TEMPLATE

def get_active_user_file():
    return os.path.join(BASE_DIR, "users", "active_user.json")

def get_user_config_file(username):
    return os.path.join(BASE_DIR, "users", username, "config.json")

def migrate_old_monolithic_config():
    """Migrates old monolithic users_config.json and global directories to the users/ directory structure."""
    old_config_file = os.path.join(BASE_DIR, "users_config.json")
    users_dir = os.path.join(BASE_DIR, "users")
    
    # If the users folder already contains any subdirectories with config.json, don't re-migrate
    if os.path.exists(users_dir):
        subdirs = [d for d in os.listdir(users_dir) if os.path.isdir(os.path.join(users_dir, d)) and d != "default"]
        if subdirs:
            return
            
    if os.path.exists(old_config_file):
        try:
            with open(old_config_file, "r") as f:
                old_config = json.load(f)
                
            # Perform migration for each user in the old config
            save_all_configs(old_config)
            
            # Now let's migrate their Excel databases from data/ to users/<username>/data/
            # For simplicity, if there was a selected user, migrate the root data, logs, resumes, and chrome profiles to that user!
            selected_user = old_config.get("selected_user")
            if selected_user:
                user_data_dir = os.path.join(users_dir, selected_user, "data")
                user_logs_dir = os.path.join(users_dir, selected_user, "logs")
                user_resumes_dir = os.path.join(users_dir, selected_user, "resumes")
                user_chrome_dir = os.path.join(users_dir, selected_user, "chrome-profile")
                
                os.makedirs(user_data_dir, exist_ok=True)
                os.makedirs(user_logs_dir, exist_ok=True)
                os.makedirs(user_resumes_dir, exist_ok=True)
                os.makedirs(user_chrome_dir, exist_ok=True)
                
                # Move Excel database files
                root_data_dir = os.path.join(BASE_DIR, "data")
                if os.path.exists(root_data_dir):
                    for filename in os.listdir(root_data_dir):
                        src = os.path.join(root_data_dir, filename)
                        dst = os.path.join(user_data_dir, filename)
                        if os.path.isfile(src) and not os.path.exists(dst):
                            try:
                                shutil.move(src, dst)
                            except Exception:
                                pass
                            
                # Move Log files
                root_logs_dir = os.path.join(BASE_DIR, "logs")
                if os.path.exists(root_logs_dir):
                    for filename in os.listdir(root_logs_dir):
                        src = os.path.join(root_logs_dir, filename)
                        dst = os.path.join(user_logs_dir, filename)
                        if os.path.isfile(src) and not os.path.exists(dst):
                            try:
                                shutil.move(src, dst)
                            except Exception:
                                pass
                            
                # Move Resumes
                root_resumes_dir = os.path.join(BASE_DIR, "resumes")
                if os.path.exists(root_resumes_dir):
                    for filename in os.listdir(root_resumes_dir):
                        src = os.path.join(root_resumes_dir, filename)
                        dst = os.path.join(user_resumes_dir, filename)
                        if os.path.isfile(src) and not os.path.exists(dst):
                            try:
                                shutil.copy2(src, dst)
                            except Exception:
                                pass
                            
                # Move Chrome Profile (.chrome-profile)
                root_chrome_dir = os.path.join(BASE_DIR, ".chrome-profile")
                if os.path.exists(root_chrome_dir):
                    try:
                        shutil.copytree(root_chrome_dir, user_chrome_dir, dirs_exist_ok=True)
                    except Exception:
                        pass
                        
            # After migration, rename the old file to users_config.json.backup
            os.rename(old_config_file, old_config_file + ".backup")
        except Exception:
            pass

def load_all_configs(bypass_cache: bool = False):
    """
    Loads user profiles dynamically from the active storage provider
    and reconstructs the unified configuration format.
    """
    migrate_old_monolithic_config()
    
    users_dir = os.path.join(BASE_DIR, "users")
    active_user_file = get_active_user_file()
    
    selected_user = os.getenv("CONNECTIFY_USER")
    if not selected_user:
        if os.path.exists(active_user_file):
            try:
                with open(active_user_file, "r") as f:
                    selected_user = json.load(f).get("selected_user")
            except Exception:
                pass
            
    users = {}
    if os.path.exists(users_dir):
        try:
            from core.storage.engine import get_user_config
            for d in os.listdir(users_dir):
                if d == "default" or not os.path.isdir(os.path.join(users_dir, d)):
                    continue
                users[d] = get_user_config(d, bypass_cache=bypass_cache)
        except Exception as e:
            logger.error(f"Error loading configs via storage provider: {e}")
            
    # If no users exist, or selected_user not found in users list, select first available
    if users:
        if not selected_user or selected_user not in users:
            selected_user = sorted(list(users.keys()))[0]
    else:
        selected_user = ""

    # Resolve global settings for the selected user
    global_settings = {}
    if selected_user and selected_user in users:
        global_settings = users[selected_user].get("global_settings", {})
        
    # If global settings are empty, supply defaults
    if not global_settings:
        global_settings = {
            "linkedin_email": os.getenv("LINKEDIN_EMAIL", ""),
            "linkedin_password": os.getenv("LINKEDIN_PASSWORD", ""),
            "search_location": "Bangalore, Karnataka, India",
            "search_time_range": "r604800",
            "dry_run": "0",
            "max_run_duration_seconds": "600",
            "max_apply": "5",
            "smtp_server": os.getenv("SMTP_SERVER", "smtp.gmail.com"),
            "smtp_port": os.getenv("SMTP_PORT", "587"),
            "smtp_email": os.getenv("SMTP_EMAIL", ""),
            "smtp_password": os.getenv("SMTP_PASSWORD", ""),
            "database_type": "local",
            "google_sheet_url": "",
            "google_credentials_json": ""
        }

    return {
        "users": users,
        "selected_user": selected_user,
        "global_settings": global_settings
    }

def save_all_configs(config):
    """
    Saves configurations dynamically back to the active storage provider.
    """
    users_dir = os.path.join(BASE_DIR, "users")
    os.makedirs(users_dir, exist_ok=True)
    
    # 1. Update active user
    selected_user = config.get("selected_user", "")
    active_user_file = get_active_user_file()
    try:
        with open(active_user_file, "w") as f:
            json.dump({"selected_user": selected_user}, f, indent=2)
    except Exception:
        pass
        
    # 2. Save individual user configs via storage provider
    from core.storage.engine import save_user_config, get_user_config
    for username, user_data in config.get("users", {}).items():
        # Ensure user folder exists (to store bootstrap files and local excel cache)
        user_dir = os.path.join(users_dir, username)
        os.makedirs(user_dir, exist_ok=True)
        os.makedirs(os.path.join(user_dir, "data"), exist_ok=True)
        os.makedirs(os.path.join(user_dir, "logs"), exist_ok=True)
        os.makedirs(os.path.join(user_dir, "resumes"), exist_ok=True)
        os.makedirs(os.path.join(user_dir, "chrome-profile"), exist_ok=True)
        
        # If this is the selected user, we store the config's top-level global settings inside it
        if username == selected_user:
            user_data["global_settings"] = config.get("global_settings", {})
        else:
            # Otherwise, read existing global settings from provider to prevent losing them
            existing_user_data = get_user_config(username)
            user_data["global_settings"] = existing_user_data.get("global_settings", {})
            
        if "global_settings" not in user_data:
            user_data["global_settings"] = {}

        # Save via active storage provider
        save_user_config(user_data, username)

def get_selected_user_name():
    env_user = os.getenv("CONNECTIFY_USER")
    if env_user:
        return env_user
    config = load_all_configs()
    return config.get("selected_user", "")

def get_selected_user_config():
    config = load_all_configs()
    user = get_selected_user_name()
    return config.get("users", {}).get(user, {})

def get_global_settings():
    config = load_all_configs()
    return config.get("global_settings", {})

def substitute_template_variables(template_str, profile_dict, extra_vars=None):
    if not template_str:
        return ""
    
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
        "{EXPECTED_CTC}": profile_dict.get("expected_ctc", ""),
        "{NOTICE_PERIOD}": profile_dict.get("notice_period", ""),
        "{LAST_WORKING_DAY}": profile_dict.get("last_working_day", ""),
        "{RESUME}": profile_dict.get("resume_url", ""),
        "{COMPANY}": "",
        "{JOB_URL}": "",
        "{POST_URL}": "",
        "{RECEIVER_NAME}": ""
    }
    
    if extra_vars:
        mappings.update(extra_vars)
        
    result = template_str
    for placeholder, val in mappings.items():
        result = result.replace(placeholder, str(val))
            
    return result

def get_resume_file_path(profile_dict):
    from config.settings import get_resumes_dir
    local_resume_name = profile_dict.get("resume_name", "")
    if local_resume_name:
        return os.path.join(get_resumes_dir(), local_resume_name)
    
    env_path = os.getenv("RESUME_FILE_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
        
    return ""
