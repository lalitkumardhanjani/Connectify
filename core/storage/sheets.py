import json
import time
import threading
from core.logging.config import logger
from config.constants import GOOGLE_SHEET_WORKSHEETS

# We will import gspread and google-auth inside functions to allow starting the app
# even if packages are still installing.

# ---------------------------------------------------------------------------
# In-memory TTL cache — prevents hammering the Google Sheets API quota (429)
# Each worksheet gets its own cache entry:  { worksheet_name: (timestamp, data) }
# ---------------------------------------------------------------------------
_cache_lock = threading.Lock()
_row_cache: dict = {}          # { worksheet_name: (fetched_at_monotonic, [rows]) }
_CACHE_TTL_SECONDS = 60        # Re-fetch from Sheets at most once per minute per worksheet


def _cache_get(worksheet_name: str):
    """Return cached rows if they are fresh, otherwise None."""
    with _cache_lock:
        entry = _row_cache.get(worksheet_name)
        if entry:
            fetched_at, rows = entry
            if time.monotonic() - fetched_at < _CACHE_TTL_SECONDS:
                return rows
    return None


def _cache_set(worksheet_name: str, rows: list):
    """Store rows in the cache."""
    with _cache_lock:
        _row_cache[worksheet_name] = (time.monotonic(), rows)


def _cache_invalidate(worksheet_name: str):
    """Remove a worksheet entry from the cache, forcing the next read to fetch fresh data."""
    with _cache_lock:
        _row_cache.pop(worksheet_name, None)


def _cache_invalidate_all():
    """Clear the entire row cache."""
    with _cache_lock:
        _row_cache.clear()


# ---------------------------------------------------------------------------


def get_sheets_client(credentials_json_content):
    """Initializes the gspread client using Service Account JSON key string."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        raise ImportError("Required packages 'gspread' or 'google-auth' are not installed in python environment.")

    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        creds_data = json.loads(credentials_json_content)
        credentials = Credentials.from_service_account_info(creds_data, scopes=scopes)
        client = gspread.authorize(credentials)
        return client
    except Exception as e:
        logger.error(f"Google Sheets Authorization failed: {e}")
        raise ValueError(f"Google authorization failed: {e}")

_spreadsheet_cache = {}
_spreadsheet_cache_lock = threading.Lock()
_SPREADSHEET_CACHE_TTL = 30

def get_open_spreadsheet(spreadsheet_url, credentials_json_content):
    """Retrieve an opened spreadsheet, using a thread-safe TTL cache to prevent duplicate open_by_url requests."""
    with _spreadsheet_cache_lock:
        entry = _spreadsheet_cache.get(spreadsheet_url)
        if entry:
            ts, sh = entry
            if time.monotonic() - ts < _SPREADSHEET_CACHE_TTL:
                return sh
                
    client = get_sheets_client(credentials_json_content)
    sh = client.open_by_url(spreadsheet_url)
    with _spreadsheet_cache_lock:
        _spreadsheet_cache[spreadsheet_url] = (time.monotonic(), sh)
    return sh



def format_worksheet(ws, headers):
    """Applies header style, freezes first row, and auto-resizes columns."""
    try:
        num_cols = len(headers)
        end_col_letter = chr(64 + num_cols)
        header_range = f"A1:{end_col_letter}1"
        
        # Format header row: dark navy blue background (#1f2937), white bold text, centered
        ws.format(header_range, {
            "textFormat": {
                "bold": True,
                "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}
            },
            "backgroundColor": {
                "red": 31/255.0, "green": 41/255.0, "blue": 55/255.0
            },
            "horizontalAlignment": "CENTER"
        })
        ws.freeze(rows=1)
        ws.columns_auto_resize(0, num_cols)
    except Exception as e:
        logger.warning(f"Failed to apply professional formatting to worksheet '{ws.title}': {e}")


def ensure_worksheets_exist(spreadsheet_url, credentials_json_content):
    """Checks and creates all required worksheets in the Google Sheet, setting up their table headers."""
    client = get_sheets_client(credentials_json_content)
    try:
        sh = client.open_by_url(spreadsheet_url)
    except Exception as e:
        logger.error(f"Failed to open Google Sheet by URL: {e}")
        raise ValueError(f"Failed to open Google Sheet. Please check the URL and confirm the sheet is shared with the service account email. Error: {e}")

def ensure_worksheets_exist(spreadsheet_url, credentials_json_content):
    """Checks and creates all required worksheets in the Google Sheet, setting up their table headers."""
    try:
        sh = get_open_spreadsheet(spreadsheet_url, credentials_json_content)
    except Exception as e:
        logger.error(f"Failed to open Google Sheet: {e}")
        raise ValueError(f"Failed to open Google Sheet. Please check the URL and confirm the sheet is shared with the service account email. Error: {e}")


    # Fetch all worksheet objects in a single call to save read API quota
    try:
        worksheets = sh.worksheets()
        worksheets_by_title = {ws.title: ws for ws in worksheets}
    except Exception as e:
        logger.error(f"Failed to fetch worksheets metadata: {e}")
        raise e

    # --- Self-Healing Migration: Old config sheet -> New 4-sheet layout ---
    old_config_ws_name = "Profile & Settings"
    if old_config_ws_name in worksheets_by_title:
        logger.info("Upgrading old single 'Profile & Settings' worksheet to 4 separate worksheets layout...")
        try:
            from core.storage.engine import unflatten_dict, get_setting_meta
            old_ws = worksheets_by_title[old_config_ws_name]
            old_records = old_ws.get_all_records()
            
            flat_dict = {}
            for rec in old_records:
                k = rec.get("Key")
                v = rec.get("Value")
                if k:
                    flat_dict[k] = v if v is not None else ""
                    
            config = unflatten_dict(flat_dict)
            
            # Helper to check/create worksheet
            def get_or_create_ws(title, headers_list):
                if title in worksheets_by_title:
                    return worksheets_by_title[title]
                w = sh.add_worksheet(title=title, rows="500", cols=str(len(headers_list)))
                worksheets_by_title[title] = w
                return w

            # A. Profile sheet
            profile_headers = GOOGLE_SHEET_WORKSHEETS["profile"]["headers"]
            profile_ws = get_or_create_ws(GOOGLE_SHEET_WORKSHEETS["profile"]["name"], profile_headers)
            profile_data = config.get("profile", {})
            profile_field_mapping = {
                "First Name": "first_name", "Last Name": "last_name", "Email Address": "email",
                "Phone Number": "phone", "LinkedIn URL": "linkedin_url", "Resume Filename": "resume_name",
                "Resume Short URL": "resume_url", "Years of Experience": "experience",
                "Current Location": "current_location", "Preferred Locations": "preferred_locations",
                "Current CTC": "current_ctc", "Expected CTC": "expected_ctc",
                "Notice Period": "notice_period", "Last Working Day": "last_working_day"
            }
            row_vals = [str(profile_data.get(profile_field_mapping[h], "")) for h in profile_headers]
            profile_ws.clear()
            profile_ws.update(range_name="A1", values=[profile_headers, row_vals])
            format_worksheet(profile_ws, profile_headers)
            
            # B. Templates sheet
            templates_headers = GOOGLE_SHEET_WORKSHEETS["templates"]["headers"]
            templates_ws = get_or_create_ws(GOOGLE_SHEET_WORKSHEETS["templates"]["name"], templates_headers)
            template_rows = [
                ["Outreach Email", flat_dict.get("email_scraper.email_subject", ""), flat_dict.get("email_scraper.email_template", ""), "email_scraper.email_template"],
                ["LinkedIn Connection Note", "", flat_dict.get("linkedin_connect.message_template", ""), "linkedin_connect.message_template"],
                ["Recruiter Message", "", flat_dict.get("recruiter_outreach.message_template", ""), "recruiter_outreach.message_template"],
                ["Recruiter Direct Message", "", flat_dict.get("recruiter_outreach.direct_message_template", ""), "recruiter_outreach.direct_message_template"],
                ["Referral Request", "", flat_dict.get("referral_outreach.message_template", ""), "referral_outreach.message_template"]
            ]
            templates_ws.clear()
            templates_ws.update(range_name="A1", values=[templates_headers] + template_rows)
            format_worksheet(templates_ws, templates_headers)
            
            # C. Keywords sheet
            keywords_headers = GOOGLE_SHEET_WORKSHEETS["keywords"]["headers"]
            keywords_ws = get_or_create_ws(GOOGLE_SHEET_WORKSHEETS["keywords"]["name"], keywords_headers)
            
            def get_kw_list(key):
                val = flat_dict.get(key, "[]")
                if isinstance(val, list):
                    return val
                if isinstance(val, str):
                    try:
                        return json.loads(val)
                    except Exception:
                        return [x.strip() for x in val.split(",") if x.strip()]
                return []
            
            kw_lists = [
                get_kw_list("email_scraper.search_keywords"),
                get_kw_list("email_scraper.title_keywords"),
                get_kw_list("email_scraper.excluded_keywords"),
                get_kw_list("linkedin_connect.search_keywords"),
                get_kw_list("linkedin_connect.title_keywords"),
                get_kw_list("linkedin_connect.excluded_keywords")
            ]
            max_len = max(len(lst) for lst in kw_lists) if kw_lists else 0
            kw_rows = []
            for i in range(max_len):
                kw_rows.append([
                    (kw_lists[j][i] if i < len(kw_lists[j]) else "") for j in range(6)
                ])
            keywords_ws.clear()
            keywords_ws.update(range_name="A1", values=[keywords_headers] + kw_rows)
            format_worksheet(keywords_ws, keywords_headers)
            
            # D. Settings sheet
            settings_headers = GOOGLE_SHEET_WORKSHEETS["settings"]["headers"]
            settings_ws = get_or_create_ws(GOOGLE_SHEET_WORKSHEETS["settings"]["name"], settings_headers)
            settings_rows = []
            for key, val in flat_dict.items():
                if (key.startswith("profile.") or 
                    key.endswith("_template") or 
                    key.endswith("_keywords") or 
                    key == "email_scraper.email_subject" or
                    key == "recruiter_outreach.direct_message_template"):
                    continue
                cat, name = get_setting_meta(key)
                settings_rows.append([cat, name, val, key])
            
            settings_rows.sort(key=lambda x: (x[0], x[1]))
            settings_ws.clear()
            settings_ws.update(range_name="A1", values=[settings_headers] + settings_rows)
            format_worksheet(settings_ws, settings_headers)
            
            # Delete the old worksheet
            sh.del_worksheet(old_ws)
            worksheets_by_title.pop(old_config_ws_name, None)
            logger.info("Migration to new 4-sheet settings worksheets successful!")
        except Exception as migration_error:
            logger.error(f"Failed self-healing migration of settings sheets: {migration_error}")

    # Check if all worksheets exist
    all_exist = True
    for key, info in GOOGLE_SHEET_WORKSHEETS.items():
        if info["name"] not in worksheets_by_title:
            all_exist = False
            break

    if all_exist:
        logger.debug("All required worksheets exist. Skipping check & formatting.")
        return

    # If any sheet is missing, build them
    for key, info in GOOGLE_SHEET_WORKSHEETS.items():
        name = info["name"]
        headers = info["headers"]
        
        if name in worksheets_by_title:
            continue
            
        try:
            ws = sh.add_worksheet(title=name, rows="1000", cols=str(len(headers)))
            ws.append_row(headers)
            logger.info(f"Created worksheet '{name}' and wrote headers.")
            format_worksheet(ws, headers)
            time.sleep(0.5)
        except Exception as ws_err:
            logger.error(f"Failed to create worksheet '{name}': {ws_err}")

    _cache_invalidate_all()



def read_rows(spreadsheet_url, credentials_json_content, worksheet_name):
    """Reads all rows from a worksheet and returns them as a list of dictionaries mapped by headers.
    
    Results are cached in-memory for up to 60 seconds to prevent hitting the Google Sheets
    API read quota limit (60 reads/min/user), which causes HTTP 429 errors.
    """
    # Return cached result if fresh
    cached = _cache_get(worksheet_name)
    if cached is not None:
        logger.debug(f"Cache hit for worksheet '{worksheet_name}' ({len(cached)} rows)")
        return cached

    try:
        sh = get_open_spreadsheet(spreadsheet_url, credentials_json_content)
        ws = sh.worksheet(worksheet_name)

        data = ws.get_all_records()
        _cache_set(worksheet_name, data)
        logger.debug(f"Fetched {len(data)} rows from Google Sheets '{worksheet_name}' and cached.")
        return data
    except Exception as e:
        logger.error(f"Error reading Google Sheets worksheet '{worksheet_name}': {e}")
        raise e


def write_rows(spreadsheet_url, credentials_json_content, worksheet_name, data_dicts):
    """Bulk writes/overwrites data to a worksheet, retaining the header row."""
    try:
        sh = get_open_spreadsheet(spreadsheet_url, credentials_json_content)
        ws = sh.worksheet(worksheet_name)

        
        # Get headers from constants
        headers = None
        for key, info in GOOGLE_SHEET_WORKSHEETS.items():
            if info["name"] == worksheet_name:
                headers = info["headers"]
                break
        
        if not headers:
            # Fallback to current sheet headers if not found in constants
            headers = ws.row_values(1)
            
        rows_to_write = [headers]
        for row in data_dicts:
            new_row = []
            for h in headers:
                val = row.get(h)
                if val is None:
                    val = ""
                new_row.append(str(val))
            rows_to_write.append(new_row)
            
        # Overwrite all data: clear sheet and write
        ws.clear()
        ws.update(range_name="A1", values=rows_to_write)
        logger.info(f"Overwrote {len(data_dicts)} rows in Google Sheets worksheet '{worksheet_name}'")
        
        # Style sheet and adjust auto-widths
        format_worksheet(ws, headers)
        
        # Invalidate cache so next read returns fresh data
        _cache_invalidate(worksheet_name)
        # Also update cache with the data we just wrote (avoids an immediate re-fetch)
        _cache_set(worksheet_name, data_dicts)
    except Exception as e:
        logger.error(f"Error writing to Google Sheets worksheet '{worksheet_name}': {e}")
        raise e


def append_row(spreadsheet_url, credentials_json_content, worksheet_name, data_dict):
    """Appends a single dictionary row to the worksheet matching column headers."""
    try:
        sh = get_open_spreadsheet(spreadsheet_url, credentials_json_content)
        ws = sh.worksheet(worksheet_name)

        
        headers = None
        for key, info in GOOGLE_SHEET_WORKSHEETS.items():
            if info["name"] == worksheet_name:
                headers = info["headers"]
                break
                
        if not headers:
            headers = ws.row_values(1)
            
        row_values = []
        for h in headers:
            val = data_dict.get(h)
            if val is None:
                val = ""
            row_values.append(str(val))
            
        ws.append_row(row_values)
        logger.info(f"Appended 1 row to Google Sheets worksheet '{worksheet_name}'")
        
        # Invalidate cache for this worksheet so next read picks up the new row
        _cache_invalidate(worksheet_name)
    except Exception as e:
        logger.error(f"Error appending to Google Sheets worksheet '{worksheet_name}': {e}")
        raise e
