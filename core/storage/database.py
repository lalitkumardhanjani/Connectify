import os
from datetime import datetime
from config.constants import SCRAPER_HEADERS, JOB_LEADS_HEADERS, REFERRAL_HEADERS
from core.logging.config import logger
from core.utils.url_utils import is_valid_external_url, normalize_external_url
from core.storage.engine import read_database_rows, write_database_rows, append_database_row

# Cache set for fast duplicate checks of external apply URLs
seen_external_urls = set()

def get_sheets_config():
    """Helper to retrieve active Google Sheets configuration if enabled."""
    try:
        from core.storage.engine import get_active_storage_provider, GoogleSheetsStorageProvider
        provider = get_active_storage_provider()
        if isinstance(provider, GoogleSheetsStorageProvider):
            from core.storage.engine import get_active_username
            username = get_active_username()
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
        for r in rows:
            if str(r.get('Email')).strip().lower() == normalized_email:
                return False
        max_id = max([int(float(r.get('ID') or 0)) for r in rows]) if rows else 0
    except Exception:
        max_id = 0
        
    data = {
        'ID': max_id + 1,
        'Email': email,
        'Status': 'New',
        'Timestamp': datetime.utcnow().isoformat(),
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
    """Saves a new job to the job leads database if its URL is unique."""
    apply_url = normalize_external_url(data.get('CompanyURL') or '')
    if apply_url:
        if apply_url in seen_external_urls:
            logger.info(f"Skipping duplicate job saving: External URL {apply_url} already matched in cache.")
            return False
            
    rows = read_database_rows("jobs")
    for r in rows:
        r_url = normalize_external_url(r.get('CompanyURL') or '')
        if r_url and r_url == apply_url:
            if apply_url:
                seen_external_urls.add(apply_url)
            logger.info(f"Skipping duplicate job saving: External URL {apply_url} already matched in database.")
            return False

    max_id = max([int(float(r.get('JobID') or 0)) for r in rows]) if rows else 0
    new_job = {
        'JobID': max_id + 1,
        'JobTitle': data.get('JobTitle', ''),
        'CompanyName': data.get('CompanyName', ''),
        'LinkedIn_Company_URL': data.get('LinkedIn_Company_URL', ''),
        'CompanyURL': data.get('CompanyURL', ''),
        'ShortenURL': data.get('ShortenURL', ''),
        'SearchKeyword': data.get('SearchKeyword', ''),
        'Status': data.get('Status', 'NEW'),
        'ShortUrlCreated': data.get('ShortUrlCreated', '0'),
        'CreatedDateTime': data.get('CreatedDateTime') or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    }
    append_database_row("jobs", new_job)
    if apply_url:
        seen_external_urls.add(apply_url)
    return True

def load_jobs_for_referral(path=None, status_filter='Asked for Referral'):
    """Loads all job leads matching the target status filter."""
    rows = read_database_rows("jobs")
    return [r for r in rows if str(r.get('Status')).strip().lower() == status_filter.lower()]

def update_status_by_id(job_id, status, path=None):
    """Updates the status of a specific job lead by ID."""
    rows = read_database_rows("jobs")
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
    rows = read_database_rows("jobs")
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

def load_all_referrals(path=None):
    return read_database_rows("referrals")

def add_or_update_referral(referral_data, path=None):
    """Inserts a new referral outreach row or updates an existing one if matching."""
    rows = read_database_rows("referrals")
    target_profile = str(referral_data.get('Referral_Person_Profile_URL') or '').strip().lower()
    target_job_id = str(referral_data.get('JobID') or '').strip()
    
    updated = False
    for r in rows:
        curr_profile = str(r.get('Referral_Person_Profile_URL') or '').strip().lower()
        curr_job_id = str(r.get('JobID') or '').strip()
        if curr_profile == target_profile and curr_job_id == target_job_id:
            # Update columns
            for k, v in referral_data.items():
                if k != 'ReferralID':
                    r[k] = v
            updated = True
            break
            
    if not updated:
        max_id = max([int(float(r.get('ReferralID') or 0)) for r in rows]) if rows else 0
        referral_data['ReferralID'] = max_id + 1
        rows.append(referral_data)
        
    write_database_rows("referrals", rows)
    return True

def is_profile_already_contacted(profile_url, job_url=None, path=None):
    """Checks if a user has already sent outreach to this LinkedIn profile for this job/company."""
    rows = read_database_rows("referrals")
    target_profile = str(profile_url or '').strip().lower()
    for r in rows:
        if str(r.get('Referral_Person_Profile_URL') or '').strip().lower() == target_profile:
            return True
    return False

def edit_referral_contact_row(referral_id, referral_data, path=None):
    """Edits all columns of a referral connection record."""
    rows = read_database_rows("referrals")
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
    try:
        from config.user_profiles import get_selected_user_config
        user_conf = get_selected_user_config()
        connect_conf = user_conf.get("linkedin_connect", {})
        target = int(connect_conf.get("max_connections_per_company") or connect_conf.get("max_connections_per_run") or 5)
        
        referrals = load_all_referrals()
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

        rows = read_database_rows("jobs")
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
        leads = read_database_rows("jobs")
        referrals = read_database_rows("referrals")
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
