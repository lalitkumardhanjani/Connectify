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


def ensure_worksheets_exist(spreadsheet_url, credentials_json_content):
    """Checks and creates all required worksheets in the Google Sheet, setting up their table headers."""
    client = get_sheets_client(credentials_json_content)
    try:
        sh = client.open_by_url(spreadsheet_url)
    except Exception as e:
        logger.error(f"Failed to open Google Sheet by URL: {e}")
        raise ValueError(f"Failed to open Google Sheet. Please check the URL and confirm the sheet is shared with the service account email. Error: {e}")

    for key, info in GOOGLE_SHEET_WORKSHEETS.items():
        name = info["name"]
        headers = info["headers"]
        
        try:
            ws = sh.worksheet(name)
            # Verify if headers are set, if sheet is empty set headers
            first_row = ws.row_values(1)
            if not first_row:
                ws.append_row(headers)
                logger.info(f"Initialized headers for existing worksheet: '{name}'")
        except Exception:
            # Worksheet does not exist, create it and write headers
            ws = sh.add_worksheet(title=name, rows="1000", cols=str(len(headers)))
            ws.append_row(headers)
            logger.info(f"Created worksheet '{name}' and wrote headers.")
            time.sleep(1)

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

    client = get_sheets_client(credentials_json_content)
    try:
        sh = client.open_by_url(spreadsheet_url)
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
    client = get_sheets_client(credentials_json_content)
    try:
        sh = client.open_by_url(spreadsheet_url)
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
        
        # Invalidate cache so next read returns fresh data
        _cache_invalidate(worksheet_name)
        # Also update cache with the data we just wrote (avoids an immediate re-fetch)
        _cache_set(worksheet_name, data_dicts)
    except Exception as e:
        logger.error(f"Error writing to Google Sheets worksheet '{worksheet_name}': {e}")
        raise e


def append_row(spreadsheet_url, credentials_json_content, worksheet_name, data_dict):
    """Appends a single dictionary row to the worksheet matching column headers."""
    client = get_sheets_client(credentials_json_content)
    try:
        sh = client.open_by_url(spreadsheet_url)
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
