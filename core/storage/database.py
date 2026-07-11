import os
from datetime import datetime
from config.constants import SCRAPER_HEADERS, JOB_LEADS_HEADERS, REFERRAL_HEADERS
from core.logging.config import logger
from core.utils.url_utils import is_valid_external_url, normalize_external_url
from core.storage.engine import read_database_rows, write_database_rows, append_database_row

import threading
import time

_last_sync_time = 0
_sync_lock = threading.Lock()
SYNC_INTERVAL_SECONDS = 180  # Throttle status syncs to at most once per 3 minutes

# Cache set for fast duplicate checks of external apply URLs
seen_external_urls = set()

def get_sheets_config():
    """Helper to retrieve active Google Sheets configuration if enabled."""
    try:
        from core.storage.engine import GoogleSheetsStorageProvider, get_active_username, get_user_config
        username = get_active_username()
        config = get_user_config(username)
        db_type = config.get("global_settings", {}).get("database_type", "local")
        if db_type == "google_sheets":
            provider = GoogleSheetsStorageProvider()
            return provider.get_sheets_config(username)
    except Exception as e:
        logger.warning(f"Error checking sheets configuration: {e}")
    return None

def migrate_old_data_files():
    """Checks and handles any legacy migration details on-demand."""
    pass

def migrate_referrals_data():
    """Migrates existing referrals worksheet data to correct user data folder structure."""
    pass

def init_scraper_store(path=None):
    """Initializes the scraper database by reading it, which triggers template creation if missing."""
    read_database_rows("emails")

def trim_scraper_excel_to_schema(path=None):
    pass

def append_email(email, keyword='', post_url='', company_name='', experience='', location='', path=None):
    """Appends extracted email to the job tracker if it's unique."""
    try:
        rows = read_database_rows("emails")
        normalized_email = str(email or '').strip().lower()
        normalized_post_url = str(post_url or '').strip().lower()
        for r in rows:
            if str(r.get('Email')).strip().lower() == normalized_email and str(r.get('PostURL')).strip().lower() == normalized_post_url:
                return False
        max_id = max([int(float(r.get('ID') or 0)) for r in rows]) if rows else 0
    except Exception:
        max_id = 0
        
    data = {
        'ID': max_id + 1,
        'Email': email,
        'Status': 'New',
        'Timestamp': datetime.utcnow().isoformat(),
        'Generated_Time': datetime.utcnow().isoformat(),
        'Keyword': keyword,
        'PostURL': post_url,
        'CompanyName': company_name,
        'Experience': experience,
        'Location': location
    }
    append_database_row("emails", data)
    return True

def update_status(email, status, path=None):
    """Updates status for a specific scraped email row."""
    rows = read_database_rows("emails")
    normalized_email = str(email or '').strip().lower()
    updated = False
    for r in rows:
        if str(r.get('Email')).strip().lower() == normalized_email:
            r['Status'] = status
            r['Timestamp'] = datetime.utcnow().isoformat()
            if status.lower() == 'sent':
                r['Sent_Time'] = datetime.utcnow().isoformat()
            updated = True
            break
    if updated:
        write_database_rows("emails", rows)
    return updated

def count_unique_emails(path=None):
    """Counts unique emails processed in the scraper sheet."""
    rows = read_database_rows("emails")
    emails = {str(r.get('Email')).strip().lower() for r in rows if r.get('Email')}
    return len(emails)

def edit_row(row_id, email, status, keyword, post_url=None, company_name=None, experience=None, location=None, path=None):
    """Edits all fields of a scraper row."""
    rows = read_database_rows("emails")
    updated = False
    try:
        target_id = int(float(row_id))
    except (ValueError, TypeError):
        return False

    for r in rows:
        try:
            curr_id = int(float(r.get('ID') or 0))
        except (ValueError, TypeError):
            continue
        if curr_id == target_id:
            r['Email'] = email
            r['Status'] = status
            r['Keyword'] = keyword
            r['Timestamp'] = datetime.utcnow().isoformat()
            if post_url is not None: r['PostURL'] = post_url
            if company_name is not None: r['CompanyName'] = company_name
            if experience is not None: r['Experience'] = experience
            if location is not None: r['Location'] = location
            updated = True
            break
    if updated:
        write_database_rows("emails", rows)
    return updated

def migrate_pending_to_new(path=None):
    """Changes any legacy 'Pending' status values to 'New' to match standard pipeline conventions."""
    rows = read_database_rows("emails")
    updated = False
    for r in rows:
        if str(r.get('Status')).strip().lower() == 'pending':
            r['Status'] = 'New'
            updated = True
    if updated:
        write_database_rows("emails", rows)

def init_job_leads_store(path=None):
    read_database_rows("jobs")

def trim_job_leads_excel_to_schema(path=None):
    pass

def load_saved_jobs(path=None):
    """Loads all saved job leads."""
    return read_database_rows("jobs")

def save_job(data, path=None):
    """Saves a new job to the job leads database if its URL is unique and valid."""
    comp_name = str(data.get('CompanyName') or '').strip()
    job_title = str(data.get('JobTitle') or '').strip()
    apply_url = normalize_external_url(data.get('CompanyURL') or '')
    linkedin_company_url = normalize_external_url(data.get('LinkedIn_Company_URL') or '')
    
    if not comp_name or not job_title or not apply_url:
        logger.warning(f"Skipping save_job: Missing critical fields (CompanyName: '{comp_name}', JobTitle: '{job_title}', CompanyURL: '{apply_url}')")
        return False
        
    cache_key = (linkedin_company_url, apply_url)
    if cache_key in seen_external_urls:
        logger.info(f"Skipping duplicate job saving: (Company URL: {linkedin_company_url}, Apply URL: {apply_url}) already matched in cache.")
        return False
        
    rows = read_database_rows("jobs", bypass_cache=True)
    for r in rows:
        r_url = normalize_external_url(r.get('CompanyURL') or '')
        r_comp_url = normalize_external_url(r.get('LinkedIn_Company_URL') or '')
        
        # Check by company URL + apply URL combination
        if r_comp_url == linkedin_company_url and r_url == apply_url:
            seen_external_urls.add(cache_key)
            logger.info(f"Skipping duplicate job saving: (Company URL: {linkedin_company_url}, Apply URL: {apply_url}) already matched in database.")
            return False

    max_id = 0
    if rows:
        for r in rows:
            try:
                val = int(float(r.get('JobID') or 0))
                if val > max_id:
                    max_id = val
            except (ValueError, TypeError):
                pass
    new_job = {
        'JobID': int(max_id + 1),
        'JobTitle': data.get('JobTitle', ''),
        'CompanyName': data.get('CompanyName', ''),
        'LinkedIn_Company_URL': data.get('LinkedIn_Company_URL', ''),
        'CompanyURL': data.get('CompanyURL', ''),
        'ShortenURL': data.get('ShortenURL', ''),
        'SearchKeyword': data.get('SearchKeyword', ''),
        'Status': data.get('Status', 'NEW'),
        'ShortUrlCreated': data.get('ShortUrlCreated') if data.get('ShortUrlCreated') is not None else 0,
        'CreatedDateTime': data.get('CreatedDateTime') or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    append_database_row("jobs", new_job)
    seen_external_urls.add(cache_key)
    return True

def load_jobs_for_referral(path=None, status_filter='Asked for Referral'):
    """Loads all job leads matching the target status filter."""
    rows = read_database_rows("jobs")
    return [r for r in rows if str(r.get('Status')).strip().lower() == status_filter.lower()]

def update_status_by_id(job_id, status, path=None):
    """Updates the status of a specific job lead by ID."""
    rows = read_database_rows("jobs", bypass_cache=True)
    updated = False
    try:
        target_id = int(float(job_id))
    except (ValueError, TypeError):
        return False

    for r in rows:
        try:
            curr_id = int(float(r.get('JobID') or 0))
        except (ValueError, TypeError):
            continue
        if curr_id == target_id:
            r['Status'] = status
            updated = True
            break
    if updated:
        write_database_rows("jobs", rows)
    return updated

def edit_lead_row(job_id, company, url, shorten, keyword, position, status, path=None):
    """Edits all columns in a job lead row."""
    rows = read_database_rows("jobs", bypass_cache=True)
    updated = False
    try:
        target_id = int(float(job_id))
    except (ValueError, TypeError):
        return False

    for r in rows:
        try:
            curr_id = int(float(r.get('JobID') or 0))
        except (ValueError, TypeError):
            continue
        if curr_id == target_id:
            r['CompanyName'] = company
            r['LinkedIn_Company_URL'] = url
            r['ShortenURL'] = shorten
            r['SearchKeyword'] = keyword
            r['JobTitle'] = position
            r['Status'] = status
            updated = True
            break
    if updated:
        write_database_rows("jobs", rows)
    return updated

def init_referrals_store(path=None):
    read_database_rows("referrals")

def trim_referrals_excel_to_schema(path=None):
    pass

def load_all_referrals(path=None, bypass_cache: bool = False):
    return read_database_rows("referrals", bypass_cache=bypass_cache)

def add_or_update_referral(referral_data, path=None):
    """Inserts a new referral outreach row or updates an existing one if matching."""
    rows = read_database_rows("referrals", bypass_cache=True)
    target_profile = str(referral_data.get('Referral_Person_Profile_URL') or '').strip().lower()
    target_job_url = str(referral_data.get('Company_URL') or '').strip().lower()
    target_job_id = str(referral_data.get('JobID') or '').strip()
    
    updated = False
    for r in rows:
        curr_profile = str(r.get('Referral_Person_Profile_URL') or '').strip().lower()
        curr_job_url = str(r.get('Company_URL') or '').strip().lower()
        curr_job_id = str(r.get('JobID') or '').strip()
        
        if curr_profile == target_profile and (curr_job_url == target_job_url or (target_job_id and curr_job_id == target_job_id)):
            for k, v in referral_data.items():
                if k != 'ReferralID':
                    r[k] = v
            updated = True
            break
            
    if not updated:
        max_id = 0
        if rows:
            for r in rows:
                try:
                    val = int(float(r.get('ReferralID') or 0))
                    if val > max_id:
                        max_id = val
                except (ValueError, TypeError):
                    pass
        new_ref = {
            'ReferralID': max_id + 1,
            'JobID': referral_data.get('JobID', ''),
            'JobTitle': referral_data.get('JobTitle', ''),
            'CompanyName': referral_data.get('CompanyName', ''),
            'Company_URL': referral_data.get('Company_URL', ''),
            'Referral_Person_Name': referral_data.get('Referral_Person_Name', ''),
            'Referral_Person_Profile_URL': referral_data.get('Referral_Person_Profile_URL', ''),
            'Referral_Source': referral_data.get('Referral_Source', ''),
            'Referral_Status': referral_data.get('Referral_Status', 'NEW'),
            'Sent_Time': referral_data.get('Sent_Time') or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        rows.append(new_ref)
        
    write_database_rows("referrals", rows)
    return True

def is_profile_already_contacted(profile_url, job_url=None, path=None):
    rows = read_database_rows("referrals")
    target_profile = str(profile_url).strip().lower()
    target_job_url = str(job_url or '').strip().lower()
    for r in rows:
        curr_profile = str(r.get('Referral_Person_Profile_URL') or '').strip().lower()
        curr_job_url = str(r.get('Company_URL') or '').strip().lower()
        if curr_profile == target_profile:
            if not target_job_url or curr_job_url == target_job_url:
                return True
    return False

def edit_referral_contact_row(referral_id, referral_data, path=None):
    """Edits all columns of a referral connection record."""
    rows = read_database_rows("referrals", bypass_cache=True)
    updated = False
    try:
        target_id = int(float(referral_id))
    except (ValueError, TypeError):
        return False

    for r in rows:
        try:
            curr_id = int(float(r.get('ReferralID') or 0))
        except (ValueError, TypeError):
            continue
        if curr_id == target_id:
            for k, v in referral_data.items():
                if k != 'ReferralID':
                    r[k] = v
            updated = True
            break
    if updated:
        write_database_rows("referrals", rows)
    return updated

def get_company_sent_count(company_name, path=None):
    rows = read_database_rows("referrals")
    c_name = str(company_name or '').strip().lower()
    return sum(
        1 for r in rows 
        if str(r.get('CompanyName')).strip().lower() == c_name 
        and str(r.get('Referral_Status')).strip().lower() in ('sent', 'replied', 'referral received')
    )

def get_company_referrals_count(company_name, path=None):
    rows = read_database_rows("referrals")
    c_name = str(company_name or '').strip().lower()
    return sum(1 for r in rows if str(r.get('CompanyName')).strip().lower() == c_name)

def get_employee_outreach_progress(company_name, path=None):
    rows = read_database_rows("referrals")
    c_name = str(company_name or '').strip().lower()
    sent_count = 0
    replied_count = 0
    
    for r in rows:
        if str(r.get('CompanyName')).strip().lower() == c_name:
            source = str(r.get('Referral_Source') or '').strip().lower()
            status = str(r.get('Referral_Status') or '').strip().lower()
            is_employee = source in ('existing employee', 'sent employee connection')
            if is_employee:
                if status in ('sent', 'replied', 'referral received'):
                    sent_count += 1
                if status in ('replied', 'referral received'):
                    replied_count += 1
                    
    return {"sent": sent_count, "replied": replied_count}

def get_recruiter_outreach_progress(company_name, path=None):
    rows = read_database_rows("referrals")
    c_name = str(company_name or '').strip().lower()
    sent_count = 0
    replied_count = 0
    
    for r in rows:
        if str(r.get('CompanyName')).strip().lower() == c_name:
            source = str(r.get('Referral_Source') or '').strip().lower()
            status = str(r.get('Referral_Status') or '').strip().lower()
            is_recruiter = source in ('existing recruiter', 'sent recruiter connection')
            if is_recruiter:
                if status in ('sent', 'replied', 'referral received'):
                    sent_count += 1
                if status in ('replied', 'referral received'):
                    replied_count += 1
                    
    return {"sent": sent_count, "replied": replied_count}

def clean_company_url(url):
    if not url:
        return ""
    url = str(url).strip()
    if "/company/" in url:
        parts = url.split("/company/")
        slug = parts[1].split("/")[0].split("?")[0]
        return f"https://www.linkedin.com/company/{slug}/"
    return url

def get_completed_referral_count(company_name, job_url=None, job_id=None, path=None):
    rows = read_database_rows("referrals")
    c_name = str(company_name or '').strip().lower()
    job_id_str = str(job_id or '').strip()
    
    count = 0
    for r in rows:
        curr_company = str(r.get('CompanyName')).strip().lower()
        curr_job_id = str(r.get('JobID') or '').strip()
        status = str(r.get('Referral_Status') or '').strip().lower()
        source = str(r.get('Referral_Source') or '').strip().lower()
        is_employee = source in ('existing employee', 'sent employee connection')
        
        if curr_company == c_name and curr_job_id == job_id_str:
            if is_employee and status in ('sent', 'replied', 'referral received'):
                count += 1
    return count

def sync_job_lead_referral_statuses(path=None):
    """Automatically updates job tracker status to 'Referral Outreach Completed' if targets are met."""
    global _last_sync_time
    current_time = time.time()
    with _sync_lock:
        if current_time - _last_sync_time < SYNC_INTERVAL_SECONDS:
            logger.info("Skipping sync_job_lead_referral_statuses: throttled (ran less than 3 minutes ago).")
            return
        _last_sync_time = current_time

    try:
        from config.user_profiles import get_selected_user_config
        user_conf = get_selected_user_config()
        connect_conf = user_conf.get("linkedin_connect", {})
        target = int(connect_conf.get("max_connections_per_company") or connect_conf.get("max_connections_per_run") or 5)
        
        referrals = load_all_referrals(bypass_cache=True)
        company_data = {}
        for ref in referrals:
            c_name = str(ref.get("CompanyName") or "").strip().lower()
            c_url = clean_company_url(ref.get("Company_URL") or "")
            job_id_val = str(ref.get("JobID") or "").strip()
            ref_source = str(ref.get("Referral_Source") or "").strip().lower()
            ref_status = str(ref.get("Referral_Status") or "").strip().lower()
            is_employee = ref_source in ("existing employee", "sent employee connection")
            is_valid_status = ref_status in ("sent", "replied", "referral received")
            
            key = (c_name, c_url, job_id_val)
            if key not in company_data:
                company_data[key] = 0
            if is_employee and is_valid_status:
                company_data[key] += 1

        rows = read_database_rows("jobs", bypass_cache=True)
        updated = False
        for r in rows:
            company_name = str(r.get("CompanyName") or "").strip()
            c_name_lower = company_name.lower()
            row_job_id = str(r.get("JobID") or "").strip()
            
            company_url = clean_company_url(r.get("LinkedIn_Company_URL") or "")
            if not company_url:
                for (cn, cu, jid) in company_data.keys():
                    if cn == c_name_lower and cu:
                        company_url = cu
                        break
            if not company_url:
                slug = company_name.lower().replace(" ", "-").replace(".", "").replace(",", "")
                company_url = f"https://www.linkedin.com/company/{slug}/"
                
            completed_count = 0
            for (cn, cu, jid), count in company_data.items():
                if cn == c_name_lower and jid == row_job_id:
                    if not company_url or not cu or company_url == cu:
                        completed_count += count
                        
            if completed_count >= target:
                current_status = str(r.get("Status") or "").strip()
                if current_status != 'Referral Outreach Completed' and current_status.lower() != 'done':
                    r['Status'] = 'Referral Outreach Completed'
                    updated = True
                    
            current_linkedin_url = r.get("LinkedIn_Company_URL")
            if not current_linkedin_url:
                r["LinkedIn_Company_URL"] = company_url
                updated = True
                
        if updated:
            write_database_rows("jobs", rows)
    except Exception as e:
        logger.error(f"Error syncing job tracker referral statuses: {e}")

def load_job_leads_with_referral_counts():
    """Loads all job leads enriched with dynamic referral progress metrics."""
    try:
        from config.user_profiles import get_selected_user_config
        user_conf = get_selected_user_config()
    except Exception:
        user_conf = {}
    connect_conf = user_conf.get("linkedin_connect", {})
    target = int(connect_conf.get("max_connections_per_company") or connect_conf.get("max_connections_per_run") or 5)

    try:
        # Run sync first to update status of completed referrals
        sync_job_lead_referral_statuses()
        leads = read_database_rows("jobs", bypass_cache=True)
        referrals = read_database_rows("referrals", bypass_cache=True)
    except Exception as e:
        logger.error(f"Error reading job leads or referrals: {e}")
        return []

    company_data = {}
    for ref in referrals:
        c_name = str(ref.get("CompanyName") or "").strip().lower()
        c_url = clean_company_url(ref.get("Company_URL") or "")
        job_id_val = str(ref.get("JobID") or "").strip()
        ref_source = str(ref.get("Referral_Source") or "").strip().lower()
        ref_status = str(ref.get("Referral_Status") or "").strip().lower()

        is_employee = ref_source in ("existing employee", "sent employee connection")
        is_valid_status = ref_status in ("sent", "replied", "referral received")

        key = (c_name, c_url, job_id_val)
        if key not in company_data:
            company_data[key] = {
                "completed": 0,
                "urls": set()
            }
        
        if c_url:
            company_data[key]["urls"].add(c_url)
        if is_employee and is_valid_status:
            company_data[key]["completed"] += 1

    for lead in leads:
        company_name = str(lead.get("CompanyName") or "").strip()
        c_name_lower = company_name.lower()
        lead_job_id = str(lead.get("JobID") or "").strip()
        lead_status = str(lead.get("Status") or "").strip().lower()
        
        # If the job is marked as Not Interested, show zero for all referral metrics
        if lead_status == "not interested":
            lead["LinkedIn_Company_URL"] = clean_company_url(lead.get("LinkedIn_Company_URL") or "")
            lead["Referral_Target"] = 0
            lead["Referral_Completed"] = 0
            lead["Referral_Remaining"] = 0
            lead["Referral_Target_Achieved"] = "N/A"
            continue
        
        company_url = clean_company_url(lead.get("LinkedIn_Company_URL") or "")
        if not company_url:
            for (cn, cu, jid) in company_data.keys():
                if cn == c_name_lower and cu:
                    company_url = cu
                    break
        if not company_url:
            slug = company_name.lower().replace(" ", "-").replace(".", "").replace(",", "")
            company_url = f"https://www.linkedin.com/company/{slug}/"

        completed_count = 0
        for (cn, cu, jid), data in company_data.items():
            if cn == c_name_lower and jid == lead_job_id:
                if not company_url or not cu or company_url == cu:
                    completed_count += data["completed"]

        remaining = max(0, target - completed_count)
        lead["LinkedIn_Company_URL"] = company_url
        lead["Referral_Target"] = target
        lead["Referral_Completed"] = completed_count
        lead["Referral_Remaining"] = remaining
        lead["Referral_Target_Achieved"] = "Yes" if completed_count >= target else "No"

    return leads

def migrate_company_url_and_tracking_fields():
    pass

def deduplicate_all_tables(username):
    """Scans and removes duplicates from all database tables for the given user in both Local DB and Google Sheets."""
    try:
        from core.storage.engine import read_database_rows, write_database_rows
        
        # 1. Deduplicate 'emails' (Email + PostURL)
        email_rows = read_database_rows("emails", username=username, bypass_cache=True)
        unique_emails = []
        seen_emails = set()
        for r in email_rows:
            email_val = str(r.get('Email') or '').strip().lower()
            post_url_val = str(r.get('PostURL') or '').strip().lower()
            key = (email_val, post_url_val)
            if key not in seen_emails:
                seen_emails.add(key)
                unique_emails.append(r)
        if len(unique_emails) < len(email_rows):
            logger.info(f"Removing {len(email_rows) - len(unique_emails)} duplicate outreach records for user {username}.")
            write_database_rows("emails", unique_emails, username=username)

        # 2. Deduplicate 'jobs' (LinkedIn_Company_URL + CompanyURL)
        job_rows = read_database_rows("jobs", username=username, bypass_cache=True)
        unique_jobs = []
        seen_jobs = set()
        for r in job_rows:
            comp_url_val = str(r.get('LinkedIn_Company_URL') or '').strip().lower()
            job_url_val = str(r.get('CompanyURL') or '').strip().lower()
            key = (comp_url_val, job_url_val)
            if key not in seen_jobs:
                seen_jobs.add(key)
                unique_jobs.append(r)
        if len(unique_jobs) < len(job_rows):
            logger.info(f"Removing {len(job_rows) - len(unique_jobs)} duplicate job opportunities for user {username}.")
            write_database_rows("jobs", unique_jobs, username=username)

        # 3. Deduplicate 'referrals' (Company_URL + Referral_Person_Profile_URL)
        referral_rows = read_database_rows("referrals", username=username, bypass_cache=True)
        unique_referrals = []
        seen_referrals = set()
        for r in referral_rows:
            job_url_val = str(r.get('Company_URL') or '').strip().lower()
            profile_url_val = str(r.get('Referral_Person_Profile_URL') or '').strip().lower()
            key = (job_url_val, profile_url_val)
            if key not in seen_referrals:
                seen_referrals.add(key)
                unique_referrals.append(r)
        if len(unique_referrals) < len(referral_rows):
            logger.info(f"Removing {len(referral_rows) - len(unique_referrals)} duplicate referral contacts for user {username}.")
            write_database_rows("referrals", unique_referrals, username=username)

    except Exception as e:
        logger.error(f"Error deduplicating tables for user {username}: {e}")
