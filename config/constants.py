# System-wide static default parameters

DBA_KEYWORDS_DEFAULT = []

LINKEDIN_CONNECT_KEYWORDS_DEFAULT = []

# Table schemas for tracking spreadsheets
SCRAPER_HEADERS = ['ID', 'Email', 'Status', 'Timestamp', 'Keyword', 'PostURL', 'CompanyName', 'Experience', 'Location']

JOB_LEADS_HEADERS = [
    'JobID', 'JobTitle', 'CompanyName', 'LinkedIn_Company_URL', 'CompanyURL', 'ShortenURL', 'SearchKeyword', 'Status', 
    'ShortUrlCreated', 'CreatedDateTime', 'Experience', 'Location'
]

REFERRAL_HEADERS = [
    'ReferralID', 'JobID', 'CompanyName', 'Job_URL', 'Referral_Person_Name', 'Referral_Person_Email',
    'Referral_Person_Profile_URL', 'Referral_Source',
    'Referral_Status', 'Employment_Verification_Status', 'Sent_Time', 'Error_Reason'
]

GOOGLE_SHEET_WORKSHEETS = {
    "jobs": {
        "name": "Job Leads",
        "headers": JOB_LEADS_HEADERS
    },
    "emails": {
        "name": "Scraped Emails",
        "headers": SCRAPER_HEADERS
    },
    "referrals": {
        "name": "Referrals & Connections",
        "headers": REFERRAL_HEADERS
    },
    "profile": {
        "name": "User Profile",
        "headers": [
            "First Name", "Last Name", "Email Address", "Phone Number", "LinkedIn URL", 
            "Resume Filename", "Resume Short URL", "Years of Experience", "Current Location", 
            "Preferred Locations", "Current CTC", "Expected CTC", "Notice Period", "Last Working Day"
        ]
    },
    "templates": {
        "name": "Message Templates",
        "headers": ["Template Name", "Subject", "Body", "Key"]
    },
    "keywords": {
        "name": "Keyword Lists",
        "headers": [
            "Scraper Search Keywords", "Scraper Title Keywords", "Scraper Excluded Keywords",
            "Connect Search Keywords", "Connect Title Keywords", "Connect Excluded Keywords"
        ]
    },
    "settings": {
        "name": "Application Settings",
        "headers": ["Category", "Setting Name", "Value", "Key"]
    }
}
