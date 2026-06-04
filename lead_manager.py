import os
import pandas as pd
from datetime import datetime
from config import CONTACTED_EMAILS_FILE, DBA_JOB_LEADS_FILE
from logger import logger

def ensure_file_exists(file_path, columns):
    if not os.path.exists(file_path):
        df = pd.DataFrame(columns=columns)
        df.to_excel(file_path, index=False)
        logger.info(f"Created new file: {file_path}")

def load_contacted_emails():
    ensure_file_exists(CONTACTED_EMAILS_FILE, [
        "Email", "Name", "Company", "Post URL", "Date Added", "Email Sent", "Sent Date"
    ])
    try:
        df = pd.read_excel(CONTACTED_EMAILS_FILE)
        return set(df["Email"].dropna().str.lower().tolist())
    except Exception as e:
        logger.error(f"Error loading contacted emails: {e}")
        return set()

def add_contacted_email(email, name, company, post_url, email_sent=False):
    ensure_file_exists(CONTACTED_EMAILS_FILE, [
        "Email", "Name", "Company", "Post URL", "Date Added", "Email Sent", "Sent Date"
    ])
    try:
        df = pd.read_excel(CONTACTED_EMAILS_FILE)
        new_row = pd.DataFrame([{
            "Email": email.lower(),
            "Name": name,
            "Company": company,
            "Post URL": post_url,
            "Date Added": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Email Sent": "Yes" if email_sent else "No",
            "Sent Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S") if email_sent else ""
        }])
        df = pd.concat([df, new_row], ignore_index=True)
        df.to_excel(CONTACTED_EMAILS_FILE, index=False)
        logger.info(f"Added {email} to contacted emails.")
    except Exception as e:
        logger.error(f"Error adding to contacted emails: {e}")

def add_job_lead(poster_name, email, post_url, profile_url, post_date, keyword_matched, post_content):
    ensure_file_exists(DBA_JOB_LEADS_FILE, [
        "Poster Name", "Email", "Post URL", "Profile URL", "Post Date", "Job Keyword Matched", "Post Content"
    ])
    try:
        df = pd.read_excel(DBA_JOB_LEADS_FILE)
        
        # Avoid exact duplicates by Post URL and Email
        if not df[(df["Post URL"] == post_url) & (df["Email"] == email.lower())].empty:
            logger.info(f"Lead for {email} on post {post_url} already exists. Skipping.")
            return False
            
        new_row = pd.DataFrame([{
            "Poster Name": poster_name,
            "Email": email.lower(),
            "Post URL": post_url,
            "Profile URL": profile_url,
            "Post Date": post_date,
            "Job Keyword Matched": keyword_matched,
            "Post Content": post_content
        }])
        df = pd.concat([df, new_row], ignore_index=True)
        df.to_excel(DBA_JOB_LEADS_FILE, index=False)
        logger.info(f"Added job lead for {poster_name} ({email}).")
        return True
    except Exception as e:
        logger.error(f"Error adding job lead: {e}")
        return False