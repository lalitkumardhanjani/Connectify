#!/usr/bin/env python
import os
import sys
import json
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# Set up path to import Connectify modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.user_profiles import get_selected_user_config, get_selected_user_name
from config.constants import GOOGLE_SHEET_WORKSHEETS
from config.settings import get_job_tracker_file, get_job_leads_file, get_referrals_file

def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    print("=================================================================")
    print("        Connectify Google Sheets Idempotent Migration Utility    ")
    print("=================================================================")
    
    # 1. Fetch user configuration
    username = get_selected_user_name()
    if not username:
        print("❌ Error: No active user profile selected. Please start the app first.")
        sys.exit(1)
        
    print(f"Active Profile: {username}")
    user_conf = get_selected_user_config()
    global_settings = user_conf.get("global_settings", {})
    
    sheet_url = global_settings.get("google_sheet_url")
    creds_content = global_settings.get("google_credentials_json")
    
    if not sheet_url or not creds_content:
        print("❌ Error: Google Sheets configuration is missing in your active profile settings.")
        print("\nTo configure Google Sheets:")
        print("1. Start the application (python app.py).")
        print("2. Navigate to 'Settings' > 'Database Storage' tab.")
        print("3. Set storage type to 'Google Sheets', enter your URL and service account credentials.")
        print("4. Click 'Save Database Configuration' and try running this script again.")
        sys.exit(1)
        
    print(f"Google Sheet URL: {sheet_url}")
    
    # 2. Authenticate
    print("\nStep 1: Authenticating with Google APIs...")
    try:
        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        creds_dict = json.loads(creds_content)
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(credentials)
        print("✅ Authentication successful.")
    except Exception as e:
        print(f"❌ Authentication Failed: {e}")
        sys.exit(1)
        
    # 3. Open Spreadsheet
    print("\nStep 2: Connecting to Google Sheet...")
    try:
        sh = client.open_by_url(sheet_url)
        print(f"✅ Successfully opened: '{sh.title}'")
    except Exception as e:
        print(f"❌ Failed to open Google Sheet: {e}")
        print("Please check that your sheet URL is correct and shared with Editor access to your service account email:")
        print(f"👉 {creds_dict.get('client_email')}")
        sys.exit(1)

    existing_sheets = [sheet.title for sheet in sh.worksheets()]
    
    local_paths = {
        "Job Leads": get_job_leads_file(),
        "Scraped Emails": get_job_tracker_file(),
        "Referrals & Connections": get_referrals_file()
    }
    
    # 4. Migrate and Format worksheets
    print("\nStep 3: Beginning data migration...")
    import time
    
    for key, info in GOOGLE_SHEET_WORKSHEETS.items():
        if key not in ("jobs", "emails", "referrals"):
            continue
        ws_name = info["name"]
        headers = info["headers"]
        local_file = local_paths[ws_name]
        
        print(f"\n📁 Processing '{ws_name}'...")
        time.sleep(2.0)  # Throttling to avoid 429 Google Sheets rate limit
        
        # Get or create worksheet
        try:
            if ws_name in existing_sheets:
                ws = sh.worksheet(ws_name)
            else:
                if ws_name == "Job Leads" and len(existing_sheets) == 1 and existing_sheets[0].lower().startswith("sheet"):
                    ws = sh.worksheet(existing_sheets[0])
                    ws.update_title(ws_name)
                else:
                    ws = sh.add_worksheet(title=ws_name, rows="1000", cols=str(len(headers)))
        except Exception as e:
            print(f"  ❌ Error initializing worksheet {ws_name}: {e}")
            continue
            
        # Determine unique key index
        id_col_name = "JobID" if ws_name == "Job Leads" else ("ID" if ws_name == "Scraped Emails" else "ReferralID")
        
        # Load existing Google Sheet records to prevent duplicates
        try:
            existing_values = ws.get_all_values()
            if len(existing_values) > 1:
                col_indices = {val: idx for idx, val in enumerate(existing_values[0])}
                key_idx = col_indices.get(id_col_name)
                if key_idx is not None:
                    existing_ids = set(str(row[key_idx]).strip() for row in existing_values[1:] if len(row) > key_idx)
                else:
                    existing_ids = set()
            else:
                existing_ids = set()
        except Exception as e:
            print(f"  ⚠️ Warning reading existing rows: {e}. Rewriting headers.")
            existing_ids = set()
            ws.clear()
            ws.update(range_name="A1", values=[headers])
            existing_values = [headers]
            
        # Write headers if empty
        if not existing_values or len(existing_values) == 0:
            ws.update(range_name="A1", values=[headers])
            
        # Read local Excel file data
        new_rows_count = 0
        skipped_count = 0
        
        if os.path.exists(local_file):
            try:
                df = pd.read_excel(local_file)
                df = df.fillna("")
                
                rows_to_append = []
                for index, row in df.iterrows():
                    row_id = str(row.get(id_col_name, "")).strip()
                    if not row_id or row_id == ".0" or row_id == "":
                        continue
                        
                    # Clean decimals from IDs if present
                    if row_id.endswith(".0"):
                        row_id = row_id[:-2]
                        
                    if row_id in existing_ids:
                        skipped_count += 1
                        continue
                        
                    # Construct row array
                    row_data = []
                    for h in headers:
                        val = row.get(h, "")
                        if val is None:
                            val = ""
                        # Convert float IDs to clean strings
                        if h == id_col_name and str(val).endswith(".0"):
                            val = str(val)[:-2]
                        row_data.append(str(val))
                    rows_to_append.append(row_data)
                    
                if rows_to_append:
                    ws.append_rows(rows_to_append)
                    new_rows_count = len(rows_to_append)
                
                print(f"  📊 Status: Migrated {new_rows_count} new rows. Skipped {skipped_count} duplicates.")
            except Exception as e:
                print(f"  ❌ Error migrating local file {local_file}: {e}")
        else:
            print(f"  ℹ️ Local Excel file '{os.path.basename(local_file)}' not found. Skipping data import.")
            
        # 5. Format worksheet (idempotently styling)
        print(f"  🎨 Applying professional formatting to '{ws_name}'...")
        try:
            num_cols = len(headers)
            end_col_letter = chr(64 + num_cols)
            header_range = f"A1:{end_col_letter}1"
            
            # Format header: dark navy blue background (#1f2937), white bold text, centered
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
            
            # Freeze row 1
            ws.freeze(rows=1)
            
            # Set basic filters (wrapped in try/except in case a structured table exists)
            try:
                ws.clear_basic_filter()
            except Exception:
                pass
            try:
                ws.set_basic_filter()
            except Exception:
                pass
                
            # Auto-resize column widths
            ws.columns_auto_resize(0, num_cols)
            print(f"  ✅ Formatting successfully applied to '{ws_name}'")
        except Exception as e:
            print(f"  ⚠️ Formatting warning: {e}")

    # 6. Set database mode to sheets and upload settings
    print("\nStep 4: Activating Google Sheets mode and uploading configuration settings...")
    try:
        user_conf["global_settings"]["database_type"] = "google_sheets"
        
        from core.storage.engine import GoogleSheetsStorageProvider
        provider = GoogleSheetsStorageProvider()
        provider.save_config(username, user_conf)
        print("✅ User configuration saved & uploaded to Google Sheets. Active Storage is now GOOGLE SHEETS.")
    except Exception as e:
        print(f"❌ Error updating configuration settings: {e}")
        
    print("\n🎉 Migration process completed successfully!")
    print(f"👉 Open your Google Sheet here: {sheet_url}")

if __name__ == "__main__":
    main()
