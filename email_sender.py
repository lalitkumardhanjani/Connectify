import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from logger import logger

def generate_email_draft():
    """Generate email subject and body dynamically using the active user configuration and templates."""
    try:
        from user_config_manager import get_selected_user_config, substitute_template_variables
        user_conf = get_selected_user_config()
    except Exception:
        user_conf = {}
        
    profile = user_conf.get("profile", {})
    email_scraper = user_conf.get("email_scraper", {})
    
    # Retrieve template from config
    raw_template = email_scraper.get("email_template")
    if not raw_template:
        from user_config_manager import DEFAULT_EMAIL_TEMPLATE
        raw_template = DEFAULT_EMAIL_TEMPLATE
        
    # Substitute variables
    body = substitute_template_variables(raw_template, profile)
    subject = "Referral Request – DBA Opportunity"
    
    return subject, body

def send_email(to_email, name, post_url):
    subject, body = generate_email_draft()
    
    try:
        from user_config_manager import get_selected_user_config, get_global_settings
        user_conf = get_selected_user_config()
        global_conf = get_global_settings()
    except Exception:
        user_conf = {}
        global_conf = {}
        
    email_scraper = user_conf.get("email_scraper", {})
    review_mode = email_scraper.get("review_mode", True)
    
    smtp_email = global_conf.get("smtp_email") or os.getenv("SMTP_EMAIL", "lk356003@gmail.com")
    smtp_password = global_conf.get("smtp_password") or os.getenv("SMTP_PASSWORD")
    smtp_server = global_conf.get("smtp_server") or os.getenv("SMTP_SERVER", "smtp.gmail.com")
    try:
        smtp_port = int(global_conf.get("smtp_port") or os.getenv("SMTP_PORT", 587))
    except ValueError:
        smtp_port = 587
    
    if review_mode:
        print("\n" + "="*50)
        print("REVIEW MODE - NEW EMAIL")
        print("="*50)
        print(f"To: {to_email} ({name})")
        print(f"Post Source: {post_url}")
        print("-" * 50)
        print(f"Subject: {subject}")
        print(body)
        print("="*50)
        
        choice = input("Send this email? (Y/N): ").strip().lower()
        if choice != 'y':
            logger.info(f"User skipped sending email to {to_email}.")
            return False

    if not smtp_email or not smtp_password:
        logger.error("SMTP credentials not configured. Cannot send email.")
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_email, smtp_password)
        server.send_message(msg)
        server.quit()
        
        logger.info(f"Successfully sent email to {to_email}.")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False