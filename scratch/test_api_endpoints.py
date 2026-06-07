import os
import sys
import openpyxl
import json
import urllib.request
import shutil

# Ensure the root directory is in the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import get_job_tracker_file
from core.storage.database import init_scraper_store, update_status

def test_api_endpoints():
    tracker_file = get_job_tracker_file()
    backup_file = tracker_file + ".bak"
    
    # 1. Back up current tracker file if it exists
    has_backup = False
    if os.path.exists(tracker_file):
        shutil.copyfile(tracker_file, backup_file)
        has_backup = True
        print(f"Backed up current job tracker to {backup_file}")
    
    try:
        # Create a fresh test tracker file
        if os.path.exists(tracker_file):
            os.remove(tracker_file)
            
        init_scraper_store()
        
        # Add test rows: one 'New', one 'Sent', one 'Skipped'
        wb = openpyxl.load_workbook(tracker_file)
        ws = wb.active
        ws.append([1, "new@example.com", "New", "Python", "2026-06-07T08:50:00"])
        ws.append([2, "sent@example.com", "Sent", "Java", "2026-06-07T08:50:00"])
        ws.append([3, "skipped@example.com", "Skipped", "C#", "2026-06-07T08:50:00"])
        wb.save(tracker_file)
        print("Set up test database rows.")
        
        # 2. Query the /api/email_stats endpoint
        print("Querying /api/email_stats...")
        req = urllib.request.Request("http://127.0.0.1:5001/api/email_stats")
        with urllib.request.urlopen(req) as response:
            stats = json.loads(response.read().decode())
            
        print("API stats response:", json.dumps(stats, indent=2))
        
        # Assertions
        assert stats["total_emails"] == 3, f"Expected 3 emails, got {stats['total_emails']}"
        assert stats["sent"] == 1, f"Expected 1 sent, got {stats['sent']}"
        assert stats["pending"] == 1, f"Expected 1 pending, got {stats['pending']}"
        assert stats["skipped"] == 1, f"Expected 1 skipped, got {stats['skipped']}"
        assert stats["status_distribution"]["skipped"] == 1, f"Expected status_distribution['skipped'] == 1, got {stats['status_distribution'].get('skipped')}"
        
        print("API /api/email_stats assertions passed successfully!")
        
        # 3. Query the /api/data/job_tracker data endpoint
        print("Querying /api/data/job_tracker...")
        req = urllib.request.Request("http://127.0.0.1:5001/api/data/job_tracker")
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            
        print(f"API data response (has {len(data)} items):")
        for row in data:
            print(f"Row ID={row.get('ID')}: Email={row.get('Email')}, Status={row.get('Status')}")
            
        # Verify the skipped row is present and correct
        skipped_rows = [r for r in data if r.get('Email') == 'skipped@example.com']
        assert len(skipped_rows) == 1, "Expected to find skipped lead in data API"
        assert skipped_rows[0].get('Status') == 'Skipped', f"Expected status 'Skipped', got {skipped_rows[0].get('Status')}"
        
        print("API /api/data/job_tracker assertions passed successfully!")
        print("\nALL API ENDPOINT INTEGRATION TESTS PASSED!")
        
    finally:
        # Restore backup
        if os.path.exists(tracker_file):
            os.remove(tracker_file)
        if has_backup:
            shutil.copyfile(backup_file, tracker_file)
            os.remove(backup_file)
            print("Restored original job tracker.")
        else:
            print("No original job tracker to restore.")

if __name__ == "__main__":
    test_api_endpoints()
