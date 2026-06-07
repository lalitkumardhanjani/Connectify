import sys
import os

sys.path.append(os.getcwd())

from pipelines.linkedin_outreach.services.recruiter_connector import get_recruiter_direct_message

# Mocking user config retrieval or using current config
msg = get_recruiter_direct_message(
    company="Acme Corp",
    first_name="Alice",
    resume_link="https://myresume.com/pdf",
    person_name="Alice Recruiter"
)

print("--- Generated Recruiter Message Preview ---")
print(msg)
print("------------------------------------------")

# Assert that some key components exist
assert "Alice" in msg, "First name placeholder not resolved!"
assert "Acme Corp" in msg or "the company" in msg, "Company name placeholder not resolved!"
print("Test completed successfully! Variables resolve as expected.")
