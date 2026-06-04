import re

def extract_emails(text):
    """Extract all email addresses from the given text using regex."""
    if not text:
        return []
    
    # Regex to match email addresses
    email_pattern = r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
    emails = re.findall(email_pattern, text)
    
    # Return unique emails
    return list(set(emails))