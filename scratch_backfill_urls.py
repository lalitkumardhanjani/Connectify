import os
import sys

# Add project root to python path
sys.path.insert(0, r"e:\Connectify")

from core.storage.database import read_database_rows, write_database_rows

def backfill():
    # Load all users or just default/Lalit
    users = ["Lalit", "default"]
    for user in users:
        print(f"Backfilling for user: {user}")
        try:
            jobs = read_database_rows("jobs", username=user, bypass_cache=True)
            referrals = read_database_rows("referrals", username=user, bypass_cache=True)
        except Exception as e:
            print(f"Could not load data for {user}: {e}")
            continue
            
        if not jobs or not referrals:
            print(f"No jobs or referrals found for {user}.")
            continue
            
        jobs_map = {}
        for j in jobs:
            jid = str(j.get("JobID") or "").strip()
            if jid:
                url = j.get("ShortenURL") or j.get("CompanyURL") or j.get("LinkedIn_Company_URL") or ""
                jobs_map[jid] = url
                
        updated = False
        for r in referrals:
            job_url = r.get("Job_URL") or r.get("Company_URL") or ""
            if not job_url:
                jid = str(r.get("JobID") or "").strip()
                if jid in jobs_map:
                    r["Job_URL"] = jobs_map[jid]
                    r["Company_URL"] = jobs_map[jid]
                    updated = True
                    print(f"Backfilled referral ID {r.get('ReferralID')}: {r.get('Referral_Person_Name')} -> {jobs_map[jid]}")
            else:
                # Ensure Job_URL is synchronized if only Company_URL was present
                if not r.get("Job_URL"):
                    r["Job_URL"] = job_url
                    updated = True
                    
        if updated:
            write_database_rows("referrals", referrals, username=user)
            print("Successfully saved backfilled referrals.")
            # Trigger Sheets sync
            try:
                from core.storage.engine import sync_local_to_google_sheets
                sync_local_to_google_sheets(user, "referrals")
                print("Synced to Google Sheets.")
            except Exception as se:
                print(f"Failed to sync to Sheets: {se}")

if __name__ == "__main__":
    backfill()
