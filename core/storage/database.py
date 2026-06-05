import os
import shutil
import openpyxl
from datetime import datetime
from openpyxl.worksheet.table import Table, TableStyleInfo
from config.settings import (
    BASE_DIR, get_data_dir, get_job_tracker_file, get_job_leads_file, get_jobs_json_file, get_audit_json_file
)
from config.constants import SCRAPER_HEADERS, JOB_LEADS_HEADERS
from core.logging.config import logger
from core.utils.url_utils import is_valid_external_url, normalize_external_url

# Cache set for fast duplicate checks of external apply URLs
seen_external_urls = set()

def migrate_old_data_files():
    """Migrates existing tracking databases from the root directory to the active user's data/ directory."""
    from config.settings import get_active_user
    active_user = get_active_user()
    if not active_user:
        return
        
    old_files = {
        "job_tracker.xlsx": get_job_tracker_file(),
        "LinkedIn_Job_Tracker.xlsx": get_job_leads_file(),
        "linkedin_jobs.json": get_jobs_json_file(),
        "linkedin_jobs_audit.json": get_audit_json_file()
    }
    for old_name, new_path in old_files.items():
        old_path = os.path.join(BASE_DIR, old_name)
        if os.path.exists(old_path) and not os.path.exists(new_path):
            try:
                shutil.move(old_path, new_path)
                logger.info(f"Migrated legacy file to new storage directory: {old_name} -> {new_path}")
            except Exception as e:
                logger.error(f"Failed to migrate legacy file {old_name}: {e}")

# Run data files migration automatically upon module import
migrate_old_data_files()


def _trigger_mac_excel_reload(path):
    """Refreshes Microsoft Excel / Numbers document on macOS if open to show instantaneous updates."""
    try:
        import subprocess
        abs_path = os.path.abspath(path)
        filename = os.path.basename(path)
        
        reload_script = f'''\
        tell application "System Events"
            set excelRunning to (name of processes) contains "Microsoft Excel"
            set numbersRunning to (name of processes) contains "Numbers"
        end tell
        
        if excelRunning then
            tell application "Microsoft Excel"
                try
                    if exists workbook "{filename}" then
                        close workbook "{filename}" saving no
                        open POSIX file "{abs_path}"
                    end if
                end try
            end tell
        end if
        
        if numbersRunning then
            tell application "Numbers"
                try
                    set docName to "{filename}"
                    set docExists to false
                    repeat with doc in documents
                        if name of doc is docName then
                            set docExists to true
                            exit repeat
                        end if
                    end repeat
                    if docExists then
                        close document docName saving no
                        open POSIX file "{abs_path}"
                    end if
                end try
            end tell
        end if
        '''
        subprocess.run(["osascript", "-e", reload_script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


# =========================================================================
# 1. Email Scraper Database Operations (job_tracker.xlsx)
# =========================================================================

def init_scraper_store(path=None):
    """Initializes the scraper database Excel sheet if it does not exist."""
    if path is None:
        path = get_job_tracker_file()
    if not os.path.exists(path):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Jobs"
        ws.append(SCRAPER_HEADERS)
        
        col_count = len(SCRAPER_HEADERS)
        tab = Table(displayName="JobTrackerTable", ref=f"A1:{chr(64+col_count)}1")
        style = TableStyleInfo(
            name="TableStyleLight9",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False
        )
        tab.tableStyleInfo = style
        ws.add_table(tab)
        wb.save(path)
        _trigger_mac_excel_reload(path)
        
    trim_scraper_excel_to_schema(path)
    migrate_pending_to_new(path)

def trim_scraper_excel_to_schema(path=None):
    """Enforces scraper Excel headers conform to standard schema."""
    if path is None:
        path = get_job_tracker_file()
    if not os.path.exists(path):
        return
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    current_headers = [cell.value for cell in ws[1]]
    needed = SCRAPER_HEADERS
    header_map = {h: i+1 for i, h in enumerate(current_headers) if h in needed}
    
    for h in needed:
        if h not in header_map:
            ws.cell(row=1, column=len(current_headers)+1, value=h)
            header_map[h] = len(current_headers)+1
            current_headers.append(h)
            
    for target_idx, h in enumerate(needed, start=1):
        src_idx = header_map[h]
        if src_idx != target_idx:
            for row in range(1, ws.max_row + 1):
                ws.cell(row=row, column=target_idx, value=ws.cell(row=row, column=src_idx).value)
                
    max_col = ws.max_column
    if max_col > len(needed):
        ws.delete_cols(len(needed)+1, max_col - len(needed))
        
    ws._tables.clear()
    ref = f"A1:{chr(64+len(needed))}{ws.max_row}"
    tab = Table(displayName="JobTrackerTable", ref=ref)
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

def append_email(email, keyword='', path=None):
    """Appends extracted email to the job tracker if it's unique."""
    if path is None:
        path = get_job_tracker_file()
    init_scraper_store(path)
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    col_indices = {cell.value: idx for idx, cell in enumerate(ws[1], start=1)}
    id_col = col_indices.get('ID', 1)
    email_col = col_indices.get('Email', 2)
    
    normalized_email = str(email or '').strip().lower()
    for row in range(2, ws.max_row + 1):
        if str(ws.cell(row=row, column=email_col).value or '').strip().lower() == normalized_email:
            return False
            
    max_id = max([ws.cell(row=row, column=id_col).value or 0 for row in range(2, ws.max_row + 1)], default=0)
    new_id = int(max_id) + 1
    timestamp = datetime.utcnow().isoformat()
    new_row = [new_id, email, 'New', timestamp, keyword]
    ws.append(new_row)
    
    ws._tables.clear()
    col_count = len(SCRAPER_HEADERS)
    ref = f"A1:{chr(64+col_count)}{ws.max_row}"
    tab = Table(displayName="JobTrackerTable", ref=ref)
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
    return True

def update_status(email, status, path=None):
    """Updates status for a specific scraped email row."""
    if path is None:
        path = get_job_tracker_file()
    init_scraper_store(path)
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    col_indices = {cell.value: idx for idx, cell in enumerate(ws[1], start=1)}
    email_col = col_indices.get('Email', 2)
    status_col = col_indices.get('Status', 3)
    timestamp_col = col_indices.get('Timestamp', 4)
    normalized_email = str(email or '').strip().lower()
    updated = False
    
    for row in range(2, ws.max_row + 1):
        if str(ws.cell(row=row, column=email_col).value or '').strip().lower() == normalized_email:
            ws.cell(row=row, column=status_col, value=status)
            ws.cell(row=row, column=timestamp_col, value=datetime.utcnow().isoformat())
            updated = True
            break
            
    if updated:
        wb.save(path)
        _trigger_mac_excel_reload(path)
    return updated

def count_unique_emails(path=None):
    """Counts unique emails processed in the scraper sheet."""
    if path is None:
        path = get_job_tracker_file()
    if not os.path.exists(path):
        return 0
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    col_indices = {cell.value: idx for idx, cell in enumerate(ws[1], start=1)}
    email_col = col_indices.get('Email', 2)
    unique_emails = set()
    for row in range(2, ws.max_row + 1):
        val = ws.cell(row=row, column=email_col).value
        if val:
            unique_emails.add(str(val).strip().lower())
    return len(unique_emails)

def edit_row(row_id, email, status, keyword, path=None):
    """Modifies details of an existing scraper log by row ID."""
    if path is None:
        path = get_job_tracker_file()
    init_scraper_store(path)
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    col_indices = {cell.value: idx for idx, cell in enumerate(ws[1], start=1)}
    id_col = col_indices.get('ID', 1)
    email_col = col_indices.get('Email', 2)
    status_col = col_indices.get('Status', 3)
    keyword_col = col_indices.get('Keyword', 5)
    
    updated = False
    for row in range(2, ws.max_row + 1):
        if ws.cell(row=row, column=id_col).value == row_id:
            if email_col:
                ws.cell(row=row, column=email_col, value=email)
            if status_col:
                ws.cell(row=row, column=status_col, value=status)
            if keyword_col:
                ws.cell(row=row, column=keyword_col, value=keyword)
            updated = True
            break
            
    if updated:
        wb.save(path)
        _trigger_mac_excel_reload(path)
    return updated

def migrate_pending_to_new(path=None):
    """Legacy helper converting old 'Pending' labels to standard 'New'."""
    if path is None:
        path = get_job_tracker_file()
    if not os.path.exists(path):
        return
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    col_indices = {cell.value: idx for idx, cell in enumerate(ws[1], start=1)}
    status_col = col_indices.get('Status')
    if not status_col:
        return
    updated = False
    for row in range(2, ws.max_row + 1):
        val = ws.cell(row=row, column=status_col).value
        if val and str(val).strip().lower() == 'pending':
            ws.cell(row=row, column=status_col, value='New')
            updated = True
    if updated:
        wb.save(path)
        _trigger_mac_excel_reload(path)


# =========================================================================
# 2. LinkedIn Outreach Database Operations (LinkedIn_Job_Tracker.xlsx)
# =========================================================================

def init_job_leads_store(path=None):
    """Ensures the job search leads database exists and contains standard headers."""
    if path is None:
        path = get_job_leads_file()
    if not os.path.exists(path):
        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Jobs"
            ws.append(JOB_LEADS_HEADERS)
            update_job_leads_table(ws)
            wb.save(path)
            logger.info(f"Initialized new Excel tracker: {path}")
        except Exception as e:
            logger.error(f"Unable to initialize Excel tracker: {str(e)}")
    else:
        try:
            wb = openpyxl.load_workbook(path)
            ws = wb.active
            if ws.max_row == 0 or ws.cell(row=1, column=1).value != 'JobID':
                ws.insert_rows(1)
                for col_idx, header in enumerate(JOB_LEADS_HEADERS, start=1):
                    ws.cell(row=1, column=col_idx, value=header)
            update_job_leads_table(ws)
            wb.save(path)
        except Exception:
            pass

def update_job_leads_table(ws):
    """Updates formatting on the openpyxl job leads worksheet."""
    ws._tables.clear()
    max_row = max(ws.max_row, 1)
    col_letter = chr(64 + len(JOB_LEADS_HEADERS))
    ref_range = f"A1:{col_letter}{max_row}"
    tab = Table(displayName="JobTrackerTable", ref=ref_range)
    style = TableStyleInfo(
        name="TableStyleLight9", 
        showFirstColumn=False,
        showLastColumn=False, 
        showRowStripes=True, 
        showColumnStripes=False
    )
    tab.tableStyleInfo = style
    ws.add_table(tab)

def load_saved_jobs(path=None):
    """Loads all saved job applications into memory."""
    if path is None:
        path = get_job_leads_file()
    jobs = []
    normalized_urls = set()

    if os.path.exists(path):
        try:
            wb = openpyxl.load_workbook(path)
            ws = wb.active
            col_indices = {cell.value: idx for idx, cell in enumerate(ws[1], start=1)}
            
            company_url_col = col_indices.get('CompanyURL')
            company_col = col_indices.get('CompanyName')
            job_id_col = col_indices.get('JobID')
            keyword_col = col_indices.get('SearchKeyword')

            if company_url_col:
                for row in ws.iter_rows(min_row=2, values_only=True):
                    if not any(cell is not None for cell in row):
                        continue
                    company_url = row[company_url_col - 1]
                    if company_url:
                        company_url_str = str(company_url).strip()
                        normalized_urls.add(normalize_external_url(company_url_str))
                        
                        jobs.append({
                            "url": company_url_str,
                            "company": str(row[company_col - 1]).strip() if company_col and row[company_col - 1] else "",
                            "job_id": int(row[job_id_col - 1]) if job_id_col and row[job_id_col - 1] else None,
                            "keyword": str(row[keyword_col - 1]).strip() if keyword_col and row[keyword_col - 1] else ""
                        })
        except Exception as e:
            logger.error(f"Error loading tracker Excel file: {str(e)}")

    return jobs, normalized_urls

def save_job(data, path=None):
    """Saves a discovered external apply job to the Excel leads sheet."""
    if path is None:
        path = get_job_leads_file()
    url = (data.get("url") or "").strip()
    company = (data.get("company") or "").strip()
    search_keyword = (data.get("search_keyword") or "").strip()

    if not url or not is_valid_external_url(url):
        return False

    normalized_url = normalize_external_url(url)
    jobs, existing_urls = load_saved_jobs(path)

    if normalized_url in existing_urls:
        logger.info(f"Duplicate job URL skipped (normalized match): {url}")
        return False

    for existing_job in jobs:
        if existing_job.get("url") == url:
            logger.info(f"Duplicate job URL skipped (exact string match): {url}")
            return False

    try:
        init_job_leads_store(path)
        wb = openpyxl.load_workbook(path)
        ws = wb.active

        max_id = 0
        col_indices = {cell.value: idx for idx, cell in enumerate(ws[1], start=1)}
        job_id_col = col_indices.get('JobID', 1)

        for row in range(2, ws.max_row + 1):
            val = ws.cell(row=row, column=job_id_col).value
            if val is not None:
                try:
                    val_int = int(val)
                    if val_int > max_id:
                        max_id = val_int
                except ValueError:
                    pass

        new_job_id = max_id + 1
        created_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        row_data = []
        for header in JOB_LEADS_HEADERS:
            if header == 'JobID':
                row_data.append(new_job_id)
            elif header == 'CompanyName':
                row_data.append(company)
            elif header == 'CompanyURL':
                row_data.append(url)
            elif header == 'ShortenURL':
                row_data.append('')
            elif header == 'SearchKeyword':
                row_data.append(search_keyword)
            elif header == 'Status':
                row_data.append('NEW')
            elif header == 'ReferralAsked':
                row_data.append('No')
            elif header == 'ShortUrlCreated':
                row_data.append('No')
            elif header == 'Remarks':
                row_data.append('')
            elif header == 'CreatedDateTime':
                row_data.append(created_time)

        ws.append(row_data)

        # Sort jobs by ID
        rows_to_sort = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if any(cell is not None for cell in row):
                rows_to_sort.append(list(row))

        job_id_idx = JOB_LEADS_HEADERS.index('JobID')
        rows_to_sort.sort(key=lambda r: int(r[job_id_idx]) if r[job_id_idx] is not None else 0)

        while ws.max_row > 1:
            ws.delete_rows(2)

        for r in rows_to_sort:
            ws.append(r)

        update_job_leads_table(ws)
        wb.save(path)
        _trigger_mac_excel_reload(path)

        seen_external_urls.add(normalized_url)
        logger.info(f"Saved & Sorted in Excel Tracker (JobID {new_job_id}): {url}")
        return True

    except Exception as e:
        logger.error(f"Error saving job to Excel tracker: {str(e)}")
        return False

def load_jobs_for_referral(path=None, status_filter='Ask for referral'):
    """Loads all lead row dictionaries filtered by status."""
    if path is None:
        path = get_job_leads_file()
    if not os.path.exists(path):
        return []
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    col_indices = {cell.value: idx for idx, cell in enumerate(ws[1], start=1)}
    rows = []
    
    for row in range(2, ws.max_row + 1):
        raw_status = ws.cell(row=row, column=col_indices.get('Status')).value
        status = str(raw_status).strip().lower() if raw_status is not None else ''
        if status == status_filter.strip().lower():
            row_dict = {header: ws.cell(row=row, column=col_idx).value for header, col_idx in col_indices.items()}
            rows.append(row_dict)
    return rows



def update_status_by_id(job_id, status, path=None):
    """Updates status for a specific lead row identified by JobID."""
    if path is None:
        path = get_job_leads_file()
    if not os.path.exists(path):
        return False
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    col_indices = {cell.value: idx for idx, cell in enumerate(ws[1], start=1)}
    id_col = col_indices.get('JobID')
    status_col = col_indices.get('Status')
    timestamp_col = col_indices.get('CreatedDateTime')
    
    if not id_col or not status_col:
        return False
    updated = False
    for row in range(2, ws.max_row + 1):
        if ws.cell(row=row, column=id_col).value == job_id:
            ws.cell(row=row, column=status_col, value=status)
            if timestamp_col:
                ws.cell(row=row, column=timestamp_col, value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            updated = True
            break
            
    if updated:
        wb.save(path)
        _trigger_mac_excel_reload(path)
    return updated
