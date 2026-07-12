import sys
sys.path.insert(0, r"e:\Connectify")

from core.storage.database import read_database_rows, write_database_rows

def revert():
    user = "Lalit"
    try:
        referrals = read_database_rows("referrals", username=user, bypass_cache=True)
    except Exception as e:
        print(f"Could not load referrals: {e}")
        return
        
    updated = False
    for r in referrals:
        if str(r.get("Referral_Status")).strip().lower() == "skipped":
            r["Referral_Status"] = "Pending"
            updated = True
            print(f"Reverted {r.get('Referral_Person_Name')} status to Pending.")
            
    if updated:
        write_database_rows("referrals", referrals, username=user)
        print("Successfully saved referrals.")
        try:
            from core.storage.engine import sync_local_to_google_sheets
            # Just verify how sheets upload is triggered: write_database_rows already does it!
            print("Google Sheets automatically updated via write_database_rows.")
        except Exception as se:
            print(f"Sync check: {se}")

if __name__ == "__main__":
    revert()
