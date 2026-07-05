import json
import time
from core.logging.config import logger
from config.constants import GOOGLE_SHEET_WORKSHEETS

# We will import gspread and google-auth inside functions to allow starting the app
# even if packages are still installing.

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


def read_rows(spreadsheet_url, credentials_json_content, worksheet_name):
    """Reads all rows from a worksheet and returns them as a list of dictionaries mapped by headers."""
    client = get_sheets_client(credentials_json_content)
    try:
        sh = client.open_by_url(spreadsheet_url)
        ws = sh.worksheet(worksheet_name)
        data = ws.get_all_records()
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
        ws.update(range_name=f"A1", values=rows_to_write)
        logger.info(f"Overwrote {len(data_dicts)} rows in Google Sheets worksheet '{worksheet_name}'")
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
    except Exception as e:
        logger.error(f"Error appending to Google Sheets worksheet '{worksheet_name}': {e}")
        raise e
