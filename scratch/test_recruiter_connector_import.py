import sys
import os

sys.path.append(os.getcwd())

try:
    from pipelines.linkedin_outreach.services.recruiter_connector import (
        run_recruiter_discovery,
        run_recruiter_messaging,
        get_recruiter_direct_message
    )
    print("Success: Imported run_recruiter_discovery, run_recruiter_messaging, and get_recruiter_direct_message!")
except Exception as e:
    print(f"Error importing recruiter connector: {e}")
    sys.exit(1)
