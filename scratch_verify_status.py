import sys
sys.path.insert(0, r"e:\Connectify")

from core.storage.database import read_database_rows

def verify():
    user = "Lalit"
    try:
        referrals = read_database_rows("referrals", username=user, bypass_cache=True)
    except Exception as e:
        print(f"Could not load referrals: {e}")
        return
        
    target_names = ["Ashish Aryan", "Vishal Jain", "Vidul Dabir", "Anushka Sharma", "Pratik Bedase"]
    for r in referrals:
        name = r.get("Referral_Person_Name")
        if name in target_names:
            print(f"Name: {name:20} | Status: {r.get('Referral_Status')} | Job_URL: {r.get('Job_URL')}")

if __name__ == "__main__":
    verify()
