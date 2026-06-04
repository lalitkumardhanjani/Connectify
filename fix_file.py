import re

with open("linkdin_connect.py", "r") as f:
    content = f.read()

correct_function = """def build_message(employee_name, company, position, job_url, max_length=200):
    first_name = (employee_name or "there").split()[0]
    job_title = position or "this role"
    role_phrase = f"the {job_title} role" if job_title != "this role" else "this role"
    
    message = f"Hi {first_name}, my sister is interested in {role_phrase} at {company}. Could you consider referring her? CV: {RESUME_LINK} Job: {job_url}"

    if len(message) <= max_length:
        return message

    compact_message = f"Hi {first_name}, could you refer my sister for {role_phrase} at {company}? CV:{RESUME_LINK} Job:{job_url}"

    if len(compact_message) <= max_length:
        return compact_message

    return f"Refer my sister for {role_phrase} @ {company}? CV:{RESUME_LINK} Job:{job_url}"[:max_length]
"""

# Find the start of get_message or generate_referral_note (which seems to be messed up)
start_idx = content.find("def get_message(")

if start_idx != -1:
    # Find safe_click which seems to be the next valid function after the broken block
    end_idx = content.find("def safe_click(")
    
    if end_idx != -1:
        # Replace the entire broken block with just our single clean build_message function
        new_content = content[:start_idx] + correct_function + "\n\n" + content[end_idx:]
        
        with open("linkdin_connect.py", "w") as f:
            f.write(new_content)
        print("File fixed successfully.")
    else:
        print("Could not find safe_click.")
else:
    print("Could not find get_message.")
